"""E-3 y E-4 — pagos parciales del anticipo y pagos adicionales posteriores a su liquidación.

Decisiones de implementación del equipo (las fuentes originales no las tratan de forma explícita: GL «anticipo», CA-019, CA-107
y CA-108 no hablan de sumar pagos; la auditoría final las registró como preguntas E-3 y E-4):

E-3  El anticipo mínimo sigue siendo el 30 % del costo del contrato, pero se puede alcanzar con varios pagos válidos del mismo
     contrato. Un pago menor al mínimo sobre un anticipo Pendiente ya no es «Importe incorrecto»: queda Registrado o Verificado
     como parcial y la obligación sigue Pendiente hasta que los pagos Verificados sumen el mínimo. No cuentan los pagos
     «Importe incorrecto» (solo históricos), los de otra obligación ni uno repetido (mismo comprobante en la misma obligación).
E-4  Con el anticipo ya Liquidado, un pago menor al 30 % se registra y verifica como adicional: no se devuelve, no se aplica al
     saldo (B-4) y no cambia la liquidación (anticipo_aplicado ≤ importe de la obligación).

Tratamiento donde las fuentes no definen la fecha efectiva (documentado, no una regla nueva): el pago se mide por la fecha en que
el Cliente lo efectuó (`Pago.fecha`, BN-009). Para liquidar la obligación cuentan todos los pagos verificados, también los tardíos
(H-10); para las 24 horas posteriores al contacto (confirmar o cerrar la contratación) solo cuentan los efectuados a más tardar
en el límite, y un pago parcial dentro de ese plazo no evita el cierre.
Ejecutar desde la raíz:  python -m unittest tests.test_anticipo_pagos_parciales_e3_e4 -v"""
import os, sys, threading, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from fastapi.testclient import TestClient                                                           # noqa: E402
from apoyo_bd import BaseConBD                                                                       # noqa: E402
from apoyo_flujo import Flujo                                                                        # noqa: E402
from apoyo_persistencia import estado_de                                                             # noqa: E402
from test_reglas_anticipo_decisiones_abc import contrato, escenario, pagar                           # noqa: E402
from test_reglas_corregidas import T0                                                                # noqa: E402
from api.main import crear_app                                                                       # noqa: E402
from domain.estado_cuenta import EstadoCuenta, Pago                                                  # noqa: E402
from domain.valores import (ConceptoPago as CP, EstadoContrato, EstadoEvento as EE, EstadoObligacionPago as EO,   # noqa: E402
                            EstadoPago as EPg, ErrorDominio, Importe)
from infrastructure.persistencia.composicion_persistente import construir_persistente                # noqa: E402
from infrastructure.persistencia.errores import ConflictoDeConcurrencia                              # noqa: E402

DIA = T0 + timedelta(days=1)


def pagos_del_anticipo(e):
    return [p for p in e.ec().pagos if p.obligacion_id == e.obligacion('Anticipo').obligacion_id]


