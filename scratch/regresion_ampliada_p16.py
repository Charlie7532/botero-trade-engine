#!/usr/bin/env python3
"""Regresión ampliada (P1.6): sorpresa_total y regime_change_exit contra el
God file ORIGINAL real (backup), con paths corregidos por vivir en _deprecated/."""
import sys, json, importlib.util
from pathlib import Path

sys.path.insert(0, "research/01_señales_entry_exit")

spec = importlib.util.spec_from_file_location(
    "godfile", "research/01_señales_entry_exit/_deprecated/medir_senal_godfile_1497L_backup.py")
god = importlib.util.module_from_spec(spec)
spec.loader.exec_module(god)
# CORREGIR los paths del backup (vive un nivel más profundo que el original)
god.ROOT = Path("/root/botero-trade")
god.OBS_PKL = Path("/root/botero-trade/data/research/pivots/quants_obs.pkl")
god._FS_DIR = Path("/root/botero-trade/backend/modules/entry_decision/domain/rules")
print("backup paths corregidos | FS_DIR existe:", god._FS_DIR.exists())

from arnes import cargar_datos as cargar_new, medir as medir_new

df_old, spy_old = god.cargar_datos()
df_new, spy_new = cargar_new()
print(f"datos: old={len(df_old)} new={len(df_new)} pivotes")

for sig in ["sorpresa_total", "regime_change_exit"]:
    rep_old = god.medir(sig, df_old, "next_leg", spy=spy_old, n_iter=3000, seed=42)
    rep_new = medir_new(sig, df_new, "next_leg", spy=spy_new, n_iter=3000, seed=42)
    json.dump(rep_old, open(f"/tmp/regression_godfile/{sig}_GOD.json", "w"),
              indent=2, ensure_ascii=False, default=str)
    json.dump(rep_new, open(f"/tmp/regression_godfile/{sig}_NEW.json", "w"),
              indent=2, ensure_ascii=False, default=str)
    print(f"{sig}: OK")
