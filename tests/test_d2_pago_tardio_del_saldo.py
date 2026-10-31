"""D-2 — un pago del saldo efectuado después de su fecha límite no lo liquida directamente (C-06 / ND-29, GL-049, CA-113, BN-005).

Hallazgo del 28/10/2026: con la obligación del saldo todavía `Pendiente` (vencimiento sin registrar), un pago con fecha posterior al
límite la dejaba `Liquidada`. El cierre de alcance (§8, brecha 3) ya lo registraba como brecha. Reglas que fijan estas pruebas:
  * la fecha efectiva del pago decide el plazo (BN-005, GL-046); registro y verificación posteriores no lo cambian;
  * un pago posterior al límite se registra y se verifica, cuenta para la regularización, pero no liquida el saldo;
  * el saldo pagado tarde puede registrarse como vencido (el vencimiento ya no depende de que falte dinero);
  * el anticipo (H-10) y el costo de una sustitución concretada tarde (GL-012) conservan su excepción;
  * la consulta informa «si el plazo ya venció» (CA-023).
Calendario: evento viernes 20/11/2026 18:00 → límite del saldo mié 18/11/2026 00:00 (exclusivo, E-1).
Ejecutar desde la raíz:  python -m unittest tests.test_d2_pago_tardio_del_saldo -v"""
import os, sys, unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient                                          # noqa: E402
from apoyo_bd import BaseConBD                                                      # noqa: E402
from apoyo_flujo import Flujo                                                       # noqa: E402
from api.dependencias import obtener_reloj                                          # noqa: E402
from api.main import crear_app                                                      # noqa: E402
from domain.valores import EstadoObligacionPago as EO, EstadoPago as EP, Importe     # noqa: E402
from infrastructure.composicion import construir                                    # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente   # noqa: E402

SEG = timedelta(seconds=1)
LIMITE = datetime(2026, 11, 18, 0, 0)
ANTES = LIMITE - SEG                                   # último segundo del plazo
TARDE = LIMITE + timedelta(hours=9)                    # miércoles 18/11 09:00


