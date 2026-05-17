"""
Neon Passport Store — PostgreSQL implementation of PassportStorePort
=====================================================================
Persists Signal Reliability Passports to engine.signal_passports.

Schema (DDL auto-created on first use via ensure_schema()):
    engine.signal_passports (
        ticker           TEXT NOT NULL,
        department       TEXT NOT NULL,   -- QUALITY_CORE | QUALITY_SWING
        signal_name      TEXT NOT NULL,

        -- Core performance
        ceiling_sharpe   FLOAT,
        floor_sharpe     FLOAT,
        win_rate         FLOAT,
        profit_factor    FLOAT,
        n_entries        INT,
        avg_return_pct   FLOAT,
        total_return_pct FLOAT,
        max_drawdown_pct FLOAT,
        avg_bars_held    FLOAT,
        avg_bars_to_loss FLOAT,
        pct_loss_hit     FLOAT,
        pct_time_hit     FLOAT,

        -- Reliability scores
        reliability_score FLOAT,
        consistency_score FLOAT,
        oos_sharpe        FLOAT,
        oos_win_rate      FLOAT,

        -- JSONB breakdowns (regime, fear_level, sigma_band, etc.)
        regime_breakdown  JSONB,   -- {sharpe_by: {}, wr_by: {}, n_by: {}}
        swing_breakdown   JSONB,   -- {wr_fear: {}, n_fear: {}, wr_sigma: {}, ...}
        core_breakdown    JSONB,   -- {recovery_bars: x, survival_rate: x}

        -- Gate fields
        viable           BOOL,
        grade            TEXT,
        geometry_used    JSONB,
        calibrated_at    TIMESTAMPTZ DEFAULT NOW(),

        PRIMARY KEY (ticker, department, signal_name)
    )
"""
import json
import logging
import os
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from backend.modules.simulation.domain.entities.signal_passport import SignalPassport
from backend.modules.simulation.domain.ports.passport_store_port import PassportStorePort

logger = logging.getLogger(__name__)

_DDL = """
CREATE SCHEMA IF NOT EXISTS engine;

CREATE TABLE IF NOT EXISTS engine.signal_passports (
    ticker            TEXT NOT NULL,
    department        TEXT NOT NULL,
    signal_name       TEXT NOT NULL,

    ceiling_sharpe    FLOAT,
    floor_sharpe      FLOAT,
    win_rate          FLOAT,
    profit_factor     FLOAT,
    n_entries         INT,
    avg_return_pct    FLOAT,
    total_return_pct  FLOAT,
    max_drawdown_pct  FLOAT,
    avg_bars_held     FLOAT,
    avg_bars_to_loss  FLOAT,
    pct_loss_hit      FLOAT,
    pct_time_hit      FLOAT,

    reliability_score FLOAT,
    consistency_score FLOAT,
    oos_sharpe        FLOAT,
    oos_win_rate      FLOAT,

    regime_breakdown  JSONB,
    swing_breakdown   JSONB,
    core_breakdown    JSONB,

    viable            BOOLEAN,
    grade             TEXT,
    geometry_used     JSONB,
    calibrated_at     TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (ticker, department, signal_name)
);
"""


