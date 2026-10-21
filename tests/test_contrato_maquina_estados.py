"""Etapa E3B — State Machine del agregado Contrato.

Comprueba la tabla implementada, cada transición válida y cada acción no permitida, el uso real de la máquina, que
los rechazos no modifican el agregado, la confirmación repetida sin un segundo Domain Event, los pendientes de la
Specification de E2, la coherencia entre la Specification y la máquina, los límites temporales del cierre, las
restricciones de las operaciones que no cambian el estado y la conservación del comportamiento anterior."""
import json
import os
import sys
import unittest
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoyo_maquina_estados_contrato import (contrato_en, observar, variantes, acciones,                # noqa: E402
                                            capturar_comportamiento_contrato, RUTA_REFERENCIA_CONTRATO,
                                            FIRMA, CONTACTO, LIMITE, NUEVA_FIRMA, AHORA)

import domain.contrato as mod_contrato                                                          # noqa: E402
from domain.contrato import Contrato, EvidenciaAnticipo, AccionContrato, MAQUINA_CONTRATO        # noqa: E402
from domain.especificacion import EspecificacionSimple                                          # noqa: E402
from domain.especificaciones import ContratoEstaFirmado, SituacionContratacion                  # noqa: E402
from domain.maquina_estados import MaquinaEstados, TransicionNoPermitida                        # noqa: E402
from domain.valores import EstadoContrato as EC, ErrorDominio, TipoSolicitud, Importe           # noqa: E402

TABLA_ESPERADA = {
    (EC.EN_PREPARACION, AccionContrato.FIRMAR): EC.FIRMADO,
    (EC.FIRMADO, AccionContrato.CONFIRMAR_CONTRATACION): EC.CONTRATACION_CONFIRMADA,
    (EC.FIRMADO, AccionContrato.CERRAR_SIN_CONFIRMAR): EC.CERRADO_SIN_CONFIRMAR,
}
REPETICIONES = {(EC.CONTRATACION_CONFIRMADA, AccionContrato.CONFIRMAR_CONTRATACION)}

# Mensajes existentes de Contrato (v8), escritos literalmente para no depender de la propia tabla.
NO_FIRMABLE = "Solo un contrato En preparación puede firmarse."
SIN_SEGUIMIENTO = "Debe existir un seguimiento del anticipo antes de cerrar la contratación (CA-020)."
DENTRO_DE_24H = "El Cliente todavía dispone de 24 horas naturales desde el contacto para efectuar el anticipo (CA-021)."
PAGO_A_TIEMPO = "El Cliente efectuó el anticipo dentro del plazo; queda pendiente de registro o verificación (CA-021)."
SEGUIMIENTO_NO_FIRMADO = "El seguimiento del anticipo solo aplica a un contrato firmado."
PLAZO_NO_VENCIDO = "El plazo de tres días hábiles para el anticipo no ha vencido (CA-020)."
ANEXO_NO_CONFIRMADA = "Solo se registran anexos sobre una contratación confirmada."
ANEXO_DUPLICADO = "La operación ya tiene un anexo registrado."
PENDIENTES = ['contrato firmado', 'política de no reembolso comunicada', 'anticipo del 30 % registrado y verificado']

ANTICIPO_OK = EvidenciaAnticipo(True, True, True)
SIN_ANTICIPO = EvidenciaAnticipo(False, False, False)
DESPUES = LIMITE + timedelta(hours=1)


def antes(estado, comunicada=True, con_seguimiento=False):
    """Observación de un Contrato recién construido en ese estado (para comparar después de un rechazo)."""
    return observar(contrato_en(estado, comunicada, con_seguimiento))


# ======================================================================= tabla
class TablaDeTransiciones(unittest.TestCase):
    def test_tabla_implementada(self):
        self.assertEqual({(t.origen, t.accion): t.destino for t in MAQUINA_CONTRATO.transiciones}, TABLA_ESPERADA)
        self.assertEqual(set(MAQUINA_CONTRATO.repeticiones_idempotentes), REPETICIONES)

    def test_estados_terminales(self):
        self.assertEqual(MAQUINA_CONTRATO.estados_terminales, {EC.CONTRATACION_CONFIRMADA, EC.CERRADO_SIN_CONFIRMAR})

    def test_estados_existentes_y_acciones_que_son_metodos_de_contrato(self):
        self.assertEqual(set(MAQUINA_CONTRATO.estados), set(EC))
        for accion in AccionContrato:
            with self.subTest(accion=accion):
                self.assertTrue(callable(getattr(Contrato, accion.value, None)))

    def test_operaciones_que_no_cambian_el_estado_no_estan_en_la_tabla(self):
        nombres = {a.value for a in MAQUINA_CONTRATO.acciones}
        for metodo in ('registrar_seguimiento_anticipo', 'registrar_anexo', 'registrar_comunicacion_politica'):
            self.assertNotIn(metodo, nombres)

    def test_reutiliza_la_maquina_generica_de_e3a(self):
        self.assertIsInstance(MAQUINA_CONTRATO, MaquinaEstados)
        self.assertIs(mod_contrato.MaquinaEstados, MaquinaEstados)


