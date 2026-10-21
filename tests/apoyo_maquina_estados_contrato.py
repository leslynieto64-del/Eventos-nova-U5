"""Apoyo de la Etapa E3B: captura el comportamiento observable del agregado Contrato.

`capturar_comportamiento_contrato()` parte de un Contrato en cada estado posible, con o sin política comunicada,
con o sin seguimiento del anticipo y (si está confirmado) con un anexo previo, y le aplica cada método público de
Contrato con sus combinaciones relevantes de parámetros. Registra el valor devuelto o el mensaje de ErrorDominio,
el estado final, la fecha de firma, los seguimientos, los anexos, la política y los Domain Events.

La referencia `referencias/comportamiento_contrato_v8_e3a.json` se generó con esta función sobre el código de
v8 + E1 + E2 + E3A, antes de introducir la State Machine en Contrato.
"""
import itertools
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from domain.contrato import Contrato, EvidenciaAnticipo, AnexoContrato                        # noqa: E402
from domain.valores import (CondicionesContractuales, PoliticaNoReembolso, Importe, EstadoContrato,  # noqa: E402
                            ErrorDominio, TipoSolicitud)

RUTA_REFERENCIA_CONTRATO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencias',
                                        'comportamiento_contrato_v8_e3a.json')
FIRMA = datetime(2026, 10, 1, 10, 0)
CONTACTO = datetime(2026, 10, 7, 10, 0)            # primer seguimiento del anticipo (después de 3 días hábiles)
LIMITE = CONTACTO + timedelta(hours=24)            # 24 horas naturales desde el contacto (CA-020, CA-021)
NUEVA_FIRMA = datetime(2026, 10, 2, 12, 0)
AHORA = datetime(2026, 10, 9, 9, 0)
B = (False, True)


def contrato_en(estado: EstadoContrato, comunicada: bool = True, con_seguimiento: bool = False) -> Contrato:
    """Contrato en un estado dado, con los atributos que ese estado implica en el código actual."""
    c = Contrato('CT-1', 'EV-1', 'PR-1', 'PR-1-v1', CondicionesContractuales(('Banquete',), Importe(D(10000)), 'Condiciones'),
                 PoliticaNoReembolso(True, FIRMA if comunicada else None))
    if estado != EstadoContrato.EN_PREPARACION:
        c.fecha_firma = FIRMA
    if con_seguimiento:
        c.seguimientos_anticipo.append((CONTACTO, 'Contacto con el Cliente'))
    if estado == EstadoContrato.CONTRATACION_CONFIRMADA:
        c.anexos.append(AnexoContrato('AX-0', TipoSolicitud.CAMBIO, 'SC-0', 'Anexo previo', AHORA))
    c.estado = estado
    return c


def variantes():
    """(nombre, estado, política comunicada, con seguimiento)."""
    return [(f'{e.name}|politica={com}|seguimiento={seg}', e, com, seg)
            for e, com, seg in itertools.product(EstadoContrato, B, B)]


def _confirmar_dos_veces(c):
    primera = c.confirmar_contratacion(EvidenciaAnticipo(True, True, True), AHORA)
    eventos_primera = [e.nombre for e in c.extraer_eventos()]
    segunda = c.confirmar_contratacion(EvidenciaAnticipo(True, True, True), AHORA)
    return {'primera': primera, 'eventos_primera': eventos_primera, 'segunda': segunda}


def acciones():
    """(nombre, llamada) para cada método público de Contrato con sus combinaciones de parámetros."""
    lista = [('firmar', lambda c: c.firmar(NUEVA_FIRMA))]
    for reg, ver, imp in itertools.product(B, B, B):
        lista.append((f'confirmar_contratacion(registrado={reg}, verificado={ver}, importe_correcto={imp})',
                      lambda c, e=EvidenciaAnticipo(reg, ver, imp): c.confirmar_contratacion(e, AHORA)))
    lista.append(('confirmar_contratacion dos veces', _confirmar_dos_veces))
    for nombre_ahora, ahora in (('antes_del_limite', LIMITE - timedelta(hours=1)), ('en_el_limite', LIMITE),
                                ('despues_del_limite', LIMITE + timedelta(hours=1))):
        for pagado in B:
            lista.append((f'cerrar_sin_confirmar(ahora={nombre_ahora}, anticipo_efectuado_en_plazo={pagado})',
                          lambda c, a=ahora, p=pagado: c.cerrar_sin_confirmar(a, p)))
    for vencido in B:
        lista.append((f'registrar_seguimiento_anticipo(plazo_vencido={vencido})',
                      lambda c, v=vencido: c.registrar_seguimiento_anticipo(AHORA, 'Nuevo contacto', v)))
    for origen in ('SC-9', 'SC-0'):
        lista.append((f'registrar_anexo(origen={origen})',
                      lambda c, o=origen: c.registrar_anexo('AX-9', TipoSolicitud.SERVICIO_ADICIONAL, o, 'Anexo', AHORA)))
    lista.append(('registrar_comunicacion_politica', lambda c: c.registrar_comunicacion_politica(AHORA)))
    return lista


def _serializable(valor):
    if isinstance(valor, AnexoContrato):
        return ['AnexoContrato', valor.anexo_id, valor.tipo_origen.name, valor.origen_id]
    if isinstance(valor, dict):
        return {k: _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_serializable(v) for v in valor]
    return valor


def observar(c: Contrato) -> dict:
    return {
        'estado': c.estado.name,
        'fecha_firma': c.fecha_firma.isoformat() if c.fecha_firma else None,
        'seguimientos': [(f.isoformat(), r) for f, r in c.seguimientos_anticipo],
        'anexos': [(a.anexo_id, a.tipo_origen.name, a.origen_id) for a in c.anexos],
        'politica': (c.politica.incluida, c.politica.comunicada_en.isoformat() if c.politica.comunicada_en else None),
        'eventos': [e.nombre for e in c.extraer_eventos()],
    }


def ejecutar(variante, accion):
    _, estado, comunicada, seguimiento = variante
    c = contrato_en(estado, comunicada, seguimiento)
    try:
        resultado = {'devuelve': _serializable(accion(c))}
    except ErrorDominio as e:
        resultado = {'error': str(e)}
    resultado.update(observar(c))
    return resultado


def capturar_comportamiento_contrato():
    return {f'{v[0]} | {nombre}': ejecutar(v, llamada) for v in variantes() for nombre, llamada in acciones()}
