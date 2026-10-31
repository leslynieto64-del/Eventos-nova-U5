"""E3G (H-03): consultas de Administración y de servicios pendientes, y contenido real de las consultas y los
Command Handlers existentes.

Reglas: US-022 (CA-055 a CA-058), US-012 (CA-028), BN-007, GL-036; CQRS: las consultas solo leen.
La agrupación de CA-058 en «pendientes / autorizadas / rechazadas» no se implementa (las fuentes no clasifican «Pendiente
de pago», «No aprobada» ni los cierres): las solicitudes se devuelven con su estado original.
Ejecutar desde la raíz:  python -m unittest tests.test_h03_consultas_administracion -v"""
import os
import pickle
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                       # noqa: E402
from application import cqrs as Q                                                                     # noqa: E402
from domain.valores import (CondicionesServicio, ContenidoPropuesta, DatosEvento, Decision, DisponibilidadProveedor,   # noqa: E402
                            ErrorDominio, Importe, ResultadoViabilidad, TipoSolicitud, ConceptoPago as CP,
                            EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA,
                            limite_exclusivo_dias_habiles_antes)
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                                 # noqa: E402
from infrastructure.composicion import construir                                                      # noqa: E402

FECHA_B, FECHA_C, FECHA_D = datetime(2026, 12, 5, 12, 0), datetime(2026, 11, 25, 12, 0), datetime(2026, 11, 22, 12, 0)
OPCIONES = [DisponibilidadProveedor('PV-1', True, Importe(D(100)), CondicionesServicio('c')),
            DisponibilidadProveedor('PV-2', True, Importe(D(120)), CondicionesServicio('c')),
            DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))]


def importe(x):
    return Importe(D(x))


def nuevo_evento(app, fecha, cliente='CL-2', servicios=('Banquete',), costo=D(10000), confirmar=True):
    """Evento adicional en la misma aplicación: con la contratación confirmada, o solo registrado (En gestión)."""
    s, d = app.servicios, app.despachador
    ev = s.propuestas.registrar_evento(cliente, DatosEvento('Graduación', fecha, 'Jardín', 80), list(servicios)).datos['evento_id']
    if not confirmar:
        return SimpleNamespace(evento_id=ev)
    pr = s.propuestas.crear_propuesta(ev, ContenidoPropuesta(tuple(servicios), ('PV-1',), Importe(costo), 'Condiciones B'), T0).datos['propuesta_id']
    s.propuestas.aceptar_propuesta(pr, app.repos.propuestas.obtener_por_id(pr).version_vigente_id, T0); d.despachar()
    ct = s.contratacion.preparar_contrato(pr, True).datos['contrato_id']
    s.contratacion.registrar_firma_contrato(ct, T0); d.despachar()
    s.contratacion.registrar_comunicacion_politica_no_reembolso(ct, T0)
    ec = app.repos.estados_cuenta.obtener_por_contrato_id(ct)
    anticipo = next(o for o in ec.obligaciones.values() if o.concepto == CP.ANTICIPO)
    s.pagos.registrar_y_verificar_pago(ec.id, anticipo.obligacion_id, anticipo.importe, T0 + timedelta(days=1), 'C-ANT'); d.despachar()
    return SimpleNamespace(evento_id=ev, contrato_id=ct, ec_id=ec.id)


def primer_servicio(app, evento_id):
    return next(iter(app.repos.eventos.obtener_por_id(evento_id).servicios))


def mundo():
    """A (20/nov, con solicitudes y un proveedor asignado), B (5/dic, dos servicios y un cambio con costo y cargo
    tardío), C (25/nov, solo registrado), D (22/nov, cancelado)."""
    e = Escenario(ConsultaDisponibilidadSimulada(OPCIONES)); e.confirmar_contratacion()
    app, s = e.app, e.s
    m = SimpleNamespace(e=e, app=app, s=s, A=SimpleNamespace(evento_id=e.evento_id, contrato_id=e.contrato_id, ec_id=e.ec_id))
    m.sA = primer_servicio(app, e.evento_id)
    s.proveedores.asignar_proveedor(e.evento_id, m.sA, 'PV-1')
    m.B = nuevo_evento(app, FECHA_B, servicios=('Banquete', 'Música'))
    m.C = nuevo_evento(app, FECHA_C, confirmar=False)
    m.D = nuevo_evento(app, FECHA_D)
    s.cierre.gestionar_cancelacion_solicitada(m.D.evento_id, 'Desiste', T0 + timedelta(days=3)); e.d.despachar()
    return m


def cambio_con_costo_y_cargo(m):
    """En B, a 6 días: costo del proveedor 300 y cargo tardío 150 (tarifa vigente), con solicitud de pago comunicada."""
    dia = FECHA_B - timedelta(days=6)
    sid = m.s.cambios.registrar_solicitud_cambio(m.B.evento_id, m.B.contrato_id, 'Cambio de menú', importe('150'), dia).datos['solicitud_id']
    m.s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), importe('300'), dia)
    m.s.cambios.registrar_decision_cliente_cambio(sid, Decision('Cliente', True, dia))
    m.s.cambios.registrar_autorizacion_administracion_cambio(sid, Decision('Administración', True, dia))
    m.s.cambios.registrar_anexo_cambio(sid, 'Anexo', dia); m.e.d.despachar()
    r = m.s.pagos.comunicar_solicitud_pago_cambio(sid, dia)
    assert r.exito, r.mensaje
    return sid, dia


