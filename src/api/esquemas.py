"""Esquemas de entrada y respuesta de la API (Pydantic) y su conversión a objetos del dominio.

Los esquemas solo validan la *forma* de la petición (campos presentes, tipos, sin campos desconocidos).
Las reglas de negocio —datos completos del evento (CA-003), contenido de la propuesta (CA-005), importe no
negativo— las sigue aplicando el dominio al construir DatosEvento, ContenidoPropuesta e Importe; aquí no se repiten.
Este módulo depende de Pydantic y del dominio, no de FastAPI ni de la infraestructura."""
from __future__ import annotations
from decimal import Decimal
from typing import List
from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime
from domain.valores import DatosEvento, ContenidoPropuesta, Importe


class _Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- entrada
class DatosEventoEntrada(_Esquema):
    """Campos de DatosEvento. La fecha y hora se envían sin zona horaria, como las maneja el dominio."""
    tipo: str = Field(examples=["Boda"])
    fecha_hora: NaiveDatetime = Field(examples=["2026-11-20T18:00:00"])
    lugar: str = Field(examples=["Salón"])
    invitados_aproximados: int = Field(examples=[100])

    def a_dominio(self) -> DatosEvento:
        return DatosEvento(self.tipo, self.fecha_hora, self.lugar, self.invitados_aproximados)


class RegistrarEventoEntrada(_Esquema):
    """Parámetros de GestionPropuestaService.registrar_evento."""
    cliente_id: str = Field(examples=["CL-1"])
    datos: DatosEventoEntrada
    servicios: List[str] = Field(examples=[["Banquete"]])


class CrearPropuestaEntrada(_Esquema):
    """Campos de ContenidoPropuesta. La fecha de la versión la asigna el servidor."""
    servicios: List[str] = Field(examples=[["Banquete"]])
    proveedores_considerados: List[str] = Field(examples=[["PV-1"]])
    costo_total: Decimal = Field(examples=["10000.00"])
    condiciones: str = Field(examples=["Condiciones generales"])

    def a_dominio(self) -> ContenidoPropuesta:
        return ContenidoPropuesta(tuple(self.servicios), tuple(self.proveedores_considerados),
                                  Importe(self.costo_total), self.condiciones)


# ---------------------------------------------------------------- respuesta
class EventoRegistradoRespuesta(_Esquema):
    evento_id: str
    mensaje: str


class PropuestaCreadaRespuesta(_Esquema):
    propuesta_id: str
    evento_id: str
    mensaje: str


class RechazoRespuesta(_Esquema):
    """Rechazo de negocio: el motivo es el que devuelve el servicio de aplicación o el dominio."""
    tipo: str = "rechazo_de_negocio"
    detalle: str
    pendientes: List[str] = []
