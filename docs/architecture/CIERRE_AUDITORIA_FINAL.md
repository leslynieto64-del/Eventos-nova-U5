# Cierre de la auditoría final — Eventos Nova (PIA)

> **Estado vigente (2026-10-29): ver la sección Q.** D-1, D-2 y D-3 están corregidos en el código; la última ejecución registrada de la suite es de **1415 pruebas aprobadas en Docker con cobertura de 98,82 % de sentencias y 95,77 % de ramas** (`tests/evidencias/ejecucion-docker-final-20261028-202102.txt`); T-21, T-23 y T-24 con el código corregido resultaron **satisfactorias** según los resultados informados por el equipo. Siguen sin aprobación externa las decisiones internas (ADR-007, ADR-008) y sin existir el repositorio remoto, la CI ejecutada en GitHub y el despliegue. Las secciones anteriores se conservan como historial fechado.

> **Actualización 2026-10-25 (posterior a este informe).** Se implementaron las decisiones E-1 a E-4 (detalle y estado de aprobación en [`DECISIONES_E1_E4.md`](DECISIONES_E1_E4.md)). Las cifras de este informe (1250 pruebas, 98,82 % / 95,86 %) corresponden a la auditoría del 24/10 y quedan **superadas** por las siguientes, medidas sin paralelismo después de los cambios:
>
> | Entorno | Pruebas | Aprobadas | Fallidas | Errores | Omitidas | rc | Evidencia |
> |---|---|---|---|---|---|---|---|
> | Equipo (PostgreSQL obligatorio) | 1306 | 1306 | 0 | 0 | 0 | 0 | `tests/evidencias/ejecucion-pruebas-e1-e4-host-20261025.txt` |
> | Docker (`tests`, imagen reconstruida) | 1306 | 1306 | 0 | 0 | 0 | 0 | `tests/evidencias/ejecucion-pruebas-e1-e4-docker-20261025.txt` |
>
> Cobertura (`.coveragerc` sin cambios): **98,82 % de sentencias (5379 de 5443) y 95,85 % de ramas (1016 de 1060)** (`tests/evidencias/cobertura-e1-e4-20261025.txt`). Los nombres de prueba aprobados coinciden entre equipo y Docker.
>
> **Oráculo histórico:** `comportamiento_estado_cuenta_v8_e3c.json` no se editó (SHA-256 `d98b4cff…`). Sus 1203 claves se comparan con un esperado derivado de las reglas (E-1, H-10, E-3/E-4), sin código de producción; recuento exacto con identificadores en `tests/evidencias/diferencias-oraculo-e1-e4-20261025.txt`. **Pendiente de autorización:** que la responsable apruebe formalmente ese método. **E-2, E-3 y E-4 siguen sin aprobación formal.** Las preguntas E-1 a E-4 de la sección E ya no son preguntas abiertas de implementación sino decisiones del equipo por confirmar. Las secciones siguientes se conservan como el registro del 24/10.
>
> **Servicios y humo (2026-10-25):** `api` y `worker` se reconstruyeron y recrearon con el código actual (sanos; `/ready` con `persistencia: postgresql`, `/health` y `/docs` 200; Alembic 0004; datos de desarrollo sin cambios). Pruebas de humo por HTTP sobre PostgreSQL en una base temporal: E-2/E-3/E-4 15 de 15, E-1 7 de 7, Outbox sin duplicados (`tests/evidencias/humo-api-*-20261025.txt`). Detalle en `PROGRESO_FASE_FINAL.md`, que también registra la aclaración del límite exacto de E-1, la prueba del servicio `migrate` en una base aislada y la revisión de la presentación en PowerPoint.
>
> **Verificación final de entregables (2026-10-25):** (1) el `mapa-dominio.pdf` del repositorio **no corresponde a la versión actual de `mapa-dominio.drawio`**: es byte a byte el del 24/10 (SHA-256 `75b0d7b9…`, igual al del respaldo `…ANTES_POSTGRESQL_20261024`) y conserva la etiqueta anterior a E-3/E-4; no se encontró en el equipo ningún PDF más reciente, así que **sigue pendiente exportarlo desde draw.io y guardarlo en `diagramas/dominio/`**; (2) las cifras del PDF de entrega y de la presentación (1306; 98,82 %; 95,85 %) coinciden con las evidencias; (3) `migrate` tiene el contenedor creado con `eventosnova-app:local` y `docker compose up --no-start migrate` no lo recrea (configuración al día), con Alembic en 0004; (4) los hashes del cierre de alcance y del oráculo coinciden con los registrados; `.env` sigue sin versionarse (no hay hash registrado de `.env`).
>
> **Dictamen vigente (2026-10-25): LISTO PARA ENTREGA CON PENDIENTES DOCUMENTADOS.** Pendientes: aprobación externa, si el curso la exige, de E-2, E-3, E-4, del control de comprobante repetido, de la fecha efectiva de un parcial y del método de validar el oráculo; ejecución de la CI en GitHub, repositorio publicado y despliegue; revisión visual de la presentación y del diagrama `mapa-dominio` (su PDF no se regeneró).

Fecha de la auditoría: 2026-10-24 (hora del equipo). Rama: `fix/auditoria-integral`. Carpeta: `C:\Users\YAZMIN\Downloads\5to semeste\CLNEG\Eventosnova`. Sin remoto Git configurado. No se hicieron commits, push, publicación ni despliegue.

## A. Resumen ejecutivo

El sistema funciona y está probado: **1250 pruebas aprobadas tanto en el equipo como en Docker (mismas 1250 pruebas, comprobado por nombre)**, cobertura **98,82 % de sentencias y 95,86 % de ramas**, cuatro migraciones aplicadas con una sola cabeza (0004), esquema real idéntico a los metadatos, datos conservados tras reiniciar el contenedor de la API.

La auditoría **encontró y corrigió** tres cosas reales: (1) las pruebas fallaban dentro de Docker por un defecto de `.dockerignore` que esta misma sesión había hecho visible (y que habría roto también el trabajo `docker` de la CI); (2) el respaldo del cierre por falta de pago de un servicio adicional estaba subestimado como «parcial»: el BPMN SP-04 aprobado lo modela de forma explícita; (3) el informe anterior afirmaba «1241 pruebas en Docker», pero esa cifra no se había medido (las ejecuciones en Docker fueron 1214 y 1236, y coincidían con las del equipo en su momento); se corrigieron los documentos.

Siguen **pendientes de autorización** de la responsable: la regla de vencimiento GL-060/C-15 para anticipo, saldo y devolución SE-012; la coherencia solicitud–contrato–evento; y dos interpretaciones de pagos de la regla B. Siguen **bloqueados por recursos externos**: ejecución de la CI en GitHub, repositorio publicado, despliegue y URL pública.

**Dictamen: LISTO PARA ENTREGA CON PENDIENTES DOCUMENTADOS** (sección H).

## B. Tabla de auditoría

| Asunto | Estado | Fuente o requisito | Evidencia comprobada | Corrección realizada | Pruebas ejecutadas | Pendiente o autorización necesaria |
|---|---|---|---|---|---|---|
| Integridad del cierre de alcance | VERIFICADO | Cierre aprobado | SHA-256 `b67d2f47…487a` igual al de `MANIFIESTO_SHA256.txt`; archivo sin cambios | — | — | — |
| Estado de partida | VERIFICADO | Reglas de seguridad | 163 entradas en `git status` al inicio (guardadas fuera del repositorio); `.env`, base de desarrollo (2 eventos, 1 propuesta) y respaldo intactos | — | — | — |
| C-15 / GL-060 — vencimiento de plazos en días hábiles | PENDIENTE DE AUTORIZACIÓN | GL-060, C-15, cierre §6 | `tests/evidencias/auditoria-plazos-gl060-20261024.txt`: de 6 plazos en días hábiles, solo la devolución del anticipo (decisión A) cumple; anticipo, seguimiento del anticipo, saldo, límite de sustitución y devolución SE-012 conservan la hora de partida | Ninguna (ver §E-1) | `scripts/auditar_plazos_dias_habiles.py` (solo lectura) | Autorizar el cambio y el recálculo del oráculo |
| Oráculo histórico (`comportamiento_estado_cuenta_v8_e3c.json`) | PENDIENTE DE AUTORIZACIÓN | Cierre §6 (BL-2) | El único procedimiento documentado (§6) cuenta diferencias y registra la evidencia y dice expresamente «No se edita el JSON de referencia»; no autoriza sustituirlo. Captura de solo lectura con el código actual: 1203 claves, 42 diferencias (las mismas 42 que cita el cierre); JSON sin modificar (hash `d98b4cff…`) | No se editó el JSON ni se alteraron pruebas | Captura de solo lectura | Autorización explícita para regenerar o redefinir el oráculo |
| Coherencia solicitud–contrato–evento (evento B con contrato A) | PENDIENTE DE AUTORIZACIÓN | BRD, US, glosario, cierre, BPMN, matriz | Reproducible por `POST /solicitudes-cambio` y `POST /solicitudes-servicio-adicional` (prueba `test_riesgo_coherencia_solicitud_contrato_evento`); `POST /sustituciones` recibe también ambos ids (verificado por lectura de código, no reproducido por prueba). Ninguna fuente exige la coincidencia; el glosario define el estado de cuenta «por contrato… del evento» y aclara que «no introduce reglas de negocio nuevas» | Ninguna | `test_riesgo_coherencia_solicitud_contrato_evento` (3 OK) | Responder la pregunta E-2 |
| Cierre por falta de pago de servicio adicional (24 h) | CORREGIDO Y REVERIFICADO (documentación y pruebas) | CA-082, US-025, glosario («Pendiente»), BPMN SP-04, matriz (evento `ServicioAdicionalCerradoPorFaltaDePago`) | El BPMN SP-04 contiene la compuerta «¿El Cliente efectuó el pago dentro de las 24 horas?» → «Cerrar la solicitud por falta de pago…» y «Registrar y verificar el pago, aunque sea después de las 24 horas». El código cumple: el plazo cuenta desde la comunicación, el límite exacto es inclusivo, un pago efectuado a tiempo y registrado después no cierra, uno tardío no evita el cierre | La trazabilidad dejó de marcar la operación como «respaldo parcial»: cita CA-082, US-025 y el BPMN, y el generador verifica que esos elementos existan en el `.bpmn`. Ninguna User Story ni CA enumera el cierre de forma literal (se declara) | `test_servicio_adicional_cierre_falta_pago` (8, nuevas), `test_trazabilidad_api` (6) | — |
| Anticipo mínimo — evaluar cada pago por separado | PENDIENTE DE AUTORIZACIÓN | Glosario GL anticipo; CA-019, CA-107, CA-108 | Los textos dicen «verifique el pago… cubre al menos el 30 %… Si el monto es inferior… corrección» y que un pago mayor o una segunda transferencia ≥ al mínimo se verifica sin devolución. Ningún texto trata la suma de pagos parciales. Es una decisión técnica asumida (cada pago se evalúa solo) | Ninguna | `test_reglas_anticipo_decisiones_abc` (clase B, 5) | Responder la pregunta E-3 |
| Anticipo mínimo — pago menor al mínimo sobre un anticipo ya liquidado | PENDIENTE DE AUTORIZACIÓN | Ídem | Comportamiento previo conservado (importe incorrecto); los textos aprobados solo cubren pagos ≥ al mínimo sobre un anticipo liquidado (CA-108) | Ninguna | Ídem y `test_estado_cuenta_maquina_estados` | Responder la pregunta E-4 |
| Decisiones A, B y C (devolución del anticipo, mínimo, no reembolso) | VERIFICADO | Cierre §1 | Implementadas y con pruebas (`test_reglas_anticipo_decisiones_abc` 25, `test_persistencia_devolucion_anticipo` 5, `test_h10_anticipo_liquidado`) | — | Suite completa | — |
| UUID completos e identificadores históricos | VERIFICADO | ADR-006 | `nuevo_id` = prefijo + UUID v4; `nuevo_id_libre` en las 7 creaciones; los ids de 8 caracteres (`EV-0028db33`) siguen en la base de desarrollo junto a un UUID; colisión forzada sin sobrescritura (memoria y PostgreSQL) | — | `test_identificadores` (10) | La garantía es estadística, no absoluta (declarado) |
| Control optimista, versiones y 409 | VERIFICADO | ADR-006 | Versión por raíz; conflicto reproducido con hilos reales (5 rondas) y con un conflicto real por HTTP (otro escritor avanza la versión entre lectura y guardado): 409, sin pago, sin eventos en el Outbox; el reintento posterior funciona | Se añadió la prueba del conflicto real por una ruta (`ConflictoRealEnLaApi`); antes solo se simulaba el error del servicio | `test_concurrencia_optimista` (14) | — |
| Outbox: reintentos y deduplicación | VERIFICADO | ADR-004 | Claves estables, reintento tras conflicto, paso a Revisión si persiste, reaplicar reacciones sin duplicar obligaciones, pagos ni devoluciones. Garantía real: **al menos una vez con deduplicación por reacción**, no «exactamente una vez» | — | `test_persistencia_outbox` (27), `test_concurrencia_optimista` | — |
| Migraciones 0001–0004 | VERIFICADO | — | Cadena lineal `0001←0002←0003←0004`, una sola cabeza; `upgrade` solo agrega (los `drop_column` están únicamente en `downgrade`); desarrollo y pruebas en 0004 con 22 tablas, 25 claves foráneas y 0 diferencias con los metadatos (`compare_metadata`) | — | `test_esquema_postgresql*`, `test_migraciones_ciclo`; script de auditoría de solo lectura | — |
| Migraciones creadas frente a aplicadas | VERIFICADO | — | Creadas: 0001–0004. Aplicadas: a la base de desarrollo (`eventosnova`) y a la de pruebas (`eventosnova_test`) hasta 0004; la base desechable `eventosnova_migraciones_test` se usa para subida/bajada y no se tocó la de desarrollo con `downgrade` | — | — | — |
| Persistencia tras reiniciar la API | VERIFICADO | PIA | `docker restart eventosnova-api-1`: `/ready` ok, mismos 2 eventos y 1 propuesta antes y después, `/docs` 200 (`GET /eventos` sin parámetros responde 422: exige `desde` y `hasta`) | — | — | — |
| Suite completa en el equipo | VERIFICADO | PIA | 1250 pruebas, 0 fallos, 0 errores, 0 omitidas, código de salida 0 | — | Ver §C | — |
| Suite completa en Docker | CORREGIDO Y REVERIFICADO | PIA | Primer intento: 1250 pruebas, **3 errores** (`FileNotFoundError` del `.bpmn` porque `.dockerignore` excluía todo `diagramas/bpmn`); tras la corrección: 1250 OK, código 0 | `.dockerignore` excluye ahora solo las exportaciones pesadas (`*.svg`, `*.png`, `*.pdf`, `*.drawio`) y conserva los `.bpmn` | Ver §C (intento fallido conservado como evidencia) | — |
| Diferencia 1241 (equipo) frente a 1214 (Docker) | CORREGIDO Y REVERIFICADO | — | **No era una diferencia entre entornos.** Cronología medida: etapa 3: equipo 1214 = Docker 1214; etapas 8–9: equipo 1236 = Docker 1236; después se añadieron pruebas de OpenAPI y del BRD (equipo 1241) sin reconstruir la imagen ni repetir Docker. El «1241 en Docker» del informe anterior era una cifra no medida | Documentos corregidos (`PROGRESO_FASE_FINAL.md`, `auditoria-final-pia.md`); comprobación de que host y Docker ejecutan **el mismo conjunto de 1250 pruebas por nombre** | Ver §C | — |
| Cobertura | VERIFICADO | PIA ≥ 80 % | `.coveragerc` sin cambios (`source = src`, ramas): 5365 de 5429 sentencias (98,82 %), 1018 de 1062 ramas (95,86 %). No se tocaron exclusiones ni denominadores | — | `scripts/verificar_cobertura.py` (rc 0) | — |
| OpenAPI | VERIFICADO | PIA | `docs/api/openapi.json` coincide con la API actual (60 operaciones) | — | `test_openapi_exportada` (2) | — |
| Integraciones externas | VERIFICADO | BRD, glosario | Todas siguen **simuladas** y así se declaran (`integraciones-externas.md`) | — | `test_integraciones_simuladas` (13) | Fuentes reales (pasarela, notificaciones, disponibilidad) |
| Documentos de entrega (existencia y contenido) | VERIFICADO | PIA | Existen y se abren: `docs/BRD.md`, `docs/api/openapi.json`, `PROGRESO_FASE_FINAL.md`, `integraciones-externas.md`, `ci-cd-y-despliegue.md`, complemento, auditorías, ADR-006, README, evidencias | Se corrigieron contradicciones objetivas (respaldo «parcial», cifra de Docker) | `test_brd_markdown`, `test_auditoria_requisitos`, `test_trazabilidad_api` | — |
| Reporte PDF final | CORREGIDO Y REVERIFICADO | PIA | `docs/entrega/Reporte_Final_PIA_Eventos_Nova.pdf`, 7 páginas, **revisadas visualmente** (render a imagen): sin texto cortado | Regenerado con las cifras de esta auditoría (1250 pruebas, 98,82 %/95,86 %, 18 rutas con respaldo explícito) | — | Revisión del equipo antes de subirlo |
| Presentación (9 diapositivas) | CORREGIDO Y REVERIFICADO (contenido); NO VERIFICADO (visual) | PIA | `docs/entrega/Presentacion_Defensa_Eventos_Nova.pptx` se abre con python-pptx: 9 diapositivas; la novena **no tenía notas** (el informe anterior decía que todas las tenían) | Notas añadidas: ahora 9 de 9 | — | **Revisión visual no realizada** (no hay LibreOffice/PowerPoint en el entorno): revisarla en PowerPoint |
| CI validada estáticamente | VERIFICADO | PIA | `actionlint` sin errores (rc 0) sobre `.github/`; el defecto de Docker encontrado arriba habría roto el trabajo `docker` | `.dockerignore` | — | — |
| CI ejecutada realmente en GitHub | BLOQUEADO POR RECURSOS | PIA | `git remote -v` vacío; no hay `gh` ni credenciales | — | — | Publicar y ejecutar |
| Repositorio publicado / historial de commits de esta fase | BLOQUEADO POR RECURSOS | PIA | Sin remoto; 169 entradas sin versionar o modificadas; no se hicieron commits (prohibido) | — | — | Versionar y publicar |
| Sistema desplegado y URL pública | BLOQUEADO POR RECURSOS | PIA | No hay plataforma, credenciales ni URL; no se inventó ninguna | — | — | Desplegar y comprobar |
| Revisión visual de la presentación y de los diagramas UML de clases | NO VERIFICADO | PIA | Los UML de clases son anteriores a la persistencia (declarado) | — | — | Regenerar `clases_3_cqrs_infraestructura` |

