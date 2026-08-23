"""
Regresión de la cadena quants_obs
=================================
La tabla de observación canónica (data/research/pivots/quants_obs.pkl) fue
sustituida el 23-Ago-2026 por la versión auditada (3 auditorías externas Opus,
15 fixes acumulados, builder determinista en backend/scripts/generators/).

Estos tests CONGELAN los invariantes verificados para que ningún cambio futuro
los rompa en silencio. Si un test falla, la cadena está rota: detener cualquier
trabajo sobre señales hasta diagnosticar (ver docs/research/10_gate_oos_validation/).
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

PKL = ROOT / "data/research/pivots/quants_obs.pkl"
STATIONS = ["vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew", "credit",
            "yield_curve", "rotation", "bsi", "dxy"]


@pytest.fixture(scope="module")
def obs():
    return pd.read_pickle(PKL).reset_index(drop=True)


def test_esquema_143_columnas(obs):
    """Esquema auditado: 1,590 pivotes × 143 columnas (incluye n_stations_a y
    cascade_conviction_50, añadidas por el builder v8)."""
    assert obs.shape == (1590, 143), f"esquema inesperado: {obs.shape}"
    for col in ("pivot_date", "pivot_type", "cascade_conviction_50",
                "n_stations_a", "duration_bars", "daily_return_pct",
                "d1_bear_5", "z_bear", "z_dom", "cascade_conviction"):
        assert col in obs.columns, f"falta columna crítica: {col}"


def test_pivotes_zigzag_oficial(obs):
    """Columna vertebral: los pivotes deben ser EXACTAMENTE los del repo de
    producción (ZigzagLegRepository zz25). Cualquier desalineación rompe todo."""
    from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
    legs = sorted(ZigzagLegRepository().get_confirmed_legs("SPY", "zz25"),
                  key=lambda l: l.start_timestamp)
    assert len(legs) == len(obs), f"{len(legs)} legs en repo vs {len(obs)} filas"
    fechas_db = [pd.Timestamp(l.start_timestamp).tz_convert("UTC").tz_localize(None)
                 for l in legs]
    fechas_obs = pd.to_datetime(obs["pivot_date"]).tolist()
    assert fechas_db == fechas_obs, "desalineación de pivotes vs repo oficial"
    tipos_db = [l.start_type for l in legs]  # "MAX"/"MIN"
    tipos_obs = obs["pivot_type"].tolist()
    assert tipos_db == tipos_obs, "desalineación de tipos de pivote vs repo"


def test_state_keys_sin_huerfanos(obs):
    """Cada state_key de la tabla debe existir en el fact store de su estación
    (evita estados fantasma que inflarían señales)."""
    rules = ROOT / "backend/modules/entry_decision/domain/rules"
    for st in STATIONS:
        fs = json.loads((rules / f"{st}_fact_store.json").read_text())
        keys = set(fs.get("states", {}).keys())
        sks = set(obs[f"{st}_sk"].dropna().astype(str))
        huerfanos = sks - keys
        assert not huerfanos, f"{st}: state_keys huérfanos: {list(huerfanos)[:3]}"


def test_cascade_reversal_no_inerte(obs):
    """Guard histórico: cascade_reversal estuvo inerte en silencio porque la
    columna cascade_conviction_50 no existía. ~240 disparos con umbral −0.957."""
    from arnes import SEÑALES
    n = int(SEÑALES["cascade_reversal"](obs).sum())
    assert 100 < n < 400, f"cascade_reversal: {n} disparos (esperado ~240)"


def test_z_bear_consistente_con_produccion(obs):
    """F1 de la auditoría Opus: z_bear debe normalizarse con los μ/σ del
    cascade_calibration.json (producción), no con constantes históricas."""
    cal = json.loads((ROOT / "backend/modules/entry_decision/domain/rules"
                      / "cascade_calibration.json").read_text())
    mu = cal["d1_bear_5"]["mean"]
    sg = cal["d1_bear_5"]["std"]
    zb = (obs["d1_bear_5"] - mu) / sg
    assert (zb - obs["z_bear"]).abs().max() < 1e-9, "z_bear inconsistente con cal-file"


def test_diamantes_no_degradados(obs):
    """Protocolo §3.3: rareza = riqueza. panico_total y skew_paranoia_exit son
    diamantes (N bajo); ninguna reclasificación futura debe borrarlos en silencio."""
    from arnes import SEÑALES
    for sig in ("panico_total", "skew_paranoia_exit"):
        n = int(SEÑALES[sig](obs).sum())
        assert 5 <= n <= 25, f"{sig}: N={n} fuera de rango diamante"


def test_n_stations_a_rango(obs):
    """BS3: n_stations_a documenta el denominador variable (2-5 estaciones)."""
    assert obs["n_stations_a"].between(0, 5).all()
    assert (obs["n_stations_a"] >= 2).mean() > 0.99
