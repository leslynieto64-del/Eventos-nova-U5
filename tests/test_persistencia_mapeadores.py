"""Etapa 3 de la persistencia — mapeadores agregado ↔ filas SQL (sin base de datos).

Ida y vuelta de los siete agregados: identidad, estados, importes y precisión decimal, objetos de valor, entidades hijas y
orden de las colecciones, estado privado necesario para rehidratar, ausencia de eventos fantasma e invariantes."""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
import apoyo_persistencia as A                                                          # noqa: E402
from apoyo_persistencia import estado_de, T0, FECHA_EVENTO                              # noqa: E402
from infrastructure.esquema_postgresql import metadata                                  # noqa: E402
from infrastructure.persistencia.mapeadores import MAPEADORES, mapeador_de, Filas       # noqa: E402
from domain.base import AggregateRoot                                                   # noqa: E402
from domain.contrato import Contrato                                                    # noqa: E402
from domain.estado_cuenta import EstadoCuenta                                           # noqa: E402
from domain.evento import Evento                                                        # noqa: E402
from domain.propuesta import Propuesta                                                  # noqa: E402
from domain.servicios_dominio import DecisionRegularizacion                             # noqa: E402
from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor   # noqa: E402
from domain.valores import (ContenidoPropuesta, DatosEvento, ErrorDominio, EstadoEvento, EstadoSolicitudCambio,   # noqa: E402
                            Importe, TipoSolicitud, EstadoObligacionPago)

TODOS = A.todos()


def _ida_y_vuelta(ag):
    m = mapeador_de(ag)
    return m, m.a_filas(ag), m.desde_filas(m.a_filas(ag))


class SieteAgregados(unittest.TestCase):
    def test_los_siete_agregados_tienen_mapeador_y_escenarios(self):
        nombres = {c.__name__ for c in MAPEADORES}
        self.assertEqual(nombres, {'Propuesta', 'Contrato', 'Evento', 'SolicitudCambio', 'SolicitudServicioAdicional',
                                   'SustitucionProveedor', 'EstadoCuenta'})
        self.assertEqual(set(TODOS), nombres)
        for nombre, lista in TODOS.items():
            self.assertTrue(lista, nombre)

    def test_cada_tabla_del_esquema_esta_cubierta_por_un_mapeador_salvo_el_outbox(self):
        tablas = set()
        for m in MAPEADORES.values():
            tablas.add(m.tabla_raiz)
            tablas |= {h[0] for h in m.hijas}
        self.assertEqual(set(metadata.tables) - tablas, {'outbox_evento', 'outbox_reaccion', 'proveedor', 'usuario', 'sesion', 'intento_acceso'})   # catálogo y seguridad no son agregados: repositorio propio


class IdaYVuelta(unittest.TestCase):
    def test_el_agregado_reconstruido_es_igual_al_original(self):
        for nombre, lista in TODOS.items():
            for ag in lista:
                with self.subTest(f'{nombre} {ag.id}'):
                    _, _, nuevo = _ida_y_vuelta(ag)
                    self.assertIs(type(nuevo), type(ag))
                    self.assertEqual(nuevo.id, ag.id)
                    self.assertEqual(estado_de(nuevo), estado_de(ag))

    def test_no_falta_ni_sobra_ningun_atributo(self):
        for nombre, lista in TODOS.items():
            for ag in lista:
                with self.subTest(f'{nombre} {ag.id}'):
                    _, _, nuevo = _ida_y_vuelta(ag)
                    self.assertEqual(set(vars(nuevo)), set(vars(ag)))

    def test_las_filas_tienen_exactamente_las_columnas_de_cada_tabla(self):
        for nombre, lista in TODOS.items():
            for ag in lista:
                m = mapeador_de(ag)
                f = m.a_filas(ag)
                with self.subTest(f'{nombre} {ag.id} raíz'):
                    self.assertEqual(set(f.raiz), set(metadata.tables[m.tabla_raiz].columns.keys()) - {'version'})   # la versión la gestiona el repositorio
                self.assertEqual(set(f.hijas), {h[0] for h in m.hijas})
                for tabla, filas in f.hijas.items():
                    for fila in filas:
                        with self.subTest(f'{nombre} {ag.id} {tabla}'):
                            self.assertEqual(set(fila), set(metadata.tables[tabla].columns.keys()))

    def test_a_filas_no_modifica_ni_consume_los_eventos_del_agregado(self):
        s = A.solicitudes_cambio()[0]
        antes = list(s._eventos)
        self.assertTrue(antes)
        mapeador_de(s).a_filas(s)
        self.assertEqual(s._eventos, antes)

    def test_dos_idas_y_vueltas_producen_las_mismas_filas(self):
        for nombre, lista in TODOS.items():
            for ag in lista:
                with self.subTest(f'{nombre} {ag.id}'):
                    m, f1, nuevo = _ida_y_vuelta(ag)
                    f2 = m.a_filas(nuevo)
                    self.assertEqual(f1.raiz, f2.raiz)
                    self.assertEqual(f1.hijas, f2.hijas)