## C. Resultados técnicos

| Ejecución | Comando exacto | Inicio → fin | Pruebas | Aprobadas / fallos / errores / omitidas | Código | Entorno | Evidencia |
|---|---|---|---|---|---|---|---|
| Línea base, equipo (con una prueba nueva añadida durante la ejecución) | `EVENTOSNOVA_REQUIERE_BD=1 .venv\Scripts\python.exe -m coverage run --rcfile=.coveragerc -m unittest discover -s tests -v` | 18:44 → 18:50 | 1241 | 1240 / **1 fallo** / 0 / 0 | 1 | Windows 11, Python 3.13, PostgreSQL 18 en Docker | (salida no conservada en archivo; el fallo fue `test_auditoria_requisitos`: el documento generado cuenta los archivos de prueba y yo añadí `test_servicio_adicional_cierre_falta_pago.py` mientras corría; no es un defecto del sistema y se regeneró el documento) |
| Equipo, final | Ídem | 18:52:27 → 18:59:28 | **1250** | 1250 / 0 / 0 / 0 | **0** | Ídem | `tests/evidencias/ejecucion-pruebas-auditoria-final-host-20261024.txt` |
| Docker, intento 1 | `docker compose run --rm tests python -m unittest discover -s tests -v` | 19:00 → 19:02 | 1250 | 1247 / 0 / **3 errores** / 0 | 1 | Contenedor Linux python:3.13-slim, PostgreSQL 18 (servicio `db`) | `tests/evidencias/ejecucion-pruebas-auditoria-final-docker-intento1-fallido-20261024.txt` |
| Docker, final (tras corregir `.dockerignore` y reconstruir `tests`) | Ídem | 19:02:40 → 19:04:14 | **1250** | 1250 / 0 / 0 / 0 | **0** | Ídem | `tests/evidencias/ejecucion-pruebas-auditoria-final-docker-20261024.txt` |
| Cobertura | `coverage report` y `scripts/verificar_cobertura.py` sobre la ejecución final del equipo | — | — | 98,82 % sentencias, 95,86 % ramas | 0 | — | `tests/evidencias/cobertura-auditoria-final-20261024.txt` |
| Plazos (solo lectura) | `python scripts/auditar_plazos_dias_habiles.py` | — | — | tabla de 6 plazos | 0 | — | `tests/evidencias/auditoria-plazos-gl060-20261024.txt` |

- **Alembic:** una cabeza, `0004`; desarrollo y pruebas en `0004`; 22 tablas; 25 claves foráneas; 0 diferencias con los metadatos.
- **Docker:** `docker compose config --quiet` correcto; `api` sana, `worker` en marcha, `db` sana; imágenes reconstruidas; `/ready` → `{"estado":"ok","persistencia":"postgresql","base_de_datos":"ok"}`.
- **Persistencia:** los datos de desarrollo (2 eventos, 1 propuesta; ids de 8 caracteres y UUID) se conservan tras reiniciar la API.
- **Por qué dos conteos distintos en el pasado:** ver la fila «Diferencia 1241 frente a 1214» de la tabla B. Medido ahora: equipo y Docker ejecutan los mismos 1250 nombres de prueba.
- **Advertencia conocida:** deprecación de `httpx` en `starlette.testclient`.

## D. Cambios realizados en esta auditoría

| Archivo | Cambio |
|---|---|
| `.dockerignore` | Excluye solo `diagramas/bpmn/*.svg|png|pdf|drawio`; los `.bpmn` ahora van a la imagen de pruebas (corrige 3 errores en Docker y el trabajo `docker` de la CI) |
| `scripts/generar_trazabilidad_api.py` | Respaldo de `cierre-por-falta-de-pago` (servicio adicional) con BPMN SP-04; verificación de que los elementos del BPMN existen |
| `docs/architecture/trazabilidad-api-persistencia.md` | Regenerado (18 rutas con respaldo explícito, 0 parciales) |
| `docs/trazabilidad/auditoria-requisitos-fase-final.md` | Regenerado (incluye la nueva prueba) |
| `docs/trazabilidad/complemento-trazabilidad-fase-final.md`, `docs/trazabilidad/auditoria-final-pia.md`, `docs/architecture/PROGRESO_FASE_FINAL.md`, `README.md` | Correcciones objetivas: respaldo del servicio adicional, cifras de Docker, referencia a este informe |
| `tests/test_servicio_adicional_cierre_falta_pago.py` (nuevo) | 8 pruebas de regresión del plazo de 24 h (límite inclusivo, pagos antes y después, cierre idempotente) |
| `tests/test_concurrencia_optimista.py` | +1 prueba: conflicto real por HTTP (409, sin cambios, reintento correcto) |
| `scripts/auditar_plazos_dias_habiles.py` (nuevo) | Auditoría de solo lectura de GL-060 |
| `scripts/generar_entrega_pia.py` | Lee las evidencias de esta auditoría; notas en la diapositiva 9; texto de pendientes corregido |
| `docs/entrega/Reporte_Final_PIA_Eventos_Nova.pdf`, `docs/entrega/Presentacion_Defensa_Eventos_Nova.pptx` | Regenerados |
| `tests/evidencias/*auditoria*20261024.txt` (5 archivos nuevos) | Evidencias de esta auditoría (la del intento fallido de Docker se conserva) |
| `docs/architecture/CIERRE_AUDITORIA_FINAL.md` (nuevo) | Este informe |

No se modificó código de dominio, aplicación, infraestructura ni migraciones: no hubo defectos reproducibles con respaldo que lo exigieran. No se tocaron el cierre aprobado, `.env`, el oráculo ni ninguna base de datos.

## E. Decisiones pendientes (preguntas para la responsable del proyecto)

1. **Plazos en días hábiles (GL-060 / C-15).** El glosario aprobado dice que los plazos en días hábiles de anticipo, saldo y devoluciones vencen a las 00:00 del día siguiente al último día del plazo, con límite exclusivo. Hoy solo la devolución del anticipo lo hace; el anticipo (3 días hábiles tras la firma), el saldo (3 días hábiles antes del evento) y la devolución por solicitud no realizada conservan la hora de partida (ejemplo: firma jueves 10:00 → hoy vence el martes a las 10:00; según GL-060 vencería el miércoles a las 00:00). **¿Autoriza aplicar GL-060 a todos y recalcular el oráculo histórico según el procedimiento del cierre (§6)?** Impacto de sí: cambia el momento de vencimiento (sobre todo en las primeras horas) y obliga a regenerar el oráculo con su procedimiento. Impacto de no: queda una discrepancia documentada con el glosario.
2. **Coherencia solicitud–contrato–evento.** Hoy se acepta una solicitud de cambio o de servicio adicional con el evento B y el contrato del evento A, y sus cobros irían a la cuenta de A. **¿Debe rechazarse una solicitud cuyo evento no coincida con el del contrato?** Impacto de sí: una validación en los tres servicios de registro (opcionalmente una clave foránea compuesta) y pruebas nuevas. Impacto de no: queda el riesgo de datos cruzados, ya documentado.
3. **Anticipo y pagos parciales.** Hoy cada pago se evalúa solo: un pago menor al 30 % es «importe incorrecto» y se corrige con un pago nuevo. **¿Deben sumarse varios pagos parciales para cubrir el mínimo?** Impacto de sí: un anticipo podría liquidarse con varias transferencias y habría que decidir qué pasa con los pagos «incorrectos» ya registrados. Impacto de no: se conserva el comportamiento actual (CA-019 habla de «el monto» y de corrección con nueva verificación).
4. **Pago menor al mínimo sobre un anticipo ya liquidado.** Hoy se registra como «importe incorrecto». **¿Debe verificarse y tratarse como excedente (sin devolución ni aplicación), como ocurre con un pago ≥ al mínimo (CA-108)?** Impacto de sí: cambiaría el resultado de esos pagos. Impacto de no: se conserva el comportamiento actual.

## F. Entregables (rutas reales)

| Entregable | Ruta | Comprobado |
|---|---|---|
| Reporte final PDF | `docs/entrega/Reporte_Final_PIA_Eventos_Nova.pdf` (7 páginas) | Abierto, texto extraído y **revisado visualmente** |
| Presentación | `docs/entrega/Presentacion_Defensa_Eventos_Nova.pptx` (9 diapositivas, 9 con notas) | Abierto con python-pptx; **visual no verificado** |
| Léeme de la entrega | `docs/entrega/LEEME.md` | Existe |
| BRD en Markdown | `docs/BRD.md` | Existe; coincide con el `.docx` (prueba) |
| OpenAPI | `docs/api/openapi.json` | Coincide con la API (prueba) |
| Progreso | `docs/architecture/PROGRESO_FASE_FINAL.md` | Existe; corregido |
| Integraciones | `docs/architecture/integraciones-externas.md` | Existe |
| CI y despliegue | `docs/architecture/ci-cd-y-despliegue.md` | Existe |
| Trazabilidad | `docs/trazabilidad/complemento-trazabilidad-fase-final.md`, `auditoria-requisitos-fase-final.md`, `auditoria-final-pia.md`, `docs/architecture/trazabilidad-api-persistencia.md` | Existen; los generados están al día (prueba) |
| ADR | `docs/ADR/ADR-005-postgresql.md`, `ADR-006-concurrencia-optimista-e-identificadores.md`, `ADR-007-decisiones-funcionales-e1-e4.md` (añadido el 28/10/2026) | Existen |
| Evidencias de esta auditoría | `tests/evidencias/*auditoria*-20261024.txt` | Existen |
| Matriz aprobada | `docs/trazabilidad/matriz-trazabilidad.xlsx` | Sin modificar |

## G. Acciones manuales del equipo (por prioridad)

1. Responder las preguntas E-1 a E-4 (E-1 y E-2 son las que afectan reglas de negocio).
2. Revisar el PDF y **abrir la presentación en PowerPoint** para comprobar el diseño.
3. Versionar los archivos nuevos y modificados (hay 169 entradas), sin subir `.env`, `.coverage`, `htmlcov/` ni `.venv/`, y publicar el repositorio con su historial.
4. Anotar la URL del repositorio en el README y ejecutar la CI en GitHub (`workflow_dispatch`); confirmar que los dos trabajos (`pruebas` y `docker`) terminan en verde.
5. Desplegar siguiendo `docs/architecture/ci-cd-y-despliegue.md` (imagen `app`, PostgreSQL gestionado, `DATABASE_URL`, `EVENTOSNOVA_PERSISTENCIA=postgresql`, `alembic upgrade head`, trabajador del Outbox) y comprobar `/ready`, `/docs` y un flujo de negocio.
6. Anotar la URL real del despliegue en el README, el reporte y la presentación solo después de comprobarla.
7. Opcional: regenerar el diagrama UML `clases_3_cqrs_infraestructura` con los adaptadores SQL.

## H. Dictamen final

**LISTO PARA ENTREGA CON PENDIENTES DOCUMENTADOS.**

Justificación: no hay defectos críticos abiertos; la suite completa pasa en el equipo y en Docker con las mismas 1250 pruebas (0 fallos, 0 omitidas), la cobertura supera ampliamente el 80 %, las migraciones y el esquema real son coherentes y los datos persisten. Los hallazgos de esta auditoría (Docker, respaldo de la trazabilidad, cifras erróneas del informe anterior, notas de la presentación) se corrigieron y reverificaron.

No es «LISTO PARA ENTREGA» sin reservas porque: (a) hay tres decisiones de negocio sin autorización (GL-060/C-15, coherencia solicitud–contrato–evento, interpretaciones de pagos parciales); (b) la CI nunca se ha ejecutado en GitHub, el repositorio no está publicado y no hay despliegue ni URL, que son requisitos de la consigna que dependen de recursos externos; y (c) el diseño visual de la presentación no se pudo verificar. Nada de lo anterior se presenta como resuelto.

> **Actualización del dictamen (2026-10-28).** La frase «no hay defectos críticos abiertos» de esta sección **ya no puede afirmarse**: la sección J registra tres defectos de implementación frente a reglas aprobadas (D-1: servicio adicional sin contratación confirmada, CA-101; D-2: pago tardío del saldo, CA-113; D-3: inicio automático en T, CA-109/110) y la sección I deja T-21 y T-23 sin resultados válidos. Dictamen vigente: **ENTREGABLE DOCUMENTAL CON RESERVAS, NO CERRADO**: la documentación aprobada no se modificó y describe lo previsto, pero el código no la cumple en esos tres puntos hasta que una tarea autorizada los corrija.

> **Actualización del dictamen (2026-10-29).** El dictamen anterior queda superado por el de la sección Q.7.

## I. Validación manual en Swagger (T-14 a T-24) — registro del 2026-10-28

> **Actualización (2026-10-29):** T-21, T-23 y T-24 se repitieron con el código corregido y eventos independientes; resultados en la sección Q.1. Lo que esta sección dice que «no demuestra» queda cubierto allí para T-21 y T-23, con las limitaciones indicadas.

**Entorno:** API `eventosnova-api-manual` en `http://127.0.0.1:8001/docs`, base `eventosnova_manual_test` (Alembic 0004), trabajador independiente; el sistema de desarrollo (puerto 8000, base `eventosnova`) no se usó para escribir (2 eventos, sin cambios). Procedimiento: [`docs/pruebas-manuales/GUIA_PRUEBAS_MANUALES_T14_T24.md`](../pruebas-manuales/GUIA_PRUEBAS_MANUALES_T14_T24.md).

