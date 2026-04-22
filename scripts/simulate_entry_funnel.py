"""
SIMULACIÓN DEL EMBUDO COMPLETO — Entry Intelligence Pipeline
================================================================
Demuestra el flujo completo del Ejecutor de Entradas Inteligente
con datos simulados de 5 escenarios reales del mercado.

Ejecutar: python3 scripts/simulate_entry_funnel.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta, UTC

from backend.infrastructure.data_providers.event_flow_intelligence import (
    EventFlowIntelligence, MacroEvent,
)
from backend.application.price_phase_intelligence import PricePhaseIntelligence
from backend.application.portfolio_intelligence import AdaptiveTrailingStop


# ═══════════════════════════════════════════════════════════════
# FORMATTING
# ═══════════════════════════════════════════════════════════════

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"

def header(text):
    print(f"\n{'='*72}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{'='*72}")

def sub(text):
    print(f"  {DIM}{'─'*60}{RESET}")
    print(f"  {BOLD}{text}{RESET}")

def result_line(label, value, color=""):
    print(f"    {label:30s} {color}{value}{RESET}")


# ═══════════════════════════════════════════════════════════════
# PRICE DATA GENERATORS (Realistic scenarios)
# ═══════════════════════════════════════════════════════════════

def gen_correction(base=192, n=60):
    """NVDA-like: strong trend, then healthy pullback to SMA20."""
    close = [base]
    for i in range(1, 45):
        close.append(close[-1] * 1.003)  # Solid uptrend
    for i in range(45, n):
        # Mixed bars near SMA20
        if i % 5 in (0, 2): close.append(close[-1] * 1.001)
        else: close.append(close[-1] * 0.998)
    close = np.array(close)
    high = close * 1.004
    low = close * 0.996
    vol = np.ones(n) * 2_000_000
    vol[-12:] = 600_000  # Volume dries up
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


def gen_breakout(base=150, n=55):
    """AMZN-like: consolidation then breakout with volume."""
    np.random.seed(99)
    close = np.full(50, base) + np.random.randn(50) * 0.3
    for i in range(50, n):
        close = np.append(close, close[-1] * 1.004)
    high = close * 1.003
    low = close * 0.997
    vol = np.ones(n) * 800_000
    vol[50:] = 3_200_000  # 4x volume explosion
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


def gen_exhaustion(base=100, n=60):
    """TSLA-like: parabolic run, extended far above SMA20."""
    close = [base]
    for i in range(1, n):
        close.append(close[-1] * 1.018)  # +1.8% daily = parabolic
    close = np.array(close)
    high = close * 1.01
    low = close * 0.99
    vol = np.ones(n) * 3_000_000
    vol[-5:] *= 5  # Volume climax at the top
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


def gen_consolidation(base=175, n=60):
    """JPM-like: sideways range, no direction."""
    np.random.seed(55)
    close = base + np.random.randn(n) * 1.5  # Random walk around base
    close = np.maximum(close, base - 5)
    high = close + abs(np.random.randn(n) * 0.8)
    low = close - abs(np.random.randn(n) * 0.8)
    vol = np.ones(n) * 1_500_000
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


# ═══════════════════════════════════════════════════════════════
# SIMULATION SCENARIOS
# ═══════════════════════════════════════════════════════════════

def run_simulation():
    header("SIMULACIÓN DEL EMBUDO COMPLETO — Entry Intelligence Pipeline")
    print(f"  {DIM}Fecha simulada: 2026-04-27 (un día antes del FOMC){RESET}")
    print(f"  {DIM}Próximo FOMC: 2026-04-29 14:00 ET{RESET}")
    print()

    efi = EventFlowIntelligence()
    ppi = PricePhaseIntelligence()
    trailing = AdaptiveTrailingStop()

    # ── Reference date: 1 day before FOMC ──
    ref_date = date(2026, 4, 27)
    events = efi.get_events(days_ahead=5, reference_date=ref_date)

    print(f"  📅 Eventos macro detectados ({len(events)}):")
    for e in events:
        icon = "🔴" if e.impact_level == 1 else "🟡" if e.impact_level == 2 else "🟢"
        print(f"    {icon} {e.name:20s} → {e.event_date.strftime('%Y-%m-%d %H:%M UTC')} (Level {e.impact_level})")

    scenarios = [
        {
            "name": "NVDA — Corrección Sana + Ballenas Comprando",
            "ticker": "NVDA",
            "prices": gen_correction(),
            "put_wall": 195.0, "call_wall": 215.0,
            "gamma_regime": "PIN", "wyckoff_state": "ACCUMULATION",
            # Whale flow: STRONG BULLISH (whales know FOMC will be dovish)
            "flow": dict(
                spy_cum_delta=900_000, total_sweeps=18, sweep_call_pct=78,
                tide_direction="BULLISH", tide_accelerating=True,
                tide_net_premium=12_000_000, spy_confidence=0.88,
                gex_regime="PIN",
            ),
            "vix": 19.5,
        },
        {
            "name": "AMZN — Breakout + Flujo Moderado",
            "ticker": "AMZN",
            "prices": gen_breakout(),
            "put_wall": 148.0, "call_wall": 162.0,
            "gamma_regime": "SQUEEZE_UP", "wyckoff_state": "MARKUP",
            # Whale flow: moderate bullish
            "flow": dict(
                spy_cum_delta=250_000, total_sweeps=7, sweep_call_pct=64,
                tide_direction="BULLISH", tide_accelerating=False,
                spy_confidence=0.65, gex_regime="SQUEEZE_UP",
            ),
            "vix": 21.0,
        },
        {
            "name": "TSLA — Extensión Parabólica (Trampa)",
            "ticker": "TSLA",
            "prices": gen_exhaustion(),
            "put_wall": 250.0, "call_wall": 320.0,
            "gamma_regime": "DRIFT", "wyckoff_state": "DISTRIBUTION",
            # Whale flow: CONTRA (puts increasing, AM/PM diverge)
            "flow": dict(
                spy_cum_delta=-100_000, total_sweeps=8, sweep_call_pct=35,
                am_pm_diverges=True, tide_direction="BEARISH",
                tide_accelerating=True, spy_confidence=0.7,
                gex_regime="DRIFT",
            ),
            "vix": 24.0,
        },
        {
            "name": "JPM — Consolidación + Sin Flujo",
            "ticker": "JPM",
            "prices": gen_consolidation(),
            "put_wall": 172.0, "call_wall": 180.0,
            "gamma_regime": "PIN", "wyckoff_state": "CONSOLIDATION",
            # Whale flow: SILENT — nobody knows what FOMC will bring
            "flow": dict(
                spy_cum_delta=15_000, total_sweeps=1, sweep_call_pct=50,
                tide_direction="NEUTRAL", spy_confidence=0.35,
                gex_regime="PIN",
            ),
            "vix": 22.0,
        },
        {
            "name": "META — Corrección + Flujo Contradictorio",
            "ticker": "META",
            "prices": gen_correction(base=510),
            "put_wall": 520.0, "call_wall": 560.0,
            "gamma_regime": "PIN", "wyckoff_state": "ACCUMULATION",
            # Whale flow: CONTRADICTORY — SPY bearish but sweeps bullish
            "flow": dict(
                spy_cum_delta=-400_000, total_sweeps=10, sweep_call_pct=70,
                am_pm_diverges=True, tide_direction="BEARISH",
                spy_confidence=0.6, gex_regime="PIN",
            ),
            "vix": 26.0,
        },
    ]

    final_results = []

    for i, sc in enumerate(scenarios, 1):
        header(f"ESCENARIO {i}: {sc['name']}")

        # ── GATE 1: Hohn (simulated) ──
        sub("GATE 1: Filtro Hohn (Calidad Fundamental)")
        result_line("QGARP Score:", "82/100 ✅", GREEN)
        result_line("FCF Margin:", "28% ✅", GREEN)
        result_line("Piotroski:", "7/9 ✅", GREEN)

        # ── GATE 2: AlphaScanner (simulated) ──
        sub("GATE 2: AlphaScanner (RS + Momentum)")
        result_line("RS vs SPY 20d:", "1.12 (Superando)", GREEN)
        result_line("UW Flow Score:", "67.3/100", GREEN)
        result_line("Status:", "CANDIDATO APROBADO ✅", GREEN)

        # ── GATE 3: EventFlowIntelligence ──
        sub("GATE 3: EventFlowIntelligence (Calendario + Ballenas)")
        whale_v = efi.assess(reference_date=ref_date, **sc["flow"])

        verdict_color = {
            "RIDE_THE_WHALES": GREEN, "LEAN_WITH_FLOW": YELLOW,
            "UNCERTAIN": YELLOW, "CONTRA_FLOW": RED,
        }.get(whale_v.verdict, "")
        result_line("Nearest Event:", f"{whale_v.nearest_event.name if whale_v.nearest_event else 'NONE'} ({whale_v.hours_to_event:.0f}h)")
        result_line("SPY Flow:", whale_v.spy_flow_direction)
        result_line("Sweep Intensity:", whale_v.sweep_intensity)
        result_line("GEX Regime:", whale_v.gex_regime)
        result_line("AM/PM Divergence:", str(whale_v.am_pm_divergence), RED if whale_v.am_pm_divergence else "")
        result_line("Whale Verdict:", f"{whale_v.verdict} (scale={whale_v.position_scale:.0%})", verdict_color)
        result_line("Diagnosis:", whale_v.diagnosis[:65] + "...")

        if whale_v.verdict == "CONTRA_FLOW":
            result_line("", f"{RED}⛔ BLOQUEADO POR FLUJO CONTRADICTORIO{RESET}")
            final_results.append((sc["ticker"], "⛔ BLOCKED", "N/A", "N/A"))
            continue

        # ── GATE 4: PricePhaseIntelligence ──
        sub("GATE 4: PricePhaseIntelligence (Timing)")
        phase_v = ppi.diagnose(
            sc["ticker"], sc["prices"],
            put_wall=sc["put_wall"], call_wall=sc["call_wall"],
            gamma_regime=sc["gamma_regime"], wyckoff_state=sc["wyckoff_state"],
        )

        phase_color = {
            "CORRECTION": GREEN, "BREAKOUT": GREEN,
            "EXHAUSTION_UP": RED, "CONSOLIDATION": YELLOW,
        }.get(phase_v.phase, "")
        result_line("Phase:", phase_v.phase, phase_color)
        result_line("RSI:", f"{phase_v.rsi14:.0f}")
        result_line("Dist SMA20:", f"{phase_v.distance_to_sma20_atr:+.1f} ATR")
        result_line("RVOL:", f"{phase_v.rvol:.1f}x")
        result_line("Wyckoff:", phase_v.wyckoff_state)
        result_line("Gamma:", f"{phase_v.gamma_regime}")
        result_line("Dims Confirming:", f"{phase_v.dimensions_confirming}/3 ({phase_v.confidence:.0f}%)")

        verdict_color2 = {
            "FIRE": GREEN, "STALK": YELLOW, "ABORT": RED,
        }.get(phase_v.verdict, "")
        result_line("Phase Verdict:", phase_v.verdict, verdict_color2)

        if phase_v.verdict == "ABORT":
            result_line("", f"{RED}⛔ ABORTADO POR FASE EXHAUSTION{RESET}")
            final_results.append((sc["ticker"], "⛔ ABORT", phase_v.phase, "N/A"))
            continue

        if phase_v.verdict == "STALK":
            result_line("", f"{YELLOW}⏳ EN ESPERA — Stalkeando para mejor entrada{RESET}")
            final_results.append((sc["ticker"], "⏳ STALK", phase_v.phase, f"R:R={phase_v.risk_reward_ratio}:1"))
            continue

        # ── GATE 5: Niveles de Entrada ──
        sub("GATE 5: Niveles de Ejecución")
        result_line("Entry (LIMIT):", f"${phase_v.entry_price:.2f}", GREEN)
        result_line("Stop (Gamma):", f"${phase_v.stop_price:.2f}", RED)
        result_line("Target (Call Wall):", f"${phase_v.target_price:.2f}", CYAN)
        result_line("Risk:Reward:", f"{phase_v.risk_reward_ratio}:1", GREEN if phase_v.risk_reward_ratio >= 3 else RED)

        # ── GATE 6: Stop Gamma-Aware ──
        sub("GATE 6: GammaAwareStop (Protección de Barrido)")
        # Compare: old stop vs new gamma-aware stop
        old_stop = trailing.calculate_stop(phase_v.current_price, phase_v.atr14, rs_vs_spy=1.1)
        gamma_stop = trailing.calculate_stop(
            phase_v.current_price, phase_v.atr14, rs_vs_spy=1.1,
            put_wall=sc["put_wall"], vix_current=sc["vix"],
        )
        result_line("Stop V1 (ATR only):", f"${old_stop:.2f}")
        result_line("Stop V2 (Gamma+VIX):", f"${gamma_stop:.2f}", GREEN)
        result_line("VIX:", f"{sc['vix']:.1f}")
        result_line("Put Wall:", f"${sc['put_wall']:.2f}")

        if gamma_stop < old_stop:
            result_line("Protection:", f"${old_stop - gamma_stop:.2f} más de room para respirar", GREEN)
        else:
            result_line("Protection:", "Stop ATR ya era más generoso", YELLOW)

        # Freeze check
        freeze = trailing.should_freeze(freeze_stops=whale_v.freeze_stops)
        result_line("Freeze Active:", str(freeze), RED if freeze else "")

        # ── Position sizing ──
        sub("RESULTADO FINAL")
        scale = whale_v.position_scale
        result_line("Position Scale:", f"{scale:.0%}", GREEN if scale >= 0.7 else YELLOW)
        if scale > 0:
            notional = 5000 * scale
            qty = max(1, int(notional / phase_v.entry_price))
            result_line("Notional:", f"${notional:,.0f}")
            result_line("Quantity:", f"{qty} shares")
            result_line("Max Loss:", f"${qty * (phase_v.entry_price - gamma_stop):,.2f}", RED)
            result_line("Potential Profit:", f"${qty * (phase_v.target_price - phase_v.entry_price):,.2f}", GREEN)
        final_results.append((
            sc["ticker"], f"🎯 FIRE ({scale:.0%})", phase_v.phase,
            f"R:R={phase_v.risk_reward_ratio}:1"
        ))

    # ═══ SUMMARY TABLE ═══
    header("RESUMEN DEL EMBUDO")
    print(f"  {'Ticker':<10} {'Resultado':<25} {'Phase':<20} {'R:R':<15}")
    print(f"  {'─'*10} {'─'*25} {'─'*20} {'─'*15}")
    for ticker, result, phase, rr in final_results:
        color = GREEN if "FIRE" in result else YELLOW if "STALK" in result else RED
        print(f"  {ticker:<10} {color}{result:<25}{RESET} {phase:<20} {rr:<15}")

    print(f"\n  {BOLD}Conclusión:{RESET}")
    fires = sum(1 for _, r, _, _ in final_results if "FIRE" in r)
    stalks = sum(1 for _, r, _, _ in final_results if "STALK" in r)
    blocks = sum(1 for _, r, _, _ in final_results if "BLOCK" in r or "ABORT" in r)
    print(f"    🎯 FIRE:  {fires} trades listos para ejecutar")
    print(f"    ⏳ STALK: {stalks} trades en watchlist")
    print(f"    ⛔ BLOCK: {blocks} trades vetados por el embudo")
    print(f"\n  {DIM}De 5 candidatos con calidad fundamental A+, solo {fires} pasan")
    print(f"  todos los gates del embudo. Eso es SELECTIVIDAD institucional.{RESET}\n")


if __name__ == "__main__":
    run_simulation()
