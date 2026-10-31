"""Comprueba el requisito de cobertura del PIA y de la Unidad 5 a partir del informe JSON de coverage.py.

    python -m pytest --cov --cov-report=term-missing --cov-report=html --cov-report=json:coverage.json
    python scripts/verificar_cobertura.py coverage.json [--minimo 80] [--minimo-capa 80] [--capa src/domain --capa src/application]

(También sirve el JSON de `coverage run -m unittest discover -s tests` + `coverage json -o coverage.json`.)

Comprobaciones, todas sobre la cobertura de SENTENCIAS (líneas), que es la métrica del requisito del 80 %:
  1. Total del proyecto (todo src/, sin omitir módulos): el control global que ya existía, con el mismo mínimo.
  2. Cada capa exigida por la Unidad 5 por separado (por omisión src/domain y src/application).
La cobertura de ramas se informa (total y por capa) pero no se exige. Una capa sin sentencias medidas es un FALLO: indica que el
informe no corresponde a esta configuración (p. ej. se midió otro directorio), no que la capa esté cubierta.
También se listan los módulos de cada capa con líneas sin cubrir, para orientar nuevas pruebas.
Sale con código 1 si alguna comprobación no alcanza su mínimo. No modifica ningún archivo ni evidencia."""
import argparse
import json
import sys

CAPAS_POR_OMISION = ("src/domain", "src/application")


def _ruta(nombre: str) -> str:
    """Las claves del JSON usan el separador del sistema donde se midió (Windows: «\\»); se comparan con «/»."""
    return nombre.replace("\\", "/")


def _porcentaje(cubiertas: int, total: int) -> float:
    return 100.0 * cubiertas / total if total else 100.0


def resumen_capa(archivos: dict, capa: str) -> dict:
    """Suma las sentencias y ramas de los archivos cuya ruta está dentro de `capa` (p. ej. «src/domain»)."""
    prefijo = _ruta(capa).rstrip("/") + "/"
    r = {"capa": capa, "archivos": 0, "sentencias": 0, "cubiertas": 0, "sin_cubrir": 0, "ramas": 0, "ramas_cubiertas": 0, "pendientes": []}
    for nombre, datos in sorted(archivos.items()):
        ruta = _ruta(nombre)
        if not ruta.startswith(prefijo):
            continue
        s = datos["summary"]
        r["archivos"] += 1
        r["sentencias"] += s["num_statements"]
        r["cubiertas"] += s["covered_lines"]
        r["sin_cubrir"] += s["missing_lines"]
        r["ramas"] += s.get("num_branches", 0)
        r["ramas_cubiertas"] += s.get("covered_branches", 0)
        if s["missing_lines"] or s.get("missing_branches", 0):
            r["pendientes"].append((ruta, _porcentaje(s["covered_lines"], s["num_statements"]), datos.get("missing_lines", []),
                                    s.get("missing_branches", 0)))
    return r


def _lineas(numeros, maximo: int = 25) -> str:
    texto = ", ".join(str(n) for n in numeros[:maximo])
    return texto + (f", … (+{len(numeros) - maximo})" if len(numeros) > maximo else "")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verifica la cobertura mínima de sentencias (total y por capa)")
    parser.add_argument("archivo", help="salida JSON de coverage (pytest --cov-report=json:… o `coverage json`)")
    parser.add_argument("--minimo", type=float, default=80.0, help="mínimo del total del proyecto (por omisión 80)")
    parser.add_argument("--minimo-capa", type=float, default=80.0, help="mínimo de cada capa (por omisión 80)")
    parser.add_argument("--capa", action="append", default=None,
                        help="directorio de una capa exigida; se puede repetir (por omisión: src/domain y src/application)")
    args = parser.parse_args(argv)
    with open(args.archivo, encoding="utf-8") as f:
        informe = json.load(f)
    t, archivos = informe["totals"], informe.get("files", {})
    fallos = []

    # 1. Control global existente (sin cambios en su criterio).
    sentencias = t["percent_statements_covered"]
    ramas = _porcentaje(t.get("covered_branches", 0), t.get("num_branches", 0))
    print(f"Cobertura de sentencias: {sentencias:.2f} % ({t['covered_lines']} de {t['num_statements']}; sin cubrir {t['missing_lines']})")
    print(f"Cobertura de ramas:      {ramas:.2f} % ({t.get('covered_branches', 0)} de {t.get('num_branches', 0)})")
    if sentencias < args.minimo:
        fallos.append(f"la cobertura de sentencias del proyecto {sentencias:.2f} % es menor que el mínimo {args.minimo:.0f} %")

    # 2. Capas exigidas por la Unidad 5.
    for capa in args.capa or list(CAPAS_POR_OMISION):
        r = resumen_capa(archivos, capa)
        print()
        if r["sentencias"] == 0:
            print(f"[{capa}] sin sentencias medidas en el informe.")
            fallos.append(f"la capa {capa} no aparece medida en el informe (revise --cov y .coveragerc)")
            continue
        pct = _porcentaje(r["cubiertas"], r["sentencias"])
        pct_ramas = _porcentaje(r["ramas_cubiertas"], r["ramas"])
        print(f"[{capa}] sentencias: {pct:.2f} % ({r['cubiertas']} de {r['sentencias']}; sin cubrir {r['sin_cubrir']}) "
              f"en {r['archivos']} módulos")
        print(f"[{capa}] ramas:      {pct_ramas:.2f} % ({r['ramas_cubiertas']} de {r['ramas']})")
        if r["pendientes"]:
            print(f"[{capa}] módulos con líneas o ramas sin cubrir:")
            for ruta, pct_mod, faltan, ramas_faltan in sorted(r["pendientes"], key=lambda x: x[1]):
                detalle = f"líneas {_lineas(faltan)}" if faltan else "sin líneas pendientes"
                print(f"    {pct_mod:6.2f} %  {ruta}: {detalle}; ramas sin cubrir: {ramas_faltan}")
        if pct < args.minimo_capa:
            fallos.append(f"la cobertura de sentencias de {capa} {pct:.2f} % es menor que el mínimo {args.minimo_capa:.0f} %")

    print()
    if fallos:
        for f in fallos:
            print(f"FALLO: {f}.", file=sys.stderr)
        return 1
    print(f"OK: el proyecto cumple el mínimo de {args.minimo:.0f} % y cada capa exigida el de {args.minimo_capa:.0f} %.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
