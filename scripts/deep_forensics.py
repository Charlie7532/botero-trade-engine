#!/usr/bin/env python3
"""
DEEP TRADE FORENSICS V2 — Oscillation & Timing Analysis
=========================================================
For EACH trade the simulator takes, analyzes:
1. Price oscillation after entry (MFE/MAE per hour/day)
2. Optimal entry timing (could we have entered better?)
3. Optimal exit timing (where was max profit?)
4. WHY winners won and losers lost
5. Extracts RULES for perfect entry/exit
"""
import sys, os, json
import pandas as pd
import numpy as np
from datetime import datetime, date
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))
from application.entry_intelligence_hub import EntryIntelligenceHub
from dotenv import load_dotenv
load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CACHE_FILE = os.path.join(DATA_DIR, "sim_7d_cache.json")

def load_cache():
    with open(CACHE_FILE, 'r') as f:
        return json.load(f)

def get_all_dates(cache):
    prices = cache.get("prices", {})
    sample = prices.get("AAPL", prices.get("MSFT", {}))
    return sorted(sample.keys())

def get_price_series(cache, ticker, all_dates):
    """Get full price dict for a ticker."""
    return cache.get("prices", {}).get(ticker, {})

def analyze_oscillation(prices_dict, entry_date, entry_price, all_dates):
    """Analyze price behavior after entry."""
    entry_idx = all_dates.index(entry_date) if entry_date in all_dates else -1
    if entry_idx < 0:
        return {}
    
    # Get prices for days after entry
    forward_days = []
    for i in range(entry_idx, min(entry_idx + 10, len(all_dates))):
        d = all_dates[i]
        p = prices_dict.get(d, {})
        if p:
            forward_days.append({
                'date': d,
                'day_offset': i - entry_idx,
                'open': p['Open'],
                'high': p['High'],
                'low': p['Low'],
                'close': p['Close'],
                'volume': p['Volume'],
                'pnl_close': ((p['Close'] / entry_price) - 1) * 100,
                'mfe': ((p['High'] / entry_price) - 1) * 100,  # Max favorable
                'mae': ((p['Low'] / entry_price) - 1) * 100,   # Max adverse
            })
    
    # Get prices before entry for context
    lookback_days = []
    for i in range(max(0, entry_idx - 5), entry_idx):
        d = all_dates[i]
        p = prices_dict.get(d, {})
        if p:
            lookback_days.append({
                'date': d,
                'close': p['Close'],
                'high': p['High'],
                'low': p['Low'],
                'volume': p['Volume'],
            })
    
    if not forward_days:
        return {}
    
    # Calculate running MFE/MAE
    running_mfe = 0
    running_mae = 0
    best_exit_day = 0
    best_exit_pnl = -999
    
    for fd in forward_days:
        running_mfe = max(running_mfe, fd['mfe'])
        running_mae = min(running_mae, fd['mae'])
        if fd['pnl_close'] > best_exit_pnl:
            best_exit_pnl = fd['pnl_close']
            best_exit_day = fd['day_offset']
    
    # Pre-entry momentum
    if lookback_days:
        pre_momentum = ((lookback_days[-1]['close'] / lookback_days[0]['close']) - 1) * 100 if len(lookback_days) > 1 else 0
        pre_volume_trend = lookback_days[-1]['volume'] / np.mean([d['volume'] for d in lookback_days]) if lookback_days else 1
    else:
        pre_momentum = 0
        pre_volume_trend = 1
    
    return {
        'forward_days': forward_days,
        'lookback_days': lookback_days,
        'running_mfe': running_mfe,
        'running_mae': running_mae,
        'best_exit_day': best_exit_day,
        'best_exit_pnl': best_exit_pnl,
        'final_pnl': forward_days[-1]['pnl_close'] if forward_days else 0,
        'pre_momentum': pre_momentum,
        'pre_volume_trend': pre_volume_trend,
        'entry_day_range': forward_days[0]['mfe'] - forward_days[0]['mae'] if forward_days else 0,
    }


