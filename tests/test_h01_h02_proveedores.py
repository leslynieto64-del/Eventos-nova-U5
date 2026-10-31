"""E3G (H-01 y H-02): asignación inicial de proveedores y operaciones del proveedor sobre sus servicios.

Reglas: US-013 a US-016, CA-029 a CA-036, GL-013, GL-018, GL-036, GL-040, BN-004, BN-007, BN-009 (los proveedores se
asignan con la contratación confirmada y antes del inicio), SE-001 (la sustitución sigue siendo su propio caso de uso).
Ejecutar desde la raíz:  python -m unittest tests.test_h01_h02_proveedores -v"""
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from test_reglas_corregidas import Escenario, FECHA_EVENTO                                          # noqa: E402
from application.cqrs import ConsultarServicioAsignadoQuery                                         # noqa: E402
from domain import eventos_dominio                                                                   # noqa: E402
from domain.evento import ServicioContratado                                                         # noqa: E402
from domain.valores import (CondicionesServicio, DisponibilidadProveedor, ErrorDominio, EstadoEvento,  # noqa: E402
                            EstadoServicioContratado as ES, Importe)
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                               # noqa: E402

OPCIONES = [DisponibilidadProveedor('PV-1', True, Importe(D(100)), CondicionesServicio('c')),
            DisponibilidadProveedor('PV-2', True, Importe(D(120)), CondicionesServicio('c')),
            DisponibilidadProveedor('PV-3', False)]


def escenario(opciones=OPCIONES, confirmar=True):
    e = Escenario(ConsultaDisponibilidadSimulada(opciones))
    if confirmar:
        e.confirmar_contratacion()
        e.servicio_id = next(iter(e.evento().servicios))
    return e


def estado_servicio(e, sid=None):
    return e.evento().servicios[sid or e.servicio_id].estado


def snapshot(e):
    """Lo que no debe cambiar con las consultas ni con los rechazos: Evento completo y Outbox."""
    ev = e.evento()
    return (ev.estado, ev.datos, {k: (s.proveedor_id, s.estado, s.condiciones) for k, s in ev.servicios.items()},
            ev.configuracion_vigente(), len(e.app.uow.outbox))


# ======================================================================= consulta de disponibilidad (CA-029, CA-030)
class ConsultaDeDisponibilidad(unittest.TestCase):
    def test_informa_quienes_estan_disponibles_para_el_servicio_y_la_fecha(self):            # CA-029, CA-030
        e = escenario()
        antes = snapshot(e)
        r = e.s.proveedores.consultar_disponibilidad_servicio(e.evento_id, e.servicio_id)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(r.datos['servicio'], 'Banquete')
        self.assertEqual((r.datos['disponibles'], r.datos['no_disponibles']), (['PV-1', 'PV-2'], ['PV-3']))
        self.assertEqual(snapshot(e), antes)                                                   # consulta sin efectos

    def test_la_consulta_recibe_el_servicio_y_la_fecha_del_evento(self):                     # CA-029
        llamadas = []

        class Espia(ConsultaDisponibilidadSimulada):
            def consultar(self, servicio, fecha_evento, proveedores_actuales):
                llamadas.append((servicio, fecha_evento))
                return super().consultar(servicio, fecha_evento, proveedores_actuales)
        e = Escenario(Espia(OPCIONES)); e.confirmar_contratacion()
        sid = next(iter(e.evento().servicios))
        e.s.proveedores.consultar_disponibilidad_servicio(e.evento_id, sid)
        self.assertEqual(llamadas, [('Banquete', FECHA_EVENTO)])

    def test_sin_opciones_la_consulta_devuelve_listas_vacias(self):
        e = escenario(opciones=[])
        r = e.s.proveedores.consultar_disponibilidad_servicio(e.evento_id, e.servicio_id)
        self.assertEqual((r.exito, r.datos['disponibles'], r.datos['no_disponibles']), (True, [], []))

    def test_evento_o_servicio_inexistentes_se_rechazan(self):
        e = escenario()
        for evento, servicio in (('EV-no-existe', e.servicio_id), (e.evento_id, 'S-no-existe')):
            with self.subTest(evento=evento, servicio=servicio):
                r = e.s.proveedores.consultar_disponibilidad_servicio(evento, servicio)
                self.assertFalse(r.exito)
                self.assertTrue(r.mensaje)


