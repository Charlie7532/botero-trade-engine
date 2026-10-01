import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
c = TimescaleDataStore()._conn()
print("### PASE 2 — VERIFICACIÓN ###")

# B1: tipo de columna obs_vel_svw
print("\n[B1] tipo de columna obs_vel_svw:")
print(pd.read_sql("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='engine' AND table_name='channel_snapshots' AND column_name LIKE 'obs_vel%'", c).to_string(index=False))

# B2: los 6 conteos + los reales
print("\n[B2] conteos:")
def n(q): return pd.read_sql(q, c).iloc[0,0]
print("  channel_snapshots filtro(561?):", n("""SELECT COUNT(DISTINCT tm.ticker) FROM market.ticker_metadata tm JOIN market.ohlcv_bars b ON b.ticker=tm.ticker AND b.timeframe='1d' WHERE tm.asset_type IN ('STOCK','ETF') AND tm.sector NOT IN ('Breadth','Options Flow','Sentiment','Commodities','Fixed Income','Currency','Yields','International','Volatility') AND tm.ticker NOT LIKE 'UW_%%' AND tm.industry NOT IN ('INDICATOR','Breadth Index') AND LENGTH(tm.ticker)<=5"""))
print("  zigzag filtro(520?):", n("""SELECT COUNT(DISTINCT tm.ticker) FROM market.ticker_metadata tm JOIN market.ohlcv_bars b ON b.ticker=tm.ticker AND b.timeframe='1d' WHERE tm.asset_type='STOCK' AND tm.sector NOT IN ('Breadth','Options Flow','Sentiment','Commodities','Fixed Income','Currency','Yields','International','Broad Market','Volatility') AND tm.ticker NOT LIKE 'UW_%%' AND tm.industry NOT IN ('ETF','INDICATOR','Breadth Index','Equity Index') AND LENGTH(tm.ticker)<=5"""))
print("  canónico(567?):", n("""SELECT COUNT(DISTINCT tm.ticker) FROM market.ticker_metadata tm JOIN market.ohlcv_bars b ON b.ticker=tm.ticker AND b.timeframe='1d' WHERE (tm.industry IS NULL OR UPPER(tm.industry)!='INDICATOR') AND UPPER(tm.asset_type) IN ('STOCK','ETF') AND tm.ticker NOT LIKE 'UW_%%'"""))
print("  actual snapshots(562?):", n("SELECT COUNT(DISTINCT ticker) FROM engine.channel_snapshots"))
print("  actual zigzag(539?):", n("SELECT COUNT(DISTINCT ticker) FROM engine.zigzag_points"))
print("  zigzag filtro SIN MIN_BARS vs get_stock_universe():", n("""SELECT COUNT(DISTINCT tm.ticker) FROM market.ticker_metadata tm JOIN market.ohlcv_bars b ON b.ticker=tm.ticker AND b.timeframe='1d' WHERE tm.asset_type='STOCK' AND tm.sector NOT IN ('Breadth','Options Flow','Sentiment','Commodities','Fixed Income','Currency','Yields','International','Broad Market','Volatility') AND tm.ticker NOT LIKE 'UW_%%' AND tm.industry NOT IN ('ETF','INDICATOR','Breadth Index','Equity Index') AND LENGTH(tm.ticker)<=5"""))

# verificar citas de líneas
import pathlib
t = pathlib.Path('backend/scripts/trainers/train_multiscale_kinematic_ev_tree.py').read_text().splitlines()
print("\n[B2] trainer L203-213 contiene 'BROAD MARKET'?:", any('BROAD MARKET' in l for l in t[202:213]))
z = pathlib.Path('backend/scripts/backfills/backfill_zigzag_points.py').read_text().splitlines()
print("[B2] zigzag L110 'def get_stock_universe'?:", 'def get_stock_universe' in z[109])
s = pathlib.Path('backend/scripts/backfills/backfill_channel_snapshots.py').read_text().splitlines()
print("[B2] snapshots L51-65 (asset_type IN STOCK/ETF)?:", any("asset_type IN ('STOCK', 'ETF')" in l for l in s[50:65]))
