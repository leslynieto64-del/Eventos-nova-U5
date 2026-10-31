/* Operaciones de negocio de la API, declaradas una sola vez: formulario, texto de confirmación y petición real.
   Cada acción recibe un «contexto» con los identificadores que necesita (evento, contrato, estado de cuenta, solicitud…). */
import { POST, GET } from './api.js';
import { fmtImporte, fmtFechaHora } from './negocio.js';
import { registro } from './registro.js';

const f = (nombre, etiqueta, tipo, extra) => ({ nombre, etiqueta, tipo, ...extra });
const FECHA = (nombre, etiqueta, ayuda) => f(nombre, etiqueta, 'fechahora', {
  requerido: true, valor: 'AHORA', ayuda: ayuda || 'Fecha y hora en que ocurrió, en la hora de negocio (Ciudad de México). Se propone la actual.' });
const SI_NO = (v) => (v ? 'Sí' : 'No');
const lista = (v) => v.join(', ');

const CAMPOS_PROPUESTA = (ctx) => [
  f('servicios', 'Servicios incluidos', 'lista', { requerido: true, valor: (ctx.servicios || []).join(', '), ayuda: 'Separa los servicios con comas.' }),
  f('proveedores_considerados', 'Proveedores considerados', 'lista', { requerido: true, ayuda: 'Identificadores de proveedor separados con comas (por ejemplo, PV-1, PV-2).' }),
  f('costo_total', 'Costo total', 'importe', { requerido: true, positivo: true, ayuda: 'Importe total de la propuesta.' }),
  f('condiciones', 'Condiciones', 'textarea', { requerido: true }),
];
const cuerpoPropuesta = (v) => ({ servicios: v.servicios, proveedores_considerados: v.proveedores_considerados, costo_total: v.costo_total, condiciones: v.condiciones });

const campoDecision = (actorPorDefecto) => [
  f('actor', 'Quién decide', 'texto', { requerido: true, valor: actorPorDefecto }),
  f('aprobada', 'Se aprueba', 'bool', { valor: true }),
  FECHA('fecha', 'Fecha de la decisión'),
  f('motivo', 'Motivo', 'textarea', { ayuda: 'Recomendado cuando la decisión es un rechazo.' }),
];
const cuerpoDecision = (v) => ({ actor: v.actor, aprobada: v.aprobada, fecha: v.fecha, motivo: v.motivo || '' });

const DATOS_PROPUESTOS = [
  f('cambiar_datos', 'El cambio modifica los datos del evento (tipo, fecha, lugar o invitados)', 'bool', {}),
  f('tipo', 'Tipo de evento', 'texto', { requerido: true, visibleSi: (v) => v.cambiar_datos }),
  f('fecha_hora', 'Nueva fecha y hora del evento', 'fechahora', { requerido: true, visibleSi: (v) => v.cambiar_datos }),
  f('lugar', 'Lugar', 'texto', { requerido: true, visibleSi: (v) => v.cambiar_datos }),
  f('invitados_aproximados', 'Invitados aproximados', 'entero', { requerido: true, minimo: 1, visibleSi: (v) => v.cambiar_datos }),
];

