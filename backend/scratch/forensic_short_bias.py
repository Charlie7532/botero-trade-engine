"""
FORENSIC DEEP DIVE — SHORT Head Design Flaws
=============================================
Forensic team (LdP) + Data Science team (Simons)

Questions to answer with DATA:
1. Is the regime classifier contaminating short training?
2. Is 20d the wrong horizon for shorts? (crashes are fast)
3. Would MAX DRAWDOWN labels work better than terminal return?
4. What context filter produces the best discrimination?
5. What changes can we make WITHOUT touching long_entry/pullback_depth/bounce_height?
"""
import sys; sys.path.insert(0, '/root/botero-trade')
from dotenv import load_dotenv; load_dotenv('/root/botero-trade/.env')
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd
import numpy as np
from scipy import stats

def p(title):
    print(f"\n{'═' * 90}")
    print(f"  {title}")
    print(f"{'═' * 90}")

store = TimescaleDataStore()
tape = pd.read_sql('SELECT * FROM engine.signal_tape', store.engine)

p("EXPERIMENT 1: ¿Por qué BEAR tiene drift positivo?")
print("  El clasificador de régimen usa TSI momentum. Veamos qué pasa dentro del BEAR:")

bear = tape[tape['regime'] == 'BEAR'].copy()
bear['sigma_bucket'] = pd.cut(bear['sigma_tide'], bins=[-10,-2,-1,-0.5,0,0.5,1,10], 
                               labels=['<-2','-2:-1','-1:-0.5','-0.5:0','0:0.5','0.5:1','>1'])

print(f"\n  BEAR regime breakdown by sigma_tide:")
print(f"  {'σ_tide bucket':>15s} │ {'N':>6s} │ {'fwd_20d':>8s} │ {'fwd_10d':>8s} │ {'P(down 20d)':>11s} │ {'MaxDD 10d':>9s}")
print(f"  {'─'*75}")
for bucket in ['<-2','-2:-1','-1:-0.5','-0.5:0','0:0.5','0.5:1','>1']:
    sub = bear[bear['sigma_bucket'] == bucket]
    if len(sub) < 50:
        continue
    fwd20 = sub['fwd_return_20d'].mean()
    fwd10 = sub['fwd_return_10d'].mean()
    p_down = (sub['fwd_return_20d'] < 0).mean()
    maxdd = sub['fwd_max_dd_10d'].mean()
    print(f"  {bucket:>15s} │ {len(sub):>6,d} │ {fwd20:>+8.4f} │ {fwd10:>+8.4f} │ {p_down*100:>10.1f}% │ {maxdd:>+9.4f}")

# BEAR with sigma_tide < 0 = actually bearish?
bear_real = bear[bear['sigma_tide'] < 0]
bear_fake = bear[bear['sigma_tide'] >= 0]
print(f"\n  BEAR + σ_tide < 0 (truly bearish): N={len(bear_real):,d}  fwd_20d={bear_real['fwd_return_20d'].mean():+.4f}  P(down)={(bear_real['fwd_return_20d'] < 0).mean()*100:.1f}%")
print(f"  BEAR + σ_tide ≥ 0 (bouncing bear): N={len(bear_fake):,d}  fwd_20d={bear_fake['fwd_return_20d'].mean():+.4f}  P(down)={(bear_fake['fwd_return_20d'] < 0).mean()*100:.1f}%")

p("EXPERIMENT 2: Horizonte óptimo para SHORT")
print("  Los crashes son rápidos. ¿20d es demasiado largo?")

print(f"\n  {'Context':>25s} │ {'Horizon':>7s} │ {'P(down)':>7s} │ {'mean ret':>8s} │ {'Separation':>10s}")
print(f"  {'─'*75}")

# Test different contexts × horizons
contexts = {
    'ALL': tape,
    'BEAR+FLAT': tape[tape['regime'].isin(['BEAR','FLAT'])],
    'BEAR only': tape[tape['regime'] == 'BEAR'],
    'σ_tide < -0.5': tape[tape['sigma_tide'] < -0.5],
    'σ_tide < 0': tape[tape['sigma_tide'] < 0],
    'RSI < 50': tape[tape['rsi_value'] < 50],
    'BEAR + σ<0': tape[(tape['regime']=='BEAR') & (tape['sigma_tide'] < 0)],
}

