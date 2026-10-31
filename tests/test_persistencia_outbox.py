"""Etapa 6 — Outbox persistente y despachador (PostgreSQL de pruebas).

Registro transaccional, estados, reacciones con idempotencia por clave estable, fallo y reintento, error permanente (REVISION),
recuperación tras la caída de un trabajador, reinicio, dos trabajadores concurrentes y eventos no rehidratables."""
import os, sys, threading, time, unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
import sqlalchemy as sa                                                                    # noqa: E402
import apoyo_persistencia as A                                                             # noqa: E402
from apoyo_bd import BaseConBD                                                             # noqa: E402
from application.servicios import transaccion                                              # noqa: E402
from domain import eventos_dominio as E                                                    # noqa: E402
from infrastructure.persistencia import repositorios_sql as S                              # noqa: E402
from infrastructure.persistencia.conexion import AlmacenSQL                                # noqa: E402
from infrastructure.persistencia.errores import ErrorDePersistencia                        # noqa: E402
from infrastructure.persistencia.outbox_sql import (DespachadorOutboxSQL, OutboxSQL, PublicadorEstable,   # noqa: E402
                                                    clave_de_reaccion)
from infrastructure.persistencia.unidad_trabajo_sql import UnitOfWorkSQL                   # noqa: E402

OCURRIDO = datetime(2026, 10, 1, 10, 0)


class Reacciones:
    """Reacciones de prueba con contadores; sus métodos enlazados dan claves estables, como las reales."""
    def __init__(self):
        self.llamadas = []
        self.fallos = {}                    # nombre -> número de veces que debe fallar antes de funcionar ('siempre' = infinito)
        self.pausa = 0.0
        self.caer_en = None                 # nombre de la reacción que simula la caída del trabajador (BaseException)

    def _ejecutar(self, nombre, evento):
        self.llamadas.append((nombre, evento.evento_id))
        if self.pausa:
            time.sleep(self.pausa)
        if self.caer_en == nombre:
            self.caer_en = None
            raise Caida('el trabajador se cayó')
        pendientes = self.fallos.get(nombre, 0)
        if pendientes == 'siempre' or pendientes > 0:
            if pendientes != 'siempre':
                self.fallos[nombre] -= 1
            raise RuntimeError(f'{nombre} falló')

    def primera(self, e): self._ejecutar('primera', e)
    def segunda(self, e): self._ejecutar('segunda', e)

    def contar(self, nombre):
        return len([1 for n, _ in self.llamadas if n == nombre])


class Caida(BaseException):
    """Simula un fallo que no es una excepción de negocio (corte de proceso): no la captura `except Exception`."""


class Base(BaseConBD):
    def setUp(self):
        super().setUp()
        self.outbox = OutboxSQL(self.almacen)
        self.uow = UnitOfWorkSQL(self.almacen, self.outbox)
        self.eventos = S.EventoRepositorySQL(self.almacen)
        self.r = Reacciones()

    def publicador(self, reacciones=None):
        p = PublicadorEstable()
        r = reacciones or self.r
        p.suscribir(E.PropuestaAceptada, r.primera)
        p.suscribir(E.PropuestaAceptada, r.segunda)
        return p

    def despachador(self, max_intentos=3, almacen=None, reacciones=None):
        return DespachadorOutboxSQL(almacen or self.almacen, self.publicador(reacciones), max_intentos=max_intentos)

    def registrar(self, *eventos):
        """Registra eventos en el Outbox con una transacción propia (confirma o revierte, sin dejar nada abierto)."""
        self.almacen.iniciar()
        try:
            self.outbox.registrar(self.almacen.conexion_activa, list(eventos))
        except BaseException:
            self.almacen.revertir()
            raise
        self.almacen.confirmar()

    @staticmethod
    def aceptada(n=1, ref='EV-1'):
        return [E.PropuestaAceptada(agregado_id=f'PR-{i}', ocurrido_en=OCURRIDO, evento_ref=ref) for i in range(n)]

    def registro(self, evento):
        return next(x for x in self.outbox.registros() if x.evento_id == evento.evento_id)


