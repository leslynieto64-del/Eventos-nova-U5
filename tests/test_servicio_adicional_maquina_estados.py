"""Etapa E3E — State Machine de SolicitudServicioAdicional.

Comprueba la tabla implementada (`MAQUINA_SERVICIO_ADICIONAL`, a nivel de módulo) y su coherencia con el mapa de
dominio, que cada método propio consulta la máquina antes de modificar el agregado, cada transición válida con sus
atributos y Domain Events, los rechazos con los mensajes actuales y sin efectos, las dos operaciones válidas que no
cambian el estado, la conservación de la elegibilidad, que los métodos heredados de _SolicitudBase (regularización N2,
cierre por cancelación y anexo) quedan fuera de la máquina y sin cambios, y la conservación del comportamiento anterior
(referencia capturada sobre 5e046c6). N6 queda fuera: no hay pruebas de registro con el Evento iniciado o cancelado."""
import html
import json
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_maquina_estados_servicio_adicional import (solicitud, variantes, acciones, observar, huellas_de_clases,   # noqa: E402
                                                      capturar_comportamiento_servicio_adicional,
                                                      RUTA_REFERENCIA_SERVICIO_ADICIONAL, A10, A4, FECHA_EVENTO, T,
                                                      CON_COSTO, SIN_COSTO, SIN_PROVEEDOR)
from apoyo_regularizacion_solicitudes import (capturar_comportamiento_regularizacion,                        # noqa: E402
                                              RUTA_REFERENCIA_REGULARIZACION)

import domain.solicitudes as mod_solicitudes                                                                  # noqa: E402
from domain.solicitudes import (SolicitudServicioAdicional as SA, SolicitudCambio, SustitucionProveedor,      # noqa: E402
                                _SolicitudBase, MAQUINA_SERVICIO_ADICIONAL as MAQ, AccionServicioAdicional as A)
from domain.maquina_estados import MaquinaEstados, TransicionNoPermitida                                      # noqa: E402
from domain.valores import (ErrorDominio, Decision, CausaCierreSolicitud,                                     # noqa: E402
                            EstadoSolicitudServicioAdicional as ESA)

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EN_TRAMITE = (ESA.REGISTRADA, ESA.DETENIDA_SALDO_VENCIDO, ESA.EN_BUSQUEDA_PROVEEDOR, ESA.PENDIENTE_APROBACION_CLIENTE,
              ESA.PENDIENTE_AUTORIZACION, ESA.AUTORIZADA, ESA.PENDIENTE_PAGO)
TABLA_ESPERADA = {
    (ESA.REGISTRADA, A.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR): ESA.PENDIENTE_APROBACION_CLIENTE,
    (ESA.EN_BUSQUEDA_PROVEEDOR, A.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR): ESA.PENDIENTE_APROBACION_CLIENTE,
    (ESA.REGISTRADA, A.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR): ESA.EN_BUSQUEDA_PROVEEDOR,
    (ESA.REGISTRADA, A.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO): ESA.NO_PROCEDENTE,
    (ESA.EN_BUSQUEDA_PROVEEDOR, A.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO): ESA.NO_PROCEDENTE,
    (ESA.EN_BUSQUEDA_PROVEEDOR, A.REGISTRAR_RESPUESTA_ESPERA_NO_ESPERA): ESA.NO_SE_REALIZARA,
    (ESA.EN_BUSQUEDA_PROVEEDOR, A.REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO): ESA.NO_PROCEDENTE,
    (ESA.PENDIENTE_APROBACION_CLIENTE, A.REGISTRAR_DECISION_CLIENTE_APROBADA): ESA.PENDIENTE_AUTORIZACION,
    (ESA.PENDIENTE_APROBACION_CLIENTE, A.REGISTRAR_DECISION_CLIENTE_RECHAZADA): ESA.NO_APROBADA,
    (ESA.PENDIENTE_AUTORIZACION, A.REGISTRAR_AUTORIZACION_APROBADA): ESA.AUTORIZADA,
    (ESA.PENDIENTE_AUTORIZACION, A.REGISTRAR_AUTORIZACION_RECHAZADA): ESA.NO_AUTORIZADA,
    (ESA.AUTORIZADA, A.REGISTRAR_SOLICITUD_PAGO): ESA.PENDIENTE_PAGO,
    (ESA.PENDIENTE_PAGO, A.CONFIRMAR): ESA.CONFIRMADA,
    (ESA.PENDIENTE_PAGO, A.CERRAR_POR_FALTA_DE_PAGO): ESA.CERRADA_FALTA_PAGO,
}
for _e in EN_TRAMITE:
    TABLA_ESPERADA[(_e, A.CERRAR_POR_INICIO_EVENTO)] = ESA.CERRADA_INICIO_EVENTO

