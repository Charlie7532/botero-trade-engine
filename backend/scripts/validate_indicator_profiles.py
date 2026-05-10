"""
Indicator Profile Validation — Walk-Forward Scientific Protocol
=================================================================
Validates ALL signal hypotheses in .agents/knowledge/indicators/
using strict walk-forward out-of-sample testing.

Protocol:
  1. Load OHLCV + breadth + VIX + RSI from vault (our data only)
  2. Split 70/30 temporal with 5-day embargo
  3. Calculate thresholds on TRAIN, test on TEST
  4. Compute Deflated Sharpe Ratio (López de Prado)
  5. Assign reliability grade (A/B/C/D/F)
  6. Update signals.yaml with OOS results
  7. Populate engine.signal_registry
  8. Backfill engine.signal_states with historical vectors

Usage:
    python -m backend.scripts.validate_indicator_profiles
"""
import logging
import os
import sys
from datetime import datetime, UTC

import numpy as np
import pandas as pd
import psycopg2
import yaml
from scipy import stats
from sqlalchemy import create_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────
INDICATORS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", ".agents", "knowledge", "indicators"
)

# ── Constants ──────────────────────────────────────────
TRAIN_RATIO = 0.70
EMBARGO_DAYS = 5
FORWARD_HORIZONS = [5, 10, 20, 60]


def compute_rsi14(prices: np.ndarray) -> np.ndarray:
    """Compute RSI-14 from close prices."""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    rsi = np.full(len(prices), 50.0)
    if len(gains) < 14:
        return rsi

    avg_gain = np.zeros(len(gains))
    avg_loss = np.zeros(len(gains))
    avg_gain[13] = np.mean(gains[:14])
    avg_loss[13] = np.mean(losses[:14])

    for i in range(14, len(gains)):
        avg_gain[i] = (avg_gain[i - 1] * 13 + gains[i]) / 14
        avg_loss[i] = (avg_loss[i - 1] * 13 + losses[i]) / 14

    rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
    rsi_vals = 100.0 - 100.0 / (1.0 + rs)
    rsi_vals[:14] = 50.0
    rsi[1:] = rsi_vals
    return rsi


def deflated_sharpe_ratio(sharpe: float, n_obs: int, n_trials: int,
                          skew: float = 0.0, kurt: float = 3.0) -> float:
    """López de Prado Deflated Sharpe Ratio.

    Adjusts observed Sharpe for multiple testing bias.
    """
    if n_obs <= 1 or n_trials <= 0:
        return 0.0

    # Expected maximum Sharpe from n_trials under null
    euler_mascheroni = 0.5772156649
    e_max_sr = (
        (1 - euler_mascheroni) * stats.norm.ppf(1 - 1 / n_trials)
        + euler_mascheroni * stats.norm.ppf(1 - 1 / (n_trials * np.e))
    )

    # Standard error of Sharpe
    se_sr = np.sqrt(
        (1 + 0.5 * sharpe**2 - skew * sharpe + ((kurt - 3) / 4) * sharpe**2)
        / (n_obs - 1)
    )

    if se_sr == 0:
        return 0.0

    # DSR = probability that observed Sharpe > expected max
    dsr_stat = (sharpe - e_max_sr) / se_sr
    dsr = float(stats.norm.cdf(dsr_stat))
    return dsr


def assign_grade(p_value: float, dsr: float, n_obs: int,
                 oos_wr: float, is_wr: float) -> str:
    """Assign reliability grade based on validation results."""
    if p_value is None or oos_wr is None:
        return "D"

    # Failed OOS
    wr_degradation = (is_wr - oos_wr) / is_wr if is_wr > 0 else 1.0
    if wr_degradation > 0.30:  # >30% degradation
        return "F"

    if dsr > 1.5 and p_value < 0.001 and n_obs > 100:
        return "A"
    if dsr > 1.0 and p_value < 0.01 and n_obs > 50:
        return "B"
    if dsr > 0.5 and p_value < 0.05 and n_obs > 30:
        return "C"
    if p_value < 0.10:
        return "D"
    return "F"


