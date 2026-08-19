# PROMPT PARA GEMINI — B1 micro-fix: or 100 → or 0
# Archivo: backend/modules/entry_decision/domain/services/convergence_compositor.py
# Línea 366: n_samp = metar.get("n_samples", 100) or 100
# Bug: "or 100" convierte n_samples=0 en 100, anulando el fix B1 para N=0.

## Fix (1 palabra)
n_samp = metar.get("n_samples", 0) or 0

## PROHIBIDO
- NO tocar ninguna otra línea
- NO tocar ningún otro archivo