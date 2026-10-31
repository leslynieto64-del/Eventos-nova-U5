"""Prepara la base de datos de PRUEBAS (idempotente y no destructiva).

    python scripts/preparar_base_de_pruebas.py

Lee TEST_DATABASE_URL del entorno o de `.env`. Crea la base SOLO si no existe, aplica las migraciones de Alembic y no borra nada.
Se niega a actuar si la base no es local o su nombre no termina en «_test». No imprime credenciales."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from infrastructure.persistencia import configuracion as C                       # noqa: E402
from infrastructure.persistencia.preparacion import asegurar_base_de_pruebas      # noqa: E402


def main() -> int:
    url = C.url_pruebas()
    if not url:
        print("Defina TEST_DATABASE_URL (vea .env.example).", file=sys.stderr)
        return 2
    resumen = asegurar_base_de_pruebas(url)
    print("Base de pruebas lista:", {k: resumen[k] for k in ("host", "puerto", "base", "usuario", "creada")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
