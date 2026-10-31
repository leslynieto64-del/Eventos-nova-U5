"""CA-073 / CA-074: la disponibilidad de un servicio adicional se consulta en dos etapas reales.

Reglas aprobadas:
- CA-073 / SE-004: el Coordinador consulta PRIMERO la disponibilidad de los proveedores que ya participan en el evento.
- CA-074 / SE-004: SOLO si ninguno de ellos puede proporcionar el servicio, busca un proveedor alternativo.
- SE-004, BN-008, CA-071, GL-032: con el Evento cancelado o iniciado no continúa la gestión (sin consultar proveedores).
- CA-075: el proveedor disponible debe traer costo y condiciones antes de continuar (validación existente, sin cambios).

Convención del puerto (IConsultaDisponibilidadProveedor.consultar), la misma que ya usan la sustitución y la asignación:
lista no vacía = consulta dirigida a esos proveedores; lista vacía = consulta general. Proveedores actuales = los
indicados por el Coordinador y los asignados a los servicios del Evento.

El adaptador espía registra cada llamada (servicio, fecha, lista) y responde según los argumentos: así se comprueba el
número de llamadas, sus argumentos y su orden, no solo el proveedor elegido.
Ejecutar desde la raíz:  python -m unittest tests.test_ca073_074_consulta_en_dos_etapas -v"""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                       # noqa: E402
from application.puertos import IConsultaDisponibilidadProveedor                                      # noqa: E402
from domain.valores import (CondicionesServicio, DisponibilidadProveedor, EstadoSolicitudServicioAdicional as ESA,  # noqa: E402
                            Importe)

DIA = T0 + timedelta(days=2)
SERVICIO = 'Fotografía'


def opcion(proveedor, disponible=True, costo='500', condiciones=True):
    return DisponibilidadProveedor(proveedor, disponible, Importe(D(costo)) if costo is not None else None,
                                   CondicionesServicio(f'Condiciones {proveedor}') if condiciones else None)


class AdaptadorEspia(IConsultaDisponibilidadProveedor):
    """Responde a la consulta dirigida con `dirigida[proveedor]` (solo los pedidos, salvo `extra_dirigida`) y a la
    consulta general (lista vacía) con `general`. Registra cada llamada en orden."""

    def __init__(self, dirigida=None, general=None, extra_dirigida=()):
        self.dirigida, self.general, self.extra_dirigida = dict(dirigida or {}), list(general or []), list(extra_dirigida)
        self.llamadas = []

    def consultar(self, servicio, fecha_evento, proveedores_actuales):
        self.llamadas.append((servicio, fecha_evento, tuple(proveedores_actuales)))
        if proveedores_actuales:
            return [self.dirigida[p] for p in proveedores_actuales if p in self.dirigida] + self.extra_dirigida
        return list(self.general)

    def listas(self):
        return [lista for _, _, lista in self.llamadas]


def preparar(espia, asignar=None):
    """Evento con la contratación confirmada; opcionalmente un proveedor asignado a su servicio (participa en el evento).
    El espía se limpia después de la asignación para registrar solo las consultas del servicio adicional."""
    e = Escenario(espia); e.confirmar_contratacion()
    if asignar:
        espia.general = [opcion(asignar)] + espia.general                 # la asignación exige que figure disponible
        servicio = next(iter(e.evento().servicios))
        assert e.s.proveedores.asignar_proveedor(e.evento_id, servicio, asignar).exito
        espia.general = espia.general[1:]
    sa = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, SERVICIO, DIA).datos['solicitud_id']
    espia.llamadas.clear()
    return e, sa


def sol(e, sa):
    return e.app.repos.adicionales.obtener_por_id(sa)


class EtapaUnoProveedoresActuales(unittest.TestCase):
    def test_un_actual_disponible_se_elige_sin_consultar_alternativas(self):                # CA-073
        espia = AdaptadorEspia(dirigida={'PV-1': opcion('PV-1', costo='400')}, general=[opcion('PV-9', costo='100')])
        e, sa = preparar(espia, asignar='PV-1')
        self.assertTrue(e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA).exito)
        self.assertEqual(espia.llamadas, [(SERVICIO, FECHA_EVENTO, ('PV-1',))])          # una sola llamada, dirigida
        s = sol(e, sa)
        self.assertEqual((s.estado, s.disponibilidad.proveedor_id, s.importe_a_cobrar),
                         (ESA.PENDIENTE_APROBACION_CLIENTE, 'PV-1', Importe(D(400))))   # aunque la alternativa cueste menos

    def test_los_actuales_son_los_indicados_y_los_asignados_sin_repetir(self):            # CA-073
        espia = AdaptadorEspia(dirigida={'PV-5': opcion('PV-5')})
        e, sa = preparar(espia, asignar='PV-1')
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, ['PV-5', 'PV-1'], DIA)
        self.assertEqual(espia.listas(), [('PV-5', 'PV-1')])
        self.assertEqual(sol(e, sa).disponibilidad.proveedor_id, 'PV-5')

    def test_en_la_etapa_dirigida_solo_cuentan_las_respuestas_de_los_actuales(self):      # CA-073
        espia = AdaptadorEspia(dirigida={'PV-1': opcion('PV-1', disponible=False)}, extra_dirigida=[opcion('PV-7')],
                               general=[opcion('PV-9')])
        e, sa = preparar(espia, asignar='PV-1')
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        self.assertEqual(espia.listas(), [('PV-1',), ()])                                 # PV-7 no se tomó en la etapa 1
        self.assertEqual(sol(e, sa).disponibilidad.proveedor_id, 'PV-9')

    def test_actual_disponible_sin_costo_conserva_el_rechazo_de_ca_075(self):              # CA-075 (regla existente)
        espia = AdaptadorEspia(dirigida={'PV-1': opcion('PV-1', costo=None)}, general=[opcion('PV-9')])
        e, sa = preparar(espia, asignar='PV-1')
        r = e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        self.assertFalse(r.exito)
        self.assertIn('CA-075', r.mensaje)
        self.assertEqual(espia.listas(), [('PV-1',)])                                     # no pasa a las alternativas
        self.assertEqual((sol(e, sa).estado, sol(e, sa).disponibilidad), (ESA.REGISTRADA, None))


