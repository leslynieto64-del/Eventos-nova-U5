"""docs/BRD.md (estructura mínima del PIA) es la exportación fiel y al día del BRD aprobado (.docx)."""
import importlib.util, os, re, unittest, zipfile

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class BrdMarkdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('convertir_brd', os.path.join(RAIZ, 'scripts', 'convertir_brd_a_markdown.py'))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        with open(os.path.join(RAIZ, 'docs', 'BRD.md'), encoding='utf-8') as f:
            cls.md = f.read()

    def test_esta_al_dia_con_el_docx_aprobado(self):
        self.assertEqual(self.md, self.mod.generar())

    def test_conserva_todos_los_identificadores_del_docx(self):
        xml = zipfile.ZipFile(os.path.join(RAIZ, 'docs', 'unidad 2', 'Reporte_BRD_Corregido.docx')).read('word/document.xml').decode('utf-8')
        texto = re.sub(r'<[^>]+>', ' ', xml)
        for ident in sorted(set(re.findall(r'\b(?:BN|SE)-\d{3}\b', texto))):
            self.assertIn(ident, self.md, ident)

    def test_declara_que_es_generado_y_no_cambia_la_fuente(self):
        self.assertIn('GENERADO', self.md.splitlines()[0])


if __name__ == '__main__':
    unittest.main()
