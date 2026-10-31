# ADR-005: PostgreSQL 18 como motor de persistencia

- **Estado:** Aceptada (decisión técnica del equipo)
- **Fecha:** 2026-10-24
- **Relacionada con:** ADR-001 a ADR-004 (`ADR_Eventos_Nova.docx`, sin modificar)

## Contexto y problema

Eventos Nova funciona hoy con repositorios en memoria (`src/infrastructure/repositorios_memoria.py`) y un `UnitOfWorkMemoria` con Outbox en memoria. Los datos se pierden al reiniciar la API. Se necesita persistencia real sin alterar las reglas de negocio aprobadas.

## Requisitos del PIA relacionados

Fuente: `PIA_CLN_Proyecto_Integrador_AD2026.pdf` (verificado el 2026-10-24).

- **Página 1, punto 5:** «Contenerizar la solución con Docker Compose para DB + App + Tests, separar configuración mediante variables de entorno y realizar un despliegue funcional para la demostración.»
- **Página 2, apartado PRODUCCIÓN:** «Docker Compose para DB + App + Tests en un entorno reproducible; variables de entorno para separar configuración del código (12-Factor App)…». La estructura mínima del repositorio de la misma página incluye `docker-compose.yml` y `.env.example` (sin secretos reales).

El PIA exige una base de datos (**DB**) dentro de Docker Compose junto con la aplicación y las pruebas. Las páginas 1 y 2 no emplean la palabra «persistencia» ni **nombran ningún motor de base de datos** (el documento completo tampoco menciona PostgreSQL, MySQL, SQLite ni otro). La elección de PostgreSQL es una decisión técnica del equipo; no la impuso el profesor ni consta que la haya aprobado.

**Relación con TP-01.** El cierre de alcance aprobado (`Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md`, sección 4, fila TP-01) mantenía la persistencia «bloqueada hasta recibir la base de datos oficial». El equipo resolvió esa condición el 2026-10-24: el ZIP `16_Eventos_Nova` es la fuente oficial de datos recibida y el equipo construye la base de datos relacional con PostgreSQL (ver `docs/architecture/resolucion-tp01.md`). Esta ADR registra el motor elegido por el equipo; **la elección del motor es una decisión del equipo y no consta que el profesor la haya impuesto ni aprobado**. El cierre de alcance se conserva sin modificar.

## Alternativas consideradas

| Alternativa | Ventajas | Desventajas |
|---|---|---|
| **PostgreSQL 18** | Transacciones ACID robustas, restricciones e integridad referencial, JSONB, imagen oficial, estándar de la industria, buen soporte en SQLAlchemy/Alembic | Requiere un servicio adicional (Docker) |
| SQLite | Sin servidor, muy simple | Concurrencia limitada, `ALTER TABLE` restringido, no representa un entorno DB + App + Tests en Compose |
| MySQL / MariaDB | Muy extendido, imagen oficial | Menor rigor por defecto en restricciones y tipos; sin ventaja frente a PostgreSQL para este caso |
| MongoDB | Esquema flexible, encaja con agregados | Transacciones multi-documento menos naturales; el dominio es relacional (contratos, pagos, estados de cuenta) |

## Decisión

Usar **PostgreSQL 18** (imagen `postgres:18`) como motor de persistencia, ejecutado con Docker Compose.

## Justificación

- La consistencia transaccional es crítica (pagos, saldos, Outbox junto con el agregado en la misma transacción).
- Permite modelar estados y reglas como restricciones (`CHECK`, `UNIQUE`, claves foráneas).
- Compose permite reproducir el entorno DB + App + Tests exigido por el PIA.

## Consecuencias

**Positivas:** persistencia durable; integridad garantizada por la base; entorno reproducible; Outbox transaccional posible.
**Negativas:** dependencia de Docker para desarrollo y pruebas de integración; mayor complejidad que los repositorios en memoria; hay que mantener migraciones.

## Herramientas complementarias previstas

- **SQLAlchemy Core 2.0.x** (sin ORM) para acceso a datos.
- **Alembic** para migraciones versionadas.
- **Psycopg 3** (`psycopg[binary]`) como controlador.
- Docker Compose; volumen nombrado `eventosnova_pgdata` montado en `/var/lib/postgresql` (convención de PostgreSQL 18+); puerto publicado solo en `127.0.0.1`.

## Estrategia de migración incremental

1. Dependencias, servicio PostgreSQL en Compose y variables de entorno. **Hecho.**
2. Diseño del esquema relacional de Eventos Nova y migraciones de Alembic (0001 y 0002). **Hecho.**
3. Mapeadores agregado ↔ filas y repositorios SQL que respeten las interfaces de `application/puertos.py`. **Hecho.**
4. `UnitOfWork` SQL con Outbox persistente y despachador. **Hecho** (despacho en línea y trabajador independiente).
5. Composición configurable (memoria o PostgreSQL), pruebas de integración y servicios `api`, `worker` y `tests` en Compose. **Hecho.** Estado detallado en `docs/architecture/registro-progreso-persistencia-fase2.md`.

Los repositorios en memoria se conservan durante la transición como implementación para las pruebas unitarias.

## Riesgos y cuestiones pendientes

- Conservar el comportamiento de `guardar()` / `confirmar()` / `revertir` del UoW actual con transacciones reales.
- Definir el esquema a partir del modelo de dominio de Eventos Nova, no de los CSV genéricos.
- Estrategia de bases de datos de prueba (aislamiento y limpieza).
- Gestión de secretos: `.env` local fuera de Git; `.env.example` sin valores reales.
- Compatibilidad de la suite actual (834 pruebas, 98.2 % de cobertura) al introducir persistencia.
