"""Especificaciones de negocio de Eventos Nova (Etapa E2).

Cada condición se define una sola vez aquí y la usan los agregados y los Domain Services existentes; los motivos
son los mismos textos que el dominio ya comunicaba. Solo contiene reglas aceptadas en el BRD/U2/U3; las reglas
ilustrativas del paquete CSV no forman parte del dominio.

Candidatos de evaluación:
- SituacionContratacion: Contrato y la evidencia del anticipo leída de EstadoCuenta.
- ImpactoModificacion (valores.py): resultado de EvaluarImpactoCambio.
- AnticipacionSolicitud (valores.py) o cualquier objeto con `dias_naturales`.
- SituacionTemporalSolicitud: estado del Evento, elegibilidad obtenida y anticipación al momento de evaluar.
- SituacionContinuidadSolicitud: lo que combina EvaluarRegularizacionDeSolicitudes.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional

from .especificacion import Especificacion
from .valores import AnticipacionSolicitud, CondicionTemporal, EstadoContrato

DIAS_MINIMOS_SERVICIO_ADICIONAL = 5   # SE-004
DIAS_SIN_CARGO_TARDIO = 7            # BN-003


# ======================================================================= candidatos
@dataclass(frozen=True)
class SituacionContratacion:
    contrato: Any                       # domain.contrato.Contrato
    evidencia: Any                      # domain.contrato.EvidenciaAnticipo


@dataclass(frozen=True)
class SituacionTemporalSolicitud:
    evento_iniciado: bool
    elegibilidad_obtenida: bool = False
    anticipacion: Optional[AnticipacionSolicitud] = None    # desde el momento de la evaluación hasta el evento

    @property
    def dias_naturales(self) -> int:
        return self.anticipacion.dias_naturales


@dataclass(frozen=True)
class SituacionContinuidadSolicitud:
    saldo_vencido_sin_regularizar: bool
    evento_cancelado: bool
    condicion_temporal: CondicionTemporal


# ======================================================================= contratación (BN-009, CA-019)
class ContratoEstaFirmado(Especificacion):
    descripcion = "contrato firmado"

    def es_satisfecha_por(self, c: SituacionContratacion) -> bool:
        return c.contrato.estado == EstadoContrato.FIRMADO


class PoliticaNoReembolsoComunicada(Especificacion):
    descripcion = "política de no reembolso comunicada"

    def es_satisfecha_por(self, c: SituacionContratacion) -> bool:
        return c.contrato.politica.comunicada()


class AnticipoVerificado(Especificacion):
    descripcion = "anticipo del 30 % registrado y verificado"

    def es_satisfecha_por(self, c: SituacionContratacion) -> bool:
        e = c.evidencia
        return e.registrado and e.verificado and e.importe_correcto


CONTRATACION_CONFIRMABLE = ContratoEstaFirmado() & PoliticaNoReembolsoComunicada() & AnticipoVerificado()


# ======================================================================= impacto de una modificación
class AfectaServicios(Especificacion):
    descripcion = "afecta los servicios"

    def es_satisfecha_por(self, impacto) -> bool:
        return impacto.afecta_servicios


class AfectaCostos(Especificacion):
    descripcion = "afecta los costos"

    def es_satisfecha_por(self, impacto) -> bool:
        return impacto.afecta_costos


class AfectaCondiciones(Especificacion):
    descripcion = "afecta las condiciones"

    def es_satisfecha_por(self, impacto) -> bool:
        return impacto.afecta_condiciones


# BN-003: un cambio requiere aprobación del Cliente (ruta B) si afecta costos o condiciones acordadas.
CAMBIO_REQUIERE_APROBACION_CLIENTE = AfectaCostos() | AfectaCondiciones()

# Restricciones del BRD y SE-001: una alternativa de sustitución requiere aprobación si modifica los servicios, los
# costos o las condiciones (ImpactoModificacion.tiene_impacto). Es una regla distinta de la del cambio.
MODIFICACION_CON_IMPACTO = AfectaServicios() | AfectaCostos() | AfectaCondiciones()


# ======================================================================= anticipación y condición temporal
class AnticipacionMinima(Especificacion):
    """Al menos `dias` días naturales entre la fecha de referencia y la fecha del evento."""

    def __init__(self, dias: int, motivo: str = ""):
        self.dias = dias
        self.descripcion = motivo or f"anticipación mínima de {dias} días naturales"

    def es_satisfecha_por(self, candidato) -> bool:
        return candidato.dias_naturales >= self.dias


class EventoNoIniciado(Especificacion):
    def __init__(self, motivo: str):
        self.descripcion = motivo

    def es_satisfecha_por(self, candidato) -> bool:
        return not candidato.evento_iniciado


class EventoNoCancelado(Especificacion):
    def __init__(self, motivo: str):
        self.descripcion = motivo

    def es_satisfecha_por(self, candidato) -> bool:
        return not candidato.evento_cancelado


class ElegibilidadObtenida(Especificacion):
    """SE-004, CA-080: la elegibilidad obtenida dentro del plazo se conserva aunque después resten menos días."""
    descripcion = "elegibilidad obtenida dentro del plazo"

    def es_satisfecha_por(self, candidato) -> bool:
        return candidato.elegibilidad_obtenida


# BN-003, CA-061, CA-062: con menos de siete días naturales el cambio queda sujeto al cargo por cambio tardío.
# Solo determina el cargo; la viabilidad con los proveedores se evalúa siempre.
CAMBIO_SIN_CARGO_TARDIO = AnticipacionMinima(DIAS_SIN_CARGO_TARDIO)
CAMBIO_CON_CARGO_TARDIO = ~CAMBIO_SIN_CARGO_TARDIO

# CA-039: una solicitud de cambio solo se tramita antes del inicio del evento.
SOLICITUD_CAMBIO_EN_PLAZO = EventoNoIniciado("El evento ya inició (CA-039).")

# SE-004, CA-077, CA-080, CA-083: evento no iniciado y, salvo que la elegibilidad ya se haya obtenido dentro del
# plazo, al menos cinco días naturales hasta el evento contados desde el momento de la evaluación (al registrar o
# al retomar una solicitud detenida antes de obtenerla).
SERVICIO_ADICIONAL_EN_PLAZO = (
    EventoNoIniciado("Condición temporal: el evento ya inició.")
    & (ElegibilidadObtenida() | AnticipacionMinima(DIAS_MINIMOS_SERVICIO_ADICIONAL)).con_motivo(
        "Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).")
)


# ======================================================================= continuidad de una solicitud (O-01)
class CondicionTemporalCumplida(Especificacion):
    """La condición temporal que informa la propia solicitud (cada tipo calcula la suya, hallazgo H-04)."""
    descripcion = "condición temporal de la solicitud"

    def es_satisfecha_por(self, s: SituacionContinuidadSolicitud) -> bool:
        return s.condicion_temporal.cumple

    def motivo(self, s: SituacionContinuidadSolicitud) -> str:
        return s.condicion_temporal.motivo


class SinSaldoVencido(Especificacion):
    descripcion = "Saldo vencido sin regularizar (CA-066, CA-072)."

    def es_satisfecha_por(self, s: SituacionContinuidadSolicitud) -> bool:
        return not s.saldo_vencido_sin_regularizar


# O-01 (SE-004, SE-006, SE-007, BN-005): el orden de las partes es el orden de los motivos; se usa el primero.
# 1) Evento cancelado; 2) condición temporal (evento iniciado y, en servicios adicionales, plazo de cinco días);
# 3) saldo vencido sin regularizar, que detiene la solicitud en lugar de cerrarla.
SOLICITUD_PUEDE_CONTINUAR = (
    EventoNoCancelado("El evento fue cancelado; la solicitud no puede retomarse (SE-006).")
    & CondicionTemporalCumplida()
    & SinSaldoVencido()
)
