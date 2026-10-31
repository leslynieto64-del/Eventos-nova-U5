# Pruebas manuales y limpieza de datos de prueba (base manual)

Fecha de la limpieza: **29/10/2026**. Base: **`eventosnova_manual_test`** (API manual en el puerto 8001, migración `0005`). No se tocaron las bases `eventosnova` (desarrollo, migración `0004`, 2 eventos), `eventosnova_test` (pruebas automatizadas) ni `eventosnova_migraciones_test`.

## 1. Destino verificado antes de actuar
- Los contenedores `eventosnova-api-manual` y `eventosnova-worker-manual` apuntan a `…@db:5432/eventosnova_manual_test` (contraseña no mostrada).
- El script consultó `current_database()` = `eventosnova_manual_test` y la revisión `0005` antes de leer o borrar; con cualquier otro destino se niega.
- `/ready` del puerto 8001: `postgresql` con base de datos `ok`.

## 2. Copia de seguridad
- Archivo: `backups/eventosnova_manual_test_20261029_145506.dump` (formato personalizado de `pg_dump`, 111 217 bytes) y su huella `…dump.sha256` (SHA-256 `c133c133…e2432d`).
- Está **excluida de Git** (`backups/` en `.gitignore`) y se conserva intacta.
- Validación: `pg_dump` terminó con código 0; el archivo no está vacío; `pg_restore --list` lo leyó (131 entradas, base de origen `eventosnova_manual_test`, 24 tablas con datos); `pg_restore -a -t evento` muestra 38 eventos y `-t proveedor` 11 proveedores, igual que la base en ese momento.
- No se probó una restauración completa en otra base (no se creó ninguna base nueva).
- Inventario previo: `backups/inventario_previo.json`.

## 3. Criterio para identificar datos de prueba
Script: `scripts/limpiar_datos_manuales.py` (inventario de solo lectura por omisión; para borrar exige la copia validada con su huella y la confirmación explícita de la base).

Un evento se consideró de prueba si su tipo, lugar o cliente contiene un marcador (`prueba`, `T14`/`T21`/`T23`/`T24`, `CL-UI`, `CL-PROV-UI`, `CL-PRUEBA-*`) **o** coincide exactamente con el cuerpo de ejemplo de Swagger (`CL-1`, `Boda`, `2026-11-20T18:00:00`, `Salón`, 100 invitados, `Banquete`), que solo puede venir de ejecutar el ejemplo sin cambios (`EV-5d7df250…`). Un proveedor se consideró de prueba si su nombre contiene `prueba`, o empieza por `Banquetes UI ` o `Foto UI ` (creados por los recorridos de navegador). Se borraron además todas las filas que dependen de esos eventos y las filas del Outbox de esos agregados.

Resultado: los 38 eventos y los 11 proveedores cumplieron el criterio. **No hubo registros dudosos**, por lo que no se conservó ninguno por indeterminación.

## 4. Cantidades antes y después
| Tabla | Antes | Después |
|---|---:|---:|
| evento | 38 | 0 |
| evento_servicio_contratado | 40 | 0 |
| evento_solicitud_cancelacion | 6 | 0 |
| propuesta | 28 | 0 |
| version_propuesta | 28 | 0 |
| contrato | 27 | 0 |
| estado_cuenta | 27 | 0 |
| estado_cuenta_cierre_sin_realizar | 2 | 0 |
| obligacion_pago | 53 | 0 |
| pago | 32 | 0 |
| solicitud_cambio | 6 | 0 |
| solicitud_servicio_adicional | 8 | 0 |
| outbox_evento | 134 | 0 |
| outbox_reaccion | 152 | 0 |
| proveedor | 11 | 0 |
| devolucion, contrato_anexo, contrato_seguimiento_anticipo, estado_cuenta_seguimiento_cobro, evento_operacion_aplicada, solicitud_cambio_condicion, sustitucion_alternativa, sustitucion_proveedor | 0 | 0 |

La limpieza se hizo en **una sola transacción** (solicitudes → estados de cuenta → contratos → propuestas → eventos → Outbox → proveedores), con comprobación de integridad antes de confirmar. No se usó `TRUNCATE`; el esquema, las migraciones (`0005`) y las tablas se conservan.

## 5. Eventos de las pruebas manuales T-21, T-23 y T-24 (retirados de la base activa)
Se confirmó que seguían siendo registros de prueba y se retiraron, después de la copia de seguridad:

| Prueba | Evento retirado |
|---|---|
| T-21 (cancelación) | `EV-157c1d85-2609-49ba-8ff7-2585d8780239` |
| T-23 (servicio adicional) | `EV-c5ac61cc-5ce4-412f-96df-ca109dae427a`, `EV-8e2a6f41-62f0-4717-93c7-350d2598701a` (solicitud `SA-28aff283-a4ed-4604-9a20-7601977ec5ea`) |
| T-24 (cambio tras el inicio) | `EV-c0595c85-6ce9-45cd-a45b-15996de7e26a`, `EV-2edfbcd8-8d51-4890-b51f-39c0b9c48ba1` |
| T-14 | `EV-89ab606e-6eef-42c4-9627-3142e7d89b3b`, `EV-d8d49221-301a-4a51-bde2-f4643fbbae75` |

Otros retirados: `EV-5d7df250-ea34-453d-aa7b-22098644c85c` (ejemplo de Swagger), los eventos de los recorridos de navegador (`CL-UI`, `CL-PROV-UI`) y los 11 proveedores de prueba, incluido «Proveedor de prueba UI». Observación: el identificador `EV-d8d49221-301a-4a51-bde2-f4643fbaeb75` de una lista anterior no existía; el real terminaba en `…fbbae75`.

## 6. Evidencia que se mantiene
Las guías y capturas de las pruebas (`docs/pruebas-manuales/GUIA_PRUEBAS_MANUALES_T14_T24.md` y las capturas archivadas) **no se modificaron** salvo una nota al inicio de la guía. Los identificadores que citan describen lo ejecutado el 28/10/2026 y **ya no existen en la base activa**; su contenido original está en la copia de seguridad. Los resultados de los recorridos de navegador están en `scripts/probar_interfaz_navegador.mjs` y `scripts/probar_proveedores_navegador.mjs`, que pueden repetirse (crean sus propios datos de prueba).

## 7. Verificación posterior
- Migración de la base manual: `0005`. `/ready`: `postgresql`, base `ok`. API manual `healthy` y trabajador en marcha (ambos con la imagen `eventosnova-app:proveedores`).
- Ninguno de los identificadores retirados existe; `GET /eventos` (2020–2035) devuelve 0 eventos, `/servicios-pendientes-confirmacion` 0 servicios y 0 solicitudes, `/proveedores` 0 proveedores.
- Chrome (`/app/`): panel, eventos, seguimiento, proveedores, solicitudes, pagos y sistema cargan con los contadores en 0, sin `null`, `undefined` ni códigos internos, sin excepciones de JavaScript y sin peticiones de escritura. La confirmación de «Registrar proveedor» muestra una sola línea y se canceló sin guardar.
- Desarrollo (`eventosnova`) sigue en `0004` con 2 eventos; no se modificó.

## 8. Limitaciones
- La base manual quedó vacía; el catálogo de proveedores también (no había proveedores que no fueran de prueba). Las pruebas de navegador vuelven a crear datos; tras repetirlas se puede reutilizar el mismo script de limpieza (siempre con una copia nueva).
- Los datos de demostración de disponibilidad (`PV-DEMO-*`) no están en la base: salen del archivo configurado en la API y no se tocaron.
- La restauración de la copia no se ensayó en una base aparte.
