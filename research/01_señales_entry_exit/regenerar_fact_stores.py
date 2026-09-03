#!/usr/bin/env python3
"""
SPRINT 2: Regenerar Fact Stores Enriquecidos con Gobernanza Estadística
========================================================================
Lee bar_augment.parquet + continuous_metar_lake.parquet.
Para cada una de las 11 estaciones, para cada estado observado:
  - N_crudo, N_independiente (post-purge de-clustering)
  - HR, Lift vs baseline, CI95 Clopper-Pearson
  - p_raw (binom), p_BH (Benjamini-Hochberg)
  - MAE (min, mean, max), MFE (mean, max)
  - Duration (mean, max streak), n_episodes

Writes ENRICHED {station}_fact_store.json PRESERVING backward-compatible schema.
"""
import sys
import json
import time
import warnings
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import binomtest, binom

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = ROOT / "research" / "01_señales_entry_exit"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence",
    "skew", "credit", "yield_curve", "rotation", "dxy", "bsi",
]

ESCALAS = {"zz25": 0.025, "zz50": 0.050, "zz75": 0.075}
SCALE_WINDOWS = {"zz25": 80, "zz50": 40, "zz75": 27}

FACT_STORE_DIR = ROOT / "backend" / "modules" / "entry_decision" / "domain" / "rules"
DATA_DIR = ROOT / "data" / "research"


