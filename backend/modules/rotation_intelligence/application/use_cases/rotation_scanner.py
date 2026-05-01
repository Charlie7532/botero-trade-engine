"""
Rotation Scanner — Weinstein & Pring Analysis Engine.

Processes raw ETF price/volume data into rotation signals using:
- Stan Weinstein's Stage Analysis (30-week MA, RS, volume)
- Martin Pring's Intermarket Cycle (bonds → stocks → commodities)

Produces a RotationSnapshot that feeds directly into the CIO's synthesize_mandate().
"""
import logging
from datetime import datetime, UTC

from backend.modules.rotation_intelligence.domain.entities.rotation_snapshot import (
    RotationSignal,
    RotationSnapshot,
)
from backend.modules.rotation_intelligence.domain.ports.rotation_data_port import (
    RotationDataPort,
)

logger = logging.getLogger(__name__)

# ── ETF Universe ─────────────────────────────────────

SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Healthcare", "XLI": "Industrials", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLC": "Communication Services", "XLB": "Materials",
}

INTERNATIONAL_ETFS = {
    "EFA": "Developed ex-US", "EEM": "Emerging Markets", "FXI": "China",
    "EWZ": "Brazil", "EWJ": "Japan", "INDA": "India",
    "VGK": "Europe", "EWG": "Germany",
}

ASSET_CLASS_ETFS = {
    "SPY": "US Equities", "TLT": "Long Treasuries", "GLD": "Gold",
    "USO": "Oil", "UUP": "US Dollar", "HYG": "High Yield Bonds",
    "LQD": "Investment Grade Bonds",
}

BENCHMARK = "SPY"


