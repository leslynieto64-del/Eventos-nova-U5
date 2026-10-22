"""Aggregates SolicitudCambio, SolicitudServicioAdicional y SustitucionProveedor."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from .base import AggregateRoot
from .maquina_estados import MaquinaEstados, Transicion
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
                               SOLICITUD_CAMBIO_EN_PLAZO, SERVICIO_ADICIONAL_EN_PLAZO, SituacionTemporalSolicitud,
                               MOTIVO_EVENTO_INICIADO_SERVICIO_ADICIONAL)

_AFECTA_COSTOS = AfectaCostos()


def _condicion_temporal(especificacion, situacion: SituacionTemporalSolicitud) -> CondicionTemporal:
    """Traduce una Specification temporal al Value Object CondicionTemporal (primer motivo o cumplida)."""
    motivo = especificacion.primer_motivo(situacion)
    return CondicionTemporal(True) if motivo is None else CondicionTemporal(False, motivo)


class _SolicitudBase(AggregateRoot):
    FINALES: tuple = ()
    DETENIDA = None
    CERRADA_CANCELACION = None
    # N2: únicos estados que una decisión de regularización puede modificar. SE-006 y P-06 la aplican al registrar una
    # solicitud nueva de cambio o de servicio adicional (Registrada) y al retomarla (Detenida por saldo vencido).
    ESTADOS_REGULARIZABLES: tuple = ()

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
        """Usado al registrar y al retomar: la solicitud cambia su propio estado.
        N2: solo una solicitud Registrada o Detenida por saldo vencido (ESTADOS_REGULARIZABLES) cambia por esta
        decisión. En cualquier otro estado (en trámite, P-06, o final) la llamada no tiene efecto: no modifica estado,
        atributos ni Domain Events y devuelve el mismo valor que antes (True si puede continuar; False si no)."""
        if self.estado not in self.ESTADOS_REGULARIZABLES:
            return d.puede_continuar
        if d.puede_continuar:
            if self.estado == self.DETENIDA:
                self.estado = self._estado_antes_de_detener
            return True
        if d.detener_por_saldo:
            if self.estado != self.DETENIDA:
                self._estado_antes_de_detener, self.estado = self.estado, self.DETENIDA
            return False
        if d.motivo == MOTIVO_EVENTO_INICIADO_SERVICIO_ADICIONAL:
            causa = CausaCierreSolicitud.INICIO_EVENTO       # N6, CA-099: el Evento ya inició; no es falta de plazo
        else:
            causa = CausaCierreSolicitud.PLAZO_INSUFICIENTE if d.motivo.startswith('Condición') else CausaCierreSolicitud.EVENTO_CANCELADO
        self._cerrar(estado_no_procede, causa, d.motivo, ahora)
        return False


# ------------------------------------------------------------------ SolicitudCambio
class AccionSolicitudCambio(Enum):
    """Acciones internas de la State Machine de SolicitudCambio (Etapa E3F). Corresponden a los métodos propios de la
    clase; los que tienen varios resultados usan una acción por resultado («método:resultado»), elegida a partir del
    resultado que el método ya calcula (ResultadoViabilidad.viable, CAMBIO_REQUIERE_APROBACION_CLIENTE o
    Decision.aprobada), sin reglas nuevas."""
    REGISTRAR_VIABILIDAD_NO_VIABLE = "registrar_viabilidad:no_viable"                                # ruta A
    REGISTRAR_VIABILIDAD_REQUIERE_APROBACION = "registrar_viabilidad:requiere_aprobacion_cliente"    # ruta B
    REGISTRAR_VIABILIDAD_SIN_APROBACION = "registrar_viabilidad:sin_aprobacion_cliente"              # ruta C
    REGISTRAR_DECISION_CLIENTE_APROBADA = "registrar_decision_cliente:aprobada"
    REGISTRAR_DECISION_CLIENTE_RECHAZADA = "registrar_decision_cliente:rechazada"
    REGISTRAR_AUTORIZACION_APROBADA = "registrar_autorizacion:aprobada"
    REGISTRAR_AUTORIZACION_RECHAZADA = "registrar_autorizacion:rechazada"
    REGISTRAR_SOLICITUD_PAGO = "registrar_solicitud_pago"
    CONFIRMAR = "confirmar"
    CERRAR_POR_FALTA_DE_PAGO = "cerrar_por_falta_de_pago"
    CERRAR_POR_INICIO_EVENTO = "cerrar_por_inicio_evento"


_AC = AccionSolicitudCambio
_MENSAJE_VIABILIDAD = "La viabilidad solo se evalúa en una solicitud registrada."
_MENSAJE_DECISION_CLIENTE_SC = "La solicitud no espera la aprobación del Cliente."
_MENSAJE_AUTORIZACION_SC = "La autorización requiere la aprobación previa del Cliente (CA-043)."
_MENSAJE_PAGO_SC = "El pago se solicita con el anexo registrado (CA-068)."
_EN_TRAMITE_SC = (ESC.REGISTRADA, ESC.DETENIDA_SALDO_VENCIDO, ESC.PENDIENTE_APROBACION_CLIENTE, ESC.PENDIENTE_AUTORIZACION,
                  ESC.PENDIENTE_FORMALIZACION, ESC.PENDIENTE_PAGO)
# Mensajes de rechazo existentes, sin cambios. confirmar devuelve sus faltantes y cerrar_por_inicio_evento no tiene
# efecto en un estado final: la máquina solo se consulta cuando la operación procede.
_MENSAJES_RECHAZO_SC = {
    _AC.REGISTRAR_VIABILIDAD_NO_VIABLE: lambda o: _MENSAJE_VIABILIDAD,
    _AC.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION: lambda o: _MENSAJE_VIABILIDAD,
    _AC.REGISTRAR_VIABILIDAD_SIN_APROBACION: lambda o: _MENSAJE_VIABILIDAD,
    _AC.REGISTRAR_DECISION_CLIENTE_APROBADA: lambda o: _MENSAJE_DECISION_CLIENTE_SC,
    _AC.REGISTRAR_DECISION_CLIENTE_RECHAZADA: lambda o: _MENSAJE_DECISION_CLIENTE_SC,
    _AC.REGISTRAR_AUTORIZACION_APROBADA: lambda o: _MENSAJE_AUTORIZACION_SC,
    _AC.REGISTRAR_AUTORIZACION_RECHAZADA: lambda o: _MENSAJE_AUTORIZACION_SC,
    _AC.REGISTRAR_SOLICITUD_PAGO: lambda o: _MENSAJE_PAGO_SC,
    _AC.CERRAR_POR_FALTA_DE_PAGO: lambda o: "Solo se cierra por falta de pago una solicitud Pendiente de pago.",
}

# Mapa de dominio U3, página «03 — Detalle B», «Estados de SolicitudCambio · CA-037–CA-070», y BPMN SP-03. La puerta
# «¿Existen importes por pagar?» del mapa corresponde a las dos salidas de Pendiente de formalización (solicitud de
# pago y confirmación). Fuera de la tabla, con sus guardas actuales y sin cambios: la regularización
# (aplicar_decision_regularizacion, N2: Registrada → Detenida → estado anterior, o No procedente), el cierre por
# cancelación del evento (BN-008) y asociar_anexo, heredados de _SolicitudBase.
# AR-05: «En evaluación» no es un estado del flujo normal. No figura entre los estados de esta máquina, ninguna
# transición entra en él ni sale de él; ver MAQUINA_COMPATIBILIDAD_EN_EVALUACION.
MAQUINA_SOLICITUD_CAMBIO = MaquinaEstados(
    estados=tuple(e for e in ESC if e is not ESC.EN_EVALUACION),
    transiciones=(
        Transicion(ESC.REGISTRADA, _AC.REGISTRAR_VIABILIDAD_NO_VIABLE, ESC.NO_PROCEDENTE),                        # ruta A
        Transicion(ESC.REGISTRADA, _AC.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION, ESC.PENDIENTE_APROBACION_CLIENTE),  # ruta B, BN-003
        Transicion(ESC.REGISTRADA, _AC.REGISTRAR_VIABILIDAD_SIN_APROBACION, ESC.PENDIENTE_FORMALIZACION),          # ruta C
        Transicion(ESC.PENDIENTE_APROBACION_CLIENTE, _AC.REGISTRAR_DECISION_CLIENTE_APROBADA, ESC.PENDIENTE_AUTORIZACION),
        Transicion(ESC.PENDIENTE_APROBACION_CLIENTE, _AC.REGISTRAR_DECISION_CLIENTE_RECHAZADA, ESC.RECHAZADA_CLIENTE),
        Transicion(ESC.PENDIENTE_AUTORIZACION, _AC.REGISTRAR_AUTORIZACION_APROBADA, ESC.PENDIENTE_FORMALIZACION),   # CA-043
        Transicion(ESC.PENDIENTE_AUTORIZACION, _AC.REGISTRAR_AUTORIZACION_RECHAZADA, ESC.NO_AUTORIZADA),
        Transicion(ESC.PENDIENTE_FORMALIZACION, _AC.REGISTRAR_SOLICITUD_PAGO, ESC.PENDIENTE_PAGO),                 # CA-068
        Transicion(ESC.PENDIENTE_FORMALIZACION, _AC.CONFIRMAR, ESC.CONFIRMADA),
        Transicion(ESC.PENDIENTE_PAGO, _AC.CONFIRMAR, ESC.CONFIRMADA),                                            # SE-007
        Transicion(ESC.PENDIENTE_PAGO, _AC.CERRAR_POR_FALTA_DE_PAGO, ESC.CERRADA_FALTA_PAGO),                    # BN-004
    ) + tuple(Transicion(e, _AC.CERRAR_POR_INICIO_EVENTO, ESC.CERRADA_INICIO_EVENTO) for e in _EN_TRAMITE_SC),
    mensajes_rechazo=_MENSAJES_RECHAZO_SC,
    nombre="SolicitudCambio",
)

# Compatibilidad histórica (AR-05), separada de la tabla normal. EN_EVALUACION es un valor heredado que ningún método
# asigna; si una solicitud persistida lo tuviera, conserva las respuestas anteriores a E3F (referencia
# comportamiento_solicitud_cambio_pre_e3f.json, bloque historico_en_evaluacion): la viabilidad se registra como desde
# Registrada y el cierre por inicio del evento procede. Solo contiene salidas desde EN_EVALUACION: no hay transición
# de entrada. Las demás acciones se rechazan con los mismos mensajes.
MAQUINA_COMPATIBILIDAD_EN_EVALUACION = MaquinaEstados(
    estados=ESC,
    transiciones=(
        Transicion(ESC.EN_EVALUACION, _AC.REGISTRAR_VIABILIDAD_NO_VIABLE, ESC.NO_PROCEDENTE),
        Transicion(ESC.EN_EVALUACION, _AC.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION, ESC.PENDIENTE_APROBACION_CLIENTE),
        Transicion(ESC.EN_EVALUACION, _AC.REGISTRAR_VIABILIDAD_SIN_APROBACION, ESC.PENDIENTE_FORMALIZACION),
        Transicion(ESC.EN_EVALUACION, _AC.CERRAR_POR_INICIO_EVENTO, ESC.CERRADA_INICIO_EVENTO),
    ),
    mensajes_rechazo=_MENSAJES_RECHAZO_SC,
    nombre="SolicitudCambio (compatibilidad histórica de EN_EVALUACION, AR-05)",
)


def _maquina_solicitud_cambio(estado: ESC) -> MaquinaEstados:
    """La tabla normal, o la de compatibilidad solo para el valor histórico EN_EVALUACION (AR-05)."""
    return MAQUINA_COMPATIBILIDAD_EN_EVALUACION if estado is ESC.EN_EVALUACION else MAQUINA_SOLICITUD_CAMBIO


class SolicitudCambio(_SolicitudBase):
    FINALES = (ESC.CONFIRMADA, ESC.NO_PROCEDENTE, ESC.RECHAZADA_CLIENTE, ESC.NO_AUTORIZADA,
               ESC.CERRADA_FALTA_PAGO, ESC.CERRADA_INICIO_EVENTO, ESC.CERRADA_EVENTO_CANCELADO)
    DETENIDA = ESC.DETENIDA_SALDO_VENCIDO
    CERRADA_CANCELACION = ESC.CERRADA_EVENTO_CANCELADO
    ESTADOS_REGULARIZABLES = (ESC.REGISTRADA, ESC.DETENIDA_SALDO_VENCIDO)        # N2

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

    def _transitar(self, accion: AccionSolicitudCambio) -> ESC:
        """E3F: destino permitido por la máquina (o TransicionNoPermitida, un ErrorDominio, con el mensaje existente).
        No modifica nada: cada método la consulta antes de modificar el agregado y luego asigna el destino."""
        return _maquina_solicitud_cambio(self.estado).transitar(self.estado, accion)

    def registrar_viabilidad(self, resultado: ResultadoViabilidad, impacto: ImpactoModificacion, ahora: datetime) -> None:
        if not resultado.viable:                                   # Ruta A
            accion = _AC.REGISTRAR_VIABILIDAD_NO_VIABLE
        elif CAMBIO_REQUIERE_APROBACION_CLIENTE.es_satisfecha_por(impacto):   # Ruta B
            accion = _AC.REGISTRAR_VIABILIDAD_REQUIERE_APROBACION
        else:                                                       # Ruta C
            accion = _AC.REGISTRAR_VIABILIDAD_SIN_APROBACION
        destino = self._transitar(accion)
        self.viabilidad, self.impacto = resultado, impacto
        self._registrar(ViabilidadCambioEvaluada(self.id, ahora, viable=resultado.viable))
        if accion is _AC.REGISTRAR_VIABILIDAD_NO_VIABLE:
            self._cerrar(destino, CausaCierreSolicitud.NO_VIABLE, resultado.motivo, ahora)
        else:
            self.estado = destino
        self.importes_por_pagar = resultado.viable and (_AFECTA_COSTOS.es_satisfecha_por(impacto) or self.aplica_cargo_tardio)

    def registrar_decision_cliente(self, d: Decision) -> None:
        destino = self._transitar(_AC.REGISTRAR_DECISION_CLIENTE_APROBADA if d.aprobada
                                  else _AC.REGISTRAR_DECISION_CLIENTE_RECHAZADA)
        self.decision_cliente = d
        if d.aprobada:
            self.estado = destino
        else:
            self._cerrar(destino, CausaCierreSolicitud.RECHAZO_CLIENTE, d.motivo, d.fecha)

    def registrar_autorizacion(self, d: Decision) -> None:
        destino = self._transitar(_AC.REGISTRAR_AUTORIZACION_APROBADA if d.aprobada
                                  else _AC.REGISTRAR_AUTORIZACION_RECHAZADA)
        self.autorizacion_administracion = d
        if d.aprobada:
            self.estado = destino
        else:
            self._cerrar(destino, CausaCierreSolicitud.NO_AUTORIZADA, d.motivo, d.fecha)

    def puede_registrar_anexo(self) -> bool:
        return self.estado == ESC.PENDIENTE_FORMALIZACION and self.anexo_id is None

    def registrar_solicitud_pago(self, obligacion_pago_id: str) -> None:
        destino = self._transitar(_AC.REGISTRAR_SOLICITUD_PAGO)
        if not self.anexo_id:
            raise ErrorDominio(_MENSAJE_PAGO_SC)
        self.obligacion_pago_id, self.estado = obligacion_pago_id, destino

    def confirmar(self, pago_verificado: bool, evento_iniciado: bool, ahora: datetime,
                  evento_cancelado: bool = False) -> List[str]:
        faltan = []
        if evento_iniciado: faltan.append("evento no iniciado")
        if evento_cancelado: faltan.append("evento no cancelado (SE-007)")
        if not _maquina_solicitud_cambio(self.estado).permite(self.estado, _AC.CONFIRMAR):   # la tabla decide el estado
            faltan.append("aprobaciones requeridas")
        if not self.anexo_id: faltan.append("anexo vinculado al contrato original")
        if self.importes_por_pagar and not pago_verificado: faltan.append("pago registrado y verificado")
        if not faltan:                                   # la máquina solo se consulta con todos los requisitos cumplidos
            self.estado = self._transitar(_AC.CONFIRMAR)
            self._registrar(CambioConfirmado(self.id, ahora, evento_ref=self.evento_id, descripcion=self.descripcion,
                                             datos_propuestos=self.datos_propuestos,
                                             condiciones_propuestas=tuple(self.condiciones_propuestas.items())))
        return faltan

    def cerrar_por_falta_de_pago(self, ahora: datetime) -> None:
        destino = self._transitar(_AC.CERRAR_POR_FALTA_DE_PAGO)
        self._cerrar(destino, CausaCierreSolicitud.FALTA_PAGO, "El Cliente no efectuó el pago en las 24 h naturales", ahora)
        self._registrar(SolicitudCambioCerradaPorFaltaDePago(self.id, ahora, evento_ref=self.evento_id))

    def cerrar_por_inicio_evento(self, ahora: datetime) -> None:
        if not self.pendiente:                           # estados finales: sin efecto
            return
        destino = self._transitar(_AC.CERRAR_POR_INICIO_EVENTO)
        self._cerrar(destino, CausaCierreSolicitud.INICIO_EVENTO, "El evento inició antes de confirmar", ahora)
        self._registrar(SolicitudCambioCerradaPorInicioEvento(self.id, ahora, evento_ref=self.evento_id))


# ------------------------------------------------------------------ SolicitudServicioAdicional
class AccionServicioAdicional(Enum):
    """Acciones internas de la State Machine de SolicitudServicioAdicional (Etapa E3E). Corresponden a los métodos propios
    de la clase; los que tienen varios resultados usan una acción por resultado («método:resultado»), elegida a partir
    del resultado que el método ya calcula, sin reglas nuevas."""
    REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR = "registrar_disponibilidad:con_proveedor"
    REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR = "registrar_disponibilidad:sin_proveedor"
    REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO = "registrar_disponibilidad:fuera_de_plazo"
    REGISTRAR_RESPUESTA_ESPERA_NO_ESPERA = "registrar_respuesta_espera:no_espera"
    REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO = "registrar_respuesta_espera:fuera_de_plazo"
    REGISTRAR_DECISION_CLIENTE_APROBADA = "registrar_decision_cliente:aprobada"
    REGISTRAR_DECISION_CLIENTE_RECHAZADA = "registrar_decision_cliente:rechazada"
    REGISTRAR_AUTORIZACION_APROBADA = "registrar_autorizacion:aprobada"
    REGISTRAR_AUTORIZACION_RECHAZADA = "registrar_autorizacion:rechazada"
    REGISTRAR_SOLICITUD_PAGO = "registrar_solicitud_pago"
    CONFIRMAR = "confirmar"
    CERRAR_POR_FALTA_DE_PAGO = "cerrar_por_falta_de_pago"
    CERRAR_POR_INICIO_EVENTO = "cerrar_por_inicio_evento"


_AS = AccionServicioAdicional
_MENSAJE_DISPONIBILIDAD = "La disponibilidad se registra durante la búsqueda de proveedor."
_MENSAJE_ESPERA = "No hay una búsqueda en curso."
_EN_TRAMITE_SA = (ESA.REGISTRADA, ESA.DETENIDA_SALDO_VENCIDO, ESA.EN_BUSQUEDA_PROVEEDOR, ESA.PENDIENTE_APROBACION_CLIENTE,
                  ESA.PENDIENTE_AUTORIZACION, ESA.AUTORIZADA, ESA.PENDIENTE_PAGO)

# Mapa de dominio U3, página «03 — Detalle B», «Estados de SolicitudServicioAdicional · SE-004, CA-071–CA-083», y
# BPMN SP-04. Fuera de la tabla, con sus guardas actuales: la regularización (aplicar_decision_regularizacion, N2), el
# cierre por cancelación del evento (BN-008) y asociar_anexo, heredados de _SolicitudBase; y la respuesta del Cliente
# que acepta esperar dentro de la ventana, que no cambia el estado (guarda manual de registrar_respuesta_espera).
MAQUINA_SERVICIO_ADICIONAL = MaquinaEstados(
    estados=ESA,
    transiciones=(
        Transicion(ESA.REGISTRADA, _AS.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR, ESA.PENDIENTE_APROBACION_CLIENTE),        # CA-073, CA-075, CA-079
        Transicion(ESA.EN_BUSQUEDA_PROVEEDOR, _AS.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR, ESA.PENDIENTE_APROBACION_CLIENTE),
        Transicion(ESA.REGISTRADA, _AS.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR, ESA.EN_BUSQUEDA_PROVEEDOR),               # CA-074, CA-076
        Transicion(ESA.REGISTRADA, _AS.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO, ESA.NO_PROCEDENTE),                     # CA-077, CA-083
        Transicion(ESA.EN_BUSQUEDA_PROVEEDOR, _AS.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO, ESA.NO_PROCEDENTE),
        Transicion(ESA.EN_BUSQUEDA_PROVEEDOR, _AS.REGISTRAR_RESPUESTA_ESPERA_NO_ESPERA, ESA.NO_SE_REALIZARA),           # CA-078
        Transicion(ESA.EN_BUSQUEDA_PROVEEDOR, _AS.REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO, ESA.NO_PROCEDENTE),        # CA-077
        Transicion(ESA.PENDIENTE_APROBACION_CLIENTE, _AS.REGISTRAR_DECISION_CLIENTE_APROBADA, ESA.PENDIENTE_AUTORIZACION),  # CA-079
        Transicion(ESA.PENDIENTE_APROBACION_CLIENTE, _AS.REGISTRAR_DECISION_CLIENTE_RECHAZADA, ESA.NO_APROBADA),
        Transicion(ESA.PENDIENTE_AUTORIZACION, _AS.REGISTRAR_AUTORIZACION_APROBADA, ESA.AUTORIZADA),                    # CA-079, CA-081
        Transicion(ESA.PENDIENTE_AUTORIZACION, _AS.REGISTRAR_AUTORIZACION_RECHAZADA, ESA.NO_AUTORIZADA),
        Transicion(ESA.AUTORIZADA, _AS.REGISTRAR_SOLICITUD_PAGO, ESA.PENDIENTE_PAGO),                                   # CA-082
        Transicion(ESA.PENDIENTE_PAGO, _AS.CONFIRMAR, ESA.CONFIRMADA),                                                   # CA-080, CA-082, SE-007
        Transicion(ESA.PENDIENTE_PAGO, _AS.CERRAR_POR_FALTA_DE_PAGO, ESA.CERRADA_FALTA_PAGO),                           # CA-080, BN-004
    ) + tuple(Transicion(e, _AS.CERRAR_POR_INICIO_EVENTO, ESA.CERRADA_INICIO_EVENTO) for e in _EN_TRAMITE_SA),      # CA-071, GL-032
    # Sin proveedor estando ya En búsqueda: la búsqueda continúa sin cambios (CA-076).
    repeticiones_idempotentes=((ESA.EN_BUSQUEDA_PROVEEDOR, _AS.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR),),
    # Mensajes de rechazo existentes, sin cambios. confirmar devuelve sus faltantes y cerrar_por_inicio_evento no tiene
    # efecto en un estado final: la máquina solo se consulta cuando la operación procede.
    mensajes_rechazo={
        _AS.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR: lambda o: _MENSAJE_DISPONIBILIDAD,
        _AS.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR: lambda o: _MENSAJE_DISPONIBILIDAD,
        _AS.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO: lambda o: _MENSAJE_DISPONIBILIDAD,
        _AS.REGISTRAR_RESPUESTA_ESPERA_NO_ESPERA: lambda o: _MENSAJE_ESPERA,
        _AS.REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO: lambda o: _MENSAJE_ESPERA,
        _AS.REGISTRAR_DECISION_CLIENTE_APROBADA: lambda o: "La solicitud no espera la aprobación del Cliente.",
        _AS.REGISTRAR_DECISION_CLIENTE_RECHAZADA: lambda o: "La solicitud no espera la aprobación del Cliente.",
        _AS.REGISTRAR_AUTORIZACION_APROBADA: lambda o: "La autorización es posterior a la aprobación del Cliente (CA-081).",
        _AS.REGISTRAR_AUTORIZACION_RECHAZADA: lambda o: "La autorización es posterior a la aprobación del Cliente (CA-081).",
        _AS.REGISTRAR_SOLICITUD_PAGO: lambda o: "El anexo se registra antes de comunicar la solicitud de pago (CA-082).",
        _AS.CERRAR_POR_FALTA_DE_PAGO: lambda o: "Solo se cierra por falta de pago una solicitud Pendiente de pago.",
    },
    nombre="SolicitudServicioAdicional",
)


class SolicitudServicioAdicional(_SolicitudBase):
    FINALES = (ESA.CONFIRMADA, ESA.NO_PROCEDENTE, ESA.NO_SE_REALIZARA, ESA.NO_APROBADA, ESA.NO_AUTORIZADA,
               ESA.CERRADA_FALTA_PAGO, ESA.CERRADA_INICIO_EVENTO, ESA.CERRADA_EVENTO_CANCELADO)
    DETENIDA = ESA.DETENIDA_SALDO_VENCIDO
    CERRADA_CANCELACION = ESA.CERRADA_EVENTO_CANCELADO
    ESTADOS_REGULARIZABLES = (ESA.REGISTRADA, ESA.DETENIDA_SALDO_VENCIDO)        # N2

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
        """E3E: el resultado se calcula como antes (la condición temporal no tiene efectos) y elige la acción; la máquina
        valida el estado antes de exigir costo y condiciones (CA-075) y antes de modificar el agregado, de modo que los
        rechazos conservan su orden: estado, CA-075."""
        if not d.disponible:
            ct = self.condicion_temporal(ahora, False)
            accion = _AS.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR if ct.cumple else _AS.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO
            motivo = ct.motivo
        elif not self.condicion_temporal(ahora, False).cumple:
            accion, motivo = _AS.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO, "Alternativa fuera de la ventana"
        else:
            accion, motivo = _AS.REGISTRAR_DISPONIBILIDAD_CON_PROVEEDOR, None
        if MAQUINA_SERVICIO_ADICIONAL.es_repeticion(self.estado, accion):
            return                                       # ya En búsqueda y sin proveedor: la búsqueda continúa (CA-076)
        destino = MAQUINA_SERVICIO_ADICIONAL.transitar(self.estado, accion)
        if accion is _AS.REGISTRAR_DISPONIBILIDAD_FUERA_DE_PLAZO:
            self._cerrar(destino, CausaCierreSolicitud.PLAZO_INSUFICIENTE, motivo, ahora)
            return
        if accion is _AS.REGISTRAR_DISPONIBILIDAD_SIN_PROVEEDOR:
            self.estado = destino
            return
        if d.costo is None or d.condiciones is None:
            raise ErrorDominio("Antes de continuar deben determinarse el costo y las condiciones del servicio (CA-075).")
        self.disponibilidad, self.elegibilidad_obtenida = d, True
        self.estado = destino
        self._registrar(AlternativaProveedorEncontrada(self.id, ahora, proveedor_id=d.proveedor_id))

    def registrar_respuesta_espera(self, acepta_esperar: bool, ahora: datetime) -> None:
        if self.estado != ESA.EN_BUSQUEDA_PROVEEDOR:          # guarda manual existente
            raise ErrorDominio(_MENSAJE_ESPERA)
        if not acepta_esperar:
            accion, causa, motivo = (_AS.REGISTRAR_RESPUESTA_ESPERA_NO_ESPERA, CausaCierreSolicitud.CLIENTE_NO_ESPERA,
                                     "El Cliente no acepta esperar (CA-078)")
        elif not self.condicion_temporal(ahora, False).cumple:
            accion, causa, motivo = (_AS.REGISTRAR_RESPUESTA_ESPERA_FUERA_DE_PLAZO, CausaCierreSolicitud.PLAZO_INSUFICIENTE,
                                     "Esperar no amplía el plazo (CA-077)")
        else:
            return                       # acepta esperar dentro de la ventana: operación válida sin cambio de estado
        self._cerrar(MAQUINA_SERVICIO_ADICIONAL.transitar(self.estado, accion), causa, motivo, ahora)

    def registrar_decision_cliente(self, d: Decision) -> None:
        destino = MAQUINA_SERVICIO_ADICIONAL.transitar(
            self.estado, _AS.REGISTRAR_DECISION_CLIENTE_APROBADA if d.aprobada else _AS.REGISTRAR_DECISION_CLIENTE_RECHAZADA)
        self.decision_cliente = d
        if d.aprobada:
            self.estado = destino
        else:
            self._cerrar(destino, CausaCierreSolicitud.RECHAZO_CLIENTE, d.motivo, d.fecha)

    def registrar_autorizacion(self, d: Decision) -> None:
        destino = MAQUINA_SERVICIO_ADICIONAL.transitar(
            self.estado, _AS.REGISTRAR_AUTORIZACION_APROBADA if d.aprobada else _AS.REGISTRAR_AUTORIZACION_RECHAZADA)
        self.autorizacion_administracion = d
        if d.aprobada:
            self.estado = destino
        else:
            self._cerrar(destino, CausaCierreSolicitud.NO_AUTORIZADA, d.motivo, d.fecha)

    def puede_registrar_anexo(self) -> bool:
        return self.estado == ESA.AUTORIZADA and self.anexo_id is None

    def registrar_solicitud_pago(self, obligacion_pago_id: str) -> None:
        destino = MAQUINA_SERVICIO_ADICIONAL.transitar(self.estado, _AS.REGISTRAR_SOLICITUD_PAGO)
        if not self.anexo_id:
            raise ErrorDominio("El anexo se registra antes de comunicar la solicitud de pago (CA-082).")
        self.obligacion_pago_id, self.estado = obligacion_pago_id, destino

    def confirmar(self, pago_verificado: bool, evento_iniciado: bool, ahora: datetime,
                  evento_cancelado: bool = False) -> List[str]:
        faltan = []
        if evento_cancelado: faltan.append("evento no cancelado (SE-007)")
        if not self.condicion_temporal(ahora, evento_iniciado).cumple: faltan.append("elegibilidad vigente")
        if self.estado != ESA.PENDIENTE_PAGO: faltan.append("aprobación, autorización, anexo y solicitud de pago")
        if not pago_verificado: faltan.append("pago registrado y verificado")
        if not faltan:                                   # la máquina solo se consulta con todos los requisitos cumplidos
            self.estado = MAQUINA_SERVICIO_ADICIONAL.transitar(self.estado, _AS.CONFIRMAR)
            self._registrar(ServicioAdicionalConfirmado(self.id, ahora, evento_ref=self.evento_id,
                                                        servicio=self.servicio, proveedor_id=self.disponibilidad.proveedor_id,
                                                        condiciones=self.disponibilidad.condiciones))
        return faltan

    def cerrar_por_falta_de_pago(self, ahora: datetime) -> None:
        destino = MAQUINA_SERVICIO_ADICIONAL.transitar(self.estado, _AS.CERRAR_POR_FALTA_DE_PAGO)
        self._cerrar(destino, CausaCierreSolicitud.FALTA_PAGO, "El Cliente no efectuó el pago en las 24 h naturales", ahora)
        self._registrar(ServicioAdicionalCerradoPorFaltaDePago(self.id, ahora, evento_ref=self.evento_id))

    def cerrar_por_inicio_evento(self, ahora: datetime) -> None:
        if not self.pendiente:                           # estados finales: sin efecto
            return
        destino = MAQUINA_SERVICIO_ADICIONAL.transitar(self.estado, _AS.CERRAR_POR_INICIO_EVENTO)
        self._cerrar(destino, CausaCierreSolicitud.INICIO_EVENTO, "El evento inició antes de confirmar", ahora)
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

    # -- State Machine (Etapa E3C). Las importaciones se hacen aquí para que el cambio quede dentro de la clase.
    from enum import Enum as _Enum
    from .maquina_estados import MaquinaEstados as _MaquinaEstados, Transicion as _Transicion

    class Accion(_Enum):
        """Acciones internas de la máquina. Los métodos con dos resultados posibles se representan con una acción por
        resultado; el método la elige a partir del resultado que ya calcula (impacto de la alternativa o
        Decision.aprobada), sin reglas nuevas."""
        PROPONER_ALTERNATIVA_CON_IMPACTO = "proponer_alternativa:con_impacto"     # ImpactoModificacion.tiene_impacto
        PROPONER_ALTERNATIVA_SIN_IMPACTO = "proponer_alternativa:sin_impacto"
        APROBACION_CLIENTE = "registrar_decision_cliente:aprobada"                 # Decision.aprobada
        RECHAZO_CLIENTE = "registrar_decision_cliente:rechazada"
        AUTORIZACION_ADMINISTRACION = "registrar_autorizacion:aprobada"
        RECHAZO_ADMINISTRACION = "registrar_autorizacion:rechazada"
        CONFIRMAR = "confirmar"
        CERRAR_POR_INICIO_EVENTO = "cerrar_por_inicio_evento"
        CERRAR_POR_CANCELACION_EVENTO = "cerrar_por_cancelacion_evento"

    # Mapa de dominio U3, página «03 — Detalle B», «Estados de SustitucionProveedor · SE-001, CA-046–CA-054, CA-096».
    # Los cierres proceden «desde cualquier estado pendiente» (CA-096) o «en trámite» (BN-008): los cuatro no finales.
    MAQUINA = _MaquinaEstados(
        estados=ESP,
        transiciones=(
            _Transicion(ESP.EN_BUSQUEDA_ALTERNATIVA, Accion.PROPONER_ALTERNATIVA_CON_IMPACTO, ESP.PENDIENTE_APROBACION_CLIENTE),  # CA-049
            _Transicion(ESP.EN_BUSQUEDA_ALTERNATIVA, Accion.PROPONER_ALTERNATIVA_SIN_IMPACTO, ESP.PENDIENTE_FORMALIZACION),       # CA-053
            _Transicion(ESP.PENDIENTE_APROBACION_CLIENTE, Accion.APROBACION_CLIENTE, ESP.PENDIENTE_AUTORIZACION),                 # CA-049
            _Transicion(ESP.PENDIENTE_APROBACION_CLIENTE, Accion.RECHAZO_CLIENTE, ESP.EN_BUSQUEDA_ALTERNATIVA),                   # CA-054
            _Transicion(ESP.PENDIENTE_AUTORIZACION, Accion.AUTORIZACION_ADMINISTRACION, ESP.PENDIENTE_FORMALIZACION),             # CA-051, CA-052
            _Transicion(ESP.PENDIENTE_AUTORIZACION, Accion.RECHAZO_ADMINISTRACION, ESP.EN_BUSQUEDA_ALTERNATIVA),                  # CA-050
            _Transicion(ESP.PENDIENTE_FORMALIZACION, Accion.CONFIRMAR, ESP.CONFIRMADA),                                           # CA-051, CA-053
            _Transicion(ESP.EN_BUSQUEDA_ALTERNATIVA, Accion.CERRAR_POR_INICIO_EVENTO, ESP.CERRADA_INICIO_EVENTO),                 # CA-096
            _Transicion(ESP.PENDIENTE_APROBACION_CLIENTE, Accion.CERRAR_POR_INICIO_EVENTO, ESP.CERRADA_INICIO_EVENTO),
            _Transicion(ESP.PENDIENTE_AUTORIZACION, Accion.CERRAR_POR_INICIO_EVENTO, ESP.CERRADA_INICIO_EVENTO),
            _Transicion(ESP.PENDIENTE_FORMALIZACION, Accion.CERRAR_POR_INICIO_EVENTO, ESP.CERRADA_INICIO_EVENTO),
            _Transicion(ESP.EN_BUSQUEDA_ALTERNATIVA, Accion.CERRAR_POR_CANCELACION_EVENTO, ESP.CERRADA_EVENTO_CANCELADO),         # BN-008
            _Transicion(ESP.PENDIENTE_APROBACION_CLIENTE, Accion.CERRAR_POR_CANCELACION_EVENTO, ESP.CERRADA_EVENTO_CANCELADO),
            _Transicion(ESP.PENDIENTE_AUTORIZACION, Accion.CERRAR_POR_CANCELACION_EVENTO, ESP.CERRADA_EVENTO_CANCELADO),
            _Transicion(ESP.PENDIENTE_FORMALIZACION, Accion.CERRAR_POR_CANCELACION_EVENTO, ESP.CERRADA_EVENTO_CANCELADO),
        ),
        # Mensajes de rechazo existentes, sin cambios. confirmar y los cierres no los usan: confirmar devuelve la lista
        # de faltantes y los cierres en un estado final no tienen efecto (comprobación `pendiente`).
        mensajes_rechazo={
            Accion.PROPONER_ALTERNATIVA_CON_IMPACTO: lambda o: "La sustitución no está en búsqueda de alternativa.",
            Accion.PROPONER_ALTERNATIVA_SIN_IMPACTO: lambda o: "La sustitución no está en búsqueda de alternativa.",
            Accion.APROBACION_CLIENTE: lambda o: "La alternativa no requiere o no espera aprobación del Cliente.",
            Accion.RECHAZO_CLIENTE: lambda o: "La alternativa no requiere o no espera aprobación del Cliente.",
            Accion.AUTORIZACION_ADMINISTRACION: lambda o: "La autorización es posterior a la aprobación del Cliente (SE-001).",
            Accion.RECHAZO_ADMINISTRACION: lambda o: "La autorización es posterior a la aprobación del Cliente (SE-001).",
        },
        nombre="SustitucionProveedor",
    )
    del _Enum, _MaquinaEstados, _Transicion

    def _transitar(self, accion: "SustitucionProveedor.Accion") -> ESP:
        """Destino permitido por MAQUINA o TransicionNoPermitida (ErrorDominio) con el mensaje existente."""
        return self.MAQUINA.transitar(self.estado, accion)

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
        # El impacto lo decide la Specification MODIFICACION_CON_IMPACTO de E2 (ImpactoModificacion.tiene_impacto).
        accion = (self.Accion.PROPONER_ALTERNATIVA_CON_IMPACTO if alt.impacto.tiene_impacto
                  else self.Accion.PROPONER_ALTERNATIVA_SIN_IMPACTO)
        destino = self._transitar(accion)                 # valida antes de modificar el agregado
        self.alternativas.append(alt)
        self.costo_adicional = costo_adicional
        self.estado = destino

    def _reemplazar(self, **cambios):
        a = self.alternativas[-1]
        self.alternativas[-1] = AlternativaPropuesta(**{**a.__dict__, **cambios})

    def registrar_decision_cliente(self, d: Decision) -> None:
        destino = self._transitar(self.Accion.APROBACION_CLIENTE if d.aprobada else self.Accion.RECHAZO_CLIENTE)
        self._reemplazar(decision_cliente=d)
        self.estado = destino
        if not d.aprobada:                                               # CA-054: se vuelve a buscar
            self._registrar(AlternativaRechazadaPorCliente(self.id, d.fecha, proveedor_id=self.alternativas[-1].proveedor_id))

    def registrar_autorizacion(self, d: Decision, fecha_evento: datetime) -> None:
        """Si la autorización llega después del límite ordinario (3 días hábiles antes del evento), el costo
        adicional debe pagarse y verificarse antes de confirmar, sin considerarse vencido (SE-001, CA-052)."""
        destino = self._transitar(self.Accion.AUTORIZACION_ADMINISTRACION if d.aprobada
                                  else self.Accion.RECHAZO_ADMINISTRACION)
        self._reemplazar(autorizacion_administracion=d)
        self.estado = destino
        if d.aprobada:
            self.aprobada_despues_del_limite = d.fecha > restar_dias_habiles(fecha_evento, 3)
        else:                                                            # CA-050: se vuelve a buscar
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
        if not faltan:                                   # la máquina solo se consulta con todos los requisitos cumplidos
            self.estado = self._transitar(self.Accion.CONFIRMAR)
            self._registrar(SustitucionProveedorConfirmada(self.id, ahora, evento_ref=self.evento_id,
                                                           servicio_contratado_id=self.servicio_contratado_id,
                                                           proveedor_id=self.alternativa_vigente.proveedor_id))
        return faltan

    def cerrar_por_inicio_evento(self, ahora: datetime) -> None:
        if not self.pendiente:                           # estados finales: sin efecto
            return
        destino = self._transitar(self.Accion.CERRAR_POR_INICIO_EVENTO)
        self._cerrar(destino, CausaCierreSolicitud.INICIO_EVENTO, "El reemplazo no se concretó", ahora)
        self._registrar(SustitucionProveedorCerradaPorInicioEvento(self.id, ahora, evento_ref=self.evento_id))

    def cerrar_por_cancelacion_evento(self, ahora: datetime) -> bool:
        """BN-008. Valida con la máquina antes de modificar el agregado y delega en _SolicitudBase, que conserva el
        resultado actual: False sin cambios en un estado final, True al cerrar. Este cierre no emite Domain Event."""
        if self.pendiente:
            self.MAQUINA.validar(self.estado, self.Accion.CERRAR_POR_CANCELACION_EVENTO)
        return super().cerrar_por_cancelacion_evento(ahora)
