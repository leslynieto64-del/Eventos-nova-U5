# Progreso de la fase final (cierre funcional, técnico y PIA)

Estado inicial de Git guardado fuera del repositorio (`%TEMP%\git_status_inicial_fase_final.txt`, 140 entradas).

| Etapa | Contenido | Estado |
|---|---|---|
| 0 | Estado inicial y línea base | Completada: 1159 pruebas OK, Alembic en 0002, API/worker/db en Docker activos (`tests/evidencias/ejecucion-pruebas-fase-final-etapa0-20261024.txt`) |
| 1 | Reglas de anticipo (decisiones A, B, C) | Completada (ver sección) |
| 2 | Identificadores | Completada |
| 3 | Outbox y concurrencia | Completada |
| 4 | Trazabilidad HTTP | Completada |
| 5 | Coherencia solicitud–contrato–evento | Completada (decisión pendiente del responsable) |
| 6 | Integraciones simuladas | Completada (todas siguen simuladas) |
| 7 | Auditoría de requisitos | Completada (brecha GL-060) |
| 8 | Validación de pruebas y persistencia | Completada |
| 9 | Docker Compose | Completada |
| 10 | CI/CD | Preparada; sin ejecución en GitHub |
| 11 | Despliegue | No realizado (sin recursos) |
| 12 | Documentación y entregables | Completada |
| 13 | Auditoría final del PIA | Completada |

## Etapa 1: reglas de anticipo (2026-10-24)
- **Recuperación tras el apagado:** se verificó el estado real; los cambios de dominio, esquema, mapeador, servicio, reacción y consultas estaban completos y solo faltaba la migración 0003. Docker Desktop se reinició (los contenedores `db`, `api` y `worker` volvieron solos) y PostgreSQL terminó su recuperación sin pérdida de datos (dev conserva 1 evento y 1 propuesta).
- **Dominio:** `EstadoCuenta` (cierre de contratación, devolución del anticipo, anticipo como mínimo, recibido/aplicado/excedente, el saldo solo descuenta lo aplicado), `Devolucion` (tipo, pago, fecha de referencia, límite exclusivo), `limite_exclusivo_dias_habiles`, `TipoDevolucion`.
- **Aplicación:** `GestionPagosService.aplicar_cierre_contratacion`, reacción a `ProcesoContratacionCerrado`, consulta de devoluciones con `tipo` y `pagoId`.
- **Persistencia:** migración `0003` (aplicada a dev y pruebas), mapeador, esquema.
- **Pruebas nuevas:** `test_reglas_anticipo_decisiones_abc` (25), `test_persistencia_devolucion_anticipo` (5, PostgreSQL). Modificadas por superarlas la decisión A aprobada (T-48): `test_h10_anticipo_liquidado` (esperaba «sin devolución»), y las de cadena de migraciones (`test_esquema_postgresql`, `test_migraciones_ciclo`, `test_esquema_postgresql_real`, `test_persistencia_conexion`).
- **Resultados:** suite completa con `EVENTOSNOVA_REQUIERE_BD=1`: 1190 pruebas OK en el equipo y 1190 OK en Docker; ninguna prueba previa fue eliminada ni relajada salvo la expectativa de T-48 indicada.
- **Hallazgo:** con un pago ya recibido antes del contacto el seguimiento se rechaza («anticipo ya recibido»); la devolución de un pago de importe incorrecto solo se alcanza si el pago se efectúa tras las 24 h del contacto (comportamiento previo, no modificado).
- **Incidente:** el primer `docker compose up` tras el apagado devolvió `migrate` con código 255 (la base seguía en recuperación); la repetición terminó con código 0.
- **Interpretaciones por confirmar:** ver `docs/trazabilidad/complemento-trazabilidad-fase-final.md`.
- **Siguiente paso:** Etapa 2 (identificadores).

