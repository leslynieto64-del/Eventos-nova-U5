/* Sesión de la persona que usa la aplicación. La cookie de sesión es HttpOnly (el JavaScript no la ve ni la guarda); aquí solo se conserva en memoria
   lo que informa el servidor: quién es, qué rol tiene y el token CSRF. Nada de esto se guarda en localStorage. Los permisos que se usan para ocultar
   botones son solo comodidad: el servidor vuelve a comprobarlos en cada operación. */
import { GET, POST, ErrorApi, fijarCsrf } from './api.js';

export const estado = { cargada: false, activa: true, usuario: null, permisos: new Set() };
export const ETIQUETA_ROL = { administrador: 'Administración', coordinador: 'Coordinación', proveedor: 'Proveedor' };

function aplicar(datos) {
  estado.cargada = true;
  estado.activa = datos.autenticacionActiva !== false;
  estado.usuario = datos.usuario || null;
  estado.permisos = new Set(datos.permisos || []);
  fijarCsrf(datos.csrf || null);
}

/** Pregunta al servidor si hay una sesión vigente. Sin sesión deja `usuario` en null. */
export async function cargar() {
  try { aplicar((await GET('/auth/yo')).datos); } catch (e) {
    if (e instanceof ErrorApi && e.tipo === 'sesion') { estado.cargada = true; estado.usuario = null; estado.permisos = new Set(); fijarCsrf(null); } else throw e;
  }
}

export async function iniciar(correo, contrasena) { aplicar((await POST('/auth/inicio-sesion', { correo, contrasena })).datos); }

export async function cerrar() {
  try { await POST('/auth/cierre-sesion'); } catch { /* la sesión ya no existía: el resultado es el mismo */ }
  estado.usuario = null; estado.permisos = new Set(); fijarCsrf(null);
}

export function olvidar() { estado.usuario = null; estado.permisos = new Set(); fijarCsrf(null); }

export const rol = () => (estado.usuario ? estado.usuario.rol : null);
/** ¿La cuenta actual tiene ALGUNO de los permisos indicados (texto con espacios o lista)? Sin autenticación activa (solo desarrollo) todo se muestra. */
export function puede(permisos) {
  if (!estado.activa) return true;
  if (!permisos) return true;
  const lista = Array.isArray(permisos) ? permisos : String(permisos).split(/\s+/).filter(Boolean);
  return lista.some((p) => estado.permisos.has(p));
}
export const requiereIngreso = () => estado.activa && !estado.usuario;
