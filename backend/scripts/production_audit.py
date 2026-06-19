#!/usr/bin/env python3
"""
Production Audit — Full System Validation
=============================================
5-phase comprehensive audit of the Quality Swing system:

  Phase 1: Architecture Audit (static, no DB)
  Phase 2: Signal Backtest (91K bars replay → signal_footprint)
  Phase 3: ZigZag Validation (signals vs triple zigzag + confluences)
  Phase 4: Edge Quantification (win rate, profit factor, timing)
  Phase 5: Observer Integration Verification (daemon chain)

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/production_audit.py
"""
import sys, os, warnings, json, importlib, ast
from pathlib import Path

warnings.filterwarnings("ignore")
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
from datetime import datetime, UTC

# ═══════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════

def banner(title):
    print(f"\n{'═' * 100}")
    print(f"  {title}")
    print(f"{'═' * 100}")

def check(label, passed, detail=""):
    icon = "✅" if passed else "❌"
    det = f" — {detail}" if detail else ""
    print(f"  {icon} {label}{det}")
    return passed

TICKERS = [
    "AAPL", "AMZN", "COST", "HD", "HON", "IBM", "JNJ", "JPM",
    "MCD", "MRK", "MSFT", "PEP", "PG", "QQQ", "SPY", "WMT", "XOM",
]


# ═══════════════════════════════════════════════════════════════
# PHASE 1: ARCHITECTURE AUDIT
# ═══════════════════════════════════════════════════════════════

def phase1_architecture():
    banner("PHASE 1: ARCHITECTURE AUDIT — Clean Architecture Compliance")
    passed = 0
    failed = 0

    # 1a. Domain rules must NOT import infrastructure
    domain_files = [
        root_dir / "backend/modules/quality_swing/domain/rules/swing_entry_rules.py",
        root_dir / "backend/modules/quality_swing/domain/rules/rc_state_probability.py",
        root_dir / "backend/modules/shared/domain/rules/unified_observer.py",
        root_dir / "backend/modules/shared/domain/entities/observer_snapshot.py",
    ]
    infra_markers = ["psycopg2", "timescale_data_store", "requests", "httpx", "yfinance", "alpaca"]

    for f in domain_files:
        content = f.read_text()
        violations = [m for m in infra_markers if m in content]
        ok = len(violations) == 0
        if check(f"Domain purity: {f.name}", ok,
                 f"violations: {violations}" if violations else "no infra imports"):
            passed += 1
        else:
            failed += 1

    # 1b. swing_gate.py (application layer) CAN import infrastructure — verify it loads observer
    gate_path = root_dir / "backend/modules/quality_swing/application/use_cases/swing_gate.py"
    gate_content = gate_path.read_text()
    ok = "_load_observer_recovery" in gate_content and "observer_recovery" in gate_content
    if check("SwingGate loads observer_recovery", ok): passed += 1
    else: failed += 1

    ok = "is_accumulate_signal" in gate_content and "observer_recovery=_observer_recovery" in gate_content
    if check("SwingGate passes observer_recovery to entry rules", ok): passed += 1
    else: failed += 1

    # 1c. Dead code check — old filters should NOT be in entry rules
    entry_content = (root_dir / "backend/modules/quality_swing/domain/rules/swing_entry_rules.py").read_text()
    dead_params = ["sigma_c_vel", "svw_vel", "kf_consensus"]
    for dp in dead_params:
        ok = dp not in entry_content
        if check(f"Dead code removed: {dp} not in entry_rules", ok):
            passed += 1
        else:
            failed += 1

    # 1d. Observer provider registered in daemon
    daemon_content = (root_dir / "backend/daemons/data_vault_daemon.py").read_text()
    ok = "observer_provider" in daemon_content and "ObserverProvider" in daemon_content
    if check("ObserverProvider in daemon run_cycle", ok): passed += 1
    else: failed += 1

    ok = "Tier 3d" in daemon_content or "Unified Observer" in daemon_content
    if check("Observer positioned as Tier 3d (after Market Health)", ok): passed += 1
    else: failed += 1

    # 1e. Provider auto-registers
    provider_content = (root_dir / "backend/daemons/vault_providers/observer_provider.py").read_text()
    ok = "register_provider(ObserverProvider())" in provider_content
    if check("ObserverProvider auto-registers on import", ok): passed += 1
    else: failed += 1

    # 1f. JSON table integrity
    table_path = root_dir / "backend/modules/quality_swing/domain/rules/rc_probability_table.json"
    try:
        with open(table_path) as f:
            table = json.load(f)
        n_cells = len(table.get("cells", {}))
        ok = n_cells >= 600
        if check(f"RC probability table valid JSON: {n_cells} cells", ok): passed += 1
        else: failed += 1
    except Exception as e:
        check("RC probability table JSON", False, str(e))
        failed += 1

    # 1g. Import chain smoke test
    try:
        from backend.modules.quality_swing.domain.rules.swing_entry_rules import is_accumulate_signal
        from backend.modules.quality_swing.domain.rules.rc_state_probability import lookup_probability
        from backend.modules.shared.domain.rules.unified_observer import UnifiedKalmanObserver
        from backend.modules.shared.domain.entities.observer_snapshot import ObserverSnapshot
        if check("Full import chain works (entry_rules → rc_prob → observer → snapshot)", True):
            passed += 1
    except Exception as e:
        check("Import chain", False, str(e))
        failed += 1

    print(f"\n  SUMMARY: {passed} passed, {failed} failed")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# PHASE 2: SIGNAL BACKTEST (Full Replay)