class Registro(Base):
    def test_los_eventos_se_guardan_pendientes_y_en_orden(self):
        a, b, c = self.aceptada(3)
        self.registrar(a, b, c)
        regs = self.outbox.registros()
        self.assertEqual([x.evento_id for x in regs], [a.evento_id, b.evento_id, c.evento_id])
        self.assertEqual([x.secuencia for x in regs], sorted(x.secuencia for x in regs))
        self.assertTrue(all(x.estado == 'Pendiente' and x.intentos == 0 and x.error == '' for x in regs))
        self.assertEqual(regs[0].evento, a)                              # se rehidrata idéntico
        self.assertEqual(regs[0].tipo_evento, 'PropuestaAceptada')

    def test_el_evento_se_guarda_en_la_misma_transaccion_que_el_agregado(self):
        ev = A.eventos()[3]
        n = len(ev._eventos)
        with transaccion(self.uow, ev):
            self.eventos.guardar(ev)
        self.assertEqual(self.contar('evento'), 1)
        self.assertEqual(len(self.outbox.registros()), n)
        self.assertEqual(ev._eventos, [])

    def test_si_la_operacion_se_revierte_no_queda_ningun_evento(self):
        ev = A.eventos()[3]
        with self.assertRaises(RuntimeError):
            with transaccion(self.uow, ev):
                self.eventos.guardar(ev)
                raise RuntimeError('falla del caso de uso')
        self.assertEqual(self.contar('evento'), 0)
        self.assertEqual(self.contar('outbox_evento'), 0)

    def test_un_evento_que_no_se_puede_serializar_revierte_toda_la_operacion(self):
        ev = A.eventos()[3]
        ev._eventos.append(E.PropuestaAceptada(agregado_id='X', ocurrido_en=OCURRIDO, evento_ref=1.5))   # float: el codec lo rechaza
        with self.assertRaises(ErrorDePersistencia):
            with transaccion(self.uow, ev):
                self.eventos.guardar(ev)
        self.assertEqual(self.contar('evento'), 0)
        self.assertEqual(self.contar('outbox_evento'), 0)

    def test_un_evento_duplicado_se_rechaza(self):
        a = self.aceptada()[0]
        self.registrar(a)
        with self.assertRaises(ErrorDePersistencia):
            self.registrar(a)
        self.assertEqual(self.contar('outbox_evento'), 1)

    def test_rehidratar_no_vuelve_a_registrar_eventos(self):
        a = self.aceptada()[0]
        self.registrar(a)
        for _ in range(3):
            self.outbox.registros()
        self.assertEqual(self.contar('outbox_evento'), 1)


