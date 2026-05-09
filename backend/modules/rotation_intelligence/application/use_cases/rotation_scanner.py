"""
Rotation Scanner — Unified Rotation Intelligence Engine.

Consolidates three previously-disconnected legacy systems into a single motor:
1. Weinstein Stage Analysis + Pring Intermarket Cycle (original RotationScanner)
2. Wyckoff Flow Classification + Kalman Volume Dynamics (from SectorFlowEngine)
3. Capitulation Detection + Fear & Greed (from MarketBreadthProvider)
4. Cap-Weight vs Equal-Weight Breadth Divergence (NEW)

Produces a RotationSnapshot that feeds the CIO, SectorRanker, EntryHub,
and Risk Manager.
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
from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    INTERNATIONAL_ETFS,
    ASSET_CLASS_ETFS,
    EQUAL_WEIGHT_PROXIES,
    BENCHMARK,
)

logger = logging.getLogger(__name__)


class RotationScanner:
    """
    Unified rotation engine — single source of truth for all
    sector, international, and asset-class rotation intelligence.
    """

    def __init__(self, data_port: RotationDataPort):
        self._port = data_port
        # Kalman state per ETF (persistent across scans)
        self._kalman_state: dict[str, dict] = {}

    def scan(self) -> RotationSnapshot:
        """Run a complete rotation scan across all 3 dimensions."""
        all_symbols = (
            list(SECTOR_ETFS.keys())
            + list(INTERNATIONAL_ETFS.keys())
            + list(ASSET_CLASS_ETFS.keys())
        )
        if BENCHMARK not in all_symbols:
            all_symbols.append(BENCHMARK)

        # Add equal-weight proxies for breadth divergence
        ew_symbols = list(EQUAL_WEIGHT_PROXIES.values())
        fetch_symbols = list(set(all_symbols + ew_symbols))

        raw = self._port.fetch_etf_data(fetch_symbols, period="6mo")

        if not raw or BENCHMARK not in raw:
            logger.warning("RotationScanner: No data or missing benchmark.")
            return RotationSnapshot(
                date=datetime.now(UTC).strftime("%Y-%m-%d"),
                dominant_rotation="NO_DATA",
            )

        benchmark_data = raw[BENCHMARK]
        signals = []

        for etf in all_symbols:
            if etf == BENCHMARK:
                continue
            data = raw.get(etf)
            if not data:
                continue
            dimension, name = self._classify_etf(etf)
            if not dimension:
                continue

            signal = self._analyze_etf(etf, name, dimension, data, benchmark_data, raw)
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

        # ── Market-level breadth (RSP vs SPY) ──────────────
        breadth_pct = self._compute_market_breadth(raw)

        # ── Capitulation detection ─────────────────────────
        vix = self._estimate_vix(raw)
        cap_level, cap_action = self._detect_capitulation(vix, breadth_pct)

        # ── Fear & Greed (best-effort, non-blocking) ───────
        fg_score = self._fetch_fear_greed()

        snapshot = RotationSnapshot(
            date=datetime.now(UTC).strftime("%Y-%m-%d"),
            sector_flows=sector_flows,
            international_flows=intl_flows,
            asset_class_flows=asset_flows,
            signals=signals,
            dominant_rotation=dominant,
            cycle_phase=cycle_phase,
            capitulation_level=cap_level,
            capitulation_action=cap_action,
            fear_greed_score=fg_score,
            market_breadth_pct=breadth_pct,
        )

        logger.info(
            f"RotationScanner: {cycle_phase} | {dominant} | "
            f"{len(sector_flows)} sectors, {len(intl_flows)} intl, {len(asset_flows)} assets | "
            f"Breadth={breadth_pct:.0f}% Cap_L{cap_level} F&G={fg_score:.0f}"
        )
        return snapshot

    # ══════════════════════════════════════════════════════════
    # WEINSTEIN STAGE ANALYSIS
    # ══════════════════════════════════════════════════════════

    def _analyze_etf(
        self,
        etf: str,
        name: str,
        dimension: str,
        data: dict,
        benchmark: dict,
        all_raw: dict,
    ) -> RotationSignal:
        """Analyze a single ETF — Weinstein + Wyckoff + Breadth Divergence."""
        prices = data.get("prices", [])
        volumes = data.get("volumes", [])
        bench_prices = benchmark.get("prices", [])

        mom_20d = self._momentum(prices, 20)
        mom_60d = self._momentum(prices, 60)
        vol_ratio = self._volume_ratio(volumes, 20)
        rs = self._relative_strength(prices, bench_prices, 20)
        stage = self._weinstein_stage(prices, rs)

        # ── Wyckoff Flow Classification (absorbed from SectorFlowEngine) ──
        flow_signal = self._classify_flow_signal(vol_ratio, mom_20d * 100)

        # ── Kalman Volume Dynamics ─────────────────────────
        k_vel, k_acc = self._kalman_update(etf, vol_ratio)

        # ── Cap-Weight vs Equal-Weight Divergence ──────────
        cap_ret, ew_ret, divergence = self._breadth_divergence(
            etf, prices, all_raw
        )

        return RotationSignal(
            etf=etf,
            name=name,
            dimension=dimension,
            rs_score=max(-1.0, min(1.0, rs)),
            momentum_20d=mom_20d,
            momentum_60d=mom_60d,
            volume_ratio=vol_ratio,
            stage=stage,
            flow_signal=flow_signal,
            kalman_velocity=k_vel,
            kalman_acceleration=k_acc,
            cap_weighted_return=cap_ret,
            equal_weighted_return=ew_ret,
            breadth_divergence=divergence,
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
        if abs(bench_ret) < 0.001:
            return max(-1.0, min(1.0, etf_ret * 10))
        rs_raw = (etf_ret / bench_ret) - 1.0
        return max(-1.0, min(1.0, rs_raw * 5))

    @staticmethod
    def _weinstein_stage(prices: list[float], rs: float) -> int:
        """
        Simplified Weinstein Stage Analysis.
        Uses 150-day (≈30-week) MA and relative strength trend.
        """
        if len(prices) < 150:
            return 0

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

    # ══════════════════════════════════════════════════════════
    # PRING INTERMARKET CYCLE
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _detect_cycle_phase(asset_flows: dict[str, float]) -> str:
        """Detect Pring's intermarket cycle phase."""
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

    # ══════════════════════════════════════════════════════════
    # WYCKOFF FLOW CLASSIFICATION (absorbed from SectorFlowEngine)
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _classify_flow_signal(rel_vol: float, change_pct: float) -> str:
        """
        Classify institutional flow signal.

        Simplified Wyckoff matrix:
          RVol ≥ 1.5 + Change > 0   → ACCUMULATION_ACTIVE
          RVol ≥ 1.5 + Change < 0   → DISTRIBUTION
          RVol ≥ 1.5 + Change ≈ 0   → HIGH_VOL_CONSOLIDATION
          RVol < 0.8 + Change > 0   → WEAK_RALLY
          RVol < 0.8 + Change < 0   → QUIET_DECLINE
          Otherwise                  → CONSOLIDATION
        """
        if rel_vol >= 1.5 and change_pct > 0.3:
            return "ACCUMULATION_ACTIVE"
        elif rel_vol >= 1.5 and change_pct < -0.3:
            return "DISTRIBUTION"
        elif rel_vol >= 1.5 and abs(change_pct) <= 0.3:
            return "HIGH_VOL_CONSOLIDATION"
        elif rel_vol < 0.8 and change_pct > 0.3:
            return "WEAK_RALLY"
        elif rel_vol < 0.8 and change_pct < -0.3:
            return "QUIET_DECLINE"
        else:
            return "CONSOLIDATION"

    # ══════════════════════════════════════════════════════════
    # KALMAN VOLUME DYNAMICS (absorbed from SectorFlowEngine)
    # ══════════════════════════════════════════════════════════

    def _kalman_update(self, etf: str, rel_vol: float) -> tuple[float, float]:
        """
        Simple Kalman-inspired volume tracker.

        Tracks velocity (rate of change) and acceleration (change of velocity)
        of relative volume for each ETF. Detects institutional activity
        BEFORE the volume fully materializes.

        Returns: (velocity, acceleration)
        """
        state = self._kalman_state.get(etf)
        if state is None:
            self._kalman_state[etf] = {
                "prev_vol": rel_vol,
                "velocity": 0.0,
                "acceleration": 0.0,
            }
            return 0.0, 0.0

        alpha = 0.3  # Smoothing factor
        new_velocity = alpha * (rel_vol - state["prev_vol"]) + (1 - alpha) * state["velocity"]
        new_accel = alpha * (new_velocity - state["velocity"]) + (1 - alpha) * state["acceleration"]

        self._kalman_state[etf] = {
            "prev_vol": rel_vol,
            "velocity": round(new_velocity, 4),
            "acceleration": round(new_accel, 4),
        }
        return round(new_velocity, 4), round(new_accel, 4)

    # ══════════════════════════════════════════════════════════
    # CAP-WEIGHT vs EQUAL-WEIGHT DIVERGENCE
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _breadth_divergence(
        etf: str, prices: list[float], all_raw: dict
    ) -> tuple[float, float, float]:
        """
        Calculate divergence between cap-weighted ETF return and
        equal-weighted proxy return over 20 days.

        Positive divergence = broad-based strength (all stocks participating)
        Negative divergence = narrow market (only mega-caps holding up ETF)

        Returns: (cap_return_20d, ew_return_20d, divergence)
        """
        cap_ret = 0.0
        if len(prices) >= 21 and prices[-21] > 0:
            cap_ret = (prices[-1] / prices[-21]) - 1.0

        ew_proxy = EQUAL_WEIGHT_PROXIES.get(etf)
        if not ew_proxy or ew_proxy not in all_raw:
            return round(cap_ret, 4), 0.0, 0.0

        ew_prices = all_raw[ew_proxy].get("prices", [])
        ew_ret = 0.0
        if len(ew_prices) >= 21 and ew_prices[-21] > 0:
            ew_ret = (ew_prices[-1] / ew_prices[-21]) - 1.0

        divergence = ew_ret - cap_ret
        return round(cap_ret, 4), round(ew_ret, 4), round(divergence, 4)

    # ══════════════════════════════════════════════════════════
    # CAPITULATION DETECTION (absorbed from MarketBreadthProvider)
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _detect_capitulation(vix: float, breadth_pct: float) -> tuple[int, str]:
        """
        Detect capitulation zones using VIX + breadth.

        Empirical evidence (SPX 2020-2026):
          VIX 30-40           → Ret 60d +5.09%,  Win ~75%
          VIX > 40            → Ret 60d +21.68%, Win ~80%
          VIX>25 + breadth<30 → Ret 60d +4.92%,  Win 75.6%

        Returns: (level 0-4, action)
        """
        if vix > 40 and breadth_pct < 20:
            return 4, "max_allocation_long"
        elif vix > 35 and breadth_pct < 25:
            return 3, "aggressive_long"
        elif vix > 30 and breadth_pct < 30:
            return 2, "start_accumulating"
        elif vix > 25 or breadth_pct < 30:
            return 1, "reduce_risk_wait"
        else:
            return 0, "operate_normal"

    # ══════════════════════════════════════════════════════════
    # MARKET BREADTH (RSP vs SPY as proxy for S5TH)
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _compute_market_breadth(raw: dict) -> float:
        """
        Compute breadth proxy using RSP (Equal-Weight S&P 500) vs SPY.

        If RSP is above its 200-day MA → broad participation → ~65%
        If RSP is below → narrow market → ~35%
        Refined: use RSP/SPY ratio trend for gradation.
        """
        rsp_data = raw.get("RSP")
        spy_data = raw.get("SPY")
        if not rsp_data or not spy_data:
            return 50.0

        rsp_prices = rsp_data.get("prices", [])
        spy_prices = spy_data.get("prices", [])

        if len(rsp_prices) < 50 or len(spy_prices) < 50:
            return 50.0

        # RSP/SPY ratio
        rsp_current = rsp_prices[-1]
        spy_current = spy_prices[-1]
        if spy_current <= 0:
            return 50.0

        ratio_now = rsp_current / spy_current

        # 50-day average of the ratio
        ratios = [
            rsp_prices[i] / spy_prices[i]
            for i in range(-50, 0)
            if spy_prices[i] > 0
        ]
        if not ratios:
            return 50.0
        ratio_avg = sum(ratios) / len(ratios)

        # If ratio rising → broad participation
        if ratio_now > ratio_avg * 1.01:
            return 70.0
        elif ratio_now > ratio_avg * 0.99:
            return 55.0
        else:
            return 35.0

    # ══════════════════════════════════════════════════════════
    # VIX ESTIMATION & FEAR/GREED
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _estimate_vix(raw: dict) -> float:
        """
        Estimate VIX from SPY volatility if VIX data not directly available.
        Uses 20-day realized volatility of SPY as proxy.
        """
        spy_data = raw.get("SPY")
        if not spy_data:
            return 20.0

        prices = spy_data.get("prices", [])
        if len(prices) < 21:
            return 20.0

        # 20-day realized volatility (annualized)
        returns = [
            (prices[i] / prices[i - 1]) - 1.0
            for i in range(-20, 0)
            if prices[i - 1] > 0
        ]
        if not returns:
            return 20.0

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        daily_vol = variance ** 0.5
        annualized = daily_vol * (252 ** 0.5) * 100

        return round(annualized, 1)

    @staticmethod
    def _fetch_fear_greed() -> float:
        """
        Read CNN Fear & Greed Index from the Neon Vault.
        Captured daily by the Vault Daemon's vault_fear_greed() task.
        Returns 50.0 (neutral) if not available.
        """
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            snapshot = store.load_mcp_latest("macro/fear_greed", "MARKET")
            store.close()
            if snapshot and isinstance(snapshot, dict):
                score = snapshot.get("score", 50.0)
                return round(float(score), 1)
        except Exception:
            pass
        return 50.0

    # ══════════════════════════════════════════════════════════
    # ETF CLASSIFICATION
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _classify_etf(etf: str) -> tuple[str, str]:
        """Return (dimension, name) for a given ETF."""
        if etf in SECTOR_ETFS:
            return "sector", SECTOR_ETFS[etf]
        if etf in INTERNATIONAL_ETFS:
            return "international", INTERNATIONAL_ETFS[etf]
        if etf in ASSET_CLASS_ETFS:
            return "asset_class", ASSET_CLASS_ETFS[etf]
        return "", ""


def _avg_flow(flows: dict[str, float], names: list[str]) -> float:
    """Average flow score for a list of sector names."""
    vals = [flows[n] for n in names if n in flows]
    return sum(vals) / max(len(vals), 1)
