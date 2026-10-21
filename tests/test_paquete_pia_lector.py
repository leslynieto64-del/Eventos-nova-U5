"""Etapa E1 — lector de los CSV oficiales: conteos, encabezados, tipos, claves, referencias y formatos.

Las pruebas de rechazo alteran una copia temporal del paquete y leen con verificar_integridad=False para
comprobar cada validación estructural por separado (la verificación del hash se prueba en
test_paquete_pia_integridad.py). No dependen del dominio, de la API ni de una base de datos."""
import ast
import glob
import os
import unittest
from datetime import date
from decimal import Decimal

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # permite ejecutar como tests.<módulo>
from apoyo_paquete_pia import CopiaPaquete, DIRECTORIO_OFICIAL, RAIZ

from paquete_pia import (leer_paquete, ErrorPaquetePIA, PaquetePIA, Actor, RecursoCatalogo, Operacion,
                         DetalleOperacion, CasoPrueba, TransicionPrueba)
from paquete_pia.esquema import ESQUEMAS

CONTEOS = {"actores.csv": 40, "catalogo.csv": 20, "operaciones.csv": 60, "detalle_operaciones.csv": 117,
           "casos_prueba.csv": 120, "transiciones_prueba.csv": 20}

ENCABEZADOS = {
    "actores.csv": ["actor_id", "nombre", "es_preferente", "activo", "ciudad"],
    "catalogo.csv": ["recurso_id", "descripcion", "precio_mxn", "capacidad_o_stock", "habilitado"],
    "operaciones.csv": ["operacion_id", "actor_id", "estado_inicial", "fecha_solicitud", "promocion_activa",
                        "autorizado", "referencia"],
    "detalle_operaciones.csv": ["operacion_id", "recurso_id", "cantidad"],
    "casos_prueba.csv": ["caso_id", "operacion_id", "tipo_prueba", "regla_a_verificar", "resultado_alumno",
                         "instrucciones"],
    "transiciones_prueba.csv": ["caso_id", "operacion_id", "accion_sugerida", "estado_inicial", "resultado_alumno",
                                "instrucciones"],
}


