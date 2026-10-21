"""Apoyo de la Etapa E3E: captura el comportamiento observable de SolicitudServicioAdicional.

`capturar_comportamiento_servicio_adicional()` parte de una SolicitudServicioAdicional en cada uno de sus 15 estados
(con los datos que cada estado tiene en el flujo: disponibilidad, elegibilidad, decisiones, anexo, obligación de pago,
motivo de cierre y estado anterior a la detención) y le aplica:
- cada método propio con sus combinaciones relevantes de parámetros (proveedor con o sin costo y condiciones, sin
  proveedor; 10 o 4 días naturales antes del evento; decisiones aprobadas o rechazadas; confirmación con pago, inicio y
  cancelación del evento), y
- los métodos heredados de _SolicitudBase (regularización N2 con sus 5 decisiones, cierre por cancelación y anexo),
  para demostrar que E3E no los cambia.
Registra el valor devuelto o el mensaje de ErrorDominio, todos los atributos, `pendiente`, `puede_registrar_anexo`,
la condición temporal y los Domain Events con sus atributos.

También guarda la huella (SHA-256 del texto, con saltos de línea normalizados) de las clases `_SolicitudBase`,
`SolicitudCambio` y `SustitucionProveedor`, que E3E no debe modificar.

La referencia `referencias/comportamiento_servicio_adicional_v8_n2.json` se generó con esta función sobre el código del
commit 5e046c6 (v8 + E1 + E2 + E3A–E3D + N2), antes de introducir la State Machine en SolicitudServicioAdicional.
"""
import ast
import hashlib
import itertools
import json
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from apoyo_regularizacion_solicitudes import DECISIONES, _v                                    # noqa: E402
from domain.solicitudes import SolicitudServicioAdicional                                       # noqa: E402
from domain.valores import (ErrorDominio, Importe, Decision, DisponibilidadProveedor,           # noqa: E402
                            CondicionesServicio, AnticipacionSolicitud, MotivoCierreSolicitud,
                            CausaCierreSolicitud, EstadoSolicitudServicioAdicional as ESA)
import dataclasses                                                                              # noqa: E402

RUTA_SOLICITUDES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', 'solicitudes.py')
RUTA_REFERENCIA_SERVICIO_ADICIONAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencias',
                                                  'comportamiento_servicio_adicional_v8_n2.json')
CLASES_NO_MODIFICADAS = ('_SolicitudBase', 'SolicitudCambio', 'SustitucionProveedor')

T = datetime(2026, 11, 1, 10, 0)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)
A10 = FECHA_EVENTO - timedelta(days=10)          # dentro de la ventana de 5 días naturales
A4 = FECHA_EVENTO - timedelta(days=4)            # fuera de la ventana
COND = CondicionesServicio('DJ 4 horas')
CON_COSTO = DisponibilidadProveedor('PV-9', True, Importe(D(500)), COND)
SIN_COSTO = DisponibilidadProveedor('PV-9', True, None, None)
SIN_PROVEEDOR = DisponibilidadProveedor('', False)
B = (False, True)


def _cierre(causa):
    return MotivoCierreSolicitud(causa, causa.value, T)


