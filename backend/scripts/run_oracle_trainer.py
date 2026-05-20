#!/usr/bin/env python3
"""
Oracle Forensic Laboratory Runner Script.
Executes deep historical backtests on signal adapters using TimescaleDataStore,
evaluates entry (+1) and exit (-1) performance independently, diagnoses failures (Dalio),
and persists the forensic records to Neon PostgreSQL.
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Setup path and load .env
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.simulation.infrastructure.neon_forensic_store import NeonForensicStore
from backend.modules.simulation.application.use_cases.oracle_trainer import OracleTrainer

# Import Signal Adapters
from backend.modules.simulation.infrastructure.signal_adapters import (
    RSISignalAdapter,
    RegressionChannelAdapter,
    KalmanSignalAdapter,
    MeanReversionSignalAdapter,
    VolumeQualitySignalAdapter,
    FlowSignalAdapter,
    BOSSignalAdapter,
    PatternSignalAdapter,
)

# Setup beautiful console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("oracle_runner")

ADAPTER_MAP = {
    "rsi_intelligence": RSISignalAdapter,
    "regression_channel": RegressionChannelAdapter,
    "kalman_wyckoff": KalmanSignalAdapter,
    "mean_reversion": MeanReversionSignalAdapter,
    "volume_quality": VolumeQualitySignalAdapter,
    "flow_persistence": FlowSignalAdapter,
    "bos_choch": BOSSignalAdapter,
    "pattern_recognition": PatternSignalAdapter,
}

def generate_progress_bar(pct: float, width: int = 20) -> str:
    """Generate a clean ASCII progress bar using solid blocks."""
    if not (0.0 <= pct <= 100.0) or pd.isna(pct):
        return " " * width
    num_blocks = int(round(pct / 100.0 * width))
    return "█" * num_blocks + " " * (width - num_blocks)

def format_entry_card(card) -> str:
    """Format an EntryReportCard into the beautiful ASCII box defined in the plan."""
    n_signals = card.n_signals
    if n_signals == 0:
        return f"║  🟢 {card.ticker} × {card.signal_name} — No signals found                 ║"

    # Classifications
    c_dist = card.classification_dist or {}
    c_pct = card.classification_pct or {}
    
    # Failures
    f_pct = card.foreseeable_pct
    f_breakdown = card.failure_breakdown or {}
    f_total = sum(f_breakdown.values())
    
    # Foreseeability breakdown
    fore_breakdown = card.foreseeability_breakdown or {}
    
    # Fear levels
    golden_by_fear = card.golden_rate_by_fear or {}

    out = []
    out.append("╔══════════════════════════════════════════════════════════════╗")
    out.append(f"║  🟢 {card.signal_name.upper()} × {card.ticker.upper()} — ENTRY ReportCard" + " " * (43 - len(card.signal_name) - len(card.ticker)) + "║")
    out.append(f"║  ({n_signals} señales +1 evaluadas, 20 años)                         ║")
    out.append("╠══════════════════════════════════════════════════════════════╣")
    out.append("║  CLASIFICACIÓN:                                              ║")
    
    for cls_name in ["GOLDEN_RUN", "SOLID_MOVE", "SLOW_GRIND", "MISS", "TRAP", "FALSE_SIGNAL"]:
        count = c_dist.get(cls_name, 0)
        pct = c_pct.get(cls_name, 0.0)
        bar = generate_progress_bar(pct, width=20)
        line = f"║    {cls_name:<13} {count:>4} ({pct:>5.1f}%) {bar} ║"
        out.append(line)
        
    out.append("║                                                              ║")
    out.append("║  MÉTRICAS DE ENTRADA:                                        ║")
    out.append(f"║    Golden Rate:     {card.golden_rate:>5.1f}% (GOLDEN + SOLID)                   ║")
    out.append(f"║    Trap Rate:       {card.trap_rate:>5.1f}%                                    ║")
    out.append(f"║    False Rate:      {card.false_rate:>5.1f}%                                    ║")
    out.append(f"║    Edge Ratio H=10: {card.edge_ratio_10:>5.2f} (MFE/MAE)                          ║")
    out.append(f"║    Avg MFE(10):    {card.avg_mfe_10:>+5.1f}%                                     ║")
    out.append(f"║    Avg MAE(10):    {card.avg_mae_10:>+5.1f}%                                     ║")
    out.append("║                                                              ║")
    out.append("║  WIN RATE POR HORIZONTE:                                     ║")
    
    h3 = card.wr_by_horizon.get(3, 0.0)
    h5 = card.wr_by_horizon.get(5, 0.0)
    h10 = card.wr_by_horizon.get(10, 0.0)
    h20 = card.wr_by_horizon.get(20, 0.0)
    h40 = card.wr_by_horizon.get(40, 0.0)
    
    out.append(f"║    H=3:  {h3:>4.1f}%  │  H=5:  {h5:>4.1f}%  │  H=10: {h10:>4.1f}%             ║")
    out.append(f"║    H=20: {h20:>4.1f}%  │  H=40: {h40:>4.1f}%                              ║")
    out.append("║                                                              ║")
    out.append(f"║  DIAGNÓSTICO DE FALLOS ({f_total} failures):                        ║")
    
    fore_n = fore_breakdown.get("FORESEEABLE", 0)
    fore_p = (fore_n / f_total * 100) if f_total > 0 else 0.0
    out.append(f"║    🟢 FORESEEABLE:        {fore_n:>3} ({fore_p:>4.1f}%)                         ║")
    
    # Sort failure types by count
    sorted_failures = sorted(f_breakdown.items(), key=lambda x: x[1], reverse=True)
    for f_type, f_count in sorted_failures[:5]:
        f_pct_val = (f_count / f_total * 100) if f_total > 0 else 0.0
        f_bar = generate_progress_bar(f_pct_val, width=15)
        out.append(f"║       {f_type:<20}: {f_count:>3} {f_bar}    ║")
        
    part_n = fore_breakdown.get("PARTIALLY", 0)
    part_p = (part_n / f_total * 100) if f_total > 0 else 0.0
    out.append(f"║    ⚠️ PARTIALLY:            {part_n:>3} ({part_p:>4.1f}%)                        ║")
    
    unfore_n = fore_breakdown.get("UNFORESEEABLE", 0)
    unfore_p = (unfore_n / f_total * 100) if f_total > 0 else 0.0
    out.append(f"║    🔴 UNFORESEEABLE:        {unfore_n:>3} ({unfore_p:>4.1f}%)                        ║")
    out.append("║                                                              ║")
    out.append("║  GOLDEN RATE POR RÉGIMEN (FEAR LEVEL):                       ║")
    
    for fl_label in ["PANIC", "FEAR", "ANXIETY", "NEUTRAL", "GREED"]:
        fl_pct = golden_by_fear.get(fl_label, 0.0)
        fl_bar = generate_progress_bar(fl_pct, width=20)
        out.append(f"║    {fl_label:<10} {fl_pct:>5.1f}% {fl_bar} ║")
        
    out.append("║                                                              ║")
    verdict_str = f"► GRADE: {card.grade}  │  VERDICT: {card.verdict}"
    out.append(f"║  {verdict_str:<58} ║")
    out.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(out)

def format_exit_card(card) -> str:
    """Format an ExitReportCard into the beautiful ASCII box defined in the plan."""
    n_signals = card.n_signals
    if n_signals == 0:
        return f"║  🔴 {card.ticker} × {card.signal_name} — No signals found                 ║"

    # Classifications
    c_dist = card.classification_dist or {}
    c_pct = card.classification_pct or {}
    
    # Failures
    f_pct = card.foreseeable_pct
    f_breakdown = card.failure_breakdown or {}
    f_total = sum(f_breakdown.values())
    
    # Foreseeability breakdown
    fore_breakdown = card.foreseeability_breakdown or {}
    
    # Fear levels
    save_by_fear = card.save_rate_by_fear or {}

    out = []
    out.append("╔══════════════════════════════════════════════════════════════╗")
    out.append(f"║  🔴 {card.signal_name.upper()} × {card.ticker.upper()} — EXIT ReportCard" + " " * (44 - len(card.signal_name) - len(card.ticker)) + "║")
    out.append(f"║  ({n_signals} señales -1 evaluadas, 20 años)                         ║")
    out.append("╠══════════════════════════════════════════════════════════════╣")
    out.append("║  CLASIFICACIÓN:                                              ║")
    
    for cls_name in ["SAVED_US", "GOOD_WARNING", "EARLY_BUT_RIGHT", "NEUTRAL_EXIT", "FALSE_ALARM", "MISSED_UPSIDE"]:
        count = c_dist.get(cls_name, 0)
        pct = c_pct.get(cls_name, 0.0)
        bar = generate_progress_bar(pct, width=20)
        line = f"║    {cls_name:<16} {count:>3} ({pct:>5.1f}%) {bar} ║"
        out.append(line)
        
    out.append("║                                                              ║")
    out.append("║  MÉTRICAS DE SALIDA:                                         ║")
    out.append(f"║    Save Rate:        {card.save_rate:>5.1f}% (SAVED + WARNING)                 ║")
    out.append(f"║    False Alarm Rate: {card.false_alarm_rate:>5.1f}%                                   ║")
    out.append(f"║    Missed Upside:    {card.missed_upside_rate:>5.1f}%                                   ║")
    out.append(f"║    Net Exit Value:   {card.net_exit_value:>+5.1f}% (pérdida evitada - ganancia       ║")
    out.append("║                             perdida = neto positivo = AYUDA) ║")
    out.append(f"║    Cost of FA:       {card.cost_of_false_alarms:>+5.1f}% avg return perdido                ║")
    out.append(f"║    Cost of MU:       {card.cost_of_missed_upside:>+5.1f}% avg return perdido                ║")
    out.append("║                                                              ║")
    out.append("║  PÉRDIDA EVITADA POR HORIZONTE:                              ║")
    
    h3 = card.avg_avoided_loss.get(3, 0.0)
    h5 = card.avg_avoided_loss.get(5, 0.0)
    h10 = card.avg_avoided_loss.get(10, 0.0)
    h20 = card.avg_avoided_loss.get(20, 0.0)
    h40 = card.avg_avoided_loss.get(40, 0.0)
    
    out.append(f"║    H=3:  {h3:>+5.1f}%  │  H=5:  {h5:>+5.1f}%  │  H=10: {h10:>+5.1f}%             ║")
    out.append(f"║    H=20: {h20:>+5.1f}%  │  H=40: {h40:>+5.1f}%                              ║")
    out.append("║                                                              ║")
    out.append(f"║  DIAGNÓSTICO DE FALLOS ({f_total} exit failures):                   ║")
    
    fore_n = fore_breakdown.get("FORESEEABLE", 0)
    fore_p = (fore_n / f_total * 100) if f_total > 0 else 0.0
    out.append(f"║    🟢 FORESEEABLE:        {fore_n:>3} ({fore_p:>4.1f}%)                         ║")
    
    sorted_failures = sorted(f_breakdown.items(), key=lambda x: x[1], reverse=True)
    for f_type, f_count in sorted_failures[:5]:
        f_pct_val = (f_count / f_total * 100) if f_total > 0 else 0.0
        f_bar = generate_progress_bar(f_pct_val, width=15)
        out.append(f"║       {f_type:<20}: {f_count:>3} {f_bar}    ║")
        
    part_n = fore_breakdown.get("PARTIALLY", 0)
    part_p = (part_n / f_total * 100) if f_total > 0 else 0.0
    out.append(f"║    ⚠️ PARTIALLY:            {part_n:>3} ({part_p:>4.1f}%)                        ║")
    
    unfore_n = fore_breakdown.get("UNFORESEEABLE", 0)
    unfore_p = (unfore_n / f_total * 100) if f_total > 0 else 0.0
    out.append(f"║    🔴 UNFORESEEABLE:        {unfore_n:>3} ({unfore_p:>4.1f}%)                        ║")
    out.append("║                                                              ║")
    out.append("║  SAVE RATE POR RÉGIMEN (FEAR LEVEL):                         ║")
    
    for fl_label in ["PANIC", "FEAR", "ANXIETY", "NEUTRAL", "GREED"]:
        fl_pct = save_by_fear.get(fl_label, 0.0)
        fl_bar = generate_progress_bar(fl_pct, width=20)
        out.append(f"║    {fl_label:<10} {fl_pct:>5.1f}% {fl_bar} ║")
        
    out.append("║                                                              ║")
    verdict_str = f"► GRADE: {card.grade}  │  VERDICT: {card.verdict}"
    out.append(f"║  {verdict_str:<58} ║")
    out.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(out)

def main():
    parser = argparse.ArgumentParser(description="Oracle Training Forensic Backtest Lab")
    parser.add_argument(
        "--mode",
        choices=["entry", "exit", "both"],
        default="both",
        help="Evaluation direction mode. (default: both)"
    )
    parser.add_argument(
        "--tickers",
        default="SPY,QQQ,AAPL,COST",
        help="Comma-separated ticker list to backtest. (default: SPY,QQQ,AAPL,COST)"
    )
    parser.add_argument(
        "--signals",
        default="rsi_intelligence,regression_channel",
        help="Comma-separated signal adapter list. (default: rsi_intelligence,regression_channel)"
    )
    parser.add_argument(
        "--timeframe",
        default="1d",
        help="Timeframe to use. (default: 1d)"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Persist forensic labels and cards to Neon DB. (default: True)"
    )
    
    args = parser.parse_args()
    
    # 1. Connect to Neon Vault & Forensic Store
    pg_url = os.environ.get("POSTGRES_URL", "")
    if not pg_url:
        logger.error("POSTGRES_URL environment variable is not set. Please set it in .env.")
        sys.exit(1)
        
    logger.info("Initializing TimescaleDataStore and NeonForensicStore interfaces...")
    store = TimescaleDataStore(dsn=pg_url)
    forensic_store = NeonForensicStore(dsn=pg_url)
    
    # 2. Instantiate core OracleTrainer Use Case
    trainer = OracleTrainer(store=store)
    
    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    signals = [s.strip().lower() for s in args.signals.split(",")]
    
    logger.info(f"Target Tickers: {tickers}")
    logger.info(f"Target Signals: {signals}")
    logger.info(f"Target Mode: {args.mode.upper()}")
    
    # 3. Execution loop
    for ticker in tickers:
        for signal_name in signals:
            if signal_name not in ADAPTER_MAP:
                logger.error(f"Signal Adapter '{signal_name}' is not registered in ADAPTER_MAP. Skipping.")
                continue
                
            adapter_class = ADAPTER_MAP[signal_name]
            adapter_instance = adapter_class()
            
            logger.info(f"Executing Oracle laboratory for {ticker} using {signal_name} on {args.timeframe}...")
            
            # --- EVALUATE ENTRIES (+1) ---
            if args.mode in ("entry", "both"):
                try:
                    labels, card = trainer.evaluate_entries(
                        ticker=ticker,
                        tf=args.timeframe,
                        signal_name=signal_name,
                        adapter=adapter_instance
                    )
                    
                    # Print beautiful ASCII report
                    print("\n" + format_entry_card(card) + "\n")
                    
                    # Persist to database
                    if args.save and labels and card.n_signals > 0:
                        logger.info(f"Persisting {len(labels)} entry labels to database...")
                        forensic_store.save_entry_labels(labels)
                        logger.info(f"Persisting entry report card to database...")
                        forensic_store.save_entry_report_card(card)
                        logger.info("Database persistence completed.")
                except Exception as e:
                    logger.error(f"Error executing entry evaluation for {ticker} / {signal_name}: {e}", exc_info=True)
                    
            # --- EVALUATE EXITS (-1) ---
            if args.mode in ("exit", "both"):
                try:
                    labels, card = trainer.evaluate_exits(
                        ticker=ticker,
                        tf=args.timeframe,
                        signal_name=signal_name,
                        adapter=adapter_instance
                    )
                    
                    # Print beautiful ASCII report
                    print("\n" + format_exit_card(card) + "\n")
                    
                    # Persist to database
                    if args.save and labels and card.n_signals > 0:
                        logger.info(f"Persisting {len(labels)} exit labels to database...")
                        forensic_store.save_exit_labels(labels)
                        logger.info(f"Persisting exit report card to database...")
                        forensic_store.save_exit_report_card(card)
                        logger.info("Database persistence completed.")
                except Exception as e:
                    logger.error(f"Error executing exit evaluation for {ticker} / {signal_name}: {e}", exc_info=True)
                    
    # Clean connection pools
    store.close()
    logger.info("Oracle laboratory run completed successfully! 🧪🔬🎉")

if __name__ == "__main__":
    main()
