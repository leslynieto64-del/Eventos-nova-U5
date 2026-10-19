"""Pruebas de las correcciones técnicas de la revisión de las etapas 3 a 7.
Se escribieron antes de corregir el código para comprobar los defectos señalados."""
import os, sys, unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO          # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada  # noqa: E402
from infrastructure.unidad_trabajo import UnitOfWorkMemoria, PublicadorEnProceso, DespachadorOutbox, RegistroOutbox  # noqa: E402
from domain.eventos_dominio import EventoDominio                        # noqa: E402
from domain.valores import (Importe, DisponibilidadProveedor, CondicionesServicio, Decision, DatosEvento,  # noqa: E402
                            ResultadoViabilidad, EstadoEvento, EstadoObligacionPago as EO,
                            EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA,
                            EstadoSustitucionProveedor as ESP, ConceptoPago, TipoSolicitud)


def _saldo_vencido(e):
    e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
    return e.comunicacion + timedelta(hours=25)


class B1RegularizacionYAvisos(unittest.TestCase):
    def test_regularizado_comunica_el_resultado_y_no_avisa_cancelacion(self):  # BN-005, CA-027
        e = Escenario(); revision = _saldo_vencido(e)
        saldo, mor = e.obligacion('SaldoContratoOriginal'), e.obligacion('CargosMoratorios')
        a_tiempo = e.comunicacion + timedelta(hours=3)
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, saldo.obligacion_id, saldo.importe, a_tiempo, 'C-S')
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, mor.obligacion_id, mor.importe, a_tiempo, 'C-M')
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision); e.d.despachar()
        self.assertEqual(len(e.avisos('Saldo regularizado')), 1)
        self.assertEqual(e.avisos('Plazo de regularización vencido'), [])
        self.assertEqual(e.avisos('Evento cancelado'), [])

    def test_resultado_no_se_registra_dos_veces(self):  # CA-027
        e = Escenario(); revision = _saldo_vencido(e)
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision); e.d.despachar()
        r = e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision + timedelta(hours=1)); e.d.despachar()
        self.assertFalse(r.exito)
        self.assertEqual(len(e.avisos('Plazo de regularización vencido')), 1)

    def test_reintento_no_repite_reacciones_ya_ejecutadas(self):
        uow, pub = UnitOfWorkMemoria(), PublicadorEnProceso()
        llamadas = {'aviso': 0, 'falla': 0}
        class Hecho(EventoDominio): pass
        def aviso(e): llamadas['aviso'] += 1
        def falla_una_vez(e):
            llamadas['falla'] += 1
            if llamadas['falla'] == 1:
                raise RuntimeError('falla técnica')
        pub.suscribir(Hecho, aviso); pub.suscribir(Hecho, falla_una_vez)
        uow.outbox.append(RegistroOutbox(Hecho('X', T0)))
        DespachadorOutbox(uow, pub).despachar()
        self.assertEqual(llamadas, {'aviso': 1, 'falla': 2})
        self.assertEqual(uow.outbox[0].estado, 'Procesado')


class B2CambioConfirmadoSeAplica(unittest.TestCase):
    def test_la_configuracion_aprobada_se_aplica_al_evento(self):  # BN-003, BN-006, SE-002, CA-038, CA-041, CA-064
        e = Escenario(); e.confirmar_contratacion()
        ev = e.evento(); sc_id = next(iter(ev.servicios))
        nuevos = DatosEvento('Boda', FECHA_EVENTO, 'Salón', 150)
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Aumento de invitados', Importe(D(100)), T0 + timedelta(days=5),
                                                    datos_propuestos=nuevos,
                                                    condiciones_propuestas={sc_id: CondicionesServicio('Banquete para 150 personas')})
        sid = r.datos['solicitud_id']
        dia = T0 + timedelta(days=5)
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), None, dia)
        # Ruta B: el aumento de invitados modifica las condiciones acordadas (BN-003, CA-038, CA-064)
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sid).estado, ESC.PENDIENTE_APROBACION_CLIENTE)
        e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, dia))
        e.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', True, dia))
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo: 150 invitados', dia); e.d.despachar()
        self.assertTrue(e.s.cambios.confirmar_cambio(sid, T0 + timedelta(days=6)).exito)
        e.d.despachar()
        ev = e.evento()
        self.assertEqual(ev.datos.invitados_aproximados, 150)
        self.assertEqual(ev.servicios[sc_id].condiciones.descripcion, 'Banquete para 150 personas')

    def test_cambio_no_confirmado_conserva_la_configuracion(self):  # BN-006, CA-060
        e = Escenario(); e.confirmar_contratacion()
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Aumento', Importe(D(100)), T0 + timedelta(days=5),
                                                    datos_propuestos=DatosEvento('Boda', FECHA_EVENTO, 'Salón', 300))
        e.s.cambios.evaluar_viabilidad_cambio(r.datos['solicitud_id'], ResultadoViabilidad(False, 'Capacidad insuficiente'), None, T0 + timedelta(days=5))
        e.d.despachar()
        self.assertEqual(e.evento().datos.invitados_aproximados, 100)


class B3ServicioAdicionalConservaCondiciones(unittest.TestCase):
    def test_servicio_contratado_con_las_condiciones_aprobadas(self):  # BN-004, SE-004, CA-075, CA-082
        cond = CondicionesServicio('DJ 4 horas, 21:00 a 01:00, equipo incluido')
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), cond)]))
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, dia))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo DJ', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), dia).datos['obligacion_id']
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(500)), dia + timedelta(hours=2), 'C-DJ'); e.d.despachar()
        self.assertTrue(s.confirmar_servicio_adicional(sa, dia + timedelta(hours=3)).exito); e.d.despachar()
        nuevo = [x for x in e.evento().servicios.values() if x.servicio == 'DJ'][0]
        self.assertEqual(nuevo.condiciones, cond)
        self.assertEqual(nuevo.proveedor_id, 'PV-9')


