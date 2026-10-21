"""Etapa E3C — State Machine de SustitucionProveedor.

Comprueba la tabla implementada, que las acciones internas corresponden al resultado que ya calcula el código, el uso
real de la máquina, cada transición válida y cada acción no permitida sin efectos, los faltantes de `confirmar`, los
cierres por inicio y por cancelación del evento (incluidos los estados finales), la Specification de E2 que usa la
sustitución, y la conservación del comportamiento anterior, también para los cierres de las otras dos solicitudes."""
import ast
import json
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_maquina_estados_sustitucion import (sustitucion, variantes, acciones, observar, alternativa, aprobada,  # noqa: E402
                                               rechazada, capturar_comportamiento_sustitucion, cierres_de_otras_solicitudes,
                                               cambio_en, adicional_en, RUTA_REFERENCIA_SUSTITUCION, T, FECHA_EVENTO,
                                               ANTES_DEL_LIMITE, DESPUES_DEL_LIMITE, CON_IMPACTO, SIN_IMPACTO)

import domain.especificaciones as mod_esp                                                          # noqa: E402
from domain.especificacion import EspecificacionSimple                                             # noqa: E402
from domain.maquina_estados import MaquinaEstados, TransicionNoPermitida                           # noqa: E402
from domain.solicitudes import SustitucionProveedor as SP, SolicitudCambio, SolicitudServicioAdicional  # noqa: E402
from domain.valores import (EstadoSustitucionProveedor as ESP, ErrorDominio, Importe, CausaCierreSolicitud,  # noqa: E402
                            ImpactoModificacion)

A = SP.Accion
TABLA_ESPERADA = {
    (ESP.EN_BUSQUEDA_ALTERNATIVA, A.PROPONER_ALTERNATIVA_CON_IMPACTO): ESP.PENDIENTE_APROBACION_CLIENTE,
    (ESP.EN_BUSQUEDA_ALTERNATIVA, A.PROPONER_ALTERNATIVA_SIN_IMPACTO): ESP.PENDIENTE_FORMALIZACION,
    (ESP.PENDIENTE_APROBACION_CLIENTE, A.APROBACION_CLIENTE): ESP.PENDIENTE_AUTORIZACION,
    (ESP.PENDIENTE_APROBACION_CLIENTE, A.RECHAZO_CLIENTE): ESP.EN_BUSQUEDA_ALTERNATIVA,
    (ESP.PENDIENTE_AUTORIZACION, A.AUTORIZACION_ADMINISTRACION): ESP.PENDIENTE_FORMALIZACION,
    (ESP.PENDIENTE_AUTORIZACION, A.RECHAZO_ADMINISTRACION): ESP.EN_BUSQUEDA_ALTERNATIVA,
    (ESP.PENDIENTE_FORMALIZACION, A.CONFIRMAR): ESP.CONFIRMADA,
}
EN_TRAMITE = (ESP.EN_BUSQUEDA_ALTERNATIVA, ESP.PENDIENTE_APROBACION_CLIENTE, ESP.PENDIENTE_AUTORIZACION, ESP.PENDIENTE_FORMALIZACION)
for _e in EN_TRAMITE:
    TABLA_ESPERADA[(_e, A.CERRAR_POR_INICIO_EVENTO)] = ESP.CERRADA_INICIO_EVENTO
    TABLA_ESPERADA[(_e, A.CERRAR_POR_CANCELACION_EVENTO)] = ESP.CERRADA_EVENTO_CANCELADO

# Mensajes existentes (v8), escritos literalmente para no depender de la propia tabla.
NO_EN_BUSQUEDA = "La sustitución no está en búsqueda de alternativa."
NO_ESPERA_CLIENTE = "La alternativa no requiere o no espera aprobación del Cliente."
NO_ESPERA_AUTORIZACION = "La autorización es posterior a la aprobación del Cliente (SE-001)."
VARIANTES = dict(variantes())


def en(nombre):
    return sustitucion(**VARIANTES[nombre])


def inicial(nombre):
    return observar(en(nombre))


