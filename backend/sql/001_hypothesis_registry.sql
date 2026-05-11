-- Hypothesis Registry — Signal Lifecycle Governance
-- =====================================================
-- Schema: engine (separate from market data)
-- 
-- Usage:
--   cd /root/botero-trade
--   PGPASSWORD=$(...) psql $POSTGRES_URL -f backend/sql/001_hypothesis_registry.sql

CREATE SCHEMA IF NOT EXISTS engine;

CREATE TABLE IF NOT EXISTS engine.hypothesis_registry (
    id TEXT PRIMARY KEY,                        -- e.g. "rsi-oversold-long"
    indicator_id TEXT NOT NULL,                 -- e.g. "rsi-cardwell"
    signal_name TEXT NOT NULL,                  -- e.g. "rsi_intelligence"
    department TEXT NOT NULL DEFAULT 'SPECULATIVE',  -- SPECULATIVE | QUALITY
    description TEXT,

    -- Lifecycle
    evidence_status TEXT NOT NULL DEFAULT 'HYPOTHESIS',
        -- CANDIDATE | HYPOTHESIS | VALIDATED | DEGRADED | REPOSTULATED | RETIRED
    reliability_grade TEXT NOT NULL DEFAULT 'D',
        -- A | B | C | D | F

    -- Oracle Alpha Ceiling (Step 1)
    oracle_sharpe FLOAT,
    oracle_win_rate FLOAT,
    oracle_profit_factor FLOAT,
    oracle_n_entries INT,

    -- Walk-Forward (Step 3)
    wf_sharpe FLOAT,
    wf_win_rate FLOAT,

    -- Deflated Sharpe Ratio (Step 5)
    dsr FLOAT,
    dsr_n_trials INT,                          -- Number of trials tested

    -- OOS Confirmation
    oos_sharpe FLOAT,
    oos_p_value FLOAT,

    -- Conjugation
    is_conjugated BOOLEAN DEFAULT FALSE,
    parent_signals TEXT[],                      -- IDs of parent signals if conjugated
    conjugation_improvement_pct FLOAT,          -- % improvement vs best parent

    -- Timestamps
    discovered_at TIMESTAMPTZ DEFAULT NOW(),
    validated_at TIMESTAMPTZ,
    degraded_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,

    -- Full results blob
    validation_log JSONB,
    created_by TEXT DEFAULT 'agent'
);

-- Index for lifecycle queries
CREATE INDEX IF NOT EXISTS idx_hyp_status
    ON engine.hypothesis_registry (evidence_status);
CREATE INDEX IF NOT EXISTS idx_hyp_indicator
    ON engine.hypothesis_registry (indicator_id);
CREATE INDEX IF NOT EXISTS idx_hyp_department
    ON engine.hypothesis_registry (department);
