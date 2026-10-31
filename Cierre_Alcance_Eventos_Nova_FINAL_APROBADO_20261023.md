# Cierre del alcance funcional de Eventos Nova — versión definitiva

**Fecha:** 23/10/2026
**Sustituye como referencia a:** `Cierre_Alcance_Eventos_Nova.md`, que se conserva intacto. Incorpora las decisiones de negocio **A, B y C, aprobadas**.
**Base:** `Auditoria_Alcance_Eventos_Nova_V4_1.md`; `Resolucion_Funcional_Eventos_Nova_V4_1_FINAL.md` (referencia histórica); fuentes aprobadas del proyecto:
- BRD (BN, SE, restricciones);
- User Stories y CA;
- glosario (GL);
- BPMN, mapa de dominio y matriz.

**Archivos citados que no estaban disponibles en esta sesión:** `Cierre_Alcance_Eventos_Nova_decision_A_provisional.md` y la nota `Markdown pegado(20261023-230436).md` (B-3 y B-4). Nada de este documento se atribuye a su contenido. El plazo de la devolución de A (A-6) se cotejó después con el texto de B-3, RN-42 y RN-60 de la nota histórica, conservado en la conversación de trabajo (ver la trazabilidad de A-6).

**Carácter:** cierre de alcance, no especificación. No modifica el BRD, las User Stories, los CA, el glosario, el BPMN, la matriz, el código, las pruebas ni Git. Cuando la V4.1 contradiga este cierre, prevalece el cierre.

---

## 1. Decisiones de negocio aprobadas

### A. Anticipo cuando la contratación se cierra sin confirmarse (Cerrado sin contratación)

| # | Regla aprobada |
|---|---|
| A-1 | Se devuelve el importe recibido como anticipo que no se haya aplicado a una contratación confirmada |
| A-2 | La contratación cerrada no se reabre |
| A-3 | Un pago de anticipo puede registrarse y verificarse después del cierre sin reactivar la contratación |
| A-4 | Si el Cliente desea continuar, inicia un proceso nuevo |
| A-5 | Esta devolución es **distinta** de la devolución SE-012, que corresponde a solicitudes no realizadas con el Evento vigente |
| A-6 | **Plazo:** 5 días hábiles (nota histórica B-3: «La devolución se ejecuta en 5 días hábiles (RN-42)»).<br>**Fecha de referencia** (RN-42: «desde el día posterior entre el cierre de la contratación y el registro del pago», es decir, la más tardía de las dos):<br>• pago ya registrado al cerrarse la contratación: el día del cierre;<br>• pago registrado después del cierre: el día de su registro.<br>**Vencimiento** (RN-60): al final del 5.º día hábil posterior al día de referencia; el día de referencia no cuenta. Con C-15, ese final es el límite exclusivo de las 00:00 del día siguiente.<br>La verificación del importe forma parte del plazo: verificar tarde no abre un plazo nuevo (RN-43).<br>Es la regla temporal de la devolución A, **no** la de SE-012 |

**Consecuencias directas del texto aprobado** (no son reglas nuevas):
- «Importe recibido como anticipo» incluye la parte que excediera el 30 %. Ninguna parte se aplicó a una contratación confirmada, así que A-1 la cubre por completo.
- Un anticipo que quedó Liquidado conserva ese estado (regla C-04) y también se devuelve. La contratación no llegó a confirmarse.
- La regla de integridad de C-11 rige igual: un pago no genera una devolución superior a lo recibido, y genera como máximo una.

**Trazabilidad de A-6.** Cotejado con el texto de B-3, RN-42, RN-43 y RN-60 de la nota histórica. Ese texto está en la primera versión de la resolución funcional, dentro de la conversación de trabajo, y coincide con los identificadores que cita la nota. El archivo `Markdown pegado(20261023-230436).md` no estaba adjunto como tal.

La V4.1 (tabla B.6.C-1, clase D3) usaba la misma referencia y el mismo plazo, así que no hay diferencia. La nota B-4 de esa misma versión exigía el 30 % exacto; en eso la sustituye la decisión B.

