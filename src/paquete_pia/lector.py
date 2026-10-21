"""Lector de los CSV oficiales del paquete 16_Eventos_Nova.

Orden de la validación:
1. Integridad: los archivos deben coincidir con el manifiesto SHA-256. Si no coinciden, no se leen.
2. Estructura de cada archivo: codificación UTF-8 (con BOM), encabezados exactos y en orden, número de columnas
   por fila, formatos de los valores, número de registros y unicidad de las claves.
3. Referencias entre archivos e igualdad del estado inicial de cada transición con el de su operación.

Se reúnen todos los problemas antes de rechazar el paquete. Los archivos se abren solo para lectura.
"""
from __future__ import annotations
import csv
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from .dto import PaquetePIA
from .errores import ErrorPaquetePIA, ProblemaValidacion
from .esquema import (CODIFICACION, DIRECTORIO_PREDETERMINADO, ESQUEMAS, REFERENCIAS, UNICOS_ADICIONALES,
                      EsquemaArchivo)
from .manifiesto import verificar_manifiesto

Ruta = Union[str, Path]
Fila = Tuple[int, Dict[str, object]]         # (número de línea, valores convertidos)


def leer_paquete(directorio: Optional[Ruta] = None, *, verificar_integridad: bool = True,
                 ruta_manifiesto: Optional[Ruta] = None) -> PaquetePIA:
    """Lee y valida el paquete. Devuelve los DTO o lanza ErrorPaquetePIA con todos los problemas encontrados.

    `verificar_integridad=False` omite la comprobación del manifiesto (solo para analizar la estructura de una
    copia de trabajo); la lectura de los datos oficiales debe hacerse siempre con la verificación activa."""
    directorio = Path(directorio) if directorio is not None else DIRECTORIO_PREDETERMINADO
    if verificar_integridad:
        problemas = verificar_manifiesto(directorio, ruta_manifiesto)
        if problemas:
            raise ErrorPaquetePIA(problemas)

    problemas: List[ProblemaValidacion] = []
    filas: Dict[str, List[Fila]] = {}
    claves: Dict[str, Set[object]] = {}
    for esquema in ESQUEMAS:
        resultado = _leer_archivo(directorio / esquema.nombre, esquema, problemas)
        if resultado is not None:
            filas[esquema.nombre], claves[esquema.nombre] = resultado
    _validar_referencias(filas, claves, problemas)
    if problemas:
        raise ErrorPaquetePIA(problemas)

    def dtos(esquema: EsquemaArchivo):
        return tuple(esquema.dto(**valores) for _, valores in filas[esquema.nombre])
    return PaquetePIA(*(dtos(e) for e in ESQUEMAS))


