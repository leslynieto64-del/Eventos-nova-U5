"""Interfaz web (HTML, CSS y JavaScript sin frameworks) servida por FastAPI en /app.

Comprueba, sin PostgreSQL ni navegador: que los archivos estáticos se sirven, que la API original (salud, documentación, OpenAPI) sigue
intacta, que la interfaz no llama a ningún endpoint inexistente, que la matriz de cobertura está al día y que el tratamiento del servicio
adicional posterior al inicio (lo que la interfaz explica al usuario) es el que informa el backend.
Las pruebas con navegador real están en scripts/probar_interfaz_navegador.mjs.
Ejecutar desde la raíz:  python -m unittest tests.test_interfaz_web -v"""
import importlib.util, json, os, re, sys, unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from fastapi.testclient import TestClient                                                    # noqa: E402
from api.main import crear_app                                                               # noqa: E402
from infrastructure.composicion import construir                                              # noqa: E402
from apoyo_flujo import FECHA_EVENTO                                                         # noqa: E402
from test_api_operaciones import ApiHttp, iso                                                # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WEB = os.path.join(RAIZ, 'src', 'web')


def _archivos(ext):
    for d, _, fs in os.walk(WEB):
        for f in fs:
            if f.endswith(ext):
                yield os.path.join(d, f)


class ArchivosEstaticos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cliente = TestClient(crear_app(construir))

    def test_la_interfaz_se_sirve_en_app(self):
        r = self.cliente.get('/app/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/html', r.headers['content-type'])
        self.assertIn('<html lang="es">', r.text)
        for recurso in ('/app/css/app.css', '/app/js/main.js', '/app/js/api.js', '/app/js/ui.js', '/app/js/acciones.js'):
            self.assertEqual(self.cliente.get(recurso).status_code, 200, recurso)

    def test_la_api_original_no_cambia(self):
        for ruta in ('/', '/health', '/docs', '/openapi.json'):
            self.assertEqual(self.cliente.get(ruta).status_code, 200, ruta)
        self.assertEqual(self.cliente.get('/health').json()['estado'], 'ok')
        self.assertNotIn('/app', json.dumps(self.cliente.get('/openapi.json').json()['paths']))      # la interfaz no entra en el contrato

    def test_solo_html_css_y_javascript(self):
        extensiones = {os.path.splitext(f)[1] for f in (os.path.join(d, x) for d, _, fs in os.walk(WEB) for x in fs)}
        self.assertLessEqual(extensiones, {'.html', '.css', '.js'})
        for f in _archivos('.html'):
            texto = open(f, encoding='utf-8').read()
            self.assertNotRegex(texto, r'https?://(?!127\.0\.0\.1|localhost)', f'{f} no debe cargar recursos externos')
        for f in _archivos('.js'):
            self.assertNotRegex(open(f, encoding='utf-8').read(), r'^\s*import .* from [\'"](?![./])', f'{f} usa una biblioteca externa')

    def test_los_modulos_importados_existen(self):
        for f in _archivos('.js'):
            for destino in re.findall(r"from '(\.[^']+)'", open(f, encoding='utf-8').read()):
                self.assertTrue(os.path.isfile(os.path.normpath(os.path.join(os.path.dirname(f), destino))), f'{f} importa {destino}')


class LlamadasALaApi(unittest.TestCase):
    """Cada ruta que escribe el JavaScript debe existir en docs/api/openapi.json con ese método (nada inventado)."""
    def test_todas_las_rutas_usadas_existen_en_el_openapi(self):
        doc = json.load(open(os.path.join(RAIZ, 'docs', 'api', 'openapi.json'), encoding='utf-8'))
        patrones = [(m.upper(), re.compile('^' + re.sub(r'\{[^}]+\}', '[^/]+', ruta) + '$')) for ruta, ops in doc['paths'].items() for m in ops]
        usadas = set()
        for f in _archivos('.js'):
            texto = open(f, encoding='utf-8').read()
            for metodo, _, ruta in re.findall(r"\b(GET|POST)\(\s*([`'])(/[^`']*)\2", texto):
                usadas.add((metodo, re.sub(r'\$\{[^}]+\}', 'X', ruta)))
            for ruta in re.findall(r"api\('(GET|POST)', '(/[^']*)'", texto):
                usadas.add(ruta)
        self.assertGreater(len(usadas), 40)
        for metodo, ruta in sorted(usadas):
            self.assertTrue(any(m == metodo and p.match(ruta) for m, p in patrones), f'{metodo} {ruta} no existe en el OpenAPI')

    def test_cada_operacion_del_openapi_se_usa_o_esta_justificada(self):
        doc = json.load(open(os.path.join(RAIZ, 'docs', 'api', 'openapi.json'), encoding='utf-8'))
        codigo = ''.join(open(f, encoding='utf-8').read() for f in _archivos('.js'))
        sin_uso = []
        for ruta, ops in doc['paths'].items():
            for metodo in ops:
                base = re.sub(r'\{[^}]+\}', '', ruta).rstrip('/').split('/')
                clave = [t for t in base if t][-1] if [t for t in base if t] else ''
                if clave and clave not in codigo:
                    sin_uso.append((metodo.upper(), ruta))
        self.assertEqual(sin_uso, [])


class MatrizDeCobertura(unittest.TestCase):
    def test_esta_al_dia_y_cubre_todas_las_operaciones(self):
        spec = importlib.util.spec_from_file_location('cobertura', os.path.join(RAIZ, 'scripts', 'generar_cobertura_interfaz.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        actual = open(os.path.join(RAIZ, 'docs', 'INTERFAZ_WEB_COBERTURA.md'), encoding='utf-8').read()
        self.assertEqual(actual, mod.generar())


class ServicioAdicionalDespuesDelInicio(ApiHttp, unittest.TestCase):
    """Lo que la interfaz le explica al usuario: tras el inicio, el servicio adicional se registra «No procedente» (GL-015, SE-004, ADR-008)."""
    def crear_contenedor(self, disponibilidad=None):
        return construir(disponibilidad)

    def test_se_registra_como_no_procedente_y_la_lista_lo_muestra_sin_cambiarlo(self):
        ids = self.contratar()
        self.ahora = FECHA_EVENTO
        self.post(f"/eventos/{ids['evento']}/inicio")
        self.assertEqual(self.get(f"/eventos/{ids['evento']}/administracion")['estadoEvento'], 'En ejecución')
        r = self.post('/solicitudes-servicio-adicional', {'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'servicio': 'DJ'}, esperado=201)
        self.assertEqual(r['datos']['estado'], 'No procedente')
        self.assertIn('inició', r['datos']['motivo'])
        lista = self.get('/solicitudes', evento_id=ids['evento'])['solicitudes']
        self.assertEqual([x['estadoActual'] for x in lista], ['No procedente'])

    def test_el_cambio_despues_del_inicio_se_rechaza_con_motivo(self):
        ids = self.contratar()
        self.ahora = FECHA_EVENTO
        self.post(f"/eventos/{ids['evento']}/inicio")
        r = self.post('/solicitudes-cambio', {'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'descripcion': 'Cambiar hora', 'tarifa_vigente': '500.00'}, esperado=422)
        self.assertEqual(r['tipo'], 'rechazo_de_negocio')
        self.assertTrue(r['detalle'])


if __name__ == '__main__':
    unittest.main()
