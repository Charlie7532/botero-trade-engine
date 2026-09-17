# PROMPT PARA GEMINI — Rediseñar YIELD_CURVE a 2Y-10Y
# Archivos: yield_curve_metar_service.py, yield_curve_lookup.py, yield_curve_fact_store.json
# Cambio: reemplazar TNX−IRX (10Y−3M) → DGS2−DGS10 (2Y−10Y)
# Razón: 2Y-10Y captura 7/8 drawdowns >15% y captura 2022 (194 días antes del fondo).
# 10Y-3M llegó 29 días después del fondo de 2022.

## Tareas
1. Cambiar spread_series = pivot_c["TNX"] - pivot_c["IRX"] → spread_series = pivot_c["DGS2"] - pivot_c["DGS10"]
2. Verificar DGS2 y DGS10 en Vault (DGS2: 12,547 filas, DGS10: 16,139 filas)
3. Re-entrenar fact store yield_curve_fact_store.json con la nueva fórmula
4. Mantener estructura D1×D2×D3 y state_key idéntica

## PROHIBIDO
- NO añadir 2Y-3M todavía (es señal de re-entry, prompt separado)
- NO tocar el cascade, ni STATION_WEIGHTS, ni otras estaciones
- NO tocar velocidad Δ3d (mantener como D2)
- NO regenerar otros fact stores