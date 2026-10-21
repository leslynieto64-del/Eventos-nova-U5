# Eventos Nova — Diseño arquitectural del sistema

## Datos de identificación

- **Actividad:** Diseño arquitectural del sistema con IA
- **Materia:** Componentes de Lógica de Negocios
- **Unidad:** 3
- **Equipo:** 16
- **Integrantes:**
  - Lesly Adamaris Cotlame Nieto — Matrícula 2226958
  - Christopher Bethancourt Contreras — Matrícula 2226948
  - Francisco Mora Ruiz — Matrícula 2226912

## Empresa

**Eventos Nova** es el caso de negocio para el que se propone un sistema de apoyo a la gestión de eventos, incluyendo propuestas, contratación, pagos, cancelaciones, cambios, servicios adicionales y sustituciones de proveedores.

## Alcance

El proyecto contiene una propuesta arquitectural organizada en las capas de dominio, aplicación e infraestructura, junto con diagramas, decisiones arquitecturales, matriz de trazabilidad, documentación de requisitos y pruebas automatizadas. La infraestructura de referencia utiliza almacenamiento en memoria y simulaciones para los colaboradores externos; no representa una integración de producción con una base de datos ni con servicios externos reales.

## Estructura del proyecto

```text
EVENTOS_NOVA_U3_ARQUITECTURA_CLNEG/
├── Resumen_EventosNova_U3_Equipo16.docx
├── Resumen_Eventos_Nova_Equipo16.pdf
├── validar_paquete_pia.py     (Etapa E1: validación de los CSV oficiales)
├── datos/
│   └── paquete_pia/           (Etapa E1: seis CSV oficiales sin modificar + MANIFIESTO.sha256)
├── diagramas/
│   ├── bpmn/
│   │   ├── BPMN_Eventos_Nova.drawio / .bpmn / .pdf / .svg / .png (maestro con los subprocesos desplegados)
│   │   ├── BPMN_Eventos_Nova_paginado.pdf (versión del maestro para imprimir en A3)
│   │   └── BPMN_Eventos_Nova_SP01 … SP08 (subprocesos) .drawio / .bpmn / .pdf / .svg / .png
│   ├── clases/
│   │   ├── clases_1_dominio.puml / .pdf / .png
│   │   ├── clases_2_aplicacion.puml / .pdf / .png
│   │   └── clases_3_cqrs_infraestructura.puml / .pdf / .png
│   ├── dominio/
│   │   ├── mapa-dominio.drawio
│   │   └── mapa-dominio.pdf
│   └── secuencia/
│       ├── secuencia_1_confirmacion_contratacion.puml / .pdf / .png
│       └── secuencia_2_regularizacion_y_cancelacion.puml / .pdf / .png
├── docs/
│   ├── ADR/
│   │   ├── ADR_Eventos_Nova.docx
│   │   └── ADR_Eventos_Nova.pdf
│   ├── bitacora ia/
│   │   ├── Bitacora_IA_Eventos_Nova.docx
│   │   └── Bitacora_IA_Eventos_Nova.pdf
│   ├── informe/
│   │   ├── informe-arquitectura-eventos-nova.docx
│   │   └── informe-arquitectura-eventos-nova.pdf
│   ├── trazabilidad/
│   │   ├── matriz-trazabilidad.xlsx
│   │   └── matriz-trazabilidad.pdf
│   └── unidad 2/
│       ├── Glosario_Corregido.docx / .pdf
│       ├── Reporte_BRD_Corregido.docx / .pdf
│       └── User_Stories_corregido.docx / .pdf
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py            (raíz de composición de la API: GET /, GET /health y rutas de CU-01)
│   │   ├── dependencias.py    (obtención sustituible de servicios y reloj)
│   │   ├── esquemas.py        (esquemas de entrada y respuesta, conversión a objetos del dominio)
│   │   ├── errores.py         (rechazos de negocio → HTTP 422)
│   │   └── rutas_propuestas.py (POST /eventos y POST /eventos/{evento_id}/propuestas)
│   ├── application/
│   │   ├── cqrs.py
│   │   ├── puertos.py
│   │   ├── reacciones.py
│   │   ├── resultados.py
│   │   └── servicios.py
│   ├── paquete_pia/           (Etapa E1: lector y DTO de los CSV, independiente de las demás capas)
│   ├── domain/
│   │   ├── base.py
│   │   ├── contrato.py
│   │   ├── especificacion.py      (Etapa E2: base Specification y combinadores)
│   │   ├── especificaciones.py    (Etapa E2: especificaciones de negocio)
│   │   ├── maquina_estados.py     (Etapa E3A: State Machine declarativa; Evento en E3A, Contrato en E3B, SustitucionProveedor en E3C)
│   │   ├── estado_cuenta.py
│   │   ├── evento.py
│   │   ├── eventos_dominio.py
│   │   ├── propuesta.py
│   │   ├── servicios_dominio.py
│   │   ├── solicitudes.py
│   │   └── valores.py
│   └── infrastructure/
│       ├── adaptadores.py
│       ├── composicion.py
│       ├── repositorios_memoria.py
│       └── unidad_trabajo.py
├── tests/
│   ├── evidencias/
│   │   ├── ejecucion-pruebas.txt
│   │   ├── evidencia-pruebas.docx
│   │   └── evidencia-pruebas.pdf
│   ├── test_api_esquemas.py
│   ├── test_api_etapa1.py
│   ├── test_api_propuestas.py
│   ├── test_coherencia_diagramas.py
│   ├── test_correcciones_etapas_3_a_7.py
│   ├── test_decisiones_stakeholder.py
│   ├── test_etapa9_casos_de_uso.py
│   ├── test_etapa9_transacciones_y_reacciones.py
│   └── test_reglas_corregidas.py
├── requirements.txt
└── README.md
```

