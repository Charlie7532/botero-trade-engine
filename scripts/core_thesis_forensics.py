#!/usr/bin/env python3
"""
CORE THESIS FORENSICS — "Are we self-sabotaging?"
====================================================
The CORE bucket has 13% WR (87% LOSERS). Inverted, this is 87% accuracy.
This script investigates whether we're entering at DISTRIBUTION instead of
ACCUMULATION — systematically buying what smart money is selling.

Hypothesis: Our CORRECTION phase misidentifies DISTRIBUTION as ACCUMULATION.
If we can detect the actual Wyckoff phase, we flip our edge.

Analysis:
1. For each CORE entry, reconstruct the FULL price structure (20d+)
2. Calculate Wyckoff state from volume + price dynamics
3. Check if "healthy pullback" was actually "early markdown"
4. Compare winners vs losers structural patterns
5. Propose structural filters to fix the signal
"""
import sys, os, json
import pandas as pd
import numpy as np
from datetime import datetime, date
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))
from modules.volume_intelligence.kalman_engine import KalmanVolumeTracker, SectorRegimeDetector
from modules.entry_decision.hub import EntryIntelligenceHub
from dotenv import load_dotenv
load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CACHE_FILE = os.path.join(DATA_DIR, "sim_7d_cache.json")

def load_cache():
    with open(CACHE_FILE, 'r') as f:
        return json.load(f)

