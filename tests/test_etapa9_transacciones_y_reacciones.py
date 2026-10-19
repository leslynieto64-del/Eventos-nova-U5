"""Etapa 9 — validación de invariantes, límites transaccionales, reacciones a Domain Events y dependencias entre capas."""
import ast, glob, os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D

RAIZ = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(RAIZ, 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                 # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada          # noqa: E402
from infrastructure.unidad_trabajo import UnitOfWorkMemoria, PublicadorEnProceso, DespachadorOutbox, RegistroOutbox  # noqa: E402
from domain.valores import ErrorDominio                                         # noqa: E402
from domain.eventos_dominio import EventoDominio, EventoCancelado, ContratacionConfirmada  # noqa: E402
from domain.valores import (Importe, Decision, DisponibilidadProveedor, CondicionesServicio, DatosEvento,  # noqa: E402
                            ResultadoViabilidad, ConceptoPago, TipoSolicitud, EstadoEvento, EstadoContrato)


class _Espia:
    """Registra qué raíces se inscriben en cada transacción del Unit of Work."""

    def __init__(self, uow):
        self.transacciones, original = [], uow.registrar

        def registrar(*agregados):
            self.transacciones.append(tuple(type(a).__name__ for a in agregados if a is not None))
            return original(*agregados)
        uow.registrar = registrar


class LimitesTransaccionales(unittest.TestCase):
    def test_una_raiz_por_transaccion_salvo_la_excepcion_documentada(self):     # Etapa 5, B-15
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        espia = _Espia(e.app.uow)
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia).datos['obligacion_id']
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + timedelta(hours=1), 'C-DJ'); e.d.despachar()
        s.confirmar_servicio_adicional(sa, dia + timedelta(hours=2)); e.d.despachar()
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', dia + timedelta(days=1)); e.d.despachar()
        varias = [t for t in espia.transacciones if len(t) > 1]
        self.assertGreater(len(espia.transacciones), 10)
        self.assertEqual(varias, [('EstadoCuenta', 'SolicitudServicioAdicional')])   # solo comunicarSolicitudPago()

    def test_falla_tecnica_revierte_y_no_publica_eventos(self):                 # Transacción: manejo de error
        e = Escenario(); e.confirmar_contratacion()
        en_outbox = len(e.app.uow.outbox)
        original = e.app.repos.eventos.guardar

        def guardar_con_falla(agregado):
            original(agregado)
            raise RuntimeError('falla de persistencia simulada')
        e.app.repos.eventos.guardar = guardar_con_falla
        with self.assertRaises(RuntimeError):                                   # las fallas técnicas se propagan
            e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', T0 + timedelta(days=3))
        e.app.repos.eventos.guardar = original
        self.assertEqual(e.evento().estado, EstadoEvento.EN_ORGANIZACION)       # el cambio no se hizo visible
        self.assertEqual(len(e.app.uow.outbox), en_outbox)                      # ningún Domain Event pendiente
        e.d.despachar()
        self.assertEqual(e.avisos('Evento cancelado'), [])

    def test_rechazo_de_negocio_no_cambia_el_agregado(self):                    # Responsabilidad: invariante en el dominio
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        revision = e.comunicacion + timedelta(hours=25)
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision); e.d.despachar()
        r = e.s.cierre.registrar_cancelacion_por_falta_de_regularizacion(e.evento_id, '', 'Coordinador', revision)
        self.assertFalse(r.exito)                                               # BN-005: el motivo es obligatorio
        self.assertEqual(e.evento().estado, EstadoEvento.EN_ORGANIZACION)
        self.assertFalse(any(isinstance(x.evento, EventoCancelado) for x in e.app.uow.outbox))

    def test_los_eventos_se_publican_despues_del_commit(self):                  # Etapa 5 (Outbox)
        e = Escenario()
        e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
        ob = e.obligacion('Anticipo')
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('3000.00')), T0 + timedelta(days=1), 'C-1')
        self.assertEqual(e.evento().estado, EstadoEvento.EN_GESTION)            # aún sin reacciones
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.FIRMADO)
        e.d.despachar()
        self.assertEqual(e.evento().estado, EstadoEvento.EN_ORGANIZACION)
        self.assertTrue(all(x.estado == 'Procesado' for x in e.app.uow.outbox))


