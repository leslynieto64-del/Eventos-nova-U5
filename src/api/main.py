"""Punto de entrada de la API de Eventos Nova.

Ejecución desde la raíz del proyecto:
    python -m uvicorn api.main:app --app-dir src --reload
"""
from __future__ import annotations
from fastapi import FastAPI

NOMBRE_APLICACION = "Eventos Nova"
VERSION_API = "0.1.0"
DESCRIPCION = ("API del sistema de apoyo a la gestión de eventos de Eventos Nova: propuestas, contratación, "
               "pagos, cancelaciones, cambios, servicios adicionales y sustituciones de proveedores.")


def crear_app() -> FastAPI:
    """Crea y configura la instancia de FastAPI."""
    aplicacion = FastAPI(title=f"{NOMBRE_APLICACION} API", version=VERSION_API, description=DESCRIPCION)

    @aplicacion.get("/", tags=["General"], summary="Identificación de la aplicación")
    def raiz() -> dict:
        return {
            "aplicacion": NOMBRE_APLICACION,
            "descripcion": DESCRIPCION,
            "version": VERSION_API,
            "documentacion": "/docs",
            "salud": "/health",
        }

    @aplicacion.get("/health", tags=["General"], summary="Verificación de disponibilidad")
    def salud() -> dict:
        return {"estado": "ok", "aplicacion": NOMBRE_APLICACION, "version": VERSION_API}

    return aplicacion


app = crear_app()
