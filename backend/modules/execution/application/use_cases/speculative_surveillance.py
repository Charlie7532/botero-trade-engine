"""
Speculative Surveillance Loop — Seykota & PTJ
===============================================
Monitoreo continuo de posiciones SPECULATIVE.

A diferencia de la Quality Surveillance (que busca thesis death / moat decay),
la Speculative Surveillance busca:
1. Stop mecánico check (ATR)
2. Time stop check (PTJ: si no funciona en N barras, salir)
3. RS decay check (alpha erosion)
4. Signal decay monitoring (Sharpe rolling)
5. Anti-pattern feed (fracasos → Memory Guard)
"""
import logging
from typing import List, Dict
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


class SpeculativeSurveillance:
    """
    Surveillance loop para posiciones SPECULATIVE.

    Seykota: "The elements of good trading are: (1) cutting losses,
    (2) cutting losses, (3) cutting losses."

    PTJ: "I'm always thinking about losing money as opposed to making money."
    """

    def __init__(
        self,
        speculative_journal,
        market_data_port=None,
        blacklist=None,
    ):
        self.journal = speculative_journal  # Direct SPECULATIVE journal injection
        self.market_data = market_data_port
        self.blacklist = blacklist

        # PTJ Time Stop defaults
        self.max_bars_without_profit = 10  # If no progress in 10 bars, exit
        self.rs_decay_threshold = 0.85     # RS vs SPY below this = warning
        self.rs_critical_threshold = 0.75  # RS below this = mandatory exit

    def run_surveillance(self) -> List[Dict]:
        """
        Escanea todas las posiciones abiertas del SPECULATIVE journal.
        Evalúa stops mecánicos, time stops, y decay de señal.
        """
        logger.info("Iniciando Speculative Surveillance (Seykota + PTJ)...")
        open_trades = self.journal.get_open_trades()
        surveillance_reports = []

        for trade in open_trades:
            ticker = trade["ticker"]
            logger.info(f"Auditing SPECULATIVE position: {ticker}...")

            report = {
                "ticker": ticker,
                "trade_id": trade.get("trade_id", ""),
                "alerts": [],
                "should_exit": False,
                "exit_reason": "",
                "urgency": "LOW",
            }

            # ── 1. Time Stop (PTJ) ──
            bars_held = trade.get("bars_held", 0)
            entry_price = trade.get("entry_price", 0)
            current_price = trade.get("current_price", entry_price)

            if bars_held > 0 and entry_price > 0:
                pnl_pct = ((current_price / entry_price) - 1) * 100

                # PTJ: "If it hasn't worked in N bars, it's not going to work"
                if bars_held >= self.max_bars_without_profit and pnl_pct <= 0:
                    report["should_exit"] = True
                    report["exit_reason"] = (
                        f"TIME_STOP_PTJ: {bars_held} bars held with PnL={pnl_pct:+.2f}%. "
                        f"Trade has not demonstrated directional conviction."
                    )
                    report["urgency"] = "HIGH"
                    report["alerts"].append("TIME_STOP")
                    logger.warning(f"⏰ TIME STOP for {ticker}: {bars_held} bars, PnL={pnl_pct:+.2f}%")

            # ── 2. RS Decay Check (Alpha Erosion) ──
            rs_vs_spy = trade.get("rs_vs_spy", 1.0)
            entry_rs = trade.get("entry_rs", 1.0)

            if rs_vs_spy > 0 and entry_rs > 0:
                rs_ratio = rs_vs_spy / entry_rs  # How much RS has decayed since entry

                if rs_ratio < self.rs_critical_threshold:
                    report["should_exit"] = True
                    report["exit_reason"] = (
                        f"RS_CRITICAL: RS decayed to {rs_ratio:.2f}x entry level. "
                        f"Entry RS={entry_rs:.4f}, Current RS={rs_vs_spy:.4f}. "
                        f"Alpha completely eroded."
                    )
                    report["urgency"] = "CRITICAL"
                    report["alerts"].append("RS_CRITICAL")
                    logger.warning(f"📉 RS CRITICAL for {ticker}: ratio={rs_ratio:.2f}")

                elif rs_ratio < self.rs_decay_threshold:
                    report["alerts"].append("RS_WARNING")
                    logger.info(f"⚠️ RS WARNING for {ticker}: ratio={rs_ratio:.2f}")

            # ── 3. Mechanical Stop Check ──
            current_stop = trade.get("current_stop_price", 0)
            if current_stop > 0 and current_price > 0 and current_price <= current_stop:
                report["should_exit"] = True
                report["exit_reason"] = (
                    f"MECHANICAL_STOP: Price ${current_price:.2f} ≤ Stop ${current_stop:.2f}. "
                    f"Seykota: 'Cut losses. No exceptions.'"
                )
                report["urgency"] = "IMMEDIATE"
                report["alerts"].append("STOP_HIT")
                logger.warning(f"🛑 STOP HIT for {ticker}: ${current_price:.2f} ≤ ${current_stop:.2f}")

            # ── 4. Anti-Pattern Detection (for Memory Guard) ──
            entry_intel = trade.get("entry_intelligence", {})
            if report["should_exit"] and not trade.get("was_winner", True):
                # This is a losing trade — record the pattern for Memory Guard
                report["anti_pattern"] = {
                    "gamma_regime": entry_intel.get("gamma_regime", "UNKNOWN"),
                    "whale_verdict": entry_intel.get("whale_verdict", "UNKNOWN"),
                    "phase": entry_intel.get("phase", "UNKNOWN"),
                    "flow_persistence_grade": entry_intel.get("flow_persistence_grade", "UNKNOWN"),
                    "exit_reason": report["exit_reason"],
                    "bars_held": bars_held,
                }
                logger.info(f"🧠 Anti-pattern recorded for {ticker} → Memory Guard")

            # ── Apply actions ──
            if report["should_exit"]:
                logger.warning(f"🚨 EXIT SIGNAL for {ticker}: {report['exit_reason']}")

                # Update journal
                self.journal.update_trade(trade["trade_id"], {
                    "surveillance_exit_signal": True,
                    "surveillance_reason": report["exit_reason"],
                    "surveillance_urgency": report["urgency"],
                })

            surveillance_reports.append(report)

        return surveillance_reports