# Mensajes existentes (v8), escritos literalmente para no depender de la tabla.
M_DISPONIBILIDAD = "La disponibilidad se registra durante la búsqueda de proveedor."
M_ESPERA = "No hay una búsqueda en curso."
M_CLIENTE = "La solicitud no espera la aprobación del Cliente."
M_AUTORIZACION = "La autorización es posterior a la aprobación del Cliente (CA-081)."
M_PAGO = "El anexo se registra antes de comunicar la solicitud de pago (CA-082)."
M_FALTA_PAGO = "Solo se cierra por falta de pago una solicitud Pendiente de pago."
M_CA075 = "Antes de continuar deben determinarse el costo y las condiciones del servicio (CA-075)."
VARIANTES = {n: (e, a) for n, e, a in variantes()}


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
        self.assertEqual(len(MAQ.transiciones), 21)

    def test_una_sola_repeticion_idempotente(self):
        self.assertEqual(MAQ.repeticiones_idempotentes,
                         {(ESA.EN_BUSQUEDA_PROVEEDOR, A.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR)})

    def test_estados_y_terminales(self):
        self.assertEqual(set(MAQ.estados), set(ESA))
        self.assertEqual(MAQ.estados_terminales, set(SA.FINALES))
        self.assertEqual(set(EN_TRAMITE), set(ESA) - set(SA.FINALES))

    def test_acciones_derivadas_de_los_metodos_reales(self):
        for accion in A:
            with self.subTest(accion=accion):
                metodo = accion.value.split(':')[0]
                self.assertTrue(callable(getattr(SA, metodo, None)), metodo)
                self.assertIn(metodo, vars(SA), metodo)                     # método propio, no heredado

    def test_lo_heredado_queda_fuera_de_la_maquina(self):
        destinos = {t.destino for t in MAQ.transiciones}
        self.assertNotIn(ESA.CERRADA_EVENTO_CANCELADO, destinos)            # cierre por cancelación (BN-008)
        self.assertNotIn(ESA.DETENIDA_SALDO_VENCIDO, destinos)              # regularización (N2)
        self.assertEqual(MAQ.acciones_desde(ESA.DETENIDA_SALDO_VENCIDO), {A.CERRAR_POR_INICIO_EVENTO})
        for nombre in ('aplicar_decision_regularizacion', 'cerrar_por_cancelacion_evento', 'asociar_anexo', 'pendiente', '_cerrar'):
            with self.subTest(metodo=nombre):
                self.assertNotIn(nombre, vars(SA))
                self.assertIs(getattr(SA, nombre), getattr(_SolicitudBase, nombre))
        self.assertEqual(SA.ESTADOS_REGULARIZABLES, (ESA.REGISTRADA, ESA.DETENIDA_SALDO_VENCIDO))   # N2 sin ampliar

    def test_tabla_a_nivel_de_modulo_sin_atributo_maquina(self):
        self.assertIsInstance(MAQ, MaquinaEstados)
        for clase in (SA, SolicitudCambio):
            self.assertFalse(hasattr(clase, 'MAQUINA'), clase.__name__)
        self.assertFalse(hasattr(SustitucionProveedor, 'MAQUINA_SERVICIO_ADICIONAL'))

    def test_coherencia_con_el_mapa_de_dominio(self):
        """Flechas de «Estados de SolicitudServicioAdicional» (mapa, página «03»): todas están en la tabla salvo
        Registrada → Detenida (regularización, fuera de la máquina). La tabla añade Registrada → Pendiente de aprobación
        (AR-06, posible discrepancia documental) y los cierres por inicio del evento (CA-071)."""
        arbol = ET.parse(os.path.join(RAIZ, 'diagramas', 'dominio', 'mapa-dominio.drawio'))
        pagina = next(d for d in arbol.getroot().iter('diagram') if d.get('name', '').startswith('03'))
        celdas = {c.get('id'): c for c in pagina.iter('mxCell')}

        def texto(c):
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(c.get('value') or ''))).strip().split(' —')[0]

        def geo(c):
            g = c.find('mxGeometry')
            return None if g is None else tuple(float(g.get(k, 0)) for k in ('x', 'y', 'width', 'height'))
        caja = next(geo(c) for c in celdas.values() if texto(c).startswith('Estados de SolicitudServicioAdicional'))
        dentro = lambda c: geo(c) and caja[0] <= geo(c)[0] <= caja[0] + caja[2] and caja[1] <= geo(c)[1] <= caja[1] + caja[3]  # noqa: E731
        valores = {e.value for e in ESA}
        flechas = set()
        for c in celdas.values():
            s, d = celdas.get(c.get('source')), celdas.get(c.get('target'))
            if c.get('edge') == '1' and s is not None and d is not None and dentro(s) and texto(s) in valores and texto(d) in valores:
                flechas.add((texto(s), texto(d)))
        tabla = {(o.value, d.value) for (o, _), d in TABLA_ESPERADA.items()}
        self.assertEqual(flechas - tabla, {(ESA.REGISTRADA.value, ESA.DETENIDA_SALDO_VENCIDO.value)})
        self.assertEqual(tabla - flechas, {(ESA.REGISTRADA.value, ESA.PENDIENTE_APROBACION_CLIENTE.value)}
                         | {(e.value, ESA.CERRADA_INICIO_EVENTO.value) for e in EN_TRAMITE})


