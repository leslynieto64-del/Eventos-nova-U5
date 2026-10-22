"""Etapa E3F — State Machine de SolicitudCambio.

Comprueba la tabla implementada (`MAQUINA_SOLICITUD_CAMBIO`, a nivel de módulo) y su coherencia con el mapa de dominio,
que cada método propio consulta la máquina antes de modificar el agregado, cada transición válida con sus atributos y
Domain Events, los rechazos con los mensajes actuales y sin mutaciones parciales, la idempotencia existente, que los
métodos heredados de _SolicitudBase (regularización N2, cierre por cancelación y anexo) quedan fuera de la máquina y sin
cambios, el tratamiento de EN_EVALUACION según AR-05 (valor histórico no alcanzable, con compatibilidad separada) y la
conservación del comportamiento anterior contra `referencias/comportamiento_solicitud_cambio_pre_e3f.json`
(capturada sobre la línea base, antes de E3F)."""
import ast
import html
import json
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_maquina_estados_solicitud_cambio import (solicitud, variantes, variantes_historicas, acciones, observar,  # noqa: E402
                                                    capturar_comportamiento_solicitud_cambio, huellas_de_clases,
                                                    serializar, diferencias, RUTA_REFERENCIA_SOLICITUD_CAMBIO,
                                                    RUTA_SOLICITUDES, A10, A3, FECHA_EVENTO, DATOS_MISMO_DIA,
                                                    CONDICIONES)
from apoyo_regularizacion_solicitudes import DECISIONES                                                     # noqa: E402

import domain.solicitudes as mod_solicitudes                                                                # noqa: E402
from domain.solicitudes import (SolicitudCambio as SC, _SolicitudBase, MAQUINA_SOLICITUD_CAMBIO as MAQ,      # noqa: E402
                                MAQUINA_COMPATIBILIDAD_EN_EVALUACION as COMPAT, AccionSolicitudCambio as A)
from domain.maquina_estados import MaquinaEstados, TransicionNoPermitida                                    # noqa: E402
from domain.valores import (ErrorDominio, Decision, CausaCierreSolicitud, ResultadoViabilidad,              # noqa: E402
                            ImpactoModificacion, EstadoSolicitudCambio as ESC)

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EN_TRAMITE = (ESC.REGISTRADA, ESC.DETENIDA_SALDO_VENCIDO, ESC.PENDIENTE_APROBACION_CLIENTE, ESC.PENDIENTE_AUTORIZACION,
              ESC.PENDIENTE_FORMALIZACION, ESC.PENDIENTE_PAGO)
# Tabla derivada de las guardas de v8 + N2 + N6 (antes de E3F) y de la referencia pre-E3F, escrita literalmente.
TABLA_ESPERADA = {
    (ESC.REGISTRADA, A.REGISTRAR_VIABILIDAD_NO_VIABLE): ESC.NO_PROCEDENTE,
    (ESC.REGISTRADA, A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION): ESC.PENDIENTE_APROBACION_CLIENTE,
    (ESC.REGISTRADA, A.REGISTRAR_VIABILIDAD_SIN_APROBACION): ESC.PENDIENTE_FORMALIZACION,
    (ESC.PENDIENTE_APROBACION_CLIENTE, A.REGISTRAR_DECISION_CLIENTE_APROBADA): ESC.PENDIENTE_AUTORIZACION,
    (ESC.PENDIENTE_APROBACION_CLIENTE, A.REGISTRAR_DECISION_CLIENTE_RECHAZADA): ESC.RECHAZADA_CLIENTE,
    (ESC.PENDIENTE_AUTORIZACION, A.REGISTRAR_AUTORIZACION_APROBADA): ESC.PENDIENTE_FORMALIZACION,
    (ESC.PENDIENTE_AUTORIZACION, A.REGISTRAR_AUTORIZACION_RECHAZADA): ESC.NO_AUTORIZADA,
    (ESC.PENDIENTE_FORMALIZACION, A.REGISTRAR_SOLICITUD_PAGO): ESC.PENDIENTE_PAGO,
    (ESC.PENDIENTE_FORMALIZACION, A.CONFIRMAR_SIN_IMPORTES): ESC.CONFIRMADA,        # E3F.1: sin importes por pagar
    (ESC.PENDIENTE_PAGO, A.CONFIRMAR_CON_IMPORTES): ESC.CONFIRMADA,                 # E3F.1: con importes, tras el pago
    (ESC.PENDIENTE_PAGO, A.CERRAR_POR_FALTA_DE_PAGO): ESC.CERRADA_FALTA_PAGO,
}
for _e in EN_TRAMITE:
    TABLA_ESPERADA[(_e, A.CERRAR_POR_INICIO_EVENTO)] = ESC.CERRADA_INICIO_EVENTO
COMPATIBILIDAD_ESPERADA = {
    (ESC.EN_EVALUACION, A.REGISTRAR_VIABILIDAD_NO_VIABLE): ESC.NO_PROCEDENTE,
    (ESC.EN_EVALUACION, A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION): ESC.PENDIENTE_APROBACION_CLIENTE,
    (ESC.EN_EVALUACION, A.REGISTRAR_VIABILIDAD_SIN_APROBACION): ESC.PENDIENTE_FORMALIZACION,
    (ESC.EN_EVALUACION, A.CERRAR_POR_INICIO_EVENTO): ESC.CERRADA_INICIO_EVENTO,
}

# Mensajes existentes (antes de E3F), escritos literalmente para no depender de la tabla.
M_VIABILIDAD = "La viabilidad solo se evalúa en una solicitud registrada."
M_CLIENTE = "La solicitud no espera la aprobación del Cliente."
M_AUTORIZACION = "La autorización requiere la aprobación previa del Cliente (CA-043)."
M_PAGO = "El pago se solicita con el anexo registrado (CA-068)."
M_FALTA_PAGO = "Solo se cierra por falta de pago una solicitud Pendiente de pago."
# E3F.1 (BN-003, SE-006, CA-041, CA-067, CA-068): textos nuevos, escritos literalmente.
M_SIN_IMPORTES = "No se puede solicitar el pago porque el cambio no genera importes por pagar (BN-003, CA-041, CA-067)."
F_SOLICITUD_PAGO = "solicitud de pago comunicada al Cliente (BN-003, CA-067)"
F_EVENTO = ('evento no iniciado', 'evento no cancelado (SE-007)')
VARIANTES = {n: (e, a) for n, e, a in variantes() + variantes_historicas()}

