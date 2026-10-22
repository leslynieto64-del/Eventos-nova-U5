# Evidencias F2: ejecución del paquete oficial 16_Eventos_Nova

Generado por `python ejecutar_paquete_pia.py` (verificación: `python ejecutar_paquete_pia.py --verificar`).
Contenido determinista: sin identificadores aleatorios ni marcas de tiempo.

## Entradas (sin modificar)

| Archivo | Registros | SHA-256 |
|---|---|---|
| actores.csv | 40 | `64996c64eca5a253067ef9102c8832978646159e511bc0126f622939512a8d6a` |
| catalogo.csv | 20 | `5933a87d19072555d602c3d656b0550e6c08cabc6ae0b369e0e300983c4be8be` |
| operaciones.csv | 60 | `cb9a091864b3cd103898bee5328aa03315fbc89347512e093e3c12412255eb69` |
| detalle_operaciones.csv | 117 | `131ab6d724ba3894f8418a5856ce48c1804a8882419445c8e61521d018a04ced` |
| casos_prueba.csv | 120 | `ee24c89b0c78feda2fe0b5b2802223c9bb0ebc3b256353d4e012849a755b8a27` |
| transiciones_prueba.csv | 20 | `f691e9eb54ff7ba088e55dc22ed5f3cbb171923e1bc457a6bda8eb5c9bd7f5f1` |
| MANIFIESTO.sha256 | — | `437fbc664e9e38c89f9e8364818337c2a944f730e009458f154a77c34938c2fe` |

## Totales

- Operaciones: 60; coinciden con el oráculo: 60.
- Suma de los totales: 372918.00 MXN (Decimal).
- Operaciones sin líneas (total 0.00): EVE-O013, EVE-O039.

## Casos (casos_prueba.csv)

| Familia | Diferencia | Casos | CUMPLE | NO_CUMPLE | APROBADO | FALLIDO | NO_EJECUTABLE |
|---|---|---|---|---|---|---|---|
| evaluar_beneficio | D-02 | 60 | 9 | 51 | 60 | 0 | 0 |
| validar_operacion | D-01 | 60 | 42 | 18 | 60 | 0 | 0 |
| **Total** | | 120 | 51 | 69 | 120 | 0 | 0 |

Casos con observaciones del catálogo (D-06, no cambian el veredicto): 12 (EVE-T005, EVE-B005, EVE-T015, EVE-B015, EVE-T020, EVE-B020, EVE-T035, EVE-B035, EVE-T040, EVE-B040, EVE-T055, EVE-B055).

## Transiciones (transiciones_prueba.csv)

| Acción | Transiciones | APROBADO | FALLIDO | NO_EJECUTABLE | Coincide con el paquete (SÍ/NO/—) | Diferencias |
|---|---|---|---|---|---|---|
| aprobar | 4 | 4 | 0 | 0 | 3/1/0 | D-05 |
| cancelar | 4 | 4 | 0 | 0 | 0/4/0 | D-03 |
| completar | 4 | 4 | 0 | 0 | 4/0/0 | — |
| saltar_estado | 4 | 4 | 0 | 0 | 4/0/0 | — |
| repetir_aprobacion | 4 | 3 | 0 | 1 | 0/3/1 | D-04, D-05, D-08 |
| **Total** | 20 | 19 | 0 | 1 | 11/8/1 | |

## Criterios

- APROBADO: el resultado real coincide con el esperado (resultado y condiciones incumplidas en los casos; resultado, mensaje, estados, Domain Events, anticipo y ausencia de cambios parciales en las transiciones). No basta con que no haya excepción.
- FALLIDO: el resultado real no coincide con el esperado (fallo funcional).
- NO_EJECUTABLE: la entrada no puede representarse en el dominio por una regla aprobada documentada; se verifica el rechazo.
- `coincide_con_paquete = NO`: diferencia documentada del modelo (ver `diferencias_modelo.csv`), no un fallo.
- Los esperados de los casos se derivan del texto de las reglas del LEEME con un oráculo independiente (los resultados del docente no forman parte del paquete del alumno).

## Preguntas abiertas

- **Q-01.** ¿A qué estado del dominio corresponde EN_PREPARACION y, por tanto, qué salto representa «saltar_estado»? Alternativas: (a) Dentro de «En organización» (semántica de GL-033); (b) «En ejecución» (posición en el flujo). Decisión provisional: Se ejecuta el inicio del evento desde «En gestión» (salta la contratación); el resultado es un rechazo en ambas interpretaciones.
- **Q-02.** ¿«completar» significa llegar a REALIZADO o completar el paso actual? Alternativas: (a) Llegar a REALIZADO (finalizar); (b) avanzar al siguiente estado (equivaldría a «aprobar»). Decisión provisional: (a): se ejecuta la finalización, porque «aprobar» ya cubre el paso COTIZADO → CONTRATADO.
- **Q-03.** ¿Qué resultado espera el docente para cada caso y transición? Alternativas: Comparar con los resultados de `02_Docente` cuando estén disponibles. Decisión provisional: Esperados derivados del texto del LEEME y de las reglas del equipo.
