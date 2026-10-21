"""Apoyo de la Etapa E3D: captura el comportamiento observable del agregado EstadoCuenta.

`capturar_comportamiento_estado_cuenta()` construye, solo con métodos públicos, un EstadoCuenta en cada una de las
variantes de `variantes()` (obligaciones de cada concepto en sus estados, pagos completos, parciales, tardíos,
registrados sin verificar o con importe incorrecto, ventana de regularización sin activar, vigente, vencida o resuelta,
cierres sin realizar con y sin Evento cancelado y devoluciones Pendiente o Efectuada) y le aplica cada operación de
`acciones()` con sus parámetros relevantes. Registra el valor devuelto o el mensaje de ErrorDominio, todas las
obligaciones, pagos y devoluciones, el resultado de la regularización, los seguimientos, las consultas de lectura y
los Domain Events con sus atributos.

`registrar_devolucion_efectuada` se aplica solo a las variantes que tienen la devolución `DV-1`: con un identificador
inexistente el código lanza StopIteration (AR-08, pendiente), y la referencia no debe fijar ese comportamiento.

La referencia `referencias/comportamiento_estado_cuenta_v8_e3c.json` se generó con esta función sobre el código de
v8 + E1 + E2 + E3A + E3B + E3C (commit 8c80470), antes de introducir las State Machines en EstadoCuenta.
"""
import dataclasses
import json
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from domain.estado_cuenta import EstadoCuenta, ObligacionPago, Pago, Devolucion          # noqa: E402
from domain.valores import ErrorDominio, Importe, ConceptoPago as CP                     # noqa: E402

RUTA_REFERENCIA_ESTADO_CUENTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'referencias',
                                             'comportamiento_estado_cuenta_v8_e3c.json')
COSTO_TOTAL = Importe(D(10000))                 # anticipo 3000 (30 %), saldo 7000 tras el anticipo verificado
FIRMA = datetime(2026, 11, 2, 10, 0)            # plazo del anticipo: 3 días hábiles → 05/11 10:00
ANTICIPO_A_TIEMPO = datetime(2026, 11, 3, 12, 0)
ANTICIPO_TARDIO = datetime(2026, 11, 6, 12, 0)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)    # límite del saldo: 3 días hábiles antes → 17/11 18:00
LIMITE_SALDO = datetime(2026, 11, 17, 18, 0)
ANTES_LIMITE = datetime(2026, 11, 16, 12, 0)
DESPUES_LIMITE = datetime(2026, 11, 18, 9, 0)
COMUNICADO = datetime(2026, 11, 18, 10, 0)      # inicio de la ventana de regularización (24 h naturales)
FIN_VENTANA = COMUNICADO + timedelta(hours=24)
DENTRO_VENTANA = datetime(2026, 11, 18, 20, 0)
DESPUES_VENTANA = datetime(2026, 11, 19, 12, 0)
REVISION_TEMPRANA = datetime(2026, 11, 18, 22, 0)
REVISION = datetime(2026, 11, 19, 11, 0)
CAMBIO_COMUNICADO = datetime(2026, 11, 10, 10, 0)   # ventana de 24 h del cambio → 11/11 10:00
CAMBIO_A_TIEMPO = datetime(2026, 11, 10, 15, 0)
CAMBIO_TARDIO = datetime(2026, 11, 12, 9, 0)
CIERRE = datetime(2026, 11, 14, 9, 0)
EFECTUADA = datetime(2026, 11, 16, 9, 0)
CONSULTA = datetime(2026, 11, 19, 12, 0)


def M(cantidad) -> Importe:
    return Importe(D(cantidad))


class _Ids:
    def __init__(self, prefijo):
        self.prefijo, self.n = prefijo, 0

    def __call__(self):
        self.n += 1
        return f"{self.prefijo}-{self.n}"