NO_VIABLE = ResultadoViabilidad(False, 'Sin disponibilidad')
VIABLE = ResultadoViabilidad(True)
SIN_IMPACTO = ImpactoModificacion(False, False, False)
SOLO_SERVICIOS = ImpactoModificacion(True, False, False)
COSTOS = ImpactoModificacion(False, True, False)
CONDICIONES_IMPACTO = ImpactoModificacion(False, False, True)


def en(nombre):
    estado, atributos = VARIANTES[nombre]
    return solicitud(estado, **atributos)


def inicial(nombre):
    return observar(en(nombre))


def nombres(eventos):
    return [e.nombre for e in eventos]


# ======================================================================= tabla
class TablaDeTransiciones(unittest.TestCase):
    def test_tabla_implementada(self):
        self.assertEqual({(t.origen, t.accion): t.destino for t in MAQ.transiciones}, TABLA_ESPERADA)
        self.assertEqual(len(MAQ.transiciones), 17)

    def test_sin_repeticiones_idempotentes_en_la_tabla(self):
        """La idempotencia existente (anexo, cierres en estados finales) no pasa por la máquina."""
        self.assertEqual(MAQ.repeticiones_idempotentes, frozenset())

    def test_estados_y_terminales(self):
        self.assertEqual(set(MAQ.estados), set(ESC) - {ESC.EN_EVALUACION})
        self.assertEqual(MAQ.estados_terminales, set(SC.FINALES))
        self.assertEqual(set(EN_TRAMITE), set(ESC) - set(SC.FINALES) - {ESC.EN_EVALUACION})

    def test_acciones_derivadas_de_los_metodos_reales(self):
        for accion in A:
            with self.subTest(accion=accion):
                metodo = accion.value.split(':')[0]
                self.assertTrue(callable(getattr(SC, metodo, None)), metodo)
                self.assertIn(metodo, vars(SC), metodo)                      # método propio, no heredado
        self.assertEqual(MAQ.acciones, set(A))

    def test_lo_heredado_queda_fuera_de_la_maquina(self):
        destinos = {t.destino for t in MAQ.transiciones}
        self.assertNotIn(ESC.CERRADA_EVENTO_CANCELADO, destinos)            # cierre por cancelación (BN-008)
        self.assertNotIn(ESC.DETENIDA_SALDO_VENCIDO, destinos)              # regularización (N2)
        self.assertEqual(MAQ.acciones_desde(ESC.DETENIDA_SALDO_VENCIDO), {A.CERRAR_POR_INICIO_EVENTO})
        for nombre in ('aplicar_decision_regularizacion', 'cerrar_por_cancelacion_evento', 'asociar_anexo', 'pendiente', '_cerrar'):
            with self.subTest(metodo=nombre):
                self.assertNotIn(nombre, vars(SC))
                self.assertIs(getattr(SC, nombre), getattr(_SolicitudBase, nombre))
        self.assertEqual(SC.ESTADOS_REGULARIZABLES, (ESC.REGISTRADA, ESC.DETENIDA_SALDO_VENCIDO))   # N2 sin ampliar

    def test_tabla_a_nivel_de_modulo_sin_atributo_maquina(self):
        self.assertIsInstance(MAQ, MaquinaEstados)
        self.assertIsInstance(COMPAT, MaquinaEstados)
        self.assertFalse(hasattr(SC, 'MAQUINA'))

    def test_coherencia_con_el_mapa_de_dominio(self):
        """Flechas de «Estados de SolicitudCambio» (mapa, página «03»), atravesando la puerta «¿Existen importes por
        pagar?»: todas están en la tabla salvo Registrada → Detenida (regularización, fuera de la máquina). La tabla
        añade los cierres por inicio del evento, que el mapa no dibuja como flechas. El mapa no dibuja «En evaluación»."""
        arbol = ET.parse(os.path.join(RAIZ, 'diagramas', 'dominio', 'mapa-dominio.drawio'))
        pagina = next(d for d in arbol.getroot().iter('diagram') if d.get('name', '').startswith('03'))
        celdas = {c.get('id'): c for c in pagina.iter('mxCell')}

        def texto(c):
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(c.get('value') or ''))).strip().split(' —')[0]

        def geo(c):
            g = c.find('mxGeometry')
            return None if g is None else tuple(float(g.get(k, 0)) for k in ('x', 'y', 'width', 'height'))
        caja = next(geo(c) for c in celdas.values() if texto(c).startswith('Estados de SolicitudCambio'))
        dentro = lambda c: geo(c) and caja[0] <= geo(c)[0] <= caja[0] + caja[2] and caja[1] <= geo(c)[1] <= caja[1] + caja[3]  # noqa: E731
        valores = {e.value for e in ESC}
        salidas = {}
        for c in celdas.values():
            s, d = celdas.get(c.get('source')), celdas.get(c.get('target'))
            if c.get('edge') == '1' and s is not None and d is not None and dentro(s):
                salidas.setdefault(c.get('source'), []).append(d)

        def destinos(nodo):
            for d in salidas.get(nodo.get('id'), []):
                if texto(d) in valores:
                    yield texto(d)
                elif texto(d).startswith('¿'):                               # puerta de decisión
                    yield from destinos(d)
        flechas = {(texto(s), d) for s in celdas.values() if dentro(s) and texto(s) in valores for d in destinos(s)}
        dibujados = {texto(c) for c in celdas.values() if dentro(c) and texto(c) in valores}
        tabla = {(o.value, d.value) for (o, _), d in TABLA_ESPERADA.items()}
        self.assertEqual(flechas - tabla, {(ESC.REGISTRADA.value, ESC.DETENIDA_SALDO_VENCIDO.value)})
        self.assertEqual(tabla - flechas, {(e.value, ESC.CERRADA_INICIO_EVENTO.value) for e in EN_TRAMITE})
        self.assertEqual(dibujados, {e.value for e in MAQ.estados})
        self.assertNotIn(ESC.EN_EVALUACION.value, dibujados)


