"""
Script: Ingesta de sustitutos de S&P 500 (VEEV, FERG, RDDT, VMRK)
y saneamiento de index_membership para los delistados (CTRA, EA, AVB, EQR).
"""
import yfinance as yf
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

REPLACEMENTS = {
    "VEEV": {
        "sector": "Healthcare",
        "industry": "Health Information Services",
        "replaces": "CTRA",
    },
    "FERG": {
        "sector": "Industrials",
        "industry": "Industrial Distribution",
        "replaces": "EA",
    },
    "RDDT": {
        "sector": "Communication Services",
        "industry": "Internet Content & Information",
        "replaces": "EQR",
    },
    "VMRK": {
        "sector": "Real Estate",
        "industry": "REIT - Residential",
        "replaces": "AVB",
    },
}

def run():
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        # 1. Backfill e ingesta de los 4 nuevos miembros del S&P 500
        print("=== 1. DESCARGA E INGESTA HISTÓRICA (2 AÑOS) PARA NUEVOS MIEMBROS ===")
        for ticker, meta in REPLACEMENTS.items():
            print(f"Descargando {ticker} (sustituye a {meta['replaces']})...")
            df = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
            if df.empty:
                print(f"  ALERTA: {ticker} no devolvió datos en yfinance")
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(ticker, level=1, axis=1)
            df.columns = [c.lower() for c in df.columns]
            
            # Guardar barras en Vault
            store.save_bars(ticker, "1d", df)
            
            # Registrar metadata como miembro oficial del S&P 500
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO market.ticker_metadata 
                    (ticker, sector, industry, asset_type, index_membership, update_source, updated_at)
                    VALUES (%s, %s, %s, 'STOCK', ARRAY['SP500'], 'vault_ohlcv_bars', NOW())
                    ON CONFLICT (ticker) DO UPDATE
                    SET sector = EXCLUDED.sector,
                        industry = EXCLUDED.industry,
                        asset_type = 'STOCK',
                        index_membership = ARRAY['SP500'],
                        update_source = 'vault_ohlcv_bars',
                        updated_at = NOW();
                """, (ticker, meta["sector"], meta["industry"]))
            conn.commit()
            print(f"  {ticker}: {len(df)} barras guardadas y registrado en S&P 500.")

        # 2. Retirar membresía SP500 y QQQ de los tickers delistados
        print("\n=== 2. SANEAMIENTO DE INDEX_MEMBERSHIP PARA DELISTADOS ===")
        delisted = ["CTRA", "EA", "AVB", "EQR"]
        with conn.cursor() as cur:
            for tk in delisted:
                cur.execute("""
                    UPDATE market.ticker_metadata
                    SET index_membership = array_remove(array_remove(index_membership, 'SP500'), 'QQQ'),
                        update_source = 'none_historical_only',
                        updated_at = NOW()
                    WHERE ticker = %s;
                """, (tk,))
                print(f"  {tk}: membresía de SP500/QQQ removida ({cur.rowcount} fila afectada).")
        conn.commit()
        print("\nTransacción completada exitosamente.")

    finally:
        store._put(conn)
        store.close()

if __name__ == "__main__":
    run()
