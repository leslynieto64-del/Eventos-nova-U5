"""Etapa F2 — ejecución de los 120 casos y las 20 transiciones del paquete oficial 16_Eventos_Nova.

Comprueba: totales con Decimal; cada familia de casos y cada condición de las reglas; conteos 120/20; mapeos y
diferencias; comparación esperado/real (un caso no se aprueba por no lanzar excepción); entradas no válidas;
transiciones válidas e inválidas; ausencia de cambios parciales; integridad SHA-256; que los CSV y el manifiesto no se
modifican; y que las evidencias son completas, trazables y reproducibles. No requieren FastAPI.
"""
import ast
import contextlib
import dataclasses
import glob
import os
import sys
import tempfile
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # permite ejecutar como tests.<módulo>
from apoyo_paquete_pia import CopiaPaquete, DIRECTORIO_OFICIAL, RAIZ, huella_directorio

from paquete_pia import CasoPrueba, ErrorPaquetePIA, DetalleOperacion, leer_paquete, verificar_manifiesto
from domain.valores import EstadoEvento
from ejecucion_paquete import (ErrorTotal, importe_linea, total_operacion, ejecutar_casos, ejecutar_transiciones,
                               generar_evidencias, escribir_evidencias, verificar_evidencias, DIRECTORIO_EVIDENCIAS)
from ejecucion_paquete import transiciones as m_trans, evidencias as m_evid
from ejecucion_paquete.mapeo import ACCIONES, DIFERENCIAS, ESTADOS, PREGUNTAS
from ejecucion_paquete.oraculo import Oraculo
from ejecucion_paquete.reglas_paquete import (BENEFICIO_REFERENCIA, PUEDE_PROCESARSE, REGLAS, SituacionOperacion,
                                              UMBRAL_BENEFICIO)

ESTADOS_PAQUETE = ("COTIZADO", "CONTRATADO", "EN_PREPARACION", "REALIZADO", "CANCELADO")
ACCIONES_PAQUETE = ("aprobar", "cancelar", "completar", "saltar_estado", "repetir_aprobacion")


class _Resultados:
    """Una sola ejecución compartida (las transiciones crean 20 composiciones en memoria)."""
    _casos = _trans = _evid = None

    @classmethod
    def casos(cls):
        if cls._casos is None:
            cls._casos = ejecutar_casos()
        return cls._casos

    @classmethod
    def transiciones(cls):
        if cls._trans is None:
            cls._trans = ejecutar_transiciones()
        return cls._trans

    @classmethod
    def evidencias(cls):
        if cls._evid is None:
            cls._evid = generar_evidencias()
        return cls._evid


def _por_id(resultados):
    return {r.caso_id: r for r in resultados}


def _situacion(**cambios):
    base = dict(operacion_id="X", actor_activo=True, actor_preferente=True, autorizada=True, promocion_activa=False,
                lineas=1, total=Decimal("2000.00"))
    base.update(cambios)
    return SituacionOperacion(**base)


# ============================================================================================ 1. Decimal

