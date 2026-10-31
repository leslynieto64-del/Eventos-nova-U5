# Matriz de roles y permisos (generada)

> Documento **generado** por `scripts/generar_matriz_permisos.py` a partir de `src/application/seguridad.py`: es la misma matriz que la API aplica. No editar a mano (la prueba `tests/test_seguridad_documentacion.py` comprueba que está al día). Contexto y decisiones: `docs/SEGURIDAD_Y_PERMISOS.md`.

Leyenda: **✔** permitido · **—** denegado (HTTP 403) · **propio** permitido solo sobre el recurso de la propia cuenta (un proveedor solo accede a su proveedor). Sin sesión toda operación protegida responde HTTP 401. Una ruta que no figura en la matriz se deniega.

## Permisos por rol

| Rol | Permisos |
|---|---|
| administrador | `devoluciones.ejecutar`, `eventos.consultar`, `eventos.revision_administrativa`, `pagos.cobranza`, `pagos.consultar`, `pagos.registrar`, `proveedores.consultar`, `proveedores.registrar`, `solicitudes.autorizar`, `solicitudes.importe_adicional`, `usuarios.administrar` |
| coordinador | `contratos.gestionar`, `eventos.cancelar`, `eventos.ciclo`, `eventos.consultar`, `eventos.registrar`, `pagos.consultar`, `propuestas.gestionar`, `proveedores.asignar`, `proveedores.consultar`, `proveedores.registrar`, `proveedores.responder`, `solicitudes.gestionar`, `solicitudes.registrar` |
| proveedor | `proveedores.propio`, `proveedores.responder` |

## Operaciones públicas (sin sesión)

| Método | Ruta | Motivo |
|---|---|---|
| GET | `/` | Identificación de la aplicación |
| POST | `/auth/inicio-sesion` | Inicio de sesión (valida las credenciales; limitado por intentos) |
| GET | `/health` | Sonda de vida (sin datos sensibles) |
| GET | `/ready` | Sonda de disponibilidad (solo «ok» y el modo de persistencia) |

Además se sirve la interfaz estática en `/app/` (HTML, CSS y JavaScript sin datos de negocio) y, fuera de producción, `/docs`, `/redoc` y `/openapi.json`.

## Eventos

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| GET | `/eventos` | `eventos.consultar` | ✔ | ✔ | — |
| POST | `/eventos` | `eventos.registrar` | — | ✔ | — |
| GET | `/eventos/{evento_id}/administracion` | `eventos.consultar` | ✔ | ✔ | — |
| POST | `/eventos/{evento_id}/cancelacion` | `eventos.cancelar` | — | ✔ | — |
| POST | `/eventos/{evento_id}/cancelacion-por-falta-de-regularizacion` | `eventos.cancelar` | — | ✔ | — |
| POST | `/eventos/{evento_id}/finalizacion` | `eventos.ciclo` | — | ✔ | — |
| POST | `/eventos/{evento_id}/inicio` | `eventos.ciclo` | — | ✔ | — |
| GET | `/eventos/{evento_id}/pagos` | `pagos.consultar` | ✔ | ✔ | — |
| POST | `/eventos/{evento_id}/propuestas` | `propuestas.gestionar` | — | ✔ | — |
| POST | `/eventos/{evento_id}/revision-administrativa` | `eventos.revision_administrativa` | ✔ | — | — |
| GET | `/eventos/{evento_id}/solicitudes-pendientes` | `eventos.consultar` | ✔ | ✔ | — |
| GET | `/servicios-pendientes-confirmacion` | `eventos.consultar` | ✔ | ✔ | — |
| GET | `/solicitudes` | `eventos.consultar` | ✔ | ✔ | — |

## Propuestas

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| POST | `/propuestas/{propuesta_id}/aceptacion` | `propuestas.gestionar` | — | ✔ | — |
| POST | `/propuestas/{propuesta_id}/cierre-por-no-aceptacion` | `propuestas.gestionar` | — | ✔ | — |
| POST | `/propuestas/{propuesta_id}/contrato` | `contratos.gestionar` | — | ✔ | — |
| POST | `/propuestas/{propuesta_id}/versiones` | `propuestas.gestionar` | — | ✔ | — |

## Contratos

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| POST | `/contratos/{contrato_id}/comunicacion-politica-no-reembolso` | `contratos.gestionar` | — | ✔ | — |
| POST | `/contratos/{contrato_id}/confirmacion` | `contratos.gestionar` | — | ✔ | — |
| POST | `/contratos/{contrato_id}/firma` | `contratos.gestionar` | — | ✔ | — |
| POST | `/contratos/{contrato_id}/seguimiento-anticipo` | `contratos.gestionar` | — | ✔ | — |

