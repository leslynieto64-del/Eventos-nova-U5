// Pruebas de seguridad de extremo a extremo con Chrome real contra la API (con PostgreSQL, entorno manual): ingreso, roles, denegaciones del servidor,
// aislamiento del proveedor, caducidad de sesión, cookies y bloqueo por intentos.
//   EVENTOSNOVA_E2E_ADMIN_CORREO=… EVENTOSNOVA_E2E_ADMIN_CLAVE=… node scripts/probar_seguridad_navegador.mjs http://127.0.0.1:8001 <carpeta de capturas>
// Requiere una cuenta de administrador existente (scripts/crear_administrador.py). Crea cuentas y datos de prueba; no borra nada. Las contraseñas no se imprimen.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { Sesion, prepararCuentas } from './lib_sesion_e2e.mjs';

const BASE = process.argv[2] || 'http://127.0.0.1:8001';
const SALIDA = process.argv[3] || '.';
const MARCA = Date.now().toString(36).toUpperCase();
const PUERTO = 9338;
const perfil = mkdtempSync(join(tmpdir(), 'enova-seg-'));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--disable-gpu', '--no-sandbox', `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`, '--window-size=1280,900', 'about:blank'], { stdio: 'ignore' });
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
let ws; let id = 0; const pend = new Map(); const errores = [];
for (let i = 0; i < 40; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PUERTO}/json`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); await new Promise((a, b) => { ws.onopen = a; ws.onerror = b; }); break; } } catch { /* espera */ } await dormir(250); }
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); } if (d.method === 'Runtime.exceptionThrown') errores.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text); };
const cdp = (method, params = {}) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
async function ev(expr) { const r = await cdp('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.result.exceptionDetails) throw new Error('evaluate: ' + JSON.stringify(r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text)); return r.result.result.value; }
async function esperar(expr, texto, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch { /* reintenta */ } await dormir(120); } throw new Error('Tiempo agotado esperando: ' + texto); }
const resultados = [];
const paso = async (nombre, fn) => { try { await fn(); resultados.push(['OK', nombre]); console.log('OK   ', nombre); } catch (e) { resultados.push(['FALLO', nombre, e.message]); console.log('FALLO', nombre, '->', e.message); } };
const helpers = `(() => {
  window.$t = (txt, sel='button,a') => [...document.querySelectorAll(sel)].find(e => e.textContent.trim() === txt && e.offsetParent !== null);
  window.$campo = (txt) => { const l = [...document.querySelectorAll('dialog[open] label')].find(x => x.textContent.includes(txt)); return l && document.getElementById(l.getAttribute('for')); };
  window.$poner = (txt, v) => { const c = $campo(txt); if (!c) throw new Error('campo no encontrado: ' + txt); c.value = v; c.dispatchEvent(new Event('input', {bubbles:true})); };
  window.$dlg = () => document.querySelector('dialog[open]');
})()`;
const menu = () => ev(`[...document.querySelectorAll('#menu a')].filter(a => !a.hidden && a.offsetParent !== null).map(a => a.textContent.trim())`);
const ir = async (hash) => { await cdp('Page.navigate', { url: `${BASE}/app/${hash}` }); await dormir(700); await ev(helpers).catch(() => {}); };
async function ingresar(correo, clave) {
  await cdp('Page.navigate', { url: `${BASE}/app/` }); await dormir(700);
  await esperar(`!!document.getElementById('ing-correo')`, 'formulario de ingreso');
  await ev(`(() => { document.getElementById('ing-correo').value = ${JSON.stringify(correo)}; document.getElementById('ing-clave').value = ${JSON.stringify(clave)}; document.querySelector('.ingreso-forma button[type=submit]').click(); })()`);
}
async function ingresarYEsperar(correo, clave) { await ingresar(correo, clave); await esperar(`!document.getElementById('ing-correo') && !!document.querySelector('#sesion-caja button')`, 'sesión iniciada'); await ev(helpers); }
async function salir() { await ev(`[...document.querySelectorAll('#sesion-caja button')].find(b => b.textContent.trim() === 'Cerrar sesión').click()`); await esperar(`!!document.getElementById('ing-correo')`, 'ingreso tras salir'); }
const texto = () => ev('document.body.innerText');
const CODIGO = /\b(?:BN|CA|GL|SE|US|CU|RN|AR|TP|ADR|[ACDEHR])-\d{1,3}[A-Za-z]?\b(?!-)/;
const VACIO = /(^|[\s(«"'])(null|undefined|NaN)([\s.,;:)»"']|$)|\[object /;

const nueva = () => 'Prueba-' + randomBytes(12).toString('base64url');
const c = await prepararCuentas(BASE, MARCA);                                // administrador (variables de entorno) y coordinador de prueba
const crear = async (rol, nombre, extra = {}) => { const clave = nueva(); const correo = `${rol}.${nombre}.${MARCA}@eventosnova.example`.toLowerCase(); const r = await c.admin.json('POST', '/usuarios', { correo, nombre: `${nombre} ${MARCA}`, rol, contrasena: clave, ...extra }); return { correo, clave, usuarioId: r.datos.usuarioId }; };
await cdp('Runtime.enable'); await cdp('Page.enable'); await cdp('Network.enable');
let provA; let provB; let cuentaA; let cuentaB; let eventoId; let servicioId; let coordCuenta;

await paso('Sin sesión: la aplicación solo muestra el ingreso y la API responde 401', async () => {
  await ir('');
  await esperar(`!!document.getElementById('ing-correo')`, 'ingreso');
  if ((await menu()).length) throw new Error('hay menú sin sesión: ' + (await menu()));
  const cap = await cdp('Page.captureScreenshot', { format: 'png' }); writeFileSync(SALIDA + '/seg_ingreso.png', Buffer.from(cap.result.data, 'base64'));
  for (const ruta of ['/eventos?desde=2020-01-01T00:00:00&hasta=2030-01-01T00:00:00', '/pagos-pendientes', '/proveedores', '/usuarios']) {
    const r = await fetch(BASE + ruta); if (r.status !== 401) throw new Error(`${ruta} -> ${r.status}`);
  }
  const p = await fetch(BASE + '/eventos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) }); if (p.status !== 401) throw new Error('POST sin sesión -> ' + p.status);
});

await paso('Formulario vacío y credenciales incorrectas muestran mensajes comprensibles (sin revelar si el correo existe)', async () => {
  await ev(`document.querySelector('.ingreso-forma button[type=submit]').click()`);
  await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText?.includes('Escribe tu correo')`, 'mensaje de campos vacíos');
  await ingresar(c.correoCoord, 'contrasena-incorrecta-larga-1');
  await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText === 'Correo o contraseña incorrectos.'`, 'mensaje de credenciales');
  await ingresar('no.existe@eventosnova.example', 'contrasena-incorrecta-larga-1');
  await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText === 'Correo o contraseña incorrectos.'`, 'mismo mensaje con un correo inexistente');
  if (await ev(`!!document.querySelector('#sesion-caja button')`)) throw new Error('se inició sesión con credenciales incorrectas');
});

