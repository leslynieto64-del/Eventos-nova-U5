"""D-3 — llegada de la fecha y hora programadas (T) sin contratación confirmada (C-01, C-02, BN-009, BN-010, GL-032, GL-033,
CA-109, CA-110, CA-111) y D-3b (la contratación no puede confirmarse después de T).

Hallazgos del 28/10/2026: no había inicio automático; `POST /eventos/{id}/inicio` sobre un Evento `En gestión` respondía 422 y el Evento
seguía `En gestión`; el contrato solo se cerraba por el seguimiento de 24 h; y se podía confirmar la contratación después de T.
Decisiones internas aplicadas (no son aprobaciones externas): (1) el proceso periódico del trabajador procesa los eventos con T
vencida (`GestionCierreEventoService.procesar_eventos_vencidos`) y `POST /inicio` aplica la misma regla; (2) al llegar T se cierran
tanto el contrato `En preparación` como el `Firmado` sin confirmar (reutiliza `ProcesoContratacionCerrado`, que cierra el Evento y
devuelve el anticipo, decisión A); (3) se avisa a Cliente, Coordinador y Administración; (4) T se compara con el reloj del servidor,
sin zona (igual que el resto de fechas); (5) la confirmación con `ahora >= T` se rechaza con el motivo de CA-110.
Ejecutar desde la raíz:  python -m unittest tests.test_d3_llegada_de_t -v"""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient                                          # noqa: E402
from apoyo_bd import BaseConBD                                                      # noqa: E402
from apoyo_flujo import Flujo                                                       # noqa: E402
from api.dependencias import obtener_reloj                                          # noqa: E402
from api.main import crear_app                                                      # noqa: E402
from domain.contrato import AccionContrato, MAQUINA_CONTRATO                        # noqa: E402
from domain.valores import (EstadoContrato as EC, EstadoEvento as EE, EstadoObligacionPago as EO, Importe,   # noqa: E402
                            TipoDevolucion, ErrorDominio)
from infrastructure.composicion import construir                                    # noqa: E402
from infrastructure.persistencia import trabajador_outbox                           # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente   # noqa: E402
from test_reglas_corregidas import T0, FECHA_EVENTO, CONTENIDO                      # noqa: E402

T = FECHA_EVENTO
SEG = timedelta(seconds=1)
MOTIVO_T = 'ya no puede confirmarse'


