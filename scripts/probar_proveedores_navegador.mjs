// Pruebas de extremo a extremo del catálogo de proveedores y su asignación, con Chrome real (protocolo DevTools).
// Requisitos: Node 22+ y Google Chrome, y la API en marcha. Contra PostgreSQL: el entorno de pruebas manuales (puerto 8001).
//   EVENTOSNOVA_E2E_ADMIN_CORREO=… EVENTOSNOVA_E2E_ADMIN_CLAVE=… node scripts/probar_proveedores_navegador.mjs http://127.0.0.1:8001 <carpeta>
// Con autenticación activa necesita una cuenta de administrador existente (scripts/crear_administrador.py); crea por la API un coordinador de prueba.
// Crea datos de prueba (un proveedor, dos eventos contratados) en la API a la que apunte; no borra ni modifica registros existentes.
// La preparación (evento ya contratado y En organización) se hace por la API; el catálogo, la asignación, la respuesta del proveedor y el
// seguimiento se hacen en la interfaz. Escribe <carpeta>/llamadas_http_proveedores.json con método, ruta y código de cada llamada.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { prepararCuentas } from './lib_sesion_e2e.mjs';

const BASE = process.argv[2] || 'http://127.0.0.1:8001';
const SALIDA = process.argv[3] || '.';
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PUERTO = 9334;
const MARCA = Date.now().toString(36).toUpperCase();               // hace único el nombre del proveedor en cada ejecución
const SERVICIO_UNICO = `Servicio exclusivo ${MARCA}`;
// ningún proveedor previo lo ofrece: la prueba no depende de los datos que ya existan
const NOMBRE = `Banquetes UI ${MARCA}`;
const perfil = mkdtempSync(join(tmpdir(), 'enova-prov-'));
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox', `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`, '--window-size=1280,900', 'about:blank'], { stdio: 'ignore' });
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

let ws; let id = 0; const pend = new Map(); const errores = []; const solicitudes = new Map(); const llamadas = [];
async function conectar() {
  for (let i = 0; i < 40; i++) {
    try {
      const lista = await (await fetch(`http://127.0.0.1:${PUERTO}/json`)).json();
      const pag = lista.find((x) => x.type === 'page');
      if (pag) { ws = new WebSocket(pag.webSocketDebuggerUrl); await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; }); break; }
    } catch { /* espera */ }
    await dormir(250);
  }
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
    if (d.method === 'Network.requestWillBeSent') solicitudes.set(d.params.requestId, d.params.request);
    if (d.method === 'Network.responseReceived') {
      const q = solicitudes.get(d.params.requestId); const u = new URL(d.params.response.url);
      if (q && u.origin === new URL(BASE).origin && !u.pathname.startsWith('/app/')) llamadas.push({ metodo: q.method, ruta: u.pathname + u.search, codigo: d.params.response.status });
    }
    if (d.method === 'Runtime.exceptionThrown') errores.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  };
}
const cdp = (method, params = {}) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
async function ev(expr) {
  const r = await cdp('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error('evaluate: ' + JSON.stringify(r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text));
  return r.result.result.value;
}
async function esperar(expr, texto, ms = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch { /* reintenta */ } await dormir(120); }
  throw new Error('Tiempo agotado esperando: ' + texto);
}