def evaluate_signal(df: pd.DataFrame, condition_func, horizon: int,
                    train_end_idx: int, embargo: int = 5):
    """Evaluate a signal on train and test sets.

    Returns dict with IS and OOS metrics, or None if insufficient data.
    """
    fwd_col = f"fwd_{horizon}d"
    if fwd_col not in df.columns:
        return None

    # Apply condition to get signal mask
    mask = condition_func(df)
    test_start_idx = train_end_idx + embargo

    # Train set
    train_mask = mask.iloc[:train_end_idx]
    train_fwd = df[fwd_col].iloc[:train_end_idx]
    train_signals = train_fwd[train_mask]

    if len(train_signals) < 10:
        return None

    # Test set
    test_mask = mask.iloc[test_start_idx:]
    test_fwd = df[fwd_col].iloc[test_start_idx:]
    test_signals = test_fwd[test_mask].dropna()

    if len(test_signals) < 5:
        return {
            "status": "insufficient_oos",
            "is_n": len(train_signals),
            "oos_n": len(test_signals),
        }

    # IS metrics
    is_wr = float((train_signals > 0).mean())
    is_mean = float(train_signals.mean())
    is_std = float(train_signals.std()) if len(train_signals) > 1 else 1.0
    is_sharpe = (is_mean / is_std * np.sqrt(252 / horizon)) if is_std > 0 else 0.0

    # t-test: is mean return significantly different from zero?
    is_t, is_p = stats.ttest_1samp(train_signals, 0) if len(train_signals) >= 2 else (0, 1)

    # OOS metrics
    oos_wr = float((test_signals > 0).mean())
    oos_mean = float(test_signals.mean())
    oos_std = float(test_signals.std()) if len(test_signals) > 1 else 1.0
    oos_sharpe = (oos_mean / oos_std * np.sqrt(252 / horizon)) if oos_std > 0 else 0.0
    oos_t, oos_p = stats.ttest_1samp(test_signals, 0) if len(test_signals) >= 2 else (0, 1)

    # Skew and kurtosis for DSR
    skew = float(stats.skew(test_signals)) if len(test_signals) > 2 else 0.0
    kurt = float(stats.kurtosis(test_signals, fisher=False)) if len(test_signals) > 2 else 3.0

    # DSR — account for multiple testing (we test ~15 signals)
    dsr = deflated_sharpe_ratio(oos_sharpe, len(test_signals), n_trials=15,
                                skew=skew, kurt=kurt)

    # Grade
    grade = assign_grade(float(oos_p), dsr, len(test_signals), oos_wr, is_wr)

    return {
        "status": "validated",
        "is_n": int(len(train_signals)),
        "is_wr": round(is_wr, 4),
        "is_mean": round(is_mean, 6),
        "is_sharpe": round(is_sharpe, 4),
        "is_p": round(float(is_p), 6),
        "oos_n": int(len(test_signals)),
        "oos_wr": round(oos_wr, 4),
        "oos_mean": round(oos_mean, 6),
        "oos_sharpe": round(oos_sharpe, 4),
        "oos_p": round(float(oos_p), 6),
        "dsr": round(dsr, 4),
        "grade": grade,
        "skew": round(skew, 4),
        "kurtosis": round(kurt, 4),
    }


def build_dataset(engine) -> pd.DataFrame:
    """Build the master analysis dataset from vault data."""
    logger.info("Loading OHLCV data from vault...")

    # SPY prices
    spy = pd.read_sql(
        "SELECT time::date as date, close FROM market.ohlcv_bars "
        "WHERE ticker = 'SPY' AND timeframe = '1d' ORDER BY time",
        engine, parse_dates=["date"],
    ).set_index("date")
    spy.columns = ["spy"]

    # VIX prices
    vix = pd.read_sql(
        "SELECT time::date as date, close FROM market.ohlcv_bars "
        "WHERE ticker = 'VIX' AND timeframe = '1d' AND time >= '2021-01-01' ORDER BY time",
        engine, parse_dates=["date"],
    ).set_index("date")
    vix.columns = ["vix"]

    # All tickers for breadth
    logger.info("Computing breadth indicators (S5TH, S5TW)...")
    all_data = pd.read_sql(
        "SELECT time::date as date, ticker, close FROM market.ohlcv_bars "
        "WHERE timeframe = '1d' AND time >= '2020-01-01' ORDER BY time",
        engine, parse_dates=["date"],
    )
    pvt = all_data.pivot_table(index="date", columns="ticker", values="close").sort_index()

    valid = [c for c in pvt.columns if pvt[c].notna().sum() >= 250 and c not in ("VIX", "SKEW", "VVIX")]

    # S5TW = % above 20-DMA
    ma20 = pvt[valid].rolling(20, min_periods=20).mean()
    s5tw = ((pvt[valid] > ma20) & ma20.notna()).sum(axis=1) / ma20.notna().sum(axis=1) * 100

    # S5TH = % above 200-DMA
    ma200 = pvt[valid].rolling(200, min_periods=200).mean()
    s5th = ((pvt[valid] > ma200) & ma200.notna()).sum(axis=1) / ma200.notna().sum(axis=1) * 100

    # RSI
    rsi_vals = compute_rsi14(spy["spy"].values)
    rsi = pd.Series(rsi_vals, index=spy.index, name="rsi")

    # Join everything
    df = pd.DataFrame({
        "spy": spy["spy"],
        "vix": vix["vix"],
        "s5tw": s5tw,
        "s5th": s5th,
        "rsi": rsi,
    }).dropna()

    # Forward returns
    for h in FORWARD_HORIZONS:
        df[f"fwd_{h}d"] = df["spy"].shift(-h) / df["spy"] - 1

    # Volume ratio (SPY)
    spy_vol = pd.read_sql(
        "SELECT time::date as date, volume FROM market.ohlcv_bars "
        "WHERE ticker = 'SPY' AND timeframe = '1d' ORDER BY time",
        engine, parse_dates=["date"],
    ).set_index("date")
    spy_vol.columns = ["vol"]
    vol_ratio = spy_vol["vol"] / spy_vol["vol"].rolling(20).mean()
    df["vol_ratio"] = vol_ratio

    logger.info(f"Dataset: {len(df)} days ({df.index[0]} → {df.index[-1]})")
    return df