class TotalesDecimal(unittest.TestCase):
    L = staticmethod(lambda r, c: DetalleOperacion("EVE-O999", r, c))

    def test_importe_de_linea_exacto_con_dos_decimales(self):
        self.assertEqual(importe_linea(Decimal("1157.00"), 3), Decimal("3471.00"))
        self.assertEqual(importe_linea(Decimal("0.10"), 3), Decimal("0.30"))      # con float sería 0.30000000000000004
        self.assertIsInstance(importe_linea(Decimal("1.5"), 2), Decimal)
        self.assertEqual(str(importe_linea(Decimal("1.5"), 2)), "3.00")

    def test_rechaza_float_bool_y_valores_no_validos(self):
        for precio in (1157.0, 1, True, "1157.00", Decimal("NaN"), Decimal("Infinity"), Decimal("-1.00"),
                       Decimal("1.001")):
            with self.subTest(precio=precio), self.assertRaises(ErrorTotal):
                importe_linea(precio, 1)
        for cantidad in (0, -1, 1.0, True, Decimal("2"), "2"):
            with self.subTest(cantidad=cantidad), self.assertRaises(ErrorTotal):
                importe_linea(Decimal("10.00"), cantidad)

    def test_total_suma_lineas_operacion_vacia_y_recurso_inexistente(self):
        precios = {"A": Decimal("0.10"), "B": Decimal("0.20")}
        self.assertEqual(total_operacion([self.L("A", 1), self.L("B", 1)], precios), Decimal("0.30"))
        self.assertEqual(total_operacion([], precios), Decimal("0.00"))
        with self.assertRaises(ErrorTotal):
            total_operacion([self.L("Z", 1)], precios)

    def test_totales_del_paquete_coinciden_con_el_oraculo_y_son_decimal(self):
        p = leer_paquete()
        precios = {c.recurso_id: c.precio_mxn for c in p.catalogo}
        oraculo = Oraculo(DIRECTORIO_OFICIAL)
        suma = Decimal("0.00")
        for op in p.operaciones:
            lineas = [d for d in p.detalle_operaciones if d.operacion_id == op.operacion_id]
            total = total_operacion(lineas, precios)
            self.assertIsInstance(total, Decimal)
            self.assertEqual(total, oraculo.total(op.operacion_id), op.operacion_id)
            suma += total
        self.assertEqual(suma, Decimal("372918.00"))

    def test_valores_conocidos(self):
        r = _por_id(_Resultados.casos())
        self.assertEqual(r["EVE-T001"].total_mxn, Decimal("9519.00"))      # 1157.00×3 + 1512.00×4
        self.assertEqual(r["EVE-T013"].total_mxn, Decimal("0.00"))         # EVE-O013 sin líneas
        self.assertEqual(r["EVE-T039"].total_mxn, Decimal("0.00"))         # EVE-O039 sin líneas

    def test_ningun_resultado_usa_float(self):
        for r in _Resultados.casos() + _Resultados.transiciones():
            for campo in dataclasses.fields(r):
                self.assertNotIsInstance(getattr(r, campo.name), float, (r.caso_id, campo.name))


# ============================================================================================ 2. reglas y familias

class ReglasDelPaquete(unittest.TestCase):
    def test_puede_procesarse_cada_condicion(self):
        self.assertTrue(PUEDE_PROCESARSE.es_satisfecha_por(_situacion()))
        for cambio, motivo in ((dict(actor_activo=False), "actor activo"), (dict(lineas=0), "detalle no vacío"),
                               (dict(autorizada=False), "autorización")):
            with self.subTest(motivo=motivo):
                s = _situacion(**cambio)
                self.assertFalse(PUEDE_PROCESARSE.es_satisfecha_por(s))
                self.assertEqual(PUEDE_PROCESARSE.motivos_incumplimiento(s), [motivo])
        todas = _situacion(actor_activo=False, lineas=0, autorizada=False)
        self.assertEqual(PUEDE_PROCESARSE.motivos_incumplimiento(todas),
                         ["actor activo", "detalle no vacío", "autorización"])

    def test_beneficio_referencia_cada_condicion_y_umbral_incluido(self):
        self.assertEqual(UMBRAL_BENEFICIO, Decimal("1500"))
        self.assertTrue(BENEFICIO_REFERENCIA.es_satisfecha_por(_situacion(total=Decimal("1500.00"))))
        self.assertEqual(BENEFICIO_REFERENCIA.motivos_incumplimiento(_situacion(total=Decimal("1499.99"))),
                         ["total >= 1500"])
        self.assertEqual(BENEFICIO_REFERENCIA.motivos_incumplimiento(_situacion(actor_preferente=False)),
                         ["actor preferente (VIP)"])
        self.assertEqual(BENEFICIO_REFERENCIA.motivos_incumplimiento(_situacion(promocion_activa=True)),
                         ["sin promoción activa"])

    def test_reglas_por_tipo_de_prueba(self):
        self.assertEqual(set(REGLAS), {"validar_operacion", "evaluar_beneficio"})


