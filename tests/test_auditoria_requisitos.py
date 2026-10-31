"""La auditoría de requisitos (docs/trazabilidad/auditoria-requisitos-fase-final.md) está al día y declara el estado de GL-060 / C-15
(implementado con E-1, oráculo pendiente de autorización) y que E-2, E-3 y E-4 son decisiones del equipo sin aprobación formal."""
import importlib.util, os, unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def generador():
    spec = importlib.util.spec_from_file_location('generar_auditoria_requisitos', os.path.join(RAIZ, 'scripts', 'generar_auditoria_requisitos.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Auditoria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(RAIZ, 'docs', 'trazabilidad', 'auditoria-requisitos-fase-final.md'), encoding='utf-8') as f:
            cls.doc = f.read()

    def test_el_documento_coincide_con_lo_que_genera_el_script(self):
        self.assertEqual(self.doc, generador().generar())

    def test_declara_el_estado_de_los_plazos_en_dias_habiles(self):
        self.assertIn('GL-060', self.doc)
        self.assertIn('IMPLEMENTADO (decisión E-1)', self.doc)
        self.assertIn('PENDIENTE DE AUTORIZACIÓN', self.doc)            # el oráculo histórico no se recalculó
        fila = next(l for l in self.doc.splitlines() if l.startswith('| C-15 / GL-060 |'))
        self.assertNotIn('BRECHA CONFIRMADA', fila)                       # la leyenda general sí la menciona

    def test_declara_que_e2_e3_y_e4_no_tienen_aprobacion_formal(self):
        for regla in ('E-2 (decisión del equipo)', 'E-3 / E-4 (decisiones del equipo)'):
            self.assertIn(f'| {regla} |', self.doc)
        self.assertGreaterEqual(self.doc.count('SIN APROBACIÓN FORMAL'), 2)

    def test_ninguna_regla_aprobada_queda_sin_pruebas_identificables(self):
        self.assertNotIn('SIN pruebas identificables', self.doc)
        self.assertNotIn('SIN evidencia automática', self.doc)

    def test_cubre_los_22_requisitos_del_brd_y_las_reglas_del_cierre(self):
        self.assertEqual(len([l for l in self.doc.splitlines() if l.startswith('| BN-') or l.startswith('| SE-')]), 22)
        for regla in ('A-1…A-6', 'B-1…B-5', 'C-1…C-4', 'C-01', 'C-15 / GL-060'):
            self.assertIn(f'| {regla} |', self.doc)


if __name__ == '__main__':
    unittest.main()