def analyze_structure(prices_dict, entry_date, all_dates):
    """
    Deep structural analysis of a stock at entry point.
    Reconstruct what was ACTUALLY happening in the price structure.
    """
    entry_idx = all_dates.index(entry_date) if entry_date in all_dates else -1
    if entry_idx < 20:
        return {}
    
    # Get 40 days of history before entry
    lookback = min(entry_idx, 40)
    hist_dates = all_dates[entry_idx - lookback: entry_idx + 1]
    
    closes = []
    highs = []
    lows = []
    volumes = []
    opens = []
    
    for d in hist_dates:
        p = prices_dict.get(d, {})
        if p and p.get('Close', 0) > 0:
            closes.append(p['Close'])
            highs.append(p['High'])
            lows.append(p['Low'])
            volumes.append(p['Volume'])
            opens.append(p['Open'])
    
    if len(closes) < 20:
        return {}
    
    closes = np.array(closes, dtype=float)
    highs = np.array(highs, dtype=float)
    lows = np.array(lows, dtype=float)
    volumes = np.array(volumes, dtype=float)
    
    # === STRUCTURAL ANALYSIS ===
    
    # 1. TREND DIRECTION (20d linear regression slope)
    x = np.arange(len(closes[-20:]))
    slope = np.polyfit(x, closes[-20:], 1)[0]
    trend_slope_pct = (slope / closes[-20]) * 100  # % per day
    
    # 2. HIGHER HIGHS / LOWER LOWS analysis (last 20 days)
    recent_highs = highs[-20:]
    recent_lows = lows[-20:]
    
    # Count HH/HL vs LH/LL in 5-day windows
    hh_count = 0
    ll_count = 0
    for i in range(4, len(recent_highs), 5):
        window = recent_highs[max(0,i-4):i+1]
        if len(window) >= 2:
            if window[-1] > window[0]:
                hh_count += 1
            else:
                ll_count += 1
    
    # 3. VOLUME DISTRIBUTION ANALYSIS
    # Key question: Is volume EXPANDING on down days or up days?
    up_days = []
    down_days = []
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            up_days.append(volumes[i])
        else:
            down_days.append(volumes[i])
    
    avg_up_vol = np.mean(up_days) if up_days else 1
    avg_down_vol = np.mean(down_days) if down_days else 1
    up_down_vol_ratio = avg_up_vol / avg_down_vol if avg_down_vol > 0 else 1.0
    
    # Last 5 days specifically
    recent_up_vol = []
    recent_down_vol = []
    for i in range(-5, 0):
        if closes[i] > closes[i-1]:
            recent_up_vol.append(volumes[i])
        else:
            recent_down_vol.append(volumes[i])
    
    recent_up_down_ratio = (np.mean(recent_up_vol) / np.mean(recent_down_vol) 
                           if recent_down_vol and recent_up_vol else 1.0)
    
    # 4. WYCKOFF via Kalman (per-stock)
    kalman = KalmanVolumeTracker()
    avg_vol = np.mean(volumes[-20:])
    wyckoff_states = []
    for i in range(-20, 0):
        rvol = volumes[i] / avg_vol if avg_vol > 0 else 1.0
        change_pct = ((closes[i] / closes[i-1]) - 1) * 100 if i > -20 else 0
        result = kalman.update("stock", rvol, change_pct)
        wyckoff_states.append(result['wyckoff_state'])
    
    # Most recent Wyckoff state
    latest_wyckoff = wyckoff_states[-1] if wyckoff_states else "UNKNOWN"
    
    # Wyckoff trajectory (what direction is the state moving?)
    state_sequence = " → ".join(wyckoff_states[-5:])
    
    # 5. DISTRIBUTION SCORE (0-100)
    # Higher = more likely distribution (smart money selling)
    dist_score = 0
    
    # Volume expanding on down days = distribution
    if up_down_vol_ratio < 0.8:
        dist_score += 25
    elif up_down_vol_ratio < 1.0:
        dist_score += 10
    
    # Recent volume shift (last 5 days more selling volume)
    if recent_up_down_ratio < 0.7:
        dist_score += 20
    
    # Negative trend slope
    if trend_slope_pct < -0.1:
        dist_score += 15
    elif trend_slope_pct < 0:
        dist_score += 5
    
    # Lower highs pattern
    if ll_count > hh_count:
        dist_score += 15
    
    # Wyckoff says distribution or markdown
    if latest_wyckoff in ("DISTRIBUTION", "MARKDOWN"):
        dist_score += 25
    elif latest_wyckoff == "CONSOLIDATION":
        dist_score += 10
    
    # 6. ACCUMULATION SCORE (0-100)
    acc_score = 0
    
    # Volume expanding on up days
    if up_down_vol_ratio > 1.2:
        acc_score += 25
    elif up_down_vol_ratio > 1.0:
        acc_score += 10
    
    # Recent volume shift (last 5 days more buying volume)
    if recent_up_down_ratio > 1.3:
        acc_score += 20
    
    # Positive trend
    if trend_slope_pct > 0.1:
        acc_score += 15
    elif trend_slope_pct > 0:
        acc_score += 5
    
    # Higher highs
    if hh_count > ll_count:
        acc_score += 15
    
    # Wyckoff says accumulation or markup
    if latest_wyckoff in ("ACCUMULATION", "MARKUP"):
        acc_score += 25
    
    # 7. SUPPORT/RESISTANCE context
    # Is price near the 20d LOW (support test) or near 20d HIGH (resistance)?
    current = closes[-1]
    high_20d = np.max(highs[-20:])
    low_20d = np.min(lows[-20:])
    range_20d = high_20d - low_20d
    
    position_in_range = (current - low_20d) / range_20d if range_20d > 0 else 0.5
    
    # Forward returns for labeling
    forward_dates = all_dates[entry_idx + 1: entry_idx + 6]
    fwd_closes = []
    for fd in forward_dates:
        fp = prices_dict.get(fd, {})
        if fp and fp.get('Close', 0) > 0:
            fwd_closes.append(fp['Close'])
    
    fwd_5d = ((fwd_closes[-1] / current) - 1) * 100 if fwd_closes else 0
    fwd_max = ((max([prices_dict.get(fd, {}).get('High', current) for fd in forward_dates]) / current) - 1) * 100 if forward_dates else 0
    
    return {
        'trend_slope_pct': round(trend_slope_pct, 3),
        'up_down_vol_ratio': round(up_down_vol_ratio, 2),
        'recent_up_down_ratio': round(recent_up_down_ratio, 2),
        'hh_count': hh_count,
        'll_count': ll_count,
        'latest_wyckoff': latest_wyckoff,
        'wyckoff_sequence': state_sequence,
        'distribution_score': dist_score,
        'accumulation_score': acc_score,
        'position_in_range': round(position_in_range, 2),
        'fwd_5d': round(fwd_5d, 2),
        'fwd_max': round(fwd_max, 2),
        'is_winner': fwd_5d > 0,
    }


