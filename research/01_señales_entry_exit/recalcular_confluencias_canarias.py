#!/usr/bin/env python3
"""
Recalcular Confluencias Canarias con N Limpio Post-Inception
============================================================
Evalúa sistemáticamente la co-ocurrencia, correlación phi, lift individual y conjunto,
y significancia estadística bajo control FDR Benjamini-Hochberg de pares y tríadas
de señales canarias sobre datos limpios.

Produce: data/research/signals/confluencias_canarias.json
"""
import json
import sys
from pathlib import Path
from itertools import combinations
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "research" / "01_señales_entry_exit") not in sys.path:
    sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consultar_inteligencia import SignalIntelligenceEngine
from arnes.registro import SEÑALES, _CERTEZA

def main():
    engine = SignalIntelligenceEngine()
    print("Iniciando evaluación de confluencias canarias sobre datos limpios...")

    # Señales operativas clave para confluencias (excluyendo background / saturación)
    SEÑALES_CLAVE_ENTRY = [
        "panico_total", "vix_crisis_spike", "fg_extreme_fear", "credit_stress",
        "bsi_washed_out", "capitulacion", "vvix_entry", "neutral_crush_entry",
        "pcr_put_panic", "credit_capitulation_entry"
    ]
    
    SEÑALES_CLAVE_EXIT = [
        "skew_paranoia_exit", "stealth_tail_hedging", "sv5t_silent_distribution",
        "fg_extreme_greed", "pcr_panic_exit", "credit_stress_exit",
        "neutral_spike_exit", "defensive_rotation_divergence"
    ]

    confluencias = []

    # 1. Pares de Entry (convergencia de compra / capitulación)
    print(f"\nEvaluando {len(list(combinations(SEÑALES_CLAVE_ENTRY, 2)))} pares de ENTRY...")
    for sig_a, sig_b in combinations(SEÑALES_CLAVE_ENTRY, 2):
        res = engine.consultar_confluencia(sig_a, sig_b, scale="zz25")
        if "error" in res:
            continue
        co = res["co_occurrence"]
        combo = res.get("edge_combined", {})
        bh = res.get("bh_correction", {})
        
        # Filtro de relevancia: deben haber co-ocurrido al menos 1 vez
        if co["n_both_active"] > 0:
            confluencias.append({
                "tipo": "ENTRY_CONVERGENCE",
                "signal_a": sig_a,
                "signal_b": sig_b,
                "scale": "zz25",
                "dias_co_ocurrencia": co["n_both_active"],
                "overlap_ratio": co["overlap_ratio"],
                "phi_correlation": co["phi_correlation"],
                "p_independencia": co["p_independence"],
                "independencia": res.get("independencia_conclusion"),
                "edge_a": res["edge_individual"].get(sig_a),
                "edge_b": res["edge_individual"].get(sig_b),
                "edge_combinado": combo,
                "bh_significant": bh.get("any_significant_bh", False),
            })

    # 2. Pares de Exit (convergencia de distribución / alerta de techo)
    print(f"Evaluando {len(list(combinations(SEÑALES_CLAVE_EXIT, 2)))} pares de EXIT...")
    for sig_a, sig_b in combinations(SEÑALES_CLAVE_EXIT, 2):
        res = engine.consultar_confluencia(sig_a, sig_b, scale="zz25")
        if "error" in res:
            continue
        co = res["co_occurrence"]
        combo = res.get("edge_combined", {})
        bh = res.get("bh_correction", {})
        
        if co["n_both_active"] > 0:
            confluencias.append({
                "tipo": "EXIT_CONVERGENCE",
                "signal_a": sig_a,
                "signal_b": sig_b,
                "scale": "zz25",
                "dias_co_ocurrencia": co["n_both_active"],
                "overlap_ratio": co["overlap_ratio"],
                "phi_correlation": co["phi_correlation"],
                "p_independencia": co["p_independence"],
                "independencia": res.get("independencia_conclusion"),
                "edge_a": res["edge_individual"].get(sig_a),
                "edge_b": res["edge_individual"].get(sig_b),
                "edge_combinado": combo,
                "bh_significant": bh.get("any_significant_bh", False),
            })

    # Ordenar por lift combinado si existe, o por días de co-ocurrencia
    confluencias.sort(
        key=lambda x: (
            x["edge_combinado"].get("lift", -999) if x["edge_combinado"] else -999,
            x["dias_co_ocurrencia"]
        ),
        reverse=True
    )

    out_file = ROOT / "data" / "research" / "signals" / "confluencias_canarias.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "version": "1.0-limpio-inception",
            "total_confluencias_activas": len(confluencias),
            "descripcion": "Pares de señales METAR evaluados sobre series post-inception con independencia y edge combinado",
        },
        "confluencias": confluencias,
    }
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    print(f"\n✅ Confluencias Canarias ({len(confluencias)} pares activos) guardadas en:\n   {out_file}")

    # Imprimir top confluencias con edge combinado
    print("\nTop Confluencias con Disparo Combinado:")
    print(f"{'Tipo':<18s} | {'Señal A':<22s} + {'Señal B':<22s} | {'Días':>4s} {'Overlap':>7s} {'Phi':>6s} | {'N_indep':>7s} {'HR_combo':>8s} {'Lift_combo':>10s}")
    print("-" * 115)
    for c in confluencias:
        combo = c["edge_combinado"]
        if combo and combo.get("n_indep", 0) > 0:
            hr = f"{combo['hit_rate']:.1%}" if combo.get('hit_rate') is not None else "-"
            lift = f"{combo['lift']:+.1%}" if combo.get('lift') is not None else "-"
            n_ind = str(combo.get('n_indep', '-'))
            print(f"{c['tipo']:<18s} | {c['signal_a']:<22s} + {c['signal_b']:<22s} | {c['dias_co_ocurrencia']:>4d} {c['overlap_ratio']:>7.2f} {c['phi_correlation']:>6.2f} | {n_ind:>7s} {hr:>8s} {lift:>10s}")

if __name__ == "__main__":
    main()