class SinEventosFantasma(unittest.TestCase):
    def test_rehidratar_no_emite_ningun_domain_event(self):
        for nombre, lista in TODOS.items():
            for ag in lista:
                with self.subTest(f'{nombre} {ag.id}'):
                    _, _, nuevo = _ida_y_vuelta(ag)
                    self.assertEqual(nuevo._eventos, [])
                    self.assertEqual(nuevo.extraer_eventos(), [])

    def test_los_escenarios_originales_si_tenian_eventos_pendientes(self):
        con_eventos = [ag for lista in TODOS.values() for ag in lista if ag._eventos]
        self.assertGreater(len(con_eventos), 10)

    def test_la_rehidratacion_no_ejecuta_los_constructores(self):
        # Los constructores de SolicitudCambio y SustitucionProveedor registran un evento: si se llamaran, este parche fallaría.
        from contextlib import ExitStack
        from unittest import mock
        originales = [A.solicitudes_cambio()[0], A.sustituciones()[0], A.propuestas()[0], A.eventos()[0]]

        def prohibido(self, *a, **k):
            raise AssertionError('se llamó a un constructor de agregado durante la rehidratación')
        with ExitStack() as pila:
            for clase in (SolicitudCambio, SustitucionProveedor, Propuesta, Evento):
                pila.enter_context(mock.patch.object(clase, '__init__', prohibido))
            for ag in originales:
                m = mapeador_de(ag)
                nuevo = m.desde_filas(m.a_filas(ag))
                self.assertEqual(nuevo._eventos, [])


class PrecisionYTipos(unittest.TestCase):
    def _valores(self, f: Filas):
        for fila in [f.raiz, *[x for filas in f.hijas.values() for x in filas]]:
            yield from fila.items()

    def test_ninguna_fila_contiene_float(self):
        for nombre, lista in TODOS.items():
            for ag in lista:
                for clave, valor in self._valores(mapeador_de(ag).a_filas(ag)):
                    with self.subTest(f'{nombre} {ag.id} {clave}'):
                        self.assertNotIsInstance(valor, float)

    def test_los_importes_conservan_el_decimal_exacto_y_su_escala(self):
        ec = A.estados_cuenta()[0]
        f = mapeador_de(ec).a_filas(ec)
        importes = {o['obligacion_id']: o['importe'] for o in f.hijas['obligacion_pago']}
        self.assertEqual(importes['OB-3'], D('150.25'))
        self.assertEqual(str(importes['OB-3B']), '99.9')              # sin añadir ceros ni redondear
        self.assertEqual(str(importes['OB-1']), '3000.00')           # 30 % de 10000.00 (BN-009)
        self.assertEqual(str(importes['OB-2']), '7000.00')            # saldo = costo - anticipo verificado
        for v in importes.values():
            self.assertIsInstance(v, D)
        nuevo = mapeador_de(ec).desde_filas(f)
        self.assertEqual({k: str(o.importe.cantidad) for k, o in nuevo.obligaciones.items()},
                         {k: str(o.importe.cantidad) for k, o in ec.obligaciones.items()})

    def test_decimales_largos_y_el_maximo_de_invitados_viajan_sin_perdida(self):
        e = Evento('EV-X', 'CL-X', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 9223372036854775807), ['x'])
        nuevo = _ida_y_vuelta(e)[2]
        self.assertEqual(nuevo.datos.invitados_aproximados, 9223372036854775807)
        p = Propuesta('PR-X', 'EV-X', 'CL-X', ContenidoPropuesta(('a',), (), Importe(D('12.345678901234567890')), 'c'), T0)
        nuevo = _ida_y_vuelta(p)[2]
        self.assertEqual(str(nuevo.versiones[0].contenido.costo_total.cantidad), '12.345678901234567890')

    def test_las_enumeraciones_se_guardan_por_nombre(self):
        for nombre, lista in TODOS.items():
            for ag in lista:
                f = mapeador_de(ag).a_filas(ag)
                for clave, valor in self._valores(f):
                    if clave in ('estado', 'concepto', 'tipo_origen') and valor is not None:
                        with self.subTest(f'{nombre} {ag.id} {clave}'):
                            self.assertRegex(valor, r'^[A-Z][A-Z0-9_]*$')

    def test_las_fechas_son_naive_como_el_dominio(self):
        from datetime import datetime
        for nombre, lista in TODOS.items():
            for ag in lista:
                for clave, valor in self._valores(mapeador_de(ag).a_filas(ag)):
                    if isinstance(valor, datetime):
                        self.assertIsNone(valor.tzinfo, (nombre, clave))

    def test_los_importes_reconstruidos_pasan_por_importe(self):
        f = mapeador_de(A.estados_cuenta()[0]).a_filas(A.estados_cuenta()[0])
        f.hijas['obligacion_pago'][0]['importe'] = D('-1')             # una fila corrupta no se acepta en silencio
        with self.assertRaises(ErrorDominio):
            mapeador_de(EstadoCuenta).desde_filas(f)