# ======================================================================= asignación (CA-031, CA-032)
class Asignacion(unittest.TestCase):
    def test_asigna_un_proveedor_disponible_y_queda_pendiente_de_confirmacion(self):         # CA-031, CA-032
        e = escenario()
        self.assertEqual(estado_servicio(e), ES.SIN_PROVEEDOR)
        self.assertIsNone(e.evento().servicios[e.servicio_id].proveedor_id)
        r = e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
        self.assertTrue(r.exito, r.mensaje)
        sc = e.evento().servicios[e.servicio_id]
        self.assertEqual((sc.proveedor_id, sc.estado, r.datos['estado']), ('PV-1', ES.PENDIENTE_CONFIRMACION, ES.PENDIENTE_CONFIRMACION.value))

    def test_la_asignacion_no_cambia_la_configuracion_vigente_ni_el_estado_del_evento(self):  # GL-035
        e = escenario()
        antes = e.evento()
        vigente, estado, outbox = antes.configuracion_vigente(), antes.estado, len(e.app.uow.outbox)
        e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
        e.d.despachar()
        despues = e.evento()
        self.assertEqual((despues.configuracion_vigente(), despues.estado, despues.datos), (vigente, estado, antes.datos))
        self.assertEqual(len(e.app.uow.outbox), outbox)                                        # sin Domain Events nuevos

    def test_un_proveedor_no_disponible_no_se_asigna(self):                                  # CA-031
        e = escenario()
        for proveedor in ('PV-3', 'PV-desconocido'):
            with self.subTest(proveedor=proveedor):
                r = e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, proveedor)
                self.assertFalse(r.exito)
                self.assertEqual(estado_servicio(e), ES.SIN_PROVEEDOR)
                self.assertIsNone(e.evento().servicios[e.servicio_id].proveedor_id)

    def test_un_servicio_con_proveedor_no_admite_otra_asignacion_inicial(self):               # SE-001
        e = escenario()
        e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
        r = e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-2')
        self.assertFalse(r.exito)
        self.assertIn('sustitución', r.mensaje)
        self.assertEqual(e.evento().servicios[e.servicio_id].proveedor_id, 'PV-1')

    def test_identificadores_inexistentes_se_rechazan_sin_efectos(self):
        e = escenario()
        antes = snapshot(e)
        for evento, servicio in (('EV-no-existe', e.servicio_id), (e.evento_id, 'S-no-existe')):
            with self.subTest(evento=evento, servicio=servicio):
                self.assertFalse(e.s.proveedores.asignar_proveedor(evento, servicio, 'PV-1').exito)
        self.assertEqual(snapshot(e), antes)

    def test_solo_se_asigna_con_el_evento_en_organizacion(self):                             # BN-009
        # En gestión: la contratación no está confirmada y el Evento todavía no tiene servicios contratados.
        e = escenario(confirmar=False)
        r = e.s.proveedores.asignar_proveedor(e.evento_id, 'cualquiera', 'PV-1')
        self.assertFalse(r.exito)
        self.assertEqual(e.evento().estado, EstadoEvento.EN_GESTION)
        # Iniciado, cancelado y finalizado: se rechaza sin cambios.
        for nombre, preparar in (('iniciado', lambda x: x.s.cierre.procesar_inicio_evento(x.evento_id, FECHA_EVENTO)),
                                 ('cancelado', lambda x: x.s.cierre.gestionar_cancelacion_solicitada(
                                     x.evento_id, 'Desiste', FECHA_EVENTO - timedelta(days=5)))):
            with self.subTest(estado=nombre):
                e = escenario()
                preparar(e); e.d.despachar()
                antes = snapshot(e)
                r = e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
                self.assertFalse(r.exito)
                self.assertIn('En organización', r.mensaje)
                self.assertEqual(snapshot(e), antes)
        e = escenario()
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO)
        e.s.cierre.finalizar_evento(e.evento_id, FECHA_EVENTO + timedelta(hours=6)); e.d.despachar()
        self.assertEqual(e.evento().estado, EstadoEvento.FINALIZADO)
        self.assertFalse(e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1').exito)

    def test_cada_servicio_se_asigna_por_separado(self):
        e = escenario()
        ev = e.evento()
        # Un segundo servicio contratado, confirmado antes (nace Sin proveedor), se asigna de forma independiente.
        otro = ServicioContratado('CT-S2', 'Música', None, CondicionesServicio('x'))
        self.assertEqual(otro.estado, ES.SIN_PROVEEDOR)
        ev.servicios[otro.servicio_contratado_id] = otro
        from application.servicios import transaccion
        with transaccion(e.app.uow, ev):
            e.app.repos.eventos.guardar(ev)
        e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
        self.assertEqual((estado_servicio(e, e.servicio_id), estado_servicio(e, 'CT-S2')), (ES.PENDIENTE_CONFIRMACION, ES.SIN_PROVEEDOR))
        self.assertTrue(e.s.proveedores.asignar_proveedor(e.evento_id, 'CT-S2', 'PV-2').exito)
        self.assertEqual({k: s.proveedor_id for k, s in e.evento().servicios.items()}, {e.servicio_id: 'PV-1', 'CT-S2': 'PV-2'})


# ======================================================================= respuesta del proveedor (CA-035, CA-036)
class RespuestaDelProveedor(unittest.TestCase):
    def asignado(self):
        e = escenario()
        self.assertTrue(e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1').exito)
        return e

    def test_el_proveedor_confirma_su_disponibilidad(self):                                  # CA-035
        e = self.asignado()
        r = e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', True)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual((estado_servicio(e), r.datos['estado']), (ES.CONFIRMADO, ES.CONFIRMADO.value))
        self.assertEqual(e.evento().servicios[e.servicio_id].proveedor_id, 'PV-1')
        self.assertEqual(e.avisos('Proveedor no disponible'), [])

    def test_la_confirmacion_conserva_las_condiciones_acordadas(self):                       # GL-035, no se inventan condiciones
        e = self.asignado()
        antes = e.evento().servicios[e.servicio_id].condiciones
        e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', True)
        self.assertEqual(e.evento().servicios[e.servicio_id].condiciones, antes)

    def test_el_proveedor_informa_que_no_puede_y_se_avisa_al_coordinador(self):              # CA-036
        e = self.asignado()
        r = e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', False)
        self.assertTrue(r.exito, r.mensaje)
        self.assertEqual(estado_servicio(e), ES.PROVEEDOR_NO_DISPONIBLE)
        self.assertEqual(e.evento().servicios[e.servicio_id].proveedor_id, 'PV-1')            # queda como proveedor original
        (aviso,) = e.avisos('Proveedor no disponible')
        self.assertEqual(aviso[0], ('Coordinador',))
        self.assertIn('PV-1', aviso[2]); self.assertIn('Banquete', aviso[2])

    def test_la_sustitucion_puede_iniciarse_con_el_caso_de_uso_existente(self):               # SE-001, CA-046
        e = self.asignado()
        e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', False)
        r = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, e.servicio_id, e.contrato_id, FECHA_EVENTO - timedelta(days=20))
        self.assertTrue(r.exito, r.mensaje)
        s = e.app.repos.sustituciones.obtener_por_id(r.datos['sustitucion_id'])
        self.assertEqual(s.proveedor_original_id, 'PV-1')
        # La alternativa confirmada reemplaza al proveedor y el servicio queda confirmado por el nuevo proveedor.
        e2 = escenario([DisponibilidadProveedor('PV-9', True, Importe(D(100)), CondicionesServicio('c')), OPCIONES[0]])
        e2.s.proveedores.asignar_proveedor(e2.evento_id, e2.servicio_id, 'PV-1')
        e2.s.proveedores.registrar_respuesta_proveedor(e2.evento_id, e2.servicio_id, 'PV-1', False)
        dia = FECHA_EVENTO - timedelta(days=20)
        sp = e2.s.sustitucion.registrar_proveedor_no_disponible(e2.evento_id, e2.servicio_id, e2.contrato_id, dia).datos['sustitucion_id']
        self.assertTrue(e2.s.sustitucion.buscar_alternativa_sustitucion(sp, CondicionesServicio('Condiciones acordadas'), None, dia).exito)
        self.assertEqual(e2.app.repos.sustituciones.obtener_por_id(sp).alternativa_vigente.proveedor_id, 'PV-9')

    def test_el_reemplazo_confirmado_queda_asignado_y_confirmado_en_el_evento(self):            # SE-001, CA-051, CA-053
        e = escenario([DisponibilidadProveedor('PV-9', True, Importe(D(100)), CondicionesServicio('c')), OPCIONES[0]])
        e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
        e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', False)
        dia = FECHA_EVENTO - timedelta(days=20)
        sp = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, e.servicio_id, e.contrato_id, dia).datos['sustitucion_id']
        condiciones = e.evento().servicios[e.servicio_id].condiciones                       # misma condición: sin impacto
        self.assertTrue(e.s.sustitucion.buscar_alternativa_sustitucion(sp, condiciones, None, dia).exito)
        self.assertTrue(e.s.sustitucion.registrar_anexo_sustitucion_proveedor(sp, 'Anexo del reemplazo', dia).exito)
        e.d.despachar()
        r = e.s.sustitucion.confirmar_sustitucion_proveedor(sp, dia + timedelta(hours=1))
        self.assertTrue(r.exito, r.mensaje)
        e.d.despachar()                                                                      # reacción que reasigna el proveedor
        sc = e.evento().servicios[e.servicio_id]
        self.assertEqual((sc.proveedor_id, sc.estado, sc.condiciones), ('PV-9', ES.CONFIRMADO, condiciones))
        vm = e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-9', e.evento_id))
        self.assertEqual([(s.servicio, s.estado) for s in vm.servicios], [('Banquete', 'Confirmado por el proveedor')])
        self.assertIsNone(e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-1', e.evento_id)))

    def test_solo_responde_el_proveedor_asignado(self):                                     # BN-007
        e = self.asignado()
        antes = snapshot(e)
        r = e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-2', True)
        self.assertFalse(r.exito)
        self.assertIn('no está asignado', r.mensaje)
        self.assertEqual(snapshot(e), antes)
        self.assertEqual(e.avisos('Proveedor no disponible'), [])

    def test_no_se_responde_sin_asignacion_ni_dos_veces(self):
        e = escenario()
        self.assertFalse(e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', True).exito)  # sin asignar
        e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
        self.assertTrue(e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', True).exito)
        antes = snapshot(e)
        for disponible in (True, False):
            with self.subTest(disponible=disponible):
                self.assertFalse(e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', disponible).exito)
        self.assertEqual(snapshot(e), antes)
        self.assertEqual(e.avisos('Proveedor no disponible'), [])                              # la 2.ª respuesta no avisa

    def test_identificadores_inexistentes_y_estados_invalidos(self):
        e = self.asignado()
        antes = snapshot(e)
        for evento, servicio in (('EV-no-existe', e.servicio_id), (e.evento_id, 'S-no-existe')):
            with self.subTest(evento=evento, servicio=servicio):
                self.assertFalse(e.s.proveedores.registrar_respuesta_proveedor(evento, servicio, 'PV-1', True).exito)
        self.assertEqual(snapshot(e), antes)                                                   # los rechazos no cambian nada
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        iniciado = snapshot(e)
        r = e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', True)
        self.assertFalse(r.exito)
        self.assertIn('En organización', r.mensaje)
        self.assertEqual(estado_servicio(e), ES.PENDIENTE_CONFIRMACION)                       # tras el inicio ya no se responde
        self.assertEqual(snapshot(e), iniciado)


# ======================================================================= consulta del Proveedor (CA-033, CA-034)
class ConsultaDelProveedor(unittest.TestCase):
    def preparar(self):
        e = escenario()
        ev = e.evento()
        ev.servicios['CT-S2'] = ServicioContratado('CT-S2', 'Música', None, CondicionesServicio('DJ 4 horas'))
        from application.servicios import transaccion
        with transaccion(e.app.uow, ev):
            e.app.repos.eventos.guardar(ev)
        e.s.proveedores.asignar_proveedor(e.evento_id, e.servicio_id, 'PV-1')
        e.s.proveedores.asignar_proveedor(e.evento_id, 'CT-S2', 'PV-2')
        return e

    def test_el_proveedor_ve_los_datos_del_evento_y_su_servicio(self):                       # CA-033, CA-034
        e = self.preparar()
        vm = e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-1', e.evento_id))
        self.assertEqual((vm.eventoId, vm.tipoEvento, vm.fecha, vm.hora, vm.lugar, vm.invitadosAproximados),
                         (e.evento_id, 'Boda', '2026-11-20', '18:00', 'Salón', 100))
        self.assertEqual([(s.servicioContratadoId, s.servicio, s.condiciones, s.estado) for s in vm.servicios],
                         [(e.servicio_id, 'Banquete', 'Condiciones acordadas', 'Pendiente de confirmación del proveedor')])

    def test_cada_proveedor_ve_solo_sus_servicios(self):                                    # BN-007
        e = self.preparar()
        vm1 = e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-1', e.evento_id))
        vm2 = e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-2', e.evento_id))
        self.assertEqual([s.servicio for s in vm1.servicios], ['Banquete'])
        self.assertEqual([(s.servicio, s.condiciones) for s in vm2.servicios], [('Música', 'DJ 4 horas')])

    def test_proveedor_sin_servicios_o_evento_inexistente_no_obtiene_datos(self):             # BN-007
        e = self.preparar()
        self.assertIsNone(e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-3', e.evento_id)))
        self.assertIsNone(e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-1', 'EV-no-existe')))
        self.assertIsNone(e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('', e.evento_id)))

    def test_la_consulta_refleja_la_respuesta_y_no_modifica_nada(self):                     # CA-035, CA-036
        e = self.preparar()
        e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, e.servicio_id, 'PV-1', True)
        e.s.proveedores.registrar_respuesta_proveedor(e.evento_id, 'CT-S2', 'PV-2', False)
        antes = snapshot(e)
        vm1 = e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-1', e.evento_id))
        vm2 = e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-2', e.evento_id))
        self.assertEqual(vm1.servicios[0].estado, 'Confirmado por el proveedor')
        self.assertEqual(vm2.servicios[0].estado, 'Proveedor no disponible')
        self.assertEqual(snapshot(e), antes)                                                    # consulta sin escrituras

    def test_un_servicio_adicional_confirmado_aparece_confirmado_para_su_proveedor(self):
        e = escenario([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ 4 horas'))])
        self.assertEqual(ServicioContratado('SA-1-S', 'DJ', 'PV-9', CondicionesServicio('x')).estado, ES.CONFIRMADO)
        ev = e.evento()
        ev.incorporar_servicio_adicional('SA-1', ServicioContratado('SA-1-S', 'DJ', 'PV-9', CondicionesServicio('DJ 4 horas')))
        from application.servicios import transaccion
        with transaccion(e.app.uow, ev):
            e.app.repos.eventos.guardar(ev)
        vm = e.app.queries.servicio_asignado.handle(ConsultarServicioAsignadoQuery('PV-9', e.evento_id))
        self.assertEqual([(s.servicio, s.estado) for s in vm.servicios], [('DJ', 'Confirmado por el proveedor')])


# ======================================================================= dominio y restricciones del proyecto
class DominioDelEvento(unittest.TestCase):
    def test_estado_por_defecto_segun_el_proveedor(self):
        self.assertEqual(ServicioContratado('S1', 'Banquete', None, CondicionesServicio('c')).estado, ES.SIN_PROVEEDOR)
        self.assertEqual(ServicioContratado('S1', 'Banquete', 'PV-1', CondicionesServicio('c')).estado, ES.CONFIRMADO)
        explicito = ServicioContratado('S1', 'Banquete', 'PV-1', CondicionesServicio('c'), ES.PENDIENTE_CONFIRMACION)
        self.assertEqual(explicito.estado, ES.PENDIENTE_CONFIRMACION)

    def test_asignar_exige_proveedor_y_servicio_existente(self):
        e = escenario(); ev = e.evento()
        with self.assertRaises(ErrorDominio):
            ev.asignar_proveedor(e.servicio_id, '')
        with self.assertRaises(ErrorDominio):
            ev.asignar_proveedor('S-no-existe', 'PV-1')
        self.assertEqual(ev.servicios[e.servicio_id].estado, ES.SIN_PROVEEDOR)

    def test_no_se_agregaron_domain_events_ni_se_alteraron_los_existentes(self):
        eventos = {n for n, c in vars(eventos_dominio).items() if isinstance(c, type)
                   and issubclass(c, eventos_dominio.EventoDominio) and c is not eventos_dominio.EventoDominio}
        self.assertEqual(len(eventos), 31)

    def test_la_asignacion_y_la_respuesta_no_emiten_domain_events(self):
        e = escenario(); ev = e.evento()
        ev.extraer_eventos()
        ev.asignar_proveedor(e.servicio_id, 'PV-1')
        ev.registrar_respuesta_proveedor(e.servicio_id, 'PV-1', True)
        self.assertEqual(ev.extraer_eventos(), [])


if __name__ == '__main__':
    unittest.main()
