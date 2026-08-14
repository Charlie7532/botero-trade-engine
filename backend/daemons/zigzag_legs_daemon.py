"""
Daemon de Generación y Mantenimiento Factual de Tramos de ZigZag en Neon Vault
=============================================================================
Almacena DATOS PUROS Y DUROS de tramos ZigZag CONFIRMADOS ('CONFIRMED')
en la base de datos PostgreSQL (Neon Vault) para TODOS los ~700+ Tickers 
de Acciones y ETFs con barras OHLCV reales.

Esquema Simplificado (Hechos Físicos Puros):
  - ticker, scale, leg_id
  - start_timestamp, start_type, start_price  (Pivote Origen)
  - end_timestamp, end_type, end_price        (Pivote Destino)
  - confirmed_at_timestamp                     (Sello Temporal Causal)
  - status                                     ('CONFIRMED')

Garantía Única de Verdad:
  - Restricted por CONSTRAINT uq_zigzag_leg UNIQUE (ticker, scale, start_timestamp, end_timestamp)
  - Cero duplicados en Neon Vault.
"""

import sys
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ZigZagLegsDaemon")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market.zigzag_legs (
    ticker                  VARCHAR(20) NOT NULL,
    scale                   VARCHAR(10) NOT NULL,
    leg_id                  SERIAL PRIMARY KEY,
    
    start_timestamp         TIMESTAMPTZ NOT NULL,
    start_type              VARCHAR(4)  NOT NULL,
    start_price             NUMERIC     NOT NULL,
    
    end_timestamp           TIMESTAMPTZ NOT NULL,
    end_type                VARCHAR(4)  NOT NULL,
    end_price               NUMERIC     NOT NULL,
    
    confirmed_at_timestamp  TIMESTAMPTZ NOT NULL,
    status                  VARCHAR(15) NOT NULL DEFAULT 'CONFIRMED',
    
    prev_leg_return         NUMERIC,
    prev_leg_duration       INTEGER,
    
    CONSTRAINT uq_zigzag_leg UNIQUE (ticker, scale, start_timestamp, end_timestamp)
);

