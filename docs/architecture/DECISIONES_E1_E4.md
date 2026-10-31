# Decisiones E-1 a E-4 — implementación y estado de aprobación

Registro de las cuatro decisiones funcionales que el equipo eligió después de la auditoría final (`CIERRE_AUDITORIA_FINAL.md`, sección E). Fecha de implementación: 2026-10-25. El cierre de alcance (`Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md`) no se modificó.

**Qué es una regla aprobada y qué es una decisión del equipo.** Solo E-1 aplica una regla ya aprobada en las fuentes (GL-060 / C-15). E-2, E-3 y E-4 son **decisiones de implementación del equipo**: ninguna fuente original (BRD, User Stories, glosario, cierre de alcance, BPMN, matriz) las exige.

## Quién decidió qué, y qué aprobación externa falta

| Decisión | Selección registrada | Respaldo en las fuentes | Aprobación externa |
|---|---|---|---|
| E-1 · GL-060 en todos los plazos en días hábiles | Seleccionada por el equipo en la conversación de trabajo del 2026-10-25 (opción A) | **Sí:** GL-060 y C-15 del cierre de alcance aprobado | No hace falta para la regla (ya aprobada). Falta la aprobación del método de validar el oráculo (ver abajo) |
| E-2 · el evento de la solicitud debe ser el del contrato | Seleccionada por el equipo (opción A), igual fecha | **No.** Ninguna fuente la exige; es una decisión de implementación | Sin evidencia de aprobación de la docente o de una responsable externa. **Pendiente** si el curso la exige |
| E-3 · suma de pagos parciales para el 30 % | Seleccionada por el equipo (opción A) | **No.** GL «anticipo», CA-019, CA-107 y CA-108 no tratan la suma | Ídem: **pendiente** |
| E-4 · pago menor al 30 % tras liquidar = adicional | Seleccionada por el equipo (opción B) | **No** para este escenario exacto (B-3/B-4 respaldan solo que el excedente no se devuelve ni se aplica al saldo) | Ídem: **pendiente** |
| Método de validar el oráculo con esperados derivados de las reglas | Aprobado por el equipo en la conversación del 2026-10-25, con condiciones (JSON intacto; sin dejar la suite en rojo; esperados sin código de producción) | **No:** el cierre §6 no define un procedimiento para E-1/E-3/E-4 y dice «No se edita el JSON de referencia» | Sin evidencia de aprobación externa; **pendiente** si el curso la exige |
| Control de comprobante repetido (añadido con E-3/E-4) | Adoptado por el equipo como control de integridad para no contar un pago dos veces | **No** como regla de negocio. Es la forma de cumplir «no contar dos veces un pago» y «el reintento no duplica»; las fuentes no hablan de comprobantes duplicados | **Pendiente** |
| Fecha efectiva de un pago parcial | Tratamiento adoptado por el equipo (ver E-3) | **Parcial:** BN-009 (la fecha en que el Cliente efectuó el pago, según el comprobante, decide el plazo), H-10 y CA-021 respaldan medir por esa fecha; **no** definen si un parcial tardío cuenta para las 24 horas | **Pendiente** para esa pregunta concreta |

**«Seleccionada por el equipo» significa** que la decisión consta en la conversación de trabajo con quien dirige la implementación; no existe un documento firmado ni evidencia de que la docente o una responsable externa las haya aprobado, y este repositorio no lo afirma.

| Decisión | Estado del código | Estado de aprobación |
|---|---|---|
| E-1 · GL-060 / C-15 en todos los plazos en días hábiles | Implementada y probada | Regla ya aprobada en las fuentes; el oráculo histórico se conserva y se valida por reglas (ver abajo) |
| E-2 · el evento de la solicitud debe ser el del contrato | Implementada y probada | Decisión del equipo, **sin aprobación externa registrada** |
| E-3 · el anticipo mínimo se puede alcanzar con pagos parciales | Implementada y probada | Decisión del equipo, **sin aprobación externa registrada** |
| E-4 · pago menor al 30 % después de liquidar el anticipo | Implementada y probada | Decisión del equipo, **sin aprobación externa registrada** |

No hay migraciones nuevas: los cambios no tocan el esquema (Alembic sigue en 0004). Ver «Datos existentes».

---

## E-1 · GL-060 / C-15 aplicado a todos los plazos en días hábiles

