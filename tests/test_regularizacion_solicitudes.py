"""Corrección N2 — protección de `_SolicitudBase.aplicar_decision_regularizacion`.

Una decisión de regularización (EvaluarRegularizacionDeSolicitudes) solo modifica una solicitud Registrada (al
registrarla) o Detenida por saldo vencido (al retomarla), según SE-006 y P-06. En cualquier otro estado, en trámite o
final, la llamada no tiene efecto. Se comprueban las decisiones válidas, la restauración del estado anterior, los
estados protegidos de SolicitudCambio y SolicitudServicioAdicional, los flujos de los servicios y la comparación con el
comportamiento anterior (referencia capturada sobre bdc98c3), cuyas únicas diferencias son las de N2."""
import json
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_regularizacion_solicitudes import (solicitud, observar, variantes, DECISIONES, NO_PROCEDE, AHORA,      # noqa: E402
                                              capturar_comportamiento_regularizacion,
                                              RUTA_REFERENCIA_REGULARIZACION, adaptar_referencia_e3g)
from test_reglas_corregidas import Escenario, FECHA_EVENTO                                             # noqa: E402

from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor     # noqa: E402
from infrastructure.adaptadores import ConsultaDisponibilidadSimulada                               # noqa: E402
from domain.valores import (CausaCierreSolicitud, Importe, ResultadoViabilidad, DisponibilidadProveedor,  # noqa: E402
                            CondicionesServicio, EstadoSolicitudCambio as ESC,
                            EstadoSolicitudServicioAdicional as ESA, EstadoSustitucionProveedor as ESP)

CLASES = (('SolicitudCambio', SolicitudCambio, ESC), ('SolicitudServicioAdicional', SolicitudServicioAdicional, ESA))
MODIFICADORAS = ('detener_por_saldo', 'no_procede_condicion_temporal', 'no_procede_evento_cancelado',
                 'no_procede_evento_iniciado_cambio')
# E3F.1 (resuelve el hallazgo N3): en SolicitudCambio, el motivo «El evento ya inició (CA-039).» cierra con la causa
# «Inicio del evento» (CA-070, GL-032), no «Evento cancelado». Únicos casos de la referencia de N2 que cambian por
# E3F.1; solo cambia `motivo_cierre.causa`. SolicitudServicioAdicional y SustitucionProveedor no cambian.
DIFERENCIAS_E3F1 = {
    'SolicitudCambio|REGISTRADA | no_procede_evento_iniciado_cambio',
    'SolicitudCambio|DETENIDA_SALDO_VENCIDO|antes=REGISTRADA | no_procede_evento_iniciado_cambio',
    'SolicitudCambio|DETENIDA_SALDO_VENCIDO|antes=PENDIENTE_APROBACION_CLIENTE | no_procede_evento_iniciado_cambio',
}


def esperado_e3f1(clave, referencia):
    """Lo que la referencia de N2 registraba, con la causa corregida por E3F.1."""
    if clave not in DIFERENCIAS_E3F1:
        return referencia
    assert referencia['motivo_cierre']['causa'] == CausaCierreSolicitud.EVENTO_CANCELADO.name
    return {**referencia, 'motivo_cierre': {**referencia['motivo_cierre'], 'causa': CausaCierreSolicitud.INICIO_EVENTO.name}}


def aplicar(tipo, estado, decision, antes=None, con_motivo=False):
    s = solicitud(tipo, estado, antes, con_motivo)
    devuelve = s.aplicar_decision_regularizacion(DECISIONES[decision], AHORA, NO_PROCEDE[tipo])
    return s, devuelve


def protegidos(clase, enum):
    return [e for e in enum if e not in clase.ESTADOS_REGULARIZABLES]


# ======================================================================= estados regularizables
class EstadosRegularizables(unittest.TestCase):
    def test_solo_registrada_y_detenida(self):
        self.assertEqual(SolicitudCambio.ESTADOS_REGULARIZABLES, (ESC.REGISTRADA, ESC.DETENIDA_SALDO_VENCIDO))
        self.assertEqual(SolicitudServicioAdicional.ESTADOS_REGULARIZABLES, (ESA.REGISTRADA, ESA.DETENIDA_SALDO_VENCIDO))

    def test_sustitucion_no_tiene_estados_regularizables(self):
        """Ningún servicio aplica la regularización a una SustitucionProveedor (SE-006 regula cambios y servicios
        adicionales nuevos): con N2 una llamada directa ya no la deja sin estado."""
        self.assertEqual(SustitucionProveedor.ESTADOS_REGULARIZABLES, ())
        for estado in ESP:
            for decision in DECISIONES:
                with self.subTest(estado=estado, decision=decision):
                    antes = observar(solicitud('SustitucionProveedor', estado))
                    s, _ = aplicar('SustitucionProveedor', estado, decision)
                    self.assertEqual(observar(s), antes)

    def test_los_regularizables_no_son_finales(self):
        for _, clase, _ in CLASES:
            self.assertFalse(set(clase.ESTADOS_REGULARIZABLES) & set(clase.FINALES))
            self.assertIn(clase.DETENIDA, clase.ESTADOS_REGULARIZABLES)


