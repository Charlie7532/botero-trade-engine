#!/usr/bin/env python3
"""
Auditoría de Zigzag Kinematics — Cascade Rates, Contradicciones, Decay, Structural Momentum
=============================================================================================
SPY-only, consulta directa a la DB (market.zigzag_legs).
"""
import os, re
os.chdir('/root/botero-trade')
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#'):
            m = re.match(r'([^=]+)=(.*)', line)
            if m:
                k, v = m.group(1), m.group(2).strip('"').strip("'")
                os.environ[k] = v

import psycopg2
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, spearmanr, mannwhitneyu

conn = psycopg2.connect(os.environ['POSTGRES_URL'])

def q(sql):
    return pd.read_sql(sql, conn)

TICKER = 'SPY'

print("="*90)
print(f"AUDITORÍA ZIGZAG KINEMATICS — {TICKER}")
print("="*90)

# Load all SPY legs
legs = q(f"""
    SELECT ticker, scale, start_timestamp, start_type, 
           end_timestamp, end_type,
           prev_leg_return, prev_leg_duration
    FROM market.zigzag_legs
    WHERE ticker = '{TICKER}' AND status = 'CONFIRMED'
    ORDER BY scale, start_timestamp
""")

z25 = legs[legs['scale']=='zz25'].copy()
z50 = legs[legs['scale']=='zz50'].copy()
z75 = legs[legs['scale']=='zz75'].copy()

z25['start_dt'] = pd.to_datetime(z25['start_timestamp'])
z50['start_dt'] = pd.to_datetime(z50['start_timestamp'])
z75['start_dt'] = pd.to_datetime(z75['start_timestamp'])

print(f"  zz25: N={len(z25)}  {z25['start_dt'].min().date()} → {z25['start_dt'].max().date()}")
print(f"  zz50: N={len(z50)}  {z50['start_dt'].min().date()} → {z50['start_dt'].max().date()}")
print(f"  zz75: N={len(z75)}  {z75['start_dt'].min().date()} → {z75['start_dt'].max().date()}")

# ==========================================================================
# 1. CASCADE RATES (SPY, ±3 días, same type)
# ==========================================================================
print("\n" + "="*90)
print("1. CASCADE RATES REALES (DB, ±3 días, mismo ticker + mismo type)")
print("="*90)

z50_dates_ns = pd.to_datetime(z50['start_dt']).values.astype('datetime64[ns]')
z50_types = z50['start_type'].values
z75_dates_ns = pd.to_datetime(z75['start_dt']).values.astype('datetime64[ns]')
z75_types = z75['start_type'].values

# zz25→zz50
c50 = []
for _, r in z25.iterrows():
    s_dt = np.datetime64(r['start_dt'])
    d = np.abs(z50_dates_ns - s_dt)
    m = (d <= np.timedelta64(3, 'D')) & (z50_types == r['start_type'])
    c50.append(int(m.any()))
z25['c_50'] = c50

# zz25→zz75
c75 = []
for _, r in z25.iterrows():
    s_dt = np.datetime64(r['start_dt'])
    d = np.abs(z75_dates_ns - s_dt)
    m = (d <= np.timedelta64(3, 'D')) & (z75_types == r['start_type'])
    c75.append(int(m.any()))
z25['c_75'] = c75

# zz50→zz75
c50to75 = []
for _, r in z50.iterrows():
    s_dt = np.datetime64(r['start_dt'])
    d = np.abs(z75_dates_ns - s_dt)
    m = (d <= np.timedelta64(3, 'D')) & (z75_types == r['start_type'])
    c50to75.append(int(m.any()))
z50['c_50to75'] = c50to75

r25_50 = z25['c_50'].mean()
r25_75 = z25['c_75'].mean()
r50_75 = z50['c_50to75'].mean()

print(f"\n  ── Global Rates ──")
print(f"  zz25→zz50:  {r25_50:.4f} ({r25_50*100:.2f}%)  N={len(z25)}  n_cascade={z25['c_50'].sum()}")
print(f"  zz25→zz75:  {r25_75:.4f} ({r25_75*100:.2f}%)  N={len(z25)}  n_cascade={z25['c_75'].sum()}")
print(f"  zz50→zz75:  {r50_75:.4f} ({r50_75*100:.2f}%)  N={len(z50)}  n_cascade={z50['c_50to75'].sum()}")

