"""Etapa 7 — operaciones de la API por HTTP, sobre la composición en memoria y sobre PostgreSQL de pruebas.

Cada flujo recorre los casos de uso reales SOLO a través de HTTP (sin tocar servicios ni repositorios), con un reloj controlable.
Las mismas pruebas se ejecutan con ambas composiciones: el comportamiento observable debe ser idéntico."""
import os, sys, unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient                                                    # noqa: E402
from apoyo_bd import BaseConBD                                                               # noqa: E402
from apoyo_flujo import T0, FECHA_EVENTO                                                     # noqa: E402
from api.dependencias import obtener_reloj                                                   # noqa: E402
from api.main import crear_app                                                               # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                        # noqa: E402
from infrastructure.composicion import construir                                              # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente         # noqa: E402
from domain.valores import CondicionesServicio, DisponibilidadProveedor, Importe              # noqa: E402
from decimal import Decimal as D                                                              # noqa: E402


def iso(d: datetime) -> str:
    return d.isoformat()


DATOS = {'tipo': 'Boda', 'fecha_hora': iso(FECHA_EVENTO), 'lugar': 'Salón', 'invitados_aproximados': 100}
CONTENIDO = {'servicios': ['Banquete'], 'proveedores_considerados': ['PV-1'], 'costo_total': '10000.00', 'condiciones': 'Condiciones generales'}


