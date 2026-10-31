"""Catálogo de Proveedores (registro de las personas o empresas que prestan servicios en los eventos).

El BRD define al Proveedor como «persona o empresa encargada de proporcionar alguno de los servicios necesarios para el evento»
y pide conocer qué proveedores están asignados a cada evento (BN-004), pero no especifica sus atributos. Por eso el registro es
mínimo y no inventa datos: identificador, nombre (obligatorio), contacto (texto libre, opcional) y los servicios que ofrece
(opcional). No tiene tarifas, condiciones contractuales ni calendario: esos datos siguen viniendo del puerto de disponibilidad.

Es un registro de referencia, no una raíz de agregado con máquina de estados: no emite Domain Events ni se versiona."""
from __future__ import annotations
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Tuple
from .valores import ErrorDominio


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados: para comparar nombres y servicios («Música» == «musica»)."""
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return " ".join(sin_acentos.lower().split())


@dataclass(frozen=True)
class Proveedor:
    proveedor_id: str
    nombre: str
    servicios: Tuple[str, ...]
    contacto: str
    registrado_en: datetime

    def __post_init__(self):
        if not self.proveedor_id or not self.proveedor_id.strip():
            raise ErrorDominio("El proveedor debe tener un identificador.")
        if not self.nombre or not self.nombre.strip():
            raise ErrorDominio("Debe indicarse el nombre del proveedor.")
        if any(not s or not s.strip() for s in self.servicios):
            raise ErrorDominio("Los servicios del proveedor no pueden estar vacíos.")

    @staticmethod
    def registrar(proveedor_id: str, nombre: str, servicios: Iterable[str], contacto: str, ahora: datetime) -> "Proveedor":
        vistos, unicos = set(), []
        for s in servicios:
            limpio = " ".join((s or "").split())
            if limpio and normalizar_texto(limpio) not in vistos:
                vistos.add(normalizar_texto(limpio)); unicos.append(limpio)
        return Proveedor(proveedor_id, " ".join((nombre or "").split()), tuple(unicos), (contacto or "").strip(), ahora)

    @property
    def nombre_normalizado(self) -> str:
        return normalizar_texto(self.nombre)

    def ofrece(self, servicio: str) -> bool:
        return normalizar_texto(servicio) in {normalizar_texto(s) for s in self.servicios}

    def coincide_con(self, busqueda: str) -> bool:
        """Búsqueda por texto en el identificador, el nombre, el contacto y los servicios (sin distinguir mayúsculas ni acentos)."""
        q = normalizar_texto(busqueda)
        if not q:
            return True
        return any(q in normalizar_texto(t) for t in (self.proveedor_id, self.nombre, self.contacto, *self.servicios))
