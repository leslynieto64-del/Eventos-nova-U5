"""Unidad 5 — reglas de negocio aprobadas de Eventos Nova: escenarios de éxito, error y límite (pytest, Arrange–Act–Assert).

Complementan la suite existente; no la sustituyen ni duplican lo que ya comprobaba. Se añaden solo los escenarios que no estaban
verificados de forma explícita:

  R-CAN  Cancelación solicitada por el Cliente (BN-008, SE-009, C-08, CA-084 a CA-088). La fecha y hora programadas (T) son un límite
         INCLUSIVO (C-15, GL-032): en T la cancelación ya se rechaza. La suite comprobaba T − 1 min y T + 2 h, pero no T exacto, ni
         el Domain Event y el actor de una cancelación procedente, ni el rechazo sin contratación confirmada desde el servicio, ni la
         segunda solicitud sobre un Evento ya Cancelado.
  R-REV  Revisión administrativa y constancia de no reembolso (BN-008, CA-089 a CA-091, C-12 y decisión C). La suite comprobaba el
         caso feliz; no los rechazos del agregado (Evento no cancelado, revisión sin constancia) ni que los pagos posteriores a la
         cancelación entren en la relación de pagos sin generar devolución.

  R-ANT  Anticipo de al menos el 30 % en 3 días HÁBILES (BN-009, C-03, decisión B, GL-060/C-15): importe exacto, un centavo menos y
         un centavo más, comprobante repetido y el límite exclusivo del plazo (00:00 del día siguiente al 3.er día hábil).
  R-SA   Servicio adicional con al menos 5 días NATURALES hasta el evento (SE-004, CA-077, CA-083), en el agregado: la hora no cuenta.
  R-CAM  Cargo por cambio tardío con menos de 7 días NATURALES (BN-003, CA-061, CA-062) y fecha del evento no reprogramable.
         (No existe en las fuentes aprobadas una prohibición de cambios con menos de 7 días: solo el cargo tardío.)

Otras pruebas existentes de las mismas reglas se reutilizan en la matriz (test_reglas_anticipo_decisiones_abc.py,
test_anticipo_pagos_parciales_e3_e4.py, test_d1_servicio_adicional_contratacion_confirmada.py, test_h08_inicio_evento.py).

Datos fijos: T0 = 01/10/2026 10:00 y T = 20/11/2026 18:00 (test_reglas_corregidas). Ninguna prueba depende del reloj ni del orden."""
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                    # noqa: E402
from domain.especificaciones import MOTIVO_EVENTO_INICIADO_SERVICIO_ADICIONAL                     # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                                     # noqa: E402
from domain.evento import Evento, RevisionAdministrativa, ServicioContratado                      # noqa: E402
from domain.eventos_dominio import EventoCancelado, PagoVerificado                                # noqa: E402
from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional                        # noqa: E402
from domain.valores import (AnticipacionSolicitud, CondicionesServicio, DatosEvento, ErrorDominio,  # noqa: E402
                            EstadoEvento as EE, EstadoObligacionPago as EO, EstadoPago as EPG,
                            EstadoSolicitudCambio as ESC, EstadoSolicitudCancelacion as ESCAN, Importe, OrigenCancelacion,
                            TarifaCargoTardio)

MOTIVO = 'El Cliente desiste del evento'


def evento_en_organizacion() -> Evento:
    """Evento con la contratación confirmada (En organización) y sin Domain Events pendientes."""
    ev = Evento('EV-U5', 'CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete'])
    ev.confirmar_contratacion([ServicioContratado('SC-1', 'Banquete', None, CondicionesServicio('Menú de tres tiempos'))])
    ev.extraer_eventos()
    return ev


@pytest.fixture
def contratado() -> Escenario:
    """Flujo real en memoria: contrato firmado, política comunicada y anticipo de 3000.00 verificado (Evento En organización)."""
    e = Escenario()
    e.confirmar_contratacion()
    return e


