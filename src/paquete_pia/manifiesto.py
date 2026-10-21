"""Manifiesto SHA-256 de los CSV oficiales.

Formato (compatible con `sha256sum -c`): una línea por archivo, «<hash hexadecimal en minúsculas>  <nombre>»,
ordenadas por nombre. Las funciones de este módulo solo leen archivos; ninguna escribe el manifiesto.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

from .errores import ProblemaValidacion
from .esquema import ARCHIVOS, NOMBRE_MANIFIESTO

Ruta = Union[str, Path]
_LINEA = re.compile(r"([0-9a-f]{64})  ([^/\\\s][^/\\]*)")


def calcular_sha256(ruta: Ruta) -> str:
    """Hash SHA-256 del contenido exacto del archivo (bytes, sin normalizar saltos de línea ni codificación)."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def generar_manifiesto(directorio: Ruta) -> str:
    """Texto del manifiesto de los seis archivos del paquete en `directorio`. No escribe nada en disco."""
    directorio = Path(directorio)
    return "".join(f"{calcular_sha256(directorio / nombre)}  {nombre}\n" for nombre in sorted(ARCHIVOS))


def leer_manifiesto(ruta: Ruta) -> Dict[str, str]:
    """{nombre: hash}. Lanza ValueError si alguna línea no tiene el formato esperado o un nombre se repite."""
    entradas: Dict[str, str] = {}
    with open(ruta, encoding="utf-8", newline="") as f:
        for numero, linea in enumerate(f.read().splitlines(), start=1):
            if not linea.strip():
                continue
            m = _LINEA.fullmatch(linea)
            if not m:
                raise ValueError(f"línea {numero} del manifiesto con formato inválido: {linea!r}")
            hash_, nombre = m.groups()
            if nombre in entradas:
                raise ValueError(f"el archivo {nombre} aparece más de una vez en el manifiesto")
            entradas[nombre] = hash_
    return entradas


def verificar_manifiesto(directorio: Ruta, ruta_manifiesto: Optional[Ruta] = None) -> List[ProblemaValidacion]:
    """Compara los archivos de `directorio` con el manifiesto. Devuelve la lista de problemas (vacía si coincide)."""
    directorio = Path(directorio)
    ruta_manifiesto = Path(ruta_manifiesto) if ruta_manifiesto else directorio / NOMBRE_MANIFIESTO
    nombre_manifiesto = ruta_manifiesto.name
    if not ruta_manifiesto.is_file():
        return [ProblemaValidacion(nombre_manifiesto, "no se encontró el manifiesto SHA-256")]
    try:
        entradas = leer_manifiesto(ruta_manifiesto)
    except (ValueError, UnicodeDecodeError) as e:
        return [ProblemaValidacion(nombre_manifiesto, str(e))]

    problemas: List[ProblemaValidacion] = []
    for nombre in sorted(set(ARCHIVOS) - set(entradas)):
        problemas.append(ProblemaValidacion(nombre_manifiesto, f"el manifiesto no incluye {nombre}"))
    for nombre in sorted(set(entradas) - set(ARCHIVOS)):
        problemas.append(ProblemaValidacion(nombre_manifiesto, f"el manifiesto incluye un archivo ajeno al paquete: {nombre}"))
    for nombre in ARCHIVOS:
        if nombre not in entradas:
            continue
        ruta = directorio / nombre
        if not ruta.is_file():
            problemas.append(ProblemaValidacion(nombre, "el archivo no existe"))
            continue
        obtenido = calcular_sha256(ruta)
        if obtenido != entradas[nombre]:
            problemas.append(ProblemaValidacion(
                nombre, f"el archivo fue alterado: SHA-256 {obtenido} no coincide con el manifiesto {entradas[nombre]}"))
    return problemas