def solicitudes_en_A(m):
    """Cambios y servicios adicionales de A en distintos estados, y una sustitución en búsqueda."""
    e, s, dia = m.e, m.s, FECHA_EVENTO - timedelta(days=10)
    cond = {m.sA: CondicionesServicio('Menú ajustado')}
    ids = SimpleNamespace()
    for nombre in ('cambio_cliente', 'cambio_autorizacion'):
        sid = s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, nombre, importe('150'), dia,
                                                    condiciones_propuestas=cond).datos['solicitud_id']
        s.cambios.evaluar_viabilidad_cambio(sid, ResultadoViabilidad(True), None, dia)
        setattr(ids, nombre, sid)
    s.cambios.registrar_decision_cliente_cambio(ids.cambio_autorizacion, Decision('Cliente', True, dia))   # → pendiente de autorización
    adic = {}
    for nombre in ('a_cliente', 'a_autorizacion', 'autorizada', 'no_autorizada', 'confirmada'):
        sa = s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        adic[nombre] = sa
    for nombre in ('a_autorizacion', 'autorizada', 'no_autorizada', 'confirmada'):
        s.adicionales.registrar_aprobacion_cliente_servicio_adicional(adic[nombre], Decision('Cliente', True, dia))
    s.adicionales.registrar_autorizacion_administracion_servicio_adicional(adic['autorizada'], Decision('Administración', True, dia))
    s.adicionales.registrar_autorizacion_administracion_servicio_adicional(adic['no_autorizada'], Decision('Administración', False, dia, 'No'))
    s.adicionales.registrar_autorizacion_administracion_servicio_adicional(adic['confirmada'], Decision('Administración', True, dia))
    s.adicionales.registrar_anexo_servicio_adicional(adic['confirmada'], 'Anexo DJ', dia); e.d.despachar()
    costo = m.app.repos.adicionales.obtener_por_id(adic['confirmada']).importe_a_cobrar        # costo del proveedor (H-06)
    ob = s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, adic['confirmada'], CP.SERVICIO_ADICIONAL, costo, dia).datos['obligacion_id']
    s.pagos.registrar_y_verificar_pago(e.ec_id, ob, costo, dia + timedelta(hours=2), 'C-DJ')
    assert s.adicionales.confirmar_servicio_adicional(adic['confirmada'], dia + timedelta(hours=3)).exito
    ids.adic = adic
    ids.sustitucion = s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, m.sA, e.contrato_id, dia).datos['sustitucion_id']
    e.d.despachar()
    return ids


@contextmanager
def sin_escrituras(app):
    """Falla si una consulta usa el Unit of Work o guarda un agregado; al salir comprueba que los datos no cambiaron."""
    def prohibido(*a, **k):
        raise AssertionError('una consulta no debe escribir')
    antes = {n: pickle.dumps(r._alm.datos) for n, r in vars(app.repos).items()}
    outbox = len(app.uow.outbox)
    parches = [mock.patch.object(type(app.uow), n, side_effect=prohibido) for n in ('iniciar', 'registrar', 'confirmar', 'revertir')]
    parches += [mock.patch.object(type(r), 'guardar', side_effect=prohibido) for r in vars(app.repos).values()]
    for p in parches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(parches):
            p.stop()
    despues = {n: pickle.dumps(r._alm.datos) for n, r in vars(app.repos).items()}
    assert antes == despues, 'una consulta modificó datos'
    assert len(app.uow.outbox) == outbox, 'una consulta generó eventos'


