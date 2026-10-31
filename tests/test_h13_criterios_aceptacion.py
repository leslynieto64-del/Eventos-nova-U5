"""H-13 / H-23: pruebas de comportamiento para criterios de aceptación que antes solo tenían cobertura superficial.

Cada prueba verifica estados, avisos, eventos y/o importes reales (no solo que "no falle"). El mapa TRAZABILIDAD relaciona
cada criterio con su historia, reglas, componente y pruebas; `MapaDeTrazabilidad` comprueba que esas pruebas existen.
Ejecutar desde la raíz:  python -m unittest tests.test_h13_criterios_aceptacion -v"""
import importlib
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import CONTENIDO, Escenario, FECHA_EVENTO, T0                           # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                                # noqa: E402
from domain.valores import (CondicionesServicio, ConceptoPago as CP, ContenidoPropuesta, DatosEvento, Decision,   # noqa: E402
                            CausaCierreSolicitud, DisponibilidadProveedor, EstadoContrato, EstadoEvento, EstadoPropuesta,
                            EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA,
                            EstadoSustitucionProveedor as ESP, Importe, ResultadoViabilidad)

DIA = T0 + timedelta(days=2)                                   # un día de octubre: faltan más de 7 días para el evento
VIABLE = ResultadoViabilidad(True)


def avisos(e, asunto):
    return [n for n in e.app.notificador.enviados if n[1] == asunto]


def alternativa(proveedor='PV-9', costo='500'):
    return ConsultaDisponibilidadSimulada([DisponibilidadProveedor(proveedor, True, Importe(D(costo)),
                                                                   CondicionesServicio('Condiciones alternativas'))])


def alternativa_con_original():
    return ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-1', True, Importe(D('400')), CondicionesServicio('Original')),
                                           DisponibilidadProveedor('PV-9', True, Importe(D('500')), CondicionesServicio('Alt'))])


