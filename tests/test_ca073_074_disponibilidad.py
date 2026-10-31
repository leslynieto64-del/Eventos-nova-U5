"""CA-073 / CA-074: disponibilidad de un servicio adicional en trámite.

Reglas aprobadas:
- CA-073 y SE-004: el Coordinador consulta primero la disponibilidad de los proveedores que ya participan en el evento.
- CA-074 y SE-004: solo si ninguno de ellos puede proporcionarlo, busca un proveedor alternativo.
- SE-004 (orden de verificación: primero el estado del Evento), BN-008 (con el Evento cancelado las solicitudes en
  trámite se cierran con el motivo «Evento cancelado») y CA-071 / GL-032 (con el Evento iniciado se cierran por inicio).

La comprobación del estado del Evento rechaza la operación sin modificar la solicitud; su cierre con el motivo que
corresponde lo hacen las reacciones existentes a EventoCancelado y EventoIniciado. El dominio
(SolicitudServicioAdicional.registrar_disponibilidad) no cambia.
Ejecutar desde la raíz:  python -m unittest tests.test_ca073_074_disponibilidad -v"""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                       # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                                 # noqa: E402
from domain.valores import (CausaCierreSolicitud, CondicionesServicio, DisponibilidadProveedor,       # noqa: E402
                            EstadoSolicitudServicioAdicional as ESA, Importe)

DIA = T0 + timedelta(days=2)


def opcion(proveedor, disponible=True, costo='500'):
    return DisponibilidadProveedor(proveedor, disponible, Importe(D(costo)), CondicionesServicio(f'Condiciones {proveedor}'))


def solicitud(opciones, asignar=None):
    e = Escenario(ConsultaDisponibilidadSimulada(opciones)); e.confirmar_contratacion()
    if asignar:
        servicio = next(iter(e.evento().servicios))
        assert e.s.proveedores.asignar_proveedor(e.evento_id, servicio, asignar).exito
    sa = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'Fotografía', DIA).datos['solicitud_id']
    return e, sa


def sa_de(e, sa):
    return e.app.repos.adicionales.obtener_por_id(sa)


class PrimeroLosProveedoresQueYaParticipan(unittest.TestCase):
    def test_se_elige_al_proveedor_asignado_al_evento_antes_que_a_una_alternativa(self):   # CA-073
        e, sa = solicitud([opcion('PV-9', costo='800'), opcion('PV-1', costo='400')], asignar='PV-1')
        self.assertTrue(e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA).exito)
        s = sa_de(e, sa)
        self.assertEqual((s.estado, s.disponibilidad.proveedor_id, s.importe_a_cobrar), (ESA.PENDIENTE_APROBACION_CLIENTE, 'PV-1', Importe(D(400))))

    def test_se_respetan_los_proveedores_actuales_indicados_por_el_coordinador(self):     # CA-073
        e, sa = solicitud([opcion('PV-9'), opcion('PV-5')])
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, ['PV-5'], DIA)
        self.assertEqual(sa_de(e, sa).disponibilidad.proveedor_id, 'PV-5')

    def test_si_ningun_actual_puede_se_usa_una_alternativa(self):                           # CA-074, CA-075
        e, sa = solicitud([opcion('PV-1', disponible=False), opcion('PV-9')], asignar=None)
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, ['PV-1'], DIA)
        self.assertEqual(sa_de(e, sa).disponibilidad.proveedor_id, 'PV-9')

    def test_sin_actuales_se_conserva_el_orden_de_la_consulta(self):                        # regresión
        e, sa = solicitud([opcion('PV-9'), opcion('PV-5')])
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        self.assertEqual(sa_de(e, sa).disponibilidad.proveedor_id, 'PV-9')

    def test_sin_ninguno_disponible_continua_la_busqueda(self):                             # CA-074, CA-076 (regresión)
        e, sa = solicitud([opcion('PV-1', disponible=False)])
        self.assertTrue(e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, ['PV-1'], DIA).exito)
        self.assertEqual(sa_de(e, sa).estado, ESA.EN_BUSQUEDA_PROVEEDOR)


class PrimeroElEstadoDelEvento(unittest.TestCase):
    def _rechazada_sin_cambios(self, e, sa, ahora, texto):
        antes = (sa_de(e, sa).estado, sa_de(e, sa).motivo_cierre, sa_de(e, sa).disponibilidad)
        r = e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], ahora)
        self.assertFalse(r.exito)
        self.assertIn(texto, r.mensaje)
        self.assertEqual((sa_de(e, sa).estado, sa_de(e, sa).motivo_cierre, sa_de(e, sa).disponibilidad), antes)

    def test_evento_cancelado_antes_de_la_reaccion(self):                                  # BN-008, SE-004
        e, sa = solicitud([opcion('PV-9')])
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', DIA)          # sin despachar la reacción
        self._rechazada_sin_cambios(e, sa, DIA, 'BN-008')
        e.d.despachar()
        self.assertEqual(sa_de(e, sa).estado, ESA.CERRADA_EVENTO_CANCELADO)           # el cierre lo hace la reacción

    def test_evento_iniciado_antes_de_la_reaccion_no_se_cierra_por_plazo(self):           # CA-071, GL-032
        e, sa = solicitud([opcion('PV-9')])
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO)                       # sin despachar la reacción
        self._rechazada_sin_cambios(e, sa, FECHA_EVENTO + timedelta(minutes=5), 'CA-071')
        e.d.despachar()
        s = sa_de(e, sa)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESA.CERRADA_INICIO_EVENTO, CausaCierreSolicitud.INICIO_EVENTO))

    def test_hora_programada_alcanzada_sin_inicio_registrado(self):                        # GL-032, CA-071
        e, sa = solicitud([opcion('PV-9')])
        self._rechazada_sin_cambios(e, sa, FECHA_EVENTO + timedelta(hours=1), 'CA-071')

    def test_la_respuesta_de_espera_tambien_respeta_el_estado_del_evento(self):           # CA-077, BN-008
        e, sa = solicitud([opcion('PV-9', disponible=False)])
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        self.assertEqual(sa_de(e, sa).estado, ESA.EN_BUSQUEDA_PROVEEDOR)
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', DIA)
        r = e.s.adicionales.registrar_decision_espera_cliente(sa, False, DIA)
        self.assertFalse(r.exito)
        self.assertEqual(sa_de(e, sa).estado, ESA.EN_BUSQUEDA_PROVEEDOR)

    def test_la_respuesta_de_espera_con_el_evento_vigente_no_cambia(self):               # CA-076, CA-078 (regresión)
        for acepta, estado in ((True, ESA.EN_BUSQUEDA_PROVEEDOR), (False, ESA.NO_SE_REALIZARA)):
            with self.subTest(acepta_esperar=acepta):
                e, sa = solicitud([opcion('PV-9', disponible=False)])
                e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
                self.assertTrue(e.s.adicionales.registrar_decision_espera_cliente(sa, acepta, DIA).exito)
                self.assertEqual(sa_de(e, sa).estado, estado)

    def test_fuera_de_plazo_con_el_evento_vigente_conserva_su_cierre(self):               # CA-077, CA-083 (regresión)
        e, sa = solicitud([opcion('PV-9')])
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], FECHA_EVENTO - timedelta(days=4))
        s = sa_de(e, sa)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESA.NO_PROCEDENTE, CausaCierreSolicitud.PLAZO_INSUFICIENTE))


if __name__ == '__main__':
    unittest.main()
