#!/usr/bin/env python3
"""
D2 Direction Full Analysis — Botero Trade Grupo A (5 stations)
Steps 1-6: correlations, cross-tab, cascade_conviction proposals, walk-forward + bootstrap.

Key insight: target = leg_bear (direction of the leg starting at this pivot).
Confirmed: VIX D2 -> leg_bear rho = -0.310 ~= -0.29 empirical finding.
"""
import sys, json, math
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

BSI_TICKER_SIM = "S5TW"   # authoritative
# BSI_TICKER_SIM = "S5FI" # decay_check compatible (for baseline match test)

STATION_CONFIG_ALL = {
    "vix":      {"ticker": "VIX",            "adapter_cls": VIXLookupAdapter,      "method": "lookup_vix_guidance"},
    "fg":       {"ticker": "FG",             "adapter_cls": FGLookupAdapter,       "method": "lookup_fg_guidance"},
    "credit":   {"ticker": "CREDIT_RATIO",   "adapter_cls": CreditLookupAdapter,   "method": "lookup_credit_guidance"},
    "rotation": {"ticker": "ROTATION_INDEX", "adapter_cls": RotationLookupAdapter, "method": "lookup_rotation_guidance"},
    "bsi":      {"ticker": BSI_TICKER_SIM,   "adapter_cls": BSILookupAdapter,      "method": "lookup_bsi_guidance"},
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
    with open(CALIBRATION_FILE) as f:
        calib = json.load(f)
    d1_mean, d1_std = calib["d1_bear_5"]["mean"], calib["d1_bear_5"]["std"]
    dom25_mean, dom25_std = calib["domino_zz25"]["mean"], calib["domino_zz25"]["std"]
    w_bear, w_dom = 0.66, 0.34

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)
    legs25_raw = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

    legs_sorted = sorted(legs25_raw, key=lambda l: l.start_timestamp)
    df = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
         "prev_leg_return": l.prev_leg_return}
        for l in legs_sorted
    ])
    df["pivot_date"] = pd.to_datetime(df["start_timestamp"]).dt.date
    df["pivot_year"] = pd.to_datetime(df["start_timestamp"]).dt.year
    df["abs_prev_leg_return"] = df["prev_leg_return"].abs()
    df["cascade_50"] = df["pivot_date"].apply(
        lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
    )
    df["leg_bear"] = (df["start_type"] == "MAX").astype(int)

    # Indicator series
    indicator_series = {}
    for code, cfg in STATION_CONFIG_ALL.items():
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
        std_2, std_10 = s.rolling(2).std(), s.rolling(10).std()
        vol = (std_2 / std_10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        date_features[f"{code}_val"] = s
        date_features[f"{code}_vel"] = vel
        date_features[f"{code}_vol"] = vol

    adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG_ALL.items()}

    obs = []
    for idx, row in df.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_features.index:
            continue
        feats = date_features.loc[pd_]
        rec = {
            "pivot_date": pd_, "pivot_year": row["pivot_year"],
            "pivot_type": row["start_type"],
            "leg_bear": row["leg_bear"],
            "cascade_50": row["cascade_50"],
            "abs_prev_leg_return": row["abs_prev_leg_return"],
        }
        for code in GRUPO_A:
            val = feats.get(f"{code}_val")
            vel = feats.get(f"{code}_vel", 0.0)
            vol = feats.get(f"{code}_vol", 1.0)
            if pd.isna(val):
                rec[f"{code}_d1_vote"] = np.nan
                rec[f"{code}_vel"] = np.nan
                rec[f"{code}_val"] = np.nan
                rec[f"{code}_sk"] = None
                continue
            if pd.isna(vel): vel = 0.0
            if pd.isna(vol): vol = 1.0
            rec[f"{code}_vel"] = float(vel)
            rec[f"{code}_val"] = float(val)
            try:
                method = STATION_CONFIG_ALL[code]["method"]
                res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
                if res and res.state_key:
                    rec[f"{code}_sk"] = res.state_key
                    rec[f"{code}_d1_vote"] = d1_directional_vote(res.state_key)
                else:
                    rec[f"{code}_sk"] = None
                    rec[f"{code}_d1_vote"] = np.nan
            except Exception:
                rec[f"{code}_sk"] = None
                rec[f"{code}_d1_vote"] = np.nan
        obs.append(rec)

    df_obs = pd.DataFrame(obs)

    # D1 bearish vote baseline (type masked, fractional bear counting)
    for idx, row in df_obs.iterrows():
        p_type = row["pivot_type"]
        allowed = set(calib.get("type_mask", {}).get(p_type, {}).get("stations", GRUPO_A))
        m_votes = [row.get(f"{code}_d1_vote", np.nan) for code in allowed]
        m_votes = [v for v in m_votes if not np.isnan(v)]
        m_bear = sum(-v for v in m_votes if v < 0)
        df_obs.at[idx, "d1_bear_5"] = (m_bear / len(m_votes)) if m_votes else np.nan

    # Drop rows with NaN d1_bear or abs_prev_leg_return
    df_obs = df_obs.dropna(subset=["d1_bear_5", "abs_prev_leg_return"]).reset_index(drop=True)
    N = len(df_obs)
    store.close()

    # ===========================================================
    # STEP 1: rho(D2 vel, leg_bear) vs rho(D1 level, leg_bear)
    # ===========================================================
    z_bear = (df_obs["d1_bear_5"] - d1_mean) / d1_std
    z_dom = (df_obs["abs_prev_leg_return"] - dom25_mean) / dom25_std
    c50_baseline = w_bear * z_bear + w_dom * z_dom
    base_ic, _ = compute_ic(c50_baseline, df_obs["cascade_50"])

    print("═" * 70)
    print(" D2 (VELOCITY) AS DIRECTION PREDICTOR — GRUPO A STATIONS")
    print("═" * 70)
    print(f"\nBaseline cascade_conviction IC: {base_ic:+.4f} (N={N}, BSI={BSI_TICKER_SIM})")
    print(f"Stored baseline: +0.4313")
    print(f"\n{'Station':<12} {'ρ(D2,dir)':>10} {'p':>9} {'ρ(D1,dir)':>10} {'p':>9} {'|ρD2|-|ρD1|':>13} {'D2 win?':>9}")
    print("-" * 70)
    d2_vs_d1 = {}
    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]
        lvl = df_obs[f"{code}_val"]
        r_d2, nd2 = compute_ic(vel, df_obs["leg_bear"])
        r_d1, nd1 = compute_ic(lvl, df_obs["leg_bear"])
        mask_d2 = ~np.isnan(vel) & ~np.isnan(df_obs["leg_bear"])
        _, p_d2 = spearmanr(vel[mask_d2], df_obs["leg_bear"][mask_d2]) if mask_d2.sum()>5 else (np.nan, 1)
        mask_d1 = ~np.isnan(lvl) & ~np.isnan(df_obs["leg_bear"])
        _, p_d1 = spearmanr(lvl[mask_d1], df_obs["leg_bear"][mask_d1]) if mask_d1.sum()>5 else (np.nan, 1)
        gap = abs(r_d2) - abs(r_d1)
        d2_better = abs(r_d2) > abs(r_d1)
        print(f"{code:<12} {r_d2:>+10.4f} {p_d2:>9.2g} {r_d1:>+10.4f} {p_d1:>9.2g} {gap:>+13.4f} {'✅' if d2_better else 'D1 better'}")
        d2_vs_d1[code] = {"r_d2": r_d2, "r_d1": r_d1, "gap": gap, "d2_better": d2_better, "n_d2": nd2, "n_d1": nd1}

    # ===========================================================
    # STEP 2: Cross-tab D1 level × D2 sign → %bear
    # ===========================================================
    print(f"\n{'═'*70}")
    print(" CROSS-TAB: D1 (level tercile) × D2 (↑/↓) → % bear next leg")
    print("═" * 70)

    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]
        lvl = df_obs[f"{code}_val"]
        leg_b = df_obs["leg_bear"]
        valid = ~np.isnan(vel) & ~np.isnan(lvl) & ~np.isnan(leg_b)
        d2_up = (vel > 0) & valid
        d2_down = (vel < 0) & valid
        lvl_valid = lvl[valid]
        lvl_median = lvl_valid.median()
        low_d1 = (lvl <= lvl_median) & valid
        high_d1 = (lvl > lvl_median) & valid
        
        print(f"\n{code.upper():>15} — D1 median = {lvl_median:.3f}")
        print(f"  {'':>20} {'D2↑ (building)':>16} {'D2↓ (resolving)':>16} {'Gap':>10}")
        print(f"  {'':>20} {'─'*14} {'─'*14} {'─'*9}")
        
        for d1_label, d1_mask in [("BAJO", low_d1), ("ALTO", high_d1)]:
            bear_up = leg_b[d1_mask & d2_up].mean() if (d1_mask & d2_up).sum() > 3 else np.nan
            bear_down = leg_b[d1_mask & d2_down].mean() if (d1_mask & d2_down).sum() > 3 else np.nan
            n_up = (d1_mask & d2_up).sum()
            n_down = (d1_mask & d2_down).sum()
            gap_pct = (bear_down - bear_up) * 100 if not np.isnan(bear_up) and not np.isnan(bear_down) else np.nan
            u_str = f"{bear_up:.1%} ({n_up:>4})" if not np.isnan(bear_up) else f"N/A ({n_up:>4})"
            d_str = f"{bear_down:.1%} ({n_down:>4})" if not np.isnan(bear_down) else f"N/A ({n_down:>4})"
            g_str = f"{gap_pct:+.1f}pp" if not np.isnan(gap_pct) else "N/A"
            print(f"  D1 {d1_label:<14} {bear_up:>13.1%} ({n_up:>4}) {bear_down:>13.1%} ({n_down:>4}) {gap_pct:>+8.1f}pp")

    # ===========================================================
    # STEP 3: Most predictive D2
    # ===========================================================
    print(f"\n{'═'*70}")
    print(" TOP D2 PREDICTORS (by |ρ| vs next-leg direction)")
    print("═" * 70)
    ranked = sorted(d2_vs_d1.items(), key=lambda x: -abs(x[1]["r_d2"]))
    for i, (code, v) in enumerate(ranked, 1):
        print(f"  #{i} {code:<10} |ρ(D2)| = {abs(v['r_d2']):.4f}  (N={v['n_d2']})  {'D2 > D1 ✅' if v['d2_better'] else 'D1 ≥ D2'}")

    # Compute D2 directional vote per station (data-driven sign)
    for code in GRUPO_A:
        r_d2 = d2_vs_d1[code]["r_d2"]
        vel_col = df_obs[f"{code}_vel"]
        if r_d2 < 0:
            # VIX case: D2↑ (VIX rising) → less bear (bullish) → D2_vote = +1 (bullish)
            # D2 bearish for counting: -1 if D2↓, +1 if D2↑
            df_obs[f"{code}_d2_bear"] = np.where(vel_col < 0, 1.0, np.where(vel_col > 0, 0.0, np.nan))
        else:
            # BSI/FG case: D2↑ → more bear → D2_vote bearish
            df_obs[f"{code}_d2_bear"] = np.where(vel_col > 0, 1.0, np.where(vel_col < 0, 0.0, np.nan))
        df_obs[f"{code}_d2_sign"] = np.where(vel_col > 0, +1, np.where(vel_col < 0, -1, 0))

    # ===========================================================
    # STEP 4-5: 3 proposals
    # ===========================================================
    print(f"\n{'═'*70}")
    print(" D2 → CASCADE_CONVICTION PROPOSALS (ΔIC)")
    print("═" * 70)

    # Proposal A: D2 as additional vote
    def compute_d1_bear_A(row, allowed):
        """D1 votes + D2 votes combined. Each station contributes D1 + D2 vote."""
        n = 0
        bear = 0.0
        for code in allowed:
            d1v = row.get(f"{code}_d1_vote", np.nan)
            d2b = row.get(f"{code}_d2_bear", np.nan)
            if not np.isnan(d1v):
                n += 1
                if d1v < 0:
                    bear += 1.0
                elif d1v == -0.5:
                    bear += 0.5
            if not np.isnan(d2b):
                n += 1
                bear += d2b
        return bear / n if n > 0 else 0.0

    # Proposal B: D2 as D1 vote modulator (amplify if aligned, reduce if opposed)
    def compute_d1_bear_B(row, allowed):
        """D1 vote scaled by D2 agreement."""
        n = 0
        bear = 0.0
        for code in allowed:
            d1v = row.get(f"{code}_d1_vote", np.nan)
            if np.isnan(d1v): continue
            vel = row.get(f"{code}_vel", np.nan)
            n += 1
            if d1v < 0:  # D1 bearish
                if not np.isnan(vel) and vel < 0:
                    # VIX: D1 bearish + D2↓ (panic resolving) = very bearish → amplify
                    bear += 1.5
                elif not np.isnan(vel) and vel > 0:
                    # D1 bearish + D2↑ (panic building) = diverging → reduce
                    bear += 0.5
                else:
                    bear += 1.0
            elif abs(d1v) < 1e-9:  # D1 neutral
                if not np.isnan(vel):
                    bear += 0.0  # neutral stays neutral
        return bear / n if n > 0 else 0.0

    # Proposal C: D2 as filter (D1-D2 disagreement → lower station weight)
    def compute_d1_bear_C(row, allowed):
        """D1 vote with D2 agreement filter."""
        total_w = 0.0
        bear = 0.0
        for code in allowed:
            d1v = row.get(f"{code}_d1_vote", np.nan)
            if np.isnan(d1v): continue
            vel = row.get(f"{code}_vel", np.nan)
            # Weight: 1.0 if D1 neutral, else depends on D2 alignment
            if abs(d1v) < 1e-9:
                w = 1.0
            else:
                d2_sign = np.sign(vel) if not np.isnan(vel) and vel != 0 else 0
                # D1 bearish (v < 0) aligned with D2↓ (sign < 0 for VIX-type) or D2↑ (for BSI-type)
                # Simplification: D1-D2 align = same direction for bear
                # For this analysis: if D1 is bearish AND D2 also points bearish → w=1.0
                # if they disagree → w=0.5
                if d1v < 0:
                    r_d2_station = d2_vs_d1[code]["r_d2"]
                    d2_bearish = (r_d2_station < 0 and d2_sign < 0) or (r_d2_station > 0 and d2_sign > 0)
                    w = 1.0 if d2_bearish else 0.5
                else:
                    w = 1.0
            total_w += w
            if d1v < 0:
                bear += w * 1.0
        return bear / total_w if total_w > 0 else 0.0

    proposals = {"A": compute_d1_bear_A, "B": compute_d1_bear_B, "C": compute_d1_bear_C}

    for pname, pfunc in proposals.items():
        p_d1_bear = []
        for idx, row in df_obs.iterrows():
            p_type = row["pivot_type"]
            allowed = set(calib.get("type_mask", {}).get(p_type, {}).get("stations", GRUPO_A))
            p_d1_bear.append(pfunc(row, allowed))
        df_obs[f"d1_bear_{pname}"] = p_d1_bear

    ic_results = {}
    for pname in ["A", "B", "C"]:
        col = f"d1_bear_{pname}"
        z_p = (df_obs[col] - df_obs[col].mean()) / df_obs[col].std()
        c50_p = w_bear * z_p + w_dom * z_dom
        ic, n = compute_ic(c50_p, df_obs["cascade_50"])
        delta = ic - base_ic
        print(f"  Proposal {pname}: IC = {ic:+.4f} (Δ = {delta:+.4f} vs baseline {base_ic:+.4f})")
        ic_results[pname] = {"ic_is": ic, "delta": delta}

    # ===========================================================
    # STEP 6: Walk-forward OOS 26 folds + bootstrap
    # ===========================================================
    print(f"\n{'═'*70}")
    print(" WALK-FORWARD OOS — 26 expanding-window folds + bootstrap 2000x")
    print("═" * 70)

    dates = pd.to_datetime(df_obs["pivot_date"])
    years = sorted(dates.dt.year.unique())
    n_folds = min(26, len(years) - 5)
    test_years = years[-n_folds:]
    print(f"  Years: {years[0]}-{years[-1]}, folds={n_folds}, test years={test_years[0]}-{test_years[-1]}")

    wf_results = {}
    for pname in ["baseline", "A", "B", "C"]:
        if pname == "baseline":
            target_feat = "d1_bear_5"
        else:
            target_feat = f"d1_bear_{pname}"
        
        fold_ics = []
        all_oos_scores = []
        all_oos_targets = []
        
        for t_year in test_years:
            train_mask = dates.dt.year < t_year
            test_mask = dates.dt.year == t_year
            if test_mask.sum() < 3:
                continue
            
            train = df_obs[train_mask]
            test = df_obs[test_mask]
            
            feat_mu = train[target_feat].mean()
            feat_std = train[target_feat].std()
            dom_mu = train["abs_prev_leg_return"].mean()
            dom_std = train["abs_prev_leg_return"].std()
            
            if feat_std == 0: feat_std = 1e-8
            if dom_std == 0: dom_std = 1e-8
            
            z_f = (test[target_feat] - feat_mu) / feat_std
            z_d = (test["abs_prev_leg_return"] - dom_mu) / dom_std
            oos_c50 = w_bear * z_f + w_dom * z_d
            
            ic_val, n = compute_ic(oos_c50, test["cascade_50"])
            if not np.isnan(ic_val) and n >= 3:
                fold_ics.append(ic_val)
                all_oos_scores.extend(oos_c50.tolist())
                all_oos_targets.extend(test["cascade_50"].tolist())
        
        if fold_ics:
            oos_ic, _ = compute_ic(all_oos_scores, all_oos_targets)
            folds_pos = sum(1 for v in fold_ics if v > 0) / len(fold_ics)
            
            bs_ics = []
            rng = np.random.RandomState(42)
            nf = len(fold_ics)
            for _ in range(2000):
                idx = rng.choice(nf, size=nf, replace=True)
                bs_ics.append(np.mean([fold_ics[j] for j in idx]))
            ci95 = [np.percentile(bs_ics, 2.5), np.percentile(bs_ics, 97.5)]
            
            print(f"  {pname:<10} OOS IC = {oos_ic:+.4f}  {folds_pos*100:.1f}% folds+  CI95=[{ci95[0]:+.4f}, {ci95[1]:+.4f}]  ({len(fold_ics)} folds)")
        else:
            print(f"  {pname:<10} INSUFFICIENT DATA")
            oos_ic, folds_pos, ci95 = np.nan, np.nan, [np.nan, np.nan]
        
        wf_results[pname] = {"oos_ic": oos_ic, "folds_pct": folds_pos, "ci95": ci95, "n_folds": len(fold_ics)}

    # ===========================================================
    # FINAL SUMMARY
    # ===========================================================
    print(f"\n{'═'*70}")
    print(" FINAL SUMMARY")
    print("═" * 70)
    print(f"\n  Baseline cascade_50 IC (IS): {base_ic:+.4f}")
    print(f"  Baseline cascade_50 IC (OOS): {wf_results['baseline']['oos_ic']:+.4f}")
    print(f"\n{'Proposal':<30} {'IC IS':>8} {'Δ IS':>10} {'OOS IC':>8} {'% folds+':>9} {'CI95 OOS':>26}")
    print("-" * 95)
    for pname in ["baseline", "A", "B", "C"]:
        wf = wf_results[pname]
        ic_is = base_ic if pname == "baseline" else ic_results.get(pname, {}).get("ic_is", np.nan)
        delta = 0 if pname == "baseline" else ic_results.get(pname, {}).get("delta", np.nan)
        ci_str = f"[{wf['ci95'][0]:+.4f}, {wf['ci95'][1]:+.4f}]" if not np.isnan(wf['ci95'][0]) else "N/A"
        fp = wf['folds_pct']
        fp_str = f"{fp*100:.1f}%" if not np.isnan(fp) else "N/A"
        print(f"{'['+pname+']':<30} {ic_is:>+8.4f} {delta:>+10.4f} {wf['oos_ic']:>+8.4f} {fp_str:>9} {ci_str:>26}")

    # Key finding
    print(f"\n═══ KEY FINDINGS ═══")
    best_station = max(d2_vs_d1.items(), key=lambda x: abs(x[1]["r_d2"]))
    print(f"  1. Mejor D2 predictor de dirección: {best_station[0]} (|ρ| = {abs(best_station[1]['r_d2']):.4f})")
    print(f"     D2 beats D1 for: {', '.join(c for c,v in d2_vs_d1.items() if v['d2_better'])}")
    print(f"     D1 beats D2 for: {', '.join(c for c,v in d2_vs_d1.items() if not v['d2_better'])}")
    
    # Best proposal
    if ic_results:
        best_is = max(ic_results.items(), key=lambda x: x[1]["delta"])
        best_oos = max(wf_results.items(), key=lambda x: x[1]["oos_ic"] if not np.isnan(x[1]["oos_ic"]) else -999)
        print(f"\n  2. Mejor propuesta (ΔIC IS): {best_is[0]} ({best_is[1]['delta']:+.4f})")
        print(f"     Mejor propuesta (OOS):    {best_oos[0]} ({best_oos[1]['oos_ic']:+.4f})")


if __name__ == "__main__":
    main()