**Ejemplo** (fechas de los datos comunes de la V4.1):
- Contratación cerrada el viernes 20/11/2026 con el pago ya registrado: referencia 20/11; vence al final del viernes 27/11 (límite 28/11 a las 00:00).
- Mismo cierre, pero el pago se registra el lunes 23/11: referencia 23/11; vence al final del lunes 30/11.

### B. El 30 % es el mínimo del anticipo

| # | Regla aprobada |
|---|---|
| B-1 | El anticipo requerido es **al menos** el 30 % del costo de la propuesta aceptada, no un importe exacto |
| B-2 | Si lo recibido como anticipo supera el 30 %, el requisito del anticipo se considera cubierto |
| B-3 | Superar el 30 % no genera ninguna devolución automática |
| B-4 | El excedente no se aplica automáticamente al saldo ni a otra obligación |
| B-5 | La decisión se limita a los pagos identificados como anticipo. No se extiende a excedentes de otros conceptos ni crea un proceso general de sobrepagos |

**Consecuencias directas del texto aprobado:**
- Lo recibido como anticipo por debajo del 30 % sigue siendo un importe incorrecto que requiere corrección (BN-009, CA-019).
- El saldo del contrato original no se reduce por el excedente (B-4).

### C. No reembolso cuando el Evento está cancelado

| # | Regla aprobada |
|---|---|
| C-1 | Se aplica la política de GL-055 a los pagos relacionados con el Evento cancelado |
| C-2 | Esto incluye los excedentes del anticipo y los pagos tardíos relacionados con el Evento |
| C-3 | No se genera ninguna devolución automática en esos casos, ni nuevas clases de devolución o excepciones |
| C-4 | Se conserva la distinción entre Evento **Cancelado** (GL-055, C) y Evento **Cerrado sin contratación** (A) |

**Consecuencia directa:** A y C no se solapan.
- Un Evento solo puede quedar Cancelado desde En organización, es decir, con la contratación confirmada (GL-033; mapa de dominio).
- Un Evento Cerrado sin contratación nunca está Cancelado (BN-009: «Cerrado sin contratación, no Cancelado»).

### Diferencias entre las decisiones aprobadas y las fuentes existentes

Se declaran sin ocultarlas. Las fuentes no se modifican en esta etapa; cada una queda señalada para actualizarla más adelante.

| Decisión | Fuente | Qué dice la fuente | Diferencia |
|---|---|---|---|
| A | BN-009, SE-010, CA-021 | Describen el cierre por falta de anticipo (Cerrado sin contratación). **No mencionan** el destino del dinero recibido | A añade una devolución que las fuentes no contienen |
| A | GL-057, US-031, CA-098 | La devolución se define **solo** para solicitudes no realizadas | La devolución de A no está en esa definición. Hay que ampliar GL-057 o crear una entrada propia |
| A | SE-011, GL-033 | «Cerrado sin contratación» es un estado final del Evento | Sin diferencia: el «proceso nuevo» de A-4 es compatible |
| B | BN-009 («si el importe no corresponde al 30 % requerido»); CA-019 («comprobar que corresponde al 30 %»); SE-010 y restricciones del BRD («verificar que corresponda al 30 %») | Leídas literalmente, exigen un importe que **corresponda** al 30 % | B lo reinterpreta como un **mínimo**. Las fuentes no dicen «al menos». Es la diferencia más visible respecto del texto original |
| B | GL-012 («saldo pendiente… después de descontar el anticipo y los pagos aplicados») | No precisa si el anticipo descontado es el 30 % o todo lo recibido | Con B-4, solo se descuenta lo aplicado al anticipo. GL-012 debería precisarlo |
| B | BN-009, GL-055 y demás fuentes | No definen qué pasa con el excedente del anticipo si el Evento se realiza y finaliza | B tampoco lo define, de forma deliberada: el excedente queda registrado, sin aplicación ni devolución automáticas. **No se añade ningún proceso** |
| C | GL-055; restricción del BRD («no se realizará ningún reembolso… comprende el anticipo, los pagos del contrato original, …»); SE-012 (última frase) | No reembolso al cancelarse el Evento | Sin diferencia: C confirma la lectura literal. Las decisiones contrarias de la V4.1 (ND-06, ND-24) quedan descartadas |