class Constructor:
    """Construye un EstadoCuenta con métodos públicos y numera pagos y devoluciones en orden (PG-1, DV-1, ...)."""

    def __init__(self):
        self.ec = EstadoCuenta('EC-1', 'CT-1', 'EV-1')
        self.pg = _Ids('PG')
        self.dv = _Ids('DV')

    def pagar(self, ob_id, cantidad, fecha, verificar=True):
        self.ec.registrar_y_verificar_pago(self.pg(), ob_id, M(cantidad), fecha, 'CMP', verificar)
        return self

    def anticipo(self, pagar=True):
        self.ec.registrar_obligacion_anticipo('OB-A', COSTO_TOTAL, FIRMA)
        if pagar:
            self.pagar('OB-A', 3000, ANTICIPO_A_TIEMPO)
        return self

    def saldo(self):
        self.ec.registrar_obligacion_saldo_original('OB-S', COSTO_TOTAL, FECHA_EVENTO)
        return self

    def sustitucion(self, despues_del_limite=False):
        self.ec.registrar_importe_adicional_sustitucion('OB-SP', M(500), 'SP-1', despues_del_limite, FECHA_EVENTO)
        return self

    def cambio(self):
        self.ec.comunicar_solicitud_pago('OB-C', CP.CAMBIO, M(300), 'SC-1', CAMBIO_COMUNICADO)
        return self

    def vencer(self):
        self.ec.registrar_vencimiento_saldo(DESPUES_LIMITE)
        return self

    def protocolo(self):
        self.ec.activar_protocolo_cobro('OB-M', M(700), COMUNICADO, 'Recordatorio amistoso')
        return self

    def cerrar(self, origen_id, evento_cancelado):
        self.ec.aplicar_cierre_sin_realizar(origen_id, CIERRE, evento_cancelado, self.dv)
        return self


def variantes():
    """(nombre, función que devuelve un Constructor) para cada situación del agregado."""
    C = Constructor
    return [
        ('anticipo_pendiente', lambda: C().anticipo(pagar=False)),
        ('anticipo_importe_incorrecto', lambda: C().anticipo(pagar=False).pagar('OB-A', 1000, ANTICIPO_A_TIEMPO)),
        ('anticipo_registrado_sin_verificar', lambda: C().anticipo(pagar=False).pagar('OB-A', 3000, ANTICIPO_A_TIEMPO, False)),
        ('anticipo_tardio_verificado', lambda: C().anticipo(pagar=False).pagar('OB-A', 3000, ANTICIPO_TARDIO)),
        ('saldo_pendiente', lambda: C().anticipo().saldo()),
        ('saldo_pago_parcial', lambda: C().anticipo().saldo().pagar('OB-S', 2000, ANTES_LIMITE)),
        ('saldo_pago_a_tiempo_sin_verificar', lambda: C().anticipo().saldo().pagar('OB-S', 7000, ANTES_LIMITE, False)),
        ('saldo_liquidado', lambda: C().anticipo().saldo().pagar('OB-S', 7000, ANTES_LIMITE)),
        ('saldo_y_sustitucion_pendientes', lambda: C().anticipo().saldo().sustitucion()),
        ('saldo_pendiente_y_sustitucion_liquidada', lambda: C().anticipo().saldo().sustitucion().pagar('OB-SP', 500, ANTES_LIMITE)),
        ('sustitucion_sin_plazo', lambda: C().anticipo().saldo().sustitucion(despues_del_limite=True)),
        ('saldo_vencido', lambda: C().anticipo().saldo().vencer()),
        ('saldo_y_sustitucion_vencidos', lambda: C().anticipo().saldo().sustitucion().vencer()),
        ('ventana_vigente', lambda: C().anticipo().saldo().vencer().protocolo()),
        ('ventana_pagos_completos_a_tiempo', lambda: C().anticipo().saldo().vencer().protocolo()
         .pagar('OB-S', 7000, DENTRO_VENTANA).pagar('OB-M', 700, DENTRO_VENTANA)),
        ('ventana_pago_a_tiempo_sin_verificar', lambda: C().anticipo().saldo().vencer().protocolo()
         .pagar('OB-S', 7000, DENTRO_VENTANA, False).pagar('OB-M', 700, DENTRO_VENTANA)),
        ('ventana_pagos_tardios', lambda: C().anticipo().saldo().vencer().protocolo()
         .pagar('OB-S', 7000, DESPUES_VENTANA).pagar('OB-M', 700, DESPUES_VENTANA)),
        ('ventana_sustitucion_vencida', lambda: C().anticipo().saldo().sustitucion().vencer().protocolo()),
        ('regularizado', lambda: _resuelto(C().anticipo().saldo().vencer().protocolo()
                                            .pagar('OB-S', 7000, DENTRO_VENTANA).pagar('OB-M', 700, DENTRO_VENTANA))),
        ('no_regularizado', lambda: _resuelto(C().anticipo().saldo().vencer().protocolo())),
        ('cambio_pendiente', lambda: C().anticipo().saldo().cambio()),
        ('cambio_pago_parcial', lambda: C().anticipo().saldo().cambio().pagar('OB-C', 100, CAMBIO_A_TIEMPO)),
        ('cambio_liquidado', lambda: C().anticipo().saldo().cambio().pagar('OB-C', 300, CAMBIO_A_TIEMPO)),
        ('cambio_pago_tardio', lambda: C().anticipo().saldo().cambio().pagar('OB-C', 300, CAMBIO_TARDIO)),
        ('cambio_sin_efecto_evento_cancelado', lambda: C().anticipo().saldo().cambio().cerrar('SC-1', True)),
        ('cambio_sin_efecto_sin_pagos', lambda: C().anticipo().saldo().cambio().cerrar('SC-1', False)),
        ('cambio_cerrado_con_devolucion_pendiente', lambda: C().anticipo().saldo().cambio()
         .pagar('OB-C', 100, CAMBIO_A_TIEMPO).cerrar('SC-1', False)),
        ('cambio_liquidado_cerrado_con_devolucion_pendiente', lambda: C().anticipo().saldo().cambio()
         .pagar('OB-C', 300, CAMBIO_A_TIEMPO).cerrar('SC-1', False)),
        ('cambio_cerrado_con_devolucion_efectuada', lambda: _efectuada(C().anticipo().saldo().cambio()
                                                                       .pagar('OB-C', 300, CAMBIO_A_TIEMPO).cerrar('SC-1', False))),
        ('cambio_liquidado_cerrado_evento_cancelado', lambda: C().anticipo().saldo().cambio()
         .pagar('OB-C', 300, CAMBIO_A_TIEMPO).cerrar('SC-1', True)),
    ]


