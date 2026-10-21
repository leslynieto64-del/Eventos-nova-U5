"""Etapa E3A — State Machine del agregado Evento.

Comprueba la tabla implementada, cada transición válida, las inválidas (incluidos los estados terminales), las
precondiciones de cancelación, inicio y finalización, la idempotencia, la ausencia de efectos en los rechazos, la
separación con las Specifications y la conservación del comportamiento de v8 + E1 + E2."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_maquina_estados import (evento_en, observar, acciones, capturar_comportamiento_evento,   # noqa: E402
                                   RUTA_REFERENCIA_EVENTO, VARIANTES, AHORA, INICIO, SERVICIOS)
from test_reglas_corregidas import Escenario, T0, FECHA_EVENTO                                    # noqa: E402

import domain.evento as mod_evento                                                                 # noqa: E402
from domain.evento import Evento, AccionEvento, MAQUINA_EVENTO, ServicioContratado                # noqa: E402
from domain.maquina_estados import MaquinaEstados, Transicion, TransicionNoPermitida              # noqa: E402
from domain.valores import (EstadoEvento as EE, ErrorDominio, OrigenCancelacion, CondicionesServicio,  # noqa: E402
                            EstadoSolicitudCancelacion, EstadoPropuesta)

TABLA_ESPERADA = {
    (EE.EN_GESTION, AccionEvento.CONFIRMAR_CONTRATACION): EE.EN_ORGANIZACION,
    (EE.EN_GESTION, AccionEvento.CERRAR_SIN_CONTRATACION): EE.CERRADO_SIN_CONTRATACION,
    (EE.EN_ORGANIZACION, AccionEvento.CANCELAR): EE.CANCELADO,
    (EE.EN_ORGANIZACION, AccionEvento.INICIAR): EE.EN_EJECUCION,
    (EE.EN_EJECUCION, AccionEvento.FINALIZAR): EE.FINALIZADO,
}
IDEMPOTENTES = {(EE.EN_ORGANIZACION, AccionEvento.CONFIRMAR_CONTRATACION),
                (EE.CERRADO_SIN_CONTRATACION, AccionEvento.CERRAR_SIN_CONTRATACION)}

# Mensajes existentes de Evento (v8), escritos literalmente para no depender de la propia tabla.
MENSAJES = {
    AccionEvento.CONFIRMAR_CONTRATACION: "No puede pasar a En organización desde {}.",
    AccionEvento.CERRAR_SIN_CONTRATACION: "No puede cerrarse sin contratación desde {}.",
    AccionEvento.CANCELAR: "No puede cancelarse un evento {}.",
    AccionEvento.INICIAR: "No puede iniciar un evento {}.",
}
CA_084 = "La cancelación solo procede con la contratación confirmada (CA-084)."
CA_094 = "Solo puede finalizarse un evento que se realizó (CA-094)."
CA_095 = "Un evento cancelado no puede registrarse como Finalizado (CA-095)."
SIN_VERIFICAR = "Administración no ha verificado el vencimiento del plazo de regularización."
SIN_MOTIVO = "El Coordinador debe indicar el motivo de la cancelación (BN-005)."
FIN = datetime(2026, 11, 21, 3, 0)


def ejecutar_accion(ev: Evento, accion: AccionEvento):
    """Invoca el método del agregado que corresponde a la acción (cancelar: solicitud procedente del Cliente)."""
    return {
        AccionEvento.CONFIRMAR_CONTRATACION: lambda: ev.confirmar_contratacion(
            [ServicioContratado('CT-S9', 'Música', None, CondicionesServicio('x'))]),
        AccionEvento.CERRAR_SIN_CONTRATACION: lambda: ev.cerrar_sin_contratacion(),
        AccionEvento.CANCELAR: lambda: ev.solicitar_cancelacion('Motivo', AHORA, True),
        AccionEvento.INICIAR: lambda: ev.iniciar(INICIO),
        AccionEvento.FINALIZAR: lambda: ev.finalizar(FIN),
    }[accion]()


def mensaje_esperado(estado: EE, accion: AccionEvento) -> str:
    if accion == AccionEvento.FINALIZAR:
        return CA_095 if estado == EE.CANCELADO else CA_094
    return MENSAJES[accion].format(estado.value)


# ======================================================================= tabla
class TablaDeTransiciones(unittest.TestCase):
    def test_tabla_implementada(self):
        self.assertEqual({(t.origen, t.accion): t.destino for t in MAQUINA_EVENTO.transiciones}, TABLA_ESPERADA)
        self.assertEqual(set(MAQUINA_EVENTO.repeticiones_idempotentes), IDEMPOTENTES)

    def test_estados_terminales(self):
        self.assertEqual(MAQUINA_EVENTO.estados_terminales, {EE.FINALIZADO, EE.CANCELADO, EE.CERRADO_SIN_CONTRATACION})

    def test_usa_los_estados_existentes_y_acciones_que_son_metodos_de_evento(self):
        self.assertEqual(set(MAQUINA_EVENTO.estados), set(EE))
        for accion in AccionEvento:
            with self.subTest(accion=accion):
                nombre = '_cancelar' if accion == AccionEvento.CANCELAR else accion.value
                self.assertTrue(callable(getattr(Evento, nombre, None)))

    def test_evento_usa_la_maquina(self):
        """Con una máquina que no permite iniciar, Evento.iniciar se rechaza: el agregado consulta la tabla."""
        sin_inicio = MaquinaEstados(EE, [t for t in MAQUINA_EVENTO.transiciones if t.accion != AccionEvento.INICIAR])
        ev = evento_en(EE.EN_ORGANIZACION)
        with mock.patch.object(mod_evento, 'MAQUINA_EVENTO', sin_inicio):
            with self.assertRaises(TransicionNoPermitida):
                ev.iniciar(INICIO)
        self.assertEqual(ev.estado, EE.EN_ORGANIZACION)


# ======================================================================= transiciones válidas
class TransicionesValidas(unittest.TestCase):
    def test_confirmar_contratacion(self):
        ev = evento_en(EE.EN_GESTION)
        ev.confirmar_contratacion(SERVICIOS)
        self.assertEqual(ev.estado, EE.EN_ORGANIZACION)
        self.assertEqual(list(ev.servicios), ['CT-S1'])
        self.assertEqual(ev.extraer_eventos(), [])           # la reacción no registra Domain Events propios

    def test_cerrar_sin_contratacion_nunca_cancela(self):
        ev = evento_en(EE.EN_GESTION)
        ev.cerrar_sin_contratacion()
        self.assertEqual(ev.estado, EE.CERRADO_SIN_CONTRATACION)
        self.assertIsNone(ev.motivo_cancelacion)
        self.assertEqual(ev.extraer_eventos(), [])

    def test_cancelar_por_solicitud_del_cliente(self):
        ev = evento_en(EE.EN_ORGANIZACION)
        self.assertTrue(ev.solicitar_cancelacion('Motivo', AHORA, True))
        self.assertEqual(ev.estado, EE.CANCELADO)
        self.assertEqual(ev.motivo_cancelacion.origen, OrigenCancelacion.SOLICITUD_CLIENTE)
        self.assertEqual([s.estado for s in ev.solicitudes_cancelacion], [EstadoSolicitudCancelacion.PROCEDENTE])
        eventos = ev.extraer_eventos()
        self.assertEqual([(e.nombre, e.origen) for e in eventos], [('EventoCancelado', 'Solicitud del Cliente')])

    def test_cancelar_por_falta_de_regularizacion(self):
        ev = evento_en(EE.EN_ORGANIZACION)
        self.assertTrue(ev.cancelar_por_falta_de_regularizacion('Sin regularizar', 'Coordinador', AHORA, True))
        self.assertEqual(ev.estado, EE.CANCELADO)
        self.assertEqual(ev.motivo_cancelacion.origen, OrigenCancelacion.FALTA_REGULARIZACION)
        self.assertEqual([e.nombre for e in ev.extraer_eventos()], ['EventoCancelado'])

    def test_iniciar(self):
        ev = evento_en(EE.EN_ORGANIZACION)
        ev.iniciar(INICIO)
        self.assertEqual((ev.estado, ev.fecha_inicio), (EE.EN_EJECUCION, INICIO))
        self.assertEqual([e.nombre for e in ev.extraer_eventos()], ['EventoIniciado'])

    def test_finalizar(self):
        ev = evento_en(EE.EN_EJECUCION)
        ev.finalizar(FIN)
        self.assertEqual((ev.estado, ev.fecha_finalizacion), (EE.FINALIZADO, FIN))
        self.assertEqual([e.nombre for e in ev.extraer_eventos()], ['EventoFinalizado'])

    def test_recorrido_completo(self):
        ev = evento_en(EE.EN_GESTION)
        ev.confirmar_contratacion(SERVICIOS); ev.iniciar(INICIO); ev.finalizar(FIN)
        self.assertEqual(ev.estado, EE.FINALIZADO)
        self.assertEqual([e.nombre for e in ev.extraer_eventos()], ['EventoIniciado', 'EventoFinalizado'])


# ======================================================================= transiciones inválidas
class TransicionesInvalidas(unittest.TestCase):
    def test_cada_par_no_permitido_se_rechaza_sin_efectos(self):
        revisados = 0
        for nombre, estado, origen in VARIANTES:
            for accion in AccionEvento:
                if (estado, accion) in TABLA_ESPERADA or (estado, accion) in IDEMPOTENTES:
                    continue
                if accion == AccionEvento.CANCELAR and estado == EE.EN_EJECUCION:
                    continue                                   # rechazo de negocio CA-088, se prueba aparte
                with self.subTest(estado=nombre, accion=accion.value):
                    ev = evento_en(estado, origen)
                    antes = observar(evento_en(estado, origen))
                    with self.assertRaises(ErrorDominio) as ctx:
                        ejecutar_accion(ev, accion)
                    self.assertEqual(str(ctx.exception), mensaje_esperado(estado, accion))
                    # Mismo estado, sin Domain Events, solicitudes, motivo, fechas ni servicios (incluye E3A-01).
                    self.assertEqual(observar(ev), antes)
                    revisados += 1
        # 7 variantes de estado × 5 acciones − 5 transiciones − 2 repeticiones − cancelar En ejecución (CA-088)
        self.assertEqual(revisados, 27)

    def test_cancelacion_por_falta_de_regularizacion_invalida_no_tiene_efectos(self):
        for nombre, estado, origen in VARIANTES:
            if estado == EE.EN_ORGANIZACION or origen == OrigenCancelacion.FALTA_REGULARIZACION:
                continue                                       # transición válida / repetición idempotente
            with self.subTest(estado=nombre):
                ev = evento_en(estado, origen)
                antes = observar(evento_en(estado, origen))
                with self.assertRaisesRegex(ErrorDominio, f"^No puede cancelarse un evento {estado.value}\\.$"):
                    ev.cancelar_por_falta_de_regularizacion('x', 'Coordinador', AHORA, True)
                self.assertEqual(observar(ev), antes)

    def test_estados_terminales_no_admiten_otras_transiciones(self):
        for nombre, estado, origen in VARIANTES:
            if estado not in MAQUINA_EVENTO.estados_terminales:
                continue
            for accion in AccionEvento:
                if (estado, accion) in IDEMPOTENTES:
                    continue
                with self.subTest(estado=nombre, accion=accion.value):
                    self.assertFalse(MAQUINA_EVENTO.permite(estado, accion))
                    with self.assertRaises(ErrorDominio):
                        ejecutar_accion(evento_en(estado, origen), accion)

    def test_finalizar_un_evento_cancelado_o_no_iniciado(self):
        for estado, mensaje in ((EE.CANCELADO, CA_095), (EE.EN_ORGANIZACION, CA_094), (EE.EN_GESTION, CA_094),
                                (EE.FINALIZADO, CA_094), (EE.CERRADO_SIN_CONTRATACION, CA_094)):
            with self.subTest(estado=estado):
                with self.assertRaisesRegex(ErrorDominio, f"^{mensaje.replace('(', '[(]').replace(')', '[)]')}$"):
                    evento_en(estado, OrigenCancelacion.SOLICITUD_CLIENTE).finalizar(FIN)



class CorreccionE3A01(unittest.TestCase):
    """E3A-01 (corregida, aprobada en la revisión de E3A).

    `solicitar_cancelacion` valida la transición antes de modificar el agregado. Antes, con la contratación confirmada,
    agregaba la solicitud como «Procedente» y después la máquina rechazaba la cancelación (En gestión, Finalizado,
    Cerrado sin contratación o Cancelado), de modo que la solicitud quedaba en el objeto aunque se lanzara el error."""

    def test_rechazo_sin_efectos_en_el_agregado(self):
        for nombre, estado, origen in VARIANTES:
            if estado in (EE.EN_ORGANIZACION, EE.EN_EJECUCION):
                continue
            with self.subTest(estado=nombre):
                ev = evento_en(estado, origen)
                antes = observar(evento_en(estado, origen))
                with self.assertRaises(ErrorDominio) as ctx:
                    ev.solicitar_cancelacion('Motivo', AHORA, True)
                self.assertEqual(str(ctx.exception), f"No puede cancelarse un evento {estado.value}.")   # mensaje de siempre
                self.assertEqual(ev.solicitudes_cancelacion, [])
                self.assertEqual(observar(ev), antes)   # estado, fechas, motivo de cancelación y Domain Events intactos

    def test_ca_084_ocurre_antes_de_registrar_cualquier_solicitud(self):
        for nombre, estado, origen in VARIANTES:
            with self.subTest(estado=nombre):
                ev = evento_en(estado, origen)
                with self.assertRaises(ErrorDominio) as ctx:
                    ev.solicitar_cancelacion('Motivo', AHORA, False)
                self.assertEqual(str(ctx.exception), CA_084)
                self.assertEqual(ev.solicitudes_cancelacion, [])

    def test_ca_088_se_conserva_en_ejecucion(self):
        ev = evento_en(EE.EN_EJECUCION)
        self.assertFalse(ev.solicitar_cancelacion('Motivo', AHORA, True))
        self.assertEqual(ev.estado, EE.EN_EJECUCION)
        self.assertEqual([(s.motivo, s.estado) for s in ev.solicitudes_cancelacion],
                         [('Motivo', EstadoSolicitudCancelacion.RECHAZADA_INICIO_EVENTO)])
        self.assertIsNone(ev.motivo_cancelacion)
        self.assertEqual(ev.extraer_eventos(), [])

    def test_cancelacion_valida_genera_un_unico_evento_cancelado(self):
        ev = evento_en(EE.EN_ORGANIZACION)
        self.assertTrue(ev.solicitar_cancelacion('Motivo', AHORA, True))
        self.assertEqual(ev.estado, EE.CANCELADO)
        self.assertEqual([(s.motivo, s.estado) for s in ev.solicitudes_cancelacion],
                         [('Motivo', EstadoSolicitudCancelacion.PROCEDENTE)])
        self.assertEqual([e.nombre for e in ev.extraer_eventos()], ['EventoCancelado'])
        with self.assertRaises(ErrorDominio):                                   # repetirla se rechaza sin efectos
            ev.solicitar_cancelacion('Otra vez', AHORA, True)
        self.assertEqual(len(ev.solicitudes_cancelacion), 1)
        self.assertEqual(ev.extraer_eventos(), [])

    def test_a_traves_del_servicio_no_se_persiste(self):
        e = Escenario(); e.confirmar_contratacion()
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        e.s.cierre.finalizar_evento(e.evento_id, FECHA_EVENTO + timedelta(hours=8)); e.d.despachar()
        r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Motivo', FECHA_EVENTO + timedelta(days=1))
        self.assertFalse(r.exito)
        self.assertEqual(e.evento().solicitudes_cancelacion, [])


# ======================================================================= precondiciones
class Precondiciones(unittest.TestCase):
    def test_no_se_cancela_sin_contratacion_confirmada(self):
        for nombre, estado, origen in VARIANTES:
            with self.subTest(estado=nombre):
                ev = evento_en(estado, origen)
                antes = observar(evento_en(estado, origen))
                with self.assertRaises(ErrorDominio) as ctx:
                    ev.solicitar_cancelacion('Motivo', AHORA, False)
                self.assertEqual(str(ctx.exception), CA_084)
                self.assertEqual(observar(ev), antes)           # se rechaza antes de registrar la solicitud

    def test_la_maquina_no_sustituye_la_precondicion_de_contratacion(self):
        """La tabla permite cancelar desde En organización, pero la condición CA-084 la sigue exigiendo el agregado."""
        self.assertTrue(MAQUINA_EVENTO.permite(EE.EN_ORGANIZACION, AccionEvento.CANCELAR))
        ev = evento_en(EE.EN_ORGANIZACION)
        with self.assertRaisesRegex(ErrorDominio, r"CA-084"):
            ev.solicitar_cancelacion('Motivo', AHORA, False)
        self.assertEqual(ev.estado, EE.EN_ORGANIZACION)

    def test_una_maquina_permisiva_no_salta_las_validaciones_del_agregado(self):
        permisiva = MaquinaEstados(EE, list(MAQUINA_EVENTO.transiciones) + [Transicion(EE.EN_GESTION, AccionEvento.CANCELAR, EE.CANCELADO)])
        with mock.patch.object(mod_evento, 'MAQUINA_EVENTO', permisiva):
            ev = evento_en(EE.EN_GESTION)
            with self.assertRaisesRegex(ErrorDominio, r"CA-084"):
                ev.solicitar_cancelacion('Motivo', AHORA, False)
            with self.assertRaisesRegex(ErrorDominio, "no ha verificado"):
                ev.cancelar_por_falta_de_regularizacion('x', 'Coordinador', AHORA, False)
            self.assertEqual(ev.estado, EE.EN_GESTION)

    def test_cancelacion_despues_del_inicio_se_rechaza_y_se_registra(self):     # CA-088
        ev = evento_en(EE.EN_EJECUCION)
        self.assertFalse(ev.solicitar_cancelacion('Motivo', AHORA, True))
        self.assertEqual(ev.estado, EE.EN_EJECUCION)
        self.assertEqual([(s.motivo, s.estado) for s in ev.solicitudes_cancelacion],
                         [('Motivo', EstadoSolicitudCancelacion.RECHAZADA_INICIO_EVENTO)])
        self.assertIsNone(ev.motivo_cancelacion)
        self.assertEqual(ev.extraer_eventos(), [])

    def test_cancelacion_por_falta_de_regularizacion_exige_verificacion_y_motivo(self):
        for estado in (EE.EN_ORGANIZACION, EE.EN_GESTION, EE.EN_EJECUCION):
            with self.subTest(estado=estado):
                with self.assertRaisesRegex(ErrorDominio, f"^{SIN_VERIFICAR}$"):
                    evento_en(estado).cancelar_por_falta_de_regularizacion('x', 'Coordinador', AHORA, False)
                with self.assertRaisesRegex(ErrorDominio, r"^El Coordinador debe indicar el motivo"):
                    evento_en(estado).cancelar_por_falta_de_regularizacion('', 'Coordinador', AHORA, True)
        with self.assertRaisesRegex(ErrorDominio, r"^No puede cancelarse un evento En ejecución\.$"):
            evento_en(EE.EN_EJECUCION).cancelar_por_falta_de_regularizacion('x', 'Coordinador', AHORA, True)

    def test_inicio_solo_desde_en_organizacion(self):
        for estado in EE:
            with self.subTest(estado=estado):
                ev = evento_en(estado, OrigenCancelacion.SOLICITUD_CLIENTE)
                if estado == EE.EN_ORGANIZACION:
                    ev.iniciar(INICIO); self.assertEqual(ev.estado, EE.EN_EJECUCION)
                else:
                    with self.assertRaisesRegex(ErrorDominio, f"^No puede iniciar un evento {estado.value}\\.$"):
                        ev.iniciar(INICIO)

    def test_cerrar_propuesta_por_no_aceptacion_no_cancela_el_evento(self):     # CA-092, SE-011
        from infrastructure.composicion import construir
        from domain.valores import DatosEvento
        from test_reglas_corregidas import CONTENIDO
        app = construir(); s = app.servicios
        evento_id = s.propuestas.registrar_evento('CL-1', DatosEvento('Boda', FECHA_EVENTO, 'Salón', 100), ['Banquete']).datos['evento_id']
        pr = s.propuestas.crear_propuesta(evento_id, CONTENIDO, T0).datos['propuesta_id']
        self.assertTrue(s.propuestas.cerrar_propuesta_no_aceptada(pr, 'No acepta', T0).exito)
        app.despachador.despachar()
        self.assertEqual(app.repos.propuestas.obtener_por_id(pr).estado, EstadoPropuesta.CERRADA_NO_ACEPTACION)
        ev = app.repos.eventos.obtener_por_id(evento_id)
        self.assertEqual(ev.estado, EE.EN_GESTION)
        self.assertIsNone(ev.motivo_cancelacion)


# ======================================================================= idempotencia
class Idempotencia(unittest.TestCase):
    def test_confirmar_contratacion_repetida_no_incorpora_servicios_otra_vez(self):
        ev = evento_en(EE.EN_GESTION)
        ev.confirmar_contratacion(SERVICIOS)
        ev.confirmar_contratacion([ServicioContratado('CT-S9', 'Otro', None, CondicionesServicio('x'))])
        self.assertEqual((ev.estado, list(ev.servicios)), (EE.EN_ORGANIZACION, ['CT-S1']))

    def test_cerrar_sin_contratacion_repetido(self):
        ev = evento_en(EE.EN_GESTION)
        ev.cerrar_sin_contratacion(); ev.cerrar_sin_contratacion()
        self.assertEqual(ev.estado, EE.CERRADO_SIN_CONTRATACION)

    def test_cancelacion_por_falta_de_regularizacion_repetida(self):
        ev = evento_en(EE.EN_ORGANIZACION)
        self.assertTrue(ev.cancelar_por_falta_de_regularizacion('x', 'Coordinador', AHORA, True))
        ev.extraer_eventos()
        self.assertFalse(ev.cancelar_por_falta_de_regularizacion('x', 'Coordinador', AHORA, True))
        self.assertEqual(ev.extraer_eventos(), [])                    # sin un segundo EventoCancelado

    def test_cancelado_por_el_cliente_no_es_repeticion_de_falta_de_regularizacion(self):
        ev = evento_en(EE.CANCELADO, OrigenCancelacion.SOLICITUD_CLIENTE)
        with self.assertRaisesRegex(ErrorDominio, r"^No puede cancelarse un evento Cancelado\.$"):
            ev.cancelar_por_falta_de_regularizacion('x', 'Coordinador', AHORA, True)

    def test_reaccion_repetida_a_contratacion_confirmada(self):
        e = Escenario(); e.confirmar_contratacion()
        servicios = list(e.evento().servicios)
        from domain.eventos_dominio import ContratacionConfirmada
        reaccion = next(r for _, r in e.app.despachador.publicador.reacciones(ContratacionConfirmada('X', T0))
                        if 'al_confirmarse_contratacion' in getattr(r, '__qualname__', ''))
        reaccion(ContratacionConfirmada(e.contrato_id, T0, evento_ref=e.evento_id))
        self.assertEqual((e.evento().estado, list(e.evento().servicios)), (EE.EN_ORGANIZACION, servicios))


# ======================================================================= aplicación y Specifications
class SeparacionDeResponsabilidades(unittest.TestCase):
    def test_servicio_de_cierre_conserva_respuestas_y_lo_persistido(self):
        e = Escenario(); e.confirmar_contratacion()
        e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO); e.d.despachar()
        r = e.s.cierre.finalizar_evento(e.evento_id, FECHA_EVENTO + timedelta(hours=8)); e.d.despachar()
        self.assertEqual((r.exito, r.mensaje), (True, 'Evento Finalizado.'))
        r = e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Motivo', FECHA_EVENTO + timedelta(days=1))
        self.assertEqual((r.exito, r.mensaje), (False, 'No puede cancelarse un evento Finalizado.'))
        self.assertEqual(e.evento().solicitudes_cancelacion, [])
        r = e.s.cierre.procesar_inicio_evento(e.evento_id, FECHA_EVENTO)
        self.assertEqual((r.exito, r.mensaje), (False, 'No puede iniciar un evento Finalizado.'))

    def test_evento_no_usa_specifications_y_la_maquina_tampoco(self):
        for archivo in ('evento.py', 'maquina_estados.py'):
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', archivo), encoding='utf8') as f:
                self.assertNotIn('especificacion', f.read().lower(), archivo)

    def test_specifications_de_e2_siguen_decidiendo_sus_condiciones(self):
        from apoyo_especificaciones import capturar_comportamiento, RUTA_REFERENCIA
        with open(RUTA_REFERENCIA, encoding='utf-8') as f:
            self.assertEqual(json.loads(json.dumps(capturar_comportamiento(), ensure_ascii=False)), json.load(f))


# ======================================================================= conservación
class ConservacionDelComportamiento(unittest.TestCase):
    """Referencia capturada con v8 + E1 + E2: 70 combinaciones de estado de partida × acción × precondiciones.

    Diferencia intencional (E3A-01): en los cinco casos de CORREGIDOS la referencia registra la solicitud «Procedente»
    que quedaba en el agregado tras el rechazo; ahora no queda ninguna. En esos casos se comprueba exactamente esa
    diferencia y que todo lo demás (mensaje, estado, Domain Events, motivo, fechas y servicios) es igual. Las otras
    65 combinaciones deben ser idénticas."""

    CORREGIDOS = {f'{variante} | solicitar_cancelacion(confirmada=True)' for variante in
                  ('EN_GESTION', 'FINALIZADO', 'CERRADO_SIN_CONTRATACION', 'CANCELADO_SOLICITUD_CLIENTE',
                   'CANCELADO_FALTA_REGULARIZACION')}

    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA_EVENTO, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = json.loads(json.dumps(capturar_comportamiento_evento(), ensure_ascii=False))

    def test_cobertura_de_la_referencia(self):
        self.assertEqual(len(self.referencia), len(VARIANTES) * len(acciones()))
        self.assertEqual(set(self.actual), set(self.referencia))

    def test_resultados_identicos_salvo_la_correccion_e3a01(self):
        """Valor devuelto o mensaje de error, estado, Domain Events, solicitudes, motivo, fechas y servicios."""
        for clave, esperado in self.referencia.items():
            if clave in self.CORREGIDOS:
                continue
            with self.subTest(caso=clave):
                self.assertEqual(self.actual[clave], esperado)
        self.assertEqual(len(self.referencia) - len(self.CORREGIDOS), 65)

    def test_correccion_e3a01_es_la_unica_diferencia(self):
        for clave in sorted(self.CORREGIDOS):
            with self.subTest(caso=clave):
                antes, ahora = dict(self.referencia[clave]), dict(self.actual[clave])
                self.assertEqual(antes.pop('solicitudes_cancelacion'), [['Motivo del Cliente', 'PROCEDENTE']])   # v8
                self.assertEqual(ahora.pop('solicitudes_cancelacion'), [])                                    # corregido
                self.assertIn('error', ahora)
                self.assertEqual(ahora, antes)


class AislamientoDelPaqueteCSV(unittest.TestCase):
    """Los estados ilustrativos del paquete 16_Eventos_Nova no forman parte del dominio (aclaración de alcance E3)."""

    def test_estados_y_acciones_son_los_de_eventos_nova(self):
        nombres = {e.name for e in MAQUINA_EVENTO.estados} | {a.name for a in AccionEvento}
        for ajeno in ('COTIZADO', 'CONTRATADO', 'EN_PREPARACION', 'REALIZADO', 'APROBAR', 'COMPLETAR',
                      'REPETIR_APROBACION', 'SALTAR_ESTADO'):
            self.assertNotIn(ajeno, nombres)
        self.assertEqual({e.value for e in MAQUINA_EVENTO.estados},
                         {'En gestión', 'En organización', 'En ejecución', 'Finalizado', 'Cancelado',
                          'Cerrado sin contratación'})

    def test_el_dominio_no_lee_el_paquete(self):
        for archivo in ('evento.py', 'maquina_estados.py'):
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', archivo), encoding='utf8') as f:
                texto = f.read()
            for ajeno in ('paquete_pia', 'COTIZADO', '.csv'):
                self.assertNotIn(ajeno, texto, archivo)


if __name__ == '__main__':
    unittest.main()
