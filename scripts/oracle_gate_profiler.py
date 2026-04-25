"""
ORACLE GATE PROFILER — Perfect Foresight Attribution
=====================================================
Evaluates EACH gate/filter independently against the KNOWN future outcome.

For every ticker/day, this script:
  1. Runs the full Hub pipeline capturing ALL gate decisions
  2. "Cheats" by looking at the actual future price (1d, 3d, 5d)
  3. Computes a Confusion Matrix per gate (TP, FP, TN, FN)
  4. Calculates a Credibility Index per gate
  5. Trains mini-ML models to learn WHEN each gate fails
  6. Exports a comprehensive gate performance report

Usage:
  python scripts/oracle_gate_profiler.py
"""
import sys, os, json, logging
import numpy as np
import pandas as pd
from datetime import date
from collections import defaultdict
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from modules.entry_decision.hub import EntryIntelligenceHub

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════

@dataclass
class GateDecision:
    """A single gate's decision for one ticker/day."""
    gate_name: str
    decision: str          # "PASS" or "BLOCK"
    reason: str = ""
    # Context at decision time
    conditions: dict = field(default_factory=dict)


@dataclass
class OracleRow:
    """One ticker/day with all gate decisions + oracle outcome."""
    ticker: str
    date: str
    entry_price: float
    strategy: str
    # Oracle: future prices (the "cheat")
    future_1d_pnl: float = 0.0
    future_3d_pnl: float = 0.0
    future_5d_pnl: float = 0.0
    future_mfe: float = 0.0
    oracle_winner: bool = False  # Would MFE > 1% in 5 days?
    # All gate decisions
    gate_decisions: list = field(default_factory=list)
    # Full Hub report snapshot
    hub_snapshot: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
# GATE DEFINITIONS — Every decision point in the pipeline
# ═══════════════════════════════════════════════════════════

