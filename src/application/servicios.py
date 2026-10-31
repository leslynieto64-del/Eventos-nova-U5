"""Application Services (Etapa 4). Coordinan casos de uso; las reglas viven en el dominio.
Cada método de escritura usa IUnitOfWork; los Domain Events se publican después del commit (Outbox)."""
from __future__ import annotations
import functools
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from domain.valores import (ErrorDominio, DatosEvento, ContenidoPropuesta, CondicionesContractuales, PoliticaNoReembolso,
                            Importe, Decision, AnticipacionSolicitud, TarifaCargoTardio, ResultadoViabilidad,
                            TipoSolicitud, ConceptoPago, EstadoSolicitudCambio, EstadoSolicitudServicioAdicional, EstadoServicioContratado,
                            EstadoEvento,
                            EstadoContrato, CondicionesServicio, limite_exclusivo_dias_habiles)
from domain.propuesta import Propuesta
from domain.contrato import Contrato, EvidenciaAnticipo
from domain.evento import Evento, RevisionAdministrativa
from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor, AlternativaPropuesta
from domain.estado_cuenta import EstadoCuenta
from domain.proveedor import Proveedor
from domain.servicios_dominio import (EvaluarImpactoCambio, EvaluarRegularizacionDeSolicitudes, SituacionSaldo,
                                      ConfiguracionComparable)
from .puertos import (IPropuestaRepository, IContratoRepository, IEventoRepository, ISolicitudCambioRepository,
                      ISolicitudServicioAdicionalRepository, ISustitucionProveedorRepository, IEstadoCuentaRepository,
                      IUnitOfWork, IConsultaDisponibilidadProveedor, INotificadorParticipantes, IVerificadorPagos,
                      IEjecutorDevoluciones, IProveedorRepository)
from .resultados import Resultado


def nuevo_id(prefijo: str) -> str:
    """Identificador nuevo: prefijo + UUID versión 4 completo (122 bits aleatorios). Los identificadores históricos de 8
    caracteres hexadecimales siguen siendo válidos: ningún código asume una longitud ni un formato de la parte aleatoria."""
    return f"{prefijo}-{uuid.uuid4()}"


def nuevo_id_libre(prefijo: str, repositorio) -> str:
    """Identificador de una raíz de agregado nueva que no existe todavía en su repositorio. El guardado es un *upsert* por
    clave primaria, de modo que un id repetido sobrescribiría el agregado existente: con 122 bits aleatorios es
    estadísticamente improbable (no imposible), y esta comprobación impide que ocurra por accidente al crear. La clave
    primaria de la base de datos sigue protegiendo frente a duplicados entre tablas hijas."""
    for _ in range(5):
        candidato = nuevo_id(prefijo)
        if repositorio.obtener_por_id(candidato) is None:
            return candidato
    raise RuntimeError(f"No se pudo generar un identificador {prefijo} libre.")


@contextmanager
def transaccion(uow: IUnitOfWork, *agregados):
    """Inicio y fin transaccional explícitos: confirmar() o revertir()."""
    uow.iniciar()
    try:
        uow.registrar(*agregados)
        yield
        uow.confirmar()
    except Exception:
        uow.revertir()
        raise


def con_rechazos_de_negocio(cls):
    """Los métodos que devuelven Resultado convierten un ErrorDominio en un rechazo con su motivo de negocio.
    Las fallas técnicas (otras excepciones) se propagan para poder reintentarse."""
    for nombre, metodo in list(vars(cls).items()):
        if callable(metodo) and not nombre.startswith('_') and getattr(metodo, '__annotations__', {}).get('return') == 'Resultado':
            def envolver(m):
                @functools.wraps(m)
                def w(*a, **k):
                    try:
                        return m(*a, **k)
                    except ErrorDominio as e:
                        return Resultado.rechazo(str(e))
                return w
            setattr(cls, nombre, envolver(metodo))
    return cls


def _existente(agregado, descripcion: str):
    """H-07/H-17: un identificador inexistente es un rechazo de negocio (ErrorDominio), no una falla técnica."""
    if agregado is None:
        raise ErrorDominio(f"{descripcion} no existe.")
    return agregado


def _estado_cuenta_del_contrato(ec_repo: IEstadoCuentaRepository, contrato_id: str) -> EstadoCuenta:
    """H-07: el estado de cuenta nace al firmarse el contrato; sin él no hay solicitudes ni sustituciones posibles."""
    ec = ec_repo.obtener_por_contrato_id(contrato_id)
    if ec is None:
        raise ErrorDominio("El contrato no existe o todavía no tiene estado de cuenta: la contratación debe estar firmada.")
    return ec


def _exigir_evento_del_contrato(contratos: IContratoRepository, contrato_id: str, evento_id: str) -> None:
    """Decisión de implementación del equipo E-2 (no la exigen las fuentes originales): la solicitud de cambio, de servicio
    adicional o la sustitución se refieren al evento del contrato relacionado. Solo lectura: se rechaza antes de crear o
    modificar cualquier agregado. Un contrato inexistente lo rechaza el flujo habitual (sin estado de cuenta)."""
    contrato = contratos.obtener_por_id(contrato_id)
    if contrato is not None and contrato.evento_id != evento_id:
        raise ErrorDominio("El evento de la solicitud no coincide con el evento del contrato: la solicitud debe referirse "
                           "al evento contratado.")


def _saldo(ec_repo: IEstadoCuentaRepository, contrato_id: str, ahora: datetime) -> SituacionSaldo:
    """GL-049, SE-006: el saldo cuenta como vencido por el hecho (plazo terminado sin pago a tiempo que lo cubra), no solo por haberse
    registrado su vencimiento."""
    ec = ec_repo.obtener_por_contrato_id(contrato_id)
    return SituacionSaldo(bool(ec and ec.saldo_vencido_en(ahora)))


# ======================================================================= CU-01
@con_rechazos_de_negocio
class GestionPropuestaService:
    def __init__(self, propuestas: IPropuestaRepository, eventos: IEventoRepository, uow: IUnitOfWork):
        self.propuestas, self.eventos, self.uow = propuestas, eventos, uow

    def registrar_evento(self, cliente_id: str, datos: DatosEvento, servicios: List[str]) -> Resultado:
        try:
            ev = Evento(nuevo_id_libre("EV", self.eventos), cliente_id, datos, servicios)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        with transaccion(self.uow, ev):
            self.eventos.guardar(ev)
        return Resultado.ok("Evento registrado En gestión.", evento_id=ev.id)

    def crear_propuesta(self, evento_id: str, contenido: ContenidoPropuesta, ahora: datetime) -> Resultado:
        ev = self.eventos.obtener_por_id(evento_id)               # solo lectura
        if ev is None or ev.estado.value != "En gestión":
            return Resultado.rechazo("El evento no existe o no está En gestión.")
        p = Propuesta(nuevo_id_libre("PR", self.propuestas), evento_id, ev.cliente_id, contenido, ahora)
        with transaccion(self.uow, p):
            self.propuestas.guardar(p)
        return Resultado.ok("Propuesta creada.", propuesta_id=p.id)

    def generar_nueva_version(self, propuesta_id: str, contenido: ContenidoPropuesta, ahora: datetime) -> Resultado:
        p = _existente(self.propuestas.obtener_por_id(propuesta_id), "La propuesta")
        try:
            with transaccion(self.uow, p):
                v = p.generar_nueva_version(contenido, ahora)
                self.propuestas.guardar(p)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Nueva versión vigente.", version_id=v.version_id, numero=v.numero)

    def aceptar_propuesta(self, propuesta_id: str, version_id: str, ahora: datetime) -> Resultado:
        p = _existente(self.propuestas.obtener_por_id(propuesta_id), "La propuesta")
        try:
            with transaccion(self.uow, p):
                p.aceptar(version_id, ahora); self.propuestas.guardar(p)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Propuesta aceptada.")

    def cerrar_propuesta_no_aceptada(self, propuesta_id: str, motivo: str, ahora: datetime) -> Resultado:
        p = _existente(self.propuestas.obtener_por_id(propuesta_id), "La propuesta")
        try:
            with transaccion(self.uow, p):
                p.cerrar_por_no_aceptacion(motivo, ahora); self.propuestas.guardar(p)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Propuesta cerrada; el Evento sigue En gestión.")