class Despacho(Base):
    def test_procesa_marca_procesado_y_anota_cada_reaccion(self):
        a = self.aceptada()[0]
        self.registrar(a)
        self.assertEqual(self.despachador().despachar(), 1)
        reg = self.registro(a)
        self.assertEqual((reg.estado, reg.intentos), ('Procesado', 0))
        self.assertEqual({n for n, _ in self.r.llamadas}, {'primera', 'segunda'})
        self.assertEqual(reg.reacciones_procesadas, {clave_de_reaccion(self.r.primera), clave_de_reaccion(self.r.segunda)})

    def test_cada_reaccion_se_ejecuta_una_sola_vez(self):
        self.registrar(*self.aceptada(2))
        d = self.despachador()
        self.assertEqual(d.despachar(), 2)
        self.assertEqual(d.despachar(), 0)                              # nada más que hacer
        self.assertEqual((self.r.contar('primera'), self.r.contar('segunda')), (2, 2))

    def test_una_reaccion_ya_anotada_no_se_repite_en_un_dispatcher_nuevo(self):
        a = self.aceptada()[0]
        self.registrar(a)
        self.despachador().despachar()
        with self.motor.begin() as con:                                  # simula un registro que volvió a estar pendiente
            con.execute(sa.text("update outbox_evento set estado = 'PENDIENTE'"))
        self.despachador().despachar()
        self.assertEqual((self.r.contar('primera'), self.r.contar('segunda')), (1, 1))
        self.assertEqual(self.registro(a).estado, 'Procesado')

    def test_fallo_y_reintento_hasta_tener_exito(self):
        a = self.aceptada()[0]
        self.registrar(a)
        self.r.fallos['segunda'] = 2                                     # falla 2 veces y a la tercera funciona
        self.assertEqual(self.despachador(max_intentos=3).despachar(), 1)
        reg = self.registro(a)
        self.assertEqual((reg.estado, reg.intentos), ('Procesado', 2))
        self.assertIn('segunda falló', reg.error)                        # conserva el último error visto, como el Outbox en memoria
        self.assertEqual((self.r.contar('primera'), self.r.contar('segunda')), (1, 3))   # la primera NO se repitió

    def test_error_permanente_pasa_a_revision_con_el_motivo(self):
        a = self.aceptada()[0]
        self.registrar(a)
        self.r.fallos['segunda'] = 'siempre'
        self.assertEqual(self.despachador(max_intentos=3).despachar(), 0)
        reg = self.registro(a)
        self.assertEqual((reg.estado, reg.intentos), ('Revisión', 3))
        self.assertIn('segunda falló', reg.error)
        n = self.r.contar('segunda')
        self.assertEqual(self.despachador().despachar(), 0)             # un evento en revisión no se vuelve a tocar solo
        self.assertEqual(self.r.contar('segunda'), n)
        self.assertEqual(self.r.contar('primera'), 1)

    def test_reabrir_un_evento_en_revision(self):
        a = self.aceptada()[0]
        self.registrar(a)
        self.r.fallos['segunda'] = 'siempre'
        self.despachador().despachar()
        self.assertFalse(self.outbox.reabrir('NO-EXISTE'))
        self.assertTrue(self.outbox.reabrir(a.evento_id))
        self.r.fallos['segunda'] = 0                                     # ya se corrigió la causa
        self.assertEqual(self.despachador().despachar(), 1)
        self.assertEqual(self.registro(a).estado, 'Procesado')
        self.assertEqual(self.r.contar('primera'), 1)                    # las reacciones ya hechas no se repiten

    def test_los_eventos_se_despachan_en_orden_de_secuencia(self):
        eventos = self.aceptada(5)
        self.registrar(*eventos)
        self.despachador().despachar()
        orden = [eid for n, eid in self.r.llamadas if n == 'primera']
        self.assertEqual(orden, [e.evento_id for e in eventos])

    def test_eventos_sin_reacciones_suscritas_se_marcan_procesados(self):
        e = E.EventoFinalizado(agregado_id='EV-1', ocurrido_en=OCURRIDO)
        self.registrar(e)
        self.assertEqual(self.despachador().despachar(), 1)
        self.assertEqual(self.registro(e).estado, 'Procesado')

    def test_una_reaccion_que_genera_otro_evento_se_procesa_en_el_mismo_despacho(self):
        nuevo = E.EventoFinalizado(agregado_id='EV-2', ocurrido_en=OCURRIDO)
        outbox, almacen = self.outbox, self.almacen

        class Cascada:
            def al_aceptar(self, e):
                uow = UnitOfWorkSQL(almacen, outbox)
                uow.iniciar()
                outbox.registrar(almacen.conexion_activa, [nuevo])
                uow.confirmar()
        p = PublicadorEstable()
        p.suscribir(E.PropuestaAceptada, Cascada().al_aceptar)
        self.registrar(self.aceptada()[0])
        self.assertEqual(DespachadorOutboxSQL(self.almacen, p).despachar(), 2)
        self.assertEqual(self.registro(nuevo).estado, 'Procesado')

    def test_no_se_puede_despachar_dentro_de_una_transaccion(self):
        self.uow.iniciar()
        try:
            with self.assertRaises(ErrorDePersistencia):
                self.despachador().despachar()
        finally:
            self.uow.revertir()

    def test_no_quedan_conexiones_ni_transacciones_abiertas(self):
        self.registrar(*self.aceptada(3))
        self.r.fallos['primera'] = 'siempre'
        self.despachador().despachar()
        self.assertEqual(self.motor.pool.checkedout(), 0)
        with self.motor.connect() as con:
            n = con.execute(sa.text("select count(*) from pg_stat_activity where datname = current_database() and pid <> "
                                    "pg_backend_pid() and state like 'idle in transaction%'")).scalar()
        self.assertEqual(n, 0)