class ParesNoPermitidos(unittest.TestCase):
    def test_todo_par_fuera_de_la_tabla_se_rechaza(self):
        for estado in ESA:
            for accion in A:
                if (estado, accion) in TABLA_ESPERADA or MAQ.es_repeticion(estado, accion):
                    continue
                with self.subTest(estado=estado, accion=accion):
                    with self.assertRaises(TransicionNoPermitida):
                        MAQ.transitar(estado, accion)

    def test_mensajes_por_accion_son_los_existentes(self):
        esperados = {A.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR: M_DISPONIBILIDAD, A.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR: M_DISPONIBILIDAD,
                     A.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO: M_DISPONIBILIDAD, A.REGISTRAR_RESPUESTA_ESPERA_NO_ESPERA: M_ESPERA,
                     A.REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO: M_ESPERA, A.REGISTRAR_DECISION_CLIENTE_APROBADA: M_CLIENTE,
                     A.REGISTRAR_DECISION_CLIENTE_RECHAZADA: M_CLIENTE, A.REGISTRAR_AUTORIZACION_APROBADA: M_AUTORIZACION,
                     A.REGISTRAR_AUTORIZACION_RECHAZADA: M_AUTORIZACION, A.REGISTRAR_SOLICITUD_PAGO: M_PAGO,
                     A.CERRAR_POR_FALTA_DE_PAGO: M_FALTA_PAGO}
        for accion, mensaje in esperados.items():
            with self.subTest(accion=accion):
                self.assertEqual(MAQ.mensaje_rechazo(ESA.CONFIRMADA, accion), mensaje)


