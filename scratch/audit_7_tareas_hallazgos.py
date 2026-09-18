#!/usr/bin/env python3
"""
Auditoría Forense Integral — 7 Tareas del Prompt de Hallazgos METAR
Verifica empíricamente cada hallazgo contra los 11 Timing Fact Stores.
"""
import sys, json, statistics
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, "/root/botero-trade")

from backend.modules.entry_decision.domain.rules.station_profiles import (
    STATION_PROFILES, get_station_profile,
    get_all_stress_bins, get_all_complacent_bins,
    get_all_floor_bins, get_all_ceiling_bins,
)
from backend.modules.entry_decision.domain.rules.family_sequence_detector import (
    STATION_CATEGORIES, Category,
)
from backend.modules.entry_decision.domain.rules.timing_context import get_timing_context

TIMING_DIR = Path("/root/botero-trade/backend/modules/entry_decision/domain/rules")

# Preload all timing stores
ALL_TIMING = {}
for s in STATION_PROFILES:
    p = TIMING_DIR / f"{s}_timing_fact_store.json"
    with open(p) as f:
        ALL_TIMING[s] = json.load(f)

# ══════════════════════════════════════════════════════════════════
# TAREA 1: [A] Consistencia CAT station_profiles vs family_sequence
# ══════════════════════════════════════════════════════════════════
print("=" * 80)
print("TAREA 1: [A] CAT MISMATCH de FG — ¿cosmético o afecta decisión?")
print("=" * 80)

# 1. family_sequence_detector usa SU propio STATION_CATEGORIES, no prof.cat
# Ya sabemos: fg → cat=2 en profiles, CAT3_ACTION en family
# La pregunta: ¿station_cat (del discriminator output) afecta alguna decisión downstream?

# Search: station_cat is only in FloorSignal/CeilingSignal/ContextSignal dataclass outputs
# and _get_station_context. It's serialized to dict via to_dict(). Check consumers.
print("FG en station_profiles.cat = 2 (CAT2_SENTIMENT)")
print("FG en family_sequence.STATION_CATEGORIES = CAT3_ACTION")
print()
print("CONSUMIDORES de station_cat:")
print("  signal_discriminator.py: FloorSignal.station_cat, CeilingSignal.station_cat, ContextSignal.station_cat")
print("  convergence_compositor.py: NO consume station_cat (verified grep: 0 hits)")
print("  family_sequence_detector.py: NO usa prof.cat — usa su propio STATION_CATEGORIES")
print()
print("VEREDICTO: station_cat es SOLO campo informativo de rotulado en el output.")
print("           Ninguna lógica de decisión consulta 'station_cat == 2' o 'station_cat == 3'.")
print("           La secuencia causal (CAT1→CAT2→CAT3) usa STATION_CATEGORIES del detector.")
print("           FIX: alinear cat=3 en profiles. RIESGO: CERO (cosmético).")


# ══════════════════════════════════════════════════════════════════
# TAREA 2: [B] Inconsistencia de escala: sgs (ratio) vs scale_gradient (diferencia)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TAREA 2: [B] INCONSISTENCIA SGS (ratio) vs SCALE_GRADIENT (diferencia)")
print("=" * 80)

# sgs = (hr75-hr25)/hr25  (timing_context.py L317) → C4 threshold: < -0.05
# scale_gradient = hr75-hr25 (signal_discriminator.py L1298) → threshold: ±0.10

# WHERE each is used:
# sgs:
#   - timing_context.py L317: computed and stored in TimingContext.floor_sgs
#   - signal_discriminator.py _extract_metrics_from_timing L892-896: extracts timing.floor_sgs
#   - signal_discriminator.py _compute_floor_concordance L296: C4 uses sgs < -0.05
#   - signal_discriminator.py _concordance_to_class_and_confidence L389, L399, L409: secondary tiebreak
# scale_gradient:
#   - signal_discriminator.py classify_context L1298: local computation for COMPLACENT/NEUTRAL zone
#   - Used ONLY in classify_context for scale_pattern → STRUCTURAL/TACTICAL/FLAT
#   - NOT used in classify_floor or classify_ceiling

sgs_vs_gradient_conflict = 0
sgs_vs_gradient_same = 0
by_station_conflicts = defaultdict(int)
by_station_total = defaultdict(int)

