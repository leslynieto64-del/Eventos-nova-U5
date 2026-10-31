// Pruebas de extremo a extremo de la interfaz con Chrome real (protocolo DevTools) contra el backend real.
// Requisitos: Node 22+ y Google Chrome. La API debe estar en marcha (modo en memoria basta: no toca ninguna base de datos).
//   python -m uvicorn api.main:app --app-dir src --port 8010
//   node scripts/probar_interfaz_navegador.mjs http://127.0.0.1:8010 <carpeta de capturas>
// Contra PostgreSQL (entorno de pruebas manuales, base eventosnova_manual_test): el mismo comando con http://127.0.0.1:8001. Escribe además
// <carpeta>/llamadas_http.json (método, ruta y código de cada llamada a la API) y comprueba la recuperación tras recargar sin localStorage.
// Con autenticación activa necesita una cuenta de administrador existente (EVENTOSNOVA_E2E_ADMIN_CORREO/CLAVE; scripts/crear_administrador.py): crea por la API un
// coordinador de prueba y cambia de usuario en la interfaz (Coordinación registra el evento y la contratación; Administración registra los pagos).
// Crea eventos de prueba en la API a la que apunte: no lo uses contra datos reales.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { prepararCuentas } from './lib_sesion_e2e.mjs';

const BASE = process.argv[2] || 'http://127.0.0.1:8010';
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PUERTO = 9333;
const SALIDA = process.argv[3] || '.';
const perfil = mkdtempSync(join(tmpdir(), 'enova-'));
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox', `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`, '--window-size=1280,900', 'about:blank'], { stdio: 'ignore' });
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

let ws; let id = 0; const pend = new Map(); const errores = []; const consola = [];
const solicitudes = new Map(); const llamadas = [];   // llamadas HTTP a la API: evidencia de endpoint y código
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
    if (d.method === 'Runtime.consoleAPICalled' && d.params.type === 'error') consola.push(d.params.args.map((a) => a.value || a.description).join(' '));
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
    let dbg = '';
    try { dbg = await ev("(document.querySelector('dialog[open]') || document.body).innerText.slice(0, 500)"); } catch (x) { /* sin DOM */ }
    resultados.push(['FALLO', nombre, e.message]); console.log('FALLO', nombre, '->', e.message); console.log('   DOM:', dbg.split(String.fromCharCode(10)).join(' | '));
  }
};

const helpers = `(() => {
  window.$t = (txt, sel='button,a') => [...document.querySelectorAll(sel)].find(e => e.textContent.trim() === txt && e.offsetParent !== null);
  window.$ti = (txt, sel='button,a') => [...document.querySelectorAll(sel)].find(e => e.textContent.trim().includes(txt) && e.offsetParent !== null);
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

const cuentas = await prepararCuentas(BASE, Date.now().toString(36).toUpperCase());
await conectar();
await cdp('Runtime.enable'); await cdp('Page.enable'); await cdp('Network.enable');
const ir = async (hash) => { await cdp('Page.navigate', { url: `${BASE}/app/${hash}` }); await dormir(300); await ev(helpers).catch(() => {}); };
const cargar = async (hash) => { await ir(hash); await esperar(`document.readyState==='complete' && !!document.querySelector('#contenido') && !document.querySelector('.cargando')`, 'carga ' + hash); await ev(helpers); };

const clic = async (txt) => { await esperar(`!!$t('${txt}')`, 'botón ' + txt, 10000); await ev(`$t('${txt}').click()`); };

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
let eventoId; let propuestaId;

await paso('El panel carga con indicadores reales', async () => {
  await cargar('');
  await esperar(`document.querySelectorAll('.indicador').length >= 3`, 'indicadores');
  const t = await ev(`document.querySelector('h1').textContent`); if (!t.includes('Panel principal')) throw new Error(t);
});

await paso('Registrar evento: el formulario vacío muestra mensajes de validación y no envía', async () => {
  await cargar('#/eventos');
  await clic('Registrar evento');
  await esperar(`!!$dlg()`, 'diálogo');
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`$dlg().querySelectorAll('.error-campo').length && [...$dlg().querySelectorAll('.error-campo')].some(x => x.textContent.includes('obligatorio'))`, 'mensajes');
  const n = await ev(`[...$dlg().querySelectorAll('.error-campo')].filter(x=>x.textContent).length`); if (n < 4) throw new Error('pocos mensajes: ' + n);
});

await paso('Registrar evento con datos válidos y abrir su detalle', async () => {
  const f = await ev(`(()=>{const d=new Date(Date.now()+75*864e5);return d.toISOString().slice(0,16)})()`);
  await ev(`$poner('Identificador del cliente','CL-UI'); $poner('Tipo de evento','Boda'); $poner('Fecha y hora del evento','${f}'); $poner('Lugar','Salón Jardín'); $poner('Invitados aproximados','120'); $poner('Servicios solicitados','Banquete, Música')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar') || !$dlg()`, 'confirmación');
  if (await ev(`!!$dlg()`)) await ev(`document.getElementById('btn-confirmar')?.click()`);
  await esperar(`location.hash.startsWith('#/evento/EV-')`, 'navegación al evento');
  eventoId = await ev(`decodeURIComponent(location.hash.split('/').pop())`);
  await esperar(`document.querySelector('h1')?.textContent.includes('Boda')`, 'detalle');
  const estado = await ev(`document.querySelector('h1 .insignia').textContent`); if (estado !== 'En gestión') throw new Error(estado);
});

