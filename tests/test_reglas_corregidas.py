"""Pruebas preliminares de las reglas corregidas en las etapas 3 a 7.
Ejecutar desde la raíz:  python -m unittest discover -s tests -v"""
import os, sys, unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from infrastructure.composicion import construir                       # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada  # noqa: E402
from application.cqrs import ConsultarEstadoPagosQuery, RegistrarCancelacionPorFaltaDeRegularizacionCommand  # noqa: E402
from domain.valores import (CondicionesServicio, DatosEvento, ContenidoPropuesta, Importe, DisponibilidadProveedor, Decision,  # noqa: E402
                            EstadoEvento, EstadoContrato, OrigenCancelacion, EstadoSolicitudCambio as ESC,
                            EstadoSolicitudServicioAdicional as ESA, EstadoPago, ResultadoViabilidad, TipoSolicitud, ConceptoPago)

T0 = datetime(2026, 10, 1, 10, 0)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)
CONTENIDO = ContenidoPropuesta(('Banquete',), ('PV-1',), Importe(D(10000)), 'Condiciones acordadas')


class Escenario:
    def __init__(self, disponibilidad=None):
        self.app = construir(disponibilidad)
        s, d = self.app.servicios, self.app.despachador
        self.s, self.d = s, d
        self.evento_id = s.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        pr = s.propuestas.crear_propuesta(self.evento_id, CONTENIDO, T0).datos['propuesta_id']
        p = self.app.repos.propuestas.obtener_por_id(pr)
        s.propuestas.aceptar_propuesta(pr, p.version_vigente_id, T0); d.despachar()
        self.contrato_id = s.contratacion.preparar_contrato(pr, True).datos['contrato_id']
        s.contratacion.registrar_firma_contrato(self.contrato_id, T0); d.despachar()
        self.ec_id = self.app.repos.estados_cuenta.obtener_por_contrato_id(self.contrato_id).id

    def ec(self):
        return self.app.repos.estados_cuenta.obtener_por_id(self.ec_id)

    def evento(self):
        return self.app.repos.eventos.obtener_por_id(self.evento_id)

    def obligacion(self, concepto):
        return next(o for o in self.ec().obligaciones.values() if o.concepto.value == concepto)

    def confirmar_contratacion(self):
        self.s.contratacion.registrar_comunicacion_politica_no_reembolso(self.contrato_id, T0)
        ob = self.obligacion('Anticipo')
        self.s.pagos.registrar_y_verificar_pago(self.ec_id, ob.obligacion_id, Importe(D('3000.00')), T0 + timedelta(days=1), 'C-ANT')
        self.d.despachar()

    def vencer_saldo_y_comunicar_moratorios(self):
        limite = self.obligacion('SaldoContratoOriginal').plazo.vence
        self.vencimiento = limite + timedelta(hours=1)
        self.s.pagos.registrar_vencimiento_saldo_original(self.ec_id, self.vencimiento); self.d.despachar()
        self.comunicacion = self.vencimiento + timedelta(hours=1)
        self.s.pagos.activar_protocolo_cobro(self.ec_id, Importe(D(200)), self.comunicacion, 'Recordatorio amistoso'); self.d.despachar()

    def avisos(self, asunto):
        return [n for n in self.app.notificador.enviados if n[1] == asunto]


