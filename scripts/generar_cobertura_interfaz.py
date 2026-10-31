"""Genera docs/INTERFAZ_WEB_COBERTURA.md: la correspondencia entre cada operación de docs/api/openapi.json y la interfaz web.

    python scripts/generar_cobertura_interfaz.py              # escribe el documento
    python scripts/generar_cobertura_interfaz.py --comprobar  # sale con 1 si no está al día o falta alguna operación

Las columnas «Datos de entrada» salen del OpenAPI; el resto está declarado aquí, a mano, y la prueba tests/test_interfaz_web.py
exige que cada operación del OpenAPI tenga su fila (una operación nueva sin fila hace fallar la prueba)."""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
OPENAPI = RAIZ / "docs" / "api" / "openapi.json"
DESTINO = RAIZ / "docs" / "INTERFAZ_WEB_COBERTURA.md"

OK = "Implementada"
TEC = "No aplica (técnico)"
EV, CONT, PAG, SOL, SEG, PROV, SIS, PAN = ("Eventos · detalle", "Eventos · detalle · Contratación", "Eventos · detalle · Pagos / Pagos y devoluciones",
                                           "Solicitudes / Eventos · detalle", "Seguimiento", "Proveedores", "Sistema y ayuda", "Panel principal")

# (método, ruta): (función de negocio, módulo, pantalla o acción, resultado esperado, estado, observaciones)
FILAS = {
    ("GET", "/"): ("Identificación de la aplicación", SIS, "No tiene pantalla propia", "JSON con nombre y versión", TEC, "Se conserva sin cambios; la interfaz vive en /app/."),
    ("GET", "/health"): ("Disponibilidad", SIS, "Estado del servicio", "Insignia «Disponible»", OK, "Sigue disponible para sondas externas."),
    ("GET", "/ready"): ("Disponibilidad de la base de datos", SIS, "Estado del servicio", "Insignia con el modo de persistencia", OK, "Sin PostgreSQL en marcha muestra «No disponible»."),
    ("GET", "/eventos"): ("Consultar eventos por ventana de fechas", f"Eventos; {PAN}", "Lista con filtros de fechas, estado y búsqueda", "Tabla de eventos con estado oficial", OK,
                          "La API solo consulta por rango de fecha del evento; no existe un listado sin rango. La búsqueda por texto se hace en el navegador sobre el resultado."),
    ("POST", "/eventos"): ("Registrar un evento", "Eventos", "Botón «Registrar evento»", "Evento En gestión y salto a su detalle", OK, "El cliente se identifica con un texto libre (no hay catálogo de clientes)."),
    ("GET", "/eventos/{evento_id}/administracion"): ("Información administrativa del evento", EV, "Encabezado, contratos, resumen económico, proveedores", "Datos y estados del evento", OK, "Es la única consulta de detalle de evento y de contratos."),
    ("GET", "/eventos/{evento_id}/pagos"): ("Estado de los pagos del evento", PAG, "Tarjeta «Estado de cuenta»", "Anticipo, saldo, pagos, otras obligaciones y devoluciones; `plazoVencido`", OK,
                                           "`plazoVencido` se muestra tal como lo devuelve la API, sin recalcularlo."),
    ("GET", "/eventos/{evento_id}/solicitudes-pendientes"): ("Solicitudes pendientes del evento", SOL, "Texto «Pendiente: …» bajo el estado", "Acción pendiente de cada solicitud", OK, ""),
    ("POST", "/eventos/{evento_id}/propuestas"): ("Crear la propuesta", EV, "Botón «Crear propuesta» (evento En gestión)", "Propuesta creada; se recuerda en este navegador", OK,
                                                  "La API no tiene consulta de propuestas: la interfaz las recuerda localmente (se rotula como tal)."),
    ("POST", "/propuestas/{propuesta_id}/versiones"): ("Generar nueva versión", EV, "Botón «Generar nueva versión»", "Versión vigente nueva", OK, "El identificador de versión es el que devuelve la API."),
    ("POST", "/propuestas/{propuesta_id}/aceptacion"): ("Aceptar la versión vigente", EV, "Botón «Aceptar propuesta»", "Propuesta aceptada", OK,
                                                         "La versión propuesta es `<propuesta>-v<n>` según lo registrado en este navegador; el backend valida que sea la vigente."),
    ("POST", "/propuestas/{propuesta_id}/cierre-por-no-aceptacion"): ("Cerrar por no aceptación", EV, "Botón «Cerrar por no aceptación» (con confirmación)", "Propuesta cerrada", OK, ""),
    ("POST", "/propuestas/{propuesta_id}/contrato"): ("Preparar el contrato", EV, "Botón «Preparar contrato»", "Contrato En preparación", OK, "El identificador del contrato se consulta después en la administración del evento."),
    ("POST", "/contratos/{contrato_id}/comunicacion-politica-no-reembolso"): ("Comunicar la política de no reembolso", CONT, "Botón «Comunicar política de no reembolso»", "Comunicación registrada", OK, "Se ofrece antes de la firma."),
    ("POST", "/contratos/{contrato_id}/firma"): ("Registrar la firma del contrato", CONT, "Botón «Registrar firma del contrato»", "Contrato Firmado", OK,
                                                  "Solo anota la firma; no es firma electrónica. Pide confirmar que la política fue comunicada."),
    ("POST", "/contratos/{contrato_id}/seguimiento-anticipo"): ("Seguimiento del anticipo pendiente", CONT, "Botón «Dar seguimiento al anticipo»", "Seguimiento registrado o contratación cerrada", OK, ""),
    ("POST", "/contratos/{contrato_id}/confirmacion"): ("Confirmar la contratación", CONT, "Botón «Confirmar la contratación»", "Contratación confirmada", OK,
                                                         "Con anticipo verificado el sistema confirma por sí mismo; el botón solo aparece si el contrato sigue Firmado con anticipo Liquidada."),
    ("POST", "/estados-cuenta/{estado_cuenta_id}/pagos"): ("Registrar (y verificar) un pago", PAG, "Botón «Registrar pago»", "Pago Registrado o Verificado", OK, "No procesa cobros: solo anota pagos ya efectuados."),
    ("POST", "/estados-cuenta/{estado_cuenta_id}/pagos/{pago_id}/verificacion"): ("Verificar un pago registrado", PAG, "Botón «Verificar pago»", "Pago Verificado", OK,
                                                                                  "La consulta de pagos no incluye identificadores; se proponen los pagos registrados desde este navegador y se puede escribir otro."),
    ("POST", "/estados-cuenta/{estado_cuenta_id}/vencimiento-saldo-original"): ("Registrar el vencimiento del saldo", PAG, "Botón «Registrar vencimiento del saldo»", "Saldo Vencido", OK, "Solo se ofrece con `plazoVencido`."),
    ("POST", "/estados-cuenta/{estado_cuenta_id}/protocolo-cobro"): ("Activar el protocolo de cobro", PAG, "Botón «Activar protocolo de cobro»", "Protocolo activo", OK, "Solo con saldo Vencida."),
    ("POST", "/estados-cuenta/{estado_cuenta_id}/regularizacion"): ("Resultado de la regularización", PAG, "Botón «Registrar regularización del saldo»", "Regularizado o plazo vencido", OK, "Solo con saldo Vencida."),
    ("GET", "/pagos-pendientes"): ("Obligaciones pendientes o vencidas", f"Pagos y devoluciones; {PAN}", "Tabla con acción «Registrar pago»", "Saldos y fechas límite", OK, ""),
    ("GET", "/devoluciones-pendientes"): ("Devoluciones pendientes", f"Pagos y devoluciones; {PAN}", "Tabla con acción «Registrar devolución efectuada»", "Devoluciones y su plazo", OK, ""),
    ("POST", "/estados-cuenta/{estado_cuenta_id}/devoluciones/{devolucion_id}/ejecucion"): ("Registrar y ejecutar una devolución", PAG, "Botón «Registrar devolución efectuada»", "Devolución Efectuada", OK, "Comprobante opcional."),
    ("POST", "/eventos/{evento_id}/inicio"): ("Registrar el inicio del evento", EV, "Botón «Registrar inicio del evento» (En organización)", "Evento En ejecución", OK, "El trabajador automático también lo hace al llegar T."),
    ("POST", "/eventos/{evento_id}/finalizacion"): ("Registrar la finalización", EV, "Botón «Registrar finalización del evento» (En ejecución)", "Evento Finalizado", OK, ""),
    ("POST", "/eventos/{evento_id}/cancelacion"): ("Cancelación solicitada por el Cliente", EV, "Botón «Cancelar evento» (con confirmación)", "Evento Cancelado", OK, "Se ofrece con el evento En organización."),
    ("POST", "/eventos/{evento_id}/cancelacion-por-falta-de-regularizacion"): ("Cancelación por falta de regularización", EV, "Botón «Cancelar por falta de regularización»", "Evento Cancelado", OK, "Solo con saldo Vencida."),
    ("POST", "/eventos/{evento_id}/revision-administrativa"): ("Revisión administrativa de un evento cancelado", EV, "Botón «Registrar revisión administrativa» (Cancelado)", "Revisión registrada", OK, ""),
    ("GET", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/disponibilidad"): ("Disponibilidad de proveedores de un servicio", EV, "Botón «Ver disponibilidad»", "Diálogo con la respuesta", OK, ""),
    ("POST", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/proveedor"): ("Asignar un proveedor", EV, "Botón «Asignar proveedor»", "Servicio pendiente de confirmación del proveedor", OK, ""),
    ("POST", "/eventos/{evento_id}/servicios/{servicio_contratado_id}/respuesta-proveedor"): ("Respuesta del proveedor", EV, "Botón «Registrar respuesta del proveedor»", "Servicio confirmado o proveedor no disponible", OK, ""),
    ("POST", "/auth/inicio-sesion"): ("Iniciar sesión", "Ingreso", "Pantalla de inicio de sesión", "Sesión con cookie HttpOnly y menús según el rol", OK, "Las credenciales las valida el servidor; tras 5 fallos seguidos se bloquea el intento unos minutos."),
    ("GET", "/auth/yo"): ("Sesión actual", "Ingreso", "Se consulta al abrir la aplicación", "Quién es la persona, su rol y sus permisos", OK, "Sin sesión vigente muestra el ingreso."),
    ("POST", "/auth/cierre-sesion"): ("Cerrar sesión", "Ingreso", "Botón «Cerrar sesión»", "Vuelve al ingreso; la sesión queda invalidada en el servidor", OK, ""),
    ("POST", "/auth/cambio-contrasena"): ("Cambiar la contraseña propia", "Ingreso", "Botón «Cambiar contraseña»", "Se cierran todas las sesiones y se pide ingresar de nuevo", OK, ""),
    ("GET", "/usuarios"): ("Listar cuentas", "Cuentas (administración)", "Lista de cuentas", "Tabla con rol, proveedor y estado", OK, "Solo el rol administrador."),
    ("POST", "/usuarios"): ("Crear una cuenta", "Cuentas (administración)", "Botón «Crear cuenta»", "Cuenta con el rol indicado (nunca por omisión)", OK, "Solo el rol administrador; las cuentas de proveedor se vinculan a un proveedor del catálogo."),
    ("POST", "/usuarios/{usuario_id}/estado"): ("Activar o desactivar una cuenta", "Cuentas (administración)", "Botones «Desactivar» y «Activar»", "La baja cierra sus sesiones de inmediato", OK, "No se puede desactivar la propia cuenta ni al último administrador."),
    ("POST", "/usuarios/{usuario_id}/contrasena"): ("Restablecer la contraseña de una cuenta", "Cuentas (administración)", "Botón «Restablecer contraseña»", "Cierra las sesiones de la cuenta", OK, ""),
    ("POST", "/proveedores"): ("Registrar un proveedor en el catálogo", PROV, "Botón «Registrar proveedor»", "Proveedor creado y salto a su ficha", OK,
                               "Extensión D-P1 pendiente de aprobación: solo nombre (obligatorio), servicios que ofrece y contacto. Sin tarifas ni condiciones."),
    ("GET", "/proveedores"): ("Consultar y buscar proveedores", PROV, "Lista con búsqueda por texto y por servicio", "Tabla de proveedores", OK,
                              "También alimenta el nombre legible del proveedor al asignar un servicio."),
    ("GET", "/proveedores/{proveedor_id}"): ("Datos de un proveedor", PROV, "Ficha del proveedor", "Nombre, servicios, contacto y fecha de registro", OK,
                                             "Responde 404 si el identificador no está en el catálogo."),
    ("GET", "/proveedores/{proveedor_id}/eventos/{evento_id}"): ("Servicios que un proveedor tiene en un evento", PROV, "Formulario de consulta", "Datos del evento y sus servicios", OK, "Responde 404 si el proveedor no tiene servicios en el evento (BN-007)."),
    ("GET", "/servicios-pendientes-confirmacion"): ("Servicios y solicitudes pendientes de confirmación", f"{SEG}; {PAN}", "Dos tablas", "Pendientes por confirmar", OK, ""),
    ("GET", "/solicitudes"): ("Solicitudes por estado, evento y tipo", f"Solicitudes; {EV}", "Tabla con filtros", "Solicitudes con su estado oficial", OK, "Se muestra el estado exacto de la API, sin agrupar."),
    ("POST", "/solicitudes-cambio"): ("Registrar una solicitud de cambio", EV, "Botón «Solicitar cambio» (En organización con contrato confirmado)", "Solicitud Registrada", OK, "El plazo lo valida el backend."),
    ("POST", "/solicitudes-cambio/{solicitud_id}/viabilidad"): ("Evaluar la viabilidad", SOL, "Acción según estado «Registrada»", "No procedente / pendiente de aprobación / formalización", OK, ""),
    ("POST", "/solicitudes-cambio/{solicitud_id}/decision-cliente"): ("Decisión del Cliente", SOL, "Acción según estado «Pendiente de aprobación del Cliente»", "Pendiente de autorización o rechazada", OK, ""),
    ("POST", "/solicitudes-cambio/{solicitud_id}/autorizacion"): ("Autorización de Administración", SOL, "Acción según estado «Pendiente de autorización»", "Pendiente de formalización o no autorizada", OK, ""),
    ("POST", "/solicitudes-cambio/{solicitud_id}/anexo"): ("Anexo del contrato", SOL, "Acción según estado «Pendiente de formalización»", "Anexo registrado", OK, "La lista no indica si ya tiene anexo; el backend lo rechaza si lo tiene."),
    ("POST", "/solicitudes-cambio/{solicitud_id}/solicitud-pago"): ("Comunicar la solicitud de pago", SOL, "Acción según estado «Pendiente de formalización»", "Pendiente de pago", OK, "Se rechaza si el cambio no genera importes."),
    ("POST", "/solicitudes-cambio/{solicitud_id}/confirmacion"): ("Confirmar el cambio", SOL, "Acción según estado", "Cambio Confirmada", OK, "El backend lista lo que falte."),
    ("POST", "/solicitudes-cambio/{solicitud_id}/cierre-por-falta-de-pago"): ("Cerrar por falta de pago", SOL, "Acción en «Pendiente de pago» (con confirmación)", "Cerrada por falta de pago", OK, ""),
    ("POST", "/solicitudes-servicio-adicional"): ("Registrar un servicio adicional", EV, "Botón «Solicitar servicio adicional»", "Solicitud Registrada o No procedente", OK,
                                                  "También se ofrece con el evento En ejecución: el backend la registra como «No procedente» (GL-015, SE-004)."),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/disponibilidad"): ("Evaluar disponibilidad de proveedores", SOL, "Acción en «Registrada» o «En búsqueda de proveedor»", "Pendiente de aprobación, en búsqueda o no procedente", OK, ""),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/decision-espera"): ("Decisión de espera del Cliente", SOL, "Acción en «En búsqueda de proveedor»", "Sigue la búsqueda o no se realizará", OK, ""),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/aprobacion-cliente"): ("Aprobación del Cliente", SOL, "Acción en «Pendiente de aprobación del Cliente»", "Pendiente de autorización o no aprobada", OK, ""),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/autorizacion"): ("Autorización de Administración", SOL, "Acción en «Pendiente de autorización»", "Autorizada o no autorizada", OK, ""),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/anexo"): ("Anexo del contrato", SOL, "Acción en «Autorizada»", "Anexo registrado", OK, ""),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/solicitud-pago"): ("Comunicar la solicitud de pago", SOL, "Acción en «Autorizada»", "Pendiente de pago", OK, "El concepto se envía como `ServicioAdicional`."),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/confirmacion"): ("Confirmar el servicio adicional", SOL, "Acción en «Pendiente de pago»", "Confirmada", OK, ""),
    ("POST", "/solicitudes-servicio-adicional/{solicitud_id}/cierre-por-falta-de-pago"): ("Cerrar por falta de pago", SOL, "Acción en «Pendiente de pago» (con confirmación)", "Cerrada por falta de pago", OK, ""),
    ("POST", "/sustituciones"): ("Iniciar la sustitución de un proveedor", EV, "Botón «Sustituir proveedor»", "Sustitución En búsqueda de alternativa", OK, ""),
    ("POST", "/sustituciones/{sustitucion_id}/alternativa"): ("Proponer una alternativa", SOL, "Acción en «En búsqueda de alternativa»", "Pendiente de aprobación o de formalización", OK, ""),
    ("POST", "/sustituciones/{sustitucion_id}/decision-cliente"): ("Decisión del Cliente", SOL, "Acción en «Pendiente de aprobación del Cliente»", "Pendiente de autorización o nueva búsqueda", OK, ""),
    ("POST", "/sustituciones/{sustitucion_id}/autorizacion"): ("Autorización de Administración", SOL, "Acción en «Pendiente de autorización»", "Pendiente de formalización o nueva búsqueda", OK, ""),
    ("POST", "/sustituciones/{sustitucion_id}/anexo"): ("Anexo del contrato", SOL, "Acción en «Pendiente de formalización»", "Anexo registrado", OK, ""),
    ("POST", "/sustituciones/{sustitucion_id}/importe-adicional"): ("Integrar el importe adicional al saldo", SOL, "Acción en «Pendiente de formalización»", "Importe integrado", OK, ""),
    ("POST", "/sustituciones/{sustitucion_id}/confirmacion"): ("Confirmar la sustitución", SOL, "Acción en «Pendiente de formalización»", "Sustitución Confirmada", OK, ""),
}


