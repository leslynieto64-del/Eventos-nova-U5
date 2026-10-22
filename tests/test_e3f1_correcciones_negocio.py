"""E3F.1 — Correcciones de negocio del flujo de SolicitudCambio.

A. Causa al cerrar por regularización con el Evento iniciado (hallazgo N3). Las solicitudes de cambio que siguen sin
   confirmar cuando inicia el Evento se cierran como no procedentes por inicio del evento (CA-070, GL-032; BPMN SP-03,
   evento de borde «Evento iniciado»). Antes, `_SolicitudBase.aplicar_decision_regularizacion` cerraba una
   SolicitudCambio con el motivo «El evento ya inició (CA-039).» con la causa «Evento cancelado». Una cancelación real
   conserva «Evento cancelado» (BN-008, SE-006), y SolicitudServicioAdicional (N6) y SustitucionProveedor no cambian.

B. Importes por pagar, solicitud de pago y confirmación (BN-003, SE-006, CA-041, CA-067, CA-068; mapa de dominio, puerta
   «¿Existen importes por pagar?»; BPMN SP-03, puerta «¿Genera nuevos importes por pagar?»). Con importes, el cambio pasa
   por la solicitud de pago y Pendiente de pago antes de confirmarse, y un pago informado como verificado no sustituye
   ese paso. Sin importes, no se genera una obligación de pago y se confirma desde Pendiente de formalización."""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_maquina_estados_solicitud_cambio import solicitud, observar, variantes, A10, A3, FECHA_EVENTO      # noqa: E402
from apoyo_regularizacion_solicitudes import DECISIONES                                                      # noqa: E402
from test_reglas_corregidas import Escenario, FECHA_EVENTO as FECHA_EVENTO_ESCENARIO                         # noqa: E402

from domain.solicitudes import (SolicitudCambio as SC, SolicitudServicioAdicional as SA, SustitucionProveedor as SP,  # noqa: E402
                                _SolicitudBase)
from domain.maquina_estados import TransicionNoPermitida                                                    # noqa: E402
from domain.servicios_dominio import EvaluarRegularizacionDeSolicitudes, SituacionSaldo                     # noqa: E402
from domain.especificaciones import (SOLICITUD_CAMBIO_EN_PLAZO, MOTIVO_EVENTO_INICIADO_SERVICIO_ADICIONAL,  # noqa: E402
                                     SituacionTemporalSolicitud)
from domain.valores import (ErrorDominio, Decision, CausaCierreSolicitud as CC, ResultadoViabilidad,       # noqa: E402
                            ImpactoModificacion, AnticipacionSolicitud, Importe, TipoSolicitud, ConceptoPago,
                            EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA,
                            EstadoSustitucionProveedor as ESP)

M_PAGO = "El pago se solicita con el anexo registrado (CA-068)."
M_SIN_IMPORTES = "No se puede solicitar el pago porque el cambio no genera importes por pagar (BN-003, CA-041, CA-067)."
F_SOLICITUD_PAGO = "solicitud de pago comunicada al Cliente (BN-003, CA-067)"
F_PAGO = "pago registrado y verificado"
F_ANEXO = "anexo vinculado al contrato original"
MOTIVO_INICIADO_CAMBIO = "El evento ya inició (CA-039)."
MOTIVO_CANCELADO = "El evento fue cancelado; la solicitud no puede retomarse (SE-006)."
VARIANTES = {n: (e, a) for n, e, a in variantes()}
VIABLE = ResultadoViabilidad(True)
SIN_IMPACTO = ImpactoModificacion(False, False, False)
COSTOS = ImpactoModificacion(False, True, False)
CONDICIONES = ImpactoModificacion(False, False, True)
SERVICIOS = ImpactoModificacion(True, False, False)
EVALUAR = EvaluarRegularizacionDeSolicitudes()


def en(nombre):
    estado, atributos = VARIANTES[nombre]
    return solicitud(estado, **atributos)


def nombres(eventos):
    return [e.nombre for e in eventos]


def adicional(estado=ESA.REGISTRADA):
    s = SA('SA-1', 'EV-1', 'CT-1', 'EC-1', 'DJ', AnticipacionSolicitud(A10, FECHA_EVENTO))
    s.extraer_eventos()
    if estado is ESA.DETENIDA_SALDO_VENCIDO:
        s._estado_antes_de_detener = ESA.REGISTRADA
    s.estado = estado
    return s


