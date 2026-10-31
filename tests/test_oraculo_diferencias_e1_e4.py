"""Garantías de la validación del oráculo histórico por resultados esperados derivados de las reglas.

La comparación principal está en `test_estado_cuenta_maquina_estados.ConservacionDelComportamiento.test_resultados_identicos`: cada una de
las 1203 claves del oráculo (inmutable) debe coincidir con su esperado = oráculo + cambios ordenados por E-1, H-10 y E-3/E-4
(`apoyo_esperados_oraculo.py`, sin código de producción). Aquí se comprueba que esa validación es rigurosa:
  1. el oráculo no cambió y los recuentos por regla son exactos (con los identificadores de las claves combinadas);
  2. el calendario de referencia de E-1 coincide con el del dominio en dos años de fechas, pero es una implementación distinta;
  3. una diferencia inesperada se DETECTA: se prueba alterando una copia del resultado actual y perturbando el dominio a propósito.
Ejecutar desde la raíz:  python -m unittest tests.test_oraculo_diferencias_e1_e4 -v"""
import copy
import hashlib
import json
import os
import sys
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import apoyo_esperados_oraculo as R                                                                  # noqa: E402
import apoyo_maquina_estados_estado_cuenta as A                                                      # noqa: E402
from domain import estado_cuenta as dominio_ec, valores                                                        # noqa: E402
from domain.valores import limite_exclusivo_dias_habiles, limite_exclusivo_dias_habiles_antes         # noqa: E402

COMBINADAS = {'anticipo_importe_incorrecto | pagar(OB-A, 3000, tardio)',
              'anticipo_tardio_verificado | pagar(OB-A, 1000, importe_incorrecto)'}


def capturar():
    return json.loads(json.dumps(A.capturar_comportamiento_estado_cuenta(), ensure_ascii=False))


