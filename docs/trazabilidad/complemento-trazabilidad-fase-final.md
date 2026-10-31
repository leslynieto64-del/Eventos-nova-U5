# Complemento de trazabilidad — fase final

Este complemento **no sustituye** la matriz aprobada (`matriz-trazabilidad.xlsx`) ni el cierre de alcance
(`Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md`): registra el estado de implementación y de prueba de filas que la
matriz aprobada declara «pendiente de implementación». Una regla aprobada, una regla implementada y una regla con prueba
aprobada son tres estados distintos; aquí se indican por separado.

## Decisiones A y B (Etapa 1)

| Fila de la matriz aprobada | Regla (cierre aprobado) | Implementación | Pruebas | Resultado |
|---|---|---|---|---|
| BN-009 / BN-005 — Devolución del anticipo por contratación cerrada sin confirmar (decisión A) | A-1 a A-6, C-04, C-11 | `EstadoCuenta.aplicar_cierre_contratacion`, `_devolver_anticipo`, `Devolucion.fecha_limite` (tipo `ANTICIPO_CONTRATACION_CERRADA`), `limite_exclusivo_dias_habiles`; reacción `ReaccionesPagos.al_cerrarse_proceso_contratacion`; migración `0003` | `test_reglas_anticipo_decisiones_abc` (clases `A_*`), `test_persistencia_devolucion_anticipo`, `test_h10_anticipo_liquidado` | Implementada y probada |
| BN-009 — Anticipo superior al 30 % (decisión B) | B-1 a B-5, C-03 | `EstadoCuenta.registrar_y_verificar_pago` (rechaza solo importes menores al mínimo), `anticipo_recibido_verificado`, `anticipo_aplicado`, `anticipo_excedente`; el saldo solo descuenta lo aplicado | `test_reglas_anticipo_decisiones_abc` (clase `B_*`) | Implementada y probada |
| (cancelación del Evento, decisión C) | C-1 a C-4, C-12 | Sin cambios de código: la cancelación no crea devoluciones | `test_reglas_anticipo_decisiones_abc` (clase `C_*`) | Probada (comportamiento ya existente) |

### Interpretaciones que el responsable debe confirmar

El cierre aprobado no precisa estos puntos; se implementó la lectura mínima y se registra aquí para que no pase por regla aprobada:

1. **Pagos individuales frente a suma. [Superado por la decisión E-3 del equipo, 2026-10-25; sin aprobación formal.]** B-2 habla de «lo recibido como anticipo». Antes se evaluaba cada pago (uno menor al 30 % era «importe incorrecto»); ahora los pagos parciales válidos del mismo contrato se suman hasta el 30 % (`docs/architecture/DECISIONES_E1_E4.md`).
2. **Pago menor al mínimo sobre un anticipo ya Liquidado. [Superado por la decisión E-4 del equipo; sin aprobación formal.]** Antes era «importe incorrecto»; ahora se verifica como pago adicional (no se devuelve ni se aplica al saldo).
3. **Pago menor al mínimo recibido antes del cierre.** Se devuelve al cerrarse la contratación (T-46: «el pago de 1000 recibido como anticipo genera una devolución A de 1000»); desde E-3 ese pago queda Verificado (parcial), ya no «Importe incorrecto». Tras el cierre ya no hay importe que corregir y el pago se registra y verifica para devolverse (A-3).
4. **Plazo de SE-012. [Unificado por la decisión E-1, regla ya aprobada C-15.]** Antes conservaba la hora del cierre con límite inclusivo; ahora usa el mismo límite exclusivo de las 00:00 que la devolución del anticipo. El oráculo histórico no se editó; se valida con esperados derivados de las reglas (pendiente de aprobación formal del método).

## Operaciones HTTP (Etapa 4)

El detalle ruta por ruta está en `docs/architecture/trazabilidad-api-persistencia.md` (generado por `scripts/generar_trazabilidad_api.py`; la prueba `test_trazabilidad_api` comprueba que está al día y que cada US, CA o regla citada existe en las fuentes aprobadas). Resumen de las 60 operaciones del OpenAPI:

| Clasificación | Operaciones | Criterio |
|---|---|---|
| Negocio con fila en la matriz aprobada | 39 | Fila de la matriz que nombra el método de servicio o de consulta |
| Negocio sin fila propia en la matriz, con respaldo explícito en las User Stories, el cierre de alcance o el BPMN SP-04 | 18 | Se cita solo lo que el texto aprobado dice; ninguna historia se asignó por semejanza. La operación `POST /solicitudes-servicio-adicional/{id}/cierre-por-falta-de-pago` se respalda en CA-082 (plazo de 24 h y confirmación solo con pago verificado), US-025 y el BPMN SP-04 (compuerta «¿El Cliente efectuó el pago dentro de las 24 horas?» → «Cerrar la solicitud por falta de pago…»); ningún criterio de aceptación enumera el cierre de forma literal (auditoría final) |
| Técnica (sin historia de usuario) | 3 (`GET /`, `GET /health`, `GET /ready`) | Identificación, vida y disponibilidad del servicio |
| Administración o soporte | 0 | No hay rutas de soporte: `reabrir` eventos del Outbox es una operación manual de código, no una ruta HTTP |
| Sin respaldo documental suficiente | 0 | El generador falla si una ruta de negocio queda sin clasificar |

Brechas conocidas de la matriz aprobada (no se modificó): 18 rutas de negocio no tienen fila propia porque la matriz las agrupa por servicio o por consulta; el respaldo de esas 18 sale de las User Stories, no de la matriz.

## Riesgo de coherencia solicitud–contrato–evento (Etapa 5) — resuelto con la decisión E-2 del equipo (2026-10-25)

> **Actualización:** el equipo decidió validar la coincidencia (E-2, HTTP 422 en `POST /solicitudes-cambio`, `POST /solicitudes-servicio-adicional` y `POST /sustituciones`), pruebas en `tests/test_coherencia_solicitud_contrato_evento.py`. **Sigue sin haber una regla en las fuentes ni aprobación formal.** La descripción siguiente es la de la Etapa 5 y se conserva como antecedente.

- **Fuentes revisadas:** cierre de alcance, BRD, User Stories y glosario corregidos: ninguna exige que el evento de una solicitud sea el del contrato asociado; no existe una decisión formal posterior. Por eso **no** se implementó la validación, no se añadió una restricción SQL y no se cambiaron firmas.
- **Comportamiento actual (comprobado por HTTP):** `POST /solicitudes-cambio` y `POST /solicitudes-servicio-adicional` aceptan el evento B con el contrato de A; la solicitud queda con el estado de cuenta de A. Las referencias inexistentes sí se rechazan (D-01). Prueba: `test_riesgo_coherencia_solicitud_contrato_evento` (documenta el estado actual; no es un requisito).
- **Decisión que debe confirmar el responsable:** «¿Debe rechazarse una solicitud de cambio, de servicio adicional o de sustitución cuyo `evento_id` no coincida con el `evento_id` del contrato?». Si la respuesta es sí: validar en los tres servicios de registro (menos invasivo), opcionalmente reforzar con una FK compuesta `(estado_cuenta_id, contrato_id, evento_id)` o derivar `evento_id` del contrato; en cualquier caso hay que invertir las pruebas indicadas.
- **Aclaración de nomenclatura:** el «C-02» de `esquema-relacional-postgresql.md` es el riesgo de coherencia; la regla C-02 del cierre aprobado trata del cierre de solicitudes no confirmadas en T.

## Verificación cruzada de identificadores (2026-10-28, solo lectura)

Comprobación con expresiones regulares sobre el texto de `matriz-trazabilidad.xlsx` (con los rangos «US-001, US-002; CA-001–CA-004» expandidos) y de `docs/unidad 2/User_Stories_corregido.docx`:

- Las historias **US-001 a US-033** y los criterios **CA-001 a CA-114** de las historias aparecen todos en la matriz; no hay identificadores de la matriz que no existan en las historias. (El valor numérico 0 que detecta la expresión corresponde a un texto de las historias con el patrón `US-0`/`CA-0`, no a una historia ni a un criterio; no se investigó más.)
- La matriz aprobada **no se modificó**. No se añadió ninguna relación: la matriz relaciona 10 necesidades BN con US/CA/CU/ADR y no contiene filas por regla SE ni por término GL; esa cobertura está en la auditoría generada (`auditoria-requisitos-fase-final.md`).
- **Limitación:** la comprobación es textual; no valida que la relación BN → US/CA sea la correcta, solo que los identificadores existen en ambos lados.
- La matriz tampoco cita el ADR-007 (decisiones E-1 a E-4, 2026-10-25) porque es posterior a su aprobación; queda registrado en este complemento y en `docs/ADR/ADR-007-decisiones-funcionales-e1-e4.md`.

