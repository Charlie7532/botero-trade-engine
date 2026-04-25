"""
Generador de Data Store Histórico en formato Parquet
=====================================================
Descarga datos históricos (2020-2025) masivos mediante yfinance,
los limpia y los persiste en formato Parquet para uso del 
Walk-Forward Backtester.

¿Por qué Parquet?
- 10x más rápido de cargar que CSV
- 75% más compacto
- Preserva tipos de datos automáticamente (Fechas, Floats)
"""

import os
import sys
import logging
import asyncio
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, UTC
from tqdm import tqdm

# Añadir el root del proyecto al PYTHONPATH para poder importar backend
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.infrastructure.data_providers.sector_flow import SectorFlowEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = root_dir / "data" / "historical"


def setup_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 Directorio de datos: {DATA_DIR}")


def get_target_etfs():
    """Obtiene la lista consolidada de ETFs desde la matriz central."""
    sf = SectorFlowEngine()
    
    # Construimos un diccionario master
    master = {}
    if hasattr(sf, 'MARKET_ETFS'):
        for name, ticker in sf.MARKET_ETFS.items(): master[ticker] = 'Market'
    for name, ticker in sf.SECTOR_ETFS.items(): master[ticker] = 'Domestic'
    if hasattr(sf, 'INTERNATIONAL_ETFS'):
        for name, ticker in sf.INTERNATIONAL_ETFS.items(): master[ticker] = 'International'
    if hasattr(sf, 'COMMODITY_ETFS'):
        for name, ticker in sf.COMMODITY_ETFS.items(): master[ticker] = 'Commodity'
        
    master['^VIX'] = 'Macro'
    return master


def download_batch(tickers: list, start_date: str, end_date: str) -> dict:
    """Descarga de lote en paralelo usando yfinance auto-threading."""
    logger.info(f"⏳ Descargando {len(tickers)} tickers ({start_date} a {end_date})...")
    
    # auto_adjust=True significa que el Open/High/Low/Close ya tienen splits y dividendos aplicados.
    data = yf.download(
        tickers, 
        start=start_date, 
        end=end_date,
        interval='1d', 
        group_by='ticker',
        auto_adjust=True,
        progress=False,
    )
    return data


def format_to_parquet(data: pd.DataFrame, ticker_metadata: dict, output_name: str):
    """
    Formatea el multi-index DataFrame de yfinance en una estructura
    tidy y guárdalo como Parquet.
    """
    records = []
    
    # Procesar data frame
    if hasattr(data.columns, 'levels'):
        tickers = data.columns.levels[0]
        for ticker in tqdm(tickers, desc="Data Formatting"):
            df_t = data[ticker].dropna(how='all')
            if df_t.empty: continue
                
            df_t = df_t.reset_index()
            # Asegurarnos de que el nombre de la fecha sea Date
            if 'index' in df_t.columns: df_t.rename(columns={'index': 'Date'}, inplace=True)
            if 'Datetime' in df_t.columns: df_t.rename(columns={'Datetime': 'Date'}, inplace=True)
                
            for _, row in df_t.iterrows():
                # Evitar registros sin volumen (feriados raros) o datos corruptos
                if pd.isna(row['Close']): continue
                    
                records.append({
                    'Date': pd.to_datetime(row['Date']).date(),
                    'Ticker': ticker,
                    'Universe': ticker_metadata.get(ticker, 'Unknown'),
                    'Open': float(row['Open']) if not pd.isna(row['Open']) else float(row['Close']),
                    'High': float(row['High']) if not pd.isna(row['High']) else float(row['Close']),
                    'Low': float(row['Low']) if not pd.isna(row['Low']) else float(row['Close']),
                    'Close': float(row['Close']),
                    'Volume': float(row['Volume']) if 'Volume' in row and not pd.isna(row['Volume']) else 0.0,
                })
    else:
        # Single ticker case
        pass 
        
    if not records:
        logger.warning("No se pudieron extraer registros.")
        return
        
    df_clean = pd.DataFrame(records)
    
    # Convertir 'Date' a tipo datetime pandas para orden topológico rápido
    df_clean['Date'] = pd.to_datetime(df_clean['Date'])
    df_clean = df_clean.sort_values(by=['Date', 'Ticker']).reset_index(drop=True)
    
    output_path = DATA_DIR / f"{output_name}.parquet"
    
    # Guardar a Parquet
    df_clean.to_parquet(
        output_path, 
        engine='pyarrow', 
        compression='snappy',
        index=False
    )
    
    # Estadísticas
    mb_size = output_path.stat().st_size / (1024*1024)
    logger.info(f"✅ Guardado en {output_name}.parquet | {len(df_clean):,} filas | {mb_size:.1f} MB")
    
    # Reportar el rango disponible
    min_date = df_clean['Date'].min()
    max_date = df_clean['Date'].max()
    logger.info(f"   Rango temporal: {min_date.date()} — {max_date.date()}")


def main():
    setup_directories()
    
    # 1. Definir Marco Temporal
    START_DATE = "2020-01-01"
    END_DATE = "2026-01-01"  # Para atrapar todo 2025
    
    # 2. Market & Sectors Data
    logger.info(f"\n{'='*50}\n1. EXTRAYENDO DATA MARCO (ETFs + VIX)\n{'='*50}")
    etfs = get_target_etfs()
    tickers = list(etfs.keys())
    
    data = download_batch(tickers, START_DATE, END_DATE)
    format_to_parquet(data, etfs, "market_context_5y")
    
    # Opcional (se puede escalar después): Bajar todo el S&P 500
    # Por ahora, con los ETFs podemos validar el Macro-Contexto del Backtest.
    # El Walk-Forward engine leerá estos archivos nativamente.

if __name__ == '__main__':
    main()
