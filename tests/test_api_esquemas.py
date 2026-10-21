"""Etapa 3A — esquemas de la API y su conversión a objetos del dominio (requiere Pydantic, incluido con FastAPI).

Comprueba que los esquemas solo validan la forma de la petición y que las reglas siguen en el dominio."""
import os, sys, unittest
from datetime import datetime, timezone
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from pydantic import ValidationError                                              # noqa: E402
from api.esquemas import DatosEventoEntrada, RegistrarEventoEntrada, CrearPropuestaEntrada   # noqa: E402
from domain.valores import DatosEvento, ContenidoPropuesta, Importe, ErrorDominio # noqa: E402

DATOS = {'tipo': 'Boda', 'fecha_hora': '2026-11-20T18:00:00', 'lugar': 'Salón', 'invitados_aproximados': 100}
CONTENIDO = {'servicios': ['Banquete'], 'proveedores_considerados': ['PV-1'], 'costo_total': '10000.00',
             'condiciones': 'Condiciones generales'}


class ConversionADominio(unittest.TestCase):
    def test_datos_evento(self):
        d = DatosEventoEntrada.model_validate(DATOS).a_dominio()
        self.assertEqual(d, DatosEvento('Boda', datetime(2026, 11, 20, 18, 0), 'Salón', 100))

    def test_contenido_propuesta(self):
        c = CrearPropuestaEntrada.model_validate(CONTENIDO).a_dominio()
        self.assertEqual(c, ContenidoPropuesta(('Banquete',), ('PV-1',), Importe(D('10000.00')), 'Condiciones generales'))

    def test_registrar_evento_con_datos_anidados(self):
        e = RegistrarEventoEntrada.model_validate({'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']})
        self.assertEqual(e.servicios, ['Banquete'])
        self.assertIsInstance(e.datos.a_dominio(), DatosEvento)


class ValidacionDeForma(unittest.TestCase):
    def test_campo_obligatorio_ausente(self):
        with self.assertRaises(ValidationError):
            DatosEventoEntrada.model_validate({k: v for k, v in DATOS.items() if k != 'lugar'})

    def test_campo_desconocido(self):
        with self.assertRaises(ValidationError):
            CrearPropuestaEntrada.model_validate({**CONTENIDO, 'descuento': '10'})

    def test_tipo_incorrecto(self):
        with self.assertRaises(ValidationError):
            DatosEventoEntrada.model_validate({**DATOS, 'invitados_aproximados': 'muchos'})

    def test_fecha_con_zona_horaria(self):
        """El dominio compara fechas sin zona; una fecha con zona se rechaza en lugar de convertirse."""
        with self.assertRaises(ValidationError):
            DatosEventoEntrada.model_validate({**DATOS, 'fecha_hora': datetime(2026, 11, 20, 18, tzinfo=timezone.utc)})


class LasReglasSiguenEnElDominio(unittest.TestCase):
    """El esquema acepta la forma; el dominio aplica la regla al convertir."""

    def test_invitados_no_positivos_los_rechaza_el_dominio(self):
        entrada = DatosEventoEntrada.model_validate({**DATOS, 'invitados_aproximados': 0})
        with self.assertRaisesRegex(ErrorDominio, 'CA-003'):
            entrada.a_dominio()

    def test_importe_negativo_lo_rechaza_el_dominio(self):
        entrada = CrearPropuestaEntrada.model_validate({**CONTENIDO, 'costo_total': '-1'})
        with self.assertRaisesRegex(ErrorDominio, 'negativo'):
            entrada.a_dominio()

    def test_propuesta_sin_servicios_la_rechaza_el_dominio(self):
        entrada = CrearPropuestaEntrada.model_validate({**CONTENIDO, 'servicios': []})
        with self.assertRaisesRegex(ErrorDominio, 'CA-005'):
            entrada.a_dominio()


if __name__ == '__main__':
    unittest.main()
