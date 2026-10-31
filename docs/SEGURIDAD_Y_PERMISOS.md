# Seguridad: autenticación, roles y permisos

Estado: implementado y probado en el entorno **local de pruebas** con PostgreSQL (29–30/10/2026). **No es una declaración de que el sistema esté listo para Internet**: ver «Pendiente antes de un despliegue público».

La matriz operación por operación (generada del código) está en [`SEGURIDAD_MATRIZ_PERMISOS.md`](SEGURIDAD_MATRIZ_PERMISOS.md).

## 1. Qué existía antes (inspección)
- 63 operaciones de negocio sin ninguna autenticación ni autorización: cualquiera con acceso a la dirección podía ejecutarlas (hallazgo ya documentado en las fases anteriores).
- No existía una entidad Usuario ni cuentas. Los proveedores existen como catálogo (`proveedor`, desde la revisión 0005) pero **sin cuentas de acceso**: no había relación entre una persona autenticada y un proveedor.
- CORS no estaba configurado (la interfaz se sirve del mismo origen), no había cabeceras de seguridad y `/docs` era público.

## 2. Roles
Basados en los interesados del BRD (Coordinador, Proveedor, Administración). **El Cliente no tiene cuenta**: actúa por medio de Coordinación y Administración.

| Rol | Quién es | Resumen de permisos |
|---|---|---|
| `administrador` | Administración | Registrar y verificar pagos, cobranza, devoluciones, autorizar cambios/servicios adicionales/sustituciones, revisión administrativa de cancelaciones, consultas administrativas, catálogo de proveedores (consultar y registrar) y **administrar cuentas**. |
| `coordinador` | Coordinador de Eventos Nova | Registrar eventos, propuestas, contratos, solicitudes (cambio, servicio adicional, sustitución) y su gestión, cancelaciones, ciclo del evento, catálogo de proveedores, asignar proveedor y anotar su respuesta, consultar pagos (solo lectura). |
| `proveedor` | Persona o empresa proveedora | **Solo lo suyo:** su ficha, los servicios que tiene asignados en un evento y su respuesta de disponibilidad. |

Principios aplicados:
- **Mínimo privilegio:** no existe rol por omisión; crear una cuenta exige indicar el rol. Una cuenta de proveedor **debe** vincularse a un proveedor del catálogo y ningún otro rol puede llevar ese vínculo (también lo exige la base de datos con `CHECK`). El administrador **no** recibe los permisos de coordinación (por ejemplo, no registra eventos).
- **Deniega por omisión:** la dependencia de FastAPI busca la ruta en la matriz; si falta, responde 403. Una prueba comprueba que cada ruta de la API está en la matriz y viceversa.
- **El proveedor nunca elige su identidad:** el identificador de proveedor sale de la cuenta autenticada. En las rutas con `{proveedor_id}` se compara con el de la cuenta; en la respuesta del proveedor se compara el del cuerpo con el de la cuenta (HTTP 403 si difiere).

### Decisiones documentadas y decisiones que necesitan aprobación del equipo
| # | Decisión | Fuente | Estado |
|---|---|---|---|
| S-1 | Tres roles: administrador (Administración), coordinador, proveedor; el Cliente sin cuenta | Interesados del BRD | **Sin aprobación formal** (los nombres de rol los propuso el equipo) |
| S-2 | Pagos, verificación y devoluciones: Administración. Autorizaciones: Administración | BRD (responsabilidades de Administración) | Documentada |
| S-3 | Cancelación por falta de regularización: Coordinación («registro formal del Coordinador») | BRD, BN-008 | Documentada |
| S-4 | Coordinación consulta pagos (solo lectura) | BN-007 («información que necesitan») | **Inferida, pendiente de aprobación** |
| S-5 | Coordinación anota la respuesta del proveedor cuando este se la comunica por teléfono o mensaje (el BRD indica que hoy se usa WhatsApp, llamadas y correo) además del propio proveedor | BRD, comunicación actual | **Pendiente de aprobación** |
| S-6 | «Integrar el importe adicional de una sustitución al saldo» (`importe-adicional`) lo ejecuta Administración | Ningún documento nombra al actor | **Pendiente de aprobación** |
| S-7 | Inicio y finalización manual del evento y cierre por falta de pago de solicitudes: Coordinación | Seguimiento de eventos del Coordinador (BRD) | **Pendiente de aprobación** |
| S-8 | El catálogo de proveedores lo registran Coordinación y Administración | D-P1 (`DECISIONES_PROVEEDORES.md`) | **Pendiente de aprobación** |
| S-9 | El administrador puede ver (no crear) lo que consulta Coordinación; no hay «superusuario» | Mínimo privilegio | Decisión de diseño |