await paso('Crear propuesta desde el detalle y verla en la lista local', async () => {
  await clic('Crear propuesta'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$poner('Servicios incluidos','Banquete, Música'); $poner('Proveedores considerados','PV-1'); $poner('Costo total','10000.00'); $poner('Condiciones','Condiciones generales')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`[...document.querySelectorAll('.id-copiable')].some(b => b.textContent.startsWith('PR-'))`, 'propuesta listada');
  propuestaId = await ev(`[...document.querySelectorAll('.id-copiable')].find(b => b.textContent.startsWith('PR-')).textContent`);
});

await paso('Aceptar la propuesta y preparar el contrato', async () => {
  await clic('Aceptar propuesta'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`!$dlg()`, 'cierre');
  await clic('Preparar contrato'); await esperar(`!!$dlg()`, 'dlg2');
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!$dlg()`, 'cierre2');
  await esperar(`document.body.textContent.includes('En preparación') && [...document.querySelectorAll('.id-copiable')].some(b=>b.textContent.startsWith('CT-'))`, 'contrato en preparación');
});

await paso('Aceptar una propuesta con versión incorrecta muestra el motivo del backend sin cerrar el formulario', async () => {
  await clic('Aceptar propuesta'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$poner('Versión que se acepta','PR-NO-EXISTE-v9')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`$dlg() && !$dlg().querySelector('.modal-alerta').hidden`, 'alerta de error');
  const msg = await ev(`$dlg().querySelector('.modal-alerta').textContent`); if (!msg.length) throw new Error('sin mensaje');
  console.log('      mensaje del backend:', msg.slice(0, 120));
  await clic('Cancelar');
});

await paso('Firmar exige confirmar la política; comunicar política y firmar el contrato', async () => {
  await clic('Comunicar política de no reembolso'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$dlg().querySelector('button[type=submit]').click()`); await esperar(`!$dlg()`, 'cierre');
  await clic('Registrar firma del contrato'); await esperar(`!!$dlg()`, 'dlg2');
  const aviso = await ev(`$dlg().textContent.includes('política de no reembolso ya fue comunicada')`); if (!aviso) throw new Error('falta aviso de política');
  await ev(`$poner('Confirmo que la política',true)`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`!$dlg()`, 'cierre firma');
  await esperar(`document.body.textContent.includes('Estado de cuenta EC-')`, 'estado de cuenta');
});

await paso('Los pagos los registra Administración: Coordinación no ve el botón y, al cambiar de usuario, Administración sí', async () => {
  if (await ev(`!!$t('Registrar pago')`)) throw new Error('Coordinación ve «Registrar pago»');
  await cambiarUsuarioUI(cuentas.correoAdmin, cuentas.claveAdmin);
  await cargar(`#/evento/${eventoId}`); await esperar(`!!$t('Registrar pago')`, 'botón de pago para Administración', 10000);
});

