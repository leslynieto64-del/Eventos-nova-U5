/* Detalle de un evento: contratación, pagos, solicitudes, proveedores y ciclo de vida. Todo sale de la API; los botones se
   habilitan según el estado oficial devuelto, y el backend sigue siendo quien acepta o rechaza cada operación. */
import { GET } from '../api.js';
import { ACCIONES, accionesDeSolicitud, candidatosParaAsignar, consultarDisponibilidad } from '../acciones.js';
import { AYUDA_ESTADO, fmtFechaHora, fmtImporte } from '../negocio.js';
import { registro } from '../registro.js';
import { puede } from '../sesion.js';
import { aviso, botonAccion, cajaError, cargando, celdaProveedor, copiable, datos, dialogoInfo, ejecutarAccion, h, insignia, tabla, tarjeta, vacio } from '../ui.js';

const PASOS = ['Contrato preparado', 'Contrato firmado', 'Anticipo verificado', 'Contratación confirmada'];

function avance(contratos, estadosCuenta) {
  const c = contratos[0]; const ec = estadosCuenta[0];
  const cerrado = c && c.estado === 'Cerrado sin confirmar';
  const hechos = [!!c, !!c && ['Firmado', 'Contratación confirmada'].includes(c.estado), !!ec && ec.anticipo.estado === 'Liquidada', !!c && c.estado === 'Contratación confirmada'];
  const siguiente = hechos.indexOf(false);
  return h('ol', { class: 'pasos', 'aria-label': 'Avance de la contratación' }, PASOS.map((p, i) =>
    h('li', { class: hechos[i] ? 'hecho' : (i === siguiente && !cerrado ? 'actual' : '') , 'aria-current': i === siguiente && !cerrado ? 'step' : null },
      h('span', { class: 'paso-n' }, hechos[i] ? '✓' : String(i + 1)), h('span', null, p),
      h('span', { class: 'peq' }, hechos[i] ? 'Completado' : (i === siguiente && !cerrado ? 'Siguiente paso' : 'Pendiente')))));
}

