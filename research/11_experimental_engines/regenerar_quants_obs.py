#!/usr/bin/env python3
"""
REGENERAR COLUMNAS ROTAS DE data/research/pivots/quants_obs.pkl
===================================================
P0 — Cirugía mínima sobre quants_obs.pkl (1,590 pivotes SPY zz25, 1993-2026).

DEFECTOS (ya diagnosticados):
1. Las 11 columnas {station}_n están en 0 (rotas). Deben contener el N
   (tamaño de muestra) del estado actual de cada estación, leído del fact store
   vía state_key ({station}_sk).
2. 6 state_keys de SKEW están OBSOLETOS (tras reentrenar el fact store SKEW con
   corte post-2011-02-01 ya no existen) → 17 filas con NaN al joinear.

ALCANCE (PROHIBIDO tocar cualquier otra cosa):
- SOLO se modifican: las 11 columnas {station}_n y (para SKEW) skew_sk + skew_n
  en las 17 filas con state_key obsoleto.
- NO se recomputa cascade, prev_leg_return, ni ninguna otra columna.
- NO cambia el número de filas (1,590) ni el orden de filas.
- Respaldo byte-a-byte previo a data/research/pivots/quants_obs.pkl.bak.

Intérprete:
  cd /root/botero-trade && PYTHONPATH=/root/botero-trade \
    backend/.venv/bin/python research/regenerar_quants_obs.py

Salidas:
  - data/research/pivots/quants_obs.pkl         (regenerado)
  - data/research/pivots/quants_obs.pkl.bak     (respaldo byte-a-byte del original)
  - data/research/misc/regenerar_quants_obs_report.json
"""

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
SCRATCH = ROOT / "data/research"
FS_DIR = ROOT / "backend/modules/entry_decision/domain/rules"

PKL = SCRATCH / "quants_obs.pkl"
BAK = SCRATCH / "quants_obs.pkl.bak"
REPORT = SCRATCH / "regenerar_quants_obs_report.json"

# Hacer importable el paquete backend (por si no se corre con PYTHONPATH).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew", "credit",
    "yield_curve", "rotation", "bsi", "dxy",
]


def load_fact_store_n_lookup(station: str) -> dict:
    """state_key -> n (campo top-level del estado)."""
    fp = FS_DIR / f"{station}_fact_store.json"
    with open(fp, "r", encoding="utf-8") as f:
        fs = json.load(f)
    states = fs.get("states", {})
    return {sk: sd.get("n") for sk, sd in states.items() if isinstance(sd, dict)}


