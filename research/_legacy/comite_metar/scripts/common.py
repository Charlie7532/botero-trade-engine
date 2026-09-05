"""
common.py — base compartida del Comité METAR Walk-Forward (Fases 1-3).

Rutas canónicas, carga del lake / perfiles / catálogo, y utilidades de
metrología usadas por episodios.py, estado_en.py y first_passage.py.

Marco normativo (no negociable, arnés METAR):
    - Sin lookahead: en t solo columnas observables <= t.
    - Inception por estación: el agente "madura" cuando su estación tiene datos.
    - D1xD2xD3: labels canónicos por estación + universales D2/D3.
    - De-clustering = credibilidad, nunca exclusión.
    - Confluencia probabilística, no determinista. La verdad habla.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]                 # /root/botero-trade
COMITE = REPO_ROOT / "comite_metar"
SCRIPTS = COMITE / "scripts"
AGENTES = COMITE / "agentes"
CURADOR = COMITE / "curador"
SALIDAS = COMITE / "salidas"
PERFILES = COMITE / "perfiles"

DATA_RESEARCH = REPO_ROOT / "data" / "research"
LAKE_PATH = DATA_RESEARCH / "continuous_metar_lake.parquet"
EVAL_PATH = DATA_RESEARCH / "signals" / "evaluacion_generalizada_lake.json"
RANK_PATH = DATA_RESEARCH / "signals" / "ranking_maestro.json"
CANARY_PATH = DATA_RESEARCH / "signals" / "confluencias_canarias.json"
PERFIL_PATH = PERFILES / "perfil_estaciones.json"

# Las 11 estaciones en el orden del registro maestro.
ESTACIONES = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew",
    "credit", "yield_curve", "rotation", "dxy", "bsi",
]

# Sufijo de columnas uniformes por estación (22 por estación + spy).
ST_COLS = ["_val", "_d2_raw", "_d3_raw", "_d1_bin", "_d2_bin", "_d3_bin",
           "_d1", "_d2", "_d3", "_sk", "_z_d1", "_z_d2", "_z_d3",
           "_ovf2s_d1", "_ovf3s_d1", "_overflow_tier_d1",
           "_ovf2s_d2", "_ovf3s_d2", "_overflow_tier_d2",
           "_ovf2s_d3", "_ovf3s_d3", "_overflow_tier_d3"]

MERCADO_COLS = ["spy_open", "spy_high", "spy_low", "spy_close", "spy_volume", "spy_ret_1d"]

# Bins auxiliares para label lookup: bin -1 = pre-inception/sin datos.
D2_UNIVERSAL = [
    "FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D",
    "ACCELERATING_UP_3D", "FAST_SPIKE_3D",
]
D3_UNIVERSAL = [
    "VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION", "VOL_NEUTRAL_BASELINE",
    "VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION",
]


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def cargar_lake():
    """Lake continuo limpio (8,456 barras, 257 cols). Index = 'time'."""
    import pandas as pd
    df = pd.read_parquet(LAKE_PATH)
    if df.index.name != "time":
        df = df.set_index("time")
    df.index = pd.to_datetime(df.index)
    return df


def cargar_perfiles() -> List[Dict]:
    data = json.loads(PERFIL_PATH.read_text(encoding="utf-8"))
    est = data["estaciones"]
    return [{"estacion": k, **v} for k, v in est.items()]


def perfiles_por_estacion() -> Dict[str, Dict]:
    return {p["estacion"]: p for p in cargar_perfiles()}


def cargar_catalogo() -> Dict:
    """evaluacion_generalizada_lake.json — 36 señales, criterio continuo."""
    return json.loads(EVAL_PATH.read_text(encoding="utf-8"))


def cargar_ranking() -> Dict:
    """ranking_maestro.json — {metadata, ranking[36]}."""
    return json.loads(RANK_PATH.read_text(encoding="utf-8"))


def ranking_por_senal() -> Dict[str, Dict]:
    rk = cargar_ranking()
    return {r["senal"]: r for r in rk["ranking"]}


def cargar_confluencias() -> Dict:
    return json.loads(CANARY_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
#  Mapeo señal -> estacion (heurística por prefijo / sobre-escrito)
# ---------------------------------------------------------------------------
# Señales compuestas o de estructura de mercado (sin estación única).
_SENALES_MERCADO = {
    "cascade_reversal", "capitulacion", "capitulacion_v2", "panico_total",
    "sorpresa_total", "sub_reaccion", "neutral_crush_entry",
    "neutral_spike_exit", "stealth_tail_hedging", "euforia", "euforia_v2",
    "regime_change_exit", "credit_equity_divergence", "defensive_rotation_divergence",
}

_SEÑAL_A_ESTACION = {
    "vix_crisis_spike": "vix", "vix_crisis_spike_v2": "vix",
    "vix_instability_warning": "vix", "vix_complacency_exit": "vix",
    "vvix_entry": "vvix",
    "pcr_put_panic": "pcr", "pcr_panic_exit": "pcr",
    "fg_extreme_fear": "fg", "fg_extreme_greed": "fg",
    "sv5t_silent_distribution": "sv5_turbulence",
    "skew_paranoia_exit": "skew",
    "credit_stress": "credit", "credit_stress_exit": "credit",
    "credit_capitulation_entry": "credit", "credit_capitulation_exit": "credit",
    "credit_ease_exit": "credit", "credit_easing_k1": "credit",
    "bsi_compression_entry": "bsi", "bsi_washed_out": "bsi",
    "bsi_recovery": "bsi", "breadth_contraction_exit": "bsi",
    "dxy_bearish": "dxy", "dxy_spike_exit": "dxy",
}


def senal_estacion(senal: str) -> Optional[str]:
    if senal in _SENALES_MERCADO:
        return None
    return _SEÑAL_A_ESTACION.get(senal)


def señales_de_estacion(estacion: str) -> List[str]:
    return [s for s, e in _SEÑAL_A_ESTACION.items() if e == estacion]


# ---------------------------------------------------------------------------
#  Helpers de columna
# ---------------------------------------------------------------------------
def sk_columns() -> List[str]:
    return [f"{e}_sk" for e in ESTACIONES]


def val_columns() -> List[str]:
    return [f"{e}_val" for e in ESTACIONES]


def _between(a, lo, hi):
    return lo <= a <= hi