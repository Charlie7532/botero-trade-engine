"""
Causal Verification Provider — Vault Data Provider
====================================================
Computes CausalVerificationSnapshot from Vault data and persists it as:
  1. mcp_snapshot("causal/verdict", ticker)
  2. RegimeStatePort state transitions ("causal:weinstein:{ticker}" & "causal:verdict:{ticker}")

All inputs read from Vault — zero external API calls in the domain layer.
Follows Rules 13, 15, 16, 17, 18.
"""
import logging
from datetime import datetime, date, timedelta, UTC
from typing import Dict, Any

from backend.daemons.vault_providers import register_provider, VaultProvider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.postgres_regime_state_adapter import PostgresRegimeStateAdapter
from backend.modules.causal_investigation import (
    CausalInputDTO,
    evaluate_causal_conviction,
)

logger = logging.getLogger(__name__)


class CausalVerificationProvider:
    """Vault provider for Causal Investigation Engine snapshot."""

    name = "causal_verification"
    categories = ["causal_verification", "causal"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Runs full update across core sector ETFs and SPY."""
        sectors = ["XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLRE", "XLC", "XLB", "SPY"]
        count = 0
        for sec in sectors:
            res = self.run_ticker(store, sec)
            if res.get("status") == "ok":
                count += 1
        return {"status": "ok", "evaluated_count": count}

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """Runs causal evaluation for a single ticker/sector."""
        if _already_vaulted_today(store, "causal/verdict", ticker):
            logger.info(f"🔬 Causal Verdict for {ticker} already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        try:
            start_date = date.today() - timedelta(days=220)

            # ── 1. Load OHLCV price history ──
            bars = store.load_bars(ticker, "1d", start=start_date)
            if bars is None or len(bars) < 150:
                return {"status": "skipped", "reason": "insufficient_ohlcv"}

            close_col = "Close" if "Close" in bars.columns else "close"
            price_history = bars[close_col].tolist()

            # ── 2. Load Unusual Whales flow ──
            uw_alerts = store.load_mcp_latest("uw/flow_alerts", ticker)
            uw_net_prem = 0.0
            uw_sweeps = 0
            if isinstance(uw_alerts, dict):
                uw_net_prem = float(uw_alerts.get("net_premium", 0.0))
                uw_sweeps = int(uw_alerts.get("n_sweeps", 0))

            # ── 3. Load FRED macro snapshot ──
            fred_snap = store.load_mcp_latest("macro/fred_real", "SUMMARY")
            if not fred_snap:
                fred_snap = store.load_mcp_latest("macro/fred", "SUMMARY")

            # ── 4. Load Insider activity ──
            insider_act = store.load_mcp_latest("fundamental/insider", ticker)

            # ── 5. Load S5/SV5 indicators ──
            s5th_bars = store.load_bars(f"S5_{ticker}_TH", "1d", start=start_date)
            s5fi_bars = store.load_bars(f"S5_{ticker}_FI", "1d", start=start_date)
            s5tw_bars = store.load_bars(f"S5_{ticker}_TW", "1d", start=start_date)
            sv5tw_bars = store.load_bars(f"SV5_{ticker}_TW", "1d", start=start_date)

            s5_th = self._last_bar_val(s5th_bars, 50.0)
            s5_fi = self._last_bar_val(s5fi_bars, 50.0)
            s5_tw = self._last_bar_val(s5tw_bars, 50.0)
            sv5_tw = self._last_bar_val(sv5tw_bars, 50.0)
            vol_div = sv5_tw - s5_fi

            # ── 6. Load News Sentiment ──
            news_snap = store.load_mcp_latest("news/sentiment", ticker)
            news_sent = 0.0
            if isinstance(news_snap, dict):
                news_sent = float(news_snap.get("sentiment_score", 0.0))

            # ── 7. Build DTO & Evaluate Use Case ──
            input_dto = CausalInputDTO(
                symbol=ticker,
                price_history=price_history,
                rs_score=0.0,
                uw_flow_alerts=uw_alerts if isinstance(uw_alerts, list) else None,
                uw_net_premium=uw_net_prem,
                uw_sweep_count=uw_sweeps,
                fred_macro_snapshot=fred_snap,
                insider_activity=insider_act,
                s5_th=s5_th,
                s5_fi=s5_fi,
                s5_tw=s5_tw,
                sv5_tw=sv5_tw,
                vol_div=vol_div,
                news_sentiment_score=news_sent,
            )

            snapshot = evaluate_causal_conviction(input_dto)

            # ── 8. Persist Snapshot to Vault (mcp_snapshot) ──
            store.save_mcp_snapshot("causal/verdict", ticker, snapshot.to_dict())

            # ── 9. Persist Regime Transitions (RegimeStatePort) ──
            regime_port = PostgresRegimeStateAdapter(store)
            regime_port.commit_transition(
                key=f"causal:weinstein:{ticker}",
                next_state=snapshot.structural_veto.stage.label,
                trigger=f"MA150={snapshot.structural_veto.ma_150:.2f}",
                metadata={"price": snapshot.structural_veto.current_price},
            )
            regime_port.commit_transition(
                key=f"causal:verdict:{ticker}",
                next_state=snapshot.decision.value,
                trigger=f"CausalScore={snapshot.counter_veto.causal_score:.2f}",
                metadata={"sizing_multiplier": snapshot.sizing_multiplier},
            )

            logger.info(f"🔬 Causal Verification for {ticker}: {snapshot.decision.value} (Score={snapshot.counter_veto.causal_score:.2f})")
            return {"status": "ok", "ticker": ticker, "decision": snapshot.decision.value}

        except Exception as e:
            logger.error(f"❌ CausalVerificationProvider error for {ticker}: {e}", exc_info=True)
            return {"status": "error", "reason": str(e)}

    @staticmethod
    def _last_bar_val(df, default: float) -> float:
        if df is None or df.empty:
            return default
        col = "Close" if "Close" in df.columns else ("close" if "close" in df.columns else df.columns[-1])
        return float(df[col].iloc[-1])


provider = CausalVerificationProvider()
register_provider(provider)