function pagosVista(ec, pendientes, ctxBase, refrescar, evento) {
  const ctx = { ...ctxBase, estadoCuentaId: ec.estadoCuentaId, contratoId: ec.contratoId };
  const mios = pendientes.filter((p) => p.estadoCuentaId === ec.estadoCuentaId);
  const ob = (titulo, o, pend) => {
    const vacia = !o || !o.estado;
    const abono = pend ? pend.pagado : (o && o.estado === 'Liquidada' ? o.importe : null);
    return h('div', { class: 'obligacion' }, h('h4', null, titulo),
      vacia ? h('p', { class: 'peq' }, 'Todavía no existe esta obligación.') : [
        h('div', { class: 'fila-estado' }, insignia(o.estado), o.plazoVencido === true ? h('span', { class: 'etiqueta-alerta' }, 'Plazo vencido') : null),
        datos(...[['Importe', fmtImporte(o.importe)], ['Pagado', fmtImporte(abono)], ['Saldo', pend ? fmtImporte(pend.saldo) : (o.estado === 'Liquidada' ? '0.00' : '—')],
          ['Fecha límite', fmtFechaHora(o.fechaLimite)], o.resultadoRegularizacion ? ['Regularización', o.resultadoRegularizacion] : null].filter(Boolean)),
        o.plazoVencido === true ? h('p', { class: 'caja-aviso' }, 'El plazo de pago aparece vencido. Revisa la fecha límite y el estado actual de la cuenta.') : null]);
  };
  const anticipoPend = mios.find((p) => p.concepto === 'Anticipo');
  const saldoPend = mios.find((p) => p.concepto === 'SaldoContratoOriginal');
  const acciones = [];
  if (mios.length) acciones.push(botonAccion(ACCIONES.registrarPago, { ...ctx, obligaciones: mios }, refrescar, { clase: 'btn btn-primario' }));
  if (ec.pagosRegistrados.some((p) => p.estado === 'Registrado') || registro.pagos(ec.estadoCuentaId).some((p) => p.estado === 'Registrado')) acciones.push(botonAccion(ACCIONES.verificarPago, ctx, refrescar));
  const saldo = ec.saldoContratoOriginal;
  if (saldo.estado === 'Pendiente' && saldo.plazoVencido) acciones.push(botonAccion(ACCIONES.vencimientoSaldo, ctx, refrescar));
  if (saldo.estado === 'Vencida') acciones.push(botonAccion(ACCIONES.protocoloCobro, ctx, refrescar), botonAccion(ACCIONES.regularizacion, ctx, refrescar));

  return tarjeta(`Estado de cuenta ${ec.estadoCuentaId}`, h('div', null,
    h('div', { class: 'rejilla-2' }, ob('Anticipo (mínimo 30 %)', ec.anticipo, anticipoPend), ob('Saldo del contrato original', ec.saldoContratoOriginal, saldoPend)),
    h('p', { class: 'peq' }, 'El anticipo es un mínimo del 30 %: puede cubrirse con varios pagos parciales que se acumulan (criterio adoptado por el equipo, aún sin aprobación formal).'),
    h('h4', null, 'Pagos registrados'),
    tabla([
      { titulo: 'Concepto', celda: (p) => p.concepto }, { titulo: 'Importe', clase: 'num', celda: (p) => fmtImporte(p.importe) },
      { titulo: 'Fecha del pago', celda: (p) => fmtFechaHora(p.fecha) }, { titulo: 'Estado', celda: (p) => insignia(p.estado) },
      { titulo: 'Verificado', celda: (p) => (p.verificadoEn ? fmtFechaHora(p.verificadoEn) : '—') },
    ], ec.pagosRegistrados, { vacioTitulo: 'Aún no hay pagos registrados', vacioDetalle: 'Cuando se registre un pago aparecerá aquí con su estado.' }),
    ec.obligacionesAdicionales.length ? [h('h4', null, 'Otras obligaciones'), tabla([
      { titulo: 'Concepto', celda: (o) => o.concepto }, { titulo: 'Importe', clase: 'num', celda: (o) => fmtImporte(o.importe) },
      { titulo: 'Plazo', celda: (o) => fmtFechaHora(o.plazo) }, { titulo: 'Estado', celda: (o) => insignia(o.estado) }], ec.obligacionesAdicionales)] : null,
    ec.devoluciones.length ? [h('h4', null, 'Devoluciones'), tabla([
      { titulo: 'Tipo', celda: (d) => d.tipo }, { titulo: 'Concepto', celda: (d) => d.concepto }, { titulo: 'Importe', clase: 'num', celda: (d) => fmtImporte(d.importe) },
      { titulo: 'Fecha límite', celda: (d) => fmtFechaHora(d.fechaLimite) }, { titulo: 'Estado', celda: (d) => insignia(d.estado) },
      { titulo: 'Acción', celda: (d) => (d.estado === 'Pendiente' ? botonAccion(ACCIONES.ejecutarDevolucion, { ...ctx, devolucionId: d.devolucionId, importe: d.importe, concepto: d.concepto }, refrescar, { clase: 'btn btn-peq' }) : (d.fechaDevolucion ? fmtFechaHora(d.fechaDevolucion) : '—')) },
    ], ec.devoluciones)] : null,
    registro.pagos(ec.estadoCuentaId).length ? h('p', { class: 'peq' }, 'Pagos registrados desde este navegador (para verificarlos): ', registro.pagos(ec.estadoCuentaId).map((p) => copiable(p.pagoId))) : null),
  { acciones });
}

