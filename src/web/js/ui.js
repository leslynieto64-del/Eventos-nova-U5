/* Componentes comunes: creación de elementos, iconos, avisos, estados de carga, tablas y formularios con validación. */
import { ErrorApi } from './api.js';
import { AYUDA_ESTADO, ahoraNegocio, fmtFechaHora, tono } from './negocio.js';
import { humanizar, sinVacios } from './texto.js';
import { puede } from './sesion.js';

/** h('div', {class:'x', onclick}, hijo1, 'texto') */
export function h(etiqueta, atributos, ...hijos) {
  const el = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  const poner = (x) => {
    if (x === null || x === undefined || x === false) return;
    if (Array.isArray(x)) x.forEach(poner);
    else el.append(x.nodeType ? x : document.createTextNode(String(x)));
  };
  hijos.forEach(poner);
  return el;
}

const ICONOS = {
  inicio: 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  calendario: 'M4 6h16v14H4zM4 10h16M8 3v6M16 3v6',
  documento: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7',
  contrato: 'M5 3h14v18H5zM9 8h6M9 12h6M9 16h3',
  pago: 'M3 6h18v12H3zM3 10h18M7 15h4',
  cambio: 'M7 7h11l-3-3M17 17H6l3 3',
  mas: 'M12 5v14M5 12h14',
  proveedor: 'M3 7h11v9H3zM14 10h4l3 3v3h-7M7 19a1.5 1.5 0 100-.01M17 19a1.5 1.5 0 100-.01',
  devolucion: 'M9 14l-5-5 5-5M4 9h10a6 6 0 010 12h-3',
  info: 'M12 8h.01M11 12h1v5h1M3 12a9 9 0 1018 0 9 9 0 00-18 0',
  menu: 'M4 6h16M4 12h16M4 18h16',
  cerrar: 'M6 6l12 12M18 6L6 18',
  ok: 'M5 12l5 5L20 7',
  alerta: 'M12 4l9 16H3zM12 10v4M12 17h.01',
  buscar: 'M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-5-5',
  flecha: 'M9 6l6 6-6 6',
  sistema: 'M4 5h16v10H4zM8 19h8M12 15v4',
  seguimiento: 'M4 12h4l3-8 4 16 3-8h2',
};
export function icono(nombre) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('class', 'icono'); svg.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS(ns, 'path'); p.setAttribute('d', ICONOS[nombre] || ICONOS.info);
  svg.append(p);
  return svg;
}

// ---------------------------------------------------------------- avisos
export function aviso(tipo, mensaje, detalle) {
  const zona = document.getElementById('avisos');
  const cierre = h('button', { class: 'aviso-cerrar', type: 'button', 'aria-label': 'Cerrar aviso' }, icono('cerrar'));
  const el = h('div', { class: `aviso aviso-${tipo}`, role: tipo === 'error' ? 'alert' : 'status' },
    icono(tipo === 'ok' ? 'ok' : tipo === 'error' || tipo === 'aviso' ? 'alerta' : 'info'),
    h('div', { class: 'aviso-texto' }, h('strong', null, mensaje), detalle ? h('div', { class: 'peq' }, detalle) : null), cierre);
  const quitar = () => el.remove();
  cierre.addEventListener('click', quitar);
  while (zona.children.length >= 3) zona.firstChild.remove();      // no apilar avisos sin límite
  zona.append(el);
  if (tipo !== 'error') setTimeout(quitar, 7000);
}

export function insignia(estado) {
  const ayuda = AYUDA_ESTADO[estado];
  return h('span', { class: `insignia t-${tono(estado)}`, title: ayuda || null }, estado || '—');
}

// ---------------------------------------------------------------- estados de pantalla
export const cargando = (texto = 'Cargando…') => h('div', { class: 'cargando', role: 'status' }, h('span', { class: 'rueda' }), texto);
export const vacio = (titulo, detalle) => h('div', { class: 'vacio' }, h('strong', null, titulo), detalle ? h('p', null, detalle) : null);

/** Caja de error para consultas; ofrece reintentar. */
export function cajaError(err, reintentar) {
  const msg = err instanceof ErrorApi ? err.message : 'Ocurrió un problema inesperado al mostrar esta información.';
  return h('div', { class: 'caja-error', role: 'alert' }, icono('alerta'),
    h('div', null, h('strong', null, err instanceof ErrorApi && err.tipo === 'no_encontrado' ? 'No se encontró la información' : 'No se pudo cargar la información'),
      h('p', null, msg), reintentar ? h('button', { class: 'btn', type: 'button', onclick: reintentar }, 'Reintentar') : null));
}