**Regla (GL-060, C-15).** Los días hábiles son de lunes a viernes, con los festivos contados como hábiles. El día de partida no cuenta. El límite de un plazo en días hábiles es **exclusivo**: vence a las 00:00 del día siguiente al último día del plazo, y a esa hora ya está fuera de plazo. Los límites en T y en las ventanas de horas siguen siendo inclusivos.

**Los seis plazos (todos conformes ahora).** Evidencia: `tests/evidencias/auditoria-plazos-gl060-e1-aplicado-20261025.txt` (antes: `auditoria-plazos-gl060-20261024.txt`, que mostraba 1 de 6).

| Plazo | Antes | Ahora (ejemplo: firma jue 01/10 10:00; evento vie 20/11 18:00; cierre vie 20/11 15:30) |
|---|---|---|
| Anticipo (3 días hábiles tras la firma) | mar 06/10 10:00, inclusivo | mié 07/10 00:00, exclusivo |
| Seguimiento del anticipo | mar 06/10 10:00 | mié 07/10 00:00 |
| Saldo (3 días hábiles antes del evento) | mar 17/11 18:00 | mié 18/11 00:00, exclusivo |
| Límite de la sustitución con costo adicional | mar 17/11 18:00 | mié 18/11 00:00 |
| Devolución del anticipo (decisión A) | sáb 28/11 00:00 (ya conforme) | sáb 28/11 00:00 |
| Devolución por solicitud no realizada (SE-012) | vie 27/11 15:30, inclusivo | sáb 28/11 00:00, exclusivo |

**No se extiende** a plazos en horas o días naturales: las 24 horas de cambios, servicios adicionales y cobro (inclusivas), los cinco días naturales del servicio adicional y los siete del cambio tardío, ni T. Hay pruebas que lo comprueban.

**Cómo está hecho.**
- `PlazoPago` tiene `exclusivo` (por omisión falso). `dias_habiles()` y `dias_habiles_antes_de()` crean plazos exclusivos y `vencido()` / `incluye()` respetan el límite. `src/domain/valores.py`.
- `limite_exclusivo_dias_habiles_antes()` es la versión «antes del evento» (saldo y sustitución).
- `Devolucion.fecha_limite` usa el mismo cálculo para SE-012 y para el anticipo. `src/domain/estado_cuenta.py`.
- El seguimiento del anticipo (`FormalizarContratacionService.dar_seguimiento_anticipo_pendiente`) y el límite de la sustitución (`SustitucionProveedor.registrar_autorizacion`) usan el mismo límite.
- Al leer de PostgreSQL, `exclusivo` se deduce del concepto (anticipo, saldo, sustitución): no se guarda una columna nueva.

**Pruebas.** `tests/test_plazos_dias_habiles_gl060_e1.py` (16): cada plazo en el último segundo y a las 00:00, fin de semana, cruce de mes y año, persistencia en PostgreSQL y no extensión a plazos naturales. Se actualizaron las pruebas que fijaban el límite antiguo (`test_h09_plazo_devolucion`, `test_h10_anticipo_liquidado`, `test_h03_consultas_administracion`, `test_etapa9_casos_de_uso`, `test_reglas_anticipo_decisiones_abc`) y las huellas de clases protegidas por E3E/E3F de `SustitucionProveedor` (como ya se hizo con E3F.1).

### Oráculo histórico: estado y bloqueo

