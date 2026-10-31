"""Incremento 2.2 — validación de datos de entrada en la API (POST /eventos y POST /eventos/{id}/propuestas).

La API valida la forma y el tipo del dato; las invariantes (importe no negativo, invitados > 0) las aplica el dominio y se
devuelven con el formato de rechazo de negocio existente (HTTP 422, tipo «rechazo_de_negocio»). Una entrada con tipo
incorrecto devuelve el 422 estándar de validación de FastAPI."""
import os, sys, unittest
from datetime import datetime
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from fastapi.testclient import TestClient                                          # noqa: E402
from api.main import crear_app                                                     # noqa: E402
from api.dependencias import obtener_reloj                                         # noqa: E402

AHORA = datetime(2026, 10, 1, 10, 0)
DATOS = {'tipo': 'Boda', 'fecha_hora': '2026-11-20T18:00:00', 'lugar': 'Salón', 'invitados_aproximados': 100}
EVENTO = {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']}
CONTENIDO = {'servicios': ['Banquete'], 'proveedores_considerados': ['PV-1'], 'costo_total': '10000.00',
             'condiciones': 'Condiciones generales'}


class _Base(unittest.TestCase):
    def setUp(self):
        self.app = crear_app()
        self.app.dependency_overrides[obtener_reloj] = lambda: (lambda: AHORA)
        self.cliente = TestClient(self.app)
        self.repos = self.app.state.contenedor.repos

    def evento(self, **datos):
        return self.cliente.post('/eventos', json={**EVENTO, 'datos': {**DATOS, **datos}})

    def propuesta(self, **cambios):
        evento_id = self.cliente.post('/eventos', json=EVENTO).json()['evento_id']
        return self.cliente.post(f'/eventos/{evento_id}/propuestas', json={**CONTENIDO, **cambios})

    def assertValidacion422(self, r):
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn('detail', r.json())                       # 422 estándar de validación de forma/tipo

    def assertRechazoNegocio(self, r, fragmento):
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()['tipo'], 'rechazo_de_negocio')
        self.assertIn(fragmento, r.json()['detalle'])


class CostoTotal(_Base):
    def test_valores_validos(self):
        for valor in ('125.50', '0', '0.00', '10000.00', '12.345678901234', '1000'):
            with self.subTest(valor):
                r = self.propuesta(costo_total=valor)
                self.assertEqual(r.status_code, 201, r.text)

    def test_no_se_redondea_al_guardar(self):
        r = self.propuesta(costo_total='12.345678901234')
        p = self.repos.propuestas.obtener_por_id(r.json()['propuesta_id'])
        self.assertEqual(p.versiones[0].contenido.costo_total.cantidad, D('12.345678901234'))

    def test_letras_y_cadenas_no_numericas(self):
        for valor in ('ciento', 'mucho', '12abc', '1,000.00 MXN', '', ' ', '--5', '1.2.3'):
            with self.subTest(valor):
                self.assertValidacion422(self.propuesta(costo_total=valor))

    def test_no_finitos(self):
        for valor in ('NaN', 'nan', 'sNaN', 'Infinity', '-Infinity', 'inf', '-inf'):
            with self.subTest(valor):
                self.assertValidacion422(self.propuesta(costo_total=valor))

    def test_negativos_los_rechaza_el_dominio_con_el_formato_de_rechazo(self):
        for valor in ('-1', '-0.01', '-10000.00'):
            with self.subTest(valor):
                self.assertRechazoNegocio(self.propuesta(costo_total=valor), 'negativo')

    def test_tipos_incorrectos(self):
        for valor in (True, False, None, [], {}, [1]):
            with self.subTest(repr(valor)):
                self.assertValidacion422(self.propuesta(costo_total=valor))

    def test_omitido(self):
        evento_id = self.cliente.post('/eventos', json=EVENTO).json()['evento_id']
        cuerpo = {k: v for k, v in CONTENIDO.items() if k != 'costo_total'}
        self.assertValidacion422(self.cliente.post(f'/eventos/{evento_id}/propuestas', json=cuerpo))

    def test_un_rechazo_no_guarda_propuestas(self):
        self.propuesta(costo_total='NaN')
        self.propuesta(costo_total='-1')
        self.assertEqual(self.repos.propuestas.listar_por_evento_id('x'), [])
        self.assertEqual(len([p for e in self.repos.eventos.listar_todos()
                              for p in self.repos.propuestas.listar_por_evento_id(e.id)]), 0)


class InvitadosAproximados(_Base):
    def test_validos(self):
        for valor in (1, 100, 2147483648, '12', 12.0):          # los textos numéricos y 12.0 se aceptaban antes
            with self.subTest(repr(valor)):
                self.assertEqual(self.evento(invitados_aproximados=valor).status_code, 201)

    def test_letras_decimales_y_notacion(self):
        for valor in ('abc', 'cien', '12.5', 12.5, '1e2', '', '1 2'):
            with self.subTest(repr(valor)):
                self.assertValidacion422(self.evento(invitados_aproximados=valor))

    def test_booleanos_ya_no_se_convierten_en_enteros(self):
        for valor in (True, False):
            with self.subTest(repr(valor)):
                self.assertValidacion422(self.evento(invitados_aproximados=valor))

    def test_no_positivos_los_rechaza_el_dominio(self):          # CA-003
        for valor in (0, -1, -100, '0', '-5'):
            with self.subTest(repr(valor)):
                self.assertRechazoNegocio(self.evento(invitados_aproximados=valor), 'CA-003')

    def test_nulo_u_omitido(self):
        self.assertValidacion422(self.evento(invitados_aproximados=None))
        datos = {k: v for k, v in DATOS.items() if k != 'invitados_aproximados'}
        self.assertValidacion422(self.cliente.post('/eventos', json={**EVENTO, 'datos': datos}))