## 3. Autenticación y sesiones
- **Credenciales:** correo + contraseña. Hash **Argon2id** (`argon2-cffi`, parámetros recomendados por la biblioteca); nunca se guarda ni se devuelve la contraseña. Política: mínimo 12 caracteres, no igual al correo o nombre ni de un solo carácter repetido.
- **Sesión:** token opaco de 256 bits generado con `secrets`; en la base de datos solo se guarda su **SHA-256** (si se filtrara la tabla no sirve para entrar). Cookie `eventosnova_sesion`: `HttpOnly`, `SameSite=Strict`, `Path=/`, y `Secure` cuando `EVENTOSNOVA_COOKIE_SEGURA=1` (obligatorio en producción). El token no está en el cuerpo de ninguna respuesta ni en `localStorage`.
- **Caducidad:** por inactividad (30 min por omisión) y absoluta (8 h). Cierre de sesión, baja de la cuenta, restablecimiento y cambio de contraseña **invalidan** las sesiones.
- **CSRF:** cada sesión tiene un token CSRF (`X-CSRF-Token`, que devuelve el inicio de sesión y `GET /auth/yo`) exigido en toda operación que modifica datos, más comprobación del encabezado `Origin` y `SameSite=Strict`.
- **Limitación de intentos:** 5 fallos por (correo, IP) y 25 por IP en 15 minutos bloquean el ingreso 15 minutos (HTTP 429 con `Retry-After`); persistido en PostgreSQL (`intento_acceso`), así que sobrevive a reinicios y vale para varias instancias. El mensaje de credenciales incorrectas es el mismo para correo inexistente, contraseña errónea o cuenta desactivada, y se ejecuta una verificación ficticia para igualar el tiempo.
- **Respuestas:** 401 `no_autenticado` (sin sesión), 401 `sesion_expirada` (caducada o cerrada), 403 `sin_permiso`, 429 `demasiados_intentos`. Los mensajes son comprensibles y no revelan detalles internos.

### Primer administrador (sin credenciales predeterminadas)
```powershell
# 1. La base debe estar en la revisión 0006:  python -m alembic upgrade head   (con DATABASE_URL de ESA base)
# 2. Crear el primer administrador (la contraseña se pide por teclado, sin eco; --base es obligatorio):
.\.venv\Scripts\python.exe scripts\crear_administrador.py --base eventosnova_manual_test --correo admin@su-organizacion.example --nombre "Nombre Apellido"
# Para automatizar: --contrasena-desde-entorno NOMBRE_DE_VARIABLE (nunca como argumento de la línea de comandos)
```
El script se niega si ya existe un administrador y solo trabaja con un servidor local. Las demás cuentas las crea un administrador en **Cuentas** (interfaz) o con `POST /usuarios`.

## 4. Endpoints
Todas las operaciones de negocio y de administración de cuentas exigen sesión y permiso (ver matriz). Públicas: `GET /`, `GET /health`, `GET /ready` (no devuelven secretos: solo «ok» y el modo de persistencia) y `POST /auth/inicio-sesion`. Nuevas: `POST /auth/inicio-sesion`, `GET /auth/yo`, `POST /auth/cierre-sesion`, `POST /auth/cambio-contrasena`, `GET|POST /usuarios`, `POST /usuarios/{id}/estado`, `POST /usuarios/{id}/contrasena`.

