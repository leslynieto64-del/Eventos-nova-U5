"""Aggregate EstadoCuenta (raíz) con ObligacionPago, Pago y Devolucion."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from .base import AggregateRoot
from .maquina_estados import MaquinaEstados, Transicion
from .valores import (Importe, PlazoPago, ConceptoPago as CP, EstadoObligacionPago as EO, EstadoPago as EPg,
                      EstadoDevolucion as ED, ErrorDominio, restar_dias_habiles)
from .eventos_dominio import (PagoVerificado, SaldoContratoOriginalVencido, SaldoVencidoRegularizado,
                              PlazoRegularizacionVencido, DevolucionRegistrada, CargosMoratoriosComunicados)

PORCENTAJE_ANTICIPO = Decimal(30)       # BN-009
DIAS_HABILES_ANTICIPO = 3                # BN-009
DIAS_HABILES_SALDO = 3                   # BN-005
HORAS_VENTANA = 24                       # BN-003, BN-004, BN-005

MENSAJE_PAGO_NO_VERIFICABLE = "Solo se verifica un pago registrado que está pendiente de verificación."


# ---------------------------------------------------------------- State Machines (Etapa E3D)
# Mapa de dominio U3, página «04 — Detalle C: Gestión financiera». Las máquinas solo validan pares estado-acción; las
# condiciones de negocio (plazos, importes, ventana de regularización, SE-012) siguen en los métodos de EstadoCuenta.
# Las altas (obligaciones, pagos y devoluciones nuevas) son creaciones, no transiciones.
class AccionObligacionPago(Enum):
    LIQUIDAR_POR_PAGO = "liquidar_por_pago"        # verificación de un pago (_destinos_verificacion)
    VENCER = "vencer"                              # registrar_vencimiento_saldo
    REGULARIZAR = "regularizar"                    # resolver_regularizacion con resultado «Regularizado»
    DEJAR_SIN_EFECTO = "dejar_sin_efecto"          # aplicar_cierre_sin_realizar


class AccionPago(Enum):
    VERIFICAR = "verificar"                        # verificación de un pago (_destinos_verificacion)
    RECHAZAR_IMPORTE = "rechazar_importe"          # registrar_y_verificar_pago: anticipo con importe incorrecto


class AccionDevolucion(Enum):
    REGISTRAR_EFECTUADA = "registrar_efectuada"    # registrar_devolucion_efectuada


_AO, _AP, _AD = AccionObligacionPago, AccionPago, AccionDevolucion

# Pendiente → Liquidada | Vencida | Sin efecto; Vencida → Liquidada. Liquidada y Sin efecto no tienen salida.
# Una obligación Liquidada sigue admitiendo pagos válidos: el pago se registra y verifica (con su PagoVerificado) y la
# obligación no cambia; por eso (Liquidada, LIQUIDAR_POR_PAGO) no se declara como repetición idempotente.
MAQUINA_OBLIGACION_PAGO = MaquinaEstados(
    estados=EO,
    transiciones=(
        Transicion(EO.PENDIENTE, _AO.LIQUIDAR_POR_PAGO, EO.LIQUIDADA),     # CA-018, CA-019, CA-026
        Transicion(EO.PENDIENTE, _AO.VENCER, EO.VENCIDA),                  # CA-023, CA-025, BN-005
        Transicion(EO.VENCIDA, _AO.REGULARIZAR, EO.LIQUIDADA),             # CA-027: saldo vencido regularizado
        Transicion(EO.PENDIENTE, _AO.REGULARIZAR, EO.LIQUIDADA),           # CA-025, CA-027: cargos moratorios
        Transicion(EO.PENDIENTE, _AO.DEJAR_SIN_EFECTO, EO.SIN_EFECTO),     # SE-012, CA-070, CA-071, CA-096, CA-097, GL-053
    ),
    nombre="ObligacionPago",
)

# Registrado → Verificado | Importe incorrecto. Un pago corregido es un pago nuevo.
MAQUINA_PAGO = MaquinaEstados(
    estados=EPg,
    transiciones=(
        Transicion(EPg.REGISTRADO, _AP.VERIFICAR, EPg.VERIFICADO),                 # CA-018, CA-021, CA-027
        Transicion(EPg.REGISTRADO, _AP.RECHAZAR_IMPORTE, EPg.IMPORTE_INCORRECTO),  # CA-019
    ),
    mensajes_rechazo={_AP.VERIFICAR: lambda o: MENSAJE_PAGO_NO_VERIFICABLE},
    nombre="Pago",
)

# Pendiente → Efectuada. Registrar otra vez una devolución Efectuada se acepta sin efecto y sin DevolucionRegistrada.
MAQUINA_DEVOLUCION = MaquinaEstados(
    estados=ED,
    transiciones=(Transicion(ED.PENDIENTE, _AD.REGISTRAR_EFECTUADA, ED.EFECTUADA),),   # SE-012, CA-098, GL-057
    repeticiones_idempotentes=((ED.EFECTUADA, _AD.REGISTRAR_EFECTUADA),),
    nombre="Devolucion",
)


@dataclass
class ObligacionPago:
    obligacion_id: str
    concepto: CP
    importe: Importe
    plazo: Optional[PlazoPago]
    origen_id: str                      # contrato, solicitudCambioId, solicitudServicioAdicionalId o sustitucionProveedorId
    estado: EO = EO.PENDIENTE


@dataclass
class Pago:
    """El pago se efectúa fuera del sistema; Administración lo registra y verifica manualmente.
    `fecha` es la fecha y hora en que el Cliente efectuó el pago (según el comprobante) y es la que decide si cumplió
    el plazo; `registrado_en` y `verificado_en` son momentos distintos y pueden ser posteriores al plazo (BN-009)."""
    pago_id: str
    obligacion_id: str
    importe: Importe
    fecha: datetime
    comprobante: str
    estado: EPg = EPg.REGISTRADO
    registrado_en: Optional[datetime] = None
    verificado_en: Optional[datetime] = None


@dataclass
class Devolucion:
    devolucion_id: str
    solicitud_id: str
    concepto: CP
    importe: Importe
    motivo_devolucion: str              # atributo; no reutiliza MotivoCierreSolicitud
    fecha_cierre: datetime
    estado: ED = ED.PENDIENTE
    fecha_devolucion: Optional[datetime] = None
    comprobante: Optional[str] = None


class EstadoCuenta(AggregateRoot):
    """Un EstadoCuenta por contrato: decisión arquitectónica, no regla textual del BRD."""

    def __init__(self, estado_cuenta_id: str, contrato_id: str, evento_id: str):
        super().__init__(estado_cuenta_id)
        self.contrato_id, self.evento_id = contrato_id, evento_id
        self.obligaciones: Dict[str, ObligacionPago] = {}
        self.pagos: List[Pago] = []
        self.devoluciones: List[Devolucion] = []
        self.seguimientos_cobro: List[str] = []
        self.resultado_regularizacion: Optional[str] = None      # registrado por Administración
        self.fecha_resultado_regularizacion: Optional[datetime] = None
        self._ventana_resuelta: Optional[str] = None             # obligación de moratorios ya revisada

    # -- obligaciones
    def _crear(self, ob_id, concepto, importe, plazo, origen_id) -> ObligacionPago:
        existente = next((o for o in self.obligaciones.values() if o.concepto == concepto and o.origen_id == origen_id), None)
        if existente:
            return existente                                           # idempotencia en reintentos
        o = ObligacionPago(ob_id, concepto, importe, plazo, origen_id)
        self.obligaciones[ob_id] = o
        return o

    def registrar_obligacion_anticipo(self, ob_id: str, costo_total: Importe, fecha_firma: datetime) -> ObligacionPago:
        return self._crear(ob_id, CP.ANTICIPO, costo_total.porcentaje(PORCENTAJE_ANTICIPO),
                           PlazoPago.dias_habiles(fecha_firma, DIAS_HABILES_ANTICIPO), self.contrato_id)

    def registrar_obligacion_saldo_original(self, ob_id: str, costo_total: Importe, fecha_evento: datetime) -> ObligacionPago:
        anticipo = sum((p.importe.cantidad for p in self.pagos if p.estado == EPg.VERIFICADO
                        and self.obligaciones[p.obligacion_id].concepto == CP.ANTICIPO), Decimal(0))
        limite = restar_dias_habiles(fecha_evento, DIAS_HABILES_SALDO)   # la fecha del evento no se reprograma (BRD, fuera del alcance)
        return self._crear(ob_id, CP.SALDO_CONTRATO_ORIGINAL, Importe(costo_total.cantidad - anticipo),
                           PlazoPago(fecha_evento, limite), self.contrato_id)

    def comunicar_solicitud_pago(self, ob_id: str, concepto: CP, importe: Importe, origen_id: str, comunicado_en: datetime) -> ObligacionPago:
        if concepto not in (CP.CAMBIO, CP.CARGO_CAMBIO_TARDIO, CP.SERVICIO_ADICIONAL):
            raise ErrorDominio("La ventana de 24 h aplica a cambios y servicios adicionales.")
        return self._crear(ob_id, concepto, importe, PlazoPago.horas_naturales(comunicado_en, HORAS_VENTANA), origen_id)

    def registrar_importe_adicional_sustitucion(self, ob_id: str, importe: Importe, sustitucion_id: str,
                                                aprobada_despues_del_limite: bool, fecha_evento: datetime) -> ObligacionPago:
        """Se integra una sola vez al saldo general (CA-052, GL-056).
        Antes del límite ordinario: se liquida con el saldo general, a más tardar 3 días hábiles antes del evento.
        Después del límite: no tiene otro plazo fijo; se paga y verifica antes de confirmar el reemplazo y no vence
        automáticamente (SE-001, CA-052). No se reutiliza una fecha ya vencida."""
        if aprobada_despues_del_limite:
            plazo = None
        else:
            plazo = PlazoPago(fecha_evento, restar_dias_habiles(fecha_evento, DIAS_HABILES_SALDO))
        return self._crear(ob_id, CP.SUSTITUCION_PROVEEDOR, importe, plazo, sustitucion_id)

    def _obligacion(self, concepto: CP) -> Optional[ObligacionPago]:
        return next((o for o in self.obligaciones.values() if o.concepto == concepto), None)

    # -- pagos
    def registrar_y_verificar_pago(self, pago_id: str, ob_id: str, importe: Importe, fecha: datetime,
                                   comprobante: str, verificado_externamente: bool,
                                   registrado_en: Optional[datetime] = None) -> Pago:
        """`fecha`: cuándo el Cliente efectuó el pago; `registrado_en`: cuándo Administración lo registra (por omisión,
        la misma fecha). El cumplimiento del plazo se evalúa con `fecha`, no con el registro ni con la verificación."""
        o = self.obligaciones.get(ob_id)
        if o is None or o.estado == EO.SIN_EFECTO:
            raise ErrorDominio("La obligación no existe o quedó sin efecto.")
        p = Pago(pago_id, ob_id, importe, fecha, comprobante, registrado_en=registrado_en or fecha)
        if o.concepto == CP.ANTICIPO and importe != o.importe:
            p.estado = MAQUINA_PAGO.transitar(p.estado, AccionPago.RECHAZAR_IMPORTE)   # CA-019: se solicita corrección
            self.pagos.append(p)
            return p
        # Con verificación externa, ambos destinos (pago y obligación) se validan antes de agregar el pago.
        destinos = self._destinos_verificacion(o, p) if verificado_externamente else None
        self.pagos.append(p)                                           # registrado ≠ verificado (GL-046, GL-052)
        if destinos is not None:
            self._aplicar_verificacion(o, p, p.registrado_en, *destinos)
        return p

    def verificar_pago_registrado(self, pago_id: str, verificado_en: datetime) -> Pago:
        """Administración verifica después un pago que ya había registrado. La verificación tardía no convierte en
        incumplimiento un pago que el Cliente efectuó dentro del plazo."""
        p = next((x for x in self.pagos if x.pago_id == pago_id), None)
        if p is None:
            raise ErrorDominio(MENSAJE_PAGO_NO_VERIFICABLE)
        MAQUINA_PAGO.validar(p.estado, AccionPago.VERIFICAR)          # mismo mensaje si ya no está Registrado
        o = self.obligaciones[p.obligacion_id]
        if o.estado == EO.SIN_EFECTO:
            raise ErrorDominio("La obligación quedó sin efecto.")
        self._aplicar_verificacion(o, p, verificado_en, *self._destinos_verificacion(o, p))
        return p

    def _destinos_verificacion(self, o: ObligacionPago, p: Pago):
        """Destinos validados del pago y, si transita, de la obligación; no modifica nada.
        El ciclo de vida del Pago y el estado de la ObligacionPago son independientes: el pago se verifica (y se emite
        PagoVerificado) aunque la obligación ya esté Liquidada o en regularización; la obligación solo transita si está
        Pendiente y lo pagado, contando este pago, cubre su importe."""
        destino_pago = MAQUINA_PAGO.transitar(p.estado, AccionPago.VERIFICAR)
        en_regularizacion = o.estado == EO.VENCIDA or o.concepto == CP.CARGOS_MORATORIOS
        destino_obligacion = None
        if en_regularizacion:
            pass        # la liquidación la determina resolver_regularizacion() al revisar la ventana (CA-027)
        elif o.plazo is None or not o.plazo.vencido(p.fecha) or o.concepto in (CP.SALDO_CONTRATO_ORIGINAL, CP.SUSTITUCION_PROVEEDOR):
            pagado = self._pagado(o.obligacion_id) + p.importe.cantidad          # este pago todavía no está Verificado
            if o.estado == EO.PENDIENTE and pagado >= o.importe.cantidad:          # Liquidada: sigue Liquidada
                destino_obligacion = MAQUINA_OBLIGACION_PAGO.transitar(o.estado, AccionObligacionPago.LIQUIDAR_POR_PAGO)
        return destino_pago, destino_obligacion

    def _aplicar_verificacion(self, o: ObligacionPago, p: Pago, verificado_en: datetime, destino_pago: EPg,
                              destino_obligacion: Optional[EO]) -> None:
        p.estado, p.verificado_en = destino_pago, verificado_en
        if destino_obligacion is not None:
            o.estado = destino_obligacion
        self._registrar(PagoVerificado(self.id, verificado_en, obligacion_id=o.obligacion_id, concepto=o.concepto.value,
                                       origen_id=o.origen_id))

    def _pagado(self, ob_id: str, hasta: Optional[datetime] = None) -> Decimal:
        return sum((p.importe.cantidad for p in self.pagos if p.obligacion_id == ob_id and p.estado == EPg.VERIFICADO
                    and (hasta is None or p.fecha <= hasta)), Decimal(0))

    def anticipo_verificado(self, efectuado_hasta: Optional[datetime] = None) -> bool:
        """Con `efectuado_hasta` solo cuenta un anticipo que el Cliente efectuó a más tardar en esa fecha (BN-009)."""
        o = self._obligacion(CP.ANTICIPO)
        return bool(o) and any(p.obligacion_id == o.obligacion_id and p.estado == EPg.VERIFICADO
                               and (efectuado_hasta is None or p.fecha <= efectuado_hasta) for p in self.pagos)

    def anticipo_efectuado_hasta(self, limite: datetime) -> bool:
        """Hay un anticipo efectuado por el Cliente a más tardar en `limite`, aunque esté pendiente de registro o verificación."""
        o = self._obligacion(CP.ANTICIPO)
        return bool(o) and any(p.obligacion_id == o.obligacion_id and p.fecha <= limite for p in self.pagos)

    def _pago_pendiente_de_verificacion(self, ob_ids, hasta: datetime) -> bool:
        """Pago efectuado a más tardar en `hasta` que Administración registró y todavía no verifica."""
        return any(p.obligacion_id in ob_ids and p.estado == EPg.REGISTRADO and p.fecha <= hasta for p in self.pagos)

    def anticipo_recibido(self) -> bool:
        o = self._obligacion(CP.ANTICIPO)
        return bool(o) and any(p.obligacion_id == o.obligacion_id for p in self.pagos)

    def obligacion_liquidada(self, ob_id: Optional[str]) -> bool:
        return bool(ob_id) and self.obligaciones[ob_id].estado == EO.LIQUIDADA

    def obligacion_vencida_sin_pago(self, ob_id: str, ahora: datetime) -> bool:
        """El plazo del Cliente para pagar venció y no hay un pago efectuado dentro de él: ni liquidado ni pendiente de
        verificación. La demora de Administración al registrar o verificar no es falta de pago."""
        o = self.obligaciones[ob_id]
        return (o.plazo.vencido(ahora) and o.estado != EO.LIQUIDADA
                and not self._pago_pendiente_de_verificacion({ob_id}, o.plazo.vence))

    # -- saldo vencido y regularización (BN-005)
    def _saldo_general(self) -> List[ObligacionPago]:
        """Saldo del contrato original más los importes de sustitución integrados con el plazo ordinario."""
        return [o for o in self.obligaciones.values()
                if o.concepto == CP.SALDO_CONTRATO_ORIGINAL or (o.concepto == CP.SUSTITUCION_PROVEEDOR and o.plazo is not None)]

    def registrar_vencimiento_saldo(self, ahora: datetime) -> bool:
        vencen = [o for o in self._saldo_general()
                  if o.estado == EO.PENDIENTE and o.plazo is not None and ahora > o.plazo.vence and self._pagado(o.obligacion_id) < o.importe.cantidad
                  and not self._pago_pendiente_de_verificacion({o.obligacion_id}, o.plazo.vence)]   # pagado a tiempo, sin verificar aún
        if not vencen:
            return False
        # Vencimiento masivo: se validan todas las transiciones antes de asignar la primera (sin cambios parciales).
        destinos = [MAQUINA_OBLIGACION_PAGO.transitar(o.estado, AccionObligacionPago.VENCER) for o in vencen]
        for o, destino in zip(vencen, destinos):
            o.estado = destino
        self._registrar(SaldoContratoOriginalVencido(self.id, ahora, evento_ref=self.evento_id))
        return True

    @property
    def saldo_vencido_sin_regularizar(self) -> bool:
        return any(o.estado == EO.VENCIDA for o in self._saldo_general())

    def activar_protocolo_cobro(self, ob_id: str, importe_moratorio: Importe, comunicado_en: datetime, seguimiento: str) -> ObligacionPago:
        if not self.saldo_vencido_sin_regularizar:
            raise ErrorDominio("El protocolo de cobro requiere un saldo vencido (CA-025).")
        if self._obligacion(CP.CARGOS_MORATORIOS) and self._obligacion(CP.CARGOS_MORATORIOS).estado == EO.PENDIENTE:
            raise ErrorDominio("Ya existe una ventana de regularización vigente.")
        self.seguimientos_cobro.append(seguimiento)
        o = self._crear(ob_id, CP.CARGOS_MORATORIOS, importe_moratorio, PlazoPago.horas_naturales(comunicado_en, HORAS_VENTANA), self.contrato_id)
        self._registrar(CargosMoratoriosComunicados(self.id, comunicado_en))
        return o

    def resolver_regularizacion(self, revisado_en: datetime) -> bool:
        """Administración revisa los pagos al vencer la ventana y registra el resultado.
        Un pago tardío no regulariza (CA-027). No modifica Evento: la cancelación la registra el Coordinador."""
        mor = self._obligacion(CP.CARGOS_MORATORIOS)
        vencidas = [o for o in self._saldo_general() if o.estado == EO.VENCIDA]
        if mor is not None and self._ventana_resuelta == mor.obligacion_id:
            raise ErrorDominio("El resultado de esta regularización ya fue registrado.")
        if not mor or not vencidas:
            raise ErrorDominio("No hay una regularización en curso.")
        if not mor.plazo.vencido(revisado_en):
            raise ErrorDominio("La ventana de 24 horas naturales todavía está vigente.")
        limite = mor.plazo.vence
        ok = (all(self._pagado(o.obligacion_id, limite) >= o.importe.cantidad for o in vencidas) and
              self._pagado(mor.obligacion_id, limite) >= mor.importe.cantidad)
        if not ok and self._pago_pendiente_de_verificacion({o.obligacion_id for o in vencidas} | {mor.obligacion_id}, limite):
            raise ErrorDominio("Hay pagos efectuados dentro del plazo pendientes de verificación; "
                               "Administración debe verificarlos antes de registrar el resultado.")
        if ok:      # se validan todas las transiciones antes de registrar el resultado y asignar estados
            destinos = [MAQUINA_OBLIGACION_PAGO.transitar(o.estado, AccionObligacionPago.REGULARIZAR) for o in vencidas]
            destino_moratorios = MAQUINA_OBLIGACION_PAGO.transitar(mor.estado, AccionObligacionPago.REGULARIZAR)
        self.resultado_regularizacion = 'Regularizado' if ok else 'No regularizado'
        self.fecha_resultado_regularizacion = revisado_en
        self._ventana_resuelta = mor.obligacion_id
        if ok:
            for o, destino in zip(vencidas, destinos):
                o.estado = destino
            mor.estado = destino_moratorios
            self._registrar(SaldoVencidoRegularizado(self.id, revisado_en, evento_ref=self.evento_id))
        else:
            self._registrar(PlazoRegularizacionVencido(self.id, revisado_en, evento_ref=self.evento_id))
        return ok

    # -- lectura para la revisión administrativa de la cancelación (CA-090, CA-091)
    def pagos_realizados(self) -> Importe:
        return Importe(sum((p.importe.cantidad for p in self.pagos if p.estado == EPg.VERIFICADO), Decimal(0)))

    def saldo_pendiente_contrato(self) -> Importe:
        """Saldo general pendiente del contrato original (incluye sustituciones integradas)."""
        pendiente = Decimal(0)
        for o in self.obligaciones.values():
            if o.concepto in (CP.SALDO_CONTRATO_ORIGINAL, CP.SUSTITUCION_PROVEEDOR) and o.estado in (EO.PENDIENTE, EO.VENCIDA):
                pendiente += max(o.importe.cantidad - self._pagado(o.obligacion_id), Decimal(0))
        return Importe(pendiente)

    @property
    def no_regularizado_verificado(self) -> bool:
        """Administración registró que el saldo y los moratorios no se liquidaron dentro de la ventana.
        Un pago posterior no cambia este resultado (BN-005, CA-027)."""
        return self.resultado_regularizacion == 'No regularizado'

    # -- SE-012
    def aplicar_cierre_sin_realizar(self, origen_id: str, fecha_cierre: datetime, evento_cancelado: bool,
                                    devolucion_id_factory) -> List[Devolucion]:
        """Idempotente por origen. Las obligaciones del contrato original no cambian."""
        nuevas = []
        del_origen = [o for o in self.obligaciones.values() if o.origen_id == origen_id]
        # Solo los cobros Pendiente quedan sin efecto, esté o no cancelado el Evento (SE-012, AR-07); los demás estados
        # se omiten sin rechazo. Se validan todas las transiciones antes de asignar la primera.
        pendientes = [o for o in del_origen if o.estado == EO.PENDIENTE]
        destinos = [MAQUINA_OBLIGACION_PAGO.transitar(o.estado, AccionObligacionPago.DEJAR_SIN_EFECTO) for o in pendientes]
        for o, destino in zip(pendientes, destinos):
            o.estado = destino
        for o in del_origen:
            recibido = self._pagado(o.obligacion_id)
            ya = any(d.solicitud_id == origen_id and d.concepto == o.concepto for d in self.devoluciones)
            if recibido > 0 and not evento_cancelado and not ya:
                d = Devolucion(devolucion_id_factory(), origen_id, o.concepto, Importe(recibido),
                               "Operación no realizada (SE-012)", fecha_cierre)
                self.devoluciones.append(d); nuevas.append(d)
        return nuevas

    def registrar_devolucion_efectuada(self, devolucion_id: str, fecha: datetime, comprobante: str) -> None:
        d = next(d for d in self.devoluciones if d.devolucion_id == devolucion_id)    # AR-08 (pendiente): sin cambios
        if MAQUINA_DEVOLUCION.es_repeticion(d.estado, AccionDevolucion.REGISTRAR_EFECTUADA):
            return                                     # ya Efectuada: sin segunda devolución ni DevolucionRegistrada
        destino = MAQUINA_DEVOLUCION.transitar(d.estado, AccionDevolucion.REGISTRAR_EFECTUADA)
        d.estado, d.fecha_devolucion, d.comprobante = destino, fecha, comprobante
        self._registrar(DevolucionRegistrada(self.id, fecha, devolucion_id=devolucion_id))
