"""Unidad 5 — colaboradores externos sustituidos por dobles de prueba (unittest.mock) sobre los puertos EXISTENTES de la aplicación.

Eventos Nova no tiene integraciones reales (docs/architecture/integraciones-externas.md): los pagos y las devoluciones se efectúan fuera
del sistema. La aplicación los usa a través de puertos (application/puertos.py):
  IVerificadorPagos.verificar(comprobante, importe) -> bool
  IEjecutorDevoluciones.ejecutar(devolucion_id, importe, referencia_idempotente) -> comprobante
  INotificadorParticipantes.notificar(destinatarios, asunto, detalle)
Contrato existente que se verifica (application/servicios.py): un rechazo del colaborador es un resultado de negocio; una falla técnica
(cualquier excepción que no sea ErrorDominio, p. ej. un timeout) se PROPAGA para poder reintentarse, y como el colaborador se consulta
ANTES de abrir la transacción, no deja pagos, devoluciones ni Domain Events a medias.

Se comprueban la respuesta satisfactoria, el rechazo, el error o timeout, el número y los argumentos de las llamadas y la ausencia de
efectos secundarios. Ninguna prueba llama a una pasarela, banco o servicio de correo real: `create_autospec` exige además que cada
llamada respete la firma del puerto."""
import os
import sys
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import create_autospec

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                    # noqa: E402
from application.puertos import IEjecutorDevoluciones, INotificadorParticipantes, IVerificadorPagos   # noqa: E402
from domain.valores import (EstadoDevolucion, EstadoEvento, EstadoObligacionPago, EstadoPago,      # noqa: E402
                            Importe)

IMPORTE = Importe(D('1000.00'))
FECHA_PAGO = T0 + timedelta(days=5)                    # dentro del plazo del saldo (vence 3 días hábiles antes del evento)


def tipos_nuevos(e: Escenario, desde: int):
    """Nombres de los Domain Events que entraron al Outbox en memoria a partir de la posición `desde`."""
    return [type(r.evento).__name__ for r in e.app.uow.outbox[desde:]]


@pytest.fixture
def contratado() -> Escenario:
    e = Escenario()
    e.confirmar_contratacion()                         # usa los adaptadores simulados; los dobles se instalan después
    return e


@pytest.fixture
def verificador(contratado):
    doble = create_autospec(IVerificadorPagos, instance=True)
    contratado.s.pagos.verificador = doble
    return doble


# ================================================================================ verificación de pagos (IVerificadorPagos)
def test_pago_verificado_por_el_colaborador_queda_verificado_y_emite_un_solo_hecho(contratado, verificador):
    # Arrange
    e = contratado
    verificador.verificar.return_value = True
    saldo = e.obligacion('SaldoContratoOriginal')
    outbox_antes = len(e.app.uow.outbox)
    # Act
    r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, IMPORTE, FECHA_PAGO, 'C-SALDO-1')
    # Assert
    assert r.exito and r.datos['estado'] == 'Verificado'
    verificador.verificar.assert_called_once_with('C-SALDO-1', IMPORTE)
    pago = next(p for p in e.ec().pagos if p.comprobante == 'C-SALDO-1')
    assert pago.estado == EstadoPago.VERIFICADO
    assert e.ec().importe_pagado(saldo.obligacion_id) == D('1000.00')
    assert tipos_nuevos(e, outbox_antes) == ['PagoVerificado']


def test_pago_rechazado_por_el_colaborador_queda_registrado_sin_aplicarse(contratado, verificador):
    # Arrange
    e = contratado
    verificador.verificar.return_value = False
    saldo = e.obligacion('SaldoContratoOriginal')
    outbox_antes = len(e.app.uow.outbox)
    # Act
    r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, IMPORTE, FECHA_PAGO, 'C-SALDO-1')
    # Assert
    assert r.exito and r.datos['estado'] == 'Registrado'            # registrado ≠ verificado (GL-046, GL-052)
    verificador.verificar.assert_called_once_with('C-SALDO-1', IMPORTE)
    ec = e.ec()
    assert [p.estado for p in ec.pagos if p.comprobante == 'C-SALDO-1'] == [EstadoPago.REGISTRADO]
    assert ec.importe_pagado(saldo.obligacion_id) == D(0)
    assert ec.obligaciones[saldo.obligacion_id].estado == EstadoObligacionPago.PENDIENTE
    assert tipos_nuevos(e, outbox_antes) == []                    # sin PagoVerificado no hay reacciones


