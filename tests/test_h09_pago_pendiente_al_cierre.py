"""H-09: pago registrado pero todavía sin verificar cuando una solicitud se cierra sin realizarse.

Reglas aprobadas:
- SE-012 y CA-097: si el Evento no está cancelado, Administración devuelve los importes efectivamente recibidos
  exclusivamente por la operación no realizada, una vez verificado el importe; los cobros pendientes quedan sin efecto.
- GL-046 / BN-009: los pagos se efectúan fuera del sistema y Administración los registra y verifica manualmente; la
  fecha en que el Cliente pagó se distingue de las de registro y verificación.
- BN-008, GL-055: con el Evento cancelado se aplica la política de no reembolso (sin devolución).

Corrección: un pago que el Cliente efectuó a más tardar al cierre y que estaba registrado sin verificar puede
verificarse después; al verificarse se registra su devolución si el Evento no estaba cancelado. La obligación sigue
Sin efecto. Con el Evento cancelado se conserva el rechazo anterior.

PENDIENTE (no se decide aquí): desde cuándo corren los cinco días hábiles de una devolución cuyo importe se verificó
después del cierre (la devolución conserva la fecha del cierre, como las demás), la consecuencia de devolver fuera de
plazo y el registro de un pago efectuado antes del cierre que Administración todavía no había registrado.
Ejecutar desde la raíz:  python -m unittest tests.test_h09_pago_pendiente_al_cierre -v"""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                       # noqa: E402
from apoyo_maquina_estados_estado_cuenta import Constructor, observar, M, CAMBIO_A_TIEMPO, CIERRE, CONSULTA   # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                                 # noqa: E402
from domain.valores import (CondicionesServicio, ConceptoPago as CP, Decision, DisponibilidadProveedor,  # noqa: E402
                            ErrorDominio, EstadoDevolucion as ED, EstadoObligacionPago as EO, EstadoPago as EPg,
                            EstadoSolicitudServicioAdicional as ESA, Importe, TipoSolicitud)

DIA = T0 + timedelta(days=2)
SIN_EFECTO = "La obligación quedó sin efecto."


def cambio_con_pago_sin_verificar(fecha_pago=CAMBIO_A_TIEMPO):
    c = Constructor().anticipo().saldo().cambio().pagar('OB-C', 300, fecha_pago, verificar=False)
    return c, c.ec.pagos[-1].pago_id


