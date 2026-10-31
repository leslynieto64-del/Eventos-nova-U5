"""Inicio y cierre de sesión, sesión actual, cambio de contraseña y administración de cuentas.

Solo `POST /auth/inicio-sesion` es público. Las cuentas las administra únicamente el rol administrador. Las contraseñas nunca se devuelven ni se
registran; el token de sesión viaja solo en una cookie HttpOnly."""
from __future__ import annotations
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field, StrictBool
from application.seguridad import ErrorSeguridad, ROLES, permisos_del_rol
from .esquemas import RechazoRespuesta, _Esquema
from .rutas_comunes import OperacionRespuesta
from .seguridad import (CABECERA_CSRF, ContextoSeguridad, aplicar_seguridad, comprobar_origen, configuracion, contexto_actual, ip_de, poner_cookie,
                        quitar_cookie, servicio_de_seguridad)

registro = logging.getLogger("eventosnova.seguridad")
_RECHAZO = {422: {"model": RechazoRespuesta, "description": "Datos no válidos"}, 401: {"model": RechazoRespuesta, "description": "No autenticado"},
            403: {"model": RechazoRespuesta, "description": "Sin permiso"}}

# Público: no lleva la dependencia de autorización (valida las credenciales él mismo).
publico = APIRouter(tags=["Seguridad"])
# Requiere sesión (la matriz decide el permiso).
protegido = APIRouter(tags=["Seguridad"], dependencies=[Depends(aplicar_seguridad)])


class InicioSesionEntrada(_Esquema):
    correo: str = Field(examples=["coordinador@eventosnova.example"], max_length=254)
    contrasena: str = Field(max_length=256)


class CambioContrasenaEntrada(_Esquema):
    actual: str = Field(max_length=256)
    nueva: str = Field(max_length=256)


class UsuarioEntrada(_Esquema):
    correo: str = Field(max_length=254)
    nombre: str = Field(max_length=200)
    rol: str = Field(examples=list(ROLES), description="Obligatorio: no existe un rol por omisión (mínimo privilegio).")
    contrasena: str = Field(max_length=256)
    proveedor_id: Optional[str] = Field(default=None, description="Solo para el rol proveedor: el proveedor del catálogo al que pertenece la cuenta.")


class EstadoUsuarioEntrada(_Esquema):
    activo: StrictBool


class ContrasenaEntrada(_Esquema):
    contrasena: str = Field(max_length=256)


def _datos_de_sesion(cfg, usuario, sesion) -> dict:
    return {"autenticacionActiva": True, "usuario": usuario.publico(), "permisos": sorted(permisos_del_rol(usuario.rol)), "csrf": sesion.csrf,
            "cabeceraCsrf": CABECERA_CSRF, "expiraEn": sesion.expira_en.isoformat(), "inactividadMinutos": cfg.inactividad_minutos}


def _rechazo_negocio(detalle: str) -> JSONResponse:
    return JSONResponse(status_code=422, content=RechazoRespuesta(detalle=detalle).model_dump())