export async function evento(contenedor, [eventoId]) {
  const id = decodeURIComponent(eventoId || '');
  const refrescar = () => evento(contenedor, [eventoId]);
  contenedor.replaceChildren(cargando('Consultando el evento…'));
  let admin; let pagos; let pendientes; let solicitudes; let accionesPend;
  try {
    admin = await GET(`/eventos/${encodeURIComponent(id)}/administracion`);
    [pagos, pendientes, solicitudes, accionesPend] = await Promise.all([
      GET(`/eventos/${encodeURIComponent(id)}/pagos`), GET('/pagos-pendientes', { evento_id: id }), GET('/solicitudes', { evento_id: id }),
      GET(`/eventos/${encodeURIComponent(id)}/solicitudes-pendientes`)]);
  } catch (e) { contenedor.replaceChildren(cajaError(e, refrescar), h('a', { href: '#/eventos', class: 'btn' }, 'Volver a eventos')); return; }

  registro.recordarEvento(id, `${admin.tipoEvento} · ${id}`);
  const estado = admin.estadoEvento;
  const confirmados = admin.contratos.filter((c) => c.estado === 'Contratación confirmada');
  const base = { eventoId: id, servicios: admin.proveedores.map((s) => s.servicio), contratos: confirmados, evento: admin };
  const ecs = pagos.estadosCuenta;

  // ----- encabezado
  const cabecera = h('header', { class: 'pagina-cab' },
    h('a', { href: '#/eventos', class: 'migas' }, '← Eventos'),
    h('h1', null, admin.tipoEvento, ' ', insignia(estado)),
    h('p', null, `${fmtFechaHora(admin.fechaHora)} · ${admin.lugar} · ${admin.invitadosAproximados} invitados aproximados`),
    AYUDA_ESTADO[estado] ? h('p', { class: 'peq' }, AYUDA_ESTADO[estado]) : null,
    h('p', { class: 'peq' }, 'Identificador: ', copiable(id)));

  const resumen = tarjeta('Resumen económico', datos(
    ['Pagos realizados (verificados)', fmtImporte(admin.pagosRealizados)], ['Saldo pendiente del contrato original', fmtImporte(admin.saldoPendienteContratoOriginal)],
    ['Contratos', admin.contratos.length]));

  // ----- propuestas (solo registro local; la API no consulta propuestas)
  const propuestas = registro.propuestas(id);
  const bloquePropuestas = tarjeta('Propuestas', h('div', null,
    h('p', { class: 'peq' }, 'La API permite crear y gestionar propuestas, pero no consultarlas. Aquí aparecen las que se crearon desde este navegador, con el último resultado que informó el sistema. El sistema valida cada operación.'),
    propuestas.length ? tabla([
      { titulo: 'Propuesta', celda: (p) => copiable(p.id) }, { titulo: 'Versión vigente', celda: (p) => `v${p.version}` },
      { titulo: 'Último resultado', celda: (p) => p.resultado || '—' },
      { titulo: 'Acciones', celda: (p) => h('div', { class: 'acciones' },
        botonAccion(ACCIONES.aceptarPropuesta, { propuestaId: p.id, versionId: p.versionId }, refrescar, { clase: 'btn btn-peq' }),
        botonAccion(ACCIONES.nuevaVersion, { propuestaId: p.id, servicios: base.servicios }, refrescar, { clase: 'btn btn-peq' }),
        botonAccion(ACCIONES.prepararContrato, { propuestaId: p.id }, refrescar, { clase: 'btn btn-peq' }),
        botonAccion(ACCIONES.cerrarPropuesta, { propuestaId: p.id }, refrescar, { clase: 'btn btn-peq btn-peligro-suave' })) },
    ], propuestas) : vacio('Sin propuestas registradas en este navegador', 'Crea la primera propuesta del evento.')),
  { acciones: estado === 'En gestión' ? botonAccion(ACCIONES.crearPropuesta, base, refrescar, { clase: 'btn btn-primario' }) : null });

  // ----- contratos
  const accionesContrato = (c) => {
    const ctx = { ...base, contratoId: c.contratoId }; const ec = ecs.find((x) => x.contratoId === c.contratoId);
    const out = [];
    if (c.estado === 'En preparación') out.push(botonAccion(ACCIONES.comunicarPolitica, ctx, refrescar, { clase: 'btn btn-peq' }), botonAccion(ACCIONES.firmarContrato, ctx, refrescar, { clase: 'btn btn-peq btn-primario' }));
    if (c.estado === 'Firmado') {
      if (!ec || ec.anticipo.estado !== 'Liquidada') out.push(botonAccion(ACCIONES.seguimientoAnticipo, ctx, refrescar, { clase: 'btn btn-peq' }));
      if (ec && ec.anticipo.estado === 'Liquidada') out.push(botonAccion(ACCIONES.confirmarContratacion, ctx, refrescar, { clase: 'btn btn-peq btn-primario' }));
    }
    return out.length ? h('div', { class: 'acciones' }, out) : h('span', { class: 'peq' }, 'Sin acciones disponibles');
  };
  const bloqueContratos = tarjeta('Contratación', h('div', null, avance(admin.contratos, ecs),
    h('p', { class: 'peq' }, 'Antes de firmar debe comunicarse al Cliente la política de no reembolso. La confirmación exige contrato firmado, política comunicada y anticipo verificado; el sistema lo comprueba.'),
    tabla([
      { titulo: 'Contrato', celda: (c) => copiable(c.contratoId) }, { titulo: 'Costo total', clase: 'num', celda: (c) => fmtImporte(c.costoTotal) },
      { titulo: 'Estado', celda: (c) => insignia(c.estado) }, { titulo: 'Acciones', celda: accionesContrato },
    ], admin.contratos, { vacioTitulo: 'Todavía no hay contrato', vacioDetalle: 'Acepta una propuesta y prepara el contrato desde la sección de propuestas.' })));

  // ----- pagos
  const bloquesPagos = ecs.length ? ecs.map((ec) => pagosVista(ec, pendientes.pagos, base, refrescar, admin))
    : [tarjeta('Pagos', vacio('Todavía no hay estado de cuenta', 'Se crea al firmarse el contrato.'))];

  // ----- solicitudes
  const puedeCambio = estado === 'En organización' && confirmados.length;
  const puedeAdicional = ['En organización', 'En ejecución'].includes(estado) && confirmados.length;
  const nuevas = [];
  if (puedeCambio) nuevas.push(botonAccion(ACCIONES.nuevoCambio, base, refrescar, { texto: 'Solicitar cambio' }), botonAccion(ACCIONES.nuevaSustitucion, { ...base, servicios: admin.proveedores }, refrescar, { texto: 'Sustituir proveedor' }));
  if (puedeAdicional) nuevas.push(botonAccion(ACCIONES.nuevoServicioAdicional, base, refrescar, { texto: 'Solicitar servicio adicional' }));
  const bloqueSolicitudes = tarjeta('Solicitudes del evento', h('div', null,
    !confirmados.length ? h('p', { class: 'peq' }, 'Los cambios, servicios adicionales y sustituciones solo se registran con la contratación confirmada.') : null,
    estado === 'En ejecución' ? h('p', { class: 'peq' }, 'El evento ya inició: ya no se aceptan cambios. Un servicio adicional presentado ahora se registra como «No procedente», porque ya no hay tiempo de atenderlo.') : null,
    tablaSolicitudes(solicitudes.solicitudes, refrescar, { pendientes: Object.fromEntries(accionesPend.solicitudes.map((x) => [x.solicitudId, x])) })), { acciones: nuevas });

  // ----- servicios y proveedores
  // Los servicios contratados nacen al confirmarse la contratación; antes solo existen los servicios pedidos al registrar el evento.
  const solicitados = admin.serviciosSolicitados || [];
  const gestionable = estado === 'En organización';
  const motivoSinAccion = (s) => {
    if (s.estado === 'Sin proveedor asignado') return `El proveedor se asigna solo con el evento En organización; este evento está ${estado}.`;
    if (s.estado === 'Pendiente de confirmación del proveedor') return `La respuesta del proveedor se registra solo con el evento En organización; este evento está ${estado}.`;
    if (s.estado === 'Proveedor no disponible') return 'Para cambiar de proveedor registra una sustitución (botón «Sustituir proveedor» de Solicitudes del evento).';
    return 'Sin acciones pendientes.';
  };
  const accionesServicio = (s) => {
    const ctx = { ...base, servicioId: s.servicioContratadoId, servicio: s.servicio, proveedorId: s.proveedorId, proveedorNombre: s.proveedorNombre };
    const botones = puede('proveedores.asignar') ? [h('button', { type: 'button', class: 'btn btn-peq', onclick: () => verDisponibilidad(id, s) }, 'Ver disponibilidad')] : [];
    if (gestionable && s.estado === 'Sin proveedor asignado' && puede('proveedores.asignar')) botones.push(h('button', { type: 'button', class: 'btn btn-peq btn-primario', onclick: () => asignarConCandidatos(ctx, refrescar) }, 'Asignar proveedor'));
    else if (gestionable && s.estado === 'Pendiente de confirmación del proveedor') botones.push(botonAccion(ACCIONES.respuestaProveedor, ctx, refrescar, { clase: 'btn btn-peq btn-primario' }));
    else botones.push(h('span', { class: 'peq' }, motivoSinAccion(s)));
    return h('div', { class: 'acciones' }, botones);
  };
  let contenidoServicios;
  if (admin.proveedores.length) {
    contenidoServicios = tabla([
      { titulo: 'Servicio', celda: (s) => s.servicio }, { titulo: 'Proveedor', celda: celdaProveedor }, { titulo: 'Estado', celda: (s) => insignia(s.estado) },
      { titulo: 'Acciones', celda: accionesServicio },
    ], admin.proveedores, {});
  } else if (solicitados.length) {
    contenidoServicios = h('div', null,
      h('p', { class: 'peq' }, ['Cerrado sin contratación', 'Cancelado'].includes(estado)
        ? `Estos son los servicios que se pidieron al registrar el evento. El evento está ${estado} y no llegó a contratarse, por lo que no se asignan proveedores.`
        : 'Estos son los servicios que se pidieron al registrar el evento. Todavía no están contratados: los proveedores se asignan cuando la contratación se confirma y el evento pasa a En organización.'),
      tabla([{ titulo: 'Servicio solicitado', celda: (x) => x }, { titulo: 'Situación', celda: () => h('span', { class: 'peq' }, 'Pendiente de contratación') }], solicitados, {}));
  } else {
    contenidoServicios = vacio('Sin servicios registrados', 'Este evento no tiene servicios solicitados ni contratados.');
  }
  const bloqueProveedores = tarjeta('Servicios y proveedores', contenidoServicios,
    { acciones: [h('a', { class: 'btn btn-peq', href: '#/proveedores' }, 'Ver catálogo de proveedores')] });

  // ----- ciclo de vida
  const ciclo = [];
  if (estado === 'En organización') ciclo.push(botonAccion(ACCIONES.iniciarEvento, base, refrescar), botonAccion(ACCIONES.cancelarEvento, base, refrescar, { clase: 'btn btn-peligro-suave' }));
  if (estado === 'En ejecución') ciclo.push(botonAccion(ACCIONES.finalizarEvento, base, refrescar, { clase: 'btn btn-primario' }));
  if (estado === 'Cancelado') ciclo.push(botonAccion(ACCIONES.revisionAdministrativa, base, refrescar));
  if (ecs.some((e) => e.saldoContratoOriginal.estado === 'Vencida') && !['Cancelado', 'Finalizado', 'Cerrado sin contratación'].includes(estado)) {
    ciclo.push(botonAccion(ACCIONES.cancelarPorRegularizacion, base, refrescar, { clase: 'btn btn-peligro-suave' }));
  }
  const bloqueCiclo = tarjeta('Ciclo de vida del evento', h('div', null,
    h('p', null, 'Estado actual: ', insignia(estado), ' ', AYUDA_ESTADO[estado] || ''),
    h('p', { class: 'peq' }, 'El inicio y el cierre por fecha los aplica automáticamente el trabajador del sistema; esta pantalla muestra el estado que informa el servidor.'),
    ciclo.length ? h('div', { class: 'acciones' }, ciclo) : h('p', { class: 'peq' }, 'No hay operaciones disponibles en este estado.')));

  contenedor.replaceChildren(cabecera, h('div', { class: 'rejilla-detalle' }, resumen, bloqueCiclo), bloqueContratos, bloquePropuestas, ...bloquesPagos, bloqueSolicitudes, bloqueProveedores);
}

