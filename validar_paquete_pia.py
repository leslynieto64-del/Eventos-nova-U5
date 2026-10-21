"""Atajo para validar el paquete de datos desde la raíz del proyecto, sin configurar PYTHONPATH.

    python validar_paquete_pia.py            valida datos/paquete_pia
    python validar_paquete_pia.py hashes     muestra el manifiesto calculado
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from paquete_pia.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