GATE_REGISTRY = [
    # Step 5.6: VP Distribution Gate
    {
        "name": "VP_DISTRIBUTION",
        "description": "Blocks CORE trades when VP shows institutional distribution",
        "evaluate": lambda r: (
            "BLOCK" if (r.vp_institutional_bias == "DISTRIBUTION" and r.vp_bias_confidence >= 75)
            else "PASS"
        ),
        "conditions": lambda r: {
            "vp_bias": r.vp_institutional_bias,
            "vp_confidence": r.vp_bias_confidence,
            "vp_shape_short": r.vp_shape_short,
            "vp_poc_migration": r.vp_poc_migration,
        }
    },
    # Step 6: Phase Verdict
    {
        "name": "PHASE_VERDICT",
        "description": "PricePhaseIntelligence determines if timing is right",
        "evaluate": lambda r: (
            "PASS" if r.phase_verdict == "FIRE"
            else "BLOCK"
        ),
        "conditions": lambda r: {
            "phase": r.phase,
            "phase_verdict": r.phase_verdict,
            "dimensions": r.dimensions_confirming,
            "risk_reward": r.risk_reward,
            "rsi": r.rsi,
        }
    },
    # Step 6 sub: RSI Zone (regime-aware)
    {
        "name": "RSI_ZONE",
        "description": "Cardwell/Brown regime-aware RSI zone filter",
        "evaluate": lambda r: (
            "BLOCK" if r.rsi_zone in ("BOUNCE_SELL", "EXTREME_BULL", "EXTREME_BEAR", "OVERBOUGHT")
            else "PASS"
        ),
        "conditions": lambda r: {
            "rsi": r.rsi,
            "rsi_regime": r.rsi_regime,
            "rsi_zone": r.rsi_zone,
            "rsi_conviction": r.rsi_conviction,
            "rsi_divergence": r.rsi_divergence,
        }
    },
    # Step 6 sub: RSI Divergence Signal
    {
        "name": "RSI_DIVERGENCE",
        "description": "Cardwell positive/negative reversal detection",
        "evaluate": lambda r: (
            "BOOST" if r.rsi_divergence in ("POSITIVE_REVERSAL", "CLASSIC_BULLISH_DIV")
            else "CAUTION" if r.rsi_divergence in ("NEGATIVE_REVERSAL", "CLASSIC_BEARISH_DIV")
            else "PASS"
        ),
        "conditions": lambda r: {
            "divergence": r.rsi_divergence,
            "strength": r.rsi_divergence_strength,
            "slope_alignment": r.rsi_slope_alignment,
            "price_slope": r.rsi_price_slope,
            "rsi_slope": r.rsi_indicator_slope,
        }
    },
    # Step 6b: Pattern Intelligence
    {
        "name": "PATTERN_INTEL",
        "description": "Candlestick pattern confirmation/veto",
        "evaluate": lambda r: (
            "BLOCK" if (r.pattern_sentiment == "BEARISH" and r.pattern_score <= -0.5)
            else "BOOST" if (r.pattern_sentiment == "BULLISH" and r.pattern_score >= 0.5)
            else "PASS"
        ),
        "conditions": lambda r: {
            "pattern": r.candlestick_pattern,
            "sentiment": r.pattern_sentiment,
            "score": r.pattern_score,
            "on_support": r.pattern_on_support,
            "confirms": r.pattern_confirms,
        }
    },
    # Step 5: Whale/Flow
    {
        "name": "WHALE_FLOW",
        "description": "Institutional flow conviction",
        "evaluate": lambda r: (
            "BOOST" if r.whale_verdict in ("RIDE_THE_WHALES",)
            else "CAUTION" if r.whale_verdict in ("CONTRA_FLOW",)
            else "PASS"
        ),
        "conditions": lambda r: {
            "whale_verdict": r.whale_verdict,
            "whale_confidence": r.whale_confidence,
            "flow_grade": r.flow_persistence_grade,
            "flow_consecutive": r.flow_consecutive_days,
            "tide_direction": r.tide_direction,
        }
    },
    # Step 4b: Flow Persistence Grade
    {
        "name": "FLOW_GRADE",
        "description": "Flow persistence quality filter",
        "evaluate": lambda r: (
            "BOOST" if r.flow_persistence_grade in ("CONFIRMED_STREAK",)
            else "CAUTION" if r.flow_persistence_grade in ("STALE", "UNKNOWN")
            else "PASS"
        ),
        "conditions": lambda r: {
            "flow_grade": r.flow_persistence_grade,
            "flow_freshness": r.flow_freshness_weight,
            "flow_darkpool": r.flow_darkpool_confirmed,
        }
    },
    # Step 6 sub: Volume Confirmation
    {
        "name": "VOLUME_CONFIRM",
        "description": "RVOL and Wyckoff state confirmation",
        "evaluate": lambda r: (
            "BOOST" if (r.rvol >= 1.5 and r.wyckoff_state in ("ACCUMULATION", "MARKUP"))
            else "CAUTION" if (r.rvol < 0.7)
            else "PASS"
        ),
        "conditions": lambda r: {
            "rvol": r.rvol,
            "wyckoff_state": r.wyckoff_state,
        }
    },
    # Composite: GAP direction
    {
        "name": "GAP_FILTER",
        "description": "Gap chase prevention",
        "evaluate": lambda r: (
            "BLOCK" if (hasattr(r, '_gap_pct') and r._gap_pct > 3.0)
            else "PASS"
        ),
        "conditions": lambda r: {
            "phase": r.phase,
        }
    },
    # Step 6 sub: VP Price vs Value Area
    {
        "name": "VP_LOCATION",
        "description": "Price position relative to VP Value Area",
        "evaluate": lambda r: (
            "BOOST" if r.vp_price_vs_va == "BELOW_VA"  # Below VA = potential value buy
            else "CAUTION" if r.vp_price_vs_va == "ABOVE_VA"
            else "PASS"
        ),
        "conditions": lambda r: {
            "price_vs_va": r.vp_price_vs_va,
            "vp_poc_short": r.vp_poc_short,
            "vp_shape_short": r.vp_shape_short,
            "vp_institutional_bias": r.vp_institutional_bias,
        }
    },
]


# ═══════════════════════════════════════════════════════════
# ORACLE COMPUTATION
# ═══════════════════════════════════════════════════════════

