"""
GuruFocus Intelligence Adapter
================================
Bridges GuruFocus MCP tools (55 capabilities) to the Botero Trade engine.

This adapter translates MCP tool responses into consumption-ready data
structures for UniverseFilter, AlphaScanner, RiskGuardian, and TickerQualifier.

MCP Tools Consumed:
- get_qgarp_analysis → QGARP scoring (0-100)
- get_stock_risk_analysis → 5D risk matrix
- get_stock_keyratios → Piotroski, Altman Z, ROIC, margins
- get_insider_cluster_buys, get_insider_ceo_buys, get_insider_cfo_buys → Insider conviction
- get_stock_gurus, get_guru_realtime_picks → Guru tracking
- get_economic_indicators, get_economic_indicator → Macro dashboard
- get_stock_analyst_estimates, get_stock_estimate_history → Analyst intelligence
- get_financial_calendar → Earnings calendar
- get_politician_transactions → Political signal
- get_etf_sector_weighting → Sector allocation
- get_stock_summary → Company fundamentals
"""
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class QGARPScorecard:
    """Quality-Growth-At-Reasonable-Price composite score."""
    ticker: str
    total_score: float = 0.0          # 0-100 composite
    quality_score: float = 0.0        # Financial quality
    growth_score: float = 0.0         # Revenue/earnings growth
    valuation_score: float = 0.0      # Price vs intrinsic value
    gf_value_discount_pct: float = 0.0  # Discount to GF Value
    piotroski_f_score: int = 0        # 0-9 financial strength
    altman_z_score: float = 0.0       # Bankruptcy risk (>2.99 safe)
    roic: float = 0.0                 # Return on invested capital
    predictability_rank: float = 0.0  # GuruFocus predictability
    raw_data: dict = field(default_factory=dict)


@dataclass
class RiskMatrix5D:
    """Five-dimension risk assessment."""
    ticker: str
    financial_risk: str = "UNKNOWN"    # RED/YELLOW/GREEN
    quality_risk: str = "UNKNOWN"
    growth_risk: str = "UNKNOWN"
    valuation_risk: str = "UNKNOWN"
    market_risk: str = "UNKNOWN"
    overall_risk: str = "UNKNOWN"
    risk_score: float = 50.0           # 0-100 (lower = riskier)
    raw_data: dict = field(default_factory=dict)


@dataclass
class InsiderConviction:
    """Insider buying conviction score."""
    ticker: str
    conviction_score: float = 0.0      # 0-100
    cluster_buys: int = 0              # Multiple insiders buying together
    ceo_buys: int = 0
    cfo_buys: int = 0
    total_insider_buys: int = 0
    net_insider_sentiment: str = "neutral"  # strong_buy, buy, neutral, sell
    recent_events: list = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


@dataclass
class GuruTracking:
    """Guru/institutional accumulation data."""
    ticker: str
    guru_count: int = 0                # Number of gurus holding
    net_buying_score: float = 0.0      # -100 to +100 (net buys vs sells)
    top_holders: list = field(default_factory=list)  # [{name, action, shares}]
    recent_picks: list = field(default_factory=list)
    accumulation: bool = False         # True if net buying
    raw_data: dict = field(default_factory=dict)


@dataclass
class MacroDashboard:
    """FRED + GuruFocus macro economic indicators."""
    gdp_growth: Optional[float] = None
    cpi_yoy: Optional[float] = None
    fed_funds_rate: Optional[float] = None
    unemployment_rate: Optional[float] = None
    treasury_10y: Optional[float] = None
    treasury_2y: Optional[float] = None
    yield_spread: Optional[float] = None
    raw_data: dict = field(default_factory=dict)


@dataclass
class AnalystIntelligence:
    """Analyst estimates and revision momentum."""
    ticker: str
    consensus: str = "hold"             # strong_buy, buy, hold, sell
    price_target_mean: float = 0.0
    price_target_upside_pct: float = 0.0
    num_analysts: int = 0
    revision_momentum: float = 0.0     # +/- estimates revised up/down
    earnings_surprise_pct: float = 0.0
    raw_data: dict = field(default_factory=dict)