class CancelacionPorSaldoVencido(unittest.TestCase):
    def setUp(self):
        self.e = Escenario(); self.e.confirmar_contratacion(); self.e.vencer_saldo_y_comunicar_moratorios()
        self.revision = self.e.comunicacion + timedelta(hours=25)

    def test_vencimiento_verificado_no_cancela_automaticamente(self):  # BN-005, BN-008, SE-007, CA-027
        r = self.e.s.cierre.resolver_regularizacion_saldo_vencido(self.e.ec_id, self.revision); self.e.d.despachar()
        self.assertFalse(r.datos['regularizado'])
        self.assertEqual(self.e.evento().estado, EstadoEvento.EN_ORGANIZACION)
        self.assertEqual(len(self.e.avisos('Plazo de regularización vencido')), 1)
        self.assertEqual(self.e.avisos('Evento cancelado'), [])

    def test_coordinador_registra_la_cancelacion_con_motivo(self):  # BN-008, CA-027
        self.e.s.cierre.resolver_regularizacion_saldo_vencido(self.e.ec_id, self.revision); self.e.d.despachar()
        cmd = RegistrarCancelacionPorFaltaDeRegularizacionCommand(self.e.evento_id, 'Saldo y moratorios no liquidados en 24 h', 'Coordinador', self.revision + timedelta(hours=2))
        r = self.e.app.commands.cancelar_por_falta_de_regularizacion.handle(cmd); self.e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        ev = self.e.evento()
        self.assertEqual(ev.estado, EstadoEvento.CANCELADO)
        self.assertEqual(ev.motivo_cancelacion.origen, OrigenCancelacion.FALTA_REGULARIZACION)
        self.assertEqual(ev.motivo_cancelacion.registrado_por, 'Coordinador')
        self.assertEqual(len(self.e.avisos('Evento cancelado')), 1)
        self.e.app.commands.cancelar_por_falta_de_regularizacion.handle(cmd); self.e.d.despachar()
        self.assertEqual(len(self.e.avisos('Evento cancelado')), 1)

    def test_no_se_registra_sin_verificacion_de_administracion(self):  # BN-008, CA-027
        r = self.e.s.cierre.registrar_cancelacion_por_falta_de_regularizacion(self.e.evento_id, 'motivo', 'Coordinador', self.revision)
        self.assertFalse(r.exito)
        self.assertEqual(self.e.evento().estado, EstadoEvento.EN_ORGANIZACION)

    def test_pago_tardio_no_evita_la_cancelacion(self):  # BN-005, CA-027
        saldo, mor = self.e.obligacion('SaldoContratoOriginal'), self.e.obligacion('CargosMoratorios')
        tarde = self.e.comunicacion + timedelta(hours=30)
        self.e.s.pagos.registrar_y_verificar_pago(self.e.ec_id, saldo.obligacion_id, saldo.importe, tarde, 'C-S')
        self.e.s.pagos.registrar_y_verificar_pago(self.e.ec_id, mor.obligacion_id, mor.importe, tarde, 'C-M')
        r = self.e.s.cierre.resolver_regularizacion_saldo_vencido(self.e.ec_id, tarde + timedelta(hours=1)); self.e.d.despachar()
        self.assertFalse(r.datos['regularizado'])
        r = self.e.s.cierre.registrar_cancelacion_por_falta_de_regularizacion(self.e.evento_id, 'Pago fuera de plazo', 'Coordinador', tarde + timedelta(hours=2))
        self.assertTrue(r.exito)

    def test_regularizado_a_tiempo_retoma_solicitudes_y_no_permite_cancelar(self):  # BN-003, SE-006, CA-066, CA-027
        sc = self.e.s.cambios.registrar_solicitud_cambio(self.e.evento_id, self.e.contrato_id, 'Más invitados', Importe(D(100)), self.e.comunicacion)
        self.assertEqual(sc.datos['estado'], ESC.DETENIDA_SALDO_VENCIDO.value)
        saldo, mor = self.e.obligacion('SaldoContratoOriginal'), self.e.obligacion('CargosMoratorios')
        a_tiempo = self.e.comunicacion + timedelta(hours=5)
        self.e.s.pagos.registrar_y_verificar_pago(self.e.ec_id, saldo.obligacion_id, saldo.importe, a_tiempo, 'C-S')
        self.e.s.pagos.registrar_y_verificar_pago(self.e.ec_id, mor.obligacion_id, mor.importe, a_tiempo, 'C-M')
        r = self.e.s.cierre.resolver_regularizacion_saldo_vencido(self.e.ec_id, self.revision); self.e.d.despachar()
        self.assertTrue(r.datos['regularizado'])
        self.assertEqual(self.e.app.repos.cambios.obtener_por_id(sc.datos['solicitud_id']).estado, ESC.REGISTRADA)
        r = self.e.s.cierre.registrar_cancelacion_por_falta_de_regularizacion(self.e.evento_id, 'motivo', 'Coordinador', self.revision)
        self.assertFalse(r.exito)

    def test_consulta_de_pagos_muestra_el_resultado(self):  # BN-007, CA-027
        self.e.s.cierre.resolver_regularizacion_saldo_vencido(self.e.ec_id, self.revision); self.e.d.despachar()
        vm = self.e.app.queries.estado_pagos.handle(ConsultarEstadoPagosQuery(self.e.evento_id))
        self.assertEqual(vm.estadosCuenta[0].saldoContratoOriginal['resultadoRegularizacion'], 'No regularizado')


