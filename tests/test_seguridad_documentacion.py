"""La matriz de permisos documentada coincide con la que aplica la API, y los scripts de seguridad no contienen credenciales."""
import importlib.util, os, re, sys, unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'src'))


class DocumentacionDeSeguridad(unittest.TestCase):
    def test_la_matriz_documentada_esta_al_dia(self):
        spec = importlib.util.spec_from_file_location('matriz', os.path.join(RAIZ, 'scripts', 'generar_matriz_permisos.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with open(os.path.join(RAIZ, 'docs', 'SEGURIDAD_MATRIZ_PERMISOS.md'), encoding='utf-8') as f:
            self.assertEqual(f.read(), mod.generar())

    def test_no_hay_credenciales_predeterminadas_en_el_codigo_ni_en_las_migraciones(self):
        for carpeta in ('src', 'migraciones', 'scripts'):
            for d, _, fs in os.walk(os.path.join(RAIZ, carpeta)):
                if '__pycache__' in d or 'datos_demo' in d:
                    continue
                for f in fs:
                    if not f.endswith(('.py', '.js', '.mjs', '.html')):
                        continue
                    texto = open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
                    for m in re.finditer(r"(?i)(contrasena|password|clave)\w*\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]", texto):
                        valor = m.group(2)
                        # se admiten ejemplos obvios de documentación y valores de pruebas explícitos; nada con aspecto de credencial real
                        self.assertTrue(valor.startswith(('una-contrasena', 'otra-contrasena', 'Prueba-', 'incorrecta', 'mala-')) or '${' in valor or valor.startswith(('http', 'postgresql')),
                                        f'posible credencial en {f}: {m.group(0)[:60]}')

    def test_la_migracion_no_inserta_cuentas(self):
        with open(os.path.join(RAIZ, 'migraciones', 'versions', '0006_seguridad_cuentas_y_sesiones.py'), encoding='utf-8') as f:
            texto = f.read()
        self.assertNotRegex(texto, r'(?i)insert\s+into|bulk_insert|op\.execute')


if __name__ == '__main__':
    unittest.main()
