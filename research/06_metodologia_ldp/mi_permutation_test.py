#!/usr/bin/env python3
"""
MI PERMUTATION TEST — p-values para la información mutua.
Complemento: MI basada en bins (χ² / G-test) con null de permutación.
Distingue señal real de sesgo del estimador kNN.
"""
import sys, pickle, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, chi2_contingency

ROOT = Path("/root/botero-trade")
OBS_PKL = ROOT / "scratch/quants_obs.pkl"

with open(OBS_PKL, 'rb') as f:
    df = pickle.load(f)

ALL_STATIONS = ["vix","vvix","pcr","fg","sv5_turbulence","skew","credit","yield_curve","rotation","bsi","dxy"]

def binned_mi(x, y, n_bins=8):
    """MI via contingency table (binned feature × binary target), in nats.
    Returns MI, p-value from chi2 independence test."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    m = ~np.isnan(x) & ~np.isnan(y)
    x_c = x[m]; y_c = y[m]
    if len(x_c) < 30:
        return 0.0, 1.0, 0
    try:
        x_b = pd.qcut(x_c, q=n_bins, duplicates='drop', labels=False)
    except Exception:
        return 0.0, 1.0, len(x_c)
    valid = ~np.isnan(x_b)
    x_b = x_b[valid]; y_cc = y_c[valid]
    if len(x_b) < 30:
        return 0.0, 1.0, len(x_b)
    
    # contingency table: bins × binary
    table = pd.crosstab(x_b, y_cc.astype(int))
    if table.shape[0] < 2 or table.shape[1] < 2:
        return 0.0, 1.0, len(x_b)
    
    # normalize to probabilities
    p = table.values / table.values.sum()
    px = p.sum(axis=1, keepdims=True)
    py = p.sum(axis=0, keepdims=True)
    
    # MI = sum p(x,y) log p(x,y)/(p(x)p(y))
    denom = px @ py
    with np.errstate(divide='ignore', invalid='ignore'):
        log_term = np.where(p > 0, np.log(p / denom), 0.0)
    mi = float(np.sum(p * log_term))
    
    # chi2 independence p-value
    try:
        chi2, pval, dof, expected = chi2_contingency(table.values, correction=False)
    except Exception:
        pval = 1.0
    
    return mi, float(pval), len(x_b)

def permutation_mi_pval(x, y, n_bins=8, n_perm=500):
    """Permutation test: shuffle target, recompute MI, get empirical p-value."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    m = ~np.isnan(x) & ~np.isnan(y)
    x_c = x[m]; y_c = y[m]
    if len(x_c) < 30:
        return 0.0, 1.0, 0
    obs_mi, _, n = binned_mi(x_c, y_c, n_bins)
    
    rng = np.random.default_rng(42)
    perm_mis = []
    for _ in range(n_perm):
        y_perm = rng.permutation(y_c)
        pmi, _, _ = binned_mi(x_c, y_perm, n_bins)
        perm_mis.append(pmi)
    perm_mis = np.array(perm_mis)
    pval = (np.sum(perm_mis >= obs_mi) + 1) / (n_perm + 1)
    return obs_mi, pval, n

print("═" * 78)
print(" MI CON BINS (χ²) + PERMUTATION TEST — señal real vs sesgo del estimador")
print("═" * 78)

outcomes = {
    "cascade_50": df["cascade_50"],
    "next_leg_direction": df["next_leg_direction"],
    "cascade_75": df["cascade_75"],
}

results = []
for out_name, out_col in outcomes.items():
    print(f"\n── {out_name} ──")
    print(f"{'Feature':<22} {'MI_bins':>9} {'MI_perm':>9} {'p_perm':>8} {'p_chi2':>9} {'|ρ|':>7} {'N':>6}  Verdicto")
    print("-" * 90)
    
    rows = []
    for code in ALL_STATIONS:
        for dim, suffix in [("val","D1"),("vel","D2"),("vol","D3")]:
            feat = df[f"{code}_{dim}"].values
            mi_obs, p_perm, n = permutation_mi_pval(feat, out_col.values, n_bins=8, n_perm=300)
            _, p_chi2, _ = binned_mi(feat, out_col.values, n_bins=8)
            valid_mask = ~np.isnan(feat) & ~np.isnan(out_col.values)
            if valid_mask.sum() > 5:
                rho_val = spearmanr(feat[valid_mask], out_col.values[valid_mask])[0]
                rho = abs(rho_val) if not np.isnan(rho_val) else 0.0
            else:
                rho = 0.0
            
            sig = "✅ SIGNIFICATIVO" if p_perm < 0.05 else "—"
            rows.append({
                "feature": f"{code}_{dim}", "mi": mi_obs, "p_perm": p_perm,
                "p_chi2": p_chi2, "rho": abs(rho) if not np.isnan(rho) else 0, "n": n,
                "sig": sig, "outcome": out_name
            })
    
    # Sort by MI and print top 12 + the ones with significant p
    rows_sorted = sorted(rows, key=lambda r: -r["mi"])
    for r in rows_sorted[:12]:
        print(f"{r['feature']:<22} {r['mi']:9.4f} {r['mi']:9.4f} {r['p_perm']:8.4f} {r['p_chi2']:9.2e} {r['rho']:7.3f} {r['n']:6d}  {r['sig']}")
    
    # Also list all features with p_perm < 0.05 (significant non-linear info)
    sig_rows = [r for r in rows if r["p_perm"] < 0.05]
    print(f"\n  → {len(sig_rows)}/33 features con MI significativa (p_perm < 0.05):")
    for r in sorted(sig_rows, key=lambda r: -r["mi"]):
        print(f"      {r['feature']:<22} MI={r['mi']:.4f} p={r['p_perm']:.4f} |ρ|={r['rho']:.3f}")
    
    results.extend(rows)

# Non-linearity: features where MI is significant but |ρ| is LOW (non-monotonic relationship)
print("\n" + "═" * 78)
print(" ANÁLISIS NO-LINEALIDAD: MI significativa pero |ρ| baja (relación no-monotónica)")
print("═" * 78)

for out_name in outcomes:
    sub = [r for r in results if r["outcome"] == out_name]
    # Features with significant MI but low |ρ| relative to other significant features
    sig = [r for r in sub if r["p_perm"] < 0.05]
    if not sig:
        continue
    max_rho = max(r["rho"] for r in sig)
    nonlin = [r for r in sig if r["rho"] < 0.15 and r["mi"] > 0.01]
    
    print(f"\n  {out_name}: features con MI significativa y |ρ| < 0.15 (info NO-lineal):")
    if nonlin:
        for r in sorted(nonlin, key=lambda r: -r["mi"])[:8]:
            print(f"    {r['feature']:<22} MI={r['mi']:.4f} p={r['p_perm']:.4f} |ρ|={r['rho']:.3f}")
    else:
        print(f"    Ninguna — la info significativa es mayormente monotónica (capturada por ρ).")

# Save
pd.DataFrame(results).to_csv(ROOT / "scratch/mi_permutation_results.csv", index=False)
print("\n  Guardado en scratch/mi_permutation_results.csv")
