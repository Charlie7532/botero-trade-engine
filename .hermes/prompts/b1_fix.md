# PROMPT PARA GEMINI — B1: N=0 vote attenuation
# Archivo: backend/modules/entry_decision/domain/services/convergence_compositor.py
# Bug: estados con N=0 votan con plena convicción en cascade_conviction

## Fix (2 líneas)
1. d1_directional_vote(state_key: str) -> int → -> float
   return values: -1 → -1.0, 0 → 0.0, +1 → +1.0

2. En el loop de votos:
   vote = d1_directional_vote(st_key) * rf
   donde rf = reliability_factor(n_samp) (ya calculado)

## PROHIBIDO
- NO tocar pesos del cascade (w_bear=0.66, w_dom=0.34)
- NO tocar reliability_factor ni rarity_amplifier
- NO tocar otros canales (EV, rareza)
- NO añadir TAF, state vector, cuadrantes ni ninguna clase nueva
- NO tocar otros archivos

## Verificación
cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/decay_check_cascade_conviction.py
cascade_50 IC debe mantenerse ≈ +0.41