class FamiliasDeCasos(unittest.TestCase):
    def test_validar_operacion_situaciones_del_paquete(self):
        r = _por_id(_Resultados.casos())
        esperados = {
            "EVE-T001": ("CUMPLE", "—"),
            "EVE-T010": ("NO_CUMPLE", "actor activo"),          # EVE-O010: actor inactivo
            "EVE-T013": ("NO_CUMPLE", "actor activo; detalle no vacío"),   # EVE-O013: actor inactivo y sin líneas
            "EVE-T039": ("NO_CUMPLE", "detalle no vacío"),                 # EVE-O039: sin líneas
            "EVE-T008": ("NO_CUMPLE", "autorización"),          # EVE-O008: no autorizada
        }
        for caso, (real, condiciones) in esperados.items():
            with self.subTest(caso=caso):
                self.assertEqual((r[caso].real, r[caso].condiciones_reales), (real, condiciones))
                self.assertEqual(r[caso].veredicto, "APROBADO")

    def test_evaluar_beneficio_situaciones_del_paquete(self):
        casos = _Resultados.casos()
        beneficio = [c for c in casos if c.tipo_prueba == "evaluar_beneficio"]
        cumplen = [c for c in beneficio if c.real == "CUMPLE"]
        self.assertTrue(cumplen)
        for c in cumplen:
            self.assertTrue(c.actor_preferente and c.total_mxn >= Decimal("1500") and not c.promocion_activa)
        con_promocion = [c for c in beneficio if c.promocion_activa]
        self.assertEqual({c.operacion_id for c in con_promocion},
                         {"EVE-O009", "EVE-O018", "EVE-O027", "EVE-O036", "EVE-O045", "EVE-O054"})
        for c in con_promocion:
            self.assertIn("sin promoción activa", c.condiciones_reales)
        for c in beneficio:
            self.assertEqual("total >= 1500" in c.condiciones_reales, c.total_mxn < Decimal("1500"), c.caso_id)

    def test_cada_familia_completa_y_con_su_diferencia(self):
        casos = _Resultados.casos()
        familias = Counter(c.tipo_prueba for c in casos)
        self.assertEqual(familias, {"validar_operacion": 60, "evaluar_beneficio": 60})
        for c in casos:
            self.assertEqual(c.diferencia_modelo, {"validar_operacion": "D-01", "evaluar_beneficio": "D-02"}[c.tipo_prueba])
            self.assertEqual(c.caso_id[4], {"validar_operacion": "T", "evaluar_beneficio": "B"}[c.tipo_prueba])

    def test_ambas_familias_tienen_casos_que_cumplen_y_que_no(self):
        for tipo in ("validar_operacion", "evaluar_beneficio"):
            reales = {c.real for c in _Resultados.casos() if c.tipo_prueba == tipo}
            self.assertEqual(reales, {"CUMPLE", "NO_CUMPLE"}, tipo)

    def test_observaciones_del_catalogo_no_cambian_el_veredicto(self):
        obs = [c for c in _Resultados.casos() if c.observaciones != "—"]
        self.assertEqual({c.operacion_id for c in obs},
                         {"EVE-O005", "EVE-O015", "EVE-O020", "EVE-O035", "EVE-O040", "EVE-O055"})
        for c in obs:
            self.assertIn("EVE-P011 deshabilitado", c.observaciones)


# ============================================================================================ 3. conteos

class Conteos(unittest.TestCase):
    def test_120_casos_en_el_orden_del_csv(self):
        casos = _Resultados.casos()
        self.assertEqual(len(casos), 120)
        self.assertEqual([c.caso_id for c in casos], [c.caso_id for c in leer_paquete().casos_prueba])

    def test_20_transiciones_en_el_orden_del_csv_y_4_por_accion(self):
        trans = _Resultados.transiciones()
        self.assertEqual(len(trans), 20)
        self.assertEqual([t.caso_id for t in trans], [t.caso_id for t in leer_paquete().transiciones_prueba])
        self.assertEqual(Counter(t.accion_sugerida for t in trans), {a: 4 for a in ACCIONES_PAQUETE})

    def test_resultados_no_todos_aprobados_por_defecto(self):
        veredictos = Counter(t.veredicto for t in _Resultados.transiciones())
        self.assertEqual(veredictos, {"APROBADO": 19, "NO_EJECUTABLE": 1})
        self.assertEqual(Counter(c.veredicto for c in _Resultados.casos()), {"APROBADO": 120})


# ============================================================================================ 4. mapeos y diferencias