# ======================================================================= información administrativa (CA-055 a CA-057)
class InformacionAdministrativaDelEvento(unittest.TestCase):
    def test_estado_costo_pagos_y_datos_del_evento(self):                                      # CA-055, CA-056, CA-057
        m = mundo()
        with sin_escrituras(m.app):
            vm = m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery(m.A.evento_id))
        self.assertEqual((vm.eventoId, vm.estadoEvento, vm.tipoEvento, vm.fechaHora, vm.lugar, vm.invitadosAproximados),
                         (m.A.evento_id, 'En organización', 'Boda', FECHA_EVENTO.isoformat(), 'Salón', 100))
        self.assertEqual([(c['contratoId'], c['estado'], D(c['costoTotal'])) for c in vm.contratos],
                         [(m.A.contrato_id, 'Contratación confirmada', D(10000))])
        self.assertEqual((D(vm.pagosRealizados), D(vm.saldoPendienteContratoOriginal)), (D(3000), D(7000)))
        resumen = vm.estadosCuenta[0]
        self.assertEqual((D(resumen.anticipo['importe']), resumen.anticipo['estado']), (D(3000), 'Liquidada'))
        self.assertEqual((D(resumen.saldoContratoOriginal['importe']), resumen.saldoContratoOriginal['estado'],
                          resumen.saldoContratoOriginal['fechaLimite']),
                         (D(7000), 'Pendiente', limite_exclusivo_dias_habiles_antes(FECHA_EVENTO, 3).isoformat()))
        (pendiente,) = vm.obligacionesPendientes
        self.assertEqual((pendiente['concepto'], D(pendiente['importe']), D(pendiente['pagado']), pendiente['estado']),
                         ('SaldoContratoOriginal', D(7000), D(0), 'Pendiente'))

    def test_proveedores_asignados_y_estado_de_cada_servicio(self):                            # CA-057
        m = mundo()
        vm = m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery(m.A.evento_id))
        self.assertEqual(vm.proveedores, [{'servicioContratadoId': m.sA, 'servicio': 'Banquete', 'proveedorId': 'PV-1',
                                           'estado': 'Pendiente de confirmación del proveedor'}])
        vm_b = m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery(m.B.evento_id))
        self.assertEqual({(p['servicio'], p['proveedorId'], p['estado']) for p in vm_b.proveedores},
                         {('Banquete', None, 'Sin proveedor asignado'), ('Música', None, 'Sin proveedor asignado')})

    def test_cambios_pendientes_de_autorizacion_y_adicionales_con_su_estado(self):             # CA-057, CA-058
        m = mundo(); ids = solicitudes_en_A(m)
        vm = m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery(m.A.evento_id))
        self.assertEqual([c['solicitudId'] for c in vm.cambiosPendientesAutorizacion], [ids.cambio_autorizacion])
        estados = {s['solicitudId']: (s['estado'], s['pendiente']) for s in vm.serviciosAdicionales}
        self.assertEqual(estados, {ids.adic['a_cliente']: (ESA.PENDIENTE_APROBACION_CLIENTE.value, True),
                                   ids.adic['a_autorizacion']: (ESA.PENDIENTE_AUTORIZACION.value, True),
                                   ids.adic['autorizada']: (ESA.AUTORIZADA.value, True),
                                   ids.adic['no_autorizada']: (ESA.NO_AUTORIZADA.value, False),
                                   ids.adic['confirmada']: (ESA.CONFIRMADA.value, False)})
        pendientes = {s.solicitudId for s in vm.solicitudesPendientes}
        self.assertEqual(pendientes, {ids.cambio_cliente, ids.cambio_autorizacion, ids.sustitucion,
                                      ids.adic['a_cliente'], ids.adic['a_autorizacion'], ids.adic['autorizada']})

    def test_importes_por_concepto_separados_y_pendientes(self):                               # CA-026, CA-057, BN-005
        m = mundo(); sid, dia = cambio_con_costo_y_cargo(m)
        vm = m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery(m.B.evento_id))
        adicionales = {a['concepto']: (D(a['importe']), a['estado']) for a in vm.estadosCuenta[0].obligacionesAdicionales}
        self.assertEqual(adicionales, {'Cambio': (D(300), 'Pendiente'), 'CargoCambioTardio': (D(150), 'Pendiente')})
        pendientes = {(o['concepto'], D(o['importe']), o['origenId']) for o in vm.obligacionesPendientes}
        self.assertEqual(pendientes, {('SaldoContratoOriginal', D(7000), m.B.contrato_id), ('Cambio', D(300), sid),
                                      ('CargoCambioTardio', D(150), sid)})

    def test_evento_en_gestion_no_tiene_contrato_ni_pagos(self):
        m = mundo()
        vm = m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery(m.C.evento_id))
        self.assertEqual((vm.estadoEvento, vm.contratos, vm.estadosCuenta, vm.proveedores, vm.obligacionesPendientes),
                         ('En gestión', [], [], [], []))
        self.assertEqual((D(vm.pagosRealizados), D(vm.saldoPendienteContratoOriginal)), (0, 0))

    def test_evento_cancelado_conserva_su_saldo_registrado(self):                              # BN-008
        m = mundo()
        vm = m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery(m.D.evento_id))
        self.assertEqual(vm.estadoEvento, 'Cancelado')
        self.assertEqual(D(vm.saldoPendienteContratoOriginal), D(7000))

    def test_evento_inexistente_devuelve_none(self):
        m = mundo()
        self.assertIsNone(m.app.queries.info_administrativa.handle(Q.ConsultarInformacionAdministrativaEventoQuery('EV-no-existe')))