class E3_PagosParcialesQueSumanElMinimo(unittest.TestCase):
    def test_dos_pagos_de_1500_alcanzan_el_minimo_de_3000(self):                 # ejemplo de referencia: contrato de $10,000
        e = escenario()
        r1 = pagar(e, 1500, DIA, comprobante='C-1'); e.d.despachar()
        self.assertEqual(r1.datos['estado'], EPg.VERIFICADO.value)               # parcial válido, no «importe incorrecto»
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)          # 1500 < 3000: todavía no liquida
        self.assertEqual(contrato(e).estado, EstadoContrato.FIRMADO)             # y no confirma la contratación
        self.assertFalse(e.ec().anticipo_verificado())
        r2 = pagar(e, 1500, DIA + timedelta(hours=1), comprobante='C-2'); e.d.despachar()
        self.assertEqual(r2.datos['estado'], EPg.VERIFICADO.value)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)          # 1500 + 1500 = 3000
        self.assertEqual(contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        self.assertEqual(e.ec().devoluciones, [])
        self.assertEqual((e.ec().anticipo_aplicado(), e.ec().anticipo_excedente()), (D('3000'), D('0')))

    def test_alcanzar_exactamente_el_30_por_ciento_con_tres_pagos(self):
        e = escenario()
        for i, importe in enumerate((1000, 1000, 1000)):
            pagar(e, importe, DIA + timedelta(hours=i), comprobante=f'C-{i}'); e.d.despachar()
            esperado = EO.LIQUIDADA if i == 2 else EO.PENDIENTE
            self.assertEqual(e.obligacion('Anticipo').estado, esperado, i)
        self.assertEqual(e.ec().anticipo_excedente(), D('0'))

    def test_un_importe_acumulado_insuficiente_no_liquida_ni_confirma(self):
        e = escenario()
        pagar(e, 1000, DIA, comprobante='C-1'); pagar(e, '1999.99', DIA + timedelta(hours=1), comprobante='C-2'); e.d.despachar()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)           # 2999.99 < 3000
        self.assertEqual(contrato(e).estado, EstadoContrato.FIRMADO)
        self.assertFalse(e.ec().anticipo_recibido())
        pagar(e, '0.01', DIA + timedelta(hours=2), comprobante='C-3'); e.d.despachar()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)           # el centavo faltante completa el 30 %

    def test_superar_el_30_por_ciento_con_pagos_parciales_conserva_el_excedente_sin_aplicarlo(self):     # B-3, B-4
        e = escenario()
        pagar(e, 1500, DIA, comprobante='C-1'); pagar(e, 2000, DIA + timedelta(hours=1), comprobante='C-2'); e.d.despachar()
        ec = e.ec()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertEqual((ec.anticipo_aplicado(), ec.anticipo_excedente()), (D('3000'), D('500')))
        self.assertEqual(ec.devoluciones, [])                                     # el excedente no se devuelve (B-3)
        self.assertEqual(e.obligacion('SaldoContratoOriginal').importe.cantidad, D('7000'))   # ni se aplica al saldo (B-4)

    def test_un_pago_repetido_no_se_cuenta_dos_veces(self):
        e = escenario()
        pagar(e, 1500, DIA, comprobante='C-1'); e.d.despachar()
        antes = len(e.ec().pagos)
        r = pagar(e, 1500, DIA + timedelta(minutes=5), comprobante='C-1')         # reintento con el mismo comprobante
        self.assertFalse(r.exito)
        self.assertIn('comprobante', r.mensaje)
        self.assertEqual(len(e.ec().pagos), antes)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)           # no sumó 3000
        self.assertEqual(e.ec().anticipo_recibido_verificado(), D('1500'))

    def test_el_mismo_pago_registrado_y_verificado_despues_no_suma_dos_veces(self):
        e = escenario()
        r = pagar(e, 1500, DIA, verificar=False, comprobante='C-1')               # Registrado, sin verificar
        self.assertTrue(e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], DIA + timedelta(hours=1)).exito)
        self.assertFalse(e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], DIA + timedelta(hours=2)).exito)
        self.assertEqual(e.ec().anticipo_recibido_verificado(), D('1500'))
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)

    def test_los_pagos_de_contratos_diferentes_no_se_suman(self):
        e1, e2 = escenario(), escenario()                                         # dos contratos, cada uno con su estado de cuenta
        pagar(e1, 1500, DIA, comprobante='C-1'); pagar(e2, 1500, DIA, comprobante='C-1'); e1.d.despachar(); e2.d.despachar()
        self.assertEqual(e1.obligacion('Anticipo').estado, EO.PENDIENTE)
        self.assertEqual(e2.obligacion('Anticipo').estado, EO.PENDIENTE)
        self.assertEqual(e1.ec().anticipo_recibido_verificado(), D('1500'))

    def test_un_pago_historico_con_importe_incorrecto_no_se_contabiliza(self):
        ec = EstadoCuenta('EC-H', 'CT-H', 'EV-H')
        o = ec.registrar_obligacion_anticipo('OB-A', Importe(D('10000')), T0)
        ec.pagos.append(Pago('PG-VIEJO', o.obligacion_id, Importe(D('2000')), DIA, 'C-VIEJO', EPg.IMPORTE_INCORRECTO, DIA, None))
        ec.registrar_y_verificar_pago('PG-1', o.obligacion_id, Importe(D('1000')), DIA, 'C-1', True)
        self.assertEqual(o.estado, EO.PENDIENTE)                                   # 1000 verificados; los 2000 históricos no cuentan
        self.assertEqual(ec.anticipo_recibido_verificado(), D('1000'))
        self.assertEqual([p.estado for p in ec.pagos][0], EPg.IMPORTE_INCORRECTO)  # el historial no se modifica
        ec.registrar_y_verificar_pago('PG-2', o.obligacion_id, Importe(D('2000')), DIA, 'C-2', True)
        self.assertEqual(o.estado, EO.LIQUIDADA)

    def test_un_pago_con_el_mismo_comprobante_que_uno_historico_incorrecto_si_se_acepta(self):   # la corrección es un pago nuevo
        ec = EstadoCuenta('EC-H', 'CT-H', 'EV-H')
        o = ec.registrar_obligacion_anticipo('OB-A', Importe(D('10000')), T0)
        ec.pagos.append(Pago('PG-VIEJO', o.obligacion_id, Importe(D('2000')), DIA, 'C-1', EPg.IMPORTE_INCORRECTO, DIA, None))
        ec.registrar_y_verificar_pago('PG-1', o.obligacion_id, Importe(D('3000')), DIA, 'C-1', True)
        self.assertEqual(o.estado, EO.LIQUIDADA)

