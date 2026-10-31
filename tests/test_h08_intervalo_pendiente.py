"""H-08: intervalo entre la hora programada del Evento y el registro formal de su inicio (documentado, no resuelto).

El sistema distingue la hora programada (GL-032) del registro del inicio (BPMN SP-07). Mientras el Coordinador no registra
el inicio, el Evento sigue En organización. Estas pruebas dejan escrito qué ocurre en ese intervalo hoy; no son reglas
nuevas. DECISIÓN DE NEGOCIO PENDIENTE (H-15): quién registra el inicio, si debe hacerse automáticamente y qué operaciones
deberían seguir permitidas mientras tanto. No se inventa una transición automática ni una hora de término.
Ejecutar desde la raíz:  python -m unittest tests.test_h08_intervalo_pendiente -v"""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, FECHA_EVENTO                                           # noqa: E402
from test_h13_criterios_aceptacion import DIA, alternativa_con_original                               # noqa: E402
from domain.valores import (EstadoEvento as EE, EstadoSolicitudCambio as ESC,                         # noqa: E402
                            EstadoSolicitudServicioAdicional as ESA, Importe, ResultadoViabilidad)

LLEGADA = FECHA_EVENTO + timedelta(hours=2)        # la hora programada ya pasó y el inicio no se ha registrado


class IntervaloSinInicioRegistrado(unittest.TestCase):
    def setUp(self):
        self.e = Escenario(alternativa_con_original()); self.e.confirmar_contratacion()
        self.servicio = next(iter(self.e.evento().servicios))

    def test_el_evento_sigue_en_organizacion_sin_transicion_automatica(self):
        self.assertEqual(self.e.evento().estado, EE.EN_ORGANIZACION)
        self.e.s.pagos.registrar_vencimiento_saldo_original(self.e.ec_id, LLEGADA)
        self.e.d.despachar()
        self.assertEqual(self.e.evento().estado, EE.EN_ORGANIZACION)

    def test_operaciones_que_todavia_ocurren_en_el_intervalo(self):
        e = self.e
        self.assertTrue(e.s.proveedores.asignar_proveedor(e.evento_id, self.servicio, 'PV-1').exito)
        self.assertTrue(e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, self.servicio, 'PV-1', True).exito)
        saldo = e.obligacion('SaldoContratoOriginal')
        self.assertTrue(e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, saldo.importe, LLEGADA, 'C-S').exito)
        previo = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Previo', Importe(D(150)), DIA).datos['solicitud_id']
        self.assertTrue(e.s.cambios.evaluar_viabilidad_cambio(previo, ResultadoViabilidad(True), None, LLEGADA).exito)
        self.assertTrue(e.s.cambios.registrar_anexo_cambio(previo, 'Anexo', LLEGADA).exito)

    def test_operaciones_que_ya_se_rechazan_en_el_intervalo(self):
        e = self.e
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Nuevo', Importe(D(150)), LLEGADA)
        self.assertFalse(r.exito)                                                                  # CA-039
        self.assertFalse(e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Cancela', LLEGADA).exito)   # CA-088
        self.assertFalse(e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, self.servicio, e.contrato_id, LLEGADA).exito)
        self.assertEqual(e.evento().estado, EE.EN_ORGANIZACION)

    def test_el_registro_posterior_del_inicio_cierra_las_solicitudes_en_tramite(self):
        e = self.e
        cambio = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Previo', Importe(D(150)), DIA).datos['solicitud_id']
        adicional = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', DIA).datos['solicitud_id']
        antes = e.app.repos.adicionales.obtener_por_id(adicional).estado
        self.assertFalse(e.s.adicionales.evaluar_disponibilidad_servicio_adicional(adicional, [], LLEGADA).exito)   # no avanza
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(adicional).estado, antes)
        self.assertTrue(e.s.cierre.procesar_inicio_evento(e.evento_id, LLEGADA).exito); e.d.despachar()
        self.assertEqual(e.evento().estado, EE.EN_EJECUCION)
        self.assertEqual(e.app.repos.cambios.obtener_por_id(cambio).estado, ESC.CERRADA_INICIO_EVENTO)
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(adicional).estado, ESA.CERRADA_INICIO_EVENTO)


if __name__ == '__main__':
    unittest.main()
