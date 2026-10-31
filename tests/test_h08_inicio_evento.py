"""H-08: inicio y finalización del Evento según su fecha y hora programadas.

Reglas aprobadas que se verifican (no se agregan reglas nuevas):
- GL-032: «Evento iniciado» es la situación en que el evento ya comenzó según su fecha y hora programadas.
- GL-005: el Evento incluye fecha y hora programadas. BPMN SP-07: el temporizador «Fecha y hora de inicio del evento»
  precede a «Registrar el inicio del evento (En ejecución)».
- BN-010, GL-033, CA-094, CA-095: Finalizado solo desde En ejecución, una vez concluido; Cancelado nunca es Finalizado.
- CA-039 (no se solicitan cambios con el evento iniciado), CA-088 / SE-009 (la cancelación se rechaza si el evento ya
  inició), CA-099 (servicio adicional nuevo con el evento iniciado: primer motivo «Evento iniciado»), BN-005 (la
  cancelación por falta de regularización solo procede antes del inicio).

Fuera de esta etapa (decisiones pendientes, no se prueban como reglas): quién registra el inicio y si se registra de
forma automática (H-15), la hora de término del evento (no definida en las fuentes), el evento que llega a su fecha En
gestión y la zona horaria.
Ejecutar desde la raíz:  python -m unittest tests.test_h08_inicio_evento -v"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                       # noqa: E402
from application.cqrs import RegistrarCancelacionPorFaltaDeRegularizacionCommand                      # noqa: E402
from domain.evento import Evento, ServicioContratado                                                   # noqa: E402
from domain.valores import (CausaCierreSolicitud, CondicionesServicio, DatosEvento, Decision,          # noqa: E402
                            DisponibilidadProveedor, ErrorDominio, EstadoEvento as EE, EstadoSolicitudCancelacion,
                            EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA,
                            EstadoSustitucionProveedor as ESP, Importe, ResultadoViabilidad)
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                                 # noqa: E402

DIA = T0 + timedelta(days=2)                      # faltan más de 7 días naturales para el evento
ANTES = FECHA_EVENTO - timedelta(minutes=1)
DESPUES = FECHA_EVENTO + timedelta(hours=2)       # ya llegó la hora programada; el inicio no se ha registrado


def evento(estado=EE.EN_ORGANIZACION):
    ev = Evento('EV-1', 'CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete'])
    if estado != EE.EN_GESTION:
        ev.confirmar_contratacion([ServicioContratado('S1', 'Banquete', None, CondicionesServicio('c'))])
    ev.extraer_eventos()
    return ev


def contratado(disponibilidad=None):
    e = Escenario(disponibilidad); e.confirmar_contratacion()
    return e


# ======================================================================= agregado Evento
class IniciarSegunLaFechaYHoraProgramadas(unittest.TestCase):
    def test_no_inicia_antes_de_la_hora_programada_y_no_modifica_el_agregado(self):     # GL-032, SP-07
        for ahora in (T0, FECHA_EVENTO - timedelta(days=1), ANTES):
            with self.subTest(ahora=ahora):
                ev = evento()
                with self.assertRaises(ErrorDominio) as ctx:
                    ev.iniciar(ahora)
                self.assertIn('antes de su fecha y hora programadas', str(ctx.exception))
                self.assertEqual((ev.estado, ev.fecha_inicio, ev.extraer_eventos()), (EE.EN_ORGANIZACION, None, []))

    def test_inicia_a_la_hora_programada_o_despues(self):                                 # regresión: SP-07
        for ahora in (FECHA_EVENTO, FECHA_EVENTO + timedelta(minutes=5), DESPUES):
            with self.subTest(ahora=ahora):
                ev = evento(); ev.iniciar(ahora)
                self.assertEqual((ev.estado, ev.fecha_inicio), (EE.EN_EJECUCION, ahora))
                self.assertEqual([e.nombre for e in ev.extraer_eventos()], ['EventoIniciado'])

    def test_el_estado_se_valida_antes_que_la_hora_y_conserva_sus_mensajes(self):        # regresión: E3A, F2
        for estado, mensaje in ((EE.EN_GESTION, 'No puede iniciar un evento En gestión.'),):
            with self.subTest(estado=estado):
                ev = evento(estado)
                with self.assertRaises(ErrorDominio) as ctx:
                    ev.iniciar(T0)                                     # antes de la hora y en un estado no permitido
                self.assertEqual(str(ctx.exception), mensaje)

    def test_servicio_rechaza_el_inicio_anticipado_sin_efectos(self):                     # GL-032
        e = contratado()
        r = e.s.cierre.procesar_inicio_evento(e.evento_id, T0 + timedelta(days=3)); e.d.despachar()
        self.assertFalse(r.exito)
        self.assertIn('antes de su fecha y hora programadas', r.mensaje)
        self.assertEqual(e.evento().estado, EE.EN_ORGANIZACION)
        self.assertTrue(e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO).exito)   # regresión


class FinalizarDespuesDelInicio(unittest.TestCase):
    def test_la_finalizacion_no_puede_ser_anterior_al_inicio(self):                        # BN-010, CA-094
        ev = evento(); ev.iniciar(FECHA_EVENTO); ev.extraer_eventos()
        with self.assertRaises(ErrorDominio) as ctx:
            ev.finalizar(FECHA_EVENTO - timedelta(minutes=1))
        self.assertIn('no puede ser anterior al inicio', str(ctx.exception))
        self.assertEqual((ev.estado, ev.fecha_finalizacion, ev.extraer_eventos()), (EE.EN_EJECUCION, None, []))

    def test_finaliza_en_o_despues_del_inicio_sin_exigir_hora_de_termino(self):           # CA-094 (regresión)
        for fin in (FECHA_EVENTO, FECHA_EVENTO + timedelta(hours=6), FECHA_EVENTO + timedelta(days=2)):
            with self.subTest(fin=fin):
                ev = evento(); ev.iniciar(FECHA_EVENTO); ev.finalizar(fin)
                self.assertEqual((ev.estado, ev.fecha_finalizacion), (EE.FINALIZADO, fin))

    def test_solo_desde_en_ejecucion_con_los_mensajes_existentes(self):                    # CA-094, CA-095
        self.assertRaisesRegex(ErrorDominio, r'Solo puede finalizarse un evento que se realizó \(CA-094\)\.',
                               evento().finalizar, DESPUES)
        cancelado = evento(); cancelado.solicitar_cancelacion('Desiste', DIA, True)
        self.assertRaisesRegex(ErrorDominio, r'Un evento cancelado no puede registrarse como Finalizado \(CA-095\)\.',
                               cancelado.finalizar, DESPUES)

    def test_servicio_rechaza_una_finalizacion_anterior_al_inicio(self):
        e = contratado(); e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO + timedelta(minutes=10))
        r = e.s.cierre.finalizar_evento(e.evento_id, FECHA_EVENTO)
        self.assertFalse(r.exito)
        self.assertEqual(e.evento().estado, EE.EN_EJECUCION)


class EventoIniciadoSegunLaHora(unittest.TestCase):
    def test_iniciado_en(self):                                                            # GL-032
        ev = evento()
        self.assertFalse(ev.iniciado_en(ANTES))
        self.assertTrue(ev.iniciado_en(FECHA_EVENTO))
        self.assertEqual(ev.estado, EE.EN_ORGANIZACION)                        # la consulta no cambia el estado
        ev.iniciar(FECHA_EVENTO)
        self.assertTrue(ev.iniciado_en(T0))                                    # ya registrado: iniciado siempre

    def test_sin_contratacion_confirmada_o_cancelado_no_se_considera_iniciado(self):      # GL-033: solo En organización inicia
        self.assertFalse(evento(EE.EN_GESTION).iniciado_en(DESPUES))
        cancelado = evento(); cancelado.solicitar_cancelacion('Desiste', DIA, True)
        self.assertFalse(cancelado.iniciado_en(DESPUES))


# ======================================================================= reglas que dependen del inicio
class OperacionesConLaHoraProgramadaAlcanzada(unittest.TestCase):
    """El inicio todavía no se registró, pero ya llegó la fecha y hora programadas (GL-032)."""

    def test_no_se_registran_cambios(self):                                                # CA-039
        e = contratado()
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Más invitados', Importe(D(100)), DESPUES)
        self.assertEqual((r.exito, r.mensaje), (False, 'El cambio solo procede después de contratar y antes del inicio (CA-039).'))
        self.assertEqual(e.app.repos.cambios.listar_todas(), [])
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Más invitados', Importe(D(100)), ANTES)
        self.assertTrue(r.exito)                                                # regresión: antes de la hora procede

    def test_servicio_adicional_nuevo_registra_solo_el_motivo_del_inicio(self):           # CA-099, SE-004
        e = contratado()
        r = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'Fotografía', DESPUES)
        s = e.app.repos.adicionales.obtener_por_id(r.datos['solicitud_id'])
        self.assertEqual(s.estado, ESA.NO_PROCEDENTE)
        self.assertEqual(s.motivo_cierre.causa, CausaCierreSolicitud.INICIO_EVENTO)
        self.assertNotIn('cinco días', r.datos['motivo'])                       # no el segundo motivo (plazo)

    def test_la_cancelacion_del_cliente_se_rechaza_y_el_evento_no_se_cancela(self):        # CA-088, SE-009
        e = contratado()
        r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', DESPUES); e.d.despachar()
        self.assertFalse(r.exito)
        ev = e.evento()
        self.assertEqual(ev.estado, EE.EN_ORGANIZACION)
        self.assertEqual([s.estado for s in ev.solicitudes_cancelacion], [EstadoSolicitudCancelacion.RECHAZADA_INICIO_EVENTO])
        self.assertEqual(e.avisos('Evento cancelado'), [])
        self.assertEqual(len(e.avisos('Cancelación no procedente')), 1)

    def test_la_cancelacion_del_cliente_antes_de_la_hora_sigue_procediendo(self):         # regresión: CA-087
        e = contratado()
        self.assertTrue(e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', ANTES).exito)
        self.assertEqual(e.evento().estado, EE.CANCELADO)

    def _no_regularizado(self):
        e = contratado(); e.vencer_saldo_y_comunicar_moratorios()
        revision = e.comunicacion + timedelta(hours=25)
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision); e.d.despachar()
        return e

    def test_la_cancelacion_por_falta_de_regularizacion_ya_no_procede(self):              # BN-005
        e = self._no_regularizado()
        cmd = RegistrarCancelacionPorFaltaDeRegularizacionCommand(e.evento_id, 'Sin regularizar', 'Coordinador', DESPUES)
        r = e.app.commands.cancelar_por_falta_de_regularizacion.handle(cmd); e.d.despachar()
        self.assertFalse(r.exito)
        self.assertIn('BN-005', r.mensaje)
        self.assertEqual(e.evento().estado, EE.EN_ORGANIZACION)
        self.assertEqual(e.obligacion('SaldoContratoOriginal').estado.value, 'Vencida')   # el adeudo permanece

    def test_la_cancelacion_por_falta_de_regularizacion_antes_de_la_hora_procede(self):  # regresión: CA-027
        e = self._no_regularizado()
        cmd = RegistrarCancelacionPorFaltaDeRegularizacionCommand(e.evento_id, 'Sin regularizar', 'Coordinador', ANTES)
        self.assertTrue(e.app.commands.cancelar_por_falta_de_regularizacion.handle(cmd).exito)

    def test_no_se_confirma_un_cambio(self):                                               # BRD: no se confirman después del inicio
        e = contratado()
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Ajuste', Importe(D(0)), DIA).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), None, DIA)
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo', DIA); e.d.despachar()
        r = e.s.cambios.confirmar_cambio(sid, DESPUES)
        self.assertFalse(r.exito)
        self.assertIn('evento no iniciado', r.pendientes)
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sid).estado, ESC.PENDIENTE_FORMALIZACION)
        self.assertTrue(e.s.cambios.confirmar_cambio(sid, ANTES).exito)         # regresión

    def test_no_se_confirma_una_sustitucion_ni_se_inicia_una_nueva(self):                  # CA-096, SP-05
        disp = ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(0)), CondicionesServicio('c'))])
        e = contratado(disp); servicio = next(iter(e.evento().servicios))
        sid = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, DIA).datos['sustitucion_id']
        e.s.sustitucion.buscar_alternativa_sustitucion(sid, CondicionesServicio('Condiciones acordadas'), None, DIA)
        e.s.sustitucion.registrar_anexo_sustitucion_proveedor(sid, 'Anexo', DIA); e.d.despachar()
        r = e.s.sustitucion.confirmar_sustitucion_proveedor(sid, DESPUES)
        self.assertFalse(r.exito)
        self.assertIn('evento no iniciado', r.pendientes)
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(sid).estado, ESP.PENDIENTE_FORMALIZACION)
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, DESPUES)
        self.assertFalse(r.exito)
        self.assertIn('fuera del alcance', r.mensaje)
        self.assertTrue(e.s.sustitucion.confirmar_sustitucion_proveedor(sid, ANTES).exito)   # regresión

    def test_no_se_confirma_un_servicio_adicional(self):                                   # CA-071, CA-080
        disp = ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('c'))])
        e = contratado(disp); s = e.s.adicionales
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'Fotografía', DIA).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, DIA))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, DIA))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo', DIA); e.d.despachar()
        from domain.valores import TipoSolicitud, ConceptoPago
        oid = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL,
                                                 Importe(D(500)), DIA).datos['obligacion_id']
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, oid, Importe(D(500)), DIA + timedelta(hours=1), 'C-SA'); e.d.despachar()
        r = s.confirmar_servicio_adicional(sa, DESPUES)
        self.assertFalse(r.exito)
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.PENDIENTE_PAGO)
        self.assertTrue(s.confirmar_servicio_adicional(sa, ANTES).exito)         # regresión


if __name__ == '__main__':
    unittest.main()
