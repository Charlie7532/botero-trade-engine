-- ============================================================
-- Migration 004: Split Trade Journal by Department
-- ============================================================
-- Each department (QUALITY / SPECULATIVE) gets its own tables.
-- "Cada lorito en su palito."
-- ============================================================

BEGIN;

-- 1. Department-specific journal tables
CREATE TABLE IF NOT EXISTS engine.trade_journal_quality (LIKE engine.trade_journal INCLUDING ALL);
CREATE TABLE IF NOT EXISTS engine.trade_journal_speculative (LIKE engine.trade_journal INCLUDING ALL);

-- 2. Quality-specific columns (not in original schema)
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS moat_type VARCHAR(64);
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS thesis_alive BOOLEAN DEFAULT TRUE;
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS thesis_death_flag BOOLEAN DEFAULT FALSE;
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS thesis_death_reason TEXT;
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS entry_roic NUMERIC;
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS entry_operating_margin NUMERIC;
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS entry_gf_value NUMERIC;
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS irr NUMERIC;
ALTER TABLE engine.trade_journal_quality ADD COLUMN IF NOT EXISTS dividends_collected NUMERIC DEFAULT 0;

-- 3. Migrate existing data by strategy_bucket
INSERT INTO engine.trade_journal_quality
  SELECT * FROM engine.trade_journal WHERE strategy_bucket = 'QUALITY'
  ON CONFLICT DO NOTHING;
INSERT INTO engine.trade_journal_speculative
  SELECT * FROM engine.trade_journal WHERE strategy_bucket IN ('SPECULATIVE', 'UNCLASSIFIED')
  ON CONFLICT DO NOTHING;

-- 4. Snapshot tables
CREATE TABLE IF NOT EXISTS engine.trade_snapshots_quality (LIKE engine.trade_snapshots INCLUDING ALL);
CREATE TABLE IF NOT EXISTS engine.trade_snapshots_speculative (LIKE engine.trade_snapshots INCLUDING ALL);

INSERT INTO engine.trade_snapshots_quality
  SELECT s.* FROM engine.trade_snapshots s
  JOIN engine.trade_journal j ON s.trade_id = j.trade_id
  WHERE j.strategy_bucket = 'QUALITY'
  ON CONFLICT DO NOTHING;
INSERT INTO engine.trade_snapshots_speculative
  SELECT s.* FROM engine.trade_snapshots s
  JOIN engine.trade_journal j ON s.trade_id = j.trade_id
  WHERE j.strategy_bucket IN ('SPECULATIVE', 'UNCLASSIFIED')
  ON CONFLICT DO NOTHING;

-- 5. Pattern tables
CREATE TABLE IF NOT EXISTS engine.trade_patterns_quality (LIKE engine.trade_patterns INCLUDING ALL);
CREATE TABLE IF NOT EXISTS engine.trade_patterns_speculative (LIKE engine.trade_patterns INCLUDING ALL);

INSERT INTO engine.trade_patterns_speculative
  SELECT * FROM engine.trade_patterns
  ON CONFLICT DO NOTHING;

-- 6. Instrument Blacklist (4Q THESIS_DEATH guard)
CREATE TABLE IF NOT EXISTS engine.instrument_blacklist (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(16) NOT NULL,
    department VARCHAR(16) NOT NULL,
    reason TEXT,
    blacklisted_at TIMESTAMPTZ DEFAULT NOW(),
    blacklisted_until TIMESTAMPTZ NOT NULL,
    created_by VARCHAR(64) DEFAULT 'surveillance_loop'
);
CREATE INDEX IF NOT EXISTS idx_blacklist_lookup
  ON engine.instrument_blacklist(ticker, department, blacklisted_until);

-- 7. Rename originals as backup (do NOT drop)
ALTER TABLE engine.trade_journal RENAME TO trade_journal_legacy;
ALTER TABLE engine.trade_snapshots RENAME TO trade_snapshots_legacy;
ALTER TABLE engine.trade_patterns RENAME TO trade_patterns_legacy;

COMMIT;
