"""Unidad de trabajo persistente (PostgreSQL) compatible con `application.puertos.IUnitOfWork`.

Contrato (el mismo que `UnitOfWorkMemoria`): `iniciar()` abre la transacción; `registrar(*agregados)` indica qué agregados
participan; `confirmar()` extrae sus Domain Events y los guarda en el Outbox DENTRO de la misma transacción que los cambios del
agregado (ADR-004) y la confirma; `revertir()` deshace todo y descarta los eventos. Una operación = una transacción: no se
admiten transacciones anidadas (ningún servicio las usa).

Aislamiento: la transacción y la lista de agregados viven en `threading.local` (a través de `AlmacenSQL`), de modo que cada
petición tiene la suya y no se comparte estado mutable. Los recursos se liberan siempre: tras `confirmar` o `revertir` la conexión
vuelve al pool, también cuando falla la confirmación. Los errores de la base se propagan como `ErrorDePersistencia` (no se
convierten en rechazos de negocio ni se ocultan)."""
from __future__ import annotations
import threading
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence
import sqlalchemy as sa
from application.puertos import IUnitOfWork
from domain.eventos_dominio import EventoDominio
from .conexion import AlmacenSQL
from .errores import ErrorDePersistencia


class IRegistradorDeEventos(ABC):
    """Guarda los Domain Events con la conexión de la transacción en curso (la misma que usan los repositorios)."""
    @abstractmethod
    def registrar(self, conexion: sa.Connection, eventos: Sequence[EventoDominio]) -> None: ...


class UnitOfWorkSQL(IUnitOfWork):
    def __init__(self, almacen: AlmacenSQL, registrador: Optional[IRegistradorDeEventos] = None):
        self._almacen, self._registrador = almacen, registrador
        self._local = threading.local()

    @property
    def _agregados(self) -> List:
        return self._local.__dict__.setdefault("agregados", [])

    @property
    def almacen(self) -> AlmacenSQL:
        return self._almacen

    def iniciar(self) -> None:
        self._almacen.iniciar()                      # lanza ErrorDePersistencia si ya hay una transacción en este hilo
        self._local.agregados = []

    def registrar(self, *agregados) -> None:
        if self._almacen.conexion_activa is None:
            raise ErrorDePersistencia("No hay una transacción activa: llame primero a iniciar().")
        self._agregados.extend(a for a in agregados if a is not None)

    def confirmar(self) -> None:
        con = self._almacen.conexion_activa
        if con is None:
            raise ErrorDePersistencia("No hay una transacción activa que confirmar.")
        agregados, self._local.agregados = list(self._agregados), []
        try:
            eventos = [e for a in agregados for e in a.extraer_eventos()]
            if eventos and self._registrador is not None:
                self._registrador.registrar(con, eventos)       # misma transacción que los cambios del agregado
            elif eventos:
                raise ErrorDePersistencia("Hay Domain Events pendientes y no se configuró un registrador de eventos (Outbox).")
        except BaseException:
            self._almacen.revertir()
            raise
        self._almacen.confirmar()                               # si el commit falla, el almacén revierte y cierra la conexión

    def revertir(self) -> None:
        agregados, self._local.agregados = list(self._agregados), []
        for a in agregados:
            a.extraer_eventos()                                 # los eventos de una operación revertida no se publican
        if self._almacen.conexion_activa is not None:           # tolerante: tras un commit fallido ya no queda transacción
            self._almacen.revertir()
