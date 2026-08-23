"""arnes — Arnés de medición estándar Botero Trade (refactor del God file).

Re-exporta la API pública completa de medir_senal.py para compatibilidad.
"""
from .datos import ROOT, SCRATCH, OBS_PKL, cargar_datos
from .registro import SEÑALES, _CERTEZA, _registrar
from . import señales as _señales  # noqa: F401 — ejecuta el registro
from .estadisticas import _pctiles, _wins_losses, _bootstrap_ci, _lift_vs_baseline
from .timing import _mae_intratrade, _costo_tarde, _sensibilidad_timing
from .estructura import (_FS_DIR, _ESTACIONES, _CAT, _surprise_vector,
                         _structural_momentum_filter, _prev_leg_context,
                         _divergence_regime)
from .medicion import medir, medir_cross_overlap
from .cli import main

__all__ = ["ROOT", "SCRATCH", "OBS_PKL", "cargar_datos", "SEÑALES", "_CERTEZA",
           "_registrar", "medir", "medir_cross_overlap", "main"]