# ======================================================================= eventos próximos (ventana por parámetros)
class EventosProximos(unittest.TestCase):
    def consultar(self, m, desde, hasta):
        return m.app.queries.eventos_proximos.handle(Q.ConsultarEventosProximosQuery(desde, hasta))

    def test_devuelve_los_eventos_de_la_ventana_ordenados_con_su_estado(self):                  # CA-058
        m = mundo()
        with sin_escrituras(m.app):
            vm = self.consultar(m, datetime(2026, 11, 18), datetime(2026, 11, 26))
        self.assertEqual([(e.eventoId, e.estadoEvento, e.fechaHora, e.clienteId) for e in vm.eventos],
                         [(m.A.evento_id, 'En organización', FECHA_EVENTO.isoformat(), 'CL-1'),
                          (m.D.evento_id, 'Cancelado', FECHA_D.isoformat(), 'CL-2'),
                          (m.C.evento_id, 'En gestión', FECHA_C.isoformat(), 'CL-2')])
        self.assertEqual((vm.desde, vm.hasta), (datetime(2026, 11, 18).isoformat(), datetime(2026, 11, 26).isoformat()))

    def test_los_limites_de_la_ventana_son_inclusivos(self):
        m = mundo()
        self.assertEqual([e.eventoId for e in self.consultar(m, FECHA_EVENTO, FECHA_EVENTO).eventos], [m.A.evento_id])
        self.assertEqual(self.consultar(m, FECHA_EVENTO + timedelta(seconds=1), FECHA_D - timedelta(seconds=1)).eventos, [])
        self.assertEqual([e.eventoId for e in self.consultar(m, FECHA_D, FECHA_D).eventos], [m.D.evento_id])

    def test_la_ventana_fuera_de_los_eventos_devuelve_una_lista_vacia(self):
        m = mundo()
        self.assertEqual(self.consultar(m, datetime(2030, 1, 1), datetime(2030, 12, 31)).eventos, [])
        self.assertEqual(self.consultar(m, datetime(2020, 1, 1), datetime(2020, 12, 31)).eventos, [])

    def test_una_ventana_invertida_se_rechaza(self):
        m = mundo()
        with self.assertRaises(ErrorDominio):
            self.consultar(m, FECHA_B, FECHA_EVENTO)

    def test_sin_eventos_devuelve_vacio_y_con_un_evento_lo_incluye(self):
        app = construir()
        ventana = Q.ConsultarEventosProximosQuery(datetime(2000, 1, 1), datetime(2100, 1, 1))
        self.assertEqual(app.queries.eventos_proximos.handle(ventana).eventos, [])
        e = Escenario()
        self.assertEqual([x.eventoId for x in e.app.queries.eventos_proximos.handle(ventana).eventos], [e.evento_id])


# ======================================================================= solicitudes por estado
class SolicitudesPorEstado(unittest.TestCase):
    def consultar(self, m, **filtros):
        return m.app.queries.solicitudes_por_estado.handle(Q.ConsultarSolicitudesPorEstadoQuery(**filtros)).solicitudes

    def test_sin_filtros_devuelve_los_tres_tipos_con_su_estado_original(self):                 # CA-058
        m = mundo(); ids = solicitudes_en_A(m)
        with sin_escrituras(m.app):
            filas = self.consultar(m)
        self.assertEqual(len(filas), 2 + 5 + 1)
        tipos = {}
        for f in filas:
            tipos.setdefault(f.tipoSolicitud, []).append(f.solicitudId)
        self.assertEqual({t: len(v) for t, v in tipos.items()}, {'cambio': 2, 'servicio adicional': 5, 'sustitución de proveedor': 1})
        por_id = {f.solicitudId: f for f in filas}
        self.assertEqual(por_id[ids.cambio_autorizacion].estadoActual, 'Pendiente de autorización')
        self.assertEqual(por_id[ids.sustitucion].estadoActual, 'En búsqueda de alternativa')
        self.assertEqual((por_id[ids.sustitucion].servicioAfectado, por_id[ids.cambio_cliente].servicioAfectado), (m.sA, None))
        self.assertEqual(por_id[ids.adic['confirmada']].pendiente, False)

    def test_filtra_por_estado_original(self):                                                  # CA-058
        m = mundo(); ids = solicitudes_en_A(m)
        casos = {'Pendiente de autorización': {ids.cambio_autorizacion, ids.adic['a_autorizacion']},
                 'Autorizada': {ids.adic['autorizada']}, 'No autorizada': {ids.adic['no_autorizada']},
                 'Confirmada': {ids.adic['confirmada']}, 'Pendiente de aprobación del Cliente': {ids.cambio_cliente, ids.adic['a_cliente']}}
        for estado, esperado in casos.items():
            with self.subTest(estado=estado):
                self.assertEqual({f.solicitudId for f in self.consultar(m, estado=estado)}, esperado)

    def test_estado_valido_sin_solicitudes_devuelve_lista_vacia(self):
        m = mundo(); solicitudes_en_A(m)
        self.assertEqual(self.consultar(m, estado='Cerrada por falta de pago'), [])

    def test_filtra_por_tipo_y_por_evento(self):
        m = mundo(); ids = solicitudes_en_A(m); sid, _ = cambio_con_costo_y_cargo(m)
        self.assertEqual({f.solicitudId for f in self.consultar(m, tipo='cambio')}, {ids.cambio_cliente, ids.cambio_autorizacion, sid})
        self.assertEqual({f.solicitudId for f in self.consultar(m, tipo='cambio', eventoId=m.B.evento_id)}, {sid})
        self.assertEqual({f.solicitudId for f in self.consultar(m, tipo='servicio adicional', eventoId=m.A.evento_id)}, set(ids.adic.values()))
        self.assertEqual(self.consultar(m, eventoId=m.C.evento_id), [])
        self.assertEqual(self.consultar(m, estado='Pendiente de pago', tipo='cambio')[0].solicitudId, sid)

    def test_estado_o_tipo_desconocidos_se_rechazan(self):
        m = mundo()
        for filtros in ({'estado': 'Inventado'}, {'tipo': 'otro'}):
            with self.subTest(filtros=filtros), self.assertRaises(ErrorDominio):
                self.consultar(m, **filtros)

    def test_sin_solicitudes_devuelve_vacio(self):
        m = mundo()
        self.assertEqual(self.consultar(m), [])


