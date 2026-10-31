# Guía de usuario de la interfaz web de Eventos Nova

La interfaz está hecha con HTML5, CSS3 y JavaScript sin frameworks, y se sirve desde la propia API (FastAPI) en la dirección `/app/`. Todo lo que muestra y ejecuta viene de la API real: ningún dato es de ejemplo.

## 0. Iniciar sesión y roles

Al abrir la aplicación se pide **correo y contraseña**. Las cuentas las crea un administrador en **Cuentas**; el primer administrador se crea con `scripts/crear_administrador.py` (ver `docs/SEGURIDAD_Y_PERMISOS.md`). Según tu rol verás solo las pantallas y botones que te corresponden: **Administración** (pagos, devoluciones, autorizaciones, cuentas), **Coordinación** (eventos, propuestas, contratos, solicitudes y proveedores) y **Proveedor** («Mi proveedor»: sus servicios y su respuesta). Si falta el permiso, el sistema lo indica; ocultar un botón no es la protección, el servidor comprueba cada operación.

- **Cerrar sesión** y **Cambiar contraseña** están en la caja de la sesión (parte inferior del menú). Cambiar la contraseña cierra todas tus sesiones.
- La sesión caduca tras 30 minutos sin actividad (8 horas como máximo); al vencer se vuelve al ingreso con un aviso.
- Tras 5 intentos fallidos seguidos el ingreso se bloquea unos minutos.
- En una instalación con la autenticación desactivada (solo desarrollo) se muestra un aviso y se ven todas las funciones.

## 1. Cómo iniciarla

**Con Docker Compose** (la forma habitual; usa PostgreSQL):

```powershell
docker compose up -d --build
```

Abre **http://127.0.0.1:8000/app/** (el puerto sigue siendo el de la API, 8000; el entorno de pruebas manuales usa **http://127.0.0.1:8001/app/**). No uses `docker compose down -v`: borraría los datos.

