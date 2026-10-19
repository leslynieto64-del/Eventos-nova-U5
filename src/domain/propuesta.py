"""Aggregate Propuesta (raíz) con la entidad interna VersionPropuesta."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from .base import AggregateRoot
from .valores import ContenidoPropuesta, EstadoPropuesta, ErrorDominio
from .eventos_dominio import PropuestaAceptada, VersionPropuestaGenerada, PropuestaCerradaPorNoAceptacion


@dataclass
class VersionPropuesta:
    version_id: str
    numero: int
    fecha_actualizacion: datetime
    contenido: ContenidoPropuesta


class Propuesta(AggregateRoot):
    def __init__(self, propuesta_id: str, evento_id: str, cliente_id: str, contenido: ContenidoPropuesta, ahora: datetime):
        super().__init__(propuesta_id)
        self.evento_id, self.cliente_id = evento_id, cliente_id
        self.versiones: List[VersionPropuesta] = [VersionPropuesta(f"{propuesta_id}-v1", 1, ahora, contenido)]
        self.version_vigente_id = self.versiones[0].version_id   # GL-008: referencia, no clase
        self.estado = EstadoPropuesta.EN_REVISION_CLIENTE
        self.motivo_cierre: Optional[str] = None

    def _abierta(self) -> None:
        if self.estado in (EstadoPropuesta.ACEPTADA, EstadoPropuesta.CERRADA_NO_ACEPTACION):
            raise ErrorDominio(f"La propuesta está {self.estado.value}.")

    def generar_nueva_version(self, contenido: ContenidoPropuesta, ahora: datetime) -> VersionPropuesta:
        """BN-002, CA-007, CA-009: número consecutivo y una sola versión vigente."""
        self._abierta()
        numero = max(v.numero for v in self.versiones) + 1
        v = VersionPropuesta(f"{self.id}-v{numero}", numero, ahora, contenido)
        self.versiones.append(v)
        self.version_vigente_id = v.version_id
        self._registrar(VersionPropuestaGenerada(self.id, ahora, numero=numero))
        return v

    def aceptar(self, version_id: str, ahora: datetime) -> None:
        self._abierta()
        if version_id != self.version_vigente_id:
            raise ErrorDominio("Solo puede aceptarse la versión vigente (CA-013).")
        self.estado = EstadoPropuesta.ACEPTADA
        self._registrar(PropuestaAceptada(self.id, ahora, evento_ref=self.evento_id))

    def cerrar_por_no_aceptacion(self, motivo: str, ahora: datetime) -> None:
        """CA-092. No cambia el Evento: permanece En gestión (SE-011)."""
        self._abierta()
        self.estado, self.motivo_cierre = EstadoPropuesta.CERRADA_NO_ACEPTACION, motivo
        self._registrar(PropuestaCerradaPorNoAceptacion(self.id, ahora))

    def version_aceptada(self) -> VersionPropuesta:
        if self.estado != EstadoPropuesta.ACEPTADA:
            raise ErrorDominio("La propuesta no ha sido aceptada.")
        return next(v for v in self.versiones if v.version_id == self.version_vigente_id)