def nombres_en_estado(estado):
    return [n for n, a in VARIANTES.items() if a.get('estado', ESP.EN_BUSQUEDA_ALTERNATIVA) == estado]


OPERACIONES = {   # nombre -> (llamada, estado en el que está permitida, mensaje de rechazo)
    'proponer_con_impacto': (lambda s: s.proponer_alternativa(alternativa(CON_IMPACTO, 'PV-3'), Importe(D(800)), T),
                             ESP.EN_BUSQUEDA_ALTERNATIVA, NO_EN_BUSQUEDA),
    'proponer_sin_impacto': (lambda s: s.proponer_alternativa(alternativa(SIN_IMPACTO, 'PV-3'), None, T),
                             ESP.EN_BUSQUEDA_ALTERNATIVA, NO_EN_BUSQUEDA),
    'cliente_aprueba': (lambda s: s.registrar_decision_cliente(aprobada()), ESP.PENDIENTE_APROBACION_CLIENTE, NO_ESPERA_CLIENTE),
    'cliente_rechaza': (lambda s: s.registrar_decision_cliente(rechazada()), ESP.PENDIENTE_APROBACION_CLIENTE, NO_ESPERA_CLIENTE),
    'administracion_autoriza': (lambda s: s.registrar_autorizacion(aprobada('Administración'), FECHA_EVENTO),
                                ESP.PENDIENTE_AUTORIZACION, NO_ESPERA_AUTORIZACION),
    'administracion_rechaza': (lambda s: s.registrar_autorizacion(rechazada('Administración'), FECHA_EVENTO),
                               ESP.PENDIENTE_AUTORIZACION, NO_ESPERA_AUTORIZACION),
}


# ======================================================================= tabla
class TablaDeTransiciones(unittest.TestCase):
    def test_tabla_implementada(self):
        self.assertEqual({(t.origen, t.accion): t.destino for t in SP.MAQUINA.transiciones}, TABLA_ESPERADA)
        self.assertEqual(len(SP.MAQUINA.transiciones), 15)

    def test_sin_repeticiones_idempotentes(self):
        self.assertEqual(SP.MAQUINA.repeticiones_idempotentes, frozenset())

    def test_estados_terminales_son_los_finales(self):
        self.assertEqual(SP.MAQUINA.estados_terminales, set(SP.FINALES))

    def test_pendiente_coincide_con_los_estados_que_admiten_cierre(self):
        for estado in ESP:
            with self.subTest(estado=estado):
                pendiente = estado not in SP.FINALES
                self.assertEqual(SP.MAQUINA.permite(estado, A.CERRAR_POR_INICIO_EVENTO), pendiente)
                self.assertEqual(SP.MAQUINA.permite(estado, A.CERRAR_POR_CANCELACION_EVENTO), pendiente)
        self.assertEqual(SP.MAQUINA.destino(ESP.EN_BUSQUEDA_ALTERNATIVA, A.CERRAR_POR_CANCELACION_EVENTO), SP.CERRADA_CANCELACION)

    def test_acciones_internas_corresponden_a_metodos_existentes(self):
        for accion in A:
            with self.subTest(accion=accion):
                metodo = accion.value.split(':')[0]
                self.assertTrue(callable(getattr(SP, metodo, None)), metodo)

    def test_reutiliza_la_maquina_generica_sin_dejar_nombres_auxiliares(self):
        self.assertIsInstance(SP.MAQUINA, MaquinaEstados)
        for nombre in ('_Enum', '_MaquinaEstados', '_Transicion'):
            self.assertFalse(hasattr(SP, nombre), nombre)

    def test_las_otras_solicitudes_no_tienen_maquina(self):
        for clase in (SolicitudCambio, SolicitudServicioAdicional):
            self.assertFalse(hasattr(clase, 'MAQUINA'), clase.__name__)
            self.assertIs(clase.cerrar_por_cancelacion_evento, SP.__mro__[1].cerrar_por_cancelacion_evento)


