"""Adaptadores simulados de colaboradores externos (solo para revisar la arquitectura)."""
from __future__ import annotations
from typing import List
from application.puertos import (IConsultaDisponibilidadProveedor, INotificadorParticipantes, IVerificadorPagos,
                                 IEjecutorDevoluciones)
from domain.valores import DisponibilidadProveedor


class ConsultaDisponibilidadSimulada(IConsultaDisponibilidadProveedor):
    def __init__(self, respuestas: List[DisponibilidadProveedor] = None):
        self.respuestas = respuestas or []

    def consultar(self, servicio, fecha_evento, proveedores_actuales):
        return list(self.respuestas)


class NotificadorEnMemoria(INotificadorParticipantes):
    def __init__(self):
        self.enviados = []

    def notificar(self, destinatarios, asunto, detalle):
        self.enviados.append((tuple(destinatarios), asunto, detalle))


class VerificadorPagosSimulado(IVerificadorPagos):
    def verificar(self, comprobante, importe):
        return bool(comprobante)


class EjecutorDevolucionesSimulado(IEjecutorDevoluciones):
    def __init__(self):
        self.ejecutadas = {}

    def ejecutar(self, devolucion_id, importe, referencia_idempotente):
        return self.ejecutadas.setdefault(referencia_idempotente, f"COMP-{devolucion_id}")
