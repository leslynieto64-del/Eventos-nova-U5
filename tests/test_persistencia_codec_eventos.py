"""Etapa 6 — codec de Domain Events (sin base de datos): inventario real, ida y vuelta de TODOS los tipos y errores controlados."""
import dataclasses, inspect, json, os, sys, unittest
from datetime import datetime
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from domain import eventos_dominio as E                                                  # noqa: E402
from domain.valores import CondicionesServicio, DatosEvento, EstadoEvento, Importe       # noqa: E402
from infrastructure.persistencia import codec_eventos as C                               # noqa: E402
from infrastructure.persistencia.errores import ErrorDePersistencia, EventoNoRehidratable   # noqa: E402

OCURRIDO = datetime(2026, 10, 1, 10, 0, 0, 123456)
MUESTRAS = {
    'numero': 7, 'viable': True,
    'datos_propuestos': DatosEvento('Boda 2', datetime(2026, 11, 20, 20, 0), 'Jardín #5', 9223372036854775807),
    'condiciones_propuestas': (('CT-1-S1', CondicionesServicio('Menú nuevo')), ('CT-1-S2', CondicionesServicio('Música en vivo'))),
    'condiciones': CondicionesServicio('Foto 4 h'),
}


def clases_del_dominio():
    return [c for _, c in inspect.getmembers(E, inspect.isclass) if issubclass(c, E.EventoDominio) and c is not E.EventoDominio]


def ejemplo(clase, completo=True):
    campos = {f.name: MUESTRAS.get(f.name, f'valor-{f.name}') for f in C.campos_propios(clase)} if completo else {}
    return clase(agregado_id='AG-1', ocurrido_en=OCURRIDO, **campos)


class Inventario(unittest.TestCase):
    def test_el_registro_explicito_coincide_con_los_eventos_reales_del_dominio(self):
        reales = clases_del_dominio()
        self.assertEqual(len(reales), 31)                                       # inventario obtenido del código, no supuesto
        self.assertEqual(set(C.TIPOS_DE_EVENTO), set(reales))
        self.assertEqual(len(C.TIPOS_DE_EVENTO), len(set(C.TIPOS_DE_EVENTO)))   # sin duplicados
        self.assertEqual(set(C.REGISTRO), {c.__name__ for c in reales})

    def test_los_campos_comunes_no_se_serializan_dos_veces(self):
        for clase in clases_del_dominio():
            self.assertTrue(set(C.CAMPOS_COMUNES).isdisjoint(f.name for f in C.campos_propios(clase)), clase.__name__)


class IdaYVueltaDeCadaTipo(unittest.TestCase):
    def test_los_31_tipos_se_reconstruyen_iguales(self):
        for clase in clases_del_dominio():
            for completo in (True, False):                                      # con todos los campos y con los valores por defecto
                with self.subTest(f'{clase.__name__} completo={completo}'):
                    original = ejemplo(clase, completo)
                    datos = json.loads(json.dumps(C.codificar(original)))        # pasa por JSON real, como JSONB
                    nuevo = C.decodificar(clase.__name__, original.agregado_id, original.ocurrido_en, original.evento_id, datos)
                    self.assertEqual(nuevo, original)
                    self.assertIs(type(nuevo), clase)
                    self.assertEqual(nuevo.evento_id, original.evento_id)         # identificación estable
                    self.assertEqual(nuevo.ocurrido_en, OCURRIDO)                 # microsegundos incluidos

    def test_los_objetos_de_valor_y_las_tuplas_conservan_su_tipo(self):
        e = ejemplo(E.CambioConfirmado)
        nuevo = C.decodificar('CambioConfirmado', e.agregado_id, e.ocurrido_en, e.evento_id, json.loads(json.dumps(C.codificar(e))))
        self.assertIsInstance(nuevo.datos_propuestos, DatosEvento)
        self.assertEqual(nuevo.datos_propuestos.invitados_aproximados, 9223372036854775807)
        self.assertIsInstance(nuevo.condiciones_propuestas, tuple)
        self.assertIsInstance(nuevo.condiciones_propuestas[0], tuple)
        self.assertIsInstance(nuevo.condiciones_propuestas[0][1], CondicionesServicio)
        s = ejemplo(E.ServicioAdicionalConfirmado)
        self.assertIsInstance(C.decodificar('ServicioAdicionalConfirmado', s.agregado_id, s.ocurrido_en, s.evento_id,
                                            C.codificar(s)).condiciones, CondicionesServicio)

    def test_campos_opcionales_en_none(self):
        e = E.CambioConfirmado(agregado_id='SC-1', ocurrido_en=OCURRIDO)        # datos_propuestos=None, condiciones=()
        nuevo = C.decodificar('CambioConfirmado', 'SC-1', OCURRIDO, e.evento_id, C.codificar(e))
        self.assertIsNone(nuevo.datos_propuestos)
        self.assertEqual(nuevo.condiciones_propuestas, ())

    def test_la_estructura_es_versionada_y_solo_lleva_los_campos_propios(self):
        datos = C.codificar(ejemplo(E.PagoVerificado))
        self.assertEqual(datos['version'], C.VERSION_ACTUAL)
        self.assertEqual(set(datos['campos']), {'obligacion_id', 'concepto', 'origen_id'})


