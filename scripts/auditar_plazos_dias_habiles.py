"""Auditoría de solo lectura de los plazos en días hábiles frente a GL-060 / C-15 del cierre de alcance aprobado.

    python scripts/auditar_plazos_dias_habiles.py

GL-060: «Para los plazos expresados en días hábiles (anticipo, saldo del contrato original y devoluciones) los días festivos se cuentan
como hábiles… El límite de un plazo en días hábiles es exclusivo: vence a las 00:00 del día siguiente al último día del plazo, mientras
que los límites en T y en las ventanas de horas son inclusivos.»

Calcula, con el código ACTUAL, el vencimiento de cada plazo para fechas de ejemplo y lo compara con el que fija GL-060. No modifica
nada ni escribe en ninguna base de datos. Sale con 0 siempre (es un informe); la columna «Conforme» indica si coincide.
Desde la decisión E-1 los seis plazos lo cumplen. El seguimiento del anticipo y el límite de la sustitución no se guardan como un
dato: se obtienen sondeando el servicio y el agregado reales (primer instante en que el código acepta la operación)."""
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from domain.estado_cuenta import Devolucion, EstadoCuenta                     # noqa: E402
from domain.valores import (ConceptoPago, Importe, PlazoPago, TipoDevolucion, restar_dias_habiles,      # noqa: E402
                            sumar_dias_habiles)


def dia(f: datetime) -> datetime:
    return f.replace(hour=0, minute=0, second=0, microsecond=0)


def limite_esperado_adelante(base: datetime, dias: int) -> datetime:
    """GL-060: 00:00 del día siguiente al último día hábil del plazo; el día de partida no cuenta."""
    return sumar_dias_habiles(dia(base), dias) + timedelta(days=1)


def limite_esperado_antes_del_evento(evento: datetime, dias: int) -> datetime:
    return restar_dias_habiles(dia(evento), dias) + timedelta(days=1)


def _primer_instante(candidatos, acepta):
    """Primer instante, entre los candidatos ordenados, en que `acepta(instante)` es verdadero (None si ninguno)."""
    return next((c for c in sorted(set(candidatos)) if acepta(c)), None)


def sondear_seguimiento(firma: datetime, esperado: datetime):
    """Primer instante en que el servicio real acepta el seguimiento del anticipo (plazo de 3 días hábiles vencido)."""
    from test_reglas_corregidas import Escenario, T0
    assert firma == T0
    segundo = timedelta(seconds=1)

    def acepta(momento):
        e = Escenario()
        return e.s.contratacion.dar_seguimiento_anticipo_pendiente(e.contrato_id, momento, "Contacto", False).exito
    return _primer_instante([esperado - segundo, esperado, sumar_dias_habiles(firma, 3), sumar_dias_habiles(firma, 3) + segundo], acepta)