# ================================================================================ R-CAN: cancelación solicitada por el Cliente
def test_exito_cancelacion_antes_de_T_cancela_el_evento_y_registra_el_hecho_con_su_actor():          # BN-008, CA-087, C-08
    # Arrange
    ev = evento_en_organizacion()
    momento = FECHA_EVENTO - timedelta(minutes=1)
    # Act
    cancelado = ev.solicitar_cancelacion(MOTIVO, momento, contratacion_confirmada=True)
    # Assert
    assert cancelado is True
    assert ev.estado == EE.CANCELADO
    assert [s.estado for s in ev.solicitudes_cancelacion] == [ESCAN.PROCEDENTE]
    assert (ev.motivo_cancelacion.origen, ev.motivo_cancelacion.descripcion, ev.motivo_cancelacion.fecha,
            ev.motivo_cancelacion.registrado_por) == (OrigenCancelacion.SOLICITUD_CLIENTE, MOTIVO, momento, 'Coordinador')
    eventos = ev.extraer_eventos()
    assert [type(x) for x in eventos] == [EventoCancelado]                     # un único hecho, para el Outbox
    assert (eventos[0].agregado_id, eventos[0].ocurrido_en, eventos[0].origen) == ('EV-U5', momento, 'Solicitud del Cliente')


@pytest.mark.parametrize('desfase, procede, estado_final, estado_solicitud, eventos_esperados', [
    (timedelta(seconds=-1), True, EE.CANCELADO, ESCAN.PROCEDENTE, [EventoCancelado]),
    (timedelta(0), False, EE.EN_ORGANIZACION, ESCAN.RECHAZADA_INICIO_EVENTO, []),
    (timedelta(seconds=1), False, EE.EN_ORGANIZACION, ESCAN.RECHAZADA_INICIO_EVENTO, []),
], ids=['un-segundo-antes-de-T-procede', 'exactamente-en-T-se-rechaza', 'un-segundo-despues-de-T-se-rechaza'])
def test_limite_la_hora_programada_T_es_inclusiva_para_la_cancelacion(desfase, procede, estado_final, estado_solicitud,
                                                                      eventos_esperados):                # C-15, GL-032, CA-088
    # Arrange
    ev = evento_en_organizacion()
    # Act
    resultado = ev.solicitar_cancelacion(MOTIVO, FECHA_EVENTO + desfase, True)
    # Assert
    assert resultado is procede
    assert ev.estado == estado_final
    assert [s.estado for s in ev.solicitudes_cancelacion] == [estado_solicitud]   # el rechazo también queda registrado
    assert [type(x) for x in ev.extraer_eventos()] == eventos_esperados
    assert (ev.motivo_cancelacion is not None) is procede


def test_limite_cancelacion_solicitada_exactamente_en_T_desde_el_servicio(contratado):                  # CA-088, SE-009, C-15
    # Arrange
    e = contratado
    # Act
    r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, MOTIVO, FECHA_EVENTO)
    e.d.despachar()
    # Assert
    assert not r.exito
    ev = e.evento()
    assert ev.estado == EE.EN_ORGANIZACION                                    # la ejecución continúa
    assert [s.estado for s in ev.solicitudes_cancelacion] == [ESCAN.RECHAZADA_INICIO_EVENTO]
    assert e.avisos('Evento cancelado') == []                                 # sin EventoCancelado no hay reacción ni aviso
    assert len(e.avisos('Cancelación no procedente')) == 1


def test_error_sin_contratacion_confirmada_la_cancelacion_se_rechaza_sin_cambios():                     # CA-084, C-08
    # Arrange: contrato firmado, pero la contratación no se confirmó (Evento En gestión)
    e = Escenario()
    # Act
    r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, MOTIVO, T0 + timedelta(days=3))
    e.d.despachar()
    # Assert
    assert not r.exito
    assert 'CA-084' in r.mensaje
    ev = e.evento()
    assert ev.estado == EE.EN_GESTION                                         # nunca Cancelado (BN-009)
    assert ev.solicitudes_cancelacion == [] and ev.motivo_cancelacion is None
    assert e.avisos('Evento cancelado') == []


def test_error_un_evento_ya_cancelado_no_admite_otra_cancelacion_ni_otro_hecho():                      # GL-033, BN-008
    # Arrange
    ev = evento_en_organizacion()
    ev.solicitar_cancelacion('Primera solicitud', FECHA_EVENTO - timedelta(days=2), True)
    ev.extraer_eventos()
    # Act / Assert
    with pytest.raises(ErrorDominio, match='No puede cancelarse un evento Cancelado'):
        ev.solicitar_cancelacion('Segunda solicitud', FECHA_EVENTO - timedelta(days=1), True)
    assert len(ev.solicitudes_cancelacion) == 1                               # la transición se valida antes de registrar nada
    assert ev.motivo_cancelacion.descripcion == 'Primera solicitud'
    assert ev.extraer_eventos() == []