def compute_oracle(ticker_prices, current_date, entry_price, all_dates):
    """Look at actual future prices to determine if trade would win."""
    date_idx = all_dates.index(current_date) if current_date in all_dates else -1
    if date_idx < 0:
        return 0, 0, 0, 0, False

    future_pnls = []
    mfe = 0.0
    for offset in range(1, 6):
        future_date = all_dates[date_idx + offset] if date_idx + offset < len(all_dates) else None
        if future_date and future_date in ticker_prices:
            high = ticker_prices[future_date].get('High', entry_price)
            low = ticker_prices[future_date].get('Low', entry_price)
            close = ticker_prices[future_date].get('Close', entry_price)
            pnl = (close / entry_price - 1) * 100
            day_mfe = (high / entry_price - 1) * 100
            mfe = max(mfe, day_mfe)
            future_pnls.append(pnl)

    pnl_1d = future_pnls[0] if len(future_pnls) >= 1 else 0
    pnl_3d = future_pnls[2] if len(future_pnls) >= 3 else pnl_1d
    pnl_5d = future_pnls[4] if len(future_pnls) >= 5 else pnl_3d
    winner = mfe > 1.0  # Would have seen >1% gain

    return pnl_1d, pnl_3d, pnl_5d, mfe, winner


# ═══════════════════════════════════════════════════════════
# MAIN PROFILER
# ═══════════════════════════════════════════════════════════

def load_cache():
    """Load simulation cache."""
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    cache_path = os.path.join(DATA_DIR, "simulation_cache.json")
    with open(cache_path, 'r') as f:
        return json.load(f)


def get_all_dates(cache):
    """Extract sorted unique dates."""
    all_dates = set()
    for ticker_data in cache.get("prices", {}).values():
        all_dates.update(ticker_data.keys())
    return sorted(all_dates)


