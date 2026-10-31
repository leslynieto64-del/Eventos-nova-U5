"""Metadatos SQLAlchemy Core del esquema relacional de PostgreSQL (Fase 2, incremento 2).

Solo define tablas: no hay ORM, repositorios SQL ni mapeadores. Alembic usa `metadata` para conocer el esquema y los
repositorios SQL futuros usarán estas mismas tablas. El diseño y su justificación están en
docs/architecture/esquema-relacional-postgresql.md.

Convenciones:
- Estados y enumeraciones se guardan como el *nombre* del miembro del Enum del dominio (ASCII, estable) en VARCHAR con un
  CHECK; no se usan tipos ENUM nativos de PostgreSQL para no complicar las migraciones futuras.
- Fechas y horas: TIMESTAMP sin zona. El dominio usa fechas locales sin zona (America/Mexico_City, TP-06); no se convierten.
- Importes: NUMERIC sin precisión ni escala (el dominio no fija ninguna: no se inventa un máximo ni una escala), nunca float.
  `Importe` no admite negativos y el CHECK exige además un valor finito: en PostgreSQL `'NaN' >= 0` es verdadero y
  NUMERIC sin precisión admite NaN e Infinity, de modo que `>= 0` por sí solo no basta.
- Referencias entre raíces de agregado (D-01): hay clave foránea hacia la *raíz* cuando el código confirma que existe al
  crear el agregado (evento, versión de propuesta, contrato, estado de cuenta); NO hay cascada de borrado entre raíces
  (NO ACTION). Las referencias a filas hijas de otro agregado (anexo, obligación, servicio contratado), a identificadores
  polimórficos (origen_id, solicitud_id, agregado_id) o sin tabla (cliente_id, proveedor_id) quedan como referencia blanda.
- Las colecciones ordenadas llevan `posicion` para reconstruir el agregado en el mismo orden.
"""
from __future__ import annotations
from enum import Enum
from typing import Iterable, Type
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from domain import valores as V

CONVENCION_NOMBRES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = sa.MetaData(naming_convention=CONVENCION_NOMBRES)

# Estados del Outbox (UnitOfWorkMemoria.RegistroOutbox usa «Pendiente», «Procesado» y «Revisión»).
ESTADOS_OUTBOX = ("PENDIENTE", "PROCESADO", "REVISION")


# ---------------------------------------------------------------- ayudas de definición
def _nombres(enum: Type[Enum]) -> str:
    return ", ".join(f"'{m.name}'" for m in enum)


def _en_enum(columna: str, enum: Type[Enum]) -> str:
    return f"{columna} IN ({_nombres(enum)})"


def _todo_o_nada(*columnas: str) -> str:
    """Un Value Object opcional incrustado: o todas sus columnas obligatorias vienen informadas, o ninguna."""
    nulas = " AND ".join(f"{c} IS NULL" for c in columnas)
    llenas = " AND ".join(f"{c} IS NOT NULL" for c in columnas)
    return f"({nulas}) OR ({llenas})"


def _texto(nombre: str, **kw) -> sa.Column:
    return sa.Column(nombre, sa.Text, **kw)


def _importe(nombre: str, **kw) -> sa.Column:
    return sa.Column(nombre, sa.Numeric(), **kw)


def _importe_valido(*columnas: str, anulable: bool = False) -> str:
    """Importe del dominio: no negativo y finito (sin NaN ni Infinity). Con `anulable`, una columna sin valor es válida."""
    cuerpo = " AND ".join(f"{c} >= 0 AND {c} <> 'NaN' AND {c} <> 'Infinity'" for c in columnas)
    return f"{columnas[0]} IS NULL OR ({cuerpo})" if anulable else cuerpo


def _fecha(nombre: str, **kw) -> sa.Column:
    return sa.Column(nombre, sa.DateTime(timezone=False), **kw)


def _version() -> sa.Column:
    """Versión de la raíz de agregado para el control de concurrencia optimista (revisión 0004). Sube en cada guardado."""
    return sa.Column("version", sa.BigInteger, nullable=False, server_default="0")


def _estado(enum: Type[Enum], nombre: str = "estado", **kw) -> sa.Column:
    return sa.Column(nombre, sa.String(40), **kw)


def _posicion() -> sa.Column:
    return sa.Column("posicion", sa.Integer, nullable=False)


def _decision(prefijo: str) -> Iterable[sa.SchemaItem]:
    """Value Object Decision(actor, aprobada, fecha, motivo), opcional."""
    p = prefijo
    return (
        _texto(f"{p}_actor"), sa.Column(f"{p}_aprobada", sa.Boolean), _fecha(f"{p}_fecha"), _texto(f"{p}_motivo"),
        sa.CheckConstraint(_todo_o_nada(f"{p}_actor", f"{p}_aprobada", f"{p}_fecha", f"{p}_motivo"), name=f"{p}_completa"),
    )


