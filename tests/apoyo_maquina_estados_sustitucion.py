"""Apoyo de la Etapa E3C: captura el comportamiento observable de SustitucionProveedor y de los cierres de las otras
dos solicitudes.

`capturar_comportamiento_sustitucion()` parte de una SustitucionProveedor en cada uno de sus 7 estados (con las
variantes de alternativa, costo, límite de 3 días hábiles y anexo que cada estado admite en el código) y le aplica
cada método con sus combinaciones relevantes de parámetros. Registra el valor devuelto o el mensaje de ErrorDominio,
el estado, las alternativas, el costo, el anexo, el motivo de cierre, las propiedades derivadas y los Domain Events.
También captura `cerrar_por_inicio_evento` y `cerrar_por_cancelacion_evento` de SolicitudCambio y
SolicitudServicioAdicional en todos sus estados, para demostrar que E3C no los modifica.

La referencia `referencias/comportamiento_sustitucion_v8_e3b.json` se generó con esta función sobre el código de
v8 + E1 + E2 + E3A + E3B, antes de introducir la State Machine en SustitucionProveedor.
"""
import itertools
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from domain.solicitudes import (SustitucionProveedor, AlternativaPropuesta, SolicitudCambio,          # noqa: E402
                                SolicitudServicioAdicional)
from domain.valores import (ErrorDominio, Decision, DisponibilidadProveedor, ImpactoModificacion, Importe,  # noqa: E402
                            CondicionesServicio, MotivoCierreSolicitud, CausaCierreSolicitud, AnticipacionSolicitud,
                            TarifaCargoTardio, EstadoSustitucionProveedor as ESP, EstadoSolicitudCambio as ESC,
                            EstadoSolicitudServicioAdicional as ESA)

RUTA_REFERENCIA_SUSTITUCION = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencias',
                                           'comportamiento_sustitucion_v8_e3b.json')
T = datetime(2026, 11, 1, 10, 0)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)                 # límite ordinario: 3 días hábiles antes (17/11 18:00)
ANTES_DEL_LIMITE = datetime(2026, 11, 10, 12, 0)
DESPUES_DEL_LIMITE = datetime(2026, 11, 18, 12, 0)
CON_IMPACTO = ImpactoModificacion(False, True, True)
SIN_IMPACTO = ImpactoModificacion(False, False, False)
B = (False, True)


def alternativa(impacto, proveedor='PV-2', decision=None, autorizacion=None):
    return AlternativaPropuesta(proveedor, DisponibilidadProveedor(proveedor, True, Importe(D(800)), CondicionesServicio('Otro')),
                                impacto, decision, autorizacion)


def aprobada(actor='Cliente', fecha=T):
    return Decision(actor, True, fecha)


def rechazada(actor='Cliente', fecha=T):
    return Decision(actor, False, fecha, 'No acepta')


def sustitucion(estado=ESP.EN_BUSQUEDA_ALTERNATIVA, alternativas=(), costo=None, despues_del_limite=False,
                anexo=None, motivo=None):
    """SustitucionProveedor en un estado dado, sin Domain Events pendientes."""
    s = SustitucionProveedor('SP-1', 'EV-1', 'CT-1-S1', 'PV-1', 'CT-1', 'EC-1', T)
    s.extraer_eventos()
    s.alternativas = list(alternativas)
    s.costo_adicional = costo
    s.aprobada_despues_del_limite = despues_del_limite
    s.anexo_id = anexo
    s.motivo_cierre = motivo
    s.estado = estado
    return s


