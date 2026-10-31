// Pruebas de diseño responsivo y de acceso por rol con Chrome real contra la API con PostgreSQL (entorno manual).
//   EVENTOSNOVA_E2E_ADMIN_CORREO=… EVENTOSNOVA_E2E_ADMIN_CLAVE=… node scripts/probar_responsivo_navegador.mjs http://127.0.0.1:8001 <carpeta de capturas>
// Mide, en 320, 390, 768, 1024 y 1440 px: desbordamiento horizontal global, elementos fuera de la pantalla, diálogos que no caben y botones inaccesibles,
// en el ingreso y en las pantallas de Administración y de Coordinación; comprueba el ingreso por rol (cuenta existente, activa y con credenciales válidas),
// el rechazo de credenciales incorrectas y de cuentas desactivadas, los menús por rol, el rechazo del backend, el cierre y la caducidad de sesión.
// Crea cuentas y datos de prueba (no borra nada). No imprime contraseñas.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { prepararCuentas } from './lib_sesion_e2e.mjs';

const BASE = process.argv[2] || 'http://127.0.0.1:8001';
const SALIDA = process.argv[3] || '.';
const MARCA = Date.now().toString(36).toUpperCase();
const PUERTO = 9339;
const TAMANOS = [[320, 640], [390, 844], [768, 1024], [1024, 768], [1440, 900]];
const perfil = mkdtempSync(join(tmpdir(), 'enova-resp-'));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--disable-gpu', '--no-sandbox', `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`, 'about:blank'], { stdio: 'ignore' });
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
let ws; let id = 0; const pend = new Map(); const errores = [];
for (let i = 0; i < 40; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PUERTO}/json`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); await new Promise((a, b) => { ws.onopen = a; ws.onerror = b; }); break; } } catch { /* espera */ } await dormir(250); }
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); } if (d.method === 'Runtime.exceptionThrown') errores.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text); };
const cdp = (method, params = {}) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
async function ev(expr) { const r = await cdp('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.result.exceptionDetails) throw new Error('evaluate: ' + JSON.stringify(r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text)); return r.result.result.value; }
async function esperar(expr, texto, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch { /* reintenta */ } await dormir(120); } throw new Error('Tiempo agotado esperando: ' + texto); }
const resultados = [];
const paso = async (nombre, fn) => { try { await fn(); resultados.push(['OK', nombre]); console.log('OK   ', nombre); } catch (e) { resultados.push(['FALLO', nombre, e.message]); console.log('FALLO', nombre, '->', e.message); } };

const MEDIR = `(() => {
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  const desplazable = (e) => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  const fuera = [...document.querySelectorAll('body *')].filter((e) => {
    const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || cs.position === 'fixed' || e.classList.contains('salto')) return false;   // el enlace «Saltar al contenido» está fuera a propósito
    const r = e.getBoundingClientRect(); if (!r.width || !r.height) return false;
    if (e.closest('.lateral') && document.documentElement.clientWidth <= 900 && !document.body.classList.contains('menu-abierto')) return false;
    return (r.right > vw + 1 || r.left < -1) && !desplazable(e);
  }).slice(0, 4).map((e) => e.tagName.toLowerCase() + '.' + String(e.className).split(' ')[0] + ' [' + Math.round(e.getBoundingClientRect().left) + ',' + Math.round(e.getBoundingClientRect().right) + ']');
  const botonesFuera = [...document.querySelectorAll('button, a.btn, input, select')].filter((e) => {
    const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || e.hidden || e.closest('[hidden]')) return false;
    if (e.closest('.lateral') && vw <= 900 && !document.body.classList.contains('menu-abierto')) return false;
    const r = e.getBoundingClientRect(); return r.width && (r.right > vw + 1 || r.left < -1) && !desplazable(e);
  }).slice(0, 3).map((e) => (e.textContent || e.name || e.id).trim().slice(0, 30));
  const d = document.querySelector('dialog[open]'); let dlg = null;
  if (d) { const r = d.getBoundingClientRect(); const pie = d.querySelector('.modal-pie'); const pr = pie && pie.getBoundingClientRect();
    dlg = { cabe: r.left >= -1 && r.right <= vw + 1 && r.top >= -1 && r.bottom <= vh + 1, pie: !pie || (pr.bottom <= vh + 1 && pr.right <= vw + 1 && pr.left >= -1), ancho: Math.round(r.width), alto: Math.round(r.height) }; }
  return { vw, sw: document.documentElement.scrollWidth, desborda: document.documentElement.scrollWidth > vw + 1, fuera, botonesFuera, dlg };
})()`;
const tam = async (w, h) => { await cdp('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w <= 768 }); await dormir(250); };
const captura = async (nombre, completa = false) => { const c = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: completa }); writeFileSync(`${SALIDA}/${nombre}.png`, Buffer.from(c.result.data, 'base64')); };
const ir = async (hash) => { await cdp('Page.navigate', { url: `${BASE}/app/${hash}` }); await dormir(500); await esperar(`document.readyState === 'complete' && !document.querySelector('.cargando')`, 'carga ' + hash, 12000); await dormir(300); };
async function ingresar(correo, clave) {
  await cdp('Page.navigate', { url: `${BASE}/app/` }); await dormir(500);
  await esperar(`!!document.getElementById('ing-correo')`, 'formulario de ingreso');
  await ev(`(() => { document.getElementById('ing-correo').value = ${JSON.stringify(correo)}; document.getElementById('ing-clave').value = ${JSON.stringify(clave)}; document.querySelector('.ingreso-forma button[type=submit]').click(); })()`);
}
async function entrar(correo, clave) { await cdp('Network.clearBrowserCookies'); await ingresar(correo, clave); await esperar(`!document.getElementById('ing-correo') && !!document.querySelector('#sesion-caja button')`, 'sesión iniciada'); }
async function salir() {
  await ev(`(() => { if (document.body.classList.contains('menu-abierto') === false && document.getElementById('boton-menu').offsetParent) document.getElementById('boton-menu').click(); })()`);
  await ev(`[...document.querySelectorAll('#sesion-caja button')].find(b => b.textContent.trim() === 'Cerrar sesión').click()`); await esperar(`!!document.getElementById('ing-correo')`, 'ingreso tras salir');
}
const menu = () => ev(`[...document.querySelectorAll('#menu a')].filter(a => !a.hidden).map(a => a.textContent.trim())`);
const texto = () => ev('document.body.innerText');
const CODIGO = /\b(?:BN|CA|GL|SE|US|CU|RN|AR|TP|ADR|[ACDEHR])-\d{1,3}[A-Za-z]?\b(?!-)/;
const VACIO = /(^|[\s(«"'])(null|undefined|NaN)([\s.,;:)»"']|$)|\[object /;
const nueva = () => 'Prueba-' + randomBytes(12).toString('base64url');
const revisar = (m, etiqueta) => { const malo = m.desborda ? `desbordamiento horizontal global (${m.sw} > ${m.vw})` : m.fuera.length ? 'elementos fuera: ' + m.fuera.join('; ') : m.botonesFuera.length ? 'controles fuera: ' + m.botonesFuera.join('; ') : (m.dlg && !m.dlg.cabe) ? 'el diálogo no cabe: ' + JSON.stringify(m.dlg) : (m.dlg && !m.dlg.pie) ? 'los botones del diálogo quedan fuera' : null; if (malo) throw new Error(`${etiqueta}: ${malo}`); };

const c = await prepararCuentas(BASE, MARCA);                                // administrador (variables de entorno) y coordinador de prueba
await cdp('Runtime.enable'); await cdp('Page.enable'); await cdp('Network.enable');
const claveDesactivada = nueva(); const correoDesactivada = `desactivada.${MARCA}@eventosnova.example`.toLowerCase();
const u = await c.admin.json('POST', '/usuarios', { correo: correoDesactivada, nombre: `Cuenta desactivada ${MARCA}`, rol: 'coordinador', contrasena: claveDesactivada });
await c.admin.json('POST', `/usuarios/${u.datos.usuarioId}/estado`, { activo: false });
let eventoId;

await paso('Datos de prueba: un evento contratado (por la API) para medir el detalle', async () => {
  const ahora = () => new Date(Date.now() - 6 * 3600 * 1000).toISOString().slice(0, 19);
  const servicios = ['Banquete', 'Música'];
  eventoId = (await c.coord.json('POST', '/eventos', { cliente_id: 'CL-RESP', datos: { tipo: `Prueba responsivo ${MARCA}`, fecha_hora: new Date(Date.now() + 75 * 864e5).toISOString().slice(0, 19), lugar: 'Salón de prueba', invitados_aproximados: 60 }, servicios })).evento_id;
  const prop = (await c.coord.json('POST', `/eventos/${eventoId}/propuestas`, { servicios, proveedores_considerados: ['PV-X'], costo_total: '10000.00', condiciones: 'Prueba' })).propuesta_id;
  await c.coord.json('POST', `/propuestas/${prop}/aceptacion`, { version_id: `${prop}-v1` });
  const ct = (await c.coord.json('POST', `/propuestas/${prop}/contrato`, { politica_incluida: true })).datos.contrato_id;
  await c.coord.json('POST', `/contratos/${ct}/comunicacion-politica-no-reembolso`, { fecha: ahora() }); await c.coord.json('POST', `/contratos/${ct}/firma`, { fecha: ahora() });
  const ec = (await c.coord.json('GET', `/eventos/${eventoId}/pagos`)).estadosCuenta[0].estadoCuentaId;
  const ob = (await c.coord.json('GET', `/pagos-pendientes?evento_id=${eventoId}`)).pagos.find((p) => p.concepto === 'Anticipo');
  await c.admin.json('POST', `/estados-cuenta/${ec}/pagos`, { obligacion_id: ob.obligacionId, importe: '3000.00', fecha: ahora(), comprobante: `CMP-RESP-${MARCA}`, verificar_ahora: true });
  for (let i = 0; i < 20; i++) { if ((await c.coord.json('GET', `/eventos/${eventoId}/administracion`)).estadoEvento === 'En organización') break; await dormir(300); }
  await c.coord.json('POST', '/solicitudes-servicio-adicional', { evento_id: eventoId, contrato_id: ct, servicio: 'Fotografía' });
});

for (const [w, h] of TAMANOS) {
  await paso(`${w}×${h}: el ingreso está centrado, con tarjeta legible, sin desbordamiento y sin que el error desplace el formulario`, async () => {
    await tam(w, h); await cdp('Page.navigate', { url: `${BASE}/app/` }); await dormir(600);
    await esperar(`!!document.getElementById('ing-correo')`, 'ingreso');
    const g = JSON.parse(await ev(`(() => { const t = document.querySelector('.ingreso').getBoundingClientRect(); const vw = document.documentElement.clientWidth, vh = innerHeight;
      const campo = document.getElementById('ing-correo').getBoundingClientRect(), boton = document.querySelector('.ingreso-forma button').getBoundingClientRect();
      return JSON.stringify({ vw, vh, izq: t.left, der: vw - t.right, arriba: t.top, abajo: vh - t.bottom, ancho: t.width, alto: t.height, campoAlto: campo.height, botonAlto: boton.height, fuente: parseFloat(getComputedStyle(document.getElementById('ing-correo')).fontSize), sw: document.documentElement.scrollWidth }); })()`));
    console.log(`      tarjeta ${Math.round(g.ancho)}×${Math.round(g.alto)} px · márgenes izq ${Math.round(g.izq)} / der ${Math.round(g.der)} · arriba ${Math.round(g.arriba)} / abajo ${Math.round(g.abajo)} · campo ${Math.round(g.campoAlto)} px · botón ${Math.round(g.botonAlto)} px · fuente ${g.fuente} px`);
    if (g.sw > g.vw + 1) throw new Error('desbordamiento horizontal');
    if (Math.abs(g.izq - g.der) > 2) throw new Error('la tarjeta no está centrada horizontalmente');
    if (g.arriba < 0 || g.abajo < 0) throw new Error('la tarjeta no cabe en la altura de la ventana');
    if (g.alto < g.vh - 40 && Math.abs(g.arriba - g.abajo) > Math.max(24, g.vh * 0.2)) throw new Error('posición vertical desequilibrada');
    if (w >= 768 && (g.ancho < 400 || g.ancho > 470)) throw new Error('ancho fuera del rango 400–470 px: ' + g.ancho);
    if (w < 768 && g.ancho < w - 2 * 24 - 2) throw new Error('en móvil la tarjeta debería usar casi todo el ancho');
    if (g.campoAlto < 44 || g.botonAlto < 44 || g.fuente < 16) throw new Error('campos o botón demasiado pequeños');
    const tope = g.arriba;
    await ev(`document.querySelector('.ingreso-forma button[type=submit]').click()`);
    await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText?.includes('Escribe tu correo')`, 'mensaje');
    const t2 = await ev(`document.querySelector('.ingreso').getBoundingClientRect().top`);
    console.log(`      desplazamiento de la tarjeta al aparecer el error: ${Math.round(Math.abs(t2 - tope))} px`);
    if (Math.abs(t2 - tope) > 1) throw new Error('el mensaje de error desplaza el formulario');
    revisar(JSON.parse(JSON.stringify(await ev(MEDIR))), 'ingreso con error');
    await captura(`login_${w}`);
  });
}