# ======================================================================= pagos pendientes
class PagosPendientes(unittest.TestCase):
    def consultar(self, m, evento_id=None):
        return m.app.queries.pagos_pendientes.handle(Q.ConsultarPagosPendientesQuery(evento_id)).pagos

    def test_pagos_pendientes_de_distintos_eventos_cada_concepto_por_separado(self):           # CA-058, CA-026
        m = mundo(); sid, dia = cambio_con_costo_y_cargo(m)
        with sin_escrituras(m.app):
            filas = self.consultar(m)
        self.assertEqual({(f.eventoId, f.concepto, D(f.importe), D(f.pagado), D(f.saldo), f.estado) for f in filas},
                         {(m.A.evento_id, 'SaldoContratoOriginal', D(7000), D(0), D(7000), 'Pendiente'),
                          (m.B.evento_id, 'SaldoContratoOriginal', D(7000), D(0), D(7000), 'Pendiente'),
                          (m.D.evento_id, 'SaldoContratoOriginal', D(7000), D(0), D(7000), 'Pendiente'),   # el adeudo sigue (BN-008)
                          (m.B.evento_id, 'Cambio', D(300), D(0), D(300), 'Pendiente'),
                          (m.B.evento_id, 'CargoCambioTardio', D(150), D(0), D(150), 'Pendiente')})
        self.assertNotIn(m.C.evento_id, {f.eventoId for f in filas})                           # sin contrato no hay estado de cuenta
        fechas = [f.fechaLimite for f in filas]
        self.assertEqual(fechas, sorted(fechas))
        cambio = next(f for f in filas if f.concepto == 'Cambio')
        self.assertEqual((cambio.origenId, cambio.fechaLimite), (sid, (dia + timedelta(hours=24)).isoformat()))

    def test_un_pago_parcial_reduce_el_saldo_y_uno_completo_retira_la_obligacion(self):         # BN-005
        m = mundo(); sid, dia = cambio_con_costo_y_cargo(m)
        saldo_b = next(f for f in self.consultar(m, m.B.evento_id) if f.concepto == 'SaldoContratoOriginal')
        m.s.pagos.registrar_y_verificar_pago(m.B.ec_id, saldo_b.obligacionId, importe('1000'), dia, 'C-1')
        filas = {f.concepto: f for f in self.consultar(m, m.B.evento_id)}
        self.assertEqual((D(filas['SaldoContratoOriginal'].pagado), D(filas['SaldoContratoOriginal'].saldo),
                          filas['SaldoContratoOriginal'].estado), (D(1000), D(6000), 'Pendiente'))
        m.s.pagos.registrar_y_verificar_pago(m.B.ec_id, filas['Cambio'].obligacionId, importe('300'), dia + timedelta(hours=1), 'C-2')
        self.assertEqual({f.concepto for f in self.consultar(m, m.B.evento_id)}, {'SaldoContratoOriginal', 'CargoCambioTardio'})

    def test_saldo_vencido_aparece_como_vencida(self):
        m = mundo()
        limite = limite_exclusivo_dias_habiles_antes(FECHA_EVENTO, 3)
        m.s.pagos.registrar_vencimiento_saldo_original(m.A.ec_id, limite + timedelta(hours=1)); m.e.d.despachar()
        fila = next(f for f in self.consultar(m, m.A.evento_id))
        self.assertEqual((fila.concepto, fila.estado, fila.fechaLimite), ('SaldoContratoOriginal', 'Vencida', limite.isoformat()))

    def test_una_obligacion_sin_efecto_o_liquidada_no_aparece(self):                            # SE-012
        m = mundo(); sid, dia = cambio_con_costo_y_cargo(m)
        m.s.cambios.cerrar_cambio_por_falta_de_pago(sid, dia + timedelta(hours=25)); m.e.d.despachar()
        self.assertEqual({f.concepto for f in self.consultar(m, m.B.evento_id)}, {'SaldoContratoOriginal'})

    def test_filtra_por_evento_y_los_inexistentes_o_sin_contrato_devuelven_vacio(self):
        m = mundo()
        self.assertEqual({f.eventoId for f in self.consultar(m, m.A.evento_id)}, {m.A.evento_id})
        self.assertEqual(self.consultar(m, m.C.evento_id), [])
        self.assertEqual(self.consultar(m, 'EV-no-existe'), [])