for ctx_name, ctx_df in contexts.items():
    for horizon, ret_col in [(5,'fwd_return_5d'),(10,'fwd_return_10d'),(20,'fwd_return_20d')]:
        p_down = (ctx_df[ret_col] < 0).mean()
        mean_ret = ctx_df[ret_col].mean()
        # Separation: how different are down vs up returns?
        down_mean = ctx_df[ctx_df[ret_col] < 0][ret_col].mean()
        up_mean = ctx_df[ctx_df[ret_col] > 0][ret_col].mean()
        sep = abs(down_mean) - abs(up_mean)
        
        if horizon == 20:
            print(f"  {ctx_name:>25s} │ {horizon:>5d}d │ {p_down*100:>6.1f}% │ {mean_ret:>+8.4f} │ {sep:>+10.4f}")

p("EXPERIMENT 3: ¿MAX DRAWDOWN en vez de retorno terminal?")
print("  Un stock puede caer -8% en 5d y recuperar a +2% en 20d.")
print("  Terminal return dice 'no cayó'. MaxDD dice 'sí cayó -8%'.")

# Compare labels: terminal return vs max drawdown
for ctx_name, ctx_df in [('BEAR+FLAT', tape[tape['regime'].isin(['BEAR','FLAT'])]),
                          ('BEAR only', tape[tape['regime']=='BEAR']),
                          ('σ<0', tape[tape['sigma_tide']<0])]:
    # Terminal return label (current)
    term_pos = (ctx_df['fwd_return_20d'] < 0).mean()
    # MaxDD label (proposed): did it drop > 3% at any point in 10d?
    dd_pos = (ctx_df['fwd_max_dd_10d'] < -0.03).mean()
    # MaxDD label (proposed): did it drop > 2% at any point in 5d?
    dd5_pos = (ctx_df['fwd_max_dd_5d'] < -0.02).mean()
    
    print(f"\n  {ctx_name}:")
    print(f"    Terminal return 20d < 0:     {term_pos*100:.1f}% positive (current short_entry)")
    print(f"    MaxDD 10d < -3%:             {dd_pos*100:.1f}% positive")
    print(f"    MaxDD 5d < -2%:              {dd5_pos*100:.1f}% positive")

p("EXPERIMENT 4: ¿Qué features predicen mejor las CAÍDAS vs SUBIDAS?")
print("  Correlación de cada feature con fwd_max_dd_10d (drawdown = lo que importa para shorts)")

features = ['sigma_tide','sigma_current','sigma_wave','tide_slope','current_slope','wave_slope',
            'kalman_velocity','rsi_value','fear_level','compression_ratio','vol_up_down_ratio',
            'p_long_entry','p_short_entry','p_swing_exit','p_pullback_depth']

print(f"\n  {'Feature':>22s} │ {'corr(fwd_10d)':>12s} │ {'corr(max_dd_10d)':>15s} │ {'Better for':>12s}")
print(f"  {'─'*70}")
for feat in features:
    sub = tape[[feat,'fwd_return_10d','fwd_max_dd_10d']].dropna()
    r_ret = sub[feat].corr(sub['fwd_return_10d'])
    r_dd = sub[feat].corr(sub['fwd_max_dd_10d'])
    better = 'DD' if abs(r_dd) > abs(r_ret) else 'Return'
    star = '★' if abs(r_dd) > 0.05 else ''
    print(f"  {feat:>22s} │ {r_ret:>+12.4f} │ {r_dd:>+15.4f} │ {better:>10s} {star}")

p("EXPERIMENT 5: Simulación de short_entry con diferentes diseños")
print("  Entrenamos con p_short_entry actual Y evaluamos alternativas")

# Design A: current (terminal return 20d, BEAR+FLAT)
ctx_a = tape[tape['regime'].isin(['BEAR','FLAT'])]
# Design B: MaxDD 10d > 3%, BEAR only  
ctx_b = tape[tape['regime'] == 'BEAR']
# Design C: sigma_tide < 0 (momentum-based, regime-agnostic)
ctx_c = tape[tape['sigma_tide'] < 0]