await paso('Administración: ingresa, ve Cuentas y Pagos, no ve «Mi proveedor», y no puede registrar eventos', async () => {
  await ingresarYEsperar(c.correoAdmin, c.claveAdmin);
  const m = await menu();
  for (const x of ['Panel principal', 'Pagos y devoluciones', 'Proveedores', 'Cuentas']) if (!m.includes(x)) throw new Error(`falta «${x}»: ${m}`);
  if (m.includes('Mi proveedor')) throw new Error('el administrador ve «Mi proveedor»');
  const caja = await ev(`document.getElementById('sesion-caja').innerText`); if (!caja.includes('Administración')) throw new Error(caja);
  await ir('#/eventos'); await esperar(`!!document.querySelector('h1')`, 'eventos');
  if (await ev(`!!$t('Registrar evento')`)) throw new Error('Administración ve «Registrar evento» (es de Coordinación)');
  const cap = await cdp('Page.captureScreenshot', { format: 'png' }); writeFileSync(SALIDA + '/seg_admin.png', Buffer.from(cap.result.data, 'base64'));
});

await paso('Cuentas: Administración crea una cuenta de coordinador desde la interfaz', async () => {
  await ir('#/cuentas'); await esperar(`!!$t('Crear cuenta')`, 'botón');
  await ev(`$t('Crear cuenta').click()`); await esperar(`!!$dlg() && !!$campo('Nombre de la persona')`, 'formulario');
  coordCuenta = { correo: `coord.ui.${MARCA}@eventosnova.example`.toLowerCase(), clave: nueva() };
  await ev(`$poner('Nombre de la persona', 'Coordinación creada en pantalla ${MARCA}'); $poner('Correo (será su usuario)', ${JSON.stringify(coordCuenta.correo)}); $poner('Rol', 'coordinador'); $poner('Contraseña inicial', 'corta')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`[...$dlg().querySelectorAll('.error-campo')].some(x => x.textContent.includes('al menos 12'))`, 'validación de contraseña corta');
  await ev(`$poner('Contraseña inicial', ${JSON.stringify(coordCuenta.clave)})`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`); await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación');
  const conf = await ev(`$dlg().querySelector('.confirmacion').innerText`); if (conf.includes(coordCuenta.clave)) throw new Error('la confirmación muestra la contraseña');
  await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`document.body.innerText.includes(${JSON.stringify(coordCuenta.correo)})`, 'cuenta en la lista');
  if ((await texto()).includes(coordCuenta.clave)) throw new Error('la pantalla muestra la contraseña');
});

