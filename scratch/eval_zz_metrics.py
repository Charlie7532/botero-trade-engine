import json
import numpy as np
import pandas as pd
from pathlib import Path

path_ts = Path("backend/modules/entry_decision/domain/rules/skew_timing_fact_store.json")
path_fs = Path("backend/modules/entry_decision/domain/rules/skew_fact_store.json")

with open(path_ts) as f:
    ts = json.load(f)
with open(path_fs) as f:
    fs = json.load(f)

states_ts = ts.get("states", {})
states_fs = fs.get("states", {})

records = []
for state_key, data_ts in states_ts.items():
    parts = state_key.split("__")
    if len(parts) != 3:
        continue
    d1, d2, d3 = int(parts[0]), int(parts[1]), int(parts[2])
    
    data_fs = states_fs.get(state_key, {})
    n_barras = data_ts.get("poblacion", {}).get("barras", data_fs.get("n", 0))
    n_episodes = data_ts.get("poblacion", {}).get("n_episodios", data_fs.get("n_episodes", 0))
    
    # Extract ZZ metrics for Floor (medicion_min)
    m_min = data_ts.get("medicion_min", {})
    fp_min = m_min.get("first_passage", {})
    
    # Extract ZZ metrics for Ceiling (medicion_max)
    m_max = data_ts.get("medicion_max", {})
    fp_max = m_max.get("first_passage", {})
    
    row = {
        "state_key": state_key,
        "d1": d1, "d2": d2, "d3": d3,
        "n_barras": n_barras,
        "n_episodes": n_episodes,
    }
    
    for scale in ["zz25", "zz50", "zz75"]:
        # Floor first passage
        sc_floor = fp_min.get(scale, {})
        row[f"floor_hr_{scale}"] = sc_floor.get("hit_rate")
        row[f"floor_ev_{scale}"] = sc_floor.get("ev")
        row[f"floor_ev_neto_{scale}"] = sc_floor.get("ev_neto")
        row[f"floor_pf_{scale}"] = sc_floor.get("profit_factor")
        row[f"floor_rr_{scale}"] = sc_floor.get("rr_asymmetry")
        row[f"floor_pval_{scale}"] = sc_floor.get("p_value")
        
        # Ceiling first passage
        sc_ceil = fp_max.get(scale, {})
        row[f"ceil_hr_{scale}"] = sc_ceil.get("hit_rate")
        row[f"ceil_ev_{scale}"] = sc_ceil.get("ev")
        row[f"ceil_ev_neto_{scale}"] = sc_ceil.get("ev_neto")
        row[f"ceil_pf_{scale}"] = sc_ceil.get("profit_factor")
        row[f"ceil_rr_{scale}"] = sc_ceil.get("rr_asymmetry")
        
        # Standard layer from fact store (p_bull, ev_net)
        fs_sc = data_fs.get(scale, {})
        row[f"fs_p_bull_{scale}"] = fs_sc.get("p_bull")
        row[f"fs_ev_net_{scale}"] = fs_sc.get("ev_net")
        row[f"fs_lift_{scale}"] = fs_sc.get("lift_vs_baseline")

    records.append(row)

df = pd.DataFrame(records)
print(f"Total estados analizados en Evaluador General ZZ: {len(df)}")

# Weighted average helper
def w_avg(s, w):
    mask = s.notna() & w.notna() & (w > 0)
    if not mask.any() or w[mask].sum() == 0:
        return np.nan
    return (s[mask] * w[mask]).sum() / w[mask].sum()

print("=" * 95)
print("EVALUADOR GENERAL DE RETORNOS ZIGZAG (zz25, zz50, zz75) — AUDITORÍA ANTES vs DESPUÉS")
print("=" * 95)

# 1. Comparación de Suelos: ANTES (D1 in [4,5]) vs AHORA (D1 in [0,1])
old_floor_mask = df["d1"].isin([4, 5])
new_floor_mask = df["d1"].isin([0, 1])

print("\n--- 1. PISOS / SUELOS (medicion_min First-Passage a Escalas ZZ) ---")
for scale, name in [("zz25", "TÁCTICA (2.5%)"), ("zz50", "SWING (5.0%)"), ("zz75", "ESTRUCTURAL (7.5%)")]:
    print(f"\n  ESCALA {name}:")
    
    # Old floor zone (D1 in [4, 5])
    hr_old = w_avg(df.loc[old_floor_mask, f"floor_hr_{scale}"], df.loc[old_floor_mask, "n_barras"])
    ev_old = w_avg(df.loc[old_floor_mask, f"floor_ev_{scale}"], df.loc[old_floor_mask, "n_barras"])
    ev_net_old = w_avg(df.loc[old_floor_mask, f"floor_ev_neto_{scale}"], df.loc[old_floor_mask, "n_barras"])
    pf_old = w_avg(df.loc[old_floor_mask, f"floor_pf_{scale}"], df.loc[old_floor_mask, "n_barras"])
    
    # New floor zone (D1 in [0, 1])
    hr_new = w_avg(df.loc[new_floor_mask, f"floor_hr_{scale}"], df.loc[new_floor_mask, "n_barras"])
    ev_new = w_avg(df.loc[new_floor_mask, f"floor_ev_{scale}"], df.loc[new_floor_mask, "n_barras"])
    ev_net_new = w_avg(df.loc[new_floor_mask, f"floor_ev_neto_{scale}"], df.loc[new_floor_mask, "n_barras"])
    pf_new = w_avg(df.loc[new_floor_mask, f"floor_pf_{scale}"], df.loc[new_floor_mask, "n_barras"])
    
    print(f"    • ANTES (SKEW D1 in [4, 5] como suelo):")
    print(f"        Floor Hit Rate: {hr_old*100:.1f}% | EV: {ev_old*100:+.2f}% | EV Neto: {ev_net_old*100:+.2f}% | Profit Factor: {pf_old:.2f}")
    print(f"    • AHORA (SKEW D1 in [0, 1] como suelo):")
    print(f"        Floor Hit Rate: {hr_new*100:.1f}% | EV: {ev_new*100:+.2f}% | EV Neto: {ev_net_new*100:+.2f}% | Profit Factor: {pf_new:.2f}")
    delta_ev = (ev_new - ev_old) * 100
    delta_hr = (hr_new - hr_old) * 100
    print(f"    ==> MEJORA ZZ: ΔHitRate = {delta_hr:+.1f} pp | ΔEV = {delta_ev:+.2f} pp | PF sube de {pf_old:.2f} a {pf_new:.2f}!")

