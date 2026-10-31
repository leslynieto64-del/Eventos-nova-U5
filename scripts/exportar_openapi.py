"""Exporta la especificación OpenAPI de la API a docs/api/openapi.json (estructura mínima del PIA: docs/api/).

    python scripts/exportar_openapi.py              # escribe el archivo
    python scripts/exportar_openapi.py --comprobar  # sale con 1 si el archivo no está al día

La especificación se genera desde el código (FastAPI) en modo memoria, sin base de datos ni variables de entorno."""
import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
DESTINO = RAIZ / "docs" / "api" / "openapi.json"


def generar() -> str:
    os.environ.pop("EVENTOSNOVA_PERSISTENCIA", None)
    os.environ.pop("EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO", None)
    from api.main import crear_app
    from infrastructure.composicion import construir
    return json.dumps(crear_app(construir).openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comprobar", action="store_true")
    args = parser.parse_args()
    texto = generar()
    if args.comprobar:
        actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if actual != texto:
            print("docs/api/openapi.json no está al día: ejecute scripts/exportar_openapi.py", file=sys.stderr)
            return 1
        print("OpenAPI al día.")
        return 0
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
