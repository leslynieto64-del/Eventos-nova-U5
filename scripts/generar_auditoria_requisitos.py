"""Genera docs/trazabilidad/auditoria-requisitos-fase-final.md: requisito → fuente → implementación → pruebas → estado.

    python scripts/generar_auditoria_requisitos.py            # escribe el documento
    python scripts/generar_auditoria_requisitos.py --comprobar

Distingue tres cosas que no son lo mismo: regla APROBADA (está en las fuentes), regla IMPLEMENTADA (el código la cita o la
realiza) y regla con PRUEBA (alguna prueba la nombra o ejercita la operación). «Pasa» se refiere a la última ejecución de la suite
completa registrada en tests/evidencias; este generador NO ejecuta las pruebas. Un identificador citado en código o prueba es evidencia
de intención, no una demostración: por eso la columna «Estado» es prudente y las brechas conocidas están declaradas a mano."""
import argparse
import html
import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "trazabilidad" / "auditoria-requisitos-fase-final.md"
BRD = RAIZ / "docs" / "unidad 2" / "Reporte_BRD_Corregido.docx"
CIERRE = RAIZ / "Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md"
EVIDENCIA = "tests/evidencias/ejecucion-docker-final-20261028-202102.txt"

# Reglas del cierre de alcance: id → (módulos o funciones que la implementan, términos que identifican sus pruebas, estado manual o None)
REGLAS = {
    "A-1…A-6": ("EstadoCuenta.aplicar_cierre_contratacion, _devolver_anticipo; Devolucion.fecha_limite", ["aplicar_cierre_contratacion", "ANTICIPO_CONTRATACION_CERRADA"], None),
    "B-1…B-5": ("EstadoCuenta.registrar_y_verificar_pago, anticipo_aplicado, anticipo_excedente", ["anticipo_excedente", "B_ElAnticipoEsUnMinimo"], None),
    "E-3 / E-4 (decisiones del equipo)": (
        "EstadoCuenta.registrar_y_verificar_pago, _anticipo_acumulado, anticipo_verificado / anticipo_efectuado_hasta / anticipo_recibido (suma de pagos); control de comprobante repetido",
        ["pagos_parciales", "E3_", "E4_"],
        "DECISIÓN DE IMPLEMENTACIÓN DEL EQUIPO, SIN APROBACIÓN FORMAL: las fuentes no tratan la suma de pagos parciales (E-3) ni un pago menor al 30 % sobre un anticipo liquidado (E-4); el equipo eligió sumar y aceptar como adicional. Requiere aprobación formal del responsable"),
    "C-1…C-4": ("Sin devolución al cancelar (EstadoCuenta.aplicar_cierre_sin_realizar con Evento cancelado)", ["C_NoHayReembolsoAlCancelarElEvento"], None),
    "C-01": ("GestionCierreEventoService.procesar_inicio_evento, _cerrar_por_llegada_de_t y procesar_eventos_vencidos (proceso periódico en trabajador_outbox.ejecutar); Contrato.cerrar_por_inicio; reacción a ProcesoContratacionCerrado", ["procesar_eventos_vencidos", "llegada_de_t", "D3_"],
             "Aprobada · Implementada · Con pruebas (corrección D-3 del 2026-10-28). **Decisiones internas del equipo sin aprobación externa:** el contrato Firmado también se cierra al llegar T (las fuentes dicen «contrato no firmado»), aviso a Cliente, Coordinador y Administración, y rechazo de la confirmación con `ahora ≥ T` (D-3b). T se compara con el reloj de negocio America/Mexico_City sin zona (`reloj_negocio`, TP-06 aprobado; no es una decisión interna). Ver CIERRE_AUDITORIA_FINAL.md §O, §P y §Q"),    "C-02": ("ReaccionesSolicitudes.al_iniciarse_evento; cerrar_*_por_inicio_evento", ["por_inicio_evento"],
             "Aprobada · Implementada · Con pruebas: las solicitudes se cierran al registrarse el inicio, que desde la corrección D-3 hace el trabajador al llegar T (`test_d3_llegada_de_t`) o la operación explícita"),    "E-2 (decisión del equipo)": (
        "servicios._exigir_evento_del_contrato en registrar_solicitud_cambio, registrar_solicitud_servicio_adicional y registrar_proveedor_no_disponible (HTTP 422, sin cambios)",
        ["coherencia_solicitud_contrato_evento"],
        "DECISIÓN DE IMPLEMENTACIÓN DEL EQUIPO, SIN APROBACIÓN FORMAL: ninguna fuente exige que el evento de la solicitud sea el del contrato. Requiere aprobación formal del responsable"),
    "C-03": ("FormalizarContratacionService.dar_seguimiento_anticipo_pendiente; Contrato.cerrar_sin_confirmar", ["dar_seguimiento_anticipo_pendiente"], None),
    "C-04": ("EstadoCuenta.aplicar_cierre_contratacion (Pendiente → Sin efecto; Liquidado se conserva)", ["aplicar_cierre_contratacion"], None),
    "C-05": ("ObligacionPago por concepto y origen; EstadoCuenta.solicitud_liquidada", ["comunicar_solicitud_pago_cambio", "solicitud_liquidada"], None),
    "C-06": ("EstadoCuenta._destinos_verificacion y _pagado_para_liquidar (un pago posterior al límite no liquida el saldo); registrar_vencimiento_saldo (ND-29)", ["registrar_vencimiento_saldo", "pago_tardio_del_saldo"],
             "Aprobada · Implementada · Con pruebas (corrección D-2 del 2026-10-28; el oráculo se valida con la regla D-2, 48 claves). **Decisión interna del equipo sin aprobación externa:** un pago tardío completo deja el saldo Pendiente (no Vencida) hasta que se registre el vencimiento, que ahora puede registrarse; el bloqueo de solicitudes nuevas usa el vencimiento de hecho (`EstadoCuenta.saldo_vencido_en`, GL-049, SE-006), con o sin registro previo. Ver CIERRE_AUDITORIA_FINAL.md §O y §P"),    "C-07": ("EstadoCuenta.activar_protocolo_cobro, resolver_regularizacion", ["resolver_regularizacion", "activar_protocolo_cobro"], None),
    "C-08": ("Evento.solicitar_cancelacion; GestionCierreEventoService (cancelación del Cliente)", ["solicitar_cancelacion", "registrar_cancelacion"], None),
    "C-09": ("SolicitudCambio/ServicioAdicional/Sustitucion.cerrar_por_cancelacion_evento; ReaccionesSolicitudes.al_cancelarse_evento", ["cerrar_por_cancelacion_evento"], None),
    "C-10": ("EstadoCuenta.aplicar_cierre_sin_realizar; _verificar_pago_de_solicitud_cerrada", ["aplicar_cierre_sin_realizar"], None),
    "C-11": ("Devolución SE-012 (aplicar_cierre_sin_realizar) y del anticipo (aplicar_cierre_contratacion); una devolución por pago", ["registrar_y_ejecutar_devolucion", "uq_devolucion_pago"], None),
    "C-12": ("Evento.revision_administrativa (constancia de no reembolso)", ["constancia_no_reembolso", "revision_administrativa"], None),
    "C-13": ("ConsultarPagosPendientesHandler, ConsultarDevolucionesPendientesHandler (sin obligaciones Sin efecto)", ["Consultar", "pagos_pendientes", "devoluciones_pendientes"], None),
    "C-14": ("GestionServiciosAdicionalesService.registrar_solicitud_servicio_adicional: rechaza (Resultado.rechazo, HTTP 422) si el contrato del evento no está en «Contratación confirmada», antes de crear la solicitud y sin evaluar plazo ni saldo; corrección D-1 del 2026-10-28",
             ["registrar_solicitud_servicio_adicional", "D1_", "contratacion_confirmada"], None),
    "C-15 / GL-060": (
        "Todos los plazos en días hábiles (anticipo, seguimiento, saldo, límite de sustitución, devolución del anticipo y SE-012): PlazoPago.dias_habiles / dias_habiles_antes_de, limite_exclusivo_dias_habiles(_antes), Devolucion.fecha_limite",
        ["plazos_dias_habiles_gl060_e1", "limite_exclusivo", "fecha_limite"],
        "IMPLEMENTADO (decisión E-1) y probado. El oráculo histórico (`comportamiento_estado_cuenta_v8_e3c.json`) NO se editó: se conserva y cada clave se compara con su esperado derivado de las reglas (E-1, H-10, E-3/E-4; `tests/apoyo_esperados_oraculo.py`), con recuento exacto en `tests/evidencias/diferencias-oraculo-e1-e4-20261025.txt`. PENDIENTE DE AUTORIZACIÓN: que la responsable apruebe formalmente este método de validación (el cierre §6 no define esperados para E-1/E-3/E-4)"),
}

