"""Devolución del anticipo de una contratación cerrada sin confirmar (decisión A del cierre de alcance aprobado).

- `estado_cuenta.cierre_contratacion`: momento en que se cerró la contratación sin confirmar (NULL mientras no se cierre).
- `devolucion.tipo`: «SOLICITUD_NO_REALIZADA» (SE-012, las filas existentes) o «ANTICIPO_CONTRATACION_CERRADA» (decisión A).
- `devolucion.pago_id` y `devolucion.fecha_referencia`: la devolución del anticipo nace de un pago (como máximo una por pago,
  C-11) y su plazo cuenta desde la más tardía entre el cierre y el registro del pago (A-6).
- `devolucion.solicitud_id` pasa a admitir NULL; el CHECK `origen_segun_tipo` exige la solicitud en SE-012 y el pago en la
  devolución del anticipo.
Cambio aditivo: las devoluciones existentes quedan como SE-012 y no se modifica ningún dato.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('estado_cuenta', sa.Column('cierre_contratacion', sa.DateTime(timezone=False), nullable=True))
    op.add_column('devolucion', sa.Column('tipo', sa.String(length=40), server_default='SOLICITUD_NO_REALIZADA', nullable=False))
    op.add_column('devolucion', sa.Column('pago_id', sa.Text(), nullable=True))
    op.add_column('devolucion', sa.Column('fecha_referencia', sa.DateTime(timezone=False), nullable=True))
    op.alter_column('devolucion', 'solicitud_id', existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(op.f('ck_devolucion_tipo_valido'), 'devolucion',
                               "tipo IN ('SOLICITUD_NO_REALIZADA', 'ANTICIPO_CONTRATACION_CERRADA')")
    op.create_check_constraint(
        op.f('ck_devolucion_origen_segun_tipo'), 'devolucion',
        "(tipo = 'SOLICITUD_NO_REALIZADA' AND solicitud_id IS NOT NULL) OR "
        "(tipo = 'ANTICIPO_CONTRATACION_CERRADA' AND pago_id IS NOT NULL AND fecha_referencia IS NOT NULL "
        "AND concepto = 'ANTICIPO')")
    op.create_index('uq_devolucion_pago', 'devolucion', ['estado_cuenta_id', 'pago_id'], unique=True,
                    postgresql_where=sa.text('pago_id IS NOT NULL'))


def downgrade() -> None:
    # Falla (sin modificar nada) si ya existen devoluciones del anticipo: su solicitud_id es NULL y no se inventa un valor.
    op.drop_index('uq_devolucion_pago', table_name='devolucion', postgresql_where=sa.text('pago_id IS NOT NULL'))
    op.drop_constraint(op.f('ck_devolucion_origen_segun_tipo'), 'devolucion', type_='check')
    op.drop_constraint(op.f('ck_devolucion_tipo_valido'), 'devolucion', type_='check')
    op.alter_column('devolucion', 'solicitud_id', existing_type=sa.Text(), nullable=False)
    op.drop_column('devolucion', 'fecha_referencia')
    op.drop_column('devolucion', 'pago_id')
    op.drop_column('devolucion', 'tipo')
    op.drop_column('estado_cuenta', 'cierre_contratacion')
