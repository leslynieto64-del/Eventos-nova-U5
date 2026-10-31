"""E3G (H-06, H-07/H-17 y H-21).

H-06: el importe de un servicio adicional es el costo establecido por el proveedor (BN-004, GL-016, CA-073, SE-004); Eventos
      Nova no aplica un cargo propio y no se acepta un importe arbitrario.
H-07/H-17: un identificador inexistente produce un rechazo de negocio (Resultado), no una excepción técnica.
H-21: con el Evento ya iniciado o finalizado, el aviso del proveedor queda fuera del alcance del sistema (BPMN SP-05, Bitácora,
      Informe): no se inicia la sustitución.
Ejecutar desde la raíz:  python -m unittest tests.test_h06_h07_h21_correcciones -v"""
import inspect
import os
import pickle
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                        # noqa: E402
from application import servicios as S                                                                 # noqa: E402
from application.resultados import Resultado                                                           # noqa: E402
from domain.valores import (CondicionesServicio, ConceptoPago as CP, ContenidoPropuesta, DatosEvento, Decision,   # noqa: E402
                            DisponibilidadProveedor, EstadoEvento, EstadoObligacionPago as EO,
                            EstadoSolicitudServicioAdicional as ESA, EstadoSustitucionProveedor as ESP, Importe,
                            ResultadoViabilidad, TipoSolicitud)
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada, EjecutorDevolucionesSimulado   # noqa: E402
from infrastructure.composicion import construir                                                       # noqa: E402

DIA = FECHA_EVENTO - timedelta(days=10)


def importe(x):
    return Importe(D(x))


def opciones(*costos):
    return [DisponibilidadProveedor(f'PV-{i}', True, importe(c), CondicionesServicio(f'DJ {i}')) for i, c in enumerate(costos, 1)]


def adicional(e, anexo=True):
    """Servicio adicional con el costo ya determinado, aprobado y autorizado y, si `anexo`, formalizado en su anexo."""
    s = e.s.adicionales
    sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', DIA).datos['solicitud_id']
    assert s.evaluar_disponibilidad_servicio_adicional(sa, [], DIA).exito
    s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, DIA))
    s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, DIA))
    if anexo:
        s.registrar_anexo_servicio_adicional(sa, 'Anexo del servicio', DIA)
    e.d.despachar()
    return sa


def solicitud(e, sa):
    return e.app.repos.adicionales.obtener_por_id(sa)


def comunicar(e, sa, cantidad, concepto=CP.SERVICIO_ADICIONAL):
    return e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, concepto, cantidad, DIA)