---

## 2. Se conserva

| # | Regla conservada | Fuente o decisión |
|---|---|---|
| C-01 | Inicio automático en T. Un Evento todavía En gestión pasa a Cerrado sin contratación, y su contrato no firmado, a Cerrado sin confirmar | Decisión A del ejercicio; GL-033; BN-009; SE-011 |
| C-02 | Las solicitudes no confirmadas se cierran al llegar T con un único resultado. Nada se confirma después de T. Lo confirmado antes de T se aplica | Restricciones del BRD; BN-006; CA-070, CA-071, CA-096; GL-013 |
| C-03 | Anticipo:<br>• **al menos el 30 %** (B-1, B-2), en 3 días hábiles desde la firma;<br>• contacto registrado con fecha y hora, y 24 h desde ese contacto;<br>• corrección de un importe inferior al 30 % con nueva verificación;<br>• confirmación con contrato firmado, política incluida y comunicada, y anticipo verificado | BN-009; SE-010; CA-019 a CA-021; **B** |
| C-04 | Al cerrarse la contratación sin confirmar, el anticipo Pendiente pasa a Sin efecto y uno Liquidado conserva ese estado | GL-053; CA-021 |
| C-05 | Obligaciones separadas por concepto; el pago de un concepto no liquida otro; el plazo se decide por la fecha en que el Cliente pagó | BN-005; BN-009; GL-012; GL-046; CA-023; CA-026 |
| C-06 | **ND-29:** un pago del saldo efectuado después de su límite no lo liquida directamente; el saldo queda vencido y el pago cuenta para la regularización | GL-049; BN-005 |
| C-07 | Protocolo de cobro, cargos moratorios, ventana de 24 h, «Regularizado» o «No regularizado», cancelación registrada por el Coordinador, adeudo que permanece | BN-005; BN-008 |
| C-08 | Cancelación del Cliente: procede con la contratación confirmada y antes de T; en T o después se rechaza. El Coordinador la registra y revisa en una sola operación | SE-009; BN-008; CA-084 a CA-088 |
| C-09 | Al cancelarse el Evento, las solicitudes en trámite se cierran por «Evento cancelado» y las confirmadas no se cierran | BN-008 |
| C-10 | Los cobros pendientes exclusivos de una solicitud cerrada sin realizarse pasan a Sin efecto. Sin efecto nunca sale de ese estado. Un pago puede verificarse después de un cierre o de la cancelación | SE-012; CA-097; GL-053; BN-008; US-028 |
| C-11 | **Devoluciones del alcance (solo dos):**<br>(1) **SE-012:** solicitud no realizada con el Evento no cancelado. Se devuelve lo recibido exclusivamente por esa operación, en 5 días hábiles desde el cierre una vez verificado el importe (desde el registro, si el pago se registra después del cierre), con solicitud, concepto, importe, motivo, fecha y comprobante.<br>(2) **Devolución del anticipo de la decisión A.**<br>**Para ambas:** un pago no genera una devolución superior a lo recibido, y genera como máximo una | SE-012; GL-057; US-031; CA-097; CA-098; **A** |
| C-12 | No reembolso al cancelarse el Evento, registrado una vez por cancelación con la relación de los pagos. Incluye los excedentes del anticipo y los pagos tardíos | GL-055; BN-008; US-028; CA-087; **C** |
| C-13 | Consultas de pagos realizados y pendientes, fechas límite, vencimientos y devoluciones pendientes, sin las obligaciones Sin efecto | BN-007; CA-022, CA-023, CA-026, CA-058 |
| C-14 | Un servicio adicional solo puede registrarse con la contratación confirmada | GL-044; BN-004 |
| C-15 | Días hábiles de lunes a viernes, con los festivos contados como hábiles; límite exclusivo a las 00:00 del día siguiente; límites inclusivos en T y en las ventanas | GL-060 |

---

## 3. Se excluye o aplaza

