"""Solicitudes del Cliente: cambios, servicios adicionales y sustitución de proveedor. Cada ruta llama a un método de
`GestionCambiosEventoService`, `GestionServiciosAdicionalesService` o `GestionSustitucionProveedorService`; las reglas
(plazos, aprobaciones, autorizaciones, anexos, pagos) viven en el dominio y en esos servicios, no aquí.

El pago de cada solicitud se comunica con las rutas de `rutas_pagos` (`.../solicitud-pago`)."""
from __future__ import annotations
from datetime import datetime
from typing import Callable
from fastapi import APIRouter, Depends, status
from domain.valores import CondicionesServicio
from .dependencias import obtener_contenedor, obtener_reloj
from .esquemas import RechazoRespuesta
from .esquemas_operaciones import (AlternativaEntrada, AnexoEntrada, DecisionEntrada, DecisionEsperaEntrada, DisponibilidadEntrada,
                                   SolicitudCambioEntrada, SolicitudServicioAdicionalEntrada, SustitucionEntrada, ViabilidadEntrada, importe)
from .rutas_comunes import OperacionRespuesta, responder

router = APIRouter(tags=["Solicitudes: cambios, servicios adicionales y sustituciones"])
_RECHAZO = {422: {"model": RechazoRespuesta, "description": "Rechazo de negocio o entrada no válida"}}
Reloj = Callable[[], datetime]