await paso('Coordinación: sin «Cuentas»; la pantalla de cuentas y las operaciones de Administración se deniegan', async () => {
  await salir(); await ingresarYEsperar(coordCuenta.correo, coordCuenta.clave);
  const m = await menu(); if (m.includes('Cuentas')) throw new Error('Coordinación ve «Cuentas»');
  await ir('#/cuentas'); await esperar(`document.body.innerText.includes('No tienes permiso para ver esta pantalla')`, 'aviso de pantalla sin permiso');
  const r = await ev(`(async () => { const { api } = await import('/app/js/api.js'); try { await api('POST', '/usuarios', { cuerpo: { correo: 'x@y.mx', nombre: 'X', rol: 'administrador', contrasena: 'una-contrasena-larga-1' } }); return { ok: true }; } catch (e) { return { tipo: e.tipo, mensaje: e.message, estado: e.estado }; } })()`);
  console.log('      llamada directa de Coordinación a POST /usuarios ->', JSON.stringify(r));
  if (r.estado !== 403 || r.tipo !== 'permiso') throw new Error(JSON.stringify(r));
});

await paso('Aunque se eludan los botones, el servidor rechaza y el formulario muestra el motivo (registrar un pago como Coordinación)', async () => {
  await ir(''); await esperar(`!!document.getElementById('sesion-caja')`, 'inicio');
  await ev(`(async () => { const s = await import('/app/js/sesion.js'); s.estado.permisos.add('pagos.registrar');                      // simula manipular la interfaz
    const u = await import('/app/js/ui.js'); const a = await import('/app/js/acciones.js');
    u.ejecutarAccion(a.ACCIONES.registrarPago, { estadoCuentaId: 'EC-INEXISTENTE', contratoId: 'CT-X', obligaciones: [{ obligacionId: 'OB-X', concepto: 'Anticipo', saldo: '100.00' }] }); })()`);
  await esperar(`!!$dlg() && !!$campo('Importe pagado')`, 'formulario');
  await ev(`$poner('Importe pagado', '100'); $poner('Referencia del comprobante', 'CMP-SEG-1')`);
  await ev(`$dlg().querySelector('button[type=submit]').click()`); await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`$dlg() && !$dlg().querySelector('.modal-alerta').hidden`, 'alerta de denegación');
  const m = await ev(`$dlg().querySelector('.modal-alerta').innerText`); console.log('      mensaje del servidor:', m.split('\n')[0]);
  if (!m.includes('No tiene permiso')) throw new Error(m);
  await ev(`[...document.querySelectorAll('dialog[open] button')].find(b => b.textContent.trim() === 'Cancelar').click()`);
});