class Mapeos(unittest.TestCase):
    IDS = {d.id for d in DIFERENCIAS}

    def test_cada_estado_y_accion_del_paquete_tiene_correspondencia_con_fuente(self):
        self.assertEqual(tuple(e.estado_paquete for e in ESTADOS), ESTADOS_PAQUETE)
        self.assertEqual({a.accion_paquete for a in ACCIONES}, set(ACCIONES_PAQUETE))
        for x in ESTADOS + ACCIONES:
            self.assertTrue(x.fuente.strip())

    def test_diferencias_identificadas_y_referenciadas(self):
        self.assertEqual([d.id for d in DIFERENCIAS], [f"D-0{i}" for i in range(1, 9)])
        for d in DIFERENCIAS:
            self.assertTrue(all([d.regla_paquete, d.regla_dominio, d.motivo, d.fuente, d.ajuste_oraculo, d.afectados]))
        for t in _Resultados.transiciones():
            for d in t.diferencias.split(", "):
                if d != "—":
                    self.assertIn(d, self.IDS)
        self.assertEqual([p.id for p in PREGUNTAS], ["Q-01", "Q-02", "Q-03"])

    def test_no_se_anaden_estados_artificiales_al_dominio(self):
        self.assertEqual([e.value for e in EstadoEvento],
                         ["En gestión", "En organización", "En ejecución", "Finalizado", "Cancelado",
                          "Cerrado sin contratación"])
        for archivo in glob.glob(os.path.join(RAIZ, "src", "domain", "*.py")):
            texto = Path(archivo).read_text(encoding="utf-8")
            # EN_PREPARACION no se busca: es un estado legítimo de Contrato («En preparación»), no del paquete
            for prohibido in ("COTIZADO", "CONTRATADO", "REALIZADO", "paquete_pia", "ejecucion_paquete"):
                self.assertNotIn(prohibido, texto, (archivo, prohibido))

    def test_las_capas_no_dependen_del_ejecutor_ni_el_lector_del_dominio(self):
        def modulos(patron):
            mods = set()
            for f in glob.glob(patron):
                for n in ast.walk(ast.parse(Path(f).read_text(encoding="utf-8"))):
                    if isinstance(n, ast.Import):
                        mods |= {a.name.split(".")[0] for a in n.names}
                    elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                        mods.add(n.module.split(".")[0])
            return mods
        for capa in ("domain", "application", "infrastructure", "api", "paquete_pia"):
            with self.subTest(capa=capa):
                self.assertNotIn("ejecucion_paquete", modulos(os.path.join(RAIZ, "src", capa, "*.py")))
        self.assertFalse(modulos(os.path.join(RAIZ, "src", "paquete_pia", "*.py")) &
                         {"domain", "application", "infrastructure", "api"})


# ============================================================================================ 5. esperado frente a real

class ComparacionEsperadoReal(unittest.TestCase):
    def test_aprobado_solo_si_coinciden_resultado_y_condiciones(self):
        for c in _Resultados.casos():
            self.assertEqual(c.veredicto == "APROBADO",
                             c.esperado == c.real and c.condiciones_esperadas == c.condiciones_reales, c.caso_id)

    def test_un_oraculo_distinto_produce_fallido(self):
        original = Oraculo.esperado

        def invertido(self, tipo, op):
            cumple, fallidas = original(self, tipo, op)
            return (not cumple, [] if fallidas else ["condición inventada"])
        with mock.patch.object(Oraculo, "esperado", invertido):
            resultados = ejecutar_casos()
        self.assertEqual(Counter(r.veredicto for r in resultados), {"FALLIDO": 120})
        self.assertTrue(all("Discrepancia" in r.explicacion for r in resultados))

    def test_mismas_condiciones_pero_distinto_motivo_produce_fallido(self):
        original = Oraculo.esperado

        def otro_motivo(self, tipo, op):
            cumple, fallidas = original(self, tipo, op)
            return cumple, ["otra condición"] * len(fallidas)
        with mock.patch.object(Oraculo, "esperado", otro_motivo):
            r = _por_id(ejecutar_casos())
        self.assertEqual(r["EVE-T010"].veredicto, "FALLIDO")     # NO_CUMPLE en ambos, pero por otra condición
        self.assertEqual(r["EVE-T001"].veredicto, "APROBADO")    # CUMPLE sin condiciones incumplidas

    def test_transicion_con_oraculo_distinto_produce_fallido(self):
        falso = dict(m_trans.ORACULO_DOMINIO)
        falso["cancelar"] = dataclasses.replace(falso["cancelar"], mensaje="Otro mensaje")
        falso["aprobar"] = dataclasses.replace(falso["aprobar"], eventos=("PropuestaAceptada",))
        with mock.patch.object(m_trans, "ORACULO_DOMINIO", falso):
            r = _por_id(ejecutar_transiciones())
        for caso in ("EVE-S002", "EVE-S007", "EVE-S012", "EVE-S017", "EVE-S005", "EVE-S010", "EVE-S015", "EVE-S020"):
            self.assertEqual(r[caso].veredicto, "FALLIDO", caso)
        self.assertEqual(r["EVE-S001"].veredicto, "APROBADO")

    def test_coincide_con_paquete_independiente_del_veredicto(self):
        r = _por_id(_Resultados.transiciones())
        for caso in ("EVE-S002", "EVE-S003", "EVE-S010"):
            self.assertEqual((r[caso].veredicto, r[caso].coincide_con_paquete), ("APROBADO", "NO"))
            self.assertIn("difiere del flujo del paquete", r[caso].explicacion)
        self.assertEqual(r["EVE-S001"].coincide_con_paquete, "SÍ")


