# ADR-007: Plazos GL-060, coherencia solicitud–contrato–evento y pagos parciales del anticipo (E-1 a E-4)

- **Estado:** Aceptada por el equipo (2026-10-25). **Sin aprobación externa registrada** para E-2, E-3 y E-4 (ver abajo)
- **Fecha:** 2026-10-25
- **Relacionada con:** ADR-002 (raíces de agregado), ADR-006 (concurrencia optimista); no sustituye ni deja obsoleta ninguna decisión anterior
- **Detalle completo, pruebas y resultados medidos:** [`../architecture/DECISIONES_E1_E4.md`](../architecture/DECISIONES_E1_E4.md)

## Contexto

La auditoría final (`../architecture/CIERRE_AUDITORIA_FINAL.md`, sección E) dejó cuatro puntos en los que el comportamiento implementado no coincidía con una regla de las fuentes o no estaba definido por ellas.

## Decisión

| Id | Decisión | Respaldo en las fuentes |
|---|---|---|
| E-1 | Los seis plazos en días hábiles (anticipo, seguimiento del anticipo, saldo, límite de sustitución, devolución del anticipo y SE-012) vencen a las 00:00 del día siguiente al último día, con límite exclusivo (GL-060 / C-15). Horas y días naturales no cambian | **Sí**: glosario y cierre de alcance aprobados |
| E-2 | `POST /solicitudes-cambio`, `/solicitudes-servicio-adicional` y `/sustituciones` rechazan con HTTP 422 si el evento no es el del contrato | No: decisión de implementación |
| E-3 | El anticipo mínimo (30 %) puede alcanzarse sumando pagos parciales verificados del mismo contrato; un comprobante repetido sobre la misma obligación se rechaza | No (BN-009, H-10 y CA-021 respaldan solo la fecha efectiva del pago) |
| E-4 | Con el anticipo liquidado, un pago menor al 30 % se verifica como adicional, sin devolución ni aplicación al saldo | No para este caso exacto |

El oráculo histórico `tests/referencias/comportamiento_estado_cuenta_v8_e3c.json` **no se modificó**; sus 1203 claves se comparan con esperados derivados de las reglas.

## Alternativas consideradas

Se evaluaron las opciones ofrecidas al equipo en cada punto (por ejemplo, conservar el comportamiento anterior en E-2 a E-4); constan en `CIERRE_AUDITORIA_FINAL.md` §E. No se amplía aquí lo que no esté registrado en ese documento.

## Consecuencias

- El estado «Importe incorrecto» y su transición se conservan en el dominio solo para pagos históricos.
- E-2 a E-4 cambian reglas que las fuentes no exigen: si la responsable del proyecto las rechaza, hay que revertirlas en una tarea separada.
- La migración de Alembic no cambió (head 0004).

## Revisión del 29/10/2026 (E-3 y coherencia documental)

Motivo: la revisión documental del 29/10/2026 encontró que el glosario (GL-011), el BRD, las historias de usuario (anticipo inferior al 30 %) y el BPMN SP-02 conservaban la regla anterior de corregir un anticipo inferior al 30 %, mientras el código acumula pagos parciales (E-3). **Sin cambio de código ni de decisión:** E-3 sigue siendo una decisión del equipo sin aprobación externa. Los documentos activos conservan la redacción anterior y añaden una nota fechada (`[Revisión 29/10/2026 · E-3]`); el BPMN SP-02 dice ahora «anticipo acumulado … para que lo complete (E-3)». La matriz de trazabilidad (fila 29) ya describía E-3 y no se modificó.