await paso('Cookie de sesión: HttpOnly, SameSite=Strict, invisible al JavaScript y sin credenciales en el almacenamiento del navegador', async () => {
  const cookies = (await cdp('Network.getCookies', { urls: [BASE] })).result.cookies;
  const s = cookies.find((x) => x.name === 'eventosnova_sesion'); if (!s) throw new Error('no hay cookie de sesión');
  console.log(`      cookie: httpOnly=${s.httpOnly} sameSite=${s.sameSite} secure=${s.secure} path=${s.path}`);
  if (!s.httpOnly || s.sameSite !== 'Strict') throw new Error('atributos de la cookie: ' + JSON.stringify({ h: s.httpOnly, s: s.sameSite }));
  const visible = await ev(`document.cookie`); if (visible.includes('eventosnova_sesion')) throw new Error('el JavaScript ve la cookie');
  const almacen = await ev(`JSON.stringify([localStorage, sessionStorage].map(a => Object.fromEntries(Object.entries(a))))`);
  if (almacen.includes(s.value) || almacen.includes(coordCuenta.clave)) throw new Error('el token o la contraseña están en el almacenamiento del navegador');
});

await paso('Preparar proveedores y un evento contratado con un servicio asignado (por la API)', async () => {
  provA = (await c.coord.json('POST', '/proveedores', { nombre: `Prueba seguridad A ${MARCA}`, servicios: [`Servicio seguridad ${MARCA}`], contacto: '' })).datos.proveedorId;
  provB = (await c.coord.json('POST', '/proveedores', { nombre: `Prueba seguridad B ${MARCA}`, servicios: [`Servicio seguridad ${MARCA}`], contacto: '' })).datos.proveedorId;
  cuentaA = await crear('proveedor', 'a', { proveedor_id: provA }); cuentaB = await crear('proveedor', 'b', { proveedor_id: provB });
  const ahora = () => new Date(Date.now() - 6 * 3600 * 1000).toISOString().slice(0, 19);
  const servicios = [`Servicio seguridad ${MARCA}`];
  eventoId = (await c.coord.json('POST', '/eventos', { cliente_id: 'CL-SEG', datos: { tipo: `Prueba seguridad ${MARCA}`, fecha_hora: new Date(Date.now() + 75 * 864e5).toISOString().slice(0, 19), lugar: 'Salón de prueba', invitados_aproximados: 20 }, servicios })).evento_id;
  const prop = (await c.coord.json('POST', `/eventos/${eventoId}/propuestas`, { servicios, proveedores_considerados: [provA], costo_total: '10000.00', condiciones: 'Prueba' })).propuesta_id;
  await c.coord.json('POST', `/propuestas/${prop}/aceptacion`, { version_id: `${prop}-v1` });
  const ct = (await c.coord.json('POST', `/propuestas/${prop}/contrato`, { politica_incluida: true })).datos.contrato_id;
  await c.coord.json('POST', `/contratos/${ct}/comunicacion-politica-no-reembolso`, { fecha: ahora() }); await c.coord.json('POST', `/contratos/${ct}/firma`, { fecha: ahora() });
  const ec = (await c.coord.json('GET', `/eventos/${eventoId}/pagos`)).estadosCuenta[0].estadoCuentaId;
  const ob = (await c.coord.json('GET', `/pagos-pendientes?evento_id=${eventoId}`)).pagos.find((p) => p.concepto === 'Anticipo');
  await c.admin.json('POST', `/estados-cuenta/${ec}/pagos`, { obligacion_id: ob.obligacionId, importe: '3000.00', fecha: ahora(), comprobante: `CMP-SEG-${MARCA}`, verificar_ahora: true });
  for (let i = 0; i < 20; i++) { if ((await c.coord.json('GET', `/eventos/${eventoId}/administracion`)).estadoEvento === 'En organización') break; await dormir(300); }
  servicioId = (await c.coord.json('GET', `/eventos/${eventoId}/administracion`)).proveedores[0].servicioContratadoId;
  await c.coord.json('POST', `/eventos/${eventoId}/servicios/${servicioId}/proveedor`, { proveedor_id: provA });
});

