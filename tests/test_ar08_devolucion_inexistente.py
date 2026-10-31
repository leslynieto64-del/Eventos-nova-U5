"""AR-08: `EstadoCuenta.registrar_devolucion_efectuada` rechaza una devolución inexistente con un error de dominio (antes
escapaba un StopIteration) sin modificar el agregado ni registrar eventos; la ejecución válida y su repetición idempotente no cambian.
Ejecutar desde la raíz:  python -m unittest tests.test_ar08_devolucion_inexistente -v"""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from apoyo_persistencia import T0, estado_de                              # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                         # noqa: E402
from domain.valores import ConceptoPago, ErrorDominio, EstadoDevolucion, Importe                                 # noqa: E402


class DevolucionInexistente(unittest.TestCase):
    def _ec(self):
        ec = EstadoCuenta('EC-1', 'CT-1', 'EV-1')
        ec.registrar_obligacion_anticipo('OB-1', Importe(D('10000.00')), T0)
        ec.comunicar_solicitud_pago('OB-3', ConceptoPago.CAMBIO,
                                    Importe(D('150.25')), 'SC-1', T0)
        ec.registrar_y_verificar_pago('PG-2', 'OB-3', Importe(D('150.25')), T0 + timedelta(hours=2), 'C-2', True)
        ec.aplicar_cierre_sin_realizar('SC-1', T0 + timedelta(days=2), False, lambda: 'DV-1')
        ec.extraer_eventos()
        return ec

    def test_devolucion_inexistente_es_error_de_dominio_sin_cambios(self):
        ec = self._ec()
        antes = estado_de(ec)
        with self.assertRaisesRegex(ErrorDominio, 'La devolución no existe'):
            ec.registrar_devolucion_efectuada('DV-NO-EXISTE', T0 + timedelta(days=3), 'CMP')
        self.assertEqual(estado_de(ec), antes)
        self.assertEqual(ec.extraer_eventos(), [])

    def test_sin_devoluciones_tambien_es_error_de_dominio(self):
        with self.assertRaises(ErrorDominio):
            EstadoCuenta('EC-9', 'CT-9', 'EV-9').registrar_devolucion_efectuada('DV-1', T0, 'CMP')

    def test_devolucion_existente_y_repeticion_idempotente(self):
        ec = self._ec()
        fecha = T0 + timedelta(days=3)
        ec.registrar_devolucion_efectuada('DV-1', fecha, 'CMP-1')
        d = ec.devoluciones[0]
        self.assertEqual((d.estado, d.fecha_devolucion, d.comprobante), (EstadoDevolucion.EFECTUADA, fecha, 'CMP-1'))
        self.assertEqual(len(ec.extraer_eventos()), 1)
        ec.registrar_devolucion_efectuada('DV-1', fecha + timedelta(days=1), 'CMP-OTRO')
        self.assertEqual((d.fecha_devolucion, d.comprobante), (fecha, 'CMP-1'))
        self.assertEqual(ec.extraer_eventos(), [])


if __name__ == '__main__':
    unittest.main()
