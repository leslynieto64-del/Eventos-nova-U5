"""Application Services (Etapa 4). Coordinan casos de uso; las reglas viven en el dominio.
Cada método de escritura usa IUnitOfWork; los Domain Events se publican después del commit (Outbox)."""
from __future__ import annotations
import functools
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from domain.valores import (ErrorDominio, DatosEvento, ContenidoPropuesta, CondicionesContractuales, PoliticaNoReembolso,
                            Importe, Decision, AnticipacionSolicitud, TarifaCargoTardio, ResultadoViabilidad,
                            TipoSolicitud, ConceptoPago, EstadoSolicitudCambio, EstadoSolicitudServicioAdicional,
                            EstadoContrato, CondicionesServicio, sumar_dias_habiles)
from domain.propuesta import Propuesta
from domain.contrato import Contrato, EvidenciaAnticipo
from domain.evento import Evento, RevisionAdministrativa
from domain.solicitudes import SolicitudCambio, SolicitudServicioAdicional, SustitucionProveedor, AlternativaPropuesta
from domain.estado_cuenta import EstadoCuenta
from domain.servicios_dominio import (EvaluarImpactoCambio, EvaluarRegularizacionDeSolicitudes, SituacionSaldo,
                                      ConfiguracionComparable)
from .puertos import (IPropuestaRepository, IContratoRepository, IEventoRepository, ISolicitudCambioRepository,
                      ISolicitudServicioAdicionalRepository, ISustitucionProveedorRepository, IEstadoCuentaRepository,
                      IUnitOfWork, IConsultaDisponibilidadProveedor, INotificadorParticipantes, IVerificadorPagos,
                      IEjecutorDevoluciones)
from .resultados import Resultado


def nuevo_id(prefijo: str) -> str:
    return f"{prefijo}-{uuid.uuid4().hex[:8]}"


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


def _saldo(ec_repo: IEstadoCuentaRepository, contrato_id: str) -> SituacionSaldo:
    ec = ec_repo.obtener_por_contrato_id(contrato_id)
    return SituacionSaldo(bool(ec and ec.saldo_vencido_sin_regularizar))


