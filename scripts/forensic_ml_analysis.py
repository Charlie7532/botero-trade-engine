#!/usr/bin/env python3
"""
FORENSIC ML ANALYSIS — Signal-to-Outcome Correlation Engine
=============================================================
Extracts ALL available signals from the cache for every ticker-day,
correlates them with actual forward returns, and builds a statistical
model to determine which signal combinations predict profitable moves.

Output: CSV dataset + statistical summary + optimal thresholds
"""
import sys, os, json, math
import pandas as pd
import numpy as np
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CACHE_FILE = os.path.join(DATA_DIR, "sim_7d_cache.json")
OUTPUT_CSV = os.path.join(DATA_DIR, "forensic_signals.csv")

def load_cache():
    with open(CACHE_FILE, 'r') as f:
        return json.load(f)

def extract_signals(cache):
    """Extract signal features for every ticker-day pair."""
    prices_all = cache.get("prices", {})
    flow_all = cache.get("flow", {})
    universe = cache.get("metadata", {}).get("tickers", [])
    
    # Get all trading dates from a liquid ticker
    spy_dates = sorted(prices_all.get("AAPL", {}).keys())
    if len(spy_dates) < 25:
        print(f"Only {len(spy_dates)} dates available, need at least 25")
        return pd.DataFrame()
    
    # Use last 10 trading days for analysis (5 for signals, 5 for forward returns)
    analysis_dates = spy_dates[-10:]
    signal_dates = analysis_dates[:5]  # Days we generate signals
    forward_dates = analysis_dates[5:]  # Days we measure outcomes
    
    print(f"Signal dates: {signal_dates[0]} → {signal_dates[-1]}")
    print(f"Forward dates: {forward_dates[0]} → {forward_dates[-1]}")
    print(f"Universe: {len(universe)} tickers")
    
    rows = []
    for ticker in universe:
        ticker_prices = prices_all.get(ticker, {})
        ticker_flow = flow_all.get(ticker, [])
        
        if not ticker_prices:
            continue
        
        for i, sig_date in enumerate(signal_dates):
            if sig_date not in ticker_prices:
                continue
            
            today = ticker_prices[sig_date]
            
            # Get previous day for gap calculation
            prev_date = signal_dates[i-1] if i > 0 else spy_dates[spy_dates.index(sig_date)-1] if sig_date in spy_dates and spy_dates.index(sig_date) > 0 else None
            prev = ticker_prices.get(prev_date, {}) if prev_date else {}
            
            # Get 20-day history for technical indicators
            date_idx = spy_dates.index(sig_date) if sig_date in spy_dates else -1
            if date_idx < 20:
                continue
            
            hist_dates = spy_dates[date_idx-20:date_idx+1]
            closes = [ticker_prices.get(d, {}).get('Close', 0) for d in hist_dates]
            volumes = [ticker_prices.get(d, {}).get('Volume', 0) for d in hist_dates]
            highs = [ticker_prices.get(d, {}).get('High', 0) for d in hist_dates]
            lows = [ticker_prices.get(d, {}).get('Low', 0) for d in hist_dates]
            
            if not all(c > 0 for c in closes[-5:]):
                continue
            
            # === PRICE FEATURES ===
            close = today['Close']
            open_p = today['Open']
            high = today['High']
            low = today['Low']
            volume = today['Volume']
            
            gap_pct = ((open_p / prev['Close']) - 1) * 100 if prev.get('Close', 0) > 0 else 0
            intraday_pct = ((close / open_p) - 1) * 100 if open_p > 0 else 0
            daily_range_pct = ((high - low) / close) * 100 if close > 0 else 0
            
            # SMA20
            sma20 = np.mean(closes[-20:]) if len(closes) >= 20 else close
            dist_sma20_pct = ((close / sma20) - 1) * 100 if sma20 > 0 else 0
            
            # RSI 14
            deltas = np.diff(closes[-15:]) if len(closes) >= 15 else [0]
            gains = np.mean([d for d in deltas if d > 0]) if any(d > 0 for d in deltas) else 0
            losses = np.mean([abs(d) for d in deltas if d < 0]) if any(d < 0 for d in deltas) else 0.001
            rsi = 100 - (100 / (1 + gains/losses)) if losses > 0 else 50
            
            # ATR 14
            trs = []
            for j in range(1, min(15, len(closes))):
                tr = max(highs[-j] - lows[-j], abs(highs[-j] - closes[-j-1]), abs(lows[-j] - closes[-j-1]))
                trs.append(tr)
            atr = np.mean(trs) if trs else 1.0
            dist_sma20_atr = (close - sma20) / atr if atr > 0 else 0
            
            # RVOL
            avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else 1
            rvol = volume / avg_vol_20 if avg_vol_20 > 0 else 1.0
            
            # Momentum (5d return)
            if len(closes) >= 6:
                momentum_5d = ((closes[-1] / closes[-6]) - 1) * 100
            else:
                momentum_5d = 0
            
            # VCP: Volatility Contraction
            recent_atr = np.mean([highs[-j]-lows[-j] for j in range(1,6)]) if len(highs) >= 6 else atr
            vcp_ratio = recent_atr / atr if atr > 0 else 1.0
            
            # === FLOW FEATURES (from aggregate data) ===
            flow_for_date = [f for f in ticker_flow if f.get('date', '') <= sig_date]
            recent_flow = sorted(flow_for_date, key=lambda x: x.get('date',''), reverse=True)[:5]
            
            if recent_flow and 'call_volume' in recent_flow[0]:
                latest = recent_flow[0]
                call_vol = int(latest.get('call_volume', 0) or 0)
                put_vol = int(latest.get('put_volume', 0) or 0)
                cp_ratio = call_vol / max(put_vol, 1)
                
                call_ask = int(latest.get('call_volume_ask_side', 0) or 0)
                put_ask = int(latest.get('put_volume_ask_side', 0) or 0)
                ask_delta = call_ask - put_ask
                
                bp = float(latest.get('bullish_premium', 0) or 0)
                brp = float(latest.get('bearish_premium', 0) or 0)
                bull_bear_ratio = bp / max(brp, 1) if brp > 0 else (2.0 if bp > 0 else 1.0)
                net_premium_direction = 1 if bp > brp else (-1 if brp > bp else 0)
                
                # Multi-day flow consistency
                bullish_days = sum(1 for r in recent_flow 
                    if float(r.get('bullish_premium',0) or 0) > float(r.get('bearish_premium',0) or 0))
                flow_consistency = bullish_days / len(recent_flow) if recent_flow else 0.5
                
                avg_30d_cv = int(float(latest.get('avg_30_day_call_volume', 0) or 0))
                volume_spike = (call_vol / avg_30d_cv) if avg_30d_cv > 0 else 1.0
            else:
                cp_ratio = 1.0
                ask_delta = 0
                bull_bear_ratio = 1.0
                net_premium_direction = 0
                flow_consistency = 0.5
                volume_spike = 1.0
            
            # === FORWARD RETURNS (LABELS) ===
            fwd_1d = fwd_2d = fwd_3d = fwd_5d = 0.0
            fwd_max = fwd_min = 0.0
            
            future_closes = []
            future_highs = []
            future_lows = []
            for fd in forward_dates:
                fp = ticker_prices.get(fd, {})
                if fp.get('Close', 0) > 0:
                    future_closes.append(fp['Close'])
                    future_highs.append(fp.get('High', fp['Close']))
                    future_lows.append(fp.get('Low', fp['Close']))
            
            if future_closes and close > 0:
                fwd_1d = ((future_closes[0] / close) - 1) * 100 if len(future_closes) >= 1 else 0
                fwd_2d = ((future_closes[1] / close) - 1) * 100 if len(future_closes) >= 2 else fwd_1d
                fwd_3d = ((future_closes[2] / close) - 1) * 100 if len(future_closes) >= 3 else fwd_2d
                fwd_5d = ((future_closes[-1] / close) - 1) * 100
                fwd_max = ((max(future_highs) / close) - 1) * 100
                fwd_min = ((min(future_lows) / close) - 1) * 100
            
            rows.append({
                'ticker': ticker,
                'date': sig_date,
                # Price features
                'gap_pct': round(gap_pct, 2),
                'intraday_pct': round(intraday_pct, 2),
                'daily_range_pct': round(daily_range_pct, 2),
                'dist_sma20_pct': round(dist_sma20_pct, 2),
                'dist_sma20_atr': round(dist_sma20_atr, 2),
                'rsi': round(rsi, 1),
                'rvol': round(rvol, 2),
                'momentum_5d': round(momentum_5d, 2),
                'vcp_ratio': round(vcp_ratio, 2),
                'atr_pct': round(atr/close*100, 2) if close > 0 else 0,
                # Flow features
                'cp_ratio': round(cp_ratio, 3),
                'ask_delta': ask_delta,
                'bull_bear_ratio': round(bull_bear_ratio, 3),
                'net_premium_dir': net_premium_direction,
                'flow_consistency': round(flow_consistency, 2),
                'volume_spike': round(volume_spike, 2),
                # Forward returns (labels)
                'fwd_1d': round(fwd_1d, 2),
                'fwd_2d': round(fwd_2d, 2),
                'fwd_3d': round(fwd_3d, 2),
                'fwd_5d': round(fwd_5d, 2),
                'fwd_max': round(fwd_max, 2),
                'fwd_min': round(fwd_min, 2),
                'winner_3d': 1 if fwd_3d > 0 else 0,
                'winner_5d': 1 if fwd_5d > 0 else 0,
                'big_winner': 1 if fwd_max > 5 else 0,
            })
    
    return pd.DataFrame(rows)