def _resuelto(c):
    c.ec.resolver_regularizacion(REVISION)
    return c


def _efectuada(c):
    c.ec.registrar_devolucion_efectuada('DV-1', EFECTUADA, 'CMP-DV')
    return c


def acciones():
    """(nombre, llamada(constructor), requiere_DV-1) para cada operación pública de EstadoCuenta."""
    def pago(ob_id, cantidad, fecha, verificar=True):
        return lambda c: c.ec.registrar_y_verificar_pago(c.pg(), ob_id, M(cantidad), fecha, 'CMP-N', verificar)

    lista = [
        ('pagar(OB-A, 3000, a_tiempo)', pago('OB-A', 3000, ANTICIPO_A_TIEMPO)),
        ('pagar(OB-A, 3000, tardio)', pago('OB-A', 3000, ANTICIPO_TARDIO)),
        ('pagar(OB-A, 1000, importe_incorrecto)', pago('OB-A', 1000, ANTICIPO_A_TIEMPO)),
        ('pagar(OB-A, 3000, sin_verificar)', pago('OB-A', 3000, ANTICIPO_A_TIEMPO, False)),
        ('pagar(OB-S, 7000, antes_limite)', pago('OB-S', 7000, ANTES_LIMITE)),
        ('pagar(OB-S, 2000, parcial)', pago('OB-S', 2000, ANTES_LIMITE)),
        ('pagar(OB-S, 7000, sin_verificar)', pago('OB-S', 7000, ANTES_LIMITE, False)),
        ('pagar(OB-S, 7000, despues_limite)', pago('OB-S', 7000, DESPUES_LIMITE)),
        ('pagar(OB-S, 7000, dentro_ventana)', pago('OB-S', 7000, DENTRO_VENTANA)),
        ('pagar(OB-S, 7000, despues_ventana)', pago('OB-S', 7000, DESPUES_VENTANA)),
        ('pagar(OB-SP, 500, antes_limite)', pago('OB-SP', 500, ANTES_LIMITE)),
        ('pagar(OB-M, 700, dentro_ventana)', pago('OB-M', 700, DENTRO_VENTANA)),
        ('pagar(OB-M, 700, despues_ventana)', pago('OB-M', 700, DESPUES_VENTANA)),
        ('pagar(OB-C, 300, a_tiempo)', pago('OB-C', 300, CAMBIO_A_TIEMPO)),
        ('pagar(OB-C, 300, tardio)', pago('OB-C', 300, CAMBIO_TARDIO)),
        ('pagar(OB-X, inexistente)', pago('OB-X', 100, ANTES_LIMITE)),
    ]
    for pago_id in ('PG-1', 'PG-2', 'PG-3', 'PG-X'):
        lista.append((f'verificar_pago_registrado({pago_id})',
                      lambda c, i=pago_id: c.ec.verificar_pago_registrado(i, REVISION)))
    lista += [
        ('registrar_vencimiento_saldo(antes_limite)', lambda c: c.ec.registrar_vencimiento_saldo(ANTES_LIMITE)),
        ('registrar_vencimiento_saldo(despues_limite)', lambda c: c.ec.registrar_vencimiento_saldo(DESPUES_LIMITE)),
        ('activar_protocolo_cobro', lambda c: c.ec.activar_protocolo_cobro('OB-M2', M(700), COMUNICADO, 'Segundo aviso')),
        ('resolver_regularizacion(ventana_vigente)', lambda c: c.ec.resolver_regularizacion(REVISION_TEMPRANA)),
        ('resolver_regularizacion(fin_exacto)', lambda c: c.ec.resolver_regularizacion(FIN_VENTANA)),
        ('resolver_regularizacion(despues)', lambda c: c.ec.resolver_regularizacion(REVISION)),
        ('comunicar_solicitud_pago(CAMBIO, SC-2)', lambda c: c.ec.comunicar_solicitud_pago('OB-C2', CP.CAMBIO, M(300), 'SC-2', CAMBIO_COMUNICADO)),
        ('comunicar_solicitud_pago(CAMBIO, SC-1)', lambda c: c.ec.comunicar_solicitud_pago('OB-C3', CP.CAMBIO, M(300), 'SC-1', CAMBIO_COMUNICADO)),
        ('comunicar_solicitud_pago(ANTICIPO)', lambda c: c.ec.comunicar_solicitud_pago('OB-C4', CP.ANTICIPO, M(300), 'SC-2', CAMBIO_COMUNICADO)),
        ('registrar_importe_adicional_sustitucion(antes_del_limite)',
         lambda c: c.ec.registrar_importe_adicional_sustitucion('OB-SP2', M(500), 'SP-2', False, FECHA_EVENTO)),
        ('registrar_importe_adicional_sustitucion(despues_del_limite)',
         lambda c: c.ec.registrar_importe_adicional_sustitucion('OB-SP3', M(500), 'SP-3', True, FECHA_EVENTO)),
        ('registrar_obligacion_saldo_original', lambda c: c.ec.registrar_obligacion_saldo_original('OB-S2', COSTO_TOTAL, FECHA_EVENTO)),
        ('registrar_obligacion_anticipo', lambda c: c.ec.registrar_obligacion_anticipo('OB-A2', COSTO_TOTAL, FIRMA)),
    ]
    for origen in ('SC-1', 'SP-1', 'CT-1'):
        for cancelado in (False, True):
            lista.append((f'aplicar_cierre_sin_realizar({origen}, evento_cancelado={cancelado})',
                          lambda c, o=origen, x=cancelado: c.ec.aplicar_cierre_sin_realizar(o, CIERRE, x, c.dv)))
    return [(n, f, False) for n, f in lista] + [
        ('registrar_devolucion_efectuada(DV-1)', lambda c: c.ec.registrar_devolucion_efectuada('DV-1', CONSULTA, 'CMP-DV2'), True),
    ]