**Sin Docker, solo para probar** (los datos viven en memoria y se pierden al detener el servidor):

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir src --port 8010
```

Abre **http://127.0.0.1:8010/app/**. Para comprobar que el servidor responde: `/health`; con base de datos: `/ready`; documentación técnica: `/docs`.

## 2. Qué hace cada módulo

| Módulo (menú) | Para qué sirve |
|---|---|
| **Panel principal** | Indicadores reales: eventos por estado, pagos pendientes o vencidos, solicitudes en trámite, devoluciones pendientes y servicios por confirmar. Cada tarjeta lleva al módulo correspondiente. |
| **Eventos** | Lista de eventos **por rango de fechas del evento** (la API no ofrece otra consulta), con filtro por estado y búsqueda por texto. Aquí se **registra un evento** y se abre su detalle. Si buscas uno por su identificador, escríbelo en «Abrir un evento por su identificador». |
| **Detalle del evento** | El centro de trabajo: ciclo de vida, contratación (propuestas, contrato, política de no reembolso, firma), estado de cuenta (anticipo, saldo, pagos, devoluciones), solicitudes del evento y proveedores. |
| **Solicitudes** | Todas las solicitudes de cambio, servicio adicional y sustitución, con filtros, su estado oficial y las acciones que corresponden a cada estado. |
| **Pagos y devoluciones** | Obligaciones pendientes o vencidas de todos los eventos y las devoluciones por efectuar. Desde aquí se registra un pago o una devolución. |
| **Seguimiento** | Servicios que el proveedor aún no confirma y solicitudes en trámite. |
| **Proveedores** | Consulta lo que un proveedor puede ver de un evento (solo sus servicios asignados). |
| **Sistema y ayuda** | Estado del servicio, enlaces a la documentación técnica y los límites conocidos. |

## 3. Flujo típico de una contratación

1. **Registrar evento** (módulo Eventos). Queda **En gestión**.
2. En el detalle, **Crear propuesta** (servicios, proveedores considerados, costo total y condiciones).
3. **Aceptar propuesta** (versión vigente) y **Preparar contrato**.
4. **Comunicar política de no reembolso** al Cliente y después **Registrar firma del contrato**. La firma solo anota que ocurrió: no es una firma electrónica.
5. Con el contrato firmado aparece el **estado de cuenta**. El **anticipo es un mínimo del 30 %** del costo; puede cubrirse con **varios pagos parciales** que se acumulan (decisión E-3 del equipo, sin aprobación externa). Usa **Registrar pago**: elige la obligación, escribe el importe, la fecha en que el Cliente pagó y la referencia del comprobante. Si dejas marcado «Verificar el pago ahora», queda verificado.
6. Cuando el anticipo queda **Liquidada**, el sistema confirma la contratación por sí mismo y el evento pasa a **En organización**. (El botón «Confirmar la contratación» solo aparece si, con el anticipo liquidado, el contrato sigue Firmado.)
7. Con la contratación confirmada ya se pueden registrar **cambios**, **servicios adicionales** y **sustituciones de proveedor**.

La barra de **avance de la contratación** del detalle muestra qué pasos están completados y cuál sigue.

## 4. Cómo interpretar los estados

Los nombres de los estados son los oficiales de la API; la interfaz solo les añade color y, cuando ayuda, una explicación breve. El color nunca es lo único que indica el estado: siempre va con texto.

- **Verde:** completado o vigente (por ejemplo, *Contratación confirmada*, *Liquidada*, *Verificado*, *En organización*).
- **Ámbar:** en trámite o pendiente (*En gestión*, *Pendiente*, *Pendiente de autorización*…).
- **Rojo:** cerrado sin éxito o con problema (*Vencida*, *Cancelado*, *No procedente*, *Cerrada por falta de pago*…).

Dos estados que suelen confundirse:

- **No procedente:** la solicitud se registró, pero no cumple un requisito (el evento ya inició o está cancelado, faltan menos de cinco días naturales, no hubo alternativa a tiempo).
- **Cerrada por inicio del evento:** la solicitud seguía en trámite, sin confirmarse, cuando el evento inició.

Un **servicio adicional solicitado cuando el evento ya inició** se registra como **No procedente**, con el motivo que informa el sistema. Un **cambio** solicitado después del inicio **se rechaza** (no queda registrado).

## 5. Pagos y plazos

- Los importes se muestran con separador de miles y dos decimales, sin símbolo de moneda: la API no indica la moneda.
- La **fecha límite** y el aviso **«Plazo vencido»** vienen de la API (`plazoVencido`); la interfaz no los recalcula.
- Las fechas se muestran como las guarda el sistema, en la **hora de negocio de la Ciudad de México**, sin conversiones. En los formularios, la fecha y hora se proponen con la hora actual de la Ciudad de México y puedes cambiarlas.
- Un pago se considera registrado **solo después de que el sistema lo confirma**; el aviso verde con el identificador del pago es esa confirmación.
- **No hay cobros en línea**: se anotan pagos que el Cliente ya efectuó.
- Los **plazos en días hábiles** y **naturales** los calcula el sistema (por ejemplo, 24 horas naturales para pagar un servicio adicional; límite del saldo: tres días hábiles antes del evento). La interfaz solo te orienta; si el sistema rechaza una operación por plazo, verás su motivo.

## 6. Formularios, validaciones y mensajes

- Los campos con **\*** son obligatorios. Si falta alguno, el formulario no se envía y marca cada campo con el mensaje «Este campo es obligatorio. Introduce la información para continuar.».
- Los importes aceptan solo números y punto decimal; los pagos y cargos deben ser mayores que cero.
- Las operaciones importantes (pagos, cancelaciones, cierres, aceptación de una propuesta) piden **confirmar** antes de enviarse y muestran un resumen.
- Al enviar, el botón se desactiva («Enviando…») para evitar duplicados.
- Si el sistema **rechaza** la operación por una regla de negocio, el formulario **se queda abierto con tus datos** y muestra el motivo real, por ejemplo: «La propuesta está Aceptada.». Puedes corregir y reintentar, o cancelar.
- Si hay un problema de **conexión**: «No fue posible conectar con el sistema. Comprueba que el servidor esté funcionando e inténtalo nuevamente.» Verifica que el servicio esté encendido (`/health`) y pulsa **Reintentar**.
- Si ocurre un **error del servidor**: «No fue posible completar la operación. No se han confirmado los cambios…». Nada se guardó; revisa los datos e inténtalo de nuevo. El apartado **Detalles** de los errores muestra información útil para el equipo técnico.
- Los avisos verdes confirman lo que el sistema respondió, con su mensaje original.

## 7. Cosas que debes saber (límites de la API)

- **No hay módulo de Clientes como catálogo:** el cliente se identifica con un texto (por ejemplo, `CL-1`). Los proveedores sí tienen catálogo (sección 7.1). La API no ofrece operaciones para registrar, editar ni buscar clientes.
- **No se pueden consultar propuestas ni pagos por identificador.** La interfaz **recuerda en este navegador** las propuestas y los pagos que se crean desde ella, para poder aceptarlas o verificarlos. Esa lista es local: otra persona u otro navegador no la ve (se avisa en pantalla). Con otro navegador puedes escribir el identificador a mano.
- **No hay autenticación ni permisos:** quien llegue a la dirección puede ejecutar cualquier operación. Úsala solo en una red de confianza.
- **Las acciones se habilitan según el estado** del registro. Cuando algo depende de datos que la API no muestra (por ejemplo, si una solicitud ya tiene anexo), el botón aparece y el sistema responde con el motivo si no procede.
- El **inicio del evento** y el **cierre sin contratación** al llegar la fecha los hace el trabajador automático del sistema (en el modo sin Docker no hay trabajador). La pantalla muestra el estado que informa el servidor.

### 7.1 Proveedores: registrar y asignar

1. **Registrar el proveedor.** Menú **Proveedores** → **Registrar proveedor**. Solo el nombre es obligatorio. En «Servicios que ofrece» escribe los servicios separados con comas, con el mismo nombre que tienen en el evento (por ejemplo, `Banquete, Música`; no importan mayúsculas ni acentos). El nombre no puede repetirse. Puedes buscar por texto o por servicio.
2. **Tener el evento En organización** (contratación confirmada). Los proveedores no se asignan antes ni después (BN-009).
3. **Asignar.** En el detalle del evento, tarjeta **Servicios y proveedores**, botón **Asignar proveedor** del servicio «Sin proveedor asignado». La lista muestra solo los proveedores **registrados en el catálogo** que ofrecen ese servicio (no hay proveedores de demostración). Si no hay ninguno, la pantalla explica que debes registrar uno que ofrezca ese servicio.
4. **Confirmación del proveedor.** El servicio queda «Pendiente de confirmación del proveedor». Con **Registrar respuesta del proveedor** se anota si está disponible (queda «Confirmado por el proveedor») o no («Proveedor no disponible», que se resuelve con una sustitución).
5. **Seguimiento** separa los servicios «Sin proveedor asignado» de los «Asignados, pendientes de confirmación». Por omisión oculta (y cuenta) los de eventos cancelados, finalizados o cerrados, porque ya no admiten asignación; un interruptor los muestra.

Límites: el catálogo no guarda tarifas, condiciones ni calendario. Por eso «disponible» significa «registrado y ofrece el servicio», sin revisar la fecha del evento (decisión D-P2 pendiente de aprobación; ver docs/architecture/DECISIONES_PROVEEDORES.md). No hay edición ni baja de proveedores, y la API no permite saber qué eventos tiene un proveedor.

## 8. Dónde ver más

- Correspondencia de cada operación de la API con la interfaz: [`INTERFAZ_WEB_COBERTURA.md`](INTERFAZ_WEB_COBERTURA.md).
- Contrato técnico de la API: `docs/api/openapi.json` y `/docs`.