def statistical_analysis(df):
    """Run statistical analysis on signal-to-outcome correlations."""
    print("\n" + "="*72)
    print("  FORENSIC STATISTICAL ANALYSIS")
    print("="*72)
    
    print(f"\nDataset: {len(df)} ticker-day observations")
    print(f"Win Rate (3d): {df['winner_3d'].mean()*100:.1f}%")
    print(f"Win Rate (5d): {df['winner_5d'].mean()*100:.1f}%")
    print(f"Big Winners (>5% max): {df['big_winner'].mean()*100:.1f}%")
    print(f"Avg fwd_5d: {df['fwd_5d'].mean():+.2f}%")
    
    # Correlation matrix
    features = ['gap_pct', 'intraday_pct', 'rvol', 'dist_sma20_atr', 'rsi',
                'momentum_5d', 'cp_ratio', 'bull_bear_ratio', 'flow_consistency', 'volume_spike']
    targets = ['fwd_3d', 'fwd_5d', 'fwd_max']
    
    print("\n--- CORRELATIONS: Signal → Forward Return ---")
    for feat in features:
        corrs = {}
        for target in targets:
            corrs[target] = df[feat].corr(df[target])
        best_target = max(corrs, key=lambda k: abs(corrs[k]))
        print(f"  {feat:25s} → {best_target}: ρ={corrs[best_target]:+.3f}")
    
    # Quintile analysis for top features
    print("\n--- QUINTILE ANALYSIS ---")
    for feat in ['gap_pct', 'rvol', 'momentum_5d', 'bull_bear_ratio', 'flow_consistency']:
        try:
            df['_q'] = pd.qcut(df[feat], 5, labels=['Q1','Q2','Q3','Q4','Q5'], duplicates='drop')
            qa = df.groupby('_q').agg(
                count=('fwd_5d','count'),
                avg_5d=('fwd_5d','mean'),
                win_rate=('winner_5d','mean'),
                avg_max=('fwd_max','mean'),
            ).round(2)
            print(f"\n  {feat}:")
            for idx, row in qa.iterrows():
                bar = "█" * int(row['win_rate'] * 20)
                print(f"    {idx}: n={int(row['count']):4d} | avg_5d={row['avg_5d']:+.2f}% | WR={row['win_rate']*100:.0f}% {bar} | max={row['avg_max']:+.2f}%")
            df.drop('_q', axis=1, inplace=True)
        except Exception as e:
            print(f"  {feat}: skipped ({e})")
    
    # Tactical mover analysis
    print("\n--- TACTICAL MOVER ANALYSIS ---")
    print("  (Stocks with |gap| > 3% or RVOL > 2.0)")
    tactical = df[(df['gap_pct'].abs() > 3) | (df['rvol'] > 2.0)]
    if len(tactical) > 0:
        print(f"  Total tactical candidates: {len(tactical)}")
        print(f"  Win Rate (5d): {tactical['winner_5d'].mean()*100:.1f}%")
        print(f"  Avg fwd_5d: {tactical['fwd_5d'].mean():+.2f}%")
        print(f"  Avg fwd_max: {tactical['fwd_max'].mean():+.2f}%")
        
        # Gap direction matters
        gap_up = tactical[tactical['gap_pct'] > 3]
        gap_down = tactical[tactical['gap_pct'] < -3]
        print(f"\n  Gap UP (>3%):  n={len(gap_up):3d} | WR={gap_up['winner_5d'].mean()*100:.0f}% | avg_5d={gap_up['fwd_5d'].mean():+.2f}%")
        print(f"  Gap DOWN (<-3%): n={len(gap_down):3d} | WR={gap_down['winner_5d'].mean()*100:.0f}% | avg_5d={gap_down['fwd_5d'].mean():+.2f}%")
        
        # Flow confirmation on tactical
        bull_flow = tactical[tactical['bull_bear_ratio'] > 1.2]
        bear_flow = tactical[tactical['bull_bear_ratio'] < 0.8]
        mixed = tactical[(tactical['bull_bear_ratio'] >= 0.8) & (tactical['bull_bear_ratio'] <= 1.2)]
        print(f"\n  + Bullish flow (BB>1.2): n={len(bull_flow):3d} | WR={bull_flow['winner_5d'].mean()*100:.0f}% | avg_5d={bull_flow['fwd_5d'].mean():+.2f}%")
        print(f"  + Bearish flow (BB<0.8): n={len(bear_flow):3d} | WR={bear_flow['winner_5d'].mean()*100:.0f}% | avg_5d={bear_flow['fwd_5d'].mean():+.2f}%")
        print(f"  + Mixed flow:            n={len(mixed):3d} | WR={mixed['winner_5d'].mean()*100:.0f}% | avg_5d={mixed['fwd_5d'].mean():+.2f}%")
    
    return tactical

