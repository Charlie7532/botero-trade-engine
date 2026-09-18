#!/usr/bin/env python3
"""
Forense de Alineación y Puntos Ciegos — 3 Módulos de Dominio METAR
station_profiles.py + signal_discriminator.py + family_sequence_detector.py
Evaluado empíricamente contra los 11 Timing Fact Stores del Neon Vault / Fact Stores.
"""
import sys
import json
from pathlib import Path
from collections import defaultdict
import statistics

# Asegurar path
REPO_ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(REPO_ROOT))

from backend.modules.entry_decision.domain.rules.station_profiles import (
    STATION_PROFILES, get_station_profile,
    get_all_stress_bins, get_all_complacent_bins,
    get_all_floor_bins, get_all_ceiling_bins,
)
from backend.modules.entry_decision.domain.rules.family_sequence_detector import (
    STATION_CATEGORIES, Category,
    STATION_STRESS_BINS, STATION_COMPLACENT_BINS,
    STATION_FLOOR_BINS, STATION_CEILING_BINS,
)
from backend.modules.entry_decision.domain.rules.signal_discriminator import (
    STRESS_BINS, COMPLACENT_BINS, FLOOR_BINS, CEILING_BINS,
    _compute_floor_concordance, _compute_ceiling_concordance,
    _concordance_to_class_and_confidence,
    _load_rules, D2_LABELS, D3_LABELS,
)
from backend.modules.entry_decision.domain.rules.timing_context import get_timing_context

print("=" * 80)
print("AUDITORÍA FORENSE EMPÍRICA — ALINEACIÓN Y PUNTOS CIEGOS (5 TAREAS)")
print("=" * 80)

# ==============================================================================
# TAREA 1: VERIFICAR IDENTIDAD Y ALINEACIÓN ESTABLE
# ==============================================================================
print("\n" + "=" * 50)
print("TAREA 1: IDENTIDAD Y ALINEACIÓN ENTRE LOS 3 MÓDULOS")
print("=" * 50)

# 1.1 Estabilidad de Bins Canónicos
print("\n--- 1.1 Estabilidad de Bins Canónicos ---")
profiles_stress = get_all_stress_bins()
profiles_complacent = get_all_complacent_bins()
profiles_floor = get_all_floor_bins()
profiles_ceiling = get_all_ceiling_bins()

discr_stress_match = (STRESS_BINS == profiles_stress)
discr_compl_match = (COMPLACENT_BINS == profiles_complacent)
discr_floor_match = (FLOOR_BINS == profiles_floor)
discr_ceil_match = (CEILING_BINS == profiles_ceiling)

fam_stress_match = (STATION_STRESS_BINS == profiles_stress)
fam_compl_match = (STATION_COMPLACENT_BINS == profiles_complacent)
fam_floor_match = (STATION_FLOOR_BINS == profiles_floor)
fam_ceil_match = (STATION_CEILING_BINS == profiles_ceiling)

print(f"signal_discriminator STRESS_BINS == profiles:     {discr_stress_match}")
print(f"signal_discriminator COMPLACENT_BINS == profiles: {discr_compl_match}")
print(f"signal_discriminator FLOOR_BINS == profiles:      {discr_floor_match}")
print(f"signal_discriminator CEILING_BINS == profiles:    {discr_ceil_match}")
print(f"family_sequence STATION_STRESS_BINS == profiles:  {fam_stress_match}")
print(f"family_sequence STATION_COMPLACENT_BINS == profiles: {fam_compl_match}")
print(f"family_sequence STATION_FLOOR_BINS == profiles:   {fam_floor_match}")
print(f"family_sequence STATION_CEILING_BINS == profiles: {fam_ceil_match}")