# ======================================================================= decisiones válidas
class DecisionesValidas(unittest.TestCase):
    def test_registrada_se_detiene_por_saldo(self):                          # SE-006, CA-066, CA-072
        for tipo, clase, enum in CLASES:
            with self.subTest(tipo=tipo):
                s, devuelve = aplicar(tipo, enum.REGISTRADA, 'detener_por_saldo')
                self.assertFalse(devuelve)
                self.assertEqual((s.estado, s._estado_antes_de_detener), (clase.DETENIDA, enum.REGISTRADA))
                self.assertIsNone(s.motivo_cierre)
                self.assertEqual(s.extraer_eventos(), [])

    def test_reanudacion_restaura_el_estado_anterior(self):                 # SE-006, CA-066, CA-072
        for tipo, clase, enum in CLASES:
            for antes in (enum.REGISTRADA, enum.PENDIENTE_APROBACION_CLIENTE):
                with self.subTest(tipo=tipo, antes=antes):
                    s, devuelve = aplicar(tipo, clase.DETENIDA, 'continuar', antes=antes)
                    self.assertTrue(devuelve)
                    self.assertEqual(s.estado, antes)

    def test_detener_y_retomar_en_secuencia(self):
        for tipo, clase, enum in CLASES:
            with self.subTest(tipo=tipo):
                s = solicitud(tipo, enum.REGISTRADA)
                s.aplicar_decision_regularizacion(DECISIONES['detener_por_saldo'], AHORA, NO_PROCEDE[tipo])
                s.aplicar_decision_regularizacion(DECISIONES['detener_por_saldo'], AHORA, NO_PROCEDE[tipo])   # sigue Detenida
                self.assertEqual((s.estado, s._estado_antes_de_detener), (clase.DETENIDA, enum.REGISTRADA))
                self.assertTrue(s.aplicar_decision_regularizacion(DECISIONES['continuar'], AHORA, NO_PROCEDE[tipo]))
                self.assertEqual(s.estado, enum.REGISTRADA)

    def test_registrada_que_puede_continuar_no_cambia(self):
        for tipo, _, enum in CLASES:
            with self.subTest(tipo=tipo):
                antes = observar(solicitud(tipo, enum.REGISTRADA))
                s, devuelve = aplicar(tipo, enum.REGISTRADA, 'continuar')
                self.assertTrue(devuelve)
                self.assertEqual(observar(s), antes)

    def test_no_procede_desde_registrada_y_desde_detenida(self):            # SE-004, SE-006, CA-083
        esperado = {'no_procede_condicion_temporal': CausaCierreSolicitud.PLAZO_INSUFICIENTE,
                    'no_procede_evento_cancelado': CausaCierreSolicitud.EVENTO_CANCELADO}
        # E3F.1 resuelve N3 solo en SolicitudCambio, cuya condición temporal produce ese motivo (CA-070, GL-032). En
        # SolicitudServicioAdicional, que nunca lo produce (usa el motivo N6), se conserva el resultado anterior.
        iniciado_cambio = {'SolicitudCambio': CausaCierreSolicitud.INICIO_EVENTO,
                           'SolicitudServicioAdicional': CausaCierreSolicitud.EVENTO_CANCELADO}
        for tipo, clase, enum in CLASES:
            for origen, antes in ((enum.REGISTRADA, None), (clase.DETENIDA, enum.REGISTRADA)):
                for decision, causa in {**esperado, 'no_procede_evento_iniciado_cambio': iniciado_cambio[tipo]}.items():
                    with self.subTest(tipo=tipo, origen=origen, decision=decision):
                        s, devuelve = aplicar(tipo, origen, decision, antes=antes)
                        self.assertFalse(devuelve)
                        self.assertEqual(s.estado, enum.NO_PROCEDENTE)
                        self.assertEqual((s.motivo_cierre.causa, s.motivo_cierre.descripcion, s.motivo_cierre.fecha),
                                         (causa, DECISIONES[decision].motivo, AHORA))
                        self.assertEqual(s.extraer_eventos(), [])


