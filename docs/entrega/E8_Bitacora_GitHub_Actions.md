# E8 — Bitácora de GitHub Actions (Eventos Nova, Unidad 5)

Repositorio: https://github.com/leslynieto64-del/Eventos-nova-U5 · Workflow: `.github/workflows/ci.yml`

> Las tres ejecuciones históricas de abajo se hicieron cuando el workflow aún se llamaba **«CI»** y sus trabajos **«Pruebas, migraciones y cobertura»** y **«Docker Compose (DB + App + Tests)»**. Después se renombraron (solo presentación; ids internos `pruebas` y `docker` intactos) a **«Eventos Nova | Validación y CI — Unidad 5»** con trabajos **«Pruebas automatizadas y cobertura»** y **«Construcción y validación Docker»**. Las ejecuciones posteriores al renombrado (p. ej. la del PR #1 tras ese commit) no forman parte de la secuencia E8.

## Secuencia E8 (tres ejecuciones reales, en orden)
| # | Resultado | Ejecución | Rama / PR | Commit | Trabajo de pruebas | Trabajo Docker |
|---|---|---|---|---|---|---|
| 1 | **Success** | https://github.com/leslynieto64-del/Eventos-nova-U5/actions/runs/41250209274 | `fix/auditoria-integral` · PR #1 | d8e0663 | success · 1574 aprobadas, 0 fallidas, 0 omitidas | success · 1571 aprobadas, 3 omitidas |
| 2 | **Failure** (intencional) | https://github.com/leslynieto64-del/Eventos-nova-U5/actions/runs/41250517954 | `demo/e8-fallo-intencional` · PR #2 (cerrado, no fusionado) | 79c2ed7 | failure · 1 fallida, 1574 aprobadas | failure · 1 fallida, 1571 aprobadas, 3 omitidas |
| 3 | **Success** (recuperado) | https://github.com/leslynieto64-del/Eventos-nova-U5/actions/runs/41250782078 | `demo/e8-fallo-intencional` tras el revert · PR #2 | c895107 | success · 1574 aprobadas, 0 fallidas | success · 1571 aprobadas, 3 omitidas |

- **Motivo del fallo (ejecución 2):** se añadió `tests/test_e8_fallo_intencional.py` con `assertEqual(1 + 1, 3)` → `AssertionError: 2 != 3`. Falló el paso «Suite completa con pytest y cobertura» y el paso «Ejecutar la suite completa dentro de Docker (servicio tests, pytest)».
- **Aislamiento:** el commit 79c2ed7 existe solo en `demo/e8-fallo-intencional`; no es ancestro de `main` ni de `fix/auditoria-integral`. El PR #2 se cerró sin fusionar.
- **Recuperación (ejecución 3):** `git revert` del fallo; el árbol de la rama demo quedó idéntico al de `fix/auditoria-integral`.
- **Pruebas omitidas en Docker (3):** `tests/test_interfaz_textos.py` (líneas 82, 100, 113) necesitan Node.js, que la imagen Docker no incluye. Se ejecutan en el trabajo de pruebas (runner con Node) y en local: 1574 aprobadas, 0 omitidas. No son parte del laboratorio de la Unidad 5 (reglas, mocks, persistencia, seguridad, cobertura).

## Resultados de calidad (misma versión del código)
Cobertura 97.6 % global (sentencias 98.40 %, ramas 93.66 %) · `src/domain` 99.59 % · `src/application` 96.81 % · mínimo 80/80/80 cumplido · Ruff sin errores · Alembic: una sola cabeza (`0006`).

## Capturas a tomar manualmente
1. Success: https://github.com/leslynieto64-del/Eventos-nova-U5/actions/runs/41250209274 — debe verse el estado verde «Success» y los dos trabajos con ✓.
2. Failure: https://github.com/leslynieto64-del/Eventos-nova-U5/actions/runs/41250517954 — estado rojo «Failure»; abrir el trabajo de pruebas y mostrar `FAILED tests/test_e8_fallo_intencional.py` (`2 != 3`).
3. Success tras recuperar: https://github.com/leslynieto64-del/Eventos-nova-U5/actions/runs/41250782078 — verde «Success», rama `demo/e8-fallo-intencional`, commit c895107.