## Etapa 2: identificadores (2026-10-24)
- `nuevo_id` ahora genera prefijo + UUID v4 completo; `nuevo_id_libre` verifica que la raíz nueva no exista (7 puntos de creación: EV, PR, CT, EC, SC, SA, SP); `EstadoCuenta` rechaza obligación o pago con id repetido. Los ids históricos (`EV-0028db33`) siguen válidos y se probaron con claves foráneas.
- Pruebas: `test_identificadores` (10, incluida una colisión forzada en memoria y en PostgreSQL). Suite completa con BD obligatoria: 1200 OK.
- Garantía: estadística (122 bits), no absoluta; documentada en D-10.
- Siguiente paso: Etapa 3 (Outbox y concurrencia).

## Etapa 3: Outbox y concurrencia (2026-10-24)
- **Auditoría del Outbox (sin cambios de código necesarios):** registro en la misma transacción que el agregado, codec versionado, claves estables `módulo.Clase.método` (no dependen del orden de suscripción), reintentos con tope y paso a Revisión, recuperación de pendientes, `FOR NO KEY UPDATE SKIP LOCKED` para dos trabajadores. Garantía real: entrega *al menos una vez* con deduplicación por reacción; no se afirma «exactamente una vez».
- **Concurrencia:** control optimista por versión en las 7 raíces (migración `0004`), `ConflictoDeConcurrencia` → HTTP 409 `conflicto_de_concurrencia`, reversión completa de la operación. No se bloquea globalmente: probado que escrituras de agregados distintos no se esperan.
- **Pruebas nuevas** `test_concurrencia_optimista` (13): copia obsoleta, reintento tras conflicto, siete raíces, crear con id existente, versión inexistente, dos hilos reales (5 rondas: exactamente uno se confirma, nada se pierde), agregados distintos sin bloqueo, reversión completa, 409 en la API, reintento de una reacción con conflicto, paso a Revisión si persiste, y reaplicar reacciones de pagos sin duplicar obligaciones, pagos ni devoluciones.
- **Tests adaptados** (expectativas no relajadas, solo semántica nueva): `test_persistencia_repositorios` (dos pruebas ahora parten de un agregado leído en lugar de una instancia nueva con id existente), `test_persistencia_unidad_trabajo` (bucle que re-guardaba un id nuevo), cadena de migraciones 0001→0004.
- **Incidente:** una primera ejecución quedó colgada porque una prueba dejaba una transacción abierta tras el conflicto; dos procesos de prueba huérfanos (PIDs propios) se terminaron por PID. No se tocó la base de desarrollo.
- Resultados: 1214 pruebas OK en el equipo (`EVENTOSNOVA_REQUIERE_BD=1`) y 1214 OK en Docker; dev en 0004; API sana (`/ready`).
- **Siguiente paso:** Etapa 4 (trazabilidad de las operaciones HTTP).

## Etapa 4: trazabilidad de las operaciones HTTP (2026-10-24)
- Generador ampliado: clasificación por ruta (Negocio / Técnica / Sin respaldo), respaldo directo (US · CA) para las 18 rutas sin fila en la matriz, con comprobación automática de que cada identificador citado existe en las User Stories o el cierre; el generador falla si una ruta queda sin clasificar. 3 rutas técnicas listadas aparte.
- Resultado (corregido en la auditoría final): 39 con fila de matriz, 18 con respaldo explícito (la de `cierre-por-falta-de-pago` de servicio adicional se respalda además en el BPMN SP-04), 3 técnicas, 0 sin respaldo.
- Matriz aprobada y cierre de alcance sin modificar; complemento en `docs/trazabilidad/complemento-trazabilidad-fase-final.md`.
- Pruebas: `test_trazabilidad_api` (6 OK).
- Pendiente (Etapa 7): tabla requisito → implementación → prueba de todas las reglas C-01…C-15.
- **Siguiente paso:** Etapa 5 (C-02).