class NeonPassportStore(PassportStorePort):
    """Persists Signal Reliability Passports to Neon PostgreSQL."""

    def __init__(self, dsn: str | None = None):
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=3,
            dsn=dsn or os.environ.get("POSTGRES_URL", ""),
        )

    def ensure_schema(self) -> None:
        """Create engine.signal_passports if it doesn't exist."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(_DDL)
            conn.commit()
            logger.info("NeonPassportStore: schema ensured")
        except Exception as e:
            conn.rollback()
            logger.error(f"NeonPassportStore: schema creation failed: {e}")
            raise
        finally:
            self._pool.putconn(conn)

    def save_passport(self, passport: SignalPassport) -> None:
        """Upsert a passport. Key: (ticker, department, signal_name)."""
        regime = {
            "sharpe_by": passport.sharpe_by_vol_regime,
            "wr_by": passport.wr_by_vol_regime,
            "n_by": passport.n_by_vol_regime,
        }
        swing = {
            "wr_fear": passport.wr_by_fear_level,
            "n_fear": passport.n_by_fear_level,
            "wr_sigma": passport.wr_by_sigma_band,
            "n_sigma": passport.n_by_sigma_band,
            "wave_flip_wr": passport.wave_flip_wr,
            "wave_flip_no_wr": passport.wave_flip_no_wr,
            "wave_flip_edge": passport.wave_flip_edge,
            "tide_regime_wr": passport.tide_regime_wr,
            "n_tide": passport.n_by_tide_regime,
        }
        core = {
            "drawdown_recovery_avg_bars": passport.drawdown_recovery_avg_bars,
            "thesis_survival_rate": passport.thesis_survival_rate,
        }

        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO engine.signal_passports (
                        ticker, department, signal_name,
                        ceiling_sharpe, floor_sharpe, win_rate, profit_factor,
                        n_entries, avg_return_pct, total_return_pct, max_drawdown_pct,
                        avg_bars_held, avg_bars_to_loss, pct_loss_hit, pct_time_hit,
                        reliability_score, consistency_score, oos_sharpe, oos_win_rate,
                        regime_breakdown, swing_breakdown, core_breakdown,
                        viable, grade, geometry_used, calibrated_at
                    ) VALUES (
                        %(ticker)s, %(department)s, %(signal_name)s,
                        %(ceiling_sharpe)s, %(floor_sharpe)s, %(win_rate)s, %(profit_factor)s,
                        %(n_entries)s, %(avg_return_pct)s, %(total_return_pct)s, %(max_drawdown_pct)s,
                        %(avg_bars_held)s, %(avg_bars_to_loss)s, %(pct_loss_hit)s, %(pct_time_hit)s,
                        %(reliability_score)s, %(consistency_score)s, %(oos_sharpe)s, %(oos_win_rate)s,
                        %(regime_breakdown)s, %(swing_breakdown)s, %(core_breakdown)s,
                        %(viable)s, %(grade)s, %(geometry_used)s, NOW()
                    )
                    ON CONFLICT (ticker, department, signal_name) DO UPDATE SET
                        ceiling_sharpe   = EXCLUDED.ceiling_sharpe,
                        floor_sharpe     = EXCLUDED.floor_sharpe,
                        win_rate         = EXCLUDED.win_rate,
                        profit_factor    = EXCLUDED.profit_factor,
                        n_entries        = EXCLUDED.n_entries,
                        avg_return_pct   = EXCLUDED.avg_return_pct,
                        total_return_pct = EXCLUDED.total_return_pct,
                        max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                        avg_bars_held    = EXCLUDED.avg_bars_held,
                        avg_bars_to_loss = EXCLUDED.avg_bars_to_loss,
                        pct_loss_hit     = EXCLUDED.pct_loss_hit,
                        pct_time_hit     = EXCLUDED.pct_time_hit,
                        reliability_score= EXCLUDED.reliability_score,
                        consistency_score= EXCLUDED.consistency_score,
                        oos_sharpe       = EXCLUDED.oos_sharpe,
                        oos_win_rate     = EXCLUDED.oos_win_rate,
                        regime_breakdown = EXCLUDED.regime_breakdown,
                        swing_breakdown  = EXCLUDED.swing_breakdown,
                        core_breakdown   = EXCLUDED.core_breakdown,
                        viable           = EXCLUDED.viable,
                        grade            = EXCLUDED.grade,
                        geometry_used    = EXCLUDED.geometry_used,
                        calibrated_at    = NOW()
                """, {
                    "ticker": passport.ticker,
                    "department": passport.department,
                    "signal_name": passport.signal_name,
                    "ceiling_sharpe": passport.ceiling_sharpe,
                    "floor_sharpe": passport.floor_sharpe,
                    "win_rate": passport.win_rate,
                    "profit_factor": passport.profit_factor,
                    "n_entries": passport.n_entries,
                    "avg_return_pct": passport.avg_return_pct,
                    "total_return_pct": passport.total_return_pct,
                    "max_drawdown_pct": passport.max_drawdown_pct,
                    "avg_bars_held": passport.avg_bars_held,
                    "avg_bars_to_loss": passport.avg_bars_to_loss,
                    "pct_loss_hit": passport.pct_loss_hit,
                    "pct_time_hit": passport.pct_time_hit,
                    "reliability_score": passport.reliability_score,
                    "consistency_score": passport.consistency_score,
                    "oos_sharpe": passport.oos_sharpe,
                    "oos_win_rate": passport.oos_win_rate,
                    "regime_breakdown": json.dumps(regime),
                    "swing_breakdown": json.dumps(swing),
                    "core_breakdown": json.dumps(core),
                    "viable": passport.viable,
                    "grade": passport.grade,
                    "geometry_used": json.dumps(passport.geometry_used),
                })
            conn.commit()
            logger.info(
                f"Passport saved: {passport.ticker}/{passport.department}/{passport.signal_name} "
                f"grade={passport.grade} reliability={passport.reliability_score:.2f}"
            )
        except Exception as e:
            conn.rollback()
            logger.error(f"Passport save failed: {e}")
            raise
        finally:
            self._pool.putconn(conn)

    def load_passport(
        self,
        ticker: str,
        department: str,
        signal_name: str,
    ) -> Optional[SignalPassport]:
        """Load a single passport. Returns None if not found."""
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM engine.signal_passports
                    WHERE ticker = %s AND department = %s AND signal_name = %s
                """, (ticker, department, signal_name))
                row = cur.fetchone()
                return self._row_to_passport(dict(row)) if row else None
        except Exception as e:
            logger.error(f"Passport load failed: {e}")
            return None
        finally:
            self._pool.putconn(conn)

    def load_passports_for_ticker(
        self,
        ticker: str,
        department: str,
    ) -> list[SignalPassport]:
        """Load all passports for a ticker × department."""
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM engine.signal_passports
                    WHERE ticker = %s AND department = %s
                    ORDER BY reliability_score DESC
                """, (ticker, department))
                return [self._row_to_passport(dict(r)) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Passport load_for_ticker failed: {e}")
            return []
        finally:
            self._pool.putconn(conn)

    def load_viable_passports(self, department: str) -> list[SignalPassport]:
        """Load all viable passports for a department across all tickers."""
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM engine.signal_passports
                    WHERE department = %s AND viable = true
                    ORDER BY reliability_score DESC
                """, (department,))
                return [self._row_to_passport(dict(r)) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Passport load_viable failed: {e}")
            return []
        finally:
            self._pool.putconn(conn)

    @staticmethod
    def _row_to_passport(row: dict) -> SignalPassport:
        """Convert a database row to a SignalPassport."""
        regime = row.get("regime_breakdown") or {}
        if isinstance(regime, str):
            regime = json.loads(regime)
        swing = row.get("swing_breakdown") or {}
        if isinstance(swing, str):
            swing = json.loads(swing)
        core = row.get("core_breakdown") or {}
        if isinstance(core, str):
            core = json.loads(core)
        geo = row.get("geometry_used") or {}
        if isinstance(geo, str):
            geo = json.loads(geo)

        cal = row.get("calibrated_at")

        return SignalPassport(
            ticker=row["ticker"],
            department=row["department"],
            signal_name=row["signal_name"],
            ceiling_sharpe=float(row.get("ceiling_sharpe") or 0),
            floor_sharpe=float(row.get("floor_sharpe") or 0),
            win_rate=float(row.get("win_rate") or 0),
            profit_factor=float(row.get("profit_factor") or 0),
            n_entries=int(row.get("n_entries") or 0),
            avg_return_pct=float(row.get("avg_return_pct") or 0),
            total_return_pct=float(row.get("total_return_pct") or 0),
            max_drawdown_pct=float(row.get("max_drawdown_pct") or 0),
            avg_bars_held=float(row.get("avg_bars_held") or 0),
            avg_bars_to_loss=float(row.get("avg_bars_to_loss") or 0),
            pct_loss_hit=float(row.get("pct_loss_hit") or 0),
            pct_time_hit=float(row.get("pct_time_hit") or 0),
            reliability_score=float(row.get("reliability_score") or 0),
            consistency_score=float(row.get("consistency_score") or 0),
            oos_sharpe=float(row.get("oos_sharpe") or 0),
            oos_win_rate=float(row.get("oos_win_rate") or 0),
            sharpe_by_vol_regime=regime.get("sharpe_by", {}),
            wr_by_vol_regime=regime.get("wr_by", {}),
            n_by_vol_regime=regime.get("n_by", {}),
            wr_by_fear_level=swing.get("wr_fear", {}),
            n_by_fear_level=swing.get("n_fear", {}),
            wr_by_sigma_band=swing.get("wr_sigma", {}),
            n_by_sigma_band=swing.get("n_sigma", {}),
            wave_flip_wr=float(swing.get("wave_flip_wr") or 0),
            wave_flip_no_wr=float(swing.get("wave_flip_no_wr") or 0),
            wave_flip_edge=float(swing.get("wave_flip_edge") or 0),
            tide_regime_wr=swing.get("tide_regime_wr", {}),
            n_by_tide_regime=swing.get("n_tide", {}),
            drawdown_recovery_avg_bars=float(core.get("drawdown_recovery_avg_bars") or 0),
            thesis_survival_rate=float(core.get("thesis_survival_rate") or 0),
            viable=bool(row.get("viable", False)),
            grade=str(row.get("grade") or "D"),
            geometry_used=geo,
            calibrated_at=str(cal) if cal else None,
        )
