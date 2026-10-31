"""Esquema relacional inicial de Eventos Nova (22 tablas).

Crea las tablas, claves, restricciones e índices diseñados en docs/architecture/esquema-relacional-postgresql.md.
Es explícita: no importa los metadatos del proyecto, de modo que la migración no cambia aunque el código evolucione.
PROPUESTA: revisar antes de aplicar (no se ha ejecutado contra PostgreSQL).

Revision ID: 0001
Revises:
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('evento',
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('cliente_id', sa.Text(), nullable=False),
        sa.Column('tipo', sa.Text(), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(), nullable=False),
        sa.Column('lugar', sa.Text(), nullable=False),
        sa.Column('invitados_aproximados', sa.BigInteger(), nullable=False),
        sa.Column('servicios_solicitados', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('fecha_inicio', sa.DateTime(), nullable=True),
        sa.Column('fecha_finalizacion', sa.DateTime(), nullable=True),
        sa.Column('motivo_cancelacion_origen', sa.String(length=40), nullable=True),
        sa.Column('motivo_cancelacion_descripcion', sa.Text(), nullable=True),
        sa.Column('motivo_cancelacion_fecha', sa.DateTime(), nullable=True),
        sa.Column('motivo_cancelacion_registrado_por', sa.Text(), nullable=True),
        sa.Column('revision_resultado', sa.Text(), nullable=True),
        sa.Column('revision_pagos_realizados', sa.Numeric(), nullable=True),
        sa.Column('revision_saldo_pendiente', sa.Numeric(), nullable=True),
        sa.Column('revision_politica_incluida', sa.Boolean(), nullable=True),
        sa.Column('revision_constancia_no_reembolso', sa.Boolean(), nullable=True),
        sa.Column('revision_fecha', sa.DateTime(), nullable=True),
        sa.CheckConstraint("(revision_pagos_realizados IS NULL OR (revision_pagos_realizados >= 0 AND revision_pagos_realizados <> 'NaN' AND revision_pagos_realizados <> 'Infinity')) AND (revision_saldo_pendiente IS NULL OR (revision_saldo_pendiente >= 0 AND revision_saldo_pendiente <> 'NaN' AND revision_saldo_pendiente <> 'Infinity'))", name=op.f('ck_evento_revision_importes_validos')),
        sa.CheckConstraint("estado IN ('EN_GESTION', 'EN_ORGANIZACION', 'EN_EJECUCION', 'FINALIZADO', 'CANCELADO', 'CERRADO_SIN_CONTRATACION')", name=op.f('ck_evento_estado_valido')),
        sa.CheckConstraint("motivo_cancelacion_origen IS NULL OR motivo_cancelacion_origen IN ('SOLICITUD_CLIENTE', 'FALTA_REGULARIZACION')", name=op.f('ck_evento_motivo_cancelacion_origen_valido')),
        sa.CheckConstraint("tipo <> '' AND lugar <> ''", name=op.f('ck_evento_datos_no_vacios')),
        sa.CheckConstraint('(motivo_cancelacion_origen IS NULL AND motivo_cancelacion_descripcion IS NULL AND motivo_cancelacion_fecha IS NULL AND motivo_cancelacion_registrado_por IS NULL) OR (motivo_cancelacion_origen IS NOT NULL AND motivo_cancelacion_descripcion IS NOT NULL AND motivo_cancelacion_fecha IS NOT NULL AND motivo_cancelacion_registrado_por IS NOT NULL)', name=op.f('ck_evento_motivo_cancelacion_completo')),
        sa.CheckConstraint('(revision_resultado IS NULL AND revision_pagos_realizados IS NULL AND revision_saldo_pendiente IS NULL AND revision_politica_incluida IS NULL AND revision_constancia_no_reembolso IS NULL AND revision_fecha IS NULL) OR (revision_resultado IS NOT NULL AND revision_pagos_realizados IS NOT NULL AND revision_saldo_pendiente IS NOT NULL AND revision_politica_incluida IS NOT NULL AND revision_constancia_no_reembolso IS NOT NULL AND revision_fecha IS NOT NULL)', name=op.f('ck_evento_revision_completa')),
        sa.CheckConstraint('invitados_aproximados > 0', name=op.f('ck_evento_invitados_positivo')),
        sa.PrimaryKeyConstraint('evento_id', name=op.f('pk_evento'))
    )
    op.create_index('ix_evento_fecha_hora', 'evento', ['fecha_hora'], unique=False)
    op.create_table('outbox_evento',
        sa.Column('secuencia', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('tipo_evento', sa.Text(), nullable=False),
        sa.Column('agregado_id', sa.Text(), nullable=False),
        sa.Column('ocurrido_en', sa.DateTime(), nullable=False),
        sa.Column('datos', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('estado', sa.String(length=20), server_default='PENDIENTE', nullable=False),
        sa.Column('intentos', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error', sa.Text(), server_default='', nullable=False),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'PROCESADO', 'REVISION')", name=op.f('ck_outbox_evento_estado_valido')),
        sa.CheckConstraint("jsonb_typeof(datos) = 'object'", name=op.f('ck_outbox_evento_datos_es_objeto')),
        sa.CheckConstraint('intentos >= 0', name=op.f('ck_outbox_evento_intentos_no_negativos')),
        sa.PrimaryKeyConstraint('secuencia', name=op.f('pk_outbox_evento')),
        sa.UniqueConstraint('evento_id', name=op.f('uq_outbox_evento_evento_id'))
    )
    op.create_index('ix_outbox_evento_pendientes', 'outbox_evento', ['secuencia'], unique=False, postgresql_where=sa.text("estado = 'PENDIENTE'"))
    op.create_table('evento_operacion_aplicada',
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('operacion_id', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name=op.f('fk_evento_operacion_aplicada_evento_id_evento'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('evento_id', 'operacion_id', name=op.f('pk_evento_operacion_aplicada'))
    )
    op.create_table('evento_servicio_contratado',
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('servicio_contratado_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('servicio', sa.Text(), nullable=False),
        sa.Column('proveedor_id', sa.Text(), nullable=True),
        sa.Column('condiciones', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.CheckConstraint("estado IN ('SIN_PROVEEDOR', 'PENDIENTE_CONFIRMACION', 'CONFIRMADO', 'PROVEEDOR_NO_DISPONIBLE')", name=op.f('ck_evento_servicio_contratado_estado_valido')),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name=op.f('fk_evento_servicio_contratado_evento_id_evento'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('evento_id', 'servicio_contratado_id', name=op.f('pk_evento_servicio_contratado')),
        sa.UniqueConstraint('evento_id', 'posicion', name=op.f('uq_evento_servicio_contratado_evento_id_posicion'))
    )
    op.create_index('ix_evento_servicio_contratado_proveedor_id', 'evento_servicio_contratado', ['proveedor_id'], unique=False)
    op.create_table('evento_solicitud_cancelacion',
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.CheckConstraint("estado IN ('REGISTRADA', 'PROCEDENTE', 'RECHAZADA_INICIO_EVENTO')", name=op.f('ck_evento_solicitud_cancelacion_estado_valido')),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name=op.f('fk_evento_solicitud_cancelacion_evento_id_evento'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('evento_id', 'posicion', name=op.f('pk_evento_solicitud_cancelacion'))
    )
    op.create_table('outbox_reaccion',
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('clave_reaccion', sa.Text(), nullable=False),
        sa.Column('procesada_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['evento_id'], ['outbox_evento.evento_id'], name=op.f('fk_outbox_reaccion_evento_id_outbox_evento'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('evento_id', 'clave_reaccion', name=op.f('pk_outbox_reaccion'))
    )
    op.create_table('propuesta',
        sa.Column('propuesta_id', sa.Text(), nullable=False),
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('cliente_id', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('version_vigente_id', sa.Text(), nullable=False),
        sa.Column('motivo_cierre', sa.Text(), nullable=True),
        sa.CheckConstraint("estado IN ('EN_ELABORACION', 'EN_REVISION_CLIENTE', 'ACEPTADA', 'CERRADA_NO_ACEPTACION')", name=op.f('ck_propuesta_estado_valido')),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name=op.f('fk_propuesta_evento_id_evento')),
        sa.PrimaryKeyConstraint('propuesta_id', name=op.f('pk_propuesta'))
    )
    op.create_index('ix_propuesta_evento_id', 'propuesta', ['evento_id'], unique=False)
    op.create_table('version_propuesta',
        sa.Column('version_id', sa.Text(), nullable=False),
        sa.Column('propuesta_id', sa.Text(), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('fecha_actualizacion', sa.DateTime(), nullable=False),
        sa.Column('servicios', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('proveedores_considerados', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('costo_total', sa.Numeric(), nullable=False),
        sa.Column('condiciones', sa.Text(), nullable=False),
        sa.CheckConstraint("cardinality(servicios) > 0 AND condiciones <> ''", name=op.f('ck_version_propuesta_contenido_completo')),
        sa.CheckConstraint("costo_total >= 0 AND costo_total <> 'NaN' AND costo_total <> 'Infinity'", name=op.f('ck_version_propuesta_costo_total_valido')),
        sa.CheckConstraint('numero >= 1', name=op.f('ck_version_propuesta_numero_positivo')),
        sa.ForeignKeyConstraint(['propuesta_id'], ['propuesta.propuesta_id'], name=op.f('fk_version_propuesta_propuesta_id_propuesta'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('version_id', name=op.f('pk_version_propuesta')),
        sa.UniqueConstraint('propuesta_id', 'numero', name=op.f('uq_version_propuesta_propuesta_id_numero')),
        sa.UniqueConstraint('propuesta_id', 'version_id', name=op.f('uq_version_propuesta_propuesta_id_version_id'))
    )
    op.create_table('contrato',
        sa.Column('contrato_id', sa.Text(), nullable=False),
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('propuesta_id', sa.Text(), nullable=False),
        sa.Column('version_aceptada_id', sa.Text(), nullable=False),
        sa.Column('servicios', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('costo_total', sa.Numeric(), nullable=False),
        sa.Column('condiciones', sa.Text(), nullable=False),
        sa.Column('politica_incluida', sa.Boolean(), nullable=False),
        sa.Column('politica_comunicada_en', sa.DateTime(), nullable=True),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('fecha_firma', sa.DateTime(), nullable=True),
        sa.CheckConstraint("costo_total >= 0 AND costo_total <> 'NaN' AND costo_total <> 'Infinity'", name=op.f('ck_contrato_costo_total_valido')),
        sa.CheckConstraint("estado IN ('EN_PREPARACION', 'FIRMADO', 'CONTRATACION_CONFIRMADA', 'CERRADO_SIN_CONFIRMAR')", name=op.f('ck_contrato_estado_valido')),
        sa.CheckConstraint('(politica_comunicada_en IS NULL) OR politica_incluida', name=op.f('ck_contrato_comunicacion_requiere_politica')),
        sa.CheckConstraint('politica_incluida', name=op.f('ck_contrato_politica_incluida')),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name=op.f('fk_contrato_evento_id_evento')),
        sa.ForeignKeyConstraint(['propuesta_id', 'version_aceptada_id'], ['version_propuesta.propuesta_id', 'version_propuesta.version_id'], name='fk_contrato_version_aceptada'),
        sa.PrimaryKeyConstraint('contrato_id', name=op.f('pk_contrato')),
        sa.UniqueConstraint('contrato_id', 'evento_id', name=op.f('uq_contrato_contrato_id_evento_id'))
    )
    op.create_index('ix_contrato_evento_id', 'contrato', ['evento_id'], unique=False)
    op.create_table('contrato_anexo',
        sa.Column('anexo_id', sa.Text(), nullable=False),
        sa.Column('contrato_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('tipo_origen', sa.String(length=40), nullable=False),
        sa.Column('origen_id', sa.Text(), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.CheckConstraint("tipo_origen IN ('CAMBIO', 'SERVICIO_ADICIONAL', 'SUSTITUCION_PROVEEDOR')", name=op.f('ck_contrato_anexo_tipo_origen_valido')),
        sa.ForeignKeyConstraint(['contrato_id'], ['contrato.contrato_id'], name=op.f('fk_contrato_anexo_contrato_id_contrato'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('anexo_id', name=op.f('pk_contrato_anexo')),
        sa.UniqueConstraint('contrato_id', 'origen_id', name=op.f('uq_contrato_anexo_contrato_id_origen_id')),
        sa.UniqueConstraint('contrato_id', 'posicion', name=op.f('uq_contrato_anexo_contrato_id_posicion'))
    )
    op.create_table('contrato_seguimiento_anticipo',
        sa.Column('contrato_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.Column('resultado', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['contrato_id'], ['contrato.contrato_id'], name=op.f('fk_contrato_seguimiento_anticipo_contrato_id_contrato'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('contrato_id', 'posicion', name=op.f('pk_contrato_seguimiento_anticipo'))
    )
    op.create_table('estado_cuenta',
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('contrato_id', sa.Text(), nullable=False),
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('resultado_regularizacion', sa.Text(), nullable=True),
        sa.Column('fecha_resultado_regularizacion', sa.DateTime(), nullable=True),
        sa.Column('ventana_resuelta_obligacion_id', sa.Text(), nullable=True),
        sa.CheckConstraint("resultado_regularizacion IS NULL OR resultado_regularizacion IN ('Regularizado', 'No regularizado')", name=op.f('ck_estado_cuenta_resultado_regularizacion_valido')),
        sa.ForeignKeyConstraint(['contrato_id', 'evento_id'], ['contrato.contrato_id', 'contrato.evento_id'], name='fk_estado_cuenta_contrato'),
        sa.PrimaryKeyConstraint('estado_cuenta_id', name=op.f('pk_estado_cuenta')),
        sa.UniqueConstraint('contrato_id', name=op.f('uq_estado_cuenta_contrato_id')),
        sa.UniqueConstraint('estado_cuenta_id', 'contrato_id', name=op.f('uq_estado_cuenta_estado_cuenta_id_contrato_id'))
    )
    op.create_index('ix_estado_cuenta_evento_id', 'estado_cuenta', ['evento_id'], unique=False)
    op.create_table('devolucion',
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('devolucion_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('solicitud_id', sa.Text(), nullable=False),
        sa.Column('concepto', sa.String(length=40), nullable=False),
        sa.Column('importe', sa.Numeric(), nullable=False),
        sa.Column('motivo_devolucion', sa.Text(), nullable=False),
        sa.Column('fecha_cierre', sa.DateTime(), nullable=False),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('fecha_devolucion', sa.DateTime(), nullable=True),
        sa.Column('comprobante', sa.Text(), nullable=True),
        sa.CheckConstraint("concepto IN ('ANTICIPO', 'SALDO_CONTRATO_ORIGINAL', 'SUSTITUCION_PROVEEDOR', 'CAMBIO', 'CARGO_CAMBIO_TARDIO', 'CARGOS_MORATORIOS', 'SERVICIO_ADICIONAL')", name=op.f('ck_devolucion_concepto_valido')),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'EFECTUADA')", name=op.f('ck_devolucion_estado_valido')),
        sa.CheckConstraint("importe >= 0 AND importe <> 'NaN' AND importe <> 'Infinity'", name=op.f('ck_devolucion_importe_valido')),
        sa.ForeignKeyConstraint(['estado_cuenta_id'], ['estado_cuenta.estado_cuenta_id'], name=op.f('fk_devolucion_estado_cuenta_id_estado_cuenta'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('estado_cuenta_id', 'devolucion_id', name=op.f('pk_devolucion')),
        sa.UniqueConstraint('estado_cuenta_id', 'posicion', name=op.f('uq_devolucion_estado_cuenta_id_posicion'))
    )
    op.create_index('ix_devolucion_pendientes', 'devolucion', ['fecha_cierre'], unique=False, postgresql_where=sa.text("estado = 'PENDIENTE'"))
    op.create_table('estado_cuenta_cierre_sin_realizar',
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('origen_id', sa.Text(), nullable=False),
        sa.Column('fecha_cierre', sa.DateTime(), nullable=False),
        sa.Column('evento_cancelado', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['estado_cuenta_id'], ['estado_cuenta.estado_cuenta_id'], name='fk_ec_cierre_sin_realizar_estado_cuenta', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('estado_cuenta_id', 'origen_id', name=op.f('pk_estado_cuenta_cierre_sin_realizar'))
    )
    op.create_table('estado_cuenta_seguimiento_cobro',
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('seguimiento', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['estado_cuenta_id'], ['estado_cuenta.estado_cuenta_id'], name='fk_ec_seguimiento_cobro_estado_cuenta', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('estado_cuenta_id', 'posicion', name=op.f('pk_estado_cuenta_seguimiento_cobro'))
    )
    op.create_table('obligacion_pago',
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('obligacion_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('concepto', sa.String(length=40), nullable=False),
        sa.Column('importe', sa.Numeric(), nullable=False),
        sa.Column('plazo_inicio', sa.DateTime(), nullable=True),
        sa.Column('plazo_vence', sa.DateTime(), nullable=True),
        sa.Column('origen_id', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.CheckConstraint("concepto IN ('ANTICIPO', 'SALDO_CONTRATO_ORIGINAL', 'SUSTITUCION_PROVEEDOR', 'CAMBIO', 'CARGO_CAMBIO_TARDIO', 'CARGOS_MORATORIOS', 'SERVICIO_ADICIONAL')", name=op.f('ck_obligacion_pago_concepto_valido')),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'VENCIDA', 'LIQUIDADA', 'SIN_EFECTO')", name=op.f('ck_obligacion_pago_estado_valido')),
        sa.CheckConstraint("importe >= 0 AND importe <> 'NaN' AND importe <> 'Infinity'", name=op.f('ck_obligacion_pago_importe_valido')),
        sa.CheckConstraint('(plazo_inicio IS NULL AND plazo_vence IS NULL) OR (plazo_inicio IS NOT NULL AND plazo_vence IS NOT NULL)', name=op.f('ck_obligacion_pago_plazo_completo')),
        sa.ForeignKeyConstraint(['estado_cuenta_id'], ['estado_cuenta.estado_cuenta_id'], name=op.f('fk_obligacion_pago_estado_cuenta_id_estado_cuenta'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('estado_cuenta_id', 'obligacion_id', name=op.f('pk_obligacion_pago')),
        sa.UniqueConstraint('estado_cuenta_id', 'concepto', 'origen_id', name=op.f('uq_obligacion_pago_estado_cuenta_id_concepto_origen_id')),
        sa.UniqueConstraint('estado_cuenta_id', 'posicion', name=op.f('uq_obligacion_pago_estado_cuenta_id_posicion'))
    )
    op.create_index('ix_obligacion_pago_abiertas', 'obligacion_pago', ['estado', 'plazo_vence'], unique=False, postgresql_where=sa.text("estado IN ('PENDIENTE', 'VENCIDA')"))
    op.create_table('solicitud_cambio',
        sa.Column('solicitud_id', sa.Text(), nullable=False),
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('contrato_id', sa.Text(), nullable=False),
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('anexo_id', sa.Text(), nullable=True),
        sa.Column('obligacion_pago_id', sa.Text(), nullable=True),
        sa.Column('motivo_cierre_causa', sa.String(length=40), nullable=True),
        sa.Column('motivo_cierre_descripcion', sa.Text(), nullable=True),
        sa.Column('motivo_cierre_fecha', sa.DateTime(), nullable=True),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('estado_antes_de_detener', sa.String(length=40), nullable=True),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('anticipacion_fecha_solicitud', sa.DateTime(), nullable=False),
        sa.Column('anticipacion_fecha_evento', sa.DateTime(), nullable=False),
        sa.Column('tarifa_importe', sa.Numeric(), nullable=False),
        sa.Column('datos_propuestos_tipo', sa.Text(), nullable=True),
        sa.Column('datos_propuestos_fecha_hora', sa.DateTime(), nullable=True),
        sa.Column('datos_propuestos_lugar', sa.Text(), nullable=True),
        sa.Column('datos_propuestos_invitados', sa.BigInteger(), nullable=True),
        sa.Column('viabilidad_viable', sa.Boolean(), nullable=True),
        sa.Column('viabilidad_motivo', sa.Text(), nullable=True),
        sa.Column('impacto_afecta_servicios', sa.Boolean(), nullable=True),
        sa.Column('impacto_afecta_costos', sa.Boolean(), nullable=True),
        sa.Column('impacto_afecta_condiciones', sa.Boolean(), nullable=True),
        sa.Column('costo_proveedor', sa.Numeric(), nullable=True),
        sa.Column('decision_cliente_actor', sa.Text(), nullable=True),
        sa.Column('decision_cliente_aprobada', sa.Boolean(), nullable=True),
        sa.Column('decision_cliente_fecha', sa.DateTime(), nullable=True),
        sa.Column('decision_cliente_motivo', sa.Text(), nullable=True),
        sa.Column('autorizacion_actor', sa.Text(), nullable=True),
        sa.Column('autorizacion_aprobada', sa.Boolean(), nullable=True),
        sa.Column('autorizacion_fecha', sa.DateTime(), nullable=True),
        sa.Column('autorizacion_motivo', sa.Text(), nullable=True),
        sa.Column('importes_por_pagar', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.CheckConstraint("(tarifa_importe >= 0 AND tarifa_importe <> 'NaN' AND tarifa_importe <> 'Infinity') AND (costo_proveedor IS NULL OR (costo_proveedor >= 0 AND costo_proveedor <> 'NaN' AND costo_proveedor <> 'Infinity'))", name=op.f('ck_solicitud_cambio_importes_validos')),
        sa.CheckConstraint("datos_propuestos_tipo IS NULL OR (datos_propuestos_tipo <> '' AND datos_propuestos_lugar <> '')", name=op.f('ck_solicitud_cambio_datos_propuestos_no_vacios')),
        sa.CheckConstraint("estado IN ('REGISTRADA', 'DETENIDA_SALDO_VENCIDO', 'EN_EVALUACION', 'PENDIENTE_APROBACION_CLIENTE', 'PENDIENTE_AUTORIZACION', 'PENDIENTE_FORMALIZACION', 'PENDIENTE_PAGO', 'CONFIRMADA', 'NO_PROCEDENTE', 'RECHAZADA_CLIENTE', 'NO_AUTORIZADA', 'CERRADA_FALTA_PAGO', 'CERRADA_INICIO_EVENTO', 'CERRADA_EVENTO_CANCELADO')", name=op.f('ck_solicitud_cambio_estado_valido')),
        sa.CheckConstraint("estado_antes_de_detener IS NULL OR estado_antes_de_detener IN ('REGISTRADA', 'DETENIDA_SALDO_VENCIDO', 'EN_EVALUACION', 'PENDIENTE_APROBACION_CLIENTE', 'PENDIENTE_AUTORIZACION', 'PENDIENTE_FORMALIZACION', 'PENDIENTE_PAGO', 'CONFIRMADA', 'NO_PROCEDENTE', 'RECHAZADA_CLIENTE', 'NO_AUTORIZADA', 'CERRADA_FALTA_PAGO', 'CERRADA_INICIO_EVENTO', 'CERRADA_EVENTO_CANCELADO')", name=op.f('ck_solicitud_cambio_estado_antes_de_detener_valido')),
        sa.CheckConstraint("motivo_cierre_causa IS NULL OR motivo_cierre_causa IN ('NO_VIABLE', 'RECHAZO_CLIENTE', 'NO_AUTORIZADA', 'FALTA_PAGO', 'PLAZO_INSUFICIENTE', 'CLIENTE_NO_ESPERA', 'INICIO_EVENTO', 'EVENTO_CANCELADO')", name=op.f('ck_solicitud_cambio_motivo_cierre_causa_valida')),
        sa.CheckConstraint('(autorizacion_actor IS NULL AND autorizacion_aprobada IS NULL AND autorizacion_fecha IS NULL AND autorizacion_motivo IS NULL) OR (autorizacion_actor IS NOT NULL AND autorizacion_aprobada IS NOT NULL AND autorizacion_fecha IS NOT NULL AND autorizacion_motivo IS NOT NULL)', name=op.f('ck_solicitud_cambio_autorizacion_completa')),
        sa.CheckConstraint('(datos_propuestos_tipo IS NULL AND datos_propuestos_fecha_hora IS NULL AND datos_propuestos_lugar IS NULL AND datos_propuestos_invitados IS NULL) OR (datos_propuestos_tipo IS NOT NULL AND datos_propuestos_fecha_hora IS NOT NULL AND datos_propuestos_lugar IS NOT NULL AND datos_propuestos_invitados IS NOT NULL)', name=op.f('ck_solicitud_cambio_datos_propuestos_completos')),
        sa.CheckConstraint('(decision_cliente_actor IS NULL AND decision_cliente_aprobada IS NULL AND decision_cliente_fecha IS NULL AND decision_cliente_motivo IS NULL) OR (decision_cliente_actor IS NOT NULL AND decision_cliente_aprobada IS NOT NULL AND decision_cliente_fecha IS NOT NULL AND decision_cliente_motivo IS NOT NULL)', name=op.f('ck_solicitud_cambio_decision_cliente_completa')),
        sa.CheckConstraint('(impacto_afecta_servicios IS NULL AND impacto_afecta_costos IS NULL AND impacto_afecta_condiciones IS NULL) OR (impacto_afecta_servicios IS NOT NULL AND impacto_afecta_costos IS NOT NULL AND impacto_afecta_condiciones IS NOT NULL)', name=op.f('ck_solicitud_cambio_impacto_completo')),
        sa.CheckConstraint('(motivo_cierre_causa IS NULL AND motivo_cierre_descripcion IS NULL AND motivo_cierre_fecha IS NULL) OR (motivo_cierre_causa IS NOT NULL AND motivo_cierre_descripcion IS NOT NULL AND motivo_cierre_fecha IS NOT NULL)', name=op.f('ck_solicitud_cambio_motivo_cierre_completo')),
        sa.CheckConstraint('(viabilidad_viable IS NULL AND viabilidad_motivo IS NULL) OR (viabilidad_viable IS NOT NULL AND viabilidad_motivo IS NOT NULL)', name=op.f('ck_solicitud_cambio_viabilidad_completa')),
        sa.CheckConstraint('datos_propuestos_invitados IS NULL OR datos_propuestos_invitados > 0', name=op.f('ck_solicitud_cambio_datos_propuestos_invitados_positivo')),
        sa.ForeignKeyConstraint(['estado_cuenta_id', 'contrato_id'], ['estado_cuenta.estado_cuenta_id', 'estado_cuenta.contrato_id'], name='fk_solicitud_cambio_estado_cuenta'),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name='fk_solicitud_cambio_evento'),
        sa.PrimaryKeyConstraint('solicitud_id', name=op.f('pk_solicitud_cambio'))
    )
    op.create_index('ix_solicitud_cambio_evento_id_estado', 'solicitud_cambio', ['evento_id', 'estado'], unique=False)
    op.create_table('solicitud_servicio_adicional',
        sa.Column('solicitud_id', sa.Text(), nullable=False),
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('contrato_id', sa.Text(), nullable=False),
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('anexo_id', sa.Text(), nullable=True),
        sa.Column('obligacion_pago_id', sa.Text(), nullable=True),
        sa.Column('motivo_cierre_causa', sa.String(length=40), nullable=True),
        sa.Column('motivo_cierre_descripcion', sa.Text(), nullable=True),
        sa.Column('motivo_cierre_fecha', sa.DateTime(), nullable=True),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('estado_antes_de_detener', sa.String(length=40), nullable=True),
        sa.Column('servicio', sa.Text(), nullable=False),
        sa.Column('anticipacion_fecha_solicitud', sa.DateTime(), nullable=False),
        sa.Column('anticipacion_fecha_evento', sa.DateTime(), nullable=False),
        sa.Column('elegibilidad_obtenida', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('disponibilidad_proveedor_id', sa.Text(), nullable=True),
        sa.Column('disponibilidad_disponible', sa.Boolean(), nullable=True),
        sa.Column('disponibilidad_costo', sa.Numeric(), nullable=True),
        sa.Column('disponibilidad_condiciones', sa.Text(), nullable=True),
        sa.Column('decision_cliente_actor', sa.Text(), nullable=True),
        sa.Column('decision_cliente_aprobada', sa.Boolean(), nullable=True),
        sa.Column('decision_cliente_fecha', sa.DateTime(), nullable=True),
        sa.Column('decision_cliente_motivo', sa.Text(), nullable=True),
        sa.Column('autorizacion_actor', sa.Text(), nullable=True),
        sa.Column('autorizacion_aprobada', sa.Boolean(), nullable=True),
        sa.Column('autorizacion_fecha', sa.DateTime(), nullable=True),
        sa.Column('autorizacion_motivo', sa.Text(), nullable=True),
        sa.CheckConstraint("disponibilidad_costo IS NULL OR (disponibilidad_costo >= 0 AND disponibilidad_costo <> 'NaN' AND disponibilidad_costo <> 'Infinity')", name=op.f('ck_solicitud_servicio_adicional_disponibilidad_costo_valido')),
        sa.CheckConstraint("estado IN ('REGISTRADA', 'DETENIDA_SALDO_VENCIDO', 'EN_BUSQUEDA_PROVEEDOR', 'PENDIENTE_APROBACION_CLIENTE', 'PENDIENTE_AUTORIZACION', 'AUTORIZADA', 'PENDIENTE_PAGO', 'CONFIRMADA', 'NO_PROCEDENTE', 'NO_SE_REALIZARA', 'NO_APROBADA', 'NO_AUTORIZADA', 'CERRADA_FALTA_PAGO', 'CERRADA_INICIO_EVENTO', 'CERRADA_EVENTO_CANCELADO')", name=op.f('ck_solicitud_servicio_adicional_estado_valido')),
        sa.CheckConstraint("estado_antes_de_detener IS NULL OR estado_antes_de_detener IN ('REGISTRADA', 'DETENIDA_SALDO_VENCIDO', 'EN_BUSQUEDA_PROVEEDOR', 'PENDIENTE_APROBACION_CLIENTE', 'PENDIENTE_AUTORIZACION', 'AUTORIZADA', 'PENDIENTE_PAGO', 'CONFIRMADA', 'NO_PROCEDENTE', 'NO_SE_REALIZARA', 'NO_APROBADA', 'NO_AUTORIZADA', 'CERRADA_FALTA_PAGO', 'CERRADA_INICIO_EVENTO', 'CERRADA_EVENTO_CANCELADO')", name=op.f('ck_solicitud_servicio_adicional_estado_antes_de_detener_valido')),
        sa.CheckConstraint("motivo_cierre_causa IS NULL OR motivo_cierre_causa IN ('NO_VIABLE', 'RECHAZO_CLIENTE', 'NO_AUTORIZADA', 'FALTA_PAGO', 'PLAZO_INSUFICIENTE', 'CLIENTE_NO_ESPERA', 'INICIO_EVENTO', 'EVENTO_CANCELADO')", name=op.f('ck_solicitud_servicio_adicional_motivo_cierre_causa_valida')),
        sa.CheckConstraint('(autorizacion_actor IS NULL AND autorizacion_aprobada IS NULL AND autorizacion_fecha IS NULL AND autorizacion_motivo IS NULL) OR (autorizacion_actor IS NOT NULL AND autorizacion_aprobada IS NOT NULL AND autorizacion_fecha IS NOT NULL AND autorizacion_motivo IS NOT NULL)', name=op.f('ck_solicitud_servicio_adicional_autorizacion_completa')),
        sa.CheckConstraint('(decision_cliente_actor IS NULL AND decision_cliente_aprobada IS NULL AND decision_cliente_fecha IS NULL AND decision_cliente_motivo IS NULL) OR (decision_cliente_actor IS NOT NULL AND decision_cliente_aprobada IS NOT NULL AND decision_cliente_fecha IS NOT NULL AND decision_cliente_motivo IS NOT NULL)', name=op.f('ck_solicitud_servicio_adicional_decision_cliente_completa')),
        sa.CheckConstraint('(disponibilidad_proveedor_id IS NULL AND disponibilidad_disponible IS NULL) OR (disponibilidad_proveedor_id IS NOT NULL AND disponibilidad_disponible IS NOT NULL)', name=op.f('ck_solicitud_servicio_adicional_disponibilidad_completa')),
        sa.CheckConstraint('(motivo_cierre_causa IS NULL AND motivo_cierre_descripcion IS NULL AND motivo_cierre_fecha IS NULL) OR (motivo_cierre_causa IS NOT NULL AND motivo_cierre_descripcion IS NOT NULL AND motivo_cierre_fecha IS NOT NULL)', name=op.f('ck_solicitud_servicio_adicional_motivo_cierre_completo')),
        sa.ForeignKeyConstraint(['estado_cuenta_id', 'contrato_id'], ['estado_cuenta.estado_cuenta_id', 'estado_cuenta.contrato_id'], name='fk_solicitud_servicio_adicional_estado_cuenta'),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name='fk_solicitud_servicio_adicional_evento'),
        sa.PrimaryKeyConstraint('solicitud_id', name=op.f('pk_solicitud_servicio_adicional'))
    )
    op.create_index('ix_solicitud_servicio_adicional_evento_id_estado', 'solicitud_servicio_adicional', ['evento_id', 'estado'], unique=False)
    op.create_table('sustitucion_proveedor',
        sa.Column('sustitucion_id', sa.Text(), nullable=False),
        sa.Column('evento_id', sa.Text(), nullable=False),
        sa.Column('contrato_id', sa.Text(), nullable=False),
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('anexo_id', sa.Text(), nullable=True),
        sa.Column('obligacion_pago_id', sa.Text(), nullable=True),
        sa.Column('motivo_cierre_causa', sa.String(length=40), nullable=True),
        sa.Column('motivo_cierre_descripcion', sa.Text(), nullable=True),
        sa.Column('motivo_cierre_fecha', sa.DateTime(), nullable=True),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('estado_antes_de_detener', sa.String(length=40), nullable=True),
        sa.Column('servicio_contratado_id', sa.Text(), nullable=False),
        sa.Column('proveedor_original_id', sa.Text(), nullable=False),
        sa.Column('costo_adicional', sa.Numeric(), nullable=True),
        sa.Column('aprobada_despues_del_limite', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.CheckConstraint("costo_adicional IS NULL OR (costo_adicional >= 0 AND costo_adicional <> 'NaN' AND costo_adicional <> 'Infinity')", name=op.f('ck_sustitucion_proveedor_costo_adicional_valido')),
        sa.CheckConstraint("estado IN ('EN_BUSQUEDA_ALTERNATIVA', 'PENDIENTE_APROBACION_CLIENTE', 'PENDIENTE_AUTORIZACION', 'PENDIENTE_FORMALIZACION', 'CONFIRMADA', 'CERRADA_INICIO_EVENTO', 'CERRADA_EVENTO_CANCELADO')", name=op.f('ck_sustitucion_proveedor_estado_valido')),
        sa.CheckConstraint("estado_antes_de_detener IS NULL OR estado_antes_de_detener IN ('EN_BUSQUEDA_ALTERNATIVA', 'PENDIENTE_APROBACION_CLIENTE', 'PENDIENTE_AUTORIZACION', 'PENDIENTE_FORMALIZACION', 'CONFIRMADA', 'CERRADA_INICIO_EVENTO', 'CERRADA_EVENTO_CANCELADO')", name=op.f('ck_sustitucion_proveedor_estado_antes_de_detener_valido')),
        sa.CheckConstraint("motivo_cierre_causa IS NULL OR motivo_cierre_causa IN ('NO_VIABLE', 'RECHAZO_CLIENTE', 'NO_AUTORIZADA', 'FALTA_PAGO', 'PLAZO_INSUFICIENTE', 'CLIENTE_NO_ESPERA', 'INICIO_EVENTO', 'EVENTO_CANCELADO')", name=op.f('ck_sustitucion_proveedor_motivo_cierre_causa_valida')),
        sa.CheckConstraint('(motivo_cierre_causa IS NULL AND motivo_cierre_descripcion IS NULL AND motivo_cierre_fecha IS NULL) OR (motivo_cierre_causa IS NOT NULL AND motivo_cierre_descripcion IS NOT NULL AND motivo_cierre_fecha IS NOT NULL)', name=op.f('ck_sustitucion_proveedor_motivo_cierre_completo')),
        sa.ForeignKeyConstraint(['estado_cuenta_id', 'contrato_id'], ['estado_cuenta.estado_cuenta_id', 'estado_cuenta.contrato_id'], name='fk_sustitucion_proveedor_estado_cuenta'),
        sa.ForeignKeyConstraint(['evento_id'], ['evento.evento_id'], name='fk_sustitucion_proveedor_evento'),
        sa.PrimaryKeyConstraint('sustitucion_id', name=op.f('pk_sustitucion_proveedor'))
    )
    op.create_index('ix_sustitucion_proveedor_evento_id_estado', 'sustitucion_proveedor', ['evento_id', 'estado'], unique=False)
    op.create_table('pago',
        sa.Column('estado_cuenta_id', sa.Text(), nullable=False),
        sa.Column('pago_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('obligacion_id', sa.Text(), nullable=False),
        sa.Column('importe', sa.Numeric(), nullable=False),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.Column('comprobante', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(length=40), nullable=False),
        sa.Column('registrado_en', sa.DateTime(), nullable=True),
        sa.Column('verificado_en', sa.DateTime(), nullable=True),
        sa.CheckConstraint("estado IN ('REGISTRADO', 'VERIFICADO', 'IMPORTE_INCORRECTO')", name=op.f('ck_pago_estado_valido')),
        sa.CheckConstraint("importe >= 0 AND importe <> 'NaN' AND importe <> 'Infinity'", name=op.f('ck_pago_importe_valido')),
        sa.ForeignKeyConstraint(['estado_cuenta_id', 'obligacion_id'], ['obligacion_pago.estado_cuenta_id', 'obligacion_pago.obligacion_id'], name=op.f('fk_pago_estado_cuenta_id_obligacion_id_obligacion_pago'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('estado_cuenta_id', 'pago_id', name=op.f('pk_pago')),
        sa.UniqueConstraint('estado_cuenta_id', 'posicion', name=op.f('uq_pago_estado_cuenta_id_posicion'))
    )
    op.create_index('ix_pago_estado_cuenta_id_obligacion_id', 'pago', ['estado_cuenta_id', 'obligacion_id'], unique=False)
    op.create_table('solicitud_cambio_condicion',
        sa.Column('solicitud_id', sa.Text(), nullable=False),
        sa.Column('servicio_contratado_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('condiciones', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['solicitud_id'], ['solicitud_cambio.solicitud_id'], name=op.f('fk_solicitud_cambio_condicion_solicitud_id_solicitud_cambio'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('solicitud_id', 'servicio_contratado_id', name=op.f('pk_solicitud_cambio_condicion')),
        sa.UniqueConstraint('solicitud_id', 'posicion', name=op.f('uq_solicitud_cambio_condicion_solicitud_id_posicion'))
    )
    op.create_table('sustitucion_alternativa',
        sa.Column('sustitucion_id', sa.Text(), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('proveedor_id', sa.Text(), nullable=False),
        sa.Column('disponibilidad_proveedor_id', sa.Text(), nullable=True),
        sa.Column('disponibilidad_disponible', sa.Boolean(), nullable=True),
        sa.Column('disponibilidad_costo', sa.Numeric(), nullable=True),
        sa.Column('disponibilidad_condiciones', sa.Text(), nullable=True),
        sa.Column('impacto_afecta_servicios', sa.Boolean(), nullable=False),
        sa.Column('impacto_afecta_costos', sa.Boolean(), nullable=False),
        sa.Column('impacto_afecta_condiciones', sa.Boolean(), nullable=False),
        sa.Column('decision_cliente_actor', sa.Text(), nullable=True),
        sa.Column('decision_cliente_aprobada', sa.Boolean(), nullable=True),
        sa.Column('decision_cliente_fecha', sa.DateTime(), nullable=True),
        sa.Column('decision_cliente_motivo', sa.Text(), nullable=True),
        sa.Column('autorizacion_actor', sa.Text(), nullable=True),
        sa.Column('autorizacion_aprobada', sa.Boolean(), nullable=True),
        sa.Column('autorizacion_fecha', sa.DateTime(), nullable=True),
        sa.Column('autorizacion_motivo', sa.Text(), nullable=True),
        sa.CheckConstraint("disponibilidad_costo IS NULL OR (disponibilidad_costo >= 0 AND disponibilidad_costo <> 'NaN' AND disponibilidad_costo <> 'Infinity')", name=op.f('ck_sustitucion_alternativa_disponibilidad_costo_valido')),
        sa.CheckConstraint('(autorizacion_actor IS NULL AND autorizacion_aprobada IS NULL AND autorizacion_fecha IS NULL AND autorizacion_motivo IS NULL) OR (autorizacion_actor IS NOT NULL AND autorizacion_aprobada IS NOT NULL AND autorizacion_fecha IS NOT NULL AND autorizacion_motivo IS NOT NULL)', name=op.f('ck_sustitucion_alternativa_autorizacion_completa')),
        sa.CheckConstraint('(decision_cliente_actor IS NULL AND decision_cliente_aprobada IS NULL AND decision_cliente_fecha IS NULL AND decision_cliente_motivo IS NULL) OR (decision_cliente_actor IS NOT NULL AND decision_cliente_aprobada IS NOT NULL AND decision_cliente_fecha IS NOT NULL AND decision_cliente_motivo IS NOT NULL)', name=op.f('ck_sustitucion_alternativa_decision_cliente_completa')),
        sa.CheckConstraint('(disponibilidad_proveedor_id IS NULL AND disponibilidad_disponible IS NULL) OR (disponibilidad_proveedor_id IS NOT NULL AND disponibilidad_disponible IS NOT NULL)', name=op.f('ck_sustitucion_alternativa_disponibilidad_completa')),
        sa.CheckConstraint('disponibilidad_proveedor_id IS NOT NULL AND disponibilidad_disponible IS NOT NULL', name=op.f('ck_sustitucion_alternativa_disponibilidad_informada')),
        sa.ForeignKeyConstraint(['sustitucion_id'], ['sustitucion_proveedor.sustitucion_id'], name=op.f('fk_sustitucion_alternativa_sustitucion_id_sustitucion_proveedor'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('sustitucion_id', 'posicion', name=op.f('pk_sustitucion_alternativa'))
    )
    op.create_foreign_key('fk_propuesta_version_vigente', 'propuesta', 'version_propuesta',
                          ['propuesta_id', 'version_vigente_id'], ['propuesta_id', 'version_id'], deferrable=True, initially='DEFERRED')


def downgrade() -> None:
    # Inversa exacta de upgrade(): solo elimina lo que esta revisión crea.
    op.drop_constraint('fk_propuesta_version_vigente', 'propuesta', type_='foreignkey')
    op.drop_table('sustitucion_alternativa')
    op.drop_table('solicitud_cambio_condicion')
    op.drop_index('ix_pago_estado_cuenta_id_obligacion_id', table_name='pago')
    op.drop_table('pago')
    op.drop_index('ix_sustitucion_proveedor_evento_id_estado', table_name='sustitucion_proveedor')
    op.drop_table('sustitucion_proveedor')
    op.drop_index('ix_solicitud_servicio_adicional_evento_id_estado', table_name='solicitud_servicio_adicional')
    op.drop_table('solicitud_servicio_adicional')
    op.drop_index('ix_solicitud_cambio_evento_id_estado', table_name='solicitud_cambio')
    op.drop_table('solicitud_cambio')
    op.drop_index('ix_obligacion_pago_abiertas', table_name='obligacion_pago', postgresql_where=sa.text("estado IN ('PENDIENTE', 'VENCIDA')"))
    op.drop_table('obligacion_pago')
    op.drop_table('estado_cuenta_seguimiento_cobro')
    op.drop_table('estado_cuenta_cierre_sin_realizar')
    op.drop_index('ix_devolucion_pendientes', table_name='devolucion', postgresql_where=sa.text("estado = 'PENDIENTE'"))
    op.drop_table('devolucion')
    op.drop_index('ix_estado_cuenta_evento_id', table_name='estado_cuenta')
    op.drop_table('estado_cuenta')
    op.drop_table('contrato_seguimiento_anticipo')
    op.drop_table('contrato_anexo')
    op.drop_index('ix_contrato_evento_id', table_name='contrato')
    op.drop_table('contrato')
    op.drop_table('version_propuesta')
    op.drop_index('ix_propuesta_evento_id', table_name='propuesta')
    op.drop_table('propuesta')
    op.drop_table('outbox_reaccion')
    op.drop_table('evento_solicitud_cancelacion')
    op.drop_index('ix_evento_servicio_contratado_proveedor_id', table_name='evento_servicio_contratado')
    op.drop_table('evento_servicio_contratado')
    op.drop_table('evento_operacion_aplicada')
    op.drop_index('ix_outbox_evento_pendientes', table_name='outbox_evento', postgresql_where=sa.text("estado = 'PENDIENTE'"))
    op.drop_table('outbox_evento')
    op.drop_index('ix_evento_fecha_hora', table_name='evento')
    op.drop_table('evento')
