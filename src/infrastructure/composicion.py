"""Raíz de composición: conecta interfaces con implementaciones.

`construir()` usa repositorios en memoria (desarrollo y pruebas unitarias). `ensamblar()` contiene el cableado común de servicios,
reacciones, consultas y comandos; la composición persistente (`infrastructure.persistencia.composicion_persistente`) lo reutiliza
con repositorios SQL, así ambas composiciones exponen exactamente la misma estructura."""
from __future__ import annotations
from types import SimpleNamespace
from application.seguridad import ServicioSeguridad
from application import servicios as S, reacciones as R, cqrs as Q
from .repositorios_memoria import (PropuestaRepositoryMemoria, ContratoRepositoryMemoria, EventoRepositoryMemoria,
                                   SolicitudCambioRepositoryMemoria, SolicitudServicioAdicionalRepositoryMemoria,
                                   SustitucionProveedorRepositoryMemoria, EstadoCuentaRepositoryMemoria,
                                   ProveedorRepositoryMemoria)
from .seguridad_memoria import AlmacenSeguridadMemoria
from .unidad_trabajo import UnitOfWorkMemoria, PublicadorEnProceso, DespachadorOutbox
from .adaptadores import (ConsultaDisponibilidadSimulada, ConsultaDisponibilidadDesdeCatalogo, ConsultaDisponibilidadCombinada, NotificadorEnMemoria, VerificadorPagosSimulado,
                          EjecutorDevolucionesSimulado)


def construir(disponibilidad=None):
    uow = UnitOfWorkMemoria()
    r = SimpleNamespace(
        propuestas=PropuestaRepositoryMemoria(uow), contratos=ContratoRepositoryMemoria(uow),
        eventos=EventoRepositoryMemoria(uow), cambios=SolicitudCambioRepositoryMemoria(uow),
        adicionales=SolicitudServicioAdicionalRepositoryMemoria(uow),
        sustituciones=SustitucionProveedorRepositoryMemoria(uow), estados_cuenta=EstadoCuentaRepositoryMemoria(uow),
        proveedores=ProveedorRepositoryMemoria())
    pub = PublicadorEnProceso()
    return ensamblar(r, uow, pub, DespachadorOutbox(uow, pub), disponibilidad, AlmacenSeguridadMemoria())


def ensamblar(r, uow, pub, despachador, disponibilidad=None, almacen_seguridad=None):
    """Cablea servicios, reacciones, consultas y comandos sobre los repositorios `r`, la unidad de trabajo y el publicador dados."""
    disp = disponibilidad or ConsultaDisponibilidadSimulada()
    notif, verif, ejec = NotificadorEnMemoria(), VerificadorPagosSimulado(), EjecutorDevolucionesSimulado()
    svc = SimpleNamespace(
        propuestas=S.GestionPropuestaService(r.propuestas, r.eventos, uow),
        contratacion=S.FormalizarContratacionService(r.contratos, r.propuestas, r.estados_cuenta, uow, r.eventos),
        pagos=S.GestionPagosService(r.estados_cuenta, r.contratos, r.eventos, r.cambios, r.adicionales, r.sustituciones,
                                    uow, verif, ejec, notif),
        cierre=S.GestionCierreEventoService(r.eventos, r.contratos, r.estados_cuenta, uow, notif),
        cambios=S.GestionCambiosEventoService(r.cambios, r.eventos, r.contratos, r.estados_cuenta, uow, disp, notif),
        adicionales=S.GestionServiciosAdicionalesService(r.adicionales, r.eventos, r.contratos, r.estados_cuenta, uow, disp, notif),
        sustitucion=S.GestionSustitucionProveedorService(r.sustituciones, r.eventos, r.contratos, r.estados_cuenta, uow, disp, notif),
        # Asignación inicial: candidatos del catálogo registrado (sin costo; decisión D-P2) y de la fuente inyectada explícitamente. La fuente
        # de demostración cargada del entorno (PV-DEMO-*) NO participa: solo proveedores registrados pueden asignarse.
        proveedores=S.GestionProveedoresServicioService(
            r.eventos, uow, ConsultaDisponibilidadDesdeCatalogo(r.proveedores) if getattr(disp, "solo_demostracion", False)
            else ConsultaDisponibilidadCombinada(disp, ConsultaDisponibilidadDesdeCatalogo(r.proveedores)), notif, r.proveedores),
        catalogo=S.GestionCatalogoProveedoresService(r.proveedores),
        seguridad=ServicioSeguridad(almacen_seguridad, catalogo=r.proveedores) if almacen_seguridad is not None else None,
    )
    R.suscribir_reacciones(
        pub,
        R.ReaccionesEvento(r.eventos, r.contratos, uow),
        R.ReaccionesSolicitudes(r.cambios, r.adicionales, r.sustituciones, uow, svc.cambios, svc.adicionales, svc.sustitucion,
                                svc.pagos),
        R.ReaccionesPagos(svc.pagos, svc.contratacion, r.cambios, r.adicionales, r.sustituciones, r.estados_cuenta),
        R.ReaccionesNotificacion(notif))
    queries = SimpleNamespace(
        estado_pagos=Q.ConsultarEstadoPagosHandler(r.estados_cuenta),
        pendientes=Q.ConsultarSolicitudesPendientesHandler(r.cambios, r.adicionales, r.sustituciones, r.estados_cuenta),
        servicio_asignado=Q.ConsultarServicioAsignadoHandler(r.eventos),
        info_administrativa=Q.ConsultarInformacionAdministrativaEventoHandler(
            r.eventos, r.contratos, r.estados_cuenta, r.cambios, r.adicionales, r.sustituciones, r.proveedores),
        eventos_proximos=Q.ConsultarEventosProximosHandler(r.eventos),
        solicitudes_por_estado=Q.ConsultarSolicitudesPorEstadoHandler(r.cambios, r.adicionales, r.sustituciones),
        pagos_pendientes=Q.ConsultarPagosPendientesHandler(r.estados_cuenta),
        devoluciones_pendientes=Q.ConsultarDevolucionesPendientesHandler(r.estados_cuenta),
        servicios_pendientes=Q.ConsultarServiciosPendientesConfirmacionHandler(
            r.eventos, r.cambios, r.adicionales, r.sustituciones, r.proveedores))
    commands = SimpleNamespace(
        nueva_version=Q.GenerarNuevaVersionPropuestaHandler(svc.propuestas),
        confirmar_cambio=Q.ConfirmarCambioHandler(svc.cambios),
        seguimiento_anticipo=Q.DarSeguimientoAnticipoPendienteHandler(svc.contratacion),
        cancelar_por_falta_de_regularizacion=Q.RegistrarCancelacionPorFaltaDeRegularizacionHandler(svc.cierre))
    return SimpleNamespace(repos=r, servicios=svc, uow=uow, despachador=despachador,
                           notificador=notif, queries=queries, commands=commands)
