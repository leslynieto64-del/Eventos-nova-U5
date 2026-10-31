"""Conexión, traducción de errores, configuración por entorno y trabajador del Outbox (línea de comandos)."""
import os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
import sqlalchemy as sa                                                                   # noqa: E402
from sqlalchemy import exc as sa_exc                                                      # noqa: E402
from apoyo_bd import BaseConBD                                                            # noqa: E402
from infrastructure.persistencia import configuracion as C                                # noqa: E402
from infrastructure.persistencia import trabajador_outbox                                 # noqa: E402
from infrastructure.persistencia.conexion import AlmacenSQL, crear_motor, traducir        # noqa: E402
from infrastructure.persistencia.errores import (ErrorDeConexion, ErrorDeDatos, ErrorDePersistencia,   # noqa: E402
                                                 ViolacionDeRestriccion)


def origen(mensaje='mensaje del servidor', sqlstate=None, **diag):
    e = Exception(mensaje)
    e.sqlstate = sqlstate
    e.diag = SimpleNamespace(constraint_name=diag.get('constraint_name'), table_name=diag.get('table_name'),
                             column_name=diag.get('column_name'), sqlstate=sqlstate)
    return e


class TraduccionDeErrores(unittest.TestCase):
    def test_integridad_conserva_restriccion_tabla_y_codigo(self):
        e = traducir(sa_exc.IntegrityError('INSERT', {}, origen('duplicate key\nDETAIL: ...', '23505', constraint_name='uq_x', table_name='t')))
        self.assertIsInstance(e, ViolacionDeRestriccion)
        self.assertEqual((e.restriccion, e.tabla, e.codigo), ('uq_x', 't', '23505'))
        self.assertEqual(str(e), 'duplicate key')                                            # solo la primera línea
        self.assertIsInstance(e.__cause__, sa_exc.IntegrityError)

    def test_not_null_se_identifica_por_su_columna(self):
        e = traducir(sa_exc.IntegrityError('INSERT', {}, origen('null value', '23502', column_name='proveedor', table_name='t')))
        self.assertEqual(e.restriccion, 'NOT NULL proveedor')

    def test_datos_conexion_y_generico(self):
        self.assertIsInstance(traducir(sa_exc.DataError('x', {}, origen('integer out of range'))), ErrorDeDatos)
        self.assertIsInstance(traducir(sa_exc.OperationalError('x', {}, origen('server closed the connection'))), ErrorDeConexion)
        self.assertIsInstance(traducir(sa_exc.InterfaceError('x', {}, origen('connection is closed'))), ErrorDeConexion)
        general = traducir(sa_exc.ProgrammingError('x', {}, origen('relation does not exist')))
        self.assertIs(type(general), ErrorDePersistencia)
        self.assertIs(type(traducir(sa_exc.SQLAlchemyError('sin origen'))), ErrorDePersistencia)

    def test_el_mensaje_no_incluye_la_sentencia_ni_los_parametros(self):
        e = traducir(sa_exc.IntegrityError('INSERT INTO t VALUES (:secreto)', {'secreto': 'CONTRASENA-123'}, origen('violación')))
        self.assertNotIn('CONTRASENA-123', str(e))
        self.assertNotIn('INSERT', str(e))


class AlmacenSinBaseDeDatos(unittest.TestCase):
    def test_sin_transaccion_activa(self):
        almacen = AlmacenSQL(sa.create_engine('sqlite://'))
        self.assertIsNone(almacen.conexion_activa)
        with self.assertRaises(ErrorDePersistencia):
            almacen.confirmar()
        with self.assertRaises(ErrorDePersistencia):
            almacen.revertir()

    def test_conectar_a_una_base_inalcanzable_es_un_error_de_conexion(self):
        motor = crear_motor('postgresql+psycopg://u:clave-secreta@127.0.0.1:1/x_test', connect_args={'connect_timeout': 2})
        almacen = AlmacenSQL(motor)
        with self.assertRaises(ErrorDeConexion) as ctx:
            almacen.iniciar()
        self.assertNotIn('clave-secreta', str(ctx.exception))
        self.assertIsNone(almacen.conexion_activa)                                           # no queda una transacción a medias
        with self.assertRaises(ErrorDeConexion):
            with almacen.lectura() as con:
                con.execute(sa.text('select 1'))
        with self.assertRaises(ErrorDeConexion):
            with almacen.escritura() as con:
                con.execute(sa.text('select 1'))
        almacen.cerrar()

    def test_el_motor_define_un_tiempo_maximo_de_conexion_y_verifica_las_conexiones_por_omision(self):
        with mock.patch('infrastructure.persistencia.conexion.sa.create_engine') as crear:
            crear_motor('postgresql://u:p@127.0.0.1:5432/x_test')
        url, = crear.call_args.args
        self.assertEqual(url, 'postgresql+psycopg://u:p@127.0.0.1:5432/x_test')                 # siempre el controlador Psycopg 3
        self.assertEqual(crear.call_args.kwargs['connect_args']['connect_timeout'], 10)
        self.assertTrue(crear.call_args.kwargs['pool_pre_ping'])


