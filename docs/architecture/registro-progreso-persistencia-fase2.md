# Registro de progreso: persistencia con PostgreSQL (Fase 2)

Este archivo permite retomar el trabajo si se interrumpe, sin repetir etapas. Se actualiza al terminar cada etapa. Las evidencias de cada ejecución se guardan en `tests/evidencias/` con nombres únicos.

**Decisiones vigentes**
- TP-01: resuelta por el equipo (`resolucion-tp01.md`). PostgreSQL 18 fue elegido por el equipo.
- D-01: se mantienen las claves foráneas actuales; sin nuevas relaciones entre raíces. Las referencias sin FK se comprueban en la capa de aplicación (`esquema-relacional-postgresql.md`, 13.1).
- Coherencia solicitud–contrato–evento: **no** se impone (sin regla aprobada); riesgo documentado en 13.3.
- Importes `NUMERIC` sin precisión ni escala; invitados `BIGINT` con límite técnico 9223372036854775807.
- Los repositorios en memoria y `construir(disponibilidad=None)` se conservan.

| Etapa | Contenido | Estado |
|---|---|---|
| 0 | Línea base y respaldo | Completada |
| 1 | Documentación de decisiones | Completada |
| 2 | Aplicar la migración en desarrollo | Completada |
| 3 | Mapeadores y rehidratación | Completada |
| 4 | Repositorios SQL | Completada |
| 5 | Unidad de trabajo persistente | Completada |
| 6 | Outbox persistente | Completada |
| 7 | Composición persistente y API | Completada |
| 8 | Pruebas de integración aisladas | Completada |
| 9 | Docker Compose completo | Completada |
| 10 | CI/CD y calidad | Completada |
| 11 | Documentación final | Completada |
| 12 | Auditoría final | Completada |

## Etapa 0: estado inicial y línea base (2026-10-24)
- Carpeta de trabajo: `C:\Users\YAZMIN\Downloads\5to semeste\CLNEG\Eventosnova`. Respaldo `Eventosnova_RESPALDO_ANTES_POSTGRESQL_20261024` presente.
- Git inicial: 104 entradas (idéntico al cierre del incremento 2.4); listado guardado fuera del repositorio (`%TEMP%\git_status_inicial_fase2_impl.txt`).
- Línea base real: **906 pruebas, 906 aprobadas, 0 fallidas**. Un aviso previo (Starlette: `httpx` en `TestClient`). El informe del incremento 2.4 mencionaba 889 en una parte; el valor correcto es 906 (889 + 17).
- Evidencia: `tests/evidencias/ejecucion-pruebas-fase2-impl-etapa0-20261024.txt`.
- No existen `.github/` ni `Dockerfile` en el repositorio.

## Etapa 1: documentación de decisiones
- Creada `docs/architecture/resolucion-tp01.md` (nota complementaria; el cierre de alcance no se modifica).
- README: referencias de TP-01 y de persistencia actualizadas conservando la condición histórica.
- ADR-005: relación con TP-01 actualizada; el motor se mantiene como decisión del equipo.
- `esquema-relacional-postgresql.md`: cabecera, C-01, sección 11 y 13.1 (D-01 como decisión operativa y límites de las referencias sin FK).

## Etapa 2: migración aplicada en desarrollo
- Antes de escribir se verificó el destino sin imprimir secretos: host `127.0.0.1`, puerto `5432`, base `eventosnova` (la del Compose); único contenedor `eventosnova-db` (`postgres:18`, puerto publicado solo en loopback); `system_identifier` idéntico por la URL y por el contenedor; 0 tablas y sin `alembic_version`.
- Comando: `.\.venv\Scripts\python.exe -m alembic upgrade head` (código 0). `alembic current` = `0001 (head)`.
- Resultado (solo lectura): 22 tablas; 25 claves foráneas, 61 `CHECK`, 14 `UNIQUE` y 12 índices; `compare_metadata` de Alembic **sin diferencias**; `fk_propuesta_version_vigente` diferida; invitados `BIGINT`; importes `NUMERIC` sin escala; `outbox_evento.secuencia` identidad; tablas vacías.
- Evidencia: `tests/evidencias/migracion-0001-aplicada-desarrollo-20261024.txt`.
- El `downgrade` NO se ejecutó sobre desarrollo; se probará solo en una base de pruebas desechable (Etapa 8).

