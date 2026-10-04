#!/usr/bin/env python3
"""
Atomic Wipe & Reload Cascade (wipe_reload_cascade)
==================================================
Rebuilds a ticker's full data lake atomically with zero data loss on failure:
  1. Download full history from Yahoo Finance and validate in-memory.
     Network operations happen 100% OUTSIDE the database transaction.
  2. Single Atomic DB Transaction:
     DELETE FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d';
     DELETE FROM engine.channel_snapshots WHERE ticker = %s AND timeframe = '1d';
     DELETE FROM engine.zigzag_points WHERE ticker = %s;
     INSERT INTO market.ohlcv_bars (new bars);
     COMMIT;
     If any error occurs: ROLLBACK (the ticker remains completely intact).
  3. Chained Reconstruction:
     - Channel Snapshots: rolling linreg + rolling vwap with CR-1 safe guards (vstd > 1e-4).
     - Zigzag Points: canonical pivots (High/Low, levels 0.025, 0.05, 0.075).
     - Unified Observer: Kalman filter velocity and physical bounds on snapshots.
  4. Invalidate Redis L1 cache (`bars:{ticker}:*`).

Usage:
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfills/wipe_reload_cascade.py --ticker IBM
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfills/wipe_reload_cascade.py --tickers IBM,XOM,MCD,WMT
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfills/wipe_reload_cascade.py --test-failure-download AAPL
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfills/wipe_reload_cascade.py --test-failure-db AAPL
"""
import os, sys, time, logging, argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd
import yfinance as yf
from psycopg2.extras import execute_batch, execute_values

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.redis_cache import get_redis_cache
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle
from backend.modules.shared.domain.rules.geometric_features import compute_geometric_features
from backend.modules.shared.domain.rules.unified_observer import compute_observer_series
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker
from backend.modules.quality_swing.domain.rules.rc_slope_classifier import classify_slopes
from backend.scripts.backfills.backfill_zigzag_points import zigzag_canonical, ZIGZAG_LEVELS
from backend.scripts.backfills.backfill_unified_observer import _BOUNDS, _clamp_real
from backend.scripts.backfills.backfill_channel_snapshots_v2 import (
    _rolling_linreg, _rolling_vwap, _precompute_rsi, _precompute_kalman,
    TIDE_WINDOW, CURRENT_WINDOW, RSI_PERIOD, RSI_MIN_BARS, RSI_WINDOW, MIN_BARS
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wipe_reload_cascade")


def download_and_validate(ticker: str, fail_simulation: Optional[str] = None) -> pd.DataFrame:
    """Download full history and validate in-memory.
    No database connection or transaction is active during this step.
    """
    if fail_simulation == "download":
        raise ConnectionError(f"[INJECTED FAILURE] Network timeout while downloading {ticker}")

    logger.info(f"[{ticker}] Downloading max history via Yahoo Finance (auto_adjust=True)...")
    # yfinance symbol translation if needed
    yf_symbol = ticker.replace(".", "-")
    df = yf.download(yf_symbol, period="max", interval="1d", auto_adjust=True, progress=False)

    if df is None or df.empty:
        raise ValueError(f"[{ticker}] Downloaded data is empty.")

    # Flatten MultiIndex columns if present (yfinance >= 0.2.x)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]

    # Validate required columns
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"[{ticker}] Missing required columns: {missing}")

    # Clean and filter
    df = df[required].dropna(subset=["open", "high", "low", "close"])
    df = df[df["close"] > 0]
    df = df[df["volume"] >= 0]

    # Ensure UTC midnight index
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    # Normalize to midnight UTC (00:00:00)
    df.index = df.index.normalize()

    # Deduplicate timestamps, keep last
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()

    if len(df) < MIN_BARS:
        raise ValueError(f"[{ticker}] Insufficient bars: {len(df)} < {MIN_BARS}")

    logger.info(f"[{ticker}] Validated in-memory: {len(df):,} bars from {df.index.min().date()} to {df.index.max().date()}")
    return df


