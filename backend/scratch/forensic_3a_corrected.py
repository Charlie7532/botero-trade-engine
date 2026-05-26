"""Quick run of corrected 3A only — to get the honest metrics."""
import sys; sys.path.insert(0, '/root/botero-trade')
from dotenv import load_dotenv; load_dotenv('/root/botero-trade/.env')
from backend.scripts.forensic_signal_tape import load_tape, HEAD_EVAL, HEADS, evaluate_signal, apply_context_filter
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd

store = TimescaleDataStore()
df = load_tape(store)
print(f"Loaded: {len(df):,d} rows")

print(f"\n{'═' * 110}")
print(f"  3A CORRECTED: Each head measured with ITS label and IN ITS context")
print(f"{'═' * 110}")

print(f"\n  {'Head':20s} │ {'Thr':>5s} │ {'Context':>20s} │ {'N(ctx)':>8s} │ {'N>Thr':>7s} │ {'WR%':>6s} │ {'Base%':>6s} │ {'Edge':>7s} │ {'Label':>20s}")
print(f"  {'─'*115}")

for head in HEADS:
    pcol = f'p_{head}'
    fwd_col, direction, threshold, context = HEAD_EVAL[head]
    
    # Apply context filter
    ctx_df = apply_context_filter(df, context)
    valid = ctx_df[ctx_df[fwd_col].notna()].copy()
    
    # Evaluate correctness
    correct = valid.apply(lambda r: evaluate_signal(r, head), axis=1)
    base_rate = correct.mean() * 100
    
    # Signal triggered
    triggered = valid[pcol] >= threshold
    n_triggered = triggered.sum()
    
    if n_triggered > 0:
        wr = correct[triggered].mean() * 100
    else:
        wr = 0
    
    edge = wr - base_rate
    ctx_name = context or 'ALL'
    
    label_desc = f"{fwd_col} {direction}"
    
    print(f"  {head:20s} │ {threshold:5.2f} │ {ctx_name:>20s} │ {len(valid):>8,d} │ {n_triggered:>7,d} │ {wr:5.1f}% │ {base_rate:5.1f}% │ {edge:+6.1f}% │ {label_desc:>20s}")

# Also show the PREVIOUS (wrong) measurement for comparison
print(f"\n  ── COMPARISON: Previous (wrong) vs Corrected ──")
print(f"  {'Head':20s} │ {'OLD label':>25s} │ {'NEW label':>25s} │ {'OLD WR':>7s} │ {'NEW WR':>7s}")
print(f"  {'─'*95}")

OLD_EVAL = {
    'long_entry':     ('fwd_return_20d', 'positive', 0.80),
    'swing_exit':     ('fwd_return_10d', 'negative', 0.80),
    'pullback_depth': ('fwd_max_dd_5d',  'below_-2pct', 0.80),
    'trend_reversal': ('fwd_return_20d', 'negative', 0.80),
    'short_entry':    ('fwd_return_20d', 'negative', 0.50),
    'short_cover':    ('fwd_return_10d', 'positive', 0.75),
    'bounce_height':  ('fwd_max_runup_5d', 'above_2pct', 0.80),
    'trend_recovery': ('fwd_return_20d', 'positive', 0.80),
}

for head in HEADS:
    pcol = f'p_{head}'
    
    # OLD: no context, old label
    old_fwd, old_dir, old_thr = OLD_EVAL[head]
    old_valid = df[df[old_fwd].notna()].copy()
    old_correct = old_valid.apply(lambda r: r.get(old_fwd, 0) > 0 if old_dir == 'positive' else 
                                            r.get(old_fwd, 0) < 0 if old_dir == 'negative' else
                                            r.get(old_fwd, 0) < -0.02 if old_dir == 'below_-2pct' else
                                            r.get(old_fwd, 0) > 0.02, axis=1)
    old_trig = old_valid[old_valid[pcol] >= old_thr]
    old_wr = old_correct[old_valid[pcol] >= old_thr].mean() * 100 if len(old_trig) > 0 else 0
    
    # NEW: with context, correct label
    new_fwd, new_dir, new_thr, ctx = HEAD_EVAL[head]
    new_ctx = apply_context_filter(df, ctx)
    new_valid = new_ctx[new_ctx[new_fwd].notna()].copy()
    new_correct = new_valid.apply(lambda r: evaluate_signal(r, head), axis=1)
    new_trig = new_valid[new_valid[pcol] >= new_thr]
    new_wr = new_correct[new_valid[pcol] >= new_thr].mean() * 100 if len(new_trig) > 0 else 0
    
    old_label = f"{old_fwd} {old_dir}"
    new_label = f"{new_fwd} {new_dir}"
    delta = new_wr - old_wr
    marker = "🔴 WRONG before" if abs(delta) > 5 else "✅ same"
    
    print(f"  {head:20s} │ {old_label:>25s} │ {new_label:>25s} │ {old_wr:6.1f}% │ {new_wr:6.1f}% {marker}")

store.close()
print(f"\n{'═' * 110}")
print(f"  CORRECTED MEASUREMENT COMPLETE")
print(f"{'═' * 110}")
