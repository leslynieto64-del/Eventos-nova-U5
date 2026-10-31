"""Crea la PRIMERA cuenta de administrador de una base de datos, sin credenciales predeterminadas.

    python scripts/crear_administrador.py --base eventosnova_manual_test --correo admin@su-organizacion.example --nombre "Nombre Apellido"

- La contraseña se pide por teclado (sin eco, dos veces) o, para automatizar, se lee de la variable de entorno que indique
  `--contrasena-desde-entorno NOMBRE` (nunca como argumento de la línea de comandos, que queda en el historial).
- `--base` es OBLIGATORIO: el script no elige una base por usted. Usa el servidor y las credenciales de DATABASE_URL (.env) con esa base.
  La base debe estar migrada a la revisión 0006 (`alembic upgrade head`).
- Solo crea un administrador si todavía no hay ninguno (use `--ya-hay-administradores` solo si sabe lo que hace). Los demás usuarios los crea un
  administrador desde la interfaz o con `POST /usuarios`.
- No imprime ni guarda la contraseña; en la base solo queda su hash Argon2id."""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sqlalchemy as sa                                                      # noqa: E402
from application.seguridad import ADMINISTRADOR, ConfiguracionSeguridad, ServicioSeguridad     # noqa: E402
from infrastructure.persistencia import configuracion as C                   # noqa: E402
from infrastructure.persistencia.conexion import AlmacenSQL, crear_motor     # noqa: E402
from infrastructure.persistencia.repositorios_sql import AlmacenSeguridadSQL  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="nombre de la base de datos (obligatorio)")
    ap.add_argument("--correo", required=True)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--contrasena-desde-entorno", metavar="VARIABLE")
    ap.add_argument("--ya-hay-administradores", action="store_true", help="permite crear otro administrador aunque ya exista uno")
    a = ap.parse_args()

    url = C.url_con_base(C.normalizar_url(C.url_desarrollo() or ""), a.base) if C.url_desarrollo() else None
    if not url:
        print("Defina DATABASE_URL (vea .env.example).", file=sys.stderr)
        return 2
    d = C.descripcion_segura(url)
    if d["host"] not in C.HOSTS_LOCALES:
        print("Por seguridad el script solo trabaja con un servidor local.", file=sys.stderr)
        return 2
    print(f"Base de datos: {d['base']} en {d['host']}:{d['puerto']}")
    motor = crear_motor(url)
    try:
        with motor.connect() as con:
            revision = con.execute(sa.text("select version_num from alembic_version")).scalar()
        if revision is None or revision < "0006":
            print(f"La base está en la revisión {revision}; se necesita 0006 o posterior (alembic upgrade head).", file=sys.stderr)
            return 2
        almacen = AlmacenSeguridadSQL(AlmacenSQL(motor))
        if not a.ya_hay_administradores and any(u.rol == ADMINISTRADOR for u in almacen.listar_usuarios()):
            print("Ya existe un administrador. Cree las demás cuentas desde la aplicación (o use --ya-hay-administradores).", file=sys.stderr)
            return 1
        if a.contrasena_desde_entorno:
            contrasena = os.environ.get(a.contrasena_desde_entorno, "")
        else:
            contrasena = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
            if contrasena != getpass.getpass("Repita la contraseña: "):
                print("Las contraseñas no coinciden.", file=sys.stderr)
                return 1
        servicio = ServicioSeguridad(almacen, ConfiguracionSeguridad.desactivada())
        try:
            usuario = servicio.crear_usuario(a.correo, a.nombre, ADMINISTRADOR, contrasena)
        except ValueError as e:
            print(f"No se creó la cuenta: {e}", file=sys.stderr)
            return 1
        print(f"Administrador creado: {usuario.correo} ({usuario.usuario_id}). Inicie sesión en /app/.")
        return 0
    finally:
        motor.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