# ======================================================================= CU-02
@con_rechazos_de_negocio
class FormalizarContratacionService:
    def __init__(self, contratos: IContratoRepository, propuestas: IPropuestaRepository,
                 estados_cuenta: IEstadoCuentaRepository, uow: IUnitOfWork, eventos: Optional[IEventoRepository] = None):
        self.contratos, self.propuestas, self.estados_cuenta, self.uow = contratos, propuestas, estados_cuenta, uow
        self.eventos = eventos

    def preparar_contrato(self, propuesta_id: str, politica_incluida: bool) -> Resultado:
        p = _existente(self.propuestas.obtener_por_id(propuesta_id), "La propuesta")              # solo lectura
        try:
            v = p.version_aceptada()
            if any(c.estado != EstadoContrato.CERRADO_SIN_CONFIRMAR for c in self.contratos.listar_por_evento_id(p.evento_id)):
                return Resultado.rechazo("Ya existe un contrato activo para el evento.")
            c = Contrato(nuevo_id_libre("CT", self.contratos), p.evento_id, p.id, v.version_id,
                         CondicionesContractuales(v.contenido.servicios, v.contenido.costo_total, v.contenido.condiciones),
                         PoliticaNoReembolso(politica_incluida))
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        with transaccion(self.uow, c):
            self.contratos.guardar(c)
        return Resultado.ok("Contrato preparado.", contrato_id=c.id)

    def registrar_comunicacion_politica_no_reembolso(self, contrato_id: str, fecha: datetime) -> Resultado:
        c = _existente(self.contratos.obtener_por_id(contrato_id), "El contrato")
        with transaccion(self.uow, c):
            c.registrar_comunicacion_politica(fecha); self.contratos.guardar(c)
        return Resultado.ok("Comunicación de la política registrada.")

    def registrar_firma_contrato(self, contrato_id: str, fecha: datetime) -> Resultado:
        c = _existente(self.contratos.obtener_por_id(contrato_id), "El contrato")
        try:
            with transaccion(self.uow, c):
                c.firmar(fecha); self.contratos.guardar(c)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Contrato firmado.")

    def dar_seguimiento_anticipo_pendiente(self, contrato_id: str, fecha: datetime, resultado_contacto: str,
                                           sin_pago_tras_seguimiento: bool) -> Resultado:
        """CA-020, CA-021. Sin `sin_pago_tras_seguimiento` registra el contacto, desde el cual el Cliente tiene 24 horas
        naturales para efectuar el anticipo. Con él cierra la contratación solo si vencieron esas 24 horas y el Cliente
        no efectuó el pago dentro de ellas (según la fecha del pago, no la de su registro o verificación).
        Solo modifica Contrato. Evento cambia en la reacción a ProcesoContratacionCerrado."""
        c = _existente(self.contratos.obtener_por_id(contrato_id), "El contrato")
        ec = self.estados_cuenta.obtener_por_contrato_id(contrato_id)          # solo lectura
        if sin_pago_tras_seguimiento:
            limite = c.limite_pago_anticipo()
            pagado_a_tiempo = bool(ec and limite and ec.anticipo_efectuado_hasta(limite))
            try:
                with transaccion(self.uow, c):
                    c.cerrar_sin_confirmar(fecha, pagado_a_tiempo); self.contratos.guardar(c)
            except ErrorDominio as e:
                return Resultado.rechazo(str(e))
            return Resultado.ok("Proceso de contratación cerrado sin confirmar.")
        if ec and ec.anticipo_recibido():
            return Resultado.rechazo("El anticipo ya fue recibido; no procede el seguimiento.")
        plazo_vencido = fecha >= limite_exclusivo_dias_habiles(c.fecha_firma, 3)     # GL-060, C-15, decisión E-1
        try:
            with transaccion(self.uow, c):
                c.registrar_seguimiento_anticipo(fecha, resultado_contacto, plazo_vencido); self.contratos.guardar(c)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Seguimiento registrado: el Cliente dispone de 24 horas naturales para efectuar el anticipo.")

    def confirmar_contratacion(self, contrato_id: str, ahora: datetime) -> Resultado:
        c = _existente(self.contratos.obtener_por_id(contrato_id), "El contrato")
        if c.estado == EstadoContrato.CONTRATACION_CONFIRMADA:
            return Resultado.ok("La contratación ya estaba confirmada.")           # idempotente
        ev = self.eventos.obtener_por_id(c.evento_id) if self.eventos is not None else None
        if ev is not None and ahora >= ev.datos.fecha_hora:                    # D-3b (CA-110, GL-032): T es inclusivo
            return Resultado.rechazo("La contratación ya no puede confirmarse: llegó la fecha y hora programadas del evento (CA-110, GL-032).")
        ec = self.estados_cuenta.obtener_por_contrato_id(contrato_id)          # solo lectura
        limite = c.limite_pago_anticipo()        # tras el contacto, solo cuenta el anticipo efectuado en las 24 horas
        verificado = bool(ec and ec.anticipo_verificado(limite))
        evidencia = EvidenciaAnticipo(bool(ec and ec.anticipo_recibido()), verificado, verificado)
        with transaccion(self.uow, c):
            pendientes = c.confirmar_contratacion(evidencia, ahora)
            self.contratos.guardar(c)
        if pendientes:
            return Resultado.rechazo("Requisitos pendientes para confirmar la contratación.", pendientes)
        return Resultado.ok("Contratación confirmada.")


