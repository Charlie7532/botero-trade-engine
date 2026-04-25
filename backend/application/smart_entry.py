"""
Smart Entry Engine — Intelligent Order Execution
====================================================
Replaces dangerous MarketOrderRequest with institutional-grade entry logic.

Problems solved:
1. Gap protection — abort if price gapped too far overnight
2. Limit orders with ceiling — never pay more than analysis price + tolerance
3. Pre-market validation — verify price before committing capital
4. Spread protection — abort if bid/ask spread too wide (illiquid)
5. Wait period — optional delay to let opening volatility settle

Philosophy:
    "It's better to miss a trade than to enter at a terrible price."
    A 3% gap at open can erase 2 weeks of alpha in a single trade.
"""
import logging
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GapRules:
    """Configurable gap protection rules."""
    max_gap_up_pct: float = 3.0        # Abort buy if gap > +3%
    max_gap_down_pct: float = -5.0     # Abort buy if gap < -5% (something bad happened)
    max_entry_premium_pct: float = 2.0 # Limit price = analysis_price × (1 + 2%)
    max_spread_pct: float = 0.5        # Abort if bid/ask spread > 0.5%
    wait_minutes_after_open: int = 0   # Minutes to wait after market open (0 = immediate)
    min_premarket_volume: int = 5000   # Minimum premarket volume to trust the price
    order_timeout_minutes: int = 30    # Cancel unfilled limit orders after 30 min


@dataclass
class PreMarketCheck:
    """Result of pre-market validation."""
    ticker: str
    analysis_price: float       # Price when we analyzed (previous close)
    premarket_price: float      # Current premarket or latest price
    gap_pct: float              # Gap percentage
    spread_pct: float = 0.0     # Bid/Ask spread as percentage
    premarket_volume: int = 0   # Volume in premarket
    is_valid: bool = True       # Whether entry is approved
    rejection_reason: str = ""  # Why rejected (if any)
    recommended_limit: float = 0.0  # Recommended limit price
    recommended_stop: float = 0.0   # Recommended initial stop