class OrdenYColecciones(unittest.TestCase):
    def test_diccionarios_y_listas_conservan_su_orden(self):
        e = A.eventos()[0]
        nuevo = _ida_y_vuelta(e)[2]
        self.assertEqual(list(nuevo.servicios), list(e.servicios))
        self.assertEqual(list(nuevo.servicios), ['CT-1-S1', 'CT-1-S2', 'SA-1-S'])
        s = A.solicitudes_cambio()[0]
        self.assertEqual(list(_ida_y_vuelta(s)[2].condiciones_propuestas), ['CT-1-S2', 'CT-1-S1'])     # orden de inserción
        ec = A.estados_cuenta()[0]
        self.assertEqual(list(_ida_y_vuelta(ec)[2].obligaciones), list(ec.obligaciones))
        self.assertEqual([p.pago_id for p in _ida_y_vuelta(ec)[2].pagos], ['PG-1', 'PG-2', 'PG-3', 'PG-4'])

    def test_las_filas_hijas_llevan_posicion_consecutiva(self):
        for ag in (A.eventos()[0], A.contratos()[0], A.estados_cuenta()[0], A.sustituciones()[0], A.solicitudes_cambio()[0]):
            f = mapeador_de(ag).a_filas(ag)
            for tabla, filas in f.hijas.items():
                if filas and 'posicion' in filas[0]:
                    self.assertEqual([x['posicion'] for x in filas], list(range(len(filas))), tabla)

    def test_versiones_alternativas_y_anexos_conservan_su_secuencia(self):
        p = _ida_y_vuelta(A.propuestas()[0])[2]
        self.assertEqual([v.numero for v in p.versiones], [1, 2])
        sp = _ida_y_vuelta(A.sustituciones()[0])[2]
        self.assertEqual([a.proveedor_id for a in sp.alternativas], ['PV-2', 'PV-3'])
        self.assertEqual(sp.alternativa_vigente.proveedor_id, 'PV-3')
        c = _ida_y_vuelta(A.contratos()[0])[2]
        self.assertEqual([a.anexo_id for a in c.anexos], ['AX-1', 'AX-2', 'AX-3'])
        self.assertEqual([a.tipo_origen for a in c.anexos],
                         [TipoSolicitud.CAMBIO, TipoSolicitud.SERVICIO_ADICIONAL, TipoSolicitud.SUSTITUCION_PROVEEDOR])


