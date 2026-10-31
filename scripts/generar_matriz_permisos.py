"""Genera docs/SEGURIDAD_MATRIZ_PERMISOS.md: qué rol puede ejecutar cada operación de la API (sale de `application.seguridad`, la misma matriz que la API aplica).

    python scripts/generar_matriz_permisos.py              # escribe el documento
    python scripts/generar_matriz_permisos.py --comprobar  # sale con 1 si no está al día"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from application.seguridad import ADMINISTRADOR, COORDINADOR, MATRIZ, PERMISOS_POR_ROL, PROVEEDOR, PUBLICAS, SESION, autoriza   # noqa: E402

DESTINO = RAIZ / "docs" / "SEGURIDAD_MATRIZ_PERMISOS.md"
GRUPOS = [("Eventos", ("/eventos", "/solicitudes", "/servicios-pendientes-confirmacion")), ("Propuestas", ("/propuestas",)),
          ("Contratos", ("/contratos",)), ("Pagos y devoluciones", ("/estados-cuenta", "/pagos-pendientes", "/devoluciones-pendientes")),
          ("Solicitudes de cambio", ("/solicitudes-cambio",)), ("Servicios adicionales", ("/solicitudes-servicio-adicional",)),
          ("Sustituciones de proveedor", ("/sustituciones",)), ("Proveedores", ("/proveedores",)),
          ("Sesión y cuentas (administración)", ("/auth", "/usuarios"))]
PROPIO = {("GET", "/proveedores/{proveedor_id}"), ("GET", "/proveedores/{proveedor_id}/eventos/{evento_id}"),
          ("POST", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/respuesta-proveedor")}


def _grupo(ruta: str) -> str:
    if ruta.startswith("/eventos/") and ("/servicios/" in ruta):
        return "Proveedores"
    for nombre, prefijos in GRUPOS:
        if any(ruta == p or ruta.startswith(p + "/") for p in prefijos):
            return nombre
    return "Otras"


def generar() -> str:
    L = ["# Matriz de roles y permisos (generada)", "",
         "> Documento **generado** por `scripts/generar_matriz_permisos.py` a partir de `src/application/seguridad.py`: es la misma matriz que la API aplica. "
         "No editar a mano (la prueba `tests/test_seguridad_documentacion.py` comprueba que está al día). Contexto y decisiones: `docs/SEGURIDAD_Y_PERMISOS.md`.", "",
         "Leyenda: **✔** permitido · **—** denegado (HTTP 403) · **propio** permitido solo sobre el recurso de la propia cuenta (un proveedor solo accede a su proveedor). "
         "Sin sesión toda operación protegida responde HTTP 401. Una ruta que no figura en la matriz se deniega.", "",
         "## Permisos por rol", "", "| Rol | Permisos |", "|---|---|"]
    for rol in (ADMINISTRADOR, COORDINADOR, PROVEEDOR):
        L.append(f"| {rol} | {', '.join(f'`{p}`' for p in sorted(PERMISOS_POR_ROL[rol]))} |")
    L += ["", "## Operaciones públicas (sin sesión)", "", "| Método | Ruta | Motivo |", "|---|---|---|"]
    motivos = {("GET", "/"): "Identificación de la aplicación", ("GET", "/health"): "Sonda de vida (sin datos sensibles)",
               ("GET", "/ready"): "Sonda de disponibilidad (solo «ok» y el modo de persistencia)", ("POST", "/auth/inicio-sesion"): "Inicio de sesión (valida las credenciales; limitado por intentos)"}
    for m, r in sorted(PUBLICAS, key=lambda x: (x[1], x[0])):
        L.append(f"| {m} | `{r}` | {motivos[(m, r)]} |")
    L += ["", "Además se sirve la interfaz estática en `/app/` (HTML, CSS y JavaScript sin datos de negocio) y, fuera de producción, `/docs`, `/redoc` y `/openapi.json`.", ""]
    por_grupo = {}
    for (m, r), req in MATRIZ.items():
        por_grupo.setdefault(_grupo(r), []).append((m, r, req))
    for nombre, _ in GRUPOS:
        filas = sorted(por_grupo.get(nombre, []), key=lambda x: (x[1], x[0]))
        if not filas:
            continue
        L += [f"## {nombre}", "", "| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |", "|---|---|---|:-:|:-:|:-:|"]
        for m, r, req in filas:
            celdas = []
            for rol in (ADMINISTRADOR, COORDINADOR, PROVEEDOR):
                ok = autoriza(rol, m, r)
                celdas.append(("propio" if (m, r) in PROPIO else "✔") if ok else "—")
            perm = "sesión" if SESION in req else " o ".join(f"`{p}`" for p in sorted(req))
            L.append(f"| {m} | `{r}` | {perm} | {celdas[0]} | {celdas[1]} | {celdas[2]} |")
        L.append("")
    L.append(f"Total de operaciones protegidas: **{len(MATRIZ)}**; públicas: **{len(PUBLICAS)}**.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comprobar", action="store_true")
    a = ap.parse_args()
    texto = generar()
    if a.comprobar:
        if not DESTINO.exists() or DESTINO.read_text(encoding="utf-8") != texto:
            print("La matriz de permisos no está al día: ejecute scripts/generar_matriz_permisos.py")
            return 1
        print("Matriz de permisos al día.")
        return 0
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
