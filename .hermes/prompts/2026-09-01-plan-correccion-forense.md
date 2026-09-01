# PLAN DE CORRECCIÓN FORENSE — Basado en López de Prado

**Origen:** Forensic audit tras walkthrough Gemini + E1-E6 + Ranking Maestro
**Framework:** López de Prado — Triple Barrier, Deflated Sharpe Ratio, Combinatorial Purged Cross-Validation

---

## BS-1 🔴 P0 — Ranking sin ajuste por múltiples comparaciones (p-hacking)

**López de Prado:** Con 33 señales × 3 escalas = 99 pruebas, el mejor score esperado por azar NO es 0 sino ~2.3σ. El ranking actual usa `score_compuesto` crudo sin deflactar.

**Datos:**
| Señal | Score | ¿Significativo tras Bonferroni? |
|:------|:-----:|:-------------------------------:|
| sv5t_silent_distribution | 33.62 | ✅ α=0.05/33=0.0015 → Sí |
| cascade_reversal | 14.66 | ⚠️ Depende del p-valor real |
| Las 10 primeras | 2-33 | Sin ajuste no podemos afirmar |

**Corrección:** Agregar columna `p_bonferroni` al ranking maestro. Bonferroni `α' = 0.05 / 33`.

---

## BS-2 🟡 P1 — E2: N=6 post-QE es diamante, no confirmación

**Datos:**
| Período | N | Hit | CI95 |
|:--------|:-:|:---:|:----:|
| Pre-QE (antes 2010) | 77 | 62.3% | [0.51, 0.73] |
| Post-QE (después 2010) | **6** | 83.3% | **[0.36, 0.99]** |

**Problema:** El walkthrough dice "Invarianza Confirmada". Con N=6 y CI95=[0.36, 0.99], la señal post-QE es un **DIAMANTE §3.3**. No hay poder estadístico para confirmar invarianza.

**Corrección:** Cambiar conclusión de "Invarianza Confirmada" a "PENDIENTE — N=6 insuficiente (diamante §3.3). Se requieren más datos o bootstrap."

---

## BS-3 🟡 P1 — `delta_medio` no existe por slot de timing

**Datos:** `timing_canonico` tiene `delta_medio` global, pero `rendimiento_por_slot` no incluye `delta_medio` por slot.

| Señal | Slot | N | Hit | EV | ¿delta_medio? |
|:------|:----:|:-:|:---:|:--:|:-------------:|
| cascade_reversal | t=0 | 118 | 85.6% | +1.98% | ❌ No existe |
| cascade_reversal | ENTRE | 61 | 13.1% | -2.04% | ❌ No existe |

**Corrección:** Agregar `delta_medio` y `delta_mediana` al `rendimiento_por_slot` en `evaluador_general.py`.

---

## BS-4 ⚪ P2 — Triple barrier sin time-stop

**López de Prado:** La triple barrier tiene 3 barreras:
1. Take-profit (favorable) → ✅ Implementado (zz25/zz50/zz75)
2. Stop-loss (adversa) → ✅ Implementado (misma barrera opuesta)
3. **Time-stop** (máximo N barras) → ❌ **NO IMPLEMENTADO**

**Impacto:** Una señal que tarda 200 barras en cruzar la barrera favorable tiene el mismo `bars_medio` que una que tarda 5 barras. No hay penalización temporal.

**Dato concreto:**
| Señal | bars_medio (zz25) | bars_medio (zz75) |
|:------|:-----------------:|:-----------------:|
| cascade_reversal | 6.4 | ~30-44 |
| credit_stress | 4.2 | ~30-44 |
| sv5t_silent_distribution | 8.1 | ~25 |

**Corrección:** Implementar time-stop como `max_barras = ceil(1/scale)`. Para zz25=2.5% → max=40 barras. Si no cruza en 40 barras, es "timeout" con favorable=0.

---

## BS-5 🟡 P1 — E3 lead/lag: días calendario vs barras de trading

**Datos:**
| Métrica | Valor |
|:--------|:-----:|
| `delta_mediana_barras` | 0 |
| Conclusión | "Indicador coincidente/líder" |

**Problema:** `delta_mediana_barras=0` significa que la mitad de las veces credit_stress dispara exactamente en el suelo del SPY. Pero si la ventana de búsqueda usa días calendario (no trading days), un viernes→lunes aparece como "exacta" cuando pasaron 3 días calendario (gap de fin de semana).

**Corrección:** Documentar explícitamente que `delta_mediana_barras` usa **barras de trading** (no días calendario). Si `VENTANA_DIAS` sigue siendo días calendario en el evaluador vela-a-vela, eso contamina los resultados de E3.

---

## BS-6 🟡 P1 — Sin p-values ni CI95 en E1-E6

**Datos:**
| Ejercicio | Reporta p-valor? | Reporta CI95? |
|:----------|:----------------:|:--------------:|
| E1 | Fisher exact p≈0 | ❌ No |
| E2 | ❌ No | ❌ No |
| E3 | ❌ No | ❌ No |
| E4 | ❌ No | ❌ No |
| E5 | ❌ No | ❌ No |
| E6 | ❌ No | ❌ No |

**Problema:** Sin intervalos de confianza, no sabemos si los resultados son estables o artefactos de muestra pequeña.

**Corrección:** Agregar CI95 Clopper-Pearson a cada métrica de los 6 ejercicios. Al menos reportar `hit_rate_ci95_lower`, `hit_rate_ci95_upper` para cada celda.

---

## ORDEN DE EJECUCIÓN

| # | Prioridad | BS | Corrección | Archivo | Esfuerzo |
|:-:|:---------:|:--:|:-----------|:--------|:---------|
| 1 | 🔴 P0 | 1 | Agregar `p_bonferroni` al ranking maestro | `consolidar_ranking.py` | 10 min |
| 2 | 🔴 P0 | 4 | Implementar time-stop en first-passage | `evaluador_general.py` | 20 min |
| 3 | 🟡 P1 | 2 | Cambiar conclusión E2: "PENDIENTE (diamante)" | `ejercicios_regimen.py` | 5 min |
| 4 | 🟡 P1 | 3 | Agregar delta_medio por slot de timing | `evaluador_general.py` | 10 min |
| 5 | 🟡 P1 | 5 | Documentar barras de trading en E3 timing | `ejercicios_regimen.py` | 5 min |
| 6 | 🟡 P1 | 6 | Agregar CI95 Clopper-Pearson a E1-E6 | `ejercicios_regimen.py` | 15 min |
| 7 | ⚪ P2 | — | VENTANA_DIAS → VENTANA_BARRAS (arrastrado) | `evaluador_vela_a_vela.py` | 10 min |

---

## LÓPEZ DE PRADO — Veredicto sobre el ecosistema actual

| Principio | Status |
|:----------|:------:|
| Triple Barrier (3 barreras) | ⚠️ Parcial — falta time-stop |
| Deflated Sharpe Ratio | ❌ No implementado |
| Combinatorial Purged CV | ❌ Walk-forward standard (sin purging) |
| Meta-labeling | ❌ No aplica (señales booleanas) |
| Stochastic Control vs Deterministic | ⚠️ First-passage es determinístico, no estocástico |
| CPV protegida contra overflow | ❌ No implementado en SIGMET |

**Veredicto general:** El ecosistema es operacional y produce resultados útiles, pero **no cumple con el estándar académico de López de Prado** en 5/7 principios. Esto es aceptable para una herramienta de screening de señales, pero cualquier publicación o uso institucional requeriría cerrar estos gaps.