# ---------------------------------------------------------------- un archivo
def _leer_archivo(ruta: Path, esquema: EsquemaArchivo,
                  problemas: List[ProblemaValidacion]) -> Optional[Tuple[List[Fila], Set[object]]]:
    """Devuelve (filas válidas, claves presentes), o None si el archivo no puede interpretarse (no existe,
    codificación o encabezados inválidos); en ese caso no participa en la validación de referencias.

    Las claves presentes incluyen la clave de las filas que tienen otro valor mal formado: así, un error de formato
    se informa una sola vez y no produce además referencias inválidas en los archivos que apuntan a esa fila."""
    nombre = esquema.nombre
    if not ruta.is_file():
        problemas.append(ProblemaValidacion(nombre, "el archivo no existe"))
        return None
    try:
        # utf-8-sig descarta el BOM; newline='' deja al módulo csv el manejo de CRLF y LF.
        with open(ruta, mode="r", encoding=CODIFICACION, newline="") as f:
            registros = list(csv.reader(f, strict=True))
    except UnicodeDecodeError as e:
        problemas.append(ProblemaValidacion(nombre, f"el archivo no está codificado en UTF-8: {e.reason} en el byte {e.start}"))
        return None
    except csv.Error as e:
        problemas.append(ProblemaValidacion(nombre, f"CSV mal formado: {e}"))
        return None

    if not registros:
        problemas.append(ProblemaValidacion(nombre, "el archivo está vacío"))
        return None
    encabezado = tuple(registros[0])
    if encabezado != esquema.encabezados:
        problemas.append(ProblemaValidacion(
            nombre, f"encabezados inválidos: se esperaba {list(esquema.encabezados)} y se encontró {list(encabezado)}", fila=1))
        return None

    validas: List[Fila] = []
    presentes: Set[object] = set()
    total_registros = 0
    for linea, registro in enumerate(registros[1:], start=2):
        if not registro or registro == [""]:
            problemas.append(ProblemaValidacion(nombre, "fila vacía", fila=linea))
            continue
        total_registros += 1
        if len(registro) != len(esquema.columnas):
            problemas.append(ProblemaValidacion(
                nombre, f"la fila tiene {len(registro)} columnas y se esperaban {len(esquema.columnas)}", fila=linea))
            continue
        valores, fila_valida = {}, True
        for (columna, convertir), celda in zip(esquema.columnas, registro):
            try:
                valores[columna] = convertir(celda)
            except ValueError as e:
                problemas.append(ProblemaValidacion(nombre, str(e), fila=linea, columna=columna))
                fila_valida = False
        if len(esquema.clave) == 1 and esquema.clave[0] in valores:
            presentes.add(valores[esquema.clave[0]])
        if fila_valida:
            validas.append((linea, valores))

    if total_registros != esquema.registros_esperados:
        problemas.append(ProblemaValidacion(
            nombre, f"se esperaban {esquema.registros_esperados} registros y se encontraron {total_registros}"))
    _validar_unicidad(nombre, esquema.clave, validas, problemas, "clave primaria")
    for columna in UNICOS_ADICIONALES.get(nombre, ()):
        _validar_unicidad(nombre, (columna,), validas, problemas, "valor único")
    return validas, presentes


def _validar_unicidad(nombre: str, columnas: Tuple[str, ...], filas: List[Fila],
                      problemas: List[ProblemaValidacion], descripcion: str) -> None:
    conteo = Counter(tuple(v[c] for c in columnas) for _, v in filas)
    for linea, valores in filas:
        clave = tuple(valores[c] for c in columnas)
        if conteo[clave] > 1:
            texto = ", ".join(str(x) for x in clave)
            problemas.append(ProblemaValidacion(
                nombre, f"{descripcion} duplicada: ({texto}) aparece {conteo[clave]} veces", fila=linea,
                columna=", ".join(columnas)))


# ---------------------------------------------------------------- entre archivos
def _validar_referencias(filas: Dict[str, List[Fila]], claves: Dict[str, Set[object]],
                         problemas: List[ProblemaValidacion]) -> None:
    for origen, columna, destino in REFERENCIAS:
        if origen not in filas or destino not in filas:
            continue                                     # el archivo ya tiene un problema que impide leerlo
        for linea, valores in filas[origen]:
            if valores[columna] not in claves[destino]:
                problemas.append(ProblemaValidacion(
                    origen, f"referencia inválida: {valores[columna]} no existe en {destino}", fila=linea, columna=columna))

    if "transiciones_prueba.csv" in filas and "operaciones.csv" in filas:
        estado_de = {v["operacion_id"]: v["estado_inicial"] for _, v in filas["operaciones.csv"]}
        for linea, valores in filas["transiciones_prueba.csv"]:
            esperado = estado_de.get(valores["operacion_id"])
            if esperado is not None and valores["estado_inicial"] != esperado:
                problemas.append(ProblemaValidacion(
                    "transiciones_prueba.csv",
                    f"estado_inicial {valores['estado_inicial']} no coincide con el de {valores['operacion_id']} en "
                    f"operaciones.csv ({esperado})", fila=linea, columna="estado_inicial"))
