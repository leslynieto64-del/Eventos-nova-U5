"""Etapa 5 de la persistencia — unidad de trabajo SQL (PostgreSQL de pruebas).

Confirmación, reversión, excepciones, errores de restricciones, atomicidad de un agregado, cierre de recursos, aislamiento entre
hilos/operaciones y registro de eventos en la misma transacción (ADR-004)."""
import os, sys, threading, unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
import sqlalchemy as sa                                                                   # noqa: E402
import apoyo_persistencia as A                                                            # noqa: E402
from apoyo_bd import BaseConBD                                                            # noqa: E402
from application.servicios import transaccion                                             # noqa: E402
from infrastructure.persistencia import repositorios_sql as S                             # noqa: E402
from infrastructure.persistencia.errores import ErrorDePersistencia, ViolacionDeRestriccion   # noqa: E402
from infrastructure.persistencia.unidad_trabajo_sql import IRegistradorDeEventos, UnitOfWorkSQL   # noqa: E402


class RegistradorFalso(IRegistradorDeEventos):
    def __init__(self, almacen, falla=None):
        self.almacen, self.falla = almacen, falla
        self.registrados, self.misma_conexion = [], []

    def registrar(self, conexion, eventos):
        self.misma_conexion.append(conexion is self.almacen.conexion_activa)
        if self.falla:
            raise self.falla
        self.registrados.extend(eventos)


class Base(BaseConBD):
    def setUp(self):
        super().setUp()
        self.registrador = RegistradorFalso(self.almacen)
        self.uow = UnitOfWorkSQL(self.almacen, self.registrador)
        self.eventos = S.EventoRepositorySQL(self.almacen)
        self.propuestas = S.PropuestaRepositorySQL(self.almacen)

    def visibles(self, id_):
        """Lee con una conexión independiente: solo ve lo confirmado."""
        with self.motor.connect() as con:
            return con.execute(sa.text('select count(*) from evento where evento_id = :i'), {'i': id_}).scalar()

    def en_uso(self):
        return self.motor.pool.checkedout()

    def transacciones_abiertas(self):
        with self.motor.connect() as con:
            return con.execute(sa.text("select count(*) from pg_stat_activity where datname = current_database() "
                                       "and pid <> pg_backend_pid() and state like 'idle in transaction%'")).scalar()


class Confirmacion(Base):
    def test_los_cambios_solo_son_visibles_fuera_de_la_transaccion_tras_confirmar(self):
        e = A.eventos()[1]
        self.uow.iniciar(); self.uow.registrar(e)
        self.eventos.guardar(e)
        self.assertEqual(self.visibles('EV-2'), 0)                   # sin confirmar: otra conexión no lo ve
        self.assertIsNotNone(self.eventos.obtener_por_id('EV-2'))    # dentro de la transacción sí se ven los cambios propios
        self.uow.confirmar()
        self.assertEqual(self.visibles('EV-2'), 1)
        self.assertEqual(self.en_uso(), 0)

    def test_revertir_deshace_todo_y_descarta_los_eventos(self):
        e = A.eventos()[3]                                           # tiene Domain Events pendientes
        self.assertTrue(e._eventos)
        self.uow.iniciar(); self.uow.registrar(e)
        self.eventos.guardar(e)
        self.uow.revertir()
        self.assertEqual(self.visibles('EV-3'), 0)
        self.assertEqual(e._eventos, [])                             # descartados: no se publican
        self.assertEqual(self.registrador.registrados, [])
        self.assertEqual(self.en_uso(), 0)

    def test_confirmar_guarda_los_eventos_con_la_misma_conexion_de_la_transaccion(self):
        e = A.eventos()[3]
        n = len(e._eventos)
        self.uow.iniciar(); self.uow.registrar(e)
        self.eventos.guardar(e)
        self.uow.confirmar()
        self.assertEqual(len(self.registrador.registrados), n)
        self.assertEqual(self.registrador.misma_conexion, [True])
        self.assertEqual(e._eventos, [])

    def test_si_el_registro_de_eventos_falla_el_agregado_tampoco_se_guarda(self):
        self.registrador.falla = ErrorDePersistencia('Outbox no disponible')
        e = A.eventos()[3]
        self.uow.iniciar(); self.uow.registrar(e)
        self.eventos.guardar(e)
        with self.assertRaises(ErrorDePersistencia):
            self.uow.confirmar()
        self.assertEqual(self.visibles('EV-3'), 0)                   # el cambio y su evento van juntos o no van
        self.assertEqual(self.en_uso(), 0)

    def test_con_eventos_pendientes_y_sin_registrador_no_se_pierden_en_silencio(self):
        uow = UnitOfWorkSQL(self.almacen)                            # sin Outbox configurado
        e = A.eventos()[3]
        uow.iniciar(); uow.registrar(e)
        self.eventos.guardar(e)
        with self.assertRaises(ErrorDePersistencia):
            uow.confirmar()
        self.assertEqual(self.visibles('EV-3'), 0)

    def test_sin_eventos_no_hace_falta_registrador(self):
        uow = UnitOfWorkSQL(self.almacen)
        e = A.eventos()[1]
        self.assertEqual(e._eventos, [])
        uow.iniciar(); uow.registrar(e)
        self.eventos.guardar(e)
        uow.confirmar()
        self.assertEqual(self.visibles('EV-2'), 1)