# 1.2 Consistencia STATION_CATEGORIES vs cat en profiles
print("\n--- 1.2 Consistencia STATION_CATEGORIES vs cat en profiles ---")
cat_map = {1: Category.CAT1_MACRO, 2: Category.CAT2_SENTIMENT, 3: Category.CAT3_ACTION}
cat_mismatches = []
print(f"{'Estación':<16} | {'Profile cat':<12} | {'Family Category':<16} | {'Mapeo Coherente':<15}")
print("-" * 65)
for s, prof in sorted(STATION_PROFILES.items()):
    fam_cat = STATION_CATEGORIES.get(s)
    expected_cat = cat_map.get(prof.cat)
    coherent = (fam_cat == expected_cat)
    if not coherent:
        cat_mismatches.append((s, prof.cat, fam_cat, expected_cat))
    print(f"{s:<16} | {prof.cat} ({expected_cat.value if expected_cat else 'None'}) | {fam_cat.value if fam_cat else 'None':<16} | {'✅ OK' if coherent else '❌ MISMATCH'}")

# 1.3 Programa de probes
print("\n--- 1.3 Probes de Carga ---")
print(f"Total perfiles en station_profiles: {len(STATION_PROFILES)}/11")
print(f"get_all_stress_bins count:     {len(profiles_stress)}/11")
print(f"get_all_complacent_bins count: {len(profiles_complacent)}/11")
print(f"get_all_floor_bins count:      {len(profiles_floor)}/11")
print(f"get_all_ceiling_bins count:    {len(profiles_ceiling)}/11")


# ==============================================================================
# TAREA 2: PUNTO CIEGO A — EL FALLBACK NO_TIMING_DATA
# ==============================================================================
print("\n" + "=" * 50)
print("TAREA 2: PUNTO CIEGO A — EL FALLBACK NO_TIMING_DATA")
print("=" * 50)

rules = _load_rules()
floor_rules = rules.get("floor_rules", {})
ceiling_rules = rules.get("ceiling_rules", {})

print("\n--- 2.1 Verificación de rules JSON (`signal_discriminator_rules.json`) ---")
stations_in_floor_rules = list(floor_rules.keys())
stations_in_ceil_rules = list(ceiling_rules.keys())
print(f"Estaciones con floor_rules: {len(stations_in_floor_rules)}/11: {stations_in_floor_rules}")
print(f"Estaciones con ceiling_rules: {len(stations_in_ceil_rules)}/11: {stations_in_ceil_rules}")

# Verificar si d2_rule tiene hr_zz75 y sgs_median
missing_fields_floor = []
for st, r in floor_rules.items():
    by_d2 = r.get("by_d2", {})
    for d2_lbl, d2_dict in by_d2.items():
        if "hr_zz75" not in d2_dict or "sgs_median" not in d2_dict:
            missing_fields_floor.append((st, d2_lbl))

print(f"Campos hr_zz75/sgs_median ausentes en floor_rules: {len(missing_fields_floor)}")

# 2.2 Cuantificación por estación en Timing Fact Stores
print("\n--- 2.2 Cuantificación de estados sin timing / fallback por estación ---")
TIMING_DIR = REPO_ROOT / "backend/modules/entry_decision/domain/rules"
timing_stats = {}

print(f"{'Estación':<16} | {'Reg':<5} | {'N>0':<5} | {'FP_Floor':<8} | {'FP_Ceil':<8} | {'Sin FP_Fl':<9} | {'Fallback %':<10}")
print("-" * 75)

total_reg = 0
total_populated = 0
total_no_floor = 0

for s in sorted(STATION_PROFILES.keys()):
    json_path = TIMING_DIR / f"{s}_timing_fact_store.json"
    if not json_path.exists():
        print(f"ALERTA: {json_path} no existe")
        continue
    with open(json_path) as f:
        data = json.load(f)
    states = data.get("states", {})
    n_reg = len(states)
    n_pop = 0
    n_fp_floor = 0
    n_fp_ceil = 0
    
    for sk, sv in states.items():
        n_ep = sv.get("poblacion", {}).get("n_episodios", 0)
        if n_ep > 0:
            n_pop += 1
        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        if "zz75" in fp_min and fp_min["zz75"] is not None:
            n_fp_floor += 1
            
        m_max = sv.get("medicion_max", {})
        fp_max = m_max.get("first_passage", {})
        if "zz75" in fp_max and fp_max["zz75"] is not None:
            n_fp_ceil += 1
            
    no_fp_fl = n_reg - n_fp_floor
    fb_pct = (no_fp_fl / n_reg * 100) if n_reg > 0 else 0.0
    total_reg += n_reg
    total_populated += n_pop
    total_no_floor += no_fp_fl
    
    timing_stats[s] = {
        "n_reg": n_reg,
        "n_pop": n_pop,
        "n_fp_floor": n_fp_floor,
        "n_fp_ceil": n_fp_ceil,
        "no_fp_floor": no_fp_fl,
        "fb_pct": fb_pct,
    }
    print(f"{s:<16} | {n_reg:<5} | {n_pop:<5} | {n_fp_floor:<8} | {n_fp_ceil:<8} | {no_fp_fl:<9} | {fb_pct:<9.1f}%")

