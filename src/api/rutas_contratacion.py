"""CU-01 (resto) y CU-02: versiones y aceptación de la propuesta, cierre por no aceptación y formalización de la contratación.

Cada ruta llama a un método de `GestionPropuestaService` / `FormalizarContratacionService`; no contiene reglas de negocio."""
from __future__ import annotations
from datetime import datetime
from typing import Callable
from fastapi import APIRouter, Depends, status
from .dependencias import obtener_contenedor, obtener_reloj
from .esquemas import CrearPropuestaEntrada, RechazoRespuesta
from .esquemas_operaciones import (AceptarPropuestaEntrada, CierreNoAceptacionEntrada, FechaEntrada, PrepararContratoEntrada,
                                   SeguimientoAnticipoEntrada)
from .rutas_comunes import OperacionRespuesta, responder

router = APIRouter(tags=["Propuestas y contratación (CU-01, CU-02)"])
_RECHAZO = {422: {"model": RechazoRespuesta, "description": "Rechazo de negocio o entrada no válida"}}


@router.post("/propuestas/{propuesta_id}/versiones", status_code=status.HTTP_201_CREATED, response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Generar una nueva versión de la propuesta")
def generar_nueva_version(propuesta_id: str, entrada: CrearPropuestaEntrada, contenedor=Depends(obtener_contenedor),
                          reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.propuestas.generar_nueva_version(propuesta_id, entrada.a_dominio(), reloj()))


@router.post("/propuestas/{propuesta_id}/aceptacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Aceptar la versión vigente de la propuesta")
def aceptar_propuesta(propuesta_id: str, entrada: AceptarPropuestaEntrada, contenedor=Depends(obtener_contenedor),
                      reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.propuestas.aceptar_propuesta(propuesta_id, entrada.version_id, reloj()))


@router.post("/propuestas/{propuesta_id}/cierre-por-no-aceptacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Cerrar la propuesta por no aceptación del Cliente")
def cerrar_propuesta(propuesta_id: str, entrada: CierreNoAceptacionEntrada, contenedor=Depends(obtener_contenedor),
                     reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.propuestas.cerrar_propuesta_no_aceptada(propuesta_id, entrada.motivo, reloj()))


@router.post("/propuestas/{propuesta_id}/contrato", status_code=status.HTTP_201_CREATED, response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Preparar el contrato de una propuesta aceptada")
def preparar_contrato(propuesta_id: str, entrada: PrepararContratoEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.contratacion.preparar_contrato(propuesta_id, entrada.politica_incluida))


@router.post("/contratos/{contrato_id}/firma", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la firma del contrato")
def registrar_firma(contrato_id: str, entrada: FechaEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.contratacion.registrar_firma_contrato(contrato_id, entrada.fecha))


@router.post("/contratos/{contrato_id}/comunicacion-politica-no-reembolso", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar que se comunicó la política de no reembolso al Cliente")
def comunicar_politica(contrato_id: str, entrada: FechaEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.contratacion.registrar_comunicacion_politica_no_reembolso(contrato_id, entrada.fecha))


@router.post("/contratos/{contrato_id}/confirmacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Confirmar la contratación (firma, política comunicada y anticipo verificado)")
def confirmar_contratacion(contrato_id: str, contenedor=Depends(obtener_contenedor),
                           reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.contratacion.confirmar_contratacion(contrato_id, reloj()))


@router.post("/contratos/{contrato_id}/seguimiento-anticipo", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Dar seguimiento al anticipo pendiente (y cerrar la contratación si procede)")
def seguimiento_anticipo(contrato_id: str, entrada: SeguimientoAnticipoEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.contratacion.dar_seguimiento_anticipo_pendiente(
        contrato_id, entrada.fecha, entrada.resultado_contacto, entrada.sin_pago_tras_seguimiento))