class LlegadaDeT:
    """Mixin. Requiere `crear_contenedor()` y `registros_outbox()`."""

    def preparar(self):
        self.app = self.crear_contenedor()
        self.cierre = self.app.servicios.cierre
        self.repos = self.app.repos

    # ---- construcción de escenarios
    def firmado(self):
        return Flujo(self.app).contratar(confirmar=False)

    def en_preparacion(self):
        f = Flujo(self.app)
        f.evento_id = f.registrar_evento()
        f.propuesta_id = self.app.servicios.propuestas.crear_propuesta(f.evento_id, CONTENIDO, T0).datos['propuesta_id']
        p = self.repos.propuestas.obtener_por_id(f.propuesta_id)
        self.app.servicios.propuestas.aceptar_propuesta(f.propuesta_id, p.version_vigente_id, T0)
        self.app.despachador.despachar()
        f.contrato_id = self.app.servicios.contratacion.preparar_contrato(f.propuesta_id, True).datos['contrato_id']
        return f

    def solo_evento(self):
        f = Flujo(self.app)
        f.evento_id = f.registrar_evento()
        return f

    def pagar_anticipo(self, f, fecha, verificar=True):
        ob = f.obligacion('Anticipo')
        r = self.app.servicios.pagos.registrar_y_verificar_pago(f.ec_id, ob.obligacion_id, Importe(D('3000')), fecha, 'A-' + f.evento_id[-6:],
                                                               registrado_en=fecha, verificar_ahora=verificar)
        self.assertTrue(r.exito, r.mensaje)
        return r

    def estados(self, f):
        return (self.repos.eventos.obtener_por_id(f.evento_id).estado,
                self.repos.contratos.obtener_por_id(f.contrato_id).estado if getattr(f, 'contrato_id', None) else None)

    def procesar(self, ahora):
        r = self.cierre.procesar_eventos_vencidos(ahora)
        self.assertTrue(r.exito, r.mensaje)
        self.app.despachador.despachar()
        return r

    # ---- C-01: Evento En gestión al llegar T
    def test_contrato_firmado_sin_confirmar_en_T_cierra_el_evento_y_el_contrato(self):
        f = self.firmado()
        self.assertEqual(self.estados(f), (EE.EN_GESTION, EC.FIRMADO))
        self.procesar(T)
        self.assertEqual(self.estados(f), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))       # nunca Cancelado
        self.assertEqual(f.obligacion('Anticipo').estado, EO.SIN_EFECTO)                                  # C-04: pendiente → Sin efecto
        self.assertEqual(self.repos.estados_cuenta.obtener_por_id(f.ec_id).devoluciones, [])               # sin dinero recibido, nada que devolver

    def test_un_segundo_antes_de_T_no_cambia_nada(self):
        f = self.firmado()
        antes = self.registros_outbox()
        r = self.procesar(T - SEG)
        self.assertEqual(self.estados(f), (EE.EN_GESTION, EC.FIRMADO))
        self.assertEqual(self.registros_outbox(), antes)
        self.assertEqual(r.datos['cerrados'] + r.datos['iniciados'], 0)

    def test_contrato_en_preparacion_en_T_tambien_se_cierra(self):
        f = self.en_preparacion()
        self.assertEqual(self.estados(f), (EE.EN_GESTION, EC.EN_PREPARACION))
        self.procesar(T)
        self.assertEqual(self.estados(f), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))

    def test_un_evento_sin_contrato_en_T_queda_cerrado_sin_contratacion(self):
        f = self.solo_evento()
        self.procesar(T)
        self.assertEqual(self.repos.eventos.obtener_por_id(f.evento_id).estado, EE.CERRADO_SIN_CONTRATACION)

    def test_el_anticipo_recibido_se_devuelve_al_cerrar_por_T(self):                    # CA-110 → CA-102 a CA-105
        f = self.firmado()
        self.pagar_anticipo(f, T0 + timedelta(days=1))                                   # verificado, pero sin política comunicada: no se confirma
        self.assertEqual(self.estados(f)[1], EC.FIRMADO)
        self.procesar(T)
        ec = self.repos.estados_cuenta.obtener_por_id(f.ec_id)
        self.assertEqual(self.estados(f), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))
        self.assertEqual(f.obligacion('Anticipo').estado, EO.LIQUIDADA)                   # el Liquidado conserva su estado (C-04)
        self.assertEqual([(d.tipo, d.importe.cantidad) for d in ec.devoluciones], [(TipoDevolucion.ANTICIPO_CONTRATACION_CERRADA, D('3000'))])

    def test_un_pago_registrado_antes_de_T_y_verificado_despues_se_verifica_sin_confirmar_y_se_devuelve(self):   # CA-110
        f = self.firmado()
        r = self.pagar_anticipo(f, T - timedelta(days=1), verificar=False)
        self.procesar(T)
        v = self.app.servicios.pagos.verificar_pago_registrado(f.ec_id, r.datos['pago_id'], T + timedelta(hours=2))
        self.assertTrue(v.exito, v.mensaje)
        self.app.despachador.despachar()
        ec = self.repos.estados_cuenta.obtener_por_id(f.ec_id)
        self.assertEqual(self.estados(f), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))          # no se confirma ni se reactiva
        self.assertEqual(len(ec.devoluciones), 1)

    def test_se_avisa_a_cliente_coordinador_y_administracion(self):
        f = self.firmado()
        self.procesar(T)
        avisos = [a for a in self.app.notificador.enviados if a[1] == 'Evento cerrado sin contratación']
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0][0], ('Cliente', 'Coordinador', 'Administración'))

    # ---- CA-109 / CA-111: Evento En organización al llegar T
    def test_evento_en_organizacion_inicia_en_T_y_cierra_las_solicitudes_no_confirmadas(self):
        f = Flujo(self.app).contratar()
        sc = self.app.servicios.cambios.registrar_solicitud_cambio(f.evento_id, f.contrato_id, 'Cambio de menú', Importe(D('0')), T - timedelta(days=10))
        sa = self.app.servicios.adicionales.registrar_solicitud_servicio_adicional(f.evento_id, f.contrato_id, 'Fotografía', T - timedelta(days=10))
        self.assertTrue(sc.exito and sa.exito)
        self.procesar(T - SEG)
        self.assertEqual(self.repos.eventos.obtener_por_id(f.evento_id).estado, EE.EN_ORGANIZACION)
        self.procesar(T)                                                                  # límite inclusivo en T (CA-109)
        self.assertEqual(self.repos.eventos.obtener_por_id(f.evento_id).estado, EE.EN_EJECUCION)
        self.assertFalse(self.repos.cambios.obtener_por_id(sc.datos['solicitud_id']).pendiente)
        self.assertFalse(self.repos.adicionales.obtener_por_id(sa.datos['solicitud_id']).pendiente)
        self.assertEqual(self.repos.cambios.obtener_por_id(sc.datos['solicitud_id']).estado.value, 'Cerrada por inicio del evento')

    # ---- idempotencia, aislamiento y recuperación
    def test_un_segundo_ciclo_no_repite_ni_duplica_nada(self):
        f = self.firmado()
        self.procesar(T)
        despues_primero = self.registros_outbox()
        r = self.procesar(T + timedelta(minutes=5))
        self.assertEqual(r.datos['cerrados'] + r.datos['iniciados'], 0)
        self.assertEqual(self.registros_outbox(), despues_primero)
        self.assertEqual(self.estados(f), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))

    def test_los_eventos_cancelados_finalizados_o_ya_cerrados_no_se_procesan(self):
        f = Flujo(self.app).contratar()
        self.assertTrue(self.cierre.gestionar_cancelacion_solicitada(f.evento_id, 'Desiste', T - timedelta(days=5)).exito)
        self.app.despachador.despachar()
        r = self.procesar(T + timedelta(days=1))
        self.assertEqual(self.repos.eventos.obtener_por_id(f.evento_id).estado, EE.CANCELADO)
        self.assertEqual(r.datos['cerrados'] + r.datos['iniciados'], 0)

    def test_un_fallo_en_un_evento_no_impide_procesar_los_demas_y_se_recupera_en_el_ciclo_siguiente(self):
        a, b = self.firmado(), self.firmado()
        original = type(self.cierre).procesar_inicio_evento
        def falla_con_a(servicio, evento_id, ahora):
            if evento_id == a.evento_id:
                raise RuntimeError('fallo técnico simulado')
            return original(servicio, evento_id, ahora)
        with mock.patch.object(type(self.cierre), 'procesar_inicio_evento', falla_con_a):
            r = self.procesar(T)
        self.assertEqual(r.datos['errores'], 1)
        self.assertEqual(self.estados(a), (EE.EN_GESTION, EC.FIRMADO))                    # el que falló no cambió
        self.assertEqual(self.estados(b), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))
        self.procesar(T + timedelta(seconds=30))                                          # el ciclo siguiente lo recupera
        self.assertEqual(self.estados(a), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))

    def test_el_trabajador_aplica_la_regla_y_despacha_las_reacciones_en_un_ciclo(self):
        f = self.firmado()
        trabajador_outbox.ejecutar(self.app, una_vez=True, reloj=lambda: T)
        self.assertEqual(self.estados(f), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))

    # ---- POST /eventos/{id}/inicio aplica la misma regla
    def cliente(self, ahora):
        app = crear_app(lambda: self.app)
        app.dependency_overrides[obtener_reloj] = lambda: (lambda: ahora)
        return TestClient(app)

    def test_http_inicio_de_un_evento_en_gestion_antes_de_T_se_rechaza(self):
        f = self.firmado()
        r = self.cliente(T - SEG).post(f'/eventos/{f.evento_id}/inicio')
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(self.estados(f), (EE.EN_GESTION, EC.FIRMADO))

    def test_http_inicio_de_un_evento_en_gestion_en_T_lo_cierra_sin_contratacion(self):
        f = self.firmado()
        r = self.cliente(T).post(f'/eventos/{f.evento_id}/inicio')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.estados(f), (EE.CERRADO_SIN_CONTRATACION, EC.CERRADO_SIN_CONFIRMAR))
        self.assertEqual(self.cliente(T).post(f'/eventos/{f.evento_id}/inicio').status_code, 422)        # un evento cerrado ya no inicia

    # ---- D-3b: la contratación no puede confirmarse después de T (CA-110, GL-032)
    def test_la_confirmacion_en_T_o_despues_se_rechaza_y_un_segundo_antes_se_permite(self):
        f = self.firmado()
        self.app.servicios.contratacion.registrar_comunicacion_politica_no_reembolso(f.contrato_id, T0)
        self.pagar_anticipo(f, T0 + timedelta(days=1), verificar=False)
        pago = next(p for p in f.ec().pagos)
        self.app.servicios.pagos.verificar_pago_registrado(f.ec_id, pago.pago_id, T0 + timedelta(days=2))
        self.app.despachador.despachar()
        # la reacción ya confirmó (verificado antes de T): se prueba el caso aparte con un segundo contrato
        g = self.firmado()
        self.app.servicios.contratacion.registrar_comunicacion_politica_no_reembolso(g.contrato_id, T0)
        self.pagar_anticipo(g, T0 + timedelta(days=1), verificar=False)
        pago_g = next(p for p in g.ec().pagos)
        v = self.app.servicios.pagos.verificar_pago_registrado(g.ec_id, pago_g.pago_id, T)       # verificado justo en T: la reacción no confirma
        self.assertTrue(v.exito, v.mensaje)
        self.app.despachador.despachar()
        self.assertEqual(self.estados(g), (EE.EN_GESTION, EC.FIRMADO))
        r = self.app.servicios.contratacion.confirmar_contratacion(g.contrato_id, T)
        self.assertFalse(r.exito)
        self.assertIn(MOTIVO_T, r.mensaje)
        self.assertEqual(self.estados(g), (EE.EN_GESTION, EC.FIRMADO))
        ok = self.app.servicios.contratacion.confirmar_contratacion(g.contrato_id, T - SEG)
        self.assertTrue(ok.exito, ok.mensaje)
        self.assertEqual(self.estados(f)[1], EC.CONTRATACION_CONFIRMADA)                        # el verificado antes de T sí se confirmó

    def test_http_confirmar_despues_de_T_responde_422(self):
        g = self.firmado()
        self.app.servicios.contratacion.registrar_comunicacion_politica_no_reembolso(g.contrato_id, T0)
        self.pagar_anticipo(g, T0 + timedelta(days=1), verificar=False)
        pago = next(p for p in g.ec().pagos)
        self.app.servicios.pagos.verificar_pago_registrado(g.ec_id, pago.pago_id, T + timedelta(hours=1))
        self.app.despachador.despachar()
        r = self.cliente(T + timedelta(hours=1)).post(f'/contratos/{g.contrato_id}/confirmacion')
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn(MOTIVO_T, r.json()['detalle'])


