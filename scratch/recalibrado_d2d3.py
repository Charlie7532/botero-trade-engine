#!/usr/bin/env python3
"""
RECALIBRADO D2/D3 — Análisis con bins calibrados de los lookup adapters.
Mide SPY forward returns usando EXCLUSIVAMENTE los bins D1/D2/D3 del proyecto,
NO umbrales crudos.

Análisis:
1. MATRIZ DE OPORTUNIDAD: D1 extremo x D2_bin x D3_bin -> SPY forward 5d/10d/20d
2. FLIP / TRANSICION: Cambio de signo D2 en extremos D1 -> retorno forward, split por D3
3. D3 COMO FILTRO: Discrimina D3 en estados extremos?
4. D2 VELOCIDAD: Gradiente de bins D2 -> SPY forward
5. PICO VS CRUCE: Primer bar CRISIS_SPIKE vs esperar a ELEVATED_PANIC o HIGH_VOL
6. EXTENDER a FG y BSI: misma matriz para FG y S5TW
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# Calibrated thresholds from lookup adapters
CALIBRATED = {
    'VIX': {
        'ticker': 'VIX',
        'd1_edges': [12.74, 15.46, 17.61, 20.499001000000007, 25.92],
        'd1_labels': ['DEEP_COMPLACENCY', 'LOW_VOL', 'MODERATE_VOL',
                       'HIGH_VOL', 'ELEVATED_PANIC', 'CRISIS_SPIKE'],
        'd2_edges': [-1.8054944999999993, -0.6600000000000001,
                      0.4900000000000001, 1.7599999999999998],
        'd2_labels': ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D',
                       'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'],
        'd3_edges': [0.2859356636215917, 0.460455625825507, 0.7474005777370026],
        'd3_labels': ['VOL_EXTREME_SQUEEZE', 'VOL_MODERATE_COMPRESSION',
                       'VOL_NEUTRAL_BASELINE', 'VOL_ACCELERATING_EXPANSION',
                       'VOL_PEAK_DECELERATION'],
        'extreme_d1': ['CRISIS_SPIKE', 'ELEVATED_PANIC'],
        'd1_fear': 'CRISIS_SPIKE',
        'd1_next': ['ELEVATED_PANIC', 'HIGH_VOL'],
    },
    'FG': {
        'ticker': 'FG',
        'd1_edges': [24.57857142857143, 41.0, 50.45428571428572,
                      59.42857142857144, 71.14285714285715],
        'd1_labels': ['EXTREME_FEAR', 'FEAR', 'NEUTRAL_FEAR',
                       'GREED', 'EUPHORIA', 'EXTREME_GREED'],
        'd2_edges': [-8.270476190476192, -3.0, 3.051428571428613, 8.519999999999998],
        'd2_labels': ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D',
                       'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'],
        'd3_edges': [0.20429502413641673, 0.3491933862465682, 0.6007366512353014],
        'd3_labels': ['VOL_EXTREME_SQUEEZE', 'VOL_MODERATE_COMPRESSION',
                       'VOL_NEUTRAL_BASELINE', 'VOL_ACCELERATING_EXPANSION',
                       'VOL_PEAK_DECELERATION'],
        'extreme_d1': ['EXTREME_GREED', 'EUPHORIA'],
        'extreme_d1_fear': ['EXTREME_FEAR'],
    },
    'BSI': {
        'ticker': 'S5TW',
        'd1_edges': [11.0, 33.84, 59.6, 77.6, 89.70],
        'd1_labels': ['BREADTH_WASHED_OUT', 'OVERSOLD_BREADTH',
                       'NEUTRAL_LOW_BREADTH', 'NEUTRAL_HIGH_BREADTH',
                       'EXPANSIVE_BREADTH', 'HYPER_EXPANSIVE_BREADTH'],
        'd2_edges': [-30.7, -13.4, 12.9, 32.2],
        'd2_labels': ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D',
                       'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'],
        'd3_edges': [0.0069, 0.0954, 0.9247, 1.6680],
        'd3_labels': ['VOL_EXTREME_SQUEEZE', 'VOL_MODERATE_COMPRESSION',
                       'VOL_NEUTRAL_BASELINE', 'VOL_ACCELERATING_EXPANSION',
                       'VOL_PEAK_DECELERATION'],
        'extreme_d1': ['BREADTH_WASHED_OUT', 'OVERSOLD_BREADTH', 'HYPER_EXPANSIVE_BREADTH'],
    },
}


def classify(value, edges, labels):
    """Classify a value into a bin using calibrated edges."""
    for i, e in enumerate(edges):
        if value < e:
            return labels[i]
    return labels[-1]


def build_dataset(station_name):
    """Load raw data, compute D1/D2/D3 bins, align with SPY, compute forward returns."""
    cfg = CALIBRATED[station_name]
    ticker = cfg['ticker']

    store = TimescaleDataStore()
    engine = store.engine

    # Load station data
    df_station = pd.read_sql("""
        SELECT time::date as date, close as val
        FROM market.ohlcv_bars
        WHERE ticker = '%s' AND timeframe = '1d'
        ORDER BY time
    """ % ticker, engine)
    df_station['date'] = pd.to_datetime(df_station['date'])
    df_station = df_station.set_index('date')
    df_station = df_station[~df_station.index.duplicated(keep='last')]

    # Load SPY data
    df_spy = pd.read_sql("""
        SELECT time::date as date, close as spy
        FROM market.ohlcv_bars
        WHERE ticker = 'SPY' AND timeframe = '1d'
        ORDER BY time
    """, engine)
    df_spy['date'] = pd.to_datetime(df_spy['date'])
    df_spy = df_spy.set_index('date')
    df_spy = df_spy[~df_spy.index.duplicated(keep='last')]

    store.close()

    # Align
    common = df_station.index.intersection(df_spy.index)
    df = pd.DataFrame(index=common)
    df['val'] = df_station.loc[common, 'val']
    df['spy'] = df_spy.loc[common, 'spy']

    # Compute D2 = 3-day velocity
    df['vel_3d'] = df['val'].diff(3)

    # Compute D3 = vol_norm = 2d_vol / 10d_vol
    vol2 = df['val'].rolling(2).std()
    vol10 = df['val'].rolling(10).std().replace(0, np.nan)
    df['vol_norm'] = (vol2 / vol10).fillna(1.0)

    # Classify D1, D2, D3
    df['D1'] = df['val'].apply(lambda v: classify(v, cfg['d1_edges'], cfg['d1_labels']))
    df['D2'] = df['vel_3d'].apply(lambda v: classify(v, cfg['d2_edges'], cfg['d2_labels']))
    df['D3'] = df['vol_norm'].apply(lambda v: classify(v, cfg['d3_edges'], cfg['d3_labels']))

    # Forward SPY returns
    for horizon in [5, 10, 20]:
        df[f'fwd_{horizon}d'] = df['spy'].shift(-horizon) / df['spy'] - 1

    df = df.dropna(subset=['D1', 'D2', 'D3'])

    return df, cfg


def fmt_pct(x):
    """Format as percentage string."""
    if pd.isna(x):
        return "   N/A"
    return f"{x*100:+7.2f}%"


def short_label(label, n=14):
    """Shorten a label for table display."""
    return label[:n]


def print_header(title):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print(f"{'='*100}")


def analysis_1_opportunity_matrix(df, cfg, station_name):
    """MATRIZ DE OPORTUNIDAD: D1 extremo x D2 x D3 -> SPY forward."""
    print_header(f"[1] MATRIZ DE OPORTUNIDAD - {station_name}")

    extreme_d1 = cfg['extreme_d1']
    sub = df[df['D1'].isin(extreme_d1)]

    if len(sub) < 20:
        print(f"  WARNING: Insufficient data: {len(sub)} bars in {extreme_d1}")
        return

    for d1_bin in extreme_d1:
        sub_d1 = sub[sub['D1'] == d1_bin]
        print(f"\n  -- D1 = {d1_bin} (N={len(sub_d1)}) --")

        d2_bins = cfg['d2_labels']
        d3_bins = cfg['d3_labels']

        for horizon in [5, 10, 20]:
            print(f"\n  Forward {horizon}d returns:")
            header = "  {:28}".format('D2 \\ D3')
            for d3 in d3_bins:
                header += " {:>14}".format(d3[:14])
            print(header)
            sep_line = f"  {'-'*28}{'-'*14*len(d3_bins)}"
            print(sep_line)

            for d2 in d2_bins:
                row = f"  {d2:<28}"
                for d3 in d3_bins:
                    mask = (sub_d1['D2'] == d2) & (sub_d1['D3'] == d3)
                    n = mask.sum()
                    if n >= 3:
                        ret = sub_d1.loc[mask, f'fwd_{horizon}d'].mean()
                        row += f" {fmt_pct(ret)}"
                    else:
                        row += f" {'':>14}"
                print(row)

        # Summary: which cells are most positive/negative
        print(f"\n  -- TOP CELLS for {d1_bin} (10d forward) --")
        cells = []
        for d2 in d2_bins:
            for d3 in d3_bins:
                mask = (sub_d1['D2'] == d2) & (sub_d1['D3'] == d3)
                n = mask.sum()
                if n >= 3:
                    ret = sub_d1.loc[mask, 'fwd_10d'].mean()
                    cells.append((d2, d3, n, ret))
        cells.sort(key=lambda x: x[3], reverse=True)
        for d2, d3, n, ret in cells[:5]:
            marker = "GREEN" if ret > 0.01 else ("RED" if ret < -0.01 else "NEUTRAL")
            print(f"    [{marker}] {d2} x {d3}: {ret*100:+.2f}% (N={n})")


def analysis_2_flip_transition(df, cfg, station_name):
    """FLIP / TRANSICION: cambio de signo D2 en extremos D1 -> SPY forward."""
    print_header(f"[2] FLIP / TRANSICION - {station_name}")

    extreme_d1 = cfg['extreme_d1']

    # Define D2 sign: positive / negative / stable
    d2_pos = {'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'}
    d2_neg = {'FAST_CRUSH_3D', 'DECELERATING_DOWN_3D'}

    df_sorted = df.sort_index()
    df_sorted['D2_sign'] = df_sorted['D2'].apply(
        lambda x: 1 if x in d2_pos else (-1 if x in d2_neg else 0)
    )
    df_sorted['D2_sign_prev'] = df_sorted['D2_sign'].shift(1)

    for horizon in [5, 10, 20]:
        print(f"\n  Forward {horizon}d SPY returns after D2 flip in extreme D1:")

        for d1_bin in extreme_d1:
            in_extreme = df_sorted['D1'] == d1_bin

            # Positive flip: D2 turns positive (was negative before)
            pos_flip = in_extreme & (df_sorted['D2_sign'] == 1) & (df_sorted['D2_sign_prev'] == -1)
            # Negative flip: D2 turns negative (was positive before)
            neg_flip = in_extreme & (df_sorted['D2_sign'] == -1) & (df_sorted['D2_sign_prev'] == 1)

            for flip_label, flip_mask in [('D2 turns POSITIVE', pos_flip),
                                           ('D2 turns NEGATIVE', neg_flip)]:
                n_flips = flip_mask.sum()
                if n_flips < 5:
                    continue

                flip_df = df_sorted[flip_mask]
                avg_ret = flip_df[f'fwd_{horizon}d'].dropna().mean()

                print(f"    {d1_bin} | {flip_label}: {fmt_pct(avg_ret)} (N={n_flips})")

                # Split by D3 at flip point
                for d3 in cfg['d3_labels']:
                    sub_flip = flip_df[flip_df['D3'] == d3]
                    n = len(sub_flip)
                    if n >= 3:
                        ret = sub_flip[f'fwd_{horizon}d'].dropna().mean()
                        print(f"      |-- D3={d3}: {fmt_pct(ret)} (N={n})")


def analysis_3_d3_filter(df, cfg, station_name):
    """D3 COMO FILTRO: Discrimina D3 retornos forward en estados extremos?"""
    print_header(f"[3] D3 COMO FILTRO - {station_name}")

    extreme_d1 = cfg['extreme_d1']
    sub = df[df['D1'].isin(extreme_d1)]

    for horizon in [5, 10, 20]:
        print(f"\n  Forward {horizon}d - D3 discrimination in extreme D1 states:")
        header = f"  {'D3 Bin':<30} {'Mean Return':>12} {'%% Positive':>10} {'N':>8} {'T-stat':>10}"
        print(header)
        sep_line = f"  {'-'*30}{'-'*12}{'-'*10}{'-'*8}{'-'*10}"
        print(sep_line)

        for d3 in cfg['d3_labels']:
            sub_d3 = sub[sub['D3'] == d3]
            n = len(sub_d3)
            if n < 5:
                continue
            rets = sub_d3[f'fwd_{horizon}d'].dropna()
            if len(rets) < 5:
                continue
            mean_ret = rets.mean()
            pct_pos = (rets > 0).mean()
            se = rets.std() / np.sqrt(len(rets)) if rets.std() > 0 else 1e-10
            tstat = mean_ret / se
            marker = "*" if abs(tstat) > 2 else " "
            print(f"  {marker}{d3:<29} {fmt_pct(mean_ret)} {pct_pos*100:>9.1f}%% {len(rets):>8} {tstat:>+9.2f}")

        # All extreme D1 (baseline)
        all_rets = sub[f'fwd_{horizon}d'].dropna()
        print(f"  {'-'*70}")
        print(f"  {'ALL extreme D1 (baseline)':<29} {fmt_pct(all_rets.mean())} "
              f"{(all_rets>0).mean()*100:>9.1f}%% {len(all_rets):>8}")


def analysis_4_d2_velocity_gradient(df, cfg, station_name):
    """D2 VELOCIDAD: Gradiente de bins D2 -> SPY forward."""
    print_header(f"[4] D2 VELOCITY GRADIENT - {station_name}")

    # D2 bins in velocity order
    d2_order = ['FAST_SPIKE_3D', 'ACCELERATING_UP_3D', 'STABLE_CONTINUATION_3D',
                'DECELERATING_DOWN_3D', 'FAST_CRUSH_3D']

    # Filter to extreme D1 only for stress analysis
    extreme_d1 = cfg['extreme_d1']
    sub = df[df['D1'].isin(extreme_d1)]

    for horizon in [5, 10, 20]:
        print(f"\n  Forward {horizon}d - D2 gradient in extreme D1 states:")
        header = f"  {'D2 Bin':<30} {'Mean Return':>12} {'%% Positive':>10} {'N':>8} {'Median':>10}"
        print(header)
        sep_line = f"  {'-'*30}{'-'*12}{'-'*10}{'-'*8}{'-'*10}"
        print(sep_line)

        for d2 in d2_order:
            sub_d2 = sub[sub['D2'] == d2]
            rets = sub_d2[f'fwd_{horizon}d'].dropna()
            n = len(rets)
            if n < 5:
                continue
            mean_ret = rets.mean()
            pct_pos = (rets > 0).mean()
            median = rets.median()
            print(f"  {d2:<30} {fmt_pct(mean_ret)} {pct_pos*100:>9.1f}%% {n:>8} {fmt_pct(median)}")

        # Also show gradient for ALL D1 states
        print(f"\n  -- Same gradient, ALL D1 states --")
        header2 = f"  {'D2 Bin':<30} {'Mean Return':>12} {'%% Positive':>10} {'N':>8}"
        print(header2)
        print(f"  {'-'*30}{'-'*12}{'-'*10}{'-'*8}")
        for d2 in d2_order:
            sub_d2 = df[df['D2'] == d2]
            rets = sub_d2[f'fwd_{horizon}d'].dropna()
            n = len(rets)
            if n < 5:
                continue
            print(f"  {d2:<30} {fmt_pct(rets.mean())} {(rets>0).mean()*100:>9.1f}%% {n:>8}")


def analysis_5_peak_vs_cross(df, cfg, station_name):
    """PICO VS CRUCE: Primer bar en CRISIS_SPIKE vs esperar a bajar."""
    print_header(f"[5] PICO VS CRUCE - {station_name}")

    if 'd1_fear' not in cfg:
        print("  WARNING: No CRISIS_SPIKE equivalent defined for this station, skipping.")
        return

    d1_fear = cfg['d1_fear']  # CRISIS_SPIKE
    d1_next = cfg.get('d1_next', [])  # ELEVATED_PANIC, HIGH_VOL

    # Find sequences: first bar in d1_fear, then subsequent exit
    df_sorted = df.sort_index()

    # Identify entry into d1_fear
    df_sorted['prev_D1'] = df_sorted['D1'].shift(1)
    df_sorted['entering_fear'] = (df_sorted['D1'] == d1_fear) & (df_sorted['prev_D1'] != d1_fear)

    entering = df_sorted[df_sorted['entering_fear']]

    if len(entering) < 5:
        print(f"  WARNING: Few {d1_fear} entries: {len(entering)}")
        return

    print(f"\n  {d1_fear} entries found: {len(entering)}")

    for horizon in [5, 10, 20]:
        print(f"\n  Forward {horizon}d returns from first bar in {d1_fear}:")

        # Buy at first bar
        first_bar_rets = entering[f'fwd_{horizon}d'].dropna()
        if len(first_bar_rets) > 0:
            pos_pct = (first_bar_rets > 0).mean() * 100
            print(f"    Buy at 1st {d1_fear} bar: {fmt_pct(first_bar_rets.mean())}  "
                  f"%%pos={pos_pct:.0f}%%  N={len(first_bar_rets)}")

        # Wait until exit to each next level
        for next_d1 in d1_next:
            exit_returns = []
            for idx in entering.index:
                # Look forward up to 30 bars
                future = df_sorted.loc[idx:].head(31)
                exit_bars = future[future['D1'] == next_d1]
                if len(exit_bars) > 0:
                    exit_idx = exit_bars.index[0]
                    col = f'fwd_{horizon}d'
                    if exit_idx in df_sorted.index:
                        exit_ret = df_sorted.loc[exit_idx, col]
                        if not pd.isna(exit_ret):
                            exit_returns.append(exit_ret)

            if exit_returns:
                arr = np.array(exit_returns)
                pos_pct = (arr > 0).mean() * 100
                print(f"    Wait -> {next_d1}:              {fmt_pct(arr.mean())}  "
                      f"%%pos={pos_pct:.0f}%%  N={len(arr)}")
            else:
                print(f"    Wait -> {next_d1}:              (no transitions found)")


def analysis_6_extend_fg_bsi(df_fg, cfg_fg, df_bsi, cfg_bsi):
    """EXTENDER a FG y BSI: mismas matrices."""
    print_header("[6] EXTENDER A FG Y BSI")

    # FG: extreme greed
    print("\n  === FG - Extreme Greed (D1 = EUPHORIA, EXTREME_GREED) ===")
    sub_fg = df_fg[df_fg['D1'].isin(cfg_fg['extreme_d1'])]
    print(f"  Total bars in extreme greed: {len(sub_fg)}")

    for d1_bin in cfg_fg['extreme_d1']:
        sub_fg_d1 = sub_fg[sub_fg['D1'] == d1_bin]
        print(f"\n  -- D1 = {d1_bin} (N={len(sub_fg_d1)}) --")

        for horizon in [5, 10, 20]:
            print(f"\n  Forward {horizon}d:")
            for d2 in cfg_fg['d2_labels']:
                row_str = f"    {d2:<28}"
                for d3 in cfg_fg['d3_labels']:
                    mask = (sub_fg_d1['D2'] == d2) & (sub_fg_d1['D3'] == d3)
                    n = mask.sum()
                    if n >= 3:
                        ret = sub_fg_d1.loc[mask, f'fwd_{horizon}d'].mean()
                        row_str += f" {fmt_pct(ret)}"
                    else:
                        row_str += f" {'':>14}"
                print(row_str)

    # FG: extreme fear (opposite)
    if 'extreme_d1_fear' in cfg_fg:
        print(f"\n  === FG - Extreme Fear (D1 = EXTREME_FEAR) ===")
        sub_fg_fear = df_fg[df_fg['D1'].isin(cfg_fg['extreme_d1_fear'])]
        print(f"  Total bars in extreme fear: {len(sub_fg_fear)}")

        for d1_bin in cfg_fg['extreme_d1_fear']:
            sub_fg_fear_d1 = sub_fg_fear[sub_fg_fear['D1'] == d1_bin]
            print(f"\n  -- D1 = {d1_bin} (N={len(sub_fg_fear_d1)}) --")

            for horizon in [5, 10, 20]:
                print(f"\n  Forward {horizon}d:")
                for d2 in cfg_fg['d2_labels']:
                    row_str = f"    {d2:<28}"
                    for d3 in cfg_fg['d3_labels']:
                        mask = (sub_fg_fear_d1['D2'] == d2) & (sub_fg_fear_d1['D3'] == d3)
                        n = mask.sum()
                        if n >= 3:
                            ret = sub_fg_fear_d1.loc[mask, f'fwd_{horizon}d'].mean()
                            row_str += f" {fmt_pct(ret)}"
                        else:
                            row_str += f" {'':>14}"
                    print(row_str)

    # BSI
    print(f"\n  === BSI (S5TW) - Extreme Breadth ===")
    for d1_bin in cfg_bsi['extreme_d1']:
        sub_bsi_d1 = df_bsi[df_bsi['D1'] == d1_bin]
        if len(sub_bsi_d1) < 20:
            print(f"  {d1_bin}: too few bars ({len(sub_bsi_d1)})")
            continue

        print(f"\n  -- D1 = {d1_bin} (N={len(sub_bsi_d1)}) --")
        for horizon in [5, 10, 20]:
            print(f"\n  Forward {horizon}d:")
            for d2 in cfg_bsi['d2_labels']:
                row_str = f"    {d2:<28}"
                for d3 in cfg_bsi['d3_labels']:
                    mask = (sub_bsi_d1['D2'] == d2) & (sub_bsi_d1['D3'] == d3)
                    n = mask.sum()
                    if n >= 3:
                        ret = sub_bsi_d1.loc[mask, f'fwd_{horizon}d'].mean()
                        row_str += f" {fmt_pct(ret)}"
                    else:
                        row_str += f" {'':>14}"
                print(row_str)


# ======================================================================
# MAIN
# ======================================================================
if __name__ == '__main__':
    print("RECALIBRADO D2/D3 - Analisis con bins calibrados")
    print("=" * 100)

    # Build VIX dataset
    print("\nLoading VIX data...")
    df_vix, cfg_vix = build_dataset('VIX')
    print(f"   VIX: {len(df_vix)} bars, {df_vix['D1'].nunique()} D1 bins, "
          f"{df_vix['D2'].nunique()} D2 bins, {df_vix['D3'].nunique()} D3 bins")
    print(f"   D1 distribution:")
    for k, v in df_vix['D1'].value_counts().items():
        print(f"     {k}: {v}")
    print(f"   D2 distribution:")
    for k, v in df_vix['D2'].value_counts().items():
        print(f"     {k}: {v}")
    print(f"   D3 distribution:")
    for k, v in df_vix['D3'].value_counts().items():
        print(f"     {k}: {v}")

    # Build FG dataset
    print("\nLoading FG data...")
    df_fg, cfg_fg = build_dataset('FG')
    print(f"   FG: {len(df_fg)} bars, {df_fg['D1'].nunique()} D1 bins")
    for k, v in df_fg['D1'].value_counts().items():
        print(f"     {k}: {v}")

    # Build BSI dataset
    print("\nLoading BSI (S5TW) data...")
    df_bsi, cfg_bsi = build_dataset('BSI')
    print(f"   BSI: {len(df_bsi)} bars, {df_bsi['D1'].nunique()} D1 bins")
    for k, v in df_bsi['D1'].value_counts().items():
        print(f"     {k}: {v}")

    # Run all analyses on VIX
    analysis_1_opportunity_matrix(df_vix, cfg_vix, 'VIX')
    analysis_2_flip_transition(df_vix, cfg_vix, 'VIX')
    analysis_3_d3_filter(df_vix, cfg_vix, 'VIX')
    analysis_4_d2_velocity_gradient(df_vix, cfg_vix, 'VIX')
    analysis_5_peak_vs_cross(df_vix, cfg_vix, 'VIX')

    # Extend to FG and BSI
    analysis_6_extend_fg_bsi(df_fg, cfg_fg, df_bsi, cfg_bsi)

    print(f"\n{'='*100}")
    print("  ANALISIS COMPLETO")
    print(f"{'='*100}")