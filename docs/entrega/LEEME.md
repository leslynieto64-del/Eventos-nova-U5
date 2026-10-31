# Entrega del PIA — Eventos Nova (Equipo 16)

| Archivo | Contenido |
|---|---|
| `Reporte_Final_PIA_Eventos_Nova.pdf` | Reporte final: análisis (BRD), arquitectura, implementación, calidad, producción, trazabilidad, evidencias, cumplimiento de la consigna, pendientes y conclusiones |
| `Presentacion_Defensa_Eventos_Nova.pptx` | Presentación de apoyo para la defensa (9 diapositivas con notas del orador) |

Ambos se generan con `scripts/generar_entrega_pia.py` a partir de las evidencias reales del repositorio (cifras de `tests/evidencias/`, `docs/api/openapi.json` y el esquema). El script necesita `reportlab` y `python-pptx`, que **no** son dependencias de la aplicación: instálelos en un entorno aparte (en Windows, en una ruta corta, porque `lxml` falla con rutas largas).

**Antes de subirlos:** revisar el contenido, anotar en el README las URL reales del repositorio y del despliegue (hoy figuran como pendientes) y, si se cambian cifras, volver a ejecutar las pruebas y regenerar. Si la plataforma pide un archivo comprimido, incluir ambos documentos en un ZIP.

## Regeneración del 29/10/2026 (versión vigente)

El PDF (7 páginas) y la presentación (9 diapositivas) se regeneraron el 29/10/2026 con `scripts/generar_entrega_pia.py`, en un entorno aislado fuera del repositorio. Cambios en el script (solo textos y fuentes de datos): `FECHA`, `VALIDACION_MANUAL_T21_T23` con los resultados de T-21, T-23 y T-24 informados por el equipo, viñetas de evidencias y pendientes, la observación de BN-005 (ya no aplica: el bloqueo usa el vencimiento de hecho) y la lectura de la evidencia `tests/evidencias/ejecucion-docker-final-20261028-202102.txt` (UTF-16; 1415 pruebas, 98,82 % / 95,77 %), para lo que `_leer` reconoce ahora la marca UTF-16. **Diferencias de entorno:** la fuente Arial (ruta de Windows en el script) se sustituyó por Liberation Sans, métricamente equivalente, mediante un enlace en el directorio de ejecución; el script no se cambió para ello. **Revisión visual:** las 7 páginas del PDF (rasterizadas) y las 9 diapositivas (convertidas a imagen con LibreOffice, no con PowerPoint): sin texto cortado ni desbordado. Las notas del orador se generan desde el script.

## Regeneración anterior (preparada el 28/10/2026; historial)

**Estado actual (28/10/2026):** el PDF y la presentación se regeneraron el 28/10/2026 con `scripts/generar_entrega_pia.py` en un entorno temporal aislado (`reportlab`, `python-pptx`, `sqlalchemy` y `pymupdf` instalados fuera del repositorio, en `C:\pia_env_tmp`) y se revisaron visualmente (las 7 páginas del PDF y las 9 diapositivas, exportadas con PowerPoint). Incluyen el ADR-007, los diagramas actualizados, los tres defectos de implementación D-1 a D-3 y la validación manual con T-21 y T-23 **declaradas pendientes de repetición**. **No son la versión final**: deben regenerarse cuando el equipo ejecute T-21 y T-23 y se registren sus resultados.

**Fuentes (no hay otra fuente editable):** `scripts/generar_entrega_pia.py`. Lee `tests/evidencias/ejecucion-pruebas-e1-e4-host-20261025.txt`, `cobertura-e1-e4-20261025.txt`, `docs/api/openapi.json` y el esquema (`infrastructure/esquema_postgresql.py`); los textos y las constantes (`FECHA`, `VALIDACION_MANUAL_T21_T23`, `PENDIENTES`, `adrs`, `us`, `ca`…) están en el propio script. El script ya se preparó el 28/10 para: contar 7 ADR y citar el ADR-007; listar en *Evidencias* la validación manual y los diagramas actualizados; y declarar T-21 y T-23 como «pendiente de repetición». Compila (`python -m py_compile`), pero **no se ejecutó**.

**Procedimiento:**

1. El equipo ejecuta T-21 y T-23 (`docs/pruebas-manuales/GUIA_PRUEBAS_MANUALES_T14_T24.md`, sección 11) y registra los resultados reales en `docs/architecture/CIERRE_AUDITORIA_FINAL.md` §I y en la guía (sección 10).
2. Se actualizan en el script, solo con esos resultados: `VALIDACION_MANUAL_T21_T23`, el texto de las viñetas de *Evidencias* y de pendientes que mencionan T-21/T-23, y `FECHA` (fecha real de generación). Si cambió el número de pruebas o la cobertura, se vuelven a ejecutar las pruebas y se apuntan las rutas de las evidencias nuevas en `cifras()`.
3. Se usa un entorno aparte con `reportlab`, `python-pptx` y `sqlalchemy` (en una ruta corta en Windows; en esta regeneración, `C:\pia_env_tmp`, creado con `python -m venv` e `pip install reportlab python-pptx sqlalchemy pymupdf`) y se ejecuta, desde la raíz: `<python del entorno> scripts/generar_entrega_pia.py`.
4. **Verificación textual:** extraer el texto del PDF (`pdftotext`) y del PPTX (python-pptx, incluidas las notas) y comprobar que solo aparecen las cifras vigentes y que no se afirma la aprobación de T-21/T-23 más allá de lo registrado.
5. **Verificación visual (no se puede sustituir por la textual):** abrir el PDF y revisar todas las páginas; abrir la presentación en PowerPoint (por ejemplo exportando las diapositivas a imágenes) y revisar las nueve diapositivas y las notas. Anotar en `CIERRE_AUDITORIA_FINAL.md` qué se revisó visualmente y qué no.
6. Si la plataforma pide un archivo comprimido, incluir ambos documentos en un ZIP.