def simulate_and_forensics(cache):
    """Run simulation and deep forensic analysis on every trade."""
    all_dates = get_all_dates(cache)
    universe = cache.get("metadata", {}).get("tickers", [])
    flow_all = cache.get("flow", {})
    
    sim_dates = all_dates[-5:]
    print(f"Simulation: {sim_dates[0]} → {sim_dates[-1]}")
    print(f"Universe: {len(universe)} tickers\n")
    
    # Collect all trades with full context
    all_trades = []
    missed_trades = []  # Fix #3: Contrafactual STALK/BLOCK trades
    
    hub = EntryIntelligenceHub()
    mock_journal = type('obj', (object,), {'find_similar_trades': lambda self, vec, limit: []})()
    hub.journal = mock_journal
    
    macro_spy = cache.get("macro", {}).get("spy_ticks", [])
    macro_tide = cache.get("macro", {}).get("tide", [])
    
    import logging
    for name in ['application', 'infrastructure']:
        logging.getLogger(name).setLevel(logging.ERROR)
    
    for day_idx, current_date in enumerate(sim_dates):
        # Identify tactical movers
        tactical_tickers = set()
        if day_idx > 0:
            prev_date = sim_dates[day_idx - 1]
            for ticker in universe:
                tp = cache["prices"].get(ticker, {})
                today = tp.get(current_date, {})
                yesterday = tp.get(prev_date, {})
                if today and yesterday and yesterday.get('Close', 0) > 0:
                    gap = ((today['Open'] / yesterday['Close']) - 1) * 100
                    rvol_raw = today['Volume'] / yesterday['Volume'] if yesterday['Volume'] > 0 else 1
                    if abs(gap) > 3 or rvol_raw > 2.0:
                        tactical_tickers.add(ticker)
        
        for ticker in universe:
            tp = cache["prices"].get(ticker, {})
            
            # Build price DataFrame up to current_date
            valid_dates = sorted([d for d in tp.keys() if d <= current_date])
            if len(valid_dates) < 20:
                continue
            
            rows = []
            for d in valid_dates:
                row = tp[d].copy()
                row["Date"] = pd.to_datetime(d)
                rows.append(row)
            prices_df = pd.DataFrame(rows).set_index("Date")
            
            recent_flow = [f for f in flow_all.get(ticker, []) if f.get('date', '') <= current_date]
            dp = cache.get("darkpool", {}).get(ticker, [])
            
            hub.inject_uw_data(
                spy_ticks=macro_spy, tide_data=macro_tide,
                flow_alerts=recent_flow, recent_flow=recent_flow,
                darkpool_prints=dp
            )
            
            vix = cache["prices"].get("^VIX", {}).get(current_date, 18.0)
            if isinstance(vix, dict):
                vix = vix.get('Close', 18.0) if 'Close' in vix else 18.0
            
            close_price = prices_df['Close'].iloc[-1]
            atr_f = float((prices_df['High'] - prices_df['Low']).rolling(14).mean().iloc[-1]) if len(prices_df) >= 14 else float(close_price) * 0.02
            c_f = float(close_price)
            hub._fetch_options_data = lambda t, c=c_f, a=atr_f: {
                "put_wall": round(c - 2.0 * a, 2),
                "call_wall": round(c + 3.0 * a, 2),
                "gamma_regime": "POSITIVE" if vix < 20 else "NEGATIVE",
                "max_pain": round(c, 2),
            }
            
            strategy = "TACTICAL" if ticker in tactical_tickers else "CORE"
            ref_date = date.fromisoformat(current_date)
            
            report = hub.evaluate(ticker, reference_date=ref_date, prices_df=prices_df, 
                                  vix_override=vix, strategy_bucket=strategy)
            
            # === BUILD FULL FEATURE VECTOR (Fix #1+#2) ===
            entry_price = float(prices_df['Close'].iloc[-1])
            
            # Market context
            flow_data = sorted([f for f in flow_all.get(ticker, []) if f.get('date','') <= current_date],
                               key=lambda x: x.get('date',''), reverse=True)[:5]
            bull_prem = sum(float(f.get('bullish_premium', 0) or 0) for f in flow_data[:1])
            bear_prem = sum(float(f.get('bearish_premium', 0) or 0) for f in flow_data[:1])
            bb_ratio = bull_prem / max(bear_prem, 1) if bear_prem > 0 else (2.0 if bull_prem > 0 else 1.0)
            prev_close_list = [tp.get(d, {}).get('Close', 0) for d in sorted(tp.keys()) if d < current_date]
            prev_close = prev_close_list[-1] if prev_close_list else entry_price
            gap_pct = ((tp[current_date]['Open'] / prev_close) - 1) * 100 if prev_close > 0 else 0
            intraday_pct = ((tp[current_date]['Close'] / tp[current_date]['Open']) - 1) * 100 if tp[current_date]['Open'] > 0 else 0
            
            feature_row = {
                # Identity
                'ticker': ticker, 'entry_date': current_date, 'entry_price': entry_price,
                'strategy': strategy, 'final_verdict': report.final_verdict,
                'final_reason': getattr(report, 'final_reason', ''),
                'final_scale': getattr(report, 'final_scale', 0.0),
                # Phase (¿CUÁNDO?)
                'phase': report.phase,
                'phase_confidence': getattr(report, 'phase_confidence', 0.0),
                'dimensions_confirming': getattr(report, 'dimensions_confirming', 0),
                'risk_reward': report.risk_reward,
                # Price Technicals (¿QUÉ DICE EL PRECIO?)
                'rsi': report.rsi, 'atr': getattr(report, 'atr', 0.0),
                'rvol': getattr(report, 'rvol', 1.0),
                'rs_vs_spy': getattr(report, 'rs_vs_spy', 1.0),
                'vix': getattr(report, 'vix', 17.0),
                # Whale/Flow (¿QUÉ HACEN LOS INSTITUCIONALES?)
                'whale_verdict': report.whale_verdict,
                'whale_confidence': getattr(report, 'whale_confidence', 0.0),
                'whale_scale': getattr(report, 'whale_scale', 1.0),
                'flow_grade': report.flow_persistence_grade,
                'flow_freshness': getattr(report, 'flow_freshness_weight', 1.0),
                'flow_consecutive_days': getattr(report, 'flow_consecutive_days', 0),
                'flow_darkpool': getattr(report, 'flow_darkpool_confirmed', False),
                'spy_signal': getattr(report, 'spy_signal', 'NEUTRAL'),
                'tide_direction': getattr(report, 'tide_direction', 'NEUTRAL'),
                # Volume Profile (¿DÓNDE ESTÁN LOS INSTITUCIONALES?)
                'vp_shape_short': getattr(report, 'vp_shape_short', 'D'),
                'vp_shape_long': getattr(report, 'vp_shape_long', 'D'),
                'vp_poc_migration': getattr(report, 'vp_poc_migration', 'NEUTRAL'),
                'vp_institutional_bias': getattr(report, 'vp_institutional_bias', 'NEUTRAL'),
                'vp_bias_confidence': getattr(report, 'vp_bias_confidence', 0.0),
                'vp_price_vs_va': getattr(report, 'vp_price_vs_va', 'UNKNOWN'),
                'vp_poc_short': getattr(report, 'vp_poc_short', 0.0),
                'vp_val_short': getattr(report, 'vp_val_short', 0.0),
                'vp_vah_short': getattr(report, 'vp_vah_short', 0.0),
                # Gamma/Options (¿QUÉ DICEN LAS OPCIONES?)
                'gamma_regime': getattr(report, 'gamma_regime', 'UNKNOWN'),
                'wyckoff_state': getattr(report, 'wyckoff_state', 'UNKNOWN'),
                # Pattern Intelligence (¿QUÉ VE EL PRECIO?)
                'pattern': getattr(report, 'candlestick_pattern', 'NONE'),
                'pattern_sentiment': getattr(report, 'pattern_sentiment', 'NEUTRAL'),
                'pattern_score': getattr(report, 'pattern_score', 0.0),
                'pattern_on_support': getattr(report, 'pattern_on_support', False),
                'pattern_confirms': getattr(report, 'pattern_confirms', False),
                # RSI Intelligence (Cardwell/Brown)
                'rsi_regime': getattr(report, 'rsi_regime', 'NEUTRAL'),
                'rsi_zone': getattr(report, 'rsi_zone', 'NEUTRAL'),
                'rsi_divergence': getattr(report, 'rsi_divergence', 'NONE'),
                'rsi_divergence_strength': getattr(report, 'rsi_divergence_strength', 0.0),
                'rsi_price_slope': getattr(report, 'rsi_price_slope', 0.0),
                'rsi_indicator_slope': getattr(report, 'rsi_indicator_slope', 0.0),
                'rsi_slope_alignment': getattr(report, 'rsi_slope_alignment', 'ALIGNED'),
                'rsi_conviction': getattr(report, 'rsi_conviction', 0.0),
                # Market context
                'gap_pct': round(gap_pct, 2), 'intraday_pct': round(intraday_pct, 2),
                'bb_ratio': round(bb_ratio, 2), 'stop_price': report.stop_price,
            }
            
            if report.final_verdict == "EXECUTE":
                osc = analyze_oscillation(tp, current_date, entry_price, all_dates)
                all_trades.append({**feature_row, **osc})
            
            # === Fix #3: CONTRAFACTUAL — Track STALK/BLOCK outcomes ===
            elif report.final_verdict in ("STALK", "BLOCK"):
                osc = analyze_oscillation(tp, current_date, entry_price, all_dates)
                if osc.get('running_mfe', 0) > 0.5:  # Would have seen >0.5% gain
                    missed_trades.append({**feature_row, **osc, 'was_missed': True})
    
    return all_trades, missed_trades

