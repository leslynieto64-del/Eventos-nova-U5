"""Acceso a PostgreSQL: motor de SQLAlchemy y almacén transaccional compartido por los repositorios y la unidad de trabajo.

`AlmacenSQL` guarda la transacción activa en un `threading.local`: cada hilo (cada petición atendida por FastAPI) tiene SU
propia conexión y transacción, así que ninguna transacción mutable se comparte entre peticiones. Sin transacción activa, cada
lectura usa una conexión corta y cada escritura aislada (`guardar` fuera de una unidad de trabajo) se confirma sola."""
from __future__ import annotations
import threading
from contextlib import contextmanager
from typing import Iterator, Optional
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc
from .configuracion import normalizar_url
from .errores import (ErrorDeConexion, ErrorDeDatos, ErrorDePersistencia, ViolacionDeRestriccion)


def crear_motor(url: str, **opciones) -> sa.Engine:
    """Motor con conexiones verificadas antes de usarse (`pool_pre_ping`)."""
    opciones.setdefault("pool_pre_ping", True)
    argumentos = opciones.setdefault("connect_args", {})
    argumentos.setdefault("connect_timeout", 10)           # un fallo de red es un error rápido, no una espera indefinida
    return sa.create_engine(normalizar_url(url), **opciones)


def traducir(error: Exception) -> ErrorDePersistencia:
    """Convierte una excepción de SQLAlchemy/Psycopg en un error de persistencia con significado."""
    original = getattr(error, "orig", None)
    diag = getattr(original, "diag", None)
    codigo = getattr(original, "sqlstate", None) or getattr(diag, "sqlstate", None)
    if isinstance(error, sa_exc.IntegrityError):
        restriccion = getattr(diag, "constraint_name", None)
        if restriccion is None and getattr(diag, "column_name", None):                # NOT NULL no tiene nombre de restricción
            restriccion = f"NOT NULL {getattr(diag, 'column_name')}"
        nuevo = ViolacionDeRestriccion(str(original or error).strip().splitlines()[0], restriccion,
                                       getattr(diag, "table_name", None), codigo)
    elif isinstance(error, sa_exc.DataError):
        nuevo = ErrorDeDatos(str(original or error).strip().splitlines()[0])
    elif isinstance(error, (sa_exc.OperationalError, sa_exc.InterfaceError)):
        nuevo = ErrorDeConexion(str(original or error).strip().splitlines()[0])
    else:
        nuevo = ErrorDePersistencia(str(original or error).strip().splitlines()[0])
    nuevo.__cause__ = error
    return nuevo


class AlmacenSQL:
    def __init__(self, motor: sa.Engine):
        self.motor = motor
        self._local = threading.local()

    # -- transacción activa (la gestiona la unidad de trabajo)
    @property
    def conexion_activa(self) -> Optional[sa.Connection]:
        return getattr(self._local, "conexion", None)

    def iniciar(self) -> sa.Connection:
        if self.conexion_activa is not None:
            raise ErrorDePersistencia("Ya hay una transacción activa en este hilo: no se admiten transacciones anidadas.")
        try:
            con = self.motor.connect()
            con.begin()
        except sa_exc.SQLAlchemyError as e:
            raise traducir(e) from e
        self._local.conexion = con
        return con

    def confirmar(self) -> None:
        con = self._retirar()
        try:
            con.commit()
        except sa_exc.SQLAlchemyError as e:
            try:
                con.rollback()
            except sa_exc.SQLAlchemyError:
                pass                                # la conexión puede estar rota; se cierra igualmente
            raise traducir(e) from e
        finally:
            con.close()

    def revertir(self) -> None:
        con = self._retirar()
        try:
            con.rollback()
        except sa_exc.SQLAlchemyError:
            pass                                    # la conexión puede estar rota; se cierra igualmente
        finally:
            con.close()

    def _retirar(self) -> sa.Connection:
        con = self.conexion_activa
        if con is None:
            raise ErrorDePersistencia("No hay una transacción activa.")
        self._local.conexion = None
        return con

    # -- conexiones para los repositorios
    @contextmanager
    def lectura(self) -> Iterator[sa.Connection]:
        con = self.conexion_activa
        try:
            if con is not None:                      # dentro de una unidad de trabajo se ven los cambios propios
                yield con
            else:
                with self.motor.connect() as nueva:
                    yield nueva
        except sa_exc.SQLAlchemyError as e:
            raise traducir(e) from e

    @contextmanager
    def escritura(self) -> Iterator[sa.Connection]:
        con = self.conexion_activa
        try:
            if con is not None:                      # la unidad de trabajo confirma o revierte
                yield con
            else:                                    # escritura aislada: una transacción propia, confirmada al terminar
                with self.motor.begin() as nueva:
                    yield nueva
        except sa_exc.SQLAlchemyError as e:
            raise traducir(e) from e

    def cerrar(self) -> None:
        self.motor.dispose()