def _impacto(prefijo: str = "impacto") -> Iterable[sa.SchemaItem]:
    """Value Object ImpactoModificacion(afecta_servicios, afecta_costos, afecta_condiciones), opcional."""
    p = prefijo
    cols = (f"{p}_afecta_servicios", f"{p}_afecta_costos", f"{p}_afecta_condiciones")
    return (*(sa.Column(c, sa.Boolean) for c in cols), sa.CheckConstraint(_todo_o_nada(*cols), name=f"{p}_completo"))


def _disponibilidad(prefijo: str) -> Iterable[sa.SchemaItem]:
    """DisponibilidadProveedor(proveedor_id, disponible, costo?, condiciones?), opcional. costo y condiciones pueden ser None."""
    p = prefijo
    return (
        _texto(f"{p}_proveedor_id"), sa.Column(f"{p}_disponible", sa.Boolean), _importe(f"{p}_costo"),
        _texto(f"{p}_condiciones"),
        sa.CheckConstraint(_todo_o_nada(f"{p}_proveedor_id", f"{p}_disponible"), name=f"{p}_completa"),
        sa.CheckConstraint(_importe_valido(f"{p}_costo", anulable=True), name=f"{p}_costo_valido"),
    )


def _solicitud_base(tabla: str) -> Iterable[sa.SchemaItem]:
    """Columnas de _SolicitudBase compartidas por las tres solicitudes."""
    return (
        _texto("evento_id", nullable=False), _texto("contrato_id", nullable=False),
        _texto("estado_cuenta_id", nullable=False),
        _texto("anexo_id"), _texto("obligacion_pago_id"),
        # La solicitud se crea con un Evento existente y con el EstadoCuenta del contrato (_estado_cuenta_del_contrato).
        sa.ForeignKeyConstraint(["evento_id"], ["evento.evento_id"], name=f"fk_{tabla}_evento"),
        sa.ForeignKeyConstraint(["estado_cuenta_id", "contrato_id"], ["estado_cuenta.estado_cuenta_id", "estado_cuenta.contrato_id"],
                                name=f"fk_{tabla}_estado_cuenta"),
        # MotivoCierreSolicitud(causa, descripcion, fecha), opcional
        sa.Column("motivo_cierre_causa", sa.String(40)), _texto("motivo_cierre_descripcion"), _fecha("motivo_cierre_fecha"),
        sa.CheckConstraint(_todo_o_nada("motivo_cierre_causa", "motivo_cierre_descripcion", "motivo_cierre_fecha"),
                           name="motivo_cierre_completo"),
        sa.CheckConstraint("motivo_cierre_causa IS NULL OR " + _en_enum("motivo_cierre_causa", V.CausaCierreSolicitud),
                           name="motivo_cierre_causa_valida"),
    )


# ================================================================ Propuesta
propuesta = sa.Table(
    "propuesta", metadata,
    _texto("propuesta_id", nullable=False), _texto("evento_id", nullable=False), _texto("cliente_id", nullable=False),
    _estado(V.EstadoPropuesta, nullable=False), _texto("version_vigente_id", nullable=False), _texto("motivo_cierre"),
    sa.PrimaryKeyConstraint("propuesta_id"),
    sa.ForeignKeyConstraint(["evento_id"], ["evento.evento_id"]),                   # crear_propuesta exige un Evento existente
    sa.CheckConstraint(_en_enum("estado", V.EstadoPropuesta), name="estado_valido"),
)
sa.Index("ix_propuesta_evento_id", propuesta.c.evento_id)

version_propuesta = sa.Table(
    "version_propuesta", metadata,
    _texto("version_id", nullable=False), _texto("propuesta_id", nullable=False), sa.Column("numero", sa.Integer, nullable=False),
    _fecha("fecha_actualizacion", nullable=False),
    # ContenidoPropuesta
    sa.Column("servicios", pg.ARRAY(sa.Text), nullable=False), sa.Column("proveedores_considerados", pg.ARRAY(sa.Text), nullable=False),
    _importe("costo_total", nullable=False), _texto("condiciones", nullable=False),
    sa.PrimaryKeyConstraint("version_id"),
    sa.ForeignKeyConstraint(["propuesta_id"], ["propuesta.propuesta_id"], ondelete="CASCADE"),
    sa.UniqueConstraint("propuesta_id", "numero"),                       # BN-002, CA-007: número consecutivo por propuesta
    sa.UniqueConstraint("propuesta_id", "version_id"),                   # destino de las FK compuestas de versión vigente y aceptada
    sa.CheckConstraint("numero >= 1", name="numero_positivo"),
    sa.CheckConstraint(_importe_valido("costo_total"), name="costo_total_valido"),           # Importe
    sa.CheckConstraint("cardinality(servicios) > 0 AND condiciones <> ''", name="contenido_completo"),   # CA-005
)
# GL-008: la versión vigente es una versión *de la misma propuesta* (id `{propuesta}-v{n}`; `version_aceptada()` la busca en
# `self.versiones`). La FK compuesta garantiza pertenencia y no solo existencia. Referencia circular: se crea con ALTER y
# diferida para insertar la propuesta y su primera versión en la misma transacción.
sa.ForeignKeyConstraint(
    ["propuesta_id", "version_vigente_id"], ["version_propuesta.propuesta_id", "version_propuesta.version_id"],
    name="fk_propuesta_version_vigente", deferrable=True, initially="DEFERRED", use_alter=True, table=propuesta)

