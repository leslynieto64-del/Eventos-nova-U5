"""Unidad 5 — seguridad de negocio: una operación DENEGADA no produce cambios ni efectos secundarios.

La matriz de permisos y la autenticación ya están cubiertas por tests/test_seguridad.py (cada rol contra cada ruta, sesión, CSRF,
caducidad, aislamiento del proveedor). Lo que no se comprobaba de forma explícita es que, tras la denegación, el estado de negocio
quede intacto: sin pagos, sin revisión administrativa, sin cancelación, sin respuesta del proveedor, sin Domain Events en el Outbox y
sin avisos. Cada prueba confirma además que la MISMA operación, hecha por el rol autorizado, sí procede (la denegación se debe al
permiso, no a datos inválidos).

Autorización ≠ autenticación: 401 = no hay sesión válida; 403 = hay sesión pero el rol, el token CSRF o la propiedad del recurso no lo
permiten (docs/SEGURIDAD_Y_PERMISOS.md). Roles y permisos: application/seguridad.py (no se inventan permisos nuevos).
El reloj de negocio de la API y el de la seguridad se fijan para que el resultado no dependa de la fecha en que se ejecuta."""
import os
import sys
from datetime import timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi.testclient import TestClient                                                    # noqa: E402
from test_reglas_corregidas import Escenario, T0                                              # noqa: E402
from test_seguridad import CLAVE, Cliente                                                     # noqa: E402
from api.dependencias import obtener_reloj                                                    # noqa: E402
from api.main import crear_app                                                                # noqa: E402
from application.seguridad import ADMINISTRADOR, COORDINADOR, PROVEEDOR, ConfiguracionSeguridad   # noqa: E402
from domain.proveedor import Proveedor                                                        # noqa: E402
from domain.valores import EstadoEvento, EstadoServicioContratado, EstadoSolicitudCancelacion   # noqa: E402

AHORA = T0 + timedelta(days=3)          # antes de la fecha del evento (20/11/2026): la cancelación del Cliente procedería


@pytest.fixture
def sistema():
    """Evento En organización (flujo real en memoria) servido por la API con la autenticación ACTIVA."""
    e = Escenario()
    e.confirmar_contratacion()
    app = crear_app(lambda: e.app, ConfiguracionSeguridad(activa=True))
    app.dependency_overrides[obtener_reloj] = lambda: (lambda: AHORA)
    seguridad = e.app.servicios.seguridad
    seguridad.reloj = lambda: AHORA

    def entrar(rol, correo, proveedor_id=None) -> Cliente:
        seguridad.crear_usuario(correo, f'Persona {rol}', rol, CLAVE, proveedor_id)
        cliente = Cliente(app)
        cliente.entrar(correo)
        return cliente

    return SimpleNamespace(e=e, app=app, entrar=entrar)


def huella(e: Escenario) -> tuple:
    """Estado observable que una operación denegada no debe alterar."""
    ev, ec = e.evento(), e.ec()
    return (ev.estado, len(ev.solicitudes_cancelacion), ev.revision_administrativa, len(ec.pagos), len(ec.devoluciones),
            len(e.app.uow.outbox), len(e.app.notificador.enviados))


def test_un_coordinador_no_registra_pagos_y_la_denegacion_no_deja_efectos(sistema):            # pagos.registrar: solo Administración
    # Arrange
    e = sistema.e
    coordinador = sistema.entrar(COORDINADOR, 'coordinador@eventosnova.mx')
    administrador = sistema.entrar(ADMINISTRADOR, 'administracion@eventosnova.mx')
    saldo = e.obligacion('SaldoContratoOriginal')
    cuerpo = {'obligacion_id': saldo.obligacion_id, 'importe': '1000.00', 'fecha': (T0 + timedelta(days=5)).isoformat(),
              'comprobante': 'C-SEG-1', 'verificar_ahora': True}
    antes = huella(e)
    # Act
    denegada = coordinador.post(f'/estados-cuenta/{e.ec_id}/pagos', cuerpo)
    # Assert
    assert denegada.status_code == 403 and denegada.json()['tipo'] == 'sin_permiso'
    assert huella(e) == antes
    permitida = administrador.post(f'/estados-cuenta/{e.ec_id}/pagos', cuerpo)
    assert permitida.status_code == 201, permitida.text
    assert [p.comprobante for p in e.ec().pagos].count('C-SEG-1') == 1