## Etapa 5: coherencia solicitud–contrato–evento (2026-10-24)
- Fuentes revisadas: sin regla aprobada ni decisión formal posterior; no se implementó nada (sin validación, sin SQL, sin cambiar firmas).
- Hallazgo: el riesgo SÍ es alcanzable por HTTP (la documentación decía lo contrario); corregido en `esquema-relacional-postgresql.md` §13.3.
- Prueba nueva `test_riesgo_coherencia_solicitud_contrato_evento` (3 OK) documenta el comportamiento actual.
- Decisión exacta para el responsable en `docs/trazabilidad/complemento-trazabilidad-fase-final.md`.
- **Siguiente paso:** Etapa 6 (integraciones simuladas).

## Etapa 6: integraciones simuladas (2026-10-24)
- Auditoría completa en `docs/architecture/integraciones-externas.md`: verificación de pagos y notificaciones = simulación intencional (BRD y glosario: los pagos se efectúan fuera del sistema y Administración los registra); ejecución de devoluciones = parcial; disponibilidad de proveedores = simulación + funcionalidad pendiente.
- **Hallazgo funcional:** con el adaptador vacío por omisión la API no podía asignar ningún proveedor. Se añadió `ConsultaDisponibilidadDesdeArchivo` (opt-in con `EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO`, datos rotulados de demostración, `construir(disponibilidad=None)` intacto).
- **CA-098:** `POST …/devoluciones/{id}/ejecucion` acepta el `comprobante` de Administración (opcional, retrocompatible).
- Ninguna integración real fue implementada: no hay especificación, acceso ni credenciales.
- Pruebas: `test_integraciones_simuladas` (13 OK).
- **Siguiente paso:** Etapa 7 (auditoría de requisitos y reglas).

## Etapas 7 a 13 (2026-10-24)
- **Etapa 7:** `scripts/generar_auditoria_requisitos.py` → `docs/trazabilidad/auditoria-requisitos-fase-final.md` (22 requisitos BN/SE del BRD + 18 reglas del cierre; `test_auditoria_requisitos`). **Hallazgo:** GL-060/C-15 (plazos en días hábiles con límite exclusivo a las 00:00) solo se cumple en la devolución del anticipo. Se probó aplicarlo a anticipo, saldo y SE-012: rompió masivamente el oráculo histórico (`comportamiento_estado_cuenta_v8_e3c.json`, que el cierre prohíbe editar a mano) y se **revirtió** (copias propias, sin `git restore`); queda como brecha confirmada para decisión.
- **Etapa 8:** suite completa 1241 OK con `EVENTOSNOVA_REQUIERE_BD=1` (equipo; en Docker la última ejecución de esa etapa fue de 1236 pruebas, anterior a las pruebas de OpenAPI y BRD: **la afirmación «1241 en Docker» era inexacta**, corregida en la auditoría final); cobertura 98.78 % de sentencias / 95.86 % de ramas (`.coveragerc`, src/ con ramas); sin pruebas omitidas ni fallos; único aviso: deprecación de httpx en Starlette. Evidencias nuevas: `ejecucion-pruebas-fase-final-etapa7-20261024.txt`, `cobertura-fase-final-20261024.txt`.
- **Etapa 9:** `docker compose config` OK; imágenes reconstruidas; `api` sana, `worker` en marcha; un evento creado por HTTP sobrevive al reinicio del contenedor; la imagen respeta `$PORT`; la migración funciona con una URL `postgres://` (se corrigió `migraciones/env.py` y `normalizar_url`).
- **Etapa 10:** actionlint rc=0 sobre `.github/`; sin remoto ni `gh`, no es posible ejecutar GitHub Actions; pasos documentados en `docs/architecture/ci-cd-y-despliegue.md`.
- **Etapa 11:** despliegue **no realizado** (sin plataforma ni credenciales); guía de pasos manuales y verificación local equivalente en el mismo documento. No existe URL.
- **Etapa 12:** `docs/BRD.md` (exportación del .docx aprobado, `test_brd_markdown`), `docs/api/openapi.json` (`test_openapi_exportada`), ADR-006, README actualizado, `docs/entrega/` con el reporte PDF (7 páginas, revisado visualmente) y la presentación (9 diapositivas con notas), generados por `scripts/generar_entrega_pia.py`.
- **Etapa 13:** `docs/trazabilidad/auditoria-final-pia.md` con 26 requisitos de la consigna: cumplen 21 (uno con la brecha GL-060 declarada); parcial 2 (UML de clases anterior a la persistencia; repositorio sin remoto ni commits de esta fase); pendientes 3 (CI en GitHub, despliegue con URL, enlace del despliegue) y la brecha GL-060.
- **Siguiente paso (del equipo):** decidir GL-060 y la coherencia solicitud–contrato–evento; versionar los archivos nuevos; publicar, ejecutar la CI y desplegar; anotar las URL en el README.