def clopper_pearson_ci(k: int, n: int, alpha: float = 0.05) -> Tuple[float, float]:
    """Exact Clopper-Pearson confidence interval for binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    lo = binom.ppf(alpha / 2, n, k / n) / n if k > 0 else 0.0
    hi = binom.ppf(1 - alpha / 2, n, k / n) / n if k < n else 1.0
    # Use scipy beta for exact bounds
    from scipy.stats import beta as beta_dist
    lo = beta_dist.ppf(alpha / 2, k, n - k + 1) if k > 0 else 0.0
    hi = beta_dist.ppf(1 - alpha / 2, k + 1, n - k) if k < n else 1.0
    return (float(lo), float(hi))


def decluster_indices(indices: np.ndarray, window: int) -> np.ndarray:
    """De-cluster indices by embargo: keep only entries separated by >= window bars."""
    if len(indices) == 0:
        return indices
    result = [indices[0]]
    for idx in indices[1:]:
        if idx - result[-1] >= window:
            result.append(idx)
    return np.array(result)


def benjamini_hochberg(p_values: List[float], q: float = 0.05) -> List[float]:
    """Benjamini-Hochberg correction for multiple testing. Returns adjusted p-values."""
    n = len(p_values)
    if n == 0:
        return []
    sorted_indices = np.argsort(p_values)
    sorted_pvals = np.array(p_values)[sorted_indices]
    adjusted = np.zeros(n)
    
    for i in range(n - 1, -1, -1):
        rank = i + 1
        adjusted_p = sorted_pvals[i] * n / rank
        if i < n - 1:
            adjusted_p = min(adjusted_p, adjusted[sorted_indices[i + 1]])
        adjusted[sorted_indices[i]] = min(adjusted_p, 1.0)
    
    return adjusted.tolist()


def compute_baseline_hr(augment: pd.DataFrame) -> Dict[str, float]:
    """Compute unconditional baseline hit rate for each scale."""
    baselines = {}
    for scale in ESCALAS:
        col = f"{scale}_long_hit"
        valid = augment[col].dropna()
        baselines[scale] = float(valid.mean()) if len(valid) > 0 else 0.5
    return baselines


def grade_state(n_indep: int, lift: float, p_bh: float, rr: float) -> str:
    """Classify state quality based on de-clustered N, lift, and adjusted p-value."""
    if n_indep >= 30 and abs(lift) > 0.05 and p_bh < 0.05:
        return "GRADE_A_VALIDADA"
    elif n_indep >= 15 and abs(lift) > 0.03 and p_bh < 0.10:
        return "GRADE_B_MODERADA"
    elif n_indep < 15 and rr > 2.0:
        return "GRADE_C_DIAMANTE"
    else:
        return "ESPECULATIVA"


def rareza_tier(n: int) -> str:
    """Classify rarity tier based on sample size."""
    if n >= 30:
        return "NORMAL"
    elif n >= 20:
        return "MARGINAL"
    elif n >= 10:
        return "RARO"
    elif n >= 3:
        return "DIAMANTE"
    else:
        return "ULTRA_RARO"


def compute_state_metrics(
    augment: pd.DataFrame,
    lake: pd.DataFrame,
    station: str,
    state_key: str,
    baselines: Dict[str, float],
) -> Dict[str, Any]:
    """Compute enriched metrics for a single state of a single station."""
    sk_col = f"{station}_sk"
    mask = lake[sk_col] == state_key
    indices = np.where(mask.values)[0]
    n_crudo = len(indices)
    
    if n_crudo == 0:
        return None
    
    # ─── Population & Duration ───────────────────────────────────────────
    pct_tiempo = n_crudo / len(lake) * 100
    
    # Episodes: consecutive runs of this state
    state_bool = mask.values.astype(int)
    diff = np.diff(np.concatenate(([0], state_bool, [0])))
    episode_starts = np.where(diff == 1)[0]
    episode_ends = np.where(diff == -1)[0] - 1
    n_episodes = len(episode_starts)
    durations = episode_ends - episode_starts + 1
    duration_mean = float(durations.mean()) if len(durations) > 0 else 0
    duration_max = int(durations.max()) if len(durations) > 0 else 0
    
    # ─── Enriched metrics per scale ──────────────────────────────────────
    result_scales = {}
    all_p_raw = []
    
    for scale_name, scale_val in ESCALAS.items():
        window = SCALE_WINDOWS[scale_name]
        baseline_hr = baselines[scale_name]
        
        # LONG direction
        hit_col = f"{scale_name}_long_hit"
        fav_col = f"{scale_name}_long_fav"
        mae_col = f"{scale_name}_long_mae"
        mfe_col = f"{scale_name}_long_mfe"
        bars_col = f"{scale_name}_long_bars"
        timeout_col = f"{scale_name}_long_timeout"
        
        # All bars in this state
        hits_all = augment[hit_col].iloc[indices].dropna()
        n_all = len(hits_all)
        
        if n_all == 0:
            result_scales[scale_name] = {
                "n_raw": 0, "n_independent": 0,
                "p_bull": 0.5, "p_bear": 0.5,
                "e_ret_max": 0.0, "e_ret_min": 0.0,
                "ev_net": 0.0, "e_days": 0.0, "ev_per_day": 0.0,
                "rr_asymmetry": 1.0,
                "lift_vs_baseline": 0.0,
                "ci95_lo": 0.0, "ci95_hi": 1.0,
                "p_raw": 1.0, "p_bh": 1.0,
                "mae_min": 0.0, "mae_mean": 0.0, "mae_max": 0.0,
                "mfe_mean": 0.0, "mfe_max": 0.0,
                "grade": "ESPECULATIVA",
                "tier_rareza": "ULTRA_RARO",
            }
            all_p_raw.append(1.0)
            continue
        
        hr_all = float(hits_all.mean())
        
        # De-clustered indices
        valid_indices = hits_all.index
        # Get positional indices in the original array
        pos_indices = np.array([lake.index.get_loc(idx) for idx in valid_indices])
        declustered = decluster_indices(pos_indices, window)
        n_independent = len(declustered)
        
        # HR on de-clustered
        if n_independent > 0:
            hits_indep = augment[hit_col].iloc[declustered].dropna()
            hr_indep = float(hits_indep.mean())
            n_hits_indep = int(hits_indep.sum())
        else:
            hr_indep = hr_all
            n_hits_indep = int(round(hr_all * n_all))
        
        # Lift vs baseline
        lift = hr_indep - baseline_hr
        
        # CI95 Clopper-Pearson on independent N
        ci95_lo, ci95_hi = clopper_pearson_ci(n_hits_indep, n_independent)
        
        # p-value: binomial test vs baseline
        try:
            if n_independent > 0:
                bt = binomtest(n_hits_indep, n_independent, baseline_hr, alternative='two-sided')
                p_raw = float(bt.pvalue)
            else:
                p_raw = 1.0
        except Exception:
            p_raw = 1.0
        all_p_raw.append(p_raw)
        
        # MAE/MFE stats (on all bars, not de-clustered — these are characteristics of the state)
        mae_vals = augment[mae_col].iloc[indices].dropna()
        mfe_vals = augment[mfe_col].iloc[indices].dropna()
        fav_vals = augment[fav_col].iloc[indices].dropna()
        bars_vals = augment[bars_col].iloc[indices].dropna()
        
        mae_min = float(mae_vals.min()) if len(mae_vals) > 0 else 0.0
        mae_mean = float(mae_vals.mean()) if len(mae_vals) > 0 else 0.0
        mae_max = float(mae_vals.max()) if len(mae_vals) > 0 else 0.0
        mfe_mean = float(mfe_vals.mean()) if len(mfe_vals) > 0 else 0.0
        mfe_max = float(mfe_vals.max()) if len(mfe_vals) > 0 else 0.0
        
        # EV metrics (backward compatible)
        p_bull = hr_all  # preserve backward compat — raw HR
        p_bear = 1.0 - hr_all
        
        pos_fav = fav_vals[fav_vals > 0]
        neg_fav = fav_vals[fav_vals <= 0]
        e_ret_max = float(pos_fav.mean()) if len(pos_fav) > 0 else 0.0
        e_ret_min = float(neg_fav.mean()) if len(neg_fav) > 0 else 0.0
        ev_net = float(fav_vals.mean()) if len(fav_vals) > 0 else 0.0
        e_days = float(bars_vals.mean()) if len(bars_vals) > 0 else 0.0
        ev_per_day = ev_net / e_days if e_days > 0 else 0.0
        rr_asymmetry = abs(e_ret_max / e_ret_min) if e_ret_min != 0 else 99.0
        
        n_indep_for_grade = n_independent
        grade = grade_state(n_indep_for_grade, lift, p_raw, rr_asymmetry)
        tier = rareza_tier(n_independent)
        
        result_scales[scale_name] = {
            # Backward-compatible fields
            "n_raw": n_all,
            "p_bull": round(p_bull, 4),
            "p_bear": round(p_bear, 4),
            "e_ret_max": round(e_ret_max, 6),
            "e_ret_min": round(e_ret_min, 6),
            "ev_net": round(ev_net, 6),
            "e_days": round(e_days, 1),
            "ev_per_day": round(ev_per_day, 6),
            "rr_asymmetry": round(rr_asymmetry, 4),
            # NEW enriched fields
            "n_independent": n_independent,
            "hr_independent": round(hr_indep, 4),
            "lift_vs_baseline": round(lift, 4),
            "ci95_lo": round(ci95_lo, 4),
            "ci95_hi": round(ci95_hi, 4),
            "p_raw": round(p_raw, 6),
            "mae_min": round(mae_min, 6),
            "mae_mean": round(mae_mean, 6),
            "mae_max": round(mae_max, 6),
            "mfe_mean": round(mfe_mean, 6),
            "mfe_max": round(mfe_max, 6),
            "grade": grade,
            "tier_rareza": tier,
        }
    
    # BH correction across scales for this state
    p_bh_values = benjamini_hochberg(all_p_raw)
    for i, scale_name in enumerate(ESCALAS):
        if scale_name in result_scales:
            result_scales[scale_name]["p_bh"] = round(p_bh_values[i], 6)
    
    # ─── Determine operational guidance ──────────────────────────────────
    # Use zz50 as primary scale for guidance
    zz50 = result_scales.get("zz50", {})
    p_bull_50 = zz50.get("p_bull", 0.5)
    ev_50 = zz50.get("ev_net", 0.0)
    
    # Divergence regime based on multi-scale agreement
    zz25_bull = result_scales.get("zz25", {}).get("p_bull", 0.5) > 0.5
    zz50_bull = p_bull_50 > 0.5
    zz75_bull = result_scales.get("zz75", {}).get("p_bull", 0.5) > 0.5
    
    if zz25_bull and zz50_bull and zz75_bull:
        div_regime = "FULL_CONVERGENT_BULL"
    elif not zz25_bull and not zz50_bull and not zz75_bull:
        div_regime = "FULL_CONVERGENT_BEAR"
    elif zz25_bull != zz75_bull:
        div_regime = "HORIZON_DIVERGENT"
    else:
        div_regime = "PARTIAL_CONVERGENT"
    
    # Operational guidance
    if p_bull_50 >= 0.60 and ev_50 > 0:
        op_guidance = "STK_ACCUMULATE_STRUCTURAL"
    elif p_bull_50 >= 0.55:
        op_guidance = "STK_HOLD_STABLE"
    elif p_bull_50 <= 0.40 and ev_50 < 0:
        op_guidance = "STK_TRIM_TACTICAL"
    elif p_bull_50 <= 0.35:
        op_guidance = "STK_BLOCK_CRISIS"
    else:
        op_guidance = "STK_HOLD_STABLE"
    
    # If strong conviction with high N
    n_indep_primary = result_scales.get("zz50", {}).get("n_independent", 0)
    if n_indep_primary >= 30 and p_bull_50 >= 0.65:
        op_guidance = "STK_ACCUMULATE_STRUCTURAL_MAX_CONVICTION"
    
    # Stats (value statistics within this state)
    val_col = f"{station}_val" if f"{station}_val" in lake.columns else None
    stats = {}
    if val_col and val_col in lake.columns:
        vals = lake[val_col].iloc[indices].dropna()
        if len(vals) > 0:
            stats = {
                "min": round(float(vals.min()), 4),
                "max": round(float(vals.max()), 4),
                "mean": round(float(vals.mean()), 4),
                "std": round(float(vals.std()), 4),
            }
    
    return {
        "n": n_crudo,
        "stats": stats,
        "divergence_regime": div_regime,
        "operational_guidance": op_guidance,
        # Population metadata (NEW)
        "n_episodes": n_episodes,
        "pct_tiempo": round(pct_tiempo, 2),
        "duration_mean": round(duration_mean, 1),
        "duration_max": duration_max,
        # Per-scale metrics
        **result_scales,
    }


def regenerate_station_fact_store(
    station: str,
    lake: pd.DataFrame,
    augment: pd.DataFrame,
    baselines: Dict[str, float],
) -> Dict[str, Any]:
    """Regenerate enriched fact store for one station."""
    sk_col = f"{station}_sk"
    if sk_col not in lake.columns:
        print(f"  WARNING: {sk_col} not in lake, skipping {station}")
        return {}
    
    # Get all observed state keys
    state_keys = lake[sk_col].dropna().unique()
    state_keys = sorted([str(sk) for sk in state_keys])
    
    print(f"  {station}: {len(state_keys)} states observed")
    
    # Load existing fact store to preserve _documentation
    existing_path = FACT_STORE_DIR / f"{station}_fact_store.json"
    existing_doc = {}
    if existing_path.exists():
        with open(existing_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing_doc = existing.get("_documentation", {})
    
    # Compute enriched metrics for each state
    states = {}
    for sk in state_keys:
        metrics = compute_state_metrics(augment, lake, station, sk, baselines)
        if metrics is not None:
            states[sk] = metrics
    
    # Compute BH correction ACROSS all states for each scale
    for scale_name in ESCALAS:
        p_raws = []
        state_key_order = []
        for sk, sv in states.items():
            if scale_name in sv and "p_raw" in sv[scale_name]:
                p_raws.append(sv[scale_name]["p_raw"])
                state_key_order.append(sk)
        
        if p_raws:
            p_bh_corrected = benjamini_hochberg(p_raws)
            for j, sk in enumerate(state_key_order):
                states[sk][scale_name]["p_bh"] = round(p_bh_corrected[j], 6)
    
    # Build final fact store
    fact_store = {
        "_documentation": existing_doc,
        "station": station.upper(),
        "sample_size": len(lake),
        "states_populated": len(states),
        "baselines": {
            scale: round(hr, 4) for scale, hr in baselines.items()
        },
        "enrichment_metadata": {
            "generated_by": "regenerar_fact_stores.py (Sprint 2)",
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "declustering": "embargo by scale window (zz25=80, zz50=40, zz75=27)",
            "ci_method": "Clopper-Pearson exact",
            "multiple_testing": "Benjamini-Hochberg (q=0.05)",
            "n_states": len(states),
            "n_tests_per_scale": len(states),
        },
        "states": states,
    }
    
    return fact_store


def main():
    print("=" * 70)
    print("SPRINT 2: Regenerar Fact Stores Enriquecidos")
    print("=" * 70)
    
    # ─── Load data ───────────────────────────────────────────────────────
    print("\n[1/3] Loading Lake + Augment...")
    lake = pd.read_parquet(DATA_DIR / "continuous_metar_lake.parquet")
    augment = pd.read_parquet(DATA_DIR / "bar_augment.parquet")
    
    assert len(lake) == len(augment), f"Row mismatch: lake={len(lake)}, augment={len(augment)}"
    assert (lake.index == augment.index).all(), "Index mismatch"
    
    print(f"  Lake: {lake.shape}")
    print(f"  Augment: {augment.shape}")
    
    # ─── Compute baselines ───────────────────────────────────────────────
    print("\n[2/3] Computing unconditional baselines...")
    baselines = compute_baseline_hr(augment)
    for scale, hr in baselines.items():
        print(f"  {scale} long baseline HR: {hr:.4f}")
    
    # ─── Regenerate fact stores ──────────────────────────────────────────
    print("\n[3/3] Regenerating enriched fact stores...")
    t0 = time.time()
    
    summary = []
    for station in STATIONS:
        t_station = time.time()
        fact_store = regenerate_station_fact_store(station, lake, augment, baselines)
        
        if not fact_store:
            continue
        
        # Write enriched fact store
        out_path = FACT_STORE_DIR / f"{station}_fact_store.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fact_store, f, indent=2, ensure_ascii=False, default=str)
        
        n_states = fact_store.get("states_populated", 0)
        elapsed_station = time.time() - t_station
        
        # Count grades
        grades = {}
        for sk, sv in fact_store.get("states", {}).items():
            zz50 = sv.get("zz50", {})
            g = zz50.get("grade", "?")
            grades[g] = grades.get(g, 0) + 1
        
        summary.append({
            "station": station,
            "n_states": n_states,
            "time": elapsed_station,
            "grades": grades,
        })
        
        grade_str = " | ".join(f"{g}:{c}" for g, c in sorted(grades.items()))
        print(f"    → {station:20s}: {n_states:3d} states in {elapsed_station:.1f}s [{grade_str}]")
    
    total_time = time.time() - t0
    
    # ─── Verification ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    
    for station in STATIONS:
        fs_path = FACT_STORE_DIR / f"{station}_fact_store.json"
        assert fs_path.exists(), f"Missing {fs_path}"
        
        with open(fs_path, "r", encoding="utf-8") as f:
            fs = json.load(f)
        
        states = fs.get("states", {})
        assert len(states) > 0, f"{station}: no states"
        
        # Check enriched fields exist
        first_state = list(states.values())[0]
        assert "n_episodes" in first_state, f"{station}: missing n_episodes"
        assert "pct_tiempo" in first_state, f"{station}: missing pct_tiempo"
        
        if "zz50" in first_state:
            zz50 = first_state["zz50"]
            assert "n_independent" in zz50, f"{station}: missing n_independent in zz50"
            assert "lift_vs_baseline" in zz50, f"{station}: missing lift_vs_baseline in zz50"
            assert "ci95_lo" in zz50, f"{station}: missing ci95_lo in zz50"
            assert "p_bh" in zz50, f"{station}: missing p_bh in zz50"
            assert "mae_mean" in zz50, f"{station}: missing mae_mean in zz50"
            assert "grade" in zz50, f"{station}: missing grade in zz50"
            # Backward compat
            assert "p_bull" in zz50, f"{station}: missing p_bull in zz50 (backward compat!)"
            assert "ev_net" in zz50, f"{station}: missing ev_net in zz50 (backward compat!)"
            assert "e_days" in zz50, f"{station}: missing e_days in zz50 (backward compat!)"
            assert "rr_asymmetry" in zz50, f"{station}: missing rr_asymmetry in zz50 (backward compat!)"
    
    print("  ✅ All 11 fact stores verified: enriched + backward compatible")
    
    # Summary
    print(f"\n  Total regeneration time: {total_time:.1f}s")
    total_states = sum(s["n_states"] for s in summary)
    print(f"  Total states across 11 stations: {total_states}")
    
    # Overall grade distribution
    all_grades = {}
    for s in summary:
        for g, c in s["grades"].items():
            all_grades[g] = all_grades.get(g, 0) + c
    print(f"  Grade distribution (zz50): {json.dumps(all_grades, indent=2)}")


if __name__ == "__main__":
    main()
