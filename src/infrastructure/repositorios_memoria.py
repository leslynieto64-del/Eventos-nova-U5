"""Repositorios en memoria. Respetan el contrato de las interfaces (H-05): agregado completo, lecturas sin efectos.
guardar() solo prepara el cambio; el UnitOfWork lo hace visible al confirmar."""
from __future__ import annotations
import copy
import threading
from application import puertos as P
from domain.valores import EstadoEvento


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

    def listar_todos(self):                        # lectura: copias de todos los agregados guardados
        return self._todos()


class PropuestaRepositoryMemoria(_RepoBase, P.IPropuestaRepository):
    def listar_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id]


class ContratoRepositoryMemoria(_RepoBase, P.IContratoRepository):
    def listar_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id]


class EventoRepositoryMemoria(_RepoBase, P.IEventoRepository):
    def listar_con_fecha_vencida(self, ahora):
        return sorted((e for e in self._todos() if e.estado in (EstadoEvento.EN_GESTION, EstadoEvento.EN_ORGANIZACION)
                       and e.datos.fecha_hora <= ahora), key=lambda e: e.id)


class _RepoSolicitudes(_RepoBase):
    def listar_pendientes_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id and a.pendiente]

    def listar_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id]

    def listar_todas(self):
        return self._todos()


class SolicitudCambioRepositoryMemoria(_RepoSolicitudes, P.ISolicitudCambioRepository): pass
class SolicitudServicioAdicionalRepositoryMemoria(_RepoSolicitudes, P.ISolicitudServicioAdicionalRepository): pass
class SustitucionProveedorRepositoryMemoria(_RepoSolicitudes, P.ISustitucionProveedorRepository): pass


class EstadoCuentaRepositoryMemoria(_RepoBase, P.IEstadoCuentaRepository):
    def obtener_por_contrato_id(self, contrato_id):
        return next((a for a in self._todos() if a.contrato_id == contrato_id), None)

    def listar_por_evento_id(self, evento_id):
        return [a for a in self._todos() if a.evento_id == evento_id]


class ProveedorRepositoryMemoria(P.IProveedorRepository):
    """Catálogo de proveedores en memoria. No usa la unidad de trabajo: es un registro de referencia, sin agregado ni eventos."""
    def __init__(self):
        self._alm = _Almacen()                  # mismo contrato de inspección que los demás repositorios (`_alm.datos`)
        self._por_id = self._alm.datos
        self._cerrojo = threading.Lock()

    def guardar(self, proveedor):
        with self._cerrojo:
            if proveedor.proveedor_id in self._por_id or any(
                    p.nombre_normalizado == proveedor.nombre_normalizado for p in self._por_id.values()):
                return False
            self._por_id[proveedor.proveedor_id] = proveedor
            return True

    def obtener_por_id(self, proveedor_id):
        return self._por_id.get(proveedor_id)

    def listar_todos(self):
        return sorted(self._por_id.values(), key=lambda p: (p.nombre_normalizado, p.proveedor_id))
