"""Etapa 3 (fase final): control de concurrencia optimista y reintentos del Outbox sin duplicar efectos de negocio.

Estrategia: cada raíz de agregado lleva `version` (revisión 0004). `guardar` hace `UPDATE ... WHERE version = <leída>`; si otra
transacción cambió el agregado antes, lanza ConflictoDeConcurrencia y la operación entera se revierte, en vez de «gana la última».
No hay bloqueo global: solo compiten las escrituras del MISMO agregado; agregados distintos no se esperan.
Entrega del Outbox: AL MENOS UNA VEZ con deduplicación por reacción (clave estable); NO se afirma «exactamente una vez».
Los repositorios en memoria no usan versión (un solo proceso, sin transacciones concurrentes).
Ejecutar desde la raíz:  python -m unittest tests.test_concurrencia_optimista -v"""
import os, sys, threading, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import sqlalchemy as sa                                                                   # noqa: E402
import apoyo_persistencia as A                                                            # noqa: E402
from apoyo_bd import BaseConBD                                                            # noqa: E402
from test_persistencia_outbox import Base as BaseOutbox                                   # noqa: E402
from test_persistencia_repositorios import FabricaSQL, ORDEN_DE_GUARDADO                  # noqa: E402
from application.servicios import transaccion                                             # noqa: E402
from domain import eventos_dominio as E                                                   # noqa: E402
from domain.valores import EstadoObligacionPago as EO, Importe                            # noqa: E402
from infrastructure.persistencia import repositorios_sql as S                             # noqa: E402
from infrastructure.persistencia.errores import ConflictoDeConcurrencia                   # noqa: E402
from infrastructure.persistencia.unidad_trabajo_sql import UnitOfWorkSQL                  # noqa: E402

T0 = A.T0


class Base(BaseConBD):
    def setUp(self):
        super().setUp()
        self.f = FabricaSQL(self.almacen)
        self.uow = UnitOfWorkSQL(self.almacen, None)
        escenarios = A.todos()
        self.por_repo = {'propuestas': escenarios['Propuesta'], 'contratos': escenarios['Contrato'], 'eventos': escenarios['Evento'],
                         'estados_cuenta': escenarios['EstadoCuenta'], 'cambios': escenarios['SolicitudCambio'],
                         'adicionales': escenarios['SolicitudServicioAdicional'], 'sustituciones': escenarios['SustitucionProveedor']}
        for nombre in ORDEN_DE_GUARDADO:
            for ag in self.por_repo[nombre]:
                self.f.guardar(getattr(self.f.repos, nombre), ag)

    def version_en_bd(self, tabla, columna, id_):
        with self.motor.connect() as con:
            return con.execute(sa.text(f'select version from "{tabla}" where "{columna}" = :i'), {'i': id_}).scalar()

    def pendiente(self, ec):
        return next(o for o in ec.obligaciones.values() if o.estado != EO.SIN_EFECTO)      # cualquier obligación que admita pagos


