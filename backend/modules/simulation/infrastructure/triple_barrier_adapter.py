"""
Triple Barrier Adapter — Oracle Labeling Infrastructure
==========================================================
Implements BarrierLabelerPort for the Oracle Backtester.
Uses ATR-based barriers: profit, loss, and time exit.

Migrated from legacy backtrader scaffold — no PyTorch dependency.
"""
import logging

import numpy as np
import pandas as pd

from backend.modules.simulation.domain.ports.barrier_labeler_port import (
    BarrierLabelerPort,
    BarrierLabel,
)

logger = logging.getLogger(__name__)


class TripleBarrierAdapter(BarrierLabelerPort):
    """ATR-based Triple Barrier labeler for Oracle evaluation."""

    def label_entries(
        self,
        ohlc: pd.DataFrame,
        entries: pd.Series,
        profit_mult: float,
        loss_mult: float,
        max_bars: int,
        vol_lookback: int = 20,
    ) -> list[BarrierLabel]:
        """
        Apply Triple Barrier to each entry point.

        For each entry bar:
        1. Calculate ATR at that point (vol_lookback window)
        2. Set upper barrier = close + ATR * profit_mult
        3. Set lower barrier = close - ATR * loss_mult
        4. Walk forward up to max_bars
        5. Record which barrier was hit first
        """
        # Calculate ATR series
        high = ohlc["high"]
        low = ohlc["low"]
        close = ohlc["close"]

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        atr = tr.rolling(window=vol_lookback, min_periods=1).mean()

        # Get entry indices
        entry_indices = entries[entries].index
        results = []

        for entry_idx in entry_indices:
            pos = ohlc.index.get_loc(entry_idx)

            if pos >= len(ohlc) - 1:
                continue

            entry_price = float(close.iloc[pos])
            entry_atr = float(atr.iloc[pos])

            if entry_atr <= 0 or entry_price <= 0:
                continue

            upper = entry_price + entry_atr * profit_mult
            lower = entry_price - entry_atr * loss_mult

            # Walk forward
            label = 0
            ret = 0.0
            bars = 0
            hit = "time"

            for bar in range(1, min(max_bars + 1, len(ohlc) - pos)):
                bar_high = float(high.iloc[pos + bar])
                bar_low = float(low.iloc[pos + bar])
                bar_close = float(close.iloc[pos + bar])

                # Check upper barrier (profit)
                if bar_high >= upper:
                    label = 1
                    ret = (upper - entry_price) / entry_price * 100
                    bars = bar
                    hit = "profit"
                    break

                # Check lower barrier (loss)
                if bar_low <= lower:
                    label = -1
                    ret = (lower - entry_price) / entry_price * 100
                    bars = bar
                    hit = "loss"
                    break

                bars = bar
                ret = (bar_close - entry_price) / entry_price * 100

            results.append(BarrierLabel(
                label=label,
                return_pct=round(ret, 4),
                bars_held=bars,
                hit_barrier=hit,
            ))

        logger.info(
            f"TripleBarrier: {len(results)} entries labeled "
            f"(profit={sum(1 for r in results if r.label == 1)}, "
            f"loss={sum(1 for r in results if r.label == -1)}, "
            f"time={sum(1 for r in results if r.label == 0)})"
        )
        return results