await paso('Credenciales incorrectas y cuenta desactivada se rechazan con un mensaje claro (y sin revelar el motivo)', async () => {
  await tam(1440, 900);
  await ingresar(c.correoAdmin, 'contrasena-incorrecta-larga-1');
  await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText === 'Correo o contraseña incorrectos.'`, 'credenciales incorrectas');
  await ingresar(correoDesactivada, claveDesactivada);                      // credenciales válidas pero cuenta desactivada
  await esperar(`(document.querySelector('.alerta-ingreso')||{}).innerText === 'Correo o contraseña incorrectos.'`, 'cuenta desactivada');
  if (await ev(`!!document.querySelector('#sesion-caja button')`)) throw new Error('entró con una cuenta desactivada');
});

const ROLES = [
  { nombre: 'Administración', correo: c.correoAdmin, clave: c.claveAdmin, menu: ['Panel principal', 'Eventos', 'Solicitudes', 'Pagos y devoluciones', 'Seguimiento', 'Proveedores', 'Cuentas', 'Sistema y ayuda'], sin: ['Mi proveedor'],
    paginas: ['#/', '#/eventos', '#/solicitudes', '#/pagos', '#/seguimiento', '#/proveedores', '#/cuentas', '#/sistema'] },
  { nombre: 'Coordinación', correo: c.correoCoord, clave: c.claveCoord, menu: ['Panel principal', 'Eventos', 'Solicitudes', 'Pagos y devoluciones', 'Seguimiento', 'Proveedores', 'Sistema y ayuda'], sin: ['Cuentas', 'Mi proveedor'],
    paginas: ['#/', '#/eventos', '#/solicitudes', '#/pagos', '#/seguimiento', '#/proveedores', '#/sistema'] },
];

for (const rol of ROLES) {
  await paso(`${rol.nombre}: inicia sesión con su cuenta, el servidor le asigna su rol y el menú muestra solo lo suyo`, async () => {
    await tam(1440, 900); await entrar(rol.correo, rol.clave);
    const m = await menu(); console.log(`      menú: ${JSON.stringify(m)}`);
    if (JSON.stringify(m) !== JSON.stringify(rol.menu)) throw new Error('menú inesperado: ' + m);
    for (const x of rol.sin) if (m.includes(x)) throw new Error(`ve «${x}»`);
    const caja = await ev(`document.getElementById('sesion-caja').innerText`); if (!caja.includes(rol.nombre)) throw new Error('la caja de sesión no indica el rol: ' + caja);
    if (await ev(`!!document.querySelector('select[name=rol], #ing-rol')`)) throw new Error('hay un selector de rol');
    await salir();
  });
}

await paso('El formulario de ingreso no ofrece escoger un rol: el rol sale únicamente de la cuenta', async () => {
  await tam(1440, 900); await cdp('Page.navigate', { url: `${BASE}/app/` }); await dormir(600); await esperar(`!!document.getElementById('ing-correo')`, 'ingreso');
  const campos = await ev(`[...document.querySelectorAll('.ingreso-forma input, .ingreso-forma select')].map(e => e.type + ':' + (e.name || e.id))`);
  console.log('      campos del formulario:', JSON.stringify(campos));
  if (campos.some((x) => /rol/i.test(x)) || JSON.stringify(campos) !== JSON.stringify(['email:correo', 'password:contrasena'])) throw new Error('campos inesperados: ' + campos);
});

for (const rol of ROLES) {
  for (const [w, h] of TAMANOS) {
    await paso(`${rol.nombre} a ${w} px: todas sus pantallas (${rol.paginas.length}) y el detalle de evento sin desbordamiento ni controles fuera de la pantalla`, async () => {
      await tam(w, h); await entrar(rol.correo, rol.clave);
      for (const hash of [...rol.paginas, `#/evento/${eventoId}`]) {
        await ir(hash);
        const m = JSON.parse(JSON.stringify(await ev(MEDIR))); revisar(m, hash);
        const t = await texto(); const malos = t.split('\\n').filter((l) => VACIO.test(l) || CODIGO.test(l)); if (malos.length) throw new Error(`${hash}: texto indebido: ${malos[0]}`);
        if (hash === '#/' || hash.startsWith('#/evento')) await captura(`${rol.nombre === 'Coordinación' ? 'coord' : 'admin'}_${hash === '#/' ? 'panel' : 'evento'}_${w}`, hash.startsWith('#/evento'));
      }
      if (w <= 900) {                                                     // menú: se despliega y se cierra con la barra superior
        await ev(`document.getElementById('boton-menu').click()`); await dormir(350);
        const m = JSON.parse(JSON.stringify(await ev(MEDIR))); revisar(m, 'menú desplegado');
        const vis = await ev(`(() => { const r = document.querySelector('.lateral').getBoundingClientRect(); return r.left >= -1 && r.right <= document.documentElement.clientWidth + 1; })()`);
        if (!vis) throw new Error('el menú desplegado no cabe en la pantalla'); await captura(`${rol.nombre === 'Coordinación' ? 'coord' : 'admin'}_menu_${w}`);
        await ev(`document.getElementById('boton-menu').click()`);
      }
      await salir();
    });
  }
}