## 5. Base de datos
Migración **0006** (aditiva): tablas `usuario` (correo único en minúsculas, rol con `CHECK`, vínculo opcional a `proveedor` con clave foránea y `CHECK` de coherencia con el rol), `sesion` (borrado en cascada con la cuenta) e `intento_acceso`. No inserta ninguna cuenta. La bajada (`downgrade`) descarta cuentas y sesiones: hacer copia de seguridad antes.

## 6. Interfaz web
Pantalla de ingreso, caja de sesión (nombre, rol, **Cambiar contraseña**, **Cerrar sesión**), menú y botones por rol, pantalla **Cuentas** (solo administrador), «Mi proveedor» para el rol proveedor, mensajes claros de credenciales, bloqueo, permiso denegado y sesión vencida (vuelve al ingreso). **Ocultar botones es comodidad; la verificación definitiva es la del servidor**, que se probó eludiendo la interfaz. La interfaz no guarda contraseñas ni tokens (solo en memoria el token CSRF).

## 7. Configuración: local frente a producción
| Variable | Local (por omisión) | Producción |
|---|---|---|
| `EVENTOSNOVA_ENTORNO` | `local` | `produccion` |
| `EVENTOSNOVA_AUTENTICACION` | `activa` (se puede poner `desactivada` solo en local) | no se permite desactivar (la aplicación no arranca) |
| `EVENTOSNOVA_COOKIE_SEGURA` | `0` (http://127.0.0.1) | `1` obligatorio (sin él no arranca) |
| `/docs`, `/redoc`, `/openapi.json` | visibles | ocultos (`EVENTOSNOVA_DOCS=1` para mostrarlos) |
| `Strict-Transport-Security` | no | sí |
Cabeceras siempre: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store` en la API y `Content-Security-Policy` estricta para `/app/` (solo recursos propios, sin scripts ni estilos en línea). CORS no está habilitado (la interfaz y la API comparten origen). La fábrica programática `crear_app()` no exige autenticación (es para pruebas); la aplicación que se sirve (`api.main:app`, Docker) sí.

## 8. Pruebas
- `tests/test_seguridad.py` (memoria y PostgreSQL): sin sesión 401 en todas las rutas protegidas, matriz completa, credenciales incorrectas, bloqueo y desbloqueo, cookies, CSRF y Origin, cada rol contra cada operación llamando directo a la API, aislamiento del proveedor, caducidad por inactividad y absoluta, cierre/baja/cambio de contraseña, política de contraseñas, restricciones de PostgreSQL, producción.
- Navegador (Chrome real, PostgreSQL): `scripts/probar_seguridad_navegador.mjs`; recorridos anteriores adaptados a la autenticación: `probar_interfaz_navegador.mjs`, `probar_proveedores_navegador.mjs`.

## 9. Pendiente antes de un despliegue público (no resuelto)
1. **HTTPS real** y proxy inverso configurados; esta fase solo prepara la cookie `Secure` y HSTS, no se probó detrás de HTTPS.
2. **Detrás de un proxy** la IP del cliente es la del proxy: hay que configurar la cabecera de confianza (`X-Forwarded-For`) antes de confiar en la limitación por IP; hoy un atacante detrás de una IP compartida podría bloquear a otros usuarios (límite de 25 por IP).
3. **Recuperación de contraseña por correo, MFA y política de rotación**: no implementadas (el restablecimiento lo hace un administrador).
4. **Registro de auditoría** persistente (quién hizo qué): hay registros de log de accesos y denegaciones, pero no una tabla de auditoría de negocio.
5. **Gestión de secretos y de la base de datos** (contraseñas de PostgreSQL, copias de seguridad cifradas, usuarios de base de datos con privilegios mínimos) y revisión del contenedor.
6. **Aprobación del equipo** de las decisiones S-1 a S-9 y una revisión de seguridad independiente (pruebas de penetración).
7. **Limitación general de peticiones** (solo está limitado el ingreso), tamaños máximos y protección contra denegación de servicio en la capa de red.
8. **Cuentas de proveedor sin listado de sus eventos:** la API no ofrece «mis servicios»; el proveedor consulta con el identificador del evento que le comunica Coordinación.
9. El modo en memoria no es apto con autenticación activa (las cuentas se pierden al reiniciar): usar PostgreSQL.
