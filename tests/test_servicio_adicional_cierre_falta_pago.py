"""Cierre de una solicitud de servicio adicional por falta de pago (plazo de 24 horas naturales).

Fuentes aprobadas: CA-082 (el plazo de 24 horas comienza con la comunicación de la solicitud de pago; el servicio solo se confirma con el
pago registrado y verificado), US-025, glosario («Pendiente»: falta un pago registrado y verificado) y el BPMN SP-04 (compuerta «¿El
Cliente efectuó el pago dentro de las 24 horas?»; si no, «Cerrar la solicitud por falta de pago»; «Registrar y verificar el pago, aunque
sea después de las 24 horas»). Los límites de las ventanas de horas son inclusivos (GL-060): el instante exacto del límite sigue en plazo.
Ejecutar desde la raíz:  python -m unittest tests.test_servicio_adicional_cierre_falta_pago -v"""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, FECHA_EVENTO                            # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                 # noqa: E402
from domain.valores import (CondicionesServicio, ConceptoPago, Decision, DisponibilidadProveedor, EstadoObligacionPago as EO,   # noqa: E402
                            EstadoSolicitudServicioAdicional as ESA, Importe, TipoSolicitud)

H = timedelta(hours=1)


def escenario():
    e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
    e.confirmar_contratacion()
    s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
    sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
    s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
    s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
    s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
    s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia)
    e.d.despachar()
    ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia).datos['obligacion_id']
    return e, sa, ob, dia          # `dia` es el momento de la comunicación: desde él corren las 24 horas (CA-082)


def estado(e, sa):
    return e.app.repos.adicionales.obtener_por_id(sa).estado


class PlazoDe24Horas(unittest.TestCase):
    def test_el_plazo_comienza_con_la_comunicacion_y_dura_24_horas_naturales(self):
        e, sa, ob, dia = escenario()
        plazo = e.ec().obligaciones[ob].plazo
        self.assertEqual((plazo.inicio, plazo.vence), (dia, dia + 24 * H))

    def test_antes_del_vencimiento_y_en_el_limite_exacto_no_se_cierra(self):
        e, sa, ob, dia = escenario()
        for momento in (dia + 5 * H, dia + 24 * H):                       # el límite de una ventana de horas es inclusivo
            self.assertFalse(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, momento).exito, momento)
        self.assertEqual(estado(e, sa), ESA.PENDIENTE_PAGO)

    def test_sin_pago_se_cierra_un_instante_despues_del_limite(self):
        e, sa, ob, dia = escenario()
        r = e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + 24 * H + timedelta(seconds=1)); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(estado(e, sa), ESA.CERRADA_FALTA_PAGO)
        self.assertEqual(e.ec().obligaciones[ob].estado, EO.SIN_EFECTO)           # cobro exclusivo de la solicitud: sin efecto
        self.assertEqual(e.ec().devoluciones, [])                                 # nada recibido, nada que devolver
        self.assertFalse(any(sc.servicio == 'DJ' for sc in e.evento().servicios.values()))   # el servicio no se incorporó

    def test_un_segundo_cierre_se_rechaza_sin_efectos(self):
        e, sa, ob, dia = escenario()
        tarde = dia + 25 * H
        self.assertTrue(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, tarde).exito)
        self.assertFalse(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, tarde + H).exito)
        self.assertEqual(estado(e, sa), ESA.CERRADA_FALTA_PAGO)


class PagosAntesYDespuesDelVencimiento(unittest.TestCase):
    def test_pago_efectuado_y_verificado_dentro_del_plazo_permite_confirmar_y_no_cerrar(self):
        e, sa, ob, dia = escenario()
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + 10 * H, 'C-1', dia + 11 * H)
        self.assertFalse(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + 30 * H).exito)
        self.assertTrue(e.s.adicionales.confirmar_servicio_adicional(sa, dia + 30 * H).exito)
        self.assertEqual(estado(e, sa), ESA.CONFIRMADA)

    def test_pago_efectuado_en_el_limite_exacto_y_registrado_despues_no_cierra(self):
        e, sa, ob, dia = escenario()
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + 24 * H, 'C-2', dia + 40 * H, verificar_ahora=False)
        self.assertFalse(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + 41 * H).exito)   # pendiente de verificación
        self.assertTrue(e.s.pagos.verificar_pago_registrado(e.ec_id, r.datos['pago_id'], dia + 42 * H).exito)
        self.assertTrue(e.s.adicionales.confirmar_servicio_adicional(sa, dia + 43 * H).exito)

    def test_pago_efectuado_un_instante_despues_del_limite_no_evita_el_cierre(self):
        e, sa, ob, dia = escenario()
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + 24 * H + timedelta(seconds=1), 'C-3', dia + 25 * H)
        self.assertFalse(e.s.adicionales.confirmar_servicio_adicional(sa, dia + 26 * H).exito)
        self.assertTrue(e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + 26 * H).exito)

    def test_un_pago_efectuado_despues_del_cierre_ya_no_se_acepta_sobre_la_obligacion_sin_efecto(self):
        e, sa, ob, dia = escenario()
        e.s.adicionales.cerrar_servicio_adicional_por_falta_de_pago(sa, dia + 25 * H)
        e.d.despachar()                                                   # la reacción deja Sin efecto el cobro (SE-012, C-10)
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + 30 * H, 'C-4', dia + 31 * H)
        self.assertFalse(r.exito)
        self.assertEqual(estado(e, sa), ESA.CERRADA_FALTA_PAGO)


if __name__ == '__main__':
    unittest.main()
