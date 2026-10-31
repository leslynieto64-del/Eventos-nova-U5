# Auditoría de integraciones externas (fase final, Etapa 6)

Ninguna integración externa es real. Este documento clasifica cada una, indica su base documental y qué haría falta para volverla real. No se inventaron credenciales ni se presentó ninguna simulación como si fuera una integración.

| Integración | Puerto (`application/puertos.py`) | Adaptador actual | Clasificación | Base documental | Para hacerla real |
|---|---|---|---|---|---|
| Verificación de pagos | `IVerificadorPagos` | `VerificadorPagosSimulado` (verdadero si hay comprobante) | **Simulación intencional** | BRD: «Realizar los pagos por parte del Cliente» está fuera del alcance; glosario: «Los pagos se efectúan fuera del sistema y Administración los registra manualmente» | Especificación de un banco o pasarela, credenciales y formato de comprobante. Hoy la verificación es un acto de Administración, que el sistema solo registra |
| Ejecución de devoluciones | `IEjecutorDevoluciones` | `EjecutorDevolucionesSimulado` (comprobante `COMP-<id>`, idempotente por referencia) | **Implementación parcial** | CA-098: Administración efectúa la devolución y el sistema registra concepto, importe, motivo, fecha y comprobante | **Hecho en esta etapa:** `POST …/devoluciones/{id}/ejecucion` acepta el `comprobante` que entrega Administración y lo registra; sin él se usa el ejecutor simulado. Una transferencia real requeriría una pasarela especificada |
| Notificaciones | `INotificadorParticipantes` | `NotificadorEnMemoria` (lista de avisos en memoria del proceso) | **Simulación intencional** | BRD: hoy se usa WhatsApp, llamadas y correo; el sistema debe registrar y comunicar (US-027, CA-087) pero no define canal ni proveedor | Elegir canal (correo, mensajería), obtener credenciales y plantillas. Los avisos no persisten: se pierden al reiniciar el proceso |
| Disponibilidad de proveedores | `IConsultaDisponibilidadProveedor` | `ConsultaDisponibilidadSimulada` (vacía por omisión) o `ConsultaDisponibilidadDesdeArchivo` (opt-in) | **Simulación intencional + funcionalidad pendiente** | US-013, US-014, CA-029 a CA-031: el Coordinador consulta la disponibilidad y asigna; no se especifica la fuente | Una fuente de datos de proveedores (catálogo, calendario o API). **Hallazgo:** con el adaptador vacío, `asignar_proveedor` siempre rechaza («el proveedor no figura disponible»), de modo que sin configuración la API no puede asignar proveedores |

## Simulación configurable de la disponibilidad

Para poder demostrar la asignación de proveedores por HTTP existe `ConsultaDisponibilidadDesdeArchivo`: lee un JSON `{servicio: [{proveedor_id, disponible, costo?, condiciones?}]}`. Se activa con la variable de entorno `EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO`. El archivo de ejemplo `src/infrastructure/datos_demo/disponibilidad_demo.json` está rotulado como **datos de demostración** (no proviene de ningún sistema de proveedores). No usa la fecha del evento ni los proveedores actuales: es una demostración, no un calendario. Un archivo inexistente hace fallar el arranque (no se ignora).

**Desde el 29/10/2026 esta fuente NO participa en la asignación inicial de proveedores:** `GET …/servicios/{id}/disponibilidad` y `POST …/servicios/{id}/proveedor` consultan únicamente el **catálogo de proveedores registrado en la base de datos** (los que ofrecen el servicio; ver `docs/architecture/DECISIONES_PROVEEDORES.md`), de modo que los identificadores `PV-DEMO-*` nunca son candidatos operativos. La fuente de demostración solo se usa, si se activa expresamente, en los flujos que necesitan costo y condiciones del proveedor (cambios, servicios adicionales y sustituciones). Las pruebas automatizadas la inyectan de forma explícita como fixture. El entorno de pruebas manuales (`docker-compose.manual-test.yml`) ya no la activa.

Está desactivada por omisión: sin la variable, el sistema se comporta como antes. Para activarla en Docker Compose, defina `EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO=/app/src/infrastructure/datos_demo/disponibilidad_demo.json` en el entorno de la API (véase `.env.example`).

## Pruebas

`tests/test_integraciones_simuladas.py` (13): los adaptadores son simulados, la verificación solo exige comprobante, el ejecutor es idempotente, el notificador solo registra en memoria, la simulación configurable se carga y se rotula, asigna proveedores cuando hay datos y no asigna ninguno cuando no los hay, y la devolución registra el comprobante de Administración (o usa el simulado).

## Pendientes externos

Elegir la plataforma y credenciales de notificación; decidir si habrá una pasarela de pagos o si Administración seguirá registrando manualmente (lo que indican BRD y glosario); proveer una fuente real de disponibilidad de proveedores.
