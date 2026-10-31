"""Etapa E3D — State Machines de EstadoCuenta: ObligacionPago, Pago y Devolucion.

Comprueba las tres tablas implementadas y su coherencia con el mapa de dominio U3, que cada método consulta la máquina
antes de modificar el agregado, cada transición válida, los pares no permitidos, los rechazos actuales sin efectos, los
casos obligatorios del plan (pago adicional sobre una obligación Liquidada, devolución Efectuada repetida, vencimiento
masivo sin cambios parciales, regularización y cierre sin realizar según SE-012/AR-07), los puntos pendientes
P-E3D-01 a P-E3D-03 tal como están, y la conservación del comportamiento anterior a E3D."""
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
from apoyo_esperados_oraculo import esperado as esperado_oraculo                          # noqa: E402
from apoyo_maquina_estados_estado_cuenta import (Constructor, variantes, acciones, observar, construir,          # noqa: E402
                                                 capturar_comportamiento_estado_cuenta, RUTA_REFERENCIA_ESTADO_CUENTA,
                                                 M, ANTICIPO_A_TIEMPO, ANTICIPO_TARDIO, ANTES_LIMITE, DESPUES_LIMITE,
                                                 DENTRO_VENTANA, DESPUES_VENTANA, FIN_VENTANA, REVISION,
                                                 REVISION_TEMPRANA, CAMBIO_A_TIEMPO, CIERRE, EFECTUADA, CONSULTA,
                                                 COMUNICADO)

import domain.estado_cuenta as mod_ec                                                                  # noqa: E402
from domain.estado_cuenta import (MAQUINA_OBLIGACION_PAGO, MAQUINA_PAGO, MAQUINA_DEVOLUCION,           # noqa: E402
                                  AccionObligacionPago as AO, AccionPago as AP, AccionDevolucion as AD)
from domain.maquina_estados import MaquinaEstados, TransicionNoPermitida                              # noqa: E402
from domain.valores import (ErrorDominio, EstadoObligacionPago as EO, EstadoPago as EPg,              # noqa: E402
                            EstadoDevolucion as ED)

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

TABLA_OBLIGACION = {
    (EO.PENDIENTE, AO.LIQUIDAR_POR_PAGO): EO.LIQUIDADA,
    (EO.PENDIENTE, AO.VENCER): EO.VENCIDA,
    (EO.VENCIDA, AO.REGULARIZAR): EO.LIQUIDADA,
    (EO.PENDIENTE, AO.REGULARIZAR): EO.LIQUIDADA,
    (EO.PENDIENTE, AO.DEJAR_SIN_EFECTO): EO.SIN_EFECTO,
}
TABLA_PAGO = {
    (EPg.REGISTRADO, AP.VERIFICAR): EPg.VERIFICADO,
    (EPg.REGISTRADO, AP.RECHAZAR_IMPORTE): EPg.IMPORTE_INCORRECTO,
}
TABLA_DEVOLUCION = {(ED.PENDIENTE, AD.REGISTRAR_EFECTUADA): ED.EFECTUADA}
MAQUINAS = ((MAQUINA_OBLIGACION_PAGO, TABLA_OBLIGACION, EO, AO),
            (MAQUINA_PAGO, TABLA_PAGO, EPg, AP),
            (MAQUINA_DEVOLUCION, TABLA_DEVOLUCION, ED, AD))

# Mensajes existentes (v8), escritos literalmente para no depender de la propia implementación.
NO_VERIFICABLE = "Solo se verifica un pago registrado que está pendiente de verificación."
SIN_EFECTO_O_INEXISTENTE = "La obligación no existe o quedó sin efecto."
VENTANA_VIGENTE = "La ventana de 24 horas naturales todavía está vigente."
YA_REGISTRADO = "El resultado de esta regularización ya fue registrado."
SIN_REGULARIZACION = "No hay una regularización en curso."
PENDIENTES_DE_VERIFICAR = ("Hay pagos efectuados dentro del plazo pendientes de verificación; "
                           "Administración debe verificarlos antes de registrar el resultado.")
SIN_SALDO_VENCIDO = "El protocolo de cobro requiere un saldo vencido (CA-025)."
VENTANA_EXISTENTE = "Ya existe una ventana de regularización vigente."


def en(nombre):
    return construir(nombre)


def estados(c):
    return {i: o.estado for i, o in c.ec.obligaciones.items()}


def nombres(eventos):
    return [e.nombre for e in eventos]


def falla_en_la_llamada(n, maquina):
    """transitar() real salvo en la llamada número n, que lanza TransicionNoPermitida."""
    real, cuenta = maquina.transitar, {'n': 0}

    def transitar(origen, accion):
        cuenta['n'] += 1
        if cuenta['n'] == n:
            raise TransicionNoPermitida("falla simulada", origen, accion)
        return real(origen, accion)
    return transitar


