"""Reacciones a Domain Events (después del commit). Cada una usa su propia transacción y es idempotente."""
from __future__ import annotations
from datetime import datetime
from domain import eventos_dominio as E
from domain.evento import ServicioContratado
from domain.valores import CondicionesServicio, TipoSolicitud, EstadoSolicitudCambio, EstadoSolicitudServicioAdicional
from .servicios import transaccion, nuevo_id


class ReaccionesEvento:
    """Cambios en Evento provocados por hechos de otros agregados (Detalle D)."""

    def __init__(self, eventos, contratos, uow):
        self.eventos, self.contratos, self.uow = eventos, contratos, uow

    def _con_evento(self, evento_id, accion):
        ev = self.eventos.obtener_por_id(evento_id)
        with transaccion(self.uow, ev):
            accion(ev); self.eventos.guardar(ev)

    def al_confirmarse_contratacion(self, e: E.ContratacionConfirmada):
        c = self.contratos.obtener_por_id(e.agregado_id)
        servicios = [ServicioContratado(f"{c.id}-S{i}", s, None, CondicionesServicio(c.condiciones.condiciones))
                     for i, s in enumerate(c.condiciones.servicios, 1)]
        self._con_evento(e.evento_ref, lambda ev: ev.confirmar_contratacion(servicios))

    def al_cerrarse_proceso_contratacion(self, e: E.ProcesoContratacionCerrado):
        self._con_evento(e.evento_ref, lambda ev: ev.cerrar_sin_contratacion())      # nunca Cancelado

    def al_confirmarse_cambio(self, e: E.CambioConfirmado):
        """Aplica la configuración aprobada (datos y condiciones por servicio) una sola vez. Si el Evento inició
        después de la confirmación, el cambio confirmado se aplica igualmente (BN-006)."""
        self._con_evento(e.evento_ref, lambda ev: ev.aplicar_cambio_confirmado(e.agregado_id, e.datos_propuestos,
                                                                              dict(e.condiciones_propuestas), e.ocurrido_en))

    def al_confirmarse_servicio_adicional(self, e: E.ServicioAdicionalConfirmado):
        """Incorpora el servicio con las condiciones aprobadas por el Cliente y formalizadas en el anexo."""
        sc = ServicioContratado(f"{e.agregado_id}-S", e.servicio, e.proveedor_id, e.condiciones)
        self._con_evento(e.evento_ref, lambda ev: ev.incorporar_servicio_adicional(e.agregado_id, sc, e.ocurrido_en))

    def al_confirmarse_sustitucion(self, e: E.SustitucionProveedorConfirmada):
        self._con_evento(e.evento_ref, lambda ev: ev.reasignar_proveedor(e.agregado_id, e.servicio_contratado_id, e.proveedor_id,
                                                                        e.ocurrido_en))


class ReaccionesSolicitudes:
    def __init__(self, cambios, adicionales, sustituciones, uow, svc_cambios, svc_adicionales, svc_sustitucion,
                 svc_pagos=None):
        self.repos = {TipoSolicitud.CAMBIO.value: cambios, TipoSolicitud.SERVICIO_ADICIONAL.value: adicionales,
                      TipoSolicitud.SUSTITUCION_PROVEEDOR.value: sustituciones}
        self.cambios, self.adicionales, self.sustituciones, self.uow = cambios, adicionales, sustituciones, uow
        self.svc_cambios, self.svc_adicionales, self.svc_sustitucion = svc_cambios, svc_adicionales, svc_sustitucion
        self.svc_pagos = svc_pagos

    def al_registrarse_anexo(self, e: E.AnexoContratoRegistrado):
        repo = self.repos[e.tipo_origen]
        s = repo.obtener_por_id(e.origen_id)
        with transaccion(self.uow, s):
            s.asociar_anexo(e.anexo_id); repo.guardar(s)

    def al_iniciarse_evento(self, e: E.EventoIniciado):
        """Un cierre por raíz y por transacción; un error en uno no revierte el inicio ni los demás."""
        for s in self.cambios.listar_pendientes_por_evento_id(e.agregado_id):
            self.svc_cambios.cerrar_cambio_por_inicio_evento(s.id, e.ocurrido_en)
        for s in self.adicionales.listar_pendientes_por_evento_id(e.agregado_id):
            self.svc_adicionales.cerrar_servicio_adicional_por_inicio_evento(s.id, e.ocurrido_en)
        for s in self.sustituciones.listar_pendientes_por_evento_id(e.agregado_id):
            self.svc_sustitucion.cerrar_sustitucion_por_inicio_evento(s.id, e.ocurrido_en)

    def al_cancelarse_evento(self, e: E.EventoCancelado):
        """BN-008: cada solicitud en trámite (no confirmada) del Evento cancelado se cierra con el motivo «Evento
        cancelado», una transacción por solicitud. Después se aplica SE-012: sus cobros exclusivos quedan sin efecto y,
        por estar cancelado el Evento, no hay devolución. Las solicitudes confirmadas no se tocan."""
        for repo in (self.cambios, self.adicionales, self.sustituciones):
            for s in repo.listar_pendientes_por_evento_id(e.agregado_id):
                with transaccion(self.uow, s):
                    s.cerrar_por_cancelacion_evento(e.ocurrido_en); repo.guardar(s)
                if self.svc_pagos is not None:
                    self.svc_pagos.aplicar_cierre_sin_realizar(s.id, s.estado_cuenta_id, s.evento_id, e.ocurrido_en)

    def al_regularizarse_saldo(self, e: E.SaldoVencidoRegularizado):
        for s in self.cambios.listar_pendientes_por_evento_id(e.evento_ref):
            if s.estado == EstadoSolicitudCambio.DETENIDA_SALDO_VENCIDO:
                self.svc_cambios.retomar_solicitud_cambio(s.id, e.ocurrido_en)
        for s in self.adicionales.listar_pendientes_por_evento_id(e.evento_ref):
            if s.estado == EstadoSolicitudServicioAdicional.DETENIDA_SALDO_VENCIDO:
                self.svc_adicionales.retomar_solicitud_servicio_adicional(s.id, e.ocurrido_en)


