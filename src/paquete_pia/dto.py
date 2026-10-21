"""Objetos de datos (DTO) del paquete 16_Eventos_Nova.

Reflejan las columnas de los CSV con su tipo ya convertido. No son objetos del dominio de Eventos Nova ni tienen
comportamiento de negocio: la correspondencia con el dominio se decidirá en una etapa posterior.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, Tuple


@dataclass(frozen=True)
class Actor:
    """Fila de actores.csv."""
    actor_id: str
    nombre: str
    es_preferente: bool
    activo: bool
    ciudad: str


@dataclass(frozen=True)
class RecursoCatalogo:
    """Fila de catalogo.csv."""
    recurso_id: str
    descripcion: str
    precio_mxn: Decimal
    capacidad_o_stock: int
    habilitado: bool


@dataclass(frozen=True)
class Operacion:
    """Fila de operaciones.csv."""
    operacion_id: str
    actor_id: str
    estado_inicial: str
    fecha_solicitud: date
    promocion_activa: bool
    autorizado: bool
    referencia: str


@dataclass(frozen=True)
class DetalleOperacion:
    """Fila de detalle_operaciones.csv."""
    operacion_id: str
    recurso_id: str
    cantidad: int


@dataclass(frozen=True)
class CasoPrueba:
    """Fila de casos_prueba.csv. `resultado_alumno` se conserva como texto: es una columna de salida."""
    caso_id: str
    operacion_id: str
    tipo_prueba: str
    regla_a_verificar: str
    resultado_alumno: str
    instrucciones: str


@dataclass(frozen=True)
class TransicionPrueba:
    """Fila de transiciones_prueba.csv. `resultado_alumno` se conserva como texto: es una columna de salida."""
    caso_id: str
    operacion_id: str
    accion_sugerida: str
    estado_inicial: str
    resultado_alumno: str
    instrucciones: str


@dataclass(frozen=True)
class PaquetePIA:
    """Contenido validado del paquete, en el mismo orden de los archivos."""
    actores: Tuple[Actor, ...]
    catalogo: Tuple[RecursoCatalogo, ...]
    operaciones: Tuple[Operacion, ...]
    detalle_operaciones: Tuple[DetalleOperacion, ...]
    casos_prueba: Tuple[CasoPrueba, ...]
    transiciones_prueba: Tuple[TransicionPrueba, ...]

    def conteos(self) -> Dict[str, int]:
        """Número de registros por archivo."""
        return {
            "actores.csv": len(self.actores),
            "catalogo.csv": len(self.catalogo),
            "operaciones.csv": len(self.operaciones),
            "detalle_operaciones.csv": len(self.detalle_operaciones),
            "casos_prueba.csv": len(self.casos_prueba),
            "transiciones_prueba.csv": len(self.transiciones_prueba),
        }