# ======================================================================= servicios pendientes de confirmación (US-012)
class ServiciosPendientes(unittest.TestCase):
    def consultar(self, m, evento_id=None):
        return m.app.queries.servicios_pendientes.handle(Q.ConsultarServiciosPendientesConfirmacionQuery(evento_id))

    def test_servicios_sin_confirmar_de_todos_los_eventos(self):                                # CA-028, GL-036
        m = mundo()
        with sin_escrituras(m.app):
            vm = self.consultar(m)
        filas = {(s.eventoId, s.servicio, s.proveedorId, s.estado, s.estadoEvento) for s in vm.servicios}
        self.assertEqual(filas, {(m.A.evento_id, 'Banquete', 'PV-1', 'Pendiente de confirmación del proveedor', 'En organización'),
                                 (m.B.evento_id, 'Banquete', None, 'Sin proveedor asignado', 'En organización'),
                                 (m.B.evento_id, 'Música', None, 'Sin proveedor asignado', 'En organización'),
                                 (m.D.evento_id, 'Banquete', None, 'Sin proveedor asignado', 'Cancelado')})

    def test_un_servicio_confirmado_deja_de_estar_pendiente(self):                              # CA-035
        m = mundo()
        m.s.proveedores.registrar_respuesta_proveedor(m.A.evento_id, m.sA, 'PV-1', True)
        self.assertEqual({s.eventoId for s in self.consultar(m, m.A.evento_id).servicios}, set())
        m.s.proveedores.asignar_proveedor(m.B.evento_id, primer_servicio(m.app, m.B.evento_id), 'PV-2')
        self.assertEqual({s.estado for s in self.consultar(m, m.B.evento_id).servicios},
                         {'Pendiente de confirmación del proveedor', 'Sin proveedor asignado'})

    def test_un_proveedor_que_no_esta_disponible_sigue_pendiente(self):                         # CA-036
        m = mundo()
        m.s.proveedores.registrar_respuesta_proveedor(m.A.evento_id, m.sA, 'PV-1', False)
        (s,) = self.consultar(m, m.A.evento_id).servicios
        self.assertEqual((s.proveedorId, s.estado), ('PV-1', 'Proveedor no disponible'))

    def test_incluye_las_solicitudes_en_tramite_de_los_tres_tipos(self):                        # GL-036
        m = mundo(); ids = solicitudes_en_A(m)
        vm = self.consultar(m, m.A.evento_id)
        self.assertEqual({(s.tipoSolicitud, s.solicitudId) for s in vm.solicitudes},
                         {('cambio', ids.cambio_cliente), ('cambio', ids.cambio_autorizacion),
                          ('sustitución de proveedor', ids.sustitucion), ('servicio adicional', ids.adic['a_cliente']),
                          ('servicio adicional', ids.adic['a_autorizacion']), ('servicio adicional', ids.adic['autorizada'])})
        self.assertTrue(all(s.pendiente for s in vm.solicitudes))

    def test_evento_inexistente_o_sin_servicios_devuelve_vacio(self):
        m = mundo()
        for evento in ('EV-no-existe', m.C.evento_id):
            vm = self.consultar(m, evento)
            self.assertEqual((vm.servicios, vm.solicitudes), ([], []))


# ======================================================================= contenido real de las consultas existentes
class EstadoDePagosExistente(unittest.TestCase):
    def test_contenido_de_anticipo_pagos_saldo_y_adicionales(self):                             # CA-022, CA-023, CA-026
        m = mundo(); sid, dia = cambio_con_costo_y_cargo(m)
        vm = m.app.queries.estado_pagos.handle(Q.ConsultarEstadoPagosQuery(m.B.evento_id))
        self.assertEqual(vm.eventoId, m.B.evento_id)
        (resumen,) = vm.estadosCuenta
        self.assertEqual((resumen.estadoCuentaId, resumen.contratoId), (m.B.ec_id, m.B.contrato_id))
        self.assertEqual((D(resumen.anticipo['importe']), resumen.anticipo['estado'],
                          resumen.anticipo['fechaLimite']),
                         (D(3000), 'Liquidada', T0.__class__(2026, 10, 7, 0, 0).isoformat()))      # 3 días hábiles tras la firma; límite exclusivo (E-1)
        (pago,) = resumen.pagosRegistrados
        self.assertEqual((pago['concepto'], D(pago['importe']), pago['estado'], pago['fecha'], pago['registradoEn'], pago['verificadoEn']),
                         ('Anticipo', D(3000), 'Verificado', (T0 + timedelta(days=1)).isoformat(),
                          (T0 + timedelta(days=1)).isoformat(), (T0 + timedelta(days=1)).isoformat()))
        self.assertEqual((D(resumen.saldoContratoOriginal['importe']), resumen.saldoContratoOriginal['estado'],
                          resumen.saldoContratoOriginal['fechaLimite']),
                         (D(7000), 'Pendiente', limite_exclusivo_dias_habiles_antes(FECHA_B, 3).isoformat()))
        self.assertEqual({(a['concepto'], D(a['importe']), a['estado'], a['plazo']) for a in resumen.obligacionesAdicionales},
                         {('Cambio', D(300), 'Pendiente', (dia + timedelta(hours=24)).isoformat()),
                          ('CargoCambioTardio', D(150), 'Pendiente', (dia + timedelta(hours=24)).isoformat())})

    def test_saldo_vencido_y_resultado_de_regularizacion(self):                                  # CA-023, CA-027
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        vm = e.app.queries.estado_pagos.handle(Q.ConsultarEstadoPagosQuery(e.evento_id))
        saldo = vm.estadosCuenta[0].saldoContratoOriginal
        self.assertEqual((saldo['estado'], D(saldo['importe'])), ('Vencida', D(7000)))
        self.assertNotIn('resultadoRegularizacion', saldo)
        self.assertEqual([a['concepto'] for a in vm.estadosCuenta[0].obligacionesAdicionales], ['CargosMoratorios'])
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, e.comunicacion + timedelta(hours=25))
        vm = e.app.queries.estado_pagos.handle(Q.ConsultarEstadoPagosQuery(e.evento_id))
        self.assertEqual(vm.estadosCuenta[0].saldoContratoOriginal['resultadoRegularizacion'], 'No regularizado')

    def test_evento_sin_estado_de_cuenta(self):
        m = mundo()
        vm = m.app.queries.estado_pagos.handle(Q.ConsultarEstadoPagosQuery(m.C.evento_id))
        self.assertEqual((vm.eventoId, vm.estadosCuenta), (m.C.evento_id, []))


