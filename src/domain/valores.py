"""Value Objects y enumeraciones del mapa de dominio (Etapa 3, modelo v1.4)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional


class ErrorDominio(Exception):
    """Rechazo de negocio expresado con términos del glosario."""


# ---------------------------------------------------------------- enumeraciones
class EstadoEvento(Enum):
    EN_GESTION = "En gestión"
    EN_ORGANIZACION = "En organización"
    EN_EJECUCION = "En ejecución"
    FINALIZADO = "Finalizado"
    CANCELADO = "Cancelado"
    CERRADO_SIN_CONTRATACION = "Cerrado sin contratación"


class EstadoPropuesta(Enum):
    EN_ELABORACION = "En elaboración"
    EN_REVISION_CLIENTE = "En revisión del Cliente"
    ACEPTADA = "Aceptada"
    CERRADA_NO_ACEPTACION = "Cerrada por no aceptación"


class EstadoContrato(Enum):
    EN_PREPARACION = "En preparación"
    FIRMADO = "Firmado"
    CONTRATACION_CONFIRMADA = "Contratación confirmada"
    CERRADO_SIN_CONFIRMAR = "Cerrado sin confirmar"


class EstadoSolicitudCambio(Enum):
    REGISTRADA = "Registrada"
    DETENIDA_SALDO_VENCIDO = "Detenida por saldo vencido"
    EN_EVALUACION = "En evaluación"
    PENDIENTE_APROBACION_CLIENTE = "Pendiente de aprobación del Cliente"
    PENDIENTE_AUTORIZACION = "Pendiente de autorización"
    PENDIENTE_FORMALIZACION = "Pendiente de formalización"
    PENDIENTE_PAGO = "Pendiente de pago"
    CONFIRMADA = "Confirmada"
    NO_PROCEDENTE = "No procedente"
    RECHAZADA_CLIENTE = "Rechazada por el Cliente"
    NO_AUTORIZADA = "No autorizada"
    CERRADA_FALTA_PAGO = "Cerrada por falta de pago"
    CERRADA_INICIO_EVENTO = "Cerrada por inicio del evento"
    CERRADA_EVENTO_CANCELADO = "Cerrada por evento cancelado"


class EstadoSolicitudServicioAdicional(Enum):
    REGISTRADA = "Registrada"
    DETENIDA_SALDO_VENCIDO = "Detenida por saldo vencido"
    EN_BUSQUEDA_PROVEEDOR = "En búsqueda de proveedor"
    PENDIENTE_APROBACION_CLIENTE = "Pendiente de aprobación del Cliente"
    PENDIENTE_AUTORIZACION = "Pendiente de autorización"
    AUTORIZADA = "Autorizada"
    PENDIENTE_PAGO = "Pendiente de pago"
    CONFIRMADA = "Confirmada"
    NO_PROCEDENTE = "No procedente"
    NO_SE_REALIZARA = "No se realizará"
    NO_APROBADA = "No aprobada"
    NO_AUTORIZADA = "No autorizada"
    CERRADA_FALTA_PAGO = "Cerrada por falta de pago"
    CERRADA_INICIO_EVENTO = "Cerrada por inicio del evento"
    CERRADA_EVENTO_CANCELADO = "Cerrada por evento cancelado"


class EstadoSustitucionProveedor(Enum):
    EN_BUSQUEDA_ALTERNATIVA = "En búsqueda de alternativa"
    PENDIENTE_APROBACION_CLIENTE = "Pendiente de aprobación del Cliente"
    PENDIENTE_AUTORIZACION = "Pendiente de autorización"
    PENDIENTE_FORMALIZACION = "Pendiente de formalización"
    CONFIRMADA = "Confirmada"
    CERRADA_INICIO_EVENTO = "Cerrada por inicio del evento"
    CERRADA_EVENTO_CANCELADO = "Cerrada por evento cancelado"


class EstadoSolicitudCancelacion(Enum):
    REGISTRADA = "Registrada"
    PROCEDENTE = "Procedente"
    RECHAZADA_INICIO_EVENTO = "Rechazada por inicio del evento"


class EstadoObligacionPago(Enum):
    PENDIENTE = "Pendiente"
    VENCIDA = "Vencida"
    LIQUIDADA = "Liquidada"
    SIN_EFECTO = "Sin efecto"


class EstadoPago(Enum):
    REGISTRADO = "Registrado"
    VERIFICADO = "Verificado"
    IMPORTE_INCORRECTO = "Importe incorrecto"


class EstadoDevolucion(Enum):
    PENDIENTE = "Pendiente"
    EFECTUADA = "Efectuada"


class ConceptoPago(Enum):
    ANTICIPO = "Anticipo"
    SALDO_CONTRATO_ORIGINAL = "SaldoContratoOriginal"
    SUSTITUCION_PROVEEDOR = "SustitucionProveedor"
    CAMBIO = "Cambio"
    CARGO_CAMBIO_TARDIO = "CargoCambioTardio"
    CARGOS_MORATORIOS = "CargosMoratorios"
    SERVICIO_ADICIONAL = "ServicioAdicional"


class TipoSolicitud(Enum):
    CAMBIO = "cambio"
    SERVICIO_ADICIONAL = "servicio adicional"
    SUSTITUCION_PROVEEDOR = "sustitución de proveedor"


class OrigenCancelacion(Enum):
    SOLICITUD_CLIENTE = "Solicitud del Cliente"
    FALTA_REGULARIZACION = "Falta de regularización del saldo vencido"


class CausaCierreSolicitud(Enum):
    NO_VIABLE = "No viable"
    RECHAZO_CLIENTE = "Rechazo del Cliente"
    NO_AUTORIZADA = "No autorizada por Administración"
    FALTA_PAGO = "Falta de pago"
    PLAZO_INSUFICIENTE = "Plazo insuficiente"
    CLIENTE_NO_ESPERA = "El Cliente no acepta esperar"
    INICIO_EVENTO = "Inicio del evento"
    EVENTO_CANCELADO = "Evento cancelado"


# ---------------------------------------------------------------- Value Objects
@dataclass(frozen=True)
class Importe:
    cantidad: Decimal

    def __post_init__(self):
        if self.cantidad < 0:
            raise ErrorDominio("El importe no puede ser negativo.")

    def __add__(self, otro: "Importe") -> "Importe":
        return Importe(self.cantidad + otro.cantidad)

    def porcentaje(self, pct: Decimal) -> "Importe":
        return Importe((self.cantidad * pct / Decimal(100)).quantize(Decimal("0.01")))


@dataclass(frozen=True)
class DatosEvento:
    tipo: str
    fecha_hora: datetime
    lugar: str
    invitados_aproximados: int

    def __post_init__(self):
        if not self.tipo or not self.lugar or self.invitados_aproximados <= 0:
            raise ErrorDominio("Los datos del evento están incompletos (CA-003).")


@dataclass(frozen=True)
class ContenidoPropuesta:
    servicios: tuple
    proveedores_considerados: tuple
    costo_total: Importe
    condiciones: str

    def __post_init__(self):
        if not self.servicios or not self.condiciones:
            raise ErrorDominio("La propuesta debe incluir servicios, proveedores, costos y condiciones (CA-005).")


@dataclass(frozen=True)
class CondicionesContractuales:
    servicios: tuple
    costo_total: Importe
    condiciones: str


@dataclass(frozen=True)
class PoliticaNoReembolso:
    incluida: bool
    comunicada_en: Optional[datetime] = None

    def comunicada(self) -> bool:
        return self.incluida and self.comunicada_en is not None


@dataclass(frozen=True)
class CondicionesServicio:
    descripcion: str


@dataclass(frozen=True)
class DisponibilidadProveedor:
    proveedor_id: str
    disponible: bool
    costo: Optional[Importe] = None
    condiciones: Optional[CondicionesServicio] = None


@dataclass(frozen=True)
class ImpactoModificacion:
    afecta_servicios: bool
    afecta_costos: bool
    afecta_condiciones: bool

    @property
    def tiene_impacto(self) -> bool:
        """Specification MODIFICACION_CON_IMPACTO: servicios OR costos OR condiciones (sustitución de proveedor)."""
        from .especificaciones import MODIFICACION_CON_IMPACTO      # importación diferida: evita el ciclo con valores
        return MODIFICACION_CON_IMPACTO.es_satisfecha_por(self)


@dataclass(frozen=True)
class ResultadoViabilidad:
    viable: bool
    motivo: str = ""


@dataclass(frozen=True)
class Decision:
    actor: str
    aprobada: bool
    fecha: datetime
    motivo: str = ""


@dataclass(frozen=True)
class AnticipacionSolicitud:
    fecha_solicitud: datetime
    fecha_evento: datetime

    @property
    def dias_naturales(self) -> int:
        return (self.fecha_evento.date() - self.fecha_solicitud.date()).days


@dataclass(frozen=True)
class TarifaCargoTardio:
    """Tarifa vigente al registrar la solicitud; el importe lo informa el negocio (BN-003)."""
    importe: Importe


@dataclass(frozen=True)
class PlazoPago:
    inicio: datetime
    vence: datetime

    @staticmethod
    def horas_naturales(inicio: datetime, horas: int) -> "PlazoPago":
        return PlazoPago(inicio, inicio + timedelta(hours=horas))

    @staticmethod
    def dias_habiles(inicio: datetime, dias: int) -> "PlazoPago":
        return PlazoPago(inicio, sumar_dias_habiles(inicio, dias))

    def vencido(self, ahora: datetime) -> bool:
        return ahora > self.vence


@dataclass(frozen=True)
class MotivoCancelacionEvento:
    """Motivo de la cancelación del Evento. No se usa para cierres de solicitudes ni devoluciones."""
    origen: OrigenCancelacion
    descripcion: str
    fecha: datetime
    registrado_por: str


@dataclass(frozen=True)
class MotivoCierreSolicitud:
    """Causa del cierre de una solicitud individual sin confirmarse."""
    causa: CausaCierreSolicitud
    descripcion: str
    fecha: datetime


@dataclass(frozen=True)
class CondicionTemporal:
    """Resultado que cada solicitud informa a EvaluarRegularizacionDeSolicitudes."""
    cumple: bool
    motivo: str = ""


def sumar_dias_habiles(inicio: datetime, dias: int) -> datetime:
    """Días hábiles: lunes a viernes, sin considerar días festivos (GL-060)."""
    actual, sumados = inicio, 0
    while sumados < dias:
        actual += timedelta(days=1)
        if actual.weekday() < 5:
            sumados += 1
    return actual


def restar_dias_habiles(fecha: datetime, dias: int) -> datetime:
    actual, restados = fecha, 0
    while restados < dias:
        actual -= timedelta(days=1)
        if actual.weekday() < 5:
            restados += 1
    return actual
