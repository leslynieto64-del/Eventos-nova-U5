"""Etapa 2 (fase final): identificadores nuevos con UUID completo y sin sobrescritura accidental de agregados.

Garantía estadística: UUID versión 4 aporta 122 bits aleatorios; con 10^12 identificadores la probabilidad de alguna colisión
sigue siendo del orden de 10^-13. No se afirma que sea imposible: por eso la creación de una raíz comprueba que el id no exista
(`nuevo_id_libre`) y la base de datos conserva sus claves primarias. Los identificadores históricos (8 caracteres hexadecimales,
p. ej. EV-0028db33) siguen siendo válidos.
Ejecutar desde la raíz:  python -m unittest tests.test_identificadores -v"""
import os, re, sys, unittest, uuid
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import sqlalchemy as sa                                                                   # noqa: E402
from apoyo_bd import BaseConBD                                                            # noqa: E402
from test_reglas_corregidas import CONTENIDO, FECHA_EVENTO, T0                           # noqa: E402
import apoyo_persistencia as AP                                                           # noqa: E402
from application import servicios as S                                                    # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                             # noqa: E402
from domain.evento import Evento                                                          # noqa: E402
from domain.valores import ConceptoPago, DatosEvento, ErrorDominio, Importe              # noqa: E402
from infrastructure.composicion import construir                                          # noqa: E402
from infrastructure.persistencia import repositorios_sql as R                             # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente    # noqa: E402

UUID4 = re.compile(r'^[A-Z]{2}-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')


class Formato(unittest.TestCase):
    def test_los_ids_nuevos_son_prefijo_mas_uuid_v4_completo(self):
        for prefijo in ('EV', 'PR', 'CT', 'EC', 'OB', 'PG', 'DV', 'SC', 'SA', 'SP', 'AX'):
            i = S.nuevo_id(prefijo)
            self.assertRegex(i, UUID4)
            self.assertEqual(i.split('-', 1)[0], prefijo)
            self.assertEqual(uuid.UUID(i.split('-', 1)[1]).version, 4)

    def test_diez_mil_ids_son_distintos(self):
        self.assertEqual(len({S.nuevo_id('EV') for _ in range(10_000)}), 10_000)

    def test_el_ejemplo_historico_de_8_caracteres_ya_no_se_genera(self):
        self.assertNotRegex(S.nuevo_id('EV'), r'^EV-[0-9a-f]{8}$')


class SinSobrescrituraAccidental(unittest.TestCase):
    def test_una_colision_forzada_no_sobrescribe_el_evento_existente(self):
        app = construir()
        fijo = uuid.UUID('12345678-1234-4234-8234-123456789abc')
        with mock.patch.object(S.uuid, 'uuid4', side_effect=[fijo, fijo, uuid.uuid4()]):
            r1 = app.servicios.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete'])
            r2 = app.servicios.propuestas.registrar_evento('CL-2', DatosEvento('XV', FECHA_EVENTO, 'Jardín', 80), ['Música'])
        self.assertEqual(r1.datos['evento_id'], 'EV-' + str(fijo))
        self.assertNotEqual(r2.datos['evento_id'], r1.datos['evento_id'])
        self.assertEqual(app.repos.eventos.obtener_por_id(r1.datos['evento_id']).cliente_id, 'CL-1')      # el primero sigue intacto
        self.assertEqual(app.repos.eventos.obtener_por_id(r2.datos['evento_id']).cliente_id, 'CL-2')

    def test_si_no_hay_ids_libres_se_falla_en_vez_de_sobrescribir(self):
        class Lleno:
            def obtener_por_id(self, _): return object()
        with self.assertRaises(RuntimeError):
            S.nuevo_id_libre('EV', Lleno())

    def test_una_obligacion_o_un_pago_con_id_repetido_se_rechaza(self):
        ec = EstadoCuenta('EC-1', 'CT-1', 'EV-1')
        ec.comunicar_solicitud_pago('OB-1', ConceptoPago.CAMBIO, Importe(D(100)), 'SC-1', T0)
        with self.assertRaises(ErrorDominio):
            ec.comunicar_solicitud_pago('OB-1', ConceptoPago.CARGO_CAMBIO_TARDIO, Importe(D(50)), 'SC-1', T0)
        self.assertEqual(ec.obligaciones['OB-1'].concepto, ConceptoPago.CAMBIO)
        ec.registrar_y_verificar_pago('PG-1', 'OB-1', Importe(D(100)), T0, 'C', False)
        with self.assertRaises(ErrorDominio):
            ec.registrar_y_verificar_pago('PG-1', 'OB-1', Importe(D(7)), T0, 'D', False)
        self.assertEqual([p.importe.cantidad for p in ec.pagos], [D(100)])
        # la repetición idempotente de la misma obligación (mismo concepto y origen) sigue permitida
        self.assertIs(ec.comunicar_solicitud_pago('OB-2', ConceptoPago.CAMBIO, Importe(D(100)), 'SC-1', T0), ec.obligaciones['OB-1'])


