"""E-1 — GL-060 / C-15 aplicado uniformemente a los plazos expresados en días hábiles.

GL-060 (cierre de alcance C-15): los días hábiles son de lunes a viernes, con los festivos contados como hábiles; el día de partida
no cuenta; el límite de un plazo en días hábiles es EXCLUSIVO: vence a las 00:00 del día siguiente al último día del plazo (a esa
hora ya está fuera de plazo), mientras que los límites en T y en las ventanas de horas son inclusivos.
Los seis plazos en días hábiles: anticipo (3), seguimiento del anticipo (3), saldo (3 antes del evento), límite de la sustitución
(3 antes del evento), devolución del anticipo por contratación cerrada (5) y devolución por solicitud no realizada, SE-012 (5).
No se extiende a plazos en horas o días naturales (24 h de cambios y servicios adicionales, 5 y 7 días naturales).
Calendario del escenario: firma jueves 01/10/2026 10:00; evento viernes 20/11/2026 18:00.
Ejecutar desde la raíz:  python -m unittest tests.test_plazos_dias_habiles_gl060_e1 -v"""
import os, sys, unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from apoyo_bd import BaseConBD                                                                       # noqa: E402
from apoyo_flujo import Flujo                                                                        # noqa: E402
from apoyo_maquina_estados_sustitucion import CON_IMPACTO, ESP, alternativa, aprobada, sustitucion   # noqa: E402
from test_reglas_anticipo_decisiones_abc import escenario, pagar                                     # noqa: E402
from test_reglas_corregidas import Escenario, FECHA_EVENTO, T0                                       # noqa: E402
from domain.estado_cuenta import Devolucion                                                          # noqa: E402
from domain.valores import (ConceptoPago as CP, Decision, EstadoObligacionPago as EO, Importe, PlazoPago, TipoDevolucion,   # noqa: E402
                            limite_exclusivo_dias_habiles, limite_exclusivo_dias_habiles_antes)
from infrastructure.persistencia.composicion_persistente import construir_persistente                # noqa: E402

SEG = timedelta(seconds=1)
LIMITE_ANTICIPO = datetime(2026, 10, 7, 0, 0)        # firma jue 01/10 → viernes 02, lunes 05, martes 06 → vence mié 07/10 00:00
LIMITE_SALDO = datetime(2026, 11, 18, 0, 0)          # evento vie 20/11 → jueves 19, miércoles 18, martes 17 → vence mié 18/11 00:00


class FuncionesDeLimite(unittest.TestCase):
    def test_hacia_adelante_el_dia_de_partida_no_cuenta_y_el_limite_es_la_medianoche_siguiente(self):
        self.assertEqual(limite_exclusivo_dias_habiles(T0, 3), LIMITE_ANTICIPO)
        self.assertEqual(limite_exclusivo_dias_habiles(datetime(2026, 11, 13, 9, 0), 5), datetime(2026, 11, 21, 0, 0))   # viernes → sábado
        self.assertEqual(limite_exclusivo_dias_habiles(datetime(2026, 11, 14, 23, 59), 5), datetime(2026, 11, 21, 0, 0))  # sábado = como el lunes
        self.assertEqual(limite_exclusivo_dias_habiles(datetime(2026, 11, 15, 0, 0), 5), datetime(2026, 11, 21, 0, 0))   # domingo

    def test_hacia_atras_el_ultimo_dia_es_el_ultimo_dia_habil_previo_al_evento(self):
        self.assertEqual(limite_exclusivo_dias_habiles_antes(FECHA_EVENTO, 3), LIMITE_SALDO)
        # evento en lunes 23/11 18:00: hábiles previos viernes 20, jueves 19 y miércoles 18 (el fin de semana no cuenta) → límite jueves 19/11 00:00
        self.assertEqual(limite_exclusivo_dias_habiles_antes(datetime(2026, 11, 23, 18, 0), 3), datetime(2026, 11, 19, 0, 0))

    def test_el_plazo_exclusivo_vence_en_el_limite_y_el_de_horas_no(self):
        dias = PlazoPago.dias_habiles(T0, 3)
        self.assertTrue(dias.exclusivo)
        self.assertEqual((dias.vence, dias.vencido(dias.vence - SEG), dias.vencido(dias.vence)), (LIMITE_ANTICIPO, False, True))
        self.assertTrue(dias.incluye(dias.vence - SEG) and not dias.incluye(dias.vence))
        horas = PlazoPago.horas_naturales(T0, 24)                                                    # ventana de horas: inclusiva (GL-060)
        self.assertFalse(horas.exclusivo)
        self.assertEqual((horas.vencido(horas.vence), horas.vencido(horas.vence + SEG)), (False, True))


