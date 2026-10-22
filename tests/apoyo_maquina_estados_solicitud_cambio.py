"""Apoyo previo a la Etapa E3F: captura el comportamiento observable de SolicitudCambio antes de su State Machine.

`capturar_comportamiento_solicitud_cambio()` registra cuatro bloques:

- `constructor`: la creación de la solicitud con y sin modificación propuesta (misma fecha con otra hora, otra fecha
  del evento, condiciones por servicio contratado) y con 10 o 3 días naturales de anticipación (con y sin cargo por
  cambio tardío).
- `comportamiento`: una SolicitudCambio en cada estado alcanzable, con los datos que ese estado tiene en el flujo real
  (viabilidad, impacto, importes por pagar, decisiones, anexo, obligación de pago, motivo de cierre y estado anterior a
  la detención), a la que se le aplica:
  * cada método propio con sus combinaciones relevantes de parámetros: viabilidad (no viable; viable sin impacto o con
    impacto en servicios, costos o condiciones), decisiones del Cliente y de Administración (aprobada o rechazada),
    solicitud de pago, confirmación (pago verificado, evento iniciado y evento cancelado: las 8 combinaciones), cierre
    por falta de pago y cierre por inicio del evento; y
  * los métodos heredados de _SolicitudBase: regularización N2 con sus 5 decisiones, cierre por cancelación del evento
    y asociación del anexo (mismo anexo y otro anexo).
  Para cada caso guarda el valor devuelto o el mensaje de ErrorDominio, todos los atributos, `pendiente`,
  `puede_registrar_anexo()`, `aplica_cargo_tardio`, `condicion_temporal()` (evento no iniciado e iniciado),
  `configuracion_propuesta()` sobre una configuración vigente fija (sin costo y con costo del proveedor) y los Domain
  Events emitidos con sus atributos (sin `evento_id`, que es aleatorio).
- `historico_en_evaluacion`: los mismos casos partiendo de `EstadoSolicitudCambio.EN_EVALUACION`. AR-05 lo resolvió
  como valor histórico de la enumeración, no alcanzable: ningún método lo asigna. Se captura por separado solo para
  documentar lo que hace hoy el código si una solicitud estuviera en ese valor (por ejemplo, la guarda de
  `registrar_viabilidad` lo acepta). No es un estado del ciclo de vida.
- `huellas`: SHA-256 del texto de las clases `SolicitudCambio` (la que E3F modificará), `_SolicitudBase` y
  `SustitucionProveedor`, con saltos de línea normalizados.

La captura es determinista: fechas fijas, identificadores fijos y sin `evento_id`. Ejecutada dos veces sobre el mismo
código produce el mismo JSON byte a byte.

Uso (desde la raíz del proyecto, con el código anterior a E3F):
    python tests/apoyo_maquina_estados_solicitud_cambio.py                    # resumen, sin escribir nada
    python tests/apoyo_maquina_estados_solicitud_cambio.py --write-reference  # crea la referencia (no sobrescribe)
    python tests/apoyo_maquina_estados_solicitud_cambio.py --write-reference --force   # sobrescribe a propósito
    python tests/apoyo_maquina_estados_solicitud_cambio.py --check            # compara la referencia con el código:
        # 0 = sin diferencias; 1 = diferencias (comparación semántica completa, en ambas direcciones);
        # 2 = referencia inexistente o ilegible; --write-reference sobre una referencia existente sin --force también da 2

La referencia se escribe en `tests/referencias/comportamiento_solicitud_cambio_pre_e3f.json`.
"""
import argparse
import ast
import dataclasses
import hashlib
import itertools
import json
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from apoyo_regularizacion_solicitudes import DECISIONES, _v as _v_base                             # noqa: E402
from domain.solicitudes import SolicitudCambio                                                    # noqa: E402
from domain.servicios_dominio import ConfiguracionComparable                                     # noqa: E402
from domain.valores import (ErrorDominio, Importe, Decision, AnticipacionSolicitud, TarifaCargoTardio,  # noqa: E402
                            DatosEvento, CondicionesServicio, ImpactoModificacion, ResultadoViabilidad,
                            MotivoCierreSolicitud, CausaCierreSolicitud, EstadoSolicitudCambio as ESC)

DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_SOLICITUDES = os.path.join(DIR, '..', 'src', 'domain', 'solicitudes.py')
RUTA_REFERENCIA_SOLICITUD_CAMBIO = os.path.join(DIR, 'referencias', 'comportamiento_solicitud_cambio_pre_e3f.json')
CLASES_CON_HUELLA = ('SolicitudCambio', '_SolicitudBase', 'SustitucionProveedor')

T = datetime(2026, 11, 1, 10, 0)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)
A10 = FECHA_EVENTO - timedelta(days=10)       # 10 días naturales: sin cargo por cambio tardío (BN-003)
A3 = FECHA_EVENTO - timedelta(days=3)         # 3 días naturales: con cargo por cambio tardío (CA-062)
TARIFA = TarifaCargoTardio(Importe(D(150)))
DATOS_VIGENTES = DatosEvento('Boda', FECHA_EVENTO, 'Salón Norte', 100)
DATOS_MISMO_DIA = DatosEvento('Boda', FECHA_EVENTO.replace(hour=20), 'Salón Norte', 120)
DATOS_OTRA_FECHA = DatosEvento('Boda', FECHA_EVENTO + timedelta(days=1), 'Salón Norte', 100)
CONDICIONES = {'SC-S1': CondicionesServicio('Banquete para 120')}
VIGENTE = ConfiguracionComparable(DATOS_VIGENTES, frozenset({('SC-S1', CondicionesServicio('Banquete para 100'))}),
                                  Importe(D(0)))
SIN_IMPACTO = ImpactoModificacion(False, False, False)
IMPACTOS = (('sin_impacto', SIN_IMPACTO), ('servicios', ImpactoModificacion(True, False, False)),
            ('costos', ImpactoModificacion(False, True, False)), ('condiciones', ImpactoModificacion(False, False, True)))
B = (False, True)


def _v(x):
    """Igual que el de N2, con conjuntos ordenados para que el JSON sea determinista."""
    if isinstance(x, (set, frozenset)):
        return sorted((_v(e) for e in x), key=lambda e: json.dumps(e, sort_keys=True, ensure_ascii=False))
    if isinstance(x, (list, tuple)):
        return [_v(e) for e in x]
    if isinstance(x, dict):
        return {str(_v(k)): _v(v) for k, v in x.items()}
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: _v(getattr(x, f.name)) for f in dataclasses.fields(x)}
    return _v_base(x)


def _cierre(causa):
    return MotivoCierreSolicitud(causa, causa.value, T)


def solicitud(estado=ESC.REGISTRADA, fecha_solicitud=A10, datos=None, condiciones=None, **atributos):
    """SolicitudCambio en un estado dado, sin Domain Events pendientes."""
    s = SolicitudCambio('SC-1', 'EV-1', 'CT-1', 'EC-1', 'Cambio de hora y banquete',
                        AnticipacionSolicitud(fecha_solicitud, FECHA_EVENTO), TARIFA, datos, condiciones)
    s.extraer_eventos()
    for k, v in atributos.items():
        setattr(s, k, v)
    s.estado = estado
    return s


