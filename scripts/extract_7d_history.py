#!/usr/bin/env python3
"""
7-DAY HISTORY EXTRACTOR (V8)
============================
Downloads the last 7 days of market data and Unusual Whales flow
to freeze an immutable dataset for the Walk-Forward Simulator.
"""
import sys
import os
import json
import time
import logging
from datetime import datetime, timedelta, UTC
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# The Simulation Universe (S&P 500)
def get_sp500_tickers():
    try:
        import requests
        import io
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).text
        tables = pd.read_html(io.StringIO(html))
        df = tables[0]
        tickers = df['Symbol'].tolist()
        # Some tickers have dots (e.g. BRK.B), yfinance uses dashes (BRK-B)
        tickers = [t.replace('.', '-') for t in tickers]
        return tickers
    except Exception as e:
        logger.error(f"Error fetching S&P 500 list: {e}")
        return ["AAPL", "MSFT", "NVDA", "SPY"] # Fallback

UNIVERSE = get_sp500_tickers()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CACHE_FILE = os.path.join(DATA_DIR, "sim_7d_cache.json")

def extract_history():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    bridge = UWDataBridge()
    if not bridge.is_configured():
        logger.error("❌ UW_API_KEY no configurado.")
        return
        
    cache = {
        "prices": {},       # {ticker: {date_str: {Open, High, Low, Close, Volume}}}
        "flow": {},         # {ticker: [flow_alerts]}
        "darkpool": {},     # {ticker: [dp_prints]}
        "macro": {
            "spy_ticks": [],
            "tide": []
        },
        "metadata": {
            "extracted_at": datetime.now(UTC).isoformat(),
            "tickers": UNIVERSE
        }
    }
    
    logger.info("📅 Extrayendo historial de 3 meses + 7 días (yfinance)...")
    for i, ticker in enumerate(UNIVERSE, 1):
        try:
            logger.info(f"   [{i}/{len(UNIVERSE)}] Precio: {ticker}")
            df = yf.download(ticker, period="4mo", interval="1d", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Convirtiendo a diccionario indexado por fecha (str)
            price_dict = {}
            for index, row in df.iterrows():
                # Formato: "YYYY-MM-DD"
                date_str = index.strftime("%Y-%m-%d") if hasattr(index, 'strftime') else str(index)[:10]
                price_dict[date_str] = {
                    "Open": float(row["Open"]),
                    "High": float(row["High"]),
                    "Low": float(row["Low"]),
                    "Close": float(row["Close"]),
                    "Volume": float(row["Volume"]),
                }
            cache["prices"][ticker] = price_dict
            
        except Exception as e:
            logger.error(f"     ❌ Error descargando precio {ticker}: {e}")
            
    # También descargar VIX
    logger.info("   [VIX] Precio: ^VIX")
    vix_df = yf.download('^VIX', period="4mo", interval="1d", progress=False)
    vix_dict = {}
    if not vix_df.empty:
        if isinstance(vix_df.columns, pd.MultiIndex):
            vix_df.columns = vix_df.columns.get_level_values(0)
        for index, row in vix_df.iterrows():
            date_str = index.strftime("%Y-%m-%d") if hasattr(index, 'strftime') else str(index)[:10]
            vix_dict[date_str] = float(row["Close"])
    cache["prices"]["^VIX"] = vix_dict

    logger.info("\n🐋 Extrayendo Macro Flow (Unusual Whales)...")
    cache["macro"]["spy_ticks"] = bridge.fetch_spy_flow()
    time.sleep(1)
    cache["macro"]["tide"] = bridge.fetch_market_tide()
    time.sleep(1)

    logger.info("\n🐋 Extrayendo Options Flow & Dark Pool por Ticker...")
    for i, ticker in enumerate(UNIVERSE, 1):
        logger.info(f"   [{i}/{len(UNIVERSE)}] Flow: {ticker}")
        
        # Rate limit protector: 120 req / min -> 2 req / sec max
        time.sleep(0.6) 
        
        # Flow (max 500 alerts)
        flow = bridge.fetch_flow_alerts(ticker, limit=500)
        cache["flow"][ticker] = flow
        
        time.sleep(0.6)
        
        # Darkpool
        dp = bridge.fetch_darkpool_trades(ticker)
        cache["darkpool"][ticker] = dp
        
    logger.info(f"\n💾 Guardando caché en {CACHE_FILE}...")
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)
        
    logger.info("✅ Extracción completa.")

if __name__ == "__main__":
    import pandas as pd # Ensure pandas is available for MultiIndex check
    extract_history()