def classify_skew_obs(adapter, val, vel, vol):
    """Re-clasifica una observación raw de SKEW con las edges ACTUALES.

    Usa el adaptador de producción (skew_lookup.py), que implementa la cadena de
    fallback exacta: D1__D2__D3 -> D1__D2__VOL_NEUTRAL_BASELINE -> D1__D2__* -> D1__*.
    Devuelve (state_key, n, exact_key, used_fallback) o (None, None, None, None)
    si el dato falta.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None, None, None, None
    g = adapter.lookup_skew_guidance(val=val, d3_speed=vel, vol_norm=vol)
    if g is None:
        return None, None, None, None
    # Key EXACTO D1__D2__D3 (sin fallback), para documentar si hubo fallback.
    d1 = adapter._classify_d1(val)
    d2 = adapter._classify_d2(vel)
    d3 = adapter._classify_d3(vol)
    exact_key = f"{d1}__{d2}__{d3}"
    used_fallback = (exact_key != g.state_key)
    return g.state_key, g.n, exact_key, used_fallback


def main():
    print("=" * 92)
    print("REGENERAR COLUMNAS ROTAS DE quants_obs.pkl — P0 (cirugía mínima)")
    print("=" * 92)

    # ── PASO 0: respaldo byte-a-byte ANTES de tocar nada ──
    if not PKL.exists():
        raise FileNotFoundError(f"No existe {PKL}")
    shutil.copy2(PKL, BAK)
    bak_bytes = BAK.stat().st_size
    print(f"\n[RESPALDO] {PKL.name} -> {BAK.name} ({bak_bytes:,} bytes)")

    # ── PASO 1: cargar ──
    print("\n[PASO 1] Cargando quants_obs.pkl ...")
    df = pd.read_pickle(PKL)
    n_rows = len(df)
    cols_orig = list(df.columns)
    idx_orig = df.index
    print(f"  Filas: {n_rows} | Columnas: {len(cols_orig)}")

    orig = df.copy(deep=True)  # snapshot para verificación final

    # Columnas que SÍ se van a tocar (las únicas).
    touched = [f"{s}_n" for s in STATIONS] + ["skew_sk"]
    untouched = [c for c in cols_orig if c not in touched]
    print(f"  Columnas tocadas (único alcance permitido): {touched}")

    # ── PASO 2: llenar {station}_n desde el fact store vía state_key ──
    print("\n[PASO 2] Llenando {station}_n desde cada fact store vía state_key ...")
    per_station = {}
    for s in STATIONS:
        lookup = load_fact_store_n_lookup(s)
        sk_col = f"{s}_sk"
        n_col = f"{s}_n"
        df[n_col] = df[sk_col].map(lookup)
        nonnull = int(df[sk_col].notna().sum())
        matched = int(df.loc[df[sk_col].notna(), sk_col].isin(lookup.keys()).sum())
        per_station[s] = {
            "state_key_nonnull": nonnull,
            "state_key_matched": matched,
            "state_key_mismatch": nonnull - matched,
        }
        print(f"    {s:16s} matched={matched:5d}/{nonnull} mismatch={nonnull - matched}")

    # ── PASO 3: SKEW — re-clasificar los 6 state_keys obsoletos ──
    print("\n[PASO 3] SKEW — re-clasificar state_keys obsoletos (edges post-2011) ...")
    from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

    adapter = SkewLookupAdapter()
    states_skew = adapter.states

    sk_vals = df["skew_sk"].dropna()
    obsolete_keys = sorted([k for k in sk_vals.unique() if k not in states_skew])
    obsolete_counts = {k: int((df["skew_sk"] == k).sum()) for k in obsolete_keys}
    print(f"  State_keys obsoletos detectados: {len(obsolete_keys)}")
    for k in obsolete_keys:
        print(f"    - {k!r} ({obsolete_counts[k]} filas)")

    reclassified = []
    for idx in df.index:
        sk = df.at[idx, "skew_sk"]
        if pd.notna(sk) and sk in obsolete_keys:
            r = df.loc[idx]
            new_key, new_n, exact_key, used_fallback = classify_skew_obs(
                adapter, r["skew_val"], r["skew_vel"], r["skew_vol"]
            )
            old_key = sk
            if new_key is not None:
                df.at[idx, "skew_sk"] = new_key
                df.at[idx, "skew_n"] = new_n
                reclassified.append({
                    "index": int(idx),
                    "pivot_date": str(r["pivot_date"]),
                    "old_key": old_key,
                    "exact_key_D1_D2_D3": exact_key,
                    "new_key": new_key,
                    "used_fallback": bool(used_fallback),
                    "n": int(new_n) if new_n is not None else None,
                })
            else:
                # Dato faltante: no re-clasificable -> NaN (documentado).
                df.at[idx, "skew_n"] = np.nan
                reclassified.append({
                    "index": int(idx),
                    "pivot_date": str(r["pivot_date"]),
                    "old_key": old_key,
                    "exact_key_D1_D2_D3": None,
                    "new_key": None,
                    "used_fallback": False,
                    "n": None,
                    "note": "skew_val NaN -> no re-clasificable",
                })

    print(f"  Filas re-clasificadas: {len(reclassified)}")
    n_fallback = sum(1 for r in reclassified if r.get("used_fallback"))
    n_not_reclass = sum(1 for r in reclassified if r.get("new_key") is None)
    n_exact = len(reclassified) - n_fallback - n_not_reclass
    print(f"    exactas en fact store (sin fallback): {n_exact} | "
          f"con fallback del adaptador: {n_fallback} | no re-clasificables: {n_not_reclass}")

    # ── PASO 4: guardar ──
    print("\n[PASO 4] Guardando pickle regenerado ...")
    df.to_pickle(PKL)
    print(f"  Escrito {PKL} ({PKL.stat().st_size:,} bytes)")

    # ── PASO 5: verificación ──
    print("\n[PASO 5] VERIFICACIÓN ...")
    df_new = pd.read_pickle(PKL)

    # 5a. estructura intacta
    n_rows_ok = len(df_new) == n_rows
    cols_ok = list(df_new.columns) == cols_orig
    idx_ok = df_new.index.equals(idx_orig)
    print(f"  Filas 1,590 intactas: {n_rows_ok} ({len(df_new)})")
    print(f"  Columnas intactas: {cols_ok}")
    print(f"  Índice/orden intacto: {idx_ok}")

    # 5b. columnas NO tocadas idénticas
    untouched_identical = orig[untouched].equals(df_new[untouched])
    per_col_diff = [
        c for c in untouched
        if not orig[c].equals(df_new[c])
    ]
    print(f"  Columnas no tocadas idénticas: {untouched_identical} (diffs: {len(per_col_diff)})")
    if per_col_diff:
        print(f"    ¡¡DIFERENCIAS INESPERADAS!! {per_col_diff}")

    # 5c. skew_sk: exactamente 17 filas cambiadas
    def normalize_sk(s):
        return s.fillna("__NA__")
    skew_changed = int((normalize_sk(df_new["skew_sk"]) != normalize_sk(orig["skew_sk"])).sum())
    print(f"  skew_sk filas cambiadas: {skew_changed} (esperado 17)")

    # 5d. {station}_n ya no todo a cero + rango/distribución
    print("\n  Distribución de {station}_n (tras regenerar):")
    n_stats = {}
    for s in STATIONS:
        col = f"{s}_n"
        v = df_new[col]
        nonnull = v.dropna()
        stats = {
            "dtype": str(v.dtype),
            "n_nonnull": int(nonnull.count()),
            "n_nan": int(v.isna().sum()),
            "n_zero": int((v == 0).sum()),
            "min": float(nonnull.min()) if len(nonnull) else None,
            "max": float(nonnull.max()) if len(nonnull) else None,
            "mean": float(nonnull.mean()) if len(nonnull) else None,
            "median": float(nonnull.median()) if len(nonnull) else None,
            "unique": int(nonnull.nunique()),
        }
        n_stats[s] = stats
        print(f"    {s:16s} nonnull={stats['n_nonnull']:5d} nan={stats['n_nan']:5d} "
              f"zero={stats['n_zero']:5d} min={stats['min']} max={stats['max']} "
              f"median={stats['median']}")

    # 5e. SKEW sin state_keys obsoletos
    sk_remaining_obsolete = [
        k for k in df_new["skew_sk"].dropna().unique() if k not in states_skew
    ]
    print(f"\n  SKEW state_keys obsoletos restantes: {len(sk_remaining_obsolete)}")
    if sk_remaining_obsolete:
        print(f"    {sk_remaining_obsolete}")

    # checksum de columnas no tocadas (para el reporte)
    untouched_hash_before = hashlib.md5(
        pd.util.hash_pandas_object(orig[untouched], index=False).values.tobytes()
    ).hexdigest()
    untouched_hash_after = hashlib.md5(
        pd.util.hash_pandas_object(df_new[untouched], index=False).values.tobytes()
    ).hexdigest()

    # ── Reporte ──
    report = {
        "meta": {
            "script": "regenerar_quants_obs.py",
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "input": str(PKL),
            "backup": str(BAK),
            "backup_bytes": bak_bytes,
            "report": str(REPORT),
            "n_rows": n_rows,
            "n_columns": len(cols_orig),
            "stations": STATIONS,
            "touched_columns": touched,
            "fact_store_dir": str(FS_DIR),
            "skew_reclassification_method": (
                "skew_lookup.SkewLookupAdapter.lookup_skew_guidance() — edges actuales "
                "skew_edges_d1/d2/d3 + cadena de fallback de producción "
                "(D1__D2__D3 -> D1__D2__VOL_NEUTRAL_BASELINE -> D1__D2__* -> D1__*)"
            ),
        },
        "per_station_state_key_match": per_station,
        "per_station_n": n_stats,
        "skew_obsolete": {
            "n_obsolete_keys": len(obsolete_keys),
            "n_rows": sum(obsolete_counts.values()),
            "obsolete_keys": [
                {"key": k, "n_rows": obsolete_counts[k]} for k in obsolete_keys
            ],
            "reclassified_rows": reclassified,
        },
        "verification": {
            "n_rows_unchanged": n_rows_ok,
            "columns_unchanged": cols_ok,
            "index_order_unchanged": idx_ok,
            "untouched_columns_identical": untouched_identical,
            "untouched_columns_diff": per_col_diff,
            "untouched_columns_md5_before": untouched_hash_before,
            "untouched_columns_md5_after": untouched_hash_after,
            "skew_sk_changed_rows": skew_changed,
            "skew_sk_changed_rows_expected": 17,
            "skew_obsolete_keys_remaining": len(sk_remaining_obsolete),
            "skew_obsolete_keys_remaining_list": sk_remaining_obsolete,
            "all_n_no_longer_all_zero": all(
                n_stats[s]["n_zero"] == 0 for s in STATIONS
            ),
        },
    }

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[REPORTE] {REPORT}")

    # Resumen final
    ok = (
        n_rows_ok and cols_ok and idx_ok and untouched_identical
        and skew_changed == 17 and len(sk_remaining_obsolete) == 0
    )
    print("\n" + "=" * 92)
    print("RESULTADO:", "OK ✓" if ok else "REVISAR ✗")
    print("=" * 92)


if __name__ == "__main__":
    main()