- `tests/referencias/comportamiento_estado_cuenta_v8_e3c.json` **no se editó** (SHA-256 `d98b4cff…`, igual al de antes). Tampoco se desactivó ninguna prueba.
- El cierre (§6) permite recalcular los esperados **solo** con su procedimiento, que fija nuevos esperados para las decisiones A, B y C (R1–R12 y H-10). **No define esperados para E-1, E-3 ni E-4**, y termina con «No se edita el JSON de referencia». Por tanto **no existe un procedimiento autorizado para sustituir el oráculo con estas decisiones**.
- Consecuencia y solución adoptada (método indicado y aprobado en la conversación de trabajo del 2026-10-25; no hay un registro formal de esa aprobación y no equivale a aprobar un recálculo del oráculo): `ConservacionDelComportamiento.test_resultados_identicos` **se conserva** y compara cada una de las 1203 claves con su *esperado* = entrada del oráculo + solo los cambios que ordenan las reglas. Toda clave que ninguna regla toque debe ser idéntica al oráculo. Las 1203 claves difieren del oráculo porque el oráculo registra el plazo del anticipo en cada estado (E-1).
- Los esperados (`tests/apoyo_esperados_oraculo.py`) no usan código de producción: calendario por fórmula cerrada para E-1; cambios específicos de OB-A para H-10; y para E-3/E-4 el estado del pago, los importes acumulados, los eventos, las devoluciones y las consultas derivadas, calculados desde los pagos esperados.
- Recuento exacto (`diferencias-oraculo-e1-e4-20261025.txt`, con los identificadores): 1203 claves = 1094 solo E-1 + 67 E-1 + E-3/E-4 + 2 E-1 + E-3/E-4 + H-10 + 40 E-1 + H-10. Por regla: E-1 1203, E-3/E-4 69, H-10 42 (las 42 de H-10 coinciden con las ya documentadas antes). Las «1204 subpruebas fallidas» del informe provisional eran las 1203 claves más la aserción final `afectadas == 42`, que fallaba aparte.
- `tests/test_oraculo_diferencias_e1_e4.py` comprueba que la validación es rigurosa: el oráculo no cambió (SHA-256 `d98b4cff…`), los recuentos son exactos, el calendario independiente coincide con el del dominio en dos años de fechas, y una diferencia inesperada se detecta (alteraciones del resultado y perturbaciones deliberadas del dominio).
- Para que la diferencia no quede sin explicar, `scripts/comparar_oraculo_decisiones_e1_e4.py` (solo lectura) y `tests/test_oraculo_diferencias_e1_e4.py` la contabilizan. Resultado (`tests/evidencias/diferencias-oraculo-e1-e4-20261025.txt`): de 1203 claves, **1094** difieren solo por un plazo en días hábiles (E-1), **69** además por E-3/E-4 y **40** además por H-10 (diferencia ya documentada antes); **0 sin explicar**. La prueba verifica además que cada plazo nuevo es exactamente el de la fórmula de GL-060 y que los plazos de horas no cambian.
- **Qué sigue pendiente de autorización:** el cierre (§6) no define un procedimiento para recalcular el oráculo con E-1/E-3/E-4. Mientras no exista, el oráculo queda como referencia histórica inmutable y los esperados por regla son la validación. Si la responsable prefiere recalcularlo, debe definir ese procedimiento.
- Nota para la responsable: la regla de la devolución SE-012 se aplicó con el mismo cálculo de GL-060 porque C-15 lo exige para «las devoluciones»; A-6 dice que el anticipo no sigue la *referencia* de SE-012, no que SE-012 conserve la hora.

---

## E-2 · coherencia solicitud–contrato–evento

**Decisión del equipo, sin aprobación formal.** Antes de registrar una solicitud de cambio, una de servicio adicional o una sustitución, el evento de la solicitud debe ser el del contrato relacionado.

- Rutas: `POST /solicitudes-cambio`, `POST /solicitudes-servicio-adicional`, `POST /sustituciones`.
- Si no coinciden: HTTP **422** `rechazo_de_negocio` («El evento de la solicitud no coincide con el evento del contrato…»), antes de crear nada. Es la convención de la API para una regla de negocio.
- Se hace en los servicios de aplicación (`_exigir_evento_del_contrato`, solo lectura por el repositorio de contratos). No hay claves foráneas nuevas entre raíces. Un contrato inexistente conserva su rechazo anterior.
- Pruebas: `tests/test_coherencia_solicitud_contrato_evento.py`, en memoria y en PostgreSQL: evento coincidente (permitido), evento distinto en ambos sentidos (rechazado), las tres rutas, y que ni los estados de cuenta, contratos, eventos, solicitudes, pagos, obligaciones ni el Outbox cambian al rechazar. La prueba de riesgo anterior se sustituyó por esta.

---

## E-3 · el anticipo mínimo puede alcanzarse con pagos parciales

**Decisión del equipo, sin aprobación formal.** El mínimo sigue siendo el 30 % del costo del contrato (ejemplo: $10,000 → $3,000), pero lo pueden cubrir varios pagos válidos del mismo contrato (ejemplo: $1,500 + $1,500).