def test_timeout_del_colaborador_se_propaga_y_no_registra_el_pago(contratado, verificador):
    # Arrange
    e = contratado
    verificador.verificar.side_effect = TimeoutError('la verificación no respondió a tiempo')
    saldo = e.obligacion('SaldoContratoOriginal')
    pagos_antes, outbox_antes = len(e.ec().pagos), len(e.app.uow.outbox)
    # Act / Assert
    with pytest.raises(TimeoutError):
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, IMPORTE, FECHA_PAGO, 'C-SALDO-1')
    verificador.verificar.assert_called_once_with('C-SALDO-1', IMPORTE)
    assert len(e.ec().pagos) == pagos_antes                       # nada a medias: el pago puede reintentarse
    assert e.ec().obligaciones[saldo.obligacion_id].estado == EstadoObligacionPago.PENDIENTE
    assert tipos_nuevos(e, outbox_antes) == []


def test_verificacion_posterior_rechazada_deja_el_pago_registrado(contratado, verificador):
    # Arrange: el pago se registra sin verificar (no se consulta al colaborador)
    e = contratado
    saldo = e.obligacion('SaldoContratoOriginal')
    registrado = e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, IMPORTE, FECHA_PAGO, 'C-SALDO-2',
                                                      verificar_ahora=False)
    assert registrado.exito
    verificador.verificar.assert_not_called()
    verificador.verificar.return_value = False
    outbox_antes = len(e.app.uow.outbox)
    # Act
    r = e.s.pagos.verificar_pago_registrado(e.ec_id, registrado.datos['pago_id'], FECHA_PAGO + timedelta(days=1))
    # Assert
    assert not r.exito and 'permanece registrado' in r.mensaje
    verificador.verificar.assert_called_once_with('C-SALDO-2', IMPORTE)
    assert next(p for p in e.ec().pagos if p.pago_id == registrado.datos['pago_id']).estado == EstadoPago.REGISTRADO
    assert tipos_nuevos(e, outbox_antes) == []


# ================================================================================ ejecución de devoluciones (IEjecutorDevoluciones)
def con_devolucion_del_anticipo():
    """Contratación cerrada sin confirmar (CA-021) y anticipo de 3000 pagado después del cierre: genera una devolución A (A-1, A-3).
    Mismo recorrido que test_integraciones_simuladas.DevolucionConComprobanteDeAdministracion."""
    e = Escenario()
    e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
    contacto = T0 + timedelta(days=6)
    e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
    ob = e.obligacion('Anticipo')
    cierre = contacto + timedelta(hours=31)
    e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, cierre, 'Sin pago', True)
    e.d.despachar()
    e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('3000')), cierre + timedelta(days=1), 'C',
                                         registrado_en=cierre + timedelta(days=1))
    e.d.despachar()
    devolucion = e.ec().devoluciones[0]
    assert devolucion.estado == EstadoDevolucion.PENDIENTE
    return e, devolucion


@pytest.fixture
def ejecutor_y_devolucion():
    e, devolucion = con_devolucion_del_anticipo()
    doble = create_autospec(IEjecutorDevoluciones, instance=True)
    e.s.pagos.ejecutor = doble
    return e, devolucion, doble


def test_devolucion_ejecutada_por_el_colaborador_registra_su_comprobante(ejecutor_y_devolucion):           # CA-098, A-6
    # Arrange
    e, d, ejecutor = ejecutor_y_devolucion
    ejecutor.ejecutar.return_value = 'TRANSF-EXT-0001'
    outbox_antes = len(e.app.uow.outbox)
    ahora = d.fecha_limite - timedelta(hours=1)                    # dentro de los cinco días hábiles
    # Act
    r = e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, ahora)
    # Assert
    assert r.exito and r.datos['en_plazo'] is True and r.datos['comprobante'] == 'TRANSF-EXT-0001'
    ejecutor.ejecutar.assert_called_once_with(d.devolucion_id, d.importe, referencia_idempotente=d.devolucion_id)
    efectuada = e.ec().devoluciones[0]
    assert (efectuada.estado, efectuada.comprobante, efectuada.fecha_devolucion) == (EstadoDevolucion.EFECTUADA, 'TRANSF-EXT-0001', ahora)
    assert tipos_nuevos(e, outbox_antes) == ['DevolucionRegistrada']


