"""Seguridad de Eventos Nova: cuentas, sesiones, roles y matriz de permisos.

No contiene reglas de negocio de eventos, pagos o proveedores: solo decide QUIÉN puede ejecutar QUÉ. La API aplica esta decisión en
FastAPI (`api/seguridad.py`); ocultar botones en la interfaz es solo comodidad.

Roles (decisión del equipo basada en los interesados del BRD; el Cliente no tiene cuenta, actúa por medio del Coordinador y Administración):
  - administrador: Administración. Pagos, devoluciones, autorizaciones, revisión de cancelaciones, consultas administrativas y cuentas.
  - coordinador:   Coordinador de Eventos Nova. Eventos, propuestas, contratos, solicitudes, proveedores y cancelaciones.
  - proveedor:     Proveedor externo. SOLO lo suyo: su ficha, los servicios que tiene asignados y su respuesta de disponibilidad.
Mínimo privilegio: una cuenta se crea SIEMPRE con un rol explícito (no hay rol por omisión) y el rol proveedor exige estar vinculado a un
proveedor del catálogo; ningún otro rol puede llevar ese vínculo.

Autenticación: correo + contraseña (Argon2id). Sesión opaca de 256 bits guardada solo como SHA-256 en la base de datos, caducidad por
inactividad y absoluta, cierre e invalidación, limitación de intentos fallidos persistida. La documentación completa está en
docs/SEGURIDAD_Y_PERMISOS.md."""
from __future__ import annotations
import hashlib
import hmac
import os
import re
import secrets
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from .reloj import reloj_negocio

ADMINISTRADOR, COORDINADOR, PROVEEDOR = "administrador", "coordinador", "proveedor"
ROLES = (ADMINISTRADOR, COORDINADOR, PROVEEDOR)
LONGITUD_MINIMA_CONTRASENA = 12
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------------------------------------ configuración
def _entero(nombre: str, defecto: int) -> int:
    try:
        return max(1, int(os.environ.get(nombre, defecto)))
    except ValueError:
        return defecto


@dataclass(frozen=True)
class ConfiguracionSeguridad:
    """Parámetros de seguridad. `desde_entorno()` es lo que usa la aplicación al arrancar; las pruebas construyen la suya."""
    activa: bool = True
    entorno: str = "local"                       # «local» o «produccion»
    cookie_nombre: str = "eventosnova_sesion"
    cookie_segura: bool = False                  # Secure: obligatoria en producción (HTTPS)
    inactividad_minutos: int = 30
    duracion_maxima_horas: int = 8
    max_intentos: int = 5                        # fallos por (correo, IP) dentro de la ventana
    max_intentos_ip: int = 25                    # fallos por IP, cualquier correo
    ventana_minutos: int = 15
    bloqueo_minutos: int = 15
    documentacion: bool = True                   # /docs, /redoc y /openapi.json
    origenes_permitidos: Tuple[str, ...] = ()    # además del propio host, para la comprobación de Origin
    hsts: bool = False

    @property
    def produccion(self) -> bool:
        return self.entorno == "produccion"

    @staticmethod
    def desactivada() -> "ConfiguracionSeguridad":
        """SIN autenticación: solo para pruebas automatizadas y desarrollo local explícito. Nunca válida en producción."""
        return ConfiguracionSeguridad(activa=False)

    @staticmethod
    def desde_entorno() -> "ConfiguracionSeguridad":
        entorno = os.environ.get("EVENTOSNOVA_ENTORNO", "local").strip().lower()
        if entorno not in ("local", "produccion"):
            raise ValueError("EVENTOSNOVA_ENTORNO debe ser «local» o «produccion».")
        prod = entorno == "produccion"
        desactivar = os.environ.get("EVENTOSNOVA_AUTENTICACION", "activa").strip().lower() in ("desactivada", "0", "off", "no")
        if desactivar and prod:
            raise ValueError("La autenticación no puede desactivarse con EVENTOSNOVA_ENTORNO=produccion.")
        segura = os.environ.get("EVENTOSNOVA_COOKIE_SEGURA", "1" if prod else "0").strip().lower() in ("1", "si", "sí", "true")
        if prod and not segura:
            raise ValueError("En producción la cookie de sesión debe ser Secure (EVENTOSNOVA_COOKIE_SEGURA=1, servicio detrás de HTTPS).")
        docs_defecto = "0" if prod else "1"
        return ConfiguracionSeguridad(
            activa=not desactivar, entorno=entorno, cookie_segura=segura,
            inactividad_minutos=_entero("EVENTOSNOVA_SESION_INACTIVIDAD_MIN", 30), duracion_maxima_horas=_entero("EVENTOSNOVA_SESION_DURACION_HORAS", 8),
            max_intentos=_entero("EVENTOSNOVA_LOGIN_MAX_INTENTOS", 5), ventana_minutos=_entero("EVENTOSNOVA_LOGIN_VENTANA_MIN", 15),
            bloqueo_minutos=_entero("EVENTOSNOVA_LOGIN_BLOQUEO_MIN", 15),
            documentacion=os.environ.get("EVENTOSNOVA_DOCS", docs_defecto).strip().lower() in ("1", "si", "sí", "true"),
            origenes_permitidos=tuple(x.strip().rstrip("/") for x in os.environ.get("EVENTOSNOVA_ORIGENES_PERMITIDOS", "").split(",") if x.strip()),
            hsts=prod)