# ======================================================================= uso real de la máquina
OPERACIONES = {
    A.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR: ('REGISTRADA', lambda s: s.registrar_disponibilidad(CON_COSTO, A10)),
    A.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR: ('REGISTRADA', lambda s: s.registrar_disponibilidad(SIN_PROVEEDOR, A10)),
    A.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO: ('EN_BUSQUEDA_PROVEEDOR', lambda s: s.registrar_disponibilidad(CON_COSTO, A4)),
    A.REGISTRAR_RESPUESTA_ESPERA_NO_ESPERA: ('EN_BUSQUEDA_PROVEEDOR', lambda s: s.registrar_respuesta_espera(False, A10)),
    A.REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO: ('EN_BUSQUEDA_PROVEEDOR', lambda s: s.registrar_respuesta_espera(True, A4)),
    A.REGISTRAR_DECISION_CLIENTE_APROBADA: ('PENDIENTE_APROBACION_CLIENTE', lambda s: s.registrar_decision_cliente(Decision('Cliente', True, A10))),
    A.REGISTRAR_DECISION_CLIENTE_RECHAZADA: ('PENDIENTE_APROBACION_CLIENTE', lambda s: s.registrar_decision_cliente(Decision('Cliente', False, A10, 'No'))),
    A.REGISTRAR_AUTORIZACION_APROBADA: ('PENDIENTE_AUTORIZACION', lambda s: s.registrar_autorizacion(Decision('Administración', True, A10))),
    A.REGISTRAR_AUTORIZACION_RECHAZADA: ('PENDIENTE_AUTORIZACION', lambda s: s.registrar_autorizacion(Decision('Administración', False, A10, 'No'))),
    A.REGISTRAR_SOLICITUD_PAGO: ('AUTORIZADA|con_anexo', lambda s: s.registrar_solicitud_pago('OB-9')),
    A.CONFIRMAR: ('PENDIENTE_PAGO', lambda s: s.confirmar(True, False, A10, False)),
    A.CERRAR_POR_FALTA_DE_PAGO: ('PENDIENTE_PAGO', lambda s: s.cerrar_por_falta_de_pago(A10)),
    A.CERRAR_POR_INICIO_EVENTO: ('AUTORIZADA|con_anexo', lambda s: s.cerrar_por_inicio_evento(FECHA_EVENTO)),
}


class UsoRealDeLaMaquina(unittest.TestCase):
    def _sin(self, accion):
        return MaquinaEstados(ESA, [t for t in MAQ.transiciones if t.accion != accion],
                              repeticiones_idempotentes=MAQ.repeticiones_idempotentes)

    def test_cada_metodo_consulta_la_maquina_antes_de_modificar(self):
        self.assertEqual(set(OPERACIONES), set(A))
        for accion, (variante, llamada) in OPERACIONES.items():
            with self.subTest(accion=accion):
                s = en(variante)
                with mock.patch.object(mod_solicitudes, 'MAQUINA_SERVICIO_ADICIONAL', self._sin(accion)):
                    with self.assertRaises(TransicionNoPermitida):
                        llamada(s)
                self.assertEqual(observar(s), inicial(variante))

    def test_accion_elegida_segun_el_resultado(self):
        casos = [('REGISTRADA', OPERACIONES[A.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR][1], A.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR),
                 ('REGISTRADA', lambda s: s.registrar_disponibilidad(SIN_PROVEEDOR, A4), A.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO),
                 ('REGISTRADA', lambda s: s.registrar_disponibilidad(SIN_COSTO, A4), A.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO),
                 ('EN_BUSQUEDA_PROVEEDOR', lambda s: s.registrar_respuesta_espera(True, A4), A.REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO)]
        for variante, llamada, esperada in casos:
            with self.subTest(esperada=esperada):
                with mock.patch.object(MAQ, 'transitar', wraps=MAQ.transitar) as espia:
                    llamada(en(variante))
                self.assertEqual([c.args[1] for c in espia.call_args_list], [esperada])