# Por tipo
print(f"\n  ── Por Tipo ──")
for typ in ['MIN', 'MAX']:
    s25 = z25[z25['start_type']==typ]
    s50 = z50[z50['start_type']==typ]
    if len(s25)>0 and len(s50)>0:
        print(f"  {typ}: zz25→zz50={s25['c_50'].mean():.4f} (N={len(s25)})  "
              f"zz25→zz75={s25['c_75'].mean():.4f} (N={len(s25)})  "
              f"zz50→zz75={s50['c_50to75'].mean():.4f} (N={len(s50)})")

# Por década
print(f"\n  ── Por Década ──")
z25['decade'] = (z25['start_dt'].dt.year // 10) * 10
z50['decade'] = (z50['start_dt'].dt.year // 10) * 10
for d in sorted(z25['decade'].unique()):
    d25 = z25[z25['decade']==d]
    d50 = z50[z50['decade']==d]
    r1 = d25['c_50'].mean() if len(d25)>0 else 0
    r2 = d25['c_75'].mean() if len(d25)>0 else 0
    r3 = d50['c_50to75'].mean() if len(d50)>0 else 0
    print(f"  {int(d)}s: zz25→zz50={r1:.4f} (N={len(d25):3d})  zz25→zz75={r2:.4f} (N={len(d25):3d})  zz50→zz75={r3:.4f} (N={len(d50):3d})")

# Chi² test decade variability
decades_w_data = [d for d in sorted(z25['decade'].unique()) if len(z25[z25['decade']==d])>=10]
if len(decades_w_data)>=2:
    cont = []
    for d in decades_w_data:
        sub = z25[z25['decade']==d]
        cont.append([sub['c_50'].sum(), len(sub)-sub['c_50'].sum()])
    cont = np.array(cont)
    chi2, p_dec, dof, _ = chi2_contingency(cont)
    print(f"\n  Chi² (zz25→zz50 por década): χ²={chi2:.3f}, p={p_dec:.4f}, dof={dof}")
    print(f"  {'⚠️ SIGNIFICATIVO: la tasa VARÍA por década' if p_dec<0.05 else '✓ No significativo: tasa estable'}")

# ==========================================================================
# 2. CONTRADICCIONES DE SIGNO
# ==========================================================================
print("\n" + "="*90)
print("2. CONTRADICCIONES DE SIGNO ENTRE ESCALAS")
print("="*90)

def count_contradictions(src, tgt_dates_ns, tgt_types, label):
    contras = []
    for _, r in src.iterrows():
        s_dt = np.datetime64(r['start_dt'])
        d = np.abs(tgt_dates_ns - s_dt)
        near = d <= np.timedelta64(3, 'D')
        if near.any() and (tgt_types[near] != r['start_type']).any():
            contras.append(r['start_dt'])
    print(f"  {label}: {len(contras)}/{len(src)} ({len(contras)/len(src)*100:.1f}%)")
    return contras

c_25v50 = count_contradictions(z25, z50_dates_ns, z50_types, 'zz25 vs zz50')
c_25v75 = count_contradictions(z25, z75_dates_ns, z75_types, 'zz25 vs zz75')
c_50v75 = count_contradictions(z50, z75_dates_ns, z75_types, 'zz50 vs zz75')

# Impact: cascades que tienen contradicción en escala superior
contra_25_set = set(c_25v75)
cascade_and_contra = sum(1 for _, r in z25.iterrows() if r['c_50']==1 and r['start_dt'] in contra_25_set)
print(f"\n  Piernas zz25 que cascadean a zz50 Y tienen contradicción zz75: {cascade_and_contra}")
print(f"  % del total de cascades: {cascade_and_contra/z25['c_50'].sum()*100:.1f}%" if z25['c_50'].sum()>0 else "  N/A")

# ==========================================================================
# 3. AGOTAMIENTO (DECAY)
# ==========================================================================
print("\n" + "="*90)
print("3. AGOTAMIENTO — Cascade vs Duración del Leg")
print("="*90)

z25['leg_dur'] = (pd.to_datetime(z25['end_timestamp']) - z25['start_dt']).dt.days
z50['leg_dur'] = (pd.to_datetime(z50['end_timestamp']) - z50['start_dt']).dt.days

z25f = z25[z25['leg_dur']>=1].copy()
z50f = z50[z50['leg_dur']>=1].copy()

bins = [(1,3),(4,7),(8,14),(15,30),(31,200)]
for name, df, col in [('zz25→zz50', z25f, 'c_50'), ('zz25→zz75', z25f, 'c_75'), ('zz50→zz75', z50f, 'c_50to75')]:
    print(f"\n  ── {name} ──")
    for lo, hi in bins:
        sub = df[(df['leg_dur']>=lo) & (df['leg_dur']<=hi)]
        if len(sub)>=5:
            print(f"    {lo:3d}-{hi:3d}d: rate={sub[col].mean():.4f} ({sub[col].mean()*100:.1f}%) N={len(sub):3d}")
    
    short = df[df['leg_dur']<=10]
    long = df[df['leg_dur']>10]
    if len(short)>=5 and len(long)>=5:
        stat, pv = mannwhitneyu(short[col], long[col], alternative='two-sided')
        print(f"    ≤10d: rate={short[col].mean():.4f} N={len(short)}  >10d: rate={long[col].mean():.4f} N={len(long)}")
        print(f"    MW U={stat:.1f}, p={pv:.4f} {'⚠️' if pv<0.05 else '✓'}")
    
    if len(df)>=10:
        rho, p_rho = spearmanr(df['leg_dur'], df[col])
        print(f"    Spearman ρ(dur, cascade)={rho:.4f}, p={p_rho:.4f}")

# prev_leg_duration from DB column
print(f"\n  ── prev_leg_duration (DB column) ──")
for name, df, col in [('zz25→zz50', z25f, 'c_50'), ('zz25→zz75', z25f, 'c_75'), ('zz50→zz75', z50f, 'c_50to75')]:
    sub = df.dropna(subset=['prev_leg_duration']).copy()
    sub = sub[sub['prev_leg_duration']>=1]
    if len(sub)>=10:
        rho, p_rho = spearmanr(sub['prev_leg_duration'], sub[col])
        print(f"    {name}: ρ(prev_dur, cascade)={rho:.4f}, p={p_rho:.4f}, N={len(sub)}")

# ==========================================================================
# 4. STRUCTURAL MOMENTUM
# ==========================================================================
print("\n" + "="*90)
print("4. STRUCTURAL MOMENTUM — p_continuation (same-scale)")
print("="*90)

def structural_momentum(legs_df, scale_name):
    df = legs_df.sort_values('start_dt').reset_index(drop=True).copy()
    df['next_type'] = df['start_type'].shift(-1)
    df['next_start'] = df['start_dt'].shift(-1)
    df['end_dt'] = pd.to_datetime(df['end_timestamp'])
    df['gap'] = (df['next_start'] - df['end_dt']).dt.days
    df['is_cont'] = (df['start_type'] == df['next_type']).astype(int)
    # Filter reasonable gaps
    cons = df[(df['gap']>=0) & (df['gap']<60)].copy()
    
    print(f"\n  ── {scale_name} ──")
    for typ in ['MIN', 'MAX']:
        sub = cons[cons['start_type']==typ]
        if len(sub)>0:
            print(f"    {typ}: p_cont={sub['is_cont'].mean():.4f} ({sub['is_cont'].mean()*100:.1f}%) N={len(sub)}")
    
    n_tot = len(cons)
    n_cont = cons['is_cont'].sum()
    p_raw = n_cont/n_tot if n_tot>0 else 0
    p_shr = (n_cont + 10*0.5)/(n_tot+10)  # m=10
    print(f"    Global: p_raw={p_raw:.4f}, p_shrunk={p_shr:.4f}, N={n_tot}")
    
    # Correlation with |prev_leg_return|
    sub = cons.dropna(subset=['prev_leg_return'])
    if len(sub)>=10:
        sub['abs_prev'] = sub['prev_leg_return'].abs()
        rho, p_rho = spearmanr(sub['abs_prev'], sub['is_cont'])
        print(f"    ρ(|prev_return|, continuation)={rho:.4f}, p={p_rho:.4f}, N={len(sub)}")
    return cons

sm25 = structural_momentum(z25, 'zz25')
sm50 = structural_momentum(z50, 'zz50')
sm75 = structural_momentum(z75, 'zz75')

# ==========================================================================
# 4b. DOMINO CALIBRATION
# ==========================================================================
print("\n" + "="*90)
print("4b. DOMINO — |prev_leg_return| vs Cascade")
print("="*90)

def domino_analysis(df, col, name):
    sub = df.dropna(subset=['prev_leg_return']).copy()
    sub['abs_prev'] = sub['prev_leg_return'].abs()
    
    edges = np.quantile(sub['abs_prev'], [0.3333, 0.6667])
    print(f"\n  ── {name} ──")
    print(f"    Tercil edges: [{edges[0]:.4f}, {edges[1]:.4f}]")
    
    masks = [
        sub['abs_prev'] <= edges[0],
        (sub['abs_prev'] > edges[0]) & (sub['abs_prev'] <= edges[1]),
        sub['abs_prev'] > edges[1],
    ]
    rates = []
    for i, (label, mask) in enumerate(zip(['t1_small','t2_medium','t3_large'], masks)):
        terc = sub[mask]
        rate = terc[col].mean()
        rates.append(rate)
        print(f"    {label}: rate={rate:.4f} ({rate*100:.1f}%) N={len(terc):3d} mean|prev|={terc['abs_prev'].mean():.4f}")
    
    t1 = sub[masks[0]][col]
    t3 = sub[masks[2]][col]
    if len(t1)>=5 and len(t3)>=5:
        stat, pv = mannwhitneyu(t3, t1, alternative='greater')
        print(f"    T3 vs T1 (one-sided): U={stat:.1f}, p={pv:.4f} {'⚠️' if pv<0.05 else '✓'}")
    
    rho, p_rho = spearmanr(sub['abs_prev'], sub[col])
    print(f"    Spearman ρ(|prev_return|, cascade)={rho:.4f}, p={p_rho:.4f}, N={len(sub)}")
    print(f"    Mean: {sub['abs_prev'].mean():.4f}  Std: {sub['abs_prev'].std():.4f}  Median: {sub['abs_prev'].median():.4f}")

domino_analysis(z25, 'c_50', 'zz25→zz50 (Domino zz25)')
domino_analysis(z25, 'c_75', 'zz25→zz75 (Domino zz25)')
domino_analysis(z50, 'c_50to75', 'zz50→zz75 (Domino zz50)')

# Compare with fact store
print("\n" + "="*90)
print("4c. FACT STORE vs DB REAL")
print("="*90)

import json
fs_dir = '/root/botero-trade/backend/modules/entry_decision/domain/rules'
for fname in sorted(os.listdir(fs_dir)):
    if not fname.endswith('_fact_store.json'):
        continue
    fpath = os.path.join(fs_dir, fname)
    try:
        with open(fpath) as f:
            fs = json.load(f)
        kin = fs.get('kinematic', fs.get('zigzag_kinematic', {}))
        
        if 'structural_momentum' in kin:
            sm = kin['structural_momentum']
            up = sm.get('up_legs', {})
            down = sm.get('down_legs', {})
            # Only print first one as example
            if 'vix' in fname.lower():
                print(f"\n  {fname} (structural_momentum):")
                print(f"    up_legs:   n={up.get('n_measured')}, p_cont={up.get('p_continuation')}, ev={up.get('ev_structural_pct')}")
                print(f"    down_legs: n={down.get('n_measured')}, p_cont={down.get('p_continuation')}, ev={down.get('ev_structural_pct')}")
                print(f"    DB real zz25 MAX p_cont: {sm25[sm25['start_type']=='MAX']['is_cont'].mean():.4f} (N={len(sm25[sm25['start_type']=='MAX'])})")
                print(f"    DB real zz25 MIN p_cont: {sm25[sm25['start_type']=='MIN']['is_cont'].mean():.4f} (N={len(sm25[sm25['start_type']=='MIN'])})")
        
        if 'prev_leg_domino' in kin:
            dom = kin['prev_leg_domino']
            if 'vix' in fname.lower():
                print(f"\n  {fname} (prev_leg_domino):")
                print(f"    n={dom.get('n_measured')}, mean_prev={dom.get('mean_prev_return')}")
                for tk in ['t1_small','t2_medium','t3_large']:
                    if tk in dom:
                        d = dom[tk]
                        print(f"    {tk}: rate={d.get('cascade_rate')}, n={d.get('n')}, mean|prev|={d.get('mean_abs_prev')}")
    except Exception as e:
        pass

# ==========================================================================
# SUMMARY
# ==========================================================================
print("\n" + "="*90)
print("RESUMEN FINAL")
print("="*90)
print(f"""
CASCADE RATES ({TICKER}, DB real, ±3d, same type):
  zz25→zz50:  {r25_50:.4f} ({r25_50*100:.1f}%)  N={len(z25)}  n={z25['c_50'].sum()}
  zz25→zz75:  {r25_75:.4f} ({r25_75*100:.1f}%)  N={len(z25)}  n={z25['c_75'].sum()}
  zz50→zz75:  {r50_75:.4f} ({r50_75*100:.1f}%)  N={len(z50)}  n={z50['c_50to75'].sum()}

CONTRADICCIONES:
  zz25 vs zz50: {len(c_25v50)}/{len(z25)} ({len(c_25v50)/len(z25)*100:.1f}%)
  zz25 vs zz75: {len(c_25v75)}/{len(z25)} ({len(c_25v75)/len(z25)*100:.1f}%)
  zz50 vs zz75: {len(c_50v75)}/{len(z50)} ({len(c_50v75)/len(z50)*100:.1f}%)
""")

conn.close()
print("✓ Auditoría completa.")