const CODIGO_INTERNO = /\b(?:BN|CA|GL|SE|US|CU|RN|AR|TP|ADR|[ACDEHR])-\d{1,3}[A-Za-z]?\b(?!-)/;
const VACIO = /(^|[\s(«"'])(null|undefined|NaN)([\s.,;:)»"']|$)|\[object /;
async function revisarTextos(etiqueta) {
  const textos = JSON.parse((await ev(`sessionStorage.getItem('__textos') || '[]'`)) || '[]');
  const visibles = [...textos, await ev(`document.body.innerText`)];
  const malos = [];
  for (const t of visibles) {
    for (const linea of t.split('\n')) {
      if (VACIO.test(linea)) malos.push('valor ausente: ' + linea.slice(0, 120));
      if (CODIGO_INTERNO.test(linea)) malos.push('código interno: ' + linea.slice(0, 120));
    }
  }
  if (malos.length) throw new Error(etiqueta + ' → ' + [...new Set(malos)].slice(0, 4).join(' | '));
  console.log(`      textos revisados (${etiqueta}): ${visibles.length} bloques, sin valores ausentes ni códigos internos`);
}

const resultados = [];
const paso = async (nombre, fn) => {
  try { await fn(); resultados.push(['OK', nombre]); console.log('OK   ', nombre); } catch (e) {
    let dbg = ''; try { dbg = await ev("(document.querySelector('dialog[open]') || document.body).innerText.slice(0, 600)"); } catch { /* sin DOM */ }
    resultados.push(['FALLO', nombre, e.message]); console.log('FALLO', nombre, '->', e.message); console.log('   DOM:', dbg.split('\n').join(' | '));
  }
};
const helpers = `(() => {
  window.$t = (txt, sel='button,a') => [...document.querySelectorAll(sel)].find(e => e.textContent.trim() === txt && e.offsetParent !== null);
  window.$campo = (txt) => { const l = [...document.querySelectorAll('dialog[open] label')].find(x => x.textContent.includes(txt)); return l && document.getElementById(l.getAttribute('for')); };
  window.$poner = (txt, v) => { const c = $campo(txt); if (!c) throw new Error('campo no encontrado: ' + txt); if (c.type === 'checkbox') { c.checked = v; } else { c.value = v; } c.dispatchEvent(new Event('input', {bubbles:true})); c.dispatchEvent(new Event('change', {bubbles:true})); };
  window.$dlg = () => document.querySelector('dialog[open]');
  // Registra el texto visible de diálogos, avisos y errores (sobrevive a las recargas con sessionStorage) para revisarlo al final.
  if (!window.__obs) {
    window.__obs = true;
    const guardar = () => {
      try {
        const ya = new Set(JSON.parse(sessionStorage.getItem('__textos') || '[]'));
        document.querySelectorAll('dialog[open], .aviso, .modal-alerta, .caja-error, .caja-aviso, .confirmacion').forEach((e) => { if (e.innerText && e.innerText.trim()) ya.add(e.innerText.trim()); });
        sessionStorage.setItem('__textos', JSON.stringify([...ya]));
      } catch { /* sin almacenamiento */ }
    };
    new MutationObserver(guardar).observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
  }
})()`;

// ---- preparación por la API (sin interfaz): evento contratado y En organización
let cuentas;                                                                      // sesiones de administración y coordinación (creadas al iniciar)
const j = async (metodo, ruta, cuerpo, quien) => (quien || cuentas.coord).json(metodo, ruta, cuerpo);
const ahora = () => new Date(Date.now() - 6 * 3600 * 1000).toISOString().slice(0, 19);        // hora aproximada de la Ciudad de México
async function eventoContratado(servicios) {
  const fecha = new Date(Date.now() + 75 * 864e5).toISOString().slice(0, 19);
  const evento = (await j('POST', '/eventos', { cliente_id: 'CL-PROV-UI', datos: { tipo: `Prueba proveedores ${MARCA}`, fecha_hora: fecha, lugar: 'Salón de prueba', invitados_aproximados: 50 }, servicios })).evento_id;
  const propuesta = (await j('POST', `/eventos/${evento}/propuestas`, { servicios, proveedores_considerados: ['PV-PRUEBA'], costo_total: '10000.00', condiciones: 'Prueba' })).propuesta_id;
  await j('POST', `/propuestas/${propuesta}/aceptacion`, { version_id: `${propuesta}-v1` });
  const contrato = (await j('POST', `/propuestas/${propuesta}/contrato`, { politica_incluida: true })).datos.contrato_id;
  await j('POST', `/contratos/${contrato}/comunicacion-politica-no-reembolso`, { fecha: ahora() });
  await j('POST', `/contratos/${contrato}/firma`, { fecha: ahora() });
  const ec = (await j('GET', `/eventos/${evento}/pagos`)).estadosCuenta[0];
  const ob = (await j('GET', `/pagos-pendientes?evento_id=${evento}`)).pagos.find((p) => p.concepto === 'Anticipo');
  await j('POST', `/estados-cuenta/${ec.estadoCuentaId}/pagos`, { obligacion_id: ob.obligacionId, importe: '3000.00', fecha: ahora(), comprobante: `CMP-PROV-${MARCA}-${servicios.length}`, verificar_ahora: true }, cuentas.admin);   // los pagos los registra Administración
  for (let i = 0; i < 20; i++) { if ((await j('GET', `/eventos/${evento}/administracion`)).estadoEvento === 'En organización') return evento; await dormir(300); }
  throw new Error('el evento no llegó a En organización');
}

cuentas = await prepararCuentas(BASE, MARCA);
await conectar();
await cdp('Runtime.enable'); await cdp('Page.enable'); await cdp('Network.enable');
const ir = async (hash) => { await cdp('Page.navigate', { url: `${BASE}/app/${hash}` }); await dormir(300); await ev(helpers).catch(() => {}); };
const cargar = async (hash) => { await ir(hash); await esperar(`document.readyState==='complete' && !!document.querySelector('#contenido') && !document.querySelector('.cargando')`, 'carga ' + hash); await ev(helpers); };
const clic = async (txt) => { await esperar(`!!$t('${txt}')`, 'botón ' + txt, 10000); await ev(`$t('${txt}').click()`); };
const confirmar = async () => { await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`); };
const texto = () => ev(`document.body.innerText`);

// ---- sesión en la interfaz: se inicia con el formulario real (la cuenta la valida el servidor)
async function ingresarUI(correo, clave) {
  await cdp('Page.navigate', { url: `${BASE}/app/` }); await dormir(500);
  await esperar(`!!document.getElementById('ing-correo')`, 'formulario de ingreso', 10000);
  await ev(`(() => { const c = document.getElementById('ing-correo'), p = document.getElementById('ing-clave'); c.value = ${JSON.stringify(correo)}; p.value = ${JSON.stringify(clave)}; document.querySelector('.ingreso-forma button[type=submit]').click(); })()`);
  await esperar(`!document.getElementById('ing-correo') && !!document.querySelector('#sesion-caja button')`, 'sesión iniciada', 10000);
}
async function cambiarUsuarioUI(correo, clave) {
  await ev(`[...document.querySelectorAll('#sesion-caja button')].find(b => b.textContent.trim() === 'Cerrar sesión').click()`);
  await esperar(`!!document.getElementById('ing-correo')`, 'ingreso tras cerrar sesión', 10000);
  await ingresarUI(correo, clave);
}

await ingresarUI(cuentas.correoCoord, cuentas.claveCoord);
let proveedorId; let eventoA; let eventoB; let eventoG; let eventoV; let eventoC;

await paso('El catálogo carga (con o sin proveedores previos)', async () => {
  await cargar('#/proveedores');
  const t = await texto(); if (!t.includes('Registrar proveedor')) throw new Error('sin botón de alta');
  if (await ev(`!!document.querySelector('.caja-error')`)) throw new Error('caja de error');
});

await paso('Registrar proveedor: el formulario vacío muestra el mensaje de campo obligatorio y no envía', async () => {
  await clic('Registrar proveedor'); await esperar(`!!$dlg()`, 'diálogo');
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`[...$dlg().querySelectorAll('.error-campo')].some(x => x.textContent.includes('obligatorio'))`, 'mensaje');
});

await paso('Registrar proveedor con nombre, servicios y contacto: se crea y se abre su ficha', async () => {
  await ev(`$poner('Nombre del proveedor','${NOMBRE}'); $poner('Servicios que ofrece','Banquete, Música'); $poner('Contacto','55 0000 0000')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación');
  const conf = await ev(`$dlg().querySelector('.confirmacion').innerText`);
  const parrafos = await ev(`$dlg().querySelector('.confirmacion').children.length`);
  console.log('      confirmación mostrada:', JSON.stringify(conf));
  if (/null|undefined/i.test(conf)) throw new Error('la confirmación muestra un valor ausente: ' + conf);
  if (parrafos !== 1) throw new Error('la confirmación tiene bloques de más: ' + parrafos);
  await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`location.hash.startsWith('#/proveedores/PV-')`, 'ficha');
  proveedorId = await ev(`decodeURIComponent(location.hash.split('/').pop())`);
  await esperar(`document.querySelector('h1')?.textContent === '${NOMBRE}'`, 'nombre en la ficha');
  const t = await texto(); for (const x of ['Banquete, Música', '55 0000 0000']) if (!t.includes(x)) throw new Error('falta en la ficha: ' + x);
});

await paso('Registrar el mismo nombre (otras mayúsculas) lo rechaza el backend y la interfaz muestra el motivo real', async () => {
  await cargar('#/proveedores');
  await clic('Registrar proveedor'); await esperar(`!!$dlg()`, 'diálogo');
  await ev(`$poner('Nombre del proveedor','${NOMBRE.toLowerCase()}')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`); await confirmar();
  await esperar(`$dlg() && !$dlg().querySelector('.modal-alerta').hidden`, 'alerta');
  const m = await ev(`$dlg().querySelector('.modal-alerta').textContent`); if (!m.includes('Ya existe un proveedor')) throw new Error(m);
  console.log('      mensaje del backend:', m.slice(0, 110));
  await clic('Cancelar');
});

await paso('Buscar por texto y por servicio encuentra al proveedor; una búsqueda sin coincidencias lo explica', async () => {
  await cargar(`#/proveedores?q=${encodeURIComponent(MARCA)}&servicio=${encodeURIComponent('musica')}`);
  await esperar(`document.body.innerText.includes('${NOMBRE}')`, 'resultado');
  await cargar(`#/proveedores?q=${encodeURIComponent('zzz-no-existe-' + MARCA)}`);
  await esperar(`document.body.innerText.includes('Ningún proveedor coincide')`, 'sin coincidencias');
});

await paso('Evento sin proveedor: el detalle muestra «Sin asignar» y ofrece Asignar proveedor', async () => {
  eventoA = await eventoContratado(['Banquete', 'Música']);
  await cargar(`#/evento/${eventoA}`);
  await esperar(`document.querySelector('h1 .insignia')?.textContent === 'En organización'`, 'En organización');
  const t = await texto(); if (!t.includes('Sin asignar') || !t.includes('Sin proveedor asignado')) throw new Error('no distingue el servicio sin proveedor');
  if (!(await ev(`!!$t('Asignar proveedor')`))) throw new Error('falta el botón');
});

await paso('Asignar el proveedor al servicio Banquete desde una lista de candidatos con nombre', async () => {
  await ev(`[...document.querySelectorAll('tbody tr')].find(r => r.textContent.includes('Banquete')).querySelector('button.btn-primario').click()`);
  await esperar(`!!$dlg() && !!$campo('Proveedor')`, 'diálogo de asignación');
  const opciones = await ev(`[...$campo('Proveedor').options].map(o => o.textContent)`);
  console.log('      candidatos:', JSON.stringify(opciones));
  if (!opciones.some((o) => o.includes(NOMBRE) && o.includes(proveedorId))) throw new Error('el proveedor registrado no es candidato');
  if (opciones.some((o) => o.includes('PV-DEMO'))) throw new Error('aparece un proveedor de demostración como candidato: ' + JSON.stringify(opciones));
  if (opciones.some((o) => o.includes('no figura en el catálogo'))) throw new Error('aparece un candidato que no está en el catálogo: ' + JSON.stringify(opciones));
  await ev(`$poner('Proveedor','${proveedorId}')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`); await confirmar();
  await esperar(`!$dlg()`, 'cierre');
  await esperar(`[...document.querySelectorAll('tbody tr')].some(r => r.textContent.includes('Banquete') && r.textContent.includes('${NOMBRE}') && r.textContent.includes('Pendiente de confirmación del proveedor'))`, 'servicio pendiente con nombre');
});

await paso('Seguimiento distingue «sin proveedor» de «asignado, pendiente de confirmación» y muestra el nombre', async () => {
  await cargar(`#/seguimiento?evento=${eventoA}`);
  await esperar(`document.body.innerText.includes('Sin proveedor asignado (1)')`, 'sección sin proveedor');
  const t = await texto();
  if (!t.includes('Asignados, pendientes de confirmación del proveedor (1)')) throw new Error('falta la sección de pendientes');
  if (!t.includes(NOMBRE)) throw new Error('no muestra el nombre del proveedor');
});

await paso('Tras limpiar localStorage y recargar, la asignación se recupera desde la API (PostgreSQL)', async () => {
  await cargar('#/'); await ev(`localStorage.clear()`);
  await cargar(`#/evento/${eventoA}`);
  await esperar(`[...document.querySelectorAll('tbody tr')].some(r => r.textContent.includes('Banquete') && r.textContent.includes('${NOMBRE}'))`, 'asignación persistida');
  const admin = await (await cuentas.coord.fetch(`/eventos/${eventoA}/administracion`)).json();
  const s = admin.proveedores.find((x) => x.servicio === 'Banquete');
  if (s.proveedorId !== proveedorId || s.proveedorNombre !== NOMBRE || s.estado !== 'Pendiente de confirmación del proveedor') throw new Error(JSON.stringify(s));
  console.log('      API:', JSON.stringify(s));
});

await paso('Registrar la respuesta del proveedor (disponible): el servicio queda Confirmado y sale de pendientes', async () => {
  await ev(`[...document.querySelectorAll('tbody tr')].find(r => r.textContent.includes('Banquete')).querySelector('.acciones button:last-child').click()`);
  await esperar(`!!$dlg() && !!$campo('Identificador del proveedor')`, 'diálogo de respuesta');
  const previo = await ev(`$campo('Identificador del proveedor').value`); if (previo !== proveedorId) throw new Error('no precarga el proveedor: ' + previo);
  await ev(`$dlg().querySelector('button[type=submit]').click()`); await confirmar();
  await esperar(`!$dlg()`, 'cierre');
  await esperar(`[...document.querySelectorAll('tbody tr')].some(r => r.textContent.includes('Banquete') && r.textContent.includes('Confirmado por el proveedor'))`, 'servicio confirmado');
  await cargar(`#/seguimiento?evento=${eventoA}`);
  await esperar(`document.body.innerText.includes('Asignados, pendientes de confirmación del proveedor (0)')`, 'ya no está pendiente');
});

await paso('Un servicio sin ningún proveedor que lo ofrezca explica cómo continuar (sin inventar candidatos)', async () => {
  eventoB = await eventoContratado([SERVICIO_UNICO]);
  await cargar(`#/evento/${eventoB}`);
  await esperar(`!!$t('Asignar proveedor')`, 'botón');
  await clic('Asignar proveedor');
  await esperar(`!!$dlg() && $dlg().innerText.includes('No hay proveedores disponibles')`, 'aviso sin candidatos');
  await ev(`$dlg().querySelector('button').click()`);
});

await paso('El backend rechaza con HTTP 422 asignar un proveedor que no ofrece el servicio (petición directa; la interfaz no lo propone)', async () => {
  // La interfaz solo propone candidatos válidos; la regla se comprueba contra el backend con una petición directa.
  const admin = await (await cuentas.coord.fetch(`/eventos/${eventoB}/administracion`)).json();
  const r = await cuentas.coord.fetch(`/eventos/${eventoB}/servicios/${admin.proveedores[0].servicioContratadoId}/proveedor`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ proveedor_id: proveedorId }) });
  const cuerpo = await r.json(); llamadas.push({ metodo: 'POST', ruta: '/eventos/{id}/servicios/{id}/proveedor (directa)', codigo: r.status });
  if (r.status !== 422 || !String(cuerpo.detalle).includes('no ofrece el servicio')) throw new Error(r.status + ' ' + JSON.stringify(cuerpo));
  console.log('      HTTP 422:', cuerpo.detalle);
});

