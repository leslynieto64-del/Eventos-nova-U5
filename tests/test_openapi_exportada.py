"""docs/api/openapi.json (estructura mínima del PIA) está al día con la API real y describe las 71 operaciones."""
import importlib.util, json, os, unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class OpenApiExportada(unittest.TestCase):
    def test_el_archivo_coincide_con_la_api_actual(self):
        spec = importlib.util.spec_from_file_location('exportar_openapi', os.path.join(RAIZ, 'scripts', 'exportar_openapi.py'))
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        with open(os.path.join(RAIZ, 'docs', 'api', 'openapi.json'), encoding='utf-8') as f:
            self.assertEqual(f.read(), modulo.generar())

    def test_describe_las_71_operaciones_y_el_esquema_de_errores(self):
        with open(os.path.join(RAIZ, 'docs', 'api', 'openapi.json'), encoding='utf-8') as f:
            doc = json.load(f)
        self.assertEqual(sum(len(v) for v in doc['paths'].values()), 71)
        self.assertTrue(doc['openapi'].startswith('3.'))
        self.assertTrue(all('summary' in op for ops in doc['paths'].values() for op in ops.values()))

    def test_estado_de_pagos_tiene_esquema_y_describe_plazo_vencido(self):
        with open(os.path.join(RAIZ, 'docs', 'api', 'openapi.json'), encoding='utf-8') as f:
            doc = json.load(f)
        esquema = doc['paths']['/eventos/{evento_id}/pagos']['get']['responses']['200']['content']['application/json']['schema']
        self.assertEqual(esquema, {'$ref': '#/components/schemas/EstadoPagosRespuesta'})
        piezas = doc['components']['schemas']
        resumen = piezas['EstadoCuentaResumenRespuesta']['properties']
        self.assertEqual(set(resumen), {'estadoCuentaId', 'contratoId', 'anticipo', 'pagosRegistrados', 'saldoContratoOriginal',
                                        'obligacionesAdicionales', 'devoluciones'})
        self.assertEqual(resumen['anticipo'], {'$ref': '#/components/schemas/ObligacionPagoRespuesta'})
        obligacion = piezas['ObligacionPagoRespuesta']['properties']
        self.assertEqual(set(obligacion), {'importe', 'fechaLimite', 'estado', 'plazoVencido', 'resultadoRegularizacion'})
        self.assertIn({'type': 'boolean'}, obligacion['plazoVencido']['anyOf'])
        self.assertIn('CA-023', obligacion['plazoVencido']['description'])
        self.assertIn('fechaLimite', obligacion)


if __name__ == '__main__':
    unittest.main()