class ParesNoPermitidos(unittest.TestCase):
    def test_todo_par_fuera_de_la_tabla_se_rechaza(self):
        for estado in ESC:
            for accion in A:
                if (estado, accion) in TABLA_ESPERADA:
                    continue
                with self.subTest(estado=estado, accion=accion):
                    with self.assertRaises(TransicionNoPermitida):
                        MAQ.transitar(estado, accion)

    def test_mensajes_por_accion_son_los_existentes(self):
        esperados = {A.REGISTRAR_VIABILIDAD_NO_VIABLE: M_VIABILIDAD, A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION: M_VIABILIDAD,
                     A.REGISTRAR_VIABILIDAD_SIN_APROBACION: M_VIABILIDAD, A.REGISTRAR_DECISION_CLIENTE_APROBADA: M_CLIENTE,
                     A.REGISTRAR_DECISION_CLIENTE_RECHAZADA: M_CLIENTE, A.REGISTRAR_AUTORIZACION_APROBADA: M_AUTORIZACION,
                     A.REGISTRAR_AUTORIZACION_RECHAZADA: M_AUTORIZACION, A.REGISTRAR_SOLICITUD_PAGO: M_PAGO,
                     A.CERRAR_POR_FALTA_DE_PAGO: M_FALTA_PAGO}
        for maquina in (MAQ, COMPAT):
            for accion, mensaje in esperados.items():
                with self.subTest(maquina=maquina.nombre, accion=accion):
                    self.assertEqual(maquina.mensaje_rechazo(ESC.CONFIRMADA, accion), mensaje)


# ======================================================================= uso real de la máquina
OPERACIONES = {
    A.REGISTRAR_VIABILIDAD_NO_VIABLE: ('REGISTRADA|10d', lambda s: s.registrar_viabilidad(NO_VIABLE, COSTOS, A10)),
    A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION: ('REGISTRADA|10d', lambda s: s.registrar_viabilidad(VIABLE, COSTOS, A10)),
    A.REGISTRAR_VIABILIDAD_SIN_APROBACION: ('REGISTRADA|10d', lambda s: s.registrar_viabilidad(VIABLE, SIN_IMPACTO, A10)),
    A.REGISTRAR_DECISION_CLIENTE_APROBADA: ('PENDIENTE_APROBACION_CLIENTE', lambda s: s.registrar_decision_cliente(Decision('Cliente', True, A10))),
    A.REGISTRAR_DECISION_CLIENTE_RECHAZADA: ('PENDIENTE_APROBACION_CLIENTE', lambda s: s.registrar_decision_cliente(Decision('Cliente', False, A10, 'No'))),
    A.REGISTRAR_AUTORIZACION_APROBADA: ('PENDIENTE_AUTORIZACION', lambda s: s.registrar_autorizacion(Decision('Administración', True, A10))),
    A.REGISTRAR_AUTORIZACION_RECHAZADA: ('PENDIENTE_AUTORIZACION', lambda s: s.registrar_autorizacion(Decision('Administración', False, A10, 'No'))),
    A.REGISTRAR_SOLICITUD_PAGO: ('PENDIENTE_FORMALIZACION|ruta_B|con_anexo', lambda s: s.registrar_solicitud_pago('OB-9')),
    A.CONFIRMAR_CON_IMPORTES: ('PENDIENTE_PAGO', lambda s: s.confirmar(True, False, A10, False)),
    A.CONFIRMAR_SIN_IMPORTES: ('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo', lambda s: s.confirmar(False, False, A10, False)),
    A.CERRAR_POR_FALTA_DE_PAGO: ('PENDIENTE_PAGO', lambda s: s.cerrar_por_falta_de_pago(A10)),
    A.CERRAR_POR_INICIO_EVENTO: ('PENDIENTE_AUTORIZACION', lambda s: s.cerrar_por_inicio_evento(FECHA_EVENTO)),
}


class UsoRealDeLaMaquina(unittest.TestCase):
    @staticmethod
    def _sin(maquina, accion):
        return MaquinaEstados(maquina.estados, [t for t in maquina.transiciones if t.accion != accion],
                              mensajes_rechazo={a: (lambda o, a=a: maquina.mensaje_rechazo(o, a)) for a in A})

    def test_cada_metodo_consulta_la_maquina_antes_de_modificar(self):
        self.assertEqual(set(OPERACIONES), set(A))
        for accion, (variante, llamada) in OPERACIONES.items():
            with self.subTest(accion=accion):
                s = en(variante)
                with mock.patch.object(mod_solicitudes, 'MAQUINA_SOLICITUD_CAMBIO', self._sin(MAQ, accion)):
                    if accion in (A.CONFIRMAR_CON_IMPORTES, A.CONFIRMAR_SIN_IMPORTES):   # confirmar informa el faltante
                        self.assertEqual(llamada(s), ['aprobaciones requeridas'])
                    else:
                        with self.assertRaises(TransicionNoPermitida):
                            llamada(s)
                self.assertEqual(observar(s), inicial(variante))

    def test_accion_elegida_segun_el_resultado(self):
        casos = [(lambda s: s.registrar_viabilidad(NO_VIABLE, SIN_IMPACTO, A10), A.REGISTRAR_VIABILIDAD_NO_VIABLE),
                 (lambda s: s.registrar_viabilidad(VIABLE, COSTOS, A10), A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION),
                 (lambda s: s.registrar_viabilidad(VIABLE, CONDICIONES_IMPACTO, A10), A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION),
                 (lambda s: s.registrar_viabilidad(VIABLE, SOLO_SERVICIOS, A10), A.REGISTRAR_VIABILIDAD_SIN_APROBACION),
                 (lambda s: s.registrar_viabilidad(VIABLE, SIN_IMPACTO, A10), A.REGISTRAR_VIABILIDAD_SIN_APROBACION)]
        for llamada, esperada in casos:
            with self.subTest(esperada=esperada):
                with mock.patch.object(MAQ, 'transitar', wraps=MAQ.transitar) as espia:
                    llamada(en('REGISTRADA|10d'))
                self.assertEqual([c.args[1] for c in espia.call_args_list], [esperada])

    def test_confirmar_consulta_la_tabla_y_no_una_lista_de_estados(self):
        """El faltante de estado lo decide MAQ.permite con la acción que corresponde a importes_por_pagar (E3F.1)."""
        s = en('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo')
        with mock.patch.object(MAQ, 'permite', wraps=MAQ.permite) as espia:
            self.assertEqual(s.confirmar(False, False, A10), [])
        espia.assert_any_call(ESC.PENDIENTE_FORMALIZACION, A.CONFIRMAR_SIN_IMPORTES)
        s = en('PENDIENTE_FORMALIZACION|ruta_B|con_anexo')
        with mock.patch.object(MAQ, 'permite', wraps=MAQ.permite) as espia:
            self.assertEqual(s.confirmar(True, False, A10), [F_SOLICITUD_PAGO])
        espia.assert_any_call(ESC.PENDIENTE_FORMALIZACION, A.CONFIRMAR_CON_IMPORTES)


