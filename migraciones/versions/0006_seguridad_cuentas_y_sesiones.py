"""Seguridad: tablas `usuario`, `sesion` e `intento_acceso`.

Cambio aditivo: crea tablas nuevas; no modifica ni borra ninguna tabla ni fila existente. No inserta ninguna cuenta: el primer administrador se
crea con `scripts/crear_administrador.py` (sin credenciales predeterminadas). Las contraseñas se guardan solo como hash Argon2id y las sesiones
solo como SHA-256 del token.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'usuario',
        sa.Column('usuario_id', sa.Text(), nullable=False),
        sa.Column('correo', sa.Text(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('rol', sa.Text(), nullable=False),
        sa.Column('contrasena_hash', sa.Text(), nullable=False),
        sa.Column('activo', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('proveedor_id', sa.Text(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=False), nullable=False),
        sa.Column('ultimo_acceso', sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint('usuario_id', name=op.f('pk_usuario')),
        sa.UniqueConstraint('correo', name=op.f('uq_usuario_correo')),
        sa.ForeignKeyConstraint(['proveedor_id'], ['proveedor.proveedor_id'], name=op.f('fk_usuario_proveedor_id_proveedor')),
        sa.CheckConstraint("rol IN ('administrador', 'coordinador', 'proveedor')", name=op.f('ck_usuario_rol_valido')),
        sa.CheckConstraint("(rol = 'proveedor') = (proveedor_id IS NOT NULL)", name=op.f('ck_usuario_proveedor_solo_si_rol_proveedor')),
        sa.CheckConstraint("correo = lower(correo) AND correo <> ''", name=op.f('ck_usuario_correo_normalizado')),
    )
    op.create_table(
        'sesion',
        sa.Column('sesion_hash', sa.Text(), nullable=False),
        sa.Column('usuario_id', sa.Text(), nullable=False),
        sa.Column('csrf', sa.Text(), nullable=False),
        sa.Column('creada_en', sa.DateTime(timezone=False), nullable=False),
        sa.Column('ultima_actividad', sa.DateTime(timezone=False), nullable=False),
        sa.Column('expira_en', sa.DateTime(timezone=False), nullable=False),
        sa.Column('revocada_en', sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint('sesion_hash', name=op.f('pk_sesion')),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.usuario_id'], name=op.f('fk_sesion_usuario_id_usuario'), ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_sesion_usuario_id'), 'sesion', ['usuario_id'])
    op.create_table(
        'intento_acceso',
        sa.Column('clave', sa.Text(), nullable=False),
        sa.Column('fallos', sa.BigInteger(), nullable=False),
        sa.Column('primer_fallo', sa.DateTime(timezone=False), nullable=False),
        sa.Column('bloqueado_hasta', sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint('clave', name=op.f('pk_intento_acceso')),
        sa.CheckConstraint('fallos >= 0', name=op.f('ck_intento_acceso_fallos_no_negativos')),
    )


def downgrade() -> None:
    # Descarta las cuentas, sesiones e intentos (las contraseñas no pueden recuperarse). Hacer copia de seguridad antes.
    op.drop_table('intento_acceso')
    op.drop_index(op.f('ix_sesion_usuario_id'), table_name='sesion')
    op.drop_table('sesion')
    op.drop_table('usuario')