class ReaccionesPagos:
    def __init__(self, svc_pagos, svc_contratacion, cambios, adicionales, sustituciones, estados_cuenta):
        self.pagos, self.contratacion = svc_pagos, svc_contratacion
        self.cambios, self.adicionales, self.sustituciones, self.ec = cambios, adicionales, sustituciones, estados_cuenta

    def al_firmarse_contrato(self, e: E.ContratoFirmado):
        self.pagos.registrar_obligacion_anticipo(e.agregado_id)

    def al_confirmarse_contratacion(self, e: E.ContratacionConfirmada):
        self.pagos.registrar_obligacion_saldo_original(e.agregado_id)

    def al_verificarse_pago(self, e: E.PagoVerificado):
        if e.concepto == "Anticipo":
            ec = self.ec.obtener_por_id(e.agregado_id)
            self.contratacion.confirmar_contratacion(ec.contrato_id, e.ocurrido_en)   # idempotente

    def al_cerrarse_sin_realizar(self, e):
        """SE-012 en un solo lugar (H-02)."""
        for repo in (self.cambios, self.adicionales, self.sustituciones):
            s = repo.obtener_por_id(e.agregado_id)
            if s is not None:
                self.pagos.aplicar_cierre_sin_realizar(s.id, s.estado_cuenta_id, s.evento_id, e.ocurrido_en)
                return


class ReaccionesNotificacion:
    """Único punto de notificación de los hechos que no requieren escritura."""

    def __init__(self, notificador):
        self.n = notificador

    def al_aceptarse_propuesta(self, e): self.n.notificar(["Coordinador"], "Propuesta aceptada", "Puede iniciar la formalización del contrato.")
    def al_regularizarse_saldo(self, e):
        """Comunica la regularización; no hay aviso de cancelación (BN-005, CA-027)."""
        self.n.notificar(["Coordinador", "Cliente"], "Saldo regularizado",
                         f"Evento {e.evento_ref}: se retoman la organización y las solicitudes detenidas que cumplan sus condiciones.")

    def al_vencer_plazo_regularizacion(self, e):
        """Solo avisa: la cancelación la registra el Coordinador (BN-005, CA-027)."""
        self.n.notificar(["Coordinador", "Administración"], "Plazo de regularización vencido",
                         f"Evento {e.evento_ref}: registrar la cancelación e indicar el motivo.")

    def al_cancelarse_evento(self, e): self.n.notificar(["Cliente", "Administración", "Proveedores"], "Evento cancelado", f"Origen: {e.origen}. Aplica la política de no reembolso.")
    def al_vencer_saldo(self, e): self.n.notificar(["Coordinador", "Administración"], "Saldo vencido", "Activar el protocolo de cobro.")
    def al_no_disponer_proveedor(self, e): self.n.notificar(["Coordinador"], "Proveedor no disponible", "Buscar alternativa.")
    def al_registrarse_devolucion(self, e): self.n.notificar(["Coordinador"], "Devolución efectuada", "Comunicar el resultado al Cliente.")


def suscribir_reacciones(pub, r_evento, r_solicitudes, r_pagos, r_notif):
    s = pub.suscribir
    s(E.PropuestaAceptada, r_notif.al_aceptarse_propuesta)
    s(E.ContratoFirmado, r_pagos.al_firmarse_contrato)
    s(E.PagoVerificado, r_pagos.al_verificarse_pago)
    s(E.ContratacionConfirmada, r_evento.al_confirmarse_contratacion)
    s(E.ContratacionConfirmada, r_pagos.al_confirmarse_contratacion)
    s(E.ProcesoContratacionCerrado, r_evento.al_cerrarse_proceso_contratacion)
    s(E.AnexoContratoRegistrado, r_solicitudes.al_registrarse_anexo)
    s(E.CambioConfirmado, r_evento.al_confirmarse_cambio)
    s(E.ServicioAdicionalConfirmado, r_evento.al_confirmarse_servicio_adicional)
    s(E.SustitucionProveedorConfirmada, r_evento.al_confirmarse_sustitucion)
    s(E.ProveedorNoDisponible, r_notif.al_no_disponer_proveedor)
    s(E.EventoIniciado, r_solicitudes.al_iniciarse_evento)
    for t in (E.SolicitudCambioCerradaPorInicioEvento, E.ServicioAdicionalCerradoPorInicioEvento,
              E.SustitucionProveedorCerradaPorInicioEvento, E.SolicitudCambioCerradaPorFaltaDePago,
              E.ServicioAdicionalCerradoPorFaltaDePago):
        s(t, r_pagos.al_cerrarse_sin_realizar)
    s(E.SaldoContratoOriginalVencido, r_notif.al_vencer_saldo)
    s(E.SaldoVencidoRegularizado, r_solicitudes.al_regularizarse_saldo)
    s(E.SaldoVencidoRegularizado, r_notif.al_regularizarse_saldo)
    s(E.PlazoRegularizacionVencido, r_notif.al_vencer_plazo_regularizacion)   # sin escritura
    s(E.EventoCancelado, r_solicitudes.al_cancelarse_evento)
    s(E.EventoCancelado, r_notif.al_cancelarse_evento)
    s(E.DevolucionRegistrada, r_notif.al_registrarse_devolucion)
