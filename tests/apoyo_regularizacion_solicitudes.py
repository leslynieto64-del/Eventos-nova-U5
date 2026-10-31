"""Apoyo de la corrección N2: captura el comportamiento de `_SolicitudBase.aplicar_decision_regularizacion`.

`capturar_comportamiento_regularizacion()` parte de una SolicitudCambio, una SolicitudServicioAdicional y una
SustitucionProveedor (que hereda el método aunque ningún servicio se lo aplica) en cada uno de sus estados, con las
variantes que el código admite (motivo de cierre en los estados finales; estado anterior a la detención en Detenida), y
les aplica cada tipo de DecisionRegularizacion que produce EvaluarRegularizacionDeSolicitudes: continuar, detener por
saldo vencido y no procede (por condición temporal, por evento cancelado y por el motivo «evento ya inició» de
SolicitudCambio, hallazgo N3). Registra el valor devuelto o el mensaje de ErrorDominio, todos los atributos de la
solicitud y los Domain Events.

La referencia `referencias/comportamiento_regularizacion_v8_e3d.json` se generó con esta función sobre el código del
commit bdc98c3 (v8 + E1 + E2 + E3A + E3B + E3C + E3D), antes de corregir N2.
"""
import copy
import dataclasses
import json
import os
import sys
from datetime import datetime
from decimal import Decimal as D
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor     # noqa: E402
from domain.servicios_dominio import DecisionRegularizacion                                       # noqa: E402
from domain.valores import (ErrorDominio, Importe, AnticipacionSolicitud, TarifaCargoTardio,     # noqa: E402
                            MotivoCierreSolicitud, CausaCierreSolicitud,
                            EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA,
                            EstadoSustitucionProveedor as ESP)

RUTA_REFERENCIA_REGULARIZACION = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencias',
                                              'comportamiento_regularizacion_v8_e3d.json')
T = datetime(2026, 11, 1, 10, 0)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)
AHORA = datetime(2026, 11, 12, 9, 0)

# Decisiones tal como las produce EvaluarRegularizacionDeSolicitudes (motivos reales de las Specifications).
DECISIONES = {
    'continuar': DecisionRegularizacion(True, False),
    'detener_por_saldo': DecisionRegularizacion(False, True, "Saldo vencido sin regularizar (CA-066, CA-072)."),
    'no_procede_condicion_temporal': DecisionRegularizacion(
        False, False, "Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083)."),
    'no_procede_evento_cancelado': DecisionRegularizacion(
        False, False, "El evento fue cancelado; la solicitud no puede retomarse (SE-006)."),
    'no_procede_evento_iniciado_cambio': DecisionRegularizacion(False, False, "El evento ya inició (CA-039)."),
}

# Estado de cierre que pasan los servicios (servicios.py); SustitucionProveedor no tiene uno porque ningún servicio
# le aplica la regularización: se usa None, el valor que recibiría una llamada directa sin ese argumento significativo.
NO_PROCEDE = {'SolicitudCambio': ESC.NO_PROCEDENTE, 'SolicitudServicioAdicional': ESA.NO_PROCEDENTE,
              'SustitucionProveedor': None}


def cambio():
    return SolicitudCambio('SC-1', 'EV-1', 'CT-1', 'EC-1', 'Cambio', AnticipacionSolicitud(T, FECHA_EVENTO),
                           TarifaCargoTardio(Importe(D(150))))


def adicional():
    return SolicitudServicioAdicional('SA-1', 'EV-1', 'CT-1', 'EC-1', 'DJ', AnticipacionSolicitud(T, FECHA_EVENTO))


def sustitucion():
    return SustitucionProveedor('SP-1', 'EV-1', 'CT-1-S1', 'PV-1', 'CT-1', 'EC-1', T)


FABRICAS = {'SolicitudCambio': (cambio, ESC), 'SolicitudServicioAdicional': (adicional, ESA),
            'SustitucionProveedor': (sustitucion, ESP)}


def variantes():
    """(tipo, nombre, estado, estado_antes_de_detener, con_motivo_de_cierre) para cada estado de las tres solicitudes."""
    out = []
    for tipo, (fabrica, enum) in FABRICAS.items():
        s = fabrica()
        for estado in enum:
            final = estado in type(s).FINALES and estado.name != 'CONFIRMADA'
            if estado is getattr(type(s), 'DETENIDA', None):
                out.append((tipo, f'{estado.name}|antes=REGISTRADA', estado, enum.REGISTRADA, False))
                out.append((tipo, f'{estado.name}|antes=PENDIENTE_APROBACION_CLIENTE', estado,
                            enum.PENDIENTE_APROBACION_CLIENTE, False))
            else:
                out.append((tipo, estado.name, estado, None, final))
    return out


def solicitud(tipo, estado, antes=None, con_motivo=False):
    """Solicitud en el estado dado, sin Domain Events pendientes."""
    s = FABRICAS[tipo][0]()
    s.extraer_eventos()
    s.estado = estado
    s._estado_antes_de_detener = antes
    if con_motivo:
        s.motivo_cierre = MotivoCierreSolicitud(CausaCierreSolicitud.NO_VIABLE, 'Cierre previo', T)
    return s


def _v(x):
    if isinstance(x, Enum):
        return x.name
    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, D):
        return str(x)
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: _v(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, (list, tuple)):
        return [_v(e) for e in x]
    if isinstance(x, dict):
        return {str(_v(k)): _v(v) for k, v in x.items()}
    return x


def observar(s) -> dict:
    """Todos los atributos de la solicitud (incluidos los protegidos) y los Domain Events pendientes."""
    atributos = {k: _v(v) for k, v in sorted(vars(s).items()) if k != '_eventos'}
    atributos['pendiente'] = s.pendiente
    atributos['eventos'] = [[e.nombre] + [[k, _v(v)] for k, v in sorted(dataclasses.asdict(e).items()) if k != 'evento_id']
                            for e in s.extraer_eventos()]
    return atributos


def ejecutar(tipo, estado, antes, con_motivo, decision):
    s = solicitud(tipo, estado, antes, con_motivo)
    try:
        resultado = {'devuelve': s.aplicar_decision_regularizacion(DECISIONES[decision], AHORA, NO_PROCEDE[tipo])}
    except ErrorDominio as e:
        resultado = {'error': str(e)}
    resultado.update(observar(s))
    return resultado


def adaptar_referencia_e3g(referencia: dict) -> dict:
    """E3G: SolicitudCambio gana el atributo `costo_proveedor` (valor inicial None). La referencia histórica no se
    modifica: al cargarla, cada observación de una SolicitudCambio recibe ese atributo con su valor por defecto; las de
    SolicitudServicioAdicional y SustitucionProveedor no cambian (mismo patrón que E3F.1)."""
    adaptada = copy.deepcopy(referencia)
    for clave, caso in adaptada.items():
        if clave.startswith('SolicitudCambio|') and 'anexo_id' in caso:
            caso.setdefault('costo_proveedor', None)
    return adaptada


def capturar_comportamiento_regularizacion():
    datos = {}
    for tipo, nombre, estado, antes, con_motivo in variantes():
        datos[f'{tipo}|{nombre} | (inicial)'] = observar(solicitud(tipo, estado, antes, con_motivo))
        for decision in DECISIONES:
            datos[f'{tipo}|{nombre} | {decision}'] = ejecutar(tipo, estado, antes, con_motivo, decision)
    return datos


def escribir_referencia(ruta=RUTA_REFERENCIA_REGULARIZACION):
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(capturar_comportamiento_regularizacion(), f, ensure_ascii=False, indent=1)
        f.write('\n')