class ConAlmacen(BaseConBD):
    def test_errores_de_sql_dentro_de_lectura_y_escritura_se_traducen(self):
        with self.assertRaises(ErrorDePersistencia) as ctx:
            with self.almacen.lectura() as con:
                con.execute(sa.text('select * from tabla_que_no_existe'))
        self.assertNotIn('tabla_que_no_existe', type(ctx.exception).__name__)
        with self.assertRaises(ErrorDePersistencia):
            with self.almacen.escritura() as con:
                con.execute(sa.text('insert into tabla_que_no_existe values (1)'))
        self.assertEqual(self.motor.pool.checkedout(), 0)

    def test_confirmar_con_la_conexion_perdida_revierte_y_libera(self):
        self.almacen.iniciar()
        con = self.almacen.conexion_activa
        with mock.patch.object(type(con), 'commit', side_effect=sa_exc.OperationalError('x', {}, origen('server closed the connection'))):
            with self.assertRaises(ErrorDeConexion):
                self.almacen.confirmar()
        self.assertIsNone(self.almacen.conexion_activa)
        self.assertEqual(self.motor.pool.checkedout(), 0)

    def test_revertir_con_la_conexion_rota_no_oculta_el_error_original(self):
        self.almacen.iniciar()
        con = self.almacen.conexion_activa
        with mock.patch.object(type(con), 'rollback', side_effect=sa_exc.OperationalError('x', {}, origen('roto'))):
            self.almacen.revertir()                                                           # no lanza
        self.assertIsNone(self.almacen.conexion_activa)

    def test_exigir_esquema_al_dia(self):
        from infrastructure.persistencia.preparacion import exigir_esquema_al_dia, revision_actual
        self.assertEqual(revision_actual(self.motor), '0006')
        exigir_esquema_al_dia(self.motor)

    def test_trabajador_una_vez_desde_la_linea_de_comandos(self):
        with mock.patch.dict(os.environ, {'DATABASE_URL': C.url_pruebas()}):
            self.assertEqual(trabajador_outbox.main(['--una-vez']), 0)
            self.assertEqual(trabajador_outbox.main(['--una-vez', '--intervalo', '0.1']), 0)

    def test_trabajador_no_arranca_sin_base_de_datos(self):
        with mock.patch.dict(os.environ, {'DATABASE_URL': 'postgresql+psycopg://u:p@127.0.0.1:1/x_test'}):
            with mock.patch('infrastructure.persistencia.composicion_persistente.crear_motor',
                            side_effect=lambda url, **o: crear_motor(url, connect_args={'connect_timeout': 2})):
                with self.assertRaises(ErrorDeConexion):
                    trabajador_outbox.main(['--una-vez'])


class Configuracion(unittest.TestCase):
    def test_cargar_env_no_sobrescribe_variables_existentes_ni_requiere_el_archivo(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / '.env'
            ruta.write_text('# comentario\nVAR_NUEVA_X=hola\nVAR_EXISTENTE_X="del archivo"\n\nsin_igual\n', encoding='utf-8')
            with mock.patch.dict(os.environ, {'VAR_EXISTENTE_X': 'del entorno'}, clear=False):
                os.environ.pop('VAR_NUEVA_X', None)
                C.cargar_env_local(ruta)
                self.assertEqual(os.environ['VAR_NUEVA_X'], 'hola')
                self.assertEqual(os.environ['VAR_EXISTENTE_X'], 'del entorno')
                os.environ.pop('VAR_NUEVA_X', None)
            C.cargar_env_local(Path(d) / 'no-existe.env')                                      # sin archivo: no hace nada

    def test_modo_de_persistencia(self):
        with mock.patch.object(C, 'cargar_env_local'):
            for valor, esperado in (('', 'memoria'), ('MEMORIA', 'memoria'), (' postgresql ', 'postgresql')):
                with mock.patch.dict(os.environ, {'EVENTOSNOVA_PERSISTENCIA': valor}):
                    self.assertEqual(C.modo_persistencia(), esperado)
            with mock.patch.dict(os.environ, {'EVENTOSNOVA_PERSISTENCIA': 'sqlite'}):
                with self.assertRaises(ValueError):
                    C.modo_persistencia()

    def test_urls(self):
        self.assertEqual(C.normalizar_url('postgresql://u:p@h/b'), 'postgresql+psycopg://u:p@h/b')
        self.assertEqual(C.normalizar_url('postgresql+psycopg://u:p@h/b'), 'postgresql+psycopg://u:p@h/b')
        self.assertEqual(C.normalizar_url('postgres://u:p@h/b'), 'postgresql+psycopg://u:p@h/b')     # forma de algunas plataformas
        d = C.descripcion_segura('postgresql+psycopg://usuario:clave-secreta@127.0.0.1:5432/mi_base')
        self.assertEqual(d, {'host': '127.0.0.1', 'puerto': 5432, 'base': 'mi_base', 'usuario': 'usuario'})
        self.assertNotIn('clave-secreta', str(d))
        self.assertEqual(C.url_con_base('postgresql+psycopg://u:p@h:1/a', 'b'), 'postgresql+psycopg://u:p@h:1/b')

    def test_solo_las_bases_locales_terminadas_en_test_son_de_pruebas(self):
        for url, esperado in (('postgresql+psycopg://u:p@127.0.0.1:5432/eventosnova_test', True),
                              ('postgresql+psycopg://u:p@localhost/x_test', True), ('postgresql+psycopg://u:p@db:5432/x_test', True),
                              ('postgresql+psycopg://u:p@127.0.0.1:5432/eventosnova', False),
                              ('postgresql+psycopg://u:p@servidor.remoto.com/x_test', False),
                              ('postgresql+psycopg://u:p@127.0.0.1/test_x', False)):
            with self.subTest(url):
                self.assertEqual(C.es_base_local_de_pruebas(url), esperado)


if __name__ == '__main__':
    unittest.main()
