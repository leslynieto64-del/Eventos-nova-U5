"""Etapa E2 — especificaciones de negocio y su integración con el dominio existente.

Cubre ContratacionConfirmable (BN-009, CA-019), CambioRequiereAprobacionCliente (BN-003) frente a la regla de la
sustitución (SE-001), la condición temporal de servicios adicionales (SE-004, CA-077, CA-080, CA-083), el cargo
tardío (BN-003, CA-061, CA-062) y SolicitudPuedeContinuar con el orden O-01."""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_especificaciones import (contrato, cambio, servicio_adicional, FECHA_EVENTO, T, MOTIVO_CINCO_DIAS,  # noqa: E402
                                    MOTIVO_INICIADO_ADICIONAL, MOTIVO_INICIADO_CAMBIO, MOTIVO_CANCELADO, MOTIVO_SALDO)

import domain.contrato as mod_contrato                                                   # noqa: E402
import domain.especificaciones as mod_esp                                                # noqa: E402
import domain.servicios_dominio as mod_servicios                                         # noqa: E402
import domain.solicitudes as mod_solicitudes                                             # noqa: E402
from domain.contrato import EvidenciaAnticipo                                            # noqa: E402
from domain.especificacion import EspecificacionSimple                                   # noqa: E402
from domain.especificaciones import (                                                    # noqa: E402
    CONTRATACION_CONFIRMABLE, CAMBIO_REQUIERE_APROBACION_CLIENTE, MODIFICACION_CON_IMPACTO, CAMBIO_CON_CARGO_TARDIO,
    CAMBIO_SIN_CARGO_TARDIO, SERVICIO_ADICIONAL_EN_PLAZO, SOLICITUD_CAMBIO_EN_PLAZO, SOLICITUD_PUEDE_CONTINUAR,
    ContratoEstaFirmado, PoliticaNoReembolsoComunicada, AnticipoVerificado, AfectaServicios, AfectaCostos,
    AfectaCondiciones, AnticipacionMinima, EventoNoIniciado, EventoNoCancelado, ElegibilidadObtenida,
    CondicionTemporalCumplida, SinSaldoVencido, SituacionContratacion, SituacionTemporalSolicitud,
    SituacionContinuidadSolicitud)
from domain.servicios_dominio import EvaluarRegularizacionDeSolicitudes, SituacionSaldo  # noqa: E402
from domain.valores import (EstadoContrato, ImpactoModificacion, AnticipacionSolicitud, CondicionTemporal,  # noqa: E402
                            ResultadoViabilidad, DisponibilidadProveedor, Importe, CondicionesServicio, Decision,
                            CausaCierreSolicitud, EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA)

PENDIENTES = ['contrato firmado', 'política de no reembolso comunicada', 'anticipo del 30 % registrado y verificado']
ANTICIPO_OK = EvidenciaAnticipo(True, True, True)


def situacion_contratacion(estado=EstadoContrato.FIRMADO, comunicada=True, evidencia=ANTICIPO_OK):
    return SituacionContratacion(contrato(estado, comunicada), evidencia)


def a_dias(dias, hora=9):
    """Momento de evaluación a `dias` días naturales de la fecha del evento."""
    return FECHA_EVENTO.replace(hour=hora) - timedelta(days=dias)


