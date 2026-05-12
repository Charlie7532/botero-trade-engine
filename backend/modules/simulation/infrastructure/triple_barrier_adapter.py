"""
Triple Barrier Adapter — Oracle Labeling Infrastructure
==========================================================
Implements BarrierLabelerPort for the Oracle Backtester.
Uses ATR-based barriers with realistic execution modeling.

Execution Reality Model (Almgren-Chriss simplified):
    1. Entry at Open[T+delay] + volatility-adjusted slippage.
    2. Exit at barrier price minus adverse slippage.
    3. Round-trip costs (spread + commissions) deducted from return.
    Slippage = ATR × slippage_factor × √(1 / RVOL)
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
    """ATR-based Triple Barrier labeler with realistic execution modeling."""

    def label_entries(
        self,
        ohlc: pd.DataFrame,
        entries: pd.Series,
        profit_mult: float,
        loss_mult: float,
        max_bars: int,
        vol_lookback: int = 20,
        entry_delay_bars: int = 1,
        slippage_factor: float = 0.08,
        round_trip_cost_bps: float = 10.0,
    ) -> list[BarrierLabel]:
        """
        Apply Triple Barrier with Volatility-Adjusted Execution Price (VAEP).

        For each signal bar T:
        1. Compute ATR and RVOL at bar T (backward-looking, no leakage)
        2. Entry at Open[T+delay] + adverse slippage (VAEP)
        3. Walk forward from T+delay+1 checking barriers
        4. Exit with adverse slippage at barrier touch
        5. Deduct round-trip costs from final return
        """
        high = ohlc["high"]
        low = ohlc["low"]
        close = ohlc["close"]
        volume = ohlc["volume"]
        open_price = ohlc["open"]

        # ATR series (backward-looking)
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=vol_lookback, min_periods=1).mean()

        # Average volume for RVOL calculation (backward-looking)
        avg_volume = volume.rolling(window=vol_lookback, min_periods=1).mean()

        entry_indices = entries[entries].index
        results = []

        for entry_idx in entry_indices:
            pos = ohlc.index.get_loc(entry_idx)

            # ── EXECUTION DELAY ──────────────────────────────────
            # Signal fires after bar T closes. Fill happens at bar T+delay.
            exec_bar = pos + entry_delay_bars
            if exec_bar >= len(ohlc) - 1:
                continue

            entry_atr = float(atr.iloc[pos])
            if entry_atr <= 0:
                continue

            # ── RVOL at signal bar (backward-looking) ────────────
            signal_vol = float(volume.iloc[pos])
            avg_vol = float(avg_volume.iloc[pos])
            rvol = signal_vol / max(avg_vol, 1.0)

            # ── VAEP: Volatility-Adjusted Execution Price ────────
            # Slippage increases with volatility, decreases with liquidity
            raw_open = float(open_price.iloc[exec_bar])
            slippage = entry_atr * slippage_factor * (1.0 / max(rvol, 0.3)) ** 0.5
            entry_price = raw_open + slippage  # Adverse for long entries

            if entry_price <= 0:
                continue

            # ── BARRIERS from actual fill price ──────────────────
            upper = entry_price + entry_atr * profit_mult
            lower = entry_price - entry_atr * loss_mult

            # ── WALK FORWARD from exec_bar + 1 ───────────────────
            label = 0
            ret = 0.0
            bars = 0
            hit = "time"
            exit_slippage = entry_atr * slippage_factor * 0.5  # Half of entry slippage

            for bar in range(1, min(max_bars + 1, len(ohlc) - exec_bar)):
                bar_pos = exec_bar + bar
                bar_high = float(high.iloc[bar_pos])
                bar_low = float(low.iloc[bar_pos])
                bar_close = float(close.iloc[bar_pos])

                # Check upper barrier (profit) — exit with adverse slippage
                if bar_high >= upper:
                    actual_exit = upper - exit_slippage
                    label = 1
                    ret = (actual_exit - entry_price) / entry_price * 100
                    bars = bar
                    hit = "profit"
                    break

                # Check lower barrier (loss) — exit with adverse slippage
                if bar_low <= lower:
                    actual_exit = lower + exit_slippage  # Worse than barrier
                    label = -1
                    ret = (actual_exit - entry_price) / entry_price * 100
                    bars = bar
                    hit = "loss"
                    break

                bars = bar
                ret = (bar_close - entry_price) / entry_price * 100

            # ── DEDUCT ROUND-TRIP COSTS ──────────────────────────
            ret -= round_trip_cost_bps / 100.0

            # Timestamps for purging/embargo
            signal_time = entry_idx
            exit_bar_pos = min(exec_bar + bars, len(ohlc) - 1)
            exit_time = ohlc.index[exit_bar_pos]

            results.append(BarrierLabel(
                label=label,
                return_pct=round(ret, 4),
                bars_held=bars,
                hit_barrier=hit,
                entry_time=signal_time,
                exit_time=exit_time,
                entry_price=round(entry_price, 4),
            ))

        logger.info(
            f"TripleBarrier: {len(results)} entries labeled "
            f"(profit={sum(1 for r in results if r.label == 1)}, "
            f"loss={sum(1 for r in results if r.label == -1)}, "
            f"time={sum(1 for r in results if r.label == 0)}) "
            f"[delay={entry_delay_bars}bar, slip={slippage_factor:.0%}ATR, "
            f"cost={round_trip_cost_bps:.0f}bps]"
        )
        return results