def variantes():
    """(nombre, estado, argumentos de solicitud()) con los datos que cada estado alcanzable tiene en el flujo real.
    No incluye EN_EVALUACION (ver variantes_historicas)."""
    viable_b = dict(viabilidad=ResultadoViabilidad(True), impacto=ImpactoModificacion(False, True, True),
                    importes_por_pagar=True)                                       # ruta B: afecta costos o condiciones
    viable_c = dict(viabilidad=ResultadoViabilidad(True), impacto=SIN_IMPACTO, importes_por_pagar=False)   # ruta C
    viable_c_tardio = dict(viable_c, importes_por_pagar=True, fecha_solicitud=A3)  # ruta C con cargo tardío
    cliente = dict(viable_b, decision_cliente=Decision('Cliente', True, T))
    autorizada = dict(cliente, autorizacion_administracion=Decision('Administración', True, T))
    return [
        ('REGISTRADA|10d', ESC.REGISTRADA, {}),
        ('REGISTRADA|3d', ESC.REGISTRADA, dict(fecha_solicitud=A3)),
        ('REGISTRADA|con_modificacion', ESC.REGISTRADA, dict(datos=DATOS_MISMO_DIA, condiciones=CONDICIONES)),
        ('DETENIDA_SALDO_VENCIDO|antes=REGISTRADA', ESC.DETENIDA_SALDO_VENCIDO,
         dict(_estado_antes_de_detener=ESC.REGISTRADA)),
        ('PENDIENTE_APROBACION_CLIENTE', ESC.PENDIENTE_APROBACION_CLIENTE, viable_b),
        ('PENDIENTE_AUTORIZACION', ESC.PENDIENTE_AUTORIZACION, cliente),
        ('PENDIENTE_FORMALIZACION|ruta_B|sin_anexo', ESC.PENDIENTE_FORMALIZACION, autorizada),
        ('PENDIENTE_FORMALIZACION|ruta_B|con_anexo', ESC.PENDIENTE_FORMALIZACION, dict(autorizada, anexo_id='AX-1')),
        ('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|sin_anexo', ESC.PENDIENTE_FORMALIZACION, viable_c),
        ('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo', ESC.PENDIENTE_FORMALIZACION,
         dict(viable_c, anexo_id='AX-1')),
        ('PENDIENTE_FORMALIZACION|ruta_C|cargo_tardio|con_anexo', ESC.PENDIENTE_FORMALIZACION,
         dict(viable_c_tardio, anexo_id='AX-1')),
        ('PENDIENTE_PAGO', ESC.PENDIENTE_PAGO, dict(autorizada, anexo_id='AX-1', obligacion_pago_id='OB-1')),
        ('CONFIRMADA', ESC.CONFIRMADA, dict(autorizada, anexo_id='AX-1', obligacion_pago_id='OB-1')),
        ('NO_PROCEDENTE|no_viable', ESC.NO_PROCEDENTE,
         dict(viabilidad=ResultadoViabilidad(False, 'Proveedor sin disponibilidad'), impacto=SIN_IMPACTO,
              motivo_cierre=_cierre(CausaCierreSolicitud.NO_VIABLE))),
        ('NO_PROCEDENTE|regularizacion', ESC.NO_PROCEDENTE,
         dict(motivo_cierre=_cierre(CausaCierreSolicitud.EVENTO_CANCELADO))),
        ('RECHAZADA_CLIENTE', ESC.RECHAZADA_CLIENTE,
         dict(viable_b, decision_cliente=Decision('Cliente', False, T, 'No'),
              motivo_cierre=_cierre(CausaCierreSolicitud.RECHAZO_CLIENTE))),
        ('NO_AUTORIZADA', ESC.NO_AUTORIZADA,
         dict(cliente, autorizacion_administracion=Decision('Administración', False, T, 'No'),
              motivo_cierre=_cierre(CausaCierreSolicitud.NO_AUTORIZADA))),
        ('CERRADA_FALTA_PAGO', ESC.CERRADA_FALTA_PAGO,
         dict(autorizada, anexo_id='AX-1', obligacion_pago_id='OB-1', motivo_cierre=_cierre(CausaCierreSolicitud.FALTA_PAGO))),
        ('CERRADA_INICIO_EVENTO', ESC.CERRADA_INICIO_EVENTO, dict(viable_b, motivo_cierre=_cierre(CausaCierreSolicitud.INICIO_EVENTO))),
        ('CERRADA_EVENTO_CANCELADO', ESC.CERRADA_EVENTO_CANCELADO, dict(motivo_cierre=_cierre(CausaCierreSolicitud.EVENTO_CANCELADO))),
    ]


