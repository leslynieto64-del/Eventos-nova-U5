"""Etapa 3A — rutas POST /eventos y POST /eventos/{evento_id}/propuestas sobre GestionPropuestaService.

Cada prueba crea su propia aplicación con crear_app(), que construye un contenedor en memoria nuevo: las pruebas
no comparten datos. Requiere las dependencias de requirements.txt."""
import ast, glob, os, sys, unittest
from datetime import datetime
from decimal import Decimal as D

RAIZ = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(RAIZ, 'src'))

try:
    from fastapi.testclient import TestClient                                   # noqa: E402
except ImportError as e:  # se falla de forma explícita: no se omiten las pruebas en silencio
    raise ImportError("Faltan las dependencias de la API. Ejecuta: python -m pip install -r requirements.txt") from e

from api.main import crear_app                                                   # noqa: E402
from api.dependencias import obtener_reloj, obtener_servicio_propuestas          # noqa: E402
from application.resultados import Resultado                                     # noqa: E402
from domain.valores import EstadoEvento, EstadoPropuesta, Importe                # noqa: E402

AHORA = datetime(2026, 10, 1, 10, 0)
DATOS = {'tipo': 'Boda', 'fecha_hora': '2026-11-20T18:00:00', 'lugar': 'Salón', 'invitados_aproximados': 100}
EVENTO = {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']}
CONTENIDO = {'servicios': ['Banquete'], 'proveedores_considerados': ['PV-1'], 'costo_total': '10000.00',
             'condiciones': 'Condiciones generales'}


class _ApiBase(unittest.TestCase):
    def setUp(self):
        self.app = crear_app()
        self.app.dependency_overrides[obtener_reloj] = lambda: (lambda: AHORA)
        self.cliente = TestClient(self.app)
        self.repos = self.app.state.contenedor.repos

    def registrar_evento(self, cuerpo=EVENTO):
        return self.cliente.post('/eventos', json=cuerpo)

    def assertRechazoNegocio(self, r, fragmento):
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()['tipo'], 'rechazo_de_negocio')
        self.assertIn(fragmento, r.json()['detalle'])


class RegistrarEvento(_ApiBase):
    def test_registra_el_evento_en_gestion(self):
        r = self.registrar_evento()
        self.assertEqual(r.status_code, 201, r.text)
        cuerpo = r.json()
        self.assertTrue(cuerpo['evento_id'].startswith('EV-'))
        self.assertEqual(cuerpo['mensaje'], 'Evento registrado En gestión.')
        ev = self.repos.eventos.obtener_por_id(cuerpo['evento_id'])
        self.assertEqual(ev.estado, EstadoEvento.EN_GESTION)
        self.assertEqual((ev.cliente_id, ev.datos.tipo, ev.datos.fecha_hora, ev.datos.lugar, ev.datos.invitados_aproximados),
                         ('CL-1', 'Boda', datetime(2026, 11, 20, 18, 0), 'Salón', 100))
        self.assertEqual(ev.servicios_solicitados, ['Banquete'])

    def test_datos_incompletos_los_rechaza_el_dominio(self):            # CA-003
        r = self.registrar_evento({**EVENTO, 'datos': {**DATOS, 'lugar': ''}})
        self.assertRechazoNegocio(r, 'CA-003')

    def test_invitados_no_positivos(self):                              # CA-003
        self.assertRechazoNegocio(self.registrar_evento({**EVENTO, 'datos': {**DATOS, 'invitados_aproximados': 0}}), 'CA-003')

    def test_campo_obligatorio_ausente(self):
        r = self.registrar_evento({'datos': DATOS, 'servicios': ['Banquete']})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn('tipo', r.json())                              # error de validación de FastAPI, no de negocio

    def test_fecha_con_zona_horaria_no_se_acepta(self):
        r = self.registrar_evento({**EVENTO, 'datos': {**DATOS, 'fecha_hora': '2026-11-20T18:00:00-06:00'}})
        self.assertEqual(r.status_code, 422)

    def test_campo_desconocido_no_se_acepta(self):
        self.assertEqual(self.registrar_evento({**EVENTO, 'estado': 'Cancelado'}).status_code, 422)

    def test_rechazo_no_guarda_nada(self):
        self.registrar_evento({**EVENTO, 'datos': {**DATOS, 'tipo': ''}})
        self.assertEqual(self.repos.eventos._todos(), [])


