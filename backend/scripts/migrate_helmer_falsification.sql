-- Migration: Helmer Protocol Falsification System
-- Adds tables for Investment Theses and Thesis Checkpoints (Neon PostgreSQL)

CREATE TABLE IF NOT EXISTS portfolio_investment_theses (
    ticker VARCHAR(10) PRIMARY KEY,
    author VARCHAR(50) NOT NULL,
    thesis_status VARCHAR(20) NOT NULL, -- ACTIVE, INVALIDATED, ARCHIVED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_thesis_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) REFERENCES portfolio_investment_theses(ticker) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    threshold_value NUMERIC(15, 4) NOT NULL,
    current_value NUMERIC(15, 4),
    is_breached BOOLEAN DEFAULT FALSE,
    breach_date TIMESTAMP WITH TIME ZONE,
    evidence_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for quick lookups by ticker
CREATE INDEX idx_checkpoints_ticker ON portfolio_thesis_checkpoints(ticker);