**Cómo estaba y cómo queda.**
- Antes, `registrar_y_verificar_pago` marcaba como `Importe incorrecto` cualquier pago de anticipo menor al mínimo y no lo contaba nunca.
- Ahora un pago menor al mínimo sobre un anticipo **Pendiente** queda Registrado o Verificado como pago parcial. La obligación sigue Pendiente hasta que la suma de los pagos **Verificados** alcance el mínimo (`pagado >= importe`); entonces se liquida.
- Cuentan solo los pagos de **esa** obligación (un contrato, un estado de cuenta). No cuentan los pagos en `Importe incorrecto` (quedan solo históricos, sin modificarse) ni los de otras obligaciones.
- **Pago repetido:** un pago con el mismo comprobante sobre la misma obligación se rechaza («Ya existe un pago registrado con ese comprobante para esta obligación»). Es un control de integridad nuevo que el equipo añadió con E-3/E-4; también requiere aprobación. Un comprobante igual al de un pago histórico `Importe incorrecto` sí se acepta (la corrección es un pago nuevo).
- Los estados de pago siguen siendo tres (Registrado, Verificado, Importe incorrecto): no hay estados rechazado/anulado/duplicado/devuelto. Un pago devuelto se refleja en la devolución, no en su estado.
- La transición `RECHAZAR_IMPORTE` y el estado `Importe incorrecto` se **conservan** (mapa de dominio y pagos históricos), pero ningún método del dominio los dispara ya.

**Plazos y fecha efectiva (las fuentes no lo definen; no se inventó una regla, se documenta el tratamiento).**
- El pago se mide por la fecha en que el Cliente lo **efectuó** (`Pago.fecha`, BN-009), no por el registro ni la verificación.
- Para **liquidar** la obligación cuentan todos los pagos verificados, también los efectuados después del plazo de tres días hábiles (H-10, ya existente).
- Para las **24 horas posteriores al contacto** (confirmar o cerrar la contratación) solo cuentan los efectuados a más tardar en el límite (inclusivo). Un pago parcial dentro de ese plazo **no evita el cierre**: hace falta que lo efectuado a tiempo sume el mínimo. `anticipo_verificado`, `anticipo_efectuado_hasta` y `anticipo_recibido` pasaron de «hay algún pago» a «los pagos suman el mínimo».
- Pregunta abierta: si un pago parcial tardío debería contar para el plazo de 24 horas es una cuestión que las fuentes no resuelven; el tratamiento anterior es el más cercano al texto de BN-009 y CA-021.

**Excedente.** Si los parciales superan el mínimo (p. ej. $1,500 + $2,000), la obligación se liquida con $3,000; los $500 quedan registrados, sin aplicarse al saldo (B-4) ni devolverse (B-3).

**Pagos históricos.** No se modifican ni se reclasifican. Los que estaban en `Importe incorrecto` siguen así y no suman.

**Pruebas.** `tests/test_anticipo_pagos_parciales_e3_e4.py`: dos pagos de $1,500; tres de $1,000; $2,999.99 más $0.01; superar el 30 %; importes insuficientes; pago repetido; mismo pago verificado dos veces; contratos distintos; pago histórico incorrecto; plazo de 24 horas (dentro, fuera, exacto) y pagos tardíos; HTTP y persistencia en PostgreSQL con contenedor nuevo; Outbox (un `PagoVerificado` por pago, sin duplicados); concurrencia (dos registros simultáneos del mismo pago dejan uno).

---

## E-4 · pago menor al 30 % después de liquidar el anticipo

**Decisión del equipo, sin aprobación formal.** Con el anticipo ya liquidado, una nueva transferencia válida del mismo contrato no se marca como incorrecta por ser menor al 30 %: se registra y verifica como pago adicional.

- Ejemplo: contrato $10,000; anticipo liquidado $3,000; nuevo pago $1,000 → Verificado; la obligación sigue Liquidada; `anticipo_aplicado` sigue en $3,000; `anticipo_excedente` pasa a $1,000; sin devolución; el saldo sigue en $7,000 y sin pagos.
- No se devuelve automáticamente, no se aplica al saldo (B-4), el reintento con el mismo comprobante se rechaza y no modifica la liquidación ni los pagos anteriores.
- **Diferencia con E-3:** antes de liquidar, los pagos válidos se acumulan hasta el 30 %; después, un pago menor es adicional. Es el mismo código (`registrar_y_verificar_pago`), sin una rama distinta: la obligación Liquidada simplemente no vuelve a transitar.
- Si la contratación ya se cerró sin confirmar, sigue vigente la decisión A (A-1, A-3): el pago se registra y se devuelve.