class SolicitudesPendientesExistente(unittest.TestCase):
    def test_contenido_de_las_solicitudes_pendientes_de_los_tres_tipos(self):                    # CA-028, CA-058
        m = mundo(); ids = solicitudes_en_A(m)
        with sin_escrituras(m.app):
            vm = m.app.queries.pendientes.handle(Q.ConsultarSolicitudesPendientesQuery(m.A.evento_id))
        filas = {s.solicitudId: s for s in vm.solicitudes}
        self.assertEqual(set(filas), {ids.cambio_cliente, ids.cambio_autorizacion, ids.sustitucion, ids.adic['a_cliente'],
                                      ids.adic['a_autorizacion'], ids.adic['autorizada']})
        c = filas[ids.cambio_cliente]
        self.assertEqual((c.tipoSolicitud, c.servicioAfectado, c.estadoActual, c.accionPendiente, c.estadoPago, c.obligaciones),
                         ('cambio', None, 'Pendiente de aprobación del Cliente', 'aprobación', None, []))
        self.assertEqual(filas[ids.cambio_autorizacion].accionPendiente, 'autorización')
        a = filas[ids.adic['autorizada']]
        self.assertEqual((a.tipoSolicitud, a.servicioAfectado, a.estadoActual, a.accionPendiente), ('servicio adicional', 'DJ', 'Autorizada', 'formalización'))
        s = filas[ids.sustitucion]
        self.assertEqual((s.tipoSolicitud, s.servicioAfectado, s.estadoActual, s.accionPendiente),
                         ('sustitución de proveedor', m.sA, 'En búsqueda de alternativa', 'evaluación'))

    def test_una_solicitud_con_pago_muestra_el_estado_de_su_obligacion(self):                    # CA-067
        m = mundo(); sid, dia = cambio_con_costo_y_cargo(m)
        (f,) = m.app.queries.pendientes.handle(Q.ConsultarSolicitudesPendientesQuery(m.B.evento_id)).solicitudes
        self.assertEqual((f.estadoActual, f.accionPendiente, f.estadoPago), ('Pendiente de pago', 'pago pendiente', 'Pendiente'))
        self.assertEqual({(o['concepto'], D(o['importe']), o['estado']) for o in f.obligaciones},
                         {('Cambio', D(300), 'Pendiente'), ('CargoCambioTardio', D(150), 'Pendiente')})

    def test_las_solicitudes_finales_no_aparecen_y_otro_evento_no_se_mezcla(self):
        m = mundo(); ids = solicitudes_en_A(m)
        vm = m.app.queries.pendientes.handle(Q.ConsultarSolicitudesPendientesQuery(m.B.evento_id))
        self.assertEqual(vm.solicitudes, [])
        vm = m.app.queries.pendientes.handle(Q.ConsultarSolicitudesPendientesQuery(m.A.evento_id))
        self.assertNotIn(ids.adic['confirmada'], {s.solicitudId for s in vm.solicitudes})
        self.assertNotIn(ids.adic['no_autorizada'], {s.solicitudId for s in vm.solicitudes})