class Anticipo(unittest.TestCase):
    def test_el_plazo_del_anticipo_vence_a_la_medianoche_del_dia_siguiente_al_tercer_dia_habil(self):
        e = escenario()
        plazo = e.obligacion('Anticipo').plazo
        self.assertEqual((plazo.inicio, plazo.vence, plazo.exclusivo), (T0, LIMITE_ANTICIPO, True))
        self.assertFalse(plazo.vencido(datetime(2026, 10, 6, 23, 59, 59)))                           # martes 06/10 23:59:59: dentro
        self.assertTrue(plazo.vencido(LIMITE_ANTICIPO))                                              # miércoles 07/10 00:00: vencido

    def test_un_pago_efectuado_en_el_ultimo_segundo_esta_en_plazo_y_a_las_00_00_ya_no(self):
        e = escenario(); ob = e.obligacion('Anticipo').obligacion_id
        pagar(e, 3000, LIMITE_ANTICIPO - SEG, verificar=False, comprobante='C-1')                    # registrado, sin verificar
        self.assertFalse(e.ec().obligacion_vencida_sin_pago(ob, LIMITE_ANTICIPO + timedelta(days=1)))   # pagó a tiempo
        e2 = escenario(); ob2 = e2.obligacion('Anticipo').obligacion_id
        pagar(e2, 3000, LIMITE_ANTICIPO, verificar=False, comprobante='C-1')
        self.assertTrue(e2.ec().obligacion_vencida_sin_pago(ob2, LIMITE_ANTICIPO + timedelta(days=1)))   # efectuado ya vencido

    def test_el_seguimiento_del_anticipo_procede_solo_desde_la_medianoche(self):
        e = escenario()
        antes = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, LIMITE_ANTICIPO - SEG, 'Contacto', False)
        self.assertFalse(antes.exito)
        self.assertIn('no ha vencido', antes.mensaje)
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).seguimientos_anticipo, [])    # sin cambios al rechazar
        despues = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, LIMITE_ANTICIPO, 'Contacto', False)
        self.assertTrue(despues.exito, despues.mensaje)


class Saldo(unittest.TestCase):
    def setUp(self):
        self.e = Escenario(); self.e.confirmar_contratacion()
        self.ob = self.e.obligacion('SaldoContratoOriginal')

    def test_el_plazo_del_saldo_vence_a_la_medianoche_posterior_al_tercer_dia_habil_previo(self):
        self.assertEqual((self.ob.plazo.vence, self.ob.plazo.exclusivo), (LIMITE_SALDO, True))

    def test_el_vencimiento_se_registra_desde_la_medianoche_y_no_antes(self):
        antes = self.e.s.pagos.registrar_vencimiento_saldo_original(self.e.ec_id, LIMITE_SALDO - SEG)
        self.assertEqual(antes.mensaje, 'Sin vencimiento.')
        self.assertEqual(self.e.obligacion('SaldoContratoOriginal').estado, EO.PENDIENTE)
        despues = self.e.s.pagos.registrar_vencimiento_saldo_original(self.e.ec_id, LIMITE_SALDO)
        self.assertEqual(despues.mensaje, 'Saldo vencido registrado.')
        self.assertEqual(self.e.obligacion('SaldoContratoOriginal').estado, EO.VENCIDA)

    def test_un_pago_del_saldo_en_el_ultimo_segundo_es_a_tiempo_y_a_las_00_00_es_tardio(self):
        self.e.s.pagos.registrar_y_verificar_pago(self.e.ec_id, self.ob.obligacion_id, Importe(D('7000')), LIMITE_SALDO - SEG, 'S-1')
        self.assertEqual(self.e.obligacion('SaldoContratoOriginal').estado, EO.LIQUIDADA)
        self.assertFalse(self.e.ec().obligacion_vencida_sin_pago(self.ob.obligacion_id, LIMITE_SALDO + timedelta(days=1)))


