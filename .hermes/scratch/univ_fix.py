import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
conn = TimescaleDataStore()._conn()

q_actual = """
SELECT ticker FROM market.ticker_metadata 
WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
  AND (sector IS NULL OR UPPER(sector) NOT IN (
      'INDICATOR','VOLUME BREADTH','CAP-WEIGHTED BREADTH','OPTIONS FLOW','VOLATILITY','SENTIMENT',
      'SHORT INTEREST','VOLUME INTENSITY','QQQ BREADTH','INDEX','YIELDS','BROAD MARKET','CURRENCY',
      'COMMODITIES','FIXED INCOME','FEAR & GREED','BREADTH'))
  AND ticker NOT IN ('VIX','VVIX','CBOE_PCR','FG','S5TH','S5FI','S5TW')
"""
actual = set(pd.read_sql(q_actual, conn).ticker)

# FIX CORRECTO: industry (campo fiable) + asset_type + sin UW_/pseudo
q_fix = """
SELECT ticker, asset_type, sector, industry FROM market.ticker_metadata
WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
  AND UPPER(asset_type) IN ('STOCK','ETF')
  AND ticker NOT LIKE 'UW_%'
"""
fix_df = pd.read_sql(q_fix, conn)
fix = set(fix_df.ticker)

print(f"ACTUAL: {len(actual)}   |   FIX (industry+asset_type, sin UW_): {len(fix)}")
entran = sorted(fix - actual)
print(f"\n=== ENTRAN ({len(entran)}) ===")
print(", ".join(entran))
if entran:
    print(fix_df[fix_df.ticker.isin(entran)].to_string(index=False))
print(f"\n=== salen: {sorted(actual - fix)} ===")
