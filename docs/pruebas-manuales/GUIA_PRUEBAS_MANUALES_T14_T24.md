# Guía de pruebas manuales T-14 a T-24 (Swagger)

> **Nota del 29/10/2026:** los eventos y demás registros que esta guía cita como evidencia de las pruebas ejecutadas el 28/10/2026 (por ejemplo `EV-157c1d85…`, `EV-c0595c85…`) **fueron retirados de la base activa `eventosnova_manual_test`** durante la limpieza de datos de prueba. Se conservan en la copia de seguridad `backups/eventosnova_manual_test_20261029_145506.dump`. Detalle en [`docs/PRUEBAS_Y_LIMPIEZA_DATOS_MANUAL.md`](../PRUEBAS_Y_LIMPIEZA_DATOS_MANUAL.md).

> **Corrección del reloj (28/10/2026):** la zona horaria aprobada es America/Mexico_City (TP-06, cierre de alcance). La API, el trabajador y el Outbox usan ahora `reloj_negocio` (hora de pared de la Ciudad de México, sin zona). Donde las secciones 0 a 11 dicen «UTC» o «hora del servidor (UTC)», describen la primera ejecución, anterior a esta corrección; **para ejecutar use solo la sección 12**.
>
> **Para ejecutar T-21, T-23 y T-24 con el código actualizado (D-1, D-2, D-3) use la sección 12.** Las secciones 1 a 11 conservan el procedimiento y los resultados históricos de la primera ejecución. **Estado (29/10/2026):** el equipo ejecutó T-21, T-23 y T-24 con el procedimiento de la sección 12 y las tres resultaron satisfactorias; los resultados informados están en la sección 10.1 y en `CIERRE_AUDITORIA_FINAL.md` §Q.

> **Estado de este documento (histórico, primera versión):** guía preparada; las pruebas aún no se habían ejecutado. El punto 1.9 de la verificación local no está completado hasta que se ejecuten y se registren en la bitácora (sección 9). *(Desde el 29/10/2026 constan los resultados de la ejecución final en la sección 10.1; la plantilla de la sección 9 sigue sin completarse con las horas y los nombres de las capturas, que no se entregaron.)*

## 0. Reglas de uso

1. Swagger de la **API manual**: **http://127.0.0.1:8001/docs**. Todas las operaciones de esta guía se ejecutan **solo en el puerto 8001**. **Nunca** en el puerto 8000 (desarrollo).
2. La API manual usa la base `eventosnova_manual_test` (PostgreSQL, migraciones en `0004`). Se levantó con `docker-compose.manual-test.yml` (API `eventosnova-api-manual` y trabajador `eventosnova-worker-manual`).
3. No use `EV-0028db33` ni ningún otro evento de la base de desarrollo.
4. Antes de empezar, compruebe (solo lectura) que `GET http://127.0.0.1:8001/ready` responde `{"estado":"ok","persistencia":"postgresql","base_de_datos":"ok"}`.
5. En Swagger use **Try it out → Execute** y guarde la respuesta (código HTTP y cuerpo). Los valores entre `<ángulos>` se sustituyen por los identificadores reales copiados de respuestas anteriores. **Los identificadores de los ejemplos del OpenAPI (`CL-1`, `PV-1`, `OB-1a2b3c4d`, `PR-1a2b3c4d-v1`…) no existen en la base**; no los copie tal cual.

### 0.1 Origen de los datos de esta guía

Todo lo siguiente se tomó del código real (esquemas Pydantic de `src/api/`, servicios de `src/application/servicios.py`, dominio de `src/domain/`). Además, los cuerpos y las respuestas de cada caso se **comprobaron previamente en una instancia en memoria** (sin PostgreSQL ni puerto 8001), con un reloj fijo al 28/10/2026 06:45. Esa comprobación valida el comportamiento del código; **no sustituye** la ejecución real en el puerto 8001, que está pendiente.

### 0.2 Fechas y hora del servidor

Las fechas se envían **sin zona horaria** (`2026-10-28T10:00:00`). El servidor usa `datetime.now()` del contenedor, que está en **UTC** (el contenedor marcaba 06:35 UTC cuando su equipo local marcaba 00:35). Para calcular las fechas relativas, consulte la hora del servidor (solo lectura):

```
docker exec eventosnova-api-manual date
```

Llámela **AHORA** (UTC). Fechas de esta guía, calculadas el 28/10/2026 y que debe recalcular si ejecuta otro día:

| Variable | Regla | Valor si AHORA = 2026-10-28 06:45 |
|---|---|---|
| `FECHA_FIRMA` | AHORA redondeado a la hora | `2026-10-28T07:00:00` |
| `FECHA_PAGO` | 30 min después de `FECHA_FIRMA` | `2026-10-28T07:30:00` |
| `FECHA_REGISTRO_PAGO` | 30 min después de `FECHA_PAGO` | `2026-10-28T08:00:00` |
| `FECHA_VERIFICACION` | 30 min después del registro | `2026-10-28T08:30:00` |
| `EV_PRINCIPAL` (T-14) | AHORA + 50 días o más | `2026-12-18T18:00:00` |
| `EV_CANCELACION` (T-21) | AHORA + 50 días o más | `2026-12-19T18:00:00` |
| `EV_CERCANO` (T-23) | **Sustituido:** véase la sección 11.3 (AHORA + 4 días, domingo a martes UTC) | — |
| `EV_PASADO` (T-24) | AHORA − 8 días (cualquier fecha anterior a AHORA) | `2026-10-20T18:00:00` |

Notas: (a) en las pruebas previas el servicio aceptó fechas de firma y de pago posteriores al reloj, y el anticipo se compara con su plazo de 3 días hábiles tras la firma; use fechas cercanas a AHORA para no salirse de ese plazo. (b) El plazo del anticipo es `FECHA_FIRMA` + 3 días hábiles, con límite exclusivo a las 00:00 del día siguiente (decisión E-1); el pago de esta guía cae el mismo día de la firma, dentro del plazo.

### 0.3 Cómo localizar los identificadores

| Identificador | De dónde se copia |
|---|---|
| `evento_id` | Respuesta de T-14 (`POST /eventos`), campo `evento_id` (formato `EV-<uuid>`). |
| `propuesta_id` | Respuesta de T-15, campo `propuesta_id` (`PR-<uuid>`). |
| `version_id` | **No aparece en ninguna respuesta ni GET.** Es una convención implementada, no una suposición: `Propuesta.__init__` (`src/domain/propuesta.py`, línea 23) crea la primera versión con `f"{propuesta_id}-v1"` y `generar_nueva_version` usa `f"{self.id}-v{numero}"`; `aceptar` solo admite el id igual a `version_vigente_id` (CA-013) y el mapeador (`src/infrastructure/persistencia/mapeadores.py`, líneas 176 y 185) conserva el valor en PostgreSQL. La primera versión es `<propuesta_id>-v1`. Ejemplo: `PR-8192a1d3-…-v1`. Si generó nuevas versiones, la vigente sería `-v2`, etc. (esta guía no genera nuevas). |
| `contrato_id` | Respuesta de T-16 (`POST /propuestas/{propuesta_id}/contrato`), en `datos.contrato_id` (`CT-<uuid>`). |
| `estado_cuenta_id` y `obligacion_id` | `GET /pagos-pendientes?evento_id=<evento_id>`: en `pagos[0]` → `estadoCuentaId` (`EC-<uuid>`) y `obligacionId` (`OB-<uuid>`). El anticipo aparece con `concepto: "Anticipo"`. Los GET `/eventos/{id}/pagos` y `/administracion` muestran el estado de cuenta pero **no** el `obligacionId`. |
| `pago_id` | **Solo** en la respuesta del `POST …/pagos` (T-18), en `datos.pago_id` (`PG-<uuid>`). Los GET no lo muestran: cópielo al instante. |
| `solicitud_id` | Respuesta de T-19 / T-20 / T-23, en `datos.solicitud_id` (`SA-…` o `SC-…`). |

Los identificadores son únicos por ejecución; anótelos en la bitácora (sección 9).

### 0.4 Convención de respuestas

- Éxito: HTTP 200/201 con `{"mensaje": "...", "datos": {...}}` (los POST de creación devuelven además el id en el nivel superior: T-14 y T-15).
- Rechazo de negocio: **HTTP 422** con `{"tipo": "rechazo_de_negocio", "detalle": "...", "pendientes": []}`.
- Error de validación del cuerpo (campo faltante, fecha con zona…): **HTTP 422** con `{"detail": [ {"type": ..., "loc": [...], "msg": ...} ]}`.
- Los textos de `mensaje`/`detalle` de esta guía son los que devuelve el código; si en la ejecución difieren, anótelo como discrepancia.

---

## 1. Preparación de eventos independientes

Se usan **cuatro eventos distintos**, uno por escenario, para que una prueba terminal (cancelar, iniciar) no impida las demás:

| Evento | Casos | Fecha del evento |
|---|---|---|
| `EV_PRINCIPAL` | T-14 a T-20 y T-22 | AHORA + 50 días |
| `EV_CANCELACION` | T-21 | AHORA + 50 días |
| `EV_CERCANO` | T-23 | AHORA + 4 días (domingo a martes UTC; ver 11.3) |
| `EV_PASADO` | T-24 | anterior a AHORA |

