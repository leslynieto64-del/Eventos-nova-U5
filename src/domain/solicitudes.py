"""Aggregates SolicitudCambio, SolicitudServicioAdicional y SustitucionProveedor."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from .base import AggregateRoot
from .valores import (DatosEvento, CondicionesServicio, restar_dias_habiles, AnticipacionSolicitud, TarifaCargoTardio, ResultadoViabilidad, ImpactoModificacion, Decision,
                      Importe, MotivoCierreSolicitud, CausaCierreSolicitud, CondicionTemporal, DisponibilidadProveedor,
                      EstadoSolicitudCambio as ESC, EstadoSolicitudServicioAdicional as ESA,
                      EstadoSustitucionProveedor as ESP, ErrorDominio)
from .eventos_dominio import (CambioConfirmado, SolicitudCambioCerradaPorFaltaDePago, SolicitudCambioCerradaPorInicioEvento,
                              CambioSolicitado, ViabilidadCambioEvaluada, ServicioAdicionalConfirmado,
                              ServicioAdicionalCerradoPorFaltaDePago, ServicioAdicionalCerradoPorInicioEvento,
                              ServicioAdicionalSolicitado, AlternativaProveedorEncontrada, ProveedorNoDisponible,
                              SustitucionProveedorConfirmada, SustitucionProveedorCerradaPorInicioEvento,
                              AlternativaRechazadaPorCliente, AlternativaNoAutorizadaPorAdministracion)
from .servicios_dominio import DecisionRegularizacion, ConfiguracionComparable
from .especificaciones import (DIAS_MINIMOS_SERVICIO_ADICIONAL, DIAS_SIN_CARGO_TARDIO,   # noqa: F401  (5 y 7 días)
                               CAMBIO_CON_CARGO_TARDIO, CAMBIO_REQUIERE_APROBACION_CLIENTE, AfectaCostos,
                               SOLICITUD_CAMBIO_EN_PLAZO, SERVICIO_ADICIONAL_EN_PLAZO, SituacionTemporalSolicitud)

_AFECTA_COSTOS = AfectaCostos()


def _condicion_temporal(especificacion, situacion: SituacionTemporalSolicitud) -> CondicionTemporal:
    """Traduce una Specification temporal al Value Object CondicionTemporal (primer motivo o cumplida)."""
    motivo = especificacion.primer_motivo(situacion)
    return CondicionTemporal(True) if motivo is None else CondicionTemporal(False, motivo)


class _SolicitudBase(AggregateRoot):
    FINALES: tuple = ()
    DETENIDA = None
    CERRADA_CANCELACION = None

    def __init__(self, id_, evento_id, contrato_id, estado_cuenta_id):
        super().__init__(id_)
        self.evento_id, self.contrato_id, self.estado_cuenta_id = evento_id, contrato_id, estado_cuenta_id
        self.anexo_id: Optional[str] = None
        self.obligacion_pago_id: Optional[str] = None
        self.motivo_cierre: Optional[MotivoCierreSolicitud] = None
        self._estado_antes_de_detener = None

    @property
    def pendiente(self) -> bool:
        return self.estado not in self.FINALES

    def _cerrar(self, estado, causa: CausaCierreSolicitud, descripcion: str, ahora: datetime) -> None:
        self.estado, self.motivo_cierre = estado, MotivoCierreSolicitud(causa, descripcion, ahora)

    def cerrar_por_cancelacion_evento(self, ahora: datetime) -> bool:
        """BN-008: al cancelarse el Evento, la solicitud que sigue en trámite se cierra con el motivo «Evento cancelado».
        Una solicitud ya confirmada o cerrada no cambia por esta regla."""
        if not self.pendiente:
            return False
        self._cerrar(self.CERRADA_CANCELACION, CausaCierreSolicitud.EVENTO_CANCELADO,
                     CausaCierreSolicitud.EVENTO_CANCELADO.value, ahora)
        return True

    def asociar_anexo(self, anexo_id: str) -> None:
        """Reacción a AnexoContratoRegistrado; idempotente."""
        if self.anexo_id in (None, anexo_id):
            self.anexo_id = anexo_id
        else:
            raise ErrorDominio("La solicitud ya tiene otro anexo asociado.")

    def aplicar_decision_regularizacion(self, d: DecisionRegularizacion, ahora: datetime, estado_no_procede):
        """Usado al registrar y al retomar: la solicitud cambia su propio estado."""
        if d.puede_continuar:
            if self.estado == self.DETENIDA:
                self.estado = self._estado_antes_de_detener
            return True
        if d.detener_por_saldo:
            if self.estado != self.DETENIDA:
                self._estado_antes_de_detener, self.estado = self.estado, self.DETENIDA
            return False
        causa = CausaCierreSolicitud.PLAZO_INSUFICIENTE if d.motivo.startswith('Condición') else CausaCierreSolicitud.EVENTO_CANCELADO
        self._cerrar(estado_no_procede, causa, d.motivo, ahora)
        return False


# ------------------------------------------------------------------ SolicitudCambio
class SolicitudCambio(_SolicitudBase):
    FINALES = (ESC.CONFIRMADA, ESC.NO_PROCEDENTE, ESC.RECHAZADA_CLIENTE, ESC.NO_AUTORIZADA,
               ESC.CERRADA_FALTA_PAGO, ESC.CERRADA_INICIO_EVENTO, ESC.CERRADA_EVENTO_CANCELADO)
    DETENIDA = ESC.DETENIDA_SALDO_VENCIDO
    CERRADA_CANCELACION = ESC.CERRADA_EVENTO_CANCELADO

    def __init__(self, id_, evento_id, contrato_id, estado_cuenta_id, descripcion: str,
                 anticipacion: AnticipacionSolicitud, tarifa: TarifaCargoTardio,
                 datos_propuestos: Optional[DatosEvento] = None, condiciones_propuestas: Optional[dict] = None):
        if datos_propuestos is not None and datos_propuestos.fecha_hora.date() != anticipacion.fecha_evento.date():
            # BRD, fuera del alcance: reprogramar la fecha del evento; la hora del mismo día sí puede cambiarse (GL-019).
            raise ErrorDominio("Reprogramar la fecha del evento no forma parte del alcance; solo puede cambiarse la hora del mismo día.")
        super().__init__(id_, evento_id, contrato_id, estado_cuenta_id)
        self.descripcion, self.anticipacion, self.tarifa = descripcion, anticipacion, tarifa
        # Modificación propuesta: se aplica a Evento solo cuando el cambio se confirma (BN-006).
        self.datos_propuestos = datos_propuestos
        self.condiciones_propuestas = dict(condiciones_propuestas or {})
        self.estado = ESC.REGISTRADA
        self.viabilidad: Optional[ResultadoViabilidad] = None
        self.impacto: Optional[ImpactoModificacion] = None
        self.decision_cliente: Optional[Decision] = None
        self.autorizacion_administracion: Optional[Decision] = None
        self.importes_por_pagar = False
        self._registrar(CambioSolicitado(self.id, anticipacion.fecha_solicitud))

    def condicion_temporal(self, evento_iniciado: bool) -> CondicionTemporal:
        return _condicion_temporal(SOLICITUD_CAMBIO_EN_PLAZO, SituacionTemporalSolicitud(evento_iniciado))

    def configuracion_propuesta(self, vigente: ConfiguracionComparable, costo_adicional: Optional[Importe]) -> ConfiguracionComparable:
        condiciones = dict(vigente.condiciones)
        condiciones.update(self.condiciones_propuestas)
        return ConfiguracionComparable(self.datos_propuestos or vigente.datos, frozenset(condiciones.items()),
                                       costo_adicional or Importe(vigente.costo_adicional.cantidad))

    @property
    def aplica_cargo_tardio(self) -> bool:
        """Con menos de 7 días; solo se cobra si el cambio es viable, aceptado y se realiza (CA-061, CA-062)."""
        return CAMBIO_CON_CARGO_TARDIO.es_satisfecha_por(self.anticipacion)

    def registrar_viabilidad(self, resultado: ResultadoViabilidad, impacto: ImpactoModificacion, ahora: datetime) -> None:
        if self.estado not in (ESC.REGISTRADA, ESC.EN_EVALUACION):
            raise ErrorDominio("La viabilidad solo se evalúa en una solicitud registrada.")
        self.viabilidad, self.impacto = resultado, impacto
        self._registrar(ViabilidadCambioEvaluada(self.id, ahora, viable=resultado.viable))
        if not resultado.viable:                                   # Ruta A
            self._cerrar(ESC.NO_PROCEDENTE, CausaCierreSolicitud.NO_VIABLE, resultado.motivo, ahora)
        elif CAMBIO_REQUIERE_APROBACION_CLIENTE.es_satisfecha_por(impacto):   # Ruta B
            self.estado = ESC.PENDIENTE_APROBACION_CLIENTE
        else:                                                       # Ruta C
            self.estado = ESC.PENDIENTE_FORMALIZACION
        self.importes_por_pagar = resultado.viable and (_AFECTA_COSTOS.es_satisfecha_por(impacto) or self.aplica_cargo_tardio)

    def registrar_decision_cliente(self, d: Decision) -> None:
        if self.estado != ESC.PENDIENTE_APROBACION_CLIENTE:
            raise ErrorDominio("La solicitud no espera la aprobación del Cliente.")
        self.decision_cliente = d
        if d.aprobada:
            self.estado = ESC.PENDIENTE_AUTORIZACION
        else:
            self._cerrar(ESC.RECHAZADA_CLIENTE, CausaCierreSolicitud.RECHAZO_CLIENTE, d.motivo, d.fecha)

    def registrar_autorizacion(self, d: Decision) -> None:
        if self.estado != ESC.PENDIENTE_AUTORIZACION:
            raise ErrorDominio("La autorización requiere la aprobación previa del Cliente (CA-043).")
        self.autorizacion_administracion = d
        if d.aprobada:
            self.estado = ESC.PENDIENTE_FORMALIZACION
        else:
            self._cerrar(ESC.NO_AUTORIZADA, CausaCierreSolicitud.NO_AUTORIZADA, d.motivo, d.fecha)

    def puede_registrar_anexo(self) -> bool:
        return self.estado == ESC.PENDIENTE_FORMALIZACION and self.anexo_id is None

    def registrar_solicitud_pago(self, obligacion_pago_id: str) -> None:
        if self.estado != ESC.PENDIENTE_FORMALIZACION or not self.anexo_id:
            raise ErrorDominio("El pago se solicita con el anexo registrado (CA-068).")
        self.obligacion_pago_id, self.estado = obligacion_pago_id, ESC.PENDIENTE_PAGO

    def confirmar(self, pago_verificado: bool, evento_iniciado: bool, ahora: datetime,
                  evento_cancelado: bool = False) -> List[str]:
        faltan = []
        if evento_iniciado: faltan.append("evento no iniciado")
        if evento_cancelado: faltan.append("evento no cancelado (SE-007)")
        if self.estado not in (ESC.PENDIENTE_FORMALIZACION, ESC.PENDIENTE_PAGO): faltan.append("aprobaciones requeridas")
        if not self.anexo_id: faltan.append("anexo vinculado al contrato original")
        if self.importes_por_pagar and not pago_verificado: faltan.append("pago registrado y verificado")
        if not faltan:
            self.estado = ESC.CONFIRMADA
            self._registrar(CambioConfirmado(self.id, ahora, evento_ref=self.evento_id, descripcion=self.descripcion,
                                             datos_propuestos=self.datos_propuestos,
                                             condiciones_propuestas=tuple(self.condiciones_propuestas.items())))
        return faltan

    def cerrar_por_falta_de_pago(self, ahora: datetime) -> None:
        if self.estado != ESC.PENDIENTE_PAGO:
            raise ErrorDominio("Solo se cierra por falta de pago una solicitud Pendiente de pago.")
        self._cerrar(ESC.CERRADA_FALTA_PAGO, CausaCierreSolicitud.FALTA_PAGO, "El Cliente no efectuó el pago en las 24 h naturales", ahora)
        self._registrar(SolicitudCambioCerradaPorFaltaDePago(self.id, ahora, evento_ref=self.evento_id))

    def cerrar_por_inicio_evento(self, ahora: datetime) -> None:
        if not self.pendiente:
            return
        self._cerrar(ESC.CERRADA_INICIO_EVENTO, CausaCierreSolicitud.INICIO_EVENTO, "El evento inició antes de confirmar", ahora)
        self._registrar(SolicitudCambioCerradaPorInicioEvento(self.id, ahora, evento_ref=self.evento_id))


# ------------------------------------------------------------------ SolicitudServicioAdicional
class SolicitudServicioAdicional(_SolicitudBase):
    FINALES = (ESA.CONFIRMADA, ESA.NO_PROCEDENTE, ESA.NO_SE_REALIZARA, ESA.NO_APROBADA, ESA.NO_AUTORIZADA,
               ESA.CERRADA_FALTA_PAGO, ESA.CERRADA_INICIO_EVENTO, ESA.CERRADA_EVENTO_CANCELADO)
    DETENIDA = ESA.DETENIDA_SALDO_VENCIDO
    CERRADA_CANCELACION = ESA.CERRADA_EVENTO_CANCELADO

    def __init__(self, id_, evento_id, contrato_id, estado_cuenta_id, servicio: str, anticipacion: AnticipacionSolicitud):
        super().__init__(id_, evento_id, contrato_id, estado_cuenta_id)
        self.servicio, self.anticipacion = servicio, anticipacion
        self.estado = ESA.REGISTRADA
        self.elegibilidad_obtenida = False           # SE-004, CA-080
        self.disponibilidad: Optional[DisponibilidadProveedor] = None
        self.decision_cliente: Optional[Decision] = None
        self.autorizacion_administracion: Optional[Decision] = None
        self._registrar(ServicioAdicionalSolicitado(self.id, anticipacion.fecha_solicitud))

    def condicion_temporal(self, ahora: datetime, evento_iniciado: bool) -> CondicionTemporal:
        """La propia solicitud calcula su ventana de elegibilidad (corrección de la Etapa 3 / H-04).
        Specification SERVICIO_ADICIONAL_EN_PLAZO: evento no iniciado AND (elegibilidad obtenida OR cinco días
        naturales contados desde `ahora`). La elegibilidad obtenida no se invalida por la pausa ni por los días
        restantes; si la solicitud se detuvo antes de obtenerla, al retomarla se revalidan los cinco días."""
        return _condicion_temporal(SERVICIO_ADICIONAL_EN_PLAZO, SituacionTemporalSolicitud(
            evento_iniciado, self.elegibilidad_obtenida, AnticipacionSolicitud(ahora, self.anticipacion.fecha_evento)))

    def registrar_disponibilidad(self, d: DisponibilidadProveedor, ahora: datetime) -> None:
        if self.estado not in (ESA.REGISTRADA, ESA.EN_BUSQUEDA_PROVEEDOR):
            raise ErrorDominio("La disponibilidad se registra durante la búsqueda de proveedor.")
        if not d.disponible:
            ct = self.condicion_temporal(ahora, False)
            if not ct.cumple:
                self._cerrar(ESA.NO_PROCEDENTE, CausaCierreSolicitud.PLAZO_INSUFICIENTE, ct.motivo, ahora)
            else:
                self.estado = ESA.EN_BUSQUEDA_PROVEEDOR
            return
        if not self.condicion_temporal(ahora, False).cumple:
            self._cerrar(ESA.NO_PROCEDENTE, CausaCierreSolicitud.PLAZO_INSUFICIENTE, "Alternativa fuera de la ventana", ahora)
            return
        if d.costo is None or d.condiciones is None:
            raise ErrorDominio("Antes de continuar deben determinarse el costo y las condiciones del servicio (CA-075).")
        self.disponibilidad, self.elegibilidad_obtenida = d, True
        self.estado = ESA.PENDIENTE_APROBACION_CLIENTE
        self._registrar(AlternativaProveedorEncontrada(self.id, ahora, proveedor_id=d.proveedor_id))

    def registrar_respuesta_espera(self, acepta_esperar: bool, ahora: datetime) -> None:
        if self.estado != ESA.EN_BUSQUEDA_PROVEEDOR:
            raise ErrorDominio("No hay una búsqueda en curso.")
        if not acepta_esperar:
            self._cerrar(ESA.NO_SE_REALIZARA, CausaCierreSolicitud.CLIENTE_NO_ESPERA, "El Cliente no acepta esperar (CA-078)", ahora)
        elif not self.condicion_temporal(ahora, False).cumple:
            self._cerrar(ESA.NO_PROCEDENTE, CausaCierreSolicitud.PLAZO_INSUFICIENTE, "Esperar no amplía el plazo (CA-077)", ahora)

    def registrar_decision_cliente(self, d: Decision) -> None:
        if self.estado != ESA.PENDIENTE_APROBACION_CLIENTE:
            raise ErrorDominio("La solicitud no espera la aprobación del Cliente.")
        self.decision_cliente = d
        if d.aprobada:
            self.estado = ESA.PENDIENTE_AUTORIZACION
        else:
            self._cerrar(ESA.NO_APROBADA, CausaCierreSolicitud.RECHAZO_CLIENTE, d.motivo, d.fecha)

    def registrar_autorizacion(self, d: Decision) -> None:
        if self.estado != ESA.PENDIENTE_AUTORIZACION:
            raise ErrorDominio("La autorización es posterior a la aprobación del Cliente (CA-081).")
        self.autorizacion_administracion = d
        if d.aprobada:
            self.estado = ESA.AUTORIZADA
        else:
            self._cerrar(ESA.NO_AUTORIZADA, CausaCierreSolicitud.NO_AUTORIZADA, d.motivo, d.fecha)

    def puede_registrar_anexo(self) -> bool:
        return self.estado == ESA.AUTORIZADA and self.anexo_id is None

    def registrar_solicitud_pago(self, obligacion_pago_id: str) -> None:
        if self.estado != ESA.AUTORIZADA or not self.anexo_id:
            raise ErrorDominio("El anexo se registra antes de comunicar la solicitud de pago (CA-082).")
        self.obligacion_pago_id, self.estado = obligacion_pago_id, ESA.PENDIENTE_PAGO

    def confirmar(self, pago_verificado: bool, evento_iniciado: bool, ahora: datetime,
                  evento_cancelado: bool = False) -> List[str]:
        faltan = []
        if evento_cancelado: faltan.append("evento no cancelado (SE-007)")
        if not self.condicion_temporal(ahora, evento_iniciado).cumple: faltan.append("elegibilidad vigente")
        if self.estado != ESA.PENDIENTE_PAGO: faltan.append("aprobación, autorización, anexo y solicitud de pago")
        if not pago_verificado: faltan.append("pago registrado y verificado")
        if not faltan:
            self.estado = ESA.CONFIRMADA
            self._registrar(ServicioAdicionalConfirmado(self.id, ahora, evento_ref=self.evento_id,
                                                        servicio=self.servicio, proveedor_id=self.disponibilidad.proveedor_id,
                                                        condiciones=self.disponibilidad.condiciones))
        return faltan

    def cerrar_por_falta_de_pago(self, ahora: datetime) -> None:
        if self.estado != ESA.PENDIENTE_PAGO:
            raise ErrorDominio("Solo se cierra por falta de pago una solicitud Pendiente de pago.")
        self._cerrar(ESA.CERRADA_FALTA_PAGO, CausaCierreSolicitud.FALTA_PAGO, "El Cliente no efectuó el pago en las 24 h naturales", ahora)
        self._registrar(ServicioAdicionalCerradoPorFaltaDePago(self.id, ahora, evento_ref=self.evento_id))

    def cerrar_por_inicio_evento(self, ahora: datetime) -> None:
        if not self.pendiente:
            return
        self._cerrar(ESA.CERRADA_INICIO_EVENTO, CausaCierreSolicitud.INICIO_EVENTO, "El evento inició antes de confirmar", ahora)
        self._registrar(ServicioAdicionalCerradoPorInicioEvento(self.id, ahora, evento_ref=self.evento_id))


# ------------------------------------------------------------------ SustitucionProveedor
@dataclass(frozen=True)
class AlternativaPropuesta:
    proveedor_id: str
    disponibilidad: DisponibilidadProveedor
    impacto: ImpactoModificacion
    decision_cliente: Optional[Decision] = None
    autorizacion_administracion: Optional[Decision] = None


class SustitucionProveedor(_SolicitudBase):
    FINALES = (ESP.CONFIRMADA, ESP.CERRADA_INICIO_EVENTO, ESP.CERRADA_EVENTO_CANCELADO)
    CERRADA_CANCELACION = ESP.CERRADA_EVENTO_CANCELADO

    def __init__(self, id_, evento_id, servicio_contratado_id, proveedor_original_id, contrato_id, estado_cuenta_id, ahora):
        super().__init__(id_, evento_id, contrato_id, estado_cuenta_id)
        self.servicio_contratado_id, self.proveedor_original_id = servicio_contratado_id, proveedor_original_id
        self.estado = ESP.EN_BUSQUEDA_ALTERNATIVA
        self.alternativas: List[AlternativaPropuesta] = []
        self.costo_adicional: Optional[Importe] = None
        self.aprobada_despues_del_limite = False
        self._registrar(ProveedorNoDisponible(self.id, ahora, evento_ref=evento_id, servicio_contratado_id=servicio_contratado_id))

    @property
    def alternativa_vigente(self) -> Optional[AlternativaPropuesta]:
        return self.alternativas[-1] if self.alternativas else None

    def proponer_alternativa(self, alt: AlternativaPropuesta, costo_adicional: Optional[Importe], ahora: datetime) -> None:
        if self.estado != ESP.EN_BUSQUEDA_ALTERNATIVA:
            raise ErrorDominio("La sustitución no está en búsqueda de alternativa.")
        self.alternativas.append(alt)
        self.costo_adicional = costo_adicional
        self.estado = ESP.PENDIENTE_APROBACION_CLIENTE if alt.impacto.tiene_impacto else ESP.PENDIENTE_FORMALIZACION

    def _reemplazar(self, **cambios):
        a = self.alternativas[-1]
        self.alternativas[-1] = AlternativaPropuesta(**{**a.__dict__, **cambios})

    def registrar_decision_cliente(self, d: Decision) -> None:
        if self.estado != ESP.PENDIENTE_APROBACION_CLIENTE:
            raise ErrorDominio("La alternativa no requiere o no espera aprobación del Cliente.")
        self._reemplazar(decision_cliente=d)
        if d.aprobada:
            self.estado = ESP.PENDIENTE_AUTORIZACION
        else:
            self.estado = ESP.EN_BUSQUEDA_ALTERNATIVA                    # CA-054
            self._registrar(AlternativaRechazadaPorCliente(self.id, d.fecha, proveedor_id=self.alternativas[-1].proveedor_id))

    def registrar_autorizacion(self, d: Decision, fecha_evento: datetime) -> None:
        """Si la autorización llega después del límite ordinario (3 días hábiles antes del evento), el costo
        adicional debe pagarse y verificarse antes de confirmar, sin considerarse vencido (SE-001, CA-052)."""
        if self.estado != ESP.PENDIENTE_AUTORIZACION:
            raise ErrorDominio("La autorización es posterior a la aprobación del Cliente (SE-001).")
        self._reemplazar(autorizacion_administracion=d)
        if d.aprobada:
            self.estado = ESP.PENDIENTE_FORMALIZACION
            self.aprobada_despues_del_limite = d.fecha > restar_dias_habiles(fecha_evento, 3)
        else:
            self.estado = ESP.EN_BUSQUEDA_ALTERNATIVA                    # CA-050
            self._registrar(AlternativaNoAutorizadaPorAdministracion(self.id, d.fecha, proveedor_id=self.alternativas[-1].proveedor_id))

    def puede_registrar_anexo(self) -> bool:
        return self.estado == ESP.PENDIENTE_FORMALIZACION and self.anexo_id is None

    @property
    def importe_adicional_aprobado(self) -> bool:
        """El costo adicional solo se integra al saldo general si el Cliente aprobó y Administración autorizó (CA-052)."""
        a = self.alternativa_vigente
        return bool(a and self.costo_adicional and self.costo_adicional.cantidad > 0
                    and a.decision_cliente and a.decision_cliente.aprobada
                    and a.autorizacion_administracion and a.autorizacion_administracion.aprobada
                    and self.estado in (ESP.PENDIENTE_FORMALIZACION, ESP.CONFIRMADA))

    def confirmar(self, pago_previo_verificado: bool, evento_iniciado: bool, ahora: datetime,
                  evento_cancelado: bool = False) -> List[str]:
        faltan = []
        if evento_iniciado: faltan.append("evento no iniciado")
        if evento_cancelado: faltan.append("evento no cancelado (SE-007)")
        if self.estado != ESP.PENDIENTE_FORMALIZACION: faltan.append("decisiones requeridas")
        if not self.anexo_id: faltan.append("anexo vinculado al contrato original")
        if self.costo_adicional and self.aprobada_despues_del_limite and not pago_previo_verificado:
            faltan.append("pago del costo adicional verificado antes de confirmar (CA-052)")
        if not faltan:
            self.estado = ESP.CONFIRMADA
            self._registrar(SustitucionProveedorConfirmada(self.id, ahora, evento_ref=self.evento_id,
                                                           servicio_contratado_id=self.servicio_contratado_id,
                                                           proveedor_id=self.alternativa_vigente.proveedor_id))
        return faltan

    def cerrar_por_inicio_evento(self, ahora: datetime) -> None:
        if not self.pendiente:
            return
        self._cerrar(ESP.CERRADA_INICIO_EVENTO, CausaCierreSolicitud.INICIO_EVENTO, "El reemplazo no se concretó", ahora)
        self._registrar(SustitucionProveedorCerradaPorInicioEvento(self.id, ahora, evento_ref=self.evento_id))