# ------------------------------------------------------------------------------------------------ permisos
# Cada permiso es una capacidad de negocio. La matriz por rol y por operación está documentada en docs/SEGURIDAD_Y_PERMISOS.md.
PERMISOS_POR_ROL: Dict[str, FrozenSet[str]] = {
    ADMINISTRADOR: frozenset({
        "eventos.consultar", "eventos.revision_administrativa", "pagos.consultar", "pagos.registrar", "pagos.cobranza",
        "devoluciones.ejecutar", "solicitudes.autorizar", "solicitudes.importe_adicional", "proveedores.consultar", "proveedores.registrar",
        "usuarios.administrar"}),
    COORDINADOR: frozenset({
        "eventos.consultar", "eventos.registrar", "eventos.ciclo", "eventos.cancelar", "propuestas.gestionar", "contratos.gestionar",
        "pagos.consultar", "solicitudes.registrar", "solicitudes.gestionar", "proveedores.consultar", "proveedores.registrar",
        "proveedores.asignar", "proveedores.responder"}),     # el Coordinador anota la respuesta que el proveedor le comunica por teléfono o mensaje
    PROVEEDOR: frozenset({"proveedores.propio", "proveedores.responder"}),
}
SESION = "sesion"                                 # cualquier persona autenticada (su propia sesión y contraseña)


def _m(metodo: str, ruta: str, *permisos: str):
    return (metodo, ruta), frozenset(permisos)


