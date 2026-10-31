"""Configuración de la persistencia a partir de variables de entorno (nunca credenciales en el código).

Variables: `DATABASE_URL` (desarrollo / aplicación), `TEST_DATABASE_URL` (pruebas de integración) y `EVENTOSNOVA_PERSISTENCIA`
(`memoria` por defecto, o `postgresql`). Si existe un archivo `.env` en la raíz del proyecto se lee SIN sobrescribir las variables
ya definidas en el entorno. Ninguna función de este módulo imprime la contraseña."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlsplit

RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
HOSTS_LOCALES = ("127.0.0.1", "localhost", "::1", "db")        # `db` = servicio PostgreSQL de Docker Compose
MODO_MEMORIA, MODO_POSTGRESQL = "memoria", "postgresql"


def cargar_env_local(ruta: Optional[Path] = None) -> None:
    """Lee `.env` sin sobrescribir variables existentes."""
    ruta = ruta or RAIZ_PROYECTO / ".env"
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def _variable(nombre: str) -> Optional[str]:
    cargar_env_local()
    return os.environ.get(nombre) or None


def url_desarrollo() -> Optional[str]:
    return _variable("DATABASE_URL")


def url_pruebas() -> Optional[str]:
    return _variable("TEST_DATABASE_URL")


def modo_persistencia() -> str:
    modo = (_variable("EVENTOSNOVA_PERSISTENCIA") or MODO_MEMORIA).strip().lower()
    if modo not in (MODO_MEMORIA, MODO_POSTGRESQL):
        raise ValueError(f"EVENTOSNOVA_PERSISTENCIA debe ser «{MODO_MEMORIA}» o «{MODO_POSTGRESQL}», no «{modo}».")
    return modo


def normalizar_url(url: str) -> str:
    """Acepta `postgres://` y `postgresql://` (como las entregan las plataformas de despliegue) y `postgresql+psycopg://`;
    siempre usa el controlador Psycopg 3."""
    for prefijo in ("postgresql://", "postgres://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


def descripcion_segura(url: str) -> Dict[str, object]:
    """Host, puerto, base y usuario SIN contraseña (para registros e informes)."""
    u = urlsplit(url.replace("+psycopg", ""))
    return {"host": u.hostname, "puerto": u.port, "base": u.path.lstrip("/"), "usuario": u.username}


def es_base_local_de_pruebas(url: str) -> bool:
    """Una base se considera de pruebas solo si es local y su nombre termina en `_test`. Protege las operaciones destructivas."""
    d = descripcion_segura(url)
    return d["host"] in HOSTS_LOCALES and str(d["base"]).endswith("_test")


def url_con_base(url: str, base: str) -> str:
    """La misma URL (host, puerto, credenciales) apuntando a otra base de datos; solo para uso interno, nunca se imprime."""
    u = urlsplit(url)
    return u._replace(path="/" + base).geturl()
