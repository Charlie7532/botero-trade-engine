"""
Fast Empirical EV Audit for VIX States vs SPY Forward Returns
"""
import pandas as pd
import numpy as np
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()

with store.engine.connect() as conn:
    df_spy = pd.read_sql("SELECT time::date as date, close as spy_close FROM market.ohlcv_bars WHERE ticker='SPY' AND timeframe='1d' ORDER BY time ASC", conn)
    df_vix = pd.read_sql("SELECT time::date as date, close as vix_close FROM market.ohlcv_bars WHERE ticker='VIX' AND timeframe='1d' ORDER BY time ASC", conn)

df = pd.merge(df_spy, df_vix, on='date').sort_values('date')

df['spy_fwd_1d'] = df['spy_close'].pct_change(1).shift(-1)
df['spy_fwd_3d'] = df['spy_close'].pct_change(3).shift(-3)
df['vix_3d_diff'] = df['vix_close'].diff(3)

vix_edges_d1 = [12.74, 15.46, 17.61, 20.50, 25.92]
vix_labels_d1 = ['DEEP_COMPLACENCY', 'LOW_VOL', 'MODERATE_VOL', 'HIGH_VOL', 'ELEVATED_PANIC', 'CRISIS_SPIKE']

def get_d1(val):
    if val < 12.74: return 'DEEP_COMPLACENCY'
    if val < 15.46: return 'LOW_VOL'
    if val < 17.61: return 'MODERATE_VOL'
    if val < 20.50: return 'HIGH_VOL'
    if val < 25.92: return 'ELEVATED_PANIC'
    return 'CRISIS_SPIKE'

vix_edges_d2 = [-1.805, -0.660, 0.490, 1.760]

def get_d2(val):
    if val < -1.805: return 'FAST_CRUSH_3D'
    if val < -0.660: return 'DECELERATING_DOWN_3D'
    if val < 0.490: return 'STABLE_CONTINUATION_3D'
    if val < 1.760: return 'ACCELERATING_UP_3D'
    return 'FAST_SPIKE_3D'

df['d1'] = df['vix_close'].apply(get_d1)
df['d2'] = df['vix_3d_diff'].apply(get_d2)

sub_spike = df[(df['d1'] == 'ELEVATED_PANIC') & (df['d2'] == 'FAST_SPIKE_3D')].dropna()

print("========================================================================================")
print("   VERDAD EMPÍRICA REAL DE MERCADO (NEON VAULT 1990-2026): VIX ELEVATED_PANIC + FAST_SPIKE_3D")
print("========================================================================================")
print(f"Número de Ocasiones Históricas (n)              : {len(sub_spike)}")
print(f"Probabilidad de Alza SPY a 1 día (Win Rate 1d) : {(sub_spike['spy_fwd_1d'] > 0).mean()*100:.1f}%")
print(f"Esperanza Matemática Retorno 1-Día (EV 1d)    : {sub_spike['spy_fwd_1d'].mean()*100:+.2f}%")
print(f"Probabilidad de Alza SPY a 3 días (Win Rate 3d) : {(sub_spike['spy_fwd_3d'] > 0).mean()*100:.1f}%")
print(f"Esperanza Matemática Retorno 3-Días (EV 3d)   : {sub_spike['spy_fwd_3d'].mean()*100:+.2f}%")