def variantes():
    """(nombre, argumentos de sustitucion()) para los 7 estados y sus variantes de datos."""
    con = alternativa(CON_IMPACTO)
    con_aprobada = alternativa(CON_IMPACTO, decision=aprobada())
    con_autorizada = alternativa(CON_IMPACTO, decision=aprobada(), autorizacion=aprobada('Administración'))
    sin = alternativa(SIN_IMPACTO)
    costo = Importe(D(500))
    cierre = lambda causa: MotivoCierreSolicitud(causa, causa.value, T)                           # noqa: E731
    return [
        ('EN_BUSQUEDA_ALTERNATIVA|sin_alternativas', dict()),
        ('EN_BUSQUEDA_ALTERNATIVA|alternativa_rechazada', dict(alternativas=[alternativa(CON_IMPACTO, decision=rechazada())])),
        ('PENDIENTE_APROBACION_CLIENTE', dict(estado=ESP.PENDIENTE_APROBACION_CLIENTE, alternativas=[con], costo=costo)),
        ('PENDIENTE_AUTORIZACION', dict(estado=ESP.PENDIENTE_AUTORIZACION, alternativas=[con_aprobada], costo=costo)),
        ('PENDIENTE_FORMALIZACION|sin_impacto|sin_anexo', dict(estado=ESP.PENDIENTE_FORMALIZACION, alternativas=[sin])),
        ('PENDIENTE_FORMALIZACION|sin_impacto|con_anexo', dict(estado=ESP.PENDIENTE_FORMALIZACION, alternativas=[sin], anexo='AX-1')),
        ('PENDIENTE_FORMALIZACION|con_costo|antes_del_limite|con_anexo',
         dict(estado=ESP.PENDIENTE_FORMALIZACION, alternativas=[con_autorizada], costo=costo, anexo='AX-1')),
        ('PENDIENTE_FORMALIZACION|con_costo|despues_del_limite|con_anexo',
         dict(estado=ESP.PENDIENTE_FORMALIZACION, alternativas=[con_autorizada], costo=costo, despues_del_limite=True, anexo='AX-1')),
        ('CONFIRMADA', dict(estado=ESP.CONFIRMADA, alternativas=[sin], anexo='AX-1')),
        ('CERRADA_INICIO_EVENTO', dict(estado=ESP.CERRADA_INICIO_EVENTO, alternativas=[con],
                                       motivo=cierre(CausaCierreSolicitud.INICIO_EVENTO))),
        ('CERRADA_EVENTO_CANCELADO', dict(estado=ESP.CERRADA_EVENTO_CANCELADO,
                                          motivo=cierre(CausaCierreSolicitud.EVENTO_CANCELADO))),
    ]


def acciones():
    """(nombre, llamada) para cada método de SustitucionProveedor con sus combinaciones de parámetros."""
    lista = [
        ('proponer_alternativa(con_impacto, costo)', lambda s: s.proponer_alternativa(alternativa(CON_IMPACTO, 'PV-3'), Importe(D(800)), T)),
        ('proponer_alternativa(sin_impacto, sin_costo)', lambda s: s.proponer_alternativa(alternativa(SIN_IMPACTO, 'PV-3'), None, T)),
        ('registrar_decision_cliente(aprobada)', lambda s: s.registrar_decision_cliente(aprobada(fecha=ANTES_DEL_LIMITE))),
        ('registrar_decision_cliente(rechazada)', lambda s: s.registrar_decision_cliente(rechazada(fecha=ANTES_DEL_LIMITE))),
        ('registrar_autorizacion(aprobada, antes_del_limite)',
         lambda s: s.registrar_autorizacion(aprobada('Administración', ANTES_DEL_LIMITE), FECHA_EVENTO)),
        ('registrar_autorizacion(aprobada, despues_del_limite)',
         lambda s: s.registrar_autorizacion(aprobada('Administración', DESPUES_DEL_LIMITE), FECHA_EVENTO)),
        ('registrar_autorizacion(rechazada)',
         lambda s: s.registrar_autorizacion(rechazada('Administración', ANTES_DEL_LIMITE), FECHA_EVENTO)),
    ]
    for pago, iniciado, cancelado in itertools.product(B, B, B):
        lista.append((f'confirmar(pago_previo={pago}, iniciado={iniciado}, cancelado={cancelado})',
                      lambda s, p=pago, i=iniciado, c=cancelado: s.confirmar(p, i, T, c)))
    lista += [
        ('cerrar_por_inicio_evento', lambda s: s.cerrar_por_inicio_evento(T)),
        ('cerrar_por_cancelacion_evento', lambda s: s.cerrar_por_cancelacion_evento(T)),
        ('asociar_anexo(AX-1)', lambda s: s.asociar_anexo('AX-1')),
        ('asociar_anexo(AX-2)', lambda s: s.asociar_anexo('AX-2')),
    ]
    return lista


