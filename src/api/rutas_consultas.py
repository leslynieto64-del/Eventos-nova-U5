"""Consultas (CQRS, solo lectura): cada ruta GET llama a un *Query Handler* de `application.cqrs`, que no usa la unidad de trabajo
ni cambia estados. Si el handler no encuentra el recurso (o, para el Proveedor, no tiene servicios asignados en él, BN-007) la
respuesta es 404 con `tipo = "no_encontrado"`."""
from __future__ import annotations
from datetime import datetime
from typing import Callable, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from application.cqrs import (ConsultarDevolucionesPendientesQuery, ConsultarEstadoPagosQuery, ConsultarEventosProximosQuery,
                              ConsultarInformacionAdministrativaEventoQuery, ConsultarPagosPendientesQuery,
                              ConsultarServicioAsignadoQuery, ConsultarServiciosPendientesConfirmacionQuery,
                              ConsultarSolicitudesPendientesQuery, ConsultarSolicitudesPorEstadoQuery)
from pydantic import NaiveDatetime
from .dependencias import obtener_contenedor, obtener_reloj
from .esquemas import EstadoPagosRespuesta, RechazoRespuesta

router = APIRouter(tags=["Consultas (solo lectura)"])
_NO_ENCONTRADO = {404: {"model": RechazoRespuesta, "description": "Recurso no encontrado"},
                  422: {"model": RechazoRespuesta, "description": "Parámetros no válidos"}}


def _no_encontrado(detalle: str) -> JSONResponse:
    return JSONResponse(status_code=404, content=RechazoRespuesta(tipo="no_encontrado", detalle=detalle).model_dump())


@router.get("/eventos", responses=_NO_ENCONTRADO, summary="Eventos cuya fecha cae en una ventana [desde, hasta]")
def eventos_proximos(desde: NaiveDatetime, hasta: NaiveDatetime, contenedor=Depends(obtener_contenedor)):
    return contenedor.queries.eventos_proximos.handle(ConsultarEventosProximosQuery(desde, hasta))


@router.get("/eventos/{evento_id}/administracion", responses=_NO_ENCONTRADO,
            summary="Información administrativa del evento (contratos, pagos, proveedores y solicitudes)")
def informacion_administrativa(evento_id: str, contenedor=Depends(obtener_contenedor)):
    vm = contenedor.queries.info_administrativa.handle(ConsultarInformacionAdministrativaEventoQuery(evento_id))
    return vm if vm is not None else _no_encontrado("El evento no existe.")


@router.get("/eventos/{evento_id}/pagos", response_model=EstadoPagosRespuesta, response_model_exclude_unset=True, responses=_NO_ENCONTRADO, summary="Estado de los pagos del evento")
def estado_pagos(evento_id: str, contenedor=Depends(obtener_contenedor), reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return contenedor.queries.estado_pagos.handle(ConsultarEstadoPagosQuery(evento_id, reloj()))


@router.get("/eventos/{evento_id}/solicitudes-pendientes", responses=_NO_ENCONTRADO, summary="Solicitudes pendientes del evento")
def solicitudes_pendientes(evento_id: str, contenedor=Depends(obtener_contenedor)):
    return contenedor.queries.pendientes.handle(ConsultarSolicitudesPendientesQuery(evento_id))


@router.get("/proveedores/{proveedor_id}/eventos/{evento_id}", responses=_NO_ENCONTRADO,
            summary="Servicios que un proveedor tiene asignados en un evento")
def servicio_asignado(proveedor_id: str, evento_id: str, contenedor=Depends(obtener_contenedor)):
    vm = contenedor.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery(proveedor_id, evento_id))
    return vm if vm is not None else _no_encontrado("El proveedor no tiene servicios asignados en ese evento.")


@router.get("/solicitudes", responses=_NO_ENCONTRADO, summary="Solicitudes filtradas por estado, evento y tipo")
def solicitudes_por_estado(estado: Optional[str] = None, evento_id: Optional[str] = None, tipo: Optional[str] = None,
                           contenedor=Depends(obtener_contenedor)):
    return contenedor.queries.solicitudes_por_estado.handle(ConsultarSolicitudesPorEstadoQuery(estado, evento_id, tipo))


@router.get("/pagos-pendientes", responses=_NO_ENCONTRADO, summary="Obligaciones Pendientes o Vencidas")
def pagos_pendientes(evento_id: Optional[str] = Query(default=None), contenedor=Depends(obtener_contenedor)):
    return contenedor.queries.pagos_pendientes.handle(ConsultarPagosPendientesQuery(evento_id))


@router.get("/devoluciones-pendientes", responses=_NO_ENCONTRADO, summary="Devoluciones pendientes con su fecha límite")
def devoluciones_pendientes(evento_id: Optional[str] = Query(default=None), contenedor=Depends(obtener_contenedor),
                            reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return contenedor.queries.devoluciones_pendientes.handle(ConsultarDevolucionesPendientesQuery(reloj(), evento_id))


@router.get("/servicios-pendientes-confirmacion", responses=_NO_ENCONTRADO,
            summary="Servicios y solicitudes pendientes de confirmación")
def servicios_pendientes(evento_id: Optional[str] = Query(default=None), contenedor=Depends(obtener_contenedor)):
    return contenedor.queries.servicios_pendientes.handle(ConsultarServiciosPendientesConfirmacionQuery(evento_id))
