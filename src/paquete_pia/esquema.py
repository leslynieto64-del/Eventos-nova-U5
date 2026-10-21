"""Estructura esperada de cada archivo del paquete 16_Eventos_Nova.

Los encabezados y los formatos se tomaron de los archivos oficiales; los conteos son los que indican el LEEME del
paquete y la definición de la Etapa E1. Los estados son el vocabulario que declara el LEEME del paquete
(«Estados sugeridos»); no son los estados del dominio de Eventos Nova.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Tuple

from . import formatos as F
from .dto import Actor, RecursoCatalogo, Operacion, DetalleOperacion, CasoPrueba, TransicionPrueba

DIRECTORIO_PREDETERMINADO = Path(__file__).resolve().parents[2] / "datos" / "paquete_pia"
NOMBRE_MANIFIESTO = "MANIFIESTO.sha256"
CODIFICACION = "utf-8-sig"          # UTF-8 con BOM; también acepta UTF-8 sin BOM

ESTADOS_PAQUETE = ("COTIZADO", "CONTRATADO", "EN_PREPARACION", "REALIZADO", "CANCELADO")

ID_ACTOR = F.identificador(r"EVE-C\d{3}")
ID_RECURSO = F.identificador(r"EVE-P\d{3}")
ID_OPERACION = F.identificador(r"EVE-O\d{3}")
ID_CASO = F.identificador(r"EVE-[TB]\d{3}")
ID_TRANSICION = F.identificador(r"EVE-S\d{3}")
ESTADO = F.uno_de(ESTADOS_PAQUETE)


@dataclass(frozen=True)
class EsquemaArchivo:
    nombre: str
    columnas: Tuple[Tuple[str, Callable[[str], object]], ...]   # (encabezado, conversión) en orden
    registros_esperados: int
    clave: Tuple[str, ...]
    dto: type

    @property
    def encabezados(self) -> Tuple[str, ...]:
        return tuple(nombre for nombre, _ in self.columnas)


ACTORES = EsquemaArchivo(
    "actores.csv",
    (("actor_id", ID_ACTOR), ("nombre", F.texto), ("es_preferente", F.booleano), ("activo", F.booleano),
     ("ciudad", F.texto)),
    40, ("actor_id",), Actor)

CATALOGO = EsquemaArchivo(
    "catalogo.csv",
    (("recurso_id", ID_RECURSO), ("descripcion", F.texto), ("precio_mxn", F.importe),
     ("capacidad_o_stock", F.entero_no_negativo), ("habilitado", F.booleano)),
    20, ("recurso_id",), RecursoCatalogo)

OPERACIONES = EsquemaArchivo(
    "operaciones.csv",
    (("operacion_id", ID_OPERACION), ("actor_id", ID_ACTOR), ("estado_inicial", ESTADO),
     ("fecha_solicitud", F.fecha_iso), ("promocion_activa", F.booleano), ("autorizado", F.booleano),
     ("referencia", F.texto)),
    60, ("operacion_id",), Operacion)

DETALLE_OPERACIONES = EsquemaArchivo(
    "detalle_operaciones.csv",
    (("operacion_id", ID_OPERACION), ("recurso_id", ID_RECURSO), ("cantidad", F.entero_positivo)),
    117, ("operacion_id", "recurso_id"), DetalleOperacion)

CASOS_PRUEBA = EsquemaArchivo(
    "casos_prueba.csv",
    (("caso_id", ID_CASO), ("operacion_id", ID_OPERACION), ("tipo_prueba", F.texto),
     ("regla_a_verificar", F.texto), ("resultado_alumno", F.texto), ("instrucciones", F.texto)),
    120, ("caso_id",), CasoPrueba)

TRANSICIONES_PRUEBA = EsquemaArchivo(
    "transiciones_prueba.csv",
    (("caso_id", ID_TRANSICION), ("operacion_id", ID_OPERACION), ("accion_sugerida", F.texto),
     ("estado_inicial", ESTADO), ("resultado_alumno", F.texto), ("instrucciones", F.texto)),
    20, ("caso_id",), TransicionPrueba)

ESQUEMAS: Tuple[EsquemaArchivo, ...] = (ACTORES, CATALOGO, OPERACIONES, DETALLE_OPERACIONES, CASOS_PRUEBA,
                                        TRANSICIONES_PRUEBA)
ARCHIVOS: Tuple[str, ...] = tuple(e.nombre for e in ESQUEMAS)
REGISTROS_ESPERADOS: Dict[str, int] = {e.nombre: e.registros_esperados for e in ESQUEMAS}

# Columnas que deben ser únicas además de la clave primaria.
UNICOS_ADICIONALES: Dict[str, Tuple[str, ...]] = {"operaciones.csv": ("referencia",)}

# Referencias entre archivos: (archivo, columna) -> archivo referenciado (por su clave primaria simple).
REFERENCIAS: Tuple[Tuple[str, str, str], ...] = (
    ("operaciones.csv", "actor_id", "actores.csv"),
    ("detalle_operaciones.csv", "operacion_id", "operaciones.csv"),
    ("detalle_operaciones.csv", "recurso_id", "catalogo.csv"),
    ("casos_prueba.csv", "operacion_id", "operaciones.csv"),
    ("transiciones_prueba.csv", "operacion_id", "operaciones.csv"),
)