def test_colaborador_no_disponible_la_devolucion_sigue_pendiente_y_sin_hecho_registrado(ejecutor_y_devolucion):
    # Arrange
    e, d, ejecutor = ejecutor_y_devolucion
    ejecutor.ejecutar.side_effect = ConnectionError('servicio de transferencias no disponible')
    outbox_antes = len(e.app.uow.outbox)
    # Act / Assert
    with pytest.raises(ConnectionError):
        e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, d.fecha_limite - timedelta(hours=1))
    assert ejecutor.ejecutar.call_count == 1
    pendiente = e.ec().devoluciones[0]
    assert (pendiente.estado, pendiente.comprobante, pendiente.fecha_devolucion) == (EstadoDevolucion.PENDIENTE, None, None)
    assert tipos_nuevos(e, outbox_antes) == []
    e.d.despachar()
    assert e.avisos('Devolución efectuada') == []                 # sin DevolucionRegistrada no hay aviso al Coordinador


def test_el_reintento_tras_una_falla_usa_la_misma_referencia_idempotente(ejecutor_y_devolucion):
    # Arrange: la primera llamada falla y la segunda responde
    e, d, ejecutor = ejecutor_y_devolucion
    ejecutor.ejecutar.side_effect = [TimeoutError('sin respuesta'), 'TRANSF-EXT-0002']
    ahora = d.fecha_limite - timedelta(hours=1)
    with pytest.raises(TimeoutError):
        e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, ahora)
    # Act
    r = e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, ahora)
    # Assert
    assert r.exito and r.datos['comprobante'] == 'TRANSF-EXT-0002'
    assert ejecutor.ejecutar.call_count == 2
    referencias = [llamada.kwargs['referencia_idempotente'] for llamada in ejecutor.ejecutar.call_args_list]
    assert referencias == [d.devolucion_id, d.devolucion_id]       # el proveedor externo puede reconocer el reintento
    assert [x.estado for x in e.ec().devoluciones] == [EstadoDevolucion.EFECTUADA]   # una sola devolución (C-11)


def test_con_el_comprobante_de_administracion_no_se_llama_al_colaborador(ejecutor_y_devolucion):          # CA-098
    # Arrange
    e, d, ejecutor = ejecutor_y_devolucion
    # Act
    r = e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, d.fecha_limite - timedelta(hours=1),
                                                  comprobante='TRANSF-ADMIN-0001')
    # Assert
    assert r.exito
    ejecutor.ejecutar.assert_not_called()
    assert e.ec().devoluciones[0].comprobante == 'TRANSF-ADMIN-0001'


# ================================================================================ notificaciones (INotificadorParticipantes)
@pytest.fixture
def notificador_del_cierre(contratado):
    doble = create_autospec(INotificadorParticipantes, instance=True)
    contratado.s.cierre.notificador = doble
    return doble


def test_cancelacion_rechazada_en_T_avisa_una_sola_vez_al_cliente(contratado, notificador_del_cierre):    # CA-088
    # Arrange
    e = contratado
    # Act
    r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', FECHA_EVENTO)
    # Assert
    assert not r.exito
    notificador_del_cierre.notificar.assert_called_once_with(['Cliente'], 'Cancelación no procedente', 'El evento ya inició (CA-088).')
    assert e.evento().estado == EstadoEvento.EN_ORGANIZACION


def test_cancelacion_procedente_no_la_notifica_el_servicio_sino_la_reaccion(contratado, notificador_del_cierre):
    # Arrange
    e = contratado
    # Act
    r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', FECHA_EVENTO - timedelta(days=1))
    # Assert: el servicio no avisa directamente (evita avisos duplicados); el aviso sale de la reacción a EventoCancelado
    assert r.exito
    notificador_del_cierre.notificar.assert_not_called()
    assert e.avisos('Evento cancelado') == []                     # todavía no se despacha el Outbox
    e.d.despachar()
    assert len(e.avisos('Evento cancelado')) == 1
