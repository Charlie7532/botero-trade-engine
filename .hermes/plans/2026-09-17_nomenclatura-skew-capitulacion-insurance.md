# Especificación de Nomenclatura SKEW — Taxonomía CBOE (capitulación → insurance peak)

> **Fecha:** 2026-09-17 · **Estado:** la polaridad ya está corregida en `station_profiles.py`
> (`polarity="INVERTED"` — verificado). **Pendiente: la NOMENCLATURA D1** en el generador + dossier.

---

## 1. Objetivo

Reemplazar la nomenclatura D1 actual de SKEW (**EXTREME_CONFIDENCE / CONFIDENCE / NEUTRAL_CONFIDENT /
NEUTRAL_PARANOID / PARANOIA / EXTREME_PARANOIA**) por la taxonomía física de opciones CBOE, alineada
con la **decantación debida** (bin0 = piso, bin5 = techo).

## 2. Justificación (fuente de la verdad — verificado, no relato)

La nomenclatura antigua invertía el significado: "EXTREME_CONFIDENCE" (bin0) suena a techo/complacencia,
pero empíricamente bin0 es **SUELO**. El SKEW index mide la inclinación de la COLA IZQUIERDA (puts) — es
**unilateral** (no hay "call overpriced" real en SKEW).

### Evidencia empírica (SKEW raw vs retorno forward SPY a 20d, lake continuo 2011-2026)

| bin | prob | rango SKEW | n | Fwd20% | WR | lectura |
|---|---|---|---|---|---|---|
| 0 | <2.28% | 110-114 | 89 | **+4.41%** | **91%** | 🟢 SUELO (capitulación; +11.5% con VIX≥30) |
| 1 | 2-16% | 114-119 | 529 | +1.45% | 67% | presión bajista cedió |
| 2 | 16-50% | 119-130 | 1331 | +0.68% | 64% | grind up |
| 3 | 50-84% | 130-144 | 1332 | +1.00% | 67% | neutral |
| 4 | 84-98% | 144-159 | 531 | +0.96% | 72% | transición (no discrimina bien) |
| 5 | >97.7% | 159-183 | 89 | **−0.20%** | 60% | 🔴 TECHO (sin rebote) |

Correlación Spearman SKEW↔Fwd20: **−0.044** (débil global — pero los extremos bin0/bin5 son los
puntos de giro determinantes; SKEW es un indicador de RARIDAD/cola, no de dirección continua).

### Recordatorio del mecanismo (Rule 24)
Los bins NO son σ paramétricos — son **percentiles empíricos gaussianos** (`[0.0228, 0.1587, 0.5000,
0.8413, 0.9772]`) computados con expanding rank sin look-ahead (`build_continuous_metar_lake.py`
`compute_series_expanding_z`). El eje σ es la ETIQUETA de los percentiles, no un supuesto de normalidad.

---

## 3. Nomenclatura DEFINITIVA (taxonomía aprobada)

| bin | Gaussiana (Prob) | Nomenclatura | Significado Físico en SKEW | Implicación de Mercado (Contrarian) |
|---|---|---|---|---|
| 0 | <-2σ (<2.28%) | **Put Capitulation** | Puts liquidados/monetizados tras una caída; prima de pánico se evapora | 🟢 **SUELO INMINENTE** (+4%/+11%) |
| 1 | [-2σ,-1σ) (2-16%) | **Hedge Unwind** | Desarme de coberturas; instituciones tomando beneficio de Puts | Fin de presión bajista; soporte formándose |
| 2 | [-1σ,0) (16-50%) | **Base Skew (-)** | Asimetría natural baja; costo de cobertura bajo histórico | Consolidación / grind up lento |
| 3 | [0,1σ) (50-84%) | **Base Skew (+)** | Asimetría natural alta; costo de cobertura ligeramente elevado | Mercado madurando; vulnerabilidad moderada |
| 4 | [1σ,2σ) (84-98%) | **Insurance Bid** | Aceleración de demanda de Puts OTM; MM encarecen cola izquierda | Distribución en ciernes (transición) |
| 5 | >2σ (>97.7%) | **Peak Insurance** | Puts OTM sobrepreciados; exceso de demanda de protección | 🔴 **TECHO INMINENTE** (sin rebote) |

**NOTAS FINAS (de la auditoría):**
- bin4 "Insurance Bid" tiene WR 72% (alto) — **no discrimina bien**; tratar como transición, no como
  señal direccional fuerte. No forzar claim de "distribución confirmada" ahí.
- SKEW es unilateral (cola put). No crear simetría put/call (no existe "call overpriced" real).

---

## 4. Cambios requeridos

| Archivo | Cambio |
|---|---|
| `backend/scripts/generators/generate_skew_fact_table.py` L19 | `D1_LABELS = ["Put Capitulation","Hedge Unwind","Base Skew (-)","Base Skew (+)","Insurance Bid","Peak Insurance"]` |
| `.agents/references/metar/d1_labels_canonical.md` L37 | Actualizar la fila SKEW con los nuevos labels |
| `.agents/references/metar/stations/skew_personalidad.md` | Actualizar §2.1 tabla D1 + §3 polaridad (mantener INVERTED) |
| Verificar `station_profiles.py` | `polarity="INVERTED"` ✓ ya correcto; **NO tocar** (si hay re-run del generador, confirmar que no revierte) |

---

## 5. Verificación de aceptación (Hermes audita)

- [ ] `grep D1_LABELS generate_skew_fact_table.py` → los 6 nuevos labels
- [ ] Ningún referencia residual a "EXTREME_CONFIDENCE"/"EXTREME_PARANOIA" en taxonomía SKEW
- [ ] `station_profiles.py` sigue `polarity="INVERTED"` tras regenerar
- [ ] Correr tests de taxonomía (`test_taxonomy_integrity.py` o equivalente) → sin rotura por SKEW
- [ ] Re-verificar bin0=+4% y bin5=−0.2% con un re-muestreo aleatorio (guarda contra drift)