## Instrucciones de ejecución

Se requiere Python 3 (3.13 para la API). Desde la Etapa 1, la suite incluye `tests/test_api_etapa1.py`, que necesita las dependencias de `requirements.txt`; instálalas primero (ver la sección *Etapa 1*). Abre una terminal en la carpeta raíz del proyecto y ejecuta:

```bash
py -m unittest discover -s tests -v
```

Si el comando `py` no está disponible, utiliza:

```bash
python -m unittest discover -s tests -v
```

El registro de evidencias incluido reporta **91 pruebas aprobadas**. Para verificar el resultado de una ejecución actual, ejecuta nuevamente el comando y revisa el resumen de la terminal.

## Etapa 1 de desarrollo funcional: API con FastAPI

Se agregó la capa de presentación HTTP en `src/api/`. En esta etapa la API solo expone dos rutas:

| Ruta | Respuesta |
|------|-----------|
| `GET /` | Identifica la aplicación Eventos Nova (nombre, descripción, versión y enlaces a `/docs` y `/health`). |
| `GET /health` | `{"estado": "ok", "aplicacion": "Eventos Nova", "version": "0.1.0"}` para verificar que la API está disponible. |

Las capas `domain`, `application` e `infrastructure` no se modificaron y no dependen de FastAPI. Todavía no se exponen casos de uso, persistencia en base de datos ni autenticación; se incorporarán en etapas posteriores.

### Comandos en Windows (PowerShell o CMD, desde la raíz del proyecto)

Requiere Python 3.13. Crear y activar un entorno virtual e instalar las dependencias:

```bat
py -3.13 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> En PowerShell, si la activación está bloqueada, ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` o usa CMD.

Ejecutar todas las pruebas (las existentes y las de la API):

```bat
python -m unittest discover -s tests -v
```

Arrancar la API:

```bat
python -m uvicorn api.main:app --app-dir src --reload
```

Luego abre <http://127.0.0.1:8000/>, <http://127.0.0.1:8000/health> o la documentación interactiva en <http://127.0.0.1:8000/docs>. Detén el servidor con `Ctrl+C`.

## Etapa 3A: primera integración de casos de uso (CU-01)

La API expone dos casos de uso existentes de `GestionPropuestaService`, sin reglas nuevas:

| Ruta | Servicio | Respuesta correcta |
|------|----------|--------------------|
| `POST /eventos` | `registrar_evento(cliente_id, DatosEvento, servicios)` | `201` con `evento_id` y mensaje |
| `POST /eventos/{evento_id}/propuestas` | `crear_propuesta(evento_id, ContenidoPropuesta, ahora)` | `201` con `propuesta_id`, `evento_id` y mensaje |

> **Datos temporales.** Mientras la API use la composición en memoria (`infrastructure.composicion.construir`), los eventos y propuestas solo existen mientras el servidor está en marcha: **se pierden al detenerlo o reiniciarlo** (también con cada recarga de `--reload`). Es una implementación provisional para desarrollo y pruebas; la persistencia se incorporará cuando se reciba la base de datos oficial del proyecto.

**Diseño**

- Las rutas obtienen el servicio con `Depends(obtener_servicio_propuestas)`; no crean repositorios ni importan la infraestructura. `crear_app(fabrica_contenedor)` recibe la fábrica de servicios (por omisión, la composición en memoria) y cada instancia tiene su propio contenedor.
- Los esquemas (`src/api/esquemas.py`) validan solo la forma de la petición: campos obligatorios, tipos y ningún campo desconocido. Las reglas (datos completos del evento, CA-003; contenido de la propuesta, CA-005; importe no negativo) las aplica el dominio al construir `DatosEvento`, `ContenidoPropuesta` e `Importe`.
- `fecha_hora` se envía sin zona horaria (`2026-11-20T18:00:00`), igual que las fechas del dominio; una fecha con zona se rechaza. La fecha de la versión de la propuesta (`ahora`) la asigna el servidor.
- Respuestas de error:
  - `422` con `{"tipo": "rechazo_de_negocio", "detalle": ..., "pendientes": [...]}`: rechazo del servicio o del dominio, con su motivo original.
  - `422` con `{"detail": [...]}`: petición mal formada (validación de FastAPI).
  - `500`: falla técnica; no se convierte en rechazo de negocio.

**Prueba manual en Windows** (con el servidor en marcha, en PowerShell):

```powershell
$evento = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/eventos -ContentType "application/json" -Body '{"cliente_id":"CL-1","datos":{"tipo":"Boda","fecha_hora":"2026-11-20T18:00:00","lugar":"Salon","invitados_aproximados":100},"servicios":["Banquete"]}'
$evento
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/eventos/$($evento.evento_id)/propuestas" -ContentType "application/json" -Body '{"servicios":["Banquete"],"proveedores_considerados":["PV-1"],"costo_total":"10000.00","condiciones":"Condiciones generales"}'
```

