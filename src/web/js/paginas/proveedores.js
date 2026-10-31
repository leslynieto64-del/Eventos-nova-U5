/* Catálogo de proveedores: lista con búsqueda, alta y ficha de un proveedor. Todo sale de la API (GET/POST /proveedores). */
import { GET } from '../api.js';
import { ACCIONES } from '../acciones.js';
import { fmtFechaHora } from '../negocio.js';
import { botonAccion, cajaError, cargando, cargarEn, copiable, datos, h, tabla, tarjeta } from '../ui.js';

const irA = (hash) => { location.hash = hash; };

export function proveedores(contenedor, _p, consulta) {
  const filtros = { q: consulta.get('q') || '', servicio: consulta.get('servicio') || '' };
  const salida = h('div');

  const consultar = () => cargarEn(salida, () => GET('/proveedores', { q: filtros.q, servicio: filtros.servicio }), (r) => {
    const lista = r.datos.proveedores;
    const hayFiltro = filtros.q || filtros.servicio;
    return tarjeta(`${lista.length} proveedor(es)`, tabla([
      { titulo: 'Proveedor', celda: (p) => h('a', { href: `#/proveedores/${encodeURIComponent(p.proveedorId)}` }, p.nombre, h('div', { class: 'peq id' }, p.proveedorId)) },
      { titulo: 'Servicios que ofrece', celda: (p) => (p.servicios.length ? p.servicios.join(', ') : h('span', { class: 'peq' }, 'Sin servicios indicados')) },
      { titulo: 'Contacto', celda: (p) => p.contacto || '—' },
      { titulo: 'Acciones', celda: (p) => h('a', { class: 'btn btn-peq', href: `#/proveedores/${encodeURIComponent(p.proveedorId)}` }, 'Ver datos') },
    ], lista, hayFiltro
      ? { vacioTitulo: 'Ningún proveedor coincide con la búsqueda', vacioDetalle: 'Cambia el texto o quita el filtro de servicio.' }
      : { vacioTitulo: 'Aún no hay proveedores registrados', vacioDetalle: 'Registra el primero con «Registrar proveedor». Después podrás asignarlo a los servicios de un evento En organización.' }));
  });

  contenedor.replaceChildren(
    h('header', { class: 'pagina-cab' }, h('h1', null, 'Proveedores'),
      h('p', null, 'Catálogo de las personas o empresas que prestan servicios en los eventos. La asignación a un servicio se hace desde el detalle del evento (En organización).'),
      h('div', { class: 'acciones' },
        botonAccion(ACCIONES.registrarProveedor, { irA }, null, { clase: 'btn btn-primario', texto: 'Registrar proveedor' }),
        h('a', { class: 'btn', href: '#/proveedor' }, 'Consultar lo que un proveedor ve de un evento'))),
    h('form', { class: 'barra-filtros', onsubmit: (ev) => { ev.preventDefault(); const e = ev.target.elements; filtros.q = e.q.value.trim(); filtros.servicio = e.servicio.value.trim();
      const qs = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v)).toString(); history.replaceState(null, '', `#/proveedores${qs ? `?${qs}` : ''}`); consultar(); } },
      h('div', { class: 'campo' }, h('label', { for: 'pv-q' }, 'Buscar'), h('input', { id: 'pv-q', name: 'q', type: 'search', value: filtros.q, placeholder: 'Nombre, identificador, contacto o servicio', autocomplete: 'off' })),
      h('div', { class: 'campo' }, h('label', { for: 'pv-s' }, 'Ofrece el servicio'), h('input', { id: 'pv-s', name: 'servicio', value: filtros.servicio, placeholder: 'Por ejemplo, Banquete', autocomplete: 'off' })),
      h('button', { class: 'btn btn-primario', type: 'submit' }, 'Buscar')),
    salida);
  consultar();
}

export async function proveedorFicha(contenedor, [proveedorId]) {
  const id = decodeURIComponent(proveedorId || '');
  const reintentar = () => proveedorFicha(contenedor, [proveedorId]);
  contenedor.replaceChildren(cargando('Consultando el proveedor…'));
  let p;
  try { p = (await GET(`/proveedores/${encodeURIComponent(id)}`)).datos; } catch (e) {
    contenedor.replaceChildren(cajaError(e, reintentar), h('a', { class: 'btn', href: '#/proveedores' }, 'Volver al catálogo')); return;
  }
  contenedor.replaceChildren(
    h('header', { class: 'pagina-cab' }, h('a', { href: '#/proveedores', class: 'migas' }, '← Proveedores'), h('h1', null, p.nombre),
      h('p', { class: 'peq' }, 'Identificador: ', copiable(p.proveedorId))),
    tarjeta('Datos del proveedor', datos(
      ['Nombre', p.nombre], ['Servicios que ofrece', p.servicios.length ? p.servicios.join(', ') : 'Sin servicios indicados'],
      ['Contacto', p.contacto || '—'], ['Registrado', fmtFechaHora(p.registradoEn)])),
    tarjeta('Servicios de eventos', h('div', null,
      h('p', null, 'La API no ofrece una lista de los eventos de un proveedor. Para ver lo que este proveedor tiene asignado en un evento concreto, consúltalo con el identificador del evento.'),
      h('a', { class: 'btn', href: '#/proveedor' }, 'Consultar servicios asignados en un evento'))));
}
