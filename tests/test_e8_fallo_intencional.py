"""E8 — FALLO INTENCIONAL (temporal, solo en la rama demo/e8-fallo-intencional; no debe llegar a main).
Demuestra que GitHub Actions detecta una prueba fallida y marca el pipeline en rojo."""
import unittest


class E8FalloIntencional(unittest.TestCase):
    def test_fallo_intencional_para_demostrar_que_ci_detecta_errores(self):
        self.assertEqual(1 + 1, 3, 'E8: fallo intencional para demostrar la deteccion de errores en CI')


if __name__ == '__main__':
    unittest.main()