# ======================================================================= Propuesta y contrato (US-006 a US-008)
class PropuestaYContrato(unittest.TestCase):
    def propuesta(self):
        e = Escenario.__new__(Escenario)                       # Escenario ya acepta y firma: aquí se arma paso a paso
        from infrastructure.composicion import construir
        e.app = construir(); e.s, e.d = e.app.servicios, e.app.despachador
        e.evento_id = e.s.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        e.pr = e.s.propuestas.crear_propuesta(e.evento_id, CONTENIDO, T0).datos['propuesta_id']
        return e

    def p(self, e):
        return e.app.repos.propuestas.obtener_por_id(e.pr)

    def test_pedir_cambios_genera_version_vigente_nueva_y_aceptar_cierra_las_versiones(self):  # CA-012, BN-002
        e = self.propuesta()
        nuevo = ContenidoPropuesta(('Banquete', 'DJ'), ('PV-1',), Importe(D(12000)), 'Con DJ')
        r = e.s.propuestas.generar_nueva_version(e.pr, nuevo, T0 + timedelta(hours=1))
        self.assertEqual((r.exito, r.datos['numero']), (True, 2))
        p = self.p(e)
        self.assertEqual((len(p.versiones), p.version_vigente_id), (2, f'{e.pr}-v2'))
        self.assertNotEqual(p.estado, EstadoPropuesta.ACEPTADA)                                # pedir cambios no acepta
        self.assertTrue(e.s.propuestas.aceptar_propuesta(e.pr, p.version_vigente_id, T0 + timedelta(hours=2)).exito)
        despues = e.s.propuestas.generar_nueva_version(e.pr, nuevo, T0 + timedelta(hours=3))
        self.assertFalse(despues.exito)                                # aceptada: ya no hay nuevas versiones
        self.assertEqual((len(self.p(e).versiones), self.p(e).estado), (2, EstadoPropuesta.ACEPTADA))

    def test_aceptar_avisa_al_coordinador_y_habilita_el_contrato(self):                       # CA-014, CA-015
        e = self.propuesta()
        self.assertFalse(e.s.contratacion.preparar_contrato(e.pr, True).exito)                # antes de aceptar no hay contrato
        self.assertEqual(avisos(e, 'Propuesta aceptada'), [])
        self.assertTrue(e.s.propuestas.aceptar_propuesta(e.pr, self.p(e).version_vigente_id, T0).exito); e.d.despachar()
        (aviso,) = avisos(e, 'Propuesta aceptada')
        self.assertEqual(aviso[0], ('Coordinador',))
        self.assertTrue(e.s.contratacion.preparar_contrato(e.pr, True).exito)

    def test_el_contrato_toma_el_contenido_de_la_version_aceptada(self):                      # CA-015, CA-017, BN-002
        e = self.propuesta()
        nuevo = ContenidoPropuesta(('Banquete', 'DJ'), ('PV-1',), Importe(D(12000)), 'Con DJ')
        e.s.propuestas.generar_nueva_version(e.pr, nuevo, T0 + timedelta(hours=1))
        vigente = self.p(e).version_vigente_id
        e.s.propuestas.aceptar_propuesta(e.pr, vigente, T0 + timedelta(hours=2)); e.d.despachar()
        c = e.app.repos.contratos.obtener_por_id(e.s.contratacion.preparar_contrato(e.pr, True).datos['contrato_id'])
        self.assertEqual((c.propuesta_id, c.version_aceptada_id, c.estado), (e.pr, vigente, EstadoContrato.EN_PREPARACION))
        self.assertEqual((c.condiciones.servicios, c.condiciones.costo_total, c.condiciones.condiciones),
                         (('Banquete', 'DJ'), Importe(D(12000)), 'Con DJ'))

    def test_la_firma_firma_el_contrato_y_genera_la_obligacion_de_anticipo(self):             # CA-017, BN-001
        e = self.propuesta()
        e.s.propuestas.aceptar_propuesta(e.pr, self.p(e).version_vigente_id, T0); e.d.despachar()
        cid = e.s.contratacion.preparar_contrato(e.pr, True).datos['contrato_id']
        self.assertIsNone(e.app.repos.estados_cuenta.obtener_por_contrato_id(cid))
        self.assertTrue(e.s.contratacion.registrar_firma_contrato(cid, T0).exito); e.d.despachar()
        c = e.app.repos.contratos.obtener_por_id(cid)
        self.assertEqual((c.estado, c.fecha_firma), (EstadoContrato.FIRMADO, T0))
        ec = e.app.repos.estados_cuenta.obtener_por_contrato_id(cid)
        self.assertEqual([(o.concepto, o.importe) for o in ec.obligaciones.values()], [(CP.ANTICIPO, Importe(D('3000.00')))])


# ======================================================================= Saldo vencido y cobro (US-011)
class SaldoVencidoYCobro(unittest.TestCase):
    def setUp(self):
        self.e = Escenario(); self.e.confirmar_contratacion()

    def test_saldo_vencido_avisa_a_coordinador_y_administracion(self):                        # CA-024
        e = self.e
        limite = e.obligacion('SaldoContratoOriginal').plazo.vence
        r = e.s.pagos.registrar_vencimiento_saldo_original(e.ec_id, limite - timedelta(hours=1))
        self.assertEqual(r.mensaje, 'Sin vencimiento.')
        e.d.despachar()
        self.assertEqual(avisos(e, 'Saldo vencido'), [])                                     # todavía en plazo
        e.s.pagos.registrar_vencimiento_saldo_original(e.ec_id, limite + timedelta(hours=1)); e.d.despachar()
        (aviso,) = avisos(e, 'Saldo vencido')
        self.assertEqual((aviso[0], aviso[2]), (('Coordinador', 'Administración'), 'Activar el protocolo de cobro.'))

    def test_protocolo_de_cobro_recuerda_al_cliente_y_crea_moratorios(self):                  # CA-025
        e = self.e
        e.vencer_saldo_y_comunicar_moratorios()
        (aviso,) = avisos(e, 'Recordatorio de pago')
        self.assertEqual(aviso[0], ('Cliente',))
        ec = e.ec()
        mor = e.obligacion('CargosMoratorios')
        self.assertEqual((mor.importe, mor.plazo.inicio, mor.plazo.vence - mor.plazo.inicio),
                         (Importe(D(200)), e.comunicacion, timedelta(hours=24)))
        self.assertEqual(ec.seguimientos_cobro, ['Recordatorio amistoso'])

    def test_conceptos_de_pago_separados(self):                                               # CA-026, BN-005
        e = self.e
        e.vencer_saldo_y_comunicar_moratorios()
        conceptos = [o.concepto for o in e.ec().obligaciones.values()]
        self.assertEqual(sorted(c.value for c in conceptos), sorted(['Anticipo', 'SaldoContratoOriginal', 'CargosMoratorios']))
        saldo, mor = e.obligacion('SaldoContratoOriginal'), e.obligacion('CargosMoratorios')
        self.assertNotEqual(saldo.obligacion_id, mor.obligacion_id)
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, mor.obligacion_id, mor.importe, e.comunicacion + timedelta(hours=1), 'C-M')
        self.assertEqual(e.obligacion('SaldoContratoOriginal').estado, saldo.estado)          # pagar uno no liquida el otro


