"""Persistencia con PostgreSQL (SQLAlchemy Core, sin ORM): mapeadores, repositorios SQL, unidad de trabajo y Outbox.

Los repositorios en memoria (`infrastructure.repositorios_memoria`) y `infrastructure.composicion.construir` se conservan
sin cambios; este paquete es una alternativa independiente que implementa las mismas interfaces de `application.puertos`."""