class EtapaDosAlternativas(unittest.TestCase):
    def test_si_ningun_actual_puede_se_consultan_alternativas_despues(self):              # CA-074
        espia = AdaptadorEspia(dirigida={'PV-1': opcion('PV-1', disponible=False)}, general=[opcion('PV-9')])
        e, sa = preparar(espia, asignar='PV-1')
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        self.assertEqual(espia.llamadas, [(SERVICIO, FECHA_EVENTO, ('PV-1',)), (SERVICIO, FECHA_EVENTO, ())])
        self.assertEqual(sol(e, sa).disponibilidad.proveedor_id, 'PV-9')

    def test_las_alternativas_excluyen_a_los_actuales_ya_considerados(self):              # CA-074
        espia = AdaptadorEspia(dirigida={'PV-1': opcion('PV-1', disponible=False)},
                               general=[opcion('PV-1'), opcion('PV-9')])               # PV-1 reaparece en la general
        e, sa = preparar(espia, asignar='PV-1')
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        self.assertEqual(sol(e, sa).disponibilidad.proveedor_id, 'PV-9')

    def test_sin_actuales_se_consulta_directamente_la_general(self):                     # CA-074
        espia = AdaptadorEspia(general=[opcion('PV-9'), opcion('PV-5')])
        e, sa = preparar(espia)
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        self.assertEqual(espia.llamadas, [(SERVICIO, FECHA_EVENTO, ())])
        self.assertEqual(sol(e, sa).disponibilidad.proveedor_id, 'PV-9')

    def test_sin_nadie_disponible_la_busqueda_continua(self):                            # CA-074, CA-076
        espia = AdaptadorEspia(dirigida={'PV-1': opcion('PV-1', disponible=False)}, general=[opcion('PV-9', disponible=False)])
        e, sa = preparar(espia, asignar='PV-1')
        self.assertTrue(e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], DIA).exito)
        self.assertEqual(espia.listas(), [('PV-1',), ()])
        self.assertEqual(sol(e, sa).estado, ESA.EN_BUSQUEDA_PROVEEDOR)

    def test_fuera_de_plazo_conserva_su_cierre(self):                                    # CA-077 (regla existente)
        espia = AdaptadorEspia(general=[opcion('PV-9')])
        e, sa = preparar(espia)
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], FECHA_EVENTO - timedelta(days=4))
        self.assertEqual(sol(e, sa).estado, ESA.NO_PROCEDENTE)


class SinConsultasConElEventoCanceladoOIniciado(unittest.TestCase):
    def _sin_llamadas(self, e, sa, espia, ahora):
        antes = (sol(e, sa).estado, sol(e, sa).disponibilidad, sol(e, sa).motivo_cierre)
        self.assertFalse(e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, ['PV-1'], ahora).exito)
        self.assertEqual(espia.llamadas, [])
        self.assertEqual((sol(e, sa).estado, sol(e, sa).disponibilidad, sol(e, sa).motivo_cierre), antes)

    def test_evento_cancelado(self):                                                     # BN-008, SE-004
        espia = AdaptadorEspia(dirigida={'PV-1': opcion('PV-1')}, general=[opcion('PV-9')])
        e, sa = preparar(espia, asignar='PV-1')
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', DIA)          # reacción sin despachar
        self._sin_llamadas(e, sa, espia, DIA)

    def test_evento_iniciado_registrado(self):                                           # CA-071
        espia = AdaptadorEspia(general=[opcion('PV-9')])
        e, sa = preparar(espia)
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO)                       # reacción sin despachar
        self._sin_llamadas(e, sa, espia, FECHA_EVENTO + timedelta(minutes=5))

    def test_hora_programada_alcanzada_sin_inicio_registrado(self):                      # GL-032, CA-071
        espia = AdaptadorEspia(general=[opcion('PV-9')])
        e, sa = preparar(espia)
        self._sin_llamadas(e, sa, espia, FECHA_EVENTO + timedelta(hours=1))


if __name__ == '__main__':
    unittest.main()
