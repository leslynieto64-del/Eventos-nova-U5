"""Línea de comandos del lector del paquete.

    python -m paquete_pia validar [--directorio RUTA]   valida integridad y estructura (código 0 si es válido)
    python -m paquete_pia hashes  [--directorio RUTA]   muestra el manifiesto calculado (no escribe archivos)

Requiere `src` en PYTHONPATH; desde la raíz del proyecto también puede usarse `python validar_paquete_pia.py`.
"""
from __future__ import annotations
import argparse
import sys
from typing import List, Optional

from .errores import ErrorPaquetePIA
from .esquema import DIRECTORIO_PREDETERMINADO
from .lector import leer_paquete
from .manifiesto import generar_manifiesto


def main(argumentos: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="paquete_pia", description="Validación del paquete 16_Eventos_Nova.")
    parser.add_argument("comando", nargs="?", default="validar", choices=("validar", "hashes"))
    parser.add_argument("--directorio", default=str(DIRECTORIO_PREDETERMINADO),
                        help="carpeta con los CSV y MANIFIESTO.sha256 (por omisión, datos/paquete_pia)")
    args = parser.parse_args(argumentos)

    if args.comando == "hashes":
        sys.stdout.write(generar_manifiesto(args.directorio))
        return 0
    try:
        paquete = leer_paquete(args.directorio)
    except ErrorPaquetePIA as e:
        print(f"RECHAZADO: {e}")
        return 1
    print(f"Paquete válido: {args.directorio}")
    print("Integridad SHA-256: correcta")
    for archivo, cantidad in paquete.conteos().items():
        print(f"  {archivo}: {cantidad} registros")
    return 0


if __name__ == "__main__":
    sys.exit(main())