def run_oracle_profiler(cache):
    """Run the oracle gate profiler over all tickers/dates."""
    all_dates = get_all_dates(cache)
    universe = cache.get("metadata", {}).get("tickers", [])
    flow_all = cache.get("flow", {})
    vix_prices = cache.get("vix", {})

    sim_dates = all_dates[-5:]
    print(f"Oracle Profiler: {sim_dates[0]} → {sim_dates[-1]}")
    print(f"Universe: {len(universe)} tickers")
    print(f"Gates: {len(GATE_REGISTRY)}\n")

    hub = EntryIntelligenceHub()
    # Mock journal
    hub.journal = type('obj', (object,), {'find_similar_trades': lambda self, vec, limit: []})()

    all_rows = []

    for current_date in sim_dates:
        vix_raw = vix_prices.get(current_date, {})
        vix = vix_raw.get('Close', 18.0) if isinstance(vix_raw, dict) else 18.0

        for ticker in universe:
            tp = cache.get("prices", {}).get(ticker, {})
            if current_date not in tp:
                continue

            # Build prices DataFrame
            hist_dates = sorted([d for d in tp.keys() if d <= current_date])[-60:]
            if len(hist_dates) < 20:
                continue

            rows_list = []
            for d in hist_dates:
                rows_list.append({
                    'Date': d,
                    'Open': tp[d].get('Open', tp[d].get('Close', 0)),
                    'High': tp[d].get('High', tp[d].get('Close', 0)),
                    'Low': tp[d].get('Low', tp[d].get('Close', 0)),
                    'Close': tp[d].get('Close', 0),
                    'Volume': tp[d].get('Volume', 0),
                })
            prices_df = pd.DataFrame(rows_list).set_index('Date')

            # Mock options with ATR
            close_price = prices_df['Close'].iloc[-1]
            atr_f = float((prices_df['High'] - prices_df['Low']).rolling(14).mean().iloc[-1]) if len(prices_df) >= 14 else float(close_price) * 0.02
            c_f = float(close_price)
            hub._fetch_options_data = lambda t, c=c_f, a=atr_f: {
                "put_wall": round(c - 2.0 * a, 2),
                "call_wall": round(c + 3.0 * a, 2),
                "gamma_regime": "POSITIVE" if vix < 20 else "NEGATIVE",
                "max_pain": round(c, 2),
            }

            # Flow data
            flow_data = sorted(
                [f for f in flow_all.get(ticker, []) if f.get('date', '') <= current_date],
                key=lambda x: x.get('date', ''), reverse=True
            )[:10]
            dp_prints = [
                {"price": float(f.get("avg_price", 0) or 0), "volume": int(f.get("volume", 0) or 0)}
                for f in flow_data[:3] if float(f.get("volume", 0) or 0) > 100000
            ]

            strategy = "TACTICAL" if len(hist_dates) < 30 else "CORE"
            ref_date = date.fromisoformat(current_date)

            # ── RUN THE FULL HUB ──
            try:
                report = hub.evaluate(
                    ticker, reference_date=ref_date, prices_df=prices_df,
                    vix_override=vix, strategy_bucket=strategy
                )
            except Exception:
                continue

            entry_price = float(prices_df['Close'].iloc[-1])

            # ── ORACLE: Look at the future ──
            pnl_1d, pnl_3d, pnl_5d, mfe, winner = compute_oracle(
                tp, current_date, entry_price, all_dates
            )

            # ── EVALUATE EVERY GATE INDEPENDENTLY ──
            gate_decisions = []
            for gate in GATE_REGISTRY:
                try:
                    decision = gate["evaluate"](report)
                    conditions = gate["conditions"](report)
                    gate_decisions.append(GateDecision(
                        gate_name=gate["name"],
                        decision=decision,
                        reason=gate["description"],
                        conditions=conditions,
                    ))
                except Exception:
                    gate_decisions.append(GateDecision(
                        gate_name=gate["name"],
                        decision="ERROR",
                    ))

            row = OracleRow(
                ticker=ticker,
                date=current_date,
                entry_price=entry_price,
                strategy=strategy,
                future_1d_pnl=round(pnl_1d, 2),
                future_3d_pnl=round(pnl_3d, 2),
                future_5d_pnl=round(pnl_5d, 2),
                future_mfe=round(mfe, 2),
                oracle_winner=winner,
                gate_decisions=gate_decisions,
                hub_snapshot={
                    'final_verdict': report.final_verdict,
                    'phase': report.phase,
                    'rsi': report.rsi,
                    'rsi_regime': report.rsi_regime,
                    'rsi_zone': report.rsi_zone,
                    'rsi_conviction': report.rsi_conviction,
                    'vp_institutional_bias': report.vp_institutional_bias,
                    'vp_bias_confidence': report.vp_bias_confidence,
                    'flow_grade': report.flow_persistence_grade,
                    'whale_verdict': report.whale_verdict,
                    'pattern': report.candlestick_pattern,
                    'dimensions': report.dimensions_confirming,
                },
            )
            all_rows.append(row)

    return all_rows


# ═══════════════════════════════════════════════════════════
# ANALYSIS & REPORTING
# ═══════════════════════════════════════════════════════════

def compute_gate_metrics(rows: list[OracleRow]):
    """Compute confusion matrix and credibility index per gate."""
    gate_stats = defaultdict(lambda: {"TP": 0, "FP": 0, "TN": 0, "FN": 0,
                                       "decisions": [], "conditions_when_wrong": []})

    for row in rows:
        for gd in row.gate_decisions:
            stats = gate_stats[gd.gate_name]
            is_block = gd.decision == "BLOCK"
            is_winner = row.oracle_winner

            if is_block and not is_winner:
                stats["TN"] += 1  # Correctly blocked a loser
            elif is_block and is_winner:
                stats["FN"] += 1  # Wrongly blocked a winner (alpha lost)
                stats["conditions_when_wrong"].append({
                    **gd.conditions,
                    "oracle_mfe": row.future_mfe,
                    "oracle_5d": row.future_5d_pnl,
                    "ticker": row.ticker,
                    "date": row.date,
                })
            elif not is_block and is_winner:
                stats["TP"] += 1  # Correctly passed a winner
            elif not is_block and not is_winner:
                stats["FP"] += 1  # Wrongly passed a loser
                stats["conditions_when_wrong"].append({
                    **gd.conditions,
                    "oracle_mfe": row.future_mfe,
                    "oracle_5d": row.future_5d_pnl,
                    "ticker": row.ticker,
                    "date": row.date,
                })

            stats["decisions"].append({
                "decision": gd.decision,
                "winner": is_winner,
                "correct": (is_block and not is_winner) or (not is_block and is_winner),
            })

    return gate_stats