/** Pinta una promesa en un contenedor con carga, error y reintento. */
export async function cargarEn(contenedor, tarea, pintar) {
  contenedor.replaceChildren(cargando());
  try {
    const datos = await tarea();
    const nodo = pintar(datos);
    contenedor.replaceChildren(...sinVacios(nodo));
  } catch (e) {
    contenedor.replaceChildren(cajaError(e, () => cargarEn(contenedor, tarea, pintar)));
  }
}

// ---------------------------------------------------------------- tablas y tarjetas
export function tabla(columnas, filas, { vacioTitulo = 'Sin registros', vacioDetalle } = {}) {
  if (!filas.length) return vacio(vacioTitulo, vacioDetalle);
  const t = h('table', { class: 'tabla' },
    h('thead', null, h('tr', null, columnas.map((c) => h('th', { scope: 'col', class: c.clase }, c.titulo)))),
    h('tbody', null, filas.map((f) => h('tr', null, columnas.map((c) =>
      h('td', { 'data-etiqueta': c.titulo, class: c.clase }, c.celda(f)))))));
  return h('div', { class: 'tabla-contenedor' }, t);
}

export const tarjeta = (titulo, contenido, { acciones, clase } = {}) =>
  h('section', { class: `tarjeta ${clase || ''}` },
    titulo ? h('header', { class: 'tarjeta-cab' }, h('h3', null, titulo), acciones ? h('div', { class: 'acciones' }, acciones) : null) : null,
    h('div', { class: 'tarjeta-cuerpo' }, contenido));

/** Proveedor de un servicio: nombre legible (si figura en el catálogo) con su identificador, o «Sin asignar» si de verdad no hay asignación. */
export function celdaProveedor(s) {
  if (!s.proveedorId) return h('span', { class: 'peq' }, 'Sin asignar');
  return h('div', null, h('a', { href: `#/proveedores/${encodeURIComponent(s.proveedorId)}` }, s.proveedorNombre || s.proveedorId),
    s.proveedorNombre ? h('div', { class: 'peq id' }, s.proveedorId) : h('div', { class: 'peq' }, 'No figura en el catálogo'));
}

export const dato = (etiqueta, valor) => h('div', { class: 'dato' }, h('dt', null, etiqueta), h('dd', null, valor ?? '—'));
export const datos = (...pares) => h('dl', { class: 'datos' }, pares.map(([e, v]) => dato(e, v)));

export function copiable(texto) {
  return h('button', { class: 'id-copiable', type: 'button', title: 'Copiar identificador',
    onclick: async () => { try { await navigator.clipboard.writeText(texto); aviso('ok', 'Identificador copiado.'); } catch { aviso('aviso', 'No fue posible copiar automáticamente.'); } } }, texto);
}

// ---------------------------------------------------------------- formularios
const RE_IMPORTE = /^\d+(\.\d+)?$/;

function crearControl(campo, id, valor) {
  const comunes = { id, name: campo.nombre, 'aria-describedby': `${id}-ayuda ${id}-error`, required: campo.requerido ? true : null };
  switch (campo.tipo) {
    case 'textarea': return h('textarea', { ...comunes, rows: 3 }, valor ?? '');
    case 'select': return h('select', comunes,
      !campo.requerido || campo.vacio ? h('option', { value: '' }, campo.vacio || 'Selecciona una opción') : null,
      campo.opciones.map((o) => h('option', { value: o.valor, selected: String(o.valor) === String(valor) }, o.texto)));
    case 'bool': return h('input', { ...comunes, type: 'checkbox', checked: valor ? true : null });
    case 'contrasena': return h('input', { ...comunes, type: 'password', autocomplete: 'new-password', spellcheck: 'false' });
    case 'fechahora': return h('input', { ...comunes, type: 'datetime-local', step: 60, value: (valor || '').slice(0, 16) });
    case 'importe': return h('input', { ...comunes, type: 'text', inputmode: 'decimal', autocomplete: 'off', placeholder: '0.00', value: valor ?? '' });
    case 'entero': return h('input', { ...comunes, type: 'text', inputmode: 'numeric', autocomplete: 'off', value: valor ?? '' });
    default: return h('input', { ...comunes, type: 'text', autocomplete: 'off', value: valor ?? '' });
  }
}

