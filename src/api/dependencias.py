"""Dependencias sustituibles de la API.

Las rutas obtienen los servicios de aplicación a través de estas funciones; no instancian repositorios ni
conocen las clases concretas de infraestructura. El contenedor lo crea la fábrica que recibe crear_app()
(hoy, la composición en memoria) y se guarda en app.state. En pruebas pueden sustituirse con
app.dependency_overrides."""
from __future__ import annotations
from datetime import datetime
from typing import Callable
from fastapi import Request
from application.reloj import reloj_negocio
from application.servicios import GestionPropuestaService


def obtener_contenedor(request: Request):
    return request.app.state.contenedor


def obtener_servicio_propuestas(request: Request) -> GestionPropuestaService:
    return obtener_contenedor(request).servicios.propuestas


def obtener_reloj() -> Callable[[], datetime]:
    """Momento que se entrega a los casos de uso como `ahora`: la hora de pared de America/Mexico_City sin zona (TP-06), la misma que usa el
    trabajador (`application.reloj.reloj_negocio`)."""
    return reloj_negocio