await paso('Proveedor A: su menú es solo lo suyo, no entra a eventos ni cuentas y ve únicamente su servicio', async () => {
  await salir(); await ingresarYEsperar(cuentaA.correo, cuentaA.clave);
  const m = await menu(); console.log('      menú del proveedor:', JSON.stringify(m));
  if (JSON.stringify(m) !== JSON.stringify(['Mi proveedor', 'Sistema y ayuda'])) throw new Error('menú inesperado: ' + m);
  await ir('#/eventos'); await esperar(`document.body.innerText.includes('No tienes permiso para ver esta pantalla')`, 'eventos denegado');
  await ir('#/proveedor'); await esperar(`!!document.getElementById('p-ev')`, 'consulta propia');
  if (await ev(`!!document.getElementById('p-prov')`)) throw new Error('el proveedor puede escribir un identificador de proveedor');
  await ev(`(() => { const e = document.getElementById('p-ev'); e.value = ${JSON.stringify(eventoId)}; e.form.querySelector('button[type=submit]').click(); })()`);
  await esperar(`document.body.innerText.includes('Servicio seguridad ${MARCA}')`, 'su servicio');
  await esperar(`!!$t('Registrar respuesta del proveedor') || !![...document.querySelectorAll('button')].find(b => b.textContent.includes('respuesta'))`, 'acción de respuesta');
  const cap = await cdp('Page.captureScreenshot', { format: 'png' }); writeFileSync(SALIDA + '/seg_proveedor.png', Buffer.from(cap.result.data, 'base64'));
});

await paso('Proveedor A no puede consultar ni responder por el proveedor B (llamadas directas y formulario)', async () => {
  const r = await ev(`(async () => { const { api } = await import('/app/js/api.js'); const salida = {};
    for (const [k, ruta] of [['ficha de B', '/proveedores/${provB}'], ['servicios de B', '/proveedores/${provB}/eventos/${eventoId}']]) { try { await api('GET', ruta); salida[k] = 'permitido'; } catch (e) { salida[k] = e.estado + ' ' + e.message; } }
    try { await api('GET', '/proveedores'); salida.catalogo = 'permitido'; } catch (e) { salida.catalogo = e.estado + ' ' + e.message; }
    return salida; })()`);
  console.log('      ', JSON.stringify(r));
  for (const k of ['ficha de B', 'servicios de B', 'catalogo']) if (!String(r[k]).startsWith('403')) throw new Error(`${k}: ${r[k]}`);
  // Formulario: el proveedor cambia el identificador a otro proveedor y el servidor lo rechaza
  await ev(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('respuesta')).click()`);
  await esperar(`!!$dlg() && !!$campo('Identificador del proveedor')`, 'formulario de respuesta');
  await ev(`$poner('Identificador del proveedor', '${provB}')`); await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`$dlg() && !$dlg().querySelector('.modal-alerta').hidden`, 'alerta');
  const m = await ev(`$dlg().querySelector('.modal-alerta').innerText`); console.log('      mensaje:', m.split('\n')[0]);
  if (!m.includes('su propio proveedor')) throw new Error(m);
  // con su propio identificador sí puede
  await ev(`$poner('Identificador del proveedor', '${provA}')`); await ev(`$dlg().querySelector('button[type=submit]').click()`);
  await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación'); await ev(`document.getElementById('btn-confirmar').click()`);
  await esperar(`!$dlg()`, 'respuesta registrada');
  await esperar(`document.body.innerText.includes('Confirmado por el proveedor')`, 'servicio confirmado');
  const admin = await c.coord.json('GET', `/eventos/${eventoId}/administracion`); if (admin.proveedores[0].estado !== 'Confirmado por el proveedor') throw new Error('no quedó confirmado en el servidor');
});

await paso('Proveedor B no ve los servicios del proveedor A', async () => {
  await salir(); await ingresarYEsperar(cuentaB.correo, cuentaB.clave);
  await ir('#/proveedor'); await esperar(`!!document.getElementById('p-ev')`, 'consulta');
  await ev(`(() => { const e = document.getElementById('p-ev'); e.value = ${JSON.stringify(eventoId)}; e.form.querySelector('button[type=submit]').click(); })()`);
  await esperar(`document.body.innerText.includes('no tiene servicios asignados') || document.body.innerText.includes('No se encontró')`, 'sin servicios para B');
  if ((await texto()).includes(`Servicio seguridad ${MARCA}`)) throw new Error('B ve el servicio de A');
});

await paso('Sesión caducada o cerrada desde el servidor: la interfaz vuelve al ingreso con una explicación', async () => {
  await salir(); await ingresarYEsperar(coordCuenta.correo, coordCuenta.clave);
  await ir('#/eventos'); await esperar(`!!document.querySelector('h1')`, 'eventos');
  await c.admin.json('POST', `/usuarios/${(await c.admin.json('GET', '/usuarios')).datos.usuarios.find((u) => u.correo === coordCuenta.correo).usuarioId}/estado`, { activo: false });   // el servidor invalida sus sesiones
  await ev(`location.hash = '#/solicitudes'`);
  await esperar(`!!document.getElementById('ing-correo')`, 'ingreso tras la caducidad');
  const t = await ev(`(document.querySelector('.alerta-ingreso')||{}).innerText || ''`); console.log('      mensaje:', t);
  if (!/sesión|cuenta/i.test(t)) throw new Error('sin explicación: ' + t);
  if ((await menu()).length) throw new Error('quedó menú visible');
  await ingresar(coordCuenta.correo, coordCuenta.clave);
  await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText === 'Correo o contraseña incorrectos.'`, 'cuenta desactivada no entra');
});

