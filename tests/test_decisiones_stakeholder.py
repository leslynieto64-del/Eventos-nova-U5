"""Pruebas de las decisiones del stakeholder que cerraron pendientes del negocio (P-04, P-06, P-08, cierre de las
solicitudes en trámite al cancelarse el Evento, operación confirmada que no se aplicó antes de la cancelación y alcance
del cambio de fecha). Solo comprueban comportamientos definidos en el BRD y los criterios de aceptación."""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, FECHA_EVENTO              # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada  # noqa: E402
from domain.evento import ServicioContratado                            # noqa: E402
from domain.valores import (Importe, Decision, DatosEvento, DisponibilidadProveedor, CondicionesServicio,  # noqa: E402
                            ResultadoViabilidad, ConceptoPago, TipoSolicitud, EstadoEvento, ErrorDominio,
                            EstadoObligacionPago as EO, EstadoSolicitudCambio as ESC,
                            EstadoSolicitudServicioAdicional as ESA, EstadoSustitucionProveedor as ESP)


class CancelacionPorSaldoAntesDelInicio(unittest.TestCase):
    def test_despues_del_inicio_no_se_registra_y_el_adeudo_se_conserva(self):   # BN-005, BN-008, CA-027 (P-08, P-04)
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, e.comunicacion + timedelta(hours=25)); e.d.despachar()
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        r = e.s.cierre.registrar_cancelacion_por_falta_de_regularizacion(e.evento_id, 'Registro tardío', 'Coordinador',
                                                                          FECHA_EVENTO + timedelta(hours=1))
        self.assertFalse(r.exito)                                               # la cancelación solo procede antes del inicio
        self.assertEqual(e.evento().estado, EstadoEvento.EN_EJECUCION)
        self.assertEqual(e.obligacion('SaldoContratoOriginal').estado, EO.VENCIDA)   # el adeudo sigue registrado
        self.assertEqual(e.obligacion('CargosMoratorios').estado, EO.PENDIENTE)


class SolicitudEnTramiteConEventoCancelado(unittest.TestCase):
    def test_no_se_confirma_un_cambio_si_el_evento_fue_cancelado(self):        # SE-006, SE-007 (P-06)
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Ajuste', Importe(D(1)), dia).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), None, dia)
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo', dia); e.d.despachar()
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia)
        r = e.s.cambios.confirmar_cambio(sid, dia + timedelta(hours=1))         # antes de procesar las reacciones
        self.assertFalse(r.exito)
        e.d.despachar()
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sid).estado, ESC.CERRADA_EVENTO_CANCELADO)
        self.assertEqual([x for x in e.app.uow.outbox if x.estado == 'Revisión'], [])

    def test_no_se_confirma_un_servicio_adicional_si_el_evento_fue_cancelado(self):   # SE-006, SE-007 (P-06)
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia).datos['obligacion_id']
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + timedelta(hours=1), 'C-DJ'); e.d.despachar()
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia + timedelta(hours=2))
        self.assertFalse(s.confirmar_servicio_adicional(sa, dia + timedelta(hours=3)).exito)   # antes de las reacciones
        e.d.despachar()
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.CERRADA_EVENTO_CANCELADO)
        self.assertNotIn('DJ', [x.servicio for x in e.evento().servicios.values()])
        self.assertEqual(e.ec().devoluciones, [])                              # Evento cancelado: no reembolso (SE-012)


