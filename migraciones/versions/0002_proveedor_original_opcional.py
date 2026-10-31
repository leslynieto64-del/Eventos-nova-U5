"""sustitucion_proveedor.proveedor_original_id pasa a admitir NULL.

Hallazgo de las pruebas de extremo a extremo (HTTP + PostgreSQL): `GestionSustitucionProveedorService.registrar_proveedor_no_disponible`
crea la sustitución con `sc.proveedor_id`, y un servicio contratado puede no tener proveedor asignado (`Evento.servicios`,
estado «Sin proveedor asignado»). El dominio admite `None`; la columna de la revisión 0001 era NOT NULL y rechazaba ese caso.
Cambio aditivo: no borra ni modifica datos.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('sustitucion_proveedor', 'proveedor_original_id', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Vuelve a exigir el valor. Falla (sin modificar nada) si ya existen sustituciones sin proveedor original: en ese caso
    # primero hay que decidir qué hacer con esas filas; no se inventa un valor.
    op.alter_column('sustitucion_proveedor', 'proveedor_original_id', existing_type=sa.Text(), nullable=False)