## Etapa 3: mapeadores y rehidratación
- Nuevo paquete `src/infrastructure/persistencia/` con `mapeadores.py` (SQLAlchemy Core, sin ORM): un mapeador por cada una de las siete raíces (`a_filas` / `desde_filas`).
- Rehidratación con `__new__` + `AggregateRoot.__init__` (lista de eventos vacía): no se ejecutan los constructores, así que no hay eventos fantasma. El estado privado (`_operaciones_aplicadas`, `_ventana_resuelta`, `_cierres_sin_realizar`, `_estado_antes_de_detener`) se persiste y se restaura.
- Pruebas: `tests/test_persistencia_mapeadores.py` (28) y escenarios en `tests/apoyo_persistencia.py` (construidos solo con métodos reales del dominio). Suite completa: **934 pruebas, todas `OK`**.

## Etapa 4: repositorios SQL
- `persistencia/repositorios_sql.py`: un repositorio SQL por cada puerto (`I*Repository`), con *upsert* por clave primaria (nunca «borrar y reinsertar»), sin métodos de borrado. `guardar` no extrae los eventos del agregado.
- `persistencia/conexion.py` (`AlmacenSQL`: transacción por hilo, traducción de errores), `configuracion.py` (variables de entorno, sin imprimir secretos), `errores.py`, `preparacion.py` (base de pruebas).
- **Base de pruebas** `eventosnova_test`: creada solo porque no existía (script idempotente `scripts/preparar_base_de_pruebas.py`, que no borra nada y se niega a actuar si la base no es local y terminada en `_test`). La de desarrollo no se toca.
- Pruebas de contrato sobre el adaptador en memoria **y** el SQL (`tests/test_persistencia_repositorios.py`, 36) y de referencias sin FK (`tests/test_persistencia_referencias.py`, 14).
- Referencias sin FK: se añadieron comprobaciones de existencia en `application/servicios.py` (`aplicar_cierre_sin_realizar` exige que exista la solicitud de origen; las reacciones de obligaciones exigen contrato/evento/estado de cuenta). No se alteró ningún caso válido.
- Incidente: una ejecución del módulo tardó 572 s por un bloqueo de conexión que no se reprodujo; se añadió `connect_timeout=10` y se confirmó el módulo en ~10 s.

## Etapa 5: unidad de trabajo persistente
- `persistencia/unidad_trabajo_sql.py` (`UnitOfWorkSQL`, compatible con `IUnitOfWork`): una operación = una transacción; sin anidamiento (ningún servicio lo usa: comprobado en 7 885 transacciones de la suite); eventos al Outbox en la misma transacción; recursos liberados siempre; estado por hilo.
- Pruebas: `tests/test_persistencia_unidad_trabajo.py` (18): confirmación, reversión, excepciones, restricciones inmediatas y diferidas, atomicidad, cierre de conexiones, aislamiento entre hilos.

## Etapa 6: Outbox persistente
- Inventario real: **31 tipos de evento** (no se asumió un número). `persistencia/codec_eventos.py`: registro explícito + prueba de que coincide con el dominio; JSONB versionado (`{"version": 1, "campos": ...}`) con etiquetas para `datetime`, `Decimal`, tuplas, enumeraciones y objetos de valor; errores controlados (`EventoNoRehidratable`).
- `persistencia/outbox_sql.py`: registro en la misma transacción; `PublicadorEstable` (claves `módulo.Clase.método`, ya no `__qualname__#índice`); `DespachadorOutboxSQL` con reclamo `FOR NO KEY UPDATE SKIP LOCKED`, reacción anotada en `outbox_reaccion` en transacción propia, reintentos hasta `max_intentos` y paso a REVISION con el motivo; `reabrir` manual.
- Pruebas: `test_persistencia_codec_eventos.py` (15) y `test_persistencia_outbox.py` (27): idempotencia, fallo/reintento, error permanente, caída del trabajador, reinicio, dos trabajadores concurrentes (ambos procesan; nadie repite), eventos no rehidratables.
- Límite documentado: ejecutar la reacción y anotarla son dos transacciones; una caída entre ambas repite la reacción (por eso ADR-004 exige reacciones idempotentes).