# ======================================================================= tablas
class TablasImplementadas(unittest.TestCase):
    def test_tablas_exactas(self):
        for maquina, tabla, _, _ in MAQUINAS:
            with self.subTest(maquina=maquina.nombre):
                self.assertEqual({(t.origen, t.accion): t.destino for t in maquina.transiciones}, tabla)

    def test_estados_son_las_enumeraciones_existentes(self):
        for maquina, _, enum, _ in MAQUINAS:
            with self.subTest(maquina=maquina.nombre):
                self.assertEqual(set(maquina.estados), set(enum))

    def test_estados_terminales(self):
        self.assertEqual(MAQUINA_OBLIGACION_PAGO.estados_terminales, {EO.LIQUIDADA, EO.SIN_EFECTO})
        self.assertEqual(MAQUINA_PAGO.estados_terminales, {EPg.VERIFICADO, EPg.IMPORTE_INCORRECTO})
        self.assertEqual(MAQUINA_DEVOLUCION.estados_terminales, {ED.EFECTUADA})

    def test_repeticiones_idempotentes(self):
        self.assertEqual(MAQUINA_OBLIGACION_PAGO.repeticiones_idempotentes, frozenset())   # Liquidada + pago: no es repetición
        self.assertEqual(MAQUINA_PAGO.repeticiones_idempotentes, frozenset())
        self.assertEqual(MAQUINA_DEVOLUCION.repeticiones_idempotentes, {(ED.EFECTUADA, AD.REGISTRAR_EFECTUADA)})

    def test_acciones_aprobadas(self):
        self.assertEqual({a.name for a in AO}, {'LIQUIDAR_POR_PAGO', 'VENCER', 'REGULARIZAR', 'DEJAR_SIN_EFECTO'})
        self.assertEqual({a.name for a in AP}, {'VERIFICAR', 'RECHAZAR_IMPORTE'})
        self.assertEqual({a.name for a in AD}, {'REGISTRAR_EFECTUADA'})

    def test_regularizar_tiene_dos_origenes(self):                         # D-E3D-4
        self.assertEqual({o for (o, a) in TABLA_OBLIGACION if a == AO.REGULARIZAR}, {EO.VENCIDA, EO.PENDIENTE})

    def test_tablas_a_nivel_de_modulo_con_la_maquina_generica(self):       # D-E3D-1
        for maquina, _, _, _ in MAQUINAS:
            self.assertIs(type(maquina), MaquinaEstados)
        self.assertFalse(hasattr(mod_ec.EstadoCuenta, 'MAQUINA'))

    def test_coherencia_con_el_mapa_de_dominio(self):
        """Las flechas entre estados de la página «04 — Detalle C» son exactamente las transiciones de las tres tablas."""
        arbol = ET.parse(os.path.join(RAIZ, 'diagramas', 'dominio', 'mapa-dominio.drawio'))
        pagina = next(d for d in arbol.getroot().iter('diagram') if d.get('name', '').startswith('04'))
        texto = {c.get('id'): re.sub(r'<[^>]+>', ' ', html.unescape(c.get('value') or '')).strip()
                 for c in pagina.iter('mxCell')}
        valores = {e.value for _, _, enum, _ in MAQUINAS for e in enum}
        flechas = {(texto.get(c.get('source')), texto.get(c.get('target'))) for c in pagina.iter('mxCell')
                   if c.get('edge') == '1' and texto.get(c.get('source')) in valores and texto.get(c.get('target')) in valores}
        tablas = {(o.value, d.value) for _, tabla, _, _ in MAQUINAS for (o, _), d in tabla.items()}
        self.assertEqual(flechas, tablas)


class ParesNoPermitidos(unittest.TestCase):
    def test_todo_par_fuera_de_la_tabla_se_rechaza(self):
        for maquina, tabla, enum, acciones_ in MAQUINAS:
            for estado in enum:
                for accion in acciones_:
                    if (estado, accion) in tabla or maquina.es_repeticion(estado, accion):
                        continue
                    with self.subTest(maquina=maquina.nombre, estado=estado, accion=accion):
                        self.assertFalse(maquina.permite(estado, accion))
                        with self.assertRaises(TransicionNoPermitida) as ctx:
                            maquina.transitar(estado, accion)
                        self.assertIsInstance(ctx.exception, ErrorDominio)

    def test_mensaje_de_verificar_es_el_existente(self):
        for estado in (EPg.VERIFICADO, EPg.IMPORTE_INCORRECTO):
            with self.assertRaises(TransicionNoPermitida) as ctx:
                MAQUINA_PAGO.validar(estado, AP.VERIFICAR)
            self.assertEqual(str(ctx.exception), NO_VERIFICABLE)


