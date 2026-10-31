"""Genera los documentos de entrega del PIA a partir del estado real del proyecto:

    docs/entrega/Reporte_Final_PIA_Eventos_Nova.pdf     (BRD + arquitectura + evidencias + conclusiones)
    docs/entrega/Presentacion_Defensa_Eventos_Nova.pptx (presentación de apoyo para la defensa)

    python scripts/generar_entrega_pia.py

REQUIERE `reportlab` y `python-pptx`, que NO son dependencias de la aplicación (no están en requirements*.txt): instálelos en un
entorno aparte. Las cifras salen de los archivos del repositorio (esquema, OpenAPI, evidencias de pruebas y cobertura) y de las
constantes FIJAS de abajo, que reflejan la última verificación documentada; si cambian, actualícelas. No inventa resultados: lo que
no existe (URL del repositorio, URL del despliegue, ejecución de la CI en GitHub) aparece como «pendiente»."""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
SALIDA = RAIZ / "docs" / "entrega"
FECHA = "29 de octubre de 2026"      # fecha real de generación; actualizar en cada regeneración
# Estado de la repetición manual de T-21 y T-23 (ver docs/pruebas-manuales/GUIA_PRUEBAS_MANUALES_T14_T24.md, sección 11).
# SOLO se cambia cuando el equipo haya ejecutado esas pruebas y registrado sus resultados reales en CIERRE_AUDITORIA_FINAL.md §I;
# mientras tanto el reporte y la presentación NO deben afirmar que T-21 y T-23 quedaron aprobadas.
VALIDACION_MANUAL_T21_T23 = "ejecutadas con el código actualizado y satisfactorias según los resultados informados por el equipo (T-21: cancelación de un evento independiente; T-23: servicio adicional con menos de cinco días, HTTP 201 «No procedente»; T-24: cambio rechazado con HTTP 422 por CA-039 tras el inicio automático); las capturas no están archivadas en el repositorio"


# --------------------------------------------------------------------------- cifras reales
def _leer(ruta: str) -> str:
    datos = (RAIZ / ruta).read_bytes()
    if datos[:2] in (b"\xff\xfe", b"\xfe\xff"):                        # registros de PowerShell en UTF-16
        return datos.decode("utf-16")
    return datos.decode("utf-8", errors="replace")                        # las evidencias de consola pueden venir en cp1252


def cifras() -> dict:
    ejecucion = _leer("tests/evidencias/ejecucion-docker-final-20261028-202102.txt")          # suite completa en Docker con cobertura (última ejecución registrada)
    cobertura = ejecucion
    openapi = json.loads(_leer("docs/api/openapi.json"))
    from infrastructure.esquema_postgresql import metadata
    pruebas = int(re.search(r"Ran (\d+) tests", ejecucion).group(1))
    total = re.search(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)%", cobertura, re.M)
    sentencias, sin_cubrir = int(total.group(1)), int(total.group(2))
    ramas_cubiertas = re.search(r"Cobertura de ramas:\s+([\d.]+) %", cobertura)       # resumen de verificar_cobertura.py
    return {
        "pruebas": pruebas,
        "sentencias": sentencias, "sin_cubrir": sin_cubrir,
        "cobertura_sentencias": round(100 * (sentencias - sin_cubrir) / sentencias, 2),
        "cobertura_ramas": float(ramas_cubiertas.group(1)),
        "operaciones": sum(len(v) for v in openapi["paths"].values()),
        "tablas": len(metadata.tables),
        "fks": sum(len(t.foreign_key_constraints) for t in metadata.tables.values()),
        "migraciones": len(list((RAIZ / "migraciones" / "versions").glob("0*.py"))),
        "adrs": 8, "us": 33, "ca": 114, "bn": 10, "se": 12,
    }


INTEGRANTES = [("Lesly Adamaris Cotlame Nieto", "2226958"), ("Christopher Bethancourt Contreras", "2226948"),
               ("Francisco Mora Ruiz", "2226912")]
PROFESOR = "Miguel Ángel Gómez Marroquín"
CURSO = "Componentes de Lógica de Negocios — Producto Integrador de Aprendizaje (PIA)"