- **`EV_PRINCIPAL`** se crea y contrata en T-14 a T-18.
- **`EV_CANCELACION`, `EV_CERCANO` y `EV_PASADO` se contratan repitiendo los pasos T-14 a T-18** (mismos cuerpos; cambian solo `fecha_hora`, identificadores y comprobante). Ejecute este procedimiento completo para cada uno **antes** de su prueba (T-21, T-23 o T-24). Se le llamará *Procedimiento de contratación*. Use un `comprobante` distinto en cada evento (por ejemplo `C-T18-PRINCIPAL`, `C-T18-CANCEL`, `C-T18-CERCANO`, `C-T18-PASADO`).
- Un evento cancelado nunca se reutiliza.

**Por qué esas fechas (condición temporal de cada caso):**

- T-23: el servicio adicional exige **cinco días naturales o más** entre la solicitud y el evento (`AnticipacionSolicitud`, mensaje «quedan menos de cinco días naturales (CA-077, CA-083)»). `EV_CERCANO` a +2 días queda por debajo, pero en el futuro: debe seguir **sin iniciar** para que el motivo sea el plazo y no el inicio del evento (el código evalúa en orden: evento cancelado, inicio, plazo, saldo).
- T-24: el cambio no procede si `Evento.iniciado_en(ahora)` (H-08, GL-032): verdadero si el evento está *En organización* y `ahora ≥ fecha_hora`. Para que el rechazo sea reproducible hoy, `EV_PASADO` se registra con una fecha ya vencida. **Limitación:** `POST /eventos/{id}/inicio` exige `ahora ≥ fecha_hora` (el servicio lo rechaza antes de esa hora), así que con un evento futuro no se puede forzar el inicio; por eso se usa una fecha pasada. El código no valida que la fecha del evento sea futura (comprobado en la prueba en memoria), pero esa permisividad es de la implementación; no se encontró una regla documentada que la ampare ni que la prohíba.
- T-19 y T-20 usan `EV_PRINCIPAL` (a más de 5 días y no iniciado) para que se registren correctamente.

---

## 2. T-14 — Registrar un evento

- **Objetivo:** crear el evento principal.
- **Precondiciones:** API manual lista (`/ready` 200).
- **Endpoint:** `POST /eventos`
- **Cuerpo:**

```json
{
  "cliente_id": "CL-PRUEBA-01",
  "datos": {
    "tipo": "Boda",
    "fecha_hora": "2026-12-18T18:00:00",
    "lugar": "Salón Nova",
    "invitados_aproximados": 120
  },
  "servicios": ["Banquete", "Fotografía"]
}
```

- **Campos obligatorios:** `cliente_id`, `datos` (con los 4 campos) y `servicios`. No se admiten campos extra (HTTP 422). `cliente_id` es texto libre: el servicio no valida que el cliente exista (no hay catálogo de clientes en el código); `CL-PRUEBA-01` es un valor de prueba propio de esta guía.
- **Copiar:** `evento_id`.
- **Esperado:** HTTP **201**; `{"evento_id": "EV-<uuid>", "mensaje": "Evento registrado En gestión."}`.
- **GET de verificación:** `GET /eventos/<evento_id>/administracion` → `estadoEvento: "En gestión"`, `fechaHora: "2026-12-18T18:00:00"`, `contratos: []`.
- **Evidencia:** captura de la petición y la respuesta; captura del GET.
- **Bitácora:** código HTTP, `evento_id`, estado «En gestión», Aprobado/Fallido.

## 3. T-15 — Crear la propuesta

- **Precondiciones:** T-14 hecho; el evento debe estar *En gestión*.
- **Endpoint:** `POST /eventos/<evento_id>/propuestas`
- **Cuerpo:**

```json
{
  "servicios": ["Banquete", "Fotografía"],
  "proveedores_considerados": ["PV-1"],
  "costo_total": "10000.00",
  "condiciones": "Condiciones generales"
}
```

- `costo_total` acepta número o texto decimal. Con **10 000.00** el anticipo del 30 % es **3 000.00** (BN-009; `PORCENTAJE_ANTICIPO = 30`). Si usa otro importe, recalcule el anticipo. `PV-1` es un texto libre (proveedor considerado): el servicio no valida su existencia en este paso.
- **Copiar:** `propuesta_id` y calcule `version_id = <propuesta_id>-v1`.
- **Esperado:** HTTP **201**; `{"propuesta_id": "PR-<uuid>", "evento_id": "<evento_id>", "mensaje": "Propuesta creada."}`.
- **Si el evento no está En gestión:** HTTP 422 «El evento no existe o no está En gestión.»
- **Evidencia:** captura de petición y respuesta.
- **Bitácora:** `propuesta_id`, `version_id` calculado, resultado.

## 4. T-16 — Aceptar la propuesta y preparar el contrato

**Paso 1 — aceptar la versión vigente**

- **Endpoint:** `POST /propuestas/<propuesta_id>/aceptacion`
- **Cuerpo:** `{ "version_id": "<propuesta_id>-v1" }`
- **Esperado:** HTTP **200**; `{"mensaje": "Propuesta aceptada.", "datos": {}}`. Con una versión no vigente el dominio rechaza (422).

**Paso 2 — preparar el contrato**

- **Endpoint:** `POST /propuestas/<propuesta_id>/contrato`
- **Cuerpo:** `{ "politica_incluida": true }` (debe ser booleano real; `"si"` da 422).
- **Copiar:** `datos.contrato_id`.
- **Esperado:** HTTP **201**; `{"mensaje": "Contrato preparado.", "datos": {"contrato_id": "CT-<uuid>"}}`.
- **Si ya existe un contrato activo del evento:** 422 «Ya existe un contrato activo para el evento.»
- **GET:** `GET /eventos/<evento_id>/administracion` → `contratos` vacío todavía hasta la firma o con el contrato en estado inicial (anote lo que vea; el código no fija este detalle aquí).
- **Evidencia:** ambas respuestas.
- **Bitácora:** `contrato_id`, resultados de los 2 pasos.

## 5. T-17 — Comunicar la política de no reembolso y registrar la firma

Orden: primero la comunicación, después la firma (la confirmación exigirá ambas).

**Paso 1**

- **Endpoint:** `POST /contratos/<contrato_id>/comunicacion-politica-no-reembolso`
- **Cuerpo:** `{ "fecha": "2026-10-28T07:00:00" }` (`FECHA_FIRMA`; sin zona horaria).
- **Esperado:** HTTP **200**; `{"mensaje": "Comunicación de la política registrada.", "datos": {}}`.

**Paso 2**

- **Endpoint:** `POST /contratos/<contrato_id>/firma`
- **Cuerpo:** `{ "fecha": "2026-10-28T07:00:00" }`
- **Esperado:** HTTP **200**; `{"mensaje": "Contrato firmado.", "datos": {}}`. Al firmarse se crea el estado de cuenta con el anticipo (reacción al evento `ContratoFirmado`).
- **GET de verificación:** `GET /pagos-pendientes?evento_id=<evento_id>` → una fila con `concepto: "Anticipo"`, `importe: "3000.00"` (30 % de 10 000.00), `pagado: "0"`, `estado: "Pendiente"`, `fechaLimite` = tercer día hábil posterior a la firma a las 00:00 del día siguiente (con firma el miércoles 28/10: `2026-11-03T00:00:00`).
- **Copiar:** `estadoCuentaId` y `obligacionId`.
- **Evidencia:** respuestas y el GET.
- **Bitácora:** `estado_cuenta_id`, `obligacion_id`, importe del anticipo, `fechaLimite`.

> El filtro `evento_id` de `/pagos-pendientes` es el único parámetro de ese GET. En una base con más eventos el resultado puede traer más filas; escoja la del evento correcto (`eventoId`).

## 6. T-18 — Registrar y verificar el anticipo y confirmar la contratación

Requisitos de la confirmación (especificación `CONTRATACION_CONFIRMABLE`): contrato **firmado**, **política comunicada** y **anticipo del 30 % registrado y verificado**. No ejecute la confirmación antes de que se cumplan.

**Paso 1 — registrar el pago (sin verificar)**

- **Endpoint:** `POST /estados-cuenta/<estado_cuenta_id>/pagos`
- **Cuerpo:**

```json
{
  "obligacion_id": "<obligacion_id>",
  "importe": "3000.00",
  "fecha": "2026-10-28T07:30:00",
  "comprobante": "C-T18-PRINCIPAL",
  "registrado_en": "2026-10-28T08:00:00",
  "verificar_ahora": false
}
```

- `importe` = 30 % del `costo_total` real de la propuesta (lo muestra `GET /pagos-pendientes`, campo `importe`). `comprobante` debe ser **único** (un comprobante repetido sobre la misma obligación se rechaza, control del equipo sin respaldo documental). `fecha` es cuándo pagó el Cliente; `registrado_en` es cuándo lo registra Administración (opcional; por omisión, la fecha del pago); `verificar_ahora` es opcional (por omisión `true`).
- **Copiar:** `datos.pago_id`.
- **Esperado:** HTTP **201**; `{"mensaje": "Pago Registrado.", "datos": {"pago_id": "PG-<uuid>", "estado": "Registrado"}}`.