for design, ctx, label_col, label_thr, label_desc in [
    ('A (current)', ctx_a, 'fwd_return_20d', 0, 'ret_20d < 0'),
    ('B (BEAR+DD)', ctx_b, 'fwd_max_dd_10d', -0.03, 'maxDD_10d < -3%'),
    ('C (σ<0+DD)', ctx_c, 'fwd_max_dd_10d', -0.03, 'maxDD_10d < -3%'),
    ('D (σ<0+ret5d)', ctx_c, 'fwd_return_5d', 0, 'ret_5d < 0'),
]:
    labels = (ctx[label_col] < label_thr) if label_thr <= 0 else (ctx[label_col] < 0)
    pos_rate = labels.mean()
    n = len(ctx)
    
    # Can p_short_entry discriminate this alternative label?
    if 'p_short_entry' in ctx.columns:
        high_p = ctx[ctx['p_short_entry'] > 0.6]
        low_p = ctx[ctx['p_short_entry'] < 0.4]
        
        if label_thr <= 0:
            wr_high = (high_p[label_col] < label_thr).mean() if len(high_p) > 0 else 0
            wr_low = (low_p[label_col] < label_thr).mean() if len(low_p) > 0 else 0
        else:
            wr_high = (high_p[label_col] < 0).mean() if len(high_p) > 0 else 0
            wr_low = (low_p[label_col] < 0).mean() if len(low_p) > 0 else 0
        
        spread = wr_high - wr_low
        print(f"\n  Design {design}:")
        print(f"    Label: {label_desc} │ Context: {n:,d} obs │ Positive: {pos_rate*100:.1f}%")
        print(f"    P>0.6 WR: {wr_high*100:.1f}% ({len(high_p):,d} obs) │ P<0.4 WR: {wr_low*100:.1f}% ({len(low_p):,d} obs) │ Spread: {spread*100:+.1f}%")

p("EXPERIMENT 6: swing_exit — ¿Qué barrier funciona mejor?")
print("  Contexto actual: BULL + sigma_tide > 0")
ctx_se = tape[(tape['regime']=='BULL') & (tape['sigma_tide'] > 0)]
n_se = len(ctx_se)

print(f"\n  Context: BULL + σ>0 │ N = {n_se:,d}")
print(f"\n  {'Barrier Config':>25s} │ {'Pos%':>5s} │ {'P_se>0.7 WR':>11s} │ {'P_se<0.3 WR':>11s} │ {'Spread':>7s}")
print(f"  {'─'*75}")

barrier_configs = [
    ('DD>2% in 10d (current)', ctx_se['fwd_max_dd_10d'] < -0.02),
    ('DD>1.5% in 10d', ctx_se['fwd_max_dd_10d'] < -0.015),
    ('DD>1% in 10d', ctx_se['fwd_max_dd_10d'] < -0.01),
    ('DD>2% in 5d', ctx_se['fwd_max_dd_5d'] < -0.02),
    ('DD>1.5% in 5d', ctx_se['fwd_max_dd_5d'] < -0.015),
    ('DD>1% in 5d', ctx_se['fwd_max_dd_5d'] < -0.01),
    ('Ret<0 in 10d', ctx_se['fwd_return_10d'] < 0),
    ('Ret<-1% in 10d', ctx_se['fwd_return_10d'] < -0.01),
]

for desc, label_mask in barrier_configs:
    pos = label_mask.mean()
    high_p = ctx_se[ctx_se['p_swing_exit'] > 0.7]
    low_p = ctx_se[ctx_se['p_swing_exit'] < 0.3]
    wr_h = label_mask[high_p.index].mean() if len(high_p) > 0 else 0
    wr_l = label_mask[low_p.index].mean() if len(low_p) > 0 else 0
    spread = wr_h - wr_l
    print(f"  {desc:>25s} │ {pos*100:>4.1f}% │ {wr_h*100:>10.1f}% │ {wr_l*100:>10.1f}% │ {spread*100:>+6.1f}%")

p("EXPERIMENT 7: ¿Qué NO debemos tocar? (Validación de los heads buenos)")
print("  Confirmación de que long_entry, pullback_depth, bounce_height son sólidos")

for head, ret_col, direction in [
    ('p_long_entry', 'fwd_return_20d', 'positive'),
    ('p_pullback_depth', 'fwd_max_dd_5d', 'negative'),
    ('p_bounce_height', 'fwd_max_runup_5d', 'positive'),
]:
    vals = tape[[head, ret_col]].dropna()
    q = pd.qcut(vals[head], 10, labels=False, duplicates='drop')
    vals['decile'] = q
    
    decile_means = vals.groupby('decile')[ret_col].mean()
    d1 = decile_means.iloc[0]
    d10 = decile_means.iloc[-1]
    spread = d10 - d1
    
    # Check if spread is in the right direction
    if direction == 'positive':
        correct = spread > 0
    else:
        correct = spread < 0
    
    status = '✅ SOLID' if correct and abs(spread) > 0.01 else '⚠️ WEAK'
    print(f"  {head:>22s} │ D1={d1:+.4f} D10={d10:+.4f} │ spread={spread:+.4f} │ {status}")

store.close()
print(f"\n{'═' * 90}")
print(f"  FORENSIC COMPLETE")
print(f"{'═' * 90}")
