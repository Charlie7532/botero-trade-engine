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

    def _is_aggregate_format(self, flow: List[Dict]) -> bool:
        """Detect if flow data is daily aggregates (from /options-volume) vs individual alerts."""
        if not flow:
            return False
        sample = flow[0]
        # Aggregates have call_volume/put_volume; individual alerts have option_type/side
        return 'call_volume' in sample and 'option_type' not in sample

    def _parse_aggregates(
        self,
        ticker: str,
        flow: List[Dict],
        reference_date: Optional[date],
        now: datetime,
    ) -> FlowPersistenceSignal:
        """
        Parse daily aggregate flow data (from UW /stock/{ticker}/options-volume).
        
        Each record has: date, call_volume, put_volume, call_volume_ask_side,
        put_volume_ask_side, net_call_premium, net_put_premium, bullish_premium,
        bearish_premium, etc.
        """
        ref_str = reference_date.isoformat() if reference_date else now.strftime("%Y-%m-%d")
        
        # Filter to only the 7 days up to reference_date
        recent = [r for r in flow if r.get('date', '') <= ref_str]
        recent = sorted(recent, key=lambda x: x.get('date', ''), reverse=True)[:7]
        
        if not recent:
            return FlowPersistenceSignal(ticker=ticker, persistence_grade="DEAD_SIGNAL", freshness_weight=0.0)
        
        latest_date_str = recent[0].get('date', '')
        if latest_date_str:
            try:
                latest_dt = datetime.fromisoformat(latest_date_str + "T16:00:00+00:00")
                hours_old = (now - latest_dt).total_seconds() / 3600.0
            except:
                hours_old = 999.0
        else:
            hours_old = 999.0
        
        freshness = self.calculate_freshness(hours_old)
        days_with_flow = set(r.get('date', '')[:10] for r in recent if r.get('date'))
        consecutive_days = len(days_with_flow)
        
        # Directional conviction from aggregate metrics
        bullish_days = 0
        bearish_days = 0
        total_bullish_premium = 0.0
        total_bearish_premium = 0.0
        
        for r in recent:
            # Method 1: Use bullish_premium / bearish_premium if available
            bp = float(r.get('bullish_premium', 0) or 0)
            brp = float(r.get('bearish_premium', 0) or 0)
            
            if bp > 0 or brp > 0:
                total_bullish_premium += bp
                total_bearish_premium += brp
                if bp > brp:
                    bullish_days += 1
                elif brp > bp:
                    bearish_days += 1
            else:
                # Method 2: Fallback to call_volume_ask_side vs put_volume_ask_side
                call_ask = int(r.get('call_volume_ask_side', 0) or 0)
                put_ask = int(r.get('put_volume_ask_side', 0) or 0)
                # Ask-side calls = buying to open (bullish), Ask-side puts = buying to open (bearish)
                if call_ask > put_ask * 1.1:
                    bullish_days += 1
                elif put_ask > call_ask * 1.1:
                    bearish_days += 1
                    
                # Use net premiums
                ncp = float(r.get('net_call_premium', 0) or 0)
                npp = float(r.get('net_put_premium', 0) or 0)
                total_bullish_premium += max(0, ncp)
                total_bearish_premium += max(0, npp)
        
        total_dir = bullish_days + bearish_days
        consistency = (max(bullish_days, bearish_days) / total_dir) if total_dir > 0 else 0.0
        
        # Classify grade
        grade = "UNKNOWN"
        score = 50.0
        
        if hours_old > 96:
            grade = "DEAD_SIGNAL"
            score = 10.0
        elif consecutive_days >= 3 and consistency >= 0.65:
            grade = "CONFIRMED_STREAK"
            score = 90.0
        elif consecutive_days >= 2 and hours_old < 24 and consistency >= 0.7:
            grade = "FRESH_ACCUMULATION"
            score = 85.0
        elif consecutive_days >= 1 and hours_old < 24:
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
        )

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
        
        Supports TWO data formats:
        1. Individual alerts (from /option-trades/flow-alerts) with option_type, side, is_sweep
        2. Daily aggregates (from /stock/{ticker}/options-volume) with call_volume, put_volume
        
        Args:
            recent_flow: List of flow alerts or daily aggregates.
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
        
        # Detect data format and dispatch
        if self._is_aggregate_format(recent_flow):
            return self._parse_aggregates(ticker, recent_flow, reference_date, now)
        
        # Original path: individual alerts
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
        consistency = (max(bullish_count, bearish_count) / total_directional) if total_directional > 0 else 0.0
        
        consecutive_days = len(days_with_flow)
        
        # 2. Analyze Dark Pool
        dp_premium = 0.0
        for dp in darkpool_prints:
            size = float(dp.get('size', 0))
            price = float(dp.get('price', 0))
            dp_premium += size * price

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