**Paso 2 — verificar el pago**

- **Endpoint:** `POST /estados-cuenta/<estado_cuenta_id>/pagos/<pago_id>/verificacion`
- **Cuerpo:** `{ "verificado_en": "2026-10-28T08:30:00" }`
- **Esperado:** HTTP **200**; `{"mensaje": "Pago Verificado.", "datos": {"pago_id": "<pago_id>", "estado": "Verificado"}}`. (El verificador es simulado y acepta cualquier comprobante no vacío.)

**Paso 3 — confirmar la contratación**

Con la verificación del anticipo, el sistema **confirma la contratación automáticamente** (reacción al evento `PagoVerificado`, despacho en línea y por el trabajador). Por eso:

- **Endpoint:** `POST /contratos/<contrato_id>/confirmacion` (sin cuerpo).
- **Esperado en la prueba previa:** HTTP **200** con `"La contratación ya estaba confirmada."` (la operación es idempotente). Si por temporización del Outbox aún no estuviera confirmada, la llamada la confirma: HTTP 200 `"Contratación confirmada."`. Si faltara algún requisito: HTTP **422** con `pendientes` (por ejemplo `"anticipo del 30 % registrado y verificado"`).
- **GET de verificación:** `GET /eventos/<evento_id>/administracion` → `estadoEvento: "En organización"`, `contratos[0].estado: "Contratación confirmada"` y `estadosCuenta[0].anticipo.estado: "Liquidada"`. Anote cuál de las dos respuestas (ya confirmada / confirmada) obtuvo; ambas son válidas.
- **Prueba negativa opcional (no requerida por T-18):** ejecutar la confirmación **antes** del paso 2 en otro evento debería dar 422 con ese pendiente.
- **Evidencia:** respuestas de los 3 pasos y el GET.
- **Bitácora:** `pago_id`, importe, resultados, estado final del evento y del contrato.

---

## 7. Casos sobre solicitudes y cancelación

### T-19 — Solicitar un servicio adicional

- **Evento:** `EV_PRINCIPAL` (contratación confirmada, T-18; más de 5 días hasta el evento).
- **Endpoint:** `POST /solicitudes-servicio-adicional`
- **Cuerpo:**

```json
{
  "evento_id": "<evento_id>",
  "contrato_id": "<contrato_id>",
  "servicio": "Fotografía"
}
```

- `contrato_id` debe pertenecer a `evento_id`; si no, HTTP 422 (decisión E-2). Además, el servicio evalúa en orden: evento cancelado, evento iniciado, plazo de cinco días y, al final, saldo vencido; el primero que se incumple fija el motivo.
- **Copiar:** `datos.solicitud_id`.
- **Esperado:** HTTP **201**; `{"mensaje": "Solicitud Registrada.", "datos": {"solicitud_id": "SA-<uuid>", "estado": "Registrada", "motivo": ""}}`.
- **GET:** `GET /solicitudes?evento_id=<evento_id>` → fila `tipoSolicitud: "servicio adicional"`, `estadoActual: "Registrada"`, `pendiente: true`; y `GET /eventos/<evento_id>/solicitudes-pendientes` → `accionPendiente: "evaluación"`.
- **Evidencia:** respuesta y GET. **Bitácora:** `solicitud_id`, estado.

### T-20 — Solicitar un cambio

- **Evento:** `EV_PRINCIPAL`.
- **Endpoint:** `POST /solicitudes-cambio`
- **Cuerpo:**

```json
{
  "evento_id": "<evento_id>",
  "contrato_id": "<contrato_id>",
  "descripcion": "Cambiar la hora de inicio",
  "tarifa_vigente": "500.00",
  "datos_propuestos": {
    "tipo": "Boda",
    "fecha_hora": "2026-12-18T19:00:00",
    "lugar": "Salón Nova",
    "invitados_aproximados": 120
  }
}
```

- `datos_propuestos` y `condiciones_propuestas` son opcionales. `tarifa_vigente` es **obligatoria** en el esquema. **Limitación:** el importe de la tarifa del cargo por cambio tardío **no está definido** en el BRD ni en el código («tarifa vigente establecida por Eventos Nova», BN-003); `500.00` es solo el ejemplo del OpenAPI, **no una tarifa oficial**. Con este evento el cambio se pide con más de siete días de anticipación, por lo que en la regla documentada no se cobra el cargo.
- **Copiar:** `datos.solicitud_id`.
- **Esperado:** HTTP **201**; `{"mensaje": "Solicitud Registrada.", "datos": {"solicitud_id": "SC-<uuid>", "estado": "Registrada"}}`.
- **GET:** `GET /solicitudes?evento_id=<evento_id>` → ahora dos filas (cambio y servicio adicional), ambas `Registrada`.
- **Evidencia/Bitácora:** igual que T-19.

### T-21 — Cancelar un evento (independiente)

> **Repetición pendiente:** la primera ejecución canceló el evento principal (desviación registrada en la sección 10). El procedimiento vigente para repetir esta prueba con un evento independiente está en la **sección 11.2**.

- **Evento:** `EV_CANCELACION`: ejecute antes el *Procedimiento de contratación* (T-14 a T-18) con fecha de evento AHORA + 50 días y comprobante propio. **No use `EV_PRINCIPAL`.**
- **Endpoint:** `POST /eventos/<evento_id_cancelacion>/cancelacion`
- **Cuerpo:** `{ "motivo": "El Cliente canceló" }`
- **Condición:** la cancelación exige contratación confirmada (CA-084) y que el evento no haya iniciado.
- **Esperado:** HTTP **200**; `{"mensaje": "Evento cancelado.", "datos": {}}`.
- **GET:** `GET /eventos/<evento_id_cancelacion>/administracion` → `estadoEvento: "Cancelado"`.
- **Sin confirmar la contratación:** HTTP 422 «La cancelación solo procede con la contratación confirmada (CA-084).»
- **Evidencia:** respuesta y GET. **Bitácora:** estado final «Cancelado».
- Opcional (no es parte de T-21): `POST /eventos/{id}/revision-administrativa` con `{"resultado": "...", "fecha": "..."}`; ambos campos son obligatorios.

### T-22 — Rechazo de fechas con zona horaria

Confirmado en el código y en pruebas existentes: las fechas son `NaiveDatetime`; un valor con zona horaria da HTTP 422 de validación (`tests/test_api_operaciones.py`, firma con `2026-10-01T10:00:00+00:00`). La validación ocurre antes de ejecutar el servicio, por lo que **no cambia ningún dato**.

- **Endpoint:** `POST /contratos/<contrato_id>/firma` (cualquier `contrato_id`, por ejemplo el de `EV_PRINCIPAL`; se rechaza antes de cualquier acción).
- **Cuerpos a probar (uno por vez):**

```json
{ "fecha": "2026-10-28T07:00:00+00:00" }
```
```json
{ "fecha": "2026-10-28T07:00:00Z" }
```

- **Esperado:** HTTP **422** con `{"detail": [ ... ]}` (error de validación del campo `fecha`). El caso `+00:00` está cubierto por una prueba existente; el caso `Z` se verificó en una ejecución previa del proyecto (no se repitió hoy), anótelo como observación si difiere.
- **GET:** `GET /eventos/<evento_id>/administracion` → el contrato sigue en su estado anterior.
- **Evidencia:** respuesta 422. **Bitácora:** código 422, cuerpo `detail`.

### T-23 — Servicio adicional con menos de cinco días naturales

> **Repetición pendiente:** en la primera ejecución el contrato del evento seguía `Firmado` (sin confirmar). El procedimiento vigente, con la comprobación de la contratación confirmada y del saldo, está en la **sección 11.3**.

- **Evento:** `EV_CERCANO` (fecha AHORA + 4 días, domingo a martes UTC; la sección 11.3 sustituye a este texto): ejecute antes el *Procedimiento de contratación* (T-14 a T-18) con esa fecha y comprobante propio.
- **Endpoint:** `POST /solicitudes-servicio-adicional`
- **Cuerpo:**

```json
{
  "evento_id": "<evento_id_cercano>",
  "contrato_id": "<contrato_id_cercano>",
  "servicio": "Fotografía"
}
```

- **Esperado:** HTTP **201** (la solicitud se registra y se resuelve como no procedente; no es un 422); `{"mensaje": "Solicitud No procedente.", "datos": {"solicitud_id": "SA-<uuid>", "estado": "No procedente", "motivo": "Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083)."}}`.
- **GET:** `GET /solicitudes?evento_id=<evento_id_cercano>` → `estadoActual: "No procedente"`, `pendiente: false`.
- **Evidencia:** respuesta y GET. **Bitácora:** estado «No procedente» y texto del motivo.
- Si el evento ya hubiera iniciado (fecha pasada), el motivo sería otro; compruebe `fecha_hora` > AHORA.

