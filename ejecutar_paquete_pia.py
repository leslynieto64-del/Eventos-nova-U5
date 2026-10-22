"""Atajo para ejecutar el paquete oficial (Etapa F2) desde la raíz del proyecto, sin configurar PYTHONPATH.

    python ejecutar_paquete_pia.py              ejecuta los 120 casos y las 20 transiciones y escribe tests/evidencias/f2/
    python ejecutar_paquete_pia.py --verificar  no escribe: regenera y compara con las evidencias guardadas
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ejecucion_paquete.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
