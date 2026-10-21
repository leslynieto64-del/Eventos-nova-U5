"""Etapa E3A — MaquinaEstados genérica: tabla declarativa, consultas, validación y rechazo de transiciones."""
import ast
import os
import sys
import unittest
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from domain.maquina_estados import MaquinaEstados, Transicion, TransicionNoPermitida   # noqa: E402
from domain.valores import ErrorDominio                                               # noqa: E402


class Estado(Enum):
    A = "A"
    B = "B"
    C = "C"


class Accion(Enum):
    AVANZAR = "avanzar"
    TERMINAR = "terminar"
    REPETIR = "repetir"


def maquina(**extra):
    return MaquinaEstados(Estado, (Transicion(Estado.A, Accion.AVANZAR, Estado.B),
                                   Transicion(Estado.B, Accion.TERMINAR, Estado.C)), **extra)


class Consultas(unittest.TestCase):
    def test_destino_y_permite(self):
        m = maquina()
        self.assertEqual(m.destino(Estado.A, Accion.AVANZAR), Estado.B)
        self.assertTrue(m.permite(Estado.B, Accion.TERMINAR))
        self.assertFalse(m.permite(Estado.A, Accion.TERMINAR))
        self.assertIsNone(m.destino(Estado.C, Accion.AVANZAR))

    def test_acciones_desde_y_terminales(self):
        m = maquina()
        self.assertEqual(m.acciones_desde(Estado.A), {Accion.AVANZAR})
        self.assertEqual(m.acciones_desde(Estado.C), frozenset())
        self.assertEqual(m.estados_terminales, {Estado.C})
        self.assertEqual(m.acciones, {Accion.AVANZAR, Accion.TERMINAR})

    def test_repeticiones_idempotentes(self):
        m = maquina(repeticiones_idempotentes=[(Estado.B, Accion.AVANZAR)])
        self.assertTrue(m.es_repeticion(Estado.B, Accion.AVANZAR))
        self.assertFalse(m.es_repeticion(Estado.A, Accion.AVANZAR))
        self.assertFalse(m.permite(Estado.B, Accion.AVANZAR))       # una repetición no es una transición


class Validacion(unittest.TestCase):
    def test_transitar_devuelve_el_destino_sin_modificar_nada(self):
        m = maquina()
        antes = (m.transiciones, m.repeticiones_idempotentes)
        self.assertEqual(m.transitar(Estado.A, Accion.AVANZAR), Estado.B)
        self.assertEqual((m.transiciones, m.repeticiones_idempotentes), antes)

    def test_transicion_no_permitida_es_error_de_dominio(self):
        with self.assertRaises(TransicionNoPermitida) as ctx:
            maquina().transitar(Estado.C, Accion.AVANZAR)
        self.assertIsInstance(ctx.exception, ErrorDominio)       # se maneja como cualquier rechazo de negocio
        self.assertEqual((ctx.exception.origen, ctx.exception.accion), (Estado.C, Accion.AVANZAR))
        self.assertEqual(str(ctx.exception), "La acción avanzar no está permitida desde C.")

    def test_mensaje_de_rechazo_por_accion_y_origen(self):
        m = maquina(mensajes_rechazo={Accion.AVANZAR: lambda o: f"No se avanza desde {o.value}."})
        with self.assertRaisesRegex(TransicionNoPermitida, r"^No se avanza desde C\.$"):
            m.validar(Estado.C, Accion.AVANZAR)
        self.assertEqual(m.mensaje_rechazo(Estado.A, Accion.TERMINAR), "La acción terminar no está permitida desde A.")

    def test_tabla_invalida(self):
        with self.assertRaisesRegex(ValueError, "duplicada"):
            MaquinaEstados(Estado, (Transicion(Estado.A, Accion.AVANZAR, Estado.B),
                                    Transicion(Estado.A, Accion.AVANZAR, Estado.C)))
        with self.assertRaisesRegex(ValueError, "desconocido"):
            MaquinaEstados((Estado.A, Estado.B), (Transicion(Estado.A, Accion.AVANZAR, Estado.C),))
        with self.assertRaisesRegex(ValueError, "a la vez"):
            maquina(repeticiones_idempotentes=[(Estado.A, Accion.AVANZAR)])

    def test_solo_depende_del_dominio_y_la_biblioteca_estandar(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', 'maquina_estados.py')
        with open(ruta, encoding='utf8') as f:
            arbol = ast.parse(f.read())
        absolutos = {n.module.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.level == 0}
        absolutos |= {a.name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        relativos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.level == 1}
        self.assertLessEqual(absolutos, {'__future__', 'dataclasses', 'typing'}, absolutos)
        self.assertEqual(relativos, {'valores'})                  # solo ErrorDominio; no usa Specifications


if __name__ == '__main__':
    unittest.main()