# ======================================================================= CU-01
@con_rechazos_de_negocio
class GestionPropuestaService:
    def __init__(self, propuestas: IPropuestaRepository, eventos: IEventoRepository, uow: IUnitOfWork):
        self.propuestas, self.eventos, self.uow = propuestas, eventos, uow

    def registrar_evento(self, cliente_id: str, datos: DatosEvento, servicios: List[str]) -> Resultado:
        try:
            ev = Evento(nuevo_id("EV"), cliente_id, datos, servicios)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        with transaccion(self.uow, ev):
            self.eventos.guardar(ev)
        return Resultado.ok("Evento registrado En gestión.", evento_id=ev.id)

    def crear_propuesta(self, evento_id: str, contenido: ContenidoPropuesta, ahora: datetime) -> Resultado:
        ev = self.eventos.obtener_por_id(evento_id)               # solo lectura
        if ev is None or ev.estado.value != "En gestión":
            return Resultado.rechazo("El evento no existe o no está En gestión.")
        p = Propuesta(nuevo_id("PR"), evento_id, ev.cliente_id, contenido, ahora)
        with transaccion(self.uow, p):
            self.propuestas.guardar(p)
        return Resultado.ok("Propuesta creada.", propuesta_id=p.id)

    def generar_nueva_version(self, propuesta_id: str, contenido: ContenidoPropuesta, ahora: datetime) -> Resultado:
        p = self.propuestas.obtener_por_id(propuesta_id)
        try:
            with transaccion(self.uow, p):
                v = p.generar_nueva_version(contenido, ahora)
                self.propuestas.guardar(p)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Nueva versión vigente.", version_id=v.version_id, numero=v.numero)

    def aceptar_propuesta(self, propuesta_id: str, version_id: str, ahora: datetime) -> Resultado:
        p = self.propuestas.obtener_por_id(propuesta_id)
        try:
            with transaccion(self.uow, p):
                p.aceptar(version_id, ahora); self.propuestas.guardar(p)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Propuesta aceptada.")

    def cerrar_propuesta_no_aceptada(self, propuesta_id: str, motivo: str, ahora: datetime) -> Resultado:
        p = self.propuestas.obtener_por_id(propuesta_id)
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
                 estados_cuenta: IEstadoCuentaRepository, uow: IUnitOfWork):
        self.contratos, self.propuestas, self.estados_cuenta, self.uow = contratos, propuestas, estados_cuenta, uow

    def preparar_contrato(self, propuesta_id: str, politica_incluida: bool) -> Resultado:
        p = self.propuestas.obtener_por_id(propuesta_id)              # solo lectura
        try:
            v = p.version_aceptada()
            if any(c.estado != EstadoContrato.CERRADO_SIN_CONFIRMAR for c in self.contratos.listar_por_evento_id(p.evento_id)):
                return Resultado.rechazo("Ya existe un contrato activo para el evento.")
            c = Contrato(nuevo_id("CT"), p.evento_id, p.id, v.version_id,
                         CondicionesContractuales(v.contenido.servicios, v.contenido.costo_total, v.contenido.condiciones),
                         PoliticaNoReembolso(politica_incluida))
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        with transaccion(self.uow, c):
            self.contratos.guardar(c)
        return Resultado.ok("Contrato preparado.", contrato_id=c.id)

    def registrar_comunicacion_politica_no_reembolso(self, contrato_id: str, fecha: datetime) -> Resultado:
        c = self.contratos.obtener_por_id(contrato_id)
        with transaccion(self.uow, c):
            c.registrar_comunicacion_politica(fecha); self.contratos.guardar(c)
        return Resultado.ok("Comunicación de la política registrada.")

    def registrar_firma_contrato(self, contrato_id: str, fecha: datetime) -> Resultado:
        c = self.contratos.obtener_por_id(contrato_id)
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
        c = self.contratos.obtener_por_id(contrato_id)
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
        plazo_vencido = fecha > sumar_dias_habiles(c.fecha_firma, 3)
        try:
            with transaccion(self.uow, c):
                c.registrar_seguimiento_anticipo(fecha, resultado_contacto, plazo_vencido); self.contratos.guardar(c)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Seguimiento registrado: el Cliente dispone de 24 horas naturales para efectuar el anticipo.")

    def confirmar_contratacion(self, contrato_id: str, ahora: datetime) -> Resultado:
        c = self.contratos.obtener_por_id(contrato_id)
        if c.estado == EstadoContrato.CONTRATACION_CONFIRMADA:
            return Resultado.ok("La contratación ya estaba confirmada.")           # idempotente
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
        c = self.contratos.obtener_por_id(contrato_id)
        ec = self.ec.obtener_por_contrato_id(contrato_id) or EstadoCuenta(nuevo_id("EC"), contrato_id, c.evento_id)
        with transaccion(self.uow, ec):
            ec.registrar_obligacion_anticipo(nuevo_id("OB"), c.condiciones.costo_total, c.fecha_firma)
            self.ec.guardar(ec)

    def registrar_obligacion_saldo_original(self, contrato_id: str) -> None:
        c = self.contratos.obtener_por_id(contrato_id)
        ev = self.eventos.obtener_por_id(c.evento_id)                         # solo lectura
        ec = self.ec.obtener_por_contrato_id(contrato_id)
        with transaccion(self.uow, ec):
            ec.registrar_obligacion_saldo_original(nuevo_id("OB"), c.condiciones.costo_total, ev.datos.fecha_hora)
            self.ec.guardar(ec)

    def comunicar_solicitud_pago(self, tipo: TipoSolicitud, solicitud_id: str, concepto: ConceptoPago,
                                 importe: Importe, comunicado_en: datetime) -> Resultado:
        """Única operación de origen con dos raíces (decisión justificada en la Etapa 3)."""
        repo = self.cambios if tipo == TipoSolicitud.CAMBIO else self.adicionales
        s = repo.obtener_por_id(solicitud_id)
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        try:
            with transaccion(self.uow, ec, s):
                o = ec.comunicar_solicitud_pago(nuevo_id("OB"), concepto, importe, solicitud_id, comunicado_en)
                s.registrar_solicitud_pago(o.obligacion_id)
                self.ec.guardar(ec); repo.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        self.notificador.notificar(["Cliente"], "Solicitud de pago", f"Plazo de 24 horas naturales desde {comunicado_en:%d/%m/%Y %H:%M}.")
        return Resultado.ok("Solicitud de pago comunicada.", obligacion_id=o.obligacion_id)

    def registrar_y_verificar_pago(self, estado_cuenta_id: str, obligacion_id: str, importe: Importe,
                                   fecha: datetime, comprobante: str, registrado_en: Optional[datetime] = None,
                                   verificar_ahora: bool = True) -> Resultado:
        """`fecha`: cuándo el Cliente efectuó el pago (fuera del sistema); `registrado_en`: cuándo Administración lo registra.
        Con `verificar_ahora=False` el pago queda Registrado y se verifica después con verificar_pago_registrado()."""
        verificado = verificar_ahora and self.verificador.verificar(comprobante, importe)   # fuera de la transacción
        ec = self.ec.obtener_por_id(estado_cuenta_id)
        try:
            with transaccion(self.uow, ec):
                p = ec.registrar_y_verificar_pago(nuevo_id("PG"), obligacion_id, importe, fecha, comprobante, verificado,
                                                  registrado_en)
                self.ec.guardar(ec)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Pago {p.estado.value}.", pago_id=p.pago_id, estado=p.estado.value)

    def verificar_pago_registrado(self, estado_cuenta_id: str, pago_id: str, verificado_en: datetime) -> Resultado:
        ec = self.ec.obtener_por_id(estado_cuenta_id)
        p = next((x for x in ec.pagos if x.pago_id == pago_id), None)
        if p is None or not self.verificador.verificar(p.comprobante, p.importe):          # fuera de la transacción
            return Resultado.rechazo("El pago no pudo verificarse; permanece registrado.")
        try:
            with transaccion(self.uow, ec):
                ec.verificar_pago_registrado(pago_id, verificado_en); self.ec.guardar(ec)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Pago Verificado.", pago_id=pago_id, estado=p.estado.value)

    def registrar_vencimiento_saldo_original(self, estado_cuenta_id: str, ahora: datetime) -> Resultado:
        ec = self.ec.obtener_por_id(estado_cuenta_id)
        with transaccion(self.uow, ec):
            vencido = ec.registrar_vencimiento_saldo(ahora); self.ec.guardar(ec)
        return Resultado.ok("Saldo vencido registrado." if vencido else "Sin vencimiento.")

    def activar_protocolo_cobro(self, estado_cuenta_id: str, importe_moratorio: Importe, comunicado_en: datetime,
                                seguimiento: str) -> Resultado:
        ec = self.ec.obtener_por_id(estado_cuenta_id)
        try:
            with transaccion(self.uow, ec):
                ec.activar_protocolo_cobro(nuevo_id("OB"), importe_moratorio, comunicado_en, seguimiento); self.ec.guardar(ec)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        self.notificador.notificar(["Cliente"], "Recordatorio de pago", "Saldo vencido y cargos moratorios: 24 horas naturales.")
        return Resultado.ok("Protocolo de cobro activado.")

    def registrar_importe_adicional_sustitucion(self, sustitucion_id: str, importe: Importe) -> Resultado:
        s = self.sustituciones.obtener_por_id(sustitucion_id)                 # solo lectura
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
        ev = self.eventos.obtener_por_id(evento_id)                           # solo lectura
        ec = self.ec.obtener_por_id(estado_cuenta_id)
        with transaccion(self.uow, ec):
            ec.aplicar_cierre_sin_realizar(origen_id, fecha_cierre, ev.cancelado, lambda: nuevo_id("DV"))
            self.ec.guardar(ec)

    def registrar_y_ejecutar_devolucion(self, estado_cuenta_id: str, devolucion_id: str, ahora: datetime) -> Resultado:
        ec = self.ec.obtener_por_id(estado_cuenta_id)
        d = next(x for x in ec.devoluciones if x.devolucion_id == devolucion_id)
        comprobante = self.ejecutor.ejecutar(devolucion_id, d.importe, referencia_idempotente=devolucion_id)  # fuera de la transacción
        with transaccion(self.uow, ec):
            ec.registrar_devolucion_efectuada(devolucion_id, ahora, comprobante); self.ec.guardar(ec)
        return Resultado.ok("Devolución efectuada.", comprobante=comprobante)