await paso('Seguimiento: oculta (y cuenta) los eventos cancelados/finalizados/cerrados y un interruptor los muestra', async () => {
  await cargar('#/seguimiento');
  await esperar(`!!document.querySelector('#f-cerrados')`, 'interruptor');
  const t = await texto(); const oculto = /Se ocultan (\d+) servicio/.exec(t);
  console.log('      aviso de servicios ocultos:', oculto ? oculto[0] : '(ninguno: no hay servicios de eventos cerrados)');
  await cargar('#/seguimiento?cerrados=1');
  await esperar(`document.querySelector('#f-cerrados')?.checked === true`, 'interruptor activo');
  if ((await texto()).includes('Se ocultan')) throw new Error('sigue ocultando con el interruptor activo');
});

await paso('Candidatos por servicio: solo el catálogo; uno que no ofrece el servicio no aparece; un inexistente se rechaza (HTTP 422); PV-DEMO nunca', async () => {
  const solo = (await j('POST', '/proveedores', { nombre: `Foto UI Solo ${MARCA}`, servicios: ['Fotografía'], contacto: '' })).datos.proveedorId;
  const admin = await (await cuentas.coord.fetch(`/eventos/${eventoA}/administracion`)).json();
  const musica = admin.proveedores.find((x) => x.servicio === 'Música');
  const ruta = `/eventos/${eventoA}/servicios/${musica.servicioContratadoId}`;
  const disp = await (await cuentas.coord.fetch(ruta + '/disponibilidad')).json(); llamadas.push({ metodo: 'GET', ruta: ruta + '/disponibilidad (directa)', codigo: 200 });
  const ids = disp.datos.disponibles;
  console.log('      candidatos para Música:', JSON.stringify(ids));
  if (!ids.includes(proveedorId)) throw new Error('el proveedor que ofrece Música no es candidato');
  if (ids.includes(solo)) throw new Error('un proveedor que solo ofrece Fotografía aparece para Música');
  if (ids.some((x) => x.startsWith('PV-DEMO'))) throw new Error('aparece un PV-DEMO');
  for (const [prueba, id, texto] of [['inexistente', 'PV-NO-EXISTE', 'no está registrado en el catálogo'], ['que no ofrece el servicio', solo, 'no ofrece el servicio'], ['de demostración', 'PV-DEMO-MUSICA-1', 'no está registrado en el catálogo']]) {
    const r = await cuentas.coord.fetch(ruta + '/proveedor', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ proveedor_id: id }) });
    const c = await r.json(); llamadas.push({ metodo: 'POST', ruta: `${ruta}/proveedor (directa, ${prueba})`, codigo: r.status });
    console.log(`      HTTP ${r.status} (${prueba}):`, c.detalle);
    if (r.status !== 422 || !String(c.detalle).includes(texto)) throw new Error(`${prueba}: ${r.status} ${JSON.stringify(c)}`);
  }
  const despues = (await (await cuentas.coord.fetch(`/eventos/${eventoA}/administracion`)).json()).proveedores.find((x) => x.servicio === 'Música');
  if (despues.estado !== 'Sin proveedor asignado' || despues.proveedorId) throw new Error('un rechazo cambió el servicio: ' + JSON.stringify(despues));
});

