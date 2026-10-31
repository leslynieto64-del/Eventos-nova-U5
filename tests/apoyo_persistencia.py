"""Apoyo de las pruebas de persistencia: escenarios del dominio con todos los campos opcionales informados y un comparador
estructural de agregados. Los agregados se construyen SOLO con métodos reales del dominio (sin inventar estados)."""
import os, sys
from datetime import datetime, timedelta
from decimal import Decimal as D
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from domain.base import AggregateRoot                                                        # noqa: E402
from domain.contrato import Contrato, EvidenciaAnticipo                                      # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                                # noqa: E402
from domain.evento import Evento, RevisionAdministrativa, ServicioContratado                 # noqa: E402
from domain.propuesta import Propuesta                                                       # noqa: E402
from domain.servicios_dominio import DecisionRegularizacion                                  # noqa: E402
from domain.solicitudes import (AlternativaPropuesta, SolicitudCambio, SolicitudServicioAdicional,   # noqa: E402
                                SustitucionProveedor)
from domain.valores import (AnticipacionSolicitud, CondicionesContractuales, CondicionesServicio, ConceptoPago,   # noqa: E402
                            ContenidoPropuesta, DatosEvento, Decision, DisponibilidadProveedor, EstadoSolicitudCambio,
                            ImpactoModificacion, Importe, PoliticaNoReembolso, ResultadoViabilidad, TarifaCargoTardio,
                            TipoSolicitud, sumar_dias_habiles)

T0 = datetime(2026, 10, 1, 10, 0)
FECHA_EVENTO = datetime(2026, 11, 20, 18, 0)
ANTIC = AnticipacionSolicitud(T0, FECHA_EVENTO)


def estado_de(obj):
    """Representación comparable de un agregado u objeto: atributos recursivos (incluido el estado privado) sin los eventos."""
    if isinstance(obj, AggregateRoot):
        return (type(obj).__name__, {k: estado_de(v) for k, v in sorted(vars(obj).items()) if k not in ('_eventos', '_version')})
    if isinstance(obj, Enum):
        return (type(obj).__name__, obj.name)
    if isinstance(obj, D):
        return ('Decimal', str(obj))                            # compara también la escala (125.50 ≠ 125.5)
    if hasattr(obj, '__dataclass_fields__'):
        return (type(obj).__name__, {k: estado_de(getattr(obj, k)) for k in obj.__dataclass_fields__})
    if isinstance(obj, dict):
        return ('dict', [(estado_de(k), estado_de(v)) for k, v in obj.items()])      # conserva el orden de inserción
    if isinstance(obj, (list, tuple)):
        return (type(obj).__name__, [estado_de(x) for x in obj])
    if isinstance(obj, (set, frozenset)):
        return ('set', sorted(estado_de(x) for x in obj))
    return obj


# ---------------------------------------------------------------- Propuesta
def propuestas():
    c1 = ContenidoPropuesta(('Banquete', 'Música'), ('PV-1', 'PV-2'), Importe(D('12345.60')), 'Condiciones 1')
    c2 = ContenidoPropuesta(('Banquete', 'Música', 'Foto'), ('PV-1',), Importe(D('15000')), 'Condiciones 2, pago a 30 días')
    aceptada = Propuesta('PR-1', 'EV-1', 'CL-1', c1, T0)
    aceptada.generar_nueva_version(c2, T0 + timedelta(days=1))
    aceptada.aceptar(aceptada.version_vigente_id, T0 + timedelta(days=2))
    cerrada = Propuesta('PR-2', 'EV-2', 'CL-2', c1, T0)
    cerrada.cerrar_por_no_aceptacion('El Cliente no respondió', T0 + timedelta(days=10))
    en_revision = Propuesta('PR-3', 'EV-3', 'CL-3', c1, T0)
    return [aceptada, cerrada, en_revision]