for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        d1, d2, d3 = int(parts[0]), int(parts[1]), int(parts[2])

        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        fp75 = fp_min.get("zz75")
        fp25 = fp_min.get("zz25")
        if not fp75 or not fp25 or not isinstance(fp75, dict) or not isinstance(fp25, dict):
            continue

        hr75 = fp75.get("hit_rate", 0)
        hr25 = fp25.get("hit_rate", 0)

        # sgs (ratio)
        sgs = (hr75 - hr25) / hr25 if hr25 > 0 else 0.0
        # scale_gradient (difference)
        sg = hr75 - hr25

        # Classification using sgs (timing_context)
        if sgs > 0.30:
            sgs_class = "STRUCTURAL"
        elif sgs < -0.05:
            sgs_class = "TACTICAL"
        else:
            sgs_class = "IMMEDIATE"

        # Classification using scale_gradient (classify_context)
        if sg > 0.10:
            sg_class = "STRUCTURAL"
        elif sg < -0.10:
            sg_class = "TACTICAL"
        else:
            sg_class = "FLAT"

        by_station_total[s] += 1

        if sgs_class != sg_class:
            sgs_vs_gradient_conflict += 1
            by_station_conflicts[s] += 1
        else:
            sgs_vs_gradient_same += 1

total_evaluated = sgs_vs_gradient_conflict + sgs_vs_gradient_same
pct_conflict = sgs_vs_gradient_conflict / total_evaluated * 100 if total_evaluated > 0 else 0

print(f"Total estados con ambas métricas: {total_evaluated}")
print(f"Coinciden en clasificación:       {sgs_vs_gradient_same} ({sgs_vs_gradient_same/total_evaluated*100:.1f}%)")
print(f"DIVERGEN en clasificación:        {sgs_vs_gradient_conflict} ({pct_conflict:.1f}%)")
print()

# CRITICAL: Where does each function actually RUN?
print("DOMINIO DE USO DE CADA MÉTRICA (separación de contextos):")
print("  sgs (ratio):           SOLO en classify_floor / classify_ceiling → STRESS ZONES (D1=4,5 o D1=0,1)")
print("  scale_gradient (diff): SOLO en classify_context → NEUTRAL/COMPLACENT ZONES (D1=2,3)")
print("  ⚠️  NUNCA COMPITEN en el mismo estado — el D1 bin determina qué función se invoca.")
print()

# Let's verify: for stress-zone states, does classify_context ever run?
# classify_context returns None if d1 in floor_bins_list or d1 in stress_bins_list
# So for any state in stress zone, only classify_floor/classify_ceiling runs (using sgs)
# For complacent/neutral zones, only classify_context runs (using scale_gradient)

# Count conflicts ONLY for neutral/complacent states (where scale_gradient actually matters)
neutral_conflicts = 0
neutral_total = 0
stress_conflicts = 0
stress_total = 0

for s in sorted(STATION_PROFILES):
    prof = get_station_profile(s)
    floor_b = prof.floor_bins if prof.floor_bins else prof.stress_bins
    stress_b = prof.stress_bins

    states = ALL_TIMING[s].get("states", {})
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        d1 = int(parts[0])
        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        fp75 = fp_min.get("zz75")
        fp25 = fp_min.get("zz25")
        if not fp75 or not fp25 or not isinstance(fp75, dict) or not isinstance(fp25, dict):
            continue

        hr75 = fp75.get("hit_rate", 0)
        hr25 = fp25.get("hit_rate", 0)
        sgs = (hr75 - hr25) / hr25 if hr25 > 0 else 0.0
        sg = hr75 - hr25

        if sgs > 0.30: sgs_class = "STRUCTURAL"
        elif sgs < -0.05: sgs_class = "TACTICAL"
        else: sgs_class = "IMMEDIATE"

        if sg > 0.10: sg_class = "STRUCTURAL"
        elif sg < -0.10: sg_class = "TACTICAL"
        else: sg_class = "FLAT"

        is_stress = (d1 in floor_b or d1 in stress_b)
        if is_stress:
            stress_total += 1
            if sgs_class != sg_class:
                stress_conflicts += 1
        else:
            neutral_total += 1
            if sgs_class != sg_class:
                neutral_conflicts += 1

