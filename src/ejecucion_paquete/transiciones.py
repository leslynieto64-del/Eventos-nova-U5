"""Ejecutor de las 20 transiciones de transiciones_prueba.csv (LEEME, «Secuencia para estudiantes», paso 5).

Cada transición se ejecuta con los servicios de aplicación reales sobre la composición en memoria del proyecto
(`infrastructure.composicion.construir`), en una instancia nueva por transición, de modo que ninguna depende de otra.

1. Preparación (fixture D-07): se registra el Evento del actor y su Propuesta con los recursos y el total de la
   operación. El estado de partida debe ser la correspondencia de COTIZADO: Evento «En gestión» con la Propuesta
   «En revisión del Cliente»; si no lo es, la transición es FALLIDA.
2. Acción: la operación de dominio que `mapeo.ACCIONES` asigna a la acción sugerida.
3. Registro: aceptación o rechazo, mensaje, estado final del Evento y del Contrato y Domain Events emitidos (outbox).
   En los rechazos se compara una fotografía completa de los agregados del evento y la longitud del outbox antes y
   después: debe ser idéntica (sin cambios parciales).

Dos comparaciones independientes:
- veredicto (APROBADO/FALLIDO/NO_EJECUTABLE) contra el oráculo adaptado del dominio (reglas aprobadas del equipo);
- `coincide_con_paquete` (SÍ/NO) contra lo que espera el flujo de referencia del paquete; un NO no es un fallo: remite
  a la diferencia documentada correspondiente.
"""
from __future__ import annotations
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

from paquete_pia import PaquetePIA, leer_paquete

from domain.valores import ErrorDominio, ContenidoPropuesta, DatosEvento, EstadoContrato, EstadoEvento, EstadoPropuesta, Importe
from infrastructure.composicion import construir
from .totales import total_operacion

APROBADO, FALLIDO, NO_EJECUTABLE = "APROBADO", "FALLIDO", "NO_EJECUTABLE"
ACEPTADA, ACEPTADA_SIN_EFECTO, RECHAZADA = "ACEPTADA", "ACEPTADA_SIN_EFECTO", "RECHAZADA"
TRANSICION, EXCEPCION = "TRANSICION", "EXCEPCION"

PORCENTAJE_ANTICIPO = Decimal("0.30")                       # BN-009, CA-017
DIAS_HASTA_EVENTO, HORA_EVENTO, HORA_SOLICITUD = 60, time(18, 0), time(10, 0)   # fixture D-07
INVITADOS_FIXTURE = 100
CONDICIONES_FIXTURE = "Condiciones del paquete 16_Eventos_Nova"

EVENTOS_APROBACION = ("PropuestaAceptada", "ContratoFirmado", "PagoVerificado", "ContratacionConfirmada")
MSG_CA005 = "La propuesta debe incluir servicios, proveedores, costos y condiciones (CA-005)."
MSG_CA084 = "La cancelación solo procede con la contratación confirmada (CA-084)."
MSG_CA094 = "Solo puede finalizarse un evento que se realizó (CA-094)."
MSG_INICIO = "No puede iniciar un evento En gestión."
MSG_YA_CONFIRMADA = "La contratación ya estaba confirmada."


@dataclass(frozen=True)
class OraculoDominio:
    """Resultado que exigen las reglas aprobadas del equipo para una acción sobre una operación COTIZADO."""
    resultado: str
    mensaje: Optional[str]
    estado_evento: EstadoEvento
    estado_contrato: Optional[EstadoContrato]
    eventos: Tuple[str, ...]


ORACULO_DOMINIO: Dict[str, OraculoDominio] = {
    "aprobar": OraculoDominio(ACEPTADA, None, EstadoEvento.EN_ORGANIZACION, EstadoContrato.CONTRATACION_CONFIRMADA,
                              EVENTOS_APROBACION),
    "repetir_aprobacion": OraculoDominio(ACEPTADA_SIN_EFECTO, MSG_YA_CONFIRMADA, EstadoEvento.EN_ORGANIZACION,
                                         EstadoContrato.CONTRATACION_CONFIRMADA, ()),
    "cancelar": OraculoDominio(RECHAZADA, MSG_CA084, EstadoEvento.EN_GESTION, None, ()),
    "completar": OraculoDominio(RECHAZADA, MSG_CA094, EstadoEvento.EN_GESTION, None, ()),
    "saltar_estado": OraculoDominio(RECHAZADA, MSG_INICIO, EstadoEvento.EN_GESTION, None, ()),
}