También pueden probarse desde la documentación interactiva en <http://127.0.0.1:8000/docs>.

## Etapa E1: lector y validación de los CSV oficiales (paquete 16_Eventos_Nova)

Se incorporaron los seis CSV del paquete oficial proporcionado por el ingeniero como **datos de entrada reproducibles**, junto con un lector que valida su estructura e integridad. En esta etapa **no** hay base de datos, tablas ni conexión de los CSV con los agregados del dominio, y **no** se implementan las reglas ilustrativas del paquete (`puede_procesarse`, `beneficio_referencia`). Las capas `domain`, `application`, `infrastructure` y `api` no se modificaron.

| Ruta | Contenido |
|------|-----------|
| `datos/paquete_pia/*.csv` | Los seis CSV originales (`01_Alumno/datos` de `16_Eventos_Nova.zip`), copiados byte a byte: UTF-8 con BOM y saltos de línea CRLF. **No deben editarse.** |
| `datos/paquete_pia/MANIFIESTO.sha256` | SHA-256 de cada CSV (formato compatible con `sha256sum -c`). |
| `.gitattributes` | Indica a Git que no convierta los saltos de línea de esos archivos (con `core.autocrlf` el hash dejaría de coincidir). |
| `src/paquete_pia/` | Lector independiente: solo usa la biblioteca estándar; no importa el dominio, la aplicación, la API ni librerías de persistencia. |
| `validar_paquete_pia.py` | Atajo de línea de comandos desde la raíz del proyecto. |
| `tests/test_paquete_pia_lector.py`, `tests/test_paquete_pia_integridad.py`, `tests/apoyo_paquete_pia.py` | Pruebas del lector (no requieren FastAPI ni base de datos). |

**Qué valida el lector** (`paquete_pia.leer_paquete()`), reuniendo todos los problemas antes de rechazar:

1. **Integridad:** cada CSV coincide con `MANIFIESTO.sha256`; el manifiesto incluye exactamente los seis archivos. Si algo no coincide, el paquete se rechaza sin leer los datos.
2. **Lectura:** codificación `utf-8-sig` (UTF-8 con BOM) y `newline=''`, de modo que el módulo `csv` maneja CRLF; los archivos se abren solo para lectura.
3. **Estructura:** encabezados exactos y en orden, número de columnas por fila, filas vacías y número de registros: actores 40, catálogo 20, operaciones 60, detalle 117, casos de prueba 120, transiciones 20.
4. **Claves y unicidad:** `actor_id`, `recurso_id`, `operacion_id`, `caso_id` y la clave compuesta (`operacion_id`, `recurso_id`) del detalle; `referencia` de operaciones única.
5. **Referencias:** operaciones → actores; detalle → operaciones y catálogo; casos y transiciones → operaciones; el `estado_inicial` de cada transición coincide con el de su operación.
6. **Formatos:** identificadores con el patrón del paquete (`EVE-C001`, `EVE-P001`, `EVE-O001`, `EVE-T/B001`, `EVE-S001`); booleanos solo `0`/`1`; importes `1234.56` convertidos a `Decimal` (nunca `float`); enteros sin signo (cantidad mayor que cero); fechas ISO `AAAA-MM-DD` existentes; estados dentro del vocabulario que declara el LEEME del paquete (no son los estados del dominio); textos obligatorios sin espacios sobrantes.

El lector devuelve DTO inmutables (`Actor`, `RecursoCatalogo`, `Operacion`, `DetalleOperacion`, `CasoPrueba`, `TransicionPrueba`) con los valores tal como vienen; no aplica reglas de negocio ni calcula resultados esperados. `resultado_alumno` se conserva como texto (es una columna de salida del paquete).

### Comandos en Windows (desde la raíz del proyecto, con el entorno virtual activado)

```bat
REM 1. Validar el paquete (integridad + estructura). Código de salida 0 si es válido, 1 si se rechaza.
python validar_paquete_pia.py

REM 2. Solo las pruebas nuevas de la Etapa E1 (no requieren FastAPI)
python -m unittest tests.test_paquete_pia_lector tests.test_paquete_pia_integridad -v

REM 3. Toda la suite: las 134 pruebas existentes más las de E1
python -m unittest discover -s tests -v

REM 4. (Opcional) Ver el manifiesto calculado; no escribe ningún archivo
python validar_paquete_pia.py hashes
```

Comprobación manual de un hash en PowerShell (debe coincidir con la línea del manifiesto):

```powershell
(Get-FileHash datos\paquete_pia\actores.csv -Algorithm SHA256).Hash.ToLower()
Get-Content datos\paquete_pia\MANIFIESTO.sha256
```

> Si los CSV ya se habían agregado a Git **antes** de existir `.gitattributes`, revisa que no se hayan convertido a LF: `python validar_paquete_pia.py` lo detecta como «archivo alterado». En ese caso vuelve a copiar los originales del zip.

## Etapa E2: patrón Specification

Las condiciones de negocio que antes estaban escritas como `if` dentro de los métodos ahora son **especificaciones** reutilizables del dominio. Los métodos públicos, los estados, los mensajes, las listas de pendientes y la idempotencia no cambian; solo cambia *cómo* se evalúa cada condición. No se agregaron reglas, endpoints ni cambios de persistencia.