def variantes_historicas():
    """EN_EVALUACION: valor histórico, no alcanzable (AR-05). Solo se documenta su comportamiento actual."""
    return [('EN_EVALUACION|10d', ESC.EN_EVALUACION, {}), ('EN_EVALUACION|3d', ESC.EN_EVALUACION, dict(fecha_solicitud=A3))]


def acciones():
    """(nombre, llamada) para cada método propio y heredado de SolicitudCambio con sus combinaciones de parámetros."""
    lista = [('registrar_viabilidad(no_viable)',
              lambda s: s.registrar_viabilidad(ResultadoViabilidad(False, 'Sin disponibilidad'), ImpactoModificacion(False, True, True), A10))]
    for nombre, impacto in IMPACTOS:
        lista.append((f'registrar_viabilidad(viable, {nombre})',
                      lambda s, i=impacto: s.registrar_viabilidad(ResultadoViabilidad(True), i, A10)))
    lista += [
        ('registrar_decision_cliente(aprobada)', lambda s: s.registrar_decision_cliente(Decision('Cliente', True, A10))),
        ('registrar_decision_cliente(rechazada)', lambda s: s.registrar_decision_cliente(Decision('Cliente', False, A10, 'No le convence'))),
        ('registrar_autorizacion(aprobada)', lambda s: s.registrar_autorizacion(Decision('Administración', True, A10))),
        ('registrar_autorizacion(rechazada)', lambda s: s.registrar_autorizacion(Decision('Administración', False, A10, 'Sin presupuesto'))),
        ('registrar_solicitud_pago(OB-9)', lambda s: s.registrar_solicitud_pago('OB-9')),
    ]
    for pago, iniciado, cancelado in itertools.product(B, B, B):
        lista.append((f'confirmar(pago={pago}, iniciado={iniciado}, cancelado={cancelado})',
                      lambda s, p=pago, i=iniciado, c=cancelado: s.confirmar(p, i, A10, c)))
    lista += [
        ('cerrar_por_falta_de_pago', lambda s: s.cerrar_por_falta_de_pago(A10)),
        ('cerrar_por_inicio_evento', lambda s: s.cerrar_por_inicio_evento(FECHA_EVENTO)),
        # heredados de _SolicitudBase
        ('cerrar_por_cancelacion_evento', lambda s: s.cerrar_por_cancelacion_evento(A10)),
        ('asociar_anexo(AX-1)', lambda s: s.asociar_anexo('AX-1')),
        ('asociar_anexo(AX-2)', lambda s: s.asociar_anexo('AX-2')),
    ]
    for decision, d in DECISIONES.items():
        lista.append((f'aplicar_decision_regularizacion({decision})',
                      lambda s, d=d: s.aplicar_decision_regularizacion(d, A10, ESC.NO_PROCEDENTE)))
    return lista


def _condicion(s, iniciado):
    c = s.condicion_temporal(iniciado)
    return [c.cumple, c.motivo]


def observar(s) -> dict:
    datos = {k: _v(v) for k, v in sorted(vars(s).items()) if k != '_eventos'}
    datos['pendiente'] = s.pendiente
    datos['puede_registrar_anexo'] = s.puede_registrar_anexo()
    datos['aplica_cargo_tardio'] = s.aplica_cargo_tardio
    datos['condicion_temporal'] = [_condicion(s, False), _condicion(s, True)]
    datos['configuracion_propuesta'] = [_v(s.configuracion_propuesta(VIGENTE, None)),
                                        _v(s.configuracion_propuesta(VIGENTE, Importe(D(300))))]
    datos['eventos'] = [[e.nombre] + [[k, _v(v)] for k, v in sorted(dataclasses.asdict(e).items()) if k != 'evento_id']
                        for e in s.extraer_eventos()]
    return datos