print("-" * 75)
print(f"{'TOTAL':<16} | {total_reg:<5} | {total_populated:<5} | {'-':<8} | {'-':<8} | {total_no_floor:<9} | {total_no_floor/total_reg*100:<9.1f}%")


# ==============================================================================
# TAREA 3: PUNTO CIEGO B — UMBRALES DE CONCORDANCIA VS DATOS REALES (MONOTONICIDAD)
# ==============================================================================
print("\n" + "=" * 50)
print("TAREA 3: PUNTO CIEGO B — MONOTONICIDAD REAL C1-C7 VS HR75")
print("=" * 50)

# Extraer todos los estados reales con first_passage para floor
states_eval = []
by_score = defaultdict(list)
by_station_score = defaultdict(lambda: defaultdict(list))

for s in sorted(STATION_PROFILES.keys()):
    json_path = TIMING_DIR / f"{s}_timing_fact_store.json"
    with open(json_path) as f:
        data = json.load(f)
    states = data.get("states", {})
    
    for sk, sv in states.items():
        parts = sk.split("__")
        if len(parts) != 3:
            continue
        d1, d2, d3 = int(parts[0]), int(parts[1]), int(parts[2])
        
        # Extraer first passage floor (medicion_min)
        m_min = sv.get("medicion_min", {})
        fp_min = m_min.get("first_passage", {})
        fp75 = fp_min.get("zz75")
        if not fp75 or not isinstance(fp75, dict):
            continue
        
        fp25 = fp_min.get("zz25", {})
        
        # Dual: medicion_max first_passage zz75
        m_max = sv.get("medicion_max", {})
        fp_max = m_max.get("first_passage", {})
        dual75 = fp_max.get("zz75") if isinstance(fp_max, dict) else None
        
        hr75 = fp75.get("hit_rate", 0.0)
        hr25 = fp25.get("hit_rate", 0.0) if isinstance(fp25, dict) else 0.0
        pf75 = fp75.get("profit_factor", 0.0)
        rr75 = fp75.get("rr_asymmetry", 0.0)
        mae = fp75.get("mae_medio", 0.0)
        mfe = fp75.get("mfe_medio", 0.0)
        pvalue = fp75.get("p_value", 1.0)
        sgs = (hr75 - hr25) / hr25 if hr25 > 0 else 0.0
        dual_hr75 = dual75.get("hit_rate", 0.5) if (dual75 and isinstance(dual75, dict)) else 0.5
        
        score, conds = _compute_floor_concordance(
            rr=rr75, hr75=hr75, pf75=pf75, sgs=sgs,
            mae=mae, mfe=mfe, ceil_hr75=dual_hr75, pvalue=pvalue
        )
        
        sig_class, conf = _concordance_to_class_and_confidence(score, hr75, sgs, is_ceiling=False)
        
        item = {
            "station": s,
            "state_key": sk,
            "d1": d1, "d2": d2, "d3": d3,
            "score": score,
            "hr75": hr75,
            "hr25": hr25,
            "pf75": pf75,
            "rr75": rr75,
            "sgs": sgs,
            "mae": mae,
            "mfe": mfe,
            "dual_hr75": dual_hr75,
            "pvalue": pvalue,
            "sig_class": sig_class,
            "conf": conf,
            "has_dual": dual75 is not None,
            "has_pvalue": ("p_value" in fp75 and fp75["p_value"] is not None),
        }
        states_eval.append(item)
        by_score[score].append(item)
        by_station_score[s][score].append(item)

print(f"\nTotal estados evaluados con datos First Passage zz75: {len(states_eval)}")