# 2. Comparación de Techos: ANTES (D1 in [0,1]) vs AHORA (D1 in [4,5])
print("\n" + "=" * 95)
print("--- 2. TECHOS / CEILINGS (medicion_max First-Passage a Escalas ZZ) ---")
print("=" * 95)
for scale, name in [("zz25", "TÁCTICA (2.5%)"), ("zz50", "SWING (5.0%)"), ("zz75", "ESTRUCTURAL (7.5%)")]:
    print(f"\n  ESCALA {name}:")
    
    # Old ceiling zone (D1 in [0, 1] - false ceiling)
    chr_old = w_avg(df.loc[new_floor_mask, f"ceil_hr_{scale}"], df.loc[new_floor_mask, "n_barras"])
    cev_old = w_avg(df.loc[new_floor_mask, f"ceil_ev_{scale}"], df.loc[new_floor_mask, "n_barras"])
    cpf_old = w_avg(df.loc[new_floor_mask, f"ceil_pf_{scale}"], df.loc[new_floor_mask, "n_barras"])
    
    # New ceiling zone (D1 in [4, 5] - real ceiling)
    chr_new = w_avg(df.loc[old_floor_mask, f"ceil_hr_{scale}"], df.loc[old_floor_mask, "n_barras"])
    cev_new = w_avg(df.loc[old_floor_mask, f"ceil_ev_{scale}"], df.loc[old_floor_mask, "n_barras"])
    cpf_new = w_avg(df.loc[old_floor_mask, f"ceil_pf_{scale}"], df.loc[old_floor_mask, "n_barras"])
    
    print(f"    • ANTES (Techo buscado en D1 in [0, 1]):")
    print(f"        Ceil Hit Rate: {chr_old*100:.1f}% | Ceil EV: {cev_old*100:+.2f}% | Profit Factor: {cpf_old:.2f}")
    print(f"    • AHORA (Techo buscado en D1 in [4, 5]):")
    print(f"        Ceil Hit Rate: {chr_new*100:.1f}% | Ceil EV: {cev_new*100:+.2f}% | Profit Factor: {cpf_new:.2f}")

# 3. Diamantes en Escalas ZZ
print("\n" + "=" * 95)
print("--- 3. DIAMANTES DE ALTA CONVICCIÓN EN ESCALAS ZZ ---")
print("=" * 95)
d2_zero_mask = (df["d1"].isin([0, 1])) & (df["d2"] == 0)
d3_four_mask = (df["d1"].isin([0, 1])) & (df["d3"] == 4)

print(f"\nA. DIAMANTE FAST_CRUSH (D1 in [0,1] + D2=0): {d2_zero_mask.sum()} estados en tabla:")
for idx, r in df[d2_zero_mask].iterrows():
    print(f"   Estado {r['state_key']} (n_barras={r['n_barras']}, n_episodes={r['n_episodes']}):")
    print(f"     zz25: Floor HR={r['floor_hr_zz25']*100:.1f}%, EV={r['floor_ev_zz25']*100:+.2f}%, PF={r['floor_pf_zz25']:.2f}")
    print(f"     zz50: Floor HR={r['floor_hr_zz50']*100:.1f}%, EV={r['floor_ev_zz50']*100:+.2f}%, PF={r['floor_pf_zz50']:.2f}")
    print(f"     zz75: Floor HR={r['floor_hr_zz75']*100:.1f}%, EV={r['floor_ev_zz75']*100:+.2f}%, PF={r['floor_pf_zz75']:.2f}, RR={r['floor_rr_zz75']:.2f}")

print(f"\nB. DIAMANTE ABSORCIÓN INSTITUCIONAL (D1 in [0,1] + D3=4): {d3_four_mask.sum()} estados en tabla:")
for scale in ["zz25", "zz50", "zz75"]:
    hr_d3 = w_avg(df.loc[d3_four_mask, f"floor_hr_{scale}"], df.loc[d3_four_mask, "n_barras"])
    ev_d3 = w_avg(df.loc[d3_four_mask, f"floor_ev_{scale}"], df.loc[d3_four_mask, "n_barras"])
    pf_d3 = w_avg(df.loc[d3_four_mask, f"floor_pf_{scale}"], df.loc[d3_four_mask, "n_barras"])
    print(f"     {scale}: Floor HR={hr_d3*100:.1f}%, EV={ev_d3*100:+.2f}%, PF={pf_d3:.2f}")
