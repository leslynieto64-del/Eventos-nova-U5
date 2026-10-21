"""Domain Services: EvaluarImpactoCambio y EvaluarRegularizacionDeSolicitudes.
No consultan repositorios, no notifican y no cambian estados."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from .valores import ImpactoModificacion, CondicionTemporal, DatosEvento, Importe
from .especificaciones import SOLICITUD_PUEDE_CONTINUAR, SituacionContinuidadSolicitud, SinSaldoVencido


@dataclass(frozen=True)
class ConfiguracionComparable:
    """Lo que se compara: datos del evento, condiciones por servicio contratado e importe adicional."""
    datos: Optional[DatosEvento]
    condiciones: frozenset                 # {(servicioContratadoId, CondicionesServicio)}
    costo_adicional: Importe = Importe(Decimal(0))

    @property
    def servicios(self) -> frozenset:
        return frozenset(sid for sid, _ in self.condiciones)


class EvaluarImpactoCambio:
    """GL-039: compara la configuración vigente del Evento con una modificación propuesta
    (solicitud de cambio o alternativa de sustitución)."""

    def evaluar(self, vigente: ConfiguracionComparable, propuesta: ConfiguracionComparable) -> ImpactoModificacion:
        return ImpactoModificacion(
            afecta_servicios=vigente.servicios != propuesta.servicios,
            afecta_costos=propuesta.costo_adicional.cantidad > 0,
            afecta_condiciones=(vigente.datos != propuesta.datos) or (vigente.condiciones != propuesta.condiciones),
        )


@dataclass(frozen=True)
class SituacionSaldo:
    saldo_vencido_sin_regularizar: bool


@dataclass(frozen=True)
class DecisionRegularizacion:
    puede_continuar: bool
    detener_por_saldo: bool
    motivo: str = ""


class EvaluarRegularizacionDeSolicitudes:
    """Combina saldo (EstadoCuenta), estado del Evento y la condición temporal que informa la solicitud.
    No conoce reglas temporales por tipo de solicitud (hallazgo H-04)."""

    def evaluar(self, saldo: SituacionSaldo, evento_cancelado: bool, condicion: CondicionTemporal) -> DecisionRegularizacion:
        """Specification SolicitudPuedeContinuar; se usa el primer motivo según el orden O-01."""
        fallo = SOLICITUD_PUEDE_CONTINUAR.primer_incumplimiento(
            SituacionContinuidadSolicitud(saldo.saldo_vencido_sin_regularizar, evento_cancelado, condicion))
        if fallo is None:
            return DecisionRegularizacion(True, False)
        return DecisionRegularizacion(False, isinstance(fallo.especificacion, SinSaldoVencido), fallo.motivo)
