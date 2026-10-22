"""Ejecución del paquete oficial 16_Eventos_Nova (Etapa F2).

Ejecuta los 120 casos de `casos_prueba.csv` y las 20 transiciones de `transiciones_prueba.csv`, calcula los totales
de las operaciones con `Decimal` y escribe los resultados en `tests/evidencias/f2/`, sin modificar los CSV oficiales.

Es un consumidor separado: usa el lector `paquete_pia` (que sigue sin depender del dominio) y, para las transiciones,
los servicios de aplicación y la composición en memoria del proyecto. El dominio, la aplicación, la infraestructura y
la API no importan este paquete. Las reglas ilustrativas del paquete se evalúan aquí, fuera del dominio, porque el
BRD de Eventos Nova no las contiene (ver `mapeo.DIFERENCIAS`).
"""
from .totales import ErrorTotal, importe_linea, total_operacion
from .casos import ResultadoCaso, ejecutar_casos
from .transiciones import ResultadoTransicion, ejecutar_transiciones
from .evidencias import DIRECTORIO_EVIDENCIAS, generar_evidencias, escribir_evidencias, verificar_evidencias

__all__ = ["ErrorTotal", "importe_linea", "total_operacion", "ResultadoCaso", "ejecutar_casos",
           "ResultadoTransicion", "ejecutar_transiciones", "DIRECTORIO_EVIDENCIAS", "generar_evidencias",
           "escribir_evidencias", "verificar_evidencias"]
