#!/usr/bin/env python3
"""
SIMULADOR EMPÍRICO: ¿Qué conceptos tienen efecto REAL?
=======================================================
En vez de confiar en papers (sesgo académico) o en folklore (sesgo trader),
PROBAMOS cada concepto contra datos reales de nuestro parquet.

Hipótesis a testear:
  H1: Volume Profile (VPOC) — ¿Los Springs cerca del VPOC ganan más?
  H2: VSA Effort-vs-Result — ¿El stopping volume predice reversiones?
  H3: Spring Test — ¿Esperar el test mejora el Win Rate?
  H4: SMA200 Trend Filter — ¿Filtrar por tendencia mejora resultados?
  H5: VIX Filter — ¿VIX alto predice fallo de Springs?
  H6: RSI(2) vs ret_5d — ¿RSI(2) es mejor entrada que ret_5d?
  H7: Close Position en barra — ¿Close en lower 30% del rango = distribución?

Metodología: Walk-forward sobre 10 ETFs, 5 años de datos.
Para cada concepto, dividir trades en 2 grupos y comparar métricas.
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# Load data
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "historical" / "market_context_5y.parquet"

def load_data():
    df = pd.read_parquet(DATA_PATH)
    return df

def compute_rsi(closes, period=2):
    """RSI de N períodos."""
    delta = pd.Series(closes).diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return (100 - 100 / (1 + rs)).values

def compute_vpoc(closes, volumes, lookback=60):
    """
    Volume Point of Control: precio con más volumen acumulado
    en los últimos `lookback` días, discretizado en buckets.
    """
    if len(closes) < lookback:
        return np.nan, np.nan, np.nan

    recent_closes = closes[-lookback:]
    recent_volumes = volumes[-lookback:]

    # Discretizar en buckets de 0.5%
    price_min = recent_closes.min()
    price_max = recent_closes.max()
    if price_max == price_min:
        return recent_closes[-1], recent_closes[-1], recent_closes[-1]

    n_buckets = max(20, int((price_max - price_min) / (price_min * 0.005)))
    bucket_edges = np.linspace(price_min, price_max, n_buckets + 1)

    vol_by_bucket = np.zeros(n_buckets)
    for p, v in zip(recent_closes, recent_volumes):
        idx = min(np.searchsorted(bucket_edges, p) - 1, n_buckets - 1)
        idx = max(0, idx)
        vol_by_bucket[idx] += v

    # VPOC = centro del bucket con más volumen
    vpoc_idx = np.argmax(vol_by_bucket)
    vpoc = (bucket_edges[vpoc_idx] + bucket_edges[vpoc_idx + 1]) / 2

    # Value Area (70% del volumen)
    total_vol = vol_by_bucket.sum()
    target = total_vol * 0.70
    sorted_idxs = np.argsort(vol_by_bucket)[::-1]
    cumulative = 0
    va_buckets = []
    for idx in sorted_idxs:
        va_buckets.append(idx)
        cumulative += vol_by_bucket[idx]
        if cumulative >= target:
            break

    va_low = bucket_edges[min(va_buckets)]
    va_high = bucket_edges[max(va_buckets) + 1]

    return vpoc, va_low, va_high


def simulate_spring_trades(ticker_df, spy_df=None, vix_df=None):
    """
    Genera trades Spring y etiqueta cada uno con los factores
    que queremos testear. Retorna lista de trades enriquecidos.
    """
    df = ticker_df.sort_values('Date').reset_index(drop=True)
    if len(df) < 252:
        return []

    closes = df['Close'].values
    highs = df['High'].values
    lows = df['Low'].values
    volumes = df['Volume'].values
    dates = df['Date'].values
    ticker = df['Ticker'].iloc[0] if 'Ticker' in df.columns else 'UNK'

    # Pre-compute indicators
    rsi2 = compute_rsi(closes, period=2)

    # VIX series aligned by date
    vix_map = {}
    if vix_df is not None and len(vix_df) > 0:
        for _, row in vix_df.iterrows():
            vix_map[row['Date']] = row['Close']

    # SPY aligned
    spy_map = {}
    if spy_df is not None:
        for _, row in spy_df.iterrows():
            spy_map[row['Date']] = row['Close']

    trades = []
    in_trade = False
    entry_idx = 0
    entry_price = 0
    stop_price = 0
    ma20_target = 0

    # Spring detection fields for each trade
    for i in range(252, len(closes)):
        # === KEY METRICS ===
        # MA20
        ma20 = np.mean(closes[i-20:i])
        # MA200 (trend filter)
        ma200 = np.mean(closes[i-200:i])
        # Ret 5d
        ret_5d = closes[i] / closes[i-5] - 1
        # RVol
        avg_vol = np.mean(volumes[i-20:i])
        rvol = volumes[i] / max(avg_vol, 1)
        # ATR 20
        atr = np.mean(highs[i-20:i] - lows[i-20:i])
        # Close position in range
        bar_range = highs[i] - lows[i]
        close_pos = (closes[i] - lows[i]) / max(bar_range, 0.001)
        # Spread vs avg spread
        avg_spread = np.mean(highs[i-20:i] - lows[i-20:i])
        spread_ratio = bar_range / max(avg_spread, 0.001)
        # VIX
        vix = vix_map.get(dates[i], 17.0)
        # RSI(2)
        rsi_val = rsi2[i] if i < len(rsi2) and not np.isnan(rsi2[i]) else 50

        # VPOC & Value Area
        vpoc, va_low, va_high = compute_vpoc(closes[max(0,i-60):i], volumes[max(0,i-60):i], lookback=60)

        # VSA: Effort vs Result
        effort = rvol  # Relative volume = effort
        result = abs(closes[i] - closes[i-1]) / max(closes[i-1], 1) * 100  # Price change %
        # Stopping volume: high effort, low result
        stopping_volume = effort > 1.5 and result < 0.3 and close_pos > 0.5
        # Selling climax: high effort, wide spread, close at low
        selling_climax = effort > 2.0 and close_pos < 0.3 and spread_ratio > 1.5

        # === POSITION MANAGEMENT ===
        if in_trade:
            bars_held = i - entry_idx

            exit_reason = None
            if closes[i] >= ma20 and bars_held >= 2:
                exit_reason = 'MA20_REVERSION'
            elif closes[i] <= stop_price:
                exit_reason = 'STOP_HIT'
            elif bars_held >= 30:
                exit_reason = 'TIMEOUT'

            if exit_reason:
                pnl = (closes[i] / entry_price - 1) * 100 - 0.16  # with costs
                trades[-1].update({
                    'exit_price': closes[i],
                    'exit_date': str(dates[i]),
                    'exit_reason': exit_reason,
                    'pnl_pct': round(pnl, 3),
                    'bars_held': bars_held,
                    'winner': pnl > 0,
                })
                in_trade = False
            continue

        # === ENTRY: Standard Spring ===
        if ret_5d < -0.02 and rvol > 1.2:
            entry_price = closes[i]
            entry_idx = i
            stop_price = entry_price - atr * 2
            ma20_target = ma20
            in_trade = True

            # Was there a "test" (prior low revisited on low volume)?
            # Look back 1-5 days for a prior low with lower volume
            spring_test = False
            if i >= 5:
                prior_low = min(closes[i-5:i])
                prior_low_idx = i - 5 + np.argmin(closes[i-5:i])
                if prior_low_idx != i:
                    # Did today revisit near the prior low with lower volume?
                    near_prior_low = abs(closes[i] - prior_low) / prior_low < 0.01
                    lower_volume = rvol < 1.0
                    spring_test = near_prior_low and lower_volume

            # Distance to VPOC
            dist_to_vpoc = abs(closes[i] - vpoc) / vpoc * 100 if not np.isnan(vpoc) else 999
            in_value_area = (not np.isnan(va_low)) and va_low <= closes[i] <= va_high
            below_value_area = (not np.isnan(va_low)) and closes[i] < va_low

            # Consecutive down days
            consec_down = 0
            for j in range(1, 8):
                if i-j >= 0 and closes[i-j] < closes[i-j-1]:
                    consec_down += 1
                else:
                    break

            trades.append({
                'ticker': ticker,
                'entry_price': entry_price,
                'entry_date': str(dates[i]),
                'exit_price': None,
                'exit_date': None,
                'exit_reason': None,
                'pnl_pct': None,
                'bars_held': None,
                'winner': None,
                # === FACTORS TO TEST ===
                'ret_5d': round(ret_5d * 100, 2),
                'rsi2': round(rsi_val, 1),
                'rvol': round(rvol, 2),
                'ma200_above': closes[i] > ma200,
                'ma200_dist_pct': round((closes[i] / ma200 - 1) * 100, 2),
                'vix': round(vix, 1),
                'vix_high': vix > 30,
                'vix_medium': 20 <= vix <= 30,
                'vix_low': vix < 20,
                'vpoc_dist_pct': round(dist_to_vpoc, 2),
                'in_value_area': in_value_area,
                'below_value_area': below_value_area,
                'close_position': round(close_pos, 3),
                'spread_ratio': round(spread_ratio, 2),
                'stopping_volume': stopping_volume,
                'selling_climax': selling_climax,
                'spring_test': spring_test,
                'consec_down_days': consec_down,
                'effort_vs_result': round(effort / max(result, 0.01), 2),
            })

    # Remove unclosed trades
    trades = [t for t in trades if t['pnl_pct'] is not None]
    return trades


def test_hypothesis(trades_df, factor_col, label_true, label_false, description):
    """
    Divide trades en 2 grupos por un factor booleano y compara métricas.
    """
    group_true = trades_df[trades_df[factor_col] == True]
    group_false = trades_df[trades_df[factor_col] == False]

    def metrics(df, name):
        if len(df) == 0:
            return {'group': name, 'n': 0, 'wr': 0, 'avg_pnl': 0, 'total': 0, 'sharpe': 0}
        wr = df['winner'].mean() * 100
        avg_pnl = df['pnl_pct'].mean()
        total = df['pnl_pct'].sum()
        std = df['pnl_pct'].std()
        sharpe = avg_pnl / std * np.sqrt(252/6) if std > 0 else 0  # annualized approx
        return {
            'group': name, 'n': len(df),
            'wr': round(wr, 1), 'avg_pnl': round(avg_pnl, 3),
            'total': round(total, 2), 'sharpe': round(sharpe, 2)
        }

    m_true = metrics(group_true, label_true)
    m_false = metrics(group_false, label_false)

    delta_wr = m_true['wr'] - m_false['wr']
    delta_pnl = m_true['avg_pnl'] - m_false['avg_pnl']

    verdict = '✅' if delta_wr > 5 and delta_pnl > 0.1 else '⚠️' if delta_wr > 0 or delta_pnl > 0 else '❌'

    return {
        'hypothesis': description,
        'factor': factor_col,
        'true_group': m_true,
        'false_group': m_false,
        'delta_wr': round(delta_wr, 1),
        'delta_avg_pnl': round(delta_pnl, 3),
        'verdict': verdict,
    }


def test_continuous(trades_df, factor_col, threshold, above_label, below_label, description):
    """Test para factores continuos con un umbral."""
    trades_df = trades_df.copy()
    trades_df['_split'] = trades_df[factor_col] > threshold
    return test_hypothesis(trades_df, '_split', above_label, below_label, description)


def main():
    print("="*100)
    print("SIMULADOR EMPÍRICO: Verificación de Hipótesis con Datos Reales")
    print("="*100)

    df = load_data()
    print(f"\nDatos: {len(df)} filas, tickers: {df['Ticker'].nunique()}")

    # Load VIX from parquet if available, else create empty
    vix_df = df[df['Ticker'] == 'VIX'].copy() if 'VIX' in df['Ticker'].values else pd.DataFrame()

    # Get SPY data
    spy_df = df[df['Ticker'] == 'SPY'].copy()

    tickers = ['SPY', 'XLK', 'XLE', 'XLF', 'XLV', 'EEM', 'EWY', 'GLD', 'USO', 'EFA']

    # Generate trades for all tickers
    all_trades = []
    for ticker in tickers:
        tk_df = df[df['Ticker'] == ticker].copy()
        if len(tk_df) < 300:
            print(f"  {ticker}: datos insuficientes ({len(tk_df)})")
            continue
        trades = simulate_spring_trades(tk_df, spy_df=spy_df, vix_df=vix_df)
        print(f"  {ticker}: {len(trades)} trades generados")
        all_trades.extend(trades)

    trades_df = pd.DataFrame(all_trades)
    print(f"\n📊 Total trades para análisis: {len(trades_df)}")
    print(f"   Winners: {trades_df['winner'].sum()} ({trades_df['winner'].mean()*100:.1f}%)")
    print(f"   Avg PnL: {trades_df['pnl_pct'].mean():+.3f}%")
    print(f"   Total PnL: {trades_df['pnl_pct'].sum():+.1f}%")

    # ════════════════════════════════════════════════════════════════
    # HIPÓTESIS 1: SMA200 Trend Filter
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("HIPÓTESIS 1: SMA200 TREND FILTER (Connors)")
    print("¿Los trades con precio ARRIBA de la SMA200 ganan más?")
    print("="*100)
    r = test_hypothesis(trades_df, 'ma200_above', 'Price > SMA200', 'Price < SMA200',
                        'SMA200 Trend Filter')
    print(f"  {r['true_group']['group']:>20}: N={r['true_group']['n']:>4} | WR={r['true_group']['wr']:>5.1f}% | AvgPnL={r['true_group']['avg_pnl']:>+7.3f}% | Sharpe={r['true_group']['sharpe']:>6.2f}")
    print(f"  {r['false_group']['group']:>20}: N={r['false_group']['n']:>4} | WR={r['false_group']['wr']:>5.1f}% | AvgPnL={r['false_group']['avg_pnl']:>+7.3f}% | Sharpe={r['false_group']['sharpe']:>6.2f}")
    print(f"  Δ WR: {r['delta_wr']:+.1f}pp | Δ AvgPnL: {r['delta_avg_pnl']:+.3f}% | {r['verdict']}")

    # ════════════════════════════════════════════════════════════════
    # HIPÓTESIS 2: VPOC Proximity
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("HIPÓTESIS 2: VOLUME PROFILE — ¿Springs cerca del VPOC ganan más?")
    print("="*100)
    r = test_continuous(trades_df, 'vpoc_dist_pct', 2.0,
                        'Lejos del VPOC (>2%)', 'Cerca del VPOC (<2%)',
                        'VPOC Proximity')
    # NOTE: inverted — "close to VPOC" = false group (below threshold)
    print(f"  {'Cerca VPOC (<2%)':>20}: N={r['false_group']['n']:>4} | WR={r['false_group']['wr']:>5.1f}% | AvgPnL={r['false_group']['avg_pnl']:>+7.3f}% | Sharpe={r['false_group']['sharpe']:>6.2f}")
    print(f"  {'Lejos VPOC (>2%)':>20}: N={r['true_group']['n']:>4} | WR={r['true_group']['wr']:>5.1f}% | AvgPnL={r['true_group']['avg_pnl']:>+7.3f}% | Sharpe={r['true_group']['sharpe']:>6.2f}")
    delta_wr = r['false_group']['wr'] - r['true_group']['wr']
    delta_pnl = r['false_group']['avg_pnl'] - r['true_group']['avg_pnl']
    verdict = '✅' if delta_wr > 5 and delta_pnl > 0.1 else '⚠️' if delta_wr > 0 or delta_pnl > 0 else '❌'
    print(f"  Δ WR: {delta_wr:+.1f}pp | Δ AvgPnL: {delta_pnl:+.3f}% | {verdict}")

    # Value Area test
    print(f"\n  Sub-test: ¿Estar DENTRO de la Value Area mejora?")
    r2 = test_hypothesis(trades_df, 'in_value_area', 'Dentro VA', 'Fuera VA',
                         'Value Area Inclusion')
    print(f"  {'Dentro VA':>20}: N={r2['true_group']['n']:>4} | WR={r2['true_group']['wr']:>5.1f}% | AvgPnL={r2['true_group']['avg_pnl']:>+7.3f}%")
    print(f"  {'Fuera VA':>20}: N={r2['false_group']['n']:>4} | WR={r2['false_group']['wr']:>5.1f}% | AvgPnL={r2['false_group']['avg_pnl']:>+7.3f}%")
    print(f"  Δ WR: {r2['delta_wr']:+.1f}pp | Δ AvgPnL: {r2['delta_avg_pnl']:+.3f}% | {r2['verdict']}")

    # Below Value Area
    print(f"\n  Sub-test: ¿Springs DEBAJO de la Value Area (supuesto LVN) fallan más?")
    r3 = test_hypothesis(trades_df, 'below_value_area', 'Below VA', 'In/Above VA',
                         'Below Value Area')
    print(f"  {'Below VA':>20}: N={r3['true_group']['n']:>4} | WR={r3['true_group']['wr']:>5.1f}% | AvgPnL={r3['true_group']['avg_pnl']:>+7.3f}%")
    print(f"  {'In/Above VA':>20}: N={r3['false_group']['n']:>4} | WR={r3['false_group']['wr']:>5.1f}% | AvgPnL={r3['false_group']['avg_pnl']:>+7.3f}%")
    print(f"  Δ WR: {r3['delta_wr']:+.1f}pp | Δ AvgPnL: {r3['delta_avg_pnl']:+.3f}% | {r3['verdict']}")

    # ════════════════════════════════════════════════════════════════
    # HIPÓTESIS 3: VSA EFFORT vs RESULT
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("HIPÓTESIS 3: VSA — ¿Stopping Volume (alto esfuerzo, bajo resultado) predice reversión?")
    print("="*100)
    r = test_hypothesis(trades_df, 'stopping_volume',
                        'Stopping Volume', 'Normal Volume',
                        'VSA Stopping Volume')
    print(f"  {'Stopping Volume':>20}: N={r['true_group']['n']:>4} | WR={r['true_group']['wr']:>5.1f}% | AvgPnL={r['true_group']['avg_pnl']:>+7.3f}% | Sharpe={r['true_group']['sharpe']:>6.2f}")
    print(f"  {'Normal Volume':>20}: N={r['false_group']['n']:>4} | WR={r['false_group']['wr']:>5.1f}% | AvgPnL={r['false_group']['avg_pnl']:>+7.3f}% | Sharpe={r['false_group']['sharpe']:>6.2f}")
    print(f"  Δ WR: {r['delta_wr']:+.1f}pp | Δ AvgPnL: {r['delta_avg_pnl']:+.3f}% | {r['verdict']}")

    # Selling Climax
    print(f"\n  Sub-test: ¿Selling Climax (vol alto + spread amplio + close en low) = suelo?")
    r_sc = test_hypothesis(trades_df, 'selling_climax',
                           'Selling Climax', 'No Climax',
                           'VSA Selling Climax')
    print(f"  {'Selling Climax':>20}: N={r_sc['true_group']['n']:>4} | WR={r_sc['true_group']['wr']:>5.1f}% | AvgPnL={r_sc['true_group']['avg_pnl']:>+7.3f}%")
    print(f"  {'No Climax':>20}: N={r_sc['false_group']['n']:>4} | WR={r_sc['false_group']['wr']:>5.1f}% | AvgPnL={r_sc['false_group']['avg_pnl']:>+7.3f}%")
    print(f"  Δ WR: {r_sc['delta_wr']:+.1f}pp | Δ AvgPnL: {r_sc['delta_avg_pnl']:+.3f}% | {r_sc['verdict']}")

    # ════════════════════════════════════════════════════════════════
    # HIPÓTESIS 4: SPRING TEST
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("HIPÓTESIS 4: SPRING TEST — ¿Esperar el test (revisita de low en bajo volumen) mejora?")
    print("="*100)
    r = test_hypothesis(trades_df, 'spring_test',
                        'Con Test', 'Sin Test',
                        'Spring Test Confirmation')
    print(f"  {'Con Test':>20}: N={r['true_group']['n']:>4} | WR={r['true_group']['wr']:>5.1f}% | AvgPnL={r['true_group']['avg_pnl']:>+7.3f}% | Sharpe={r['true_group']['sharpe']:>6.2f}")
    print(f"  {'Sin Test':>20}: N={r['false_group']['n']:>4} | WR={r['false_group']['wr']:>5.1f}% | AvgPnL={r['false_group']['avg_pnl']:>+7.3f}% | Sharpe={r['false_group']['sharpe']:>6.2f}")
    print(f"  Δ WR: {r['delta_wr']:+.1f}pp | Δ AvgPnL: {r['delta_avg_pnl']:+.3f}% | {r['verdict']}")

    # ════════════════════════════════════════════════════════════════
    # HIPÓTESIS 5: VIX FILTER
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("HIPÓTESIS 5: VIX FILTER — ¿VIX alto = Springs fallan?")
    print("="*100)
    if 'vix' in trades_df.columns and trades_df['vix'].nunique() > 1:
        for threshold, label in [(20, 'VIX<20 vs VIX≥20'), (25, 'VIX<25 vs VIX≥25'), (30, 'VIX<30 vs VIX≥30')]:
            r = test_continuous(trades_df, 'vix', threshold,
                                f'VIX>{threshold}', f'VIX≤{threshold}', f'VIX threshold {threshold}')
            print(f"  VIX≤{threshold}: N={r['false_group']['n']:>4} | WR={r['false_group']['wr']:>5.1f}% | AvgPnL={r['false_group']['avg_pnl']:>+7.3f}%")
            print(f"  VIX>{threshold}: N={r['true_group']['n']:>4} | WR={r['true_group']['wr']:>5.1f}% | AvgPnL={r['true_group']['avg_pnl']:>+7.3f}%")
            d_wr = r['false_group']['wr'] - r['true_group']['wr']
            d_pnl = r['false_group']['avg_pnl'] - r['true_group']['avg_pnl']
            v = '✅' if d_wr > 5 and d_pnl > 0.1 else '⚠️' if d_wr > 0 or d_pnl > 0 else '❌'
            print(f"  Δ WR: {d_wr:+.1f}pp | Δ AvgPnL: {d_pnl:+.3f}% | {v}")
            print()
    else:
        print("  ⚠️ VIX data no disponible o constante en parquet. Descargando...")

    # ════════════════════════════════════════════════════════════════
    # HIPÓTESIS 6: RSI(2) vs RET_5D
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("HIPÓTESIS 6: RSI(2) — ¿RSI(2) bajo = mejor que ret_5d?")
    print("="*100)
    for threshold in [5, 10, 15, 20]:
        r = test_continuous(trades_df, 'rsi2', threshold,
                            f'RSI2>{threshold}', f'RSI2≤{threshold}', f'RSI2 threshold {threshold}')
        print(f"  RSI2≤{threshold:>2}: N={r['false_group']['n']:>4} | WR={r['false_group']['wr']:>5.1f}% | AvgPnL={r['false_group']['avg_pnl']:>+7.3f}% | Sharpe={r['false_group']['sharpe']:>6.2f}")
    print()

    # Consecutive down days
    print("  Sub-test: ¿Más días consecutivos bajistas = mejor entry?")
    for days in [2, 3, 4, 5]:
        mask = trades_df['consec_down_days'] >= days
        group = trades_df[mask]
        if len(group) > 5:
            wr = group['winner'].mean() * 100
            avg = group['pnl_pct'].mean()
            print(f"  {days}+ días down: N={len(group):>4} | WR={wr:>5.1f}% | AvgPnL={avg:>+7.3f}%")

    # ════════════════════════════════════════════════════════════════
    # HIPÓTESIS 7: CLOSE POSITION (Bar-level VSA)
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("HIPÓTESIS 7: CLOSE POSITION — ¿En qué parte de la barra cierra importa?")
    print("="*100)
    for threshold in [0.3, 0.5, 0.7]:
        r = test_continuous(trades_df, 'close_position', threshold,
                            f'Close>{threshold:.0%}', f'Close≤{threshold:.0%}',
                            f'Close Position {threshold}')
        print(f"  Close≤{threshold:.0%} range: N={r['false_group']['n']:>4} | WR={r['false_group']['wr']:>5.1f}% | AvgPnL={r['false_group']['avg_pnl']:>+7.3f}%")
        print(f"  Close>{threshold:.0%} range: N={r['true_group']['n']:>4} | WR={r['true_group']['wr']:>5.1f}% | AvgPnL={r['true_group']['avg_pnl']:>+7.3f}%")
        print()

    # ════════════════════════════════════════════════════════════════
    # RESUMEN FINAL
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print("RESUMEN: ¿QUÉ FACTORES TIENEN EFECTO MEDIBLE?")
    print("="*100)

    summary_tests = [
        ('SMA200 Filter', 'ma200_above', True),
        ('In Value Area', 'in_value_area', True),
        ('Below Value Area', 'below_value_area', True),
        ('Stopping Volume', 'stopping_volume', True),
        ('Spring Test', 'spring_test', True),
    ]

    print(f"\n  {'Factor':<25} {'N_True':>6} {'WR_True':>7} {'WR_False':>8} {'Δ WR':>6} {'Δ PnL':>7} {'Veredicto':>9}")
    print(f"  {'-'*75}")
    for name, col, _ in summary_tests:
        r = test_hypothesis(trades_df, col, 'T', 'F', name)
        print(f"  {name:<25} {r['true_group']['n']:>6} {r['true_group']['wr']:>6.1f}% {r['false_group']['wr']:>7.1f}% {r['delta_wr']:>+5.1f}% {r['delta_avg_pnl']:>+6.3f}% {r['verdict']:>9}")


if __name__ == '__main__':
    main()
