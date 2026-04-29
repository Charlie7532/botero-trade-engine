"""
SMC Adapter — Smart Money Concepts Infrastructure
====================================================
Wraps the smartmoneyconcepts library behind the MarketStructurePort.

Library: smartmoneyconcepts>=0.0.26
Detects: BOS, CHoCH, Order Blocks, Fair Value Gaps, Liquidity sweeps
"""
import logging

import pandas as pd

from backend.modules.simulation.domain.ports.market_structure_port import (
    MarketStructurePort,
    MarketStructureResult,
)

logger = logging.getLogger(__name__)


class SMCAdapter(MarketStructurePort):
    """Adapter wrapping smartmoneyconcepts for structural analysis."""

    def analyze(self, ohlc: pd.DataFrame) -> MarketStructureResult:
        """
        Run full SMC analysis. Requires minimum 50 bars.

        Gracefully degrades if smartmoneyconcepts is not installed.
        """
        if len(ohlc) < 50:
            logger.warning("SMCAdapter: insufficient bars (<50), returning defaults")
            return MarketStructureResult()

        try:
            from smartmoneyconcepts import smc
        except ImportError:
            logger.warning(
                "SMCAdapter: smartmoneyconcepts not installed. "
                "Install with: pip install smartmoneyconcepts"
            )
            return MarketStructureResult()

        result = MarketStructureResult()

        try:
            # Ensure column names match library expectations
            df = ohlc.copy()
            col_map = {}
            for col in df.columns:
                col_map[col] = col.lower()
            df.rename(columns=col_map, inplace=True)

            # Swing highs/lows for trend detection
            swing_hl = smc.swing_highs_lows(df, swing_length=10)
            if swing_hl is not None and not swing_hl.empty:
                recent_swings = swing_hl.dropna(subset=["HighLow"]).tail(4)
                if len(recent_swings) >= 2:
                    last_two = recent_swings["HighLow"].values[-2:]
                    if all(v > 0 for v in last_two):
                        result.swing_trend = "UPTREND"
                    elif all(v < 0 for v in last_two):
                        result.swing_trend = "DOWNTREND"
                    else:
                        result.swing_trend = "RANGING"

            # BOS (Break of Structure)
            bos = smc.bos_choch(df, swing_hl)
            if bos is not None and not bos.empty:
                bos_entries = bos[bos["BOS"].notna()].tail(3)
                if not bos_entries.empty:
                    last_bos = bos_entries.iloc[-1]
                    result.bos_detected = True
                    result.bos_direction = "BULLISH" if last_bos["BOS"] > 0 else "BEARISH"
                    result.bos_bars_ago = len(df) - bos_entries.index[-1] - 1

                # CHoCH (Change of Character)
                choch_entries = bos[bos["CHOCH"].notna()].tail(3)
                if not choch_entries.empty:
                    last_choch = choch_entries.iloc[-1]
                    result.choch_detected = True
                    result.choch_direction = "BULLISH" if last_choch["CHOCH"] > 0 else "BEARISH"

            # Order Blocks
            ob = smc.ob(df, swing_hl)
            if ob is not None and not ob.empty:
                active_obs = ob[ob["OB"].notna()].tail(3)
                if not active_obs.empty:
                    last_ob = active_obs.iloc[-1]
                    result.nearest_ob_price = float(last_ob.get("OBLow", 0) or 0)
                    result.nearest_ob_type = "BULLISH" if last_ob["OB"] > 0 else "BEARISH"
                    current_price = float(df["close"].iloc[-1])
                    if current_price > 0 and result.nearest_ob_price > 0:
                        result.ob_distance_pct = abs(
                            (current_price - result.nearest_ob_price) / current_price * 100
                        )

            # Fair Value Gaps
            fvg = smc.fvg(df)
            if fvg is not None and not fvg.empty:
                active_fvgs = fvg[fvg["FVG"].notna()].tail(3)
                if not active_fvgs.empty:
                    last_fvg = active_fvgs.iloc[-1]
                    result.fvg_active = True
                    result.fvg_direction = "BULLISH" if last_fvg["FVG"] > 0 else "BEARISH"
                    top = float(last_fvg.get("Top", 0) or 0)
                    bottom = float(last_fvg.get("Bottom", 0) or 0)
                    result.fvg_midpoint = (top + bottom) / 2 if top and bottom else 0.0

            # Liquidity sweeps
            liquidity = smc.liquidity(df, swing_hl)
            if liquidity is not None and not liquidity.empty:
                swept = liquidity[liquidity["Liquidity"].notna()].tail(3)
                if not swept.empty:
                    last_liq = swept.iloc[-1]
                    bars_since = len(df) - swept.index[-1] - 1
                    if bars_since <= 5:  # Recent sweep (within 5 bars)
                        result.liquidity_swept = True
                        result.liquidity_direction = (
                            "BULLISH" if last_liq["Liquidity"] > 0 else "BEARISH"
                        )

        except Exception as e:
            logger.error(f"SMCAdapter error: {e}", exc_info=True)

        logger.info(
            f"SMC: trend={result.swing_trend} BOS={result.bos_direction} "
            f"CHoCH={result.choch_detected} OB={result.nearest_ob_type} "
            f"FVG={result.fvg_active} LiqSwept={result.liquidity_swept}"
        )
        return result