class LimiteDeLaSustitucion(unittest.TestCase):
    def autorizar(self, fecha):
        s = sustitucion(ESP.PENDIENTE_AUTORIZACION, alternativas=[alternativa(CON_IMPACTO, decision=aprobada())], costo=Importe(D(800)))
        s.registrar_autorizacion(Decision('Administración', True, fecha), FECHA_EVENTO)
        return s.aprobada_despues_del_limite

    def test_autorizada_en_el_ultimo_segundo_usa_el_plazo_ordinario_y_desde_la_00_00_es_posterior_al_limite(self):
        self.assertFalse(self.autorizar(LIMITE_SALDO - SEG))
        self.assertTrue(self.autorizar(LIMITE_SALDO))
        self.assertTrue(self.autorizar(LIMITE_SALDO + timedelta(hours=1)))

    def test_la_obligacion_de_la_sustitucion_aprobada_a_tiempo_usa_el_mismo_limite_que_el_saldo(self):
        e = Escenario(); e.confirmar_contratacion()
        ob = e.ec().registrar_importe_adicional_sustitucion('OB-SP', Importe(D(500)), 'SP-1', False, FECHA_EVENTO)
        self.assertEqual((ob.plazo.vence, ob.plazo.exclusivo), (LIMITE_SALDO, True))


class Devoluciones(unittest.TestCase):
    CIERRE = datetime(2026, 11, 13, 10, 0)                  # viernes 13/11 → 16, 17, 18, 19, 20 → vence sábado 21/11 00:00

    def devolucion(self, **kw):
        return Devolucion('DV-1', 'SC-1', CP.CAMBIO, Importe(D(300)), 'Cierre', self.CIERRE, **kw)

    def test_se012_vence_a_la_medianoche_posterior_al_quinto_dia_habil(self):
        d = self.devolucion()
        self.assertEqual(d.fecha_limite, datetime(2026, 11, 21, 0, 0))
        self.assertFalse(d.vencida(d.fecha_limite - SEG))
        self.assertTrue(d.vencida(d.fecha_limite))

    def test_la_devolucion_del_anticipo_conserva_su_regla_con_la_fecha_de_referencia(self):          # decisión A-6
        d = Devolucion('DV-2', None, CP.ANTICIPO, Importe(D(1)), 'x', self.CIERRE, tipo=TipoDevolucion.ANTICIPO_CONTRATACION_CERRADA,
                       pago_id='PG-1', fecha_referencia=datetime(2026, 11, 5, 15, 0))
        self.assertEqual(d.fecha_limite, datetime(2026, 11, 13, 0, 0))                                # jue 05/11 → 6, 9, 10, 11, 12 → vie 13/11 00:00
        self.assertTrue(d.vencida(d.fecha_limite) and not d.vencida(d.fecha_limite - SEG))


class SinExtensionAPlazosNaturales(unittest.TestCase):
    def test_las_ventanas_de_24_horas_conservan_el_limite_inclusivo_y_la_hora(self):
        e = Escenario(); e.confirmar_contratacion()
        s = e.s.adicionales
        dia = FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        self.assertTrue(sa)
        plazo = PlazoPago.horas_naturales(dia, 24)
        self.assertEqual((plazo.vence, plazo.exclusivo), (dia + timedelta(hours=24), False))
        self.assertFalse(plazo.vencido(plazo.vence))                                                    # en el límite todavía está en plazo

    def test_el_cierre_por_falta_de_pago_del_servicio_adicional_sigue_inclusivo(self):
        from test_servicio_adicional_cierre_falta_pago import escenario as escenario_sa, H, estado, ESA
        e, sa, ob, dia = escenario_sa()
        self.assertFalse(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + 24 * H).exito)
        self.assertTrue(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + 24 * H + SEG).exito)
        self.assertEqual(estado(e, sa), ESA.CERRADA_FALTA_PAGO)


class PersistenciaDelLimiteExclusivo(BaseConBD):
    def test_el_limite_exclusivo_sobrevive_a_postgresql_sin_cambiar_la_base(self):
        f = Flujo(construir_persistente(motor=self.motor)).contratar()
        nuevo = construir_persistente(motor=self.motor)                                                 # contenedor nuevo: se relee de la base
        ec = nuevo.repos.estados_cuenta.obtener_por_id(f.ec_id)
        por_concepto = {o.concepto: o for o in ec.obligaciones.values()}
        self.assertEqual((por_concepto[CP.ANTICIPO].plazo.vence, por_concepto[CP.ANTICIPO].plazo.exclusivo), (LIMITE_ANTICIPO, True))
        self.assertEqual((por_concepto[CP.SALDO_CONTRATO_ORIGINAL].plazo.vence, por_concepto[CP.SALDO_CONTRATO_ORIGINAL].plazo.exclusivo),
                         (LIMITE_SALDO, True))
        self.assertTrue(por_concepto[CP.ANTICIPO].plazo.vencido(LIMITE_ANTICIPO))


if __name__ == '__main__':
    unittest.main()