def variantes():
    """(nombre, estado, atributos) con los datos que cada estado tiene en el flujo real."""
    disp = dict(disponibilidad=CON_COSTO, elegibilidad_obtenida=True)
    cliente = dict(disp, decision_cliente=Decision('Cliente', True, T))
    autorizada = dict(cliente, autorizacion_administracion=Decision('Administración', True, T))
    return [
        ('REGISTRADA', ESA.REGISTRADA, {}),
        ('DETENIDA_SALDO_VENCIDO', ESA.DETENIDA_SALDO_VENCIDO, dict(_estado_antes_de_detener=ESA.REGISTRADA)),
        ('EN_BUSQUEDA_PROVEEDOR', ESA.EN_BUSQUEDA_PROVEEDOR, {}),
        ('PENDIENTE_APROBACION_CLIENTE', ESA.PENDIENTE_APROBACION_CLIENTE, disp),
        ('PENDIENTE_AUTORIZACION', ESA.PENDIENTE_AUTORIZACION, cliente),
        ('AUTORIZADA|sin_anexo', ESA.AUTORIZADA, autorizada),
        ('AUTORIZADA|con_anexo', ESA.AUTORIZADA, dict(autorizada, anexo_id='AX-1')),
        ('PENDIENTE_PAGO', ESA.PENDIENTE_PAGO, dict(autorizada, anexo_id='AX-1', obligacion_pago_id='OB-1')),
        ('CONFIRMADA', ESA.CONFIRMADA, dict(autorizada, anexo_id='AX-1', obligacion_pago_id='OB-1')),
        ('NO_PROCEDENTE', ESA.NO_PROCEDENTE, dict(motivo_cierre=_cierre(CausaCierreSolicitud.PLAZO_INSUFICIENTE))),
        ('NO_SE_REALIZARA', ESA.NO_SE_REALIZARA, dict(motivo_cierre=_cierre(CausaCierreSolicitud.CLIENTE_NO_ESPERA))),
        ('NO_APROBADA', ESA.NO_APROBADA, dict(disp, decision_cliente=Decision('Cliente', False, T, 'No'),
                                              motivo_cierre=_cierre(CausaCierreSolicitud.RECHAZO_CLIENTE))),
        ('NO_AUTORIZADA', ESA.NO_AUTORIZADA, dict(cliente, autorizacion_administracion=Decision('Administración', False, T, 'No'),
                                                  motivo_cierre=_cierre(CausaCierreSolicitud.NO_AUTORIZADA))),
        ('CERRADA_FALTA_PAGO', ESA.CERRADA_FALTA_PAGO, dict(autorizada, anexo_id='AX-1', obligacion_pago_id='OB-1',
                                                            motivo_cierre=_cierre(CausaCierreSolicitud.FALTA_PAGO))),
        ('CERRADA_INICIO_EVENTO', ESA.CERRADA_INICIO_EVENTO, dict(disp, motivo_cierre=_cierre(CausaCierreSolicitud.INICIO_EVENTO))),
        ('CERRADA_EVENTO_CANCELADO', ESA.CERRADA_EVENTO_CANCELADO, dict(motivo_cierre=_cierre(CausaCierreSolicitud.EVENTO_CANCELADO))),
    ]


def solicitud(estado=ESA.REGISTRADA, **atributos):
    """SolicitudServicioAdicional en un estado dado, sin Domain Events pendientes."""
    s = SolicitudServicioAdicional('SA-1', 'EV-1', 'CT-1', 'EC-1', 'DJ', AnticipacionSolicitud(T, FECHA_EVENTO))
    s.extraer_eventos()
    for k, v in atributos.items():
        setattr(s, k, v)
    s.estado = estado
    return s


