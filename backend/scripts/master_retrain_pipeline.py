#!/usr/bin/env python3
"""
Master Pipeline — ETF Zigzag + Observer Backfill + Retrain Combined Table
=========================================================================
Runs 5 steps sequentially:
  1. Backfill zigzag_points for 32 ETFs (3 levels)
  2. Backfill Unified Observer (obs_*) for ALL tickers missing it
  3. Data quality audit
  4. Retrain rc_combined_probability_table.json (source table)
  5. Generate rc_combined_derived.json (committee-approved signals)

NOTE: The deprecated enriched (rc_probability_table_enriched.json) and
      tripleta (rc_tripleta_probability_table.json) pipelines have been
      removed. The architecture is now: train_combined_table.py →
      generate_derived_table.py → rc_combined_derived.json (PRIMARY).

Usage:
  nohup bash -c 'PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/master_retrain_pipeline.py' \
    > /tmp/master_pipeline.log 2>&1 &
"""
import os, sys, time, json, logging
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

RULES_DIR = root_dir / "backend/modules/quality_swing/domain/rules"


# ═══════════════════════════════════════════════════════════════
# STEP 1: Backfill zigzag for ETFs
# ═══════════════════════════════════════════════════════════════
def step1_backfill_etf_zigzag():
    """Backfill zigzag_points for ETFs that have channel_snapshots but no zigzag."""
    from backend.scripts.backfill_zigzag_points import (
        zigzag_canonical, process_ticker, _insert_batch, get_existing_combos,
    )

    logger.info("=" * 80)
    logger.info("  STEP 1: BACKFILL ZIGZAG FOR ETFs")
    logger.info("=" * 80)

    store = TimescaleDataStore()
    conn = store._conn()

    # Find ETFs with snapshots but no zigzag
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT cs.ticker
            FROM engine.channel_snapshots cs
            JOIN market.ticker_metadata tm ON tm.ticker = cs.ticker
            WHERE tm.asset_type = 'ETF'
            ORDER BY cs.ticker
        """)
        etf_tickers = [r[0] for r in cur.fetchall()]
    store._put(conn)

    # Get existing combos to skip
    existing = get_existing_combos(store)
    work = []
    for ticker in etf_tickers:
        for level in [0.025, 0.05, 0.075]:
            if (ticker, level) not in existing:
                work.append((ticker, level))

    logger.info(f"  ETFs total: {len(etf_tickers)}, combos to process: {len(work)}")
    if not work:
        logger.info("  Nothing to do — all ETFs already have zigzag.")
        store.close()
        return

    total_pivots = 0
    conn = store._conn()

    for i, (ticker, level) in enumerate(work):
        rows = process_ticker(store, ticker, level)
        if rows:
            _insert_batch(conn, rows)
            total_pivots += len(rows)

        if (i + 1) % 10 == 0 or i == len(work) - 1:
            logger.info(f"  [{i+1}/{len(work)}] {ticker}@{level}: "
                        f"total pivots={total_pivots:,}")

    store._put(conn)
    store.close()
    logger.info(f"  ✅ ETF zigzag complete: {total_pivots:,} pivots\n")


# ═══════════════════════════════════════════════════════════════
# STEP 2: Backfill Unified Observer
# ═══════════════════════════════════════════════════════════════
def step2_backfill_observer():
    """Backfill obs_* for all tickers that don't have it yet."""
    from backend.modules.shared.domain.rules.unified_observer import compute_observer_series
    from psycopg2.extras import execute_batch

    logger.info("=" * 80)
    logger.info("  STEP 2: BACKFILL UNIFIED KALMAN OBSERVER")
    logger.info("=" * 80)

    store = TimescaleDataStore()
    conn = store._conn()

    # Find tickers with NULL obs_recovery_score
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ticker, COUNT(*) as total,
                   COUNT(obs_recovery_score) as with_obs
            FROM engine.channel_snapshots
            WHERE timeframe = '1d'
            GROUP BY ticker
            HAVING COUNT(obs_recovery_score) < COUNT(*)
            ORDER BY ticker
        """)
        need_obs = [(r[0], r[1], r[2]) for r in cur.fetchall()]

    logger.info(f"  Tickers needing Observer: {len(need_obs)}")
    if not need_obs:
        logger.info("  Nothing to do.")
        store._put(conn)
        store.close()
        return

    total_updated = 0
    t0 = time.time()

    for i, (ticker, total, existing) in enumerate(need_obs):
        # Load snapshot data
        with conn.cursor() as cur:
            cur.execute("""
                SELECT timestamp, sigma_current, vwap_sigma_wave,
                       tension_wave, rsi_value, conj_wave_tide
                FROM engine.channel_snapshots
                WHERE ticker = %s AND timeframe = '1d'
                ORDER BY timestamp
            """, (ticker,))
            rows = cur.fetchall()

        if len(rows) < 100:
            continue

        timestamps = [r[0] for r in rows]
        sc = np.array([float(r[1] or 0) for r in rows])
        svw = np.array([float(r[2] or 0) for r in rows])
        tw = np.array([float(r[3] or 0) for r in rows])
        rsi = np.array([float(r[4] or 0) for r in rows])
        cwt = np.array([float(r[5] or 0) for r in rows])

        outputs = compute_observer_series(sc, svw, tw, rsi, cwt)

        updates = []
        for ts, out in zip(timestamps, outputs):
            updates.append((
                out.recovery_score, out.velocity_norm, out.state,
                out.kf_consensus,
                out.vel_sigma_c, out.vel_svw, out.vel_tension_w,
                out.vel_rsi, out.vel_conj_wt,
                ticker, ts,
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

        total_updated += len(outputs)

        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(need_obs) - i - 1) / rate / 60
            logger.info(
                f"  [{i+1}/{len(need_obs)}] {ticker}: {len(outputs)} bars | "
                f"total: {total_updated:,} | ETA: {eta:.0f}min"
            )

    store._put(conn)
    store.close()
    logger.info(f"  ✅ Observer backfill complete: {total_updated:,} bars updated\n")


# ═══════════════════════════════════════════════════════════════
# STEP 3: Data Quality Audit
# ═══════════════════════════════════════════════════════════════
def step3_audit():
    """Quick data quality audit after backfills."""
    logger.info("=" * 80)
    logger.info("  STEP 3: DATA QUALITY AUDIT")
    logger.info("=" * 80)

    store = TimescaleDataStore()
    conn = store._conn()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM engine.channel_snapshots")
        total, n_tk = cur.fetchone()
        logger.info(f"  Snapshots: {total:,} rows × {n_tk} tickers")

        # Observer coverage
        cur.execute("""
            SELECT COUNT(obs_recovery_score), COUNT(*) FROM engine.channel_snapshots
        """)
        with_obs, total_obs = cur.fetchone()
        logger.info(f"  Observer: {with_obs:,}/{total_obs:,} ({with_obs/total_obs*100:.1f}%)")

        # Zigzag coverage
        for level in [0.025, 0.05, 0.075]:
            cur.execute("""
                SELECT COUNT(*), COUNT(DISTINCT ticker) FROM engine.zigzag_points
                WHERE min_swing_pct = %s
            """, (level,))
            zz_n, zz_tk = cur.fetchone()
            logger.info(f"  ZZ {level*100:.1f}%: {zz_n:,} pivots × {zz_tk} tickers")

        # Cross-coverage: snapshots with zigzag
        cur.execute("""
            SELECT COUNT(DISTINCT cs.ticker) FROM engine.channel_snapshots cs
            WHERE EXISTS (SELECT 1 FROM engine.zigzag_points zz WHERE zz.ticker = cs.ticker)
        """)
        covered = cur.fetchone()[0]
        logger.info(f"  Snapshots with zigzag: {covered}/{n_tk}")

        # NULL check on critical columns
        for col in ['tide_slope', 'wave_slope', 'vwap_sigma_wave', 'rsi_value',
                     'obs_recovery_score', 'obs_state']:
            cur.execute(f"SELECT COUNT({col}), COUNT(*) FROM engine.channel_snapshots")
            nn, tt = cur.fetchone()
            pct = nn / tt * 100
            flag = "✅" if pct > 99 else ("⚠️" if pct > 80 else "❌")
            logger.info(f"  {flag} {col}: {nn:,}/{tt:,} ({pct:.1f}%)")

    store._put(conn)
    store.close()
    logger.info("")


# ═══════════════════════════════════════════════════════════════
# STEP 4: Retrain combined table (source)
# ═══════════════════════════════════════════════════════════════
def step4_retrain_combined():
    """Retrain rc_combined_probability_table.json (T×C×σVw source)."""
    logger.info("=" * 80)
    logger.info("  STEP 4: RETRAIN COMBINED TABLE (T×C×σVw + zigzag)")
    logger.info("=" * 80)

    import subprocess
    result = subprocess.run(
        [str(root_dir / "backend/.venv/bin/python"),
         str(root_dir / "backend/scripts/train_combined_table.py")],
        env={**os.environ, "PYTHONPATH": str(root_dir)},
        capture_output=True, text=True, timeout=1800,
    )
    if result.stdout:
        for line in result.stdout.strip().split("\n")[-15:]:
            logger.info(f"  {line}")
    if result.returncode != 0:
        logger.error(f"  ❌ Failed: {result.stderr[-500:]}")
    else:
        logger.info("  ✅ Combined table retrained\n")


# ═══════════════════════════════════════════════════════════════
# STEP 5: Generate derived table (committee signals)
# ═══════════════════════════════════════════════════════════════
def step5_generate_derived():
    """Generate rc_combined_derived.json (committee-approved signals + confidence)."""
    logger.info("=" * 80)
    logger.info("  STEP 5: GENERATE DERIVED TABLE (committee signals + confidence)")
    logger.info("=" * 80)

    import subprocess
    result = subprocess.run(
        [str(root_dir / "backend/.venv/bin/python"),
         str(root_dir / "backend/scripts/generate_derived_table.py")],
        env={**os.environ, "PYTHONPATH": str(root_dir)},
        capture_output=True, text=True, timeout=120,
    )
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            logger.info(f"  {line}")
    if result.returncode != 0:
        logger.error(f"  ❌ Failed: {result.stderr[-500:]}")
    else:
        logger.info("  ✅ Derived table generated\n")


# ═══════════════════════════════════════════════════════════════
# STEP 6: Final Validation
# ═══════════════════════════════════════════════════════════════
def step6_final_validation():
    """Validate active JSON files have correct structure."""
    logger.info("=" * 80)
    logger.info("  STEP 6: FINAL VALIDATION")
    logger.info("=" * 80)

    files = [
        ("rc_combined_probability_table.json", "T×C×σVw + zigzag (source)"),
        ("rc_combined_derived.json", "committee signals + confidence (PRIMARY)"),
    ]

    for fname, desc in files:
        path = RULES_DIR / fname
        if not path.exists():
            logger.error(f"  ❌ MISSING: {fname} ({desc})")
            continue

        with open(path) as f:
            data = json.load(f)

        if fname == "rc_combined_derived.json":
            states = data.get("states", {})
            n_states = len(states)
            sigs = Counter(s["identity"]["signal"] for s in states.values())
            has_conf = all("signal_confidence" in s["identity"] for s in states.values())
            logger.info(
                f"  ✅ {fname}: {n_states} states, signals={dict(sigs.most_common())}, "
                f"signal_confidence={'present' if has_conf else 'MISSING'}"
            )
        else:
            cells = data.get("cells", {})
            n_obs = data.get("n_total_observations", 0)
            n_tk = data.get("n_tickers", 0)
            levels = defaultdict(int)
            for k in cells:
                lvl = k.split(":")[0]
                levels[lvl] += 1
            errors = 0
            for k, c in cells.items():
                n = sum(c.get(f"count_{s}", 0) for s in ["HH", "HL", "LH", "LL"])
                if n == 0:
                    errors += 1
            logger.info(
                f"  {'✅' if errors == 0 else '❌'} {fname}: "
                f"{len(cells)} cells, {n_obs:,} obs, {n_tk} tickers, "
                f"levels={dict(levels)}, {errors} errors"
            )

    logger.info("")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    logger.info("█" * 80)
    logger.info("  MASTER RETRAIN PIPELINE")
    logger.info(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("█" * 80)

    step1_backfill_etf_zigzag()
    step2_backfill_observer()
    step3_audit()
    step4_retrain_combined()
    step5_generate_derived()
    step6_final_validation()

    elapsed = time.time() - t0
    logger.info("█" * 80)
    logger.info(f"  PIPELINE COMPLETE — {elapsed:.0f}s ({elapsed/60:.1f} min)")
    logger.info(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("█" * 80)


if __name__ == "__main__":
    main()
