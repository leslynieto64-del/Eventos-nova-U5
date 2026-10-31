"""Codec de Domain Events para el Outbox (columna JSONB `outbox_evento.datos`).

Estrategia versionada: `datos = {"version": N, "campos": {...}}`. Solo se serializan los campos PROPIOS de cada evento; los tres
campos comunes (`evento_id`, `agregado_id`, `ocurrido_en`) y el nombre de la clase (`tipo_evento`) tienen sus propias columnas.
No se serializan agregados. Los valores que JSON no representa se guardan con una etiqueta `"$t"` para recuperarlos sin pérdida:
`datetime` (ISO, sin zona), `decimal`/`Importe` (cadena: nunca float), `tupla`, `enum` y objetos de valor (`vo`).

El registro de tipos es EXPLÍCITO (`TIPOS_DE_EVENTO`); una prueba comprueba que coincide con las clases reales del dominio, de modo
que un evento nuevo obliga a registrarlo. Un tipo desconocido, una versión incompatible o datos inválidos producen
`EventoNoRehidratable` (error controlado y observable): el registro del Outbox nunca se descarta en silencio."""
from __future__ import annotations
import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Tuple, Type
from domain import eventos_dominio as E
from domain import valores as V
from .errores import ErrorDePersistencia, EventoNoRehidratable

VERSION_ACTUAL = 1
VERSIONES_SOPORTADAS = (1,)
CAMPOS_COMUNES = ("agregado_id", "ocurrido_en", "evento_id")

TIPOS_DE_EVENTO: Tuple[Type[E.EventoDominio], ...] = (
    # Coordinación
    E.PropuestaAceptada, E.ContratoFirmado, E.PagoVerificado, E.ContratacionConfirmada, E.ProcesoContratacionCerrado,
    E.AnexoContratoRegistrado, E.CambioConfirmado, E.ServicioAdicionalConfirmado, E.ProveedorNoDisponible,
    E.SustitucionProveedorConfirmada, E.EventoIniciado, E.SolicitudCambioCerradaPorInicioEvento,
    E.ServicioAdicionalCerradoPorInicioEvento, E.SustitucionProveedorCerradaPorInicioEvento,
    E.SolicitudCambioCerradaPorFaltaDePago, E.ServicioAdicionalCerradoPorFaltaDePago, E.SaldoContratoOriginalVencido,
    E.SaldoVencidoRegularizado, E.PlazoRegularizacionVencido, E.EventoCancelado, E.EventoFinalizado, E.DevolucionRegistrada,
    # Auditoría
    E.VersionPropuestaGenerada, E.PropuestaCerradaPorNoAceptacion, E.CambioSolicitado, E.ViabilidadCambioEvaluada,
    E.ServicioAdicionalSolicitado, E.AlternativaProveedorEncontrada, E.AlternativaRechazadaPorCliente,
    E.AlternativaNoAutorizadaPorAdministracion, E.CargosMoratoriosComunicados,
)
REGISTRO: Dict[str, Type[E.EventoDominio]] = {c.__name__: c for c in TIPOS_DE_EVENTO}

# Objetos de valor que pueden viajar dentro de un evento (los de `eventos_dominio` hoy: DatosEvento y CondicionesServicio).
OBJETOS_DE_VALOR: Dict[str, type] = {c.__name__: c for c in (V.DatosEvento, V.CondicionesServicio, V.Importe)}
ENUMERACIONES: Dict[str, Type[Enum]] = {n: c for n, c in vars(V).items() if isinstance(c, type) and issubclass(c, Enum) and c is not Enum}


