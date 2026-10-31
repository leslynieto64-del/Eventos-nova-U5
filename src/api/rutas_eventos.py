"""Ciclo de vida del Evento (inicio, finalización, cancelación, revisión administrativa) y gestión de los proveedores de sus
servicios contratados. Cada ruta llama a `GestionCierreEventoService` / `GestionProveedoresServicioService`."""
from __future__ import annotations
from datetime import datetime
from typing import Callable, Optional
from fastapi import APIRouter, Depends
from application.cqrs import RegistrarCancelacionPorFaltaDeRegularizacionCommand
from .dependencias import obtener_contenedor, obtener_reloj
from .esquemas import RechazoRespuesta
from .esquemas_operaciones import (AsignarProveedorEntrada, CancelacionEntrada, CancelacionFaltaRegularizacionEntrada, FechaEntrada,
                                   RespuestaProveedorEntrada, RevisionAdministrativaEntrada)
from .rutas_comunes import OperacionRespuesta, responder
from .seguridad import ContextoSeguridad, contexto_actual
from application.seguridad import ErrorSeguridad

router = APIRouter(tags=["Ciclo de vida del Evento y proveedores"])
_RECHAZO = {422: {"model": RechazoRespuesta, "description": "Rechazo de negocio o entrada no válida"}}


@router.post("/eventos/{evento_id}/inicio", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Registrar el inicio del evento")
def iniciar_evento(evento_id: str, contenedor=Depends(obtener_contenedor), reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.cierre.procesar_inicio_evento(evento_id, reloj()))


@router.post("/eventos/{evento_id}/finalizacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la finalización del evento")
def finalizar_evento(evento_id: str, entrada: FechaEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.cierre.finalizar_evento(evento_id, entrada.fecha))


@router.post("/eventos/{evento_id}/cancelacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Gestionar la cancelación solicitada por el Cliente")
def cancelar_evento(evento_id: str, entrada: CancelacionEntrada, contenedor=Depends(obtener_contenedor),
                    reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.cierre.gestionar_cancelacion_solicitada(evento_id, entrada.motivo, reloj()))


@router.post("/eventos/{evento_id}/cancelacion-por-falta-de-regularizacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la cancelación por falta de regularización del saldo (registro formal del Coordinador)")
def cancelar_por_falta_de_regularizacion(evento_id: str, entrada: CancelacionFaltaRegularizacionEntrada,
                                         contenedor=Depends(obtener_contenedor)):
    comando = RegistrarCancelacionPorFaltaDeRegularizacionCommand(evento_id, entrada.motivo, entrada.coordinador, entrada.fecha)
    return responder(contenedor, contenedor.commands.cancelar_por_falta_de_regularizacion.handle(comando))


@router.post("/eventos/{evento_id}/revision-administrativa", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la revisión administrativa de un evento cancelado")
def revision_administrativa(evento_id: str, entrada: RevisionAdministrativaEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.cierre.registrar_revision_administrativa_cancelacion(
        evento_id, entrada.resultado, entrada.fecha))


@router.get("/eventos/{evento_id}/servicios/{servicio_contratado_id}/disponibilidad", response_model=OperacionRespuesta,
            responses=_RECHAZO, summary="Consultar la disponibilidad de proveedores de un servicio contratado")
def consultar_disponibilidad(evento_id: str, servicio_contratado_id: str, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.proveedores.consultar_disponibilidad_servicio(evento_id, servicio_contratado_id),
                     despachar=False)


@router.post("/eventos/{evento_id}/servicios/{servicio_contratado_id}/proveedor", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Asignar un proveedor a un servicio contratado")
def asignar_proveedor(evento_id: str, servicio_contratado_id: str, entrada: AsignarProveedorEntrada,
                      contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.proveedores.asignar_proveedor(evento_id, servicio_contratado_id, entrada.proveedor_id))


@router.post("/eventos/{evento_id}/servicios/{servicio_contratado_id}/respuesta-proveedor", response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Registrar la respuesta del proveedor sobre su disponibilidad")
def respuesta_proveedor(evento_id: str, servicio_contratado_id: str, entrada: RespuestaProveedorEntrada,
                        contexto: Optional[ContextoSeguridad] = Depends(contexto_actual),
                        contenedor=Depends(obtener_contenedor)):
    # Un proveedor solo responde por SÍ mismo: se compara con el proveedor vinculado a su cuenta, no con un dato libre del cliente.
    if contexto is not None and contexto.es_proveedor and entrada.proveedor_id != contexto.usuario.proveedor_id:
        raise ErrorSeguridad(403, "sin_permiso", "Solo puede registrar la respuesta de su propio proveedor.")
    return responder(contenedor, contenedor.servicios.proveedores.registrar_respuesta_proveedor(
        evento_id, servicio_contratado_id, entrada.proveedor_id, entrada.disponible))