# ======================================================================= transiciones válidas
class TransicionesValidas(unittest.TestCase):
    def test_tres_rutas_de_viabilidad(self):
        casos = [(NO_VIABLE, COSTOS, 'REGISTRADA|10d', ESC.NO_PROCEDENTE, False),                       # ruta A
                 (VIABLE, COSTOS, 'REGISTRADA|10d', ESC.PENDIENTE_APROBACION_CLIENTE, True),           # ruta B
                 (VIABLE, CONDICIONES_IMPACTO, 'REGISTRADA|10d', ESC.PENDIENTE_APROBACION_CLIENTE, False),
                 (VIABLE, SIN_IMPACTO, 'REGISTRADA|10d', ESC.PENDIENTE_FORMALIZACION, False),          # ruta C
                 (VIABLE, SOLO_SERVICIOS, 'REGISTRADA|10d', ESC.PENDIENTE_FORMALIZACION, False),       # BN-003, CA-038
                 (VIABLE, SIN_IMPACTO, 'REGISTRADA|3d', ESC.PENDIENTE_FORMALIZACION, True),            # cargo tardío
                 (NO_VIABLE, SIN_IMPACTO, 'REGISTRADA|3d', ESC.NO_PROCEDENTE, False)]
        for resultado, impacto, variante, destino, importes in casos:
            with self.subTest(viable=resultado.viable, impacto=impacto, variante=variante):
                s = en(variante)
                s.registrar_viabilidad(resultado, impacto, A10)
                self.assertEqual((s.estado, s.viabilidad, s.impacto, s.importes_por_pagar), (destino, resultado, impacto, importes))
                if destino is ESC.NO_PROCEDENTE:
                    self.assertEqual((s.motivo_cierre.causa, s.motivo_cierre.descripcion, s.motivo_cierre.fecha),
                                     (CausaCierreSolicitud.NO_VIABLE, 'Sin disponibilidad', A10))
                else:
                    self.assertIsNone(s.motivo_cierre)
                ev = s.extraer_eventos()
                self.assertEqual(nombres(ev), ['ViabilidadCambioEvaluada'])
                self.assertEqual((ev[0].agregado_id, ev[0].ocurrido_en, ev[0].viable), (s.id, A10, resultado.viable))

    def test_decision_del_cliente_y_autorizacion(self):
        casos = [('PENDIENTE_APROBACION_CLIENTE', 'registrar_decision_cliente', True, ESC.PENDIENTE_AUTORIZACION, None, 'decision_cliente'),
                 ('PENDIENTE_APROBACION_CLIENTE', 'registrar_decision_cliente', False, ESC.RECHAZADA_CLIENTE,
                  CausaCierreSolicitud.RECHAZO_CLIENTE, 'decision_cliente'),
                 ('PENDIENTE_AUTORIZACION', 'registrar_autorizacion', True, ESC.PENDIENTE_FORMALIZACION, None, 'autorizacion_administracion'),
                 ('PENDIENTE_AUTORIZACION', 'registrar_autorizacion', False, ESC.NO_AUTORIZADA,
                  CausaCierreSolicitud.NO_AUTORIZADA, 'autorizacion_administracion')]
        for variante, metodo, aprobada, destino, causa, atributo in casos:
            with self.subTest(metodo=metodo, aprobada=aprobada):
                s, d = en(variante), Decision('Actor', aprobada, A10, '' if aprobada else 'Motivo')
                getattr(s, metodo)(d)
                self.assertEqual((s.estado, getattr(s, atributo)), (destino, d))
                self.assertEqual(s.motivo_cierre and s.motivo_cierre.causa, causa)
                if causa:
                    self.assertEqual((s.motivo_cierre.descripcion, s.motivo_cierre.fecha), ('Motivo', A10))
                self.assertEqual(s.extraer_eventos(), [])

    def test_solicitud_de_pago_con_anexo(self):                               # CA-068; sin importes: RutaDePagoE3F1
        for variante in ('PENDIENTE_FORMALIZACION|ruta_B|con_anexo', 'PENDIENTE_FORMALIZACION|ruta_C|cargo_tardio|con_anexo'):
            with self.subTest(variante=variante):
                s = en(variante); s.registrar_solicitud_pago('OB-9')
                self.assertEqual((s.estado, s.obligacion_pago_id), (ESC.PENDIENTE_PAGO, 'OB-9'))
                self.assertEqual(s.extraer_eventos(), [])

    def test_confirmar_desde_formalizacion_y_desde_pago(self):               # SE-007, BN-006
        for variante, pago in (('PENDIENTE_PAGO', True), ('PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo', False)):
            with self.subTest(variante=variante):
                s = en(variante)
                self.assertEqual(s.confirmar(pago, False, A10), [])
                self.assertEqual(s.estado, ESC.CONFIRMADA)
                ev = s.extraer_eventos()
                self.assertEqual(nombres(ev), ['CambioConfirmado'])
                self.assertEqual((ev[0].evento_ref, ev[0].descripcion), ('EV-1', s.descripcion))

    def test_confirmar_lleva_la_modificacion_propuesta(self):
        s = solicitud(datos=DATOS_MISMO_DIA, condiciones=CONDICIONES)
        s.registrar_viabilidad(VIABLE, SOLO_SERVICIOS, A10)
        s.asociar_anexo('AX-1')
        self.assertEqual(s.confirmar(False, False, A10), [])
        ev = s.extraer_eventos()[-1]
        self.assertEqual((ev.datos_propuestos, ev.condiciones_propuestas), (DATOS_MISMO_DIA, tuple(CONDICIONES.items())))

    def test_cierres_propios(self):                                           # BN-004, CA-070
        s = en('PENDIENTE_PAGO'); s.cerrar_por_falta_de_pago(A10)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESC.CERRADA_FALTA_PAGO, CausaCierreSolicitud.FALTA_PAGO))
        self.assertEqual(nombres(s.extraer_eventos()), ['SolicitudCambioCerradaPorFaltaDePago'])
        for nombre, estado, _ in variantes():
            if estado in EN_TRAMITE:
                with self.subTest(variante=nombre):
                    s = en(nombre); s.cerrar_por_inicio_evento(FECHA_EVENTO)
                    self.assertEqual((s.estado, s.motivo_cierre.causa, s.motivo_cierre.fecha),
                                     (ESC.CERRADA_INICIO_EVENTO, CausaCierreSolicitud.INICIO_EVENTO, FECHA_EVENTO))
                    self.assertEqual(nombres(s.extraer_eventos()), ['SolicitudCambioCerradaPorInicioEvento'])

    def test_cancelacion_del_evento_heredada(self):                            # BN-008, sin Domain Event
        for nombre, estado, _ in variantes():
            with self.subTest(variante=nombre):
                s = en(nombre)
                cerro = s.cerrar_por_cancelacion_evento(A10)
                self.assertEqual(cerro, estado in EN_TRAMITE)
                self.assertEqual(s.estado, ESC.CERRADA_EVENTO_CANCELADO if cerro else estado)
                self.assertEqual(s.extraer_eventos(), [])

    def test_recorrido_ruta_b_con_pago(self):
        s = solicitud()
        s.registrar_viabilidad(VIABLE, COSTOS, A10)
        s.registrar_decision_cliente(Decision('Cliente', True, A10))
        s.registrar_autorizacion(Decision('Administración', True, A10))
        self.assertTrue(s.puede_registrar_anexo())
        s.asociar_anexo('AX-1')
        self.assertFalse(s.puede_registrar_anexo())
        s.registrar_solicitud_pago('OB-1')
        self.assertEqual(s.confirmar(False, False, A10), ['pago registrado y verificado'])
        self.assertEqual(s.confirmar(True, False, A10), [])
        self.assertEqual(nombres(s.extraer_eventos()), ['ViabilidadCambioEvaluada', 'CambioConfirmado'])
        self.assertFalse(s.pendiente)

    def test_recorrido_ruta_c_sin_importes(self):
        s = solicitud()
        s.registrar_viabilidad(VIABLE, SIN_IMPACTO, A10)
        self.assertEqual(s.confirmar(False, False, A10), ['anexo vinculado al contrato original'])
        s.asociar_anexo('AX-1')
        self.assertEqual(s.confirmar(False, False, A10), [])
        self.assertEqual(s.estado, ESC.CONFIRMADA)


