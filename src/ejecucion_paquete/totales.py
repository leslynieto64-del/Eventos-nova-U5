"""Totales de las operaciones del paquete (LEEME, «Secuencia para estudiantes», paso 3).

    total de la operación = suma(precio_mxn × cantidad) de sus líneas de detalle_operaciones.csv

Solo usa `Decimal`. Rechaza `float`, booleanos, precios negativos, no finitos o con más de dos decimales,
cantidades que no sean enteros positivos y recursos inexistentes. Una operación sin líneas tiene total 0.00.
El total es exacto (precio con dos decimales × entero): no se redondea, solo se expresa con dos decimales.
No modifica ni sustituye los cálculos monetarios del dominio de Eventos Nova (`domain.valores.Importe`).
"""
from __future__ import annotations
from decimal import Decimal
from typing import Iterable, Mapping

CENTAVOS = Decimal("0.01")


class ErrorTotal(ValueError):
    """Entrada no válida para el cálculo de un importe."""


def _precio_valido(precio) -> Decimal:
    if isinstance(precio, bool) or not isinstance(precio, Decimal):
        raise ErrorTotal(f"el precio debe ser Decimal, no {type(precio).__name__}")
    if not precio.is_finite():
        raise ErrorTotal("el precio no es un número finito")
    if precio < 0:
        raise ErrorTotal("el precio no puede ser negativo")
    if precio.as_tuple().exponent < -2:
        raise ErrorTotal("el precio tiene más de dos decimales")
    return precio


def _cantidad_valida(cantidad) -> int:
    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        raise ErrorTotal(f"la cantidad debe ser un entero, no {type(cantidad).__name__}")
    if cantidad <= 0:
        raise ErrorTotal("la cantidad debe ser mayor que cero")
    return cantidad


def importe_linea(precio_mxn: Decimal, cantidad: int) -> Decimal:
    """precio_mxn × cantidad, exacto y con dos decimales."""
    return (_precio_valido(precio_mxn) * _cantidad_valida(cantidad)).quantize(CENTAVOS)


def total_operacion(lineas: Iterable, precios: Mapping[str, Decimal]) -> Decimal:
    """Suma de los importes de las líneas (objetos con `recurso_id` y `cantidad`). `precios`: recurso_id → precio."""
    total = Decimal("0.00")
    for linea in lineas:
        if linea.recurso_id not in precios:
            raise ErrorTotal(f"el recurso {linea.recurso_id} no existe en el catálogo")
        total += importe_linea(precios[linea.recurso_id], linea.cantidad)
    return total.quantize(CENTAVOS)