# ================================================================ Contrato
contrato = sa.Table(
    "contrato", metadata,
    _texto("contrato_id", nullable=False), _texto("evento_id", nullable=False), _texto("propuesta_id", nullable=False),
    _texto("version_aceptada_id", nullable=False),
    # CondicionesContractuales
    sa.Column("servicios", pg.ARRAY(sa.Text), nullable=False), _importe("costo_total", nullable=False),
    _texto("condiciones", nullable=False),
    # PoliticaNoReembolso(incluida, comunicada_en?)
    sa.Column("politica_incluida", sa.Boolean, nullable=False), _fecha("politica_comunicada_en"),
    _estado(V.EstadoContrato, nullable=False), _fecha("fecha_firma"),
    sa.PrimaryKeyConstraint("contrato_id"),
    sa.UniqueConstraint("contrato_id", "evento_id"),                  # destino de la FK compuesta de estado_cuenta
    sa.ForeignKeyConstraint(["evento_id"], ["evento.evento_id"]),
    # preparar_contrato toma la versión aceptada de `propuesta.version_aceptada()` y la propuesta de `p.id`: la versión
    # debe pertenecer a esa propuesta. Este FK también garantiza que la propuesta exista.
    sa.ForeignKeyConstraint(["propuesta_id", "version_aceptada_id"],
                            ["version_propuesta.propuesta_id", "version_propuesta.version_id"], name="fk_contrato_version_aceptada"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoContrato), name="estado_valido"),
    sa.CheckConstraint(_importe_valido("costo_total"), name="costo_total_valido"),
    sa.CheckConstraint("politica_incluida", name="politica_incluida"),                  # CA-016: el constructor la exige
    sa.CheckConstraint("(politica_comunicada_en IS NULL) OR politica_incluida", name="comunicacion_requiere_politica"),
)
sa.Index("ix_contrato_evento_id", contrato.c.evento_id)

contrato_seguimiento_anticipo = sa.Table(
    "contrato_seguimiento_anticipo", metadata,
    _texto("contrato_id", nullable=False), _posicion(), _fecha("fecha", nullable=False), _texto("resultado", nullable=False),
    sa.PrimaryKeyConstraint("contrato_id", "posicion"),
    sa.ForeignKeyConstraint(["contrato_id"], ["contrato.contrato_id"], ondelete="CASCADE"),
)

contrato_anexo = sa.Table(
    "contrato_anexo", metadata,
    _texto("anexo_id", nullable=False), _texto("contrato_id", nullable=False), _posicion(),
    sa.Column("tipo_origen", sa.String(40), nullable=False), _texto("origen_id", nullable=False),
    _texto("descripcion", nullable=False), _fecha("fecha", nullable=False),
    sa.PrimaryKeyConstraint("anexo_id"),
    sa.ForeignKeyConstraint(["contrato_id"], ["contrato.contrato_id"], ondelete="CASCADE"),
    sa.UniqueConstraint("contrato_id", "origen_id"),                  # «La operación ya tiene un anexo registrado»
    sa.UniqueConstraint("contrato_id", "posicion"),
    sa.CheckConstraint(_en_enum("tipo_origen", V.TipoSolicitud), name="tipo_origen_valido"),
)