# ================================================================================ R-REV: revisión y constancia de no reembolso
def _cancelado(e: Escenario, cuando=T0 + timedelta(days=3)) -> None:
    r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, MOTIVO, cuando)
    e.d.despachar()
    assert r.exito, r.mensaje


def test_exito_la_revision_de_un_evento_cancelado_registra_la_constancia_en_el_agregado():             # CA-091, C-12
    # Arrange
    ev = evento_en_organizacion()
    ev.solicitar_cancelacion(MOTIVO, FECHA_EVENTO - timedelta(days=5), True)
    revision = RevisionAdministrativa('Sin reembolso', Importe(D('3000.00')), Importe(D('7000.00')), True, True,
                                      FECHA_EVENTO - timedelta(days=4))
    # Act
    ev.registrar_revision_administrativa(revision)
    # Assert
    assert ev.revision_administrativa == revision
    assert ev.estado == EE.CANCELADO


def test_limite_un_pago_posterior_a_la_cancelacion_entra_en_la_constancia_sin_devolucion(contratado):   # C-12, decisión C, T-24
    # Arrange: Evento cancelado y, después, un pago del saldo registrado y verificado
    e = contratado
    _cancelado(e)
    saldo = e.obligacion('SaldoContratoOriginal')
    pago = e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, Importe(D('500.00')), T0 + timedelta(days=5),
                                                'C-POSTERIOR')
    assert pago.exito and pago.datos['estado'] == 'Verificado'
    # Act
    r = e.s.cierre.registrar_revision_administrativa_cancelacion(e.evento_id, 'Revisión de contrato y pagos', T0 + timedelta(days=6))
    # Assert
    assert r.exito, r.mensaje
    assert r.datos == {'pagos_realizados': '3500.00', 'saldo_pendiente': '6500.00'}
    rev = e.evento().revision_administrativa
    assert (rev.pagos_realizados, rev.saldo_pendiente) == (Importe(D('3500.00')), Importe(D('6500.00')))
    assert rev.constancia_no_reembolso is True and rev.politica_incluida is True
    assert e.ec().devoluciones == []                                          # no reembolso: ninguna devolución automática
    assert len(e.avisos('Revisión de cancelación')) == 1


def test_error_la_revision_administrativa_de_un_evento_no_cancelado_se_rechaza_sin_efectos(contratado):  # CA-091
    # Arrange
    e = contratado
    # Act
    r = e.s.cierre.registrar_revision_administrativa_cancelacion(e.evento_id, 'Revisión', T0 + timedelta(days=4))
    # Assert
    assert not r.exito
    assert 'CA-091' in r.mensaje
    assert e.evento().revision_administrativa is None
    assert e.evento().estado == EE.EN_ORGANIZACION
    assert e.avisos('Revisión de cancelación') == []                          # el aviso solo sale tras registrar la revisión


def test_error_una_revision_sin_constancia_de_no_reembolso_se_rechaza():                                # CA-091, C-12
    # Arrange
    ev = evento_en_organizacion()
    ev.solicitar_cancelacion(MOTIVO, FECHA_EVENTO - timedelta(days=5), True)
    sin_constancia = RevisionAdministrativa('Revisión incompleta', Importe(D('3000.00')), Importe(D('7000.00')), True, False,
                                            FECHA_EVENTO - timedelta(days=4))
    # Act / Assert
    with pytest.raises(ErrorDominio, match='constancia'):
        ev.registrar_revision_administrativa(sin_constancia)
    assert ev.revision_administrativa is None


# ================================================================================ R-ANT: anticipo mínimo del 30 % en 3 días hábiles
FIRMA = T0                                             # jueves 01/10/2026 10:00


def estado_cuenta_con_anticipo():
    """Contrato de 10,000.00 firmado el jueves 01/10/2026: anticipo mínimo de 3,000.00 (30 %)."""
    ec = EstadoCuenta('EC-U5', 'CT-U5', 'EV-U5')
    obligacion = ec.registrar_obligacion_anticipo('OB-ANT', Importe(D('10000.00')), FIRMA)
    return ec, obligacion


