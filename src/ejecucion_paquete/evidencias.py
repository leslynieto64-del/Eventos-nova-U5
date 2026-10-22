"""Evidencias de la Etapa F2: tablas completas, una fila por registro, en `tests/evidencias/f2/`.

Archivos generados (CSV en UTF-8 con BOM para que Excel muestre los acentos, Markdown en UTF-8; separador coma;
saltos de línea LF; sin identificadores aleatorios ni marcas de tiempo,
de modo que dos ejecuciones producen exactamente el mismo contenido):

    totales_operaciones.csv       60 operaciones: líneas, importes y total con Decimal, contrastado con el oráculo
    casos_resultados.csv          120 casos: entradas, esperado, real, veredicto, diferencia y explicación
    transiciones_resultados.csv   20 transiciones: estado de partida, acción, resultado, eventos, veredicto y diferencia
    mapeo_estados_acciones.csv    correspondencia de estados y acciones del paquete con el dominio
    diferencias_modelo.csv        diferencias documentadas D-01 a D-08
    resumen.md                    conteos, hashes SHA-256 de las entradas y preguntas abiertas

Cada fila de resultados lleva `fila_origen` (archivo y número de línea del CSV oficial) para su trazabilidad.
Los CSV oficiales solo se leen: nunca se escriben.
"""
from __future__ import annotations
import csv
import io
from collections import Counter, defaultdict
from dataclasses import asdict, fields
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from paquete_pia import ARCHIVOS, DIRECTORIO_PREDETERMINADO, NOMBRE_MANIFIESTO, calcular_sha256, leer_paquete
from .casos import APROBADO, FALLIDO, NO_EJECUTABLE, ejecutar_casos
from .mapeo import ACCIONES, DIFERENCIAS, ESTADOS, PREGUNTAS
from .oraculo import Oraculo
from .totales import importe_linea, total_operacion
from .transiciones import ejecutar_transiciones

DIRECTORIO_EVIDENCIAS = Path(__file__).resolve().parents[2] / "tests" / "evidencias" / "f2"
ARCHIVOS_EVIDENCIA = ("totales_operaciones.csv", "casos_resultados.csv", "transiciones_resultados.csv",
                      "mapeo_estados_acciones.csv", "diferencias_modelo.csv", "resumen.md")
VEREDICTOS = (APROBADO, FALLIDO, NO_EJECUTABLE)


def _celda(valor) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "SÍ" if valor else "NO"
    if isinstance(valor, float):                       # salvaguarda: los importes nunca son float
        raise TypeError("las evidencias no admiten float")
    return str(valor)


def _csv(encabezado: List[str], filas: List[List]) -> str:
    salida = io.StringIO()
    w = csv.writer(salida, lineterminator="\n")
    w.writerow(encabezado)
    for fila in filas:
        w.writerow([_celda(v) for v in fila])
    return salida.getvalue()


def _tabla_dataclass(registros, origen: str, filas_origen: Dict[str, int]) -> str:
    nombres = [f.name for f in fields(registros[0])]
    return _csv(nombres + ["fila_origen"],
                [[getattr(r, n) for n in nombres] + [f"{origen}:{filas_origen[r.caso_id]}"] for r in registros])


