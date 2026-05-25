-- ============================================================
-- 006_regime_states.sql — Stateful-First Architecture
-- ============================================================
-- Persists regime/phase/state transitions with temporal context.
--
-- Evidence: FG-H07 duration effect (WR 59.5% → 86.4%) validates
-- that time-in-state matters for decision quality.
--
-- Writers: Daemons (market_health_provider), backfill scripts.
-- Readers: Gates (SwingGate, QualityEntryGate, SpeculativeEntryHub),
--          Risk managers, Oracle Trainer (get_as_of).
-- ============================================================

CREATE TABLE IF NOT EXISTS market.regime_states (
    id             SERIAL PRIMARY KEY,
    key            TEXT NOT NULL,            -- "vol:quality:MARKET", "cascade:MARKET", etc.
    current_state  TEXT NOT NULL,            -- "ELEVATED", "CRISIS", "STRIKE", etc.
    previous_state TEXT,                     -- NULL on first-ever state for a key
    entered_at     TIMESTAMPTZ NOT NULL,     -- When this state began
    closed_at      TIMESTAMPTZ,             -- NULL if currently active
    duration_bars  INT NOT NULL DEFAULT 1,   -- Pre-computed, daemon-incremented daily
    trigger_event  TEXT,                     -- Human-readable: "VIX_ZSCORE=2.3"
    metadata       JSONB,                   -- Extensible context (sensor values, etc.)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary query: get_current — find active state for a key (closed_at IS NULL)
-- Partial index: only indexes active (non-closed) rows. Very small, very fast.
CREATE INDEX IF NOT EXISTS idx_regime_states_active
    ON market.regime_states (key)
    WHERE closed_at IS NULL;

-- Historical query: get_as_of — find state that was active at a specific date
-- Used by Oracle Trainer and trade-forensics for backtest ground truth.
CREATE INDEX IF NOT EXISTS idx_regime_states_history
    ON market.regime_states (key, entered_at DESC, closed_at DESC NULLS FIRST);

-- Range query: load_history — all transitions for a key in a date range
-- Used by forensic loop and backfill verification.
CREATE INDEX IF NOT EXISTS idx_regime_states_key_range
    ON market.regime_states (key, entered_at);
