"""
Backfill Histórico + Incremental de S5V (Volume Breadth) al Vault
==================================================================
IDEMPOTENTE: Detecta la última fecha SV5 existente y computa solo lo nuevo.
INCREMENTAL: Puede ejecutarse diariamente sin duplicar data.
SAFETY: ON CONFLICT DO NOTHING en los inserts.

Genera indicadores SV5_TH / SV5_FI / SV5_TW por sector y mercado.

Modo de uso:
  # Backfill completo (primera vez — detecta que no hay data y genera todo)
  python backend/scripts/backfill_sv5_historical.py

  # Actualización incremental (detecta última fecha y genera solo lo nuevo)
  python backend/scripts/backfill_sv5_historical.py

  # Forzar rango específico
  python backend/scripts/backfill_sv5_historical.py --from 2024-01-01

Indicadores generados: 36 series
  - 11 sectores × 3 escalas (SV5_{ETF}_{TH|FI|TW})
  - 3 mercado agregado (SV5TH, SV5FI, SV5TW)
"""
import sys, os, time, logging, argparse, bisect
sys.path.append('/root/botero-trade')
os.chdir('/root/botero-trade')
from dotenv import load_dotenv
load_dotenv('.env')

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    SECTOR_VOLUME_BREADTH_TICKERS,
    VOLUME_BREADTH_MA_CONFIG,
    canonicalize,
)

# ── CLI args ──
parser = argparse.ArgumentParser(description="Backfill SV5 Volume Breadth indicators")
parser.add_argument("--from", dest="from_date", default=None,
                    help="Force start date (YYYY-MM-DD). Default: auto-detect from vault.")
args = parser.parse_args()

conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
cur = conn.cursor()

# ═══════════════════════════════════════════════════════════════
# FASE 0: Detectar qué ya existe en el Vault (incremental)
# ═══════════════════════════════════════════════════════════════
cur.execute("""
    SELECT MAX(time)::date FROM market.ohlcv_bars
    WHERE ticker LIKE 'SV5%' AND timeframe = '1d'
""")
row = cur.fetchone()
last_sv5_date = row[0] if row and row[0] else None

if args.from_date:
    compute_from = pd.Timestamp(args.from_date)
    logger.info(f"FASE 0: Forzando inicio desde {compute_from.strftime('%Y-%m-%d')} (--from)")
elif last_sv5_date:
    compute_from = pd.Timestamp(last_sv5_date) + pd.Timedelta(days=1)
    logger.info(f"FASE 0: Última SV5 en vault: {last_sv5_date}. Computando desde {compute_from.strftime('%Y-%m-%d')}")
else:
    compute_from = pd.Timestamp("1999-10-01")
    logger.info(f"FASE 0: No hay SV5 en vault. BACKFILL COMPLETO desde {compute_from.strftime('%Y-%m-%d')}")

# ═══════════════════════════════════════════════════════════════
# FASE 1: Cargar data de volumen en memoria
# ═══════════════════════════════════════════════════════════════
# Necesitamos 250 días de historia ANTES de compute_from para las MAs
load_from = compute_from - pd.Timedelta(days=400)  # 400 cal days ≈ 280 trading days

logger.info(f"FASE 1: Cargando volúmenes SP500 desde {load_from.strftime('%Y-%m-%d')}...")
t0 = time.time()

cur.execute("""
    SELECT b.ticker, m.sector, b.time::date, b.volume
    FROM market.ohlcv_bars b
    JOIN market.ticker_metadata m ON b.ticker = m.ticker
    WHERE b.timeframe = '1d'
      AND m.asset_type = 'STOCK'
      AND 'SP500' = ANY(m.index_membership)
      AND m.sector IS NOT NULL
      AND b.volume > 0
      AND b.time >= %s
    ORDER BY b.ticker, b.time
""", (load_from,))
raw_rows = cur.fetchall()
logger.info(f"  Cargadas {len(raw_rows):,} filas en {time.time()-t0:.1f}s")

if not raw_rows:
    logger.info("  No hay filas de volumen. Abortando.")
    conn.close()
    sys.exit(0)

# Construir estructuras en memoria
ticker_sector = {}
vol_data = {}  # {ticker: {date: volume}}

for ticker, sector, dt, volume in raw_rows:
    ticker_sector[ticker] = sector
    if ticker not in vol_data:
        vol_data[ticker] = {}
    vol_data[ticker][pd.Timestamp(dt)] = float(volume)

n_tickers = len(vol_data)
logger.info(f"  {n_tickers} tickers, {len(set(ticker_sector.values()))} sectores")

# Sector → [tickers]
sector_tickers = defaultdict(list)
for t, s in ticker_sector.items():
    sector_tickers[s].append(t)

# Sector name → ETF
_SECTOR_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}

# Pre-sort dates per ticker for binary search
ticker_sorted_dates = {t: sorted(vol_data[t].keys()) for t in vol_data}

# ═══════════════════════════════════════════════════════════════
# FASE 2: Obtener días de trading a computar
# ═══════════════════════════════════════════════════════════════
cur.execute("""
    SELECT DISTINCT time::date FROM market.ohlcv_bars
    WHERE ticker = 'SPY' AND timeframe = '1d' AND time >= %s
    ORDER BY time
""", (compute_from,))
trading_days = [pd.Timestamp(r[0]) for r in cur.fetchall()]

if not trading_days:
    logger.info("FASE 2: No hay días nuevos por computar. Vault ya está actualizado. ✅")
    conn.close()
    sys.exit(0)

logger.info(f"FASE 2: {len(trading_days)} días por computar ({trading_days[0].strftime('%Y-%m-%d')} → {trading_days[-1].strftime('%Y-%m-%d')})")

