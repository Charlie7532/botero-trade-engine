# TAF Audit — ftt_days & ev_per_day (Capa 1)

**Fecha:** 2026-08-16 · **Autor:** Auditor Hermes (capa 1) · **Read-only:** no se modificó código de producción.

## 1. TAFEntry actual — qué expone

`convergence_compositor.py` líneas 214-232. 11 campos, **todos de `zigzag_kinematic.zz25`**:

| campo TAFEntry | origen fact store (`zz25`) |
|---|---|
| `station` | — |
| `scale` | hardcodeado `"zz25"` |
| `direction` | `p_bull >= p_bear` |
| `p_direction` | `max(p_bull, p_bear)` |
| `ev_pct` | `ev_net` |
| `e_days` | `e_days` |
| `e_ret_up` | `e_ret_max` |
| `e_ret_down` | `e_ret_min` |
| `rr_asymmetry` | `rr_asymmetry` |
| `n_samples` | `n_pos + n_neg` |
| `confidence` | `confidence_tier` |

## 2. `_build_taf_entry()` — verificación

**CORRECTO.** Lee `state.get("zigzag_kinematic", {}).get("zz25", {})` (la estructura rica con `n_pos`/`n_neg`, no la lean top-level `state["zz25"]`). El mapeo campo→campo es correcto. El dispatch usa `data.get("state_key")` del resultado de cada `*_metar_service`, que se genera con los `LookupAdapter` de producción → las claves coinciden con el fact store (verificado: match 100% en VIX/BSI/SKEW/Yield; 35.8% FG por gap pre-2010 ya conocido).

## 3. ftt_days y ev_per_day NO expuestos — CONFIRMADO

`zigzag_kinematic.zz25` (y zz50/zz75) contienen `ftt_bull_days`, `ftt_bear_days`, `ev_per_day`, `structural_momentum`, `prev_leg_domino`, `zigzag_pure_vault`. Ninguno está en `TAFEntry`.

Semántica (de `v3_fact_table_engine.py` líneas 167-176):
- `ftt_bull_days` = mediana de duración (bars) de piernas alcistas (MIN) en ese estado.
- `ftt_bear_days` = mediana de duración de piernas bajistas (MAX).
- `ev_per_day` = `ev_net_shrunk / max(e_days, 1.0)` → EV normalizado por horizonte (tasa diaria).

## 4. zz50 / zz75 NO expuestos — CONFIRMADO

`scale="zz25"` está hardcodeado. `zigzag_kinematic.zz50` y `.zz75` existen en los 108 estados de cada fact store con la misma estructura (sin `structural_momentum`/`prev_leg_domino`, que son zz25-only).

## 5. Señal predictiva sobre SPY forward (ρ, T-stat)

Dataset: `scratch/quants_obs.pkl` (1,590 pivotes SPY zz25, state_keys generados con los adapters de producción). Target = pierna zz25 que nace en el pivote. Spearman ρ con T-stat.

**Composite (media 11 estaciones):**

| señal → target | ρ | T-stat | p | n |
|---|---|---|---|---|
| ftt → duración (calibración) | **+0.551** | +26.29 | 0.0000 | 1590 |
| ftt → retorno/día | **+0.178** | +7.22 | 0.0000 | 1590 |
| ftt → retorno total pierna | **+0.206** | +8.39 | 0.0000 | 1590 |
| ev_per_day → retorno/día | **+0.330** | +13.90 | 0.0000 | 1590 |
| ev_per_day → retorno total | **+0.378** | +16.28 | 0.0000 | 1590 |
| e_days → duración (ya expuesto) | +0.516 | +24.01 | 0.0000 | 1590 |

**Per-station (ev_per_day → retorno total):** VIX +0.226, BSI +0.298, FG +0.234, Credit +0.145, Rotation +0.177, SV5T +0.133, SKEW +0.077, PCR +0.230, VVIX +0.186, Yield +0.141, DXY +0.094. Todos significativos (p<0.01), BSI y PCR y FG los más fuertes tras VIX.

**Multi-escala (composite, target = pierna zz25):**

| escala | ftt→dur | evpd→ret/día | evpd→ret total |
|---|---|---|---|
| zz25 | +0.551 (t=26.3) | +0.330 (t=13.9) | +0.378 (t=16.3) |
| zz50 | +0.301 (t=12.6) | +0.257 (t=10.6) | +0.278 (t=11.6) |
| zz75 | +0.142 (t=5.7) | +0.205 (t=8.4) | +0.228 (t=9.4) |

## 6. Recomendación

1. **Exponer en `TAFEntry` (zz25):** `ftt_bull_days`, `ftt_bear_days`, `ev_per_day`. Los tres con señal predictiva fuerte y significativa. `ev_per_day` NO es redundante con `ev_pct` (=`ev_net`): normaliza por horizonte y su ρ sobre ret/día (+0.33) es la tasa real. `ftt_bull`/`ftt_bear` capturan la asimetría direccional de duración que `e_days` (media de ambas) no da.

2. **Exponer multi-escala (zz50/zz75).** Cada escala tiene señal independiente y significativa (zz50 evpd→ret total +0.278, zz75 +0.228). Recomendación: cambiar `scale: str` por un dict `scales` con `{zz25, zz50, zz75}` anidando `p_direction, ev_net, e_days, ftt_bull_days, ftt_bear_days, ev_per_day, rr_asymmetry` por escala. Así el TAF entrega la **estructura temporal del EV** (term structure), no solo el horizonte zz25.

3. **Agregar consenso de ev_per_day y ftt al `TAFComposite`** (hoy solo `consensus_p_bull/ev_net/e_days`), espejo de lo que ya se hace con p_bull.

4. **Cuidado (no es señal nueva por artefacto):** el ftt→dur ρ=+0.55 es en parte mecánico (ftt es una mediana de duración del mismo estado). Su valor marginal sobre `e_days` (ya expuesto, ρ=+0.52) es la *asimetría bull/bear* de duración. El hallazgo central a explotar es `ev_per_day` (ρ +0.33 ret/día, +0.38 ret total) — tasa de EV por día, ortogonal a dirección.

5. **Cobertura:** FG (35.8%), Credit (57.5%), PCR (57.7%), VVIX (58.1%) tienen gaps pre-2010 ya documentados. Los campos nuevos heredarán esos gaps; no degradan la señal, solo reducen n.
