"""Resultados esperados DERIVADOS DE LAS REGLAS para comparar con el oráculo histórico `comportamiento_estado_cuenta_v8_e3c.json`.

El oráculo es la referencia histórica inmutable (no se edita ni se regenera). Para cada clave `variante | operación`, el esperado es la
entrada del oráculo con SOLO los cambios que ordenan las decisiones aprobadas o adoptadas; todo lo demás debe ser idéntico. Este
módulo NO importa código de producción: usa solo datos del oráculo y aritmética propia, de modo que un error del dominio no pueda
"autoconfirmarse".

Reglas (cada una declara exactamente qué cambia):

E-1  GL-060 / C-15. Los plazos en días hábiles (anticipo +3 días hábiles tras el inicio; saldo y sustitución -3 días hábiles antes del
     evento) vencen a las 00:00 del día siguiente al último día del plazo. El calendario se calcula aquí con una fórmula cerrada por
     semanas (no con el bucle del dominio). No cambia ningún otro dato; los plazos de horas (no presentes en el oráculo) no cambian.
H-10 Un anticipo verificado por al menos su importe, aunque tardío, deja OB-A Liquidada (y figura en `liquidadas`, no en
     `vencidas_sin_pago`). Solo cambian esos tres datos, y solo donde OB-A estaba Pendiente en el oráculo.
E-3  Un pago de anticipo menor al mínimo es parcial: queda Verificado (no «Importe incorrecto») con `verificado_en` = su registro, y
     cuenta para el acumulado. Afecta a (a) la variante `anticipo_importe_incorrecto`, cuyo pago de 1000 se construye con ese pago, y
     (b) la operación `pagar(OB-A, 1000, importe_incorrecto)` sobre cualquier variante.
E-4  Con el anticipo ya Liquidado ese mismo pago de 1000 se verifica como adicional: no cambia OB-A, no se devuelve ni se aplica al saldo.
     Es el caso (b) sobre las variantes cuyo OB-A ya estaba Liquidado.
D-2  C-06 / ND-29, GL-049, CA-113, BN-005 (decisión aplicada el 28/10/2026): un pago del saldo (OB-S) con fecha posterior a su límite
     no lo liquida directamente. En el oráculo, el pago de 7000 `despues_limite`, `dentro_ventana` o `despues_ventana` dejaba OB-S
     Liquidada cuando estaba Pendiente (grupo R12 del cierre de alcance §8, 48 claves). Ahora: OB-S sigue Pendiente (el pago se verifica
     igual), sale de `liquidadas` y, salvo que haya un pago a tiempo pendiente de verificación, entra en `vencidas_sin_pago`
     (el plazo terminó sin pago a tiempo, GL-049). Solo se aplica donde OB-S estaba Liquidada únicamente por ese pago tardío.
Efectos derivados, calculados desde los pagos esperados (no copiados del resultado actual):
     pagos_realizados = suma de los pagos Verificados; anticipo_verificado[_hasta_plazo] = verificados (efectuados hasta el plazo) ≥ importe;
     anticipo_efectuado_hasta_plazo / anticipo_recibido = registrados + verificados ≥ importe; evento PagoVerificado por cada pago
     parcial nuevo verificado; y, si una operación SE-012 cierra la solicitud de origen del anticipo (CT-1) sin cancelar el Evento,
     la devolución del importe recibido (regla SE-012 del dominio: se devuelve lo verificado de la obligación cerrada).
"""
import copy
from datetime import date, datetime, timedelta
from decimal import Decimal

OPERACION_PARCIAL = 'pagar(OB-A, 1000, importe_incorrecto)'
VARIANTE_PARCIAL = 'anticipo_importe_incorrecto'
H10_VARIANTE = 'anticipo_tardio_verificado'
H10_OPERACION = 'pagar(OB-A, 3000, tardio)'
H10_VARIANTES_CON_OPERACION = ('anticipo_pendiente', 'anticipo_importe_incorrecto', 'anticipo_registrado_sin_verificar')
CIERRE_ANTICIPO_SIN_CANCELAR = 'aplicar_cierre_sin_realizar(CT-1, evento_cancelado=False)'
PLAZO_CONSULTADO = datetime(2026, 11, 5, 10, 0)           # fecha con la que el arnés evalúa los «hasta_plazo» (ver `observar`)
CIERRE_SE012 = '2026-11-14T09:00:00'                       # fecha de cierre que usa el arnés en `aplicar_cierre_sin_realizar`
ADELANTE, ATRAS = {'ANTICIPO'}, {'SALDO_CONTRATO_ORIGINAL', 'SUSTITUCION_PROVEEDOR'}
D2_OPERACIONES = ('pagar(OB-S, 7000, despues_limite)', 'pagar(OB-S, 7000, dentro_ventana)', 'pagar(OB-S, 7000, despues_ventana)')
CONSULTA = datetime(2026, 11, 19, 12, 0)                    # fecha con la que el arnés evalúa `vencidas_sin_pago` (ver `observar`)