# ======================================================================= uso real de las máquinas
class UsoRealDeLasMaquinas(unittest.TestCase):
    """Con la acción retirada de la tabla, el método se rechaza y el agregado queda igual: la máquina se consulta
    antes de modificar nada."""

    def _sin(self, maquina, accion):
        return MaquinaEstados(maquina.estados, [t for t in maquina.transiciones if t.accion != accion],
                              repeticiones_idempotentes=maquina.repeticiones_idempotentes)

    def test_cada_metodo_consulta_su_maquina(self):
        casos = [
            ('MAQUINA_OBLIGACION_PAGO', AO.LIQUIDAR_POR_PAGO, 'saldo_pendiente',
             lambda c: c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(7000), ANTES_LIMITE, 'C', True)),
            ('MAQUINA_OBLIGACION_PAGO', AO.VENCER, 'saldo_y_sustitucion_pendientes',
             lambda c: c.ec.registrar_vencimiento_saldo(DESPUES_LIMITE)),
            ('MAQUINA_OBLIGACION_PAGO', AO.REGULARIZAR, 'ventana_pagos_completos_a_tiempo',
             lambda c: c.ec.resolver_regularizacion(REVISION)),
            ('MAQUINA_OBLIGACION_PAGO', AO.DEJAR_SIN_EFECTO, 'cambio_pendiente',
             lambda c: c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)),
            ('MAQUINA_PAGO', AP.VERIFICAR, 'saldo_pendiente',
             lambda c: c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(2000), ANTES_LIMITE, 'C', True)),
            ('MAQUINA_PAGO', AP.VERIFICAR, 'saldo_pago_a_tiempo_sin_verificar',
             lambda c: c.ec.verificar_pago_registrado('PG-2', REVISION)),
            ('MAQUINA_DEVOLUCION', AD.REGISTRAR_EFECTUADA, 'cambio_cerrado_con_devolucion_pendiente',
             lambda c: c.ec.registrar_devolucion_efectuada('DV-1', CONSULTA, 'CMP')),
        ]
        for nombre_maquina, accion, variante, llamada in casos:
            with self.subTest(accion=accion, variante=variante):
                c = en(variante)
                antes = observar(en(variante).ec)
                with mock.patch.object(mod_ec, nombre_maquina, self._sin(getattr(mod_ec, nombre_maquina), accion)):
                    with self.assertRaises(TransicionNoPermitida):
                        llamada(c)
                self.assertEqual(observar(c.ec), antes)

    def test_no_quedan_asignaciones_directas_de_estado(self):
        """En EstadoCuenta los estados se asignan solo con destinos devueltos por las máquinas."""
        with open(os.path.join(RAIZ, 'src', 'domain', 'estado_cuenta.py'), encoding='utf-8') as f:
            arbol = ast.parse(f.read())
        clase = next(n for n in arbol.body if isinstance(n, ast.ClassDef) and n.name == 'EstadoCuenta')
        directas = []
        for n in ast.walk(clase):
            if isinstance(n, ast.Assign):
                for valor in (n.value.elts if isinstance(n.value, ast.Tuple) else [n.value]):
                    if (isinstance(valor, ast.Attribute) and isinstance(valor.value, ast.Name)
                            and valor.value.id in ('EO', 'EPg', 'ED')):
                        directas.append(ast.unparse(n))
        self.assertEqual(directas, [])