# ======================================================================= A: causa al regularizar con el Evento iniciado
class CausaDeCierreAlRegularizar(unittest.TestCase):
    def test_el_motivo_se_obtiene_de_la_specification(self):
        self.assertEqual(SC.MOTIVOS_EVENTO_INICIADO,
                         (SOLICITUD_CAMBIO_EN_PLAZO.primer_motivo(SituacionTemporalSolicitud(evento_iniciado=True)),))
        self.assertEqual(SC.MOTIVOS_EVENTO_INICIADO, (MOTIVO_INICIADO_CAMBIO,))
        self.assertEqual(solicitud().condicion_temporal(True).motivo, MOTIVO_INICIADO_CAMBIO)
        self.assertEqual(_SolicitudBase.MOTIVOS_EVENTO_INICIADO, ())
        self.assertNotIn('MOTIVOS_EVENTO_INICIADO', vars(SA))                 # SA y SP heredan la tupla vacía
        self.assertNotIn('MOTIVOS_EVENTO_INICIADO', vars(SP))

    def test_evento_iniciado_cierra_por_inicio_del_evento(self):           # CA-070, GL-032, BPMN SP-03
        for variante in ('REGISTRADA|10d', 'REGISTRADA|3d', 'DETENIDA_SALDO_VENCIDO|antes=REGISTRADA'):
            with self.subTest(variante=variante):
                s = en(variante)
                d = EVALUAR.evaluar(SituacionSaldo(False), False, s.condicion_temporal(True))   # flujo real de la decisión
                self.assertEqual((d.puede_continuar, d.detener_por_saldo, d.motivo), (False, False, MOTIVO_INICIADO_CAMBIO))
                self.assertFalse(s.aplicar_decision_regularizacion(d, A10, ESC.NO_PROCEDENTE))
                self.assertEqual(s.estado, ESC.NO_PROCEDENTE)
                self.assertEqual((s.motivo_cierre.causa, s.motivo_cierre.descripcion, s.motivo_cierre.fecha),
                                 (CC.INICIO_EVENTO, MOTIVO_INICIADO_CAMBIO, A10))
                self.assertNotEqual(s.motivo_cierre.causa, CC.EVENTO_CANCELADO)
                self.assertEqual(s.extraer_eventos(), [])                      # sin Domain Events incorrectos

    def test_cancelacion_real_conserva_su_causa(self):                     # BN-008, SE-006, O-01
        for iniciado in (False, True):                                         # cancelado e iniciado: primero la cancelación
            for variante in ('REGISTRADA|10d', 'DETENIDA_SALDO_VENCIDO|antes=REGISTRADA'):
                with self.subTest(variante=variante, iniciado=iniciado):
                    s = en(variante)
                    d = EVALUAR.evaluar(SituacionSaldo(False), True, s.condicion_temporal(iniciado))
                    self.assertEqual(d.motivo, MOTIVO_CANCELADO)
                    s.aplicar_decision_regularizacion(d, A10, ESC.NO_PROCEDENTE)
                    self.assertEqual((s.estado, s.motivo_cierre.causa), (ESC.NO_PROCEDENTE, CC.EVENTO_CANCELADO))

    def test_saldo_continuar_y_estados_protegidos_sin_cambios(self):      # N2
        s = en('REGISTRADA|10d')
        self.assertFalse(s.aplicar_decision_regularizacion(EVALUAR.evaluar(SituacionSaldo(True), False,
                                                                           s.condicion_temporal(False)), A10, ESC.NO_PROCEDENTE))
        self.assertEqual(s.estado, ESC.DETENIDA_SALDO_VENCIDO)
        self.assertTrue(s.aplicar_decision_regularizacion(DECISIONES['continuar'], A10, ESC.NO_PROCEDENTE))
        self.assertEqual(s.estado, ESC.REGISTRADA)
        for variante in ('PENDIENTE_APROBACION_CLIENTE', 'PENDIENTE_PAGO', 'CONFIRMADA'):
            with self.subTest(variante=variante):
                s = en(variante); antes = observar(en(variante))
                self.assertFalse(s.aplicar_decision_regularizacion(DECISIONES['no_procede_evento_iniciado_cambio'], A10,
                                                                   ESC.NO_PROCEDENTE))
                self.assertEqual(observar(s), antes)

    def test_servicio_adicional_sin_cambios(self):                          # N6 (CA-099, CA-100) y N2
        casos = [(MOTIVO_EVENTO_INICIADO_SERVICIO_ADICIONAL, CC.INICIO_EVENTO),              # N6
                 ("Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).", CC.PLAZO_INSUFICIENTE),
                 (MOTIVO_CANCELADO, CC.EVENTO_CANCELADO),
                 (MOTIVO_INICIADO_CAMBIO, CC.EVENTO_CANCELADO)]       # motivo que SA nunca produce: resultado anterior
        for estado in (ESA.REGISTRADA, ESA.DETENIDA_SALDO_VENCIDO):
            for motivo, causa in casos:
                with self.subTest(estado=estado, motivo=motivo):
                    s = adicional(estado)
                    d = next(d for d in DECISIONES.values() if d.motivo == motivo) if motivo != MOTIVO_EVENTO_INICIADO_SERVICIO_ADICIONAL \
                        else EVALUAR.evaluar(SituacionSaldo(False), False, s.condicion_temporal(A10, True))
                    s.aplicar_decision_regularizacion(d, A10, ESA.NO_PROCEDENTE)
                    self.assertEqual((s.estado, s.motivo_cierre.causa), (ESA.NO_PROCEDENTE, causa))

    def test_sustitucion_no_se_regulariza(self):
        self.assertEqual(SP.ESTADOS_REGULARIZABLES, ())
        for estado in ESP:
            for nombre, d in DECISIONES.items():
                with self.subTest(estado=estado, decision=nombre):
                    s = SP('SP-1', 'EV-1', 'SC-1', 'PV-1', 'CT-1', 'EC-1', A10); s.extraer_eventos(); s.estado = estado
                    self.assertEqual(s.aplicar_decision_regularizacion(d, A10, None), d.puede_continuar)
                    self.assertEqual((s.estado, s.motivo_cierre), (estado, None))

    def test_servicio_retomar_tras_el_inicio_del_evento(self):             # reproducción con los servicios reales
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(100)),
                                                     e.comunicacion).datos['solicitud_id']
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.DETENIDA_SALDO_VENCIDO)
        self.assertTrue(e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO_ESCENARIO).exito)
        self.assertTrue(e.evento().iniciado)
        self.assertFalse(e.evento().cancelado)
        e.s.cambios.retomar_solicitud_cambio(sc, FECHA_EVENTO_ESCENARIO + timedelta(minutes=5))   # antes de las reacciones
        s = e.app.repos.cambios.obtener_por_id(sc)
        self.assertEqual((s.estado, s.motivo_cierre.causa, s.motivo_cierre.descripcion),
                         (ESC.NO_PROCEDENTE, CC.INICIO_EVENTO, MOTIVO_INICIADO_CAMBIO))
        e.d.despachar()                                                         # la reacción al inicio no lo modifica
        s = e.app.repos.cambios.obtener_por_id(sc)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESC.NO_PROCEDENTE, CC.INICIO_EVENTO))