# Tabla de Monotonicidad Global
print("\n--- TABLA DE MONOTONICIDAD GLOBAL: SCORE (0-7) vs HR75 REAL ---")
print(f"{'Score':<6} | {'N':<5} | {'HR75 Mean':<10} | {'HR75 Median':<11} | {'HR75 Min':<9} | {'HR75 Max':<9} | {'PF Mean':<8} | {'RR Mean':<8} | {'Docstring Ref':<14}")
print("-" * 95)

doc_refs = {
    0: "HR75≈70.2%",
    1: "HR75≈58.3%",
    2: "HR75≈52.0%",
    3: "HR75≈50.0%",
    4: "HR75≈50.0%",
    5: "HR75≈40.0%",
    6: "HR75≈0.0%",
    7: "HR75≈0.0%",
}

for sc in range(8):
    group = by_score[sc]
    n = len(group)
    if n == 0:
        print(f"{sc:<6} | {0:<5} | {'N/A':<10} | {'N/A':<11} | {'N/A':<9} | {'N/A':<9} | {'N/A':<8} | {'N/A':<8} | {doc_refs.get(sc, ''):<14}")
        continue
    hrs = [x["hr75"] for x in group]
    pfs = [x["pf75"] for x in group]
    rrs = [x["rr75"] for x in group]
    mean_hr = statistics.mean(hrs)
    med_hr = statistics.median(hrs)
    min_hr = min(hrs)
    max_hr = max(hrs)
    mean_pf = statistics.mean(pfs)
    mean_rr = statistics.mean(rrs)
    print(f"{sc:<6} | {n:<5} | {mean_hr*100:<9.1f}% | {med_hr*100:<10.1f}% | {min_hr*100:<8.1f}% | {max_hr*100:<8.1f}% | {mean_pf:<8.2f} | {mean_rr:<8.2f} | {doc_refs.get(sc, ''):<14}")

# Desglose por Signal Class asignada
print("\n--- DISTRIBUCIÓN POR SIGNAL CLASS ASIGNADA ---")
by_class = defaultdict(list)
for item in states_eval:
    by_class[item["sig_class"]].append(item)

print(f"{'Signal Class':<22} | {'N':<5} | {'% Total':<8} | {'HR75 Mean':<10} | {'HR75 Median':<11} | {'PF Mean':<8}")
print("-" * 75)
for sc, group in sorted(by_class.items(), key=lambda x: -statistics.mean([y["hr75"] for y in x[1]])):
    hrs = [x["hr75"] for x in group]
    pfs = [x["pf75"] for x in group]
    n = len(group)
    pct = n / len(states_eval) * 100
    print(f"{sc:<22} | {n:<5} | {pct:<7.1f}% | {statistics.mean(hrs)*100:<9.1f}% | {statistics.median(hrs)*100:<10.1f}% | {statistics.mean(pfs):<8.2f}")


# ==============================================================================
# TAREA 4: PUNTO CIEGO C — SILENCIO DE C5 Y C7
# ==============================================================================
print("\n" + "=" * 50)
print("TAREA 4: PUNTO CIEGO C — SILENCIO DE C5 (DUAL) Y C7 (PVALUE)")
print("=" * 50)

c5_total = len(states_eval)
c5_with_dual = sum(1 for x in states_eval if x["has_dual"])
c5_default = c5_total - c5_with_dual
c5_fired = sum(1 for x in states_eval if x["dual_hr75"] > 0.60)

c7_total = len(states_eval)
c7_with_pval = sum(1 for x in states_eval if x["has_pvalue"])
c7_default = c7_total - c7_with_pval
c7_fired = sum(1 for x in states_eval if x["pvalue"] > 0.80)

print(f"Total estados analizados: {c5_total}")
print("\n--- C5: Dual Nature (ceil_hr75 > 0.60) ---")
print(f"Estados con dual real (medicion_max poblada):   {c5_with_dual} ({c5_with_dual/c5_total*100:.1f}%)")
print(f"Estados que caen a default dual_hr75 = 0.5:      {c5_default} ({c5_default/c5_total*100:.1f}%)")
print(f"Estados donde C5 realmente DISPARÓ (> 0.60):     {c5_fired} ({c5_fired/c5_total*100:.1f}%)")
print(f"-> IMPACTO: En el {c5_default/c5_total*100:.1f}% de estados, C5 es SILENCIOSO por falta de dual.")

