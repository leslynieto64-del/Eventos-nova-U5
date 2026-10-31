/* Acceso centralizado a la API de Eventos Nova (mismo origen). Normaliza los errores para que la interfaz los explique. */
import { humanizar } from './texto.js';

let tokenCsrf = null;
/** El token CSRF lo entrega el servidor al iniciar sesión; se guarda solo en memoria y se envía en las operaciones que modifican datos. */
export const fijarCsrf = (t) => { tokenCsrf = t; };

const BASE = (document.querySelector('meta[name="api-base"]')?.content || '').replace(/\/$/, '');

export class ErrorApi extends Error {
  /** tipo: conexion | negocio | validacion | no_encontrado | conflicto | servidor */
  constructor(tipo, mensaje, { estado = 0, pendientes = [], campos = [], crudo = null } = {}) {
    super(mensaje);
    this.tipo = tipo; this.estado = estado; this.pendientes = pendientes; this.campos = campos; this.crudo = crudo;
  }
}

function construirUrl(ruta, consulta) {
  const partes = Object.entries(consulta || {}).filter(([, v]) => v !== undefined && v !== null && v !== '');
  const qs = partes.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
  return BASE + ruta + (qs ? `?${qs}` : '');
}

function traducirValidacion(detalle) {
  // FastAPI: [{loc: ['body','campo'], msg: '...'}]
  return detalle.map((d) => ({ campo: (d.loc || []).filter((x) => x !== 'body' && x !== 'query').join('.'), mensaje: d.msg }));
}

export async function api(metodo, ruta, { consulta, cuerpo } = {}) {
  let respuesta;
  try {
    respuesta = await fetch(construirUrl(ruta, consulta), {
      method: metodo,
      headers: {
        Accept: 'application/json',
        ...(cuerpo !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(metodo !== 'GET' && tokenCsrf ? { 'X-CSRF-Token': tokenCsrf } : {}),
      },
      credentials: 'same-origin',
      body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
    });
  } catch (e) {
    throw new ErrorApi('conexion', 'No fue posible conectar con el sistema. Comprueba que el servidor esté funcionando e inténtalo nuevamente.');
  }
  let datos = null;
  const texto = await respuesta.text();
  if (texto) { try { datos = JSON.parse(texto); } catch { datos = null; } }
  if (respuesta.ok) return datos;

  const estado = respuesta.status;
  if (estado === 401) {                         // sin sesión, caducada o cerrada: la interfaz vuelve a pedir el ingreso
    const mensaje = humanizar(datos && datos.detalle) || 'Tu sesión ya no es válida. Inicia sesión nuevamente.';
    if (ruta !== '/auth/inicio-sesion' && ruta !== '/auth/yo') window.dispatchEvent(new CustomEvent('sesion-expirada', { detail: mensaje }));
    throw new ErrorApi('sesion', mensaje, { estado, crudo: datos });
  }
  if (estado === 403) throw new ErrorApi('permiso', humanizar(datos && datos.detalle) || 'No tienes permiso para realizar esta operación.', { estado, crudo: datos });
  if (estado === 429) throw new ErrorApi('bloqueo', humanizar(datos && datos.detalle) || 'Demasiados intentos. Espera unos minutos e inténtalo de nuevo.', { estado, crudo: datos });
  if (estado === 422 && datos && Array.isArray(datos.detail)) {
    const campos = traducirValidacion(datos.detail);
    throw new ErrorApi('validacion', 'Hay datos que el sistema no pudo aceptar. Revisa los campos señalados.', { estado, campos, crudo: datos });
  }
  if (estado === 422 && datos && datos.detalle) {
    // El motivo se muestra sin referencias internas a requisitos; el texto original queda en «Detalles técnicos» (crudo).
    throw new ErrorApi('negocio', humanizar(datos.detalle), { estado, pendientes: (datos.pendientes || []).map(humanizar), crudo: datos });
  }
  if (estado === 404) {
    throw new ErrorApi('no_encontrado', humanizar(datos && datos.detalle) || 'No se encontró el registro solicitado.', { estado, crudo: datos });
  }
  if (estado === 409) {
    throw new ErrorApi('conflicto', humanizar(datos && datos.detalle) || 'La operación entra en conflicto con el estado actual de los datos.', { estado, crudo: datos });
  }
  throw new ErrorApi('servidor', 'No fue posible completar la operación. No se han confirmado los cambios. Revisa la información e inténtalo nuevamente si corresponde.',
    { estado, crudo: datos });
}

export const GET = (ruta, consulta) => api('GET', ruta, { consulta });
export const POST = (ruta, cuerpo) => api('POST', ruta, { cuerpo: cuerpo === undefined ? {} : cuerpo });