# ======================================================================= H-06
class ImporteDelServicioAdicional(unittest.TestCase):
    def test_el_importe_es_el_costo_del_proveedor_para_varios_costos(self):                    # BN-004, CA-073
        for costo in ('500', '275.50', '1', '1234.56'):
            with self.subTest(costo=costo):
                e = Escenario(ConsultaDisponibilidadSimulada(opciones(costo))); e.confirmar_contratacion()
                sa = adicional(e)
                self.assertEqual(solicitud(e, sa).importe_a_cobrar, importe(costo))
                r = comunicar(e, sa, importe(costo))
                self.assertTrue(r.exito, r.mensaje)
                (o,) = e.ec().obligaciones_de(sa)
                self.assertEqual((o.concepto, o.importe, o.origen_id, o.estado), (CP.SERVICIO_ADICIONAL, importe(costo), sa, EO.PENDIENTE))
                self.assertEqual(o.plazo.vence - o.plazo.inicio, timedelta(hours=24))

    def test_un_importe_distinto_del_costo_se_rechaza_sin_efectos(self):                       # BN-004, CA-073
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        sa = adicional(e)
        avisos = len(e.avisos('Solicitud de pago'))
        for mal in ('0', '1', '499.99', '500.01', '800'):
            with self.subTest(importe=mal):
                r = comunicar(e, sa, importe(mal))
                self.assertFalse(r.exito)
                self.assertIn('costo establecido por el proveedor', r.mensaje)
                self.assertEqual(e.ec().obligaciones_de(sa), [])
                self.assertEqual(solicitud(e, sa).estado, ESA.AUTORIZADA)
                self.assertIsNone(solicitud(e, sa).obligacion_pago_id)
        self.assertEqual(len(e.avisos('Solicitud de pago')), avisos)                            # no se avisó al Cliente
        self.assertTrue(comunicar(e, sa, importe('500')).exito)                                 # el importe correcto sí procede
        self.assertEqual(solicitud(e, sa).estado, ESA.PENDIENTE_PAGO)

    def test_la_misma_cantidad_con_otra_escala_decimal_es_el_mismo_importe(self):
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        self.assertTrue(comunicar(e, adicional(e), importe('500.00')).exito)

    def test_un_concepto_distinto_se_rechaza_aunque_el_importe_coincida(self):                 # BN-005 (conceptos independientes)
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        sa = adicional(e)
        for concepto in (CP.CAMBIO, CP.CARGO_CAMBIO_TARDIO, CP.CARGOS_MORATORIOS):
            with self.subTest(concepto=concepto.name):
                self.assertFalse(comunicar(e, sa, importe('500'), concepto).exito)
                self.assertEqual(e.ec().obligaciones_de(sa), [])

    def test_el_importe_es_el_del_proveedor_elegido_y_no_el_de_otro(self):                     # CA-075
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('100', '120'))); e.confirmar_contratacion()
        sa = adicional(e)                                                    # se elige la primera opción disponible: 100
        self.assertEqual(solicitud(e, sa).disponibilidad.proveedor_id, 'PV-1')
        self.assertFalse(comunicar(e, sa, importe('120')).exito)
        self.assertTrue(comunicar(e, sa, importe('100')).exito)

    def test_eventos_nova_no_aplica_un_cargo_propio_al_servicio_adicional(self):               # SE-004, CA-073
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        sa = adicional(e)
        comunicar(e, sa, importe('500'))
        self.assertEqual([(o.concepto, o.importe) for o in e.ec().obligaciones_de(sa)], [(CP.SERVICIO_ADICIONAL, importe('500'))])

    def test_los_rechazos_de_estado_y_anexo_tienen_precedencia(self):                          # CA-082
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        sin_anexo = adicional(e, anexo=False)
        r = comunicar(e, sin_anexo, importe('1'))                          # importe incorrecto y además sin anexo
        self.assertFalse(r.exito)
        self.assertIn('anexo', r.mensaje)
        self.assertNotIn('costo establecido', r.mensaje)

    def test_sin_costo_determinado_no_hay_importe_a_cobrar(self):
        """Solicitud recién registrada: aún no hay costo, y la solicitud de pago se rechaza por estado (CA-082)."""
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        sa = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', DIA).datos['solicitud_id']
        self.assertIsNone(solicitud(e, sa).importe_a_cobrar)
        r = comunicar(e, sa, importe('500'))
        self.assertFalse(r.exito)
        self.assertEqual(e.ec().obligaciones_de(sa), [])

    def test_con_el_servicio_listo_para_pagar_pero_sin_costo_se_rechaza_por_falta_de_costo(self):   # BN-004, CA-075
        """Rama defensiva: el flujo normal no llega a Autorizada sin costo, así que el estado se fuerza para que la
        solicitud de pago supere la validación de estado y anexo y se compruebe el rechazo por costo no determinado."""
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        sa = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', DIA).datos['solicitud_id']
        s = solicitud(e, sa)
        s.estado, s.anexo_id = ESA.AUTORIZADA, 'AX-1'
        with S.transaccion(e.app.uow, s):
            e.app.repos.adicionales.guardar(s)
        self.assertIsNone(solicitud(e, sa).importe_a_cobrar)
        avisos = len(e.avisos('Solicitud de pago'))
        r = comunicar(e, sa, importe('500'))
        self.assertFalse(r.exito)
        self.assertIn('No se ha determinado el costo', r.mensaje)
        self.assertEqual(e.ec().obligaciones_de(sa), [])
        self.assertEqual((solicitud(e, sa).estado, solicitud(e, sa).obligacion_pago_id), (ESA.AUTORIZADA, None))
        self.assertEqual(len(e.avisos('Solicitud de pago')), avisos)

    def test_el_pago_exacto_confirma_el_servicio_y_uno_distinto_no_lo_hace(self):              # CA-080, CA-082
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        sa = adicional(e)
        ob = comunicar(e, sa, importe('500')).datos['obligacion_id']
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, importe('300'), DIA + timedelta(hours=2), 'C-parcial')
        self.assertFalse(e.s.adicionales.confirmar_servicio_adicional(sa, DIA + timedelta(hours=3)).exito)
        e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob, importe('200'), DIA + timedelta(hours=4), 'C-resto')
        self.assertTrue(e.s.adicionales.confirmar_servicio_adicional(sa, DIA + timedelta(hours=5)).exito)
        self.assertEqual(solicitud(e, sa).estado, ESA.CONFIRMADA)


