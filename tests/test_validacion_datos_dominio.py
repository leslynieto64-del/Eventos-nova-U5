"""Incremento 2.2 — validación de datos en el dominio: importes finitos, no negativos y de tipo Decimal, tipos de DatosEvento
y objetos de valor que transportan dinero. No cambia reglas de negocio: solo impide que entradas inválidas pasen como válidas."""
import os, sys, unittest
from datetime import datetime
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from domain.valores import (MAXIMO_TECNICO_BIGINT, Importe, DatosEvento, ContenidoPropuesta, CondicionesContractuales, TarifaCargoTardio,  # noqa: E402
                            DisponibilidadProveedor, CondicionesServicio, ErrorDominio)

FECHA = datetime(2026, 11, 20, 18, 0)


class ImporteValido(unittest.TestCase):
    def test_acepta_cero_positivos_y_decimales_sin_alterar_la_escala(self):
        for texto in ('0', '0.00', '1', '125.50', '10000.00', '12.345678901234', '1E+3', '123456789012345678901234567890.5'):
            with self.subTest(texto):
                self.assertEqual(Importe(D(texto)).cantidad, D(texto))          # sin redondeo ni máximo inventado

    def test_conserva_la_representacion_decimal_recibida(self):
        self.assertEqual(str(Importe(D('125.50')).cantidad), '125.50')
        self.assertEqual(str(Importe(D('10000')).cantidad), '10000')           # no añade una escala fija

    def test_menos_cero_es_cero(self):
        self.assertEqual(Importe(D('-0')).cantidad, 0)


class ImporteRechazado(unittest.TestCase):
    def assertRechaza(self, valor, fragmento):
        with self.assertRaises(ErrorDominio) as ctx:
            Importe(valor)
        self.assertIn(fragmento, str(ctx.exception))

    def test_negativos(self):
        for texto in ('-0.01', '-1', '-10000.00'):
            with self.subTest(texto):
                self.assertRechaza(D(texto), 'negativo')

    def test_valores_no_finitos(self):
        for texto in ('NaN', 'sNaN', 'Infinity', '-Infinity', '+Infinity'):
            with self.subTest(texto):
                self.assertRechaza(D(texto), 'finito')

    def test_nan_ya_no_escapa_como_excepcion_ajena_al_dominio(self):
        with self.assertRaises(ErrorDominio):                                  # antes: decimal.InvalidOperation
            Importe(D('NaN'))

    def test_tipos_incompatibles(self):
        for valor in (100, 125.5, True, False, '125.50', 'ciento', '', None, [D(1)], (D(1),)):
            with self.subTest(repr(valor)):
                self.assertRechaza(valor, 'Decimal')

    def test_operaciones_aprobadas_no_cambian(self):
        self.assertEqual((Importe(D('10')) + Importe(D('2.5'))).cantidad, D('12.5'))
        self.assertEqual(Importe(D('10000.00')).porcentaje(D(30)).cantidad, D('3000.00'))      # anticipo 30 % (BN-009)
        self.assertEqual(Importe(D('100.005')).porcentaje(D(30)).cantidad, D('30.00'))         # redondeo explícito existente
        self.assertEqual(Importe(D('0')).porcentaje(D(30)).cantidad, D('0.00'))


class DatosEventoTipos(unittest.TestCase):
    def test_valido_y_digitos_permitidos(self):
        d = DatosEvento('Boda 2', FECHA, 'Salón 5, Av. Juárez 123', 100)         # los dígitos son válidos en estos textos
        self.assertEqual((d.tipo, d.invitados_aproximados), ('Boda 2', 100))
        DatosEvento('123', FECHA, '456', 1)

    def test_incompleto_conserva_su_mensaje(self):                              # CA-003
        for tipo, lugar, inv in (('', 'X', 1), ('X', '', 1), ('X', 'X', 0), ('X', 'X', -3)):
            with self.subTest((tipo, lugar, inv)):
                with self.assertRaises(ErrorDominio) as ctx:
                    DatosEvento(tipo, FECHA, lugar, inv)
                self.assertIn('CA-003', str(ctx.exception))
                self.assertIn('incompletos', str(ctx.exception))

    def test_tipos_incompatibles(self):
        casos = ((5, 'X', 1), ('X', 5, 1), (None, 'X', 1), ('X', None, 1), ('X', 'X', 1.0), ('X', 'X', '12'),
                 ('X', 'X', True), ('X', 'X', None), ('X', 'X', D('5')))
        for tipo, lugar, inv in casos:
            with self.subTest((tipo, lugar, inv)):
                with self.assertRaises(ErrorDominio) as ctx:
                    DatosEvento(tipo, FECHA, lugar, inv)
                self.assertIn('tipo de dato no válido', str(ctx.exception))


