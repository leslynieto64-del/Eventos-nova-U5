"""Etapa E1 — integridad de los CSV oficiales: manifiesto SHA-256, rechazo de archivos alterados y
conservación de los originales. No dependen del dominio, de la API ni de una base de datos."""
import builtins
import os
import contextlib
import hashlib
import io
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # permite ejecutar como tests.<módulo>
from apoyo_paquete_pia import CopiaPaquete, DIRECTORIO_OFICIAL, huella_directorio

from paquete_pia import (leer_paquete, ErrorPaquetePIA, verificar_manifiesto, generar_manifiesto, leer_manifiesto,
                         calcular_sha256, ARCHIVOS, NOMBRE_MANIFIESTO)
from paquete_pia.__main__ import main

# SHA-256 de los CSV tal como vienen en 16_Eventos_Nova.zip (01_Alumno/datos), calculados al incorporarlos.
# Están fijos en la prueba para que regenerar el manifiesto no pueda «aprobar» un archivo alterado.
HASHES_OFICIALES = {
    "actores.csv": "64996c64eca5a253067ef9102c8832978646159e511bc0126f622939512a8d6a",
    "casos_prueba.csv": "ee24c89b0c78feda2fe0b5b2802223c9bb0ebc3b256353d4e012849a755b8a27",
    "catalogo.csv": "5933a87d19072555d602c3d656b0550e6c08cabc6ae0b369e0e300983c4be8be",
    "detalle_operaciones.csv": "131ab6d724ba3894f8418a5856ce48c1804a8882419445c8e61521d018a04ced",
    "operaciones.csv": "cb9a091864b3cd103898bee5328aa03315fbc89347512e093e3c12412255eb69",
    "transiciones_prueba.csv": "f691e9eb54ff7ba088e55dc22ed5f3cbb171923e1bc457a6bda8eb5c9bd7f5f1",
}


class ManifiestoOficial(unittest.TestCase):
    def test_estan_los_seis_csv_y_el_manifiesto(self):
        presentes = {p.name for p in DIRECTORIO_OFICIAL.iterdir()}
        self.assertEqual(presentes, set(ARCHIVOS) | {NOMBRE_MANIFIESTO})

    def test_manifiesto_contiene_los_hashes_oficiales(self):
        self.assertEqual(leer_manifiesto(DIRECTORIO_OFICIAL / NOMBRE_MANIFIESTO), HASHES_OFICIALES)

    def test_los_archivos_coinciden_con_los_hashes_oficiales(self):
        for nombre, esperado in HASHES_OFICIALES.items():
            with self.subTest(archivo=nombre):
                self.assertEqual(hashlib.sha256((DIRECTORIO_OFICIAL / nombre).read_bytes()).hexdigest(), esperado)
                self.assertEqual(calcular_sha256(DIRECTORIO_OFICIAL / nombre), esperado)

    def test_verificacion_sin_problemas_y_manifiesto_reproducible(self):
        self.assertEqual(verificar_manifiesto(DIRECTORIO_OFICIAL), [])
        self.assertEqual(generar_manifiesto(DIRECTORIO_OFICIAL),
                         (DIRECTORIO_OFICIAL / NOMBRE_MANIFIESTO).read_text(encoding="utf-8"))

    def test_originales_conservan_bom_y_crlf(self):
        for nombre in ARCHIVOS:
            with self.subTest(archivo=nombre):
                datos = (DIRECTORIO_OFICIAL / nombre).read_bytes()
                self.assertTrue(datos.startswith(b"\xef\xbb\xbf"))
                self.assertEqual(datos.count(b"\n"), datos.count(b"\r\n"))


