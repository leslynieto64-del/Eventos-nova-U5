"""Base de Aggregate Root: registra Domain Events pendientes de publicar después del commit."""
from __future__ import annotations
from typing import List
from .eventos_dominio import EventoDominio


class AggregateRoot:
    def __init__(self, id_: str):
        self.id = id_
        self._eventos: List[EventoDominio] = []

    def _registrar(self, evento: EventoDominio) -> None:
        self._eventos.append(evento)

    def extraer_eventos(self) -> List[EventoDominio]:
        eventos, self._eventos = self._eventos, []
        return eventos
