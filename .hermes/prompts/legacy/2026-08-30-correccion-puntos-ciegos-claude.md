# CORRECCIÓN — Puntos Ciegos en Auditoría Definitiva OOS Multi-Celda

**Auditoría auditada:** `auditoria_definitiva_oos_multicelda.md` (Claude Opus, 21:13)
**Auditor:** deepseek/deepseek-v4-flash (Hermes)
**Propósito:** Identificar 7 puntos ciegos que Claude no detectó

---

## PUNTO CIEGO 1 — Bonferroni genérico de 6 celdas (imp precisión, no cambia conclusión)

**Claude dice:** "6 celdas teóricas por señal → Bonferroni: α_ajustado = 0.05 / 6 = 0.0083"

**Realidad:** El validador multi-celda solo prueba las celdas que califican (edge IS > 0, N ≥ 10). Por señal:

| Señal | Celdas probadas OOS | α_ajustado real | α de Claude |
|:------|:-------------------:|:---------------:|:-----------:|
| cascade_reversal | 2 | 0.0250 | 0.0083 |
| vvix_entry | 3 | 0.0167 | 0.0083 |
| capitulacion | 2 | 0.0250 | 0.0083 |
| pcr_put_panic | 2 | 0.0250 | 0.0083 |

**Impacto:** La conclusión no cambia (cascade_reversal sobrevive ambos), pero el número exacto es señal-dependiente. Claude fue conservador, lo cual es correcto para el rigor, pero impreciso en el detalle.

**Corrección:** Agregar n_celdas_probadas al cálculo de Bonferroni en el JSON (`p_bonferroni = p_raw × n_celdas_probadas`).

---

## PUNTO CIEGO 2 — Score bug también aplica a cascade_reversal (potencial)

**Claude detectó el bug en credit_stress**, pero no mencionó que cascade_reversal tiene 2 celdas probadas: `zz25|ALZA` (9/9 folds) y `zz75|ALZA` (0/1 folds). Hoy no hay conflicto porque zz75|ALZA no tiene OOS positivo. Pero si en el futuro cascade ganara una segunda celda con OOS, el mismo bug de desempate aplicaría.

**Fix:** El mismo que Claude propuso — agregar `folds_con_test` como desempate en `_score()`.

---

## PUNTO CIEGO 3 — Sign-test con 3-4 folds tiene poder estadístico casi nulo

**Claude no mencionó** que el sign-test binomial con 3-4 observaciones no puede alcanzar significancia práctica:

| Folds | Mínimo p posible (todos positivos) | 
|:-----:|:----------------------------------:|
| 3 | 0.125 |
| 4 | 0.0625 |
| 5 | 0.03125 |
| 9 | 0.0020 (cascade_reversal) |

`vvix_entry` con 3 folds no puede pasar p < 0.05 ni siquiera con 3/3 aciertos. Esto no es un error de la señal — es una limitación del método walk-forward con pocos bloques de test. Claude clasificó vvix_entry como "INCONCLUSO" por el outlier, pero la razón más fundamental es que **3 folds son insuficientes para cualquier test binomial**.

**Corrección:** Documentar que señales con < 5 folds OOS no pueden alcanzar significancia binomial por construcción. Su veredicto debe ser "PENDIENTE — insuficientes folds" en lugar de "INCONCLUSO por outlier".

---

## PUNTO CIEGO 4 — No mencionó la fortaleza del baseline limpio (P5)

El evaluador excluye los propios disparos de la señal del baseline (P5 del diseño). Claude no lo menciona. Esto es importante porque garantiza que el baseline no está contaminado — si alguien lee la auditoría sin conocer el evaluador, podría pensar que el baseline incluye los disparos de la señal y por tanto está sesgado.

**Corrección:** Agregar nota: "El baseline del validador excluye los pivotes donde la señal disparó (P5 del evaluador v3). El baseline nunca está contaminado con la propia señal."

---

## PUNTO CIEGO 5 — breadth_contraction_exit tiene edge absoluto mayor que cascade_reversal

| Señal | OOS edge | Folds+ | Consistencia |
|:------|:--------:|:------:|:------------|
| cascade_reversal | +1.40% | 9/9 (100%) | Perfecta |
| breadth_contraction_exit | **+1.62%** | 6/9 (67%) | Buena |

Claude clasificó cascade como TIER 1 y breadth como TIER 2. Es correcto por consistencia (9/9 vs 6/9), pero no mencionó que **breadth_contraction_exit tiene el edge absoluto más alto del catálogo** (+1.62%) con N=452 masivo. Es una señal complementaria valiosa, no un "contribuyente menor."

---

## PUNTO CIEGO 6 — pcr_put_panic: el mono-celda eligió N=3 (diamante), no N=48

Claude clasificó pcr_put_panic como TIER 2 basado en `zz50|BAJA` (N=48, OOS=+0.28%). Pero no mencionó que **el mono-celda original eligió `zz75|ALZA` con N=3, IS=+7.67%** — un diamante con edge inflado que no se repitió OOS. El multi-celda corrige esto al elegir la celda con N=48 (robusta).

Esto es contexto importante porque explica por qué el mono-celda declaró pcr_put_panic como "inestable" — no porque la señal sea mala, sino porque eligió una celda de N=3.

---

## PUNTO CIEGO 7 — No explicitó que el multi-celda elimina el sesgo de posición

El bug fundamental del mono-celda era: elegir la celda con mayor edge IS, que a menudo tenía N pequeño (diamante), y fallar OOS. El multi-celda corrige esto al probar TODAS las celdas con N≥10 y edge>0.

Claude lo menciona implícitamente en §1 pero no lo explicita como la corrección arquitectónica que es. Esto es importante para que cualquier agente futuro entienda por qué el mono-celda estaba mal.

---

## TABLA DE CORRECCIONES

| # | Punto ciego | Severidad | Corrección requerida |
|:-:|:------------|:---------:|:---------------------|
| 1 | Bonferroni genérico (6 celdas) | 🟡 Baja | Documentar que α es señal-dependiente |
| 2 | Score bug también aplica a cascade | 🟡 Baja | Mismo fix que Claude propuso |
| 3 | Sign-test con <5 folds no es válido | 🟡 Media | vvix_entry: "PENDIENTE — insuficientes folds" |
| 4 | No mencionó baseline limpio (P5) | ⚪ Informativo | Agregar nota |
| 5 | breadth_contraction tiene edge mayor | ⚪ Informativo | Mencionar edge absoluto |
| 6 | pcr: mono-celda eligió N=3, no N=48 | 🟡 Media | Documentar contexto |
| 7 | No explicitó corrección arquitectónica | ⚪ Informativo | Explicitar: "el multi-celda elimina el sesgo de posición" |

---

## FORMATO DE ENTREGA

1. Auditoría actualizada con los 7 puntos ciegos incorporados
2. Mantener la estructura TIER 1-4 (es correcta)
3. Agregar nota sobre folds insuficientes para vvix_entry
4. Agregar nota sobre el baseline limpio (P5) como fortaleza del diseño
5. Agregar contexto de N=3 vs N=48 en pcr_put_panic
6. Firma del modelo y fecha