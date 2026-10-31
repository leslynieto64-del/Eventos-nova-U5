"""Repositorios SQL (SQLAlchemy Core + Psycopg 3) que implementan las interfaces de `application.puertos`.

Contrato (el mismo que los repositorios en memoria): `obtener_por_id` devuelve el agregado COMPLETO o None; `guardar` persiste el
agregado completo; los `listar_*` son de lectura. No hay métodos de borrado porque el dominio no los necesita.

Estrategia de guardado: *upsert* por clave primaria de la raíz y de cada fila hija (`INSERT ... ON CONFLICT DO UPDATE`), nunca
«borrar y reinsertar»: así no se violan las claves foráneas compuestas (p. ej. `pago` → `obligacion_pago`) y un guardado repetido
es idempotente. El dominio no elimina elementos de sus colecciones; por eso no se borran filas hijas.

`guardar` no extrae ni descarta los Domain Events del agregado: los recoge la unidad de trabajo al confirmar (Outbox, ADR-004).

Sin una unidad de trabajo activa, cada operación usa su propia transacción. Dentro de una, las lecturas ven los cambios propios."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from application import puertos as P
from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor
from domain.evento import Evento
from domain.valores import EstadoEvento
from domain.contrato import Contrato
from domain.propuesta import Propuesta
from domain.proveedor import Proveedor
from application.seguridad import IAlmacenSeguridad, Intento, Sesion, Usuario
from domain.estado_cuenta import EstadoCuenta
from ..esquema_postgresql import metadata
from .conexion import AlmacenSQL
from .errores import ConflictoDeConcurrencia
from .mapeadores import Filas, Mapeador, MapeadorContrato, MapeadorEstadoCuenta, MapeadorEvento, MapeadorPropuesta, \
    MapeadorSolicitudCambio, MapeadorSolicitudServicioAdicional, MapeadorSustitucionProveedor


def _upsert(tabla: sa.Table):
    pk = [c.name for c in tabla.primary_key.columns]
    resto = [c.name for c in tabla.columns if c.name not in pk]
    ins = pg_insert(tabla)
    if not resto:                                           # tabla cuya clave primaria es toda la fila
        return ins.on_conflict_do_nothing(index_elements=pk)
    return ins.on_conflict_do_update(index_elements=pk, set_={c: ins.excluded[c] for c in resto})


class _RepositorioSQL:
    mapeador: Mapeador

    def __init__(self, almacen: AlmacenSQL):
        self._alm = almacen
        self._raiz = metadata.tables[self.mapeador.tabla_raiz]
        self._id = self._raiz.c[self.mapeador.columna_id]

    # -- lectura
    def _cargar(self, condicion=None) -> list:
        """Agregados cuya raíz cumple `condicion`, ordenados por identificador, con todas sus filas hijas."""
        consulta = sa.select(self._raiz).order_by(self._id)
        if condicion is not None:
            consulta = consulta.where(condicion)
        with self._alm.lectura() as con:
            raices = [dict(r) for r in con.execute(consulta).mappings()]
            if not raices:
                return []
            ids = [r[self.mapeador.columna_id] for r in raices]
            hijas: Dict[str, Dict[object, List[dict]]] = {}
            for tabla, fk, orden in self.mapeador.hijas:
                t = metadata.tables[tabla]
                filas = con.execute(sa.select(t).where(t.c[fk].in_(ids)).order_by(t.c[fk], *[t.c[o] for o in orden])).mappings()
                agrupadas: Dict[object, List[dict]] = defaultdict(list)
                for fila in filas:
                    agrupadas[fila[fk]].append(dict(fila))
                hijas[tabla] = agrupadas
        agregados = []
        for r in raices:
            agregado = self.mapeador.desde_filas(Filas(r, {t: hijas[t].get(r[self.mapeador.columna_id], []) for t in hijas}))
            agregado._version = r["version"]                  # control de concurrencia optimista: la versión que se leyó
            agregados.append(agregado)
        return agregados

    def obtener_por_id(self, id_):
        encontrados = self._cargar(self._id == id_)
        return encontrados[0] if encontrados else None

    # -- escritura
    def guardar(self, agregado) -> None:
        """Control de concurrencia optimista sobre la raíz (las filas hijas se protegen con ella):
        - agregado nuevo (nunca guardado ni leído): `INSERT`; si ya existe una fila con ese id, ConflictoDeConcurrencia, así que
          un identificador repetido jamás sobrescribe a otro agregado;
        - agregado leído: `UPDATE ... WHERE id = :id AND version = :leída`; si otra transacción lo cambió antes (o se borró),
          0 filas afectadas → ConflictoDeConcurrencia y la operación entera se revierte. Dos escritores simultáneos del mismo
          agregado nunca se pisan: el segundo espera a que termine el primero (bloqueo de fila) y entonces falla en vez de perder
          la actualización. Guardar dos veces el mismo objeto en una operación es válido (la versión avanza en el objeto)."""
        filas = self.mapeador.a_filas(agregado)
        identificador = filas.raiz[self.mapeador.columna_id]
        leida = agregado._version
        with self._alm.escritura() as con:
            if leida is None:
                insertadas = len(con.execute(pg_insert(self._raiz).values({**filas.raiz, "version": 0})
                                             .on_conflict_do_nothing(index_elements=[self._id]).returning(self._id)).all())
                nueva = 0
            else:
                valores = {k: v for k, v in filas.raiz.items() if k != self.mapeador.columna_id}
                insertadas = len(con.execute(sa.update(self._raiz).where(self._id == identificador, self._raiz.c.version == leida)
                                             .values(**valores, version=leida + 1).returning(self._id)).all())
                nueva = leida + 1
            if insertadas != 1:
                raise ConflictoDeConcurrencia(
                    f"El agregado {self.mapeador.tabla_raiz} {identificador} "
                    + ("ya existe." if leida is None else f"cambió desde que se leyó (versión {leida}) o ya no existe."),
                    self.mapeador.tabla_raiz, identificador)
            for tabla, _, _ in self.mapeador.hijas:
                if filas.hijas.get(tabla):
                    con.execute(_upsert(metadata.tables[tabla]), filas.hijas[tabla])
        agregado._version = nueva


class PropuestaRepositorySQL(_RepositorioSQL, P.IPropuestaRepository):
    mapeador = MapeadorPropuesta()

    def listar_por_evento_id(self, evento_id: str) -> List[Propuesta]:
        return self._cargar(self._raiz.c.evento_id == evento_id)


class ContratoRepositorySQL(_RepositorioSQL, P.IContratoRepository):
    mapeador = MapeadorContrato()

    def listar_por_evento_id(self, evento_id: str) -> List[Contrato]:
        return self._cargar(self._raiz.c.evento_id == evento_id)


class EventoRepositorySQL(_RepositorioSQL, P.IEventoRepository):
    mapeador = MapeadorEvento()

    def listar_todos(self) -> List[Evento]:
        return self._cargar()

    def listar_con_fecha_vencida(self, ahora: datetime) -> List[Evento]:
        """C-01, CA-109, CA-110: usa el índice ix_evento_fecha_hora; T inclusive."""
        abiertos = [EstadoEvento.EN_GESTION.name, EstadoEvento.EN_ORGANIZACION.name]
        return self._cargar(sa.and_(self._raiz.c.fecha_hora <= ahora, self._raiz.c.estado.in_(abiertos)))


class _RepositorioSolicitudesSQL(_RepositorioSQL):
    clase = None

    def listar_por_evento_id(self, evento_id: str):
        return self._cargar(self._raiz.c.evento_id == evento_id)

    def listar_todas(self):
        return self._cargar()

    def listar_pendientes_por_evento_id(self, evento_id: str):
        finales = [e.name for e in self.clase.FINALES]       # «pendiente» = no está en un estado final (`_SolicitudBase.pendiente`)
        return self._cargar(sa.and_(self._raiz.c.evento_id == evento_id, self._raiz.c.estado.notin_(finales)))


class SolicitudCambioRepositorySQL(_RepositorioSolicitudesSQL, P.ISolicitudCambioRepository):
    mapeador, clase = MapeadorSolicitudCambio(), SolicitudCambio


class SolicitudServicioAdicionalRepositorySQL(_RepositorioSolicitudesSQL, P.ISolicitudServicioAdicionalRepository):
    mapeador, clase = MapeadorSolicitudServicioAdicional(), SolicitudServicioAdicional


class SustitucionProveedorRepositorySQL(_RepositorioSolicitudesSQL, P.ISustitucionProveedorRepository):
    mapeador, clase = MapeadorSustitucionProveedor(), SustitucionProveedor


class EstadoCuentaRepositorySQL(_RepositorioSQL, P.IEstadoCuentaRepository):
    mapeador = MapeadorEstadoCuenta()

    def obtener_por_contrato_id(self, contrato_id: str) -> Optional[EstadoCuenta]:
        encontrados = self._cargar(self._raiz.c.contrato_id == contrato_id)
        return encontrados[0] if encontrados else None

    def listar_por_evento_id(self, evento_id: str) -> List[EstadoCuenta]:
        return self._cargar(self._raiz.c.evento_id == evento_id)

    def listar_todos(self) -> List[EstadoCuenta]:
        return self._cargar()


class ProveedorRepositorySQL(P.IProveedorRepository):
    """Catálogo de proveedores en la tabla `proveedor`. Registro de referencia: sin versión, unidad de trabajo ni Outbox; cada
    operación usa su propia transacción. La unicidad (identificador y nombre normalizado) la garantiza la base de datos."""
    def __init__(self, almacen: AlmacenSQL):
        self._alm = almacen
        self._t = metadata.tables["proveedor"]

    @staticmethod
    def _desde(fila) -> Proveedor:
        return Proveedor(fila["proveedor_id"], fila["nombre"], tuple(fila["servicios"]), fila["contacto"], fila["registrado_en"])

    def guardar(self, proveedor: Proveedor) -> bool:
        valores = {"proveedor_id": proveedor.proveedor_id, "nombre": proveedor.nombre, "nombre_normalizado": proveedor.nombre_normalizado,
                   "servicios": list(proveedor.servicios), "contacto": proveedor.contacto, "registrado_en": proveedor.registrado_en}
        with self._alm.escritura() as con:
            return len(con.execute(pg_insert(self._t).values(valores).on_conflict_do_nothing().returning(self._t.c.proveedor_id)).all()) == 1

    def obtener_por_id(self, proveedor_id: str) -> Optional[Proveedor]:
        with self._alm.lectura() as con:
            fila = con.execute(sa.select(self._t).where(self._t.c.proveedor_id == proveedor_id)).mappings().first()
        return self._desde(fila) if fila else None

    def listar_todos(self) -> List[Proveedor]:
        with self._alm.lectura() as con:
            filas = con.execute(sa.select(self._t).order_by(self._t.c.nombre_normalizado, self._t.c.proveedor_id)).mappings().all()
        return [self._desde(f) for f in filas]


class AlmacenSeguridadSQL(IAlmacenSeguridad):
    """Cuentas, sesiones e intentos de acceso en PostgreSQL (tablas `usuario`, `sesion`, `intento_acceso`). Sin unidad de trabajo ni Outbox:
    cada operación usa su propia transacción. El correo es único en la base de datos (un alta simultánea nunca crea dos cuentas)."""
    def __init__(self, almacen: AlmacenSQL):
        self._alm = almacen
        self._u, self._s, self._i = (metadata.tables[n] for n in ("usuario", "sesion", "intento_acceso"))

    @staticmethod
    def _usuario(f) -> Usuario:
        return Usuario(f["usuario_id"], f["correo"], f["nombre"], f["rol"], f["contrasena_hash"], f["activo"], f["proveedor_id"],
                       f["creado_en"], f["ultimo_acceso"])

    @staticmethod
    def _valores(u: Usuario) -> dict:
        return {"usuario_id": u.usuario_id, "correo": u.correo, "nombre": u.nombre, "rol": u.rol, "contrasena_hash": u.contrasena_hash,
                "activo": u.activo, "proveedor_id": u.proveedor_id, "creado_en": u.creado_en, "ultimo_acceso": u.ultimo_acceso}

    def crear_usuario(self, usuario: Usuario) -> bool:
        with self._alm.escritura() as con:
            return len(con.execute(pg_insert(self._u).values(self._valores(usuario)).on_conflict_do_nothing().returning(self._u.c.usuario_id)).all()) == 1

    def _uno(self, condicion) -> Optional[Usuario]:
        with self._alm.lectura() as con:
            f = con.execute(sa.select(self._u).where(condicion)).mappings().first()
        return self._usuario(f) if f else None

    def obtener_usuario(self, usuario_id: str) -> Optional[Usuario]:
        return self._uno(self._u.c.usuario_id == usuario_id)

    def obtener_usuario_por_correo(self, correo: str) -> Optional[Usuario]:
        return self._uno(self._u.c.correo == correo)

    def listar_usuarios(self) -> List[Usuario]:
        with self._alm.lectura() as con:
            return [self._usuario(f) for f in con.execute(sa.select(self._u).order_by(self._u.c.correo, self._u.c.usuario_id)).mappings()]

    def actualizar_usuario(self, usuario: Usuario) -> None:
        valores = self._valores(usuario)
        with self._alm.escritura() as con:
            con.execute(sa.update(self._u).where(self._u.c.usuario_id == usuario.usuario_id).values(**{k: v for k, v in valores.items() if k != "usuario_id"}))

    @staticmethod
    def _sesion(f) -> Sesion:
        return Sesion(f["sesion_hash"], f["usuario_id"], f["csrf"], f["creada_en"], f["ultima_actividad"], f["expira_en"], f["revocada_en"])

    def crear_sesion(self, sesion: Sesion) -> None:
        with self._alm.escritura() as con:
            con.execute(sa.insert(self._s).values(sesion_hash=sesion.sesion_hash, usuario_id=sesion.usuario_id, csrf=sesion.csrf, creada_en=sesion.creada_en,
                                                  ultima_actividad=sesion.ultima_actividad, expira_en=sesion.expira_en, revocada_en=sesion.revocada_en))

    def obtener_sesion(self, sesion_hash: str) -> Optional[Sesion]:
        with self._alm.lectura() as con:
            f = con.execute(sa.select(self._s).where(self._s.c.sesion_hash == sesion_hash)).mappings().first()
        return self._sesion(f) if f else None

    def actualizar_sesion(self, sesion: Sesion) -> None:
        with self._alm.escritura() as con:
            con.execute(sa.update(self._s).where(self._s.c.sesion_hash == sesion.sesion_hash)
                        .values(ultima_actividad=sesion.ultima_actividad, revocada_en=sesion.revocada_en))

    def revocar_sesiones_de(self, usuario_id: str, cuando: datetime) -> int:
        with self._alm.escritura() as con:
            return con.execute(sa.update(self._s).where(self._s.c.usuario_id == usuario_id, self._s.c.revocada_en.is_(None)).values(revocada_en=cuando)).rowcount

    def obtener_intento(self, clave: str) -> Optional[Intento]:
        with self._alm.lectura() as con:
            f = con.execute(sa.select(self._i).where(self._i.c.clave == clave)).mappings().first()
        return Intento(f["clave"], f["fallos"], f["primer_fallo"], f["bloqueado_hasta"]) if f else None

    def guardar_intento(self, intento: Intento) -> None:
        with self._alm.escritura() as con:
            ins = pg_insert(self._i).values(clave=intento.clave, fallos=intento.fallos, primer_fallo=intento.primer_fallo, bloqueado_hasta=intento.bloqueado_hasta)
            con.execute(ins.on_conflict_do_update(index_elements=["clave"], set_={"fallos": ins.excluded.fallos, "primer_fallo": ins.excluded.primer_fallo,
                                                                                  "bloqueado_hasta": ins.excluded.bloqueado_hasta}))

    def borrar_intento(self, clave: str) -> None:
        with self._alm.escritura() as con:
            con.execute(sa.delete(self._i).where(self._i.c.clave == clave))
