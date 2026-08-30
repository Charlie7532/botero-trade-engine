#!/usr/bin/env python3
"""
Protocolo C.3 — Generador de continuous_metar_lake.parquet
============================================================
Construye la MATRIZ CONTINUA diaria del sistema METAR:
  - Cada fila = 1 día de trading (alineado con SPY)
  - Para cada una de las 11 estaciones METAR:
    * Valor raw (close)
    * D1 bin (expanding rank, zero look-ahead)
    * D2 bin (diff(3) velocity, expanding rank)
    * D3 bin (std(2)/std(10) instability, expanding rank)
    * state_key = D1__D2__D3
    * z-scores para D1, D2, D3 (contra STATION_MU_SIGMA)
    * overflow flags (±2σ, ±3σ)
  - Cross-station:
    * n_overflows_2s: cuántos canales en ≥2σ simultáneamente
    * n_overflows_3s: cuántos canales en ≥3σ
    * panic_score / euphoria_score (D1 extremos alineados)
  - SPY OHLCV para forward returns y visualización

NOTA METODOLÓGICA (Regla E.9):
  Este script NO calcula fwd_20d ni ningún retorno a horizonte fijo.
  Los retornos se calculan EXTERNAMENTE vía zigzag triad.
  El lake es SOLO features de estado. Sin target variable.

Output: data/research/continuous_metar_lake.parquet
"""
import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.sigma_overflow import STATION_MU_SIGMA

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ContinuousMETARLake")

# ── Station Config ───────────────────────────────────────────────────────────
STATION_TO_TICKER = {
    "vix": "VIX",
    "vvix": "VVIX",
    "pcr": "CBOE_PCR",
    "fg": "FG",
    "sv5_turbulence": "SV5_TURBULENCE",
    "skew": "SKEW",
    "credit": "CREDIT_RATIO",
    "yield_curve": "YIELD_SPREAD",
    "rotation": "ROTATION_INDEX",
    "dxy": "DXY",
    "bsi": "S5TW",
}

# D1 labels per station — CANONICAL from production generators
# Source: backend/scripts/generators/generate_*_fact_table.py
# Reference: .hermes/paraauditar/fact_store_v3_architecture.md lines 262-274
STATION_D1_LABELS = {
    "vix": ["EXTREME_COMPLACENCY", "COMPLACENCY", "NEUTRAL_CALM", "NEUTRAL_ALERT", "PANIC", "EXTREME_PANIC"],
    "vvix": ["EXTREME_STABILITY", "STABILITY", "NEUTRAL_STABLE", "NEUTRAL_UNSTABLE", "INSTABILITY", "EXTREME_INSTABILITY"],
    "pcr": ["EXTREME_CALL_EUPHORIA", "CALL_EUPHORIA", "NEUTRAL_CALL_BIAS", "NEUTRAL_PUT_BIAS", "PUT_PANIC", "EXTREME_PUT_PANIC"],
    "fg": ["EXTREME_FEAR", "FEAR", "NEUTRAL_FEAR", "NEUTRAL_GREED", "GREED", "EXTREME_GREED"],
    "sv5_turbulence": ["EXTREME_CALM", "CALM", "NEUTRAL_CALM", "NEUTRAL_TURBULENT", "TURBULENT", "EXTREME_TURBULENT"],
    "skew": ["EXTREME_CONFIDENCE", "CONFIDENCE", "NEUTRAL_CONFIDENT", "NEUTRAL_PARANOID", "PARANOIA", "EXTREME_PARANOIA"],
    "credit": ["EXTREME_STRESS", "STRESS", "NEUTRAL_TIGHT", "NEUTRAL_LOOSE", "EASE", "EXTREME_EASE"],
    "yield_curve": ["DEEP_INVERSION", "MODERATE_INVERSION", "FLAT_CURVE", "NORMAL_CURVE", "STEEPNING_CURVE", "EXTREME_STEEPNING"],
    "rotation": ["EXTREME_DEFENSIVE", "DEFENSIVE", "NEUTRAL_DEFENSIVE", "NEUTRAL_OFFENSIVE", "OFFENSIVE", "EXTREME_OFFENSIVE"],
    "dxy": ["EXTREME_WEAKNESS", "WEAKNESS", "NEUTRAL_WEAK", "NEUTRAL_STRONG", "STRENGTH", "EXTREME_STRENGTH"],
    "bsi": ["BREADTH_WASHED_OUT", "OVERSOLD_BREADTH", "NEUTRAL_LOW_BREADTH", "NEUTRAL_HIGH_BREADTH", "EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"],
}

