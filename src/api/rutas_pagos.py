"""CU de gestión financiera: pagos, verificación, vencimiento del saldo, protocolo de cobro, regularización, devoluciones y
solicitudes de pago. Cada ruta llama a `GestionPagosService` / `GestionCierreEventoService`; los importes se validan como `Importe`."""
from __future__ import annotations
from datetime import datetime
from typing import Callable
from typing import Optional
from fastapi import APIRouter, Body, Depends, status
from domain.valores import TipoSolicitud
from .dependencias import obtener_contenedor, obtener_reloj
from .esquemas import RechazoRespuesta
from .esquemas_operaciones import (DevolucionEntrada, ImporteAdicionalSustitucionEntrada, PagoEntrada, ProtocoloCobroEntrada, RegularizacionEntrada,
                                   SolicitudPagoCambioEntrada, SolicitudPagoServicioAdicionalEntrada, VerificacionPagoEntrada, importe)
from .rutas_comunes import OperacionRespuesta, responder

router = APIRouter(tags=["Pagos y gestión financiera"])
_RECHAZO = {422: {"model": RechazoRespuesta, "description": "Rechazo de negocio o entrada no válida"}}


@router.post("/estados-cuenta/{estado_cuenta_id}/pagos", status_code=status.HTTP_201_CREATED, response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Registrar (y verificar) un pago")
def registrar_pago(estado_cuenta_id: str, entrada: PagoEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.pagos.registrar_y_verificar_pago(
        estado_cuenta_id, entrada.obligacion_id, importe(entrada.importe), entrada.fecha, entrada.comprobante,
        entrada.registrado_en, entrada.verificar_ahora))


@router.post("/estados-cuenta/{estado_cuenta_id}/pagos/{pago_id}/verificacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Verificar un pago ya registrado")
def verificar_pago(estado_cuenta_id: str, pago_id: str, entrada: VerificacionPagoEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.pagos.verificar_pago_registrado(estado_cuenta_id, pago_id, entrada.verificado_en))


@router.post("/estados-cuenta/{estado_cuenta_id}/vencimiento-saldo-original", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar el vencimiento del saldo del contrato original")
def vencimiento_saldo(estado_cuenta_id: str, contenedor=Depends(obtener_contenedor),
                      reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.pagos.registrar_vencimiento_saldo_original(estado_cuenta_id, reloj()))


@router.post("/estados-cuenta/{estado_cuenta_id}/protocolo-cobro", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Activar el protocolo de cobro (cargos moratorios)")
def protocolo_cobro(estado_cuenta_id: str, entrada: ProtocoloCobroEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.pagos.activar_protocolo_cobro(
        estado_cuenta_id, importe(entrada.importe_moratorio), entrada.comunicado_en, entrada.seguimiento))


@router.post("/estados-cuenta/{estado_cuenta_id}/regularizacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar el resultado de la regularización del saldo vencido")
def regularizacion(estado_cuenta_id: str, entrada: RegularizacionEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.cierre.resolver_regularizacion_saldo_vencido(estado_cuenta_id, entrada.revisado_en))


@router.post("/estados-cuenta/{estado_cuenta_id}/devoluciones/{devolucion_id}/ejecucion", response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Registrar y ejecutar una devolución pendiente")
def ejecutar_devolucion(estado_cuenta_id: str, devolucion_id: str, entrada: Optional[DevolucionEntrada] = Body(default=None),
                        contenedor=Depends(obtener_contenedor), reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    comprobante = entrada.comprobante if entrada else None
    return responder(contenedor, contenedor.servicios.pagos.registrar_y_ejecutar_devolucion(
        estado_cuenta_id, devolucion_id, reloj(), comprobante))


@router.post("/solicitudes-cambio/{solicitud_id}/solicitud-pago", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Comunicar al Cliente la solicitud de pago de un cambio")
def solicitud_pago_cambio(solicitud_id: str, entrada: SolicitudPagoCambioEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.pagos.comunicar_solicitud_pago_cambio(solicitud_id, entrada.comunicado_en))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/solicitud-pago", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Comunicar al Cliente la solicitud de pago de un servicio adicional")
def solicitud_pago_servicio_adicional(solicitud_id: str, entrada: SolicitudPagoServicioAdicionalEntrada,
                                      contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.pagos.comunicar_solicitud_pago(
        TipoSolicitud.SERVICIO_ADICIONAL, solicitud_id, entrada.concepto, importe(entrada.importe), entrada.comunicado_en))


@router.post("/sustituciones/{sustitucion_id}/importe-adicional", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Integrar el importe adicional de una sustitución al saldo general")
def importe_adicional_sustitucion(sustitucion_id: str, entrada: ImporteAdicionalSustitucionEntrada,
                                  contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.pagos.registrar_importe_adicional_sustitucion(sustitucion_id, importe(entrada.importe)))