for (const [w, h] of [[320, 640], [390, 844], [768, 1024]]) {
  await paso(`${w} px: formularios y cuadros de confirmación caben, con sus botones accesibles (Coordinación: registrar evento; Administración: crear cuenta)`, async () => {
    await tam(w, h); await entrar(c.correoCoord, c.claveCoord); await ir('#/eventos');
    await ev(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Registrar evento').click()`); await esperar(`!!document.querySelector('dialog[open]')`, 'diálogo');
    revisar(JSON.parse(JSON.stringify(await ev(MEDIR))), 'formulario Registrar evento'); await captura(`dialogo_evento_${w}`);
    await ev(`document.querySelector('dialog[open] button[type=submit]').click()`); await esperar(`[...document.querySelectorAll('dialog[open] .error-campo')].some(x => x.textContent.includes('obligatorio'))`, 'validaciones');
    revisar(JSON.parse(JSON.stringify(await ev(MEDIR))), 'formulario con validaciones'); await captura(`dialogo_validacion_${w}`);
    await ev(`[...document.querySelectorAll('dialog[open] button')].find(b => b.textContent.trim() === 'Cancelar').click()`);
    await ir(`#/evento/${eventoId}`);
    await ev(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Cancelar evento (solicitud del Cliente)').click()`); await esperar(`!!document.querySelector('dialog[open]')`, 'diálogo de cancelación');
    await ev(`(() => { const t = document.querySelector('dialog[open] textarea, dialog[open] input[type=text]'); t.value = 'Prueba de diálogo'; t.dispatchEvent(new Event('input', { bubbles: true })); document.querySelector('dialog[open] button[type=submit]').click(); })()`);
    await esperar(`!!document.getElementById('btn-confirmar')`, 'confirmación');
    revisar(JSON.parse(JSON.stringify(await ev(MEDIR))), 'cuadro de confirmación'); await captura(`dialogo_confirmacion_${w}`);
    await ev(`[...document.querySelectorAll('dialog[open] button')].find(b => b.textContent.trim() === 'Volver').click()`);       // no se confirma: no cancela el evento
    await ev(`[...document.querySelectorAll('dialog[open] button')].find(b => b.textContent.trim() === 'Cancelar').click()`);
    await salir();
    await entrar(c.correoAdmin, c.claveAdmin); await ir('#/cuentas');
    await ev(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Crear cuenta').click()`); await esperar(`!!document.querySelector('dialog[open]')`, 'diálogo');
    revisar(JSON.parse(JSON.stringify(await ev(MEDIR))), 'formulario Crear cuenta'); await captura(`dialogo_cuenta_${w}`);
    await ev(`[...document.querySelectorAll('dialog[open] button')].find(b => b.textContent.trim() === 'Cancelar').click()`);
    await salir();
  });
}

await paso('El backend rechaza lo que el rol no tiene autorizado aunque se eluda la interfaz (Coordinación y Administración)', async () => {
  await tam(1440, 900); await entrar(c.correoCoord, c.claveCoord);
  const r1 = await ev(`(async () => { const { api } = await import('/app/js/api.js'); const o = {}; for (const [k, m, ruta, cuerpo] of [['Coordinación registra un pago', 'POST', '/estados-cuenta/EC-X/pagos', {}], ['Coordinación crea una cuenta', 'POST', '/usuarios', { correo: 'x@y.mx', nombre: 'X', rol: 'administrador', contrasena: 'una-contrasena-larga-1' }], ['Coordinación autoriza un cambio', 'POST', '/solicitudes-cambio/SC-X/autorizacion', {}]]) { try { await api(m, ruta, { cuerpo }); o[k] = 'permitido'; } catch (e) { o[k] = e.estado + ' ' + e.message; } } return o; })()`);
  console.log('      ', JSON.stringify(r1));
  for (const v of Object.values(r1)) if (!String(v).startsWith('403')) throw new Error('no se rechazó: ' + JSON.stringify(r1));
  await salir(); await entrar(c.correoAdmin, c.claveAdmin);
  const r2 = await ev(`(async () => { const { api } = await import('/app/js/api.js'); const o = {}; for (const [k, m, ruta, cuerpo] of [['Administración registra un evento', 'POST', '/eventos', {}], ['Administración crea una propuesta', 'POST', '/eventos/EV-X/propuestas', {}], ['Administración firma un contrato', 'POST', '/contratos/CT-X/firma', {}]]) { try { await api(m, ruta, { cuerpo }); o[k] = 'permitido'; } catch (e) { o[k] = e.estado + ' ' + e.message; } } return o; })()`);
  console.log('      ', JSON.stringify(r2));
  for (const v of Object.values(r2)) if (!String(v).startsWith('403')) throw new Error('no se rechazó: ' + JSON.stringify(r2));
  await salir();
});

await paso('Cierre de sesión y sesión expirada: se vuelve al ingreso con una explicación y sin acceso a datos', async () => {
  await tam(390, 844); await entrar(c.correoCoord, c.claveCoord);
  await salir();
  const sinSesion = await ev(`(async () => (await fetch('/eventos?desde=2020-01-01T00:00:00&hasta=2030-01-01T00:00:00')).status)()`); if (sinSesion !== 401) throw new Error('tras cerrar sesión la API respondió ' + sinSesion);
  await entrar(c.correoCoord, c.claveCoord); await ir('#/eventos');
  await c.admin.json('POST', `/usuarios/${(await c.admin.json('GET', '/usuarios')).datos.usuarios.find((x) => x.correo === c.correoCoord).usuarioId}/estado`, { activo: false });   // el servidor invalida su sesión
  await ev(`location.hash = '#/solicitudes'`); await esperar(`!!document.getElementById('ing-correo')`, 'ingreso tras la expiración');
  const t = await ev(`(document.querySelector('.alerta-ingreso')||{}).innerText || ''`); console.log('      mensaje:', t); if (!/sesión|cuenta/i.test(t)) throw new Error('sin explicación');
  revisar(JSON.parse(JSON.stringify(await ev(MEDIR))), 'ingreso tras expirar');
  await c.admin.json('POST', `/usuarios/${(await c.admin.json('GET', '/usuarios')).datos.usuarios.find((x) => x.correo === c.correoCoord).usuarioId}/estado`, { activo: true });   // se reactiva para las pruebas siguientes
});

await paso('Sin excepciones de JavaScript', async () => { if (errores.length) throw new Error(errores.slice(0, 3).join(' | ')); });
console.log(`\nRESUMEN: ${resultados.filter((r) => r[0] === 'OK').length} OK, ${resultados.filter((r) => r[0] === 'FALLO').length} FALLO`);
try { ws.close(); } catch { /* */ }
chrome.kill();
process.exit(resultados.some((r) => r[0] === 'FALLO') ? 1 : 0);
