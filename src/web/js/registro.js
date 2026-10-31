/* Registro local (solo en este navegador) de identificadores que la API devuelve al crear algo pero no vuelve a ofrecer en
   ninguna consulta: propuestas (no hay GET de propuestas) y pagos (la consulta de pagos no incluye su identificador).
   NO es información oficial del sistema: se rotula como tal en la interfaz y el backend valida siempre. */

const CLAVE = 'eventosnova.registro.v1';

function leer() {
  try { return JSON.parse(localStorage.getItem(CLAVE)) || { propuestas: {}, pagos: {}, eventos: {} }; } catch { return { propuestas: {}, pagos: {}, eventos: {} }; }
}
function guardar(r) { try { localStorage.setItem(CLAVE, JSON.stringify(r)); } catch { /* sin almacenamiento: la interfaz sigue funcionando */ } }

export const registro = {
  propuestas(eventoId) { return Object.values(leer().propuestas).filter((p) => !eventoId || p.eventoId === eventoId); },
  propuesta(id) { return leer().propuestas[id] || null; },
  guardarPropuesta(p) { const r = leer(); r.propuestas[p.id] = { ...(r.propuestas[p.id] || {}), ...p }; guardar(r); },
  pagos(estadoCuentaId) { return Object.values(leer().pagos).filter((p) => !estadoCuentaId || p.estadoCuentaId === estadoCuentaId); },
  guardarPago(p) { const r = leer(); r.pagos[p.pagoId] = { ...(r.pagos[p.pagoId] || {}), ...p }; guardar(r); },
  eventosRecientes() { return Object.values(leer().eventos).sort((a, b) => (b.visto || '').localeCompare(a.visto || '')).slice(0, 8); },
  recordarEvento(id, nombre) { const r = leer(); r.eventos[id] = { id, nombre, visto: new Date().toISOString() }; guardar(r); },
};
