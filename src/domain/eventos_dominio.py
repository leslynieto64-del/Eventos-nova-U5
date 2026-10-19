"""Domain Events: hechos del negocio que ya ocurrieron (Detalle D)."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass(frozen=True)
class EventoDominio:
    agregado_id: str
    ocurrido_en: datetime
    evento_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def nombre(self) -> str:
        return type(self).__name__


# Coordinación (22)
@dataclass(frozen=True)
class PropuestaAceptada(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class ContratoFirmado(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class PagoVerificado(EventoDominio): obligacion_id: str = ""; concepto: str = ""; origen_id: Optional[str] = None
@dataclass(frozen=True)
class ContratacionConfirmada(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class ProcesoContratacionCerrado(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class AnexoContratoRegistrado(EventoDominio): anexo_id: str = ""; tipo_origen: str = ""; origen_id: str = ""
@dataclass(frozen=True)
class CambioConfirmado(EventoDominio):
    evento_ref: str = ""; descripcion: str = ""
    datos_propuestos: Optional[object] = None          # DatosEvento aprobado, si el cambio lo modifica
    condiciones_propuestas: tuple = ()                 # ((servicioContratadoId, CondicionesServicio), ...)
@dataclass(frozen=True)
class ServicioAdicionalConfirmado(EventoDominio):
    evento_ref: str = ""; servicio: str = ""; proveedor_id: str = ""
    condiciones: Optional[object] = None               # CondicionesServicio aprobadas por el Cliente (CA-079, CA-082)
@dataclass(frozen=True)
class ProveedorNoDisponible(EventoDominio): evento_ref: str = ""; servicio_contratado_id: str = ""
@dataclass(frozen=True)
class SustitucionProveedorConfirmada(EventoDominio): evento_ref: str = ""; servicio_contratado_id: str = ""; proveedor_id: str = ""
@dataclass(frozen=True)
class EventoIniciado(EventoDominio): pass
@dataclass(frozen=True)
class SolicitudCambioCerradaPorInicioEvento(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class ServicioAdicionalCerradoPorInicioEvento(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class SustitucionProveedorCerradaPorInicioEvento(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class SolicitudCambioCerradaPorFaltaDePago(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class ServicioAdicionalCerradoPorFaltaDePago(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class SaldoContratoOriginalVencido(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class SaldoVencidoRegularizado(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class PlazoRegularizacionVencido(EventoDominio): evento_ref: str = ""
@dataclass(frozen=True)
class EventoCancelado(EventoDominio): origen: str = ""
@dataclass(frozen=True)
class EventoFinalizado(EventoDominio): pass
@dataclass(frozen=True)
class DevolucionRegistrada(EventoDominio): devolucion_id: str = ""


# Auditoría (9)
@dataclass(frozen=True)
class VersionPropuestaGenerada(EventoDominio): numero: int = 0
@dataclass(frozen=True)
class PropuestaCerradaPorNoAceptacion(EventoDominio): pass
@dataclass(frozen=True)
class CambioSolicitado(EventoDominio): pass
@dataclass(frozen=True)
class ViabilidadCambioEvaluada(EventoDominio): viable: bool = False
@dataclass(frozen=True)
class ServicioAdicionalSolicitado(EventoDominio): pass
@dataclass(frozen=True)
class AlternativaProveedorEncontrada(EventoDominio): proveedor_id: str = ""
@dataclass(frozen=True)
class AlternativaRechazadaPorCliente(EventoDominio): proveedor_id: str = ""
@dataclass(frozen=True)
class AlternativaNoAutorizadaPorAdministracion(EventoDominio): proveedor_id: str = ""
@dataclass(frozen=True)
class CargosMoratoriosComunicados(EventoDominio): pass
