# ADR-008: Llegada de T por el trabajador, cierre por T y pago tardío del saldo (D-2, D-3)

- **Estado:** Aceptada por el equipo (2026-10-28). **Las decisiones marcadas como internas no tienen aprobación externa registrada**
- **Fecha:** 2026-10-28
- **Relacionada con:** ADR-002 (raíces de agregado), ADR-004 (Outbox), ADR-006 (concurrencia optimista), ADR-007 (decisiones E-1 a E-4); no sustituye ni deja obsoleta ninguna decisión anterior
- **Detalle, fuentes y resultados:** [`../architecture/CIERRE_AUDITORIA_FINAL.md`](../architecture/CIERRE_AUDITORIA_FINAL.md), secciones J, M, N, O, P (vencimiento de hecho y reloj de negocio) y Q (validación manual T-21, T-23 y T-24 y última ejecución de la suite)

## Contexto

La revisión de concordancia del 28/10/2026 encontró que el código no cumplía reglas aprobadas: un pago del saldo posterior a su límite lo liquidaba (C-06, CA-113; el cierre de alcance §8 ya lo registraba como brecha) y no existía el inicio automático en T ni el cierre sin contratación del Evento `En gestión` (C-01, CA-109 a CA-111), además de aceptarse la confirmación de la contratación después de T (CA-110).

## Decisión

**D-2 — pago tardío del saldo (regla aprobada: C-06 / ND-29, GL-049, CA-113, BN-005)**

1. Un pago del saldo con **fecha efectiva** posterior a su límite se registra y se verifica, cuenta para la regularización, pero **no liquida** la obligación (`EstadoCuenta._destinos_verificacion`, `_pagado_para_liquidar`). El registro y la verificación posteriores no cambian el plazo (BN-005, GL-046).
2. `registrar_vencimiento_saldo` cuenta solo lo pagado dentro del plazo: un saldo pagado tarde puede registrarse como vencido.
3. El anticipo (H-10) y el costo de una sustitución concretada después del límite (GL-012) conservan su excepción.
4. La consulta de pagos informa `plazoVencido` por obligación (CA-023).
5. **Vencido es un hecho (GL-049, SE-006):** el bloqueo de solicitudes nuevas usa `EstadoCuenta.saldo_vencido_en(ahora)` —plazo terminado sin que lo pagado dentro del plazo cubra el saldo, sin pago a tiempo pendiente de verificación—, con o sin registro previo del vencimiento. El registro (`registrar_vencimiento_saldo`) sigue siendo el acto formal que habilita el protocolo de cobro y la regularización. *(Corrección del 28/10/2026: la primera versión usaba solo el estado registrado.)*

**D-3 — llegada de T (regla aprobada: C-01, C-02, BN-009, BN-010, GL-032, GL-033, CA-109, CA-110, CA-111)**

1. El **trabajador** aplica la llegada de T en cada ciclo, antes de despachar el Outbox (`GestionCierreEventoService.procesar_eventos_vencidos`, `trabajador_outbox.ejecutar`): un Evento `En organización` inicia; uno `En gestión` se cierra sin contratación. Un evento por transacción; un fallo en uno se registra y no impide los demás ni el ciclo siguiente; la repetición no tiene efecto (máquinas de estado idempotentes y consulta que deja de devolver lo ya procesado). **Reloj de negocio común (TP-06, aprobado en el cierre de alcance):** la API, el trabajador y el Outbox usan `application.reloj.reloj_negocio`, la hora de pared de `America/Mexico_City` sin zona (antes `datetime.now()`, es decir, UTC dentro de los contenedores, lo que desfasaba 6 horas plazos, límites y T). No se convierte ninguna fecha almacenada ni recibida. Reloj inyectable para pruebas.
2. `POST /eventos/{id}/inicio` aplica la misma regla.
3. *Decisión interna:* al llegar T se cierran el contrato `En preparación` **y el `Firmado`** (nueva acción `CERRAR_POR_INICIO` en `MAQUINA_CONTRATO`); su `ProcesoContratacionCerrado` reutiliza las reacciones existentes (Evento `Cerrado sin contratación`, anticipo Pendiente → Sin efecto y devolución del recibido, decisión A). Sin contrato abierto se cierra solo el Evento. Las fuentes dicen «contrato no firmado» pero mencionan un anticipo recibido, que solo existe con el contrato firmado.
4. *Decisión interna:* se avisa a Cliente, Coordinador y Administración.
5. D-3b: la confirmación con `ahora >= T` se rechaza (CA-110, GL-032: «la contratación ya no puede confirmarse»); T es inclusivo.
6. Si al llegar T el contrato ya está `Contratación confirmada` pero la reacción que pasa el Evento a `En organización` todavía no se aplicó, no se cierra nada: el Evento pasa a `En organización` por esa reacción y el ciclo siguiente lo inicia.
7. Solicitudes pendientes (C-02, CA-111; sin cambio de código en D-3): el inicio publica `EventoIniciado` y su reacción cierra cada cambio, servicio adicional y sustitución no confirmados como «Cerrada por inicio del evento», una transacción por solicitud; después se aplica SE-012 (cobros pendientes exclusivos → Sin efecto y, con el Evento no cancelado, devolución de lo recibido). Lo confirmado antes de T se aplica aunque su reacción llegue después (BN-006). Un Evento que llega a T `En gestión` no tiene solicitudes en trámite: cambios y servicios adicionales exigen la contratación confirmada (CA-039, CA-101).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Evaluación perezosa (aplicar T al leer o escribir) | Rompe la separación comando/consulta y deja sin cerrar a los eventos que nadie toque |
| Solo la operación explícita `POST /inicio` | No es «automático» (C-01, BN-010, CA-109) |
| Mantener el registro manual del inicio y modificar GL-032 | Exigiría cambiar reglas aprobadas |
| Considerar vencido por hecho el saldo en `saldo_vencido_sin_regularizar` | Obliga a rediseñar la regularización (la transición Pendiente → Vencida es explícita) |

