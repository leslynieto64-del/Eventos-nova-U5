"""Mapeadores entre los siete agregados del dominio y sus filas SQL (SQLAlchemy Core, sin ORM).

Cada mapeador convierte un agregado completo en filas (`a_filas`) y lo reconstruye a partir de ellas (`desde_filas`).
- Las enumeraciones se guardan por *nombre* (`EstadoEvento.EN_GESTION` → ``'EN_GESTION'``), como define el esquema.
- Los importes viajan como `Decimal` exacto (columnas `NUMERIC` sin escala); nunca como `float`.
- Las colecciones ordenadas llevan `posicion` y se reconstruyen en el mismo orden.
- La rehidratación NO llama a los constructores de los agregados: estos registran Domain Events (p. ej. `CambioSolicitado`)
  y reconstruir un agregado desde la base de datos no debe emitir hechos nuevos. `_rehidratar` crea el objeto con
  `__new__`, inicializa solo la base `AggregateRoot` (id y lista de eventos VACÍA) y asigna cada atributo persistente,
  incluido el estado privado que el comportamiento necesita (`_operaciones_aplicadas`, `_ventana_resuelta`,
  `_cierres_sin_realizar`, `_estado_antes_de_detener`).
- Los objetos de valor sí se construyen con sus clases, de modo que conservan sus invariantes.
- Los eventos pendientes de un agregado NO se guardan aquí: viajan por el Outbox (ADR-004)."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple, Type
from domain.base import AggregateRoot
from domain.contrato import AnexoContrato, Contrato
from domain.estado_cuenta import Devolucion, EstadoCuenta, ObligacionPago, Pago
from domain.evento import Evento, RevisionAdministrativa, ServicioContratado, SolicitudCancelacion
from domain.propuesta import Propuesta, VersionPropuesta
from domain.solicitudes import (AlternativaPropuesta, SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor)
from domain.valores import (AnticipacionSolicitud, CausaCierreSolicitud, CondicionesContractuales, CondicionesServicio,
                            ConceptoPago, ContenidoPropuesta, DatosEvento, Decision, DisponibilidadProveedor,
                            EstadoContrato, EstadoDevolucion, TipoDevolucion, EstadoEvento, EstadoObligacionPago, EstadoPago,
                            EstadoPropuesta, EstadoServicioContratado, EstadoSolicitudCambio, EstadoSolicitudCancelacion,
                            EstadoSolicitudServicioAdicional, EstadoSustitucionProveedor, ImpactoModificacion, Importe,
                            MotivoCancelacionEvento, MotivoCierreSolicitud, OrigenCancelacion, PlazoPago,
                            PoliticaNoReembolso, ResultadoViabilidad, TarifaCargoTardio, TipoSolicitud)

Fila = Dict[str, object]

CONCEPTOS_EN_DIAS_HABILES = frozenset({ConceptoPago.ANTICIPO, ConceptoPago.SALDO_CONTRATO_ORIGINAL, ConceptoPago.SUSTITUCION_PROVEEDOR})


@dataclass
class Filas:
    """Representación SQL de un agregado: la fila de la raíz y las filas de cada tabla hija (clave: nombre de tabla)."""
    raiz: Fila
    hijas: Dict[str, List[Fila]] = field(default_factory=dict)


# ---------------------------------------------------------------- utilidades
def _nombre(miembro) -> Optional[str]:
    return None if miembro is None else miembro.name


def _enum(clase, nombre):
    return None if nombre is None else clase[nombre]


def _monto(importe: Optional[Importe]) -> Optional[Decimal]:
    return None if importe is None else importe.cantidad


def _importe(valor) -> Optional[Importe]:
    return None if valor is None else Importe(valor)


def _rehidratar(clase: Type[AggregateRoot], id_: str, **atributos):
    """Reconstruye un agregado sin ejecutar su constructor: no se registra ningún Domain Event."""
    obj = clase.__new__(clase)
    AggregateRoot.__init__(obj, id_)               # id + lista de eventos vacía
    for nombre, valor in atributos.items():
        setattr(obj, nombre, valor)
    return obj


def _decision_a_filas(prefijo: str, d: Optional[Decision]) -> Fila:
    if d is None:
        return {f"{prefijo}_actor": None, f"{prefijo}_aprobada": None, f"{prefijo}_fecha": None, f"{prefijo}_motivo": None}
    return {f"{prefijo}_actor": d.actor, f"{prefijo}_aprobada": d.aprobada, f"{prefijo}_fecha": d.fecha,
            f"{prefijo}_motivo": d.motivo}


def _decision_desde(prefijo: str, fila: Fila) -> Optional[Decision]:
    if fila[f"{prefijo}_aprobada"] is None:
        return None
    return Decision(fila[f"{prefijo}_actor"], fila[f"{prefijo}_aprobada"], fila[f"{prefijo}_fecha"], fila[f"{prefijo}_motivo"])


def _disponibilidad_a_filas(prefijo: str, d: Optional[DisponibilidadProveedor]) -> Fila:
    if d is None:
        return {f"{prefijo}_proveedor_id": None, f"{prefijo}_disponible": None, f"{prefijo}_costo": None,
                f"{prefijo}_condiciones": None}
    return {f"{prefijo}_proveedor_id": d.proveedor_id, f"{prefijo}_disponible": d.disponible,
            f"{prefijo}_costo": _monto(d.costo),
            f"{prefijo}_condiciones": None if d.condiciones is None else d.condiciones.descripcion}


def _disponibilidad_desde(prefijo: str, fila: Fila) -> Optional[DisponibilidadProveedor]:
    if fila[f"{prefijo}_disponible"] is None:
        return None
    cond = fila[f"{prefijo}_condiciones"]
    return DisponibilidadProveedor(fila[f"{prefijo}_proveedor_id"], fila[f"{prefijo}_disponible"],
                                   _importe(fila[f"{prefijo}_costo"]), None if cond is None else CondicionesServicio(cond))


def _impacto_a_filas(prefijo: str, i: Optional[ImpactoModificacion]) -> Fila:
    claves = ("afecta_servicios", "afecta_costos", "afecta_condiciones")
    if i is None:
        return {f"{prefijo}_{k}": None for k in claves}
    return {f"{prefijo}_{k}": getattr(i, k) for k in claves}


def _impacto_desde(prefijo: str, fila: Fila) -> Optional[ImpactoModificacion]:
    if fila[f"{prefijo}_afecta_servicios"] is None:
        return None
    return ImpactoModificacion(fila[f"{prefijo}_afecta_servicios"], fila[f"{prefijo}_afecta_costos"],
                               fila[f"{prefijo}_afecta_condiciones"])


def _datos_evento_a_filas(prefijo: str, d: Optional[DatosEvento]) -> Fila:
    if d is None:
        return {f"{prefijo}_tipo": None, f"{prefijo}_fecha_hora": None, f"{prefijo}_lugar": None,
                f"{prefijo}_invitados": None}
    return {f"{prefijo}_tipo": d.tipo, f"{prefijo}_fecha_hora": d.fecha_hora, f"{prefijo}_lugar": d.lugar,
            f"{prefijo}_invitados": d.invitados_aproximados}


def _datos_evento_desde(prefijo: str, fila: Fila) -> Optional[DatosEvento]:
    if fila[f"{prefijo}_invitados"] is None:
        return None
    return DatosEvento(fila[f"{prefijo}_tipo"], fila[f"{prefijo}_fecha_hora"], fila[f"{prefijo}_lugar"],
                       fila[f"{prefijo}_invitados"])


def _base_solicitud_a_filas(s) -> Fila:
    """Columnas comunes de las tres solicitudes (`_SolicitudBase`)."""
    m = s.motivo_cierre
    return {
        "evento_id": s.evento_id, "contrato_id": s.contrato_id, "estado_cuenta_id": s.estado_cuenta_id,
        "anexo_id": s.anexo_id, "obligacion_pago_id": s.obligacion_pago_id,
        "motivo_cierre_causa": None if m is None else m.causa.name,
        "motivo_cierre_descripcion": None if m is None else m.descripcion,
        "motivo_cierre_fecha": None if m is None else m.fecha,
        "estado": s.estado.name, "estado_antes_de_detener": _nombre(s._estado_antes_de_detener),
    }


def _base_solicitud_desde(fila: Fila, enum_estado) -> dict:
    motivo = None
    if fila["motivo_cierre_causa"] is not None:
        motivo = MotivoCierreSolicitud(CausaCierreSolicitud[fila["motivo_cierre_causa"]],
                                       fila["motivo_cierre_descripcion"], fila["motivo_cierre_fecha"])
    return {
        "evento_id": fila["evento_id"], "contrato_id": fila["contrato_id"], "estado_cuenta_id": fila["estado_cuenta_id"],
        "anexo_id": fila["anexo_id"], "obligacion_pago_id": fila["obligacion_pago_id"], "motivo_cierre": motivo,
        "estado": enum_estado[fila["estado"]], "_estado_antes_de_detener": _enum(enum_estado, fila["estado_antes_de_detener"]),
    }


class Mapeador:
    """Contrato común. `hijas` lista, en orden de guardado, (tabla hija, columna que apunta a la raíz, columnas de orden)."""
    agregado: Type[AggregateRoot]
    tabla_raiz: str
    columna_id: str
    hijas: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = ()

    def a_filas(self, ag) -> Filas:                     # pragma: no cover - interfaz
        raise NotImplementedError

    def desde_filas(self, f: Filas):                    # pragma: no cover - interfaz
        raise NotImplementedError


# ================================================================ Propuesta
class MapeadorPropuesta(Mapeador):
    agregado, tabla_raiz, columna_id = Propuesta, "propuesta", "propuesta_id"
    hijas = (("version_propuesta", "propuesta_id", ("numero",)),)

    def a_filas(self, p: Propuesta) -> Filas:
        raiz = {"propuesta_id": p.id, "evento_id": p.evento_id, "cliente_id": p.cliente_id, "estado": p.estado.name,
                "version_vigente_id": p.version_vigente_id, "motivo_cierre": p.motivo_cierre}
        versiones = [{"version_id": v.version_id, "propuesta_id": p.id, "numero": v.numero,
                      "fecha_actualizacion": v.fecha_actualizacion, "servicios": list(v.contenido.servicios),
                      "proveedores_considerados": list(v.contenido.proveedores_considerados),
                      "costo_total": v.contenido.costo_total.cantidad, "condiciones": v.contenido.condiciones}
                     for v in p.versiones]
        return Filas(raiz, {"version_propuesta": versiones})

    def desde_filas(self, f: Filas) -> Propuesta:
        r = f.raiz
        versiones = [VersionPropuesta(v["version_id"], v["numero"], v["fecha_actualizacion"],
                                      ContenidoPropuesta(tuple(v["servicios"]), tuple(v["proveedores_considerados"]),
                                                         Importe(v["costo_total"]), v["condiciones"]))
                     for v in f.hijas["version_propuesta"]]
        return _rehidratar(Propuesta, r["propuesta_id"], evento_id=r["evento_id"], cliente_id=r["cliente_id"],
                           versiones=versiones, version_vigente_id=r["version_vigente_id"],
                           estado=EstadoPropuesta[r["estado"]], motivo_cierre=r["motivo_cierre"])


# ================================================================ Contrato
class MapeadorContrato(Mapeador):
    agregado, tabla_raiz, columna_id = Contrato, "contrato", "contrato_id"
    hijas = (("contrato_seguimiento_anticipo", "contrato_id", ("posicion",)), ("contrato_anexo", "contrato_id", ("posicion",)))

    def a_filas(self, c: Contrato) -> Filas:
        raiz = {"contrato_id": c.id, "evento_id": c.evento_id, "propuesta_id": c.propuesta_id,
                "version_aceptada_id": c.version_aceptada_id, "servicios": list(c.condiciones.servicios),
                "costo_total": c.condiciones.costo_total.cantidad, "condiciones": c.condiciones.condiciones,
                "politica_incluida": c.politica.incluida, "politica_comunicada_en": c.politica.comunicada_en,
                "estado": c.estado.name, "fecha_firma": c.fecha_firma}
        seg = [{"contrato_id": c.id, "posicion": i, "fecha": fecha, "resultado": resultado}
               for i, (fecha, resultado) in enumerate(c.seguimientos_anticipo)]
        anexos = [{"anexo_id": a.anexo_id, "contrato_id": c.id, "posicion": i, "tipo_origen": a.tipo_origen.name,
                   "origen_id": a.origen_id, "descripcion": a.descripcion, "fecha": a.fecha} for i, a in enumerate(c.anexos)]
        return Filas(raiz, {"contrato_seguimiento_anticipo": seg, "contrato_anexo": anexos})

    def desde_filas(self, f: Filas) -> Contrato:
        r = f.raiz
        return _rehidratar(
            Contrato, r["contrato_id"], evento_id=r["evento_id"], propuesta_id=r["propuesta_id"],
            version_aceptada_id=r["version_aceptada_id"],
            condiciones=CondicionesContractuales(tuple(r["servicios"]), Importe(r["costo_total"]), r["condiciones"]),
            politica=PoliticaNoReembolso(r["politica_incluida"], r["politica_comunicada_en"]),
            estado=EstadoContrato[r["estado"]], fecha_firma=r["fecha_firma"],
            seguimientos_anticipo=[(s["fecha"], s["resultado"]) for s in f.hijas["contrato_seguimiento_anticipo"]],
            anexos=[AnexoContrato(a["anexo_id"], TipoSolicitud[a["tipo_origen"]], a["origen_id"], a["descripcion"], a["fecha"])
                    for a in f.hijas["contrato_anexo"]])


# ================================================================ Evento
class MapeadorEvento(Mapeador):
    agregado, tabla_raiz, columna_id = Evento, "evento", "evento_id"
    hijas = (("evento_servicio_contratado", "evento_id", ("posicion",)),
             ("evento_solicitud_cancelacion", "evento_id", ("posicion",)),
             ("evento_operacion_aplicada", "evento_id", ("operacion_id",)))

    def a_filas(self, e: Evento) -> Filas:
        mc, ra = e.motivo_cancelacion, e.revision_administrativa
        raiz = {
            "evento_id": e.id, "cliente_id": e.cliente_id, "tipo": e.datos.tipo, "fecha_hora": e.datos.fecha_hora,
            "lugar": e.datos.lugar, "invitados_aproximados": e.datos.invitados_aproximados,
            "servicios_solicitados": list(e.servicios_solicitados), "estado": e.estado.name,
            "fecha_inicio": e.fecha_inicio, "fecha_finalizacion": e.fecha_finalizacion,
            "motivo_cancelacion_origen": None if mc is None else mc.origen.name,
            "motivo_cancelacion_descripcion": None if mc is None else mc.descripcion,
            "motivo_cancelacion_fecha": None if mc is None else mc.fecha,
            "motivo_cancelacion_registrado_por": None if mc is None else mc.registrado_por,
            "revision_resultado": None if ra is None else ra.resultado,
            "revision_pagos_realizados": None if ra is None else ra.pagos_realizados.cantidad,
            "revision_saldo_pendiente": None if ra is None else ra.saldo_pendiente.cantidad,
            "revision_politica_incluida": None if ra is None else ra.politica_incluida,
            "revision_constancia_no_reembolso": None if ra is None else ra.constancia_no_reembolso,
            "revision_fecha": None if ra is None else ra.fecha,
        }
        servicios = [{"evento_id": e.id, "servicio_contratado_id": clave, "posicion": i, "servicio": s.servicio,
                      "proveedor_id": s.proveedor_id, "condiciones": s.condiciones.descripcion, "estado": s.estado.name}
                     for i, (clave, s) in enumerate(e.servicios.items())]
        cancelaciones = [{"evento_id": e.id, "posicion": i, "fecha": s.fecha, "motivo": s.motivo, "estado": s.estado.name}
                         for i, s in enumerate(e.solicitudes_cancelacion)]
        operaciones = [{"evento_id": e.id, "operacion_id": o} for o in sorted(e._operaciones_aplicadas)]
        return Filas(raiz, {"evento_servicio_contratado": servicios, "evento_solicitud_cancelacion": cancelaciones,
                            "evento_operacion_aplicada": operaciones})

    def desde_filas(self, f: Filas) -> Evento:
        r = f.raiz
        motivo = None
        if r["motivo_cancelacion_origen"] is not None:
            motivo = MotivoCancelacionEvento(OrigenCancelacion[r["motivo_cancelacion_origen"]],
                                             r["motivo_cancelacion_descripcion"], r["motivo_cancelacion_fecha"],
                                             r["motivo_cancelacion_registrado_por"])
        revision = None
        if r["revision_resultado"] is not None:
            revision = RevisionAdministrativa(r["revision_resultado"], Importe(r["revision_pagos_realizados"]),
                                              Importe(r["revision_saldo_pendiente"]), r["revision_politica_incluida"],
                                              r["revision_constancia_no_reembolso"], r["revision_fecha"])
        servicios = {s["servicio_contratado_id"]: ServicioContratado(
            s["servicio_contratado_id"], s["servicio"], s["proveedor_id"], CondicionesServicio(s["condiciones"]),
            EstadoServicioContratado[s["estado"]]) for s in f.hijas["evento_servicio_contratado"]}
        return _rehidratar(
            Evento, r["evento_id"], cliente_id=r["cliente_id"],
            datos=DatosEvento(r["tipo"], r["fecha_hora"], r["lugar"], r["invitados_aproximados"]),
            servicios_solicitados=list(r["servicios_solicitados"]), estado=EstadoEvento[r["estado"]], servicios=servicios,
            solicitudes_cancelacion=[SolicitudCancelacion(c["fecha"], c["motivo"], EstadoSolicitudCancelacion[c["estado"]])
                                     for c in f.hijas["evento_solicitud_cancelacion"]],
            motivo_cancelacion=motivo, revision_administrativa=revision, fecha_finalizacion=r["fecha_finalizacion"],
            fecha_inicio=r["fecha_inicio"],
            _operaciones_aplicadas={o["operacion_id"] for o in f.hijas["evento_operacion_aplicada"]})


# ================================================================ SolicitudCambio
class MapeadorSolicitudCambio(Mapeador):
    agregado, tabla_raiz, columna_id = SolicitudCambio, "solicitud_cambio", "solicitud_id"
    hijas = (("solicitud_cambio_condicion", "solicitud_id", ("posicion",)),)

    def a_filas(self, s: SolicitudCambio) -> Filas:
        v = s.viabilidad
        raiz = {
            "solicitud_id": s.id, **_base_solicitud_a_filas(s), "descripcion": s.descripcion,
            "anticipacion_fecha_solicitud": s.anticipacion.fecha_solicitud, "anticipacion_fecha_evento": s.anticipacion.fecha_evento,
            "tarifa_importe": s.tarifa.importe.cantidad, **_datos_evento_a_filas("datos_propuestos", s.datos_propuestos),
            "viabilidad_viable": None if v is None else v.viable, "viabilidad_motivo": None if v is None else v.motivo,
            **_impacto_a_filas("impacto", s.impacto), "costo_proveedor": _monto(s.costo_proveedor),
            **_decision_a_filas("decision_cliente", s.decision_cliente),
            **_decision_a_filas("autorizacion", s.autorizacion_administracion),
            "importes_por_pagar": s.importes_por_pagar,
        }
        condiciones = [{"solicitud_id": s.id, "servicio_contratado_id": clave, "posicion": i, "condiciones": c.descripcion}
                       for i, (clave, c) in enumerate(s.condiciones_propuestas.items())]
        return Filas(raiz, {"solicitud_cambio_condicion": condiciones})

    def desde_filas(self, f: Filas) -> SolicitudCambio:
        r = f.raiz
        viab = None if r["viabilidad_viable"] is None else ResultadoViabilidad(r["viabilidad_viable"], r["viabilidad_motivo"])
        return _rehidratar(
            SolicitudCambio, r["solicitud_id"], **_base_solicitud_desde(r, EstadoSolicitudCambio),
            descripcion=r["descripcion"],
            anticipacion=AnticipacionSolicitud(r["anticipacion_fecha_solicitud"], r["anticipacion_fecha_evento"]),
            tarifa=TarifaCargoTardio(Importe(r["tarifa_importe"])),
            datos_propuestos=_datos_evento_desde("datos_propuestos", r),
            condiciones_propuestas={c["servicio_contratado_id"]: CondicionesServicio(c["condiciones"])
                                    for c in f.hijas["solicitud_cambio_condicion"]},
            viabilidad=viab, impacto=_impacto_desde("impacto", r), costo_proveedor=_importe(r["costo_proveedor"]),
            decision_cliente=_decision_desde("decision_cliente", r),
            autorizacion_administracion=_decision_desde("autorizacion", r), importes_por_pagar=r["importes_por_pagar"])


# ================================================================ SolicitudServicioAdicional
class MapeadorSolicitudServicioAdicional(Mapeador):
    agregado, tabla_raiz, columna_id = SolicitudServicioAdicional, "solicitud_servicio_adicional", "solicitud_id"

    def a_filas(self, s: SolicitudServicioAdicional) -> Filas:
        raiz = {
            "solicitud_id": s.id, **_base_solicitud_a_filas(s), "servicio": s.servicio,
            "anticipacion_fecha_solicitud": s.anticipacion.fecha_solicitud, "anticipacion_fecha_evento": s.anticipacion.fecha_evento,
            "elegibilidad_obtenida": s.elegibilidad_obtenida, **_disponibilidad_a_filas("disponibilidad", s.disponibilidad),
            **_decision_a_filas("decision_cliente", s.decision_cliente),
            **_decision_a_filas("autorizacion", s.autorizacion_administracion),
        }
        return Filas(raiz)

    def desde_filas(self, f: Filas) -> SolicitudServicioAdicional:
        r = f.raiz
        return _rehidratar(
            SolicitudServicioAdicional, r["solicitud_id"], **_base_solicitud_desde(r, EstadoSolicitudServicioAdicional),
            servicio=r["servicio"],
            anticipacion=AnticipacionSolicitud(r["anticipacion_fecha_solicitud"], r["anticipacion_fecha_evento"]),
            elegibilidad_obtenida=r["elegibilidad_obtenida"], disponibilidad=_disponibilidad_desde("disponibilidad", r),
            decision_cliente=_decision_desde("decision_cliente", r),
            autorizacion_administracion=_decision_desde("autorizacion", r))


# ================================================================ SustitucionProveedor
class MapeadorSustitucionProveedor(Mapeador):
    agregado, tabla_raiz, columna_id = SustitucionProveedor, "sustitucion_proveedor", "sustitucion_id"
    hijas = (("sustitucion_alternativa", "sustitucion_id", ("posicion",)),)

    def a_filas(self, s: SustitucionProveedor) -> Filas:
        raiz = {"sustitucion_id": s.id, **_base_solicitud_a_filas(s), "servicio_contratado_id": s.servicio_contratado_id,
                "proveedor_original_id": s.proveedor_original_id, "costo_adicional": _monto(s.costo_adicional),
                "aprobada_despues_del_limite": s.aprobada_despues_del_limite}
        alternativas = [{"sustitucion_id": s.id, "posicion": i, "proveedor_id": a.proveedor_id,
                         **_disponibilidad_a_filas("disponibilidad", a.disponibilidad),
                         **_impacto_a_filas("impacto", a.impacto),
                         **_decision_a_filas("decision_cliente", a.decision_cliente),
                         **_decision_a_filas("autorizacion", a.autorizacion_administracion)}
                        for i, a in enumerate(s.alternativas)]
        return Filas(raiz, {"sustitucion_alternativa": alternativas})

    def desde_filas(self, f: Filas) -> SustitucionProveedor:
        r = f.raiz
        alternativas = [AlternativaPropuesta(a["proveedor_id"], _disponibilidad_desde("disponibilidad", a),
                                             _impacto_desde("impacto", a), _decision_desde("decision_cliente", a),
                                             _decision_desde("autorizacion", a))
                        for a in f.hijas["sustitucion_alternativa"]]
        return _rehidratar(
            SustitucionProveedor, r["sustitucion_id"], **_base_solicitud_desde(r, EstadoSustitucionProveedor),
            servicio_contratado_id=r["servicio_contratado_id"], proveedor_original_id=r["proveedor_original_id"],
            alternativas=alternativas, costo_adicional=_importe(r["costo_adicional"]),
            aprobada_despues_del_limite=r["aprobada_despues_del_limite"])


# ================================================================ EstadoCuenta
class MapeadorEstadoCuenta(Mapeador):
    agregado, tabla_raiz, columna_id = EstadoCuenta, "estado_cuenta", "estado_cuenta_id"
    hijas = (("obligacion_pago", "estado_cuenta_id", ("posicion",)), ("pago", "estado_cuenta_id", ("posicion",)),
             ("devolucion", "estado_cuenta_id", ("posicion",)),
             ("estado_cuenta_seguimiento_cobro", "estado_cuenta_id", ("posicion",)),
             ("estado_cuenta_cierre_sin_realizar", "estado_cuenta_id", ("origen_id",)))

    def a_filas(self, ec: EstadoCuenta) -> Filas:
        raiz = {"estado_cuenta_id": ec.id, "contrato_id": ec.contrato_id, "evento_id": ec.evento_id,
                "resultado_regularizacion": ec.resultado_regularizacion,
                "fecha_resultado_regularizacion": ec.fecha_resultado_regularizacion,
                "ventana_resuelta_obligacion_id": ec._ventana_resuelta, "cierre_contratacion": ec.cierre_contratacion}
        obligaciones = [{"estado_cuenta_id": ec.id, "obligacion_id": clave, "posicion": i, "concepto": o.concepto.name,
                         "importe": o.importe.cantidad, "plazo_inicio": None if o.plazo is None else o.plazo.inicio,
                         "plazo_vence": None if o.plazo is None else o.plazo.vence, "origen_id": o.origen_id,
                         "estado": o.estado.name} for i, (clave, o) in enumerate(ec.obligaciones.items())]
        pagos = [{"estado_cuenta_id": ec.id, "pago_id": p.pago_id, "posicion": i, "obligacion_id": p.obligacion_id,
                  "importe": p.importe.cantidad, "fecha": p.fecha, "comprobante": p.comprobante, "estado": p.estado.name,
                  "registrado_en": p.registrado_en, "verificado_en": p.verificado_en} for i, p in enumerate(ec.pagos)]
        devoluciones = [{"estado_cuenta_id": ec.id, "devolucion_id": d.devolucion_id, "posicion": i,
                         "solicitud_id": d.solicitud_id, "concepto": d.concepto.name, "importe": d.importe.cantidad,
                         "motivo_devolucion": d.motivo_devolucion, "fecha_cierre": d.fecha_cierre, "estado": d.estado.name,
                         "fecha_devolucion": d.fecha_devolucion, "comprobante": d.comprobante, "tipo": d.tipo.name,
                         "pago_id": d.pago_id, "fecha_referencia": d.fecha_referencia}
                        for i, d in enumerate(ec.devoluciones)]
        seguimientos = [{"estado_cuenta_id": ec.id, "posicion": i, "seguimiento": t} for i, t in enumerate(ec.seguimientos_cobro)]
        cierres = [{"estado_cuenta_id": ec.id, "origen_id": origen, "fecha_cierre": fecha, "evento_cancelado": cancelado}
                   for origen, (fecha, cancelado) in ec._cierres_sin_realizar.items()]
        return Filas(raiz, {"obligacion_pago": obligaciones, "pago": pagos, "devolucion": devoluciones,
                            "estado_cuenta_seguimiento_cobro": seguimientos, "estado_cuenta_cierre_sin_realizar": cierres})

    def desde_filas(self, f: Filas) -> EstadoCuenta:
        r = f.raiz
        obligaciones = {}
        for o in f.hijas["obligacion_pago"]:
            concepto = ConceptoPago[o["concepto"]]
            # el límite exclusivo (GL-060, E-1) lo fija el concepto: anticipo, saldo y sustitución se miden en días hábiles
            plazo = None if o["plazo_inicio"] is None else PlazoPago(o["plazo_inicio"], o["plazo_vence"], concepto in CONCEPTOS_EN_DIAS_HABILES)
            obligaciones[o["obligacion_id"]] = ObligacionPago(
                o["obligacion_id"], ConceptoPago[o["concepto"]], Importe(o["importe"]), plazo, o["origen_id"],
                EstadoObligacionPago[o["estado"]])
        pagos = [Pago(p["pago_id"], p["obligacion_id"], Importe(p["importe"]), p["fecha"], p["comprobante"],
                      EstadoPago[p["estado"]], p["registrado_en"], p["verificado_en"]) for p in f.hijas["pago"]]
        devoluciones = [Devolucion(d["devolucion_id"], d["solicitud_id"], ConceptoPago[d["concepto"]], Importe(d["importe"]),
                                   d["motivo_devolucion"], d["fecha_cierre"], EstadoDevolucion[d["estado"]],
                                   d["fecha_devolucion"], d["comprobante"], TipoDevolucion[d["tipo"]], d["pago_id"],
                                   d["fecha_referencia"]) for d in f.hijas["devolucion"]]
        return _rehidratar(
            EstadoCuenta, r["estado_cuenta_id"], contrato_id=r["contrato_id"], evento_id=r["evento_id"],
            obligaciones=obligaciones, pagos=pagos, devoluciones=devoluciones,
            seguimientos_cobro=[s["seguimiento"] for s in f.hijas["estado_cuenta_seguimiento_cobro"]],
            resultado_regularizacion=r["resultado_regularizacion"],
            fecha_resultado_regularizacion=r["fecha_resultado_regularizacion"],
            _ventana_resuelta=r["ventana_resuelta_obligacion_id"], cierre_contratacion=r["cierre_contratacion"],
            _cierres_sin_realizar={c["origen_id"]: (c["fecha_cierre"], c["evento_cancelado"])
                                   for c in f.hijas["estado_cuenta_cierre_sin_realizar"]})


MAPEADORES: Dict[Type[AggregateRoot], Mapeador] = {m.agregado: m for m in (
    MapeadorPropuesta(), MapeadorContrato(), MapeadorEvento(), MapeadorSolicitudCambio(),
    MapeadorSolicitudServicioAdicional(), MapeadorSustitucionProveedor(), MapeadorEstadoCuenta())}


def mapeador_de(agregado_o_clase) -> Mapeador:
    clase = agregado_o_clase if isinstance(agregado_o_clase, type) else type(agregado_o_clase)
    return MAPEADORES[clase]
