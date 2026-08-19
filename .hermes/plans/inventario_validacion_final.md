# INVENTARIO DE SEÑALES — Validación estadística obligatoria

> **Regla de oro:** Ningún umbral numérico ni etiqueta se expone sin su
> probabilidad + CI95 + N. Un 58% = 42% en contra — el agente debe verlo.

---

## SEÑALES CON ERROR BINARIO (pendientes de validar)

### 1. s5_sv5_conviction ❌
- Etiquetas: "RALLY_CON_CONVICCIÓN" sin p/CI95/N
- Fix: validar 4 cuadrantes contra %bear + %cascade, bootstrap CI95

### 2. cross_signals (6 señales) ❌
- "EXTREME_TERRITORY_ALERT" (rarity >= 0.6)
- "CASCADE_HIGH_CONVICTION" (tercile == t3_high)
- "INSTITUTIONAL_DISTRIBUTION_BATTLE" (sv5 > 12.0) ← ¿de dónde 12.0?
- "FLOOR_NOT_CONFIRMED__SV5_VETO"
- "CONFIRMED_BUYABLE_DIP"
- "D1_BEARISH_CONVERGENCE" (bear_ratio >= 0.50)
- Fix: cada umbral → medir hit-rate del outcome que predice

### 3. unified_guidance ❌
- STK_BUY_DIP_TACTICAL / STK_TRIM_TACTICAL / STK_HOLD_STABLE / STK_ACCUMULATE_STRUCTURAL
- Fix: hit-rate de cada acción, CI95

### 4. guidance_horizon ❌
- 1D/3D/5D/WAIT — ¿validado contra horizonte real?

### 5. D1_BEARISH_BINS / BULLISH_BINS (individuales) ⚠️
- Mapeo +1/-1 duro por bin (agregado sí validado IC +0.41)
- Fix: hit-rate direccional por cada bin individual

### 6. operational_guidance (fact stores) ❌
- STK_* labels hardcodeados en cada fact store

### 7. SIGMET hazards ⚠️
- VIX >= 28, SKEW >= 145, SV5T > 10 — umbrales fijos
- Fix: ¿cada umbral predice el hazard con qué probabilidad?

---

## SEÑALES YA VALIDADAS ✅

| Señal | Validación |
|---|---|
| cascade_conviction | IC +0.41, PBO=0%, CI95 [+0.37,+0.45] |
| DirectionalStateVector.p_bull | OOS IC -0.31 |
| DirectionalStateVector.confidence | D3 vol, bootstrap 99% |
| TAFEntry | p_direction + N + confidence_tier |
| reliability_factor(N) | basado en N |

---

## MÉTODO DE VALIDACIÓN (por señal)

1. Medir contra target (dirección/cascade/duración/horizonte)
2. Walk-forward OOS (26 folds)
3. Bootstrap CI95 (2000 iter)
4. Documentar p + CI95 + N + p-value
5. Exponer con confidence: HIGH (N≥30) | MODERATE (N≥10) | LOW (N<10)