| Archivo | Contenido |
|---------|-----------|
| `src/domain/especificacion.py` | Base `Especificacion` y combinadores `Y` (AND), `O` (OR), `No` (NOT) y `ConMotivo`. Sin dependencias externas. |
| `src/domain/especificaciones.py` | Especificaciones de negocio de Eventos Nova (una sola definición por condición) y los candidatos que evalúan. |

**Cómo se usa.** Una especificación responde `es_satisfecha_por(candidato)`. Se combinan con `&` / `y()`, `|` / `o()` y `~` / `no()`. Cuando no se cumple, `motivos_incumplimiento(candidato)` devuelve todos los motivos en el orden de composición (listas de pendientes) y `primer_motivo(candidato)` el primero (rechazos con un solo motivo). `con_motivo(texto)` asigna un motivo propio a una combinación.

```python
CONTRATACION_CONFIRMABLE = ContratoEstaFirmado() & PoliticaNoReembolsoComunicada() & AnticipoVerificado()
pendientes = CONTRATACION_CONFIRMABLE.motivos_incumplimiento(SituacionContratacion(contrato, evidencia))
```

| Especificación | Regla | Dónde se usa |
|----------------|-------|--------------|
| `CONTRATACION_CONFIRMABLE` = firmado **Y** política comunicada **Y** anticipo verificado | BN-009, CA-019 | `Contrato.confirmar_contratacion` (lista de pendientes) |
| `CAMBIO_REQUIERE_APROBACION_CLIENTE` = afecta costos **O** condiciones | BN-003 (ruta B) | `SolicitudCambio.registrar_viabilidad` |
| `MODIFICACION_CON_IMPACTO` = servicios **O** costos **O** condiciones | SE-001 (sustitución) | `ImpactoModificacion.tiene_impacto`, usado por `SustitucionProveedor` |
| `CAMBIO_CON_CARGO_TARDIO` = **NO** anticipación mínima de 7 días | BN-003, CA-061, CA-062 | `SolicitudCambio.aplica_cargo_tardio` (solo el cargo; la viabilidad se evalúa siempre) |
| `SERVICIO_ADICIONAL_EN_PLAZO` = evento no iniciado **Y** (elegibilidad obtenida **O** 5 días naturales) | SE-004, CA-077, CA-080, CA-083 | `SolicitudServicioAdicional.condicion_temporal` |
| `SOLICITUD_CAMBIO_EN_PLAZO` = evento no iniciado | CA-039 | `SolicitudCambio.condicion_temporal` |
| `SOLICITUD_PUEDE_CONTINUAR` = evento no cancelado **Y** condición temporal **Y** sin saldo vencido | O-01, SE-006, BN-005 | `EvaluarRegularizacionDeSolicitudes.evaluar` (primer motivo; solo el saldo detiene) |

**Pruebas de la etapa** (64): `tests/test_especificacion_combinadores.py`, `tests/test_especificaciones_negocio.py` y `tests/test_especificaciones_conservacion.py`. La última compara el comportamiento actual con `tests/referencias/comportamiento_reglas_v8_e1.json`, capturado con el código de v8 + E1 antes del cambio (169 combinaciones de entradas).

```bat
python -m unittest tests.test_especificacion_combinadores tests.test_especificaciones_negocio tests.test_especificaciones_conservacion -v
python -m unittest discover -s tests -v
```

## Etapa E3A: State Machine explícita de Evento

Las transiciones de estado del agregado `Evento` se validan ahora con una máquina de estados declarativa. Los estados, las acciones, las precondiciones, los mensajes, los Domain Events y la idempotencia son los mismos de v8; solo cambia *dónde* se decide si un par estado-acción está permitido. Los estados ilustrativos del paquete CSV (COTIZADO, CONTRATADO, EN_PREPARACION, REALIZADO) no forman parte del dominio. Propuesta, Contrato y las solicitudes todavía no usan la máquina.

| Archivo | Contenido |
|---------|-----------|
| `src/domain/maquina_estados.py` | `MaquinaEstados` genérica: tabla (estado de origen, acción) → destino, repeticiones idempotentes y mensajes de rechazo; `TransicionNoPermitida` es un `ErrorDominio`. |
| `src/domain/evento.py` | `AccionEvento`, la tabla `MAQUINA_EVENTO` y su uso en los métodos del agregado. |

**Tabla de Evento** (GL-033 del mapa de dominio):

| Origen | Acción | Destino | Método de Evento |
|--------|--------|---------|------------------|
| En gestión | `confirmar_contratacion` | En organización | `confirmar_contratacion` (reacción a ContratacionConfirmada) |
| En gestión | `cerrar_sin_contratacion` | Cerrado sin contratación | `cerrar_sin_contratacion` (reacción a ProcesoContratacionCerrado; nunca Cancelado, CA-021) |
| En organización | `cancelar` | Cancelado | `solicitar_cancelacion` y `cancelar_por_falta_de_regularizacion` (BN-008, CA-087, CA-027) |
| En organización | `iniciar` | En ejecución | `iniciar` |
| En ejecución | `finalizar` | Finalizado | `finalizar` (CA-094, CA-095) |

Repeticiones idempotentes (aceptadas sin efecto): `confirmar_contratacion` en En organización y `cerrar_sin_contratacion` en Cerrado sin contratación. Estados terminales: Finalizado, Cancelado y Cerrado sin contratación.