**Origen de los datos de esta sección.** (1) Lo que el equipo informó de las capturas de Swagger (los códigos HTTP y estados de las columnas «Reportado»); **las capturas no están en el repositorio** y no se vieron para redactar este registro. (2) Lecturas de solo lectura (`SELECT`) de la base manual hechas el 2026-10-28, que se indican como «Corroborado en BD». Nadie repitió las operaciones al redactar esto. El equipo mencionó «ejecuciones exitosas documentadas», lo que implica intentos no exitosos previos: **no se detallaron y deben anotarse en la bitácora con sus capturas** (no se ocultan, pero tampoco se pueden describir sin la evidencia).

| Caso | Reportado | Corroborado en BD / código | Clasificación |
|---|---|---|---|
| T-14 a T-18 (evento, propuesta, aceptación, contrato, política, firma, anticipo, confirmación) | Códigos HTTP esperados en las ejecuciones exitosas | El evento principal `EV-89ab606e-…` tiene contrato en `CONTRATACION_CONFIRMADA` | **Aprobada con evidencia reportada** (capturas pendientes de archivar; intentos fallidos sin detallar) |
| T-19 servicio adicional | HTTP 201 | La solicitud existe, hoy `CERRADA_EVENTO_CANCELADO` | **Resultado satisfactorio con desviación del procedimiento**: el estado «Registrada» solo consta en la respuesta del POST; tras T-21 ya no se puede comprobar con un GET |
| T-20 cambio | HTTP 201 | Ídem | Igual que T-19 |
| T-21 cancelación | HTTP 200 | `EV-89ab606e-…` está `CANCELADO`; sus dos solicitudes quedaron cerradas por el evento cancelado (reacción a `EventoCancelado`, BN-008) | **Resultado satisfactorio con desviación**: se canceló el evento **principal** en vez de uno independiente, contra lo que preveía la guía; por eso T-19 y T-20 quedaron cerradas |
| T-22 fechas con zona horaria | HTTP 422 | El código rechaza fechas con zona (`NaiveDatetime`; prueba `tests/test_api_operaciones.py`) | **Aprobada** (el informe del equipo no precisa qué endpoint se usó; anótese en la bitácora) |
| T-23 servicio adicional con < 5 días | HTTP 201, `No procedente`, motivo «Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083)» | El evento `EV-8e2a6f41-…` (31/10/2026) está `En gestión` y su contrato `Firmado`, **no confirmado** | **Resultado observado con precondiciones incompletas**: el motivo coincide con la regla y con el código, pero el escenario previsto (contratación confirmada) no se estableció. No se afirma que las precondiciones quedaron verificadas |
| T-24 cambio con evento iniciado | Evento puesto en ejecución; cambio rechazado con HTTP 422 por CA-039 | `EV-2edfbcd8-…` está `En ejecución` con contrato confirmado | **Aprobada** (el rechazo lo reportó el equipo; la guía preveía un evento de fecha pasada y se usó el inicio del evento: desviación menor del procedimiento, que además es la vía más realista) |
| `GET /solicitudes` | Sin filtros: lista las 3 solicitudes. Con `evento_id` devolvió `[]` | El `evento_id` consultado tenía un carácter distinto (`EV-89ab686e-…` en vez de `EV-89ab606e-…`). Con `EV-89ab606e-6eef-42c4-9627-3142e7d89b3b` se comprobaron las dos solicitudes del evento principal | **Sin defecto**: la comparación es una igualdad exacta (`repositorios_sql.py`); el vacío se debió al identificador mal copiado |

**Otros registros en la base manual** (no explicados por este informe): `EV-5d7df250-…` y `EV-d8d49221-…` (ambos `En gestión`, sin contrato) son de intentos o pruebas cuyo origen no se documentó.

**Lo que esta validación no demuestra:** no hay un escenario T-23 con contratación confirmada; no hay una prueba manual de que T-21 sobre un evento independiente conserve las solicitudes del evento principal; el registro depende de capturas aún no archivadas en el repositorio. Para cerrar T-23 y T-21 como «Aprobadas» se necesita repetirlas con eventos independientes y contratación confirmada (tarea separada, no se hizo aquí).

**Pruebas automatizadas, última ejecución registrada:** `tests/evidencias/ejecucion-pruebas-local-20261028-000621.txt` (log del equipo, 28/10/2026 00:06, `docker compose run --rm tests`): `Ran 1306 tests … OK`; cobertura 98,82 % de sentencias (5379 de 5443) y 95,85 % de ramas (1016 de 1060). Coincide con las ejecuciones del 25/10 (equipo y Docker). El archivo está codificado en UTF-16 y termina con un aviso de PowerShell por la salida de error de Docker (`Container eventosnova-db Running`); no es un fallo de las pruebas. No se reejecutó la suite para redactar esta sección.

**Dictamen sobre este bloque:** la validación manual está **parcialmente completa**: T-14 a T-18, T-22 y T-24 aprobadas; T-19, T-20 y T-21 satisfactorias con desviación; T-23 con precondiciones incompletas. El dictamen de la sección H no cambia.

**Entregables no regenerados el 28/10/2026:** `docs/entrega/Reporte_Final_PIA_Eventos_Nova.pdf` y `Presentacion_Defensa_Eventos_Nova.pptx` se generaron el 25/10/2026 (cifras 1306 / 98,82 % / 95,85 %, vigentes). **No incluyen** la validación manual de esta sección ni el ADR-007: `reportlab` y `python-pptx` no están instalados en este entorno y no se instalaron. Hasta regenerarlos (`python scripts/generar_entrega_pia.py`, con esas dos bibliotecas, y una nueva revisión visual) el registro de la validación manual consta solo en este documento, en `PROGRESO_FASE_FINAL.md` y en la guía de pruebas manuales.

**Actualización del mapa de dominio (28/10/2026):** el PDF `diagramas/dominio/mapa-dominio.pdf` que la verificación del 25/10 declaró «no actualizado» se regeneró desde el `.drawio` vigente (detalle y límites en `diagramas/LEEME_EXPORTACIONES.txt`). Pendiente conocido: `secuencia_1_confirmacion_contratacion` (PlantUML) conserva la rama «importe distinto del 30 % → Importe incorrecto», anterior a E-3/E-4.

**Actualización de `secuencia_1` (28/10/2026):** el pendiente anterior quedó resuelto: `secuencia_1_confirmacion_contratacion.puml` se corrigió según E-3/E-4 y se regeneraron su PNG y su PDF (PlantUML 1.2025.4 descargado a una carpeta temporal; procedimiento y límites en `diagramas/LEEME_EXPORTACIONES.txt`). Sigue siendo documentación de decisiones del equipo sin aprobación externa registrada.


## J. Concordancia entre el código y la documentación (revisión del 2026-10-28)

> **Alcance y método.** Revisión bidireccional acotada a las reglas críticas (no una verificación línea por línea de los 114 criterios). Se cruzaron: (1) el texto aprobado (BRD, glosario, cierre de alcance C-01 a C-15, criterios CA); (2) el código ejecutable de `src/domain` y `src/application`; (3) las pruebas existentes; y (4) **simulaciones en memoria** con el cliente de pruebas de FastAPI (sin PostgreSQL, sin escribir en ninguna API real) que reproducen cada discrepancia. Las simulaciones están en el directorio temporal de la sesión, no en el repositorio. **No se afirma una concordancia del 100 %**: hay tres defectos de implementación (D-1 a D-3), cuatro decisiones de negocio pendientes y una parte no verificada, listados abajo.

### J.1 Defectos de implementación pendientes (sin corregir; requieren autorización y cambio de código)

> **Actualización posterior (sección M):** D-1 se corrigió y se comprobó con 26 pruebas de regresión; D-2 y D-3 se analizaron y siguen abiertos a la espera de decisiones de negocio. La tabla de abajo se conserva como se registró el 28/10/2026.

| Id | Regla aprobada | Comportamiento actual (comprobado) | Comportamiento requerido | Archivos y funciones | Corrección necesaria | Pruebas que la demostrarían |
|---|---|---|---|---|---|---|
| **D-1** | C-14, GL-015, BRD («solo podrá registrarse la solicitud si la contratación está confirmada»), **CA-101** (US-025) | Con contrato `Firmado` y Evento `En gestión`, `POST /solicitudes-servicio-adicional` responde **HTTP 201** `Registrada` (evento lejano) o `No procedente` por plazo (evento cercano). Solo se exige que exista el estado de cuenta, que nace al firmar (`_estado_cuenta_del_contrato`, H-07). `registrar_solicitud_cambio` sí exige `En organización` y la cancelación sí exige contratación confirmada (CA-084): el servicio adicional es la excepción | No registrar la solicitud, informar que un servicio adicional solo puede registrarse con la contratación confirmada, y **no evaluar** plazo ni saldo (CA-101) | `src/application/servicios.py`: `GestionServiciosAdicionalesService.registrar_solicitud_servicio_adicional` (usa `self.contratos` y `self.eventos`, ya inyectados) | Antes de crear la solicitud, rechazar (`Resultado.rechazo`, HTTP 422 como en `registrar_solicitud_cambio`) si el contrato del evento no está en `CONTRATACION_CONFIRMADA` o el Evento no está `En organización` | (a) contrato `Firmado`/Evento `En gestión` → rechazo, sin solicitud creada, sin consultar plazo ni saldo; (b) Evento `Cerrado sin contratación` → rechazo; (c) contratación confirmada → sigue el flujo actual; (d) HTTP 422 y mensaje por API; en memoria y PostgreSQL. Algunas pruebas existentes de servicio adicional quizá registren con contrato solo firmado y deberían ajustarse |
| **D-2** | C-06 / ND-29, **CA-113** (US-011), BRD («cuenta la fecha en que el Cliente efectuó el pago») | Un pago del saldo con **fecha posterior al límite**, verificado **antes** de registrar el vencimiento, deja el saldo `Liquidada` (simulación: saldo `Pendiente` con `fechaLimite` pasada, pago de 7000.00 → `Liquidada`). Con el saldo ya `Vencida` sí se cumple CA-113 (la liquidación la decide `resolver_regularizacion`) | Un pago posterior al límite no liquida directamente el saldo; este sigue vencido y el pago cuenta para la regularización (con cargos moratorios, CA-027) | `src/domain/estado_cuenta.py`: `_destinos_verificacion` (la condición `o.concepto in (SALDO_CONTRATO_ORIGINAL, SUSTITUCION_PROVEEDOR, ANTICIPO)` exime al saldo de comprobar `plazo.vencido(p.fecha)`) | **Decisión previa:** ¿«vencido» es el hecho (límite superado) o el registro (`registrar_vencimiento_saldo`)? Si es el hecho, el pago con `fecha` posterior al límite no debe llevar el saldo a `Liquidada` aunque no se haya registrado el vencimiento; para el anticipo, H-10 dice lo contrario y debe conservarse | Pago del saldo en el último segundo del plazo → Liquidada (ya existe en `test_plazos_dias_habiles_gl060_e1`); pago a las 00:00 del límite sin vencimiento registrado → no Liquidada; con vencimiento registrado → regularización (CA-113) |
| **D-3** | C-01, **CA-109, CA-110, CA-111**, GL-032, GL-033 | **No hay inicio automático en T**: no existe planificador (`grep` de `scheduler`/`cron` sin resultados en `src/`); el inicio solo se registra con `POST /eventos/{id}/inicio`. Sobre un Evento `En gestión` con T vencida esa operación responde **HTTP 422** «No puede iniciar un evento En gestión» y el Evento **sigue En gestión** (`MAQUINA_EVENTO` solo tiene INICIAR desde `En organización`). `cerrar_sin_contratacion` solo ocurre como reacción a `ProcesoContratacionCerrado` (anticipo no efectuado en 24 h) | Al llegar T, un Evento todavía `En gestión` pasa a `Cerrado sin contratación` (no `Cancelado`) y su contrato no firmado a `Cerrado sin confirmar`; las solicitudes no confirmadas se cierran con un único resultado (CA-111, C-02) | `src/domain/evento.py` (`MAQUINA_EVENTO`, `iniciar`); `src/application/servicios.py` (`procesar_inicio_evento`); `src/application/reacciones.py` (cierre de solicitudes solo tras registrar el inicio); `src/infrastructure/persistencia/trabajador_outbox.py` (no procesa eventos por fecha) | Decidir si basta una operación explícita (registrar el inicio también cierra un Evento `En gestión`) o se requiere un proceso periódico en el trabajador; añadir la transición y la reacción correspondientes | Evento `En gestión` con T vencida → `Cerrado sin contratación` y contrato `Cerrado sin confirmar`; solicitudes cerradas una sola vez; T exacta inclusiva (CA-109); idempotencia |

Estos tres puntos hacen que el estado «Aprobada · Implementada · Con pruebas» que la auditoría generaba para C-01, C-06 y C-14 fuera **incorrecto**: se calculaba buscando que el código citara el identificador. `scripts/generar_auditoria_requisitos.py` ya los marca como defecto y `docs/trazabilidad/auditoria-requisitos-fase-final.md` se regeneró.

### J.2 Decisiones de negocio pendientes (ninguna está aprobada externamente)

| Tema | Qué falta decidir | Documentos implicados |
|---|---|---|
| E-3 (pagos parciales) | GL-011 y el BRD dicen que un importe inferior al 30 % «debe corregirse»; no precisan si se suma o sustituye. El equipo eligió sumar | `DECISIONES_E1_E4.md`, GL-011, BRD |
| E-2 y E-4 | Sin respaldo en las fuentes; decisiones del equipo | `DECISIONES_E1_E4.md`, ADR-007 |
| Definición de «saldo vencido» (D-2) | Hecho (límite superado) o registro | C-06, CA-113, `estado_cuenta.py` |
| Inicio automático (D-3) | Planificador o registro explícito | C-01, CA-109, GL-032 |
| GL-060 vs E-1 | El glosario nombra tres plazos (anticipo, saldo, devoluciones); E-1 aplica el mismo criterio a seis (también seguimiento del anticipo, sustitución y SE-012). C-15 y GL-056 respaldan el criterio, pero la extensión a todos los plazos es una lectura del equipo | GL-060, C-15, `DECISIONES_E1_E4.md` |

### J.3 Correspondencias verificadas (regla → código → prueba o simulación)

| Regla / criterio | Código | Verificación |
|---|---|---|
| Plazo de 5 días naturales del servicio adicional (CA-077, CA-083; SE-004) | `AnticipacionMinima`, `SERVICIO_ADICIONAL_EN_PLAZO` (`especificaciones.py`); `AnticipacionSolicitud.dias_naturales` | Simulación: evento a 2 días → 201 `No procedente` con el motivo literal; `test_h08_inicio_evento` (CA-099) |
| Orden de verificaciones: cancelado → condición temporal → saldo (SE-004; BRD) | `SOLICITUD_PUEDE_CONTINUAR`, `evaluar_solicitud_nueva` | Lectura del código y simulación |
| Cambio solo después de contratar y antes del inicio (CA-039) | `registrar_solicitud_cambio` | Simulación: contrato `Firmado` → 422; evento iniciado → 422; `test_h08_inicio_evento` |
| Cancelación solo con contratación confirmada y antes de T (C-08, CA-084 a CA-088) | `Evento.solicitar_cancelacion` | Simulación: contrato `Firmado` → 422 CA-084; `test_etapa9_casos_de_uso` |
| Cancelación cierra las solicitudes en trámite (C-09, BN-008) | `ReaccionesSolicitudes.al_cancelarse_evento` | Ejecución manual de T-21 (solicitudes quedaron `Cerrada por evento cancelado`) y `test_e3g_cargo_tardio_y_conceptos` |
| Anticipo mínimo del 30 %, plazo de 3 días hábiles, liquidación (BN-009, CA-019; E-1, E-3, E-4) | `EstadoCuenta.registrar_obligacion_anticipo`, `registrar_y_verificar_pago` | 1306 pruebas, `test_anticipo_pagos_parciales_e3_e4`, `test_plazos_dias_habiles_gl060_e1`; simulación del anticipo de 3000.00 sobre 10000.00 |
| Confirmación de la contratación (CA-015 a CA-019) | `Contrato.confirmar_contratacion`, reacción a `PagoVerificado` | Simulación y ejecución manual de T-18 |
| Consulta por `evento_id` (filtro de `GET /solicitudes`) | `_RepositorioSolicitudesSQL.listar_por_evento_id` | Igualdad exacta; ver §I |

