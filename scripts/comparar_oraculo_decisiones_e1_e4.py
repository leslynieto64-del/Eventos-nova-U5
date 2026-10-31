"""Contabiliza, en SOLO LECTURA, las diferencias intencionales entre el comportamiento actual de EstadoCuenta y el oráculo histórico
`tests/referencias/comportamiento_estado_cuenta_v8_e3c.json`, con los identificadores de clave por regla (E-1, H-10, E-3/E-4).

    python scripts/comparar_oraculo_decisiones_e1_e4.py

No escribe el JSON de referencia ni ningún archivo. Los esperados salen de `tests/apoyo_esperados_oraculo.py` (derivado de las reglas,
sin código de producción). Reconciliación de cifras: el recuento histórico «1203 claves» es el número de claves del oráculo; las 1204
subpruebas fallidas de la versión anterior de la prueba eran esas 1203 más la aserción final `afectadas == 42`, que fallaba aparte."""
import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "tests"), str(RAIZ / "src")]
import apoyo_maquina_estados_estado_cuenta as A                                    # noqa: E402
from apoyo_esperados_oraculo import esperado                                       # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with open(A.RUTA_REFERENCIA_ESTADO_CUENTA, encoding="utf-8") as f:
        referencia = json.load(f)
    actual = json.loads(json.dumps(A.capturar_comportamiento_estado_cuenta(), ensure_ascii=False))
    print(f"Claves del oráculo: {len(referencia)}; claves actuales: {len(actual)}; mismas claves: {set(referencia) == set(actual)}")
    por_regla, combinacion, no_coinciden = {}, Counter(), []
    for clave, ref in referencia.items():
        esp, reglas = esperado(clave, ref)
        for r in reglas:
            por_regla.setdefault(r, []).append(clave)
        combinacion[tuple(sorted(reglas))] += 1
        if actual[clave] != esp:
            no_coinciden.append(clave)
    distintas_del_oraculo = sum(1 for k in referencia if actual[k] != referencia[k])
    print(f"Claves cuyo resultado actual difiere del oráculo: {distintas_del_oraculo}")
    print(f"Claves cuyo resultado actual NO coincide con el esperado por regla: {len(no_coinciden)}")
    for k in no_coinciden:
        print(f"  ! {k}")
    print("\nClaves por combinación de reglas:")
    for c, n in sorted(combinacion.items()):
        print(f"  {n:5d}  {' + '.join(c) or '(ninguna: idéntica al oráculo)'}")
    print("\nClaves afectadas por cada regla:")
    for r in ("E-1", "H-10", "E-3/E-4", "D-2"):
        print(f"  {r}: {len(por_regla.get(r, []))}")
    print("\nIdentificadores (H-10 y E-3/E-4; E-1 afecta a las 1203, sin lista):")
    for r in ("H-10", "E-3/E-4"):
        print(f"\n[{r}] {len(por_regla.get(r, []))} claves")
        for k in sorted(por_regla.get(r, [])):
            print(f"  {k}")
    return 0 if not no_coinciden else 1


if __name__ == "__main__":
    sys.exit(main())
