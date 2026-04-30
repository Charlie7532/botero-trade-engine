-- ═══════════════════════════════════════════════════════════
-- Trade Journal Migration: MongoDB → PostgreSQL
-- ═══════════════════════════════════════════════════════════
-- Run against the same Postgres/Neon instance used by the engine.
-- Uses the existing 'engine' schema.
-- ═══════════════════════════════════════════════════════════

-- 1. Main trades table
CREATE TABLE IF NOT EXISTS engine.trade_journal (
    id              SERIAL PRIMARY KEY,
    trade_id        TEXT NOT NULL UNIQUE,
    ticker          TEXT NOT NULL,
    direction       TEXT NOT NULL DEFAULT 'LONG',
    status          TEXT NOT NULL DEFAULT 'OPEN',       -- OPEN, CLOSED, CANCELLED
    strategy_bucket TEXT NOT NULL DEFAULT 'CORE',       -- CORE, TACTICAL
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- PRE-TRADE
    entry_thesis            TEXT DEFAULT '',
    alpha_score             REAL DEFAULT 0,
    qualifier_grade         TEXT DEFAULT '',
    qualifier_edge_score    REAL DEFAULT 0,
    optimal_model           TEXT DEFAULT '',
    lstm_probability        REAL DEFAULT 0,
    xgb_probability         REAL DEFAULT 0,
    rs_vs_spy               REAL DEFAULT 0,
    rs_vs_sector            REAL DEFAULT 0,
    insider_signal          TEXT DEFAULT '',
    insider_detail          TEXT DEFAULT '',
    earnings_safe           BOOLEAN DEFAULT TRUE,
    earnings_days           INT DEFAULT -1,
    sector_alignment        TEXT DEFAULT '',
    capitulation_level      INT DEFAULT 0,

    -- EXECUTION
    entry_price             REAL DEFAULT 0,
    entry_time              TEXT DEFAULT '',
    entry_shares            REAL DEFAULT 0,
    entry_notional          REAL DEFAULT 0,
    entry_kelly_pct         REAL DEFAULT 0,
    entry_portfolio_pct     REAL DEFAULT 0,
    entry_state             TEXT DEFAULT 'PROBING',
    entry_order_id          TEXT DEFAULT '',
    entry_fill_price        REAL DEFAULT 0,
    entry_slippage          REAL DEFAULT 0,

    -- STOP
    trailing_type           TEXT DEFAULT 'adaptive',
    trailing_atr_mult       REAL DEFAULT 3.0,
    trailing_fixed_pct      REAL DEFAULT 0.10,
    initial_stop_price      REAL DEFAULT 0,
    current_stop_price      REAL DEFAULT 0,

    -- EVOLUTION
    highest_price                   REAL DEFAULT 0,
    lowest_price                    REAL DEFAULT 0,
    max_favorable_excursion_pct     REAL DEFAULT 0,
    max_adverse_excursion_pct       REAL DEFAULT 0,
    bars_held                       INT DEFAULT 0,
    scaling_events                  JSONB DEFAULT '[]'::JSONB,
    stop_adjustments                JSONB DEFAULT '[]'::JSONB,

    -- EXIT
    exit_price          REAL DEFAULT 0,
    exit_time           TEXT DEFAULT '',
    exit_reason         TEXT DEFAULT '',
    exit_order_id       TEXT DEFAULT '',
    exit_fill_price     REAL DEFAULT 0,
    exit_slippage       REAL DEFAULT 0,

    -- RESULTS
    pnl_dollars         REAL DEFAULT 0,
    pnl_pct             REAL DEFAULT 0,
    pnl_r_multiple      REAL DEFAULT 0,
    was_winner          BOOLEAN DEFAULT FALSE,

    -- ANALYSIS
    what_went_right     TEXT DEFAULT '',
    what_went_wrong     TEXT DEFAULT '',
    lesson_learned      TEXT DEFAULT '',
    pattern_tags        TEXT[] DEFAULT '{}',
    grade               TEXT DEFAULT '',

    -- SNAPSHOTS (JSONB — replaces separate collections)
    entry_snapshot      JSONB,
    exit_snapshot        JSONB,
    entry_intelligence  JSONB,

    -- VECTOR (for pgvector similarity search)
    entry_vector        vector(32)
);

-- 2. Indexes matching the MongoDB originals
CREATE INDEX IF NOT EXISTS idx_tj_ticker_status ON engine.trade_journal (ticker, status);
CREATE INDEX IF NOT EXISTS idx_tj_created_at    ON engine.trade_journal (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tj_exit_reason   ON engine.trade_journal (exit_reason, was_winner);
CREATE INDEX IF NOT EXISTS idx_tj_status        ON engine.trade_journal (status);

-- 3. Trade snapshots (separate table for entry/exit market snapshots)
CREATE TABLE IF NOT EXISTS engine.trade_snapshots (
    id              SERIAL PRIMARY KEY,
    trade_id        TEXT NOT NULL REFERENCES engine.trade_journal(trade_id),
    snapshot_type   TEXT NOT NULL,   -- ENTRY, EXIT
    timestamp       TEXT,
    data            JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ts_trade_id ON engine.trade_snapshots (trade_id, snapshot_type);

-- 4. Pattern tracking (for learning from past trades)
CREATE TABLE IF NOT EXISTS engine.trade_patterns (
    id              SERIAL PRIMARY KEY,
    trade_id        TEXT NOT NULL REFERENCES engine.trade_journal(trade_id),
    pattern_name    TEXT NOT NULL,
    context         TEXT DEFAULT '',
    outcome         TEXT DEFAULT '',   -- WIN, LOSS
    confidence      REAL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tp_trade_id ON engine.trade_patterns (trade_id);
CREATE INDEX IF NOT EXISTS idx_tp_pattern  ON engine.trade_patterns (pattern_name);

-- 5. Enable pgvector extension (if not already enabled)
-- Note: On Neon, run: CREATE EXTENSION IF NOT EXISTS vector;
-- The entry_vector column uses vector(32) for cosine similarity search.