## Implementación de E-1 a E-4 (2026-10-25)
- **E-1** (GL-060 / C-15, regla aprobada) aplicada a los seis plazos en días hábiles; **E-2, E-3, E-4** son decisiones del equipo sin aprobación formal. Detalle: `DECISIONES_E1_E4.md`. Sin migraciones.
- **Oráculo histórico** conservado (SHA-256 `d98b4cff…`) y validado con esperados derivados de las reglas: 1203 claves = 1094 solo E-1 + 67 E-1/E-3/E-4 + 2 E-1/E-3/E-4/H-10 + 40 E-1/H-10; 0 sin explicar; recuento con identificadores en `tests/evidencias/diferencias-oraculo-e1-e4-20261025.txt`. Las «1204 subpruebas» provisionales eran las 1203 claves más la aserción `afectadas == 42`.
- **Medido sin paralelismo:** equipo 1306/1306 (0 fallos, 0 errores, 0 omitidas), Docker 1306/1306, cobertura 98,82 % sentencias y 95,85 % ramas. Una ejecución con cobertura anterior fue detenida por memoria del sistema y se repitió después; un módulo terminó una vez con un fallo de segmentación al cerrar el intérprete (resultado de pruebas OK, no reproducido en tres repeticiones).
- **Entregables regenerados** con estas cifras: PDF (7 páginas; revisadas visualmente las páginas 6 y 7) y presentación (9 diapositivas con notas; **diseño sin revisión visual**).

## Actualización de servicios y pruebas de humo (2026-10-25)
- `docker compose build api worker` y `docker compose up -d --no-deps api worker`: ambos contenedores se recrearon con el código actual (comprobado dentro de los contenedores) y están sanos; sin migraciones, sin tocar la base, el volumen ni `.env`. `/ready` (`persistencia: postgresql`), `/health` y `/docs` responden 200; Alembic en 0004; los datos de desarrollo no cambiaron (2 eventos, 1 propuesta).
- `migrate` (contenedor de una sola ejecución, terminado) conserva una referencia a una imagen que ya no existe; la imagen vigente `eventosnova-app:local` contiene migraciones idénticas a las del proyecto (huella igual). No se recreó para no ejecutar Alembic sobre la base de desarrollo; el siguiente `docker compose up` lo recreará (un `upgrade head` en 0004 no cambia nada).
- Pruebas de humo por HTTP contra una API temporal de la misma imagen y una base temporal (ya eliminada): E-2/E-3/E-4 15 de 15; E-1 (anticipo, seguimiento, saldo y límite de la sustitución) 7 de 7; Outbox sin duplicados (10 pagos verificados = 10 eventos `PagoVerificado`, todo procesado, 0 intentos de reintento, 0 devoluciones). Evidencias: `tests/evidencias/humo-api-*-20261025.txt`.
- Reintentos del Outbox y concurrencia: `test_persistencia_outbox` (27), `test_etapa9_transacciones_y_reacciones` (10), `test_concurrencia_optimista` (14), `test_migraciones_ciclo` (5), `test_persistencia_composicion` (25): OK. La devolución SE-012 se verifica en `test_h09_plazo_devolucion` (20 OK) y en `test_plazos_dias_habiles_gl060_e1`.