**Cómo se usa.** Cada método de Evento pide a la máquina el destino (`MAQUINA_EVENTO.transitar(estado, acción)`) y lo asigna; si el par no está en la tabla, la máquina lanza el mismo mensaje que el agregado ya usaba. Las precondiciones de negocio siguen en el agregado y se evalúan antes que la máquina: contratación confirmada (CA-084), rechazo registrado si el evento ya inició (CA-088), verificación de Administración y motivo del Coordinador (BN-005, CA-027), e idempotencia de la cancelación por falta de regularización según su origen. Las Specifications de E2 no cambian.

**Corrección E3A-01 (aprobada en la revisión).** `solicitar_cancelacion` valida con la máquina que la cancelación está permitida *antes* de registrar la solicitud como «Procedente». En v8 la solicitud se agregaba primero, y si el Evento estaba En gestión, Finalizado, Cerrado sin contratación o Cancelado el rechazo dejaba esa solicitud dentro del agregado (el servicio revertía la transacción, por lo que nunca se persistió). Ahora el rechazo conserva el mensaje y no modifica el agregado. Se mantienen CA-084 (se rechaza antes de registrar nada), CA-088 (En ejecución: solicitud Rechazada por inicio del evento, sin EventoCancelado) y la cancelación válida desde En organización con un único EventoCancelado. No se modificaron servicios ni repositorios.

**Pruebas de la etapa** (48): `tests/test_maquina_estados.py` y `tests/test_evento_maquina_estados.py`. Comparan el comportamiento con `tests/referencias/comportamiento_evento_v8_e2.json`, capturado con v8 + E1 + E2 antes del cambio (70 combinaciones de estado × acción × precondiciones): 65 deben ser idénticas y las 5 de E3A-01 solo pueden diferir en que ya no queda la solicitud «Procedente».

```bat
python -m unittest tests.test_maquina_estados tests.test_evento_maquina_estados -v
python -m unittest discover -s tests -v
```

## Etapa E3B: State Machine explícita de Contrato

`Contrato` valida ahora sus cambios de estado con la misma `MaquinaEstados` de E3A (sin modificarla). Los estados, los mensajes, los plazos, los Domain Events y la idempotencia son los mismos; la Specification `CONTRATACION_CONFIRMABLE` de E2 no cambia. Servicios, reacciones, API, repositorios, Outbox, diagramas y CSV no se modificaron.

**Tabla de Contrato** (mapa de dominio U3, «Estados de Contrato»):

| Origen | Acción | Destino | Domain Event | Fuente |
|--------|--------|---------|--------------|--------|
| En preparación | `firmar` | Firmado | ContratoFirmado | US-008, CA-017, BN-009 |
| Firmado | `confirmar_contratacion` | Contratación confirmada | ContratacionConfirmada | CA-019, CA-016, GL-009, BN-009, SE-010 |
| Firmado | `cerrar_sin_confirmar` | Cerrado sin confirmar | ProcesoContratacionCerrado | CA-020, CA-021, SE-010, BN-009, GL-011 |

Repetición idempotente declarada en la máquina: `confirmar_contratacion` en Contratación confirmada devuelve `[]`, no cambia el estado y no emite un segundo `ContratacionConfirmada`. Estados terminales: Contratación confirmada y Cerrado sin confirmar.

**Cómo se usa.**
- `firmar`: la máquina valida y da el destino («Solo un contrato En preparación puede firmarse.» si no procede).
- `confirmar_contratacion`: (1) si la máquina declara la repetición, devuelve `[]` sin evaluar nada; (2) la Specification de E2 calcula los pendientes y, si los hay, se devuelven sin excepción ni cambios (también desde En preparación o Cerrado sin confirmar); (3) sin pendientes, la máquina da el destino y se registra un único Domain Event.
- `cerrar_sin_confirmar`: todas las validaciones ocurren antes de modificar el agregado y en el orden de siempre: estado (máquina) y seguimiento con el mismo mensaje («Debe existir un seguimiento del anticipo antes de cerrar la contratación (CA-020).»); 24 horas naturales desde el contacto; anticipo efectuado dentro del plazo.
- `registrar_seguimiento_anticipo`, `registrar_anexo` y `registrar_comunicacion_politica` no cambian el estado: quedan fuera de la tabla con sus validaciones actuales.

**Asuntos registrados para revisión posterior** (no se modifican en E3B):

| ID | Asunto |
|----|--------|
| AR-01 | `registrar_comunicacion_politica` no valida el estado del contrato; CA-016 y GL-055 indican que la política se comunica «antes de confirmar la contratación». |
| AR-02 | `EstadoPropuesta.EN_ELABORACION` aparece en BN-009 («desde su elaboración y revisión por el Cliente») y en el mapa de dominio, pero el código no lo asigna: la propuesta nace En revisión del Cliente. |
| AR-03 | Se admiten varios seguimientos del anticipo; las 24 horas naturales se cuentan desde el primero. Las fuentes hablan de «ese contacto» sin precisar el caso de varios contactos. |
| AR-04 | Al confirmar desde Cerrado sin confirmar, el primer pendiente es «contrato firmado» aunque el contrato sí se firmó. |