# ======================================================================= especificaciones individuales
class EspecificacionesIndividuales(unittest.TestCase):
    def test_contrato_firmado(self):
        self.assertTrue(ContratoEstaFirmado().es_satisfecha_por(situacion_contratacion()))
        for estado in (EstadoContrato.EN_PREPARACION, EstadoContrato.CERRADO_SIN_CONFIRMAR):
            with self.subTest(estado=estado):
                self.assertEqual(ContratoEstaFirmado().motivos_incumplimiento(situacion_contratacion(estado)),
                                 ['contrato firmado'])

    def test_politica_no_reembolso_comunicada(self):
        self.assertTrue(PoliticaNoReembolsoComunicada().es_satisfecha_por(situacion_contratacion()))
        self.assertEqual(PoliticaNoReembolsoComunicada().motivos_incumplimiento(situacion_contratacion(comunicada=False)),
                         ['política de no reembolso comunicada'])

    def test_anticipo_verificado_exige_registro_verificacion_e_importe_correcto(self):
        self.assertTrue(AnticipoVerificado().es_satisfecha_por(situacion_contratacion()))
        for evidencia in (EvidenciaAnticipo(False, True, True), EvidenciaAnticipo(True, False, True),
                          EvidenciaAnticipo(True, True, False), EvidenciaAnticipo(False, False, False)):
            with self.subTest(evidencia=evidencia):
                self.assertEqual(AnticipoVerificado().motivos_incumplimiento(situacion_contratacion(evidencia=evidencia)),
                                 ['anticipo del 30 % registrado y verificado'])

    def test_afecta_servicios_costos_y_condiciones(self):
        for clase, campo in ((AfectaServicios, 0), (AfectaCostos, 1), (AfectaCondiciones, 2)):
            for valor in (False, True):
                banderas = [False, False, False]; banderas[campo] = valor
                with self.subTest(clase=clase.__name__, valor=valor):
                    self.assertEqual(clase().es_satisfecha_por(ImpactoModificacion(*banderas)), valor)

    def test_anticipacion_minima_en_el_limite(self):
        cinco = AnticipacionMinima(5)
        for dias, esperado in ((4, False), (5, True), (6, True)):
            with self.subTest(dias=dias):
                self.assertEqual(cinco.es_satisfecha_por(AnticipacionSolicitud(a_dias(dias), FECHA_EVENTO)), esperado)

    def test_eventos_y_elegibilidad(self):
        self.assertTrue(EventoNoIniciado('x').es_satisfecha_por(SituacionTemporalSolicitud(False)))
        self.assertEqual(EventoNoIniciado('ya inició').motivos_incumplimiento(SituacionTemporalSolicitud(True)), ['ya inició'])
        self.assertTrue(ElegibilidadObtenida().es_satisfecha_por(SituacionTemporalSolicitud(False, True)))
        self.assertFalse(ElegibilidadObtenida().es_satisfecha_por(SituacionTemporalSolicitud(False, False)))
        cont = SituacionContinuidadSolicitud(False, True, CondicionTemporal(True))
        self.assertEqual(EventoNoCancelado('cancelado').motivos_incumplimiento(cont), ['cancelado'])

    def test_condicion_temporal_usa_el_motivo_que_informa_la_solicitud(self):
        cont = SituacionContinuidadSolicitud(False, False, CondicionTemporal(False, 'motivo de la solicitud'))
        self.assertEqual(CondicionTemporalCumplida().motivos_incumplimiento(cont), ['motivo de la solicitud'])
        self.assertTrue(CondicionTemporalCumplida().es_satisfecha_por(
            SituacionContinuidadSolicitud(False, False, CondicionTemporal(True))))

    def test_sin_saldo_vencido(self):
        self.assertTrue(SinSaldoVencido().es_satisfecha_por(SituacionContinuidadSolicitud(False, False, CondicionTemporal(True))))
        self.assertEqual(SinSaldoVencido().motivos_incumplimiento(SituacionContinuidadSolicitud(True, False, CondicionTemporal(True))),
                         [MOTIVO_SALDO])


