"""Composición PERSISTENTE: los mismos servicios, reacciones, consultas y comandos que `construir()`, sobre repositorios SQL,
`UnitOfWorkSQL` y el Outbox de PostgreSQL. `construir()` (memoria) no cambia.

    contenedor = construir_persistente()                  # lee DATABASE_URL (o .env) y comprueba el esquema
    contenedor = construir_persistente(url="postgresql+psycopg://...", disponibilidad=...)

Al construirse comprueba que la base de datos responde y que las migraciones necesarias están aplicadas (si no, lanza
`ErrorDeConexion` o `EsquemaDesactualizado`; no migra por su cuenta). El contenedor expone, además de la estructura común
(`repos`, `servicios`, `uow`, `despachador`, `notificador`, `queries`, `commands`): `almacen`, `outbox`, `modo`, `comprobar_base_de_datos()`
y `cerrar()`.

Colaboradores EXTERNOS (disponibilidad de proveedores, notificaciones, verificación de pagos, ejecución de devoluciones): siguen
siendo los adaptadores simulados de `infrastructure.adaptadores`; no forman parte de la persistencia."""
from __future__ import annotations
from types import SimpleNamespace
from typing import Optional
import sqlalchemy as sa
from ..composicion import ensamblar
from . import configuracion as C
from . import repositorios_sql as S
from .conexion import AlmacenSQL, crear_motor
from .errores import ErrorDeConexion, ErrorDePersistencia
from .outbox_sql import DespachadorOutboxSQL, OutboxSQL, PublicadorEstable
from .preparacion import exigir_esquema_al_dia
from .unidad_trabajo_sql import UnitOfWorkSQL


def construir_persistente(url: Optional[str] = None, motor: Optional[sa.Engine] = None, disponibilidad=None, max_intentos: int = 3,
                          verificar_esquema: bool = True, **opciones_motor) -> SimpleNamespace:
    """Contenedor persistente. Si se pasa `motor` no se cierra al final (lo gestiona quien lo creó)."""
    propio = motor is None
    if motor is None:
        url = url or C.url_desarrollo()
        if not url:
            raise ErrorDePersistencia("Defina DATABASE_URL (vea .env.example) para usar la persistencia en PostgreSQL.")
        motor = crear_motor(url, **opciones_motor)
    try:
        with motor.connect() as con:
            con.execute(sa.text("select 1"))
    except sa.exc.SQLAlchemyError as e:
        if propio:
            motor.dispose()
        raise ErrorDeConexion(f"No se pudo conectar con la base de datos: {str(getattr(e, 'orig', e)).splitlines()[0]}") from e
    if verificar_esquema:
        try:
            exigir_esquema_al_dia(motor)
        except Exception:
            if propio:
                motor.dispose()
            raise
    almacen = AlmacenSQL(motor)
    outbox = OutboxSQL(almacen)
    uow = UnitOfWorkSQL(almacen, outbox)
    repos = SimpleNamespace(
        propuestas=S.PropuestaRepositorySQL(almacen), contratos=S.ContratoRepositorySQL(almacen), eventos=S.EventoRepositorySQL(almacen),
        cambios=S.SolicitudCambioRepositorySQL(almacen), adicionales=S.SolicitudServicioAdicionalRepositorySQL(almacen),
        sustituciones=S.SustitucionProveedorRepositorySQL(almacen), estados_cuenta=S.EstadoCuentaRepositorySQL(almacen),
        proveedores=S.ProveedorRepositorySQL(almacen))
    pub = PublicadorEstable()
    contenedor = ensamblar(repos, uow, pub, DespachadorOutboxSQL(almacen, pub, outbox, max_intentos), disponibilidad, S.AlmacenSeguridadSQL(almacen))
    contenedor.almacen, contenedor.outbox, contenedor.motor, contenedor.modo = almacen, outbox, motor, C.MODO_POSTGRESQL

    def comprobar_base_de_datos() -> None:
        with motor.connect() as con:
            con.execute(sa.text("select 1"))

    def cerrar() -> None:
        if propio:
            motor.dispose()
    contenedor.comprobar_base_de_datos, contenedor.cerrar = comprobar_base_de_datos, cerrar
    return contenedor


def construir_persistente_desde_entorno() -> SimpleNamespace:
    """Fábrica sin argumentos para `crear_app` (usa DATABASE_URL del entorno o de `.env`)."""
    from ..adaptadores import disponibilidad_desde_entorno
    return construir_persistente(disponibilidad=disponibilidad_desde_entorno())