# ======================================================================= rechazos sin efectos
class RechazosSinEfectos(unittest.TestCase):
    def test_metodos_fuera_de_su_estado(self):
        formalizacion_con_anexo = ('PENDIENTE_FORMALIZACION|ruta_B|con_anexo', 'PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo',
                                   'PENDIENTE_FORMALIZACION|ruta_C|cargo_tardio|con_anexo')
        registradas = ('REGISTRADA|10d', 'REGISTRADA|3d', 'REGISTRADA|con_modificacion', 'EN_EVALUACION|10d', 'EN_EVALUACION|3d')
        casos = [(OPERACIONES[A.REGISTRAR_VIABILIDAD_NO_VIABLE][1], M_VIABILIDAD, registradas),
                 (OPERACIONES[A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION][1], M_VIABILIDAD, registradas),
                 (OPERACIONES[A.REGISTRAR_VIABILIDAD_SIN_APROBACION][1], M_VIABILIDAD, registradas),
                 (OPERACIONES[A.REGISTRAR_DECISION_CLIENTE_APROBADA][1], M_CLIENTE, ('PENDIENTE_APROBACION_CLIENTE',)),
                 (OPERACIONES[A.REGISTRAR_DECISION_CLIENTE_RECHAZADA][1], M_CLIENTE, ('PENDIENTE_APROBACION_CLIENTE',)),
                 (OPERACIONES[A.REGISTRAR_AUTORIZACION_APROBADA][1], M_AUTORIZACION, ('PENDIENTE_AUTORIZACION',)),
                 (OPERACIONES[A.REGISTRAR_AUTORIZACION_RECHAZADA][1], M_AUTORIZACION, ('PENDIENTE_AUTORIZACION',)),
                 (OPERACIONES[A.REGISTRAR_SOLICITUD_PAGO][1], M_PAGO, formalizacion_con_anexo),
                 (OPERACIONES[A.CERRAR_POR_FALTA_DE_PAGO][1], M_FALTA_PAGO, ('PENDIENTE_PAGO',))]
        for llamada, mensaje, validos in casos:
            for nombre in VARIANTES:
                if nombre in validos:
                    continue
                with self.subTest(mensaje=mensaje, variante=nombre):
                    s = en(nombre)
                    with self.assertRaises(ErrorDominio) as ctx:
                        llamada(s)
                    self.assertEqual(str(ctx.exception), mensaje)
                    self.assertEqual(observar(s), inicial(nombre))           # sin mutaciones parciales ni eventos

    def test_rechazo_de_la_maquina_es_error_dominio(self):
        s = en('DETENIDA_SALDO_VENCIDO|antes=REGISTRADA')
        with self.assertRaises(TransicionNoPermitida) as ctx:
            s.registrar_viabilidad(VIABLE, COSTOS, A10)
        self.assertIsInstance(ctx.exception, ErrorDominio)
        self.assertEqual((ctx.exception.origen, ctx.exception.accion),
                         (ESC.DETENIDA_SALDO_VENCIDO, A.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION))

    def test_solicitud_de_pago_sin_anexo_no_modifica(self):                   # CA-068: estado válido, anexo ausente
        for variante in ('PENDIENTE_FORMALIZACION|ruta_B|sin_anexo', 'PENDIENTE_FORMALIZACION|ruta_C|sin_importes|sin_anexo'):
            with self.subTest(variante=variante):
                s = en(variante)
                with self.assertRaises(ErrorDominio) as ctx:
                    s.registrar_solicitud_pago('OB-9')
                self.assertEqual(str(ctx.exception), M_PAGO)
                self.assertNotIsInstance(ctx.exception, TransicionNoPermitida)
                self.assertEqual(observar(s), inicial(variante))

    def test_confirmar_con_faltantes_no_cambia_nada(self):
        casos = [('PENDIENTE_PAGO', (False, True, A10, True),
                  ['evento no iniciado', 'evento no cancelado (SE-007)', 'pago registrado y verificado']),
                 ('PENDIENTE_FORMALIZACION|ruta_B|sin_anexo', (True, False, A10),
                  [F_SOLICITUD_PAGO, 'anexo vinculado al contrato original']),                 # E3F.1
                 ('PENDIENTE_AUTORIZACION', (True, False, A10),
                  ['aprobaciones requeridas', 'anexo vinculado al contrato original']),
                 ('CONFIRMADA', (True, False, A10), ['aprobaciones requeridas'])]
        for variante, argumentos, faltan in casos:
            with self.subTest(variante=variante):
                s = en(variante)
                self.assertEqual(s.confirmar(*argumentos), faltan)
                self.assertEqual(observar(s), inicial(variante))

    def test_cierre_por_inicio_en_estados_finales_sin_efecto(self):
        for nombre, estado, _ in variantes():
            if estado in SC.FINALES:
                with self.subTest(variante=nombre):
                    s = en(nombre)
                    with mock.patch.object(MAQ, 'transitar', wraps=MAQ.transitar) as espia:
                        self.assertIsNone(s.cerrar_por_inicio_evento(FECHA_EVENTO))
                    espia.assert_not_called()
                    self.assertEqual(observar(s), inicial(nombre))


