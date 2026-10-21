"""Problemas de validación del paquete de datos."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


@dataclass(frozen=True)
class ProblemaValidacion:
    """Un problema concreto. `fila` es el número de línea física del archivo (el encabezado es la línea 1)."""
    archivo: str
    mensaje: str
    fila: Optional[int] = None
    columna: Optional[str] = None

    def __str__(self) -> str:
        lugar = self.archivo
        if self.fila is not None:
            lugar += f", línea {self.fila}"
        if self.columna:
            lugar += f", columna «{self.columna}»"
        return f"{lugar}: {self.mensaje}"


class ErrorPaquetePIA(Exception):
    """El paquete no superó la validación. Contiene todos los problemas encontrados, no solo el primero."""

    MAXIMO_EN_MENSAJE = 20

    def __init__(self, problemas: Iterable[ProblemaValidacion]):
        self.problemas: Tuple[ProblemaValidacion, ...] = tuple(problemas)
        lineas = [str(p) for p in self.problemas[:self.MAXIMO_EN_MENSAJE]]
        restantes = len(self.problemas) - len(lineas)
        if restantes > 0:
            lineas.append(f"... y {restantes} problema(s) más.")
        super().__init__(f"El paquete de datos no es válido ({len(self.problemas)} problema(s)):\n" + "\n".join(lineas))
