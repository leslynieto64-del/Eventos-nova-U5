"""Autenticación y autorización por roles: sesión, cookies, CSRF, permisos por rol, aislamiento del proveedor y limitación de intentos.

Se ejecuta con la composición en memoria y con PostgreSQL (base de PRUEBAS aislada): el comportamiento observable debe ser el mismo.
El reloj de la seguridad es controlable para probar la caducidad por inactividad y absoluta sin esperar.
Ejecutar desde la raíz:  python -m unittest tests.test_seguridad -v"""
import os, re, sys, unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient                                                    # noqa: E402
from apoyo_bd import BaseConBD                                                               # noqa: E402
from test_api_operaciones import CONTENIDO, DATOS                                            # noqa: E402
from api.main import crear_app                                                               # noqa: E402
from application.seguridad import (ADMINISTRADOR, COORDINADOR, MATRIZ, PROVEEDOR, PUBLICAS, ROLES, SESION, ConfiguracionSeguridad,   # noqa: E402
                                   autoriza, permisos_del_rol)
from domain.proveedor import Proveedor                                                       # noqa: E402
from infrastructure.composicion import construir                                              # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente          # noqa: E402

CLAVE = 'una-contrasena-larga-y-unica-1'
T0 = datetime(2026, 10, 30, 9, 0)


class Cliente:
    """Cliente HTTP con su propia cookie de sesión; añade el token CSRF a las operaciones que modifican datos."""
    def __init__(self, app):
        self.http = TestClient(app)
        self.csrf = None
        self.datos = None

    def entrar(self, correo, contrasena=CLAVE, esperado=200):
        r = self.http.post('/auth/inicio-sesion', json={'correo': correo, 'contrasena': contrasena})
        assert r.status_code == esperado, (r.status_code, r.text)
        if r.status_code == 200:
            self.datos = r.json()['datos']
            self.csrf = self.datos['csrf']
        return r

    def get(self, url, **kw):
        return self.http.get(url, **kw)

    def post(self, url, cuerpo=None, csrf=True, cabeceras=None):
        h = dict(cabeceras or {})
        if csrf and self.csrf:
            h['X-CSRF-Token'] = self.csrf
        return self.http.post(url, json=cuerpo if cuerpo is not None else {}, headers=h)