def print_forensics(trades, missed_trades=None):
    """Deep print of forensic findings."""
    print("="*80)
    print("  DEEP TRADE FORENSICS V3 — Full Feature + Contrafactual")
    print("="*80)
    
    winners = [t for t in trades if t.get('final_pnl', 0) > 0]
    losers = [t for t in trades if t.get('final_pnl', 0) <= 0]
    
    print(f"\nExecuted: {len(trades)} | Winners: {len(winners)} | Losers: {len(losers)}")
    print(f"Win Rate: {len(winners)/max(len(trades),1)*100:.0f}%")
    if missed_trades:
        missed_winners = [t for t in missed_trades if t.get('final_pnl', 0) > 0]
        print(f"Missed (STALK/BLOCK with MFE>0.5%): {len(missed_trades)} | Would-be Winners: {len(missed_winners)}")
    
    # === TRADE BY TRADE ===
    print("\n" + "─"*80)
    print("  TRADE-BY-TRADE ANALYSIS")
    print("─"*80)
    
    def avg(lst, key):
        vals = [t.get(key, 0) for t in lst if t.get(key) is not None]
        return np.mean(vals) if vals else 0
    
    for t in sorted(trades, key=lambda x: x.get('final_pnl', 0), reverse=True):
        emoji = "✅" if t.get('final_pnl', 0) > 0 else "❌"
        print(f"\n{emoji} {t['ticker']} ({t['strategy']}/{t['phase']}) — {t['entry_date']} @ ${t['entry_price']:.2f}")
        print(f"   RSI={t.get('rsi',0):.0f} | RVOL={t.get('rvol',1):.1f}x | Gap={t['gap_pct']:+.1f}% | Pat={t.get('pattern', 'NONE')}")
        print(f"   VP: {t.get('vp_shape_short','?')}/{t.get('vp_shape_long','?')} | Bias={t.get('vp_institutional_bias','?')} | POC_mig={t.get('vp_poc_migration','?')}")
        print(f"   PnL: {t.get('final_pnl',0):+.2f}% | MFE: {t.get('running_mfe',0):+.2f}% | MAE: {t.get('running_mae',0):+.2f}% | BestExit=D{t.get('best_exit_day',0)}")
    
    # === VOLUME PROFILE FORENSICS (Fix #1) ===
    print("\n" + "="*80)
    print("  VOLUME PROFILE CONTRIBUTION ANALYSIS")
    print("="*80)
    
    for shape in ['P', 'D', 'b']:
        st = [t for t in trades if t.get('vp_shape_short') == shape]
        if st:
            sw = [t for t in st if t.get('final_pnl', 0) > 0]
            print(f"  Short {shape}-shape: n={len(st):2d} | WR={len(sw)/len(st)*100:4.0f}% | Avg={avg(st,'final_pnl'):+.2f}%")
    
    for bias in ['ACCUMULATION', 'DISTRIBUTION', 'NEUTRAL']:
        st = [t for t in trades if t.get('vp_institutional_bias') == bias]
        if st:
            sw = [t for t in st if t.get('final_pnl', 0) > 0]
            print(f"  VP Bias {bias:14s}: n={len(st):2d} | WR={len(sw)/len(st)*100:4.0f}% | Avg={avg(st,'final_pnl'):+.2f}%")
    
    for mig in ['BULLISH', 'BEARISH', 'NEUTRAL']:
        st = [t for t in trades if t.get('vp_poc_migration') == mig]
        if st:
            sw = [t for t in st if t.get('final_pnl', 0) > 0]
            print(f"  POC Migration {mig:8s}: n={len(st):2d} | WR={len(sw)/len(st)*100:4.0f}% | Avg={avg(st,'final_pnl'):+.2f}%")
    
    # === PATTERN ANALYSIS ===
    print("\n" + "="*80)
    print("  PATTERN INTELLIGENCE CONTRIBUTION")
    print("="*80)
    
    metrics = ['rsi', 'rvol', 'rs_vs_spy', 'vix', 'atr', 'gap_pct', 'pattern_score',
               'vp_bias_confidence', 'whale_confidence', 'dimensions_confirming',
               'running_mfe', 'running_mae', 'pre_momentum']
    
    print(f"\n{'Metric':25s} | {'Winners':>10s} | {'Losers':>10s} | {'Delta':>10s}")
    print("─"*65)
    for m in metrics:
        w = avg(winners, m)
        l = avg(losers, m)
        print(f"{m:25s} | {w:+10.2f} | {l:+10.2f} | {w-l:+10.2f}")
        
    print("\n  By Pattern Sentiment:")
    for sent in ["BULLISH", "BEARISH", "NEUTRAL"]:
        st = [t for t in trades if t.get('pattern_sentiment') == sent]
        if st:
            sw = [t for t in st if t.get('final_pnl', 0) > 0]
            print(f"  {sent:10s}: n={len(st):2d} | WR={len(sw)/len(st)*100:4.0f}% | Avg={avg(st,'final_pnl'):+.2f}%")
    
    patterns = set(t.get('pattern', 'NONE') for t in trades if t.get('pattern', 'NONE') != 'NONE')
    if patterns:
        print("\n  By Specific Pattern:")
        for pat in sorted(patterns):
            pt = [t for t in trades if t.get('pattern') == pat]
            pw = [t for t in pt if t.get('final_pnl', 0) > 0]
            print(f"  {pat:22s}: n={len(pt):2d} | WR={len(pw)/len(pt)*100:4.0f}% | Avg={avg(pt,'final_pnl'):+.2f}%")
    
    # === STRATEGY BREAKDOWN ===
    print("\n" + "="*80)
    print("  STRATEGY BREAKDOWN")
    print("="*80)
    
    for strat in ['CORE', 'TACTICAL']:
        st = [t for t in trades if t['strategy'] == strat]
        if not st:
            continue
        sw = [t for t in st if t.get('final_pnl', 0) > 0]
        print(f"\n  {strat}: {len(st)} trades | WR={len(sw)/len(st)*100:.0f}%")
        print(f"    Avg PnL: {avg(st,'final_pnl'):+.2f}% | Avg MFE: {avg(st,'running_mfe'):+.2f}% | Avg MAE: {avg(st,'running_mae'):+.2f}%")
        phases = set(t['phase'] for t in st)
        for phase in phases:
            pt = [t for t in st if t['phase'] == phase]
            pw = [t for t in pt if t.get('final_pnl', 0) > 0]
            print(f"    {phase}: {len(pt)} trades | WR={len(pw)/len(pt)*100:.0f}% | Avg={avg(pt,'final_pnl'):+.2f}%")
    
    # === CONTRAFACTUAL (Fix #3) ===
    if missed_trades:
        print("\n" + "="*80)
        print("  CONTRAFACTUAL: MISSED TRADES (STALK/BLOCK con MFE > 0.5%)")
        print("="*80)
        missed_winners = [t for t in missed_trades if t.get('final_pnl', 0) > 0]
        print(f"\n  Total missed: {len(missed_trades)} | Would-be Winners: {len(missed_winners)} ({len(missed_winners)/max(len(missed_trades),1)*100:.0f}%)")
        print(f"  Avg MFE missed: {avg(missed_trades, 'running_mfe'):+.2f}%")
        print(f"  Avg final PnL if held: {avg(missed_trades, 'final_pnl'):+.2f}%")
        
        by_reason = defaultdict(list)
        for t in missed_trades:
            reason = t.get('final_reason', '')[:40]
            by_reason[reason].append(t)
        print("\n  By Block Reason:")
        for reason, ts in sorted(by_reason.items(), key=lambda x: -len(x[1]))[:8]:
            tw = [t for t in ts if t.get('final_pnl', 0) > 0]
            print(f"  {reason:42s} | n={len(ts):3d} | WouldWin={len(tw)/len(ts)*100:4.0f}% | AvgMFE={avg(ts,'running_mfe'):+.1f}%")
    
    # === CSV EXPORT FOR ML ===
    print("\n" + "="*80)
    print("  CSV EXPORT FOR ML/AI")
    print("="*80)
    
    import os
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    
    all_data = [{**t, 'was_missed': False} for t in trades] + (missed_trades or [])
    if all_data:
        df = pd.DataFrame(all_data)
        csv_path = os.path.join(DATA_DIR, "forensic_ml_dataset.csv")
        df.to_csv(csv_path, index=False)
        print(f"  ✅ Exported {len(df)} rows ({len(trades)} executed + {len(missed_trades or [])} missed) → {csv_path}")
        print(f"  Features: {len(df.columns)} columns")
        print(f"  Ready for: Random Forest, XGBoost, SHAP, Ablation Study")


def main():
    print("Loading cache...")
    cache = load_cache()
    
    print("Running simulation + forensics...\n")
    trades, missed_trades = simulate_and_forensics(cache)
    
    if not trades:
        print("No trades generated!")
        return
    
    print_forensics(trades, missed_trades)

if __name__ == "__main__":
    main()
