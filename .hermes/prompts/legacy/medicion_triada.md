# PROMPT PARA GEMINI — Agregar medición triádica (zz25/zz50/zz75) + anticipación/retraso
# Archivo: scratch/medir_senal.py
# Basado en: especificación §7.2 (tríada zigzag) y §9 (evaluador)

## Qué agregar (sin romper nada existente)
1. Medición por escala triádica: zz25 (prev_leg_return), zz50 (cascade_50), zz75 (cascade_75)
2. Anticipación/retraso: timing óptimo desde horizontes multi-día (dónde peak el edge)
3. Duración media de la pierna (duration_bars)
4. Reporte en stdout: triada info + timing_optimo

## Implementación exacta
Ver código en el prompt original (mensaje anterior del chat).

## PROHIBIDO
- NO tocar métricas existentes (_pctiles, _wins_losses, _bootstrap_ci, _mae_intratrade, _costo_tarde, _sensibilidad_timing)
- NO tocar @_registrar ni las señales
- NO tocar la estructura del JSON existente (solo agregar "triada" y "timing_optimo")
- NO cambiar seed (42) ni bootstrap (3000)

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal bsi_washed_out --horizontes 5,10,20,60
Debe mostrar: triada zz25, cascade zz50/zz75, duración, timing_optimo (horizonte_peak, edge_peak_mean)