function leer(campo, control) {
  if (campo.tipo === 'bool') return control.checked;
  const v = campo.tipo === 'contrasena' ? control.value : control.value.trim();      // la contraseña no se recorta
  if (campo.tipo === 'fechahora') return v ? (v.length === 16 ? `${v}:00` : v) : '';
  return v;
}

function validarCampo(campo, v) {
  const vacioV = v === '' || v === undefined || (Array.isArray(v) && !v.length);
  if (campo.tipo === 'bool') return null;
  if (vacioV) return campo.requerido ? 'Este campo es obligatorio. Introduce la información para continuar.' : null;
  if (campo.tipo === 'importe') {
    if (!RE_IMPORTE.test(v)) return 'Escribe un importe válido con números y, si hace falta, punto decimal (por ejemplo, 1500.50).';
    if (campo.positivo && Number(v) <= 0) return 'El importe debe ser mayor que cero.';
  }
  if (campo.tipo === 'entero' && (!/^\d+$/.test(v) || Number(v) < (campo.minimo ?? 0))) return `Escribe un número entero${campo.minimo ? ` igual o mayor que ${campo.minimo}` : ''}.`;
  if (campo.tipo === 'fechahora' && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(v)) return 'Escribe una fecha y hora válidas.';
  if (campo.tipo === 'contrasena' && campo.minLongitud && v.length < campo.minLongitud) return `La contraseña debe tener al menos ${campo.minLongitud} caracteres.`;
  return null;
}

/**
 * Abre un formulario modal. def: {titulo, intro, campos:[{nombre,etiqueta,tipo,requerido,ayuda,valor,opciones,visibleSi}],
 * resumen(valores)→texto de confirmación, aviso (texto destacado), peligro, textoEnviar, enviar(valores)→Promise<respuesta>}.
 * Devuelve la respuesta del backend si la operación se completó, o null si se canceló.
 */