class Recuperacion(Base):
    def test_si_el_trabajador_cae_a_mitad_se_continua_sin_repetir_lo_hecho(self):
        a = self.aceptada()[0]
        self.registrar(a)
        self.r.caer_en = 'segunda'                                       # cae tras terminar la primera reaccion
        with self.assertRaises(Caida):
            self.despachador().despachar()
        reg = self.registro(a)
        self.assertEqual(reg.estado, 'Pendiente')                        # el reclamo se liberó; el evento no se perdió
        self.assertEqual(reg.reacciones_procesadas, {clave_de_reaccion(self.r.primera)})
        self.assertEqual(self.despachador().despachar(), 1)              # «reinicio» del trabajador
        self.assertEqual(self.registro(a).estado, 'Procesado')
        self.assertEqual((self.r.contar('primera'), self.r.contar('segunda')), (1, 2))

    def test_reiniciar_con_otro_motor_y_otro_despachador_retoma_los_pendientes(self):
        self.registrar(*self.aceptada(3))
        self.assertEqual(len(self.outbox.registros('PENDIENTE')), 3)
        nuevo = AlmacenSQL(self.motor)                                    # un trabajador nuevo (sin estado compartido)
        self.assertEqual(self.despachador(almacen=nuevo).despachar(), 3)
        self.assertEqual(len(self.outbox.registros('PROCESADO')), 3)


class Concurrencia(Base):
    def test_dos_trabajadores_no_procesan_el_mismo_evento(self):
        eventos = self.aceptada(8)
        self.registrar(*eventos)
        self.r.pausa = 0.05
        resultados = []

        def trabajador():
            almacen = AlmacenSQL(self.motor)                              # cada trabajador con su propio almacén
            resultados.append(self.despachador(almacen=almacen).despachar())

        hilos = [threading.Thread(target=trabajador) for _ in range(2)]
        [h.start() for h in hilos]; [h.join(60) for h in hilos]
        self.assertFalse(any(h.is_alive() for h in hilos))
        self.assertEqual(sum(resultados), 8)                              # entre los dos, cada evento exactamente una vez
        for nombre in ('primera', 'segunda'):
            llamados = [eid for n, eid in self.r.llamadas if n == nombre]
            self.assertEqual(sorted(llamados), sorted(e.evento_id for e in eventos), nombre)
        self.assertEqual(len(self.outbox.registros('PROCESADO')), 8)
        self.assertEqual(len(resultados), 2)
        self.assertTrue(all(r > 0 for r in resultados), f'el trabajo no se repartió entre los dos trabajadores: {resultados}')

    def test_un_evento_reclamado_por_otro_trabajador_se_omite(self):
        a = self.aceptada()[0]
        self.registrar(a)
        con = self.motor.connect()
        tx = con.begin()
        try:                                                              # otro trabajador tiene el evento reclamado
            con.execute(sa.text("select 1 from outbox_evento where evento_id = :i for no key update"), {'i': a.evento_id})
            self.assertEqual(self.despachador().despachar(), 0)           # SKIP LOCKED: no espera ni lo procesa
            self.assertEqual(self.r.llamadas, [])
        finally:
            tx.rollback(); con.close()
        self.assertEqual(self.despachador().despachar(), 1)               # liberado: ahora sí