# ================================================================ Evento
evento = sa.Table(
    "evento", metadata,
    _texto("evento_id", nullable=False), _texto("cliente_id", nullable=False),
    # DatosEvento
    _texto("tipo", nullable=False), _fecha("fecha_hora", nullable=False), _texto("lugar", nullable=False),
    sa.Column("invitados_aproximados", sa.BigInteger, nullable=False),   # BIGINT: límite técnico 9223372036854775807, no de negocio
    sa.Column("servicios_solicitados", pg.ARRAY(sa.Text), nullable=False),
    _estado(V.EstadoEvento, nullable=False), _fecha("fecha_inicio"), _fecha("fecha_finalizacion"),
    # MotivoCancelacionEvento(origen, descripcion, fecha, registrado_por), opcional
    sa.Column("motivo_cancelacion_origen", sa.String(40)), _texto("motivo_cancelacion_descripcion"),
    _fecha("motivo_cancelacion_fecha"), _texto("motivo_cancelacion_registrado_por"),
    # RevisionAdministrativa, opcional
    _texto("revision_resultado"), _importe("revision_pagos_realizados"), _importe("revision_saldo_pendiente"),
    sa.Column("revision_politica_incluida", sa.Boolean), sa.Column("revision_constancia_no_reembolso", sa.Boolean),
    _fecha("revision_fecha"),
    sa.PrimaryKeyConstraint("evento_id"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoEvento), name="estado_valido"),
    sa.CheckConstraint("invitados_aproximados > 0", name="invitados_positivo"),               # DatosEvento (CA-003)
    sa.CheckConstraint("tipo <> '' AND lugar <> ''", name="datos_no_vacios"),                  # DatosEvento: «not tipo or not lugar» (CA-003)
    sa.CheckConstraint(_todo_o_nada("motivo_cancelacion_origen", "motivo_cancelacion_descripcion",
                                    "motivo_cancelacion_fecha", "motivo_cancelacion_registrado_por"),
                       name="motivo_cancelacion_completo"),
    sa.CheckConstraint("motivo_cancelacion_origen IS NULL OR " + _en_enum("motivo_cancelacion_origen", V.OrigenCancelacion),
                       name="motivo_cancelacion_origen_valido"),
    sa.CheckConstraint(_todo_o_nada("revision_resultado", "revision_pagos_realizados", "revision_saldo_pendiente",
                                    "revision_politica_incluida", "revision_constancia_no_reembolso", "revision_fecha"),
                       name="revision_completa"),
    sa.CheckConstraint("(" + _importe_valido("revision_pagos_realizados", anulable=True) + ") AND (" +
                       _importe_valido("revision_saldo_pendiente", anulable=True) + ")", name="revision_importes_validos"),
)
sa.Index("ix_evento_fecha_hora", evento.c.fecha_hora)       # ConsultarEventosProximosHandler: ventana [desde, hasta] sin filtrar por estado

evento_servicio_contratado = sa.Table(
    "evento_servicio_contratado", metadata,
    _texto("evento_id", nullable=False), _texto("servicio_contratado_id", nullable=False), _posicion(),
    _texto("servicio", nullable=False), _texto("proveedor_id"), _texto("condiciones", nullable=False),
    _estado(V.EstadoServicioContratado, nullable=False),
    sa.PrimaryKeyConstraint("evento_id", "servicio_contratado_id"),
    sa.ForeignKeyConstraint(["evento_id"], ["evento.evento_id"], ondelete="CASCADE"),
    sa.UniqueConstraint("evento_id", "posicion"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoServicioContratado), name="estado_valido"),
)
sa.Index("ix_evento_servicio_contratado_proveedor_id", evento_servicio_contratado.c.proveedor_id)

evento_solicitud_cancelacion = sa.Table(
    "evento_solicitud_cancelacion", metadata,
    _texto("evento_id", nullable=False), _posicion(), _fecha("fecha", nullable=False), _texto("motivo", nullable=False),
    _estado(V.EstadoSolicitudCancelacion, nullable=False),
    sa.PrimaryKeyConstraint("evento_id", "posicion"),
    sa.ForeignKeyConstraint(["evento_id"], ["evento.evento_id"], ondelete="CASCADE"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoSolicitudCancelacion), name="estado_valido"),
)

evento_operacion_aplicada = sa.Table(
    "evento_operacion_aplicada", metadata,                 # Evento._operaciones_aplicadas: idempotencia de las reacciones
    _texto("evento_id", nullable=False), _texto("operacion_id", nullable=False),
    sa.PrimaryKeyConstraint("evento_id", "operacion_id"),
    sa.ForeignKeyConstraint(["evento_id"], ["evento.evento_id"], ondelete="CASCADE"),
)

# ================================================================ SolicitudCambio
solicitud_cambio = sa.Table(
    "solicitud_cambio", metadata,
    _texto("solicitud_id", nullable=False), *_solicitud_base("solicitud_cambio"),
    _estado(V.EstadoSolicitudCambio, nullable=False), _estado(V.EstadoSolicitudCambio, "estado_antes_de_detener"),
    _texto("descripcion", nullable=False),
    # AnticipacionSolicitud y TarifaCargoTardio
    _fecha("anticipacion_fecha_solicitud", nullable=False), _fecha("anticipacion_fecha_evento", nullable=False),
    _importe("tarifa_importe", nullable=False),
    # datos_propuestos: DatosEvento opcional
    _texto("datos_propuestos_tipo"), _fecha("datos_propuestos_fecha_hora"), _texto("datos_propuestos_lugar"),
    sa.Column("datos_propuestos_invitados", sa.BigInteger),
    # viabilidad: ResultadoViabilidad opcional; impacto: ImpactoModificacion opcional
    sa.Column("viabilidad_viable", sa.Boolean), _texto("viabilidad_motivo"), *_impacto("impacto"),
    _importe("costo_proveedor"),
    *_decision("decision_cliente"), *_decision("autorizacion"),
    sa.Column("importes_por_pagar", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.PrimaryKeyConstraint("solicitud_id"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoSolicitudCambio), name="estado_valido"),
    sa.CheckConstraint("estado_antes_de_detener IS NULL OR " + _en_enum("estado_antes_de_detener", V.EstadoSolicitudCambio),
                       name="estado_antes_de_detener_valido"),
    sa.CheckConstraint(_todo_o_nada("datos_propuestos_tipo", "datos_propuestos_fecha_hora", "datos_propuestos_lugar",
                                    "datos_propuestos_invitados"), name="datos_propuestos_completos"),
    sa.CheckConstraint("datos_propuestos_invitados IS NULL OR datos_propuestos_invitados > 0", name="datos_propuestos_invitados_positivo"),
    sa.CheckConstraint(_todo_o_nada("viabilidad_viable", "viabilidad_motivo"), name="viabilidad_completa"),
    sa.CheckConstraint("datos_propuestos_tipo IS NULL OR (datos_propuestos_tipo <> '' AND datos_propuestos_lugar <> '')",
                       name="datos_propuestos_no_vacios"),
    sa.CheckConstraint("(" + _importe_valido("tarifa_importe") + ") AND (" +
                       _importe_valido("costo_proveedor", anulable=True) + ")", name="importes_validos"),
)
sa.Index("ix_solicitud_cambio_evento_id_estado", solicitud_cambio.c.evento_id, solicitud_cambio.c.estado)