**Pruebas de la etapa** (40): `tests/test_contrato_maquina_estados.py`. Comparan el comportamiento con `tests/referencias/comportamiento_contrato_v8_e3a.json`, capturado con `tests/apoyo_maquina_estados_contrato.py` sobre el código anterior a E3B (336 combinaciones de estado × política × seguimiento × método y parámetros), que deben ser idénticas.

```bat
python -m unittest tests.test_contrato_maquina_estados -v
python -m unittest discover -s tests -v
```

## Etapa E3C: State Machine explícita de SustitucionProveedor

`SustitucionProveedor` (en `src/domain/solicitudes.py`) valida ahora sus cambios de estado con la `MaquinaEstados` de E3A, sin modificarla. Todo el cambio está dentro de la clase: `SustitucionProveedor.Accion` y `SustitucionProveedor.MAQUINA`. `_SolicitudBase`, `SolicitudCambio`, `SolicitudServicioAdicional`, las Specifications de E2, Evento, Contrato, servicios, reacciones, API, repositorios, Outbox, diagramas y CSV no se modificaron. Las firmas públicas, los estados, los mensajes, los faltantes y los Domain Events son los mismos.

**Tabla de SustitucionProveedor** (mapa de dominio U3, página «03 — Detalle B», «Estados de SustitucionProveedor · SE-001, CA-046–CA-054, CA-096»):

| Origen | Método (acción interna) | Destino | Domain Event | Fuente |
|--------|-------------------------|---------|--------------|--------|
| En búsqueda de alternativa | `proponer_alternativa`, con impacto (`PROPONER_ALTERNATIVA_CON_IMPACTO`) | Pendiente de aprobación del Cliente | — | CA-049, SE-001 |
| En búsqueda de alternativa | `proponer_alternativa`, sin impacto (`PROPONER_ALTERNATIVA_SIN_IMPACTO`) | Pendiente de formalización | — | CA-053 |
| Pendiente de aprobación del Cliente | `registrar_decision_cliente`, aprobada (`APROBACION_CLIENTE`) | Pendiente de autorización | — | CA-049 |
| Pendiente de aprobación del Cliente | `registrar_decision_cliente`, rechazada (`RECHAZO_CLIENTE`) | En búsqueda de alternativa | AlternativaRechazadaPorCliente | CA-054 |
| Pendiente de autorización | `registrar_autorizacion`, aprobada (`AUTORIZACION_ADMINISTRACION`) | Pendiente de formalización | — | CA-051, CA-052 |
| Pendiente de autorización | `registrar_autorizacion`, rechazada (`RECHAZO_ADMINISTRACION`) | En búsqueda de alternativa | AlternativaNoAutorizadaPorAdministracion | CA-050 |
| Pendiente de formalización | `confirmar` (`CONFIRMAR`) | Confirmada | SustitucionProveedorConfirmada | CA-051, CA-052, CA-053 |
| Cualquiera de los 4 estados en trámite | `cerrar_por_inicio_evento` | Cerrada por inicio del evento | SustitucionProveedorCerradaPorInicioEvento | CA-096 |
| Cualquiera de los 4 estados en trámite | `cerrar_por_cancelacion_evento` | Cerrada por evento cancelado | — (sin Domain Event, como antes) | BN-008 |

Estados terminales: Confirmada, Cerrada por inicio del evento y Cerrada por evento cancelado (iguales a `FINALES`). No hay repeticiones idempotentes.

**Cómo se usa.**
- Los métodos con dos resultados (`proponer_alternativa`, `registrar_decision_cliente`, `registrar_autorizacion`) eligen la acción interna a partir del resultado que ya calculaba el código (`ImpactoModificacion.tiene_impacto` o `Decision.aprobada`), validan con la máquina **antes** de modificar el agregado y asignan el destino. Los mensajes de rechazo no cambian.
- `confirmar` conserva su lista de faltantes y sus mensajes; la máquina solo se consulta cuando no falta ningún requisito.
- Los cierres en estados finales siguen resolviéndose con `pendiente` y no tienen efecto. `cerrar_por_cancelacion_evento` se sobrescribe solo en `SustitucionProveedor`: valida con la máquina y delega en `_SolicitudBase`, que conserva el resultado (`True`/`False`) y no emite Domain Event.

**Specifications de E2 que usa SustitucionProveedor.** Solo `MODIFICACION_CON_IMPACTO` (servicios **O** costos **O** condiciones), a través de `ImpactoModificacion.tiene_impacto`, para decidir en `proponer_alternativa` si la alternativa requiere la aprobación del Cliente y la autorización de Administración (SE-001, CA-049) o pasa directamente a formalización (CA-053). El impacto lo calcula antes el Domain Service `EvaluarImpactoCambio` (no es una Specification), en `GestionSustitucionProveedorService.buscar_alternativa_sustitucion`. La sustitución no usa `CAMBIO_REQUIERE_APROBACION_CLIENTE`, `CAMBIO_CON_CARGO_TARDIO`, `SERVICIO_ADICIONAL_EN_PLAZO`, `SOLICITUD_CAMBIO_EN_PLAZO`, `SOLICITUD_PUEDE_CONTINUAR` ni `CONTRATACION_CONFIRMABLE`.

**Asuntos registrados para revisión posterior** (se suman a AR-01 a AR-04 de E3B; no se modifican en E3C):