# ======================================================================= las acciones corresponden al resultado
class AccionSegunResultado(unittest.TestCase):
    def _acciones_usadas(self, s, llamada):
        with mock.patch.object(SP.MAQUINA, 'transitar', wraps=SP.MAQUINA.transitar) as espia:
            llamada(s)
        return [c.args[1] for c in espia.call_args_list]

    def test_proponer_segun_el_impacto(self):
        self.assertEqual(self._acciones_usadas(en('EN_BUSQUEDA_ALTERNATIVA|sin_alternativas'), OPERACIONES['proponer_con_impacto'][0]),
                         [A.PROPONER_ALTERNATIVA_CON_IMPACTO])
        self.assertEqual(self._acciones_usadas(en('EN_BUSQUEDA_ALTERNATIVA|sin_alternativas'), OPERACIONES['proponer_sin_impacto'][0]),
                         [A.PROPONER_ALTERNATIVA_SIN_IMPACTO])

    def test_decisiones_segun_decision_aprobada(self):
        self.assertEqual(self._acciones_usadas(en('PENDIENTE_APROBACION_CLIENTE'), OPERACIONES['cliente_aprueba'][0]), [A.APROBACION_CLIENTE])
        self.assertEqual(self._acciones_usadas(en('PENDIENTE_APROBACION_CLIENTE'), OPERACIONES['cliente_rechaza'][0]), [A.RECHAZO_CLIENTE])
        self.assertEqual(self._acciones_usadas(en('PENDIENTE_AUTORIZACION'), OPERACIONES['administracion_autoriza'][0]),
                         [A.AUTORIZACION_ADMINISTRACION])
        self.assertEqual(self._acciones_usadas(en('PENDIENTE_AUTORIZACION'), OPERACIONES['administracion_rechaza'][0]),
                         [A.RECHAZO_ADMINISTRACION])

    def test_el_impacto_lo_decide_la_specification_de_e2(self):
        """MODIFICACION_CON_IMPACTO (vía ImpactoModificacion.tiene_impacto) decide la acción; no hay regla nueva."""
        with mock.patch.object(mod_esp, 'MODIFICACION_CON_IMPACTO', EspecificacionSimple(lambda i: True, 'x')):
            s = en('EN_BUSQUEDA_ALTERNATIVA|sin_alternativas')
            OPERACIONES['proponer_sin_impacto'][0](s)
            self.assertEqual(s.estado, ESP.PENDIENTE_APROBACION_CLIENTE)
        for s_, c, k in ((True, False, False), (False, True, False), (False, False, True), (False, False, False)):
            s = en('EN_BUSQUEDA_ALTERNATIVA|sin_alternativas')
            s.proponer_alternativa(alternativa(ImpactoModificacion(s_, c, k)), None, T)
            self.assertEqual(s.estado, ESP.PENDIENTE_APROBACION_CLIENTE if (s_ or c or k) else ESP.PENDIENTE_FORMALIZACION)


class UsoRealDeLaMaquina(unittest.TestCase):
    def _sin(self, accion):
        return MaquinaEstados(ESP, [t for t in SP.MAQUINA.transiciones if t.accion != accion])

    def test_cada_metodo_consulta_la_maquina(self):
        casos = [
            (A.PROPONER_ALTERNATIVA_CON_IMPACTO, 'EN_BUSQUEDA_ALTERNATIVA|sin_alternativas', OPERACIONES['proponer_con_impacto'][0]),
            (A.PROPONER_ALTERNATIVA_SIN_IMPACTO, 'EN_BUSQUEDA_ALTERNATIVA|sin_alternativas', OPERACIONES['proponer_sin_impacto'][0]),
            (A.APROBACION_CLIENTE, 'PENDIENTE_APROBACION_CLIENTE', OPERACIONES['cliente_aprueba'][0]),
            (A.RECHAZO_CLIENTE, 'PENDIENTE_APROBACION_CLIENTE', OPERACIONES['cliente_rechaza'][0]),
            (A.AUTORIZACION_ADMINISTRACION, 'PENDIENTE_AUTORIZACION', OPERACIONES['administracion_autoriza'][0]),
            (A.RECHAZO_ADMINISTRACION, 'PENDIENTE_AUTORIZACION', OPERACIONES['administracion_rechaza'][0]),
            (A.CONFIRMAR, 'PENDIENTE_FORMALIZACION|sin_impacto|con_anexo', lambda s: s.confirmar(False, False, T, False)),
            (A.CERRAR_POR_INICIO_EVENTO, 'PENDIENTE_AUTORIZACION', lambda s: s.cerrar_por_inicio_evento(T)),
            (A.CERRAR_POR_CANCELACION_EVENTO, 'PENDIENTE_AUTORIZACION', lambda s: s.cerrar_por_cancelacion_evento(T)),
        ]
        for accion, variante, llamada in casos:
            with self.subTest(accion=accion):
                s = en(variante)
                with mock.patch.object(SP, 'MAQUINA', self._sin(accion)):
                    with self.assertRaises(TransicionNoPermitida):
                        llamada(s)
                self.assertEqual(observar(s), inicial(variante))      # validación antes de modificar el agregado