await paso('Cerrar sesión invalida el acceso aunque se conserve la cookie anterior', async () => {
  await ingresarYEsperar(c.correoAdmin, c.claveAdmin);
  const antes = (await cdp('Network.getCookies', { urls: [BASE] })).result.cookies.find((x) => x.name === 'eventosnova_sesion').value;
  await salir();
  const r = await fetch(BASE + '/auth/yo', { headers: { Cookie: `eventosnova_sesion=${antes}` } }); const cuerpo = await r.json();
  console.log('      con la cookie anterior:', r.status, cuerpo.tipo);
  if (r.status !== 401 || cuerpo.tipo !== 'sesion_expirada') throw new Error(r.status + ' ' + JSON.stringify(cuerpo));
});

await paso('Limitación de intentos: tras varios fallos seguidos se bloquea el ingreso y la interfaz lo explica', async () => {
  const cuenta = await crear('coordinador', 'bloqueo');
  for (let i = 0; i < 5; i++) { await ingresar(cuenta.correo, 'incorrecta-larga-' + i); await esperar(`!!(document.querySelector('.alerta-ingreso')||{}).innerText && !document.querySelector('.ingreso-forma button[disabled]')`, 'respuesta ' + i); }
  await ingresar(cuenta.correo, cuenta.clave);                                // ahora con la contraseña CORRECTA: sigue bloqueada
  await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText?.includes('Demasiados intentos')`, 'mensaje de bloqueo');
  console.log('      mensaje:', await ev(`document.querySelector('.alerta-ingreso').innerText`));
});

await paso('Los textos de todas las pantallas de seguridad no muestran null, undefined ni códigos internos', async () => {
  await ingresarYEsperar(c.correoAdmin, c.claveAdmin);
  for (const h of ['#/', '#/cuentas', '#/eventos', '#/pagos', '#/proveedores', '#/sistema']) {
    await ir(h); await dormir(900); const t = await texto();
    const malos = t.split('\n').filter((l) => VACIO.test(l) || CODIGO.test(l)); if (malos.length) throw new Error(h + ': ' + malos.slice(0, 2).join(' / '));
  }
});

await paso('Sin excepciones de JavaScript', async () => { if (errores.length) throw new Error(errores.slice(0, 3).join(' | ')); });
console.log(`\nRESUMEN: ${resultados.filter((r) => r[0] === 'OK').length} OK, ${resultados.filter((r) => r[0] === 'FALLO').length} FALLO`);
try { ws.close(); } catch { /* */ }
chrome.kill();
process.exit(resultados.some((r) => r[0] === 'FALLO') ? 1 : 0);
