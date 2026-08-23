# ÁRBOLES DE DECISIÓN OPERACIONALES
## Integrando medición + precursores + momentum estructural

> Versión: 20-Ago-2026 (POST-LIMPIEZA)
> Fuentes: medir_senal.py + forense_precursores.py + validacion_5_interpretaciones_fact_store.md
> Cambios P0 20-Ago: vix_crisis_spike reclasificada ENTRY, 3 pares duplicados unificados, 2 señales degradadas a GRADO C

---

## REGLA DE ORO HH+EXIT (hallazgo 20-Ago-2026)

**Higher Highs en techos caen el 90.2%** de las veces (33 años SPY, N=429). Las señales EXIT solas no discriminan (LIFT ≈ baseline), pero combinadas con HH se vuelven casi determinísticas. **AMPLIFICAR siempre una señal EXIT cuando `structural_momentum.exit.p_hh > 0.55`.**

---

## ÁRBOL A: ENTRY (Señal de Compra)

```
¿Señal ENTRY activa? (medir_senal)
│
├─ NO → Esperar. Sin señal no se opera.
│
└─ SÍ → Consultar contexto:
    │
    ├─ ¿CI95 cruza cero? (activa.ci_mean)
    │   └─ SÍ → ABORTAR. Edge no confirmado estadísticamente.
    │
    ├─ ¿D2 = FAST_CRUSH_3D? (forense_precursores: sign flip)
    │   └─ SÍ → NO ENTRAR. El edge se INVIERTE en caída rápida.
    │       Ej: bsi_washed_out: FAST_CRUSH = −1.74% vs DECEL_DOWN = +5.17%
    │
    ├─ ¿D2 = ACCELERATING_UP_3D? (precursor universal #1)
    │   └─ SÍ → REDUCIR TAMAÑO 50%. Entrar solo si:
    │         - structural_momentum.entry.p_hl > 0.55
    │         - divergence_regime ≠ FULL_CONVERGENT_BEAR
    │
    ├─ ¿structural_momentum.entry.p_hl < 0.45? (ADDENDUM 1)
    │   └─ SÍ → Los pisos hacen Lower Lows (LL).
    │       → TRAMPA BAJISTA. NO ENTRAR aunque la señal diga que sí.
    │
    ├─ ¿prev_leg_context.pct_extreme > 20%? (ADDENDUM 2)
    │   └─ SÍ → Venimos de un crash (pierna previa >P90).
    │       → Edge AMPLIFICADO post-crash.
    │
    ├─ ¿divergence_regime = FULL_CONVERGENT_BULL? (ADDENDUM 3)
    │   └─ SÍ → Las 3 escalas confirman. TAMAÑO MÁXIMO.
    │
    └─ ¿divergence_regime = TACTICAL_ONLY?
        └─ SÍ → Funciona en zz25 pero NO escala. TAMAÑO REDUCIDO.
```

---

## ÁRBOL B: EXIT (Señal de Venta)

```
¿Señal EXIT activa? (medir_senal)
│
├─ NO → Mantener posiciones.
│
└─ SÍ → Consultar contexto:
    │
    ├─ ¿CI95 cruza cero? → ABORTAR.
    │
    ├─ ¿structural_momentum.exit.p_hh > 0.55? 🔴 REGLA DE ORO
    │   └─ SÍ → HH cae 90.2% (33 años SPY, N=429)
    │       → AMPLIFICAR la señal EXIT. SALIR 100%.
    │       → Aplica a: euforia (88% HH), fg_extreme_greed (88% HH),
    │         bsi_recovery (76% HH), stealth_tail_hedging (80% HH).
    │
    ├─ ¿Es euforia? (edge −2.99%, WR 14.6%, LIFT 1.211x)
    │   └─ SÍ → Techo más fuerte. SALIR 100%.
    │
    ├─ ¿Es fg_extreme_greed? (edge −1.92%, WR 19.4%, LIFT 1.107x)
    │   └─ SÍ → Codicia extrema. REDUCIR 70%.
    │
    ├─ ¿Es bsi_recovery? (edge −1.66%, WR 27.7%, LIFT 1.204x)
    │   └─ SÍ → Breadth saliendo de washed_out. REDUCIR 50%.
    │
    ├─ ¿Es stealth_tail_hedging? (💎 N=31, LIFT 1.206x)
    │   └─ SÍ → Diamante. P(cae)=100% en MAX. REDUCIR 30%.
    │
    ├─ ¿Es GRADO C? (credit_equity_divergence)
    │   └─ SÍ → LIFT≈1.0, no discrimina.
    │       → Solo operar si p_hh > 0.55. Si no, IGNORAR.
    │
    └─ ¿divergence_regime = FULL_CONVERGENT_BEAR?
        └─ SÍ → Las 3 escalas confirman. SALIR TODO.
```

