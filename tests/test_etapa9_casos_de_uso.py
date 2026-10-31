"""Etapa 9 — validación de la propuesta: recorrido de los casos de uso CU-01 a CU-05 con sus flujos
principales, alternativos y de error documentados (BN, SE, CA). Cada prueba indica la regla que comprueba."""
import os, sys, unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO, CONTENIDO       # noqa: E402
from infrastructure.composicion import construir                               # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada          # noqa: E402
from domain.valores import (ContenidoPropuesta, DatosEvento, Importe, Decision, DisponibilidadProveedor,  # noqa: E402
                            CondicionesServicio, ResultadoViabilidad, ConceptoPago, TipoSolicitud,
                            EstadoEvento, EstadoPropuesta, EstadoContrato, EstadoPago, EstadoDevolucion,
                            EstadoObligacionPago as EO, EstadoSolicitudCambio as ESC,
                            EstadoSolicitudServicioAdicional as ESA, EstadoSustitucionProveedor as ESP,
                            EstadoSolicitudCancelacion, limite_exclusivo_dias_habiles, limite_exclusivo_dias_habiles_antes)


# ---------------------------------------------------------------- CU-01 Gestionar la propuesta
class CU01Propuesta(unittest.TestCase):
    def setUp(self):
        self.app = construir()
        s = self.app.servicios.propuestas
        self.evento_id = s.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        self.pid = s.crear_propuesta(self.evento_id, CONTENIDO, T0).datos['propuesta_id']
        self.s = s

    def propuesta(self):
        return self.app.repos.propuestas.obtener_por_id(self.pid)

    def test_nueva_version_deja_una_sola_vigente(self):                       # BN-002, CA-007 a CA-010
        anterior = self.propuesta().version_vigente_id
        nuevo = ContenidoPropuesta(('Banquete', 'Música'), ('PV-1', 'PV-2'), Importe(D(12000)), 'Con música')
        self.assertTrue(self.s.generar_nueva_version(self.pid, nuevo, T0 + timedelta(days=1)).exito)
        p = self.propuesta()
        self.assertNotEqual(p.version_vigente_id, anterior)
        self.assertEqual(len(p.versiones), 2)

    def test_solo_se_acepta_la_version_vigente(self):                          # CA-013
        anterior = self.propuesta().version_vigente_id
        self.s.generar_nueva_version(self.pid, CONTENIDO, T0 + timedelta(days=1))
        r = self.s.aceptar_propuesta(self.pid, anterior, T0 + timedelta(days=2))
        self.assertFalse(r.exito)
        self.assertEqual(self.propuesta().estado, EstadoPropuesta.EN_REVISION_CLIENTE)

    def test_propuesta_no_aceptada_se_cierra_y_el_evento_sigue_en_gestion(self):   # SE-011, CA-092, CA-093
        self.assertTrue(self.s.cerrar_propuesta_no_aceptada(self.pid, 'El Cliente no respondió', T0 + timedelta(days=10)).exito)
        self.app.despachador.despachar()
        self.assertEqual(self.propuesta().estado, EstadoPropuesta.CERRADA_NO_ACEPTACION)
        self.assertEqual(self.app.repos.eventos.obtener_por_id(self.evento_id).estado, EstadoEvento.EN_GESTION)
        self.assertFalse(self.s.aceptar_propuesta(self.pid, self.propuesta().version_vigente_id, T0 + timedelta(days=11)).exito)