await paso('Evento En gestión: muestra los servicios solicitados (no «Sin servicios registrados») y explica por qué aún no hay proveedor', async () => {
  const idG = (await j('POST', '/eventos', { cliente_id: 'CL-PROV-UI', datos: { tipo: `Prueba proveedores ${MARCA} en gestión`, fecha_hora: new Date(Date.now() + 75 * 864e5).toISOString().slice(0, 19), lugar: 'Salón de prueba', invitados_aproximados: 30 }, servicios: ['Banquete', 'Música'] })).evento_id;
  eventoG = idG;
  await cargar(`#/evento/${idG}`);
  await esperar(`document.querySelector('h1 .insignia')?.textContent === 'En gestión'`, 'detalle');
  const t = await texto();
  for (const x of ['Servicio solicitado', 'Banquete', 'Música', 'Todavía no están contratados']) if (!t.toLowerCase().includes(x.toLowerCase())) throw new Error('falta: ' + x);
  if (t.includes('Sin servicios registrados')) throw new Error('indica que no hay servicios');
  if (await ev(`!!$t('Asignar proveedor')`)) throw new Error('ofrece asignar antes de contratar');
  await revisarTextos('evento En gestión');
});

await paso('Evento sin ningún servicio muestra «Sin servicios registrados»', async () => {
  const idV = (await j('POST', '/eventos', { cliente_id: 'CL-PROV-UI', datos: { tipo: `Prueba proveedores ${MARCA} sin servicios`, fecha_hora: new Date(Date.now() + 75 * 864e5).toISOString().slice(0, 19), lugar: 'Salón de prueba', invitados_aproximados: 30 }, servicios: [] })).evento_id;
  eventoV = idV;
  await cargar(`#/evento/${idV}`);
  await esperar(`document.body.innerText.includes('Sin servicios registrados')`, 'mensaje vacío');
});

