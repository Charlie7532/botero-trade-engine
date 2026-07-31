"""
SV5 Turbulence Provider — SV5_TURBULENCE
=========================================
Derived indicator: rolling 10-day standard deviation of daily SV5TW changes.
Measures institutional volume breadth turbulence — how erratically institutional
participation is changing day-to-day.

V40: Empirically validated as VIX contingency in V36 redirect.
     SV5_TURBULENCE > 10 recovers 96.9% of VIX's protective value.
     SV5_TURBULENCE > P90 + S5StdVIX < P75 = +1.77% fwd 20d, 73.3% WR (accumulation signal).

EXECUTION ORDER: MUST run AFTER VolumeBreadthProvider (needs SV5TW history).
Source: Derived from SV5TW bars in Vault (not external API).
"""
import logging
import math
from datetime import datetime, UTC

from backend.daemons.vault_providers import register_provider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

# Rolling window for std computation (calibrated on 6,703 days 2000-2026)
_WINDOW = 10


class SV5TurbulenceProvider:
    """Vault provider for SV5_TURBULENCE (institutional volume breadth turbulence)."""

    name = "sv5_turbulence"
    categories = ["sv5_turbulence"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Compute SV5_TURBULENCE from the last 11 SV5TW daily bars."""
        if _already_vaulted_today(store, "derived/sv5_turbulence", "MARKET"):
            logger.info("📊 SV5_TURBULENCE already vaulted today — skipping")
            return {"status": "skipped", "reason": "already_today"}

        return self._compute_sv5_turbulence(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """SV5_TURBULENCE is market-wide — falls back to run_full."""
        return self.run_full(store)

    def _compute_sv5_turbulence(self, store: TimescaleDataStore) -> dict:
        """Core SV5_TURBULENCE computation.

        SV5_TURBULENCE = std(Δ_SV5TW, window=10)
        where Δ_SV5TW = SV5TW(t) - SV5TW(t-1), daily change.
        """
        try:
            from datetime import timedelta

            # Load last 15 days of SV5TW bars (need 11 for 10 diffs + margin)
            start_date = (datetime.now(UTC) - timedelta(days=20)).date()
            bars = store.load_bars("SV5TW", "1d", start=start_date)

            if bars is None or len(bars) < _WINDOW + 1:
                logger.warning(
                    f"SV5_TURBULENCE: insufficient SV5TW history "
                    f"({len(bars) if bars is not None else 0} bars, need {_WINDOW + 1})"
                )
                return {"status": "error", "reason": "insufficient_history"}

            # time is the index; sort and take close values
            bars = bars.sort_index()
            closes = bars["close"].values[-(_WINDOW + 1):]

            # Compute daily diffs
            diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

            if len(diffs) < 2:
                return {"status": "error", "reason": "insufficient_diffs"}

            # Sample standard deviation
            n = len(diffs)
            mean = sum(diffs) / n
            variance = sum((d - mean) ** 2 for d in diffs) / (n - 1)
            sv5_turbulence = math.sqrt(variance)

            # Persist as pseudo-OHLCV (Rule 14: single-value → o=h=l=c=value, volume=0)
            now = datetime.now(UTC)
            store.upsert_ohlcv_bar(
                ticker="SV5_TURBULENCE",
                timeframe="1d",
                time=now,
                open=sv5_turbulence,
                high=sv5_turbulence,
                low=sv5_turbulence,
                close=sv5_turbulence,
                volume=0,
            )

            # Ensure ticker metadata exists (idempotent upsert)
            store.upsert_ticker_metadata(
                ticker="SV5_TURBULENCE",
                sector="Volatility",
                industry="INDICATOR",
                market_cap_bucket=None,
            )

            logger.info(
                f"📊 SV5_TURBULENCE vault: {sv5_turbulence:.2f} "
                f"(window={_WINDOW}d, last SV5TW={closes[-1]:.1f}%)"
            )

            return {
                "status": "success",
                "sv5_turbulence": sv5_turbulence,
                "bars_computed": 1,
            }

        except Exception as e:
            logger.warning(f"SV5_TURBULENCE vault failed (non-critical): {e}")
            return {"status": "error", "error": str(e)}


register_provider(SV5TurbulenceProvider())
