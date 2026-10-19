"""CQRS básico (Etapa 6): los Command Handlers delegan en la Service Layer; los Query Handlers solo leen."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from domain.valores import ContenidoPropuesta, EstadoPago, ConceptoPago, EstadoObligacionPago
from .puertos import (IEstadoCuentaRepository, ISolicitudCambioRepository, ISolicitudServicioAdicionalRepository,
                      ISustitucionProveedorRepository)


# ------------------------------------------------------------------ Commands
@dataclass(frozen=True)
class GenerarNuevaVersionPropuestaCommand:
    propuesta_id: str
    modificaciones: ContenidoPropuesta


@dataclass(frozen=True)
class ConfirmarCambioCommand:
    solicitud_id: str


@dataclass(frozen=True)
class DarSeguimientoAnticipoPendienteCommand:
    contrato_id: str
    fecha: datetime
    resultado_contacto: str
    sin_pago_tras_seguimiento: bool


@dataclass(frozen=True)
class RegistrarCancelacionPorFaltaDeRegularizacionCommand:
    evento_id: str
    motivo: str
    coordinador: str
    fecha: datetime


class RegistrarCancelacionPorFaltaDeRegularizacionHandler:
    """Intención explícita del Coordinador; distinta del cierre por anticipo no recibido."""
    def __init__(self, servicio):           # GestionCierreEventoService
        self.servicio = servicio
    def handle(self, cmd: RegistrarCancelacionPorFaltaDeRegularizacionCommand):
        return self.servicio.registrar_cancelacion_por_falta_de_regularizacion(cmd.evento_id, cmd.motivo, cmd.coordinador, cmd.fecha)


class GenerarNuevaVersionPropuestaHandler:
    def __init__(self, servicio):           # GestionPropuestaService
        self.servicio = servicio
    def handle(self, cmd: GenerarNuevaVersionPropuestaCommand, ahora: datetime):
        return self.servicio.generar_nueva_version(cmd.propuesta_id, cmd.modificaciones, ahora)


class ConfirmarCambioHandler:
    def __init__(self, servicio):           # GestionCambiosEventoService
        self.servicio = servicio
    def handle(self, cmd: ConfirmarCambioCommand, ahora: datetime):
        return self.servicio.confirmar_cambio(cmd.solicitud_id, ahora)


class DarSeguimientoAnticipoPendienteHandler:
    def __init__(self, servicio):           # FormalizarContratacionService
        self.servicio = servicio
    def handle(self, cmd: DarSeguimientoAnticipoPendienteCommand):
        return self.servicio.dar_seguimiento_anticipo_pendiente(cmd.contrato_id, cmd.fecha, cmd.resultado_contacto,
                                                                cmd.sin_pago_tras_seguimiento)


# ------------------------------------------------------------------ View Models
@dataclass
class EstadoCuentaResumenViewModel:
    estadoCuentaId: str
    contratoId: str
    anticipo: dict
    pagosRegistrados: List[dict]
    saldoContratoOriginal: dict
    obligacionesAdicionales: List[dict]


@dataclass
class EstadoPagosViewModel:
    eventoId: str
    estadosCuenta: List[EstadoCuentaResumenViewModel] = field(default_factory=list)


@dataclass
class SolicitudPendienteViewModel:
    tipoSolicitud: str
    solicitudId: str
    servicioAfectado: Optional[str]
    estadoActual: str
    accionPendiente: str
    estadoPago: Optional[str]


@dataclass
class SolicitudesPendientesViewModel:
    eventoId: str
    solicitudes: List[SolicitudPendienteViewModel] = field(default_factory=list)


# ------------------------------------------------------------------ Queries
@dataclass(frozen=True)
class ConsultarEstadoPagosQuery:
    eventoId: str


@dataclass(frozen=True)
class ConsultarSolicitudesPendientesQuery:
    eventoId: str


class ConsultarEstadoPagosHandler:
    """No escribe ni usa IUnitOfWork; no presupone un único EstadoCuenta por evento."""
    def __init__(self, estados_cuenta: IEstadoCuentaRepository):
        self.ec = estados_cuenta

    def handle(self, q: ConsultarEstadoPagosQuery) -> EstadoPagosViewModel:
        vm = EstadoPagosViewModel(q.eventoId)
        for ec in self.ec.listar_por_evento_id(q.eventoId):
            def ob(concepto):
                o = next((o for o in ec.obligaciones.values() if o.concepto == concepto), None)
                return {} if o is None else {"importe": str(o.importe.cantidad), "fechaLimite": o.plazo.vence.isoformat() if o.plazo else None, "estado": o.estado.value}
            adicionales = [{"concepto": o.concepto.value, "importe": str(o.importe.cantidad), "plazo": o.plazo.vence.isoformat() if o.plazo else None,
                            "estado": o.estado.value} for o in ec.obligaciones.values()
                           if o.concepto not in (ConceptoPago.ANTICIPO, ConceptoPago.SALDO_CONTRATO_ORIGINAL)]
            pagos = [{"concepto": ec.obligaciones[p.obligacion_id].concepto.value, "importe": str(p.importe.cantidad),
                      "fecha": p.fecha.isoformat(), "estado": p.estado.value,
                      "registradoEn": p.registrado_en.isoformat() if p.registrado_en else None,
                      "verificadoEn": p.verificado_en.isoformat() if p.verificado_en else None} for p in ec.pagos]
            saldo = ob(ConceptoPago.SALDO_CONTRATO_ORIGINAL)
            if ec.resultado_regularizacion:
                saldo["resultadoRegularizacion"] = ec.resultado_regularizacion
            vm.estadosCuenta.append(EstadoCuentaResumenViewModel(ec.id, ec.contrato_id, ob(ConceptoPago.ANTICIPO), pagos,
                                                                 saldo, adicionales))
        return vm


ACCION = {
    "Registrada": "evaluación", "Detenida por saldo vencido": "regularización del saldo", "En evaluación": "evaluación",
    "En búsqueda de proveedor": "evaluación", "En búsqueda de alternativa": "evaluación",
    "Pendiente de aprobación del Cliente": "aprobación", "Pendiente de autorización": "autorización",
    "Pendiente de formalización": "formalización", "Autorizada": "formalización", "Pendiente de pago": "pago pendiente",
}


class ConsultarSolicitudesPendientesHandler:
    """Solo lectura. Los datos financieros del contrato permanecen en EstadoPagosViewModel (H-06)."""
    def __init__(self, cambios: ISolicitudCambioRepository, adicionales: ISolicitudServicioAdicionalRepository,
                 sustituciones: ISustitucionProveedorRepository, estados_cuenta: IEstadoCuentaRepository):
        self.cambios, self.adicionales, self.sustituciones, self.ec = cambios, adicionales, sustituciones, estados_cuenta

    def _estado_pago(self, s) -> Optional[str]:
        if not s.obligacion_pago_id:
            return None
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        return ec.obligaciones[s.obligacion_pago_id].estado.value

    def handle(self, q: ConsultarSolicitudesPendientesQuery) -> SolicitudesPendientesViewModel:
        vm = SolicitudesPendientesViewModel(q.eventoId)
        for tipo, repo, servicio in (("cambio", self.cambios, lambda s: None),
                                     ("servicio adicional", self.adicionales, lambda s: s.servicio),
                                     ("sustitución de proveedor", self.sustituciones, lambda s: s.servicio_contratado_id)):
            for s in repo.listar_pendientes_por_evento_id(q.eventoId):
                vm.solicitudes.append(SolicitudPendienteViewModel(tipo, s.id, servicio(s), s.estado.value,
                                                                  ACCION.get(s.estado.value, "seguimiento"), self._estado_pago(s)))
        return vm