# Gaussian Calibration Standard (Rule 24)
PERCENTILES_D1 = [0.0228, 0.1587, 0.5000, 0.8413, 0.9772]  # 6 bins, 5 edges
PERCENTILES_D2 = [0.0228, 0.1587, 0.8413, 0.9772]            # 5 bins, 4 edges
PERCENTILES_D3 = [0.0228, 0.1587, 0.8413, 0.9772]            # 5 bins, 4 edges

LABELS_D2 = ["FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D", "ACCELERATING_UP_3D", "FAST_SPIKE_3D"]
LABELS_D3 = ["VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION", "VOL_NEUTRAL_BASELINE", "VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION"]

MIN_EXPANDING = 252  # Minimum 1 year for expanding rank


def classify_value(val: float, edges: list, labels: list) -> str:
    """Classify a percentile rank into labels using Gaussian edges.

    NaN handling: returns None. When a station has no data for a date
    (e.g. FG before 2011, Credit before 2007), its state must be NaN,
    not a fabricated neutral label. This prevents 'phantom states' from
    distorting signal harness statistics and confluence scoring.
    """
    if pd.isna(val):
        return None
    for idx, e in enumerate(edges):
        if val < e:
            return labels[idx]
    return labels[-1]


def compute_station_features(store: TimescaleDataStore, station: str, spy_index: pd.Index) -> pd.DataFrame:
    """Compute all features for a single METAR station aligned to SPY trading days."""
    ticker = STATION_TO_TICKER[station]
    d1_labels = STATION_D1_LABELS[station]
    mu_sigma = STATION_MU_SIGMA.get(station, {})

    bars = store.load_bars(ticker, "1d")
    if bars is None or len(bars) < 30:
        logger.warning(f"  {station} ({ticker}): insufficient data ({0 if bars is None else len(bars)} bars)")
        return pd.DataFrame(index=spy_index)

    bars = bars.sort_index()
    raw_val = bars["close"]

    # Normalize index to tz-naive date for alignment
    raw_val.index = raw_val.index.tz_localize(None).normalize()
    raw_val = raw_val[~raw_val.index.duplicated(keep="last")]

    # ALIGNMENT FIRST (Homologated with production fact store generators):
    # Align raw series to SPY trading days first, then ffill(limit=3) for FX/holiday gaps.
    # This prevents pre-1993 historical outliers (e.g. 1985 Plaza Accord DXY=164.72 or
    # 1980s Volcker yield spreads) from distorting the expanding rank post-1993.
    raw_val = raw_val.reindex(spy_index).ffill(limit=3)

    # Build station DataFrame
    sdf = pd.DataFrame({f"{station}_val": raw_val}, index=spy_index)

    # D2: 3-day velocity
    sdf[f"{station}_d2_raw"] = raw_val.diff(3)

    # D3: std(2)/std(10) instability (V1.1)
    vol_2d = raw_val.rolling(2).std()
    vol_10d = raw_val.rolling(10).std().replace(0, np.nan)
    sdf[f"{station}_d3_raw"] = (vol_2d / vol_10d).fillna(1.0)

    # D1: Expanding rank (zero look-ahead bias, starting from SPY inception / station inception)
    d1_rank = raw_val.expanding(min_periods=MIN_EXPANDING).rank(pct=True)
    d2_rank = sdf[f"{station}_d2_raw"].expanding(min_periods=MIN_EXPANDING).rank(pct=True)
    d3_rank = sdf[f"{station}_d3_raw"].expanding(min_periods=MIN_EXPANDING).rank(pct=True)

    # Classify into bins
    sdf[f"{station}_d1"] = d1_rank.apply(lambda r: classify_value(r, PERCENTILES_D1, d1_labels))
    sdf[f"{station}_d2"] = d2_rank.apply(lambda r: classify_value(r, PERCENTILES_D2, LABELS_D2))
    sdf[f"{station}_d3"] = d3_rank.apply(lambda r: classify_value(r, PERCENTILES_D3, LABELS_D3))

    # State key
    sdf[f"{station}_sk"] = sdf[f"{station}_d1"] + "__" + sdf[f"{station}_d2"] + "__" + sdf[f"{station}_d3"]

    # Z-scores (against population mu/sigma from sigma_overflow.py)
    if "d1" in mu_sigma:
        mu_d1, sig_d1 = mu_sigma["d1"]
        sdf[f"{station}_z_d1"] = (raw_val - mu_d1) / sig_d1 if sig_d1 > 0 else 0.0

    if "d2" in mu_sigma:
        mu_d2, sig_d2 = mu_sigma["d2"]
        sdf[f"{station}_z_d2"] = (sdf[f"{station}_d2_raw"] - mu_d2) / sig_d2 if sig_d2 > 0 else 0.0

    if "d3" in mu_sigma:
        mu_d3, sig_d3 = mu_sigma["d3"]
        sdf[f"{station}_z_d3"] = (sdf[f"{station}_d3_raw"] - mu_d3) / sig_d3 if sig_d3 > 0 else 0.0

    # Overflow flags per dimension
    for dim in ["d1", "d2", "d3"]:
        z_col = f"{station}_z_{dim}"
        if z_col in sdf.columns:
            sdf[f"{station}_ovf2s_{dim}"] = sdf[z_col].abs() >= 2.0
            sdf[f"{station}_ovf3s_{dim}"] = sdf[z_col].abs() >= 3.0

    n_valid = sdf[f"{station}_val"].notna().sum()
    logger.info(f"  {station} ({ticker}): {n_valid} days aligned to SPY, "
                f"{len(raw_val)} total bars in Vault")

    return sdf


