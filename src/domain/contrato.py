"""Aggregate Contrato (raíz) con la entidad interna AnexoContrato."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional
from .base import AggregateRoot
from .valores import CondicionesContractuales, PoliticaNoReembolso, EstadoContrato, ErrorDominio, TipoSolicitud
from .eventos_dominio import ContratoFirmado, ContratacionConfirmada, ProcesoContratacionCerrado, AnexoContratoRegistrado
from .especificaciones import CONTRATACION_CONFIRMABLE, SituacionContratacion
from .maquina_estados import MaquinaEstados, Transicion

HORAS_PAGO_TRAS_CONTACTO = 24            # BN-009: plazo del Cliente para efectuar el anticipo desde el contacto
MENSAJE_SIN_SEGUIMIENTO = "Debe existir un seguimiento del anticipo antes de cerrar la contratación (CA-020)."


class AccionContrato(Enum):
    """Acciones que cambian el estado del Contrato; corresponden a sus métodos existentes."""
    FIRMAR = "firmar"
    CONFIRMAR_CONTRATACION = "confirmar_contratacion"
    CERRAR_SIN_CONFIRMAR = "cerrar_sin_confirmar"


_EC, _AC = EstadoContrato, AccionContrato

# Mapa de dominio U3 «Estados de Contrato» (US-008, CA-015–CA-021, GL-009, SE-010):
# En preparación → Firmado → Contratación confirmada | Cerrado sin confirmar.
# registrar_seguimiento_anticipo, registrar_anexo y registrar_comunicacion_politica no cambian el estado: no están
# en la tabla y conservan sus propias validaciones.
MAQUINA_CONTRATO = MaquinaEstados(
    estados=EstadoContrato,
    transiciones=(
        Transicion(_EC.EN_PREPARACION, _AC.FIRMAR, _EC.FIRMADO),                                # US-008, CA-017, BN-009
        Transicion(_EC.FIRMADO, _AC.CONFIRMAR_CONTRATACION, _EC.CONTRATACION_CONFIRMADA),      # CA-019, GL-009
        Transicion(_EC.FIRMADO, _AC.CERRAR_SIN_CONFIRMAR, _EC.CERRADO_SIN_CONFIRMAR),          # CA-020, CA-021, SE-010
    ),
    # Confirmar una contratación ya confirmada se acepta sin efecto: devuelve [] y no emite otro Domain Event.
    repeticiones_idempotentes=((_EC.CONTRATACION_CONFIRMADA, _AC.CONFIRMAR_CONTRATACION),),
    # Mensajes de rechazo existentes del agregado, sin cambios. confirmar_contratacion no usa mensaje de rechazo:
    # fuera de Firmado devuelve los pendientes de la Specification CONTRATACION_CONFIRMABLE.
    mensajes_rechazo={
        _AC.FIRMAR: lambda o: "Solo un contrato En preparación puede firmarse.",
        _AC.CERRAR_SIN_CONFIRMAR: lambda o: MENSAJE_SIN_SEGUIMIENTO,
    },
    nombre="Contrato",
)


@dataclass
class AnexoContrato:
    anexo_id: str
    tipo_origen: TipoSolicitud
    origen_id: str
    descripcion: str
    fecha: datetime


@dataclass(frozen=True)
class EvidenciaAnticipo:
    """Lectura de EstadoCuenta que la aplicación entrega a Contrato; Contrato no modifica otra raíz."""
    registrado: bool
    verificado: bool
    importe_correcto: bool


class Contrato(AggregateRoot):
    def __init__(self, contrato_id: str, evento_id: str, propuesta_id: str, version_aceptada_id: str,
                 condiciones: CondicionesContractuales, politica: PoliticaNoReembolso):
        super().__init__(contrato_id)
        if not politica.incluida:
            raise ErrorDominio("La política de no reembolso debe estar incluida en el contrato (CA-016).")
        self.evento_id, self.propuesta_id, self.version_aceptada_id = evento_id, propuesta_id, version_aceptada_id
        self.condiciones, self.politica = condiciones, politica
        self.estado = EstadoContrato.EN_PREPARACION
        self.fecha_firma: Optional[datetime] = None
        self.seguimientos_anticipo: List[tuple] = []
        self.anexos: List[AnexoContrato] = []

    def registrar_comunicacion_politica(self, fecha: datetime) -> None:
        self.politica = PoliticaNoReembolso(True, fecha)

    # -- State Machine (Etapa E3B): valida el par estado-acción; el agregado asigna el destino
    def _transitar(self, accion: AccionContrato) -> EstadoContrato:
        """Destino permitido por MAQUINA_CONTRATO o TransicionNoPermitida (ErrorDominio) con el mensaje existente."""
        return MAQUINA_CONTRATO.transitar(self.estado, accion)

    def firmar(self, fecha: datetime) -> None:
        self.estado, self.fecha_firma = self._transitar(AccionContrato.FIRMAR), fecha
        self._registrar(ContratoFirmado(self.id, fecha, evento_ref=self.evento_id))

    def confirmar_contratacion(self, evidencia: EvidenciaAnticipo, ahora: datetime) -> List[str]:
        """Devuelve requisitos pendientes; idempotente si ya estaba confirmada (CA-019, GL-009).
        1) Repetición idempotente declarada en MAQUINA_CONTRATO: devuelve [] sin evaluar nada ni emitir eventos.
        2) La Specification CONTRATACION_CONFIRMABLE (firmado AND política comunicada AND anticipo verificado)
           decide los pendientes y sus mensajes; con pendientes se devuelven sin excepción ni cambios.
        3) Sin pendientes, la máquina da el destino y se registra un único ContratacionConfirmada."""
        if MAQUINA_CONTRATO.es_repeticion(self.estado, AccionContrato.CONFIRMAR_CONTRATACION):
            return []
        pendientes = CONTRATACION_CONFIRMABLE.motivos_incumplimiento(SituacionContratacion(self, evidencia))
        if not pendientes:
            self.estado = self._transitar(AccionContrato.CONFIRMAR_CONTRATACION)
            self._registrar(ContratacionConfirmada(self.id, ahora, evento_ref=self.evento_id))
        return pendientes

    def registrar_seguimiento_anticipo(self, fecha: datetime, resultado: str, plazo_vencido: bool) -> None:
        if self.estado != EstadoContrato.FIRMADO:
            raise ErrorDominio("El seguimiento del anticipo solo aplica a un contrato firmado.")
        if not plazo_vencido:
            raise ErrorDominio("El plazo de tres días hábiles para el anticipo no ha vencido (CA-020).")
        self.seguimientos_anticipo.append((fecha, resultado))

    def limite_pago_anticipo(self) -> Optional[datetime]:
        """24 horas naturales desde el contacto del Coordinador; None si todavía no hubo contacto (BN-009, CA-020)."""
        if not self.seguimientos_anticipo:
            return None
        return self.seguimientos_anticipo[0][0] + timedelta(hours=HORAS_PAGO_TRAS_CONTACTO)

    def cerrar_sin_confirmar(self, ahora: datetime, anticipo_efectuado_en_plazo: bool = False) -> None:
        """CA-021. Solo procede cuando vencieron las 24 horas naturales del Cliente y no efectuó el anticipo dentro de
        ellas; un pago efectuado a tiempo que Administración aún no registra o verifica no cierra la contratación.
        No modifica Evento: lo hace la reacción a ProcesoContratacionCerrado.
        Todas las validaciones ocurren antes de modificar el agregado, en el orden de siempre: estado (MAQUINA_CONTRATO)
        y seguimiento, con el mismo mensaje; 24 horas desde el primer contacto; anticipo efectuado dentro del plazo."""
        MAQUINA_CONTRATO.validar(self.estado, AccionContrato.CERRAR_SIN_CONFIRMAR)
        if not self.seguimientos_anticipo:
            raise ErrorDominio(MENSAJE_SIN_SEGUIMIENTO)
        if ahora <= self.limite_pago_anticipo():
            raise ErrorDominio("El Cliente todavía dispone de 24 horas naturales desde el contacto para efectuar el anticipo (CA-021).")
        if anticipo_efectuado_en_plazo:
            raise ErrorDominio("El Cliente efectuó el anticipo dentro del plazo; queda pendiente de registro o verificación (CA-021).")
        self.estado = self._transitar(AccionContrato.CERRAR_SIN_CONFIRMAR)
        self._registrar(ProcesoContratacionCerrado(self.id, ahora, evento_ref=self.evento_id))

    def registrar_anexo(self, anexo_id: str, tipo: TipoSolicitud, origen_id: str, descripcion: str, ahora: datetime) -> AnexoContrato:
        if self.estado != EstadoContrato.CONTRATACION_CONFIRMADA:
            raise ErrorDominio("Solo se registran anexos sobre una contratación confirmada.")
        if any(a.origen_id == origen_id for a in self.anexos):
            raise ErrorDominio("La operación ya tiene un anexo registrado.")
        a = AnexoContrato(anexo_id, tipo, origen_id, descripcion, ahora)
        self.anexos.append(a)
        self._registrar(AnexoContratoRegistrado(self.id, ahora, anexo_id=anexo_id, tipo_origen=tipo.value, origen_id=origen_id))
        return a