class MaquinaDelContrato(unittest.TestCase):
    """El contrato se cierra por la llegada de T solo desde En preparación y Firmado."""

    def test_transiciones_permitidas_y_prohibidas(self):
        for origen in (EC.EN_PREPARACION, EC.FIRMADO):
            self.assertEqual(MAQUINA_CONTRATO.transitar(origen, AccionContrato.CERRAR_POR_INICIO), EC.CERRADO_SIN_CONFIRMAR)
        for origen in (EC.CONTRATACION_CONFIRMADA, EC.CERRADO_SIN_CONFIRMAR):
            with self.assertRaises(ErrorDominio):
                MAQUINA_CONTRATO.validar(origen, AccionContrato.CERRAR_POR_INICIO)


class EnMemoria(LlegadaDeT, unittest.TestCase):
    def setUp(self):
        self.preparar()

    def crear_contenedor(self):
        return construir()

    def registros_outbox(self):
        return [(type(r.evento).__name__, r.estado) for r in self.app.uow.outbox]


class EnPostgreSQL(LlegadaDeT, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        self.preparar()

    def crear_contenedor(self):
        return construir_persistente(motor=self.motor)

    def registros_outbox(self):
        return sorted((r.tipo if hasattr(r, 'tipo') else str(r), r.estado) for r in self.app.outbox.registros())


if __name__ == '__main__':
    unittest.main()