# ======================================================================= idempotencia existente
class Idempotencia(unittest.TestCase):
    def test_asociar_el_mismo_anexo(self):
        s = en('PENDIENTE_FORMALIZACION|ruta_B|sin_anexo')
        s.asociar_anexo('AX-1'); s.asociar_anexo('AX-1')
        self.assertEqual((s.anexo_id, s.estado), ('AX-1', ESC.PENDIENTE_FORMALIZACION))
        with self.assertRaises(ErrorDominio) as ctx:
            s.asociar_anexo('AX-2')
        self.assertEqual(str(ctx.exception), "La solicitud ya tiene otro anexo asociado.")
        self.assertEqual(s.anexo_id, 'AX-1')

    def test_cierres_repetidos(self):
        s = en('PENDIENTE_PAGO')
        s.cerrar_por_inicio_evento(FECHA_EVENTO)
        primero = observar(s)
        s.cerrar_por_inicio_evento(A10)
        self.assertFalse(s.cerrar_por_cancelacion_evento(A10))
        self.assertEqual(observar(s), {**primero, 'eventos': []})


# ======================================================================= regularización N2
class RegularizacionN2(unittest.TestCase):
    def test_detener_continuar_y_no_procede(self):
        s = en('REGISTRADA|10d')
        self.assertFalse(s.aplicar_decision_regularizacion(DECISIONES['detener_por_saldo'], A10, ESC.NO_PROCEDENTE))
        self.assertEqual((s.estado, s._estado_antes_de_detener), (ESC.DETENIDA_SALDO_VENCIDO, ESC.REGISTRADA))
        with self.assertRaises(ErrorDominio):                                  # detenida: no se evalúa la viabilidad
            s.registrar_viabilidad(VIABLE, COSTOS, A10)
        self.assertTrue(s.aplicar_decision_regularizacion(DECISIONES['continuar'], A10, ESC.NO_PROCEDENTE))
        self.assertEqual(s.estado, ESC.REGISTRADA)
        s.registrar_viabilidad(VIABLE, COSTOS, A10)                            # retomada, sigue el flujo normal
        self.assertEqual(s.estado, ESC.PENDIENTE_APROBACION_CLIENTE)
        causas = {'no_procede_condicion_temporal': CausaCierreSolicitud.PLAZO_INSUFICIENTE,
                  'no_procede_evento_cancelado': CausaCierreSolicitud.EVENTO_CANCELADO,
                  'no_procede_evento_iniciado_cambio': CausaCierreSolicitud.INICIO_EVENTO}       # E3F.1 (N3)
        for decision, causa in causas.items():
            for variante in ('REGISTRADA|10d', 'DETENIDA_SALDO_VENCIDO|antes=REGISTRADA'):
                with self.subTest(decision=decision, variante=variante):
                    s = en(variante)
                    self.assertFalse(s.aplicar_decision_regularizacion(DECISIONES[decision], A10, ESC.NO_PROCEDENTE))
                    self.assertEqual((s.estado, s.motivo_cierre.causa), (ESC.NO_PROCEDENTE, causa))

    def test_fuera_de_registrada_y_detenida_sin_efecto(self):
        for nombre, estado, _ in variantes() + variantes_historicas():
            if estado in SC.ESTADOS_REGULARIZABLES:
                continue
            for decision, d in DECISIONES.items():
                with self.subTest(variante=nombre, decision=decision):
                    s = en(nombre)
                    self.assertEqual(s.aplicar_decision_regularizacion(d, A10, ESC.NO_PROCEDENTE), d.puede_continuar)
                    self.assertEqual(observar(s), inicial(nombre))


