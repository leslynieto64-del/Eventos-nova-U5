"""Ejecutor de los 120 casos de casos_prueba.csv (LEEME, «Secuencia para estudiantes», paso 4).

Para cada caso se construye el candidato a partir de los DTO del lector (`paquete_pia`), se evalúa la regla del
paquete con Specifications (`reglas_paquete`) y se compara con el oráculo independiente (`oraculo`): deben coincidir
tanto el resultado (cumple o no) como las condiciones incumplidas. No se considera aprobado un caso por no lanzar una
excepción. Veredictos: APROBADO (coincide), FALLIDO (no coincide) o NO_EJECUTABLE (no pudo construirse la entrada).
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from paquete_pia import PaquetePIA, leer_paquete
from .oraculo import Oraculo
from .reglas_paquete import REGLAS, SituacionOperacion
from .totales import ErrorTotal, total_operacion

CUMPLE, NO_CUMPLE = "CUMPLE", "NO_CUMPLE"
APROBADO, FALLIDO, NO_EJECUTABLE = "APROBADO", "FALLIDO", "NO_EJECUTABLE"
DIFERENCIA_POR_TIPO = {"validar_operacion": "D-01", "evaluar_beneficio": "D-02"}


@dataclass(frozen=True)
class ResultadoCaso:
    caso_id: str
    operacion_id: str
    tipo_prueba: str
    regla_a_verificar: str
    actor_id: str
    actor_activo: Optional[bool]
    actor_preferente: Optional[bool]
    autorizada: Optional[bool]
    promocion_activa: Optional[bool]
    lineas: Optional[int]
    total_mxn: Optional[Decimal]
    esperado: str
    condiciones_esperadas: str
    real: str
    condiciones_reales: str
    veredicto: str
    diferencia_modelo: str
    explicacion: str
    observaciones: str


def _texto(lista: List[str]) -> str:
    return "; ".join(lista) if lista else "—"


def _observaciones(paquete: PaquetePIA, lineas) -> str:
    """D-06: datos del catálogo que el dominio no usa; se informan, no deciden el veredicto."""
    catalogo = {c.recurso_id: c for c in paquete.catalogo}
    notas = []
    for l in lineas:
        recurso = catalogo[l.recurso_id]
        if not recurso.habilitado:
            notas.append(f"{l.recurso_id} deshabilitado en el catálogo")
        if l.cantidad > recurso.capacidad_o_stock:
            notas.append(f"{l.recurso_id}: cantidad {l.cantidad} > capacidad {recurso.capacidad_o_stock}")
    return _texto(notas)


def ejecutar_casos(directorio=None, paquete: Optional[PaquetePIA] = None) -> List[ResultadoCaso]:
    paquete = paquete or (leer_paquete(directorio) if directorio else leer_paquete())
    oraculo = Oraculo(Path(directorio) if directorio else Path(_directorio_del_paquete()))
    actores = {a.actor_id: a for a in paquete.actores}
    operaciones = {o.operacion_id: o for o in paquete.operaciones}
    precios = {c.recurso_id: c.precio_mxn for c in paquete.catalogo}
    lineas = defaultdict(list)
    for d in paquete.detalle_operaciones:
        lineas[d.operacion_id].append(d)

    resultados = []
    for caso in paquete.casos_prueba:
        op = operaciones.get(caso.operacion_id)
        actor = actores.get(op.actor_id) if op else None
        base = dict(caso_id=caso.caso_id, operacion_id=caso.operacion_id, tipo_prueba=caso.tipo_prueba,
                    regla_a_verificar=caso.regla_a_verificar, actor_id=op.actor_id if op else "—",
                    diferencia_modelo=DIFERENCIA_POR_TIPO.get(caso.tipo_prueba, "—"))
        try:
            if op is None or actor is None or caso.tipo_prueba not in REGLAS:
                raise LookupError("operación, actor o tipo de prueba inexistente")
            total = total_operacion(lineas[op.operacion_id], precios)
        except (LookupError, ErrorTotal) as e:
            resultados.append(ResultadoCaso(**base, actor_activo=None, actor_preferente=None, autorizada=None,
                                            promocion_activa=None, lineas=None, total_mxn=None, esperado="—",
                                            condiciones_esperadas="—", real="—", condiciones_reales="—",
                                            veredicto=NO_EJECUTABLE, explicacion=f"Entrada no ejecutable: {e}",
                                            observaciones="—"))
            continue
        situacion = SituacionOperacion(op.operacion_id, actor.activo, actor.es_preferente, op.autorizado,
                                       op.promocion_activa, len(lineas[op.operacion_id]), total)
        regla = REGLAS[caso.tipo_prueba]
        real_cumple = regla.es_satisfecha_por(situacion)
        real_condiciones = regla.motivos_incumplimiento(situacion)
        esp_cumple, esp_condiciones = oraculo.esperado(caso.tipo_prueba, caso.operacion_id)
        coincide = real_cumple == esp_cumple and real_condiciones == esp_condiciones
        if coincide:
            explicacion = ("Cumple todas las condiciones de la regla" if real_cumple else
                           f"No cumple: {_texto(real_condiciones)}") + "; coincide con el oráculo"
        else:
            explicacion = (f"Discrepancia con el oráculo: esperado {esp_cumple} {esp_condiciones}, "
                           f"real {real_cumple} {real_condiciones}")
        resultados.append(ResultadoCaso(
            **base, actor_activo=actor.activo, actor_preferente=actor.es_preferente, autorizada=op.autorizado,
            promocion_activa=op.promocion_activa, lineas=situacion.lineas, total_mxn=total,
            esperado=CUMPLE if esp_cumple else NO_CUMPLE, condiciones_esperadas=_texto(esp_condiciones),
            real=CUMPLE if real_cumple else NO_CUMPLE, condiciones_reales=_texto(real_condiciones),
            veredicto=APROBADO if coincide else FALLIDO, explicacion=explicacion,
            observaciones=_observaciones(paquete, lineas[op.operacion_id])))
    return resultados


def _directorio_del_paquete():
    from paquete_pia import DIRECTORIO_PREDETERMINADO
    return DIRECTORIO_PREDETERMINADO