solicitud_cambio_condicion = sa.Table(
    "solicitud_cambio_condicion", metadata,                # condiciones_propuestas: {servicio_contratado_id: CondicionesServicio}
    _texto("solicitud_id", nullable=False), _texto("servicio_contratado_id", nullable=False), _posicion(),
    _texto("condiciones", nullable=False),
    sa.PrimaryKeyConstraint("solicitud_id", "servicio_contratado_id"),
    sa.ForeignKeyConstraint(["solicitud_id"], ["solicitud_cambio.solicitud_id"], ondelete="CASCADE"),
    sa.UniqueConstraint("solicitud_id", "posicion"),
)

# ================================================================ SolicitudServicioAdicional
solicitud_servicio_adicional = sa.Table(
    "solicitud_servicio_adicional", metadata,
    _texto("solicitud_id", nullable=False), *_solicitud_base("solicitud_servicio_adicional"),
    _estado(V.EstadoSolicitudServicioAdicional, nullable=False), _estado(V.EstadoSolicitudServicioAdicional, "estado_antes_de_detener"),
    _texto("servicio", nullable=False),
    _fecha("anticipacion_fecha_solicitud", nullable=False), _fecha("anticipacion_fecha_evento", nullable=False),
    sa.Column("elegibilidad_obtenida", sa.Boolean, nullable=False, server_default=sa.false()),    # SE-004, CA-080
    *_disponibilidad("disponibilidad"),
    *_decision("decision_cliente"), *_decision("autorizacion"),
    sa.PrimaryKeyConstraint("solicitud_id"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoSolicitudServicioAdicional), name="estado_valido"),
    sa.CheckConstraint("estado_antes_de_detener IS NULL OR " + _en_enum("estado_antes_de_detener", V.EstadoSolicitudServicioAdicional),
                       name="estado_antes_de_detener_valido"),
)
sa.Index("ix_solicitud_servicio_adicional_evento_id_estado", solicitud_servicio_adicional.c.evento_id, solicitud_servicio_adicional.c.estado)

# ================================================================ SustitucionProveedor
sustitucion_proveedor = sa.Table(
    "sustitucion_proveedor", metadata,
    _texto("sustitucion_id", nullable=False), *_solicitud_base("sustitucion_proveedor"),
    _estado(V.EstadoSustitucionProveedor, nullable=False), _estado(V.EstadoSustitucionProveedor, "estado_antes_de_detener"),
    # Anulable (revisión 0002): el servicio puede no tener proveedor asignado cuando se registra la sustitución (Evento.servicios).
    _texto("servicio_contratado_id", nullable=False), _texto("proveedor_original_id"),
    _importe("costo_adicional"),
    sa.Column("aprobada_despues_del_limite", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.PrimaryKeyConstraint("sustitucion_id"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoSustitucionProveedor), name="estado_valido"),
    sa.CheckConstraint("estado_antes_de_detener IS NULL OR " + _en_enum("estado_antes_de_detener", V.EstadoSustitucionProveedor),
                       name="estado_antes_de_detener_valido"),
    sa.CheckConstraint(_importe_valido("costo_adicional", anulable=True), name="costo_adicional_valido"),
)
sa.Index("ix_sustitucion_proveedor_evento_id_estado", sustitucion_proveedor.c.evento_id, sustitucion_proveedor.c.estado)

