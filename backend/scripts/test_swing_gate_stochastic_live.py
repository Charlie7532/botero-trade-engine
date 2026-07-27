#!/usr/bin/env python3
"""
Test Live Quality Swing Gate with Stochastic Real EV Rules Engine
===================================================================
Evaluates SwingGate over historical OHLCV bars from TimescaleDB (Neon Vault)
to verify that stochastic Real EV rules generate active action codes:
  - STK_ACCUMULATE_STRUCTURAL
  - STK_BUY_DIP_TACTICAL
  - STK_TRIM_TACTICAL
  - STK_HOLD_STABLE / STK_HOLD_NEUTRAL
"""
import sys, logging
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.application.use_cases.swing_gate import SwingGate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TestSwingGateStochasticLive")

def main():
    store = TimescaleDataStore()
    gate = SwingGate(data_port=store)

    tickers = ["AAPL", "MSFT", "AMZN", "COST", "SPY"]
    summary = {t: {} for t in tickers}

    for ticker in tickers:
        logger.info(f"--- Evaluando SwingGate para {ticker} ---")
        decision = gate.evaluate(ticker)
        action = decision.action_code
        urgency = decision.urgency_level
        conviction = decision.conviction
        reasoning = decision.reasoning
        
        logger.info(f"Ticker {ticker}: Action={action}, Urgency={urgency}, Conviction={conviction:.2f}")
        logger.info(f"Reasoning: {reasoning}")
        summary[ticker] = {
            "action": action,
            "urgency": urgency,
            "conviction": conviction,
            "reasoning": reasoning
        }

    print("\n" + "="*80)
    print("RESUMEN DE EVALUACIÓN ESTOCÁSTICA DE SWING GATE EN EL VAULT (LIVE)")
    print("="*80)
    for ticker, res in summary.items():
        print(f"Ticker: {ticker:6s} | Action: {res['action']:26s} | Conviction: {res['conviction']:.2f} | Urgency: {res['urgency']}")
        print(f"  Reasoning: {res['reasoning']}\n")

if __name__ == "__main__":
    main()
