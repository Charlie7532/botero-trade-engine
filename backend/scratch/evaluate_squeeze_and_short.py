"""
9.4: Evaluate Squeeze signals — do current constellations catch them?
9.5: Evaluate short_entry for Speculative department
"""
import sys; sys.path.insert(0, '/root/botero-trade')
from dotenv import load_dotenv; load_dotenv('/root/botero-trade/.env')
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd, numpy as np

store = TimescaleDataStore()
tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp", store.engine)
print(f"Loaded: {len(tape):,d} rows")

# ═══════════════════════════════════════════════════════════════
# 9.4: SQUEEZE EVALUATION
# ═══════════════════════════════════════════════════════════════
print(f"\n{'═' * 95}")
print(f"  9.4: SQUEEZE SIGNALS — Are current constellations sufficient?")
print(f"{'═' * 95}")

# Define squeeze: compression_ratio < 0.3 (bands very tight)
squeeze = tape['compression_ratio'] < 0.3
n_squeeze = squeeze.sum()
print(f"\n  Squeeze bars (compression < 0.3): {n_squeeze:,d} ({n_squeeze/len(tape)*100:.1f}%)")

# What happens after squeeze?
valid = tape[tape['fwd_return_10d'].notna()].copy()
sq = valid[valid['compression_ratio'] < 0.3]
nsq = valid[valid['compression_ratio'] >= 0.3]

print(f"\n  ── Forward 10d returns ──")
print(f"  {'':>20s} │ {'N':>8s} │ {'Mean':>8s} │ {'Median':>8s} │ {'P(>0)':>8s} │ {'MaxDD':>8s} │ {'MaxRU':>8s}")
print(f"  {'─'*75}")
for name, sub in [("Squeeze", sq), ("Non-squeeze", nsq)]:
    print(f"  {name:>20s} │ {len(sub):>8,d} │ {sub['fwd_return_10d'].mean()*100:>+7.2f}% │ {sub['fwd_return_10d'].median()*100:>+7.2f}% │ {(sub['fwd_return_10d']>0).mean()*100:>7.1f}% │ {sub['fwd_max_dd_10d'].mean()*100:>+7.2f}% │ {sub['fwd_max_runup_10d'].mean()*100:>+7.2f}%")

# Squeeze + directional signal
combos = [
    ("Squeeze + P(long)>0.65", lambda d: (d['compression_ratio']<0.3) & (d['p_long_entry']>0.65)),
    ("Squeeze + KV>0", lambda d: (d['compression_ratio']<0.3) & (d['kalman_velocity']>0)),
    ("Squeeze + KV<0", lambda d: (d['compression_ratio']<0.3) & (d['kalman_velocity']<0)),
    ("Squeeze + RSI>50", lambda d: (d['compression_ratio']<0.3) & (d['rsi_value']>50)),
    ("Squeeze + RSI<30", lambda d: (d['compression_ratio']<0.3) & (d['rsi_value']<30)),
    ("Squeeze + BULL", lambda d: (d['compression_ratio']<0.3) & (d['regime']=='BULL')),
    ("Squeeze + BEAR", lambda d: (d['compression_ratio']<0.3) & (d['regime']=='BEAR')),
    ("Squeeze + fear>=4", lambda d: (d['compression_ratio']<0.3) & (d['fear_level']>=4)),
]

print(f"\n  ── Squeeze combos → 10d outcome ──")
print(f"  {'Combo':>30s} │ {'N':>6s} │ {'Ret 10d':>8s} │ {'P(>0)':>8s} │ {'MaxDD':>8s} │ {'Edge?':>6s}")
print(f"  {'─'*80}")
base_ret = valid['fwd_return_10d'].mean()
for name, fn in combos:
    mask = fn(valid)
    n = mask.sum()
    if n < 20:
        continue
    s = valid[mask]
    ret = s['fwd_return_10d'].mean()
    ppos = (s['fwd_return_10d'] > 0).mean() * 100
    dd = s['fwd_max_dd_10d'].mean() * 100
    edge = "★" if abs(ret - base_ret) > 0.005 else ""
    print(f"  {name:>30s} │ {n:>6,d} │ {ret*100:>+7.2f}% │ {ppos:>7.1f}% │ {dd:>+7.2f}% │ {edge:>6s}")

# Do existing meta_signals capture squeeze?
# Check: when compression < 0.3, what signals fire?
print(f"\n  ── Signal profile during Squeeze ──")
heads = ['p_long_entry', 'p_swing_exit', 'p_pullback_depth', 'p_short_entry',
         'p_bounce_height', 'p_trend_reversal']
for h in heads:
    sq_mean = sq[h].mean()
    nsq_mean = nsq[h].mean()
    diff = sq_mean - nsq_mean
    star = "★" if abs(diff) > 0.02 else ""
    print(f"    {h:>22s}: squeeze={sq_mean:.4f}  normal={nsq_mean:.4f}  diff={diff:+.4f} {star}")