def _entrada(doc, op) -> str:
    partes = [f"`{p['name']}`" + ("*" if p.get("required") else "") for p in op.get("parameters", []) if p["in"] in ("path", "query")]
    ref = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref")
    if ref:
        esquema = doc["components"]["schemas"][ref.split("/")[-1]]
        req = set(esquema.get("required", []))
        partes += [f"`{k}`" + ("*" if k in req else "") for k in esquema.get("properties", {})]
    return ", ".join(partes) or "—"


def generar() -> str:
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    ops = [(m.upper(), ruta, op) for ruta, ops in doc["paths"].items() for m, op in ops.items()]
    faltan = [(m, r) for m, r, _ in ops if (m, r) not in FILAS]
    sobran = [k for k in FILAS if k not in {(m, r) for m, r, _ in ops}]
    if faltan or sobran:
        raise SystemExit(f"La matriz no coincide con el OpenAPI. Sin fila: {faltan}. Filas sin operación: {sobran}")
    lineas = [
        "# Cobertura de la API por la interfaz web",
        "",
        "> Documento **generado** por `scripts/generar_cobertura_interfaz.py` a partir de `docs/api/openapi.json` (no editar a mano; la prueba `tests/test_interfaz_web.py` lo comprueba).",
        "",
        f"La API tiene **{len(ops)} operaciones**; todas aparecen aquí. «Implementada» significa que existe una pantalla o botón que envía la petición real y muestra la respuesta; "
        "no hay botones decorativos. Los datos de entrada marcados con `*` son obligatorios en la API. La interfaz habilita los botones según el estado oficial devuelto, pero el backend sigue decidiendo: "
        "si rechaza una operación, el motivo se muestra tal cual.",
        "",
        "| Método | Ruta | Función de negocio | Módulo de la interfaz | Pantalla o acción | Datos de entrada | Resultado esperado | Estado | Observaciones |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m, r, op in ops:
        f, mod, pant, res, est, obs = FILAS[(m, r)]
        lineas.append(f"| {m} | `{r}` | {f} | {mod} | {pant} | {_entrada(doc, op)} | {res} | {est} | {obs or '—'} |")
    lineas += ["", "## Limitaciones reales de la API que condicionan la interfaz", "",
               "- No hay módulo de **Clientes**: la API no tiene endpoints de clientes; `cliente_id` es un texto libre al registrar el evento.",
               "- No existe un listado de eventos sin rango de fechas ni una consulta de un evento por identificador distinta de `/administracion`.",
               "- No hay consulta de **propuestas** ni de un **pago** por identificador: la interfaz recuerda en el navegador los identificadores de lo que se crea desde ella (`localStorage`, solo en ese navegador).",
               "- No hay autenticación, roles ni permisos: cualquier persona con acceso a la dirección puede ejecutar cualquier operación.",
               "- No hay pasarela de pago: solo se registran pagos ya efectuados.",
               "- Las solicitudes no exponen si ya tienen anexo ni el costo: la lista se limita al estado oficial; el backend rechaza lo que no proceda.", ""]
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comprobar", action="store_true")
    texto = generar()
    if parser.parse_args().comprobar:
        actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if actual != texto:
            print("La matriz no está al día: ejecute scripts/generar_cobertura_interfaz.py", file=sys.stderr)
            return 1
        print("Matriz al día.")
        return 0
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