class ExcepcionesYRestricciones(Base):
    def test_una_excepcion_dentro_de_transaccion_revierte_y_se_propaga_intacta(self):
        class Fallo(Exception):
            pass
        e = A.eventos()[1]
        with self.assertRaises(Fallo):
            with transaccion(self.uow, e):                          # el mismo contexto que usan los servicios
                self.eventos.guardar(e)
                raise Fallo('error del caso de uso')
        self.assertEqual(self.visibles('EV-2'), 0)
        self.assertEqual(self.en_uso(), 0)

    def test_transaccion_de_los_servicios_confirma_cuando_todo_sale_bien(self):
        e = A.eventos()[1]
        with transaccion(self.uow, e):
            self.eventos.guardar(e)
        self.assertEqual(self.visibles('EV-2'), 1)

    def test_una_violacion_de_restriccion_al_guardar_revierte_los_cambios_previos_de_la_misma_operacion(self):
        ev = A.eventos()[0]
        propuesta = A.propuestas()[0]
        with self.assertRaises(ViolacionDeRestriccion):
            with transaccion(self.uow, ev, propuesta):
                self.eventos.guardar(ev)                             # válido
                p = A.propuestas()[0]
                p.evento_id = 'EV-NO-EXISTE'
                self.propuestas.guardar(p)                           # viola la FK hacia evento
        self.assertEqual(self.visibles('EV-1'), 0)                   # el evento válido también se revirtió
        self.assertEqual(self.transacciones_abiertas(), 0)
        self.assertEqual(self.en_uso(), 0)

    def test_una_restriccion_diferida_que_falla_al_confirmar_no_deja_nada_a_medias(self):
        self.eventos.guardar(A.eventos()[0]); self.eventos.guardar(A.eventos()[1])
        self.propuestas.guardar(A.propuestas()[1])                   # PR-2
        p = A.propuestas()[0]
        p.version_vigente_id = 'PR-2-v1'                             # vigente de otra propuesta: FK compuesta diferida
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            with transaccion(self.uow, p):
                self.propuestas.guardar(p)                           # no falla aquí: se comprueba al confirmar
        self.assertEqual(ctx.exception.restriccion, 'fk_propuesta_version_vigente')
        self.assertEqual(self.contar('propuesta'), 1)
        self.assertEqual(self.contar('version_propuesta'), 1)
        self.assertEqual(self.transacciones_abiertas(), 0)
        self.assertEqual(self.en_uso(), 0)

    def test_un_agregado_es_atomico_si_una_fila_hija_falla(self):
        self.eventos.guardar(A.eventos()[0])
        e = self.eventos.obtener_por_id('EV-1')
        n = len(e.servicios)
        e.cliente_id = 'CAMBIADO'
        from domain.valores import CondicionesServicio
        e.servicios['CT-1-S1'].condiciones = CondicionesServicio(None)   # NOT NULL: la fila hija falla tras actualizar la raíz
        with self.assertRaises(ErrorDePersistencia):
            with transaccion(self.uow, e):
                self.eventos.guardar(e)
        otra = self.eventos.obtener_por_id('EV-1')
        self.assertEqual(otra.cliente_id, 'CL-1')                    # la raíz tampoco quedó actualizada
        self.assertEqual(len(otra.servicios), n)

    def test_el_error_de_persistencia_no_es_un_rechazo_de_negocio(self):
        from domain.valores import ErrorDominio
        e = A.eventos()[1]
        object.__setattr__(e.datos, 'invitados_aproximados', -1)
        with self.assertRaises(ErrorDePersistencia) as ctx:
            with transaccion(self.uow, e):
                self.eventos.guardar(e)
        self.assertNotIsInstance(ctx.exception, ErrorDominio)