class RecuentoPorRegla(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(A.RUTA_REFERENCIA_ESTADO_CUENTA, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.por_clave = {k: R.esperado(k, v) for k, v in cls.referencia.items()}

    def test_el_oraculo_no_se_modifico(self):
        with open(A.RUTA_REFERENCIA_ESTADO_CUENTA, 'rb') as f:
            self.assertTrue(hashlib.sha256(f.read()).hexdigest().startswith('d98b4cff85db'))
        self.assertEqual(len(self.referencia), 1203)

    def test_recuento_exacto_por_combinacion_de_reglas(self):
        combos = {}
        for k, (_, reglas) in self.por_clave.items():
            combos.setdefault(tuple(sorted(reglas)), []).append(k)
        self.assertEqual({c: len(v) for c, v in combos.items()},
                         {('E-1',): 1046, ('D-2', 'E-1'): 48, ('E-1', 'E-3/E-4'): 67, ('E-1', 'E-3/E-4', 'H-10'): 2, ('E-1', 'H-10'): 40})
        self.assertEqual(set(combos[('E-1', 'E-3/E-4', 'H-10')]), COMBINADAS)                         # las dos claves que combinan reglas

    def test_cada_regla_toca_solo_lo_que_declara(self):
        """Una clave afectada solo por E-1 difiere del oráculo únicamente en el vencimiento de los plazos en días hábiles."""
        for k, (esperado, reglas) in self.por_clave.items():
            if reglas != {'E-1'}:
                continue
            ref = self.referencia[k]
            esp = copy.deepcopy(esperado)
            for ob_id, datos in esp['obligaciones'].items():
                datos[2] = ref['obligaciones'][ob_id][2] if datos[2] else None
            self.assertEqual(esp, ref, k)

    def test_los_pagos_no_afectados_conservan_su_estado(self):
        for k, (esperado, reglas) in self.por_clave.items():
            if 'E-3/E-4' not in reglas:
                self.assertEqual(esperado['pagos'], self.referencia[k]['pagos'], k)
                self.assertEqual(esperado['devoluciones'], self.referencia[k]['devoluciones'], k)
                self.assertEqual(esperado['eventos'], self.referencia[k]['eventos'], k)


class CalendarioDeReferenciaIndependiente(unittest.TestCase):
    def test_coincide_con_el_del_dominio_en_dos_anios_pero_es_otra_implementacion(self):
        inicio = date(2026, 1, 1)
        for i in range(731):
            d = inicio + timedelta(days=i)
            dt = datetime.combine(d, datetime.min.time()) + timedelta(hours=10)
            self.assertEqual(R.limite_gl060('ANTICIPO', dt), limite_exclusivo_dias_habiles(dt, 3), d)
            self.assertEqual(R.limite_gl060('SALDO_CONTRATO_ORIGINAL', dt), limite_exclusivo_dias_habiles_antes(dt, 3), d)
        import inspect
        self.assertNotIn('while', inspect.getsource(R.dia_habil_posterior))                              # fórmula cerrada, sin el bucle del dominio
        self.assertNotIn('while', inspect.getsource(R.dia_habil_anterior))

    def test_casos_conocidos_de_gl060(self):
        self.assertEqual(R.limite_gl060('ANTICIPO', datetime(2026, 10, 1, 10, 0)), datetime(2026, 10, 7, 0, 0))             # firma jueves
        self.assertEqual(R.limite_gl060('SALDO_CONTRATO_ORIGINAL', datetime(2026, 11, 20, 18, 0)), datetime(2026, 11, 18, 0, 0))   # evento viernes
        self.assertEqual(R.limite_gl060('SALDO_CONTRATO_ORIGINAL', datetime(2026, 11, 23, 18, 0)), datetime(2026, 11, 19, 0, 0))   # evento lunes
        self.assertEqual(R.limite_gl060('ANTICIPO', datetime(2026, 11, 14, 9, 0)), datetime(2026, 11, 19, 0, 0))            # firma sábado


class UnaDiferenciaInesperadaSeDetecta(unittest.TestCase):
    """Pruebas controladas: el esperado debe rechazar cualquier desviación, aun pequeña."""

    @classmethod
    def setUpClass(cls):
        with open(A.RUTA_REFERENCIA_ESTADO_CUENTA, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = capturar()

    def esperado(self, clave):
        return R.esperado(clave, self.referencia[clave])[0]

    def test_el_resultado_actual_coincide_en_todas_las_claves(self):
        self.assertEqual([k for k in self.referencia if self.actual[k] != self.esperado(k)], [])

    def test_alterar_una_copia_del_resultado_actual_deja_de_coincidir(self):
        base = 'saldo_pendiente | pagar(OB-A, 1000, importe_incorrecto)'                               # E-4
        alteraciones = {
            'estado de la obligación': lambda r: r['obligaciones']['OB-A'].__setitem__(4, 'PENDIENTE'),
            'estado del pago': lambda r: r['pagos'][-1].__setitem__(5, 'IMPORTE_INCORRECTO'),
            'importe acumulado': lambda r: r['consultas'].__setitem__('pagos_realizados', '3000'),
            'evento de dominio': lambda r: r['eventos'].clear(),
            'devolución': lambda r: r['devoluciones'].append(['DV-X']),
            'saldo': lambda r: r['obligaciones']['OB-S'].__setitem__(1, '6999'),
            'plazo (un segundo)': lambda r: r['obligaciones']['OB-S'][2].__setitem__(1, '2026-11-18T00:00:01'),
        }
        self.assertEqual(self.actual[base], self.esperado(base))
        for nombre, alterar in alteraciones.items():
            with self.subTest(alteracion=nombre):
                copia = copy.deepcopy(self.actual[base])
                alterar(copia)
                self.assertNotEqual(copia, self.esperado(base))

    def test_alterar_una_clave_sin_regla_de_pagos_tambien_se_detecta(self):
        clave = 'saldo_liquidado | registrar_vencimiento_saldo(antes_limite)'
        copia = copy.deepcopy(self.actual[clave])
        copia['obligaciones']['OB-S'][4] = 'VENCIDA'
        self.assertNotEqual(copia, self.esperado(clave))
        self.assertEqual(self.actual[clave]['pagos'], self.referencia[clave]['pagos'])                  # y su resto es idéntico al oráculo

    def test_perturbar_el_limite_de_e1_en_el_dominio_rompe_muchas_claves(self):
        def una_hora_despues(referencia, dias):
            return limite_exclusivo_dias_habiles(referencia, dias) + timedelta(hours=1)
        with mock.patch.object(valores, 'limite_exclusivo_dias_habiles', una_hora_despues):
            rotas = [k for k, v in capturar().items() if v != self.esperado(k)]
        self.assertEqual(len(rotas), 1203)                                                              # todas llevan el plazo del anticipo

    def test_perturbar_la_suma_de_parciales_del_dominio_se_detecta(self):
        with mock.patch.object(dominio_ec.EstadoCuenta, 'anticipo_recibido', lambda self: True):
            rotas = [k for k, v in capturar().items() if v != self.esperado(k)]
        self.assertGreaterEqual(len(rotas), 1)
        self.assertTrue(set(rotas) <= {k for k in self.referencia if R.partir(k)[0] in ('anticipo_pendiente', 'anticipo_importe_incorrecto')
                                       or R.partir(k)[1] == R.OPERACION_PARCIAL})

    def test_perturbar_la_liquidacion_h10_se_detecta(self):
        original = dominio_ec.EstadoCuenta._destinos_verificacion

        def sin_h10(self_, o, p):
            destino_pago, destino_obligacion = original(self_, o, p)
            if o.concepto == dominio_ec.CP.ANTICIPO and o.plazo is not None and o.plazo.vencido(p.fecha):
                destino_obligacion = None                                        # vuelve el comportamiento anterior a H-10
            return destino_pago, destino_obligacion
        with mock.patch.object(dominio_ec.EstadoCuenta, '_destinos_verificacion', sin_h10):
            rotas = [k for k, v in capturar().items() if v != self.esperado(k)]
        self.assertGreaterEqual(len(rotas), 40)


if __name__ == '__main__':
    unittest.main()