def print_gate_report(gate_stats, rows):
    """Print comprehensive gate credibility report."""
    total_obs = len(rows)
    total_winners = sum(1 for r in rows if r.oracle_winner)
    total_losers = total_obs - total_winners
    base_rate = total_winners / max(total_obs, 1) * 100

    print("=" * 90)
    print("  ORACLE GATE PROFILER — Perfect Foresight Attribution")
    print("=" * 90)
    print(f"\n  Total Observations: {total_obs}")
    print(f"  Oracle Winners (MFE>1%): {total_winners} ({base_rate:.0f}%)")
    print(f"  Oracle Losers: {total_losers} ({100-base_rate:.0f}%)")

    print("\n" + "─" * 90)
    print(f"  {'GATE':22s} | {'Acc':>5s} | {'Prec':>5s} | {'Recall':>6s} | {'F1':>5s} | {'CRED':>5s} | {'TP':>4s} {'FP':>4s} {'TN':>4s} {'FN':>4s} | {'Blocks':>6s}")
    print("─" * 90)

    gate_rankings = []

    for gate_name in [g["name"] for g in GATE_REGISTRY]:
        s = gate_stats[gate_name]
        tp, fp, tn, fn = s["TP"], s["FP"], s["TN"], s["FN"]
        total = tp + fp + tn + fn

        # Metrics
        accuracy = (tp + tn) / max(total, 1) * 100
        precision = tp / max(tp + fp, 1) * 100
        recall = tp / max(tp + fn, 1) * 100
        f1 = 2 * precision * recall / max(precision + recall, 0.01)
        blocks = fn + tn
        block_rate = blocks / max(total, 1) * 100

        # Credibility Index: weighted combination
        # High credibility = high accuracy + blocks mostly correct + doesn't lose alpha
        alpha_preservation = tp / max(tp + fn, 1)  # How much alpha we keep
        block_accuracy = tn / max(tn + fn, 1) if blocks > 0 else 1.0  # When it blocks, is it right?
        credibility = (accuracy / 100 * 0.4 + alpha_preservation * 0.3 + block_accuracy * 0.3) * 100

        print(f"  {gate_name:22s} | {accuracy:4.0f}% | {precision:4.0f}% | {recall:5.0f}% | {f1:4.0f}% | {credibility:4.0f}% | {tp:4d} {fp:4d} {tn:4d} {fn:4d} | {block_rate:5.1f}%")

        gate_rankings.append((gate_name, credibility, accuracy, fn))

    # ── TOP ALPHA DESTROYERS ──
    print("\n" + "=" * 90)
    print("  🔴 GATES DESTROYING ALPHA (Most False Negatives)")
    print("=" * 90)

    for name, cred, acc, fn_count in sorted(gate_rankings, key=lambda x: -x[3])[:5]:
        s = gate_stats[name]
        if fn_count > 0:
            print(f"\n  {name} — {fn_count} winners incorrectly blocked (credibility={cred:.0f}%)")
            # Show conditions when wrong
            for w in s["conditions_when_wrong"][:3]:
                if not any(not d["correct"] and d["decision"] == "BLOCK" for d in s["decisions"]):
                    continue
                conds = " | ".join(f"{k}={v}" for k, v in w.items()
                                   if k not in ('oracle_mfe', 'oracle_5d', 'ticker', 'date'))
                print(f"    ❌ {w.get('ticker','?')} {w.get('date','?')}: MFE={w.get('oracle_mfe',0):+.1f}% | {conds}")

    # ── CREDIBILITY RANKING ──
    print("\n" + "=" * 90)
    print("  📊 GATE CREDIBILITY RANKING")
    print("=" * 90)

    for rank, (name, cred, acc, fn_count) in enumerate(sorted(gate_rankings, key=lambda x: -x[1]), 1):
        bar = "█" * int(cred / 5) + "░" * (20 - int(cred / 5))
        emoji = "🟢" if cred >= 60 else "🟡" if cred >= 40 else "🔴"
        print(f"  {rank}. {emoji} {name:22s} | {bar} | {cred:.0f}%")