# ======================================================================= transiciones válidas
class TransicionesValidas(unittest.TestCase):
    def test_disponibilidad_con_proveedor(self):                              # CA-073, CA-075, CA-079
        for variante in ('REGISTRADA', 'EN_BUSQUEDA_PROVEEDOR'):
            with self.subTest(variante=variante):
                s = en(variante)
                s.registrar_disponibilidad(CON_COSTO, A10)
                self.assertEqual((s.estado, s.disponibilidad, s.elegibilidad_obtenida),
                                 (ESA.PENDIENTE_APROBACION_CLIENTE, CON_COSTO, True))
                ev = s.extraer_eventos()
                self.assertEqual(nombres(ev), ['AlternativaProveedorEncontrada'])
                self.assertEqual(ev[0].proveedor_id, 'PV-9')

    def test_disponibilidad_sin_proveedor_inicia_la_busqueda(self):           # CA-074, CA-076
        s = en('REGISTRADA')
        self.assertIsNone(s.registrar_disponibilidad(SIN_PROVEEDOR, A10))
        self.assertEqual((s.estado, s.disponibilidad, s.elegibilidad_obtenida), (ESA.EN_BUSQUEDA_PROVEEDOR, None, False))
        self.assertEqual(s.extraer_eventos(), [])

    def test_disponibilidad_fuera_de_la_ventana(self):                        # CA-077, CA-083
        casos = [(SIN_PROVEEDOR, 'Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).'),
                 (CON_COSTO, 'Alternativa fuera de la ventana'), (SIN_COSTO, 'Alternativa fuera de la ventana')]
        for variante in ('REGISTRADA', 'EN_BUSQUEDA_PROVEEDOR'):
            for d, motivo in casos:
                with self.subTest(variante=variante, disponible=d.disponible, costo=d.costo):
                    s = en(variante)
                    s.registrar_disponibilidad(d, A4)
                    self.assertEqual(s.estado, ESA.NO_PROCEDENTE)
                    self.assertEqual((s.motivo_cierre.causa, s.motivo_cierre.descripcion, s.motivo_cierre.fecha),
                                     (CausaCierreSolicitud.PLAZO_INSUFICIENTE, motivo, A4))
                    self.assertIsNone(s.disponibilidad)
                    self.assertEqual(s.extraer_eventos(), [])

    def test_respuesta_a_la_espera(self):                                      # CA-077, CA-078
        s = en('EN_BUSQUEDA_PROVEEDOR'); s.registrar_respuesta_espera(False, A10)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESA.NO_SE_REALIZARA, CausaCierreSolicitud.CLIENTE_NO_ESPERA))
        s = en('EN_BUSQUEDA_PROVEEDOR'); s.registrar_respuesta_espera(True, A4)
        self.assertEqual((s.estado, s.motivo_cierre.descripcion), (ESA.NO_PROCEDENTE, 'Esperar no amplía el plazo (CA-077)'))

    def test_decision_del_cliente_y_autorizacion(self):                       # CA-079, CA-081
        casos = [('PENDIENTE_APROBACION_CLIENTE', 'registrar_decision_cliente', True, ESA.PENDIENTE_AUTORIZACION, None, 'decision_cliente'),
                 ('PENDIENTE_APROBACION_CLIENTE', 'registrar_decision_cliente', False, ESA.NO_APROBADA,
                  CausaCierreSolicitud.RECHAZO_CLIENTE, 'decision_cliente'),
                 ('PENDIENTE_AUTORIZACION', 'registrar_autorizacion', True, ESA.AUTORIZADA, None, 'autorizacion_administracion'),
                 ('PENDIENTE_AUTORIZACION', 'registrar_autorizacion', False, ESA.NO_AUTORIZADA,
                  CausaCierreSolicitud.NO_AUTORIZADA, 'autorizacion_administracion')]
        for variante, metodo, aprobada, destino, causa, atributo in casos:
            with self.subTest(metodo=metodo, aprobada=aprobada):
                s, d = en(variante), Decision('Actor', aprobada, A10, '' if aprobada else 'Motivo')
                getattr(s, metodo)(d)
                self.assertEqual((s.estado, getattr(s, atributo)), (destino, d))
                self.assertEqual(s.motivo_cierre and s.motivo_cierre.causa, causa)
                self.assertEqual(s.extraer_eventos(), [])

    def test_solicitud_de_pago_con_anexo(self):                               # CA-082
        s = en('AUTORIZADA|con_anexo'); s.registrar_solicitud_pago('OB-9')
        self.assertEqual((s.estado, s.obligacion_pago_id), (ESA.PENDIENTE_PAGO, 'OB-9'))

    def test_confirmar(self):                                                 # CA-080, CA-082
        s = en('PENDIENTE_PAGO')
        self.assertEqual(s.confirmar(True, False, A10, False), [])
        self.assertEqual(s.estado, ESA.CONFIRMADA)
        ev = s.extraer_eventos()
        self.assertEqual(nombres(ev), ['ServicioAdicionalConfirmado'])
        self.assertEqual((ev[0].servicio, ev[0].proveedor_id, ev[0].condiciones), ('DJ', 'PV-9', CON_COSTO.condiciones))

    def test_cierres_propios(self):                                           # CA-080, CA-071
        s = en('PENDIENTE_PAGO'); s.cerrar_por_falta_de_pago(A10)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESA.CERRADA_FALTA_PAGO, CausaCierreSolicitud.FALTA_PAGO))
        self.assertEqual(nombres(s.extraer_eventos()), ['ServicioAdicionalCerradoPorFaltaDePago'])
        for nombre, estado, _ in variantes():
            if estado in EN_TRAMITE:
                with self.subTest(variante=nombre):
                    s = en(nombre); s.cerrar_por_inicio_evento(FECHA_EVENTO)
                    self.assertEqual((s.estado, s.motivo_cierre.causa), (ESA.CERRADA_INICIO_EVENTO, CausaCierreSolicitud.INICIO_EVENTO))
                    self.assertEqual(nombres(s.extraer_eventos()), ['ServicioAdicionalCerradoPorInicioEvento'])

    def test_recorrido_completo(self):
        s = solicitud()
        s.registrar_disponibilidad(SIN_PROVEEDOR, A10)
        s.registrar_respuesta_espera(True, A10)
        s.registrar_disponibilidad(SIN_PROVEEDOR, A10)
        s.registrar_disponibilidad(CON_COSTO, A10)
        s.registrar_decision_cliente(Decision('Cliente', True, A10))
        s.registrar_autorizacion(Decision('Administración', True, A10))
        s.asociar_anexo('AX-1')
        s.registrar_solicitud_pago('OB-1')
        self.assertEqual(s.confirmar(True, False, A10), [])
        self.assertEqual(nombres(s.extraer_eventos()), ['AlternativaProveedorEncontrada', 'ServicioAdicionalConfirmado'])