class E3_Plazos(unittest.TestCase):
    def contacto(self, e):
        c = T0 + timedelta(days=6)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, c, 'Contacto', False)
        return c

    def test_los_parciales_dentro_de_las_24_horas_que_suman_el_minimo_confirman_y_evitan_el_cierre(self):
        e = escenario(); c = self.contacto(e)
        pagar(e, 1500, c + timedelta(hours=1), comprobante='C-1'); pagar(e, 1500, c + timedelta(hours=23), comprobante='C-2'); e.d.despachar()
        self.assertEqual(contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, c + timedelta(hours=31), 'Sin pago', True)
        self.assertFalse(r.exito)
        self.assertEqual(e.evento().estado, EE.EN_ORGANIZACION)

    def test_un_parcial_dentro_del_plazo_y_el_resto_despues_no_evitan_el_cierre(self):
        e = escenario(); c = self.contacto(e)
        pagar(e, 1500, c + timedelta(hours=1), comprobante='C-1')
        pagar(e, 1500, c + timedelta(hours=30), comprobante='C-2'); e.d.despachar()      # después de las 24 h: no confirma
        self.assertEqual(contrato(e).estado, EstadoContrato.FIRMADO)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)                   # pero sí liquida (H-10)
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, c + timedelta(hours=31), 'Sin pago', True)
        e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.evento().estado, EE.CERRADO_SIN_CONTRATACION)
        self.assertEqual(len(e.ec().devoluciones), 2)                                     # A-1: cada pago recibido se devuelve

    def test_un_pago_parcial_pendiente_de_verificar_no_evita_el_cierre_si_no_cubre_el_minimo(self):
        e = escenario(); c = self.contacto(e)
        pagar(e, 1500, c + timedelta(hours=2), verificar=False, comprobante='C-1')
        self.assertFalse(e.ec().anticipo_efectuado_hasta(c + timedelta(hours=24)))        # 1500 < 3000
        pagar(e, 1500, c + timedelta(hours=3), verificar=False, comprobante='C-2')
        self.assertTrue(e.ec().anticipo_efectuado_hasta(c + timedelta(hours=24)))         # efectuados a tiempo, aunque sin verificar

    def test_la_hora_exacta_de_las_24_horas_cuenta_como_a_tiempo(self):                   # límite inclusivo de las ventanas de horas
        e = escenario(); c = self.contacto(e)
        pagar(e, 1500, c + timedelta(hours=24), comprobante='C-1'); pagar(e, 1500, c + timedelta(hours=24), comprobante='C-2'); e.d.despachar()
        self.assertEqual(contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)

    def test_los_parciales_efectuados_despues_de_los_tres_dias_habiles_liquidan_pero_no_dejan_de_ser_tardios(self):   # H-10
        e = escenario()
        pagar(e, 1500, DIA, comprobante='C-1'); pagar(e, 1500, T0 + timedelta(days=9), comprobante='C-2'); e.d.despachar()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)


