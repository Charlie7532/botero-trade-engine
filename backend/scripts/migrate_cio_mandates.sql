-- Migración: CIO Daily Mandates
-- Crea la tabla para almacenar las decisiones diarias de Ray Dalio (CIO)
-- Porcentajes almacenados como fracciones decimales (0.80 = 80%)

CREATE TABLE IF NOT EXISTS engine.daily_mandates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mandate_date DATE NOT NULL UNIQUE,
    quality_budget_pct NUMERIC(5, 4) NOT NULL,
    speculative_budget_pct NUMERIC(5, 4) NOT NULL,
    regime VARCHAR(50) NOT NULL,
    vetoed_sectors TEXT[],
    focus_sectors TEXT[],
    reasoning TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_quality_pct CHECK (quality_budget_pct BETWEEN 0 AND 1),
    CONSTRAINT chk_speculative_pct CHECK (speculative_budget_pct BETWEEN 0 AND 1),
    CONSTRAINT chk_budget_sum CHECK (quality_budget_pct + speculative_budget_pct <= 1.0001)
);

-- Index for quick lookups by date
CREATE INDEX IF NOT EXISTS idx_daily_mandates_date ON engine.daily_mandates(mandate_date);