# ============================================================================================ 6. entradas no válidas

class EntradasNoValidas(unittest.TestCase):
    def _paquete(self, **cambios):
        return dataclasses.replace(leer_paquete(), **cambios)

    def test_caso_con_operacion_inexistente_o_tipo_desconocido_no_es_ejecutable(self):
        p = leer_paquete()
        extra = (CasoPrueba("EVE-T999", "EVE-O999", "validar_operacion", "x", "PENDIENTE", "x"),
                 CasoPrueba("EVE-T998", "EVE-O001", "tipo_inventado", "x", "PENDIENTE", "x"))
        r = _por_id(ejecutar_casos(paquete=self._paquete(casos_prueba=p.casos_prueba + extra)))
        for caso in ("EVE-T999", "EVE-T998"):
            self.assertEqual(r[caso].veredicto, "NO_EJECUTABLE")
            self.assertEqual((r[caso].esperado, r[caso].real), ("—", "—"))
        self.assertEqual(Counter(x.veredicto for x in r.values())["APROBADO"], 120)

    def test_linea_con_recurso_inexistente_no_es_ejecutable(self):
        p = leer_paquete()
        detalle = p.detalle_operaciones + (DetalleOperacion("EVE-O001", "EVE-P999", 1),)
        r = _por_id(ejecutar_casos(paquete=self._paquete(detalle_operaciones=detalle)))
        self.assertEqual(r["EVE-T001"].veredicto, "NO_EJECUTABLE")
        self.assertIn("EVE-P999", r["EVE-T001"].explicacion)
        self.assertEqual(r["EVE-T002"].veredicto, "APROBADO")

    def test_operacion_sin_lineas_en_transicion_es_no_ejecutable_con_rechazo_ca005(self):
        s13 = _por_id(_Resultados.transiciones())["EVE-S013"]
        self.assertEqual(s13.veredicto, "NO_EJECUTABLE")
        self.assertEqual(s13.mensaje_real, m_trans.MSG_CA005)
        self.assertIn("D-08", s13.diferencias)

    def test_paquete_alterado_se_rechaza_antes_de_ejecutar(self):
        with CopiaPaquete() as copia:
            copia.reemplazar("catalogo.csv", "1157.00", "1157.01")
            with self.assertRaises(ErrorPaquetePIA):
                ejecutar_casos(copia.ruta)
            with self.assertRaises(ErrorPaquetePIA):
                generar_evidencias(copia.ruta)


# ============================================================================================ 7. transiciones

