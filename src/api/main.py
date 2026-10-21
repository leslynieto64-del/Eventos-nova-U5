"""Punto de entrada de la API de Eventos Nova.

Ejecución desde la raíz del proyecto:
    python -m uvicorn api.main:app --app-dir src --reload

Raíz de composición de la API: crear_app() recibe la fábrica del contenedor de servicios. Por omisión usa
infrastructure.composicion.construir (repositorios en memoria): implementación temporal para desarrollo y
pruebas; los datos se pierden al detener el servidor.
"""
from __future__ import annotations
from typing import Callable, Optional
from fastapi import FastAPI
from infrastructure.composicion import construir
from .errores import registrar_manejadores
from .rutas_propuestas import router as rutas_propuestas

NOMBRE_APLICACION = "Eventos Nova"
VERSION_API = "0.1.0"
DESCRIPCION = ("API del sistema de apoyo a la gestión de eventos de Eventos Nova: propuestas, contratación, "
               "pagos, cancelaciones, cambios, servicios adicionales y sustituciones de proveedores.")


def crear_app(fabrica_contenedor: Optional[Callable[[], object]] = None) -> FastAPI:
    """Crea y configura la instancia de FastAPI. Cada instancia tiene su propio contenedor de servicios."""
    aplicacion = FastAPI(title=f"{NOMBRE_APLICACION} API", version=VERSION_API, description=DESCRIPCION)
    aplicacion.state.contenedor = (fabrica_contenedor or construir)()
    registrar_manejadores(aplicacion)
    aplicacion.include_router(rutas_propuestas)

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