# ======================================================================= transiciones válidas
class TransicionesValidas(unittest.TestCase):
    def test_liquidar_por_pago(self):                                        # CA-018, CA-026
        c = en('saldo_pendiente')
        p = c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(7000), ANTES_LIMITE, 'C', True)
        self.assertEqual((p.estado, c.ec.obligaciones['OB-S'].estado), (EPg.VERIFICADO, EO.LIQUIDADA))
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['PagoVerificado'])

    def test_liquidar_con_pagos_parciales_acumulados(self):
        c = en('saldo_pago_parcial')
        c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(5000), ANTES_LIMITE, 'C', True)
        self.assertEqual(c.ec.obligaciones['OB-S'].estado, EO.LIQUIDADA)

    def test_verificacion_posterior_de_pago_registrado(self):               # CA-021, CA-027
        c = en('saldo_pago_a_tiempo_sin_verificar')
        c.ec.verificar_pago_registrado('PG-2', CONSULTA)
        self.assertEqual((c.ec.pagos[1].estado, c.ec.obligaciones['OB-S'].estado), (EPg.VERIFICADO, EO.LIQUIDADA))
        self.assertEqual(c.ec.pagos[1].verificado_en, CONSULTA)
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['PagoVerificado'])

    def test_pago_parcial_de_anticipo(self):                                 # E-3 (sustituye al «importe incorrecto» de CA-019)
        c = en('anticipo_pendiente')
        p = c.ec.registrar_y_verificar_pago('PG-N', 'OB-A', M(1000), ANTICIPO_A_TIEMPO, 'C', True)
        self.assertEqual((p.estado, c.ec.obligaciones['OB-A'].estado), (EPg.VERIFICADO, EO.PENDIENTE))
        self.assertIn(p, c.ec.pagos)
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['PagoVerificado'])

    def test_vencer(self):                                                   # CA-023, CA-025
        c = en('saldo_pendiente')
        self.assertTrue(c.ec.registrar_vencimiento_saldo(DESPUES_LIMITE))
        self.assertEqual(c.ec.obligaciones['OB-S'].estado, EO.VENCIDA)
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['SaldoContratoOriginalVencido'])

    def test_regularizar_saldo_y_moratorios(self):                           # CA-027
        c = en('ventana_pagos_completos_a_tiempo')
        self.assertTrue(c.ec.resolver_regularizacion(REVISION))
        self.assertEqual((c.ec.obligaciones['OB-S'].estado, c.ec.obligaciones['OB-M'].estado), (EO.LIQUIDADA, EO.LIQUIDADA))
        self.assertEqual(c.ec.resultado_regularizacion, 'Regularizado')
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['SaldoVencidoRegularizado'])

    def test_dejar_sin_efecto(self):                                         # SE-012
        c = en('cambio_pendiente')
        self.assertEqual(c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv), [])
        self.assertEqual(c.ec.obligaciones['OB-C'].estado, EO.SIN_EFECTO)
        self.assertEqual(c.ec.extraer_eventos(), [])

    def test_devolucion_efectuada(self):                                     # SE-012, CA-098
        c = en('cambio_cerrado_con_devolucion_pendiente')
        c.ec.registrar_devolucion_efectuada('DV-1', EFECTUADA, 'CMP-DV')
        d = c.ec.devoluciones[0]
        self.assertEqual((d.estado, d.fecha_devolucion, d.comprobante), (ED.EFECTUADA, EFECTUADA, 'CMP-DV'))
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['DevolucionRegistrada'])


# ======================================================================= rechazos actuales sin efectos
class RechazosSinEfectos(unittest.TestCase):
    def _rechazo(self, variante, llamada, mensaje):
        c, antes = en(variante), observar(en(variante).ec)
        with self.assertRaises(ErrorDominio) as ctx:
            llamada(c)
        self.assertEqual(str(ctx.exception), mensaje)
        self.assertEqual(observar(c.ec), antes)

    def test_rechazos_con_los_mensajes_actuales(self):
        casos = [
            ('cambio_sin_efecto_sin_pagos', lambda c: c.ec.registrar_y_verificar_pago('PG-N', 'OB-C', M(300), CAMBIO_A_TIEMPO, 'C', True), SIN_EFECTO_O_INEXISTENTE),
            ('saldo_pendiente', lambda c: c.ec.registrar_y_verificar_pago('PG-N', 'OB-X', M(300), ANTES_LIMITE, 'C', True), SIN_EFECTO_O_INEXISTENTE),
            ('saldo_liquidado', lambda c: c.ec.verificar_pago_registrado('PG-2', CONSULTA), NO_VERIFICABLE),
            ('anticipo_importe_incorrecto', lambda c: c.ec.verificar_pago_registrado('PG-1', CONSULTA), NO_VERIFICABLE),
            ('saldo_pendiente', lambda c: c.ec.verificar_pago_registrado('PG-X', CONSULTA), NO_VERIFICABLE),
            ('saldo_pendiente', lambda c: c.ec.activar_protocolo_cobro('OB-M', M(700), COMUNICADO, 'x'), SIN_SALDO_VENCIDO),
            ('ventana_vigente', lambda c: c.ec.activar_protocolo_cobro('OB-M2', M(700), COMUNICADO, 'x'), VENTANA_EXISTENTE),
            ('saldo_vencido', lambda c: c.ec.resolver_regularizacion(REVISION), SIN_REGULARIZACION),
            ('ventana_pagos_completos_a_tiempo', lambda c: c.ec.resolver_regularizacion(REVISION_TEMPRANA), VENTANA_VIGENTE),
            ('ventana_pago_a_tiempo_sin_verificar', lambda c: c.ec.resolver_regularizacion(REVISION), PENDIENTES_DE_VERIFICAR),
            ('regularizado', lambda c: c.ec.resolver_regularizacion(CONSULTA), YA_REGISTRADO),
            ('no_regularizado', lambda c: c.ec.resolver_regularizacion(CONSULTA), YA_REGISTRADO),
        ]
        for variante, llamada, mensaje in casos:
            with self.subTest(variante=variante, mensaje=mensaje):
                self._rechazo(variante, llamada, mensaje)

    def test_verificar_obligacion_sin_efecto(self):
        c = Constructor().anticipo().saldo().cambio()
        c.pagar('OB-C', 300, CAMBIO_A_TIEMPO, verificar=False).cerrar('SC-1', True)
        c.ec.extraer_eventos()
        antes = observar(c.ec)
        with self.assertRaises(ErrorDominio) as ctx:
            c.ec.verificar_pago_registrado(c.ec.pagos[-1].pago_id, CONSULTA)
        self.assertEqual(str(ctx.exception), "La obligación quedó sin efecto.")
        self.assertEqual(observar(c.ec), antes)