# ======================================================================= rechazos sin efectos
class RechazosSinEfectos(unittest.TestCase):
    def test_metodos_fuera_de_su_estado(self):
        casos = [(lambda s: s.registrar_disponibilidad(CON_COSTO, A10), M_DISPONIBILIDAD, ('REGISTRADA', 'EN_BUSQUEDA_PROVEEDOR')),
                 (lambda s: s.registrar_disponibilidad(SIN_PROVEEDOR, A4), M_DISPONIBILIDAD, ('REGISTRADA', 'EN_BUSQUEDA_PROVEEDOR')),
                 (lambda s: s.registrar_respuesta_espera(True, A10), M_ESPERA, ('EN_BUSQUEDA_PROVEEDOR',)),
                 (lambda s: s.registrar_respuesta_espera(False, A10), M_ESPERA, ('EN_BUSQUEDA_PROVEEDOR',)),
                 (lambda s: s.registrar_decision_cliente(Decision('Cliente', True, A10)), M_CLIENTE, ('PENDIENTE_APROBACION_CLIENTE',)),
                 (lambda s: s.registrar_autorizacion(Decision('Administración', True, A10)), M_AUTORIZACION, ('PENDIENTE_AUTORIZACION',)),
                 (lambda s: s.registrar_solicitud_pago('OB-9'), M_PAGO, ('AUTORIZADA|con_anexo',)),
                 (lambda s: s.cerrar_por_falta_de_pago(A10), M_FALTA_PAGO, ('PENDIENTE_PAGO',))]
        for llamada, mensaje, validos in casos:
            for nombre in VARIANTES:
                if nombre in validos:
                    continue
                with self.subTest(mensaje=mensaje, variante=nombre):
                    s = en(nombre)
                    with self.assertRaises(ErrorDominio) as ctx:
                        llamada(s)
                    self.assertEqual(str(ctx.exception), mensaje)
                    self.assertEqual(observar(s), inicial(nombre))

    def test_estado_invalido_con_costo_ausente_informa_primero_el_estado(self):
        s = en('PENDIENTE_APROBACION_CLIENTE')
        with self.assertRaises(ErrorDominio) as ctx:
            s.registrar_disponibilidad(SIN_COSTO, A10)
        self.assertEqual(str(ctx.exception), M_DISPONIBILIDAD)

    def test_costo_y_condiciones_ausentes(self):                              # CA-075
        for variante in ('REGISTRADA', 'EN_BUSQUEDA_PROVEEDOR'):
            with self.subTest(variante=variante):
                s = en(variante)
                with self.assertRaises(ErrorDominio) as ctx:
                    s.registrar_disponibilidad(SIN_COSTO, A10)
                self.assertEqual(str(ctx.exception), M_CA075)
                self.assertEqual(observar(s), inicial(variante))

    def test_confirmar_con_faltantes_no_cambia_nada(self):
        s = en('PENDIENTE_PAGO')
        self.assertEqual(s.confirmar(False, True, A10, True),
                         ['evento no cancelado (SE-007)', 'elegibilidad vigente', 'pago registrado y verificado'])
        self.assertEqual(observar(s), inicial('PENDIENTE_PAGO'))
        s = en('AUTORIZADA|con_anexo')
        self.assertEqual(s.confirmar(True, False, A10), ['aprobación, autorización, anexo y solicitud de pago'])
        self.assertEqual(observar(s), inicial('AUTORIZADA|con_anexo'))

    def test_cierre_por_inicio_en_estados_finales_sin_efecto(self):
        for nombre, estado, _ in variantes():
            if estado in SA.FINALES:
                with self.subTest(variante=nombre):
                    s = en(nombre)
                    self.assertIsNone(s.cerrar_por_inicio_evento(FECHA_EVENTO))
                    self.assertEqual(observar(s), inicial(nombre))


