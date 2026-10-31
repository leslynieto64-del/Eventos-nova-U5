"""Catálogo de proveedores: tabla `proveedor`.

Cambio aditivo: crea una tabla nueva y no modifica ni borra ninguna tabla ni fila existente. Los servicios contratados siguen
guardando `proveedor_id` como referencia blanda (sin clave foránea), de modo que los identificadores históricos (p. ej. «PV-1»)
siguen siendo válidos aunque no figuren en el catálogo.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'proveedor',
        sa.Column('proveedor_id', sa.Text(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('nombre_normalizado', sa.Text(), nullable=False),
        sa.Column('servicios', pg.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('contacto', sa.Text(), server_default='', nullable=False),
        sa.Column('registrado_en', sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint('proveedor_id', name=op.f('pk_proveedor')),
        sa.UniqueConstraint('nombre_normalizado', name=op.f('uq_proveedor_nombre_normalizado')),
        sa.CheckConstraint("btrim(nombre) <> ''", name=op.f('ck_proveedor_nombre_no_vacio')),
    )


def downgrade() -> None:
    # Descarta el catálogo (los servicios contratados conservan su proveedor_id porque no hay clave foránea).
    op.drop_table('proveedor')
