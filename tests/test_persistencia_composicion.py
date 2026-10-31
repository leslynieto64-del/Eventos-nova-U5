"""Etapa 7 — composición persistente y persistencia tras reiniciar (PostgreSQL de pruebas).

Comprueba que `construir_persistente` ofrece la misma estructura que `construir`, que falla de forma clara si la base no responde o
el esquema está desactualizado, que un flujo de negocio completo da el mismo resultado en memoria y en PostgreSQL, y que los datos
sobreviven a un «reinicio» (contenedor nuevo, motor nuevo). Las pruebas de referencias sin FK se repiten sobre PostgreSQL."""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from apoyo_bd import BaseConBD                                                              # noqa: E402
from apoyo_flujo import Flujo, T0, FECHA_EVENTO, CONTENIDO                                  # noqa: E402
from test_persistencia_referencias import ReferenciasSinFK                                  # noqa: E402
from infrastructure.composicion import construir                                            # noqa: E402
from infrastructure.persistencia import configuracion as C                                  # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente       # noqa: E402
from infrastructure.persistencia.conexion import crear_motor                                # noqa: E402
from infrastructure.persistencia.errores import ErrorDeConexion, EsquemaDesactualizado       # noqa: E402
from domain.valores import DatosEvento, Importe                                             # noqa: E402


def resumen(f: Flujo):
    """Resultado observable de un flujo, independiente de los identificadores generados al azar."""
    ev, ec = f.evento(), f.ec()
    contrato = f.repos.contratos.obtener_por_id(f.contrato_id)
    return {
        'evento': (ev.estado.name, ev.datos.tipo, ev.datos.invitados_aproximados, sorted(s.servicio for s in ev.servicios.values())),
        'contrato': (contrato.estado.name, str(contrato.condiciones.costo_total.cantidad), contrato.politica.incluida),
        'obligaciones': sorted((o.concepto.name, o.estado.name, str(o.importe.cantidad)) for o in ec.obligaciones.values()),
        'pagos': sorted((p.estado.name, str(p.importe.cantidad)) for p in ec.pagos),
        'propuesta': f.repos.propuestas.obtener_por_id(f.propuesta_id).estado.name,
    }


class Estructura(BaseConBD):
    def test_ofrece_la_misma_estructura_que_la_composicion_en_memoria(self):
        memoria, persistente = construir(), construir_persistente(motor=self.motor)
        self.assertEqual(set(vars(memoria.repos)), set(vars(persistente.repos)))
        self.assertEqual(set(vars(memoria.servicios)), set(vars(persistente.servicios)))
        self.assertEqual(set(vars(memoria.queries)), set(vars(persistente.queries)))
        self.assertEqual(set(vars(memoria.commands)), set(vars(persistente.commands)))
        for atributo in ('uow', 'despachador', 'notificador'):
            self.assertTrue(hasattr(persistente, atributo), atributo)
        self.assertEqual(persistente.modo, 'postgresql')
        self.assertFalse(hasattr(memoria, 'modo'))

    def test_la_firma_publica_de_construir_no_cambia(self):
        import inspect
        self.assertEqual(str(inspect.signature(construir)), '(disponibilidad=None)')

    def test_la_composicion_en_memoria_sigue_funcionando_sin_base_de_datos(self):
        r = Flujo(construir()).contratar()
        self.assertEqual(r.evento().estado.name, 'EN_ORGANIZACION')

    def test_comprobar_base_de_datos_y_cerrar(self):
        c = construir_persistente(motor=self.motor)
        c.comprobar_base_de_datos()
        c.cerrar()                                   # no cierra un motor que no creó
        c.comprobar_base_de_datos()


class ArranqueSeguro(unittest.TestCase):
    def test_sin_url_falla_con_un_mensaje_claro(self):
        from infrastructure.persistencia.errores import ErrorDePersistencia
        with mock.patch.dict(os.environ, {'DATABASE_URL': ''}), mock.patch.object(C, 'cargar_env_local'):
            with self.assertRaises(ErrorDePersistencia) as ctx:
                construir_persistente()
        self.assertIn('DATABASE_URL', str(ctx.exception))

    def test_base_de_datos_inalcanzable(self):
        url = C.url_pruebas() or 'postgresql+psycopg://u:p@127.0.0.1:5432/x_test'
        inalcanzable = C.url_con_base(url, 'x_test').replace(':5432', ':1')           # puerto cerrado
        with self.assertRaises(ErrorDeConexion) as ctx:
            construir_persistente(url=inalcanzable, connect_args={'connect_timeout': 2})
        self.assertNotIn('p@', str(ctx.exception))                                      # la contraseña nunca aparece

    def test_esquema_desactualizado_o_sin_migrar(self):
        motor = None
        try:
            from apoyo_bd import motor_de_pruebas
            motor = motor_de_pruebas()
        except unittest.SkipTest as e:
            self.skipTest(str(e))
        with mock.patch('infrastructure.persistencia.preparacion.revision_actual', return_value=''):
            with self.assertRaises(EsquemaDesactualizado) as ctx:
                construir_persistente(motor=motor)
        self.assertIn('alembic upgrade head', str(ctx.exception))
        with mock.patch('infrastructure.persistencia.preparacion.revision_actual', return_value='0000'):
            with self.assertRaises(EsquemaDesactualizado):
                construir_persistente(motor=motor)
        construir_persistente(motor=motor)                                               # con el esquema al día arranca