class UsoRealDeLaMaquina(unittest.TestCase):
    def _sin(self, accion):
        return MaquinaEstados(EC, [t for t in MAQUINA_CONTRATO.transiciones if t.accion != accion],
                              MAQUINA_CONTRATO.repeticiones_idempotentes)

    def test_firmar_consulta_la_maquina(self):
        c = contrato_en(EC.EN_PREPARACION)
        with mock.patch.object(mod_contrato, 'MAQUINA_CONTRATO', self._sin(AccionContrato.FIRMAR)):
            with self.assertRaises(TransicionNoPermitida):
                c.firmar(NUEVA_FIRMA)
        self.assertEqual(observar(c), antes(EC.EN_PREPARACION))

    def test_cerrar_consulta_la_maquina(self):
        c = contrato_en(EC.FIRMADO, con_seguimiento=True)
        with mock.patch.object(mod_contrato, 'MAQUINA_CONTRATO', self._sin(AccionContrato.CERRAR_SIN_CONFIRMAR)):
            with self.assertRaises(TransicionNoPermitida):
                c.cerrar_sin_confirmar(DESPUES)
        self.assertEqual(observar(c), antes(EC.FIRMADO, con_seguimiento=True))

    def test_confirmar_consulta_la_maquina_para_el_destino(self):
        c = contrato_en(EC.FIRMADO)
        with mock.patch.object(mod_contrato, 'MAQUINA_CONTRATO', self._sin(AccionContrato.CONFIRMAR_CONTRATACION)):
            with self.assertRaises(TransicionNoPermitida):
                c.confirmar_contratacion(ANTICIPO_OK, AHORA)
        self.assertEqual(observar(c), antes(EC.FIRMADO))

    def test_la_repeticion_la_declara_la_maquina(self):
        """Sin la repetición en la tabla, confirmar en Contratación confirmada llegaría a la Specification."""
        sin_repeticion = MaquinaEstados(EC, MAQUINA_CONTRATO.transiciones)
        with mock.patch.object(mod_contrato, 'MAQUINA_CONTRATO', sin_repeticion):
            self.assertEqual(contrato_en(EC.CONTRATACION_CONFIRMADA).confirmar_contratacion(ANTICIPO_OK, AHORA),
                             ['contrato firmado'])


# ======================================================================= transiciones válidas
class TransicionesValidas(unittest.TestCase):
    def test_firmar(self):
        c = contrato_en(EC.EN_PREPARACION)
        c.firmar(NUEVA_FIRMA)
        self.assertEqual((c.estado, c.fecha_firma), (EC.FIRMADO, NUEVA_FIRMA))
        eventos = c.extraer_eventos()
        self.assertEqual([(e.nombre, e.evento_ref) for e in eventos], [('ContratoFirmado', 'EV-1')])

    def test_confirmar_contratacion(self):
        c = contrato_en(EC.FIRMADO)
        self.assertEqual(c.confirmar_contratacion(ANTICIPO_OK, AHORA), [])
        self.assertEqual(c.estado, EC.CONTRATACION_CONFIRMADA)
        self.assertEqual([(e.nombre, e.evento_ref) for e in c.extraer_eventos()], [('ContratacionConfirmada', 'EV-1')])

    def test_cerrar_sin_confirmar(self):
        c = contrato_en(EC.FIRMADO, con_seguimiento=True)
        c.cerrar_sin_confirmar(DESPUES)
        self.assertEqual(c.estado, EC.CERRADO_SIN_CONFIRMAR)
        self.assertEqual([(e.nombre, e.evento_ref) for e in c.extraer_eventos()], [('ProcesoContratacionCerrado', 'EV-1')])

    def test_recorridos_completos(self):
        c = contrato_en(EC.EN_PREPARACION)
        c.firmar(FIRMA); c.confirmar_contratacion(ANTICIPO_OK, AHORA)
        self.assertEqual([e.nombre for e in c.extraer_eventos()], ['ContratoFirmado', 'ContratacionConfirmada'])
        c = contrato_en(EC.EN_PREPARACION)
        c.firmar(FIRMA); c.registrar_seguimiento_anticipo(CONTACTO, 'Contacto', True); c.cerrar_sin_confirmar(DESPUES)
        self.assertEqual((c.estado, [e.nombre for e in c.extraer_eventos()]),
                         (EC.CERRADO_SIN_CONFIRMAR, ['ContratoFirmado', 'ProcesoContratacionCerrado']))