# ---------------------------------------------------------------- cambios
@router.post("/solicitudes-cambio", status_code=status.HTTP_201_CREATED, response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar una solicitud de cambio")
def registrar_cambio(entrada: SolicitudCambioEntrada, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    datos = entrada.datos_propuestos.a_dominio() if entrada.datos_propuestos else None
    condiciones = ({k: CondicionesServicio(v) for k, v in entrada.condiciones_propuestas.items()}
                   if entrada.condiciones_propuestas else None)
    return responder(contenedor, contenedor.servicios.cambios.registrar_solicitud_cambio(
        entrada.evento_id, entrada.contrato_id, entrada.descripcion, importe(entrada.tarifa_vigente), reloj(), datos, condiciones))


@router.post("/solicitudes-cambio/{solicitud_id}/viabilidad", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la evaluación de viabilidad de un cambio")
def viabilidad_cambio(solicitud_id: str, entrada: ViabilidadEntrada, contenedor=Depends(obtener_contenedor),
                      reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.cambios.evaluar_viabilidad_cambio(
        solicitud_id, entrada.resultado(), importe(entrada.costo_adicional_proveedor), reloj()))


@router.post("/solicitudes-cambio/{solicitud_id}/decision-cliente", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la decisión del Cliente sobre un cambio")
def decision_cliente_cambio(solicitud_id: str, entrada: DecisionEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.cambios.registrar_decision_cliente_cambio(solicitud_id, entrada.a_dominio()))


@router.post("/solicitudes-cambio/{solicitud_id}/autorizacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la autorización de Administración sobre un cambio")
def autorizacion_cambio(solicitud_id: str, entrada: DecisionEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.cambios.registrar_autorizacion_administracion_cambio(solicitud_id, entrada.a_dominio()))


@router.post("/solicitudes-cambio/{solicitud_id}/anexo", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar el anexo del contrato para un cambio")
def anexo_cambio(solicitud_id: str, entrada: AnexoEntrada, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.cambios.registrar_anexo_cambio(solicitud_id, entrada.descripcion, reloj()))


@router.post("/solicitudes-cambio/{solicitud_id}/confirmacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Confirmar un cambio")
def confirmar_cambio(solicitud_id: str, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.cambios.confirmar_cambio(solicitud_id, reloj()))


@router.post("/solicitudes-cambio/{solicitud_id}/cierre-por-falta-de-pago", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Cerrar un cambio por falta de pago")
def cerrar_cambio_falta_pago(solicitud_id: str, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.cambios.cerrar_cambio_por_falta_de_pago(solicitud_id, reloj()))


# ---------------------------------------------------------------- servicios adicionales
@router.post("/solicitudes-servicio-adicional", status_code=status.HTTP_201_CREATED, response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Registrar una solicitud de servicio adicional")
def registrar_servicio_adicional(entrada: SolicitudServicioAdicionalEntrada, contenedor=Depends(obtener_contenedor),
                                 reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.adicionales.registrar_solicitud_servicio_adicional(
        entrada.evento_id, entrada.contrato_id, entrada.servicio, reloj()))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/disponibilidad", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Evaluar la disponibilidad de proveedores para un servicio adicional")
def disponibilidad_servicio_adicional(solicitud_id: str, entrada: DisponibilidadEntrada, contenedor=Depends(obtener_contenedor),
                                      reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.adicionales.evaluar_disponibilidad_servicio_adicional(
        solicitud_id, entrada.proveedores_actuales, reloj()))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/decision-espera", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar si el Cliente acepta esperar la búsqueda de proveedor")
def decision_espera(solicitud_id: str, entrada: DecisionEsperaEntrada, contenedor=Depends(obtener_contenedor),
                    reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.adicionales.registrar_decision_espera_cliente(
        solicitud_id, entrada.acepta_esperar, reloj()))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/aprobacion-cliente", response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Registrar la aprobación o rechazo del Cliente")
def aprobacion_cliente_servicio_adicional(solicitud_id: str, entrada: DecisionEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.adicionales.registrar_aprobacion_cliente_servicio_adicional(
        solicitud_id, entrada.a_dominio()))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/autorizacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la autorización de Administración")
def autorizacion_servicio_adicional(solicitud_id: str, entrada: DecisionEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.adicionales.registrar_autorizacion_administracion_servicio_adicional(
        solicitud_id, entrada.a_dominio()))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/anexo", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar el anexo del contrato para un servicio adicional")
def anexo_servicio_adicional(solicitud_id: str, entrada: AnexoEntrada, contenedor=Depends(obtener_contenedor),
                             reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.adicionales.registrar_anexo_servicio_adicional(solicitud_id, entrada.descripcion, reloj()))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/confirmacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Confirmar un servicio adicional")
def confirmar_servicio_adicional(solicitud_id: str, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.adicionales.confirmar_servicio_adicional(solicitud_id, reloj()))


@router.post("/solicitudes-servicio-adicional/{solicitud_id}/cierre-por-falta-de-pago", response_model=OperacionRespuesta,
             responses=_RECHAZO, summary="Cerrar un servicio adicional por falta de pago")
def cerrar_servicio_adicional_falta_pago(solicitud_id: str, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.adicionales.cerrar_servicio_adicional_por_falta_de_pago(solicitud_id, reloj()))


# ---------------------------------------------------------------- sustitución de proveedor
@router.post("/sustituciones", status_code=status.HTTP_201_CREATED, response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar que el proveedor de un servicio no está disponible (inicia la sustitución)")
def registrar_sustitucion(entrada: SustitucionEntrada, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.sustitucion.registrar_proveedor_no_disponible(
        entrada.evento_id, entrada.servicio_contratado_id, entrada.contrato_id, reloj()))


@router.post("/sustituciones/{sustitucion_id}/alternativa", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Buscar una alternativa de proveedor")
def alternativa_sustitucion(sustitucion_id: str, entrada: AlternativaEntrada, contenedor=Depends(obtener_contenedor),
                            reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.sustitucion.buscar_alternativa_sustitucion(
        sustitucion_id, entrada.condiciones(), importe(entrada.costo_adicional), reloj()))


@router.post("/sustituciones/{sustitucion_id}/decision-cliente", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la decisión del Cliente sobre la alternativa")
def decision_cliente_sustitucion(sustitucion_id: str, entrada: DecisionEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.sustitucion.registrar_decision_cliente_sustitucion(sustitucion_id, entrada.a_dominio()))


@router.post("/sustituciones/{sustitucion_id}/autorizacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar la autorización de Administración sobre la alternativa")
def autorizacion_sustitucion(sustitucion_id: str, entrada: DecisionEntrada, contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.sustitucion.registrar_autorizacion_administracion_sustitucion(
        sustitucion_id, entrada.a_dominio()))


@router.post("/sustituciones/{sustitucion_id}/anexo", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar el anexo del contrato para una sustitución")
def anexo_sustitucion(sustitucion_id: str, entrada: AnexoEntrada, contenedor=Depends(obtener_contenedor),
                      reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.sustitucion.registrar_anexo_sustitucion_proveedor(
        sustitucion_id, entrada.descripcion, reloj()))


@router.post("/sustituciones/{sustitucion_id}/confirmacion", response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Confirmar una sustitución de proveedor")
def confirmar_sustitucion(sustitucion_id: str, contenedor=Depends(obtener_contenedor), reloj: Reloj = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.sustitucion.confirmar_sustitucion_proveedor(sustitucion_id, reloj()))
