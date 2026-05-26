"""
Stage 1a: BASELINE REAL — Calificar nuestro modelo actual con el zigzag
========================================================================
Lee SOLO data que nuestros algoritmos YA produjeron:
  - engine.signal_tape → señales P(...) calculadas por nuestros módulos
  - engine.zigzag_points → turning points del precio real

Cero hipótesis. Solo cruzamos lo que YA existe.
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

# ════════════════════════════════════════
# READ ONLY what our algorithms produced
# ════════════════════════════════════════
zz = pd.read_sql("SELECT * FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker,timestamp", store.engine)
tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker,timestamp", store.engine)
tape_by_tk = {tk: grp.reset_index(drop=True) for tk, grp in tape.groupby('ticker')}

banner("STAGE 1a: BASELINE REAL — Nuestros algoritmos vs Realidad")
print(f"  Signal tape: {len(tape):,d} rows (computed by OUR modules)")
print(f"  Zigzag 5%: {len(zz):,d} points (computed from REAL prices)")

# ════════════════════════════════════════════════════════
# PART A: COVERAGE — ¿Cuántos giros detectamos?
# Para cada turning point, ¿nuestro modelo disparó señal?
# ════════════════════════════════════════════════════════
banner("PART A: COVERAGE — ¿Nuestras señales cubren los giros reales?")

WINDOW = 5  # bars before turn to check
LONG_HEADS = ['p_long_entry', 'p_bounce_height', 'p_short_cover', 'p_trend_reversal']
SHORT_HEADS = ['p_short_entry', 'p_swing_exit', 'p_trend_reversal', 'p_pullback_depth']

coverage = []
for _, tp in zz.iterrows():
    tk_tape = tape_by_tk.get(tp['ticker'])
    if tk_tape is None: continue
    td = (tk_tape['timestamp'] - tp['timestamp']).abs()
    if td.min() > pd.Timedelta(days=3): continue
    center = td.idxmin()
    if center < WINDOW: continue
    
    window = tk_tape.iloc[center - WINDOW: center + 1]
    heads = LONG_HEADS if tp['tp_type'] == 'MIN' else SHORT_HEADS
    
    max_p = max((window[h].max() for h in heads if h in window.columns), default=0)
    best_head = max(((window[h].max(), h) for h in heads if h in window.columns), default=(0, 'none'))[1]
    
    # Latency: how many bars BEFORE the turn did the signal peak?
    best_col = best_head if best_head in window.columns else None
    latency = np.nan
    if best_col:
        peak_idx = window[best_col].idxmax()
        latency = center - peak_idx  # positive = before turn
    
    coverage.append({
        'ticker': tp['ticker'], 'timestamp': tp['timestamp'],
        'tp_type': tp['tp_type'], 'max_p': max_p,
        'best_head': best_head, 'latency': latency,
        'swing_return': tp['swing_return'], 'swing_days': tp['swing_days'],
        'detected_60': max_p >= 0.60,
        'detected_55': max_p >= 0.55,
        'detected_50': max_p >= 0.50,
    })

cdf = pd.DataFrame(coverage)

for tp in ['MIN', 'MAX']:
    sub = cdf[cdf['tp_type'] == tp]
    label = "PISOS" if tp == 'MIN' else "TECHOS"
    section(f"{label} ({len(sub)} giros)")
    for thr, col in [(0.60, 'detected_60'), (0.55, 'detected_55'), (0.50, 'detected_50')]:
        det = sub[col].sum()
        print(f"    P≥{thr}: {det:>4d}/{len(sub)} = {det/len(sub)*100:.1f}%")
    print(f"    Latency (bars before): mean={sub['latency'].mean():.1f}, median={sub['latency'].median():.1f}")

section("COVERAGE POR TICKER (P≥0.60)")
for tp in ['MIN', 'MAX']:
    label = "PISOS" if tp == 'MIN' else "TECHOS"
    print(f"\n  {label}:")
    print(f"  {'Ticker':>6s} │ {'N':>4s} │ {'Det':>4s} │ {'%':>5s} │ {'Latency':>7s} │ {'BestHead':>18s}")
    print(f"  {'─'*55}")
    for tk in sorted(cdf['ticker'].unique()):
        sub = cdf[(cdf['ticker']==tk) & (cdf['tp_type']==tp)]
        if len(sub) < 5: continue
        det = sub['detected_60'].sum()
        lat = sub[sub['detected_60']]['latency'].mean()
        # Most common best head
        bh = sub[sub['detected_60']]['best_head'].mode()
        bh_str = bh.iloc[0] if len(bh) > 0 else 'n/a'
        print(f"  {tk:>6s} │ {len(sub):>4d} │ {det:>4d} │ {det/len(sub)*100:>4.0f}% │ {lat:>6.1f}d │ {bh_str:>18s}")

# ════════════════════════════════════════════════════════
# PART B: FALSE POSITIVES — ¿Cuántas señales son ruido?
# Para cada señal P≥0.60, ¿hay un giro real cerca?
# ════════════════════════════════════════════════════════
banner("PART B: FALSE POSITIVES — ¿Cuántas señales son ruido?")

FP_WINDOW = 10  # bars forward to check for turning point

fp_results = []
for tk in sorted(tape_by_tk.keys()):
    tk_tape = tape_by_tk[tk]
    tk_zz = zz[zz['ticker'] == tk].sort_values('timestamp')
    
    # Find all bars where any LONG head fired P >= 0.60
    for head_group, tp_type, label in [
        (LONG_HEADS, 'MIN', 'LONG'),
        (SHORT_HEADS, 'MAX', 'SHORT'),
    ]:
        for h in head_group:
            if h not in tk_tape.columns: continue
            fired = tk_tape[tk_tape[h] >= 0.60]
            
            for idx, bar in fired.iterrows():
                # Is there a zigzag turning point within ±FP_WINDOW bars?
                tp_matches = tk_zz[tk_zz['tp_type'] == tp_type]
                if len(tp_matches) == 0: continue
                
                td = (tp_matches['timestamp'] - bar['timestamp']).dt.days
                nearest = td.abs().min()
                
                is_tp = nearest <= FP_WINDOW
                fp_results.append({
                    'ticker': tk, 'timestamp': bar['timestamp'],
                    'head': h, 'p_value': bar[h],
                    'signal_type': label,
                    'nearest_turn_days': nearest,
                    'is_true_positive': is_tp,
                })

fpdf = pd.DataFrame(fp_results)

section("Señales P≥0.60 disparadas por NUESTRO modelo")
for sig in ['LONG', 'SHORT']:
    sub = fpdf[fpdf['signal_type'] == sig]
    total = len(sub)
    tp = sub['is_true_positive'].sum()
    fp = total - tp
    prec = tp/total*100 if total > 0 else 0
    print(f"    {sig:>5s}: {total:>6,d} signals │ TP={tp:>5,d} ({tp/total*100:.1f}%) │ FP={fp:>5,d} ({fp/total*100:.1f}%) │ Precision={prec:.1f}%")

section("FALSE POSITIVES POR HEAD")
print(f"  {'Head':>18s} │ {'Total':>6s} │ {'TP':>5s} │ {'FP':>5s} │ {'Precision':>9s}")
print(f"  {'─'*55}")
for h in sorted(fpdf['head'].unique()):
    sub = fpdf[fpdf['head'] == h]
    total = len(sub)
    tp = sub['is_true_positive'].sum()
    print(f"  {h:>18s} │ {total:>6,d} │ {tp:>5,d} │ {total-tp:>5,d} │ {tp/total*100:>8.1f}%")

section("FALSE POSITIVES POR TICKER")
for sig in ['LONG', 'SHORT']:
    label = "LONG signals" if sig == 'LONG' else "SHORT signals"
    print(f"\n  {label}:")
    print(f"  {'Ticker':>6s} │ {'Total':>6s} │ {'TP':>5s} │ {'FP':>5s} │ {'Precision':>9s}")
    print(f"  {'─'*45}")
    for tk in sorted(fpdf['ticker'].unique()):
        sub = fpdf[(fpdf['ticker']==tk) & (fpdf['signal_type']==sig)]
        if len(sub) < 10: continue
        total = len(sub)
        tp = sub['is_true_positive'].sum()
        print(f"  {tk:>6s} │ {total:>6,d} │ {tp:>5,d} │ {total-tp:>5,d} │ {tp/total*100:>8.1f}%")

# ════════════════════════════════════════════════════════
# RESUMEN BASELINE
# ════════════════════════════════════════════════════════
banner("BASELINE SUMMARY — Nuestro Modelo Actual")

for tp, label in [('MIN', 'PISOS'), ('MAX', 'TECHOS')]:
    sub_c = cdf[cdf['tp_type'] == tp]
    sig = 'LONG' if tp == 'MIN' else 'SHORT'
    sub_f = fpdf[fpdf['signal_type'] == sig]
    
    cov = sub_c['detected_60'].mean() * 100
    missed = (~sub_c['detected_60']).sum()
    lat = sub_c[sub_c['detected_60']]['latency'].mean()
    
    total_sig = len(sub_f)
    tp_count = sub_f['is_true_positive'].sum()
    prec = tp_count/total_sig*100 if total_sig > 0 else 0
    
    print(f"\n  {label}:")
    print(f"    Coverage (P≥0.60):  {cov:.1f}%")
    print(f"    Missed:             {missed}")
    print(f"    Latency:            {lat:.1f} bars antes del giro")
    print(f"    Signals fired:      {total_sig:,d}")
    print(f"    True Positives:     {tp_count:,d} ({prec:.1f}%)")
    print(f"    False Positives:    {total_sig-tp_count:,d} ({100-prec:.1f}%)")

store.close()
banner("STAGE 1a COMPLETE — BASELINE ESTABLECIDO")
