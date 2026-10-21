"""Etapa E2 — base Especificacion: AND, OR, NOT, sus combinaciones, operadores y motivos de incumplimiento."""
import ast
import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from domain.especificacion import Especificacion, EspecificacionSimple, Y, O, No, ConMotivo, Incumplimiento  # noqa: E402

# Especificaciones de prueba sobre diccionarios: cada una lee una clave booleana.
A = EspecificacionSimple(lambda c: c['a'], 'falta a')
B = EspecificacionSimple(lambda c: c['b'], 'falta b')
C = EspecificacionSimple(lambda c: c['c'], 'falta c')
VALORES = [dict(zip('abc', v)) for v in itertools.product((False, True), repeat=3)]


class TablasDeVerdad(unittest.TestCase):
    def test_and(self):
        for c in VALORES:
            with self.subTest(**c):
                self.assertEqual((A & B).es_satisfecha_por(c), c['a'] and c['b'])
                self.assertEqual(A.y(B).es_satisfecha_por(c), c['a'] and c['b'])

    def test_or(self):
        for c in VALORES:
            with self.subTest(**c):
                self.assertEqual((A | B).es_satisfecha_por(c), c['a'] or c['b'])
                self.assertEqual(A.o(B).es_satisfecha_por(c), c['a'] or c['b'])

    def test_not(self):
        for c in VALORES:
            with self.subTest(**c):
                self.assertEqual((~A).es_satisfecha_por(c), not c['a'])
                self.assertEqual(A.no().es_satisfecha_por(c), not c['a'])
                self.assertEqual((~~A).es_satisfecha_por(c), c['a'])

    def test_combinaciones(self):
        for c in VALORES:
            a, b, cc = c['a'], c['b'], c['c']
            with self.subTest(**c):
                self.assertEqual(((A & B) | ~C).es_satisfecha_por(c), (a and b) or not cc)
                self.assertEqual((A & (B | C)).es_satisfecha_por(c), a and (b or cc))
                self.assertEqual((~(A | B) & C).es_satisfecha_por(c), (not (a or b)) and cc)
                self.assertEqual(A.y(B, C).es_satisfecha_por(c), a and b and cc)
                self.assertEqual(A.o(B, C).es_satisfecha_por(c), a or b or cc)

    def test_leyes_de_de_morgan(self):
        for c in VALORES:
            with self.subTest(**c):
                self.assertEqual((~(A & B)).es_satisfecha_por(c), (~A | ~B).es_satisfecha_por(c))
                self.assertEqual((~(A | B)).es_satisfecha_por(c), (~A & ~B).es_satisfecha_por(c))


class MotivosDeIncumplimiento(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(A.motivos_incumplimiento({'a': True}), [])
        self.assertEqual(A.motivos_incumplimiento({'a': False}), ['falta a'])
        self.assertIsNone(A.primer_motivo({'a': True}))

    def test_and_informa_todos_los_motivos_en_orden(self):
        todo_falso = {'a': False, 'b': False, 'c': False}
        self.assertEqual((A & B & C).motivos_incumplimiento(todo_falso), ['falta a', 'falta b', 'falta c'])
        self.assertEqual((C & A & B).motivos_incumplimiento(todo_falso), ['falta c', 'falta a', 'falta b'])
        self.assertEqual((A & B & C).motivos_incumplimiento({'a': True, 'b': False, 'c': True}), ['falta b'])

    def test_primer_motivo_sigue_el_orden_de_composicion(self):
        c = {'a': True, 'b': False, 'c': False}
        self.assertEqual((A & B & C).primer_motivo(c), 'falta b')
        self.assertEqual((A & C & B).primer_motivo(c), 'falta c')
        i = (A & B & C).primer_incumplimiento(c)
        self.assertIsInstance(i, Incumplimiento)
        self.assertIs(i.especificacion, B)

    def test_or_satisfecha_no_informa_motivos(self):
        self.assertEqual((A | B).motivos_incumplimiento({'a': False, 'b': True}), [])

    def test_or_incumplida_informa_cada_alternativa_o_su_motivo_propio(self):
        c = {'a': False, 'b': False}
        self.assertEqual((A | B).motivos_incumplimiento(c), ['falta a', 'falta b'])
        self.assertEqual((A | B).con_motivo('falta a o b').motivos_incumplimiento(c), ['falta a o b'])

    def test_not_con_y_sin_motivo(self):
        self.assertEqual((~A).motivos_incumplimiento({'a': True}), ['NO falta a'])
        self.assertEqual(A.no('a no debe cumplirse').motivos_incumplimiento({'a': True}), ['a no debe cumplirse'])
        self.assertEqual(No(A, 'x').motivos_incumplimiento({'a': False}), [])

    def test_con_motivo_conserva_la_condicion(self):
        e = (A & B).con_motivo('motivo propio')
        self.assertIsInstance(e, ConMotivo)
        for c in VALORES:
            self.assertEqual(e.es_satisfecha_por(c), c['a'] and c['b'])
        self.assertEqual(e.motivos_incumplimiento({'a': False, 'b': False}), ['motivo propio'])
        self.assertIs(e.primer_incumplimiento({'a': False, 'b': True}).especificacion, e)

    def test_motivo_puede_depender_del_candidato(self):
        class Rango(Especificacion):
            def es_satisfecha_por(self, n): return n <= 10
            def motivo(self, n): return f'{n} supera 10'
        self.assertEqual((Rango() & EspecificacionSimple(lambda n: n > 0, 'no positivo')).motivos_incumplimiento(12),
                         ['12 supera 10'])


class Estructura(unittest.TestCase):
    def test_composicion_se_aplana_y_conserva_el_orden(self):
        e = (A & B) & C
        self.assertIsInstance(e, Y)
        self.assertEqual(e.partes, (A, B, C))
        self.assertEqual(((A | B) | C).partes, (A, B, C))
        self.assertEqual(len((A & (B | C)).partes), 2)            # no se aplanan operadores distintos

    def test_operadores_y_metodos_son_equivalentes(self):
        self.assertIsInstance(A & B, Y); self.assertIsInstance(A.y(B), Y)
        self.assertIsInstance(A | B, O); self.assertIsInstance(A.o(B), O)
        self.assertIsInstance(~A, No); self.assertIsInstance(A.no(), No)

    def test_compuesta_requiere_al_menos_dos_partes(self):
        with self.assertRaises(ValueError):
            Y(A)
        with self.assertRaises(ValueError):
            O(A)

    def test_descripcion_legible(self):
        self.assertEqual(repr((A & B) | ~C), '((falta a Y falta b) O NO falta c)')

    def test_base_abstracta(self):
        with self.assertRaises(TypeError):
            Especificacion()

    def test_no_depende_de_otras_capas_ni_bibliotecas_externas(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'domain', 'especificacion.py')
        with open(ruta, encoding='utf8') as f:
            arbol = ast.parse(f.read())
        mods = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                mods |= {a.name.split('.')[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add('.' * n.level + (n.module or ''))
        self.assertLessEqual(mods, {'__future__', 'abc', 'dataclasses', 'typing'}, mods)


if __name__ == '__main__':
    unittest.main()