await paso('Evento cancelado con servicios sin proveedor: se muestran, sin botón Asignar y con el motivo; Seguimiento no los cuenta', async () => {
  eventoC = await eventoContratado(['Banquete']);
  await j('POST', `/eventos/${eventoC}/cancelacion`, { motivo: 'Cancelación de prueba' });
  await cargar(`#/evento/${eventoC}`);
  await esperar(`document.querySelector('h1 .insignia')?.textContent === 'Cancelado'`, 'cancelado');
  const t = await texto();
  if (!t.includes('Banquete') || !t.includes('Sin proveedor asignado')) throw new Error('no muestra el servicio');
  if (!t.includes('solo con el evento En organización; este evento está Cancelado')) throw new Error('falta el motivo');
  if (await ev(`!!$t('Asignar proveedor')`)) throw new Error('ofrece asignar en un evento cancelado');
  await cargar('#/seguimiento'); await esperar(`document.body.innerText.includes('Sin proveedor asignado (')`, 'seguimiento');
  if ((await texto()).includes(eventoC)) throw new Error('Seguimiento cuenta un evento cancelado');
  await cargar('#/seguimiento?cerrados=1'); await esperar(`document.querySelector('#f-cerrados')?.checked === true`, 'interruptor');
  if (!(await texto()).includes(eventoC)) throw new Error('con el interruptor debería aparecer');
  await revisarTextos('seguimiento');
});