print("\n--- C7: Statistical Insignificance (pvalue > 0.80) ---")
print(f"Estados con p_value explícito en timing store:  {c7_with_pval} ({c7_with_pval/c7_total*100:.1f}%)")
print(f"Estados que caen a default pvalue = 1.0:         {c7_default} ({c7_default/c7_total*100:.1f}%)")
print(f"Estados donde C7 DISPARÓ (> 0.80):               {c7_fired} ({c7_fired/c7_total*100:.1f}%)")
print(f"-> IMPACTO: C7 penaliza al {c7_fired/c7_total*100:.1f}% de estados (de los cuales {c7_default} caen por default 1.0).")

# Desglose de C5 y C7 por estación
print("\n--- C5 y C7 POR ESTACIÓN ---")
print(f"{'Estación':<16} | {'N':<4} | {'Dual Real':<10} | {'C5 Fired':<9} | {'Pval Real':<10} | {'C7 Fired':<9}")
print("-" * 65)
for s in sorted(STATION_PROFILES.keys()):
    st_items = [x for x in states_eval if x["station"] == s]
    n_st = len(st_items)
    if n_st == 0:
        continue
    d_real = sum(1 for x in st_items if x["has_dual"])
    c5_f = sum(1 for x in st_items if x["dual_hr75"] > 0.60)
    pv_real = sum(1 for x in st_items if x["has_pvalue"])
    c7_f = sum(1 for x in st_items if x["pvalue"] > 0.80)
    print(f"{s:<16} | {n_st:<4} | {d_real:<10} | {c5_f:<9} | {pv_real:<10} | {c7_f:<9}")


# ==============================================================================
# TAREA 5: CUMPLIMIENTO DE LA CITA — NO DIRECTIVAS EN HECHOS
# ==============================================================================
print("\n" + "=" * 50)
print("TAREA 5: CUMPLIMIENTO DE CLEAN ARCHITECTURE (HECHOS VS DIRECTIVAS)")
print("=" * 50)

# 5.1 Buscar directivas en los 3 módulos
code_files = [
    "backend/modules/entry_decision/domain/rules/station_profiles.py",
    "backend/modules/entry_decision/domain/rules/signal_discriminator.py",
    "backend/modules/entry_decision/domain/rules/family_sequence_detector.py",
]

directive_tokens = ["STK_", "MKT_", "operational_guidance", "order_type", "execute_", "buy_", "sell_"]

findings = []
for cf in code_files:
    p = REPO_ROOT / cf
    with open(p) as f:
        lines = f.readlines()
    for idx, line in enumerate(lines, 1):
        # Ignorar comentarios generales y docstrings si solo mencionan el concepto
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("*"):
            continue
        for dt in directive_tokens:
            if dt in line:
                findings.append((cf, idx, dt, stripped))

print(f"\nTokens directivos encontrados en código ejecutable de los 3 módulos: {len(findings)}")
for cf, idx, dt, line in findings:
    print(f"  [{cf}:{idx}] Token '{dt}': {line[:80]}")

# 5.2 Buscar directivas en los Fact Stores JSON
print("\n--- Inspección en Fact Stores JSON (Rules) ---")
fact_store_files = list((REPO_ROOT / "backend/modules/entry_decision/domain/rules").glob("*fact_store.json"))
json_directive_findings = []

for fsf in fact_store_files:
    with open(fsf) as f:
        content = f.read()
    for dt in ["MKT_ACCUMULATE", "MKT_TRIM", "STK_ACCUMULATE", "STK_TRIM", "operational_action", "execution_directive"]:
        if dt in content:
            json_directive_findings.append((fsf.name, dt))

print(f"Directivas encontradas en Fact Stores JSON: {len(json_directive_findings)}")
for fn, dt in json_directive_findings:
    print(f"  [{fn}] Encontró directiva: '{dt}'")

print("\n" + "=" * 80)
print("FIN DEL DIAGNÓSTICO EMPÍRICO")
print("=" * 80)
