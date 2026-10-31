"""Base de Aggregate Root: registra Domain Events pendientes de publicar después del commit."""
from __future__ import annotations
from typing import List, Optional
from .eventos_dominio import EventoDominio


class AggregateRoot:
    # Metadato de persistencia (control de concurrencia optimista): versión leída de la base de datos; None si el agregado
    # todavía no se ha guardado. Solo la infraestructura lo asigna (queda en la instancia al leer o guardar) y lo lee; el dominio
    # no lo usa. Es un atributo de clase para que un agregado recién creado conserve exactamente los mismos atributos de siempre.
    _version: Optional[int] = None

    def __init__(self, id_: str):
        self.id = id_
        self._eventos: List[EventoDominio] = []

    def _registrar(self, evento: EventoDominio) -> None:
        self._eventos.append(evento)

    def extraer_eventos(self) -> List[EventoDominio]:
        eventos, self._eventos = self._eventos, []
        return eventos
