"""La trazabilidad de la API (docs/architecture/trazabilidad-api-persistencia.md) está al día con las rutas reales."""
import importlib.util, os, re, sys, unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
from api.main import crear_app                                                            # noqa: E402

RUTA_DOC = os.path.join(RAIZ, 'docs', 'architecture', 'trazabilidad-api-persistencia.md')
GENERALES = {'/', '/health', '/ready', '/auth/inicio-sesion', '/auth/yo', '/auth/cierre-sesion', '/auth/cambio-contrasena', '/usuarios',
             '/usuarios/{usuario_id}/estado', '/usuarios/{usuario_id}/contrasena'}   # seguridad: no son rutas de negocio (docs/SEGURIDAD_Y_PERMISOS.md)


def cargar_generador():
    spec = importlib.util.spec_from_file_location('generar_trazabilidad_api', os.path.join(RAIZ, 'scripts', 'generar_trazabilidad_api.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Trazabilidad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(RUTA_DOC, encoding='utf-8') as f:
            cls.doc = f.read()

    def test_el_documento_coincide_con_lo_que_genera_el_script(self):
        self.assertEqual(self.doc, cargar_generador().generar())

    def test_cada_ruta_de_negocio_de_la_api_figura_en_el_documento(self):
        paginas = crear_app().openapi()['paths']
        reales = {(m.upper(), p) for p, ops in paginas.items() for m in ops if p not in GENERALES}
        documentadas = set(re.findall(r'^\| \w+ \| (GET|POST) \| `([^`]+)` \|', self.doc, flags=re.M))
        self.assertEqual(reales, documentadas)

    def test_el_encabezado_cuenta_las_rutas_y_no_asigna_historias_por_inferencia(self):
        n = len(re.findall(r'^\| \w+ \| (?:GET|POST) \|', self.doc, flags=re.M))
        self.assertIn(f'Rutas de negocio: **{n}**', self.doc)
        for linea in self.doc.splitlines():
            if '(sin fila propia en la matriz)' in linea:
                self.assertEqual(linea.count('(sin fila propia en la matriz)'), 3, linea)       # BN, US/CA y CU juntos

    def test_cada_ruta_esta_clasificada_y_el_respaldo_cita_identificadores_existentes(self):
        gen = cargar_generador()
        gen.verificar_respaldo()                                                      # falla si una cita no existe en las fuentes
        filas = re.findall(r'^\| \w+ \| (?:GET|POST) \| .*\| (Negocio[^|]*|Técnica|Sin respaldo[^|]*) \| [^|]+ \|$', self.doc, flags=re.M)
        self.assertEqual(len(filas), len(re.findall(r'^\| \w+ \| (?:GET|POST) \|', self.doc, flags=re.M)))
        # Única excepción: el catálogo de proveedores (extensión D-P1, pendiente de aprobación del equipo). Cualquier otra ruta sin respaldo falla.
        sin = set(re.findall(r'^\| \w+ \| (GET|POST) \| `([^`]+)` \|.*\| Sin respaldo[^|]* \| [^|]+ \|$', self.doc, flags=re.M))
        self.assertEqual(sin, {('POST', '/proveedores'), ('GET', '/proveedores'), ('GET', '/proveedores/{proveedor_id}')})
        self.assertEqual(set(gen.TECNICAS), {('GET', '/'), ('GET', '/health'), ('GET', '/ready')})
        self.assertIn('## Operaciones técnicas (sin historia de usuario)', self.doc)

    def test_el_generador_rechaza_una_cita_inexistente(self):
        gen = cargar_generador()
        original = dict(gen.RESPALDO)
        try:
            gen.RESPALDO[('GET', '/x')] = ('Negocio', 'US-999', '', '')
            with self.assertRaises(RuntimeError):
                gen.verificar_respaldo()
        finally:
            gen.RESPALDO.clear(); gen.RESPALDO.update(original)

    def test_declara_las_reglas_aprobadas_que_siguen_sin_implementarse(self):
        self.assertIn('quedaron implementadas y probadas en la fase final', self.doc)
        self.assertIn('C-02', self.doc)


if __name__ == '__main__':
    unittest.main()