class RotationScanner:
    """
    Scans ETF universe and produces a RotationSnapshot for the CIO.

    Uses Weinstein's Stage Analysis and Pring's Intermarket framework.
    """

    def __init__(self, data_port: RotationDataPort):
        self._port = data_port

    def scan(self) -> RotationSnapshot:
        """Run a complete rotation scan across all 3 dimensions."""
        all_symbols = (
            list(SECTOR_ETFS.keys())
            + list(INTERNATIONAL_ETFS.keys())
            + list(ASSET_CLASS_ETFS.keys())
        )
        # Ensure benchmark is included
        if BENCHMARK not in all_symbols:
            all_symbols.append(BENCHMARK)

        raw = self._port.fetch_etf_data(all_symbols, period="6mo")

        if not raw or BENCHMARK not in raw:
            logger.warning("RotationScanner: No data or missing benchmark.")
            return RotationSnapshot(
                date=datetime.now(UTC).strftime("%Y-%m-%d"),
                dominant_rotation="NO_DATA",
            )

        benchmark_data = raw[BENCHMARK]
        signals = []

        for etf, data in raw.items():
            if etf == BENCHMARK:
                continue
            dimension, name = self._classify_etf(etf)
            if not dimension:
                continue

            signal = self._analyze_etf(etf, name, dimension, data, benchmark_data)
            signals.append(signal)

        # Build flow dicts
        sector_flows = {}
        intl_flows = {}
        asset_flows = {}

        for s in signals:
            if s.dimension == "sector":
                sector_flows[s.name] = s.rs_score
            elif s.dimension == "international":
                intl_flows[s.name] = s.rs_score
            elif s.dimension == "asset_class":
                asset_flows[s.name] = s.rs_score

        cycle_phase = self._detect_cycle_phase(asset_flows)
        dominant = self._detect_dominant_rotation(sector_flows, intl_flows)

        snapshot = RotationSnapshot(
            date=datetime.now(UTC).strftime("%Y-%m-%d"),
            sector_flows=sector_flows,
            international_flows=intl_flows,
            asset_class_flows=asset_flows,
            signals=signals,
            dominant_rotation=dominant,
            cycle_phase=cycle_phase,
        )

        logger.info(
            f"RotationScanner: {cycle_phase} | {dominant} | "
            f"{len(sector_flows)} sectors, {len(intl_flows)} intl, {len(asset_flows)} assets"
        )
        return snapshot

    # ── Private Methods ──────────────────────────────

    def _classify_etf(self, etf: str) -> tuple[str, str]:
        """Return (dimension, name) for a given ETF."""
        if etf in SECTOR_ETFS:
            return "sector", SECTOR_ETFS[etf]
        if etf in INTERNATIONAL_ETFS:
            return "international", INTERNATIONAL_ETFS[etf]
        if etf in ASSET_CLASS_ETFS:
            return "asset_class", ASSET_CLASS_ETFS[etf]
        return "", ""

    def _analyze_etf(
        self,
        etf: str,
        name: str,
        dimension: str,
        data: dict,
        benchmark: dict,
    ) -> RotationSignal:
        """Analyze a single ETF using Weinstein's framework."""
        prices = data.get("prices", [])
        volumes = data.get("volumes", [])
        bench_prices = benchmark.get("prices", [])

        mom_20d = self._momentum(prices, 20)
        mom_60d = self._momentum(prices, 60)
        vol_ratio = self._volume_ratio(volumes, 20)
        rs = self._relative_strength(prices, bench_prices, 20)
        stage = self._weinstein_stage(prices, rs)

        return RotationSignal(
            etf=etf,
            name=name,
            dimension=dimension,
            rs_score=max(-1.0, min(1.0, rs)),
            momentum_20d=mom_20d,
            momentum_60d=mom_60d,
            volume_ratio=vol_ratio,
            stage=stage,
        )

    @staticmethod
    def _momentum(prices: list[float], window: int) -> float:
        """Simple return over window."""
        if len(prices) < window + 1 or prices[-window - 1] == 0:
            return 0.0
        return (prices[-1] / prices[-window - 1]) - 1.0

    @staticmethod
    def _volume_ratio(volumes: list[float], window: int) -> float:
        """Current volume vs average over window."""
        if len(volumes) < window + 1:
            return 1.0
        avg = sum(volumes[-window - 1:-1]) / max(window, 1)
        return volumes[-1] / max(avg, 1.0)

    @staticmethod
    def _relative_strength(
        prices: list[float], benchmark: list[float], window: int
    ) -> float:
        """RS = (ETF return / Benchmark return) - 1, normalized roughly to [-1, 1]."""
        if len(prices) < window + 1 or len(benchmark) < window + 1:
            return 0.0
        etf_ret = (prices[-1] / max(prices[-window - 1], 0.01)) - 1.0
        bench_ret = (benchmark[-1] / max(benchmark[-window - 1], 0.01)) - 1.0
        # Avoid division by zero; if benchmark flat, raw RS is just etf return
        if abs(bench_ret) < 0.001:
            return max(-1.0, min(1.0, etf_ret * 10))
        rs_raw = (etf_ret / bench_ret) - 1.0
        # Clamp to [-1, 1] with scaling
        return max(-1.0, min(1.0, rs_raw * 5))

    @staticmethod
    def _weinstein_stage(prices: list[float], rs: float) -> int:
        """
        Simplified Weinstein Stage Analysis.

        Uses 150-day (≈30-week) MA and relative strength trend.
        """
        if len(prices) < 150:
            return 0  # Not enough data

        ma_150 = sum(prices[-150:]) / 150
        current = prices[-1]
        ma_slope = (sum(prices[-20:]) / 20) - (sum(prices[-40:-20]) / 20)

        if current > ma_150 and ma_slope > 0 and rs > 0.1:
            return 2  # Advancing
        elif current > ma_150 and ma_slope <= 0:
            return 3  # Topping
        elif current < ma_150 and ma_slope < 0:
            return 4  # Declining
        else:
            return 1  # Basing

    @staticmethod
    def _detect_cycle_phase(asset_flows: dict[str, float]) -> str:
        """
        Detect Pring's intermarket cycle phase.

        Uses bonds (TLT), equities (implicit benchmark), and commodities (USO/GLD).
        """
        bonds = asset_flows.get("Long Treasuries", 0)
        gold = asset_flows.get("Gold", 0)
        oil = asset_flows.get("Oil", 0)
        hyg = asset_flows.get("High Yield Bonds", 0)

        if bonds > 0.3 and oil < -0.2:
            return "EARLY_EXPANSION"
        elif bonds < -0.2 and oil > 0.3:
            return "LATE_EXPANSION"
        elif bonds < -0.3 and hyg < -0.3:
            return "CONTRACTION"
        elif bonds > 0.3 and gold > 0.3:
            return "LATE_CONTRACTION"
        else:
            return "MID_CYCLE"

    @staticmethod
    def _detect_dominant_rotation(
        sector_flows: dict[str, float],
        intl_flows: dict[str, float],
    ) -> str:
        """Identify the dominant rotation theme."""
        if not sector_flows:
            return "NO_DATA"

        cyclicals = ["Technology", "Financials", "Energy", "Industrials",
                     "Consumer Discretionary", "Materials"]
        defensives = ["Healthcare", "Consumer Staples", "Utilities"]

        cyc_avg = _avg_flow(sector_flows, cyclicals)
        def_avg = _avg_flow(sector_flows, defensives)

        em_flow = intl_flows.get("Emerging Markets", 0)

        if cyc_avg > 0.3 and def_avg < 0:
            return "RISK_ON_CYCLICALS"
        elif def_avg > 0.3 and cyc_avg < 0:
            return "DEFENSIVE_ROTATION"
        elif em_flow > 0.4:
            return "EM_INFLOW"
        elif em_flow < -0.4:
            return "EM_OUTFLOW"
        else:
            return "NEUTRAL"


def _avg_flow(flows: dict[str, float], names: list[str]) -> float:
    """Average flow score for a list of sector names."""
    vals = [flows[n] for n in names if n in flows]
    return sum(vals) / max(len(vals), 1)