class CrearPropuesta(_ApiBase):
    def setUp(self):
        super().setUp()
        self.evento_id = self.registrar_evento().json()['evento_id']

    def crear(self, evento_id=None, cuerpo=CONTENIDO):
        return self.cliente.post(f'/eventos/{evento_id or self.evento_id}/propuestas', json=cuerpo)

    def test_crea_la_propuesta_valida(self):
        r = self.crear()
        self.assertEqual(r.status_code, 201, r.text)
        cuerpo = r.json()
        self.assertTrue(cuerpo['propuesta_id'].startswith('PR-'))
        self.assertEqual((cuerpo['evento_id'], cuerpo['mensaje']), (self.evento_id, 'Propuesta creada.'))
        p = self.repos.propuestas.obtener_por_id(cuerpo['propuesta_id'])
        self.assertEqual((p.evento_id, p.cliente_id, p.estado), (self.evento_id, 'CL-1', EstadoPropuesta.EN_REVISION_CLIENTE))
        v = p.versiones[0]
        self.assertEqual((v.numero, v.fecha_actualizacion, p.version_vigente_id), (1, AHORA, v.version_id))
        self.assertEqual(v.contenido.servicios, ('Banquete',))
        self.assertEqual(v.contenido.proveedores_considerados, ('PV-1',))
        self.assertEqual(v.contenido.costo_total, Importe(D('10000.00')))
        self.assertEqual(v.contenido.condiciones, 'Condiciones generales')

    def test_evento_inexistente(self):
        self.assertRechazoNegocio(self.crear('EV-noexiste'), 'El evento no existe o no está En gestión.')

    def test_contenido_sin_servicios_lo_rechaza_el_dominio(self):        # CA-005
        self.assertRechazoNegocio(self.crear(cuerpo={**CONTENIDO, 'servicios': []}), 'CA-005')

    def test_contenido_sin_condiciones_lo_rechaza_el_dominio(self):      # CA-005
        self.assertRechazoNegocio(self.crear(cuerpo={**CONTENIDO, 'condiciones': ''}), 'CA-005')

    def test_costo_negativo_lo_rechaza_el_dominio(self):
        self.assertRechazoNegocio(self.crear(cuerpo={**CONTENIDO, 'costo_total': '-1'}), 'negativo')

    def test_costo_no_numerico(self):
        self.assertEqual(self.crear(cuerpo={**CONTENIDO, 'costo_total': 'mucho'}).status_code, 422)

    def test_rechazo_no_guarda_propuesta(self):
        self.crear(cuerpo={**CONTENIDO, 'servicios': []})
        self.assertEqual(self.repos.propuestas.listar_por_evento_id(self.evento_id), [])

    def test_la_fecha_de_la_version_no_viene_en_la_peticion(self):
        """`ahora` no viene en la petición: lo entrega la dependencia obtener_reloj."""
        self.assertEqual(self.crear(cuerpo={**CONTENIDO, 'fecha_actualizacion': '2020-01-01T00:00:00'}).status_code, 422)


class AislamientoEntrePruebas(unittest.TestCase):
    def test_cada_aplicacion_tiene_sus_propios_datos(self):
        a, b = TestClient(crear_app()), TestClient(crear_app())
        evento_id = a.post('/eventos', json=EVENTO).json()['evento_id']
        self.assertEqual(a.post(f'/eventos/{evento_id}/propuestas', json=CONTENIDO).status_code, 201)
        self.assertEqual(b.post(f'/eventos/{evento_id}/propuestas', json=CONTENIDO).status_code, 422)

    def test_una_aplicacion_nueva_empieza_vacia(self):
        self.assertEqual(crear_app().state.contenedor.repos.eventos._todos(), [])


class DependenciasSustituibles(unittest.TestCase):
    def test_la_fabrica_del_contenedor_es_sustituible(self):
        llamadas = []

        class Contenedor:  # sustituto mínimo con la forma del contenedor
            class servicios:
                class propuestas:
                    @staticmethod
                    def registrar_evento(cliente_id, datos, servicios):
                        llamadas.append((cliente_id, datos, servicios))
                        return Resultado.ok('Evento registrado En gestión.', evento_id='EV-falso')

        cliente = TestClient(crear_app(lambda: Contenedor))
        r = cliente.post('/eventos', json=EVENTO)
        self.assertEqual((r.status_code, r.json()['evento_id']), (201, 'EV-falso'))
        self.assertEqual(llamadas[0][0], 'CL-1')

    def test_rechazo_del_servicio_conserva_motivo_y_pendientes(self):
        class Servicio:
            def registrar_evento(self, *a):
                return Resultado.rechazo('Motivo de negocio', ['requisito A'])
        app = crear_app()
        app.dependency_overrides[obtener_servicio_propuestas] = Servicio
        r = TestClient(app).post('/eventos', json=EVENTO)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json(), {'tipo': 'rechazo_de_negocio', 'detalle': 'Motivo de negocio', 'pendientes': ['requisito A']})


class ErroresTecnicosNoSeOcultan(unittest.TestCase):
    """Una excepción que no es un rechazo de negocio no se convierte en 4xx."""

    def setUp(self):
        class Fallido:
            def registrar_evento(self, *a):
                raise RuntimeError('falla técnica simulada')
        self.app = crear_app()
        self.app.dependency_overrides[obtener_servicio_propuestas] = Fallido

    def test_la_excepcion_se_propaga(self):
        with self.assertRaisesRegex(RuntimeError, 'falla técnica simulada'):
            TestClient(self.app).post('/eventos', json=EVENTO)

    def test_responde_500(self):
        r = TestClient(self.app, raise_server_exceptions=False).post('/eventos', json=EVENTO)
        self.assertEqual(r.status_code, 500)


class RutasExistentesSeConservan(unittest.TestCase):
    def test_raiz_y_health(self):
        c = TestClient(crear_app())
        self.assertEqual(c.get('/').json()['aplicacion'], 'Eventos Nova')
        self.assertEqual(c.get('/health').json()['estado'], 'ok')

    def test_openapi_publica_las_rutas_nuevas(self):
        rutas = TestClient(crear_app()).get('/openapi.json').json()['paths']
        self.assertIn('post', rutas['/eventos'])
        self.assertIn('post', rutas['/eventos/{evento_id}/propuestas'])


class LasRutasNoDependenDeLaInfraestructura(unittest.TestCase):
    """Solo main.py (raíz de composición) importa infrastructure; las rutas, dependencias y esquemas no."""

    def test_modulos_de_la_api_sin_infraestructura(self):
        for f in glob.glob(os.path.join(RAIZ, 'src', 'api', '*.py')):
            if os.path.basename(f) == 'main.py':
                continue
            with open(f, encoding='utf8') as h:
                for n in ast.walk(ast.parse(h.read())):
                    mods = ([a.name for a in n.names] if isinstance(n, ast.Import)
                            else [n.module] if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 else [])
                    for m in mods:
                        self.assertNotEqual(m.split('.')[0], 'infrastructure', f'{os.path.basename(f)} importa {m}')


if __name__ == '__main__':
    unittest.main()
