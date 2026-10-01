"""
Observer Provider — Unified Kalman Observer daily update
============================================================
After channel_snapshots are populated for today (by the OHLCV→RC backfill
pipeline), this provider computes the UnifiedKalmanObserver for each ticker
and persists obs_recovery_score, obs_velocity_norm, obs_state.

Runs once daily. Requires channel_snapshots to exist for the ticker.

Architecture: Delivery mechanism (daemon provider). Calls pure domain
rule (unified_observer.py). Writes directly to Vault.
"""
import logging
import math
from datetime import datetime, UTC
import numpy as np

from backend.daemons.vault_providers import register_provider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

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
    if not math.isfinite(fv) or abs(fv) < 1e-30 or abs(fv) > max_abs:
        return 0.0
    return fv


class ObserverProvider:
    """Vault provider for Unified Kalman Observer updates."""

    name = "observer"
    categories = ["observer"]

    # Fallback tickers if dynamic query fails
    TICKERS = [
        "AAPL", "AMZN", "COST", "HD", "HON", "IBM", "JNJ", "JPM",
        "MCD", "MRK", "MSFT", "PEP", "PG", "QQQ", "SPY", "WMT", "XOM",
    ]

    # Warmup: use 100 bars of history for filter initialization
    WARMUP_BARS = 100

    def get_tickers(self, conn) -> list[str]:
        """Fetch canonical universe dynamically with fallback to hardcoded list."""
        try:
            from backend.scripts._lib.universe import get_canonical_universe
            u = get_canonical_universe(conn, min_bars=100)
            if u and len(u) >= 100:
                return u
        except Exception as e:
            logger.warning(f"Observer: could not load canonical universe dynamically: {e}")
        return self.TICKERS

    def _ensure_columns(self, conn) -> None:
        """Ensure required observer columns exist on engine.channel_snapshots."""
        try:
            with conn.cursor() as cur:
                cols = [
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
                ]
                for col, dtype in cols:
                    cur.execute(f"ALTER TABLE engine.channel_snapshots ADD COLUMN IF NOT EXISTS {col} {dtype}")
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Observer: column migration failed: {e}")

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Compute Observer for all tickers using latest snapshots."""
        from backend.modules.shared.domain.rules.unified_observer import (
            UnifiedKalmanObserver, OBS_FIELDS,
        )
        import numpy as np

        updated = 0
        skipped = 0
        conn = store._conn()

        try:
            self._ensure_columns(conn)
            tickers = self.get_tickers(conn)
            for ticker in tickers:
                try:
                    result = self._update_ticker(conn, ticker)
                    if result:
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    conn.rollback()
                    logger.warning(f"Observer {ticker}: failed: {e}")
                    skipped += 1

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Observer provider failed: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            store._put(conn)

        logger.info(f"🔭 Observer: {updated} tickers updated, {skipped} skipped")
        return {"status": "ok", "updated": updated, "skipped": skipped}

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Update Observer for a single ticker on-demand."""
        conn = store._conn()
        try:
            self._ensure_columns(conn)
            result = self._update_ticker(conn, ticker)
            conn.commit()
            return {"status": "ok" if result else "skipped"}
        except Exception as e:
            conn.rollback()
            return {"status": "error", "error": str(e)}
        finally:
            store._put(conn)

    def _update_ticker(self, conn, ticker: str) -> bool:
        """Compute Observer for one ticker using last WARMUP_BARS snapshots.

        Returns True if updated, False if skipped (insufficient data).
        """
        import numpy as np
        from psycopg2.extras import RealDictCursor
        from backend.modules.shared.domain.rules.unified_observer import (
            UnifiedKalmanObserver, OBS_FIELDS,
        )

        # Load last N snapshots (need warmup + today)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT timestamp, sigma_current, vwap_sigma_wave,
                       tension_wave, rsi_value, conj_wave_tide
                FROM engine.channel_snapshots
                WHERE ticker = %s AND timeframe = '1d'
                ORDER BY timestamp DESC
                LIMIT %s
            """, (ticker, self.WARMUP_BARS + 10))
            rows = cur.fetchall()

        if len(rows) < 50:
            logger.debug(f"Observer {ticker}: only {len(rows)} bars, need 50+")
            return False

        # Reverse to chronological order
        rows = list(reversed(rows))

        # Build observation matrix
        obs = np.array([
            [
                float(r.get('sigma_current') or 0),
                float(r.get('vwap_sigma_wave') or 0),
                float(r.get('tension_wave') or 0),
                float(r.get('rsi_value') or 0),
                float(r.get('conj_wave_tide') or 0),
            ]
            for r in rows
        ])

        # Initialize and run Observer
        warmup = min(50, len(rows) // 2)
        data_std = np.std(obs[:warmup], axis=0)
        data_std = np.maximum(data_std, 1e-6)

        observer = UnifiedKalmanObserver()
        observer.reset(obs[0], data_std)

        # Run through all bars; we only need the LAST output
        last_output = None
        for i in range(len(obs)):
            last_output = observer.update(obs[i])

        if last_output is None:
            return False

        # Persist the latest bar's Observer output
        latest_ts = rows[-1]['timestamp']
        with conn.cursor() as cur:
            cur.execute("""
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
            """, (
                _clamp_real(last_output.recovery_score, _BOUNDS["obs_recovery_score"]),
                _clamp_real(last_output.velocity_norm, _BOUNDS["obs_velocity_norm"]),
                last_output.state,
                last_output.kf_consensus,
                _clamp_real(last_output.vel_sigma_c, _BOUNDS["obs_vel_sigma_c"]),
                _clamp_real(last_output.vel_svw, _BOUNDS["obs_vel_svw"]),
                _clamp_real(last_output.vel_tension_w, _BOUNDS["obs_vel_tension_w"]),
                _clamp_real(last_output.vel_rsi, _BOUNDS["obs_vel_rsi"]),
                _clamp_real(last_output.vel_conj_wt, _BOUNDS["obs_vel_conj_wt"]),
                ticker, latest_ts,
            ))

        logger.debug(
            f"Observer {ticker}: recovery={last_output.recovery_score:+.3f} "
            f"state={last_output.state}"
        )
        return True


# Auto-register on import
register_provider(ObserverProvider())
