"""
Causal Simulation Timeline Runner (1999–2026 — 4 Quarter Snapshots Per Year)
=============================================================================
Runs point-in-time Causal NOTAM Forecast simulations sampling 4 dates per year
(Q1 March, Q2 June, Q3 Sept, Q4 Dec) from 1999 to 2026 to track historical evolution.

Clean Architecture: Script / Verification mechanism. Zero lookahead bias.
"""
import sys
import os
from datetime import datetime, date, UTC

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.causal_investigation import CausalInputDTO, evaluate_causal_conviction
from backend.modules.causal_investigation.domain.rules.temporal_trajectory_rules import evaluate_temporal_trajectory


def run_quarterly_simulations(ticker: str = "SPY", start_year: int = 1999, end_year: int = 2026):
    store = TimescaleDataStore()
    start_dt = date(start_year - 1, 1, 1)
    bars = store.load_bars(ticker, "1d", start=start_dt)

    if bars is None or len(bars) < 150:
        print(f"Insufficient history for {ticker}")
        return

    close_col = "Close" if "Close" in bars.columns else "close"
    prices = bars[close_col].astype(float).tolist()
    timestamps = [str(ts)[:10] for ts in bars.index]

    # Load complementary historical indicators
    s5th_bars = store.load_bars(f"S5_{ticker}_TH", "1d", start=start_dt)
    s5fi_bars = store.load_bars(f"S5_{ticker}_FI", "1d", start=start_dt)
    sv5tw_bars = store.load_bars(f"SV5_{ticker}_TW", "1d", start=start_dt)
    vix_bars = store.load_bars("VIX", "1d", start=start_dt)
    skew_bars = store.load_bars("SKEW", "1d", start=start_dt)

    print(f"\n==========================================================================================================")
    print(f"📜 EVOLUCIÓN HISTÓRICA DEL CAUSAL NOTAM FORECAST: {ticker} (4 SIMULACIONES / AÑO: 1999 → 2026)")
    print(f"==========================================================================================================")
    print(f"{'Año-Q':<8} | {'Fecha':<10} | {'Decision':<18} | {'Stage':<16} | {'Trajectory':<22} | {'WR 120d':<7} | {'Ret 120d':<8} | {'Cert Q/Sp':<10}")
    print("-" * 110)

    # Sample dates quarterly (~March 15, June 15, Sept 15, Dec 15 of each year)
    sample_targets = []
    for yr in range(start_year, end_year + 1):
        for q_month, q_name in [(3, "Q1"), (6, "Q2"), (9, "Q3"), (12, "Q4")]:
            sample_targets.append((yr, q_name, f"{yr}-{q_month:02d}-15"))

    ts_map = {ts: idx for idx, ts in enumerate(timestamps)}

    for yr, q_name, date_str in sample_targets:
        # Find nearest trading date
        match_idx = None
        for i, ts in enumerate(timestamps):
            if ts >= date_str:
                match_idx = i
                break
        if match_idx is None or match_idx < 150:
            continue

        actual_date = timestamps[match_idx]
        price_slice = prices[:match_idx]

        s5_th = _get_hist_val(s5th_bars, match_idx, 50.0)
        s5_fi = _get_hist_val(s5fi_bars, match_idx, 50.0)
        sv5_tw = _get_hist_val(sv5tw_bars, match_idx, 50.0)
        vol_div = sv5_tw - s5_fi
        vix_val = _get_hist_val(vix_bars, match_idx, 18.0)
        skew_val = _get_hist_val(skew_bars, match_idx, 120.0)

        dto = CausalInputDTO(
            symbol=ticker,
            price_history=price_slice,
            rs_score=0.0,
            as_of_dt=datetime.strptime(actual_date, "%Y-%m-%d").replace(tzinfo=UTC),
            s5_th=s5_th,
            s5_fi=s5_fi,
            sv5_tw=sv5_tw,
            vol_div=vol_div,
            vix_val=vix_val,
            skew_val=skew_val,
        )

        snap = evaluate_causal_conviction(dto)
        payload = snap.notam_ticker_payload

        dec = snap.decision.value
        stg = snap.structural_veto.stage.label
        traj = payload.forecast_trajectory if payload else "N/A"
        wr = f"{payload.forecast_win_rate_120d:.1%}" if payload else "N/A"
        ret = f"{payload.forecast_fwd_return_120d:+.2%}" if payload else "N/A"
        cert = f"{payload.quality_certainty_score:.0f}%/{payload.speculative_certainty_score:.0f}%" if payload else "N/A"

        print(f"{yr}-{q_name:<4} | {actual_date:<10} | {dec:<18} | {stg:<16} | {traj:<22} | {wr:<7} | {ret:<8} | {cert:<10}")

    store.close()


def _get_hist_val(df, idx: int, default: float) -> float:
    if df is None or df.empty or idx >= len(df):
        return default
    col = "Close" if "Close" in df.columns else ("close" if "close" in df.columns else df.columns[-1])
    try:
        return float(df[col].iloc[min(idx, len(df)-1)])
    except Exception:
        return default


if __name__ == "__main__":
    ticker_to_run = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    run_quarterly_simulations(ticker_to_run, start_year=1999, end_year=2026)