def main():
    print("Loading cache...")
    cache = load_cache()
    all_dates = sorted(cache["prices"].get("AAPL", {}).keys())
    universe = cache["metadata"]["tickers"]
    flow_all = cache.get("flow", {})
    sim_dates = all_dates[-5:]
    
    print(f"Analyzing structural context for ALL universe entries...")
    print(f"Sim dates: {sim_dates[0]} → {sim_dates[-1]}")
    
    # Run the Hub to identify which tickers get EXECUTE with CORE
    hub = EntryIntelligenceHub()
    hub.journal = type('obj', (object,), {'find_similar_trades': lambda self, vec, limit: []})()
    macro_spy = cache.get("macro", {}).get("spy_ticks", [])
    macro_tide = cache.get("macro", {}).get("tide", [])
    
    import logging
    for name in ['application', 'infrastructure']:
        logging.getLogger(name).setLevel(logging.ERROR)
    
    all_structural = []
    
    # Analyze the ENTIRE universe — not just EXECUTE trades
    # This lets us compare accepted vs rejected for bias detection
    for day_idx, current_date in enumerate(sim_dates):
        tactical_tickers = set()
        if day_idx > 0:
            prev_date = sim_dates[day_idx - 1]
            for ticker in universe:
                tp = cache["prices"].get(ticker, {})
                today = tp.get(current_date, {})
                yesterday = tp.get(prev_date, {})
                if today and yesterday and yesterday.get('Close', 0) > 0:
                    gap = abs((today['Open'] / yesterday['Close']) - 1) * 100
                    rvol = today['Volume'] / yesterday['Volume'] if yesterday['Volume'] > 0 else 1
                    if gap > 3 or rvol > 2.0:
                        tactical_tickers.add(ticker)
        
        for ticker in universe:
            tp = cache["prices"].get(ticker, {})
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
            
            hub.inject_uw_data(spy_ticks=macro_spy, tide_data=macro_tide,
                             flow_alerts=recent_flow, recent_flow=recent_flow,
                             darkpool_prints=dp)
            
            close = float(prices_df['Close'].iloc[-1])
            hub._fetch_options_data = lambda t: {
                "put_wall": close * 0.95, "call_wall": close * 1.05,
                "gamma_regime": "POSITIVE", "max_pain": close
            }
            
            strategy = "TACTICAL" if ticker in tactical_tickers else "CORE"
            if strategy != "CORE":
                continue  # Focus on CORE only
            
            ref_date = date.fromisoformat(current_date)
            report = hub.evaluate(ticker, reference_date=ref_date, prices_df=prices_df,
                                vix_override=18.0, strategy_bucket="CORE")
            
            # Get structural analysis regardless of verdict
            struct = analyze_structure(tp, current_date, all_dates)
            if not struct:
                continue
            
            struct['ticker'] = ticker
            struct['date'] = current_date
            struct['verdict'] = report.final_verdict
            struct['phase'] = report.phase
            struct['rsi'] = report.rsi
            struct['flow_grade'] = report.flow_persistence_grade
            
            all_structural.append(struct)
    
    # === ANALYSIS ===
    df = pd.DataFrame(all_structural)
    
    print(f"\n{'='*80}")
    print(f"  CORE THESIS FORENSICS — Structural Analysis")
    print(f"{'='*80}")
    print(f"\nTotal CORE evaluations with structure: {len(df)}")
    
    executed = df[df['verdict'] == 'EXECUTE']
    stalked = df[df['verdict'] == 'STALK']
    blocked = df[df['verdict'] == 'BLOCK']
    
    print(f"  EXECUTE: {len(executed)} | STALK: {len(stalked)} | BLOCK: {len(blocked)}")
    
    if len(executed) > 0:
        exe_win = executed[executed['is_winner'] == True]
        exe_lose = executed[executed['is_winner'] == False]
        print(f"\n  EXECUTED trades: {len(executed)}")
        print(f"    Winners: {len(exe_win)} ({len(exe_win)/len(executed)*100:.0f}%)")
        print(f"    Losers: {len(exe_lose)} ({len(exe_lose)/len(executed)*100:.0f}%)")
    
    # THE KEY QUESTION: What structural features separate winners from losers?
    print(f"\n{'─'*80}")
    print(f"  STRUCTURAL COMPARISON: Winners vs Losers (EXECUTED only)")
    print(f"{'─'*80}")
    
    if len(executed) > 0:
        for col in ['trend_slope_pct', 'up_down_vol_ratio', 'recent_up_down_ratio',
                     'distribution_score', 'accumulation_score', 'position_in_range',
                     'latest_wyckoff', 'rsi', 'fwd_5d', 'fwd_max']:
            if col in ['latest_wyckoff']:
                if len(exe_win) > 0:
                    print(f"\n  {col}:")
                    print(f"    Winners: {exe_win[col].value_counts().to_dict()}")
                    print(f"    Losers:  {exe_lose[col].value_counts().to_dict()}")
            else:
                w_avg = exe_win[col].mean() if len(exe_win) > 0 else 0
                l_avg = exe_lose[col].mean() if len(exe_lose) > 0 else 0
                print(f"  {col:30s} | Winners: {w_avg:+8.2f} | Losers: {l_avg:+8.2f} | Δ={w_avg-l_avg:+.2f}")
    
    # THE INVERSION TEST: Are the STALKED/BLOCKED trades actually winners?
    print(f"\n{'─'*80}")
    print(f"  INVERSION TEST: Are REJECTED trades actually better?")
    print(f"{'─'*80}")
    
    for verdict in ['STALK', 'BLOCK', 'EXECUTE']:
        subset = df[df['verdict'] == verdict]
        if len(subset) > 0:
            wr = subset['is_winner'].mean() * 100
            avg_5d = subset['fwd_5d'].mean()
            avg_max = subset['fwd_max'].mean()
            avg_dist = subset['distribution_score'].mean()
            avg_acc = subset['accumulation_score'].mean()
            print(f"  {verdict:10s}: n={len(subset):4d} | WR={wr:5.1f}% | avg_5d={avg_5d:+.2f}% | avg_max={avg_max:+.2f}% | dist_score={avg_dist:.0f} | acc_score={avg_acc:.0f}")
    
    # WYCKOFF STATE ANALYSIS
    print(f"\n{'─'*80}")
    print(f"  WYCKOFF STATE ANALYSIS (All CORE candidates)")
    print(f"{'─'*80}")
    
    for state in ['ACCUMULATION', 'MARKUP', 'DISTRIBUTION', 'MARKDOWN', 'CONSOLIDATION', 'UNKNOWN']:
        subset = df[df['latest_wyckoff'] == state]
        if len(subset) > 0:
            wr = subset['is_winner'].mean() * 100
            avg_5d = subset['fwd_5d'].mean()
            print(f"  {state:15s}: n={len(subset):4d} | WR={wr:5.1f}% | avg_5d={avg_5d:+.2f}%")
    
    # DISTRIBUTION SCORE ANALYSIS
    print(f"\n{'─'*80}")
    print(f"  DISTRIBUTION SCORE vs FORWARD RETURNS")
    print(f"{'─'*80}")
    
    for low, high in [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]:
        subset = df[(df['distribution_score'] >= low) & (df['distribution_score'] < high)]
        if len(subset) > 5:
            wr = subset['is_winner'].mean() * 100
            avg_5d = subset['fwd_5d'].mean()
            n_exec = len(subset[subset['verdict'] == 'EXECUTE'])
            print(f"  Score {low:2d}-{high:2d}: n={len(subset):4d} | WR={wr:5.1f}% | avg_5d={avg_5d:+.2f}% | EXECUTED={n_exec}")
    
    # ACCUMULATION SCORE ANALYSIS
    print(f"\n{'─'*80}")
    print(f"  ACCUMULATION SCORE vs FORWARD RETURNS")
    print(f"{'─'*80}")
    
    for low, high in [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]:
        subset = df[(df['accumulation_score'] >= low) & (df['accumulation_score'] < high)]
        if len(subset) > 5:
            wr = subset['is_winner'].mean() * 100
            avg_5d = subset['fwd_5d'].mean()
            n_exec = len(subset[subset['verdict'] == 'EXECUTE'])
            print(f"  Score {low:2d}-{high:2d}: n={len(subset):4d} | WR={wr:5.1f}% | avg_5d={avg_5d:+.2f}% | EXECUTED={n_exec}")
    
    # PROPOSED FIX
    print(f"\n{'='*80}")
    print(f"  PROPOSED STRUCTURAL FILTER")
    print(f"{'='*80}")
    
    # Test: Only enter CORE when accumulation_score > distribution_score
    acc_gt_dist = df[(df['accumulation_score'] > df['distribution_score']) & (df['verdict'] == 'EXECUTE')]
    dist_gt_acc = df[(df['distribution_score'] > df['accumulation_score']) & (df['verdict'] == 'EXECUTE')]
    
    if len(acc_gt_dist) > 0:
        wr1 = acc_gt_dist['is_winner'].mean() * 100
        print(f"  EXECUTE + acc > dist: n={len(acc_gt_dist)} | WR={wr1:.0f}% | avg_5d={acc_gt_dist['fwd_5d'].mean():+.2f}%")
    if len(dist_gt_acc) > 0:
        wr2 = dist_gt_acc['is_winner'].mean() * 100
        print(f"  EXECUTE + dist > acc: n={len(dist_gt_acc)} | WR={wr2:.0f}% | avg_5d={dist_gt_acc['fwd_5d'].mean():+.2f}%")
    
    # Test: Only enter when up_down_vol_ratio > 1.0 (more volume on up days)
    vol_confirms = df[(df['up_down_vol_ratio'] > 1.0) & (df['verdict'] == 'EXECUTE')]
    vol_against = df[(df['up_down_vol_ratio'] <= 1.0) & (df['verdict'] == 'EXECUTE')]
    
    if len(vol_confirms) > 0:
        print(f"  EXECUTE + UpVol/DownVol > 1: n={len(vol_confirms)} | WR={vol_confirms['is_winner'].mean()*100:.0f}% | avg_5d={vol_confirms['fwd_5d'].mean():+.2f}%")
    if len(vol_against) > 0:
        print(f"  EXECUTE + UpVol/DownVol ≤ 1: n={len(vol_against)} | WR={vol_against['is_winner'].mean()*100:.0f}% | avg_5d={vol_against['fwd_5d'].mean():+.2f}%")

if __name__ == "__main__":
    main()
