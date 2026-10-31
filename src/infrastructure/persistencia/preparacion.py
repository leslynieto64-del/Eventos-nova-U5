"""Preparación de la base de datos de PRUEBAS, separada de la de desarrollo.

- `asegurar_base_de_pruebas`: crea la base SOLO si no existe (nunca la borra ni la recrea) y le aplica las migraciones.
- `limpiar_base_de_pruebas`: vacía las tablas de aplicación entre pruebas. Se niega a actuar salvo que la base sea local y su
  nombre termine en `_test`; nunca toca la base de desarrollo.
- `aplicar_migraciones`: `alembic upgrade head` sobre la URL indicada (las migraciones se ejecutan con la URL pasada, sin
  alterar de forma permanente el entorno).
Ninguna función imprime ni devuelve la contraseña."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict
import sqlalchemy as sa
from . import configuracion as C
from .conexion import crear_motor
from .errores import EsquemaDesactualizado, ErrorDePersistencia
from ..esquema_postgresql import metadata


def _sin_dialecto(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _exigir_base_de_pruebas(url: str) -> None:
    if not C.es_base_local_de_pruebas(url):
        raise ErrorDePersistencia(f"Operación rechazada: {C.descripcion_segura(url)} no es una base local de pruebas "
                                  "(el nombre debe terminar en «_test»).")


def _alembic(url: str, accion, destino: str) -> None:
    from alembic import command
    from alembic.config import Config
    anterior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = C.normalizar_url(url)         # env.py toma la URL de este entorno
    try:
        cfg = Config(str(C.RAIZ_PROYECTO / "alembic.ini"))
        cfg.set_main_option("script_location", str(C.RAIZ_PROYECTO / "migraciones"))
        cfg.set_main_option("prepend_sys_path", str(C.RAIZ_PROYECTO / "src"))
        getattr(command, accion)(cfg, destino)
    finally:
        if anterior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = anterior


def aplicar_migraciones(url: str, destino: str = "head") -> None:
    _alembic(url, "upgrade", destino)


def revertir_migraciones(url: str, destino: str) -> None:
    """`alembic downgrade` SOLO sobre una base local de pruebas desechable (nombre terminado en `_test`); nunca sobre desarrollo."""
    _exigir_base_de_pruebas(url)
    _alembic(url, "downgrade", destino)


def asegurar_base_de_pruebas(url: str) -> Dict[str, object]:
    """Crea la base de pruebas si no existe y migra a `head`. Devuelve un resumen sin credenciales."""
    import psycopg
    from psycopg import sql
    _exigir_base_de_pruebas(url)
    destino = C.descripcion_segura(url)
    admin = _sin_dialecto(C.url_con_base(url, "postgres"))
    with psycopg.connect(admin, autocommit=True, connect_timeout=5) as con:
        existia = con.execute("select 1 from pg_database where datname = %s", [destino["base"]]).fetchone() is not None
        if not existia:
            con.execute(sql.SQL("create database {}").format(sql.Identifier(str(destino["base"]))))
    aplicar_migraciones(url)
    return {**destino, "creada": not existia}


def revision_actual(motor: sa.Engine) -> str:
    with motor.connect() as con:
        if not sa.inspect(con).has_table("alembic_version"):
            return ""
        return con.execute(sa.text("select version_num from alembic_version")).scalar() or ""


def exigir_esquema_al_dia(motor: sa.Engine) -> None:
    """Arranque de la aplicación: la base debe tener aplicada la última revisión de Alembic (no migra por su cuenta)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(C.RAIZ_PROYECTO / "alembic.ini"))
    cfg.set_main_option("script_location", str(C.RAIZ_PROYECTO / "migraciones"))
    esperada = ScriptDirectory.from_config(cfg).get_current_head()
    actual = revision_actual(motor)
    if actual != esperada:
        raise EsquemaDesactualizado(f"La base de datos está en la revisión «{actual or 'ninguna'}» y se necesita «{esperada}». "
                                    "Aplique las migraciones: python -m alembic upgrade head")


def limpiar_base_de_pruebas(motor: sa.Engine) -> None:
    """TRUNCATE de las tablas de aplicación (no de `alembic_version`) de una base de pruebas local."""
    _exigir_base_de_pruebas(motor.url.render_as_string(hide_password=False))
    with motor.begin() as con:
        existentes = set(sa.inspect(con).get_table_names())          # una base en una revisión anterior aún no tiene las tablas nuevas
        tablas = ", ".join(f'"{t.name}"' for t in metadata.sorted_tables if t.name in existentes)
        if not tablas:
            return
        con.execute(sa.text(f"TRUNCATE TABLE {tablas} RESTART IDENTITY CASCADE"))
