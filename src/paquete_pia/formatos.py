"""Conversión y validación de formatos de los valores de los CSV.

Cada función recibe el texto de la celda y devuelve el valor convertido o lanza ValueError con un mensaje.
Solo se validan formatos; no se aplica ninguna regla de negocio.
"""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

_BOOLEANOS = {"0": False, "1": True}
_IMPORTE = re.compile(r"\d+\.\d{2}")            # p. ej. 589.00: sin signo, separador decimal «.», dos decimales
_ENTERO_NO_NEGATIVO = re.compile(r"\d+")
_FECHA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")      # AAAA-MM-DD (ISO 8601, formato extendido)


def texto(valor: str) -> str:
    """Texto obligatorio, sin espacios al inicio ni al final."""
    if valor == "":
        raise ValueError("el valor está vacío")
    if valor != valor.strip():
        raise ValueError(f"el valor tiene espacios al inicio o al final: {valor!r}")
    return valor


def identificador(patron: str) -> Callable[[str], str]:
    """Identificador con el formato del paquete (p. ej. EVE-C001)."""
    expresion = re.compile(patron)

    def convertir(valor: str) -> str:
        if not expresion.fullmatch(valor):
            raise ValueError(f"identificador con formato inválido: {valor!r} (se esperaba {patron})")
        return valor
    return convertir


def booleano(valor: str) -> bool:
    """Solo se admiten 0 y 1."""
    if valor not in _BOOLEANOS:
        raise ValueError(f"booleano inválido: {valor!r} (valores permitidos: 0 o 1)")
    return _BOOLEANOS[valor]


def importe(valor: str) -> Decimal:
    """Importe en MXN convertido a Decimal (nunca a float)."""
    if not _IMPORTE.fullmatch(valor):
        raise ValueError(f"importe inválido: {valor!r} (formato esperado: 1234.56, sin signo y con dos decimales)")
    try:
        return Decimal(valor)
    except InvalidOperation as e:                     # no debería ocurrir tras la expresión regular
        raise ValueError(f"importe inválido: {valor!r}") from e


def entero_no_negativo(valor: str) -> int:
    if not _ENTERO_NO_NEGATIVO.fullmatch(valor):
        raise ValueError(f"entero inválido: {valor!r} (se esperaba un entero sin signo)")
    return int(valor)


def entero_positivo(valor: str) -> int:
    numero = entero_no_negativo(valor)
    if numero == 0:
        raise ValueError("el valor debe ser un entero mayor que cero")
    return numero


def fecha_iso(valor: str) -> date:
    """Fecha ISO 8601 AAAA-MM-DD y existente en el calendario."""
    if not _FECHA_ISO.fullmatch(valor):
        raise ValueError(f"fecha inválida: {valor!r} (formato esperado: AAAA-MM-DD)")
    try:
        return date.fromisoformat(valor)
    except ValueError as e:
        raise ValueError(f"fecha inexistente: {valor!r}") from e


def uno_de(permitidos) -> Callable[[str], str]:
    permitidos = tuple(permitidos)

    def convertir(valor: str) -> str:
        if valor not in permitidos:
            raise ValueError(f"valor no reconocido: {valor!r} (valores permitidos: {', '.join(permitidos)})")
        return valor
    return convertir
