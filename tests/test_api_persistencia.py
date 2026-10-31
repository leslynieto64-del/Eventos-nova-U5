"""Etapa 7 — integración de la API con la persistencia: modo de ejecución, errores HTTP de persistencia, disponibilidad,
persistencia tras reiniciar por HTTP, despacho en línea y trabajador del Outbox."""
import io, logging, os, sys, threading, unittest
from datetime import timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi import FastAPI                                                                  # noqa: E402
from fastapi.testclient import TestClient                                                    # noqa: E402
from apoyo_bd import BaseConBD                                                               # noqa: E402
from apoyo_flujo import T0, FECHA_EVENTO                                                     # noqa: E402
from test_api_operaciones import ApiHttp, CONTENIDO, DATOS, iso                              # noqa: E402
from api.dependencias import obtener_reloj                                                   # noqa: E402
from api.errores import registrar_manejadores_persistencia                                   # noqa: E402
from api.main import crear_app, fabrica_por_defecto                                          # noqa: E402
from infrastructure.composicion import construir                                              # noqa: E402
from infrastructure.persistencia import configuracion as C                                   # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente          # noqa: E402
from infrastructure.persistencia.errores import (ErrorDeConexion, ErrorDeDatos, ErrorDePersistencia,   # noqa: E402
                                                 ViolacionDeRestriccion)
from infrastructure.persistencia.trabajador_outbox import ejecutar                            # noqa: E402


class ModoDeEjecucion(unittest.TestCase):
    def test_por_omision_la_api_usa_la_composicion_en_memoria(self):
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_PERSISTENCIA': ''}):
            self.assertIs(fabrica_por_defecto(), construir)
        app = crear_app()
        self.assertFalse(hasattr(app.state.contenedor, 'modo'))
        self.assertEqual(TestClient(app).get('/ready').json(), {'estado': 'ok', 'persistencia': 'memoria', 'base_de_datos': 'no_aplica'})

    def test_modo_postgresql_elige_la_composicion_persistente(self):
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_PERSISTENCIA': 'postgresql'}):
            from infrastructure.persistencia.composicion_persistente import construir_persistente_desde_entorno
            self.assertIs(fabrica_por_defecto(), construir_persistente_desde_entorno)

    def test_un_modo_desconocido_falla_en_el_arranque(self):
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_PERSISTENCIA': 'mongodb'}):
            with self.assertRaises(ValueError):
                fabrica_por_defecto()

    def test_en_modo_postgresql_sin_base_de_datos_la_api_no_arranca(self):
        inalcanzable = 'postgresql+psycopg://x:y@127.0.0.1:1/z_test'
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_PERSISTENCIA': 'postgresql', 'DATABASE_URL': inalcanzable}):
            with self.assertRaises(ErrorDeConexion):
                crear_app(lambda: construir_persistente(url=inalcanzable, connect_args={'connect_timeout': 2}))


class ErroresHttpDePersistencia(unittest.TestCase):
    """Cada error de persistencia tiene su respuesta HTTP; no se confunde con un rechazo de negocio ni se filtra información interna."""
    def setUp(self):
        self.app = FastAPI()
        registrar_manejadores_persistencia(self.app, ViolacionDeRestriccion, ErrorDeDatos, ErrorDeConexion, ErrorDePersistencia)
        errores = {'violacion': ViolacionDeRestriccion('detalle interno SQL', 'fk_secreta', 'tabla_interna'),
                   'datos': ErrorDeDatos('integer out of range'), 'conexion': ErrorDeConexion('password authentication failed for user x'),
                   'general': ErrorDePersistencia('algo interno')}
        for nombre, error in errores.items():
            def ruta(error=error):
                raise error
            self.app.add_api_route(f'/falla/{nombre}', ruta, methods=['GET'])
        self.cliente = TestClient(self.app, raise_server_exceptions=False)

    def test_codigos_y_tipos(self):
        esperado = {'violacion': (409, 'conflicto_de_integridad'), 'datos': (422, 'dato_no_almacenable'),
                    'conexion': (503, 'base_de_datos_no_disponible'), 'general': (500, 'error_de_persistencia')}
        for nombre, (codigo, tipo) in esperado.items():
            with self.subTest(nombre):
                r = self.cliente.get(f'/falla/{nombre}')
                self.assertEqual((r.status_code, r.json()['tipo']), (codigo, tipo))
                self.assertEqual(set(r.json()), {'tipo', 'detalle', 'pendientes'})            # el mismo formato de error de la API

    def test_no_se_filtran_nombres_de_restricciones_ni_mensajes_internos(self):
        for nombre in ('violacion', 'datos', 'conexion', 'general'):
            texto = self.cliente.get(f'/falla/{nombre}').text
            for secreto in ('fk_secreta', 'tabla_interna', 'detalle interno', 'password', 'algo interno', 'out of range'):
                self.assertNotIn(secreto, texto, (nombre, secreto))