class EventosNoRehidratables(Base):
    def insertar_crudo(self, tipo, datos, evento_id='EV-CRUDO'):
        with self.motor.begin() as con:
            con.execute(sa.text("insert into outbox_evento (evento_id, tipo_evento, agregado_id, ocurrido_en, datos) "
                                "values (:e, :t, 'AG', :o, cast(:d as jsonb))"),
                        {'e': evento_id, 't': tipo, 'o': OCURRIDO, 'd': datos})

    def test_tipo_desconocido_queda_en_revision_sin_perderse(self):
        self.insertar_crudo('EventoDelFuturo', '{"version": 1, "campos": {}}')
        self.registrar(self.aceptada()[0])                                 # un evento válido posterior se procesa igualmente
        self.assertEqual(self.despachador().despachar(), 1)
        crudo = next(x for x in self.outbox.registros() if x.evento_id == 'EV-CRUDO')
        self.assertEqual(crudo.estado, 'Revisión')
        self.assertIn('desconocido', crudo.error)
        self.assertIsNone(crudo.evento)
        self.assertIn('desconocido', crudo.error_de_rehidratacion)
        self.assertEqual(self.contar('outbox_evento'), 2)                  # nada se descartó

    def test_version_incompatible_y_datos_corruptos(self):
        self.insertar_crudo('PropuestaAceptada', '{"version": 99, "campos": {}}', 'EV-V99')
        self.insertar_crudo('PropuestaAceptada', '{"version": 1, "campos": {"evento_ref": {"$t": "vo", "clase": "Nada", "campos": {}}}}', 'EV-MAL')
        self.despachador().despachar()
        estados = {x.evento_id: (x.estado, x.error) for x in self.outbox.registros()}
        self.assertEqual(estados['EV-V99'][0], 'Revisión')
        self.assertIn('versión', estados['EV-V99'][1])
        self.assertEqual(estados['EV-MAL'][0], 'Revisión')
        self.assertEqual(self.r.llamadas, [])                               # ninguna reacción se ejecutó con datos dudosos


class PublicadorEstableDeClaves(unittest.TestCase):
    def test_la_clave_no_depende_del_orden_de_suscripcion(self):
        r = Reacciones()
        p1, p2 = PublicadorEstable(), PublicadorEstable()
        p1.suscribir(E.PropuestaAceptada, r.primera); p1.suscribir(E.PropuestaAceptada, r.segunda)
        p2.suscribir(E.PropuestaAceptada, r.segunda); p2.suscribir(E.PropuestaAceptada, r.primera)
        evento = E.PropuestaAceptada(agregado_id='X', ocurrido_en=OCURRIDO)
        self.assertEqual({k for k, _ in p1.reacciones(evento)}, {k for k, _ in p2.reacciones(evento)})

    def test_la_clave_incluye_modulo_clase_y_metodo_no_un_indice(self):
        clave = clave_de_reaccion(Reacciones().primera)
        self.assertTrue(clave.endswith('Reacciones.primera'), clave)
        self.assertNotIn('#', clave)

    def test_las_reacciones_reales_tienen_claves_unicas_y_estables(self):
        from application import reacciones as R
        from types import SimpleNamespace
        n = SimpleNamespace(notificar=lambda *a, **k: None)
        p = PublicadorEstable()
        R.suscribir_reacciones(p, R.ReaccionesEvento(None, None, None), R.ReaccionesSolicitudes(None, None, None, None, None, None, None),
                               R.ReaccionesPagos(None, None, None, None, None, None), R.ReaccionesNotificacion(n))
        for tipo in set(E.EventoDominio.__subclasses__()):
            evento = tipo(agregado_id='X', ocurrido_en=OCURRIDO)
            claves = [k for k, _ in p.reacciones(evento)]
            self.assertEqual(len(claves), len(set(claves)), tipo.__name__)
            self.assertTrue(all('<lambda>' not in k and '#' not in k for k in claves), claves)

    def test_una_reaccion_duplicada_para_el_mismo_evento_se_rechaza(self):
        r = Reacciones()
        p = PublicadorEstable()
        p.suscribir(E.PropuestaAceptada, r.primera)
        with self.assertRaises(ErrorDePersistencia):
            p.suscribir(E.PropuestaAceptada, r.primera)


if __name__ == '__main__':
    unittest.main()
