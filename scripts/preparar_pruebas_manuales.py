"""Imprime, SOLO LECTURA, los pasos de las pruebas manuales T-21, T-23 y T-24 con las fechas ya calculadas para la hora actual de negocio
(America/Mexico_City, TP-06: la misma que usan la API y el trabajador) y los cuerpos JSON listos para copiar en Swagger. No llama a ninguna API, no escribe en ninguna base y no modifica archivos.

    python scripts/preparar_pruebas_manuales.py t21
    python scripts/preparar_pruebas_manuales.py t23
    python scripts/preparar_pruebas_manuales.py t24
    python scripts/preparar_pruebas_manuales.py t23 --ahora 2026-11-02T10:00     # simular otra hora de negocio (Ciudad de México) para planificar

Los identificadores (<evento_id>, <propuesta_id>, <contrato_id>, <estado_cuenta_id>, <obligacion_id>, <pago_id>) se copian de las
respuestas anteriores (guía: docs/pruebas-manuales/GUIA_PRUEBAS_MANUALES_T14_T24.md, sección 12). El script comprueba las condiciones
de calendario de cada prueba y avisa si hoy no se puede ejecutar."""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from application.reloj import reloj_negocio                                             # noqa: E402
from domain.valores import limite_exclusivo_dias_habiles_antes                         # noqa: E402

FMT = "%Y-%m-%dT%H:%M:%S"
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def f(d: datetime) -> str:
    return d.strftime(FMT)


def json_(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=2)


def pasos_contratacion(cliente, fecha_ev, firma, pago, registro, verificacion, comprobante):
    return [
        ("PC-1", "POST /eventos", {"cliente_id": cliente, "datos": {"tipo": "Boda", "fecha_hora": f(fecha_ev), "lugar": "Salón Nova", "invitados_aproximados": 120},
                                   "servicios": ["Banquete", "Fotografía"]}, "HTTP 201 «Evento registrado En gestión.»  → copiar evento_id"),
        ("PC-2", "POST /eventos/<evento_id>/propuestas", {"servicios": ["Banquete", "Fotografía"], "proveedores_considerados": ["PV-1"],
                                                         "costo_total": "10000.00", "condiciones": "Condiciones generales"},
         "HTTP 201 «Propuesta creada.»  → copiar propuesta_id; version_id = <propuesta_id>-v1"),
        ("PC-3", "POST /propuestas/<propuesta_id>/aceptacion", {"version_id": "<propuesta_id>-v1"}, "HTTP 200 «Propuesta aceptada.»"),
        ("PC-4", "POST /propuestas/<propuesta_id>/contrato", {"politica_incluida": True}, "HTTP 201 «Contrato preparado.»  → copiar datos.contrato_id"),
        ("PC-5", "POST /contratos/<contrato_id>/comunicacion-politica-no-reembolso", {"fecha": f(firma)}, "HTTP 200"),
        ("PC-6", "POST /contratos/<contrato_id>/firma", {"fecha": f(firma)}, "HTTP 200 «Contrato firmado.»"),
        ("PC-7", "GET /pagos-pendientes?evento_id=<evento_id>", None,
         "fila Anticipo, importe 3000.00, estado Pendiente  → copiar estadoCuentaId y obligacionId (la fila «Anticipo»)"),
        ("PC-8", "POST /estados-cuenta/<estado_cuenta_id>/pagos", {"obligacion_id": "<obligacion_id>", "importe": "3000.00", "fecha": f(pago),
                                                                  "comprobante": comprobante, "registrado_en": f(registro), "verificar_ahora": False},
         "HTTP 201 «Pago Registrado.»  → copiar datos.pago_id"),
        ("PC-9", "POST /estados-cuenta/<estado_cuenta_id>/pagos/<pago_id>/verificacion", {"verificado_en": f(verificacion)}, "HTTP 200 «Pago Verificado.»"),
        ("PC-10", "GET /eventos/<evento_id>/administracion", None,
         "estadoEvento «En organización», contratos[0].estado «Contratación confirmada», anticipo.estado «Liquidada» (si no: POST /contratos/<contrato_id>/confirmacion)"),
    ]


def imprimir(titulo, avisos, pasos):
    print(f"\n{'=' * 100}\n{titulo}\n{'=' * 100}")
    for a in avisos:
        print(f"  ! {a}")
    for clave, endpoint, cuerpo, esperado in pasos:
        print(f"\n[{clave}] {endpoint}")
        if cuerpo is not None:
            print(json_(cuerpo))
        print(f"  Esperado: {esperado}")


def redondear(d: datetime, minutos=1) -> datetime:
    return d.replace(second=0, microsecond=0)