# ======================================================================= Pagos
@con_rechazos_de_negocio
class GestionPagosService:
    def __init__(self, estados_cuenta: IEstadoCuentaRepository, contratos: IContratoRepository, eventos: IEventoRepository,
                 cambios: ISolicitudCambioRepository, adicionales: ISolicitudServicioAdicionalRepository,
                 sustituciones: ISustitucionProveedorRepository, uow: IUnitOfWork, verificador: IVerificadorPagos,
                 ejecutor: IEjecutorDevoluciones, notificador: INotificadorParticipantes):
        self.ec, self.contratos, self.eventos = estados_cuenta, contratos, eventos
        self.cambios, self.adicionales, self.sustituciones = cambios, adicionales, sustituciones
        self.uow, self.verificador, self.ejecutor, self.notificador = uow, verificador, ejecutor, notificador

    # reacciones
    def registrar_obligacion_anticipo(self, contrato_id: str) -> None:
        c = _existente(self.contratos.obtener_por_id(contrato_id), "El contrato")       # referencia obligatoria (D-01)
        ec = self.ec.obtener_por_contrato_id(contrato_id) or EstadoCuenta(nuevo_id_libre("EC", self.ec), contrato_id, c.evento_id)
        with transaccion(self.uow, ec):
            ec.registrar_obligacion_anticipo(nuevo_id("OB"), c.condiciones.costo_total, c.fecha_firma)
            self.ec.guardar(ec)

    def aplicar_cierre_contratacion(self, contrato_id: str, fecha_cierre: datetime) -> None:
        """Reacción a ProcesoContratacionCerrado (decisión A, C-04): el anticipo Pendiente queda Sin efecto y se registra la
        devolución de lo recibido. Idempotente; no modifica Contrato ni Evento (no se reabre nada)."""
        ec = self.ec.obtener_por_contrato_id(contrato_id)
        if ec is None:
            _existente(self.contratos.obtener_por_id(contrato_id), "El contrato")       # sin estado de cuenta: nada que devolver
            return
        with transaccion(self.uow, ec):
            ec.aplicar_cierre_contratacion(fecha_cierre)
            self.ec.guardar(ec)

    def registrar_obligacion_saldo_original(self, contrato_id: str) -> None:
        c = _existente(self.contratos.obtener_por_id(contrato_id), "El contrato")       # referencia obligatoria (D-01)
        ev = _existente(self.eventos.obtener_por_id(c.evento_id), "El evento")           # solo lectura
        ec = _existente(self.ec.obtener_por_contrato_id(contrato_id), "El estado de cuenta del contrato")
        with transaccion(self.uow, ec):
            ec.registrar_obligacion_saldo_original(nuevo_id("OB"), c.condiciones.costo_total, ev.datos.fecha_hora)
            self.ec.guardar(ec)

    def comunicar_solicitud_pago(self, tipo: TipoSolicitud, solicitud_id: str, concepto: ConceptoPago,
                                 importe: Importe, comunicado_en: datetime) -> Resultado:
        """Servicio adicional. Operación de origen con dos raíces (decisión justificada en la Etapa 3). Los importes de un
        cambio los determina la propia solicitud (E3G): ver comunicar_solicitud_pago_cambio()."""
        if tipo == TipoSolicitud.CAMBIO:
            return Resultado.rechazo("El importe de un cambio lo determina la solicitud (costo del proveedor y cargo por "
                                     "cambio tardío): use la solicitud de pago del cambio (BN-003).")
        s = self.adicionales.obtener_por_id(solicitud_id)
        if s is None:
            return Resultado.rechazo("La solicitud no existe.")
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        oid = nuevo_id("OB")
        try:
            with transaccion(self.uow, ec, s):
                s.registrar_solicitud_pago(oid)                       # valida estado y anexo (CA-082)
                esperado = s.importe_a_cobrar                         # H-06: el costo establecido por el proveedor
                if esperado is None:
                    raise ErrorDominio("No se ha determinado el costo del servicio adicional con el proveedor (BN-004, CA-075).")
                if concepto != ConceptoPago.SERVICIO_ADICIONAL or importe != esperado:
                    raise ErrorDominio("El importe de un servicio adicional es el costo establecido por el proveedor "
                                       "(BN-004, CA-073); no se acepta otro importe ni otro concepto.")
                o = ec.comunicar_solicitud_pago(oid, concepto, importe, solicitud_id, comunicado_en)
                self.ec.guardar(ec); self.adicionales.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        self.notificador.notificar(["Cliente"], "Solicitud de pago", f"Plazo de 24 horas naturales desde {comunicado_en:%d/%m/%Y %H:%M}.")
        return Resultado.ok("Solicitud de pago comunicada.", obligacion_id=o.obligacion_id)

    def comunicar_solicitud_pago_cambio(self, solicitud_id: str, comunicado_en: datetime) -> Resultado:
        """E3G (BN-003, BN-005, SE-005/006, CA-062, CA-063, CA-067, CA-068): una sola comunicación al Cliente, con un plazo de
        24 horas naturales, que genera una obligación independiente por cada concepto. Los importes los determina la
        solicitud: el costo adicional del proveedor y la tarifa vigente del cargo por cambio tardío (cuando corresponde)."""
        s = self.cambios.obtener_por_id(solicitud_id)
        if s is None:
            return Resultado.rechazo("La solicitud de cambio no existe.")
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        importes = s.importes_a_cobrar
        ids = [nuevo_id("OB") for _ in importes] or [nuevo_id("OB")]
        try:
            with transaccion(self.uow, ec, s):
                s.registrar_solicitud_pago(ids[0])           # valida estado, anexo y que existan importes por pagar
                if not importes:
                    raise ErrorDominio("No se pueden determinar los importes: faltan el costo del proveedor o la tarifa "
                                       "vigente del cargo por cambio tardío (BN-003).")
                for oid, (concepto, importe) in zip(ids, importes):
                    ec.comunicar_solicitud_pago(oid, concepto, importe, s.id, comunicado_en)
                self.ec.guardar(ec); self.cambios.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        self.notificador.notificar(["Cliente"], "Solicitud de pago", f"Plazo de 24 horas naturales desde {comunicado_en:%d/%m/%Y %H:%M}.")
        return Resultado.ok("Solicitud de pago comunicada.", obligacion_id=ids[0], obligacion_ids=list(ids),
                            conceptos=[c.value for c, _ in importes])

    def registrar_y_verificar_pago(self, estado_cuenta_id: str, obligacion_id: str, importe: Importe,
                                   fecha: datetime, comprobante: str, registrado_en: Optional[datetime] = None,
                                   verificar_ahora: bool = True) -> Resultado:
        """`fecha`: cuándo el Cliente efectuó el pago (fuera del sistema); `registrado_en`: cuándo Administración lo registra.
        Con `verificar_ahora=False` el pago queda Registrado y se verifica después con verificar_pago_registrado()."""
        verificado = verificar_ahora and self.verificador.verificar(comprobante, importe)   # fuera de la transacción
        ec = _existente(self.ec.obtener_por_id(estado_cuenta_id), "El estado de cuenta")
        try:
            with transaccion(self.uow, ec):
                p = ec.registrar_y_verificar_pago(nuevo_id("PG"), obligacion_id, importe, fecha, comprobante, verificado,
                                                  registrado_en)
                self.ec.guardar(ec)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Pago {p.estado.value}.", pago_id=p.pago_id, estado=p.estado.value)

    def verificar_pago_registrado(self, estado_cuenta_id: str, pago_id: str, verificado_en: datetime) -> Resultado:
        ec = _existente(self.ec.obtener_por_id(estado_cuenta_id), "El estado de cuenta")
        p = next((x for x in ec.pagos if x.pago_id == pago_id), None)
        if p is None or not self.verificador.verificar(p.comprobante, p.importe):          # fuera de la transacción
            return Resultado.rechazo("El pago no pudo verificarse; permanece registrado.")
        devoluciones_antes = {d.devolucion_id for d in ec.devoluciones}
        try:
            with transaccion(self.uow, ec):
                ec.verificar_pago_registrado(pago_id, verificado_en); self.ec.guardar(ec)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        nuevas = [d.devolucion_id for d in ec.devoluciones if d.devolucion_id not in devoluciones_antes]
        if nuevas:      # H-09 (SE-012): pago recibido por una solicitud que se cerró sin realizarse
            return Resultado.ok("Pago Verificado; corresponde su devolución por la operación no realizada (SE-012).",
                                pago_id=pago_id, estado=p.estado.value, devolucion_id=nuevas[0])
        return Resultado.ok("Pago Verificado.", pago_id=pago_id, estado=p.estado.value)

    def registrar_vencimiento_saldo_original(self, estado_cuenta_id: str, ahora: datetime) -> Resultado:
        ec = _existente(self.ec.obtener_por_id(estado_cuenta_id), "El estado de cuenta")
        with transaccion(self.uow, ec):
            vencido = ec.registrar_vencimiento_saldo(ahora); self.ec.guardar(ec)
        return Resultado.ok("Saldo vencido registrado." if vencido else "Sin vencimiento.")

    def activar_protocolo_cobro(self, estado_cuenta_id: str, importe_moratorio: Importe, comunicado_en: datetime,
                                seguimiento: str) -> Resultado:
        ec = _existente(self.ec.obtener_por_id(estado_cuenta_id), "El estado de cuenta")
        try:
            with transaccion(self.uow, ec):
                ec.activar_protocolo_cobro(nuevo_id("OB"), importe_moratorio, comunicado_en, seguimiento); self.ec.guardar(ec)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        self.notificador.notificar(["Cliente"], "Recordatorio de pago", "Saldo vencido y cargos moratorios: 24 horas naturales.")
        return Resultado.ok("Protocolo de cobro activado.")

    def registrar_importe_adicional_sustitucion(self, sustitucion_id: str, importe: Importe) -> Resultado:
        s = _existente(self.sustituciones.obtener_por_id(sustitucion_id), "La sustitución de proveedor")                 # solo lectura
        if not s.importe_adicional_aprobado:
            return Resultado.rechazo("El costo adicional requiere la aprobación del Cliente y la autorización de Administración (CA-052).")
        if importe != s.costo_adicional:
            return Resultado.rechazo("El importe no coincide con el costo adicional aprobado.")
        ev = self.eventos.obtener_por_id(s.evento_id)                         # solo lectura
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        with transaccion(self.uow, ec):
            o = ec.registrar_importe_adicional_sustitucion(nuevo_id("OB"), importe, sustitucion_id,
                                                           s.aprobada_despues_del_limite, ev.datos.fecha_hora)
            self.ec.guardar(ec)
        detalle = ("Pagar y verificar antes de confirmar el reemplazo." if o.plazo is None
                   else "Se liquida con el saldo general del contrato original.")
        return Resultado.ok("Importe integrado al saldo general. " + detalle, obligacion_id=o.obligacion_id)

    def aplicar_cierre_sin_realizar(self, origen_id: str, estado_cuenta_id: str, evento_id: str, fecha_cierre: datetime) -> None:
        """Reacción única para SE-012 (hallazgo H-02)."""
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")             # solo lectura
        ec = _existente(self.ec.obtener_por_id(estado_cuenta_id), "El estado de cuenta")
        # `origen_id` no tiene clave foránea (es polimórfico: cambio, servicio adicional o sustitución): la existencia de la
        # solicitud de origen se comprueba aquí, con los puertos de repositorio, antes de guardar nada (D-01).
        if not any(repo.obtener_por_id(origen_id) is not None for repo in (self.cambios, self.adicionales, self.sustituciones)):
            raise ErrorDominio("La solicitud de origen del cierre no existe.")
        with transaccion(self.uow, ec):
            ec.aplicar_cierre_sin_realizar(origen_id, fecha_cierre, ev.cancelado, lambda: nuevo_id("DV"))
            self.ec.guardar(ec)

    def registrar_y_ejecutar_devolucion(self, estado_cuenta_id: str, devolucion_id: str, ahora: datetime,
                                        comprobante: Optional[str] = None) -> Resultado:
        """CA-098: Administración efectúa la devolución y registra su comprobante. Con `comprobante` se registra el que entrega
        Administración (la devolución real se hace fuera del sistema); sin él se usa el ejecutor de devoluciones, que hoy es una
        simulación (no hay una pasarela de pagos especificada)."""
        ec = _existente(self.ec.obtener_por_id(estado_cuenta_id), "El estado de cuenta")
        d = _existente(next((x for x in ec.devoluciones if x.devolucion_id == devolucion_id), None), "La devolución")
        if comprobante is None:
            comprobante = self.ejecutor.ejecutar(devolucion_id, d.importe, referencia_idempotente=devolucion_id)  # fuera de la transacción
        with transaccion(self.uow, ec):
            ec.registrar_devolucion_efectuada(devolucion_id, ahora, comprobante); self.ec.guardar(ec)
        # H-09 (SE-012): se informa si la devolución quedó dentro de los cinco días hábiles; una devolución tardía igualmente
        # se registra (el importe se debe), y la consecuencia de incumplir el plazo no está definida en las fuentes.
        datos = dict(comprobante=comprobante, fecha_limite=d.fecha_limite.isoformat(), en_plazo=d.en_plazo)
        if d.en_plazo is False:
            return Resultado.ok("Devolución efectuada fuera del plazo de cinco días hábiles (SE-012).", **datos)
        return Resultado.ok("Devolución efectuada.", **datos)


