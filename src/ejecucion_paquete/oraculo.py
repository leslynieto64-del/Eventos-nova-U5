"""Oráculo de los casos del paquete: resultado esperado calculado de forma independiente.

El paquete del alumno no trae resultados esperados (el LEEME los reserva a `02_Docente`). El resultado esperado se
deriva aquí del texto de las reglas del LEEME, por un camino distinto del que se prueba:
- lee los CSV directamente con el módulo `csv` (no usa el lector `paquete_pia`, sus DTO ni sus validaciones);
- convierte los textos con `Decimal(str)` e `int(str)` y evalúa las reglas con expresiones booleanas simples (no usa
  las Specifications de `reglas_paquete`).
Si el ejecutor y el oráculo discrepan, el caso es FALLIDO.
"""
from __future__ import annotations
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple

UMBRAL = Decimal("1500")


def _filas(directorio: Path, archivo: str) -> List[dict]:
    with open(Path(directorio) / archivo, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Oraculo:
    def __init__(self, directorio):
        self.actores = {a["actor_id"]: a for a in _filas(directorio, "actores.csv")}
        self.precios = {c["recurso_id"]: Decimal(c["precio_mxn"]) for c in _filas(directorio, "catalogo.csv")}
        self.operaciones = {o["operacion_id"]: o for o in _filas(directorio, "operaciones.csv")}
        self.lineas: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        for d in _filas(directorio, "detalle_operaciones.csv"):
            self.lineas[d["operacion_id"]].append((d["recurso_id"], int(d["cantidad"])))

    def total(self, operacion_id: str) -> Decimal:
        return sum((self.precios[r] * c for r, c in self.lineas[operacion_id]), Decimal("0.00"))

    def esperado(self, tipo_prueba: str, operacion_id: str) -> Tuple[bool, List[str]]:
        """(cumple, condiciones incumplidas en el orden de la regla)."""
        op = self.operaciones[operacion_id]
        actor = self.actores[op["actor_id"]]
        if tipo_prueba == "validar_operacion":
            condiciones = [("actor activo", actor["activo"] == "1"),
                           ("detalle no vacío", len(self.lineas[operacion_id]) > 0),
                           ("autorización", op["autorizado"] == "1")]
        elif tipo_prueba == "evaluar_beneficio":
            condiciones = [("actor preferente (VIP)", actor["es_preferente"] == "1"),
                           (f"total >= {UMBRAL}", self.total(operacion_id) >= UMBRAL),
                           ("sin promoción activa", op["promocion_activa"] == "0")]
        else:
            raise KeyError(tipo_prueba)
        fallidas = [nombre for nombre, cumple in condiciones if not cumple]
        return not fallidas, fallidas