### J.4 Criterios sin cita directa en el código ni en las pruebas

Veinte criterios no se nombran en `src/` ni en `tests/` (búsqueda de «CA-nnn», con rangos): CA-001, 002, 004, 006, 011 (consultas de la información registrada), CA-045 (autorización registrada), CA-085, 086 (consulta al recibir una cancelación), CA-101 a 106, CA-109 a 114. La falta de cita **no implica** que no estén implementados. Revisados en el código: CA-001/002/004/006/011/085/086 corresponden a consultas (`ConsultarInformacionAdministrativaEventoHandler`, revisión administrativa), CA-045 a la autorización de cambios (`registrar_autorizacion_administracion_cambio`, `_servicio_adicional` y `_sustitucion`) y CA-102 a 106 a la devolución del anticipo (decisión A, con pruebas que citan A-1…A-6); CA-112 a que las consultas filtran obligaciones `Pendiente`/`Vencida` (`ConsultarPagosPendientesHandler`); CA-114 al no reembolso con evento cancelado (prueba `test_reglas_anticipo_decisiones_abc`, T-66). **CA-101, CA-109/110/111 y CA-113 no se cumplen** (D-1, D-3, D-2). Esa lectura es mía a partir del código; el equipo debe revisarla.

### J.5 Lo que no se verificó

- No se contrastaron uno por uno los 114 escenarios Gherkin con el comportamiento: sí los citados arriba y los cubiertos por la suite.
- La matriz de trazabilidad aprobada no tiene columna de pruebas ni de evidencias; la relación criterio → prueba solo existe por citas (auditoría generada y este apartado).
- BRD, historias, glosario y matriz **no se modificaron** (documentos aprobados): los tres defectos son del código, no de la documentación.

## K. Traspaso técnico para la interfaz web (sin desarrollar el frontend)

**Arquitectura de la API.** FastAPI (`src/api/main.py`, `crear_app`) con rutas finas por área (`rutas_propuestas`, `rutas_contratacion`, `rutas_pagos`, `rutas_eventos`, `rutas_solicitudes`, `rutas_consultas`) que llaman a un método de un servicio de aplicación o a un Query Handler; las reglas están en `src/domain` y `src/application`. Persistencia en memoria (por omisión) o PostgreSQL (`EVENTOSNOVA_PERSISTENCIA=postgresql`), Outbox con despacho en línea y trabajador. OpenAPI en `docs/api/openapi.json` (60 operaciones) y en `/openapi.json`; Swagger en `/docs`; `GET /health` y `GET /ready`.

**Endpoints que podrá consumir.** Los de la tabla de operaciones del README (sección 7): 47 `POST` de comando y 13 `GET` (60 operaciones en total): 10 de consulta de negocio (`/eventos?desde&hasta`, `/eventos/{id}/administracion`, `/eventos/{id}/pagos`, `/eventos/{id}/solicitudes-pendientes`, `/eventos/{id}/servicios/{sid}/disponibilidad`, `/proveedores/{p}/eventos/{e}`, `/solicitudes`, `/pagos-pendientes`, `/devoluciones-pendientes`, `/servicios-pendientes-confirmacion`) y 3 técnicos (`/`, `/health`, `/ready`). Esquemas en `src/api/esquemas.py` y `esquemas_operaciones.py`; `docs/api/openapi.json` los lista completos.

**Roles.** El código nombra actores (Coordinador, Administración, Cliente) en los casos de uso y en las notificaciones, pero **no existe autenticación ni autorización** en la API (no hay dependencias de seguridad ni middleware de credenciales) y **ningún endpoint distingue roles**. La interfaz debe tratarse como un cliente de confianza hasta que se implementen; no se debe afirmar lo contrario.

**Validaciones y reglas que permanecen en el backend.** Todas las reglas de negocio (plazos, anticipo, estados, saldo, cancelación, E-1 a E-4). El frontend solo debe validar la forma (tipos, campos obligatorios, fechas **sin zona horaria**, importes decimales no negativos, booleanos reales) y mostrar los rechazos; no debe replicar plazos ni estados.

**Manejo de errores.** Rechazo de negocio: HTTP 422 `{"tipo": "rechazo_de_negocio", "detalle", "pendientes"}`; validación de forma: 422 estándar de FastAPI (`detail` con `loc`); 409 `conflicto_de_integridad` y `conflicto_de_concurrencia` (releer y reintentar); 422 `dato_no_almacenable`; 503 sin conexión a la base; 500 genérico (`src/api/errores.py`). Una lista vacía de una consulta con filtro **no** distingue un identificador inexistente (caso `GET /solicitudes`).

**Configuración y ejecución.** `docker compose up -d --build` (API en `127.0.0.1:8000`), o el entorno manual aislado (8001, README sección 12). Variables en `.env.example`. **No hay CORS** (`CORSMiddleware` no está configurado) y la API escucha solo en loopback: un frontend en otro origen sería bloqueado por el navegador. Opciones sin duplicar reglas: servir el frontend y la API bajo el mismo origen (proxy inverso) o añadir CORS en el backend (cambio que requiere autorización).

**Brechas de la API para una interfaz.** (1) Ninguna respuesta devuelve `version_id` (se construye como `<propuesta_id>-v1`); (2) `pago_id` solo aparece en la respuesta del `POST` del pago; (3) `obligacion_id` solo en `GET /pagos-pendientes`; (4) no hay `GET` de propuesta, contrato ni evento por id (el estado se lee de `/administracion`); (5) no hay listado de eventos por estado ni búsqueda; (6) sin autenticación. Cualquier cambio de la API existente exige autorización y actualizar OpenAPI y pruebas.

**Estructura recomendada.** Carpeta separada (por ejemplo `frontend/`) con un cliente tipado generado o escrito a partir de `docs/api/openapi.json`; una capa de acceso a datos que traduzca los rechazos 422 en mensajes; flujos por rol como pantallas, pero sin reglas de negocio en el cliente; pruebas de contrato contra `docs/api/openapi.json` (ya existe `tests/test_openapi_exportada.py`). **Antes de empezar:** D-1 está corregido en el código (sección M.1) pero no en los contenedores en marcha hasta reconstruir la imagen; D-2 y D-3 siguen abiertos, y decidir la política de CORS/autenticación.

## L. Estado de los entregables de la etapa 2 (2026-10-28)

Categorías: **Implementado** (existe en el código), **Verificado** (comprobado con pruebas o simulación), **Documentado**, **Pendiente de prueba**, **Pendiente de código** (defecto), **Pendiente de aprobación externa**, **No verificable** con la evidencia disponible.

| Entregable | Estado | Respaldo |
|---|---|---|
| Suite automatizada (1306 pruebas) y cobertura (98,82 % / 95,85 %) | Implementado · Verificado (registro del 25/10 y log del equipo del 28/10 00:06; no repetido hoy) | `tests/evidencias/` |
| D-1 (servicio adicional sin contratación confirmada) | Implementado (corrección) · Verificado con 26 pruebas de regresión · desplegado en las imágenes locales (§O.5) | §M.1, §O, `tests/test_d1_servicio_adicional_contratacion_confirmada.py` |
| D-2 (pago tardío del saldo), D-3 (inicio automático en T) y D-3b (confirmar después de T) | Implementado (corrección) · Verificado con 22 y 33 pruebas, suite completa 1387 OK y cobertura 98,82 % / 95,77 % · desplegado en las imágenes locales · **decisiones internas sin aprobación externa** | §N, §O, ADR-008 |
| E-2, E-3, E-4, comprobante repetido, método del oráculo | Implementado · **Pendiente de aprobación externa** | `DECISIONES_E1_E4.md`, ADR-007 |
| GL-011/BRD «corrección» de un anticipo menor al 30 % (suma o sustitución) | **Decisión de negocio pendiente** | §J.2 |
| Validación manual T-14 a T-18, T-22, T-24 | Verificado según el equipo (capturas no archivadas) | §I |
| T-19, T-20, T-21 | Satisfactorias con desviación | §I |
| T-21 y T-23 repetidas | **Pendiente de prueba** (guía, sección 12; T-23 solo de domingo a martes UTC; T-24 con evento a +40 min) | guía |
| Mapa de dominio (`.drawio` + PDF de 5 páginas) | Documentado · Verificado contra el código (47 clases, 7 agregados, 31 eventos) · revisado visualmente | `diagramas/LEEME_EXPORTACIONES.txt` |
| `secuencia_1` (`.puml` + PNG + PDF) | Documentado según E-3/E-4 · PNG revisado visualmente | ídem |
| BPMN SP-04 (servicio adicional) | Correcto frente a CA-101 y C-14 (tiene la compuerta «¿La contratación está confirmada?»); **el código no coincide** con este diagrama (D-1). BPMN y clases no se regeneraron (no se revisaron en profundidad) | `diagramas/bpmn/…SP04….drawio` |
| README | Documentado · comandos y archivos comprobados por nombre, no ejecutados de nuevo | `README.md` |
| Matriz de trazabilidad | Sin modificar (aprobada); identificadores y pertenencia CA→US comprobados; **sin columna de pruebas** | `complemento-trazabilidad-fase-final.md` |
| Auditoría de requisitos generada | Corregida (C-01, C-06, C-14, SE-004 y BN-005 ya no figuran como implementadas sin reservas) | `auditoria-requisitos-fase-final.md` |
| BRD, historias, Gherkin, glosario | Sin cambios (documentos aprobados); los defectos son del código | §J |
| ADR-007 | Documentado; E-2 a E-4 sin aprobación externa | `docs/ADR/` |
| Bitácora de IA formal | Integrada hasta la iteración 27; **prompts sin transcribir** | `docs/bitacora ia/` |
| PDF de entrega y presentación | Generados el 28/10 con un entorno aislado, revisados visualmente (7 páginas y 9 diapositivas). **No son la versión final**: T-21 y T-23 constan como pendientes | `docs/entrega/` |
| Repositorio remoto, CI en GitHub, despliegue | **No verificable / pendiente** (no existen) | README |
| Interfaz web | Fuera de esta etapa; traspaso en §K | §K |

> **Actualización (2026-10-29):** las filas de D-1 a D-3, T-21/T-23, mapa de dominio, BPMN SP-04, diagramas, PDF y presentación quedan superadas por la tabla Q.5.

**La etapa 2 no está cerrada:** faltan T-21 y T-23, la corrección (o la decisión de aceptar) D-1, D-2 y D-3, la transcripción de los prompts de la bitácora, el archivado de las capturas y la regeneración final de los entregables con esos resultados.


## M. Corrección de D-1 y análisis de D-2 y D-3 (2026-10-28, posterior a J)

> Los hallazgos de la sección J se conservan sin cambios como historial. Esta sección registra qué se hizo con cada uno. **La etapa 2 sigue sin cerrarse.**

### M.1 D-1 — corregido y comprobado por pruebas de regresión

- **Cambio en el código** (único archivo de producción tocado): `src/application/servicios.py`, `GestionServiciosAdicionalesService.registrar_solicitud_servicio_adicional`. Después de validar el evento del contrato (E-2) y **antes** de crear la solicitud, se lee el contrato (`self.contratos`, ya inyectado); si existe y su estado no es `Contratación confirmada`, se notifica al Cliente («Servicio adicional no registrado») y se devuelve `Resultado.rechazo("Un servicio adicional solo puede registrarse con la contratación confirmada (CA-101).")`, que la API traduce a **HTTP 422** `rechazo_de_negocio` (misma convención que `registrar_solicitud_cambio`). No se crea la solicitud ni se evalúa plazo ni saldo (CA-101). Un contrato inexistente conserva su rechazo anterior («no existe o todavía no tiene estado de cuenta»). Con el evento cancelado o iniciado el contrato sigue confirmado, de modo que esos casos los siguen resolviendo la evaluación posterior y sus motivos propios. No se tocó GL-015, CA-101 ni ningún documento aprobado.
- **Pruebas nuevas:** `tests/test_d1_servicio_adicional_contratacion_confirmada.py`, 13 casos por composición (memoria y PostgreSQL de pruebas) = **26 pruebas**: contrato solo firmado rechazado sin cambios de agregados, obligaciones ni Outbox; rechazo con el plazo cumplido y con el incumplido sin evaluar el plazo; Cliente notificado; contrato en preparación y cerrado sin confirmar rechazados; contrato confirmado permite registrar (plazo cumplido y justo cinco días); con la contratación confirmada y menos de cinco días sigue `No procedente` con el motivo de CA-077/CA-083; evento cancelado conserva su motivo propio; contrato inexistente conserva su rechazo; y por HTTP: 422 con contrato firmado, 201 `No procedente` por plazo y 201 `Registrada` con la contratación confirmada.
- **Resultados reales:**
  - Con la corrección: `tests.test_d1_servicio_adicional_contratacion_confirmada` → 26 pruebas OK.
  - **Sin la corrección** (versión anterior del archivo, restaurada solo para esta comprobación): 8 de las 13 pruebas en memoria fallan; las 5 que pasan son las que verifican comportamiento conservado. Así las pruebas detectan D-1.
  - Conjunto focalizado (las 19 suites que registran servicios adicionales, la nueva, las suites del paquete F2, la auditoría, la trazabilidad, BRD, diagramas, OpenAPI y la coherencia solicitud–contrato–evento): 492 pruebas, sin fallos tras regenerar `docs/architecture/trazabilidad-api-persistencia.md` (su generador ahora cita CA-101 en la ruta del servicio adicional; cambio de una línea). Las 322 pruebas de las 19 suites existentes pasan antes y después del cambio, es decir, ninguna dependía del comportamiento defectuoso.
  - No se ejecutó la suite completa ni la cobertura. Las pruebas con PostgreSQL usan la base de pruebas existente (`eventosnova_test`); no se tocó la base de desarrollo, la API ni los contenedores.
- **Alcance de la corrección:** el código corregido **no está en los contenedores en marcha** (la imagen `eventosnova-app:local` se construyó antes). Hasta reconstruir la imagen y recrear `api` y `api-manual`, las ejecuciones en Swagger (8000 y 8001) siguen con el comportamiento anterior. No se reconstruyó nada.
- La auditoría generada marca ahora C-14 como implementada con pruebas; SE-004 pierde su observación.

### M.2 D-2 — análisis (sin cambios de código)

**Qué dicen las fuentes aprobadas sobre «vencido»:**

| Fuente | Texto | Lectura |
|---|---|---|
| Glosario GL-049 | «Importe pendiente del contrato original cuyo plazo de liquidación **ya terminó sin que el Cliente lo haya pagado dentro de ese plazo**. Un pago que el Cliente efectuó a tiempo y que Administración registra o verifica después no convierte el saldo en vencido. **Un pago del saldo efectuado después de su fecha límite no lo liquida directamente: el saldo queda vencido y el pago cuenta para la regularización.**» | Definición por **hecho**: plazo terminado y sin pago a tiempo; la fecha del pago, no el registro, decide |
| Cierre de alcance §2, C-06 (ND-29) | «un pago del saldo efectuado después de su límite no lo liquida directamente; el saldo queda vencido y el pago cuenta para la regularización» (fuentes: GL-049, BN-005) | Misma regla |
| Cierre de alcance §8, «Brechas ya observadas», punto 3 | «**ND-29**: el código liquida el saldo con un pago tardío registrado antes de que conste el vencimiento (grupo R12, 48 claves; diferencia D-24 de la V4.1)»; y §6: R12 «sin cambios frente a la V4.1» | El propio cierre aprobado clasifica el comportamiento actual como **brecha** |
| User Stories CA-113 (US-011) | «Dado que venció el plazo de pago del saldo pendiente del contrato original, cuando el Cliente efectúe el pago del saldo después de esa fecha límite, entonces el pago no liquidará directamente el saldo: este seguirá vencido y el pago contará para la regularización, que requiere liquidar también los cargos moratorios conforme a CA-027» | La premisa es que «**venció el plazo**» (hecho), sin mencionar ningún registro |
| BRD (BN-005) | «El saldo pendiente del contrato original deberá quedar liquidado como máximo tres días hábiles antes de la fecha del evento; **cuenta la fecha en que el Cliente efectuó el pago**, aunque Administración lo registre o verifique después.» | La fecha del pago decide |
| GL-046 | «la fecha del pago es la que determina si se cumplió el plazo» | Ídem |
| CA-024, CA-025 | CA-024: «Dado que existe un saldo pendiente, cuando Administración lo identifique…»; CA-025: «Dado que el saldo pendiente del contrato original **venció**, cuando el Coordinador active el procedimiento de cobro…» | Ninguna fuente describe un acto que «registre el vencimiento»; hablan de que el saldo «venció» |
| GL-054 | «El pago posterior al plazo no la evita [la cancelación], aunque aún no se haya registrado formalmente.» | Refiere al registro formal de la cancelación, no al del vencimiento |