class ValoresDelCodec(unittest.TestCase):
    def test_decimal_importe_enum_datetime_y_listas(self):
        for valor in (D('125.50'), D('0.10'), D('12345678901234567890.123456789'), Importe(D('99.9')), EstadoEvento.CANCELADO,
                      datetime(2026, 1, 2, 3, 4, 5, 6), (1, ('a', None)), [1, 2, 3], None, True, 0, ''):
            with self.subTest(repr(valor)):
                j = json.loads(json.dumps(C.codificar_valor(valor)))
                nuevo = C.decodificar_valor(j)
                self.assertEqual(nuevo, valor)
                self.assertIs(type(nuevo), type(valor))
        self.assertEqual(str(C.decodificar_valor(C.codificar_valor(D('1.50')))), '1.50')    # la escala no se pierde

    def test_un_float_nunca_se_serializa(self):
        with self.assertRaises(ErrorDePersistencia):
            C.codificar_valor(1.5)

    def test_un_tipo_no_soportado_se_rechaza(self):
        with self.assertRaises(ErrorDePersistencia):
            C.codificar_valor({'a': 1})
        with self.assertRaises(ErrorDePersistencia):
            C.codificar_valor(object())

    def test_un_evento_no_registrado_no_se_serializa(self):
        @dataclasses.dataclass(frozen=True)
        class EventoNuevo(E.EventoDominio):
            algo: str = ''
        with self.assertRaises(ErrorDePersistencia):
            C.codificar(EventoNuevo(agregado_id='X', ocurrido_en=OCURRIDO))


class ErroresControlados(unittest.TestCase):
    VALIDOS = {'version': 1, 'campos': {'evento_ref': 'EV-1'}}

    def decodificar(self, tipo='PropuestaAceptada', datos=VALIDOS):
        return C.decodificar(tipo, 'AG-1', OCURRIDO, 'ID-1', datos)

    def test_tipo_desconocido(self):
        with self.assertRaises(EventoNoRehidratable) as ctx:
            self.decodificar('EventoQueNoExiste')
        self.assertEqual((ctx.exception.evento_id, ctx.exception.tipo_evento), ('ID-1', 'EventoQueNoExiste'))
        self.assertIn('desconocido', str(ctx.exception))

    def test_version_incompatible(self):
        for datos in ({'version': 2, 'campos': {}}, {'version': None, 'campos': {}}, {'campos': {}}, {'version': 1}, [], 'x', None):
            with self.subTest(repr(datos)):
                with self.assertRaises(EventoNoRehidratable) as ctx:
                    self.decodificar(datos=datos)
                self.assertIn('versión', str(ctx.exception))

    def test_campos_desconocidos(self):
        with self.assertRaises(EventoNoRehidratable) as ctx:
            self.decodificar(datos={'version': 1, 'campos': {'evento_ref': 'EV-1', 'otro': 'x'}})
        self.assertIn('otro', str(ctx.exception))

    def test_datos_corruptos(self):
        malos = [{'evento_ref': {'$t': 'vo', 'clase': 'Inexistente', 'campos': {}}},
                 {'evento_ref': {'$t': 'datetime', 'v': 'no es una fecha'}},
                 {'evento_ref': {'$t': 'enum', 'clase': 'EstadoEvento', 'v': 'NO_EXISTE'}},
                 {'evento_ref': {'$t': 'decimal', 'v': 'abc'}},
                 {'evento_ref': {'sin': 'etiqueta'}}]
        for campos in malos:
            with self.subTest(repr(campos)):
                with self.assertRaises(EventoNoRehidratable) as ctx:
                    self.decodificar(datos={'version': 1, 'campos': campos})
                self.assertIsNotNone(ctx.exception.__cause__)

    def test_un_objeto_de_valor_invalido_no_se_reconstruye(self):
        malo = {'$t': 'vo', 'clase': 'DatosEvento', 'campos': {'tipo': '', 'fecha_hora': {'$t': 'datetime', 'v': '2026-01-01T00:00:00'},
                                                               'lugar': 'x', 'invitados_aproximados': 5}}
        with self.assertRaises(EventoNoRehidratable):
            C.decodificar('CambioConfirmado', 'SC-1', OCURRIDO, 'ID-2', {'version': 1, 'campos': {'datos_propuestos': malo}})


if __name__ == '__main__':
    unittest.main()
