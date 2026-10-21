"""Apoyo de la Etapa E2: captura el comportamiento observable de las reglas que ahora usan Specification.

`capturar_comportamiento()` evalúa los métodos públicos del dominio sobre una cuadrícula exhaustiva de entradas y
devuelve los resultados (estados, listas de pendientes, motivos y Domain Events emitidos). La referencia
`referencias/comportamiento_reglas_v8_e1.json` se generó con esta misma función sobre el código de v8 + E1, antes
de introducir las especificaciones; la prueba de conservación exige que el resultado actual sea idéntico.
"""
import itertools
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from domain.valores import (EstadoContrato, CondicionesContractuales, PoliticaNoReembolso, Importe,  # noqa: E402
                            AnticipacionSolicitud, TarifaCargoTardio, ResultadoViabilidad, ImpactoModificacion,
                            CondicionTemporal, DisponibilidadProveedor)
from domain.contrato import Contrato, EvidenciaAnticipo                                             # noqa: E402
from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor, AlternativaPropuesta  # noqa: E402
from domain.servicios_dominio import EvaluarRegularizacionDeSolicitudes, SituacionSaldo             # noqa: E402

RUTA_REFERENCIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencias',
                               'comportamiento_reglas_v8_e1.json')
B = (False, True)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)
T = datetime(2026, 10, 1, 10, 0)

MOTIVO_CINCO_DIAS = 'Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).'
MOTIVO_INICIADO_ADICIONAL = 'Condición temporal: el evento ya inició.'
MOTIVO_INICIADO_CAMBIO = 'El evento ya inició (CA-039).'
MOTIVO_CANCELADO = 'El evento fue cancelado; la solicitud no puede retomarse (SE-006).'
MOTIVO_SALDO = 'Saldo vencido sin regularizar (CA-066, CA-072).'


def contrato(estado=EstadoContrato.FIRMADO, comunicada=True):
    c = Contrato('CT', 'EV', 'PR', 'PR-v1', CondicionesContractuales(('B',), Importe(D(100)), 'x'),
                 PoliticaNoReembolso(True, T if comunicada else None))
    c.estado = estado
    return c


def cambio(dias_antes):
    return SolicitudCambio('SC', 'EV', 'CT', 'EC', 'd', AnticipacionSolicitud(FECHA_EVENTO - timedelta(days=dias_antes), FECHA_EVENTO),
                           TarifaCargoTardio(Importe(D(1))))


def servicio_adicional(elegibilidad=False):
    sa = SolicitudServicioAdicional('SA', 'EV', 'CT', 'EC', 'DJ', AnticipacionSolicitud(T, FECHA_EVENTO))
    sa.elegibilidad_obtenida = elegibilidad
    return sa


def capturar_comportamiento():
    out = {}
    r = []
    for estado, com, reg, ver, imp in itertools.product(list(EstadoContrato), B, B, B, B):
        c = contrato(estado, com)
        p = c.confirmar_contratacion(EvidenciaAnticipo(reg, ver, imp), T)
        r.append([estado.name, com, reg, ver, imp, p, c.estado.name, [e.nombre for e in c.extraer_eventos()]])
    out['contratacion'] = r
    out['cargo_tardio'] = [[d, cambio(d).aplica_cargo_tardio] for d in range(0, 11)]
    r = []
    for viable, s, c_, k, dias in itertools.product(B, B, B, B, (6, 7)):
        sc = cambio(dias)
        sc.registrar_viabilidad(ResultadoViabilidad(viable, 'm'), ImpactoModificacion(s, c_, k), T)
        r.append([viable, s, c_, k, dias, sc.estado.name, sc.importes_por_pagar,
                  sc.motivo_cierre.descripcion if sc.motivo_cierre else None])
    out['viabilidad_cambio'] = r
    out['temporal_cambio'] = [[i, list(vars(cambio(10).condicion_temporal(i)).values())] for i in B]
    r = []
    for iniciado, eleg, dias in itertools.product(B, B, range(2, 9)):
        ahora = FECHA_EVENTO.replace(hour=9) - timedelta(days=dias)
        ct = servicio_adicional(eleg).condicion_temporal(ahora, iniciado)
        r.append([iniciado, eleg, dias, ct.cumple, ct.motivo])
    out['temporal_adicional'] = r
    r = []
    conds = [CondicionTemporal(True), CondicionTemporal(False, MOTIVO_CINCO_DIAS),
             CondicionTemporal(False, MOTIVO_INICIADO_ADICIONAL), CondicionTemporal(False, MOTIVO_INICIADO_CAMBIO)]
    for saldo, cancelado, ci in itertools.product(B, B, range(len(conds))):
        d = EvaluarRegularizacionDeSolicitudes().evaluar(SituacionSaldo(saldo), cancelado, conds[ci])
        r.append([saldo, cancelado, ci, d.puede_continuar, d.detener_por_saldo, d.motivo])
    out['regularizacion'] = r
    out['tiene_impacto'] = [[s, c_, k, ImpactoModificacion(s, c_, k).tiene_impacto] for s, c_, k in itertools.product(B, B, B)]
    r = []
    for s, c_, k in itertools.product(B, B, B):
        sp = SustitucionProveedor('SP', 'EV', 'SC1', 'PV1', 'CT', 'EC', T)
        sp.proponer_alternativa(AlternativaPropuesta('PV2', DisponibilidadProveedor('PV2', True), ImpactoModificacion(s, c_, k)), None, T)
        r.append([s, c_, k, sp.estado.name])
    out['sustitucion'] = r
    return out