class VersionesObsoletas(Base):
    def test_un_agregado_nuevo_empieza_en_la_version_0_y_cada_guardado_la_sube(self):
        ev = self.f.repos.eventos.obtener_por_id('EV-1')
        self.assertEqual(ev._version, 0)
        self.f.repos.eventos.guardar(ev)
        self.assertEqual((ev._version, self.version_en_bd('evento', 'evento_id', 'EV-1')), (1, 1))
        self.f.repos.eventos.guardar(ev)                                   # guardar dos veces el mismo objeto es válido
        self.assertEqual(self.version_en_bd('evento', 'evento_id', 'EV-1'), 2)

    def test_la_copia_obsoleta_no_pisa_el_cambio_ya_confirmado(self):
        r = self.f.repos.estados_cuenta
        ec_a, ec_b = r.obtener_por_id('EC-2'), r.obtener_por_id('EC-2')
        n = len(ec_a.pagos)
        ec_a.registrar_y_verificar_pago('PG-A', self.pendiente(ec_a).obligacion_id, Importe(D('10')), T0, 'CA', False)
        r.guardar(ec_a)
        ec_b.registrar_y_verificar_pago('PG-B', self.pendiente(ec_b).obligacion_id, Importe(D('20')), T0, 'CB', False)
        with self.assertRaises(ConflictoDeConcurrencia) as ctx:
            r.guardar(ec_b)
        self.assertEqual((ctx.exception.agregado, ctx.exception.identificador), ('estado_cuenta', 'EC-2'))
        guardado = r.obtener_por_id('EC-2')
        self.assertEqual([p.pago_id for p in guardado.pagos][n:], ['PG-A'])      # PG-B no existe: no hubo cambios parciales
        self.assertEqual(self.contar('pago'), sum(len(x.pagos) for x in r.listar_todos()))

    def test_tras_el_conflicto_leer_de_nuevo_y_reintentar_funciona(self):
        r = self.f.repos.estados_cuenta
        ec_a, ec_b = r.obtener_por_id('EC-2'), r.obtener_por_id('EC-2')
        ec_a.registrar_y_verificar_pago('PG-A', self.pendiente(ec_a).obligacion_id, Importe(D('10')), T0, 'CA', False); r.guardar(ec_a)
        with self.assertRaises(ConflictoDeConcurrencia):
            r.guardar(ec_b)
        reintento = r.obtener_por_id('EC-2')
        reintento.registrar_y_verificar_pago('PG-B', self.pendiente(reintento).obligacion_id, Importe(D('20')), T0, 'CB', False)
        r.guardar(reintento)
        self.assertTrue({'PG-A', 'PG-B'} <= {p.pago_id for p in r.obtener_por_id('EC-2').pagos})   # ninguna actualización se perdió

    def test_las_siete_raices_detectan_la_copia_obsoleta(self):
        for nombre, ejemplo in (('propuestas', 'PR-1'), ('contratos', 'CT-1'), ('eventos', 'EV-1'), ('estados_cuenta', 'EC-1'),
                                ('cambios', 'SC-1'), ('adicionales', 'SA-1'), ('sustituciones', 'SP-1')):
            with self.subTest(nombre):
                repo = getattr(self.f.repos, nombre)
                uno, otro = repo.obtener_por_id(ejemplo), repo.obtener_por_id(ejemplo)
                repo.guardar(uno)
                with self.assertRaises(ConflictoDeConcurrencia):
                    repo.guardar(otro)

    def test_crear_con_un_id_que_ya_existe_nunca_sobrescribe(self):
        nuevo = A.eventos()[0]                                             # EV-1 ya existe
        with self.assertRaises(ConflictoDeConcurrencia):
            self.f.repos.eventos.guardar(nuevo)
        self.assertEqual(self.version_en_bd('evento', 'evento_id', 'EV-1'), 0)

    def test_un_agregado_borrado_o_inexistente_con_version_leida_es_conflicto(self):
        ev = self.f.repos.eventos.obtener_por_id('EV-3') or self.f.repos.eventos.listar_todos()[0]
        ev._version = 99                                                   # versión que no corresponde a la base
        with self.assertRaises(ConflictoDeConcurrencia):
            self.f.repos.eventos.guardar(ev)


