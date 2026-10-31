"""Reloj de negocio de Eventos Nova (decisión TP-06 del cierre de alcance aprobado: zona horaria `America/Mexico_City`).

Todas las fechas y horas del dominio, de la API y de la base de datos son locales y **sin zona** (`NaiveDatetime`, `TIMESTAMP` sin
zona): son la hora de pared de la Ciudad de México. El «ahora» que reciben los casos de uso (API y trabajador) sale de esta función y no de
la hora local del sistema operativo, que devolvería la hora del sistema operativo (UTC dentro de los contenedores) y desfasaría 6 horas los plazos, los
límites y la llegada de T. No se convierte ninguna fecha almacenada ni recibida: solo cambia la fuente del instante actual."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

ZONA_NEGOCIO = "America/Mexico_City"          # TP-06
_ZONA = ZoneInfo(ZONA_NEGOCIO)


def reloj_negocio(instante_utc: Optional[datetime] = None) -> datetime:
    """Hora de pared actual de la Ciudad de México, sin zona. `instante_utc` (con zona) permite convertir un instante dado, para pruebas."""
    base = instante_utc if instante_utc is not None else datetime.now(timezone.utc)
    return base.astimezone(_ZONA).replace(tzinfo=None)