# ======================================================================= Cambios (US-017, US-020, US-023, US-024)
class SolicitudDeCambio(unittest.TestCase):
    def registrar(self, e, propuestos=None, dia=DIA):
        return e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Más invitados', Importe(D(150)), dia,
                                                      datos_propuestos=propuestos)

    def cambio(self, e, sid):
        return e.app.repos.cambios.obtener_por_id(sid)

    def mas_invitados(self):
        return DatosEvento('Boda', FECHA_EVENTO, 'Salón', 120)

    def test_el_registro_guarda_la_fecha_de_la_solicitud_y_el_evento(self):                  # CA-037, CA-059
        e = Escenario(); e.confirmar_contratacion()
        r = self.registrar(e, self.mas_invitados())
        s = self.cambio(e, r.datos['solicitud_id'])
        self.assertEqual((r.exito, s.estado, s.anticipacion.fecha_solicitud, s.anticipacion.fecha_evento),
                         (True, ESC.REGISTRADA, DIA, FECHA_EVENTO))
        self.assertEqual(s.datos_propuestos.invitados_aproximados, 120)
        self.assertEqual(e.evento().datos.invitados_aproximados, 100)                          # nada cambia hasta confirmarse

    def test_cambio_rechazado_si_el_evento_no_esta_en_organizacion(self):                     # CA-039
        sin_contratar = Escenario()                                                            # Evento En gestión
        iniciado = Escenario(); iniciado.confirmar_contratacion(); iniciado.s.cierre.procesar_inicio_evento(iniciado.evento_id, FECHA_EVENTO)
        finalizado = Escenario(); finalizado.confirmar_contratacion()
        finalizado.s.cierre.procesar_inicio_evento(finalizado.evento_id, FECHA_EVENTO)
        finalizado.s.cierre.finalizar_evento(finalizado.evento_id, FECHA_EVENTO + timedelta(hours=5))
        for nombre, e, estado in (('en gestión', sin_contratar, EstadoEvento.EN_GESTION),
                                  ('iniciado', iniciado, EstadoEvento.EN_EJECUCION),
                                  ('finalizado', finalizado, EstadoEvento.FINALIZADO)):
            with self.subTest(evento=nombre):
                self.assertEqual(e.evento().estado, estado)
                r = self.registrar(e)
                self.assertEqual((r.exito, r.mensaje), (False, "El cambio solo procede después de contratar y antes del inicio (CA-039)."))
                self.assertEqual(e.app.repos.cambios.listar_todas(), [])

    def test_no_viable_se_cierra_como_no_procedente_sin_cargo_ni_cambio_en_el_evento(self):   # CA-065, CA-069, CA-060
        e = Escenario(); e.confirmar_contratacion()
        sid = self.registrar(e, self.mas_invitados()).datos['solicitud_id']
        r = e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(False, 'Sin capacidad del proveedor'), None, DIA)
        self.assertEqual((r.exito, r.datos['estado']), (True, ESC.NO_PROCEDENTE.value))
        s = self.cambio(e, sid)
        self.assertEqual((s.estado, s.motivo_cierre.causa, s.motivo_cierre.descripcion),
                         (ESC.NO_PROCEDENTE, CausaCierreSolicitud.NO_VIABLE, 'Sin capacidad del proveedor'))
        self.assertEqual(e.evento().datos.invitados_aproximados, 100)                          # configuración vigente conservada
        self.assertEqual(e.ec().obligaciones_de(sid), [])                                      # sin cargo ni costo
        self.assertFalse(e.s.pagos.comunicar_solicitud_pago_cambio(sid, DIA).exito)

    def test_la_evaluacion_registra_las_banderas_de_impacto(self):                            # CA-060, CA-038
        e = Escenario(); e.confirmar_contratacion()
        con_cambio = self.registrar(e, self.mas_invitados()).datos['solicitud_id']
        sin_cambio = self.registrar(e, None).datos['solicitud_id']
        for sid in (con_cambio, sin_cambio):
            self.assertTrue(e.s.cambios.evaluar_viabilidad_cambio(sid, VIABLE, None, DIA).exito)
        a, b = self.cambio(e, con_cambio), self.cambio(e, sin_cambio)
        # El cambio de invitados altera las condiciones del evento; sin datos propuestos no hay ningún impacto.
        self.assertEqual((a.impacto.afecta_servicios, a.impacto.afecta_costos, a.impacto.afecta_condiciones), (False, False, True))
        self.assertEqual((b.impacto.afecta_servicios, b.impacto.afecta_costos, b.impacto.afecta_condiciones), (False, False, False))
        self.assertEqual((a.estado, b.estado), (ESC.PENDIENTE_APROBACION_CLIENTE, ESC.PENDIENTE_FORMALIZACION))

    def test_cambio_con_condiciones_nuevas_requiere_aprobacion_y_se_rechaza_con_aviso(self):  # CA-044, CA-059
        e = Escenario(); e.confirmar_contratacion()
        servicio = next(iter(e.evento().servicios))
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Menú', Importe(D(150)), DIA,
                                                      condiciones_propuestas={servicio: CondicionesServicio('Menú ajustado')}
                                                      ).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, VIABLE, Importe(D(300)), DIA)
        self.assertEqual(self.cambio(e, sid).estado, ESC.PENDIENTE_APROBACION_CLIENTE)
        e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, DIA))
        r = e.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', False, DIA, 'Sin presupuesto'))
        self.assertTrue(r.exito)
        self.assertEqual(self.cambio(e, sid).estado, ESC.NO_AUTORIZADA)
        self.assertEqual(avisos(e, 'Cambio no autorizado'), [(('Cliente',), 'Cambio no autorizado', 'Sin presupuesto')])
        self.assertEqual(e.evento().servicios[servicio].condiciones, CondicionesServicio('Condiciones acordadas'))   # conservada
        self.assertEqual(e.ec().obligaciones_de(sid), [])