# ---------------------------------------------------------------- CU-02 Formalizar la contratación
class CU02Contratacion(unittest.TestCase):
    def test_flujo_principal(self):                                           # BN-009, BN-005, CA-015 a CA-019
        e = Escenario()
        ant = e.obligacion('Anticipo')
        self.assertEqual(ant.importe, Importe(D('3000.00')))                  # 30 % del costo total
        self.assertEqual(ant.plazo.vence, limite_exclusivo_dias_habiles(T0, 3))   # 3 días hábiles tras la firma; límite exclusivo (E-1)
        e.confirmar_contratacion()
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        self.assertEqual(e.evento().estado, EstadoEvento.EN_ORGANIZACION)
        self.assertEqual(len(e.evento().servicios), 1)
        saldo = e.obligacion('SaldoContratoOriginal')
        self.assertEqual(saldo.importe, Importe(D('7000.00')))
        self.assertEqual(saldo.plazo.vence, limite_exclusivo_dias_habiles_antes(FECHA_EVENTO, 3))

    def test_sin_politica_comunicada_no_se_confirma(self):                    # CA-016, CA-019
        e = Escenario()
        ob = e.obligacion('Anticipo')
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('3000.00')), T0 + timedelta(days=1), 'C-1'); e.d.despachar()
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.FIRMADO)
        r = e.s.contratacion.confirmar_contratacion(e.contrato_id, T0 + timedelta(days=1))
        self.assertFalse(r.exito)
        self.assertIn('política de no reembolso comunicada', r.pendientes)
        self.assertEqual(e.evento().estado, EstadoEvento.EN_GESTION)

    def test_anticipo_parcial_no_confirma(self):                              # CA-019; E-3: el importe menor ya no es «incorrecto»
        e = Escenario()
        e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
        ob = e.obligacion('Anticipo')
        r = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('2500.00')), T0 + timedelta(days=1), 'C-1'); e.d.despachar()
        self.assertEqual(r.datos['estado'], EstadoPago.VERIFICADO.value)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)      # el pago parcial no liquida el anticipo
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EstadoContrato.FIRMADO)

    def test_confirmacion_repetida_no_duplica_efectos(self):                  # idempotencia (Etapa 5)
        e = Escenario(); e.confirmar_contratacion()
        servicios = dict(e.evento().servicios)
        r = e.s.contratacion.confirmar_contratacion(e.contrato_id, T0 + timedelta(days=2)); e.d.despachar()
        self.assertTrue(r.exito)
        self.assertEqual(e.evento().servicios.keys(), servicios.keys())
        self.assertEqual(len([o for o in e.ec().obligaciones.values() if o.concepto == ConceptoPago.SALDO_CONTRATO_ORIGINAL]), 1)


# ---------------------------------------------------------------- CU-03 Cancelación, inicio y cierre del evento
class CU03CierreDelEvento(unittest.TestCase):
    def test_cancelacion_solicitada_procedente(self):                         # BN-008, CA-084, CA-087
        e = Escenario(); e.confirmar_contratacion()
        self.assertTrue(e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Cambio de planes', T0 + timedelta(days=3)).exito)
        e.d.despachar()
        self.assertEqual(e.evento().estado, EstadoEvento.CANCELADO)
        self.assertEqual(len(e.avisos('Evento cancelado')), 1)

    def test_cancelacion_sin_contratacion_confirmada_se_rechaza(self):        # CA-084
        e = Escenario()
        self.assertFalse(e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', T0 + timedelta(days=1)).exito)
        self.assertEqual(e.evento().estado, EstadoEvento.EN_GESTION)

    def test_cancelacion_despues_del_inicio_se_rechaza(self):                 # CA-088
        e = Escenario(); e.confirmar_contratacion()
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', FECHA_EVENTO + timedelta(hours=1))
        self.assertFalse(r.exito)
        ev = e.evento()
        self.assertEqual(ev.estado, EstadoEvento.EN_EJECUCION)
        self.assertEqual(ev.solicitudes_cancelacion[-1].estado, EstadoSolicitudCancelacion.RECHAZADA_INICIO_EVENTO)
        self.assertEqual(len(e.avisos('Cancelación no procedente')), 1)

    def test_finalizado_solo_si_se_realizo(self):                             # BN-010, CA-094, CA-095
        e = Escenario(); e.confirmar_contratacion()
        self.assertFalse(e.s.cierre.finalizar_evento(e.evento_id, FECHA_EVENTO).exito)      # aún En organización
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO)
        self.assertTrue(e.s.cierre.finalizar_evento(e.evento_id, FECHA_EVENTO + timedelta(hours=6)).exito)
        self.assertEqual(e.evento().estado, EstadoEvento.FINALIZADO)
        c = Escenario(); c.confirmar_contratacion()
        c.s.cierre.gestionar_cancelacion_solicitada(c.evento_id, 'Desiste', T0 + timedelta(days=3))
        self.assertFalse(c.s.cierre.finalizar_evento(c.evento_id, FECHA_EVENTO).exito)   # Cancelado ≠ Finalizado

    def test_inicio_del_evento_cierra_las_solicitudes_pendientes(self):       # BN-006, CA-070, CA-096
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-7', True, Importe(D(800)), CondicionesServicio('Otro banquete'))]))
        e.confirmar_contratacion()
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio de menú', Importe(D(100)), T0 + timedelta(days=5)).datos['solicitud_id']
        servicio = next(iter(e.evento().servicios))
        proveedor_original = e.evento().servicios[servicio].proveedor_id
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, T0 + timedelta(days=5))
        self.assertTrue(r.exito, r.mensaje)                                       # Evento activo: la sustitución procede
        sp = r.datos['sustitucion_id']
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(sp).estado, ESP.EN_BUSQUEDA_ALTERNATIVA)
        e.d.despachar()
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.CERRADA_INICIO_EVENTO)
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(sp).estado, ESP.CERRADA_INICIO_EVENTO)
        self.assertEqual(e.evento().servicios[servicio].proveedor_id, proveedor_original)   # no se confirma el reemplazo


