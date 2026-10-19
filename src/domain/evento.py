"""Aggregate Evento (raíz) con ServicioContratado y SolicitudCancelacion."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
from .base import AggregateRoot
from .valores import (DatosEvento, EstadoEvento, EstadoSolicitudCancelacion, MotivoCancelacionEvento,
                      OrigenCancelacion, CondicionesServicio, ErrorDominio, Importe)
from .servicios_dominio import ConfiguracionComparable
from .eventos_dominio import EventoIniciado, EventoCancelado, EventoFinalizado


@dataclass
class ServicioContratado:
    servicio_contratado_id: str
    servicio: str
    proveedor_id: Optional[str]
    condiciones: CondicionesServicio


@dataclass(frozen=True)
class RevisionAdministrativa:
    """Atributo de Evento: resultado de la revisión de contrato y pagos tras la cancelación (CA-089 a CA-091).
    Los importes los obtiene la aplicación de EstadoCuenta; Evento no consulta otras raíces."""
    resultado: str
    pagos_realizados: Importe
    saldo_pendiente: Importe
    politica_incluida: bool
    constancia_no_reembolso: bool
    fecha: datetime


@dataclass
class SolicitudCancelacion:
    fecha: datetime
    motivo: str
    estado: EstadoSolicitudCancelacion = EstadoSolicitudCancelacion.REGISTRADA


class Evento(AggregateRoot):
    def __init__(self, evento_id: str, cliente_id: str, datos: DatosEvento, servicios_solicitados: List[str]):
        super().__init__(evento_id)
        self.cliente_id, self.datos = cliente_id, datos
        self.servicios_solicitados = list(servicios_solicitados)
        self.estado = EstadoEvento.EN_GESTION
        self.servicios: Dict[str, ServicioContratado] = {}
        self.solicitudes_cancelacion: List[SolicitudCancelacion] = []
        self.motivo_cancelacion: Optional[MotivoCancelacionEvento] = None
        self.revision_administrativa: Optional[RevisionAdministrativa] = None
        self.fecha_finalizacion: Optional[datetime] = None
        self.fecha_inicio: Optional[datetime] = None
        self._operaciones_aplicadas: Set[str] = set()   # idempotencia de las reacciones

    # -- reacciones de la contratación
    def confirmar_contratacion(self, servicios: List[ServicioContratado]) -> None:
        if self.estado == EstadoEvento.EN_ORGANIZACION:
            return
        if self.estado != EstadoEvento.EN_GESTION:
            raise ErrorDominio(f"No puede pasar a En organización desde {self.estado.value}.")
        self.estado = EstadoEvento.EN_ORGANIZACION
        for s in servicios:
            self.servicios[s.servicio_contratado_id] = s

    def cerrar_sin_contratacion(self) -> None:
        """Nunca Cancelado (CA-021)."""
        if self.estado == EstadoEvento.CERRADO_SIN_CONTRATACION:
            return
        if self.estado != EstadoEvento.EN_GESTION:
            raise ErrorDominio(f"No puede cerrarse sin contratación desde {self.estado.value}.")
        self.estado = EstadoEvento.CERRADO_SIN_CONTRATACION

    # -- configuración operativa (solo por reacciones a confirmaciones, BN-006)
    def _no_iniciado(self, confirmado_en: Optional[datetime] = None) -> None:
        """La configuración cambia mientras el Evento está En organización. Una operación confirmada antes del
        inicio se aplica aunque su reacción llegue después de iniciado el Evento: lo confirmado no se pierde (BN-006).
        Si el Evento se canceló antes de aplicarla, la operación no se aplica y la configuración no cambia; la solicitud
        conserva su confirmación y el rechazo deja registrado el motivo en el registro del Outbox, que queda en
        «Revisión» (BN-008)."""
        if self.estado == EstadoEvento.EN_ORGANIZACION:
            return
        if self.estado == EstadoEvento.CANCELADO:
            raise ErrorDominio("Operación confirmada no aplicada: el Evento fue cancelado antes de aplicarla. "
                               "La solicitud conserva su confirmación (BN-008).")
        if (self.estado == EstadoEvento.EN_EJECUCION and confirmado_en is not None
                and self.fecha_inicio is not None and confirmado_en < self.fecha_inicio):
            return
        raise ErrorDominio("La configuración solo cambia mientras el Evento está En organización.")

    def configuracion_vigente(self) -> ConfiguracionComparable:
        """Última configuración confirmada (GL-035) en la forma que compara EvaluarImpactoCambio."""
        return ConfiguracionComparable(self.datos, frozenset((k, s.condiciones) for k, s in self.servicios.items()))

    def aplicar_cambio_confirmado(self, solicitud_id: str, nuevos_datos: Optional[DatosEvento],
                                  condiciones: Optional[dict] = None, confirmado_en: Optional[datetime] = None) -> None:
        """Reacción a CambioConfirmado: aplica los datos y las condiciones aprobados una sola vez (BN-006, CA-041)."""
        if solicitud_id in self._operaciones_aplicadas:
            return
        self._no_iniciado(confirmado_en)
        condiciones = condiciones or {}
        desconocidos = set(condiciones) - set(self.servicios)
        if desconocidos:
            raise ErrorDominio(f"El cambio refiere servicios que no están contratados: {sorted(desconocidos)}.")
        if nuevos_datos:
            self.datos = nuevos_datos
        for sid, cond in condiciones.items():
            self.servicios[sid].condiciones = cond
        self._operaciones_aplicadas.add(solicitud_id)

    def incorporar_servicio_adicional(self, solicitud_id: str, servicio: ServicioContratado,
                                      confirmado_en: Optional[datetime] = None) -> None:
        if solicitud_id in self._operaciones_aplicadas:
            return
        self._no_iniciado(confirmado_en)
        self.servicios[servicio.servicio_contratado_id] = servicio
        self._operaciones_aplicadas.add(solicitud_id)

    def reasignar_proveedor(self, sustitucion_id: str, servicio_contratado_id: str, proveedor_id: str,
                            confirmado_en: Optional[datetime] = None) -> None:
        if sustitucion_id in self._operaciones_aplicadas:
            return
        self._no_iniciado(confirmado_en)
        self.servicios[servicio_contratado_id].proveedor_id = proveedor_id
        self._operaciones_aplicadas.add(sustitucion_id)

    # -- cancelación y cierre
    def solicitar_cancelacion(self, motivo: str, ahora: datetime, contratacion_confirmada: bool) -> bool:
        """Devuelve True si se canceló. BN-008, CA-084, CA-087, CA-088."""
        if not contratacion_confirmada:
            raise ErrorDominio("La cancelación solo procede con la contratación confirmada (CA-084).")
        sc = SolicitudCancelacion(ahora, motivo)
        self.solicitudes_cancelacion.append(sc)
        if self.estado == EstadoEvento.EN_EJECUCION:
            sc.estado = EstadoSolicitudCancelacion.RECHAZADA_INICIO_EVENTO
            return False
        sc.estado = EstadoSolicitudCancelacion.PROCEDENTE
        self._cancelar(MotivoCancelacionEvento(OrigenCancelacion.SOLICITUD_CLIENTE, motivo, ahora, "Coordinador"))
        return True

    def cancelar_por_falta_de_regularizacion(self, motivo: str, registrado_por: str, ahora: datetime,
                                             no_regularizado_verificado: bool) -> bool:
        """Registro formal del Coordinador (BN-005, BN-008, CA-027). Nunca se ejecuta de forma automática.
        Devuelve False si ya estaba cancelado por esta causa (sin cambios ni nuevo Domain Event)."""
        if (self.estado == EstadoEvento.CANCELADO and self.motivo_cancelacion
                and self.motivo_cancelacion.origen == OrigenCancelacion.FALTA_REGULARIZACION):
            return False
        if not no_regularizado_verificado:
            raise ErrorDominio("Administración no ha verificado el vencimiento del plazo de regularización.")
        if not motivo:
            raise ErrorDominio("El Coordinador debe indicar el motivo de la cancelación (BN-005).")
        self._cancelar(MotivoCancelacionEvento(OrigenCancelacion.FALTA_REGULARIZACION, motivo, ahora, registrado_por))
        return True

    def _cancelar(self, motivo: MotivoCancelacionEvento) -> None:
        if self.estado != EstadoEvento.EN_ORGANIZACION:
            raise ErrorDominio(f"No puede cancelarse un evento {self.estado.value}.")
        self.estado, self.motivo_cancelacion = EstadoEvento.CANCELADO, motivo
        self._registrar(EventoCancelado(self.id, motivo.fecha, origen=motivo.origen.value))

    def registrar_revision_administrativa(self, revision: RevisionAdministrativa) -> None:
        if self.estado != EstadoEvento.CANCELADO:
            raise ErrorDominio("La revisión administrativa aplica a un evento cancelado (CA-091).")
        if not revision.constancia_no_reembolso:
            raise ErrorDominio("La revisión debe dejar constancia de la política de no reembolso (CA-091).")
        self.revision_administrativa = revision

    def iniciar(self, ahora: datetime) -> None:
        if self.estado != EstadoEvento.EN_ORGANIZACION:
            raise ErrorDominio(f"No puede iniciar un evento {self.estado.value}.")
        self.estado, self.fecha_inicio = EstadoEvento.EN_EJECUCION, ahora
        self._registrar(EventoIniciado(self.id, ahora))

    def finalizar(self, fecha: datetime) -> None:
        if self.estado == EstadoEvento.CANCELADO:
            raise ErrorDominio("Un evento cancelado no puede registrarse como Finalizado (CA-095).")
        if self.estado != EstadoEvento.EN_EJECUCION:
            raise ErrorDominio("Solo puede finalizarse un evento que se realizó (CA-094).")
        self.estado, self.fecha_finalizacion = EstadoEvento.FINALIZADO, fecha
        self._registrar(EventoFinalizado(self.id, fecha))

    @property
    def cancelado(self) -> bool:
        return self.estado == EstadoEvento.CANCELADO

    @property
    def iniciado(self) -> bool:
        return self.estado in (EstadoEvento.EN_EJECUCION, EstadoEvento.FINALIZADO)
