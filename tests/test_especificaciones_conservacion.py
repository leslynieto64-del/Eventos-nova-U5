"""Etapa E2 — conservación del comportamiento anterior y límites de la etapa.

La referencia `referencias/comportamiento_reglas_v8_e1.json` se generó con `capturar_comportamiento()` sobre el código
de v8 + E1, antes de introducir Specification: 169 combinaciones de entradas con sus estados, pendientes, motivos y
Domain Events. El código actual debe producir exactamente lo mismo."""
import ast
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_especificaciones import capturar_comportamiento, RUTA_REFERENCIA   # noqa: E402

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


class ConservacionDelComportamiento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = json.loads(json.dumps(capturar_comportamiento(), ensure_ascii=False))

    def test_la_referencia_cubre_todas_las_reglas(self):
        self.assertEqual({k: len(v) for k, v in self.referencia.items()},
                         {'contratacion': 64, 'cargo_tardio': 11, 'viabilidad_cambio': 32, 'temporal_cambio': 2,
                          'temporal_adicional': 28, 'regularizacion': 16, 'tiene_impacto': 8, 'sustitucion': 8})

    def test_resultados_identicos_a_v8_e1(self):
        for regla in self.referencia:
            with self.subTest(regla=regla):
                self.assertEqual(self.actual[regla], self.referencia[regla])


class LimitesDeLaEtapa(unittest.TestCase):
    def _texto(self, patron):
        textos = {}
        for f in glob.glob(os.path.join(RAIZ, patron)):
            with open(f, encoding='utf8') as h:
                textos[f] = h.read()
        return textos

    def test_reglas_ilustrativas_del_paquete_no_estan_en_el_dominio(self):
        for f, texto in self._texto(os.path.join('src', 'domain', '*.py')).items():
            for palabra in ('puede_procesarse', 'beneficio_referencia', 'preferente', 'promocion', 'paquete_pia'):
                with self.subTest(archivo=os.path.basename(f), palabra=palabra):
                    self.assertNotIn(palabra, texto)

    def test_especificaciones_viven_en_el_dominio_y_no_en_la_api(self):
        for f, texto in self._texto(os.path.join('src', 'api', '*.py')).items():
            self.assertNotIn('especificacion', texto.lower(), os.path.basename(f))

    def test_especificaciones_de_negocio_solo_dependen_del_dominio(self):
        ruta = os.path.join(RAIZ, 'src', 'domain', 'especificaciones.py')
        with open(ruta, encoding='utf8') as f:
            arbol = ast.parse(f.read())
        externos = {n.module.split('.')[0] for n in ast.walk(arbol)
                    if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}
        externos |= {a.name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        self.assertLessEqual(externos, {'__future__', 'dataclasses', 'typing'}, externos)

    def test_las_reglas_existentes_usan_las_especificaciones(self):
        usos = {'contrato.py': ['CONTRATACION_CONFIRMABLE'],
                'servicios_dominio.py': ['SOLICITUD_PUEDE_CONTINUAR'],
                'solicitudes.py': ['CAMBIO_REQUIERE_APROBACION_CLIENTE', 'CAMBIO_CON_CARGO_TARDIO',
                                   'SERVICIO_ADICIONAL_EN_PLAZO', 'SOLICITUD_CAMBIO_EN_PLAZO'],
                'valores.py': ['MODIFICACION_CON_IMPACTO']}
        for archivo, nombres in usos.items():
            with open(os.path.join(RAIZ, 'src', 'domain', archivo), encoding='utf8') as f:
                usados = {n.id for n in ast.walk(ast.parse(f.read())) if isinstance(n, ast.Name)}
            for nombre in nombres:
                with self.subTest(archivo=archivo, especificacion=nombre):
                    self.assertIn(nombre, usados)


if __name__ == '__main__':
    unittest.main()