@dataclass(frozen=True)
class ResultadoTransicion:
    caso_id: str
    operacion_id: str
    accion_sugerida: str
    estado_inicial_paquete: str
    actor_id: str
    actor_activo: bool
    total_mxn: Decimal
    estado_inicial_dominio: str
    operacion_dominio: str
    esperado_paquete: str
    esperado_dominio: str
    resultado_real: str
    mensaje_real: str
    estado_final_evento: str
    estado_final_contrato: str
    anticipo_mxn: str
    eventos_emitidos: str
    sin_cambios_parciales: str
    veredicto: str
    coincide_con_paquete: str
    diferencias: str
    explicacion: str


# ----------------------------------------------------------------------------------------------- utilidades

def _foto(valor, _vistos=None):
    """Representación profunda y comparable de un agregado (atributos, colecciones, enums, fechas e importes)."""
    if isinstance(valor, Enum):
        return valor.value
    if valor is None or isinstance(valor, (str, int, bool, Decimal, date, datetime)):
        return valor
    if isinstance(valor, dict):
        return tuple(sorted((repr(k), _foto(v)) for k, v in valor.items()))
    if isinstance(valor, (list, tuple)):
        return tuple(_foto(v) for v in valor)
    if isinstance(valor, (set, frozenset)):
        return tuple(sorted(repr(_foto(v)) for v in valor))
    if hasattr(valor, "__dict__"):
        return (type(valor).__name__, tuple(sorted((k, _foto(v)) for k, v in vars(valor).items())))
    return repr(valor)


def _fotografia(app, evento_id: str):
    r = app.repos
    return (_foto(r.eventos.obtener_por_id(evento_id)),
            _foto(sorted(r.contratos.listar_por_evento_id(evento_id), key=lambda c: c.id)),
            _foto(sorted(r.estados_cuenta.listar_por_evento_id(evento_id), key=lambda e: e.id)),
            len(app.uow.outbox))


def _eventos_desde(app, n: int) -> Tuple[str, ...]:
    return tuple(r.evento.nombre for r in app.uow.outbox[n:])


def _tipo_evento(descripcion: str) -> str:
    """Fixture D-07: «Boda 05» → «Boda»."""
    return re.sub(r"\s+\d+$", "", descripcion).strip() or descripcion


def esperado_paquete(accion: str, actor_activo: bool) -> Tuple[str, str]:
    """(TRANSICION|EXCEPCION, texto) según el flujo de referencia y las precondiciones de ejemplo del LEEME.
    De las precondiciones de ejemplo solo `cliente_activo` tiene datos en el paquete (actores.csv); `fecha_disponible`
    y `anticipo_pagado` no tienen columna y se tratan como cumplidas por el fixture (D-05)."""
    if accion == "aprobar":
        return ((TRANSICION, "COTIZADO → CONTRATADO") if actor_activo else
                (EXCEPCION, "Excepción: precondición cliente_activo no cumplida"))
    if accion == "repetir_aprobacion":
        return ((EXCEPCION, "COTIZADO → CONTRATADO; excepción en la segunda aprobación") if actor_activo else
                (EXCEPCION, "Excepción en la primera aprobación: precondición cliente_activo no cumplida"))
    if accion == "cancelar":
        return TRANSICION, "COTIZADO → CANCELADO"
    if accion == "completar":
        return EXCEPCION, "Excepción: COTIZADO → REALIZADO no permitido"
    if accion == "saltar_estado":
        return EXCEPCION, "Excepción: no se puede saltar CONTRATADO"
    raise KeyError(accion)


def _texto_oraculo(o: OraculoDominio) -> str:
    partes = [o.resultado]
    if o.mensaje:
        partes.append(f"«{o.mensaje}»")
    partes.append(f"Evento «{o.estado_evento.value}»")
    if o.estado_contrato:
        partes.append(f"Contrato «{o.estado_contrato.value}»")
    partes.append("eventos: " + (", ".join(o.eventos) if o.eventos else "ninguno"))
    return "; ".join(partes)


# ----------------------------------------------------------------------------------------------- ejecución

