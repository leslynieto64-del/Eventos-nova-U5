"""Trabajador de despacho del Outbox (proceso aparte, ejecutable).

    python -m infrastructure.persistencia.trabajador_outbox            # bucle continuo (Docker Compose: servicio `worker`)
    python -m infrastructure.persistencia.trabajador_outbox --una-vez  # despacha lo pendiente y termina

Lee DATABASE_URL del entorno o de `.env`, comprueba la conexión y que las migraciones estén aplicadas, y despacha los eventos
pendientes cada `--intervalo` segundos. Se puede ejecutar más de un trabajador a la vez: el reclamo con `SKIP LOCKED` evita que dos
procesen el mismo evento. Un fallo en un ciclo se registra y el bucle continúa; SIGINT/SIGTERM lo detienen de forma ordenada."""
from __future__ import annotations
import argparse
import logging
import signal
import sys
import threading
from datetime import datetime
from typing import Callable, Optional
from application.reloj import reloj_negocio
from .composicion_persistente import construir_persistente

registro = logging.getLogger("eventosnova.trabajador")


def ejecutar(contenedor, intervalo: float = 2.0, una_vez: bool = False, detener: Optional[threading.Event] = None,
             reloj: Callable[[], datetime] = reloj_negocio) -> int:
    """En cada ciclo aplica la llegada de T a los eventos que corresponda (C-01, CA-109, CA-110) y despacha el Outbox, hasta que `detener`
    se active (o una sola vez). Devuelve cuántos eventos del Outbox procesó en total. `reloj` es el reloj de negocio de la API (America/Mexico_City, sin zona, TP-06)."""
    detener = detener or threading.Event()
    total = 0
    while not detener.is_set():
        try:
            llegada = contenedor.servicios.cierre.procesar_eventos_vencidos(reloj())
            if llegada.datos.get("iniciados") or llegada.datos.get("cerrados") or llegada.datos.get("errores"):
                registro.info("Llegada de T: %s", llegada.datos)
            procesados = contenedor.despachador.despachar()
            total += procesados
            if procesados:
                registro.info("Eventos procesados: %s", procesados)
        except Exception:                                   # se registra y se reintenta en el siguiente ciclo
            registro.exception("Falló un ciclo de despacho del Outbox")
            if una_vez:
                raise
        if una_vez:
            break
        detener.wait(intervalo)
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Trabajador de despacho del Outbox de Eventos Nova")
    parser.add_argument("--intervalo", type=float, default=2.0, help="segundos entre ciclos (por omisión 2)")
    parser.add_argument("--una-vez", action="store_true", help="despachar lo pendiente y terminar")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    detener = threading.Event()
    anteriores = {senal: signal.signal(senal, lambda *_: detener.set()) for senal in (signal.SIGINT, signal.SIGTERM)}
    try:
        contenedor = construir_persistente()                # falla de forma clara si no hay base de datos o falta migrar
        try:
            total = ejecutar(contenedor, args.intervalo, args.una_vez, detener)
            registro.info("Trabajador detenido; eventos procesados: %s", total)
        finally:
            contenedor.cerrar()
    finally:
        for senal, manejador in anteriores.items():         # no deja alterados los manejadores de señales del proceso
            signal.signal(senal, manejador)
    return 0


if __name__ == "__main__":
    sys.exit(main())