## Etapa 7: composición persistente y API
- `infrastructure/composicion.py`: el cableado se extrajo a `ensamblar()`; `construir(disponibilidad=None)` conserva su firma y su comportamiento (las 906 pruebas previas siguen en verde). Nueva `persistencia/composicion_persistente.py` (`construir_persistente`): comprueba conexión y que las migraciones estén al día; misma estructura que `construir` más `almacen`, `outbox`, `modo`, `comprobar_base_de_datos()` y `cerrar()`.
- API: `EVENTOSNOVA_PERSISTENCIA=postgresql` elige la composición persistente (por omisión, memoria); arranque que falla si no hay base de datos o falta migrar; `GET /ready`; cierre ordenado del pool; manejadores HTTP específicos de persistencia (409 integridad, 422 dato no almacenable, 503 base no disponible, 500 error de persistencia) sin filtrar nombres de restricciones ni mensajes internos. Solo `main.py` importa infraestructura.
- Rutas nuevas (47 POST y 10 GET): propuestas/contratación, pagos y estados de cuenta, ciclo de vida del evento y proveedores, cambios, servicios adicionales, sustituciones y las 9 consultas CQRS. Cada ruta llama a **un** servicio de aplicación; no se inventó ninguna regla. Despacho en línea del Outbox tras cada comando (`EVENTOSNOVA_DESPACHO_EN_LINEA=0` lo desactiva) y trabajador independiente (`persistencia/trabajador_outbox.py`).
- **Hallazgo y corrección:** las pruebas HTTP sobre PostgreSQL revelaron que `sustitucion_proveedor.proveedor_original_id` era `NOT NULL` pero el dominio admite `None` (servicio sin proveedor asignado). Se corrigió con una **nueva** revisión `0002` (la `0001` ya estaba aplicada); aplicada a desarrollo y probada.
- Pruebas: `test_persistencia_composicion` (25), `test_api_operaciones` (32: 16 flujos × memoria/PostgreSQL), `test_api_persistencia` (14). Mismos resultados observables en memoria y en PostgreSQL.

## Etapa 8: pruebas de integración aisladas
- Bases separadas: desarrollo `eventosnova`; integración `eventosnova_test`; ciclo de migraciones `eventosnova_migraciones_test` (desechable, creada porque no existía). Todas locales; las dos de pruebas terminan en `_test`.
- `limpiar_base_de_pruebas` y `revertir_migraciones` se niegan a actuar si la base no es local y de nombre `*_test`; probado con dobles. Entre pruebas solo se vacían las tablas de `eventosnova_test`.
- `downgrade` probado únicamente en la base desechable: 0002 → 0001 → base → head; y la bajada de la 0002 se rechaza sin modificar nada si existen sustituciones sin proveedor original.
- Si PostgreSQL no está disponible las pruebas se omiten con mensaje explícito; con `EVENTOSNOVA_REQUIERE_BD=1` (CI/Compose) son un fallo.

## Etapa 9: Docker Compose completo
`Dockerfile` (objetivos `app` y `tests`), `.dockerignore` (excluye `.env`), servicios `migrate`, `api` (127.0.0.1:8000, healthcheck `/ready`), `worker` y `tests` (perfil `tests`); el servicio `db` y su volumen no se modificaron. Verificado: `docker compose config --quiet`, API sana en modo PostgreSQL, datos conservados tras reiniciar el contenedor `api`.

## Etapa 10: CI/CD y calidad
`.github/workflows/ci.yml` y `publicar-imagen.yml` (validados con actionlint; **no ejecutados en GitHub**). `scripts/verificar_cobertura.py` (mínimo 80 % de sentencias).

## Etapa 11: documentación final
README, ADR-005, `esquema-relacional-postgresql.md` (sección 14, D-10 a D-13) y `trazabilidad-api-persistencia.md` (generado y verificado por prueba).

## Etapa 12: auditoría final (2026-10-24)
- Suite completa: **1159 pruebas OK** en el equipo y en Docker (`docker compose run --rm tests`). Evidencia: `tests/evidencias/ejecucion-pruebas-fase2-impl-final-20261024.txt`.
- Cobertura: 98,4 % total (sentencias 98,8 %, ramas 96,02 %); evidencia `cobertura-fase2-impl-final-20261024.txt`.
- Alembic: un solo head (`0002`); SQL fuera de línea de subida y bajada generado; base de desarrollo en `0002` con 1 evento y 1 propuesta de demostración.
- Cierre de alcance sin modificar; sin commits ni pushes; `.env` no tocado.