class E4_PagoAdicionalDespuesDeLiquidar(unittest.TestCase):
    def liquidado(self):
        e = escenario(); pagar(e, 3000, DIA, comprobante='C-1'); e.d.despachar()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        return e

    def test_un_pago_de_1000_sobre_un_anticipo_liquidado_se_verifica_como_adicional(self):
        e = self.liquidado()
        antes = e.ec()
        previo = (antes.obligaciones[e.obligacion('Anticipo').obligacion_id].estado, antes.anticipo_aplicado(), antes.anticipo_excedente(),
                  e.obligacion('SaldoContratoOriginal').importe.cantidad, len(antes.pagos), len(antes.devoluciones))
        r = pagar(e, 1000, DIA + timedelta(days=1), comprobante='C-2'); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(r.datos['estado'], EPg.VERIFICADO.value)                       # no «Importe incorrecto»
        ec = e.ec()
        despues = (e.obligacion('Anticipo').estado, ec.anticipo_aplicado(), ec.anticipo_excedente(),
                   e.obligacion('SaldoContratoOriginal').importe.cantidad, len(ec.pagos), len(ec.devoluciones))
        self.assertEqual(previo[:4], (EO.LIQUIDADA, D('3000'), D('0'), D('7000')))
        self.assertEqual(despues, (EO.LIQUIDADA, D('3000'), D('1000'), D('7000'), 2, 0))    # +1 pago, sin devolución, saldo intacto
        self.assertEqual(ec.devoluciones, [])
        self.assertEqual(ec.importe_pagado(e.obligacion('SaldoContratoOriginal').obligacion_id), D('0'))   # no se aplica al saldo

    def test_el_pago_adicional_no_modifica_retroactivamente_la_liquidacion(self):
        e = self.liquidado()
        primero = pagos_del_anticipo(e)[0]
        instantanea = (primero.estado, primero.importe, primero.verificado_en)
        pagar(e, 1000, DIA + timedelta(days=1), comprobante='C-2'); e.d.despachar()
        p = pagos_del_anticipo(e)[0]
        self.assertEqual((p.estado, p.importe, p.verificado_en), instantanea)
        self.assertEqual(contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)

    def test_el_reintento_del_pago_adicional_no_se_duplica(self):
        e = self.liquidado()
        pagar(e, 1000, DIA + timedelta(days=1), comprobante='C-2'); e.d.despachar()
        r = pagar(e, 1000, DIA + timedelta(days=1, minutes=1), comprobante='C-2')
        self.assertFalse(r.exito)
        self.assertEqual(len(e.ec().pagos), 2)
        self.assertEqual(e.ec().anticipo_excedente(), D('1000'))

    def test_el_pago_adicional_registrado_se_verifica_despues_sin_devolverse(self):
        e = self.liquidado()
        r = pagar(e, 1000, DIA + timedelta(days=1), verificar=False, comprobante='C-2')
        self.assertEqual(r.datos['estado'], EPg.REGISTRADO.value)
        self.assertTrue(e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], DIA + timedelta(days=2)).exito)
        self.assertEqual((e.ec().anticipo_excedente(), e.ec().devoluciones), (D('1000'), []))

    def test_la_diferencia_con_e3_antes_de_liquidar_el_pago_se_acumula_y_despues_es_adicional(self):
        e = escenario()
        pagar(e, 1000, DIA, comprobante='C-1'); e.d.despachar()                          # E-3: parcial, la obligación sigue Pendiente
        self.assertEqual((e.obligacion('Anticipo').estado, e.ec().anticipo_aplicado()), (EO.PENDIENTE, D('0')))
        pagar(e, 2000, DIA + timedelta(hours=1), comprobante='C-2'); e.d.despachar()      # completa 3000
        self.assertEqual((e.obligacion('Anticipo').estado, e.ec().anticipo_aplicado()), (EO.LIQUIDADA, D('3000')))
        pagar(e, 500, DIA + timedelta(hours=2), comprobante='C-3'); e.d.despachar()        # E-4: adicional
        self.assertEqual((e.ec().anticipo_aplicado(), e.ec().anticipo_excedente()), (D('3000'), D('500')))

    def test_tras_el_cierre_de_la_contratacion_el_pago_sigue_la_decision_a_y_se_devuelve(self):    # A-1, A-3 (sin cambios)
        e = escenario()
        c = T0 + timedelta(days=6)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, c, 'Contacto', False)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, c + timedelta(hours=31), 'Sin pago', True); e.d.despachar()
        pagar(e, 1000, c + timedelta(hours=40), comprobante='C-1'); e.d.despachar()
        (d,) = e.ec().devoluciones
        self.assertEqual(d.importe.cantidad, D('1000'))