class ObjetosDeValorConDinero(unittest.TestCase):
    """Un Decimal suelto (negativo, NaN) ya no puede esquivar las reglas de Importe al viajar dentro de otro objeto."""
    def test_contenido_propuesta(self):
        ContenidoPropuesta(('a',), (), Importe(D('1')), 'c')
        for malo in (D('-5'), D('NaN'), D('5'), 5, '5', None):
            with self.subTest(repr(malo)):
                with self.assertRaises(ErrorDominio):
                    ContenidoPropuesta(('a',), (), malo, 'c')

    def test_ca005_conserva_su_mensaje_y_su_orden(self):
        with self.assertRaises(ErrorDominio) as ctx:
            ContenidoPropuesta((), (), D('-5'), '')
        self.assertIn('CA-005', str(ctx.exception))

    def test_condiciones_contractuales(self):
        CondicionesContractuales(('a',), Importe(D('1')), 'c')
        for malo in (D('-5'), D('Infinity'), 5):
            with self.subTest(repr(malo)):
                with self.assertRaises(ErrorDominio):
                    CondicionesContractuales(('a',), malo, 'c')

    def test_tarifa_cargo_tardio(self):
        TarifaCargoTardio(Importe(D('0')))
        for malo in (D('-5'), D('NaN'), 0, None):
            with self.subTest(repr(malo)):
                with self.assertRaises(ErrorDominio):
                    TarifaCargoTardio(malo)

    def test_disponibilidad_proveedor_costo_opcional(self):
        DisponibilidadProveedor('PV-1', False)                                  # sin costo: válido
        DisponibilidadProveedor('PV-1', True, Importe(D('10')), CondicionesServicio('x'))
        for malo in (D('-5'), D('NaN'), 10):
            with self.subTest(repr(malo)):
                with self.assertRaises(ErrorDominio):
                    DisponibilidadProveedor('PV-1', True, malo, None)


class LimiteTecnicoDeInvitados(unittest.TestCase):
    """Incremento 2.4: la columna es BIGINT. El límite 2^63-1 es técnico, no de negocio (ninguna fuente aprobada fija un máximo)."""
    def test_el_limite_es_el_maximo_de_un_entero_de_64_bits_con_signo(self):
        self.assertEqual(MAXIMO_TECNICO_BIGINT, 9223372036854775807)
        self.assertEqual(MAXIMO_TECNICO_BIGINT, 2 ** 63 - 1)

    def test_valores_dentro_del_limite_se_aceptan(self):
        for n in (1, 100, 2147483647, 2147483648, MAXIMO_TECNICO_BIGINT):      # 2147483648 ya no es un caso de error
            with self.subTest(n):
                self.assertEqual(DatosEvento('Boda', FECHA, 'Salón', n).invitados_aproximados, n)

    def test_el_siguiente_valor_y_los_muy_grandes_se_rechazan_antes_de_persistir(self):
        for n in (MAXIMO_TECNICO_BIGINT + 1, 2 ** 64, 10 ** 30):
            with self.subTest(n):
                with self.assertRaises(ErrorDominio) as ctx:                   # ErrorDominio → 422 en la API, nunca un error del controlador
                    DatosEvento('Boda', FECHA, 'Salón', n)
                self.assertIn('límite técnico', str(ctx.exception))
                self.assertIn('no es un máximo de negocio', str(ctx.exception))

    def test_las_demas_reglas_de_invitados_no_cambian(self):
        for n in (0, -1, -MAXIMO_TECNICO_BIGINT - 1):
            with self.subTest(n):
                with self.assertRaises(ErrorDominio) as ctx:
                    DatosEvento('Boda', FECHA, 'Salón', n)
                self.assertIn('CA-003', str(ctx.exception))                   # cero y negativos: mensaje existente
        for malo in (True, False, 1.0, 12.5, '12', 'abc', None, D('5')):
            with self.subTest(repr(malo)):
                with self.assertRaises(ErrorDominio) as ctx:
                    DatosEvento('Boda', FECHA, 'Salón', malo)
                self.assertIn('tipo de dato no válido', str(ctx.exception))

    def test_aplica_tambien_a_los_datos_propuestos_de_una_solicitud_de_cambio(self):
        # datos_propuestos es un DatosEvento: no existe ruta HTTP para este camino; se comprueba el objeto de valor que lo construye
        from domain.solicitudes import SolicitudCambio
        from domain.valores import AnticipacionSolicitud, TarifaCargoTardio
        antic = AnticipacionSolicitud(datetime(2026, 10, 1), FECHA)
        propuesto = DatosEvento('Boda', FECHA, 'Salón', MAXIMO_TECNICO_BIGINT)
        s = SolicitudCambio('SC-1', 'EV-1', 'CT-1', 'EC-1', 'cambio', antic, TarifaCargoTardio(Importe(D('0'))), propuesto)
        self.assertEqual(s.datos_propuestos.invitados_aproximados, MAXIMO_TECNICO_BIGINT)
        with self.assertRaises(ErrorDominio):
            DatosEvento('Boda', FECHA, 'Salón', MAXIMO_TECNICO_BIGINT + 1)


if __name__ == '__main__':
    unittest.main()