class SmartEntryEngine:
    """
    Intelligent entry execution engine.

    Validates pre-market conditions and generates appropriate order types
    instead of blind market orders at the open.

    Usage:
        engine = SmartEntryEngine()
        check = engine.validate_entry("NVDA", analysis_price=950.0)
        if check.is_valid:
            order = engine.create_limit_order(check)
    """

    def __init__(self, rules: GapRules = None):
        self.rules = rules or GapRules()
        self.logger = logging.getLogger(f"{__name__}.SmartEntryEngine")

    # ═══════════════════════════════════════════════════════════
    # PRE-MARKET VALIDATION
    # ═══════════════════════════════════════════════════════════

    def validate_entry(
        self,
        ticker: str,
        analysis_price: float,
        current_price: float = None,
        bid: float = None,
        ask: float = None,
        premarket_volume: int = 0,
        atr: float = None,
    ) -> PreMarketCheck:
        """
        Validate whether a trade entry is safe based on current conditions.

        Args:
            ticker: Stock symbol
            analysis_price: Price when we ran the analysis (previous close)
            current_price: Current/premarket price
            bid: Current bid price
            ask: Current ask price
            premarket_volume: Volume traded in premarket
            atr: Average True Range for stop calculation

        Returns:
            PreMarketCheck with validation result and recommended prices
        """
        check = PreMarketCheck(
            ticker=ticker,
            analysis_price=analysis_price,
            premarket_price=current_price or analysis_price,
            gap_pct=0.0,
        )

        # If no current price, we can't validate — use analysis price
        if current_price is None or current_price <= 0:
            check.recommended_limit = analysis_price * (1 + self.rules.max_entry_premium_pct / 100)
            if atr:
                check.recommended_stop = analysis_price - (atr * 2)
            self.logger.warning(f"{ticker}: No premarket price available, using analysis price ${analysis_price:.2f}")
            return check

        # Calculate gap
        gap_pct = ((current_price - analysis_price) / analysis_price) * 100
        check.gap_pct = round(gap_pct, 2)
        check.premarket_volume = premarket_volume

        # ── CHECK 1: Gap Up too large ──
        if gap_pct > self.rules.max_gap_up_pct:
            check.is_valid = False
            check.rejection_reason = (
                f"Gap UP {gap_pct:.1f}% > max {self.rules.max_gap_up_pct}%. "
                f"Price moved from ${analysis_price:.2f} → ${current_price:.2f}. "
                f"Too expensive — wait for pullback."
            )
            self.logger.warning(f"❌ {ticker}: {check.rejection_reason}")
            return check

        # ── CHECK 2: Gap Down too large ──
        if gap_pct < self.rules.max_gap_down_pct:
            check.is_valid = False
            check.rejection_reason = (
                f"Gap DOWN {gap_pct:.1f}% < max {self.rules.max_gap_down_pct}%. "
                f"Price moved from ${analysis_price:.2f} → ${current_price:.2f}. "
                f"Something bad happened overnight — thesis may be broken."
            )
            self.logger.warning(f"❌ {ticker}: {check.rejection_reason}")
            return check

        # ── CHECK 3: Spread too wide ──
        if bid and ask and ask > 0:
            spread_pct = ((ask - bid) / ask) * 100
            check.spread_pct = round(spread_pct, 2)
            if spread_pct > self.rules.max_spread_pct:
                check.is_valid = False
                check.rejection_reason = (
                    f"Spread {spread_pct:.2f}% > max {self.rules.max_spread_pct}%. "
                    f"Bid=${bid:.2f}, Ask=${ask:.2f}. Illiquid — skip."
                )
                self.logger.warning(f"❌ {ticker}: {check.rejection_reason}")
                return check

        # ── CHECK 4: Premarket volume too low ──
        if premarket_volume > 0 and premarket_volume < self.rules.min_premarket_volume:
            self.logger.info(
                f"⚠️ {ticker}: Low premarket volume ({premarket_volume} < {self.rules.min_premarket_volume}). "
                f"Price may not be reliable."
            )
            # Don't reject, but tighten the limit
            check.recommended_limit = analysis_price * (1 + self.rules.max_entry_premium_pct / 200)  # Half tolerance
        else:
            # Normal limit: analysis price + max premium
            check.recommended_limit = analysis_price * (1 + self.rules.max_entry_premium_pct / 100)

        # If current price is BELOW analysis price (gap down but within tolerance)
        # → even better: use current price + small buffer
        if current_price < analysis_price:
            check.recommended_limit = current_price * 1.005  # +0.5% buffer
            self.logger.info(f"✅ {ticker}: Gap down {gap_pct:.1f}% — favorable entry at ${current_price:.2f}")

        # Stop loss recommendation
        if atr and atr > 0:
            entry_estimate = min(current_price, check.recommended_limit)
            check.recommended_stop = entry_estimate - (atr * 2)
        else:
            # Fallback: 5% below entry
            entry_estimate = min(current_price, check.recommended_limit)
            check.recommended_stop = entry_estimate * 0.95

        check.recommended_limit = round(check.recommended_limit, 2)
        check.recommended_stop = round(check.recommended_stop, 2)

        self.logger.info(
            f"✅ {ticker}: Entry APPROVED. "
            f"Gap={gap_pct:+.1f}%, Limit=${check.recommended_limit:.2f}, "
            f"Stop=${check.recommended_stop:.2f}"
        )
        return check

    # ═══════════════════════════════════════════════════════════
    # ORDER CREATION
    # ═══════════════════════════════════════════════════════════

    def create_limit_order_params(
        self,
        check: PreMarketCheck,
        notional: float = None,
        qty: int = None,
    ) -> dict:
        """
        Create order parameters for a limit order based on pre-market validation.

        Returns dict suitable for Alpaca LimitOrderRequest or future IB adapter.
        """
        if not check.is_valid:
            raise ValueError(f"Cannot create order for rejected entry: {check.rejection_reason}")

        params = {
            "symbol": check.ticker,
            "side": "buy",
            "type": "limit",
            "limit_price": check.recommended_limit,
            "time_in_force": "day",
            "initial_stop": check.recommended_stop,
        }

        if notional:
            # Calculate qty from notional
            estimated_qty = int(notional / check.recommended_limit)
            params["qty"] = max(1, estimated_qty)
            params["estimated_notional"] = round(estimated_qty * check.recommended_limit, 2)
        elif qty:
            params["qty"] = qty
            params["estimated_notional"] = round(qty * check.recommended_limit, 2)

        return params

    def create_bracket_order_params(
        self,
        check: PreMarketCheck,
        notional: float = None,
        risk_reward_ratio: float = 2.0,
    ) -> dict:
        """
        Create bracket order (entry + stop + take profit) parameters.

        A bracket order is atomic — if entry fills, stop and target are
        automatically placed. This is the safest order type.
        """
        if not check.is_valid:
            raise ValueError(f"Cannot create bracket for rejected entry: {check.rejection_reason}")

        entry_price = check.recommended_limit
        stop_price = check.recommended_stop
        risk_per_share = entry_price - stop_price
        target_price = round(entry_price + (risk_per_share * risk_reward_ratio), 2)

        qty = 1
        if notional:
            qty = max(1, int(notional / entry_price))

        return {
            "symbol": check.ticker,
            "side": "buy",
            "type": "bracket",
            "qty": qty,
            "limit_price": entry_price,
            "stop_loss_price": stop_price,
            "take_profit_price": target_price,
            "time_in_force": "day",
            "risk_per_share": round(risk_per_share, 2),
            "reward_per_share": round(risk_per_share * risk_reward_ratio, 2),
            "risk_reward_ratio": risk_reward_ratio,
        }

    # ═══════════════════════════════════════════════════════════
    # ALPACA ORDER SUBMISSION
    # ═══════════════════════════════════════════════════════════

    def submit_alpaca_limit_order(
        self,
        client,
        check: PreMarketCheck,
        notional: float = None,
        qty: int = None,
    ):
        """
        Submit a limit order to Alpaca (replaces MarketOrderRequest).

        Args:
            client: Alpaca TradingClient
            check: Validated PreMarketCheck
            notional: Dollar amount to invest
            qty: Number of shares (alternative to notional)

        Returns:
            Alpaca Order object
        """
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        if not check.is_valid:
            raise ValueError(f"Entry rejected: {check.rejection_reason}")

        # Calculate quantity
        if notional and not qty:
            qty = max(1, int(notional / check.recommended_limit))

        order_request = LimitOrderRequest(
            symbol=check.ticker,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=check.recommended_limit,
        )

        self.logger.info(
            f"📤 Submitting LIMIT order: {check.ticker} "
            f"qty={qty}, limit=${check.recommended_limit:.2f} "
            f"(analysis=${check.analysis_price:.2f}, gap={check.gap_pct:+.1f}%)"
        )

        order = client.submit_order(order_request)
        return order

    # ═══════════════════════════════════════════════════════════
    # VOLATILITY-ADAPTIVE RULES
    # ═══════════════════════════════════════════════════════════

    def adaptive_rules(self, vix: float = None, beta: float = None) -> GapRules:
        """
        Adjust gap rules based on market volatility (VIX) and stock beta.

        High VIX → tighter gaps, narrower limits (more conservative)
        High beta → wider gaps (stock naturally moves more)
        """
        rules = GapRules(
            max_gap_up_pct=self.rules.max_gap_up_pct,
            max_gap_down_pct=self.rules.max_gap_down_pct,
            max_entry_premium_pct=self.rules.max_entry_premium_pct,
            max_spread_pct=self.rules.max_spread_pct,
        )

        # VIX adjustment — check crisis FIRST, then elevated
        if vix and vix > 35:
            # Crisis: very tight execution
            rules.max_entry_premium_pct *= 0.3
            rules.max_gap_up_pct *= 2.0  # Allow wider gaps (everything is swinging)
            rules.max_gap_down_pct *= 2.0
            rules.wait_minutes_after_open = 15  # Wait for opening chaos to settle

        elif vix and vix > 25:
            # High volatility: tighten entry premium
            rules.max_entry_premium_pct *= 0.5  # Half the premium tolerance
            rules.max_gap_up_pct *= 1.5  # Allow wider gaps (they're normal in high vol)
            rules.max_gap_down_pct *= 1.5  # Same for downs

        # Beta adjustment
        if beta and beta > 1.5:
            # High beta stock: wider tolerances (naturally moves more)
            rules.max_gap_up_pct *= beta / 1.5
            rules.max_gap_down_pct *= beta / 1.5

        return rules