def acciones():
    """(nombre, llamada) para cada método propio y heredado con sus combinaciones de parámetros."""
    lista = []
    for nombre, d in (('con_costo', CON_COSTO), ('sin_costo', SIN_COSTO), ('sin_proveedor', SIN_PROVEEDOR)):
        for dia, ahora in (('10d', A10), ('4d', A4)):
            lista.append((f'registrar_disponibilidad({nombre}, {dia})', lambda s, d=d, a=ahora: s.registrar_disponibilidad(d, a)))
    for acepta, dia, ahora in ((True, '10d', A10), (True, '4d', A4), (False, '10d', A10)):
        lista.append((f'registrar_respuesta_espera({acepta}, {dia})',
                      lambda s, x=acepta, a=ahora: s.registrar_respuesta_espera(x, a)))
    lista += [
        ('registrar_decision_cliente(aprobada)', lambda s: s.registrar_decision_cliente(Decision('Cliente', True, A10))),
        ('registrar_decision_cliente(rechazada)', lambda s: s.registrar_decision_cliente(Decision('Cliente', False, A10, 'No le convence'))),
        ('registrar_autorizacion(aprobada)', lambda s: s.registrar_autorizacion(Decision('Administración', True, A10))),
        ('registrar_autorizacion(rechazada)', lambda s: s.registrar_autorizacion(Decision('Administración', False, A10, 'Sin presupuesto'))),
        ('registrar_solicitud_pago(OB-9)', lambda s: s.registrar_solicitud_pago('OB-9')),
    ]
    for pago, iniciado, cancelado in itertools.product(B, B, B):
        lista.append((f'confirmar(pago={pago}, iniciado={iniciado}, cancelado={cancelado}, 10d)',
                      lambda s, p=pago, i=iniciado, c=cancelado: s.confirmar(p, i, A10, c)))
    lista += [
        ('confirmar(pago=True, iniciado=False, cancelado=False, 4d)', lambda s: s.confirmar(True, False, A4, False)),
        ('cerrar_por_falta_de_pago', lambda s: s.cerrar_por_falta_de_pago(A10)),
        ('cerrar_por_inicio_evento', lambda s: s.cerrar_por_inicio_evento(FECHA_EVENTO)),
        # heredados de _SolicitudBase (fuera de la máquina)
        ('cerrar_por_cancelacion_evento', lambda s: s.cerrar_por_cancelacion_evento(A10)),
        ('asociar_anexo(AX-1)', lambda s: s.asociar_anexo('AX-1')),
        ('asociar_anexo(AX-2)', lambda s: s.asociar_anexo('AX-2')),
    ]
    for decision, d in DECISIONES.items():
        lista.append((f'aplicar_decision_regularizacion({decision})',
                      lambda s, d=d: s.aplicar_decision_regularizacion(d, A10, ESA.NO_PROCEDENTE)))
    return lista


def _condicion(s, ahora, iniciado):
    c = s.condicion_temporal(ahora, iniciado)
    return [c.cumple, c.motivo]


def observar(s) -> dict:
    datos = {k: _v(v) for k, v in sorted(vars(s).items()) if k != '_eventos'}
    datos['pendiente'] = s.pendiente
    datos['puede_registrar_anexo'] = s.puede_registrar_anexo()
    datos['condicion_temporal'] = [_condicion(s, A10, False), _condicion(s, A4, False), _condicion(s, A10, True)]
    datos['eventos'] = [[e.nombre] + [[k, _v(v)] for k, v in sorted(dataclasses.asdict(e).items()) if k != 'evento_id']
                        for e in s.extraer_eventos()]
    return datos


def ejecutar(estado, atributos, accion):
    s = solicitud(estado, **atributos)
    try:
        resultado = {'devuelve': _v(accion(s))}
    except ErrorDominio as e:
        resultado = {'error': str(e)}
    resultado.update(observar(s))
    return resultado


def huellas_de_clases(ruta=RUTA_SOLICITUDES) -> dict:
    """SHA-256 del texto de cada clase que E3E no debe modificar (saltos de línea normalizados)."""
    with open(ruta, encoding='utf-8') as f:
        texto = f.read().replace('\r\n', '\n')
    arbol = ast.parse(texto)
    out = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.ClassDef) and nodo.name in CLASES_NO_MODIFICADAS:
            segmento = ast.get_source_segment(texto, nodo)
            out[nodo.name] = hashlib.sha256(segmento.encode('utf-8')).hexdigest()
    return out


def capturar_comportamiento_servicio_adicional():
    datos = {}
    for nombre, estado, atributos in variantes():
        datos[f'{nombre} | (inicial)'] = observar(solicitud(estado, **atributos))
        for accion, llamada in acciones():
            datos[f'{nombre} | {accion}'] = ejecutar(estado, atributos, llamada)
    return datos


def escribir_referencia(ruta=RUTA_REFERENCIA_SERVICIO_ADICIONAL):
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'huellas': huellas_de_clases(), 'comportamiento': capturar_comportamiento_servicio_adicional()},
                  f, ensure_ascii=False, indent=1)
        f.write('\n')
