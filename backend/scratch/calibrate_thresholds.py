"""
Per-Ticker Threshold Calibration — Using CORRECTED labels
==========================================================
For each head × ticker: find the threshold that maximizes edge.
Only consider heads that matter (WR > 60%).
"""
import sys; sys.path.insert(0, '/root/botero-trade')
from dotenv import load_dotenv; load_dotenv('/root/botero-trade/.env')
from backend.scripts.forensic_signal_tape import (
    load_tape, HEAD_EVAL, HEADS, evaluate_signal, apply_context_filter
)
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd, numpy as np

store = TimescaleDataStore()
df = load_tape(store)
print(f"Loaded: {len(df):,d} rows")

# Only calibrate heads worth calibrating (edge > 5%)
CALIBRATE_HEADS = ['long_entry', 'swing_exit', 'pullback_depth', 'short_entry',
                   'short_cover', 'bounce_height']

THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]

print(f"\n{'═' * 100}")
print(f"  PER-TICKER THRESHOLD CALIBRATION (corrected labels)")
print(f"{'═' * 100}")

results = []

for head in CALIBRATE_HEADS:
    pcol = f'p_{head}'
    fwd_col, direction, current_thr, context = HEAD_EVAL[head]
    
    print(f"\n  ── {head} (current thr={current_thr}, label={fwd_col} {direction}) ──")
    print(f"  {'Ticker':>6s} │ {'Current':>7s} │ {'CurrWR':>7s} │ {'Optimal':>7s} │ {'OptWR':>7s} │ {'OptN':>6s} │ {'Δ WR':>6s} │ {'Edge':>7s} │ Verdict")
    print(f"  {'─'*85}")
    
    for ticker in sorted(df['ticker'].unique()):
        # Apply context filter
        ticker_df = df[df['ticker'] == ticker]
        ctx_df = apply_context_filter(ticker_df, context)
        valid = ctx_df[ctx_df[fwd_col].notna()].copy()
        
        if len(valid) < 50:
            continue
        
        correct = valid.apply(lambda r: evaluate_signal(r, head), axis=1)
        base_rate = correct.mean() * 100
        
        # Current threshold
        curr_trig = valid[pcol] >= current_thr
        curr_wr = correct[curr_trig].mean() * 100 if curr_trig.sum() > 0 else 0
        
        # Try all thresholds
        best_thr, best_wr, best_n, best_edge = current_thr, curr_wr, curr_trig.sum(), curr_wr - base_rate
        for thr in THRESHOLDS:
            trig = valid[pcol] >= thr
            n = trig.sum()
            if n < 5:
                continue
            wr = correct[trig].mean() * 100
            edge = wr - base_rate
            # Optimize for edge * sqrt(N) — balance WR improvement with sample size
            score = edge * np.sqrt(n)
            best_score = best_edge * np.sqrt(best_n) if best_n > 0 else 0
            if score > best_score:
                best_thr, best_wr, best_n, best_edge = thr, wr, n, edge
        
        delta = best_wr - curr_wr
        verdict = "★ IMPROVE" if delta > 3 else ("→ keep" if abs(delta) <= 3 else "↓ worse")
        
        print(f"  {ticker:>6s} │ {current_thr:>7.2f} │ {curr_wr:>6.1f}% │ {best_thr:>7.2f} │ {best_wr:>6.1f}% │ {best_n:>6,d} │ {delta:>+5.1f}% │ {best_edge:>+6.1f}% │ {verdict}")
        
        results.append({
            'head': head, 'ticker': ticker,
            'current_thr': current_thr, 'current_wr': curr_wr,
            'optimal_thr': best_thr, 'optimal_wr': best_wr,
            'optimal_n': best_n, 'delta_wr': delta, 'edge': best_edge,
        })

# Summary
print(f"\n{'═' * 100}")
print(f"  SUMMARY — Tickers where optimal ≠ current")
print(f"{'═' * 100}")

rdf = pd.DataFrame(results)
improved = rdf[rdf['delta_wr'] > 3]
print(f"\n  Tickers with WR improvement > 3%: {len(improved)} of {len(rdf)}")
if len(improved) > 0:
    print(f"\n  {'Head':>16s} │ {'Ticker':>6s} │ {'Current→Optimal':>15s} │ {'WR change':>10s}")
    print(f"  {'─'*55}")
    for _, row in improved.sort_values('delta_wr', ascending=False).iterrows():
        print(f"  {row['head']:>16s} │ {row['ticker']:>6s} │ {row['current_thr']:.2f} → {row['optimal_thr']:.2f} │ {row['delta_wr']:>+9.1f}%")

# Should we auto-calibrate?
avg_delta = rdf['delta_wr'].mean()
print(f"\n  Average WR change if we adopt optimal thresholds: {avg_delta:+.2f}%")
print(f"  Conclusion: {'WORTH IT — auto-calibrate' if avg_delta > 2 else 'MARGINAL — keep defaults' if avg_delta > 0 else 'NOT WORTH IT'}")

store.close()
print(f"\n{'═' * 100}")
print(f"  CALIBRATION COMPLETE")
print(f"{'═' * 100}")