await paso('Un rechazo del backend se muestra sin referencias internas, y el texto original queda solo en los detalles técnicos', async () => {
  // Respuesta real del backend a una asignación no permitida (viene con referencias a requisitos) procesada por el cliente de la interfaz.
  await cargar(`#/evento/${eventoB}`);
  const r = await ev(`(async () => {
    const { api } = await import('/app/js/api.js');
    const admin = await (await fetch('/eventos/${eventoB}/administracion')).json();
    try { await api('POST', '/eventos/${eventoB}/servicios/' + admin.proveedores[0].servicioContratadoId + '/proveedor', { cuerpo: { proveedor_id: '${proveedorId}' } }); return { ok: true }; }
    catch (e) { return { mensaje: e.message, crudo: e.crudo && e.crudo.detalle }; }
  })()`);
  console.log('      backend (detalle técnico):', r.crudo);
  console.log('      lo que ve el usuario     :', r.mensaje);
  if (!r.crudo || !/\b(CA|BN)-\d+/.test(r.crudo)) throw new Error('el backend ya no incluye referencias: la prueba no demuestra nada');
  if (CODIGO_INTERNO.test(r.mensaje)) throw new Error('la interfaz muestra la referencia: ' + r.mensaje);
  if (!r.mensaje.includes('no ofrece el servicio')) throw new Error('se perdió el motivo: ' + r.mensaje);
});

