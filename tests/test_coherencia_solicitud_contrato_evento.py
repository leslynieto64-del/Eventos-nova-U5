"""E-2 — coherencia solicitud–contrato–evento.

Decisión de implementación del equipo (NO una regla de las fuentes originales: ni el cierre de alcance, ni el BRD, ni las User
Stories, ni el glosario la exigen; la auditoría final la registró como brecha C-02 de riesgos y el equipo eligió validarla):
antes de registrar una solicitud de cambio, una solicitud de servicio adicional o una sustitución de proveedor, el evento de la
solicitud debe ser el del contrato relacionado. Si no coincide se rechaza con HTTP 422 (convención de la API para una regla de
negocio) y no se modifica ningún agregado, pago, obligación ni registro del Outbox. No se añaden claves foráneas entre raíces.
Las pruebas se ejecutan por HTTP sobre la composición en memoria y sobre PostgreSQL.
Ejecutar desde la raíz:  python -m unittest tests.test_coherencia_solicitud_contrato_evento -v"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient                                          # noqa: E402
from apoyo_bd import BaseConBD                                                      # noqa: E402
from apoyo_flujo import Flujo                                                       # noqa: E402
from apoyo_persistencia import estado_de                                            # noqa: E402
from api.main import crear_app                                                      # noqa: E402
from infrastructure.composicion import construir                                    # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente   # noqa: E402

MENSAJE = 'no coincide con el evento del contrato'


class CoherenciaSolicitudContratoEvento:
    """Mixin. Requiere `crear_contenedor()` y `registros_outbox()`."""

    def preparar(self):
        self.app = self.crear_contenedor()
        self.a = Flujo(self.app).contratar()                       # evento A con su contrato y su estado de cuenta
        self.b = Flujo(self.app).contratar()                       # evento B con los suyos
        self.cliente = TestClient(crear_app(lambda: self.app))
        self.servicio_a = next(iter(self.a.evento().servicios))
        self.servicio_b = next(iter(self.b.evento().servicios))

    def instantanea(self):
        r = self.app.repos
        return {
            'ec_a': estado_de(r.estados_cuenta.obtener_por_id(self.a.ec_id)), 'ec_b': estado_de(r.estados_cuenta.obtener_por_id(self.b.ec_id)),
            'contrato_a': estado_de(r.contratos.obtener_por_id(self.a.contrato_id)), 'contrato_b': estado_de(r.contratos.obtener_por_id(self.b.contrato_id)),
            'evento_a': estado_de(r.eventos.obtener_por_id(self.a.evento_id)), 'evento_b': estado_de(r.eventos.obtener_por_id(self.b.evento_id)),
            'cambios': len(r.cambios.listar_todas()), 'adicionales': len(r.adicionales.listar_todas()),
            'sustituciones': (len(r.sustituciones.listar_pendientes_por_evento_id(self.a.evento_id)),
                              len(r.sustituciones.listar_pendientes_por_evento_id(self.b.evento_id))),
            'outbox': self.registros_outbox(),
        }

    # ---- las tres rutas: (ruta, carga con evento y contrato)
    def cambio(self, evento, contrato):
        return '/solicitudes-cambio', {'evento_id': evento.evento_id, 'contrato_id': contrato.contrato_id,
                                       'descripcion': 'Cambio de menú', 'tarifa_vigente': '0.00'}

    def servicio_adicional(self, evento, contrato):
        return '/solicitudes-servicio-adicional', {'evento_id': evento.evento_id, 'contrato_id': contrato.contrato_id, 'servicio': 'Fotografía'}

    def sustitucion(self, evento, contrato):
        servicio = self.servicio_a if evento is self.a else self.servicio_b
        return '/sustituciones', {'evento_id': evento.evento_id, 'servicio_contratado_id': servicio, 'contrato_id': contrato.contrato_id}

    def rutas(self):
        return {'cambio': self.cambio, 'servicio adicional': self.servicio_adicional, 'sustitución': self.sustitucion}

    # ---- evento coincidente: la operación se permite
    def test_con_el_evento_del_contrato_la_operacion_se_permite(self):
        for nombre, armar in self.rutas().items():
            with self.subTest(ruta=nombre):
                ruta, carga = armar(self.a, self.a)
                r = self.cliente.post(ruta, json=carga)
                self.assertEqual(r.status_code, 201, r.text)

    # ---- evento distinto: rechazo 422, sin cambios en ninguna parte
    def test_con_un_evento_distinto_al_del_contrato_se_rechaza_con_422_y_sin_cambios(self):
        combinaciones = {'evento B con contrato A': (self.a, self.b), 'evento A con contrato B': (self.b, self.a)}
        for nombre, armar in self.rutas().items():
            for descripcion, (contrato_de, evento_de) in combinaciones.items():
                with self.subTest(ruta=nombre, caso=descripcion):
                    antes = self.instantanea()
                    ruta, carga = armar(evento_de, contrato_de)
                    r = self.cliente.post(ruta, json=carga)
                    self.assertEqual(r.status_code, 422, r.text)
                    self.assertEqual(r.json()['tipo'], 'rechazo_de_negocio')
                    self.assertIn(MENSAJE, r.json()['detalle'])
                    self.assertEqual(self.instantanea(), antes)          # ni agregados, ni pagos, ni obligaciones, ni Outbox

    def test_un_rechazo_no_impide_la_operacion_correcta_posterior(self):
        for nombre, armar in self.rutas().items():
            with self.subTest(ruta=nombre):
                ruta, carga = armar(self.b, self.a)
                self.assertEqual(self.cliente.post(ruta, json=carga).status_code, 422)
                ruta, carga = armar(self.a, self.a)
                self.assertEqual(self.cliente.post(ruta, json=carga).status_code, 201)

    def test_los_identificadores_inexistentes_siguen_rechazandose(self):       # D-01: se conserva el comportamiento anterior
        r = self.cliente.post('/solicitudes-cambio', json={'evento_id': 'EV-NO-EXISTE', 'contrato_id': self.a.contrato_id,
                                                           'descripcion': 'x', 'tarifa_vigente': '0.00'})
        self.assertEqual(r.status_code, 422)
        r = self.cliente.post('/solicitudes-cambio', json={'evento_id': self.a.evento_id, 'contrato_id': 'CT-NO-EXISTE',
                                                           'descripcion': 'x', 'tarifa_vigente': '0.00'})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(MENSAJE, r.json()['detalle'])                         # un contrato inexistente conserva su propio motivo


class CoherenciaEnMemoria(CoherenciaSolicitudContratoEvento, unittest.TestCase):
    def setUp(self):
        self.preparar()

    def crear_contenedor(self):
        return construir()

    def registros_outbox(self):
        return [(type(r.evento).__name__, r.estado) for r in self.app.uow.outbox]


class CoherenciaEnPostgreSQL(CoherenciaSolicitudContratoEvento, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        self.preparar()

    def crear_contenedor(self):
        return construir_persistente(motor=self.motor)

    def registros_outbox(self):
        return sorted((r.tipo if hasattr(r, 'tipo') else str(r), r.estado) for r in self.app.outbox.registros())


if __name__ == '__main__':
    unittest.main()