# ======================================================================= Command Handlers existentes
class CommandHandlers(unittest.TestCase):
    def test_generar_nueva_version_de_la_propuesta(self):                                        # CA-007, CA-009
        app = Escenario().app
        s = app.servicios
        ev = s.propuestas.registrar_evento('CL-9', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        pr = s.propuestas.crear_propuesta(ev, ContenidoPropuesta(('Banquete',), ('PV-1',), importe('10000'), 'v1'), T0).datos['propuesta_id']
        cmd = Q.GenerarNuevaVersionPropuestaCommand(pr, ContenidoPropuesta(('Banquete', 'Música'), ('PV-1',), importe('12000'), 'v2'))
        r = app.commands.nueva_version.handle(cmd, T0 + timedelta(days=1))
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual((r.datos['numero'], r.datos['version_id']), (2, f'{pr}-v2'))
        p = app.repos.propuestas.obtener_por_id(pr)
        self.assertEqual((p.version_vigente_id, [v.numero for v in p.versiones], p.versiones[1].fecha_actualizacion),
                         (f'{pr}-v2', [1, 2], T0 + timedelta(days=1)))
        self.assertEqual(p.versiones[1].contenido.servicios, ('Banquete', 'Música'))               # CA-008: contiene los cambios
        r3 = app.commands.nueva_version.handle(Q.GenerarNuevaVersionPropuestaCommand(pr, p.versiones[0].contenido), T0 + timedelta(days=2))
        self.assertEqual(r3.datos['numero'], 3)                                                    # números consecutivos (CA-009)

    def test_confirmar_cambio_mediante_el_command_handler(self):                                 # CA-041
        m = mundo(); sid, dia = cambio_con_costo_y_cargo(m)
        for concepto in ('Cambio', 'CargoCambioTardio'):
            ob = next(o for o in m.app.repos.estados_cuenta.obtener_por_id(m.B.ec_id).obligaciones_de(sid) if o.concepto.value == concepto)
            m.s.pagos.registrar_y_verificar_pago(m.B.ec_id, ob.obligacion_id, ob.importe, dia + timedelta(hours=2), f'C-{concepto}')
        r = m.app.commands.confirmar_cambio.handle(Q.ConfirmarCambioCommand(sid), dia + timedelta(hours=3))
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(m.app.repos.cambios.obtener_por_id(sid).estado, ESC.CONFIRMADA)
        r2 = m.app.commands.confirmar_cambio.handle(Q.ConfirmarCambioCommand(sid), dia + timedelta(hours=4))
        self.assertFalse(r2.exito)                                                                   # ya confirmado: no se repite

    def test_dar_seguimiento_al_anticipo_pendiente_mediante_el_command_handler(self):            # CA-020, CA-021
        e = Escenario()
        contacto = T0 + timedelta(days=6)
        cmd = Q.DarSeguimientoAnticipoPendienteCommand(e.contrato_id, contacto, 'Contacto con el Cliente', False)
        r = e.app.commands.seguimiento_anticipo.handle(cmd)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).seguimientos_anticipo, [(contacto, 'Contacto con el Cliente')])
        cierre = Q.DarSeguimientoAnticipoPendienteCommand(e.contrato_id, contacto + timedelta(hours=25), 'Sin pago', True)
        self.assertTrue(e.app.commands.seguimiento_anticipo.handle(cierre).exito)
        e.d.despachar()
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado.value, 'Cerrado sin confirmar')


# ======================================================================= lecturas de los repositorios y del estado de cuenta
class LecturasDeSoporte(unittest.TestCase):
    def test_los_listados_devuelven_copias_y_no_modifican_lo_guardado(self):                      # H-05 (contrato de lectura)
        m = mundo(); solicitudes_en_A(m)
        repos = m.app.repos
        for nombre, listar in (('eventos', repos.eventos.listar_todos), ('estados_cuenta', repos.estados_cuenta.listar_todos),
                               ('cambios', repos.cambios.listar_todas), ('adicionales', repos.adicionales.listar_todas),
                               ('sustituciones', repos.sustituciones.listar_todas)):
            with self.subTest(repositorio=nombre):
                antes = pickle.dumps(getattr(repos, nombre)._alm.datos)
                listado = listar()
                self.assertGreater(len(listado), 0)
                for agregado in listado:
                    agregado.id = 'alterado'                                                       # la copia no afecta al almacén
                self.assertEqual(pickle.dumps(getattr(repos, nombre)._alm.datos), antes)
                self.assertNotIn('alterado', {a.id for a in listar()})

    def test_los_listados_por_evento_filtran_cada_tipo_de_solicitud(self):
        m = mundo(); ids = solicitudes_en_A(m)
        repos = m.app.repos
        self.assertEqual({s.id for s in repos.cambios.listar_por_evento_id(m.A.evento_id)}, {ids.cambio_cliente, ids.cambio_autorizacion})
        self.assertEqual({s.id for s in repos.adicionales.listar_por_evento_id(m.A.evento_id)}, set(ids.adic.values()))
        self.assertEqual({s.id for s in repos.sustituciones.listar_por_evento_id(m.A.evento_id)}, {ids.sustitucion})
        for repo in (repos.cambios, repos.adicionales, repos.sustituciones):
            self.assertEqual(repo.listar_por_evento_id(m.B.evento_id), [])
        self.assertEqual(len(repos.eventos.listar_todos()), 4)

    def test_importe_pagado_suma_solo_pagos_verificados_de_la_obligacion(self):
        m = mundo()
        ec = m.app.repos.estados_cuenta.obtener_por_id(m.B.ec_id)
        saldo = next(o for o in ec.obligaciones.values() if o.concepto == CP.SALDO_CONTRATO_ORIGINAL)
        anticipo = next(o for o in ec.obligaciones.values() if o.concepto == CP.ANTICIPO)
        self.assertEqual((ec.importe_pagado(saldo.obligacion_id), ec.importe_pagado(anticipo.obligacion_id)), (D(0), D(3000)))
        m.s.pagos.registrar_y_verificar_pago(m.B.ec_id, saldo.obligacion_id, importe('1000'), T0 + timedelta(days=2), 'C-1')
        m.s.pagos.registrar_y_verificar_pago(m.B.ec_id, saldo.obligacion_id, importe('500'), T0 + timedelta(days=2), 'C-2',
                                             verificar_ahora=False)                                # registrado, no verificado
        ec = m.app.repos.estados_cuenta.obtener_por_id(m.B.ec_id)
        self.assertEqual(ec.importe_pagado(saldo.obligacion_id), D(1000))


if __name__ == '__main__':
    unittest.main()