def test_exito_un_anticipo_del_30_por_ciento_exacto_liquida_la_obligacion_y_emite_pago_verificado():    # BN-009, CA-018
    # Arrange
    ec, obligacion = estado_cuenta_con_anticipo()
    # Act
    pago = ec.registrar_y_verificar_pago('PG-1', 'OB-ANT', Importe(D('3000.00')), FIRMA + timedelta(days=1), 'C-1', True)
    # Assert
    assert obligacion.importe == Importe(D('3000.00'))
    assert (pago.estado, obligacion.estado) == (EPG.VERIFICADO, EO.LIQUIDADA)
    assert (ec.anticipo_aplicado(), ec.anticipo_excedente()) == (D('3000.00'), D(0))
    eventos = ec.extraer_eventos()
    assert [type(x) for x in eventos] == [PagoVerificado]
    assert (eventos[0].obligacion_id, eventos[0].concepto) == ('OB-ANT', 'Anticipo')


@pytest.mark.parametrize('importe, estado_obligacion, cubre_el_minimo', [
    ('2999.99', EO.PENDIENTE, False),
    ('3000.00', EO.LIQUIDADA, True),
    ('3000.01', EO.LIQUIDADA, True),
], ids=['un-centavo-menos-pago-parcial', 'minimo-exacto', 'un-centavo-mas-sin-devolucion'])
def test_limite_el_30_por_ciento_es_un_minimo(importe, estado_obligacion, cubre_el_minimo):                  # B-1, B-2, B-3, E-3
    # Arrange
    ec, obligacion = estado_cuenta_con_anticipo()
    # Act
    pago = ec.registrar_y_verificar_pago('PG-1', 'OB-ANT', Importe(D(importe)), FIRMA + timedelta(days=1), 'C-1', True)
    # Assert
    assert pago.estado == EPG.VERIFICADO                                     # un pago menor ya no es «Importe incorrecto»
    assert obligacion.estado == estado_obligacion
    assert ec.anticipo_verificado() is cubre_el_minimo
    assert ec.devoluciones == []                                             # el excedente no se devuelve (B-3)


def test_error_un_comprobante_repetido_no_registra_otro_pago_ni_suma_al_anticipo():                       # E-3/E-4: un pago no cuenta dos veces
    # Arrange
    ec, obligacion = estado_cuenta_con_anticipo()
    ec.registrar_y_verificar_pago('PG-1', 'OB-ANT', Importe(D('1500.00')), FIRMA + timedelta(days=1), 'C-1', True)
    ec.extraer_eventos()
    # Act / Assert
    with pytest.raises(ErrorDominio, match='comprobante'):
        ec.registrar_y_verificar_pago('PG-2', 'OB-ANT', Importe(D('1500.00')), FIRMA + timedelta(days=1), 'C-1', True)
    assert [p.pago_id for p in ec.pagos] == ['PG-1']
    assert obligacion.estado == EO.PENDIENTE                                 # 1,500.00 no cubre el mínimo
    assert ec.extraer_eventos() == []


def test_limite_el_plazo_del_anticipo_son_tres_dias_habiles_con_limite_exclusivo():                       # BN-009, GL-060, C-15
    # Arrange: firma el jueves 01/10; hábiles: vie 02, lun 05 y mar 06 (el fin de semana no cuenta)
    _, obligacion = estado_cuenta_con_anticipo()
    # Act
    plazo = obligacion.plazo
    # Assert
    assert (plazo.vence, plazo.exclusivo) == (datetime(2026, 10, 7, 0, 0), True)
    assert plazo.vencido(datetime(2026, 10, 6, 23, 59, 59)) is False
    assert plazo.vencido(datetime(2026, 10, 7, 0, 0)) is True


# ================================================================================ R-SA: servicio adicional con 5 días naturales
def solicitud_servicio_adicional(registrada_en: datetime) -> SolicitudServicioAdicional:
    return SolicitudServicioAdicional('SA-U5', 'EV-U5', 'CT-U5', 'EC-U5', 'DJ', AnticipacionSolicitud(registrada_en, FECHA_EVENTO))