# ---------------------------------------------------------------- CU-04 Cambios al evento
class CU04Cambios(unittest.TestCase):
    def setUp(self):
        self.e = Escenario(); self.e.confirmar_contratacion()

    def _registrar(self, dias_antes, **extra):
        r = self.e.s.cambios.registrar_solicitud_cambio(self.e.evento_id, self.e.contrato_id, 'Cambio', Importe(D(150)),
                                                         FECHA_EVENTO - timedelta(days=dias_antes), **extra)
        return r.datos['solicitud_id']

    def cambio(self, sid):
        return self.e.app.repos.cambios.obtener_por_id(sid)

    def test_cargo_tardio_segun_anticipacion(self):                           # BN-003, SE-005, CA-061, CA-062
        self.assertFalse(self.cambio(self._registrar(7)).aplica_cargo_tardio)
        self.assertTrue(self.cambio(self._registrar(6)).aplica_cargo_tardio)

    def test_ruta_a_no_viable(self):                                          # SE-008, CA-060, CA-069
        sid = self._registrar(10)
        self.e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(False, 'Proveedor sin disponibilidad'), None, FECHA_EVENTO - timedelta(days=10))
        self.assertEqual(self.cambio(sid).estado, ESC.NO_PROCEDENTE)

    def test_ruta_c_sin_impacto_pasa_a_formalizacion(self):                   # BN-003 (ruta C)
        sid = self._registrar(10)
        self.e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), None, FECHA_EVENTO - timedelta(days=10))
        s = self.cambio(sid)
        self.assertEqual(s.estado, ESC.PENDIENTE_FORMALIZACION)
        self.assertFalse(s.importes_por_pagar)

    def test_cambio_antes_de_contratar_se_rechaza(self):                      # CA-039
        e = Escenario()
        r = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(150)), T0 + timedelta(days=1))
        self.assertFalse(r.exito)

    def test_falta_de_pago_en_24_horas_cierra_y_devuelve_lo_recibido(self):   # BN-003, SE-012, CA-067, CA-097, CA-098
        e, dia = self.e, FECHA_EVENTO - timedelta(days=10)
        sid = self._registrar(10, datos_propuestos=DatosEvento('Boda', FECHA_EVENTO, 'Salón', 120))
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), Importe(D(900)), dia)
        e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, dia))
        e.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', True, dia))
        e.s.cambios.registrar_anexo_cambio(sid, 'Anexo 120 invitados', dia); e.d.despachar()
        ob = e.s.pagos.comunicar_solicitud_pago_cambio(sid, dia).datos['obligacion_id']
        self.assertEqual(self.cambio(sid).estado, ESC.PENDIENTE_PAGO)
        self.assertFalse(e.s.cambios.cerrar_cambio_por_falta_de_pago(sid, dia + timedelta(hours=23)).exito)   # plazo vigente
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, Importe(D(900)), dia + timedelta(hours=30), 'C-TARDE')   # fuera de plazo
        self.assertFalse(e.s.cambios.confirmar_cambio(sid, dia + timedelta(hours=31)).exito)
        self.assertTrue(e.s.cambios.cerrar_cambio_por_falta_de_pago(sid, dia + timedelta(hours=32)).exito); e.d.despachar()
        self.assertEqual(self.cambio(sid).estado, ESC.CERRADA_FALTA_PAGO)
        self.assertEqual(e.evento().datos.invitados_aproximados, 100)                 # se conserva la configuración
        dev = [d for d in e.ec().devoluciones if d.solicitud_id == sid]
        self.assertEqual(len(dev), 1)
        self.assertEqual(dev[0].importe, Importe(D(900)))
        e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, dev[0].devolucion_id, dia + timedelta(days=1)); e.d.despachar()
        e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, dev[0].devolucion_id, dia + timedelta(days=1)); e.d.despachar()
        self.assertEqual(e.ec().devoluciones[0].estado, EstadoDevolucion.EFECTUADA)
        self.assertEqual(len(e.avisos('Devolución efectuada')), 1)