## Pagos y devoluciones

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| GET | `/devoluciones-pendientes` | `pagos.consultar` | ✔ | ✔ | — |
| POST | `/estados-cuenta/{estado_cuenta_id}/devoluciones/{devolucion_id}/ejecucion` | `devoluciones.ejecutar` | ✔ | — | — |
| POST | `/estados-cuenta/{estado_cuenta_id}/pagos` | `pagos.registrar` | ✔ | — | — |
| POST | `/estados-cuenta/{estado_cuenta_id}/pagos/{pago_id}/verificacion` | `pagos.registrar` | ✔ | — | — |
| POST | `/estados-cuenta/{estado_cuenta_id}/protocolo-cobro` | `pagos.cobranza` | ✔ | — | — |
| POST | `/estados-cuenta/{estado_cuenta_id}/regularizacion` | `pagos.cobranza` | ✔ | — | — |
| POST | `/estados-cuenta/{estado_cuenta_id}/vencimiento-saldo-original` | `pagos.cobranza` | ✔ | — | — |
| GET | `/pagos-pendientes` | `pagos.consultar` | ✔ | ✔ | — |

## Solicitudes de cambio

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| POST | `/solicitudes-cambio` | `solicitudes.registrar` | — | ✔ | — |
| POST | `/solicitudes-cambio/{solicitud_id}/anexo` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-cambio/{solicitud_id}/autorizacion` | `solicitudes.autorizar` | ✔ | — | — |
| POST | `/solicitudes-cambio/{solicitud_id}/cierre-por-falta-de-pago` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-cambio/{solicitud_id}/confirmacion` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-cambio/{solicitud_id}/decision-cliente` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-cambio/{solicitud_id}/solicitud-pago` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-cambio/{solicitud_id}/viabilidad` | `solicitudes.gestionar` | — | ✔ | — |

## Servicios adicionales

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| POST | `/solicitudes-servicio-adicional` | `solicitudes.registrar` | — | ✔ | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/anexo` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/aprobacion-cliente` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/autorizacion` | `solicitudes.autorizar` | ✔ | — | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/cierre-por-falta-de-pago` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/confirmacion` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/decision-espera` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/disponibilidad` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/solicitudes-servicio-adicional/{solicitud_id}/solicitud-pago` | `solicitudes.gestionar` | — | ✔ | — |

## Sustituciones de proveedor

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| POST | `/sustituciones` | `solicitudes.registrar` | — | ✔ | — |
| POST | `/sustituciones/{sustitucion_id}/alternativa` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/sustituciones/{sustitucion_id}/anexo` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/sustituciones/{sustitucion_id}/autorizacion` | `solicitudes.autorizar` | ✔ | — | — |
| POST | `/sustituciones/{sustitucion_id}/confirmacion` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/sustituciones/{sustitucion_id}/decision-cliente` | `solicitudes.gestionar` | — | ✔ | — |
| POST | `/sustituciones/{sustitucion_id}/importe-adicional` | `solicitudes.importe_adicional` | ✔ | — | — |

## Proveedores

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| GET | `/eventos/{evento_id}/servicios/{servicio_contratado_id}/disponibilidad` | `proveedores.asignar` | — | ✔ | — |
| POST | `/eventos/{evento_id}/servicios/{servicio_contratado_id}/proveedor` | `proveedores.asignar` | — | ✔ | — |
| POST | `/eventos/{evento_id}/servicios/{servicio_contratado_id}/respuesta-proveedor` | `proveedores.responder` | — | propio | propio |
| GET | `/proveedores` | `proveedores.consultar` | ✔ | ✔ | — |
| POST | `/proveedores` | `proveedores.registrar` | ✔ | ✔ | — |
| GET | `/proveedores/{proveedor_id}` | `proveedores.consultar` o `proveedores.propio` | propio | propio | propio |
| GET | `/proveedores/{proveedor_id}/eventos/{evento_id}` | `proveedores.consultar` o `proveedores.propio` | propio | propio | propio |

## Sesión y cuentas (administración)

| Método | Ruta | Permiso | Administrador | Coordinador | Proveedor |
|---|---|---|:-:|:-:|:-:|
| POST | `/auth/cambio-contrasena` | sesión | ✔ | ✔ | ✔ |
| POST | `/auth/cierre-sesion` | sesión | ✔ | ✔ | ✔ |
| GET | `/auth/yo` | sesión | ✔ | ✔ | ✔ |
| GET | `/usuarios` | `usuarios.administrar` | ✔ | — | — |
| POST | `/usuarios` | `usuarios.administrar` | ✔ | — | — |
| POST | `/usuarios/{usuario_id}/contrasena` | `usuarios.administrar` | ✔ | — | — |
| POST | `/usuarios/{usuario_id}/estado` | `usuarios.administrar` | ✔ | — | — |

Total de operaciones protegidas: **67**; públicas: **4**.