PENDIENTES = [
    "Repositorio GitHub: el repositorio local no tiene remoto; la URL se anota en el README cuando el equipo lo publique.",
    "Despliegue: no se realizó en ninguna plataforma; no existe URL del sistema desplegado. Pasos exactos en docs/architecture/ci-cd-y-despliegue.md.",
    "CI/CD: los workflows están validados estáticamente (actionlint) y sus pasos se ejecutaron localmente; no se han ejecutado en GitHub Actions.",
    "Historial de commits: esta fase no hizo commits ni push; el equipo debe versionar los archivos nuevos antes de la entrega.",
    "E-1 · GL-060 / C-15: aplicado a los seis plazos en días hábiles (límite exclusivo a las 00:00). El oráculo histórico (comportamiento_estado_cuenta_v8_e3c.json) no se editó, porque el cierre de alcance (sección 6) lo prohíbe: cada una de sus 1203 claves se compara con su esperado derivado de las reglas E-1, H-10, E-3/E-4 y D-2 (recuento exacto en tests/evidencias/diferencias-oraculo-d2-20261028.txt). PENDIENTE DE AUTORIZACIÓN: que la responsable apruebe formalmente ese método, porque el cierre no define cómo recalcular el oráculo.",
    "E-2 · coherencia solicitud–contrato–evento: decisión de implementación del equipo, SIN aprobación formal; ninguna fuente original la exige. Si el evento de la solicitud no es el del contrato se rechaza con HTTP 422.",
    "Integraciones externas (pagos, notificaciones, devoluciones, disponibilidad de proveedores): simulaciones documentadas; no hay especificación ni credenciales.",
    "E-3 y E-4 · anticipo mínimo: decisiones de implementación del equipo, SIN aprobación formal y sin respaldo explícito en las fuentes. E-3: el 30 % puede alcanzarse con varios pagos parciales del mismo contrato (antes, un pago menor era «importe incorrecto»). E-4: un pago menor al 30 % después de liquidar el anticipo se verifica como adicional, sin devolverse ni aplicarse al saldo. Detalle en docs/architecture/DECISIONES_E1_E4.md.",
    "Diagramas UML de clases: anteriores a la capa de persistencia; el diagrama por capas de este reporte la incluye.",
    "Defectos D-1, D-2 y D-3 (servicio adicional sin contratación confirmada, pago tardío del saldo e inicio automático en T): corregidos el 28-29/10/2026 con pruebas de regresión y desplegados en las imágenes locales. Contienen decisiones internas del equipo SIN aprobación externa (contrato Firmado cerrado por T y avisos a Cliente, Coordinador y Administración; el reloj America/Mexico_City y el vencimiento de hecho aplican TP-06, GL-049 y SE-006). Detalle en docs/architecture/CIERRE_AUDITORIA_FINAL.md §O a §Q y docs/ADR/ADR-008.",
    "Validación manual: T-21, T-23 y T-24 " + VALIDACION_MANUAL_T21_T23 + ".",
]