---

## Tabla de Señales EXIT (8 activas + 1 GRADO C)

| Señal | Edge | WR | LIFT (MAX) | % HH | Acción |
|-------|------|-----|:----------:|:----:|--------|
| euforia | −2.99% | 14.6% | 1.211x | 88.2% | SALIR 100% |
| fg_extreme_greed | −1.92% | 19.4% | 1.107x | 88.0% | REDUCIR 70% |
| bsi_recovery | −1.66% | 27.7% | 1.204x | 76.2% | REDUCIR 50% |
| stealth_tail_hedging | −0.65% | 35.5% | 1.206x | 80.0% | 💎 REDUCIR 30% |
| skew_paranoia_exit | +2.84% neto | 69% | — | — | 💎 RESCATADA v6 (INDEP=71%) |
| credit_ease_exit | +1.54% neto | 53% | — | — | RESCATADA v6 (p=0.001) |
| breadth_contraction_exit | +0.84% neto | 49% | — | — | RESCATADA v6 (p=0.001) |
| credit_equity_divergence | −3.15% | 14.2% | 1.035x | 63.3% | GRADO C |

**EXIT retiradas (7):** regime_change_exit, sv5t_silent_distribution, defensive_rotation_divergence, vix_complacency_exit, credit_stress_exit, dxy_spike_exit, pcr_panic_exit.

> **Nota v6 (22-Ago-2026):** credit_ease_exit, breadth_contraction_exit y skew_paranoia_exit fueron rescatadas tras re-evaluación con el evaluador first-passage (v6). El método antiguo (lift pivote-a-pivote) las descartó por sesgo de estructura; el método nuevo confirma edge neto positivo y significativo.

## Tabla de Señales ENTRY (9 activas)

| Señal | Edge | WR | LIFT (MIN) | D2 Sign Flips | Condición |
|-------|------|-----|:----------:|---------------|-----------|
| credit_easing_k1 | +5.19% | 93.8% | 0.341x | FAST_CRUSH: NO ENTRAR | p_hl > 0.55 |
| pcr_put_panic | +2.70% | 71.4% | 1.304x | FAST_CRUSH: −2.19% | D2=STABLE_CONT |
| vvix_entry | +1.70% | 62.6% | 1.692x | — | cascade_50 > 60% |
| fg_extreme_fear | +1.58% | 68.5% | 1.034x | — | post-2010 |
| panico_total | +1.49% | 58.8% | 1.526x | — | 💎 N=34 |
| bsi_washed_out | +1.42% | 65.8% | 1.315x | FAST_CRUSH: −1.74% | D2=DECEL_DOWN |
| capitulacion | +1.40% | 65.9% | 1.326x | D3 VOL_EXP: −0.67% | D3=VOL_COMPR |
| credit_stress | +1.00% | 54.9% | 1.368x | — | duration > 2b |
| **vix_crisis_spike** | **+0.75%** | **56.7%** | **1.829x** | — | **RECLASIFICADA ENTRY 20-Ago** |

---

## Reglas de Cruce

| Sistema | Qué aporta | Cuándo usar |
|---------|-----------|-------------|
| medir_senal.py | Edge, WR, CI95, tríada, timing | Siempre: primer filtro |
| forense_precursores.py | D2/D3 sign flips, precursores universales | Segundo filtro |
| structural_momentum (ADDENDUM 1) | HL/LL, LH/HH **→ HH=90.2% cae** | Tercer filtro: timing y trampa |
| prev_leg_context (ADDENDUM 2) | Post-crash amplification | Cuarto filtro: sizing |
| divergence_regime (ADDENDUM 3) | Convergencia/divergencia | Quinto filtro: convicción |

## Correcciones Fácticas

1. **P1 (p_hl):** p_continuation y p_bull son ORTOGONALES (r=0.015)
2. **P2 (pct_extreme):** Umbral >50% es inalcanzable. Usar >20%
3. **P3 (divergence_regime):** CONCEPTO DERIVADO del fact store
4. **P4 (D2=ACCEL_UP + LL):** NO ENTRAR. Doble confirmación bajista.
5. **P5 (p_hh):** AMPLIFICAR EXIT. HH cae 90.2%.
6. **P6 (vix_crisis_spike):** RECLASIFICADA ENTRY. Edge +0.75% positivo.
7. **P7 (duplicados):** pcr_panic_exit, credit_stress_exit, dxy_spike_exit → RETIRADAS.

---
**Firma:** deepseek/deepseek-v4-pro (Hermes) · 20-Ago-2026