# ======================================================================= transiciones válidas
class TransicionesValidas(unittest.TestCase):
    def _aplicar(self, variante, operacion):
        s = en(variante)
        OPERACIONES[operacion][0](s)
        return s, s.extraer_eventos()

    def test_proponer_alternativa(self):
        s, ev = self._aplicar('EN_BUSQUEDA_ALTERNATIVA|sin_alternativas', 'proponer_con_impacto')
        self.assertEqual((s.estado, len(s.alternativas), s.costo_adicional, ev), (ESP.PENDIENTE_APROBACION_CLIENTE, 1, Importe(D(800)), []))
        s, ev = self._aplicar('EN_BUSQUEDA_ALTERNATIVA|alternativa_rechazada', 'proponer_sin_impacto')
        self.assertEqual((s.estado, len(s.alternativas), s.costo_adicional, ev), (ESP.PENDIENTE_FORMALIZACION, 2, None, []))

    def test_decision_del_cliente(self):
        s, ev = self._aplicar('PENDIENTE_APROBACION_CLIENTE', 'cliente_aprueba')
        self.assertEqual((s.estado, s.alternativa_vigente.decision_cliente.aprobada, ev), (ESP.PENDIENTE_AUTORIZACION, True, []))
        s, ev = self._aplicar('PENDIENTE_APROBACION_CLIENTE', 'cliente_rechaza')
        self.assertEqual(s.estado, ESP.EN_BUSQUEDA_ALTERNATIVA)
        self.assertEqual([(e.nombre, e.proveedor_id) for e in ev], [('AlternativaRechazadaPorCliente', 'PV-2')])

    def test_autorizacion_de_administracion(self):
        s = en('PENDIENTE_AUTORIZACION')
        s.registrar_autorizacion(aprobada('Administración', ANTES_DEL_LIMITE), FECHA_EVENTO)
        self.assertEqual((s.estado, s.aprobada_despues_del_limite, s.extraer_eventos()), (ESP.PENDIENTE_FORMALIZACION, False, []))
        s = en('PENDIENTE_AUTORIZACION')
        s.registrar_autorizacion(aprobada('Administración', DESPUES_DEL_LIMITE), FECHA_EVENTO)
        self.assertEqual((s.estado, s.aprobada_despues_del_limite), (ESP.PENDIENTE_FORMALIZACION, True))
        s, ev = self._aplicar('PENDIENTE_AUTORIZACION', 'administracion_rechaza')
        self.assertEqual((s.estado, s.aprobada_despues_del_limite), (ESP.EN_BUSQUEDA_ALTERNATIVA, False))
        self.assertEqual([(e.nombre, e.proveedor_id) for e in ev], [('AlternativaNoAutorizadaPorAdministracion', 'PV-2')])

    def test_confirmar(self):
        s = en('PENDIENTE_FORMALIZACION|sin_impacto|con_anexo')
        self.assertEqual(s.confirmar(False, False, T, False), [])
        eventos = s.extraer_eventos()
        self.assertEqual(s.estado, ESP.CONFIRMADA)
        self.assertEqual([(e.nombre, e.proveedor_id, e.servicio_contratado_id) for e in eventos],
                         [('SustitucionProveedorConfirmada', 'PV-2', 'CT-1-S1')])

    def test_recorridos_completos(self):
        s = en('EN_BUSQUEDA_ALTERNATIVA|sin_alternativas')
        OPERACIONES['proponer_con_impacto'][0](s); OPERACIONES['cliente_rechaza'][0](s)       # CA-054: se vuelve a buscar
        OPERACIONES['proponer_con_impacto'][0](s); OPERACIONES['cliente_aprueba'][0](s)
        OPERACIONES['administracion_rechaza'][0](s)                                           # CA-050: se vuelve a buscar
        OPERACIONES['proponer_sin_impacto'][0](s); s.asociar_anexo('AX-1')
        self.assertEqual(s.confirmar(False, False, T, False), [])
        self.assertEqual(s.estado, ESP.CONFIRMADA)
        self.assertEqual([e.nombre for e in s.extraer_eventos()],
                         ['AlternativaRechazadaPorCliente', 'AlternativaNoAutorizadaPorAdministracion', 'SustitucionProveedorConfirmada'])


