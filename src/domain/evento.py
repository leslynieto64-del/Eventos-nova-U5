"""Aggregate Evento (raíz) con ServicioContratado y SolicitudCancelacion."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from .base import AggregateRoot
from .valores import (DatosEvento, EstadoEvento, EstadoSolicitudCancelacion, MotivoCancelacionEvento,
                      OrigenCancelacion, CondicionesServicio, ErrorDominio, Importe, EstadoServicioContratado)
from .servicios_dominio import ConfiguracionComparable
from .eventos_dominio import EventoIniciado, EventoCancelado, EventoFinalizado
from .maquina_estados import MaquinaEstados, Transicion


class AccionEvento(Enum):
    """Acciones que cambian el estado del Evento; corresponden a sus métodos existentes."""
    CONFIRMAR_CONTRATACION = "confirmar_contratacion"
    CERRAR_SIN_CONTRATACION = "cerrar_sin_contratacion"
    CANCELAR = "cancelar"                  # solicitar_cancelacion y cancelar_por_falta_de_regularizacion
    INICIAR = "iniciar"
    FINALIZAR = "finalizar"


_EE, _AE = EstadoEvento, AccionEvento

# GL-033 (mapa de dominio): En gestión → En organización | Cerrado sin contratación;
# En organización → En ejecución | Cancelado; En ejecución → Finalizado.
MAQUINA_EVENTO = MaquinaEstados(
    estados=EstadoEvento,
    transiciones=(
        Transicion(_EE.EN_GESTION, _AE.CONFIRMAR_CONTRATACION, _EE.EN_ORGANIZACION),      # reacción a ContratacionConfirmada
        Transicion(_EE.EN_GESTION, _AE.CERRAR_SIN_CONTRATACION, _EE.CERRADO_SIN_CONTRATACION),  # reacción a ProcesoContratacionCerrado (CA-021)
        Transicion(_EE.EN_ORGANIZACION, _AE.CANCELAR, _EE.CANCELADO),                     # BN-008, CA-087, CA-027
        Transicion(_EE.EN_ORGANIZACION, _AE.INICIAR, _EE.EN_EJECUCION),
        Transicion(_EE.EN_EJECUCION, _AE.FINALIZAR, _EE.FINALIZADO),                      # BN-010, CA-094
    ),
    # Idempotencia de las reacciones: repetirlas en el estado que ya produjeron no tiene efecto.
    repeticiones_idempotentes=(
        (_EE.EN_ORGANIZACION, _AE.CONFIRMAR_CONTRATACION),
        (_EE.CERRADO_SIN_CONTRATACION, _AE.CERRAR_SIN_CONTRATACION),
    ),
    # Mensajes de rechazo existentes del agregado, sin cambios.
    mensajes_rechazo={
        _AE.CONFIRMAR_CONTRATACION: lambda o: f"No puede pasar a En organización desde {o.value}.",
        _AE.CERRAR_SIN_CONTRATACION: lambda o: f"No puede cerrarse sin contratación desde {o.value}.",
        _AE.CANCELAR: lambda o: f"No puede cancelarse un evento {o.value}.",
        _AE.INICIAR: lambda o: f"No puede iniciar un evento {o.value}.",
        _AE.FINALIZAR: lambda o: ("Un evento cancelado no puede registrarse como Finalizado (CA-095)."
                                  if o == _EE.CANCELADO else "Solo puede finalizarse un evento que se realizó (CA-094)."),
    },
    nombre="Evento",
)


@dataclass
class ServicioContratado:
    servicio_contratado_id: str
    servicio: str
    proveedor_id: Optional[str]
    condiciones: CondicionesServicio
    # E3G: si no se indica, un servicio sin proveedor nace «Sin proveedor asignado» y uno con proveedor ya confirmado
    # (servicio adicional o reemplazo confirmados) nace «Confirmado por el proveedor».
    estado: Optional[EstadoServicioContratado] = None

    def __post_init__(self):
        if self.estado is None:
            self.estado = (EstadoServicioContratado.CONFIRMADO if self.proveedor_id
                           else EstadoServicioContratado.SIN_PROVEEDOR)


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

    # -- State Machine (Etapa E3A): valida el par estado-acción; el agregado asigna el destino
    def _transitar(self, accion: AccionEvento) -> EstadoEvento:
        """Destino permitido por MAQUINA_EVENTO o TransicionNoPermitida (ErrorDominio) con el mensaje existente."""
        return MAQUINA_EVENTO.transitar(self.estado, accion)

    # -- reacciones de la contratación
    def confirmar_contratacion(self, servicios: List[ServicioContratado]) -> None:
        if MAQUINA_EVENTO.es_repeticion(self.estado, AccionEvento.CONFIRMAR_CONTRATACION):
            return                                          # idempotente: no vuelve a incorporar servicios
        self.estado = self._transitar(AccionEvento.CONFIRMAR_CONTRATACION)
        for s in servicios:
            self.servicios[s.servicio_contratado_id] = s

    def cerrar_sin_contratacion(self) -> None:
        """Nunca Cancelado (CA-021)."""
        if MAQUINA_EVENTO.es_repeticion(self.estado, AccionEvento.CERRAR_SIN_CONTRATACION):
            return
        self.estado = self._transitar(AccionEvento.CERRAR_SIN_CONTRATACION)

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
        sc = self.servicios[servicio_contratado_id]
        sc.proveedor_id = proveedor_id
        sc.estado = EstadoServicioContratado.CONFIRMADO     # el reemplazo se confirma con su disponibilidad (SE-001)
        self._operaciones_aplicadas.add(sustitucion_id)

    # -- proveedores de los servicios contratados (E3G: US-013 a US-016; BN-004, BN-009)
    def _servicio(self, servicio_contratado_id: str) -> ServicioContratado:
        sc = self.servicios.get(servicio_contratado_id)
        if sc is None:
            raise ErrorDominio("El servicio contratado no existe en el Evento.")
        return sc

    def _admite_gestion_de_proveedores(self) -> None:
        """Los proveedores se asignan y responden solo con la contratación confirmada y antes del inicio (BN-009)."""
        if self.estado != EstadoEvento.EN_ORGANIZACION:
            raise ErrorDominio(f"Los proveedores solo se gestionan con el Evento En organización; el Evento está "
                               f"{self.estado.value} (BN-009).")

    def asignar_proveedor(self, servicio_contratado_id: str, proveedor_id: str) -> ServicioContratado:
        """CA-031, CA-032: relaciona al proveedor con el servicio; queda pendiente de que el proveedor confirme su
        disponibilidad. No modifica la configuración vigente (servicios y condiciones acordadas)."""
        self._admite_gestion_de_proveedores()
        sc = self._servicio(servicio_contratado_id)
        if not proveedor_id:
            raise ErrorDominio("Debe indicarse el proveedor que se asigna al servicio.")
        if sc.estado != EstadoServicioContratado.SIN_PROVEEDOR:
            raise ErrorDominio(f"El servicio ya tiene proveedor asignado ({sc.estado.value}); un cambio de proveedor "
                               "se gestiona como sustitución (SE-001).")
        sc.proveedor_id, sc.estado = proveedor_id, EstadoServicioContratado.PENDIENTE_CONFIRMACION
        return sc

    def registrar_respuesta_proveedor(self, servicio_contratado_id: str, proveedor_id: str, disponible: bool) -> ServicioContratado:
        """CA-035, CA-036: solo el proveedor asignado responde, mientras el servicio espera su confirmación. Si no está
        disponible, el servicio queda marcado y conserva a ese proveedor como original de la sustitución (SE-001)."""
        self._admite_gestion_de_proveedores()
        sc = self._servicio(servicio_contratado_id)
        if sc.proveedor_id != proveedor_id:
            raise ErrorDominio("El proveedor no está asignado a este servicio.")
        if sc.estado != EstadoServicioContratado.PENDIENTE_CONFIRMACION:
            raise ErrorDominio(f"El servicio no espera la respuesta del proveedor ({sc.estado.value}).")
        sc.estado = (EstadoServicioContratado.CONFIRMADO if disponible
                     else EstadoServicioContratado.PROVEEDOR_NO_DISPONIBLE)
        return sc

    # -- cancelación y cierre
    def solicitar_cancelacion(self, motivo: str, ahora: datetime, contratacion_confirmada: bool) -> bool:
        """Devuelve True si se canceló. BN-008, CA-084, CA-087, CA-088."""
        if not contratacion_confirmada:
            raise ErrorDominio("La cancelación solo procede con la contratación confirmada (CA-084).")
        if self.iniciado_en(ahora) and self.estado in (EstadoEvento.EN_EJECUCION, EstadoEvento.EN_ORGANIZACION):
            # CA-088: la solicitud se registra como rechazada y el Evento continúa En ejecución (no es una transición).
            # H-08 (GL-032, SE-009): también cuando ya llegó la fecha y hora programadas aunque el inicio todavía no se
            # haya registrado; el Evento no cambia de estado por este rechazo.
            self.solicitudes_cancelacion.append(
                SolicitudCancelacion(ahora, motivo, EstadoSolicitudCancelacion.RECHAZADA_INICIO_EVENTO))
            return False
        # E3A-01: la transición se valida antes de modificar el agregado. Si no está permitida, se rechaza con el
        # mensaje de siempre y no queda ninguna solicitud «Procedente» registrada.
        MAQUINA_EVENTO.validar(self.estado, AccionEvento.CANCELAR)
        self.solicitudes_cancelacion.append(SolicitudCancelacion(ahora, motivo, EstadoSolicitudCancelacion.PROCEDENTE))
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
        if self.estado == EstadoEvento.EN_ORGANIZACION and self.iniciado_en(ahora):
            # H-08 (BN-005, GL-032): «siempre antes del inicio del evento»; si inicia sin registrarse, ya no procede.
            raise ErrorDominio("El evento ya inició según su fecha y hora programadas: la cancelación ya no procede y "
                               "el saldo vencido y los cargos moratorios permanecen registrados como adeudo (BN-005).")
        self._cancelar(MotivoCancelacionEvento(OrigenCancelacion.FALTA_REGULARIZACION, motivo, ahora, registrado_por))
        return True

    def _cancelar(self, motivo: MotivoCancelacionEvento) -> None:
        self.estado, self.motivo_cancelacion = self._transitar(AccionEvento.CANCELAR), motivo
        self._registrar(EventoCancelado(self.id, motivo.fecha, origen=motivo.origen.value))

    def registrar_revision_administrativa(self, revision: RevisionAdministrativa) -> None:
        if self.estado != EstadoEvento.CANCELADO:
            raise ErrorDominio("La revisión administrativa aplica a un evento cancelado (CA-091).")
        if not revision.constancia_no_reembolso:
            raise ErrorDominio("La revisión debe dejar constancia de la política de no reembolso (CA-091).")
        if self.revision_administrativa is not None:
            # BN-008, C-12: la constancia de no reembolso se registra una sola vez por cancelación (Cancelado es final).
            raise ErrorDominio("La constancia de no reembolso de esta cancelación ya fue registrada (BN-008, C-12).")
        self.revision_administrativa = revision

    def iniciar(self, ahora: datetime) -> None:
        """H-08 (GL-032, GL-005, BPMN SP-07 «Fecha y hora de inicio del evento»): el inicio no puede registrarse antes de
        la fecha y hora programadas. El estado se valida primero (mensajes existentes), después la hora."""
        destino = self._transitar(AccionEvento.INICIAR)
        if ahora < self.datos.fecha_hora:
            raise ErrorDominio(f"El evento no puede iniciar antes de su fecha y hora programadas "
                               f"({self.datos.fecha_hora:%d/%m/%Y %H:%M}) (GL-032).")
        self.estado, self.fecha_inicio = destino, ahora
        self._registrar(EventoIniciado(self.id, ahora))

    def finalizar(self, fecha: datetime) -> None:
        """CA-094: solo un evento En ejecución; CA-095: un evento cancelado nunca se registra como Finalizado.
        H-08 (BN-010, GL-033): la finalización es posterior al inicio, por lo que su fecha no puede ser anterior a la
        fecha de inicio registrada. No se valida una hora de término: las fuentes no la definen."""
        destino = self._transitar(AccionEvento.FINALIZAR)
        if self.fecha_inicio is not None and fecha < self.fecha_inicio:
            raise ErrorDominio(f"La fecha de finalización no puede ser anterior al inicio del evento "
                               f"({self.fecha_inicio:%d/%m/%Y %H:%M}) (BN-010, CA-094).")
        self.estado, self.fecha_finalizacion = destino, fecha
        self._registrar(EventoFinalizado(self.id, fecha))

    @property
    def cancelado(self) -> bool:
        return self.estado == EstadoEvento.CANCELADO

    @property
    def iniciado(self) -> bool:
        return self.estado in (EstadoEvento.EN_EJECUCION, EstadoEvento.FINALIZADO)

    def iniciado_en(self, ahora: datetime) -> bool:
        """H-08 (GL-032): «Evento iniciado» es la situación en que el evento ya comenzó según su fecha y hora
        programadas. Es verdadero si el inicio ya se registró o si, con la contratación confirmada (En organización),
        ya llegó esa fecha y hora aunque el registro del inicio esté pendiente. No cambia el estado del Evento."""
        return self.iniciado or (self.estado == EstadoEvento.EN_ORGANIZACION and ahora >= self.datos.fecha_hora)