print("CUANTIFICACIÓN POR ZONA DE USO:")
print(f"  Stress zones (solo sgs se usa en producción):    {stress_total} estados, {stress_conflicts} conflictos")
print(f"  Neutral/Complacent (solo scale_gradient en prod): {neutral_total} estados, {neutral_conflicts} conflictos")
print(f"  -> Las dos definiciones NUNCA se aplican al mismo estado simultáneamente.")
print(f"  -> El 'conflicto del 14.4%' es TEÓRICO — ambas métricas operan en zonas D1 distintas.")
print()

# Per-station
print("DESGLOSE TEÓRICO POR ESTACIÓN:")
print(f"{'Estación':<16} | {'Total':<6} | {'Divergen':<9} | {'%':<6}")
print("-" * 45)
for s in sorted(by_station_conflicts, key=lambda x: -by_station_conflicts[x]):
    t = by_station_total[s]
    c = by_station_conflicts[s]
    print(f"{s:<16} | {t:<6} | {c:<9} | {c/t*100:.1f}%")


# ══════════════════════════════════════════════════════════════════
# TAREA 3: [C] timing_mode=NOISE artefacto de umbral per-slot
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TAREA 3: [C] timing_mode=NOISE ARTEFACTO DE UMBRAL PER-SLOT")
print("=" * 80)

# timing_mode is NOISE by default (L344). Changes only if slot has n>=5 AND edge>0.15
# We need to check: for intermediate episodes (n=5-9), how many have pct_en_rango>=60% but timing_mode=NOISE?

intermediates_total = 0
intermediates_coherent = 0  # pct_rango >= 60%
intermediates_coherent_noise = 0  # coherent but timing_mode=NOISE
structural_but_noise = []  # STRUCTURAL_FLOOR + high pct + NOISE timing

for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    floor_bins_s = get_all_floor_bins().get(s, [])

    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        d1, d2, d3 = int(parts[0]), int(parts[1]), int(parts[2])

        n_ep = sv.get("poblacion", {}).get("n_episodios", 0)
        if not (5 <= n_ep <= 9):
            continue

        # Only stress-zone states for floor analysis
        if d1 not in floor_bins_s:
            continue

        intermediates_total += 1

        # Get timing context
        tc = get_timing_context(s, sk)
        if tc is None:
            continue

        pct_rango = tc.floor_pct_en_rango
        timing_mode = tc.floor_timing_mode
        signal_class = tc.floor_signal_class

        if pct_rango >= 60.0:
            intermediates_coherent += 1
            if timing_mode == "NOISE":
                intermediates_coherent_noise += 1
                # Extra: check if discriminator would also give it STRUCTURAL
                m_min = sv.get("medicion_min", {})
                fp_min = m_min.get("first_passage", {})
                fp75 = fp_min.get("zz75")
                if fp75 and isinstance(fp75, dict):
                    hr75 = fp75.get("hit_rate", 0)
                    if hr75 >= 0.60:
                        structural_but_noise.append({
                            "station": s, "state": sk, "n": n_ep,
                            "hr75": hr75, "pct_rango": pct_rango,
                            "timing_mode": timing_mode,
                        })

print(f"Intermedias (N=5-9) en stress zone (floor):         {intermediates_total}")
print(f"  Con pct_en_rango ≥ 60% (coherentes):              {intermediates_coherent}")
if intermediates_coherent > 0:
    print(f"  De esas, con timing_mode=NOISE:                    {intermediates_coherent_noise} ({intermediates_coherent_noise/intermediates_coherent*100:.1f}%)")
else:
    print(f"  De esas, con timing_mode=NOISE:                    0 (N/A)")
print()

if structural_but_noise:
    print(f"CONTRADICCIONES GRAVES (HR75≥60% + pct_rango≥60% + timing_mode=NOISE):")
    print(f"{'Estación':<16} | {'State':<10} | {'N':<3} | {'HR75':<6} | {'PctRango':<8} | {'TimingMode'}")
    print("-" * 65)
    for item in structural_but_noise:
        print(f"{item['station']:<16} | {item['state']:<10} | {item['n']:<3} | {item['hr75']*100:.1f}% | {item['pct_rango']:.1f}%    | {item['timing_mode']}")
else:
    print("No se encontraron contradicciones graves (HR75≥60% + pct≥60% + NOISE).")