# ======================================================================= acciones no permitidas
class AccionesNoPermitidas(unittest.TestCase):
    def test_cada_operacion_fuera_de_su_estado_se_rechaza_sin_efectos(self):
        revisados = 0
        for variante, argumentos in VARIANTES.items():
            estado = argumentos.get('estado', ESP.EN_BUSQUEDA_ALTERNATIVA)
            for operacion, (llamada, permitido, mensaje) in OPERACIONES.items():
                if estado == permitido:
                    continue
                with self.subTest(variante=variante, operacion=operacion):
                    s = en(variante)
                    with self.assertRaises(ErrorDominio) as ctx:
                        llamada(s)
                    self.assertEqual(str(ctx.exception), mensaje)
                    self.assertEqual(observar(s), inicial(variante))
                    revisados += 1
        self.assertEqual(revisados, 11 * 6 - 2 * 2 - 1 * 2 - 1 * 2)        # 58

    def test_estados_finales_rechazan_todas_las_operaciones_del_flujo(self):
        for estado in SP.FINALES:
            for accion in A:
                if accion in (A.CERRAR_POR_INICIO_EVENTO, A.CERRAR_POR_CANCELACION_EVENTO, A.CONFIRMAR):
                    continue
                with self.subTest(estado=estado, accion=accion):
                    self.assertFalse(SP.MAQUINA.permite(estado, accion))


# ======================================================================= confirmar con faltantes
class ConfirmacionConFaltantes(unittest.TestCase):
    def test_faltantes_y_mensajes_actuales_sin_efectos(self):
        casos = [
            ('PENDIENTE_FORMALIZACION|sin_impacto|sin_anexo', (False, False, False), ['anexo vinculado al contrato original']),
            ('PENDIENTE_FORMALIZACION|sin_impacto|con_anexo', (False, True, True),
             ['evento no iniciado', 'evento no cancelado (SE-007)']),
            ('PENDIENTE_FORMALIZACION|con_costo|despues_del_limite|con_anexo', (False, False, False),
             ['pago del costo adicional verificado antes de confirmar (CA-052)']),
            ('PENDIENTE_APROBACION_CLIENTE', (True, False, False), ['decisiones requeridas', 'anexo vinculado al contrato original']),
            ('CONFIRMADA', (True, False, False), ['decisiones requeridas']),
            ('CERRADA_EVENTO_CANCELADO', (False, True, True),
             ['evento no iniciado', 'evento no cancelado (SE-007)', 'decisiones requeridas', 'anexo vinculado al contrato original']),
        ]
        for variante, (pago, iniciado, cancelado), faltan in casos:
            with self.subTest(variante=variante):
                s = en(variante)
                with mock.patch.object(SP.MAQUINA, 'transitar', wraps=SP.MAQUINA.transitar) as espia:
                    self.assertEqual(s.confirmar(pago, iniciado, T, cancelado), faltan)
                espia.assert_not_called()                                   # la máquina no se consulta con faltantes
                self.assertEqual(observar(s), inicial(variante))

    def test_pago_previo_despues_del_limite(self):                          # SE-001, CA-052
        s = en('PENDIENTE_FORMALIZACION|con_costo|despues_del_limite|con_anexo')
        self.assertEqual(s.confirmar(True, False, T, False), [])
        self.assertEqual(s.estado, ESP.CONFIRMADA)
        s = en('PENDIENTE_FORMALIZACION|con_costo|antes_del_limite|con_anexo')
        self.assertEqual(s.confirmar(False, False, T, False), [])           # antes del límite no se exige pago previo

    def test_coherencia_decisiones_requeridas_y_maquina(self):
        """El faltante «decisiones requeridas» aparece si y solo si la máquina no permite confirmar desde ese estado."""
        for variante in VARIANTES:
            with self.subTest(variante=variante):
                s = en(variante)
                permitido = SP.MAQUINA.permite(s.estado, A.CONFIRMAR)
                self.assertEqual('decisiones requeridas' in s.confirmar(True, False, T, False), not permitido)
        self.assertEqual({e for e in ESP if SP.MAQUINA.permite(e, A.CONFIRMAR)}, {ESP.PENDIENTE_FORMALIZACION})


