"""Raíz de composición: conecta interfaces con implementaciones en memoria."""
from __future__ import annotations
from types import SimpleNamespace
from application import servicios as S, reacciones as R, cqrs as Q
from .repositorios_memoria import (PropuestaRepositoryMemoria, ContratoRepositoryMemoria, EventoRepositoryMemoria,
                                   SolicitudCambioRepositoryMemoria, SolicitudServicioAdicionalRepositoryMemoria,
                                   SustitucionProveedorRepositoryMemoria, EstadoCuentaRepositoryMemoria)
from .unidad_trabajo import UnitOfWorkMemoria, PublicadorEnProceso, DespachadorOutbox
from .adaptadores import (ConsultaDisponibilidadSimulada, NotificadorEnMemoria, VerificadorPagosSimulado,
                          EjecutorDevolucionesSimulado)


def construir(disponibilidad=None):
    uow = UnitOfWorkMemoria()
    r = SimpleNamespace(
        propuestas=PropuestaRepositoryMemoria(uow), contratos=ContratoRepositoryMemoria(uow),
        eventos=EventoRepositoryMemoria(uow), cambios=SolicitudCambioRepositoryMemoria(uow),
        adicionales=SolicitudServicioAdicionalRepositoryMemoria(uow),
        sustituciones=SustitucionProveedorRepositoryMemoria(uow), estados_cuenta=EstadoCuentaRepositoryMemoria(uow))
    disp = disponibilidad or ConsultaDisponibilidadSimulada()
    notif, verif, ejec = NotificadorEnMemoria(), VerificadorPagosSimulado(), EjecutorDevolucionesSimulado()
    svc = SimpleNamespace(
        propuestas=S.GestionPropuestaService(r.propuestas, r.eventos, uow),
        contratacion=S.FormalizarContratacionService(r.contratos, r.propuestas, r.estados_cuenta, uow),
        pagos=S.GestionPagosService(r.estados_cuenta, r.contratos, r.eventos, r.cambios, r.adicionales, r.sustituciones,
                                    uow, verif, ejec, notif),
        cierre=S.GestionCierreEventoService(r.eventos, r.contratos, r.estados_cuenta, uow, notif),
        cambios=S.GestionCambiosEventoService(r.cambios, r.eventos, r.contratos, r.estados_cuenta, uow, disp, notif),
        adicionales=S.GestionServiciosAdicionalesService(r.adicionales, r.eventos, r.contratos, r.estados_cuenta, uow, disp, notif),
        sustitucion=S.GestionSustitucionProveedorService(r.sustituciones, r.eventos, r.contratos, r.estados_cuenta, uow, disp, notif),
    )
    pub = PublicadorEnProceso()
    R.suscribir_reacciones(
        pub,
        R.ReaccionesEvento(r.eventos, r.contratos, uow),
        R.ReaccionesSolicitudes(r.cambios, r.adicionales, r.sustituciones, uow, svc.cambios, svc.adicionales, svc.sustitucion,
                                svc.pagos),
        R.ReaccionesPagos(svc.pagos, svc.contratacion, r.cambios, r.adicionales, r.sustituciones, r.estados_cuenta),
        R.ReaccionesNotificacion(notif))
    queries = SimpleNamespace(
        estado_pagos=Q.ConsultarEstadoPagosHandler(r.estados_cuenta),
        pendientes=Q.ConsultarSolicitudesPendientesHandler(r.cambios, r.adicionales, r.sustituciones, r.estados_cuenta))
    commands = SimpleNamespace(
        nueva_version=Q.GenerarNuevaVersionPropuestaHandler(svc.propuestas),
        confirmar_cambio=Q.ConfirmarCambioHandler(svc.cambios),
        seguimiento_anticipo=Q.DarSeguimientoAnticipoPendienteHandler(svc.contratacion),
        cancelar_por_falta_de_regularizacion=Q.RegistrarCancelacionPorFaltaDeRegularizacionHandler(svc.cierre))
    return SimpleNamespace(repos=r, servicios=svc, uow=uow, despachador=DespachadorOutbox(uow, pub),
                           notificador=notif, queries=queries, commands=commands)