class Transiciones(unittest.TestCase):
    def setUp(self):
        self.r = _por_id(_Resultados.transiciones())

    def test_todas_parten_de_la_correspondencia_de_cotizado(self):
        for t in self.r.values():
            self.assertEqual(t.estado_inicial_paquete, "COTIZADO")
            if t.veredicto != "NO_EJECUTABLE":
                self.assertEqual(t.estado_inicial_dominio, "Evento «En gestión» / Propuesta «En revisión del Cliente»")

    def test_aprobar_valida_confirma_la_contratacion_con_anticipo_del_30(self):
        for caso in ("EVE-S005", "EVE-S010", "EVE-S015", "EVE-S020"):
            t = self.r[caso]
            self.assertEqual((t.resultado_real, t.estado_final_evento, t.estado_final_contrato, t.veredicto),
                             ("ACEPTADA", "En organización", "Contratación confirmada", "APROBADO"))
            self.assertEqual(t.eventos_emitidos, "PropuestaAceptada, ContratoFirmado, PagoVerificado, ContratacionConfirmada")
            self.assertEqual(Decimal(t.anticipo_mxn), (t.total_mxn * Decimal("0.30")).quantize(Decimal("0.01")))
        self.assertEqual(self.r["EVE-S005"].anticipo_mxn, "2052.60")
        self.assertEqual(self.r["EVE-S010"].coincide_con_paquete, "NO")         # actor inactivo (D-05)
        self.assertIn("D-05", self.r["EVE-S010"].diferencias)

    def test_invalidas_se_rechazan_con_su_mensaje(self):
        mensajes = {"cancelar": m_trans.MSG_CA084, "completar": m_trans.MSG_CA094, "saltar_estado": m_trans.MSG_INICIO}
        for t in self.r.values():
            if t.accion_sugerida in mensajes:
                with self.subTest(caso=t.caso_id):
                    self.assertEqual((t.resultado_real, t.mensaje_real, t.estado_final_evento, t.eventos_emitidos),
                                     ("RECHAZADA", mensajes[t.accion_sugerida], "En gestión", "ninguno"))
                    self.assertEqual(t.veredicto, "APROBADO")
                    self.assertEqual(t.coincide_con_paquete, "NO" if t.accion_sugerida == "cancelar" else "SÍ")

    def test_repetir_aprobacion_es_idempotente(self):
        for caso in ("EVE-S003", "EVE-S008", "EVE-S018"):
            t = self.r[caso]
            self.assertEqual((t.resultado_real, t.mensaje_real, t.eventos_emitidos, t.estado_final_evento),
                             ("ACEPTADA_SIN_EFECTO", m_trans.MSG_YA_CONFIRMADA, "ninguno", "En organización"))
            self.assertEqual((t.veredicto, t.coincide_con_paquete), ("APROBADO", "NO"))
            self.assertIn("D-04", t.diferencias)

    def test_esperado_del_paquete_derivado_del_flujo_de_referencia(self):
        self.assertEqual(m_trans.esperado_paquete("aprobar", True)[0], "TRANSICION")
        self.assertEqual(m_trans.esperado_paquete("aprobar", False)[0], "EXCEPCION")
        self.assertEqual(m_trans.esperado_paquete("cancelar", True)[0], "TRANSICION")
        for accion in ("completar", "saltar_estado", "repetir_aprobacion"):
            self.assertEqual(m_trans.esperado_paquete(accion, True)[0], "EXCEPCION")
        with self.assertRaises(KeyError):
            m_trans.esperado_paquete("inventada", True)


class FallosFuncionalesDeTransicion(unittest.TestCase):
    """Cada desviación del oráculo del dominio se registra como FALLIDO (no como aprobado ni como no ejecutable)."""

    def _con(self, *parches):
        with contextlib.ExitStack() as pila:
            for p in parches:
                pila.enter_context(p)
            return _por_id(ejecutar_transiciones())

    def test_rechazo_al_preparar_es_fallido(self):
        from application.resultados import Resultado
        from application.servicios import GestionPropuestaService
        parche = mock.patch.object(GestionPropuestaService, "crear_propuesta",
                                   lambda *a, **k: Resultado.rechazo("rechazo simulado"))
        r = self._con(parche)
        self.assertEqual(r["EVE-S001"].veredicto, "FALLIDO")
        self.assertIn("rechazo simulado", r["EVE-S001"].explicacion)

    def test_propuesta_sin_servicios_aceptada_seria_fallido(self):
        real = m_trans.ContenidoPropuesta

        def Permisiva(servicios, *resto):                 # acepta solo el caso vacío, que el dominio rechaza
            return object() if not servicios else real(servicios, *resto)
        r = self._con(mock.patch.object(m_trans, "ContenidoPropuesta", Permisiva))
        self.assertEqual(r["EVE-S013"].veredicto, "FALLIDO")
        self.assertIn("no fue rechazada", r["EVE-S013"].explicacion)

    def test_paso_rechazado_en_la_aprobacion_es_fallido(self):
        from application.resultados import Resultado
        pago = mock.patch("application.servicios.GestionPagosService.registrar_y_verificar_pago",
                          lambda *a, **k: Resultado.rechazo("pago rechazado"))
        r = self._con(pago)
        for caso in ("EVE-S005", "EVE-S003"):
            self.assertEqual((r[caso].resultado_real, r[caso].veredicto), ("RECHAZADA", "FALLIDO"), caso)
        self.assertIn("pago rechazado", r["EVE-S005"].mensaje_real)
        self.assertEqual(r["EVE-S001"].veredicto, "APROBADO")

    def test_anticipo_distinto_al_30_es_fallido(self):
        r = self._con(mock.patch.object(m_trans, "PORCENTAJE_ANTICIPO", Decimal("0.40")))
        self.assertEqual(r["EVE-S005"].veredicto, "FALLIDO")
        self.assertIn("anticipo", r["EVE-S005"].explicacion)

    def test_cambio_parcial_es_fallido(self):
        contador = iter(range(10 ** 6))
        r = self._con(mock.patch.object(m_trans, "_fotografia", lambda app, ev: next(contador)))
        self.assertEqual((r["EVE-S002"].sin_cambios_parciales, r["EVE-S002"].veredicto), ("NO", "FALLIDO"))
        self.assertIn("cambiaron", r["EVE-S002"].explicacion)

    def test_estado_o_resultado_distinto_es_fallido(self):
        falso = dict(m_trans.ORACULO_DOMINIO)
        falso["completar"] = dataclasses.replace(falso["completar"], resultado="ACEPTADA",
                                                 estado_evento=EstadoEvento.FINALIZADO)
        falso["aprobar"] = dataclasses.replace(falso["aprobar"], estado_contrato=m_trans.EstadoContrato.FIRMADO)
        r = self._con(mock.patch.object(m_trans, "ORACULO_DOMINIO", falso))
        self.assertIn("resultado RECHAZADA", r["EVE-S001"].explicacion)
        self.assertIn("Finalizado", r["EVE-S001"].explicacion)
        self.assertIn("Contrato", r["EVE-S005"].explicacion)

    def test_accion_desconocida(self):
        c = SinCambiosParciales._corrida(None)
        with self.assertRaises(KeyError):
            c.ejecutar("inventada")
        self.assertEqual(m_trans._foto(1.5), "1.5")       # valores no previstos: representación textual


