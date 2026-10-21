"""Lector y validación del paquete oficial de datos 16_Eventos_Nova (Etapa E1).

Este paquete es independiente del dominio, de la aplicación, de la API y de cualquier infraestructura de
persistencia: solo usa la biblioteca estándar. Lee los seis CSV oficiales, comprueba su integridad con el
manifiesto SHA-256 y valida su estructura (encabezados, conteos, claves, referencias, unicidad y formatos).

No interpreta reglas de negocio ni calcula resultados esperados: los datos se entregan como objetos de datos
(DTO) inmutables, tal como vienen en los archivos.
"""
from .dto import (Actor, RecursoCatalogo, Operacion, DetalleOperacion, CasoPrueba, TransicionPrueba,
                  PaquetePIA)
from .errores import ProblemaValidacion, ErrorPaquetePIA
from .esquema import ARCHIVOS, DIRECTORIO_PREDETERMINADO, NOMBRE_MANIFIESTO
from .lector import leer_paquete
from .manifiesto import calcular_sha256, generar_manifiesto, leer_manifiesto, verificar_manifiesto

__all__ = [
    "Actor", "RecursoCatalogo", "Operacion", "DetalleOperacion", "CasoPrueba", "TransicionPrueba", "PaquetePIA",
    "ProblemaValidacion", "ErrorPaquetePIA", "ARCHIVOS", "DIRECTORIO_PREDETERMINADO", "NOMBRE_MANIFIESTO",
    "leer_paquete", "calcular_sha256", "generar_manifiesto", "leer_manifiesto", "verificar_manifiesto",
]