# (método, ruta) → permisos que la autorizan (basta uno). Toda ruta ausente de esta matriz y de PUBLICAS se DENIEGA.
MATRIZ: Dict[Tuple[str, str], FrozenSet[str]] = dict([
    # eventos
    _m("GET", "/eventos", "eventos.consultar"), _m("POST", "/eventos", "eventos.registrar"),
    _m("GET", "/eventos/{evento_id}/administracion", "eventos.consultar"),
    _m("GET", "/eventos/{evento_id}/solicitudes-pendientes", "eventos.consultar"),
    _m("GET", "/solicitudes", "eventos.consultar"), _m("GET", "/servicios-pendientes-confirmacion", "eventos.consultar"),
    _m("POST", "/eventos/{evento_id}/inicio", "eventos.ciclo"), _m("POST", "/eventos/{evento_id}/finalizacion", "eventos.ciclo"),
    _m("POST", "/eventos/{evento_id}/cancelacion", "eventos.cancelar"),
    _m("POST", "/eventos/{evento_id}/cancelacion-por-falta-de-regularizacion", "eventos.cancelar"),
    _m("POST", "/eventos/{evento_id}/revision-administrativa", "eventos.revision_administrativa"),
    # propuestas
    _m("POST", "/eventos/{evento_id}/propuestas", "propuestas.gestionar"), _m("POST", "/propuestas/{propuesta_id}/versiones", "propuestas.gestionar"),
    _m("POST", "/propuestas/{propuesta_id}/aceptacion", "propuestas.gestionar"),
    _m("POST", "/propuestas/{propuesta_id}/cierre-por-no-aceptacion", "propuestas.gestionar"),
    # contratos
    _m("POST", "/propuestas/{propuesta_id}/contrato", "contratos.gestionar"),
    _m("POST", "/contratos/{contrato_id}/comunicacion-politica-no-reembolso", "contratos.gestionar"),
    _m("POST", "/contratos/{contrato_id}/firma", "contratos.gestionar"), _m("POST", "/contratos/{contrato_id}/confirmacion", "contratos.gestionar"),
    _m("POST", "/contratos/{contrato_id}/seguimiento-anticipo", "contratos.gestionar"),
    # pagos y devoluciones
    _m("GET", "/eventos/{evento_id}/pagos", "pagos.consultar"), _m("GET", "/pagos-pendientes", "pagos.consultar"),
    _m("GET", "/devoluciones-pendientes", "pagos.consultar"),
    _m("POST", "/estados-cuenta/{estado_cuenta_id}/pagos", "pagos.registrar"),
    _m("POST", "/estados-cuenta/{estado_cuenta_id}/pagos/{pago_id}/verificacion", "pagos.registrar"),
    _m("POST", "/estados-cuenta/{estado_cuenta_id}/protocolo-cobro", "pagos.cobranza"),
    _m("POST", "/estados-cuenta/{estado_cuenta_id}/regularizacion", "pagos.cobranza"),
    _m("POST", "/estados-cuenta/{estado_cuenta_id}/vencimiento-saldo-original", "pagos.cobranza"),
    _m("POST", "/estados-cuenta/{estado_cuenta_id}/devoluciones/{devolucion_id}/ejecucion", "devoluciones.ejecutar"),
    # solicitudes de cambio
    _m("POST", "/solicitudes-cambio", "solicitudes.registrar"),
    *[_m("POST", f"/solicitudes-cambio/{{solicitud_id}}/{x}", "solicitudes.gestionar")
      for x in ("anexo", "cierre-por-falta-de-pago", "confirmacion", "decision-cliente", "solicitud-pago", "viabilidad")],
    _m("POST", "/solicitudes-cambio/{solicitud_id}/autorizacion", "solicitudes.autorizar"),
    # servicios adicionales
    _m("POST", "/solicitudes-servicio-adicional", "solicitudes.registrar"),
    *[_m("POST", f"/solicitudes-servicio-adicional/{{solicitud_id}}/{x}", "solicitudes.gestionar")
      for x in ("anexo", "aprobacion-cliente", "cierre-por-falta-de-pago", "confirmacion", "decision-espera", "disponibilidad", "solicitud-pago")],
    _m("POST", "/solicitudes-servicio-adicional/{solicitud_id}/autorizacion", "solicitudes.autorizar"),
    # sustituciones de proveedor
    _m("POST", "/sustituciones", "solicitudes.registrar"),
    *[_m("POST", f"/sustituciones/{{sustitucion_id}}/{x}", "solicitudes.gestionar") for x in ("alternativa", "anexo", "confirmacion", "decision-cliente")],
    _m("POST", "/sustituciones/{sustitucion_id}/autorizacion", "solicitudes.autorizar"),
    _m("POST", "/sustituciones/{sustitucion_id}/importe-adicional", "solicitudes.importe_adicional"),
    # proveedores
    _m("GET", "/proveedores", "proveedores.consultar"), _m("POST", "/proveedores", "proveedores.registrar"),
    _m("GET", "/proveedores/{proveedor_id}", "proveedores.consultar", "proveedores.propio"),                      # el proveedor, solo la suya
    _m("GET", "/proveedores/{proveedor_id}/eventos/{evento_id}", "proveedores.consultar", "proveedores.propio"),  # el proveedor, solo la suya
    _m("GET", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/disponibilidad", "proveedores.asignar"),
    _m("POST", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/proveedor", "proveedores.asignar"),
    _m("POST", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/respuesta-proveedor", "proveedores.responder"),   # el proveedor, solo la suya
    # cuentas y sesión
    _m("GET", "/auth/yo", SESION), _m("POST", "/auth/cierre-sesion", SESION), _m("POST", "/auth/cambio-contrasena", SESION),
    _m("GET", "/usuarios", "usuarios.administrar"), _m("POST", "/usuarios", "usuarios.administrar"),
    _m("POST", "/usuarios/{usuario_id}/estado", "usuarios.administrar"), _m("POST", "/usuarios/{usuario_id}/contrasena", "usuarios.administrar"),
])
PUBLICAS = frozenset({("GET", "/"), ("GET", "/health"), ("GET", "/ready"), ("POST", "/auth/inicio-sesion")})
# Permisos que SOLO se ejercen sobre recursos propios: la API comprueba además que el recurso pertenece a la cuenta.
PERMISOS_DE_RECURSO_PROPIO = frozenset({"proveedores.propio", "proveedores.responder"})


def permisos_del_rol(rol: str) -> FrozenSet[str]:
    return PERMISOS_POR_ROL.get(rol, frozenset())


def autoriza(rol: str, metodo: str, ruta: str) -> bool:
    requeridos = MATRIZ.get((metodo.upper(), ruta))
    if requeridos is None:
        return False                                                           # deny-by-default
    return SESION in requeridos or bool(requeridos & permisos_del_rol(rol))


# ------------------------------------------------------------------------------------------------ modelos
@dataclass(frozen=True)
class Usuario:
    usuario_id: str
    correo: str
    nombre: str
    rol: str
    contrasena_hash: str
    activo: bool
    proveedor_id: Optional[str]
    creado_en: datetime
    ultimo_acceso: Optional[datetime] = None

    def publico(self) -> dict:
        return {"usuarioId": self.usuario_id, "correo": self.correo, "nombre": self.nombre, "rol": self.rol, "activo": self.activo,
                "proveedorId": self.proveedor_id, "creadoEn": self.creado_en.isoformat(),
                "ultimoAcceso": self.ultimo_acceso.isoformat() if self.ultimo_acceso else None}


@dataclass(frozen=True)
class Sesion:
    sesion_hash: str                 # SHA-256 del token; el token en claro solo existe en la cookie del navegador
    usuario_id: str
    csrf: str
    creada_en: datetime
    ultima_actividad: datetime
    expira_en: datetime
    revocada_en: Optional[datetime] = None


@dataclass(frozen=True)
class Intento:
    clave: str
    fallos: int
    primer_fallo: datetime
    bloqueado_hasta: Optional[datetime] = None


class ErrorSeguridad(Exception):
    """Fallo de autenticación o autorización con el estado HTTP y el tipo que la API devuelve."""
    def __init__(self, estado: int, tipo: str, detalle: str, reintentar_en: Optional[int] = None):
        super().__init__(detalle)
        self.estado, self.tipo, self.detalle, self.reintentar_en = estado, tipo, detalle, reintentar_en


class IAlmacenSeguridad:
    """Persistencia de cuentas, sesiones e intentos. Implementaciones: memoria y PostgreSQL."""
    def crear_usuario(self, usuario: Usuario) -> bool: raise NotImplementedError          # False si el correo ya existe
    def obtener_usuario(self, usuario_id: str) -> Optional[Usuario]: raise NotImplementedError
    def obtener_usuario_por_correo(self, correo: str) -> Optional[Usuario]: raise NotImplementedError
    def listar_usuarios(self) -> List[Usuario]: raise NotImplementedError
    def actualizar_usuario(self, usuario: Usuario) -> None: raise NotImplementedError
    def crear_sesion(self, sesion: Sesion) -> None: raise NotImplementedError
    def obtener_sesion(self, sesion_hash: str) -> Optional[Sesion]: raise NotImplementedError
    def actualizar_sesion(self, sesion: Sesion) -> None: raise NotImplementedError
    def revocar_sesiones_de(self, usuario_id: str, cuando: datetime) -> int: raise NotImplementedError
    def obtener_intento(self, clave: str) -> Optional[Intento]: raise NotImplementedError
    def guardar_intento(self, intento: Intento) -> None: raise NotImplementedError
    def borrar_intento(self, clave: str) -> None: raise NotImplementedError


# ------------------------------------------------------------------------------------------------ servicio
def hash_de_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clave(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:40]


class ServicioSeguridad:
    MENSAJE_CREDENCIALES = "Correo o contraseña incorrectos."

    def __init__(self, almacen: IAlmacenSeguridad, config: Optional[ConfiguracionSeguridad] = None,
                 reloj: Callable[[], datetime] = reloj_negocio, catalogo=None):
        self.almacen, self.config, self.reloj, self.catalogo = almacen, config or ConfiguracionSeguridad.desde_entorno(), reloj, catalogo
        self._hasher = PasswordHasher()                                       # Argon2id con los parámetros recomendados de argon2-cffi
        self._hash_ficticio = self._hasher.hash(secrets.token_urlsafe(16))    # iguala el tiempo cuando el correo no existe

    # -- contraseñas
    @staticmethod
    def validar_contrasena(contrasena: str, correo: str = "", nombre: str = "") -> Optional[str]:
        if not isinstance(contrasena, str) or len(contrasena) < LONGITUD_MINIMA_CONTRASENA:
            return f"La contraseña debe tener al menos {LONGITUD_MINIMA_CONTRASENA} caracteres."
        if len(contrasena) > 256:
            return "La contraseña es demasiado larga (máximo 256 caracteres)."
        if len(set(contrasena)) < 4:
            return "La contraseña es demasiado simple: use más caracteres distintos."
        if correo and contrasena.lower() in (correo.lower(), correo.split("@")[0].lower()):
            return "La contraseña no puede ser igual al correo."
        if nombre and contrasena.lower() == nombre.lower():
            return "La contraseña no puede ser igual al nombre."
        return None

    def _verificar(self, hash_: str, contrasena: str) -> bool:
        try:
            return self._hasher.verify(hash_, contrasena)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    # -- cuentas
    def crear_usuario(self, correo: str, nombre: str, rol: str, contrasena: str, proveedor_id: Optional[str] = None) -> Usuario:
        correo = (correo or "").strip().lower()
        nombre = " ".join((nombre or "").split())
        if not RE_CORREO.match(correo):
            raise ValueError("Indique un correo válido.")
        if not nombre:
            raise ValueError("Indique el nombre de la persona.")
        if rol not in ROLES:
            raise ValueError(f"El rol debe indicarse explícitamente y ser uno de: {', '.join(ROLES)}.")
        if rol == PROVEEDOR:
            if not proveedor_id:
                raise ValueError("Una cuenta de proveedor debe vincularse a un proveedor del catálogo.")
            if self.catalogo is not None and self.catalogo.obtener_por_id(proveedor_id) is None:
                raise ValueError("El proveedor indicado no existe en el catálogo.")
        elif proveedor_id:
            raise ValueError("Solo las cuentas con rol proveedor se vinculan a un proveedor.")
        problema = self.validar_contrasena(contrasena, correo, nombre)
        if problema:
            raise ValueError(problema)
        usuario = Usuario(f"US-{uuid.uuid4()}", correo, nombre, rol, self._hasher.hash(contrasena), True, proveedor_id or None, self.reloj())
        if not self.almacen.crear_usuario(usuario):
            raise ValueError("Ya existe una cuenta con ese correo.")
        return usuario

    def listar_usuarios(self) -> List[Usuario]:
        return self.almacen.listar_usuarios()

    def cambiar_estado(self, usuario_id: str, activo: bool, actor_id: str) -> Usuario:
        u = self.almacen.obtener_usuario(usuario_id)
        if u is None:
            raise LookupError("La cuenta no existe.")
        if not activo and u.usuario_id == actor_id:
            raise ValueError("No puede desactivar su propia cuenta.")
        if not activo and u.rol == ADMINISTRADOR and u.activo and sum(1 for x in self.almacen.listar_usuarios() if x.rol == ADMINISTRADOR and x.activo) <= 1:
            raise ValueError("No se puede desactivar al último administrador activo.")
        nuevo = replace(u, activo=activo)
        self.almacen.actualizar_usuario(nuevo)
        if not activo:
            self.almacen.revocar_sesiones_de(u.usuario_id, self.reloj())          # la baja cierra de inmediato todas sus sesiones
        return nuevo

    def restablecer_contrasena(self, usuario_id: str, nueva: str) -> Usuario:
        u = self.almacen.obtener_usuario(usuario_id)
        if u is None:
            raise LookupError("La cuenta no existe.")
        problema = self.validar_contrasena(nueva, u.correo, u.nombre)
        if problema:
            raise ValueError(problema)
        nuevo = replace(u, contrasena_hash=self._hasher.hash(nueva))
        self.almacen.actualizar_usuario(nuevo)
        self.almacen.revocar_sesiones_de(u.usuario_id, self.reloj())
        return nuevo

    def cambiar_contrasena_propia(self, usuario: Usuario, actual: str, nueva: str) -> None:
        u = self.almacen.obtener_usuario(usuario.usuario_id)
        if u is None or not self._verificar(u.contrasena_hash, actual or ""):
            raise ErrorSeguridad(403, "sin_permiso", "La contraseña actual no es correcta.")
        problema = self.validar_contrasena(nueva, u.correo, u.nombre)
        if problema:
            raise ValueError(problema)
        self.almacen.actualizar_usuario(replace(u, contrasena_hash=self._hasher.hash(nueva)))
        self.almacen.revocar_sesiones_de(u.usuario_id, self.reloj())              # el cambio cierra todas las sesiones, incluida la actual

    # -- limitación de intentos
    def _claves_de_intento(self, correo: str, ip: str) -> List[Tuple[str, int]]:
        return [(_clave(f"par|{correo}|{ip}"), self.config.max_intentos), (_clave(f"ip|{ip}"), self.config.max_intentos_ip)]

    def _comprobar_bloqueo(self, claves: List[Tuple[str, int]]) -> None:
        ahora = self.reloj()
        for clave, _ in claves:
            i = self.almacen.obtener_intento(clave)
            if i and i.bloqueado_hasta and i.bloqueado_hasta > ahora:
                espera = max(1, int((i.bloqueado_hasta - ahora).total_seconds()))
                raise ErrorSeguridad(429, "demasiados_intentos", f"Demasiados intentos fallidos. Espere {max(1, round(espera / 60))} minuto(s) e inténtelo de nuevo.", espera)

    def _registrar_fallo(self, claves: List[Tuple[str, int]]) -> None:
        ahora = self.reloj()
        for clave, maximo in claves:
            i = self.almacen.obtener_intento(clave)
            if i is None or (ahora - i.primer_fallo) > timedelta(minutes=self.config.ventana_minutos) and not (i.bloqueado_hasta and i.bloqueado_hasta > ahora):
                i = Intento(clave, 1, ahora)
            else:
                i = Intento(clave, i.fallos + 1, i.primer_fallo, i.bloqueado_hasta)
            if i.fallos >= maximo:
                i = Intento(clave, 0, ahora, ahora + timedelta(minutes=self.config.bloqueo_minutos))
            self.almacen.guardar_intento(i)

    # -- sesiones
    def iniciar_sesion(self, correo: str, contrasena: str, ip: str = "-") -> Tuple[str, Sesion, Usuario]:
        correo = (correo or "").strip().lower()
        claves = self._claves_de_intento(correo, ip)
        self._comprobar_bloqueo(claves)
        u = self.almacen.obtener_usuario_por_correo(correo)
        correcto = self._verificar(u.contrasena_hash if u else self._hash_ficticio, contrasena or "")
        if u is None or not correcto or not u.activo:
            self._registrar_fallo(claves)
            raise ErrorSeguridad(401, "no_autenticado", self.MENSAJE_CREDENCIALES)      # el mismo mensaje para cualquier causa
        for clave, _ in claves[:1]:
            self.almacen.borrar_intento(clave)
        ahora = self.reloj()
        token = secrets.token_urlsafe(32)
        sesion = Sesion(hash_de_token(token), u.usuario_id, secrets.token_urlsafe(24), ahora, ahora,
                        ahora + timedelta(hours=self.config.duracion_maxima_horas))
        self.almacen.crear_sesion(sesion)
        u = replace(u, ultimo_acceso=ahora)
        self.almacen.actualizar_usuario(u)
        return token, sesion, u

    def autenticar(self, token: Optional[str]) -> Tuple[Usuario, Sesion]:
        if not token:
            raise ErrorSeguridad(401, "no_autenticado", "Inicie sesión para continuar.")
        s = self.almacen.obtener_sesion(hash_de_token(token))
        ahora = self.reloj()
        if s is None or s.revocada_en is not None:
            raise ErrorSeguridad(401, "sesion_expirada", "Su sesión ya no es válida. Inicie sesión nuevamente.")
        if ahora >= s.expira_en or ahora - s.ultima_actividad > timedelta(minutes=self.config.inactividad_minutos):
            self.almacen.actualizar_sesion(replace(s, revocada_en=ahora))
            raise ErrorSeguridad(401, "sesion_expirada", "Su sesión expiró. Inicie sesión nuevamente.")
        u = self.almacen.obtener_usuario(s.usuario_id)
        if u is None or not u.activo:
            raise ErrorSeguridad(401, "sesion_expirada", "Su cuenta ya no tiene acceso. Contacte a un administrador.")
        if ahora - s.ultima_actividad > timedelta(seconds=60):                    # actividad deslizante sin escribir en cada petición
            s = replace(s, ultima_actividad=ahora)
            self.almacen.actualizar_sesion(s)
        return u, s

    def cerrar_sesion(self, token: Optional[str]) -> None:
        if not token:
            return
        s = self.almacen.obtener_sesion(hash_de_token(token))
        if s is not None and s.revocada_en is None:
            self.almacen.actualizar_sesion(replace(s, revocada_en=self.reloj()))

    @staticmethod
    def csrf_valido(sesion: Sesion, recibido: Optional[str]) -> bool:
        return bool(recibido) and hmac.compare_digest(sesion.csrf, recibido)