# ======================================================================= acciones no permitidas
class AccionesNoPermitidas(unittest.TestCase):
    def test_firmar_fuera_de_en_preparacion_se_rechaza_sin_efectos(self):
        for nombre, estado, comunicada, seguimiento in variantes():
            if estado == EC.EN_PREPARACION:
                continue
            with self.subTest(variante=nombre):
                c = contrato_en(estado, comunicada, seguimiento)
                with self.assertRaises(ErrorDominio) as ctx:
                    c.firmar(NUEVA_FIRMA)
                self.assertEqual(str(ctx.exception), NO_FIRMABLE)
                self.assertEqual(observar(c), antes(estado, comunicada, seguimiento))

    def test_cerrar_fuera_de_firmado_se_rechaza_sin_efectos(self):
        for nombre, estado, comunicada, seguimiento in variantes():
            if estado == EC.FIRMADO:
                continue
            for pagado in (False, True):
                with self.subTest(variante=nombre, pagado=pagado):
                    c = contrato_en(estado, comunicada, seguimiento)
                    with self.assertRaises(ErrorDominio) as ctx:
                        c.cerrar_sin_confirmar(DESPUES, pagado)
                    self.assertEqual(str(ctx.exception), SIN_SEGUIMIENTO)          # mensaje actual, también por estado
                    self.assertEqual(observar(c), antes(estado, comunicada, seguimiento))

    def test_estados_terminales_no_admiten_transiciones(self):
        for estado in MAQUINA_CONTRATO.estados_terminales:
            for accion in AccionContrato:
                with self.subTest(estado=estado, accion=accion):
                    self.assertFalse(MAQUINA_CONTRATO.permite(estado, accion))
        for estado in (EC.CONTRATACION_CONFIRMADA, EC.CERRADO_SIN_CONFIRMAR):
            with self.assertRaises(ErrorDominio):
                contrato_en(estado).firmar(NUEVA_FIRMA)
            with self.assertRaises(ErrorDominio):
                contrato_en(estado, con_seguimiento=True).cerrar_sin_confirmar(DESPUES)


# ======================================================================= confirmación: pendientes y repetición
class ConfirmacionYPendientes(unittest.TestCase):
    def test_desde_en_preparacion_o_cerrado_devuelve_pendientes_sin_excepcion(self):
        for estado in (EC.EN_PREPARACION, EC.CERRADO_SIN_CONFIRMAR):
            for comunicada, evidencia, esperados in ((True, ANTICIPO_OK, PENDIENTES[:1]),
                                                     (False, SIN_ANTICIPO, PENDIENTES),
                                                     (False, ANTICIPO_OK, PENDIENTES[:2])):
                with self.subTest(estado=estado, comunicada=comunicada, evidencia=evidencia):
                    c = contrato_en(estado, comunicada)
                    self.assertEqual(c.confirmar_contratacion(evidencia, AHORA), esperados)   # AR-04 conservado
                    self.assertEqual(observar(c), antes(estado, comunicada))                  # sin cambios ni eventos

    def test_desde_firmado_con_pendientes_no_cambia(self):
        c = contrato_en(EC.FIRMADO, comunicada=False)
        self.assertEqual(c.confirmar_contratacion(EvidenciaAnticipo(True, True, False), AHORA), PENDIENTES[1:])
        self.assertEqual(observar(c), antes(EC.FIRMADO, comunicada=False))

    def test_confirmacion_repetida_devuelve_lista_vacia_sin_segundo_evento(self):
        c = contrato_en(EC.FIRMADO)
        self.assertEqual(c.confirmar_contratacion(ANTICIPO_OK, AHORA), [])
        self.assertEqual([e.nombre for e in c.extraer_eventos()], ['ContratacionConfirmada'])
        for evidencia in (ANTICIPO_OK, SIN_ANTICIPO):
            self.assertEqual(c.confirmar_contratacion(evidencia, AHORA + timedelta(days=1)), [])
            self.assertEqual(c.estado, EC.CONTRATACION_CONFIRMADA)
            self.assertEqual(c.extraer_eventos(), [])

    def test_la_repeticion_no_evalua_la_specification(self):
        """Aunque la Specification se cumpliera, la repetición devuelve [] sin cambiar el estado ni emitir eventos."""
        siempre = EspecificacionSimple(lambda s: True, 'x')
        with mock.patch.object(mod_contrato, 'CONTRATACION_CONFIRMABLE', siempre):
            c = contrato_en(EC.CONTRATACION_CONFIRMADA)
            self.assertEqual(c.confirmar_contratacion(SIN_ANTICIPO, AHORA), [])
            self.assertEqual(observar(c), antes(EC.CONTRATACION_CONFIRMADA))

    def test_la_specification_sigue_decidiendo_los_pendientes(self):
        falsa = EspecificacionSimple(lambda s: False, 'requisito sustituido')
        with mock.patch.object(mod_contrato, 'CONTRATACION_CONFIRMABLE', falsa):
            c = contrato_en(EC.FIRMADO)
            self.assertEqual(c.confirmar_contratacion(ANTICIPO_OK, AHORA), ['requisito sustituido'])
            self.assertEqual(observar(c), antes(EC.FIRMADO))