# ======================================================================= agregado EstadoCuenta
class VerificacionPosteriorAlCierre(unittest.TestCase):
    def test_con_el_evento_no_cancelado_se_verifica_y_se_registra_la_devolucion(self):   # SE-012, CA-097
        c, pid = cambio_con_pago_sin_verificar()
        self.assertEqual(c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv), [])   # nada verificado al cierre
        self.assertEqual(c.ec.obligaciones['OB-C'].estado, EO.SIN_EFECTO)
        c.ec.extraer_eventos()
        p = c.ec.verificar_pago_registrado(pid, CONSULTA)
        self.assertEqual((p.estado, p.verificado_en), (EPg.VERIFICADO, CONSULTA))
        self.assertEqual(c.ec.obligaciones['OB-C'].estado, EO.SIN_EFECTO)        # no se vuelve a cobrar
        d, = c.ec.devoluciones
        self.assertEqual((d.solicitud_id, d.concepto, d.importe, d.estado, d.fecha_cierre),
                         ('SC-1', CP.CAMBIO, M(300), ED.PENDIENTE, CIERRE))
        self.assertEqual([e.nombre for e in c.ec.extraer_eventos()], ['PagoVerificado'])   # sin Domain Events nuevos

    def test_con_el_evento_cancelado_se_conserva_el_rechazo(self):                       # BN-008, SE-012 (regresión)
        c, pid = cambio_con_pago_sin_verificar()
        c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, True, c.dv); c.ec.extraer_eventos()
        antes = observar(c.ec)
        self.assertRaisesRegex(ErrorDominio, SIN_EFECTO, c.ec.verificar_pago_registrado, pid, CONSULTA)
        self.assertEqual(observar(c.ec), antes)

    def test_un_pago_efectuado_despues_del_cierre_no_genera_devolucion(self):            # SE-012: recibido por la operación
        c, pid = cambio_con_pago_sin_verificar(CIERRE + timedelta(hours=1))
        c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv); c.ec.extraer_eventos()
        antes = observar(c.ec)
        self.assertRaisesRegex(ErrorDominio, SIN_EFECTO, c.ec.verificar_pago_registrado, pid, CONSULTA)
        self.assertEqual(observar(c.ec), antes)

    def test_el_pago_efectuado_en_el_instante_del_cierre_cuenta(self):
        c, pid = cambio_con_pago_sin_verificar(CIERRE)
        c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)
        c.ec.verificar_pago_registrado(pid, CONSULTA)
        self.assertEqual(len(c.ec.devoluciones), 1)

    def test_no_se_duplica_si_el_cierre_se_vuelve_a_aplicar(self):                       # idempotencia por origen
        c, pid = cambio_con_pago_sin_verificar()
        c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)
        c.ec.verificar_pago_registrado(pid, CONSULTA)
        self.assertEqual(c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv), [])
        self.assertEqual(len(c.ec.devoluciones), 1)

    def test_verificar_dos_veces_conserva_el_mensaje_existente(self):
        c, pid = cambio_con_pago_sin_verificar()
        c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)
        c.ec.verificar_pago_registrado(pid, CONSULTA)
        self.assertRaisesRegex(ErrorDominio, 'Solo se verifica un pago registrado', c.ec.verificar_pago_registrado, pid, CONSULTA)
        self.assertEqual(len(c.ec.devoluciones), 1)

    def test_un_pago_nuevo_sobre_la_obligacion_sin_efecto_sigue_rechazandose(self):      # pendiente de decisión
        c, _ = cambio_con_pago_sin_verificar()
        c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)
        self.assertRaisesRegex(ErrorDominio, 'La obligación no existe o quedó sin efecto.',
                               c.ec.registrar_y_verificar_pago, 'PG-N', 'OB-C', M(300), CAMBIO_A_TIEMPO, 'C', False)

    def test_un_pago_ya_verificado_al_cierre_se_devuelve_como_antes(self):               # regresión: SE-012
        c = Constructor().anticipo().saldo().cambio().pagar('OB-C', 300, CAMBIO_A_TIEMPO)
        nuevas = c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)
        self.assertEqual([(d.importe, d.fecha_cierre) for d in nuevas], [(M(300), CIERRE)])


# ======================================================================= flujo completo
class ServicioAdicionalCerradoPorInicio(unittest.TestCase):
    def _cerrado_con_pago_sin_verificar(self):
        disp = ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('c'))])
        e = Escenario(disp); e.confirmar_contratacion(); s = e.s.adicionales
        sa = s.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'Fotografía', DIA).datos['solicitud_id']
        s.evaluar_disponibilidad_servicio_adicional(sa, [], DIA)
        s.registrar_aprobacion_cliente_servicio_adicional(sa, Decision('Cliente', True, DIA))
        s.registrar_autorizacion_administracion_servicio_adicional(sa, Decision('Administración', True, DIA))
        s.registrar_anexo_servicio_adicional(sa, 'Anexo', DIA); e.d.despachar()
        oid = e.s.pagos.comunicar_solicitud_pago(TipoSolicitud.SERVICIO_ADICIONAL, sa, CP.SERVICIO_ADICIONAL,
                                                 Importe(D(500)), DIA).datos['obligacion_id']
        pid = e.s.pagos.registrar_y_verificar_pago(e.ec_id, oid, Importe(D(500)), DIA + timedelta(hours=2), 'C-SA',
                                                   verificar_ahora=False).datos['pago_id']
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.CERRADA_INICIO_EVENTO)
        self.assertEqual(e.ec().obligaciones[oid].estado, EO.SIN_EFECTO)
        self.assertEqual(e.ec().devoluciones, [])                                # todavía no verificado
        return e, sa, pid

    def test_al_verificarse_despues_se_registra_y_puede_ejecutarse_la_devolucion(self):   # CA-071, SE-012, CA-098
        e, sa, pid = self._cerrado_con_pago_sin_verificar()
        r = e.s.pagos.verificar_pago_registrado(e.ec_id, pid, FECHA_EVENTO + timedelta(days=1)); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertIn('SE-012', r.mensaje)
        d, = e.ec().devoluciones
        self.assertEqual((d.solicitud_id, d.importe, d.devolucion_id), (sa, Importe(D(500)), r.datos['devolucion_id']))
        r = e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, FECHA_EVENTO + timedelta(days=2)); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.ec().devoluciones[0].estado, ED.EFECTUADA)
        self.assertEqual(len(e.avisos('Devolución efectuada')), 1)


if __name__ == '__main__':
    unittest.main()