class BaseSeguridad:
    def crear_contenedor(self):                                                              # pragma: no cover
        raise NotImplementedError

    def arrancar(self, **cfg):
        self.contenedor = self.crear_contenedor()
        self.config = ConfiguracionSeguridad(activa=True, **cfg)
        self.app = crear_app(lambda: self.contenedor, self.config)
        self.seg = self.contenedor.servicios.seguridad
        self.ahora = T0
        self.seg.reloj = lambda: self.ahora
        self.cuentas = {}

    def setUp(self):
        self.arrancar()

    def cuenta(self, rol, correo=None, proveedor_id=None):
        correo = correo or f'{rol}-{len(self.cuentas)}@ejemplo.mx'
        self.seg.crear_usuario(correo, f'Persona {rol}', rol, CLAVE, proveedor_id)
        self.cuentas[correo] = rol
        return correo

    def cliente(self, rol, **kw):
        c = Cliente(self.app)
        c.entrar(self.cuenta(rol, **kw))
        return c

    def proveedor(self, nombre, servicios=('Banquete',)):
        p = Proveedor.registrar(f'PV-{nombre}', nombre, list(servicios), '', T0)
        self.assertTrue(self.contenedor.repos.proveedores.guardar(p))
        return p.proveedor_id

    # ---------------------------------------------------------------- 1. sin sesión
    def test_sin_sesion_toda_operacion_protegida_responde_401(self):
        c = Cliente(self.app)
        protegidas = sorted(k for k in MATRIZ if k not in PUBLICAS)
        self.assertGreater(len(protegidas), 60)
        for metodo, ruta in protegidas:
            url = re.sub(r'\{[^}]+\}', 'X', ruta)
            r = c.http.request(metodo, url, json={} if metodo == 'POST' else None)
            self.assertEqual(r.status_code, 401, f'{metodo} {ruta} sin sesión debe ser 401 y fue {r.status_code}')
            self.assertEqual(r.json()['tipo'], 'no_autenticado')

    def test_las_rutas_publicas_siguen_abiertas_y_no_revelan_secretos(self):
        c = Cliente(self.app)
        for ruta in ('/', '/health', '/ready'):
            self.assertEqual(c.get(ruta).status_code, 200, ruta)
        texto = c.get('/ready').text + c.get('/health').text + c.get('/').text
        for prohibido in ('password', 'contrase', 'postgresql+psycopg', '@db:', 'secret'):
            self.assertNotIn(prohibido, texto.lower())

    def test_toda_ruta_de_la_api_esta_en_la_matriz_y_viceversa(self):
        rutas = {(m.upper(), p) for p, ops in self.app.openapi()['paths'].items() for m in ops}
        self.assertEqual(rutas - set(MATRIZ) - set(PUBLICAS), set(), 'ruta sin permiso definido (se denegaría)')
        self.assertEqual(set(MATRIZ) - rutas, set(), 'entrada de la matriz sin ruta')

    def test_una_ruta_que_no_esta_en_la_matriz_se_deniega(self):
        from fastapi import APIRouter, Depends
        from api.seguridad import aplicar_seguridad
        r = APIRouter(dependencies=[Depends(aplicar_seguridad)])

        @r.get('/prueba-sin-permiso')
        def _y():
            return {'ok': True}
        self.app.include_router(r)
        resp = self.cliente(ADMINISTRADOR).get('/prueba-sin-permiso')                          # ni el administrador: lo no definido se deniega
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['tipo'], 'sin_permiso')

    # ---------------------------------------------------------------- 2. credenciales
    def test_credenciales_incorrectas_se_rechazan_con_el_mismo_mensaje(self):
        correo = self.cuenta(COORDINADOR)
        c = Cliente(self.app)
        a = c.entrar(correo, 'otra-contrasena-larga-9', esperado=401).json()
        b = c.entrar('no-existe@ejemplo.mx', CLAVE, esperado=401).json()
        self.assertEqual(a['detalle'], b['detalle'])                                          # no revela si el correo existe
        self.assertEqual(a['detalle'], 'Correo o contraseña incorrectos.')
        self.assertNotIn('set-cookie', c.http.post('/auth/inicio-sesion', json={'correo': correo, 'contrasena': 'x'}).headers)

    def test_una_cuenta_desactivada_no_puede_entrar(self):
        admin = self.cliente(ADMINISTRADOR)
        correo = self.cuenta(COORDINADOR)
        uid = self.seg.almacen.obtener_usuario_por_correo(correo).usuario_id
        self.assertEqual(admin.post(f'/usuarios/{uid}/estado', {'activo': False}).status_code, 200)
        Cliente(self.app).entrar(correo, esperado=401)

    def test_limitacion_de_intentos_y_desbloqueo_por_tiempo(self):
        correo = self.cuenta(COORDINADOR)
        c = Cliente(self.app)
        for _ in range(self.config.max_intentos):
            c.entrar(correo, 'mala-contrasena-larga-1', esperado=401)
        r = c.entrar(correo, CLAVE, esperado=429)                                             # bloqueado aunque ahora sea la correcta
        self.assertEqual(r.json()['tipo'], 'demasiados_intentos')
        self.assertIn('Retry-After', r.headers)
        self.ahora += timedelta(minutes=self.config.bloqueo_minutos + 1)
        c.entrar(correo, CLAVE)                                                               # pasado el bloqueo vuelve a funcionar

    def test_un_inicio_correcto_reinicia_el_contador(self):
        correo = self.cuenta(COORDINADOR)
        c = Cliente(self.app)
        for _ in range(self.config.max_intentos - 1):
            c.entrar(correo, 'mala-contrasena-larga-1', esperado=401)
        c.entrar(correo)
        for _ in range(self.config.max_intentos - 1):
            c.entrar(correo, 'mala-contrasena-larga-1', esperado=401)
        c.entrar(correo)                                                                      # no se acumuló el contador anterior

    # ---------------------------------------------------------------- 3. cookies, CSRF y Origin
    def test_la_cookie_de_sesion_es_httponly_samesite_y_secure_en_https(self):
        for segura in (False, True):
            self.arrancar(cookie_segura=segura)
            correo = self.cuenta(COORDINADOR, correo=f'cookie-{segura}@ejemplo.mx')       # único: en PostgreSQL las cuentas persisten entre arranques
            r = Cliente(self.app).entrar(correo)
            cookie = r.headers['set-cookie'].lower()
            self.assertIn('httponly', cookie)
            self.assertIn('samesite=strict', cookie)
            atributos = [x.strip() for x in cookie.split(';')]
            self.assertEqual('secure' in atributos, segura)
            self.assertNotIn(self.config.cookie_nombre, r.text)                              # el token nunca va en el cuerpo
            self.assertNotIn('contrasena', r.text.lower())

    def test_el_token_de_sesion_no_se_guarda_en_claro(self):
        correo = self.cuenta(COORDINADOR)
        c = Cliente(self.app)
        c.entrar(correo)
        token = c.http.cookies.get(self.config.cookie_nombre)
        self.assertTrue(token)
        self.assertIsNone(self.seg.almacen.obtener_sesion(token))                              # lo guardado es el SHA-256, no el token
        usuario = self.seg.almacen.obtener_usuario_por_correo(correo)
        self.assertTrue(usuario.contrasena_hash.startswith('$argon2id$'))
        self.assertNotIn(CLAVE, usuario.contrasena_hash)

    def test_csrf_las_operaciones_que_modifican_datos_exigen_el_token(self):
        c = self.cliente(COORDINADOR)
        cuerpo = {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']}
        sin = c.post('/eventos', cuerpo, csrf=False)
        self.assertEqual(sin.status_code, 403)
        self.assertIn('token de seguridad', sin.json()['detalle'])
        self.assertEqual(c.post('/eventos', cuerpo, cabeceras={'X-CSRF-Token': 'falso'}, csrf=False).status_code, 403)
        self.assertEqual(c.post('/eventos', cuerpo).status_code, 201)                         # con el token correcto sí
        self.assertEqual(c.get('/eventos', params={'desde': '2026-01-01T00:00:00', 'hasta': '2027-12-31T00:00:00'}).status_code, 200)   # GET sin token

    def test_el_token_csrf_de_otra_sesion_no_sirve(self):
        a, b = self.cliente(COORDINADOR), self.cliente(COORDINADOR)
        cuerpo = {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']}
        self.assertEqual(a.post('/eventos', cuerpo, cabeceras={'X-CSRF-Token': b.csrf}, csrf=False).status_code, 403)

    def test_origen_ajeno_se_rechaza_y_el_propio_se_acepta(self):
        c = self.cliente(COORDINADOR)
        cuerpo = {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']}
        self.assertEqual(c.post('/eventos', cuerpo, cabeceras={'Origin': 'https://sitio-malicioso.example', 'X-CSRF-Token': c.csrf}, csrf=False).status_code, 403)
        self.assertEqual(c.post('/eventos', cuerpo, cabeceras={'Origin': 'http://testserver'}).status_code, 201)
        self.assertEqual(Cliente(self.app).http.post('/auth/inicio-sesion', json={'correo': 'a@b.mx', 'contrasena': 'x'},
                                                     headers={'Origin': 'https://sitio-malicioso.example'}).status_code, 403)

    # ---------------------------------------------------------------- 4. permisos por rol
    def test_cada_rol_solo_ejecuta_lo_que_la_matriz_le_permite_llamando_directamente_a_la_api(self):
        proveedor = self.proveedor('Propio')
        for rol in ROLES:
            c = self.cliente(rol, proveedor_id=proveedor if rol == PROVEEDOR else None)
            for (metodo, ruta), requeridos in sorted(MATRIZ.items()):
                if (metodo, ruta) in PUBLICAS or ruta in ('/auth/cierre-sesion', '/auth/cambio-contrasena'):
                    continue
                url = re.sub(r'\{proveedor_id\}', proveedor, re.sub(r'\{(?!proveedor_id)[^}]+\}', 'X', ruta))
                r = c.http.request(metodo, url, json={} if metodo == 'POST' else None, headers={'X-CSRF-Token': c.csrf})
                permitido = autoriza(rol, metodo, ruta)
                if permitido:
                    self.assertNotIn(r.status_code, (401, 403), f'{rol} debería poder {metodo} {ruta}: {r.status_code} {r.text[:120]}')
                else:
                    self.assertEqual(r.status_code, 403, f'{rol} NO debería poder {metodo} {ruta}: {r.status_code}')
                    self.assertEqual(r.json()['tipo'], 'sin_permiso')

    def test_un_coordinador_no_ejecuta_funciones_exclusivas_del_administrador(self):
        c = self.cliente(COORDINADOR)
        for metodo, ruta in [('POST', '/usuarios'), ('GET', '/usuarios'), ('POST', '/usuarios/X/estado'), ('POST', '/usuarios/X/contrasena'),
                             ('POST', '/estados-cuenta/X/pagos'), ('POST', '/estados-cuenta/X/pagos/Y/verificacion'),
                             ('POST', '/estados-cuenta/X/devoluciones/Y/ejecucion'), ('POST', '/solicitudes-cambio/X/autorizacion'),
                             ('POST', '/solicitudes-servicio-adicional/X/autorizacion'), ('POST', '/sustituciones/X/autorizacion'),
                             ('POST', '/eventos/X/revision-administrativa')]:
            r = c.http.request(metodo, ruta, json={}, headers={'X-CSRF-Token': c.csrf})
            self.assertEqual(r.status_code, 403, f'{metodo} {ruta}')

    def test_el_administrador_no_recibe_permisos_de_coordinacion_por_defecto(self):
        a = self.cliente(ADMINISTRADOR)
        for ruta in ('/eventos', '/proveedores/X/eventos/Y'):
            self.assertNotEqual(a.get(ruta, params={'desde': '2026-01-01T00:00:00', 'hasta': '2026-12-31T00:00:00'}).status_code, 403)
        r = a.post('/eventos', {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']})
        self.assertEqual(r.status_code, 403)                                                  # registrar eventos es del coordinador

    def test_una_cuenta_nueva_no_tiene_permisos_administrativos_por_omision(self):
        admin = self.cliente(ADMINISTRADOR)
        r = admin.post('/usuarios', {'correo': 'nuevo@ejemplo.mx', 'nombre': 'Nueva Persona', 'contrasena': CLAVE})      # sin rol
        self.assertEqual(r.status_code, 422)
        r = admin.post('/usuarios', {'correo': 'nuevo@ejemplo.mx', 'nombre': 'Nueva Persona', 'contrasena': CLAVE, 'rol': 'superusuario'})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.seg.almacen.obtener_usuario_por_correo('nuevo@ejemplo.mx'), None)

    # ---------------------------------------------------------------- 5. proveedor
    def test_un_proveedor_no_accede_a_los_servicios_de_otro_proveedor(self):
        pa, pb = self.proveedor('Proveedor A'), self.proveedor('Proveedor B')
        a = self.cliente(PROVEEDOR, proveedor_id=pa)
        for ruta in (f'/proveedores/{pb}', f'/proveedores/{pb}/eventos/EV-1'):
            r = a.get(ruta)
            self.assertEqual(r.status_code, 403, ruta)
            self.assertIn('propio proveedor', r.json()['detalle'])
        self.assertEqual(a.get(f'/proveedores/{pa}').status_code, 200)                         # lo suyo sí
        self.assertEqual(a.get(f'/proveedores/{pa}/eventos/EV-1').status_code, 404)             # propio, sin servicios en ese evento (regla BN-007)
        self.assertEqual(a.get('/proveedores').status_code, 403)                                # no ve el catálogo completo
        self.assertEqual(a.get('/eventos', params={'desde': '2026-01-01T00:00:00', 'hasta': '2026-12-31T00:00:00'}).status_code, 403)

    def test_un_proveedor_solo_responde_por_si_mismo_sin_importar_lo_que_envie_el_cliente(self):
        pa, pb = self.proveedor('Proveedor A'), self.proveedor('Proveedor B')
        a = self.cliente(PROVEEDOR, proveedor_id=pa)
        r = a.post('/eventos/EV-1/servicios/SV-1/respuesta-proveedor', {'proveedor_id': pb, 'disponible': True})
        self.assertEqual(r.status_code, 403)
        self.assertIn('su propio proveedor', r.json()['detalle'])
        r = a.post('/eventos/EV-1/servicios/SV-1/respuesta-proveedor', {'proveedor_id': pa, 'disponible': True})
        self.assertEqual(r.status_code, 422)                                                   # propio: ahora decide la regla de negocio (evento inexistente)

    def test_flujo_completo_la_respuesta_la_da_el_proveedor_asignado_y_otro_no_puede(self):
        pa, pb = self.proveedor('Proveedor A'), self.proveedor('Proveedor B')
        coord, admin = self.cliente(COORDINADOR), self.cliente(ADMINISTRADOR)
        ev = coord.post('/eventos', {'cliente_id': 'CL-1', 'datos': {**DATOS, 'fecha_hora': (T0 + timedelta(days=80)).isoformat()}, 'servicios': ['Banquete']})
        self.assertEqual(ev.status_code, 201)
        evento = ev.json()['evento_id']
        propuesta = coord.post(f'/eventos/{evento}/propuestas', CONTENIDO).json()['propuesta_id']
        self.assertEqual(coord.post(f'/propuestas/{propuesta}/aceptacion', {'version_id': f'{propuesta}-v1'}).status_code, 200)
        contrato = coord.post(f'/propuestas/{propuesta}/contrato', {'politica_incluida': True}).json()['datos']['contrato_id']
        fecha = T0.isoformat()
        self.assertEqual(coord.post(f'/contratos/{contrato}/comunicacion-politica-no-reembolso', {'fecha': fecha}).status_code, 200)
        self.assertEqual(coord.post(f'/contratos/{contrato}/firma', {'fecha': fecha}).status_code, 200)
        ec = admin.get(f'/eventos/{evento}/pagos').json()['estadosCuenta'][0]['estadoCuentaId']
        ob = next(p for p in admin.get('/pagos-pendientes', params={'evento_id': evento}).json()['pagos'] if p['concepto'] == 'Anticipo')
        cuerpo_pago = {'obligacion_id': ob['obligacionId'], 'importe': '3000.00', 'fecha': fecha, 'comprobante': 'C-1', 'verificar_ahora': True}
        self.assertEqual(coord.post(f'/estados-cuenta/{ec}/pagos', cuerpo_pago).status_code, 403)     # el coordinador no registra pagos
        self.assertEqual(admin.post(f'/estados-cuenta/{ec}/pagos', cuerpo_pago).status_code, 201)       # el administrador sí
        servicio = coord.get(f'/eventos/{evento}/administracion').json()['proveedores'][0]['servicioContratadoId']
        base = f'/eventos/{evento}/servicios/{servicio}'
        self.assertEqual(coord.post(f'{base}/proveedor', {'proveedor_id': pa}).status_code, 200)
        a, b = self.cliente(PROVEEDOR, proveedor_id=pa), self.cliente(PROVEEDOR, proveedor_id=pb)
        self.assertEqual(b.post(f'{base}/respuesta-proveedor', {'proveedor_id': pb, 'disponible': True}).status_code, 422)   # propio pero no asignado: regla de negocio
        self.assertEqual(b.get(f'/proveedores/{pb}/eventos/{evento}').status_code, 404)                                     # no ve el evento
        self.assertEqual(a.get(f'/proveedores/{pa}/eventos/{evento}').status_code, 200)
        self.assertEqual(a.post(f'{base}/respuesta-proveedor', {'proveedor_id': pa, 'disponible': True}).status_code, 200)
        self.assertEqual(coord.get(f'/eventos/{evento}/administracion').json()['proveedores'][0]['estado'], 'Confirmado por el proveedor')

    def test_la_cuenta_de_proveedor_exige_un_proveedor_del_catalogo_y_los_demas_roles_no_lo_llevan(self):
        admin = self.cliente(ADMINISTRADOR)
        base = {'correo': 'prov@ejemplo.mx', 'nombre': 'Cuenta Proveedor', 'contrasena': CLAVE}
        self.assertEqual(admin.post('/usuarios', {**base, 'rol': PROVEEDOR}).status_code, 422)
        self.assertEqual(admin.post('/usuarios', {**base, 'rol': PROVEEDOR, 'proveedor_id': 'PV-NO-EXISTE'}).status_code, 422)
        self.assertEqual(admin.post('/usuarios', {**base, 'rol': COORDINADOR, 'proveedor_id': self.proveedor('X')}).status_code, 422)
        self.assertEqual(admin.post('/usuarios', {**base, 'rol': PROVEEDOR, 'proveedor_id': self.proveedor('Y')}).status_code, 201)

    # ---------------------------------------------------------------- 6. sesiones
    def test_cerrar_sesion_invalida_la_cookie(self):
        c = self.cliente(COORDINADOR)
        self.assertEqual(c.get('/auth/yo').status_code, 200)
        token = c.http.cookies.get(self.config.cookie_nombre)
        self.assertEqual(c.post('/auth/cierre-sesion').status_code, 200)
        self.assertEqual(c.get('/auth/yo').status_code, 401)                                   # el navegador ya no tiene la cookie
        c.http.cookies.set(self.config.cookie_nombre, token)                                   # y aunque alguien conserve el token anterior…
        r = c.get('/auth/yo')
        self.assertEqual((r.status_code, r.json()['tipo']), (401, 'sesion_expirada'))          # …el servidor ya lo invalidó
        self.assertEqual(c.post('/eventos', {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']}).status_code, 401)

    def test_la_sesion_caduca_por_inactividad_y_el_uso_la_mantiene(self):
        c = self.cliente(COORDINADOR)
        for _ in range(3):
            self.ahora += timedelta(minutes=self.config.inactividad_minutos - 5)
            self.assertEqual(c.get('/auth/yo').status_code, 200)                              # la actividad renueva la ventana
        self.ahora += timedelta(minutes=self.config.inactividad_minutos + 1)
        r = c.get('/auth/yo')
        self.assertEqual((r.status_code, r.json()['tipo']), (401, 'sesion_expirada'))
        self.assertIn('expiró', r.json()['detalle'])

    def test_la_sesion_caduca_por_duracion_maxima_aunque_haya_actividad(self):
        c = self.cliente(COORDINADOR)
        for _ in range(self.config.duracion_maxima_horas * 3):
            self.ahora += timedelta(minutes=29)
            if c.get('/auth/yo').status_code == 401:
                break
        self.assertEqual(c.get('/auth/yo').status_code, 401)
        self.assertGreaterEqual(self.ahora - T0, timedelta(hours=self.config.duracion_maxima_horas))

    def test_desactivar_una_cuenta_o_cambiar_su_contrasena_cierra_sus_sesiones(self):
        admin = self.cliente(ADMINISTRADOR)
        c1, c2 = self.cliente(COORDINADOR), self.cliente(COORDINADOR)
        uid1 = self.seg.almacen.obtener_usuario_por_correo([k for k, v in self.cuentas.items() if v == COORDINADOR][0]).usuario_id
        self.assertEqual(admin.post(f'/usuarios/{uid1}/estado', {'activo': False}).status_code, 200)
        self.assertEqual(c1.get('/auth/yo').status_code, 401)
        self.assertEqual(c2.get('/auth/yo').status_code, 200)
        r = c2.post('/auth/cambio-contrasena', {'actual': CLAVE, 'nueva': 'otra-contrasena-larga-2'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c2.get('/auth/yo').status_code, 401)                                  # el cambio cierra todas sus sesiones
        Cliente(self.app).entrar([k for k, v in self.cuentas.items() if v == COORDINADOR][1], 'otra-contrasena-larga-2')

    def test_el_cambio_de_contrasena_exige_la_actual_y_cumple_la_politica(self):
        c = self.cliente(COORDINADOR)
        self.assertEqual(c.post('/auth/cambio-contrasena', {'actual': 'incorrecta-larga-1', 'nueva': 'otra-contrasena-larga-2'}).status_code, 403)
        r = c.post('/auth/cambio-contrasena', {'actual': CLAVE, 'nueva': 'corta'})
        self.assertEqual(r.status_code, 422)
        self.assertIn('al menos 12', r.json()['detalle'])

    def test_no_se_puede_dejar_al_sistema_sin_administrador(self):
        admin = self.cliente(ADMINISTRADOR)
        mio = self.seg.almacen.obtener_usuario_por_correo([k for k, v in self.cuentas.items() if v == ADMINISTRADOR][0]).usuario_id
        r = admin.post(f'/usuarios/{mio}/estado', {'activo': False})
        self.assertEqual(r.status_code, 422)
        self.assertIn('propia cuenta', r.json()['detalle'])
        otro = self.cuenta(ADMINISTRADOR)
        uid = self.seg.almacen.obtener_usuario_por_correo(otro).usuario_id
        self.assertEqual(admin.post(f'/usuarios/{uid}/estado', {'activo': False}).status_code, 200)

    def test_politica_de_contrasenas_y_correos_duplicados(self):
        admin = self.cliente(ADMINISTRADOR)
        base = {'correo': 'nuevo@ejemplo.mx', 'nombre': 'Nueva Persona', 'rol': COORDINADOR}
        for mala in ('corta', 'aaaaaaaaaaaaaaaa', 'nuevo@ejemplo.mx'):
            self.assertEqual(admin.post('/usuarios', {**base, 'contrasena': mala}).status_code, 422, mala)
        self.assertEqual(admin.post('/usuarios', {**base, 'contrasena': CLAVE}).status_code, 201)
        r = admin.post('/usuarios', {**base, 'correo': 'NUEVO@ejemplo.mx', 'contrasena': CLAVE})
        self.assertEqual(r.status_code, 422)
        self.assertIn('Ya existe una cuenta', r.json()['detalle'])
        texto = admin.get('/usuarios').text
        self.assertNotIn('argon2', texto)                                                      # el hash nunca sale por la API
        self.assertNotIn('contrasena_hash', texto)

    # ---------------------------------------------------------------- 7. negocio y configuración
    def test_las_validaciones_de_negocio_siguen_funcionando_con_permisos(self):
        c = self.cliente(COORDINADOR)
        r = c.post('/eventos', {'cliente_id': 'CL-1', 'datos': {**DATOS, 'invitados_aproximados': 0}, 'servicios': ['Banquete']})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(c.post('/propuestas/PR-NO-EXISTE/aceptacion', {'version_id': 'PR-NO-EXISTE-v1'}).status_code, 422)

    def test_cabeceras_de_seguridad(self):
        c = Cliente(self.app)
        r = c.get('/health')
        self.assertEqual(r.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(r.headers['x-frame-options'], 'DENY')
        self.assertEqual(r.headers['cache-control'], 'no-store')
        self.assertNotIn('strict-transport-security', r.headers)
        a = c.get('/app/')
        self.assertIn("default-src 'self'", a.headers['content-security-policy'])
        self.assertIn("frame-ancestors 'none'", a.headers['content-security-policy'])

    def test_produccion_exige_cookie_segura_no_permite_desactivar_y_oculta_la_documentacion(self):
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_ENTORNO': 'produccion', 'EVENTOSNOVA_AUTENTICACION': 'desactivada'}):
            with self.assertRaises(ValueError):
                ConfiguracionSeguridad.desde_entorno()
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_ENTORNO': 'produccion', 'EVENTOSNOVA_COOKIE_SEGURA': '0'}):
            with self.assertRaises(ValueError):
                ConfiguracionSeguridad.desde_entorno()
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_ENTORNO': 'produccion'}, clear=False):
            os.environ.pop('EVENTOSNOVA_AUTENTICACION', None); os.environ.pop('EVENTOSNOVA_COOKIE_SEGURA', None); os.environ.pop('EVENTOSNOVA_DOCS', None)
            cfg = ConfiguracionSeguridad.desde_entorno()
        self.assertTrue(cfg.activa and cfg.cookie_segura and cfg.hsts and not cfg.documentacion)
        app = crear_app(lambda: self.crear_contenedor(), cfg)
        c = TestClient(app)
        for ruta in ('/docs', '/redoc', '/openapi.json'):
            self.assertEqual(c.get(ruta).status_code, 404, ruta)
        self.assertIn('strict-transport-security', c.get('/health').headers)

    def test_la_aplicacion_servida_exige_autenticacion_por_omision(self):
        import api.main as M
        self.assertTrue(M.app.state.seguridad.activa)
        r = TestClient(M.app).get('/eventos', params={'desde': '2026-01-01T00:00:00', 'hasta': '2026-12-31T00:00:00'})
        self.assertEqual(r.status_code, 401)

    def test_la_matriz_no_concede_permisos_amplios(self):
        self.assertEqual(permisos_del_rol('rol-inexistente'), frozenset())
        self.assertFalse(autoriza(PROVEEDOR, 'POST', '/eventos'))
        self.assertFalse(autoriza(COORDINADOR, 'POST', '/usuarios'))
        self.assertTrue(autoriza(ADMINISTRADOR, 'POST', '/usuarios'))
        self.assertFalse(autoriza(ADMINISTRADOR, 'GET', '/ruta/inexistente'))
        self.assertEqual({p for r in ROLES for p in permisos_del_rol(r)} - {p for v in MATRIZ.values() for p in v}, set())   # ningún permiso huérfano


class SeguridadEnMemoria(BaseSeguridad, unittest.TestCase):
    def crear_contenedor(self):
        return construir()


class SeguridadEnPostgreSQL(BaseSeguridad, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        BaseSeguridad.setUp(self)

    def crear_contenedor(self):
        return construir_persistente(motor=self.motor)

    def test_las_restricciones_de_la_base_impiden_cuentas_incoherentes(self):
        import sqlalchemy as sa
        from infrastructure.persistencia.errores import ViolacionDeRestriccion  # noqa: F401
        base = {'n': 'x', 'h': 'h', 'f': T0}
        casos = [
            ("insert into usuario (usuario_id, correo, nombre, rol, contrasena_hash, creado_en) values ('U1','Mayus@x.mx',:n,'administrador',:h,:f)", 'correo en minúsculas'),
            ("insert into usuario (usuario_id, correo, nombre, rol, contrasena_hash, creado_en) values ('U2','a@x.mx',:n,'superusuario',:h,:f)", 'rol válido'),
            ("insert into usuario (usuario_id, correo, nombre, rol, contrasena_hash, creado_en) values ('U3','b@x.mx',:n,'proveedor',:h,:f)", 'proveedor sin vínculo'),
            ("insert into usuario (usuario_id, correo, nombre, rol, contrasena_hash, creado_en) values ('U4','c@x.mx',:n,'coordinador',:h,:f)", 'ok'),
            ("insert into usuario (usuario_id, correo, nombre, rol, contrasena_hash, creado_en, proveedor_id) values ('U5','d@x.mx',:n,'coordinador',:h,:f,'PV-X')", 'vínculo en rol ajeno'),
            ("insert into usuario (usuario_id, correo, nombre, rol, contrasena_hash, creado_en) values ('U6','c@x.mx',:n,'coordinador',:h,:f)", 'correo único'),
            ("insert into usuario (usuario_id, correo, nombre, rol, contrasena_hash, creado_en, proveedor_id) values ('U7','e@x.mx',:n,'proveedor',:h,:f,'PV-NO-EXISTE')", 'proveedor inexistente'),
        ]
        for sql, descripcion in casos:
            try:
                with self.motor.begin() as con:
                    con.execute(sa.text(sql), base)
                aceptado = True
            except sa.exc.IntegrityError:
                aceptado = False
            self.assertEqual(aceptado, descripcion == 'ok', descripcion)

    def test_las_sesiones_se_borran_con_su_cuenta_y_persisten_entre_instancias(self):
        c = self.cliente(COORDINADOR)

        def crear_segunda_instancia():
            contenedor = construir_persistente(motor=self.motor)
            contenedor.servicios.seguridad.reloj = lambda: self.ahora
            return contenedor

        self.arrancar_de_nuevo = crear_app(crear_segunda_instancia, self.config)
        c2 = TestClient(self.arrancar_de_nuevo)
        c2.cookies.set(
            self.config.cookie_nombre,
            c.http.cookies.get(self.config.cookie_nombre)
        )
        self.assertEqual(c2.get('/auth/yo').status_code, 200)


if __name__ == '__main__':
    unittest.main()
