"""
Train Ticker Profiles — Statistical Calibration per Ticker
=============================================================
Computes percentile tables (TSI/ADI) and RSI regime bands for each
ticker in the Vault. These are PURE STATISTICS — no ML here.

For each ticker:
  1. Load ALL channel_snapshots (5,000+ per ticker)
  2. Compute 101-point percentile tables for 6 distributions:
     - tide_slope, current_slope, wave_slope (TSI)
     - tension_tide, tension_current, tension_wave (ADI)
  3. Compute RSI(14) over full price history
  4. Filter RSI by regime, extract P5/P95 as Cardwell bands
  5. Detect dominant cycle via autocorrelation
  6. Persist as TickerProfile in engine.ticker_profiles

Usage:
    python backend/scripts/train_ticker_profiles.py
    python backend/scripts/train_ticker_profiles.py --ticker AAPL
    python backend/scripts/train_ticker_profiles.py --dry-run
"""
import argparse
import logging
import sys
from pathlib import Path

import numpy as np

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from backend.modules.shared.domain.entities.ticker_profile import TickerProfile
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# ── RSI Computation (standalone, no module dependency) ─────────

def _compute_rsi_series(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's RSI. Returns full-length array (first `period` = 50)."""
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.zeros(len(gains))
    avg_loss = np.zeros(len(gains))
    avg_gain[period - 1] = np.mean(gains[:period])
    avg_loss[period - 1] = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

    rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi[:period] = 50.0
    return rsi


# ── Profile Training ──────────────────────────────────────────

def train_profile(
    ticker: str,
    vault: TimescaleDataStore,
) -> TickerProfile:
    """Train a TickerProfile from historical data.

    Pure statistics: percentiles, RSI bands, cycle detection.
    No ML models here — those come from the Unified Pre-Trainer.
    """
    logger.info(f"Training profile for {ticker}...")
    conn = vault._conn()
    cur = conn.cursor()

    # ── 1. Load all channel_snapshots ──
    cur.execute("""
        SELECT tide_slope, current_slope, wave_slope,
               tension_tide, tension_current, tension_wave,
               regime
        FROM engine.channel_snapshots
        WHERE ticker = %s
          AND tide_slope IS NOT NULL
          AND current_slope IS NOT NULL
          AND wave_slope IS NOT NULL
        ORDER BY timestamp
    """, (ticker,))
    rows = cur.fetchall()

    if len(rows) < 100:
        logger.warning(f"{ticker}: Only {len(rows)} snapshots — skipping")
        vault._put(conn)
        return None

    tide_slopes = np.array([r[0] for r in rows])
    current_slopes = np.array([r[1] for r in rows])
    wave_slopes = np.array([r[2] for r in rows])
    tension_tides = np.array([r[3] for r in rows])
    tension_currents = np.array([r[4] for r in rows])
    tension_waves = np.array([r[5] for r in rows])
    regimes = [r[6] for r in rows]

    # ── 2. Compute TSI percentile tables (101 points each) ──
    percentile_range = np.arange(101)  # 0, 1, 2, ..., 100

    tsi_tide = np.percentile(tide_slopes, percentile_range).tolist()
    tsi_current = np.percentile(current_slopes, percentile_range).tolist()
    tsi_wave = np.percentile(wave_slopes, percentile_range).tolist()

    # ── 3. Compute ADI percentile tables ──
    adi_tide = np.percentile(tension_tides, percentile_range).tolist()
    adi_current = np.percentile(tension_currents, percentile_range).tolist()
    adi_wave = np.percentile(tension_waves, percentile_range).tolist()

    logger.info(
        f"  TSI tide: P5={tsi_tide[5]:+.4f}  P50={tsi_tide[50]:+.4f}  "
        f"P95={tsi_tide[95]:+.4f}  (n={len(rows):,d})"
    )

    # ── 4. Load OHLCV for RSI bands ──
    cur.execute("""
        SELECT close FROM market.ohlcv_bars
        WHERE ticker = %s AND timeframe = '1d'
        ORDER BY time
    """, (ticker,))
    closes = np.array([r[0] for r in cur.fetchall()], dtype=float)

    rsi_bull_floor = 40.0
    rsi_bull_ceil = 80.0
    rsi_bear_floor = 20.0
    rsi_bear_ceil = 60.0
    dominant_cycle = 28

    if len(closes) >= 250:
        # Compute RSI
        rsi_full = _compute_rsi_series(closes, 14)
        rsi_valid = rsi_full[14:]  # Skip warmup

        # We need regime labels aligned with RSI. Use the snapshot regimes.
        # Snapshots may not cover the full OHLCV history, so we use
        # the latest `len(rows)` RSI values aligned with snapshots.
        n_snap = len(rows)
        if len(rsi_valid) >= n_snap:
            rsi_aligned = rsi_valid[-n_snap:]

            # RSI in BULL regime
            bull_mask = np.array([r == "BULL" for r in regimes])
            if bull_mask.sum() > 50:
                rsi_bull = rsi_aligned[bull_mask]
                rsi_bull_floor = round(float(np.percentile(rsi_bull, 5)), 1)
                rsi_bull_ceil = round(float(np.percentile(rsi_bull, 95)), 1)

            # RSI in BEAR regime
            bear_mask = np.array([r == "BEAR" for r in regimes])
            if bear_mask.sum() > 50:
                rsi_bear = rsi_aligned[bear_mask]
                rsi_bear_floor = round(float(np.percentile(rsi_bear, 5)), 1)
                rsi_bear_ceil = round(float(np.percentile(rsi_bear, 95)), 1)

        logger.info(
            f"  RSI bands: BULL[{rsi_bull_floor}-{rsi_bull_ceil}] "
            f"BEAR[{rsi_bear_floor}-{rsi_bear_ceil}]"
        )

        # ── 5. Dominant cycle detection ──
        dominant_cycle = detect_dominant_cycle(closes)
        logger.info(f"  Dominant cycle: {dominant_cycle} bars")

    vault._put(conn)

    # ── 6. Build profile ──
    profile = TickerProfile(
        ticker=ticker,
        tsi_tide_percentiles=tsi_tide,
        tsi_current_percentiles=tsi_current,
        tsi_wave_percentiles=tsi_wave,
        adi_tide_percentiles=adi_tide,
        adi_current_percentiles=adi_current,
        adi_wave_percentiles=adi_wave,
        rsi_bull_floor=rsi_bull_floor,
        rsi_bull_ceil=rsi_bull_ceil,
        rsi_bear_floor=rsi_bear_floor,
        rsi_bear_ceil=rsi_bear_ceil,
        dominant_cycle=dominant_cycle,
        n_observations=len(rows),
    )

    logger.info(f"  ✅ Profile trained: {len(rows):,d} obs, "
                f"cycle={dominant_cycle}, v{profile.version}")
    return profile


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Train per-ticker profiles")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Single ticker to train (default: all Vault tickers)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but don't persist")
    args = parser.parse_args()

    vault = TimescaleDataStore()
    store = TickerProfileStore()
    store.ensure_table()

    # Get tickers from Vault
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        conn = vault._conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ticker FROM engine.channel_snapshots
            WHERE tide_slope IS NOT NULL
            ORDER BY ticker
        """)
        tickers = [r[0] for r in cur.fetchall()]
        vault._put(conn)
        logger.info(f"Found {len(tickers)} tickers in Vault: {tickers}")

    trained = 0
    for ticker in tickers:
        profile = train_profile(ticker, vault)
        if profile is None:
            continue

        if args.dry_run:
            logger.info(f"  [DRY RUN] Would save profile for {ticker}")
        else:
            store.save_profile(profile)
            trained += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"Trained {trained}/{len(tickers)} profiles")

    # Verification: load one back and check
    if trained > 0 and not args.dry_run:
        test_ticker = tickers[0]
        loaded = store.load_profile(test_ticker)
        assert loaded is not None, f"Failed to load profile for {test_ticker}"
        assert len(loaded.tsi_tide_percentiles) == 101, \
            f"TSI tide has {len(loaded.tsi_tide_percentiles)} points, expected 101"
        logger.info(f"✅ Verification: {test_ticker} profile round-trip OK")

        # Quick TSI test
        tsi = loaded.get_tsi("tide", 0.0)
        logger.info(f"  {test_ticker}: slope=0.0 → TSI={tsi} "
                     f"(expected ~25 for most tickers)")

    store.close()
    vault.close()


if __name__ == "__main__":
    main()