**Pruebas.** `tests/test_anticipo_pagos_parciales_e3_e4.py` (clases E4_ y la prueba de contraste con E-3): estado de la obligación, pagos, devoluciones y saldo antes y después.

---

## Resultados medidos tras implementar E-1 a E-4

1306 pruebas aprobadas (0 fallos, 0 errores, 0 omitidas) en el equipo y en Docker; cobertura de 98,82 % de sentencias (5379 de 5443) y 95,85 % de ramas (1016 de 1060). Evidencias en `tests/evidencias/*e1-e4*-20261025.txt`; pruebas de humo por HTTP en `tests/evidencias/humo-api-*-20261025.txt`.

## Datos existentes y migraciones

- **Sin migración.** Nada cambió en el esquema. `exclusivo` se deduce del concepto al leer.
- Las obligaciones ya guardadas en la base de desarrollo (los eventos de demostración) conservan su fecha de vencimiento antigua (con hora de partida); no se recalcularon, porque no hay una estrategia aprobada para modificar datos históricos. Al leerlas se tratan con el límite exclusivo sobre esa fecha. Es una diferencia de un instante, sin efecto en los datos de demostración.
- Los pagos históricos en `Importe incorrecto` no se tocan.

## Diagrama de estados del pago

`diagramas/dominio/mapa-dominio.drawio` (páginas «00 — Todas las vistas» y «04 — Detalle C») conserva el estado «Importe incorrecto» y su transición desde «Registrado», porque el dominio los conserva: existen pagos históricos en ese estado y la prueba `test_coherencia_con_el_mapa_de_dominio` exige que las flechas coincidan con las tablas de transición. La etiqueta de esa flecha decía «anticipo inferior al 30 %: se solicita corrección y nuevo pago (CA-019)», que describe el comportamiento anterior; ahora dice «histórico: anticipo < 30 %, se pedía / corregir; hoy: parcial/adicional (E-3/4)». Un primer intento de añadir una nota aparte se descartó al comprobar por coordenadas que se solapaba con esas etiquetas.

**Límites:** el cambio se hizo sobre el XML y **no se pudo renderizar** (no hay draw.io en el entorno; solo se comprobó que el XML es válido y que la etiqueta coincide con el espacio de la original, con una línea unos caracteres más larga). `mapa-dominio.pdf` **no se regeneró** por la misma razón y todavía muestra la etiqueta anterior (anterior a E-3/E-4); debe exportarse de nuevo desde draw.io. Quitar el estado o la transición del dominio exigiría decidir cómo representar los pagos históricos; no se hizo.

## Qué requiere aprobación formal

1. **E-2, E-3, E-4:** confirmar o rechazar las tres decisiones, incluido el control de comprobante repetido.
2. **Oráculo histórico:** aprobar el método de validación por esperados derivados de las reglas (arriba); E-1 en sí es una regla ya aprobada.
3. **Fecha efectiva de un pago parcial** respecto de las 24 horas (tratamiento documentado en E-3).
4. Regenerar `mapa-dominio.pdf` y revisar visualmente el diagrama anotado.

## Texto de las fuentes que E-3 interpreta (revisión documental del 2026-10-28)

Al cotejar los documentos aprobados se encontró un texto que esta decisión **interpreta** y que el registro anterior no citaba:

- **Glosario, GL-011 (Anticipo):** «Un importe inferior al 30 % debe corregirse; uno superior cubre el requisito, sin devolución automática ni aplicación automática del excedente…».
- **BRD (anticipo):** «Si el monto es inferior al 30 %, debe informar al Cliente para que realice la corrección correspondiente y volver a verificar el anticipo.»

Las fuentes no dicen si esa «corrección» es **un pago complementario que se suma** al ya registrado (lectura que implementa E-3) o **un pago nuevo que sustituye** al anterior (comportamiento previo: el pago menor quedaba «Importe incorrecto» y se corregía con otro pago por el importe completo). Tampoco usan la palabra «sumar» ni «parcial». Por eso E-3 sigue siendo una **decisión del equipo sin respaldo explícito** y queda **pendiente de aprobación externa**; no se modificó el glosario ni el BRD (documentos aprobados). Si la responsable del proyecto elige la lectura «sustituye», hay que revertir E-3 y E-4 en una tarea separada de código y pruebas.
