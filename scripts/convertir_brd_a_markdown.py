"""Convierte el BRD aprobado (docs/unidad 2/Reporte_BRD_Corregido.docx) a docs/BRD.md, la ubicación que pide el PIA.

    python scripts/convertir_brd_a_markdown.py              # escribe docs/BRD.md
    python scripts/convertir_brd_a_markdown.py --comprobar  # sale con 1 si docs/BRD.md no está al día

El .docx sigue siendo la FUENTE aprobada y no se modifica; docs/BRD.md es una exportación generada (no se edita a mano). Solo usa la
biblioteca estándar. Conserva el texto, los títulos de nivel 2, las listas y las tablas; no interpreta ni resume."""
import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / "docs" / "unidad 2" / "Reporte_BRD_Corregido.docx"
DESTINO = RAIZ / "docs" / "BRD.md"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _texto(elemento) -> str:
    partes = []
    for nodo in elemento.iter():
        if nodo.tag == W + "t" and nodo.text:
            partes.append(nodo.text)
        elif nodo.tag in (W + "tab",):
            partes.append(" ")
        elif nodo.tag in (W + "br", W + "cr"):
            partes.append(" ")
    return re.sub(r"[ \t]+", " ", "".join(partes)).strip()


def _estilo(parrafo) -> str:
    est = parrafo.find(f"{W}pPr/{W}pStyle")
    return est.get(W + "val") if est is not None else ""


def _es_lista(parrafo) -> bool:
    return parrafo.find(f"{W}pPr/{W}numPr") is not None or _estilo(parrafo).startswith("Prrafodelista")


def _tabla(tbl) -> list:
    filas = []
    for tr in tbl.findall(W + "tr"):
        celdas = [" / ".join(t for t in (_texto(par) for par in tc.iter(W + "p")) if t).replace("|", "\\|")
                  for tc in tr.findall(W + "tc")]
        filas.append("| " + " | ".join(celdas) + " |")
    if not filas:
        return []
    columnas = filas[0].count("|") - 1
    return [filas[0], "|" + "---|" * columnas, *filas[1:], ""]


def generar() -> str:
    cuerpo = ET.fromstring(zipfile.ZipFile(ORIGEN).read("word/document.xml")).find(W + "body")
    lineas = [
        "<!-- Documento GENERADO por scripts/convertir_brd_a_markdown.py a partir de docs/unidad 2/Reporte_BRD_Corregido.docx. No editar a mano: "
        "la fuente aprobada es el .docx. -->",
        "",
        "# BRD — Eventos Nova",
        "",
        "> Exportación en Markdown del BRD aprobado (`docs/unidad 2/Reporte_BRD_Corregido.docx`; PDF en la misma carpeta). "
        "Los requisitos de negocio (BN), las situaciones especiales (SE) y las reglas se enlazan con las User Stories, los criterios "
        "de aceptación, el glosario, los BPMN, el código y las pruebas en `docs/trazabilidad/` y `docs/architecture/trazabilidad-api-persistencia.md`.",
        "",
    ]
    for hijo in cuerpo:
        if hijo.tag == W + "p":
            texto = _texto(hijo)
            if not texto:
                continue
            estilo = _estilo(hijo)
            if estilo.startswith("Ttulo"):
                lineas += ["", "## " + texto, ""]
            elif _es_lista(hijo):
                lineas.append("- " + texto)
            else:
                lineas += [texto, ""]
        elif hijo.tag == W + "tbl":
            lineas += [""] + _tabla(hijo)
    texto = "\n".join(lineas)
    return re.sub(r"\n{3,}", "\n\n", texto).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comprobar", action="store_true")
    args = parser.parse_args()
    texto = generar()
    if args.comprobar:
        actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if actual != texto:
            print("docs/BRD.md no está al día: ejecute scripts/convertir_brd_a_markdown.py", file=sys.stderr)
            return 1
        print("BRD.md al día.")
        return 0
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
