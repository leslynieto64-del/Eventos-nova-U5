"""Outbox persistente (ADR-004) sobre las tablas `outbox_evento` y `outbox_reaccion`.

REGISTRO. `OutboxSQL.registrar` inserta los Domain Events de una operación con la MISMA conexión de la transacción del agregado
(la llama `UnitOfWorkSQL.confirmar`): el cambio y su evento se confirman o se revierten juntos. Un evento que el codec no puede
serializar hace fallar (y revertir) la operación, así no se guarda nada que luego no pueda reconstruirse.

DESPACHO. `DespachadorOutboxSQL.despachar` toma el siguiente evento PENDIENTE (orden de `secuencia`) y lo RECLAMA con
`SELECT ... FOR NO KEY UPDATE SKIP LOCKED`: dos trabajadores concurrentes nunca procesan a la vez el mismo evento (FOR NO KEY UPDATE
no bloquea la comprobación de la clave foránea de `outbox_reaccion`). Cada reacción se ejecuta en SU transacción (ADR-004) y, al
terminar bien, se anota de inmediato en `outbox_reaccion` en una transacción propia: si el trabajador cae, el reintento solo
ejecuta las reacciones que faltan. Si todas terminan, el evento pasa a PROCESADO; si alguna falla, se cuenta un intento y, al
llegar a `max_intentos`, pasa a REVISION con el motivo en `error` (error permanente observable). Un evento que no puede
rehidratarse pasa a REVISION con el motivo; nunca se descarta.

LÍMITE conocido: ejecutar la reacción y anotarla son dos transacciones; una caída entre ambas repite la reacción en el reintento,
por eso ADR-004 exige reacciones idempotentes. El orden por `secuencia` es de inserción; eventos de agregados distintos confirmados
en transacciones concurrentes pueden despacharse en otro orden (el de un mismo agregado sí se conserva)."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Set
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from application.reloj import reloj_negocio
from domain.eventos_dominio import EventoDominio
from ..esquema_postgresql import metadata
from ..unidad_trabajo import PublicadorEnProceso
from . import codec_eventos as codec
from .conexion import AlmacenSQL, traducir
from .errores import ErrorDePersistencia, EventoNoRehidratable
from .unidad_trabajo_sql import IRegistradorDeEventos

PENDIENTE, PROCESADO, REVISION = "PENDIENTE", "PROCESADO", "REVISION"
ETIQUETAS = {PENDIENTE: "Pendiente", PROCESADO: "Procesado", REVISION: "Revisión"}        # las del Outbox en memoria
_OB = metadata.tables["outbox_evento"]
_RX = metadata.tables["outbox_reaccion"]


@dataclass
class RegistroPersistido:
    """Vista de una fila del Outbox con los mismos nombres que `RegistroOutbox` (memoria)."""
    secuencia: int
    evento_id: str
    tipo_evento: str
    estado: str                                   # «Pendiente» | «Procesado» | «Revisión»
    intentos: int
    error: str
    evento: Optional[EventoDominio]               # None si no pudo rehidratarse
    reacciones_procesadas: Set[str] = field(default_factory=set)
    error_de_rehidratacion: str = ""


def clave_de_reaccion(reaccion: Callable) -> str:
    """Identificador ESTABLE de una reacción: módulo, clase y método (no depende del orden de suscripción)."""
    propietario = getattr(reaccion, "__self__", None)
    if propietario is not None:
        return f"{type(propietario).__module__}.{type(propietario).__qualname__}.{reaccion.__func__.__name__}"
    return f"{reaccion.__module__}.{reaccion.__qualname__}"


class PublicadorEstable(PublicadorEnProceso):
    """Igual que el publicador en proceso, pero la clave de cada reacción es estable y no repetida por tipo de evento."""
    def suscribir(self, tipo_evento, reaccion):
        clave = clave_de_reaccion(reaccion)
        if any(clave_de_reaccion(r) == clave for r in self._suscripciones.get(tipo_evento, [])):
            raise ErrorDePersistencia(f"La reacción {clave} ya está suscrita al evento {tipo_evento.__name__}.")
        super().suscribir(tipo_evento, reaccion)

    def reacciones(self, evento):
        return [(clave_de_reaccion(r), r) for r in self._suscripciones.get(type(evento), [])]


class OutboxSQL(IRegistradorDeEventos):
    def __init__(self, almacen: AlmacenSQL):
        self._alm = almacen

    # -- registro (dentro de la transacción del agregado)
    def registrar(self, conexion: sa.Connection, eventos: Sequence[EventoDominio]) -> None:
        try:
            for e in eventos:                                       # uno a uno: `secuencia` conserva el orden de la lista
                conexion.execute(sa.insert(_OB), {
                    "evento_id": e.evento_id, "tipo_evento": type(e).__name__, "agregado_id": e.agregado_id,
                    "ocurrido_en": e.ocurrido_en, "datos": codec.codificar(e), "estado": PENDIENTE, "intentos": 0, "error": ""})
        except sa.exc.SQLAlchemyError as error:
            raise traducir(error) from error

    # -- consulta
    def registros(self, estado: Optional[str] = None) -> List[RegistroPersistido]:
        """Todos los registros (opcionalmente solo los de un estado: «PENDIENTE», «PROCESADO» o «REVISION»), por `secuencia`."""
        consulta = sa.select(_OB).order_by(_OB.c.secuencia)
        if estado:
            consulta = consulta.where(_OB.c.estado == estado)
        with self._alm.lectura() as con:
            filas = [dict(r) for r in con.execute(consulta).mappings()]
            hechas: Dict[str, Set[str]] = {}
            for r in con.execute(sa.select(_RX.c.evento_id, _RX.c.clave_reaccion)).all():
                hechas.setdefault(r[0], set()).add(r[1])
        salida = []
        for f in filas:
            try:
                evento, fallo = codec.decodificar(f["tipo_evento"], f["agregado_id"], f["ocurrido_en"], f["evento_id"], f["datos"]), ""
            except EventoNoRehidratable as e:
                evento, fallo = None, str(e)
            salida.append(RegistroPersistido(f["secuencia"], f["evento_id"], f["tipo_evento"], ETIQUETAS[f["estado"]], f["intentos"],
                                             f["error"], evento, hechas.get(f["evento_id"], set()), fallo))
        return salida

    def reabrir(self, evento_id: str) -> bool:
        """Operación manual: devuelve un evento en REVISION a PENDIENTE con 0 intentos (las reacciones ya hechas no se repiten)."""
        with self._alm.escritura() as con:
            r = con.execute(sa.update(_OB).where(sa.and_(_OB.c.evento_id == evento_id, _OB.c.estado == REVISION))
                            .values(estado=PENDIENTE, intentos=0, error=""))
            return r.rowcount == 1


class DespachadorOutboxSQL:
    def __init__(self, almacen: AlmacenSQL, publicador: PublicadorEnProceso, outbox: Optional[OutboxSQL] = None, max_intentos: int = 3,
                 reloj: Callable[[], datetime] = reloj_negocio):
        self.almacen, self.publicador, self.outbox = almacen, publicador, outbox or OutboxSQL(almacen)
        self.max_intentos, self._reloj = max_intentos, reloj

    def despachar(self) -> int:
        """Procesa los eventos pendientes (incluidos los que generen las reacciones). Devuelve cuántos terminaron PROCESADOS."""
        if self.almacen.conexion_activa is not None:
            raise ErrorDePersistencia("El despacho del Outbox no puede ejecutarse dentro de una transacción activa de este hilo.")
        procesados = 0
        while True:
            resultado = self._procesar_siguiente()
            if resultado is None:
                return procesados
            procesados += resultado

    def _procesar_siguiente(self) -> Optional[int]:
        """None si no hay eventos pendientes que reclamar; 1 si procesó uno; 0 si falló o pasó a revisión."""
        try:
            with self.almacen.motor.connect() as reclamo:
                tx = reclamo.begin()
                fila = reclamo.execute(sa.select(_OB).where(_OB.c.estado == PENDIENTE).order_by(_OB.c.secuencia).limit(1)
                                       .with_for_update(skip_locked=True, key_share=True)).mappings().first()
                if fila is None:
                    tx.rollback()
                    return None
                resultado = self._despachar_reclamado(reclamo, dict(fila))
                tx.commit()
                return resultado
        except ErrorDePersistencia:
            raise
        except sa.exc.SQLAlchemyError as e:
            raise traducir(e) from e

    def _despachar_reclamado(self, reclamo: sa.Connection, fila: dict) -> int:
        evento_id = fila["evento_id"]
        try:
            evento = codec.decodificar(fila["tipo_evento"], fila["agregado_id"], fila["ocurrido_en"], evento_id, fila["datos"])
        except EventoNoRehidratable as e:                       # controlado y observable: queda en REVISION con el motivo
            reclamo.execute(sa.update(_OB).where(_OB.c.evento_id == evento_id)
                            .values(estado=REVISION, intentos=fila["intentos"] + 1, error=str(e)))
            return 0
        hechas = set(reclamo.execute(sa.select(_RX.c.clave_reaccion).where(_RX.c.evento_id == evento_id)).scalars())
        fallo: Optional[BaseException] = None
        for clave, reaccion in self.publicador.reacciones(evento):
            if clave in hechas:
                continue                                         # no se repite una reacción ya ejecutada
            try:
                reaccion(evento)                                 # su propia transacción (ADR-004)
            except Exception as exc:                             # queda pendiente de reintento
                fallo = exc
                continue
            self._anotar(evento_id, clave)                       # transacción propia: sobrevive a una caída posterior
            hechas.add(clave)
        if fallo is None:
            reclamo.execute(sa.update(_OB).where(_OB.c.evento_id == evento_id).values(estado=PROCESADO))   # conserva el último error visto
            return 1
        intentos = fila["intentos"] + 1
        reclamo.execute(sa.update(_OB).where(_OB.c.evento_id == evento_id)
                        .values(intentos=intentos, error=str(fallo), estado=REVISION if intentos >= self.max_intentos else PENDIENTE))
        return 0

    def _anotar(self, evento_id: str, clave: str) -> None:
        with self.almacen.escritura() as con:
            con.execute(pg_insert(_RX).values(evento_id=evento_id, clave_reaccion=clave, procesada_en=self._reloj())
                        .on_conflict_do_nothing(index_elements=["evento_id", "clave_reaccion"]))