def generar_evidencias(directorio: Optional[Path] = None) -> Dict[str, str]:
    """{nombre de archivo: contenido}. No escribe nada."""
    directorio = Path(directorio) if directorio else DIRECTORIO_PREDETERMINADO
    paquete = leer_paquete(directorio)                 # verifica el manifiesto SHA-256 antes de ejecutar
    oraculo = Oraculo(directorio)
    casos = ejecutar_casos(directorio, paquete=paquete)
    transiciones = ejecutar_transiciones(directorio, paquete=paquete)

    # líneas de cada CSV oficial: encabezado en la línea 1, primer registro en la línea 2
    fila_caso = {c.caso_id: i for i, c in enumerate(paquete.casos_prueba, start=2)}
    fila_trans = {t.caso_id: i for i, t in enumerate(paquete.transiciones_prueba, start=2)}

    # totales
    precios = {c.recurso_id: c.precio_mxn for c in paquete.catalogo}
    lineas = defaultdict(list)
    for d in paquete.detalle_operaciones:
        lineas[d.operacion_id].append(d)
    filas_tot = []
    for i, op in enumerate(paquete.operaciones, start=2):
        ls = lineas[op.operacion_id]
        detalle = " + ".join(f"{l.recurso_id} {precios[l.recurso_id]}×{l.cantidad}="
                             f"{importe_linea(precios[l.recurso_id], l.cantidad)}" for l in ls) or "sin líneas"
        total, esperado = total_operacion(ls, precios), oraculo.total(op.operacion_id)
        filas_tot.append([op.operacion_id, op.actor_id, len(ls), detalle, total, esperado,
                          "SÍ" if total == esperado else "NO", f"operaciones.csv:{i}"])
    totales = _csv(["operacion_id", "actor_id", "lineas", "detalle_precio_x_cantidad", "total_mxn",
                    "total_oraculo_mxn", "coincide", "fila_origen"], filas_tot)

    mapeo = _csv(["tipo", "paquete", "dominio", "esperado_paquete", "esperado_dominio", "diferencia", "justificacion",
                  "fuente"],
                 [["estado", e.estado_paquete, e.estado_dominio, "—", "—", "—", e.justificacion, e.fuente]
                  for e in ESTADOS] +
                 [["accion", a.accion_paquete, a.operacion_dominio, a.esperado_paquete, a.esperado_dominio,
                   a.diferencia, "—", a.fuente] for a in ACCIONES])
    diferencias = _csv([f.name for f in fields(DIFERENCIAS[0])], [list(asdict(d).values()) for d in DIFERENCIAS])

    return {
        "totales_operaciones.csv": totales,
        "casos_resultados.csv": _tabla_dataclass(casos, "casos_prueba.csv", fila_caso),
        "transiciones_resultados.csv": _tabla_dataclass(transiciones, "transiciones_prueba.csv", fila_trans),
        "mapeo_estados_acciones.csv": mapeo,
        "diferencias_modelo.csv": diferencias,
        "resumen.md": _resumen(directorio, paquete, casos, transiciones, filas_tot),
    }


def _conteo(registros, clave) -> str:
    c = Counter(clave(r) for r in registros)
    return " | ".join(str(c.get(v, 0)) for v in VEREDICTOS)


