"""N6: validación ordenada de una solicitud nueva de servicio adicional (SE-004, O-01, US-025, CA-072, CA-083,
CA-099, CA-100; BPMN SP-04).

Orden: se registra la solicitud; después se verifica el Evento (cancelado o iniciado), luego el plazo de cinco días
naturales y, al final, el saldo vencido del contrato original. Cada verificación se ejecuta solo si las anteriores se
cumplieron y se conserva únicamente el primer motivo. Las solicitudes que ya estaban en trámite conservan sus cierres.

Ejecutar desde la raíz:  python -m unittest tests.test_n6_validacion_servicio_adicional -v"""
import itertools
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, FECHA_EVENTO                                              # noqa: E402
from apoyo_especificaciones import MOTIVO_INICIADO_ADICIONAL                                            # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                                    # noqa: E402
from domain.especificacion import EspecificacionSimple, Y                                                # noqa: E402
from domain.especificaciones import AnticipacionMinima, DIAS_MINIMOS_SERVICIO_ADICIONAL                  # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                                            # noqa: E402
from domain.servicios_dominio import EvaluarRegularizacionDeSolicitudes, SituacionSaldo                  # noqa: E402
from domain.solicitudes import SolicitudServicioAdicional                                                # noqa: E402
from domain.valores import (CausaCierreSolicitud, CondicionTemporal, CondicionesServicio, DisponibilidadProveedor,  # noqa: E402
                            Importe, EstadoSolicitudServicioAdicional as ESA)

MOTIVO_CANCELADO = "El evento fue cancelado; la solicitud no puede retomarse (SE-006)."
MOTIVO_CINCO_DIAS = "Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083)."
MOTIVO_SALDO = "Saldo vencido sin regularizar (CA-066, CA-072)."
DIA_VALIDO = FECHA_EVENTO - timedelta(days=10)          # diez días naturales: plazo cumplido
DIA_SIN_PLAZO = FECHA_EVENTO - timedelta(days=4)        # cuatro días naturales: plazo incumplido
DESPUES_DEL_INICIO = FECHA_EVENTO + timedelta(hours=1)


class Espias:
    """Cuenta las verificaciones que se ejecutan durante el registro: la condición temporal de la solicitud, el
    cálculo de los cinco días y la lectura del saldo vencido. `saldo_vencido` fija la respuesta del saldo sin depender
    de las fechas de vencimiento del contrato (O-01: con los plazos reales, ambos casos no coinciden)."""

    def __init__(self, saldo_vencido: bool):
        self.saldo_vencido = saldo_vencido

    def __enter__(self):
        original_ct, original_am = SolicitudServicioAdicional.condicion_temporal, AnticipacionMinima.es_satisfecha_por
        self._parches = [
            mock.patch.object(SolicitudServicioAdicional, 'condicion_temporal', autospec=True, side_effect=original_ct),
            mock.patch.object(AnticipacionMinima, 'es_satisfecha_por', autospec=True, side_effect=original_am),
            # GL-049 / SE-006: el servicio lee `saldo_vencido_en(ahora)` (vencimiento de hecho), no solo el estado registrado
            mock.patch.object(EstadoCuenta, 'saldo_vencido_en', return_value=self.saldo_vencido),
        ]
        self.condicion_temporal, self.anticipacion, self.saldo = [p.start() for p in self._parches]
        return self

    def __exit__(self, *exc):
        for p in reversed(self._parches):
            p.stop()

    @property
    def plazo_evaluado(self) -> int:
        return sum(1 for c in self.anticipacion.call_args_list if c.args[0].dias == DIAS_MINIMOS_SERVICIO_ADICIONAL)


