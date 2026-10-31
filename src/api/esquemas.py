"""Esquemas de entrada y respuesta de la API (Pydantic) y su conversión a objetos del dominio.

Los esquemas solo validan la *forma* de la petición (campos presentes, tipos, sin campos desconocidos).
Las reglas de negocio —datos completos del evento (CA-003), contenido de la propuesta (CA-005), importe no
negativo— las sigue aplicando el dominio al construir DatosEvento, ContenidoPropuesta e Importe; aquí no se repiten.
Este módulo depende de Pydantic y del dominio, no de FastAPI ni de la infraestructura."""
from __future__ import annotations
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, field_validator
from domain.valores import DatosEvento, ContenidoPropuesta, Importe, MAXIMO_TECNICO_BIGINT


class _Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- entrada
class DatosEventoEntrada(_Esquema):
    """Campos de DatosEvento. La fecha y hora se envían sin zona horaria, como las maneja el dominio."""
    tipo: str = Field(examples=["Boda"])
    fecha_hora: NaiveDatetime = Field(examples=["2026-11-20T18:00:00"])
    lugar: str = Field(examples=["Salón"])
    invitados_aproximados: int = Field(examples=[100], le=MAXIMO_TECNICO_BIGINT)    # límite técnico de BIGINT, no de negocio

    @field_validator("invitados_aproximados", mode="before")
    @classmethod
    def _no_booleano(cls, valor):
        """Pydantic convierte True en 1; un booleano no es una cantidad de invitados."""
        if isinstance(valor, bool):
            raise ValueError("invitados_aproximados debe ser un número entero, no un booleano")
        return valor

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
    costo_total: Decimal = Field(examples=["10000.00"], allow_inf_nan=False)   # sin NaN ni infinitos; el dominio rechaza negativos
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


# ---------------------------------------------------------------- respuesta de GET /eventos/{evento_id}/pagos
class ObligacionPagoRespuesta(_Esquema):
    """Anticipo o saldo del contrato original. Vacío si el Estado de Cuenta no tiene esa obligación; `plazoVencido` solo se
    informa cuando la consulta recibe reloj (CA-023); `resultadoRegularizacion` solo aparece en el saldo ya revisado."""
    importe: Optional[str] = None
    fechaLimite: Optional[str] = Field(default=None, description="Vencimiento del plazo (ISO 8601); null si la obligación no tiene plazo")
    estado: Optional[str] = None
    plazoVencido: Optional[bool] = Field(default=None, description="true si la obligación sigue Pendiente o Vencida y su plazo ya venció a la hora de la consulta (CA-023)")
    resultadoRegularizacion: Optional[str] = Field(default=None, description="«Regularizado» o «No regularizado», registrado por Administración")


class PagoRegistradoRespuesta(_Esquema):
    concepto: str
    importe: str
    fecha: str
    estado: str
    registradoEn: Optional[str] = None
    verificadoEn: Optional[str] = None


class ObligacionAdicionalRespuesta(_Esquema):
    concepto: str
    importe: str
    plazo: Optional[str] = None
    estado: str


class DevolucionRespuesta(_Esquema):
    devolucionId: str
    solicitudId: Optional[str] = None
    concepto: str
    importe: str
    estado: str
    fechaCierre: str
    fechaLimite: str
    fechaDevolucion: Optional[str] = None
    comprobante: Optional[str] = None
    enPlazo: Optional[bool] = None
    tipo: str
    pagoId: Optional[str] = None


class EstadoCuentaResumenRespuesta(_Esquema):
    estadoCuentaId: str
    contratoId: str
    anticipo: ObligacionPagoRespuesta
    pagosRegistrados: List[PagoRegistradoRespuesta]
    saldoContratoOriginal: ObligacionPagoRespuesta
    obligacionesAdicionales: List[ObligacionAdicionalRespuesta]
    devoluciones: List[DevolucionRespuesta]


class EstadoPagosRespuesta(_Esquema):
    eventoId: str
    estadosCuenta: List[EstadoCuentaResumenRespuesta]