@pytest.mark.parametrize('ahora', [
    datetime(2026, 11, 10, 9, 0),                       # 10 días naturales
    datetime(2026, 11, 15, 0, 0),                       # exactamente 5 días naturales
    datetime(2026, 11, 15, 23, 59),                     # la hora no cuenta: siguen siendo 5 días naturales
], ids=['diez-dias', 'cinco-dias-a-las-00-00', 'cinco-dias-a-las-23-59'])
def test_exito_y_limite_con_cinco_o_mas_dias_naturales_el_servicio_adicional_esta_en_plazo(ahora):       # SE-004, CA-077
    # Arrange
    solicitud = solicitud_servicio_adicional(ahora)
    # Act
    condicion = solicitud.condicion_temporal(ahora, evento_iniciado=False)
    # Assert
    assert condicion.cumple is True


def test_limite_con_cuatro_dias_naturales_el_servicio_adicional_no_esta_en_plazo():                      # CA-077, CA-083
    # Arrange
    ahora = datetime(2026, 11, 16, 0, 0)
    solicitud = solicitud_servicio_adicional(ahora)
    # Act
    condicion = solicitud.condicion_temporal(ahora, evento_iniciado=False)
    # Assert
    assert condicion.cumple is False
    assert 'cinco días naturales' in condicion.motivo


def test_error_con_el_evento_iniciado_el_primer_motivo_es_el_inicio_y_no_el_plazo():                     # SE-004 (orden de motivos)
    # Arrange
    ahora = datetime(2026, 11, 1, 9, 0)                 # sobran días, pero el Evento ya inició
    solicitud = solicitud_servicio_adicional(ahora)
    # Act
    condicion = solicitud.condicion_temporal(ahora, evento_iniciado=True)
    # Assert
    assert (condicion.cumple, condicion.motivo) == (False, MOTIVO_EVENTO_INICIADO_SERVICIO_ADICIONAL)


# ================================================================================ R-CAM: cargo por cambio tardío (7 días naturales)
def solicitud_cambio(registrada_en: datetime, datos_propuestos=None) -> SolicitudCambio:
    return SolicitudCambio('SC-U5', 'EV-U5', 'CT-U5', 'EC-U5', 'Cambiar el menú', AnticipacionSolicitud(registrada_en, FECHA_EVENTO),
                           TarifaCargoTardio(Importe(D('500.00'))), datos_propuestos)


@pytest.mark.parametrize('registrada_en, aplica_cargo', [
    (datetime(2026, 11, 1, 10, 0), False),              # 19 días naturales: sin cargo
    (datetime(2026, 11, 13, 23, 59), False),            # exactamente 7 días naturales: sin cargo
    (datetime(2026, 11, 14, 0, 0), True),               # 6 días naturales: con cargo tardío
], ids=['diecinueve-dias-sin-cargo', 'siete-dias-sin-cargo', 'seis-dias-con-cargo'])
def test_exito_y_limite_el_cargo_tardio_aplica_con_menos_de_siete_dias_naturales(registrada_en, aplica_cargo):   # BN-003, CA-061
    # Arrange / Act
    solicitud = solicitud_cambio(registrada_en)
    # Assert
    assert solicitud.estado == ESC.REGISTRADA                                # el cambio se admite en ambos casos
    assert solicitud.aplica_cargo_tardio is aplica_cargo


def test_error_un_cambio_no_puede_reprogramar_la_fecha_del_evento():                                       # BRD (fuera del alcance), GL-019
    # Arrange
    otra_fecha = DatosEvento('Boda', FECHA_EVENTO + timedelta(days=1), 'Salón', 100)
    # Act / Assert
    with pytest.raises(ErrorDominio, match='Reprogramar la fecha'):
        solicitud_cambio(datetime(2026, 11, 1, 10, 0), otra_fecha)


def test_limite_un_cambio_de_hora_el_mismo_dia_si_se_admite():                                            # GL-019
    # Arrange
    misma_fecha_otra_hora = DatosEvento('Boda', FECHA_EVENTO.replace(hour=20), 'Salón', 100)
    # Act
    solicitud = solicitud_cambio(datetime(2026, 11, 1, 10, 0), misma_fecha_otra_hora)
    # Assert
    assert solicitud.estado == ESC.REGISTRADA
    assert solicitud.datos_propuestos == misma_fecha_otra_hora
