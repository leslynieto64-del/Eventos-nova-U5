"""D-01 — referencias SIN clave foránea: la aplicación las comprueba antes de guardar.

Sin FK, PostgreSQL no protege por sí solo estas referencias; las protegen los servicios de aplicación mediante los puertos de
repositorio (no hay referencias directas entre agregados). Estas pruebas se ejecutan sobre la composición en memoria y, cuando la
base de pruebas está disponible, sobre la composición persistente (ver `test_persistencia_composicion`).
Un rechazo no debe dejar cambios parciales: se comprueba que el estado guardado no cambia."""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from apoyo_flujo import Flujo, T0, FECHA_EVENTO, CONTENIDO                       # noqa: E402
from apoyo_persistencia import estado_de                                          # noqa: E402
from infrastructure.composicion import construir                                  # noqa: E402
from domain.valores import DatosEvento, ErrorDominio, Importe, TipoSolicitud       # noqa: E402


class ReferenciasSinFK:
    """Mixin. Requiere `crear_contenedor()`."""
    def crear_contenedor(self):                                                   # pragma: no cover
        raise NotImplementedError

    def setUp(self):
        self.app = self.crear_contenedor()
        self.f = Flujo(self.app).contratar()
        self.s, self.repos = self.app.servicios, self.app.repos

    def instantanea(self):
        return {'ec': estado_de(self.repos.estados_cuenta.obtener_por_id(self.f.ec_id)),
                'contrato': estado_de(self.repos.contratos.obtener_por_id(self.f.contrato_id)),
                'evento': estado_de(self.repos.eventos.obtener_por_id(self.f.evento_id))}

    # ---- referencias del tipo «id recibido por un servicio»
    def test_propuesta_de_un_evento_inexistente(self):
        r = self.s.propuestas.crear_propuesta('EV-NO-EXISTE', CONTENIDO, T0)
        self.assertFalse(r.exito)
        self.assertEqual(self.repos.propuestas.listar_por_evento_id('EV-NO-EXISTE'), [])

    def test_contrato_de_una_propuesta_inexistente(self):
        r = self.s.contratacion.preparar_contrato('PR-NO-EXISTE', True)
        self.assertFalse(r.exito)
        self.assertIn('no existe', r.mensaje)

    def test_pago_en_un_estado_de_cuenta_inexistente(self):
        r = self.s.pagos.registrar_y_verificar_pago('EC-NO-EXISTE', 'OB-1', Importe(D('1.00')), T0, 'C-1')
        self.assertFalse(r.exito)

    def test_solicitud_de_cambio_con_evento_inexistente(self):
        antes = self.instantanea()
        r = self.s.cambios.registrar_solicitud_cambio('EV-NO-EXISTE', self.f.contrato_id, 'x', Importe(D('0')), T0 + timedelta(days=2))
        self.assertFalse(r.exito)
        self.assertEqual(self.repos.cambios.listar_todas(), [])
        self.assertEqual(self.instantanea(), antes)

    def test_solicitud_de_cambio_con_contrato_inexistente(self):
        r = self.s.cambios.registrar_solicitud_cambio(self.f.evento_id, 'CT-NO-EXISTE', 'x', Importe(D('0')), T0 + timedelta(days=2))
        self.assertFalse(r.exito)
        self.assertEqual(self.repos.cambios.listar_todas(), [])

    def test_anexo_de_una_solicitud_inexistente(self):
        self.assertFalse(self.s.cambios.registrar_anexo_cambio('SC-NO-EXISTE', 'desc', T0).exito)
        self.assertFalse(self.s.adicionales.registrar_anexo_servicio_adicional('SA-NO-EXISTE', 'desc', T0).exito)
        self.assertFalse(self.s.sustitucion.registrar_anexo_sustitucion_proveedor('SP-NO-EXISTE', 'desc', T0).exito)
        self.assertEqual(self.repos.contratos.obtener_por_id(self.f.contrato_id).anexos, [])

    def test_sustitucion_de_un_servicio_contratado_inexistente(self):
        r = self.s.sustitucion.registrar_proveedor_no_disponible(self.f.evento_id, 'CT-NO-EXISTE-S1', self.f.contrato_id, T0 + timedelta(days=2))
        self.assertFalse(r.exito)
        self.assertIn('no existe', r.mensaje)
        self.assertEqual(self.repos.sustituciones.listar_todas(), [])

    # ---- referencias «polimórficas» creadas por reacciones
    def test_cierre_sin_realizar_exige_que_exista_la_solicitud_de_origen(self):
        antes = self.instantanea()
        with self.assertRaises(ErrorDominio) as ctx:
            self.s.pagos.aplicar_cierre_sin_realizar('SC-FANTASMA', self.f.ec_id, self.f.evento_id, T0)
        self.assertIn('no existe', str(ctx.exception))
        self.assertEqual(self.instantanea(), antes)                              # sin cambios parciales
        self.assertEqual(self.repos.estados_cuenta.obtener_por_id(self.f.ec_id)._cierres_sin_realizar, {})

    def test_cierre_sin_realizar_con_origen_existente_si_se_aplica(self):
        r = self.s.cambios.registrar_solicitud_cambio(self.f.evento_id, self.f.contrato_id, 'cambio', Importe(D('0')), T0 + timedelta(days=2))
        self.assertTrue(r.exito, r.mensaje)
        sid = r.datos['solicitud_id']
        self.s.pagos.aplicar_cierre_sin_realizar(sid, self.f.ec_id, self.f.evento_id, T0 + timedelta(days=3))
        self.assertIn(sid, self.repos.estados_cuenta.obtener_por_id(self.f.ec_id)._cierres_sin_realizar)

    def test_cierre_sin_realizar_con_estado_de_cuenta_o_evento_inexistente(self):
        with self.assertRaises(ErrorDominio):
            self.s.pagos.aplicar_cierre_sin_realizar('SC-1', 'EC-NO-EXISTE', self.f.evento_id, T0)
        with self.assertRaises(ErrorDominio):
            self.s.pagos.aplicar_cierre_sin_realizar('SC-1', self.f.ec_id, 'EV-NO-EXISTE', T0)

    def test_las_reacciones_de_obligaciones_exigen_un_contrato_existente(self):
        with self.assertRaises(ErrorDominio):
            self.s.pagos.registrar_obligacion_anticipo('CT-NO-EXISTE')
        with self.assertRaises(ErrorDominio):
            self.s.pagos.registrar_obligacion_saldo_original('CT-NO-EXISTE')

    def test_un_rechazo_no_deja_eventos_pendientes_en_el_outbox(self):
        self.app.despachador.despachar()
        antes = self.contar_eventos_pendientes()
        with self.assertRaises(ErrorDominio):
            self.s.pagos.aplicar_cierre_sin_realizar('SC-FANTASMA', self.f.ec_id, self.f.evento_id, T0)
        self.assertEqual(self.contar_eventos_pendientes(), antes)

    # ---- límites que NO se resuelven aquí (documentados)
    def test_cliente_id_no_es_verificable(self):
        # No existe un agregado/repositorio de clientes: el identificador se acepta tal cual (límite documentado en D-01).
        eid = self.f.registrar_evento(cliente='CLIENTE-QUE-NO-EXISTE-EN-NINGUN-LADO')
        self.assertEqual(self.repos.eventos.obtener_por_id(eid).cliente_id, 'CLIENTE-QUE-NO-EXISTE-EN-NINGUN-LADO')

    def test_la_solicitud_con_el_evento_de_otro_contrato_se_rechaza_sin_cambios(self):
        """E-2 (decisión de implementación del equipo; ver test_coherencia_solicitud_contrato_evento): un evento B con el
        contrato de A se rechaza antes de crear la solicitud, sin tocar ningún agregado."""
        b = Flujo(self.app).contratar()
        antes = self.instantanea()
        r = self.s.cambios.registrar_solicitud_cambio(b.evento_id, self.f.contrato_id, 'mezcla', Importe(D('0')), T0 + timedelta(days=2))
        self.assertFalse(r.exito)
        self.assertIn('no coincide con el evento del contrato', r.mensaje)
        self.assertEqual(self.repos.cambios.listar_todas(), [])
        self.assertEqual(self.instantanea(), antes)


class ReferenciasEnMemoria(ReferenciasSinFK, unittest.TestCase):
    def crear_contenedor(self):
        return construir()

    def contar_eventos_pendientes(self):
        return len([r for r in self.app.uow.outbox if r.estado == 'Pendiente'])


if __name__ == '__main__':
    unittest.main()
