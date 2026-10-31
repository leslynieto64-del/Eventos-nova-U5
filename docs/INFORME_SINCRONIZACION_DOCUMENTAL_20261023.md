# Informe de sincronización documental — Eventos Nova

**Fecha:** 23/10/2026
**Referencia de alcance:** `Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md` (decisiones A, B y C; reglas C-01 a C-15; A-6)
**Respaldo previo:** `..\Eventosnova_RESPALDO_ANTES_SINCRONIZACION_2026-10-23` (confirmado antes de editar)
**Revisiones de este informe:** (1) sincronización inicial; (2) revisión de cierre de la fase 1, que resolvió pendientes y corrigió una afirmación de la primera versión (ver 7.3).

## 1. Resultado de la fase

**La fase NO está cerrada.** Los documentos Word y la matriz están sincronizados con el cierre aprobado. Los diagramas fuente se actualizaron en lo que pudo representarse y validarse. Siguen abiertos:

- una decisión de negocio que el cierre aprobado no resuelve (contrato firmado con anticipo sin verificar al llegar T, sección 7.1);
- representaciones de diagrama que requieren geometría adicional (sección 5.2);
- todas las exportaciones PDF, PNG y SVG, que no pudieron regenerarse (sección 6).

## 2. Historial de cambios guardados

El método fue el reemplazo exacto de texto sobre el XML interno de cada archivo, sin re-serializarlo. Cada reemplazo exigía una coincidencia única o un número esperado de coincidencias.

| Archivo | Cambio |
|---|---|
| `docs/unidad 2/Reporte_BRD_Corregido.docx` | 21 ediciones: anticipo mínimo del 30 % (B); cierre sin confirmar, no reapertura y devolución A con el plazo de A-6 (BN-009, SE-010, SE-011); no reembolso con Evento cancelado, con excedentes y pagos tardíos (C); inicio automático en T (BN-010); contratación confirmada como precondición de servicios adicionales (BN-004, SE-004); pago tardío del saldo (BN-005); consultas sin obligaciones Sin efecto (BN-007); diferencia entre SE-012 y devolución A (SE-012); responsabilidad de Administración y alcance. |
| `docs/unidad 2/User_Stories_corregido.docx` | Historias nuevas US-032 y US-033. Criterios Gherkin nuevos CA-101 a CA-114. Criterios modificados: CA-019, CA-021, CA-091, CA-097, CA-098. US-031 precisada. Tabla de validación y trazabilidad actualizada (BN-004 a BN-010). Los criterios están dentro de este mismo documento, no en archivos separados. |
| `docs/unidad 2/Glosario_Corregido.docx` | Entradas nuevas GL-061 (devolución A) y GL-062 (obligación Sin efecto). Modificadas: GL-004, GL-009, GL-011, GL-012, GL-015, GL-031, GL-032, GL-033, GL-042, GL-049, GL-053, GL-055, GL-057, GL-060. |
| `docs/trazabilidad/matriz-trazabilidad.xlsx` | Filas 9, 10, 11, 17, 23, 24, 26 y 27 actualizadas. Filas nuevas 28 (devolución A) y 29 (anticipo superior al 30 %). En la revisión 2 se añadieron referencias a los BPMN en las filas 17, 24 y 27. Autofiltro, área de impresión y dimensión ampliados a la fila 29. |
| `diagramas/bpmn/…SP02_Contratacion` (`.bpmn` y `.drawio`) | Etiquetas «al menos el 30 %». **Revisión 2:** ruta de la devolución A tras el cierre, nota del plazo y subproceso de evento «Llegada de T con el Evento En gestión» (detalle en 5.1). |
| `diagramas/bpmn/…SP01_Propuesta` (`.bpmn` y `.drawio`) | **Revisión 2:** subproceso de evento «Llegada de T con el Evento En gestión» y ampliación de la altura del pool y la lane (390 → 500) para alojarlo. |
| `diagramas/bpmn/…SP04_Servicio_adicional` (`.bpmn` y `.drawio`) | **Revisión 2:** etiqueta de «Registrar la solicitud…» con la precondición «solo si la contratación está confirmada». |
| `diagramas/bpmn/…SP08_Devolucion_SE-012` (`.bpmn` y `.drawio`) | Etiqueta del plazo: desde el cierre, o desde el registro del pago si es posterior. |
| `diagramas/bpmn/BPMN_Eventos_Nova` (`.bpmn` y `.drawio`, maestro) | Las mismas etiquetas de SP-02, SP-04 y SP-08. **Revisión 2:** los subprocesos de evento de SP-01 y SP-02 y la ruta de la devolución A, dentro de sus subprocesos. «Gestionar la propuesta» pasa de 382 a 476 de alto. |
| `diagramas/dominio/mapa-dominio.drawio` | **Revisión 2:** solo texto en 6 celdas (Devolucion en las páginas 01, 04 y la vista 00; reacción del anticipo en la página 05 y la vista 00). Sin cambios de geometría ni de transiciones. |
| `docs/INFORME_SINCRONIZACION_DOCUMENTAL_20261023.md` | Este informe (archivo nuevo). |

