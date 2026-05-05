"""
Execution — PostgreSQL Trade Journal Adapter
===============================================
Infrastructure adapter: all trade journal persistence via PostgreSQL.
Domain code interacts via TradeJournalPort interface.

Each department (QUALITY / SPECULATIVE) receives its own instance
scoped to its own table via the table_name constructor parameter.
"""
import json
import logging
import os
from datetime import datetime, UTC
from typing import Optional
from dataclasses import asdict

import psycopg2
import psycopg2.extras
import psycopg2.pool

from backend.modules.execution.domain.entities.trade_record import TradeJournalEntry
from backend.modules.execution.domain.ports.trade_journal_port import TradeJournalPort

logger = logging.getLogger(__name__)


class PostgresTradeJournalAdapter(TradeJournalPort):
    """
    Trade Journal — PostgreSQL implementation.
    Table names are parameterized for department-scoped instances.
    Implements TradeJournalPort.
    """

    def __init__(
        self,
        dsn: str | None = None,
        pool=None,
        table_name: str = "engine.trade_journal",
        snapshots_table: str = "engine.trade_snapshots",
        patterns_table: str = "engine.trade_patterns",
    ):
        """
        Args:
            dsn: PostgreSQL connection string (POSTGRES_URL).
            pool: Pre-built psycopg2 pool (for tests).
            table_name: Journal table (department-scoped).
            snapshots_table: Snapshots table (department-scoped).
            patterns_table: Patterns table (department-scoped).
        """
        self._table = table_name
        self._snapshots_table = snapshots_table
        self._patterns_table = patterns_table
        if pool is not None:
            self._pool = pool
            self._owns_pool = False
        else:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=3,
                dsn=dsn or os.environ.get("POSTGRES_URL", ""),
            )
            self._owns_pool = True
        logger.info(f"Trade Journal PostgreSQL: connected → {table_name}")

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn):
        self._pool.putconn(conn)

    def close(self):
        if self._owns_pool:
            self._pool.closeall()

    # ═══════════════════════════════════════════════════════════
    # TradeJournalPort Implementation
    # ═══════════════════════════════════════════════════════════

    def open_trade(self, entry: TradeJournalEntry) -> str:
        """Register a new trade entry. Returns trade_id."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""INSERT INTO {self._table} (
                        trade_id, ticker, direction, status, strategy_bucket,
                        created_at, updated_at,
                        entry_thesis, alpha_score, qualifier_grade, qualifier_edge_score,
                        optimal_model, lstm_probability, xgb_probability,
                        rs_vs_spy, rs_vs_sector, insider_signal, insider_detail,
                        earnings_safe, earnings_days, sector_alignment, capitulation_level,
                        entry_price, entry_time, entry_shares, entry_notional,
                        entry_kelly_pct, entry_portfolio_pct, entry_state,
                        entry_order_id, entry_fill_price, entry_slippage,
                        trailing_type, trailing_atr_mult, trailing_fixed_pct,
                        initial_stop_price, current_stop_price,
                        pattern_tags, entry_snapshot, entry_intelligence
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        NOW(), NOW(),
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s
                    )""",
                    (
                        entry.trade_id, entry.ticker, entry.direction,
                        entry.status, entry.strategy_bucket,
                        entry.entry_thesis, entry.alpha_score,
                        entry.qualifier_grade, entry.qualifier_edge_score,
                        entry.optimal_model, entry.lstm_probability, entry.xgb_probability,
                        entry.rs_vs_spy, entry.rs_vs_sector,
                        entry.insider_signal, entry.insider_detail,
                        entry.earnings_safe, entry.earnings_days,
                        entry.sector_alignment, entry.capitulation_level,
                        entry.entry_price, entry.entry_time,
                        entry.entry_shares, entry.entry_notional,
                        entry.entry_kelly_pct, entry.entry_portfolio_pct,
                        entry.entry_state, entry.entry_order_id,
                        entry.entry_fill_price, entry.entry_slippage,
                        entry.trailing_type, entry.trailing_atr_mult,
                        entry.trailing_fixed_pct, entry.initial_stop_price,
                        entry.current_stop_price,
                        entry.pattern_tags or [],
                        json.dumps(entry.entry_snapshot) if entry.entry_snapshot else None,
                        json.dumps(entry.entry_intelligence) if entry.entry_intelligence else None,
                    ),
                )

                # Snapshot as separate row
                if entry.entry_snapshot:
                    cur.execute(
                        f"""INSERT INTO {self._snapshots_table}
                           (trade_id, snapshot_type, timestamp, data)
                           VALUES (%s, 'ENTRY', %s, %s)""",
                        (entry.trade_id, entry.entry_time,
                         json.dumps(entry.entry_snapshot)),
                    )

            conn.commit()
            logger.info(
                f"📝 Journal OPEN: {entry.ticker} @ ${entry.entry_price:.2f}"
                f" — {entry.entry_thesis[:80]}"
            )
            return entry.trade_id
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def close_trade(self, entry: TradeJournalEntry) -> None:
        """Update a trade entry with exit data."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE {self._table} SET
                        status = 'CLOSED', updated_at = NOW(),
                        exit_time = %s, exit_price = %s,
                        exit_order_id = %s, exit_fill_price = %s, exit_slippage = %s,
                        exit_snapshot = %s,
                        pnl_dollars = %s, pnl_pct = %s, pnl_r_multiple = %s,
                        was_winner = %s, exit_reason = %s,
                        what_went_right = %s, what_went_wrong = %s,
                        lesson_learned = %s, grade = %s,
                        pattern_tags = %s,
                        highest_price = %s, lowest_price = %s,
                        max_favorable_excursion_pct = %s,
                        max_adverse_excursion_pct = %s,
                        bars_held = %s,
                        scaling_events = %s, stop_adjustments = %s
                    WHERE trade_id = %s""",
                    (
                        entry.exit_time, entry.exit_price,
                        entry.exit_order_id, entry.exit_fill_price, entry.exit_slippage,
                        json.dumps(entry.exit_snapshot) if entry.exit_snapshot else None,
                        entry.pnl_dollars, entry.pnl_pct, entry.pnl_r_multiple,
                        entry.was_winner, entry.exit_reason,
                        entry.what_went_right, entry.what_went_wrong,
                        entry.lesson_learned, entry.grade,
                        entry.pattern_tags or [],
                        entry.highest_price, entry.lowest_price,
                        entry.max_favorable_excursion_pct,
                        entry.max_adverse_excursion_pct,
                        entry.bars_held,
                        json.dumps(entry.scaling_events or []),
                        json.dumps(entry.stop_adjustments or []),
                        entry.trade_id,
                    ),
                )

                # Exit snapshot
                if entry.exit_snapshot:
                    cur.execute(
                        f"""INSERT INTO {self._snapshots_table}
                           (trade_id, snapshot_type, timestamp, data)
                           VALUES (%s, 'EXIT', %s, %s)""",
                        (entry.trade_id, entry.exit_time,
                         json.dumps(entry.exit_snapshot)),
                    )

                # Pattern tracking
                if entry.pattern_tags:
                    psycopg2.extras.execute_values(
                        cur,
                        f"""INSERT INTO {self._patterns_table}
                           (trade_id, pattern_name, context, outcome, confidence)
                           VALUES %s""",
                        [
                            (
                                entry.trade_id,
                                tag,
                                entry.entry_thesis,
                                "WIN" if entry.was_winner else "LOSS",
                                abs(entry.pnl_r_multiple),
                            )
                            for tag in entry.pattern_tags
                        ],
                    )

            conn.commit()
            emoji = "✅" if entry.was_winner else "❌"
            logger.info(
                f"{emoji} Journal CLOSE: {entry.ticker} "
                f"PnL: {entry.pnl_pct:+.2f}% (${entry.pnl_dollars:+,.0f}) "
                f"R: {entry.pnl_r_multiple:+.2f} "
                f"Reason: {entry.exit_reason} Grade: {entry.grade}"
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def update_trade(self, trade_id: str, fields: dict) -> None:
        """Partial update of trade fields (e.g. thesis_death_flag)."""
        if not fields:
            return
        conn = self._conn()
        try:
            set_clause = ", ".join(f"{k} = %s" for k in fields)
            values = list(fields.values()) + [trade_id]
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {self._table} SET {set_clause}, updated_at = NOW() WHERE trade_id = %s",
                    values,
                )
            conn.commit()
            logger.info(f"📝 Journal UPDATE: {trade_id} → {list(fields.keys())}")
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def get_open_trades(self) -> list[dict]:
        """Return all currently open trades."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT trade_id, ticker, entry_price, entry_time,
                              alpha_score, qualifier_grade, strategy_bucket
                       FROM {self._table}
                       WHERE status = 'OPEN'
                       ORDER BY created_at DESC"""
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            self._put(conn)

    def get_trade_full_data(self, trade_id: str) -> Optional[dict]:
        """Return the complete record for a trade by ID."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT * FROM {self._table} WHERE trade_id = %s""",
                    (trade_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
        finally:
            self._put(conn)

    def get_performance_summary(self) -> dict:
        """Return performance summary of all closed trades."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT
                        COUNT(*)                                    AS total,
                        COUNT(*) FILTER (WHERE was_winner)          AS wins,
                        COUNT(*) FILTER (WHERE NOT was_winner)      AS losses,
                        COALESCE(AVG(pnl_pct) FILTER (WHERE was_winner), 0)       AS avg_win,
                        COALESCE(AVG(pnl_pct) FILTER (WHERE NOT was_winner), 0)   AS avg_loss,
                        COALESCE(SUM(pnl_dollars), 0)               AS total_pnl,
                        COALESCE(SUM(pnl_dollars) FILTER (WHERE was_winner), 0)   AS gross_profit,
                        COALESCE(SUM(pnl_dollars) FILTER (WHERE NOT was_winner), 0) AS gross_loss
                    FROM {self._table}
                    WHERE status = 'CLOSED'"""
                )
                row = cur.fetchone()
                total, wins, losses, avg_win, avg_loss, total_pnl, gross_profit, gross_loss = row

                if total == 0:
                    return {"total_trades": 0, "message": "Sin trades cerrados"}

                return {
                    "total_trades": total,
                    "winners": wins,
                    "losers": losses,
                    "win_rate": (wins / total * 100) if total > 0 else 0,
                    "avg_win_pct": float(avg_win),
                    "avg_loss_pct": float(avg_loss),
                    "total_pnl": float(total_pnl),
                    "profit_factor": abs(gross_profit / gross_loss) if gross_loss != 0 else 0,
                }
        finally:
            self._put(conn)

    def get_pattern_stats(self) -> list[dict]:
        """Return pattern statistics for learning."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT
                        pattern_name,
                        COUNT(*)                                AS total,
                        COUNT(*) FILTER (WHERE outcome = 'WIN') AS wins,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE outcome = 'WIN')
                              / NULLIF(COUNT(*), 0), 1)         AS win_rate,
                        ROUND(AVG(confidence)::numeric, 2)      AS avg_r
                    FROM {self._patterns_table}
                    GROUP BY pattern_name
                    ORDER BY total DESC"""
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            self._put(conn)

    def get_exit_reason_stats(self) -> list[dict]:
        """Return statistics grouped by exit reason."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT
                        exit_reason,
                        COUNT(*)                                    AS total,
                        COUNT(*) FILTER (WHERE was_winner)          AS wins,
                        ROUND(100.0 * COUNT(*) FILTER (WHERE was_winner)
                              / NULLIF(COUNT(*), 0), 1)             AS win_rate,
                        ROUND(AVG(pnl_pct)::numeric, 2)             AS avg_pnl,
                        ROUND(AVG(pnl_r_multiple)::numeric, 2)      AS avg_r
                    FROM {self._table}
                    WHERE status = 'CLOSED'
                      AND exit_reason IS NOT NULL
                      AND exit_reason != ''
                    GROUP BY exit_reason
                    ORDER BY total DESC"""
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            self._put(conn)

    def find_similar_trades(self, vector: list[float], limit: int = 5) -> list[dict]:
        """Find historically similar trades via pgvector cosine similarity."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        f"""SELECT trade_id, ticker, status, was_winner,
                                  exit_reason, pnl_pct, grade, lesson_learned,
                                  1 - (entry_vector <=> %s::vector) AS score
                           FROM {self._table}
                           WHERE entry_vector IS NOT NULL
                           ORDER BY entry_vector <=> %s::vector
                           LIMIT %s""",
                        (vector, vector, limit),
                    )
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, row)) for row in cur.fetchall()]
                except Exception as e:
                    logger.warning(f"Vector search not available: {e}")
                    return []
        finally:
            self._put(conn)
