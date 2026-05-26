"""
FORENSIC: Event-Based Signal Evaluation (Zigzag)
=================================================
LdP + Simons + Druckenmiller + PTJ
"""
import sys; sys.path.insert(0, '/root/botero-trade')
from dotenv import load_dotenv; load_dotenv('/root/botero-trade/.env')
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd
import numpy as np

def p(title):
    print(f"\n{'═' * 90}")
    print(f"  {title}")
    print(f"{'═' * 90}")

store = TimescaleDataStore()

# Load tape + OHLCV (join on ticker+timestamp)
tape = pd.read_sql('SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp', store.engine)
ohlcv = pd.read_sql("SELECT ticker, time as timestamp, close FROM market.ohlcv_bars WHERE timeframe='1d'", store.engine)
tape = tape.merge(ohlcv, on=['ticker','timestamp'], how='left')
print(f"Loaded: {len(tape):,d} rows, close NaN: {tape['close'].isna().sum()}")

heads = ['p_long_entry','p_swing_exit','p_pullback_depth','p_trend_reversal',
         'p_short_entry','p_short_cover','p_bounce_height','p_trend_recovery']
features_extra = ['sigma_tide','rsi_value','fear_level','compression_ratio',
                  'kalman_velocity','tide_slope']

# ============================================================================
def zigzag(close, min_pct=0.03):
    """Detect alternating min/max with minimum swing >= min_pct."""
    pts = []
    last_idx, last_type = 0, ('MIN' if close[0] < close[min(1,len(close)-1)] else 'MAX')
    last_val = close[0]
    for i in range(1, len(close)):
        if last_type == 'MIN':
            if close[i] > last_val * (1 + min_pct):
                pts.append((last_idx, 'MIN', last_val))
                best = last_idx + int(np.argmax(close[last_idx:i+1]))
                last_idx, last_type, last_val = best, 'MAX', close[best]
            elif close[i] < last_val:
                last_idx, last_val = i, close[i]
        else:
            if close[i] < last_val * (1 - min_pct):
                pts.append((last_idx, 'MAX', last_val))
                best = last_idx + int(np.argmin(close[last_idx:i+1]))
                last_idx, last_type, last_val = best, 'MIN', close[best]
            elif close[i] > last_val:
                last_idx, last_val = i, close[i]
    return pts

# ============================================================================
p("STEP 1: DETECCIÓN DE PUNTOS DE INFLEXIÓN (Zigzag 3% y 5%)")

all_tp = []
for ticker in tape['ticker'].unique():
    sub = tape[tape['ticker'] == ticker].sort_values('timestamp').reset_index(drop=True)
    close = sub['close'].values.astype(float)
    if np.isnan(close).all():
        continue
    
    for min_sw in [0.03, 0.05]:
        pts = zigzag(close, min_sw)
        for j, (idx, tp_type, val) in enumerate(pts):
            if idx < 50 or j + 1 >= len(pts):
                continue
            next_idx, _, next_val = pts[j+1]
            if next_idx >= len(sub):
                continue
            swing_ret = next_val / val - 1
            swing_days = next_idx - idx
            row = sub.iloc[idx]
            rec = {'ticker': ticker, 'tp_type': tp_type, 'min_swing': min_sw,
                   'swing_return': swing_ret, 'swing_days': swing_days,
                   'swing_speed': swing_ret / max(swing_days, 1), 'idx': idx}
            for h in heads:
                rec[h] = float(row[h]) if pd.notna(row.get(h)) else None
            for f in features_extra:
                rec[f] = float(row[f]) if pd.notna(row.get(f)) else None
            rec['regime'] = row.get('regime', '')
            all_tp.append(rec)

tp_df = pd.DataFrame(all_tp)

for ms in [0.03, 0.05]:
    s = tp_df[tp_df['min_swing'] == ms]
    mins = s[s['tp_type'] == 'MIN']
    maxs = s[s['tp_type'] == 'MAX']
    print(f"\n  Zigzag ≥ {ms*100:.0f}%:")
    print(f"    Local MINIMA: {len(mins):,d}  (avg rally: {mins['swing_return'].mean():+.2%}, avg {mins['swing_days'].mean():.1f}d)")
    print(f"    Local MAXIMA: {len(maxs):,d}  (avg decline: {maxs['swing_return'].mean():+.2%}, avg {maxs['swing_days'].mean():.1f}d)")