def test_un_coordinador_no_registra_la_revision_administrativa_de_la_cancelacion(sistema):    # eventos.revision_administrativa
    # Arrange: Evento cancelado por el Cliente
    e = sistema.e
    assert e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', AHORA).exito
    e.d.despachar()
    coordinador = sistema.entrar(COORDINADOR, 'coordinador@eventosnova.mx')
    administrador = sistema.entrar(ADMINISTRADOR, 'administracion@eventosnova.mx')
    cuerpo = {'resultado': 'Sin reembolso (política de no reembolso)', 'fecha': (AHORA + timedelta(days=1)).isoformat()}
    antes = huella(e)
    # Act
    denegada = coordinador.post(f'/eventos/{e.evento_id}/revision-administrativa', cuerpo)
    # Assert
    assert denegada.status_code == 403
    assert huella(e) == antes
    assert e.evento().revision_administrativa is None
    assert e.avisos('Revisión de cancelación') == []
    permitida = administrador.post(f'/eventos/{e.evento_id}/revision-administrativa', cuerpo)
    assert permitida.status_code == 200, permitida.text
    assert e.evento().revision_administrativa.resultado == 'Sin reembolso (política de no reembolso)'


def test_sin_sesion_la_cancelacion_se_rechaza_con_401_y_el_evento_no_cambia(sistema):           # autenticación
    # Arrange
    e = sistema.e
    antes = huella(e)
    # Act
    r = TestClient(sistema.app).post(f'/eventos/{e.evento_id}/cancelacion', json={'motivo': 'Intento sin sesión'})
    # Assert
    assert r.status_code == 401 and r.json()['tipo'] == 'no_autenticado'
    assert huella(e) == antes
    assert e.evento().estado == EstadoEvento.EN_ORGANIZACION


def test_sin_token_csrf_la_cancelacion_se_deniega_y_con_el_token_procede(sistema):              # eventos.cancelar + CSRF
    # Arrange
    e = sistema.e
    coordinador = sistema.entrar(COORDINADOR, 'coordinador@eventosnova.mx')
    antes = huella(e)
    # Act
    denegada = coordinador.post(f'/eventos/{e.evento_id}/cancelacion', {'motivo': 'El Cliente desiste'}, csrf=False)
    # Assert
    assert denegada.status_code == 403 and denegada.json()['tipo'] == 'sin_permiso'
    assert huella(e) == antes
    permitida = coordinador.post(f'/eventos/{e.evento_id}/cancelacion', {'motivo': 'El Cliente desiste'})
    assert permitida.status_code == 200, permitida.text
    ev = e.evento()
    assert ev.estado == EstadoEvento.CANCELADO
    assert [s.estado for s in ev.solicitudes_cancelacion] == [EstadoSolicitudCancelacion.PROCEDENTE]


def test_un_proveedor_no_responde_por_el_servicio_asignado_a_otro_proveedor(sistema):           # proveedores.responder (recurso propio)
    # Arrange: el servicio queda asignado a PV-A y pendiente de su confirmación
    e = sistema.e
    for proveedor_id, nombre in (('PV-A', 'Proveedor A'), ('PV-B', 'Proveedor B')):
        assert e.app.repos.proveedores.guardar(Proveedor.registrar(proveedor_id, nombre, ['Banquete'], '', T0))
    servicio_id = next(iter(e.evento().servicios))
    assert e.s.proveedores.asignar_proveedor(e.evento_id, servicio_id, 'PV-A').exito
    proveedor_b = sistema.entrar(PROVEEDOR, 'proveedor-b@ejemplo.mx', proveedor_id='PV-B')
    proveedor_a = sistema.entrar(PROVEEDOR, 'proveedor-a@ejemplo.mx', proveedor_id='PV-A')
    url = f'/eventos/{e.evento_id}/servicios/{servicio_id}/respuesta-proveedor'
    antes = huella(e)
    # Act: PV-B intenta declarar «no disponible» en nombre de PV-A
    denegada = proveedor_b.post(url, {'proveedor_id': 'PV-A', 'disponible': False})
    # Assert
    assert denegada.status_code == 403 and 'su propio proveedor' in denegada.json()['detalle']
    assert huella(e) == antes
    servicio = e.evento().servicios[servicio_id]
    assert (servicio.proveedor_id, servicio.estado) == ('PV-A', EstadoServicioContratado.PENDIENTE_CONFIRMACION)
    assert e.avisos('Proveedor no disponible') == []
    permitida = proveedor_a.post(url, {'proveedor_id': 'PV-A', 'disponible': True})
    assert permitida.status_code == 200, permitida.text
    assert e.evento().servicios[servicio_id].estado == EstadoServicioContratado.CONFIRMADO