# ---------------------------------------------------------------- Contrato
def contratos():
    cond = CondicionesContractuales(('Banquete', 'Música'), Importe(D('12345.67')), 'Cond. contractuales 2026')
    confirmado = Contrato('CT-1', 'EV-1', 'PR-1', 'PR-1-v2', cond, PoliticaNoReembolso(True))
    confirmado.registrar_comunicacion_politica(T0)
    confirmado.firmar(T0)
    confirmado.registrar_seguimiento_anticipo(T0 + timedelta(days=4), 'Se contactó al Cliente', True)
    confirmado.registrar_seguimiento_anticipo(T0 + timedelta(days=5), 'Segundo aviso', True)
    confirmado.confirmar_contratacion(EvidenciaAnticipo(True, True, True), T0 + timedelta(days=6))
    confirmado.registrar_anexo('AX-1', TipoSolicitud.CAMBIO, 'SC-1', 'Cambio de hora', T0 + timedelta(days=7))
    confirmado.registrar_anexo('AX-2', TipoSolicitud.SERVICIO_ADICIONAL, 'SA-1', 'Servicio de foto', T0 + timedelta(days=8))
    confirmado.registrar_anexo('AX-3', TipoSolicitud.SUSTITUCION_PROVEEDOR, 'SP-1', 'Reemplazo', T0 + timedelta(days=9))
    cerrado = Contrato('CT-2', 'EV-2', 'PR-2', 'PR-2-v1', cond, PoliticaNoReembolso(True))
    cerrado.firmar(T0)
    cerrado.registrar_seguimiento_anticipo(T0 + timedelta(days=4), 'Contacto', True)
    cerrado.cerrar_sin_confirmar(T0 + timedelta(days=6))
    en_preparacion = Contrato('CT-3', 'EV-3', 'PR-3', 'PR-3-v1', cond, PoliticaNoReembolso(True))
    return [confirmado, cerrado, en_preparacion]


# ---------------------------------------------------------------- Evento
def eventos():
    datos = DatosEvento('Boda 2', FECHA_EVENTO, 'Salón 5, Av. Juárez #123', 150)
    s1 = ServicioContratado('CT-1-S1', 'Banquete', None, CondicionesServicio('Condiciones banquete'))
    s2 = ServicioContratado('CT-1-S2', 'Música', None, CondicionesServicio('Condiciones música'))
    activo = Evento('EV-1', 'CL-1', datos, ['Banquete', 'Música'])
    activo.confirmar_contratacion([s1, s2])
    activo.asignar_proveedor('CT-1-S1', 'PV-1')
    activo.registrar_respuesta_proveedor('CT-1-S1', 'PV-1', False)            # Proveedor no disponible
    activo.asignar_proveedor('CT-1-S2', 'PV-2')                               # Pendiente de confirmación
    activo.aplicar_cambio_confirmado('SC-1', DatosEvento('Boda 2', FECHA_EVENTO.replace(hour=20), 'Jardín', 160),
                                     {'CT-1-S2': CondicionesServicio('Música en vivo')}, T0)
    activo.incorporar_servicio_adicional('SA-1', ServicioContratado('SA-1-S', 'Foto', 'PV-9', CondicionesServicio('Foto 4 h')), T0)
    activo.reasignar_proveedor('SP-1', 'CT-1-S1', 'PV-3', T0)
    gestion = Evento('EV-2', 'CL-2', DatosEvento('XV años', FECHA_EVENTO, 'Jardín', 9223372036854775807), ['Música'])
    cerrado = Evento('EV-6', 'CL-6', DatosEvento('Graduación', FECHA_EVENTO, 'Aula', 40), ['Banquete'])
    cerrado.cerrar_sin_contratacion()
    ejecutado = Evento('EV-3', 'CL-3', datos, ['Banquete'])
    ejecutado.confirmar_contratacion([ServicioContratado('CT-3-S1', 'Banquete', 'PV-1', CondicionesServicio('x'))])
    ejecutado.iniciar(FECHA_EVENTO + timedelta(hours=1))
    ejecutado.solicitar_cancelacion('Tarde', FECHA_EVENTO + timedelta(hours=2), True)       # rechazada: ya inició
    ejecutado.finalizar(FECHA_EVENTO + timedelta(hours=6))
    cancelado = Evento('EV-4', 'CL-4', datos, ['Banquete'])
    cancelado.confirmar_contratacion([ServicioContratado('CT-4-S1', 'Banquete', None, CondicionesServicio('x'))])
    cancelado.solicitar_cancelacion('El Cliente canceló', T0, True)
    cancelado.registrar_revision_administrativa(RevisionAdministrativa(
        'Sin reembolso (política de no reembolso)', Importe(D('3000.50')), Importe(D('7000')), True, True, T0 + timedelta(days=1)))
    sin_regularizar = Evento('EV-5', 'CL-5', datos, ['Banquete'])
    sin_regularizar.confirmar_contratacion([ServicioContratado('CT-5-S1', 'Banquete', None, CondicionesServicio('x'))])
    sin_regularizar.cancelar_por_falta_de_regularizacion('Saldo vencido sin regularizar', 'Coordinador', T0, True)
    return [activo, gestion, cerrado, ejecutado, cancelado, sin_regularizar]


