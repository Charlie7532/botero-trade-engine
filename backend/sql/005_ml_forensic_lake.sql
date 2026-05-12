-- ==============================================================================
-- Migration: 005_ml_forensic_lake.sql
-- Description: Creates the ML Data Lake for Meta-Labeling forensic storage.
-- It establishes a strict one-to-one relationship between features and labels.
-- ==============================================================================

BEGIN;

-- 1. Create ml_features table (The "X" matrix)
CREATE TABLE IF NOT EXISTS engine.ml_features (
    id UUID PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    signal_name VARCHAR(50) NOT NULL,
    signal_time TIMESTAMPTZ NOT NULL,
    features JSONB NOT NULL,          -- The orthogonal feature array/dict at T=0
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for querying by ticker and time (typical forensic queries)
CREATE INDEX IF NOT EXISTS idx_ml_features_ticker_time 
    ON engine.ml_features (ticker, signal_time);

-- Index for analyzing specific signals
CREATE INDEX IF NOT EXISTS idx_ml_features_signal 
    ON engine.ml_features (signal_name);

-- 2. Create ml_labels table (The "y" vector)
CREATE TABLE IF NOT EXISTS engine.ml_labels (
    feature_id UUID PRIMARY KEY REFERENCES engine.ml_features(id) ON DELETE CASCADE,
    label INTEGER NOT NULL,           -- -1 (Stop Hit), 0 (Time Stop/Scratch), 1 (Profit Hit)
    return_pct NUMERIC(10, 4) NOT NULL,
    bars_held INTEGER NOT NULL,
    exit_time TIMESTAMPTZ NOT NULL,
    geometry_used JSONB NOT NULL,     -- The exact TP/SL/Time limit used to generate this label
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for analyzing label distribution
CREATE INDEX IF NOT EXISTS idx_ml_labels_label 
    ON engine.ml_labels (label);

COMMIT;
