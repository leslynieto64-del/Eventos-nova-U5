from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Resultado:
    """Resultado de un caso de uso: éxito con datos o rechazo con motivo de negocio."""
    exito: bool
    mensaje: str = ""
    datos: dict = field(default_factory=dict)
    pendientes: List[str] = field(default_factory=list)

    @staticmethod
    def ok(mensaje: str = "", **datos) -> "Resultado":
        return Resultado(True, mensaje, datos)

    @staticmethod
    def rechazo(mensaje: str, pendientes: Optional[List[str]] = None) -> "Resultado":
        return Resultado(False, mensaje, {}, pendientes or [])
