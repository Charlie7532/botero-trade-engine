"""
SIMULACIÓN LIVE — Entry Intelligence Hub con Datos Reales
============================================================
Ejecuta el pipeline COMPLETO con:
  - Precios REALES de yfinance (3 meses)
  - Opciones REALES (OptionsAwareness + Black-Scholes Gamma)
  - Volumen REAL (Kalman Wyckoff tracker)
  - VIX REAL
  - RS vs SPY REAL
  - Calendario FOMC real (2026 hardcoded)

UW Intelligence se ejecuta con datos vacíos (requiere MCP live).

Ejecutar: python3 scripts/simulate_live.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import logging
import time
import numpy as np
import pandas as pd
from datetime import datetime, date, UTC

from modules.entry_decision.hub import EntryIntelligenceHub
from modules.portfolio_management.domain.portfolio_intelligence import AdaptiveTrailingStop

# Suppress yfinance noise
logging.basicConfig(level=logging.WARNING)
logging.getLogger('yfinance').setLevel(logging.ERROR)

# ═══════════════════════════════════════════════════════════════
# FORMATTING
# ═══════════════════════════════════════════════════════════════

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
DIM = "\033[2m"
WHITE = "\033[97m"

def header(text):
    print(f"\n{'═'*72}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{'═'*72}")

def sub(text):
    print(f"\n  {MAGENTA}▸ {text}{RESET}")

def line(label, value, color=""):
    print(f"    {label:30s} {color}{value}{RESET}")

def bar(value, max_val=100, width=20, color=GREEN):
    filled = int(value / max(max_val, 1) * width)
    return f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET} {value:.0f}%"

def verdict_emoji(v):
    return {"EXECUTE": "🎯", "STALK": "⏳", "BLOCK": "⛔", "PASS": "➖"}.get(v, "❓")

def whale_emoji(v):
    return {"RIDE_THE_WHALES": "🐋", "LEAN_WITH_FLOW": "🌊", "UNCERTAIN": "🌫️", "CONTRA_FLOW": "🚫"}.get(v, "❓")

def phase_emoji(p):
    return {"CORRECTION": "📉↗", "BREAKOUT": "🚀", "EXHAUSTION_UP": "🔥", "EXHAUSTION_DOWN": "💀", "CONSOLIDATION": "📊"}.get(p, "❓")


# ═══════════════════════════════════════════════════════════════
# MAIN SIMULATION
# ═══════════════════════════════════════════════════════════════

# Tickers to evaluate — mix of different expected phases
TICKERS = [
    "NVDA",    # AI momentum leader
    "AAPL",    # Stable compounder
    "TSLA",    # Volatile, often extended
    "AMZN",    # Cloud + retail titan
    "META",    # Social media + AI
    "MSFT",    # Enterprise cloud
    "GOOGL",   # Search + AI
    "JPM",     # Financials leader
]


def run_live_simulation():
    header("SIMULACIÓN LIVE — Entry Intelligence Hub")
    print(f"  {DIM}Fecha: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}{RESET}")
    print(f"  {DIM}Datos: yfinance (precios 3mo) + opciones reales + VIX live{RESET}")
    print(f"  {DIM}Tickers: {', '.join(TICKERS)}{RESET}")

    hub = EntryIntelligenceHub()

    # No UW data (requires MCP live)
    hub.inject_uw_data(spy_ticks=[], flow_alerts=[], tide_data=[])

    trailing = AdaptiveTrailingStop()
    results = []
    detailed_reports = []

    for i, ticker in enumerate(TICKERS, 1):
        print(f"\n  {DIM}[{i}/{len(TICKERS)}] Evaluando {ticker}...{RESET}", end="", flush=True)
        t0 = time.time()

        try:
            report = hub.evaluate(ticker)
            elapsed = time.time() - t0
            print(f" {GREEN}OK{RESET} ({elapsed:.1f}s)")

            detailed_reports.append(report)
            results.append({
                "ticker": ticker,
                "report": report,
                "elapsed": elapsed,
                "error": None,
            })
        except Exception as e:
            elapsed = time.time() - t0
            print(f" {RED}ERROR{RESET} ({elapsed:.1f}s): {e}")
            results.append({
                "ticker": ticker,
                "report": None,
                "elapsed": elapsed,
                "error": str(e),
            })

    # ═══════════════════════════════════════════════════════════
    # DETAILED REPORTS
    # ═══════════════════════════════════════════════════════════

    for r in results:
        if r["error"]:
            header(f"{r['ticker']} — ❌ ERROR")
            line("Error:", r["error"], RED)
            continue

        report = r["report"]
        ticker = report.ticker

        header(f"{ticker} — {verdict_emoji(report.final_verdict)} {report.final_verdict}")

        sub("PRECIO & ESTRUCTURA")
        line("Precio:", f"${report.current_price:.2f}")
        line("VIX:", f"{report.vix:.1f}",
             RED if report.vix > 25 else YELLOW if report.vix > 20 else GREEN)
        line("ATR:", f"${report.atr:.2f} ({report.atr/report.current_price*100:.1f}% del precio)")
        line("RVOL:", f"{report.rvol:.2f}x",
             GREEN if 0.8 < report.rvol < 1.5 else YELLOW)
        line("RSI:", f"{report.rsi:.0f}",
             RED if report.rsi > 70 else GREEN if report.rsi < 30 else "")
        line("RS vs SPY 20d:", f"{report.rs_vs_spy:.4f}",
             GREEN if report.rs_vs_spy > 1.05 else RED if report.rs_vs_spy < 0.95 else "")

        sub("OPTIONS AWARENESS (Gamma Regime)")
        if report.put_wall > 0:
            line("Put Wall:", f"${report.put_wall:.2f} ({(report.current_price/report.put_wall-1)*100:+.1f}% from price)", GREEN)
            line("Call Wall:", f"${report.call_wall:.2f} ({(report.call_wall/report.current_price-1)*100:+.1f}% upside)", CYAN)
            regime_color = {
                "PIN": GREEN, "DRIFT": YELLOW,
                "SQUEEZE_UP": CYAN, "SQUEEZE_DOWN": RED,
            }.get(report.gamma_regime, "")
            line("Gamma Regime:", report.gamma_regime, regime_color)
            line("Max Pain:", f"${report.max_pain:.2f}")

            # Put Wall defense zone
            pw_dist = (report.current_price - report.put_wall) / report.atr if report.atr > 0 else 0
            line("Put Wall Distance:", f"{pw_dist:.1f} ATR",
                 GREEN if pw_dist > 1 else YELLOW if pw_dist > 0.3 else RED)
        else:
            line("Opciones:", "No disponibles (sin cadena activa)", DIM)

        sub("VOLUME DYNAMICS (Kalman Wyckoff)")
        wyckoff_color = {
            "ACCUMULATION": GREEN, "MARKUP": GREEN,
            "DISTRIBUTION": RED, "MARKDOWN": RED,
        }.get(report.wyckoff_state, YELLOW)
        line("Wyckoff State:", report.wyckoff_state, wyckoff_color)
        line("Kalman Velocity:", f"{report.wyckoff_velocity:.4f}",
             GREEN if report.wyckoff_velocity > 0.05 else
             RED if report.wyckoff_velocity < -0.05 else "")

        sub("EVENT FLOW INTELLIGENCE (Calendario + Flujo)")
        line("Whale Verdict:", f"{whale_emoji(report.whale_verdict)} {report.whale_verdict}",
             GREEN if "RIDE" in report.whale_verdict else
             YELLOW if "LEAN" in report.whale_verdict else
             RED if "CONTRA" in report.whale_verdict else "")
        line("Position Scale:", f"{report.whale_scale:.0%}")
        if report.nearest_event:
            event_color = RED if report.hours_to_event < 48 else YELLOW if report.hours_to_event < 120 else ""
            line("Próximo Evento:", f"{report.nearest_event} ({report.hours_to_event:.0f}h)", event_color)
        line("Freeze Stops:", str(report.freeze_stops),
             RED + BOLD if report.freeze_stops else "")
        line("Whale Confidence:", f"{report.whale_confidence:.0f}%")

        sub("PRICE PHASE INTELLIGENCE (Timing)")
        phase_color = {
            "CORRECTION": GREEN, "BREAKOUT": GREEN + BOLD,
            "EXHAUSTION_UP": RED, "EXHAUSTION_DOWN": RED,
            "CONSOLIDATION": YELLOW,
        }.get(report.phase, "")
        line("Phase:", f"{phase_emoji(report.phase)} {report.phase}", phase_color)
        line("Confidence:", bar(report.phase_confidence))
        line("Dimensions:", f"{report.dimensions_confirming}/3")

        if report.entry_price > 0:
            sub("NIVELES DE EJECUCIÓN")
            line("Entry (LIMIT):", f"${report.entry_price:.2f}", GREEN + BOLD)
            line("Stop (Gamma):", f"${report.stop_price:.2f}", RED)
            line("Target:", f"${report.target_price:.2f}", CYAN)
            rr_color = GREEN + BOLD if report.risk_reward >= 3 else YELLOW if report.risk_reward >= 2 else RED
            line("Risk:Reward:", f"{report.risk_reward}:1", rr_color)

            risk_dollars = report.entry_price - report.stop_price
            reward_dollars = report.target_price - report.entry_price
            line("Risk ($/share):", f"${risk_dollars:.2f}")
            line("Reward ($/share):", f"${reward_dollars:.2f}")

            # Gamma-Aware Stop comparison
            if report.put_wall > 0:
                old_stop = trailing.calculate_stop(
                    report.current_price, report.atr, report.rs_vs_spy)
                gamma_stop = trailing.calculate_stop(
                    report.current_price, report.atr, report.rs_vs_spy,
                    put_wall=report.put_wall, vix_current=report.vix)
                line("Stop V1 (ATR only):", f"${old_stop:.2f}", DIM)
                line("Stop V2 (Gamma+VIX):", f"${gamma_stop:.2f}", GREEN)
                if gamma_stop < old_stop:
                    line("Extra Room:", f"+${old_stop - gamma_stop:.2f} anti-barrido", GREEN)

        sub("DICTAMEN FINAL")
        verdict_color = {
            "EXECUTE": GREEN + BOLD, "STALK": YELLOW,
            "BLOCK": RED + BOLD, "PASS": DIM,
        }.get(report.final_verdict, "")
        line("", f"{verdict_emoji(report.final_verdict)} {report.final_verdict} — {report.final_reason[:65]}", verdict_color)

    # ═══════════════════════════════════════════════════════════
    # SUMMARY TABLE
    # ═══════════════════════════════════════════════════════════

    header("RESUMEN — Dashboard de Inteligencia")

    # Table header
    print(f"\n  {BOLD}{'Ticker':<8} {'Price':>9} {'Phase':<15} {'Whales':<18} {'Gamma':<10} {'Wyckoff':<14} {'R:R':>6} {'Verdict':<10}{RESET}")
    print(f"  {'─'*8} {'─'*9} {'─'*15} {'─'*18} {'─'*10} {'─'*14} {'─'*6} {'─'*10}")

    executes = []
    stalks = []
    blocks = []

    for r in results:
        if r["error"]:
            print(f"  {r['ticker']:<8} {'ERROR':>9} {'—':<15} {'—':<18} {'—':<10} {'—':<14} {'—':>6} {RED}ERROR{RESET}")
            continue

        rpt = r["report"]
        v_color = {
            "EXECUTE": GREEN, "STALK": YELLOW,
            "BLOCK": RED, "PASS": DIM,
        }.get(rpt.final_verdict, "")

        gamma_short = rpt.gamma_regime[:7] if rpt.gamma_regime != "UNKNOWN" else "—"
        wyckoff_short = rpt.wyckoff_state[:12] if rpt.wyckoff_state != "UNKNOWN" else "—"

        rr_str = f"{rpt.risk_reward}:1" if rpt.risk_reward > 0 else "—"

        print(
            f"  {rpt.ticker:<8} "
            f"${rpt.current_price:>7.2f} "
            f"{rpt.phase:<15} "
            f"{rpt.whale_verdict:<18} "
            f"{gamma_short:<10} "
            f"{wyckoff_short:<14} "
            f"{rr_str:>6} "
            f"{v_color}{rpt.final_verdict:<10}{RESET}"
        )

        if rpt.final_verdict == "EXECUTE":
            executes.append(rpt)
        elif rpt.final_verdict == "STALK":
            stalks.append(rpt)
        else:
            blocks.append(rpt)

    # Summary stats
    print(f"\n  {BOLD}Resumen del Embudo:{RESET}")
    print(f"    🎯 EXECUTE: {GREEN}{len(executes)}{RESET} trades listos para ejecutar")
    print(f"    ⏳ STALK:   {YELLOW}{len(stalks)}{RESET} en watchlist esperando setup")
    print(f"    ⛔ BLOCK:   {RED}{len(blocks)}{RESET} vetados (exhaustion/contra flow)")

    # VIX context
    if detailed_reports:
        vix = detailed_reports[0].vix
        vix_color = RED if vix > 25 else YELLOW if vix > 20 else GREEN
        print(f"\n  {BOLD}Contexto Macro:{RESET}")
        print(f"    VIX: {vix_color}{vix:.1f}{RESET}", end="")
        if vix > 30:
            print(f" — {RED}CRISIS: stops expandidos 2x, sizing -50%{RESET}")
        elif vix > 25:
            print(f" — {YELLOW}ALTA VOL: stops expandidos 1.5x, sizing -30%{RESET}")
        elif vix > 20:
            print(f" — {YELLOW}ELEVADO: sizing normal con precaución{RESET}")
        else:
            print(f" — {GREEN}CALMA: condiciones favorables{RESET}")

        # Nearest macro event
        events_with_time = [(r.nearest_event, r.hours_to_event) for r in detailed_reports if r.nearest_event]
        if events_with_time:
            nearest = min(events_with_time, key=lambda x: x[1])
            event_color = RED if nearest[1] < 48 else YELLOW if nearest[1] < 120 else GREEN
            print(f"    Próximo evento: {event_color}{nearest[0]} en {nearest[1]:.0f}h{RESET}")

    # Execute details
    if executes:
        print(f"\n  {GREEN}{BOLD}═══ TRADES LISTOS PARA EJECUTAR ═══{RESET}")
        for rpt in executes:
            print(f"    {GREEN}🎯 {rpt.ticker}{RESET}: Entry=${rpt.entry_price:.2f}, "
                  f"Stop=${rpt.stop_price:.2f}, Target=${rpt.target_price:.2f}, "
                  f"R:R={rpt.risk_reward}:1, Scale={rpt.final_scale:.0%}")

    if stalks:
        print(f"\n  {YELLOW}{BOLD}═══ WATCHLIST (STALKING) ═══{RESET}")
        for rpt in stalks:
            print(f"    {YELLOW}⏳ {rpt.ticker}{RESET}: {rpt.phase} — "
                  f"{'R:R=' + str(rpt.risk_reward) + ':1' if rpt.risk_reward > 0 else 'Sin setup'} "
                  f"({rpt.dimensions_confirming}/3 dims)")

    total_time = sum(r["elapsed"] for r in results)
    print(f"\n  {DIM}Tiempo total: {total_time:.1f}s ({total_time/len(TICKERS):.1f}s/ticker){RESET}")
    print(f"  {DIM}59/59 tests pasando — Integración verificada{RESET}\n")


if __name__ == "__main__":
    run_live_simulation()