def _decision(d):
    return None if d is None else [d.actor, d.aprobada, d.fecha.isoformat(), d.motivo]


def observar(s) -> dict:
    return {
        'estado': s.estado.name,
        'alternativas': [[a.proveedor_id, [a.impacto.afecta_servicios, a.impacto.afecta_costos, a.impacto.afecta_condiciones],
                          _decision(a.decision_cliente), _decision(a.autorizacion_administracion)] for a in s.alternativas],
        'costo_adicional': str(s.costo_adicional.cantidad) if s.costo_adicional else None,
        'aprobada_despues_del_limite': s.aprobada_despues_del_limite,
        'anexo_id': s.anexo_id,
        'motivo_cierre': [s.motivo_cierre.causa.name, s.motivo_cierre.descripcion, s.motivo_cierre.fecha.isoformat()]
        if s.motivo_cierre else None,
        'pendiente': s.pendiente,
        'puede_registrar_anexo': s.puede_registrar_anexo(),
        'importe_adicional_aprobado': s.importe_adicional_aprobado,
        'eventos': [[e.nombre, getattr(e, 'proveedor_id', None)] for e in s.extraer_eventos()],
    }


def ejecutar(argumentos, accion):
    s = sustitucion(**argumentos)
    try:
        resultado = {'devuelve': accion(s)}
    except ErrorDominio as e:
        resultado = {'error': str(e)}
    resultado.update(observar(s))
    return resultado


# ---------------------------------------------------------------- cierres de las otras dos solicitudes
def cambio_en(estado):
    s = SolicitudCambio('SC-1', 'EV-1', 'CT-1', 'EC-1', 'Cambio',
                        AnticipacionSolicitud(T, FECHA_EVENTO), TarifaCargoTardio(Importe(D(150))))
    s.extraer_eventos(); s.estado = estado
    return s


def adicional_en(estado):
    s = SolicitudServicioAdicional('SA-1', 'EV-1', 'CT-1', 'EC-1', 'DJ', AnticipacionSolicitud(T, FECHA_EVENTO))
    s.extraer_eventos(); s.estado = estado
    return s


def cierres_de_otras_solicitudes():
    out = {}
    for tipo, fabrica, enum in (('SolicitudCambio', cambio_en, ESC), ('SolicitudServicioAdicional', adicional_en, ESA)):
        for estado in enum:
            for nombre, llamada in (('cerrar_por_inicio_evento', lambda s: s.cerrar_por_inicio_evento(T)),
                                    ('cerrar_por_cancelacion_evento', lambda s: s.cerrar_por_cancelacion_evento(T))):
                s = fabrica(estado)
                devuelve = llamada(s)
                out[f'{tipo}|{estado.name} | {nombre}'] = {
                    'devuelve': devuelve, 'estado': s.estado.name, 'pendiente': s.pendiente,
                    'motivo_cierre': [s.motivo_cierre.causa.name, s.motivo_cierre.descripcion] if s.motivo_cierre else None,
                    'eventos': [e.nombre for e in s.extraer_eventos()]}
    return out


def capturar_comportamiento_sustitucion():
    datos = {f'SustitucionProveedor|{nombre} | {accion}': ejecutar(argumentos, llamada)
             for nombre, argumentos in variantes() for accion, llamada in acciones()}
    datos.update(cierres_de_otras_solicitudes())
    return datos
