"""
Data Harmonizer — Raw Vault → ML-Ready Features
===================================================
Transforms raw JSON (UW, GuruFocus) and Parquet (OHLCV, macro)
into harmonized feature DataFrames ready for ML training and
Oracle evaluation.

Harmonization Rules (see data_harmonization_plan.md):
- R1: All timestamps → UTC
- R3: UW Flow → 11 canonical feature columns
- R4: Market-wide → 9 feature columns
- R5: Macro → 11 feature columns
- R8: Cross-source join by timestamp UTC with forward-fill
"""
import logging
from datetime import date
from typing import Optional

import pandas as pd

from backend.modules.simulation.domain.ports.time_series_port import TimeSeriesPort

logger = logging.getLogger(__name__)


class DataHarmonizer:
    """Transforms raw vault data into ML-ready feature DataFrames."""

    def __init__(self, store: TimeSeriesPort):
        self.store = store

    def harmonize_uw_flow(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """
        Load raw UW JSON alerts for a ticker and transform into
        daily feature DataFrame with canonical columns.

        Output columns: uw_sweep_count, uw_call_put_ratio, uw_flow_score,
        uw_total_premium, uw_net_premium, uw_voi_avg, uw_ask_bid_ratio,
        uw_darkpool_premium, uw_persistence_grade, uw_persistence_score
        """
        raw_entries = self.store.load_mcp_range("flow/alerts", ticker, start, end)
        if not raw_entries:
            return pd.DataFrame()

        rows = []
        for dt, alerts in raw_entries:
            if not alerts or not isinstance(alerts, list):
                continue

            n_calls = sum(1 for a in alerts if a.get("type") == "call" or a.get("call_volume"))
            n_puts = sum(1 for a in alerts if a.get("type") == "put" or a.get("put_volume"))
            n_sweeps = sum(1 for a in alerts if a.get("has_sweep"))

            call_prem = sum(float(a.get("call_premium", 0) or a.get("total_premium", 0) or 0)
                           for a in alerts if a.get("type") == "call")
            put_prem = sum(float(a.get("put_premium", 0) or a.get("total_premium", 0) or 0)
                          for a in alerts if a.get("type") == "put")

            # Handle aggregate format
            if alerts and "call_volume" in alerts[0]:
                n_calls = sum(int(a.get("call_volume", 0) or 0) for a in alerts)
                n_puts = sum(int(a.get("put_volume", 0) or 0) for a in alerts)
                call_prem = sum(float(a.get("call_premium", 0) or 0) for a in alerts)
                put_prem = sum(float(a.get("put_premium", 0) or 0) for a in alerts)
                avg_call_vol = int(alerts[0].get("avg_30_day_call_volume", 0) or 0)
                if avg_call_vol > 0 and n_calls / max(len(alerts), 1) > avg_call_vol * 1.5:
                    n_sweeps = max(1, int((n_calls / max(len(alerts), 1) / avg_call_vol - 1) * 10))

            voi_values = [float(a.get("volume_oi_ratio", 0) or 0) for a in alerts if a.get("volume_oi_ratio")]
            ask_vals = [float(a.get("total_ask_side_prem", 0) or 0) for a in alerts]
            bid_vals = [float(a.get("total_bid_side_prem", 0) or 0) for a in alerts]

            cp_ratio = n_calls / max(n_puts, 1)
            total_prem = call_prem + put_prem
            net_prem = call_prem - put_prem
            voi_avg = sum(voi_values) / max(len(voi_values), 1)
            ask_total = sum(ask_vals)
            bid_total = sum(bid_vals)
            ab_ratio = ask_total / max(bid_total, 1)

            # Simple flow score (mirrors UWIntelligence scoring)
            score = 0.0
            if n_sweeps > 5: score += 40
            elif n_sweeps > 0: score += 25
            if voi_avg > 2.0: score += 25
            elif voi_avg > 1.0: score += 15
            if cp_ratio > 2.0: score += 15
            elif cp_ratio > 1.0: score += 10
            if ab_ratio > 1.5: score += 10
            elif ab_ratio > 1.0: score += 5
            if total_prem > 1_000_000: score += 10
            elif total_prem > 100_000: score += 5

            # Load darkpool if available
            dp_data = self.store.load_mcp_snapshot("flow/darkpool", ticker, dt)
            dp_premium = 0.0
            if dp_data and isinstance(dp_data, list):
                dp_premium = sum(
                    float(d.get("size", 0)) * float(d.get("price", 0))
                    for d in dp_data
                )

            rows.append({
                "timestamp": pd.Timestamp(f"{dt}T20:00:00", tz="UTC"),
                "uw_sweep_count": n_sweeps,
                "uw_call_put_ratio": round(cp_ratio, 4),
                "uw_flow_score": min(100.0, score),
                "uw_total_premium": total_prem,
                "uw_net_premium": net_prem,
                "uw_voi_avg": round(voi_avg, 4),
                "uw_ask_bid_ratio": round(ab_ratio, 4),
                "uw_darkpool_premium": dp_premium,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        return df

    def harmonize_market_flow(self, start: str, end: str) -> pd.DataFrame:
        """
        Harmonize market-wide flow data (SPY gate + sentiment + tide).
        Output: vault/features/_MARKET/flow_1d.parquet
        """
        rows = []
        spy_entries = self.store.load_mcp_range("flow/spy", "SPY", start, end)
        sent_entries = self.store.load_mcp_range("flow/sentiment", "MARKET", start, end)
        tide_entries = self.store.load_mcp_range("flow/tide", "MARKET", start, end)

        # Index by date for joining
        spy_by_date = {dt: data for dt, data in spy_entries}
        sent_by_date = {dt: data for dt, data in sent_entries}
        tide_by_date = {dt: data for dt, data in tide_entries}

        all_dates = sorted(set(spy_by_date) | set(sent_by_date) | set(tide_by_date))
        for dt in all_dates:
            if start <= dt <= end:
                spy = spy_by_date.get(dt, {})
                sent = sent_by_date.get(dt, {})
                tide = tide_by_date.get(dt, {})

                rows.append({
                    "timestamp": pd.Timestamp(f"{dt}T20:00:00", tz="UTC"),
                    "spy_cum_delta": float(spy.get("cum_delta", 0) if isinstance(spy, dict) else 0),
                    "spy_signal": spy.get("signal", "NEUTRAL") if isinstance(spy, dict) else "NEUTRAL",
                    "spy_scale_factor": float(spy.get("position_scale_factor", 1.0) if isinstance(spy, dict) else 1.0),
                    "sentiment_score": int(sent.get("sentiment_score", 0) if isinstance(sent, dict) else 0),
                    "sentiment_regime": sent.get("regime", "NEUTRAL") if isinstance(sent, dict) else "NEUTRAL",
                    "tide_direction": tide.get("tide_direction", "NEUTRAL") if isinstance(tide, dict) else "NEUTRAL",
                    "tide_accelerating": bool(tide.get("is_accelerating", False) if isinstance(tide, dict) else False),
                })

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("timestamp").sort_index()

    def harmonize_macro(self, start: str, end: str) -> pd.DataFrame:
        """
        Combine VIX + yields + breadth into unified macro features.
        Output: vault/features/_MARKET/macro_1d.parquet
        """
        vix_df = self.store.load_macro("vix")
        yields_df = self.store.load_macro("yields")

        if vix_df is None and yields_df is None:
            return pd.DataFrame()

        frames = []
        if vix_df is not None and not vix_df.empty:
            vix_df = vix_df.rename(columns={"close": "vix_close"})
            vix_df["vix_regime"] = vix_df["vix_close"].apply(
                lambda v: "FEAR" if v > 25 else ("COMPLACENT" if v < 15 else "NORMAL")
            )
            frames.append(vix_df[["vix_close", "vix_regime"]])

        if yields_df is not None and not yields_df.empty:
            if "yield_10y" in yields_df.columns and "yield_3m" in yields_df.columns:
                yields_df["yield_spread"] = yields_df["yield_10y"] - yields_df["yield_3m"]
                yields_df["yield_curve_inverted"] = yields_df["yield_spread"] < 0
                frames.append(yields_df[["yield_10y", "yield_3m", "yield_spread", "yield_curve_inverted"]])

        if not frames:
            return pd.DataFrame()

        result = pd.concat(frames, axis=1).sort_index()
        # Filter date range
        if start:
            result = result[result.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            result = result[result.index <= pd.Timestamp(end, tz="UTC")]
        return result

    def build_ml_dataset(
        self, ticker: str, tf: str = "1d",
        start: Optional[str] = None, end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Build complete ML dataset by joining OHLCV + flow + macro + fundamentals.
        This is the primary input for StrategyCalibrator.
        """
        # 1. Base: OHLCV
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
        ohlcv = self.store.load_bars(ticker, tf, start_date, end_date)
        if ohlcv.empty:
            logger.warning(f"DataHarmonizer: No OHLCV data for {ticker}/{tf}")
            return pd.DataFrame()

        # 2. Flow features (per-ticker)
        flow = self.store.load_features(ticker, "flow_1d")
        if flow is not None and not flow.empty:
            if tf != "1d":
                flow = flow.resample(tf).ffill()
            ohlcv = ohlcv.join(flow, how="left")

        # 3. Market-wide flow
        market_flow = self.store.load_features("_MARKET", "flow_1d")
        if market_flow is not None and not market_flow.empty:
            if tf != "1d":
                market_flow = market_flow.resample(tf).ffill()
            ohlcv = ohlcv.join(market_flow, how="left", rsuffix="_mkt")

        # 4. Macro
        macro = self.store.load_features("_MARKET", "macro_1d")
        if macro is not None and not macro.empty:
            if tf != "1d":
                macro = macro.resample(tf).ffill()
            ohlcv = ohlcv.join(macro, how="left")

        # 5. Fundamental snapshot (static, broadcast)
        fund_path = self.store.root / "features" / ticker.upper() / "fundamental_latest.json"
        if fund_path.exists():
            import json
            with open(fund_path) as f:
                fund = json.load(f)
            for k, v in fund.items():
                if k != "vault_date":
                    ohlcv[f"fund_{k}"] = v

        # 6. Forward-fill gaps
        ohlcv.ffill(inplace=True)

        logger.info(
            f"DataHarmonizer: built dataset for {ticker}/{tf} — "
            f"{len(ohlcv)} rows, {len(ohlcv.columns)} columns"
        )
        return ohlcv
