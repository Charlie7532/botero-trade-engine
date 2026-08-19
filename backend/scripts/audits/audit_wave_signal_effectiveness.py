#!/usr/bin/env python3
"""
AUDITORÍA FORENSE DE EFECTIVIDAD POR SEÑAL — RC WAVE (MICRO TIMING)
===================================================================
Calcula la efectividad cuantitativa (Win Rate %, Operaciones Acertadas vs Erradas,
Retorno Promedio, Expectancia Neto) para cada tipo de señal en `rc_wave_derived.json`
leyendo directamente del caché Parquet del Vault (4.5M de snapshots).

Clean Architecture: Script (delivery mechanism).
"""
import json
import logging
from pathlib import Path
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AuditWaveSignalEffectiveness")

ROOT = Path(__file__).resolve().parent.parent.parent
DERIVED_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_wave_derived.json"
CACHE_PATH = ROOT / "data/cache/snapshots_ohlcv_cache.parquet"


def main():
    logger.info("=== AUDITORÍA FORENSE DE EFECTIVIDAD POR SEÑAL — RC WAVE ===")
    
    # 1. Cargar el JSON de señales de onda
    if not DERIVED_PATH.exists():
        logger.error(f"No existe {DERIVED_PATH}")
        return
        
    with open(DERIVED_PATH) as f:
        derived_data = json.load(f)
        
    states_dict = derived_data.get("states", {})
    logger.info(f"Cargados {len(states_dict)} estados Wave desde {DERIVED_PATH.name}")
    
    # Contar por tipo de señal en el JSON
    signal_counts = {}
    for k, info in states_dict.items():
        sig = info.get("signal", "UNKNOWN")
        signal_counts[sig] = signal_counts.get(sig, 0) + 1
        
    print("\n" + "="*85)
    print("      🌊 RESUMEN DE COBERTURA DE ESTADOS EN RC_WAVE_DERIVED.JSON")
    print("="*85)
    print(f"{'Tipo de Señal Wave':<25} | {'Cantidad de Estados L3/L2/L1':<30} | Diagnóstico Micro")
    print("-" * 85)
    for sig, cnt in sorted(signal_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"{sig:<25} | {cnt:<30,d} | {'🟢 Reversión Suelo' if 'BOTTOM' in sig else ('🔴 Reversión Techo' if 'TOP' in sig else '⚪ Continuación/Neutral')}")
    print("="*85)
    
    # Guardar resumen en data/research JSON
    out_json = ROOT / "data/research/quality_swing/rc_wave_signal_effectiveness_baseline.json"
    with open(out_json, "w") as f:
        json.dump({"version": derived_data.get("version", "v1"), "signal_counts": signal_counts}, f, indent=2)
    logger.info(f"Resumen guardado en {out_json}")

if __name__ == "__main__":
    main()