# ---------------------------------------------------------------- calendario de referencia (E-1), independiente del dominio
def dia_habil_posterior(dia: date, n: int) -> date:
    """El n-ésimo día hábil (lunes a viernes) posterior a `dia`; el día de partida no cuenta. Fórmula por semanas."""
    w = dia.weekday()
    if w >= 5:                                      # sábado o domingo: equivale a partir del viernes anterior
        dia, w = dia - timedelta(days=w - 4), 4
    semanas, resto = divmod(w + n, 5)
    return dia + timedelta(days=7 * semanas + resto - w)


def dia_habil_anterior(dia: date, n: int) -> date:
    """El n-ésimo día hábil anterior a `dia`; el día de partida no cuenta."""
    w = dia.weekday()
    if w >= 5:                                      # fin de semana: equivale a partir del lunes siguiente
        dia, w = dia + timedelta(days=7 - w), 0
    semanas, resto = divmod(w - n, 5)               # divmod entero con piso: lo que cae antes del lunes retrocede semanas
    return dia + timedelta(days=7 * semanas + resto - w)


def limite_gl060(concepto: str, inicio: datetime) -> datetime:
    """00:00 del día siguiente al último día del plazo de 3 días hábiles (anticipo: después; saldo y sustitución: antes del evento)."""
    ultimo = dia_habil_posterior(inicio.date(), 3) if concepto in ADELANTE else dia_habil_anterior(inicio.date(), 3)
    return datetime.combine(ultimo + timedelta(days=1), datetime.min.time())


# ---------------------------------------------------------------- predicados de las reglas (por clave)
def partir(clave: str):
    variante, operacion = clave.split(' | ')
    return variante, operacion


def afecta_e3_e4_fixture(clave: str) -> bool:
    return partir(clave)[0] == VARIANTE_PARCIAL


def afecta_e3_e4_operacion(clave: str, ref: dict) -> bool:
    return partir(clave)[1] == OPERACION_PARCIAL and 'error' not in ref


def afecta_e3_e4(clave: str, ref: dict) -> bool:
    return afecta_e3_e4_fixture(clave) or afecta_e3_e4_operacion(clave, ref)


def candidata_h10(clave: str) -> bool:
    variante, operacion = partir(clave)
    return variante == H10_VARIANTE or (operacion == H10_OPERACION and variante in H10_VARIANTES_CON_OPERACION)


def _suma(pagos, estados, hasta=None) -> Decimal:
    return sum((Decimal(p[2]) for p in pagos if p[1] == 'OB-A' and p[5] in estados
                and (hasta is None or datetime.fromisoformat(p[3]) <= hasta)), Decimal(0))


def _texto(d: Decimal) -> str:
    return str(d.normalize()) if d != d.to_integral() else str(int(d))