### T-24 — Cambio después de iniciado el evento

- **Evento:** `EV_PASADO` (fecha anterior a AHORA): ejecute antes el *Procedimiento de contratación* con esa fecha y comprobante propio. El evento queda *En organización* con la fecha ya vencida, lo que el dominio considera «iniciado» (H-08).
- **Endpoint:** `POST /solicitudes-cambio`
- **Cuerpo:**

```json
{
  "evento_id": "<evento_id_pasado>",
  "contrato_id": "<contrato_id_pasado>",
  "descripcion": "Cambiar la hora",
  "tarifa_vigente": "500.00"
}
```

- (`tarifa_vigente` obligatoria; ver la limitación de T-20.)
- **Esperado:** HTTP **422**; `{"tipo": "rechazo_de_negocio", "detalle": "El cambio solo procede después de contratar y antes del inicio (CA-039).", "pendientes": []}`.
- **GET:** `GET /solicitudes?evento_id=<evento_id_pasado>` → `solicitudes: []` (el rechazo no deja solicitud).
- **Evidencia:** respuesta 422 y GET. **Bitácora:** código 422, detalle.

---

## 8. Resumen de la secuencia

| Caso | Método y endpoint | Evento | HTTP esperado | Resultado de negocio |
|---|---|---|---|---|
| T-14 | `POST /eventos` | PRINCIPAL | 201 | Evento «En gestión» |
| T-15 | `POST /eventos/{evento_id}/propuestas` | PRINCIPAL | 201 | Propuesta creada |
| T-16 | `POST /propuestas/{id}/aceptacion` y `/contrato` | PRINCIPAL | 200 y 201 | Propuesta aceptada; contrato preparado |
| T-17 | `POST /contratos/{id}/comunicacion-politica-no-reembolso` y `/firma` | PRINCIPAL | 200 y 200 | Política comunicada; contrato firmado; anticipo Pendiente |
| T-18 | `POST /estados-cuenta/{ec}/pagos`, `/pagos/{pago}/verificacion`, `POST /contratos/{id}/confirmacion` | PRINCIPAL | 201, 200, 200 | Anticipo verificado y Liquidado; contratación confirmada; evento «En organización» |
| T-19 | `POST /solicitudes-servicio-adicional` | PRINCIPAL | 201 | Solicitud «Registrada» |
| T-20 | `POST /solicitudes-cambio` | PRINCIPAL | 201 | Solicitud «Registrada» |
| T-21 | `POST /eventos/{id}/cancelacion` | CANCELACIÓN | 200 | Evento «Cancelado» |
| T-22 | `POST /contratos/{id}/firma` con zona horaria | PRINCIPAL (sin cambios) | 422 | Validación del campo `fecha` |
| T-23 | `POST /solicitudes-servicio-adicional` | CERCANO | 201 | «No procedente» por menos de cinco días |
| T-24 | `POST /solicitudes-cambio` | PASADO | 422 | Rechazo por evento iniciado (CA-039) |

Orden recomendado: T-14→T-18 (principal), T-19, T-20, T-22; en paralelo o después, el procedimiento de contratación y T-21, T-23, T-24, cada uno con su propio evento.

### 8.1 Limitaciones y datos no verificados

- **No se ejecutó nada en el puerto 8001.** Todas las respuestas indicadas proceden del código y de una ejecución en memoria; pueden aparecer diferencias en PostgreSQL (por ejemplo, la temporización de la confirmación automática por el Outbox).
- `cliente_id`, `PV-1`, `tipo`, `lugar`, `invitados_aproximados`, textos de `condiciones`, `descripcion` y `motivo` son valores de prueba propios; el código no valida su existencia ni un catálogo.
- `500.00` (`tarifa_vigente`) **no es una tarifa oficial**; el BRD no fija su importe.
- El importe de 10 000.00 es ilustrativo; el anticipo (30 %) debe calcularse con el `costo_total` real que use.
- `version_id` no lo devuelve la API: se construye con la convención implementada en `Propuesta.__init__` (`<propuesta_id>-v1`). Si `POST …/aceptacion` respondiera 422 «Solo puede aceptarse la versión vigente (CA-013)», revise que el id esté bien copiado.
- La aceptación de fechas de evento pasadas no se apoya en una regla documentada; se usa solo para poder probar T-24.
- El caso `Z` de T-22 no se repitió hoy (el `+00:00` sí está cubierto por una prueba existente).
- La hora del servidor es UTC; los cálculos relativos de la sección 0.2 deben rehacerse si la ejecución se hace otro día.
- Los textos de las decisiones E-1 a E-4 y del control de comprobante repetido son decisiones del equipo, sin aprobación externa registrada.

---

## 9. Bitácora de ejecución (plantilla)

Copie una fila por cada petición ejecutada. Estado: **Aprobado** (HTTP y resultado de negocio coinciden con lo esperado), **Fallido** (difieren) o **Bloqueado** (no pudo ejecutarse; indique la causa).

| Fecha y hora (local) | Caso | Endpoint y método | Cuerpo / identificadores usados | HTTP real | Resultado real | HTTP y resultado esperados | Evidencia (archivo de captura) | Estado |
|---|---|---|---|---|---|---|---|---|
| | T-14 | `POST /eventos` | | | | 201 · Evento registrado En gestión | | |
| | T-15 | `POST /eventos/{id}/propuestas` | | | | 201 · Propuesta creada | | |
| | T-16a | `POST /propuestas/{id}/aceptacion` | | | | 200 · Propuesta aceptada | | |
| | T-16b | `POST /propuestas/{id}/contrato` | | | | 201 · Contrato preparado | | |
| | T-17a | `POST /contratos/{id}/comunicacion-politica-no-reembolso` | | | | 200 | | |
| | T-17b | `POST /contratos/{id}/firma` | | | | 200 · Contrato firmado | | |
| | T-18a | `POST /estados-cuenta/{ec}/pagos` | | | | 201 · Pago Registrado | | |
| | T-18b | `POST …/pagos/{pago}/verificacion` | | | | 200 · Pago Verificado | | |
| | T-18c | `POST /contratos/{id}/confirmacion` | | | | 200 · confirmada / ya confirmada | | |
| | T-19 | `POST /solicitudes-servicio-adicional` | | | | 201 · Registrada | | |
| | T-20 | `POST /solicitudes-cambio` | | | | 201 · Registrada | | |
| | T-21 | `POST /eventos/{id}/cancelacion` | | | | 200 · Evento cancelado | | |
| | T-22 | `POST /contratos/{id}/firma` (con zona) | | | | 422 · validación | | |
| | T-23 | `POST /solicitudes-servicio-adicional` | | | | 201 · No procedente (< 5 días) | | |
| | T-24 | `POST /solicitudes-cambio` | | | | 422 · CA-039 | | |

**Identificadores de la ejecución** (anótelos al obtenerlos):

| Escenario | evento_id | propuesta_id | version_id | contrato_id | estado_cuenta_id | obligacion_id | pago_id | solicitud_id |
|---|---|---|---|---|---|---|---|---|
| PRINCIPAL | | | | | | | | |
| CANCELACIÓN | | | | | | | | — |
| CERCANO | | | | | | | | |
| PASADO | | | | | | | | — |

**Cómo guardar la evidencia:** para cada caso, una captura de Swagger con la petición (URL, cuerpo) y la respuesta (código y cuerpo), y otra del GET de verificación; nómbrelas `T-XX_paso_AAAAMMDD-HHMM.png` y guárdelas en una carpeta propia (por ejemplo `tests/evidencias/manuales/`, que debe crear usted; esta guía no la crea). Anote también la hora del servidor consultada y el valor de AHORA que usó para calcular las fechas. El punto 1.9 solo puede declararse completado cuando todas las filas tengan estado y evidencia.

---

## 10. Resultados registrados (2026-10-28)

> Esta guía conserva el procedimiento **previsto**. Lo realmente ocurrido, con desviaciones, está en la sección I de [`../architecture/CIERRE_AUDITORIA_FINAL.md`](../architecture/CIERRE_AUDITORIA_FINAL.md). Las capturas de Swagger las conserva el equipo y **aún no están archivadas en el repositorio**; las columnas «Fecha y hora», «Evidencia» y los intentos fallidos de la plantilla de la sección 9 deben completarse con ellas.

| Caso | Estado | Observación |
|---|---|---|
| T-14 a T-18 | Aprobado (resultado reportado por el equipo) | Códigos HTTP esperados en las ejecuciones exitosas; intentos fallidos previos sin detallar |
| T-19, T-20 | Satisfactorio con desviación | HTTP 201; quedaron `Cerrada por evento cancelado` porque T-21 se ejecutó sobre el mismo evento |
| T-21 | Satisfactorio con desviación | HTTP 200, pero se canceló el evento principal en vez de `EV_CANCELACION` |
| T-22 | Aprobado | HTTP 422 con fechas con zona horaria |
| T-23 | Observado con precondiciones incompletas | HTTP 201, `No procedente`, motivo del plazo de 5 días; el contrato de ese evento seguía `Firmado` (sin confirmar) |
| T-24 | Aprobado (reportado) | Evento puesto en ejecución (no se usó una fecha pasada como preveía §1); cambio rechazado con HTTP 422 (CA-039) |
| `GET /solicitudes?evento_id=` | Sin defecto | La respuesta vacía se debió a un `evento_id` mal copiado (`EV-89ab686e-…` en lugar de `EV-89ab606e-…`) |