# ======================================================================= H-07 / H-17
def _argumento(nombre):
    n = nombre.lower()
    if n.endswith('_id'):
        return 'NO-EXISTE'
    if n in ('ahora', 'fecha', 'comunicado_en', 'revisado_en', 'verificado_en', 'registrado_en', 'fecha_cierre'):
        return datetime(2026, 11, 1, 10, 0)
    if n == 'tarifa_vigente' or n.startswith('importe') or n.startswith('costo_adicional'):
        return importe('1')
    return {'decision': Decision('x', True, datetime(2026, 11, 1)), 'contenido': ContenidoPropuesta(('s',), ('p',), importe('1'), 'c'),
            'modificaciones': ContenidoPropuesta(('s',), ('p',), importe('1'), 'c'), 'resultado': ResultadoViabilidad(True),
            'tipo': TipoSolicitud.SERVICIO_ADICIONAL, 'concepto': CP.SERVICIO_ADICIONAL, 'servicios': ['s'],
            'condiciones_alternativa': CondicionesServicio('x'), 'proveedores_actuales': [],
            'datos': DatosEvento('Boda', datetime(2026, 11, 20, 18), 'L', 1)}.get(
        n, True if n in ('politica_incluida', 'sin_pago_tras_seguimiento', 'verificar_ahora', 'acepta_esperar', 'disponible') else 'x')


ATRIBUTO = {'GestionPropuestaService': 'propuestas', 'FormalizarContratacionService': 'contratacion', 'GestionPagosService': 'pagos',
            'GestionCierreEventoService': 'cierre', 'GestionCambiosEventoService': 'cambios',
            'GestionServiciosAdicionalesService': 'adicionales', 'GestionSustitucionProveedorService': 'sustitucion',
            'GestionProveedoresServicioService': 'proveedores'}
# no dependen de un identificador: el alta de un evento y el proceso periódico de la llegada de T (D-3), que recorre los eventos vencidos
CREAN_DATOS = {('GestionPropuestaService', 'registrar_evento'), ('GestionCierreEventoService', 'procesar_eventos_vencidos')}


def metodos_con_resultado():
    for clase, atributo in ATRIBUTO.items():
        for nombre, f in inspect.getmembers(getattr(S, clase), inspect.isfunction):
            if not nombre.startswith('_') and inspect.signature(f).return_annotation in ('Resultado', Resultado):
                yield clase, atributo, nombre