# ======================================================================= A: dos caminos al iniciar el Evento
class DosCaminosAlIniciarElEvento(unittest.TestCase):
    """Se conservan dos caminos distintos, ambos con la causa «Inicio del evento»:
    1. Retomar (regularización N2) una solicitud cuando el Evento ya inició → NO_PROCEDENTE, sin Domain Event
       (CA-070: «cerrarse como no procedente por inicio del evento»; GL-032; BPMN SP-03).
    2. Reacción al inicio del Evento sobre una solicitud en trámite (`cerrar_por_inicio_evento`) → CERRADA_INICIO_EVENTO,
       con SolicitudCambioCerradaPorInicioEvento (comportamiento de E3F, sin cambios).
    No se unifican: ninguna fuente aprobada exige un único estado."""
    DESCRIPCION_REACCION = "El evento inició antes de confirmar"

    def test_camino_retomar_no_procedente(self):
        for variante in ('REGISTRADA|10d', 'DETENIDA_SALDO_VENCIDO|antes=REGISTRADA'):
            with self.subTest(variante=variante):
                s = en(variante)
                d = EVALUAR.evaluar(SituacionSaldo(False), False, s.condicion_temporal(True))
                s.aplicar_decision_regularizacion(d, A10, ESC.NO_PROCEDENTE)
                self.assertEqual((s.estado, s.motivo_cierre.causa, s.motivo_cierre.descripcion),
                                 (ESC.NO_PROCEDENTE, CC.INICIO_EVENTO, MOTIVO_INICIADO_CAMBIO))
                self.assertNotEqual(s.estado, ESC.CERRADA_INICIO_EVENTO)
                self.assertEqual(s.extraer_eventos(), [])

    def test_camino_reaccion_cerrada_inicio_evento(self):
        for nombre, estado, _ in variantes():
            if estado in SC.FINALES:
                continue
            with self.subTest(variante=nombre):
                s = en(nombre)
                s.cerrar_por_inicio_evento(FECHA_EVENTO)
                self.assertEqual((s.estado, s.motivo_cierre.causa, s.motivo_cierre.descripcion),
                                 (ESC.CERRADA_INICIO_EVENTO, CC.INICIO_EVENTO, self.DESCRIPCION_REACCION))
                self.assertNotEqual(s.estado, ESC.NO_PROCEDENTE)
                self.assertEqual(nombres(s.extraer_eventos()), ['SolicitudCambioCerradaPorInicioEvento'])

    def test_cada_camino_no_modifica_el_resultado_del_otro(self):
        s = en('DETENIDA_SALDO_VENCIDO|antes=REGISTRADA')                      # 1 y después 2
        s.aplicar_decision_regularizacion(EVALUAR.evaluar(SituacionSaldo(False), False, s.condicion_temporal(True)),
                                          A10, ESC.NO_PROCEDENTE)
        s.cerrar_por_inicio_evento(FECHA_EVENTO)
        self.assertEqual((s.estado, s.motivo_cierre.causa, s.extraer_eventos()), (ESC.NO_PROCEDENTE, CC.INICIO_EVENTO, []))
        s = en('DETENIDA_SALDO_VENCIDO|antes=REGISTRADA')                      # 2 y después 1
        s.cerrar_por_inicio_evento(FECHA_EVENTO); s.extraer_eventos()
        self.assertFalse(s.aplicar_decision_regularizacion(DECISIONES['no_procede_evento_iniciado_cambio'], A10,
                                                           ESC.NO_PROCEDENTE))
        self.assertEqual((s.estado, s.motivo_cierre.descripcion), (ESC.CERRADA_INICIO_EVENTO, self.DESCRIPCION_REACCION))

    def test_servicio_reaccion_al_inicio(self):
        """Con los servicios: la reacción al inicio cierra en CERRADA_INICIO_EVENTO una solicitud en trámite y una
        detenida; retomarla después no la modifica."""
        e = Escenario(); e.confirmar_contratacion()
        dia = FECHA_EVENTO_ESCENARIO - timedelta(days=10)
        en_tramite = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(150)),
                                                             dia).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(en_tramite, VIABLE, None, dia)     # Pendiente de formalización
        e.vencer_saldo_y_comunicar_moratorios()
        detenida = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Otro', Importe(D(150)),
                                                           e.comunicacion).datos['solicitud_id']
        self.assertEqual(e.app.repos.cambios.obtener_por_id(detenida).estado, ESC.DETENIDA_SALDO_VENCIDO)
        self.assertTrue(e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO_ESCENARIO).exito)
        e.d.despachar()                                                         # reacción al inicio
        for sc in (en_tramite, detenida):
            s = e.app.repos.cambios.obtener_por_id(sc)
            self.assertEqual((s.estado, s.motivo_cierre.causa), (ESC.CERRADA_INICIO_EVENTO, CC.INICIO_EVENTO))
        e.s.cambios.retomar_solicitud_cambio(detenida, FECHA_EVENTO_ESCENARIO + timedelta(minutes=5))
        self.assertEqual(e.app.repos.cambios.obtener_por_id(detenida).estado, ESC.CERRADA_INICIO_EVENTO)