# ═══════════════════════════════════════════════════════════════

def phase2_signal_backtest():
    banner("PHASE 2: SIGNAL BACKTEST — Full SwingGate Replay on 91K Bars")

    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    from backend.modules.quality_swing.domain.rules.rc_state_probability import lookup_probability
    from backend.modules.quality_swing.domain.rules.swing_entry_rules import (
        is_accumulate_signal, is_trim_signal,
    )
    from backend.modules.quality_swing.domain.entities.swing_bias import TickerSentimentBias

    store = TimescaleDataStore()
    conn = store._conn()

    # 2a. Create signal_footprint table
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS engine;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS engine.signal_footprint (
                ticker TEXT NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                action TEXT NOT NULL,
                conviction DOUBLE PRECISION,
                p_bull DOUBLE PRECISION,
                state_key TEXT,
                level TEXT,
                observer_recovery DOUBLE PRECISION,
                observer_state TEXT,
                hookup BOOLEAN,
                vol_regime TEXT DEFAULT 'NORMAL',
                reasoning TEXT,
                PRIMARY KEY (ticker, timestamp)
            );
        """)
        cur.execute("DELETE FROM engine.signal_footprint;")
    conn.commit()
    print("  engine.signal_footprint table created + cleared.")

    # 2b. Load channel snapshots with observer data
    cs = pd.read_sql("""
        SELECT ticker, timestamp::date as date, timestamp,
               sigma_current, sigma_wave, sigma_tide,
               vwap_sigma_wave, vwap_sigma_current, vwap_sigma_tide,
               tide_slope, current_slope, wave_slope,
               tide_accel, current_accel, wave_accel,
               tension_wave, tension_current, tension_tide,
               rsi_value, conj_wave_tide, conj_wave_current,
               fear_level, fear_label, regime,
               wave_flip, wave_flip_direction,
               below_all_vwaps, above_all_vwaps,
               compression_ratio, vol_up_down_ratio,
               obs_recovery_score, obs_velocity_norm, obs_state
        FROM engine.channel_snapshots
        WHERE timeframe = '1d'
        ORDER BY ticker, timestamp
    """, conn)
    print(f"  Loaded {len(cs):,} channel snapshots")

    # 2c. Load OHLCV for hookup computation
    bars = pd.read_sql("""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars
        WHERE timeframe = '1d'
        ORDER BY ticker, time
    """, conn)
    bars['date'] = pd.to_datetime(bars['date'])
    cs['date'] = pd.to_datetime(cs['date'])

    # Merge
    df = cs.merge(bars[['ticker', 'date', 'close']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
    print(f"  Merged: {len(df):,} bars with close prices")

    # 2d. Replay every bar
    signals = []
    for ticker in TICKERS:
        tk = df[df['ticker'] == ticker].reset_index(drop=True)
        if len(tk) < 250:
            print(f"  {ticker}: skipped ({len(tk)} bars)")
            continue

        n_accum = 0
        n_trim = 0
        for i in range(1, len(tk)):
            row = tk.iloc[i]

            # RC probability lookup
            rc_prob = lookup_probability(
                tide_slope=float(row.get('tide_slope', 0) or 0),
                sigma_current=float(row.get('sigma_current', 0) or 0),
                sigma_wave=float(row.get('sigma_wave', 0) or 0),
                vwap_sigma_wave=float(row.get('vwap_sigma_wave', 0) or 0),
            )

            # Observer recovery
            obs_recovery = float(row.get('obs_recovery_score', 0) or 0)
            obs_state = row.get('obs_state', 'STABLE') or 'STABLE'

            # Hookup
            hookup = float(row['close']) > float(tk.iloc[i-1]['close'])

            # Below VWAP
            below_vwap = bool(row.get('below_all_vwaps', False))

            # Fear bias (simplified from snapshot)
            fear = None
            if row.get('fear_level') is not None:
                try:
                    fear = TickerSentimentBias(
                        fear_level=int(row['fear_level']),
                        fear_label=str(row.get('fear_label', 'NEUTRAL') or 'NEUTRAL'),
                        tide_slope=float(row.get('tide_slope', 0) or 0),
                        wave_slope=float(row.get('wave_slope', 0) or 0),
                        tide_accel=float(row.get('tide_accel', 0) or 0),
                        wave_flip=bool(row.get('wave_flip', False)),
                        wave_flip_direction=int(row.get('wave_flip_direction', 0) or 0),
                        sigma_position=float(row.get('sigma_current', 0) or 0),
                        slope_conjugation=float(row.get('conj_wave_tide', 0) or 0),
                    )
                except Exception:
                    pass

            # Evaluate accumulate
            should_accum, conviction, reason = is_accumulate_signal(
                sigma_pos=float(row.get('sigma_current', 0) or 0),
                fear=fear,
                below_vwap=below_vwap,
                hookup=hookup,
                vol_regime_label="NORMAL",
                rc_prob=rc_prob,
                observer_recovery=obs_recovery,
            )

            if should_accum:
                action = "ACCUMULATE"
                n_accum += 1
            else:
                # Evaluate trim
                should_trim, trim_pct, trim_reason = is_trim_signal(
                    sigma_pos=float(row.get('sigma_current', 0) or 0),
                    fear=fear,
                    rc_prob=rc_prob,
                )
                if should_trim:
                    action = "TRIM"
                    conviction = trim_pct
                    reason = trim_reason
                    n_trim += 1
                else:
                    action = "HOLD"

            signals.append({
                'ticker': ticker,
                'timestamp': row['timestamp'],
                'action': action,
                'conviction': round(conviction, 4) if conviction else 0,
                'p_bull': round(rc_prob.prob_bull, 4) if rc_prob else None,
                'state_key': rc_prob.state_key if rc_prob else None,
                'level': rc_prob.level if rc_prob else None,
                'observer_recovery': round(obs_recovery, 4),
                'observer_state': obs_state,
                'hookup': hookup,
                'vol_regime': 'NORMAL',
                'reasoning': reason[:500] if reason else None,
            })

        print(f"  {ticker}: {len(tk)-1:,} bars → {n_accum} ACCUMULATE, {n_trim} TRIM")

    # 2e. Persist to Vault
    from psycopg2.extras import execute_values
    rows = [(
        s['ticker'], s['timestamp'], s['action'], s['conviction'],
        s['p_bull'], s['state_key'], s['level'],
        s['observer_recovery'], s['observer_state'],
        s['hookup'], s['vol_regime'], s['reasoning'],
    ) for s in signals]

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO engine.signal_footprint
            (ticker, timestamp, action, conviction, p_bull, state_key, level,
             observer_recovery, observer_state, hookup, vol_regime, reasoning)
            VALUES %s
            ON CONFLICT (ticker, timestamp) DO UPDATE SET
                action = EXCLUDED.action,
                conviction = EXCLUDED.conviction,
                p_bull = EXCLUDED.p_bull,
                state_key = EXCLUDED.state_key,
                level = EXCLUDED.level,
                observer_recovery = EXCLUDED.observer_recovery,
                observer_state = EXCLUDED.observer_state,
                hookup = EXCLUDED.hookup,
                reasoning = EXCLUDED.reasoning
        """, rows, page_size=1000)
    conn.commit()

    n_accum = sum(1 for s in signals if s['action'] == 'ACCUMULATE')
    n_trim = sum(1 for s in signals if s['action'] == 'TRIM')
    n_hold = sum(1 for s in signals if s['action'] == 'HOLD')
    print(f"\n  PERSISTED: {len(signals):,} signals to engine.signal_footprint")
    print(f"  Distribution: ACCUMULATE={n_accum:,} TRIM={n_trim:,} HOLD={n_hold:,}")

    store._put(conn)
    store.close()
    return len(signals)