## Hallazgo GL-015 / C-14 / CA-101 frente a la implementación (2026-10-28, sin cambio de código) — defecto D-1 confirmado

Fuentes aprobadas que coinciden: GL-015 («solo puede registrarse cuando la contratación está confirmada»), BRD («solo podrá registrarse la solicitud si la contratación está confirmada»), cierre de alcance **C-14** y el criterio **CA-101** (US-025: con la contratación no confirmada «el Coordinador no deberá registrar la solicitud… y no evaluará el plazo mínimo ni el saldo vencido»). `GestionServiciosAdicionalesService.registrar_solicitud_servicio_adicional` (`src/application/servicios.py`) valida el evento del contrato (E-2) y que exista el estado de cuenta (se crea al firmar), y después evalúa condición temporal y saldo; **no comprueba que el contrato esté confirmado**. No existe una validación equivalente en otra parte del flujo (se revisó el servicio, el dominio de `SolicitudServicioAdicional` y las reacciones). Simulación en memoria (28/10/2026): contrato `Firmado` y Evento `En gestión` → HTTP 201 `Registrada`. La primera ejecución manual de T-23 (contrato sin confirmar) devolvió 201 `No procedente` por plazo cuando CA-101 exigía el rechazo previo. Es un defecto de implementación, no una decisión pendiente; su corrección (cambio de código y pruebas) queda para una tarea autorizada (ver `CIERRE_AUDITORIA_FINAL.md`, sección J). La auditoría generada marcaba C-14 como implementada por citar el identificador; se corrigió.

## Otros dos incumplimientos hallados (2026-10-28)

- **D-2 · C-06 / CA-113:** un pago del saldo con fecha posterior al límite lo liquida si el vencimiento no se registró (`_destinos_verificacion`). Requiere decidir qué es «vencido».
- **D-3 · C-01 / CA-109 a CA-111 / GL-032:** no hay inicio automático en T y un Evento `En gestión` no pasa a `Cerrado sin contratación` por la fecha.

Detalle, archivos y pruebas necesarias en `CIERRE_AUDITORIA_FINAL.md`, sección J.

## Estado posterior de D-1, D-2 y D-3 (2026-10-28)

- **D-1 corregido:** `registrar_solicitud_servicio_adicional` rechaza (HTTP 422) si el contrato del evento no está en «Contratación confirmada» (CA-101); 26 pruebas de regresión en `tests/test_d1_servicio_adicional_contratacion_confirmada.py`; la ruta del servicio adicional cita ahora CA-101 en `trazabilidad-api-persistencia.md`. No está desplegado en los contenedores en marcha.
- **D-2 y D-3: analizados, abiertos.** Fuentes, alternativas y decisiones pendientes en `docs/architecture/CIERRE_AUDITORIA_FINAL.md`, secciones M.2 y M.3. El cierre de alcance aprobado (§8, brecha 3) ya clasificaba el comportamiento de D-2 como brecha.

## Estado vigente de D-1, D-2 y D-3 y de la matriz (2026-10-29)

- **D-1, D-2 y D-3 corregidos** (secciones O, P y Q de `docs/architecture/CIERRE_AUDITORIA_FINAL.md`; ADR-008). La sección anterior conserva el estado del 28/10 como historial.
- **Matriz:** se actualizaron solo las columnas *Componentes de arquitectura* y *Decisiones arquitectónicas* de las filas BN-005 (saldo y regularización), BN-004/BN-005 (servicio adicional), BN-010 (inicio en T) y BN-009/BN-005 (decisiones A y B), porque describían como pendiente una implementación que ya existe o atribuían `resolverRegularizacionSaldoVencido` a otro servicio. Necesidades, reglas, historias, criterios y casos de uso no cambiaron; la relación ruta → fila de `trazabilidad-api-persistencia.md` sigue igual (39 / 18 / 3).
- **Sin cambio en las fuentes aprobadas:** el cierre del contrato `Firmado` al llegar T sigue siendo una decisión interna (C-01 y CA-110 nombran el no firmado) y la suma de anticipos parciales (E-3) sigue sin aprobación formal frente a GL-011.
- **Validación manual:** T-21, T-23 y T-24 aprobadas según los resultados informados por el equipo (CIERRE §Q.1). La matriz sigue sin columna de pruebas.
