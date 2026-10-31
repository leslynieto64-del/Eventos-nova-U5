"""Inventario y limpieza SELECTIVA de los datos de prueba de la base de pruebas manuales `eventosnova_manual_test`.

    python scripts/limpiar_datos_manuales.py                                   # inventario (solo lectura)
    python scripts/limpiar_datos_manuales.py --ejecutar --respaldo backups/<archivo>.dump --confirmo-base eventosnova_manual_test

Seguridad:
- Solo actúa sobre la base `eventosnova_manual_test` de un servidor local con la migración 0005; con cualquier otra base se niega.
- Para borrar exige la copia de seguridad (archivo existente, no vacío, con su .sha256 coincidente) y la confirmación explícita de la base.
- Borra solo lo identificado: los eventos de prueba y TODO lo que depende de ellos, los proveedores de prueba y las filas del Outbox de esos
  agregados. No usa TRUNCATE ni borra tablas completas; todo ocurre en UNA transacción que se revierte si alguna comprobación falla.
- Lo que no se puede identificar con seguridad se lista aparte y se conserva.
No imprime credenciales."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
import sqlalchemy as sa                                                      # noqa: E402
from infrastructure.persistencia import configuracion as C                   # noqa: E402

BASE_AUTORIZADA = "eventosnova_manual_test"
REVISION = "0005"
# Marcadores de los datos de prueba (tipo, lugar o cliente del evento): «prueba», T14/T21/T23/T24, clientes CL-UI, CL-PROV-UI, CL-PRUEBA-*.
MARCADOR_EVENTO = re.compile(r"(?i)prueba|\bT-?\d{2}\b|^CL-UI$|^CL-PROV-UI$|^CL-PRUEBA-")
# Cuerpo de ejemplo de Swagger (esquemas.py): solo puede venir de ejecutar el ejemplo tal cual.
EJEMPLO_SWAGGER = ("CL-1", "Boda", "2026-11-20T18:00:00", "Salón", 100, ["Banquete"])
MARCADOR_PROVEEDOR = re.compile(r"(?i)prueba|^Banquetes UI |^Foto UI ")
# Tablas con evento_id (borrado por dependencia) en orden de borrado seguro (hijas primero).
POR_EVENTO = ["solicitud_cambio", "solicitud_servicio_adicional", "sustitucion_proveedor", "estado_cuenta", "contrato", "propuesta", "evento"]
HIJAS_CASCADA = {  # tabla → hijas que PostgreSQL borra en cascada (solo para el recuento informativo)
    "estado_cuenta": ["obligacion_pago", "pago", "devolucion", "estado_cuenta_cierre_sin_realizar", "estado_cuenta_seguimiento_cobro"],
    "contrato": ["contrato_anexo", "contrato_seguimiento_anticipo"], "propuesta": ["version_propuesta"],
    "evento": ["evento_servicio_contratado", "evento_solicitud_cancelacion", "evento_operacion_aplicada"],
    "solicitud_cambio": ["solicitud_cambio_condicion"], "sustitucion_proveedor": ["sustitucion_alternativa"]}
ID_AGREGADO = {"solicitud_cambio": "solicitud_id", "solicitud_servicio_adicional": "solicitud_id", "sustitucion_proveedor": "sustitucion_id",
               "estado_cuenta": "estado_cuenta_id", "contrato": "contrato_id", "propuesta": "propuesta_id", "evento": "evento_id"}


def conectar():
    url = C.url_con_base(C.normalizar_url(C.url_desarrollo()), BASE_AUTORIZADA)
    d = C.descripcion_segura(url)
    if d["base"] != BASE_AUTORIZADA or d["host"] not in C.HOSTS_LOCALES:
        raise SystemExit("Destino no autorizado.")
    return sa.create_engine(url)


def verificar_destino(con) -> dict:
    base, revision = con.execute(sa.text("select current_database(), (select version_num from alembic_version)")).one()
    if base != BASE_AUTORIZADA:
        raise SystemExit(f"La conexión apunta a «{base}», no a {BASE_AUTORIZADA}: no se hace nada.")
    if revision != REVISION:
        raise SystemExit(f"La base está en la revisión {revision}, se esperaba {REVISION}: no se hace nada.")
    return {"base": base, "revision": revision}


def recuento(con) -> dict:
    tablas = [r[0] for r in con.execute(sa.text("select table_name from information_schema.tables where table_schema='public' and table_name<>'alembic_version' order by 1"))]
    return {t: con.execute(sa.text(f'select count(*) from "{t}"')).scalar() for t in tablas}


def clasificar_eventos(con):
    filas = con.execute(sa.text("select evento_id, cliente_id, tipo, lugar, fecha_hora, invitados_aproximados, servicios_solicitados, estado from evento order by evento_id")).all()
    prueba, dudosos = [], []
    for e in filas:
        ejemplo = (e.cliente_id, e.tipo, e.fecha_hora.isoformat(), e.lugar, e.invitados_aproximados, list(e.servicios_solicitados)) == EJEMPLO_SWAGGER
        marcado = any(MARCADOR_EVENTO.search(x or "") for x in (e.tipo, e.lugar, e.cliente_id))
        (prueba if (marcado or ejemplo) else dudosos).append((e, "ejemplo de Swagger" if ejemplo and not marcado else "marcador de prueba"))
    return prueba, dudosos


def ids_dependientes(con, eventos: list) -> dict:
    """Identificadores (por tabla de agregado) que dependen de los eventos de prueba."""
    ids = {}
    for t in POR_EVENTO:
        col = ID_AGREGADO[t]
        ids[t] = [r[0] for r in con.execute(sa.text(f'select "{col}" from "{t}" where evento_id = any(:e)'), {"e": eventos})]
    return ids


def contar_por_tabla(con, ids: dict) -> dict:
    c = {t: len(v) for t, v in ids.items()}
    for padre, hijas in HIJAS_CASCADA.items():
        col = ID_AGREGADO[padre]
        for h in hijas:
            cols = {r[0] for r in con.execute(sa.text("select column_name from information_schema.columns where table_name=:t"), {"t": h})}
            fk = next((x for x in (col, "evento_id", "propuesta_id", "contrato_id", "estado_cuenta_id", "solicitud_id", "sustitucion_id") if x in cols), None)
            c[h] = c.get(h, 0) + (con.execute(sa.text(f'select count(*) from "{h}" where "{fk}" = any(:i)'), {"i": ids[padre]}).scalar() if ids[padre] else 0)
    todos = [i for v in ids.values() for i in v]
    c["outbox_evento"] = con.execute(sa.text("select count(*) from outbox_evento where agregado_id = any(:i)"), {"i": todos}).scalar()
    c["outbox_reaccion"] = con.execute(sa.text("select count(*) from outbox_reaccion where evento_id in (select evento_id from outbox_evento where agregado_id = any(:i))"), {"i": todos}).scalar()
    return {k: v for k, v in c.items() if v}


def proveedores_de_prueba(con, eventos_conservados: list):
    filas = con.execute(sa.text("select proveedor_id, nombre, servicios, contacto from proveedor order by nombre")).all()
    prueba, dudosos = [], []
    for p in filas:
        (prueba if MARCADOR_PROVEEDOR.search(p.nombre) else dudosos).append(p)
    # Un proveedor de prueba asignado a un servicio de un evento que se CONSERVA no se retira.
    en_uso = {r[0] for r in con.execute(sa.text("select distinct proveedor_id from evento_servicio_contratado where evento_id = any(:e) and proveedor_id is not null"), {"e": eventos_conservados})}
    return [p for p in prueba if p.proveedor_id not in en_uso], dudosos, [p for p in prueba if p.proveedor_id in en_uso]


def inventario(con):
    prueba, dudosos = clasificar_eventos(con)
    ev_ids = [e.evento_id for e, _ in prueba]
    conservados = [e.evento_id for e, _ in dudosos]
    ids = ids_dependientes(con, ev_ids)
    provs, provs_dudosos, provs_en_uso = proveedores_de_prueba(con, conservados)
    return {"prueba": prueba, "dudosos": dudosos, "ev_ids": ev_ids, "ids": ids, "conteo": contar_por_tabla(con, ids),
            "proveedores": provs, "proveedores_dudosos": provs_dudosos, "proveedores_en_uso": provs_en_uso}


def mostrar(inv, destino, antes):
    print(f"Destino verificado: base={destino['base']} revisión={destino['revision']}")
    print(f"Eventos de prueba a retirar: {len(inv['prueba'])}")
    for e, motivo in inv["prueba"]:
        print(f"  {e.evento_id}  {e.estado:<16} {e.tipo[:34]:<34} {e.cliente_id:<14} [{motivo}]")
    print(f"Eventos que se CONSERVAN por no poder identificarse con seguridad: {len(inv['dudosos'])}")
    for e, _ in inv["dudosos"]:
        print(f"  {e.evento_id}  {e.estado}  {e.tipo}  {e.lugar}  {e.cliente_id}")
    print("Filas a retirar por tabla:")
    for t, n in inv["conteo"].items():
        print(f"  {t:<36} {n:>4}  (de {antes.get(t, 0)})")
    print(f"Proveedores de prueba a retirar: {len(inv['proveedores'])}")
    for p in inv["proveedores"]:
        print(f"  {p.proveedor_id}  {p.nombre}")
    print(f"Proveedores que se CONSERVAN (no identificables como prueba): {len(inv['proveedores_dudosos'])}")
    for p in inv["proveedores_dudosos"]:
        print(f"  {p.proveedor_id}  {p.nombre}")
    print(f"Proveedores de prueba que se CONSERVAN por estar asignados a un evento conservado: {len(inv['proveedores_en_uso'])}")


def validar_respaldo(ruta: str):
    p = Path(ruta)
    if not p.is_file() or p.stat().st_size == 0:
        raise SystemExit("La copia de seguridad no existe o está vacía: no se borra nada.")
    huella = Path(str(p) + ".sha256")
    if not huella.is_file() or huella.read_text().split()[0] != hashlib.sha256(p.read_bytes()).hexdigest():
        raise SystemExit("La huella de la copia de seguridad no coincide: no se borra nada.")


def ejecutar(con, inv):
    ev = inv["ev_ids"]
    todos = [i for v in inv["ids"].values() for i in v]
    pendientes = con.execute(sa.text("select count(*) from outbox_evento where agregado_id = any(:i) and estado='PENDIENTE'"), {"i": todos}).scalar()
    if pendientes:
        raise SystemExit(f"Hay {pendientes} eventos del Outbox PENDIENTES de esos agregados: se cancela para no perder reacciones.")
    for t in POR_EVENTO:                                        # hijas primero; las tablas dependientes caen en cascada
        r = con.execute(sa.text(f'delete from "{t}" where evento_id = any(:e)'), {"e": ev})
        print(f"  borradas {r.rowcount:>3} de {t}")
    r = con.execute(sa.text("delete from outbox_evento where agregado_id = any(:i)"), {"i": todos})
    print(f"  borradas {r.rowcount:>3} de outbox_evento (y sus outbox_reaccion en cascada)")
    r = con.execute(sa.text("delete from proveedor where proveedor_id = any(:p)"), {"p": [p.proveedor_id for p in inv["proveedores"]]})
    print(f"  borradas {r.rowcount:>3} de proveedor")


def comprobar_integridad(con, inv):
    """Si algo falla se lanza SystemExit y la transacción se revierte."""
    for t in POR_EVENTO:
        n = con.execute(sa.text(f'select count(*) from "{t}" where evento_id = any(:e)'), {"e": inv["ev_ids"]}).scalar()
        if n:
            raise SystemExit(f"Quedan {n} filas de {t} de los eventos retirados: se revierte.")
    huerfanos = {
        "servicios": "select count(*) from evento_servicio_contratado s left join evento e using(evento_id) where e.evento_id is null",
        "contratos": "select count(*) from contrato c left join evento e using(evento_id) where e.evento_id is null",
        "propuestas": "select count(*) from propuesta p left join evento e using(evento_id) where e.evento_id is null",
        "estados de cuenta": "select count(*) from estado_cuenta x left join contrato c on c.contrato_id=x.contrato_id where c.contrato_id is null",
        "pagos": "select count(*) from pago p left join obligacion_pago o on (o.estado_cuenta_id,o.obligacion_id)=(p.estado_cuenta_id,p.obligacion_id) where o.obligacion_id is null",
        "solicitudes": "select count(*) from (select evento_id from solicitud_cambio union all select evento_id from solicitud_servicio_adicional union all select evento_id from sustitucion_proveedor) s left join evento e using(evento_id) where e.evento_id is null",
        "reacciones del Outbox": "select count(*) from outbox_reaccion r left join outbox_evento o using(evento_id) where o.evento_id is null",
    }
    for nombre, q in huerfanos.items():
        n = con.execute(sa.text(q)).scalar()
        if n:
            raise SystemExit(f"Integridad: {n} filas huérfanas en {nombre}: se revierte.")
    print("  integridad referencial: sin filas huérfanas")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ejecutar", action="store_true")
    ap.add_argument("--respaldo")
    ap.add_argument("--confirmo-base")
    ap.add_argument("--json", help="guarda el inventario y los recuentos en este archivo")
    a = ap.parse_args()
    motor = conectar()
    with motor.connect() as con:
        destino = verificar_destino(con)
        antes = recuento(con)
        inv = inventario(con)
        mostrar(inv, destino, antes)
        if a.json:
            Path(a.json).write_text(json.dumps({"destino": destino, "antes": antes, "a_retirar": inv["conteo"],
                                                "eventos": inv["ev_ids"], "proveedores": [p.proveedor_id for p in inv["proveedores"]],
                                                "conservados": [e.evento_id for e, _ in inv["dudosos"]]}, indent=1), encoding="utf-8")
    if not a.ejecutar:
        print("\nInventario terminado (solo lectura). No se borró nada.")
        return 0
    if a.confirmo_base != BASE_AUTORIZADA or not a.respaldo:
        raise SystemExit("Para ejecutar se necesita --respaldo y --confirmo-base eventosnova_manual_test.")
    validar_respaldo(a.respaldo)
    print("\nCopia de seguridad validada. Ejecutando la limpieza en una sola transacción…")
    with motor.begin() as con:                                   # si algo falla, se revierte todo
        verificar_destino(con)
        ejecutar(con, inv)
        comprobar_integridad(con, inv)
        despues = recuento(con)
    print("Transacción confirmada. Filas por tabla (antes → después):")
    for t in antes:
        print(f"  {t:<36} {antes[t]:>4} → {despues[t]:>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
