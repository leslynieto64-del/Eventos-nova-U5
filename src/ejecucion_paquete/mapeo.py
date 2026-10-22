"""Correspondencia entre el modelo de pruebas del paquete y el dominio de Eventos Nova, y diferencias documentadas.

El LEEME del paquete declara que su flujo, sus estados y sus reglas son un «modelo de pruebas propuesto», no
requerimientos originales, y pide: «Si difieren, documentar las diferencias y adaptar fixtures y oráculos; no
reemplazar los requerimientos propios con estas reglas». Aquí se documenta cada adaptación con su fuente.
Fuentes del equipo: BRD (`docs/unidad 2/Reporte_BRD_Corregido.docx`), User Stories y criterios en Gherkin
(`User_Stories_corregido.docx`), glosario (`Glosario_Corregido.docx`), mapa de dominio y README.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CorrespondenciaEstado:
    estado_paquete: str
    estado_dominio: str
    justificacion: str
    fuente: str


ESTADOS: Tuple[CorrespondenciaEstado, ...] = (
    CorrespondenciaEstado(
        "COTIZADO", "Evento «En gestión» con su Propuesta «En revisión del Cliente»",
        "La operación del paquete parte de una cotización. En el dominio, el Evento está En gestión mientras se "
        "prepara la propuesta o se formaliza la contratación, sin confirmarla.",
        "GL-033 (En gestión); CA-005; README E3A (tabla de Evento)"),
    CorrespondenciaEstado(
        "CONTRATADO", "Evento «En organización» con Contrato «Contratación confirmada»",
        "La contratación confirmada (contrato firmado, política comunicada y anticipo del 30 % verificado) lleva el "
        "Evento a En organización.",
        "GL-033 (En organización); BN-009; CA-019; README E3B"),
    CorrespondenciaEstado(
        "EN_PREPARACION", "Sin equivalente exacto (pregunta Q-01)",
        "En el dominio la preparación ocurre dentro de «En organización» (contratación confirmada y evento no iniciado); "
        "por posición en el flujo, el siguiente estado es «En ejecución». No se añade un estado artificial.",
        "GL-033"),
    CorrespondenciaEstado(
        "REALIZADO", "Evento «Finalizado»",
        "El evento se llevó a cabo y concluyó; se registra la fecha de finalización.",
        "GL-033 (Finalizado); BN-010; CA-094"),
    CorrespondenciaEstado(
        "CANCELADO", "Evento «Cancelado», solo desde «En organización» (diferencia D-03)",
        "En el dominio solo se cancela un evento cuya contratación fue confirmada. Una cotización que no prospera "
        "se registra como Propuesta cerrada por no aceptación o, en la contratación, como «Cerrado sin contratación», "
        "nunca como Cancelado.",
        "GL-033 (Cancelado, Cerrado sin contratación); GL-037; CA-084; CA-021; BN-008"),
)


@dataclass(frozen=True)
class CorrespondenciaAccion:
    accion_paquete: str
    esperado_paquete: str            # derivado del flujo de referencia del LEEME
    operacion_dominio: str
    esperado_dominio: str            # oráculo adaptado
    diferencia: str                  # ID de DIFERENCIAS o "—"
    fuente: str


ACCIONES: Tuple[CorrespondenciaAccion, ...] = (
    CorrespondenciaAccion(
        "aprobar", "COTIZADO → CONTRATADO (si se cumplen las precondiciones de ejemplo)",
        "CU-02: aceptar la propuesta, preparar y firmar el contrato con la política incluida, comunicar la política y "
        "registrar y verificar el anticipo del 30 %; la reacción confirma la contratación y el Evento",
        "Evento «En organización»; un ContratacionConfirmada", "D-05 (precondiciones de ejemplo)",
        "BN-009; CA-013; CA-017; CA-019; README E3B"),
    CorrespondenciaAccion(
        "cancelar", "COTIZADO → CANCELADO", "GestionCierreEventoService.gestionar_cancelacion_solicitada",
        "Rechazo «La cancelación solo procede con la contratación confirmada (CA-084).»; sin cambios ni eventos",
        "D-03", "CA-084; BN-008; GL-033"),
    CorrespondenciaAccion(
        "completar", "Excepción: completar (→ REALIZADO) no está permitido desde COTIZADO",
        "GestionCierreEventoService.finalizar_evento",
        "Rechazo «Solo puede finalizarse un evento que se realizó (CA-094).»; sin cambios ni eventos",
        "—", "CA-094; BN-010; README E3A"),
    CorrespondenciaAccion(
        "saltar_estado", "Excepción: no se puede saltar CONTRATADO", "GestionCierreEventoService.procesar_inicio_evento",
        "Rechazo «No puede iniciar un evento En gestión.»; sin cambios ni eventos",
        "— (pregunta Q-01 sobre el estado destino)", "GL-033; README E3A"),
    CorrespondenciaAccion(
        "repetir_aprobacion", "Excepción en la segunda aprobación (CONTRATADO no admite aprobar)",
        "La aprobación anterior y después FormalizarContratacionService.confirmar_contratacion otra vez",
        "Segunda confirmación aceptada sin efecto («La contratación ya estaba confirmada.»); Evento «En organización»; "
        "un solo ContratacionConfirmada", "D-04", "README E3A y E3B (repeticiones idempotentes)"),
)


@dataclass(frozen=True)
class Diferencia:
    id: str
    regla_paquete: str
    regla_dominio: str
    motivo: str
    fuente: str
    ajuste_oraculo: str
    afectados: str


DIFERENCIAS: Tuple[Diferencia, ...] = (
    Diferencia("D-01", "puede_procesarse: actor activo AND detalle no vacío AND autorización",
               "No existe: el BRD no tiene clientes activos o inactivos ni una autorización por operación",
               "Regla ilustrativa del paquete sin equivalente en los requerimientos del equipo",
               "LEEME «IMPORTANTE»; BRD; User Stories; glosario (sin esos conceptos); README E1",
               "Se evalúa como modelo de pruebas fuera del dominio; esperado derivado del texto de la regla",
               "EVE-T001 a EVE-T060"),
    Diferencia("D-02", "beneficio_referencia: preferente AND total >= 1500 AND NOT promoción",
               "No existe: el BRD no tiene clientes preferentes, promociones ni beneficios",
               "Regla ilustrativa del paquete sin equivalente en los requerimientos del equipo",
               "LEEME «IMPORTANTE»; BRD; User Stories; glosario (sin esos conceptos); README E1",
               "Se evalúa como modelo de pruebas fuera del dominio; umbral incluido (>=); esperado derivado del texto",
               "EVE-B001 a EVE-B060"),
    Diferencia("D-03", "COTIZADO → CANCELADO es una transición válida",
               "Solo se cancela un evento con la contratación confirmada; sin ella la solicitud se rechaza",
               "Regla aprobada del equipo",
               "CA-084; BN-008; GL-033 (Cancelado); CA-021 (nunca Cancelado sin contratación)",
               "Esperado adaptado: rechazo CA-084 sin cambios", "EVE-S002, EVE-S007, EVE-S012, EVE-S017"),
    Diferencia("D-04", "Repetir la aprobación desde CONTRATADO es una transición inválida (excepción)",
               "La confirmación de la contratación es idempotente: repetirla se acepta sin efecto",
               "Decisión de diseño aprobada (repeticiones idempotentes de las máquinas de Contrato y Evento)",
               "README E3A y E3B; MAQUINA_CONTRATO y MAQUINA_EVENTO (repeticiones_idempotentes)",
               "Esperado adaptado: aceptación sin efecto y un solo ContratacionConfirmada",
               "EVE-S003, EVE-S008, EVE-S018 (EVE-S013 no ejecutable, ver D-08)"),
    Diferencia("D-05", "Precondiciones de ejemplo de la aprobación: cliente_activo, fecha_disponible, anticipo_pagado",
               "anticipo_pagado ≈ anticipo del 30 % registrado y verificado; cliente_activo y fecha_disponible no existen",
               "El paquete no trae datos de anticipo ni de fecha disponible; el BRD no tiene clientes inactivos",
               "LEEME «Flujo de referencia»; BN-009; CA-019",
               "El anticipo se paga como fixture; un actor inactivo no impide aprobar en el dominio",
               "EVE-S010 (actor inactivo): coincide_con_paquete = NO; EVE-S013 también tiene actor inactivo, pero no "
               "es ejecutable (D-08)"),
    Diferencia("D-06", "Validar disponibilidad/capacidad del catálogo (habilitado, capacidad_o_stock)",
               "El dominio valida la disponibilidad de proveedores (servicios adicionales, sustituciones), no un catálogo",
               "El catálogo del paquete no forma parte del modelo del equipo",
               "LEEME «Reglas de prueba» 4; BN-004; SE-001; SE-004",
               "Se informa como observación (recurso deshabilitado, cantidad > capacidad); no cambia el veredicto",
               "Operaciones con EVE-P011 (deshabilitado): O005, O015, O020, O035, O040, O055"),
    Diferencia("D-07", "Los datos del paquete no incluyen fecha del evento, tipo, lugar ni invitados",
               "DatosEvento exige tipo, fecha y hora, lugar e invitados (CA-003); la propuesta, servicios y costo (CA-005)",
               "Fixtures necesarios para crear el Evento y la Propuesta",
               "LEEME «adaptar fixtures»; CA-003; CA-005",
               "Fecha del evento = fecha_solicitud + 60 días a las 18:00; tipo = descripción del primer recurso sin su "
               "número; lugar = ciudad del actor; 100 invitados; servicios = descripciones de los recursos; "
               "costo total = total de la operación", "Las 20 transiciones"),
    Diferencia("D-08", "Una operación COTIZADO puede no tener líneas de detalle",
               "Una propuesta sin servicios se rechaza (CA-005): la operación no puede llegar a «COTIZADO» en el dominio",
               "Regla aprobada del equipo", "CA-005",
               "La transición se registra como NO_EJECUTABLE y se comprueba el rechazo CA-005",
               "EVE-S013 (EVE-O013 sin líneas)"),
)


@dataclass(frozen=True)
class Pregunta:
    id: str
    pregunta: str
    alternativas: str
    decision_provisional: str


PREGUNTAS: Tuple[Pregunta, ...] = (
    Pregunta("Q-01", "¿A qué estado del dominio corresponde EN_PREPARACION y, por tanto, qué salto representa "
                     "«saltar_estado»?",
             "(a) Dentro de «En organización» (semántica de GL-033); (b) «En ejecución» (posición en el flujo)",
             "Se ejecuta el inicio del evento desde «En gestión» (salta la contratación); el resultado es un rechazo en "
             "ambas interpretaciones"),
    Pregunta("Q-02", "¿«completar» significa llegar a REALIZADO o completar el paso actual?",
             "(a) Llegar a REALIZADO (finalizar); (b) avanzar al siguiente estado (equivaldría a «aprobar»)",
             "(a): se ejecuta la finalización, porque «aprobar» ya cubre el paso COTIZADO → CONTRATADO"),
    Pregunta("Q-03", "¿Qué resultado espera el docente para cada caso y transición?",
             "Comparar con los resultados de `02_Docente` cuando estén disponibles",
             "Esperados derivados del texto del LEEME y de las reglas del equipo"),
)
