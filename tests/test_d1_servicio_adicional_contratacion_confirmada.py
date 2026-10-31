"""D-1 — un servicio adicional solo puede registrarse con la contratación confirmada (C-14, GL-015, BRD, CA-101).

Hallazgo del 28/10/2026: con el contrato solo `Firmado` y el Evento `En gestión`, `registrar_solicitud_servicio_adicional` creaba la
solicitud (HTTP 201). CA-101 exige no registrarla, informar al Cliente y no evaluar el plazo mínimo ni el saldo vencido. Estas
pruebas fijan el comportamiento corregido sobre la composición en memoria y sobre PostgreSQL de pruebas (mismos casos), y por HTTP.
No cambian ninguna regla aprobada: comprueban que la regla de CA-101 se cumple y que el resto del flujo (plazo de cinco días,
evento cancelado, registro correcto) se conserva.
Ejecutar desde la raíz:  python -m unittest tests.test_d1_servicio_adicional_contratacion_confirmada -v"""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient                                          # noqa: E402
from apoyo_bd import BaseConBD                                                      # noqa: E402
from apoyo_flujo import Flujo                                                       # noqa: E402
from apoyo_persistencia import estado_de                                            # noqa: E402
from api.dependencias import obtener_reloj                                          # noqa: E402
from api.main import crear_app                                                      # noqa: E402
from domain.valores import EstadoContrato, EstadoEvento, EstadoSolicitudServicioAdicional as ESA   # noqa: E402
from infrastructure.composicion import construir                                    # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente   # noqa: E402
from test_reglas_corregidas import T0, FECHA_EVENTO, CONTENIDO                                 # noqa: E402

MENSAJE = 'Un servicio adicional solo puede registrarse con la contratación confirmada (CA-101).'
MOTIVO_PLAZO = 'Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).'
DIA_VALIDO = FECHA_EVENTO - timedelta(days=10)          # diez días naturales: plazo cumplido
DIA_SIN_PLAZO = FECHA_EVENTO - timedelta(days=4)        # cuatro días naturales: plazo incumplido