def compute_cross_station_features(lake: pd.DataFrame, stations: list) -> pd.DataFrame:
    """Compute cross-station confluence features.

    NaN handling: stations that don't exist for a given date contribute NaN,
    not 0. We track n_stations_active and compute normalized scores so that
    confluence metrics are comparable across eras (e.g. 1995 with 5 stations
    vs 2025 with 11 stations).
    """
    # Count simultaneous overflows across all stations x all dimensions
    ovf2s_cols = [c for c in lake.columns if "_ovf2s_" in c]
    ovf3s_cols = [c for c in lake.columns if "_ovf3s_" in c]

    lake["n_overflows_2s"] = lake[ovf2s_cols].sum(axis=1).astype(int) if ovf2s_cols else 0
    lake["n_overflows_3s"] = lake[ovf3s_cols].sum(axis=1).astype(int) if ovf3s_cols else 0
    # How many overflow channels were observable (non-NaN) this day
    lake["n_ovf_channels_active"] = lake[ovf2s_cols].notna().sum(axis=1).astype(int) if ovf2s_cols else 0

    # Panic score: count of FEAR/STRESS-aligned D1 extremes
    # Canonical symmetric labels (Rule 24 & d1_labels_canonical.md)
    panic_conditions = {
        "vix_d1": {"PANIC", "EXTREME_PANIC"},
        "bsi_d1": {"BREADTH_WASHED_OUT", "OVERSOLD_BREADTH"},
        "pcr_d1": {"PUT_PANIC", "EXTREME_PUT_PANIC"},
        "fg_d1": {"EXTREME_FEAR", "FEAR"},
        "skew_d1": {"PARANOIA", "EXTREME_PARANOIA"},
        "credit_d1": {"EXTREME_STRESS", "STRESS"},
        "sv5_turbulence_d1": {"TURBULENT", "EXTREME_TURBULENT"},
        "yield_curve_d1": {"DEEP_INVERSION", "MODERATE_INVERSION"},
        "rotation_d1": {"EXTREME_DEFENSIVE", "DEFENSIVE"},
        "dxy_d1": {"STRENGTH", "EXTREME_STRENGTH"},
    }

    panic_score = pd.Series(0, index=lake.index, dtype=int)
    panic_active = pd.Series(0, index=lake.index, dtype=int)
    for col, vals in panic_conditions.items():
        if col in lake.columns:
            is_active = lake[col].notna()
            panic_score += lake[col].isin(vals).astype(int)
            panic_active += is_active.astype(int)
    lake["panic_score"] = panic_score
    lake["n_panic_stations_active"] = panic_active
    lake["panic_score_pct"] = (panic_score / panic_active.replace(0, 1)).round(4)

    # Euphoria score: count of GREED/EASE-aligned D1 extremes
    euphoria_conditions = {
        "vix_d1": {"EXTREME_COMPLACENCY", "COMPLACENCY"},
        "bsi_d1": {"EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"},
        "pcr_d1": {"EXTREME_CALL_EUPHORIA", "CALL_EUPHORIA"},
        "fg_d1": {"GREED", "EXTREME_GREED"},
        "credit_d1": {"EASE", "EXTREME_EASE"},
        "skew_d1": {"EXTREME_CONFIDENCE", "CONFIDENCE"},
        "sv5_turbulence_d1": {"EXTREME_CALM", "CALM"},
        "yield_curve_d1": {"STEEPNING_CURVE", "EXTREME_STEEPNING"},
        "rotation_d1": {"OFFENSIVE", "EXTREME_OFFENSIVE"},
        "dxy_d1": {"EXTREME_WEAKNESS", "WEAKNESS"},
    }

    euphoria_score = pd.Series(0, index=lake.index, dtype=int)
    euphoria_active = pd.Series(0, index=lake.index, dtype=int)
    for col, vals in euphoria_conditions.items():
        if col in lake.columns:
            is_active = lake[col].notna()
            euphoria_score += lake[col].isin(vals).astype(int)
            euphoria_active += is_active.astype(int)
    lake["euphoria_score"] = euphoria_score
    lake["n_euphoria_stations_active"] = euphoria_active
    lake["euphoria_score_pct"] = (euphoria_score / euphoria_active.replace(0, 1)).round(4)

    return lake