def sondear_sustitucion(evento: datetime, esperado: datetime):
    """Primer instante en que SustitucionProveedor.registrar_autorizacion considera la autorización posterior al límite ordinario."""
    from apoyo_maquina_estados_sustitucion import CON_IMPACTO, ESP, alternativa, aprobada, sustitucion
    from domain.valores import Decision
    segundo = timedelta(seconds=1)

    def posterior(momento):
        s = sustitucion(ESP.PENDIENTE_AUTORIZACION, alternativas=[alternativa(CON_IMPACTO, decision=aprobada())], costo=Importe(Decimal(800)))
        s.registrar_autorizacion(Decision("Administración", True, momento), evento)
        return s.aprobada_despues_del_limite
    antiguo = restar_dias_habiles(evento, 3)
    return _primer_instante([esperado - segundo, esperado, antiguo, antiguo + segundo], posterior)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    firma = datetime(2026, 10, 1, 10, 0)            # jueves
    evento = datetime(2026, 11, 20, 18, 0)          # viernes
    cierre = datetime(2026, 11, 20, 15, 30)         # viernes
    ec = EstadoCuenta("EC", "CT", "EV")
    anticipo = ec.registrar_obligacion_anticipo("OB-A", Importe(Decimal(10000)), firma).plazo
    saldo = ec.registrar_obligacion_saldo_original("OB-S", Importe(Decimal(10000)), evento).plazo
    se012 = Devolucion("DV", "SC", ConceptoPago.CAMBIO, Importe(Decimal(1)), "x", cierre).fecha_limite
    anticipo_dev = Devolucion("DV2", None, ConceptoPago.ANTICIPO, Importe(Decimal(1)), "x", cierre,
                              tipo=TipoDevolucion.ANTICIPO_CONTRATACION_CERRADA, pago_id="PG", fecha_referencia=cierre).fecha_limite
    filas = [
        ("Anticipo (3 días hábiles tras la firma)", "días hábiles", f"firma {firma:%a %d/%m %H:%M}", anticipo.vence,
         limite_esperado_adelante(firma, 3), "EstadoCuenta.registrar_obligacion_anticipo → PlazoPago.dias_habiles → limite_exclusivo_dias_habiles"),
        ("Seguimiento del anticipo (¿venció el plazo de 3 días hábiles?)", "días hábiles", f"firma {firma:%a %d/%m %H:%M}",
         sondear_seguimiento(firma, limite_esperado_adelante(firma, 3)), limite_esperado_adelante(firma, 3),
         "FormalizarContratacionService.dar_seguimiento_anticipo_pendiente (sondeado)"),
        ("Saldo del contrato original (3 días hábiles antes del evento)", "días hábiles", f"evento {evento:%a %d/%m %H:%M}", saldo.vence,
         limite_esperado_antes_del_evento(evento, 3), "EstadoCuenta.registrar_obligacion_saldo_original → PlazoPago.dias_habiles_antes_de"),
        ("Límite ordinario de la sustitución con costo adicional", "días hábiles", f"evento {evento:%a %d/%m %H:%M}",
         sondear_sustitucion(evento, limite_esperado_antes_del_evento(evento, 3)), limite_esperado_antes_del_evento(evento, 3),
         "SustitucionProveedor.registrar_autorizacion (sondeado)"),
        ("Devolución SE-012 (5 días hábiles)", "días hábiles", f"cierre {cierre:%a %d/%m %H:%M}", se012,
         limite_esperado_adelante(cierre, 5), "Devolucion.fecha_limite (tipo SE-012) → limite_exclusivo_dias_habiles"),
        ("Devolución del anticipo, decisión A (5 días hábiles)", "días hábiles", f"cierre {cierre:%a %d/%m %H:%M}", anticipo_dev,
         limite_esperado_adelante(cierre, 5), "Devolucion.fecha_limite (tipo anticipo) → limite_exclusivo_dias_habiles"),
    ]
    print("| Plazo | Unidad | Punto de partida | Vencimiento con el código actual | Vencimiento según GL-060 | Conforme | Implementación |")
    print("|---|---|---|---|---|---|---|")
    for nombre, unidad, partida, actual, esperado, donde in filas:
        print(f"| {nombre} | {unidad} | {partida} | {actual:%a %d/%m/%Y %H:%M:%S} | {esperado:%a %d/%m/%Y %H:%M:%S} | "
              f"{'SÍ' if actual == esperado else 'NO'} | {donde} |")
    print()
    print("Plazos en horas o días naturales (límite inclusivo según GL-060; no afectados por E-1):")
    ventana = PlazoPago.horas_naturales(firma, 24)
    print(f"- Ventanas de 24 horas (contacto del anticipo, moratorios, solicitudes de pago): vence a las {ventana.vence:%d/%m %H:%M} y "
          f"«vencido» es ahora > vence → en el instante exacto del límite todavía está en plazo (inclusivo).")
    print("- Cinco días naturales (servicio adicional) y siete (cambio tardío): se cuentan por fecha de calendario (AnticipacionSolicitud.dias_naturales).")
    print("- T (inicio del evento): Evento.iniciado_en usa ahora >= fecha y hora programadas (límite inclusivo en T).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