export function abrirFormulario(def) {
  return new Promise((resolver) => {
    const dialogo = h('dialog', { class: 'modal', 'aria-labelledby': 'modal-titulo' });
    const campos = def.campos || [];
    const controles = new Map();
    const filas = new Map();
    let enviando = false;

    const alerta = h('div', { class: 'modal-alerta', hidden: true, role: 'alert' });
    const cuerpoForm = h('div', { class: 'modal-cuerpo' });
    const pie = h('footer', { class: 'modal-pie' });
    const forma = h('form', { novalidate: true, class: 'formulario' });

    campos.forEach((c, i) => {
      const id = `f-${i}-${c.nombre}`;
      const ctl = crearControl(c, id, c.valor);
      controles.set(c.nombre, ctl);
      const fila = h('div', { class: `campo ${c.tipo === 'bool' ? 'campo-bool' : ''}` },
        c.tipo === 'bool'
          ? h('label', { for: id }, ctl, h('span', null, c.etiqueta))
          : [h('label', { for: id }, c.etiqueta, c.requerido ? h('span', { class: 'req', 'aria-hidden': 'true' }, ' *') : h('span', { class: 'opc' }, ' (opcional)')), ctl],
        c.ayuda ? h('div', { class: 'ayuda', id: `${id}-ayuda` }, c.ayuda) : h('span', { id: `${id}-ayuda` }),
        h('div', { class: 'error-campo', id: `${id}-error`, role: 'alert' }));
      filas.set(c.nombre, fila);
      forma.append(fila);
      ctl.addEventListener('input', () => { fila.querySelector('.error-campo').textContent = ''; fila.classList.remove('invalido'); ctl.removeAttribute('aria-invalid'); actualizarVisibilidad(); });
      ctl.addEventListener('change', actualizarVisibilidad);
    });

    const valores = () => {
      const v = {};
      for (const c of campos) {
        const bruto = leer(c, controles.get(c.nombre));
        v[c.nombre] = c.tipo === 'lista' ? bruto.split(',').map((x) => x.trim()).filter(Boolean) : bruto;
      }
      return v;
    };
    const visible = (c, v) => !c.visibleSi || c.visibleSi(v);
    function actualizarVisibilidad() {
      const v = valores();
      for (const c of campos) filas.get(c.nombre).hidden = !visible(c, v);
    }

    const marcar = (nombre, mensaje) => {
      const fila = filas.get(nombre); if (!fila) return false;
      fila.classList.add('invalido'); fila.querySelector('.error-campo').textContent = mensaje;
      controles.get(nombre).setAttribute('aria-invalid', 'true'); return true;
    };
    const mostrarAlerta = (tipo, ...hijos) => { alerta.hidden = false; alerta.className = `modal-alerta aviso-${tipo}`; alerta.replaceChildren(...sinVacios(hijos)); };

    function validar() {
      const v = valores(); let primero = null;
      for (const c of campos) {
        if (!visible(c, v)) continue;
        const msg = validarCampo(c, v[c.nombre]);
        if (msg) { marcar(c.nombre, msg); primero = primero || c.nombre; }
      }
      if (primero) { controles.get(primero).focus(); mostrarAlerta('error', 'Revisa los campos marcados antes de continuar.'); return null; }
      alerta.hidden = true;
      // Los campos ocultos no se envían.
      for (const c of campos) if (!visible(c, v)) delete v[c.nombre];
      return v;
    }

    const cerrar = (resultado) => { dialogo.close(); dialogo.remove(); resolver(resultado); };
    const btnCancelar = h('button', { type: 'button', class: 'btn', onclick: () => cerrar(null) }, 'Cancelar');
    const btnEnviar = h('button', { type: 'submit', class: `btn ${def.peligro ? 'btn-peligro' : 'btn-primario'}` }, def.textoEnviar || 'Guardar');

    async function ejecutar(v) {
      if (enviando) return;                                   // evita envíos duplicados
      enviando = true; btnEnviar.disabled = true; btnCancelar.disabled = true; btnEnviar.setAttribute('aria-busy', 'true');
      const textoOriginal = btnEnviar.textContent; btnEnviar.textContent = 'Enviando…';
      try {
        const respuesta = await def.enviar(v);
        cerrar(respuesta ?? true);
      } catch (e) {
        enviando = false; btnEnviar.disabled = false; btnCancelar.disabled = false; btnEnviar.removeAttribute('aria-busy'); btnEnviar.textContent = textoOriginal;
        if (campos.length) mostrarEnConfirmacion(false); else mostrarEnConfirmacion(true, v);
        if (e instanceof ErrorApi && e.tipo === 'validacion') {
          const sin = [];
          for (const f of e.campos) {
            const nombre = f.campo.split('.').pop();
            if (!marcar(nombre, f.mensaje)) sin.push(`${f.campo}: ${f.mensaje}`);
          }
          mostrarAlerta('error', h('strong', null, e.message), sin.length ? h('ul', null, sin.map((s) => h('li', null, s))) : null);
        } else if (e instanceof ErrorApi) {
          mostrarAlerta('error', h('strong', null, e.message),
            e.pendientes.length ? h('ul', null, e.pendientes.map((p) => h('li', null, p))) : null,
            e.tipo === 'negocio' ? h('p', { class: 'peq' }, 'No es posible realizar esta operación en el estado actual. Consulta el motivo indicado y las acciones disponibles.') : null,
            e.crudo ? h('details', null, h('summary', null, 'Detalles técnicos'), h('pre', null, JSON.stringify(e.crudo, null, 2))) : null);
        } else {
          mostrarAlerta('error', 'Ocurrió un problema inesperado. No se han confirmado los cambios.');
          console.error(e);
        }
      }
    }

    const vistaConfirmacion = h('div', { class: 'confirmacion', hidden: true });
    function mostrarEnConfirmacion(si, v) {
      forma.hidden = si; vistaConfirmacion.hidden = !si;
      if (si) {
        vistaConfirmacion.replaceChildren(...sinVacios(h('p', null, def.resumen ? def.resumen(v) : 'Confirma que deseas ejecutar esta operación.'),
          def.aviso ? h('p', { class: 'aviso-fuerte' }, def.aviso) : null));      // un aviso ausente no se pinta (el DOM escribiría «null»)
        pie.replaceChildren(
          h('button', { type: 'button', class: 'btn', onclick: () => mostrarEnConfirmacion(false) }, campos.length ? 'Volver' : 'Cancelar'),
          h('button', { type: 'button', class: `btn ${def.peligro ? 'btn-peligro' : 'btn-primario'}`, id: 'btn-confirmar', onclick: () => ejecutar(v) }, def.textoEnviar || 'Confirmar'));
        pie.lastChild.focus();
        if (!campos.length) pie.firstChild.onclick = () => cerrar(null);
      } else {
        pie.replaceChildren(btnCancelar, btnEnviar);
      }
    }

    forma.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const v = validar(); if (!v) return;
      if (def.resumen || def.peligro) mostrarEnConfirmacion(true, v); else ejecutar(v);
    });
    btnEnviar.setAttribute('form', 'x'); forma.id = 'x'; // el botón pertenece al formulario aunque esté en el pie
    dialogo.addEventListener('cancel', (ev) => { if (enviando) ev.preventDefault(); else { dialogo.remove(); resolver(null); } });

    cuerpoForm.append(...[def.intro ? h('p', { class: 'intro' }, def.intro) : null,
      def.aviso && campos.length ? h('p', { class: 'aviso-fuerte' }, def.aviso) : null, forma, vistaConfirmacion].filter(Boolean));
    dialogo.append(h('header', { class: 'modal-cab' }, h('h2', { id: 'modal-titulo' }, def.titulo)), alerta, cuerpoForm, pie);
    document.body.append(dialogo);
    actualizarVisibilidad();
    dialogo.showModal();
    if (campos.length) { pie.replaceChildren(btnCancelar, btnEnviar); const primero = [...controles.values()][0]; primero && primero.focus(); }
    else mostrarEnConfirmacion(true, {});
  });
}