# ======================================================================= CU-03
@con_rechazos_de_negocio
class GestionCierreEventoService:
    def __init__(self, eventos: IEventoRepository, contratos: IContratoRepository, estados_cuenta: IEstadoCuentaRepository,
                 uow: IUnitOfWork, notificador: INotificadorParticipantes):
        self.eventos, self.contratos, self.ec, self.uow, self.notificador = eventos, contratos, estados_cuenta, uow, notificador

    def gestionar_cancelacion_solicitada(self, evento_id: str, motivo: str, ahora: datetime) -> Resultado:
        ev = self.eventos.obtener_por_id(evento_id)
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
        ev = self.eventos.obtener_por_id(evento_id)
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
        ec = self.ec.obtener_por_id(estado_cuenta_id)
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
        ev = self.eventos.obtener_por_id(evento_id)
        verificado = any(ec.no_regularizado_verificado for ec in self.ec.listar_por_evento_id(evento_id))   # solo lectura
        try:
            with transaccion(self.uow, ev):
                cambiado = ev.cancelar_por_falta_de_regularizacion(motivo, coordinador, ahora, verificado)
                self.eventos.guardar(ev)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Cancelación registrada por el Coordinador." if cambiado else "El evento ya estaba cancelado por esta causa.")

    def procesar_inicio_evento(self, evento_id: str, ahora: datetime) -> Resultado:
        ev = self.eventos.obtener_por_id(evento_id)
        try:
            with transaccion(self.uow, ev):
                ev.iniciar(ahora); self.eventos.guardar(ev)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok("Evento En ejecución.")

    def finalizar_evento(self, evento_id: str, fecha: datetime) -> Resultado:
        ev = self.eventos.obtener_por_id(evento_id)
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
        ev = self.eventos.obtener_por_id(evento_id)                           # solo lectura
        if ev.estado.value != "En organización":
            return Resultado.rechazo("El cambio solo procede después de contratar y antes del inicio (CA-039).")
        ec = self.ec.obtener_por_contrato_id(contrato_id)
        s = SolicitudCambio(nuevo_id("SC"), evento_id, contrato_id, ec.id, descripcion,
                            AnticipacionSolicitud(ahora, ev.datos.fecha_hora), TarifaCargoTardio(tarifa_vigente),
                            datos_propuestos, condiciones_propuestas)
        d = self.regularizacion.evaluar(_saldo(self.ec, contrato_id), ev.cancelado, s.condicion_temporal(ev.iniciado))
        with transaccion(self.uow, s):
            s.aplicar_decision_regularizacion(d, ahora, EstadoSolicitudCambio.NO_PROCEDENTE)
            self.cambios.guardar(s)
        if d.detener_por_saldo:
            self.notificador.notificar(["Cliente"], "Solicitud detenida", "Debe regularizar el saldo vencido y los cargos moratorios.")
        return Resultado.ok(f"Solicitud {s.estado.value}.", solicitud_id=s.id, estado=s.estado.value)

    def retomar_solicitud_cambio(self, solicitud_id: str, ahora: datetime) -> None:
        s = self.cambios.obtener_por_id(solicitud_id)
        ev = self.eventos.obtener_por_id(s.evento_id)
        d = self.regularizacion.evaluar(_saldo(self.ec, s.contrato_id), ev.cancelado, s.condicion_temporal(ev.iniciado))
        with transaccion(self.uow, s):
            s.aplicar_decision_regularizacion(d, ahora, EstadoSolicitudCambio.NO_PROCEDENTE); self.cambios.guardar(s)

    def evaluar_viabilidad_cambio(self, solicitud_id: str, resultado: ResultadoViabilidad,
                                  costo_adicional_proveedor: Optional[Importe], ahora: datetime) -> Resultado:
        """La aplicación recibe la respuesta de los proveedores (viabilidad y costo); EvaluarImpactoCambio compara la
        configuración vigente del Evento con la modificación propuesta (CA-038, CA-060, CA-063)."""
        s = self.cambios.obtener_por_id(solicitud_id)
        ev = self.eventos.obtener_por_id(s.evento_id)                         # solo lectura
        vigente = ev.configuracion_vigente()
        impacto = self.impacto.evaluar(vigente, s.configuracion_propuesta(vigente, costo_adicional_proveedor))
        try:
            with transaccion(self.uow, s):
                s.registrar_viabilidad(resultado, impacto, ahora); self.cambios.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Solicitud {s.estado.value}.", estado=s.estado.value)

    def registrar_decision_cliente_cambio(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = self.cambios.obtener_por_id(solicitud_id)
        try:
            with transaccion(self.uow, s):
                s.registrar_decision_cliente(decision); self.cambios.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_autorizacion_administracion_cambio(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = self.cambios.obtener_por_id(solicitud_id)
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
        s = self.cambios.obtener_por_id(solicitud_id)                         # solo lectura
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
        s = self.cambios.obtener_por_id(solicitud_id)
        ev = self.eventos.obtener_por_id(s.evento_id)                         # solo lectura
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)                       # solo lectura
        with transaccion(self.uow, s):
            faltan = s.confirmar(ec.obligacion_liquidada(s.obligacion_pago_id), ev.iniciado, ahora, ev.cancelado)
            self.cambios.guardar(s)
        if faltan:
            return Resultado.rechazo("El cambio no puede confirmarse.", faltan)
        return Resultado.ok("Cambio confirmado.")

    def cerrar_cambio_por_falta_de_pago(self, solicitud_id: str, ahora: datetime) -> Resultado:
        s = self.cambios.obtener_por_id(solicitud_id)
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)                       # solo lectura
        if not s.obligacion_pago_id or not ec.obligacion_vencida_sin_pago(s.obligacion_pago_id, ahora):
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
        return self.regularizacion.evaluar(_saldo(self.ec, s.contrato_id), ev.cancelado, s.condicion_temporal(ahora, ev.iniciado))

    def registrar_solicitud_servicio_adicional(self, evento_id: str, contrato_id: str, servicio: str, ahora: datetime) -> Resultado:
        ev = self.eventos.obtener_por_id(evento_id)
        ec = self.ec.obtener_por_contrato_id(contrato_id)
        s = SolicitudServicioAdicional(nuevo_id("SA"), evento_id, contrato_id, ec.id, servicio,
                                       AnticipacionSolicitud(ahora, ev.datos.fecha_hora))
        # N6 (SE-004, O-01): la solicitud ya está registrada; se verifica en orden el Evento, el plazo y, al final, el
        # saldo. Cada verificación se ejecuta solo si las anteriores se cumplieron y se conserva el primer motivo.
        d = self.regularizacion.evaluar_solicitud_nueva(ev.cancelado, lambda: s.condicion_temporal(ahora, ev.iniciado),
                                                        lambda: _saldo(self.ec, contrato_id))
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

    def evaluar_disponibilidad_servicio_adicional(self, solicitud_id: str, proveedores_actuales: List[str], ahora: datetime) -> Resultado:
        s = self.adicionales.obtener_por_id(solicitud_id)
        opciones = self.disponibilidad.consultar(s.servicio, s.anticipacion.fecha_evento, proveedores_actuales)  # fuera de la transacción
        elegida = next((o for o in opciones if o.disponible), None)
        from domain.valores import DisponibilidadProveedor
        try:
            with transaccion(self.uow, s):
                s.registrar_disponibilidad(elegida or DisponibilidadProveedor("", False), ahora); self.adicionales.guardar(s)
        except ErrorDominio as e:
            return Resultado.rechazo(str(e))
        return Resultado.ok(f"Solicitud {s.estado.value}.", estado=s.estado.value)

    def registrar_decision_espera_cliente(self, solicitud_id: str, acepta_esperar: bool, ahora: datetime) -> Resultado:
        s = self.adicionales.obtener_por_id(solicitud_id)
        with transaccion(self.uow, s):
            s.registrar_respuesta_espera(acepta_esperar, ahora); self.adicionales.guardar(s)
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_aprobacion_cliente_servicio_adicional(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = self.adicionales.obtener_por_id(solicitud_id)
        with transaccion(self.uow, s):
            s.registrar_decision_cliente(decision); self.adicionales.guardar(s)
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_autorizacion_administracion_servicio_adicional(self, solicitud_id: str, decision: Decision) -> Resultado:
        s = self.adicionales.obtener_por_id(solicitud_id)
        with transaccion(self.uow, s):
            s.registrar_autorizacion(decision); self.adicionales.guardar(s)
        if not decision.aprobada:
            self.notificador.notificar(["Cliente"], "Servicio adicional no autorizado", decision.motivo)
        return Resultado.ok(f"Solicitud {s.estado.value}.")

    def registrar_anexo_servicio_adicional(self, solicitud_id: str, descripcion: str, ahora: datetime) -> Resultado:
        s = self.adicionales.obtener_por_id(solicitud_id)                     # solo lectura
        if not s.puede_registrar_anexo():
            return Resultado.rechazo("La solicitud no está Autorizada o ya tiene anexo.")
        c = self.contratos.obtener_por_id(s.contrato_id)
        with transaccion(self.uow, c):
            a = c.registrar_anexo(nuevo_id("AX"), TipoSolicitud.SERVICIO_ADICIONAL, s.id, descripcion, ahora); self.contratos.guardar(c)
        return Resultado.ok("Anexo registrado en el contrato.", anexo_id=a.anexo_id)

    def confirmar_servicio_adicional(self, solicitud_id: str, ahora: datetime) -> Resultado:
        s = self.adicionales.obtener_por_id(solicitud_id)
        ev = self.eventos.obtener_por_id(s.evento_id)
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        with transaccion(self.uow, s):
            faltan = s.confirmar(ec.obligacion_liquidada(s.obligacion_pago_id), ev.iniciado, ahora, ev.cancelado)
            self.adicionales.guardar(s)
        return Resultado.rechazo("El servicio adicional no puede confirmarse.", faltan) if faltan else Resultado.ok("Servicio adicional confirmado.")

    def cerrar_servicio_adicional_por_falta_de_pago(self, solicitud_id: str, ahora: datetime) -> Resultado:
        s = self.adicionales.obtener_por_id(solicitud_id)
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
        reacción a la cancelación y una nueva quedaría pendiente sin cierre posible."""
        ev = self.eventos.obtener_por_id(evento_id)                           # solo lectura
        if ev.cancelado:
            return Resultado.rechazo("El evento está cancelado: no se inician nuevas sustituciones de proveedor.")
        sc = ev.servicios[servicio_contratado_id]
        ec = self.ec.obtener_por_contrato_id(contrato_id)
        s = SustitucionProveedor(nuevo_id("SP"), evento_id, servicio_contratado_id, sc.proveedor_id, contrato_id, ec.id, ahora)
        with transaccion(self.uow, s):
            self.sustituciones.guardar(s)
        return Resultado.ok("Sustitución En búsqueda de alternativa.", sustitucion_id=s.id)

    def buscar_alternativa_sustitucion(self, sustitucion_id: str, condiciones_alternativa: CondicionesServicio,
                                       costo_adicional: Optional[Importe], ahora: datetime) -> Resultado:
        s = self.sustituciones.obtener_por_id(sustitucion_id)
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
        s = self.sustituciones.obtener_por_id(sustitucion_id)
        with transaccion(self.uow, s):
            s.registrar_decision_cliente(decision); self.sustituciones.guardar(s)
        return Resultado.ok(f"Sustitución {s.estado.value}.")

    def registrar_autorizacion_administracion_sustitucion(self, sustitucion_id: str, decision: Decision) -> Resultado:
        s = self.sustituciones.obtener_por_id(sustitucion_id)
        ev = self.eventos.obtener_por_id(s.evento_id)                         # solo lectura: fecha del evento
        with transaccion(self.uow, s):
            s.registrar_autorizacion(decision, ev.datos.fecha_hora); self.sustituciones.guardar(s)
        if not decision.aprobada:
            self.notificador.notificar(["Cliente"], "Sustitución no autorizada", "Se continúa buscando otra alternativa (CA-050).")
        return Resultado.ok(f"Sustitución {s.estado.value}.")

    def registrar_anexo_sustitucion_proveedor(self, sustitucion_id: str, descripcion: str, ahora: datetime) -> Resultado:
        s = self.sustituciones.obtener_por_id(sustitucion_id)
        if not s.puede_registrar_anexo():
            return Resultado.rechazo("La sustitución no está Pendiente de formalización o ya tiene anexo.")
        c = self.contratos.obtener_por_id(s.contrato_id)
        with transaccion(self.uow, c):
            a = c.registrar_anexo(nuevo_id("AX"), TipoSolicitud.SUSTITUCION_PROVEEDOR, s.id, descripcion, ahora); self.contratos.guardar(c)
        return Resultado.ok("Anexo registrado en el contrato.", anexo_id=a.anexo_id)

    def confirmar_sustitucion_proveedor(self, sustitucion_id: str, ahora: datetime) -> Resultado:
        s = self.sustituciones.obtener_por_id(sustitucion_id)
        ev = self.eventos.obtener_por_id(s.evento_id)
        ec = self.ec.obtener_por_id(s.estado_cuenta_id)
        ob = next((o for o in ec.obligaciones.values() if o.origen_id == s.id), None)
        with transaccion(self.uow, s):
            faltan = s.confirmar(bool(ob) and ec.obligacion_liquidada(ob.obligacion_id), ev.iniciado, ahora, ev.cancelado)
            self.sustituciones.guardar(s)
        return Resultado.rechazo("La sustitución no puede confirmarse.", faltan) if faltan else Resultado.ok("Sustitución confirmada.")

    def cerrar_sustitucion_por_inicio_evento(self, sustitucion_id: str, ahora: datetime) -> None:
        s = self.sustituciones.obtener_por_id(sustitucion_id)
        with transaccion(self.uow, s):
            s.cerrar_por_inicio_evento(ahora); self.sustituciones.guardar(s)
