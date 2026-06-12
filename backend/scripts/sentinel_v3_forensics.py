"""
Sentinel V3 Forensics — Turn Lifecycle Analysis
=================================================
For every zigzag turn, answers:
  ALERTA      (full incoming swing): Did features anticipate? When? Or silence?
  DETECCIÓN   (t=0):                 What does the snapshot look like AT the turn?
  CONFIRMACIÓN (t+1..t+3):           Does the signal persist?
  CONTINUACIÓN (t+4..next turn):     Does the move have legs? Accumulation or Distribution?

No fixed windows. No assumptions. The DATA tells us where alerts cluster.
Per archetype (HL, LL, HH, LH) and per feature set (Kalman / Raw / Both).
"""

import sys
import os
import time
import argparse
import warnings
import numpy as np
import pandas as pd
from datetime import datetime

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
LOG = []
T0 = time.time()


def log(msg=""):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [INFO] {msg}"
    print(line, flush=True)
    LOG.append(line)


def log_section(title):
    log("═" * 100)
    log(f"  {title}")
    log("═" * 100)


# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════
ZZ_SCALE = 0.05  # 5% zigzag
CONFIRM_WINDOW = 3  # t+1..t+3
Z_THRESHOLD = 2.0  # Feature "active" = |z| > 2σ
# NO fixed alert window — we scan the ENTIRE incoming swing

# Features that indicate Accumulation vs Distribution
ACCDIST_FEATURES = [
    "kf_rvol_pred_val", "kf_rvol_filt_vel",        # Volume Kalman
    "kf_tension_pred_val", "kf_tension_filt_vel",  # Price-volume divergence
    "kf_conj_pred_val", "kf_conj_filt_vel",        # Multi-timeframe agreement
    "tension_tide", "tension_current", "tension_wave",
    "conj_wave_tide", "conj_current_tide", "conj_wave_current",
    "vwap_spread_tide_current", "vwap_spread_tide_wave",
]

# Feature groups
KALMAN_FEATURES = [
    "kf_price_pred_val", "kf_price_filt_vel", "kf_price_innovation",
    "kf_rvol_pred_val", "kf_rvol_filt_vel",
    "kf_tension_pred_val", "kf_tension_filt_vel",
    "kf_rsi_pred_val", "kf_rsi_filt_vel",
    "kf_conj_pred_val", "kf_conj_filt_vel",
]

RAW_FEATURES = [
    "rsi_value", "sigma_tide", "sigma_current", "sigma_wave",
    "vwap_sigma_tide", "vwap_sigma_current", "vwap_sigma_wave",
    "vwap_spread_tide_current", "vwap_spread_tide_wave", "vwap_spread_current_wave",
    "tide_slope", "current_slope", "wave_slope",
    "tide_accel", "current_accel", "wave_accel",
    "reg_value_tide", "reg_value_current", "reg_value_wave",
    "conj_wave_tide", "conj_current_tide", "conj_wave_current",
    "tension_tide", "tension_current", "tension_wave",
    "compression_ratio", "fear_level",
]

ALL_FEATURES = KALMAN_FEATURES + RAW_FEATURES

# ═══════════════════════════════════════════════════════════════
# STEP 1: LOAD DATA + BUILD TURN PAIRS
# ═══════════════════════════════════════════════════════════════


