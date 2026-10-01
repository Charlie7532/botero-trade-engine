import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()
P = lambda t, d: print(f"\n{'='*70}\n{t}\n{'='*70}\n{d}")

# A) SPY: ¿único con sector='Broad Market'?
P("A) sector='Broad Market'", pd.read_sql("SELECT ticker, asset_type, sector, industry FROM market.ticker_metadata WHERE UPPER(sector)='BROAD MARKET'", conn).to_string(index=False))

# B) asset_type de SPY/QQQ/AAPL/VIX
P("B) asset_type de referencia", pd.read_sql("SELECT ticker, asset_type, sector, industry, update_source FROM market.ticker_metadata WHERE ticker IN ('SPY','QQQ','AAPL','VIX','TLT','LQD','DBA','UUP') ORDER BY ticker", conn).to_string(index=False))

# C) 59 = asset_type STOCK + industry INDICATOR
P("C) asset_type=STOCK & industry=INDICATOR", pd.read_sql("SELECT COUNT(*) n FROM market.ticker_metadata WHERE UPPER(asset_type)='STOCK' AND UPPER(industry)='INDICATOR'", conn).to_string(index=False))

# D) distribuciones
P("D) asset_type", pd.read_sql("SELECT asset_type, COUNT(*) n FROM market.ticker_metadata GROUP BY 1 ORDER BY 2 DESC", conn).to_string(index=False))
P("D2) industry", pd.read_sql("SELECT industry, COUNT(*) n FROM market.ticker_metadata GROUP BY 1 ORDER BY 2 DESC LIMIT 8", conn).to_string(index=False))

# E) delta universo
qa = """SELECT ticker FROM market.ticker_metadata WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
 AND (sector IS NULL OR UPPER(sector) NOT IN ('INDICATOR','VOLUME BREADTH','CAP-WEIGHTED BREADTH','OPTIONS FLOW','VOLATILITY','SENTIMENT','SHORT INTEREST','VOLUME INTENSITY','QQQ BREADTH','INDEX','YIELDS','BROAD MARKET','CURRENCY','COMMODITIES','FIXED INCOME','FEAR & GREED','BREADTH'))
 AND ticker NOT IN ('VIX','VVIX','CBOE_PCR','FG','S5TH','S5FI','S5TW')"""
qf = """SELECT ticker FROM market.ticker_metadata WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
 AND UPPER(asset_type) IN ('STOCK','ETF') AND ticker NOT LIKE 'UW_%'"""
a=set(pd.read_sql(qa,conn).ticker); f=set(pd.read_sql(qf,conn).ticker)
P("E) universo actual vs fix", f"actual={len(a)} fix={len(f)} entran={sorted(f-a)} salen={sorted(a-f)}")

# F) snapshots: ¿cuántos tickers? ¿incluye indicadores?
P("F) tickers en channel_snapshots", pd.read_sql("SELECT COUNT(DISTINCT ticker) n FROM engine.channel_snapshots", conn).to_string(index=False))
P("F2) ¿hay indicadores en snapshots?", pd.read_sql("""SELECT COUNT(DISTINCT c.ticker) n FROM engine.channel_snapshots c JOIN market.ticker_metadata m ON m.ticker=c.ticker WHERE UPPER(m.industry)='INDICATOR'""", conn).to_string(index=False))

# G) zigzag de los 5 + universo zigzag
P("G) zigzag", pd.read_sql("""SELECT t.ticker, (SELECT COUNT(*) FROM engine.zigzag_points z WHERE z.ticker=t.ticker) zz,
 (SELECT COUNT(*) FROM engine.channel_snapshots c WHERE c.ticker=t.ticker) snaps
 FROM (SELECT unnest(ARRAY['SPY','TLT','LQD','DBA','UUP']) ticker) t""", conn).to_string(index=False))
P("G2) tickers totales en zigzag_points", pd.read_sql("SELECT COUNT(DISTINCT ticker) n FROM engine.zigzag_points", conn).to_string(index=False))
