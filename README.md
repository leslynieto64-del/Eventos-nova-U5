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
│   ├── test_coherencia_diagramas.py
│   ├── test_correcciones_etapas_3_a_7.py
│   ├── test_decisiones_stakeholder.py
│   ├── test_etapa9_casos_de_uso.py
│   ├── test_etapa9_transacciones_y_reacciones.py
│   └── test_reglas_corregidas.py
└── README.md
```

## Instrucciones de ejecución

Se requiere Python 3. Abre una terminal en la carpeta raíz del proyecto y ejecuta:

```bash
py -m unittest discover -s tests -v
```

Si el comando `py` no está disponible, utiliza:

```bash
python -m unittest discover -s tests -v
```

El registro de evidencias incluido reporta **91 pruebas aprobadas**. Para verificar el resultado de una ejecución actual, ejecuta nuevamente el comando y revisa el resumen de la terminal.

## Entregables

Los entregables principales están organizados en las siguientes rutas relativas:

- **Informe de arquitectura:** [`docs/informe/informe-arquitectura-eventos-nova.pdf`](docs/informe/informe-arquitectura-eventos-nova.pdf) y su versión editable `.docx`.
- **Registros de decisiones arquitecturales (ADR):** [`docs/ADR/ADR_Eventos_Nova.pdf`](docs/ADR/ADR_Eventos_Nova.pdf) y su versión editable `.docx`.
- **Matriz de trazabilidad:** [`docs/trazabilidad/matriz-trazabilidad.xlsx`](docs/trazabilidad/matriz-trazabilidad.xlsx) y [`docs/trazabilidad/matriz-trazabilidad.pdf`](docs/trazabilidad/matriz-trazabilidad.pdf).
- **Bitácora de IA:** [`docs/bitacora ia/Bitacora_IA_Eventos_Nova.pdf`](docs/bitacora%20ia/Bitacora_IA_Eventos_Nova.pdf) y su versión editable `.docx`.
- **Documentos de requisitos de la Unidad 2:** glosario, BRD y User Stories en `docs/unidad 2/`.
- **Diagramas:** diagramas de clases y secuencia en `diagramas/clases/` y `diagramas/secuencia/`; mapa de dominio en `diagramas/dominio/`; BPMN maestro con todos los subprocesos desplegados y subprocesos SP-01 a SP-08 en `diagramas/bpmn/` (fuente editable en draw.io `.drawio`; la misma versión en BPMN 2.0 `.bpmn`, que se abre en cualquier herramienta compatible; y exportaciones PDF, SVG y PNG), más una versión paginada del maestro para imprimir (`BPMN_Eventos_Nova_paginado.pdf`). Los cambios al BPMN se hacen en el `.drawio` y se exportan desde draw.io; el `.bpmn` y las exportaciones incluidas corresponden a esta versión del modelo.
- **Evidencias de pruebas:** archivos en `tests/evidencias/`.