# ======================================================================= Servicios adicionales (US-025)
class ServicioAdicionalNoAutorizado(unittest.TestCase):
    def test_no_autorizado_avisa_al_cliente_y_no_incorpora_el_servicio(self):                 # CA-081
        e = Escenario(alternativa()); e.confirmar_contratacion()
        s = e.s.adicionales
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', DIA).datos['solicitud_id']
        self.assertTrue(s.evaluar_disponibilidad_servicio_adicional(sa, [], DIA).exito)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, DIA))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', False, DIA, 'Sin cupo'))
        sol = e.app.repos.adicionales.obtener_por_id(sa)
        self.assertEqual(sol.estado, ESA.NO_AUTORIZADA)
        self.assertEqual(avisos(e, 'Servicio adicional no autorizado'), [(('Cliente',), 'Servicio adicional no autorizado', 'Sin cupo')])
        self.assertEqual(len(e.evento().servicios), 1)                                         # solo el servicio contratado
        self.assertEqual(e.ec().obligaciones_de(sa), [])
        self.assertFalse(s.registrar_anexo_servicio_adicional(sa, 'Anexo', DIA).exito)


# ======================================================================= Sustitución de proveedor (US-021)
class SustitucionDeProveedor(unittest.TestCase):
    def iniciar(self, disponibilidad=None):
        e = Escenario(disponibilidad); e.confirmar_contratacion()
        servicio = next(iter(e.evento().servicios))
        if disponibilidad is not None and disponibilidad.respuestas:
            e.s.proveedores.asignar_proveedor(e.evento_id, servicio, 'PV-1')
        sid = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, DIA).datos['sustitucion_id']
        return e, servicio, sid

    def sustitucion(self, e, sid):
        return e.app.repos.sustituciones.obtener_por_id(sid)

    def test_sin_alternativa_se_informa_y_la_sustitucion_sigue_en_busqueda(self):             # CA-048
        e, servicio, sid = self.iniciar(ConsultaDisponibilidadSimulada([]))
        r = e.s.sustitucion.buscar_alternativa_sustitucion(sid, CondicionesServicio('Alt'), None, DIA)
        self.assertEqual((r.exito, r.mensaje), (False, 'No hay alternativa disponible; se continúa buscando.'))
        self.assertEqual(self.sustitucion(e, sid).estado, ESP.EN_BUSQUEDA_ALTERNATIVA)
        self.assertEqual(len(avisos(e, 'Sin alternativa disponible')), 1)

    def test_rechazo_de_administracion_vuelve_a_buscar_y_conserva_el_proveedor(self):         # CA-050
        e, servicio, sid = self.iniciar(alternativa_con_original())
        original = e.evento().servicios[servicio].proveedor_id
        self.assertEqual(original, 'PV-1')
        self.assertTrue(e.s.sustitucion.buscar_alternativa_sustitucion(sid, CondicionesServicio('Alt'), Importe(D(500)), DIA).exito)
        e.s.sustitucion.registrar_decision_cliente_sustitucion(sid, Decision('Cliente', True, DIA))
        e.s.sustitucion.registrar_autorizacion_administracion_sustitucion(sid, Decision('Administración', False, DIA, 'No autorizada'))
        e.d.despachar()
        self.assertEqual(self.sustitucion(e, sid).estado, ESP.EN_BUSQUEDA_ALTERNATIVA)
        self.assertEqual(len(avisos(e, 'Sustitución no autorizada')), 1)
        self.assertEqual(e.evento().servicios[servicio].proveedor_id, original)