class RechazoDeArchivosAlterados(unittest.TestCase):
    def assertRechazadoPorHash(self, copia, archivo):
        with self.assertRaises(ErrorPaquetePIA) as ctx:
            leer_paquete(copia.ruta)
        self.assertTrue(any(p.archivo == archivo and "fue alterado" in p.mensaje for p in ctx.exception.problemas),
                        [str(p) for p in ctx.exception.problemas])

    def test_alteracion_que_sigue_siendo_estructuralmente_valida(self):
        """Sin el manifiesto pasaría la validación; con él se rechaza."""
        with CopiaPaquete() as c:
            c.reemplazar("catalogo.csv", "Boda 01,589.00,", "Boda 01,589.01,", linea=2)
            leer_paquete(c.ruta, verificar_integridad=False)          # estructura correcta
            self.assertRechazadoPorHash(c, "catalogo.csv")

    def test_cada_csv_alterado_se_rechaza(self):
        for nombre in ARCHIVOS:
            with self.subTest(archivo=nombre), CopiaPaquete() as c:
                ruta = c.archivo(nombre)
                ruta.write_bytes(ruta.read_bytes() + b"\r\n")
                self.assertRechazadoPorHash(c, nombre)

    def test_conversion_de_saltos_de_linea_o_perdida_del_bom_se_detecta(self):
        """Así se vería un archivo que Git o un editor convirtieron (CRLF→LF) o guardaron sin BOM."""
        for transformar in (lambda b: b.replace(b"\r\n", b"\n"), lambda b: b[3:]):
            with CopiaPaquete() as c:
                ruta = c.archivo("operaciones.csv")
                ruta.write_bytes(transformar(ruta.read_bytes()))
                self.assertRechazadoPorHash(c, "operaciones.csv")

    def test_no_se_leen_datos_si_falla_la_integridad(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "es_preferente", "preferente", linea=1)
            with self.assertRaises(ErrorPaquetePIA) as ctx:
                leer_paquete(c.ruta)
            self.assertFalse(any("encabezados" in p.mensaje for p in ctx.exception.problemas))

    def test_manifiesto_faltante_mal_formado_incompleto_o_con_ajenos(self):
        casos = {
            "no se encontró el manifiesto": lambda m: m.unlink(),
            "formato inválido": lambda m: m.write_text("no es un manifiesto\n", encoding="utf-8"),
            "no incluye actores.csv": lambda m: m.write_text(
                "".join(l + "\n" for l in m.read_text(encoding="utf-8").splitlines() if "actores.csv" not in l),
                encoding="utf-8"),
            "archivo ajeno al paquete": lambda m: m.write_text(
                m.read_text(encoding="utf-8") + "0" * 64 + "  extra.csv\n", encoding="utf-8"),
            "aparece más de una vez": lambda m: m.write_text(
                m.read_text(encoding="utf-8") + m.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8"),
        }
        for fragmento, alterar in casos.items():
            with self.subTest(caso=fragmento), CopiaPaquete() as c:
                alterar(c.archivo(NOMBRE_MANIFIESTO))
                with self.assertRaises(ErrorPaquetePIA) as ctx:
                    leer_paquete(c.ruta)
                self.assertTrue(any(fragmento in p.mensaje for p in ctx.exception.problemas),
                                [str(p) for p in ctx.exception.problemas])

    def test_hash_del_manifiesto_alterado(self):
        with CopiaPaquete() as c:
            m = c.archivo(NOMBRE_MANIFIESTO)
            m.write_text(m.read_text(encoding="utf-8").replace(HASHES_OFICIALES["catalogo.csv"], "f" * 64),
                         encoding="utf-8")
            self.assertRechazadoPorHash(c, "catalogo.csv")


class ConservacionDeLosOriginales(unittest.TestCase):
    def test_leer_no_modifica_ni_toca_los_originales(self):
        antes = huella_directorio()
        leer_paquete()
        verificar_manifiesto(DIRECTORIO_OFICIAL)
        with contextlib.redirect_stdout(io.StringIO()):
            main(["validar"]); main(["hashes"])
        self.assertEqual(huella_directorio(), antes)

    def test_el_lector_abre_los_archivos_solo_para_lectura(self):
        modos, abrir = [], builtins.open

        def espia(archivo, mode="r", *a, **k):
            modos.append(mode)
            return abrir(archivo, mode, *a, **k)
        with mock.patch("builtins.open", espia):
            leer_paquete()
        self.assertTrue(modos)
        self.assertFalse([m for m in modos if set(m) & set("wax+")], modos)

    def test_las_pruebas_de_rechazo_trabajan_sobre_copias(self):
        antes = huella_directorio()
        with CopiaPaquete() as c:
            self.assertNotEqual(c.ruta.resolve(), DIRECTORIO_OFICIAL.resolve())
            for nombre in ARCHIVOS:
                c.archivo(nombre).write_bytes(b"alterado")
            with self.assertRaises(ErrorPaquetePIA):
                leer_paquete(c.ruta)
        self.assertEqual(huella_directorio(), antes)
        self.assertEqual(verificar_manifiesto(DIRECTORIO_OFICIAL), [])


class LineaDeComandos(unittest.TestCase):
    def test_validar_paquete_oficial(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(main(["validar"]), 0)
        self.assertIn("Integridad SHA-256: correcta", salida.getvalue())
        self.assertIn("detalle_operaciones.csv: 117 registros", salida.getvalue())

    def test_validar_copia_alterada_devuelve_error(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "Monterrey", "Guadalupe", linea=2)
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                self.assertEqual(main(["validar", "--directorio", str(c.ruta)]), 1)
            self.assertIn("RECHAZADO", salida.getvalue())
            self.assertIn("actores.csv", salida.getvalue())

    def test_hashes_muestra_el_manifiesto_sin_escribirlo(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(main(["hashes"]), 0)
        self.assertEqual(salida.getvalue(), (DIRECTORIO_OFICIAL / NOMBRE_MANIFIESTO).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