print(f"\n  CONCLUSION 9.4: ", end="")
sq_ret = sq['fwd_return_10d'].mean()
if abs(sq_ret - nsq['fwd_return_10d'].mean()) < 0.003:
    print("Squeeze alone has NO directional edge. It needs a directional filter.")
    print("  → Current heads already provide that filter. No new head needed.")
else:
    print(f"Squeeze has edge: {sq_ret*100:+.2f}% vs {nsq['fwd_return_10d'].mean()*100:+.2f}%")

# ═══════════════════════════════════════════════════════════════
# 9.5: SHORT_ENTRY FOR SPECULATIVE
# ═══════════════════════════════════════════════════════════════
print(f"\n{'═' * 95}")
print(f"  9.5: SHORT_ENTRY — Viability as Speculative SHORT signal")
print(f"{'═' * 95}")

# Context: BEAR + FLAT only (matching training)
bear_flat = valid[valid['regime'].isin(['BEAR', 'FLAT'])].copy()
print(f"\n  BEAR+FLAT context: {len(bear_flat):,d} rows")

# Different thresholds
print(f"\n  ── P(short_entry) thresholds → forward performance ──")
print(f"  {'Threshold':>12s} │ {'N':>7s} │ {'Ret 10d':>8s} │ {'Ret 20d':>8s} │ {'P(ret<0)10d':>12s} │ {'MaxDD 10d':>10s}")
print(f"  {'─'*70}")
for thr in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
    mask = bear_flat['p_short_entry'] >= thr
    n = mask.sum()
    if n < 10:
        print(f"  {thr:>12.2f} │ {n:>7,d} │ {'n/a':>8s} │ {'n/a':>8s} │ {'n/a':>12s} │ {'n/a':>10s}")
        continue
    s = bear_flat[mask]
    r10 = s['fwd_return_10d'].mean() * 100
    r20 = s['fwd_return_20d'].mean() * 100
    pneg = (s['fwd_return_10d'] < 0).mean() * 100
    dd = s['fwd_max_dd_10d'].mean() * 100
    print(f"  {thr:>12.2f} │ {n:>7,d} │ {r10:>+7.2f}% │ {r20:>+7.2f}% │ {pneg:>11.1f}% │ {dd:>+9.2f}%")

# Composite signal: short_entry + swing_exit both high
print(f"\n  ── Composite SHORT signals ──")
composites = [
    ("short>0.6 + swing_exit>0.6", lambda d: (d['p_short_entry']>0.6) & (d['p_swing_exit']>0.6)),
    ("short>0.6 + pullback>0.6", lambda d: (d['p_short_entry']>0.6) & (d['p_pullback_depth']>0.6)),
    ("short>0.6 + RSI>65", lambda d: (d['p_short_entry']>0.6) & (d['rsi_value']>65)),
    ("short>0.6 + σ_tide>1.5", lambda d: (d['p_short_entry']>0.6) & (d['sigma_tide']>1.5)),
    ("short>0.6 + KV<0", lambda d: (d['p_short_entry']>0.6) & (d['kalman_velocity']<0)),
]
print(f"  {'Signal':>35s} │ {'N':>6s} │ {'Ret 10d':>8s} │ {'P(neg)':>8s} │ {'MaxDD':>8s}")
print(f"  {'─'*75}")
for name, fn in composites:
    mask = fn(bear_flat)
    n = mask.sum()
    if n < 10:
        continue
    s = bear_flat[mask]
    print(f"  {name:>35s} │ {n:>6,d} │ {s['fwd_return_10d'].mean()*100:>+7.2f}% │ {(s['fwd_return_10d']<0).mean()*100:>7.1f}% │ {s['fwd_max_dd_10d'].mean()*100:>+7.2f}%")

# Per ticker
print(f"\n  ── Per-ticker short_entry > 0.60 in BEAR+FLAT ──")
print(f"  {'Ticker':>6s} │ {'N':>5s} │ {'Ret 10d':>8s} │ {'Ret 20d':>8s} │ {'P(neg)':>8s} │ {'Viable?':>8s}")
print(f"  {'─'*55}")
for tk in sorted(bear_flat['ticker'].unique()):
    t = bear_flat[(bear_flat['ticker']==tk) & (bear_flat['p_short_entry']>=0.60)]
    if len(t) < 5:
        continue
    r10 = t['fwd_return_10d'].mean()*100
    r20 = t['fwd_return_20d'].mean()*100
    pneg = (t['fwd_return_10d']<0).mean()*100
    viable = "✅ YES" if r10 < -0.5 and pneg > 55 else "⚠️ WEAK" if pneg > 50 else "❌ NO"
    print(f"  {tk:>6s} │ {len(t):>5d} │ {r10:>+7.2f}% │ {r20:>+7.2f}% │ {pneg:>7.1f}% │ {viable:>8s}")

store.close()
print(f"\n{'═' * 95}")
print(f"  9.4 + 9.5 EVALUATION COMPLETE")
print(f"{'═' * 95}")