sustitucion_alternativa = sa.Table(
    "sustitucion_alternativa", metadata,                   # AlternativaPropuesta; la vigente es la de mayor posición
    _texto("sustitucion_id", nullable=False), _posicion(), _texto("proveedor_id", nullable=False),
    *_disponibilidad("disponibilidad"),
    sa.Column("impacto_afecta_servicios", sa.Boolean, nullable=False),
    sa.Column("impacto_afecta_costos", sa.Boolean, nullable=False),
    sa.Column("impacto_afecta_condiciones", sa.Boolean, nullable=False),
    *_decision("decision_cliente"), *_decision("autorizacion"),
    sa.PrimaryKeyConstraint("sustitucion_id", "posicion"),
    sa.ForeignKeyConstraint(["sustitucion_id"], ["sustitucion_proveedor.sustitucion_id"], ondelete="CASCADE"),
    sa.CheckConstraint("disponibilidad_proveedor_id IS NOT NULL AND disponibilidad_disponible IS NOT NULL",
                       name="disponibilidad_informada"),
)

# ================================================================ EstadoCuenta
estado_cuenta = sa.Table(
    "estado_cuenta", metadata,
    _texto("estado_cuenta_id", nullable=False), _texto("contrato_id", nullable=False), _texto("evento_id", nullable=False),
    _texto("resultado_regularizacion"), _fecha("fecha_resultado_regularizacion"),
    _texto("ventana_resuelta_obligacion_id"),             # EstadoCuenta._ventana_resuelta (privado, necesario para rehidratar)
    _fecha("cierre_contratacion"),                        # decisión A: cierre de la contratación sin confirmar (revisión 0003)
    sa.PrimaryKeyConstraint("estado_cuenta_id"),
    sa.UniqueConstraint("contrato_id"),                   # «Un EstadoCuenta por contrato» (decisión arquitectónica documentada)
    sa.UniqueConstraint("estado_cuenta_id", "contrato_id"),   # destino de la FK compuesta de las solicitudes
    # registrar_obligacion_anticipo crea EstadoCuenta(id, contrato_id, c.evento_id): contrato y evento del mismo contrato.
    sa.ForeignKeyConstraint(["contrato_id", "evento_id"], ["contrato.contrato_id", "contrato.evento_id"],
                            name="fk_estado_cuenta_contrato"),
    sa.CheckConstraint("resultado_regularizacion IS NULL OR resultado_regularizacion IN ('Regularizado', 'No regularizado')",
                       name="resultado_regularizacion_valido"),
)
sa.Index("ix_estado_cuenta_evento_id", estado_cuenta.c.evento_id)

estado_cuenta_seguimiento_cobro = sa.Table(
    "estado_cuenta_seguimiento_cobro", metadata,
    _texto("estado_cuenta_id", nullable=False), _posicion(), _texto("seguimiento", nullable=False),
    sa.PrimaryKeyConstraint("estado_cuenta_id", "posicion"),
    sa.ForeignKeyConstraint(["estado_cuenta_id"], ["estado_cuenta.estado_cuenta_id"], ondelete="CASCADE",
                            name="fk_ec_seguimiento_cobro_estado_cuenta"),
)

estado_cuenta_cierre_sin_realizar = sa.Table(
    "estado_cuenta_cierre_sin_realizar", metadata,         # EstadoCuenta._cierres_sin_realizar (H-09), privado
    _texto("estado_cuenta_id", nullable=False), _texto("origen_id", nullable=False), _fecha("fecha_cierre", nullable=False),
    sa.Column("evento_cancelado", sa.Boolean, nullable=False),
    sa.PrimaryKeyConstraint("estado_cuenta_id", "origen_id"),
    sa.ForeignKeyConstraint(["estado_cuenta_id"], ["estado_cuenta.estado_cuenta_id"], ondelete="CASCADE",
                            name="fk_ec_cierre_sin_realizar_estado_cuenta"),
)

obligacion_pago = sa.Table(
    "obligacion_pago", metadata,
    _texto("estado_cuenta_id", nullable=False), _texto("obligacion_id", nullable=False), _posicion(),
    sa.Column("concepto", sa.String(40), nullable=False), _importe("importe", nullable=False),
    # PlazoPago(inicio, vence), opcional: la sustitución aprobada después del límite no tiene plazo (CA-052)
    _fecha("plazo_inicio"), _fecha("plazo_vence"), _texto("origen_id", nullable=False),
    _estado(V.EstadoObligacionPago, nullable=False),
    sa.PrimaryKeyConstraint("estado_cuenta_id", "obligacion_id"),
    sa.ForeignKeyConstraint(["estado_cuenta_id"], ["estado_cuenta.estado_cuenta_id"], ondelete="CASCADE"),
    sa.UniqueConstraint("estado_cuenta_id", "concepto", "origen_id"),       # EstadoCuenta._crear: idempotencia por concepto y origen
    sa.UniqueConstraint("estado_cuenta_id", "posicion"),
    sa.CheckConstraint(_en_enum("concepto", V.ConceptoPago), name="concepto_valido"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoObligacionPago), name="estado_valido"),
    sa.CheckConstraint(_importe_valido("importe"), name="importe_valido"),
    sa.CheckConstraint(_todo_o_nada("plazo_inicio", "plazo_vence"), name="plazo_completo"),
)
sa.Index("ix_obligacion_pago_abiertas", obligacion_pago.c.estado, obligacion_pago.c.plazo_vence,
         postgresql_where=sa.text("estado IN ('PENDIENTE', 'VENCIDA')"))        # ConsultarPagosPendientesHandler

