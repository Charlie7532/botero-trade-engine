-- ═══════════════════════════════════════════════════════════════
-- Botero Trade — TimescaleDB Bootstrap
-- ═══════════════════════════════════════════════════════════════
-- Creates schemas 'market' and 'engine' alongside Payload's 'payload' schema.
-- Run once: psql $POSTGRES_URL -f backend/scripts/bootstrap_timescale.sql
-- ═══════════════════════════════════════════════════════════════

-- Verify TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ── Schema: market (time-series, Python-owned) ──────────────

CREATE SCHEMA IF NOT EXISTS market;

-- OHLCV Bars — the core hypertable
CREATE TABLE IF NOT EXISTS market.ohlcv_bars (
    time        TIMESTAMPTZ      NOT NULL,
    ticker      TEXT             NOT NULL,
    timeframe   TEXT             NOT NULL DEFAULT '1d',
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      BIGINT           NOT NULL,
    vwap        DOUBLE PRECISION,
    trade_count INT
);

SELECT create_hypertable('market.ohlcv_bars', 'time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_time
    ON market.ohlcv_bars (ticker, time DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ohlcv_dedup
    ON market.ohlcv_bars (ticker, timeframe, time);

-- NOTE: Compression and continuous aggregates require TimescaleDB Community
-- (commercial) license. Under Apache license, use time_bucket() queries instead.
-- Uncomment these if you upgrade to TimescaleDB Community Edition.
--
-- ALTER TABLE market.ohlcv_bars SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'ticker,timeframe',
--     timescaledb.compress_orderby = 'time DESC'
-- );
-- SELECT add_compression_policy('market.ohlcv_bars', INTERVAL '7 days',
--     if_not_exists => TRUE);
--
-- CREATE MATERIALIZED VIEW IF NOT EXISTS market.ohlcv_weekly
-- WITH (timescaledb.continuous) AS
-- SELECT
--     time_bucket('1 week', time) AS bucket,
--     ticker,
--     first(open, time)  AS open,
--     max(high)          AS high,
--     min(low)           AS low,
--     last(close, time)  AS close,
--     sum(volume)        AS volume
-- FROM market.ohlcv_bars
-- WHERE timeframe = '1d'
-- GROUP BY bucket, ticker;

-- Alternative: Weekly candles via simple query (works on Apache license):
-- SELECT time_bucket('1 week', time) AS bucket, ticker,
--        first(open, time) AS open, max(high) AS high,
--        min(low) AS low, last(close, time) AS close, sum(volume) AS volume
-- FROM market.ohlcv_bars WHERE timeframe = '1d'
-- GROUP BY bucket, ticker ORDER BY bucket;

-- Macro Data (VIX, yields, breadth indicators)
CREATE TABLE IF NOT EXISTS market.macro_data (
    time  TIMESTAMPTZ      NOT NULL,
    name  TEXT             NOT NULL,
    value DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('market.macro_data', 'time',
    chunk_time_interval => INTERVAL '3 months',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_macro_name_time
    ON market.macro_data (name, time DESC);

-- MCP Snapshots (flow alerts, QGARP, darkpool — immutable JSONB)
CREATE TABLE IF NOT EXISTS market.mcp_snapshots (
    time     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category TEXT        NOT NULL,
    ticker   TEXT        NOT NULL,
    data     JSONB       NOT NULL
);

SELECT create_hypertable('market.mcp_snapshots', 'time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Compression (requires TimescaleDB Community license):
-- ALTER TABLE market.mcp_snapshots SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'category,ticker',
--     timescaledb.compress_orderby = 'time DESC'
-- );
-- SELECT add_compression_policy('market.mcp_snapshots', INTERVAL '3 days',
--     if_not_exists => TRUE);


-- ── Schema: engine (analytics, Python-owned) ────────────────

CREATE SCHEMA IF NOT EXISTS engine;

CREATE TABLE IF NOT EXISTS engine.backtest_results (
    id            SERIAL PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    period_start  DATE,
    period_end    DATE,
    sharpe_ratio  DOUBLE PRECISION,
    max_drawdown  DOUBLE PRECISION,
    win_rate      DOUBLE PRECISION,
    total_trades  INT,
    result_json   JSONB,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS engine.harmonized_features (
    time        TIMESTAMPTZ NOT NULL,
    ticker      TEXT        NOT NULL,
    feature_set TEXT        NOT NULL,
    features    JSONB       NOT NULL
);

SELECT create_hypertable('engine.harmonized_features', 'time',
    chunk_time_interval => INTERVAL '3 months',
    if_not_exists => TRUE
);

-- ═══════════════════════════════════════════════════════════════
-- Verification queries (uncomment to check):
-- SELECT hypertable_schema, hypertable_name FROM timescaledb_information.hypertables;
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('market','engine');
-- ═══════════════════════════════════════════════════════════════
