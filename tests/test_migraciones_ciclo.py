"""Etapa 8 — ciclo de migraciones en una base DESECHABLE e independiente (`eventosnova_migraciones_test`).

`alembic downgrade` se ejercita únicamente aquí: nunca sobre la base de desarrollo ni sobre la de pruebas de integración. La base
se crea si no existe y se reutiliza entre ejecuciones (no se borra: el `downgrade` ya elimina sus tablas). Las funciones de
`preparacion` se niegan a actuar sobre una base que no sea local y de nombre terminado en `_test`."""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
import sqlalchemy as sa                                                                   # noqa: E402
from alembic.autogenerate import compare_metadata                                         # noqa: E402
from alembic.migration import MigrationContext                                            # noqa: E402
from apoyo_bd import motor_de_pruebas                                                     # noqa: E402
import apoyo_persistencia as A                                                            # noqa: E402
from infrastructure.esquema_postgresql import metadata                                    # noqa: E402
from infrastructure.persistencia import configuracion as C                                # noqa: E402
from infrastructure.persistencia import repositorios_sql as S                             # noqa: E402
from infrastructure.persistencia.conexion import AlmacenSQL, crear_motor                  # noqa: E402
from infrastructure.persistencia.errores import ErrorDePersistencia                       # noqa: E402
from infrastructure.persistencia.preparacion import (asegurar_base_de_pruebas, aplicar_migraciones,   # noqa: E402
                                                     limpiar_base_de_pruebas, revertir_migraciones)
from domain.solicitudes import SustitucionProveedor                                       # noqa: E402

BASE_DESECHABLE = 'eventosnova_migraciones_test'