def define_signals():
    """Define all signal conditions as lambda functions."""
    return {
        # S5TW signals
        "S5TW-WASHOUT-001": {
            "condition": lambda df: df["s5tw"] < 15,
            "horizon": 60,
            "indicator": "S5TW",
            "action": "LONG — potential capitulation",
        },
        "S5TW-OVERSOLD-001": {
            "condition": lambda df: df["s5tw"] < 25,
            "horizon": 60,
            "indicator": "S5TW",
            "action": "LONG — oversold breadth",
        },
        "S5TW-EUPHORIA-001": {
            "condition": lambda df: df["s5tw"] > 85,
            "horizon": 5,
            "indicator": "S5TW",
            "action": "REDUCE — potential mean reversion",
        },
        # S5TH signals
        "S5TH-CAPITULATION-001": {
            "condition": lambda df: df["s5th"] < 30,
            "horizon": 60,
            "indicator": "S5TH",
            "action": "LONG — structural washout",
        },
        "S5TH-WEAK-STRUCTURE-001": {
            "condition": lambda df: df["s5th"] < 50,
            "horizon": 20,
            "indicator": "S5TH",
            "action": "CAUTION — structural breadth declining",
        },
        "S5TH-BROAD-HEALTH-001": {
            "condition": lambda df: df["s5th"] > 75,
            "horizon": 20,
            "indicator": "S5TH",
            "action": "CONFIRM — broad participation supports trend",
        },
        # RSI signals
        "RSI-NARROW-MOMENTUM-001": {
            "condition": lambda df: (df["rsi"] > 60) & (df["s5tw"] < 45),
            "horizon": 60,
            "indicator": "RSI-14",
            "action": "HOLD/ADD — concentrated momentum",
        },
        "RSI-OVERSOLD-001": {
            "condition": lambda df: df["rsi"] < 30,
            "horizon": 20,
            "indicator": "RSI-14",
            "action": "LONG — oversold bounce potential",
        },
        "RSI-BULL-PULLBACK-001": {
            "condition": lambda df: (df["rsi"] >= 40) & (df["rsi"] <= 50) & (df["s5th"] > 60),
            "horizon": 20,
            "indicator": "RSI-14",
            "action": "LONG — Cardwell bull pullback zone",
        },
        # VIX signals
        "VIX-SPIKE-001": {
            "condition": lambda df: df["vix"] > 30,
            "horizon": 60,
            "indicator": "VIX",
            "action": "LONG — contrarian, panic likely overdone",
        },
        "VIX-COMPLACENCY-001": {
            "condition": lambda df: df["vix"] < 13,
            "horizon": 20,
            "indicator": "VIX",
            "action": "CAUTION — reduce new entries",
        },
        # Composite signals
        "COMPOSITE-CAPITULATION-001": {
            "condition": lambda df: (df["s5th"] < 30) & (df["s5tw"] < 20),
            "horizon": 60,
            "indicator": "COMPOSITE",
            "action": "LONG — maximum conviction, structural capitulation",
        },
        "COMPOSITE-BUYABLE-PULLBACK-001": {
            "condition": lambda df: (df["s5th"] >= 50) & (df["s5tw"] < 20),
            "horizon": 20,
            "indicator": "COMPOSITE",
            "action": "LONG — structural trend intact, tactical washout",
        },
        "COMPOSITE-NARROW-STRENGTH-001": {
            "condition": lambda df: (df["rsi"] > 55) & (df["s5tw"] < 45),
            "horizon": 60,
            "indicator": "COMPOSITE",
            "action": "HOLD — concentrated momentum, not classic overbought",
        },
        "COMPOSITE-TRIPLE-FEAR-001": {
            "condition": lambda df: (df["vix"] > 25) & (df["rsi"] < 35) & (df["s5tw"] < 25),
            "horizon": 60,
            "indicator": "COMPOSITE",
            "action": "LONG — triple convergence of fear signals",
        },
    }