# ======================================================================= CU-03
@con_rechazos_de_negocio
class GestionCierreEventoService:
    def __init__(self, eventos: IEventoRepository, contratos: IContratoRepository, estados_cuenta: IEstadoCuentaRepository,
                 uow: IUnitOfWork, notificador: INotificadorParticipantes):
        self.eventos, self.contratos, self.ec, self.uow, self.notificador = eventos, contratos, estados_cuenta, uow, notificador

    def gestionar_cancelacion_solicitada(self, evento_id: str, motivo: str, ahora: datetime) -> Resultado:
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")
        confirmada = any(c.estado == EstadoContrato.CONTRATACION_CONFIRMADA for c in self.contratos.listar_por_evento_id(evento_id))
        try:
            with transaccion(self.uow, ev):
                cancelado = ev.solicitar_cancelacion(motivo, ahora, confirmada); self.eventos.guardar(ev)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        if not cancelado:
            # El rechazo no tiene Domain Event: este es su único aviso. La cancelación la notifica solo la reacción.
            self.notificador.notificar(["Cliente"], "Cancelación no procedente", "El evento ya inició (CA-088).")
            return Resultado.rechazo("Solicitud rechazada: el evento ya inició; continúa En ejecución.")
        return Resultado.ok("Evento cancelado.")

    def registrar_revision_administrativa_cancelacion(self, evento_id: str, resultado: str, fecha: datetime) -> Resultado:
        """Administración consulta el contrato y los estados de cuenta del evento (solo lectura) y registra
        el resultado con los pagos realizados, el saldo pendiente y la constancia de no reembolso (CA-089 a CA-091).
        La cancelación no anula el saldo pendiente: queda registrado como obligación y su exigibilidad se rige por el
        contrato; no se crea un proceso de cobro posterior (BN-008)."""
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")
        contratos = self.contratos.listar_por_evento_id(evento_id)
        estados = self.ec.listar_por_evento_id(evento_id)
        pagos = sum((x.pagos_realizados().cantidad for x in estados), Decimal(0))
        saldo = sum((x.saldo_pendiente_contrato().cantidad for x in estados), Decimal(0))
        politica = any(c.politica.incluida for c in contratos)
        revision = RevisionAdministrativa(resultado, Importe(pagos), Importe(saldo), politica, True, fecha)
        with transaccion(self.uow, ev):
            ev.registrar_revision_administrativa(revision); self.eventos.guardar(ev)
        self.notificador.notificar(["Coordinador"], "Revisión de cancelación",
                                   f"Pagos realizados: {pagos}; saldo pendiente: {saldo}; no corresponde reembolso.")
        return Resultado.ok("Revisión registrada con constancia de no reembolso.", pagos_realizados=str(pagos), saldo_pendiente=str(saldo))

    def resolver_regularizacion_saldo_vencido(self, estado_cuenta_id: str, revisado_en: datetime) -> Resultado:
        """Administración registra el resultado en EstadoCuenta; no modifica Evento ni cancela."""
        ec = _existente(self.ec.obtener_por_id(estado_cuenta_id), "El estado de cuenta")
        try:
            with transaccion(self.uow, ec):
                ok = ec.resolver_regularizacion(revisado_en); self.ec.guardar(ec)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Saldo regularizado." if ok else "Plazo de regularización vencido.", regularizado=ok)

    def registrar_cancelacion_por_falta_de_regularizacion(self, evento_id: str, motivo: str, coordinador: str,
                                                          ahora: datetime) -> Resultado:
        """Caso de uso del Coordinador, después del aviso de Administración (BN-005, BN-008, CA-027).
        No es una reacción automática. La comunicación a los involucrados la hace la reacción a EventoCancelado."""
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")
        verificado = any(ec.no_regularizado_verificado for ec in self.ec.listar_por_evento_id(evento_id))   # solo lectura
        try:
            with transaccion(self.uow, ev):
                cambiado = ev.cancelar_por_falta_de_regularizacion(motivo, coordinador, ahora, verificado)
                self.eventos.guardar(ev)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Cancelación registrada por el Coordinador." if cambiado else "El evento ya estaba cancelado por esta causa.")

    def procesar_inicio_evento(self, evento_id: str, ahora: datetime) -> Resultado:
        """Llegada de T (C-01, CA-109, CA-110): un Evento En organización inicia; uno que sigue En gestión se cierra sin contratación.
        Lo invocan la operación explícita (POST /eventos/{id}/inicio) y el proceso periódico del trabajador."""
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")
        if ev.estado == EstadoEvento.EN_GESTION and ahora >= ev.datos.fecha_hora:
            return self._cerrar_por_llegada_de_t(ev, ahora)
        try:
            with transaccion(self.uow, ev):
                ev.iniciar(ahora); self.eventos.guardar(ev)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Evento En ejecución.")

    def _cerrar_por_llegada_de_t(self, ev: Evento, ahora: datetime) -> Resultado:
        """C-01 / CA-110: llegó T con el Evento En gestión. Se cierra el contrato abierto (En preparación o Firmado): su evento
        ProcesoContratacionCerrado cierra el Evento (nunca Cancelado) y devuelve el anticipo recibido (decisión A) en las reacciones. Sin
        contrato abierto se cierra el Evento directamente. Con la contratación ya confirmada (reacción pendiente) no se cierra nada."""
        contratos = self.contratos.listar_por_evento_id(ev.id)
        if any(c.estado == EstadoContrato.CONTRATACION_CONFIRMADA for c in contratos):
            return Resultado.ok("La contratación está confirmada: el Evento pasa a En organización por su reacción.")
        abiertos = [c for c in contratos if c.estado in (EstadoContrato.EN_PREPARACION, EstadoContrato.FIRMADO)]
        for c in abiertos:
            with transaccion(self.uow, c):
                c.cerrar_por_inicio(ahora); self.contratos.guardar(c)
        if not abiertos:
            with transaccion(self.uow, ev):
                ev.cerrar_sin_contratacion(); self.eventos.guardar(ev)
        self.notificador.notificar(["Cliente", "Coordinador", "Administración"], "Evento cerrado sin contratación",
                                   f"Evento {ev.id}: llegó la fecha y hora programadas sin contratación confirmada (CA-110); el anticipo recibido, "
                                   f"si existe, se devuelve.")
        return Resultado.ok("Evento Cerrado sin contratación: llegó la fecha y hora programadas sin contratación confirmada.")

    def procesar_eventos_vencidos(self, ahora: datetime) -> Resultado:
        """Proceso periódico (trabajador): aplica la llegada de T a cada Evento En gestión o En organización cuya fecha ya llegó.
        Un evento por transacción; un fallo en uno se registra y no impide los demás ni el ciclo siguiente. Idempotente: los eventos
        ya procesados dejan de aparecer en la consulta."""
        iniciados = cerrados = errores = 0
        for ev in self.eventos.listar_con_fecha_vencida(ahora):
            try:
                estado_previo = ev.estado
                r = self.procesar_inicio_evento(ev.id, ahora)
            except Exception:                                   # falla técnica: se reintenta en el ciclo siguiente
                errores += 1
                logging.getLogger("eventosnova.servicios").exception("Falló el procesamiento de la llegada de T del evento %s", ev.id)
                continue
            if not r.exito:
                errores += 1
                logging.getLogger("eventosnova.servicios").warning("Evento %s no procesado: %s", ev.id, r.mensaje)
            elif estado_previo == EstadoEvento.EN_ORGANIZACION:
                iniciados += 1
            elif "Cerrado sin contratación" in r.mensaje:
                cerrados += 1
        return Resultado.ok("Llegada de T procesada.", iniciados=iniciados, cerrados=cerrados, errores=errores)

    def finalizar_evento(self, evento_id: str, fecha: datetime) -> Resultado:
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")
        try:
            with transaccion(self.uow, ev):
                ev.finalizar(fecha); self.eventos.guardar(ev)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Evento Finalizado.")