class ApiHttp:
    """Mixin. Requiere `crear_contenedor(disponibilidad)`."""
    def crear_contenedor(self, disponibilidad=None):                                          # pragma: no cover
        raise NotImplementedError

    def arrancar(self, disponibilidad=None):
        self.contenedor = self.crear_contenedor(disponibilidad)
        self.ahora = T0
        self.app = crear_app(lambda: self.contenedor)
        self.app.dependency_overrides[obtener_reloj] = lambda: (lambda: self.ahora)
        self.cliente = TestClient(self.app)

    def setUp(self):
        self.arrancar()

    # ---- ayudas
    def post(self, url, cuerpo=None, esperado=(200, 201)):
        r = self.cliente.post(url, json=cuerpo) if cuerpo is not None else self.cliente.post(url)
        self.assertIn(r.status_code, (esperado if isinstance(esperado, tuple) else (esperado,)), f'POST {url} → {r.status_code}: {r.text}')
        return r.json()

    def get(self, url, esperado=200, **params):
        r = self.cliente.get(url, params=params)
        self.assertEqual(r.status_code, esperado, f'GET {url} → {r.status_code}: {r.text}')
        return r.json()

    def contratar(self, confirmar=True):
        """Evento → propuesta → aceptación → contrato → firma → política → anticipo; devuelve los identificadores."""
        self.ahora = T0
        evento = self.post('/eventos', {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']})['evento_id']
        propuesta = self.post(f'/eventos/{evento}/propuestas', CONTENIDO)['propuesta_id']
        version = f'{propuesta}-v1'
        self.post(f'/propuestas/{propuesta}/aceptacion', {'version_id': version})
        contrato = self.post(f'/propuestas/{propuesta}/contrato', {'politica_incluida': True})['datos']['contrato_id']
        self.post(f'/contratos/{contrato}/firma', {'fecha': iso(T0)})
        ids = {'evento': evento, 'propuesta': propuesta, 'contrato': contrato,
               'ec': self.get(f'/eventos/{evento}/pagos')['estadosCuenta'][0]['estadoCuentaId']}
        if confirmar:
            self.post(f'/contratos/{contrato}/comunicacion-politica-no-reembolso', {'fecha': iso(T0)})
            self.pagar(ids, 'Anticipo', '3000.00', T0 + timedelta(days=1))
        return ids

    def obligacion(self, ids, concepto):
        filas = self.get('/pagos-pendientes', evento_id=ids['evento'])['pagos']
        return next(f for f in filas if f['concepto'] == concepto)

    def pagar(self, ids, concepto, importe, fecha, **extra):
        ob = self.obligacion(ids, concepto)
        return self.post(f"/estados-cuenta/{ids['ec']}/pagos",
                         {'obligacion_id': ob['obligacionId'], 'importe': importe, 'fecha': iso(fecha), 'comprobante': f'C-{concepto}', **extra})

    def admin(self, ids):
        return self.get(f"/eventos/{ids['evento']}/administracion")

    def decision(self, actor, aprobada, fecha, motivo=''):
        return {'actor': actor, 'aprobada': aprobada, 'fecha': iso(fecha), 'motivo': motivo}


class FlujosDeNegocio(ApiHttp):
    def test_contratacion_completa(self):
        ids = self.contratar(confirmar=False)
        self.assertEqual(self.admin(ids)['estadoEvento'], 'En gestión')
        rechazo = self.post(f"/contratos/{ids['contrato']}/confirmacion", esperado=(200, 422))     # sin anticipo todavía
        self.post(f"/contratos/{ids['contrato']}/comunicacion-politica-no-reembolso", {'fecha': iso(T0)})
        self.pagar(ids, 'Anticipo', '3000.00', T0 + timedelta(days=1))
        info = self.admin(ids)
        self.assertEqual(info['estadoEvento'], 'En organización')
        self.assertEqual(info['contratos'][0]['estado'], 'Contratación confirmada')
        self.assertEqual(info['pagosRealizados'], '3000.00')
        self.assertEqual(info['saldoPendienteContratoOriginal'], '7000.00')
        self.assertEqual(sorted(p['concepto'] for p in self.get('/pagos-pendientes', evento_id=ids['evento'])['pagos']), ['SaldoContratoOriginal'])

    def test_versiones_y_cierre_de_la_propuesta(self):
        evento = self.post('/eventos', {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']})['evento_id']
        propuesta = self.post(f'/eventos/{evento}/propuestas', CONTENIDO)['propuesta_id']
        nueva = self.post(f'/propuestas/{propuesta}/versiones', {**CONTENIDO, 'costo_total': '12000.50'}, esperado=201)
        self.assertEqual(nueva['datos']['numero'], 2)
        antigua = self.post(f'/propuestas/{propuesta}/aceptacion', {'version_id': f'{propuesta}-v1'}, esperado=422)
        self.assertEqual(antigua['tipo'], 'rechazo_de_negocio')                                       # solo la vigente (CA-013)
        self.post(f'/propuestas/{propuesta}/cierre-por-no-aceptacion', {'motivo': 'No respondió'})
        self.assertEqual(self.post(f'/propuestas/{propuesta}/aceptacion', {'version_id': f'{propuesta}-v2'}, esperado=422)['tipo'], 'rechazo_de_negocio')
        self.assertEqual(self.get(f'/eventos/{evento}/administracion')['estadoEvento'], 'En gestión')   # SE-011

    def test_cambio_completo_con_pago_y_confirmacion(self):
        ids = self.contratar()
        self.ahora = dia = FECHA_EVENTO - timedelta(days=10)
        propuesto = {**DATOS, 'invitados_aproximados': 120}
        sid = self.post('/solicitudes-cambio', {'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'descripcion': 'Más invitados',
                                                 'tarifa_vigente': '150.00', 'datos_propuestos': propuesto}, esperado=201)['datos']['solicitud_id']
        self.post(f'/solicitudes-cambio/{sid}/viabilidad', {'viable': True, 'costo_adicional_proveedor': '900.00'})
        self.post(f'/solicitudes-cambio/{sid}/decision-cliente', self.decision('Cliente', True, dia, 'Conforme'))
        self.post(f'/solicitudes-cambio/{sid}/autorizacion', self.decision('Administración', True, dia))
        self.post(f'/solicitudes-cambio/{sid}/anexo', {'descripcion': 'Anexo 120 invitados'})
        ob = self.post(f'/solicitudes-cambio/{sid}/solicitud-pago', {'comunicado_en': iso(dia)})['datos']['obligacion_id']
        pendientes = self.get(f"/eventos/{ids['evento']}/solicitudes-pendientes")['solicitudes']
        self.assertEqual([s['estadoActual'] for s in pendientes], ['Pendiente de pago'])
        self.post(f"/estados-cuenta/{ids['ec']}/pagos", {'obligacion_id': ob, 'importe': '900.00', 'fecha': iso(dia + timedelta(hours=1)),
                                                          'comprobante': 'C-CAMBIO'})
        self.ahora = dia + timedelta(hours=2)
        self.post(f'/solicitudes-cambio/{sid}/confirmacion')
        self.assertEqual(self.admin(ids)['invitadosAproximados'], 120)                     # el cambio se aplicó al evento
        self.assertEqual(self.get('/solicitudes', evento_id=ids['evento'], tipo='cambio')['solicitudes'][0]['estadoActual'], 'Confirmada')

    def test_cambio_sin_pago_en_plazo_se_cierra_y_genera_devolucion(self):
        ids = self.contratar()
        self.ahora = dia = FECHA_EVENTO - timedelta(days=10)
        sid = self.post('/solicitudes-cambio', {'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'descripcion': 'x', 'tarifa_vigente': '0',
                                                 'datos_propuestos': {**DATOS, 'invitados_aproximados': 120}}, esperado=201)['datos']['solicitud_id']
        self.post(f'/solicitudes-cambio/{sid}/viabilidad', {'viable': True, 'costo_adicional_proveedor': '900'})
        self.post(f'/solicitudes-cambio/{sid}/decision-cliente', self.decision('Cliente', True, dia))
        self.post(f'/solicitudes-cambio/{sid}/autorizacion', self.decision('Administración', True, dia))
        self.post(f'/solicitudes-cambio/{sid}/anexo', {'descripcion': 'Anexo'})
        ob = self.post(f'/solicitudes-cambio/{sid}/solicitud-pago', {'comunicado_en': iso(dia)})['datos']['obligacion_id']
        self.assertEqual(self.post(f'/solicitudes-cambio/{sid}/cierre-por-falta-de-pago', esperado=422)['tipo'], 'rechazo_de_negocio')   # plazo vigente
        self.post(f"/estados-cuenta/{ids['ec']}/pagos", {'obligacion_id': ob, 'importe': '900', 'fecha': iso(dia + timedelta(hours=30)),
                                                          'comprobante': 'C-TARDE'})
        self.ahora = dia + timedelta(hours=32)
        self.post(f'/solicitudes-cambio/{sid}/cierre-por-falta-de-pago')
        devoluciones = self.get('/devoluciones-pendientes', evento_id=ids['evento'])['devoluciones']
        self.assertEqual(len(devoluciones), 1)
        self.assertEqual(devoluciones[0]['importe'], '900')
        self.post(f"/estados-cuenta/{ids['ec']}/devoluciones/{devoluciones[0]['devolucionId']}/ejecucion")
        self.assertEqual(self.get('/devoluciones-pendientes', evento_id=ids['evento'])['devoluciones'], [])
        self.assertEqual(self.admin(ids)['invitadosAproximados'], 100)                      # la configuración no cambió

    def test_servicio_adicional_completo(self):
        self.arrancar(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        ids = self.contratar()
        self.ahora = dia = FECHA_EVENTO - timedelta(days=10)
        sa = self.post('/solicitudes-servicio-adicional', {'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'servicio': 'DJ'},
                       esperado=201)['datos']['solicitud_id']
        self.post(f'/solicitudes-servicio-adicional/{sa}/disponibilidad', {'proveedores_actuales': []})
        self.post(f'/solicitudes-servicio-adicional/{sa}/aprobacion-cliente', self.decision('Cliente', True, dia))
        self.post(f'/solicitudes-servicio-adicional/{sa}/autorizacion', self.decision('Administración', True, dia))
        self.post(f'/solicitudes-servicio-adicional/{sa}/anexo', {'descripcion': 'Anexo DJ'})
        ob = self.post(f'/solicitudes-servicio-adicional/{sa}/solicitud-pago',
                       {'concepto': 'ServicioAdicional', 'importe': '500.00', 'comunicado_en': iso(dia)})['datos']['obligacion_id']
        self.post(f"/estados-cuenta/{ids['ec']}/pagos", {'obligacion_id': ob, 'importe': '500.00', 'fecha': iso(dia + timedelta(hours=1)),
                                                          'comprobante': 'C-DJ'})
        self.ahora = dia + timedelta(hours=2)
        self.post(f'/solicitudes-servicio-adicional/{sa}/confirmacion')
        info = self.admin(ids)
        self.assertIn('DJ', [p['servicio'] for p in info['proveedores']])                  # el servicio se incorporó al evento
        self.assertEqual(self.get('/solicitudes', evento_id=ids['evento'], tipo='servicio adicional')['solicitudes'][0]['estadoActual'], 'Confirmada')

    def test_sustitucion_con_alternativa_rechazada_y_luego_aceptada(self):
        self.arrancar(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-7', True, Importe(D(800)), CondicionesServicio('Otro banquete'))]))
        ids = self.contratar()
        self.ahora = dia = T0 + timedelta(days=5)
        servicio = self.admin(ids)['proveedores'][0]['servicioContratadoId']
        sid = self.post('/sustituciones', {'evento_id': ids['evento'], 'servicio_contratado_id': servicio, 'contrato_id': ids['contrato']},
                        esperado=201)['datos']['sustitucion_id']
        self.post(f'/sustituciones/{sid}/alternativa', {'condiciones_alternativa': 'Otro banquete', 'costo_adicional': '800.00'})
        self.post(f'/sustituciones/{sid}/decision-cliente', self.decision('Cliente', False, dia, 'No le convence'))
        pend = self.get('/solicitudes', evento_id=ids['evento'], tipo='sustitución de proveedor')['solicitudes'][0]
        self.assertEqual(pend['estadoActual'], 'En búsqueda de alternativa')
        self.post(f'/sustituciones/{sid}/alternativa', {'condiciones_alternativa': 'Otro banquete', 'costo_adicional': '800.00'})
        self.post(f'/sustituciones/{sid}/decision-cliente', self.decision('Cliente', True, dia))
        self.post(f'/sustituciones/{sid}/autorizacion', self.decision('Administración', True, dia))
        self.post(f'/sustituciones/{sid}/anexo', {'descripcion': 'Anexo reemplazo'})
        self.post(f'/sustituciones/{sid}/importe-adicional', {'importe': '800.00'})
        self.assertEqual(self.get('/solicitudes', evento_id=ids['evento'], tipo='sustitución de proveedor')['solicitudes'][0]['estadoActual'],
                         'Pendiente de formalización')

    def test_cancelacion_del_cliente_y_revision_administrativa(self):
        ids = self.contratar()
        self.ahora = T0 + timedelta(days=3)
        self.post(f"/eventos/{ids['evento']}/cancelacion", {'motivo': 'Cambio de planes'})
        self.assertEqual(self.admin(ids)['estadoEvento'], 'Cancelado')
        self.post(f"/eventos/{ids['evento']}/revision-administrativa", {'resultado': 'Sin reembolso', 'fecha': iso(self.ahora)})

    def test_cancelacion_sin_contratacion_confirmada_se_rechaza(self):
        ids = self.contratar(confirmar=False)
        r = self.post(f"/eventos/{ids['evento']}/cancelacion", {'motivo': 'Desiste'}, esperado=422)
        self.assertEqual(r['tipo'], 'rechazo_de_negocio')
        self.assertEqual(self.admin(ids)['estadoEvento'], 'En gestión')

    def test_inicio_y_finalizacion_del_evento(self):
        ids = self.contratar()
        self.assertEqual(self.post(f"/eventos/{ids['evento']}/finalizacion", {'fecha': iso(FECHA_EVENTO)}, esperado=422)['tipo'], 'rechazo_de_negocio')
        self.ahora = FECHA_EVENTO
        self.post(f"/eventos/{ids['evento']}/inicio")
        self.assertEqual(self.admin(ids)['estadoEvento'], 'En ejecución')
        self.post(f"/eventos/{ids['evento']}/finalizacion", {'fecha': iso(FECHA_EVENTO + timedelta(hours=6))})
        self.assertEqual(self.admin(ids)['estadoEvento'], 'Finalizado')

    def test_proveedores_del_evento(self):
        self.arrancar(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-1', True, Importe(D(100)), CondicionesServicio('Banquete'))]))
        ids = self.contratar()
        servicio = self.admin(ids)['proveedores'][0]['servicioContratadoId']
        base = f"/eventos/{ids['evento']}/servicios/{servicio}"
        self.get(f'{base}/disponibilidad')
        self.post(f'{base}/proveedor', {'proveedor_id': 'PV-1'})
        self.post(f'{base}/respuesta-proveedor', {'proveedor_id': 'PV-1', 'disponible': True})
        vista = self.get(f"/proveedores/PV-1/eventos/{ids['evento']}")
        self.assertEqual(vista['servicios'][0]['estado'], 'Confirmado por el proveedor')
        self.assertEqual(self.get(f"/proveedores/PV-OTRO/eventos/{ids['evento']}", esperado=404)['tipo'], 'no_encontrado')
        self.assertEqual(self.post(f'{base}/respuesta-proveedor', {'proveedor_id': 'PV-OTRO', 'disponible': True}, esperado=422)['tipo'],
                         'rechazo_de_negocio')

    def test_consultas(self):
        ids = self.contratar()
        proximos = self.get('/eventos', desde='2026-11-01T00:00:00', hasta='2026-12-01T00:00:00')['eventos']
        self.assertEqual([e['eventoId'] for e in proximos], [ids['evento']])
        self.assertEqual(self.get('/eventos', desde='2027-01-01T00:00:00', hasta='2027-02-01T00:00:00')['eventos'], [])
        self.assertEqual(self.get('/eventos', desde='2026-12-01T00:00:00', hasta='2026-11-01T00:00:00', esperado=422)['tipo'], 'rechazo_de_negocio')
        self.assertEqual(self.get('/solicitudes')['solicitudes'], [])
        pendientes = self.get('/servicios-pendientes-confirmacion', evento_id=ids['evento'])
        self.assertEqual([x['estado'] for x in pendientes['servicios']], ['Sin proveedor asignado'])
        self.assertEqual(self.get('/devoluciones-pendientes')['devoluciones'], [])
        self.assertEqual(self.get(f"/eventos/{ids['evento']}/administracion")['eventoId'], ids['evento'])
        self.assertEqual(self.get('/eventos/EV-NO-EXISTE/administracion', esperado=404)['tipo'], 'no_encontrado')
        self.assertEqual(self.get('/ready')['persistencia'], getattr(self.contenedor, 'modo', 'memoria'))

    def test_pago_registrado_se_verifica_despues_y_confirma_la_contratacion(self):
        ids = self.contratar(confirmar=False)
        self.post(f"/contratos/{ids['contrato']}/comunicacion-politica-no-reembolso", {'fecha': iso(T0)})
        pago = self.pagar(ids, 'Anticipo', '3000.00', T0 + timedelta(days=1), verificar_ahora=False)
        self.assertEqual(pago['datos']['estado'], 'Registrado')
        self.assertEqual(self.admin(ids)['estadoEvento'], 'En gestión')                         # registrado no es verificado
        self.post(f"/estados-cuenta/{ids['ec']}/pagos/{pago['datos']['pago_id']}/verificacion", {'verificado_en': iso(T0 + timedelta(days=2))})
        self.assertEqual(self.admin(ids)['estadoEvento'], 'En organización')
        self.assertEqual(self.post(f"/estados-cuenta/{ids['ec']}/pagos/PG-NO-EXISTE/verificacion",
                                   {'verificado_en': iso(T0)}, esperado=422)['tipo'], 'rechazo_de_negocio')

    def test_anticipo_no_recibido_seguimiento_y_cierre_sin_contratacion(self):
        ids = self.contratar(confirmar=False)
        self.ahora = T0 + timedelta(days=6)                                                       # pasaron los 3 días hábiles del anticipo
        contacto = T0 + timedelta(days=6)
        self.post(f"/contratos/{ids['contrato']}/seguimiento-anticipo",
                  {'fecha': iso(contacto), 'resultado_contacto': 'Se contactó al Cliente', 'sin_pago_tras_seguimiento': False})
        pronto = self.post(f"/contratos/{ids['contrato']}/seguimiento-anticipo",
                           {'fecha': iso(contacto + timedelta(hours=2)), 'resultado_contacto': '', 'sin_pago_tras_seguimiento': True}, esperado=422)
        self.assertEqual(pronto['tipo'], 'rechazo_de_negocio')                                    # aún dispone de 24 horas (CA-021)
        self.post(f"/contratos/{ids['contrato']}/seguimiento-anticipo",
                  {'fecha': iso(contacto + timedelta(hours=25)), 'resultado_contacto': '', 'sin_pago_tras_seguimiento': True})
        self.assertEqual(self.admin(ids)['estadoEvento'], 'Cerrado sin contratación')

    def test_saldo_vencido_cobro_regularizacion_y_cancelacion_formal(self):
        ids = self.contratar()
        limite = datetime.fromisoformat(self.obligacion(ids, 'SaldoContratoOriginal')['fechaLimite'])
        self.ahora = vencimiento = limite + timedelta(hours=1)
        self.post(f"/estados-cuenta/{ids['ec']}/vencimiento-saldo-original")
        self.assertEqual(self.obligacion(ids, 'SaldoContratoOriginal')['estado'], 'Vencida')
        comunicado = vencimiento + timedelta(hours=1)
        self.post(f"/estados-cuenta/{ids['ec']}/protocolo-cobro",
                  {'importe_moratorio': '200.00', 'comunicado_en': iso(comunicado), 'seguimiento': 'Recordatorio amistoso'})
        self.assertEqual(self.obligacion(ids, 'CargosMoratorios')['importe'], '200.00')
        self.assertEqual(self.post(f"/estados-cuenta/{ids['ec']}/regularizacion", {'revisado_en': iso(comunicado + timedelta(hours=2))},
                                   esperado=422)['tipo'], 'rechazo_de_negocio')                  # la ventana de 24 h sigue vigente
        revision = comunicado + timedelta(hours=25)
        self.ahora = revision
        self.post(f"/estados-cuenta/{ids['ec']}/regularizacion", {'revisado_en': iso(revision)})
        self.post(f"/eventos/{ids['evento']}/cancelacion-por-falta-de-regularizacion",
                  {'motivo': 'Saldo vencido sin regularizar', 'coordinador': 'Coordinador', 'fecha': iso(revision + timedelta(hours=1))})
        self.assertEqual(self.admin(ids)['estadoEvento'], 'Cancelado')                           # nunca automática: la registró el Coordinador

    def test_servicio_adicional_sin_proveedor_el_cliente_no_acepta_esperar(self):
        ids = self.contratar()
        self.ahora = dia = FECHA_EVENTO - timedelta(days=10)
        sa = self.post('/solicitudes-servicio-adicional', {'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'servicio': 'DJ'},
                       esperado=201)['datos']['solicitud_id']
        self.post(f'/solicitudes-servicio-adicional/{sa}/disponibilidad', {'proveedores_actuales': []})      # sin alternativas
        self.post(f'/solicitudes-servicio-adicional/{sa}/decision-espera', {'acepta_esperar': False})
        self.assertEqual(self.get('/solicitudes', evento_id=ids['evento'], tipo='servicio adicional')['solicitudes'][0]['estadoActual'],
                         'No se realizará')

    def test_servicio_adicional_sin_pago_en_plazo_se_cierra_por_falta_de_pago(self):
        self.arrancar(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]))
        ids = self.contratar()
        self.ahora = dia = FECHA_EVENTO - timedelta(days=10)
        sa = self.post('/solicitudes-servicio-adicional', {'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'servicio': 'DJ'},
                       esperado=201)['datos']['solicitud_id']
        self.post(f'/solicitudes-servicio-adicional/{sa}/disponibilidad', {'proveedores_actuales': []})
        self.post(f'/solicitudes-servicio-adicional/{sa}/aprobacion-cliente', self.decision('Cliente', True, dia))
        self.post(f'/solicitudes-servicio-adicional/{sa}/autorizacion', self.decision('Administración', True, dia))
        self.post(f'/solicitudes-servicio-adicional/{sa}/anexo', {'descripcion': 'Anexo DJ'})
        self.post(f'/solicitudes-servicio-adicional/{sa}/solicitud-pago', {'concepto': 'ServicioAdicional', 'importe': '500.00', 'comunicado_en': iso(dia)})
        self.assertEqual(self.post(f'/solicitudes-servicio-adicional/{sa}/cierre-por-falta-de-pago', esperado=422)['tipo'], 'rechazo_de_negocio')
        self.ahora = dia + timedelta(hours=25)
        self.post(f'/solicitudes-servicio-adicional/{sa}/cierre-por-falta-de-pago')
        self.assertEqual(self.get('/solicitudes', evento_id=ids['evento'], tipo='servicio adicional')['solicitudes'][0]['estadoActual'],
                         'Cerrada por falta de pago')

    def test_sustitucion_confirmada_reemplaza_al_proveedor_del_servicio(self):
        self.arrancar(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-7', True, Importe(D(800)), CondicionesServicio('Otro banquete'))]))
        ids = self.contratar()
        self.ahora = dia = T0 + timedelta(days=5)
        servicio = self.admin(ids)['proveedores'][0]['servicioContratadoId']
        sid = self.post('/sustituciones', {'evento_id': ids['evento'], 'servicio_contratado_id': servicio, 'contrato_id': ids['contrato']},
                        esperado=201)['datos']['sustitucion_id']
        self.post(f'/sustituciones/{sid}/alternativa', {'condiciones_alternativa': 'Otro banquete', 'costo_adicional': '800.00'})
        self.post(f'/sustituciones/{sid}/decision-cliente', self.decision('Cliente', True, dia))
        self.post(f'/sustituciones/{sid}/autorizacion', self.decision('Administración', True, dia))
        self.post(f'/sustituciones/{sid}/anexo', {'descripcion': 'Anexo reemplazo'})
        self.post(f'/sustituciones/{sid}/importe-adicional', {'importe': '800.00'})
        self.post(f'/sustituciones/{sid}/confirmacion')
        self.assertEqual(self.get('/solicitudes', evento_id=ids['evento'], tipo='sustitución de proveedor')['solicitudes'][0]['estadoActual'],
                         'Confirmada')
        self.assertEqual({p['proveedorId'] for p in self.admin(ids)['proveedores']
                          if p['servicioContratadoId'] == servicio}, {'PV-7'})


class ValidacionDeEntrada(ApiHttp):
    def test_importes_invalidos_se_rechazan_con_422(self):
        ids = self.contratar(confirmar=False)
        ob = self.obligacion(ids, 'Anticipo')['obligacionId']
        url = f"/estados-cuenta/{ids['ec']}/pagos"
        base = {'obligacion_id': ob, 'fecha': iso(T0), 'comprobante': 'C'}
        for malo in ('abc', 'ciento', 'NaN', 'Infinity', '-Infinity', '', None, [], True):
            with self.subTest(repr(malo)):
                r = self.cliente.post(url, json={**base, 'importe': malo})
                self.assertEqual(r.status_code, 422, r.text)
                self.assertIn('detail', r.json())                                        # validación de forma/tipo
        r = self.cliente.post(url, json={**base, 'importe': '-1'})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()['tipo'], 'rechazo_de_negocio')                         # importe negativo: lo rechaza el dominio
        self.assertEqual(self.get(f"/eventos/{ids['evento']}/pagos")['estadosCuenta'][0]['pagosRegistrados'], [])

    def test_booleanos_estrictos_fechas_sin_zona_y_campos_desconocidos(self):
        ids = self.contratar()
        servicio = self.admin(ids)['proveedores'][0]['servicioContratadoId']
        base = f"/eventos/{ids['evento']}/servicios/{servicio}"
        for malo in ('si', 'true', 1, 0, None):
            with self.subTest(repr(malo)):
                self.assertEqual(self.cliente.post(f'{base}/respuesta-proveedor', json={'proveedor_id': 'PV-1', 'disponible': malo}).status_code, 422)
        self.assertEqual(self.cliente.post(f"/contratos/{ids['contrato']}/firma", json={'fecha': '2026-10-01T10:00:00+00:00'}).status_code, 422)
        self.assertEqual(self.cliente.post(f"/contratos/{ids['contrato']}/firma", json={'fecha': 'ayer'}).status_code, 422)
        self.assertEqual(self.cliente.post(f"/contratos/{ids['contrato']}/firma", json={'fecha': iso(T0), 'otro': 1}).status_code, 422)
        self.assertEqual(self.cliente.post(f"/contratos/{ids['contrato']}/firma", json={}).status_code, 422)
        self.assertEqual(self.cliente.post(f"/propuestas/{ids['propuesta']}/contrato", json={'politica_incluida': 'si'}).status_code, 422)

    def test_tarifa_y_costos_negativos_los_rechaza_el_dominio_sin_dejar_rastro(self):
        ids = self.contratar()
        self.ahora = dia = FECHA_EVENTO - timedelta(days=10)
        r = self.cliente.post('/solicitudes-cambio', json={'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'descripcion': 'x',
                                                           'tarifa_vigente': '-5'})
        self.assertEqual((r.status_code, r.json()['tipo']), (422, 'rechazo_de_negocio'))
        self.assertEqual(self.get('/solicitudes')['solicitudes'], [])
        r = self.cliente.post('/solicitudes-cambio', json={'evento_id': ids['evento'], 'contrato_id': ids['contrato'], 'descripcion': 'x',
                                                           'tarifa_vigente': 'gratis'})
        self.assertEqual(r.status_code, 422)

    def test_decimales_largos_se_aceptan_sin_redondear(self):
        evento = self.post('/eventos', {'cliente_id': 'CL-1', 'datos': DATOS, 'servicios': ['Banquete']})['evento_id']
        propuesta = self.post(f'/eventos/{evento}/propuestas', CONTENIDO)['propuesta_id']
        nueva = self.post(f'/propuestas/{propuesta}/versiones', {**CONTENIDO, 'costo_total': '12345.678901234567'}, esperado=201)
        self.assertEqual(nueva['datos']['numero'], 2)

    def test_un_rechazo_conserva_el_formato_y_los_pendientes(self):
        ids = self.contratar(confirmar=False)
        r = self.cliente.post(f"/contratos/{ids['contrato']}/confirmacion")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()['tipo'], 'rechazo_de_negocio')
        self.assertTrue(r.json()['pendientes'])                                          # lista de requisitos pendientes (CA-019)


class EnMemoria(FlujosDeNegocio, ValidacionDeEntrada, unittest.TestCase):
    def crear_contenedor(self, disponibilidad=None):
        return construir(disponibilidad)


class EnPostgreSQL(FlujosDeNegocio, ValidacionDeEntrada, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        ApiHttp.setUp(self)

    def crear_contenedor(self, disponibilidad=None):
        return construir_persistente(motor=self.motor, disponibilidad=disponibilidad)



if __name__ == '__main__':
    unittest.main()