## Revisión funcional y visual posterior (2026-10-25)
- **Límite exacto de E-1 (aclarado, sin defecto):** firma jueves 01/10/2026 10:00 (fechas sin zona horaria: la API exige `NaiveDatetime` y devuelve 422 si recibe `Z` o un desfase). Los tres días hábiles son vie 02, lun 05 y mar 06; el límite exclusivo es el miércoles 07/10/2026 **00:00:00**. El seguimiento `2026-10-06T23:59:59` (martes, último segundo del plazo) se rechaza porque el plazo aún no venció (CA-020) y `2026-10-07T00:00:00` (miércoles) se acepta; también `00:00:01`. Comprobado con el calendario independiente, el código y HTTP. No hay inversión.
- **`migrate`:** `docker compose config` válido. Se ejecutó el servicio `migrate` (imagen vigente) contra una base aislada `eventosnova_migrate_aislada_test` (ya eliminada): 0001→0004 y segundo `upgrade head` sin cambios (`tests/evidencias/migrate-servicio-base-aislada-20261025.txt`). El contenedor `migrate` antiguo (imagen inexistente) se eliminó y se recreó sin ejecutarlo (`docker compose create --no-recreate migrate`): ahora usa `eventosnova-app:local`. La base de desarrollo sigue en 0004 y no se ejecutó Alembic sobre ella.
- **Presentación:** abierta en PowerPoint (automatización COM, sobre una copia) y exportadas las 9 diapositivas a imagen; revisadas una por una: sin texto cortado ni desbordado. El diseño es sobrio (fondo blanco, solo texto y sin imágenes).
- **Diagrama del pago:** la etiqueta de la flecha a «Importe incorrecto» describía el comportamiento anterior; se corrigió (ver `DECISIONES_E1_E4.md`). `mapa-dominio.pdf` no se pudo regenerar (sin draw.io).

## Verificación final de entregables (2026-10-25)
- `mapa-dominio.pdf`: **no actualizado en el repositorio.** Fecha 24/10/2026 00:03, SHA-256 `75b0d7b9…`, idéntico al del respaldo `Eventosnova_RESPALDO_ANTES_POSTGRESQL_20261024`; su texto aún contiene «anticipo inferior al 30 %: se solicita…» y no la etiqueta nueva. El `.drawio` es de las 19:23 del 25/10. No hay otro PDF más reciente en el equipo. Pendiente: guardar el PDF exportado en `diagramas/dominio/mapa-dominio.pdf` y volver a comprobarlo.
- Cifras: el PDF de entrega y la presentación solo contienen 1306, 98,82 %, 95,85 %, 5379/5443; README y `DECISIONES_E1_E4.md` ahora las citan; las cifras antiguas solo aparecen en secciones históricas fechadas de este archivo y de `CIERRE_AUDITORIA_FINAL.md`.
- `migrate`: contenedor creado con la imagen vigente; `docker compose --dry-run up --no-start migrate` no propone recrearlo; `docker compose config` válido; Alembic 0004 en desarrollo (lectura).
- Hashes: cierre `b67d2f47…` = `MANIFIESTO_SHA256.txt`; oráculo `d98b4cff85db0aa9…` = el registrado; `.env` ignorado por Git, no modificado (último cambio 24/10/2026 11:42, sin hash registrado).

## Auditoría final (2026-10-24)
Ver `docs/architecture/CIERRE_AUDITORIA_FINAL.md` (tabla de auditoría, resultados técnicos, decisiones pendientes y dictamen).