# ======================================================================= llamadas inválidas sin efecto
class LlamadasInvalidasSinEfecto(unittest.TestCase):
    def _sin_efecto(self, tipo, estado, decision, con_motivo=False):
        antes = observar(solicitud(tipo, estado, con_motivo=con_motivo))
        s, devuelve = aplicar(tipo, estado, decision, con_motivo=con_motivo)
        self.assertEqual(devuelve, DECISIONES[decision].puede_continuar)   # mismo valor que antes de N2
        self.assertEqual(observar(s), antes)                               # estado, atributos y Domain Events

    def test_confirmada_no_pasa_a_detenida(self):
        for tipo, clase, enum in CLASES:
            with self.subTest(tipo=tipo):
                self._sin_efecto(tipo, enum.CONFIRMADA, 'detener_por_saldo')
                s, _ = aplicar(tipo, enum.CONFIRMADA, 'detener_por_saldo')
                self.assertEqual((s.estado, s._estado_antes_de_detener), (enum.CONFIRMADA, None))

    def test_confirmada_no_pasa_a_no_procedente(self):
        for tipo, _, enum in CLASES:
            for decision in MODIFICADORAS[1:]:
                with self.subTest(tipo=tipo, decision=decision):
                    self._sin_efecto(tipo, enum.CONFIRMADA, decision)
                    s, _ = aplicar(tipo, enum.CONFIRMADA, decision)
                    self.assertEqual((s.estado, s.motivo_cierre), (enum.CONFIRMADA, None))

    def test_ningun_estado_final_cambia(self):
        for tipo, clase, enum in CLASES:
            for estado in clase.FINALES:
                for decision in DECISIONES:
                    with self.subTest(tipo=tipo, estado=estado, decision=decision):
                        self._sin_efecto(tipo, estado, decision, con_motivo=estado.name != 'CONFIRMADA')

    def test_solicitudes_en_tramite_no_cambian(self):                       # P-06: la solicitud en trámite continúa
        for tipo, clase, enum in CLASES:
            en_tramite = [e for e in protegidos(clase, enum) if e not in clase.FINALES]
            self.assertTrue(en_tramite)
            for estado in en_tramite:
                for decision in DECISIONES:
                    with self.subTest(tipo=tipo, estado=estado, decision=decision):
                        self._sin_efecto(tipo, estado, decision)


# ======================================================================= flujos de los servicios
class FlujosDeLosServicios(unittest.TestCase):
    def test_registro_con_saldo_vencido_detiene_y_la_regularizacion_retoma(self):     # SE-006, CA-066, CA-027
        e = Escenario(); e.confirmar_contratacion(); e.vencer_saldo_y_comunicar_moratorios()
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(100)), e.comunicacion).datos['solicitud_id']
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.DETENIDA_SALDO_VENCIDO)
        a_tiempo = e.comunicacion + timedelta(hours=5)
        for concepto in ('SaldoContratoOriginal', 'CargosMoratorios'):
            o = e.obligacion(concepto)
            e.s.pagos.registrar_y_verificar_pago(e.ec_id, o.obligacion_id, o.importe, a_tiempo, 'C')
        e.s.cierre.resolver_regularizacion_saldo_vencido(e.ec_id, e.comunicacion + timedelta(hours=25)); e.d.despachar()
        self.assertEqual(e.app.repos.cambios.obtener_por_id(sc).estado, ESC.REGISTRADA)

    def test_retomar_un_cambio_confirmado_no_lo_modifica(self):
        e = Escenario(); e.confirmar_contratacion()
        dia = FECHA_EVENTO - timedelta(days=10)
        sc = e.s.cambios.registrar_solicitud_cambio(e.evento_id, e.contrato_id, 'Cambio', Importe(D(150)), dia).datos['solicitud_id']
        e.s.cambios.evaluar_viabilidad_cambio(sc, ResultadoViabilidad(True), None, dia)       # ruta C, sin importes
        e.s.cambios.registrar_anexo_cambio(sc, 'Anexo', dia); e.d.despachar()
        self.assertTrue(e.s.cambios.confirmar_cambio(sc, dia).exito); e.d.despachar()
        e.vencer_saldo_y_comunicar_moratorios()                                                 # saldo vencido
        antes = observar(e.app.repos.cambios.obtener_por_id(sc))
        e.s.cambios.retomar_solicitud_cambio(sc, e.comunicacion)                                # llamada directa
        s = e.app.repos.cambios.obtener_por_id(sc)
        self.assertEqual(s.estado, ESC.CONFIRMADA)
        self.assertEqual(observar(s), antes)

    def test_retomar_un_servicio_adicional_en_tramite_no_lo_detiene(self):               # P-06
        e = Escenario(ConsultaDisponibilidadSimulada([DisponibilidadProveedor('PV-9', True, Importe(D(500)), CondicionesServicio('DJ'))]))
        e.confirmar_contratacion()
        dia = FECHA_EVENTO - timedelta(days=10)
        sa = e.s.adicionales.registrar_solicitud_servicio_adicional(e.evento_id, e.contrato_id, 'DJ', dia).datos['solicitud_id']
        e.s.adicionales.evaluar_disponibilidad_servicio_adicional(sa, [], dia)
        e.vencer_saldo_y_comunicar_moratorios()
        e.s.adicionales.retomar_solicitud_servicio_adicional(sa, e.comunicacion)            # llamada directa
        self.assertEqual(e.app.repos.adicionales.obtener_por_id(sa).estado, ESA.PENDIENTE_APROBACION_CLIENTE)