**Qué hace el código:**
- `EstadoCuenta.registrar_vencimiento_saldo` (`src/domain/estado_cuenta.py`, ~l. 427) pasa la obligación a `Vencida` solo al ejecutarse; la única llamada es `POST /estados-cuenta/{id}/vencimiento-saldo-original` (`rutas_pagos.py`), sin ningún proceso automático.
- `EstadoCuenta._destinos_verificacion` (~l. 330) liquida una obligación `Pendiente` cuando lo pagado, con este pago, cubre el importe. La condición `o.plazo is None or not o.plazo.vencido(p.fecha) or o.concepto in (SALDO_CONTRATO_ORIGINAL, SUSTITUCION_PROVEEDOR, ANTICIPO)` **no comprueba la fecha del pago para esos tres conceptos**: un pago del saldo con fecha posterior al límite liquida el saldo mientras siga `Pendiente`.
- Existe además un predicado por **hecho**: `EstadoCuenta.obligacion_vencida_sin_pago` (~l. 399): «el plazo del Cliente para pagar venció y no hay un pago efectuado dentro de él», que usa el cierre por falta de pago de solicitudes (`servicios.py` ~l. 760).
- Sin embargo `saldo_vencido_sin_regularizar` (`any(o.estado == VENCIDA)`), que usan el bloqueo de solicitudes y el protocolo de cobro, depende del **estado registrado**.
- Excepciones documentadas que **no** son D-2: el anticipo (H-10: un anticipo correcto y verificado queda Liquidado aunque sea tardío, BN-009/SE-010) y el costo adicional de una sustitución concretada después del límite (GL-012: no se considera vencido automáticamente).

**Conclusión del análisis:** las fuentes aprobadas definen «vencido» por el **hecho** (plazo terminado sin pago a tiempo; la fecha del pago manda) y el cierre aprobado cataloga el comportamiento actual como brecha. Lo que **no** determinan es el **mecanismo**: si el saldo debe pasar a `Vencida` solo en el momento del hecho (automáticamente), si basta con que un pago tardío no liquide, o si el registro explícito sigue siendo el disparador de todo lo demás (protocolo de cobro, bloqueo de solicitudes). Por eso no se modificó D-2.

**Alternativas y efecto de cada una (decisión pendiente de la responsable):**

| Alternativa | Qué cambia | Efectos y riesgos |
|---|---|---|
| **A. Mínima: un pago con fecha posterior al límite no liquida el saldo** (el saldo sigue `Pendiente` hasta que se registre el vencimiento y se regularice) | Quitar a `SALDO_CONTRATO_ORIGINAL` de la excepción de `_destinos_verificacion`; el pago queda `Verificado` y cuenta para la regularización | Cumple C-06/CA-113 en lo esencial; el estado `Pendiente` con el límite pasado sigue siendo ambiguo; hay que definir cómo cuenta el pago tardío en `resolver_regularizacion` |
| **B. Vencimiento por hecho**: el saldo se considera vencido cuando el límite se supera (calculado al leer o al verificar; o por un proceso periódico) | `saldo_vencido_sin_regularizar` y los consumidores usarían `obligacion_vencida_sin_pago`; puede añadirse la transición automática a `Vencida` | Es la lectura más fiel a GL-049; afecta el bloqueo de solicitudes (T-23 y otros), el protocolo de cobro y exige decidir si es automática (ligado a D-3: planificador) o perezosa |
| **C. Mantener el registro explícito** y documentar que el vencimiento «consta» al registrarlo (comportamiento actual) | Solo documentación (GL-049, C-06, CA-113 y el cierre §8 punto 3 quedarían contradichos) | **No respaldada** por las fuentes: exigiría modificar reglas aprobadas, que esta fase no puede hacer |

**Impactos comunes si se corrige:** cambiarían las 48 claves del grupo R12 del oráculo histórico (`comportamiento_estado_cuenta_v8_e3c.json`, que no se edita): habría que añadir una regla D-2 a `tests/apoyo_esperados_oraculo.py` (método de validación del oráculo, aún pendiente de aprobación formal); y se necesitarían pruebas del pago a las 00:00 exactas del límite (E-1) y con el saldo ya `Vencida`.

### M.3 D-3 — análisis (sin cambios de código)

**Qué dicen las fuentes aprobadas:**

| Fuente | Texto |
|---|---|
| Cierre de alcance §2, C-01 | «**Inicio automático en T.** Un Evento todavía En gestión pasa a Cerrado sin contratación, y su contrato no firmado, a Cerrado sin confirmar» (Decisión A del ejercicio; GL-033; BN-009; SE-011) |
| C-02 | «Las solicitudes no confirmadas se cierran al llegar T con un único resultado. Nada se confirma después de T. Lo confirmado antes de T se aplica» |
| BRD, BN-010 (`docs/BRD.md`, línea 96) y BN-009 (línea 95) | BN-010: «El Evento inicia automáticamente en la fecha y hora programadas (T), con límite inclusivo en T.» BN-009: «El estado Cerrado sin contratación se utilizará cuando… llega la fecha y hora de inicio del Evento sin que la contratación haya quedado confirmada» |
| GL-032 | «El inicio es automático en esa fecha y hora (T), con límite inclusivo en T. Si en T el Evento sigue En gestión, no inicia: pasa a Cerrado sin contratación (GL-033) y la contratación ya no puede confirmarse. Desde entonces, los cambios y servicios adicionales pendientes… se cierran como no procedentes…» |
| GL-033 | «Cerrado sin contratación: el proceso de contratación se cerró sin confirmarse, por ejemplo, por falta del anticipo… o porque llegó la fecha y hora de inicio del evento sin que la contratación estuviera confirmada. Nunca es Cancelado» |
| CA-109 (US-033) | «Dado que el Evento está En organización, cuando llegue la fecha y hora programadas (T), entonces el Evento deberá **iniciar automáticamente** y pasar a En ejecución. El límite es inclusivo en T…» |
| CA-110 | «Dado que al llegar T el Evento sigue En gestión porque la contratación no llegó a confirmarse, cuando inicie el Evento, entonces el Evento deberá quedar Cerrado sin contratación, no Cancelado, y su contrato no firmado deberá quedar Cerrado sin confirmar. La contratación no podrá confirmarse después de T y el anticipo recibido, si existe, se devolverá conforme a CA-102 a CA-105…» |
| CA-111 | «…cuando llegue T, entonces cada una [solicitud no confirmada] deberá cerrarse con un único resultado conforme a CA-070, CA-071 y CA-096…» |

**Qué debe ocurrir al llegar T sin contratación confirmada (determinado):** el Evento pasa a `Cerrado sin contratación` (nunca `Cancelado`), la contratación ya no puede confirmarse, el anticipo recibido se devuelve conforme a CA-102 a CA-105 y las solicitudes no confirmadas se cierran con un único resultado.

**Qué hay implementado hoy:**
- No hay inicio automático: el único camino es `POST /eventos/{id}/inicio` (`rutas_eventos.py` → `GestionCierreEventoService.procesar_inicio_evento` → `Evento.iniciar`). `MAQUINA_EVENTO` solo define INICIAR desde `En organización`; sobre un Evento `En gestión` esa operación responde 422 «No puede iniciar un evento En gestión» (comprobado por simulación) y el Evento sigue `En gestión`.
- `Evento.iniciado_en(ahora)` (H-08) **deriva** el inicio de la fecha programada para decidir cambios, cancelaciones y servicios adicionales aunque el inicio no se haya registrado.
- `Evento.cerrar_sin_contratacion` solo se ejecuta como reacción a `ProcesoContratacionCerrado` (anticipo no efectuado en 24 h, `reacciones.py`), con la devolución del anticipo que ya implementa la decisión A.
- Las solicitudes pendientes se cierran por inicio (reacción a `EventoIniciado`) **solo cuando alguien registra el inicio** de un Evento `En organización`.
- El contrato solo tiene la transición `Firmado → Cerrado sin confirmar`; `En preparación` no puede cerrarse (CA-110 y C-01 hablan de «su contrato no firmado»).
- El único proceso periódico existente es el trabajador del Outbox (`trabajador_outbox.ejecutar`, ciclo cada 2 s), que solo despacha eventos pendientes; no recorre eventos por fecha.

**¿Se requiere un planificador?** Las fuentes dicen «automático» pero no el mecanismo. No lo determinan el BRD, el glosario ni los CA. Que sea automático implica que **algo** debe actuar al llegar T sin intervención humana; hoy nada lo hace. Es una decisión de negocio/técnica pendiente:

| Alternativa | Qué cambia | Efectos y riesgos |
|---|---|---|
| **A. Proceso periódico en el trabajador** (recorre eventos con T vencida: `En organización` → iniciar; `En gestión` → cerrar sin contratación y cerrar contrato y solicitudes) | Nuevo caso de uso + ciclo en el trabajador; transiciones nuevas en `MAQUINA_EVENTO` y, si se decide, en `MAQUINA_CONTRATO` | Cumple «automático»; añade una responsabilidad al trabajador (hoy solo despacha el Outbox, ADR-004), concurrencia (versión optimista), idempotencia y pruebas con reloj controlado |
| **B. Operación explícita ampliada**: `POST /eventos/{id}/inicio` también cierra un Evento `En gestión` cuando T ya llegó; algo externo (cron, Administración) la invoca | Cambios solo en el servicio y la máquina de estados | Pequeño, pero **no es automático**: hasta que alguien la llame, el Evento no cambia (las fuentes lo llaman automático); requiere aprobar esa lectura |
| **C. Evaluación perezosa**: al leer o escribir sobre el evento se aplica la transición si ya pasó T | Cambios en repositorios, servicios y consultas | Rompe la separación comando/consulta (GET con efectos), efectos tardíos en el Outbox; solo para Eventos que nadie toque, nunca se cierran |
| **D. Mantener** y documentar el inicio como registro manual | Solo documentación | **No respaldada**: contradice C-01, GL-032 y CA-109 a CA-111 |

**Ambigüedades adicionales que necesitan decisión:** (1) C-01 y CA-110 dicen «su contrato **no firmado**»: no precisan qué ocurre con un contrato `Firmado` sin confirmar en T (el caso más frecuente); GL-033 sí habla de «contratación no confirmada»; (2) quién y cómo informa a las partes al cerrar por T; (3) T inclusivo y el reloj de referencia (el servidor trabaja en UTC; las fechas del evento no llevan zona).

### M.4 Riesgos y pendientes antes de repetir T-21 y T-23

1. **Las pruebas manuales corren sobre el código anterior.** Las API del puerto 8000 y del 8001 usan la imagen construida antes de D-1. T-21 y T-23 con contratación confirmada no se ven afectadas; un intento con contrato sin confirmar seguirá devolviendo 201 hasta reconstruir la imagen y recrear `api` y `api-manual` (decisión del equipo; no se hizo).
2. **T-23 sigue limitada por el calendario:** solo de domingo a martes (UTC), con el evento a +4 días, para que el límite del saldo (3 días hábiles antes) sea posterior a AHORA (guía, §11.3). D-2 y D-3 no cambian eso mientras no se resuelvan.
3. **D-2 y D-3 siguen abiertos** y condicionan la lectura de «saldo no vencido» y de «evento iniciado» en las pruebas manuales.
4. El PDF de entrega, la presentación y la fila 27 de la bitácora aún dicen que D-1 no está corregido; hay que regenerarlos después de T-21 y T-23.
5. La corrección de D-1 no se probó contra el entorno desplegado ni con la suite completa ni con cobertura; conviene ejecutar ambas antes de la entrega.


## N. D-2 y D-3: diagnóstico ampliado y plan de corrección (2026-10-28, sin cambios de código)

> Complementa M.2 y M.3. No se modificó código ni documentos aprobados. Lo marcado «lectura de código» no se ejecutó; lo marcado «simulación» se comprobó en memoria el 28/10/2026 (sin escribir en ninguna API real).

### N.1 D-2 — qué regla corresponde a cada obligación

| Obligación | Plazo aprobado | Fecha que decide | Efecto de un pago tardío (aprobado) | Estados | Código actual |
|---|---|---|---|---|---|
| **Anticipo** (≥ 30 %) | 3 días hábiles tras la firma (GL-009, GL-011, BN-009, SE-010, CA-020), límite exclusivo (GL-060, E-1). **Distinto** del plazo del saldo | La fecha en que el Cliente pagó decide si el proceso se cierra: tras el contacto tiene 24 h (CA-020, CA-021); registro y verificación pueden ser posteriores | Un pago posterior a los 3 días **no** invalida el anticipo: las fuentes solo prevén contacto y 24 h; si paga en ese plazo no se cierra (CA-021). Ninguna fuente dice que un anticipo tardío «no liquida» | Pendiente → Liquidada, o Sin efecto al cerrarse la contratación (C-04). **Nunca «Vencida»** | `_destinos_verificacion` exime a `ANTICIPO` de la comprobación de fecha (H-10, adoptada por el equipo con respaldo parcial: BN-009, SE-010, CA-019, CA-021); `registrar_vencimiento_saldo` solo mira el saldo. **Coherente** |
| **Saldo del contrato original** | 3 días hábiles **antes** del evento (GL-012, BN-005, CA-023), límite exclusivo | La fecha del pago, no la del registro (BN-005; GL-046; GL-049) | **No liquida directamente**: el saldo queda vencido y el pago cuenta para la regularización, que exige también los cargos moratorios (C-06/ND-29, GL-049, CA-113, CA-027) | Pendiente → **Vencida** (GL-049; mapa de dominio) → Liquidada solo por regularización | `_destinos_verificacion` exime también a `SALDO_CONTRATO_ORIGINAL`: un pago tardío verificado con la obligación aún `Pendiente` la **liquida**. **Incumple C-06/CA-113** (el cierre §8, brecha 3, ya lo registraba) |
| Costo adicional de una sustitución concretada después del límite | Se paga y verifica antes de confirmar el reemplazo; «sin considerarse vencido automáticamente» (GL-012, CA-052) | Fecha del pago | No hay vencimiento automático por esa circunstancia | Pendiente/Liquidada | Exento en `_destinos_verificacion` (`SUSTITUCION_PROVEEDOR`): **coherente** con GL-012 |
| Cambio, cargo por cambio tardío, servicio adicional | Ventana de 24 h desde la comunicación (BN-003, BN-004) | Fecha del pago | Un pago fuera de la ventana no evita el cierre por falta de pago | Pendiente → Liquidada / Sin efecto | El `elif` **sí** comprueba `plazo.vencido(p.fecha)` para estos conceptos: **coherente** |
| Cargos moratorios | 24 h desde la comunicación (GL-051, GL-054) | Fecha del pago | Los resuelve `resolver_regularizacion` | — | `en_regularizacion`: **coherente** |

**Distinción de fechas (tal como las fuentes y el código las separan):** *fecha efectiva del pago* (`Pago.fecha`, cuándo pagó el Cliente: decide el plazo); *fecha de registro* (`registrado_en`: cuándo Administración lo anota) y *fecha de verificación* (`verificado_en`): pueden ser posteriores y **no** convierten un pago a tiempo en tardío ni un saldo en vencido (BN-005, GL-046, GL-049, CA-021, CA-027).