/** Ejecuta una acción declarativa (ver acciones.js): formulario, confirmación, envío y aviso de resultado. */
export async function ejecutarAccion(accion, contexto, alTerminar) {
  if (accion.permiso && !puede(accion.permiso)) {              // el servidor decide en definitiva; esto evita enviar una operación que seguro se rechazará
    aviso('error', 'No tienes permiso para realizar esta operación con tu rol.');
    return null;
  }
  const campos = (accion.campos ? accion.campos(contexto) : []).map((c) => ({ ...c, valor: c.valor === 'AHORA' ? ahoraNegocio() : c.valor }));
  const respuesta = await abrirFormulario({
    titulo: accion.titulo,
    intro: accion.intro ? accion.intro(contexto) : null,
    aviso: accion.aviso || null,
    campos,
    peligro: accion.peligro,
    textoEnviar: accion.textoEnviar || accion.titulo,
    resumen: accion.resumen ? (v) => accion.resumen(v, contexto) : (accion.peligro || !campos.length ? () => `¿Confirmas «${accion.titulo.toLowerCase()}»?` : null),
    enviar: (v) => accion.enviar(v, contexto),
  });
  if (respuesta === null) return null;
  const mensaje = respuesta && respuesta.mensaje ? humanizar(respuesta.mensaje) : 'La operación se completó correctamente.';
  aviso('ok', mensaje, accion.exito ? accion.exito(respuesta, contexto) : null);
  if (accion.despues) accion.despues(respuesta, contexto);
  if (alTerminar) alTerminar(respuesta);
  return respuesta;
}

export const botonAccion = (accion, contexto, alTerminar, { clase = 'btn', texto } = {}) =>
  accion.permiso && !puede(accion.permiso) ? null : h('button', { type: 'button', class: clase, onclick: () => ejecutarAccion(accion, contexto, alTerminar) }, texto || accion.etiqueta || accion.titulo);

/** Diálogo informativo de solo lectura (por ejemplo, el resultado de una consulta). */
export function dialogoInfo(titulo, contenido) {
  const d = h('dialog', { class: 'modal', 'aria-labelledby': 'info-titulo' },
    h('header', { class: 'modal-cab' }, h('h2', { id: 'info-titulo' }, titulo)), h('div', { class: 'modal-cuerpo' }, contenido),
    h('footer', { class: 'modal-pie' }, h('button', { class: 'btn btn-primario', type: 'button', onclick: () => { d.close(); d.remove(); } }, 'Cerrar')));
  d.addEventListener('cancel', () => d.remove());
  document.body.append(d); d.showModal();
}

export const fechaCorta = fmtFechaHora;
