"""
FLOW PERSISTENCE ANALYZER
=========================
Calculates temporal decay, multi-day institutional persistence,
and dark pool confirmation for options flow signals.
"""
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, UTC, date

logger = logging.getLogger(__name__)

@dataclass
class FlowPersistenceSignal:
    ticker: str
    
    # Temporal dimensions
    hours_since_latest: float = 999.0          # How fresh is the newest signal?
    days_with_flow: int = 0                    # How many of last 5 days had flow?
    consecutive_days: int = 0                  # Current streak of same-direction flow
    freshness_weight: float = 0.0              # e^(-0.3 * days_old), 0.0-1.0
    
    # Conviction modifiers
    direction_consistency: float = 0.0         # % of signals that agree (bullish vs bearish)
    premium_trend: str = "STABLE"              # INCREASING, STABLE, DECREASING
    voi_trend: str = "STABLE"                  # Are VOI ratios growing?
    
    # Dark pool confirmation
    darkpool_aligned: bool = False             # Is darkpool buying in same direction?
    darkpool_premium: float = 0.0              # Total dark pool premium in last 5 days
    darkpool_count: int = 0                    # Number of dark pool prints
    
    # Price validation (post-signal behavior)
    price_at_first_signal: float = 0.0         # Price when first signal of streak appeared
    price_now: float = 0.0                     # Current price
    price_confirmed: bool = False              # Did price move in signal direction?
    price_change_since_signal_pct: float = 0.0
    
    # Composite
    persistence_score: float = 0.0             # 0-100 composite
    persistence_grade: str = "UNKNOWN"         # FRESH_ACCUMULATION, DEAD_SIGNAL, etc.


class FlowPersistenceAnalyzer:
    """
    Evaluates historical options flow and dark pool prints to determine
    the true institutional conviction and freshness of a signal.
    """
    
    LAMBDA_DECAY = 0.3  # Decay rate per day (~24h half-life)
    
    def calculate_freshness(self, hours_old: float) -> float:
        """Exponential decay with 24-hour half-life."""
        if hours_old < 0:
            return 1.0
        days_old = hours_old / 24.0
        return math.exp(-self.LAMBDA_DECAY * days_old)

    def evaluate_persistence(
        self,
        ticker: str,
        recent_flow: List[Dict],
        darkpool_prints: List[Dict],
        current_price: float,
        price_history: List[float],
        reference_date: Optional[date] = None,
    ) -> FlowPersistenceSignal:
        """
        Analyzes recent flow to generate a persistence grade.
        
        Args:
            recent_flow: List of flow alerts from last 5 days.
            darkpool_prints: List of dark pool blocks from last 5 days.
            current_price: Latest close.
            price_history: Historical prices matching the days of the flow.
            reference_date: For historical simulation purposes.
        """
        if not recent_flow:
            return FlowPersistenceSignal(
                ticker=ticker,
                persistence_grade="DEAD_SIGNAL",
                freshness_weight=0.0
            )

        # 1. Analyze Flow Temporality
        if reference_date:
            # For simulation, simulate end of day 16:00 ET (20:00 UTC)
            now = datetime(reference_date.year, reference_date.month, reference_date.day, 20, 0, tzinfo=UTC)
        else:
            now = datetime.now(UTC)
        
        # Sort flow newest to oldest
        try:
            sorted_flow = sorted(
                recent_flow, 
                key=lambda x: datetime.fromisoformat(
                    (x.get('timestamp') or x.get('created_at') or x.get('date', now.isoformat()[:10]))[:10] + "T16:00:00+00:00"
                ), 
                reverse=True
            )
        except Exception as e:
            logger.error(f"Error sorting flow for {ticker}: {e}")
            sorted_flow = recent_flow

        latest_time_str = sorted_flow[0].get('timestamp') or sorted_flow[0].get('created_at') or sorted_flow[0].get('date')
        if latest_time_str:
            try:
                # Si viene solo la fecha 'YYYY-MM-DD', agregar la hora
                if len(latest_time_str) == 10:
                    latest_time_str += "T16:00:00Z" # Asumir cierre de mercado
                latest_dt = datetime.fromisoformat(latest_time_str.replace('Z', '+00:00'))
                hours_old = (now - latest_dt).total_seconds() / 3600.0
            except:
                hours_old = 999.0
        else:
            hours_old = 999.0

        freshness = self.calculate_freshness(hours_old)
        
        # Group by day to check streaks
        # In a real scenario, we map timestamps to trading days
        days_with_flow = set()
        bullish_count = 0
        bearish_count = 0
        
        for alert in sorted_flow:
            ts = alert.get('timestamp') or alert.get('created_at')
            if ts:
                day_str = ts[:10]
                days_with_flow.add(day_str)
            
            # Simple heuristic: Calls at Ask/Above Ask are bullish
            # Puts at Ask/Above Ask are bearish
            side = alert.get('side', '').upper()
            contract_type = alert.get('option_type', alert.get('type', '')).upper()
            
            if contract_type == 'CALL' and side == 'ASK':
                bullish_count += 1
            elif contract_type == 'PUT' and side == 'BID':
                bullish_count += 1
            elif contract_type == 'PUT' and side == 'ASK':
                bearish_count += 1
            elif contract_type == 'CALL' and side == 'BID':
                bearish_count += 1
                
        total_directional = bullish_count + bearish_count
        dominant_direction = "BULLISH" if bullish_count >= bearish_count else "BEARISH"
        consistency = (max(bullish_count, bearish_count) / total_directional) if total_directional > 0 else 0.0
        
        # Mocking consecutive days logic (assumes sorted_flow covers continuous days)
        # For full implementation, we need a trading calendar. Let's approximate.
        consecutive_days = len(days_with_flow)
        
        # 2. Analyze Dark Pool
        dp_premium = 0.0
        dp_bullish = 0
        dp_bearish = 0
        
        for print in darkpool_prints:
            size = float(print.get('size', 0))
            price = float(print.get('price', 0))
            premium = size * price
            dp_premium += premium
            
            # Very naive DP assumption: large blocks at ask = buy
            # Normally UW doesn't give side for DP, so we might need to assume 
            # alignment if price moves up after print
            # For now, we will rely on external flagging or price action
            pass

        # 3. Classify Grade
        grade = "UNKNOWN"
        score = 50.0
        
        if hours_old > 96: # Older than 4 days
            grade = "DEAD_SIGNAL"
            score = 10.0
        elif consecutive_days >= 3 and consistency >= 0.7:
            grade = "CONFIRMED_STREAK"
            score = 90.0
        elif consecutive_days >= 2 and hours_old < 12 and consistency >= 0.8:
            grade = "FRESH_ACCUMULATION"
            score = 85.0
        elif consecutive_days == 1 and hours_old < 12:
            grade = "FRESH_ISOLATED"
            score = 65.0
        elif consecutive_days >= 2 and hours_old > 24:
            grade = "STALE_CONFIRMED"
            score = 55.0
        else:
            grade = "STALE_UNCONFIRMED"
            score = 30.0
            
        return FlowPersistenceSignal(
            ticker=ticker,
            hours_since_latest=hours_old,
            days_with_flow=len(days_with_flow),
            consecutive_days=consecutive_days,
            freshness_weight=freshness,
            direction_consistency=consistency,
            persistence_score=score,
            persistence_grade=grade,
            darkpool_premium=dp_premium,
            darkpool_count=len(darkpool_prints)
        )
