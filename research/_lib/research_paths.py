"""
PUNTO ÚNICO DE RESOLUCIÓN DE RUTAS — Research Lab.

Todos los scripts de research importan de aquí. Cuando movemos archivos,
actualizamos UNA constante en UN archivo. No tocamos 50 scripts.

Uso:
    from research._lib.research_paths import ROOT, PIVOTS, DATA
    import sys; sys.path.insert(0, str(ROOT))
"""
from pathlib import Path

# Resolución robusta: sube hasta encontrar backend/
_here = Path(__file__).resolve()
ROOT = _here
while not (ROOT / "backend").is_dir():
    ROOT = ROOT.parent

# ── Zonas principales ──
DATA     = ROOT / "data"
RESEARCH = ROOT / "research"

# ── Datasets compartidos (en data/research/) ──
PIVOTS   = DATA / "research" / "pivots" / "quants_obs.pkl"
D2_OBS   = DATA / "research" / "pivots" / "d2_direction_obs.pkl"
LAKE_V21 = DATA / "research" / "feature_lake" / "sprint2_redo_lake_v21.pkl"
CACHE    = DATA / "cache"


def signal_output(signal_name: str) -> Path:
    """Ruta canónica para medicion_{signal_name}.json"""
    return DATA / "research" / "signals" / f"medicion_{signal_name}.json"


def get_vault():
    """Retorna TimescaleDataStore. Import lazy para no requerir DB en tests."""
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.modules.shared.infrastructure.timescale_data_store import (
        TimescaleDataStore,
    )
    return TimescaleDataStore()