| # | Elemento | Motivo |
|---|---|---|
| X-01 | ND-27: rechazo automático de una solicitud de cancelación pendiente | CA-088; resolución en una sola operación (C-08) |
| X-02 | ND-30: tratamiento especial de pagos no identificados | GL-046 |
| X-03 | ND-31: devoluciones parciales | GL-057; CA-098 |
| X-04 | ND-28: algoritmo de prioridades (P0 a P8), remanente, clase histórica e incidencias de reclasificación | Innecesarios con dos devoluciones que no se combinan sobre un mismo pago |
| X-05 | Cualquier devolución distinta de las dos de C-11: excedentes D4 (**B-3** la descarta para el anticipo), pagos posteriores D2 como clase propia y excedentes de otros conceptos | Sin fuente; B y C |
| X-06 | ND-06 y ND-24: devoluciones con el Evento cancelado | **C** |
| X-07 | Retención por no reembolso por pago y con importe | Basta C-12 |
| X-08 | ND-22: consulta específica de seguimientos de anticipo atrasados | CA-058 |
| X-09 | Tipos de intento de contacto fallido y alerta propia del plazo del anticipo | BN-009 solo exige la comunicación |
| X-10 | Alerta automática de devolución vencida | Basta la consulta (C-13) |
| X-11 | Causa de cierre para servicios adicionales heredados | Imposible con C-14 |
| X-12 | Flujo propio para un pago oportuno registrado después de «No regularizado» | Queda como nota (C-07) |
| X-13 | Rama «Vencida» del anticipo | Estado inalcanzable |
| X-14 | Proceso general de sobrepagos para conceptos distintos del anticipo | **B-5** |

**Excedentes de conceptos distintos del anticipo** con el Evento vigente: quedan fuera del alcance (X-14). El pago se registra y verifica, no liquida otros conceptos (BN-005) y no genera devolución. Con el Evento cancelado se aplica C-12.

---

## 4. Decisiones técnicas pendientes

No cambian el alcance funcional y no condicionan este cierre.

| # | Decisión | Situación |
|---|---|---|
| TP-01 | Persistencia tras reinicio | Bloqueada hasta recibir la base de datos oficial (README) |
| TP-02 | Outbox persistente | Trabajo posterior según ADR-004; hoy está en memoria |
| TP-03 | Recuperación del RLT | Con TP-01. En el alcance basta con que el procesamiento de T sea idempotente en memoria |
| TP-04 | Idempotencia de las reacciones y del procesamiento de T, en memoria | Se mantiene (ADR-004; mapa de dominio) |
| TP-05 | Referencia del pago para rechazar un registro idéntico; identificador de petición de la API | La referencia se mantiene; el identificador, con TP-01 |
| TP-06 | Zona horaria `America/Mexico_City` | Se mantiene |
| TP-07 | Suite completa con FastAPI | Pendiente del entorno |

Ya no quedan decisiones de negocio pendientes.

---

## 5. Pruebas afectadas por A, B y C y estado final de T-46 a T-72

### 5.1 Pruebas revisadas por las decisiones

| Prueba | Antes | Ahora | Resultado esperado reformulado |
|---|---|---|---|
| T-46 | Necesaria (solo estados); devolución pendiente de A | **Necesaria, reformular** | Evento Cerrado sin contratación; Contrato Cerrado sin confirmar; OB-A Sin efecto. El pago de 1000 recibido como anticipo genera **una devolución A de 1000**. La contratación no se reabre |
| T-48 | Necesaria (solo estados); devolución pendiente de A | **Necesaria, reformular** | OB-A **sigue Liquidada**. El pago de 3000 genera **una devolución A de 3000**. La liquidación no se revierte y la contratación no se reabre |
| T-55 | Pendiente de B | **Necesaria, reformular** | (a) Un único pago de anticipo de 4000 (40 %): requisito cubierto; OB-A Liquidada; **no** queda como importe incorrecto; sin devolución; OB-S sigue en 7000.<br>(b) Dos transferencias de anticipo de 3000 con ID-TR distintos: OB-A Liquidada; la segunda se registra y verifica; sin devolución; no se aplica al saldo |
| T-57 | Pendiente de A | **Necesaria, reformular** | Contratación cerrada en T con PG-A (3000, Liquidado) y PG-B (3000, registrado sin verificar). PG-B se **verifica en T + 1 d sin reactivar la contratación**. Una devolución A por cada pago: 3000 y 3000. Ninguna devolución de otra clase |
| T-64 | Pendiente de C | **Necesaria, reformular** | Pago de 300 posterior al cierre de su solicitud; el Evento se cancela después: se registra y verifica, no se aplica, **sin devolución** y queda incluido en la constancia de no reembolso (C-12) |
| T-65 | Pendiente de C | **Fuera del alcance (redundante)** | Con C, el resultado no depende del instante del pago respecto de la cancelación. T-64 y T-70 ya lo cubren |
| T-66 | Pendiente de B y C | **Necesaria, reformular sobre el anticipo** | Anticipo de 4000 aceptado (B-2) y Evento cancelado después: el excedente de 1000 **no se devuelve**; constancia de no reembolso. **No** se prueba el excedente sobre un cambio: sería un sobrepago de otro concepto (X-14) |

