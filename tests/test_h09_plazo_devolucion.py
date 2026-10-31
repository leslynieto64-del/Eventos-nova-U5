"""H-09: la devolución se efectúa dentro de los cinco días hábiles siguientes al cierre de la solicitud.

Reglas: SE-012, GL-057 (devolución), GL-060 (días hábiles: lunes a viernes, sin calendario de festivos), CA-097, CA-098.
Decisión E-1 (GL-060, C-15): el límite de la devolución es exclusivo, a las 00:00 del día siguiente al quinto día hábil; el
día del cierre no cuenta. Antes de E-1 se conservaba la hora del cierre y el límite era inclusivo.
Decisiones pendientes (no inventadas): consecuencia de no devolver en plazo (la devolución tardía se registra y se marca
fuera de plazo, no se rechaza); inicio del plazo de una devolución cuyo importe se verifica después del cierre. El pago registrado pero no verificado al cierre
(SE-012, CA-097) se corrigió en test_h09_pago_pendiente_al_cierre: puede verificarse después y genera su devolución.
Ejecutar desde la raíz:  python -m unittest tests.test_h09_plazo_devolucion -v"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_e3g_cargo_tardio_y_conceptos import Base, importe                                         # noqa: E402
from application import cqrs as Q                                                                   # noqa: E402
from domain.estado_cuenta import DIAS_HABILES_DEVOLUCION, Devolucion                                # noqa: E402
from domain.valores import ConceptoPago as CP, EstadoDevolucion as ED                               # noqa: E402


def devolucion(cierre, **kw):
    return Devolucion('DEV-1', 'S-1', CP.CAMBIO, importe('300'), 'Cierre sin realizar', cierre, **kw)


class FechaLimite(unittest.TestCase):
    def test_son_cinco_dias_habiles(self):                                                  # SE-012
        self.assertEqual(DIAS_HABILES_DEVOLUCION, 5)

    def test_fecha_limite_segun_el_dia_de_cierre(self):                                     # GL-060
        # semana del 16 al 22 de noviembre de 2026 (lunes a domingo), cierre a las 10:30. El quinto día hábil posterior al cierre
        # es el lunes 23 para el cierre del lunes 16, etc.; el límite es la 00:00 del día siguiente a ese quinto día.
        esperado = {16: 24, 17: 25, 18: 26, 19: 27, 20: 28, 21: 28, 22: 28}   # sáb y dom cuentan desde el lunes siguiente
        for dia, limite in esperado.items():
            with self.subTest(cierre=dia):
                cierre = datetime(2026, 11, dia, 10, 30)
                self.assertEqual(devolucion(cierre).fecha_limite, datetime(2026, 11, limite, 0, 0))

    def test_el_limite_es_la_medianoche_posterior_a_un_dia_habil(self):                       # E-1
        for dia in range(1, 29):
            cierre = datetime(2026, 11, dia, 18, 45, 7)
            lim = devolucion(cierre).fecha_limite
            self.assertEqual(lim.time(), datetime.min.time())                                  # 00:00: la hora del cierre no se conserva
            self.assertLess((lim - timedelta(days=1)).weekday(), 5)                           # el último día del plazo es hábil
            self.assertGreaterEqual((lim.date() - cierre.date()).days, 6)

    def test_no_hay_calendario_de_festivos(self):                                           # GL-060
        # un viernes con lunes 16-nov intermedio: todos los lunes a viernes cuentan como hábiles
        self.assertEqual(devolucion(datetime(2026, 11, 13, 9, 0)).fecha_limite, datetime(2026, 11, 21, 0, 0))

    def test_cruce_de_fin_de_mes_y_de_anio(self):
        self.assertEqual(devolucion(datetime(2026, 12, 28, 8, 0)).fecha_limite, datetime(2027, 1, 5, 0, 0))


class VencimientoYCumplimiento(unittest.TestCase):
    CIERRE = datetime(2026, 11, 16, 10, 0)           # lunes -> quinto día hábil: lunes 23; límite exclusivo: martes 24 a las 00:00
    LIMITE = datetime(2026, 11, 24, 0, 0)

    def test_pendiente_vence_en_el_limite_exclusivo(self):                         # E-1
        d = devolucion(self.CIERRE)
        self.assertFalse(d.vencida(self.CIERRE))
        self.assertFalse(d.vencida(self.LIMITE - timedelta(seconds=1)))           # el último segundo del lunes 23 está en plazo
        self.assertTrue(d.vencida(self.LIMITE))                                   # a las 00:00 ya está vencida
        self.assertTrue(d.vencida(self.LIMITE + timedelta(seconds=1)))

    def test_en_plazo_es_none_mientras_no_se_efectua(self):
        self.assertIsNone(devolucion(self.CIERRE).en_plazo)

    def test_en_plazo_un_segundo_antes_del_limite_y_fuera_en_el_limite(self):        # E-1
        self.assertTrue(devolucion(self.CIERRE, fecha_devolucion=self.LIMITE - timedelta(seconds=1)).en_plazo)
        self.assertTrue(devolucion(self.CIERRE, fecha_devolucion=self.CIERRE).en_plazo)
        self.assertFalse(devolucion(self.CIERRE, fecha_devolucion=self.LIMITE).en_plazo)
        self.assertFalse(devolucion(self.CIERRE, fecha_devolucion=self.LIMITE + timedelta(seconds=1)).en_plazo)

    def test_efectuada_no_esta_vencida(self):
        d = devolucion(self.CIERRE, estado=ED.EFECTUADA, fecha_devolucion=self.LIMITE + timedelta(days=9))
        self.assertFalse(d.vencida(self.LIMITE + timedelta(days=30)))


class ConCierre(Base):
    """Cierre por falta de pago a +25 h de una solicitud hecha el sábado 14-nov: cae en domingo 15-nov 19:00."""

    def cerrar_con_un_pago(self):
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CAMBIO)                                  # solo se paga el costo del proveedor
        cierre = c.dia + timedelta(hours=25)
        self.assertTrue(c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, cierre).exito); c.e.d.despachar()
        return c, cierre


class CierreYDevolucion(ConCierre):
    """Integración: la devolución del cierre del domingo 15-nov 19:00 vence el sábado 21-nov a las 00:00 (E-1)."""

    def test_la_devolucion_nace_con_el_cierre_y_su_limite_esta_en_dia_habil(self):          # SE-012, CA-097
        c, cierre = self.cerrar_con_un_pago()
        self.assertEqual((cierre.weekday(), cierre.hour), (6, 19))                # domingo 15-nov 19:00
        (d,) = c.e.ec().devoluciones
        self.assertEqual((d.concepto, d.importe, d.estado, d.fecha_cierre), (CP.CAMBIO, importe('300'), ED.PENDIENTE, cierre))
        self.assertEqual(d.fecha_limite, datetime(2026, 11, 21, 0, 0))

    def test_devolucion_en_plazo(self):
        c, cierre = self.cerrar_con_un_pago()
        (d,) = c.e.ec().devoluciones
        r = c.e.s.pagos.registrar_y_ejecutar_devolucion(c.e.ec_id, d.devolucion_id, d.fecha_limite - timedelta(seconds=1))
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual((r.mensaje, r.datos['en_plazo'], r.datos['fecha_limite']),
                         ("Devolución efectuada.", True, '2026-11-21T00:00:00'))
        self.assertEqual(c.e.ec().devoluciones[0].estado, ED.EFECTUADA)

    def test_devolucion_tardia_se_registra_y_se_informa_fuera_de_plazo(self):
        c, cierre = self.cerrar_con_un_pago()
        (d,) = c.e.ec().devoluciones
        tarde = d.fecha_limite + timedelta(seconds=1)
        r = c.e.s.pagos.registrar_y_ejecutar_devolucion(c.e.ec_id, d.devolucion_id, tarde)
        self.assertTrue(r.exito)
        self.assertIn("fuera del plazo de cinco días hábiles", r.mensaje)
        self.assertIs(r.datos['en_plazo'], False)
        d = c.e.ec().devoluciones[0]
        self.assertEqual((d.estado, d.fecha_devolucion), (ED.EFECTUADA, tarde))   # la deuda se salda igualmente

    def test_devolucion_inexistente_se_rechaza(self):
        c, _ = self.cerrar_con_un_pago()
        r = c.e.s.pagos.registrar_y_ejecutar_devolucion(c.e.ec_id, 'DEV-no-existe', c.dia)
        self.assertEqual((r.exito, r.mensaje), (False, 'La devolución no existe.'))

    def test_con_todo_pagado_la_solicitud_se_confirma_y_no_hay_devolucion(self):            # SE-012
        c = self.armar(6, tarifa='150', costo='300')
        self.pagar(c, CP.CAMBIO); self.pagar(c, CP.CARGO_CAMBIO_TARDIO)
        self.assertTrue(c.e.s.cambios.confirmar_cambio(c.sid, c.dia + timedelta(hours=3)).exito)
        self.assertEqual(c.e.ec().devoluciones, [])

    def test_sin_pago_verificado_no_hay_devolucion(self):                                   # SE-012
        c = self.armar(6, tarifa='150', costo='300')
        self.assertTrue(c.e.s.cambios.cerrar_cambio_por_falta_de_pago(c.sid, c.dia + timedelta(hours=25)).exito)
        self.assertEqual(c.e.ec().devoluciones, [])


class ConsultasDeDevoluciones(ConCierre):
    def test_estado_de_pagos_muestra_la_fecha_limite(self):                                 # CA-098
        c, cierre = self.cerrar_con_un_pago()
        vm = c.e.app.queries.estado_pagos.handle(Q.ConsultarEstadoPagosQuery(c.e.evento_id))
        (fila,) = vm.estadosCuenta[0].devoluciones
        self.assertEqual((fila['solicitudId'], fila['concepto'], fila['importe'], fila['estado']),
                         (c.sid, CP.CAMBIO.value, '300', 'Pendiente'))
        self.assertEqual((fila['fechaCierre'], fila['fechaLimite'], fila['enPlazo'], fila['fechaDevolucion']),
                         (cierre.isoformat(), '2026-11-21T00:00:00', None, None))

    def test_estado_de_pagos_refleja_la_devolucion_efectuada(self):
        c, _ = self.cerrar_con_un_pago()
        (d,) = c.e.ec().devoluciones
        c.e.s.pagos.registrar_y_ejecutar_devolucion(c.e.ec_id, d.devolucion_id, d.fecha_limite + timedelta(days=1))
        vm = c.e.app.queries.estado_pagos.handle(Q.ConsultarEstadoPagosQuery(c.e.evento_id))
        fila = vm.estadosCuenta[0].devoluciones[0]
        self.assertEqual((fila['estado'], fila['enPlazo'], fila['comprobante'] is not None), ('Efectuada', False, True))

    def test_devoluciones_pendientes_marca_las_vencidas(self):
        c, _ = self.cerrar_con_un_pago()
        (d,) = c.e.ec().devoluciones
        h = c.e.app.queries.devoluciones_pendientes
        antes = h.handle(Q.ConsultarDevolucionesPendientesQuery(d.fecha_limite - timedelta(seconds=1)))
        despues = h.handle(Q.ConsultarDevolucionesPendientesQuery(d.fecha_limite))
        self.assertEqual([f.vencida for f in antes.devoluciones], [False])
        self.assertEqual([f.vencida for f in despues.devoluciones], [True])
        f = despues.devoluciones[0]
        self.assertEqual((f.eventoId, f.devolucionId, f.concepto, f.importe, f.fechaLimite),
                         (c.e.evento_id, d.devolucion_id, CP.CAMBIO.value, '300', '2026-11-21T00:00:00'))

    def test_devoluciones_pendientes_excluye_efectuadas_y_filtra_por_evento(self):
        c, _ = self.cerrar_con_un_pago()
        (d,) = c.e.ec().devoluciones
        h = c.e.app.queries.devoluciones_pendientes
        self.assertEqual(len(h.handle(Q.ConsultarDevolucionesPendientesQuery(c.dia)).devoluciones), 1)
        self.assertEqual(h.handle(Q.ConsultarDevolucionesPendientesQuery(c.dia, 'EV-otro')).devoluciones, [])
        self.assertEqual(len(h.handle(Q.ConsultarDevolucionesPendientesQuery(c.dia, c.e.evento_id)).devoluciones), 1)
        c.e.s.pagos.registrar_y_ejecutar_devolucion(c.e.ec_id, d.devolucion_id, d.fecha_limite)
        self.assertEqual(h.handle(Q.ConsultarDevolucionesPendientesQuery(c.dia)).devoluciones, [])

    def test_las_consultas_no_modifican_el_estado(self):
        c, _ = self.cerrar_con_un_pago()
        antes = [(d.estado, d.fecha_devolucion, d.comprobante) for d in c.e.ec().devoluciones]
        c.e.app.queries.devoluciones_pendientes.handle(Q.ConsultarDevolucionesPendientesQuery(c.dia + timedelta(days=99)))
        c.e.app.queries.estado_pagos.handle(Q.ConsultarEstadoPagosQuery(c.e.evento_id))
        self.assertEqual(antes, [(d.estado, d.fecha_devolucion, d.comprobante) for d in c.e.ec().devoluciones])


if __name__ == '__main__':
    unittest.main()
