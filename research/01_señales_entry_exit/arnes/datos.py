"""Carga de datos: pivotes de quants_obs + barras diarias de SPY.

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SCRATCH = ROOT / "data/research"
OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"
if not OBS_PKL.exists():
    OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"

def cargar_datos():
    """Carga los pivotes de quants_obs.pkl y las barras diarias de SPY desde el Vault."""
    df = pd.read_pickle(OBS_PKL).reset_index(drop=True)
    df["pivot_date"] = pd.to_datetime(df["pivot_date"])

    # ── Fase 1 V7: Deduplicación geométrica determinista ──────────────
    # Cuando un pivot_date aparece dos veces (end de pierna anterior +
    # start de pierna nueva), conservamos MIN preferente (start de ciclo
    # alcista). Sort: MIN < MAX alfabéticamente → keep='first'.
    n_before = len(df)
    df = df.sort_values(["pivot_date", "pivot_type"], ascending=[True, True])
    df = df.drop_duplicates(subset=["pivot_date"], keep="first")
    df = df.reset_index(drop=True)
    n_after = len(df)
    if n_before != n_after:
        print(f"[DEDUP] {n_before} → {n_after} pivotes ({n_before - n_after} duplicados removidos)")

    try:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        store = TimescaleDataStore()
        spy = store.load_bars("SPY", "1d")
        spy.index = pd.to_datetime(spy.index).tz_localize(None)
    except Exception as e:
        print(f"[WARN] No se pudo cargar SPY del Vault: {e}", file=sys.stderr)
        spy = None

    return df, spy

