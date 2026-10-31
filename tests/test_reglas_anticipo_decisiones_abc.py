"""Decisiones aprobadas A, B y C del cierre de alcance (Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md, sección 1).

A (A-1 a A-6, C-04, C-11)  contratación cerrada sin confirmar: devolución del anticipo recibido, sin reabrir la contratación.
B (B-1 a B-5, C-03)        el 30 % es el mínimo del anticipo: un excedente cubre el requisito, no se devuelve ni se aplica.
C (C-1 a C-4, C-12)        con el Evento cancelado no hay devolución automática (cancelación ≠ contratación cerrada).
Pruebas de referencia del cierre: T-46, T-48, T-55, T-57, T-64, T-66; T-15 y T-25 (clases de devolución).
Ejecutar desde la raíz:  python -m unittest tests.test_reglas_anticipo_decisiones_abc -v"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from test_reglas_corregidas import Escenario, T0                                                     # noqa: E402
from application.cqrs import ConsultarDevolucionesPendientesQuery                                    # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                                        # noqa: E402
from domain.valores import (ConceptoPago, EstadoContrato, EstadoDevolucion, EstadoEvento as EE,      # noqa: E402
                            EstadoObligacionPago as EO, EstadoPago as EPg, ErrorDominio, Importe, TipoDevolucion)

TRES_MIL = Importe(D('3000.00'))                 # 30 % de 10 000 (costo del escenario)
A = TipoDevolucion.ANTICIPO_CONTRATACION_CERRADA


def escenario():
    e = Escenario()
    e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
    return e


def pagar(e, importe, fecha, verificar=True, comprobante='C'):
    ob = e.obligacion('Anticipo')
    return e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D(str(importe))), fecha, comprobante,
                                                 registrado_en=fecha, verificar_ahora=verificar)


def cerrar_contratacion(e, pago_tardio=None):
    """Contacto al 6.º día y cierre cuando vencen las 24 horas sin pago a tiempo (CA-021). Devuelve el instante del cierre.
    Con `pago_tardio` el Cliente paga ese importe después de las 24 horas, antes del cierre (un pago así no lo impide)."""
    contacto = T0 + timedelta(days=6)
    e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
    if pago_tardio is not None:
        pagar(e, pago_tardio, contacto + timedelta(hours=30))
    cierre = contacto + timedelta(hours=31)
    r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, cierre, 'Sin pago', True)
    e.d.despachar()
    assert r.exito, r.mensaje
    return cierre


def contrato(e):
    return e.app.repos.contratos.obtener_por_id(e.contrato_id)


class B_ElAnticipoEsUnMinimo(unittest.TestCase):
    def test_un_pago_de_40_por_ciento_cubre_el_requisito_sin_devolucion_ni_aplicacion_al_saldo(self):      # T-55 (a), B-1..B-4
        e = escenario()
        r = pagar(e, 4000, T0 + timedelta(days=1)); e.d.despachar()
        self.assertEqual(r.datos['estado'], EPg.VERIFICADO.value)                 # no queda como importe incorrecto
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertEqual(contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)
        self.assertEqual(e.ec().devoluciones, [])                                  # B-3
        self.assertEqual(e.obligacion('SaldoContratoOriginal').importe.cantidad, D('7000'))   # B-4: OB-S sigue en 7000

    def test_se_distingue_lo_recibido_de_lo_aplicado(self):                       # B-2, B-4
        e = escenario(); pagar(e, 4000, T0 + timedelta(days=1)); e.d.despachar()
        ec = e.ec()
        self.assertEqual((ec.anticipo_recibido_verificado(), ec.anticipo_aplicado(), ec.anticipo_excedente()),
                         (D('4000'), D('3000'), D('1000')))

    def test_dos_transferencias_de_3000_la_segunda_se_registra_y_verifica_sin_devolucion(self):          # T-55 (b)
        e = escenario()
        pagar(e, 3000, T0 + timedelta(days=1), comprobante='TR-1'); e.d.despachar()
        r = pagar(e, 3000, T0 + timedelta(days=2), comprobante='TR-2'); e.d.despachar()
        self.assertEqual(r.datos['estado'], EPg.VERIFICADO.value)
        ec = e.ec()
        self.assertEqual([p.estado for p in ec.pagos], [EPg.VERIFICADO, EPg.VERIFICADO])
        self.assertEqual(ec.devoluciones, [])
        self.assertEqual(e.obligacion('SaldoContratoOriginal').importe.cantidad, D('7000'))
        self.assertEqual((ec.anticipo_aplicado(), ec.anticipo_excedente()), (D('3000'), D('3000')))

    def test_el_minimo_exacto_se_acepta_y_un_centavo_menos_es_un_pago_parcial(self):               # B-1, BN-009, CA-019, E-3
        e = escenario()
        r = pagar(e, '2999.99', T0 + timedelta(days=1)); e.d.despachar()
        self.assertEqual(r.datos['estado'], EPg.VERIFICADO.value)                    # E-3: parcial, ya no «importe incorrecto»
        self.assertEqual(e.obligacion('Anticipo').estado, EO.PENDIENTE)
        self.assertEqual(contrato(e).estado, EstadoContrato.FIRMADO)
        r = pagar(e, '0.01', T0 + timedelta(days=1, hours=1), comprobante='C-2'); e.d.despachar()   # el segundo pago completa el mínimo
        self.assertEqual(r.datos['estado'], EPg.VERIFICADO.value)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertEqual(contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)

    def test_la_precision_monetaria_se_conserva_en_el_excedente(self):
        e = escenario(); pagar(e, '3000.01', T0 + timedelta(days=1)); e.d.despachar()
        self.assertEqual(e.ec().anticipo_excedente(), D('0.01'))
        self.assertEqual(e.obligacion('SaldoContratoOriginal').importe.cantidad, D('7000'))


class A_ContratacionCerradaSinConfirmar(unittest.TestCase):
    def test_sin_pago_el_anticipo_queda_sin_efecto_y_no_hay_devolucion(self):          # C-04, A-2
        e = escenario(); cerrar_contratacion(e)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.SIN_EFECTO)
        self.assertEqual(e.ec().devoluciones, [])
        self.assertEqual(contrato(e).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)
        self.assertEqual(e.evento().estado, EE.CERRADO_SIN_CONTRATACION)               # nunca Cancelado

    def test_pago_parcial_recibido_antes_del_cierre_genera_una_devolucion(self):          # T-46; E-3: el pago menor ya no es «incorrecto»
        e = escenario()
        cierre = cerrar_contratacion(e, pago_tardio=1000)
        ec = e.ec()
        self.assertEqual(ec.pagos[0].estado, EPg.VERIFICADO)                          # parcial verificado; no cubre el anticipo
        self.assertEqual(e.obligacion('Anticipo').estado, EO.SIN_EFECTO)
        self.assertEqual([(d.tipo, d.importe.cantidad, d.estado, d.fecha_cierre) for d in ec.devoluciones],
                         [(A, D('1000'), EstadoDevolucion.PENDIENTE, cierre)])
        self.assertEqual(contrato(e).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)       # no se reabre

    def test_anticipo_liquidado_conserva_su_estado_y_tambien_se_devuelve(self):         # T-48, C-04
        e = escenario()
        contacto = T0 + timedelta(days=6)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
        pagar(e, 3000, contacto + timedelta(hours=30)); e.d.despachar()                  # después de las 24 h: no confirma
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=31), 'Sin pago', True)
        e.d.despachar()
        ec = e.ec()
        self.assertEqual(e.obligacion('Anticipo').estado, EO.LIQUIDADA)
        self.assertEqual([(d.tipo, d.importe.cantidad) for d in ec.devoluciones], [(A, D('3000'))])
        self.assertEqual(contrato(e).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)

    def test_pago_posterior_al_cierre_se_registra_y_verifica_sin_reactivar_nada(self):   # A-2, A-3, T-15
        e = escenario(); cierre = cerrar_contratacion(e)
        despues = cierre + timedelta(days=3)
        r = pagar(e, 3000, despues); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(r.datos['estado'], EPg.VERIFICADO.value)
        self.assertEqual(e.obligacion('Anticipo').estado, EO.SIN_EFECTO)                  # la obligación no se reactiva
        self.assertEqual(contrato(e).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)        # la contratación no se reabre
        self.assertEqual(e.evento().estado, EE.CERRADO_SIN_CONTRATACION)
        self.assertEqual(e.app.repos.estados_cuenta.obtener_por_id(e.ec_id).obligaciones.keys(), e.ec().obligaciones.keys())
        self.assertEqual([(d.tipo, d.importe.cantidad, d.fecha_referencia) for d in e.ec().devoluciones],
                         [(A, D('3000'), despues)])
        self.assertNotIn('SaldoContratoOriginal', {o.concepto.value for o in e.ec().obligaciones.values()})   # no se crea saldo

    def test_pago_registrado_antes_del_cierre_y_verificado_despues_T57(self):             # T-57
        e = escenario()
        contacto = T0 + timedelta(days=6)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False)
        pagar(e, 3000, contacto + timedelta(hours=30)); e.d.despachar()                   # PG-A, Liquidado
        pb = pagar(e, 3000, contacto + timedelta(hours=30, minutes=5), verificar=False, comprobante='TR-B').datos['pago_id']
        cierre = contacto + timedelta(hours=31)
        e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, cierre, 'Sin pago', True); e.d.despachar()
        self.assertEqual([d.importe.cantidad for d in e.ec().devoluciones], [D('3000')])      # solo PG-A: PG-B no está verificado
        r = e.s.pagos.verificar_pago_registrado(e.ec_id, pb, cierre + timedelta(days=1)); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        ec = e.ec()
        self.assertEqual([(d.tipo, d.importe.cantidad, d.pago_id) for d in ec.devoluciones][1:], [(A, D('3000'), pb)])
        self.assertEqual({d.tipo for d in ec.devoluciones}, {A})                          # ninguna devolución de otra clase
        # la verificación tardía no abre un plazo nuevo: la referencia sigue siendo el día del cierre (A-6, RN-43)
        self.assertEqual(ec.devoluciones[1].fecha_referencia, cierre)
        self.assertEqual(contrato(e).estado, EstadoContrato.CERRADO_SIN_CONFIRMAR)       # sin reactivar la contratación

    def test_un_pago_posterior_registrado_sin_verificar_se_devuelve_al_verificarse(self):           # A-3
        e = escenario(); cierre = cerrar_contratacion(e)
        registro = cierre + timedelta(days=2)
        pid = pagar(e, 3000, registro, verificar=False).datos['pago_id']
        self.assertEqual(e.ec().devoluciones, [])                                          # todavía no verificado
        e.s.pagos.verificar_pago_registrado(e.ec_id, pid, registro + timedelta(days=4)); e.d.despachar()
        (d,) = e.ec().devoluciones
        self.assertEqual((d.tipo, d.fecha_referencia), (A, registro))                      # el plazo cuenta desde el registro


class A_PlazoDeLaDevolucion(unittest.TestCase):
    """A-6 y C-15: cinco días hábiles posteriores al día de referencia (que no cuenta), límite exclusivo a las 00:00."""
    VIERNES_CIERRE = datetime(2026, 11, 20, 15, 30)       # ejemplo del cierre aprobado (datos comunes de la V4.1)

    def devolucion(self, cierre, registro):
        ec = EstadoCuenta('EC', 'CT', 'EV')
        o = ec.registrar_obligacion_anticipo('OB-A', Importe(D(10000)), cierre - timedelta(days=5))
        ec.registrar_y_verificar_pago('PG-1', o.obligacion_id, TRES_MIL, registro, 'C', False, registro)
        ec.aplicar_cierre_contratacion(cierre)
        ec.verificar_pago_registrado('PG-1', max(cierre, registro) + timedelta(days=9)) if ec.pagos[0].estado == EPg.REGISTRADO else None
        return ec.devoluciones[0]

    def test_pago_registrado_antes_del_cierre_referencia_el_dia_del_cierre(self):            # ejemplo 1 del cierre
        d = self.devolucion(self.VIERNES_CIERRE, self.VIERNES_CIERRE - timedelta(days=1))
        self.assertEqual(d.fecha_referencia, self.VIERNES_CIERRE)
        self.assertEqual(d.fecha_limite, datetime(2026, 11, 28, 0, 0))               # vence al final del viernes 27/11

    def test_pago_registrado_despues_del_cierre_referencia_el_dia_del_registro(self):        # ejemplo 2 del cierre
        registro = datetime(2026, 11, 23, 9, 0)                                       # lunes
        d = self.devolucion(self.VIERNES_CIERRE, registro)
        self.assertEqual(d.fecha_referencia, registro)
        self.assertEqual(d.fecha_limite, datetime(2026, 12, 1, 0, 0))                 # vence al final del lunes 30/11

    def test_el_limite_es_exclusivo_y_se_ignora_la_hora_del_cierre(self):
        d = self.devolucion(self.VIERNES_CIERRE, self.VIERNES_CIERRE - timedelta(days=1))
        self.assertFalse(d.vencida(datetime(2026, 11, 27, 23, 59, 59)))
        self.assertTrue(d.vencida(datetime(2026, 11, 28, 0, 0)))                      # 00:00 ya no está en plazo
        otra = self.devolucion(self.VIERNES_CIERRE.replace(hour=0, minute=1), self.VIERNES_CIERRE - timedelta(days=1))
        self.assertEqual(otra.fecha_limite, d.fecha_limite)

    def test_los_festivos_cuentan_como_habiles_y_el_fin_de_semana_no(self):                 # C-15, GL-060
        cierre = datetime(2026, 11, 16, 12, 0)                                        # lunes (festivo en México: cuenta como hábil)
        d = self.devolucion(cierre, cierre - timedelta(days=2))
        self.assertEqual(d.fecha_limite, datetime(2026, 11, 24, 0, 0))                # hábiles: 17, 18, 19, 20 y lunes 23 → límite el martes 00:00

    def test_en_plazo_distingue_el_momento_de_la_devolucion(self):
        d = self.devolucion(self.VIERNES_CIERRE, self.VIERNES_CIERRE - timedelta(days=1))
        ec = EstadoCuenta('EC', 'CT', 'EV')
        ec.devoluciones.append(d)
        ec.registrar_devolucion_efectuada(d.devolucion_id, datetime(2026, 11, 27, 23, 0), 'CMP')
        self.assertTrue(d.en_plazo)
        ec2 = EstadoCuenta('EC2', 'CT', 'EV')
        d2 = self.devolucion(self.VIERNES_CIERRE, self.VIERNES_CIERRE - timedelta(days=1))
        ec2.devoluciones.append(d2)
        ec2.registrar_devolucion_efectuada(d2.devolucion_id, datetime(2026, 11, 28, 0, 0), 'CMP')
        self.assertFalse(d2.en_plazo)


class A_IdempotenciaYTipos(unittest.TestCase):
    def test_reintentar_el_cierre_no_duplica_devoluciones(self):                               # C-11: una por pago
        e = escenario(); cierre = cerrar_contratacion(e, pago_tardio=1000)
        ec = e.ec()
        self.assertEqual(ec.aplicar_cierre_contratacion(cierre + timedelta(days=1)), [])
        self.assertEqual(len(ec.devoluciones), 1)
        e.s.pagos.aplicar_cierre_contratacion(e.contrato_id, cierre)                       # la reacción se vuelve a ejecutar
        self.assertEqual(len(e.ec().devoluciones), 1)
        self.assertEqual(e.ec().cierre_contratacion, cierre)                               # la primera fecha prevalece

    def test_verificar_dos_veces_el_mismo_pago_no_genera_otra_devolucion(self):
        e = escenario(); cierre = cerrar_contratacion(e)
        pid = pagar(e, 3000, cierre + timedelta(days=1), verificar=False).datos['pago_id']
        self.assertTrue(e.s.pagos.verificar_pago_registrado(e.ec_id, pid, cierre + timedelta(days=2)).exito)
        self.assertFalse(e.s.pagos.verificar_pago_registrado(e.ec_id, pid, cierre + timedelta(days=3)).exito)
        self.assertEqual(len(e.ec().devoluciones), 1)

    def test_ejecutar_la_devolucion_dos_veces_la_registra_una_sola_vez(self):
        e = escenario(); cierre = cerrar_contratacion(e); pagar(e, 3000, cierre + timedelta(days=1))
        (d,) = e.ec().devoluciones
        r1 = e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, cierre + timedelta(days=2))
        r2 = e.s.pagos.registrar_y_ejecutar_devolucion(e.ec_id, d.devolucion_id, cierre + timedelta(days=3))
        self.assertTrue(r1.exito and r2.exito)
        e.d.despachar()
        d = e.ec().devoluciones[0]
        self.assertEqual((d.estado, d.fecha_devolucion), (EstadoDevolucion.EFECTUADA, cierre + timedelta(days=2)))
        self.assertEqual(len([n for n in e.app.notificador.enviados if n[1] == 'Devolución efectuada']), 1)

    def test_la_devolucion_del_anticipo_y_la_de_se012_son_distintas(self):                    # A-5, T-25
        e = escenario(); cierre = cerrar_contratacion(e); pagar(e, 3000, cierre + timedelta(days=1))
        otra = EstadoCuenta('EC-X', 'CT-X', 'EV-X')
        o = otra.comunicar_solicitud_pago('OB-C', ConceptoPago.CAMBIO, Importe(D(300)), 'SC-1', T0)
        otra.registrar_y_verificar_pago('PG-C', o.obligacion_id, Importe(D(300)), T0, 'C', True)
        (se012,) = otra.aplicar_cierre_sin_realizar('SC-1', T0 + timedelta(hours=30), False, lambda: 'DV-SC')
        (a,) = e.ec().devoluciones
        self.assertEqual((se012.tipo, a.tipo), (TipoDevolucion.SOLICITUD_NO_REALIZADA, A))
        self.assertIsNone(a.solicitud_id)
        self.assertEqual(a.pago_id, e.ec().pagos[0].pago_id)
        self.assertIsNone(se012.pago_id)
        # SE-012 (decisión E-1) usa el mismo cálculo de GL-060: cierre vie 02/10 16:00 → quinto día hábil vie 09/10 → límite sáb 10/10 00:00
        self.assertEqual(se012.fecha_limite, datetime(2026, 10, 10, 0, 0))

    def test_la_consulta_de_pendientes_expone_el_tipo(self):
        e = escenario(); cierre = cerrar_contratacion(e); pagar(e, 3000, cierre + timedelta(days=1))
        vm = e.app.queries.devoluciones_pendientes.handle(ConsultarDevolucionesPendientesQuery(cierre + timedelta(days=1), e.evento_id))
        (f,) = vm.devoluciones
        self.assertEqual((f.tipo, f.solicitudId, f.pagoId, f.concepto), (A.value, None, e.ec().pagos[0].pago_id, 'Anticipo'))
        self.assertFalse(f.vencida)
        vencida = e.app.queries.devoluciones_pendientes.handle(ConsultarDevolucionesPendientesQuery(cierre + timedelta(days=30), e.evento_id))
        self.assertTrue(vencida.devoluciones[0].vencida)

    def test_un_pago_de_otro_concepto_con_la_obligacion_sin_efecto_sigue_rechazandose(self):      # H-09 / SE-012 (regresión)
        ec = EstadoCuenta('EC', 'CT', 'EV')
        o = ec.comunicar_solicitud_pago('OB-C', ConceptoPago.CAMBIO, Importe(D(300)), 'SC-1', T0)
        ec.aplicar_cierre_sin_realizar('SC-1', T0 + timedelta(days=3), False, lambda: 'DV-1')
        self.assertEqual(o.estado, EO.SIN_EFECTO)
        with self.assertRaises(ErrorDominio):
            ec.registrar_y_verificar_pago('PG-X', 'OB-C', Importe(D(300)), T0 + timedelta(days=4), 'C', False)


class C_NoHayReembolsoAlCancelarElEvento(unittest.TestCase):
    def cancelar_por_falta_de_regularizacion(self, e):
        from application.cqrs import RegistrarCancelacionPorFaltaDeRegularizacionCommand
        e.vencer_saldo_y_comunicar_moratorios()
        revision = e.comunicacion + timedelta(hours=25)
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, revision); e.d.despachar()
        r = e.app.commands.cancelar_por_falta_de_regularizacion.handle(RegistrarCancelacionPorFaltaDeRegularizacionCommand(
            e.evento_id, 'Saldo y moratorios no liquidados en 24 h', 'Coordinador', revision + timedelta(hours=2)))
        e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)

    def test_el_excedente_del_anticipo_no_se_devuelve_con_el_evento_cancelado(self):          # T-66, B-3, C-2, C-12
        e = escenario(); pagar(e, 4000, T0 + timedelta(days=1)); e.d.despachar()
        self.cancelar_por_falta_de_regularizacion(e)
        self.assertEqual(e.evento().estado, EE.CANCELADO)
        self.assertEqual(e.ec().devoluciones, [])
        self.assertIsNone(e.ec().cierre_contratacion)                                    # cancelación ≠ contratación cerrada (C-4)
        self.assertEqual(contrato(e).estado, EstadoContrato.CONTRATACION_CONFIRMADA)

    def test_un_pago_de_anticipo_posterior_a_la_cancelacion_no_genera_devolucion(self):        # T-64, C-2
        e = escenario(); pagar(e, 3000, T0 + timedelta(days=1)); e.d.despachar()
        self.cancelar_por_falta_de_regularizacion(e)
        r = pagar(e, 3000, T0 + timedelta(days=40), comprobante='C-2'); e.d.despachar()
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(e.ec().devoluciones, [])


class Persistencia(unittest.TestCase):
    """Los nuevos campos sobreviven a la ida y vuelta por los mapeadores (sin base de datos)."""
    def test_ida_y_vuelta_del_estado_de_cuenta_con_devolucion_del_anticipo(self):
        from infrastructure.persistencia.mapeadores import MapeadorEstadoCuenta
        e = escenario(); cierre = cerrar_contratacion(e); pagar(e, 3000, cierre + timedelta(days=1))
        m = MapeadorEstadoCuenta()
        ec = e.ec()
        copia = m.desde_filas(m.a_filas(ec))
        self.assertEqual(copia.cierre_contratacion, cierre)
        self.assertEqual(copia.devoluciones, ec.devoluciones)
        self.assertEqual(copia.devoluciones[0].tipo, A)


if __name__ == '__main__':
    unittest.main()