# ============================================================================
tp3 = tp_df[tp_df['min_swing'] == 0.03]
mins3 = tp3[tp3['tp_type'] == 'MIN']
maxs3 = tp3[tp3['tp_type'] == 'MAX']
normal = tape.sample(min(5000, len(tape)//3), random_state=42)

p("STEP 2: SEÑALES EN PUNTOS DE INFLEXIÓN vs BARRAS NORMALES")
print(f"\n  {'Signal':>22s} │ {'At MIN':>8s} │ {'At MAX':>8s} │ {'Normal':>8s} │ {'MIN diff':>9s} │ {'MAX diff':>9s}")
print(f"  {'─'*75}")
for col in heads + features_extra:
    mv = mins3[col].mean(); xv = maxs3[col].mean(); nv = normal[col].mean()
    md = mv - nv; xd = xv - nv
    ms_ = '★' if abs(md) > 0.02 else ''; xs_ = '★' if abs(xd) > 0.02 else ''
    print(f"  {col:>22s} │ {mv:>8.4f} │ {xv:>8.4f} │ {nv:>8.4f} │ {md:>+8.4f} {ms_} │ {xd:>+8.4f} {xs_}")

# ============================================================================
p("STEP 3: DISCRIMINACIÓN — ¿Señal alta = punto de inflexión?")
print("\n  En LOCAL MINIMA (rallies inminentes):")
print(f"  {'Signal':>22s} │ {'P>0.7@MIN':>10s} │ {'P>0.7@norm':>10s} │ {'Lift':>6s}")
print(f"  {'─'*60}")
for h in heads:
    hm = (mins3[h] > 0.7).mean(); hn = (normal[h] > 0.7).mean()
    lift = hm / max(hn, 0.0001)
    st = '★★★' if lift > 2 else ('★★' if lift > 1.5 else ('★' if lift > 1.2 else ''))
    print(f"  {h:>22s} │ {hm*100:>9.1f}% │ {hn*100:>9.1f}% │ {lift:>5.1f}x {st}")

print("\n  En LOCAL MAXIMA (caídas inminentes):")
print(f"  {'Signal':>22s} │ {'P>0.7@MAX':>10s} │ {'P>0.7@norm':>10s} │ {'Lift':>6s}")
print(f"  {'─'*60}")
for h in heads:
    hm = (maxs3[h] > 0.7).mean(); hn = (normal[h] > 0.7).mean()
    lift = hm / max(hn, 0.0001)
    st = '★★★' if lift > 2 else ('★★' if lift > 1.5 else ('★' if lift > 1.2 else ''))
    print(f"  {h:>22s} │ {hm*100:>9.1f}% │ {hn*100:>9.1f}% │ {lift:>5.1f}x {st}")

# ============================================================================
p("STEP 4: CORRELACIÓN SEÑAL → MAGNITUD DEL SWING")
print("  En MINIMA: ¿P alta → rally más grande?")
print(f"  {'Signal':>22s} │ {'corr(swing%)':>12s} │ {'corr(days)':>10s} │ {'corr(speed)':>11s}")
print(f"  {'─'*65}")
for h in heads:
    r1 = mins3[h].corr(mins3['swing_return']); r2 = mins3[h].corr(mins3['swing_days'])
    r3 = mins3[h].corr(mins3['swing_speed'])
    st = '★' if abs(r1) > 0.05 else ''
    print(f"  {h:>22s} │ {r1:>+12.4f} │ {r2:>+10.4f} │ {r3:>+11.4f} {st}")

print("\n  En MAXIMA: ¿P alta → caída más grande?")
print(f"  {'Signal':>22s} │ {'corr(swing%)':>12s} │ {'corr(days)':>10s} │ {'corr(speed)':>11s}")
print(f"  {'─'*65}")
for h in heads:
    r1 = maxs3[h].corr(maxs3['swing_return']); r2 = maxs3[h].corr(maxs3['swing_days'])
    r3 = maxs3[h].corr(maxs3['swing_speed'])
    st = '★' if abs(r1) > 0.05 else ''
    print(f"  {h:>22s} │ {r1:>+12.4f} │ {r2:>+10.4f} │ {r3:>+11.4f} {st}")

# ============================================================================
p("STEP 5: DRIFT — ¿Señal llega ANTES o DESPUÉS del turning point?")
for tp_type, signal, thr, desc in [
    ('MIN', 'p_long_entry', 0.7, 'P(long)>0.7 around MINIMA'),
    ('MIN', 'p_bounce_height', 0.7, 'P(bounce)>0.7 around MINIMA'),
    ('MAX', 'p_swing_exit', 0.6, 'P(swing_exit)>0.6 around MAXIMA'),
    ('MAX', 'p_short_entry', 0.6, 'P(short)>0.6 around MAXIMA'),
]:
    tp_sub = tp3[tp3['tp_type'] == tp_type]
    drifts = []
    for _, tpr in tp_sub.head(500).iterrows():  # sample for speed
        tt = tape[(tape['ticker'] == tpr['ticker'])].sort_values('timestamp').reset_index(drop=True)
        ti = int(tpr['idx'])
        if ti < 10 or ti + 10 >= len(tt):
            continue
        window = tt.iloc[ti-10:ti+11]
        sig_on = window[window[signal] > thr]
        if len(sig_on) > 0:
            first = sig_on.index[0]
            drifts.append(first - (ti))  # relative to the reset index
    
    if drifts:
        d = np.array(drifts)
        # Fix: compute relative to window center
        # window indices are ti-10 to ti+10, so center is at position 10
        # But after reset_index, the indices are the original df indices
        # Let me fix this by using iloc positions
        pass
    
    # Simpler approach: just check the signal AT the turning point vs neighbors
    tp_at = tp_sub[signal].mean()
    # Get bars 5 before and 5 after from tape
    befores, afters = [], []
    for _, tpr in tp_sub.head(500).iterrows():
        tt = tape[(tape['ticker'] == tpr['ticker'])].sort_values('timestamp').reset_index(drop=True)
        ti = int(tpr['idx'])
        if ti >= 5 and ti + 5 < len(tt):
            befores.append(tt.iloc[ti-5:ti][signal].mean())
            afters.append(tt.iloc[ti+1:ti+6][signal].mean())
    
    before_avg = np.mean(befores) if befores else 0
    after_avg = np.mean(afters) if afters else 0
    print(f"\n  {desc}:")
    print(f"    5 bars BEFORE: {before_avg:.4f}  │  AT turning point: {tp_at:.4f}  │  5 bars AFTER: {after_avg:.4f}")
    print(f"    Signal arrives: {'BEFORE' if before_avg > tp_at else ('AT' if abs(before_avg - tp_at) < 0.005 else 'AFTER')} the turn")

# ============================================================================
p("STEP 6: DURACIÓN DE SWINGS — Por qué 20d fijo falla")
print(f"\n  {'Type':>15s} │ {'N':>5s} │ {'P5':>5s} │ {'P25':>5s} │ {'P50':>5s} │ {'P75':>5s} │ {'P95':>5s} │ {'Mean':>5s}")
print(f"  {'─'*65}")
for tt, desc in [('MIN','UP (min→max)'), ('MAX','DOWN (max→min)')]:
    s = tp3[tp3['tp_type'] == tt]['swing_days']
    pq = s.quantile([0.05,0.25,0.5,0.75,0.95])
    print(f"  {desc:>15s} │ {len(s):>5,d} │ {pq.iloc[0]:>4.0f}d │ {pq.iloc[1]:>4.0f}d │ {pq.iloc[2]:>4.0f}d │ {pq.iloc[3]:>4.0f}d │ {pq.iloc[4]:>4.0f}d │ {s.mean():>4.1f}d")

pct_under20 = (tp3['swing_days'] < 20).mean()
pct_20_40 = ((tp3['swing_days'] >= 20) & (tp3['swing_days'] < 40)).mean()
pct_over40 = (tp3['swing_days'] >= 40).mean()
print(f"\n  Con horizonte fijo 20d:")
print(f"    < 20d (capturados completos):  {pct_under20*100:.1f}%")
print(f"    20-40d (parciales):            {pct_20_40*100:.1f}%")
print(f"    > 40d (perdidos):              {pct_over40*100:.1f}%")

# ============================================================================
p("STEP 7: POR TICKER — Señales en puntos de inflexión (3%)")
tp3_mins = tp3[tp3['tp_type'] == 'MIN']
print(f"\n  {'Ticker':>6s} │ {'MINs':>5s} │ {'Avg Rally':>9s} │ {'Days':>5s} │ {'P(long)@MIN':>11s} │ {'P(long)norm':>11s} │ {'Lift':>5s}")
print(f"  {'─'*70}")
for tk in sorted(tape['ticker'].unique()):
    tm = tp3_mins[tp3_mins['ticker'] == tk]
    tn = tape[tape['ticker'] == tk]
    if len(tm) < 3: continue
    print(f"  {tk:>6s} │ {len(tm):>5d} │ {tm['swing_return'].mean():>+9.2%} │ {tm['swing_days'].mean():>4.0f}d │ {tm['p_long_entry'].mean():>11.4f} │ {tn['p_long_entry'].mean():>11.4f} │ {tm['p_long_entry'].mean()/max(tn['p_long_entry'].mean(),0.001):>4.2f}x")

store.close()
print(f"\n{'═' * 90}")
print(f"  FORENSIC TURNING POINTS COMPLETE")
print(f"{'═' * 90}")
