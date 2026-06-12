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
            ("obs_vel_sigma_c", "REAL"),
            ("obs_vel_svw", "REAL"),
            ("obs_vel_tension_w", "REAL"),
            ("obs_vel_rsi", "REAL"),
            ("obs_vel_conj_wt", "REAL"),
        ]:
            cur.execute(f"""
                ALTER TABLE engine.channel_snapshots
                ADD COLUMN IF NOT EXISTS {col} {dtype}
            """)
        conn.commit()
    logger.info("  Columns ready.")

    # 2. Load all channel snapshots
    logger.info("Loading channel snapshots...")
    cs = pd.read_sql("""
        SELECT ticker, timestamp,
               sigma_current, vwap_sigma_wave, tension_wave,
               rsi_value, conj_wave_tide
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
        ORDER BY ticker, timestamp
    """, conn)
    logger.info(f"  {len(cs):,} snapshots, {cs['ticker'].nunique()} tickers")

    # 3. Compute Observer per ticker
    total_updated = 0
    for ticker in cs['ticker'].unique():
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
                out.recovery_score, out.velocity_norm, out.state,
                out.vel_sigma_c, out.vel_svw, out.vel_tension_w,
                out.vel_rsi, out.vel_conj_wt,
                ticker, py_ts,
            ))

        with conn.cursor() as cur:
            from psycopg2.extras import execute_batch
            execute_batch(cur, """
                UPDATE engine.channel_snapshots
                SET obs_recovery_score = %s,
                    obs_velocity_norm = %s,
                    obs_state = %s,
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
