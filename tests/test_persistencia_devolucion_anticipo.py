"""Decisión A en PostgreSQL (revisión 0003): la devolución del anticipo se guarda, se recupera y sus restricciones protegen los datos.

Complementa test_reglas_anticipo_decisiones_abc (reglas, en memoria) con la persistencia real: ida y vuelta, el mismo resultado
que en memoria, una devolución por pago (índice único parcial) y el CHECK de origen según el tipo."""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import sqlalchemy as sa                                                                   # noqa: E402
from apoyo_bd import BaseConBD                                                            # noqa: E402
from test_reglas_corregidas import CONTENIDO, FECHA_EVENTO, T0                           # noqa: E402
from domain.valores import (DatosEvento, EstadoContrato, EstadoDevolucion, EstadoEvento, EstadoObligacionPago as EO,   # noqa: E402
                            Importe, TipoDevolucion)
from infrastructure.composicion import construir                                         # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente   # noqa: E402
from infrastructure.persistencia.errores import ViolacionDeRestriccion                   # noqa: E402

A = TipoDevolucion.ANTICIPO_CONTRATACION_CERRADA


class Flujo:
    """Contratación hasta la firma, política comunicada, seguimiento y cierre sin confirmar; luego un pago posterior."""
    def __init__(self, app):
        self.app = app
        s, d = app.servicios, app.despachador
        self.s, self.d = s, d
        self.evento_id = s.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        pr = s.propuestas.crear_propuesta(self.evento_id, CONTENIDO, T0).datos['propuesta_id']
        p = app.repos.propuestas.obtener_por_id(pr)
        s.propuestas.aceptar_propuesta(pr, p.version_vigente_id, T0); d.despachar()
        self.contrato_id = s.contratacion.preparar_contrato(pr, True).datos['contrato_id']
        s.contratacion.registrar_comunicacion_politica_no_reembolso(self.contrato_id, T0)
        s.contratacion.registrar_firma_contrato(self.contrato_id, T0); d.despachar()
        self.ec_id = app.repos.estados_cuenta.obtener_por_contrato_id(self.contrato_id).id

    def ec(self):
        return self.app.repos.estados_cuenta.obtener_por_id(self.ec_id)

    def cerrar_y_recibir_un_pago_posterior(self):
        contacto = T0 + timedelta(days=6)
        self.s.contratacion.dar_seguimiento_anticipo_pendiente(self.contrato_id, contacto, 'Contacto', False)
        self.cierre = contacto + timedelta(hours=30)
        self.s.contratacion.dar_seguimiento_anticipo_pendiente(self.contrato_id, self.cierre, 'Sin pago', True); self.d.despachar()
        ob = next(o for o in self.ec().obligaciones.values() if o.concepto.value == 'Anticipo')
        self.registro = self.cierre + timedelta(days=3)
        self.s.pagos.registrar_y_verificar_pago(self.ec_id, ob.obligacion_id, Importe(D('3000')), self.registro, 'C', registrado_en=self.registro)
        self.d.despachar()
        return self


def resumen(f):
    ec = f.ec()
    return {'cierre': ec.cierre_contratacion, 'obligaciones': [(o.concepto.name, o.estado.name, o.importe.cantidad) for o in ec.obligaciones.values()],
            'pagos': [(p.estado.name, p.importe.cantidad) for p in ec.pagos],
            'devoluciones': [(d.tipo.name, d.solicitud_id, d.concepto.name, d.importe.cantidad, d.estado.name, d.fecha_cierre,
                              d.fecha_referencia, d.fecha_limite) for d in ec.devoluciones],
            'contrato': f.app.repos.contratos.obtener_por_id(f.contrato_id).estado.name,
            'evento': f.app.repos.eventos.obtener_por_id(f.evento_id).estado.name}


