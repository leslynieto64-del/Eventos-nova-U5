# Decisiones sobre proveedores (pendientes de aprobación del equipo)

Estas decisiones las tomó el equipo de desarrollo para poder operar; **ninguna tiene aprobación externa** ni respaldo explícito en el BRD, las User Stories o el cierre de alcance. No se presentan como resueltas.

## Qué está implementado hoy (29/10/2026)
- **Fuente de los candidatos:** la asignación inicial de un proveedor a un servicio contratado (`GET …/servicios/{id}/disponibilidad`, `POST …/servicios/{id}/proveedor`) usa **solo el catálogo registrado en PostgreSQL** (`proveedor`): son candidatos los proveedores cuyos servicios incluyen el del evento (sin distinguir mayúsculas ni acentos). No se crean registros automáticamente; con el catálogo vacío la lista es vacía y la interfaz indica que primero hay que registrar un proveedor.
- **Los identificadores `PV-DEMO-*`** (archivo `src/infrastructure/datos_demo/disponibilidad_demo.json`) **no son candidatos operativos**: la fuente cargada del entorno está marcada como demostración y la asignación la ignora. El entorno de pruebas manuales ya no la activa. Las pruebas automatizadas pueden inyectarla explícitamente.
- **Validaciones de la asignación (en el servicio, aunque se llame al endpoint directamente):** evento En organización (si no, rechazo con ese motivo); proveedor registrado en el catálogo («no está registrado en el catálogo de proveedores»); que ofrezca el servicio («no ofrece el servicio …»). Todo rechazo es HTTP 422 y no cambia el estado del servicio. Una asignación válida deja el servicio «Pendiente de confirmación del proveedor»; solo la respuesta del proveedor lo confirma.

## D-P1 · Catálogo de proveedores
El BRD pide conocer los proveedores asignados (BN-004) pero ninguna historia aprobada describe su alta ni su consulta. Se implementó un registro mínimo (nombre obligatorio, servicios que ofrece, contacto; nombre único sin distinguir mayúsculas ni acentos). Sin tarifas, condiciones ni baja/edición. **Requiere aprobación.**

## D-P2 · Significado de «disponible»
El catálogo **no tiene calendario de disponibilidad**. Hoy «disponible» significa «está registrado y ofrece el servicio»; **no se comprueba la fecha del evento** ni si el proveedor ya está comprometido ese día. Esto **no está resuelto**: CA-029 habla de disponibilidad para la fecha. Opciones para el equipo: (a) aceptar la simplificación; (b) añadir un calendario o un registro de compromisos por proveedor y fecha; (c) integrar una fuente externa. Hasta que se decida, no se inventan fechas ni calendarios.

## D-P3 · Cambios, servicios adicionales y sustituciones sin fuente de costo
Esos flujos necesitan costo y condiciones del proveedor (BN-003, CA-075), datos que el catálogo no tiene y que no se inventan. Con la fuente de demostración retirada del entorno manual, «Evaluar disponibilidad» de un servicio adicional o de una sustitución no encuentra proveedores. La fuente de demostración puede reactivarse expresamente (`EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO`) solo para pruebas aisladas. **El equipo debe decidir de dónde saldrán el costo y las condiciones** (por ejemplo, ampliar el catálogo con tarifas aprobadas).