# ---------------------------------------------------------------- EstadoCuenta
def estados_cuenta():
    firma = T0
    ec = EstadoCuenta('EC-1', 'CT-1', 'EV-1')
    ec.registrar_obligacion_anticipo('OB-1', Importe(D('10000.00')), firma)
    ec.registrar_y_verificar_pago('PG-1', 'OB-1', Importe(D('3000.00')), firma + timedelta(days=1), 'C-1', True)
    ec.registrar_obligacion_saldo_original('OB-2', Importe(D('10000.00')), FECHA_EVENTO)
    ec.comunicar_solicitud_pago('OB-3', ConceptoPago.CAMBIO, Importe(D('150.25')), 'SC-1', T0)
    ec.registrar_y_verificar_pago('PG-2', 'OB-3', Importe(D('150.25')), T0 + timedelta(hours=2), 'C-2', True)
    ec.comunicar_solicitud_pago('OB-3B', ConceptoPago.CARGO_CAMBIO_TARDIO, Importe(D('99.9')), 'SC-1', T0)
    ec.registrar_importe_adicional_sustitucion('OB-4', Importe(D('100.00')), 'SP-1', True, FECHA_EVENTO)   # sin plazo (CA-052)
    ec.registrar_y_verificar_pago('PG-3', 'OB-2', Importe(D('1000.00')), FECHA_EVENTO + timedelta(days=10), 'C-3', False)   # Registrado, tardío
    ec.registrar_y_verificar_pago('PG-4', 'OB-1', Importe(D('1.00')), T0 + timedelta(days=3), 'C-4', False)     # Importe incorrecto
    ec.aplicar_cierre_sin_realizar('SC-1', T0 + timedelta(days=2), False, lambda: 'DV-1')                       # devolución
    ec.registrar_devolucion_efectuada('DV-1', T0 + timedelta(days=4), 'Transferencia 99')
    ec.registrar_vencimiento_saldo(sumar_dias_habiles(FECHA_EVENTO, 1))
    ec.activar_protocolo_cobro('OB-5', Importe(D('200.00')), FECHA_EVENTO + timedelta(days=2), 'Recordatorio amistoso')
    ec.resolver_regularizacion(FECHA_EVENTO + timedelta(days=4))
    simple = EstadoCuenta('EC-2', 'CT-2', 'EV-2')
    simple.registrar_obligacion_anticipo('OB-9', Importe(D('1234.56')), firma)
    con_plazo = EstadoCuenta('EC-3', 'CT-3', 'EV-3')
    con_plazo.aplicar_cierre_sin_realizar('SA-7', T0, True, lambda: 'DV-X')     # cierre con Evento cancelado
    return [ec, simple, con_plazo]


# ---------------------------------------------------------------- Solicitudes
def solicitudes_cambio():
    tarifa = TarifaCargoTardio(Importe(D('500.00')))
    completa = SolicitudCambio('SC-1', 'EV-1', 'CT-1', 'EC-1', 'Cambiar la hora y el lugar', ANTIC, tarifa,
                               DatosEvento('Boda 2', FECHA_EVENTO.replace(hour=20), 'Jardín', 160),
                               {'CT-1-S2': CondicionesServicio('Música en vivo'), 'CT-1-S1': CondicionesServicio('Menú nuevo')})
    completa.registrar_viabilidad(ResultadoViabilidad(True, 'Hay disponibilidad'), ImpactoModificacion(True, True, True), T0,
                                  Importe(D('1200.50')))
    completa.registrar_decision_cliente(Decision('Cliente', True, T0 + timedelta(hours=1), 'Conforme'))
    completa.registrar_autorizacion(Decision('Administración', True, T0 + timedelta(hours=2), ''))
    completa.asociar_anexo('AX-1')
    completa.registrar_solicitud_pago('OB-3')
    completa.confirmar(True, False, T0 + timedelta(hours=3))
    detenida = SolicitudCambio('SC-2', 'EV-1', 'CT-1', 'EC-1', 'Cambio detenido', ANTIC, tarifa)
    detenida.aplicar_decision_regularizacion(DecisionRegularizacion(False, True, 'Saldo vencido'), T0, EstadoSolicitudCambio.NO_PROCEDENTE)
    no_viable = SolicitudCambio('SC-3', 'EV-1', 'CT-1', 'EC-1', 'Imposible', ANTIC, tarifa)
    no_viable.registrar_viabilidad(ResultadoViabilidad(False, 'Sin disponibilidad'), ImpactoModificacion(False, False, True), T0)
    rechazada = SolicitudCambio('SC-4', 'EV-1', 'CT-1', 'EC-1', 'Rechazada por el Cliente', ANTIC, tarifa)
    rechazada.registrar_viabilidad(ResultadoViabilidad(True, ''), ImpactoModificacion(False, True, False), T0, Importe(D('10')))
    rechazada.registrar_decision_cliente(Decision('Cliente', False, T0, 'Muy caro'))
    simple = SolicitudCambio('SC-5', 'EV-1', 'CT-1', 'EC-1', 'Recién registrada', ANTIC, tarifa)
    return [completa, detenida, no_viable, rechazada, simple]