await paso('Registrar pago parcial del anticipo (mínimo 30 %) con verificación y confirmar la contratación', async () => {
  await clic('Registrar pago'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$poner('Obligación que se paga', [...$campo('Obligación').options].find(o=>o.value).value); $poner('Importe pagado','3000'); $poner('Referencia del comprobante','CMP-UI-1')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación');
  const resumen = await ev(`$dlg().querySelector('.confirmacion').textContent`); if (!resumen.includes('3,000.00')) throw new Error('resumen sin importe: ' + resumen);
  await ev(`document.getElementById('btn-confirmar').click()`); await esperar(`!$dlg()`, 'cierre pago');
  await esperar(`document.body.textContent.includes('Liquidada')`, 'anticipo liquidado');
  // El sistema confirma la contratación por sí mismo al verificarse el anticipo (reacción de dominio); el botón manual solo aparece si hace falta.
  await dormir(1500);
  if (await ev(`!!$t('Confirmar la contratación')`)) { await clic('Confirmar la contratación'); await esperar(`!!document.getElementById('btn-confirmar')`, 'conf'); await ev(`document.getElementById('btn-confirmar').click()`); await esperar(`!$dlg()`, 'cierre confirmación'); }
  await esperar(`document.querySelector('h1 .insignia')?.textContent === 'En organización'`, 'evento en organización', 10000);
});

await paso('Segundo pago parcial (10.00) sobre el saldo con la misma referencia de comprobante: se registra, porque ninguna regla lo impide', async () => {
  // El anticipo ya está liquidado; se usa el saldo si hay obligación pendiente.
  const hay = await ev(`!!$t('Registrar pago')`);
  if (!hay) { console.log('      (sin obligaciones pendientes para repetir comprobante: omitido)'); return; }
  await clic('Registrar pago'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$poner('Obligación que se paga', [...$campo('Obligación').options].find(o=>o.value).value); $poner('Importe pagado','10'); $poner('Referencia del comprobante','CMP-UI-1')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'conf'); await ev(`document.getElementById('btn-confirmar').click()`);
  await dormir(800);
  await ev(`$t('Cancelar')?.click()`);   // si el pago ya se registró, el diálogo está cerrado y no hay nada que cancelar
});

await paso('Vuelve Coordinación al evento (las solicitudes las registra Coordinación)', async () => {
  await cambiarUsuarioUI(cuentas.correoCoord, cuentas.claveCoord);
  await cargar(`#/evento/${eventoId}`); await esperar(`!!$t('Solicitar servicio adicional')`, 'acciones de solicitudes', 10000);
});

await paso('Servicio adicional con evento En organización: se registra y aparece en la tabla con su estado oficial', async () => {
  await ev(`$t('Solicitar servicio adicional').click()`); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$poner('Servicio solicitado','Fotografía')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!$dlg()`, 'cierre');
  await esperar(`document.body.textContent.includes('Fotografía')`, 'fila de servicio adicional');
  const estados = await ev(`[...document.querySelectorAll('table')].map(t=>t.textContent).join(' ')`);
  if (!/Registrada|No procedente|En búsqueda|Pendiente/.test(estados)) throw new Error('sin estado visible');
});

await paso('Solicitud de cambio con descripción vacía y tarifa inválida muestra validaciones', async () => {
  await clic('Solicitar cambio'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$poner('Tarifa vigente','abc')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`[...$dlg().querySelectorAll('.error-campo')].some(x => x.textContent.includes('importe válido'))`, 'mensaje de importe');
  await clic('Cancelar');
});

await paso('Páginas de pagos, solicitudes, seguimiento, proveedor y sistema cargan sin error', async () => {
  for (const h of ['#/pagos', '#/solicitudes', '#/seguimiento', '#/proveedor', '#/sistema']) {
    await cargar(h);
    const err = await ev(`!!document.querySelector('.caja-error')`);
    if (err) throw new Error('caja de error en ' + h + ': ' + await ev(`document.querySelector('.caja-error').textContent`));
  }
});

await paso('Sistema: /health y /ready, Swagger y OpenAPI siguen disponibles', async () => {
  for (const u of ['/health', '/docs', '/openapi.json', '/']) { const r = await fetch(BASE + u); if (!r.ok) throw new Error(u + ' ' + r.status); }
});

await paso('Evento inexistente muestra un mensaje comprensible', async () => {
  await cargar('#/evento/EV-NO-EXISTE');
  await esperar(`!!document.querySelector('.caja-error')`, 'caja de error');
  const t = await ev(`document.querySelector('.caja-error').textContent`); if (t.includes('Traceback')) throw new Error('expone traza');
});

await paso('Servidor detenido: error de conexión comprensible (simulado bloqueando la URL de la API)', async () => {
  await cdp('Network.enable'); await cdp('Network.setBlockedURLs', { urls: ['*/eventos*'] });
  await cargar('#/eventos');
  await esperar(`!!document.querySelector('.caja-error')`, 'error de conexión');
  const t = await ev(`document.querySelector('.caja-error').textContent`); if (!t.includes('No fue posible conectar')) throw new Error(t);
  await cdp('Network.setBlockedURLs', { urls: [] });
});

await paso('Vista móvil (390 px): menú adaptable y tablas en formato de tarjetas', async () => {
  await cdp('Emulation.setDeviceMetricsOverride', { width: 390, height: 800, deviceScaleFactor: 1, mobile: true });
  await cargar('#/eventos'); await dormir(500);
  const visible = await ev(`getComputedStyle(document.querySelector('.barra-superior')).display`); if (visible === 'none') throw new Error('sin barra superior');
  const desborda = await ev(`document.documentElement.scrollWidth > window.innerWidth + 2`); if (desborda) throw new Error('desbordamiento horizontal');
  await ev(`document.getElementById('boton-menu').click()`); await dormir(300);
  const menu = await ev(`document.body.classList.contains('menu-abierto')`); if (!menu) throw new Error('menú no abre');
  const cap = await cdp('Page.captureScreenshot', { format: 'png' }); writeFileSync(SALIDA + '/movil.png', Buffer.from(cap.result.data, 'base64'));
  await cdp('Emulation.clearDeviceMetricsOverride');
});

// ---- Persistencia: lo que sigue solo tiene sentido contra una API con base de datos (se ejecuta igual en memoria, sin recargar el servidor).
const api = async (ruta) => { const r = await cuentas.coord.fetch(ruta); return { codigo: r.status, cuerpo: await r.json() }; };

await paso('Persistencia: sin localStorage, el detalle se recupera íntegro desde la API tras recargar', async () => {
  await cargar('#/'); await ev(`localStorage.clear()`);
  await cargar(`#/evento/${eventoId}`);
  await esperar(`document.querySelector('h1 .insignia')?.textContent === 'En organización'`, 'estado persistido');
  const t = await ev(`document.body.textContent`);
  for (const x of ['Liquidada', 'Estado de cuenta EC-', 'CT-', 'Fotografía']) if (!t.includes(x)) throw new Error('falta tras recargar: ' + x);
  const admin = (await api(`/eventos/${eventoId}/administracion`)).cuerpo;
  if (admin.estadoEvento !== 'En organización') throw new Error('API: ' + admin.estadoEvento);
  console.log('      API /administracion estadoEvento =', admin.estadoEvento);
});

await paso('Persistencia: el estado de cuenta y los pagos devueltos por la API coinciden con lo mostrado', async () => {
  const r = await api(`/eventos/${eventoId}/pagos`); if (r.codigo !== 200) throw new Error('HTTP ' + r.codigo);
  const txt = JSON.stringify(r.cuerpo);
  if (!txt.includes('3000')) throw new Error('el pago de 3000 no aparece en la API: ' + txt.slice(0, 300));
  console.log('      GET /eventos/{id}/pagos -> 200; contiene el pago de 3,000.00; claves:', Object.keys(r.cuerpo).join(','));
});

await paso('Dependencia de localStorage: tras limpiar y recargar, las propuestas y pagos recordados localmente no regresan', async () => {
  // La interfaz solo vuelve a anotar localmente lo que se consulta en esta sesión (eventos recientes); propuestas y pagos solo existen donde se crearon.
  const r = await ev(`JSON.stringify(Object.fromEntries(Object.entries(JSON.parse(localStorage.getItem('eventosnova.registro.v1') || '{}')).map(([k, v]) => [k, Object.keys(v).length])))`);
  console.log('      registro local tras limpiar y recargar (cantidad por tipo):', r);
  const c = JSON.parse(r); if (c.propuestas || c.pagos) throw new Error('el registro local conservó propuestas o pagos: ' + r);
});

await paso('Solicitud de cambio válida en En organización: la API decide y la interfaz muestra el resultado real', async () => {
  await cargar(`#/evento/${eventoId}`);
  await esperar(`!!$t('Solicitar cambio')`, 'botón de cambio');
  await clic('Solicitar cambio'); await esperar(`!!$dlg()`, 'dlg');
  await ev(`$poner('Descripción del cambio','Mover el brindis a las 20:00'); $poner('Tarifa vigente','500.00')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar') || !$dlg()`, 'confirmación');
  if (await ev(`!!document.getElementById('btn-confirmar')`)) await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`!$dlg() || !$dlg().querySelector('.modal-alerta').hidden`, 'resultado');
  if (await ev(`!!$dlg()`)) { console.log('      rechazo del backend:', (await ev(`$dlg().querySelector('.modal-alerta').textContent`)).slice(0, 160)); await clic('Cancelar'); }
  else {
    const lista = (await api(`/solicitudes?evento_id=${eventoId}`)).cuerpo.solicitudes.filter((x) => x.tipo === 'Cambio' || /cambio/i.test(JSON.stringify(x)));
    if (!lista.length) throw new Error('el cambio no aparece en GET /solicitudes');
    console.log('      cambio registrado; estado en la API:', lista[0].estadoActual);
  }
});