# ======================================================================= Cancelación (US-027, US-028)
class CancelacionDelEvento(unittest.TestCase):
    @staticmethod
    def _cambio_confirmado(e):
        """Cambio sin impacto ni cargo (más de 7 días), formalizado y confirmado antes de la cancelación."""
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Ajuste menor', Importe(D(150)), DIA).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, VIABLE, None, DIA)
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo', DIA); e.d.despachar()
        if not e.s.cambios.confirmar_cambio(sid, DIA).exito:
            raise AssertionError('el cambio de preparación debía confirmarse')
        e.d.despachar()
        return sid

    def test_cancelar_avisa_cierra_solicitudes_en_tramite_y_conserva_las_confirmadas(self):   # CA-087, CA-089
        e = Escenario(alternativa()); e.confirmar_contratacion()
        en_tramite = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(150)), DIA).datos['solicitud_id']
        confirmada = self._cambio_confirmado(e)
        r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente cancela', DIA + timedelta(days=1)); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.evento().estado, EstadoEvento.CANCELADO)
        (aviso,) = avisos(e, 'Evento cancelado')
        self.assertEqual(aviso[0], ('Cliente', 'Administración', 'Proveedores'))
        self.assertIn('Aplica la política de no reembolso', aviso[2])
        self.assertEqual(e.app.repos.cambios.obtener_por_id(en_tramite).estado, ESC.CERRADA_EVENTO_CANCELADO)
        self.assertEqual(e.app.repos.cambios.obtener_por_id(confirmada).estado, ESC.CONFIRMADA)   # lo confirmado no se cierra

    def test_la_revision_administrativa_usa_el_contrato_y_los_estados_de_cuenta(self):         # CA-089
        e = Escenario(); e.confirmar_contratacion()
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente cancela', DIA); e.d.despachar()
        r = e.s.cierre.registrar_revision_administrativa_cancelacion(e.evento_id, 'Sin reembolso', DIA + timedelta(days=1))
        self.assertEqual((r.exito, r.datos['pagos_realizados'], r.datos['saldo_pendiente']), (True, '3000.00', '7000.00'))
        rev = e.evento().revision_administrativa
        self.assertEqual((rev.resultado, rev.pagos_realizados, rev.saldo_pendiente, rev.politica_incluida),
                         ('Sin reembolso', Importe(D('3000.00')), Importe(D('7000.00')), True))
        (aviso,) = avisos(e, 'Revisión de cancelación')
        self.assertEqual(aviso[0], ('Coordinador',))