| ID | Asunto |
|----|--------|
| AR-05 | `EstadoSolicitudCambio.EN_EVALUACION`: el mapa de dominio dibuja Registrada → En evaluación → No procedente / Pendiente de aprobación del Cliente / Pendiente de formalización; el código solo lo menciona en la comprobación de `registrar_viabilidad` y pasa de Registrada directamente al resultado. |
| AR-06 | `SolicitudServicioAdicional`: el mapa dibuja Registrada → En búsqueda de proveedor → Pendiente de aprobación del Cliente; el código pasa de Registrada directamente a Pendiente de aprobación del Cliente cuando el proveedor está disponible (y a En búsqueda de proveedor cuando no lo está). |

**Pruebas de la etapa** (32): `tests/test_sustitucion_maquina_estados.py`. Comparan el comportamiento con `tests/referencias/comportamiento_sustitucion_v8_e3b.json`, capturado con `tests/apoyo_maquina_estados_sustitucion.py` sobre el código anterior a E3C: 209 combinaciones de SustitucionProveedor (sus 7 estados con variantes de alternativa, costo, límite y anexo × cada método y parámetros) y 58 cierres de SolicitudCambio y SolicitudServicioAdicional en todos sus estados, que deben ser idénticos.

```bat
python -m unittest tests.test_sustitucion_maquina_estados -v
python -m unittest discover -s tests -v
```

## Corrección documental previa a E3D (AR-07 y AR-08)

Antes de planificar E3D se revisaron las fuentes del dominio financiero. Esta corrección es solo documental: no cambia código, pruebas, diagramas, CSV ni manifiestos. El plan de la etapa está en [`docs/planificacion/Plan_E3D_Final.docx`](docs/planificacion/Plan_E3D_Final.docx).

**Asuntos registrados** (se suman a AR-01 a AR-06; esos siguen pendientes y no se modifican):

| ID | Asunto | Estado |
|----|--------|--------|
| AR-07 | CA-097 condicionaba que los cobros pendientes exclusivos de una solicitud cerrada sin realizarse quedaran sin efecto a que el Evento no estuviera cancelado. SE-012, BN-008, GL-053, el mapa de dominio, el BPMN SP-08 y el código (`EstadoCuenta.aplicar_cierre_sin_realizar`) los dejan sin efecto en ambos casos y reservan la condición «Evento no cancelado» para la devolución. Se conservó SE-012 y se alinearon con ella CA-097, CA-070 y CA-071 (User Stories), GL-032 (Glosario y su copia en el informe de arquitectura), la restricción del negocio del BRD y las celdas B15 y B24 de la matriz de trazabilidad. Los ID, las demás condiciones y la política de no reembolso no cambian. | Resuelto (documental) |
| AR-08 | `EstadoCuenta.registrar_devolucion_efectuada` y `EstadoCuentaService.registrar_y_ejecutar_devolucion` buscan la devolución con `next(...)` sin valor por omisión: con un `devolucion_id` inexistente se lanza `StopIteration` en lugar de un rechazo de negocio (`ErrorDominio`). | Pendiente; no se corrige en E3D |

## Etapa E3D: State Machines explícitas de EstadoCuenta

`EstadoCuenta` (en `src/domain/estado_cuenta.py`) valida ahora con la `MaquinaEstados` de E3A, sin modificarla, los cambios de estado de sus tres entidades: `ObligacionPago`, `Pago` y `Devolucion`. Las acciones internas y las tablas están a nivel de módulo, como en Evento y Contrato: `AccionObligacionPago`/`MAQUINA_OBLIGACION_PAGO`, `AccionPago`/`MAQUINA_PAGO` y `AccionDevolucion`/`MAQUINA_DEVOLUCION`. Plan aprobado: [`docs/planificacion/Plan_E3D_Final.docx`](docs/planificacion/Plan_E3D_Final.docx) (decisiones D-E3D-1 a D-E3D-5).

No se modificaron la máquina genérica, las Specifications de E2, Evento, Contrato, las solicitudes, `valores.py`, `eventos_dominio.py`, servicios, reacciones, API, repositorios, Outbox, UoW, diagramas ni CSV. Las firmas públicas, los estados, las reglas, los plazos, los importes, los mensajes y los Domain Events son los mismos.

**Tablas** (mapa de dominio U3, página «04 — Detalle C: Gestión financiera»):

| Entidad | Origen | Acción interna | Destino | Método | Domain Event | Fuente |
|---------|--------|----------------|---------|--------|--------------|--------|
| ObligacionPago | Pendiente | `LIQUIDAR_POR_PAGO` | Liquidada | verificación de un pago | PagoVerificado (del pago) | CA-018, CA-019, CA-026 |
| ObligacionPago | Pendiente | `VENCER` | Vencida | `registrar_vencimiento_saldo` | SaldoContratoOriginalVencido (uno por llamada) | CA-023, CA-025, BN-005 |
| ObligacionPago | Vencida | `REGULARIZAR` | Liquidada | `resolver_regularizacion` (saldo) | SaldoVencidoRegularizado | CA-027 |
| ObligacionPago | Pendiente | `REGULARIZAR` | Liquidada | `resolver_regularizacion` (cargos moratorios) | el mismo SaldoVencidoRegularizado | CA-025, CA-027 |
| ObligacionPago | Pendiente | `DEJAR_SIN_EFECTO` | Sin efecto | `aplicar_cierre_sin_realizar` | — | SE-012, CA-070, CA-071, CA-096, CA-097, GL-053 |
| Pago | Registrado | `VERIFICAR` | Verificado | `registrar_y_verificar_pago`, `verificar_pago_registrado` | PagoVerificado | CA-018, CA-021, CA-027 |
| Pago | Registrado | `RECHAZAR_IMPORTE` | Importe incorrecto | `registrar_y_verificar_pago` (anticipo) | — | CA-019 |
| Devolucion | Pendiente | `REGISTRAR_EFECTUADA` | Efectuada | `registrar_devolucion_efectuada` | DevolucionRegistrada | SE-012, CA-098, GL-057 |

