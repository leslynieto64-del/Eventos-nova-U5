"""Patrón Specification (Etapa E2): base genérica y combinadores AND, OR y NOT.

Una especificación responde si un candidato satisface una condición de negocio y, cuando no la satisface, explica
por qué mediante una lista ordenada de incumplimientos (especificación que falló y su motivo). Así el dominio puede
conservar sus listas de requisitos pendientes (todos los motivos) y sus rechazos con un único motivo (el primero
según el orden de evaluación).

No depende de ninguna biblioteca externa ni de otras partes del dominio.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple


@dataclass(frozen=True)
class Incumplimiento:
    """Especificación no satisfecha y el motivo con el que el dominio lo comunica."""
    especificacion: "Especificacion"
    motivo: str


class Especificacion(ABC):
    """Condición evaluable sobre un candidato.

    - `es_satisfecha_por(candidato)`: True o False.
    - `incumplimientos(candidato)`: lista ordenada de Incumplimiento (vacía si se satisface).
    - `motivos_incumplimiento(candidato)` y `primer_motivo(candidato)`: atajos sobre la lista anterior.
    - Composición: `y()`, `o()`, `no()` o los operadores `&`, `|` y `~`; `con_motivo()` reemplaza los motivos de
      una especificación (simple o compuesta) por un único motivo propio.
    """

    descripcion: str = ""

    @abstractmethod
    def es_satisfecha_por(self, candidato: Any) -> bool:
        ...

    def motivo(self, candidato: Any) -> str:
        """Motivo de incumplimiento de una especificación simple. Puede depender del candidato."""
        return self.descripcion or type(self).__name__

    def incumplimientos(self, candidato: Any) -> List[Incumplimiento]:
        return [] if self.es_satisfecha_por(candidato) else [Incumplimiento(self, self.motivo(candidato))]

    # -- atajos
    def motivos_incumplimiento(self, candidato: Any) -> List[str]:
        return [i.motivo for i in self.incumplimientos(candidato)]

    def primer_incumplimiento(self, candidato: Any) -> Optional[Incumplimiento]:
        lista = self.incumplimientos(candidato)
        return lista[0] if lista else None

    def primer_motivo(self, candidato: Any) -> Optional[str]:
        i = self.primer_incumplimiento(candidato)
        return i.motivo if i else None

    # -- composición
    def y(self, *otras: "Especificacion") -> "Especificacion":
        return Y(self, *otras)

    def o(self, *otras: "Especificacion") -> "Especificacion":
        return O(self, *otras)

    def no(self, motivo: Optional[str] = None) -> "Especificacion":
        return No(self, motivo)

    def con_motivo(self, motivo: str) -> "Especificacion":
        return ConMotivo(self, motivo)

    def __and__(self, otra: "Especificacion") -> "Especificacion":
        return Y(self, otra)

    def __or__(self, otra: "Especificacion") -> "Especificacion":
        return O(self, otra)

    def __invert__(self) -> "Especificacion":
        return No(self)

    def __repr__(self) -> str:
        return self.descripcion or type(self).__name__


class EspecificacionSimple(Especificacion):
    """Especificación definida por un predicado y un motivo; útil para condiciones puntuales y para pruebas."""

    def __init__(self, predicado: Callable[[Any], bool], motivo: str, descripcion: str = ""):
        self._predicado, self._motivo = predicado, motivo
        self.descripcion = descripcion or motivo

    def es_satisfecha_por(self, candidato: Any) -> bool:
        return bool(self._predicado(candidato))

    def motivo(self, candidato: Any) -> str:
        return self._motivo


class _Compuesta(Especificacion):
    SIMBOLO = ""

    def __init__(self, *partes: Especificacion):
        if len(partes) < 2:
            raise ValueError(f"{type(self).__name__} combina al menos dos especificaciones.")
        aplanadas: List[Especificacion] = []
        for p in partes:                                  # (a & b) & c se guarda como Y(a, b, c): conserva el orden
            aplanadas.extend(p.partes if type(p) is type(self) else (p,))
        self.partes: Tuple[Especificacion, ...] = tuple(aplanadas)
        self.descripcion = "(" + f" {self.SIMBOLO} ".join(repr(p) for p in self.partes) + ")"


class Y(_Compuesta):
    """AND: se satisface si todas las partes se satisfacen. Los incumplimientos de las partes se informan en el
    orden en que se combinaron; ese orden define también el primer motivo."""
    SIMBOLO = "Y"

    def es_satisfecha_por(self, candidato: Any) -> bool:
        return all(p.es_satisfecha_por(candidato) for p in self.partes)

    def incumplimientos(self, candidato: Any) -> List[Incumplimiento]:
        return [i for p in self.partes for i in p.incumplimientos(candidato)]

    def primer_incumplimiento(self, candidato: Any) -> Optional[Incumplimiento]:
        """N6: el primer incumplimiento es el de la primera parte que no se satisface (el mismo que el primero de
        `incumplimientos`), pero las partes posteriores ya no se evalúan."""
        for p in self.partes:
            i = p.primer_incumplimiento(candidato)
            if i is not None:
                return i
        return None


class O(_Compuesta):
    """OR: se satisface si alguna parte se satisface. Si ninguna lo hace, informa los incumplimientos de todas
    (en orden), salvo que se le asigne un motivo propio con `con_motivo()`."""
    SIMBOLO = "O"

    def es_satisfecha_por(self, candidato: Any) -> bool:
        return any(p.es_satisfecha_por(candidato) for p in self.partes)

    def incumplimientos(self, candidato: Any) -> List[Incumplimiento]:
        if self.es_satisfecha_por(candidato):
            return []
        return [i for p in self.partes for i in p.incumplimientos(candidato)]


class No(Especificacion):
    """NOT: se satisface si la especificación interna no se satisface."""

    def __init__(self, interna: Especificacion, motivo: Optional[str] = None):
        self.interna, self._motivo = interna, motivo
        self.descripcion = f"NO {interna!r}"

    def es_satisfecha_por(self, candidato: Any) -> bool:
        return not self.interna.es_satisfecha_por(candidato)

    def motivo(self, candidato: Any) -> str:
        return self._motivo or self.descripcion


class ConMotivo(Especificacion):
    """Misma condición que la especificación interna, con un único motivo propio de incumplimiento."""

    def __init__(self, interna: Especificacion, motivo: str):
        self.interna, self._motivo = interna, motivo
        self.descripcion = interna.descripcion

    def es_satisfecha_por(self, candidato: Any) -> bool:
        return self.interna.es_satisfecha_por(candidato)

    def motivo(self, candidato: Any) -> str:
        return self._motivo