# ======================================================================= Trazabilidad CA -> US -> regla -> componente -> prueba
_H = 'test_h13_criterios_aceptacion'
TRAZABILIDAD = {
    'CA-012': ('US-006', ('BN-002', 'BN-009'), 'Propuesta.generar_nueva_version / aceptar', (f'{_H}.PropuestaYContrato.test_pedir_cambios_genera_version_vigente_nueva_y_aceptar_cierra_las_versiones',)),
    'CA-014': ('US-007', ('BN-002',), 'Reacción a PropuestaAceptada / FormalizarContratacionService.preparar_contrato', (f'{_H}.PropuestaYContrato.test_aceptar_avisa_al_coordinador_y_habilita_el_contrato',)),
    'CA-015': ('US-008', ('BN-002',), 'FormalizarContratacionService.preparar_contrato', (f'{_H}.PropuestaYContrato.test_el_contrato_toma_el_contenido_de_la_version_aceptada',)),
    'CA-017': ('US-008', ('BN-001',), 'Contrato.firmar / EstadoCuenta (anticipo)', (f'{_H}.PropuestaYContrato.test_la_firma_firma_el_contrato_y_genera_la_obligacion_de_anticipo',)),
    'CA-024': ('US-011', ('BN-005', 'SE-007'), 'EstadoCuenta.registrar_vencimiento_saldo / ReaccionesNotificaciones', (f'{_H}.SaldoVencidoYCobro.test_saldo_vencido_avisa_a_coordinador_y_administracion',)),
    'CA-025': ('US-011', ('BN-005',), 'GestionPagosService.activar_protocolo_cobro', (f'{_H}.SaldoVencidoYCobro.test_protocolo_de_cobro_recuerda_al_cliente_y_crea_moratorios',)),
    'CA-026': ('US-011', ('BN-005',), 'EstadoCuenta (obligaciones por concepto)', (f'{_H}.SaldoVencidoYCobro.test_conceptos_de_pago_separados', 'test_h03_consultas_administracion.EstadoDePagosExistente')),
    'CA-037': ('US-017', ('BN-003',), 'GestionCambiosEventoService.registrar_solicitud_cambio', (f'{_H}.SolicitudDeCambio.test_el_registro_guarda_la_fecha_de_la_solicitud_y_el_evento',)),
    'CA-039': ('US-017', ('BN-003',), 'GestionCambiosEventoService.registrar_solicitud_cambio', (f'{_H}.SolicitudDeCambio.test_cambio_rechazado_si_el_evento_no_esta_en_organizacion',)),
    'CA-044': ('US-020', ('BN-003',), 'SolicitudCambio.registrar_autorizacion', (f'{_H}.SolicitudDeCambio.test_cambio_con_condiciones_nuevas_requiere_aprobacion_y_se_rechaza_con_aviso',)),
    'CA-048': ('US-021', ('SE-001',), 'GestionSustitucionProveedorService.buscar_alternativa_sustitucion', (f'{_H}.SustitucionDeProveedor.test_sin_alternativa_se_informa_y_la_sustitucion_sigue_en_busqueda',)),
    'CA-050': ('US-021', ('SE-001',), 'GestionSustitucionProveedorService.registrar_autorizacion_administracion_sustitucion', (f'{_H}.SustitucionDeProveedor.test_rechazo_de_administracion_vuelve_a_buscar_y_conserva_el_proveedor',)),
    'CA-059': ('US-023', ('BN-003',), 'GestionCambiosEventoService.registrar_solicitud_cambio', (f'{_H}.SolicitudDeCambio.test_el_registro_guarda_la_fecha_de_la_solicitud_y_el_evento',)),
    'CA-060': ('US-024', ('BN-003',), 'EvaluarImpactoCambio / SolicitudCambio.registrar_viabilidad', (f'{_H}.SolicitudDeCambio.test_la_evaluacion_registra_las_banderas_de_impacto',)),
    'CA-065': ('US-024', ('BN-003',), 'SolicitudCambio.registrar_viabilidad (no viable)', (f'{_H}.SolicitudDeCambio.test_no_viable_se_cierra_como_no_procedente_sin_cargo_ni_cambio_en_el_evento',)),
    'CA-069': ('US-024', ('BN-003',), 'SolicitudCambio.registrar_viabilidad (no viable)', (f'{_H}.SolicitudDeCambio.test_no_viable_se_cierra_como_no_procedente_sin_cargo_ni_cambio_en_el_evento',)),
    'CA-081': ('US-025', ('BN-004',), 'GestionServiciosAdicionalesService.registrar_autorizacion_administracion_servicio_adicional', (f'{_H}.ServicioAdicionalNoAutorizado.test_no_autorizado_avisa_al_cliente_y_no_incorpora_el_servicio',)),
    'CA-087': ('US-027', ('BN-008',), 'Reacción a EventoCancelado / GestionCierreEventoService', (f'{_H}.CancelacionDelEvento.test_cancelar_avisa_cierra_solicitudes_en_tramite_y_conserva_las_confirmadas',)),
    'CA-089': ('US-028', ('BN-008',), 'GestionCierreEventoService.registrar_revision_administrativa_cancelacion', (f'{_H}.CancelacionDelEvento.test_la_revision_administrativa_usa_el_contrato_y_los_estados_de_cuenta',)),
    # H-09 (plazo de devolución): la matriz relaciona CA-097/CA-098 con BN-005/BN-006 y la historia US-031
    'CA-098': ('US-031', ('BN-005', 'BN-006', 'SE-012', 'GL-060'), 'Devolucion.fecha_limite / ConsultarDevolucionesPendientesHandler', ('test_h09_plazo_devolucion.FechaLimite', 'test_h09_plazo_devolucion.ConsultasDeDevoluciones')),
}