class ServicioAdicionalExigeContratacionConfirmada:
    """Mixin. Requiere `crear_contenedor()` y `registros_outbox()`."""

    def preparar(self):
        self.app = self.crear_contenedor()
        self.adicionales = self.app.servicios.adicionales

    def firmado(self):
        return Flujo(self.app).contratar(confirmar=False)           # contrato firmado, evento En gestión

    def confirmado(self):
        return Flujo(self.app).contratar()                          # contratación confirmada, evento En organización

    def solicitar(self, flujo, ahora):
        return self.adicionales.registrar_solicitud_servicio_adicional(flujo.evento_id, flujo.contrato_id, 'Fotografía', ahora)

    def instantanea(self, flujo):
        r = self.app.repos
        return {'ec': estado_de(r.estados_cuenta.obtener_por_id(flujo.ec_id)), 'contrato': estado_de(r.contratos.obtener_por_id(flujo.contrato_id)),
                'evento': estado_de(r.eventos.obtener_por_id(flujo.evento_id)), 'adicionales': len(r.adicionales.listar_todas()),
                'outbox': self.registros_outbox()}

    # ---- el defecto D-1: contrato solo firmado
    def test_un_contrato_solo_firmado_no_permite_registrar_el_servicio_adicional(self):
        f = self.firmado()
        self.assertEqual(f.evento().estado, EstadoEvento.EN_GESTION)
        self.assertEqual(self.app.repos.contratos.obtener_por_id(f.contrato_id).estado, EstadoContrato.FIRMADO)
        antes = self.instantanea(f)
        r = self.solicitar(f, T0)
        self.assertFalse(r.exito)
        self.assertEqual(r.mensaje, MENSAJE)
        self.assertEqual(self.instantanea(f), antes)               # no se crea solicitud ni cambia agregado, obligación ni Outbox

    def test_el_rechazo_informa_al_cliente(self):
        f = self.firmado()
        self.solicitar(f, T0)
        self.assertIn((('Cliente',), 'Servicio adicional no registrado', MENSAJE), self.app.notificador.enviados)

    def test_con_la_contratacion_sin_confirmar_no_se_evalua_el_plazo_ni_el_saldo(self):   # CA-101
        f = self.firmado()
        for nombre, ahora in {'plazo cumplido': DIA_VALIDO, 'plazo incumplido': DIA_SIN_PLAZO}.items():
            with self.subTest(caso=nombre):
                r = self.solicitar(f, ahora)
                self.assertFalse(r.exito)
                self.assertEqual(r.mensaje, MENSAJE)                # el motivo es la contratación, no el plazo (CA-077/083)
        self.assertEqual(self.app.repos.adicionales.listar_todas(), [])

    def test_un_contrato_en_preparacion_tampoco_permite_registrarlo(self):
        flujo = Flujo(self.app)
        flujo.evento_id = flujo.registrar_evento()
        flujo.propuesta_id = self.app.servicios.propuestas.crear_propuesta(flujo.evento_id, CONTENIDO, T0).datos['propuesta_id']
        p = self.app.repos.propuestas.obtener_por_id(flujo.propuesta_id)
        self.app.servicios.propuestas.aceptar_propuesta(flujo.propuesta_id, p.version_vigente_id, T0)
        self.app.despachador.despachar()
        contrato_id = self.app.servicios.contratacion.preparar_contrato(flujo.propuesta_id, True).datos['contrato_id']
        r = self.adicionales.registrar_solicitud_servicio_adicional(flujo.evento_id, contrato_id, 'Fotografía', T0)
        self.assertFalse(r.exito)
        self.assertEqual(r.mensaje, MENSAJE)

    def test_un_contrato_cerrado_sin_confirmar_no_permite_registrarlo(self):
        f = self.firmado()
        contacto = T0 + timedelta(days=6)
        self.app.servicios.contratacion.dar_seguimiento_anticipo_pendiente(f.contrato_id, contacto, 'Contacto', False)
        cierre = contacto + timedelta(hours=31)
        self.assertTrue(self.app.servicios.contratacion.dar_seguimiento_anticipo_pendiente(f.contrato_id, cierre, 'Sin pago', True).exito)
        self.app.despachador.despachar()
        self.assertEqual(self.app.repos.contratos.obtener_por_id(f.contrato_id).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)
        r = self.solicitar(f, cierre)
        self.assertFalse(r.exito)
        self.assertEqual(r.mensaje, MENSAJE)
        self.assertEqual(self.app.repos.adicionales.listar_todas(), [])

    # ---- el resto del flujo se conserva con la contratación confirmada
    def test_un_contrato_confirmado_permite_registrar_y_continuar_con_las_demas_validaciones(self):
        f = self.confirmado()
        self.assertEqual(self.app.repos.contratos.obtener_por_id(f.contrato_id).estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        r = self.solicitar(f, DIA_VALIDO)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual((r.datos['estado'], r.datos['motivo']), (ESA.REGISTRADA.value, ''))
        self.assertEqual(len(self.app.repos.adicionales.listar_todas()), 1)

    def test_con_la_contratacion_confirmada_el_plazo_menor_a_cinco_dias_sigue_rechazando(self):   # CA-077, CA-083
        f = self.confirmado()
        r = self.solicitar(f, DIA_SIN_PLAZO)
        self.assertTrue(r.exito)                                    # la solicitud se registra y se resuelve como no procedente
        self.assertEqual((r.datos['estado'], r.datos['motivo']), (ESA.NO_PROCEDENTE.value, MOTIVO_PLAZO))

    def test_con_la_contratacion_confirmada_y_exactamente_cinco_dias_se_registra(self):      # límite: cinco días cumplen
        f = self.confirmado()
        r = self.solicitar(f, FECHA_EVENTO - timedelta(days=5))
        self.assertEqual(r.datos['estado'], ESA.REGISTRADA.value)

    def test_con_el_evento_cancelado_el_motivo_sigue_siendo_el_del_evento_no_la_contratacion(self):   # el contrato sigue confirmado
        f = self.confirmado()
        self.assertTrue(self.app.servicios.cierre.gestionar_cancelacion_solicitada(f.evento_id, 'El Cliente desiste', DIA_VALIDO).exito)
        self.app.despachador.despachar()
        r = self.solicitar(f, DIA_VALIDO)
        self.assertTrue(r.exito)
        self.assertEqual(r.datos['estado'], ESA.NO_PROCEDENTE.value)
        self.assertIn('cancelado', r.datos['motivo'])
        self.assertNotEqual(r.datos['motivo'], MENSAJE)

    def test_un_contrato_inexistente_conserva_su_propio_rechazo(self):
        f = self.confirmado()
        r = self.adicionales.registrar_solicitud_servicio_adicional(f.evento_id, 'CT-NO-EXISTE', 'Fotografía', DIA_VALIDO)
        self.assertFalse(r.exito)
        self.assertNotEqual(r.mensaje, MENSAJE)


class ServicioAdicionalPorHttp:
    """HTTP 422 con la convención de rechazo de negocio, y 201 con la contratación confirmada."""

    def cliente(self, ahora):
        app = crear_app(lambda: self.app)
        app.dependency_overrides[obtener_reloj] = lambda: (lambda: ahora)
        return TestClient(app)

    def cuerpo(self, f):
        return {'evento_id': f.evento_id, 'contrato_id': f.contrato_id, 'servicio': 'Fotografía'}

    def test_http_con_contrato_firmado_responde_422_sin_crear_la_solicitud(self):
        f = Flujo(self.app).contratar(confirmar=False)
        r = self.cliente(DIA_VALIDO).post('/solicitudes-servicio-adicional', json=self.cuerpo(f))
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()['tipo'], 'rechazo_de_negocio')
        self.assertEqual(r.json()['detalle'], MENSAJE)
        self.assertEqual(self.app.repos.adicionales.listar_todas(), [])

    def test_http_con_contratacion_confirmada_y_menos_de_cinco_dias_responde_201_no_procedente(self):
        f = Flujo(self.app).contratar()
        r = self.cliente(DIA_SIN_PLAZO).post('/solicitudes-servicio-adicional', json=self.cuerpo(f))
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual((r.json()['datos']['estado'], r.json()['datos']['motivo']), (ESA.NO_PROCEDENTE.value, MOTIVO_PLAZO))

    def test_http_con_contratacion_confirmada_y_plazo_cumplido_responde_201_registrada(self):
        f = Flujo(self.app).contratar()
        r = self.cliente(DIA_VALIDO).post('/solicitudes-servicio-adicional', json=self.cuerpo(f))
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()['datos']['estado'], ESA.REGISTRADA.value)


class EnMemoria(ServicioAdicionalExigeContratacionConfirmada, ServicioAdicionalPorHttp, unittest.TestCase):
    def setUp(self):
        self.preparar()

    def crear_contenedor(self):
        return construir()

    def registros_outbox(self):
        return [(type(r.evento).__name__, r.estado) for r in self.app.uow.outbox]


class EnPostgreSQL(ServicioAdicionalExigeContratacionConfirmada, ServicioAdicionalPorHttp, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        self.preparar()

    def crear_contenedor(self):
        return construir_persistente(motor=self.motor)

    def registros_outbox(self):
        return sorted((r.tipo if hasattr(r, 'tipo') else str(r), r.estado) for r in self.app.outbox.registros())


if __name__ == '__main__':
    unittest.main()
