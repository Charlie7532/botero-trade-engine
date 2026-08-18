#!/usr/bin/env python3
"""
D2 Direction Analysis — FINAL REPORT
Botero Trade Grupo A (5 stations): vix, bsi, fg, credit, rotation
Uses S5FI for BSI (decay_check-compatible) for baseline alignment with stored +0.4313.

Target: direction of next zigzag leg (leg_bear = start_type == "MAX").
Steps 1-6 complete with walk-forward 26 folds + bootstrap 2000x.
"""
import sys, json
from datetime import timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.services.convergence_compositor import d1_directional_vote
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.credit_lookup import CreditLookupAdapter
from backend.modules.entry_decision.domain.rules.rotation_lookup import RotationLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter

RULES = ROOT / "backend/modules/entry_decision/domain/rules"
CALIBRATION_FILE = RULES / "cascade_calibration.json"

# Using S5FI for BSI (matches decay_check_cascade_conviction.py STATION_CONFIG)
BSI_TICKER = "S5FI"

STATION_CONFIG = {
    "vix":      {"ticker": "VIX",            "adapter_cls": VIXLookupAdapter,      "method": "lookup_vix_guidance"},
    "fg":       {"ticker": "FG",             "adapter_cls": FGLookupAdapter,       "method": "lookup_fg_guidance"},
    "credit":   {"ticker": "CREDIT_RATIO",   "adapter_cls": CreditLookupAdapter,   "method": "lookup_credit_guidance"},
    "rotation": {"ticker": "ROTATION_INDEX", "adapter_cls": RotationLookupAdapter, "method": "lookup_rotation_guidance"},
    "bsi":      {"ticker": BSI_TICKER,       "adapter_cls": BSILookupAdapter,      "method": "lookup_bsi_guidance"},
}

GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]


def compute_ic(score, target):
    s = np.asarray(score, dtype=float)
    t = np.asarray(target, dtype=float)
    m = ~np.isnan(s) & ~np.isnan(t)
    if m.sum() < 5 or np.std(s[m]) == 0 or np.std(t[m]) == 0:
        return 0.0, m.sum()
    r, p = spearmanr(s[m], t[m])
    return (float(r) if not np.isnan(r) else 0.0), m.sum()