# ======================================================================= casos obligatorios del plan (5.2)
class PagoAdicionalSobreObligacionLiquidada(unittest.TestCase):
    def _comprobar(self, c, p):
        self.assertEqual(p.estado, EPg.VERIFICADO)
        self.assertIn(p, c.ec.pagos)
        self.assertEqual(c.ec.obligaciones[p.obligacion_id].estado, EO.LIQUIDADA)
        eventos = c.ec.extraer_eventos()
        self.assertEqual(nombres(eventos), ['PagoVerificado'])                 # uno, no duplicado
        self.assertEqual(eventos[0].obligacion_id, p.obligacion_id)

    def test_registrado_y_verificado_en_una_operacion(self):
        for variante, ob_id, cantidad, fecha in (('saldo_liquidado', 'OB-S', 500, ANTES_LIMITE),
                                                 ('saldo_liquidado', 'OB-S', 500, DESPUES_LIMITE),
                                                 ('saldo_liquidado', 'OB-A', 3000, ANTICIPO_TARDIO),
                                                 ('cambio_liquidado', 'OB-C', 300, CAMBIO_A_TIEMPO),
                                                 ('regularizado', 'OB-M', 700, DESPUES_VENTANA)):
            with self.subTest(variante=variante, obligacion=ob_id, fecha=fecha):
                c = en(variante)
                self._comprobar(c, c.ec.registrar_y_verificar_pago('PG-N', ob_id, M(cantidad), fecha, 'C', True))

    def test_registrado_y_verificado_despues(self):
        c = en('saldo_liquidado')
        p = c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(500), ANTES_LIMITE, 'C', False)
        self.assertEqual((p.estado, c.ec.extraer_eventos()), (EPg.REGISTRADO, []))
        c.ec.verificar_pago_registrado('PG-N', CONSULTA)
        self._comprobar(c, p)

    def test_la_maquina_de_obligacion_no_se_consulta_si_ya_esta_liquidada(self):
        c = en('saldo_liquidado')
        with mock.patch.object(mod_ec.MAQUINA_OBLIGACION_PAGO, 'transitar', side_effect=AssertionError('consultada')):
            self._comprobar(c, c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(500), ANTES_LIMITE, 'C', True))

    def test_pago_adicional_menor_al_minimo_sobre_anticipo_liquidado(self):      # E-4: se verifica como adicional
        c = en('saldo_pendiente')
        p = c.ec.registrar_y_verificar_pago('PG-N', 'OB-A', M(1000), ANTICIPO_A_TIEMPO, 'C', True)
        self.assertEqual((p.estado, c.ec.obligaciones['OB-A'].estado), (EPg.VERIFICADO, EO.LIQUIDADA))
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['PagoVerificado'])

    def test_si_falla_una_transicion_no_hay_cambios_parciales(self):
        for variante, llamada in (
                ('saldo_pendiente', lambda c: c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(7000), ANTES_LIMITE, 'C', True)),
                ('saldo_pago_a_tiempo_sin_verificar', lambda c: c.ec.verificar_pago_registrado('PG-2', CONSULTA))):
            with self.subTest(variante=variante):
                c, antes = en(variante), observar(en(variante).ec)
                with mock.patch.object(mod_ec.MAQUINA_OBLIGACION_PAGO, 'transitar',
                                       falla_en_la_llamada(1, mod_ec.MAQUINA_OBLIGACION_PAGO)):
                    with self.assertRaises(TransicionNoPermitida):
                        llamada(c)
                self.assertEqual(observar(c.ec), antes)        # ni pago agregado o verificado, ni obligación, ni evento


class DevolucionEfectuadaRepetida(unittest.TestCase):
    def test_sin_segunda_devolucion_ni_evento(self):
        c = en('cambio_cerrado_con_devolucion_efectuada')
        antes = observar(en('cambio_cerrado_con_devolucion_efectuada').ec)
        for _ in range(2):
            self.assertIsNone(c.ec.registrar_devolucion_efectuada('DV-1', CONSULTA, 'OTRO'))
        self.assertEqual(observar(c.ec), antes)
        d = c.ec.devoluciones[0]
        self.assertEqual((len(c.ec.devoluciones), d.fecha_devolucion, d.comprobante), (1, EFECTUADA, 'CMP-DV'))

    def test_un_solo_evento_en_toda_la_secuencia(self):
        c = en('cambio_cerrado_con_devolucion_pendiente')
        c.ec.registrar_devolucion_efectuada('DV-1', EFECTUADA, 'CMP-DV')
        c.ec.registrar_devolucion_efectuada('DV-1', CONSULTA, 'OTRO')
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['DevolucionRegistrada'])