class Reacciones(unittest.TestCase):
    def test_reaccion_que_falla_siempre_queda_en_revision(self):               # Outbox: sin reintentos infinitos
        uow, pub = UnitOfWorkMemoria(), PublicadorEnProceso()
        class Hecho(EventoDominio): pass
        def falla(e): raise RuntimeError('servicio externo no disponible')
        pub.suscribir(Hecho, falla)
        uow.outbox.append(RegistroOutbox(Hecho('X', T0)))
        DespachadorOutbox(uow, pub, max_intentos=3).despachar()
        self.assertEqual(uow.outbox[0].estado, 'Revisión')
        self.assertEqual(uow.outbox[0].intentos, 3)

    def test_evento_de_dominio_duplicado_no_duplica_efectos(self):             # idempotencia de las reacciones
        e = Escenario(); e.confirmar_contratacion()
        servicios = dict(e.evento().servicios)
        repetido = next(x.evento for x in e.app.uow.outbox if isinstance(x.evento, ContratacionConfirmada))
        e.app.uow.outbox.append(RegistroOutbox(repetido)); e.d.despachar()
        self.assertEqual(e.evento().servicios.keys(), servicios.keys())
        self.assertEqual(len([o for o in e.ec().obligaciones.values() if o.concepto == ConceptoPago.SALDO_CONTRATO_ORIGINAL]), 1)

    def test_cambio_confirmado_se_aplica_una_sola_vez(self):                   # BN-006, CA-041
        e = Escenario(); e.confirmar_contratacion()
        ev = e.evento()
        ev.aplicar_cambio_confirmado('SC-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 150))
        ev.aplicar_cambio_confirmado('SC-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 999))
        self.assertEqual(ev.datos.invitados_aproximados, 150)
        with self.assertRaises(ErrorDominio):                                   # servicio no contratado
            ev.aplicar_cambio_confirmado('SC-2', None, {'NO-EXISTE': CondicionesServicio('x')})


    def test_observacion_o02_evento_iniciado_antes_de_aplicar_el_cambio(self):   # BN-006, CA-041; observación O-02 (resuelta)
        """Decisión del stakeholder sobre O-02: un cambio confirmado antes del inicio se aplica al Evento aunque la
        reacción se procese después de iniciado; lo confirmado no queda sin aplicar ni pasa a «Revisión»."""
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=8)
        ev = e.evento(); sc_id = next(iter(ev.servicios))
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Ajuste sin costo', Importe(D(1)), dia,
                                                      condiciones_propuestas={sc_id: CondicionesServicio('Menú ajustado')}).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), None, dia)
        e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, dia))
        e.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', True, dia))
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo', dia); e.d.despachar()
        self.assertTrue(e.s.cambios.confirmar_cambio(sid, dia).exito)
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO)            # antes de despachar la reacción
        e.d.despachar()
        self.assertEqual([x for x in e.app.uow.outbox if x.estado == 'Revisión'], [])
        self.assertEqual(e.evento().estado, EstadoEvento.EN_EJECUCION)
        self.assertEqual(e.evento().servicios[sc_id].condiciones.descripcion, 'Menú ajustado')
        with self.assertRaises(ErrorDominio):                                   # sin confirmación previa al inicio, no se aplica
            e.evento().aplicar_cambio_confirmado('SC-X', None, {}, FECHA_EVENTO + timedelta(hours=1))


class DependenciasEntreCapas(unittest.TestCase):
    """Persistencia: el dominio no depende de SQL, ORM ni de la infraestructura; la aplicación no depende de la infraestructura."""

    PROHIBIDOS = ('sqlite3', 'sqlalchemy', 'psycopg', 'pymysql', 'django', 'peewee')

    def _imports(self, capa):
        mods = set()
        for f in glob.glob(os.path.join(RAIZ, 'src', capa, '*.py')):
            with open(f, encoding='utf8') as h:
                for n in ast.walk(ast.parse(h.read())):
                    if isinstance(n, ast.Import):
                        mods |= {a.name.split('.')[0] for a in n.names}
                    elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                        mods.add(n.module.split('.')[0])
        return mods

    def test_dominio_independiente(self):
        mods = self._imports('domain')
        self.assertFalse(mods & {'application', 'infrastructure', *self.PROHIBIDOS}, mods)

    def test_aplicacion_no_depende_de_infraestructura(self):
        mods = self._imports('application')
        self.assertFalse(mods & {'infrastructure', *self.PROHIBIDOS}, mods)


if __name__ == '__main__':
    unittest.main()