def _resumen(directorio, paquete, casos, transiciones, filas_tot) -> str:
    l = ["# Evidencias F2: ejecución del paquete oficial 16_Eventos_Nova", "",
         "Generado por `python ejecutar_paquete_pia.py` (verificación: `python ejecutar_paquete_pia.py --verificar`).",
         "Contenido determinista: sin identificadores aleatorios ni marcas de tiempo.", "",
         "## Entradas (sin modificar)", "", "| Archivo | Registros | SHA-256 |", "|---|---|---|"]
    conteos = paquete.conteos()
    for nombre in ARCHIVOS:
        l.append(f"| {nombre} | {conteos[nombre]} | `{calcular_sha256(Path(directorio) / nombre)}` |")
    l.append(f"| {NOMBRE_MANIFIESTO} | — | `{calcular_sha256(Path(directorio) / NOMBRE_MANIFIESTO)}` |")
    l += ["", "## Totales", "",
          f"- Operaciones: {len(filas_tot)}; coinciden con el oráculo: {sum(f[6] == 'SÍ' for f in filas_tot)}.",
          f"- Suma de los totales: {sum((f[4] for f in filas_tot), Decimal('0.00'))} MXN (Decimal).",
          f"- Operaciones sin líneas (total 0.00): {', '.join(f[0] for f in filas_tot if f[2] == 0) or 'ninguna'}.",
          "", "## Casos (casos_prueba.csv)", "",
          "| Familia | Diferencia | Casos | CUMPLE | NO_CUMPLE | APROBADO | FALLIDO | NO_EJECUTABLE |",
          "|---|---|---|---|---|---|---|---|"]
    for tipo in sorted({c.tipo_prueba for c in casos}):
        grupo = [c for c in casos if c.tipo_prueba == tipo]
        l.append(f"| {tipo} | {grupo[0].diferencia_modelo} | {len(grupo)} | {sum(c.real == 'CUMPLE' for c in grupo)} | "
                 f"{sum(c.real == 'NO_CUMPLE' for c in grupo)} | {_conteo(grupo, lambda c: c.veredicto)} |")
    l.append(f"| **Total** | | {len(casos)} | {sum(c.real == 'CUMPLE' for c in casos)} | "
             f"{sum(c.real == 'NO_CUMPLE' for c in casos)} | {_conteo(casos, lambda c: c.veredicto)} |")
    obs = [c for c in casos if c.observaciones != "—"]
    l += ["", f"Casos con observaciones del catálogo (D-06, no cambian el veredicto): {len(obs)} "
              f"({', '.join(c.caso_id for c in obs) or 'ninguno'}).",
          "", "## Transiciones (transiciones_prueba.csv)", "",
          "| Acción | Transiciones | APROBADO | FALLIDO | NO_EJECUTABLE | Coincide con el paquete (SÍ/NO/—) | Diferencias |",
          "|---|---|---|---|---|---|---|"]
    for accion in [a.accion_paquete for a in ACCIONES]:
        grupo = [t for t in transiciones if t.accion_sugerida == accion]
        cc = Counter(t.coincide_con_paquete for t in grupo)
        difs = sorted({d for t in grupo for d in t.diferencias.split(", ") if d != "—"})
        l.append(f"| {accion} | {len(grupo)} | {_conteo(grupo, lambda t: t.veredicto)} | "
                 f"{cc.get('SÍ', 0)}/{cc.get('NO', 0)}/{cc.get('—', 0)} | {', '.join(difs) or '—'} |")
    cc = Counter(t.coincide_con_paquete for t in transiciones)
    l.append(f"| **Total** | {len(transiciones)} | {_conteo(transiciones, lambda t: t.veredicto)} | "
             f"{cc.get('SÍ', 0)}/{cc.get('NO', 0)}/{cc.get('—', 0)} | |")
    l += ["", "## Criterios", "",
          "- APROBADO: el resultado real coincide con el esperado (resultado y condiciones incumplidas en los casos; "
          "resultado, mensaje, estados, Domain Events, anticipo y ausencia de cambios parciales en las transiciones). "
          "No basta con que no haya excepción.",
          "- FALLIDO: el resultado real no coincide con el esperado (fallo funcional).",
          "- NO_EJECUTABLE: la entrada no puede representarse en el dominio por una regla aprobada documentada; se "
          "verifica el rechazo.",
          "- `coincide_con_paquete = NO`: diferencia documentada del modelo (ver `diferencias_modelo.csv`), no un fallo.",
          "- Los esperados de los casos se derivan del texto de las reglas del LEEME con un oráculo independiente "
          "(los resultados del docente no forman parte del paquete del alumno).",
          "", "## Preguntas abiertas", ""]
    for p in PREGUNTAS:
        l.append(f"- **{p.id}.** {p.pregunta} Alternativas: {p.alternativas}. Decisión provisional: "
                 f"{p.decision_provisional}.")
    return "\n".join(l) + "\n"


def escribir_evidencias(destino: Optional[Path] = None, directorio: Optional[Path] = None) -> List[Path]:
    destino = Path(destino) if destino else DIRECTORIO_EVIDENCIAS
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre, contenido in generar_evidencias(directorio).items():
        ruta = destino / nombre
        with open(ruta, "w", encoding=_codificacion(nombre), newline="") as f:
            f.write(contenido)
        rutas.append(ruta)
    return rutas


def _codificacion(nombre: str) -> str:
    return "utf-8-sig" if nombre.endswith(".csv") else "utf-8"


def _normalizar(texto: str) -> str:
    return texto.replace("\r\n", "\n")                 # un checkout con autocrlf puede convertir LF en CRLF


def verificar_evidencias(destino: Optional[Path] = None, directorio: Optional[Path] = None) -> List[str]:
    """Regenera las evidencias y las compara con las guardadas. Devuelve las diferencias (vacía si coinciden)."""
    destino = Path(destino) if destino else DIRECTORIO_EVIDENCIAS
    problemas = []
    for nombre, contenido in generar_evidencias(directorio).items():
        ruta = destino / nombre
        if not ruta.exists():
            problemas.append(f"{nombre}: no existe")
        elif _normalizar(ruta.read_text(encoding=_codificacion(nombre))) != contenido:
            problemas.append(f"{nombre}: el contenido guardado no coincide con la ejecución actual")
    return problemas