class PagoTardioDelSaldo:
    """Mixin. Requiere `crear_contenedor()`."""

    def preparar(self):
        self.app = self.crear_contenedor()
        self.f = Flujo(self.app).contratar()
        self.saldo = self.f.obligacion('SaldoContratoOriginal')
        self.assertEqual(self.saldo.plazo.vence, LIMITE)

    def pagar(self, importe, fecha, comprobante, registrado_en=None, verificar=True):
        r = self.app.servicios.pagos.registrar_y_verificar_pago(
            self.f.ec_id, self.saldo.obligacion_id, Importe(D(importe)), fecha, comprobante,
            registrado_en=registrado_en or fecha, verificar_ahora=verificar)
        self.assertTrue(r.exito, r.mensaje)
        self.app.despachador.despachar()
        return r

    def estado_saldo(self):
        return self.f.obligacion('SaldoContratoOriginal').estado

    def estado_pago(self, r):
        return next(p for p in self.f.ec().pagos if p.pago_id == r.datos['pago_id']).estado

    # ---- el defecto: pago completo con fecha posterior al límite
    def test_un_pago_completo_con_fecha_posterior_al_limite_no_liquida_el_saldo(self):
        r = self.pagar('7000', TARDE, 'S-TARDE')
        self.assertEqual(self.estado_pago(r), EP.VERIFICADO)           # se registra y se verifica
        self.assertEqual(self.estado_saldo(), EO.PENDIENTE)            # pero no liquida (C-06, CA-113)
        self.assertNotIn('SaldoContratoOriginal', [p['concepto'] for p in self.pendientes_como_liquidadas()])

    def test_el_pago_a_las_00_00_exactas_del_limite_es_tardio_y_en_el_ultimo_segundo_es_a_tiempo(self):    # E-1
        self.pagar('7000', LIMITE, 'S-00')
        self.assertEqual(self.estado_saldo(), EO.PENDIENTE)

    def test_un_pago_completo_en_el_ultimo_segundo_del_plazo_liquida(self):
        self.pagar('7000', ANTES, 'S-A-TIEMPO')
        self.assertEqual(self.estado_saldo(), EO.LIQUIDADA)

    def test_un_pago_a_tiempo_registrado_y_verificado_despues_sigue_liquidando(self):         # BN-005: la fecha del pago manda
        r = self.pagar('7000', ANTES, 'S-A-TIEMPO-2', registrado_en=TARDE + timedelta(days=1), verificar=False)
        self.assertEqual(self.estado_saldo(), EO.PENDIENTE)
        v = self.app.servicios.pagos.verificar_pago_registrado(self.f.ec_id, r.datos['pago_id'], TARDE + timedelta(days=2))
        self.assertTrue(v.exito, v.mensaje)
        self.assertEqual(self.estado_saldo(), EO.LIQUIDADA)

    def test_solo_cuenta_lo_pagado_dentro_del_plazo_aunque_el_total_cubra_el_saldo(self):
        self.pagar('3000', ANTES, 'S-P1')
        self.pagar('4000', TARDE, 'S-P2')
        self.assertEqual(self.estado_saldo(), EO.PENDIENTE)            # 3000 a tiempo + 4000 tarde: no liquida

    def test_un_pago_tardio_verificado_antes_que_uno_a_tiempo_tampoco_hace_que_este_liquide_de_mas(self):
        self.pagar('4000', TARDE, 'S-T')                               # tardío, verificado primero
        self.pagar('3000', ANTES, 'S-A')                               # a tiempo, verificado después: 3000 en plazo < 7000
        self.assertEqual(self.estado_saldo(), EO.PENDIENTE)

    # ---- el saldo pagado tarde puede registrarse como vencido
    def test_un_saldo_pagado_tarde_puede_registrarse_como_vencido(self):
        self.pagar('7000', TARDE, 'S-TARDE')
        r = self.app.servicios.pagos.registrar_vencimiento_saldo_original(self.f.ec_id, TARDE)
        self.assertEqual(r.mensaje, 'Saldo vencido registrado.')
        self.assertEqual(self.estado_saldo(), EO.VENCIDA)              # «queda vencido» (C-06) y el pago cuenta para la regularización

    def test_un_pago_a_tiempo_sin_verificar_impide_registrar_el_vencimiento(self):             # conservado
        self.pagar('7000', ANTES, 'S-SV', verificar=False)
        self.assertEqual(self.app.servicios.pagos.registrar_vencimiento_saldo_original(self.f.ec_id, TARDE).mensaje, 'Sin vencimiento.')

    def test_con_el_saldo_ya_vencido_un_pago_tardio_no_lo_liquida(self):                        # conservado (CA-113)
        self.assertEqual(self.app.servicios.pagos.registrar_vencimiento_saldo_original(self.f.ec_id, TARDE).mensaje, 'Saldo vencido registrado.')
        self.pagar('7000', TARDE + timedelta(hours=1), 'S-V')
        self.assertEqual(self.estado_saldo(), EO.VENCIDA)

    # ---- excepciones que se conservan
    def test_el_anticipo_pagado_tarde_sigue_liquidando_por_h10(self):
        e = Flujo(self.app).contratar(confirmar=False)
        ob = e.obligacion('Anticipo')
        tardio = ob.plazo.vence + timedelta(days=1)
        r = self.app.servicios.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('3000')), tardio, 'A-TARDE', registrado_en=tardio)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)

    # ---- CA-023: la consulta informa si el plazo ya venció
    def test_la_consulta_de_pagos_informa_si_el_plazo_del_saldo_ya_vencio(self):
        cliente = self.cliente(TARDE)
        saldo = cliente.get(f'/eventos/{self.f.evento_id}/pagos').json()['estadosCuenta'][0]['saldoContratoOriginal']
        self.assertEqual((saldo['estado'], saldo['plazoVencido']), ('Pendiente', True))     # límite superado, sin registrar el vencimiento
        antes = self.cliente(ANTES).get(f'/eventos/{self.f.evento_id}/pagos').json()['estadosCuenta'][0]['saldoContratoOriginal']
        self.assertEqual((antes['estado'], antes['plazoVencido']), ('Pendiente', False))
        ec = cliente.get(f'/eventos/{self.f.evento_id}/pagos').json()['estadosCuenta'][0]
        self.assertFalse(ec['anticipo']['plazoVencido'])                                    # el anticipo ya está liquidado

    def cliente(self, ahora):
        app = crear_app(lambda: self.app)
        app.dependency_overrides[obtener_reloj] = lambda: (lambda: ahora)
        return TestClient(app)

    def pendientes_como_liquidadas(self):
        return [] if self.estado_saldo() != EO.LIQUIDADA else [{'concepto': 'SaldoContratoOriginal'}]


