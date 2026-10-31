"""TDD (Unidad 5) — ciclo RED → GREEN → REFACTOR: la constancia de no reembolso se registra UNA SOLA VEZ por cancelación.

Regla aprobada (no se inventa):
  - docs/BRD.md, BN-008: «La constancia de no reembolso se registra una sola vez por cancelación, con la relación de los pagos.»
  - Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md, C-12: «No reembolso al cancelarse el Evento, registrado una vez por
    cancelación con la relación de los pagos.»

Brecha observada en el código original (fase RED, preparada en la fase 1 de la Unidad 5):
  - domain/evento.py, Evento.registrar_revision_administrativa: solo exigía que el Evento estuviera Cancelado y que la revisión trajera
    la constancia; si ya había una revisión registrada, la SUSTITUÍA (`self.revision_administrativa = revision`).
  - application/servicios.py, GestionCierreEventoService.registrar_revision_administrativa_cancelacion: volvía a avisar al Coordinador
    en cada llamada.
  Un Evento solo se cancela una vez (Cancelado es un estado final, GL-033), así que «una vez por cancelación» = una vez por Evento.

Fase GREEN (implementación mínima): Evento.registrar_revision_administrativa lanza ErrorDominio si ya existe una revisión. El servicio
no cambia: su decorador convierte el ErrorDominio en un Resultado de rechazo y el aviso al Coordinador ya no se alcanza.
REFACTOR: no fue necesario modificar más código; el comportamiento queda protegido por estas dos pruebas.

Comportamiento esperado: un segundo registro se rechaza como regla de negocio (ErrorDominio en el agregado, Resultado de rechazo en el
servicio), la constancia original se conserva sin cambios y no hay un segundo aviso. Es el mismo criterio que el proyecto ya aplica a
otro resultado administrativo que se registra una sola vez: EstadoCuenta.resolver_regularizacion («El resultado de esta regularización
ya fue registrado», prueba test_correcciones_etapas_3_a_7.B1RegularizacionYAvisos.test_resultado_no_se_registra_dos_veces).

La evidencia RED se obtiene con el proyecto ORIGINAL (Eventosnova_actualizado.zip) más el archivo
tests_tdd/test_tdd_constancia_no_reembolso_unica.py de EventosNova_U5_fase1_cambios.zip; con este proyecto ambas pruebas deben pasar:
    python -m pytest tests/test_tdd_constancia_no_reembolso_unica.py -v
"""
import os
import sys
from datetime import timedelta
from decimal import Decimal as D

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                       # noqa: E402
from domain.evento import Evento, RevisionAdministrativa, ServicioContratado         # noqa: E402
from domain.valores import CondicionesServicio, DatosEvento, ErrorDominio, Importe   # noqa: E402


def test_tdd_el_agregado_no_sustituye_una_constancia_ya_registrada():
    # Arrange: Evento cancelado con su revisión administrativa ya registrada
    ev = Evento('EV-TDD', 'CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete'])
    ev.confirmar_contratacion([ServicioContratado('SC-1', 'Banquete', None, CondicionesServicio('Menú de tres tiempos'))])
    ev.solicitar_cancelacion('El Cliente desiste', FECHA_EVENTO - timedelta(days=10), True)
    primera = RevisionAdministrativa('Revisión de contrato y pagos', Importe(D('3000.00')), Importe(D('7000.00')), True, True,
                                     FECHA_EVENTO - timedelta(days=9))
    ev.registrar_revision_administrativa(primera)
    segunda = RevisionAdministrativa('Segunda revisión', Importe(D('3500.00')), Importe(D('6500.00')), True, True,
                                     FECHA_EVENTO - timedelta(days=8))
    # Act / Assert
    with pytest.raises(ErrorDominio):
        ev.registrar_revision_administrativa(segunda)
    assert ev.revision_administrativa == primera


def test_tdd_el_servicio_rechaza_un_segundo_registro_y_conserva_la_constancia_y_el_aviso_originales():
    # Arrange: Evento cancelado por el Cliente y revisión administrativa registrada
    e = Escenario()
    e.confirmar_contratacion()
    assert e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'El Cliente desiste', T0 + timedelta(days=3)).exito
    e.d.despachar()
    primera = e.s.cierre.registrar_revision_administrativa_cancelacion(e.evento_id, 'Revisión de contrato y pagos',
                                                                       T0 + timedelta(days=4))
    assert primera.exito, primera.mensaje
    constancia_original = e.evento().revision_administrativa
    # Act
    segunda = e.s.cierre.registrar_revision_administrativa_cancelacion(e.evento_id, 'Segunda revisión', T0 + timedelta(days=6))
    # Assert
    assert not segunda.exito
    assert e.evento().revision_administrativa == constancia_original
    assert e.evento().revision_administrativa.fecha == T0 + timedelta(days=4)
    assert len(e.avisos('Revisión de cancelación')) == 1
