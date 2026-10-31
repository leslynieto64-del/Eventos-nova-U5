import { GET } from '../api.js';
import { ahoraNegocio, fmtFechaHora, sumarDias } from '../negocio.js';
import { cargando, cajaError, h, insignia, tabla, tarjeta, vacio } from '../ui.js';
import { registro } from '../registro.js';

const enlace = (href, texto) => h('a', { href }, texto);

function indicador(titulo, valor, detalle, href, tono = '') {
  return h('a', { class: `indicador ${tono}`, href }, h('span', { class: 'ind-valor' }, String(valor)), h('span', { class: 'ind-titulo' }, titulo),
    detalle ? h('span', { class: 'ind-detalle' }, detalle) : null);
}

export async function panel(contenedor) {
  const hoy = ahoraNegocio().slice(0, 10);
  const desde = `${sumarDias(hoy, -90)}T00:00:00`;
  const hasta = `${sumarDias(hoy, 365)}T23:59:59`;
  contenedor.replaceChildren(h('header', { class: 'pagina-cab' }, h('h1', null, 'Panel principal'),
    h('p', null, 'Resumen del trabajo de hoy con la información real del sistema.')), cargando('Consultando el sistema…'));

  const [eventos, pagos, solicitudes, devoluciones, servicios] = await Promise.allSettled([
    GET('/eventos', { desde, hasta }), GET('/pagos-pendientes'), GET('/solicitudes'), GET('/devoluciones-pendientes'), GET('/servicios-pendientes-confirmacion')]);

  const falla = (r) => (r.status === 'rejected' ? cajaError(r.reason, () => panel(contenedor)) : null);
  const rejilla = h('div', { class: 'rejilla-indicadores' });

  if (eventos.status === 'fulfilled') {
    const lista = eventos.value.eventos;
    const porEstado = {};
    lista.forEach((e) => { porEstado[e.estadoEvento] = (porEstado[e.estadoEvento] || 0) + 1; });
    rejilla.append(indicador('Eventos en la ventana consultada', lista.length, `${fmtFechaHora(desde).split(',')[0]} a ${fmtFechaHora(hasta).split(',')[0]}`, '#/eventos'));
    rejilla.append(indicador('En gestión', porEstado['En gestión'] || 0, 'Propuesta y contratación', '#/eventos', 'aviso'));
    rejilla.append(indicador('En organización', porEstado['En organización'] || 0, 'Contratación confirmada', '#/eventos', 'ok'));
  }
  if (pagos.status === 'fulfilled') {
    const p = pagos.value.pagos;
    const vencidos = p.filter((x) => x.estado === 'Vencida').length;
    rejilla.append(indicador('Pagos pendientes', p.length, vencidos ? `${vencidos} con plazo vencido` : 'Ninguno vencido', '#/pagos', vencidos ? 'error' : ''));
  }
  if (solicitudes.status === 'fulfilled') {
    const pend = solicitudes.value.solicitudes.filter((s) => s.pendiente).length;
    rejilla.append(indicador('Solicitudes en trámite', pend, 'Cambios, servicios adicionales y sustituciones', '#/solicitudes', pend ? 'aviso' : ''));
  }
  if (devoluciones.status === 'fulfilled') {
    const d = devoluciones.value.devoluciones; const v = d.filter((x) => x.vencida).length;
    rejilla.append(indicador('Devoluciones pendientes', d.length, v ? `${v} fuera de plazo` : 'Dentro de plazo', '#/pagos', v ? 'error' : ''));
  }
  if (servicios.status === 'fulfilled') {
    // Solo eventos que aún admiten gestionar proveedores (no cancelados, finalizados ni cerrados); Seguimiento explica los demás.
    const vigentes = servicios.value.servicios.filter((x) => !['Cancelado', 'Finalizado', 'Cerrado sin contratación'].includes(x.estadoEvento));
    rejilla.append(indicador('Servicios por confirmar', vigentes.length, 'Sin proveedor o pendientes de su confirmación', '#/seguimiento', vigentes.length ? 'aviso' : ''));
  }

  const bloques = [rejilla];
  [eventos, pagos, solicitudes, devoluciones, servicios].forEach((r) => { const e = falla(r); if (e) bloques.push(e); });

  if (eventos.status === 'fulfilled') {
    const proximos = eventos.value.eventos.filter((e) => e.fechaHora.slice(0, 10) >= hoy).sort((a, b) => a.fechaHora.localeCompare(b.fechaHora)).slice(0, 6);
    bloques.push(tarjeta('Próximos eventos', tabla([
      { titulo: 'Evento', celda: (e) => enlace(`#/evento/${e.eventoId}`, `${e.tipoEvento} · ${e.eventoId}`) },
      { titulo: 'Fecha', celda: (e) => fmtFechaHora(e.fechaHora) },
      { titulo: 'Lugar', celda: (e) => e.lugar },
      { titulo: 'Estado', celda: (e) => insignia(e.estadoEvento) },
    ], proximos, { vacioTitulo: 'No hay eventos próximos', vacioDetalle: 'No existen eventos con fecha desde hoy en la ventana consultada.' }),
    { acciones: enlace('#/eventos', 'Ver todos') }));
  }
  const recientes = registro.eventosRecientes();
  if (recientes.length) {
    bloques.push(tarjeta('Eventos consultados recientemente (en este navegador)', h('ul', { class: 'lista-simple' },
      recientes.map((e) => h('li', null, enlace(`#/evento/${e.id}`, e.nombre || e.id))))));
  }
  contenedor.replaceChildren(h('header', { class: 'pagina-cab' }, h('h1', null, 'Panel principal'),
    h('p', null, 'Resumen del trabajo de hoy con la información real del sistema.')), ...bloques);
  if (bloques.length === 1 && !rejilla.children.length) contenedor.append(vacio('Sin datos', 'No fue posible obtener indicadores.'));
}