# ======================================================================= EN_EVALUACION (AR-05)
class EnEvaluacionAR05(unittest.TestCase):
    def test_no_es_estado_del_flujo_normal(self):
        self.assertNotIn(ESC.EN_EVALUACION, MAQ.estados)
        self.assertNotIn(ESC.EN_EVALUACION, SC.FINALES)
        self.assertIn(ESC.EN_EVALUACION, set(ESC))                             # el valor del enum se conserva
        self.assertFalse(MAQ.acciones_desde(ESC.EN_EVALUACION))

    def test_ninguna_transicion_entra_en_en_evaluacion(self):
        for maquina in (MAQ, COMPAT):
            with self.subTest(maquina=maquina.nombre):
                self.assertNotIn(ESC.EN_EVALUACION, {t.destino for t in maquina.transiciones})

    def test_compatibilidad_separada_y_solo_de_salida(self):
        self.assertEqual({(t.origen, t.accion): t.destino for t in COMPAT.transiciones}, COMPATIBILIDAD_ESPERADA)
        self.assertEqual({t.origen for t in COMPAT.transiciones}, {ESC.EN_EVALUACION})
        self.assertEqual(COMPAT.repeticiones_idempotentes, frozenset())
        self.assertFalse(set(COMPATIBILIDAD_ESPERADA) & set(TABLA_ESPERADA))
        self.assertIs(mod_solicitudes._maquina_solicitud_cambio(ESC.EN_EVALUACION), COMPAT)
        for estado in set(ESC) - {ESC.EN_EVALUACION}:
            self.assertIs(mod_solicitudes._maquina_solicitud_cambio(estado), MAQ)

    def test_ningun_metodo_asigna_en_evaluacion(self):
        """En el código, EN_EVALUACION solo aparece como origen de la compatibilidad y en el selector de máquina."""
        with open(RUTA_SOLICITUDES, encoding='utf-8') as f:
            arbol = ast.parse(f.read())
        usos = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Attribute) and nodo.attr == 'EN_EVALUACION':
                usos.append(nodo.lineno)
            if isinstance(nodo, ast.Call) and getattr(nodo.func, 'id', None) == 'Transicion' and len(nodo.args) == 3:
                self.assertNotEqual(getattr(nodo.args[2], 'attr', None), 'EN_EVALUACION')
            if isinstance(nodo, ast.Assign):
                for destino in nodo.targets:
                    if getattr(destino, 'attr', None) == 'estado':
                        self.assertNotEqual(getattr(nodo.value, 'attr', None), 'EN_EVALUACION')
        self.assertEqual(len(usos), 6)              # exclusión en los estados de MAQ, 4 orígenes de COMPAT y el selector

    def test_ningun_recorrido_normal_llega_a_en_evaluacion(self):
        self.assertEqual(solicitud().estado, ESC.REGISTRADA)
        for clave, caso in capturar_comportamiento_solicitud_cambio()['comportamiento'].items():
            self.assertNotEqual(caso['estado'], ESC.EN_EVALUACION.name, clave)

    def test_operaciones_historicas_conservadas(self):
        s = en('EN_EVALUACION|10d'); s.registrar_viabilidad(VIABLE, COSTOS, A10)
        self.assertEqual(s.estado, ESC.PENDIENTE_APROBACION_CLIENTE)
        s = en('EN_EVALUACION|3d'); s.registrar_viabilidad(VIABLE, SIN_IMPACTO, A10)
        self.assertEqual((s.estado, s.importes_por_pagar), (ESC.PENDIENTE_FORMALIZACION, True))
        s = en('EN_EVALUACION|10d'); s.registrar_viabilidad(NO_VIABLE, SIN_IMPACTO, A10)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESC.NO_PROCEDENTE, CausaCierreSolicitud.NO_VIABLE))
        s = en('EN_EVALUACION|10d'); s.cerrar_por_inicio_evento(FECHA_EVENTO)
        self.assertEqual(nombres(s.extraer_eventos()), ['SolicitudCambioCerradaPorInicioEvento'])
        s = en('EN_EVALUACION|10d')
        self.assertTrue(s.cerrar_por_cancelacion_evento(A10))
        self.assertEqual(s.estado, ESC.CERRADA_EVENTO_CANCELADO)

    def test_compatibilidad_pasa_por_su_propia_maquina(self):
        for accion in [a for _, a in COMPATIBILIDAD_ESPERADA]:
            variante, llamada = OPERACIONES[accion]
            with self.subTest(accion=accion):
                s = en('EN_EVALUACION|10d')
                with mock.patch.object(mod_solicitudes, 'MAQUINA_COMPATIBILIDAD_EN_EVALUACION',
                                       UsoRealDeLaMaquina._sin(COMPAT, accion)):
                    with self.assertRaises(TransicionNoPermitida):
                        llamada(s)
                self.assertEqual(observar(s), inicial('EN_EVALUACION|10d'))


# ======================================================================= conservación del comportamiento
# Diferencias intencionales de E3F.1 respecto a la referencia pre-E3F (que no se modifica). Son las únicas: cualquier
# otro caso debe seguir idéntico.
_RAMAS_CONFIRMAR = [f'confirmar(pago={p}, iniciado={i}, cancelado={c})' for p in (False, True) for i in (False, True)
                    for c in (False, True)]
DIFERENCIAS_E3F1 = {
    # A — CA-070, GL-032, BPMN SP-03 (evento de borde «Evento iniciado»): causa «Inicio del evento» (hallazgo N3).
    'causa_inicio_evento': {f'{v} | aplicar_decision_regularizacion(no_procede_evento_iniciado_cambio)'
                            for v in ('REGISTRADA|10d', 'REGISTRADA|3d', 'REGISTRADA|con_modificacion',
                                      'DETENIDA_SALDO_VENCIDO|antes=REGISTRADA')},
    # B — BN-003, SE-006, CA-067, mapa («¿Existen importes por pagar?»): sin importes no se solicita pago.
    'solicitud_pago_sin_importes': {'PENDIENTE_FORMALIZACION|ruta_C|sin_importes|con_anexo | registrar_solicitud_pago(OB-9)'},
    # B — BN-003, CA-041, CA-067, CA-068: con importes no se confirma desde Pendiente de formalización.
    'confirmar_con_importes_sin_solicitud_de_pago': {
        f'{v} | {r}' for v in ('PENDIENTE_FORMALIZACION|ruta_B|sin_anexo', 'PENDIENTE_FORMALIZACION|ruta_B|con_anexo',
                               'PENDIENTE_FORMALIZACION|ruta_C|cargo_tardio|con_anexo') for r in _RAMAS_CONFIRMAR},
}


