import { GET } from '../api.js';
import { ACCIONES } from '../acciones.js';
import { ahoraNegocio, fmtFechaHora, sumarDias } from '../negocio.js';
import { botonAccion, cargarEn, h, insignia, tabla, tarjeta } from '../ui.js';

const ESTADOS = ['En gestión', 'En organización', 'En ejecución', 'Finalizado', 'Cancelado', 'Cerrado sin contratación'];

export function eventos(contenedor) {
  const hoy = ahoraNegocio().slice(0, 10);
  const estadoUi = { desde: sumarDias(hoy, -90), hasta: sumarDias(hoy, 365), texto: '', estado: '' };
  const resultado = h('div');

  const campoFecha = (id, etiqueta, clave) => h('div', { class: 'campo' }, h('label', { for: id }, etiqueta),
    h('input', { id, type: 'date', value: estadoUi[clave], onchange: (e) => { estadoUi[clave] = e.target.value; } }));

  const consultar = () => {
    if (!estadoUi.desde || !estadoUi.hasta || estadoUi.desde > estadoUi.hasta) {
      resultado.replaceChildren(h('div', { class: 'caja-aviso', role: 'alert' }, 'Indica un rango de fechas válido: la fecha inicial no puede ser posterior a la final.'));
      return;
    }
    cargarEn(resultado, () => GET('/eventos', { desde: `${estadoUi.desde}T00:00:00`, hasta: `${estadoUi.hasta}T23:59:59` }), (r) => pintar(r.eventos));
  };

  function pintar(lista) {
    const t = estadoUi.texto.trim().toLowerCase();
    const filtrados = lista.filter((e) => (!estadoUi.estado || e.estadoEvento === estadoUi.estado)
      && (!t || [e.eventoId, e.tipoEvento, e.lugar, e.clienteId].some((x) => String(x).toLowerCase().includes(t))));
    return tarjeta(`${filtrados.length} evento(s)`, tabla([
      { titulo: 'Evento', celda: (e) => h('a', { href: `#/evento/${e.eventoId}` }, `${e.tipoEvento}`, h('div', { class: 'peq id' }, e.eventoId)) },
      { titulo: 'Fecha y hora', celda: (e) => fmtFechaHora(e.fechaHora) },
      { titulo: 'Lugar', celda: (e) => e.lugar },
      { titulo: 'Cliente', celda: (e) => e.clienteId },
      { titulo: 'Estado', celda: (e) => insignia(e.estadoEvento) },
      { titulo: 'Acciones', celda: (e) => h('a', { class: 'btn btn-peq', href: `#/evento/${e.eventoId}` }, 'Abrir') },
    ], filtrados, { vacioTitulo: 'No hay eventos con esos criterios', vacioDetalle: 'Cambia el rango de fechas o los filtros, o registra un evento nuevo.' }));
  }

  const abrirPorId = h('form', { class: 'barra-filtros', onsubmit: (ev) => { ev.preventDefault(); const v = ev.target.elements.id.value.trim(); if (v) location.hash = `#/evento/${encodeURIComponent(v)}`; } },
    h('div', { class: 'campo' }, h('label', { for: 'abrir-id' }, 'Abrir un evento por su identificador'),
      h('input', { id: 'abrir-id', name: 'id', placeholder: 'Por ejemplo, EV-1', autocomplete: 'off' })),
    h('button', { class: 'btn', type: 'submit' }, 'Abrir'));

  contenedor.replaceChildren(
    h('header', { class: 'pagina-cab' }, h('h1', null, 'Eventos'),
      h('p', null, 'La API consulta los eventos por rango de fechas del evento. Ajusta el rango para encontrar los que buscas.'),
      botonAccion(ACCIONES.registrarEvento, { irA: (h2) => { location.hash = h2; } }, null, { clase: 'btn btn-primario', texto: 'Registrar evento' })),
    h('form', { class: 'barra-filtros', onsubmit: (ev) => { ev.preventDefault(); consultar(); } },
      campoFecha('f-desde', 'Eventos desde', 'desde'), campoFecha('f-hasta', 'Eventos hasta', 'hasta'),
      h('div', { class: 'campo' }, h('label', { for: 'f-estado' }, 'Estado'),
        h('select', { id: 'f-estado', onchange: (e) => { estadoUi.estado = e.target.value; consultar(); } }, h('option', { value: '' }, 'Todos'), ESTADOS.map((s) => h('option', { value: s }, s)))),
      h('div', { class: 'campo' }, h('label', { for: 'f-texto' }, 'Buscar'),
        h('input', { id: 'f-texto', type: 'search', placeholder: 'Tipo, lugar, cliente o identificador', oninput: (e) => { estadoUi.texto = e.target.value; } })),
      h('button', { class: 'btn btn-primario', type: 'submit' }, 'Consultar')),
    abrirPorId, resultado);
  consultar();
}