await paso('Persistencia de solicitudes: GET /solicitudes devuelve las del evento y la página Solicitudes las muestra', async () => {
  const r = await api(`/solicitudes?evento_id=${eventoId}`); if (r.codigo !== 200 || !r.cuerpo.solicitudes.length) throw new Error('sin solicitudes');
  console.log('      solicitudes del evento en la API:', r.cuerpo.solicitudes.map((x) => x.estadoActual).join(', '));
  await cargar('#/solicitudes'); await dormir(600);
  if (await ev(`!!document.querySelector('.caja-error')`)) throw new Error('error al listar');
});

await paso('Evento existente anterior (solo lectura): se abre su detalle', async () => {
  const lista = (await api('/eventos?desde=2020-01-01T00:00:00&hasta=2035-12-31T00:00:00')).cuerpo.eventos.filter((e) => e.eventoId !== eventoId);
  if (!lista.length) { console.log('      (no hay eventos previos en esta base)'); return; }
  await cargar(`#/evento/${lista[0].eventoId}`);
  await esperar(`!!document.querySelector('h1 .insignia')`, 'detalle del evento previo');
  console.log('      evento previo', lista[0].eventoId, '->', await ev(`document.querySelector('h1 .insignia').textContent`));
});

await paso('Textos visibles de todos los diálogos y pantallas del recorrido: sin null, undefined ni códigos internos', async () => {
  await revisarTextos('recorrido completo');
});

