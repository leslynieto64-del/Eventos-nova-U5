"""Reglas ilustrativas del paquete, implementadas como Specifications (LEEME, «Reglas de prueba ilustrativas»).

    1. puede_procesarse:     actor activo AND operación con al menos una línea AND autorización
    2. beneficio_referencia: actor preferente AND total >= 1500 MXN AND NOT promoción activa

El BRD, las User Stories y el glosario de Eventos Nova no contienen clientes activos o inactivos, clientes
preferentes, promociones ni beneficios (diferencias D-01 y D-02 en `mapeo.DIFERENCIAS`). Por eso estas reglas viven
aquí, como modelo de pruebas del paquete, y no se incorporan al dominio. Se construyen con la base y los
combinadores del patrón Specification del proyecto (`domain.especificacion`), sin modificarlos.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

from domain.especificacion import Especificacion

UMBRAL_BENEFICIO = Decimal("1500")      # «total >= 1500 MXN»: el umbral está incluido


@dataclass(frozen=True)
class SituacionOperacion:
    """Candidato de las reglas: datos de una operación del paquete y de su actor."""
    operacion_id: str
    actor_activo: bool
    actor_preferente: bool
    autorizada: bool
    promocion_activa: bool
    lineas: int
    total: Decimal


class ActorActivo(Especificacion):
    descripcion = "actor activo"

    def es_satisfecha_por(self, s: SituacionOperacion) -> bool:
        return s.actor_activo


class DetalleNoVacio(Especificacion):
    descripcion = "detalle no vacío"

    def es_satisfecha_por(self, s: SituacionOperacion) -> bool:
        return s.lineas > 0


class OperacionAutorizada(Especificacion):
    descripcion = "autorización"

    def es_satisfecha_por(self, s: SituacionOperacion) -> bool:
        return s.autorizada


class ActorPreferente(Especificacion):
    descripcion = "actor preferente (VIP)"

    def es_satisfecha_por(self, s: SituacionOperacion) -> bool:
        return s.actor_preferente


class TotalMinimo(Especificacion):
    def __init__(self, minimo: Decimal):
        self.minimo = minimo
        self.descripcion = f"total >= {minimo}"

    def es_satisfecha_por(self, s: SituacionOperacion) -> bool:
        return s.total >= self.minimo


class PromocionActiva(Especificacion):
    descripcion = "promoción activa"

    def es_satisfecha_por(self, s: SituacionOperacion) -> bool:
        return s.promocion_activa


PUEDE_PROCESARSE = ActorActivo() & DetalleNoVacio() & OperacionAutorizada()
BENEFICIO_REFERENCIA = ActorPreferente() & TotalMinimo(UMBRAL_BENEFICIO) & (~PromocionActiva()).con_motivo(
    "sin promoción activa")

REGLAS = {"validar_operacion": PUEDE_PROCESARSE, "evaluar_beneficio": BENEFICIO_REFERENCIA}