# ============================================================================================ 8. sin cambios parciales

class SinCambiosParciales(unittest.TestCase):
    @staticmethod
    def _corrida(_self=None, operacion_id="EVE-O002"):
        p = leer_paquete()
        op = next(o for o in p.operaciones if o.operacion_id == operacion_id)
        actor = next(a for a in p.actores if a.actor_id == op.actor_id)
        cat = {c.recurso_id: c for c in p.catalogo}
        lineas = [d for d in p.detalle_operaciones if d.operacion_id == operacion_id]
        c = m_trans._Corrida(op, actor, [cat[l.recurso_id].descripcion for l in lineas],
                             total_operacion(lineas, {k: v.precio_mxn for k, v in cat.items()}))
        c.preparar()
        return c

    def test_rechazos_y_repeticiones_registran_ausencia_de_cambios(self):
        for t in _Resultados.transiciones():
            if t.accion_sugerida in ("cancelar", "completar", "saltar_estado", "repetir_aprobacion") \
                    and t.veredicto != "NO_EJECUTABLE":
                self.assertEqual(t.sin_cambios_parciales, "SÍ", t.caso_id)

    def test_cada_rechazo_deja_identicos_agregados_y_outbox(self):
        for accion in ("cancelar", "completar", "saltar_estado"):
            with self.subTest(accion=accion):
                c = self._corrida()
                antes = m_trans._fotografia(c.app, c.evento_id)
                r = c.ejecutar(accion)
                c.despachador.despachar()
                self.assertFalse(r.exito)
                self.assertEqual(m_trans._fotografia(c.app, c.evento_id), antes)

    def test_la_fotografia_detecta_cambios(self):
        c = self._corrida()
        antes = m_trans._fotografia(c.app, c.evento_id)
        ev = c.app.repos.eventos.obtener_por_id(c.evento_id)
        ev.servicios_solicitados.append("cambio")
        c.app.repos.eventos.guardar(ev)
        c.app.repos.eventos._confirmar()                # lo que haría el UnitOfWork al confirmar una transacción
        self.assertNotEqual(m_trans._fotografia(c.app, c.evento_id), antes)

    def test_cada_transicion_usa_una_composicion_nueva(self):
        a, b = self._corrida(operacion_id="EVE-O001"), self._corrida(operacion_id="EVE-O001")
        self.assertIsNot(a.app, b.app)
        self.assertEqual(len(b.app.repos.contratos.listar_por_evento_id(b.evento_id)), 0)


# ============================================================================================ 9-10. integridad

class IntegridadDeLasEntradas(unittest.TestCase):
    def test_manifiesto_valido_y_csv_sin_modificar_despues_de_ejecutar(self):
        antes = huella_directorio()
        self.assertEqual(verificar_manifiesto(DIRECTORIO_OFICIAL), [])
        ejecutar_casos()
        ejecutar_transiciones()
        with tempfile.TemporaryDirectory() as tmp:
            escribir_evidencias(Path(tmp))
        self.assertEqual(huella_directorio(), antes)              # mismos bytes y misma fecha de modificación
        self.assertEqual(verificar_manifiesto(DIRECTORIO_OFICIAL), [])

    def test_resultado_alumno_sigue_pendiente_en_los_csv_oficiales(self):
        p = leer_paquete()
        self.assertEqual({c.resultado_alumno for c in p.casos_prueba + p.transiciones_prueba}, {"PENDIENTE"})

    def test_el_resumen_registra_los_hashes_del_manifiesto(self):
        from paquete_pia import leer_manifiesto
        resumen = _Resultados.evidencias()["resumen.md"]
        for nombre, h in leer_manifiesto(DIRECTORIO_OFICIAL / "MANIFIESTO.sha256").items():
            self.assertIn(f"| {nombre} |", resumen)
            self.assertIn(h, resumen)


