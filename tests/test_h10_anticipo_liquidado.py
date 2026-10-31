"""H-10: un anticipo correcto y verificado deja su obligación Liquidada aunque se haya efectuado tarde.

Reglas aprobadas: BN-009 y SE-010 (el anticipo es el 30 %; si no se recibe en los tres días hábiles, el Coordinador
contacta al Cliente y desde ese contacto corren 24 horas naturales; la contratación se confirma con el anticipo
registrado y verificado), CA-019, CA-020, CA-021 y CA-026 (cada concepto con su importe y estado de pago).

Solo se corrige el estado de la obligación. El flujo de la contratación no cambia: Contrato sigue decidiendo con el
pago efectuado hasta las 24 horas del contacto (CA-021). Quedan PENDIENTES y no se prueban como reglas: qué ocurre con
el dinero de un anticipo efectuado después de esas 24 horas cuando se cierra la contratación, y el plazo para corregir un
importe incorrecto.
Ejecutar desde la raíz:  python -m unittest tests.test_h10_anticipo_liquidado -v"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, T0                                                     # noqa: E402
from apoyo_maquina_estados_estado_cuenta import Constructor, CAMBIO_TARDIO                          # noqa: E402
from domain.valores import (EstadoContrato, EstadoEvento as EE, EstadoObligacionPago as EO,          # noqa: E402
                            EstadoPago as EPg, Importe, TipoDevolucion, ConceptoPago)

ANTICIPO = Importe(D('3000.00'))                  # 30 % de 10 000 (CONTENIDO del escenario)
LIMITE_3_DIAS = datetime(2026, 10, 7, 0, 0)       # firma jue 01/10 10:00 → tercer día hábil: mar 06/10; límite exclusivo mié 07/10 00:00 (E-1)
TARDIO = LIMITE_3_DIAS + timedelta(days=2)


def escenario_con_politica():
    e = Escenario()
    e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
    return e


class AnticipoTardioAntesDelContacto(unittest.TestCase):
    def test_queda_liquidado_y_la_contratacion_se_confirma(self):                       # BN-009, CA-019, CA-026
        e = escenario_con_politica()
        ob = e.obligacion('Anticipo')
        self.assertEqual(ob.plazo.vence, LIMITE_3_DIAS)
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, ANTICIPO, TARDIO, 'C'); e.d.despachar()
        self.assertTrue(r.exito)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertTrue(e.ec().obligacion_liquidada(ob.obligacion_id))
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        self.assertEqual(e.evento().estado, EE.EN_ORGANIZACION)                 # regresión: confirmación como antes

    def test_verificado_despues_de_registrado_tambien_queda_liquidado(self):           # CA-018, GL-046, GL-052
        e = escenario_con_politica(); ob = e.obligacion('Anticipo')
        pid = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, ANTICIPO, TARDIO, 'C',
                                                   verificar_ahora=False).datos['pago_id']
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)       # registrado ≠ verificado
        self.assertTrue(e.s.pagos.verificar_pago_registrado(e.ec_id, pid, TARDIO + timedelta(days=1)).exito)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)

    def test_ya_no_figura_como_vencido_sin_pago(self):                                  # CA-026 (consulta de pagos)
        e = escenario_con_politica(); ob = e.obligacion('Anticipo')
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, ANTICIPO, TARDIO, 'C'); e.d.despachar()
        self.assertFalse(e.ec().obligacion_vencida_sin_pago(ob.obligacion_id, TARDIO + timedelta(days=1)))


class FlujoDeContratacionSinCambios(unittest.TestCase):
    def test_a_tiempo_queda_liquidado(self):                                            # regresión: CA-018
        e = escenario_con_politica(); ob = e.obligacion('Anticipo')
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, ANTICIPO, T0 + timedelta(days=1), 'C'); e.d.despachar()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)

    def test_pago_parcial_no_liquida(self):                                              # CA-019; E-3: ya no es «importe incorrecto»
        e = escenario_con_politica(); ob = e.obligacion('Anticipo')
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D(1000)), TARDIO, 'C'); e.d.despachar()
        self.assertEqual(r.datos['estado'], EPg.VERIFICADO.value)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.FIRMADO)

    def test_pago_despues_de_las_24_horas_del_contacto_no_confirma_y_el_cierre_procede(self):   # CA-021 (regresión)
        """La obligación refleja que el pago se recibió y verificó; Contrato no confirma porque el pago se efectuó
        después de las 24 horas y el cierre sin contratación sigue procediendo. No se crea ninguna devolución: el
        destino de ese dinero es una decisión pendiente (H-10)."""
        e = escenario_con_politica()
        contacto = T0 + timedelta(days=6)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
        ob = e.obligacion('Anticipo')
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, ANTICIPO, contacto + timedelta(hours=30), 'C')
        e.d.despachar()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.FIRMADO)
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=31), 'Sin pago', True)
        e.d.despachar()
        self.assertTrue(r.exito)
        self.assertEqual(e.evento().estado, EE.CERRADO_SIN_CONTRATACION)
        # Decisión A (A-1, C-04; T-48): el anticipo Liquidado conserva ese estado y se devuelve lo recibido, una sola vez.
        self.assertEqual([(d.tipo, d.importe, d.concepto) for d in e.ec().devoluciones],
                         [(TipoDevolucion.ANTICIPO_CONTRATACION_CERRADA, ANTICIPO, ConceptoPago.ANTICIPO)])
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)

    def test_pago_dentro_de_las_24_horas_verificado_despues_confirma(self):              # CA-021 (regresión)
        e = escenario_con_politica()
        contacto = T0 + timedelta(days=6)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
        ob = e.obligacion('Anticipo')
        pid = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, ANTICIPO, contacto + timedelta(hours=20), 'C',
                                                   verificar_ahora=False).datos['pago_id']
        self.assertFalse(e.s.contratacion.dar_seguimiento_anticipo_pendiente(
            e.contrato_id, contacto + timedelta(hours=26), 'Sin pago', True).exito)
        e.s.pagos.verificar_pago_registrado(e.ec_id, pid, contacto + timedelta(hours=40)); e.d.despachar()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.CONTRATACION_CONFIRMADA)


class OtrosConceptosSinCambios(unittest.TestCase):
    def test_el_pago_tardio_de_un_cambio_sigue_sin_liquidar(self):                       # BN-003, CA-067 (regresión)
        c = Constructor().anticipo().saldo().cambio().pagar('OB-C', 300, CAMBIO_TARDIO)
        self.assertEqual(c.ec.obligaciones['OB-C'].estado, EO.PENDIENTE)


if __name__ == '__main__':
    unittest.main()