class GuruFocusIntelligence:
    """
    Adapter for GuruFocus MCP tools.

    This class is designed to be called by the engine's Application layer.
    It does NOT call MCP tools directly — instead, it expects pre-fetched
    MCP responses to be passed in, maintaining Clean Architecture boundaries.

    Usage:
        The PaperTradingOrchestrator or a coordination layer fetches MCP data,
        then passes it to these methods for structured interpretation.
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.GuruFocusIntelligence")

    # ═══════════════════════════════════════════════════════════
    # SCORING & VALUATION
    # ═══════════════════════════════════════════════════════════

    def parse_qgarp_scorecard(self, ticker: str, mcp_response: dict) -> QGARPScorecard:
        """
        Parse MCP: get_qgarp_analysis response into structured scorecard.

        The QGARP score replaces the ad-hoc _compute_score() in UniverseFilter
        with an institutional-grade composite metric.
        """
        try:
            data = mcp_response if isinstance(mcp_response, dict) else {}

            scorecard = QGARPScorecard(
                ticker=ticker,
                total_score=self._safe_float(data.get("total_score", data.get("gf_score", 0))),
                quality_score=self._safe_float(data.get("quality_score", 0)),
                growth_score=self._safe_float(data.get("growth_score", 0)),
                valuation_score=self._safe_float(data.get("valuation_score", 0)),
                gf_value_discount_pct=self._safe_float(data.get("gf_value_discount", 0)),
                piotroski_f_score=int(self._safe_float(data.get("piotroski_f_score", 0))),
                altman_z_score=self._safe_float(data.get("altman_z_score", 0)),
                roic=self._safe_float(data.get("roic", 0)),
                predictability_rank=self._safe_float(data.get("predictability_rank", 0)),
                raw_data=data,
            )

            self.logger.info(
                f"QGARP {ticker}: score={scorecard.total_score:.0f}, "
                f"Piotroski={scorecard.piotroski_f_score}, "
                f"Altman Z={scorecard.altman_z_score:.2f}"
            )
            return scorecard

        except Exception as e:
            self.logger.error(f"Error parsing QGARP for {ticker}: {e}")
            return QGARPScorecard(ticker=ticker)

    def parse_risk_matrix(self, ticker: str, mcp_response: dict) -> RiskMatrix5D:
        """
        Parse MCP: get_stock_risk_analysis response into 5D risk matrix.

        Used by RiskGuardian to evaluate per-position risk, not just
        portfolio-level drawdown.
        """
        try:
            data = mcp_response if isinstance(mcp_response, dict) else {}

            matrix = RiskMatrix5D(
                ticker=ticker,
                financial_risk=str(data.get("financial_risk", "UNKNOWN")).upper(),
                quality_risk=str(data.get("quality_risk", "UNKNOWN")).upper(),
                growth_risk=str(data.get("growth_risk", "UNKNOWN")).upper(),
                valuation_risk=str(data.get("valuation_risk", "UNKNOWN")).upper(),
                market_risk=str(data.get("market_risk", "UNKNOWN")).upper(),
                overall_risk=str(data.get("overall_risk", "UNKNOWN")).upper(),
                raw_data=data,
            )

            # Calculate composite risk score (0-100, higher = safer)
            risk_map = {"GREEN": 100, "YELLOW": 50, "RED": 0, "UNKNOWN": 25}
            dimensions = [
                matrix.financial_risk, matrix.quality_risk,
                matrix.growth_risk, matrix.valuation_risk, matrix.market_risk,
            ]
            scores = [risk_map.get(d, 25) for d in dimensions]
            matrix.risk_score = sum(scores) / len(scores)

            self.logger.info(
                f"Risk5D {ticker}: score={matrix.risk_score:.0f}, "
                f"overall={matrix.overall_risk}"
            )
            return matrix

        except Exception as e:
            self.logger.error(f"Error parsing Risk5D for {ticker}: {e}")
            return RiskMatrix5D(ticker=ticker)

    def parse_quality_metrics(self, ticker: str, mcp_response: dict) -> dict:
        """
        Parse MCP: get_stock_keyratios response for quality pre-filtering.

        Returns dict with Piotroski F-Score, Altman Z-Score, ROIC, margins.
        Used by TickerQualifier to reject low-quality stocks before Walk-Forward.
        """
        try:
            data = mcp_response if isinstance(mcp_response, dict) else {}
            metrics = {
                "piotroski_f_score": int(self._safe_float(data.get("piotroski_f_score", 0))),
                "altman_z_score": self._safe_float(data.get("altman_z_score", 0)),
                "roic": self._safe_float(data.get("roic", 0)),
                "roe": self._safe_float(data.get("roe", 0)),
                "gross_margin": self._safe_float(data.get("gross_margin", 0)),
                "operating_margin": self._safe_float(data.get("operating_margin", 0)),
                "debt_to_equity": self._safe_float(data.get("debt_to_equity", 0)),
                "current_ratio": self._safe_float(data.get("current_ratio", 0)),
                "beta": self._safe_float(data.get("beta", 1.0)),
                "short_float_pct": self._safe_float(data.get("short_float_pct", 0)),
            }
            return metrics
        except Exception as e:
            self.logger.error(f"Error parsing quality for {ticker}: {e}")
            return {}

    def passes_quality_gate(self, metrics: dict) -> tuple[bool, str]:
        """
        Pre-filter decision: does this stock meet minimum quality?

        Rules:
        - Altman Z-Score > 1.81 (not in distress zone)
        - Piotroski F-Score >= 3 (not extremely weak)

        Returns: (passes, reason)
        """
        altman = metrics.get("altman_z_score", 0)
        piotroski = metrics.get("piotroski_f_score", 0)

        if altman > 0 and altman < 1.81:
            return False, f"Altman Z={altman:.2f} < 1.81 (distress zone)"
        if piotroski > 0 and piotroski < 3:
            return False, f"Piotroski F={piotroski} < 3 (weak financials)"

        return True, "OK"

    # ═══════════════════════════════════════════════════════════
    # INSIDER INTELLIGENCE
    # ═══════════════════════════════════════════════════════════

    def parse_insider_conviction(
        self,
        ticker: str,
        cluster_data: dict = None,
        ceo_data: dict = None,
        cfo_data: dict = None,
    ) -> InsiderConviction:
        """
        Parse MCP: get_insider_cluster_buys + get_insider_ceo_buys + get_insider_cfo_buys.

        Cluster buys (multiple insiders buying simultaneously) are the
        strongest insider signal — much stronger than individual transactions.
        """
        try:
            cluster_count = self._count_events(cluster_data)
            ceo_count = self._count_events(ceo_data)
            cfo_count = self._count_events(cfo_data)

            total = cluster_count + ceo_count + cfo_count

            # Conviction scoring: cluster buys weighted 3x
            conviction = min(100, (cluster_count * 30) + (ceo_count * 20) + (cfo_count * 15))

            if conviction >= 70:
                sentiment = "strong_buy"
            elif conviction >= 40:
                sentiment = "buy"
            elif conviction > 0:
                sentiment = "neutral"
            else:
                sentiment = "neutral"

            result = InsiderConviction(
                ticker=ticker,
                conviction_score=conviction,
                cluster_buys=cluster_count,
                ceo_buys=ceo_count,
                cfo_buys=cfo_count,
                total_insider_buys=total,
                net_insider_sentiment=sentiment,
                raw_data={
                    "cluster": cluster_data or {},
                    "ceo": ceo_data or {},
                    "cfo": cfo_data or {},
                },
            )

            self.logger.info(
                f"Insider {ticker}: conviction={conviction:.0f}, "
                f"cluster={cluster_count}, ceo={ceo_count}, "
                f"sentiment={sentiment}"
            )
            return result

        except Exception as e:
            self.logger.error(f"Error parsing insider for {ticker}: {e}")
            return InsiderConviction(ticker=ticker)

    # ═══════════════════════════════════════════════════════════
    # GURU / INSTITUTIONAL TRACKING
    # ═══════════════════════════════════════════════════════════

    def parse_guru_tracking(
        self, ticker: str, gurus_data: dict = None, picks_data: dict = None
    ) -> GuruTracking:
        """
        Parse MCP: get_stock_gurus + get_guru_realtime_picks.

        Replaces the boolean guru_accumulation in UniverseCandidate with
        a quantitative score based on guru portfolio actions.
        """
        try:
            guru_count = 0
            top_holders = []
            net_buys = 0
            net_sells = 0

            if gurus_data and isinstance(gurus_data, (dict, list)):
                holders = gurus_data if isinstance(gurus_data, list) else gurus_data.get("data", [])
                guru_count = len(holders)
                for guru in holders[:10]:
                    action = str(guru.get("action", "hold")).lower()
                    if "buy" in action or "add" in action:
                        net_buys += 1
                    elif "sell" in action or "reduce" in action:
                        net_sells += 1
                    top_holders.append({
                        "name": guru.get("name", "Unknown"),
                        "action": action,
                        "shares": guru.get("shares", 0),
                    })

            total_actions = net_buys + net_sells
            net_score = ((net_buys - net_sells) / max(total_actions, 1)) * 100

            return GuruTracking(
                ticker=ticker,
                guru_count=guru_count,
                net_buying_score=net_score,
                top_holders=top_holders[:5],
                accumulation=net_buys > net_sells,
                raw_data={
                    "gurus": gurus_data or {},
                    "picks": picks_data or {},
                },
            )

        except Exception as e:
            self.logger.error(f"Error parsing guru tracking for {ticker}: {e}")
            return GuruTracking(ticker=ticker)

    # ═══════════════════════════════════════════════════════════
    # ANALYST INTELLIGENCE
    # ═══════════════════════════════════════════════════════════

    def parse_analyst_intelligence(
        self, ticker: str, estimates_data: dict = None, history_data: dict = None
    ) -> AnalystIntelligence:
        """
        Parse MCP: get_stock_analyst_estimates + get_stock_estimate_history.

        Revision momentum (estimates being revised up or down) is a stronger
        signal than the absolute consensus level.
        """
        try:
            data = estimates_data if isinstance(estimates_data, dict) else {}

            consensus_map = {1: "strong_buy", 2: "buy", 3: "hold", 4: "sell", 5: "strong_sell"}
            consensus_val = self._safe_float(data.get("consensus", 3))
            consensus = consensus_map.get(int(consensus_val), "hold")

            target_mean = self._safe_float(data.get("price_target_mean", 0))
            current_price = self._safe_float(data.get("current_price", 0))
            upside = (
                ((target_mean - current_price) / current_price * 100)
                if current_price > 0 else 0
            )

            return AnalystIntelligence(
                ticker=ticker,
                consensus=consensus,
                price_target_mean=target_mean,
                price_target_upside_pct=upside,
                num_analysts=int(self._safe_float(data.get("num_analysts", 0))),
                revision_momentum=self._safe_float(data.get("revision_momentum", 0)),
                earnings_surprise_pct=self._safe_float(
                    data.get("earnings_surprise_pct", 0)
                ),
                raw_data=data,
            )

        except Exception as e:
            self.logger.error(f"Error parsing analyst for {ticker}: {e}")
            return AnalystIntelligence(ticker=ticker)

    # ═══════════════════════════════════════════════════════════
    # MACRO & ECONOMIC
    # ═══════════════════════════════════════════════════════════

    def parse_macro_dashboard(self, indicators_data: dict = None) -> MacroDashboard:
        """
        Parse MCP: get_economic_indicators response.

        Provides GDP, CPI, Fed Funds Rate, Unemployment for
        enhanced MacroRegimeDetector — transforms 2-signal (VIX+Yield)
        into 6-signal macro regime detection.
        """
        try:
            data = indicators_data if isinstance(indicators_data, dict) else {}

            dashboard = MacroDashboard(
                gdp_growth=self._safe_float(data.get("gdp_growth")),
                cpi_yoy=self._safe_float(data.get("cpi_yoy")),
                fed_funds_rate=self._safe_float(data.get("fed_funds_rate")),
                unemployment_rate=self._safe_float(data.get("unemployment_rate")),
                treasury_10y=self._safe_float(data.get("treasury_10y")),
                treasury_2y=self._safe_float(data.get("treasury_2y")),
                raw_data=data,
            )

            if dashboard.treasury_10y and dashboard.treasury_2y:
                dashboard.yield_spread = dashboard.treasury_10y - dashboard.treasury_2y

            return dashboard

        except Exception as e:
            self.logger.error(f"Error parsing macro dashboard: {e}")
            return MacroDashboard()

    # ═══════════════════════════════════════════════════════════
    # POLITICAL SIGNAL
    # ═══════════════════════════════════════════════════════════

    def parse_political_trades(self, ticker: str = None, data: dict = None) -> dict:
        """
        Parse MCP: get_politician_transactions.

        Congressional trades can be a leading indicator — available via
        both GuruFocus MCP and Finnhub MCP for cross-validation.
        """
        try:
            transactions = data if isinstance(data, (dict, list)) else {}
            items = transactions if isinstance(transactions, list) else transactions.get("data", [])

            buys = [t for t in items if "buy" in str(t.get("type", "")).lower() or "purchase" in str(t.get("type", "")).lower()]
            sells = [t for t in items if "sell" in str(t.get("type", "")).lower()]

            return {
                "ticker": ticker,
                "total_transactions": len(items),
                "buys": len(buys),
                "sells": len(sells),
                "net_signal": "bullish" if len(buys) > len(sells) else "bearish" if len(sells) > len(buys) else "neutral",
                "recent": items[:5],
            }

        except Exception as e:
            self.logger.error(f"Error parsing political trades: {e}")
            return {"ticker": ticker, "net_signal": "neutral"}

    # ═══════════════════════════════════════════════════════════
    # GURU VALUATION — Real GF Data for Scoring
    # ═══════════════════════════════════════════════════════════

    def parse_guru_valuation(self, ticker: str, qgarp_data: dict, keyratios_data: dict = None) -> dict:
        """
        Extract guru-grade valuation signals from QGARP and KeyRatios data.

        Returns dict with:
            price_to_gf_value: Price / GF Value (<1 = undervalued)
            gf_value_discount_pct: Margin of Safety % (positive = cheap)
            ps_vs_historical: Current P/S / Historical Median P/S
            price_to_fcf: Price / Free Cash Flow
            fcf_margin: FCF Margin %
            beneish_m_score: Beneish M-Score (> -1.78 = manipulation risk)
        """
        result = {
            "price_to_gf_value": 0.0,
            "gf_value_discount_pct": 0.0,
            "ps_vs_historical": 0.0,
            "price_to_fcf": 0.0,
            "fcf_margin": 0.0,
            "beneish_m_score": -3.0,  # Default: safe
        }

        try:
            data = qgarp_data if isinstance(qgarp_data, dict) else {}

            # --- Price / GF Value ---
            # From QGARP valuation section or summary
            valuation = data.get("valuation", {})
            current_price = valuation.get("current_price", 0) or data.get("current_price", 0)
            gf_value = valuation.get("gf_value", 0) or data.get("gf_value", 0)

            if current_price and gf_value and gf_value > 0:
                result["price_to_gf_value"] = round(current_price / gf_value, 3)
                result["gf_value_discount_pct"] = round(
                    ((gf_value - current_price) / gf_value) * 100, 1
                )

            # --- P/S vs Historical Median ---
            # From QGARP valuation multiples
            ps_data = valuation.get("ps", {})
            ps_current = self._safe_float(ps_data.get("current", 0))
            ps_hist_median = self._safe_float(ps_data.get("historical_median", 0))
            if ps_current > 0 and ps_hist_median > 0:
                result["ps_vs_historical"] = round(ps_current / ps_hist_median, 3)

            # --- Price / FCF ---
            # From keyratios valuation or QGARP
            kr = keyratios_data if isinstance(keyratios_data, dict) else {}
            kr_valuation = kr.get("valuation", {})
            price_to_fcf = self._safe_float(kr_valuation.get("price_to_fcf", 0))
            if price_to_fcf <= 0:
                # Try QGARP overview - some responses nest differently
                price_to_fcf = self._safe_float(data.get("price_to_fcf", 0))
            result["price_to_fcf"] = price_to_fcf

            # --- FCF Margin ---
            kr_profitability = kr.get("profitability", {})
            fcf_margin = self._safe_float(kr_profitability.get("fcf_margin", 0))
            if fcf_margin <= 0:
                # Try from QGARP profitability section
                prof = data.get("profitability", {})
                fcf_margin = self._safe_float(prof.get("fcf_margin", 0))
            result["fcf_margin"] = fcf_margin

            # --- Beneish M-Score ---
            beneish = self._safe_float(kr.get("beneish_m_score", -3.0), default=-3.0)
            if beneish == 0:
                beneish = -3.0  # Treat missing as safe
            result["beneish_m_score"] = beneish

            self.logger.info(
                f"GuruValuation {ticker}: P/GF={result['price_to_gf_value']:.2f}, "
                f"MoS={result['gf_value_discount_pct']:+.1f}%, "
                f"P/S_hist={result['ps_vs_historical']:.2f}, "
                f"P/FCF={result['price_to_fcf']:.1f}, "
                f"FCF%={result['fcf_margin']:.1f}, "
                f"Beneish={result['beneish_m_score']:.2f}"
            )
            return result

        except Exception as e:
            self.logger.error(f"Error parsing guru valuation for {ticker}: {e}")
            return result

    # ═══════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """Safely convert value to float."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _count_events(data) -> int:
        """Count events from MCP response (list or dict with data key)."""
        if not data:
            return 0
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            entries = data.get("data", data.get("entries", []))
            return len(entries) if isinstance(entries, list) else 0
        return 0