class IdentificadoresInexistentes(unittest.TestCase):
    def test_todos_los_casos_de_uso_rechazan_identificadores_inexistentes(self):               # H-07, H-17
        revisados = 0
        for clase, atributo, nombre in metodos_con_resultado():
            if (clase, nombre) in CREAN_DATOS:
                continue
            with self.subTest(servicio=clase, metodo=nombre):
                app = construir()
                metodo = getattr(getattr(app.servicios, atributo), nombre)
                r = metodo(*[_argumento(p) for p in inspect.signature(metodo).parameters])
                self.assertIsInstance(r, Resultado)
                self.assertFalse(r.exito, r.mensaje)
                self.assertTrue(r.mensaje)
                self.assertEqual(app.uow.outbox, [])                                            # sin eventos ni escrituras
                self.assertTrue(all(not repo._alm.datos for repo in vars(app.repos).values()))
                revisados += 1
        self.assertGreaterEqual(revisados, 45)                                                  # 47 al corregirse H-07/H-17

    def test_mensajes_de_los_casos_representativos(self):
        app = construir(); s = app.servicios
        casos = [(lambda: s.propuestas.generar_nueva_version('PR-x', ContenidoPropuesta(('s',), ('p',), importe('1'), 'c'), T0), 'La propuesta no existe.'),
                 (lambda: s.contratacion.registrar_firma_contrato('CT-x', T0), 'El contrato no existe.'),
                 (lambda: s.cierre.finalizar_evento('EV-x', T0), 'El evento no existe.'),
                 (lambda: s.pagos.registrar_y_verificar_pago('EC-x', 'OB-x', importe('1'), T0, 'C'), 'El estado de cuenta no existe.'),
                 (lambda: s.cambios.confirmar_cambio('SC-x', T0), 'La solicitud de cambio no existe.'),
                 (lambda: s.adicionales.confirmar_servicio_adicional('SA-x', T0), 'La solicitud de servicio adicional no existe.'),
                 (lambda: s.sustitucion.confirmar_sustitucion_proveedor('SP-x', T0), 'La sustitución de proveedor no existe.')]
        for llamada, mensaje in casos:
            with self.subTest(mensaje=mensaje):
                r = llamada()
                self.assertEqual((r.exito, r.mensaje), (False, mensaje))

    def test_una_devolucion_inexistente_se_rechaza_sin_invocar_al_ejecutor(self):
        e = Escenario(); e.confirmar_contratacion()
        with mock.patch.object(EjecutorDevolucionesSimulado, 'ejecutar') as ejecutor:
            r = e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, 'DV-no-existe', T0)
        self.assertEqual((r.exito, r.mensaje), (False, 'La devolución no existe.'))
        ejecutor.assert_not_called()

    def test_contrato_inexistente_o_sin_estado_de_cuenta(self):                                # H-07
        e = Escenario(ConsultaDisponibilidadSimulada(opciones('500'))); e.confirmar_contratacion()
        servicio = next(iter(e.evento().servicios))
        for nombre, llamada in (
                ('cambio', lambda: e.s.cambios.registrar_solicitud_cambio(e.evento_id, 'CT-x', 'c', importe('150'), DIA)),
                ('adicional', lambda: e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, 'CT-x', 'DJ', DIA)),
                ('sustitución', lambda: e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, 'CT-x', DIA))):
            with self.subTest(caso=nombre):
                r = llamada()
                self.assertFalse(r.exito)
                self.assertIn('estado de cuenta', r.mensaje)
        self.assertEqual(e.app.repos.cambios.listar_todas(), [])
        self.assertEqual(e.app.repos.adicionales.listar_todas(), [])
        self.assertEqual(e.app.repos.sustituciones.listar_todas(), [])

    def test_un_servicio_adicional_sobre_un_evento_sin_contrato_se_rechaza(self):              # H-07 (caso original)
        e = Escenario()                                                    # evento En gestión: contrato firmado, sin confirmar
        sin_contrato = e.s.propuestas.registrar_evento('CL-2', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 10), ['Banquete']).datos['evento_id']
        r = e.s.adicionales.registrar_solicitud_servicio_adicional(sin_contrato, 'CT-sin-firmar', 'DJ', DIA)
        self.assertFalse(r.exito)
        self.assertEqual(e.app.repos.adicionales.listar_todas(), [])

    def test_los_rechazos_existentes_conservan_su_mensaje(self):
        s = construir().servicios
        self.assertEqual(s.propuestas.crear_propuesta('EV-x', ContenidoPropuesta(('s',), ('p',), importe('1'), 'c'), T0).mensaje,
                         'El evento no existe o no está En gestión.')

    def test_un_servicio_contratado_inexistente_en_la_sustitucion_se_rechaza(self):
        e = Escenario(); e.confirmar_contratacion()
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, 'S-no-existe', e.contrato_id, DIA)
        self.assertEqual((r.exito, r.mensaje), (False, 'El servicio contratado no existe.'))
        self.assertEqual(e.app.repos.sustituciones.listar_todas(), [])


# ======================================================================= H-21
def snapshot(e):
    return ({n: pickle.dumps(r._alm.datos) for n, r in vars(e.app.repos).items()}, len(e.app.uow.outbox))