## Consecuencias

- El trabajador, hasta ahora solo despachador del Outbox, también procesa eventos por fecha; debe ejecutarse al menos un trabajador. El índice `ix_evento_fecha_hora` ya existe (sin migración nueva; Alembic sigue en 0004).
- `Contrato` gana dos transiciones (`En preparación → Cerrado sin confirmar` y `Firmado → Cerrado sin confirmar` por T); el mapa de dominio ya recogía la primera.
- Las 48 claves del oráculo histórico del grupo R12 cambian y se validan con la regla D-2 de `tests/apoyo_esperados_oraculo.py`; el JSON del oráculo no se editó.
- Decisiones internas sin aprobación externa: contrato `Firmado` cerrado por T y avisos a Cliente, Coordinador y Administración. El reloj (America/Mexico_City) y el vencimiento de hecho no son decisiones internas: aplican TP-06, GL-049 y SE-006.
- Comprobación (29/10/2026, resultados informados por el equipo; capturas fuera del repositorio): en T-24 el trabajador inició automáticamente un Evento `En organización` al llegar su hora y el cambio posterior se rechazó con HTTP 422 (CA-039); en T-23, con la contratación confirmada y el saldo todavía no vencido, el servicio adicional con menos de cinco días naturales quedó `No procedente`. La última ejecución de la suite registrada (1415 pruebas, Docker, con cobertura) está en `tests/evidencias/ejecucion-docker-final-20261028-202102.txt`.

## Revisión del 29/10/2026 (D-3, CA-109 y terminología)

Motivo: reconciliar los documentos activos con las decisiones de este ADR. No cambia código ni ninguna regla aprobada; las interpretaciones del equipo **no tienen aprobación externa**.

1. **D-3, contrato Firmado al llegar T:** se mantiene la decisión interna del punto 3. Se añadió una nota fechada en el BRD y las historias de usuario (CA-110), y se actualizó el BPMN SP-02 y el maestro («contrato En preparación o Firmado, Cerrado sin confirmar (D-3)»); la redacción aprobada que nombra solo el contrato no firmado se conserva.
2. **CA-109 frente a GL-015 / SE-004:** interpretación del equipo: «no se podrán … registrar nuevos servicios adicionales» significa que desde T no se tramita ninguno; la solicitud se registra como `No procedente` (motivo: el Evento ya inició), se informa al Cliente y no genera cobro, que es lo que hace el código. Es una lectura de redacción, no una regla nueva.
3. **Terminología:** `No procedente` es el resultado de una solicitud de servicio adicional registrada que incumple un requisito (Evento cancelado o iniciado, menos de cinco días naturales, sin alternativa a tiempo). `Cerrada por inicio del evento` es el estado de una solicitud de cambio, servicio adicional o sustitución en trámite sin confirmar al llegar T (punto 7 de D-3). El glosario (GL-032) y los BPMN SP-03, SP-04, SP-05 y maestro que decían «se cierran como no procedentes» se leen como «Cerrada por inicio del evento».