class ProtocoloYRecursos(Base):
    def test_no_se_admiten_transacciones_anidadas_y_la_primera_sigue_valida(self):
        self.uow.iniciar()
        with self.assertRaises(ErrorDePersistencia):
            self.uow.iniciar()
        e = A.eventos()[1]
        self.uow.registrar(e); self.eventos.guardar(e)
        self.uow.confirmar()
        self.assertEqual(self.visibles('EV-2'), 1)

    def test_operaciones_sin_transaccion(self):
        with self.assertRaises(ErrorDePersistencia):
            self.uow.registrar(A.eventos()[1])
        with self.assertRaises(ErrorDePersistencia):
            self.uow.confirmar()
        self.uow.revertir()                                          # tolerante: no hace nada

    def test_ninguna_conexion_queda_abierta_tras_confirmar_revertir_o_fallar(self):
        for i in range(8):
            e = self.eventos.obtener_por_id('EV-2') or A.eventos()[1]          # existente: se actualiza (control de concurrencia optimista)
            self.uow.iniciar(); self.uow.registrar(e); self.eventos.guardar(e)
            (self.uow.confirmar if i % 2 == 0 else self.uow.revertir)()
        with self.assertRaises(ViolacionDeRestriccion):
            with transaccion(self.uow):
                p = A.propuestas()[0]; self.propuestas.guardar(p)   # evento inexistente
        self.assertEqual(self.en_uso(), 0)
        self.assertEqual(self.transacciones_abiertas(), 0)

    def test_leer_fuera_de_una_transaccion_no_deja_conexiones_ni_transacciones(self):
        self.eventos.guardar(A.eventos()[1])
        for _ in range(5):
            self.eventos.obtener_por_id('EV-2'); self.eventos.listar_todos()
        self.assertEqual(self.en_uso(), 0)
        self.assertEqual(self.transacciones_abiertas(), 0)


class Aislamiento(Base):
    def test_cada_hilo_tiene_su_propia_transaccion_y_no_ve_la_ajena_sin_confirmar(self):
        e_a, e_b = A.eventos()[1], A.eventos()[2]                    # EV-2 y EV-6
        a_listo, b_termino, resultado = threading.Event(), threading.Event(), {}

        def hilo_a():
            self.uow.iniciar(); self.uow.registrar(e_a); self.eventos.guardar(e_a)
            resultado['a_conexion'] = id(self.almacen.conexion_activa)
            a_listo.set()
            b_termino.wait(10)                                       # B confirma mientras A sigue abierta
            resultado['a_ve_b'] = self.eventos.obtener_por_id('EV-6') is not None     # A (aún en su transacción) ve lo confirmado
            self.uow.revertir()

        def hilo_b():
            a_listo.wait(10)
            resultado['b_ve_a_antes'] = self.eventos.obtener_por_id('EV-2') is not None
            resultado['b_conexion'] = None
            self.uow.iniciar(); self.uow.registrar(e_b); self.eventos.guardar(e_b)
            resultado['b_conexion'] = id(self.almacen.conexion_activa)
            self.uow.confirmar()
            b_termino.set()

        ta, tb = threading.Thread(target=hilo_a), threading.Thread(target=hilo_b)
        ta.start(); tb.start(); ta.join(30); tb.join(30)
        self.assertFalse(ta.is_alive() or tb.is_alive())
        self.assertFalse(resultado['b_ve_a_antes'])                  # B no ve el cambio sin confirmar de A
        self.assertNotEqual(resultado['a_conexion'], resultado['b_conexion'])
        self.assertTrue(resultado['a_ve_b'])
        self.assertEqual(self.visibles('EV-2'), 0)                   # A revirtió
        self.assertEqual(self.visibles('EV-6'), 1)                   # B confirmó
        self.assertEqual(self.en_uso(), 0)

    def test_operaciones_sucesivas_no_comparten_estado(self):
        e1 = A.eventos()[1]
        self.uow.iniciar(); self.uow.registrar(e1); self.eventos.guardar(e1); self.uow.revertir()
        self.assertIsNone(self.almacen.conexion_activa)
        e2 = A.eventos()[2]
        self.uow.iniciar(); self.uow.registrar(e2); self.eventos.guardar(e2); self.uow.confirmar()
        self.assertEqual((self.visibles('EV-2'), self.visibles('EV-6')), (0, 1))


if __name__ == '__main__':
    unittest.main()