# ======================================================================= CU-04
@con_rechazos_de_negocio
class GestionCambiosEventoService:
    def __init__(self, cambios: ISolicitudCambioRepository, eventos: IEventoRepository, contratos: IContratoRepository,
                 estados_cuenta: IEstadoCuentaRepository, uow: IUnitOfWork, disponibilidad: IConsultaDisponibilidadProveedor,
                 notificador: INotificadorParticipantes):
        self.cambios, self.eventos, self.contratos, self.ec = cambios, eventos, contratos, estados_cuenta
        self.uow, self.disponibilidad, self.notificador = uow, disponibilidad, notificador
        self.regularizacion, self.impacto = EvaluarRegularizacionDeSolicitudes(), EvaluarImpactoCambio()

    def registrar_solicitud_cambio(self, evento_id: str, contrato_id: str, descripcion: str,
                                   tarifa_vigente: Importe, ahora: datetime, datos_propuestos: Optional[DatosEvento] = None,
                                   condiciones_propuestas: Optional[dict] = None) -> Resultado:
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")                           # solo lectura
        _exigir_evento_del_contrato(self.contratos, contrato_id, evento_id)                           # E-2
        # H-08 (GL-032, CA-039): el inicio se determina por la fecha y hora programadas, aunque no se haya registrado.
        if ev.estado.value != "En organización" or ev.iniciado_en(ahora):
            return Resultado.rechazo("El cambio solo procede después de contratar y antes del inicio (CA-039).")
        ec = _estado_cuenta_del_contrato(self.ec, contrato_id)
        s = SolicitudCambio(nuevo_id_libre("SC", self.cambios), evento_id, contrato_id, ec.id, descripcion,
                            AnticipacionSolicitud(ahora, ev.datos.fecha_hora), TarifaCargoTardio(tarifa_vigente),
                            datos_propuestos, condiciones_propuestas)
        d = self.regularizacion.evaluar(_saldo(self.ec, contrato_id, ahora), ev.cancelado, s.condicion_temporal(ev.iniciado_en(ahora)))
        with transaccion(self.uow, s):
            s.aplicar_decision_regularizacion(d, ahora, EstadoSolicitudCambio.NO_PROCEDENTE)
            self.cambios.guardar(s)
        if d.detener_por_saldo:
            self.notificador.notificar(["Cliente"], "Solicitud detenida", "Debe regularizar el saldo vencido y los cargos moratorios.")
        return Resultado.ok(f"Solicitud {s.estado.value}.", solicitud_id=s.id, estado=s.estado.value)

    def retomar_solicitud_cambio(self, solicitud_id: str, ahora: datetime) -> None:
        s = self.cambios.obtener_por_id(solicitud_id)
        ev = self.eventos.obtener_por_id(s.evento_id)
        d = self.regularizacion.evaluar(_saldo(self.ec, s.contrato_id, ahora), ev.cancelado, s.condicion_temporal(ev.iniciado_en(ahora)))
        with transaccion(self.uow, s):
            s.aplicar_decision_regularizacion(d, ahora, EstadoSolicitudCambio.NO_PROCEDENTE); self.cambios.guardar(s)

    def evaluar_viabilidad_cambio(self, solicitud_id: str, resultado: ResultadoViabilidad,
                                  costo_adicional_proveedor: Optional[Importe], ahora: datetime) -> Resultado:
        """La aplicación recibe la respuesta de los proveedores (viabilidad y costo); EvaluarImpactoCambio compara la
        configuración vigente del Evento con la modificación propuesta (CA-038, CA-060, CA-063)."""
        s = _existente(self.cambios.obtener_por_id(solicitud_id), "La solicitud de cambio")
        ev = self.eventos.obtener_por_id(s.evento_id)                         # solo lectura
        vigente = ev.configuracion_vigente()
        impacto = self.impacto.evaluar(vigente, s.configuracion_propuesta(vigente, costo_adicional_proveedor))
        try:
            with transaccion(self.uow, s):
                s.registrar_viabilidad(resultado, impacto, ahora, costo_adicional_proveedor); self.cambios.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Solicitud {s.estado.value}.", estado=s.estado.value)

    def registrar_decision_cliente_cambio(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = _existente(self.cambios.obtener_por_id(solicitud_id), "La solicitud de cambio")
        try:
            with transaccion(self.uow, s):
                s.registrar_decision_cliente(decision); self.cambios.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_autorizacion_administracion_cambio(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = _existente(self.cambios.obtener_por_id(solicitud_id), "La solicitud de cambio")
        try:
            with transaccion(self.uow, s):
                s.registrar_autorizacion(decision); self.cambios.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        if not decision.aprobada:
            self.notificador.notificar(["Cliente"], "Cambio no autorizado", decision.motivo)
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_anexo_cambio(self, solicitud_id: str, descripcion: str, ahora: datetime) -> Resultado:
        """Guarda el anexo en Contrato. La asociación de anexoId ocurre en la reacción a AnexoContratoRegistrado."""
        s = _existente(self.cambios.obtener_por_id(solicitud_id), "La solicitud de cambio")                         # solo lectura
        if not s.puede_registrar_anexo():
            return Resultado.rechazo("La solicitud no está Pendiente de formalización o ya tiene anexo.")
        c = self.contratos.obtener_por_id(s.contrato_id)
        try:
            with transaccion(self.uow, c):
                a = c.registrar_anexo(nuevo_id("AX"), TipoSolicitud.CAMBIO, s.id, descripcion, ahora); self.contratos.guardar(c)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Anexo registrado en el contrato.", anexo_id=a.anexo_id)

    def confirmar_cambio(self, solicitud_id: str, ahora: datetime) -> Resultado:
        """Confirma solo SolicitudCambio. La configuración de Evento cambia en la reacción a CambioConfirmado."""
        s = _existente(self.cambios.obtener_por_id(solicitud_id), "La solicitud de cambio")
        ev = self.eventos.obtener_por_id(s.evento_id)                         # solo lectura
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)                       # solo lectura
        with transaccion(self.uow, s):
            faltan = s.confirmar(ec.solicitud_liquidada(s.id), ev.iniciado_en(ahora), ahora, ev.cancelado)   # todas las obligaciones del cambio
            self.cambios.guardar(s)
        if faltan:
            return Resultado.rechazo("El cambio no puede confirmarse.", faltan)
        return Resultado.ok("Cambio confirmado.")

    def cerrar_cambio_por_falta_de_pago(self, solicitud_id: str, ahora: datetime) -> Resultado:
        s = _existente(self.cambios.obtener_por_id(solicitud_id), "La solicitud de cambio")
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)                       # solo lectura
        if not s.obligacion_pago_id or not ec.solicitud_vencida_sin_pago(s.id, ahora):
            return Resultado.rechazo("El plazo de pago sigue vigente, el pago está verificado o hay un pago efectuado "
                                     "dentro del plazo pendiente de verificación.")
        with transaccion(self.uow, s):
            s.cerrar_por_falta_de_pago(ahora); self.cambios.guardar(s)
        self.notificador.notificar(["Cliente"], "Solicitud cerrada por falta de pago", "Se conserva la última configuración confirmada.")
        return Resultado.ok("Solicitud cerrada por falta de pago.")

    def cerrar_cambio_por_inicio_evento(self, solicitud_id: str, ahora: datetime) -> None:
        s = self.cambios.obtener_por_id(solicitud_id)
        with transaccion(self.uow, s):
            s.cerrar_por_inicio_evento(ahora); self.cambios.guardar(s)