**Qué es un saldo «vencido» según las fuentes:** un **hecho** (plazo terminado sin pago a tiempo): GL-049 («cuyo plazo de liquidación ya terminó sin que el Cliente lo haya pagado dentro de ese plazo»), CA-023 («si el plazo ya venció»), CA-113 («Dado que venció el plazo»), CA-025 («Dado que el saldo… venció»). **Ninguna fuente aprobada describe un acto que «registre» el vencimiento** ni dice quién lo ejecuta; el código lo modela como transición explícita (`registrar_vencimiento_saldo`, `POST /estados-cuenta/{id}/vencimiento-saldo-original`) y como evento `SaldoContratoOriginalVencido`.

**Dónde están la contradicción y las lagunas (sin elegir interpretación):**

1. **Modelo frente a fuentes:** las fuentes definen el vencimiento como hecho; el estado `Vencida` del mapa y del código solo cambia por registro. Entre el límite y el registro el sistema dice `Pendiente` aunque «el plazo ya venció» (CA-023): la consulta `GET /eventos/{id}/pagos` muestra `estado` y `fechaLimite`, pero no «si el plazo ya venció».
2. **Bloqueo de solicitudes:** GL-049 («Mientras exista este saldo vencido, no se podrá continuar con nuevas solicitudes») y el BRD hablan del saldo vencido como hecho; el código usa `saldo_vencido_sin_regularizar` = alguna obligación en estado `Vencida`. Con el saldo vencido de hecho pero sin registrar, las solicitudes siguen permitidas.
3. **«El saldo queda vencido» (C-06, CA-113):** no dice si un pago tardío completo, **antes** de cualquier registro, debe producir la transición a `Vencida` o solo no liquidar; ni cómo se calculan los cargos moratorios (GL-051: «no establece una fórmula»); hoy los introduce Administración al activar el protocolo.
4. **Anticipo (H-10):** las fuentes no dicen que un anticipo tardío liquide; el equipo lo adoptó con respaldo parcial. No contradice C-06 porque son obligaciones distintas, pero no está aprobado por separado.

**Efecto concreto de corregir solo `_destinos_verificacion` (lectura de código):** si se quita al saldo de la excepción, un pago tardío completo quedaría `Verificado` con la obligación `Pendiente`; y `registrar_vencimiento_saldo` (que excluye obligaciones con `_pagado(o) >= importe` sin límite de fecha, `_pagado` admite un parámetro `hasta`) **nunca la vencería**: el saldo pagado tarde quedaría `Pendiente` para siempre. La corrección debe tocar ambas funciones.

### N.2 D-3 — qué debe ocurrir al llegar T y qué falta decidir

**Determinado por las fuentes** (C-01, C-02, BN-009, BN-010 y la línea 96 del BRD, GL-032, GL-033, CA-109, CA-110, CA-111): llegado T, un Evento `En organización` inicia y pasa a `En ejecución` (límite inclusivo en T); uno que sigue `En gestión` pasa a `Cerrado sin contratación` (nunca `Cancelado`), su contrato pasa a `Cerrado sin confirmar`, **la contratación no puede confirmarse después de T**, el anticipo recibido se devuelve (CA-102 a CA-105; un pago registrado antes de T y verificado después se verifica sin confirmar y también se devuelve) y las solicitudes no confirmadas se cierran con un único resultado (CA-070, CA-071, CA-096). Todo es «automático»: así lo dicen C-01, BN-010, GL-032 y CA-109.

**Estados reales hoy:**

| Elemento | Comportamiento actual |
|---|---|
| Evento `En organización` con T vencida | No cambia solo. `Evento.iniciado_en` lo **deriva** para rechazar cambios, cancelaciones y servicios adicionales; el estado y `EventoIniciado` solo se producen con `POST /eventos/{id}/inicio` (`Evento.iniciar`, exige `ahora ≥ T`) |
| Evento `En gestión` con T vencida | Sigue `En gestión` (`MAQUINA_EVENTO` solo tiene INICIAR desde `En organización`; la operación devuelve 422). Simulación |
| Contrato | Solo `Firmado → Cerrado sin confirmar` y únicamente con el seguimiento de 24 h (`Contrato.cerrar_sin_confirmar`); `En preparación` no puede cerrarse; no existe un cierre «por llegar T» |
| **Confirmar después de T** | **No se rechaza** (nuevo hallazgo **D-3b**): simulación del 28/10: un evento con T = 2026-10-20 y contrato firmado se confirmó el 28/10 y quedó `En organización` (la primera ejecución de T-24 de esta guía dependía de eso). Contradice CA-110/GL-032 («la contratación ya no puede confirmarse») |
| Solicitudes | Se cierran por inicio solo tras `EventoIniciado` (reacción `al_iniciarse_evento`); con D-1 ya no pueden existir solicitudes sobre un evento sin contratación confirmada |
| Comunicaciones | No hay notificación a las partes en el cierre por inicio ni en el cierre del proceso de contratación (`reacciones.py`) |
| Procesos periódicos | Solo el trabajador del Outbox (`trabajador_outbox.ejecutar`, ciclo de 2 s) que despacha eventos pendientes; no recorre eventos por fecha. El repositorio de eventos solo ofrece `listar_todos` |

**Decisiones de negocio sin especificar (necesitan respuesta de la responsable):**

1. **Mecanismo:** las fuentes dicen «automático» pero no cómo; alternativas A a D de M.3.
2. **Contrato `Firmado` pero no confirmado en T:** C-01 y CA-110 dicen «su contrato **no firmado**»; pero un anticipo recibido, que ambos mencionan, solo existe con el contrato firmado (el estado de cuenta nace al firmar). El texto es internamente ambiguo. Opciones: (i) cerrar también el contrato `Firmado` (lectura coherente con la devolución del anticipo); (ii) solo el `En preparación` (lectura literal), dejando el `Firmado` sin estado final.
3. **Contrato `En preparación` y propuesta `En revisión` en T:** no hay estados finales definidos para la propuesta; el contrato necesitaría una transición nueva.
4. **Comunicaciones** a Cliente, Coordinador y Administración al cerrar por T: no están especificadas.
5. **Zona horaria y reloj:** `fecha_hora` del evento no lleva zona; el servidor trabaja en UTC; con un proceso automático «T» debe tener un reloj de referencia definido.
6. **Fechas pasadas:** si `POST /eventos` debe rechazar un evento cuya T ya pasó (las fuentes no lo dicen) y cómo se rechaza una confirmación posterior a T (código HTTP y mensaje).

### N.3 Mecanismo técnico recomendado para D-3 (si se aprueba una transición automática)

- **Proceso periódico en el trabajador** (alternativa A de M.3): un segundo paso dentro del bucle de `trabajador_outbox.ejecutar` (o un proceso aparte), que cada ciclo obtiene los eventos con `fecha_hora ≤ ahora` en `En organización` o `En gestión` y los procesa **uno por transacción** con el caso de uso, no con SQL directo.
- **Nuevos elementos mínimos:** método de repositorio `listar_con_fecha_vencida(ahora)` (puerto, memoria y SQL; quizá un índice en `evento(fecha_hora, estado)`, que requeriría una migración 0005 y su prueba de subida/bajada/subida); `GestionCierreEventoService.procesar_llegada_de_t(evento_id, ahora)` que reutiliza `Evento.iniciar` y, para `En gestión`, `Evento.cerrar_sin_contratacion` y un cierre del contrato (acciones nuevas en `MAQUINA_CONTRATO`, p. ej. `CERRAR_POR_INICIO`) que emita `ProcesoContratacionCerrado` para reutilizar las reacciones ya existentes (devolución del anticipo A, cierre del evento); rechazo de la confirmación cuando `ahora ≥ T` (D-3b).
- **Idempotencia:** las máquinas de estado ya aceptan repeticiones (`repeticiones_idempotentes`) y cada paso se confirma en su propia transacción: un segundo ciclo sobre un evento ya procesado no tiene efecto ni duplica eventos del Outbox.
- **Recuperación ante fallos:** un error en un evento se registra y no impide los demás ni el ciclo siguiente (patrón actual de `ejecutar`); lo ya confirmado queda y las reacciones fallidas las reintenta el Outbox (al menos una vez, con deduplicación por clave de reacción, ADR-004). Dos trabajadores a la vez: el control optimista por versión (ADR-006) hace que uno falle con conflicto y reintente sin duplicar.
- **Reloj:** inyectar el reloj (como en la API) para probar con fechas controladas.

### N.4 Plan de corrección verificable

#### D-2 — pago tardío del saldo y vencimiento

| Concepto | Plan |
|---|---|
| Regla aprobada | C-06/ND-29, GL-049, CA-113, CA-023, BN-005, GL-046 |
| Comportamiento actual | Pago tardío verificado con la obligación `Pendiente` la liquida; el vencimiento solo existe tras `POST …/vencimiento-saldo-original`; `GET …/pagos` no informa si el plazo ya venció |
| Diferencia | C-06/CA-113 (no liquida) incumplido hasta el registro; CA-023 («si el plazo ya venció») no se muestra; GL-049 (bloqueo por saldo vencido de hecho) no se aplica antes del registro |
| Archivos y funciones | `src/domain/estado_cuenta.py`: `_destinos_verificacion`, `registrar_vencimiento_saldo`, `saldo_vencido_sin_regularizar`, `_pagado`; `src/application/servicios.py`: `_saldo`; `src/application/cqrs.py`: handler de estado de pagos (y `docs/api/openapi.json` si se añade un campo) |
| Corrección mínima propuesta | (1) Quitar `SALDO_CONTRATO_ORIGINAL` de la excepción de `_destinos_verificacion` para que un pago con `fecha` posterior al límite no liquide la obligación; (2) hacer que `registrar_vencimiento_saldo` cuente solo lo pagado dentro del plazo (`_pagado(o, hasta=plazo.vence)`) para que un saldo pagado tarde pueda vencer; (3) **solo si se aprueba**: considerar vencido de hecho (`obligacion_vencida_sin_pago`) en `saldo_vencido_sin_regularizar` y mostrar «plazo vencido» en la consulta |
| Pruebas | **Unitarias** (`test_estado_cuenta_maquina_estados` y un archivo nuevo): pago un segundo antes del límite → Liquidada; a las 00:00 exactas → no Liquidada (E-1); pago tardío parcial y completo; saldo ya `Vencida`; sustitución y anticipo siguen exentos (regresión H-10 y GL-012). **Integración** (memoria y PostgreSQL): vencer tras un pago tardío completo; bloqueo de solicitudes. **Regresión**: oráculo — añadir la regla D-2 a `tests/apoyo_esperados_oraculo.py` para las claves `pagar(OB-S, 7000, despues_limite)` sobre variantes con el saldo `Pendiente` (la tabla del cierre §8 las agrupa como R12, 48 claves), sin editar el JSON; `test_oraculo_diferencias_e1_e4` con recuento nuevo |
| Documentos y diagramas | `auditoria-requisitos-fase-final.md` (C-06), `DECISIONES_E1_E4.md` o ADR nuevo si se adopta el vencimiento por hecho, `CIERRE_AUDITORIA_FINAL.md`; mapa de dominio (página 04, transición Pendiente → Vencida: disparador); no se tocan GL-049, CA-113 ni C-06 |
| Decisiones previas | (a) ¿Un pago tardío completo debe dejar el saldo `Vencida` o `Pendiente`? (b) ¿El vencimiento debe ser automático (planificador, ligado a D-3) o seguir registrándose? (c) ¿El bloqueo de solicitudes usa el hecho o el registro? (d) ¿Cómo se calculan los cargos moratorios (GL-051)? (e) ¿Se añade «plazo vencido» a la consulta (CA-023)? |

#### D-3 — llegada de T sin contratación confirmada

| Concepto | Plan |
|---|---|
| Regla aprobada | C-01, C-02, BN-009, BN-010 (BRD l. 95–96), GL-032, GL-033, CA-109, CA-110, CA-111 |
| Comportamiento actual | N.2 (sin inicio automático; `En gestión` no cierra; confirmar después de T permitido; sin comunicaciones) |
| Diferencia | Falta la transición automática o su disparador; falta el cierre del contrato por T; la confirmación posterior a T se acepta (D-3b) |
| Archivos y funciones | `src/domain/evento.py` (`MAQUINA_EVENTO`, `iniciar`, `cerrar_sin_contratacion`); `src/domain/contrato.py` (`MAQUINA_CONTRATO`, acción nueva, `confirmar_contratacion`); `src/application/servicios.py` (`procesar_inicio_evento`, `confirmar_contratacion`); `src/application/reacciones.py`; `src/application/puertos.py` y `infrastructure/persistencia/repositorios_sql.py` / `repositorios_memoria.py` (consulta por fecha); `src/infrastructure/persistencia/trabajador_outbox.py`; posible migración 0005 |
| Corrección mínima propuesta | Según la alternativa aprobada (N.3 para la A): caso de uso `procesar_llegada_de_t`, transición del contrato y rechazo de la confirmación con `ahora ≥ T` |
| Pruebas | **Unitarias:** máquinas de estado (nuevas transiciones, idempotencia); T inclusivo (`ahora == T`); confirmación en `T − 1 s` permitida y en `T` rechazada. **Integración (memoria y PostgreSQL, reloj controlado):** `En gestión` con contrato `En preparación`, `Firmado` sin pago y `Firmado` con anticipo recibido (devolución A, CA-102 a CA-105); `En organización` → `En ejecución` con cierre de solicitudes; dos ciclos seguidos; fallo en un evento sin afectar a otro; dos trabajadores; recuperación tras reinicio. **Regresión:** pruebas de inicio (`test_h08_*`), cierre sin confirmar (`test_reglas_anticipo_decisiones_abc`), oráculo de `Evento` si aplica; las 1306 pruebas |
| Documentos y diagramas | BPMN SP-07 (el temporizador «Fecha y hora de inicio del evento» ya existe; comprobar que coincida), mapa de dominio (estados del Contrato, página 01 detalle A), `secuencia_*` si se añade un flujo nuevo (p. ej. una `secuencia_3`), README (el trabajador tendría otra responsabilidad), un ADR nuevo (responsabilidad del trabajador, reloj), `auditoria-requisitos-fase-final.md` (C-01, C-02) y `complemento-trazabilidad`; la guía de T-24 (hoy usa un evento con T pasada confirmado, lo que dejaría de ser posible) |
| Decisiones previas | Las seis de N.2 y la alternativa de mecanismo (A, B, C o D de M.3) |

### N.5 Estado de la entrega: qué hay que hacer

1. **Reconstruir la imagen de Docker de forma segura** (hoy contiene el código anterior a D-1).
   - Antes: comprobar que el volumen `eventosnova_eventosnova_pgdata` existe (`docker volume ls`) y que `docker compose ps` muestra `db` sano; **nunca** `down -v`. La reconstrucción no cambia el esquema (head 0004) ni toca la base.
   - Reconstruir: `docker compose build api worker` (usa el `Dockerfile`, objetivo `app`; actualiza la etiqueta `eventosnova-app:local` que también usa el entorno manual).
   - Recrear solo los servicios de aplicación: `docker compose up -d --no-deps api worker` y `docker compose -f docker-compose.manual-test.yml up -d --force-recreate` (no recrea `db` ni `migrate`). Se interrumpen unos segundos las API.
   - Después: `/ready` en 8000 y 8001 (`persistencia: postgresql`), `alembic current` = 0004, mismos conteos de eventos, y que el archivo del contenedor contenga la corrección (`docker exec eventosnova-api-1 grep -c "D-1 (C-14" /app/src/application/servicios.py` → 1). Recién entonces una prueba manual de D-1 por Swagger (contrato firmado → 422) es válida.
