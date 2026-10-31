"""Etapa 6 (fase final): las integraciones externas son SIMULACIONES documentadas; no se presentan como reales.

Fuentes: BRD («Realizar los pagos por parte del Cliente» está fuera del alcance) y glosario («Los pagos se efectúan fuera del
sistema y Administración los registra manualmente»). No hay especificación, acceso ni credenciales de pasarelas de pago, correo,
mensajería ni calendarios de proveedores; por eso no se implementó ninguna integración real.
Ver docs/architecture/integraciones-externas.md."""
import json, os, sys, tempfile, unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient                                           # noqa: E402
from test_reglas_corregidas import Escenario, T0                                    # noqa: E402
from api.main import crear_app, fabrica_por_defecto                                 # noqa: E402
from domain.valores import Importe                                                  # noqa: E402
from infrastructure import adaptadores as AD                                        # noqa: E402
from infrastructure.composicion import construir                                    # noqa: E402

DEMO = os.path.join(os.path.dirname(__file__), '..', 'src', 'infrastructure', 'datos_demo', 'disponibilidad_demo.json')


class Adaptadores(unittest.TestCase):
    def test_la_composicion_usa_solo_adaptadores_simulados(self):
        app = construir()
        self.assertIsInstance(app.notificador, AD.NotificadorEnMemoria)
        self.assertIsInstance(app.servicios.pagos.ejecutor, AD.EjecutorDevolucionesSimulado)
        self.assertIsInstance(app.servicios.pagos.verificador, AD.VerificadorPagosSimulado)
        self.assertTrue(AD.__doc__.lower().startswith('adaptadores simulados'))

    def test_la_verificacion_de_pagos_simulada_solo_exige_un_comprobante(self):
        v = AD.VerificadorPagosSimulado()
        self.assertTrue(v.verificar('TRANSF-1', Importe(D('10'))))
        self.assertFalse(v.verificar('', Importe(D('10'))))          # sin comprobante no se verifica (no consulta ningún banco)

    def test_el_ejecutor_de_devoluciones_es_idempotente_por_referencia(self):
        e = AD.EjecutorDevolucionesSimulado()
        self.assertEqual(e.ejecutar('DV-1', Importe(D('5')), 'REF'), e.ejecutar('DV-1', Importe(D('5')), 'REF'))
        self.assertEqual(len(e.ejecutadas), 1)

    def test_el_notificador_solo_registra_en_memoria(self):
        n = AD.NotificadorEnMemoria()
        n.notificar(['Cliente'], 'Asunto', 'Detalle')
        self.assertEqual(n.enviados, [(('Cliente',), 'Asunto', 'Detalle')])

    def test_sin_configuracion_no_hay_datos_de_disponibilidad(self):
        self.assertEqual(AD.ConsultaDisponibilidadSimulada().consultar('Banquete', T0, []), [])
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO': '', 'EVENTOSNOVA_PERSISTENCIA': ''}):
            self.assertIsNone(AD.disponibilidad_desde_entorno())
            self.assertIs(fabrica_por_defecto(), construir)


