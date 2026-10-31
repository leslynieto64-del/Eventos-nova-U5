"""Piezas comunes de las rutas de la API: respuesta uniforme de las operaciones, conversión de `Resultado` y despacho en línea
de los eventos pendientes del Outbox.

Convención de las rutas de escritura (comandos): llaman a UN servicio de aplicación con la entrada validada, devuelven
`OperacionRespuesta` si tuvo éxito y, si el servicio rechazó la operación por una regla de negocio, HTTP 422 con el motivo
(`RechazoRespuesta`), igual que las rutas anteriores. `ahora` lo entrega el reloj inyectado (`obtener_reloj`); las fechas que son
HECHOS del negocio (fecha de pago, de firma, de comunicación...) las informa quien llama en el cuerpo.

Despacho en línea: tras un comando exitoso se despachan los eventos pendientes para que las reacciones (p. ej. crear el estado de
cuenta al firmar) ocurran sin esperar a un trabajador externo. Si el despacho falla, el comando YA está confirmado: el error se
registra y los eventos quedan en el Outbox para el trabajador o para el siguiente despacho. Se desactiva con
EVENTOSNOVA_DESPACHO_EN_LINEA=0 (cuando solo se usa el trabajador)."""
from __future__ import annotations
import logging
import os
from typing import Any, Dict
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from application.resultados import Resultado
from .errores import exigir_exito

registro = logging.getLogger("eventosnova.api")


class OperacionRespuesta(BaseModel):
    """Éxito de una operación: mensaje del servicio y los datos que devuelve (identificadores, números...)."""
    mensaje: str
    datos: Dict[str, Any] = Field(default_factory=dict)


def despachar_pendientes(contenedor) -> None:
    if os.environ.get("EVENTOSNOVA_DESPACHO_EN_LINEA", "1") == "0":
        return
    try:
        contenedor.despachador.despachar()
    except Exception:                                    # el comando ya se confirmó; los eventos siguen en el Outbox
        registro.exception("No se pudo despachar el Outbox tras la operación; quedan eventos pendientes")


def responder(contenedor, resultado: Resultado, despachar: bool = True) -> OperacionRespuesta:
    """Convierte el `Resultado` de un servicio: rechazo → 422 (RechazoDeNegocio); éxito → despacho en línea y respuesta.
    Las consultas (sin efectos) usan `despachar=False`."""
    exigir_exito(resultado)
    if despachar:
        despachar_pendientes(contenedor)
    return OperacionRespuesta(mensaje=resultado.mensaje, datos=jsonable_encoder(resultado.datos))