class _Corrida:
    """Una transición sobre una composición en memoria nueva."""

    def __init__(self, op, actor, recursos: List[str], total: Decimal):
        self.app = construir()
        self.s, self.despachador = self.app.servicios, self.app.despachador
        self.op, self.actor, self.recursos, self.total = op, actor, recursos, total
        self.ahora = datetime.combine(op.fecha_solicitud, HORA_SOLICITUD)
        self.evento_id = self.propuesta_id = self.contrato_id = None
        self.anticipo: Optional[Decimal] = None

    def _paso(self, resultado, descripcion: str):
        self.despachador.despachar()
        if not resultado.exito:
            raise _PasoRechazado(f"{descripcion}: {resultado.mensaje}")
        return resultado

    def preparar(self) -> str:
        """Crea el Evento y la Propuesta (correspondencia de COTIZADO). Devuelve el estado de partida observado."""
        contenido = ContenidoPropuesta(tuple(self.recursos), (), Importe(self.total), CONDICIONES_FIXTURE)  # CA-005
        tipo = _tipo_evento(self.recursos[0])
        fecha = datetime.combine(self.op.fecha_solicitud + timedelta(days=DIAS_HASTA_EVENTO), HORA_EVENTO)
        r = self._paso(self.s.propuestas.registrar_evento(
            self.actor.actor_id, DatosEvento(tipo, fecha, self.actor.ciudad, INVITADOS_FIXTURE), list(self.recursos)),
            "registrar evento")
        self.evento_id = r.datos["evento_id"]
        r = self._paso(self.s.propuestas.crear_propuesta(self.evento_id, contenido, self.ahora), "crear propuesta")
        self.propuesta_id = r.datos["propuesta_id"]
        ev = self.app.repos.eventos.obtener_por_id(self.evento_id)
        pr = self.app.repos.propuestas.obtener_por_id(self.propuesta_id)
        return f"Evento «{ev.estado.value}» / Propuesta «{pr.estado.value}»"

    def aprobar(self):
        """CU-02 completo hasta la confirmación de la contratación."""
        pr = self.app.repos.propuestas.obtener_por_id(self.propuesta_id)
        t = self.ahora
        self._paso(self.s.propuestas.aceptar_propuesta(self.propuesta_id, pr.version_vigente_id, t + timedelta(hours=1)),
                   "aceptar propuesta")
        r = self._paso(self.s.contratacion.preparar_contrato(self.propuesta_id, True), "preparar contrato")
        self.contrato_id = r.datos["contrato_id"]
        self._paso(self.s.contratacion.registrar_firma_contrato(self.contrato_id, t + timedelta(hours=2)), "firmar contrato")
        self._paso(self.s.contratacion.registrar_comunicacion_politica_no_reembolso(self.contrato_id, t + timedelta(hours=2)),
                   "comunicar política de no reembolso")
        ec = self.app.repos.estados_cuenta.obtener_por_contrato_id(self.contrato_id)
        ob = next(o for o in ec.obligaciones.values() if o.concepto.value == "Anticipo")
        self.anticipo = ob.importe.cantidad
        self._paso(self.s.pagos.registrar_y_verificar_pago(ec.id, ob.obligacion_id, ob.importe, t + timedelta(days=1),
                                                           "COMPROBANTE-ANTICIPO"), "registrar y verificar anticipo")

    def ejecutar(self, accion: str):
        """Ejecuta una acción de un solo paso; devuelve su `Resultado` (None en «aprobar», que lanza _PasoRechazado
        si algún paso se rechaza). «repetir_aprobacion» se ejecuta en `_ejecutar_una`, que fotografía el estado
        entre la primera aprobación y la segunda confirmación."""
        t = self.ahora + timedelta(days=2)
        if accion == "aprobar":
            self.aprobar()
            return None
        if accion == "cancelar":
            return self.s.cierre.gestionar_cancelacion_solicitada(self.evento_id, "Cancelación solicitada (paquete)", t)
        if accion == "completar":
            return self.s.cierre.finalizar_evento(self.evento_id, t)
        if accion == "saltar_estado":
            return self.s.cierre.procesar_inicio_evento(self.evento_id, t)
        raise KeyError(accion)

    def estados(self) -> Tuple[EstadoEvento, Optional[EstadoContrato]]:
        ev = self.app.repos.eventos.obtener_por_id(self.evento_id)
        contratos = self.app.repos.contratos.listar_por_evento_id(self.evento_id)
        return ev.estado, (contratos[0].estado if contratos else None)


