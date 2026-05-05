-- ═══════════════════════════════════════════════════════════
-- Taxonomy Migration: CORE/TACTICAL → QUALITY/SPECULATIVE
-- ═══════════════════════════════════════════════════════════
-- Run AFTER deploying code changes.
-- Safe to run multiple times (idempotent).
-- ═══════════════════════════════════════════════════════════

-- 1. Rename existing bucket values
UPDATE engine.trade_journal SET strategy_bucket = 'QUALITY' WHERE strategy_bucket = 'CORE';
UPDATE engine.trade_journal SET strategy_bucket = 'SPECULATIVE' WHERE strategy_bucket = 'TACTICAL';

-- 2. Add sector column (if not exists)
ALTER TABLE engine.trade_journal ADD COLUMN IF NOT EXISTS sector TEXT DEFAULT 'UNKNOWN';

-- 3. Update default constraint on strategy_bucket
ALTER TABLE engine.trade_journal ALTER COLUMN strategy_bucket SET DEFAULT 'QUALITY';
