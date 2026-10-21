"""State Machine explícita y declarativa (Etapa E3).

Una MaquinaEstados se define con una tabla de transiciones (estado de origen, acción) → estado de destino. Responde
si una acción está permitida desde un estado y cuál es su destino; si no lo está, lanza TransicionNoPermitida con el
mensaje de rechazo que el agregado ya comunicaba. También declara las repeticiones idempotentes: acciones que, en
el estado al que ya condujeron, se aceptan sin efecto.

La máquina solo valida pares estado-acción. No evalúa condiciones de negocio (eso lo hacen las Specifications y el
propio agregado) ni modifica el estado: el agregado asigna el destino que la máquina le devuelve.
No depende de bibliotecas externas.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, Generic, Iterable, Optional, Tuple, TypeVar

from .valores import ErrorDominio

E = TypeVar("E")      # tipo de estado (una Enum del dominio)
A = TypeVar("A")      # tipo de acción


class TransicionNoPermitida(ErrorDominio):
    """La acción no está permitida desde el estado actual. Es un ErrorDominio: se trata como rechazo de negocio."""

    def __init__(self, mensaje: str, origen=None, accion=None):
        super().__init__(mensaje)
        self.origen, self.accion = origen, accion


@dataclass(frozen=True)
class Transicion(Generic[E, A]):
    origen: E
    accion: A
    destino: E


class MaquinaEstados(Generic[E, A]):
    def __init__(self, estados: Iterable[E], transiciones: Iterable[Transicion],
                 repeticiones_idempotentes: Iterable[Tuple[E, A]] = (),
                 mensajes_rechazo: Optional[Dict[A, Callable[[E], str]]] = None, nombre: str = ""):
        self.nombre = nombre
        self.estados: Tuple[E, ...] = tuple(estados)
        self.transiciones: Tuple[Transicion, ...] = tuple(transiciones)
        self._tabla: Dict[Tuple[E, A], E] = {}
        for t in self.transiciones:
            for estado in (t.origen, t.destino):
                if estado not in self.estados:
                    raise ValueError(f"Estado desconocido en la tabla: {estado!r}")
            clave = (t.origen, t.accion)
            if clave in self._tabla:
                raise ValueError(f"Transición duplicada para {clave!r}")
            self._tabla[clave] = t.destino
        self.repeticiones_idempotentes: FrozenSet[Tuple[E, A]] = frozenset(repeticiones_idempotentes)
        for clave in self.repeticiones_idempotentes:
            if clave in self._tabla:
                raise ValueError(f"{clave!r} no puede ser a la vez transición y repetición idempotente")
        self._mensajes = dict(mensajes_rechazo or {})

    # -- consultas
    @property
    def acciones(self) -> FrozenSet[A]:
        return frozenset(a for _, a in self._tabla) | frozenset(a for _, a in self.repeticiones_idempotentes)

    def destino(self, origen: E, accion: A) -> Optional[E]:
        return self._tabla.get((origen, accion))

    def permite(self, origen: E, accion: A) -> bool:
        return (origen, accion) in self._tabla

    def es_repeticion(self, estado: E, accion: A) -> bool:
        """La acción ya produjo este estado y repetirla se acepta sin efecto (idempotencia)."""
        return (estado, accion) in self.repeticiones_idempotentes

    def acciones_desde(self, origen: E) -> FrozenSet[A]:
        return frozenset(a for (o, a) in self._tabla if o == origen)

    @property
    def estados_terminales(self) -> FrozenSet[E]:
        """Estados sin transiciones de salida."""
        con_salida = {o for (o, _) in self._tabla}
        return frozenset(e for e in self.estados if e not in con_salida)

    def mensaje_rechazo(self, origen: E, accion: A) -> str:
        if accion in self._mensajes:
            return self._mensajes[accion](origen)
        return f"La acción {getattr(accion, 'value', accion)} no está permitida desde {getattr(origen, 'value', origen)}."

    # -- validación
    def validar(self, origen: E, accion: A) -> None:
        if not self.permite(origen, accion):
            raise TransicionNoPermitida(self.mensaje_rechazo(origen, accion), origen, accion)

    def transitar(self, origen: E, accion: A) -> E:
        """Destino de la transición o TransicionNoPermitida. No modifica nada: el agregado asigna el estado."""
        self.validar(origen, accion)
        return self._tabla[(origen, accion)]