# Requisitos del BRD cuya implementación no cita el identificador pero que se cubren por diseño o por otra operación.
MANUAL_BRD = {
    "BN-001": "Agregado Evento (datos, servicios, estado, historial de solicitudes) y consultas de Evento",
    "SE-002": "Se tramita como SolicitudCambio con datos propuestos (invitados): SolicitudCambio.registrar_viabilidad con los proveedores; sin cita explícita del identificador",
    "SE-008": "SolicitudCambio.registrar_viabilidad con resultado no viable: se informa al Cliente y se conserva la última configuración confirmada; sin cita explícita del identificador",
}


def _texto_docx(ruta: Path) -> str:
    x = zipfile.ZipFile(ruta).read("word/document.xml").decode("utf-8")
    x = re.sub(r"</w:p>", "\n", x)
    return html.unescape(re.sub(r"<[^>]+>", "", x))


def _definiciones_brd() -> dict:
    lineas = [l.strip() for l in _texto_docx(BRD).splitlines()]
    salida = {}
    for i, l in enumerate(lineas):
        if re.fullmatch(r"(BN|SE)-\d{3}", l) and l not in salida:
            resto = [x for x in lineas[i + 1:i + 5] if x]
            salida[l] = " ".join(resto[:2])[:150]
    return salida