2. **Suite completa y cobertura** (no se ejecutaron tras D-1): en el equipo, con PostgreSQL de pruebas y `EVENTOSNOVA_REQUIERE_BD=1`, sin paralelismo: `python -m unittest discover -s tests`; y `coverage run -m unittest discover -s tests`, `coverage report`, `coverage json -o coverage.json -q`, `python scripts/verificar_cobertura.py coverage.json`; y `docker compose run --rm tests`. Guardar los registros con nombre nuevo en `tests/evidencias/`. Si el sistema detiene un proceso por memoria, no relanzarlo automáticamente.
3. **T-21 y T-23** (guía, sección 11): T-21 en cualquier momento; T-23 solo de domingo a martes (UTC) con el evento a +4 días. Si se aprueban cambios de D-2/D-3 antes, T-23 y T-24 deben revisarse (el bloqueo por saldo vencido de hecho y la imposibilidad de confirmar después de T cambiarían el procedimiento de T-24).
4. **Regenerar PDF y presentación**, con los resultados reales de T-21/T-23 y el estado final de D-1 a D-3: actualizar en `scripts/generar_entrega_pia.py` `VALIDACION_MANUAL_T21_T23`, los textos de D-1 (ahora corregido), D-2, D-3 y `FECHA`; ejecutar con el entorno aislado `C:\pia_env_tmp`; revisar visualmente cada página y diapositiva (`pymupdf` y PowerPoint) y actualizar la fila 27 de la bitácora formal y su PDF (Word).
5. **Consistencia final:** tras cualquier cambio de D-2/D-3, regenerar `auditoria-requisitos-fase-final.md` y `trazabilidad-api-persistencia.md`, ejecutar las pruebas de documentación, actualizar mapa de dominio, `secuencia_1`/nuevas, BPMN afectados y `LEEME_EXPORTACIONES.txt`, y revisar que la matriz aprobada no necesite filas nuevas (no se modifica sin aprobación).


## O. Corrección de D-1, D-2 y D-3: estado real (2026-10-28 / 29, posterior a N)

> Las secciones J, M y N se conservan como historial. **La etapa 2 sigue sin cerrarse:** faltan T-21, T-23 y T-24 con el código actualizado, la aprobación externa de las decisiones internas, y la regeneración final del PDF, la presentación y la bitácora con esos resultados.

### O.1 Estado de cada defecto

| Defecto | Estado | Qué se hizo | Pruebas |
|---|---|---|---|
| **D-1** servicio adicional sin contratación confirmada (C-14, GL-015, CA-101) | **Corregido y desplegado** | `GestionServiciosAdicionalesService.registrar_solicitud_servicio_adicional` rechaza (HTTP 422) si el contrato no está confirmado, sin evaluar plazo ni saldo y avisando al Cliente | `tests/test_d1_servicio_adicional_contratacion_confirmada.py` (26) |
| **D-2** pago tardío del saldo (C-06, CA-113, GL-049, BN-005, CA-023) | **Corregido y desplegado** | `EstadoCuenta._destinos_verificacion` ya no liquida el saldo con un pago de fecha posterior a su límite y solo cuenta lo pagado en plazo (`_pagado_para_liquidar`); `registrar_vencimiento_saldo` puede vencer un saldo pagado tarde; `GET /eventos/{id}/pagos` informa `plazoVencido` por obligación (CA-023) | `tests/test_d2_pago_tardio_del_saldo.py` (22); el oráculo se valida con la regla D-2 (48 claves, grupo R12 del cierre §8) |
| **D-3** llegada de T (C-01, C-02, CA-109 a CA-111, GL-032, GL-033) y **D-3b** | **Corregido y desplegado** | `procesar_eventos_vencidos` (ciclo del trabajador, un evento por transacción, idempotente, reloj inyectable); `procesar_inicio_evento` cierra un Evento En gestión sin contratación al llegar T; `Contrato.cerrar_por_inicio` (En preparación y Firmado → Cerrado sin confirmar, reutiliza `ProcesoContratacionCerrado`); `IEventoRepository.listar_con_fecha_vencida`; la confirmación con `ahora ≥ T` se rechaza | `tests/test_d3_llegada_de_t.py` (33, memoria y PostgreSQL) |

**Antes de corregir se comprobó el defecto:** D-1: 8 de 13 pruebas en memoria fallaban con el código anterior; D-2: 6 de 11 fallaban (5 fallos y 1 error); D-3/D-3b: 3 de las 4 pruebas de HTTP y de confirmación fallaban (la operación `/inicio` sobre un Evento En gestión daba 422, y se confirmaba después de T).

### O.2 Decisiones internas aplicadas (sin aprobación externa)

Las fuentes dicen «automático» y «contrato no firmado» sin precisar el mecanismo ni el caso del contrato firmado. Se aplicó (ADR-008): proceso periódico en el trabajador; contrato `Firmado` también cerrado al llegar T; aviso a Cliente, Coordinador y Administración; T comparado con el reloj del servidor sin zona (UTC en Docker); confirmación rechazada desde T inclusive; un pago tardío completo deja el saldo `Pendiente` hasta registrar el vencimiento; el bloqueo de solicitudes sigue usando el estado `Vencida` registrado (no el hecho de superar el límite: extenderlo exigiría rediseñar la regularización). **No se afirma ninguna aprobación de la docente ni de una responsable externa.** *(Corrección, sección P: el reloj «UTC sin zona» y el bloqueo «por estado registrado» de esta lista quedaron sin efecto: rige TP-06 y el vencimiento de hecho de GL-049.)*

### O.3 Cambios en pruebas existentes (por cambio de regla, no para ocultar fallos)

- `tests/test_contrato_maquina_estados.py`: la tabla esperada incluye las dos transiciones nuevas de C-01.
- `tests/test_h06_h07_h21_correcciones.py`: `procesar_eventos_vencidos` no recibe identificadores (como `registrar_evento`), por lo que se excluye de la comprobación de «identificador inexistente».
- `tests/test_estado_cuenta_maquina_estados.py` y `tests/apoyo_esperados_oraculo.py`: la regla D-2 se suma a E-1, H-10 y E-3/E-4; recuento exacto `{E-1: 1203, E-3/E-4: 69, H-10: 42, D-2: 48}`. `tests/test_oraculo_diferencias_e1_e4.py`: nuevo recuento por combinación. **El JSON del oráculo no se tocó** (SHA-256 `d98b4cff…`).
- Documentos generados: `auditoria-requisitos-fase-final.md` (C-01, C-02, C-06, C-14 ahora «Implementada · Con pruebas») y `trazabilidad-api-persistencia.md`.

### O.4 Resultados medidos

| Entorno | Pruebas | Resultado | Evidencia |
|---|---|---|---|
| Equipo (PostgreSQL obligatorio, con cobertura) | 1387 | OK, 0 fallos, 0 errores, 0 omitidas | `tests/evidencias/ejecucion-pruebas-d1-d3-host-20261028.txt` |
| Docker (`docker compose run --build --rm tests`) | 1387 | OK | `tests/evidencias/ejecucion-pruebas-d1-d3-docker-20261028.txt` |
| Cobertura | — | **98,82 %** de sentencias (5448 de 5513) · **95,77 %** de ramas (1042 de 1088) · cumple el mínimo de 80 % | `tests/evidencias/cobertura-d1-d3-20261028.txt` |
| Oráculo | 1203 claves | 0 sin explicar: E-1 (1203), H-10 (42), E-3/E-4 (69), D-2 (48) | `tests/evidencias/diferencias-oraculo-d2-20261028.txt` |

(1387 = 1306 anteriores + 26 + 22 + 33.) Las pruebas de PostgreSQL usaron `eventosnova_test`; no se tocaron las bases de desarrollo ni la manual con datos de negocio. En una primera ejecución de la suite hubo 5 fallos legítimos por cambio de regla (O.3); tras ajustarlos y regenerar los documentos, pasó completa.

### O.5 Imágenes Docker

Docker Desktop estaba apagado al empezar; se inició y PostgreSQL (`eventosnova-db`, volumen `eventosnova_eventosnova_pgdata`) volvió sano con los datos intactos (desarrollo: 2 eventos; manual: 5, igual que antes). Se reconstruyó `eventosnova-app:local` (`docker compose build api worker`, id `d5487c827385`) y se recrearon `api` y `worker` (`up -d --no-deps`) y `api-manual` y `worker-manual` (`-f docker-compose.manual-test.yml up -d --force-recreate`), sin tocar `db` ni `migrate` ni borrar volúmenes. Verificado en **los cuatro contenedores**: imagen `d5487c827385` y las marcas de D-1, D-2, D-3 y D-3b presentes en `/app/src`; `/ready` 200 `postgresql` y `/health` y `/docs` 200 en 8000 y 8001; Alembic `0004 (head)` en ambas bases; `GET /eventos/{id}/pagos` ya devuelve `plazoVencido`; 60 operaciones en `/openapi.json`; sin errores en el registro del trabajador manual.

### O.6 Efectos que el equipo debe conocer

1. **El trabajador de desarrollo y el manual ya aplican la llegada de T.** Los eventos que siguen `En gestión` con T futura serán **cerrados sin contratación al llegar T**: en desarrollo `EV-0028db33` (2026-11-20 18:00 UTC; es el evento de demostración) y `EV-aab4eaa9-…` (2030); en la base manual `EV-8e2a6f41-…` (31/10/2026 18:00 UTC, el T-23 de la primera ejecución), `EV-5d7df250-…` y `EV-d8d49221-…` (20/11/2026). Es el comportamiento de C-01; si se quiere conservar el evento de demostración `En gestión` más allá de su fecha hay que cambiar su `fecha_hora` por la vía normal de la aplicación o detener el trabajador de desarrollo (decisión del equipo; no se hizo).
2. T-24 ya no puede apoyarse en un evento con fecha pasada ni en iniciar con `/inicio` antes de tiempo: la guía (sección 12.6) usa un evento a +40 minutos que el trabajador inicia solo.
3. La API de desarrollo (8000) y la manual (8001) comparten ahora el código corregido.

### O.7 Pendiente (no se ha ejecutado ni aprobado)

T-21, T-23 y T-24 con el código actualizado (guía, sección 12; `scripts/preparar_pruebas_manuales.py`), la aprobación externa de las decisiones internas, el archivado de las capturas, la transcripción de los prompts de la bitácora y la versión final del PDF, la presentación y la bitácora con esos resultados. Repositorio remoto, CI y despliegue siguen sin existir.


## P. Verificación previa a T-21, T-23 y T-24: vencimiento de hecho y reloj de negocio (2026-10-28, posterior a O)

> Corrige dos puntos de la sección O. No cambia reglas de negocio ni el oráculo. **La etapa 2 sigue sin cerrarse.**

### P.1 D-2: bloqueo de solicitudes por vencimiento de hecho

- **Hallazgo (comprobado):** con el plazo del saldo vencido, lo pagado dentro del plazo sin cubrirlo y `registrar_vencimiento_saldo` sin ejecutar, una solicitud de cambio nueva quedaba `Registrada`: `_saldo` leía solo el estado registrado `Vencida`. Contradice GL-049 («Mientras exista este saldo vencido, no se podrá continuar con nuevas solicitudes»; «vencido» = plazo terminado sin pago a tiempo), SE-006 (BRD), BN-003/BN-005 y CA-023/CA-113, que definen el vencimiento por el hecho. La sección O.2 había dejado esto sin corregir; se corrige.
- **Documentos citados que no se encontraron:** no existe en el repositorio un «apartado C.3 del documento de resolución» ni un símbolo `reloj_negocio` anterior a esta corrección (`docs/architecture/resolucion-tp01.md` trata la persistencia, no el vencimiento ni el reloj). La corrección se apoya en GL-049, SE-006, BN-003/BN-005, CA-023, CA-113 y C-06.
- **Corrección:** `EstadoCuenta.saldo_vencido_en(ahora)` (`src/domain/estado_cuenta.py`): el saldo está vencido de hecho si alguna obligación del saldo general está `Vencida` o está `Pendiente` con el plazo superado (límite exclusivo, E-1), lo pagado dentro del plazo (`_pagado_para_liquidar`) no la cubre y no hay un pago a tiempo pendiente de verificación (mismo criterio que `registrar_vencimiento_saldo`). `_saldo(repositorio, contrato_id, ahora)` en `src/application/servicios.py` lo usa en el registro de cambios y servicios adicionales y al retomarlos. `registrar_vencimiento_saldo` sigue siendo el acto formal que habilita el protocolo de cobro y la regularización.
- **Pruebas de regresión** (`tests/test_d2_pago_tardio_del_saldo.py`, +20, memoria y PostgreSQL de pruebas): vencimiento de hecho en el límite exacto y un segundo antes, pago parcial a tiempo, pago tardío completo, saldo liquidado a tiempo, pago a tiempo pendiente de verificación, solicitud detenida con el vencimiento sin registrar y registrada antes del límite o con el saldo liquidado a tiempo. Antes de corregir fallaban 7 de las 10 en memoria.
- **Ajustes a pruebas existentes (por el cambio de regla):** `tests/test_n6_validacion_servicio_adicional.py` espía ahora `saldo_vencido_en` en lugar de la propiedad; `tests/test_e3g_cargo_tardio_y_conceptos.py` paga el saldo a tiempo cuando el escenario pide un cambio después del límite del saldo (esos casos prueban el cargo tardío, no el bloqueo).
- **Alcance real:** un servicio adicional con menos de cinco días naturales se rechaza antes por el plazo (orden de SE-004), y con cinco días o más el límite del saldo (tres días hábiles antes del evento) aún no ha pasado: el bloqueo por saldo se observa en los cambios y en las solicitudes que se retoman.

### P.2 Reloj de negocio

- **Fuente vigente:** el cierre de alcance aprobado (§ de pendientes técnicos, **TP-06**: «Zona horaria `America/Mexico_City` — Se mantiene») y la documentación del esquema («el dominio usa fechas locales sin zona; el cierre mantiene `America/Mexico_City`»). No hay ninguna decisión aprobada que autorice usar UTC.
- **Discrepancia hallada:** `dependencias.obtener_reloj`, el trabajador y el despachador del Outbox usaban `datetime.now()`, la hora del sistema: en los contenedores, UTC (el servidor marcaba 01:36 mientras en la Ciudad de México eran las 19:36). Las fechas que se escriben en la API (`NaiveDatetime`) y se guardan (`TIMESTAMP` sin zona) son horas de pared de la Ciudad de México; con UTC, los plazos, el límite del saldo, la llegada de T y la verificación de `confirmar` se desfasaban 6 horas. La sección O.2 había decidido «UTC sin zona»: era una decisión interna que contradice TP-06 y **queda sin efecto**.
- **Corrección:** nuevo `src/application/reloj.py` con `reloj_negocio()` (hora de pared de `America/Mexico_City`, sin zona; `zoneinfo`, que usa la base de zonas del sistema en la imagen `python:3.13-slim` y el paquete `tzdata` que ya trae `psycopg` en Windows; sin dependencias nuevas). Lo usan `api.dependencias.obtener_reloj`, `trabajador_outbox.ejecutar` (por omisión) y `DespachadorOutboxSQL` (por omisión). No se convierte ninguna fecha almacenada ni recibida; solo cambia la fuente del instante actual. Se comprobó en el contenedor en marcha que la zona está disponible.
- **Pruebas** (`tests/test_reloj_negocio.py`, 8): zona aprobada; conversión de instantes UTC a la hora de pared (incluida la medianoche de negocio); el reloj actual coincide con la Ciudad de México y no con UTC; la API, el trabajador y el Outbox usan `reloj_negocio` por omisión; ningún archivo de producción vuelve a usar la hora local del sistema.
- **Guías:** `scripts/preparar_pruebas_manuales.py` calcula con `reloj_negocio` (hora de la Ciudad de México) y la guía (sección 12 y una nota al inicio) deja de hablar de UTC; las secciones 0 a 11 se conservan como historial de la primera ejecución. La comprobación del reloj en la guía usa `reloj_negocio`, no `date`.
- **Ventanas de T-23 con la hora de negocio:** el script marca T-23 ejecutable el miércoles 28/10/2026 hasta poco antes de la medianoche (el límite del saldo es el jueves 29/10 a las 00:00 de la Ciudad de México); después, el primer día válido es el domingo 01/11/2026.

### P.3 Pruebas de esta verificación