# ------------------------------------------------------------------ observación
def _v(x):
    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, Importe):
        return str(x.cantidad)
    if hasattr(x, 'value') and hasattr(x, 'name'):
        return x.name
    return x


def _devuelve(r):
    if isinstance(r, ObligacionPago):
        return ['ObligacionPago', r.obligacion_id]
    if isinstance(r, Pago):
        return ['Pago', r.pago_id]
    if isinstance(r, list):
        return [_devuelve(x) for x in r]
    if isinstance(r, Devolucion):
        return ['Devolucion', r.devolucion_id]
    return r


def observar(ec: EstadoCuenta) -> dict:
    return {
        'obligaciones': {o.obligacion_id: [o.concepto.name, _v(o.importe),
                                           [_v(o.plazo.inicio), _v(o.plazo.vence)] if o.plazo else None,
                                           o.origen_id, o.estado.name] for o in ec.obligaciones.values()},
        'pagos': [[p.pago_id, p.obligacion_id, _v(p.importe), _v(p.fecha), p.comprobante, p.estado.name,
                   _v(p.registrado_en), _v(p.verificado_en)] for p in ec.pagos],
        'devoluciones': [[d.devolucion_id, d.solicitud_id, d.concepto.name, _v(d.importe), d.motivo_devolucion,
                          _v(d.fecha_cierre), d.estado.name, _v(d.fecha_devolucion), d.comprobante] for d in ec.devoluciones],
        'seguimientos_cobro': list(ec.seguimientos_cobro),
        'resultado_regularizacion': ec.resultado_regularizacion,
        'fecha_resultado_regularizacion': _v(ec.fecha_resultado_regularizacion),
        'ventana_resuelta': ec._ventana_resuelta,
        'consultas': {
            'anticipo_verificado': ec.anticipo_verificado(),
            'anticipo_verificado_hasta_plazo': ec.anticipo_verificado(datetime(2026, 11, 5, 10, 0)),
            'anticipo_efectuado_hasta_plazo': ec.anticipo_efectuado_hasta(datetime(2026, 11, 5, 10, 0)),
            'anticipo_recibido': ec.anticipo_recibido(),
            'saldo_vencido_sin_regularizar': ec.saldo_vencido_sin_regularizar,
            'pagos_realizados': _v(ec.pagos_realizados()),
            'saldo_pendiente_contrato': _v(ec.saldo_pendiente_contrato()),
            'no_regularizado_verificado': ec.no_regularizado_verificado,
            'liquidadas': sorted(i for i in ec.obligaciones if ec.obligacion_liquidada(i)),
            'vencidas_sin_pago': sorted(i for i, o in ec.obligaciones.items()
                                        if o.plazo is not None and ec.obligacion_vencida_sin_pago(i, CONSULTA)),
        },
        'eventos': [[e.nombre] + [[k, _v(v)] for k, v in sorted(dataclasses.asdict(e).items()) if k != 'evento_id']
                    for e in ec.extraer_eventos()],
    }


def construir(nombre):
    """Constructor de la variante, sin Domain Events pendientes."""
    c = dict(variantes())[nombre]()
    c.ec.extraer_eventos()
    return c


def ejecutar(nombre, accion):
    c = construir(nombre)
    try:
        resultado = {'devuelve': _devuelve(accion(c))}
    except ErrorDominio as e:
        resultado = {'error': str(e)}
    resultado.update(observar(c.ec))
    return resultado


def capturar_comportamiento_estado_cuenta():
    datos = {}
    for nombre, _ in variantes():
        tiene_devolucion = any(d.devolucion_id == 'DV-1' for d in construir(nombre).ec.devoluciones)
        datos[f'{nombre} | (inicial)'] = observar(construir(nombre).ec)
        for accion, llamada, requiere_devolucion in acciones():
            if requiere_devolucion and not tiene_devolucion:
                continue                                    # AR-08: id inexistente → StopIteration (no se fija)
            datos[f'{nombre} | {accion}'] = ejecutar(nombre, llamada)
    return datos


def escribir_referencia(ruta=RUTA_REFERENCIA_ESTADO_CUENTA):
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(capturar_comportamiento_estado_cuenta(), f, ensure_ascii=False, indent=1)
        f.write('\n')