### Identificadores nuevos y justificación
- **US-032:** Administración devuelve el anticipo de una contratación cerrada sin confirmarse. Es una decisión A sin historia previa, con actor y plazo propios, distintos de US-031.
- **US-033:** inicio automático en T y cierre de lo no confirmado (C-01, C-02). La transición de estado no tenía historia.
- **CA-101 a CA-114:** respaldan lo anterior y C-14, B, C-12, C-13 y C-06.
- **GL-061 y GL-062:** devolución A y obligación Sin efecto.
- No hay BN ni SE nuevos. No se crearon identificadores de BPMN con numeración nueva (no hay SP-09).

## 3. Documentos sincronizados y comprobados

- **BRD, historias con Gherkin, glosario y matriz.**
  - Las historias de usuario son 33 y los criterios 114, todos únicos; cada historia tiene al menos un criterio. El glosario tiene 62 entradas únicas.
  - Ninguna referencia a US, CA, GL, BN o SE apunta a un identificador inexistente, ni en los rangos.
  - La matriz tiene 29 filas y ninguna fórmula (0 antes y 0 después). Se conservaron estilos, filtros y áreas de impresión. Las filas 28 y 29 indican «pendiente de implementación» y no afirman código ni pruebas.
- **Reserva.** Los textos de BN-009, SE-010, BN-010, CA-110 y GL-033 reproducen la regla de C-01 de forma literal y no resuelven la decisión 7.1.

## 4. Documentos parcialmente sincronizados

| Documento | Qué falta |
|---|---|
| `mapa-dominio.drawio` | Solo texto. Falta: representar T como causa de la transición En gestión → Cerrado sin contratación; actualizar los pies de página de fuentes (siguen en US-001–US-031, CA-001–CA-098 y GL-001–GL-059); representar la devolución A como elemento propio y las notas de B y C. Esto requiere celdas nuevas o cambios de geometría que no pude verificar visualmente en draw.io. |
| `BPMN_Eventos_Nova_SP04…` y maestro | La precondición está en una etiqueta. No hay una rama de rechazo propia (compuerta y fin) para una solicitud sin contratación confirmada. Hay solo 40 px entre el evento inicial y «Registrar la solicitud», así que haría falta desplazar nodos. |
| SP-02 y maestro | Un pago de anticipo posterior al cierre está descrito en la nota, no como evento y flujo propios. |
| `informe-arquitectura-eventos-nova.docx` | **No revisado ni modificado** (fuera de la lista de documentos de esta fase). Mantiene «corresponde al 30 %» y «equivalente al 30 %» y no cita US-032, US-033 ni CA-101 a CA-114. Depende de las decisiones B y A. |

## 5. Diagramas

### 5.1 Cambios aplicados y su validación
- **SP-02 (autónomo y maestro).**
  - Se retargeteó `SP02_F15` (maestro: `MAE_F27`) para que «Cerrar el proceso de contratación sin confirmar» pase por `SP02_SinEfecto` (anticipo pendiente Sin efecto, el Liquidado se conserva, la contratación no se reabre) y por la compuerta `SP02_GwRecibido` («¿Se recibió algún importe como anticipo?»).
  - Con «Sí» sigue `SP02_DevA`, que devuelve el anticipo en 5 días hábiles desde la fecha de referencia, y termina en `SP02_FinDevA`. Con «No» llega al fin existente `SP02_FinCerrado`.
  - Se añadió la nota `SP02_NotaDevA` con la fecha de referencia y el límite exclusivo.
  - Subproceso de evento `SP02_EvT` con cuatro nodos: T → cerrar la contratación → devolver el anticipo → fin.
  - Flujos nuevos: `SP02_F27` a `SP02_F30` y `SP02_EvT_F01` a `F03`. En el maestro: `MAE_F320` a `MAE_F323`.
