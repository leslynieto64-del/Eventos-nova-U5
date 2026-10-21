"""Utilidades compartidas por las pruebas del lector del paquete (Etapa E1).

Las alteraciones se hacen siempre sobre una copia temporal de datos/paquete_pia; los originales no se modifican.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

DIRECTORIO_OFICIAL = RAIZ / "datos" / "paquete_pia"
BOM = b"\xef\xbb\xbf"


class CopiaPaquete:
    """Copia temporal del paquete oficial, para alterarla en una prueba (uso con `with`)."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="paquete_pia_")
        self.ruta = Path(self._tmp.name) / "paquete_pia"
        shutil.copytree(DIRECTORIO_OFICIAL, self.ruta)
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()

    def archivo(self, nombre):
        return self.ruta / nombre

    def lineas(self, nombre):
        """Líneas del CSV sin BOM ni saltos de línea."""
        datos = self.archivo(nombre).read_bytes()
        if datos.startswith(BOM):
            datos = datos[len(BOM):]
        return datos.decode("utf-8").split("\r\n")[:-1]           # el archivo termina en CRLF

    def escribir_lineas(self, nombre, lineas):
        """Escribe con el mismo formato del original: UTF-8 con BOM y CRLF."""
        self.archivo(nombre).write_bytes(BOM + "".join(l + "\r\n" for l in lineas).encode("utf-8"))

    def reemplazar(self, nombre, anterior, nuevo, linea=None):
        """Reemplaza un texto en una línea concreta (número físico, encabezado = 1) o en todo el archivo."""
        lineas = self.lineas(nombre)
        if linea is None:
            texto = "\r\n".join(lineas)
            assert anterior in texto, f"{anterior!r} no está en {nombre}"
            lineas = texto.replace(anterior, nuevo).split("\r\n")
        else:
            assert anterior in lineas[linea - 1], f"{anterior!r} no está en la línea {linea} de {nombre}"
            lineas[linea - 1] = lineas[linea - 1].replace(anterior, nuevo)
        self.escribir_lineas(nombre, lineas)


def huella_directorio(directorio=DIRECTORIO_OFICIAL):
    """{nombre: (contenido en bytes, mtime_ns)} de todos los archivos del directorio."""
    return {p.name: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in sorted(Path(directorio).iterdir()) if p.is_file()}
