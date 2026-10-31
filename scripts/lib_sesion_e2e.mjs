// Ayuda de las pruebas de extremo a extremo con autenticación: sesiones HTTP de Node (cookie + token CSRF) y cuentas de prueba.
// Requiere una cuenta de administrador EXISTENTE (créela con scripts/crear_administrador.py) cuyas credenciales se pasan por variables de entorno:
//   EVENTOSNOVA_E2E_ADMIN_CORREO, EVENTOSNOVA_E2E_ADMIN_CLAVE
// A partir de ella crea, por la API, una cuenta de coordinador de prueba con contraseña aleatoria. Las contraseñas no se imprimen ni se guardan.
import { randomBytes } from 'node:crypto';

export class Sesion {
  constructor(base) { this.base = base; this.cookie = ''; this.csrf = ''; this.datos = null; }

  async entrar(correo, clave) {
    const r = await fetch(this.base + '/auth/inicio-sesion', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ correo, contrasena: clave }) });
    const cuerpo = await r.json();
    if (!r.ok) throw new Error(`inicio de sesión rechazado (${r.status}): ${cuerpo.detalle}`);
    this.cookie = r.headers.getSetCookie().map((c) => c.split(';')[0]).join('; ');
    this.csrf = cuerpo.datos.csrf; this.datos = cuerpo.datos;
    return this;
  }

  /** fetch con la cookie de sesión y, en las operaciones que modifican datos, el token CSRF. Acepta rutas relativas o con la base. */
  fetch(ruta, opciones = {}) {
    const url = ruta.startsWith('http') ? ruta : this.base + ruta;
    const metodo = (opciones.method || 'GET').toUpperCase();
    const cabeceras = { Cookie: this.cookie, ...(opciones.body ? { 'Content-Type': 'application/json' } : {}), ...(metodo !== 'GET' ? { 'X-CSRF-Token': this.csrf } : {}), ...(opciones.headers || {}) };
    return fetch(url, { ...opciones, headers: cabeceras });
  }

  async json(metodo, ruta, cuerpo) {
    const r = await this.fetch(ruta, { method: metodo, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
    const t = await r.json();
    if (!r.ok) throw new Error(`${metodo} ${ruta} -> ${r.status} ${JSON.stringify(t)}`);
    return t;
  }
}

/** Inicia sesión como administrador (variables de entorno) y crea un coordinador de prueba. Devuelve las sesiones y las credenciales del coordinador para escribirlas en la interfaz. */
export async function prepararCuentas(base, marca) {
  const correoAdmin = process.env.EVENTOSNOVA_E2E_ADMIN_CORREO; const claveAdmin = process.env.EVENTOSNOVA_E2E_ADMIN_CLAVE;
  if (!correoAdmin || !claveAdmin) throw new Error('Defina EVENTOSNOVA_E2E_ADMIN_CORREO y EVENTOSNOVA_E2E_ADMIN_CLAVE (cuenta de administrador existente).');
  const admin = await new Sesion(base).entrar(correoAdmin, claveAdmin);
  const correoCoord = `coord.${marca.toLowerCase()}@eventosnova.example`; const claveCoord = 'Coord-' + randomBytes(12).toString('base64url');
  await admin.json('POST', '/usuarios', { correo: correoCoord, nombre: `Coordinación de prueba ${marca}`, rol: 'coordinador', contrasena: claveCoord });
  const coord = await new Sesion(base).entrar(correoCoord, claveCoord);
  return { admin, coord, correoAdmin, claveAdmin, correoCoord, claveCoord };
}