class CoherenciaSpecificationYMaquina(unittest.TestCase):
    """ContratoEstaFirmado (E2) y la transición real de confirmación coinciden; la repetición es aparte."""

    def test_transicion_real_coincide_con_contrato_firmado(self):
        for estado in EC:
            with self.subTest(estado=estado):
                firmado = ContratoEstaFirmado().es_satisfecha_por(SituacionContratacion(contrato_en(estado), ANTICIPO_OK))
                self.assertEqual(MAQUINA_CONTRATO.permite(estado, AccionContrato.CONFIRMAR_CONTRATACION), firmado)
        self.assertEqual({e for e in EC if MAQUINA_CONTRATO.permite(e, AccionContrato.CONFIRMAR_CONTRATACION)}, {EC.FIRMADO})

    def test_repeticion_solo_en_contratacion_confirmada(self):
        repeticiones = {e for e in EC if MAQUINA_CONTRATO.es_repeticion(e, AccionContrato.CONFIRMAR_CONTRATACION)}
        self.assertEqual(repeticiones, {EC.CONTRATACION_CONFIRMADA})
        self.assertFalse(ContratoEstaFirmado().es_satisfecha_por(
            SituacionContratacion(contrato_en(EC.CONTRATACION_CONFIRMADA), ANTICIPO_OK)))

    def test_ningun_estado_es_transicion_y_repeticion(self):
        for estado in EC:
            for accion in AccionContrato:
                with self.subTest(estado=estado, accion=accion):
                    self.assertFalse(MAQUINA_CONTRATO.permite(estado, accion) and MAQUINA_CONTRATO.es_repeticion(estado, accion))


