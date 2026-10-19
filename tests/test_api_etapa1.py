"""Etapa 1 de desarrollo funcional — configuración inicial de FastAPI.

Comprueba las rutas GET / y GET /health y que la nueva capa api no altera la independencia de las
capas existentes. Requiere las dependencias de requirements.txt (pip install -r requirements.txt)."""
import ast, glob, os, sys, unittest

RAIZ = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(RAIZ, 'src'))

try:
    from fastapi.testclient import TestClient                                   # noqa: E402
except ImportError as e:  # se falla de forma explícita: no se omiten las pruebas en silencio
    raise ImportError("Faltan las dependencias de la API. Ejecuta: python -m pip install -r requirements.txt") from e

from api.main import app, NOMBRE_APLICACION, VERSION_API                        # noqa: E402


class RutaRaiz(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(app)

    def test_responde_200_en_json(self):
        r = self.cliente.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers['content-type'].startswith('application/json'))

    def test_identifica_a_eventos_nova(self):
        datos = self.cliente.get('/').json()
        self.assertEqual(datos['aplicacion'], 'Eventos Nova')
        self.assertEqual(datos['version'], VERSION_API)
        self.assertEqual(datos['salud'], '/health')
        self.assertEqual(datos['documentacion'], '/docs')


class RutaHealth(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(app)

    def test_responde_200_con_estado_ok(self):
        r = self.cliente.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers['content-type'].startswith('application/json'))
        self.assertEqual(r.json(), {'estado': 'ok', 'aplicacion': NOMBRE_APLICACION, 'version': VERSION_API})

    def test_solo_admite_get(self):
        self.assertEqual(self.cliente.post('/health').status_code, 405)


class ConfiguracionDeLaApp(unittest.TestCase):
    def test_metadatos_de_la_instancia(self):
        self.assertEqual(app.title, 'Eventos Nova API')
        self.assertEqual(app.version, VERSION_API)

    def test_esquema_openapi_publica_las_rutas(self):
        rutas = TestClient(app).get('/openapi.json').json()['paths']
        self.assertIn('/', rutas)
        self.assertIn('/health', rutas)

    def test_ruta_inexistente_devuelve_404(self):
        self.assertEqual(TestClient(app).get('/no-existe').status_code, 404)


class CapaApiNoInvadeLasDemasCapas(unittest.TestCase):
    """Dominio, aplicación e infraestructura no dependen de la capa api ni de FastAPI."""

    def test_capas_existentes_no_importan_api_ni_fastapi(self):
        for capa in ('domain', 'application', 'infrastructure'):
            for f in glob.glob(os.path.join(RAIZ, 'src', capa, '*.py')):
                with open(f, encoding='utf8') as h:
                    for n in ast.walk(ast.parse(h.read())):
                        mods = ([a.name for a in n.names] if isinstance(n, ast.Import)
                                else [n.module] if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 else [])
                        for m in mods:
                            self.assertNotIn(m.split('.')[0], {'api', 'fastapi', 'starlette', 'uvicorn'},
                                             f'{os.path.basename(f)} importa {m}')


if __name__ == '__main__':
    unittest.main()