def load_data():
    """Load channel_snapshots + zigzag_points from Vault."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

    log_section("STEP 1: LOAD DATA + BUILD TURN PAIRS")
    store = TimescaleDataStore()
    conn = store._conn()
    cur = conn.cursor()

    # 1a. Channel snapshots
    log("  Loading channel_snapshots...")
    feature_cols = ", ".join(ALL_FEATURES)
    cur.execute(f"""
        SELECT ticker, timestamp, {feature_cols}
        FROM engine.channel_snapshots
        WHERE kf_rsi_pred_val IS NOT NULL
          AND timeframe = '1d'
        ORDER BY ticker, timestamp
    """)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    log(f"  Snapshots: {len(df):,} rows × {len(ALL_FEATURES)} features")

    # 1b. Close prices
    log("  Loading OHLCV close prices...")
    cur.execute("""
        SELECT ticker, time::date as trade_date, close
        FROM market.ohlcv_bars
        WHERE timeframe = '1d'
        ORDER BY ticker, time
    """)
    ohlcv = pd.DataFrame(cur.fetchall(), columns=["ticker", "trade_date", "close"])
    ohlcv["trade_date"] = pd.to_datetime(ohlcv["trade_date"])
    ohlcv = ohlcv.drop_duplicates(subset=["ticker", "trade_date"], keep="last")
    df["trade_date"] = df["timestamp"].dt.normalize().dt.tz_localize(None)
    df = df.merge(ohlcv[["ticker", "trade_date", "close"]],
                  on=["ticker", "trade_date"], how="left")
    df.rename(columns={"close": "close_price"}, inplace=True)
    df.drop(columns=["trade_date"], inplace=True)
    log(f"  Close prices matched: {df['close_price'].notna().sum():,}/{len(df):,}")

    # 1c. Zigzag points
    log("  Loading zigzag points...")
    cur.execute("""
        SELECT ticker, timestamp, tp_type, price, swing_return, swing_days
        FROM engine.zigzag_points
        WHERE min_swing_pct = %s
        ORDER BY ticker, timestamp
    """, (ZZ_SCALE,))
    zz = pd.DataFrame(cur.fetchall(),
                       columns=["ticker", "timestamp", "tp_type", "price",
                                "swing_return", "swing_days"])
    zz["timestamp"] = pd.to_datetime(zz["timestamp"], utc=True)
    log(f"  Zigzag: {len(zz):,} turns ({(zz.tp_type=='MIN').sum()} MIN, "
        f"{(zz.tp_type=='MAX').sum()} MAX)")
    log(f"  Swing duration: mean={zz.swing_days.mean():.0f}, "
        f"median={zz.swing_days.median():.0f}, p25={zz.swing_days.quantile(.25):.0f}, "
        f"p75={zz.swing_days.quantile(.75):.0f}")

    store.close()
    return df, zz


def build_turn_pairs(df, zz):
    """Build turn pairs (ZIG/ZAG) and classify archetypes.

    Each turn stores prev_turn_bar_idx = bar index of the PREVIOUS zigzag
    turn (any type), so ALERTA can scan the full incoming swing.
    """
    log_section("STEP 1B: BUILD TURN PAIRS + ARCHETYPES")

    turns = []  # list of dicts with full lifecycle info
    zig_zag_pairs = []
    orphan_zigs = []
    orphan_zags = []

    stats = {"HL": 0, "LL": 0, "HH": 0, "LH": 0, "FIRST": 0, "MATCHED": 0}

    for tk in sorted(df["ticker"].unique()):
        tk_mask = df["ticker"] == tk
        tk_df = df[tk_mask].reset_index(drop=True)
        tk_timestamps = tk_df["timestamp"].values.astype("datetime64[ns]")

        zz_tk = zz[zz["ticker"] == tk].sort_values("timestamp").reset_index(drop=True)
        if len(zz_tk) < 2:
            continue

        # Map each zigzag point to nearest bar index
        prev_min_price = None
        prev_max_price = None
        prev_bar_idx = None  # bar index of the PREVIOUS turn (any type)

        tk_turns_local = []
        for i, row in zz_tk.iterrows():
            zz_ts = np.datetime64(row["timestamp"])
            diffs = np.abs(tk_timestamps - zz_ts)
            bar_idx = int(np.argmin(diffs))

            # Check match quality (should be within 1 day)
            match_days = diffs[bar_idx] / np.timedelta64(1, "D")
            if match_days > 3:
                continue

            # Classify archetype
            archetype = None
            if row["tp_type"] == "MIN":
                if prev_min_price is not None:
                    archetype = "HL" if row["price"] > prev_min_price else "LL"
                    stats[archetype] += 1
                else:
                    stats["FIRST"] += 1
                prev_min_price = row["price"]
            elif row["tp_type"] == "MAX":
                if prev_max_price is not None:
                    archetype = "HH" if row["price"] > prev_max_price else "LH"
                    stats[archetype] += 1
                else:
                    stats["FIRST"] += 1
                prev_max_price = row["price"]

            swing_bars = int(row["swing_days"]) if pd.notna(row["swing_days"]) and row["swing_days"] > 0 else None

            turn = {
                "ticker": tk,
                "zz_idx": i,
                "bar_idx": bar_idx,
                "prev_turn_bar_idx": prev_bar_idx,  # None for first turn
                "timestamp": row["timestamp"],
                "tp_type": row["tp_type"],
                "price": row["price"],
                "swing_return": row["swing_return"],
                "swing_days": swing_bars,
                "archetype": archetype,
                "n_bars_in_ticker": len(tk_df),
            }
            turns.append(turn)
            tk_turns_local.append(turn)
            prev_bar_idx = bar_idx

        # Build ZIG/ZAG pairs for this ticker
        for j in range(len(tk_turns_local) - 1):
            t1 = tk_turns_local[j]
            t2 = tk_turns_local[j + 1]
            if t1["tp_type"] == "MIN" and t2["tp_type"] == "MAX":
                zig_zag_pairs.append(("ZIG", t1, t2))  # up-move
                stats["MATCHED"] += 1
            elif t1["tp_type"] == "MAX" and t2["tp_type"] == "MIN":
                zig_zag_pairs.append(("ZAG", t1, t2))  # down-move
                stats["MATCHED"] += 1

        # Check for orphans (last turn without pair)
        if tk_turns_local and tk_turns_local[-1]["tp_type"] == "MIN":
            orphan_zigs.append(tk_turns_local[-1])
        elif tk_turns_local and tk_turns_local[-1]["tp_type"] == "MAX":
            orphan_zags.append(tk_turns_local[-1])

    log(f"  Archetypes: HL={stats['HL']}  LL={stats['LL']}  "
        f"HH={stats['HH']}  LH={stats['LH']}  FIRST={stats['FIRST']}")
    log(f"  ZIG/ZAG pairs: {len(zig_zag_pairs)} matched, "
        f"{len(orphan_zigs)} orphan zigs, {len(orphan_zags)} orphan zags")

    # Swing duration summary
    swing_durations = [t["swing_days"] for t in turns if t["swing_days"] is not None]
    if swing_durations:
        log(f"  Swing durations: mean={np.mean(swing_durations):.0f}, "
            f"median={np.median(swing_durations):.0f}, "
            f"p25={np.percentile(swing_durations,25):.0f}, "
            f"p75={np.percentile(swing_durations,75):.0f}")

    return turns, zig_zag_pairs, orphan_zigs, orphan_zags, stats


# ═══════════════════════════════════════════════════════════════
# STEP 2: COMPUTE Z-SCORES (per-ticker normalization)
# ═══════════════════════════════════════════════════════════════


def compute_zscores(df, feature_list):
    """Compute per-ticker z-scores for each feature. Returns DataFrame."""
    log(f"  Computing z-scores for {len(feature_list)} features...")
    z_df = pd.DataFrame(index=df.index)

    for tk in df["ticker"].unique():
        tk_mask = df["ticker"] == tk
        tk_vals = df.loc[tk_mask, feature_list].values.astype(np.float64)
        mu = np.nanmean(tk_vals, axis=0)
        sigma = np.nanstd(tk_vals, axis=0)
        sigma[sigma < 1e-8] = 1.0
        z = (tk_vals - mu) / sigma
        z_df.loc[tk_mask, feature_list] = z

    return z_df


# ═══════════════════════════════════════════════════════════════
# STEP 3: LIFECYCLE ANALYSIS PER TURN
# ═══════════════════════════════════════════════════════════════


def analyze_turn_lifecycle(turn, df, z_df, feature_list, next_turn=None):
    """Analyze a single turn across all 4 phases.

    ALERTA scans the ENTIRE incoming swing (prev_turn..t-1) without any
    fixed window. The data tells us where alerts occurred, if at all.
    """
    tk_mask = df["ticker"] == turn["ticker"]
    tk_df = df[tk_mask].reset_index(drop=True)
    tk_z = z_df.loc[tk_mask].reset_index(drop=True)
    bar = turn["bar_idx"]
    n_bars = turn["n_bars_in_ticker"]
    prev_bar = turn["prev_turn_bar_idx"]

    result = {
        "archetype": turn["archetype"],
        "tp_type": turn["tp_type"],
        "ticker": turn["ticker"],
        "timestamp": turn["timestamp"],
        "swing_days": turn["swing_days"],
    }

    # ── ALERTA: scan ENTIRE incoming swing (prev_turn+1 .. t-1) ──
    # No fixed window. We scan all bars in the swing and report
    # WHERE features activated (if at all).
    if prev_bar is not None:
        alert_start = prev_bar + 1  # bar after the previous turn
    else:
        alert_start = max(0, bar - 30)  # first turn: use up to 30 bars back
    alert_end = max(alert_start, bar - 1)  # up to 1 bar before turn
    swing_length = bar - alert_start  # total bars in this swing

    if alert_end >= alert_start and alert_start < n_bars and swing_length > 0:
        alert_z = tk_z.iloc[alert_start:alert_end + 1][feature_list].values
        alert_z = np.nan_to_num(alert_z, nan=0.0)
        active_per_bar = (np.abs(alert_z) > Z_THRESHOLD).sum(axis=1)
        any_active = (active_per_bar > 0)

        result["alert_any_active"] = any_active.any()
        result["alert_max_density"] = int(active_per_bar.max()) if len(active_per_bar) > 0 else 0
        result["alert_bars_with_signal"] = int(any_active.sum())
        result["alert_total_bars"] = swing_length

        if any_active.any():
            # LAST activation before the turn (closest to t=0)
            active_positions = np.where(any_active)[0]
            last_active_pos = active_positions[-1]  # closest to turn
            first_active_pos = active_positions[0]   # earliest in swing
            # Bars before t=0
            result["alert_last_lead_bars"] = swing_length - last_active_pos
            result["alert_first_lead_bars"] = swing_length - first_active_pos
            # Density at the last activation
            result["alert_density_at_last"] = int(active_per_bar[last_active_pos])

            # Which features fired in the last 5 bars of the swing?
            near_turn_start = max(0, len(active_per_bar) - 5)
            near_z = alert_z[near_turn_start:]
            near_activity = (np.abs(near_z) > Z_THRESHOLD).any(axis=0)
            result["alert_near_features"] = [f for f, a in zip(feature_list, near_activity) if a]

            # Which features fired anywhere in the swing?
            all_activity = (np.abs(alert_z) > Z_THRESHOLD).any(axis=0)
            result["alert_all_features"] = [f for f, a in zip(feature_list, all_activity) if a]
        else:
            result["alert_last_lead_bars"] = 0
            result["alert_first_lead_bars"] = 0
            result["alert_density_at_last"] = 0
            result["alert_near_features"] = []
            result["alert_all_features"] = []

        # SILENCE: what fraction of the swing had ZERO features active?
        result["alert_silent_bars"] = int((~any_active).sum())
        result["alert_silence_ratio"] = float((~any_active).sum() / max(swing_length, 1))
    else:
        result["alert_any_active"] = False
        result["alert_max_density"] = 0
        result["alert_bars_with_signal"] = 0
        result["alert_total_bars"] = 0
        result["alert_last_lead_bars"] = 0
        result["alert_first_lead_bars"] = 0
        result["alert_density_at_last"] = 0
        result["alert_near_features"] = []
        result["alert_all_features"] = []
        result["alert_silent_bars"] = 0
        result["alert_silence_ratio"] = 1.0

    # ── DETECCIÓN: t=0 ──
    if 0 <= bar < n_bars:
        det_z = tk_z.iloc[bar][feature_list].values.astype(np.float64)
        det_z = np.nan_to_num(det_z, nan=0.0)
        active_at_t0 = np.abs(det_z) > Z_THRESHOLD
        result["det_density"] = int(active_at_t0.sum())
        result["det_active_features"] = [f for f, a in zip(feature_list, active_at_t0) if a]
        result["det_silent"] = result["det_density"] == 0

        # Raw feature values at t=0 (all features, for deep analysis)
        result["det_raw_values"] = {f: float(tk_df.iloc[bar][f]) if f in tk_df.columns else np.nan
                                    for f in feature_list}
    else:
        result["det_density"] = 0
        result["det_active_features"] = []
        result["det_silent"] = True
        result["det_raw_values"] = {}

    # ── CONFIRMACIÓN: t+1..t+3 ──
    conf_start = bar + 1
    conf_end = min(bar + CONFIRM_WINDOW, n_bars - 1)
    if conf_start <= conf_end and conf_start < n_bars:
        conf_z = tk_z.iloc[conf_start:conf_end + 1][feature_list].values
        conf_z = np.nan_to_num(conf_z, nan=0.0)
        active_per_bar = (np.abs(conf_z) > Z_THRESHOLD).sum(axis=1)
        result["conf_persists"] = (active_per_bar > 0).any()
        result["conf_density_mean"] = float(active_per_bar.mean())
        result["conf_density_trend"] = "INCREASING" if len(active_per_bar) >= 2 and active_per_bar[-1] > active_per_bar[0] else \
                                       "DECREASING" if len(active_per_bar) >= 2 and active_per_bar[-1] < active_per_bar[0] else "FLAT"
    else:
        result["conf_persists"] = False
        result["conf_density_mean"] = 0.0
        result["conf_density_trend"] = "N/A"

    # ── CONTINUACIÓN: t+4..next opposite turn ──
    cont_start = bar + CONFIRM_WINDOW + 1
    if next_turn is not None:
        cont_end = min(next_turn["bar_idx"], n_bars - 1)
    else:
        cont_end = min(bar + 60, n_bars - 1)  # max 60 bars if no next turn

    if cont_start < cont_end and cont_start < n_bars:
        # Price trajectory
        close_at_turn = tk_df.iloc[bar]["close_price"] if pd.notna(tk_df.iloc[bar]["close_price"]) else np.nan
        if pd.notna(close_at_turn) and close_at_turn > 0:
            cont_prices = tk_df.iloc[cont_start:cont_end + 1]["close_price"].values
            cont_prices = cont_prices[~np.isnan(cont_prices)]
            if len(cont_prices) > 0:
                if turn["tp_type"] == "MIN":
                    max_favorable = (cont_prices.max() / close_at_turn - 1) * 100
                    final_ret = (cont_prices[-1] / close_at_turn - 1) * 100
                else:
                    max_favorable = (1 - cont_prices.min() / close_at_turn) * 100
                    final_ret = (1 - cont_prices[-1] / close_at_turn) * 100

                result["cont_max_favorable_pct"] = float(max_favorable)
                result["cont_final_ret_pct"] = float(final_ret)
                result["cont_duration_bars"] = int(cont_end - cont_start + 1)
                result["cont_healthy"] = max_favorable > 5.0
            else:
                result["cont_max_favorable_pct"] = 0.0
                result["cont_final_ret_pct"] = 0.0
                result["cont_duration_bars"] = 0
                result["cont_healthy"] = False
        else:
            result["cont_max_favorable_pct"] = 0.0
            result["cont_final_ret_pct"] = 0.0
            result["cont_duration_bars"] = 0
            result["cont_healthy"] = False

        # Feature exhaustion: when do features stop being active?
        cont_z = tk_z.iloc[cont_start:min(cont_end + 1, n_bars)][feature_list].values
        cont_z = np.nan_to_num(cont_z, nan=0.0)
        active_per_bar = (np.abs(cont_z) > Z_THRESHOLD).sum(axis=1)
        if len(active_per_bar) > 0 and active_per_bar[0] > 0:
            exhaustion_idx = np.where(active_per_bar == 0)[0]
            if len(exhaustion_idx) > 0:
                result["cont_signal_exhaustion_bar"] = int(exhaustion_idx[0])
            else:
                result["cont_signal_exhaustion_bar"] = len(active_per_bar)
        else:
            result["cont_signal_exhaustion_bar"] = 0

        # ── ACCUMULATION vs DISTRIBUTION ──
        # After a turn, do volume/tension/conjugation features suggest
        # smart money is accumulating (building positions) or distributing (exiting)?
        accdist_in_list = [f for f in ACCDIST_FEATURES if f in feature_list]
        if accdist_in_list and cont_start < n_bars:
            ad_end = min(cont_start + 10, cont_end + 1, n_bars)  # first 10 bars of continuation
            ad_vals = tk_df.iloc[cont_start:ad_end][accdist_in_list].values.astype(np.float64)
            ad_vals = np.nan_to_num(ad_vals, nan=0.0)
            if len(ad_vals) >= 3:
                # Volume trend: is relative volume increasing or decreasing?
                vol_feats = [f for f in ["kf_rvol_pred_val", "kf_rvol_filt_vel"] if f in accdist_in_list]
                vol_trend = 0.0
                for vf in vol_feats:
                    vi = accdist_in_list.index(vf)
                    v = ad_vals[:, vi]
                    if len(v) >= 3:
                        slope = np.polyfit(range(len(v)), v, 1)[0]
                        vol_trend += slope

                # Tension trend: price-volume divergence
                tension_feats = [f for f in ["kf_tension_pred_val", "tension_tide", "tension_current"] if f in accdist_in_list]
                tension_trend = 0.0
                for tf in tension_feats:
                    ti = accdist_in_list.index(tf)
                    v = ad_vals[:, ti]
                    if len(v) >= 3:
                        tension_trend += np.polyfit(range(len(v)), v, 1)[0]

                # Conjugation trend: multi-timeframe agreement
                conj_feats = [f for f in ["kf_conj_pred_val", "conj_wave_tide", "conj_current_tide"] if f in accdist_in_list]
                conj_trend = 0.0
                for cf in conj_feats:
                    ci = accdist_in_list.index(cf)
                    v = ad_vals[:, ci]
                    if len(v) >= 3:
                        conj_trend += np.polyfit(range(len(v)), v, 1)[0]

                # Classification:
                # After MIN (bottom): accumulation = rising volume + rising conjugation
                # After MAX (top): distribution = rising volume + falling conjugation
                if turn["tp_type"] == "MIN":
                    # Accumulation: volume rising AND conjugation aligning (positive)
                    is_accumulation = vol_trend > 0 and conj_trend > 0
                    is_distribution = vol_trend > 0 and conj_trend < 0
                else:
                    # Distribution: volume rising AND conjugation breaking (negative)
                    is_distribution = vol_trend > 0 and conj_trend < 0
                    is_accumulation = vol_trend > 0 and conj_trend > 0

                if is_accumulation:
                    result["cont_accdist"] = "ACCUMULATION"
                elif is_distribution:
                    result["cont_accdist"] = "DISTRIBUTION"
                else:
                    result["cont_accdist"] = "NEUTRAL"
                result["cont_vol_trend"] = float(vol_trend)
                result["cont_tension_trend"] = float(tension_trend)
                result["cont_conj_trend"] = float(conj_trend)
            else:
                result["cont_accdist"] = "INSUFFICIENT_DATA"
                result["cont_vol_trend"] = 0.0
                result["cont_tension_trend"] = 0.0
                result["cont_conj_trend"] = 0.0
        else:
            result["cont_accdist"] = "N/A"
            result["cont_vol_trend"] = 0.0
            result["cont_tension_trend"] = 0.0
            result["cont_conj_trend"] = 0.0
    else:
        result["cont_max_favorable_pct"] = 0.0
        result["cont_final_ret_pct"] = 0.0
        result["cont_duration_bars"] = 0
        result["cont_healthy"] = False
        result["cont_signal_exhaustion_bar"] = 0
        result["cont_accdist"] = "N/A"
        result["cont_vol_trend"] = 0.0
        result["cont_tension_trend"] = 0.0
        result["cont_conj_trend"] = 0.0

    return result


# ═══════════════════════════════════════════════════════════════
# STEP 4: AGGREGATE RESULTS
# ═══════════════════════════════════════════════════════════════


def aggregate_results(results, label):
    """Print aggregate statistics grouped by archetype."""
    log_section(f"RESULTS: {label}")

    archetypes = ["LL", "HL", "HH", "LH"]
    for arch in archetypes:
        arch_res = [r for r in results if r["archetype"] == arch]
        if not arch_res:
            continue

        n = len(arch_res)
        tp = arch_res[0]["tp_type"]
        log(f"\n  ╔══════════════════════════════════════════════════════════════╗")
        log(f"  ║  {arch} ({tp}) — {n} turns                                  ")
        log(f"  ╚══════════════════════════════════════════════════════════════╝")

        # ALERTA — full swing scan, no fixed window
        alert_any = sum(1 for r in arch_res if r["alert_any_active"])
        alert_none = n - alert_any
        alert_rate = alert_any / n * 100
        last_leads = [r["alert_last_lead_bars"] for r in arch_res if r["alert_any_active"]]
        first_leads = [r["alert_first_lead_bars"] for r in arch_res if r["alert_any_active"]]
        swing_lengths = [r["alert_total_bars"] for r in arch_res]
        silence_ratios = [r["alert_silence_ratio"] for r in arch_res]

        log(f"\n  ── ALERTA (full incoming swing, no fixed window) ──")
        log(f"    Swing scanned:     mean={np.mean(swing_lengths):.0f} bars, "
            f"median={np.median(swing_lengths):.0f} bars")
        log(f"    Any feature fired:  {alert_rate:.1f}% ({alert_any}/{n})")
        log(f"    Complete silence:   {alert_none/n*100:.1f}% ({alert_none}/{n}) — NO features fired in entire swing")
        if last_leads:
            log(f"    Last alert before turn:  mean={np.mean(last_leads):.1f} bars, "
                f"median={np.median(last_leads):.0f}, p25={np.percentile(last_leads,25):.0f}, "
                f"p75={np.percentile(last_leads,75):.0f}")
            log(f"    First alert in swing:    mean={np.mean(first_leads):.1f} bars before turn")
        log(f"    Silence ratio:     mean={np.mean(silence_ratios)*100:.0f}% of swing bars had ZERO features active")

        # Lead time distribution (WHERE do alerts actually cluster?)
        if last_leads:
            log(f"    Lead time distribution (bars before turn):")
            for bucket in [1, 2, 3, 5, 7, 10, 15, 20]:
                n_in = sum(1 for l in last_leads if l <= bucket)
                log(f"      ≤{bucket:>2d} bars: {n_in:>4}/{len(last_leads)} = {n_in/len(last_leads)*100:.0f}%")

        # Top features that fire NEAR the turn (last 5 bars)
        near_feature_counts = {}
        for r in arch_res:
            for f in r.get("alert_near_features", []):
                near_feature_counts[f] = near_feature_counts.get(f, 0) + 1
        if near_feature_counts:
            top_near = sorted(near_feature_counts.items(), key=lambda x: -x[1])[:5]
            log(f"    Top features near turn (last 5 bars of swing):")
            for feat, cnt in top_near:
                log(f"      {feat:<35} fires in {cnt/n*100:.0f}% of turns")

        # Top features anywhere in the swing
        all_feature_counts = {}
        for r in arch_res:
            for f in r.get("alert_all_features", []):
                all_feature_counts[f] = all_feature_counts.get(f, 0) + 1
        if all_feature_counts:
            top_all = sorted(all_feature_counts.items(), key=lambda x: -x[1])[:5]
            log(f"    Top features anywhere in swing:")
            for feat, cnt in top_all:
                log(f"      {feat:<35} fires in {cnt/n*100:.0f}% of turns")

        # DETECCIÓN
        det_densities = [r["det_density"] for r in arch_res]
        det_silent = sum(1 for r in arch_res if r["det_silent"])
        det_with_signal = sum(1 for r in arch_res if r["det_density"] >= 2)

        log(f"\n  ── DETECCIÓN (t=0) ──")
        log(f"    Detection Rate (≥2 features): {det_with_signal/n*100:.1f}% ({det_with_signal}/{n})")
        log(f"    Silent at t=0 (density=0):    {det_silent/n*100:.1f}% ({det_silent}/{n})")
        log(f"    Density at t=0:  mean={np.mean(det_densities):.1f}, "
            f"median={np.median(det_densities):.0f}, "
            f"p75={np.percentile(det_densities, 75):.0f}")

        # Top features active at t=0
        det_feature_counts = {}
        for r in arch_res:
            for f in r["det_active_features"]:
                det_feature_counts[f] = det_feature_counts.get(f, 0) + 1
        if det_feature_counts:
            top_det = sorted(det_feature_counts.items(), key=lambda x: -x[1])[:5]
            log(f"    Top Detection Features:")
            for feat, cnt in top_det:
                log(f"      {feat:<35} active in {cnt/n*100:.0f}% of turns")

        # CONFIRMACIÓN
        conf_persists = sum(1 for r in arch_res if r["conf_persists"])
        conf_means = [r["conf_density_mean"] for r in arch_res]
        trends = [r["conf_density_trend"] for r in arch_res]
        n_inc = sum(1 for t in trends if t == "INCREASING")
        n_dec = sum(1 for t in trends if t == "DECREASING")

        log(f"\n  ── CONFIRMACIÓN (t+1..t+{CONFIRM_WINDOW}) ──")
        log(f"    Persistence Rate: {conf_persists/n*100:.1f}% ({conf_persists}/{n})")
        log(f"    Density mean:     {np.mean(conf_means):.1f}")
        log(f"    Trend:            INCREASING={n_inc/n*100:.0f}%, "
            f"DECREASING={n_dec/n*100:.0f}%")

        # CONTINUACIÓN + ACUMULACIÓN/DISTRIBUCIÓN
        cont_fav = [r["cont_max_favorable_pct"] for r in arch_res]
        cont_ret = [r["cont_final_ret_pct"] for r in arch_res]
        cont_dur = [r["cont_duration_bars"] for r in arch_res]
        cont_healthy = sum(1 for r in arch_res if r["cont_healthy"])
        cont_exhaust = [r["cont_signal_exhaustion_bar"] for r in arch_res
                        if r["cont_signal_exhaustion_bar"] > 0]

        log(f"\n  ── CONTINUACIÓN (t+{CONFIRM_WINDOW+1}..next turn) ──")
        log(f"    Healthy Moves (>5%): {cont_healthy/n*100:.1f}% ({cont_healthy}/{n})")
        log(f"    Max Favorable Excursion:  mean={np.mean(cont_fav):.1f}%, "
            f"median={np.median(cont_fav):.1f}%")
        log(f"    Final Return:            mean={np.mean(cont_ret):.1f}%, "
            f"median={np.median(cont_ret):.1f}%")
        log(f"    Move Duration:           mean={np.mean(cont_dur):.0f} bars, "
            f"median={np.median(cont_dur):.0f} bars")
        if cont_exhaust:
            log(f"    Signal Exhaustion:       mean={np.mean(cont_exhaust):.0f} bars, "
                f"median={np.median(cont_exhaust):.0f} bars")

        # Accumulation vs Distribution
        n_acc = sum(1 for r in arch_res if r.get("cont_accdist") == "ACCUMULATION")
        n_dist = sum(1 for r in arch_res if r.get("cont_accdist") == "DISTRIBUTION")
        n_neutral = sum(1 for r in arch_res if r.get("cont_accdist") == "NEUTRAL")

        log(f"\n  ── ACUMULACIÓN / DISTRIBUCIÓN (first 10 bars of continuation) ──")
        log(f"    ACCUMULATION:  {n_acc:>4}/{n} = {n_acc/n*100:.0f}%")
        log(f"    DISTRIBUTION:  {n_dist:>4}/{n} = {n_dist/n*100:.0f}%")
        log(f"    NEUTRAL:       {n_neutral:>4}/{n} = {n_neutral/n*100:.0f}%")

        # Cross-tabulate: does accumulation predict healthy continuation?
        acc_healthy = sum(1 for r in arch_res
                          if r.get("cont_accdist") == "ACCUMULATION" and r["cont_healthy"])
        dist_healthy = sum(1 for r in arch_res
                           if r.get("cont_accdist") == "DISTRIBUTION" and r["cont_healthy"])
        if n_acc > 0:
            log(f"    ACC → healthy:   {acc_healthy}/{n_acc} = {acc_healthy/n_acc*100:.0f}%")
        if n_dist > 0:
            log(f"    DIST → healthy:  {dist_healthy}/{n_dist} = {dist_healthy/n_dist*100:.0f}%")

        # Avg returns by acc/dist
        acc_rets = [r["cont_max_favorable_pct"] for r in arch_res
                    if r.get("cont_accdist") == "ACCUMULATION"]
        dist_rets = [r["cont_max_favorable_pct"] for r in arch_res
                     if r.get("cont_accdist") == "DISTRIBUTION"]
        if acc_rets:
            log(f"    ACC avg MFE:     {np.mean(acc_rets):.1f}%")
        if dist_rets:
            log(f"    DIST avg MFE:    {np.mean(dist_rets):.1f}%")

        # Combined funnel
        alerted_and_detected = sum(1 for r in arch_res
                                   if r["alert_any_active"] and r["det_density"] >= 2)
        alerted_detected_confirmed = sum(1 for r in arch_res
                                         if r["alert_any_active"] and r["det_density"] >= 2
                                         and r["conf_persists"])
        full_funnel = sum(1 for r in arch_res
                          if r["alert_any_active"] and r["det_density"] >= 2
                          and r["conf_persists"] and r["cont_healthy"])

        log(f"\n  ── FUNNEL ──")
        log(f"    ALERTA                            {alert_any:>4}/{n} = {alert_any/n*100:.0f}%")
        log(f"    + DETECCIÓN (≥2)                  {alerted_and_detected:>4}/{n} = {alerted_and_detected/n*100:.0f}%")
        log(f"    + CONFIRMACIÓN                    {alerted_detected_confirmed:>4}/{n} = {alerted_detected_confirmed/n*100:.0f}%")
        log(f"    + CONTINUACIÓN saludable (>5%)    {full_funnel:>4}/{n} = {full_funnel/n*100:.0f}%")


def report_zigzag_integrity(pairs, orphan_zigs, orphan_zags, turns):
    """Report zig-zag completeness and direction accuracy."""
    log_section("ZIG-ZAG INTEGRITY REPORT")

    n_zig = sum(1 for p in pairs if p[0] == "ZIG")
    n_zag = sum(1 for p in pairs if p[0] == "ZAG")
    log(f"  ZIG (MIN→MAX, up-moves):   {n_zig}")
    log(f"  ZAG (MAX→MIN, down-moves): {n_zag}")
    log(f"  Orphan ZIGs (MIN without following MAX): {len(orphan_zigs)}")
    log(f"  Orphan ZAGs (MAX without following MIN): {len(orphan_zags)}")

    # Direction accuracy: ZIGs where the end price < start price (should go up but didn't)
    zig_wrong_direction = 0
    zag_wrong_direction = 0
    for direction, t1, t2 in pairs:
        if direction == "ZIG" and t2["price"] < t1["price"]:
            zig_wrong_direction += 1
        elif direction == "ZAG" and t2["price"] > t1["price"]:
            zag_wrong_direction += 1

    # Note: by construction of zigzag, ZIG always goes up and ZAG always goes down
    # But we can check: after a ZIG, does the next ZAG go below the ZIG start?
    log(f"\n  Direction checks (by construction, zigzag enforces direction):")
    log(f"    ZIGs with end < start (impossible by construction): {zig_wrong_direction}")
    log(f"    ZAGs with end > start (impossible by construction): {zag_wrong_direction}")

    # More interesting: ZIG/ZAG magnitude distribution
    zig_returns = [abs(t2["price"] / t1["price"] - 1) * 100
                   for d, t1, t2 in pairs if d == "ZIG" and t1["price"] > 0]
    zag_returns = [abs(t2["price"] / t1["price"] - 1) * 100
                   for d, t1, t2 in pairs if d == "ZAG" and t1["price"] > 0]

    if zig_returns:
        log(f"\n  ZIG magnitude: mean={np.mean(zig_returns):.1f}%, "
            f"median={np.median(zig_returns):.1f}%, "
            f"p75={np.percentile(zig_returns, 75):.1f}%")
    if zag_returns:
        log(f"  ZAG magnitude: mean={np.mean(zag_returns):.1f}%, "
            f"median={np.median(zag_returns):.1f}%, "
            f"p75={np.percentile(zag_returns, 75):.1f}%")

    # Asymmetry: how many ZIGs are bigger than their preceding ZAG?
    zig_bigger = 0
    zag_bigger = 0
    for i in range(1, len(pairs)):
        if pairs[i][0] == "ZIG" and pairs[i-1][0] == "ZAG":
            zig_mag = abs(pairs[i][2]["price"] / pairs[i][1]["price"] - 1)
            zag_mag = abs(pairs[i-1][2]["price"] / pairs[i-1][1]["price"] - 1)
            if zig_mag > zag_mag:
                zig_bigger += 1
            else:
                zag_bigger += 1

    log(f"\n  Asymmetry (ZIG vs preceding ZAG):")
    total = zig_bigger + zag_bigger
    if total > 0:
        log(f"    ZIG bigger: {zig_bigger}/{total} ({zig_bigger/total*100:.0f}%)")
        log(f"    ZAG bigger: {zag_bigger}/{total} ({zag_bigger/total*100:.0f}%)")


# ═══════════════════════════════════════════════════════════════
# SIGNAL-FIRST PRECISION ANALYSIS
# ═══════════════════════════════════════════════════════════════


def signal_first_analysis(df, z_df, feature_list, turns, label="ALL"):
    """For every bar where a feature fires, ask: where is it in the swing?

    Phases (user-defined, forensic-validated):
      - DETECCIÓN:    t=0, activation at the turn bar
      - CONFIRMACIÓN: t+1..t+2, does the turn persist?
      - ALERTA:       t-3..t-1, ≤3 bars before next turn (diffuse, may not occur)
      - CONTINUACIÓN: t+3 onward, the body of the healthy move

    Priority: DETECCIÓN > CONFIRMACIÓN > ALERTA > CONTINUACIÓN
    For short swings where CONF and ALERTA zones overlap, CONF wins
    (confirming the turn that happened > alerting the next one).
    """
    log_section(f"SIGNAL-FIRST PRECISION ({label})")
    log(f"\n  For each feature activation (|z| > {Z_THRESHOLD}σ):")
    log(f"  → DETECCIÓN:    t=0 (exact turn bar)")
    log(f"  → CONFIRMACIÓN: t+1..t+2 (1-2 bars after prev turn)")
    log(f"  → ALERTA:       t-3..t-1 (≤3 bars before next turn)")
    log(f"  → CONTINUACIÓN: t+3+ (body of the move, everything else)")
    log(f"  Priority: DET > CONF > ALERTA > CONT")

    # Build turn index per ticker
    turn_index = {}
    for t in turns:
        if t["archetype"] is None:
            continue
        turn_index.setdefault(t["ticker"], []).append(
            (t["bar_idx"], t["archetype"], t["tp_type"])
        )
    for tk in turn_index:
        turn_index[tk].sort(key=lambda x: x[0])

    feature_results = {}

    for feat in feature_list:
        total_activations = 0
        phase_counts = {}
        for arch in ["LL", "HL", "HH", "LH"]:
            phase_counts[arch] = {
                "ALERTA": 0, "DETECCION": 0, "CONFIRMACION": 0, "CONTINUACION": 0,
            }
        phase_counts["INDET"] = 0

        alerta_distances = {a: [] for a in ["LL", "HL", "HH", "LH"]}
        continuacion_distances = {a: [] for a in ["LL", "HL", "HH", "LH"]}

        for tk in df["ticker"].unique():
            tk_mask = df["ticker"] == tk
            tk_z = z_df.loc[tk_mask].reset_index(drop=True)
            tk_turns = turn_index.get(tk, [])
            if not tk_turns:
                continue

            z_vals = tk_z[feat].values.astype(np.float64)
            z_vals = np.nan_to_num(z_vals, nan=0.0)
            active_bars = np.where(np.abs(z_vals) > Z_THRESHOLD)[0]
            turn_bar_indices = np.array([t[0] for t in tk_turns])

            for bar in active_bars:
                total_activations += 1
                pos = np.searchsorted(turn_bar_indices, bar)

                # DETECCIÓN: exact match at turn (t=0)
                if pos < len(tk_turns) and tk_turns[pos][0] == bar:
                    arch = tk_turns[pos][1]
                    phase_counts[arch]["DETECCION"] += 1
                    continue

                # Find previous and next turns
                prev_turn = tk_turns[pos - 1] if pos > 0 else None
                next_turn = tk_turns[pos] if pos < len(tk_turns) else None

                prev_dist = (bar - prev_turn[0]) if prev_turn else None
                next_dist = (next_turn[0] - bar) if next_turn else None

                # --- BETWEEN TWO TURNS ---
                if prev_turn is not None and next_turn is not None:

                    # CONFIRMACIÓN: t+1..t+2 (1-2 bars after prev turn)
                    # Takes priority over ALERTA in short swings
                    if prev_dist <= 2:
                        phase_counts[prev_turn[1]]["CONFIRMACION"] += 1
                        continue

                    # ALERTA: ≤3 bars before next turn
                    if next_dist <= 3:
                        phase_counts[next_turn[1]]["ALERTA"] += 1
                        alerta_distances[next_turn[1]].append(int(next_dist))
                        continue

                    # CONTINUACIÓN: everything else (t+3 onward, body of the move)
                    phase_counts[prev_turn[1]]["CONTINUACION"] += 1
                    continuacion_distances[prev_turn[1]].append(int(prev_dist))
                    continue

                # --- EDGE: only previous turn ---
                elif prev_turn is not None:
                    if prev_dist <= 2:
                        phase_counts[prev_turn[1]]["CONFIRMACION"] += 1
                    else:
                        phase_counts[prev_turn[1]]["CONTINUACION"] += 1
                        continuacion_distances[prev_turn[1]].append(int(prev_dist))
                    continue

                # --- EDGE: only next turn ---
                elif next_turn is not None:
                    if next_dist <= 3:
                        phase_counts[next_turn[1]]["ALERTA"] += 1
                        alerta_distances[next_turn[1]].append(int(next_dist))
                    else:
                        phase_counts["INDET"] += 1
                    continue

                # No turns at all
                phase_counts["INDET"] += 1

        feature_results[feat] = {
            "total": total_activations,
            "phase_counts": phase_counts,
            "alerta_distances": alerta_distances,
            "continuacion_distances": continuacion_distances,
        }

    # ── REPORT ──
    log(f"\n  {'─'*120}")
    log(f"  {'Feature':<35} {'Total':<8} {'INDET':<8} {'IND%':<8} "
        f"{'LL_det':<8} {'HL_det':<8} {'HH_det':<8} {'LH_det':<8} "
        f"{'LL_prc%':<8} {'HL_prc%':<8} {'HH_prc%':<8} {'LH_prc%':<8}")
    log(f"  {'─'*35} {'─'*8} {'─'*8} {'─'*8} "
        f"{'─'*8} {'─'*8} {'─'*8} {'─'*8} "
        f"{'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    for feat in feature_list:
        r = feature_results[feat]
        total = r["total"]
        if total == 0:
            continue
        indet = r["phase_counts"]["INDET"]
        indet_pct = indet / total * 100

        # Detection counts (DETECCIÓN only — the most precise phase)
        det = {}
        # Total TP per archetype (all phases combined)
        tp_all = {}
        for arch in ["LL", "HL", "HH", "LH"]:
            det[arch] = r["phase_counts"][arch]["DETECCION"]
            tp_all[arch] = sum(r["phase_counts"][arch].values())

        # Precision = (ALERTA + DETECCIÓN + CONFIRMACIÓN) / total
        # i.e., activations near a turn of this type vs all activations
        prec = {}
        for arch in ["LL", "HL", "HH", "LH"]:
            near_turn = (r["phase_counts"][arch]["ALERTA"] +
                         r["phase_counts"][arch]["DETECCION"] +
                         r["phase_counts"][arch]["CONFIRMACION"])
            prec[arch] = near_turn / total * 100 if total > 0 else 0

        log(f"  {feat:<35} {total:<8} {indet:<8} {indet_pct:<8.0f} "
            f"{det['LL']:<8} {det['HL']:<8} {det['HH']:<8} {det['LH']:<8} "
            f"{prec['LL']:<8.1f} {prec['HL']:<8.1f} {prec['HH']:<8.1f} {prec['LH']:<8.1f}")

    # ── DETAILED PHASE BREAKDOWN per archetype ──
    for arch in ["LL", "HL", "HH", "LH"]:
        tp_type = "MIN" if arch in ["LL", "HL"] else "MAX"
        log(f"\n  ╔══════════════════════════════════════════════════════════════╗")
        log(f"  ║  {arch} ({tp_type}) — Signal-First Breakdown                    ║")
        log(f"  ╚══════════════════════════════════════════════════════════════╝")

        log(f"\n  {'Feature':<35} {'ALERTA':<10} {'DETEC':<10} {'CONF':<10} {'CONT':<10} "
            f"{'Turn%':<10} {'Alert dist':<15}")
        log(f"  {'─'*35} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*15}")

        ranked = []
        for feat in feature_list:
            r = feature_results[feat]
            total = r["total"]
            if total == 0:
                continue
            pc = r["phase_counts"][arch]
            near_turn = pc["ALERTA"] + pc["DETECCION"] + pc["CONFIRMACION"]
            turn_pct = near_turn / total * 100 if total > 0 else 0
            ranked.append((feat, pc, turn_pct, total, r["alerta_distances"][arch]))

        # Sort by turn% (precision for this archetype)
        ranked.sort(key=lambda x: -x[2])

        for feat, pc, turn_pct, total, a_dists in ranked[:15]:
            dist_str = ""
            if a_dists:
                dist_str = f"med={np.median(a_dists):.0f}, μ={np.mean(a_dists):.0f}"
            log(f"  {feat:<35} {pc['ALERTA']:<10} {pc['DETECCION']:<10} "
                f"{pc['CONFIRMACION']:<10} {pc['CONTINUACION']:<10} "
                f"{turn_pct:<10.1f} {dist_str:<15}")

        # ALERTA distance distribution for this archetype
        all_a_dists = []
        for feat in feature_list:
            all_a_dists.extend(feature_results[feat]["alerta_distances"][arch])
        if all_a_dists:
            log(f"\n  {arch} ALERTA distance distribution (bars before turn):")
            log(f"    n={len(all_a_dists)}, mean={np.mean(all_a_dists):.1f}, "
                f"median={np.median(all_a_dists):.0f}, "
                f"p25={np.percentile(all_a_dists,25):.0f}, "
                f"p75={np.percentile(all_a_dists,75):.0f}")
            for bucket in [1, 2, 3, 5, 7, 10, 15, 20, 30]:
                n_in = sum(1 for d in all_a_dists if d <= bucket)
                log(f"    ≤{bucket:>2d} bars: {n_in:>6}/{len(all_a_dists)} = "
                    f"{n_in/len(all_a_dists)*100:.0f}%")

        # CONTINUACIÓN distance distribution for this archetype
        all_c_dists = []
        for feat in feature_list:
            all_c_dists.extend(feature_results[feat]["continuacion_distances"][arch])
        if all_c_dists:
            log(f"\n  {arch} CONTINUACIÓN distance distribution (bars after turn):")
            log(f"    n={len(all_c_dists)}, mean={np.mean(all_c_dists):.1f}, "
                f"median={np.median(all_c_dists):.0f}, "
                f"p25={np.percentile(all_c_dists,25):.0f}, "
                f"p75={np.percentile(all_c_dists,75):.0f}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════


def main():
    log_section("SENTINEL V3 FORENSICS — TURN LIFECYCLE ANALYSIS")
    log(f"  Zigzag scale: {ZZ_SCALE*100:.0f}%")
    log(f"  Alert window: FULL INCOMING SWING (no fixed window)")
    log(f"  z-threshold: ±{Z_THRESHOLD}σ")
    log(f"  Confirmation window: t+1..t+{CONFIRM_WINDOW}")
    log(f"  Acc/Dist features: {len(ACCDIST_FEATURES)} (volume, tension, conjugation)")
    log(f"  Feature groups: Kalman={len(KALMAN_FEATURES)}, Raw={len(RAW_FEATURES)}, "
        f"Total={len(ALL_FEATURES)}")

    # Load
    df, zz = load_data()

    # Build pairs
    turns, pairs, orphan_zigs, orphan_zags, stats = build_turn_pairs(df, zz)

    # Filter to turns with archetypes (exclude FIRST)
    classified_turns = [t for t in turns if t["archetype"] is not None]
    log(f"  Classified turns for analysis: {len(classified_turns)}")

    # Build next-turn lookup per ticker
    turns_by_ticker = {}
    for t in turns:
        turns_by_ticker.setdefault(t["ticker"], []).append(t)

    # ═══════════════════════════════════════════════════════════
    # RUN 1: ALL FEATURES
    # ═══════════════════════════════════════════════════════════
    log_section("ANALYSIS 1: ALL FEATURES (Kalman + Raw)")
    z_all = compute_zscores(df, ALL_FEATURES)

    results_all = []
    for t in classified_turns:
        tk_turns = turns_by_ticker[t["ticker"]]
        # Find next opposite-type turn
        next_turn = None
        for t2 in tk_turns:
            if t2["bar_idx"] > t["bar_idx"] and t2["tp_type"] != t["tp_type"]:
                next_turn = t2
                break
        r = analyze_turn_lifecycle(t, df, z_all, ALL_FEATURES, next_turn)
        results_all.append(r)

    aggregate_results(results_all, "ALL FEATURES (Kalman + Raw)")

    # ═══════════════════════════════════════════════════════════
    # RUN 2: KALMAN FEATURES ONLY
    # ═══════════════════════════════════════════════════════════
    log_section("ANALYSIS 2: KALMAN FEATURES ONLY")
    z_kalman = compute_zscores(df, KALMAN_FEATURES)

    results_kalman = []
    for t in classified_turns:
        tk_turns = turns_by_ticker[t["ticker"]]
        next_turn = None
        for t2 in tk_turns:
            if t2["bar_idx"] > t["bar_idx"] and t2["tp_type"] != t["tp_type"]:
                next_turn = t2
                break
        r = analyze_turn_lifecycle(t, df, z_kalman, KALMAN_FEATURES, next_turn)
        results_kalman.append(r)

    aggregate_results(results_kalman, "KALMAN FEATURES ONLY")

    # ═══════════════════════════════════════════════════════════
    # RUN 3: RAW FEATURES ONLY
    # ═══════════════════════════════════════════════════════════
    log_section("ANALYSIS 3: RAW FEATURES ONLY")
    z_raw = compute_zscores(df, RAW_FEATURES)

    results_raw = []
    for t in classified_turns:
        tk_turns = turns_by_ticker[t["ticker"]]
        next_turn = None
        for t2 in tk_turns:
            if t2["bar_idx"] > t["bar_idx"] and t2["tp_type"] != t["tp_type"]:
                next_turn = t2
                break
        r = analyze_turn_lifecycle(t, df, z_raw, RAW_FEATURES, next_turn)
        results_raw.append(r)

    aggregate_results(results_raw, "RAW FEATURES ONLY")

    # ═══════════════════════════════════════════════════════════
    # BASELINE: Are these signals exclusive to turns?
    # ═══════════════════════════════════════════════════════════
    log_section("BASELINE — CONTROL vs TURNS (¿son exclusivas estas señales?)")
    log(f"\n  Sampling random NON-TURN bars to compare...")

    # Build set of all turn bar indices per ticker (with ±5 buffer)
    turn_bars_per_ticker = {}
    for t in turns:
        tk = t["ticker"]
        turn_bars_per_ticker.setdefault(tk, set())
        for offset in range(-5, 6):
            turn_bars_per_ticker[tk].add(t["bar_idx"] + offset)

    # Sample random bars far from any turn
    np.random.seed(42)
    n_baseline_per_ticker = 200  # enough for statistical power
    baseline_indices = {}  # ticker -> list of bar indices

    for tk in df["ticker"].unique():
        tk_mask = df["ticker"] == tk
        tk_n = tk_mask.sum()
        tk_turn_bars = turn_bars_per_ticker.get(tk, set())
        eligible = [i for i in range(tk_n) if i not in tk_turn_bars]
        if len(eligible) > n_baseline_per_ticker:
            baseline_indices[tk] = list(np.random.choice(eligible, n_baseline_per_ticker, replace=False))
        else:
            baseline_indices[tk] = eligible

    total_baseline = sum(len(v) for v in baseline_indices.values())
    log(f"  Baseline bars: {total_baseline:,} (far from any turn)")

    # Compute baseline metrics using ALL features z-scores
    baseline_densities = []
    baseline_silent = 0
    baseline_feature_active_counts = {f: 0 for f in ALL_FEATURES}

    for tk, indices in baseline_indices.items():
        tk_mask = df["ticker"] == tk
        tk_z = z_all.loc[tk_mask].reset_index(drop=True)
        for idx in indices:
            if idx < len(tk_z):
                z_vals = tk_z.iloc[idx][ALL_FEATURES].values.astype(np.float64)
                z_vals = np.nan_to_num(z_vals, nan=0.0)
                active = np.abs(z_vals) > Z_THRESHOLD
                density = int(active.sum())
                baseline_densities.append(density)
                if density == 0:
                    baseline_silent += 1
                for f, a in zip(ALL_FEATURES, active):
                    if a:
                        baseline_feature_active_counts[f] += 1

    n_bl = len(baseline_densities)
    bl_density_mean = np.mean(baseline_densities) if baseline_densities else 0
    bl_silent_pct = baseline_silent / max(n_bl, 1) * 100
    bl_det_rate = sum(1 for d in baseline_densities if d >= 2) / max(n_bl, 1) * 100

    log(f"\n  BASELINE (random non-turn bars):")
    log(f"    n={n_bl:,}")
    log(f"    Density mean: {bl_density_mean:.1f}")
    log(f"    Silent (density=0): {bl_silent_pct:.1f}%")
    log(f"    Detection rate (≥2): {bl_det_rate:.1f}%")
    log(f"    Top feature activation rates:")
    bl_sorted = sorted(baseline_feature_active_counts.items(), key=lambda x: -x[1])[:10]
    for feat, cnt in bl_sorted:
        log(f"      {feat:<35} {cnt/max(n_bl,1)*100:.1f}%")

    # LIFT TABLE: each archetype vs baseline
    log(f"\n  {'─'*110}")
    log(f"  {'Archetype':<8} {'Metric':<28} {'Turn':<12} {'Baseline':<12} {'LIFT':<10} {'Signal?':<12}")
    log(f"  {'─'*8} {'─'*28} {'─'*12} {'─'*12} {'─'*10} {'─'*12}")

    for arch in ["LL", "HL", "HH", "LH"]:
        arch_res = [r for r in results_all if r["archetype"] == arch]
        if not arch_res:
            continue
        n = len(arch_res)

        # Density at t=0
        turn_density_mean = np.mean([r["det_density"] for r in arch_res])
        lift_density = turn_density_mean / max(bl_density_mean, 0.01)

        # Silent %
        turn_silent_pct = sum(1 for r in arch_res if r["det_silent"]) / n * 100
        lift_silent = turn_silent_pct / max(bl_silent_pct, 0.01)

        # Detection rate
        turn_det_rate = sum(1 for r in arch_res if r["det_density"] >= 2) / n * 100
        lift_det = turn_det_rate / max(bl_det_rate, 0.01)

        def signal_tag(lift, invert=False):
            if invert:
                lift = 1 / max(lift, 0.01)
            if lift >= 3.0: return "✅ STRONG"
            if lift >= 2.0: return "✅ GOOD"
            if lift >= 1.5: return "⚠️ WEAK"
            return "❌ NO SIGNAL"

        log(f"  {arch:<8} {'Density mean':<28} {turn_density_mean:<12.1f} {bl_density_mean:<12.1f} {lift_density:<10.2f}x {signal_tag(lift_density)}")
        log(f"  {arch:<8} {'Detection ≥2 features %':<28} {turn_det_rate:<12.1f} {bl_det_rate:<12.1f} {lift_det:<10.2f}x {signal_tag(lift_det)}")
        log(f"  {arch:<8} {'Silent %':<28} {turn_silent_pct:<12.1f} {bl_silent_pct:<12.1f} {lift_silent:<10.2f}x {'(inverted)' if arch != 'HH' else '✅ SILENCE=SIGNAL'}")

        # Per-feature LIFT (top 10 by LIFT)
        feature_lifts = []
        for f in ALL_FEATURES:
            turn_pct = sum(1 for r in arch_res if f in r.get("det_active_features", [])) / n * 100
            bl_pct = baseline_feature_active_counts[f] / max(n_bl, 1) * 100
            lift = turn_pct / max(bl_pct, 0.01)
            feature_lifts.append((f, turn_pct, bl_pct, lift))

        feature_lifts.sort(key=lambda x: -x[3])  # sort by LIFT
        log(f"\n  {arch} — Top features by LIFT (turn vs random):")
        log(f"  {'Feature':<35} {'Turn%':<10} {'Base%':<10} {'LIFT':<10} {'Signal?'}")
        log(f"  {'─'*35} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
        for feat, tpct, bpct, lift in feature_lifts[:10]:
            if tpct < 2.0:  # skip features that barely fire
                continue
            log(f"  {feat:<35} {tpct:<10.1f} {bpct:<10.1f} {lift:<10.1f}x {signal_tag(lift)}")
        log("")

    # ═══════════════════════════════════════════════════════════
    # COMPARISON MATRIX: Kalman vs Raw per Archetype
    # ═══════════════════════════════════════════════════════════
    log_section("COMPARISON: KALMAN vs RAW per Archetype")

    log(f"\n  {'Archetype':<8} {'Metric':<25} {'Kalman':>10} {'Raw':>10} {'All':>10} {'Winner':>10}")
    log(f"  {'─'*8} {'─'*25} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")

    for arch in ["LL", "HL", "HH", "LH"]:
        rk = [r for r in results_kalman if r["archetype"] == arch]
        rr = [r for r in results_raw if r["archetype"] == arch]
        ra = [r for r in results_all if r["archetype"] == arch]
        if not rk:
            continue

        n = len(rk)
        metrics = {
            "Alert Rate %": (
                sum(r["alert_any_active"] for r in rk) / n * 100,
                sum(r["alert_any_active"] for r in rr) / n * 100,
                sum(r["alert_any_active"] for r in ra) / n * 100,
            ),
            "Detection Rate %": (
                sum(r["det_density"] >= 2 for r in rk) / n * 100,
                sum(r["det_density"] >= 2 for r in rr) / n * 100,
                sum(r["det_density"] >= 2 for r in ra) / n * 100,
            ),
            "Silent at t=0 %": (
                sum(r["det_silent"] for r in rk) / n * 100,
                sum(r["det_silent"] for r in rr) / n * 100,
                sum(r["det_silent"] for r in ra) / n * 100,
            ),
            "Confirm Persist %": (
                sum(r["conf_persists"] for r in rk) / n * 100,
                sum(r["conf_persists"] for r in rr) / n * 100,
                sum(r["conf_persists"] for r in ra) / n * 100,
            ),
            "Det Density mean": (
                np.mean([r["det_density"] for r in rk]),
                np.mean([r["det_density"] for r in rr]),
                np.mean([r["det_density"] for r in ra]),
            ),
        }

        for metric, (vk, vr, va) in metrics.items():
            if "Silent" in metric:
                # Lower silence is better for detection (except HH where silence IS the signal)
                winner = "RAW" if vr < vk else "KALMAN" if vk < vr else "TIE"
                if arch == "HH":
                    winner += " (but silence IS the HH signal)"
            else:
                winner = "RAW" if vr > vk else "KALMAN" if vk > vr else "TIE"
            log(f"  {arch:<8} {metric:<25} {vk:>10.1f} {vr:>10.1f} {va:>10.1f} {winner:>10}")
        log("")

    # ═══════════════════════════════════════════════════════════
    # ZIG-ZAG INTEGRITY
    # ═══════════════════════════════════════════════════════════
    report_zigzag_integrity(pairs, orphan_zigs, orphan_zags, turns)

    # ═══════════════════════════════════════════════════════════
    # SIGNAL-FIRST PRECISION: For each activation, is it near a turn?
    # ═══════════════════════════════════════════════════════════
    signal_first_analysis(df, z_all, ALL_FEATURES, turns, label="ALL FEATURES")

    # ═══════════════════════════════════════════════════════════
    # SAVE
    # ═══════════════════════════════════════════════════════════
    elapsed = time.time() - T0
    log_section("COMPLETE")
    log(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    out_dir = os.path.join(os.path.dirname(__file__), "sentinel_v3_output")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(out_dir, f"forensics_{ts}.log")
    with open(log_path, "w") as f:
        f.write("\n".join(LOG))
    log(f"  ✅ Log saved: {log_path}")


if __name__ == "__main__":
    main()