# ======================================================================= comportamiento anterior
class ComparacionConLaReferencia(unittest.TestCase):
    """Referencia capturada sobre bdc98c3, antes de N2. Las únicas diferencias son las decisiones que modificaban una
    solicitud fuera de Registrada y Detenida: con N2 no tienen efecto y conservan el mismo valor devuelto."""

    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA_REGULARIZACION, encoding='utf-8') as f:
            cls.referencia = adaptar_referencia_e3g(json.load(f))      # E3G: atributo nuevo con su valor por defecto
        cls.actual = json.loads(json.dumps(capturar_comportamiento_regularizacion(), ensure_ascii=False))
        cls.clases = {'SolicitudCambio': SolicitudCambio, 'SolicitudServicioAdicional': SolicitudServicioAdicional,
                      'SustitucionProveedor': SustitucionProveedor}

    def _regularizable(self, clave):
        tipo, resto = clave.split('|', 1)
        estado = resto.split(' | ')[0].split('|')[0]
        return estado in {e.name for e in self.clases[tipo].ESTADOS_REGULARIZABLES}

    def test_cobertura(self):
        self.assertEqual(len(self.referencia), len(variantes()) * (1 + len(DECISIONES)))
        self.assertEqual(len(self.referencia), 228)
        self.assertEqual(set(self.actual), set(self.referencia))

    def test_registrada_y_detenida_identicas(self):
        """Idénticas a la referencia, salvo las tres diferencias de E3F.1 (DIFERENCIAS_E3F1), que solo cambian la causa."""
        self.assertTrue(DIFERENCIAS_E3F1 <= {k for k in self.referencia if self._regularizable(k)})
        for clave, esperado in self.referencia.items():
            if self._regularizable(clave):
                with self.subTest(caso=clave):
                    self.assertEqual(self.actual[clave], esperado_e3f1(clave, esperado))

    def test_los_demas_estados_conservan_el_valor_devuelto_y_no_cambian(self):
        for clave, esperado in self.referencia.items():
            if self._regularizable(clave) or clave.endswith('(inicial)'):
                continue
            inicial = self.referencia[clave.split(' | ')[0] + ' | (inicial)']
            with self.subTest(caso=clave):
                self.assertEqual(self.actual[clave].get('devuelve'), esperado.get('devuelve'))
                self.assertEqual({k: v for k, v in self.actual[clave].items() if k != 'devuelve'}, inicial)

    def test_diferencias_documentadas_de_n2(self):
        """128 casos: 12 estados de SolicitudCambio, 13 de SolicitudServicioAdicional y 7 de SustitucionProveedor fuera
        de Registrada y Detenida, por las 4 decisiones que modifican (detener y los tres «no procede»)."""
        diferentes = sorted(k for k in self.referencia if self.actual[k] != esperado_e3f1(k, self.referencia[k]))
        esperadas = sorted(k for k in self.referencia if not self._regularizable(k) and not k.endswith('(inicial)')
                           and k.split(' | ')[1] in MODIFICADORAS)
        self.assertEqual(diferentes, esperadas)
        self.assertEqual(len(diferentes), 128)
        self.assertEqual(sorted(k for k in self.referencia if self.actual[k] != self.referencia[k]),
                         sorted(set(esperadas) | DIFERENCIAS_E3F1))                         # 128 de N2 + 3 de E3F.1
        for clave in diferentes:                                       # antes cambiaban; ahora no
            inicial = self.referencia[clave.split(' | ')[0] + ' | (inicial)']
            self.assertNotEqual({k: v for k, v in self.referencia[clave].items() if k != 'devuelve'}, inicial)


if __name__ == '__main__':
    unittest.main()