# ======================================================================= operaciones válidas sin cambio de estado
class OperacionesSinCambioDeEstado(unittest.TestCase):
    def test_sin_proveedor_estando_en_busqueda_es_repeticion_idempotente(self):     # CA-076
        self.assertTrue(MAQ.es_repeticion(ESA.EN_BUSQUEDA_PROVEEDOR, A.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR))
        s = en('EN_BUSQUEDA_PROVEEDOR')
        with mock.patch.object(MAQ, 'transitar', wraps=MAQ.transitar) as espia:
            self.assertIsNone(s.registrar_disponibilidad(SIN_PROVEEDOR, A10))
        espia.assert_not_called()
        self.assertEqual(observar(s), inicial('EN_BUSQUEDA_PROVEEDOR'))

    def test_la_repeticion_no_omite_la_ventana(self):                               # CA-077
        s = en('EN_BUSQUEDA_PROVEEDOR')
        s.registrar_disponibilidad(SIN_PROVEEDOR, A4)
        self.assertEqual(s.estado, ESA.NO_PROCEDENTE)

    def test_acepta_esperar_dentro_de_la_ventana_con_guarda_manual(self):           # CA-077
        self.assertFalse(any(a.name.endswith('CONTINUA') for a in A))                 # no es acción ni repetición
        self.assertEqual(len(MAQ.repeticiones_idempotentes), 1)
        s = en('EN_BUSQUEDA_PROVEEDOR')
        with mock.patch.object(MAQ, 'transitar', wraps=MAQ.transitar) as espia:
            self.assertIsNone(s.registrar_respuesta_espera(True, A10))
        espia.assert_not_called()
        self.assertEqual(observar(s), inicial('EN_BUSQUEDA_PROVEEDOR'))
        s = en('REGISTRADA')
        with self.assertRaises(ErrorDominio) as ctx:                                    # la guarda manual sigue rechazando
            s.registrar_respuesta_espera(True, A10)
        self.assertEqual(str(ctx.exception), M_ESPERA)


# ======================================================================= elegibilidad (SE-004, CA-080, CA-082)
class ConservacionDeLaElegibilidad(unittest.TestCase):
    def test_con_menos_de_cinco_dias_la_tramitacion_continua(self):
        s = en('PENDIENTE_APROBACION_CLIENTE')
        s.registrar_decision_cliente(Decision('Cliente', True, A4))
        s.registrar_autorizacion(Decision('Administración', True, A4))
        s.asociar_anexo('AX-1'); s.registrar_solicitud_pago('OB-1')
        self.assertEqual(s.confirmar(True, False, A4), [])
        self.assertEqual(s.estado, ESA.CONFIRMADA)

    def test_el_inicio_del_evento_impide_confirmar(self):
        s = en('PENDIENTE_PAGO')
        self.assertEqual(s.confirmar(True, True, A10), ['elegibilidad vigente'])
        self.assertEqual(s.estado, ESA.PENDIENTE_PAGO)