# ======================================================================= ContratacionConfirmable
class ContratacionConfirmable(unittest.TestCase):
    def test_se_satisface_con_los_tres_requisitos(self):
        self.assertTrue(CONTRATACION_CONFIRMABLE.es_satisfecha_por(situacion_contratacion()))
        self.assertEqual(CONTRATACION_CONFIRMABLE.motivos_incumplimiento(situacion_contratacion()), [])

    def test_detalle_de_pendientes_en_el_orden_actual(self):
        sin_nada = situacion_contratacion(EstadoContrato.EN_PREPARACION, False, EvidenciaAnticipo(False, False, False))
        self.assertEqual(CONTRATACION_CONFIRMABLE.motivos_incumplimiento(sin_nada), PENDIENTES)
        self.assertEqual(CONTRATACION_CONFIRMABLE.motivos_incumplimiento(situacion_contratacion(comunicada=False)), [PENDIENTES[1]])
        self.assertEqual(CONTRATACION_CONFIRMABLE.motivos_incumplimiento(
            situacion_contratacion(EstadoContrato.EN_PREPARACION, evidencia=EvidenciaAnticipo(True, True, False))),
            [PENDIENTES[0], PENDIENTES[2]])

    def test_contrato_devuelve_los_mismos_pendientes_y_no_cambia_de_estado(self):
        c = contrato(EstadoContrato.FIRMADO, comunicada=False)
        self.assertEqual(c.confirmar_contratacion(EvidenciaAnticipo(True, True, False), T), PENDIENTES[1:])
        self.assertEqual(c.estado, EstadoContrato.FIRMADO)
        self.assertEqual(c.extraer_eventos(), [])

    def test_confirma_emite_el_evento_y_es_idempotente(self):
        c = contrato()
        self.assertEqual(c.confirmar_contratacion(ANTICIPO_OK, T), [])
        self.assertEqual(c.estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        self.assertEqual([e.nombre for e in c.extraer_eventos()], ['ContratacionConfirmada'])
        self.assertEqual(c.confirmar_contratacion(EvidenciaAnticipo(False, False, False), T), [])   # ya confirmada
        self.assertEqual(c.extraer_eventos(), [])

    def test_contrato_usa_la_especificacion(self):
        falsa = EspecificacionSimple(lambda s: False, 'requisito sustituido')
        with mock.patch.object(mod_contrato, 'CONTRATACION_CONFIRMABLE', falsa):
            self.assertEqual(contrato().confirmar_contratacion(ANTICIPO_OK, T), ['requisito sustituido'])


# ======================================================================= aprobación de cambios frente a sustitución
class AprobacionDeCambios(unittest.TestCase):
    def test_cambio_requiere_aprobacion_si_afecta_costos_o_condiciones(self):
        for s in (False, True):
            for c in (False, True):
                for k in (False, True):
                    with self.subTest(servicios=s, costos=c, condiciones=k):
                        self.assertEqual(CAMBIO_REQUIERE_APROBACION_CLIENTE.es_satisfecha_por(ImpactoModificacion(s, c, k)),
                                         c or k)

    def test_solo_servicios_no_requiere_aprobacion_en_un_cambio_pero_si_en_una_sustitucion(self):
        solo_servicios = ImpactoModificacion(True, False, False)
        self.assertFalse(CAMBIO_REQUIERE_APROBACION_CLIENTE.es_satisfecha_por(solo_servicios))
        self.assertTrue(MODIFICACION_CON_IMPACTO.es_satisfecha_por(solo_servicios))
        self.assertTrue(solo_servicios.tiene_impacto)
        self.assertFalse(ImpactoModificacion(False, False, False).tiene_impacto)

    def test_rutas_de_la_solicitud_de_cambio(self):
        casos = {(False, True, False): ESC.PENDIENTE_APROBACION_CLIENTE,     # ruta B: costos
                 (False, False, True): ESC.PENDIENTE_APROBACION_CLIENTE,     # ruta B: condiciones
                 (True, False, False): ESC.PENDIENTE_FORMALIZACION,          # ruta C
                 (False, False, False): ESC.PENDIENTE_FORMALIZACION}         # ruta C
        for banderas, estado in casos.items():
            with self.subTest(impacto=banderas):
                sc = cambio(10)
                sc.registrar_viabilidad(ResultadoViabilidad(True), ImpactoModificacion(*banderas), T)
                self.assertEqual(sc.estado, estado)

    def test_no_viable_se_cierra_aunque_requiera_aprobacion(self):            # ruta A antes que la B
        sc = cambio(10)
        sc.registrar_viabilidad(ResultadoViabilidad(False, 'Proveedor sin disponibilidad'), ImpactoModificacion(False, True, True), T)
        self.assertEqual(sc.estado, ESC.NO_PROCEDENTE)
        self.assertEqual(sc.motivo_cierre.causa, CausaCierreSolicitud.NO_VIABLE)
        self.assertFalse(sc.importes_por_pagar)

    def test_solicitud_de_cambio_y_sustitucion_usan_sus_especificaciones(self):
        verdadera = EspecificacionSimple(lambda i: True, 'x')
        with mock.patch.object(mod_solicitudes, 'CAMBIO_REQUIERE_APROBACION_CLIENTE', verdadera):
            sc = cambio(10); sc.registrar_viabilidad(ResultadoViabilidad(True), ImpactoModificacion(False, False, False), T)
            self.assertEqual(sc.estado, ESC.PENDIENTE_APROBACION_CLIENTE)
        with mock.patch.object(mod_esp, 'MODIFICACION_CON_IMPACTO', verdadera):
            self.assertTrue(ImpactoModificacion(False, False, False).tiene_impacto)


# ======================================================================= cargo tardío: siete días
class CargoTardio(unittest.TestCase):
    def test_limite_de_siete_dias_naturales(self):
        for dias, cargo in ((0, True), (6, True), (7, False), (8, False)):
            with self.subTest(dias=dias):
                self.assertEqual(cambio(dias).aplica_cargo_tardio, cargo)
                anticipacion = AnticipacionSolicitud(FECHA_EVENTO - timedelta(days=dias), FECHA_EVENTO)
                self.assertEqual(CAMBIO_CON_CARGO_TARDIO.es_satisfecha_por(anticipacion), cargo)
                self.assertEqual(CAMBIO_SIN_CARGO_TARDIO.es_satisfecha_por(anticipacion), not cargo)

    def test_se_cuentan_dias_naturales_por_fecha(self):
        tarde = AnticipacionSolicitud(FECHA_EVENTO.replace(hour=23, minute=59) - timedelta(days=7), FECHA_EVENTO.replace(hour=0))
        self.assertFalse(CAMBIO_CON_CARGO_TARDIO.es_satisfecha_por(tarde))

    def test_el_cargo_no_sustituye_la_evaluacion_de_viabilidad(self):
        """Con menos de siete días, un cambio no viable sigue cerrándose como No procedente y no genera importes."""
        sc = cambio(3)
        self.assertTrue(sc.aplica_cargo_tardio)
        self.assertEqual(sc.estado, ESC.REGISTRADA)                     # el cargo no decide la ruta por sí solo
        sc.registrar_viabilidad(ResultadoViabilidad(False, 'No es posible'), ImpactoModificacion(False, False, False), T)
        self.assertEqual(sc.estado, ESC.NO_PROCEDENTE)
        self.assertFalse(sc.importes_por_pagar)

    def test_cargo_tardio_genera_importes_si_el_cambio_es_viable(self):
        sc = cambio(3)
        sc.registrar_viabilidad(ResultadoViabilidad(True), ImpactoModificacion(False, False, False), T)
        self.assertEqual(sc.estado, ESC.PENDIENTE_FORMALIZACION)
        self.assertTrue(sc.importes_por_pagar)
        sc7 = cambio(7)
        sc7.registrar_viabilidad(ResultadoViabilidad(True), ImpactoModificacion(False, False, False), T)
        self.assertFalse(sc7.importes_por_pagar)

    def test_solicitud_usa_la_especificacion(self):
        with mock.patch.object(mod_solicitudes, 'CAMBIO_CON_CARGO_TARDIO', EspecificacionSimple(lambda a: True, 'x')):
            self.assertTrue(cambio(30).aplica_cargo_tardio)


# ======================================================================= servicios adicionales: cinco días
class ElegibilidadServicioAdicional(unittest.TestCase):
    def test_limite_de_cinco_dias_naturales(self):
        for dias, cumple in ((3, False), (4, False), (5, True), (6, True)):
            with self.subTest(dias=dias):
                ct = servicio_adicional().condicion_temporal(a_dias(dias), False)
                self.assertEqual(ct.cumple, cumple)
                self.assertEqual(ct.motivo, '' if cumple else MOTIVO_CINCO_DIAS)

    def test_elegibilidad_obtenida_se_conserva_con_menos_de_cinco_dias(self):
        for dias in (4, 1, 0):
            with self.subTest(dias=dias):
                self.assertTrue(servicio_adicional(elegibilidad=True).condicion_temporal(a_dias(dias), False).cumple)

    def test_evento_iniciado_impide_continuar_aunque_haya_elegibilidad(self):
        for eleg in (False, True):
            ct = servicio_adicional(eleg).condicion_temporal(a_dias(10), True)
            self.assertEqual((ct.cumple, ct.motivo), (False, MOTIVO_INICIADO_ADICIONAL))

    def test_evento_iniciado_se_informa_antes_que_el_plazo(self):
        ct = servicio_adicional().condicion_temporal(a_dias(2), True)
        self.assertEqual(ct.motivo, MOTIVO_INICIADO_ADICIONAL)
        self.assertEqual(SERVICIO_ADICIONAL_EN_PLAZO.motivos_incumplimiento(SituacionTemporalSolicitud(
            True, False, AnticipacionSolicitud(a_dias(2), FECHA_EVENTO))), [MOTIVO_INICIADO_ADICIONAL, MOTIVO_CINCO_DIAS])

    def test_solicitud_de_cambio_solo_exige_que_el_evento_no_haya_iniciado(self):
        self.assertTrue(cambio(1).condicion_temporal(False).cumple)
        ct = cambio(1).condicion_temporal(True)
        self.assertEqual((ct.cumple, ct.motivo), (False, MOTIVO_INICIADO_CAMBIO))
        self.assertEqual(SOLICITUD_CAMBIO_EN_PLAZO.primer_motivo(SituacionTemporalSolicitud(True)), MOTIVO_INICIADO_CAMBIO)

    def test_solicitud_usa_la_especificacion(self):
        with mock.patch.object(mod_solicitudes, 'SERVICIO_ADICIONAL_EN_PLAZO', EspecificacionSimple(lambda s: False, 'sustituida')):
            ct = servicio_adicional().condicion_temporal(a_dias(30), False)
            self.assertEqual((ct.cumple, ct.motivo), (False, 'sustituida'))


class RechazoYReanudacionDeServiciosAdicionales(unittest.TestCase):
    """Flujos del agregado con EvaluarRegularizacionDeSolicitudes, como lo hace el servicio de aplicación."""

    def evaluar(self, sa, ahora, saldo_vencido=False, cancelado=False, iniciado=False):
        d = EvaluarRegularizacionDeSolicitudes().evaluar(SituacionSaldo(saldo_vencido), cancelado,
                                                         sa.condicion_temporal(ahora, iniciado))
        sa.aplicar_decision_regularizacion(d, ahora, ESA.NO_PROCEDENTE)
        return d

    def test_con_menos_de_cinco_dias_se_rechaza_por_plazo_insuficiente(self):
        sa = servicio_adicional()
        self.evaluar(sa, a_dias(4))
        self.assertEqual(sa.estado, ESA.NO_PROCEDENTE)
        self.assertEqual(sa.motivo_cierre.causa, CausaCierreSolicitud.PLAZO_INSUFICIENTE)
        self.assertEqual(sa.motivo_cierre.descripcion, MOTIVO_CINCO_DIAS)

    def test_detenida_antes_de_obtener_elegibilidad_revalida_los_cinco_dias_al_retomarse(self):
        sa = servicio_adicional()
        d = self.evaluar(sa, a_dias(8), saldo_vencido=True)
        self.assertTrue(d.detener_por_saldo)
        self.assertEqual(sa.estado, ESA.DETENIDA_SALDO_VENCIDO)
        self.evaluar(sa, a_dias(4))                                   # saldo regularizado, pero quedan 4 días
        self.assertEqual(sa.estado, ESA.NO_PROCEDENTE)
        self.assertEqual(sa.motivo_cierre.causa, CausaCierreSolicitud.PLAZO_INSUFICIENTE)

    def test_detenida_y_retomada_dentro_del_plazo_continua(self):
        sa = servicio_adicional()
        self.evaluar(sa, a_dias(8), saldo_vencido=True)
        self.evaluar(sa, a_dias(6))
        self.assertEqual(sa.estado, ESA.REGISTRADA)                    # vuelve al estado anterior a la detención

    def test_elegibilidad_obtenida_a_tiempo_se_conserva_hasta_confirmar(self):
        sa = servicio_adicional()
        self.evaluar(sa, a_dias(6))
        sa.registrar_disponibilidad(DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ')), a_dias(6))
        self.assertTrue(sa.elegibilidad_obtenida)
        sa.registrar_decision_cliente(Decision('Cliente', True, a_dias(3)))
        sa.registrar_autorizacion(Decision('Administración', True, a_dias(3)))
        sa.asociar_anexo('AX-1'); sa.registrar_solicitud_pago('OB-1')
        self.assertEqual(sa.estado, ESA.PENDIENTE_PAGO)
        self.assertEqual(sa.confirmar(True, False, a_dias(2)), [])     # quedan 2 días y se confirma
        self.assertEqual(sa.estado, ESA.CONFIRMADA)

    def test_sin_elegibilidad_no_se_confirma_fuera_del_plazo(self):
        sa = servicio_adicional()
        self.assertIn('elegibilidad vigente', sa.confirmar(True, False, a_dias(2)))


# ======================================================================= SolicitudPuedeContinuar (O-01)
class OrdenO01(unittest.TestCase):
    def test_orden_de_las_partes(self):
        todo = SituacionContinuidadSolicitud(True, True, CondicionTemporal(False, MOTIVO_CINCO_DIAS))
        self.assertEqual(SOLICITUD_PUEDE_CONTINUAR.motivos_incumplimiento(todo), [MOTIVO_CANCELADO, MOTIVO_CINCO_DIAS, MOTIVO_SALDO])

    def test_prioridad_de_motivos_en_el_domain_service(self):
        evaluar = EvaluarRegularizacionDeSolicitudes().evaluar
        plazo = CondicionTemporal(False, MOTIVO_CINCO_DIAS)
        casos = [  # (saldo vencido, cancelado, condición) -> (continúa, detener, motivo)
            ((True, True, plazo), (False, False, MOTIVO_CANCELADO)),            # 1) evento cancelado
            ((True, False, plazo), (False, False, MOTIVO_CINCO_DIAS)),          # 2) plazo, aunque haya saldo vencido
            ((True, False, CondicionTemporal(True)), (False, True, MOTIVO_SALDO)),   # 3) saldo: se detiene
            ((False, False, CondicionTemporal(True)), (True, False, '')),
        ]
        for (saldo, cancelado, cond), esperado in casos:
            with self.subTest(saldo=saldo, cancelado=cancelado, condicion=cond.motivo):
                d = evaluar(SituacionSaldo(saldo), cancelado, cond)
                self.assertEqual((d.puede_continuar, d.detener_por_saldo, d.motivo), esperado)

    def test_evento_iniciado_precede_al_plazo_y_al_saldo(self):
        sa = servicio_adicional()
        d = EvaluarRegularizacionDeSolicitudes().evaluar(SituacionSaldo(True), False, sa.condicion_temporal(a_dias(2), True))
        self.assertEqual((d.puede_continuar, d.detener_por_saldo, d.motivo), (False, False, MOTIVO_INICIADO_ADICIONAL))

    def test_solo_el_saldo_detiene_la_solicitud(self):
        evaluar = EvaluarRegularizacionDeSolicitudes().evaluar
        self.assertTrue(evaluar(SituacionSaldo(True), False, CondicionTemporal(True)).detener_por_saldo)
        self.assertFalse(evaluar(SituacionSaldo(True), True, CondicionTemporal(True)).detener_por_saldo)
        self.assertFalse(evaluar(SituacionSaldo(True), False, CondicionTemporal(False, 'x')).detener_por_saldo)

    def test_domain_service_usa_la_especificacion(self):
        falsa = EspecificacionSimple(lambda s: False, 'sustituida')
        with mock.patch.object(mod_servicios, 'SOLICITUD_PUEDE_CONTINUAR', falsa):
            d = EvaluarRegularizacionDeSolicitudes().evaluar(SituacionSaldo(False), False, CondicionTemporal(True))
            self.assertEqual((d.puede_continuar, d.detener_por_saldo, d.motivo), (False, False, 'sustituida'))


if __name__ == '__main__':
    unittest.main()
