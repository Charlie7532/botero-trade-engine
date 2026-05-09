"""
Watchlist Persistence — Neon PostgreSQL Adapter
=================================================
Infrastructure adapter for persisting and querying watchlist candidates.
Reads/writes to market.quality_watchlist and market.speculative_watchlist.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from backend.modules.portfolio_management.domain.entities.watchlist_entities import (
    QualityWatchlistCandidate,
    SpeculativeWatchlistCandidate,
)

logger = logging.getLogger(__name__)


class WatchlistStore:
    """Neon PostgreSQL adapter for watchlist persistence."""

    def __init__(self, dsn: str = ""):
        self._dsn = dsn or os.getenv("POSTGRES_URL", "")

    def _conn(self):
        return psycopg2.connect(self._dsn)

    # ── Quality Watchlist ─────────────────────────────────

    def upsert_quality(self, c: QualityWatchlistCandidate) -> None:
        """Insert or update a quality watchlist candidate."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO market.quality_watchlist (
                        ticker, company, sector, gf_score, piotroski_f_score,
                        altman_z_score, price_to_gf_value, gf_valuation,
                        rank_profitability, rank_growth, rank_financial_strength,
                        roic, roe, net_margin, debt_to_equity,
                        thesis, conviction_score, moat_classification,
                        current_price, buy_zone_low, buy_zone_high, fair_value,
                        status, alerts, last_updated, last_screened
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (ticker, department) DO UPDATE SET
                        company = EXCLUDED.company,
                        sector = EXCLUDED.sector,
                        gf_score = EXCLUDED.gf_score,
                        piotroski_f_score = EXCLUDED.piotroski_f_score,
                        altman_z_score = EXCLUDED.altman_z_score,
                        price_to_gf_value = EXCLUDED.price_to_gf_value,
                        gf_valuation = EXCLUDED.gf_valuation,
                        rank_profitability = EXCLUDED.rank_profitability,
                        rank_growth = EXCLUDED.rank_growth,
                        rank_financial_strength = EXCLUDED.rank_financial_strength,
                        roic = EXCLUDED.roic,
                        roe = EXCLUDED.roe,
                        net_margin = EXCLUDED.net_margin,
                        debt_to_equity = EXCLUDED.debt_to_equity,
                        conviction_score = EXCLUDED.conviction_score,
                        moat_classification = EXCLUDED.moat_classification,
                        current_price = EXCLUDED.current_price,
                        buy_zone_low = EXCLUDED.buy_zone_low,
                        buy_zone_high = EXCLUDED.buy_zone_high,
                        fair_value = EXCLUDED.fair_value,
                        status = EXCLUDED.status,
                        alerts = EXCLUDED.alerts,
                        last_updated = EXCLUDED.last_updated,
                        last_screened = EXCLUDED.last_screened
                """, (
                    c.ticker, c.company, c.sector, c.gf_score, c.piotroski_f_score,
                    c.altman_z_score, c.price_to_gf_value, c.gf_valuation,
                    c.rank_profitability, c.rank_growth, c.rank_financial_strength,
                    c.roic, c.roe, c.net_margin, c.debt_to_equity,
                    c.thesis, c.conviction_score, c.moat_classification,
                    c.current_price, c.buy_zone_low, c.buy_zone_high, c.fair_value,
                    c.status, json.dumps(c.alerts),
                    datetime.now(timezone.utc), datetime.now(timezone.utc),
                ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Quality watchlist upsert failed for {c.ticker}: {e}")
            raise
        finally:
            conn.close()

    def load_quality_watchlist(self, status: str = None) -> list[QualityWatchlistCandidate]:
        """Load quality watchlist, optionally filtered by status."""
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM market.quality_watchlist WHERE status = %s ORDER BY conviction_score DESC",
                        (status,),
                    )
                else:
                    cur.execute("SELECT * FROM market.quality_watchlist ORDER BY conviction_score DESC")

                candidates = []
                for row in cur.fetchall():
                    candidates.append(QualityWatchlistCandidate(
                        ticker=row["ticker"],
                        company=row["company"],
                        sector=row["sector"],
                        gf_score=row["gf_score"] or 0,
                        piotroski_f_score=row["piotroski_f_score"] or 0,
                        altman_z_score=row["altman_z_score"] or 0,
                        price_to_gf_value=row["price_to_gf_value"] or 0,
                        gf_valuation=row["gf_valuation"] or "",
                        rank_profitability=row["rank_profitability"] or 0,
                        rank_growth=row["rank_growth"] or 0,
                        rank_financial_strength=row["rank_financial_strength"] or 0,
                        roic=row["roic"] or 0,
                        roe=row["roe"] or 0,
                        net_margin=row["net_margin"] or 0,
                        debt_to_equity=row["debt_to_equity"] or 0,
                        thesis=row["thesis"] or "",
                        conviction_score=row["conviction_score"] or 0,
                        moat_classification=row["moat_classification"] or "",
                        current_price=row["current_price"] or 0,
                        buy_zone_low=row["buy_zone_low"] or 0,
                        buy_zone_high=row["buy_zone_high"] or 0,
                        fair_value=row["fair_value"] or 0,
                        status=row["status"] or "WATCHING",
                        alerts=row["alerts"] if isinstance(row["alerts"], list) else [],
                        added_at=row["added_at"],
                        last_updated=row["last_updated"],
                    ))
                return candidates
        finally:
            conn.close()

    def get_quality_count(self) -> int:
        """Get total number of quality watchlist entries."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM market.quality_watchlist")
                return cur.fetchone()[0]
        finally:
            conn.close()

    # ── Speculative Watchlist ─────────────────────────────

    def upsert_speculative(self, c: SpeculativeWatchlistCandidate) -> None:
        """Insert or update a speculative watchlist candidate."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO market.speculative_watchlist (
                        ticker, setup_type, catalyst, timeframe,
                        entry_price, stop_loss, target_price, risk_reward_ratio,
                        gex_regime, sweep_detected, dark_pool_signal,
                        conviction_score, status, alerts, expires_at, last_updated
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, department, setup_type) DO UPDATE SET
                        catalyst = EXCLUDED.catalyst,
                        entry_price = EXCLUDED.entry_price,
                        stop_loss = EXCLUDED.stop_loss,
                        target_price = EXCLUDED.target_price,
                        risk_reward_ratio = EXCLUDED.risk_reward_ratio,
                        gex_regime = EXCLUDED.gex_regime,
                        sweep_detected = EXCLUDED.sweep_detected,
                        dark_pool_signal = EXCLUDED.dark_pool_signal,
                        conviction_score = EXCLUDED.conviction_score,
                        status = EXCLUDED.status,
                        alerts = EXCLUDED.alerts,
                        last_updated = EXCLUDED.last_updated
                """, (
                    c.ticker, c.setup_type, c.catalyst, c.timeframe,
                    c.entry_price, c.stop_loss, c.target_price, c.risk_reward_ratio,
                    c.gex_regime, c.sweep_detected, c.dark_pool_signal,
                    c.conviction_score, c.status, json.dumps(c.alerts),
                    c.expires_at, datetime.now(timezone.utc),
                ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Speculative watchlist upsert failed for {c.ticker}: {e}")
            raise
        finally:
            conn.close()
