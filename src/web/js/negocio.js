/* Presentación de datos de negocio: fechas sin conversión de zona horaria, importes exactos y tonos de estado.
   Ninguna regla de negocio se calcula aquí: solo se formatea lo que devuelve la API. */

export const ZONA_NEGOCIO = 'America/Mexico_City';
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/** Hora de pared de la zona de negocio, sin zona, en formato «AAAA-MM-DDTHH:MM:SS» (igual que el reloj del servidor). */
export function ahoraNegocio() {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: ZONA_NEGOCIO, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}

export const sumarDias = (iso, dias) => {
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(a, m - 1, d + dias)).toISOString().slice(0, 10);
};

/** «2026-11-20T18:00:00» → «20 nov 2026, 18:00». No pasa por Date: no hay desplazamiento horario. */
export function fmtFechaHora(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(iso || '');
  if (!m) return iso || '—';
  const base = `${Number(m[3])} ${MESES[Number(m[2]) - 1]} ${m[1]}`;
  return m[4] !== undefined ? `${base}, ${m[4]}:${m[5]}` : base;
}
export const fmtFecha = (iso) => (iso ? fmtFechaHora(iso.slice(0, 10)) : '—');

/** Importe decimal exacto (cadena de la API) con separador de miles; sin símbolo: la API no declara moneda. */
export function fmtImporte(valor) {
  if (valor === null || valor === undefined || valor === '') return '—';
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(valor));
  if (!m) return String(valor);
  const entero = m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${m[1]}${entero}.${(m[3] || '').padEnd(2, '0')}`;
}

/** Tono visual de un estado oficial. El texto del estado nunca se cambia. */
const TONOS = {
  ok: ['Contratación confirmada', 'Confirmada', 'Confirmado por el proveedor', 'Aceptada', 'Liquidada', 'Verificado', 'Efectuada',
    'Finalizado', 'En ejecución', 'En organización', 'Procedente', 'Firmado'],
  aviso: ['En gestión', 'En preparación', 'Registrada', 'Registrado', 'Pendiente', 'Pendiente de confirmación del proveedor',
    'En revisión del Cliente', 'En elaboración', 'En búsqueda de proveedor', 'En búsqueda de alternativa', 'Sin proveedor asignado',
    'Pendiente de aprobación del Cliente', 'Pendiente de autorización', 'Pendiente de formalización', 'Pendiente de pago',
    'Autorizada', 'En evaluación'],
  error: ['Vencida', 'Cancelado', 'Cerrado sin contratación', 'Cerrado sin confirmar', 'No procedente', 'Rechazada por el Cliente',
    'No autorizada', 'No aprobada', 'No se realizará', 'Importe incorrecto', 'Proveedor no disponible', 'Detenida por saldo vencido',
    'Cerrada por falta de pago', 'Cerrada por inicio del evento', 'Cerrada por evento cancelado', 'Cerrada por no aceptación',
    'Rechazada por inicio del evento'],
};
export function tono(estado) {
  for (const [t, lista] of Object.entries(TONOS)) if (lista.includes(estado)) return t;
  return 'neutro';
}

/** Explicaciones breves (no sustituyen al estado oficial) para personas sin conocimientos técnicos. */
export const AYUDA_ESTADO = {
  'No procedente': 'La solicitud se registró, pero no cumple un requisito del proceso (por ejemplo, el plazo, o que el evento ya inició).',
  'Cerrada por inicio del evento': 'La solicitud seguía en trámite cuando el evento inició, por eso se cerró sin confirmarse.',
  'Cerrada por evento cancelado': 'La solicitud se cerró porque el evento fue cancelado.',
  'Cerrada por falta de pago': 'No se recibió el pago dentro del plazo y la solicitud se cerró.',
  'Detenida por saldo vencido': 'El saldo del contrato original está vencido; la solicitud espera a que se regularice.',
  'Cerrado sin contratación': 'Llegó la fecha del evento sin contratación confirmada; el evento no continúa.',
  'Cerrado sin confirmar': 'El contrato se cerró sin confirmarse y no se reabre.',
  'En gestión': 'El evento está en propuesta y contratación.',
  'En organización': 'La contratación está confirmada y el evento se organiza.',
  'En ejecución': 'El evento ya inició.',
  'Vencida': 'El plazo de pago terminó sin que se cubriera el importe.',
  'Sin efecto': 'La obligación ya no se cobra.',
};