export function tablaSolicitudes(lista, refrescar, { conEvento = false, pendientes = {} } = {}) {
  return tabla([
    conEvento ? { titulo: 'Evento', celda: (s) => h('a', { href: `#/evento/${s.eventoId}` }, s.eventoId) } : null,
    { titulo: 'Tipo', celda: (s) => s.tipoSolicitud },
    { titulo: 'Solicitud', celda: (s) => h('div', null, copiable(s.solicitudId), s.servicioAfectado ? h('div', { class: 'peq' }, s.servicioAfectado) : null) },
    { titulo: 'Estado', celda: (s) => h('div', null, insignia(s.estadoActual), AYUDA_ESTADO[s.estadoActual] ? h('div', { class: 'peq' }, AYUDA_ESTADO[s.estadoActual]) : null,
      pendientes[s.solicitudId] ? h('div', { class: 'peq' }, `Pendiente: ${pendientes[s.solicitudId].accionPendiente}`) : null) },
    { titulo: 'Acciones', celda: (s) => {
      const a = accionesDeSolicitud(s.tipoSolicitud, s.estadoActual);
      return a.length ? h('div', { class: 'acciones' }, a.map((k) => botonAccion(ACCIONES[k], { solicitudId: s.solicitudId, eventoId: s.eventoId }, refrescar, { clase: 'btn btn-peq' })))
        : h('span', { class: 'peq' }, s.pendiente ? 'Espera una acción externa (por ejemplo, regularizar el saldo)' : 'Sin acciones: estado final'); } },
  ].filter(Boolean), lista, { vacioTitulo: 'No hay solicitudes', vacioDetalle: 'Las solicitudes de cambio, servicio adicional y sustitución aparecerán aquí.' });
}