def _archivos(carpeta: str, patron: str) -> list:
    """Archivos de `src` o archivos `test_*.py` de `tests` (los `apoyo_*` son ayudas, no pruebas) que contienen el patrón."""
    rx = re.compile(patron)
    extension = "test_*.py" if carpeta == "tests" else "*.py"
    return sorted(str(p.relative_to(RAIZ)).replace("\\", "/") for p in (RAIZ / carpeta).rglob(extension)
                  if "__pycache__" not in p.parts and rx.search(p.read_text(encoding="utf-8", errors="ignore")))


# Observaciones de concordancia con el comportamiento real (comprobadas por simulación en memoria, 2026-10-28): el estado automático solo
# mira que el código cite el identificador, lo que no demuestra que cumpla la regla.
OBSERVACION_BRD = {
}


def _lista(archivos: list, tope: int = 4) -> str:
    nombres = [a.split("/")[-1] for a in archivos]
    return ", ".join(nombres[:tope]) + (f" (+{len(nombres) - tope})" if len(nombres) > tope else "") if nombres else "—"


def generar() -> str:
    definiciones = _definiciones_brd()
    filas_brd, brechas = [], []
    for ident in sorted(definiciones):
        src, tst = _archivos("src", rf"\b{ident}\b"), _archivos("tests", rf"\b{ident}\b")
        manual = MANUAL_BRD.get(ident)
        if src and tst:
            estado = "Aprobada · Implementada · Con pruebas"
        elif manual and tst:
            estado = "Aprobada · Cubierta por otra operación (sin cita en el código) · Con pruebas"
        elif tst:
            estado = "Aprobada · Con pruebas · Implementación sin cita explícita: revisar"
            brechas.append(ident)
        else:
            estado = "Aprobada · SIN evidencia automática"
            brechas.append(ident)
        if ident in OBSERVACION_BRD:
            estado += " · " + OBSERVACION_BRD[ident]
            brechas.append(ident)
        implementacion = manual or _lista(src)
        filas_brd.append(f"| {ident} | {definiciones[ident]} | {implementacion} | {_lista(tst)} | {estado} |")

    texto_cierre = CIERRE.read_text(encoding="utf-8")
    filas_cierre = []
    for ident, (impl, terminos, manual) in REGLAS.items():
        patron = "|".join(re.escape(t) for t in terminos)
        tst = _archivos("tests", patron)
        estado = manual or ("Aprobada · Implementada · Con pruebas" if tst else "Aprobada · Implementada · SIN pruebas identificables")
        if manual:
            brechas.append(ident)
        existe = ident.split("…")[0].split(" ")[0] in texto_cierre
        filas_cierre.append(f"| {ident} | {'Cierre de alcance' if existe else 'Cierre (agrupada)'} | {impl} | {_lista(tst)} | {estado} |")

    return "\n".join([
        "# Auditoría de requisitos y reglas de negocio — fase final (Etapa 7)",
        "",
        "> Documento **generado** por `scripts/generar_auditoria_requisitos.py`. Distingue regla *aprobada* (está en las fuentes), regla "
        "*implementada* (el código la cita o la realiza) y regla con *prueba* (alguna prueba la nombra). «Pasa» se refiere a la suite "
        f"completa registrada en `{EVIDENCIA}`; el generador no ejecuta pruebas. Un identificador citado es evidencia de intención, no "
        "una demostración: las brechas conocidas están declaradas a mano.",
        "",
        f"Requisitos del BRD auditados: **{len(filas_brd)}**. Reglas del cierre de alcance: **{len(filas_cierre)}**. "
        f"Requisitos con observación: **{len(brechas)}** ({', '.join(brechas) or 'ninguno'}).",
        "",
        "## Reglas del cierre de alcance aprobado (A, B, C y C-01 a C-15)",
        "",
        "| Regla | Fuente | Implementación | Pruebas | Estado |",
        "|---|---|---|---|---|",
        *filas_cierre,
        "",
        "## Necesidades (BN) y situaciones especiales (SE) del BRD",
        "",
        "| Requisito | Texto aprobado (extracto) | Implementación (módulos que citan el identificador) | Pruebas | Estado |",
        "|---|---|---|---|---|",
        *filas_brd,
        "",
        "## Lectura de los estados",
        "",
        "- **Aprobada · Implementada · Con pruebas:** la fuente existe, el código cita o realiza la regla y al menos una prueba la nombra. "
        "No implica que la prueba cubra todos los casos de la regla.",
        "- **Cubierta por otra operación:** la regla se cumple a través de otro flujo; se indica cuál.",
        "- **BRECHA CONFIRMADA / SIN evidencia:** requieren decisión o trabajo; ver «Pendientes» del informe final.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comprobar", action="store_true")
    args = parser.parse_args()
    texto = generar()
    if args.comprobar:
        actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if actual != texto:
            print("La auditoría no está al día: ejecute scripts/generar_auditoria_requisitos.py", file=sys.stderr)
            return 1
        print("Auditoría al día.")
        return 0
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
