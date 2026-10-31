"""Aplicación de la seguridad en FastAPI: autenticación por cookie de sesión, autorización por rol, CSRF, Origin y cabeceras.

`aplicar_seguridad` es una dependencia que se añade a TODOS los enrutadores de negocio. Busca la ruta ejecutada en la matriz de
`application.seguridad`: una ruta que no está en la matriz se DENIEGA (nunca queda abierta por olvido). Con la configuración
`activa=False` (solo pruebas automatizadas y desarrollo local explícito) no hace nada."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
from fastapi import Request, Response, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie
from application.seguridad import (MATRIZ, PERMISOS_DE_RECURSO_PROPIO, PROVEEDOR, PUBLICAS, SESION, ConfiguracionSeguridad, ErrorSeguridad,
                                    Sesion, Usuario, permisos_del_rol)
from .esquemas import RechazoRespuesta

registro = logging.getLogger("eventosnova.seguridad")
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
CABECERA_CSRF = "X-CSRF-Token"
# Documenta en OpenAPI que las operaciones usan la cookie de sesión (no la valida: la valida `aplicar_seguridad`).
esquema_cookie = APIKeyCookie(name=ConfiguracionSeguridad().cookie_nombre, scheme_name="SesionCookie", auto_error=False,
                              description="Cookie de sesión HttpOnly emitida por POST /auth/inicio-sesion. Las operaciones que modifican datos "
                                          "exigen además la cabecera X-CSRF-Token que devuelve el inicio de sesión.")


@dataclass(frozen=True)
class ContextoSeguridad:
    usuario: Usuario
    sesion: Sesion

    @property
    def es_proveedor(self) -> bool:
        return self.usuario.rol == PROVEEDOR


def configuracion(request: Request) -> ConfiguracionSeguridad:
    return request.app.state.seguridad


def servicio_de_seguridad(request: Request):
    return request.app.state.contenedor.servicios.seguridad


def ip_de(request: Request) -> str:
    return request.client.host if request.client else "-"


def respuesta_de_error(exc: ErrorSeguridad) -> JSONResponse:
    cabeceras = {"Retry-After": str(exc.reintentar_en)} if exc.reintentar_en else {}
    cuerpo = RechazoRespuesta(tipo=exc.tipo, detalle=exc.detalle).model_dump()
    return JSONResponse(status_code=exc.estado, content=cuerpo, headers={"Cache-Control": "no-store", **cabeceras})


def registrar_manejador_de_seguridad(aplicacion) -> None:
    @aplicacion.exception_handler(ErrorSeguridad)
    async def _seguridad(_: Request, exc: ErrorSeguridad):
        return respuesta_de_error(exc)


def comprobar_origen(request: Request, cfg: ConfiguracionSeguridad) -> None:
    """Defensa en profundidad contra CSRF: en las operaciones que modifican datos, si el navegador envía Origin debe ser este mismo sitio
    (o uno permitido expresamente). Las llamadas sin Origin (curl, otros programas) no pasan por navegador: siguen necesitando la cookie y el token CSRF."""
    if request.method in METODOS_SEGUROS:
        return
    origen = request.headers.get("origin")
    if origen is None:
        return
    origen = origen.rstrip("/")
    propio = f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/")
    if origen != propio and origen not in cfg.origenes_permitidos:
        registro.warning("Origen rechazado %s en %s %s", origen, request.method, request.url.path)
        raise ErrorSeguridad(403, "sin_permiso", "La petición no proviene de este sitio y fue rechazada.")


def aplicar_seguridad(request: Request, _cookie: Optional[str] = Security(esquema_cookie)) -> None:
    cfg = configuracion(request)
    if not cfg.activa:
        return
    ruta = request.scope.get("route")
    plantilla = getattr(ruta, "path", request.url.path)
    clave = (request.method.upper(), plantilla)
    if clave in PUBLICAS:
        return
    requeridos = MATRIZ.get(clave)
    if requeridos is None:                                                       # deny-by-default
        registro.error("Ruta sin permiso definido: %s %s", *clave)
        raise ErrorSeguridad(403, "sin_permiso", "Esta operación no está habilitada.")
    comprobar_origen(request, cfg)
    token = request.cookies.get(cfg.cookie_nombre)
    usuario, sesion = servicio_de_seguridad(request).autenticar(token)
    if request.method not in METODOS_SEGUROS and not servicio_de_seguridad(request).csrf_valido(sesion, request.headers.get(CABECERA_CSRF)):
        registro.warning("CSRF inválido de la cuenta %s en %s %s", usuario.usuario_id, *clave)
        raise ErrorSeguridad(403, "sin_permiso", "La petición no se pudo validar (token de seguridad ausente o vencido). Recargue la página e inténtelo de nuevo.")
    if SESION not in requeridos and not (requeridos & permisos_del_rol(usuario.rol)):
        registro.warning("Acceso denegado a la cuenta %s (%s) en %s %s", usuario.usuario_id, usuario.rol, *clave)
        raise ErrorSeguridad(403, "sin_permiso", "No tiene permiso para realizar esta operación.")
    # Permisos sobre recursos propios: un proveedor solo accede a SU proveedor, nunca a un identificador que envíe el cliente.
    if usuario.rol == PROVEEDOR and "proveedor_id" in request.path_params and request.path_params["proveedor_id"] != usuario.proveedor_id:
        registro.warning("Proveedor %s intentó acceder a otro proveedor en %s %s", usuario.usuario_id, *clave)
        raise ErrorSeguridad(403, "sin_permiso", "Solo puede consultar la información de su propio proveedor.")
    request.state.contexto = ContextoSeguridad(usuario, sesion)


def contexto_actual(request: Request) -> Optional[ContextoSeguridad]:
    """Cuenta autenticada de la petición (None con la autenticación desactivada)."""
    return getattr(request.state, "contexto", None)


def poner_cookie(respuesta: Response, cfg: ConfiguracionSeguridad, token: str) -> None:
    respuesta.set_cookie(cfg.cookie_nombre, token, max_age=cfg.duracion_maxima_horas * 3600, httponly=True, secure=cfg.cookie_segura,
                         samesite="strict", path="/")


def quitar_cookie(respuesta: Response, cfg: ConfiguracionSeguridad) -> None:
    respuesta.delete_cookie(cfg.cookie_nombre, path="/", httponly=True, secure=cfg.cookie_segura, samesite="strict")


CSP_INTERFAZ = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")


def registrar_cabeceras(aplicacion, cfg: ConfiguracionSeguridad) -> None:
    @aplicacion.middleware("http")
    async def _cabeceras(request: Request, call_next):
        respuesta = await call_next(request)
        h = respuesta.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/app"):
            h.setdefault("Content-Security-Policy", CSP_INTERFAZ)          # Swagger (/docs) carga recursos externos: sin CSP estricta allí
        elif not request.url.path.startswith(("/docs", "/redoc")):
            h.setdefault("Cache-Control", "no-store")                      # respuestas de la API con datos de negocio: no se guardan en cachés
        if cfg.hsts:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return respuesta
