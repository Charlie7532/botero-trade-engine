# Eliminar --horizontes de medir_senal.py
# --horizontes es ruido: horizontes fijos en días NO son la tríada.

## Eliminar:
1. El argumento --horizontes del argparse en main()
2. La variable horizontes y su parsing
3. La sección 4.7 (timing_optimo) y la sección 4.5 (horizontes multi-día)
4. Las líneas del stdout que imprimen timing_optimo
5. El parámetro horizontes_dias de la función medir()
6. La clave "horizontes" del JSON de salida
7. La clave "timing_optimo" del JSON de salida

## PROHIBIDO
- NO tocar métricas existentes (triada, capture_ratio, anticipacion_zigzag, desglose_d2d3)
- NO tocar @_registrar ni las señales
- NO tocar seed (42) ni bootstrap (3000)

## Verificación
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal bsi_washed_out
NO debe mostrar "Timing óptimo" ni "Horizontes". Solo debe mostrar: tríada, cascade, persistencia, capture_ratio, MAE, costo retraso.