@publico.post("/auth/inicio-sesion", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Iniciar sesión")
def iniciar_sesion(entrada: InicioSesionEntrada, request: Request, respuesta: Response):
    cfg = configuracion(request)
    if not cfg.activa:
        return JSONResponse(status_code=409, content=RechazoRespuesta(tipo="autenticacion_desactivada",
                            detalle="La autenticación está desactivada en este entorno (solo desarrollo).").model_dump())
    comprobar_origen(request, cfg)
    token, sesion, usuario = servicio_de_seguridad(request).iniciar_sesion(entrada.correo, entrada.contrasena, ip_de(request))
    poner_cookie(respuesta, cfg, token)
    respuesta.headers["Cache-Control"] = "no-store"
    registro.info("Inicio de sesión de la cuenta %s (%s)", usuario.usuario_id, usuario.rol)
    return OperacionRespuesta(mensaje="Sesión iniciada.", datos=_datos_de_sesion(cfg, usuario, sesion))


@protegido.get("/auth/yo", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Sesión actual")
def sesion_actual(request: Request, contexto: Optional[ContextoSeguridad] = Depends(contexto_actual)):
    cfg = configuracion(request)
    if not cfg.activa:
        return OperacionRespuesta(mensaje="Autenticación desactivada.", datos={"autenticacionActiva": False})
    return OperacionRespuesta(mensaje="Sesión vigente.", datos=_datos_de_sesion(cfg, contexto.usuario, contexto.sesion))


@protegido.post("/auth/cierre-sesion", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Cerrar sesión")
def cerrar_sesion(request: Request, respuesta: Response):
    cfg = configuracion(request)
    if cfg.activa:
        servicio_de_seguridad(request).cerrar_sesion(request.cookies.get(cfg.cookie_nombre))
        quitar_cookie(respuesta, cfg)
    return OperacionRespuesta(mensaje="Sesión cerrada.")


@protegido.post("/auth/cambio-contrasena", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Cambiar la contraseña propia")
def cambiar_contrasena(entrada: CambioContrasenaEntrada, request: Request, respuesta: Response, contexto: Optional[ContextoSeguridad] = Depends(contexto_actual)):
    if contexto is None:
        return _rechazo_negocio("La autenticación está desactivada: no hay cuenta a la que cambiar la contraseña.")
    try:
        servicio_de_seguridad(request).cambiar_contrasena_propia(contexto.usuario, entrada.actual, entrada.nueva)
    except ValueError as e:
        return _rechazo_negocio(str(e))
    quitar_cookie(respuesta, configuracion(request))
    return OperacionRespuesta(mensaje="Contraseña cambiada. Por seguridad se cerraron todas sus sesiones: inicie sesión de nuevo.")


@protegido.get("/usuarios", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Listar las cuentas")
def listar_usuarios(request: Request):
    return OperacionRespuesta(mensaje="Cuentas consultadas.", datos={"usuarios": [u.publico() for u in servicio_de_seguridad(request).listar_usuarios()]})


@protegido.post("/usuarios", status_code=201, response_model=OperacionRespuesta, responses=_RECHAZO, summary="Crear una cuenta")
def crear_usuario(entrada: UsuarioEntrada, request: Request):
    try:
        u = servicio_de_seguridad(request).crear_usuario(entrada.correo, entrada.nombre, entrada.rol, entrada.contrasena, entrada.proveedor_id)
    except ValueError as e:
        return _rechazo_negocio(str(e))
    registro.info("Cuenta %s creada con rol %s", u.usuario_id, u.rol)
    return OperacionRespuesta(mensaje="Cuenta creada.", datos=u.publico())


@protegido.post("/usuarios/{usuario_id}/estado", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Activar o desactivar una cuenta")
def cambiar_estado(usuario_id: str, entrada: EstadoUsuarioEntrada, request: Request, contexto: Optional[ContextoSeguridad] = Depends(contexto_actual)):
    try:
        u = servicio_de_seguridad(request).cambiar_estado(usuario_id, entrada.activo, contexto.usuario.usuario_id if contexto else "")
    except LookupError as e:
        return JSONResponse(status_code=404, content=RechazoRespuesta(tipo="no_encontrado", detalle=str(e)).model_dump())
    except ValueError as e:
        return _rechazo_negocio(str(e))
    return OperacionRespuesta(mensaje="Cuenta activada." if u.activo else "Cuenta desactivada; sus sesiones se cerraron.", datos=u.publico())


@protegido.post("/usuarios/{usuario_id}/contrasena", response_model=OperacionRespuesta, responses=_RECHAZO, summary="Restablecer la contraseña de una cuenta")
def restablecer_contrasena(usuario_id: str, entrada: ContrasenaEntrada, request: Request):
    try:
        u = servicio_de_seguridad(request).restablecer_contrasena(usuario_id, entrada.contrasena)
    except LookupError as e:
        return JSONResponse(status_code=404, content=RechazoRespuesta(tipo="no_encontrado", detalle=str(e)).model_dump())
    except ValueError as e:
        return _rechazo_negocio(str(e))
    return OperacionRespuesta(mensaje="Contraseña restablecida; las sesiones de la cuenta se cerraron.", datos=u.publico())