# ======================================================================= cierre sin confirmar
class CierreSinConfirmar(unittest.TestCase):
    def assertRechazo(self, c, ahora, pagado, mensaje, **estado_inicial):
        referencia = antes(**estado_inicial)
        with self.assertRaises(ErrorDominio) as ctx:
            c.cerrar_sin_confirmar(ahora, pagado)
        self.assertEqual(str(ctx.exception), mensaje)
        self.assertEqual(observar(c), referencia)

    def test_sin_seguimiento(self):
        self.assertRechazo(contrato_en(EC.FIRMADO), DESPUES, False, SIN_SEGUIMIENTO, estado=EC.FIRMADO)

    def test_dentro_y_en_el_limite_de_24_horas(self):
        for ahora in (CONTACTO, LIMITE - timedelta(seconds=1), LIMITE):
            with self.subTest(ahora=ahora):
                self.assertRechazo(contrato_en(EC.FIRMADO, con_seguimiento=True), ahora, False, DENTRO_DE_24H,
                                   estado=EC.FIRMADO, con_seguimiento=True)

    def test_justo_despues_del_limite_cierra(self):
        c = contrato_en(EC.FIRMADO, con_seguimiento=True)
        c.cerrar_sin_confirmar(LIMITE + timedelta(seconds=1))
        self.assertEqual(c.estado, EC.CERRADO_SIN_CONFIRMAR)

    def test_pago_efectuado_a_tiempo_impide_el_cierre_y_se_confirma_al_verificarse(self):
        c = contrato_en(EC.FIRMADO, con_seguimiento=True)
        self.assertRechazo(c, DESPUES, True, PAGO_A_TIEMPO, estado=EC.FIRMADO, con_seguimiento=True)
        self.assertEqual(c.confirmar_contratacion(ANTICIPO_OK, DESPUES + timedelta(days=1)), [])   # verificado después
        self.assertEqual(c.estado, EC.CONTRATACION_CONFIRMADA)

    def test_orden_de_los_rechazos(self):
        # estado / seguimiento → 24 horas → pago a tiempo (orden actual)
        self.assertRechazo(contrato_en(EC.EN_PREPARACION), LIMITE - timedelta(hours=1), True, SIN_SEGUIMIENTO,
                           estado=EC.EN_PREPARACION)
        self.assertRechazo(contrato_en(EC.FIRMADO), LIMITE - timedelta(hours=1), True, SIN_SEGUIMIENTO, estado=EC.FIRMADO)
        self.assertRechazo(contrato_en(EC.FIRMADO, con_seguimiento=True), LIMITE - timedelta(hours=1), True, DENTRO_DE_24H,
                           estado=EC.FIRMADO, con_seguimiento=True)

    def test_ar03_las_24_horas_se_cuentan_desde_el_primer_seguimiento(self):
        c = contrato_en(EC.FIRMADO, con_seguimiento=True)
        c.registrar_seguimiento_anticipo(CONTACTO + timedelta(hours=20), 'Segundo contacto', True)
        self.assertEqual(c.limite_pago_anticipo(), LIMITE)
        c.cerrar_sin_confirmar(LIMITE + timedelta(minutes=1))          # aún no pasan 24 h desde el segundo contacto
        self.assertEqual(c.estado, EC.CERRADO_SIN_CONFIRMAR)

    def test_pago_a_tiempo_verificado_despues_a_traves_del_servicio(self):     # BN-009, CA-021, SE-010
        from test_reglas_corregidas import Escenario, T0
        e = Escenario()
        contacto = T0 + timedelta(days=6)
        self.assertTrue(e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto, 'Contacto', False).exito)
        e.s.contratacion.registrar_comunicacion_politica_no_reembolso(e.contrato_id, T0)
        ob = e.obligacion('Anticipo')
        pago = e.s.pagos.registrar_y_verificar_pago(e.ec_id, ob.obligacion_id, Importe(D('3000.00')),
                                                    contacto + timedelta(hours=20), 'C-ANT',
                                                    contacto + timedelta(hours=30), verificar_ahora=False)
        e.d.despachar()
        r = e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, contacto + timedelta(hours=31), 'Sin pago', True)
        self.assertEqual((r.exito, r.mensaje), (False, PAGO_A_TIEMPO))
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EC.FIRMADO)
        e.s.pagos.verificar_pago_registrado(e.ec_id, pago.datos['pago_id'], contacto + timedelta(hours=32)); e.d.despachar()
        self.assertEqual(e.app.repos.contratos.obtener_por_id(e.contrato_id).estado, EC.CONTRATACION_CONFIRMADA)