await paso('Registrar la respuesta de un proveedor que no es el asignado: el backend rechaza y la interfaz muestra el motivo real', async () => {
  // Asigna en el evento B (servicio exclusivo) un proveedor nuevo que lo ofrece y responde con otro identificador.
  const foto = (await j('POST', '/proveedores', { nombre: `Foto UI ${MARCA}`, servicios: [SERVICIO_UNICO], contacto: '' })).datos.proveedorId;
  await cargar(`#/evento/${eventoB}`);
  await esperar(`!!$t('Asignar proveedor')`, 'botón');
  await clic('Asignar proveedor'); await esperar(`!!$dlg() && !!$campo('Proveedor')`, 'diálogo');
  await ev(`$poner('Proveedor','${foto}')`); await ev(`$dlg().querySelector('button[type=submit]').click()`); await confirmar();
  await esperar(`!$dlg()`, 'cierre');
  await esperar(`document.body.innerText.includes('Pendiente de confirmación del proveedor')`, 'pendiente');
  await ev(`[...document.querySelectorAll('tbody tr')].find(r => r.textContent.includes('${SERVICIO_UNICO}')).querySelector('.acciones button:last-child').click()`);
  await esperar(`!!$dlg() && !!$campo('Identificador del proveedor')`, 'respuesta');
  await ev(`$poner('Identificador del proveedor','${proveedorId}')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`); await confirmar();
  await esperar(`$dlg() && !$dlg().querySelector('.modal-alerta').hidden`, 'alerta');
  const m = await ev(`$dlg().querySelector('.modal-alerta').innerText`);
  console.log('      mensaje del backend:', m.split('\n')[0]);
  if (!m.includes('no está asignado')) throw new Error(m);
  await revisarTextos('diálogo de rechazo');
  await clic('Cancelar');
  // El servicio sigue pendiente (no se aparentó ninguna confirmación).
  await cargar(`#/evento/${eventoB}`);
  await esperar(`[...document.querySelectorAll('tbody tr')].some(r => r.textContent.includes('${SERVICIO_UNICO}') && r.textContent.includes('Pendiente de confirmación del proveedor'))`, 'sigue pendiente');
});