class CicloDeMigraciones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        motor_de_pruebas()                                                                 # omite si PostgreSQL no está disponible
        cls.url = C.url_con_base(C.url_pruebas(), BASE_DESECHABLE)
        cls.resumen = asegurar_base_de_pruebas(cls.url)
        cls.motor = crear_motor(cls.url)

    @classmethod
    def tearDownClass(cls):
        cls.motor.dispose()

    def tablas(self):
        with self.motor.connect() as con:
            return set(sa.inspect(con).get_table_names())

    def revision(self):
        with self.motor.connect() as con:
            if not sa.inspect(con).has_table('alembic_version'):
                return None
            return con.execute(sa.text('select version_num from alembic_version')).scalar()

    def test_es_una_base_distinta_de_desarrollo_y_de_pruebas_de_integracion(self):
        self.assertTrue(C.es_base_local_de_pruebas(self.url))
        bases = {C.descripcion_segura(u)['base'] for u in (C.url_desarrollo(), C.url_pruebas())}
        self.assertNotIn(BASE_DESECHABLE, bases)

    def test_ciclo_completo_subida_bajada_y_subida(self):
        aplicar_migraciones(self.url)
        self.assertEqual(self.revision(), '0006')
        self.assertEqual(self.tablas() - {'alembic_version'}, set(metadata.tables))
        with self.motor.connect() as con:
            self.assertEqual(compare_metadata(MigrationContext.configure(con, opts={'compare_type': True}), metadata), [])

        revertir_migraciones(self.url, '0005')                                              # baja solo la 0006: descarta cuentas y sesiones
        self.assertEqual(self.revision(), '0005')
        self.assertTrue({'usuario', 'sesion', 'intento_acceso'}.isdisjoint(self.tablas()))
        self.assertIn('proveedor', self.tablas())                                           # el catálogo de la 0005 sigue

        revertir_migraciones(self.url, '0004')                                              # baja solo la 0005: descarta el catálogo
        self.assertEqual(self.revision(), '0004')
        self.assertNotIn('proveedor', self.tablas())
        self.assertIn('evento', self.tablas())                                              # lo demás sigue intacto

        revertir_migraciones(self.url, '0003')                                              # baja la 0004
        self.assertEqual(self.revision(), '0003')
        with self.motor.connect() as con:
            self.assertNotIn('version', {c['name'] for c in sa.inspect(con).get_columns('estado_cuenta')})

        revertir_migraciones(self.url, '0002')                                              # baja la 0003
        self.assertEqual(self.revision(), '0002')
        with self.motor.connect() as con:
            self.assertNotIn('pago_id', {c['name'] for c in sa.inspect(con).get_columns('devolucion')})

        revertir_migraciones(self.url, '0001')                                              # baja la 0002
        self.assertEqual(self.revision(), '0001')
        with self.motor.connect() as con:
            columnas = {c['name']: c for c in sa.inspect(con).get_columns('sustitucion_proveedor')}
        self.assertFalse(columnas['proveedor_original_id']['nullable'])                     # la 0001 original

        revertir_migraciones(self.url, 'base')                                              # baja la 0001: elimina las tablas
        self.assertEqual(self.tablas() - {'alembic_version'}, set())
        self.assertIsNone(self.revision())

        aplicar_migraciones(self.url)                                                       # vuelve a subir: repetible
        self.assertEqual(self.revision(), '0006')
        self.assertEqual(self.tablas() - {'alembic_version'}, set(metadata.tables))

    def test_subir_dos_veces_es_idempotente(self):
        aplicar_migraciones(self.url)
        aplicar_migraciones(self.url)
        self.assertEqual(self.revision(), '0006')

    def test_bajar_la_0002_falla_sin_modificar_nada_si_hay_sustituciones_sin_proveedor_original(self):
        aplicar_migraciones(self.url)
        limpiar_base_de_pruebas(self.motor)
        almacen = AlmacenSQL(self.motor)
        S.EventoRepositorySQL(almacen).guardar(A.eventos()[0])
        S.PropuestaRepositorySQL(almacen).guardar(A.propuestas()[0])
        S.ContratoRepositorySQL(almacen).guardar(A.contratos()[0])
        S.EstadoCuentaRepositorySQL(almacen).guardar(A.estados_cuenta()[0])
        revertir_migraciones(self.url, '0002')                                              # sin devoluciones del anticipo: la 0003 baja
        aplicar_migraciones(self.url)
        sin_proveedor = SustitucionProveedor('SP-SIN', 'EV-1', 'CT-1-S2', None, 'CT-1', 'EC-1', A.T0)   # servicio sin proveedor asignado
        S.SustitucionProveedorRepositorySQL(almacen).guardar(sin_proveedor)
        revertir_migraciones(self.url, '0002')
        with self.assertRaises(Exception):
            revertir_migraciones(self.url, '0001')                                          # no se inventa un valor: la bajada se rechaza
        self.assertEqual(self.revision(), '0002')                                           # el esquema quedó intacto (DDL transaccional)
        with self.motor.connect() as con:
            self.assertEqual(con.execute(sa.text("select count(*) from sustitucion_proveedor where proveedor_original_id is null")).scalar(), 1)
        limpiar_base_de_pruebas(self.motor)
        revertir_migraciones(self.url, '0001')                                              # sin esas filas ya es posible
        aplicar_migraciones(self.url)

    def test_las_operaciones_destructivas_se_niegan_sobre_bases_que_no_son_de_pruebas(self):
        """Con dobles: aunque la protección fallara, nunca se ejecutaría nada contra una base real."""
        from unittest import mock
        desarrollo = C.url_desarrollo()
        with mock.patch('infrastructure.persistencia.preparacion._alembic') as alembic_falso:
            for url in (desarrollo, C.url_con_base(desarrollo, 'otra'), 'postgresql+psycopg://u:p@servidor-remoto.example/algo_test'):
                with self.subTest(C.descripcion_segura(url)['base'] + '@' + str(C.descripcion_segura(url)['host'])):
                    with self.assertRaises(ErrorDePersistencia):
                        revertir_migraciones(url, 'base')
            alembic_falso.assert_not_called()
        motor_falso = mock.MagicMock()
        motor_falso.url.render_as_string.return_value = desarrollo
        with self.assertRaises(ErrorDePersistencia):
            limpiar_base_de_pruebas(motor_falso)
        motor_falso.begin.assert_not_called()


if __name__ == '__main__':
    unittest.main()
