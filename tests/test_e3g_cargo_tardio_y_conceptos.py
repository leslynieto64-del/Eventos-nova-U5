"""E3G (H-04 y H-05): el cargo por cambio tardío sale de la tarifa vigente y el costo del proveedor y el cargo son
obligaciones de pago independientes.

Reglas: BN-003, SE-003, SE-005, SE-006, GL-020, GL-025, CA-061 a CA-063, CA-067, CA-068, CA-041; BN-005 (el pago de un
concepto no liquida los demás); SE-012 y CA-097 (cierre sin realizar y devolución por concepto).
Ejecutar desde la raíz:  python -m unittest tests.test_e3g_cargo_tardio_y_conceptos -v"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, FECHA_EVENTO, T0                                          # noqa: E402
from application.cqrs import ConsultarEstadoPagosQuery, ConsultarSolicitudesPendientesQuery        # noqa: E402
from application.servicios import transaccion                                                       # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                                       # noqa: E402
from domain.solicitudes import SolicitudCambio                                                      # noqa: E402
from domain.valores import (AnticipacionSolicitud, CondicionesServicio, ConceptoPago as CP, Decision,                  # noqa: E402
                            EstadoDevolucion, EstadoObligacionPago as EO, EstadoSolicitudCambio as ESC, Importe,
                            ImpactoModificacion, ResultadoViabilidad, TarifaCargoTardio, TipoSolicitud)

VIABLE = ResultadoViabilidad(True)
AVISO_SIN_IMPORTES = "No se puede solicitar el pago porque el cambio no genera importes por pagar (BN-003, CA-041, CA-067)."


def importe(x):
    return Importe(D(x))


class Base(unittest.TestCase):
    def armar(self, dias_antes, tarifa='150', costo=None, condiciones=False, aprobar=True, anexo=True, comunicar=True):
        """Cambio solicitado `dias_antes` días naturales antes del evento, evaluado como viable, con las aprobaciones que
        correspondan, su anexo y (si `comunicar`) la solicitud de pago. Devuelve un SimpleNamespace con el escenario."""
        e = Escenario(); e.confirmar_contratacion()
        dia = FECHA_EVENTO - timedelta(days=dias_antes)
        saldo = e.obligacion('SaldoContratoOriginal')
        if saldo.plazo.vencido(dia):
            # GL-049 / SE-006 (verificación del 28/10/2026): con el saldo vencido de hecho la solicitud se detiene. Estos casos prueban el cargo
            # tardío, no el bloqueo: si a esa fecha el plazo del saldo ya venció, el Cliente lo pagó a tiempo.
            e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, saldo.importe, T0 + timedelta(days=2), 'S-A-TIEMPO')
        cond = {next(iter(e.evento().servicios)): CondicionesServicio('Menú ajustado')} if condiciones else None
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', importe(tarifa), dia,
                                                      condiciones_propuestas=cond).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, VIABLE, importe(costo) if costo is not None else None, dia)
        if aprobar and self.cambio(e, sid).estado == ESC.PENDIENTE_APROBACION_CLIENTE:
            e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, dia))
            e.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', True, dia))
        if anexo and self.cambio(e, sid).estado == ESC.PENDIENTE_FORMALIZACION:
            e.s.cambios.registrar_anexo_cambio(sid, 'Anexo del cambio', dia); e.d.despachar()
        r = e.s.pagos.comunicar_solicitud_pago_cambio(sid, dia) if comunicar else None
        return SimpleNamespace(e=e, sid=sid, dia=dia, r=r)

    @staticmethod
    def cambio(e, sid):
        return e.app.repos.cambios.obtener_por_id(sid)

    @staticmethod
    def obligaciones(c):
        """{concepto: ObligacionPago} del cambio; falla si hubiera dos del mismo concepto."""
        obs = c.e.ec().obligaciones_de(c.sid)
        resultado = {o.concepto: o for o in obs}
        assert len(resultado) == len(obs)
        return resultado

    @staticmethod
    def pagar(c, concepto, cantidad=None, horas=2, **kw):
        o = Base.obligaciones(c)[concepto]
        return c.e.s.pagos.registrar_y_verificar_pago(c.e.ec_id, o.obligacion_id,
                                                      importe(cantidad) if cantidad is not None else o.importe,
                                                      c.dia + timedelta(hours=horas), f'C-{concepto.name}', **kw)


# ======================================================================= H-04: el cargo es la tarifa vigente
class ElCargoEsLaTarifaVigente(Base):
    def test_el_importe_del_cargo_es_la_tarifa_registrada_para_varias_tarifas(self):        # BN-003, GL-025, CA-062
        for tarifa in ('1', '150', '275.50', '1234.56'):
            with self.subTest(tarifa=tarifa):
                c = self.armar(6, tarifa=tarifa)
                self.assertTrue(c.r.exito, c.r.mensaje)
                o = self.obligaciones(c)
                self.assertEqual(list(o), [CP.CARGO_CAMBIO_TARDIO])
                cargo = o[CP.CARGO_CAMBIO_TARDIO]
                self.assertEqual((cargo.importe, cargo.origen_id, cargo.estado), (importe(tarifa), c.sid, EO.PENDIENTE))
                self.assertEqual(cargo.plazo.vence - cargo.plazo.inicio, timedelta(hours=24))
                self.assertEqual(cargo.plazo.inicio, c.dia)

    def test_limite_de_siete_dias_naturales(self):                                          # CA-061, CA-062, GL-020
        for dias, con_cargo in ((10, False), (8, False), (7, False), (6, True), (3, True), (1, True)):
            with self.subTest(dias=dias):
                c = self.armar(dias, tarifa='200', comunicar=False)
                s = self.cambio(c.e, c.sid)
                self.assertEqual(s.aplica_cargo_tardio, con_cargo)
                self.assertEqual(s.importes_a_cobrar, ((CP.CARGO_CAMBIO_TARDIO, importe('200')),) if con_cargo else ())
                r = c.e.s.pagos.comunicar_solicitud_pago_cambio(c.sid, c.dia)
                self.assertEqual(r.exito, con_cargo, r.mensaje)
                if not con_cargo:
                    self.assertEqual(r.mensaje, AVISO_SIN_IMPORTES)
                    self.assertEqual(c.e.ec().obligaciones_de(c.sid), [])

    def test_quien_llama_no_elige_el_importe(self):                                         # CA-062
        c = self.armar(6, tarifa='150', comunicar=False)
        r = c.e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.CAMBIO, c.sid, CP.CARGO_CAMBIO_TARDIO, importe('1'), c.dia)
        self.assertFalse(r.exito)
        self.assertEqual(c.e.ec().obligaciones_de(c.sid), [])
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.PENDIENTE_FORMALIZACION)
        self.assertTrue(c.e.s.pagos.comunicar_solicitud_pago_cambio(c.sid, c.dia).exito)
        self.assertEqual(self.obligaciones(c)[CP.CARGO_CAMBIO_TARDIO].importe, importe('150'))

    def test_solicitud_de_pago_de_un_servicio_adicional_inexistente_se_rechaza(self):
        e = Escenario(); e.confirmar_contratacion()
        r = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, 'SA-no-existe', CP.SERVICIO_ADICIONAL,
                                               importe('500'), FECHA_EVENTO - timedelta(days=10))
        self.assertEqual((r.exito, r.mensaje), (False, 'La solicitud no existe.'))
        self.assertEqual([o.concepto for o in e.ec().obligaciones.values()], [CP.ANTICIPO, CP.SALDO_CONTRATO_ORIGINAL])

    def test_el_cargo_no_se_solicita_antes_del_anexo(self):                                 # CA-068
        c = self.armar(6, anexo=False, comunicar=False)
        r = c.e.s.pagos.comunicar_solicitud_pago_cambio(c.sid, c.dia)
        self.assertFalse(r.exito)
        self.assertEqual(c.e.ec().obligaciones_de(c.sid), [])
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.PENDIENTE_FORMALIZACION)

    def test_tarifa_en_cero_no_genera_cargo(self):                                          # GL-025 (sin importe no hay cobro)
        c = self.armar(6, tarifa='0', comunicar=False)
        s = self.cambio(c.e, c.sid)
        self.assertTrue(s.aplica_cargo_tardio)
        self.assertEqual((s.importes_por_pagar, s.importes_a_cobrar), (False, ()))
        self.assertTrue(c.e.s.cambios.confirmar_cambio(c.sid, c.dia).exito)

    def test_el_cargo_no_se_cobra_si_el_cambio_no_es_viable(self):                          # CA-062, CA-069
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=3)
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', importe('150'), dia).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(False, 'Sin disponibilidad'), importe('300'), dia)
        s = self.cambio(e, sid)
        self.assertEqual((s.estado, s.costo_proveedor, s.importes_por_pagar, s.importes_a_cobrar),
                         (ESC.NO_PROCEDENTE, None, False, ()))
        self.assertFalse(e.s.pagos.comunicar_solicitud_pago_cambio(sid, dia).exito)
        self.assertEqual(e.ec().obligaciones_de(sid), [])

    def test_el_cargo_no_se_cobra_si_el_cliente_rechaza(self):                              # CA-062, CA-042
        c = self.armar(3, costo='300', aprobar=False, comunicar=False)
        c.e.s.cambios.registrar_decision_cliente_cambio(c.sid, Decision('Cliente', False, c.dia, 'No acepta el costo'))
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.RECHAZADA_CLIENTE)
        self.assertFalse(c.e.s.pagos.comunicar_solicitud_pago_cambio(c.sid, c.dia).exito)
        self.assertEqual(c.e.ec().obligaciones_de(c.sid), [])

    def test_el_cargo_no_se_cobra_si_administracion_no_autoriza(self):                      # CA-062, CA-044
        c = self.armar(3, costo='300', aprobar=False, comunicar=False)
        c.e.s.cambios.registrar_decision_cliente_cambio(c.sid, Decision('Cliente', True, c.dia))
        c.e.s.cambios.registrar_autorizacion_administracion_cambio(
            c.sid, Decision('Administración', False, c.dia, 'Sin presupuesto'))
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.NO_AUTORIZADA)
        self.assertFalse(c.e.s.pagos.comunicar_solicitud_pago_cambio(c.sid, c.dia).exito)
        self.assertEqual(c.e.ec().obligaciones_de(c.sid), [])

    def test_solo_el_cargo_y_su_pago_confirman_el_cambio(self):                             # CA-041, CA-067, SE-005
        c = self.armar(6, tarifa='180')
        faltan = c.e.s.cambios.confirmar_cambio(c.sid, c.dia).pendientes
        self.assertEqual(faltan, ['pago registrado y verificado'])
        self.assertTrue(self.pagar(c, CP.CARGO_CAMBIO_TARDIO).exito)
        self.assertTrue(c.e.s.cambios.confirmar_cambio(c.sid, c.dia + timedelta(hours=3)).exito)
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.CONFIRMADA)


# ======================================================================= H-05: obligaciones independientes
class ObligacionesIndependientes(Base):
    def test_costo_y_cargo_generan_dos_obligaciones_en_una_sola_comunicacion(self):         # BN-003, CA-063, SE-005
        c = self.armar(6, tarifa='150', costo='300')
        self.assertTrue(c.r.exito, c.r.mensaje)
        o = self.obligaciones(c)
        self.assertEqual(set(o), {CP.CAMBIO, CP.CARGO_CAMBIO_TARDIO})
        self.assertEqual((o[CP.CAMBIO].importe, o[CP.CARGO_CAMBIO_TARDIO].importe), (importe('300'), importe('150')))
        for ob in o.values():
            self.assertEqual((ob.origen_id, ob.estado, ob.plazo.inicio, ob.plazo.vence),
                             (c.sid, EO.PENDIENTE, c.dia, c.dia + timedelta(hours=24)))
        self.assertNotEqual(o[CP.CAMBIO].obligacion_id, o[CP.CARGO_CAMBIO_TARDIO].obligacion_id)
        s = self.cambio(c.e, c.sid)
        self.assertEqual((s.estado, s.obligacion_pago_id), (ESC.PENDIENTE_PAGO, o[CP.CAMBIO].obligacion_id))
        self.assertEqual(c.r.datos['conceptos'], ['Cambio', 'CargoCambioTardio'])
        self.assertEqual(len(c.e.avisos('Solicitud de pago')), 1)                            # una sola comunicación al Cliente

    def test_con_siete_dias_o_mas_solo_existe_el_costo_del_proveedor(self):                 # CA-061, CA-063
        c = self.armar(7, costo='300')
        self.assertEqual(set(self.obligaciones(c)), {CP.CAMBIO})
        self.assertEqual(self.obligaciones(c)[CP.CAMBIO].importe, importe('300'))

    def test_pagar_un_concepto_no_liquida_el_otro(self):                                    # BN-005
        c = self.armar(6, tarifa='150', costo='300')
        self.assertTrue(self.pagar(c, CP.CAMBIO).exito)
        o = self.obligaciones(c)
        self.assertEqual((o[CP.CAMBIO].estado, o[CP.CARGO_CAMBIO_TARDIO].estado), (EO.LIQUIDADA, EO.PENDIENTE))
        r = c.e.s.cambios.confirmar_cambio(c.sid, c.dia + timedelta(hours=3))
        self.assertFalse(r.exito)
        self.assertEqual(r.pendientes, ['pago registrado y verificado'])
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.PENDIENTE_PAGO)

    def test_se_confirma_solo_cuando_ambos_estan_liquidados_sin_importar_el_orden(self):    # CA-041, CA-067
        for orden in ((CP.CAMBIO, CP.CARGO_CAMBIO_TARDIO), (CP.CARGO_CAMBIO_TARDIO, CP.CAMBIO)):
            with self.subTest(orden=[x.name for x in orden]):
                c = self.armar(6, tarifa='150', costo='300')
                self.pagar(c, orden[0])
                self.assertFalse(c.e.s.cambios.confirmar_cambio(c.sid, c.dia + timedelta(hours=3)).exito)
                self.pagar(c, orden[1], horas=4)
                self.assertTrue(c.e.s.cambios.confirmar_cambio(c.sid, c.dia + timedelta(hours=5)).exito)
                c.e.d.despachar()
                self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.CONFIRMADA)
                self.assertTrue(all(o.estado == EO.LIQUIDADA for o in self.obligaciones(c).values()))

    def test_un_pago_parcial_no_liquida_el_concepto(self):                                  # BN-005
        c = self.armar(6, tarifa='150', costo='300')
        self.assertTrue(self.pagar(c, CP.CARGO_CAMBIO_TARDIO, cantidad='100').exito)
        self.assertEqual(self.obligaciones(c)[CP.CARGO_CAMBIO_TARDIO].estado, EO.PENDIENTE)
        self.pagar(c, CP.CAMBIO)
        self.assertFalse(c.e.s.cambios.confirmar_cambio(c.sid, c.dia + timedelta(hours=3)).exito)

    def test_pago_efectuado_a_tiempo_y_verificado_despues_de_las_24_horas(self):             # BN-003, CA-067
        """Las 24 horas son el plazo del Cliente para PAGAR (`fecha` del pago), no para que Administración lo registre
        (`registrado_en`) ni lo verifique. `ahora` es el momento en que se evalúa el cierre o la confirmación.
        Escenario: solicitud de pago en t0; el Cliente paga ambos conceptos en t0+20 h (dentro del plazo);
        Administración los registra en t0+26 h; el cierre se evalúa en t0+27 h; se verifican en t0+30 h."""
        c = self.armar(6, tarifa='150', costo='300')
        vence = c.dia + timedelta(hours=24)
        pagado, registrado, evaluado, verificado = (c.dia + timedelta(hours=h) for h in (20, 26, 27, 30))
        self.assertTrue(pagado <= vence < registrado < evaluado < verificado)
        registros = {}
        for concepto in (CP.CAMBIO, CP.CARGO_CAMBIO_TARDIO):
            registros[concepto] = self.pagar(c, concepto, horas=20, registrado_en=registrado, verificar_ahora=False)
            self.assertTrue(registros[concepto].exito)
        pagos = {p.obligacion_id: p for p in c.e.ec().pagos}
        for o in self.obligaciones(c).values():
            p = pagos[o.obligacion_id]
            self.assertEqual((p.fecha, p.registrado_en, p.verificado_en, p.estado.value),
                             (pagado, registrado, None, 'Registrado'))
            self.assertEqual(o.estado, EO.PENDIENTE)                  # registrado no es verificado (GL-046, GL-052)
        # La demora de Administración no es falta de pago: la solicitud no se cierra ni se confirma todavía.
        self.assertFalse(c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, evaluado).exito)
        r = c.e.s.cambios.confirmar_cambio(c.sid, evaluado)
        self.assertEqual((r.exito, r.pendientes), (False, ['pago registrado y verificado']))
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.PENDIENTE_PAGO)
        for registro in registros.values():
            self.assertTrue(c.e.s.pagos.verificar_pago_registrado(c.e.ec_id, registro.datos['pago_id'], verificado).exito)
        for o in self.obligaciones(c).values():                       # la verificación tardía no vuelve tardío el pago
            self.assertEqual(o.estado, EO.LIQUIDADA)
        ids = {o.obligacion_id for o in self.obligaciones(c).values()}          # solo los pagos de este cambio
        self.assertEqual({(p.fecha, p.verificado_en) for p in c.e.ec().pagos if p.obligacion_id in ids},
                         {(pagado, verificado)})
        self.assertTrue(c.e.s.cambios.confirmar_cambio(c.sid, verificado + timedelta(hours=1)).exito)
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.CONFIRMADA)

    def test_pago_efectuado_despues_del_plazo_aunque_se_registre_enseguida_no_cuenta(self):   # CA-067, SE-012
        """Contraste: lo que decide el cumplimiento es la fecha en que el Cliente pagó, no la del registro."""
        c = self.armar(6, tarifa='150', costo='300')
        pagado = c.dia + timedelta(hours=25)                           # una hora después del vencimiento
        self.assertTrue(self.pagar(c, CP.CAMBIO, horas=25, registrado_en=pagado + timedelta(minutes=5)).exito)
        self.assertEqual(self.obligaciones(c)[CP.CAMBIO].estado, EO.PENDIENTE)   # pago verificado, pero fuera de plazo
        evaluado = c.dia + timedelta(hours=26)
        r = c.e.s.cambios.confirmar_cambio(c.sid, evaluado)
        self.assertEqual((r.exito, r.pendientes), (False, ['pago registrado y verificado']))
        self.assertTrue(c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, evaluado).exito)
        c.e.d.despachar()
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.CERRADA_FALTA_PAGO)
        self.assertEqual({o.estado for o in self.obligaciones(c).values()}, {EO.SIN_EFECTO})
        # Lo recibido exclusivamente por la operación no realizada se devuelve (SE-012, evento no cancelado).
        self.assertEqual([(d.concepto, d.importe) for d in c.e.ec().devoluciones], [(CP.CAMBIO, importe('300'))])

    def test_no_se_cierra_por_falta_de_pago_dentro_del_plazo(self):                         # CA-067
        c = self.armar(6, tarifa='150', costo='300')
        self.assertFalse(c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, c.dia + timedelta(hours=23)).exito)
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.PENDIENTE_PAGO)

    def test_falta_de_pago_de_un_concepto_cierra_y_devuelve_solo_lo_recibido(self):         # CA-067, CA-097, SE-012
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CAMBIO)                                                              # el cargo no se paga
        r = c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, c.dia + timedelta(hours=25)); c.e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.CERRADA_FALTA_PAGO)
        o = self.obligaciones(c)
        self.assertEqual((o[CP.CAMBIO].estado, o[CP.CARGO_CAMBIO_TARDIO].estado), (EO.LIQUIDADA, EO.SIN_EFECTO))
        devs = c.e.ec().devoluciones
        self.assertEqual([(d.solicitud_id, d.concepto, d.importe, d.estado) for d in devs],
                         [(c.sid, CP.CAMBIO, importe('300'), EstadoDevolucion.PENDIENTE)])
        self.assertEqual(c.e.obligacion('SaldoContratoOriginal').estado, EO.PENDIENTE)       # el contrato original no cambia

    def test_falta_de_pago_de_ambos_deja_ambos_sin_efecto_y_sin_devolucion(self):           # CA-067, SE-012
        c = self.armar(6, tarifa='150', costo='300')
        self.assertTrue(c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, c.dia + timedelta(hours=25)).exito)
        c.e.d.despachar()
        self.assertEqual({o.estado for o in self.obligaciones(c).values()}, {EO.SIN_EFECTO})
        self.assertEqual(c.e.ec().devoluciones, [])

    def test_el_pago_tardio_de_un_concepto_no_evita_el_cierre(self):                        # CA-067
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CAMBIO)
        self.pagar(c, CP.CARGO_CAMBIO_TARDIO, horas=30)                                       # fuera del plazo
        self.assertFalse(c.e.s.cambios.confirmar_cambio(c.sid, c.dia + timedelta(hours=31)).exito)
        self.assertTrue(c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, c.dia + timedelta(hours=32)).exito)

    def test_inicio_del_evento_deja_sin_efecto_lo_pendiente_y_devuelve_lo_recibido(self):    # CA-070, SE-012
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CARGO_CAMBIO_TARDIO)
        self.assertTrue(c.e.s.cierre.procesar_inicio_evento(c.e.evento_id, FECHA_EVENTO).exito)
        c.e.d.despachar()
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.CERRADA_INICIO_EVENTO)
        o = self.obligaciones(c)
        self.assertEqual((o[CP.CAMBIO].estado, o[CP.CARGO_CAMBIO_TARDIO].estado), (EO.SIN_EFECTO, EO.LIQUIDADA))
        self.assertEqual([(d.concepto, d.importe) for d in c.e.ec().devoluciones], [(CP.CARGO_CAMBIO_TARDIO, importe('150'))])

    def test_cancelacion_del_evento_aplica_la_politica_de_no_reembolso(self):               # BN-008, SE-012
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CAMBIO)
        self.assertTrue(c.e.s.cierre.gestionar_cancelacion_solicitada(
            c.e.evento_id, 'El Cliente desiste', c.dia + timedelta(hours=3)).exito)
        c.e.d.despachar()
        self.assertEqual(self.cambio(c.e, c.sid).estado, ESC.CERRADA_EVENTO_CANCELADO)
        o = self.obligaciones(c)
        self.assertEqual((o[CP.CAMBIO].estado, o[CP.CARGO_CAMBIO_TARDIO].estado), (EO.LIQUIDADA, EO.SIN_EFECTO))
        self.assertEqual(c.e.ec().devoluciones, [])                                           # no se reembolsa

    def test_una_solicitud_no_afecta_las_obligaciones_de_otra(self):                         # BN-005
        a = self.armar(6, tarifa='150', costo='300')
        e = a.e
        sid2 = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Otro cambio', importe('90'), a.dia).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid2, VIABLE, None, a.dia)
        e.s.cambios.registrar_anexo_cambio(sid2, 'Anexo 2', a.dia); e.d.despachar()
        self.assertTrue(e.s.pagos.comunicar_solicitud_pago_cambio(sid2, a.dia).exito)
        otras = e.ec().obligaciones_de(sid2)
        self.assertEqual([(o.concepto, o.importe) for o in otras], [(CP.CARGO_CAMBIO_TARDIO, importe('90'))])
        self.assertEqual(len(e.ec().obligaciones_de(a.sid)), 2)
        self.assertEqual(self.obligaciones(a)[CP.CARGO_CAMBIO_TARDIO].importe, importe('150'))

    def test_la_solicitud_de_pago_no_se_comunica_dos_veces(self):
        c = self.armar(6, tarifa='150', costo='300')
        r = c.e.s.pagos.comunicar_solicitud_pago_cambio(c.sid, c.dia + timedelta(hours=1))
        self.assertFalse(r.exito)
        self.assertEqual(len(c.e.ec().obligaciones_de(c.sid)), 2)

    def test_solicitud_inexistente_se_rechaza(self):
        e = Escenario()
        r = e.s.pagos.comunicar_solicitud_pago_cambio('SC-no-existe', FECHA_EVENTO)
        self.assertFalse(r.exito)


class ConsultasDePagos(Base):
    def test_la_consulta_de_pagos_muestra_cada_concepto_por_separado(self):                  # CA-026, BN-005
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CAMBIO)
        vm = c.e.app.queries.estado_pagos.handle(ConsultarEstadoPagosQuery(c.e.evento_id))
        adicionales = {a['concepto']: a for a in vm.estadosCuenta[0].obligacionesAdicionales}
        self.assertEqual(set(adicionales), {'Cambio', 'CargoCambioTardio'})
        self.assertEqual((adicionales['Cambio']['importe'], adicionales['Cambio']['estado']), ('300', 'Liquidada'))
        self.assertEqual((adicionales['CargoCambioTardio']['importe'], adicionales['CargoCambioTardio']['estado']),
                         ('150', 'Pendiente'))
        self.assertEqual(vm.estadosCuenta[0].saldoContratoOriginal['estado'], 'Pendiente')    # el saldo del contrato no se mezcla

    def test_las_solicitudes_pendientes_muestran_importe_y_estado_de_cada_obligacion(self):    # CA-026
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CARGO_CAMBIO_TARDIO)
        vm = c.e.app.queries.pendientes.handle(ConsultarSolicitudesPendientesQuery(c.e.evento_id))
        (sol,) = [s for s in vm.solicitudes if s.solicitudId == c.sid]
        self.assertEqual({(o['concepto'], o['importe'], o['estado']) for o in sol.obligaciones},
                         {('Cambio', '300', 'Pendiente'), ('CargoCambioTardio', '150', 'Liquidada')})
        self.assertEqual((sol.estadoActual, sol.accionPendiente, sol.estadoPago), ('Pendiente de pago', 'pago pendiente', 'Pendiente'))


# ======================================================================= dominio
FECHA = datetime(2026, 11, 20, 18, 0)


def solicitud_dominio(dias, tarifa='150'):
    return SolicitudCambio('SC-1', 'EV-1', 'CT-1', 'EC-1', 'Cambio', AnticipacionSolicitud(FECHA - timedelta(days=dias), FECHA),
                           TarifaCargoTardio(importe(tarifa)))


class ImportesDeLaSolicitud(unittest.TestCase):
    def test_importes_a_cobrar_segun_viabilidad_costo_y_anticipacion(self):                  # BN-003, SE-005
        costos, sin_impacto = ImpactoModificacion(False, True, False), ImpactoModificacion(False, False, False)
        casos = [(10, VIABLE, costos, importe('300'), ((CP.CAMBIO, importe('300')),)),
                 (6, VIABLE, costos, importe('300'), ((CP.CAMBIO, importe('300')), (CP.CARGO_CAMBIO_TARDIO, importe('150')))),
                 (6, VIABLE, sin_impacto, None, ((CP.CARGO_CAMBIO_TARDIO, importe('150')),)),
                 (10, VIABLE, sin_impacto, None, ()),
                 (6, ResultadoViabilidad(False, 'No'), costos, importe('300'), ())]
        for dias, resultado, impacto, costo, esperado in casos:
            with self.subTest(dias=dias, viable=resultado.viable, costo=costo):
                s = solicitud_dominio(dias)
                s.registrar_viabilidad(resultado, impacto, FECHA - timedelta(days=dias), costo)
                self.assertEqual(s.importes_a_cobrar, esperado)
                self.assertEqual(s.costo_proveedor, costo if resultado.viable else None)

    def test_sin_costo_informado_el_costo_no_se_inventa(self):
        s = solicitud_dominio(10)
        s.registrar_viabilidad(VIABLE, ImpactoModificacion(False, True, False), FECHA - timedelta(days=10))
        self.assertEqual((s.importes_por_pagar, s.costo_proveedor, s.importes_a_cobrar), (True, None, ()))

    def test_la_solicitud_de_pago_sin_importes_determinables_se_rechaza_sin_efectos(self):
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', importe('150'), dia).datos['solicitud_id']
        # Llamada directa al dominio: un impacto que afecta costos pero sin ningún costo informado.
        s = e.app.repos.cambios.obtener_por_id(sid)
        s.registrar_viabilidad(VIABLE, ImpactoModificacion(False, True, False), dia)
        s.registrar_decision_cliente(Decision('Cliente', True, dia))
        s.registrar_autorizacion(Decision('Administración', True, dia))
        s.asociar_anexo('AX-1')
        with transaccion(e.app.uow, s):
            e.app.repos.cambios.guardar(s)
        r = e.s.pagos.comunicar_solicitud_pago_cambio(sid, dia)
        self.assertFalse(r.exito)
        self.assertIn('faltan el costo del proveedor', r.mensaje)
        self.assertEqual(e.ec().obligaciones_de(sid), [])
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sid).estado, ESC.PENDIENTE_FORMALIZACION)


class ConsultasDeEstadoCuenta(unittest.TestCase):
    @staticmethod
    def ec_con(*estados):
        ec = EstadoCuenta('EC-1', 'CT-1', 'EV-1')
        for i, (concepto, estado) in enumerate(estados):
            ec.comunicar_solicitud_pago(f'OB-{i}', concepto, importe('10'), 'SC-1', FECHA).estado = estado
        return ec

    def test_solicitud_liquidada_exige_todas_las_vigentes_liquidadas(self):
        self.assertFalse(self.ec_con((CP.CAMBIO, EO.LIQUIDADA), (CP.CARGO_CAMBIO_TARDIO, EO.PENDIENTE)).solicitud_liquidada('SC-1'))
        ec = self.ec_con((CP.CAMBIO, EO.LIQUIDADA), (CP.CARGO_CAMBIO_TARDIO, EO.LIQUIDADA))
        self.assertTrue(ec.solicitud_liquidada('SC-1'))
        self.assertFalse(ec.solicitud_liquidada('SC-otra'))
        sin_efecto = self.ec_con((CP.CAMBIO, EO.LIQUIDADA), (CP.CARGO_CAMBIO_TARDIO, EO.SIN_EFECTO))
        self.assertTrue(sin_efecto.solicitud_liquidada('SC-1'))                                # lo sin efecto no cuenta
        self.assertFalse(self.ec_con().solicitud_liquidada('SC-1'))                            # sin obligaciones: no liquidada

    def test_vencimiento_sin_pago_de_alguna_obligacion(self):
        ec = self.ec_con((CP.CAMBIO, EO.PENDIENTE), (CP.CARGO_CAMBIO_TARDIO, EO.PENDIENTE))
        self.assertFalse(ec.solicitud_vencida_sin_pago('SC-1', FECHA + timedelta(hours=24)))
        self.assertTrue(ec.solicitud_vencida_sin_pago('SC-1', FECHA + timedelta(hours=24, minutes=1)))
        pagadas = self.ec_con((CP.CAMBIO, EO.LIQUIDADA), (CP.CARGO_CAMBIO_TARDIO, EO.LIQUIDADA))
        self.assertFalse(pagadas.solicitud_vencida_sin_pago('SC-1', FECHA + timedelta(days=5)))


if __name__ == '__main__':
    unittest.main()