pago = sa.Table(
    "pago", metadata,
    _texto("estado_cuenta_id", nullable=False), _texto("pago_id", nullable=False), _posicion(),
    _texto("obligacion_id", nullable=False), _importe("importe", nullable=False), _fecha("fecha", nullable=False),
    _texto("comprobante", nullable=False), _estado(V.EstadoPago, nullable=False),
    _fecha("registrado_en"), _fecha("verificado_en"),
    sa.PrimaryKeyConstraint("estado_cuenta_id", "pago_id"),
    sa.ForeignKeyConstraint(["estado_cuenta_id", "obligacion_id"],
                            ["obligacion_pago.estado_cuenta_id", "obligacion_pago.obligacion_id"], ondelete="CASCADE"),
    sa.UniqueConstraint("estado_cuenta_id", "posicion"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoPago), name="estado_valido"),
    sa.CheckConstraint(_importe_valido("importe"), name="importe_valido"),
)
sa.Index("ix_pago_estado_cuenta_id_obligacion_id", pago.c.estado_cuenta_id, pago.c.obligacion_id)

devolucion = sa.Table(
    "devolucion", metadata,                                # fecha_limite se calcula (sumar_dias_habiles): no se persiste
    _texto("estado_cuenta_id", nullable=False), _texto("devolucion_id", nullable=False), _posicion(),
    _texto("solicitud_id"), sa.Column("concepto", sa.String(40), nullable=False),
    _importe("importe", nullable=False), _texto("motivo_devolucion", nullable=False), _fecha("fecha_cierre", nullable=False),
    _estado(V.EstadoDevolucion, nullable=False), _fecha("fecha_devolucion"), _texto("comprobante"),
    # Revisión 0003 (decisión A): la devolución del anticipo nace de un pago, no de una solicitud.
    sa.Column("tipo", sa.String(40), nullable=False, server_default=V.TipoDevolucion.SOLICITUD_NO_REALIZADA.name),
    _texto("pago_id"), _fecha("fecha_referencia"),
    sa.PrimaryKeyConstraint("estado_cuenta_id", "devolucion_id"),
    sa.ForeignKeyConstraint(["estado_cuenta_id"], ["estado_cuenta.estado_cuenta_id"], ondelete="CASCADE"),
    sa.UniqueConstraint("estado_cuenta_id", "posicion"),
    sa.CheckConstraint(_en_enum("concepto", V.ConceptoPago), name="concepto_valido"),
    sa.CheckConstraint(_en_enum("estado", V.EstadoDevolucion), name="estado_valido"),
    sa.CheckConstraint(_importe_valido("importe"), name="importe_valido"),
    sa.CheckConstraint(_en_enum("tipo", V.TipoDevolucion), name="tipo_valido"),
    sa.CheckConstraint("(tipo = 'SOLICITUD_NO_REALIZADA' AND solicitud_id IS NOT NULL) OR "
                       "(tipo = 'ANTICIPO_CONTRATACION_CERRADA' AND pago_id IS NOT NULL AND fecha_referencia IS NOT NULL "
                       "AND concepto = 'ANTICIPO')", name="origen_segun_tipo"),
)
sa.Index("uq_devolucion_pago", devolucion.c.estado_cuenta_id, devolucion.c.pago_id, unique=True,
         postgresql_where=sa.text("pago_id IS NOT NULL"))            # un pago genera como máximo una devolución (C-11)
sa.Index("ix_devolucion_pendientes", devolucion.c.fecha_cierre,
         postgresql_where=sa.text("estado = 'PENDIENTE'"))                      # ConsultarDevolucionesPendientesHandler

# ================================================================ Catálogo de proveedores (revisión 0005)
# Registro de referencia (no es una raíz de agregado: sin versión ni Outbox). `evento_servicio_contratado.proveedor_id` sigue siendo
# una referencia blanda: no se añade clave foránea para no invalidar las filas existentes ni los identificadores históricos.
proveedor = sa.Table(
    "proveedor", metadata,
    _texto("proveedor_id", nullable=False), _texto("nombre", nullable=False), _texto("nombre_normalizado", nullable=False),
    sa.Column("servicios", pg.ARRAY(sa.Text), nullable=False, server_default="{}"),
    _texto("contacto", nullable=False, server_default=""), _fecha("registrado_en", nullable=False),
    sa.PrimaryKeyConstraint("proveedor_id"),
    sa.UniqueConstraint("nombre_normalizado"),                      # no hay dos proveedores con el mismo nombre (sin acentos ni mayúsculas)
    sa.CheckConstraint("btrim(nombre) <> ''", name="nombre_no_vacio"),
)

