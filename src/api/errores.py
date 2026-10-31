"""Conversión de rechazos de negocio a respuestas HTTP.

Solo se convierten los rechazos de negocio (Resultado.rechazo y ErrorDominio) en HTTP 422 con el motivo
original. Cualquier otra excepción es una falla técnica: no se captura y FastAPI responde 500."""
from __future__ import annotations
import logging
from typing import List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from application.resultados import Resultado
from domain.valores import ErrorDominio
from .esquemas import RechazoRespuesta

ESTADO_RECHAZO_NEGOCIO = 422
registro = logging.getLogger("eventosnova.api")


class RechazoDeNegocio(Exception):
    def __init__(self, detalle: str, pendientes: List[str] | None = None):
        super().__init__(detalle)
        self.detalle, self.pendientes = detalle, list(pendientes or [])


def exigir_exito(resultado: Resultado) -> Resultado:
    """Devuelve el resultado si tuvo éxito; si fue un rechazo, lanza RechazoDeNegocio con su motivo."""
    if not resultado.exito:
        raise RechazoDeNegocio(resultado.mensaje, resultado.pendientes)
    return resultado


def _respuesta(detalle: str, pendientes: List[str]) -> JSONResponse:
    cuerpo = RechazoRespuesta(detalle=detalle, pendientes=pendientes).model_dump()
    return JSONResponse(status_code=ESTADO_RECHAZO_NEGOCIO, content=cuerpo)


def registrar_manejadores(aplicacion: FastAPI) -> None:
    @aplicacion.exception_handler(RechazoDeNegocio)
    async def _rechazo(_: Request, exc: RechazoDeNegocio):
        return _respuesta(exc.detalle, exc.pendientes)

    @aplicacion.exception_handler(ErrorDominio)
    async def _error_dominio(_: Request, exc: ErrorDominio):
        # p. ej. DatosEvento o Importe rechazados por el dominio al convertir la entrada
        return _respuesta(str(exc), [])


def registrar_manejadores_persistencia(aplicacion: FastAPI, violacion, datos, conexion, general, conflicto=None) -> None:
    """Respuestas HTTP específicas para las fallas de la base de datos (no se confunden con rechazos de negocio ni se vuelven un
    500 genérico). Recibe las clases de error de persistencia como argumentos para que este módulo no importe infraestructura:
    solo `main.py`, la raíz de composición, las conoce."""
    def responder(estado: int, tipo: str, detalle: str) -> JSONResponse:
        return JSONResponse(status_code=estado, content=RechazoRespuesta(tipo=tipo, detalle=detalle).model_dump())

    @aplicacion.exception_handler(violacion)
    async def _violacion(_: Request, exc):
        registro.warning("Violación de restricción: %s (tabla %s)", getattr(exc, "restriccion", None), getattr(exc, "tabla", None))
        return responder(409, "conflicto_de_integridad",
                         "La operación entra en conflicto con datos existentes o con una referencia que no existe "
                         "(restricción de integridad de la base de datos).")

    if conflicto is not None:
        @aplicacion.exception_handler(conflicto)
        async def _conflicto(_: Request, exc):
            registro.warning("Conflicto de concurrencia: %s", exc)
            return responder(409, "conflicto_de_concurrencia",
                             "Otra operación modificó estos datos al mismo tiempo; no se aplicó ningún cambio. "
                             "Consulte el estado actual y repita la operación.")

    @aplicacion.exception_handler(datos)
    async def _datos(_: Request, exc):
        registro.warning("Dato no almacenable: %s", exc)
        return responder(422, "dato_no_almacenable", "Un valor no puede almacenarse (fuera de rango o con formato inválido).")

    @aplicacion.exception_handler(conexion)
    async def _conexion(_: Request, exc):
        registro.error("Base de datos no disponible: %s", exc)
        return responder(503, "base_de_datos_no_disponible", "La base de datos no está disponible. Intente de nuevo más tarde.")

    @aplicacion.exception_handler(general)
    async def _general(_: Request, exc):
        registro.error("Error de persistencia: %s", exc)
        return responder(500, "error_de_persistencia", "Error al acceder a la base de datos.")