class _ConPaquete(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paquete = leer_paquete()                       # datos oficiales, con verificación de integridad


class ConteosYEncabezados(_ConPaquete):
    def test_conteos_esperados(self):
        self.assertEqual(self.paquete.conteos(), CONTEOS)

    def test_encabezados_del_esquema_coinciden_con_los_archivos(self):
        for esquema in ESQUEMAS:
            with self.subTest(archivo=esquema.nombre):
                self.assertEqual(list(esquema.encabezados), ENCABEZADOS[esquema.nombre])
                with open(DIRECTORIO_OFICIAL / esquema.nombre, encoding="utf-8-sig", newline="") as f:
                    self.assertEqual(f.readline().rstrip("\r\n").split(","), ENCABEZADOS[esquema.nombre])

    def test_devuelve_dto_independientes(self):
        self.assertIsInstance(self.paquete, PaquetePIA)
        for coleccion, tipo in ((self.paquete.actores, Actor), (self.paquete.catalogo, RecursoCatalogo),
                                (self.paquete.operaciones, Operacion), (self.paquete.detalle_operaciones, DetalleOperacion),
                                (self.paquete.casos_prueba, CasoPrueba), (self.paquete.transiciones_prueba, TransicionPrueba)):
            self.assertIsInstance(coleccion, tuple)
            self.assertTrue(all(type(x) is tipo for x in coleccion))
        with self.assertRaises(Exception):                 # inmutables
            self.paquete.actores[0].activo = False


class CodificacionYTipos(_ConPaquete):
    def test_bom_y_crlf_no_contaminan_los_valores(self):
        primero = self.paquete.actores[0]
        self.assertEqual(primero.actor_id, "EVE-C001")      # sin el BOM ﻿ delante
        textos = [v for coleccion in (self.paquete.actores, self.paquete.catalogo, self.paquete.operaciones,
                                      self.paquete.casos_prueba, self.paquete.transiciones_prueba)
                  for x in coleccion for v in vars(x).values() if isinstance(v, str)]
        self.assertFalse([t for t in textos if "\r" in t or "\n" in t or "﻿" in t])

    def test_acentos_utf8(self):
        self.assertEqual(self.paquete.catalogo[2].descripcion, "Cumpleaños 03")

    def test_importes_son_decimal_y_no_float(self):
        for r in self.paquete.catalogo:
            self.assertIs(type(r.precio_mxn), Decimal)
        self.assertEqual(self.paquete.catalogo[0].precio_mxn, Decimal("589.00"))
        self.assertEqual(str(self.paquete.catalogo[0].precio_mxn), "589.00")   # conserva la escala

    def test_booleanos_enteros_y_fechas(self):
        for a in self.paquete.actores:
            self.assertIs(type(a.es_preferente), bool); self.assertIs(type(a.activo), bool)
        for r in self.paquete.catalogo:
            self.assertIs(type(r.habilitado), bool); self.assertIs(type(r.capacidad_o_stock), int)
        for o in self.paquete.operaciones:
            self.assertIs(type(o.fecha_solicitud), date)
            self.assertIs(type(o.promocion_activa), bool); self.assertIs(type(o.autorizado), bool)
        for d in self.paquete.detalle_operaciones:
            self.assertIs(type(d.cantidad), int)
        self.assertEqual(self.paquete.operaciones[0].fecha_solicitud, date(2026, 10, 2))

    def test_resultado_alumno_se_conserva_como_texto(self):
        """Es una columna de salida: el lector no la interpreta ni la llena."""
        valores = {c.resultado_alumno for c in self.paquete.casos_prueba} | \
                  {t.resultado_alumno for t in self.paquete.transiciones_prueba}
        self.assertEqual(valores, {"PENDIENTE"})


class Independencia(unittest.TestCase):
    """El lector no depende del dominio, la aplicación, la API ni la persistencia, y ninguna capa lo usa todavía."""

    PROHIBIDOS = {"domain", "application", "infrastructure", "api", "fastapi", "starlette", "pydantic",
                  "sqlite3", "sqlalchemy", "psycopg", "psycopg2", "alembic", "pymysql"}

    def _modulos(self, patron):
        mods = set()
        for f in glob.glob(patron):
            with open(f, encoding="utf8") as h:
                for n in ast.walk(ast.parse(h.read())):
                    if isinstance(n, ast.Import):
                        mods |= {a.name.split(".")[0] for a in n.names}
                    elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                        mods.add(n.module.split(".")[0])
        return mods

    def test_lector_solo_usa_la_biblioteca_estandar(self):
        mods = self._modulos(os.path.join(RAIZ, "src", "paquete_pia", "*.py"))
        self.assertFalse(mods & self.PROHIBIDOS, mods)

    def test_las_capas_existentes_no_usan_el_lector(self):
        for capa in ("domain", "application", "infrastructure", "api"):
            with self.subTest(capa=capa):
                self.assertNotIn("paquete_pia", self._modulos(os.path.join(RAIZ, "src", capa, "*.py")))


class RechazosEstructurales(unittest.TestCase):
    """Cada alteración se aplica a una copia; se lee sin verificar el hash para aislar la validación."""

    def assertRechazo(self, copia, *fragmentos, archivo=None, columna=None):
        with self.assertRaises(ErrorPaquetePIA) as ctx:
            leer_paquete(copia.ruta, verificar_integridad=False)
        problemas = ctx.exception.problemas
        textos = [str(p) for p in problemas]
        for fragmento in fragmentos:
            coincidentes = [p for p in problemas if fragmento in p.mensaje
                            and (archivo is None or p.archivo == archivo)
                            and (columna is None or p.columna == columna)]
            self.assertTrue(coincidentes, f"no se informó {fragmento!r} ({archivo}, {columna}); problemas: {textos}")
        return problemas

    # -- encabezados y conteos
    def test_encabezado_renombrado(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "es_preferente", "preferente", linea=1)
            self.assertRechazo(c, "encabezados inválidos", archivo="actores.csv")

    def test_encabezado_reordenado(self):
        with CopiaPaquete() as c:
            c.reemplazar("detalle_operaciones.csv", "operacion_id,recurso_id", "recurso_id,operacion_id", linea=1)
            self.assertRechazo(c, "encabezados inválidos", archivo="detalle_operaciones.csv")

    def test_registro_faltante(self):
        with CopiaPaquete() as c:
            lineas = c.lineas("catalogo.csv")
            c.escribir_lineas("catalogo.csv", lineas[:-1])
            self.assertRechazo(c, "se esperaban 20 registros y se encontraron 19", archivo="catalogo.csv")

    def test_registro_agregado_aunque_sea_valido(self):
        with CopiaPaquete() as c:
            c.escribir_lineas("actores.csv", c.lineas("actores.csv") + ["EVE-C041,Organizador 41,0,1,Monterrey"])
            self.assertRechazo(c, "se esperaban 40 registros y se encontraron 41", archivo="actores.csv")

    def test_fila_vacia(self):
        with CopiaPaquete() as c:
            lineas = c.lineas("operaciones.csv")
            c.escribir_lineas("operaciones.csv", lineas[:10] + [""] + lineas[10:])
            self.assertRechazo(c, "fila vacía", archivo="operaciones.csv")

    def test_columnas_de_mas_y_de_menos(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "EVE-C003,Organizador 03,0,1,Monterrey", "EVE-C003,Organizador 03,0,1,Monterrey,X", linea=4)
            c.reemplazar("catalogo.csv", "EVE-P004,Graduación 04,802.00,22,1", "EVE-P004,Graduación 04,802.00,22", linea=5)
            self.assertRechazo(c, "la fila tiene 6 columnas", archivo="actores.csv")
            self.assertRechazo(c, "la fila tiene 4 columnas", archivo="catalogo.csv")

    # -- claves y unicidad
    def test_identificador_duplicado(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "EVE-C002,", "EVE-C001,", linea=3)
            problemas = self.assertRechazo(c, "clave primaria duplicada", archivo="actores.csv", columna="actor_id")
            self.assertEqual(sorted(p.fila for p in problemas if "duplicada" in p.mensaje), [2, 3])

    def test_clave_compuesta_duplicada_en_detalle(self):
        with CopiaPaquete() as c:
            c.reemplazar("detalle_operaciones.csv", "EVE-O001,EVE-P014,4", "EVE-O001,EVE-P009,4", linea=3)
            self.assertRechazo(c, "clave primaria duplicada", archivo="detalle_operaciones.csv",
                               columna="operacion_id, recurso_id")

    def test_casos_y_transiciones_duplicados(self):
        with CopiaPaquete() as c:
            c.reemplazar("casos_prueba.csv", "EVE-B001,", "EVE-T001,", linea=3)
            c.reemplazar("transiciones_prueba.csv", "EVE-S002,", "EVE-S001,", linea=3)
            self.assertRechazo(c, "clave primaria duplicada", archivo="casos_prueba.csv")
            self.assertRechazo(c, "clave primaria duplicada", archivo="transiciones_prueba.csv")

    def test_referencia_de_operacion_duplicada(self):
        with CopiaPaquete() as c:
            c.reemplazar("operaciones.csv", "PIA_EVE_002", "PIA_EVE_001", linea=3)
            self.assertRechazo(c, "valor único duplicada", archivo="operaciones.csv", columna="referencia")

    # -- referencias entre archivos
    def test_referencias_invalidas(self):
        with CopiaPaquete() as c:
            c.reemplazar("operaciones.csv", "EVE-O001,EVE-C024", "EVE-O001,EVE-C099", linea=2)
            c.reemplazar("detalle_operaciones.csv", "EVE-O001,EVE-P009", "EVE-O001,EVE-P099", linea=2)
            c.reemplazar("detalle_operaciones.csv", "EVE-O002,EVE-P012", "EVE-O099,EVE-P012", linea=4)
            c.reemplazar("casos_prueba.csv", "EVE-T001,EVE-O001", "EVE-T001,EVE-O098", linea=2)
            c.reemplazar("transiciones_prueba.csv", "EVE-S001,EVE-O001", "EVE-S001,EVE-O097", linea=2)
            self.assertRechazo(c, "EVE-C099 no existe en actores.csv", archivo="operaciones.csv", columna="actor_id")
            self.assertRechazo(c, "EVE-P099 no existe en catalogo.csv", archivo="detalle_operaciones.csv", columna="recurso_id")
            self.assertRechazo(c, "EVE-O099 no existe en operaciones.csv", archivo="detalle_operaciones.csv", columna="operacion_id")
            self.assertRechazo(c, "EVE-O098 no existe en operaciones.csv", archivo="casos_prueba.csv")
            self.assertRechazo(c, "EVE-O097 no existe en operaciones.csv", archivo="transiciones_prueba.csv")

    def test_estado_inicial_de_transicion_distinto_al_de_la_operacion(self):
        with CopiaPaquete() as c:
            c.reemplazar("transiciones_prueba.csv", "completar,COTIZADO", "completar,CONTRATADO", linea=2)
            self.assertRechazo(c, "no coincide con el de EVE-O001", archivo="transiciones_prueba.csv")

    # -- formatos
    def test_booleanos_invalidos(self):
        for valor in ("2", "si", "true", "", " 1"):
            with self.subTest(valor=valor), CopiaPaquete() as c:
                c.reemplazar("actores.csv", "Organizador 01,0,1,", f"Organizador 01,0,{valor},", linea=2)
                self.assertRechazo(c, "", archivo="actores.csv", columna="activo")

    def test_importes_mal_formados(self):
        for valor in ('"589,00"', "589","589.0", "-589.00", "+589.00", "5.89e2", "NaN", "abc", '"589.00 "'):
            with self.subTest(valor=valor), CopiaPaquete() as c:
                c.reemplazar("catalogo.csv", "Boda 01,589.00,", f"Boda 01,{valor},", linea=2)
                self.assertRechazo(c, "importe inválido", archivo="catalogo.csv", columna="precio_mxn")

    def test_enteros_mal_formados(self):
        for valor in ("13.0", "-1", "trece", ""):
            with self.subTest(valor=valor), CopiaPaquete() as c:
                c.reemplazar("catalogo.csv", "589.00,13,1", f"589.00,{valor},1", linea=2)
                self.assertRechazo(c, "", archivo="catalogo.csv", columna="capacidad_o_stock")
        for valor in ("0", "x", "1.5"):
            with self.subTest(cantidad=valor), CopiaPaquete() as c:
                c.reemplazar("detalle_operaciones.csv", "EVE-O001,EVE-P009,3", f"EVE-O001,EVE-P009,{valor}", linea=2)
                self.assertRechazo(c, "", archivo="detalle_operaciones.csv", columna="cantidad")

    def test_fechas_no_iso_o_inexistentes(self):
        for valor, fragmento in (("2026-13-02", "fecha inexistente"), ("2026-02-30", "fecha inexistente"),
                                 ("02/10/2026", "formato esperado"), ("20261002", "formato esperado"),
                                 ("2026-10-02T00:00", "formato esperado")):
            with self.subTest(valor=valor), CopiaPaquete() as c:
                c.reemplazar("operaciones.csv", "COTIZADO,2026-10-02,", f"COTIZADO,{valor},", linea=2)
                self.assertRechazo(c, fragmento, archivo="operaciones.csv", columna="fecha_solicitud")

    def test_identificadores_con_formato_invalido(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "EVE-C001,", "EVE-X001,", linea=2)
            c.reemplazar("catalogo.csv", "EVE-P001,", "eve-p001,", linea=2)
            self.assertRechazo(c, "identificador con formato inválido", archivo="actores.csv", columna="actor_id")
            self.assertRechazo(c, "identificador con formato inválido", archivo="catalogo.csv", columna="recurso_id")

    def test_estado_fuera_del_vocabulario_del_paquete(self):
        with CopiaPaquete() as c:
            c.reemplazar("operaciones.csv", "EVE-C024,COTIZADO,", "EVE-C024,EN_GESTION,", linea=2)
            self.assertRechazo(c, "valor no reconocido", archivo="operaciones.csv", columna="estado_inicial")

    def test_textos_vacios_o_con_espacios(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "Organizador 01,", ",", linea=2)
            c.reemplazar("actores.csv", ",Apodaca", ", Apodaca", linea=3)
            self.assertRechazo(c, "el valor está vacío", archivo="actores.csv", columna="nombre")
            self.assertRechazo(c, "espacios al inicio o al final", archivo="actores.csv", columna="ciudad")

    # -- archivo y codificación
    def test_utf8_invalido(self):
        with CopiaPaquete() as c:
            ruta = c.archivo("catalogo.csv")
            ruta.write_bytes(ruta.read_bytes().replace("ñ".encode("utf-8"), b"\xf1"))   # ñ en Latin-1
            self.assertRechazo(c, "no está codificado en UTF-8", archivo="catalogo.csv")

    def test_archivo_faltante(self):
        with CopiaPaquete() as c:
            c.archivo("detalle_operaciones.csv").unlink()
            self.assertRechazo(c, "el archivo no existe", archivo="detalle_operaciones.csv")

    def test_reune_todos_los_problemas(self):
        with CopiaPaquete() as c:
            c.reemplazar("actores.csv", "Organizador 01,0,1,", "Organizador 01,0,9,", linea=2)
            c.reemplazar("catalogo.csv", "Boda 01,589.00,", "Boda 01,589,", linea=2)
            c.reemplazar("operaciones.csv", "COTIZADO,2026-10-02,", "COTIZADO,2026/10/02,", linea=2)
            problemas = self.assertRechazo(c, "booleano inválido", "importe inválido", "fecha inválida")
            self.assertEqual({p.archivo for p in problemas}, {"actores.csv", "catalogo.csv", "operaciones.csv"})

    def test_sin_bom_y_con_lf_se_interpreta_igual(self):
        """La codificación utf-8-sig y newline='' admiten ambas variantes; el manifiesto sí las detecta."""
        oficial = leer_paquete()
        with CopiaPaquete() as c:
            for nombre in CONTEOS:
                ruta = c.archivo(nombre)
                ruta.write_bytes(ruta.read_bytes().removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n"))
            self.assertEqual(leer_paquete(c.ruta, verificar_integridad=False), oficial)


if __name__ == "__main__":
    unittest.main()