# ============================================================================================ 11. evidencias

class Evidencias(unittest.TestCase):
    def test_archivos_y_ubicacion(self):
        self.assertEqual(DIRECTORIO_EVIDENCIAS, RAIZ / "tests" / "evidencias" / "f2")
        self.assertEqual(tuple(_Resultados.evidencias()), m_evid.ARCHIVOS_EVIDENCIA)

    def test_tablas_completas_y_trazables(self):
        import csv, io
        ev = _Resultados.evidencias()
        esperado = {"casos_resultados.csv": ("casos_prueba.csv", 120), "transiciones_resultados.csv":
                    ("transiciones_prueba.csv", 20), "totales_operaciones.csv": ("operaciones.csv", 60)}
        for archivo, (origen, n) in esperado.items():
            filas = list(csv.DictReader(io.StringIO(ev[archivo])))
            self.assertEqual(len(filas), n, archivo)
            self.assertEqual([f["fila_origen"] for f in filas], [f"{origen}:{i}" for i in range(2, n + 2)])
            for f in filas:
                self.assertNotIn("", f.values(), (archivo, f))
        casos = list(csv.DictReader(io.StringIO(ev["casos_resultados.csv"])))
        self.assertEqual(Counter(f["veredicto"] for f in casos), {"APROBADO": 120})
        self.assertEqual(len(list(csv.DictReader(io.StringIO(ev["diferencias_modelo.csv"])))), 8)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(ev["mapeo_estados_acciones.csv"])))), 10)

    def test_salidas_reproducibles(self):
        self.assertEqual(generar_evidencias(), _Resultados.evidencias())
        for contenido in _Resultados.evidencias().values():
            self.assertNotRegex(contenido, r"\b(EV|PR|CT|EC)-[0-9a-f]{6,}")   # sin identificadores aleatorios

    def test_las_evidencias_guardadas_coinciden_con_la_ejecucion(self):
        self.assertEqual(verificar_evidencias(), [])

    def test_verificacion_detecta_faltantes_y_alteraciones_y_tolera_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            self.assertIn("resumen.md: no existe", verificar_evidencias(destino))
            escribir_evidencias(destino)
            self.assertEqual(verificar_evidencias(destino), [])
            ruta = destino / "casos_resultados.csv"
            ruta.write_bytes(ruta.read_bytes().replace(b"\n", b"\r\n"))       # checkout con autocrlf
            self.assertEqual(verificar_evidencias(destino), [])
            ruta.write_bytes(ruta.read_bytes().replace(b"APROBADO", b"FALLIDO", 1))
            self.assertEqual(len(verificar_evidencias(destino)), 1)

    def test_csv_con_bom_para_excel(self):
        with tempfile.TemporaryDirectory() as tmp:
            escribir_evidencias(Path(tmp))
            self.assertTrue((Path(tmp) / "casos_resultados.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertFalse((Path(tmp) / "resumen.md").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_linea_de_comandos(self):
        from ejecucion_paquete.__main__ import main
        with mock.patch("builtins.print"):
            self.assertEqual(main(["--verificar"]), 0)
        with mock.patch.object(m_evid, "verificar_evidencias", return_value=["x: difiere"]), \
                mock.patch("ejecucion_paquete.__main__.verificar_evidencias", return_value=["x: difiere"]), \
                mock.patch("builtins.print"):
            self.assertEqual(main(["--verificar"]), 1)
        with tempfile.TemporaryDirectory() as tmp:
            rutas = [DIRECTORIO_EVIDENCIAS / "x.csv"]
            with mock.patch("ejecucion_paquete.__main__.escribir_evidencias", return_value=rutas), \
                    mock.patch("builtins.print") as impreso:
                self.assertEqual(main([]), 0)
            impreso.assert_called_once_with(f"Escrito: {Path('tests', 'evidencias', 'f2', 'x.csv')}")


if __name__ == "__main__":
    unittest.main()