class _PasoRechazado(Exception):
    pass


def _diferencias(accion: str, actor_activo: bool, lineas: int) -> List[str]:
    d = []
    if lineas == 0:
        d.append("D-08")
    if accion == "cancelar":
        d.append("D-03")
    if accion == "repetir_aprobacion":
        d.append("D-04")
    if accion in ("aprobar", "repetir_aprobacion") and not actor_activo:
        d.append("D-05")
    return d


def ejecutar_transiciones(directorio=None, paquete: Optional[PaquetePIA] = None) -> List[ResultadoTransicion]:
    paquete = paquete or (leer_paquete(directorio) if directorio else leer_paquete())
    actores = {a.actor_id: a for a in paquete.actores}
    operaciones = {o.operacion_id: o for o in paquete.operaciones}
    catalogo = {c.recurso_id: c for c in paquete.catalogo}
    lineas = defaultdict(list)
    for d in paquete.detalle_operaciones:
        lineas[d.operacion_id].append(d)

    from .mapeo import ACCIONES
    operacion_dominio = {a.accion_paquete: a.operacion_dominio for a in ACCIONES}
    resultados = []
    for t in paquete.transiciones_prueba:
        op = operaciones[t.operacion_id]
        actor = actores[op.actor_id]
        recursos = [catalogo[l.recurso_id].descripcion for l in lineas[op.operacion_id]]
        total = total_operacion(lineas[op.operacion_id], {k: c.precio_mxn for k, c in catalogo.items()})
        pkg_tipo, pkg_texto = esperado_paquete(t.accion_sugerida, actor.activo)
        oraculo = ORACULO_DOMINIO[t.accion_sugerida]
        difs = _diferencias(t.accion_sugerida, actor.activo, len(lineas[op.operacion_id]))
        base = dict(caso_id=t.caso_id, operacion_id=t.operacion_id, accion_sugerida=t.accion_sugerida,
                    estado_inicial_paquete=t.estado_inicial, actor_id=actor.actor_id, actor_activo=actor.activo,
                    total_mxn=total, operacion_dominio=operacion_dominio[t.accion_sugerida],
                    esperado_paquete=pkg_texto, esperado_dominio=_texto_oraculo(oraculo))
        resultados.append(_ejecutar_una(t, op, actor, recursos, total, oraculo, pkg_tipo, difs, base))
    return resultados


