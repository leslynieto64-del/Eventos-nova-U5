"""Almacén de seguridad en memoria (composición en memoria y pruebas). Mismo contrato que el almacén de PostgreSQL."""
from __future__ import annotations
import threading
from dataclasses import replace
from application.seguridad import IAlmacenSeguridad


class AlmacenSeguridadMemoria(IAlmacenSeguridad):
    def __init__(self):
        self._u, self._s, self._i = {}, {}, {}
        self._cerrojo = threading.Lock()

    def crear_usuario(self, usuario):
        with self._cerrojo:
            if any(x.correo == usuario.correo for x in self._u.values()):
                return False
            self._u[usuario.usuario_id] = usuario
            return True

    def obtener_usuario(self, usuario_id):
        return self._u.get(usuario_id)

    def obtener_usuario_por_correo(self, correo):
        return next((x for x in self._u.values() if x.correo == correo), None)

    def listar_usuarios(self):
        return sorted(self._u.values(), key=lambda x: (x.correo, x.usuario_id))

    def actualizar_usuario(self, usuario):
        self._u[usuario.usuario_id] = usuario

    def crear_sesion(self, sesion):
        self._s[sesion.sesion_hash] = sesion

    def obtener_sesion(self, sesion_hash):
        return self._s.get(sesion_hash)

    def actualizar_sesion(self, sesion):
        self._s[sesion.sesion_hash] = sesion

    def revocar_sesiones_de(self, usuario_id, cuando):
        n = 0
        for k, s in list(self._s.items()):
            if s.usuario_id == usuario_id and s.revocada_en is None:
                self._s[k] = replace(s, revocada_en=cuando)
                n += 1
        return n

    def obtener_intento(self, clave):
        return self._i.get(clave)

    def guardar_intento(self, intento):
        self._i[intento.clave] = intento

    def borrar_intento(self, clave):
        self._i.pop(clave, None)