# --------------------------------------------------------------------------- PDF
def generar_pdf(c: dict) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether)
    from reportlab.graphics.shapes import Drawing, Rect, String, Line

    fuentes = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("Texto", str(fuentes / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("TextoNegrita", str(fuentes / "arialbd.ttf")))
    pdfmetrics.registerFontFamily("Texto", normal="Texto", bold="TextoNegrita", italic="Texto", boldItalic="TextoNegrita")
    base = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=base["Normal"], fontName="Texto", fontSize=9.5, leading=13.5, spaceAfter=5)
    h1 = ParagraphStyle("h1", parent=normal, fontName="TextoNegrita", fontSize=16, leading=20, spaceBefore=6, spaceAfter=8, keepWithNext=1,
                        textColor=colors.HexColor("#1f3a5f"))
    h2 = ParagraphStyle("h2", parent=normal, fontName="TextoNegrita", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4,
                        textColor=colors.HexColor("#1f3a5f"))
    celda = ParagraphStyle("c", parent=normal, fontSize=8.3, leading=10.8, spaceAfter=0)
    celda_n = ParagraphStyle("cn", parent=celda, fontName="TextoNegrita")
    centro = ParagraphStyle("ce", parent=normal, alignment=TA_CENTER)
    portada_t = ParagraphStyle("pt", parent=centro, fontName="TextoNegrita", fontSize=26, leading=32, textColor=colors.HexColor("#1f3a5f"))

    def P(t, e=normal):
        return Paragraph(t, e)

    def viñetas(items):
        return [Paragraph("•&nbsp;&nbsp;" + i, ParagraphStyle("b", parent=normal, leftIndent=14, firstLineIndent=-10, spaceAfter=2.5)) for i in items]

    def tabla(filas, anchos, cabecera=True):
        datos = [[Paragraph(str(x), celda_n if (cabecera and i == 0) else celda) for x in fila] for i, fila in enumerate(filas)]
        t = Table(datos, colWidths=anchos, repeatRows=1 if cabecera else 0)
        estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c2cc")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                  ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if cabecera:
            estilo.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6edf5")))
        t.setStyle(TableStyle(estilo))
        return t

    def diagrama_capas():
        d = Drawing(480, 235)
        cajas = [("api/  — FastAPI: 60 operaciones REST, errores 409/422/503", 195, "#dbe9f6"),
                 ("application/  — servicios, CQRS (consultas), reacciones, puertos", 150, "#e2f0d9"),
                 ("domain/  — agregados, Value Objects, Specification, State Machine, Domain Events", 105, "#fff2cc"),
                 ("infrastructure/  — repositorios (memoria y SQL), UoW, Outbox, mapeadores, adaptadores simulados", 60, "#fce4d6")]
        for texto, y, color in cajas:
            d.add(Rect(10, y, 460, 36, fillColor=colors.HexColor(color), strokeColor=colors.HexColor("#6b7b8c")))
            d.add(String(18, y + 13, texto, fontName="Texto", fontSize=8.6))
        d.add(Rect(10, 8, 460, 38, fillColor=colors.HexColor("#d9d9d9"), strokeColor=colors.HexColor("#6b7b8c")))
        d.add(String(18, 22, "PostgreSQL 18 (Docker Compose): 22 tablas, Alembic 0001–0004, Outbox persistente", fontName="Texto", fontSize=8.6))
        for y in (231, 186, 141, 96, 51):
            d.add(String(236, y - 6, "▼", fontName="Texto", fontSize=7))
        return d

    historia = []
    # ---- portada
    historia += [Spacer(1, 3 * cm), P("Eventos Nova", portada_t), Spacer(1, 6),
                 P("Reporte final del Producto Integrador de Aprendizaje", ParagraphStyle("s", parent=centro, fontSize=14, leading=18)),
                 Spacer(1, 4), P("BRD · arquitectura · implementación · evidencias · conclusiones", centro), Spacer(1, 1.2 * cm),
                 P(f"<b>{CURSO}</b>", centro), P(f"Profesor: {PROFESOR}", centro), P("Equipo 16", centro), Spacer(1, 0.6 * cm)]
    historia.append(tabla([["Integrante", "Matrícula"]] + [[n, m] for n, m in INTEGRANTES], [11 * cm, 4 * cm]))
    historia += [Spacer(1, 0.8 * cm), P(f"Documento preparado el {FECHA} a partir del estado real del repositorio.", centro),
                 P("Las URL del repositorio y del sistema desplegado figuran como <b>pendientes</b> porque aún no existen.", centro),
                 PageBreak()]

    # ---- 1 resumen
    historia += [P("1. Resumen ejecutivo", h1),
                 P("Eventos Nova es una empresa de organización de eventos (bodas, graduaciones y eventos empresariales). El proyecto "
                   "convierte el análisis de las Unidades 2 y 3 (BRD, User Stories con criterios Gherkin, BPMN y glosario) en una aplicación "
                   "funcional con un modelo de dominio DDD, Specification, State Machine, una API REST documentada y persistencia en PostgreSQL, "
                   "reproducible con Docker Compose.")]
    historia.append(tabla([
        ["Indicador", "Valor", "Evidencia"],
        ["Pruebas automatizadas", f"{c['pruebas']} (unitarias y de integración con PostgreSQL), todas aprobadas (equipo y Docker)", "tests/evidencias/ejecucion-docker-final-20261028-202102.txt"],
        ["Cobertura (coverage.py, .coveragerc: src/, con ramas)", f"{c['cobertura_sentencias']} % de sentencias · {c['cobertura_ramas']} % de ramas (mínimo del PIA: 80 %)", "tests/evidencias/ejecucion-docker-final-20261028-202102.txt"],
        ["Operaciones de la API", f"{c['operaciones']} (OpenAPI en docs/api/openapi.json)", "docs/api/openapi.json"],
        ["Esquema relacional", f"{c['tablas']} tablas, {c['fks']} claves foráneas, {c['migraciones']} revisiones de Alembic (0001–0004)", "migraciones/versions/"],
        ["Docker Compose", "db + migrate + api + worker + tests; suite completa dentro de Docker aprobada", "docker-compose.yml, Dockerfile"],
        ["Requisitos de negocio", f"{c['bn']} necesidades (BN) y {c['se']} situaciones especiales (SE) del BRD, todos con evidencia de prueba; 6 reglas con observación por decisiones del equipo sin aprobación formal (E-2, E-3/E-4, C-01, C-02, C-06, C-15)", "docs/trazabilidad/auditoria-requisitos-fase-final.md"],
    ], [4.2 * cm, 7.3 * cm, 4.9 * cm]))
    historia += [Spacer(1, 6), P("<b>Estado honesto de la entrega.</b> El sistema funciona y está probado de extremo a extremo en local y en Docker. "
                 "<b>No</b> está desplegado en una plataforma, el pipeline de GitHub Actions <b>no se ha ejecutado</b> en GitHub (el repositorio local no tiene "
                 "remoto) y esta fase no hizo commits. Esos tres puntos son acciones manuales del equipo y se detallan en la sección 10. Además, la revisión de concordancia del 28/10/2026 encontró <b>tres defectos de implementación</b> frente a reglas aprobadas (D-1 a D-3) que se <b>corrigieron</b> el 28/10/2026 (1415 pruebas aprobadas en la última ejecución registrada; decisiones internas sin aprobación externa), y T-21, T-23 y T-24 con el código actualizado resultaron <b>satisfactorias</b> según los resultados informados por el equipo.")]

    # ---- 2 análisis
    historia += [P("2. Análisis del negocio", h1),
                 P(f"<b>BRD.</b> El BRD aprobado (docs/unidad 2/Reporte_BRD_Corregido.docx; versión Markdown en docs/BRD.md) define el contexto, el problema, "
                   f"{c['bn']} necesidades de negocio (BN-001 a BN-010), {c['se']} situaciones especiales (SE-001 a SE-012), el alcance y lo que queda fuera de él "
                   "(por ejemplo, realizar los pagos por parte del Cliente y reprogramar la fecha de un evento contratado)."),
                 P(f"<b>User Stories y Gherkin.</b> {c['us']} User Stories (US-001 a US-033, más del mínimo de 15 que pide el PIA) con {c['ca']} criterios de aceptación "
                   "en Gherkin (CA-001 a CA-114), agrupados por casos de uso. Los actores son Cliente, Coordinador, Proveedor y Administración."),
                 P("<b>BPMN y glosario.</b> BPMN maestro y ocho subprocesos (SP-01 a SP-08) en diagramas/bpmn/; glosario de dominio GL-001 a GL-062 "
                   "(docs/unidad 2/Glosario_Corregido.docx)."),
                 P("<b>Cierre de alcance aprobado.</b> El documento Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md fija las reglas C-01 a C-15 y tres "
                   "decisiones: A (devolución del anticipo cuando la contratación se cierra sin confirmar), B (el 30 % es el mínimo del anticipo) y C (sin reembolso "
                   "al cancelar el Evento). Se conserva intacto; es la fuente de mayor prioridad para las reglas de negocio.")]

    # ---- 3 arquitectura
    historia += [P("3. Arquitectura", h1), diagrama_capas(), Spacer(1, 4),
                 P("<b>DDD.</b> Siete raíces de agregado: Propuesta (con versiones), Contrato (con anexos), Evento (con servicios contratados), "
                   "SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor y EstadoCuenta (con obligaciones, pagos y devoluciones). Value Objects "
                   "inmutables (Importe, DatosEvento, PlazoPago, etc.), 31 Domain Events y reacciones después del commit en transacciones propias (ADR-004).",),
                 P("<b>Patrones y su justificación.</b>")]
    historia.append(tabla([
        ["Patrón", "Dónde", "Por qué"],
        ["Specification", "domain/especificacion.py, especificaciones.py", "Reglas de elegibilidad combinables (CONTRATACION_CONFIRMABLE = firmado Y política comunicada Y anticipo verificado), con motivos de incumplimiento"],
        ["State Machine", "domain/maquina_estados.py", "Estados y transiciones explícitos por agregado (Evento, Contrato, solicitudes, obligaciones, pagos, devoluciones); un par estado-acción inválido se rechaza con el mismo mensaje"],
        ["Repository + Unit of Work", "application/puertos.py; repositorios_memoria.py y persistencia/repositorios_sql.py", "El dominio no conoce la base de datos; una operación = una transacción"],
        ["Outbox + Domain Events", "persistencia/outbox_sql.py", "Entrega al menos una vez con deduplicación por reacción; el cambio y su evento se confirman juntos"],
        ["CQRS ligero", "application/cqrs.py", "Consultas de solo lectura separadas de los comandos"],
        ["Ports & Adapters", "puertos + infrastructure/adaptadores.py", "Colaboradores externos sustituibles (hoy simulados)"],
        ["Optimistic locking", "persistencia/repositorios_sql.py (ADR-006)", "Evita perder actualizaciones simultáneas del mismo agregado"],
    ], [3.4 * cm, 5.2 * cm, 7.8 * cm]))
    historia += [Spacer(1, 6), P("<b>Principios SOLID (demostrables).</b>")]
    historia += viñetas([
        "<b>S</b>: cada agregado concentra las reglas de su consistencia; las rutas de la API solo traducen HTTP y llaman a un servicio.",
        "<b>O</b>: nuevas reglas se añaden como Specification o transición sin modificar a quien las consume.",
        "<b>L</b>: los repositorios en memoria y SQL cumplen el mismo contrato (las mismas pruebas de contrato se ejecutan sobre ambos).",
        "<b>I</b>: puertos pequeños (IVerificadorPagos, IEjecutorDevoluciones, INotificadorParticipantes, IConsultaDisponibilidadProveedor).",
        "<b>D</b>: servicios y reacciones dependen de puertos; la composición (infrastructure/composicion.py) es la única raíz de ensamblado.",
    ])
    historia += [P("<b>ADR.</b> ADR-001 Domain Model como patrón principal · ADR-002 SustitucionProveedor y EstadoCuenta como raíces independientes · "
                   "ADR-003 La cancelación por falta de regularización la registra el Coordinador · ADR-004 Reacciones a Domain Events después del commit con Outbox · "
                   "ADR-005 PostgreSQL 18 como motor de persistencia (decisión técnica del equipo) · ADR-006 Concurrencia optimista e identificadores UUID · ADR-007 Decisiones funcionales E-1 a E-4 (decisiones del equipo; E-2 a E-4 sin aprobación externa) · ADR-008 Llegada de T por el trabajador y pago tardío del saldo (decisiones internas sin aprobación externa)."),
                 P("<b>Diagramas.</b> diagramas/clases (3), diagramas/secuencia (2), mapa de dominio y BPMN en diagramas/. Los diagramas UML de clases son anteriores "
                   "a la capa de persistencia; el diagrama por capas de esta sección la incluye.")]

    # ---- 4 implementación
    historia += [P("4. Implementación", h1),
                 P(f"<b>API REST.</b> {c['operaciones']} operaciones con Swagger UI en /docs y la especificación en docs/api/openapi.json. Un rechazo de negocio "
                   "es HTTP 422; un conflicto de concurrencia o de integridad, 409; una base no disponible, 503. Los importes son Decimal finitos y no negativos (nunca float).",),
                 P("<b>Persistencia.</b> PostgreSQL 18 con SQLAlchemy Core (sin ORM: el dominio no depende de la base), Psycopg 3 y Alembic. Mapeadores que rehidratan sin "
                   "ejecutar constructores ni emitir eventos, repositorios SQL con control optimista, UnitOfWorkSQL, Outbox persistente con reclamo SKIP LOCKED y trabajador "
                   "independiente. Los datos sobreviven al reinicio del contenedor (probado con el contenedor real).",),
                 P("<b>Reglas de la fase final.</b>")]
    historia += viñetas([
        "Anticipo como <b>mínimo</b> (B): un excedente cubre el requisito, no se devuelve ni se aplica al saldo; se distinguen lo recibido y lo aplicado.",
        "Contratación cerrada sin confirmar (A): anticipo pendiente → Sin efecto, liquidado conserva su estado, devolución de lo recibido (una por pago), sin reabrir; pagos posteriores se registran y verifican; plazo de 5 días hábiles desde la más tardía entre cierre y registro.",
        "Cancelación del Evento (C): sin devolución automática; distinta del cierre de la contratación.",
        "Identificadores UUID v4 completos, sin sobrescritura accidental; control de concurrencia optimista (HTTP 409).",
        "Integraciones externas simuladas y documentadas; el comprobante de una devolución lo entrega Administración (CA-098).",
    ])

    # ---- 5 calidad
    historia += [P("5. Calidad y pruebas", h1),
                 P(f"La suite completa ejecuta {c['pruebas']} pruebas con <b>EVENTOSNOVA_REQUIERE_BD=1</b> (sin PostgreSQL fallan, no se omiten) y todas pasan, "
                   f"tanto en el equipo como dentro de Docker. La cobertura se mide con coverage.py sobre todo src/ con ramas (.coveragerc): "
                   f"{c['cobertura_sentencias']} % de sentencias ({c['sentencias'] - c['sin_cubrir']} de {c['sentencias']}) y {c['cobertura_ramas']} % de ramas. "
                   "El único aviso conocido es la advertencia de obsolescencia de httpx en Starlette."),
                 P("<b>Categorías.</b> Unitarias de dominio y State Machines; reglas aprobadas (anticipo A/B/C, plazos, devoluciones); API (memoria y PostgreSQL); repositorios "
                   "(el mismo contrato en memoria y SQL); mapeadores; unidad de trabajo; Outbox (reintentos, caídas, dos trabajadores); concurrencia con hilos reales; "
                   "migraciones (ciclo subida-bajada-subida en una base desechable); persistencia tras reiniciar; trazabilidad generada y comprobada.",)]

    # ---- 6 producción
    historia += [P("6. Producción: Docker Compose, CI/CD y despliegue", h1),
                 P("<b>Docker Compose.</b> Servicios db (PostgreSQL 18, volumen persistente), migrate (alembic upgrade head), api (127.0.0.1:8000, healthcheck /ready), "
                   "worker (Outbox) y tests (perfil tests). La configuración llega por variables de entorno (12-Factor); .env.example no contiene secretos y .env está en .dockerignore.",),
                 P("<b>CI/CD.</b> .github/workflows/ci.yml (pruebas con PostgreSQL efímero, migraciones, cobertura ≥ 80 %, Docker) y publicar-imagen.yml. Validados con actionlint; "
                   "<b>no ejecutados en GitHub</b> (sin remoto)."),
                 P("<b>Despliegue.</b> La imagen respeta $PORT y acepta DATABASE_URL de plataforma (postgres:// o postgresql://). <b>No se desplegó</b>: no hay URL. Pasos manuales exactos en "
                   "docs/architecture/ci-cd-y-despliegue.md.")]

    # ---- 7 trazabilidad
    historia += [P("7. Trazabilidad", h1),
                 P("Cada ruta de la API se asocia a su servicio, a la fila de la matriz aprobada que la nombra o, si no existe, al texto explícito de las User Stories; "
                   "el generador verifica que cada identificador citado exista en las fuentes."),
                 tabla([["Clasificación de las 60 operaciones", "Cantidad"],
                        ["Negocio con fila en la matriz aprobada", "39"],
                        ["Negocio sin fila propia, con respaldo explícito en User Stories, cierre o BPMN SP-04", "18"],
                        ["Técnicas (/, /health, /ready)", "3"],
                        ["Sin respaldo documental", "0"]], [12.4 * cm, 4 * cm]),
                 Spacer(1, 6),
                 P("La auditoría (docs/trazabilidad/auditoria-requisitos-fase-final.md) cubre los 22 requisitos del BRD y 20 reglas del cierre de alcance con fuente, "
                   "implementación, pruebas y estado. Distingue regla aprobada, implementada y con prueba. GL-060 / C-15 está implementado (E-1); el oráculo histórico se conserva y se valida con esperados por regla (método pendiente de aprobación formal); E-2, E-3 y E-4 son decisiones del equipo sin aprobación formal (ver sección 10).")]

    # ---- 8 evidencias
    historia += [P("8. Evidencias", h1)]
    historia += viñetas([
        "tests/evidencias/ejecucion-docker-final-20261028-202102.txt — última ejecución registrada: suite completa dentro de Docker con cobertura (1415 pruebas; registro en UTF-16). La misma suite sin cobertura en el equipo: ejecucion-pruebas-d2b-reloj-host-20261028.txt (1415).",
        "tests/evidencias/ejecucion-pruebas-d1-d3-host-20261028.txt, …-docker-20261028.txt y cobertura-d1-d3-20261028.txt — ejecución anterior (1387 pruebas); la de 1306 es ejecucion-pruebas-e1-e4-host-20261025.txt.",
        "tests/evidencias/diferencias-oraculo-d2-20261028.txt (y …-e1-e4-20261025.txt) — validación del oráculo histórico por reglas, con identificadores.",
        "tests/evidencias/humo-api-e1-e4-20261025.txt, humo-api-e1-plazos-20261025.txt y humo-api-outbox-20261025.txt — pruebas de humo por HTTP sobre PostgreSQL, en una base temporal.",
        "tests/evidencias/migracion-0001-aplicada-desarrollo-20261024.txt y registros de progreso en docs/architecture/ (PROGRESO_FASE_FINAL.md, registro-progreso-persistencia-fase2.md).",
        "docs/architecture/: esquema relacional, integraciones externas, trazabilidad de la API, CI/CD y despliegue.",
        "docs/trazabilidad/: matriz aprobada, complemento y auditoría de requisitos.",
        "docs/pruebas-manuales/ y docs/architecture/CIERRE_AUDITORIA_FINAL.md §I — validación manual en Swagger (T-14 a T-24) en un entorno aislado (puerto 8001): primera ejecución: T-14 a T-18 y T-22 aprobadas según el equipo; T-19 a T-21 satisfactorias con desviación; repetición con el código actualizado (sección Q del cierre): T-21, T-23 y T-24 " + VALIDACION_MANUAL_T21_T23 + ".",
        "Diagramas actualizados el 29/10/2026 con D-1 a D-3 (mapa de dominio, clases, secuencias, BPMN SP-02 y maestro) y sus exportaciones regeneradas (procedimiento en diagramas/LEEME_EXPORTACIONES.txt).",
        "Las evidencias históricas no se sobrescribieron; las nuevas llevan nombres únicos.",
    ])

    # ---- 9 conclusiones previas -> pendientes
    historia += [P("9. Cumplimiento de la consigna del PIA", h1)]
    historia.append(tabla([
        ["Requisito de la consigna", "Estado", "Evidencia"],
        ["Análisis: BRD, ≥ 15 US con Gherkin, BPMN, glosario", "Cumple", "docs/BRD.md, docs/unidad 2/, diagramas/bpmn/"],
        ["Arquitectura: DDD, UML, patrones, SOLID, ADR", "Cumple (UML de clases anterior a la persistencia)", "docs/ADR/, diagramas/, sección 3"],
        ["Implementación: DDD, Specification, State Machine, API REST", "Cumple", "src/, tests/"],
        ["Persistencia/DB y Swagger/OpenAPI", "Cumple en local y Docker", "migraciones/, docs/api/openapi.json, /docs"],
        ["Pruebas unitarias y de integración, cobertura ≥ 80 %", f"Cumple ({c['cobertura_sentencias']} %)", "tests/evidencias/"],
        ["Docker Compose reproducible (DB + App + Tests)", "Cumple", "docker-compose.yml"],
        ["Pipeline CI/CD activo", "Escrito y validado estáticamente; <b>sin ejecución en GitHub</b>", ".github/workflows/"],
        ["Despliegue funcional con Swagger activo", "<b>Pendiente</b> (sin plataforma ni credenciales)", "docs/architecture/ci-cd-y-despliegue.md"],
        ["Repositorio GitHub con historial de commits", "<b>Pendiente</b> (sin remoto; esta fase no hizo commits)", "—"],
        ["Concordancia de las reglas aprobadas con el código", "Defectos D-1 a D-3 <b>corregidos</b> (decisiones internas sin aprobación externa); T-21, T-23 y T-24 satisfactorias según el equipo", "docs/architecture/CIERRE_AUDITORIA_FINAL.md §O a §Q"],
        ["Estructura mínima del repositorio", "Cumple (docs/BRD.md, docs/architecture/, docs/api/, src/, tests/, .github/, docker-compose.yml, .env.example, README.md)", "raíz del proyecto"],
        ["Reporte final PDF y presentación de defensa", "Cumple (este documento y docs/entrega/)", "docs/entrega/"],
    ], [6 * cm, 5.4 * cm, 5 * cm]))

    # ---- 10 pendientes
    historia += [P("10. Pendientes, riesgos y decisiones del responsable", h1)]
    historia += viñetas(PENDIENTES)

    # ---- 11 conclusiones
    historia += [P("11. Conclusiones", h1)]
    historia += viñetas([
        "El análisis aprobado se materializó en un sistema ejecutable cuyas reglas pueden rastrearse del documento al código y a la prueba; la trazabilidad se genera y se comprueba automáticamente.",
        "Separar el dominio de la persistencia permitió añadir PostgreSQL sin tocar las reglas: los mismos contratos se prueban en memoria y en SQL.",
        "La auditoría encontró y corrigió defectos reales: el anticipo exacto frente al mínimo, las devoluciones tras el cierre, la colisión de identificadores, la pérdida de actualizaciones concurrentes y una disponibilidad de proveedores inutilizable por HTTP.",
        "La revisión de concordancia entre el código y las reglas aprobadas encontró tres incumplimientos (D-1 servicio adicional sin contratación confirmada, D-2 pago tardío del saldo, D-3 inicio automático en T). Se corrigieron con pruebas de regresión y quedaron registrados, junto con las decisiones internas que contienen, que no tienen aprobación externa.",
        "Quedan decisiones que no corresponden al equipo técnico (aprobar el método de validación del oráculo histórico para GL-060; aprobar formalmente E-2, E-3 y E-4) y acciones que requieren recursos externos (repositorio remoto, CI en GitHub, plataforma de despliegue). Están documentadas y no se presentan como resueltas.",
    ])

    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / "Reporte_Final_PIA_Eventos_Nova.pdf"

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont("Texto", 8)
        canvas.setFillColor(colors.HexColor("#6b7b8c"))
        canvas.drawString(2 * cm, 1.2 * cm, "Eventos Nova — Reporte final del PIA — Equipo 16")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                      title="Reporte final del PIA — Eventos Nova", author="Equipo 16").build(historia, onFirstPage=pie, onLaterPages=pie)
    return destino