### 10.1 Ejecución final con el código actualizado (sección 12) — resultados informados por el equipo (29/10/2026)

> Origen: códigos HTTP, estados y mensajes informados por el equipo a partir de sus ejecuciones en Swagger del puerto 8001. Las capturas no están en el repositorio y no se vieron al redactar esta sección. Varias operaciones de T-21 y de T-23 compartieron el mismo valor de *timestamp*: por eso no se anotan horas reales distintas por paso y **no se afirma una secuencia temporal exacta**; se registra el resultado funcional demostrado.

| Caso | Evento / contrato | Pasos y resultados informados | Estado |
|---|---|---|---|
| T-21 cancelación de un evento independiente | `EV-157c1d85-2609-49ba-8ff7-2585d8780239` (distinto del evento principal de T-19 y T-20) | PC-1 201 · PC-2 201 · PC-3 200 · PC-4 201 · PC-5 200 · PC-6 200 · PC-7 200 · PC-8 201 · PC-9 200 · PC-10 200 (`Contratación confirmada`, Evento `En organización`, anticipo `Liquidada`); `POST …/confirmacion` adicional 200 «La contratación ya estaba confirmada.»; `POST /eventos/{id}/cancelacion` 200 «Evento cancelado.»; `GET …/administracion` 200 `Cancelado`; `GET /solicitudes?evento_id=…` 200 `{"solicitudes":[]}` | **Aprobado**. La lista vacía solo demuestra que ese evento no tenía solicitudes al consultarse; no demuestra el cierre de solicitudes, porque no se creó ninguna |
| T-23 servicio adicional con menos de cinco días naturales | `EV-c5ac61cc-5ce4-412f-96df-ca109dae427a` · `CT-29214729-b65b-4cdb-a379-1389c2a74e68` | Registro, propuesta, aceptación, contrato, política y firma: 201, 201, 200, 201, 200 y 200; anticipo: consulta 200 (`Pendiente`), pago 201, verificación 200; `GET …/administracion` 200 (`En organización`, `Contratación confirmada`, anticipo `Liquidada`); saldo antes de la solicitud: `7000.00`, `Pendiente`, `fechaLimite` `2026-10-29T00:00:00`, posterior al reloj de negocio consultado; `POST /solicitudes-servicio-adicional` **201** «Solicitud No procedente.», estado `No procedente`, motivo «Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).»; `GET /solicitudes` 200 (servicio adicional, `estadoActual: No procedente`, `pendiente: false`); `GET /pagos-pendientes` posterior: saldo `7000.00` `Pendiente` | **Aprobado**. Precondiciones de la sección 12.5 cumplidas según lo informado (contratación confirmada, saldo no vencido, evento no iniciado). La solicitud **sí se registró** (con estado `No procedente`); no es el rechazo HTTP 422 de CA-101, que solo aplica sin contratación confirmada |
| T-24 cambio después de iniciado el evento | `EV-c0595c85-6ce9-45cd-a45b-15996de7e26a` · `CT-c9583b55-5be2-473b-94b3-8f2112844bee` | Registro, propuesta, aceptación, contrato, política y firma: 201 o 200 según el endpoint, con resultados correctos (no se informó el código de cada paso); anticipo: pago 201, verificación 200; `GET …/administracion` antes de la hora: `En organización`, `Contratación confirmada`, anticipo `Liquidada`; después de la hora programada: 200 y `En ejecución` (inicio automático del trabajador, D-3); `POST /solicitudes-cambio` **422** «El cambio solo procede después de contratar y antes del inicio (CA-039).»; `GET /solicitudes?evento_id=…` 200 `{"solicitudes":[]}` | **Aprobado**. El 422 es el resultado esperado, no un fallo; no se registró ninguna solicitud de cambio |

Pendiente de esta sección: completar la plantilla de la sección 9 con la hora de negocio de cada paso y los nombres de las capturas cuando el equipo las archive.

---

## 11. Repetición de T-21 y T-23 (procedimiento vigente)

> **Estado:** preparado, **no ejecutado**. Las pruebas las realiza el equipo en Swagger del puerto **8001** (`http://127.0.0.1:8001/docs`); nunca en el 8000. No use ni modifique `EV-89ab606e-6eef-42c4-9627-3142e7d89b3b` (evento principal, ya cancelado), `EV-2edfbcd8-…` (en ejecución, de T-24) ni `EV-8e2a6f41-…` (T-23 de la primera ejecución, con el contrato sin confirmar). T-21 y T-23 **no se marcan como aprobadas** hasta que se registren sus resultados reales (sección 10 y `CIERRE_AUDITORIA_FINAL.md` §I).

### 11.0 Hora del servidor y fechas

Consulte la hora del servidor justo antes de empezar (solo lectura): `docker exec eventosnova-api-manual date` (UTC). Llámela **AHORA**. La última lectura al preparar esta sección fue **2026-10-28 21:58 UTC**; si ejecuta otro día o a otra hora, **recalcule** los valores de la columna de ejemplo.

| Variable | Regla | Ejemplo con AHORA = 2026-10-28 21:58 |
|---|---|---|
| `FIRMA` | AHORA redondeada a la media hora | `2026-10-28T22:00:00` |
| `FECHA_PAGO` | `FIRMA` + 30 min | `2026-10-28T22:30:00` |
| `REGISTRO_PAGO` | `FECHA_PAGO` + 30 min | `2026-10-28T23:00:00` |
| `VERIFICACION` | `REGISTRO_PAGO` + 30 min | `2026-10-28T23:30:00` |
| `FECHA_EV_T21` | AHORA + 30 días o más (cualquier hora futura) | `2026-12-19T18:00:00` |
| `FECHA_EV_T23` | **fecha de AHORA + 4 días, a las 18:00**, ejecutando de domingo a martes UTC (ver 11.3) | con AHORA = lunes 2026-11-02 21:58: `2026-11-06T18:00:00` (no hay ejemplo válido para el 28/10) |

Fechas siempre **sin zona horaria** (con zona, HTTP 422). Los pasos usan `costo_total` **10000.00**, de modo que el anticipo del 30 % es **3000.00** (`PORCENTAJE_ANTICIPO = 30`). Si cambia el costo, el anticipo es el `importe` que muestre `GET /pagos-pendientes`; no suponga la cifra. Las firmas y pagos con hora posterior a AHORA se aceptan en las pruebas previas, pero conviene que queden lo más cerca posible de AHORA.

### 11.1 Procedimiento de contratación (PC), común a T-21 y T-23

Se ejecuta **completo y en este orden** para cada evento. `<ev>`, `<pr>`, `<ct>`, `<ec>`, `<ob>`, `<pg>` son los identificadores **reales** copiados de las respuestas (ver 0.3); los de los ejemplos del OpenAPI no existen. Guarde una captura por paso (petición y respuesta).

| Paso | Método y endpoint | Cuerpo JSON | Copiar | Esperado |
|---|---|---|---|---|
| PC-1 | `POST /eventos` | `{"cliente_id": "<CLIENTE>", "datos": {"tipo": "Boda", "fecha_hora": "<FECHA_EV>", "lugar": "Salón Nova", "invitados_aproximados": 120}, "servicios": ["Banquete", "Fotografía"]}` | `evento_id` → `<ev>` | HTTP 201; `Evento registrado En gestión.` |
| PC-2 | `POST /eventos/<ev>/propuestas` | `{"servicios": ["Banquete", "Fotografía"], "proveedores_considerados": ["PV-1"], "costo_total": "10000.00", "condiciones": "Condiciones generales"}` | `propuesta_id` → `<pr>`; `version_id` = `<pr>-v1` (convención de `Propuesta.__init__`; ninguna respuesta lo devuelve) | HTTP 201; `Propuesta creada.` |
| PC-3 | `POST /propuestas/<pr>/aceptacion` | `{"version_id": "<pr>-v1"}` | — | HTTP 200; `Propuesta aceptada.` |
| PC-4 | `POST /propuestas/<pr>/contrato` | `{"politica_incluida": true}` | `datos.contrato_id` → `<ct>` | HTTP 201; `Contrato preparado.` |
| PC-5 | `POST /contratos/<ct>/comunicacion-politica-no-reembolso` | `{"fecha": "<FIRMA>"}` | — | HTTP 200; `Comunicación de la política registrada.` |
| PC-6 | `POST /contratos/<ct>/firma` | `{"fecha": "<FIRMA>"}` | — | HTTP 200; `Contrato firmado.` |
| PC-7 | `GET /pagos-pendientes?evento_id=<ev>` | — | `estadoCuentaId` → `<ec>`; `obligacionId` de la fila `concepto: "Anticipo"` → `<ob>` | HTTP 200; una fila `Anticipo`, `importe` `3000.00`, `pagado` `0`, `estado` `Pendiente` |
| PC-8 | `POST /estados-cuenta/<ec>/pagos` | `{"obligacion_id": "<ob>", "importe": "3000.00", "fecha": "<FECHA_PAGO>", "comprobante": "<COMPROBANTE>", "registrado_en": "<REGISTRO_PAGO>", "verificar_ahora": false}` | `datos.pago_id` → `<pg>` (solo aparece aquí) | HTTP 201; `Pago Registrado.`, `estado: "Registrado"` |
| PC-9 | `POST /estados-cuenta/<ec>/pagos/<pg>/verificacion` | `{"verificado_en": "<VERIFICACION>"}` | — | HTTP 200; `Pago Verificado.`, `estado: "Verificado"` |
| PC-10 | `GET /eventos/<ev>/administracion` | — | — | **Compruebe que la contratación está confirmada:** `estadoEvento: "En organización"`, `contratos[0].estado: "Contratación confirmada"`, `estadosCuenta[0].anticipo.estado: "Liquidada"` |
| PC-11 (solo si PC-10 no lo muestra) | `POST /contratos/<ct>/confirmacion` | sin cuerpo | — | HTTP 200 `Contratación confirmada.` (o `La contratación ya estaba confirmada.`); con requisitos pendientes, HTTP 422 y la lista `pendientes`. **No continúe** hasta que PC-10 muestre «Contratación confirmada» |