def _ejecutar_una(t, op, actor, recursos, total, oraculo, pkg_tipo, difs, base) -> ResultadoTransicion:
    vacio = dict(estado_final_evento="—", estado_final_contrato="—", anticipo_mxn="—", eventos_emitidos="—",
                 sin_cambios_parciales="—")
    corrida = _Corrida(op, actor, recursos, total)
    # 1. preparación
    try:
        if not recursos:
            ContenidoPropuesta((), (), Importe(total), CONDICIONES_FIXTURE)      # el dominio debe rechazarla (CA-005)
            raise AssertionError("una propuesta sin servicios no fue rechazada")
        estado_inicial = corrida.preparar()
    except ErrorDominio as e:
        documentado = str(e) == MSG_CA005 and "D-08" in difs
        return ResultadoTransicion(
            **base, estado_inicial_dominio="No se puede crear (Propuesta sin servicios)", resultado_real=RECHAZADA,
            mensaje_real=str(e), **vacio, veredicto=NO_EJECUTABLE if documentado else FALLIDO,
            coincide_con_paquete="—", diferencias=", ".join(difs) or "—",
            explicacion=("Entrada no ejecutable en el dominio: la operación no tiene líneas y una propuesta sin "
                         "servicios se rechaza (CA-005); se verificó el rechazo" if documentado else
                         f"Rechazo inesperado al preparar la transición: {e}"))
    except (_PasoRechazado, AssertionError) as e:
        return ResultadoTransicion(**base, estado_inicial_dominio="—", resultado_real=RECHAZADA, mensaje_real=str(e),
                                   **vacio, veredicto=FALLIDO, coincide_con_paquete="—",
                                   diferencias=", ".join(difs) or "—",
                                   explicacion=f"Fallo al preparar el estado COTIZADO: {e}")
    esperado_inicial = (f"Evento «{EstadoEvento.EN_GESTION.value}» / Propuesta "
                        f"«{EstadoPropuesta.EN_REVISION_CLIENTE.value}»")
    fallas = [] if estado_inicial == esperado_inicial else [f"estado de partida {estado_inicial} ≠ {esperado_inicial}"]

    # 2. acción (para repetir_aprobacion se mide la segunda confirmación desde CONTRATADO)
    try:
        if t.accion_sugerida == "repetir_aprobacion":
            corrida.aprobar()
            foto_antes, n0 = _fotografia(corrida.app, corrida.evento_id), len(corrida.app.uow.outbox)
            r = corrida.s.contratacion.confirmar_contratacion(corrida.contrato_id, corrida.ahora + timedelta(days=2))
        elif t.accion_sugerida == "aprobar":
            foto_antes, n0 = None, len(corrida.app.uow.outbox)
            r = corrida.ejecutar("aprobar")
        else:
            foto_antes, n0 = _fotografia(corrida.app, corrida.evento_id), len(corrida.app.uow.outbox)
            r = corrida.ejecutar(t.accion_sugerida)
        corrida.despachador.despachar()
        mensaje = "" if r is None else r.mensaje
        if r is None or not r.exito:
            real = ACEPTADA if r is None else RECHAZADA
        else:
            real = ACEPTADA_SIN_EFECTO if mensaje == MSG_YA_CONFIRMADA else ACEPTADA
    except _PasoRechazado as e:
        real, mensaje, foto_antes, n0 = RECHAZADA, str(e), None, len(corrida.app.uow.outbox)

    # 3. registro y comparación con el oráculo del dominio
    emitidos = _eventos_desde(corrida.app, n0)
    estado_ev, estado_ct = corrida.estados()
    sin_cambios = "—"
    if foto_antes is not None:
        igual = _fotografia(corrida.app, corrida.evento_id) == foto_antes
        sin_cambios = "SÍ" if igual else "NO"
        if not igual:
            fallas.append("el agregado o el outbox cambiaron")
    if real != oraculo.resultado:
        fallas.append(f"resultado {real} ≠ {oraculo.resultado}")
    if oraculo.mensaje is not None and mensaje != oraculo.mensaje:
        fallas.append(f"mensaje «{mensaje}» ≠ «{oraculo.mensaje}»")
    if estado_ev != oraculo.estado_evento:
        fallas.append(f"Evento «{estado_ev.value}» ≠ «{oraculo.estado_evento.value}»")
    if oraculo.estado_contrato is not None and estado_ct != oraculo.estado_contrato:
        fallas.append(f"Contrato «{estado_ct.value if estado_ct else '—'}» ≠ «{oraculo.estado_contrato.value}»")
    if emitidos != oraculo.eventos:
        fallas.append(f"eventos {list(emitidos)} ≠ {list(oraculo.eventos)}")
    if corrida.anticipo is not None:
        esperado_anticipo = (total * PORCENTAJE_ANTICIPO).quantize(Decimal("0.01"))
        if corrida.anticipo != esperado_anticipo:
            fallas.append(f"anticipo {corrida.anticipo} ≠ {esperado_anticipo}")

    # ACEPTADA_SIN_EFECTO no es transición ni excepción: nunca coincide con el paquete (D-04)
    coincide = (pkg_tipo == TRANSICION and real == ACEPTADA) or (pkg_tipo == EXCEPCION and real == RECHAZADA)
    veredicto = FALLIDO if fallas else APROBADO
    if fallas:
        explicacion = "No coincide con el oráculo del dominio: " + "; ".join(fallas)
    else:
        explicacion = "Coincide con el oráculo del dominio"
        explicacion += ("; coincide también con el flujo del paquete" if coincide else
                        "; difiere del flujo del paquete por " + ", ".join(difs))
    return ResultadoTransicion(
        **base, estado_inicial_dominio=estado_inicial, resultado_real=real, mensaje_real=mensaje or "—",
        estado_final_evento=estado_ev.value, estado_final_contrato=estado_ct.value if estado_ct else "—",
        anticipo_mxn=str(corrida.anticipo) if corrida.anticipo is not None else "—",
        eventos_emitidos=", ".join(emitidos) or "ninguno", sin_cambios_parciales=sin_cambios, veredicto=veredicto,
        coincide_con_paquete="SÍ" if coincide else "NO", diferencias=", ".join(difs) or "—", explicacion=explicacion)
