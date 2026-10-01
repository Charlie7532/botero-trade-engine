import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()

# Universo ACTUAL (filtro por sector, como los trainers)
q_actual = """
SELECT ticker FROM market.ticker_metadata 
WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
  AND (sector IS NULL OR UPPER(sector) NOT IN (
      'INDICATOR','VOLUME BREADTH','CAP-WEIGHTED BREADTH','OPTIONS FLOW',
      'VOLATILITY','SENTIMENT','SHORT INTEREST','VOLUME INTENSITY',
      'QQQ BREADTH','INDEX','YIELDS','BROAD MARKET','CURRENCY',
      'COMMODITIES','FIXED INCOME','FEAR & GREED','BREADTH'))
  AND ticker NOT IN ('VIX','VVIX','CBOE_PCR','FG','S5TH','S5FI','S5TW')
"""
actual = set(pd.read_sql(q_actual, conn).ticker)

# Universo PROPUESTO (por asset_type: STOCK + ETF)
q_prop = "SELECT ticker, asset_type FROM market.ticker_metadata WHERE UPPER(asset_type) IN ('STOCK','ETF')"
prop_df = pd.read_sql(q_prop, conn)
prop = set(prop_df.ticker)

print(f"ACTUAL (filtro sector):    {len(actual)}")
print(f"PROPUESTO (asset_type):    {len(prop)}")

entran = sorted(prop - actual)
salen = sorted(actual - prop)
print(f"\n=== ENTRAN con el cambio ({len(entran)}) ===")
print(", ".join(entran))

print(f"\n=== SALDRÍAN (en actual, no en propuesto) ({len(salen)}) ===")
print(", ".join(salen))

# Detalle de los que entran
if entran:
    d = pd.read_sql("SELECT ticker, asset_type, sector, industry FROM market.ticker_metadata WHERE ticker IN (" + ",".join(f"'{t}'" for t in entran) + ") ORDER BY asset_type, ticker", conn)
    print("\n=== detalle de los que ENTRAN ===")
    print(d.to_string(index=False))