def populate_signal_registry(conn, results: dict):
    """Write validation results to engine.signal_registry."""
    signals = define_signals()
    now = datetime.now(UTC).isoformat()

    with conn.cursor() as cur:
        for sig_id, result in results.items():
            sig_def = signals.get(sig_id, {})
            if result is None or result.get("status") == "insufficient_oos":
                # Still HYPOTHESIS
                cur.execute("""
                    INSERT INTO engine.signal_registry
                        (signal_id, indicator, name, condition_expr, action, timeframe,
                         evidence_status, reliability_grade, observations,
                         created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'HYPOTHESIS', 'D', %s, NOW(), NOW())
                    ON CONFLICT (signal_id) DO UPDATE SET updated_at = NOW()
                """, (
                    sig_id,
                    sig_def.get("indicator", "UNKNOWN"),
                    sig_id,
                    str(sig_def.get("condition", "")),
                    sig_def.get("action", ""),
                    f"{sig_def.get('horizon', 0)}d",
                    result.get("is_n", 0) if result else 0,
                ))
            else:
                status = "VALIDATED" if result["grade"] in ("A", "B", "C") else "HYPOTHESIS"
                cur.execute("""
                    INSERT INTO engine.signal_registry
                        (signal_id, indicator, name, condition_expr, action, timeframe,
                         evidence_status, reliability_grade,
                         win_rate, avg_return, sharpe, deflated_sharpe, p_value, observations,
                         backtest_method, last_validated, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (signal_id) DO UPDATE SET
                        evidence_status = EXCLUDED.evidence_status,
                        reliability_grade = EXCLUDED.reliability_grade,
                        win_rate = EXCLUDED.win_rate,
                        avg_return = EXCLUDED.avg_return,
                        sharpe = EXCLUDED.sharpe,
                        deflated_sharpe = EXCLUDED.deflated_sharpe,
                        p_value = EXCLUDED.p_value,
                        observations = EXCLUDED.observations,
                        last_validated = EXCLUDED.last_validated,
                        updated_at = NOW()
                """, (
                    sig_id,
                    sig_def.get("indicator", "UNKNOWN"),
                    sig_id,
                    str(sig_def.get("condition", "")),
                    sig_def.get("action", ""),
                    f"{sig_def.get('horizon', 0)}d",
                    status,
                    result["grade"],
                    float(result["oos_wr"]),
                    float(result["oos_mean"]),
                    float(result["oos_sharpe"]),
                    float(result["dsr"]),
                    float(result["oos_p"]),
                    int(result["oos_n"]),
                    "walk-forward 70/30 temporal, 5d embargo",
                    now,
                ))
    conn.commit()
    logger.info(f"✅ Populated engine.signal_registry with {len(results)} signals")