class VencimientoMasivo(unittest.TestCase):
    def test_todas_vencen_con_un_solo_evento(self):
        c = en('saldo_y_sustitucion_pendientes')
        self.assertTrue(c.ec.registrar_vencimiento_saldo(DESPUES_LIMITE))
        self.assertEqual((c.ec.obligaciones['OB-S'].estado, c.ec.obligaciones['OB-SP'].estado), (EO.VENCIDA, EO.VENCIDA))
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['SaldoContratoOriginalVencido'])

    def test_las_que_no_cumplen_conservan_su_comportamiento(self):
        casos = {
            'saldo_pendiente_y_sustitucion_liquidada': {'OB-S': EO.VENCIDA, 'OB-SP': EO.LIQUIDADA},
            'sustitucion_sin_plazo': {'OB-S': EO.VENCIDA, 'OB-SP': EO.PENDIENTE},          # sin plazo: no vence
        }
        for variante, esperado in casos.items():
            with self.subTest(variante=variante):
                c = en(variante)
                c.ec.registrar_vencimiento_saldo(DESPUES_LIMITE)
                self.assertEqual({i: estados(c)[i] for i in esperado}, esperado)
        c = Constructor().anticipo().saldo().sustitucion().pagar('OB-S', 7000, ANTES_LIMITE, False)
        c.ec.registrar_vencimiento_saldo(DESPUES_LIMITE)                                   # pagado a tiempo sin verificar
        self.assertEqual((estados(c)['OB-S'], estados(c)['OB-SP']), (EO.PENDIENTE, EO.VENCIDA))

    def test_antes_del_limite_no_vence_nada(self):
        c = en('saldo_y_sustitucion_pendientes')
        self.assertFalse(c.ec.registrar_vencimiento_saldo(ANTES_LIMITE))
        self.assertEqual(c.ec.extraer_eventos(), [])

    def test_sin_cambios_parciales_si_falla_una_transicion(self):
        for n in (1, 2):
            with self.subTest(falla_en=n):
                c = en('saldo_y_sustitucion_pendientes')
                antes = observar(en('saldo_y_sustitucion_pendientes').ec)
                with mock.patch.object(mod_ec.MAQUINA_OBLIGACION_PAGO, 'transitar',
                                       falla_en_la_llamada(n, mod_ec.MAQUINA_OBLIGACION_PAGO)):
                    with self.assertRaises(TransicionNoPermitida):
                        c.ec.registrar_vencimiento_saldo(DESPUES_LIMITE)
                self.assertEqual(observar(c.ec), antes)


class Regularizacion(unittest.TestCase):
    def test_no_regularizado(self):                                          # CA-027
        c = en('ventana_vigente')
        self.assertFalse(c.ec.resolver_regularizacion(REVISION))
        self.assertEqual((estados(c)['OB-S'], estados(c)['OB-M']), (EO.VENCIDA, EO.PENDIENTE))
        self.assertTrue(c.ec.no_regularizado_verificado)
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['PlazoRegularizacionVencido'])

    def test_pago_tardio_no_regulariza(self):
        c = en('ventana_pagos_tardios')
        self.assertFalse(c.ec.resolver_regularizacion(REVISION))
        self.assertEqual(estados(c)['OB-S'], EO.VENCIDA)

    def test_pago_posterior_al_resultado_se_verifica_sin_cambiar_el_resultado(self):
        c = en('no_regularizado')
        p = c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(7000), DESPUES_VENTANA, 'C', True)
        self.assertEqual((p.estado, estados(c)['OB-S'], c.ec.resultado_regularizacion),
                         (EPg.VERIFICADO, EO.VENCIDA, 'No regularizado'))
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['PagoVerificado'])

    def test_verificar_durante_la_ventana_no_liquida(self):
        c = en('ventana_vigente')
        c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(7000), DENTRO_VENTANA, 'C', True)
        c.ec.registrar_y_verificar_pago('PG-M', 'OB-M', M(700), DENTRO_VENTANA, 'C', True)
        self.assertEqual((estados(c)['OB-S'], estados(c)['OB-M']), (EO.VENCIDA, EO.PENDIENTE))

    def test_regularizacion_con_sustitucion_vencida(self):
        c = en('ventana_sustitucion_vencida')
        for ob, cantidad in (('OB-S', 7000), ('OB-SP', 500), ('OB-M', 700)):
            c.ec.registrar_y_verificar_pago('PG-' + ob, ob, M(cantidad), DENTRO_VENTANA, 'C', True)
        c.ec.extraer_eventos()
        self.assertTrue(c.ec.resolver_regularizacion(REVISION))
        self.assertEqual({i: e for i, e in estados(c).items() if i != 'OB-A'},
                         {'OB-S': EO.LIQUIDADA, 'OB-SP': EO.LIQUIDADA, 'OB-M': EO.LIQUIDADA})
        self.assertEqual(nombres(c.ec.extraer_eventos()), ['SaldoVencidoRegularizado'])

    def test_sin_cambios_parciales_si_falla_una_transicion(self):
        for n in (1, 2):           # 1: saldo vencido, 2: cargos moratorios
            with self.subTest(falla_en=n):
                c = en('ventana_pagos_completos_a_tiempo')
                antes = observar(en('ventana_pagos_completos_a_tiempo').ec)
                with mock.patch.object(mod_ec.MAQUINA_OBLIGACION_PAGO, 'transitar',
                                       falla_en_la_llamada(n, mod_ec.MAQUINA_OBLIGACION_PAGO)):
                    with self.assertRaises(TransicionNoPermitida):
                        c.ec.resolver_regularizacion(REVISION)
                self.assertEqual(observar(c.ec), antes)                     # ni resultado ni estados