# ---------------------------------------------------------------- valores
def codificar_valor(valor: Any) -> Any:
    if valor is None or isinstance(valor, (bool, int, str)):
        return valor
    if isinstance(valor, float):
        raise ErrorDePersistencia("Un float no es un valor válido de un Domain Event (usar Decimal).")
    if isinstance(valor, datetime):
        return {"$t": "datetime", "v": valor.isoformat()}
    if isinstance(valor, Decimal):
        return {"$t": "decimal", "v": str(valor)}
    if isinstance(valor, Enum):
        return {"$t": "enum", "clase": type(valor).__name__, "v": valor.name}
    if isinstance(valor, tuple):
        return {"$t": "tupla", "v": [codificar_valor(x) for x in valor]}
    if isinstance(valor, list):
        return [codificar_valor(x) for x in valor]
    if dataclasses.is_dataclass(valor) and type(valor).__name__ in OBJETOS_DE_VALOR and type(valor) is OBJETOS_DE_VALOR[type(valor).__name__]:
        return {"$t": "vo", "clase": type(valor).__name__,
                "campos": {f.name: codificar_valor(getattr(valor, f.name)) for f in dataclasses.fields(valor)}}
    raise ErrorDePersistencia(f"El valor de tipo {type(valor).__name__} no está soportado por el codec de eventos.")


def decodificar_valor(j: Any) -> Any:
    if j is None or isinstance(j, (bool, int, str)):
        return j
    if isinstance(j, list):
        return [decodificar_valor(x) for x in j]
    if isinstance(j, dict) and "$t" in j:
        t = j["$t"]
        if t == "datetime":
            return datetime.fromisoformat(j["v"])
        if t == "decimal":
            return Decimal(j["v"])
        if t == "tupla":
            return tuple(decodificar_valor(x) for x in j["v"])
        if t == "enum":
            return ENUMERACIONES[j["clase"]][j["v"]]
        if t == "vo":
            clase = OBJETOS_DE_VALOR[j["clase"]]
            return clase(**{k: decodificar_valor(v) for k, v in j["campos"].items()})
    raise ValueError(f"valor JSON no reconocido: {j!r}")


# ---------------------------------------------------------------- eventos
def campos_propios(clase: Type[E.EventoDominio]):
    return [f for f in dataclasses.fields(clase) if f.name not in CAMPOS_COMUNES]


def codificar(evento: E.EventoDominio) -> Dict[str, Any]:
    """Contenido de la columna JSONB `datos` (siempre un objeto)."""
    clase = type(evento)
    if REGISTRO.get(clase.__name__) is not clase:
        raise ErrorDePersistencia(f"El evento {clase.__name__} no está registrado en el codec del Outbox.")
    return {"version": VERSION_ACTUAL, "campos": {f.name: codificar_valor(getattr(evento, f.name)) for f in campos_propios(clase)}}


def decodificar(tipo_evento: str, agregado_id: str, ocurrido_en: datetime, evento_id: str, datos: Any) -> E.EventoDominio:
    """Reconstruye el evento o lanza `EventoNoRehidratable` (nunca devuelve algo parcial)."""
    def fallo(motivo: str, causa: BaseException = None):
        error = EventoNoRehidratable(f"Evento «{evento_id}» de tipo «{tipo_evento}» no rehidratable: {motivo}", evento_id, tipo_evento)
        if causa is not None:
            error.__cause__ = causa
        return error
    clase = REGISTRO.get(tipo_evento)
    if clase is None:
        raise fallo("tipo de evento desconocido")
    if not isinstance(datos, dict) or datos.get("version") not in VERSIONES_SOPORTADAS or not isinstance(datos.get("campos"), dict):
        version = datos.get("version") if isinstance(datos, dict) else None
        raise fallo(f"versión de datos incompatible ({version!r}; soportadas: {list(VERSIONES_SOPORTADAS)})")
    esperados = {f.name for f in campos_propios(clase)}
    sobran = set(datos["campos"]) - esperados
    if sobran:
        raise fallo(f"campos desconocidos para este tipo: {sorted(sobran)}")
    try:
        campos = {k: decodificar_valor(v) for k, v in datos["campos"].items()}
        return clase(agregado_id=agregado_id, ocurrido_en=ocurrido_en, evento_id=evento_id, **campos)
    except Exception as e:                                            # datos corruptos, enumeración inexistente, VO inválido...
        raise fallo(f"datos inválidos ({type(e).__name__}: {e})", e)