# ======================================================================= operaciones que no cambian el estado
class OperacionesFueraDeLaTabla(unittest.TestCase):
    def test_seguimiento_del_anticipo(self):
        for estado in (EC.EN_PREPARACION, EC.CONTRATACION_CONFIRMADA, EC.CERRADO_SIN_CONFIRMAR):
            with self.subTest(estado=estado):
                c = contrato_en(estado)
                with self.assertRaises(ErrorDominio) as ctx:
                    c.registrar_seguimiento_anticipo(AHORA, 'Contacto', True)
                self.assertEqual(str(ctx.exception), SEGUIMIENTO_NO_FIRMADO)
                self.assertEqual(observar(c), antes(estado))
        c = contrato_en(EC.FIRMADO)
        with self.assertRaises(ErrorDominio) as ctx:
            c.registrar_seguimiento_anticipo(AHORA, 'Contacto', False)
        self.assertEqual(str(ctx.exception), PLAZO_NO_VENCIDO)
        self.assertEqual(observar(c), antes(EC.FIRMADO))
        c.registrar_seguimiento_anticipo(AHORA, 'Contacto', True)
        self.assertEqual((c.estado, c.seguimientos_anticipo, c.extraer_eventos()), (EC.FIRMADO, [(AHORA, 'Contacto')], []))

    def test_anexos(self):
        for estado in (EC.EN_PREPARACION, EC.FIRMADO, EC.CERRADO_SIN_CONFIRMAR):
            with self.subTest(estado=estado):
                c = contrato_en(estado)
                with self.assertRaises(ErrorDominio) as ctx:
                    c.registrar_anexo('AX-9', TipoSolicitud.CAMBIO, 'SC-9', 'x', AHORA)
                self.assertEqual(str(ctx.exception), ANEXO_NO_CONFIRMADA)
                self.assertEqual(observar(c), antes(estado))
        c = contrato_en(EC.CONTRATACION_CONFIRMADA)
        with self.assertRaises(ErrorDominio) as ctx:
            c.registrar_anexo('AX-9', TipoSolicitud.CAMBIO, 'SC-0', 'x', AHORA)          # SC-0 ya tiene anexo
        self.assertEqual(str(ctx.exception), ANEXO_DUPLICADO)
        self.assertEqual(observar(c), antes(EC.CONTRATACION_CONFIRMADA))
        a = c.registrar_anexo('AX-9', TipoSolicitud.CAMBIO, 'SC-9', 'x', AHORA)
        self.assertEqual((a.anexo_id, c.estado), ('AX-9', EC.CONTRATACION_CONFIRMADA))
        self.assertEqual([e.nombre for e in c.extraer_eventos()], ['AnexoContratoRegistrado'])

    def test_ar01_comunicacion_de_la_politica_no_valida_el_estado(self):
        """AR-01 registrado: se conserva el comportamiento actual en todos los estados."""
        for estado in EC:
            with self.subTest(estado=estado):
                c = contrato_en(estado, comunicada=False)
                c.registrar_comunicacion_politica(AHORA)
                self.assertTrue(c.politica.comunicada())
                self.assertEqual((c.estado, c.extraer_eventos()), (estado, []))


# ======================================================================= conservación y aislamiento
class ConservacionDelComportamiento(unittest.TestCase):
    """Referencia capturada con v8 + E1 + E2 + E3A antes de E3B: 336 combinaciones, todas idénticas."""

    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA_CONTRATO, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = json.loads(json.dumps(capturar_comportamiento_contrato(), ensure_ascii=False))

    def test_cobertura(self):
        self.assertEqual(len(self.referencia), len(variantes()) * len(acciones()))
        self.assertEqual(len(self.referencia), 336)
        self.assertEqual(set(self.actual), set(self.referencia))

    def test_resultados_identicos(self):
        for clave, esperado in self.referencia.items():
            with self.subTest(caso=clave):
                self.assertEqual(self.actual[clave], esperado)

    def test_ningun_rechazo_modifica_el_agregado(self):
        for clave, r in self.actual.items():
            if 'error' not in r:
                continue
            nombre = clave.split(' | ')[0]
            _, estado, comunicada, seguimiento = next(v for v in variantes() if v[0] == nombre)
            with self.subTest(caso=clave):
                inicial = json.loads(json.dumps(antes(estado, comunicada, seguimiento)))
                self.assertEqual({k: r[k] for k in inicial}, inicial)

    def test_referencia_de_e2_sin_cambios(self):
        from apoyo_especificaciones import capturar_comportamiento, RUTA_REFERENCIA
        with open(RUTA_REFERENCIA, encoding='utf-8') as f:
            self.assertEqual(json.loads(json.dumps(capturar_comportamiento(), ensure_ascii=False)), json.load(f))


class AislamientoDelPaqueteCSV(unittest.TestCase):
    def test_estados_y_acciones_son_los_de_eventos_nova(self):
        nombres = {e.name for e in MAQUINA_CONTRATO.estados} | {a.name for a in AccionContrato}
        for ajeno in ('COTIZADO', 'CONTRATADO', 'REALIZADO', 'CANCELADO', 'APROBAR', 'COMPLETAR', 'REPETIR_APROBACION',
                      'SALTAR_ESTADO'):
            self.assertNotIn(ajeno, nombres)
        self.assertEqual({e.value for e in MAQUINA_CONTRATO.estados},
                         {'En preparación', 'Firmado', 'Contratación confirmada', 'Cerrado sin confirmar'})

    def test_contrato_no_lee_el_paquete(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', 'contrato.py'),
                  encoding='utf8') as f:
            texto = f.read()
        for ajeno in ('paquete_pia', 'COTIZADO', '.csv'):
            self.assertNotIn(ajeno, texto)


if __name__ == '__main__':
    unittest.main()
