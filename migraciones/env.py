"""Entorno de Alembic. La URL sale de DATABASE_URL (variable de entorno o archivo .env local, nunca versionado)."""
import os
from logging.config import fileConfig
from pathlib import Path
from alembic import context
from sqlalchemy import create_engine, pool
from infrastructure.esquema_postgresql import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = metadata


def _cargar_env_local() -> None:
    """Lee .env de la raíz sin sobrescribir variables ya definidas (sin dependencias adicionales)."""
    ruta = Path(__file__).resolve().parent.parent / ".env"
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip())


def _url() -> str:
    _cargar_env_local()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Defina DATABASE_URL (vea .env.example) para ejecutar migraciones contra la base de datos.")
    from infrastructure.persistencia.configuracion import normalizar_url        # postgres:// y postgresql:// → Psycopg 3
    return normalizar_url(url)


def run_migrations_offline() -> None:
    """Modo --sql: genera el SQL sin conectarse; no necesita DATABASE_URL."""
    context.configure(dialect_name="postgresql", target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
