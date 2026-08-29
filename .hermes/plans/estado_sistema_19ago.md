# Estado del Sistema — 19-Ago-2026

## 1. UBICACIÓN DE ARCHIVOS REORGANIZADOS

### docs/research/ (taxonomía Clean)
```
01_señales_entry_exit/     → 4 análisis .md + 20 JSONs de medición
   ├── analisis_señales_exit.md         (ENTRY/EXIT classification)
   ├── analisis_estadistico_profundo.md (marco ED, precursores, sign-flips)
   ├── replanteamiento_señales_exit.md  (replanteamiento post-análisis)
   ├── wins_losses_entry4_7_REPORT.md   (reporte wins/losses)
   └── medicion_*.json                  (20 JSONs de medición individual)

04_conjuncion_multi_est/   → Conjunción Multi-Estación (S5 + VIX + SV5 + Timing)
08_versioned_benchmarks/   → Validación OOS de Regímenes
11_experimental_engines/   → Clasificador de Secuencias CAT1→2→3
```

### backend/modules/entry_decision/references/ (documentación técnica)
```
cascade-conviction.md    → Análisis estadístico profundo (marco ED, precursores)
señales-exit.md          → Taxonomía de señales de EXIT
```

### .hermes/ (privado, comunicación tú-yo)
```
plans/                   → 20 planes de especificación
prompts/                 → 12 prompts enviados a Gemini
```

### scratch/ (solo scripts, sin .md)
```
medir_senal.py           → Arnés de medición (1020 líneas, 13+7 señales)
forense_precursores.py   → Forense de precursores de crash
```

---

## 2. SEÑALES — ESTADO ACTUAL (20 señales medidas)

### ENTRY (12 señales, edge positivo)
| Señal | N | Forward | WR | CI95 | Veredicto |
|-------|---|---------|-----|------|-----------|
| credit_easing_k1 | 112 | +5.19% | 93.8% | [+4.41%, +6.01%] | ✅ ESTRELLA |
| pcr_put_panic | 70 | +2.70% | 71.4% | [+1.13%, +4.24%] | ⚠️ MONITOREAR |
| vvix_entry | 91 | +1.70% | 62.6% | [+0.19%, +3.24%] | ✅ MANTENER |
| fg_extreme_fear | 54 | +1.58% | 68.5% | [-0.33%, +3.39%] | ✅ MANTENER |
| panico_total | 34 | +1.49% | 58.8% | [-0.49%, +3.51%] | ⚠️ REVISAR |
| bsi_washed_out | 161 | +1.42% | 65.8% | [+0.25%, +2.55%] | ✅ MANTENER |
| capitulacion | 82 | +1.40% | 65.9% | [-0.46%, +3.29%] | ✅ MANTENER |
| credit_stress | 215 | +1.00% | 54.9% | [+0.08%, +1.94%] | ⚠️ FILTRAR |
| sorpresa_total | 525 | +0.83% | 54.9% | [+0.18%, +1.48%] | ⚠️ DÉBIL |
| vix_crisis_spike | 171 | +0.75% | 56.7% | [-0.45%, +1.94%] | ⚠️ DÉBIL |
| pcr_panic_exit | 70 | +2.70% | 71.4% | — | ❌ DUPLICADO |
| credit_stress_exit | 215 | +1.00% | 54.9% | — | ❌ DUPLICADO |

### EXIT (2 señales, edge negativo)
| Señal | N | Forward | WR | CI95 | Veredicto |
|-------|---|---------|-----|------|-----------|
| bsi_recovery | 324 | -1.63% | 29.0% | [-2.17%, -1.10%] | ✅ EFECTIVA |
| euforia | 41 | -2.99% | 14.6% | [-3.98%, -1.81%] | ✅ EFECTIVA |

### NEUTRAS (5 señales, edge ~0)
| Señal | N | Forward | WR | Veredicto |
|-------|---|---------|-----|-----------|
| cascade_reversal | 0 | 0.00% | 0% | ❌ ROTA (bug) |
| dxy_bearish | 35 | -0.04% | 45.7% | 🔴 RETIRAR |
| sub_reaccion | 667 | +0.39% | 50.2% | 🔴 RETIRAR |
| fg_extreme_greed | 31 | -1.92% | 19.4% | ✅ TOPE (EXIT) |
| skew_paranoia_exit | 26 | -0.38% | 46.2% | ⚠️ DÉBIL |

---

## 3. HALLAZGOS CLAVE (17-Ago a 19-Ago)

### Marco corregido
- **Antes:** "¿Cuánto gana esta señal?" (edge ofensivo)
- **Ahora:** "¿Cuánto DEJA DE PERDER si se retira a tiempo?" (edge defensivo)
- **Rareza = Riqueza:** Eventos con N_lose bajo = MÁS valiosos (61.6% del total)

### Señales de EXIT
- Solo 2 EXIT efectivas: bsi_recovery (-1.63%), euforia (-2.99%)
- Las señales de "pánico" (vix crisis, credit stress, pcr panic) son ENTRY (comprar miedo), NO EXIT
- **Gap crítico:** Necesitamos desarrollar 3-5 señales de EXIT adicionales

### Precursores de crash
- credit.D2=ACCELERATING_UP_3D es precursor universal (5/6 señales, lift 4.1×)
- 61.6% de precursores tienen N_lose 3-4 (los más valiosos por rareza)

### Bugs corregidos
- Bug 1: Anticipación Temporal (mide autocorrelación, no días reales) → CORREGIDO
- Bug 2: Capture Ratio → NO EXISTE (código ya usa abs())

---

## 4. PENDIENTES PRIORIZADOS

| # | Tema | Prioridad | Estado |
|---|------|-----------|--------|
| 1 | Desarrollar señales de EXIT (faltan 3-5) | P1 | 🔄 En análisis |
| 2 | Backtest OOS del sistema completo | P1 | ❌ No iniciado |
| 3 | Modelar costos de transacción | P2 | ❌ No iniciado |
| 4 | Equity curve compuesta | P2 | ❌ No iniciado |
| 5 | Corrección multiplicidad (21,150 estados) | P2 | ❌ No iniciado |
| 6 | Clasificador de regímenes (árbol CAT → hoja) | P3 | ❌ No iniciado |
| 7 | Bitácora + evaluador + aprendiz | P4 | ❌ No iniciado |
| 8 | Mover archivos de directorios antiguos a nueva taxonomía | P4 | 🔄 En progreso |
| 9 | Eliminar señales duplicadas (pcr_panic_exit, credit_stress_exit) | P4 | ❌ No iniciado |