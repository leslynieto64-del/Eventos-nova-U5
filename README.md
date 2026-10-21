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
│   ├── domain/
│   │   ├── base.py
│   │   ├── contrato.py
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

## Entregables

Los entregables principales están organizados en las siguientes rutas relativas:

- **Informe de arquitectura:** [`docs/informe/informe-arquitectura-eventos-nova.pdf`](docs/informe/informe-arquitectura-eventos-nova.pdf) y su versión editable `.docx`.
- **Registros de decisiones arquitecturales (ADR):** [`docs/ADR/ADR_Eventos_Nova.pdf`](docs/ADR/ADR_Eventos_Nova.pdf) y su versión editable `.docx`.
- **Matriz de trazabilidad:** [`docs/trazabilidad/matriz-trazabilidad.xlsx`](docs/trazabilidad/matriz-trazabilidad.xlsx) y [`docs/trazabilidad/matriz-trazabilidad.pdf`](docs/trazabilidad/matriz-trazabilidad.pdf).
- **Bitácora de IA:** [`docs/bitacora ia/Bitacora_IA_Eventos_Nova.pdf`](docs/bitacora%20ia/Bitacora_IA_Eventos_Nova.pdf) y su versión editable `.docx`.
- **Documentos de requisitos de la Unidad 2:** glosario, BRD y User Stories en `docs/unidad 2/`.
- **Diagramas:** diagramas de clases y secuencia en `diagramas/clases/` y `diagramas/secuencia/`; mapa de dominio en `diagramas/dominio/`; BPMN maestro con todos los subprocesos desplegados y subprocesos SP-01 a SP-08 en `diagramas/bpmn/` (fuente editable en draw.io `.drawio`; la misma versión en BPMN 2.0 `.bpmn`, que se abre en cualquier herramienta compatible; y exportaciones PDF, SVG y PNG), más una versión paginada del maestro para imprimir (`BPMN_Eventos_Nova_paginado.pdf`). Los cambios al BPMN se hacen en el `.drawio` y se exportan desde draw.io; el `.bpmn` y las exportaciones incluidas corresponden a esta versión del modelo.
- **Evidencias de pruebas:** archivos en `tests/evidencias/`.