# --------------------------------------------------------------------------- PPTX
def generar_pptx(c: dict) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    AZUL = RGBColor(0x1F, 0x3A, 0x5F)
    GRIS = RGBColor(0x44, 0x4F, 0x5C)
    vacia = prs.slide_layouts[6]

    def diapositiva(titulo, puntos, notas="", tam=20):
        s = prs.slides.add_slide(vacia)
        caja = s.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12.1), Inches(1.0))
        p = caja.text_frame.paragraphs[0]
        p.text = titulo
        p.font.size, p.font.bold, p.font.color.rgb = Pt(32), True, AZUL
        cuerpo = s.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(11.9), Inches(5.4))
        tf = cuerpo.text_frame
        tf.word_wrap = True
        for i, punto in enumerate(puntos):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = "•  " + punto
            p.font.size, p.font.color.rgb = Pt(tam), GRIS
            p.space_after = Pt(9)
        if notas:
            s.notes_slide.notes_text_frame.text = notas
        return s

    portada = prs.slides.add_slide(vacia)
    t = portada.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(1.5)).text_frame
    t.paragraphs[0].text = "Eventos Nova"
    t.paragraphs[0].font.size, t.paragraphs[0].font.bold, t.paragraphs[0].font.color.rgb = Pt(54), True, AZUL
    sub = portada.shapes.add_textbox(Inches(0.8), Inches(3.7), Inches(11.7), Inches(2.5)).text_frame
    sub.word_wrap = True
    lineas = ["Producto Integrador de Aprendizaje — Defensa", "Componentes de Lógica de Negocios · Equipo 16",
              "; ".join(n for n, _ in INTEGRANTES), f"Profesor: {PROFESOR}"]
    for i, l in enumerate(lineas):
        p = sub.paragraphs[0] if i == 0 else sub.add_paragraph()
        p.text = l
        p.font.size, p.font.color.rgb = Pt(22 if i == 0 else 16), GRIS
    portada.notes_slide.notes_text_frame.text = "Presentar al equipo y el objetivo: convertir el análisis de U2/U3 en un sistema funcional, verificable y desplegable."

    diapositiva("El negocio y el problema", [
        "Eventos Nova organiza bodas, graduaciones y eventos empresariales.",
        "Hoy los cambios viajan por WhatsApp, llamadas y correo: información desactualizada, pagos y aprobaciones difíciles de controlar.",
        f"Análisis base: BRD ({c['bn']} BN, {c['se']} SE), {c['us']} User Stories, {c['ca']} criterios Gherkin, BPMN maestro + 8 subprocesos, glosario.",
        "Cierre de alcance aprobado: reglas C-01 a C-15 y decisiones A, B y C.",
    ], "Mostrar docs/BRD.md y el BPMN maestro. Insistir en que el cierre de alcance es la fuente de mayor prioridad.")

    diapositiva("Arquitectura por capas (DDD)", [
        "api → application → domain ← infrastructure (el dominio no depende de la base de datos).",
        "7 agregados: Propuesta, Contrato, Evento, SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor, EstadoCuenta.",
        "Specification y State Machine explícitas; 31 Domain Events con reacciones después del commit (ADR-004).",
        "ADR-001 a ADR-008: dominio, agregados, cancelación, Outbox, PostgreSQL, concurrencia, decisiones E-1 a E-4 y llegada de T.",
    ], "Pregunta probable: ¿por qué SQLAlchemy Core y no ORM? Para no convertir el dominio en entidades de ORM; los mapeadores rehidratan sin ejecutar constructores.")

    diapositiva("Reglas y estados que se demuestran", [
        "Anticipo: el 30 % es el mínimo; un excedente cubre el requisito y no se devuelve ni se aplica al saldo (B). Con varios pagos parciales se suma (E-3, decisión del equipo).",
        "Contratación cerrada sin confirmar: devolución de lo recibido, sin reabrir; pagos posteriores se registran (A).",
        "Cancelación del Evento: sin reembolso (C), distinta del cierre de la contratación.",
        "Cambios, servicios adicionales y sustituciones con aprobación del Cliente y autorización de Administración.",
        "Saldo vencido → protocolo de cobro → regularización o cancelación registrada por el Coordinador.",
    ], "Demo sugerida: POST /eventos → propuesta → aceptación → contrato → firma → pago de anticipo (4000 sobre 3000) → consulta de administración.", 19)

    diapositiva("API REST y persistencia", [
        f"{c['operaciones']} operaciones documentadas con Swagger UI (/docs) y docs/api/openapi.json.",
        f"PostgreSQL 18: {c['tablas']} tablas, {c['fks']} claves foráneas, Alembic 0001–0004.",
        "Repositorios SQL, Unit of Work y Outbox persistente; el mismo contrato se prueba en memoria y en SQL.",
        "Datos conservados tras reiniciar el contenedor; errores 409/422/503 explícitos.",
    ], "Mostrar /docs y reiniciar el contenedor api para probar que los datos persisten.")

    diapositiva("Calidad y pruebas", [
        f"{c['pruebas']} pruebas aprobadas (unitarias + integración con PostgreSQL), también dentro de Docker.",
        f"Cobertura: {c['cobertura_sentencias']} % de sentencias y {c['cobertura_ramas']} % de ramas (mínimo del PIA: 80 %).",
        "Concurrencia con hilos reales, reintentos del Outbox, migraciones subida/bajada/subida, persistencia tras reiniciar.",
        "Trazabilidad generada y comprobada por pruebas: 60 operaciones, 22 requisitos del BRD, 20 reglas del cierre (3 defectos de implementación hallados y corregidos).",
    ], "Aclarar que EVENTOSNOVA_REQUIERE_BD=1 hace fallar (no omitir) las pruebas de integración sin base de datos.")

    diapositiva("Docker Compose, CI/CD y despliegue", [
        "docker compose up: db + migrate + api + worker; docker compose run --rm tests ejecuta la suite completa.",
        "Variables de entorno (12-Factor); .env.example sin secretos; la imagen respeta $PORT.",
        "CI en .github/workflows: validada estáticamente (actionlint) y sus pasos ejecutados en local; NO ejecutada en GitHub todavía.",
        "Despliegue: pendiente (sin plataforma ni credenciales). Guía exacta en docs/architecture/ci-cd-y-despliegue.md.",
    ], "Ser transparentes: no hay URL pública ni ejecución de CI en GitHub. Indicar los pasos manuales del equipo.")

    diapositiva("Lo que NO está cerrado (transparencia)", [
        "E-1 (GL-060 / C-15): aplicado a los seis plazos en días hábiles; el oráculo histórico no se editó y se valida con esperados derivados de las reglas (método pendiente de aprobación formal).",
        "Sin aprobación formal (decisiones del equipo): E-2 evento de la solicitud = evento del contrato; E-3 el anticipo mínimo se suma con pagos parciales; E-4 un pago menor al 30 % tras liquidar el anticipo es adicional.",
        "Defectos D-1 (servicio adicional sin contratación confirmada), D-2 (pago tardío del saldo) y D-3 (inicio automático en T) corregidos; sus decisiones internas no tienen aprobación externa. T-21, T-23 y T-24 satisfactorias según el equipo (capturas sin archivar).",
        "Repositorio remoto, CI en GitHub y despliegue: acciones manuales del equipo.",
    ], "Transparencia sobre lo implementado frente a lo aprobado. E-1 aplica una regla ya aprobada (GL-060), pero el cierre de alcance (sección 6) prohíbe editar a mano el oráculo histórico y no define cómo recalcularlo para E-1: se conserva intacto y cada clave se compara con un esperado derivado de las reglas (1203 claves: 1094 solo E-1, 67 con E-3/E-4, 2 con E-3/E-4 y H-10, 40 con H-10; 0 sin explicar). "
       "E-3: antes un pago menor al 30 % era «importe incorrecto»; ahora se suma con los demás pagos parciales del contrato. E-4: tras liquidar el anticipo, un pago menor se verifica como adicional (no se devuelve ni se aplica al saldo). E-2, E-3 y E-4 las eligió el equipo; ninguna fuente original las exige y no hay aprobación formal registrada.", 17)

    diapositiva("Conclusiones", [
        "El análisis aprobado se rastrea hasta el código y la prueba, y la trazabilidad se comprueba automáticamente.",
        "Separar dominio y persistencia permitió incorporar PostgreSQL sin tocar las reglas.",
        "La auditoría corrigió defectos reales: anticipo exacto vs. mínimo, devoluciones tras el cierre, colisión de ids, actualizaciones perdidas.",
        "Siguiente paso del equipo: publicar el repositorio, ejecutar la CI y desplegar.",
    ], "Cerrar con el estado real: sistema funcional y probado, con la suite completa en verde ; tres defectos de implementación hallados frente a reglas aprobadas (D-1 a D-3) ya corregidos, con decisiones internas sin aprobación externa; el oráculo histórico de GL-060 se conserva intacto y se valida con esperados por regla (método pendiente de aprobación formal). "
        "Decisiones del equipo sin aprobación formal: E-2 (evento = evento del contrato), E-3 (suma de pagos parciales del anticipo) y E-4 (pago menor al 30 % tras liquidar es adicional); difieren de lo originalmente aprobado, donde un pago menor al 30 % era «importe incorrecto». "
        "Faltan además acciones externas: repositorio, CI en GitHub y despliegue.")

    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / "Presentacion_Defensa_Eventos_Nova.pptx"
    prs.save(str(destino))
    return destino


def main() -> int:
    c = cifras()
    print("Cifras:", c)
    print("Escrito", generar_pdf(c).relative_to(RAIZ))
    print("Escrito", generar_pptx(c).relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