# ================================================================ Seguridad: cuentas, sesiones e intentos (revisión 0006)
# Contraseñas solo como hash Argon2id; sesiones solo como SHA-256 del token. `usuario.proveedor_id` es una clave foránea a `proveedor`
# (solo para el rol proveedor); `sesion` se borra con su cuenta. Ninguna tabla existente cambia.
usuario = sa.Table(
    "usuario", metadata,
    _texto("usuario_id", nullable=False), _texto("correo", nullable=False), _texto("nombre", nullable=False),
    _texto("rol", nullable=False), _texto("contrasena_hash", nullable=False), sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
    _texto("proveedor_id"), _fecha("creado_en", nullable=False), _fecha("ultimo_acceso"),
    sa.PrimaryKeyConstraint("usuario_id"),
    sa.UniqueConstraint("correo"),
    sa.ForeignKeyConstraint(["proveedor_id"], ["proveedor.proveedor_id"]),
    sa.CheckConstraint("rol IN ('administrador', 'coordinador', 'proveedor')", name="rol_valido"),
    sa.CheckConstraint("(rol = 'proveedor') = (proveedor_id IS NOT NULL)", name="proveedor_solo_si_rol_proveedor"),
    sa.CheckConstraint("correo = lower(correo) AND correo <> ''", name="correo_normalizado"),
)

sesion = sa.Table(
    "sesion", metadata,
    _texto("sesion_hash", nullable=False), _texto("usuario_id", nullable=False), _texto("csrf", nullable=False),
    _fecha("creada_en", nullable=False), _fecha("ultima_actividad", nullable=False), _fecha("expira_en", nullable=False), _fecha("revocada_en"),
    sa.PrimaryKeyConstraint("sesion_hash"),
    sa.ForeignKeyConstraint(["usuario_id"], ["usuario.usuario_id"], ondelete="CASCADE"),
)
sa.Index("ix_sesion_usuario_id", sesion.c.usuario_id)

intento_acceso = sa.Table(
    "intento_acceso", metadata,
    _texto("clave", nullable=False), sa.Column("fallos", sa.BigInteger, nullable=False), _fecha("primer_fallo", nullable=False), _fecha("bloqueado_hasta"),
    sa.PrimaryKeyConstraint("clave"),
    sa.CheckConstraint("fallos >= 0", name="fallos_no_negativos"),
)

# ================================================================ Outbox (ADR-004)
outbox_evento = sa.Table(
    "outbox_evento", metadata,
    sa.Column("secuencia", sa.BigInteger, sa.Identity(always=True), nullable=False),     # orden de despacho
    _texto("evento_id", nullable=False),                                                   # EventoDominio.evento_id
    _texto("tipo_evento", nullable=False),                                                 # nombre de la clase del evento
    _texto("agregado_id", nullable=False), _fecha("ocurrido_en", nullable=False),
    sa.Column("datos", pg.JSONB, nullable=False),                                          # campos propios del evento
    sa.Column("estado", sa.String(20), nullable=False, server_default="PENDIENTE"),
    sa.Column("intentos", sa.Integer, nullable=False, server_default="0"), _texto("error", nullable=False, server_default=""),
    sa.PrimaryKeyConstraint("secuencia"),
    sa.UniqueConstraint("evento_id"),
    sa.CheckConstraint("estado IN (" + ", ".join(f"'{e}'" for e in ESTADOS_OUTBOX) + ")", name="estado_valido"),
    sa.CheckConstraint("intentos >= 0", name="intentos_no_negativos"),
    sa.CheckConstraint("jsonb_typeof(datos) = 'object'", name="datos_es_objeto"),
)
sa.Index("ix_outbox_evento_pendientes", outbox_evento.c.secuencia, postgresql_where=sa.text("estado = 'PENDIENTE'"))

outbox_reaccion = sa.Table(
    "outbox_reaccion", metadata,                           # parejas (evento, reacción) ya ejecutadas: RegistroOutbox.reacciones_procesadas
    _texto("evento_id", nullable=False), _texto("clave_reaccion", nullable=False), _fecha("procesada_en", nullable=False),
    sa.PrimaryKeyConstraint("evento_id", "clave_reaccion"),
    sa.ForeignKeyConstraint(["evento_id"], ["outbox_evento.evento_id"], ondelete="CASCADE"),
)

# ================================================================ Control de concurrencia optimista (revisión 0004)
# Cada raíz de agregado lleva una versión: el repositorio SQL guarda con `UPDATE ... WHERE version = <leída>` y falla si otra
# transacción la cambió antes (ConflictoDeConcurrencia). Las filas hijas pertenecen a su raíz y se protegen con ella.
RAICES_VERSIONADAS = ("propuesta", "contrato", "evento", "solicitud_cambio", "solicitud_servicio_adicional",
                      "sustitucion_proveedor", "estado_cuenta")
for _nombre in RAICES_VERSIONADAS:
    _raiz = metadata.tables[_nombre]
    _raiz.append_column(_version())
    _raiz.append_constraint(sa.CheckConstraint("version >= 0", name="version_no_negativa"))