class BloqueoPorSaldoVencidoDeHecho:
    """GL-049, SE-006, BN-003/BN-005: mientras exista un saldo vencido no se tramitan nuevas solicitudes. «Vencido» es un hecho: el plazo
    de liquidación terminó sin que el pago efectuado dentro de él cubra el saldo; no depende de que `registrar_vencimiento_saldo` ya
    se haya ejecutado (verificación del 28/10/2026). Mixin: requiere `crear_contenedor()`."""

    def preparar_bloqueo(self):
        self.app = self.crear_contenedor()
        self.f = Flujo(self.app).contratar()
        self.saldo = self.f.obligacion('SaldoContratoOriginal')

    def pagar(self, importe, fecha, comprobante, verificar=True):
        r = self.app.servicios.pagos.registrar_y_verificar_pago(self.f.ec_id, self.saldo.obligacion_id, Importe(D(importe)), fecha, comprobante,
                                                               registrado_en=fecha, verificar_ahora=verificar)
        self.assertTrue(r.exito, r.mensaje)
        return r

    def cambio(self, ahora):
        r = self.app.servicios.cambios.registrar_solicitud_cambio(self.f.evento_id, self.f.contrato_id, 'Cambio de menú', Importe(D('0')), ahora)
        self.assertTrue(r.exito, r.mensaje)
        return r.datos['estado']

    # ---- a nivel de dominio
    def test_el_saldo_esta_vencido_de_hecho_al_superar_el_limite_sin_pagos_en_plazo(self):
        ec = self.f.ec()
        self.assertFalse(ec.saldo_vencido_en(LIMITE - SEG))
        self.assertTrue(ec.saldo_vencido_en(LIMITE))                     # límite exclusivo: a las 00:00 ya venció
        self.assertEqual(self.f.obligacion('SaldoContratoOriginal').estado, EO.PENDIENTE)   # sin registrar el vencimiento

    def test_los_pagos_dentro_del_plazo_que_no_cubren_el_saldo_no_evitan_el_vencimiento_de_hecho(self):
        self.pagar('2000', ANTES, 'S-PARCIAL')
        self.assertTrue(self.f.ec().saldo_vencido_en(TARDE))

    def test_un_pago_tardio_completo_no_quita_el_vencimiento_de_hecho(self):                   # C-06 / CA-113
        self.pagar('7000', TARDE, 'S-TARDE')
        self.assertTrue(self.f.ec().saldo_vencido_en(TARDE))

    def test_un_saldo_liquidado_a_tiempo_no_esta_vencido(self):
        self.pagar('7000', ANTES, 'S-OK')
        self.assertFalse(self.f.ec().saldo_vencido_en(TARDE))

    def test_un_pago_a_tiempo_pendiente_de_verificacion_no_lo_vence(self):                    # la demora de Administración no es falta de pago
        self.pagar('7000', ANTES, 'S-SV', verificar=False)
        self.assertFalse(self.f.ec().saldo_vencido_en(TARDE))

    # ---- en el servicio: una solicitud nueva se detiene
    def test_una_solicitud_nueva_se_detiene_si_el_saldo_esta_vencido_aunque_no_se_haya_registrado_el_vencimiento(self):
        self.assertEqual(self.cambio(TARDE), 'Detenida por saldo vencido')
        self.assertEqual(self.f.obligacion('SaldoContratoOriginal').estado, EO.PENDIENTE)       # el estado no cambió

    def test_con_el_pago_a_tiempo_parcial_la_solicitud_tambien_se_detiene(self):
        self.pagar('2000', ANTES, 'S-PARCIAL')
        self.assertEqual(self.cambio(TARDE), 'Detenida por saldo vencido')

    def test_antes_del_limite_la_solicitud_se_registra(self):
        self.assertEqual(self.cambio(ANTES), 'Registrada')

    def test_con_el_saldo_liquidado_a_tiempo_la_solicitud_se_registra(self):
        self.pagar('7000', ANTES, 'S-OK')
        self.assertEqual(self.cambio(TARDE), 'Registrada')

    def test_con_el_saldo_vencido_registrado_la_solicitud_sigue_deteniendose(self):            # conservado
        self.app.servicios.pagos.registrar_vencimiento_saldo_original(self.f.ec_id, TARDE)
        self.assertEqual(self.f.obligacion('SaldoContratoOriginal').estado, EO.VENCIDA)
        self.assertEqual(self.cambio(TARDE), 'Detenida por saldo vencido')


class BloqueoEnMemoria(BloqueoPorSaldoVencidoDeHecho, unittest.TestCase):
    def setUp(self):
        self.preparar_bloqueo()

    def crear_contenedor(self):
        return construir()


class BloqueoEnPostgreSQL(BloqueoPorSaldoVencidoDeHecho, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        self.preparar_bloqueo()

    def crear_contenedor(self):
        return construir_persistente(motor=self.motor)


class EnMemoria(PagoTardioDelSaldo, unittest.TestCase):
    def setUp(self):
        self.preparar()

    def crear_contenedor(self):
        return construir()


class EnPostgreSQL(PagoTardioDelSaldo, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        self.preparar()

    def crear_contenedor(self):
        return construir_persistente(motor=self.motor)


if __name__ == '__main__':
    unittest.main()