def ejecutar(estado, argumentos, accion):
    s = solicitud(estado, **argumentos)
    try:
        resultado = {'devuelve': _v(accion(s))}
    except ErrorDominio as e:
        resultado = {'error': str(e)}
    resultado.update(observar(s))
    return resultado


def capturar_constructor() -> dict:
    casos = {
        'sin_modificacion|10d': dict(),
        'sin_modificacion|3d': dict(fecha=A3),
        'misma_fecha_otra_hora|condiciones': dict(datos=DATOS_MISMO_DIA, condiciones=CONDICIONES),
        'otra_fecha_del_evento': dict(datos=DATOS_OTRA_FECHA),
        'solo_condiciones': dict(condiciones=CONDICIONES),
    }
    out = {}
    for nombre, a in casos.items():
        try:
            s = SolicitudCambio('SC-1', 'EV-1', 'CT-1', 'EC-1', 'Cambio de hora y banquete',
                                AnticipacionSolicitud(a.get('fecha', A10), FECHA_EVENTO), TARIFA,
                                a.get('datos'), a.get('condiciones'))
            out[nombre] = observar(s)                   # incluye CambioSolicitado
        except ErrorDominio as e:
            out[nombre] = {'error': str(e)}
    return out


def _capturar(lista_variantes) -> dict:
    datos = {}
    for nombre, estado, argumentos in lista_variantes:
        datos[f'{nombre} | (inicial)'] = observar(solicitud(estado, **argumentos))
        for accion, llamada in acciones():
            datos[f'{nombre} | {accion}'] = ejecutar(estado, argumentos, llamada)
    return datos


def huellas_de_clases(ruta=RUTA_SOLICITUDES) -> dict:
    """SHA-256 del texto de cada clase (saltos de línea normalizados), como en E3E."""
    with open(ruta, encoding='utf-8') as f:
        texto = f.read().replace('\r\n', '\n')
    arbol = ast.parse(texto)
    out = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.ClassDef) and nodo.name in CLASES_CON_HUELLA:
            out[nodo.name] = hashlib.sha256(ast.get_source_segment(texto, nodo).encode('utf-8')).hexdigest()
    return {n: out[n] for n in CLASES_CON_HUELLA}


def capturar_comportamiento_solicitud_cambio() -> dict:
    return {
        'huellas': huellas_de_clases(),
        'constructor': capturar_constructor(),
        'comportamiento': _capturar(variantes()),
        'historico_en_evaluacion': _capturar(variantes_historicas()),
    }


def serializar(datos) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=1) + '\n'


def escribir_referencia(ruta=RUTA_REFERENCIA_SOLICITUD_CAMBIO, forzar=False) -> str:
    """Escribe la referencia. No sobrescribe un archivo existente salvo con forzar=True."""
    if os.path.exists(ruta) and not forzar:
        raise FileExistsError(f'La referencia ya existe: {ruta}. Usa --force para sobrescribirla a propósito.')
    texto = serializar(capturar_comportamiento_solicitud_cambio())
    with open(ruta, 'w', encoding='utf-8', newline='\n') as f:
        f.write(texto)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def _resumen(datos) -> str:
    return (f"huellas: {datos['huellas']}\n"
            f"constructor: {len(datos['constructor'])} casos\n"
            f"comportamiento: {len(variantes())} variantes x (1 inicial + {len(acciones())} operaciones) = "
            f"{len(datos['comportamiento'])} casos\n"
            f"historico_en_evaluacion: {len(datos['historico_en_evaluacion'])} casos\n"
            f"SHA-256 del JSON: {hashlib.sha256(serializar(datos).encode('utf-8')).hexdigest()}")


MAX_DIFERENCIAS_MOSTRADAS = 50


def _tipo(x) -> str:
    return {dict: 'objeto', list: 'lista', str: 'texto', bool: 'booleano', int: 'entero', float: 'decimal',
            type(None): 'null'}.get(type(x), type(x).__name__)


def _ruta(ruta, clave) -> str:
    return f'{ruta}[{clave}]' if isinstance(clave, int) else (f'{ruta} › {clave!r}' if ruta else repr(clave))