# ======================================================================= cierres
class Cierres(unittest.TestCase):
    def test_cierre_por_inicio_desde_cada_estado_en_tramite(self):          # CA-096
        for estado in EN_TRAMITE:
            for variante in nombres_en_estado(estado):
                with self.subTest(variante=variante):
                    s = en(variante)
                    self.assertIsNone(s.cerrar_por_inicio_evento(T))
                    self.assertEqual(s.estado, ESP.CERRADA_INICIO_EVENTO)
                    self.assertEqual((s.motivo_cierre.causa, s.motivo_cierre.descripcion),
                                     (CausaCierreSolicitud.INICIO_EVENTO, 'El reemplazo no se concretó'))
                    self.assertEqual([e.nombre for e in s.extraer_eventos()], ['SustitucionProveedorCerradaPorInicioEvento'])

    def test_cierre_por_cancelacion_desde_cada_estado_en_tramite_sin_evento(self):   # BN-008
        for estado in EN_TRAMITE:
            for variante in nombres_en_estado(estado):
                with self.subTest(variante=variante):
                    s = en(variante)
                    self.assertTrue(s.cerrar_por_cancelacion_evento(T))
                    self.assertEqual(s.estado, ESP.CERRADA_EVENTO_CANCELADO)
                    self.assertEqual((s.motivo_cierre.causa, s.motivo_cierre.descripcion),
                                     (CausaCierreSolicitud.EVENTO_CANCELADO, CausaCierreSolicitud.EVENTO_CANCELADO.value))
                    self.assertEqual(s.extraer_eventos(), [])

    def test_cierres_en_estados_finales_no_tienen_efecto(self):
        for estado in SP.FINALES:
            for variante in nombres_en_estado(estado):
                with self.subTest(variante=variante):
                    s = en(variante)
                    with mock.patch.object(SP.MAQUINA, 'transitar', wraps=SP.MAQUINA.transitar) as espia:
                        self.assertIsNone(s.cerrar_por_inicio_evento(T))
                        self.assertFalse(s.cerrar_por_cancelacion_evento(T))
                    espia.assert_not_called()                               # se resuelven con `pendiente`
                    self.assertEqual(observar(s), inicial(variante))

    def test_reaccion_a_la_cancelacion_cierra_la_sustitucion(self):        # BN-008, a través de la reacción existente
        from test_reglas_corregidas import Escenario, T0
        e = Escenario(); e.confirmar_contratacion()
        servicio = next(iter(e.evento().servicios))
        sid = e.s.sustitucion.registrar_proveedor_no_disponible(e.evento_id, servicio, e.contrato_id, T0 + timedelta(days=5)).datos['sustitucion_id']
        e.s.cierre.gestionar_cancelacion_solicitada(e.evento_id, 'Motivo', T0 + timedelta(days=6)); e.d.despachar()
        s = e.app.repos.sustituciones.obtener_por_id(sid)
        self.assertEqual((s.estado, s.motivo_cierre.causa), (ESP.CERRADA_EVENTO_CANCELADO, CausaCierreSolicitud.EVENTO_CANCELADO))


