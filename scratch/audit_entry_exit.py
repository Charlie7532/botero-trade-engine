#!/usr/bin/env python3
"""
AUDITOR DE ENTRY/EXIT — Revalidación de señales de entrada y salida en producción
=================================================================================
Usa EXCLUSIVAMENTE los bins calibrados del proyecto (vix_lookup.py fact store),
no umbrales crudos ad hoc.

D1 (VIX nivel):       CRISIS_SPIKE = VIX ≥ 25.92
D2 (velocidad Δ3d):   FAST_CRUSH_3D / DECELERATING_DOWN_3D = VIX cayendo
D3 (vol_norm 2d/10d): caos = VOL_ACCELERATING_EXPANSION / VOL_PEAK_DECELERATION

ENTRADA (producción): CRISIS_SPIKE + D2 ∈ {FAST_CRUSH, DECELERATING} + D3 ∉ caos
SALIDA (producción):  D2 flip ↑  y/o  D3 expansión (sin zigzag)

Tareas:
1. ENTRADA: ¿el filtro D2+D3 elimina las peores trades (2008-09-29, 2009-02-06,
   2020-03-06)?
2. SALIDA: 3 estrategias — (a) D2 flip ↑, (b) hold fijo 20d, (c) D3 expansión + D2 flip ↑
3. Comparar retorno compuesto, max drawdown, win rate
4. Recomendar entry+exit óptima
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# ── Umbrales calibrados (VIX) ──────────────────────────────────────────────
D1_EDGES  = [12.74, 15.46, 17.61, 20.499001000000007, 25.92]
D1_LABELS = ['DEEP_COMPLACENCY', 'LOW_VOL', 'MODERATE_VOL',
             'HIGH_VOL', 'ELEVATED_PANIC', 'CRISIS_SPIKE']
D2_EDGES  = [-1.8054944999999993, -0.6600000000000001,
             0.4900000000000001, 1.7599999999999998]
D2_LABELS = ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D',
             'ACCELERATING_UP_3D', 'FAST_SPIKE_3D']
D3_EDGES  = [0.2859356636215917, 0.460455625825507, 0.7474005777370026]
D3_LABELS = ['VOL_EXTREME_SQUEEZE', 'VOL_MODERATE_COMPRESSION',
             'VOL_NEUTRAL_BASELINE', 'VOL_ACCELERATING_EXPANSION',
             'VOL_PEAK_DECELERATION']

D2_DOWN  = {'FAST_CRUSH_3D', 'DECELERATING_DOWN_3D'}   # VIX cayendo  → señal de compra
D2_UP    = {'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'}     # VIX subiendo → señal de venta
D3_CHAOS = {'VOL_ACCELERATING_EXPANSION', 'VOL_PEAK_DECELERATION'}  # "caos" (expansión)


def classify(value, edges, labels):
    for i, e in enumerate(edges):
        if value < e:
            return labels[i]
    return labels[-1]


def build_frame():
    store = TimescaleDataStore()
    vix = store.load_bars("VIX", "1d")["close"].copy()
    spy = store.load_bars("SPY", "1d")["close"].copy()
    store.close()
    vix.index = pd.to_datetime(vix.index)
    spy.index = pd.to_datetime(spy.index)
    common = vix.index.intersection(spy.index)
    vix = vix.loc[common]
    spy = spy.loc[common]

    df = pd.DataFrame(index=common)
    df["vix"] = vix
    df["spy"] = spy
    df["vel"] = df["vix"].diff(3)                       # D2 (velocidad Δ3d)
    vol2 = df["vix"].rolling(2).std()
    vol10 = df["vix"].rolling(10).std().replace(0, np.nan)
    df["vol_norm"] = (vol2 / vol10).fillna(1.0)         # D3 (2d/10d)

    df["D1"] = df["vix"].apply(lambda v: classify(v, D1_EDGES, D1_LABELS))
    df["D2"] = df["vel"].apply(lambda v: classify(v, D2_EDGES, D2_LABELS))
    df["D3"] = df["vol_norm"].apply(lambda v: classify(v, D3_EDGES, D3_LABELS))

    # Flip literal (para sensibilidad): D2 cambió de signo vs 3 días atrás
    df["vel_prev3"] = df["vel"].shift(3)
    df["flip_down_literal"] = (df["vel"] < 0) & (df["vel_prev3"] >= 0)
    df["flip_up_literal"]   = (df["vel"] > 0) & (df["vel_prev3"] <= 0)

    # Máscaras de entrada/salida
    df["crisis"] = df["D1"] == "CRISIS_SPIKE"
    df["d2_down"] = df["D2"].isin(D2_DOWN)
    df["d2_up"] = df["D2"].isin(D2_UP)
    df["d3_chaos"] = df["D3"].isin(D3_CHAOS)
    return df


def find_entries(df, mode, min_sep=10):
    """Devuelve lista de índices de entrada según el modo.

    mode: 'crisis'      = CRISIS_SPIKE solo
          'd2'          = CRISIS_SPIKE + D2 flip ↓
          'full'        = CRISIS_SPIKE + D2 flip ↓ + D3 ≠ caos
          'full_literal'= CRISIS_SPIKE + flip literal ↓ + D3 ≠ caos
    """
    idx = list(df.index)
    n = len(idx)
    entries = []
    last = -10**9
    for i in range(n):
        if i - last < min_sep:
            continue
        row = df.iloc[i]
        if not row["crisis"]:
            continue
        if mode == "crisis":
            ok = True
        elif mode == "d2":
            ok = row["d2_down"]
        elif mode == "full":
            ok = row["d2_down"] and (not row["d3_chaos"])
        elif mode == "full_literal":
            ok = row["flip_down_literal"] and (not row["d3_chaos"])
        else:
            raise ValueError(mode)
        if ok:
            entries.append(i)
            last = i
    return entries


def fwd_ret(df, i, hold):
    """Retorno forward de SPY en 'hold' días de trading desde el índice i."""
    n = len(df)
    j = min(i + hold, n - 1)
    return df["spy"].iloc[j] / df["spy"].iloc[i] - 1


# ── PARTE 1: ENTRADA ────────────────────────────────────────────────────────
def audit_entry(df):
    print("=" * 96)
    print("  PARTE 1 — ENTRADA: CRISIS_SPIKE + D2 flip ↓ + D3 filtro")
    print("=" * 96)
    print(f"\n  Datos: {len(df)} barras alineadas VIX∩SPY  "
          f"({df.index.min().date()} → {df.index.max().date()})")
    n_crisis = int(df["crisis"].sum())
    print(f"  Barras CRISIS_SPIKE (VIX ≥ 25.92): {n_crisis}  "
          f"({n_crisis/len(df)*100:.1f}% del total)")
    print(f"  Barras CRISIS_SPIKE + D2↓: {int((df['crisis'] & df['d2_down']).sum())}")
    print(f"  Barras CRISIS_SPIKE + D2↓ + D3≠caos: "
          f"{int((df['crisis'] & df['d2_down'] & ~df['d3_chaos']).sum())}")

    print("\n  ── Forward 20d SPY por definición de entrada (min-sep 10d) ──")
    print(f"  {'Entrada':<42} {'N':>4} {'media':>8} {'mediana':>8} {'win':>5} "
          f"{'min':>8} {'P10':>8} {'max':>8}")
    results = {}
    for mode, label in [
        ("crisis", "CRISIS_SPIKE solo (baseline)"),
        ("d2", "CRISIS_SPIKE + D2 flip ↓"),
        ("full", "CRISIS_SPIKE + D2 flip ↓ + D3≠caos"),
        ("full_literal", "CRISIS_SPIKE + flip literal ↓ + D3≠caos"),
    ]:
        entries = find_entries(df, mode)
        rets = np.array([fwd_ret(df, i, 20) for i in entries])
        results[mode] = (entries, rets)
        print(f"  {label:<42} {len(rets):>4} {rets.mean()*100:>+7.2f}% "
              f"{np.median(rets)*100:>+7.2f}% {(rets>0).mean()*100:>4.0f}% "
              f"{rets.min()*100:>+7.2f}% {np.percentile(rets,10)*100:>+7.2f}% "
              f"{rets.max()*100:>+7.2f}%")

    # Peores trades por definición
    print("\n  ── PEORES 6 TRADES (hold 20d) por definición ──")
    target_dates = {pd.Timestamp("2008-09-29"), pd.Timestamp("2009-02-06"),
                    pd.Timestamp("2020-03-06")}
    for mode, label in [
        ("crisis", "CRISIS_SPIKE solo"),
        ("d2", "+ D2 flip ↓"),
        ("full", "+ D2 flip ↓ + D3≠caos"),
    ]:
        entries, rets = results[mode]
        order = np.argsort(rets)
        print(f"\n  {label}  (N={len(rets)}):")
        for k in order[:6]:
            i = entries[k]
            d = df.index[i]
            mark = "  ◀◀ OBJETIVO" if d in target_dates else ""
            print(f"    {d.date()}  {rets[k]*100:+7.2f}%  "
                  f"(SPY={df['spy'].iloc[i]:.0f}, VIX={df['vix'].iloc[i]:.1f}, "
                  f"D2={df['D2'].iloc[i]}, D3={df['D3'].iloc[i]}){mark}")

    # ¿Los 3 objetivos concretos sobreviven al filtro?
    print("\n  ── VEREDICTO: ¿el filtro elimina las 3 peores trades? ──")
    tz = df.index.tz
    for d in sorted(target_dates):
        d_aware = d.tz_localize(tz) if tz is not None else d
        # Buscar la barra más cercana a la fecha en cada definición
        line = f"    {d.date()}:"
        for mode, label in [("crisis", "solo"), ("d2", "+D2"), ("full", "+D2+D3")]:
            entries, rets = results[mode]
            # índice de la barra más cercana a la fecha (dentro de ±3d)
            pos = None
            for k, i in enumerate(entries):
                if abs((df.index[i] - d_aware).days) <= 3:
                    pos = k
                    break
            if pos is None:
                line += f"  [{label}: no-entra]"
            else:
                r = rets[pos]
                line += f"  [{label}: ENTRA {r*100:+.1f}%]"
        print(line)


# ── PARTE 2+3: SALIDA ───────────────────────────────────────────────────────
def run_strategy(df, entry_mode, exit_mode, max_hold=60):
    """Backtest one-trade-at-a-time. Devuelve DataFrame de trades + equity."""
    idx = list(df.index)
    n = len(df)
    trades = []
    i = 0
    while i < n:
        # buscar entrada
        row = df.iloc[i]
        if row["crisis"]:
            if entry_mode == "full":
                ok = row["d2_down"] and (not row["d3_chaos"])
            else:
                ok = row["d2_down"]
        else:
            ok = False
        if not ok:
            i += 1
            continue
        entry = i
        # buscar salida
        exit_i = None
        cap = min(entry + max_hold, n - 1)
        for j in range(entry + 1, cap + 1):
            r = df.iloc[j]
            if exit_mode == "d2_up":
                fired = r["d2_up"]
            elif exit_mode == "hold20":
                fired = (j - entry) >= 20
            elif exit_mode == "d3chaos_d2up":
                fired = r["d3_chaos"] and r["d2_up"]
            else:
                raise ValueError(exit_mode)
            if fired:
                exit_i = j
                break
        if exit_i is None:
            exit_i = cap
        ret = df["spy"].iloc[exit_i] / df["spy"].iloc[entry] - 1
        # max drawdown intra-trade (precio SPY)
        seg = df["spy"].iloc[entry:exit_i + 1].values
        dd = 1 - seg / np.maximum.accumulate(seg)
        trades.append({
            "entry_date": idx[entry], "exit_date": idx[exit_i],
            "entry_i": entry, "exit_i": exit_i,
            "hold_days": exit_i - entry,
            "ret": ret, "max_dd_intra": float(dd.max()),
            "capped": exit_i == cap,
        })
        i = exit_i + 1
    return trades


def stats(trades):
    if not trades:
        return None
    rets = np.array([t["ret"] for t in trades])
    equity = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return {
        "n": len(trades),
        "compound": float(equity[-1] - 1),
        "mean": float(rets.mean()),
        "median": float(np.median(rets)),
        "win": float((rets > 0).mean()),
        "min": float(rets.min()),
        "max": float(rets.max()),
        "max_dd_equity": float(dd.min()),
        "max_dd_intra": float(max(t["max_dd_intra"] for t in trades)),
        "avg_hold": float(np.mean([t["hold_days"] for t in trades])),
        "capped": int(sum(1 for t in trades if t["capped"])),
        "equity": equity,
    }


def audit_exit(df):
    print("\n" + "=" * 96)
    print("  PARTE 2+3 — SALIDA: 3 estrategias sobre la entrada óptima")
    print("           (entrada = CRISIS_SPIKE + D2 flip ↓ + D3≠caos, one-trade-at-a-time)")
    print("=" * 96)

    strategies = [
        ("d2_up",        "a) D2 flip ↑ (VIX vuelve a subir)"),
        ("hold20",       "b) Hold fijo 20d"),
        ("d3chaos_d2up", "c) D3 expansión + D2 flip ↑ (combinados)"),
    ]

    # período de referencia buy&hold SPY (mismo rango de la 1ª entrada a la última salida)
    all_trades = {}
    for mode, label in strategies:
        trades = run_strategy(df, "full", mode)
        all_trades[mode] = trades
        s = stats(trades)
        if s is None:
            print(f"\n  {label}: sin trades")
            continue
        print(f"\n  {label}")
        print(f"    Trades: {s['n']}   (cap 60d alcanzado: {s['capped']})")
        print(f"    Retorno compuesto: {s['compound']*100:+.2f}%   "
              f"(media/trade {s['mean']*100:+.2f}%, mediana {s['median']*100:+.2f}%)")
        print(f"    Win rate: {s['win']*100:.0f}%   min {s['min']*100:+.2f}%   max {s['max']*100:+.2f}%")
        print(f"    Max drawdown (equity): {s['max_dd_equity']*100:.2f}%   "
              f"Max drawdown intra-trade: {s['max_dd_intra']*100:.2f}%")
        print(f"    Hold medio: {s['avg_hold']:.1f}d")

    # Buy & hold de referencia
    first_entry = min((t["entry_i"] for t in all_trades["hold20"]), default=None)
    last_exit = max((t["exit_i"] for t in all_trades["hold20"]), default=None)
    if first_entry is not None and last_exit is not None:
        spy_bh = df["spy"].iloc[last_exit] / df["spy"].iloc[first_entry] - 1
        seg = df["spy"].iloc[first_entry:last_exit + 1].values
        dd = 1 - seg / np.maximum.accumulate(seg)
        print(f"\n  REFERENCIA — SPY buy & hold {df.index[first_entry].date()}→"
              f"{df.index[last_exit].date()}: {spy_bh*100:+.2f}%  "
              f"(maxDD {dd.max()*100:.2f}%)")

    # Detalle de trades de la estrategia ganadora candidata
    print("\n  ── DETALLE trades por estrategia (fecha entrada → salida, retorno) ──")
    for mode, label in strategies:
        trades = all_trades[mode]
        print(f"\n  {label}:")
        for t in trades:
            print(f"    {t['entry_date'].date()} → {t['exit_date'].date()}  "
                  f"{t['ret']*100:+7.2f}%  (hold {t['hold_days']}d, dd {t['max_dd_intra']*100:.1f}%)"
                  f"{' [cap]' if t['capped'] else ''}")


def main():
    df = build_frame()
    audit_entry(df)
    audit_exit(df)
    print("\n" + "=" * 96)
    print("  PARTE 4 — RECOMENDACIÓN (escalas del proyecto: VIX D1/D2/D3 calibrados)")
    print("=" * 96)
    print("""
  ENTRADA (validada — OBLIGATORIA):
    CRISIS_SPIKE  (VIX ≥ 25.92)
    + D2 flip ↓   (D2 ∈ {FAST_CRUSH_3D, DECELERATING_DOWN_3D} — VIX ya cayendo)
    + D3 ≠ caos   (D3 ∉ {VOL_ACCELERATING_EXPANSION, VOL_PEAK_DECELERATION})

    Efecto sobre left tail (hold 20d): -24.63% → -18.55%  (peor trade)
    Elimina las 3 peores: 2008-09-29 (D2=FAST_SPIKE), 2009-02-06 (D2=STABLE),
    2020-03-06 (D2=FAST_SPIKE). OJO: 2020-03-03 (FAST_CRUSH) sigue entrando y
    pierde -14.15% — el filtro reduce la cuchilla, no la elimina del todo.

  SALIDA:
    (a) D2 flip ↑ SOLO        → RECHAZADA. Whipsaw: hold medio 4.8d, win 44%,
                                mediana -0.34% (peor que el azar). La velocidad
                                del VIX oscila demasiado para ser exit único.
    (b) Hold fijo 20d         → Mejor retorno (+73.98%) y win (62%), pero mayor
                                drawdown (equity -41.8%, intra -28.7%).
    (c) D3 expansión + D2 flip ↑ → Mejor señal de salida: corta el drawdown a la
                                mitad (intra 28.7%→14.5%) con retorno casi igual
                                (+64.68%), y corta las colas supervivientes
                                (2008-09-22: -18.55%→-8.19%;
                                 2020-03-03: -14.15%→-8.66%).

  RECOMENDACIÓN ÓPTIMA:
    ENTRY = CRISIS_SPIKE + D2 flip ↓ + D3 ≠ caos
    EXIT  = D3 expansión + D2 flip ↑ (combinados)   [primaria]
    EXIT  = Hold fijo 20d                            [alternativa si se prioriza
                                                       retorno bruto y se asume
                                                       el drawdown]
    Evitar D2 flip ↑ como salida única (destruye el edge por whipsaw).
""")
    print("=" * 96)
    print("  FIN DEL AUDIT")
    print("=" * 96)


if __name__ == "__main__":
    main()
