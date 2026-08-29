#!/usr/bin/env python3
"""P2.9 — SENSIBILIDAD DE LA VENTANA F3/INDEP (recomendación Opus A.4/P2.9)
============================================================================
La ventana ±5d era un compromiso sin calibrar. Test: correr INDEP con 3d, 5d y 7d
para las señales del ranking v6 y verificar si el ordenamiento es estable.
La ventana SOLO afecta la forensia F3/INDEP (no el edge, p-value ni favorable neto).
"""
import sys
from pathlib import Path
ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

import evaluador_vela_a_vela as evv

SEÑALES_TOP = [
    "pcr_put_panic", "credit_stress", "capitulacion", "panico_total",
    "vvix_entry", "skew_paranoia_exit", "bsi_washed_out", "bsi_recovery",
    "breadth_contraction_exit", "stealth_tail_hedging", "fg_extreme_greed",
]
RESCATADAS = {"skew_paranoia_exit"}

VENTANAS = [3, 5, 7]
resultados = {w: {} for w in VENTANAS}

for s in SEÑALES_TOP:
    for w in VENTANAS:
        r = evv.evaluar(s, reevaluar=(s in RESCATADAS), ventana_f3=w)
        if r.get("status") == "OK":
            resultados[w][s] = r.get("forensia_F3", {}).get("independencia")

# Tabla comparativa
print(f"SENSIBILIDAD DE LA VENTANA F3/INDEP (3d vs 5d vs 7d)")
print(f"{'='*78}")
print(f"{'señal':>26s} | {'INDEP 3d':>8s} {'INDEP 5d':>8s} {'INDEP 7d':>8s} | {'spread':>6s}")
for s in SEÑALES_TOP:
    vals = [resultados[w].get(s) for w in VENTANAS]
    if any(v is None for v in vals):
        continue
    spread = max(vals) - min(vals)
    print(f"{s:>26s} | {vals[0]:>7.0%} {vals[1]:>7.0%} {vals[2]:>7.0%} | {spread:>5.0%}")

# Ranking por INDEP a cada ventana
print(f"\nRANKING POR INDEP (mayor independencia primero)")
print(f"{'='*78}")
rankings = {}
for w in VENTANAS:
    orden = sorted(resultados[w].items(), key=lambda x: -(x[1] or 0))
    rankings[w] = [s for s, _ in orden]
    print(f"  ventana {w}d: {' > '.join(s[:14] for s, _ in orden)}")

# ¿El ranking es estable? (correlación de Spearman entre ordenamientos)
from scipy.stats import spearmanr
comunes = [s for s in SEÑALES_TOP if all(resultados[w].get(s) is not None for w in VENTANAS)]
r35, _ = spearmanr([resultados[3][s] for s in comunes], [resultados[5][s] for s in comunes])
r57, _ = spearmanr([resultados[5][s] for s in comunes], [resultados[7][s] for s in comunes])
r37, _ = spearmanr([resultados[3][s] for s in comunes], [resultados[7][s] for s in comunes])
print(f"\nCorrelación de Spearman del ordenamiento INDEP:")
print(f"  3d vs 5d: rho={r35:.3f}")
print(f"  5d vs 7d: rho={r57:.3f}")
print(f"  3d vs 7d: rho={r37:.3f}")
if r35 > 0.8 and r57 > 0.8 and r37 > 0.8:
    print("\n→ RANKING ESTABLE: la ventana 5d es un compromiso aceptable (no arbitrario).")
else:
    print("\n→ RANKING INESTABLE: la elección de ventana altera el ordenamiento.")