class EscritoresSimultaneos(Base):
    def test_dos_hilos_modifican_el_mismo_agregado_y_solo_uno_se_confirma(self):
        for ronda in range(5):
            r = self.f.repos.estados_cuenta
            ob = self.pendiente(r.obtener_por_id('EC-2')).obligacion_id
            antes = len(r.obtener_por_id('EC-2').pagos)
            barrera = threading.Barrier(2, timeout=15)
            resultados = {}

            def escritor(nombre):
                try:
                    ec = r.obtener_por_id('EC-2')                           # ambos leen la misma versión
                    barrera.wait()
                    self.uow.iniciar(); self.uow.registrar(ec)
                    ec.registrar_y_verificar_pago(f'PG-{nombre}-{ronda}', ob, Importe(D('1')), T0, f'{nombre}-{ronda}', False)
                    r.guardar(ec)
                    self.uow.confirmar()
                    resultados[nombre] = 'ok'
                except ConflictoDeConcurrencia:
                    self.uow.revertir()
                    resultados[nombre] = 'conflicto'

            hilos = [threading.Thread(target=escritor, args=(n,)) for n in ('X', 'Y')]
            [h.start() for h in hilos]; [h.join(30) for h in hilos]
            self.assertFalse(any(h.is_alive() for h in hilos))
            self.assertEqual(sorted(resultados.values()), ['conflicto', 'ok'], resultados)
            despues = r.obtener_por_id('EC-2')
            self.assertEqual(len(despues.pagos), antes + 1)                  # exactamente una actualización, ninguna perdida ni mezclada
            ganador = next(n for n, v in resultados.items() if v == 'ok')
            self.assertIn(f'PG-{ganador}-{ronda}', {p.pago_id for p in despues.pagos})

    def test_agregados_distintos_no_se_bloquean_entre_si(self):
        ec, ev = self.f.repos.estados_cuenta.obtener_por_id('EC-1'), self.f.repos.eventos.obtener_por_id('EV-1')
        self.uow.iniciar(); self.uow.registrar(ec); self.f.repos.estados_cuenta.guardar(ec)        # transacción abierta sobre EC-1
        otro = UnitOfWorkSQL(self.almacen, None)
        hecho = threading.Event()

        def escribir_evento():
            otro.iniciar(); self.f.repos.eventos.guardar(ev); otro.confirmar(); hecho.set()

        h = threading.Thread(target=escribir_evento); h.start()
        self.assertTrue(hecho.wait(10), 'la escritura de otro agregado no debe esperar a la transacción abierta de EC-1')
        self.uow.revertir(); h.join(5)

    def test_una_operacion_con_conflicto_se_revierte_completa(self):
        ec_obsoleto = self.f.repos.estados_cuenta.obtener_por_id('EC-1')
        self.f.repos.estados_cuenta.guardar(self.f.repos.estados_cuenta.obtener_por_id('EC-1'))     # otro escritor avanzó la versión
        ev = self.f.repos.eventos.obtener_por_id('EV-1')
        version_evento = self.version_en_bd('evento', 'evento_id', 'EV-1')
        with self.assertRaises(ConflictoDeConcurrencia):
            with transaccion(self.uow, ev, ec_obsoleto):
                self.f.repos.eventos.guardar(ev)                            # este cambio sí era válido…
                self.f.repos.estados_cuenta.guardar(ec_obsoleto)            # …pero el conflicto revierte toda la operación
        self.assertEqual(self.version_en_bd('evento', 'evento_id', 'EV-1'), version_evento)
        self.assertEqual(self.motor.pool.checkedout(), 0)


class ConflictoEnLaApi(BaseConBD):
    def test_el_conflicto_se_responde_409_sin_detalles_internos(self):
        from fastapi.testclient import TestClient
        from api.main import crear_app
        from infrastructure.persistencia.composicion_persistente import construir_persistente
        contenedor = construir_persistente(motor=self.motor)

        def conflicto(*a, **k):
            raise ConflictoDeConcurrencia('El agregado evento EV-1 cambió desde que se leyó', 'evento', 'EV-1')

        contenedor.servicios.propuestas.registrar_evento = conflicto
        with TestClient(crear_app(lambda: contenedor), raise_server_exceptions=False) as cliente:
            r = cliente.post('/eventos', json={'cliente_id': 'CL-1', 'datos': {'tipo': 'Boda', 'fecha_hora': '2030-01-01T18:00:00', 'lugar': 'Salón',
                                                                   'invitados_aproximados': 10}, 'servicios': ['Banquete']})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['tipo'], 'conflicto_de_concurrencia')
        self.assertNotIn('EV-1', r.text)