# ======================================================================= Specifications de E2 que usa la sustitución
class SpecificationsUtilizadas(unittest.TestCase):
    def test_solo_usa_modificacion_con_impacto_a_traves_de_tiene_impacto(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', 'solicitudes.py')
        with open(ruta, encoding='utf8') as f:
            arbol = ast.parse(f.read())
        clase = next(n for n in arbol.body if isinstance(n, ast.ClassDef) and n.name == 'SustitucionProveedor')
        nombres = {n.id for n in ast.walk(clase) if isinstance(n, ast.Name)}
        atributos = {n.attr for n in ast.walk(clase) if isinstance(n, ast.Attribute)}
        self.assertIn('tiene_impacto', atributos)
        for spec in ('CAMBIO_REQUIERE_APROBACION_CLIENTE', 'CAMBIO_CON_CARGO_TARDIO', 'SERVICIO_ADICIONAL_EN_PLAZO',
                     'SOLICITUD_CAMBIO_EN_PLAZO', 'SOLICITUD_PUEDE_CONTINUAR', 'CONTRATACION_CONFIRMABLE'):
            self.assertNotIn(spec, nombres)


# ======================================================================= conservación y aislamiento
class ConservacionDelComportamiento(unittest.TestCase):
    """Referencia capturada con v8 + E1 + E2 + E3A + E3B antes de E3C: 209 combinaciones de SustitucionProveedor y
    58 cierres de SolicitudCambio y SolicitudServicioAdicional, todas idénticas."""

    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA_SUSTITUCION, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = json.loads(json.dumps(capturar_comportamiento_sustitucion(), ensure_ascii=False))

    def test_cobertura(self):
        sp = [k for k in self.referencia if k.startswith('SustitucionProveedor|')]
        self.assertEqual(len(sp), len(variantes()) * len(acciones()))
        self.assertEqual(len(sp), 209)
        self.assertEqual(len(self.referencia) - len(sp), 58)
        self.assertEqual(set(self.actual), set(self.referencia))
        self.assertEqual({a.get('estado', ESP.EN_BUSQUEDA_ALTERNATIVA) for _, a in variantes()}, set(ESP))   # los 7 estados

    def test_sustitucion_identica(self):
        for clave, esperado in self.referencia.items():
            if clave.startswith('SustitucionProveedor|'):
                with self.subTest(caso=clave):
                    self.assertEqual(self.actual[clave], esperado)

    def test_cierres_de_las_otras_solicitudes_identicos(self):
        actuales = json.loads(json.dumps(cierres_de_otras_solicitudes(), ensure_ascii=False))
        for clave, esperado in actuales.items():
            with self.subTest(caso=clave):
                self.assertEqual(esperado, self.referencia[clave])

    def test_referencia_de_e2_sin_cambios(self):
        from apoyo_especificaciones import capturar_comportamiento, RUTA_REFERENCIA
        with open(RUTA_REFERENCIA, encoding='utf-8') as f:
            self.assertEqual(json.loads(json.dumps(capturar_comportamiento(), ensure_ascii=False)), json.load(f))


class AislamientoDelPaqueteCSV(unittest.TestCase):
    def test_estados_y_acciones_son_los_de_eventos_nova(self):
        nombres = {e.name for e in SP.MAQUINA.estados} | {a.name for a in A}
        for ajeno in ('COTIZADO', 'CONTRATADO', 'EN_PREPARACION', 'REALIZADO', 'CANCELADO', 'APROBAR', 'COMPLETAR',
                      'REPETIR_APROBACION', 'SALTAR_ESTADO'):
            self.assertNotIn(ajeno, nombres)

    def test_solicitudes_no_lee_el_paquete(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', 'solicitudes.py')
        with open(ruta, encoding='utf8') as f:
            texto = f.read()
        for ajeno in ('paquete_pia', 'COTIZADO', '.csv'):
            self.assertNotIn(ajeno, texto)


if __name__ == '__main__':
    unittest.main()
