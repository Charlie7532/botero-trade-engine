"""
Missed Turns Forensic — OPTIMIZED VERSION
Pre-indexes tape by ticker to avoid O(n²) sorting.
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv; load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def banner(t):
    print(f"\n{'═'*100}\n  {t}\n{'═'*100}")

def section(t):
    print(f"\n  ── {t} ──")

store = TimescaleDataStore()
zz = pd.read_sql("SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker,timestamp", store.engine)
tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker,timestamp", store.engine)

# PRE-INDEX: sort tape per ticker once
tape_by_tk = {tk: grp.reset_index(drop=True) for tk, grp in tape.groupby('ticker')}

LOOK_BACK = 5
THR_STRONG, THR_WEAK = 0.60, 0.50
LONG_HEADS = ['p_long_entry','p_trend_reversal','p_bounce_height','p_short_cover']
SHORT_HEADS = ['p_short_entry','p_swing_exit','p_trend_reversal','p_pullback_depth']
FEATURES = ['fear_level','rsi_value','kalman_velocity','sigma_wave',
            'compression_ratio','vol_up_down_ratio','tide_slope','current_slope','wave_slope']

results = []
for _, tp in zz.iterrows():
    tk_tape = tape_by_tk.get(tp['ticker'])
    if tk_tape is None or len(tk_tape) < LOOK_BACK + 1:
        continue
    
    td = (tk_tape['timestamp'] - tp['timestamp']).abs()
    if td.min() > pd.Timedelta(days=3):
        continue
    center = td.idxmin()
    if center < LOOK_BACK:
        continue
    
    window = tk_tape.iloc[center - LOOK_BACK: center + 1]
    heads = LONG_HEADS if tp['tp_type'] == 'MIN' else SHORT_HEADS
    
    strong = weak = False
    max_ps = {}
    for h in heads:
        if h in window.columns:
            mx = window[h].max()
            max_ps[h] = mx
            if mx >= THR_STRONG: strong = True
            if mx >= THR_WEAK: weak = True
    
    cls = 'DETECTED' if strong else ('PARTIAL' if weak else 'MISSED')
    
    bar = tk_tape.iloc[center]
    feat = {f'feat_{f}': bar.get(f, np.nan) for f in FEATURES}
    
    results.append({
        'ticker': tp['ticker'], 'timestamp': tp['timestamp'],
        'tp_type': tp['tp_type'], 'classification': cls,
        'swing_return': tp['swing_return'], 'swing_days': tp['swing_days'],
        **{f'max_p_{h}': max_ps.get(h) for h in heads}, **feat,
    })

rdf = pd.DataFrame(results)

# ═══════════════════════════════════════════════════════════
banner("1. COBERTURA GENERAL")
for tp in ['MIN','MAX']:
    sub = rdf[rdf['tp_type']==tp]
    total = len(sub)
    det = (sub['classification']=='DETECTED').sum()
    par = (sub['classification']=='PARTIAL').sum()
    mis = (sub['classification']=='MISSED').sum()
    label = "PISOS (MIN)" if tp=='MIN' else "TECHOS (MAX)"
    print(f"\n  {label}: {total} giros totales")
    print(f"    ✅ DETECTED (P≥0.60): {det:>4d} ({det/total*100:5.1f}%)")
    print(f"    🟡 PARTIAL  (P≥0.50): {par:>4d} ({par/total*100:5.1f}%)")
    print(f"    🔴 MISSED   (P<0.50): {mis:>4d} ({mis/total*100:5.1f}%)")

# ═══════════════════════════════════════════════════════════
banner("2. COBERTURA POR TICKER")
for tp in ['MIN','MAX']:
    label = "PISOS" if tp=='MIN' else "TECHOS"
    section(label)
    print(f"  {'Ticker':>6s} │ {'Total':>5s} │ {'Det':>4s} │ {'Part':>4s} │ {'Miss':>4s} │ {'Det%':>5s} │ {'Miss%':>5s} │ {'AvgSwing':>9s}")
    print(f"  {'─'*65}")
    for tk in sorted(rdf['ticker'].unique()):
        sub = rdf[(rdf['ticker']==tk)&(rdf['tp_type']==tp)]
        total = len(sub)
        if total < 5: continue
        det = (sub['classification']=='DETECTED').sum()
        par = (sub['classification']=='PARTIAL').sum()
        mis = (sub['classification']=='MISSED').sum()
        avg = sub['swing_return'].abs().mean()*100
        print(f"  {tk:>6s} │ {total:>5d} │ {det:>4d} │ {par:>4d} │ {mis:>4d} │ {det/total*100:>4.0f}% │ {mis/total*100:>4.0f}% │ {avg:>+8.1f}%")

# ═══════════════════════════════════════════════════════════
banner("3. ¿POR QUÉ SE PIERDEN?")
missed = rdf[rdf['classification']=='MISSED'].copy()

section("3a. ¿Los giros perdidos son más pequeños?")
for tp in ['MIN','MAX']:
    det = rdf[(rdf['tp_type']==tp)&(rdf['classification']=='DETECTED')]
    mis = rdf[(rdf['tp_type']==tp)&(rdf['classification']=='MISSED')]
    if len(det)>10 and len(mis)>10:
        label = "PISOS" if tp=='MIN' else "TECHOS"
        print(f"    {label}:")
        print(f"      Detected: {det['swing_return'].abs().mean()*100:+.1f}% avg, {det['swing_days'].median():.0f}d med")
        print(f"      Missed:   {mis['swing_return'].abs().mean()*100:+.1f}% avg, {mis['swing_days'].median():.0f}d med")

section("3b. Feature profile PERDIDOS vs DETECTADOS")
for tp in ['MIN','MAX']:
    label = "PISOS" if tp=='MIN' else "TECHOS"
    det = rdf[(rdf['tp_type']==tp)&(rdf['classification']=='DETECTED')]
    mis = rdf[(rdf['tp_type']==tp)&(rdf['classification']=='MISSED')]
    if len(det)<20 or len(mis)<20: continue
    print(f"\n    {label}:")
    print(f"    {'Feature':>22s} │ {'Detected':>9s} │ {'Missed':>9s} │ {'Delta':>9s} │ Interpretation")
    print(f"    {'─'*70}")
    for f in FEATURES:
        col = f'feat_{f}'
        if col not in rdf.columns: continue
        dv, mv = det[col].mean(), mis[col].mean()
        if np.isnan(dv) or np.isnan(mv): continue
        delta = mv - dv
        ps = np.sqrt((det[col].std()**2 + mis[col].std()**2)/2)
        d = delta/ps if ps>0 else 0
        sig = f"★★ d={d:+.2f}" if abs(d)>0.3 else (f"★  d={d:+.2f}" if abs(d)>0.15 else f"   d={d:+.2f}")
        print(f"    {f:>22s} │ {dv:>9.3f} │ {mv:>9.3f} │ {delta:>+8.3f} │ {sig}")

# ═══════════════════════════════════════════════════════════
banner("4. CONTEXTO HH/HL/LH/LL")
for tp in ['MIN','MAX']:
    tp_sub = zz[zz['tp_type']==tp]
    for tk in sorted(rdf['ticker'].unique()):
        tkz = tp_sub[tp_sub['ticker']==tk].sort_values('timestamp').reset_index(drop=True)
        for i in range(1, len(tkz)):
            ts = tkz.iloc[i]['timestamp']
            match = rdf[(rdf['ticker']==tk)&(rdf['timestamp']==ts)&(rdf['tp_type']==tp)]
            if len(match)==0: continue
            idx = match.index[0]
            if tp=='MIN':
                pat = 'HL' if tkz.iloc[i]['price']>tkz.iloc[i-1]['price'] else 'LL'
            else:
                pat = 'HH' if tkz.iloc[i]['price']>tkz.iloc[i-1]['price'] else 'LH'
            rdf.loc[idx,'structure'] = pat

for tp in ['MIN','MAX']:
    label = "PISOS" if tp=='MIN' else "TECHOS"
    sub = rdf[(rdf['tp_type']==tp)&rdf['structure'].notna()]
    if len(sub)<20: continue
    print(f"\n    {label}:")
    print(f"    {'Pattern':>8s} │ {'Total':>5s} │ {'Det':>5s} │ {'Miss':>5s} │ {'MissRate':>8s}")
    print(f"    {'─'*45}")
    for pat in sorted(sub['structure'].unique()):
        ps = sub[sub['structure']==pat]
        t = len(ps)
        d = (ps['classification']=='DETECTED').sum()
        m = (ps['classification']=='MISSED').sum()
        print(f"    {pat:>8s} │ {t:>5d} │ {d:>5d} │ {m:>5d} │ {m/t*100:>6.1f}%")

# ═══════════════════════════════════════════════════════════
banner("5. PEORES GIROS PERDIDOS")
section("5a. Biggest missed MIN (dejamos de comprar en el piso)")
mm = missed[missed['tp_type']=='MIN'].dropna(subset=['swing_return']).sort_values('swing_return',ascending=False)
print(f"  {'Ticker':>6s} │ {'Date':>12s} │ {'NextUp%':>8s} │ {'Days':>5s} │ {'fear':>5s} │ {'rsi':>5s} │ {'kalman':>7s}")
print(f"  {'─'*60}")
for _,r in mm.head(20).iterrows():
    ts = pd.Timestamp(r['timestamp']).strftime('%Y-%m-%d')
    fe = f"{r.get('feat_fear_level',np.nan):.2f}" if not np.isnan(r.get('feat_fear_level',np.nan)) else "n/a"
    rs = f"{r.get('feat_rsi_value',np.nan):.0f}" if not np.isnan(r.get('feat_rsi_value',np.nan)) else "n/a"
    kl = f"{r.get('feat_kalman_velocity',np.nan):+.3f}" if not np.isnan(r.get('feat_kalman_velocity',np.nan)) else "n/a"
    print(f"  {r['ticker']:>6s} │ {ts:>12s} │ {r['swing_return']*100:>+7.1f}% │ {r.get('swing_days',0):>5.0f} │ {fe:>5s} │ {rs:>5s} │ {kl:>7s}")

section("5b. Biggest missed MAX (dejamos de vender en el techo)")
mx = missed[missed['tp_type']=='MAX'].dropna(subset=['swing_return']).sort_values('swing_return')
print(f"  {'Ticker':>6s} │ {'Date':>12s} │ {'NextDn%':>8s} │ {'Days':>5s} │ {'fear':>5s} │ {'rsi':>5s} │ {'kalman':>7s}")
print(f"  {'─'*60}")
for _,r in mx.head(20).iterrows():
    ts = pd.Timestamp(r['timestamp']).strftime('%Y-%m-%d')
    fe = f"{r.get('feat_fear_level',np.nan):.2f}" if not np.isnan(r.get('feat_fear_level',np.nan)) else "n/a"
    rs = f"{r.get('feat_rsi_value',np.nan):.0f}" if not np.isnan(r.get('feat_rsi_value',np.nan)) else "n/a"
    kl = f"{r.get('feat_kalman_velocity',np.nan):+.3f}" if not np.isnan(r.get('feat_kalman_velocity',np.nan)) else "n/a"
    print(f"  {r['ticker']:>6s} │ {ts:>12s} │ {r['swing_return']*100:>+7.1f}% │ {r.get('swing_days',0):>5.0f} │ {fe:>5s} │ {rs:>5s} │ {kl:>7s}")

# ═══════════════════════════════════════════════════════════
banner("6. CLASIFICACIÓN DE DETECTABILIDAD")
for tp in ['MIN','MAX']:
    label = "PISOS" if tp=='MIN' else "TECHOS"
    mis = missed[missed['tp_type']==tp].copy()
    if len(mis)<5: continue
    means = {f: rdf[f'feat_{f}'].mean() for f in FEATURES if f'feat_{f}' in rdf.columns}
    stds = {f: rdf[f'feat_{f}'].std() for f in FEATURES if f'feat_{f}' in rdf.columns}
    
    dc = pc = uc = 0
    for _,r in mis.iterrows():
        ec = sum(1 for f in FEATURES if f in means and not np.isnan(r.get(f'feat_{f}',np.nan))
                 and abs(r[f'feat_{f}']-means[f])/(stds[f] if stds[f]>0 else 1) > 1.0)
        if ec>=4: dc+=1
        elif ec>=2: pc+=1
        else: uc+=1
    
    tm = len(mis)
    print(f"\n    {label} PERDIDOS ({tm} total):")
    print(f"      🟡 DETECTABLE (≥4 extremas):  {dc} ({dc/tm*100:.0f}%)")
    print(f"      🟠 PARTIAL (2-3 extremas):     {pc} ({pc/tm*100:.0f}%)")
    print(f"      🔴 UNPREDICTABLE (<2 extremas): {uc} ({uc/tm*100:.0f}%)")
    print(f"      → Margen de mejora: {(dc+pc)/tm*100:.0f}% tenían señales")

store.close()
banner("FORENSIA DE GIROS PERDIDOS COMPLETA")