class ConPostgreSQL(BaseConBD):
    def arrancar(self, **kw):
        contenedor = construir_persistente(motor=self.motor, **kw)
        app = crear_app(lambda: contenedor)
        self.ahora = T0
        app.dependency_overrides[obtener_reloj] = lambda: (lambda: self.ahora)
        return contenedor, TestClient(app)

    def test_ready_informa_la_base_de_datos_y_responde_503_si_cae(self):
        contenedor, cliente = self.arrancar()
        self.assertEqual(cliente.get('/ready').json(), {'estado': 'ok', 'persistencia': 'postgresql', 'base_de_datos': 'ok'})
        contenedor.comprobar_base_de_datos = mock.Mock(side_effect=RuntimeError('sin conexión'))
        r = cliente.get('/ready')
        self.assertEqual((r.status_code, r.json()['estado']), (503, 'no_disponible'))
        self.assertEqual(cliente.get('/health').status_code, 200)                              # /health no depende de la base

    def test_los_datos_creados_por_http_sobreviven_a_reiniciar_la_aplicacion(self):
        url = C.url_pruebas()
        c1 = construir_persistente(url=url)
        app1 = crear_app(lambda: c1)
        with TestClient(app1) as cliente:                                                      # arranca y, al salir, cierra (lifespan)
            evento = cliente.post('/eventos', json={'cliente_id': 'CL-9', 'datos': DATOS, 'servicios': ['Banquete']}).json()['evento_id']
            propuesta = cliente.post(f'/eventos/{evento}/propuestas', json=CONTENIDO).json()['propuesta_id']
        c2 = construir_persistente(url=url)                                                    # proceso nuevo: motor y pool nuevos
        try:
            with TestClient(crear_app(lambda: c2)) as cliente:
                info = cliente.get(f'/eventos/{evento}/administracion').json()
                self.assertEqual((info['estadoEvento'], info['tipoEvento'], info['lugar'], info['invitadosAproximados']),
                                 ('En gestión', 'Boda', 'Salón', 100))
                aceptada = cliente.post(f'/propuestas/{propuesta}/aceptacion', json={'version_id': f'{propuesta}-v1'})
                self.assertEqual(aceptada.status_code, 200, aceptada.text)                     # opera sobre lo guardado antes
        finally:
            c2.cerrar()

    def test_un_valor_fuera_de_rango_es_422_y_no_llega_a_la_base(self):
        contenedor, cliente = self.arrancar()
        r = cliente.post('/eventos', json={'cliente_id': 'CL-1', 'datos': {**DATOS, 'invitados_aproximados': 9223372036854775808},
                                           'servicios': ['x']})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.contar('evento'), 0)


