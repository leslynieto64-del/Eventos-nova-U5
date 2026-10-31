"""Genera docs/architecture/trazabilidad-api-persistencia.md: cada ruta de la API → método de servicio o consulta que invoca →
fila(s) de la MATRIZ DE TRAZABILIDAD APROBADA (docs/trazabilidad/matriz-trazabilidad.xlsx) que nombran ese método (BN, US/CA, CU) y
reglas (CU, US, CA, BN, SE, GL) que el propio código del método cita.

    python scripts/generar_trazabilidad_api.py              # escribe el documento
    python scripts/generar_trazabilidad_api.py --comprobar  # sale con 1 si el documento no está al día

No inventa ni audita requisitos: lo que la matriz aprobada no nombra aparece como «(sin fila propia en la matriz)»."""
import argparse
import html
import importlib
import inspect
import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
DESTINO = RAIZ / "docs" / "architecture" / "trazabilidad-api-persistencia.md"
MATRIZ = RAIZ / "docs" / "trazabilidad" / "matriz-trazabilidad.xlsx"
MODULOS = ["rutas_propuestas", "rutas_contratacion", "rutas_pagos", "rutas_eventos", "rutas_solicitudes", "rutas_consultas", "rutas_proveedores"]
ETIQUETA = re.compile(r"\b(?:CU|US|CA|BN|SE|GL)-\d+[A-Za-z]?\b")
PATRONES = (("servicios", re.compile(r"servicios\.(\w+)\.(\w+)\(")), ("queries", re.compile(r"queries\.(\w+)\.handle")),
            ("commands", re.compile(r"commands\.(\w+)\.handle")))
SERVICIO_INYECTADO = re.compile(r"\bservicio\.(\w+)\(")       # rutas de CU-01: el servicio llega por inyección de dependencias
SIN_FILA = "(sin fila propia en la matriz)"
USER_STORIES = RAIZ / "docs" / "unidad 2" / "User_Stories_corregido.docx"
CIERRE = RAIZ / "Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md"
# Operaciones técnicas: no corresponden a ninguna historia de usuario (observabilidad y descubrimiento de la API).
TECNICAS = {("GET", "/"): "Identificación de la aplicación", ("GET", "/health"): "Comprobación de vida del proceso",
            ("GET", "/ready"): "Comprobación de disponibilidad (conexión y esquema de la base de datos)"}