def atomic_swap_bars(store: TimescaleDataStore, ticker: str, df: pd.DataFrame,
                     fail_simulation: Optional[str] = None) -> int:
    """Execute atomic DELETE and INSERT in a single database transaction.
    If an error occurs, the transaction rolls back and original data is preserved.
    """
    conn = store._conn()
    try:
        # Prepare rows for market.ohlcv_bars
        # (time, ticker, timeframe, open, high, low, close, volume)
        rows = []
        for ts, row in df.iterrows():
            py_ts = ts.to_pydatetime()
            o = float(row["open"])
            h = float(row["high"])
            l = float(row["low"])
            c = float(row["close"])
            v = float(row["volume"])
            rows.append((py_ts, ticker.upper(), "1d", o, h, l, c, v))

        logger.info(f"[{ticker}] Starting atomic DB transaction (DELETE 3 tables + INSERT {len(rows):,} bars)...")
        with conn.cursor() as cur:
            # Atomic cascade delete across the 3 stores
            cur.execute("DELETE FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d';", (ticker.upper(),))
            cur.execute("DELETE FROM engine.channel_snapshots WHERE ticker = %s AND timeframe = '1d';", (ticker.upper(),))
            cur.execute("DELETE FROM engine.zigzag_points WHERE ticker = %s;", (ticker.upper(),))

            # Insert new bars
            execute_batch(cur, """
                INSERT INTO market.ohlcv_bars
                (time, ticker, timeframe, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, rows, page_size=1000)

            if fail_simulation == "db":
                raise RuntimeError(f"[INJECTED FAILURE] Database error before commit for {ticker}")

        # Commit only if all statements succeeded
        conn.commit()
        logger.info(f"[{ticker}] Atomic swap COMMITTED successfully.")
        return len(rows)

    except Exception as e:
        conn.rollback()
        logger.error(f"[{ticker}] Transaction ROLLED BACK due to error: {e}")
        raise
    finally:
        store._put(conn)


def rebuild_snapshots(store: TimescaleDataStore, ticker: str, df: pd.DataFrame) -> int:
    """Rebuild channel snapshots with safe guards and batch insert."""
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    volume = df["volume"].values.astype(float)
    timestamps = df.index.tolist()
    n = len(close)

    if n < MIN_BARS:
        return 0

    logger.info(f"[{ticker}] Computing channel snapshots for {n:,} bars...")
    wave_window = max(10, min(detect_dominant_cycle(close), 60))

    tide_reg, tide_slope, tide_std = _rolling_linreg(close, TIDE_WINDOW)
    curr_reg, curr_slope, curr_std = _rolling_linreg(close, CURRENT_WINDOW)
    wave_reg, wave_slope, wave_std = _rolling_linreg(close, wave_window)

    vwap_tide, vstd_tide = _rolling_vwap(close, high, low, volume, TIDE_WINDOW)
    vwap_curr, vstd_curr = _rolling_vwap(close, high, low, volume, CURRENT_WINDOW)
    vwap_wave, vstd_wave = _rolling_vwap(close, high, low, volume, wave_window)

    vol_sma20 = pd.Series(volume).rolling(window=20, min_periods=1).mean().values
    vol_surge = np.where(vol_sma20 > 0, volume / vol_sma20, 1.0)

    vol_ratio = np.full(n, 1.0)
    for i in range(5, n):
        up_vol, down_vol, up_n, down_n = 0.0, 0.0, 0, 0
        for j in range(max(1, i - 4), i + 1):
            if close[j] > close[j - 1]:
                up_vol += volume[j]; up_n += 1
            else:
                down_vol += volume[j]; down_n += 1
        avg_up = up_vol / max(up_n, 1)
        avg_down = down_vol / max(down_n, 1)
        vol_ratio[i] = avg_up / avg_down if avg_down > 0 else 2.0

    rsi_series, rsi_div_conv = _precompute_rsi(close)
    kalman_states = _precompute_kalman(close, volume)

    snapshots_data = []
    start_idx = TIDE_WINDOW + 5
    prev_w_level = None
    w_dur = 1

    for idx in range(start_idx, n):
        if np.isnan(tide_reg[idx]) or np.isnan(curr_reg[idx]) or np.isnan(wave_reg[idx]):
            continue

        price = close[idx]
        s_tide = (price - tide_reg[idx]) / tide_std[idx]
        s_curr = (price - curr_reg[idx]) / curr_std[idx]
        s_wave = (price - wave_reg[idx]) / wave_std[idx]

        # VWAP sigmas — guarded with vstd > 1e-4 else None
        vs_tide = (price - vwap_tide[idx]) / vstd_tide[idx] if (not np.isnan(vwap_tide[idx]) and not np.isnan(vstd_tide[idx]) and vstd_tide[idx] > 1e-4) else None
        vs_curr = (price - vwap_curr[idx]) / vstd_curr[idx] if (not np.isnan(vwap_curr[idx]) and not np.isnan(vstd_curr[idx]) and vstd_curr[idx] > 1e-4) else None
        vs_wave = (price - vwap_wave[idx]) / vstd_wave[idx] if (not np.isnan(vwap_wave[idx]) and not np.isnan(vstd_wave[idx]) and vstd_wave[idx] > 1e-4) else None

        vs_tide_val = round(float(vs_tide), 4) if vs_tide is not None else None
        vs_curr_val = round(float(vs_curr), 4) if vs_curr is not None else None
        vs_wave_val = round(float(vs_wave), 4) if vs_wave is not None else None

        tension_tide = round(float(s_tide - vs_tide), 4) if vs_tide is not None else None
        tension_current = round(float(s_curr - vs_curr), 4) if vs_curr is not None else None
        tension_wave = round(float(s_wave - vs_wave), 4) if vs_wave is not None else None

        t_accel = tide_slope[idx] - tide_slope[idx - 1] if idx > start_idx and not np.isnan(tide_slope[idx - 1]) else 0.0
        c_accel = curr_slope[idx] - curr_slope[idx - 1] if idx > start_idx and not np.isnan(curr_slope[idx - 1]) else 0.0
        w_accel = wave_slope[idx] - wave_slope[idx - 1] if idx > start_idx and not np.isnan(wave_slope[idx - 1]) else 0.0

        w_flip = False
        w_flip_dir = 0
        if idx > start_idx and not np.isnan(wave_slope[idx - 1]):
            w_flip = bool((wave_slope[idx] > 0) != (wave_slope[idx - 1] > 0))
            if w_flip:
                w_flip_dir = 1 if wave_slope[idx] > 0 else -1

        ts_val = float(tide_slope[idx])
        ws_val = float(wave_slope[idx])
        if ts_val < -0.02 and ws_val < -0.05 and t_accel < 0:
            fear_level, fear_label = 5, "PANIC"
        elif ts_val < -0.01 and ws_val <= 0.02:
            fear_level, fear_label = 4, "FEAR"
        elif ts_val > 0.01 and ws_val < -0.02:
            fear_level, fear_label = 3, "ANXIETY"
        elif -0.01 <= ts_val <= 0.01:
            fear_level, fear_label = 2, "NEUTRAL"
        elif ts_val > 0.01 and ws_val > 0.02 and t_accel <= 0:
            fear_level, fear_label = 1, "CONFIDENCE"
        elif ts_val > 0.02 and ws_val > 0.05 and t_accel > 0:
            fear_level, fear_label = 0, "EUPHORIA"
        else:
            fear_level, fear_label = 2, "NEUTRAL"

        if ts_val > 0.01 and ws_val > 0.01:
            regime = "BULL"
        elif ts_val < -0.01 and ws_val < -0.01:
            regime = "BEAR"
        else:
            regime = "FLAT"

        vt = round(float(vwap_tide[idx]), 2) if not np.isnan(vwap_tide[idx]) else None
        vc = round(float(vwap_curr[idx]), 2) if not np.isnan(vwap_curr[idx]) else None
        vw = round(float(vwap_wave[idx]), 2) if not np.isnan(vwap_wave[idx]) else None

        vw_spread_tc = round(float((vt - vc) / max(abs(vt), 1e-8) * 100), 4) if (vt is not None and vc is not None) else None
        vw_spread_tw = round(float((vt - vw) / max(abs(vt), 1e-8) * 100), 4) if (vt is not None and vw is not None) else None
        vw_spread_cw = round(float((vc - vw) / max(abs(vc), 1e-8) * 100), 4) if (vc is not None and vw is not None) else None

        below_all = bool(price < vt and price < vc and price < vw) if (vt is not None and vc is not None and vw is not None) else None
        above_all = bool(price > vt and price > vc and price > vw) if (vt is not None and vc is not None and vw is not None) else None

        comp = round(float(wave_std[idx]) / float(tide_std[idx]), 4) if tide_std[idx] > 1e-8 else None

        cs_val = float(curr_slope[idx])
        sl = classify_slopes(ts_val, cs_val, ws_val)
        curr_w_level = sl.wave_level
        if prev_w_level is not None and curr_w_level == prev_w_level:
            w_dur += 1
        else:
            w_dur = 1
        prev_w_level = curr_w_level

        rsi_val = float(rsi_series[idx]) if idx < len(rsi_series) else 50.0
        div_str, conv = rsi_div_conv[idx] if idx < len(rsi_div_conv) else (0.0, 0.0)
        k = kalman_states[idx] if idx < len(kalman_states) else {'kalman_velocity': 0.0, 'vol_adj_delta': 0.0}

        geo = compute_geometric_features(
            s_tide, s_curr, s_wave,
            ts_val, cs_val, ws_val,
            t_accel, c_accel, w_accel,
            slope_stds=None,
        )

        row = (
            ticker.upper(), "1d", timestamps[idx], 1,
            TIDE_WINDOW, CURRENT_WINDOW, wave_window,
            round(float(s_tide), 4), round(float(s_curr), 4), round(float(s_wave), 4),
            round(float(tide_reg[idx]), 2), round(float(curr_reg[idx]), 2), round(float(wave_reg[idx]), 2),
            round(float(tide_std[idx]), 4), round(float(curr_std[idx]), 4), round(float(wave_std[idx]), 4),
            vs_tide_val, vs_curr_val, vs_wave_val,
            vt, vc, vw,
            round(float(ts_val), 6), round(float(cs_val), 6), round(float(ws_val), 6),
            round(float(t_accel), 6), round(float(c_accel), 6), round(float(w_accel), 6),
            round(float(ws_val - cs_val), 6),
            round(float(ws_val - ts_val), 6),
            round(float(cs_val - ts_val), 6),
            round(float(s_tide - s_curr), 4),
            round(float(s_tide - s_wave), 4),
            round(float(s_curr - s_wave), 4),
            vw_spread_tc,
            vw_spread_tw,
            vw_spread_cw,
            int(fear_level), fear_label, regime,
            bool(w_flip), int(w_flip_dir),
            round(float(vol_ratio[idx]), 2),
            below_all,
            above_all,
            tension_tide,
            tension_current,
            tension_wave,
            comp,
            round(float(rsi_val), 1),
            round(float(div_str), 4),
            round(float(conv), 4),
            float(k['kalman_velocity']), float(k['vol_adj_delta']),
            float(geo[0]), float(geo[1]), float(geo[2]), float(geo[3]), float(geo[4]),
            round(float(vol_surge[idx]), 4),
            int(w_dur),
        )
        snapshots_data.append(row)

    conn = store._conn()
    try:
        cols_sql = ", ".join(store._CS_COLUMNS)
        update_cols = [c for c in store._CS_COLUMNS if c not in ("ticker", "timeframe", "timestamp")]
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        set_clause += ", computed_at = NOW()"

        insert_sql = f"""
            INSERT INTO engine.channel_snapshots ({cols_sql}, computed_at)
            VALUES %s
            ON CONFLICT (ticker, timeframe, timestamp)
            DO UPDATE SET {set_clause}
        """
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, snapshots_data, template=f"({'%s, ' * len(store._CS_COLUMNS)}NOW())", page_size=2000)
        conn.commit()
        logger.info(f"[{ticker}] Saved {len(snapshots_data):,} channel snapshots.")
        return len(snapshots_data)
    finally:
        store._put(conn)


def rebuild_zigzag(store: TimescaleDataStore, ticker: str, df: pd.DataFrame) -> int:
    """Rebuild canonical zigzag pivots for all 3 levels."""
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    ts = df.index

    all_rows = []
    for level in ZIGZAG_LEVELS:
        pts = zigzag_canonical(high, low, close, level)
        for i, (bar_idx, tp_type, price) in enumerate(pts):
            if i > 0:
                prev_idx, _, prev_price = pts[i - 1]
                swing_return = (price - prev_price) / prev_price
                swing_days = bar_idx - prev_idx
                swing_speed = swing_return / swing_days if swing_days > 0 else 0
            else:
                swing_return, swing_days, swing_speed = 0.0, 0, 0.0

            bar_ts = ts[bar_idx].to_pydatetime()
            if bar_ts.tzinfo is None:
                bar_ts = bar_ts.replace(tzinfo=timezone.utc)

            all_rows.append((
                ticker.upper(), bar_ts, tp_type, float(price),
                level, float(swing_return), int(swing_days), float(swing_speed)
            ))

    if not all_rows:
        return 0

    conn = store._conn()
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO engine.zigzag_points
                   (ticker, timestamp, tp_type, price, min_swing_pct,
                    swing_return, swing_days, swing_speed)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                all_rows,
                template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                page_size=1000
            )
        conn.commit()
        logger.info(f"[{ticker}] Saved {len(all_rows):,} zigzag points.")
        return len(all_rows)
    finally:
        store._put(conn)


def rebuild_observer(store: TimescaleDataStore, ticker: str) -> int:
    """Compute and update Unified Observer series in engine.channel_snapshots."""
    conn = store._conn()
    try:
        query = """
            SELECT timestamp,
                   sigma_current, vwap_sigma_wave, tension_wave,
                   rsi_value, conj_wave_tide
            FROM engine.channel_snapshots
            WHERE ticker = %s AND timeframe = '1d'
            ORDER BY timestamp
        """
        with conn.cursor() as cur:
            cur.execute(query, (ticker.upper(),))
            rows = cur.fetchall()

        if len(rows) < 100:
            logger.warning(f"[{ticker}] Too few snapshots for observer: {len(rows)} < 100")
            return 0

        cols = ["timestamp", "sigma_current", "vwap_sigma_wave", "tension_wave", "rsi_value", "conj_wave_tide"]
        tk = pd.DataFrame(rows, columns=cols)

        outputs = compute_observer_series(
            sigma_current=tk["sigma_current"].fillna(0).values,
            vwap_sigma_wave=tk["vwap_sigma_wave"].fillna(0).values,
            tension_wave=tk["tension_wave"].fillna(0).values,
            rsi_value=tk["rsi_value"].fillna(0).values,
            conj_wave_tide=tk["conj_wave_tide"].fillna(0).values,
        )

        updates = []
        for ts, out, v_raw in zip(tk["timestamp"].values, outputs, tk["vwap_sigma_wave"].values):
            py_ts = pd.Timestamp(ts).to_pydatetime()
            vel_svw_val = _clamp_real(out.vel_svw, _BOUNDS["obs_vel_svw"]) if pd.notna(v_raw) else None
            updates.append((
                _clamp_real(out.recovery_score, _BOUNDS["obs_recovery_score"]),
                _clamp_real(out.velocity_norm, _BOUNDS["obs_velocity_norm"]),
                out.state,
                out.kf_consensus,
                _clamp_real(out.vel_sigma_c, _BOUNDS["obs_vel_sigma_c"]),
                vel_svw_val,
                _clamp_real(out.vel_tension_w, _BOUNDS["obs_vel_tension_w"]),
                _clamp_real(out.vel_rsi, _BOUNDS["obs_vel_rsi"]),
                _clamp_real(out.vel_conj_wt, _BOUNDS["obs_vel_conj_wt"]),
                ticker.upper(), py_ts,
            ))

        with conn.cursor() as cur:
            execute_batch(cur, """
                UPDATE engine.channel_snapshots
                SET obs_recovery_score = %s,
                    obs_velocity_norm = %s,
                    obs_state = %s,
                    obs_kf_consensus = %s,
                    obs_vel_sigma_c = %s,
                    obs_vel_svw = %s,
                    obs_vel_tension_w = %s,
                    obs_vel_rsi = %s,
                    obs_vel_conj_wt = %s
                WHERE ticker = %s AND timeframe = '1d' AND timestamp = %s
            """, updates, page_size=500)
        conn.commit()
        logger.info(f"[{ticker}] Updated {len(updates):,} observer rows in channel_snapshots.")
        return len(updates)
    finally:
        store._put(conn)


def invalidate_cache(ticker: str):
    """Invalidate Redis L1 cache keys for ticker."""
    try:
        cache = get_redis_cache()
        if cache:
            cache.invalidate(f"bars:{ticker.upper()}:1d")
            cache.invalidate_pattern(f"bars:{ticker.upper()}:*")
            cache.invalidate_pattern(f"mcp:*:{ticker.upper()}:*")
            logger.info(f"[{ticker}] Redis L1 cache invalidated.")
    except Exception as e:
        logger.warning(f"[{ticker}] Redis cache invalidation error (non-fatal): {e}")


def wipe_reload_cascade(ticker: str, fail_simulation: Optional[str] = None) -> Dict[str, Any]:
    """Execute complete Wipe & Reload Cascade for a single ticker."""
    t0 = time.time()
    ticker = ticker.upper()
    logger.info(f"=== START WIPE & RELOAD CASCADE: {ticker} ===")
    store = TimescaleDataStore()

    try:
        # Step 1: Download & validate in-memory (network completely outside DB transaction)
        df = download_and_validate(ticker, fail_simulation=fail_simulation)

        # Step 2: Atomic Swap (DELETE 3 tables + INSERT bars -> COMMIT / ROLLBACK)
        bars_count = atomic_swap_bars(store, ticker, df, fail_simulation=fail_simulation)

        # Step 3: Chained reconstruction
        snaps_count = rebuild_snapshots(store, ticker, df)
        zigzag_count = rebuild_zigzag(store, ticker, df)
        obs_count = rebuild_observer(store, ticker)

        # Step 4: Invalidate Redis L1
        invalidate_cache(ticker)

        elapsed = time.time() - t0
        logger.info(f"=== COMPLETED CASCADE [{ticker}] in {elapsed:.2f}s: bars={bars_count}, snaps={snaps_count}, zz={zigzag_count}, obs={obs_count} ===")
        return {
            "ticker": ticker,
            "status": "SUCCESS",
            "bars": bars_count,
            "snapshots": snaps_count,
            "zigzag": zigzag_count,
            "observer": obs_count,
            "elapsed_sec": round(elapsed, 2),
        }
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(f"=== FAILED CASCADE [{ticker}] in {elapsed:.2f}s: {e} ===")
        raise
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description="Atomic Wipe & Reload Cascade for Vault tickers")
    parser.add_argument("--ticker", type=str, help="Single ticker symbol")
    parser.add_argument("--tickers", type=str, help="Comma-separated ticker list")
    parser.add_argument("--test-failure-download", type=str, help="Run failure injection test during download")
    parser.add_argument("--test-failure-db", type=str, help="Run failure injection test during DB transaction")
    args = parser.parse_args()

    if args.test_failure_download:
        ticker = args.test_failure_download.upper()
        logger.info(f"TEST: Injected download failure on {ticker}")
        try:
            wipe_reload_cascade(ticker, fail_simulation="download")
            sys.exit(1)  # Should not reach here
        except ConnectionError as e:
            logger.info(f"TEST PASSED: Caught expected error: {e}")
            sys.exit(0)

    elif args.test_failure_db:
        ticker = args.test_failure_db.upper()
        logger.info(f"TEST: Injected DB failure on {ticker}")
        try:
            wipe_reload_cascade(ticker, fail_simulation="db")
            sys.exit(1)  # Should not reach here
        except RuntimeError as e:
            logger.info(f"TEST PASSED: Caught expected error: {e}")
            sys.exit(0)

    elif args.ticker:
        res = wipe_reload_cascade(args.ticker)
        print(res)

    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        for t in tickers:
            res = wipe_reload_cascade(t)
            print(res)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
