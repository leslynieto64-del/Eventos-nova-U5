/* Punto de entrada: sesión, enrutador por «#/ruta» y navegación. Cada página se pinta en <main id="contenido">.
   Sin sesión (cuando la autenticación está activa) solo se muestra el ingreso. Los permisos que se usan aquí para ocultar menús y pantallas
   son comodidad: el servidor vuelve a comprobar cada petición. */
import { panel } from './paginas/panel.js';
import { eventos } from './paginas/eventos.js';
import { evento } from './paginas/evento.js';
import { pagos, solicitudes, seguimiento, proveedor, sistema } from './paginas/otras.js';
import { proveedores, proveedorFicha } from './paginas/proveedores.js';
import { cuentas } from './paginas/cuentas.js';
import { ingreso } from './paginas/ingreso.js';
import { ACCIONES } from './acciones.js';
import { cargar as cargarSesion, cerrar as cerrarSesion, estado as sesion, ETIQUETA_ROL, olvidar, puede, requiereIngreso, rol } from './sesion.js';
import { ejecutarAccion, h } from './ui.js';

const RUTAS = [
  { patron: /^\/?$/, modulo: 'inicio', pagina: panel, titulo: 'Panel principal', permiso: 'eventos.consultar' },
  { patron: /^\/eventos$/, modulo: 'eventos', pagina: eventos, titulo: 'Eventos', permiso: 'eventos.consultar' },
  { patron: /^\/evento\/([^/]+)$/, modulo: 'eventos', pagina: evento, titulo: 'Detalle del evento', permiso: 'eventos.consultar' },
  { patron: /^\/pagos$/, modulo: 'pagos', pagina: pagos, titulo: 'Pagos y devoluciones', permiso: 'pagos.consultar' },
  { patron: /^\/solicitudes$/, modulo: 'solicitudes', pagina: solicitudes, titulo: 'Solicitudes', permiso: 'eventos.consultar' },
  { patron: /^\/seguimiento$/, modulo: 'seguimiento', pagina: seguimiento, titulo: 'Seguimiento', permiso: 'eventos.consultar' },
  { patron: /^\/proveedores$/, modulo: 'proveedores', pagina: proveedores, titulo: 'Proveedores', permiso: 'proveedores.consultar' },
  { patron: /^\/proveedores\/([^/]+)$/, modulo: 'proveedores', pagina: proveedorFicha, titulo: 'Datos del proveedor', permiso: 'proveedores.consultar proveedores.propio' },
  { patron: /^\/proveedor$/, modulo: 'proveedor', pagina: proveedor, titulo: 'Consulta de proveedor', permiso: 'proveedores.consultar proveedores.propio' },
  { patron: /^\/cuentas$/, modulo: 'cuentas', pagina: cuentas, titulo: 'Cuentas', permiso: 'usuarios.administrar' },
  { patron: /^\/sistema$/, modulo: 'sistema', pagina: sistema, titulo: 'Sistema y ayuda', permiso: null },
];

let secuencia = 0;
const contenido = () => document.getElementById('contenido');

/** Muestra u oculta los elementos del menú según el rol y pinta la caja de la sesión. */
function pintarSesion() {
  document.body.classList.toggle('sin-sesion', requiereIngreso());
  document.querySelectorAll('#menu a').forEach((a) => { a.hidden = !puede(a.dataset.permiso || null); });
  const caja = document.getElementById('sesion-caja');
  if (!caja) return;
  if (!sesion.activa) {
    caja.replaceChildren(h('p', { class: 'sesion-aviso' }, 'Autenticación desactivada: modo de desarrollo. No uses este modo con datos reales.'));
  } else if (sesion.usuario) {
    caja.replaceChildren(h('div', { class: 'sesion-persona' }, h('strong', null, sesion.usuario.nombre), h('span', { class: 'peq' }, ETIQUETA_ROL[sesion.usuario.rol] || sesion.usuario.rol)),
      h('div', { class: 'sesion-botones' },
        h('button', { type: 'button', class: 'btn btn-peq', onclick: () => ejecutarAccion(ACCIONES.cambiarContrasena, {}, () => { olvidar(); mostrarIngreso('Tu contraseña cambió. Inicia sesión de nuevo.'); }) }, 'Cambiar contraseña'),
        h('button', { type: 'button', class: 'btn btn-peq', onclick: async () => { await cerrarSesion(); mostrarIngreso('Cerraste sesión.'); } }, 'Cerrar sesión')));
  } else {
    caja.replaceChildren();
  }
}