class CierrePorCancelacionDelEvento(unittest.TestCase):
    """BN-008: al cancelarse el Evento, toda solicitud EN TRÁMITE se cierra con el motivo «Evento cancelado»; una
    solicitud ya CONFIRMADA no se cierra por esta regla."""

    def test_solicitudes_en_tramite_se_cierran_con_motivo_evento_cancelado(self):   # BN-008, SE-012, CA-087
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Ajuste', Importe(D(1)), dia).datos['solicitud_id']
        s = e.s.adicionales
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia)
        sc_id = next(iter(e.evento().servicios))
        sp = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, sc_id, e.contrato_id, dia).datos['sustitucion_id']
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia + timedelta(hours=1)); e.d.despachar()
        for repo, sid, estado in ((e.app.repos.cambios, sc, ESC.CERRADA_EVENTO_CANCELADO),
                                  (e.app.repos.adicionales, sa, ESA.CERRADA_EVENTO_CANCELADO),
                                  (e.app.repos.sustituciones, sp, ESP.CERRADA_EVENTO_CANCELADO)):
            sol = repo.obtener_por_id(sid)
            self.assertEqual(sol.estado, estado)
            self.assertEqual(sol.motivo_cierre.causa.value, 'Evento cancelado')
            self.assertEqual(repo.listar_pendientes_por_evento_id(e.evento_id), [])
        self.assertEqual(e.obligacion('ServicioAdicional').estado, EO.SIN_EFECTO)    # cobro exclusivo sin efecto (SE-012)
        self.assertEqual(e.ec().devoluciones, [])
        self.assertEqual([x for x in e.app.uow.outbox if x.estado == 'Revisión'], [])

    def test_solicitud_confirmada_no_se_cierra_por_la_cancelacion(self):              # BN-008
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia).datos['obligacion_id']
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + timedelta(hours=1), 'C-DJ'); e.d.despachar()
        self.assertTrue(s.confirmar_servicio_adicional(sa, dia + timedelta(hours=2)).exito); e.d.despachar()
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia + timedelta(days=1)); e.d.despachar()
        sol = e.app.repos.adicionales.obtener_por_id(sa)
        self.assertEqual(sol.estado, ESA.CONFIRMADA)
        self.assertIsNone(sol.motivo_cierre)

    def test_no_se_inicia_una_sustitucion_con_el_evento_cancelado(self):              # BN-008
        """Con el Evento cancelado no se registra una nueva sustitución de proveedor, ni antes ni después de procesar
        las reacciones a la cancelación; no queda ninguna sustitución pendiente para el Evento."""
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        servicio = next(iter(e.evento().servicios))
        proveedor_original = e.evento().servicios[servicio].proveedor_id
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia)
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, dia + timedelta(hours=1))
        self.assertFalse(r.exito)                                               # antes de procesar las reacciones
        self.assertIn('cancelado', r.mensaje)
        e.d.despachar()
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, dia + timedelta(hours=2))
        self.assertFalse(r.exito)                                               # después de procesarlas
        e.d.despachar()
        self.assertEqual(e.app.repos.sustituciones.listar_pendientes_por_evento_id(e.evento_id), [])
        self.assertEqual(e.evento().estado, EstadoEvento.CANCELADO)
        self.assertEqual(e.evento().servicios[servicio].proveedor_id, proveedor_original)
        self.assertEqual([x for x in e.app.uow.outbox if x.estado == 'Revisión'], [])

    def test_cancelacion_por_falta_de_regularizacion_cierra_la_solicitud_detenida(self):   # BN-005, BN-008, CA-027
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Más invitados', Importe(D(1)), e.comunicacion).datos['solicitud_id']
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.DETENIDA_SALDO_VENCIDO)
        revision = e.comunicacion + timedelta(hours=25)
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision); e.d.despachar()
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.DETENIDA_SALDO_VENCIDO)   # no es automático
        e.s.cierre.registrar_cancelacion_por_falta_de_regularizacion(e.evento_id, 'Saldo no liquidado en 24 h', 'Coordinador',
                                                                    revision + timedelta(hours=1)); e.d.despachar()
        sol = e.app.repos.cambios.obtener_por_id(sc)
        self.assertEqual(sol.estado, ESC.CERRADA_EVENTO_CANCELADO)
        self.assertEqual(sol.motivo_cierre.causa.value, 'Evento cancelado')