def train_gate_ml(gate_stats, rows):
    """Train mini Random Forest per gate to understand failure patterns."""
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import LabelEncoder
        has_sklearn = True
    except ImportError:
        has_sklearn = False

    print("\n" + "=" * 90)
    print("  🤖 ML GATE FAILURE ANALYSIS")
    print("=" * 90)

    if not has_sklearn:
        print("  ⚠️  scikit-learn not installed. Run: pip install scikit-learn")
        print("  Skipping ML analysis.")
        return

    # Build per-gate datasets
    for gate in GATE_REGISTRY:
        name = gate["name"]
        s = gate_stats[name]
        wrong_conditions = s["conditions_when_wrong"]

        if len(wrong_conditions) < 10:
            continue

        print(f"\n  Gate: {name} ({len(wrong_conditions)} errors)")

        # Build feature matrix from conditions
        df = pd.DataFrame(wrong_conditions)
        # Remove non-numeric for ML
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = [c for c in df.columns if c not in numeric_cols
                    and c not in ('ticker', 'date', 'oracle_mfe', 'oracle_5d')]

        if not numeric_cols and not cat_cols:
            print(f"    No analyzable features.")
            continue

        # Encode categoricals
        encoders = {}
        for col in cat_cols:
            le = LabelEncoder()
            df[col + "_enc"] = le.fit_transform(df[col].astype(str))
            encoders[col] = le
            numeric_cols.append(col + "_enc")

        if len(numeric_cols) < 2:
            continue

        X = df[numeric_cols].fillna(0)
        y = (df['oracle_mfe'] > 1.0).astype(int)  # Was it a missed winner?

        if y.nunique() < 2:
            print(f"    Insufficient variance in outcomes.")
            continue

        model = RandomForestClassifier(n_estimators=50, max_depth=4, random_state=42)
        model.fit(X, y)

        # Feature importance
        importances = sorted(zip(numeric_cols, model.feature_importances_),
                           key=lambda x: -x[1])
        print(f"    Top features predicting gate failure:")
        for feat, imp in importances[:5]:
            if imp > 0.05:
                print(f"      {feat:25s} → importance={imp:.2f}")

        # Accuracy of the failure predictor
        acc = model.score(X, y) * 100
        print(f"    ML model accuracy: {acc:.0f}%")


def export_csv(rows, gate_stats):
    """Export gate profiler results to CSV."""
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    export_rows = []
    for row in rows:
        base = {
            'ticker': row.ticker,
            'date': row.date,
            'entry_price': row.entry_price,
            'strategy': row.strategy,
            'oracle_1d': row.future_1d_pnl,
            'oracle_3d': row.future_3d_pnl,
            'oracle_5d': row.future_5d_pnl,
            'oracle_mfe': row.future_mfe,
            'oracle_winner': row.oracle_winner,
            **row.hub_snapshot,
        }
        # Add each gate's decision as a column
        for gd in row.gate_decisions:
            base[f'gate_{gd.gate_name}'] = gd.decision
        export_rows.append(base)

    df = pd.DataFrame(export_rows)
    csv_path = os.path.join(DATA_DIR, "oracle_gate_profile.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n  ✅ Exported {len(df)} rows × {len(df.columns)} cols → {csv_path}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("Loading cache...")
    cache = load_cache()

    print("Running Oracle Gate Profiler...\n")
    rows = run_oracle_profiler(cache)

    if not rows:
        print("No data generated!")
        return

    print(f"\nProfiled {len(rows)} ticker/day combinations.\n")

    # Compute metrics
    gate_stats = compute_gate_metrics(rows)

    # Print report
    print_gate_report(gate_stats, rows)

    # ML analysis
    train_gate_ml(gate_stats, rows)

    # Export
    export_csv(rows, gate_stats)


if __name__ == "__main__":
    main()
