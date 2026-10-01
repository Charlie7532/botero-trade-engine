import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()

total = pd.read_sql("SELECT COUNT(*) AS n FROM market.ticker_metadata", conn)
print("TOTAL en ticker_metadata:", int(total.n[0]))

q = """
SELECT ticker FROM market.ticker_metadata 
WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
  AND (sector IS NULL OR UPPER(sector) NOT IN (
      'INDICATOR','VOLUME BREADTH','CAP-WEIGHTED BREADTH','OPTIONS FLOW',
      'VOLATILITY','SENTIMENT','SHORT INTEREST','VOLUME INTENSITY',
      'QQQ BREADTH','INDEX','YIELDS','BROAD MARKET','CURRENCY',
      'COMMODITIES','FIXED INCOME','FEAR & GREED','BREADTH'))
  AND ticker NOT IN ('VIX','VVIX','CBOE_PCR','FG','S5TH','S5FI','S5TW')
"""
f = pd.read_sql(q, conn)
print("FILTRADO (acciones + ETFs):", len(f))
print("  ¿SPY/QQQ incluidos?", [t for t in ['SPY','QQQ'] if t in set(f.ticker)])

ex = pd.read_sql("SELECT ticker, sector FROM market.ticker_metadata WHERE ticker NOT IN (SELECT ticker FROM (" + q + ") x)", conn)
print("\nEXCLUIDOS:", len(ex))
print(ex.head(30).to_string(index=False))