class Base(unittest.TestCase):
    def setUp(self):
        self.e = Escenario(ConsultaDisponibilidadSimulada(
            [DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        self.e.confirmar_contratacion()

    def registrar(self, ahora, saldo_vencido=False):
        with Espias(saldo_vencido) as espias:
            r = self.e.s.adicionales.registrar_solicitud_servicio_adicional(self.e.evento_id, self.e.contrato_id, 'DJ', ahora)
        self.assertTrue(r.exito)
        self.e.d.despachar()
        return r, self.e.app.repos.adicionales.obtener_por_id(r.datos['solicitud_id']), espias

    def cancelar_evento(self, ahora):
        self.assertTrue(self.e.s.cierre.gestionar_cancelacion_solicitada(self.e.evento_id, 'El Cliente desiste', ahora).exito)
        self.e.d.despachar()

    def iniciar_evento(self):
        self.assertTrue(self.e.s.cierre.procesar_inicio_evento(self.e.evento_id, FECHA_EVENTO).exito)
        self.e.d.despachar()

    def assertNoProcedente(self, r, s, causa, motivo):
        self.assertEqual((r.datos['estado'], r.datos['motivo']), (ESA.NO_PROCEDENTE.value, motivo))
        self.assertEqual(s.estado, ESA.NO_PROCEDENTE)
        self.assertEqual((s.motivo_cierre.causa, s.motivo_cierre.descripcion), (causa, motivo))


# ======================================================================= escenarios de registro (1 a 8)
class RegistroDeSolicitudNueva(Base):
    def test_1_evento_valido_plazo_valido_y_sin_saldo_vencido_queda_registrada(self):         # SE-004, CA-073
        r, s, espias = self.registrar(DIA_VALIDO, saldo_vencido=False)
        self.assertEqual((r.datos['estado'], r.datos['motivo']), (ESA.REGISTRADA.value, ''))
        self.assertEqual((s.estado, s.motivo_cierre), (ESA.REGISTRADA, None))
        self.assertEqual((espias.condicion_temporal.call_count, espias.saldo.call_count), (1, 1))
        self.assertTrue(self.e.s.adicionales.evaluar_disponibilidad_servicio_adicional(s.id, [], DIA_VALIDO).exito)
        self.assertEqual(self.e.app.repos.adicionales.obtener_por_id(s.id).estado, ESA.PENDIENTE_APROBACION_CLIENTE)

    def test_2_evento_cancelado_queda_no_procedente_por_cancelacion(self):                    # CA-100
        self.cancelar_evento(DIA_VALIDO - timedelta(days=1))
        r, s, espias = self.registrar(DIA_VALIDO)
        self.assertNoProcedente(r, s, CausaCierreSolicitud.EVENTO_CANCELADO, MOTIVO_CANCELADO)
        self.assertEqual((espias.condicion_temporal.call_count, espias.plazo_evaluado, espias.saldo.call_count), (0, 0, 0))

    def test_3_evento_iniciado_queda_no_procedente_por_inicio_con_la_causa_correcta(self):    # CA-099
        self.iniciar_evento()
        r, s, espias = self.registrar(DESPUES_DEL_INICIO)
        self.assertNoProcedente(
            r,
            s,
            CausaCierreSolicitud.INICIO_EVENTO,
            MOTIVO_INICIADO_ADICIONAL,
        )
        # Se verifica el Evento (dentro de la condición temporal) y ya no se calculan los cinco días ni se lee el saldo.
        self.assertEqual((espias.condicion_temporal.call_count, espias.plazo_evaluado, espias.saldo.call_count), (1, 0, 0))

    def test_4_evento_iniciado_con_saldo_vencido_prevalece_el_inicio(self):                   # O-01
        self.iniciar_evento()
        r, s, espias = self.registrar(DESPUES_DEL_INICIO, saldo_vencido=True)
        self.assertNoProcedente(r, s, CausaCierreSolicitud.INICIO_EVENTO, MOTIVO_INICIADO_ADICIONAL)
        self.assertIsNone(s._estado_antes_de_detener)                                          # no pasó por Detenida
        self.assertEqual((espias.plazo_evaluado, espias.saldo.call_count), (0, 0))             # ni plazo ni saldo

    def test_5_evento_cancelado_con_plazo_insuficiente_y_saldo_vencido_prevalece_la_cancelacion(self):   # O-01
        self.cancelar_evento(DIA_SIN_PLAZO - timedelta(days=1))
        r, s, espias = self.registrar(DIA_SIN_PLAZO, saldo_vencido=True)
        self.assertNoProcedente(r, s, CausaCierreSolicitud.EVENTO_CANCELADO, MOTIVO_CANCELADO)
        self.assertEqual((espias.condicion_temporal.call_count, espias.plazo_evaluado, espias.saldo.call_count), (0, 0, 0))

    def test_6_plazo_insuficiente_con_saldo_vencido_prevalece_el_plazo(self):                 # SE-004, CA-083
        r, s, espias = self.registrar(DIA_SIN_PLAZO, saldo_vencido=True)
        self.assertNoProcedente(r, s, CausaCierreSolicitud.PLAZO_INSUFICIENTE, MOTIVO_CINCO_DIAS)
        self.assertIsNone(s._estado_antes_de_detener)
        self.assertEqual((espias.plazo_evaluado, espias.saldo.call_count), (1, 0))             # el saldo no se consulta

    def test_7_plazo_valido_con_saldo_vencido_queda_detenida_y_se_retoma_por_n2(self):        # CA-072, SE-007, N2
        r, s, espias = self.registrar(DIA_VALIDO, saldo_vencido=True)
        self.assertEqual((r.datos['estado'], r.datos['motivo']), (ESA.DETENIDA_SALDO_VENCIDO.value, MOTIVO_SALDO))
        self.assertEqual((s.estado, s._estado_antes_de_detener, s.motivo_cierre),
                         (ESA.DETENIDA_SALDO_VENCIDO, ESA.REGISTRADA, None))
        self.assertEqual((espias.condicion_temporal.call_count, espias.plazo_evaluado, espias.saldo.call_count), (1, 1, 1))
        # Regularizado el saldo, la reanudación existente (N2) la devuelve al estado anterior a la detención.
        self.e.s.adicionales.retomar_solicitud_servicio_adicional(s.id, DIA_VALIDO + timedelta(hours=2))
        self.assertEqual(self.e.app.repos.adicionales.obtener_por_id(s.id).estado, ESA.REGISTRADA)

    def test_8_la_solicitud_no_procedente_queda_registrada_con_su_motivo(self):               # SE-004, CA-083
        r, s, _ = self.registrar(DIA_SIN_PLAZO)
        self.assertEqual(s.id, r.datos['solicitud_id'])                                       # recuperada del repositorio
        self.assertEqual((s.evento_id, s.contrato_id, s.servicio, s.anticipacion.fecha_solicitud),
                         (self.e.evento_id, self.e.contrato_id, 'DJ', DIA_SIN_PLAZO))
        self.assertEqual(s.motivo_cierre.causa, CausaCierreSolicitud.PLAZO_INSUFICIENTE)
        publicados = [x for x in self.e.app.uow.outbox if getattr(x.evento, 'agregado_id', None) == s.id]
        self.assertEqual([type(x.evento).__name__ for x in publicados], ['ServicioAdicionalSolicitado'])
        self.assertFalse(s.pendiente)                                                          # estado final
        self.assertNotIn(s, self.e.app.repos.adicionales.listar_pendientes_por_evento_id(self.e.evento_id))


# ======================================================================= solicitudes que ya estaban en trámite (9 y 10)
class SolicitudesEnTramiteConservanSuCierre(Base):
    def _en_tramite(self):
        r, s, _ = self.registrar(DIA_VALIDO)
        self.e.s.adicionales.evaluar_disponibilidad_servicio_adicional(s.id, [], DIA_VALIDO)
        self.assertEqual(self.e.app.repos.adicionales.obtener_por_id(s.id).estado, ESA.PENDIENTE_APROBACION_CLIENTE)
        return s.id

    def test_9_en_tramite_cuando_inicia_el_evento_se_cierra_por_inicio(self):                 # CA-071, GL-032
        sid = self._en_tramite()
        self.iniciar_evento()
        s = self.e.app.repos.adicionales.obtener_por_id(sid)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESA.CERRADA_INICIO_EVENTO, CausaCierreSolicitud.INICIO_EVENTO))

    def test_10_en_tramite_cuando_se_cancela_el_evento_se_cierra_por_cancelacion(self):       # BN-008
        sid = self._en_tramite()
        self.cancelar_evento(DIA_VALIDO + timedelta(hours=1))
        s = self.e.app.repos.adicionales.obtener_por_id(sid)
        self.assertEqual((s.estado, s.motivo_cierre.causa),
                         (ESA.CERRADA_EVENTO_CANCELADO, CausaCierreSolicitud.EVENTO_CANCELADO))


# ======================================================================= Domain Service y Specification
class EvaluacionOrdenadaEnElDomainService(unittest.TestCase):
    """`evaluar_solicitud_nueva` decide lo mismo que `evaluar` (misma Specification y orden O-01), pero solo obtiene la
    condición temporal y el saldo cuando las verificaciones anteriores se cumplieron."""

    CONDICIONES = (CondicionTemporal(True), CondicionTemporal(False, MOTIVO_INICIADO_ADICIONAL),
                   CondicionTemporal(False, MOTIVO_CINCO_DIAS))

    def test_misma_decision_que_evaluar_y_solo_las_verificaciones_necesarias(self):
        ds = EvaluarRegularizacionDeSolicitudes()
        for cancelado, ct, vencido in itertools.product((False, True), self.CONDICIONES, (False, True)):
            with self.subTest(cancelado=cancelado, condicion=ct, saldo_vencido=vencido):
                llamadas = []

                def condicion():
                    llamadas.append('plazo'); return ct

                def saldo():
                    llamadas.append('saldo'); return SituacionSaldo(vencido)

                d = ds.evaluar_solicitud_nueva(cancelado, condicion, saldo)
                self.assertEqual(d, ds.evaluar(SituacionSaldo(vencido), cancelado, ct))
                esperado = [] if cancelado else (['plazo'] if not ct.cumple else ['plazo', 'saldo'])
                self.assertEqual(llamadas, esperado)


class PrimerIncumplimientoDeY(unittest.TestCase):
    def test_mismo_primer_incumplimiento_sin_evaluar_las_partes_posteriores(self):
        evaluadas = []

        def parte(nombre):
            return EspecificacionSimple(lambda c, n=nombre: evaluadas.append(n) or c[n], f"falla {nombre}")

        spec = Y(parte('a'), parte('b'), parte('c'))
        for valores in itertools.product((False, True), repeat=3):
            candidato = dict(zip('abc', valores))
            with self.subTest(candidato=candidato):
                completos = spec.incumplimientos(candidato)
                evaluadas.clear()
                primero = spec.primer_incumplimiento(candidato)
                self.assertEqual(primero, completos[0] if completos else None)
                corte = next((i for i, v in enumerate(valores) if not v), 2)
                self.assertEqual(evaluadas, list('abc')[:corte + 1])


if __name__ == '__main__':
    unittest.main()
