"""Errores de persistencia. Distinguen las fallas de la base de datos de los rechazos de negocio (`ErrorDominio`), para que la
API pueda responder con un código apropiado y no con un error genérico."""
from __future__ import annotations
from typing import Optional


class ErrorDePersistencia(Exception):
    """Falla al leer o escribir en la base de datos. La excepción original queda en `__cause__`."""


class ViolacionDeRestriccion(ErrorDePersistencia):
    """Una restricción de PostgreSQL (UNIQUE, FOREIGN KEY, CHECK, NOT NULL) rechazó la operación."""
    def __init__(self, mensaje: str, restriccion: Optional[str] = None, tabla: Optional[str] = None, codigo: Optional[str] = None):
        super().__init__(mensaje)
        self.restriccion, self.tabla, self.codigo = restriccion, tabla, codigo


class ConflictoDeConcurrencia(ErrorDePersistencia):
    """Control de concurrencia optimista: el agregado cambió en la base de datos desde que se leyó (o ya existe uno nuevo con el
    mismo identificador). La operación se revierte completa y no se pierde ninguna actualización: se debe leer de nuevo y reintentar."""
    def __init__(self, mensaje: str, agregado: Optional[str] = None, identificador: Optional[str] = None):
        super().__init__(mensaje)
        self.agregado, self.identificador = agregado, identificador


class ErrorDeDatos(ErrorDePersistencia):
    """Un valor no cabe en la columna o tiene un formato inválido (p. ej. entero fuera de rango)."""


class ErrorDeConexion(ErrorDePersistencia):
    """La base de datos no está disponible o la conexión se perdió."""


class EsquemaDesactualizado(ErrorDePersistencia):
    """La base de datos no tiene aplicada la revisión de Alembic que el código necesita."""


class EventoNoRehidratable(ErrorDePersistencia):
    """Un registro del Outbox no puede reconstruirse (tipo desconocido, versión incompatible o datos inválidos)."""
    def __init__(self, mensaje: str, evento_id: Optional[str] = None, tipo_evento: Optional[str] = None):
        super().__init__(mensaje)
        self.evento_id, self.tipo_evento = evento_id, tipo_evento
