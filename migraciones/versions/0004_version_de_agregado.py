"""Control de concurrencia optimista: columna `version` en cada raíz de agregado.

El repositorio SQL guarda con `UPDATE ... WHERE version = <leída>` y falla (ConflictoDeConcurrencia) si otra transacción cambió el
agregado antes, en lugar de perder la actualización («gana la última»). Cambio aditivo: las filas existentes quedan en versión 0 y
ningún dato se modifica.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

RAICES = ('propuesta', 'contrato', 'evento', 'solicitud_cambio', 'solicitud_servicio_adicional', 'sustitucion_proveedor',
          'estado_cuenta')


def upgrade() -> None:
    for tabla in RAICES:
        op.add_column(tabla, sa.Column('version', sa.BigInteger(), server_default='0', nullable=False))
        op.create_check_constraint(op.f(f'ck_{tabla}_version_no_negativa'), tabla, 'version >= 0')


def downgrade() -> None:
    for tabla in reversed(RAICES):
        op.drop_constraint(op.f(f'ck_{tabla}_version_no_negativa'), tabla, type_='check')
        op.drop_column(tabla, 'version')
