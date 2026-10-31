"""Catálogo de proveedores: registrar, consultar un proveedor y buscar. La asignación de un proveedor a un servicio contratado y su
respuesta están en `rutas_eventos` (BN-004, BN-009). Un proveedor inexistente es 404 (`no_encontrado`), como en las demás consultas."""
from __future__ import annotations
from datetime import datetime
from typing import Callable, List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import Field
from .dependencias import obtener_contenedor, obtener_reloj
from .esquemas import RechazoRespuesta, _Esquema
from .rutas_comunes import OperacionRespuesta, responder

router = APIRouter(tags=["Proveedores (catálogo)"])
_RECHAZO = {422: {"model": RechazoRespuesta, "description": "Rechazo de negocio o entrada no válida"}}
_NO_ENCONTRADO = {404: {"model": RechazoRespuesta, "description": "Proveedor no encontrado"}, **_RECHAZO}


class ProveedorEntrada(_Esquema):
    """Alta de un proveedor. Solo el nombre es obligatorio: el BRD no especifica más atributos."""
    nombre: str = Field(examples=["Banquetes del Valle"])
    servicios: List[str] = Field(default_factory=list, examples=[["Banquete", "Música"]],
                                 description="Servicios que ofrece; se usan para proponerlo al asignar un servicio contratado.")
    contacto: str = Field(default="", examples=["55 1234 5678"], description="Texto libre (teléfono, correo...).")


@router.post("/proveedores", status_code=201, response_model=OperacionRespuesta, responses=_RECHAZO,
             summary="Registrar un proveedor en el catálogo")
def registrar_proveedor(entrada: ProveedorEntrada, contenedor=Depends(obtener_contenedor),
                        reloj: Callable[[], datetime] = Depends(obtener_reloj)):
    return responder(contenedor, contenedor.servicios.catalogo.registrar_proveedor(
        entrada.nombre, entrada.servicios, entrada.contacto, reloj()), despachar=False)


@router.get("/proveedores", response_model=OperacionRespuesta, responses=_RECHAZO,
            summary="Consultar y buscar proveedores del catálogo")
def listar_proveedores(q: str = Query(default="", description="Texto a buscar en identificador, nombre, contacto o servicios"),
                       servicio: Optional[str] = Query(default=None, description="Solo los que ofrecen este servicio"),
                       contenedor=Depends(obtener_contenedor)):
    return responder(contenedor, contenedor.servicios.catalogo.listar_proveedores(q, servicio or ""), despachar=False)


@router.get("/proveedores/{proveedor_id}", response_model=OperacionRespuesta, responses=_NO_ENCONTRADO,
            summary="Datos de un proveedor del catálogo")
def consultar_proveedor(proveedor_id: str, contenedor=Depends(obtener_contenedor)):
    resultado = contenedor.servicios.catalogo.consultar_proveedor(proveedor_id)
    if not resultado.exito:
        return JSONResponse(status_code=404, content=RechazoRespuesta(tipo="no_encontrado", detalle=resultado.mensaje).model_dump())
    return responder(contenedor, resultado, despachar=False)