# ═══════════════════════════════════════════════════════════════
# FASE 3: Computar SV5 día por día
# ═══════════════════════════════════════════════════════════════
logger.info("FASE 3: Computando SV5 indicators...")

def _sma(data, length):
    if len(data) < length:
        return None
    return float(np.mean(data[-length:]))

def _ema(data, span):
    if len(data) < span:
        return None
    alpha = 2.0 / (span + 1)
    ema_val = float(np.mean(data[:span]))
    for val in data[span:]:
        ema_val = alpha * val + (1 - alpha) * ema_val
    return ema_val

def compute_vb(ticker_vols, fast_len, slow_len, fast_type):
    """Compute volume breadth % for a set of tickers."""
    above = 0
    total = 0
    for vols in ticker_vols.values():
        if len(vols) < slow_len:
            continue
        fast_fn = _ema if fast_type == "ema" else _sma
        fast_val = fast_fn(vols, fast_len)
        slow_val = _sma(vols, slow_len)
        if fast_val is not None and slow_val is not None and slow_val > 0:
            total += 1
            if fast_val > slow_val:
                above += 1
    if total == 0:
        return None
    return round(above / total * 100, 1)

SCALE_TO_TICKER = {"tactical": "SV5TW", "intermediate": "SV5FI", "structural": "SV5TH"}

# Batch insert buffer
insert_buffer = []
BATCH_SIZE = 500

def flush_buffer():
    global insert_buffer
    if not insert_buffer:
        return
    execute_values(cur, """
        INSERT INTO market.ohlcv_bars (time, ticker, timeframe, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (ticker, timeframe, time) DO NOTHING
    """, insert_buffer)
    conn.commit()
    insert_buffer = []

def add_bar(date, ticker, value, n_constituents):
    global insert_buffer
    ts = pd.Timestamp(date).normalize()
    insert_buffer.append((ts, ticker, '1d', value, value, value, value, n_constituents))
    if len(insert_buffer) >= BATCH_SIZE:
        flush_buffer()

total_days = len(trading_days)
bars_written = 0
t_start = time.time()

for progress, d in enumerate(trading_days):
    if progress % 250 == 0:
        elapsed = time.time() - t_start
        rate = progress / elapsed if elapsed > 0 else 0
        remaining = (total_days - progress) / rate if rate > 0 else 0
        logger.info(
            f"  Día {progress}/{total_days} ({d.strftime('%Y-%m-%d')}) | "
            f"{bars_written:,} bars | {rate:.1f} días/s | ETA: {remaining/60:.0f}min"
        )
    
    market_vols = {}  # For aggregate SV5TH/FI/TW
    
    for sector_name, tickers_in_sector in sector_tickers.items():
        sector_canon = canonicalize(sector_name)
        etf = _SECTOR_TO_ETF.get(sector_canon)
        if not etf or etf not in SECTOR_VOLUME_BREADTH_TICKERS:
            continue
        
        # Collect last 250 trading days of volume for each ticker in sector
        sector_vols = {}
        for t in tickers_in_sector:
            if t not in vol_data:
                continue
            all_dates = ticker_sorted_dates[t]
            idx_end = bisect.bisect_right(all_dates, d)
            if idx_end == 0:
                continue
            start = max(0, idx_end - 250)
            date_slice = all_dates[start:idx_end]
            vols = [vol_data[t][dt] for dt in date_slice]
            if len(vols) >= 20:
                sector_vols[t] = vols
                market_vols[t] = vols
        
        if len(sector_vols) < 5:
            continue
        
        # Compute 3 scales for this sector
        tickers_map = SECTOR_VOLUME_BREADTH_TICKERS[etf]
        for scale_key, indicator_ticker in tickers_map.items():
            config = VOLUME_BREADTH_MA_CONFIG[scale_key]
            vb = compute_vb(sector_vols, config["fast"], config["slow"], config["fast_type"])
            if vb is not None:
                add_bar(d, indicator_ticker, vb, len(sector_vols))
                bars_written += 1
    
    # Compute market aggregate SV5TH, SV5FI, SV5TW
    if len(market_vols) >= 50:
        for scale_key, config in VOLUME_BREADTH_MA_CONFIG.items():
            vb = compute_vb(market_vols, config["fast"], config["slow"], config["fast_type"])
            if vb is not None:
                add_bar(d, SCALE_TO_TICKER[scale_key], vb, len(market_vols))
                bars_written += 1

# Flush remaining
flush_buffer()

elapsed_total = time.time() - t_start
logger.info(f"\n{'='*80}")
logger.info(f"✅ BACKFILL COMPLETADO")
logger.info(f"   Barras escritas: {bars_written:,}")
logger.info(f"   Tiempo total: {elapsed_total/60:.1f} minutos")
logger.info(f"   Rango: {trading_days[0].strftime('%Y-%m-%d')} → {trading_days[-1].strftime('%Y-%m-%d')}")
logger.info(f"{'='*80}")

# ═══════════════════════════════════════════════════════════════
# FASE 4: Verificación post-backfill
# ═══════════════════════════════════════════════════════════════
cur.execute("""
    SELECT ticker, COUNT(*), MIN(time)::date, MAX(time)::date
    FROM market.ohlcv_bars
    WHERE ticker LIKE 'SV5%' AND timeframe = '1d'
    GROUP BY ticker
    ORDER BY ticker
""")
print("\n📊 Verificación post-backfill:")
print(f"  {'Ticker':20s} | {'Bars':8s} | {'Desde':12s} | {'Hasta':12s}")
print("  " + "-"*55)
for r in cur.fetchall():
    print(f"  {r[0]:20s} | {r[1]:8d} | {r[2]} | {r[3]}")

conn.close()