class MapaDeTrazabilidad(unittest.TestCase):
    @staticmethod
    def _resolver(ref):
        """`modulo.Clase[.metodo]` -> objeto; falla si el módulo, la clase o el método no existen."""
        partes = ref.split('.')
        objeto = importlib.import_module(partes[0])
        for nombre in partes[1:]:
            objeto = getattr(objeto, nombre)
        return objeto

    def test_toda_prueba_referenciada_existe(self):
        for ca, (us, reglas, componente, pruebas) in TRAZABILIDAD.items():
            with self.subTest(ca=ca):
                self.assertRegex(us, r'^US-\d{3}$')
                self.assertTrue(reglas and componente and pruebas)
                for ref in pruebas:
                    self.assertTrue(callable(self._resolver(ref)) or isinstance(self._resolver(ref), type), ref)

    def test_el_mapa_cubre_los_criterios_con_cobertura_superficial_que_se_reforzaron(self):
        reforzados = {'CA-012', 'CA-014', 'CA-015', 'CA-017', 'CA-024', 'CA-025', 'CA-026', 'CA-037', 'CA-039', 'CA-044', 'CA-048',
                      'CA-050', 'CA-059', 'CA-060', 'CA-065', 'CA-069', 'CA-081', 'CA-087', 'CA-089'}
        self.assertTrue(reforzados <= set(TRAZABILIDAD))


if __name__ == '__main__':
    unittest.main()