def diferencias(referencia, actual, ruta='') -> list:
    """Comparación semántica y recursiva de dos documentos JSON ya interpretados, en ambas direcciones: claves y casos
    faltantes o adicionales en cualquier nivel, elementos faltantes o adicionales en listas, cambios de tipo (incluido
    booleano frente a número) y valores distintos. No depende del formato del archivo."""
    raiz = ruta or '(documento)'
    if type(referencia) is not type(actual):
        return [f'{raiz}: tipo distinto: referencia {_tipo(referencia)} = {json.dumps(referencia, ensure_ascii=False)[:120]}; '
                f'actual {_tipo(actual)} = {json.dumps(actual, ensure_ascii=False)[:120]}']
    if isinstance(referencia, dict):
        out = []
        for k in referencia:
            if k not in actual:
                out.append(f'{_ruta(ruta, k)}: falta en la captura actual')
        for k in actual:
            if k not in referencia:
                out.append(f'{_ruta(ruta, k)}: adicional en la captura actual (no está en la referencia)')
        for k in referencia:
            if k in actual:
                out += diferencias(referencia[k], actual[k], _ruta(ruta, k))
        return out
    if isinstance(referencia, list):
        out = []
        for i in range(min(len(referencia), len(actual))):
            out += diferencias(referencia[i], actual[i], _ruta(ruta, i))
        if len(referencia) > len(actual):
            out.append(f'{raiz}: la captura actual tiene {len(referencia) - len(actual)} elementos menos '
                       f'({len(actual)} en lugar de {len(referencia)})')
        elif len(actual) > len(referencia):
            out.append(f'{raiz}: la captura actual tiene {len(actual) - len(referencia)} elementos adicionales '
                       f'({len(actual)} en lugar de {len(referencia)})')
        return out
    if referencia != actual:
        return [f'{raiz}: valor distinto: referencia {json.dumps(referencia, ensure_ascii=False)[:120]}; '
                f'actual {json.dumps(actual, ensure_ascii=False)[:120]}']
    return []


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Línea base de SolicitudCambio antes de E3F.')
    p.add_argument('--write-reference', action='store_true', help='escribe la referencia JSON')
    p.add_argument('--force', action='store_true', help='con --write-reference, sobrescribe una referencia existente')
    p.add_argument('--check', action='store_true', help='compara la referencia existente con la captura actual')
    p.add_argument('--ruta', default=RUTA_REFERENCIA_SOLICITUD_CAMBIO, help='ruta de la referencia')
    a = p.parse_args(argv)
    if a.write_reference and a.check:
        p.error('usa --write-reference o --check, no ambos')
    if a.write_reference:
        try:
            sha = escribir_referencia(a.ruta, a.force)
        except FileExistsError as e:
            print(e, file=sys.stderr)
            return 2
        print(f'Referencia escrita: {a.ruta}\nSHA-256: {sha}')
        return 0
    actual = capturar_comportamiento_solicitud_cambio()
    if a.check:
        if not os.path.isfile(a.ruta):
            print(f'No existe la referencia: {a.ruta}', file=sys.stderr)
            return 2
        try:
            with open(a.ruta, encoding='utf-8') as f:
                referencia = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f'No se puede interpretar la referencia {a.ruta}: {e}', file=sys.stderr)
            return 2
        distintos = diferencias(referencia, json.loads(serializar(actual)))
        if not distintos:
            print('Sin diferencias.')
            return 0
        print(f'{len(distintos)} diferencias (referencia -> captura actual):')
        print('\n'.join(distintos[:MAX_DIFERENCIAS_MOSTRADAS]))
        if len(distintos) > MAX_DIFERENCIAS_MOSTRADAS:
            print(f'... y {len(distintos) - MAX_DIFERENCIAS_MOSTRADAS} más.')
        return 1
    print(_resumen(actual))
    return 0


if __name__ == '__main__':
    sys.exit(main())