def preparar(prueba: str, ahora: datetime):
    base = redondear(ahora)
    cabecera = [f"AHORA (hora de negocio, America/Mexico_City) = {f(ahora)} ({DIAS[ahora.weekday()]}). Es el reloj de la API y del trabajador (TP-06); con las imágenes reconstruidas puede comprobarlo con: docker exec eventosnova-api-manual python -c \"from application.reloj import reloj_negocio; print(reloj_negocio())\"",
                "Swagger de las pruebas: http://127.0.0.1:8001/docs (nunca el 8000)."]
    if prueba == "t21":
        firma, pago, registro, verif = base, base + timedelta(minutes=1), base + timedelta(minutes=2), base + timedelta(minutes=3)
        fecha_ev = (base + timedelta(days=30)).replace(hour=18, minute=0)
        pasos = pasos_contratacion("CL-PRUEBA-T21", fecha_ev, firma, pago, registro, verif, "C-T21-0001")
        pasos += [("T-21", "POST /eventos/<evento_id>/cancelacion", {"motivo": "El Cliente canceló"}, "HTTP 200 «Evento cancelado.»"),
                  ("T-21 GET", "GET /eventos/<evento_id>/administracion", None, "estadoEvento «Cancelado»"),
                  ("T-21 GET", "GET /solicitudes?evento_id=<evento_id>", None, '{"solicitudes": []}  (copie el evento_id completo)')]
        imprimir("T-21 · cancelación de un evento INDEPENDIENTE (no use el evento principal)", cabecera, pasos)
    elif prueba == "t23":
        evento_dia = (base + timedelta(days=4)).replace(hour=18, minute=0)
        limite = limite_exclusivo_dias_habiles_antes(evento_dia, 3)
        avisos = list(cabecera)
        factible = ahora < limite - timedelta(hours=1) and (evento_dia.date() - ahora.date()).days <= 4
        avisos.append(f"Evento a AHORA + 4 días: {f(evento_dia)}; límite del saldo (3 días hábiles antes, exclusivo) = {f(limite)}.")
        if factible:
            avisos.append("OK: el límite del saldo es posterior a AHORA y faltan menos de 5 días naturales. T-23 se puede preparar hoy.")
        else:
            avisos.append("NO EJECUTE T-23 HOY: con este calendario el límite del saldo ya habría pasado (solo es coherente de domingo a martes en hora de negocio (o el miércoles temprano)). "
                          "Espere a un domingo, lunes o martes.")
        firma, pago, registro, verif = base, base + timedelta(minutes=1), base + timedelta(minutes=2), base + timedelta(minutes=3)
        pasos = pasos_contratacion("CL-PRUEBA-T23", evento_dia, firma, pago, registro, verif, "C-T23-0001")
        pasos += [("T-23 antes", "GET /pagos-pendientes?evento_id=<evento_id>", None,
                   f"fila SaldoContratoOriginal, importe 7000.00, estado Pendiente y fechaLimite = {f(limite)} POSTERIOR a AHORA (si no, T-23 queda Bloqueado)"),
                  ("T-23 antes", "GET /eventos/<evento_id>/administracion", None, "estadoEvento «En organización», contrato «Contratación confirmada», fechaHora futura"),
                  ("T-23", "POST /solicitudes-servicio-adicional", {"evento_id": "<evento_id>", "contrato_id": "<contrato_id>", "servicio": "Fotografía"},
                   "HTTP 201, estado «No procedente», motivo «Condición temporal: quedan menos de cinco días naturales (CA-077, CA-083).»"),
                  ("T-23 GET", "GET /solicitudes?evento_id=<evento_id>", None, "tipoSolicitud servicio adicional, estadoActual «No procedente», pendiente false"),
                  ("T-23 GET", "GET /pagos-pendientes?evento_id=<evento_id>", None, "el saldo sigue Pendiente (no ejecute el endpoint de vencimiento)")]
        imprimir("T-23 · servicio adicional con menos de cinco días naturales (contratación CONFIRMADA)", avisos, pasos)
    elif prueba == "t24":
        t = base + timedelta(minutes=40)
        firma, pago, registro, verif = base, base + timedelta(minutes=1), base + timedelta(minutes=2), base + timedelta(minutes=3)
        avisos = cabecera + [f"El evento inicia a las {f(t)} hora de negocio (AHORA + 40 min). TODAS las fechas del paso PC deben quedar ANTES de esa hora: "
                             "después de T ya no se puede confirmar la contratación (CA-110, D-3b). Haga PC-1 a PC-10 sin demorarse.",
                             "El trabajador (eventosnova-worker-manual) inicia el evento solo al llegar T (ciclo de 2 s); si no lo hace, use POST /eventos/<evento_id>/inicio."]
        pasos = pasos_contratacion("CL-PRUEBA-T24", t, firma, pago, registro, verif, "C-T24-0001")
        pasos += [("T-24 espera", "GET /eventos/<evento_id>/administracion", None,
                   f"ANTES de {f(t)}: «En organización». Desde esa hora (unos segundos después): «En ejecución»"),
                  ("T-24", "POST /solicitudes-cambio", {"evento_id": "<evento_id>", "contrato_id": "<contrato_id>", "descripcion": "Cambiar la hora",
                                                        "tarifa_vigente": "500.00"},
                   "HTTP 422, tipo rechazo_de_negocio, detalle «El cambio solo procede después de contratar y antes del inicio (CA-039).» "
                   "(tarifa_vigente 500.00 es solo un valor de ejemplo, no una tarifa oficial)"),
                  ("T-24 GET", "GET /solicitudes?evento_id=<evento_id>", None, '{"solicitudes": []}  (el rechazo no deja solicitud)')]
        imprimir("T-24 · solicitud de cambio después de iniciado el evento", avisos, pasos)
    else:
        raise SystemExit("Use t21, t23 o t24.")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("prueba", choices=["t21", "t23", "t24"])
    p.add_argument("--ahora", help="hora de negocio simulada, AAAA-MM-DDTHH:MM (por omisión, la hora actual de America/Mexico_City)")
    a = p.parse_args()
    ahora = datetime.strptime(a.ahora, "%Y-%m-%dT%H:%M") if a.ahora else reloj_negocio()
    preparar(a.prueba, ahora)
    return 0


if __name__ == "__main__":
    sys.exit(main())
