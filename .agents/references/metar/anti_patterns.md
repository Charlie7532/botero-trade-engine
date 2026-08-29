# METAR Anti-Patrones — Errores a NUNCA Repetir

> **Módulo de**: [fact_store_v3_architecture.md](file:///root/botero-trade/.agents/references/metar/fact_store_v3_architecture.md) §16
> **Status**: `MANDATORY` | **Last Update**: 29-Ago-2026
> **Scope**: Todo agente que trabaje con fact stores, señales METAR, o clasificación de estados

---

## Errores Documentados

1. **Usar `fwd_20d` o cualquier retorno a horizonte fijo como métrica causal.** Los retornos se miden con ZigZag (variable, adaptativo), no con ventanas fijas. `fwd_20d` mezcla múltiples piernas ZigZag y diluye la señal real. (Regla E.9).

2. **Confundir `p_bull` con un score de calidad.** `p_bull = 0.80` en un estado con `n=5` tiene menos valor que `p_bull = 0.55` con `n=500`. La calidad de una señal es `p_bull × n × (EV > 0)`, nunca `p_bull` aislado.

3. **Promediar métricas entre escalas ZigZag.** `zz25`, `zz50`, y `zz75` son escalas INDEPENDIENTES con horizontes y poblaciones distintos. Promediar `p_bull_zz25` y `p_bull_zz75` es promediar temperatura y presión — produce un número sin significado.

4. **Usar Bonferroni sobre el Protocolo §3.3.** El protocolo §3.3 ya tiene su marco propio (N≥30 + dossier cualitativo + CI95). Aplicar Bonferroni encima es sobre-corrección.

5. **Tratar señales EXIT como inversas de señales ENTRY.** Una señal EXIT no es "entrar en corto" — es "proteger una posición existente". Los umbrales, horizontes, y poblaciones son distintos.

6. **Inventar labels D1/D2/D3 en lugar de copiarlos de la fuente canónica.** El 29-Ago-2026 un agente inventó labels para 9/11 estaciones, invirtiendo físicamente el Credit (GFC 2008 → "DEEP_CREDIT_EASE"). **Siempre copiar de** [`d1_labels_canonical.md`](file:///root/botero-trade/.agents/references/metar/d1_labels_canonical.md).

7. **Ignorar el programa de overflow.** Una señal EXIT que dice "va a caer" sin medir si la caída escala de zz25 a zz50 y zz75 tiene valor operacional limitado. La cascada de overflow distingue un pullback de -3% de un crash de -15%.

8. **Comparar `panic_score` entre eras sin normalizar.** En 1995 solo había 5/11 estaciones activas. Un `panic_score = 3` en 1995 (de 5 posibles) es más extremo que en 2025 (de 7 posibles). Usar siempre `panic_score_pct` para comparaciones inter-temporales.

9. **Tratar estados ±2σ+ como estados normales sin verificar overflow.** Un `CRISIS_SPIKE` a +2.1σ no es lo mismo que uno a +8σ. Todo estado en bin 0 o bin 5 debe verificarse con `validate_overflow()`.

10. **Aplicar reglas estáticas sin considerar Wyckoff.** Señales degradadas como `bsi_recovery` y `regime_change_exit` son detectores de FASES institucionales (distribución y acumulación), no "ruido". Buscar siempre la dinámica entre pivotes.