class SustitucionConEventoIniciado(unittest.TestCase):
    def rechazada(self, e, servicio, esperado):
        antes, avisos = snapshot(e), len(e.app.notificador.enviados)
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, FECHA_EVENTO + timedelta(hours=1))
        self.assertFalse(r.exito)
        self.assertIn(esperado, r.mensaje)
        self.assertEqual(snapshot(e), antes)                               # nada se guardó ni se publicó
        self.assertEqual(len(e.app.notificador.enviados), avisos)
        self.assertEqual(e.app.repos.sustituciones.listar_todas(), [])

    def test_con_el_evento_en_ejecucion_la_sustitucion_no_se_inicia(self):                     # SP-05, BN-006
        e = Escenario(); e.confirmar_contratacion(); servicio = next(iter(e.evento().servicios))
        self.assertTrue(e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO).exito); e.d.despachar()
        self.assertEqual(e.evento().estado, EstadoEvento.EN_EJECUCION)
        self.rechazada(e, servicio, 'después del inicio del Evento queda fuera del alcance del sistema (SP-05)')

    def test_con_el_evento_finalizado_la_sustitucion_no_se_inicia(self):                       # SP-05
        e = Escenario(); e.confirmar_contratacion(); servicio = next(iter(e.evento().servicios))
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO)
        self.assertTrue(e.s.cierre.finalizar_evento(e.evento_id, FECHA_EVENTO + timedelta(hours=6)).exito); e.d.despachar()
        self.assertEqual(e.evento().estado, EstadoEvento.FINALIZADO)
        self.rechazada(e, servicio, 'queda fuera del alcance del sistema (SP-05)')

    def test_con_el_evento_cancelado_conserva_su_rechazo_y_mensaje(self):                      # BN-008
        e = Escenario(); e.confirmar_contratacion(); servicio = next(iter(e.evento().servicios))
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Desiste', T0 + timedelta(days=3)); e.d.despachar()
        self.rechazada(e, servicio, 'El evento está cancelado: no se inician nuevas sustituciones de proveedor.')

    def test_sin_contratacion_confirmada_no_hay_servicios_que_sustituir(self):
        for nombre in ('en_gestion', 'cerrado_sin_contratacion'):
            with self.subTest(estado=nombre):
                e = Escenario()
                if nombre == 'cerrado_sin_contratacion':
                    contacto = T0 + timedelta(days=6)
                    e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
                    self.assertTrue(e.s.contratacion.dar_seguimiento_anticipo_pendiente(
                        e.contrato_id, contacto + timedelta(hours=25), 'Sin pago', True).exito)
                    e.d.despachar()
                    self.assertEqual(e.evento().estado, EstadoEvento.CERRADO_SIN_CONTRATACION)
                else:
                    self.assertEqual(e.evento().estado, EstadoEvento.EN_GESTION)
                self.rechazada(e, 'cualquiera', 'no tiene la contratación confirmada')

    def test_con_el_evento_en_organizacion_la_sustitucion_sigue_procediendo(self):             # SE-001, CA-046
        e = Escenario(); e.confirmar_contratacion(); servicio = next(iter(e.evento().servicios))
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, DIA)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(r.datos['sustitucion_id']).estado, ESP.EN_BUSQUEDA_ALTERNATIVA)

    def test_una_sustitucion_pendiente_al_iniciar_el_evento_se_cierra_y_no_admite_otra_nueva(self):   # CA-096, SP-05
        e = Escenario(); e.confirmar_contratacion(); servicio = next(iter(e.evento().servicios))
        sp = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, DIA).datos['sustitucion_id']
        e.d.despachar()
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        self.assertEqual(e.app.repos.sustituciones.obtener_por_id(sp).estado, ESP.CERRADA_INICIO_EVENTO)
        self.assertFalse(e.s.sustitucion.registrar_proveedor_no_disponible(
            e.evento_id, servicio, e.contrato_id, FECHA_EVENTO + timedelta(hours=1)).exito)
        self.assertEqual(len(e.app.repos.sustituciones.listar_todas()), 1)                    # no quedó una solicitud huérfana


if __name__ == '__main__':
    unittest.main()