## Validación manual en Swagger y cierre documental (2026-10-28)
- Entorno aislado `docker-compose.manual-test.yml` (API en 8001, base `eventosnova_manual_test`, Alembic 0004, trabajador propio); el entorno de desarrollo (8000) no se tocó.
- Resultados de T-14 a T-24 y su clasificación (aprobada / con desviación / precondiciones incompletas): sección I de `CIERRE_AUDITORIA_FINAL.md`. Guía y plantilla de bitácora: `docs/pruebas-manuales/GUIA_PRUEBAS_MANUALES_T14_T24.md`.
- La discrepancia de `GET /solicitudes?evento_id=` se debió a un identificador mal copiado, no a un defecto.
- README: migraciones hasta 0004, E-2 ya implementada, sección 12 (entorno manual), estructura con ADR-005/006 y la guía.
- **Mapa de dominio (28/10/2026):** `diagramas/dominio/mapa-dominio.pdf` regenerado desde el `.drawio` del 25/10 (sustituye al PDF del 24/10 que se registró como no actualizado); procedimiento, límites (fuente Inter sustituida) y revisión visual en `diagramas/LEEME_EXPORTACIONES.txt`. Comprobación contra el código: las 47 clases del mapa existen en `src/domain`, los 7 agregados y los 31 Domain Events del código aparecen en el mapa. Pendiente: `secuencia_1` (PlantUML) conserva la rama anterior a E-3/E-4.
- **ADR-007** añadido (decisiones E-1 a E-4). PDF y presentación de entrega **no** regenerados (faltan `reportlab`/`python-pptx` en este equipo): ver la sección I de `CIERRE_AUDITORIA_FINAL.md`.
- **secuencia_1 (28/10/2026):** corregida según E-3/E-4 (comprobante repetido, pago parcial, adicional con el anticipo liquidado) y exportaciones PNG/PDF regeneradas; resuelve el pendiente anotado más arriba.
- **Etapa 2 (28/10/2026, tarde):** concordancia código↔documentación (defectos D-1 a D-3, CIERRE §J), traspaso web (§K), estado de entregables (§L); guía de T-23 corregida (saldo = 3 días hábiles antes del evento; solo ejecutable de domingo a martes UTC); auditoría de requisitos regenerada; PDF/PPTX regenerados y revisados; bitácora de IA integrada.
- **D-1 corregido (28/10/2026):** cambio en `GestionServiciosAdicionalesService.registrar_solicitud_servicio_adicional` y 26 pruebas de regresión nuevas (sección M.1 de CIERRE); D-2 y D-3 analizados sin cambios (M.2, M.3). La etapa 2 sigue abierta.
- **D-2 y D-3 (28/10/2026, diagnóstico ampliado):** reglas por obligación, contradicciones y lagunas, plan de corrección con pruebas y documentos afectados, y plan de entrega (CIERRE §N). Hallazgo nuevo D-3b: se acepta confirmar la contratación después de T (CA-110/GL-032). Sin cambios de código.
- **D-2 y D-3 corregidos (29/10/2026, UTC):** 1387 pruebas OK en el equipo y en Docker, cobertura 98,82 % / 95,77 %, imágenes reconstruidas y verificadas en los cuatro contenedores, ADR-008, guía de T-21/T-23/T-24 (sección 12) y `scripts/preparar_pruebas_manuales.py`; T-21, T-23 y T-24 pendientes de ejecución por el equipo (CIERRE §O).
- **Verificación previa a T-21/T-23/T-24 (28/10/2026):** D-2 ahora bloquea por vencimiento de hecho (`saldo_vencido_en`) y API, trabajador y Outbox usan `reloj_negocio` (America/Mexico_City, TP-06); 1415 pruebas OK en el equipo; las imágenes en marcha son anteriores y deben reconstruirse antes de las pruebas manuales (CIERRE §P, guía 12.0 bis).
- **Cierre documental (29/10/2026):** resultados de T-21, T-23 y T-24 con el código corregido (satisfactorios según el equipo; eventos `EV-157c1d85-…`, `EV-c5ac61cc-…` y `EV-c0595c85-…`) y última ejecución registrada de la suite (1415 pruebas en Docker con cobertura 98,82 % / 95,77 %, `tests/evidencias/ejecucion-docker-final-20261028-202102.txt`); documentos, matriz, mapa de dominio, UML, BPMN SP-02/maestro, informe, bitácora, reporte final y presentación alineados con el código, sin cambios de código ni de pruebas (CIERRE §Q).