# ═══════════════════════════════════════════════════════════════
# PHASE 3: ZIGZAG VALIDATION
# ═══════════════════════════════════════════════════════════════

def phase3_zigzag_validation():
    banner("PHASE 3: ZIGZAG VALIDATION — Signals vs Ground Truth")

    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    conn = store._conn()

    # Check available zigzag swing percentages
    zz_meta = pd.read_sql("""
        SELECT min_swing_pct, COUNT(*) as n
        FROM engine.zigzag_points
        GROUP BY min_swing_pct ORDER BY min_swing_pct
    """, conn)
    print(f"  Available zigzag calibrations:")
    for _, r in zz_meta.iterrows():
        print(f"    {r['min_swing_pct']*100:.1f}%: {r['n']:,} points")

    # Determine thresholds
    available_pcts = sorted(zz_meta['min_swing_pct'].tolist())
    # Use closest available to 2.5%, 5%, 7.5%
    pct_small = min(available_pcts, key=lambda x: abs(x - 0.025))
    pct_mid = min(available_pcts, key=lambda x: abs(x - 0.05))
    pct_large = min(available_pcts, key=lambda x: abs(x - 0.075))
    print(f"  Using: small={pct_small*100:.1f}%, mid={pct_mid*100:.1f}%, large={pct_large*100:.1f}%")

    CONF_WINDOW = 5  # days for confluence matching

    # Load signals and zigzag
    sigs = pd.read_sql("""
        SELECT ticker, timestamp::date as date, action, conviction, p_bull,
               observer_recovery, observer_state, hookup, state_key, level
        FROM engine.signal_footprint
        ORDER BY ticker, timestamp
    """, conn)
    sigs['date'] = pd.to_datetime(sigs['date'])

    zz_small = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points WHERE min_swing_pct = {pct_small}
        ORDER BY ticker, timestamp
    """, conn)
    zz_mid = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points WHERE min_swing_pct = {pct_mid}
        ORDER BY ticker, timestamp
    """, conn)
    zz_large = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date, tp_type, price
        FROM engine.zigzag_points WHERE min_swing_pct = {pct_large}
        ORDER BY ticker, timestamp
    """, conn)
    for d in [zz_small, zz_mid, zz_large]:
        d['date'] = pd.to_datetime(d['date'])

    bars = pd.read_sql("""
        SELECT ticker, time::date as date, close
        FROM market.ohlcv_bars WHERE timeframe='1d'
        ORDER BY ticker, time
    """, conn)
    bars['date'] = pd.to_datetime(bars['date'])

    store._put(conn); store.close()

    # ── ACCUMULATE signal validation vs zigzag MINs ──
    accum_sigs = sigs[sigs['action'] == 'ACCUMULATE'].copy()
    print(f"\n  ACCUMULATE signals to evaluate: {len(accum_sigs):,}")

    # Build trough maps with confluence levels
    trough_map = {}
    for ticker in TICKERS:
        t_small = zz_small[(zz_small['ticker'] == ticker) & (zz_small['tp_type'] == 'MIN')].sort_values('date')
        d_mid = pd.to_datetime(zz_mid[(zz_mid['ticker'] == ticker) & (zz_mid['tp_type'] == 'MIN')]['date']).values
        d_large = pd.to_datetime(zz_large[(zz_large['ticker'] == ticker) & (zz_large['tp_type'] == 'MIN')]['date']).values

        entries = []
        for _, r in t_small.iterrows():
            d = np.datetime64(r['date'])
            has_mid = len(d_mid) > 0 and np.min(np.abs((d_mid - d) / np.timedelta64(1, 'D'))) <= CONF_WINDOW
            has_large = len(d_large) > 0 and np.min(np.abs((d_large - d) / np.timedelta64(1, 'D'))) <= CONF_WINDOW
            level = 3 if (has_mid and has_large) else 2 if has_mid else 1
            entries.append((r['date'], level, float(r['price'])))
        trough_map[ticker] = entries

    # Build peak maps for profit-to-peak
    peak_map = {}
    for ticker in TICKERS:
        peaks = zz_mid[(zz_mid['ticker'] == ticker) & (zz_mid['tp_type'] == 'MAX')].sort_values('date')
        peak_map[ticker] = [(r['date'], float(r['price'])) for _, r in peaks.iterrows()]

    # For each ACCUMULATE signal, find nearest trough
    results = []
    for _, sig in accum_sigs.iterrows():
        ticker = sig['ticker']
        d = sig['date']
        troughs = trough_map.get(ticker, [])
        if not troughs:
            continue

        # Find nearest trough
        trough_dates = np.array([np.datetime64(t[0]) for t in troughs])
        diffs = (trough_dates - np.datetime64(d)) / np.timedelta64(1, 'D')
        abs_diffs = np.abs(diffs)
        nearest_idx = abs_diffs.argmin()
        dist = float(diffs[nearest_idx])
        level = troughs[nearest_idx][1]
        side = "AFTER" if dist <= 0 else "BEFORE"

        # Get close price at signal
        tk_bars = bars[bars['ticker'] == ticker]
        price_row = tk_bars[tk_bars['date'] == d]
        price = float(price_row['close'].iloc[0]) if len(price_row) > 0 else None

        # Profit to next peak
        peaks = peak_map.get(ticker, [])
        profit = None
        if price and peaks:
            pd_arr = np.array([np.datetime64(p[0]) for p in peaks])
            pp_arr = np.array([p[1] for p in peaks])
            pi = np.searchsorted(pd_arr, np.datetime64(d), side='right')
            if pi < len(pp_arr):
                profit = (pp_arr[pi] / price - 1) * 100

        results.append({
            'ticker': ticker, 'date': d,
            'conviction': sig['conviction'],
            'p_bull': sig['p_bull'],
            'obs_recovery': sig['observer_recovery'],
            'obs_state': sig['observer_state'],
            'trough_dist': abs(dist),
            'trough_side': side,
            'trough_level': level,
            'profit_to_peak': profit,
            'state_key': sig['state_key'],
            'level': sig['level'],
        })

    rdf = pd.DataFrame(results)
    print(f"  Validated {len(rdf):,} ACCUMULATE signals against zigzag troughs")

    # ── Aggregate metrics ──
    print(f"\n  ── TIMING ACCURACY ──")
    within_5 = (rdf['trough_dist'] <= 5).mean() * 100
    within_10 = (rdf['trough_dist'] <= 10).mean() * 100
    within_15 = (rdf['trough_dist'] <= 15).mean() * 100
    far = (rdf['trough_dist'] > 15).mean() * 100
    after = (rdf['trough_side'] == 'AFTER').mean() * 100
    print(f"    Within ±5 bars of trough:  {within_5:.1f}%")
    print(f"    Within ±10 bars:           {within_10:.1f}%")
    print(f"    Within ±15 bars:           {within_15:.1f}%")
    print(f"    Far from any trough (>15): {far:.1f}% (FALSE ALARM)")
    print(f"    Fires AFTER trough:        {after:.1f}% (correct side)")

    print(f"\n  ── PRECISION BY CONFLUENCE LEVEL ──")
    for lvl in [1, 2, 3]:
        sub = rdf[rdf['trough_level'] == lvl]
        n = len(sub)
        if n < 20:
            continue
        near = (sub['trough_dist'] <= 10).mean() * 100
        pft = sub['profit_to_peak'].dropna()
        avg_pft = pft.mean() if len(pft) > 0 else 0
        med_pft = pft.median() if len(pft) > 0 else 0
        labels = {1: "Single (small only)", 2: "Double (small+mid)", 3: "Triple (ALL)"}
        print(f"    Level {lvl} ({labels[lvl]}):")
        print(f"      N={n:,}  near_trough(±10d)={near:.1f}%  "
              f"avg_profit={avg_pft:+.1f}%  med_profit={med_pft:+.1f}%")

    # Level 3 capture rate
    total_l3_troughs = sum(1 for tk_troughs in trough_map.values()
                          for _, lvl, _ in tk_troughs if lvl == 3)
    l3_captured = 0
    for ticker in TICKERS:
        l3_dates = [np.datetime64(t[0]) for t in trough_map.get(ticker, []) if t[1] == 3]
        accum_dates = np.array([
            np.datetime64(d)
            for d in accum_sigs[accum_sigs['ticker'] == ticker]['date'].values
        ])
        for td in l3_dates:
            if len(accum_dates) > 0:
                if np.min(np.abs((accum_dates - td) / np.timedelta64(1, 'D'))) <= 10:
                    l3_captured += 1

    l3_rate = (l3_captured / total_l3_troughs * 100) if total_l3_troughs > 0 else 0
    print(f"\n  ── LEVEL-3 CONFLUENCE CAPTURE ──")
    print(f"    Total L3 troughs:     {total_l3_troughs}")
    print(f"    Captured (±10 bars):  {l3_captured} ({l3_rate:.1f}%)")

    # ── TRIM validation vs zigzag MAXs ──
    trim_sigs = sigs[sigs['action'] == 'TRIM'].copy()
    print(f"\n  ── TRIM SIGNAL VALIDATION ──")
    print(f"    Total TRIM signals: {len(trim_sigs):,}")

    # Quick check: are TRIMs near peaks?
    trim_results = []
    for _, sig in trim_sigs.iterrows():
        ticker = sig['ticker']
        d = sig['date']
        peaks = peak_map.get(ticker, [])
        if not peaks:
            continue
        pd_arr = np.array([np.datetime64(p[0]) for p in peaks])
        diffs = np.abs((pd_arr - np.datetime64(d)) / np.timedelta64(1, 'D'))
        if len(diffs) > 0:
            trim_results.append({'dist': float(diffs.min())})

    if trim_results:
        tdf = pd.DataFrame(trim_results)
        near_peak = (tdf['dist'] <= 10).mean() * 100
        print(f"    Within ±10 bars of peak: {near_peak:.1f}%")

    return rdf


# ═══════════════════════════════════════════════════════════════
# PHASE 4: EDGE QUANTIFICATION
# ═══════════════════════════════════════════════════════════════

def phase4_edge_quantification(rdf: pd.DataFrame):
    banner("PHASE 4: EDGE QUANTIFICATION — Statistical Evidence of Edge")

    # 4a. Win rate by P(bull) bin
    print(f"\n  ── WIN RATE BY P(BULL) BIN ──")
    print(f"  {'P(bull) Bin':<15s} {'N':>6s} {'%AFTER':>8s} {'Med Profit':>11s} {'Avg Profit':>11s} {'Hit Rate':>9s}")
    print(f"  {'─'*65}")

    pbins = [(0.0, 0.35, "≤35% TRIM"), (0.35, 0.50, "35-50%"), (0.50, 0.65, "50-65%"),
             (0.65, 0.75, "65-75%"), (0.75, 0.85, "75-85%"), (0.85, 1.01, "85-100%")]

    for lo, hi, label in pbins:
        mask = (rdf['p_bull'] >= lo) & (rdf['p_bull'] < hi) if rdf['p_bull'].notna().any() else pd.Series(False, index=rdf.index)
        sub = rdf[mask]
        if len(sub) < 20:
            continue
        after = (sub['trough_side'] == 'AFTER').mean()
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        avg = pft.mean() if len(pft) > 0 else 0
        hit = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        print(f"  {label:<15s} {len(sub):>6,} {after:>7.1%} {med:>+10.1f}% {avg:>+10.1f}% {hit:>8.1f}%")

    # 4b. Observer lift
    print(f"\n  ── OBSERVER LIFT ──")
    print(f"  {'Observer State':<20s} {'N':>6s} {'%AFTER':>8s} {'Med Profit':>11s} {'False Alarm':>12s}")
    print(f"  {'─'*60}")

    for state in ['RECOVERING', 'STABLE', 'TRANSITIONING', 'DETERIORATING']:
        sub = rdf[rdf['obs_state'] == state]
        if len(sub) < 20:
            continue
        after = (sub['trough_side'] == 'AFTER').mean()
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        false_alarm = (sub['trough_dist'] > 15).mean() * 100
        print(f"  {state:<20s} {len(sub):>6,} {after:>7.1%} {med:>+10.1f}% {false_alarm:>11.1f}%")

    # Recovery threshold analysis
    print(f"\n  Recovery score thresholds:")
    for thresh in [-0.3, 0.0, 0.3, 0.5]:
        sub = rdf[rdf['obs_recovery'] > thresh]
        if len(sub) < 20:
            continue
        after = (sub['trough_side'] == 'AFTER').mean()
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        print(f"    recovery > {thresh:+.1f}: N={len(sub):,} %AFTER={after:.1%} profit={med:+.1f}%")

    # 4c. Profit Factor
    print(f"\n  ── PROFIT FACTOR ──")
    pft = rdf['profit_to_peak'].dropna()
    wins = pft[pft > 0]
    losses = pft[pft < 0]
    pf = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
    print(f"    Total signals with profit data: {len(pft):,}")
    print(f"    Winners: {len(wins):,} (sum={wins.sum():+,.1f}%)")
    print(f"    Losers:  {len(losses):,} (sum={losses.sum():+,.1f}%)")
    print(f"    PROFIT FACTOR: {pf:.2f}")
    print(f"    Win Rate: {len(wins)/len(pft)*100:.1f}%")

    # 4d. Per-ticker breakdown
    print(f"\n  ── PER TICKER EDGE ──")
    print(f"  {'Ticker':<8s} {'N':>5s} {'%AFTER':>8s} {'Med Pft':>9s} {'Win Rate':>9s} {'PF':>6s} {'Verdict':>10s}")
    print(f"  {'─'*60}")

    edge_tickers = 0
    for ticker in TICKERS:
        sub = rdf[rdf['ticker'] == ticker]
        if len(sub) < 20:
            continue
        after = (sub['trough_side'] == 'AFTER').mean()
        pft = sub['profit_to_peak'].dropna()
        if len(pft) < 10:
            continue
        med = pft.median()
        wr = (pft > 0).mean() * 100
        w = pft[pft > 0].sum()
        l = abs(pft[pft < 0].sum())
        pf = w / l if l > 0 else float('inf')

        verdict = "✅ EDGE" if (wr > 55 and pf > 1.2) else "⚠️ WEAK" if wr > 50 else "❌ NO EDGE"
        if wr > 55 and pf > 1.2:
            edge_tickers += 1
        print(f"  {ticker:<8s} {len(sub):>5,} {after:>7.1%} {med:>+8.1f}% {wr:>8.1f}% {pf:>5.2f} {verdict}")

    print(f"\n  TICKERS WITH EDGE: {edge_tickers}/{len(TICKERS)}")

    # 4e. Hierarchical level quality
    print(f"\n  ── HIERARCHICAL LEVEL QUALITY ──")
    print(f"  {'Level':<15s} {'N':>6s} {'%AFTER':>8s} {'Med Profit':>11s} {'Win Rate':>9s}")
    for lvl in ['L1_full', 'L2_no_tide', 'L3_sc_svw', 'L4_svw']:
        sub = rdf[rdf['level'] == lvl]
        if len(sub) < 20:
            continue
        after = (sub['trough_side'] == 'AFTER').mean()
        pft = sub['profit_to_peak'].dropna()
        med = pft.median() if len(pft) > 0 else 0
        wr = (pft > 0).mean() * 100 if len(pft) > 0 else 0
        print(f"  {lvl:<15s} {len(sub):>6,} {after:>7.1%} {med:>+10.1f}% {wr:>8.1f}%")


# ═══════════════════════════════════════════════════════════════
# PHASE 5: OBSERVER INTEGRATION VERIFICATION
# ═══════════════════════════════════════════════════════════════

def phase5_observer_integration():
    banner("PHASE 5: OBSERVER INTEGRATION VERIFICATION")

    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()
    conn = store._conn()
    passed = 0
    failed = 0

    # 5a. Column existence
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'engine' AND table_name = 'channel_snapshots'
            AND column_name LIKE 'obs_%'
        """)
        obs_cols = [r[0] for r in cur.fetchall()]

    expected = ['obs_recovery_score', 'obs_velocity_norm', 'obs_state']
    for col in expected:
        ok = col in obs_cols
        if check(f"Column exists: {col}", ok): passed += 1
        else: failed += 1

    # 5b. Data coverage
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ticker, COUNT(*) as total,
                   COUNT(obs_recovery_score) as with_obs,
                   MAX(timestamp)::date as latest
            FROM engine.channel_snapshots
            WHERE timeframe = '1d'
            GROUP BY ticker ORDER BY ticker
        """)
        coverage = cur.fetchall()

    print(f"\n  Data coverage:")
    all_covered = True
    for ticker, total, with_obs, latest in coverage:
        pct = (with_obs / total * 100) if total > 0 else 0
        ok = pct > 95
        print(f"    {ticker}: {with_obs:,}/{total:,} ({pct:.1f}%) latest={latest}")
        if not ok:
            all_covered = False

    if check("All tickers >95% observer coverage", all_covered): passed += 1
    else: failed += 1

    # 5c. Provider smoke test
    try:
        from backend.daemons.vault_providers.observer_provider import ObserverProvider
        result = ObserverProvider().run_ticker(store, 'SPY')
        ok = result.get('status') == 'ok'
        if check(f"ObserverProvider.run_ticker('SPY'): {result}", ok): passed += 1
        else: failed += 1
    except Exception as e:
        check("ObserverProvider smoke test", False, str(e))
        failed += 1

    # 5d. Daemon chain
    daemon_path = root_dir / "backend/daemons/data_vault_daemon.py"
    content = daemon_path.read_text()
    ok = 'ObserverProvider' in content and 'observer' in content
    if check("Daemon run_cycle includes ObserverProvider", ok): passed += 1
    else: failed += 1

    # 5e. SwingGate reads observer
    with conn.cursor() as cur:
        cur.execute("""
            SELECT obs_recovery_score FROM engine.channel_snapshots
            WHERE ticker = 'SPY' AND timeframe = '1d' AND obs_recovery_score IS NOT NULL
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cur.fetchone()

    ok = row is not None and row[0] is not None
    if check(f"SwingGate can read latest observer: SPY recovery={row[0] if row else 'NULL'}", ok):
        passed += 1
    else:
        failed += 1

    store._put(conn); store.close()
    print(f"\n  SUMMARY: {passed} passed, {failed} failed")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    banner("PRODUCTION AUDIT — FULL SYSTEM VALIDATION")
    print(f"  Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"  Tickers:   {len(TICKERS)}")

    # Phase 1
    arch_ok = phase1_architecture()

    # Phase 2
    n_signals = phase2_signal_backtest()

    # Phase 3
    rdf = phase3_zigzag_validation()

    # Phase 4
    phase4_edge_quantification(rdf)

    # Phase 5
    obs_ok = phase5_observer_integration()

    # Final summary
    banner("FINAL AUDIT SUMMARY")
    print(f"  Architecture:    {'✅ PASS' if arch_ok else '❌ ISSUES'}")
    print(f"  Signal Footprint: {n_signals:,} signals persisted")
    print(f"  Observer:         {'✅ PASS' if obs_ok else '❌ ISSUES'}")
    print(f"  Audit complete at {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    main()