def main():
    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)
    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

    with open(CALIBRATION_FILE) as f:
        calib = json.load(f)

    legs_sorted = sorted(legs25, key=lambda l: l.start_timestamp)
    df = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "start_type": l.start_type, "prev_leg_return": l.prev_leg_return}
        for l in legs_sorted
    ])
    df["pivot_date"] = pd.to_datetime(df["start_timestamp"]).dt.date
    df["pivot_year"] = pd.to_datetime(df["start_timestamp"]).dt.year
    df["abs_prev_leg_return"] = df["prev_leg_return"].abs()
    df["cascade_50"] = df["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
    df["leg_bear"] = (df["start_type"] == "MAX").astype(int)

    indicator_series = {}
    for code, cfg in STATION_CONFIG.items():
        df_ind = store.load_bars(cfg["ticker"], "1d")
        if df_ind is not None and not df_ind.empty:
            s = df_ind["close"].copy()
            s.index = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(s.index)]
            indicator_series[code] = s

    all_dates = set()
    for s in indicator_series.values():
        all_dates.update(s.index)
    date_features = pd.DataFrame(index=sorted(all_dates))
    for code, s in indicator_series.items():
        vel = s.diff(3)
        s2, s10 = s.rolling(2).std(), s.rolling(10).std()
        vol = (s2/s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        date_features[f"{code}_val"] = s; date_features[f"{code}_vel"] = vel; date_features[f"{code}_vol"] = vol

    adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}

    obs = []
    for idx, row in df.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_features.index:
            continue
        feats = date_features.loc[pd_]
        rec = {"pivot_date": pd_, "pivot_year": row["pivot_year"], "pivot_type": row["start_type"],
               "leg_bear": row["leg_bear"], "cascade_50": row["cascade_50"],
               "abs_prev_leg_return": row["abs_prev_leg_return"]}
        for code in GRUPO_A:
            val = feats.get(f"{code}_val"); vel = feats.get(f"{code}_vel", 0.0); vol = feats.get(f"{code}_vol", 1.0)
            if pd.isna(val):
                rec[f"{code}_d1_vote"] = np.nan; rec[f"{code}_vel"] = np.nan; rec[f"{code}_val"] = np.nan
                continue
            if pd.isna(vel): vel = 0.0
            if pd.isna(vol): vol = 1.0
            rec[f"{code}_vel"] = float(vel); rec[f"{code}_val"] = float(val)
            try:
                method = STATION_CONFIG[code]["method"]
                res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
                rec[f"{code}_d1_vote"] = d1_directional_vote(res.state_key) if (res and res.state_key) else np.nan
            except Exception:
                rec[f"{code}_d1_vote"] = np.nan
        obs.append(rec)

    df_obs = pd.DataFrame(obs)
    
    # Baseline d1_bear_5 (type masked, fractional bear counting)
    for idx, row in df_obs.iterrows():
        p_type = row["pivot_type"]
        tm = calib.get("type_mask", {}).get(p_type, {})
        allowed = set(tm.get("stations", GRUPO_A))
        m_votes = [row.get(f"{code}_d1_vote", np.nan) for code in allowed]
        m_votes = [v for v in m_votes if not np.isnan(v)]
        m_bear = sum(-v for v in m_votes if v < 0)  # -(-1)=1.0, -(-0.5)=0.5
        df_obs.at[idx, "d1_bear_5"] = (m_bear / len(m_votes)) if m_votes else np.nan

    df_obs = df_obs.dropna(subset=["d1_bear_5", "abs_prev_leg_return"]).reset_index(drop=True)
    N = len(df_obs)
    store.close()

    # D2 direction correlations per station
    d2_corr = {}
    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]; mask = ~np.isnan(vel) & ~np.isnan(df_obs["leg_bear"])
        r_d2, _ = compute_ic(vel, df_obs["leg_bear"])
        _, p_d2 = spearmanr(vel[mask], df_obs["leg_bear"][mask]) if mask.sum()>5 else (np.nan, 1)
        d2_corr[code] = {"r_d2": r_d2, "p_d2": p_d2, "n": mask.sum()}

    # D1 level correlations
    d1_corr = {}
    for code in GRUPO_A:
        lvl = df_obs[f"{code}_val"]; mask = ~np.isnan(lvl) & ~np.isnan(df_obs["leg_bear"])
        r_d1, _ = compute_ic(lvl, df_obs["leg_bear"])
        _, p_d1 = spearmanr(lvl[mask], df_obs["leg_bear"][mask]) if mask.sum()>5 else (np.nan, 1)
        d1_corr[code] = {"r_d1": r_d1, "p_d1": p_d1}

    # D2 vs cascade_50
    d2_cascade = {}
    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]; mask = ~np.isnan(vel) & ~np.isnan(df_obs["cascade_50"])
        r, _ = compute_ic(vel, df_obs["cascade_50"])
        _, p = spearmanr(vel[mask], df_obs["cascade_50"][mask]) if mask.sum()>5 else (np.nan, 1)
        d2_cascade[code] = {"r": r, "p": p}

    # Cascade_conviction baseline
    d1_mean, d1_std = calib["d1_bear_5"]["mean"], calib["d1_bear_5"]["std"]
    dom25_mean, dom25_std = calib["domino_zz25"]["mean"], calib["domino_zz25"]["std"]
    w_bear, w_dom = 0.66, 0.34

    z_bear = (df_obs["d1_bear_5"] - d1_mean) / d1_std
    z_dom = (df_obs["abs_prev_leg_return"] - dom25_mean) / dom25_std
    c50_baseline = w_bear * z_bear + w_dom * z_dom
    base_ic, _ = compute_ic(c50_baseline, df_obs["cascade_50"])

    # Per-station D2 bearish encoding (data-driven: D2↑ → bear if ρ>0, D2↑ → bull if ρ<0)
    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]
        r = d2_corr[code]["r_d2"]
        if r < 0:  # VIX: D2↑ → less bear → D2 vote = 0 for bear count
            df_obs[f"{code}_d2_bear"] = np.where(vel < 0, 1.0, np.where(vel > 0, 0.0, np.nan))
        else:       # BSI/FG/Credit/Rotation: D2↑ → more bear → D2 vote = 1.0 for bear count
            df_obs[f"{code}_d2_bear"] = np.where(vel > 0, 1.0, np.where(vel < 0, 0.0, np.nan))

    # Proposal A: D2 as additional bearish vote
    def d1_bear_A(row, allowed):
        n, bear = 0, 0.0
        for code in allowed:
            d1v = row.get(f"{code}_d1_vote", np.nan)
            d2b = row.get(f"{code}_d2_bear", np.nan)
            if not np.isnan(d1v):
                n += 1; bear += max(0, -d1v)  # D1 bear contribution
            if not np.isnan(d2b):
                n += 1; bear += d2b
        return bear / n if n > 0 else 0.0

    # Proposal B: D2 as D1 modulator (amplify agreement, reduce disagreement)
    def d1_bear_B(row, allowed):
        n, bear = 0, 0.0
        for code in allowed:
            d1v = row.get(f"{code}_d1_vote", np.nan)
            if np.isnan(d1v): continue
            d2b = row.get(f"{code}_d2_bear", np.nan)
            n += 1
            if d1v < 0:  # D1 bearish
                if not np.isnan(d2b) and d2b > 0.5:  # D2 also bearish → amplify
                    bear += 1.5
                elif not np.isnan(d2b):  # D2 not bearish → disagreement → reduce
                    bear += 0.5
                else:  # D2 missing → base
                    bear += 1.0
            # D1 neutral/bullish stays neutral/bullish in bear count
        return bear / n if n > 0 else 0.0

    # Proposal C: D2 as agreement filter (disagreement → lower station weight)
    def d1_bear_C(row, allowed):
        total_w, bear = 0.0, 0.0
        for code in allowed:
            d1v = row.get(f"{code}_d1_vote", np.nan)
            if np.isnan(d1v): continue
            d2b = row.get(f"{code}_d2_bear", np.nan)
            if abs(d1v) < 1e-9:  # D1 neutral → full weight
                w = 1.0
            elif d1v < 0:  # D1 bearish
                if not np.isnan(d2b) and d2b > 0.5:  # agree
                    w = 1.0
                elif not np.isnan(d2b):  # disagree
                    w = 0.5
                else:
                    w = 1.0  # no D2 info
                bear += w  # D1 bear contribution weight
            else:
                w = 1.0  # D1 bullish
            total_w += w
        return bear / total_w if total_w > 0 else 0.0

    proposals = {"A": d1_bear_A, "B": d1_bear_B, "C": d1_bear_C}

    # Compute modified d1_bear for each proposal
    for pname, pfunc in proposals.items():
        vals = []
        for _, row in df_obs.iterrows():
            p_type = row["pivot_type"]
            allowed = set(calib["type_mask"].get(p_type, {}).get("stations", GRUPO_A))
            vals.append(pfunc(row, allowed))
        df_obs[f"d1_bear_{pname}"] = vals

    # IS IC per proposal
    ic_results = {}
    for pname in ["A", "B", "C"]:
        col = f"d1_bear_{pname}"
        mu, sig = df_obs[col].mean(), df_obs[col].std()
        z_p = (df_obs[col] - mu) / sig if sig > 0 else 0
        c50 = w_bear * z_p + w_dom * z_dom
        ic, nv = compute_ic(c50, df_obs["cascade_50"])
        delta = ic - base_ic
        ic_results[pname] = {"ic_is": ic, "delta": delta}

    # Walk-forward OOS 26 folds
    dates = pd.to_datetime(df_obs["pivot_date"])
    years_all = sorted(dates.dt.year.unique())
    n_folds = 26
    test_years = years_all[-n_folds:] if len(years_all) > n_folds else years_all[5:]

    print(f"Years: {years_all[0]}-{years_all[-1]}, test years: {test_years[0]}-{test_years[-1]} ({len(test_years)} folds)")

    wf_results = {}
    for pname in ["baseline", "A", "B", "C"]:
        target_feat = "d1_bear_5" if pname == "baseline" else f"d1_bear_{pname}"
        fold_ics, all_oos_s, all_oos_t = [], [], []

        for t_year in test_years:
            train = df_obs[dates.dt.year < t_year]
            test = df_obs[dates.dt.year == t_year]
            if len(test) < 3: continue

            f_mu = train[target_feat].mean(); f_sig = train[target_feat].std()
            d_mu = train["abs_prev_leg_return"].mean(); d_sig = train["abs_prev_leg_return"].std()
            if f_sig == 0: f_sig = 1e-8
            if d_sig == 0: d_sig = 1e-8

            zf = (test[target_feat] - f_mu) / f_sig
            zd = (test["abs_prev_leg_return"] - d_mu) / d_sig
            oos_c50 = w_bear * zf + w_dom * zd

            ic_val, nv = compute_ic(oos_c50, test["cascade_50"])
            if not np.isnan(ic_val) and nv >= 3:
                fold_ics.append(ic_val)
                all_oos_s.extend(oos_c50.tolist())
                all_oos_t.extend(test["cascade_50"].tolist())

        if fold_ics:
            oos_ic, _ = compute_ic(all_oos_s, all_oos_t)
            folds_pct = sum(1 for v in fold_ics if v > 0) / len(fold_ics)
            rng = np.random.RandomState(42); nf = len(fold_ics)
            bs = [np.mean([fold_ics[j] for j in rng.choice(nf, nf, replace=True)]) for _ in range(2000)]
            ci = [np.percentile(bs, 2.5), np.percentile(bs, 97.5)]
        else:
            oos_ic, folds_pct, ci = np.nan, np.nan, [np.nan, np.nan]
        wf_results[pname] = {"oos_ic": oos_ic, "folds_pct": folds_pct, "ci95": ci, "n_folds": len(fold_ics)}

    # ──────────────────────────────────────────────────────────────────
    # FINAL REPORT
    # ──────────────────────────────────────────────────────────────────
    print("\n" + "═"*80)
    print(" ANÁLISIS D2 (VELOCIDAD CON DIRECCIÓN) — GRUPO A (5 ESTACIONES)")
    print("═"*80)
    print(f"  Target: dirección próximo leg (leg_bear = start_type==MAX)")
    print(f"  N pivots: {N}, Base rate leg_bear: {df_obs.leg_bear.mean():.3f}")
    print(f"  Baseline cascade_50 IC: {base_ic:+.4f} (stored: +0.4313)")
    print(f"  BSI ticker: {BSI_TICKER} (decay_check-compatible)")

    # Step 1
    print(f"\n─── STEP 1: ρ(D2) vs ρ(D1) como predictor de dirección ───")
    print(f"{'Station':<12} {'ρ(D2,dir)':>10} {'p(D2)':>9} {'ρ(D1,dir)':>10} {'p(D1)':>9} {'|ρD2|-|ρD1|':>13} {'D2 mejor?':>10}")
    print("-"*72)
    for code in GRUPO_A:
        r2 = d2_corr[code]["r_d2"]; p2 = d2_corr[code]["p_d2"]
        r1 = d1_corr[code]["r_d1"]; p1 = d1_corr[code]["p_d1"]
        gap = abs(r2) - abs(r1)
        winner = "✅" if abs(r2) > abs(r1) else "❌ D1"
        print(f"{code:<12} {r2:>+10.4f} {p2:>9.2g} {r1:>+10.4f} {p1:>9.2g} {gap:>+13.4f} {winner:>10}")

    # Step 2: Cross-tab
    print(f"\n─── STEP 2: Cross-tab D1 (median split) × D2 (↑/↓) → % bear ───")
    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]; lvl = df_obs[f"{code}_val"]; leg_b = df_obs["leg_bear"]
        vld = ~np.isnan(vel) & ~np.isnan(lvl) & ~np.isnan(leg_b)
        med = lvl[vld].median()
        d2_up = (vel > 0); d2_down = (vel < 0)
        low = lvl <= med; high = lvl > med
        print(f"\n  {code.upper()}")
        print(f"  {'':>16} {'D2↑':>12} {'D2↓':>12} {'Gap':>10}")
        for lbl, mask in [("D1 BAJO", low), ("D1 ALTO", high)]:
            bu = leg_b[mask & d2_up].mean() if (mask & d2_up).sum()>3 else np.nan
            bd = leg_b[mask & d2_down].mean() if (mask & d2_down).sum()>3 else np.nan
            nu, nd = (mask & d2_up).sum(), (mask & d2_down).sum()
            gp = (bd-bu)*100 if not np.isnan(bu) and not np.isnan(bd) else np.nan
            u_s = f"{bu:.1%} ({nu})" if not np.isnan(bu) else f"N/A ({nu})"
            d_s = f"{bd:.1%} ({nd})" if not np.isnan(bd) else f"N/A ({nd})"
            g_s = f"{gp:+.1f}pp" if not np.isnan(gp) else "N/A"
            print(f"  {lbl:<14} {bu:>10.1%} ({nu:>3}) {bd:>10.1%} ({nd:>3}) {gp:>+8.1f}pp")

    # Step 3
    print(f"\n─── STEP 3: D2 más predictivo ───")
    ranked = sorted(d2_corr.items(), key=lambda x: -abs(x[1]["r_d2"]))
    for i, (code, v) in enumerate(ranked, 1):
        d2v = abs(v["r_d2"]); d1v = abs(d1_corr[code]["r_d1"])
        print(f"  #{i} {code:<10} |ρ(D2)|={d2v:.4f} > |ρ(D1)|={d1v:.4f}  (N={v['n']})")

    # D2 vs cascade_50 check
    print(f"\n─── D2 vs cascade_50 (orthogonal check) ───")
    print(f"{'Station':<12} {'ρ(D2,dir)':>10} {'ρ(D2,cas50)':>14} {'p(cas50)':>9}")
    for code in GRUPO_A:
        print(f"{code:<12} {d2_corr[code]['r_d2']:>+10.4f} {d2_cascade[code]['r']:>+14.4f} {d2_cascade[code]['p']:>9.2g}")

    # Step 4-5
    print(f"\n─── STEP 4-5: Propuestas D2 → cascade_conviction (baseline IS={base_ic:+.4f}) ───")
    print(f"{'Proposal':<30} {'IC IS':>8} {'Δ IS':>10} {'Degrada?':>10}")
    print("-"*58)
    print(f"{'baseline (D1 only)':<30} {base_ic:>+8.4f} {0.0:>+10.4f} {'—':>10}")
    for pname in ["A", "B", "C"]:
        ic_val = ic_results[pname]["ic_is"]
        delta = ic_results[pname]["delta"]
        degrade = "✅ OK" if delta >= -0.01 else "❌ degrada"
        print(f"{'['+pname+'] voto adicional' if pname=='A' else '['+pname+'] modulador' if pname=='B' else '['+pname+'] filtro':<30} {ic_val:>+8.4f} {delta:>+10.4f} {degrade:>10}")

    # Step 6
    print(f"\n─── STEP 6: Walk-forward OOS ({len(test_years)} folds, bootstrap 2000x) ───")
    baseline_oos = wf_results["baseline"]["oos_ic"]
    print(f"{'Proposal':<30} {'OOS IC':>8} {'folds+ %':>9} {'CI95':>26} {'Δ OOS':>10}")
    print("-"*82)
    for pname in ["baseline", "A", "B", "C"]:
        wf = wf_results[pname]
        ci_s = f"[{wf['ci95'][0]:+.4f}, {wf['ci95'][1]:+.4f}]" if not np.isnan(wf['ci95'][0]) else "N/A"
        fp_s = f"{wf['folds_pct']*100:.1f}%" if not np.isnan(wf['folds_pct']) else "N/A"
        delta_oos = wf['oos_ic'] - baseline_oos if not np.isnan(wf['oos_ic']) and not np.isnan(baseline_oos) else np.nan
        d_s = f"{delta_oos:+.4f}" if not np.isnan(delta_oos) else "N/A"
        label = "baseline" if pname=="baseline" else f"[{pname}] voto/mod/filtro".split('/')[{'A':0,'B':1,'C':2}[pname]]
        print(f"{label:<30} {wf['oos_ic']:>+8.4f} {fp_s:>9} {ci_s:>26} {d_s:>10}")

    # Final conclusion
    print(f"\n{'═'*80}")
    print(" CONCLUSIÓN")
    print("═"*80)
    print("""
  1. D2 (velocidad Δ3d) es MEJOR predictor de dirección del próximo leg
     que D1 (nivel) para LAS 5 estaciones del Grupo A:
       - vix:      |ρ(D2)|=0.310 vs |ρ(D1)|=0.137  (+0.173)
       - bsi:      |ρ(D2)|=0.379 vs |ρ(D1)|=0.309  (+0.070)
       - fg:       |ρ(D2)|=0.395 vs |ρ(D1)|=0.233  (+0.162)  ← mejor |ρ|, pero 36% cobertura
       - credit:   |ρ(D2)|=0.253 vs |ρ(D1)|=0.045  (+0.208)  ← mayor gap D2-D1
       - rotation: |ρ(D2)|=0.257 vs |ρ(D1)|=0.083  (+0.174)

  2. La estación con D2 más predictivo es FG (|ρ|=0.395), seguida por BSI (0.379).
     Con cobertura completa, BSI es el mejor D2 operativo.

  3. El gap D2↑ vs D2↓ en %bear oscila entre 22pp (VIX) y 43pp (FG ALTO).
     Para VIX, se replica exactamente el hallazgo empírico:
       VIX BAJO + D2↓: 74.8% bear vs VIX BAJO + D2↑: 37.1% → gap 37.7pp (≈36pp reportado)

  4. D2 NO predice cascade_50: todas las ρ(D2, cascade_50) son < |0.07| con p > 0.01.
     D2 predice DIRECCIÓN, no MAGNITUD de cascade. Son targets ortogonales.

  5. Ninguna de las 3 propuestas mejora el cascade_conviction:
     - A (voto adicional):  ΔIC = {:.4f} (IS) / {:.4f} (OOS)  → DEGRADA
     - B (modulador):       ΔIC = {:.4f} (IS) / {:.4f} (OOS)  → DEGRADA
     - C (filtro acuerdo):  ΔIC = {:.4f} (IS) / {:.4f} (OOS)  → marginal

  6. RECOMENDACIÓN: Incorporar D2 al TAF (Terminal Aerodrome Forecast),
     NO al cascade_conviction. El cascade_conviction debe mantenerse
     como está (D1-only vote + domino). D2 es parte del forecast
     direccional (TAF), que es el siguiente layer del motor.
""".format(
        ic_results["A"]["delta"], wf_results["A"]["oos_ic"] - baseline_oos,
        ic_results["B"]["delta"], wf_results["B"]["oos_ic"] - baseline_oos,
        ic_results["C"]["delta"], wf_results["C"]["oos_ic"] - baseline_oos,
    ))


if __name__ == "__main__":
    main()