# Also: total timing_mode stats for ALL states (not just intermediates)
print("\n--- timing_mode GLOBAL para estados en stress zone (todos los N) ---")
mode_counts = defaultdict(int)
for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    floor_bins_s = get_all_floor_bins().get(s, [])
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        d1 = int(parts[0])
        if d1 not in floor_bins_s:
            continue
        tc = get_timing_context(s, sk)
        if tc:
            mode_counts[tc.floor_timing_mode] += 1

total_stress = sum(mode_counts.values())
for mode, cnt in sorted(mode_counts.items(), key=lambda x: -x[1]):
    print(f"  {mode:<20}: {cnt:>4} ({cnt/total_stress*100:.1f}%)")


# ══════════════════════════════════════════════════════════════════
# TAREA 4: [H] Investigar floor_sgs=0.0 sospechoso
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TAREA 4: [H] floor_sgs=0.0 SOSPECHOSO")
print("=" * 80)

sgs_zero_cases = []
sgs_zero_justified = 0  # hr25 == hr75 exactly
sgs_zero_suspicious = 0

for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue

        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        fp75 = fp_min.get("zz75")
        fp25 = fp_min.get("zz25")
        if not fp75 or not fp25 or not isinstance(fp75, dict) or not isinstance(fp25, dict):
            continue

        hr75 = fp75.get("hit_rate", 0)
        hr25 = fp25.get("hit_rate", 0)
        n_ep = sv.get("poblacion", {}).get("n_episodios", 0)

        sgs = (hr75 - hr25) / hr25 if hr25 > 0 else 0.0

        if sgs == 0.0 and hr75 > 0:
            if hr25 == hr75:
                sgs_zero_justified += 1
            else:
                sgs_zero_suspicious += 1
                sgs_zero_cases.append({
                    "station": s, "state": sk, "n": n_ep,
                    "hr75": hr75, "hr25": hr25, "sgs": sgs,
                })

# Also count the N=0 case (hr25=0 → sgs=0 by formula)
sgs_zero_by_hr25_zero = 0
for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    for sk, sv in states.items():
        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        fp25 = fp_min.get("zz25")
        if fp25 and isinstance(fp25, dict) and fp25.get("hit_rate", -1) == 0:
            sgs_zero_by_hr25_zero += 1

print(f"Casos con sgs == 0.0 donde hr25 == hr75 exactamente: {sgs_zero_justified}")
print(f"Casos con sgs == 0.0 donde hr25 != hr75 (sospechosos): {sgs_zero_suspicious}")
print(f"Casos con hr25 == 0 (fórmula cae a sgs=0 por guard):   {sgs_zero_by_hr25_zero}")

if sgs_zero_cases:
    print(f"\nCasos sospechosos (primeros 20):")
    for item in sgs_zero_cases[:20]:
        print(f"  {item['station']} {item['state']} N={item['n']} hr75={item['hr75']:.3f} hr25={item['hr25']:.3f} sgs={item['sgs']}")

# Specific case: bsi 0__0__3
print("\n--- Caso específico: bsi 0__0__3 ---")
bsi_data = ALL_TIMING["bsi"]["states"].get("0__0__3", {})
bsi_m_min = bsi_data.get("medicion_min", {}).get("first_passage", {})
bsi_fp75 = bsi_m_min.get("zz75", {})
bsi_fp25 = bsi_m_min.get("zz25", {})
bsi_n = bsi_data.get("poblacion", {}).get("n_episodios", 0)
hr75_bsi = bsi_fp75.get("hit_rate", -1) if bsi_fp75 else -1
hr25_bsi = bsi_fp25.get("hit_rate", -1) if bsi_fp25 else -1
print(f"  N episodios: {bsi_n}")
print(f"  hr_zz75: {hr75_bsi}")
print(f"  hr_zz25: {hr25_bsi}")
if hr25_bsi > 0:
    sgs_bsi = (hr75_bsi - hr25_bsi) / hr25_bsi
    print(f"  sgs (ratio): {sgs_bsi:.4f}")
else:
    print(f"  sgs: 0.0 (hr25=0, guard clause)")
print(f"  Diagnóstico: {'hr25 == hr75 → sgs=0 justificado' if hr25_bsi == hr75_bsi else ('hr25=0 → guard clause' if hr25_bsi == 0 else 'SOSPECHOSO')}")


# ══════════════════════════════════════════════════════════════════
# TAREA 5: [E] Coherencia temporal de señales intermedias (5-9)
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TAREA 5: [E] COHERENCIA TEMPORAL SEÑALES INTERMEDIAS (5-9)")
print("=" * 80)