def build_ml_model(df):
    """Build a simple ML model for tactical signal scoring."""
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    from sklearn.metrics import classification_report
    
    print("\n" + "="*72)
    print("  MACHINE LEARNING MODEL: Tactical Signal Scoring")
    print("="*72)
    
    features = ['gap_pct', 'intraday_pct', 'rvol', 'dist_sma20_atr', 'rsi',
                'momentum_5d', 'cp_ratio', 'bull_bear_ratio', 'flow_consistency',
                'volume_spike', 'daily_range_pct', 'vcp_ratio', 'atr_pct']
    
    X = df[features].fillna(0)
    y = df['winner_5d']
    
    # Gradient Boosting for interpretability
    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
    )
    
    # Cross-validation
    cv_scores = cross_val_score(model, X, y, cv=5, scoring='accuracy')
    print(f"\n  Cross-Val Accuracy: {cv_scores.mean():.1%} ± {cv_scores.std():.1%}")
    
    # Train on full data for feature importance
    model.fit(X, y)
    
    # Feature importance
    importances = sorted(zip(features, model.feature_importances_), key=lambda x: x[1], reverse=True)
    print("\n  Feature Importance:")
    for feat, imp in importances:
        bar = "█" * int(imp * 100)
        print(f"    {feat:25s} {imp:.3f} {bar}")
    
    # Generate predictions and find optimal threshold
    probs = model.predict_proba(X)[:, 1]
    df['ml_score'] = probs
    
    print("\n  ML Score Quintile Performance:")
    df['_mq'] = pd.qcut(probs, 5, labels=['Q1','Q2','Q3','Q4','Q5'], duplicates='drop')
    for q in ['Q1','Q2','Q3','Q4','Q5']:
        subset = df[df['_mq'] == q]
        if len(subset) > 0:
            print(f"    {q}: n={len(subset):4d} | WR={subset['winner_5d'].mean()*100:.0f}% | avg_5d={subset['fwd_5d'].mean():+.2f}% | avg_max={subset['fwd_max'].mean():+.2f}%")
    
    # Extract decision rules from top splits
    print("\n  --- EXTRACTED RULES (from tree splits) ---")
    tree = model.estimators_[0, 0]
    feature_names = features
    thresholds = {}
    for i, (feat_idx, thresh) in enumerate(zip(tree.tree_.feature, tree.tree_.threshold)):
        if feat_idx >= 0 and thresh != -2.0:
            fname = feature_names[feat_idx]
            if fname not in thresholds:
                thresholds[fname] = thresh
    
    for feat, thresh in sorted(thresholds.items(), key=lambda x: importances.index((x[0], dict(importances)[x[0]])) if x[0] in dict(importances) else 99):
        above = df[df[feat] > thresh]
        below = df[df[feat] <= thresh]
        if len(above) > 10 and len(below) > 10:
            print(f"    {feat} > {thresh:.2f}: WR={above['winner_5d'].mean()*100:.0f}% (n={len(above)}) vs ≤: WR={below['winner_5d'].mean()*100:.0f}% (n={len(below)})")
    
    df.drop('_mq', axis=1, inplace=True)
    return model, importances

def main():
    print("Loading cache...")
    cache = load_cache()
    
    print("Extracting signals...")
    df = extract_signals(cache)
    
    if df.empty:
        print("No data extracted!")
        return
    
    # Save CSV
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n💾 Dataset saved: {OUTPUT_CSV} ({len(df)} rows)")
    
    # Statistical analysis
    tactical = statistical_analysis(df)
    
    # ML Model
    try:
        model, importances = build_ml_model(df)
    except ImportError:
        print("\n⚠️ scikit-learn not installed. Run: pip install scikit-learn")
    except Exception as e:
        print(f"\n⚠️ ML model failed: {e}")

if __name__ == "__main__":
    main()
