/* Pantalla de inicio de sesión. Las credenciales las valida SIEMPRE el servidor; esta pantalla solo las envía. */
import { ErrorApi } from '../api.js';
import { iniciar } from '../sesion.js';
import { h } from '../ui.js';

export function ingreso(contenedor, { mensaje, alIniciar }) {
  const alerta = h('div', { class: 'alerta-ingreso', role: 'alert', hidden: mensaje ? null : true }, mensaje || '');
  const correo = h('input', { id: 'ing-correo', name: 'correo', type: 'email', autocomplete: 'username', required: true, spellcheck: 'false' });
  const clave = h('input', { id: 'ing-clave', name: 'contrasena', type: 'password', autocomplete: 'current-password', required: true });
  const boton = h('button', { class: 'btn btn-primario', type: 'submit' }, 'Iniciar sesión');
  const error = (t) => { alerta.hidden = false; alerta.textContent = t; };
  const forma = h('form', { class: 'ingreso-forma', novalidate: true, onsubmit: async (ev) => {
    ev.preventDefault();
    if (!correo.value.trim() || !clave.value) { error('Escribe tu correo y tu contraseña para continuar.'); (correo.value.trim() ? clave : correo).focus(); return; }
    boton.disabled = true; boton.textContent = 'Verificando…'; alerta.hidden = true;
    try { await iniciar(correo.value.trim(), clave.value); clave.value = ''; alIniciar(); } catch (e) {
      clave.value = '';
      error(e instanceof ErrorApi ? e.message : 'No fue posible iniciar sesión. Inténtalo de nuevo.');
      boton.disabled = false; boton.textContent = 'Iniciar sesión'; clave.focus();
    }
  } },
  h('div', { class: 'campo' }, h('label', { for: 'ing-correo' }, 'Correo'), correo),
  h('div', { class: 'campo' }, h('label', { for: 'ing-clave' }, 'Contraseña'), clave),
  alerta, boton);
  contenedor.replaceChildren(h('section', { class: 'ingreso' },
    h('div', { class: 'ingreso-marca' }, h('span', { class: 'marca-sello', 'aria-hidden': 'true' }, 'EN'), h('span', null, 'Eventos Nova')),
    h('h1', null, 'Iniciar sesión'),
    h('p', { class: 'peq' }, 'Usa la cuenta que te dio la administración. Si olvidaste tu contraseña, pide que la restablezcan.'),
    forma));
  correo.focus();
}
