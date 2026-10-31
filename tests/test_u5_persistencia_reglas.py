"""Unidad 5 — persistencia en PostgreSQL de las reglas seleccionadas: commit, rechazo sin escrituras y atomicidad ante un colaborador
externo que falla.

La infraestructura de persistencia ya tiene su propia batería (Unit of Work, Outbox, repositorios, restricciones, concurrencia). Aquí se
comprueba, sobre la base de PRUEBAS aislada y con la composición persistente real, lo que faltaba para las reglas de la Unidad 5:
  - la revisión administrativa con su constancia de no reembolso (C-12) se confirma y se recupera igual con un contenedor nuevo;
  - la cancelación rechazada exactamente en T (C-15, CA-088) queda registrada como «Rechazada por inicio del evento» y no deja ningún
    EventoCancelado en el Outbox;
  - un rechazo de negocio no escribe nada (ni el agregado ni el Outbox);
  - un timeout del verificador de pagos no deja filas de pago ni eventos.

Usan SIEMPRE TEST_DATABASE_URL (base local cuyo nombre termina en «_test»; tests/apoyo_bd.py). BaseConBD vacía SOLO esa base antes de
cada prueba. Sin PostgreSQL se omiten con un mensaje explícito, salvo con EVENTOSNOVA_REQUIERE_BD=1 (CI y Docker), donde FALLAN."""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import create_autospec

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sqlalchemy as sa                                                                     # noqa: E402
from apoyo_bd import BaseConBD                                                              # noqa: E402
from apoyo_flujo import Flujo, T0, FECHA_EVENTO                                             # noqa: E402
from application.puertos import IVerificadorPagos                                           # noqa: E402
from domain.evento import RevisionAdministrativa                                            # noqa: E402
from domain.valores import Importe                                                          # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente       # noqa: E402

CANCELACION = T0 + timedelta(days=3)
REVISION = T0 + timedelta(days=4)


class ReglasPersistidas(BaseConBD):
    def contratado(self) -> Flujo:
        """Contratación confirmada (Evento En organización) con la composición persistente sobre la base de pruebas."""
        return Flujo(construir_persistente(motor=self.motor)).contratar()

    def fila_evento(self, evento_id: str):
        with self.motor.connect() as con:
            return con.execute(sa.text('select estado, revision_resultado, revision_constancia_no_reembolso, revision_fecha '
                                       'from evento where evento_id = :id'), {'id': evento_id}).one()

    def contar_eventos_outbox(self, tipo: str) -> int:
        with self.motor.connect() as con:
            return con.execute(sa.text('select count(*) from outbox_evento where tipo_evento = :t'), {'t': tipo}).scalar()

    # ------------------------------------------------------------------------------------------------ commit
    def test_commit_la_constancia_de_no_reembolso_se_guarda_y_se_recupera_con_un_contenedor_nuevo(self):   # C-12, CA-091
        # Arrange
        f = self.contratado()
        self.assertTrue(f.s.cierre.gestionar_cancelacion_solicitada(f.evento_id, 'El Cliente desiste', CANCELACION).exito)
        f.d.despachar()
        # Act
        r = f.s.cierre.registrar_revision_administrativa_cancelacion(f.evento_id, 'Revisión de contrato y pagos', REVISION)
        # Assert
        self.assertTrue(r.exito, r.mensaje)
        otro = construir_persistente(motor=self.motor)                           # otra instancia: lee lo confirmado
        esperado = RevisionAdministrativa('Revisión de contrato y pagos', Importe(D('3000.00')), Importe(D('7000.00')), True, True,
                                          REVISION)
        self.assertEqual(otro.repos.eventos.obtener_por_id(f.evento_id).revision_administrativa, esperado)
        fila = self.fila_evento(f.evento_id)
        self.assertEqual((fila.estado, fila.revision_constancia_no_reembolso, fila.revision_fecha), ('CANCELADO', True, REVISION))
        self.assertEqual(self.contar_eventos_outbox('EventoCancelado'), 1)

    def test_limite_la_cancelacion_rechazada_en_T_se_registra_sin_evento_cancelado(self):                # C-15, CA-088
        # Arrange
        f = self.contratado()
        # Act
        r = f.s.cierre.gestionar_cancelacion_solicitada(f.evento_id, 'El Cliente desiste', FECHA_EVENTO)
        f.d.despachar()
        # Assert
        self.assertFalse(r.exito)
        with self.motor.connect() as con:
            solicitudes = con.execute(sa.text('select estado, fecha from evento_solicitud_cancelacion where evento_id = :id'),
                                      {'id': f.evento_id}).all()
        self.assertEqual([tuple(s) for s in solicitudes], [('RECHAZADA_INICIO_EVENTO', FECHA_EVENTO)])
        self.assertEqual(self.fila_evento(f.evento_id).estado, 'EN_ORGANIZACION')
        self.assertEqual(self.contar_eventos_outbox('EventoCancelado'), 0)

    # ------------------------------------------------------------------------------------------------ rechazo y rollback
    def test_rechazo_de_negocio_no_escribe_el_agregado_ni_el_outbox(self):                                 # CA-091
        # Arrange
        f = self.contratado()
        eventos_antes = self.contar('outbox_evento')
        # Act: revisión administrativa de un Evento que NO está cancelado
        r = f.s.cierre.registrar_revision_administrativa_cancelacion(f.evento_id, 'Revisión', REVISION)
        # Assert
        self.assertFalse(r.exito)
        fila = self.fila_evento(f.evento_id)
        self.assertEqual((fila.estado, fila.revision_resultado, fila.revision_constancia_no_reembolso, fila.revision_fecha),
                         ('EN_ORGANIZACION', None, None, None))
        self.assertEqual(self.contar('outbox_evento'), eventos_antes)

    def test_timeout_del_verificador_no_deja_filas_de_pago_ni_eventos(self):                                # atomicidad con un colaborador externo
        # Arrange
        f = self.contratado()
        verificador = create_autospec(IVerificadorPagos, instance=True)
        verificador.verificar.side_effect = TimeoutError('la verificación no respondió a tiempo')
        f.s.pagos.verificador = verificador
        saldo = f.obligacion('SaldoContratoOriginal')
        pagos_antes, eventos_antes = self.contar('pago'), self.contar('outbox_evento')
        # Act / Assert
        with self.assertRaises(TimeoutError):
            f.s.pagos.registrar_y_verificar_pago(f.ec_id, saldo.obligacion_id, Importe(D('1000.00')), T0 + timedelta(days=5), 'C-T')
        self.assertEqual(self.contar('pago'), pagos_antes)
        self.assertEqual(self.contar('outbox_evento'), eventos_antes)
        self.assertEqual(f.ec().obligaciones[saldo.obligacion_id].estado.name, 'PENDIENTE')


if __name__ == '__main__':
    unittest.main()