class EstadoPrivadoEInvariantes(unittest.TestCase):
    """El agregado rehidratado debe comportarse igual que el original: el estado privado se conservó."""
    def test_evento_operaciones_aplicadas_hacen_idempotente_la_reaccion(self):
        e = _ida_y_vuelta(A.eventos()[0])[2]
        self.assertEqual(e._operaciones_aplicadas, {'SC-1', 'SA-1', 'SP-1'})
        antes = estado_de(e)
        e.aplicar_cambio_confirmado('SC-1', DatosEvento('Otra', FECHA_EVENTO, 'Otro', 1), {}, T0)    # ya aplicada: sin efecto
        self.assertEqual(estado_de(e), antes)

    def test_estado_cuenta_ventana_resuelta_y_cierres_hacen_idempotentes_sus_operaciones(self):
        ec = _ida_y_vuelta(A.estados_cuenta()[0])[2]
        self.assertEqual(ec._ventana_resuelta, 'OB-5')
        with self.assertRaises(ErrorDominio) as ctx:
            ec.resolver_regularizacion(FECHA_EVENTO + timedelta(days=9))
        self.assertIn('ya fue registrado', str(ctx.exception))
        n = len(ec.devoluciones)
        self.assertEqual(ec.aplicar_cierre_sin_realizar('SC-1', T0, False, lambda: 'DV-NUEVA'), [])      # primer cierre ya registrado
        self.assertEqual(len(ec.devoluciones), n)
        self.assertEqual(ec.no_regularizado_verificado, True)

    def test_estado_cuenta_devolucion_efectuada_no_se_vuelve_a_registrar(self):
        ec = _ida_y_vuelta(A.estados_cuenta()[0])[2]
        ec.registrar_devolucion_efectuada('DV-1', T0, 'otro comprobante')
        self.assertEqual(ec.devoluciones[0].comprobante, 'Transferencia 99')
        self.assertEqual(ec.extraer_eventos(), [])

    def test_solicitud_detenida_recupera_su_estado_anterior(self):
        s = _ida_y_vuelta(A.solicitudes_cambio()[1])[2]
        self.assertEqual(s.estado, EstadoSolicitudCambio.DETENIDA_SALDO_VENCIDO)
        self.assertEqual(s._estado_antes_de_detener, EstadoSolicitudCambio.REGISTRADA)
        self.assertTrue(s.aplicar_decision_regularizacion(DecisionRegularizacion(True, False, ''), T0, EstadoSolicitudCambio.NO_PROCEDENTE))
        self.assertEqual(s.estado, EstadoSolicitudCambio.REGISTRADA)

    def test_solicitud_cambio_conserva_decisiones_importes_y_motivo_de_cierre(self):
        completa, _, no_viable, rechazada, _ = [_ida_y_vuelta(x)[2] for x in A.solicitudes_cambio()]
        self.assertEqual(completa.estado, EstadoSolicitudCambio.CONFIRMADA)
        self.assertEqual(completa.costo_proveedor, Importe(D('1200.50')))
        self.assertEqual([c for c, _ in completa.importes_a_cobrar], [c for c, _ in A.solicitudes_cambio()[0].importes_a_cobrar])
        self.assertTrue(completa.decision_cliente.aprobada)
        self.assertEqual(no_viable.motivo_cierre.descripcion, 'Sin disponibilidad')
        self.assertFalse(rechazada.decision_cliente.aprobada)
        self.assertEqual(rechazada.motivo_cierre.causa.name, 'RECHAZO_CLIENTE')

    def test_propuesta_rehidratada_genera_la_version_siguiente_con_un_solo_evento(self):
        p = _ida_y_vuelta(A.propuestas()[0])[2]
        nueva = p.generar_nueva_version if p.estado.name == 'EN_REVISION_CLIENTE' else None
        self.assertIsNone(nueva)                                           # aceptada: ya no admite versiones
        p3 = _ida_y_vuelta(A.propuestas()[2])[2]
        v = p3.generar_nueva_version(ContenidoPropuesta(('a',), (), Importe(D('1')), 'c'), T0)
        self.assertEqual(v.numero, 2)
        self.assertEqual(len(p3.extraer_eventos()), 1)                    # solo el evento de ESTA operación

    def test_contrato_rehidratado_conserva_el_plazo_de_24_horas_y_los_anexos_unicos(self):
        c = _ida_y_vuelta(A.contratos()[0])[2]
        self.assertEqual(c.limite_pago_anticipo(), T0 + timedelta(days=4, hours=24))
        with self.assertRaises(ErrorDominio):
            c.registrar_anexo('AX-9', TipoSolicitud.CAMBIO, 'SC-1', 'duplicado', T0)        # origen ya anexado
        self.assertTrue(c.politica.comunicada())

    def test_evento_rehidratado_respeta_la_maquina_de_estados(self):
        cancelado = _ida_y_vuelta(A.eventos()[4])[2]
        self.assertEqual(cancelado.estado, EstadoEvento.CANCELADO)
        self.assertEqual(cancelado.revision_administrativa.pagos_realizados, Importe(D('3000.50')))
        with self.assertRaises(ErrorDominio):
            cancelado.finalizar(T0)
        ejecutado = _ida_y_vuelta(A.eventos()[3])[2]
        self.assertEqual(ejecutado.estado, EstadoEvento.FINALIZADO)
        self.assertEqual(len(ejecutado.solicitudes_cancelacion), 1)

    def test_servicio_adicional_y_sustitucion_conservan_su_estado_y_disponibilidad(self):
        sa = [_ida_y_vuelta(x)[2] for x in A.solicitudes_servicio_adicional()]
        self.assertTrue(sa[0].elegibilidad_obtenida)
        self.assertEqual(sa[0].importe_a_cobrar, Importe(D('800.00')))
        self.assertEqual(sa[0].disponibilidad.proveedor_id, 'PV-9')
        self.assertEqual(sa[0].disponibilidad.condiciones.descripcion, 'Foto 4 h')
        self.assertEqual(sa[1].estado.name, 'EN_BUSQUEDA_PROVEEDOR')          # sin proveedor: el dominio no guarda disponibilidad
        self.assertIsNone(sa[1].disponibilidad)
        sp = _ida_y_vuelta(A.sustituciones()[0])[2]
        self.assertTrue(sp.importe_adicional_aprobado)
        self.assertEqual(sp.costo_adicional, Importe(D('250.75')))


if __name__ == '__main__':
    unittest.main()
