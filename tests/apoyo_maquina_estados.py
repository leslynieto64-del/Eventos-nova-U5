"""Apoyo de la Etapa E3A: captura el comportamiento observable de las transiciones del agregado Evento.

`capturar_comportamiento_evento()` aplica cada método de Evento que cambia su estado a un Evento en cada estado
posible (y con cada combinación relevante de precondiciones) y registra el resultado: valor devuelto o mensaje de
ErrorDominio, estado final, Domain Events registrados, solicitudes de cancelación, motivo de cancelación, fechas y
servicios. La referencia `referencias/comportamiento_evento_v8_e2.json` se generó con esta función sobre el código de
v8 + E1 + E2, antes de introducir la State Machine.
"""
import itertools
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from domain.evento import Evento, ServicioContratado                                           # noqa: E402
from domain.valores import (DatosEvento, EstadoEvento, ErrorDominio, CondicionesServicio,        # noqa: E402
                            MotivoCancelacionEvento, OrigenCancelacion)

RUTA_REFERENCIA_EVENTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencias',
                                      'comportamiento_evento_v8_e2.json')
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)
AHORA = datetime(2026, 11, 1, 10, 0)
INICIO = datetime(2026, 11, 20, 18, 5)
SERVICIOS = [ServicioContratado('CT-S1', 'Banquete', None, CondicionesServicio('Condiciones acordadas'))]

# Variantes del estado de partida: (nombre, estado, origen de la cancelación previa si está Cancelado)
VARIANTES = [(e.name, e, None) for e in EstadoEvento if e != EstadoEvento.CANCELADO] + [
    ('CANCELADO_SOLICITUD_CLIENTE', EstadoEvento.CANCELADO, OrigenCancelacion.SOLICITUD_CLIENTE),
    ('CANCELADO_FALTA_REGULARIZACION', EstadoEvento.CANCELADO, OrigenCancelacion.FALTA_REGULARIZACION),
]


def evento_en(estado: EstadoEvento, origen_cancelacion=None) -> Evento:
    """Evento en un estado dado, con los atributos que ese estado implica en el código actual."""
    ev = Evento('EV-1', 'CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete'])
    if estado != EstadoEvento.EN_GESTION:
        ev.estado = EstadoEvento.EN_ORGANIZACION
        for s in SERVICIOS:
            ev.servicios[s.servicio_contratado_id] = ServicioContratado(s.servicio_contratado_id, s.servicio, None, s.condiciones)
    if estado in (EstadoEvento.EN_EJECUCION, EstadoEvento.FINALIZADO):
        ev.fecha_inicio = INICIO
    if estado == EstadoEvento.FINALIZADO:
        ev.fecha_finalizacion = datetime(2026, 11, 21, 2, 0)
    if estado == EstadoEvento.CANCELADO:
        ev.motivo_cancelacion = MotivoCancelacionEvento(origen_cancelacion, 'previo', AHORA, 'Coordinador')
    ev.estado = estado
    return ev


def acciones():
    """(nombre, llamada) para cada método de Evento que realiza una transición, con sus combinaciones de precondiciones."""
    lista = [
        ('confirmar_contratacion', lambda ev: ev.confirmar_contratacion(
            [ServicioContratado('CT-S2', 'Música', None, CondicionesServicio('x'))])),
        ('cerrar_sin_contratacion', lambda ev: ev.cerrar_sin_contratacion()),
        ('iniciar', lambda ev: ev.iniciar(INICIO)),
        ('finalizar', lambda ev: ev.finalizar(datetime(2026, 11, 21, 3, 0))),
    ]
    for confirmada in (False, True):
        lista.append((f'solicitar_cancelacion(confirmada={confirmada})',
                      lambda ev, c=confirmada: ev.solicitar_cancelacion('Motivo del Cliente', AHORA, c)))
    for verificado, motivo in itertools.product((False, True), ('', 'Sin regularizar')):
        lista.append((f'cancelar_por_falta_de_regularizacion(verificado={verificado}, motivo={bool(motivo)})',
                      lambda ev, v=verificado, m=motivo: ev.cancelar_por_falta_de_regularizacion(m, 'Coordinador', AHORA, v)))
    return lista


def observar(ev: Evento) -> dict:
    return {
        'estado': ev.estado.name,
        'eventos': [e.nombre for e in ev.extraer_eventos()],
        'solicitudes_cancelacion': [(s.motivo, s.estado.name) for s in ev.solicitudes_cancelacion],
        'motivo_cancelacion': (ev.motivo_cancelacion.origen.name, ev.motivo_cancelacion.descripcion)
        if ev.motivo_cancelacion else None,
        'fecha_inicio': ev.fecha_inicio.isoformat() if ev.fecha_inicio else None,
        'fecha_finalizacion': ev.fecha_finalizacion.isoformat() if ev.fecha_finalizacion else None,
        'servicios': sorted(ev.servicios),
    }


def ejecutar(variante, accion):
    nombre, estado, origen = variante
    ev = evento_en(estado, origen)
    try:
        resultado = {'devuelve': accion(ev)}
    except ErrorDominio as e:
        resultado = {'error': str(e)}
    resultado.update(observar(ev))
    return resultado


def capturar_comportamiento_evento():
    return {f'{v[0]} | {nombre}': ejecutar(v, llamada) for v in VARIANTES for nombre, llamada in acciones()}
