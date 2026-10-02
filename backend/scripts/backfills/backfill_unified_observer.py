#!/usr/bin/env python3
"""
Backfill Unified Observer — Populate engine.channel_snapshots
================================================================
Computes UnifiedKalmanObserver for all tickers and persists
obs_recovery_score, obs_velocity_norm, obs_state to the Vault.

Run once after deploying the Observer module:
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_unified_observer.py
"""
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
import logging

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.unified_observer import compute_observer_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


# ── Per-column empirical bounds to prevent explosive numerical drift ──
# Derived from empirical census across 4.4M bars (Neon SSOT):
# - obs_recovery_score: naturally in [-1, +1]
# - obs_velocity_norm:  p99=2.67, legitimate transitions reach up to ~10.0 (bound 20.0)
# - obs_vel_svw:        p99.9=1.84, delta física máx ~6.4 (bound 10.0)
# - obs_vel_tension_w:  p99.9=1.31, delta física máx ~6.4 (bound 10.0)
# - obs_vel_sigma_c:    p99.9=1.62, legitimate reach up to ~3.9 (bound 5.0)
# - obs_vel_rsi:        in RSI points (p50=1.65, p99=7.43, legitimate up to ~40.8, bound 50.0)
# - obs_vel_conj_wt:    p99.9=0.86, legitimate reach up to 9.06 (bound 10.0)
_BOUNDS = {
    "obs_recovery_score":  1.0,
    "obs_velocity_norm":  20.0,
    "obs_vel_svw":        10.0,
    "obs_vel_tension_w":  10.0,
    "obs_vel_sigma_c":     5.0,
    "obs_vel_rsi":        50.0,
    "obs_vel_conj_wt":    10.0,
}


def _clamp_real(v, max_abs: float) -> float:
    """Clamp subnormal floats (< 1e-30) and explosive floats (|v| > max_abs) to 0.0."""
    if v is None:
        return 0.0
    fv = float(v)
    if not np.isfinite(fv) or abs(fv) < 1e-30 or abs(fv) > max_abs:
        return 0.0
    return fv


def main():
    store = TimescaleDataStore()
    conn = store._conn()

    # 1. Ensure columns exist
    logger.info("Ensuring Observer columns exist in engine.channel_snapshots...")
    with conn.cursor() as cur:
        for col, dtype in [
            ("obs_recovery_score", "REAL"),
            ("obs_velocity_norm", "REAL"),
            ("obs_state", "TEXT"),
            ("obs_kf_consensus", "INTEGER"),
            ("obs_vel_sigma_c", "REAL"),
            ("obs_vel_svw", "REAL"),
            ("obs_vel_tension_w", "REAL"),
            ("obs_vel_rsi", "REAL"),
            ("obs_vel_conj_wt", "REAL"),
            ("slope_tripleta", "TEXT"),
        ]:
            cur.execute(f"""
                ALTER TABLE engine.channel_snapshots
                ADD COLUMN IF NOT EXISTS {col} {dtype}
            """)
        conn.commit()
    logger.info("  Columns ready.")

    # Query tickers that still have NULL obs_vel_svw
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT ticker FROM engine.channel_snapshots WHERE obs_vel_svw IS NULL ORDER BY ticker;")
        tickers_to_process = [r[0] for r in cur.fetchall()]
    logger.info(f"  {len(tickers_to_process)} tickers have NULL obs_vel_svw: {tickers_to_process}")

    if not tickers_to_process:
        logger.info("  All tickers already completed. Nothing to do.")
        store._put(conn)
        store.close()
        return

    # 2. Load channel snapshots for target tickers
    logger.info("Loading channel snapshots for target tickers...")
    cs = pd.read_sql("""
        SELECT ticker, timestamp,
               sigma_current, vwap_sigma_wave, tension_wave,
               rsi_value, conj_wave_tide
        FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND ticker = ANY(%s)
        ORDER BY ticker, timestamp
    """, conn, params=(tickers_to_process,))
    logger.info(f"  {len(cs):,} snapshots, {cs['ticker'].nunique()} tickers")

    # 3. Compute Observer per ticker
    total_updated = 0
    for ticker in tickers_to_process:
        tk = cs[cs['ticker'] == ticker].sort_values('timestamp').copy()
        if len(tk) < 100:
            logger.info(f"  {ticker}: skipping ({len(tk)} bars < 100)")
            continue

        outputs = compute_observer_series(
            sigma_current=tk['sigma_current'].fillna(0).values,
            vwap_sigma_wave=tk['vwap_sigma_wave'].fillna(0).values,
            tension_wave=tk['tension_wave'].fillna(0).values,
            rsi_value=tk['rsi_value'].fillna(0).values,
            conj_wave_tide=tk['conj_wave_tide'].fillna(0).values,
        )

        # 4. Batch update
        updates = []
        for ts, out in zip(tk['timestamp'].values, outputs):
            # Convert numpy datetime64 to Python datetime for psycopg2
            py_ts = pd.Timestamp(ts).to_pydatetime()
            updates.append((
                _clamp_real(out.recovery_score, _BOUNDS["obs_recovery_score"]),
                _clamp_real(out.velocity_norm, _BOUNDS["obs_velocity_norm"]),
                out.state,
                out.kf_consensus,
                _clamp_real(out.vel_sigma_c, _BOUNDS["obs_vel_sigma_c"]),
                _clamp_real(out.vel_svw, _BOUNDS["obs_vel_svw"]),
                _clamp_real(out.vel_tension_w, _BOUNDS["obs_vel_tension_w"]),
                _clamp_real(out.vel_rsi, _BOUNDS["obs_vel_rsi"]),
                _clamp_real(out.vel_conj_wt, _BOUNDS["obs_vel_conj_wt"]),
                ticker, py_ts,
            ))

        with conn.cursor() as cur:
            from psycopg2.extras import execute_batch
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

        n = len(outputs)
        n_recovering = sum(1 for o in outputs if o.state == "RECOVERING")
        logger.info(f"  {ticker}: {n:,} bars updated, "
                    f"{n_recovering} RECOVERING ({n_recovering/n:.1%})")
        total_updated += n

    store._put(conn)
    store.close()
    logger.info(f"\nDONE: {total_updated:,} total bars updated")


if __name__ == "__main__":
    main()