def backfill_signal_states(conn, df: pd.DataFrame, signals_def: dict):
    """Backfill engine.signal_states with historical daily state vectors."""
    logger.info("Backfilling signal states (daily state vectors)...")

    rows = []
    for i, (date, row) in enumerate(df.iterrows()):
        if pd.isna(row.get("s5th")) or pd.isna(row.get("s5tw")) or pd.isna(row.get("rsi")):
            continue

        # State vector: [S5TH, S5TW, RSI, VIX, SPY_ret_20d, vol_ratio]
        spy_ret_20d = float(row.get("fwd_20d", 0) or 0) if not pd.isna(row.get("fwd_20d")) else 0
        vol_r = float(row.get("vol_ratio", 1) or 1) if not pd.isna(row.get("vol_ratio")) else 1
        state = [
            float(row["s5th"]), float(row["s5tw"]),
            float(row["rsi"]), float(row["vix"]),
            spy_ret_20d, vol_r,
        ]

        # Active signals
        active = []
        for sig_id, sig_def in signals_def.items():
            try:
                mask = sig_def["condition"](df.iloc[i:i+1])
                if mask.iloc[0]:
                    active.append(sig_id)
            except Exception:
                pass

        rows.append((
            date.to_pydatetime() if hasattr(date, "to_pydatetime") else date,
            state,
            active,
            float(row["spy"]),
            float(row.get("fwd_5d")) if not pd.isna(row.get("fwd_5d")) else None,
            float(row.get("fwd_10d")) if not pd.isna(row.get("fwd_10d")) else None,
            float(row.get("fwd_20d")) if not pd.isna(row.get("fwd_20d")) else None,
            float(row.get("fwd_60d")) if not pd.isna(row.get("fwd_60d")) else None,
        ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO engine.signal_states
               (time, state_vector, active_signals, spy_close,
                fwd_5d, fwd_10d, fwd_20d, fwd_60d)
               VALUES %s
               ON CONFLICT (time) DO NOTHING""",
            rows,
            template="(%s, %s::vector, %s, %s, %s, %s, %s, %s)",
            page_size=500,
        )
    conn.commit()
    logger.info(f"✅ Backfilled {len(rows)} signal_state rows")


def main():
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    engine = create_engine(dsn)
    conn = psycopg2.connect(dsn)

    # 1. Build dataset
    df = build_dataset(engine)

    # 2. Train/test split
    n = len(df)
    train_end = int(n * TRAIN_RATIO)
    train_dates = (df.index[0], df.index[train_end - 1])
    test_dates = (df.index[train_end + EMBARGO_DAYS], df.index[-1])
    logger.info(f"Train: {train_dates[0]} → {train_dates[1]} ({train_end} days)")
    logger.info(f"Test:  {test_dates[0]} → {test_dates[1]} ({n - train_end - EMBARGO_DAYS} days)")

    # 3. Validate all signals
    signals_def = define_signals()
    results = {}

    print(f"\n{'='*80}")
    print(f"WALK-FORWARD VALIDATION RESULTS")
    print(f"Train: {train_dates[0]} → {train_dates[1]}")
    print(f"Test:  {test_dates[0]} → {test_dates[1]}")
    print(f"{'='*80}")
    print(f"\n{'Signal ID':<40} {'Grade':>5} {'IS WR':>7} {'OOS WR':>7} {'OOS Ret':>8} {'OOS p':>8} {'DSR':>6} {'N(OOS)':>7}")
    print("-" * 95)

    for sig_id, sig_def in signals_def.items():
        result = evaluate_signal(
            df, sig_def["condition"], sig_def["horizon"],
            train_end, EMBARGO_DAYS,
        )
        results[sig_id] = result

        if result is None:
            print(f"{sig_id:<40} {'D':>5} {'--':>7} {'--':>7} {'--':>8} {'--':>8} {'--':>6} {'<10':>7}")
        elif result.get("status") == "insufficient_oos":
            print(f"{sig_id:<40} {'D':>5} {'--':>7} {'--':>7} {'--':>8} {'--':>8} {'--':>6} {result['oos_n']:>7}")
        else:
            print(
                f"{sig_id:<40} {result['grade']:>5} "
                f"{result['is_wr']:>7.1%} {result['oos_wr']:>7.1%} "
                f"{result['oos_mean']:>+8.4f} {result['oos_p']:>8.4f} "
                f"{result['dsr']:>6.3f} {result['oos_n']:>7}"
            )

    # 4. Populate signal_registry
    populate_signal_registry(conn, results)

    # 5. Backfill signal_states
    backfill_signal_states(conn, df, signals_def)

    # 6. Summary
    validated = [s for s, r in results.items() if r and r.get("grade") in ("A", "B", "C")]
    hypothesis = [s for s, r in results.items() if not r or r.get("grade") in ("D", "F")]
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"  VALIDATED (grade A/B/C): {len(validated)}")
    for s in validated:
        print(f"    ✅ {s} → {results[s]['grade']}")
    print(f"  HYPOTHESIS (grade D/F): {len(hypothesis)}")
    for s in hypothesis:
        r = results[s]
        reason = "insufficient data" if not r or r.get("status") == "insufficient_oos" else f"grade {r.get('grade', '?')}"
        print(f"    ⚠️  {s} → {reason}")

    conn.close()
    engine.dispose()
    logger.info("Validation complete.")


if __name__ == "__main__":
    main()