class DisponibilidadConfigurable(unittest.TestCase):
    def test_el_archivo_de_demostracion_se_carga_y_esta_rotulado_como_demostracion(self):
        with open(DEMO, encoding='utf-8') as f:
            self.assertIn('DEMOSTRACION', json.load(f)['_aviso'])
        c = AD.ConsultaDisponibilidadDesdeArchivo(DEMO)
        banquete = c.consultar('Banquete', T0, [])
        self.assertEqual([(d.proveedor_id, d.disponible) for d in banquete],
                         [('PV-DEMO-BANQUETE-1', True), ('PV-DEMO-BANQUETE-2', False)])
        self.assertEqual(banquete[0].costo.cantidad, D('5000.00'))
        self.assertEqual(c.consultar('Servicio-desconocido', T0, []), [])

    def test_la_variable_de_entorno_activa_la_simulacion_configurable(self):
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO': DEMO, 'EVENTOSNOVA_PERSISTENCIA': ''}):
            self.assertIsInstance(AD.disponibilidad_desde_entorno(), AD.ConsultaDisponibilidadDesdeArchivo)
            self.assertIsNot(fabrica_por_defecto(), construir)
            app = fabrica_por_defecto()()
        self.assertIsNotNone(app.servicios.proveedores)

    def test_con_datos_de_disponibilidad_se_puede_asignar_un_proveedor(self):
        e = Escenario(disponibilidad=AD.ConsultaDisponibilidadDesdeArchivo(DEMO))
        e.confirmar_contratacion()
        servicio_id = next(iter(e.evento().servicios))
        r = e.s.proveedores.consultar_disponibilidad_servicio(e.evento_id, servicio_id)
        self.assertEqual((r.datos['disponibles'], r.datos['no_disponibles']), (['PV-DEMO-BANQUETE-1'], ['PV-DEMO-BANQUETE-2']))
        self.assertTrue(e.s.proveedores.asignar_proveedor(e.evento_id, servicio_id, 'PV-DEMO-BANQUETE-1').exito)
        self.assertFalse(e.s.proveedores.asignar_proveedor(e.evento_id, servicio_id, 'PV-DEMO-BANQUETE-2').exito)

    def test_sin_datos_de_disponibilidad_no_se_puede_asignar_ningun_proveedor(self):
        e = Escenario()
        e.confirmar_contratacion()
        servicio_id = next(iter(e.evento().servicios))
        self.assertFalse(e.s.proveedores.asignar_proveedor(e.evento_id, servicio_id, 'PV-1').exito)   # límite conocido y documentado

    def test_un_archivo_inexistente_falla_al_arrancar_en_vez_de_ignorarse(self):
        with self.assertRaises(FileNotFoundError):
            AD.ConsultaDisponibilidadDesdeArchivo(os.path.join(tempfile.gettempdir(), 'no-existe-disponibilidad.json'))


class DevolucionConComprobanteDeAdministracion(unittest.TestCase):
    """CA-098: Administración efectúa la devolución fuera del sistema y registra su comprobante."""
    def preparar(self):
        e = Escenario()
        e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
        contacto = T0 + timedelta(days=6)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
        ob = e.obligacion('Anticipo')
        cierre = contacto + timedelta(hours=31)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, cierre, 'Sin pago', True)
        e.d.despachar()
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('3000')), cierre + timedelta(days=1), 'C',
                                             registrado_en=cierre + timedelta(days=1))
        e.d.despachar()
        return e, e.ec().devoluciones[0].devolucion_id

    def test_se_registra_el_comprobante_que_entrega_administracion(self):
        e, did = self.preparar()
        cliente = TestClient(crear_app(lambda: e.app))
        r = cliente.post(f'/estados-cuenta/{e.ec_id}/devoluciones/{did}/ejecucion', json={'comprobante': 'TRANSF-REAL-0001'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(e.ec().devoluciones[0].comprobante, 'TRANSF-REAL-0001')
        self.assertEqual(e.app.servicios.pagos.ejecutor.ejecutadas, {})            # no se usó la simulación

    def test_sin_comprobante_se_usa_el_ejecutor_simulado(self):
        e, did = self.preparar()
        r = TestClient(crear_app(lambda: e.app)).post(f'/estados-cuenta/{e.ec_id}/devoluciones/{did}/ejecucion')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(e.ec().devoluciones[0].comprobante.startswith('COMP-'))

    def test_un_comprobante_vacio_se_rechaza(self):
        e, did = self.preparar()
        r = TestClient(crear_app(lambda: e.app)).post(f'/estados-cuenta/{e.ec_id}/devoluciones/{did}/ejecucion', json={'comprobante': ''})
        self.assertEqual(r.status_code, 422)
        self.assertIsNone(e.ec().devoluciones[0].comprobante)


if __name__ == '__main__':
    unittest.main()