class AnticipoNoRecibido(unittest.TestCase):
    def test_cierra_sin_contratacion_y_no_cancela(self):  # BN-009, SE-010, CA-020, CA-021
        e = Escenario()
        contacto = T0 + timedelta(days=6)
        self.assertTrue(e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto con el Cliente', False).exito)
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=25), 'Sin pago', True); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)
        self.assertEqual(e.evento().estado, EstadoEvento.CERRADO_SIN_CONTRATACION)
        self.assertIsNone(e.evento().motivo_cancelacion)
        self.assertEqual(e.avisos('Evento cancelado'), [])

    def test_no_se_cierra_antes_de_tres_dias_habiles(self):  # SE-010, CA-020
        e = Escenario()
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, T0 + timedelta(days=1), 'Contacto', False)
        self.assertFalse(r.exito)
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, T0 + timedelta(days=1), 'Contacto', True)
        self.assertFalse(r.exito)


class PagoEfectuadoFrenteARegistroYVerificacion(unittest.TestCase):
    """BN-009, BN-003, BN-004, BN-005: el plazo es para que el Cliente efectúe el pago (fecha del comprobante);
    el registro y la verificación de Administración son momentos distintos y pueden ser posteriores."""

    def pago(self, e, pago_id):
        return next(p for p in e.ec().pagos if p.pago_id == pago_id)

    def contrato(self, e):
        return e.app.repos.contratos.obtener_por_id(e.contrato_id)

    def contactar(self, e):
        e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
        contacto = T0 + timedelta(days=6)                                   # vencieron los 3 días hábiles
        self.assertTrue(e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False).exito)
        return contacto

    # escenario 1
    def test_anticipo_efectuado_en_tres_dias_habiles(self):                  # BN-009, CA-018, CA-019
        e = Escenario()
        e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
        ob = e.obligacion('Anticipo').obligacion_id
        pagado, registrado = T0 + timedelta(days=1), T0 + timedelta(days=1, hours=3)
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D('3000.00')), pagado, 'C-A1', registrado); e.d.despachar()
        p = self.pago(e, r.datos['pago_id'])
        self.assertEqual((p.fecha, p.registrado_en, p.verificado_en), (pagado, registrado, registrado))
        self.assertEqual(self.contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)

    # escenario 2
    def test_anticipo_efectuado_en_las_24_horas_posteriores_al_contacto(self):   # BN-009, CA-020, CA-021
        e = Escenario(); contacto = self.contactar(e)
        ob = e.obligacion('Anticipo').obligacion_id
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D('3000.00')), contacto + timedelta(hours=10), 'C-A2',
                                             contacto + timedelta(hours=11)); e.d.despachar()
        self.assertEqual(self.contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        self.assertFalse(e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=25), 'Sin pago', True).exito)

    # escenario 3
    def test_anticipo_efectuado_a_tiempo_y_registrado_y_verificado_despues(self):   # BN-009, CA-021
        e = Escenario(); contacto = self.contactar(e)
        ob = e.obligacion('Anticipo').obligacion_id
        pagado, registrado, verificado = (contacto + timedelta(hours=20), contacto + timedelta(hours=30), contacto + timedelta(hours=40))
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D('3000.00')), pagado, 'C-A3', registrado, verificar_ahora=False)
        e.d.despachar()
        self.assertEqual(r.datos['estado'], EstadoPago.REGISTRADO.value)
        r_cierre = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=31), 'Sin pago', True)
        self.assertFalse(r_cierre.exito)                                    # la demora administrativa no es falta de pago
        self.assertEqual(self.contrato(e).estado, EstadoContrato.FIRMADO)   # pendiente de verificación, sin confirmar
        self.assertTrue(e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], verificado).exito); e.d.despachar()
        p = self.pago(e, r.datos['pago_id'])
        self.assertEqual((p.fecha, p.registrado_en, p.verificado_en), (pagado, registrado, verificado))
        self.assertEqual(self.contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)

    # escenario 4
    def test_anticipo_no_efectuado_en_las_24_horas_cierra_sin_contratacion(self):   # BN-009, SE-010, CA-021
        e = Escenario(); contacto = self.contactar(e)
        self.assertFalse(e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=23), 'Sin pago', True).exito)
        ob = e.obligacion('Anticipo').obligacion_id
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D('3000.00')), contacto + timedelta(hours=30), 'C-A4',
                                             contacto + timedelta(hours=31)); e.d.despachar()
        self.assertEqual(self.contrato(e).estado, EstadoContrato.FIRMADO)   # pago tardío: no confirma la contratación
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=32), 'Sin pago a tiempo', True)
        e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(self.contrato(e).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)
        self.assertEqual(e.evento().estado, EstadoEvento.CERRADO_SIN_CONTRATACION)

    def _cambio_con_pago(self, e):
        dia = FECHA_EVENTO - timedelta(days=10)
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Más invitados', Importe(D(100)), dia,
                                                     datos_propuestos=DatosEvento('Boda', FECHA_EVENTO, 'Salón', 120)).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), Importe(D(900)), dia)
        e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, dia))
        e.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', True, dia))
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo 120 invitados', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago_cambio(sid, dia).datos['obligacion_id']
        return sid, ob, dia

    def _servicio_con_pago(self, e):
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL,
                                                Importe(D(500)), dia).datos['obligacion_id']
        return sa, ob, dia

    # escenario 5
    def test_cambio_pagado_en_24_horas_y_registrado_despues(self):           # BN-003, CA-041, CA-067
        e = Escenario(); e.confirmar_contratacion()
        sid, ob, dia = self._cambio_con_pago(e)
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(900)), dia + timedelta(hours=20), 'C-CB',
                                                 dia + timedelta(hours=30))
        p = self.pago(e, r.datos['pago_id'])
        self.assertTrue(p.registrado_en > e.ec().obligaciones[ob].plazo.vence >= p.fecha)
        self.assertFalse(e.s.cambios.cerrar_cambio_por_falta_de_pago(sid, dia + timedelta(hours=31)).exito)
        self.assertTrue(e.s.cambios.confirmar_cambio(sid, dia + timedelta(hours=31)).exito); e.d.despachar()
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sid).estado, ESC.CONFIRMADA)
        self.assertEqual(e.evento().datos.invitados_aproximados, 120)

    # escenario 6
    def test_servicio_adicional_pagado_en_24_horas_y_registrado_y_verificado_despues(self):   # BN-004, CA-080, CA-082
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        sa, ob, dia = self._servicio_con_pago(e)
        s = e.s.adicionales
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + timedelta(hours=22), 'C-SA',
                                                 dia + timedelta(hours=26), verificar_ahora=False)
        self.assertFalse(s.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + timedelta(hours=27)).exito)
        self.assertFalse(s.confirmar_servicio_adicional(sa, dia + timedelta(hours=27)).exito)      # pendiente de verificación
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.PENDIENTE_PAGO)
        e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], dia + timedelta(hours=30))
        self.assertTrue(s.confirmar_servicio_adicional(sa, dia + timedelta(hours=31)).exito)
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.CONFIRMADA)

    # escenario 7
    def test_pago_de_servicio_adicional_efectuado_despues_del_plazo(self):   # BN-004, CA-080
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        sa, ob, dia = self._servicio_con_pago(e)
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + timedelta(hours=26), 'C-SA-T', dia + timedelta(hours=27))
        self.assertFalse(e.s.adicionales.confirmar_servicio_adicional(sa, dia + timedelta(hours=28)).exito)
        self.assertTrue(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + timedelta(hours=28)).exito)
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.CERRADA_FALTA_PAGO)

    # escenario 8
    def test_regularizacion_pagada_a_tiempo_y_registrada_y_verificada_despues(self):   # BN-005, CA-027, CA-066, CA-072
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        saldo, mor = e.obligacion('SaldoContratoOriginal'), e.obligacion('CargosMoratorios')
        pagado, registrado = e.comunicacion + timedelta(hours=20), e.comunicacion + timedelta(hours=26)
        r1 = e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, saldo.importe, pagado, 'C-S', registrado, verificar_ahora=False)
        r2 = e.s.pagos.registrar_y_verificar_pago(e.ec_id, mor.obligacion_id, mor.importe, pagado, 'C-M', registrado, verificar_ahora=False)
        revision = e.comunicacion + timedelta(hours=27)
        self.assertFalse(e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision).exito)   # no se resuelve sin verificar
        self.assertIsNone(e.ec().resultado_regularizacion)
        for r in (r1, r2):
            e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], revision)
        res = e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision + timedelta(hours=1)); e.d.despachar()
        self.assertTrue(res.datos['regularizado'])
        self.assertFalse(e.s.cierre.registrar_cancelacion_por_falta_de_regularizacion(e.evento_id, 'motivo', 'Coordinador',
                                                                                      revision + timedelta(hours=2)).exito)

    def test_saldo_original_pagado_a_tiempo_y_verificado_despues_no_vence(self):   # BN-005: plazo del Cliente, no de Administración
        e = Escenario(); e.confirmar_contratacion()
        saldo = e.obligacion('SaldoContratoOriginal')
        limite = saldo.plazo.vence
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, saldo.importe, limite - timedelta(hours=2), 'C-SO',
                                                 limite + timedelta(hours=5), verificar_ahora=False)
        e.s.pagos.registrar_vencimiento_saldo_original(e.ec_id, limite + timedelta(hours=6)); e.d.despachar()
        self.assertFalse(e.ec().saldo_vencido_sin_regularizar)
        e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], limite + timedelta(hours=8))
        self.assertEqual(e.obligacion('SaldoContratoOriginal').estado.value, 'Liquidada')


class ServiciosAdicionales(unittest.TestCase):
    def setUp(self):
        self.e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        self.e.confirmar_contratacion()

    def test_menos_de_cinco_dias_no_procede(self):  # BN-004, SE-004, CA-077, CA-083
        r = self.e.s.adicionales.registrar_solicitud_servicio_adicional(self.e.evento_id, self.e.contrato_id, 'DJ', FECHA_EVENTO - timedelta(days=4))
        self.assertEqual(r.datos['estado'], ESA.NO_PROCEDENTE.value)

    def test_elegibilidad_se_conserva_aunque_resten_menos_de_cinco_dias(self):  # SE-004, CA-080
        s = self.e.s.adicionales
        sa = s.registrar_solicitud_servicio_adicional(self.e.evento_id, self.e.contrato_id, 'DJ', FECHA_EVENTO - timedelta(days=6)).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], FECHA_EVENTO - timedelta(days=6))
        dia3 = FECHA_EVENTO - timedelta(days=3)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia3))
        r = s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia3))
        self.assertEqual(self.e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.AUTORIZADA)


if __name__ == '__main__':
    unittest.main()
