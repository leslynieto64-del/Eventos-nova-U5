"""UnitOfWork en memoria con Outbox (propuesta de la Etapa 5, versión ilustrativa).
confirmar(): hace visibles los cambios y guarda los Domain Events en el Outbox en el mismo paso.
El despachador entrega cada evento después del commit, registra las parejas (evento, reacción) ya procesadas
y solo reintenta las reacciones que fallaron."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List
from application.puertos import IUnitOfWork, IPublicadorEventosDominio
from domain.eventos_dominio import EventoDominio


@dataclass
class RegistroOutbox:
    evento: EventoDominio
    estado: str = "Pendiente"          # Pendiente | Procesado | Revisión
    intentos: int = 0
    error: str = ""
    reacciones_procesadas: set = field(default_factory=set)   # parejas (evento, reacción) ya ejecutadas


class UnitOfWorkMemoria(IUnitOfWork):
    def __init__(self):
        self._repos = []
        self._agregados = []
        self.outbox: List[RegistroOutbox] = []
        self._nivel = 0

    def adjuntar(self, repo):
        self._repos.append(repo)

    def iniciar(self):
        self._nivel += 1
        self._agregados = []

    def registrar(self, *agregados):
        self._agregados.extend(a for a in agregados if a is not None)

    def confirmar(self):
        eventos = [e for a in self._agregados for e in a.extraer_eventos()]
        for r in self._repos:
            r._confirmar()
        self.outbox.extend(RegistroOutbox(e) for e in eventos)      # mismo «commit» que el agregado
        self._agregados, self._nivel = [], self._nivel - 1

    def revertir(self):
        for r in self._repos:
            r._revertir()
        for a in self._agregados:
            a.extraer_eventos()                                       # se descartan: no se publican
        self._agregados, self._nivel = [], self._nivel - 1


class PublicadorEnProceso(IPublicadorEventosDominio):
    def __init__(self):
        self._suscripciones: Dict[type, List[Callable]] = {}

    def suscribir(self, tipo_evento, reaccion):
        self._suscripciones.setdefault(tipo_evento, []).append(reaccion)

    def reacciones(self, evento):
        """Pares (clave, reacción) suscritos al tipo del evento; la clave identifica la reacción en el Outbox."""
        return [(getattr(r, '__qualname__', repr(r)) + f"#{i}", r) for i, r in enumerate(self._suscripciones.get(type(evento), []))]

    def publicar(self, evento):
        for _, r in self.reacciones(evento):
            r(evento)


class DespachadorOutbox:
    """Lee los registros pendientes, invoca las reacciones y los marca como procesados."""

    def __init__(self, uow: UnitOfWorkMemoria, publicador: PublicadorEnProceso, max_intentos: int = 3):
        self.uow, self.publicador, self.max_intentos = uow, publicador, max_intentos

    def despachar(self) -> int:
        procesados = 0
        while True:
            pendientes = [r for r in self.uow.outbox if r.estado == "Pendiente"]
            if not pendientes:
                return procesados
            for reg in pendientes:
                fallo = None
                for clave, reaccion in self.publicador.reacciones(reg.evento):
                    if clave in reg.reacciones_procesadas:
                        continue                                      # no se repite una reacción ya ejecutada
                    try:
                        reaccion(reg.evento)
                        reg.reacciones_procesadas.add(clave)
                    except Exception as exc:                          # queda pendiente de reintento
                        fallo = exc
                if fallo is None:
                    reg.estado = "Procesado"; procesados += 1
                else:
                    reg.intentos += 1; reg.error = str(fallo)
                    if reg.intentos >= self.max_intentos:
                        reg.estado = "Revisión"