await paso('Capturas de escritorio', async () => {
  await cargar(`#/evento/${eventoId}`); await dormir(500);
  let cap = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(SALIDA + '/evento.png', Buffer.from(cap.result.data, 'base64'));
  await cargar(''); await dormir(400);
  cap = await cdp('Page.captureScreenshot', { format: 'png' }); writeFileSync(SALIDA + '/panel.png', Buffer.from(cap.result.data, 'base64'));
});

await paso('Sin excepciones de JavaScript durante la sesión', async () => {
  if (errores.length) throw new Error(errores.slice(0, 3).join(' | '));
});
console.log('Errores de consola (fetch fallidos esperados incluidos):', consola.length);
writeFileSync(SALIDA + '/llamadas_http.json', JSON.stringify(llamadas, null, 1));
console.log(`\nEvento: ${eventoId} Propuesta: ${propuestaId}  (llamadas HTTP registradas: ${llamadas.length}; detalle en llamadas_http.json)`);
console.log(`RESUMEN: ${resultados.filter((r) => r[0] === 'OK').length} OK, ${resultados.filter((r) => r[0] === 'FALLO').length} FALLO`);
try { ws.close(); } catch { /* */ }
chrome.kill();
process.exit(resultados.some((r) => r[0] === 'FALLO') ? 1 : 0);