class CierreSinRealizar(unittest.TestCase):                                # SE-012, CA-097 corregido (AR-07)
    def test_sin_efecto_con_y_sin_evento_cancelado(self):
        for cancelado in (False, True):
            with self.subTest(evento_cancelado=cancelado):
                c = en('cambio_pago_parcial')
                nuevas = c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, cancelado, c.dv)
                self.assertEqual(estados(c)['OB-C'], EO.SIN_EFECTO)
                self.assertEqual(len(nuevas), 0 if cancelado else 1)      # devolución solo con Evento no cancelado

    def test_liquidada_no_cambia_y_se_devuelve(self):
        c = en('cambio_liquidado')
        nuevas = c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)
        self.assertEqual((estados(c)['OB-C'], nuevas[0].estado, nuevas[0].importe), (EO.LIQUIDADA, ED.PENDIENTE, M(300)))

    def test_repetir_el_cierre_no_duplica_devoluciones(self):
        c = en('cambio_cerrado_con_devolucion_pendiente')
        self.assertEqual(c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv), [])
        self.assertEqual(len(c.ec.devoluciones), 1)

    def test_las_obligaciones_de_otros_origenes_no_cambian(self):
        c = en('cambio_pendiente')
        c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, True, c.dv)
        self.assertEqual((estados(c)['OB-A'], estados(c)['OB-S']), (EO.LIQUIDADA, EO.PENDIENTE))

    def test_sin_cambios_parciales_si_falla_una_transicion(self):
        c = Constructor().anticipo().saldo().cambio()
        c.ec.comunicar_solicitud_pago('OB-C2', mod_ec.CP.CARGO_CAMBIO_TARDIO, M(150), 'SC-1', CIERRE)
        c.ec.extraer_eventos()
        antes = observar(c.ec)
        with mock.patch.object(mod_ec.MAQUINA_OBLIGACION_PAGO, 'transitar',
                               falla_en_la_llamada(2, mod_ec.MAQUINA_OBLIGACION_PAGO)):
            with self.assertRaises(TransicionNoPermitida):
                c.ec.aplicar_cierre_sin_realizar('SC-1', CIERRE, False, c.dv)
        self.assertEqual(observar(c.ec), antes)


class PuntosPendientesSeConservan(unittest.TestCase):
    """P-E3D-01 a P-E3D-03: comportamiento actual, sin reglas nuevas."""

    def test_p_e3d_01_segunda_ventana_tras_no_regularizado(self):
        c = en('no_regularizado')
        with self.assertRaises(ErrorDominio) as ctx:
            c.ec.activar_protocolo_cobro('OB-M2', M(700), CONSULTA, 'Segundo aviso')
        self.assertEqual(str(ctx.exception), VENTANA_EXISTENTE)

    def test_p_e3d_02_instante_limite(self):
        c = en('ventana_vigente')
        c.ec.registrar_y_verificar_pago('PG-N', 'OB-S', M(7000), FIN_VENTANA, 'C', True)
        c.ec.registrar_y_verificar_pago('PG-M', 'OB-M', M(700), FIN_VENTANA, 'C', True)
        with self.assertRaises(ErrorDominio):
            c.ec.resolver_regularizacion(FIN_VENTANA)                      # la revisión exige un instante posterior
        self.assertTrue(c.ec.resolver_regularizacion(REVISION))            # el pago en el instante límite cuenta

    def test_p_e3d_03_sustitucion_vencida_no_queda_sin_efecto(self):
        c = en('saldo_y_sustitucion_vencidos')
        c.ec.aplicar_cierre_sin_realizar('SP-1', CIERRE, False, c.dv)
        self.assertEqual(estados(c)['OB-SP'], EO.VENCIDA)