class DespachoDelOutbox(ApiHttp, BaseConBD):
    """Los helpers HTTP de `ApiHttp` sobre un contenedor persistente (clase base de pruebas con base de datos)."""
    def setUp(self):
        BaseConBD.setUp(self)
        self.arrancar()

    def crear_contenedor(self, disponibilidad=None):
        return construir_persistente(motor=self.motor, disponibilidad=disponibilidad)

    def test_con_despacho_en_linea_las_reacciones_ocurren_dentro_de_la_peticion(self):
        ids = self.contratar()
        self.assertEqual(self.admin(ids)['estadoEvento'], 'En organización')
        self.assertEqual(self.contenedor.outbox.registros('PENDIENTE'), [])

    def test_sin_despacho_en_linea_los_eventos_esperan_al_trabajador(self):
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_DESPACHO_EN_LINEA': '0'}):
            evento = self.post('/eventos', {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['x']})['evento_id']
            propuesta = self.post(f'/eventos/{evento}/propuestas', CONTENIDO)['propuesta_id']
            self.post(f'/propuestas/{propuesta}/aceptacion', {'version_id': f'{propuesta}-v1'})
            self.assertEqual([r.tipo_evento for r in self.contenedor.outbox.registros('PENDIENTE')], ['PropuestaAceptada'])   # nadie lo despachó
            contrato = self.post(f'/propuestas/{propuesta}/contrato', {'politica_incluida': True})['datos']['contrato_id']
            self.post(f'/contratos/{contrato}/firma', {'fecha': iso(T0)})
            self.assertEqual(self.get(f'/eventos/{evento}/pagos')['estadosCuenta'], [])        # aún no existe el estado de cuenta
            self.assertEqual(ejecutar(self.contenedor, una_vez=True), 2)                        # el trabajador hace su ciclo
            self.assertEqual(len(self.get(f'/eventos/{evento}/pagos')['estadosCuenta']), 1)

    def test_si_el_despacho_en_linea_falla_el_comando_ya_confirmado_no_se_pierde(self):
        evento = self.post('/eventos', {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['x']})['evento_id']
        propuesta = self.post(f'/eventos/{evento}/propuestas', CONTENIDO)['propuesta_id']
        with mock.patch.object(self.contenedor.despachador, 'despachar', side_effect=ErrorDePersistencia('Outbox caído')):
            with self.assertLogs('eventosnova.api', level='ERROR'):
                r = self.cliente.post(f'/propuestas/{propuesta}/aceptacion', json={'version_id': f'{propuesta}-v1'})
        self.assertEqual(r.status_code, 200, r.text)                                           # el comando se confirmó
        self.assertEqual([x.tipo_evento for x in self.contenedor.outbox.registros('PENDIENTE')], ['PropuestaAceptada'])
        self.assertEqual(ejecutar(self.contenedor, una_vez=True), 1)                           # y el evento se recupera después

    def test_el_trabajador_continua_tras_un_ciclo_fallido_y_se_detiene_con_la_senal(self):
        llamadas = []

        def despachar():
            llamadas.append(1)
            if len(llamadas) == 1:
                raise ErrorDePersistencia('fallo transitorio')
            return 0
        detener = threading.Event()
        with mock.patch.object(self.contenedor.despachador, 'despachar', side_effect=despachar):
            hilo = threading.Thread(target=lambda: ejecutar(self.contenedor, intervalo=0.05, detener=detener))
            with self.assertLogs('eventosnova.trabajador', level='ERROR'):
                hilo.start()
                for _ in range(100):
                    if len(llamadas) >= 3:
                        break
                    threading.Event().wait(0.05)
            detener.set(); hilo.join(5)
        self.assertFalse(hilo.is_alive())
        self.assertGreaterEqual(len(llamadas), 3)                                              # sobrevivió al fallo del primer ciclo

    def test_una_sola_vez_propaga_el_error(self):
        with mock.patch.object(self.contenedor.despachador, 'despachar', side_effect=ErrorDePersistencia('x')):
            with self.assertRaises(ErrorDePersistencia):
                ejecutar(self.contenedor, una_vez=True)


if __name__ == '__main__':
    unittest.main()
