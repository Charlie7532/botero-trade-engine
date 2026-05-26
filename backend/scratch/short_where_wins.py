import sys; sys.path.insert(0, '/root/botero-trade')
from dotenv import load_dotenv; load_dotenv('/root/botero-trade/.env')
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
import pandas as pd, numpy as np

store = TimescaleDataStore()
tape = pd.read_sql('SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp', store.engine)
bf = tape[tape['regime'].isin(['BEAR','FLAT']) & tape['fwd_return_10d'].notna()].copy()

print('═' * 105)
print('  ¿DÓNDE GANA EL ENTRENAMIENTO SHORT? — Gradiente monotónico = señal real')
print('═' * 105)

hdr = (f"\n  {'Ticker':>6s} │ {'Base%':>6s} │ {'P≥0.50':>7s} │ {'P≥0.55':>7s} │ "
       f"{'P≥0.60':>7s} │ {'P≥0.65':>7s} │ {'P≥0.70':>7s} │ {'Monot':>5s} │ "
       f"{'MaxEdge':>8s} │ Veredicto")
print(hdr)
print(f"  {'─'*100}")

for tk in sorted(bf['ticker'].unique()):
    t = bf[bf['ticker'] == tk]
    base = (t['fwd_return_10d'] < 0).mean() * 100

    wrs, ns = [], []
    for thr in [0.50, 0.55, 0.60, 0.65, 0.70]:
        s = t[t['p_short_entry'] >= thr]
        n = len(s)
        if n >= 5:
            wrs.append((s['fwd_return_10d'] < 0).mean() * 100)
            ns.append(n)
        else:
            wrs.append(None)
            ns.append(0)

    valid_wrs = [w for w in wrs if w is not None]
    monotonic = (all(valid_wrs[i] <= valid_wrs[i+1] for i in range(len(valid_wrs)-1))
                 if len(valid_wrs) >= 3 else False)
    max_edge = max([(w - base) for w in valid_wrs]) if valid_wrs else 0

    if monotonic and max_edge > 15:
        verdict = '🟢 GANA'
    elif max_edge > 10:
        verdict = '🟡 PARCIAL'
    elif max_edge > 5:
        verdict = '🟠 DÉBIL'
    else:
        verdict = '🔴 NO'

    wr_s = [f'{w:5.1f}%' if w is not None else '  n/a' for w in wrs]
    mono_s = '  ✅' if monotonic else '  ❌'
    print(f"  {tk:>6s} │ {base:5.1f}% │ {wr_s[0]:>7s} │ {wr_s[1]:>7s} │ "
          f"{wr_s[2]:>7s} │ {wr_s[3]:>7s} │ {wr_s[4]:>7s} │ {mono_s:>5s} │ "
          f"{max_edge:>+7.1f}% │ {verdict}")

# Ranking by short return
print(f"\n  ── Ranking por retorno SHORT (P≥0.60, BEAR+FLAT) ──")
print(f"  {'Ticker':>6s} │ {'N':>5s} │ {'Ret 10d':>8s} │ {'Ret 20d':>8s} │ "
      f"{'MaxDD':>7s} │ {'P(neg)':>7s} │ Rank")
print(f"  {'─'*65}")

ranked = []
for tk in sorted(bf['ticker'].unique()):
    t = bf[(bf['ticker'] == tk) & (bf['p_short_entry'] >= 0.60)]
    if len(t) < 10:
        continue
    ranked.append((tk, len(t), t['fwd_return_10d'].mean(),
                   t['fwd_return_20d'].mean(), t['fwd_max_dd_10d'].mean(),
                   (t['fwd_return_10d'] < 0).mean()))

ranked.sort(key=lambda x: x[2])
for i, (tk, n, r10, r20, dd, pneg) in enumerate(ranked):
    print(f"  {tk:>6s} │ {n:>5d} │ {r10*100:>+7.2f}% │ {r20*100:>+7.2f}% │ "
          f"{dd*100:>+6.2f}% │ {pneg*100:>5.1f}% │ #{i+1}")

store.close()
print(f"\n{'═' * 105}")
print(f"  DONE")
print(f"{'═' * 105}")