# ======================================================================= CU-05
@con_rechazos_de_negocio
class GestionServiciosAdicionalesService:
    def __init__(self, adicionales: ISolicitudServicioAdicionalRepository, eventos: IEventoRepository,
                 contratos: IContratoRepository, estados_cuenta: IEstadoCuentaRepository, uow: IUnitOfWork,
                 disponibilidad: IConsultaDisponibilidadProveedor, notificador: INotificadorParticipantes):
        self.adicionales, self.eventos, self.contratos, self.ec = adicionales, eventos, contratos, estados_cuenta
        self.uow, self.disponibilidad, self.notificador = uow, disponibilidad, notificador
        self.regularizacion = EvaluarRegularizacionDeSolicitudes()

    def _evaluar(self, s: SolicitudServicioAdicional, ev: Evento, ahora: datetime):
        return self.regularizacion.evaluar(_saldo(self.ec, s.contrato_id, ahora), ev.cancelado, s.condicion_temporal(ahora, ev.iniciado_en(ahora)))

    def registrar_solicitud_servicio_adicional(self, evento_id: str, contrato_id: str, servicio: str, ahora: datetime) -> Resultado:
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")
        _exigir_evento_del_contrato(self.contratos, contrato_id, evento_id)                           # E-2
        # D-1 (C-14, GL-015, CA-101): un servicio adicional solo puede registrarse con la contratación confirmada. Se rechaza
        # antes de crear nada y sin evaluar el plazo mínimo ni el saldo. Con el Evento ya cancelado o iniciado el contrato sigue
        # confirmado: esos casos los resuelve la evaluación posterior (motivos propios), no este rechazo.
        contrato = self.contratos.obtener_por_id(contrato_id)
        if contrato is not None and contrato.estado != EstadoContrato.CONTRATACION_CONFIRMADA:
            self.notificador.notificar(["Cliente"], "Servicio adicional no registrado",
                                       "Un servicio adicional solo puede registrarse con la contratación confirmada (CA-101).")
            return Resultado.rechazo("Un servicio adicional solo puede registrarse con la contratación confirmada (CA-101).")
        ec = _estado_cuenta_del_contrato(self.ec, contrato_id)
        s = SolicitudServicioAdicional(nuevo_id_libre("SA", self.adicionales), evento_id, contrato_id, ec.id, servicio,
                                       AnticipacionSolicitud(ahora, ev.datos.fecha_hora))
        # N6 (SE-004, O-01): la solicitud ya está registrada; se verifica en orden el Evento, el plazo y, al final, el
        # saldo. Cada verificación se ejecuta solo si las anteriores se cumplieron y se conserva el primer motivo.
        d = self.regularizacion.evaluar_solicitud_nueva(ev.cancelado, lambda: s.condicion_temporal(ahora, ev.iniciado_en(ahora)),
                                                        lambda: _saldo(self.ec, contrato_id, ahora))
        with transaccion(self.uow, s):
            s.aplicar_decision_regularizacion(d, ahora, EstadoSolicitudServicioAdicional.NO_PROCEDENTE); self.adicionales.guardar(s)
        return Resultado.ok(f"Solicitud {s.estado.value}.", solicitud_id=s.id, estado=s.estado.value, motivo=d.motivo)

    def retomar_solicitud_servicio_adicional(self, solicitud_id: str, ahora: datetime) -> None:
        """Se comprueban de nuevo saldo, Evento y condición temporal; con elegibilidadObtenida no se exigen otra vez 5 días."""
        s = self.adicionales.obtener_por_id(solicitud_id)
        ev = self.eventos.obtener_por_id(s.evento_id)
        with transaccion(self.uow, s):
            s.aplicar_decision_regularizacion(self._evaluar(s, ev, ahora), ahora, EstadoSolicitudServicioAdicional.NO_PROCEDENTE)
            self.adicionales.guardar(s)

    @staticmethod
    def _rechazo_por_estado_del_evento(ev: Evento, ahora: datetime) -> Optional[str]:
        """CA-073/074 (SE-004, BN-008, CA-071, GL-032): la gestión de una solicitud en trámite no continúa con el Evento
        cancelado o ya iniciado. Se verifica antes que el plazo y la disponibilidad, como en el registro (SE-004), y se
        rechaza sin modificar la solicitud: su cierre con el motivo que corresponde lo hacen las reacciones existentes a
        EventoCancelado (BN-008) y a EventoIniciado (CA-071)."""
        if ev.cancelado:
            return "El Evento está cancelado: la solicitud no continúa su gestión y se cierra con el motivo «Evento cancelado» (BN-008)."
        if ev.iniciado_en(ahora):
            return "El Evento ya inició: la solicitud no continúa su gestión y se cierra por inicio del evento (CA-071)."
        return None

    def _buscar_proveedor_servicio_adicional(self, s: SolicitudServicioAdicional, ev: Evento,
                                             proveedores_actuales: List[str]):
        """CA-073, CA-074, SE-004: consulta en dos etapas con el puerto existente.
        Proveedores actuales = los que ya participan en el evento: los indicados por el Coordinador y los asignados a los
        servicios del Evento, sin repetir y en ese orden.
        1) Si hay actuales, se consulta solo a ellos (lista no vacía) y se consideran solo sus respuestas; si alguno está
           disponible se elige el primero y no se consultan alternativas.
        2) Si ninguno está disponible, o no hay actuales, se hace la consulta general (lista vacía, la misma convención
           que usan la sustitución y la asignación de proveedores) y se excluye a los actuales ya considerados.
        Devuelve la opción elegida o None. El costo y las condiciones (CA-075) y el plazo los sigue validando
        SolicitudServicioAdicional.registrar_disponibilidad, sin cambios."""
        actuales = list(dict.fromkeys(list(proveedores_actuales)
                                      + [sc.proveedor_id for sc in ev.servicios.values() if sc.proveedor_id]))
        if actuales:
            respuestas = self.disponibilidad.consultar(s.servicio, s.anticipacion.fecha_evento, list(actuales))
            elegida = next((o for o in respuestas if o.proveedor_id in actuales and o.disponible), None)
            if elegida is not None:
                return elegida
        alternativas = self.disponibilidad.consultar(s.servicio, s.anticipacion.fecha_evento, [])
        return next((o for o in alternativas if o.proveedor_id not in actuales and o.disponible), None)

    def evaluar_disponibilidad_servicio_adicional(self, solicitud_id: str, proveedores_actuales: List[str], ahora: datetime) -> Resultado:
        s = _existente(self.adicionales.obtener_por_id(solicitud_id), "La solicitud de servicio adicional")
        ev = _existente(self.eventos.obtener_por_id(s.evento_id), "El evento")                       # solo lectura
        rechazo = self._rechazo_por_estado_del_evento(ev, ahora)
        if rechazo:
            return Resultado.rechazo(rechazo)
        elegida = self._buscar_proveedor_servicio_adicional(s, ev, proveedores_actuales)    # fuera de la transacción
        from domain.valores import DisponibilidadProveedor
        try:
            with transaccion(self.uow, s):
                s.registrar_disponibilidad(elegida or DisponibilidadProveedor("", False), ahora); self.adicionales.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Solicitud {s.estado.value}.", estado=s.estado.value)

    def registrar_decision_espera_cliente(self, solicitud_id: str, acepta_esperar: bool, ahora: datetime) -> Resultado:
        s = _existente(self.adicionales.obtener_por_id(solicitud_id), "La solicitud de servicio adicional")
        rechazo = self._rechazo_por_estado_del_evento(
            _existente(self.eventos.obtener_por_id(s.evento_id), "El evento"), ahora)            # CA-077, CA-071, BN-008
        if rechazo:
            return Resultado.rechazo(rechazo)
        with transaccion(self.uow, s):
            s.registrar_respuesta_espera(acepta_esperar, ahora); self.adicionales.guardar(s)
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_aprobacion_cliente_servicio_adicional(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = _existente(self.adicionales.obtener_por_id(solicitud_id), "La solicitud de servicio adicional")
        with transaccion(self.uow, s):
            s.registrar_decision_cliente(decision); self.adicionales.guardar(s)
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_autorizacion_administracion_servicio_adicional(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = _existente(self.adicionales.obtener_por_id(solicitud_id), "La solicitud de servicio adicional")
        with transaccion(self.uow, s):
            s.registrar_autorizacion(decision); self.adicionales.guardar(s)
        if not decision.aprobada:
            self.notificador.notificar(["Cliente"], "Servicio adicional no autorizado", decision.motivo)
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_anexo_servicio_adicional(self, solicitud_id: str, descripcion: str, ahora: datetime) -> Resultado:
        s = _existente(self.adicionales.obtener_por_id(solicitud_id), "La solicitud de servicio adicional")                     # solo lectura
        if not s.puede_registrar_anexo():
            return Resultado.rechazo("La solicitud no está Autorizada o ya tiene anexo.")
        c = self.contratos.obtener_por_id(s.contrato_id)
        with transaccion(self.uow, c):
            a = c.registrar_anexo(nuevo_id("AX"), TipoSolicitud.SERVICIO_ADICIONAL, s.id, descripcion, ahora); self.contratos.guardar(c)
        return Resultado.ok("Anexo registrado en el contrato.", anexo_id=a.anexo_id)

    def confirmar_servicio_adicional(self, solicitud_id: str, ahora: datetime) -> Resultado:
        s = _existente(self.adicionales.obtener_por_id(solicitud_id), "La solicitud de servicio adicional")
        ev = self.eventos.obtener_por_id(s.evento_id)
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        with transaccion(self.uow, s):
            faltan = s.confirmar(ec.obligacion_liquidada(s.obligacion_pago_id), ev.iniciado_en(ahora), ahora, ev.cancelado)
            self.adicionales.guardar(s)
        return Resultado.rechazo("El servicio adicional no puede confirmarse.", faltan) if faltan else Resultado.ok("Servicio adicional confirmado.")

    def cerrar_servicio_adicional_por_falta_de_pago(self, solicitud_id: str, ahora: datetime) -> Resultado:
        s = _existente(self.adicionales.obtener_por_id(solicitud_id), "La solicitud de servicio adicional")
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        if not s.obligacion_pago_id or not ec.obligacion_vencida_sin_pago(s.obligacion_pago_id, ahora):
            return Resultado.rechazo("El plazo de pago sigue vigente, el pago está verificado o hay un pago efectuado "
                                     "dentro del plazo pendiente de verificación.")
        with transaccion(self.uow, s):
            s.cerrar_por_falta_de_pago(ahora); self.adicionales.guardar(s)
        self.notificador.notificar(["Cliente"], "Servicio adicional cerrado por falta de pago", "El servicio no se realizará.")
        return Resultado.ok("Solicitud cerrada por falta de pago.")

    def cerrar_servicio_adicional_por_inicio_evento(self, solicitud_id: str, ahora: datetime) -> None:
        s = self.adicionales.obtener_por_id(solicitud_id)
        with transaccion(self.uow, s):
            s.cerrar_por_inicio_evento(ahora); self.adicionales.guardar(s)


# ======================================================================= US-021
@con_rechazos_de_negocio
class GestionSustitucionProveedorService:
    def __init__(self, sustituciones: ISustitucionProveedorRepository, eventos: IEventoRepository,
                 contratos: IContratoRepository, estados_cuenta: IEstadoCuentaRepository, uow: IUnitOfWork,
                 disponibilidad: IConsultaDisponibilidadProveedor, notificador: INotificadorParticipantes):
        self.sustituciones, self.eventos, self.contratos, self.ec = sustituciones, eventos, contratos, estados_cuenta
        self.uow, self.disponibilidad, self.notificador = uow, disponibilidad, notificador
        self.impacto = EvaluarImpactoCambio()

    def registrar_proveedor_no_disponible(self, evento_id: str, servicio_contratado_id: str, contrato_id: str, ahora: datetime) -> Resultado:
        """Con el Evento cancelado no se inicia una nueva sustitución: las que ya estaban en trámite se cierran en la
        reacción a la cancelación y una nueva quedaría pendiente sin cierre posible. H-21 (BPMN SP-05, Bitácora, Informe):
        el aviso del proveedor recibido con el Evento ya iniciado o finalizado queda fuera del alcance del sistema; una
        sustitución que ya estaba pendiente al iniciar el Evento se cierra en la reacción al inicio."""
        ev = _existente(self.eventos.obtener_por_id(evento_id), "El evento")                           # solo lectura
        _exigir_evento_del_contrato(self.contratos, contrato_id, evento_id)                           # E-2
        if ev.cancelado:
            return Resultado.rechazo("El evento está cancelado: no se inician nuevas sustituciones de proveedor.")
        if ev.iniciado_en(ahora):                                          # H-08: según la fecha y hora programadas (GL-032)
            return Resultado.rechazo("El aviso del proveedor recibido después del inicio del Evento queda fuera del alcance "
                                     "del sistema (SP-05): no se inicia la sustitución.")
        if ev.estado != EstadoEvento.EN_ORGANIZACION:
            return Resultado.rechazo("El evento no tiene la contratación confirmada: no hay servicios contratados que sustituir.")
        sc = _existente(ev.servicios.get(servicio_contratado_id), "El servicio contratado")
        ec = _estado_cuenta_del_contrato(self.ec, contrato_id)
        s = SustitucionProveedor(nuevo_id_libre("SP", self.sustituciones), evento_id, servicio_contratado_id, sc.proveedor_id, contrato_id, ec.id, ahora)
        with transaccion(self.uow, s):
            self.sustituciones.guardar(s)
        return Resultado.ok("Sustitución En búsqueda de alternativa.", sustitucion_id=s.id)

    def buscar_alternativa_sustitucion(self, sustitucion_id: str, condiciones_alternativa: CondicionesServicio,
                                       costo_adicional: Optional[Importe], ahora: datetime) -> Resultado:
        s = _existente(self.sustituciones.obtener_por_id(sustitucion_id), "La sustitución de proveedor")
        ev = self.eventos.obtener_por_id(s.evento_id)
        sc = ev.servicios[s.servicio_contratado_id]
        opciones = [o for o in self.disponibilidad.consultar(sc.servicio, ev.datos.fecha_hora, []) if o.disponible
                    and o.proveedor_id != s.proveedor_original_id]
        if not opciones:
            self.notificador.notificar(["Cliente"], "Sin alternativa disponible", "La sustitución sigue pendiente (CA-048).")
            return Resultado.rechazo("No hay alternativa disponible; se continúa buscando.")
        vigente = ev.configuracion_vigente()
        condiciones = dict(vigente.condiciones); condiciones[s.servicio_contratado_id] = condiciones_alternativa
        propuesta = ConfiguracionComparable(vigente.datos, frozenset(condiciones.items()),
                                            costo_adicional or vigente.costo_adicional)
        alt = AlternativaPropuesta(opciones[0].proveedor_id, opciones[0], self.impacto.evaluar(vigente, propuesta))
        with transaccion(self.uow, s):
            s.proponer_alternativa(alt, costo_adicional, ahora); self.sustituciones.guardar(s)
        return Resultado.ok(f"Sustitución {s.estado.value}.")

    def registrar_decision_cliente_sustitucion(self, sustitucion_id: str, decision: Decision) -> Resultado:
        s = _existente(self.sustituciones.obtener_por_id(sustitucion_id), "La sustitución de proveedor")
        with transaccion(self.uow, s):
            s.registrar_decision_cliente(decision); self.sustituciones.guardar(s)
        return Resultado.ok(f"Sustitución {s.estado.value}.")

    def registrar_autorizacion_administracion_sustitucion(self, sustitucion_id: str, decision: Decision) -> Resultado:
        s = _existente(self.sustituciones.obtener_por_id(sustitucion_id), "La sustitución de proveedor")
        ev = self.eventos.obtener_por_id(s.evento_id)                         # solo lectura: fecha del evento
        with transaccion(self.uow, s):
            s.registrar_autorizacion(decision, ev.datos.fecha_hora); self.sustituciones.guardar(s)
        if not decision.aprobada:
            self.notificador.notificar(["Cliente"], "Sustitución no autorizada", "Se continúa buscando otra alternativa (CA-050).")
        return Resultado.ok(f"Sustitución {s.estado.value}.")

    def registrar_anexo_sustitucion_proveedor(self, sustitucion_id: str, descripcion: str, ahora: datetime) -> Resultado:
        s = _existente(self.sustituciones.obtener_por_id(sustitucion_id), "La sustitución de proveedor")
        if not s.puede_registrar_anexo():
            return Resultado.rechazo("La sustitución no está Pendiente de formalización o ya tiene anexo.")
        c = self.contratos.obtener_por_id(s.contrato_id)
        with transaccion(self.uow, c):
            a = c.registrar_anexo(nuevo_id("AX"), TipoSolicitud.SUSTITUCION_PROVEEDOR, s.id, descripcion, ahora); self.contratos.guardar(c)
        return Resultado.ok("Anexo registrado en el contrato.", anexo_id=a.anexo_id)

    def confirmar_sustitucion_proveedor(self, sustitucion_id: str, ahora: datetime) -> Resultado:
        s = _existente(self.sustituciones.obtener_por_id(sustitucion_id), "La sustitución de proveedor")
        ev = self.eventos.obtener_por_id(s.evento_id)
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        ob = next((o for o in ec.obligaciones.values() if o.origen_id == s.id), None)
        with transaccion(self.uow, s):
            faltan = s.confirmar(bool(ob) and ec.obligacion_liquidada(ob.obligacion_id), ev.iniciado_en(ahora), ahora, ev.cancelado)
            self.sustituciones.guardar(s)
        return Resultado.rechazo("La sustitución no puede confirmarse.", faltan) if faltan else Resultado.ok("Sustitución confirmada.")

    def cerrar_sustitucion_por_inicio_evento(self, sustitucion_id: str, ahora: datetime) -> None:
        s = self.sustituciones.obtener_por_id(sustitucion_id)
        with transaccion(self.uow, s):
            s.cerrar_por_inicio_evento(ahora); self.sustituciones.guardar(s)


# ======================================================================= US-013 a US-016
@con_rechazos_de_negocio
class GestionProveedoresServicioService:
    """Asignación inicial de proveedores a los servicios contratados y respuesta del proveedor (E3G, H-01 y H-02).
    La sustitución de un proveedor que no puede prestar el servicio sigue siendo GestionSustitucionProveedorService."""

    def __init__(self, eventos: IEventoRepository, uow: IUnitOfWork, disponibilidad: IConsultaDisponibilidadProveedor,
                 notificador: INotificadorParticipantes, catalogo: Optional[IProveedorRepository] = None):
        self.eventos, self.uow, self.disponibilidad, self.notificador = eventos, uow, disponibilidad, notificador
        self.catalogo = catalogo        # solo para explicar con precisión por qué se rechaza una asignación; no decide la disponibilidad

    def _evento_y_servicio(self, evento_id: str, servicio_contratado_id: str):
        ev = self.eventos.obtener_por_id(evento_id)                           # solo lectura
        if ev is None:
            raise ErrorDominio("El evento no existe.")
        sc = ev.servicios.get(servicio_contratado_id)
        if sc is None:
            raise ErrorDominio("El servicio contratado no existe en el Evento.")
        return ev, sc

    def _disponibles(self, ev: Evento, servicio: str) -> List:
        return self.disponibilidad.consultar(servicio, ev.datos.fecha_hora, [])   # fuera de la transacción

    def _motivo_de_rechazo(self, proveedor_id: str, servicio: str, opciones: List) -> str:
        """Explica la causa real: proveedor no registrado en el catálogo, o registrado pero que no ofrece el servicio. Si una fuente de
        disponibilidad lo conoce y lo marca no disponible, o no hay catálogo, se conserva el mensaje general."""
        general = "El proveedor no figura disponible para este servicio y fecha (CA-029, CA-031)."
        if self.catalogo is None or proveedor_id in {o.proveedor_id for o in opciones}:
            return general
        p = self.catalogo.obtener_por_id(proveedor_id)
        if p is None:
            return "El proveedor indicado no está registrado en el catálogo de proveedores (CA-029, CA-031)."
        if not p.ofrece(servicio):
            return f"El proveedor «{p.nombre}» no ofrece el servicio «{servicio}» (CA-029, CA-031)."
        return general

    def consultar_disponibilidad_servicio(self, evento_id: str, servicio_contratado_id: str) -> Resultado:
        """CA-029, CA-030: disponibilidad de los proveedores para el servicio y la fecha del Evento. Solo lectura."""
        ev, sc = self._evento_y_servicio(evento_id, servicio_contratado_id)
        opciones = self._disponibles(ev, sc.servicio)
        return Resultado.ok("Disponibilidad consultada.", servicio=sc.servicio,
                            disponibles=[o.proveedor_id for o in opciones if o.disponible],
                            no_disponibles=[o.proveedor_id for o in opciones if not o.disponible])

    def asignar_proveedor(self, evento_id: str, servicio_contratado_id: str, proveedor_id: str) -> Resultado:
        """CA-031, CA-032: solo un proveedor que figura disponible para el servicio y la fecha, con el Evento En
        organización (BN-009). El servicio queda pendiente de la confirmación del proveedor."""
        ev, sc = self._evento_y_servicio(evento_id, servicio_contratado_id)
        ev._admite_gestion_de_proveedores()                     # BN-009: primero el estado del Evento (mensaje propio si no procede)
        opciones = self._disponibles(ev, sc.servicio)
        if proveedor_id not in {o.proveedor_id for o in opciones if o.disponible}:
            return Resultado.rechazo(self._motivo_de_rechazo(proveedor_id, sc.servicio, opciones))
        with transaccion(self.uow, ev):
            ev.asignar_proveedor(servicio_contratado_id, proveedor_id)
            self.eventos.guardar(ev)
        return Resultado.ok("Proveedor asignado; pendiente de su confirmación.",
                            estado=EstadoServicioContratado.PENDIENTE_CONFIRMACION.value)

    def registrar_respuesta_proveedor(self, evento_id: str, servicio_contratado_id: str, proveedor_id: str,
                                      disponible: bool) -> Resultado:
        """CA-035, CA-036: el proveedor asignado confirma o niega su disponibilidad. Si la niega, se avisa al Coordinador,
        que puede iniciar la sustitución con el caso de uso existente (SE-001, SP-05)."""
        ev, _ = self._evento_y_servicio(evento_id, servicio_contratado_id)
        with transaccion(self.uow, ev):
            sc = ev.registrar_respuesta_proveedor(servicio_contratado_id, proveedor_id, disponible)
            self.eventos.guardar(ev)
        if not disponible:
            self.notificador.notificar(["Coordinador"], "Proveedor no disponible",
                                       f"El proveedor {proveedor_id} no puede prestar el servicio {sc.servicio}: "
                                       "registrar la sustitución y buscar una alternativa (CA-036).")
        return Resultado.ok("Disponibilidad confirmada." if disponible else "Indisponibilidad registrada.",
                            estado=sc.estado.value)


def _datos_proveedor(p: Proveedor) -> dict:
    return {"proveedorId": p.proveedor_id, "nombre": p.nombre, "servicios": list(p.servicios), "contacto": p.contacto,
            "registradoEn": p.registrado_en.isoformat()}


@con_rechazos_de_negocio
class GestionCatalogoProveedoresService:
    """Catálogo de proveedores: registrar, consultar y buscar. No cambia el estado de ningún Evento ni servicio contratado;
    la asignación a un servicio sigue siendo `GestionProveedoresServicioService.asignar_proveedor` (BN-004, BN-009)."""

    def __init__(self, proveedores: IProveedorRepository):
        self.proveedores = proveedores

    def registrar_proveedor(self, nombre: str, servicios: List[str], contacto: str, ahora: datetime) -> Resultado:
        p = Proveedor.registrar(nuevo_id("PV"), nombre, servicios or [], contacto, ahora)
        if not self.proveedores.guardar(p):
            return Resultado.rechazo(f"Ya existe un proveedor registrado con el nombre «{p.nombre}».")
        return Resultado.ok("Proveedor registrado.", **_datos_proveedor(p))

    def consultar_proveedor(self, proveedor_id: str) -> Resultado:
        p = self.proveedores.obtener_por_id(proveedor_id)
        if p is None:
            raise ErrorDominio("El proveedor no existe.")
        return Resultado.ok("Proveedor consultado.", **_datos_proveedor(p))

    def listar_proveedores(self, busqueda: str = "", servicio: str = "") -> Resultado:
        """Búsqueda por texto (identificador, nombre, contacto o servicios) y/o por servicio que ofrece. Solo lectura."""
        encontrados = [p for p in self.proveedores.listar_todos()
                       if p.coincide_con(busqueda or "") and (not servicio or p.ofrece(servicio))]
        return Resultado.ok("Proveedores consultados.", proveedores=[_datos_proveedor(p) for p in encontrados])