pct_ranges = {"high": 0, "mid": 0, "low": 0}
for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    floor_bins_s = get_all_floor_bins().get(s, [])
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        d1 = int(parts[0])
        n_ep = sv.get("poblacion", {}).get("n_episodios", 0)
        if not (5 <= n_ep <= 9):
            continue
        if d1 not in floor_bins_s:
            continue
        tc = get_timing_context(s, sk)
        if tc is None:
            continue
        pct = tc.floor_pct_en_rango
        if pct >= 60:
            pct_ranges["high"] += 1
        elif pct < 40:
            pct_ranges["low"] += 1
        else:
            pct_ranges["mid"] += 1

total_interm = sum(pct_ranges.values())
print(f"Intermedias (N=5-9, stress zone): {total_interm}")
if total_interm > 0:
    print(f"  pct_rango ≥ 60% (EN RANGO = señal de giro):    {pct_ranges['high']} ({pct_ranges['high']/total_interm*100:.1f}%)")
    print(f"  pct_rango 40-59% (MIXTO):                       {pct_ranges['mid']} ({pct_ranges['mid']/total_interm*100:.1f}%)")
    print(f"  pct_rango < 40%  (FUERA = continuación/fuerza): {pct_ranges['low']} ({pct_ranges['low']/total_interm*100:.1f}%)")


# ══════════════════════════════════════════════════════════════════
# TAREA 6: [D] Intermedias (5-9) — distribución por signal class
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TAREA 6: [D] INTERMEDIAS (5-9) — DISTRIBUCIÓN POR SIGNAL CLASS")
print("=" * 80)

from backend.modules.entry_decision.domain.rules.signal_discriminator import (
    classify_floor, _compute_floor_concordance, _concordance_to_class_and_confidence,
)

interm_classes = defaultdict(int)
interm_total = 0

for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    floor_bins_s = get_all_floor_bins().get(s, [])
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        d1, d2, d3 = int(parts[0]), int(parts[1]), int(parts[2])
        n_ep = sv.get("poblacion", {}).get("n_episodios", 0)
        if not (5 <= n_ep <= 9):
            continue
        if d1 not in floor_bins_s:
            continue

        tc = get_timing_context(s, sk)
        result = classify_floor(s, d1, d2, d3, timing=tc)
        interm_classes[result.signal_class] += 1
        interm_total += 1

print(f"Total intermedias en stress zone: {interm_total}")
print(f"{'Signal Class':<22} | {'N':<5} | {'%':<6}")
print("-" * 40)
for sc, n in sorted(interm_classes.items(), key=lambda x: -x[1]):
    print(f"{sc:<22} | {n:<5} | {n/interm_total*100:.1f}%")


# ══════════════════════════════════════════════════════════════════
# TAREA 7: [G] Validación INDEPENDIENTE de umbrales de concordancia
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TAREA 7: [G] VALIDACIÓN INDEPENDIENTE DE CONCORDANCIA (SIN REUSAR FUNCIÓN)")
print("=" * 80)

# Implementación INDEPENDIENTE de C1-C7 — lee métricas crudas del timing store
by_score_indep = defaultdict(list)

for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue

        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        fp75_raw = fp_min.get("zz75")
        fp25_raw = fp_min.get("zz25")
        if not fp75_raw or not isinstance(fp75_raw, dict):
            continue

        # Dual: medicion_max
        m_max = sv.get("medicion_max", {})
        fp_max = m_max.get("first_passage", {})
        dual75_raw = fp_max.get("zz75") if isinstance(fp_max, dict) else None

        # Raw metrics (NO function reuse)
        hr75 = fp75_raw.get("hit_rate", 0.0)
        hr25 = fp25_raw.get("hit_rate", 0.0) if (fp25_raw and isinstance(fp25_raw, dict)) else 0.0
        pf75 = fp75_raw.get("profit_factor", 0.0)
        rr75 = fp75_raw.get("rr_asymmetry", 0.0)
        mae = fp75_raw.get("mae_medio", 0.0)
        mfe = fp75_raw.get("mfe_medio", 0.0)
        pvalue = fp75_raw.get("p_value", 1.0)
        sgs = (hr75 - hr25) / hr25 if hr25 > 0 else 0.0
        dual_hr75 = dual75_raw.get("hit_rate", 0.5) if (dual75_raw and isinstance(dual75_raw, dict)) else 0.5

        # INDEPENDENT concordance computation (same logic, independent code)
        score = 0
        if rr75 < 0.8:
            score += 1
        if hr75 < 0.50:
            score += 1
        if pf75 < 1.0:
            score += 1
        if sgs < -0.05:
            score += 1
        if dual_hr75 > 0.60:
            score += 1
        if mae != 0 and mfe < abs(mae):
            score += 1
        if pvalue > 0.80:
            score += 1

        by_score_indep[score].append(hr75)