# ---------------------------------------------------------------- CU-05 Servicios adicionales y proveedores
class CU05ServiciosAdicionales(unittest.TestCase):
    def setUp(self):
        self.cond = CondicionesServicio('DJ 4 horas')
        self.e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), self.cond)]))
        self.e.confirmar_contratacion()
        self.dia = FECHA_EVENTO - timedelta(days=10)
        s = self.e.s.adicionales
        self.sa = s.registrar_solicitud_servicio_adicional(self.e.evento_id, self.e.contrato_id, 'DJ', self.dia).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(self.sa, [], self.dia)

    def test_pago_antes_del_anexo_se_rechaza(self):                           # CA-082
        e, s = self.e, self.e.s.adicionales
        s.registrar_aprobacion_cliente_servicio_adicional(self.sa, Decision('Cliente', True, self.dia))
        s.registrar_autorizacion_administracion_servicio_adicional(self.sa, Decision('Administración', True, self.dia))
        r = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, self.sa, ConceptoPago.SERVICIO_ADICIONAL, Importe(D(500)), self.dia)
        self.assertFalse(r.exito)
        self.assertEqual([o for o in e.ec().obligaciones.values() if o.concepto == ConceptoPago.SERVICIO_ADICIONAL], [])

    def test_sin_autorizacion_administrativa_no_se_confirma(self):            # BN-004, CA-081
        e, s = self.e, self.e.s.adicionales
        s.registrar_aprobacion_cliente_servicio_adicional(self.sa, Decision('Cliente', True, self.dia))
        s.registrar_autorizacion_administracion_servicio_adicional(self.sa, Decision('Administración', False, self.dia, 'Sin presupuesto'))
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(self.sa).estado, ESA.NO_AUTORIZADA)
        self.assertFalse(s.confirmar_servicio_adicional(self.sa, self.dia + timedelta(hours=1)).exito)
        self.assertNotIn('DJ', [x.servicio for x in e.evento().servicios.values()])

    def test_importe_del_servicio_es_el_costo_del_proveedor(self):            # BN-004: sin cargo propio de Eventos Nova
        s = self.e.app.repos.adicionales.obtener_por_id(self.sa)
        self.assertEqual(s.disponibilidad.costo, Importe(D(500)))
        self.assertEqual(s.disponibilidad.condiciones, self.cond)



class CU04y05Alternativas(unittest.TestCase):
    def test_cliente_rechaza_el_cambio_con_impacto(self):                      # BN-003, CA-040
        e = Escenario(); e.confirmar_contratacion(); dia = FECHA_EVENTO - timedelta(days=10)
        sid = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Más invitados', Importe(D(150)), dia,
                                                      datos_propuestos=DatosEvento('Boda', FECHA_EVENTO, 'Salón', 130)).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), Importe(D(600)), dia)
        e.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', False, dia, 'No acepta el costo'))
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sid).estado, ESC.RECHAZADA_CLIENTE)
        self.assertEqual(e.evento().datos.invitados_aproximados, 100)

    def test_servicio_adicional_con_saldo_vencido_queda_detenido(self):        # SE-006, CA-072 (Domain Service)
        from domain.servicios_dominio import EvaluarRegularizacionDeSolicitudes, SituacionSaldo
        from domain.valores import CondicionTemporal
        d = EvaluarRegularizacionDeSolicitudes().evaluar(SituacionSaldo(True), False, CondicionTemporal(True))
        self.assertTrue(d.detener_por_saldo)
        self.assertFalse(d.puede_continuar)

    def test_observacion_o01_solicitud_nueva_con_saldo_vencido(self):          # Etapa 9, observación O-01
        """O-01 (resuelta, SE-004): el orden es evento cancelado o iniciado, plazo de cinco días y saldo vencido, y se
        registra solo el primer motivo. Una solicitud nueva sin los cinco días naturales es No procedente aunque exista
        saldo vencido; el saldo se atiende por su propio protocolo (SE-007)."""
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        sa = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', e.comunicacion)
        self.assertEqual(sa.datos['estado'], ESA.NO_PROCEDENTE.value)
        self.assertIn('cinco días', sa.datos['motivo'])                       # se registra solo el primer motivo

    def test_alternativa_rechazada_conserva_el_proveedor_original(self):       # SE-001, CA-054
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-7', True, Importe(D(800)), CondicionesServicio('Otro banquete'))]))
        e.confirmar_contratacion(); dia = T0 + timedelta(days=5)
        servicio = next(iter(e.evento().servicios)); original = e.evento().servicios[servicio].proveedor_id
        sid = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, dia).datos['sustitucion_id']
        e.s.sustitucion.buscar_alternativa_sustitucion(sid, CondicionesServicio('Otro banquete'), Importe(D(800)), dia)
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(sid).estado, ESP.PENDIENTE_APROBACION_CLIENTE)
        e.s.sustitucion.registrar_decision_cliente_sustitucion(sid, Decision('Cliente', False, dia, 'No le convence')); e.d.despachar()
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(sid).estado, ESP.EN_BUSQUEDA_ALTERNATIVA)
        self.assertEqual(e.evento().servicios[servicio].proveedor_id, original)


if __name__ == '__main__':
    unittest.main()
