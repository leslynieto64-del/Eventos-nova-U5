# ADR-006: Control de concurrencia optimista e identificadores UUID

- **Estado:** Aceptada (decisión técnica del equipo; fase final)
- **Fecha:** 2026-10-24
- **Relacionada con:** ADR-002 (raíces de agregado), ADR-004 (Outbox), ADR-005 (PostgreSQL)

## Contexto y problema

Con repositorios SQL, dos transacciones pueden leer el mismo agregado y guardar después, de modo que la última escritura pisa a la primera («gana la última») y se pierde una actualización, por ejemplo dos pagos simultáneos sobre el mismo `EstadoCuenta`. Además, los identificadores nuevos tenían 8 caracteres hexadecimales (32 bits) y el guardado por *upsert* habría sobrescrito un agregado ante una colisión.

## Decisión

1. **Control optimista por versión de raíz.** Cada raíz de agregado (propuesta, contrato, evento, solicitud de cambio, solicitud de servicio adicional, sustitución de proveedor y estado de cuenta) tiene una columna `version` (revisión de Alembic `0004`). El repositorio SQL guarda con `UPDATE … WHERE id = :id AND version = :leída`; un agregado nuevo se inserta con `ON CONFLICT DO NOTHING`. Si no se afecta ninguna fila lanza `ConflictoDeConcurrencia`, la operación se revierte entera (ADR-004: una transacción por agregado) y la API responde HTTP 409.
2. **Identificadores.** Los ids nuevos son prefijo + UUID v4 completo (122 bits aleatorios). Los históricos de 8 caracteres siguen siendo válidos (columnas `TEXT`). La creación de cada raíz comprueba además que el id no exista (`nuevo_id_libre`) y `EstadoCuenta` rechaza obligaciones y pagos con id repetido.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Bloqueo pesimista (`SELECT … FOR UPDATE`) en cada operación | Serializa escrituras del mismo agregado y requiere leer dentro de la transacción de escritura, que hoy abre la unidad de trabajo después de la lectura (ADR-004) |
| Nivel de aislamiento `SERIALIZABLE` | Obliga a reintentos generales en toda la aplicación |
| Mantener «gana la última» | Pierde pagos y cambios silenciosamente |
| Ids secuenciales de la base de datos | Cambiaría el formato público de los ids y acoplaría el dominio a la base |

## Consecuencias

- Solo compiten las escrituras del mismo agregado; agregados distintos no se esperan (probado).
- El cliente de la API debe releer y reintentar tras un 409; el Outbox reintenta solo las reacciones fallidas (entrega *al menos una vez* con deduplicación por clave de reacción; no se afirma «exactamente una vez»).
- La colisión de ids es estadísticamente improbable, no imposible; la clave primaria de la base de datos sigue protegiendo frente a duplicados.
- Los repositorios en memoria no usan versión (un solo proceso).
- La bajada de la revisión `0004` elimina la columna `version` (solo en bases desechables).

## Pruebas

`test_concurrencia_optimista` (hilos reales, copias obsoletas, siete raíces, reversión completa, 409 en la API, reintento del Outbox) y `test_identificadores`.
