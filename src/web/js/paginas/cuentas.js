/* Administración de cuentas (solo el rol administrador; el servidor lo vuelve a comprobar). */
import { GET } from '../api.js';
import { ACCIONES } from '../acciones.js';
import { ETIQUETA_ROL, estado as sesion } from '../sesion.js';
import { fmtFechaHora } from '../negocio.js';
import { aviso, botonAccion, cargarEn, ejecutarAccion, h, insignia, tabla, tarjeta } from '../ui.js';

export function cuentas(contenedor) {
  const salida = h('div');
  const pintar = () => cargarEn(salida, async () => ({ u: (await GET('/usuarios')).datos.usuarios, p: (await GET('/proveedores')).datos.proveedores }), ({ u, p }) => {
    const nombreProveedor = Object.fromEntries(p.map((x) => [x.proveedorId, x.nombre]));
    return tarjeta(`${u.length} cuenta(s)`, tabla([
      { titulo: 'Persona', celda: (x) => h('div', null, x.nombre, h('div', { class: 'peq' }, x.correo)) },
      { titulo: 'Rol', celda: (x) => ETIQUETA_ROL[x.rol] || x.rol },
      { titulo: 'Proveedor', celda: (x) => (x.proveedorId ? (nombreProveedor[x.proveedorId] || x.proveedorId) : '—') },
      { titulo: 'Estado', celda: (x) => insignia(x.activo ? 'Activa' : 'Desactivada') },
      { titulo: 'Último acceso', celda: (x) => (x.ultimoAcceso ? fmtFechaHora(x.ultimoAcceso) : 'Nunca') },
      { titulo: 'Acciones', celda: (x) => h('div', { class: 'acciones' },
        x.usuarioId === (sesion.usuario && sesion.usuario.usuarioId) ? h('span', { class: 'peq' }, 'Tu cuenta')
          : botonAccion(x.activo ? ACCIONES.desactivarCuenta : ACCIONES.activarCuenta, { usuario: x }, pintar, { clase: 'btn btn-peq' }),
        botonAccion(ACCIONES.restablecerContrasena, { usuario: x }, pintar, { clase: 'btn btn-peq' })) },
    ], u, { vacioTitulo: 'No hay cuentas' }));
  });
  contenedor.replaceChildren(
    h('header', { class: 'pagina-cab' }, h('h1', null, 'Cuentas'),
      h('p', null, 'Quién puede entrar a la aplicación y con qué rol. Una cuenta nueva solo recibe los permisos de su rol; las de proveedor se vinculan a un proveedor del catálogo.'),
      h('div', { class: 'acciones' }, h('button', { type: 'button', class: 'btn btn-primario', onclick: async () => {
        let proveedores = [];
        try { proveedores = (await GET('/proveedores')).datos.proveedores; } catch (e) { aviso('error', e.message); return; }
        await ejecutarAccion(ACCIONES.crearCuenta, { proveedores }, pintar);
      } }, 'Crear cuenta'))),
    salida);
  pintar();
}