# ======================================================================= conservación del comportamiento
class ConservacionDelComportamiento(unittest.TestCase):
    """Referencia capturada sobre 5e046c6, antes de E3E: 16 variantes × (estado inicial + 33 operaciones propias y
    heredadas) = 544 combinaciones, todas idénticas, y las clases que E3E no modifica con la misma huella."""

    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA_SERVICIO_ADICIONAL, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = json.loads(json.dumps(capturar_comportamiento_servicio_adicional(), ensure_ascii=False))

    def test_cobertura(self):
        self.assertEqual(len(self.referencia['comportamiento']), len(variantes()) * (1 + len(acciones())))
        self.assertEqual(len(self.referencia['comportamiento']), 544)
        self.assertEqual(set(self.actual), set(self.referencia['comportamiento']))

    def test_resultados_identicos(self):
        for clave, esperado in self.referencia['comportamiento'].items():
            with self.subTest(caso=clave):
                self.assertEqual(self.actual[clave], esperado)

    # E3F modifica SolicitudCambio a propósito: su huella queda excluida de esta protección y su conservación la comprueba
    # por comportamiento tests/test_solicitud_cambio_maquina_estados.py (referencia comportamiento_solicitud_cambio_pre_e3f).
    HUELLA_EXCLUIDA_DESDE_E3F = 'SolicitudCambio'
    # E3F.1 modifica _SolicitudBase a propósito (causa «Inicio del evento» al regularizar, CA-070, GL-032; hallazgo N3).
    # Su protección se conserva con la huella posterior a E3F.1; la referencia de N2 mantiene la histórica.
    HUELLAS_DESDE_E3F1 = {'_SolicitudBase': 'e9947bcb48d349066310697f00a5aa1a07bb0ffa64611074751f2cc07c25500b'}
    HUELLAS_HISTORICAS = {'_SolicitudBase': '4b9632f58bf2a48a79cead87ea7c931b82f9aa70ba1bef517b3bedfef174a2b6'}

    def test_clases_no_modificadas(self):
        protegidas = set(self.referencia['huellas']) - {self.HUELLA_EXCLUIDA_DESDE_E3F}
        self.assertEqual(protegidas, {'_SolicitudBase', 'SustitucionProveedor'})
        actuales = huellas_de_clases()
        for clase in sorted(protegidas):
            with self.subTest(clase=clase):
                if clase in self.HUELLAS_DESDE_E3F1:
                    self.assertEqual(self.referencia['huellas'][clase], self.HUELLAS_HISTORICAS[clase])
                    self.assertEqual(actuales[clase], self.HUELLAS_DESDE_E3F1[clase])
                else:
                    self.assertEqual(actuales[clase], self.referencia['huellas'][clase])
        self.assertEqual(set(self.referencia['huellas']), {'_SolicitudBase', 'SolicitudCambio', 'SustitucionProveedor'})

    def test_referencia_de_n2_sin_cambios(self):
        """La referencia de N2 se capturó antes de N2 (bdc98c3). Se valida la regla documentada de N2 para
        SolicitudServicioAdicional: en Registrada y Detenida por saldo vencido, idéntica a la referencia; en los demás
        estados, la decisión no modifica estado, atributos ni Domain Events y devuelve el mismo valor que la referencia."""
        with open(RUTA_REFERENCIA_REGULARIZACION, encoding='utf-8') as f:
            referencia_n2 = json.load(f)
        actual = json.loads(json.dumps(capturar_comportamiento_regularizacion(), ensure_ascii=False))
        sa = {k: v for k, v in referencia_n2.items() if k.startswith('SolicitudServicioAdicional|')}
        self.assertEqual(len(sa), 16 * 6)
        regularizables = {e.name for e in SA.ESTADOS_REGULARIZABLES}
        for clave, esperado in sa.items():
            estado = clave.split('|')[1].split(' ')[0]
            inicial = sa[clave.split(' | ')[0] + ' | (inicial)']
            with self.subTest(caso=clave):
                if estado in regularizables or clave.endswith('(inicial)'):
                    self.assertEqual(actual[clave], esperado)
                else:
                    self.assertEqual(actual[clave].get('devuelve'), esperado.get('devuelve'))
                    self.assertEqual({k: v for k, v in actual[clave].items() if k != 'devuelve'}, inicial)


class AislamientoDelPaqueteCSV(unittest.TestCase):
    def test_estados_y_acciones_son_los_de_eventos_nova(self):
        nombres_ = {e.name for e in MAQ.estados} | {a.name for a in A}
        for ajeno in ('COTIZADO', 'CONTRATADO', 'EN_PREPARACION', 'REALIZADO', 'CANCELADO', 'APROBAR', 'COMPLETAR'):
            self.assertNotIn(ajeno, nombres_)


if __name__ == '__main__':
    unittest.main()