function mostrarIngreso(mensaje) {
  document.querySelectorAll('dialog[open]').forEach((d) => { d.close(); d.remove(); });
  pintarSesion();
  document.title = 'Iniciar sesión · Eventos Nova';
  ingreso(contenido(), { mensaje, alIniciar: () => { pintarSesion(); const destino = rol() === 'proveedor' ? '#/proveedor' : '#/'; if (location.hash === destino) navegar(); else location.hash = destino; } });   // un solo recorrido: el cambio de hash ya navega
}

async function navegar() {
  if (requiereIngreso()) { mostrarIngreso(); return; }
  const hash = location.hash.replace(/^#/, '') || '/';
  const [ruta, qs = ''] = hash.split('?');
  // Cada navegación pinta en su PROPIO contenedor: si una pantalla lenta (la anterior) termina después, escribe en uno ya descartado y no pisa a la actual.
  const cont = document.createElement('div');
  contenido().replaceChildren(cont);
  const consulta = new URLSearchParams(qs);
  pintarSesion();
  if (rol() === 'proveedor' && /^\/?$/.test(ruta)) { location.hash = '#/proveedor'; return; }           // el proveedor no tiene panel: va a lo suyo
  for (const r of RUTAS) {
    const m = r.patron.exec(ruta);
    if (!m) continue;
    const mia = ++secuencia;
    document.title = `${r.titulo} · Eventos Nova`;
    document.querySelectorAll('#menu a').forEach((a) => {
      const activo = a.dataset.modulo === r.modulo;
      a.classList.toggle('activo', activo);
      if (activo) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    document.body.classList.remove('menu-abierto');
    if (!puede(r.permiso)) {
      cont.replaceChildren(h('div', { class: 'caja-aviso', role: 'alert' }, h('strong', null, 'No tienes permiso para ver esta pantalla'),
        h('p', null, 'Tu rol no incluye esta función. Si la necesitas, pídela a la administración.'), h('a', { class: 'btn', href: rol() === 'proveedor' ? '#/proveedor' : '#/' }, 'Volver al inicio')));
      return;
    }
    try { await r.pagina(cont, m.slice(1), consulta); } catch (e) {
      if (mia === secuencia) cont.replaceChildren(h('div', { class: 'caja-error', role: 'alert' }, h('div', null, h('strong', null, 'No se pudo mostrar esta pantalla'), h('p', null, 'Recarga la página e inténtalo de nuevo.'))));
      console.error(e);
    }
    contenido().focus({ preventScroll: true });
    window.scrollTo(0, 0);
    return;
  }
  cont.replaceChildren(h('div', { class: 'vacio' }, h('strong', null, 'Página no encontrada'), h('p', null, 'La dirección no corresponde a ninguna pantalla.'), h('a', { class: 'btn', href: '#/' }, 'Ir al panel')));
}

document.getElementById('boton-menu').addEventListener('click', () => {
  const abierto = document.body.classList.toggle('menu-abierto');
  document.getElementById('boton-menu').setAttribute('aria-expanded', String(abierto));
});
window.addEventListener('hashchange', navegar);
// Una petición respondió «sin sesión» (caducó, se cerró o la cuenta se desactivó): se vuelve al ingreso con una explicación.
window.addEventListener('sesion-expirada', (e) => {
  if (!sesion.usuario) return;
  olvidar();
  mostrarIngreso(e.detail || 'Tu sesión expiró. Inicia sesión nuevamente.');
});

(async () => {
  try { await cargarSesion(); } catch (e) { console.error(e); }
  navegar();
})();