- `<COMPROBANTE>` debe ser **único** y distinto en cada evento (`C-T21-0001`, `C-T23-0001`); un comprobante repetido sobre la misma obligación se rechaza.
- La verificación del anticipo confirma la contratación automáticamente (reacción a `PagoVerificado`); por eso PC-11 suele responder «ya estaba confirmada».
- Si un paso responde distinto de lo esperado, **deténgase**, guarde la captura y anótelo como *Fallido*; no cree eventos adicionales sin registrarlos en la bitácora.

### 11.2 T-21 — cancelación de un evento independiente

0. **Plazo de cancelación realmente implementado:** `Evento.solicitar_cancelacion` (`src/domain/evento.py`; C-08, CA-084 a CA-088) exige contratación confirmada y que el evento **no haya iniciado** (`AHORA < fecha_hora`); no exige una anticipación mínima. Por eso basta cualquier fecha futura; se usa una lejana (30 días o más) para no depender del reloj. Con el evento ya iniciado la solicitud se rechazaría y el evento continuaría en ejecución (CA-088).
1. **Valores:** `<CLIENTE>` = `CL-PRUEBA-T21`; `<FECHA_EV>` = `FECHA_EV_T21`; `<COMPROBANTE>` = `C-T21-0001`.
2. Ejecute **PC-1 a PC-10** (y PC-11 si hace falta). Precondición de T-21: PC-10 con «Contratación confirmada» (el código exige contratación confirmada, CA-084).
3. **Cancelación:** `POST /eventos/<ev>/cancelacion` con `{"motivo": "El Cliente canceló"}`. Esperado: HTTP **200**; mensaje `Evento cancelado.`, `datos` vacío.
4. **Comprobaciones GET:**
   - `GET /eventos/<ev>/administracion` → `estadoEvento: "Cancelado"`.
   - `GET /solicitudes?evento_id=<ev>` → `{"solicitudes": []}` (este evento no tiene solicitudes; copie `<ev>` completo, porque un carácter distinto también devuelve una lista vacía).
   - Opcional, solo lectura: `GET /eventos/EV-89ab606e-6eef-42c4-9627-3142e7d89b3b/administracion` → sigue `Cancelado`, sin cambios.
5. **Qué comprobar en Swagger:** HTTP 200 en la cancelación; `Cancelado` en el evento **nuevo**; el `evento_id` usado es distinto del principal.
6. **Capturas a guardar:** PC-1 (con el `evento_id`), PC-10 (contratación confirmada), petición y respuesta de la cancelación y el GET de administración posterior. Nombre sugerido: `T21b_<paso>_AAAAMMDD-HHMM.png`.
7. **Bitácora:** fecha y hora, `<ev>`, HTTP de cada paso, estado antes y después, Aprobado/Fallido/Bloqueado.

### 11.3 T-23 — servicio adicional con menos de cinco días naturales

**Qué debe demostrar:** HTTP 201, estado `No procedente` y motivo `Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).`, con la contratación **realmente confirmada** y **sin saldo vencido**. Si el motivo es otro, no se declara aprobada la finalidad específica de la prueba.

**Aclaración sobre el plazo del saldo (comprobada en el BRD y en el código).** El saldo del contrato original debe quedar liquidado «como máximo tres días hábiles antes de la fecha del evento» (BRD; GL-012; `registrar_obligacion_saldo_original` con `PlazoPago.dias_habiles_antes_de(fecha_evento, 3)`, límite exclusivo a las 00:00 del día siguiente, E-1). **No** son siete días naturales: los siete días naturales son el umbral del cargo por cambio tardío (BN-003, SE-005), que no interviene en T-23.

**Por qué importa la fecha (reglas implementadas y aprobadas):**

- Para que falle por plazo, el evento debe estar a **menos de cinco días naturales** (diferencia de fechas de calendario entre AHORA y el evento ≤ 4, `AnticipacionSolicitud.dias_naturales`) y **en el futuro** (si `AHORA ≥ fecha_hora`, el evento cuenta como iniciado y el motivo sería otro).
- La solicitud evalúa en este orden: evento cancelado → condición temporal (evento iniciado y plazo de 5 días) → saldo vencido (`SOLICITUD_PUEDE_CONTINUAR`, `src/domain/especificaciones.py`; BRD: el saldo se comprueba «solo después de verificar que el evento no está cancelado ni haya iniciado y que falten al menos cinco días naturales»). Con el plazo incumplido el saldo **no se consulta**.
- **Aun así, esta guía exige un saldo legítimamente no vencido**, porque lo pidió el equipo para que la prueba no dependa de una deuda. El código marca un saldo como `Vencida` solo al ejecutar `POST /estados-cuenta/{id}/vencimiento-saldo-original`, pero una obligación cuyo límite ya pasó **no es válida solo porque siga `Pendiente`**: tiene el límite superado de hecho. Por eso la fecha del evento debe elegirse de modo que **la fecha límite del saldo (`fechaLimite`) sea posterior a AHORA** al enviar la solicitud.
- **No** se corrige el saldo pagándolo después de su límite: C-06 / CA-113 dicen que un pago posterior al límite no liquida directamente el saldo, y el código hoy lo liquida si el vencimiento aún no se registró (posible defecto D-2). Tampoco se ejecuta el endpoint de vencimiento ni el de protocolo de cobro.

**¿Existe un escenario coherente?** Sí, pero solo algunos días. Con la hora del servidor (UTC) y el evento a las 18:00, calculado con el calendario independiente de `tests/apoyo_esperados_oraculo.py` (margen mínimo de 2 horas sobre las 21:58):

| Día de ejecución (UTC) | Evento a AHORA + 3 días | Evento a AHORA + 4 días |
|---|---|---|
| lunes | jueves ✔ | viernes ✔ |
| martes | viernes ✔ | sábado ✔ |
| miércoles | sábado ✔ | domingo ✔ (límite el jueves a las 00:00 UTC: ejecutar a primera hora) |
| jueves, viernes, sábado | ✘ | ✘ |
| domingo | ✘ | jueves ✔ |

**Regla práctica:** ejecute T-23 de **domingo a martes** (UTC) con `FECHA_EV_T23` = **fecha de AHORA + 4 días a las 18:00** (diferencia de 4 días < 5; el límite del saldo cae después de AHORA). Si hoy fuera jueves, viernes o sábado (UTC), **no hay un escenario coherente** con las reglas actuales: espere al domingo. En la lectura del 28/10/2026 a las 21:58 UTC (miércoles) el margen era de unas dos horas, por lo que **no** es una fecha recomendable. Si en otro momento no se cumpliera la condición, la decisión pendiente es de negocio: qué significa «saldo no vencido» cuando el evento está tan próximo, o si T-23 debe probarse a nivel de pruebas automatizadas en vez de manualmente.

**Procedimiento:**

1. Consulte AHORA (`docker exec eventosnova-api-manual date`) y confirme que es domingo, lunes o martes (UTC). `<CLIENTE>` = `CL-PRUEBA-T23`; `<FECHA_EV>` = `FECHA_EV_T23` (AHORA + 4 días a las 18:00); `<COMPROBANTE>` = `C-T23-0001`. Las demás fechas, como en 11.0.
2. Ejecute **PC-1 a PC-10** (y PC-11 si hace falta). **No continúe** si PC-10 no muestra `Contratación confirmada` y `En organización`.
3. **Contratación confirmada, comprobada otra vez antes de solicitar el servicio:** `GET /eventos/<ev>/administracion` → `estadoEvento: "En organización"`, `contratos[0].estado: "Contratación confirmada"` y `fechaHora` posterior a AHORA.
4. **Saldo:** `GET /pagos-pendientes?evento_id=<ev>` → una fila `concepto: "SaldoContratoOriginal"`, `importe: "7000.00"`, `estado: "Pendiente"` y **`fechaLimite` posterior a AHORA** (compárela con la hora del servidor). Si `fechaLimite` ya pasó o dice `Vencida`, **deténgase y registre T-23 como *Bloqueado***: no se cumple la precondición.
5. **Solicitud:** `POST /solicitudes-servicio-adicional` con
   ```json
   {"evento_id": "<ev>", "contrato_id": "<ct>", "servicio": "Fotografía"}
   ```
   Esperado: HTTP **201**; `{"mensaje": "Solicitud No procedente.", "datos": {"solicitud_id": "SA-<uuid>", "estado": "No procedente", "motivo": "Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083)."}}`.