def solicitudes_servicio_adicional():
    completa = SolicitudServicioAdicional('SA-1', 'EV-1', 'CT-1', 'EC-1', 'Foto', ANTIC)
    completa.registrar_disponibilidad(DisponibilidadProveedor('PV-9', True, Importe(D('800.00')), CondicionesServicio('Foto 4 h')), T0)
    completa.registrar_decision_cliente(Decision('Cliente', True, T0, 'Ok'))
    completa.registrar_autorizacion(Decision('Administración', True, T0, 'Autorizada'))
    completa.asociar_anexo('AX-2')
    completa.registrar_solicitud_pago('OB-7')
    completa.confirmar(True, False, T0 + timedelta(hours=5))
    busqueda = SolicitudServicioAdicional('SA-2', 'EV-1', 'CT-1', 'EC-1', 'Baile', ANTIC)
    busqueda.registrar_disponibilidad(DisponibilidadProveedor('PV-0', False), T0)
    no_espera = SolicitudServicioAdicional('SA-3', 'EV-1', 'CT-1', 'EC-1', 'Luces', ANTIC)
    no_espera.registrar_disponibilidad(DisponibilidadProveedor('PV-0', False), T0)
    no_espera.registrar_respuesta_espera(False, T0)
    detenida = SolicitudServicioAdicional('SA-4', 'EV-1', 'CT-1', 'EC-1', 'Humo', ANTIC)
    detenida.aplicar_decision_regularizacion(DecisionRegularizacion(False, True, 'Saldo vencido'), T0, None)
    return [completa, busqueda, no_espera, detenida]


def sustituciones():
    s = SustitucionProveedor('SP-1', 'EV-1', 'CT-1-S1', 'PV-1', 'CT-1', 'EC-1', T0)
    alt1 = AlternativaPropuesta('PV-2', DisponibilidadProveedor('PV-2', True, Importe(D('100.00')), CondicionesServicio('c1')),
                                ImpactoModificacion(True, True, False))
    s.proponer_alternativa(alt1, Importe(D('100.00')), T0)
    s.registrar_decision_cliente(Decision('Cliente', False, T0, 'No me gusta'))            # vuelve a buscar
    alt2 = AlternativaPropuesta('PV-3', DisponibilidadProveedor('PV-3', True, Importe(D('250.75')), CondicionesServicio('c2')),
                                ImpactoModificacion(True, True, True))
    s.proponer_alternativa(alt2, Importe(D('250.75')), T0 + timedelta(days=1))
    s.registrar_decision_cliente(Decision('Cliente', True, T0 + timedelta(days=1), 'De acuerdo'))
    s.registrar_autorizacion(Decision('Administración', True, T0 + timedelta(days=2), ''), FECHA_EVENTO)
    s.asociar_anexo('AX-3')
    s.confirmar(True, False, T0 + timedelta(days=3))
    en_busqueda = SustitucionProveedor('SP-2', 'EV-1', 'CT-1-S2', 'PV-2', 'CT-1', 'EC-1', T0)
    cerrada = SustitucionProveedor('SP-3', 'EV-1', 'CT-1-S2', 'PV-2', 'CT-1', 'EC-1', T0)
    cerrada.cerrar_por_inicio_evento(FECHA_EVENTO)
    return [s, en_busqueda, cerrada]


def todos():
    """{nombre de clase: [agregados]} con los siete tipos de raíz."""
    return {'Propuesta': propuestas(), 'Contrato': contratos(), 'Evento': eventos(), 'EstadoCuenta': estados_cuenta(),
            'SolicitudCambio': solicitudes_cambio(), 'SolicitudServicioAdicional': solicitudes_servicio_adicional(),
            'SustitucionProveedor': sustituciones()}
