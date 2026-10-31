"""El esquema REAL de la base de pruebas (migrada a `head` con Alembic) coincide con los metadatos de SQLAlchemy.

Solo lectura: usa `compare_metadata` de Alembic y consultas al catálogo; no crea ni modifica nada."""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
import sqlalchemy as sa                                                                   # noqa: E402
from alembic.autogenerate import compare_metadata                                         # noqa: E402
from alembic.migration import MigrationContext                                            # noqa: E402
from apoyo_bd import BaseConBD                                                            # noqa: E402
from infrastructure.esquema_postgresql import metadata                                    # noqa: E402


class EsquemaReal(BaseConBD):
    def test_alembic_no_ve_diferencias_entre_la_base_y_los_metadatos(self):
        with self.motor.connect() as con:
            diferencias = compare_metadata(MigrationContext.configure(con, opts={'compare_type': True}), metadata)
        self.assertEqual(diferencias, [])

    def test_la_base_esta_en_la_ultima_revision(self):
        with self.motor.connect() as con:
            self.assertEqual(con.execute(sa.text('select version_num from alembic_version')).scalars().all(), ['0006'])
            self.assertEqual(len(sa.inspect(con).get_table_names()) - 1, len(metadata.tables))     # menos alembic_version

    def test_proveedor_original_admite_null_tras_la_revision_0002(self):
        with self.motor.connect() as con:
            columnas = {c['name']: c for c in sa.inspect(con).get_columns('sustitucion_proveedor')}
        self.assertTrue(columnas['proveedor_original_id']['nullable'])
        self.assertFalse(columnas['servicio_contratado_id']['nullable'])

    def test_restricciones_y_tipos_clave(self):
        with self.motor.connect() as con:
            fk = con.execute(sa.text("select condeferrable, condeferred from pg_constraint where conname = 'fk_propuesta_version_vigente'")).one()
            tipos = dict(con.execute(sa.text("select table_name || '.' || column_name, data_type from information_schema.columns where "
                                             "table_schema = 'public' and column_name in ('invitados_aproximados', 'costo_total')")).all())
            n_ck = con.execute(sa.text("select count(*) from pg_constraint where contype = 'c' and connamespace = 'public'::regnamespace")).scalar()
        self.assertEqual(tuple(fk), (True, True))
        self.assertEqual(tipos['evento.invitados_aproximados'], 'bigint')
        self.assertEqual(tipos['contrato.costo_total'], 'numeric')
        self.assertEqual(n_ck, sum(1 for t in metadata.tables.values() for c in t.constraints if isinstance(c, sa.CheckConstraint)))


if __name__ == '__main__':
    unittest.main()
