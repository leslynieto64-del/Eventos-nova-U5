"""`python -m ejecucion_paquete [--verificar]` (con `src` en la ruta). Ver también `ejecutar_paquete_pia.py`."""
from __future__ import annotations
import argparse
import sys

from .evidencias import DIRECTORIO_EVIDENCIAS, escribir_evidencias, verificar_evidencias


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ejecuta los casos y transiciones del paquete 16_Eventos_Nova (F2).")
    parser.add_argument("--verificar", action="store_true",
                        help="no escribe: regenera y compara con las evidencias guardadas")
    args = parser.parse_args(argv)
    if args.verificar:
        problemas = verificar_evidencias()
        for p in problemas:
            print(f"DIFERENCIA: {p}")
        print("Evidencias F2 reproducibles." if not problemas else f"{len(problemas)} archivo(s) difieren.")
        return 1 if problemas else 0
    for ruta in escribir_evidencias():
        print(f"Escrito: {ruta.relative_to(DIRECTORIO_EVIDENCIAS.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