class PersistenciaYHttp(BaseConBD):
    """Los pagos parciales sobreviven a PostgreSQL y a un contenedor nuevo; la ruta HTTP aplica E-3 y E-4."""

    def setUp(self):
        super().setUp()
        self.app = construir_persistente(motor=self.motor)
        self.http = TestClient(crear_app(lambda: self.app))

    def contratar_sin_pagar(self):
        f = Flujo(self.app)
        f.contratar(confirmar=False)
        return f

    def test_parciales_http_en_postgresql_se_suman_y_el_adicional_no_se_devuelve(self):
        f = self.contratar_sin_pagar()
        ob = next(o for o in f.ec().obligaciones.values() if o.concepto == CP.ANTICIPO)
        url = f'/estados-cuenta/{f.ec_id}/pagos'

        def pagar_http(importe, comprobante):
            r = self.http.post(url, json={'obligacion_id': ob.obligacion_id, 'importe': importe, 'fecha': DIA.isoformat(), 'comprobante': comprobante})
            self.assertEqual(r.status_code, 201, r.text)
            return r.json()['datos']

        self.assertEqual(pagar_http('1500.00', 'H-1')['estado'], 'Verificado')
        self.assertEqual(self.app.repos.estados_cuenta.obtener_por_id(f.ec_id).obligaciones[ob.obligacion_id].estado, EO.PENDIENTE)
        pagar_http('1500.00', 'H-2')
        reabierto = construir_persistente(motor=self.motor)                              # contenedor nuevo: lo guardado sobrevive
        ec = reabierto.repos.estados_cuenta.obtener_por_id(f.ec_id)
        self.assertEqual(ec.obligaciones[ob.obligacion_id].estado, EO.LIQUIDADA)
        self.assertEqual(sorted(str(p.importe.cantidad) for p in ec.pagos if p.obligacion_id == ob.obligacion_id), ['1500.00', '1500.00'])
        pagar_http('1000.00', 'H-3')                                                      # E-4
        r = self.http.post(url, json={'obligacion_id': ob.obligacion_id, 'importe': '1000.00', 'fecha': DIA.isoformat(), 'comprobante': 'H-3'})
        self.assertEqual(r.status_code, 422, r.text)                                      # el reintento se rechaza
        ec = construir_persistente(motor=self.motor).repos.estados_cuenta.obtener_por_id(f.ec_id)
        self.assertEqual((ec.anticipo_aplicado(), ec.anticipo_excedente(), ec.devoluciones), (D('3000.00'), D('1000.00'), []))
        self.assertEqual(self.contar('pago'), 3)
        registros = self.app.outbox.registros()                                           # Outbox: un hecho por pago verificado, sin duplicar
        tipos = sorted(r.tipo_evento for r in registros)
        self.assertEqual(tipos.count('PagoVerificado'), 3)                                # el reintento rechazado no emitió nada
        self.assertEqual(tipos.count('ContratacionConfirmada'), 0)                        # sin política comunicada no se confirma
        self.assertEqual([r for r in registros if r.estado != 'Procesado'], [])

    def test_dos_registros_simultaneos_del_mismo_pago_dejan_uno_solo(self):
        f = self.contratar_sin_pagar()
        ob = next(o for o in f.ec().obligaciones.values() if o.concepto == CP.ANTICIPO)
        repo = self.app.repos.estados_cuenta
        barrera = threading.Barrier(2, timeout=15)
        resultados = {}

        def escritor(nombre):
            motor_propio = construir_persistente(motor=self.motor)
            try:
                ec = motor_propio.repos.estados_cuenta.obtener_por_id(f.ec_id)
                barrera.wait()
                motor_propio.uow.iniciar(); motor_propio.uow.registrar(ec)
                ec.registrar_y_verificar_pago(f'PG-{nombre}', ob.obligacion_id, Importe(D('1500')), DIA, 'MISMO', True)
                motor_propio.repos.estados_cuenta.guardar(ec)
                motor_propio.uow.confirmar()
                resultados[nombre] = 'ok'
            except ConflictoDeConcurrencia:
                motor_propio.uow.revertir(); resultados[nombre] = 'conflicto'
            except ErrorDominio:
                motor_propio.uow.revertir(); resultados[nombre] = 'duplicado'

        hilos = [threading.Thread(target=escritor, args=(n,)) for n in ('X', 'Y')]
        [h.start() for h in hilos]; [h.join(30) for h in hilos]
        self.assertEqual(sorted(resultados.values()), ['conflicto', 'ok'], resultados)
        pagos = [p for p in repo.obtener_por_id(f.ec_id).pagos if p.obligacion_id == ob.obligacion_id]
        self.assertEqual(len(pagos), 1)                                                   # se contó una sola vez
        reintento = repo.obtener_por_id(f.ec_id)
        with self.assertRaises(ErrorDominio):                                             # y el reintento posterior es un duplicado
            reintento.registrar_y_verificar_pago('PG-Z', ob.obligacion_id, Importe(D('1500')), DIA, 'MISMO', True)


if __name__ == '__main__':
    unittest.main()