def esperado_e3f1(bloque, clave, referencia):
    """El resultado que E3F.1 exige para un caso de la referencia, derivado de lo que la referencia registraba."""
    caso = referencia[bloque][clave]
    if bloque != 'comportamiento':
        return caso
    inicial_ = referencia[bloque][clave.split(' | ')[0] + ' | (inicial)']
    if clave in DIFERENCIAS_E3F1['causa_inicio_evento']:
        assert caso['motivo_cierre']['causa'] == CausaCierreSolicitud.EVENTO_CANCELADO.name
        return {**caso, 'motivo_cierre': {**caso['motivo_cierre'], 'causa': CausaCierreSolicitud.INICIO_EVENTO.name}}
    if clave in DIFERENCIAS_E3F1['solicitud_pago_sin_importes']:
        assert caso['estado'] == ESC.PENDIENTE_PAGO.name               # antes generaba una obligación innecesaria
        return {'error': M_SIN_IMPORTES, **inicial_}
    if clave in DIFERENCIAS_E3F1['confirmar_con_importes_sin_solicitud_de_pago']:
        faltan = list(caso['devuelve'])
        posicion = sum(1 for f in faltan if f in F_EVENTO)              # mismo lugar que el faltante de estado
        return {'devuelve': faltan[:posicion] + [F_SOLICITUD_PAGO] + faltan[posicion:], **inicial_}
    return caso


class ConservacionDelComportamiento(unittest.TestCase):
    """Referencia capturada antes de E3F (`comportamiento_solicitud_cambio_pre_e3f.json`, sin modificar): constructor
    (5 casos), comportamiento (20 variantes × 29 = 580) e histórico de EN_EVALUACION (2 × 29 = 58). Todo es idéntico
    salvo los 29 casos de DIFERENCIAS_E3F1, cuyo resultado exacto se deriva de la referencia. La huella de
    SustitucionProveedor no cambia; la de _SolicitudBase cambia por E3F.1 y se protege con su nuevo valor; la de
    SolicitudCambio queda como dato histórico."""
    BLOQUES = ('constructor', 'comportamiento', 'historico_en_evaluacion')
    HUELLAS_PROTEGIDAS = ('_SolicitudBase', 'SustitucionProveedor')
    HUELLAS_DESDE_E3F1 = {'_SolicitudBase': 'e9947bcb48d349066310697f00a5aa1a07bb0ffa64611074751f2cc07c25500b'}

    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA_SOLICITUD_CAMBIO, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = json.loads(serializar(capturar_comportamiento_solicitud_cambio()))

    def test_estructura_y_cobertura(self):
        self.assertEqual(set(self.referencia), {'huellas', *self.BLOQUES})
        self.assertEqual(set(self.actual), set(self.referencia))
        self.assertEqual({b: len(self.referencia[b]) for b in self.BLOQUES},
                         {'constructor': 5, 'comportamiento': 580, 'historico_en_evaluacion': 58})
        self.assertEqual(len(self.referencia['comportamiento']), len(variantes()) * (1 + len(acciones())))
        self.assertEqual(len(self.referencia['historico_en_evaluacion']), len(variantes_historicas()) * (1 + len(acciones())))

    def test_solo_cambian_los_casos_de_e3f1(self):
        todos = set().union(*DIFERENCIAS_E3F1.values())
        self.assertEqual(len(todos), 29)
        self.assertTrue(todos <= set(self.referencia['comportamiento']))
        distintos = {k for k in self.referencia['comportamiento']
                     if self.actual['comportamiento'][k] != self.referencia['comportamiento'][k]}
        self.assertEqual(distintos, todos)
        for bloque in ('constructor', 'historico_en_evaluacion'):
            with self.subTest(bloque=bloque):                          # EN_EVALUACION conserva su comportamiento
                self.assertEqual(diferencias(self.referencia[bloque], self.actual[bloque]), [])

    def test_bloques_identicos_salvo_e3f1(self):
        for bloque in self.BLOQUES:
            for clave in self.referencia[bloque]:
                with self.subTest(bloque=bloque, caso=clave):
                    self.assertEqual(self.actual[bloque][clave], esperado_e3f1(bloque, clave, self.referencia))

    def test_huellas_protegidas(self):
        for clase in self.HUELLAS_PROTEGIDAS:
            with self.subTest(clase=clase):
                esperada = self.HUELLAS_DESDE_E3F1.get(clase, self.referencia['huellas'][clase])
                self.assertEqual(huellas_de_clases()[clase], esperada)
        self.assertEqual(self.referencia['huellas']['_SolicitudBase'],
                         '4b9632f58bf2a48a79cead87ea7c931b82f9aa70ba1bef517b3bedfef174a2b6')   # histórica, sin cambios

    def test_huella_de_solicitud_cambio_es_dato_historico(self):
        """Solo se comprueba que la referencia la conserva; no se compara con la clase actual."""
        self.assertEqual(self.referencia['huellas']['SolicitudCambio'],
                         '964ddf6da57e3b46fe281cfd4e779d8a0f3ed631e9786040efdb9786d8257a59')


class AislamientoDelPaqueteCSV(unittest.TestCase):
    def test_estados_y_acciones_son_los_de_eventos_nova(self):
        nombres_ = {e.name for e in MAQ.estados} | {a.name for a in A}
        for ajeno in ('COTIZADO', 'CONTRATADO', 'EN_PREPARACION', 'REALIZADO', 'CANCELADO', 'APROBAR', 'COMPLETAR'):
            self.assertNotIn(ajeno, nombres_)


if __name__ == '__main__':
    unittest.main()