class EnPostgreSQL(BaseConBD):
    def test_ids_largos_y_ids_historicos_se_guardan_y_recuperan_exactos(self):
        app = construir_persistente(motor=self.motor)
        largo = app.servicios.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        self.assertRegex(largo, UUID4)
        self.assertEqual(app.repos.eventos.obtener_por_id(largo).id, largo)
        historico = Evento('EV-0028db33', 'CL-H', DatosEvento('Antigua', FECHA_EVENTO, 'Sala', 10), ['Banquete'])
        app.repos.eventos.guardar(historico)
        self.assertEqual(app.repos.eventos.obtener_por_id('EV-0028db33').cliente_id, 'CL-H')

    def test_las_claves_foraneas_aceptan_ambos_formatos(self):
        app = construir_persistente(motor=self.motor)
        s = app.servicios
        historico = Evento('EV-0028db33', 'CL-H', DatosEvento('Antigua', FECHA_EVENTO, 'Sala', 10), ['Banquete'])
        app.repos.eventos.guardar(historico)
        pid = s.propuestas.crear_propuesta('EV-0028db33', CONTENIDO, T0).datos['propuesta_id']          # id nuevo (largo) → evento histórico
        self.assertRegex(pid, UUID4)
        self.assertEqual(app.repos.propuestas.obtener_por_id(pid).evento_id, 'EV-0028db33')
        with self.motor.connect() as con:
            n = con.execute(sa.text('select count(*) from propuesta where evento_id = :e'), {'e': 'EV-0028db33'}).scalar()
        self.assertEqual(n, 1)

    def test_la_clave_primaria_rechaza_una_insercion_duplicada(self):
        app = construir_persistente(motor=self.motor)
        eid = app.servicios.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        with self.assertRaises(sa.exc.IntegrityError), self.motor.begin() as con:
            con.execute(sa.text("insert into evento select * from evento where evento_id = :e"), {'e': eid})
        self.assertEqual(app.repos.eventos.obtener_por_id(eid).cliente_id, 'CL-1')

    def test_una_colision_forzada_en_postgresql_no_sobrescribe(self):
        app = construir_persistente(motor=self.motor)
        fijo = uuid.UUID('abcdefab-1234-4234-8234-123456789abc')
        with mock.patch.object(S.uuid, 'uuid4', side_effect=[fijo, fijo, uuid.uuid4()]):
            a = app.servicios.propuestas.registrar_evento('CL-A', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
            b = app.servicios.propuestas.registrar_evento('CL-B', DatosEvento('XV', FECHA_EVENTO, 'Jardín', 80), ['Música']).datos['evento_id']
        self.assertNotEqual(a, b)
        self.assertEqual((app.repos.eventos.obtener_por_id(a).cliente_id, app.repos.eventos.obtener_por_id(b).cliente_id), ('CL-A', 'CL-B'))


if __name__ == '__main__':
    unittest.main()