6. **GET de verificación:** `GET /solicitudes?evento_id=<ev>` → una fila `tipoSolicitud: "servicio adicional"`, `estadoActual: "No procedente"`, `pendiente: false`. Repita `GET /pagos-pendientes?evento_id=<ev>` → el saldo sigue `Pendiente`.
7. **Qué comprobar en Swagger:** HTTP 201 + `No procedente` + **ese texto de motivo**, con contratación confirmada (pasos 2 y 3), saldo no vencido (pasos 4 y 6) y evento no iniciado (paso 3). Si el `motivo` fuera otro, anótelo: la prueba **no** queda aprobada en su finalidad específica.
8. **Capturas a guardar:** PC-10; los pasos 3 y 4 (con la hora AHORA a la vista, por ejemplo en la bitácora); petición y respuesta completas del paso 5 (con el `motivo`); los GET del paso 6. Nombre sugerido: `T23b_<paso>_AAAAMMDD-HHMM.png`.
9. **Bitácora:** fecha y hora, AHORA consultada, `FECHA_EV_T23`, `<ev>`, `<ct>`, `fechaLimite` del saldo, HTTP, `motivo` literal, estado, Aprobado/Fallido/Bloqueado.

**Defecto relacionado (D-1, corregido en el código el 28/10/2026):** el BRD, GL-015, C-14 y **CA-101** exigen que, con la contratación no confirmada, el servicio adicional **no se registre** (ni se evalúe plazo ni saldo). `registrar_solicitud_servicio_adicional` ya rechaza ese caso con HTTP 422 y el mensaje «Un servicio adicional solo puede registrarse con la contratación confirmada (CA-101).» (26 pruebas de regresión en `tests/test_d1_servicio_adicional_contratacion_confirmada.py`). **Pero las API en marcha (puertos 8000 y 8001) siguen con la imagen anterior** hasta que el equipo reconstruya la imagen y recree `api` y `api-manual`: la primera ejecución manual de T-23 (contrato sin confirmar) devolvió 201 `No procedente` en lugar del rechazo que exige CA-101. T-23 se repite con la contratación confirmada, así que el resultado esperado no depende de la corrección. Detalle en `docs/architecture/CIERRE_AUDITORIA_FINAL.md`, secciones J y M.


---

## 12. Pruebas manuales finales con el código actualizado (T-21, T-23 y T-24)

> **Esta sección sustituye, para la ejecución, a las secciones 1 y 11 en lo que difieran.** Las pruebas las realiza el equipo. *(29/10/2026: ejecutadas; T-21, T-23 y T-24 aprobadas según los resultados informados, sección 10.1.)* Esta versión de la guía asume el código con las correcciones D-1, D-2 y D-3 (CIERRE §O) y las imágenes reconstruidas.

### 12.0 Qué abrir y qué comprobar antes de empezar

| Qué | Dirección |
|---|---|
| Swagger de las pruebas (**el único donde se escribe**) | http://127.0.0.1:8001/docs |
| OpenAPI | http://127.0.0.1:8001/openapi.json |
| Salud / preparación | http://127.0.0.1:8001/health · http://127.0.0.1:8001/ready (`{"estado":"ok","persistencia":"postgresql","base_de_datos":"ok"}`) |
| Desarrollo (**no escribir**) | http://127.0.0.1:8000/docs |

Antes de empezar: (1) `docker ps` debe mostrar `eventosnova-api-manual` (healthy) y `eventosnova-worker-manual` en ejecución; (2) **el reloj de negocio**: la API y el trabajador usan la hora de pared de **America/Mexico_City** sin zona (TP-06, `application.reloj.reloj_negocio`). Compruébelo: `docker exec eventosnova-api-manual python -c "from application.reloj import reloj_negocio; print(reloj_negocio())"` debe mostrar la hora local de la Ciudad de México (no UTC). **Si responde `ModuleNotFoundError`, las imágenes son anteriores a esta corrección: reconstrúyalas antes de seguir** (ver 12.0 bis); `docker exec … date` muestra UTC y **no** es la referencia; (3) **no use** `EV-89ab606e-6eef-42c4-9627-3142e7d89b3b`, `EV-2edfbcd8-…`, `EV-8e2a6f41-…` ni ningún evento de la base de desarrollo.

### 12.0 bis Antes de la primera prueba: imágenes con el código actual

Los contenedores deben ejecutar una imagen que incluya D-1, D-2, D-3 y el reloj de negocio. Si el comando de 12.0 (2) falla con `ModuleNotFoundError`, reconstruya y recree (no toca la base de datos, el volumen ni `db`; **nunca** `down -v`):

```powershell
docker compose build api worker
docker compose up -d --no-deps api worker
docker compose -f docker-compose.manual-test.yml up -d --force-recreate
```

y repita 12.0 (`/ready` en 8000 y 8001 y el comando del reloj).

### 12.1 Cómo obtener las fechas y los cuerpos JSON

Desde la raíz del proyecto (solo lectura; no llama a ninguna API ni escribe en ninguna base):

```powershell
.\.venv\Scripts\python.exe scripts\preparar_pruebas_manuales.py t21
.\.venv\Scripts\python.exe scripts\preparar_pruebas_manuales.py t23
.\.venv\Scripts\python.exe scripts\preparar_pruebas_manuales.py t24
```

Cada comando imprime, **con las fechas ya calculadas para la hora de negocio actual (America/Mexico_City, la misma que usan la API y el trabajador)**, cada paso con su endpoint, su JSON y el resultado esperado; los identificadores aparecen como `<evento_id>`, `<propuesta_id>`, `<contrato_id>`, `<estado_cuenta_id>`, `<obligacion_id>` y `<pago_id>`. Ejecútelo justo antes de cada prueba (las fechas dependen de la hora) y avisa si **hoy no se puede ejecutar** (T-23). Para planificar otro momento: `--ahora 2026-11-02T10:00` (hora de la Ciudad de México). Todas las fechas de los JSON son horas de pared de la Ciudad de México, como las demás fechas del sistema.

### 12.2 De dónde se copia cada identificador

| Identificador | Dónde aparece |
|---|---|
| `evento_id` | respuesta de PC-1 (`POST /eventos`) |
| `propuesta_id` | respuesta de PC-2; **`version_id` = `<propuesta_id>-v1`** (ninguna respuesta lo devuelve; es la convención de `Propuesta.__init__`) |
| `contrato_id` | respuesta de PC-4, en `datos.contrato_id` |
| `estado_cuenta_id` y `obligacion_id` | PC-7, `GET /pagos-pendientes?evento_id=<evento_id>` (campos `estadoCuentaId` y `obligacionId` de la fila `Anticipo`) |
| `pago_id` | **solo** en la respuesta de PC-8 (`datos.pago_id`) |

Copie cada `evento_id` **completo**: un carácter distinto hace que `GET /solicitudes?evento_id=` devuelva una lista vacía sin error.

### 12.3 Cuerpos comunes de la contratación (PC-1 a PC-9)

Se ejecutan en este orden para T-21, T-23 y T-24 (las fechas y los valores concretos los imprime el script):

```json
POST /eventos
{"cliente_id": "CL-PRUEBA-T21", "datos": {"tipo": "Boda", "fecha_hora": "<FECHA_EV>", "lugar": "Salón Nova", "invitados_aproximados": 120}, "servicios": ["Banquete", "Fotografía"]}
POST /eventos/<evento_id>/propuestas
{"servicios": ["Banquete", "Fotografía"], "proveedores_considerados": ["PV-1"], "costo_total": "10000.00", "condiciones": "Condiciones generales"}
POST /propuestas/<propuesta_id>/aceptacion
{"version_id": "<propuesta_id>-v1"}
POST /propuestas/<propuesta_id>/contrato
{"politica_incluida": true}
POST /contratos/<contrato_id>/comunicacion-politica-no-reembolso
{"fecha": "<FIRMA>"}
POST /contratos/<contrato_id>/firma
{"fecha": "<FIRMA>"}
GET  /pagos-pendientes?evento_id=<evento_id>
POST /estados-cuenta/<estado_cuenta_id>/pagos
{"obligacion_id": "<obligacion_id>", "importe": "3000.00", "fecha": "<FECHA_PAGO>", "comprobante": "<COMPROBANTE>", "registrado_en": "<REGISTRO_PAGO>", "verificar_ahora": false}
POST /estados-cuenta/<estado_cuenta_id>/pagos/<pago_id>/verificacion
{"verificado_en": "<VERIFICACION>"}
GET  /eventos/<evento_id>/administracion
```