/** Abre la asignación con los proveedores que el sistema informa como disponibles; sin candidatos explica cómo continuar. */
async function asignarConCandidatos(ctx, refrescar) {
  let candidatos;
  try { candidatos = await candidatosParaAsignar(ctx.eventoId, ctx.servicioId); } catch (e) { aviso('error', e.message); return; }
  if (!candidatos.length) {
    dialogoInfo('No hay proveedores disponibles', h('div', null,
      h('p', null, `El sistema no informa ningún proveedor disponible para «${ctx.servicio}».`),
      h('p', null, 'Registra al proveedor en el catálogo indicando que ofrece ese servicio (el nombre debe coincidir con el del servicio contratado) y vuelve a intentarlo.'),
      h('a', { class: 'btn btn-primario', href: '#/proveedores' }, 'Ir al catálogo de proveedores')));
    return;
  }
  await ejecutarAccion(ACCIONES.asignarProveedor, { ...ctx, candidatos }, refrescar);
}

async function verDisponibilidad(eventoId, s) {
  try {
    const [r, catalogo] = await Promise.all([consultarDisponibilidad(eventoId, s.servicioContratadoId), GET('/proveedores')]);
    const nombres = Object.fromEntries(catalogo.datos.proveedores.map((p) => [p.proveedorId, p.nombre]));
    const etiqueta = (pid) => (nombres[pid] ? `${nombres[pid]} (${pid})` : `${pid} (no figura en el catálogo)`);
    const d = r.datos || {};
    const lista = (ids, vacioTexto) => (ids && ids.length ? h('ul', null, ids.map((x) => h('li', null, etiqueta(x)))) : h('p', { class: 'peq' }, vacioTexto));
    dialogoInfo(`Disponibilidad de «${s.servicio}»`, h('div', null,
      h('h4', null, 'Proveedores disponibles'), lista(d.disponibles, 'Ningún proveedor figura disponible. Registra uno que ofrezca este servicio en el catálogo de proveedores.'),
      d.no_disponibles && d.no_disponibles.length ? h('div', null, h('h4', null, 'Proveedores no disponibles'), lista(d.no_disponibles, '')) : null));
  } catch (e) { aviso('error', e.message); }
}
