"""Punto de entrada de la API de Eventos Nova.

Ejecución desde la raíz del proyecto:
    python -m uvicorn api.main:app --app-dir src --reload

Raíz de composición de la API: crear_app() recibe la fábrica del contenedor de servicios. Por omisión usa
infrastructure.composicion.construir (repositorios en memoria): implementación temporal para desarrollo y
pruebas; los datos se pierden al detener el servidor.

Modo de persistencia (variable de entorno EVENTOSNOVA_PERSISTENCIA): «memoria» (por omisión) o «postgresql», que usa
infrastructure.persistencia.composicion_persistente.construir_persistente (lee DATABASE_URL, comprueba la conexión y que las
migraciones estén aplicadas, y falla al arrancar si no).
"""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from typing import Callable, Optional
from pathlib import Path
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from infrastructure.adaptadores import disponibilidad_desde_entorno
from infrastructure.composicion import construir
from infrastructure.persistencia import configuracion as configuracion_persistencia
from infrastructure.persistencia.errores import (ConflictoDeConcurrencia, ErrorDeConexion, ErrorDeDatos, ErrorDePersistencia,
                                                    ViolacionDeRestriccion)
from application.seguridad import ConfiguracionSeguridad
from .errores import registrar_manejadores, registrar_manejadores_persistencia
from .rutas_seguridad import protegido as rutas_seguridad_protegidas, publico as rutas_seguridad_publicas
from .seguridad import aplicar_seguridad, registrar_cabeceras, registrar_manejador_de_seguridad
from .rutas_consultas import router as rutas_consultas
from .rutas_contratacion import router as rutas_contratacion
from .rutas_eventos import router as rutas_eventos
from .rutas_pagos import router as rutas_pagos
from .rutas_propuestas import router as rutas_propuestas
from .rutas_proveedores import router as rutas_proveedores
from .rutas_solicitudes import router as rutas_solicitudes

registro = logging.getLogger("eventosnova.api")
NOMBRE_APLICACION = "Eventos Nova"
VERSION_API = "0.1.0"
RUTA_INTERFAZ = Path(__file__).resolve().parents[1] / "web"
DESCRIPCION = ("API del sistema de apoyo a la gestión de eventos de Eventos Nova: propuestas, contratación, "
               "pagos, cancelaciones, cambios, servicios adicionales y sustituciones de proveedores.")


def fabrica_por_defecto() -> Callable[[], object]:
    """La composición que corresponde al modo de EVENTOSNOVA_PERSISTENCIA (en memoria, salvo que se pida «postgresql»)."""
    if configuracion_persistencia.modo_persistencia() == configuracion_persistencia.MODO_POSTGRESQL:
        from infrastructure.persistencia.composicion_persistente import construir_persistente_desde_entorno
        return construir_persistente_desde_entorno
    if os.environ.get("EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO", "").strip():     # simulación configurable de disponibilidad (opt-in)
        return lambda: construir(disponibilidad_desde_entorno())
    return construir


def crear_app(fabrica_contenedor: Optional[Callable[[], object]] = None, seguridad: Optional[ConfiguracionSeguridad] = None) -> FastAPI:
    """Crea y configura la instancia de FastAPI. Cada instancia tiene su propio contenedor de servicios.

    `seguridad`: configuración de autenticación y autorización. Es la fábrica PROGRAMÁTICA (pruebas, herramientas): sin argumento NO exige
    autenticación. La aplicación que se sirve (`api.main:app`, Docker) se crea con `ConfiguracionSeguridad.desde_entorno()`, que exige
    autenticación salvo que se desactive expresamente en un entorno local."""
    config = seguridad or ConfiguracionSeguridad.desactivada()
    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        yield
        cerrar = getattr(app.state.contenedor, "cerrar", None)
        if cerrar is not None:                       # libera el pool de conexiones de la composición persistente
            cerrar()

    aplicacion = FastAPI(title=f"{NOMBRE_APLICACION} API", version=VERSION_API, description=DESCRIPCION, lifespan=ciclo_de_vida,
                         docs_url="/docs" if config.documentacion else None, redoc_url="/redoc" if config.documentacion else None,
                         openapi_url="/openapi.json" if config.documentacion else None)
    aplicacion.state.contenedor = (fabrica_contenedor or fabrica_por_defecto())()
    aplicacion.state.seguridad = config
    servicio_seguridad = getattr(aplicacion.state.contenedor.servicios, "seguridad", None)
    if config.activa:
        if servicio_seguridad is None:
            raise RuntimeError("La autenticación está activa pero el contenedor no tiene almacén de seguridad.")
        servicio_seguridad.config = config
    else:
        registro.warning("AUTENTICACIÓN DESACTIVADA: cualquier persona con acceso puede ejecutar todas las operaciones. Solo para pruebas y desarrollo local.")
    registrar_manejador_de_seguridad(aplicacion)
    registrar_cabeceras(aplicacion, config)
    registrar_manejadores(aplicacion)
    registrar_manejadores_persistencia(aplicacion, ViolacionDeRestriccion, ErrorDeDatos, ErrorDeConexion, ErrorDePersistencia,
                                      ConflictoDeConcurrencia)
    for enrutador in (rutas_propuestas, rutas_contratacion, rutas_pagos, rutas_eventos, rutas_solicitudes, rutas_consultas,
                       rutas_proveedores):
        aplicacion.include_router(enrutador, dependencies=[Depends(aplicar_seguridad)])   # autorización por rol en CADA ruta de negocio
    aplicacion.include_router(rutas_seguridad_publicas)
    aplicacion.include_router(rutas_seguridad_protegidas)
    if RUTA_INTERFAZ.is_dir():                      # interfaz web (HTML, CSS y JavaScript sin frameworks) en el mismo origen que la API
        aplicacion.mount("/app", StaticFiles(directory=RUTA_INTERFAZ, html=True), name="interfaz")

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

    @aplicacion.get("/ready", tags=["General"], summary="Disponibilidad de la aplicación y de la base de datos")
    def listo():
        contenedor = aplicacion.state.contenedor
        modo = getattr(contenedor, "modo", configuracion_persistencia.MODO_MEMORIA)
        comprobar = getattr(contenedor, "comprobar_base_de_datos", None)
        if comprobar is not None:
            try:
                comprobar()
            except Exception:
                return JSONResponse(status_code=503, content={"estado": "no_disponible", "persistencia": modo,
                                                              "base_de_datos": "no_disponible"})
        return {"estado": "ok", "persistencia": modo, "base_de_datos": "ok" if comprobar is not None else "no_aplica"}

    return aplicacion


app = crear_app(seguridad=ConfiguracionSeguridad.desde_entorno())