- **SP-01 (autónomo y maestro).** Subproceso de evento `SP01_EvT` con tres nodos: T → cerrar el proceso → fin «Cerrado sin contratación (no Cancelado)». Se amplió la altura del contenedor para alojarlo.
- **SP-04.** Etiqueta con la precondición.
- **SP-08.** Etiqueta con el plazo desde el registro cuando el pago es posterior al cierre.
- **Distinción de las devoluciones.** La devolución SE-012 sigue en SP-08 y en sus copias dentro de SP-03, SP-04 y SP-05. La devolución A solo aparece en SP-02. No se mezclaron.
- **Validación aplicada a los 9 `.bpmn` del proyecto.**
  - Ids únicos; referencias de flujos válidas; incoming y outgoing simétricos; todos los nodos y flujos tienen forma en el DI.
  - Sin solapamientos de nodos; ninguna flecha atraviesa un nodo que no sea su origen o destino; los extremos de cada flecha tocan sus nodos.
  - El validador, ejecutado primero sobre los originales del respaldo, no encontraba problemas; sigue sin encontrarlos.
  - Los límites de etiquetas no solapan con otros nodos ni etiquetas más allá de los solapes que ya existían (1, 1, 7 y 29 en SP-01, SP-02, SP-04 y el maestro).
- **Draw.io.** En los cuatro `.drawio` que cambiaron (SP-01, SP-02, SP-04 y el maestro), la posición de todos los vértices y los puntos intermedios de las flechas coinciden con su `.bpmn` (0 diferencias, también en el estado original).

### 5.2 Estructurales pendientes
Ver la sección 4 (precondición de SP-04, pago posterior al cierre y mapa de dominio). Falta además la decisión 7.1, de la que dependen la etiqueta del cierre por T en SP-02 y el maestro, y su equivalente para un contrato firmado.

### 5.3 Límite de la validación visual
No hay draw.io ni otro visor BPMN. La disposición se revisó con un renderizador esquemático propio, que no equivale a draw.io. Por tanto **no está verificado** que cada etiqueta quepa en su caja ni la apariencia final. Abra los archivos en draw.io antes de darlos por buenos.

## 6. Exportaciones pendientes

No existe un generador en el repositorio ni herramientas de exportación (draw.io, Inkscape, LibreOffice, etc.). No instalé ninguna. **Ninguna exportación está actualizada.**

| Exportación pendiente | Fuente cambiada |
|---|---|
| `BPMN_Eventos_Nova` (`.pdf`, `_paginado.pdf`, `.png`, `.svg`) | maestro (`.bpmn` y `.drawio`) |
| `…SP01_Propuesta` (`.pdf`, `.png`, `.svg`) | SP-01 |
| `…SP02_Contratacion` (`.pdf`, `.png`, `.svg`) | SP-02 |
| `…SP04_Servicio_adicional` (`.pdf`, `.png`, `.svg`) | SP-04 |
| `…SP08_Devolucion_SE-012` (`.pdf`, `.png`, `.svg`) | SP-08 |
| `mapa-dominio.pdf` | `mapa-dominio.drawio` (texto cambiado) |
| `Reporte_BRD_Corregido.pdf` | BRD |
| `User_Stories_corregido.pdf` | historias con Gherkin |
| `Glosario_Corregido.pdf` | glosario |
| `matriz-trazabilidad.pdf` | matriz |

SP-03, SP-05, SP-06 y SP-07 no cambiaron; sus exportaciones siguen vigentes.

## 7. Decisiones funcionales por confirmar

### 7.1 Contrato firmado y anticipo sin verificar al llegar T
**Qué dicen las fuentes.** C-01 establece que, en T, «un Evento todavía En gestión pasa a Cerrado sin contratación, y su contrato no firmado, a Cerrado sin confirmar». Un contrato firmado cuyo anticipo todavía no está verificado sigue sin contratación confirmada, así que el **Evento** queda cubierto por esa regla. Se comprobó en el cierre, el BRD (BN-006, BN-009, BN-010, SE-010, SE-011), las historias originales (CA-020, CA-021, CA-070, CA-071, CA-096) y el glosario (GL-009, GL-011, GL-033): ninguna fuente dice qué estado toma **el contrato firmado**, ni qué ocurre con un anticipo pagado antes de T pero verificado después de T.

**Alternativas sin resolver.**
1. El contrato firmado también pasa a Cerrado sin confirmar, igual que en el cierre por falta de anticipo (compatible con la ruta existente en SE-010).
2. Otro estado o tratamiento definido por negocio.
3. Para el pago verificado después de T: decidir si confirma la contratación o se devuelve como devolución A. A-1 a A-3 y C-02 apuntan a no confirmar y devolver, pero no lo dicen para este caso.