class B4SustitucionTardia(unittest.TestCase):
    def _sustitucion_aprobada(self, fecha_aprobacion):
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-7', True, Importe(D(800)), CondicionesServicio('Banquete con otro proveedor'))]))
        e.confirmar_contratacion()
        sc_id = next(iter(e.evento().servicios))
        sid = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, sc_id, e.contrato_id, fecha_aprobacion).datos['sustitucion_id']
        e.s.sustitucion.buscar_alternativa_sustitucion(sid, CondicionesServicio('Banquete con otro proveedor'), Importe(D(800)), fecha_aprobacion)
        return e, sid

    def test_importe_adicional_exige_aprobaciones(self):  # SE-001, CA-050
        e, sid = self._sustitucion_aprobada(T0 + timedelta(days=5))
        r = e.s.pagos.registrar_importe_adicional_sustitucion(sid, Importe(D(800)))
        self.assertFalse(r.exito)

    def test_aprobada_despues_del_limite_no_hereda_fecha_vencida(self):  # SE-001, BN-005, CA-052
        tarde = FECHA_EVENTO - timedelta(days=1)
        e, sid = self._sustitucion_aprobada(tarde)
        e.s.sustitucion.registrar_decision_cliente_sustitucion(sid, Decision('Cliente', True, tarde))
        e.s.sustitucion.registrar_autorizacion_administracion_sustitucion(sid, Decision('Administración', True, tarde))
        self.assertTrue(e.s.pagos.registrar_importe_adicional_sustitucion(sid, Importe(D(800))).exito)
        ob = e.obligacion('SustitucionProveedor')
        self.assertIsNone(ob.plazo)                               # sin plazo fijo adicional (CA-052)
        e.s.pagos.registrar_vencimiento_saldo_original(e.ec_id, tarde + timedelta(hours=1))
        self.assertEqual(e.obligacion('SustitucionProveedor').estado, EO.PENDIENTE)   # no vence automáticamente
        e.s.sustitucion.registrar_anexo_sustitucion_proveedor(sid, 'Anexo', tarde); e.d.despachar()
        r = e.s.sustitucion.confirmar_sustitucion_proveedor(sid, tarde + timedelta(hours=2))
        self.assertFalse(r.exito)                                 # pago previo a confirmar
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D(800)), tarde + timedelta(hours=3), 'C-SP')
        self.assertTrue(e.s.sustitucion.confirmar_sustitucion_proveedor(sid, tarde + timedelta(hours=4)).exito)

    def test_aprobada_antes_del_limite_usa_el_plazo_del_saldo_general(self):  # SE-001, CA-052
        temprano = T0 + timedelta(days=5)
        e, sid = self._sustitucion_aprobada(temprano)
        e.s.sustitucion.registrar_decision_cliente_sustitucion(sid, Decision('Cliente', True, temprano))
        e.s.sustitucion.registrar_autorizacion_administracion_sustitucion(sid, Decision('Administración', True, temprano))
        e.s.pagos.registrar_importe_adicional_sustitucion(sid, Importe(D(800)))
        self.assertEqual(e.obligacion('SustitucionProveedor').plazo.vence, e.obligacion('SaldoContratoOriginal').plazo.vence)
        e.s.sustitucion.registrar_anexo_sustitucion_proveedor(sid, 'Anexo', temprano); e.d.despachar()
        self.assertTrue(e.s.sustitucion.confirmar_sustitucion_proveedor(sid, temprano + timedelta(hours=1)).exito)


class B5RevisionAdministrativa(unittest.TestCase):
    def test_revision_consulta_pagos_y_saldo_pendiente(self):  # BN-008, SE-009, CA-089, CA-090, CA-091
        e = Escenario(); e.confirmar_contratacion()
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', T0 + timedelta(days=3)); e.d.despachar()
        r = e.s.cierre.registrar_revision_administrativa_cancelacion(e.evento_id, 'Revisión de contrato y pagos', T0 + timedelta(days=4))
        self.assertTrue(r.exito, r.mensaje)
        rev = e.evento().revision_administrativa
        self.assertEqual(rev.pagos_realizados, Importe(D('3000.00')))
        self.assertEqual(rev.saldo_pendiente, Importe(D('7000.00')))
        self.assertTrue(rev.constancia_no_reembolso)


class B6SolicitudEnTramiteConSaldoVencido(unittest.TestCase):
    def test_solicitud_en_tramite_no_se_detiene_automaticamente(self):  # SE-006, CA-072 (P-06)
        """P-06 (resuelto): BN-005, SE-007 y GL-049 regulan solo las nuevas solicitudes; la que ya está en trámite continúa.
        Ninguna solicitud puede confirmarse si el Evento está cancelado (test_decisiones_stakeholder)."""
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        e.vencer_saldo_y_comunicar_moratorios()
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.PENDIENTE_APROBACION_CLIENTE)


class RechazosComoResultado(unittest.TestCase):
    def test_autorizacion_antes_de_la_aprobacion_devuelve_rechazo(self):  # BN-004, CA-081
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        e.confirmar_contratacion()
        s, dia = e.s.adicionales, FECHA_EVENTO - timedelta(days=10)
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        r = s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, dia))
        self.assertFalse(r.exito)


if __name__ == '__main__':
    unittest.main()
