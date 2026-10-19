"""Interfaces que la aplicación necesita. Las implementa la infraestructura (inversión de dependencias)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from domain.propuesta import Propuesta
from domain.contrato import Contrato
from domain.evento import Evento
from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor
from domain.estado_cuenta import EstadoCuenta
from domain.eventos_dominio import EventoDominio
from domain.valores import DisponibilidadProveedor


# ---------------------------------------------------------------- Repository (uno por raíz)
# Contrato común: obtener_por_id devuelve el agregado completo o None; guardar persiste el agregado completo;
# los métodos listar_* son de lectura y no cambian estados (hallazgo H-05).
class IPropuestaRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, propuesta_id: str) -> Optional[Propuesta]: ...
    @abstractmethod
    def listar_por_evento_id(self, evento_id: str) -> List[Propuesta]: ...
    @abstractmethod
    def guardar(self, propuesta: Propuesta) -> None: ...


class IContratoRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, contrato_id: str) -> Optional[Contrato]: ...
    @abstractmethod
    def listar_por_evento_id(self, evento_id: str) -> List[Contrato]: ...
    @abstractmethod
    def guardar(self, contrato: Contrato) -> None: ...


class IEventoRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, evento_id: str) -> Optional[Evento]: ...
    @abstractmethod
    def guardar(self, evento: Evento) -> None: ...


class ISolicitudCambioRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, solicitud_id: str) -> Optional[SolicitudCambio]: ...
    @abstractmethod
    def listar_pendientes_por_evento_id(self, evento_id: str) -> List[SolicitudCambio]: ...
    @abstractmethod
    def guardar(self, solicitud: SolicitudCambio) -> None: ...


class ISolicitudServicioAdicionalRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, solicitud_id: str) -> Optional[SolicitudServicioAdicional]: ...
    @abstractmethod
    def listar_pendientes_por_evento_id(self, evento_id: str) -> List[SolicitudServicioAdicional]: ...
    @abstractmethod
    def guardar(self, solicitud: SolicitudServicioAdicional) -> None: ...


class ISustitucionProveedorRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, sustitucion_id: str) -> Optional[SustitucionProveedor]: ...
    @abstractmethod
    def listar_pendientes_por_evento_id(self, evento_id: str) -> List[SustitucionProveedor]: ...
    @abstractmethod
    def guardar(self, sustitucion: SustitucionProveedor) -> None: ...


class IEstadoCuentaRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, estado_cuenta_id: str) -> Optional[EstadoCuenta]: ...
    @abstractmethod
    def obtener_por_contrato_id(self, contrato_id: str) -> Optional[EstadoCuenta]: ...
    @abstractmethod
    def listar_por_evento_id(self, evento_id: str) -> List[EstadoCuenta]: ...
    @abstractmethod
    def guardar(self, estado_cuenta: EstadoCuenta) -> None: ...


# ---------------------------------------------------------------- otros puertos
class IUnitOfWork(ABC):
    """iniciar / confirmar / revertir. Al confirmar guarda los Domain Events en el Outbox (propuesta)."""
    @abstractmethod
    def iniciar(self) -> None: ...
    @abstractmethod
    def registrar(self, *agregados) -> None:
        """Indica qué agregados participan; sus Domain Events se extraen al confirmar."""
    @abstractmethod
    def confirmar(self) -> None: ...
    @abstractmethod
    def revertir(self) -> None: ...


class IPublicadorEventosDominio(ABC):
    @abstractmethod
    def suscribir(self, tipo_evento: type, reaccion: Callable[[EventoDominio], None]) -> None: ...
    @abstractmethod
    def publicar(self, evento: EventoDominio) -> None: ...


class IConsultaDisponibilidadProveedor(ABC):
    @abstractmethod
    def consultar(self, servicio: str, fecha_evento, proveedores_actuales: List[str]) -> List[DisponibilidadProveedor]: ...


class INotificadorParticipantes(ABC):
    @abstractmethod
    def notificar(self, destinatarios: List[str], asunto: str, detalle: str) -> None: ...


class IVerificadorPagos(ABC):
    @abstractmethod
    def verificar(self, comprobante: str, importe) -> bool: ...


class IEjecutorDevoluciones(ABC):
    @abstractmethod
    def ejecutar(self, devolucion_id: str, importe, referencia_idempotente: str) -> str:
        """Devuelve el comprobante de la devolución."""