await paso('Revisión final de textos: ninguna pantalla ni diálogo mostró null, undefined ni códigos internos', async () => {
  for (const h of ['#/', '#/eventos', '#/solicitudes', '#/pagos', '#/seguimiento', '#/proveedores', '#/proveedor', '#/sistema', `#/evento/${eventoA}`, `#/proveedores/${proveedorId}`]) {
    await cargar(h); await dormir(250);
    await revisarTextos(h);
  }
});

await paso('Vista móvil (390 px) del catálogo sin desbordamiento', async () => {
  await cdp('Emulation.setDeviceMetricsOverride', { width: 390, height: 800, deviceScaleFactor: 1, mobile: true });
  await cargar('#/proveedores'); await dormir(400);
  if (await ev(`document.documentElement.scrollWidth > window.innerWidth + 2`)) throw new Error('desbordamiento horizontal');
  const cap = await cdp('Page.captureScreenshot', { format: 'png' }); writeFileSync(SALIDA + '/proveedores_movil.png', Buffer.from(cap.result.data, 'base64'));
  await cdp('Emulation.clearDeviceMetricsOverride');
});

await paso('Capturas de escritorio', async () => {
  await cargar(`#/evento/${eventoA}`); await dormir(400);
  let cap = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(SALIDA + '/evento_proveedores.png', Buffer.from(cap.result.data, 'base64'));
  for (const [idx, nombre] of [[eventoG, 'evento_en_gestion'], [eventoC, 'evento_cancelado']]) {
    await cargar(`#/evento/${idx}`); await dormir(400);
    cap = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(`${SALIDA}/${nombre}.png`, Buffer.from(cap.result.data, 'base64'));
  }
  await cargar('#/proveedores'); await dormir(400);
  cap = await cdp('Page.captureScreenshot', { format: 'png' }); writeFileSync(SALIDA + '/catalogo_proveedores.png', Buffer.from(cap.result.data, 'base64'));
  await cargar('#/seguimiento'); await dormir(400);
  cap = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(SALIDA + '/seguimiento.png', Buffer.from(cap.result.data, 'base64'));
});

await paso('Sin excepciones de JavaScript durante la sesión', async () => { if (errores.length) throw new Error(errores.slice(0, 3).join(' | ')); });

writeFileSync(SALIDA + '/llamadas_http_proveedores.json', JSON.stringify(llamadas, null, 1));
console.log(`\nProveedor: ${proveedorId} (${NOMBRE})  Evento A: ${eventoA}  Evento B: ${eventoB}  En gestión: ${eventoG}  Sin servicios: ${eventoV}  Cancelado: ${eventoC}  llamadas HTTP registradas: ${llamadas.length}`);
console.log(`RESUMEN: ${resultados.filter((r) => r[0] === 'OK').length} OK, ${resultados.filter((r) => r[0] === 'FALLO').length} FALLO`);
try { ws.close(); } catch { /* */ }
chrome.kill();
process.exit(resultados.some((r) => r[0] === 'FALLO') ? 1 : 0);