# ======================================================================= B: importes, solicitud de pago y confirmación
class RutaDePagoE3F1(unittest.TestCase):
    def test_calculo_de_importes_sin_cambios(self):                          # BN-003, SE-003, SE-005, CA-061, CA-062
        casos = [(COSTOS, A10, True), (CONDICIONES, A10, False), (SERVICIOS, A10, False), (SIN_IMPACTO, A10, False),
                 (SIN_IMPACTO, A3, True), (CONDICIONES, A3, True)]
        for impacto, fecha, importes in casos:
            with self.subTest(impacto=impacto, fecha=fecha):
                s = solicitud(fecha_solicitud=fecha)
                s.registrar_viabilidad(VIABLE, impacto, A10)
                self.assertEqual(s.importes_por_pagar, importes)

    def test_solicitud_de_pago_con_importes(self):                           # CA-067, CA-068
        for variante in ('PENDIENTE_FORMALIZACION|ruta_B|con_anexo', 'PENDIENTE_FORMALIZACION|ruta_C|cargo_tardio|con_anexo'):
            with self.subTest(variante=variante):
                s = en(variante)
                self.assertTrue(s.importes_por_pagar)
                s.registrar_solicitud_pago('OB-9')
                self.assertEqual((s.estado, s.obligacion_pago_id), (ESC.PENDIENTE_PAGO, 'OB-9'))
                self.assertEqual(s.extraer_eventos(), [])

    def test_solicitud_de_pago_sin_importes_se_rechaza_sin_efectos(self):    # BN-003, CA-067
        s = en('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo')
        antes = observar(en('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo'))
        with self.assertRaises(ErrorDominio) as ctx:
            s.registrar_solicitud_pago('OB-9')
        self.assertEqual(str(ctx.exception), M_SIN_IMPORTES)
        self.assertNotIsInstance(ctx.exception, TransicionNoPermitida)          # es una condición de negocio, no de estado
        self.assertEqual(observar(s), antes)
        self.assertEqual((s.estado, s.obligacion_pago_id), (ESC.PENDIENTE_FORMALIZACION, None))

    def test_orden_de_los_rechazos_de_la_solicitud_de_pago(self):
        s = en('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|sin_anexo')         # sin anexo y sin importes: primero el anexo
        with self.assertRaises(ErrorDominio) as ctx:
            s.registrar_solicitud_pago('OB-9')
        self.assertEqual(str(ctx.exception), M_PAGO)
        s = en('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo')         # con anexo y sin importes
        with self.assertRaises(ErrorDominio) as ctx:
            s.registrar_solicitud_pago('OB-9')
        self.assertEqual(str(ctx.exception), M_SIN_IMPORTES)
        s = en('PENDIENTE_AUTORIZACION')                                         # estado no válido: primero la máquina
        with self.assertRaises(TransicionNoPermitida) as ctx:
            s.registrar_solicitud_pago('OB-9')
        self.assertEqual(str(ctx.exception), M_PAGO)

    def test_pago_verificado_no_omite_pendiente_de_pago(self):               # CA-041, CA-067, CA-068
        for variante in ('PENDIENTE_FORMALIZACION|ruta_B|con_anexo', 'PENDIENTE_FORMALIZACION|ruta_C|cargo_tardio|con_anexo'):
            with self.subTest(variante=variante):
                s = en(variante); antes = observar(en(variante))
                self.assertEqual(s.confirmar(True, False, A10), [F_SOLICITUD_PAGO])
                self.assertEqual(observar(s), antes)                            # sin mutación ni CambioConfirmado
                self.assertEqual(s.confirmar(False, False, A10), [F_SOLICITUD_PAGO, F_PAGO])

    def test_confirmar_con_importes_valida_anexo_y_pago(self):
        s = en('PENDIENTE_FORMALIZACION|ruta_B|sin_anexo')
        self.assertEqual(s.confirmar(False, True, A10, True),
                         ['evento no iniciado', 'evento no cancelado (SE-007)', F_SOLICITUD_PAGO, F_ANEXO, F_PAGO])
        s = en('PENDIENTE_PAGO')
        self.assertEqual(s.confirmar(False, False, A10), [F_PAGO])
        self.assertEqual(s.confirmar(True, True, A10), ['evento no iniciado'])
        self.assertEqual(s.estado, ESC.PENDIENTE_PAGO)
        self.assertEqual(s.confirmar(True, False, A10), [])
        self.assertEqual((s.estado, nombres(s.extraer_eventos())), (ESC.CONFIRMADA, ['CambioConfirmado']))

    def test_confirmar_sin_importes_desde_formalizacion(self):              # BN-003, CA-038, CA-041
        s = en('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo')
        self.assertEqual(s.confirmar(False, False, A10), [])                    # no espera un pago inexistente
        self.assertEqual((s.estado, s.obligacion_pago_id), (ESC.CONFIRMADA, None))
        self.assertEqual(nombres(s.extraer_eventos()), ['CambioConfirmado'])
        s = en('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|sin_anexo')
        self.assertEqual(s.confirmar(False, False, A10), [F_ANEXO])              # el anexo sigue siendo obligatorio

    def test_recorrido_con_pago(self):                                       # ruta C con cargo por cambio tardío
        s = solicitud(fecha_solicitud=A3)
        s.registrar_viabilidad(VIABLE, SIN_IMPACTO, A3)
        self.assertEqual((s.estado, s.importes_por_pagar), (ESC.PENDIENTE_FORMALIZACION, True))
        s.asociar_anexo('AX-1')
        self.assertEqual(s.confirmar(True, False, A3), [F_SOLICITUD_PAGO])
        s.registrar_solicitud_pago('OB-1')
        self.assertEqual(s.estado, ESC.PENDIENTE_PAGO)
        self.assertEqual(s.confirmar(False, False, A3), [F_PAGO])
        self.assertEqual(s.confirmar(True, False, A3), [])
        self.assertEqual(nombres(s.extraer_eventos()), ['ViabilidadCambioEvaluada', 'CambioConfirmado'])

    def test_recorrido_sin_pago_con_aprobaciones(self):                     # ruta B que solo afecta condiciones
        s = solicitud()
        s.registrar_viabilidad(VIABLE, CONDICIONES, A10)
        self.assertEqual((s.estado, s.importes_por_pagar), (ESC.PENDIENTE_APROBACION_CLIENTE, False))
        s.registrar_decision_cliente(Decision('Cliente', True, A10))
        s.registrar_autorizacion(Decision('Administración', True, A10))
        s.asociar_anexo('AX-1')
        with self.assertRaises(ErrorDominio):
            s.registrar_solicitud_pago('OB-1')
        self.assertEqual(s.confirmar(False, False, A10), [])
        self.assertEqual((s.estado, s.obligacion_pago_id), (ESC.CONFIRMADA, None))

    def test_servicio_no_genera_obligacion_sin_importes(self):              # GestionPagosService, misma transacción
        e = Escenario(); e.confirmar_contratacion()
        dia = FECHA_EVENTO_ESCENARIO - timedelta(days=10)
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(150)), dia).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sc, VIABLE, None, dia)            # ruta C, sin importes
        e.s.cambios.registrar_anexo_cambio(sc, 'Anexo', dia); e.d.despachar()
        obligaciones = set(e.ec().obligaciones)
        r = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.CAMBIO, sc, ConceptoPago.CAMBIO, Importe(D(900)), dia)
        self.assertFalse(r.exito)
        self.assertEqual(r.mensaje, M_SIN_IMPORTES)
        self.assertEqual(set(e.ec().obligaciones), obligaciones)                 # la transacción se revirtió
        s = e.app.repos.cambios.obtener_por_id(sc)
        self.assertEqual((s.estado, s.obligacion_pago_id), (ESC.PENDIENTE_FORMALIZACION, None))
        self.assertTrue(e.s.cambios.confirmar_cambio(sc, dia).exito)

    def test_servicio_con_importes_exige_la_solicitud_de_pago(self):
        e = Escenario(); e.confirmar_contratacion()
        dia = FECHA_EVENTO_ESCENARIO - timedelta(days=10)
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(150)), dia).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sc, VIABLE, Importe(D(900)), dia)  # afecta costos: ruta B
        e.s.cambios.registrar_decision_cliente_cambio(sc, Decision('Cliente', True, dia))
        e.s.cambios.registrar_autorizacion_administracion_cambio(sc, Decision('Administración', True, dia))
        e.s.cambios.registrar_anexo_cambio(sc, 'Anexo', dia); e.d.despachar()
        r = e.s.cambios.confirmar_cambio(sc, dia)
        self.assertFalse(r.exito)
        self.assertEqual(r.pendientes, [F_SOLICITUD_PAGO, F_PAGO])
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.PENDIENTE_FORMALIZACION)
        ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.CAMBIO, sc, ConceptoPago.CAMBIO, Importe(D(900)), dia)
        self.assertTrue(ob.exito)
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.PENDIENTE_PAGO)
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.datos['obligacion_id'], Importe(D(900)), dia + timedelta(hours=2), 'C')
        self.assertTrue(e.s.cambios.confirmar_cambio(sc, dia + timedelta(hours=3)).exito)


if __name__ == '__main__':
    unittest.main()