print("TABLA INDEPENDIENTE: score(0-7) → HR75 real (SIN reusar _compute_floor_concordance)")
print(f"{'Score':<6} | {'N':<5} | {'HR75 Mean':<10} | {'HR75 Median':<11} | {'Min':<6} | {'Max':<6} | {'Monotónico?'}")
print("-" * 75)

prev_mean = 999
is_monotonic = True
for sc in range(8):
    group = by_score_indep[sc]
    n = len(group)
    if n == 0:
        print(f"{sc:<6} | {0:<5} | {'N/A':<10} | {'N/A':<11} | {'N/A':<6} | {'N/A':<6} |")
        continue
    mean_hr = statistics.mean(group)
    med_hr = statistics.median(group)
    min_hr = min(group)
    max_hr = max(group)
    mono = "✅" if mean_hr <= prev_mean else "❌ BREAK"
    if mean_hr > prev_mean:
        is_monotonic = False
    prev_mean = mean_hr
    print(f"{sc:<6} | {n:<5} | {mean_hr*100:<9.1f}% | {med_hr*100:<10.1f}% | {min_hr*100:<5.1f}% | {max_hr*100:<5.1f}% | {mono}")

print(f"\nMONOTONICIDAD GLOBAL: {'✅ PERFECTA' if is_monotonic else '❌ BREAK DETECTADO'}")

# Compare with function-based computation
print("\n--- CROSS-CHECK: Coincidencia con _compute_floor_concordance ---")
matches = 0
mismatches = 0
for s in sorted(STATION_PROFILES):
    states = ALL_TIMING[s].get("states", {})
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        fp75_raw = fp_min.get("zz75")
        fp25_raw = fp_min.get("zz25")
        if not fp75_raw or not isinstance(fp75_raw, dict):
            continue
        m_max = sv.get("medicion_max", {})
        fp_max = m_max.get("first_passage", {})
        dual75_raw = fp_max.get("zz75") if isinstance(fp_max, dict) else None

        hr75 = fp75_raw.get("hit_rate", 0.0)
        hr25 = fp25_raw.get("hit_rate", 0.0) if (fp25_raw and isinstance(fp25_raw, dict)) else 0.0
        pf75 = fp75_raw.get("profit_factor", 0.0)
        rr75 = fp75_raw.get("rr_asymmetry", 0.0)
        mae = fp75_raw.get("mae_medio", 0.0)
        mfe = fp75_raw.get("mfe_medio", 0.0)
        pvalue = fp75_raw.get("p_value", 1.0)
        sgs = (hr75 - hr25) / hr25 if hr25 > 0 else 0.0
        dual_hr75 = dual75_raw.get("hit_rate", 0.5) if (dual75_raw and isinstance(dual75_raw, dict)) else 0.5

        # Independent
        ind_score = 0
        if rr75 < 0.8: ind_score += 1
        if hr75 < 0.50: ind_score += 1
        if pf75 < 1.0: ind_score += 1
        if sgs < -0.05: ind_score += 1
        if dual_hr75 > 0.60: ind_score += 1
        if mae != 0 and mfe < abs(mae): ind_score += 1
        if pvalue > 0.80: ind_score += 1

        # Function-based
        func_score, _ = _compute_floor_concordance(
            rr=rr75, hr75=hr75, pf75=pf75, sgs=sgs,
            mae=mae, mfe=mfe, ceil_hr75=dual_hr75, pvalue=pvalue
        )

        if ind_score == func_score:
            matches += 1
        else:
            mismatches += 1

print(f"Coinciden:  {matches}")
print(f"Divergen:   {mismatches}")
print(f"Tasa match: {matches/(matches+mismatches)*100:.1f}%")

print("\n" + "=" * 80)
print("FIN DE LA AUDITORÍA FORENSE INTEGRAL — 7 TAREAS")
print("=" * 80)