Estados terminales: Liquidada y Sin efecto (ObligacionPago), Verificado e Importe incorrecto (Pago), Efectuada (Devolucion). Única repetición idempotente: registrar otra vez una devolución Efectuada (sin cambios y sin segundo DevolucionRegistrada).

**Cómo se usa.**
- Las condiciones de negocio siguen en los métodos de `EstadoCuenta`; las máquinas solo validan el par estado-acción. Se consultan después de las comprobaciones existentes (mismos mensajes y orden) y antes de cualquier modificación.
- Pago y obligación son independientes. Un pago válido sobre una obligación Liquidada se registra, se verifica y emite su `PagoVerificado`; la obligación sigue Liquidada (no se consulta su máquina y no es una repetición idempotente). Los destinos del pago y de la obligación se validan antes de agregar o verificar el pago.
- Vencimiento masivo: primero se seleccionan las obligaciones que cumplen las condiciones actuales, luego se validan todas sus transiciones y solo entonces se asignan; las que no cumplen las condiciones no cambian. Lo mismo en `resolver_regularizacion` (antes de registrar el resultado) y en `aplicar_cierre_sin_realizar` (solo los cobros Pendiente; los demás se omiten sin rechazo, como antes).
- `verificar_pago_registrado` conserva su mensaje («Solo se verifica un pago registrado que está pendiente de verificación.») mediante `mensajes_rechazo` de `MAQUINA_PAGO`.
- Las altas de obligaciones, pagos y devoluciones son creaciones, no transiciones.

**Asuntos que se conservan sin resolver:** AR-08 (la búsqueda con `next(...)` no cambia) y los puntos del plan P-E3D-01 (tras «No regularizado» no se admite una segunda ventana), P-E3D-02 (el pago en el instante límite cuenta; la revisión exige un instante posterior) y P-E3D-03 (una sustitución integrada que está Vencida no queda Sin efecto al cerrarse). Las pruebas los fijan tal como están.

**Pruebas de la etapa** (53): `tests/test_estado_cuenta_maquina_estados.py`. Comparan el comportamiento con `tests/referencias/comportamiento_estado_cuenta_v8_e3c.json`, capturado con `tests/apoyo_maquina_estados_estado_cuenta.py` sobre el código del commit 8c80470, antes de E3D: 1203 combinaciones (30 situaciones del agregado × su estado inicial y 39 operaciones, más `registrar_devolucion_efectuada` en las 3 situaciones con devolución), que deben ser idénticas. La referencia no incluye identificadores inexistentes de devolución (D-E3D-5, AR-08).

```bat
python -m unittest tests.test_estado_cuenta_maquina_estados -v
python -m unittest discover -s tests -v
```

## Entregables

Los entregables principales están organizados en las siguientes rutas relativas:

- **Informe de arquitectura:** [`docs/informe/informe-arquitectura-eventos-nova.pdf`](docs/informe/informe-arquitectura-eventos-nova.pdf) y su versión editable `.docx`.
- **Registros de decisiones arquitecturales (ADR):** [`docs/ADR/ADR_Eventos_Nova.pdf`](docs/ADR/ADR_Eventos_Nova.pdf) y su versión editable `.docx`.
- **Matriz de trazabilidad:** [`docs/trazabilidad/matriz-trazabilidad.xlsx`](docs/trazabilidad/matriz-trazabilidad.xlsx) y [`docs/trazabilidad/matriz-trazabilidad.pdf`](docs/trazabilidad/matriz-trazabilidad.pdf).
- **Bitácora de IA:** [`docs/bitacora ia/Bitacora_IA_Eventos_Nova.pdf`](docs/bitacora%20ia/Bitacora_IA_Eventos_Nova.pdf) y su versión editable `.docx`.
- **Documentos de requisitos de la Unidad 2:** glosario, BRD y User Stories en `docs/unidad 2/`.
- **Diagramas:** diagramas de clases y secuencia en `diagramas/clases/` y `diagramas/secuencia/`; mapa de dominio en `diagramas/dominio/`; BPMN maestro con todos los subprocesos desplegados y subprocesos SP-01 a SP-08 en `diagramas/bpmn/` (fuente editable en draw.io `.drawio`; la misma versión en BPMN 2.0 `.bpmn`, que se abre en cualquier herramienta compatible; y exportaciones PDF, SVG y PNG), más una versión paginada del maestro para imprimir (`BPMN_Eventos_Nova_paginado.pdf`). Los cambios al BPMN se hacen en el `.drawio` y se exportan desde draw.io; el `.bpmn` y las exportaciones incluidas corresponden a esta versión del modelo.
- **Evidencias de pruebas:** archivos en `tests/evidencias/`.