### 5.2 Estado final de T-46 a T-72

| Clasificación | Pruebas |
|---|---|
| **Necesarias para el alcance congelado** (13) | T-46, T-48, T-55, T-57, T-64, T-66 (reformuladas); T-61, T-68, T-70, T-71, T-72; T-49 (se integra en T-07); T-56 (se integra en T-34). T-68 y T-70 cambian la «retención con importe» por la constancia de C-12 |
| **Excluidas o redundantes** (15) | T-47, T-50, T-51, T-52, T-53, T-54, T-58, T-58b, T-60, T-63, T-67, T-69 (dependen de X-01 a X-04, X-07 y X-13); T-59 y T-62 (repiten pruebas existentes); T-65 (redundante con C) |
| **Pendientes de una decisión de negocio** | Ninguna |

Total: 13 + 15 = 28 entradas (las 27 pruebas de T-46 a T-72 más la variante T-58b). Las fichas T-50 a T-54 no se corrigen, porque dependen de elementos excluidos. Las fichas T-55 y T-57 deben reescribirse con los resultados de 5.1, sin el remanente ni las clases D3 y D4.

### 5.3 Otras pruebas propuestas en la V4.1 que también cambian

No son nuevas; se reformulan.

| Prueba | Decisión | Cambio |
|---|---|---|
| T-14 (casos #2, #5, #6 y #7 de H-10) | B | Donde la V4.1 esperaba una D4 del anticipo: sin devolución y requisito cubierto |
| T-14b (grupo R11) | B-5, C | Con el Evento vigente: fuera del alcance (X-14). Con el Evento cancelado: C-12 |
| T-15 | A | Pagos no oportunos o posteriores al cierre de la contratación: devolución A, sin reapertura |
| T-24 | C | Pago posterior a la cancelación: sin devolución; constancia |
| T-25 | A | Una devolución de cada clase: solo SE-012 y A |

### 5.4 Trazabilidad entre decisiones y pruebas

| Decisión | Reglas | Pruebas necesarias | Pruebas que dejan de aplicar |
|---|---|---|---|
| A | A-1 a A-6; C-04, C-11 | T-46, T-48, T-57, T-15, T-25 | Las basadas en D3 con remanente y prioridad: T-50 a T-54 |
| B | B-1 a B-5; C-03 | T-55, T-66 (parte del anticipo), T-14 | Excedentes D4 del anticipo: los casos D4 de T-50 a T-55 en la V4.1; T-14b con el Evento vigente |
| C | C-1 a C-4; C-12 | T-64, T-66, T-68 (b), T-70, T-24 | T-65 |

---

## 6. Oráculo histórico: cómo recalcularlo

Los recuentos 240 / 135 / 375 de la V4.1 **no se cambian a mano**. Se sustituyen solo por los que produzca este procedimiento, con su evidencia.

**Evidencia de esta sesión:** sobre una copia del proyecto se ejecutó `capturar_comportamiento_estado_cuenta()`. Dio 1203 claves y 42 diferencias con `comportamiento_estado_cuenta_v8_e3c.json`, igual que antes. Las operaciones del arnés son las de EstadoCuenta (`pagar`, `verificar_pago_registrado`, `aplicar_cierre_sin_realizar`, `registrar_devolucion_efectuada`, `resolver_regularizacion`, entre otras). El arnés **no incluye el cierre de la contratación**, así que la decisión A se verifica con T-46, T-48 y T-57, no con el oráculo.

**Procedimiento:**
1. En una copia del proyecto, ejecutar el arnés y guardar los resultados actuales. Desde la raíz:
   `python3 -I -c "import sys,json; sys.path[:0]=['tests','src']; import apoyo_maquina_estados_estado_cuenta as A; json.dump(A.capturar_comportamiento_estado_cuenta(), open('actual.json','w'))"`
2. Seleccionar las claves de cada grupo con los predicados de la parte C.2 de la V4.1 (R1 a R12 y las 43 de H-10).
3. Fijar el esperado por clave:
   - **Sin cambios** frente a la V4.1: R1, R4, R5, R8, R9, R10 y R12.
   - **Con esperado nuevo según este cierre:**
     - R6 (pago sobre un anticipo ya Liquidado): sin D4; el pago se verifica sin aplicarse y sin devolución (B-3, B-4).
     - R7 (suma superior al 30 %): sin D4 (B-3).
     - H-10 #2, #5, #6 y #7: según B (y A si hay cierre).
     - R11 (excedente de otros conceptos): fuera del alcance con el Evento vigente; C-12 con el Evento cancelado.
     - R2 (pago sobre una obligación Sin efecto): SE-012 con el Evento vigente, C-12 con el Evento cancelado.
4. Contar por clave: esperado frente a actual en estado o resultado, frente a actual solo en consultas, y frente a la referencia. Los totales nuevos son los que salgan de ese recuento.
5. Registrar los totales nuevos con la salida del programa como evidencia. No se edita el JSON de referencia.

**Estado:** el recálculo **no se ha hecho**. Los totales nuevos no se conocen y no se anticipan.

---

## 7. Bloqueos que realmente impiden continuar

| # | Bloqueo | Qué impide | Cómo se desbloquea |
|---|---|---|---|
| BL-1 | **Resuelto.** El plazo de A se cotejó con B-3, RN-42 y RN-60 (A-6) | — | `…_decision_A_provisional.md` sigue sin estar disponible; no se le atribuye contenido |
| BL-2 | Recálculo del oráculo pendiente (sección 6) | Usar el oráculo como criterio de aceptación | Ejecutar el procedimiento de la sección 6 |
| BL-3 | FastAPI no se puede instalar en este entorno | Ejecutar las 32 pruebas de API y la suite completa | Un entorno con acceso a PyPI |

La persistencia (TP-01) no bloquea la revisión ni la implementación funcional.

---

## 8. Siguiente paso: comparar el código con el alcance aprobado

Preparar una **matriz de brechas** entre las reglas C-01 a C-15 (con A, B y C) y el código actual, sin modificar nada:
- Para cada regla: el módulo o la función responsable, el comportamiento actual con su evidencia (lectura de código, arnés o prueba existente) y el resultado: «cumple», «brecha» o «no aplicable».
- Ejecutar antes el recálculo del oráculo (sección 6).

**Brechas ya observadas al leer el código** en esta revisión, sin ejecución de pruebas nuevas. Son puntos de partida de la matriz, no conclusiones finales:
1. `EstadoCuenta.registrar_y_verificar_pago` rechaza como importe incorrecto cualquier pago de anticipo **distinto** del importe exacto (`importe != o.importe`). Choca con **B-1 y B-2**.
2. `EstadoCuenta.registrar_y_verificar_pago` rechaza todo pago sobre una obligación Sin efecto («La obligación no existe o quedó sin efecto»). Choca con **A-3** (registrar y verificar un pago de anticipo después del cierre) y con el registro de pagos tardíos de C-12.
3. **ND-29**: el código liquida el saldo con un pago tardío registrado antes de que conste el vencimiento (grupo R12, 48 claves; diferencia D-24 de la V4.1).
4. No existe la devolución del anticipo de la decisión A: hoy las devoluciones solo se crean por SE-012 (`aplicar_cierre_sin_realizar`).

---

Con este cierre no se amplía el alcance funcional de Eventos Nova. Las implementaciones posteriores deberán limitarse a corregir o completar el comportamiento necesario para cumplir las reglas conservadas.