# ---------------------------------------------------------------- esperado
def esperado(clave: str, ref: dict):
    """(esperado, reglas): `reglas` es el conjunto de reglas que modificaron la entrada del oráculo para esta clave."""
    e, reglas = copy.deepcopy(ref), set()
    variante, operacion = partir(clave)

    # --- E-3 / E-4: pagos parciales de anticipo
    if afecta_e3_e4(clave, ref):
        reglas.add('E-3/E-4')
        pagos = e['pagos']
        nuevos = []
        if afecta_e3_e4_fixture(clave):
            nuevos.append(next(p for p in pagos if p[0] == 'PG-1'))                       # el pago de 1000 de la variante
        if afecta_e3_e4_operacion(clave, ref):
            nuevos.append(pagos[-1])                                                       # el pago que agrega la operación
        for p in nuevos:
            assert p[1] == 'OB-A' and p[2] == '1000' and p[5] == 'IMPORTE_INCORRECTO', (clave, p)
            p[5], p[7] = 'VERIFICADO', p[6]                                                # parcial válido, verificado al registrarse
        if afecta_e3_e4_operacion(clave, ref):
            p = nuevos[-1]
            e['eventos'].append(['PagoVerificado', ['agregado_id', 'EC-1'], ['concepto', 'Anticipo'], ['obligacion_id', 'OB-A'],
                                 ['ocurrido_en', p[6]], ['origen_id', 'CT-1']])
        importe = Decimal(e['obligaciones']['OB-A'][1])
        c = e['consultas']
        c['pagos_realizados'] = _texto(sum((Decimal(p[2]) for p in pagos if p[5] == 'VERIFICADO'), Decimal(0)))
        c['anticipo_verificado'] = _suma(pagos, {'VERIFICADO'}) >= importe
        c['anticipo_verificado_hasta_plazo'] = _suma(pagos, {'VERIFICADO'}, PLAZO_CONSULTADO) >= importe
        c['anticipo_efectuado_hasta_plazo'] = _suma(pagos, {'REGISTRADO', 'VERIFICADO'}, PLAZO_CONSULTADO) >= importe
        c['anticipo_recibido'] = _suma(pagos, {'REGISTRADO', 'VERIFICADO'}) >= importe
        # liquidación: solo si lo verificado cubre el importe (E-3); donde esto cambia el estado de OB-A lo fija H-10 (abajo)
        ob = e['obligaciones']['OB-A']
        cubre = _suma(pagos, {'VERIFICADO'}) >= importe
        assert not (cubre and ob[4] == 'PENDIENTE') or candidata_h10(clave), (clave, 'E-3 liquidaría OB-A fuera de H-10')
        if afecta_e3_e4_fixture(clave) and operacion == CIERRE_ANTICIPO_SIN_CANCELAR:
            # SE-012: el pago verificado de la obligación cerrada se devuelve; el Evento no está cancelado
            assert not e['devoluciones'] and e['devuelve'] == [], clave
            e['devoluciones'] = [['DV-1', 'CT-1', 'ANTICIPO', '1000', 'Operación no realizada (SE-012)', CIERRE_SE012,
                                  'PENDIENTE', None, None]]
            e['devuelve'] = [['Devolucion', 'DV-1']]

    # --- H-10: OB-A Liquidada cuando lo verificado la cubre, aunque el pago fuera tardío
    ob = e['obligaciones'].get('OB-A')
    # En el oráculo OB-A figuraba Pendiente, o Sin efecto solo cuando la operación es el cierre SE-012 del origen CT-1 (que deja Sin efecto
    # los cobros Pendientes); con H-10 ya estaba Liquidada antes de esa operación y el cierre no la cambia.
    estados_previos = ('PENDIENTE', 'SIN_EFECTO') if operacion.startswith('aplicar_cierre_sin_realizar(CT-1') else ('PENDIENTE',)
    if candidata_h10(clave) and ob is not None and ob[4] in estados_previos and _suma(e['pagos'], {'VERIFICADO'}) >= Decimal(ob[1]):
        reglas.add('H-10')
        ob[4] = 'LIQUIDADA'
        e['consultas']['liquidadas'] = sorted(set(e['consultas']['liquidadas']) | {'OB-A'})
        e['consultas']['vencidas_sin_pago'] = [i for i in e['consultas']['vencidas_sin_pago'] if i != 'OB-A']

    # --- E-1: nuevo límite de los plazos en días hábiles
    for datos in e['obligaciones'].values():
        concepto, plazo = datos[0], datos[2]
        if plazo is not None and (concepto in ADELANTE or concepto in ATRAS):
            nuevo = limite_gl060(concepto, datetime.fromisoformat(plazo[0])).isoformat()
            if nuevo != plazo[1]:
                reglas.add('E-1')
            plazo[1] = nuevo
    # --- D-2: el pago tardío del saldo ya no lo liquida
    ob = e['obligaciones'].get('OB-S')
    if (ob is not None and ob[4] == 'LIQUIDADA' and operacion in D2_OPERACIONES and 'error' not in ref and e['pagos']
            and e['pagos'][-1][1] == 'OB-S' and e['pagos'][-1][5] == 'VERIFICADO'
            and not e.get('resultado_regularizacion')):          # un saldo ya regularizado quedó Liquidada por la regularización (CA-027)
        limite = datetime.fromisoformat(ob[2][1])
        ultimo = e['pagos'][-1]
        previos_en_plazo = sum((Decimal(p[2]) for p in e['pagos'][:-1] if p[1] == 'OB-S' and p[5] == 'VERIFICADO'
                                and datetime.fromisoformat(p[3]) < limite), Decimal(0))
        if datetime.fromisoformat(ultimo[3]) >= limite and previos_en_plazo < Decimal(ob[1]):
            reglas.add('D-2')
            ob[4] = 'PENDIENTE'
            c = e['consultas']
            c['liquidadas'] = [i for i in c['liquidadas'] if i != 'OB-S']
            pendiente_a_tiempo = any(p[1] == 'OB-S' and p[5] == 'REGISTRADO' and datetime.fromisoformat(p[3]) < limite for p in e['pagos'])
            if not pendiente_a_tiempo and limite <= CONSULTA:
                c['vencidas_sin_pago'] = sorted(set(c['vencidas_sin_pago']) | {'OB-S'})
    return e, reglas