class ConflictoRealEnLaApi(BaseConBD):
    """Un conflicto REAL (no simulado): otra transacción cambia el agregado entre la lectura y el guardado de la petición."""
    def test_un_pago_por_http_con_el_agregado_obsoleto_responde_409_y_no_deja_cambios(self):
        from fastapi.testclient import TestClient
        from api.main import crear_app
        from infrastructure.persistencia.composicion_persistente import construir_persistente
        from test_persistencia_devolucion_anticipo import Flujo
        contenedor = construir_persistente(motor=self.motor)
        f = Flujo(contenedor)
        repo = contenedor.repos.estados_cuenta
        ob = next(o for o in f.ec().obligaciones.values() if o.concepto.value == 'Anticipo').obligacion_id
        cuerpo = {'obligacion_id': ob, 'importe': '3000.00', 'fecha': '2026-10-02T10:00:00', 'comprobante': 'C-HTTP'}
        original = repo.guardar
        interferencias = []

        def guardar_con_interferencia(agregado):
            if not interferencias:                                   # otra transacción avanza la versión justo antes
                interferencias.append(1)
                otra = repo.obtener_por_id(agregado.id)
                original(otra)
            return original(agregado)

        repo.guardar = guardar_con_interferencia
        try:
            with TestClient(crear_app(lambda: contenedor), raise_server_exceptions=False) as cliente:
                r = cliente.post(f'/estados-cuenta/{f.ec_id}/pagos', json=cuerpo)
                self.assertEqual(r.status_code, 409, r.text)
                self.assertEqual(r.json()['tipo'], 'conflicto_de_concurrencia')
                self.assertEqual(self.contar('pago'), 0)                    # sin cambios parciales
                with self.motor.connect() as con:
                    tipos = sorted(con.execute(sa.text('select tipo_evento from outbox_evento')).scalars())
                self.assertEqual(tipos, ['ContratoFirmado', 'PropuestaAceptada'])   # solo los hechos previos: ninguno del pago rechazado
                repo.guardar = original
                r2 = cliente.post(f'/estados-cuenta/{f.ec_id}/pagos', json=cuerpo)      # releer y repetir sí funciona
                self.assertEqual(r2.status_code, 201, r2.text)
                self.assertEqual(self.contar('pago'), 1)
        finally:
            repo.guardar = original


class ReintentosDelOutbox(BaseOutbox):
    def test_un_conflicto_de_concurrencia_en_una_reaccion_se_reintenta_y_no_se_pierde(self):
        a = self.aceptada()[0]
        self.registrar(a)
        llamadas = {'n': 0}

        class Reaccion:
            def primera(_, e):
                llamadas['n'] += 1
                if llamadas['n'] == 1:
                    raise ConflictoDeConcurrencia('otro escritor cambió el agregado', 'estado_cuenta', 'EC-1')

            def segunda(_, e): self.r.segunda(e)

        d = self.despachador(reacciones=Reaccion(), max_intentos=3)
        d.despachar()
        reg = self.registro(a)
        self.assertEqual((reg.estado, reg.intentos), ('Procesado', 1))       # un intento fallido y un reintento correcto
        self.assertEqual((llamadas['n'], self.r.contar('segunda')), (2, 1))   # la reacción hermana no se repitió

    def test_si_el_conflicto_persiste_el_evento_pasa_a_revision_sin_perderse(self):
        a = self.aceptada()[0]
        self.registrar(a)

        class Siempre:
            def primera(_, e): raise ConflictoDeConcurrencia('conflicto persistente')
            def segunda(_, e): pass

        self.despachador(reacciones=Siempre(), max_intentos=2).despachar()
        reg = self.registro(a)
        self.assertEqual(reg.estado, 'Revisión')
        self.assertIn('conflicto persistente', reg.error)


class IdempotenciaDeEfectosDeNegocio(unittest.TestCase):
    """Reaplicar una reacción (caída entre ejecutarla y anotarla) no duplica efectos financieros ni transiciones."""
    def test_reaplicar_las_reacciones_de_pagos_no_duplica_obligaciones_ni_devoluciones(self):
        from infrastructure.composicion import construir
        from test_reglas_corregidas import Escenario
        e = Escenario()
        e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
        ob = e.obligacion('Anticipo')
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('3000')), T0 + timedelta(days=1), 'C'); e.d.despachar()
        antes = {'obligaciones': len(e.ec().obligaciones), 'pagos': len(e.ec().pagos), 'devoluciones': len(e.ec().devoluciones),
                 'estado': e.app.repos.contratos.obtener_por_id(e.contrato_id).estado}
        reaccion = e.app.servicios.pagos
        for _ in range(3):                                                   # la misma reacción vuelve a ejecutarse
            reaccion.registrar_obligacion_anticipo(e.contrato_id)
            reaccion.registrar_obligacion_saldo_original(e.contrato_id)
            e.app.servicios.contratacion.confirmar_contratacion(e.contrato_id, T0 + timedelta(days=2))
        self.assertEqual({'obligaciones': len(e.ec().obligaciones), 'pagos': len(e.ec().pagos),
                          'devoluciones': len(e.ec().devoluciones),
                          'estado': e.app.repos.contratos.obtener_por_id(e.contrato_id).estado}, antes)


if __name__ == '__main__':
    unittest.main()