class LimiteTecnicoDeInvitadosApi(_Base):
    """Incremento 2.4: 9223372036854775807 (BIGINT) se acepta; lo superior se rechaza con 422 y no llega a ningún repositorio."""
    MAXIMO = 9223372036854775807

    def test_el_maximo_de_bigint_se_acepta_y_se_conserva_exacto(self):
        r = self.evento(invitados_aproximados=self.MAXIMO)
        self.assertEqual(r.status_code, 201, r.text)
        ev = self.repos.eventos.obtener_por_id(r.json()['evento_id'])
        self.assertEqual(ev.datos.invitados_aproximados, self.MAXIMO)

    def test_superiores_al_maximo_devuelven_422_no_500(self):
        for valor in (self.MAXIMO + 1, 2 ** 64, 10 ** 30, str(self.MAXIMO + 1)):
            with self.subTest(repr(valor)):
                r = self.evento(invitados_aproximados=valor)
                self.assertEqual(r.status_code, 422, r.text)
                self.assertIn('9223372036854775807', r.text)

    def test_un_valor_fuera_de_rango_no_guarda_nada(self):
        self.evento(invitados_aproximados=self.MAXIMO + 1)
        self.assertEqual(self.repos.eventos.listar_todos(), [])

    def test_se_conserva_el_comportamiento_de_los_demas_valores(self):
        for valor in (1, 100, '12', '9223372036854775807'):
            with self.subTest(repr(valor)):
                self.assertEqual(self.evento(invitados_aproximados=valor).status_code, 201)
        self.assertRechazoNegocio(self.evento(invitados_aproximados=0), 'CA-003')
        self.assertRechazoNegocio(self.evento(invitados_aproximados=-1), 'CA-003')
        for valor in (True, False, 12.5, '12.5', 'abc', '', None):
            with self.subTest(repr(valor)):
                self.assertValidacion422(self.evento(invitados_aproximados=valor))

    def test_el_dominio_tambien_rechaza_si_alguien_esquiva_el_esquema(self):
        from api.esquemas import DatosEventoEntrada
        from domain.valores import ErrorDominio
        entrada = DatosEventoEntrada.model_construct(tipo='Boda', fecha_hora=AHORA, lugar='X',
                                                      invitados_aproximados=self.MAXIMO + 1)
        with self.assertRaises(ErrorDominio):
            entrada.a_dominio()


class CamposDeTexto(_Base):
    """tipo, lugar y condiciones son texto libre: ninguna fuente aprobada limita sus caracteres, así que los dígitos son válidos."""
    def test_textos_con_digitos_y_signos_son_validos(self):
        for tipo, lugar in (('Boda 2', 'Salón 5, Av. Juárez #123'), ('123', '456'), ('XV años', 'Jardín "Las Rosas" 2')):
            with self.subTest((tipo, lugar)):
                self.assertEqual(self.evento(tipo=tipo, lugar=lugar).status_code, 201)

    def test_condiciones_y_servicios_con_digitos(self):
        self.assertEqual(self.propuesta(condiciones='Pago a 30 días; anticipo 30 %', servicios=['Banquete 3 tiempos']).status_code, 201)

    def test_tipos_incorrectos_en_texto(self):
        for campo in ('tipo', 'lugar'):
            for valor in (5, 1.5, True, [], {}, None):
                with self.subTest((campo, repr(valor))):
                    self.assertValidacion422(self.evento(**{campo: valor}))
        for valor in (5, None, ['x'], {}):
            with self.subTest(('condiciones', repr(valor))):
                self.assertValidacion422(self.propuesta(condiciones=valor))

    def test_vacios_los_rechaza_el_dominio(self):                # CA-003, CA-005
        self.assertRechazoNegocio(self.evento(tipo=''), 'CA-003')
        self.assertRechazoNegocio(self.evento(lugar=''), 'CA-003')
        self.assertRechazoNegocio(self.propuesta(condiciones=''), 'CA-005')
        self.assertRechazoNegocio(self.propuesta(servicios=[]), 'CA-005')


class ContratoDeLaApi(_Base):
    def test_la_respuesta_exitosa_no_cambia(self):
        r = self.cliente.post('/eventos', json=EVENTO)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(sorted(r.json()), ['evento_id', 'mensaje'])
        r2 = self.cliente.post(f"/eventos/{r.json()['evento_id']}/propuestas", json=CONTENIDO)
        self.assertEqual(sorted(r2.json()), ['evento_id', 'mensaje', 'propuesta_id'])


if __name__ == '__main__':
    unittest.main()
