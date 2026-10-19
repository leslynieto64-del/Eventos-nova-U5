"""Repositorios en memoria. Respetan el contrato de las interfaces (H-05): agregado completo, lecturas sin efectos.
guardar() solo prepara el cambio; el UnitOfWork lo hace visible al confirmar."""
from __future__ import annotations
import copy
from application import puertos as P


class _Almacen:
    def __init__(self):
        self.datos = {}


class _RepoBase:
    def __init__(self, uow):
        self._alm = _Almacen()
        self._uow = uow
        uow.adjuntar(self)
        self._pendientes = {}

    # integración con el UnitOfWork
    def _confirmar(self):
        self._alm.datos.update(self._pendientes); self._pendientes = {}

    def _revertir(self):
        self._pendientes = {}

    def obtener_por_id(self, id_):
        a = self._alm.datos.get(id_)
        return copy.deepcopy(a) if a else None          # copia: el agregado no cambia hasta confirmar

    def guardar(self, agregado):
        guardado = copy.deepcopy(agregado)
        guardado._eventos = []                         # los eventos viajan por el UnitOfWork/Outbox, no por el almacén
        self._pendientes[agregado.id] = guardado

    def _todos(self):
        return [copy.deepcopy(a) for a in self._alm.datos.values()]


class PropuestaRepositoryMemoria(_RepoBase, P.IPropuestaRepository):
    def listar_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id]


class ContratoRepositoryMemoria(_RepoBase, P.IContratoRepository):
    def listar_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id]


class EventoRepositoryMemoria(_RepoBase, P.IEventoRepository):
    pass


class _RepoSolicitudes(_RepoBase):
    def listar_pendientes_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id and a.pendiente]


class SolicitudCambioRepositoryMemoria(_RepoSolicitudes, P.ISolicitudCambioRepository): pass
class SolicitudServicioAdicionalRepositoryMemoria(_RepoSolicitudes, P.ISolicitudServicioAdicionalRepository): pass
class SustitucionProveedorRepositoryMemoria(_RepoSolicitudes, P.ISustitucionProveedorRepository): pass


class EstadoCuentaRepositoryMemoria(_RepoBase, P.IEstadoCuentaRepository):
    def obtener_por_contrato_id(self, contrato_id):
        return next((a for a in self._todos() if a.contrato_id == contrato_id), None)

    def listar_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id]