class FlujoCompleto(BaseConBD):
    def test_el_mismo_flujo_da_el_mismo_resultado_en_memoria_y_en_postgresql(self):
        memoria = Flujo(construir()).contratar()
        persistente = Flujo(construir_persistente(motor=self.motor)).contratar()
        self.assertEqual(resumen(persistente), resumen(memoria))
        self.assertEqual(persistente.evento().estado.name, 'EN_ORGANIZACION')
        self.assertTrue(any(o[0] == 'ANTICIPO' and o[1] == 'LIQUIDADA' for o in resumen(persistente)['obligaciones']))

    def test_las_reacciones_del_outbox_se_ejecutan_y_quedan_registradas(self):
        memoria = Flujo(construir()).contratar()
        f = Flujo(construir_persistente(motor=self.motor)).contratar()
        registros = f.app.outbox.registros()
        tipos_sql = sorted(r.tipo_evento for r in registros)
        tipos_memoria = sorted(type(r.evento).__name__ for r in memoria.app.uow.outbox)
        self.assertEqual(tipos_sql, tipos_memoria)                                       # mismos hechos, mismos nombres
        self.assertEqual(tipos_sql, ['ContratacionConfirmada', 'ContratoFirmado', 'PagoVerificado', 'PropuestaAceptada'])
        self.assertEqual([r for r in registros if r.estado != 'Procesado'], [])          # todo se despachó
        self.assertTrue(all(r.evento is not None for r in registros))
        con_reacciones = {r.tipo_evento: len(r.reacciones_procesadas) for r in registros}
        self.assertEqual(con_reacciones['ContratacionConfirmada'], 2)                    # reacción de Evento y de EstadoCuenta
        self.assertEqual(f.app.outbox.registros('REVISION'), [])


class PersistenciaTrasReiniciar(BaseConBD):
    def test_los_datos_sobreviven_a_un_contenedor_y_un_motor_nuevos(self):
        url = C.url_pruebas()
        primero = construir_persistente(url=url)
        f = Flujo(primero).contratar()
        antes = resumen(f)
        evento_id, contrato_id = f.evento_id, f.contrato_id
        primero.cerrar()                                                                # «se detiene» la aplicación
        segundo = construir_persistente(url=url)                                         # motor y pool nuevos: «arranca» de nuevo
        try:
            g = Flujo(segundo)
            g.evento_id, g.propuesta_id, g.contrato_id, g.ec_id = evento_id, f.propuesta_id, contrato_id, f.ec_id
            self.assertEqual(resumen(g), antes)
            self.assertEqual(segundo.repos.eventos.obtener_por_id(evento_id).estado.name, 'EN_ORGANIZACION')
        finally:
            segundo.cerrar()

    def test_el_trabajo_pendiente_del_outbox_continua_tras_reiniciar(self):
        url = C.url_pruebas()
        primero = construir_persistente(url=url)
        s = primero.servicios
        evento_id = s.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        pr = s.propuestas.crear_propuesta(evento_id, CONTENIDO, T0).datos['propuesta_id']
        p = primero.repos.propuestas.obtener_por_id(pr)
        s.propuestas.aceptar_propuesta(pr, p.version_vigente_id, T0)                     # deja eventos pendientes SIN despachar
        pendientes = len(primero.outbox.registros('PENDIENTE'))
        self.assertGreater(pendientes, 0)
        primero.cerrar()
        segundo = construir_persistente(url=url)
        try:
            self.assertEqual(len(segundo.outbox.registros('PENDIENTE')), pendientes)      # siguen ahí
            self.assertEqual(segundo.despachador.despachar(), pendientes)
            self.assertEqual(segundo.outbox.registros('PENDIENTE'), [])
        finally:
            segundo.cerrar()


class ReferenciasSinFKEnPostgreSQL(ReferenciasSinFK, BaseConBD):
    """Las mismas pruebas de D-01 que en memoria, sobre PostgreSQL."""
    def setUp(self):
        BaseConBD.setUp(self)
        ReferenciasSinFK.setUp(self)

    def crear_contenedor(self):
        return construir_persistente(motor=self.motor)

    def contar_eventos_pendientes(self):
        return len(self.app.outbox.registros('PENDIENTE'))


if __name__ == '__main__':
    unittest.main()