# Respaldo documental de las rutas que la matriz aprobada no nombra. SOLO se registra lo que el texto de las fuentes aprobadas dice
# de forma explícita (User Stories corregidas y cierre de alcance); `generar()` comprueba que cada identificador citado exista en
# ellas. «Nota» indica qué parte del respaldo es parcial. Ninguna historia se asigna por semejanza.
# (método, ruta) -> (clasificación, historias, criterios de aceptación, nota)
RESPALDO = {
    ("POST", "/solicitudes-cambio/{solicitud_id}/solicitud-pago"): ("Negocio", "US-024", "CA-062, CA-063", "US-024: «solicitar y dar seguimiento al pago de los nuevos importes»"),
    ("POST", "/sustituciones/{sustitucion_id}/importe-adicional"): ("Negocio", "US-021", "CA-052", "CA-052: el costo adicional se incorpora al saldo general"),
    ("POST", "/eventos/{evento_id}/cancelacion-por-falta-de-regularizacion"): ("Negocio", "US-027, US-028", "CA-091", "CA-091 y US-028: cancelación registrada por el Coordinador por falta de liquidación del saldo"),
    ("GET", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/disponibilidad"): ("Negocio", "US-013", "CA-029", ""),
    ("POST", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/proveedor"): ("Negocio", "US-014", "CA-030, CA-031", ""),
    ("POST", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/respuesta-proveedor"): ("Negocio", "US-016", "", "US-016: el Proveedor confirma su disponibilidad y las condiciones; no hay un criterio de aceptación propio en esta lista"),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/decision-espera"): ("Negocio", "US-025", "CA-076, CA-077, CA-078", ""),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/cierre-por-falta-de-pago"): ("Negocio", "US-025", "CA-082", "CA-082: plazo de 24 horas desde la comunicación y confirmación solo con pago verificado; el cierre por falta de pago lo modela el BPMN SP-04 («¿El Cliente efectuó el pago dentro de las 24 horas?» → «Cerrar la solicitud por falta de pago…»); ninguna User Story ni criterio de aceptación enumera el cierre de forma literal"),
    ("POST", "/sustituciones"): ("Negocio", "US-021", "CA-096", "US-021: registrar que un proveedor no está disponible o cancela"),
    ("POST", "/sustituciones/{sustitucion_id}/anexo"): ("Negocio", "US-021", "CA-051, CA-053", ""),
    ("GET", "/eventos"): ("Negocio (consulta)", "US-022", "CA-058", "CA-058: identificar los eventos próximos"),
    ("GET", "/eventos/{evento_id}/administracion"): ("Negocio (consulta)", "US-022", "CA-055, CA-057", ""),
    ("GET", "/eventos/{evento_id}/solicitudes-pendientes"): ("Negocio (consulta)", "US-022", "CA-058", "US-022: «revisar las solicitudes pendientes»"),
    ("GET", "/proveedores/{proveedor_id}/eventos/{evento_id}"): ("Negocio (consulta)", "US-015", "", "US-015: el Proveedor consulta la información del evento y del servicio asignado"),
    ("GET", "/solicitudes"): ("Negocio (consulta)", "US-022", "CA-058", "CA-058: solicitudes distinguidas por estado"),
    ("GET", "/pagos-pendientes"): ("Negocio (consulta)", "US-011", "CA-026, CA-058", ""),
    ("GET", "/devoluciones-pendientes"): ("Negocio (consulta)", "US-031, US-032", "CA-058", "Cierre de alcance C-13: consultas de devoluciones pendientes, con fechas límite y vencimientos"),
    ("GET", "/servicios-pendientes-confirmacion"): ("Negocio (consulta)", "US-012", "CA-028", ""),
    ("POST", "/proveedores"): ("Sin respaldo documental suficiente", "", "", "Extensión D-P1 (catálogo de proveedores): el BRD (BN-004) pide conocer los proveedores asignados, pero ninguna US aprobada describe su alta ni su consulta; pendiente de aprobación del equipo"),
    ("GET", "/proveedores"): ("Sin respaldo documental suficiente", "", "", "Extensión D-P1 (catálogo de proveedores): el BRD (BN-004) pide conocer los proveedores asignados, pero ninguna US aprobada describe su alta ni su consulta; pendiente de aprobación del equipo"),
    ("GET", "/proveedores/{proveedor_id}"): ("Sin respaldo documental suficiente", "", "", "Extensión D-P1 (catálogo de proveedores): el BRD (BN-004) pide conocer los proveedores asignados, pero ninguna US aprobada describe su alta ni su consulta; pendiente de aprobación del equipo"),
}


# Elementos de los BPMN aprobados que respaldan una ruta: (archivo, nombres de elementos que deben existir en el diagrama).
BPMN_RESPALDO = {
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/cierre-por-falta-de-pago"): (
        "diagramas/bpmn/BPMN_Eventos_Nova_SP04_Servicio_adicional.bpmn",
        ["¿El Cliente efectuó el pago dentro de las 24 horas?", "Cerrar la solicitud por falta de pago, registrar el motivo e informar al Cliente",
         "Registrar y verificar el pago, aunque sea después de las 24 horas"]),
}


def _identificadores_de_las_fuentes() -> str:
    texto = zipfile.ZipFile(USER_STORIES).read("word/document.xml").decode("utf-8")
    return html.unescape(re.sub(r"<[^>]+>", " ", texto)) + CIERRE.read_text(encoding="utf-8")


def verificar_respaldo() -> None:
    """Cada US, CA o regla citada en RESPALDO debe existir en las fuentes aprobadas; si no, el generador falla."""
    fuentes = _identificadores_de_las_fuentes()
    for clave, (_, historias, criterios, nota) in RESPALDO.items():
        for ident in ETIQUETA.findall(" ".join((historias, criterios))):
            if ident not in fuentes:
                raise RuntimeError(f"{clave}: {ident} no figura en las fuentes aprobadas")
        bpmn = BPMN_RESPALDO.get(clave)
        if bpmn:
            diagrama = html.unescape((RAIZ / bpmn[0]).read_text(encoding="utf-8"))
            for nombre in bpmn[1]:
                if nombre not in diagrama:
                    raise RuntimeError(f"{clave}: el BPMN {bpmn[0]} no contiene «{nombre}»")
        if "C-13" in nota and "| C-13 |" not in fuentes:
            raise RuntimeError(f"{clave}: C-13 no figura en el cierre de alcance")


def a_snake(nombre: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", nombre).lower()


def leer_matriz():
    """[(bn, us_ca, cu, componentes)] de la hoja única de la matriz aprobada (celdas con texto en línea)."""
    hoja = zipfile.ZipFile(MATRIZ).read("xl/worksheets/sheet1.xml").decode("utf-8")
    filas = []
    for fila in re.findall(r"<row [^>]*>(.*?)</row>", hoja, flags=re.S)[4:]:
        celdas = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", c, flags=re.S)))
                  for c in re.findall(r"<c [^>]*?(?:/>|>.*?</c>)", fila, flags=re.S)]
        if len(celdas) >= 5:
            filas.append((celdas[0], celdas[2], celdas[3], celdas[4]))
    return filas


def indice_de_metodos(filas):
    """{método en snake_case o clase de consulta: [filas]} a partir de los nombres que cita la columna de componentes."""
    indice = {}
    for fila in filas:
        componentes = fila[3]
        nombres = {a_snake(m) for m in re.findall(r"\b([a-z][A-Za-z]+)\(\)", componentes)}
        nombres |= {m.replace("Query", "") for m in re.findall(r"\b(Consultar\w+Query)\b", componentes)}
        for n in nombres:
            indice.setdefault(n, []).append(fila)
    return indice


def etiquetas(fuente: str) -> str:
    vistas = sorted(set(ETIQUETA.findall(fuente)), key=lambda e: (e.split("-")[0], int(re.sub(r"\D", "", e.split("-")[1]))))
    return ", ".join(vistas) if vistas else "—"


def resolver(fuente: str, contenedor):
    """(objeto, método, nombre legible, clave de búsqueda en la matriz) de lo que invoca el cuerpo de una ruta."""
    for rama, patron in PATRONES:
        m = patron.search(fuente)
        if m is None:
            continue
        if rama == "servicios":
            objeto = getattr(contenedor.servicios, m.group(1))
            return objeto, getattr(objeto, m.group(2)), f"{type(objeto).__name__}.{m.group(2)}", m.group(2)
        objeto = getattr(getattr(contenedor, rama), m.group(1))
        nombre = type(objeto).__name__
        return objeto, objeto.handle, f"{nombre}.handle", nombre.replace("Handler", "")
    m = SERVICIO_INYECTADO.search(fuente)
    if m:
        objeto = contenedor.servicios.propuestas
        return objeto, getattr(objeto, m.group(1)), f"{type(objeto).__name__}.{m.group(1)}", m.group(1)
    raise RuntimeError("No se pudo determinar qué invoca la ruta:\n" + fuente)


def de_matriz(filas) -> tuple:
    if not filas:
        return SIN_FILA, SIN_FILA, SIN_FILA
    bn = sorted({b for f in filas for b in re.findall(r"BN-\d+", f[0])})
    return (", ".join(bn) or "—", "; ".join(dict.fromkeys(f[1] for f in filas)), ", ".join(sorted({c.strip() for f in filas for c in f[2].split(",")})))


def generar() -> str:
    from infrastructure.composicion import construir
    contenedor = construir()
    indice = indice_de_metodos(leer_matriz())
    filas = []
    for nombre in MODULOS:
        modulo = importlib.import_module(f"api.{nombre}")
        for ruta in modulo.router.routes:
            objeto, metodo, destino, clave = resolver(inspect.getsource(ruta.endpoint), contenedor)
            codigo = inspect.getsource(inspect.unwrap(metodo)) + (inspect.getdoc(type(objeto)) or "")
            bn, us_ca, cu = de_matriz(indice.get(clave))
            for metodo_http in sorted(ruta.methods - {"HEAD", "OPTIONS"}):
                filas.append((nombre.replace("rutas_", ""), metodo_http, ruta.path, destino, bn, us_ca, cu, etiquetas(codigo)))
    verificar_respaldo()
    sin = sum(1 for f in filas if f[4] == SIN_FILA)
    sin_respaldo = [f for f in filas if f[4] == SIN_FILA and (f[1], f[2]) not in RESPALDO]
    if sin_respaldo:
        raise RuntimeError("Rutas sin clasificar: " + ", ".join(f"{f[1]} {f[2]}" for f in sin_respaldo))
    lineas = [
        "# Trazabilidad de la API y la persistencia",
        "",
        "> Documento **generado** por `scripts/generar_trazabilidad_api.py` (no editar a mano; la prueba `test_trazabilidad_api` "
        "comprueba que está al día). Cada ruta llama a **un** método de servicio de aplicación o a un *Query/Command Handler*. "
        "Las columnas BN, US/CA y CU provienen de la **matriz de trazabilidad aprobada** (`docs/trazabilidad/matriz-trazabilidad.xlsx`), "
        "buscando las filas que nombran ese método en su columna «Componentes de arquitectura»; la última columna reúne las "
        "referencias (CU, US, CA, BN, SE, GL) que cita el propio código del método. Las fuentes aprobadas son el BRD, las User Stories, "
        "el glosario y el cierre de alcance (`docs/unidad 2/`, `Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md`). "
        "No se añadió ninguna regla nueva con la API ni con la persistencia.",
        "",
        f"Rutas de negocio: **{len(filas)}**. Con fila propia en la matriz: **{len(filas) - sin}**; sin fila propia: **{sin}** "
        f"(la matriz las agrupa a nivel de servicio o no las nombra; no se les asignó ninguna historia por inferencia).",
        "",
        "Clasificación de cada ruta: **Negocio** (con respaldo en la matriz aprobada o, si la matriz no la nombra, en el texto explícito de "
        "las User Stories o del cierre de alcance, verificado por el generador), **Técnica** (sin historia de usuario) o **Sin respaldo "
        "documental suficiente** (hoy solo las tres rutas del catálogo de proveedores, extensión D-P1 pendiente de aprobación; el generador falla si apareciera una ruta sin clasificar). «Respaldo directo» lista solo lo que "
        "el texto aprobado dice de forma explícita; una nota indica cuando el respaldo es parcial.",
        "",
        "| Grupo | Método | Ruta | Servicio o consulta que invoca | BN (matriz) | US / CA (matriz) | CU (matriz) | Citadas en el código | Clasificación | Respaldo directo (US · CA) y nota |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for grupo, metodo_http, ruta, destino, bn, us_ca, cu, citas in filas:
        if bn == SIN_FILA:
            clase, hist, crit, nota = RESPALDO[(metodo_http, ruta)]
            respaldo = " · ".join(x for x in (hist, crit) if x) + (f" — {nota}" if nota else "")
        else:
            clase, respaldo = "Negocio", "Fila de la matriz aprobada"
        lineas.append(f"| {grupo} | {metodo_http} | `{ruta}` | `{destino}` | {bn} | {us_ca} | {cu} | {citas} | {clase} | {respaldo} |")
    lineas += ["", "## Operaciones técnicas (sin historia de usuario)", "", "| Método | Ruta | Propósito |", "|---|---|---|"]
    lineas += [f"| {m} | `{r}` | {p} |" for (m, r), p in TECNICAS.items()]
    lineas += [
        "",
        "## Capas de integridad que intervienen en cada operación",
        "",
        "| Capa | Qué garantiza | Dónde |",
        "|---|---|---|",
        "| Entrada (API) | Forma y tipo del dato: números que son números, booleanos estrictos, fechas sin zona, campos obligatorios y sin campos desconocidos | `src/api/esquemas*.py` |",
        "| Dominio | Invariantes y reglas de negocio aprobadas (importe finito y no negativo, estados, plazos) | `src/domain/` |",
        "| Aplicación | Existencia de las referencias que no tienen clave foránea; orden de las operaciones y límites transaccionales (ADR-004) | `src/application/servicios.py` |",
        "| PostgreSQL | `CHECK`, `NOT NULL`, `UNIQUE` y claves foráneas (incluidas las compuestas de versión vigente/aceptada) | `migraciones/versions/` |",
        "",
        "Las referencias sin clave foránea y sus límites de protección están en la sección 13.1 de `esquema-relacional-postgresql.md`; "
        "la coherencia solicitud–contrato–evento (riesgo C-02 de la auditoría) se valida desde la decisión de implementación E-2 del equipo "
        "(HTTP 422 en los tres registros), sin aprobación formal todavía. Las filas de la "
        "matriz aprobada marcadas como «pendiente de implementación» (decisión A: devolución del anticipo por contratación cerrada; "
        "decisión B: anticipo superior al 30 %) **quedaron implementadas y probadas en la fase final** "
        "(`docs/trazabilidad/complemento-trazabilidad-fase-final.md`). La matriz solo se actualizó el 2026-10-29 en las columnas de componentes y de ADR para describir la implementación vigente (D-1, D-2, D-3, decisiones A y B); sus necesidades, reglas, historias, criterios y casos de uso no cambiaron.",
        "",
        "## Decisiones de implementación E-1 a E-4 (después de la auditoría final)",
        "",
        "El equipo eligió estas interpretaciones para cerrar las preguntas abiertas de la auditoría. **E-2, E-3 y E-4 no tienen "
        "aprobación formal registrada ni respaldo explícito en las fuentes originales**; E-1 aplica una regla ya aprobada (GL-060 / C-15).",
        "",
        "| Decisión | Operaciones HTTP afectadas | Efecto | Pruebas | Aprobación |",
        "|---|---|---|---|---|",
        "| E-1 · GL-060 / C-15 en todos los plazos en días hábiles | `POST /contratos/{id}/seguimiento-anticipo`, `POST /estados-cuenta/{id}/pagos`, `POST /estados-cuenta/{id}/vencimiento-saldo-original`, `POST /sustituciones/{id}/autorizacion`, devoluciones | Anticipo, seguimiento, saldo, límite de sustitución y devoluciones (anticipo y SE-012) vencen a las 00:00 del día siguiente al último día del plazo; las ventanas de horas y los días naturales no cambian | `tests/test_plazos_dias_habiles_gl060_e1.py`, `tests/test_oraculo_diferencias_e1_e4.py` | Regla aprobada (cierre C-15). **Pendiente:** recalcular el oráculo histórico, que el cierre prohíbe editar a mano |",
        "| E-2 · el evento de la solicitud debe ser el del contrato | `POST /solicitudes-cambio`, `POST /solicitudes-servicio-adicional`, `POST /sustituciones` | HTTP 422 `rechazo_de_negocio` antes de crear o modificar nada; sin claves foráneas nuevas | `tests/test_coherencia_solicitud_contrato_evento.py` (memoria y PostgreSQL), `tests/test_persistencia_referencias.py` | **Decisión del equipo, sin aprobación formal** |",
        "| E-3 · el anticipo mínimo puede sumarse con pagos parciales | `POST /estados-cuenta/{id}/pagos`, `POST /estados-cuenta/{id}/pagos/{pago_id}/verificacion` | Un pago de anticipo menor al 30 % queda Registrado o Verificado como parcial; la obligación se liquida cuando lo verificado suma el mínimo; un comprobante repetido en la misma obligación se rechaza | `tests/test_anticipo_pagos_parciales_e3_e4.py` | **Decisión del equipo, sin aprobación formal** |",
        "| E-4 · pago menor al 30 % tras liquidar el anticipo | `POST /estados-cuenta/{id}/pagos` | Se registra y verifica como adicional: no se devuelve, no se aplica al saldo y no altera la liquidación | `tests/test_anticipo_pagos_parciales_e3_e4.py` | **Decisión del equipo, sin aprobación formal** |",
        "",
    ]
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comprobar", action="store_true")
    args = parser.parse_args()
    texto = generar()
    if args.comprobar:
        actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if actual != texto:
            print("El documento de trazabilidad no está al día: ejecute scripts/generar_trazabilidad_api.py", file=sys.stderr)
            return 1
        print("Trazabilidad al día.")
        return 0
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