Suite completa en el equipo (PostgreSQL obligatorio, sin cobertura): **1415 pruebas OK** (1387 + 20 de D-2 + 8 del reloj), 0 fallos, 0 errores, 0 omitidas (`tests/evidencias/ejecucion-pruebas-d2b-reloj-host-20261028.txt`). Antes, un conjunto focalizado de 754 pruebas dio 3 fallos legítimos por el cambio de regla (los dos espías/fixtures de las suites N6 y E3G, arriba), ya resueltos. **No se volvió a medir la cobertura (98,82 % / 95,77 % corresponden a las 1387 pruebas) ni la suite en Docker.** El oráculo JSON no se tocó (`d98b4cff…`).

### P.4 Importante: las imágenes en marcha son anteriores a esta corrección

Los cuatro contenedores ejecutan la imagen `d5487c827385`, construida **antes** de P.1 y P.2: siguen usando la hora UTC y el bloqueo por estado registrado. **Antes de T-21, T-23 y T-24 hay que reconstruir las imágenes y recrear los contenedores** (guía, 12.0 bis); no se hizo porque esta tarea prohibía reiniciar contenedores. Los eventos `En gestión` serán cerrados por el trabajador al llegar su `fecha_hora` **en hora de la Ciudad de México** (por ejemplo `EV-0028db33`, el 20/11/2026 a las 18:00 de la Ciudad de México; `EV-8e2a6f41-…`, el 31/10/2026 a las 18:00).


## Q. Cierre documental con los resultados finales (2026-10-29, posterior a P)

> No se modificó código de producción, pruebas, migraciones, bases de datos, contenedores ni el oráculo histórico. No se ejecutó la suite: las cifras salen de los registros de `tests/evidencias/` y de los resultados que el equipo informó. Lo que no consta en el repositorio se indica como tal.

### Q.1 Validación manual con el código corregido (resultados informados por el equipo)

Entorno: API manual del puerto 8001 y su trabajador (guía, sección 12). Las capturas no están en el repositorio y no se vieron. Varias operaciones de T-21 y de T-23 compartieron el mismo valor de *timestamp*: se registra el resultado funcional, **no** una secuencia temporal exacta ni horas reales distintas por paso.

| Caso | Evento y contrato | Resultado decisivo | Clasificación |
|---|---|---|---|
| T-21 · cancelación de un evento independiente | `EV-157c1d85-2609-49ba-8ff7-2585d8780239` (no es el evento principal de T-19 y T-20) | PC-1 a PC-10 con 201/200 (contratación confirmada, Evento `En organización`, anticipo `Liquidada`); confirmación adicional 200 «La contratación ya estaba confirmada.»; cancelación 200 «Evento cancelado.»; administración 200 `Cancelado`; `GET /solicitudes` 200 `{"solicitudes":[]}` | **Aprobada.** La lista vacía solo muestra que el evento no tenía solicitudes al consultarse; no prueba el cierre de solicitudes (no se creó ninguna) |
| T-23 · servicio adicional con menos de cinco días naturales | `EV-c5ac61cc-5ce4-412f-96df-ca109dae427a` · `CT-29214729-b65b-4cdb-a379-1389c2a74e68` | Contratación confirmada (administración 200: `En organización`, `Contratación confirmada`, anticipo `Liquidada`); saldo previo `7000.00` `Pendiente`, `fechaLimite` `2026-10-29T00:00:00` posterior al reloj de negocio consultado; `POST /solicitudes-servicio-adicional` **201** «Solicitud No procedente.», motivo «Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).»; `GET /solicitudes` `No procedente`, `pendiente: false`; saldo posterior `7000.00` `Pendiente` | **Aprobada.** Cumple las precondiciones de la guía que faltaban en la primera ejecución. Es una solicitud registrada como `No procedente` por el plazo, no el rechazo 422 de CA-101 |
| T-24 · cambio después del inicio | `EV-c0595c85-6ce9-45cd-a45b-15996de7e26a` · `CT-c9583b55-5be2-473b-94b3-8f2112844bee` | Antes de la hora: `En organización`, `Contratación confirmada`, anticipo `Liquidada`; después: 200 `En ejecución`, transición hecha por el trabajador (D-3, CA-109); `POST /solicitudes-cambio` **422** «El cambio solo procede después de contratar y antes del inicio (CA-039).»; `GET /solicitudes` `{"solicitudes":[]}` | **Aprobada.** El 422 es el resultado esperado; no se registró ninguna solicitud de cambio |

### Q.2 Última ejecución automatizada registrada

| Entorno | Pruebas | Resultado | Cobertura | Evidencia |
|---|---|---|---|---|
| Docker (`docker compose run --build --rm tests`, PostgreSQL obligatorio) | 1415 | `Ran 1415 tests … OK` (sin fallos, errores ni omitidas) | 98,82 % de sentencias (5462 de 5527; 65 sin cubrir) · 95,77 % de ramas (1042 de 1088) · «cumple el mínimo de 80 %» | `tests/evidencias/ejecucion-docker-final-20261028-202102.txt` (UTF-16, 28/10/2026 20:21) |
| Equipo (PostgreSQL obligatorio, sin cobertura) | 1415 | OK | — | `tests/evidencias/ejecucion-pruebas-d2b-reloj-host-20261028.txt` |

Coincide con el informe del equipo (1415, 0 fallos, 0 errores, 0 omitidas, 98,82 % / 95,77 %, umbral 80 %). **El código de salida 0 no figura en el registro**: lo informó el equipo. Las cifras 5448/5513 y 1387 de §O.4 corresponden a la ejecución anterior; la diferencia de sentencias (+14) es el código de P (`saldo_vencido_en` y `reloj.py`). La línea `TOTAL … 98.3%` del informe de texto combina sentencias y ramas. El oráculo `tests/referencias/comportamiento_estado_cuenta_v8_e3c.json` conserva el SHA-256 `d98b4cff85db0aa99bdbdd118b1045f5415f5dde46295f5c1f08d5a8fdb3c696` (calculado el 29/10/2026). Los avisos `ERROR [eventosnova…]` del registro son mensajes de registro de pruebas que provocan fallos a propósito; esas pruebas terminan en `ok`.

### Q.3 Comportamiento vigente de D-1, D-2 y D-3 (comprobado en el código)

- **D-1 (C-14, GL-015, CA-101):** `GestionServiciosAdicionalesService.registrar_solicitud_servicio_adicional` rechaza con HTTP 422 y aviso al Cliente si el contrato no está `Contratación confirmada`, antes de crear la solicitud y sin evaluar plazo ni saldo. Con la contratación confirmada la solicitud se registra y se evalúa en orden Evento, plazo de cinco días naturales y saldo; un plazo incumplido da `No procedente` (HTTP 201), como en T-23.
- **D-2 (C-06, GL-049, CA-113, BN-005):** `Pago.fecha` es la fecha efectiva del pago; `registrado_en` y `verificado_en` no cambian el plazo. Un pago del saldo con fecha posterior a su límite se verifica (y emite `PagoVerificado`) pero no liquida (`_pagado_para_liquidar`); el anticipo (H-10) y la sustitución concretada tarde conservan su excepción. **Vencimiento de hecho:** `EstadoCuenta.saldo_vencido_en(ahora)` (plazo superado, lo pagado en plazo no cubre y sin pago a tiempo pendiente de verificación) detiene las solicitudes nuevas y las que se retoman, aunque la obligación siga `Pendiente`. **Transición `Vencida`:** solo con `registrar_vencimiento_saldo` (`POST /estados-cuenta/{id}/vencimiento-saldo-original`, acto de Administración; el trabajador no la ejecuta), que habilita el protocolo de cobro. **Regularización:** `resolver_regularizacion` liquida saldo y cargos moratorios si lo pagado con fecha dentro de la ventana de 24 h los cubre, incluidos pagos posteriores al límite original. `GET /eventos/{id}/pagos` informa `plazoVencido` por obligación. **No existe un campo `pagadoEnPlazo`** en el código ni en `docs/api/openapi.json`; no se documenta. No se definieron fórmulas de moratorios: el importe lo indica Administración (GL-051).
- **D-3 (C-01, C-02, CA-109 a CA-111) y D-3b:** el trabajador ejecuta `procesar_eventos_vencidos(reloj_negocio())` en cada ciclo antes de despachar el Outbox: Evento `En organización` con T alcanzado → `En ejecución` (`EventoIniciado`, cuyas reacciones cierran las solicitudes en trámite y aplican SE-012); Evento `En gestión` → el contrato `En preparación` o `Firmado` pasa a `Cerrado sin confirmar` (`ProcesoContratacionCerrado`: Evento `Cerrado sin contratación`, anticipo Pendiente → Sin efecto y devolución A de lo recibido, también si se verifica después de T) o, sin contrato abierto, el Evento se cierra directamente; con la contratación ya confirmada y la reacción pendiente no se cierra nada. Un evento por transacción; los ya procesados dejan de aparecer en la consulta, por lo que repetir el ciclo no duplica efectos. `confirmar_contratacion` rechaza desde T (inclusive). Reloj: `America/Mexico_City` sin zona (TP-06), común a API, trabajador y Outbox.

### Q.4 Documentos y diagramas actualizados el 29/10/2026

README; ADR-008; esta sección y notas de actualización en §H, §I y §L; guía de pruebas manuales (§10.1 y notas); `PROGRESO_FASE_FINAL.md`; `complemento-trazabilidad-fase-final.md`; `auditoria-final-pia.md` (filas 10, 11, 15 y 16); `esquema-relacional-postgresql.md` y `ci-cd-y-despliegue.md` (trabajador); matriz de trazabilidad (`.xlsx` y `.pdf`: columnas de componentes y ADR de las filas 10, 11, 17, 27, 28 y 29; reglas, historias y criterios sin cambios); documentos generados `auditoria-requisitos-fase-final.md` y `trazabilidad-api-persistencia.md` (con sus generadores); mapa de dominio; diagramas de clases y de secuencia; BPMN SP-02 y maestro con su versión paginada; informe de arquitectura (`.docx` y `.pdf`: tablas de casos de uso, decisiones y transacciones y figuras 3.2, 3.4, 3.5 y 11.1 a 11.5); bitácora formal de IA (iteraciones 31 y 32) y su complemento; reporte final y presentación (`scripts/generar_entrega_pia.py`, solo textos y fuentes de datos); `docs/entrega/LEEME.md` y `diagramas/LEEME_EXPORTACIONES.txt`. **No se modificaron** el BRD, las historias de usuario y sus criterios, el glosario (aprobados y coherentes con el código corregido), el cierre de alcance ni el ADR en Word (ADR-001 a ADR-004).

### Q.5 Estado de los entregables (sustituye a las filas correspondientes de §L)

| Entregable | Estado |
|---|---|
| D-1, D-2, D-3 y D-3b | Implementado · Verificado (1415 pruebas en Docker) · decisiones internas sin aprobación externa |
| T-21, T-23 y T-24 con el código corregido | Aprobadas según los resultados informados; capturas sin archivar y plantilla de la guía (§9) sin completar |
| Mapa de dominio, UML, BPMN SP-02/maestro/paginado | Fuentes actualizadas; exportaciones regeneradas y revisadas visualmente (detalle en `diagramas/LEEME_EXPORTACIONES.txt`) |
| BPMN SP-04 | Coherente con el código (compuerta de contratación confirmada); sin cambios |
| Informe de arquitectura | Actualizado; PDF regenerado con LibreOffice (69 páginas, antes 68); figuras y tablas revisadas visualmente |
| Matriz de trazabilidad | Columnas de componentes y ADR actualizadas; PDF regenerado (6 páginas, mismo aspecto) |
| Bitácora formal de IA | Iteraciones 31 y 32 añadidas; PDF regenerado con LibreOffice (8 páginas; antes, 7 con Word); prompts sin transcribir |
| PDF de entrega y presentación | Regenerados el 29/10 con los resultados finales; revisados visualmente |
| Repositorio remoto, CI en GitHub y despliegue | No existen |

### Q.6 Pendientes y discrepancias que no se resuelven editando documentos

1. **Decisiones internas sin aprobación externa:** cierre del contrato `Firmado` al llegar T y avisos a Cliente, Coordinador y Administración (ADR-008); E-2, E-3, E-4, el control de comprobante repetido y el método de validación del oráculo (ADR-007). No se presentan como aprobadas.
2. **C-01 y CA-110 frente a la implementación:** las fuentes aprobadas nombran solo el contrato «no firmado»; el código cierra también el `Firmado`. Se conserva el texto aprobado y la extensión se marca como decisión interna (BPMN SP-02 y maestro, mapa de dominio, matriz).
3. **Anticipo inferior al 30 %:** GL-011, las consecuencias de la decisión B, la matriz (regla de la fila 29) y el BPMN SP-02 («Informar al Cliente que el anticipo es inferior al 30 % para que lo corrija») piden corregirlo; el código suma pagos parciales (E-3). La regla aprobada no se cambió; requiere aprobación de E-3 o un cambio de código.
4. **CA-109 frente a GL-015 / SE-004:** CA-109 dice que desde T «no se podrán … registrar nuevos servicios adicionales»; GL-015 y SE-004 ordenan registrarlos como `No procedente` si el Evento ya inició, que es lo que hace el código. Ambas son fuentes aprobadas; la diferencia es de redacción y no se resolvió sin la responsable.
5. **Cita de C-14:** el cierre de alcance aprobado cita GL-044 (anexo al contrato); la regla está en GL-015. El cierre no se modifica.
6. **Terminología del cierre por inicio:** GL-032 y los BPMN dicen que las solicitudes pendientes «se cierran como no procedentes»; el estado del código es «Cerrada por inicio del evento».
7. **Limitaciones de evidencia:** capturas de T-21, T-23 y T-24 no archivadas; *timestamps* repetidos; el código de salida de la suite no consta en el registro; la prueba documental `test_openapi_exportada` no puede comprobarse en este entorno (versión distinta de Pydantic; `docs/api/openapi.json` no se modificó).
8. **Exportaciones:** SP-02, el maestro y su paginado salen ahora del exportador de draw.io (aspecto distinto de SP-01 y SP-03 a SP-08); la bitácora y el informe se exportaron con LibreOffice. `MANIFIESTO_SHA256.txt` (fase 1, 24/10) ya no coincide con los documentos modificados y no se regeneró.
9. **Otros pendientes conocidos:** AR-08 (devolución inexistente → `StopIteration`), repositorio remoto, CI en GitHub y despliegue.

### Q.7 Dictamen vigente

**LISTO PARA ENTREGA CON PENDIENTES DOCUMENTADOS.** El código corregido cumple las reglas aprobadas de D-1, D-2 y D-3, con pruebas automatizadas y la validación manual informada, y la documentación y los diagramas describen ese comportamiento. **No se declara una coherencia del 100 %:** quedan las decisiones internas sin aprobación externa y las discrepancias entre fuentes aprobadas de Q.6, además de las acciones externas (repositorio, CI y despliegue).

### Q.8 Revisión focalizada del 29/10/2026 (A a D)

Se conserva Q.6 como estaba; esta sección registra lo que cambió después.

- **Q.6 punto 2 (D-3, contrato Firmado):** sigue siendo decisión interna sin aprobación externa; se añadió nota fechada en BRD e historias de usuario, y el BPMN SP-02 y el maestro indican «En preparación o Firmado (D-3)».
- **Q.6 punto 3 (E-3):** se mantiene como decisión del equipo sin aprobación externa; GL-011, BRD, historias de usuario y BPMN SP-02 llevan nota fechada o etiqueta «(E-3)». No se cambió la regla aprobada.
- **Q.6 punto 4 (CA-109 frente a GL-015 / SE-004):** interpretación del equipo registrada en ADR-008 (revisión 29/10/2026): desde T no se tramita ningún servicio adicional y la solicitud se registra como `No procedente`. Sigue sin aprobación externa.
- **Q.6 punto 6 (terminología):** `No procedente` y `Cerrada por inicio del evento` quedan diferenciados en glosario, BRD, matriz y BPMN SP-03, SP-04, SP-05 y maestro.
- **Q.6 punto 9 (AR-08):** corregido: `EstadoCuenta.registrar_devolucion_efectuada` lanza `ErrorDominio` y tiene prueba directa.
- **Contrato OpenAPI:** `GET /eventos/{evento_id}/pagos` ya tiene `response_model` y `docs/api/openapi.json` describe `plazoVencido`.
