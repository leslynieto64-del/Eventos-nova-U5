# Nota complementaria: resolución de TP-01

**Fecha de registro:** 2026-10-24
**Tipo de documento:** nota complementaria. **No modifica** `Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md`, que se conserva íntegro como documento aprobado.

## 1. Condición originalmente aprobada

El cierre de alcance aprobado (sección «4. Decisiones técnicas pendientes», fila TP-01) dice:

> TP-01 · Persistencia tras reinicio · «Bloqueada hasta recibir la base de datos oficial (README)»

El README del proyecto decía, por su parte, que «la persistencia se incorporará cuando se reciba la base de datos oficial del proyecto». TP-03 («Recuperación del RLT») y TP-05 (identificador de petición de la API) están vinculadas a TP-01. Ese texto se conserva como trazabilidad histórica de la condición aprobada.

## 2. Resolución adoptada por el equipo

El equipo adoptó, para continuar con la implementación, la siguiente resolución de TP-01 (comunicada en la instrucción de trabajo de la Fase 2, implementación de persistencia, del 2026-10-24):

1. El ZIP `16_Eventos_Nova` contiene la **fuente oficial de datos** que se recibió. En el repositorio corresponde al paquete `datos/paquete_pia/` (seis CSV y `MANIFIESTO.sha256`, incorporados en la Etapa E1 y ejecutados en la F2).
2. El **equipo es responsable de construir la base de datos relacional** del sistema.
3. **PostgreSQL 18** es la tecnología elegida por el equipo.
4. Los CSV oficiales se utilizan **de acuerdo con su propósito documentado** (datos de entrada reproducibles y casos de prueba). El esquema transaccional de Eventos Nova se deriva del dominio, las reglas y la arquitectura (`docs/architecture/esquema-relacional-postgresql.md`); **no** se obtiene convirtiendo automáticamente cada CSV en una tabla.

Con esta resolución, la implementación de la persistencia deja de estar bloqueada por TP-01.

## 3. Qué afirma y qué no afirma esta nota

| Afirmación | Estado |
|---|---|
| El equipo recibió la fuente oficial de datos (`16_Eventos_Nova`) | Sí, según README (Etapa E1) y la resolución del equipo |
| El equipo construye la base de datos relacional con PostgreSQL 18 | Sí, decisión técnica del equipo (ADR-005) |
| TP-01 se considera resuelta para continuar con la implementación | Sí, por resolución del equipo |
| El profesor **impuso** PostgreSQL | **No.** El PIA no nombra ningún motor |
| El profesor **aprobó** PostgreSQL | **No consta evidencia** de esa aprobación; no se afirma |
| Se modificó el cierre de alcance aprobado | **No.** Esta nota lo complementa sin reinterpretarlo |

## 4. Qué NO cambia

- El alcance funcional aprobado y sus reglas de negocio.
- TP-02, TP-03, TP-05 y TP-06 conservan su contenido. Las que dependían de TP-01 (recuperación del RLT e identificador de petición) pasan a poder implementarse, pero cada una requiere su propio criterio aprobado: esta nota no inventa ninguno.
- Las cuestiones aún pendientes siguen identificadas en `esquema-relacional-postgresql.md` (sección 9): coherencia solicitud–contrato–evento (C-02), reglas de texto sin respaldo y esquemas de entrada HTTP no expuestos.

## 5. Trazabilidad

| Documento | Relación |
|---|---|
| `Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md` | Fuente de la condición TP-01 (sin modificar) |
| `README.md` | Actualizado para reflejar la resolución sin borrar la condición histórica |
| `docs/ADR/ADR-005-postgresql.md` | Decisión técnica del equipo sobre el motor |
| `docs/architecture/esquema-relacional-postgresql.md` | Esquema derivado del dominio |
| `docs/architecture/registro-progreso-persistencia-fase2.md` | Registro de las etapas de implementación |