class OperacionConfirmadaNoAplicadaConEventoCancelado(unittest.TestCase):
    """BN-006 y BN-008: una operación confirmada antes de la cancelación que todavía no se aplicó al Evento no se aplica
    al Evento cancelado. La solicitud conserva su confirmación y su historial (no se cierra), la configuración del
    Evento no cambia y el registro del Outbox queda en «Revisión» con el motivo. No se generan devoluciones ni nuevas
    obligaciones. El caso del Evento activo (O-02) se comprueba en test_observacion_o02_evento_iniciado_antes_de_aplicar_el_cambio."""

    def _registro(self, e, tipo):
        return next(x for x in e.app.uow.outbox if type(x.evento).__name__ == tipo)

    def test_cambio_confirmado_no_se_aplica_al_evento_cancelado(self):            # BN-006, BN-008, CA-041, CA-087
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        sc_id = next(iter(e.evento().servicios))
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Ajuste', Importe(D(1)), dia,
                                                      condiciones_propuestas={sc_id: CondicionesServicio('Menú ajustado')}).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), None, dia)
        e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, dia))
        e.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', True, dia))
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo', dia); e.d.despachar()
        self.assertTrue(e.s.cambios.confirmar_cambio(sid, dia).exito)
        obligaciones = dict(e.ec().obligaciones)
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia + timedelta(hours=1))   # antes de la reacción
        e.d.despachar()
        sol = e.app.repos.cambios.obtener_por_id(sid)
        self.assertEqual(sol.estado, ESC.CONFIRMADA)                            # conserva su confirmación
        self.assertIsNone(sol.motivo_cierre)                                    # no se cierra retroactivamente
        self.assertEqual(e.evento().estado, EstadoEvento.CANCELADO)
        self.assertEqual(e.evento().servicios[sc_id].condiciones.descripcion, 'Condiciones acordadas')   # no se aplicó
        reg = self._registro(e, 'CambioConfirmado')
        self.assertEqual(reg.estado, 'Revisión')
        self.assertIn('el Evento fue cancelado', reg.error)                     # motivo registrado
        self.assertEqual(self._registro(e, 'EventoCancelado').estado, 'Procesado')
        self.assertEqual(e.ec().devoluciones, [])
        self.assertEqual(e.ec().obligaciones.keys(), obligaciones.keys())       # sin nuevas obligaciones

    def test_servicio_adicional_confirmado_no_se_incorpora_al_evento_cancelado(self):   # BN-004, BN-008, SE-012
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia).datos['obligacion_id']
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + timedelta(hours=1), 'C-DJ'); e.d.despachar()
        self.assertTrue(s.confirmar_servicio_adicional(sa, dia + timedelta(hours=2)).exito)
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia + timedelta(hours=3))   # antes de la reacción
        e.d.despachar()
        sol = e.app.repos.adicionales.obtener_por_id(sa)
        self.assertEqual(sol.estado, ESA.CONFIRMADA)
        self.assertIsNone(sol.motivo_cierre)
        self.assertNotIn('DJ', [x.servicio for x in e.evento().servicios.values()])
        reg = self._registro(e, 'ServicioAdicionalConfirmado')
        self.assertEqual(reg.estado, 'Revisión')
        self.assertIn('el Evento fue cancelado', reg.error)
        self.assertEqual(e.obligacion('ServicioAdicional').estado, EO.LIQUIDADA)   # el pago no cambia
        self.assertEqual(e.ec().devoluciones, [])                              # Evento cancelado: no reembolso

    def test_evento_cancelado_no_acepta_ninguna_operacion_confirmada(self):       # BN-006, BN-008
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', dia + timedelta(hours=1)); e.d.despachar()
        ev = e.evento(); sc_id = next(iter(ev.servicios))
        antes = (ev.datos, {k: (v.proveedor_id, v.condiciones) for k, v in ev.servicios.items()})
        with self.assertRaises(ErrorDominio):
            ev.aplicar_cambio_confirmado('SC-1', None, {sc_id: CondicionesServicio('Otro menú')}, dia)
        with self.assertRaises(ErrorDominio):
            ev.incorporar_servicio_adicional('SA-1', ServicioContratado('SA-1-S', 'DJ', 'PV-9', CondicionesServicio('DJ')), dia)
        with self.assertRaises(ErrorDominio):
            ev.reasignar_proveedor('SP-1', sc_id, 'PV-7', dia)
        self.assertEqual((ev.datos, {k: (v.proveedor_id, v.condiciones) for k, v in ev.servicios.items()}), antes)


class ProcesosYPlazosQueSeConservan(unittest.TestCase):
    def test_alternativa_no_autorizada_de_una_sustitucion_sigue_en_busqueda(self):   # SE-001, CA-050 (distinto de CA-081)
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-7', True, Importe(D(800)), CondicionesServicio('Otro banquete'))]))
        e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=20)
        servicio = next(iter(e.evento().servicios))
        sid = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, dia).datos['sustitucion_id']
        e.s.sustitucion.buscar_alternativa_sustitucion(sid, CondicionesServicio('Otro banquete'), Importe(D(800)), dia)
        e.s.sustitucion.registrar_decision_cliente_sustitucion(sid, Decision('Cliente', True, dia))
        e.s.sustitucion.registrar_autorizacion_administracion_sustitucion(sid, Decision('Administración', False, dia, 'Costo excesivo'))
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(sid).estado, ESP.EN_BUSQUEDA_ALTERNATIVA)
        self.assertTrue(e.s.sustitucion.buscar_alternativa_sustitucion(sid, CondicionesServicio('Otro banquete'), Importe(D(800)), dia).exito)

    def test_pago_del_servicio_adicional_en_24_horas_naturales(self):              # BN-004, CA-082
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia)
        self.assertFalse(s.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + timedelta(hours=23)).exito)   # plazo vigente
        self.assertTrue(s.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + timedelta(hours=25)).exito)
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.CERRADA_FALTA_PAGO)
        self.assertEqual(len(e.avisos('Servicio adicional cerrado por falta de pago')), 1)


class AlcanceDelCambioDeFechaYHora(unittest.TestCase):
    def test_reprogramar_la_fecha_no_procede_y_cambiar_la_hora_si(self):          # BRD fuera del alcance, GL-019
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        otra_fecha = DatosEvento('Boda', FECHA_EVENTO + timedelta(days=30), 'Salón', 100)
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Reprogramar', Importe(D(1)), dia,
                                                    datos_propuestos=otra_fecha)
        self.assertFalse(r.exito)
        self.assertEqual(e.app.repos.cambios.listar_pendientes_por_evento_id(e.evento_id), [])
        otra_hora = DatosEvento('Boda', FECHA_EVENTO + timedelta(hours=2), 'Salón', 100)
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambiar horario', Importe(D(1)), dia,
                                                    datos_propuestos=otra_hora)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(r.datos['estado'], ESC.REGISTRADA.value)


if __name__ == '__main__':
    unittest.main()
