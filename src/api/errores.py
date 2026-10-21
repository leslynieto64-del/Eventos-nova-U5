"""Conversión de rechazos de negocio a respuestas HTTP.

Solo se convierten los rechazos de negocio (Resultado.rechazo y ErrorDominio) en HTTP 422 con el motivo
original. Cualquier otra excepción es una falla técnica: no se captura y FastAPI responde 500."""
from __future__ import annotations
from typing import List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from application.resultados import Resultado
from domain.valores import ErrorDominio
from .esquemas import RechazoRespuesta

ESTADO_RECHAZO_NEGOCIO = 422


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