Resultados esperados: 201 «Evento registrado En gestión.», 201 «Propuesta creada.», 200 «Propuesta aceptada.», 201 «Contrato preparado.», 200, 200 «Contrato firmado.», fila `Anticipo` `3000.00` `Pendiente`, 201 «Pago Registrado.», 200 «Pago Verificado.» y, **PC-10**, `estadoEvento: "En organización"`, `contratos[0].estado: "Contratación confirmada"`, `estadosCuenta[0].anticipo.estado: "Liquidada"`. (La verificación confirma la contratación automáticamente; si PC-10 aún no lo muestra, `POST /contratos/<contrato_id>/confirmacion`.) El anticipo (3000.00) es el 30 % de `costo_total` 10000.00. Comprobante único por evento (`C-T21-0001`, `C-T23-0001`, `C-T24-0001`).

**Regla nueva (D-3b):** la contratación **no puede confirmarse en T ni después** (CA-110): todas las fechas de PC (`FIRMA`, `FECHA_PAGO`, `REGISTRO_PAGO`, `VERIFICACION`) deben ser anteriores a `fecha_hora` del evento. Un evento con `fecha_hora` pasada ya no se puede contratar (la verificación del anticipo no lo confirma y `POST …/confirmacion` responde 422 «La contratación ya no puede confirmarse…»).

### 12.4 T-21 — cancelación de un evento independiente

1. `…\preparar_pruebas_manuales.py t21`. Evento a 30 días, `CL-PRUEBA-T21`, comprobante `C-T21-0001`.
2. Ejecute PC-1 a PC-10; **siga solo si PC-10 muestra «Contratación confirmada»**.
3. `POST /eventos/<evento_id>/cancelacion` con `{"motivo": "El Cliente canceló"}` → HTTP **200**, mensaje `Evento cancelado.`
4. `GET /eventos/<evento_id>/administracion` → `estadoEvento: "Cancelado"`; `GET /solicitudes?evento_id=<evento_id>` → `{"solicitudes": []}`.
5. (Solo lectura) el evento principal `EV-89ab606e-…` sigue `Cancelado` y no se tocó.

**Qué comprobar en Swagger:** 200 en la cancelación, `Cancelado` en el evento **nuevo** y que es distinto del principal.
**Capturas:** PC-1 (con el `evento_id`), PC-10, la cancelación (petición y respuesta) y el GET posterior. Nombre: `T21b_<paso>_AAAAMMDD-HHMM.png`.

### 12.5 T-23 — servicio adicional con menos de cinco días naturales

1. `…\preparar_pruebas_manuales.py t23`. **Si el script dice «NO EJECUTE T-23 HOY», no continúe**: solo se puede de domingo a martes (hora de negocio) —o el miércoles temprano— con el evento a +4 días, para que el límite del saldo (3 días hábiles antes del evento, a las 00:00 del día siguiente) sea posterior a AHORA. (Con la hora de esta verificación, miércoles 28/10/2026 19:41 de la Ciudad de México, el script la marca ejecutable solo hasta poco antes de la medianoche, porque el límite es el jueves 29/10 a las 00:00; después, el primer día válido es el domingo 01/11/2026.)
2. Ejecute PC-1 a PC-10; siga solo con «Contratación confirmada».
3. `GET /pagos-pendientes?evento_id=<evento_id>` → fila `SaldoContratoOriginal`, `importe` `7000.00`, `estado` `Pendiente` y **`fechaLimite` posterior a la hora de negocio**. Si no: T-23 queda *Bloqueado*. **No ejecute** `POST …/vencimiento-saldo-original` ni el protocolo de cobro.
4. `GET /eventos/<evento_id>/administracion` → «En organización», «Contratación confirmada» y `fechaHora` futura.
5. `POST /solicitudes-servicio-adicional` con `{"evento_id": "<evento_id>", "contrato_id": "<contrato_id>", "servicio": "Fotografía"}` → HTTP **201**, `estado` `No procedente`, `motivo` «Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).»
6. `GET /solicitudes?evento_id=<evento_id>` → `servicio adicional`, `No procedente`, `pendiente: false`; `GET /pagos-pendientes?evento_id=<evento_id>` → el saldo sigue `Pendiente`.

**Nota (D-2, GL-049/SE-006):** si el límite del saldo ya hubiera pasado y lo pagado dentro del plazo no lo cubriera, el saldo estaría vencido **de hecho** (aunque siga `Pendiente`) y una solicitud nueva se detendría por saldo vencido; por eso el paso 3 exige un `fechaLimite` futuro. Con el plazo de cinco días incumplido, esa comprobación no llega a hacerse.

**Qué comprobar:** 201 + `No procedente` + **ese motivo literal**, con la contratación confirmada (pasos 2 y 4), el saldo no vencido (paso 3) y el evento no iniciado. Con otro motivo, T-23 no queda aprobada en su finalidad.
**Capturas:** PC-10; el paso 3 (con la hora de negocio anotada); el paso 4; petición y respuesta del paso 5; los GET del paso 6. Nombre: `T23b_<paso>_AAAAMMDD-HHMM.png`.
**Opcional (D-1):** en otro evento con el contrato **solo firmado** (haga PC-1 a PC-6), `POST /solicitudes-servicio-adicional` debe dar **422** «Un servicio adicional solo puede registrarse con la contratación confirmada (CA-101).»

### 12.6 T-24 — solicitud de cambio después de iniciado el evento

El evento debe estar **contratado antes de T y llegar a T durante la prueba**: la fecha del evento es **AHORA + 40 minutos**.

1. `…\preparar_pruebas_manuales.py t24` (imprime la hora exacta de inicio). `CL-PRUEBA-T24`, comprobante `C-T24-0001`.
2. Ejecute PC-1 a PC-10 **sin demorarse** (todas las fechas del script son anteriores a la hora de inicio); siga solo con «Contratación confirmada» y «En organización».
3. Espere a la hora de inicio. El trabajador (`eventosnova-worker-manual`) inicia el evento solo, en unos segundos (D-3): `GET /eventos/<evento_id>/administracion` → `estadoEvento: "En ejecución"`. (Si no cambiara, `POST /eventos/<evento_id>/inicio` lo inicia.)
4. `POST /solicitudes-cambio` con `{"evento_id": "<evento_id>", "contrato_id": "<contrato_id>", "descripcion": "Cambiar la hora", "tarifa_vigente": "500.00"}` → HTTP **422**, `tipo` `rechazo_de_negocio`, `detalle` «El cambio solo procede después de contratar y antes del inicio (CA-039).» (`500.00` es solo un valor de ejemplo: el importe de la tarifa no está definido en las fuentes).
5. `GET /solicitudes?evento_id=<evento_id>` → `{"solicitudes": []}`.

**Qué comprobar:** el evento pasó solo a `En ejecución` y el cambio se rechazó con CA-039.
**Capturas:** PC-10 (con la hora a la vista), el GET con `En organización` antes de la hora, el GET con `En ejecución` después, y el 422 del paso 4. Nombre: `T24b_<paso>_AAAAMMDD-HHMM.png`.
**Opcional (D-3 / D-3b):** registre otro evento con `fecha_hora` **pasada** (PC-1 solamente): el trabajador lo cierra solo en unos segundos (`GET /eventos/<evento_id>/administracion` → «Cerrado sin contratación», C-01) y ya no admite propuesta (`POST /eventos/<evento_id>/propuestas` → 422 «El evento no existe o no está En gestión.»).

### 12.7 Capturas, bitácora y resultados que debe compartir

- **Cuándo capturar:** inmediatamente después de cada paso marcado arriba, con la petición, el código HTTP y el cuerpo visibles; guárdelas fuera del repositorio o en una carpeta que usted cree (no en `tests/evidencias/` sin revisar).
- **Para cada prueba anote** (sección 9): fecha y hora de negocio (Ciudad de México) de cada paso, `evento_id`, `contrato_id`, HTTP de cada paso, `motivo` literal, estado final y Aprobado/Fallido/Bloqueado; y **cualquier desvío** (otro evento, otro orden, un paso repetido).
- **Resultados que debe compartir** para actualizar el reporte final: por T-21, T-23 y T-24, los códigos HTTP y las respuestas JSON de PC-10 y del paso decisivo, la hora de negocio, el `fechaLimite` del saldo (T-23) y la hora a la que el evento pasó a `En ejecución` (T-24), más las capturas.
- **Quedan pendientes hasta recibirlos:** el registro de T-21, T-23 y T-24 en `CIERRE_AUDITORIA_FINAL.md` §I, la regeneración del PDF de entrega y de la presentación con esos resultados, la última fila de la bitácora de IA, y la decisión de dar por cerrada la etapa 2. *(29/10/2026: resultados registrados en la sección 10.1 y en `CIERRE_AUDITORIA_FINAL.md` §Q; PDF, presentación y bitácora actualizados con ellos. Siguen pendientes el archivado de las capturas y la plantilla de la sección 9.)*