CREATE INDEX IF NOT EXISTS idx_zigzag_legs_causal 
ON market.zigzag_legs (ticker, scale, confirmed_at_timestamp);
"""

SCALES = [
    ("zz25", 0.025),
    ("zz50", 0.050),
    ("zz75", 0.075),
]


def ensure_schema(store: TimescaleDataStore):
    conn = store._conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        logger.info("✅ Tabla market.zigzag_legs (Simplificada Pura) verificada/creada en Neon Vault.")
    finally:
        store._put(conn)


def compute_confirmed_legs_for_ticker_scale(
    ticker: str,
    dates,
    opens,
    highs,
    lows,
    closes,
    scale_name: str,
    thres: float,
) -> list:
    n = len(dates)
    if n < 10:
        return []

    legs = []
    mode = 0  # 0 = init, +1 = searching High, -1 = searching Low
    
    extreme_price = None
    extreme_idx = None
    
    start_type = None
    start_price = None
    start_idx = None

    for i in range(n):
        c_high = float(highs[i])
        c_low = float(lows[i])
        c_close = float(closes[i])

        if mode == 0:
            extreme_price = c_close
            extreme_idx = i
            start_price = c_close
            start_idx = i
            mode = 1
            start_type = "MIN"
            continue

        if mode == 1:  # Moving UP (building peak High)
            if c_high > extreme_price:
                extreme_price = c_high
                extreme_idx = i

            # Check if price dropped by thres from peak High
            if c_low <= extreme_price * (1.0 - thres):
                end_price = extreme_price
                end_idx = extreme_idx
                end_type = "MAX"

                legs.append({
                    "ticker": ticker,
                    "scale": scale_name,
                    "start_timestamp": dates[start_idx],
                    "start_type": start_type,
                    "start_price": round(float(start_price), 4),
                    "end_timestamp": dates[end_idx],
                    "end_type": end_type,
                    "end_price": round(float(end_price), 4),
                    "confirmed_at_timestamp": dates[i],
                    "status": "CONFIRMED",
                })

                mode = -1
                start_type = "MAX"
                start_price = end_price
                start_idx = end_idx
                extreme_price = c_low
                extreme_idx = i

        elif mode == -1:  # Moving DOWN (building valley Low)
            if c_low < extreme_price:
                extreme_price = c_low
                extreme_idx = i

            # Check if price rose by thres from valley Low
            if c_high >= extreme_price * (1.0 + thres):
                end_price = extreme_price
                end_idx = extreme_idx
                end_type = "MIN"

                legs.append({
                    "ticker": ticker,
                    "scale": scale_name,
                    "start_timestamp": dates[start_idx],
                    "start_type": start_type,
                    "start_price": round(float(start_price), 4),
                    "end_timestamp": dates[end_idx],
                    "end_type": end_type,
                    "end_price": round(float(end_price), 4),
                    "confirmed_at_timestamp": dates[i],
                    "status": "CONFIRMED",
                })

                mode = 1
                start_type = "MIN"
                start_price = end_price
                start_idx = end_idx
                extreme_price = c_high
                extreme_idx = i

    return legs


def sync_ticker_zigzag_legs(store: TimescaleDataStore, ticker: str, rebuild: bool = False):
    bars = store.load_bars(ticker, "1d")
    if bars is None or len(bars) < 15:
        return 0

    bars = bars.sort_index()
    dates = bars.index
    opens = bars["open"].values
    highs = bars["high"].values
    lows = bars["low"].values
    closes = bars["close"].values

    all_legs = []
    for scale_name, thres in SCALES:
        legs = compute_confirmed_legs_for_ticker_scale(
            ticker, dates, opens, highs, lows, closes, scale_name, thres
        )
        all_legs.extend(legs)

    if not all_legs:
        return 0

    conn = store._conn()
    try:
        with conn.cursor() as cursor:
            if rebuild:
                cursor.execute("DELETE FROM market.zigzag_legs WHERE ticker = %s", (ticker,))

            insert_query = """
                INSERT INTO market.zigzag_legs (
                    ticker, scale, start_timestamp, start_type, start_price,
                    end_timestamp, end_type, end_price, confirmed_at_timestamp, status
                ) VALUES %s
                ON CONFLICT (ticker, scale, start_timestamp, end_timestamp) DO UPDATE SET
                    start_type = EXCLUDED.start_type,
                    start_price = EXCLUDED.start_price,
                    end_type = EXCLUDED.end_type,
                    end_price = EXCLUDED.end_price,
                    confirmed_at_timestamp = EXCLUDED.confirmed_at_timestamp,
                    status = EXCLUDED.status;
            """
            
            tuples_to_insert = [
                (
                    leg["ticker"],
                    leg["scale"],
                    leg["start_timestamp"],
                    leg["start_type"],
                    leg["start_price"],
                    leg["end_timestamp"],
                    leg["end_type"],
                    leg["end_price"],
                    leg["confirmed_at_timestamp"],
                    leg["status"],
                )
                for leg in all_legs
            ]

            psycopg2.extras.execute_values(cursor, insert_query, tuples_to_insert, page_size=1000)

            # Post-insert: populate prev_leg_return and prev_leg_duration
            for scale_name, _ in SCALES:
                cursor.execute("""
                    WITH ordered AS (
                        SELECT leg_id, start_price, end_price,
                               GREATEST((end_timestamp - start_timestamp), INTERVAL '1 day') AS dur,
                               LAG(start_price) OVER (ORDER BY start_timestamp) AS prev_start_px,
                               LAG(end_price) OVER (ORDER BY start_timestamp) AS prev_end_px,
                               LAG(GREATEST((end_timestamp - start_timestamp), INTERVAL '1 day'))
                                   OVER (ORDER BY start_timestamp) AS prev_dur
                        FROM market.zigzag_legs
                        WHERE ticker = %s AND scale = %s
                    )
                    UPDATE market.zigzag_legs z
                    SET prev_leg_return = (o.prev_end_px / o.prev_start_px) - 1.0,
                        prev_leg_duration = EXTRACT(DAY FROM o.prev_dur)::INTEGER
                    FROM ordered o
                    WHERE z.leg_id = o.leg_id AND o.prev_start_px IS NOT NULL;
                """, [ticker, scale_name])

        conn.commit()
        return len(all_legs)
    finally:
        store._put(conn)


def run_full_sync(tickers: list = None, rebuild: bool = True):
    store = TimescaleDataStore()
    ensure_schema(store)

    if tickers is None:
        conn = store._conn()
        try:
            with conn.cursor() as cursor:
                # Select ALL tickers from metadata EXCEPT pure macro indicators
                cursor.execute("""
                    SELECT DISTINCT ticker 
                    FROM market.ticker_metadata 
                    WHERE industry IS NULL OR industry NOT IN ('INDICATOR', 'Market Internals', 'Currency Index', 'Options Sentiment')
                """)
                rows = cursor.fetchall()
                tickers = [r[0] for r in rows]
        finally:
            store._put(conn)

    total_inserted = 0
    for idx, t in enumerate(tickers):
        try:
            n_legs = sync_ticker_zigzag_legs(store, t, rebuild=rebuild)
            total_inserted += n_legs
            if (idx + 1) % 50 == 0 or idx == len(tickers) - 1:
                logger.info(f"[{idx+1}/{len(tickers)}] Ticker {t:<6s}: {n_legs} tramos insertados. Total acumulado: {total_inserted:,}")
        except Exception as e:
            logger.error(f"❌ Error al procesar ZigZag para {t}: {e}")

    logger.info(f"🎉 Sincronización completada. Total tramos procesados para {len(tickers)} tickers: {total_inserted:,}")
    store.close()


if __name__ == "__main__":
    run_full_sync()