def main():
    logger.info("=" * 100)
    logger.info("PROTOCOLO C.3 — Generacion de continuous_metar_lake.parquet")
    logger.info("=" * 100)

    store = TimescaleDataStore()
    stations = list(STATION_TO_TICKER.keys())

    # Load SPY as the master index
    spy = store.load_bars("SPY", "1d")
    if spy is None or len(spy) == 0:
        logger.error("ERROR: No SPY data in Vault")
        return
    spy = spy.sort_index()
    spy.index = spy.index.tz_localize(None).normalize()
    spy = spy[~spy.index.duplicated(keep="last")]
    logger.info(f"SPY: {len(spy)} barras ({spy.index[0].date()} -> {spy.index[-1].date()})")

    # Start with SPY OHLCV
    lake = pd.DataFrame({
        "spy_open": spy["open"],
        "spy_high": spy["high"],
        "spy_low": spy["low"],
        "spy_close": spy["close"],
        "spy_volume": spy["volume"],
    }, index=spy.index)

    # Bar-by-bar SPY returns (only bar[+1] — NO fwd_20d)
    lake["spy_ret_1d"] = spy["close"].pct_change(1)

    # Compute features for each station
    logger.info(f"\nComputing features for {len(stations)} METAR stations...")
    for station in stations:
        sdf = compute_station_features(store, station, spy.index)
        lake = lake.join(sdf, how="left")

    # Cross-station confluence
    logger.info("\nComputing cross-station confluence features...")
    lake = compute_cross_station_features(lake, stations)

    # Summary statistics
    n_total = len(lake)
    n_cols = len(lake.columns)
    date_range = f"{lake.index[0].date()} -> {lake.index[-1].date()}"

    # Count data coverage per station
    logger.info(f"\n{'='*100}")
    logger.info(f"LAKE GENERADO: {n_total} filas x {n_cols} columnas ({date_range})")
    logger.info(f"{'='*100}")
    logger.info(f"\nCobertura por estacion:")
    for station in stations:
        val_col = f"{station}_val"
        if val_col in lake.columns:
            n_valid = lake[val_col].notna().sum()
            pct = n_valid / n_total * 100
            first_valid = lake[val_col].first_valid_index()
            logger.info(f"  {station:>18s}: {n_valid:>5d} dias ({pct:>5.1f}%) desde {first_valid.date() if first_valid else 'N/A'}")

    # Overflow summary
    logger.info(f"\nOverflows (toda la historia):")
    logger.info(f"  Dias con >=1 overflow 2s: {(lake['n_overflows_2s'] >= 1).sum()}")
    logger.info(f"  Dias con >=3 overflows 2s: {(lake['n_overflows_2s'] >= 3).sum()}")
    logger.info(f"  Dias con >=1 overflow 3s: {(lake['n_overflows_3s'] >= 1).sum()}")
    logger.info(f"  Dias con panic_score >= 3: {(lake['panic_score'] >= 3).sum()}")
    logger.info(f"  Dias con euphoria_score >= 3: {(lake['euphoria_score'] >= 3).sum()}")

    # Save
    output_path = ROOT / "data" / "research" / "continuous_metar_lake.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lake.to_parquet(output_path, engine="pyarrow")
    logger.info(f"\n Lake guardado: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Also save a small CSV sample for inspection
    sample_path = ROOT / "data" / "research" / "continuous_metar_lake_sample.csv"
    lake.tail(30).to_csv(sample_path)
    logger.info(f" Sample (ultimos 30 dias): {sample_path}")


if __name__ == "__main__":
    main()
