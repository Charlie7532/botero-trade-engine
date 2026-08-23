#!/usr/bin/env python3
"""
medir_senal.py — FACHADA DE COMPATIBILIDAD (post-refactor 22-Ago-2026).

El God file original (1,497 líneas) fue descompuesto bajo Clean Architecture en
el paquete `arnes/` (8 módulos con responsabilidad única):

    arnes/datos.py          carga de datos (quants_obs + SPY)
    arnes/registro.py       registry SEÑALES / _CERTEZA
    arnes/señales.py        28 definiciones de señales (dominio)
    arnes/estadisticas.py   percentiles, wins/losses, bootstrap CI95, LIFT
    arnes/timing.py         MAE intra-trade, costo de tarde, sensibilidad
    arnes/estructura.py     sorpresa, structural momentum, régimen divergencia
    arnes/medicion.py       medir() y medir_cross_overlap()
    arnes/cli.py            interfaz de línea de comandos

Este archivo conserva la API pública exacta para los ~10 scripts que hacen
`from medir_senal import ...`. El God file original quedó respaldado en
`_deprecated/medir_senal_godfile_1497L_backup.py`.

Regresión verificada 22-Ago: 0 diferencias en credit_easing_k1, bsi_recovery
y euforia (seed=42, bootstrap=3000) contra el God file original.

Uso (idéntico al anterior):
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
      research/01_señales_entry_exit/medir_senal.py --señal credit_easing_k1
"""
import sys
from pathlib import Path

# El directorio de este archivo debe estar en sys.path para resolver `arnes`
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Re-exportación completa de la API pública (compatibilidad 1:1)
from arnes import (  # noqa: E402
    ROOT, SCRATCH, OBS_PKL,
    cargar_datos,
    SEÑALES, _CERTEZA, _registrar,
    _pctiles, _wins_losses, _bootstrap_ci, _lift_vs_baseline,
    _mae_intratrade, _costo_tarde, _sensibilidad_timing,
    _FS_DIR, _ESTACIONES, _CAT, _surprise_vector,
    _structural_momentum_filter, _prev_leg_context, _divergence_regime,
    medir, medir_cross_overlap,
    main,
)

__all__ = [
    "ROOT", "SCRATCH", "OBS_PKL", "cargar_datos",
    "SEÑALES", "_CERTEZA", "_registrar",
    "_pctiles", "_wins_losses", "_bootstrap_ci", "_lift_vs_baseline",
    "_mae_intratrade", "_costo_tarde", "_sensibilidad_timing",
    "_FS_DIR", "_ESTACIONES", "_CAT", "_surprise_vector",
    "_structural_momentum_filter", "_prev_leg_context", "_divergence_regime",
    "medir", "medir_cross_overlap", "main",
]

if __name__ == "__main__":
    main()
