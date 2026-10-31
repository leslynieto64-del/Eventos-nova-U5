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
                      EstadoDevolucion as ED, TipoDevolucion, ErrorDominio, limite_exclusivo_dias_habiles)
from .eventos_dominio import (PagoVerificado, SaldoContratoOriginalVencido, SaldoVencidoRegularizado,
                              PlazoRegularizacionVencido, DevolucionRegistrada, CargosMoratoriosComunicados)

PORCENTAJE_ANTICIPO = Decimal(30)       # BN-009
DIAS_HABILES_ANTICIPO = 3                # BN-009
DIAS_HABILES_SALDO = 3                   # BN-005
DIAS_HABILES_DEVOLUCION = 5              # SE-012, CA-097, CA-098, GL-057
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
    RECHAZAR_IMPORTE = "rechazar_importe"          # HISTÓRICA (CA-019): desde E-3/E-4 ningún método la dispara; se conserva en el mapa de dominio


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

# Registrado → Verificado | Importe incorrecto. Desde E-3/E-4 ningún método asigna «Importe incorrecto» a un pago nuevo: uno de anticipo
# menor al mínimo es parcial y se acumula. La transición y el estado se conservan (mapa de dominio, pagos históricos). Un pago corregido es un pago nuevo.
MAQUINA_PAGO = MaquinaEstados(
    estados=EPg,
    transiciones=(
        Transicion(EPg.REGISTRADO, _AP.VERIFICAR, EPg.VERIFICADO),                 # CA-018, CA-021, CA-027
        Transicion(EPg.REGISTRADO, _AP.RECHAZAR_IMPORTE, EPg.IMPORTE_INCORRECTO),  # CA-019, solo pagos históricos (ver E-3/E-4)
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
    tipo: TipoDevolucion = TipoDevolucion.SOLICITUD_NO_REALIZADA
    pago_id: Optional[str] = None                   # devolución del anticipo: el pago que la origina (como máximo una por pago)
    fecha_referencia: Optional[datetime] = None     # devolución del anticipo: la más tardía entre el cierre y el registro (A-6)

    @property
    def fecha_limite(self) -> datetime:
        """Cinco días hábiles posteriores al día de referencia; el límite es exclusivo (00:00 del día siguiente al quinto),
        GL-060 y C-15 (decisión E-1 para SE-012; devolución del anticipo: decisión A-6). Referencia: la fecha de referencia de
        la devolución del anticipo (la más tardía entre el cierre y el registro del pago) o, en SE-012, el cierre de la
        solicitud. La verificación del importe no abre un plazo nuevo. Se calcula, no se almacena."""
        return limite_exclusivo_dias_habiles(self.fecha_referencia or self.fecha_cierre, DIAS_HABILES_DEVOLUCION)

    def _fuera_de_plazo(self, momento: datetime) -> bool:
        """El límite es exclusivo: a las 00:00 del día siguiente al quinto día hábil ya está fuera de plazo."""
        return momento >= self.fecha_limite

    def vencida(self, ahora: datetime) -> bool:
        """Sigue Pendiente después de su fecha límite."""
        return self.estado == ED.PENDIENTE and self._fuera_de_plazo(ahora)

    @property
    def en_plazo(self) -> Optional[bool]:
        """None mientras no se haya efectuado; después, si la fecha de la devolución no superó el límite."""
        return None if self.fecha_devolucion is None else not self._fuera_de_plazo(self.fecha_devolucion)


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
        # H-09 (SE-012): primer cierre sin realizar de cada solicitud: origen_id -> (fecha del cierre, Evento cancelado).
        self._cierres_sin_realizar: Dict[str, tuple] = {}
        # Decisión A: momento en que se cerró la contratación sin confirmar (None mientras no se haya cerrado).
        self.cierre_contratacion: Optional[datetime] = None

    # -- obligaciones
    def _crear(self, ob_id, concepto, importe, plazo, origen_id) -> ObligacionPago:
        existente = next((o for o in self.obligaciones.values() if o.concepto == concepto and o.origen_id == origen_id), None)
        if existente:
            return existente                                           # idempotencia en reintentos
        if ob_id in self.obligaciones:
            raise ErrorDominio("Ya existe otra obligación con ese identificador.")   # nunca se sobrescribe una obligación
        o = ObligacionPago(ob_id, concepto, importe, plazo, origen_id)
        self.obligaciones[ob_id] = o
        return o

    def registrar_obligacion_anticipo(self, ob_id: str, costo_total: Importe, fecha_firma: datetime) -> ObligacionPago:
        return self._crear(ob_id, CP.ANTICIPO, costo_total.porcentaje(PORCENTAJE_ANTICIPO),
                           PlazoPago.dias_habiles(fecha_firma, DIAS_HABILES_ANTICIPO), self.contrato_id)

    def registrar_obligacion_saldo_original(self, ob_id: str, costo_total: Importe, fecha_evento: datetime) -> ObligacionPago:
        anticipo = self.anticipo_aplicado()          # B-4: el excedente del anticipo no se aplica al saldo
        # la fecha del evento no se reprograma (BRD, fuera del alcance); límite exclusivo de GL-060 (decisión E-1)
        return self._crear(ob_id, CP.SALDO_CONTRATO_ORIGINAL, Importe(costo_total.cantidad - anticipo),
                           PlazoPago.dias_habiles_antes_de(fecha_evento, DIAS_HABILES_SALDO), self.contrato_id)

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
            plazo = PlazoPago.dias_habiles_antes_de(fecha_evento, DIAS_HABILES_SALDO)
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
        if o is None or (o.estado == EO.SIN_EFECTO and not self._anticipo_de_contratacion_cerrada(o)):
            raise ErrorDominio("La obligación no existe o quedó sin efecto.")
        if any(x.pago_id == pago_id for x in self.pagos):
            raise ErrorDominio("Ya existe otro pago con ese identificador.")          # nunca se sobrescribe un pago
        if any(x.obligacion_id == ob_id and x.comprobante == comprobante and x.estado != EPg.IMPORTE_INCORRECTO for x in self.pagos):
            # E-3/E-4: un pago no se cuenta dos veces; el reintento con el mismo comprobante no suma ni se devuelve dos veces
            raise ErrorDominio("Ya existe un pago registrado con ese comprobante para esta obligación.")
        p = Pago(pago_id, ob_id, importe, fecha, comprobante, registrado_en=registrado_en or fecha)
        if self._anticipo_de_contratacion_cerrada(o):
            # A-3: tras el cierre el pago se registra y puede verificarse sin reactivar la contratación ni la obligación;
            # el importe recibido se devuelve (A-1), por lo que ya no hay un importe que corregir.
            self.pagos.append(p)
            if verificado_externamente:
                self._verificar_anticipo_de_contratacion_cerrada(o, p, p.registrado_en)
            return p
        # Anticipo (B-1, E-3, E-4): el 30 % es el mínimo, no un importe exacto, y puede alcanzarse con varios pagos válidos
        # del mismo contrato. Un pago menor al mínimo ya no se rechaza como «Importe incorrecto»: queda Registrado o
        # Verificado como pago parcial y la obligación sigue Pendiente hasta que lo verificado la cubra (E-3). Con el
        # anticipo ya Liquidado, un pago menor es adicional: se verifica sin devolverse ni aplicarse al saldo (E-4).
        # «Importe incorrecto» se conserva solo para los pagos históricos y no se contabiliza.
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
        if self._anticipo_de_contratacion_cerrada(o):
            self._verificar_anticipo_de_contratacion_cerrada(o, p, verificado_en)
            return p
        if o.estado == EO.SIN_EFECTO:
            return self._verificar_pago_de_solicitud_cerrada(o, p, verificado_en)
        self._aplicar_verificacion(o, p, verificado_en, *self._destinos_verificacion(o, p))
        return p

    # -- decisión A: contratación cerrada sin confirmar
    def _anticipo_de_contratacion_cerrada(self, o: ObligacionPago) -> bool:
        return o.concepto == CP.ANTICIPO and self.cierre_contratacion is not None

    def _verificar_anticipo_de_contratacion_cerrada(self, o: ObligacionPago, p: Pago, verificado_en: datetime) -> None:
        """Verifica el pago sin tocar la obligación (Sin efecto o Liquidada se conservan, C-04) y registra su devolución."""
        destino_pago = MAQUINA_PAGO.transitar(p.estado, AccionPago.VERIFICAR)
        self._aplicar_verificacion(o, p, verificado_en, destino_pago, None)
        self._devolver_anticipo(p)

    def _devolver_anticipo(self, p: Pago) -> Optional[Devolucion]:
        """A-1: devuelve lo recibido como anticipo. Como máximo una devolución por pago (C-11): un reintento no la duplica."""
        if any(d.pago_id == p.pago_id for d in self.devoluciones):
            return None
        referencia = max(self.cierre_contratacion, p.registrado_en or p.fecha)      # A-6 (RN-42): la más tardía de las dos
        d = Devolucion(f"DV-{p.pago_id}", None, CP.ANTICIPO, p.importe, "Contratación cerrada sin confirmar (decisión A)",
                       self.cierre_contratacion, tipo=TipoDevolucion.ANTICIPO_CONTRATACION_CERRADA, pago_id=p.pago_id,
                       fecha_referencia=referencia)
        self.devoluciones.append(d)
        return d

    def aplicar_cierre_contratacion(self, fecha_cierre: datetime) -> List[Devolucion]:
        """Decisión A y C-04. Idempotente. El anticipo Pendiente queda Sin efecto y uno Liquidado conserva su estado; se
        devuelve cada pago de anticipo ya recibido (verificado o con importe incorrecto) y los pendientes de verificación
        se devolverán al verificarse. No reabre nada: el estado de Contrato y Evento no se modifican aquí."""
        if self.cierre_contratacion is not None:
            return []
        o = self._obligacion(CP.ANTICIPO)
        destino = (MAQUINA_OBLIGACION_PAGO.transitar(o.estado, AccionObligacionPago.DEJAR_SIN_EFECTO)
                   if o is not None and o.estado == EO.PENDIENTE else None)
        self.cierre_contratacion = fecha_cierre
        if o is None:
            return []
        if destino is not None:
            o.estado = destino
        nuevas = []
        for p in self.pagos:
            if p.obligacion_id == o.obligacion_id and p.estado in (EPg.VERIFICADO, EPg.IMPORTE_INCORRECTO):
                d = self._devolver_anticipo(p)
                if d is not None:
                    nuevas.append(d)
        return nuevas

    def anticipo_recibido_verificado(self) -> Decimal:
        """Dinero recibido como anticipo y verificado (distinto de lo aplicado a la obligación)."""
        o = self._obligacion(CP.ANTICIPO)
        return sum((p.importe.cantidad for p in self.pagos if o is not None and p.obligacion_id == o.obligacion_id
                    and p.estado == EPg.VERIFICADO), Decimal(0))

    def anticipo_aplicado(self) -> Decimal:
        """Parte del anticipo recibido que cubre la obligación: nunca más que su importe y solo si quedó Liquidada (B-2, B-4)."""
        o = self._obligacion(CP.ANTICIPO)
        if o is None or o.estado != EO.LIQUIDADA:
            return Decimal(0)
        return min(self.anticipo_recibido_verificado(), o.importe.cantidad)

    def anticipo_excedente(self) -> Decimal:
        """Lo recibido como anticipo por encima de lo aplicado: queda registrado, sin aplicación ni devolución automáticas (B-3, B-4)."""
        return self.anticipo_recibido_verificado() - self.anticipo_aplicado()

    def _verificar_pago_de_solicitud_cerrada(self, o: ObligacionPago, p: Pago, verificado_en: datetime) -> Pago:
        """H-09 (SE-012, CA-097, CA-098, GL-046): la solicitud se cerró sin realizarse con este pago registrado y todavía
        sin verificar. Si el Cliente lo efectuó a más tardar al cierre y el Evento no estaba cancelado, es un importe
        efectivamente recibido por la operación no realizada: Administración puede verificarlo después y, una vez
        verificado, se registra su devolución. La obligación sigue Sin efecto (no se cobra). Con el Evento cancelado se
        aplica la política de no reembolso y se conserva el rechazo anterior.
        La devolución conserva la fecha del cierre, como las demás (Devolucion.fecha_limite, texto de SE-012): si el plazo
        debe contarse desde la verificación es una decisión pendiente y no se resuelve aquí."""
        cierre = self._cierres_sin_realizar.get(o.origen_id)
        if cierre is None or cierre[1] or p.fecha > cierre[0]:
            raise ErrorDominio("La obligación quedó sin efecto.")
        destino_pago = MAQUINA_PAGO.transitar(p.estado, AccionPago.VERIFICAR)
        self._aplicar_verificacion(o, p, verificado_en, destino_pago, None)    # la obligación no transita
        self.devoluciones.append(Devolucion(f"DV-{p.pago_id}", o.origen_id, o.concepto, p.importe,
                                            "Operación no realizada (SE-012)", cierre[0]))
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
        # H-10 (BN-009, SE-010, CA-019, CA-026): el anticipo correcto y verificado queda Liquidado aunque se haya
        # efectuado después de los tres días hábiles. Pagar tarde no lo invalida: solo da lugar al contacto y a las
        # 24 horas naturales, que Contrato evalúa al confirmar o cerrar la contratación (sin cambios aquí).
        # D-2 (C-06 / ND-29, GL-049, CA-113, BN-005): un pago del saldo con fecha posterior a su límite no lo liquida directamente:
        # se verifica y cuenta para la regularización, pero la obligación sigue su curso (vencimiento y regularización). Decide la
        # fecha efectiva del pago, no la del registro ni la de la verificación. El anticipo (H-10) y el costo de una sustitución
        # concretada después del límite (GL-012) conservan su excepción.
        elif (o.plazo is None or not o.plazo.vencido(p.fecha)
              or o.concepto in (CP.SUSTITUCION_PROVEEDOR, CP.ANTICIPO)):
            pagado = self._pagado_para_liquidar(o) + p.importe.cantidad          # este pago todavía no está Verificado
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

    def _pagado_para_liquidar(self, o: ObligacionPago) -> Decimal:
        """Lo verificado que cuenta para liquidar `o`. En el saldo del contrato original (C-06, CA-113) solo cuenta lo efectuado
        dentro del plazo: un pago posterior al límite cuenta para la regularización, no para liquidar. En los demás conceptos
        cuenta todo lo verificado."""
        if o.concepto != CP.SALDO_CONTRATO_ORIGINAL or o.plazo is None:
            return self._pagado(o.obligacion_id)
        return sum((p.importe.cantidad for p in self.pagos if p.obligacion_id == o.obligacion_id and p.estado == EPg.VERIFICADO
                    and o.plazo.incluye(p.fecha)), Decimal(0))

    def importe_pagado(self, ob_id: str) -> Decimal:
        """Suma de los pagos Verificados de la obligación (solo lectura)."""
        return self._pagado(ob_id)

    def _anticipo_acumulado(self, estados, efectuado_hasta: Optional[datetime] = None) -> Decimal:
        """Suma de los pagos del anticipo del contrato en los `estados` indicados, efectuados a más tardar en `efectuado_hasta`
        (E-3). Cada pago cuenta una vez; «Importe incorrecto» (histórico) y los pagos de otras obligaciones no cuentan."""
        o = self._obligacion(CP.ANTICIPO)
        return sum((p.importe.cantidad for p in self.pagos if o is not None and p.obligacion_id == o.obligacion_id
                    and p.estado in estados and (efectuado_hasta is None or p.fecha <= efectuado_hasta)), Decimal(0))

    def _anticipo_cubierto(self, estados, efectuado_hasta: Optional[datetime] = None) -> bool:
        o = self._obligacion(CP.ANTICIPO)
        return o is not None and self._anticipo_acumulado(estados, efectuado_hasta) >= o.importe.cantidad

    def anticipo_verificado(self, efectuado_hasta: Optional[datetime] = None) -> bool:
        """Los pagos Verificados del anticipo suman al menos el mínimo (E-3). Con `efectuado_hasta` solo cuentan los que el
        Cliente efectuó a más tardar en esa fecha (BN-009)."""
        return self._anticipo_cubierto((EPg.VERIFICADO,), efectuado_hasta)

    def anticipo_efectuado_hasta(self, limite: datetime) -> bool:
        """Los pagos efectuados por el Cliente a más tardar en `limite` suman el mínimo, aunque estén pendientes de
        verificación (E-3). Un pago parcial no evita el cierre por falta de anticipo."""
        return self._anticipo_cubierto((EPg.REGISTRADO, EPg.VERIFICADO), limite)

    def _pago_pendiente_de_verificacion(self, ob_ids, hasta: datetime, plazo: Optional[PlazoPago] = None) -> bool:
        """Pago efectuado a más tardar en `hasta` (o dentro de `plazo`, si se indica) que Administración registró y todavía no verifica."""
        return any(p.obligacion_id in ob_ids and p.estado == EPg.REGISTRADO
                   and (plazo.incluye(p.fecha) if plazo is not None else p.fecha <= hasta) for p in self.pagos)

    def anticipo_recibido(self) -> bool:
        """Lo registrado o verificado como anticipo cubre el mínimo (E-3); un pago parcial no basta."""
        return self._anticipo_cubierto((EPg.REGISTRADO, EPg.VERIFICADO))

    def obligacion_liquidada(self, ob_id: Optional[str]) -> bool:
        return bool(ob_id) and self.obligaciones[ob_id].estado == EO.LIQUIDADA

    def obligacion_vencida_sin_pago(self, ob_id: str, ahora: datetime) -> bool:
        """El plazo del Cliente para pagar venció y no hay un pago efectuado dentro de él: ni liquidado ni pendiente de
        verificación. La demora de Administración al registrar o verificar no es falta de pago."""
        o = self.obligaciones[ob_id]
        return (o.plazo.vencido(ahora) and o.estado != EO.LIQUIDADA
                and not self._pago_pendiente_de_verificacion({ob_id}, o.plazo.vence, o.plazo))

    # -- obligaciones de una misma solicitud (E3G: un cambio puede tener varias, una por concepto; BN-005)
    def obligaciones_de(self, origen_id: str) -> List[ObligacionPago]:
        """Obligaciones cuyo origen es la solicitud, en el orden en que se crearon (solo lectura)."""
        return [o for o in self.obligaciones.values() if o.origen_id == origen_id]

    def solicitud_liquidada(self, origen_id: str) -> bool:
        """Todas las obligaciones vigentes de la solicitud están Liquidadas; el pago de un concepto no liquida otro."""
        vigentes = [o for o in self.obligaciones_de(origen_id) if o.estado != EO.SIN_EFECTO]
        return bool(vigentes) and all(o.estado == EO.LIQUIDADA for o in vigentes)

    def solicitud_vencida_sin_pago(self, origen_id: str, ahora: datetime) -> bool:
        """Alguna obligación pendiente de la solicitud venció sin un pago efectuado dentro de su plazo (BN-003, CA-067)."""
        return any(o.estado == EO.PENDIENTE and o.plazo is not None and self.obligacion_vencida_sin_pago(o.obligacion_id, ahora)
                   for o in self.obligaciones_de(origen_id))

    # -- saldo vencido y regularización (BN-005)
    def _saldo_general(self) -> List[ObligacionPago]:
        """Saldo del contrato original más los importes de sustitución integrados con el plazo ordinario."""
        return [o for o in self.obligaciones.values()
                if o.concepto == CP.SALDO_CONTRATO_ORIGINAL or (o.concepto == CP.SUSTITUCION_PROVEEDOR and o.plazo is not None)]

    def registrar_vencimiento_saldo(self, ahora: datetime) -> bool:
        vencen = [o for o in self._saldo_general()
                  if o.estado == EO.PENDIENTE and o.plazo is not None and o.plazo.vencido(ahora) and self._pagado_para_liquidar(o) < o.importe.cantidad
                  and not self._pago_pendiente_de_verificacion({o.obligacion_id}, o.plazo.vence, o.plazo)]   # pagado a tiempo, sin verificar aún
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

    def saldo_vencido_en(self, ahora: datetime) -> bool:
        """GL-049 / SE-006: el saldo está vencido de HECHO cuando su plazo de liquidación terminó sin que lo pagado dentro del plazo lo
        cubra (la fecha efectiva del pago manda, BN-005); no depende de que ya se haya registrado el vencimiento. Mientras exista, no se
        tramitan nuevas solicitudes. Los pagos a tiempo pendientes de verificación no lo vencen (la demora de Administración no es falta
        de pago). Mismo criterio que `registrar_vencimiento_saldo`; incluye el saldo ya registrado como `Vencida`."""
        return any(o.estado == EO.VENCIDA or (
            o.estado == EO.PENDIENTE and o.plazo is not None and o.plazo.vencido(ahora)
            and self._pagado_para_liquidar(o) < o.importe.cantidad
            and not self._pago_pendiente_de_verificacion({o.obligacion_id}, o.plazo.vence, o.plazo))
            for o in self._saldo_general())

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
        self._cierres_sin_realizar.setdefault(origen_id, (fecha_cierre, evento_cancelado))   # H-09: primer cierre
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
        d = next((d for d in self.devoluciones if d.devolucion_id == devolucion_id), None)
        if d is None:
            raise ErrorDominio("La devolución no existe.")                             # AR-08: error de dominio, no StopIteration
        if MAQUINA_DEVOLUCION.es_repeticion(d.estado, AccionDevolucion.REGISTRAR_EFECTUADA):
            return                                     # ya Efectuada: sin segunda devolución ni DevolucionRegistrada
        destino = MAQUINA_DEVOLUCION.transitar(d.estado, AccionDevolucion.REGISTRAR_EFECTUADA)
        d.estado, d.fecha_devolucion, d.comprobante = destino, fecha, comprobante
        self._registrar(DevolucionRegistrada(self.id, fecha, devolucion_id=devolucion_id))