# ======================================================================= conservación del comportamiento
class ConservacionDelComportamiento(unittest.TestCase):
    """Referencia capturada sobre el commit 8c80470 (antes de E3D): todas las combinaciones idénticas."""

    @classmethod
    def setUpClass(cls):
        with open(RUTA_REFERENCIA_ESTADO_CUENTA, encoding='utf-8') as f:
            cls.referencia = json.load(f)
        cls.actual = json.loads(json.dumps(capturar_comportamiento_estado_cuenta(), ensure_ascii=False))

    def test_cobertura(self):
        con_dv1 = sum(1 for n, _ in variantes() if any(d.devolucion_id == 'DV-1' for d in construir(n).ec.devoluciones))
        sin_dv = sum(1 for a in acciones() if not a[2])
        self.assertEqual(len(self.referencia), len(variantes()) * (1 + sin_dv) + con_dv1)
        self.assertEqual(len(self.referencia), 1203)
        self.assertEqual(set(self.actual), set(self.referencia))

    # El oráculo (referencia histórica) NO se edita. Para cada clave, el esperado es la entrada del oráculo con solo los cambios que ordenan
    # E-1 (GL-060/C-15: límite exclusivo de los plazos en días hábiles), H-10 (anticipo tardío liquidado), E-3 y E-4 (pagos parciales del
    # anticipo). Las reglas están en tests/apoyo_esperados_oraculo.py, que no usa código de producción. Toda clave que ninguna regla
    # toque debe ser idéntica al oráculo; el resto se compara con su esperado exacto, campo por campo.
    # Recuento verificado de las 1203 claves: 1094 solo por E-1; 69 por E-3/E-4 (71 con H-10: 2 claves combinan ambas) y 42 por H-10 en total.
    # D-2 (28/10/2026): 48 claves más, las del grupo R12 del cierre de alcance §8 (pago del saldo con fecha posterior al límite).
    CLAVES_POR_REGLA = {'E-1': 1203, 'E-3/E-4': 69, 'H-10': 42, 'D-2': 48}

    def test_resultados_identicos(self):
        """Cada clave coincide con el oráculo histórico más las diferencias esperadas por regla (y nada más)."""
        aplicadas = {'E-1': 0, 'E-3/E-4': 0, 'H-10': 0, 'D-2': 0}
        for clave, referencia in self.referencia.items():
            esperado, reglas = esperado_oraculo(clave, referencia)
            for r in reglas:
                aplicadas[r] += 1
            with self.subTest(caso=clave):
                self.assertEqual(self.actual[clave], esperado)
                if not reglas:
                    self.assertEqual(self.actual[clave], referencia)        # sin regla aplicable: idéntica a la referencia histórica
        self.assertEqual(aplicadas, self.CLAVES_POR_REGLA)

    def test_la_referencia_no_incluye_devoluciones_inexistentes(self):     # D-E3D-5, AR-08
        for clave in self.referencia:
            if clave.endswith('registrar_devolucion_efectuada(DV-1)'):
                variante = clave.split(' | ')[0]
                self.assertTrue(any(d.devolucion_id == 'DV-1' for d in construir(variante).ec.devoluciones), clave)

    def test_ningun_rechazo_modifica_el_agregado(self):
        for clave, r in self.actual.items():
            if 'error' not in r:
                continue
            inicial = self.actual[clave.split(' | ')[0] + ' | (inicial)']
            with self.subTest(caso=clave):
                self.assertEqual({k: v for k, v in r.items() if k != 'error'}, inicial)


class AislamientoDelPaqueteCSV(unittest.TestCase):
    def test_estados_y_acciones_son_los_de_eventos_nova(self):
        presentes = {e.name for m, _, _, _ in MAQUINAS for e in m.estados} | {a.name for _, _, _, A in MAQUINAS for a in A}
        for ajeno in ('COTIZADO', 'CONTRATADO', 'EN_PREPARACION', 'REALIZADO', 'CANCELADO', 'PAGADO', 'APROBAR'):
            self.assertNotIn(ajeno, presentes)

    def test_estado_cuenta_no_lee_el_paquete(self):
        with open(os.path.join(RAIZ, 'src', 'domain', 'estado_cuenta.py'), encoding='utf-8') as f:
            texto = f.read()
        for ajeno in ('paquete_pia', 'COTIZADO', '.csv'):
            self.assertNotIn(ajeno, texto)


if __name__ == '__main__':
    unittest.main()