class DevolucionDelAnticipoEnPostgreSQL(BaseConBD):
    def test_el_mismo_flujo_da_el_mismo_resultado_en_memoria_y_en_postgresql(self):
        memoria = Flujo(construir()).cerrar_y_recibir_un_pago_posterior()
        persistente = Flujo(construir_persistente(motor=self.motor)).cerrar_y_recibir_un_pago_posterior()
        self.assertEqual(resumen(persistente), resumen(memoria))
        r = resumen(persistente)
        self.assertEqual((r['contrato'], r['evento']), (EstadoContrato.CERRADO_SIN_CONFIRMAR.name, EstadoEvento.CERRADO_SIN_CONTRATACION.name))
        (d,) = r['devoluciones']
        self.assertEqual((d[0], d[1], d[3], d[4]), (A.name, None, D('3000'), EstadoDevolucion.PENDIENTE.name))

    def test_la_devolucion_sobrevive_a_un_motor_nuevo(self):
        f = Flujo(construir_persistente(motor=self.motor)).cerrar_y_recibir_un_pago_posterior()
        otro = construir_persistente(motor=self.motor)
        ec = otro.repos.estados_cuenta.obtener_por_id(f.ec_id)
        self.assertEqual(ec.cierre_contratacion, f.cierre)
        self.assertEqual([(d.tipo, d.pago_id, d.fecha_referencia) for d in ec.devoluciones], [(A, ec.pagos[0].pago_id, f.registro)])
        self.assertEqual(next(o for o in ec.obligaciones.values() if o.concepto.value == 'Anticipo').estado, EO.SIN_EFECTO)

    def test_una_devolucion_por_pago_en_la_base_de_datos(self):                     # C-11
        f = Flujo(construir_persistente(motor=self.motor)).cerrar_y_recibir_un_pago_posterior()
        d = f.ec().devoluciones[0]
        with self.assertRaises(sa.exc.IntegrityError), self.motor.begin() as con:
            con.execute(sa.text(
                "insert into devolucion (estado_cuenta_id, devolucion_id, posicion, solicitud_id, concepto, importe, motivo_devolucion, "
                "fecha_cierre, estado, tipo, pago_id, fecha_referencia) values (:ec, 'DV-OTRA', 99, null, 'ANTICIPO', 1, 'x', :f, "
                "'PENDIENTE', 'ANTICIPO_CONTRATACION_CERRADA', :p, :f)"), {'ec': f.ec_id, 'f': f.cierre, 'p': d.pago_id})
        self.assertEqual(len(f.ec().devoluciones), 1)

    def test_el_origen_depende_del_tipo(self):
        f = Flujo(construir_persistente(motor=self.motor)).cerrar_y_recibir_un_pago_posterior()
        insertar = ("insert into devolucion (estado_cuenta_id, devolucion_id, posicion, solicitud_id, concepto, importe, motivo_devolucion, "
                    "fecha_cierre, estado, tipo, pago_id, fecha_referencia) values (:ec, :id, 98, :sol, :con, 1, 'x', :f, 'PENDIENTE', "
                    ":tipo, :pago, :ref)")
        base = {'ec': f.ec_id, 'f': f.cierre, 'con': 'ANTICIPO'}
        casos = {'SE-012 sin solicitud': dict(tipo='SOLICITUD_NO_REALIZADA', sol=None, pago=None, ref=None),
                 'anticipo sin pago': dict(tipo='ANTICIPO_CONTRATACION_CERRADA', sol=None, pago=None, ref=f.cierre),
                 'anticipo sin fecha de referencia': dict(tipo='ANTICIPO_CONTRATACION_CERRADA', sol=None, pago='PG-9', ref=None),
                 'tipo desconocido': dict(tipo='OTRA', sol='SC-1', pago=None, ref=None)}
        for nombre, c in casos.items():
            with self.subTest(nombre), self.assertRaises(sa.exc.IntegrityError), self.motor.begin() as con:
                con.execute(sa.text(insertar), {**base, 'id': 'DV-X', **c})
        with self.motor.begin() as con:                                             # la SE-012 válida (solicitud informada) sí entra
            con.execute(sa.text(insertar), {**base, 'id': 'DV-SE', 'tipo': 'SOLICITUD_NO_REALIZADA', 'sol': 'SC-1', 'pago': None, 'ref': None})
        self.assertEqual(len(f.ec().devoluciones), 2)

    def test_una_operacion_que_falla_no_deja_cierre_ni_devolucion(self):            # confirmación y reversión transaccional
        from application.servicios import transaccion
        f = Flujo(construir_persistente(motor=self.motor))
        ec = f.ec()
        with self.assertRaises(RuntimeError):
            with transaccion(f.app.uow, ec):
                ec.aplicar_cierre_contratacion(T0 + timedelta(days=7))
                f.app.repos.estados_cuenta.guardar(ec)
                raise RuntimeError('falla después de guardar')
        otro = f.ec()
        self.assertIsNone(otro.cierre_contratacion)
        self.assertEqual(next(o for o in otro.obligaciones.values() if o.concepto.value == 'Anticipo').estado, EO.PENDIENTE)
        self.assertEqual(f.app.outbox.registros('PENDIENTE'), [])


if __name__ == '__main__':
    unittest.main()