**Documentos que dependen de la decisión.** BRD (BN-009, BN-010, SE-010, SE-011); historias (US-033, CA-110, CA-021); glosario (GL-033); matriz (filas 26, 27 y 28); SP-02 (`SP02_EvT_Cerrar`) y el maestro; mapa de dominio (estados del Contrato).
**Mientras tanto,** los documentos reproducen solo la regla literal y los diagramas lo dejan indicado en la documentación del nodo. No se inventó ningún estado.

### 7.2 Otras confirmaciones
- **Devolución A cuando el cierre es por llegada de T.** Los documentos la aplican porque A se define para toda contratación que queda Cerrada sin contratación y C-01 la produce. El cierre no lo afirma expresamente. Confirmar.
- **Precondición de servicios adicionales en SP-04.** ¿Basta la etiqueta o se desea una rama de rechazo explícita?
- **Informe de arquitectura, ADR y bitácora.** Decidir si se actualizan a las decisiones A, B y C (ver 4).

### 7.3 Verificaciones resueltas en la revisión 2
- **CU-02 y CU-03.** Sus definiciones están en `Resumen_EventosNova_U3_Equipo16.docx` y en el informe de arquitectura. CU-02 es «Formalizar contratación»; incluye anticipo y el cierre «Cerrado sin contratación». CU-03 es «Gestionar cierre del evento»; incluye cancelación, regularización, estados del Evento (inicio, Finalizado, Cancelado, Cerrado sin contratación) y devoluciones. Las filas 26, 28 y 29 (CU-02 y CU-03 o CU-02) y la fila 27 (CU-03) son coherentes con esas definiciones. No hubo que corregir ninguna referencia.
- **Días hábiles.** La primera versión de este informe afirmó que la frase del informe de arquitectura sobre los festivos contradecía C-15. **Esa afirmación era incorrecta y se retira.** La frase del informe de arquitectura («no se consideran días festivos ni se utiliza un calendario de festivos») copia el texto anterior de GL-060. Se lee como que no se aplica ningún calendario de festivos, es decir, todo día de lunes a viernes cuenta como hábil. Es la misma regla que C-15 («festivos contados como hábiles»). No hay contradicción y no se modificó ese documento. Solo la redacción original era ambigua; GL-060 ya la hace explícita.

## 8. Validaciones y limitaciones

| Validación | Alcance | Limitación |
|---|---|---|
| Integridad de DOCX y XLSX | Paquetes ZIP válidos y XML bien formado en cada parte. | No se abrieron en Word ni Excel. |
| Identificadores y referencias | Los 3 DOCX y el XLSX, incluidos los rangos. | No valida que el significado de cada referencia sea correcto; eso se revisó leyendo. |
| Estructura BPMN (validador propio) | 9 archivos, con línea base previa limpia. | No evalúa semántica BPMN completa ni el ajuste del texto a las cajas. |
| Coherencia Draw.io ↔ BPMN | Posiciones de vértices y puntos de flechas. | Draw.io no se pudo abrir. |
| Revisión visual | Renderizado esquemático propio de SP-01, SP-02 y el maestro. | No es draw.io. |
| Pruebas existentes que leen estos archivos | `test_coherencia_diagramas` (14), `test_estado_cuenta_maquina_estados` (53), `test_solicitud_cambio_maquina_estados` (43) y `test_servicio_adicional_maquina_estados` (35): pasan antes y después. | No son la suite completa ni validan el comportamiento del software. |
| Cierre aprobado | SHA-256 idéntico antes y después. | — |

## 9. Confirmaciones

- `Cierre_Alcance_Eventos_Nova_FINAL_APROBADO_20261023.md`: intacto (`b67d2f47…5487a`).
- No se modificó código, pruebas, base de datos, configuración ni dependencias. `src` y `tests` son idénticos al respaldo.
- No se ejecutó ninguna operación de Git que escriba. El estado de Git cambió únicamente porque los archivos documentales quedaron modificados (las 17 modificaciones previas de `src` y `tests` ya existían al empezar).
- No se instalaron herramientas ni se eliminaron o movieron archivos. Los scripts temporales y las copias de trabajo están fuera del proyecto, en la carpeta temporal de la sesión.
- Nada se declara como implementado, probado o exportado sin evidencia.