export const ACCIONES = {
  // ------------------------------------------------------------ eventos y propuestas
  registrarEvento: {
    titulo: 'Registrar evento', textoEnviar: 'Registrar evento',
    intro: () => 'Registra un evento nuevo. Quedará En gestión hasta que se confirme la contratación.',
    campos: () => [
      f('cliente_id', 'Identificador del cliente', 'texto', { requerido: true, ayuda: 'El sistema no tiene un catálogo de clientes: escribe el identificador que usa Eventos Nova (por ejemplo, CL-1).' }),
      f('tipo', 'Tipo de evento', 'texto', { requerido: true, ayuda: 'Por ejemplo: Boda, Conferencia, Cumpleaños.' }),
      f('fecha_hora', 'Fecha y hora del evento', 'fechahora', { requerido: true }),
      f('lugar', 'Lugar', 'texto', { requerido: true }),
      f('invitados_aproximados', 'Invitados aproximados', 'entero', { requerido: true, minimo: 1 }),
      f('servicios', 'Servicios solicitados', 'lista', { requerido: true, ayuda: 'Separa los servicios con comas (por ejemplo, Banquete, Música).' }),
    ],
    enviar: (v) => POST('/eventos', { cliente_id: v.cliente_id, datos: { tipo: v.tipo, fecha_hora: v.fecha_hora, lugar: v.lugar, invitados_aproximados: Number(v.invitados_aproximados) }, servicios: v.servicios }),
    despues: (r, ctx) => ctx.irA && r.evento_id && ctx.irA(`#/evento/${encodeURIComponent(r.evento_id)}`),   // esta respuesta no usa «datos»
  },
  crearPropuesta: {
    titulo: 'Crear propuesta', textoEnviar: 'Crear propuesta',
    intro: (c) => `Crea la primera versión de la propuesta del evento ${c.eventoId}. El sistema asigna la fecha de la versión.`,
    campos: CAMPOS_PROPUESTA,
    resumen: (v) => `Se creará una propuesta con costo total ${fmtImporte(v.costo_total)} para los servicios: ${lista(v.servicios)}.`,
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/propuestas`, cuerpoPropuesta(v)),
    despues: (r, c) => registro.guardarPropuesta({ id: r.propuesta_id, eventoId: c.eventoId, version: 1, versionId: `${r.propuesta_id}-v1`, resultado: 'Creada' }),   // sin «datos»
  },
  nuevaVersion: {
    titulo: 'Generar nueva versión', textoEnviar: 'Generar versión',
    intro: (c) => `Genera una nueva versión vigente de la propuesta ${c.propuestaId}.`,
    campos: CAMPOS_PROPUESTA,
    enviar: (v, c) => POST(`/propuestas/${encodeURIComponent(c.propuestaId)}/versiones`, cuerpoPropuesta(v)),
    despues: (r, c) => registro.guardarPropuesta({ id: c.propuestaId, version: r.datos.numero, versionId: r.datos.version_id, resultado: 'Nueva versión vigente' }),
  },
  aceptarPropuesta: {
    titulo: 'Aceptar propuesta', textoEnviar: 'Aceptar propuesta',
    intro: (c) => `Registra que el Cliente acepta la versión vigente de la propuesta ${c.propuestaId}.`,
    campos: (c) => [f('version_id', 'Versión que se acepta', 'texto', { requerido: true, valor: c.versionId,
      ayuda: 'Debe ser la versión vigente. Si no coincide, el sistema rechazará la aceptación y te lo indicará.' })],
    resumen: (v) => `Se aceptará la versión ${v.version_id}. Después de aceptarla ya no se pueden generar versiones nuevas.`,
    enviar: (v, c) => POST(`/propuestas/${encodeURIComponent(c.propuestaId)}/aceptacion`, { version_id: v.version_id }),
    despues: (r, c) => registro.guardarPropuesta({ id: c.propuestaId, resultado: 'Aceptada' }),
  },
  cerrarPropuesta: {
    titulo: 'Cerrar por no aceptación', textoEnviar: 'Cerrar propuesta', peligro: true,
    intro: (c) => `Cierra la propuesta ${c.propuestaId} porque el Cliente no la aceptó. El evento sigue En gestión.`,
    campos: () => [f('motivo', 'Motivo', 'textarea', { requerido: true })],
    resumen: () => 'La propuesta se cerrará por no aceptación y no podrá volver a abrirse.',
    enviar: (v, c) => POST(`/propuestas/${encodeURIComponent(c.propuestaId)}/cierre-por-no-aceptacion`, { motivo: v.motivo }),
    despues: (r, c) => registro.guardarPropuesta({ id: c.propuestaId, resultado: 'Cerrada por no aceptación' }),
  },
  prepararContrato: {
    titulo: 'Preparar contrato', textoEnviar: 'Preparar contrato',
    intro: (c) => `Prepara el contrato a partir de la propuesta aceptada ${c.propuestaId}.`,
    campos: () => [f('politica_incluida', 'El contrato incluye la política de no reembolso', 'bool', { valor: true })],
    enviar: (v, c) => POST(`/propuestas/${encodeURIComponent(c.propuestaId)}/contrato`, { politica_incluida: v.politica_incluida }),
    despues: (r, c) => registro.guardarPropuesta({ id: c.propuestaId, contratoId: r.datos.contrato_id, resultado: 'Contrato preparado' }),
  },

  // ------------------------------------------------------------ contrato
  comunicarPolitica: {
    titulo: 'Comunicar política de no reembolso', textoEnviar: 'Registrar comunicación',
    intro: (c) => `Registra que se comunicó al Cliente la política de no reembolso del contrato ${c.contratoId}. Debe hacerse antes de la firma.`,
    campos: () => [FECHA('fecha', 'Fecha de la comunicación')],
    enviar: (v, c) => POST(`/contratos/${encodeURIComponent(c.contratoId)}/comunicacion-politica-no-reembolso`, { fecha: v.fecha }),
  },
  firmarContrato: {
    titulo: 'Registrar firma del contrato', textoEnviar: 'Registrar firma',
    intro: (c) => `Registra la firma del contrato ${c.contratoId}. Esta pantalla solo anota que la firma ocurrió; no es una firma electrónica.`,
    aviso: 'Antes de firmar, confirma que la política de no reembolso ya fue comunicada al Cliente.',
    campos: () => [FECHA('fecha', 'Fecha de la firma'),
      f('politica_ok', 'Confirmo que la política de no reembolso fue comunicada al Cliente', 'bool', { requerido: true, ayuda: 'El sistema comprueba este paso y rechazará la firma si no se registró la comunicación.' })],
    resumen: (v) => `Se registrará la firma del contrato con fecha ${fmtFechaHora(v.fecha)}.`,
    enviar: async (v, c) => {
      if (!v.politica_ok) { const { ErrorApi } = await import('./api.js'); throw new ErrorApi('negocio', 'Confirma que la política de no reembolso fue comunicada antes de registrar la firma.'); }
      return POST(`/contratos/${encodeURIComponent(c.contratoId)}/firma`, { fecha: v.fecha });
    },
  },
  seguimientoAnticipo: {
    titulo: 'Dar seguimiento al anticipo', textoEnviar: 'Registrar seguimiento',
    intro: (c) => `Registra el contacto con el Cliente por el anticipo pendiente del contrato ${c.contratoId}.`,
    aviso: 'Si indicas que no hubo pago tras el seguimiento, el sistema puede cerrar la contratación sin confirmar.',
    campos: () => [FECHA('fecha', 'Fecha del contacto'),
      f('resultado_contacto', 'Resultado del contacto', 'textarea', { requerido: true }),
      f('sin_pago_tras_seguimiento', 'Ya pasó el plazo del seguimiento y el Cliente no pagó', 'bool', {})],
    resumen: (v) => (v.sin_pago_tras_seguimiento ? 'Se intentará cerrar la contratación porque no hubo pago tras el seguimiento.' : 'Se registrará el seguimiento del anticipo.'),
    peligro: false,
    enviar: (v, c) => POST(`/contratos/${encodeURIComponent(c.contratoId)}/seguimiento-anticipo`, { fecha: v.fecha, resultado_contacto: v.resultado_contacto, sin_pago_tras_seguimiento: v.sin_pago_tras_seguimiento }),
  },
  confirmarContratacion: {
    titulo: 'Confirmar la contratación', textoEnviar: 'Confirmar contratación',
    intro: (c) => `Confirma la contratación del contrato ${c.contratoId}. Requiere contrato firmado, política comunicada y anticipo verificado.`,
    resumen: () => 'Se confirmará la contratación. Si falta algún requisito, el sistema lo indicará y no se cambiará nada.',
    enviar: (v, c) => POST(`/contratos/${encodeURIComponent(c.contratoId)}/confirmacion`),
  },

  // ------------------------------------------------------------ pagos
  registrarPago: {
    titulo: 'Registrar pago', textoEnviar: 'Registrar pago',
    intro: (c) => `Registra un pago recibido del Cliente en el estado de cuenta ${c.estadoCuentaId}. No se procesa ningún cobro: solo se anota el pago ya efectuado.`,
    campos: (c) => [
      f('obligacion_id', 'Obligación que se paga', 'select', { requerido: true, opciones: c.obligaciones.map((o) => ({ valor: o.obligacionId, texto: `${o.concepto} — saldo ${fmtImporte(o.saldo)}${o.estado === 'Vencida' ? ' (vencida)' : ''}` })) }),
      f('importe', 'Importe pagado', 'importe', { requerido: true, positivo: true, ayuda: 'Los pagos parciales se acumulan; el anticipo mínimo puede cubrirse con varios pagos.' }),
      FECHA('fecha', 'Fecha en que el Cliente efectuó el pago', 'Es la fecha efectiva del pago según el comprobante; decide si cumplió el plazo.'),
      f('comprobante', 'Referencia del comprobante', 'texto', { requerido: true, ayuda: 'No se puede repetir el mismo comprobante en una misma obligación.' }),
      f('verificar_ahora', 'Verificar el pago ahora', 'bool', { valor: true, ayuda: 'Si lo desmarcas, el pago queda Registrado y se verifica después.' }),
    ],
    resumen: (v, c) => { const o = c.obligaciones.find((x) => x.obligacionId === v.obligacion_id); return `Se registrará un pago de ${fmtImporte(v.importe)} para «${o ? o.concepto : v.obligacion_id}»${v.verificar_ahora ? ' y se verificará de inmediato' : ''}.`; },
    enviar: (v, c) => POST(`/estados-cuenta/${encodeURIComponent(c.estadoCuentaId)}/pagos`, { obligacion_id: v.obligacion_id, importe: v.importe, fecha: v.fecha, comprobante: v.comprobante, verificar_ahora: v.verificar_ahora }),
    despues: (r, c) => r.datos.pago_id && registro.guardarPago({ pagoId: r.datos.pago_id, estadoCuentaId: c.estadoCuentaId, eventoId: c.eventoId, estado: r.datos.estado }),
    exito: (r) => (r.datos.pago_id ? `Identificador del pago: ${r.datos.pago_id}` : null),
  },
  verificarPago: {
    titulo: 'Verificar pago', textoEnviar: 'Verificar pago',
    intro: (c) => `Verifica un pago que quedó Registrado en el estado de cuenta ${c.estadoCuentaId}.`,
    campos: (c) => [
      f('pago_id', 'Identificador del pago', 'texto', { requerido: true, valor: (registro.pagos(c.estadoCuentaId).find((p) => p.estado === 'Registrado') || {}).pagoId,
        ayuda: 'La consulta de pagos no muestra identificadores; se propone el último pago Registrado desde este navegador. Puedes escribir otro.' }),
      FECHA('verificado_en', 'Fecha de la verificación')],
    enviar: (v, c) => POST(`/estados-cuenta/${encodeURIComponent(c.estadoCuentaId)}/pagos/${encodeURIComponent(v.pago_id)}/verificacion`, { verificado_en: v.verificado_en }),
    despues: (r, c) => r.datos.pago_id && registro.guardarPago({ pagoId: r.datos.pago_id, estadoCuentaId: c.estadoCuentaId, estado: r.datos.estado }),
  },
  vencimientoSaldo: {
    titulo: 'Registrar vencimiento del saldo', textoEnviar: 'Registrar vencimiento',
    intro: (c) => `El sistema comprobará si el saldo del contrato original del estado de cuenta ${c.estadoCuentaId} ya venció y, si es así, lo registrará.`,
    resumen: () => 'Si el plazo del saldo terminó sin cubrirse, el saldo quedará Vencido y se bloquearán solicitudes nuevas.',
    enviar: (v, c) => POST(`/estados-cuenta/${encodeURIComponent(c.estadoCuentaId)}/vencimiento-saldo-original`),
  },
  protocoloCobro: {
    titulo: 'Activar protocolo de cobro', textoEnviar: 'Activar protocolo',
    intro: (c) => `Activa el protocolo de cobro del saldo vencido del estado de cuenta ${c.estadoCuentaId}.`,
    campos: () => [FECHA('comunicado_en', 'Fecha de la comunicación al Cliente'),
      f('importe_moratorio', 'Importe de los cargos moratorios', 'importe', { requerido: true, positivo: true }),
      f('seguimiento', 'Seguimiento realizado', 'textarea', { requerido: true })],
    resumen: (v) => `Se activará el protocolo de cobro con cargos moratorios de ${fmtImporte(v.importe_moratorio)}.`,
    enviar: (v, c) => POST(`/estados-cuenta/${encodeURIComponent(c.estadoCuentaId)}/protocolo-cobro`, { comunicado_en: v.comunicado_en, importe_moratorio: v.importe_moratorio, seguimiento: v.seguimiento }),
  },
  regularizacion: {
    titulo: 'Registrar regularización del saldo', textoEnviar: 'Registrar resultado',
    intro: (c) => `Registra el resultado de la regularización del saldo vencido del estado de cuenta ${c.estadoCuentaId}.`,
    campos: () => [FECHA('revisado_en', 'Fecha de la revisión')],
    resumen: () => 'El sistema determinará si el saldo quedó regularizado dentro del plazo y registrará el resultado.',
    enviar: (v, c) => POST(`/estados-cuenta/${encodeURIComponent(c.estadoCuentaId)}/regularizacion`, { revisado_en: v.revisado_en }),
  },
  ejecutarDevolucion: {
    titulo: 'Registrar devolución efectuada', textoEnviar: 'Registrar devolución',
    intro: (c) => `Registra que se devolvió ${fmtImporte(c.importe)} (${c.concepto}). La devolución real se hace fuera del sistema.`,
    campos: () => [f('comprobante', 'Comprobante de la devolución', 'texto', { ayuda: 'Opcional. Si lo dejas vacío, el sistema usa su ejecutor de devoluciones (hoy una simulación).' })],
    resumen: (v, c) => `Se registrará como efectuada la devolución de ${fmtImporte(c.importe)}.`,
    enviar: (v, c) => POST(`/estados-cuenta/${encodeURIComponent(c.estadoCuentaId)}/devoluciones/${encodeURIComponent(c.devolucionId)}/ejecucion`, v.comprobante ? { comprobante: v.comprobante } : undefined),
  },

  // ------------------------------------------------------------ ciclo de vida del evento
  iniciarEvento: {
    titulo: 'Registrar inicio del evento', textoEnviar: 'Registrar inicio',
    intro: (c) => `Registra el inicio del evento ${c.eventoId}. Normalmente el sistema lo hace solo al llegar la fecha y hora (trabajador automático).`,
    aviso: 'Después del inicio ya no se aceptan cambios, y las solicitudes en trámite se cierran por inicio del evento.',
    resumen: () => 'Se registrará el inicio del evento.',
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/inicio`),
  },
  finalizarEvento: {
    titulo: 'Registrar finalización del evento', textoEnviar: 'Registrar finalización',
    intro: (c) => `Registra que el evento ${c.eventoId} ya se llevó a cabo y concluyó.`,
    campos: () => [FECHA('fecha', 'Fecha de finalización')],
    resumen: (v) => `Se registrará la finalización con fecha ${fmtFechaHora(v.fecha)}.`,
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/finalizacion`, { fecha: v.fecha }),
  },
  cancelarEvento: {
    titulo: 'Cancelar evento (solicitud del Cliente)', textoEnviar: 'Registrar cancelación', peligro: true,
    intro: (c) => `Registra la cancelación solicitada por el Cliente para el evento ${c.eventoId}.`,
    aviso: 'La política de no reembolso aplica: los pagos recibidos no se devuelven.',
    campos: () => [f('motivo', 'Motivo de la cancelación', 'textarea', { requerido: true })],
    resumen: () => 'Se cancelará el evento. Esta acción puede no tener marcha atrás.',
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/cancelacion`, { motivo: v.motivo }),
  },
  cancelarPorRegularizacion: {
    titulo: 'Cancelar por falta de regularización', textoEnviar: 'Registrar cancelación', peligro: true,
    intro: (c) => `Registro formal del Coordinador: cancelación del evento ${c.eventoId} por falta de regularización del saldo vencido.`,
    campos: () => [f('coordinador', 'Coordinador', 'texto', { requerido: true }), FECHA('fecha', 'Fecha del registro'),
      f('motivo', 'Motivo', 'textarea', { requerido: true })],
    resumen: () => 'Se cancelará el evento por falta de regularización del saldo.',
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/cancelacion-por-falta-de-regularizacion`, { coordinador: v.coordinador, fecha: v.fecha, motivo: v.motivo }),
  },
  revisionAdministrativa: {
    titulo: 'Registrar revisión administrativa', textoEnviar: 'Registrar revisión',
    intro: (c) => `Registra la revisión administrativa del evento cancelado ${c.eventoId}.`,
    campos: () => [FECHA('fecha', 'Fecha de la revisión'), f('resultado', 'Resultado de la revisión', 'textarea', { requerido: true })],
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/revision-administrativa`, { fecha: v.fecha, resultado: v.resultado }),
  },

  // ------------------------------------------------------------ proveedores y servicios
  registrarProveedor: {
    titulo: 'Registrar proveedor', textoEnviar: 'Registrar proveedor',
    intro: () => 'Da de alta a un proveedor en el catálogo. Solo el nombre es obligatorio; los servicios que ofrece permiten proponerlo al asignar un servicio de un evento.',
    campos: () => [
      f('nombre', 'Nombre del proveedor', 'texto', { requerido: true, ayuda: 'Persona o empresa. No puede repetirse (sin distinguir mayúsculas ni acentos).' }),
      f('servicios', 'Servicios que ofrece', 'lista', { ayuda: 'Separa los servicios con comas (por ejemplo, Banquete, Música). Debe coincidir con el nombre del servicio contratado.' }),
      f('contacto', 'Contacto', 'texto', { ayuda: 'Texto libre: teléfono, correo o persona de contacto.' })],
    resumen: (v) => `Se registrará el proveedor «${v.nombre}»${v.servicios.length ? ` que ofrece: ${lista(v.servicios)}` : ' sin servicios indicados (no se propondrá al asignar hasta que los tenga)'}.`,
    enviar: (v) => POST('/proveedores', { nombre: v.nombre, servicios: v.servicios, contacto: v.contacto || '' }),
    despues: (r, c) => c.irA && r.datos && r.datos.proveedorId && c.irA(`#/proveedores/${encodeURIComponent(r.datos.proveedorId)}`),
  },
  asignarProveedor: {
    titulo: 'Asignar proveedor', textoEnviar: 'Asignar proveedor',
    intro: (c) => `Asigna un proveedor al servicio «${c.servicio}». Quedará pendiente de su confirmación.`,
    // Los candidatos son los que el sistema informa como disponibles para este servicio (catálogo registrado y fuente de disponibilidad).
    campos: (c) => [f('proveedor_id', 'Proveedor', 'select', { requerido: true, opciones: c.candidatos,
      ayuda: 'Solo aparecen los proveedores que figuran disponibles para este servicio. Si falta alguno, regístralo en Proveedores indicando que ofrece este servicio.' })],
    resumen: (v, c) => `Se asignará el proveedor ${v.proveedor_id} al servicio «${c.servicio}». Quedará «Pendiente de confirmación del proveedor».`,
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/servicios/${encodeURIComponent(c.servicioId)}/proveedor`, { proveedor_id: v.proveedor_id }),
  },
  respuestaProveedor: {
    titulo: 'Registrar respuesta del proveedor', textoEnviar: 'Registrar respuesta',
    intro: (c) => `Registra si el proveedor${c.proveedorNombre ? ` ${c.proveedorNombre}` : ''} puede prestar el servicio «${c.servicio}».`,
    campos: (c) => [f('proveedor_id', 'Identificador del proveedor', 'texto', { requerido: true, valor: c.proveedorId || '' }),
      f('disponible', 'El proveedor está disponible', 'bool', { valor: true })],
    resumen: (v) => `Se registrará que el proveedor ${v.proveedor_id} ${v.disponible ? 'está disponible' : 'NO está disponible'}.`,
    enviar: (v, c) => POST(`/eventos/${encodeURIComponent(c.eventoId)}/servicios/${encodeURIComponent(c.servicioId)}/respuesta-proveedor`, { proveedor_id: v.proveedor_id, disponible: v.disponible }),
  },

  // ------------------------------------------------------------ solicitud de cambio
  nuevoCambio: {
    titulo: 'Registrar solicitud de cambio', textoEnviar: 'Registrar solicitud',
    intro: (c) => `Solicita un cambio al evento ${c.eventoId}. Solo procede después de contratar y antes del inicio; el sistema valida el plazo y te informará el resultado.`,
    campos: (c) => [
      f('contrato_id', 'Contrato', 'select', { requerido: true, opciones: c.contratos.map((x) => ({ valor: x.contratoId, texto: `${x.contratoId} — ${x.estado}` })), valor: c.contratos[0] && c.contratos[0].contratoId }),
      f('descripcion', 'Descripción del cambio', 'textarea', { requerido: true }),
      f('tarifa_vigente', 'Tarifa vigente del cargo por cambio tardío', 'importe', { requerido: true, ayuda: 'La política de Eventos Nova la define; el sistema la usa si el cambio se pide con poca anticipación.' }),
      ...DATOS_PROPUESTOS],
    enviar: (v, c) => POST('/solicitudes-cambio', {
      evento_id: c.eventoId, contrato_id: v.contrato_id, descripcion: v.descripcion, tarifa_vigente: v.tarifa_vigente,
      datos_propuestos: v.cambiar_datos ? { tipo: v.tipo, fecha_hora: v.fecha_hora, lugar: v.lugar, invitados_aproximados: Number(v.invitados_aproximados) } : null }),
  },
  viabilidadCambio: {
    titulo: 'Evaluar viabilidad del cambio', textoEnviar: 'Registrar evaluación',
    intro: (c) => `Registra si el cambio ${c.solicitudId} es viable.`,
    campos: () => [f('viable', 'El cambio es viable', 'bool', { valor: true }), f('motivo', 'Motivo', 'textarea'),
      f('costo_adicional_proveedor', 'Costo adicional del proveedor', 'importe', { ayuda: 'Opcional. Déjalo vacío si el cambio no genera costo.' })],
    enviar: (v, c) => POST(`/solicitudes-cambio/${encodeURIComponent(c.solicitudId)}/viabilidad`, { viable: v.viable, motivo: v.motivo || '', costo_adicional_proveedor: v.costo_adicional_proveedor || null }),
  },
  decisionClienteCambio: decision('cambio', 'decision-cliente', 'Registrar decisión del Cliente', 'Cliente', '/solicitudes-cambio'),
  autorizacionCambio: decision('cambio', 'autorizacion', 'Registrar autorización de Administración', 'Administración', '/solicitudes-cambio'),
  anexoCambio: anexo('/solicitudes-cambio'),
  solicitudPagoCambio: {
    titulo: 'Comunicar solicitud de pago', textoEnviar: 'Comunicar pago',
    intro: (c) => `Comunica al Cliente el pago del cambio ${c.solicitudId} (costo del proveedor y, si aplica, cargo por cambio tardío).`,
    campos: () => [FECHA('comunicado_en', 'Fecha de la comunicación')],
    enviar: (v, c) => POST(`/solicitudes-cambio/${encodeURIComponent(c.solicitudId)}/solicitud-pago`, { comunicado_en: v.comunicado_en }),
  },
  confirmarCambio: confirmar('/solicitudes-cambio', 'Confirmar cambio'),
  cerrarCambioFaltaPago: cerrarPago('/solicitudes-cambio'),

  // ------------------------------------------------------------ servicio adicional
  nuevoServicioAdicional: {
    titulo: 'Registrar servicio adicional', textoEnviar: 'Registrar solicitud',
    intro: (c) => `Solicita un servicio que no está en el contrato original del evento ${c.eventoId}. Solo se registra con la contratación confirmada; si el evento ya inició, el sistema la registrará como No procedente.`,
    campos: (c) => [
      f('contrato_id', 'Contrato', 'select', { requerido: true, opciones: c.contratos.map((x) => ({ valor: x.contratoId, texto: `${x.contratoId} — ${x.estado}` })), valor: c.contratos[0] && c.contratos[0].contratoId }),
      f('servicio', 'Servicio solicitado', 'texto', { requerido: true, ayuda: 'Debe pedirse con al menos cinco días naturales de anticipación; el sistema lo valida.' })],
    enviar: (v, c) => POST('/solicitudes-servicio-adicional', { evento_id: c.eventoId, contrato_id: v.contrato_id, servicio: v.servicio }),
  },
  disponibilidadAdicional: {
    titulo: 'Evaluar disponibilidad de proveedores', textoEnviar: 'Evaluar disponibilidad',
    intro: (c) => `Consulta la disponibilidad de proveedores para el servicio adicional ${c.solicitudId}.`,
    campos: () => [f('proveedores_actuales', 'Proveedores que ya participan en el evento', 'lista', { ayuda: 'Opcional. Identificadores separados con comas.' })],
    enviar: (v, c) => POST(`/solicitudes-servicio-adicional/${encodeURIComponent(c.solicitudId)}/disponibilidad`, { proveedores_actuales: v.proveedores_actuales }),
  },
  esperaAdicional: {
    titulo: 'Decisión de espera del Cliente', textoEnviar: 'Registrar decisión',
    intro: (c) => `Registra si el Cliente acepta esperar la búsqueda de proveedor para ${c.solicitudId}. La espera no amplía el plazo mínimo de cinco días.`,
    campos: () => [f('acepta_esperar', 'El Cliente acepta esperar', 'bool', { valor: true })],
    enviar: (v, c) => POST(`/solicitudes-servicio-adicional/${encodeURIComponent(c.solicitudId)}/decision-espera`, { acepta_esperar: v.acepta_esperar }),
  },
  aprobacionClienteAdicional: decision('servicio adicional', 'aprobacion-cliente', 'Registrar aprobación del Cliente', 'Cliente', '/solicitudes-servicio-adicional'),
  autorizacionAdicional: decision('servicio adicional', 'autorizacion', 'Registrar autorización de Administración', 'Administración', '/solicitudes-servicio-adicional'),
  anexoAdicional: anexo('/solicitudes-servicio-adicional'),
  solicitudPagoAdicional: {
    titulo: 'Comunicar solicitud de pago', textoEnviar: 'Comunicar pago',
    intro: (c) => `Comunica al Cliente el pago del servicio adicional ${c.solicitudId}. Desde la comunicación corren 24 horas naturales para pagar.`,
    campos: () => [FECHA('comunicado_en', 'Fecha de la comunicación'),
      f('importe', 'Importe', 'importe', { requerido: true, positivo: true, ayuda: 'Solo el costo del proveedor; Eventos Nova no cobra cargo propio por servicios adicionales.' })],
    resumen: (v) => `Se comunicará al Cliente un pago de ${fmtImporte(v.importe)} por el servicio adicional.`,
    enviar: (v, c) => POST(`/solicitudes-servicio-adicional/${encodeURIComponent(c.solicitudId)}/solicitud-pago`, { comunicado_en: v.comunicado_en, concepto: 'ServicioAdicional', importe: v.importe }),
  },
  confirmarAdicional: confirmar('/solicitudes-servicio-adicional', 'Confirmar servicio adicional'),
  cerrarAdicionalFaltaPago: cerrarPago('/solicitudes-servicio-adicional'),

  // ------------------------------------------------------------ sustitución de proveedor
  nuevaSustitucion: {
    titulo: 'Iniciar sustitución de proveedor', textoEnviar: 'Iniciar sustitución',
    intro: (c) => `Registra que el proveedor de un servicio del evento ${c.eventoId} no está disponible e inicia la búsqueda de una alternativa.`,
    campos: (c) => [
      f('contrato_id', 'Contrato', 'select', { requerido: true, opciones: c.contratos.map((x) => ({ valor: x.contratoId, texto: `${x.contratoId} — ${x.estado}` })), valor: c.contratos[0] && c.contratos[0].contratoId }),
      f('servicio_contratado_id', 'Servicio contratado', 'select', { requerido: true, opciones: c.servicios.map((s) => ({ valor: s.servicioContratadoId, texto: `${s.servicio} (${s.estado})` })) })],
    enviar: (v, c) => POST('/sustituciones', { evento_id: c.eventoId, contrato_id: v.contrato_id, servicio_contratado_id: v.servicio_contratado_id }),
  },
  alternativaSustitucion: {
    titulo: 'Proponer alternativa de proveedor', textoEnviar: 'Registrar alternativa',
    intro: (c) => `Registra la alternativa encontrada para la sustitución ${c.solicitudId}.`,
    campos: () => [f('condiciones_alternativa', 'Condiciones de la alternativa', 'textarea', { requerido: true }),
      f('costo_adicional', 'Costo adicional', 'importe', { ayuda: 'Opcional. Si no hay costo adicional, la sustitución pasa directamente a formalización.' })],
    enviar: (v, c) => POST(`/sustituciones/${encodeURIComponent(c.solicitudId)}/alternativa`, { condiciones_alternativa: v.condiciones_alternativa, costo_adicional: v.costo_adicional || null }),
  },
  decisionClienteSustitucion: decision('sustitución de proveedor', 'decision-cliente', 'Registrar decisión del Cliente', 'Cliente', '/sustituciones'),
  autorizacionSustitucion: decision('sustitución de proveedor', 'autorizacion', 'Registrar autorización de Administración', 'Administración', '/sustituciones'),
  anexoSustitucion: anexo('/sustituciones'),
  importeSustitucion: {
    titulo: 'Integrar importe adicional al saldo', textoEnviar: 'Integrar importe',
    intro: (c) => `Integra el importe adicional de la sustitución ${c.solicitudId} al saldo general del contrato.`,
    campos: () => [f('importe', 'Importe adicional', 'importe', { requerido: true, positivo: true })],
    resumen: (v) => `Se integrará ${fmtImporte(v.importe)} al saldo general.`,
    enviar: (v, c) => POST(`/sustituciones/${encodeURIComponent(c.solicitudId)}/importe-adicional`, { importe: v.importe }),
  },
  confirmarSustitucion: confirmar('/sustituciones', 'Confirmar sustitución'),
};

function decision(tipo, ruta, titulo, actor, base) {
  return {
    titulo, textoEnviar: 'Registrar decisión',
    intro: (c) => `Registra la decisión sobre ${tipo} ${c.solicitudId}.`,
    campos: () => campoDecision(actor),
    resumen: (v) => `Se registrará una decisión de ${v.actor}: ${v.aprobada ? 'APROBADA' : 'NO aprobada'}.`,
    enviar: (v, c) => POST(`${base}/${encodeURIComponent(c.solicitudId)}/${ruta}`, cuerpoDecision(v)),
  };
}
function anexo(base) {
  return {
    titulo: 'Registrar anexo del contrato', textoEnviar: 'Registrar anexo',
    intro: (c) => `Documenta la solicitud ${c.solicitudId} mediante un anexo vinculado al contrato original.`,
    campos: () => [f('descripcion', 'Descripción del anexo', 'textarea', { requerido: true })],
    enviar: (v, c) => POST(`${base}/${encodeURIComponent(c.solicitudId)}/anexo`, { descripcion: v.descripcion }),
  };
}
function confirmar(base, titulo) {
  return {
    titulo, textoEnviar: titulo,
    intro: (c) => `Confirma la solicitud ${c.solicitudId}. El sistema comprueba que estén cumplidos los pasos y pagos necesarios y, si falta alguno, lo indicará.`,
    resumen: () => 'Se intentará confirmar la solicitud.',
    enviar: (v, c) => POST(`${base}/${encodeURIComponent(c.solicitudId)}/confirmacion`),
  };
}
function cerrarPago(base) {
  return {
    titulo: 'Cerrar por falta de pago', textoEnviar: 'Cerrar solicitud', peligro: true,
    intro: (c) => `Cierra la solicitud ${c.solicitudId} porque no se pagó dentro del plazo.`,
    resumen: () => 'La solicitud se cerrará por falta de pago.',
    enviar: (v, c) => POST(`${base}/${encodeURIComponent(c.solicitudId)}/cierre-por-falta-de-pago`),
  };
}

/** Acciones disponibles según el estado oficial de la solicitud (el backend sigue siendo quien decide). */
export const ACCIONES_POR_ESTADO = {
  cambio: {
    'Registrada': ['viabilidadCambio'], 'En evaluación': ['viabilidadCambio'],
    'Pendiente de aprobación del Cliente': ['decisionClienteCambio'],
    'Pendiente de autorización': ['autorizacionCambio'],
    'Pendiente de formalización': ['anexoCambio', 'solicitudPagoCambio', 'confirmarCambio'],
    'Pendiente de pago': ['confirmarCambio', 'cerrarCambioFaltaPago'],
  },
  'servicio adicional': {
    'Registrada': ['disponibilidadAdicional'], 'En búsqueda de proveedor': ['disponibilidadAdicional', 'esperaAdicional'],
    'Pendiente de aprobación del Cliente': ['aprobacionClienteAdicional'],
    'Pendiente de autorización': ['autorizacionAdicional'],
    'Autorizada': ['anexoAdicional', 'solicitudPagoAdicional'],
    'Pendiente de pago': ['confirmarAdicional', 'cerrarAdicionalFaltaPago'],
  },
  'sustitución de proveedor': {
    'En búsqueda de alternativa': ['alternativaSustitucion'],
    'Pendiente de aprobación del Cliente': ['decisionClienteSustitucion'],
    'Pendiente de autorización': ['autorizacionSustitucion'],
    'Pendiente de formalización': ['anexoSustitucion', 'importeSustitucion', 'confirmarSustitucion'],
  },
};
export const accionesDeSolicitud = (tipo, estado) => (ACCIONES_POR_ESTADO[tipo] || {})[estado] || [];

/** Proveedores que el sistema informa como disponibles para un servicio contratado, con su nombre del catálogo cuando existe. */
export async function candidatosParaAsignar(eventoId, servicioId) {
  const [disp, catalogo] = await Promise.all([consultarDisponibilidad(eventoId, servicioId), GET('/proveedores')]);
  const nombres = Object.fromEntries(catalogo.datos.proveedores.map((p) => [p.proveedorId, p.nombre]));
  return ((disp.datos && disp.datos.disponibles) || []).map((id) => ({ valor: id, texto: nombres[id] ? `${nombres[id]} (${id})` : `${id} (no figura en el catálogo)` }));
}

/** Cuentas (solo administrador). La contraseña viaja únicamente en la petición HTTPS/HTTP al servidor y no se guarda en la interfaz. */
ACCIONES.crearCuenta = {
  titulo: 'Crear cuenta', textoEnviar: 'Crear cuenta',
  intro: () => 'Crea una cuenta con el rol indicado. La persona podrá cambiar su contraseña al entrar. Una cuenta nueva solo recibe los permisos de su rol.',
  campos: (c) => [
    f('nombre', 'Nombre de la persona', 'texto', { requerido: true }),
    f('correo', 'Correo (será su usuario)', 'texto', { requerido: true }),
    f('rol', 'Rol', 'select', { requerido: true, opciones: [{ valor: 'coordinador', texto: 'Coordinación' }, { valor: 'administrador', texto: 'Administración' }, { valor: 'proveedor', texto: 'Proveedor' }],
      ayuda: 'Coordinación: eventos, propuestas, contratos y solicitudes. Administración: pagos, devoluciones, autorizaciones y cuentas. Proveedor: solo sus servicios.' }),
    f('proveedor_id', 'Proveedor al que pertenece', 'select', { requerido: true, visibleSi: (v) => v.rol === 'proveedor', opciones: c.proveedores.map((p) => ({ valor: p.proveedorId, texto: p.nombre })),
      ayuda: 'Solo las cuentas de proveedor se vinculan a un proveedor del catálogo.' }),
    f('contrasena', 'Contraseña inicial', 'contrasena', { requerido: true, minLongitud: 12, ayuda: 'Mínimo 12 caracteres. Compártela por un medio seguro; no se vuelve a mostrar.' })],
  resumen: (v) => `Se creará la cuenta de ${v.nombre} (${v.correo}) con el rol «${v.rol}».`,
  enviar: (v) => POST('/usuarios', { nombre: v.nombre, correo: v.correo, rol: v.rol, contrasena: v.contrasena, ...(v.rol === 'proveedor' ? { proveedor_id: v.proveedor_id } : {}) }),
};
ACCIONES.desactivarCuenta = {
  titulo: 'Desactivar cuenta', textoEnviar: 'Desactivar', peligro: true,
  intro: (c) => `Desactiva la cuenta de ${c.usuario.nombre}. Sus sesiones abiertas se cierran de inmediato y no podrá volver a entrar hasta que se active de nuevo.`,
  resumen: (v, c) => `La cuenta de ${c.usuario.nombre} quedará desactivada.`,
  enviar: (v, c) => POST(`/usuarios/${encodeURIComponent(c.usuario.usuarioId)}/estado`, { activo: false }),
};
ACCIONES.activarCuenta = {
  titulo: 'Activar cuenta', textoEnviar: 'Activar', intro: (c) => `Permite que ${c.usuario.nombre} vuelva a entrar con su contraseña actual.`,
  resumen: (v, c) => `La cuenta de ${c.usuario.nombre} quedará activa.`,
  enviar: (v, c) => POST(`/usuarios/${encodeURIComponent(c.usuario.usuarioId)}/estado`, { activo: true }),
};
ACCIONES.restablecerContrasena = {
  titulo: 'Restablecer contraseña', textoEnviar: 'Restablecer', peligro: true,
  intro: (c) => `Define una contraseña nueva para ${c.usuario.nombre}. Sus sesiones abiertas se cierran.`,
  campos: () => [f('contrasena', 'Contraseña nueva', 'contrasena', { requerido: true, minLongitud: 12, ayuda: 'Mínimo 12 caracteres.' })],
  resumen: (v, c) => `Se restablecerá la contraseña de ${c.usuario.nombre} y se cerrarán sus sesiones.`,
  enviar: (v, c) => POST(`/usuarios/${encodeURIComponent(c.usuario.usuarioId)}/contrasena`, { contrasena: v.contrasena }),
};
ACCIONES.cambiarContrasena = {
  titulo: 'Cambiar mi contraseña', textoEnviar: 'Cambiar contraseña',
  intro: () => 'Al cambiarla se cierran todas tus sesiones y tendrás que iniciar sesión de nuevo.',
  campos: () => [f('actual', 'Contraseña actual', 'contrasena', { requerido: true }), f('nueva', 'Contraseña nueva', 'contrasena', { requerido: true, minLongitud: 12, ayuda: 'Mínimo 12 caracteres.' })],
  enviar: (v) => POST('/auth/cambio-contrasena', { actual: v.actual, nueva: v.nueva }),
};

// Permiso del servidor que autoriza cada acción. Sirve solo para mostrar u ocultar botones: el servidor decide en cada petición.
const PERMISO_DE_ACCION = {
  registrarEvento: 'eventos.registrar', crearPropuesta: 'propuestas.gestionar', nuevaVersion: 'propuestas.gestionar', aceptarPropuesta: 'propuestas.gestionar',
  cerrarPropuesta: 'propuestas.gestionar', prepararContrato: 'contratos.gestionar', comunicarPolitica: 'contratos.gestionar', firmarContrato: 'contratos.gestionar',
  seguimientoAnticipo: 'contratos.gestionar', confirmarContratacion: 'contratos.gestionar', registrarPago: 'pagos.registrar', verificarPago: 'pagos.registrar',
  vencimientoSaldo: 'pagos.cobranza', protocoloCobro: 'pagos.cobranza', regularizacion: 'pagos.cobranza', ejecutarDevolucion: 'devoluciones.ejecutar',
  iniciarEvento: 'eventos.ciclo', finalizarEvento: 'eventos.ciclo', cancelarEvento: 'eventos.cancelar', cancelarPorRegularizacion: 'eventos.cancelar',
  revisionAdministrativa: 'eventos.revision_administrativa', registrarProveedor: 'proveedores.registrar', asignarProveedor: 'proveedores.asignar',
  respuestaProveedor: 'proveedores.responder', nuevoCambio: 'solicitudes.registrar', nuevoServicioAdicional: 'solicitudes.registrar', nuevaSustitucion: 'solicitudes.registrar',
  autorizacionCambio: 'solicitudes.autorizar', autorizacionAdicional: 'solicitudes.autorizar', autorizacionSustitucion: 'solicitudes.autorizar',
  importeSustitucion: 'solicitudes.importe_adicional', crearCuenta: 'usuarios.administrar', desactivarCuenta: 'usuarios.administrar',
  activarCuenta: 'usuarios.administrar', restablecerContrasena: 'usuarios.administrar',
  cambiarContrasena: 'sesion',
};
for (const [clave, accion] of Object.entries(ACCIONES)) {
  if (clave === 'cambiarContrasena') continue;                       // cualquier persona con sesión
  accion.permiso = PERMISO_DE_ACCION[clave] || 'solicitudes.gestionar';   // el resto son gestiones de solicitudes (viabilidad, decisiones, anexos, confirmaciones, cierres…)
}

export const consultarDisponibilidad = (eventoId, servicioId) => GET(`/eventos/${encodeURIComponent(eventoId)}/servicios/${encodeURIComponent(servicioId)}/disponibilidad`);
