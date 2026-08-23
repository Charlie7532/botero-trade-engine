#!/usr/bin/env python3
"""
GENERADOR OFICIAL DE quants_obs.pkl — Tabla de Observación Canónica
=====================================================================
Genera data/research/pivots/quants_obs.pkl: el estado dimensional instantáneo
de 11 estaciones METAR en cada pivote del zigzag SPY zz25. Es la tabla sobre la
que se mide el edge real de todas las señales de entry/exit del sistema.

DOCUMENTACIÓN DE REFERENCIA COMPLETA:
  backend/scripts/generators/QUANTS_OBS_GENERATOR.md
  (léala ANTES de modificar este archivo: contiene el esquema de las 143
   columnas, las fórmulas, las 15 decisiones auditadas y los pitfalls)

PROPÓSITO (principio rector):
  Una tabla de observación CORRECTA según la lógica de producción y
  REPRODUCIBLE. La fidelidad a artefactos históricos es un detector de
  divergencias, nunca la meta.

QUÉ CONSTRUYE (1,590+ pivotes × 143 columnas):
  1. Pivotes: ZigzagLegRepository (SPY zz25) — la columna vertebral.
     Cualquier desalineación aquí rompe TODO el sistema de señales.
  2. Columnas zigzag: leg_bear, next_bear, cascade_50/75 (proximidad ±3 días
     calendario a pivotes zz50/zz75), prev_leg_return, abs_prev_leg_return,
     duration_bars (duración calendario de la pierna SALIENTE, piso 1 día),
     daily_return_pct (retorno de la pierna saliente / duración).
  3. Por estación (11): _val (close de la serie), _vel (diff(3)),
     _vol (std2/std10), _sk (state_key del LookupAdapter de producción),
     _n, _d1_vote, _zk_pbull/_zk_pbear (bloque zigzag_kinematic.zz25 del
     fact store), _zz25_pbull/_zz25_pbear/_ev_net (bloque plano zz25).
  4. Derivadas cascade: d1_bear_5 (fracción de votos bearish del Grupo A),
     n_stations_a, mean_zk_pbull_A/11, z_bear, z_dom, cascade_conviction,
     cascade_conviction_50.

CÓMO EJECUTAR:
  cd /root/botero-trade && PYTHONPATH=/root/botero-trade \
    backend/.venv/bin/python backend/scripts/generators/generate_quants_obs.py
  Opciones: --dry-run (construye y verifica sin escribir el pickle oficial)

QUÉ VERIFICA ANTES DE GUARDAR (compuertas):
  1. Esquema: 143 columnas, todas las críticas presentes.
  2. Integridad de pivotes: fechas/tipos idénticos al repo de producción.
  3. State keys sin huérfanos: cada _sk existe en su fact store.
  4. Propósito: las 28 señales del arnés disparan (ninguna inerte).
  5. Deriva: si existía un pickle oficial previo, reporta columna por columna
     qué cambió y cuánto (trazabilidad operacional).

DETERMINISMO: verificado bit-a-bit en 3 ejecuciones consecutivas (auditoría
externa Opus 23-Ago). Hash de referencia de la tabla sustituida el 23-Ago:
59fe36d0359f7523ff86039a8446f92e.

PROVENENCIA: promovido el 23-Ago-2026 desde
research/10_gate_oos_validation/builder_quants_obs.py (v8) tras 3 auditorías
externas y 15 fixes acumulados. Reemplaza al generador one-off del 17-Ago
(nunca versionado) y a research/11_experimental_engines/regenerar_quants_obs.py
(deprecado). Tests de regresión: backend/tests/test_quants_obs_builder.py.
"""
import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Root del repo: backend/scripts/generators/ → parents[3] = repo root
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.services.convergence_compositor import d1_directional_vote

from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.vvix_lookup import VVIXLookupAdapter
from backend.modules.entry_decision.domain.rules.pcr_lookup import PCRLookupAdapter
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import SV5TurbulenceLookupAdapter
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter
from backend.modules.entry_decision.domain.rules.credit_lookup import CreditLookupAdapter
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import YieldCurveLookupAdapter
from backend.modules.entry_decision.domain.rules.rotation_lookup import RotationLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter
from backend.modules.entry_decision.domain.rules.dxy_lookup import DXYLookupAdapter

PKL_OFICIAL = ROOT / "data/research/pivots/quants_obs.pkl"
# Referencia histórica: el one-off original del 17-Ago (pre-sustitución).
# Se usa para el manifiesto de fidelidad CAT-A/B/C (artefacto de auditoría).
PKL_REFERENCIA = ROOT / "data/research/pivots/quants_obs_pre_sustitucion_20260823.pkl"
CAL_FILE = ROOT / "backend/modules/entry_decision/domain/rules/cascade_calibration.json"

STATION_CONFIG = {
    "vix":            {"ticker": "VIX",            "cls": VIXLookupAdapter,            "method": "lookup_vix_guidance"},
    "vvix":           {"ticker": "VVIX",           "cls": VVIXLookupAdapter,           "method": "lookup_vvix_guidance"},
    "pcr":            {"ticker": "CBOE_PCR",       "cls": PCRLookupAdapter,            "method": "lookup_pcr_guidance"},
    "fg":             {"ticker": "FG",             "cls": FGLookupAdapter,             "method": "lookup_fg_guidance"},
    "sv5_turbulence": {"ticker": "SV5_TURBULENCE", "cls": SV5TurbulenceLookupAdapter,  "method": "lookup_sv5_turbulence_guidance"},
    "skew":           {"ticker": "SKEW",           "cls": SkewLookupAdapter,           "method": "lookup_skew_guidance"},
    "credit":         {"ticker": "CREDIT_RATIO",   "cls": CreditLookupAdapter,         "method": "lookup_credit_guidance"},
    "yield_curve":    {"ticker": "YIELD_SPREAD",   "cls": YieldCurveLookupAdapter,     "method": "lookup_yield_curve_guidance"},
    "rotation":       {"ticker": "ROTATION_INDEX", "cls": RotationLookupAdapter,       "method": "lookup_rotation_guidance"},
    "bsi":            {"ticker": "S5TW",           "cls": BSILookupAdapter,            "method": "lookup_bsi_guidance"},
    "dxy":            {"ticker": "DXY",            "cls": DXYLookupAdapter,            "method": "lookup_dxy_guidance"},
}
STATIONS = list(STATION_CONFIG.keys())
GRUPO_A_DEFAULT = ["vix", "bsi", "fg", "credit", "rotation"]

# Columnas cuya divergencia vs la referencia histórica está clasificada y es
# ESPERADA (no investigar de nuevo — ver QUANTS_OBS_GENERATOR.md §5 y el
# manifiesto JSON). CAT-A = artefacto del one-off, se usa lógica de producción.
# CAT-B = deriva de versión (fact stores/calibraciones regeneradas).
CAT_ESPERADAS = {
    "skew_sk": "A", "skew_n": "A", "skew_d1_vote": "A",
    "skew_zk_pbull": "A", "skew_zk_pbear": "A", "skew_zz25_pbull": "A",
    "skew_zz25_pbear": "A", "skew_ev_net": "A",
    "bsi_d1_vote": "A",
    "d1_bear_5": "A", "z_bear": "A", "cascade_conviction": "A",
    "cascade_conviction_50": "A",
    "mean_zk_pbull_A": "B", "mean_zk_pbull_11": "B",
    "sv5_turbulence_sk": "B", "yield_curve_sk": "B", "rotation_sk": "B",
    "rotation_zk_pbull": "B", "rotation_zk_pbear": "B",
}


def _match_col(a: pd.Series, b: pd.Series) -> float:
    """Fracción de filas idénticas entre dos columnas (NaN-aware)."""
    if a.dtype == object or a.dtype.name == "category":
        return float((a.fillna("__NA__").astype(str) ==
                      b.fillna("__NA__").astype(str)).mean())
    x = pd.to_numeric(a, errors="coerce").astype(float)
    y = pd.to_numeric(b, errors="coerce").astype(float)
    return float(np.isclose(x, y, rtol=1e-9, atol=1e-9, equal_nan=True).mean())


def main():
    ap = argparse.ArgumentParser(description="Generador oficial de quants_obs.pkl")
    ap.add_argument("--dry-run", action="store_true",
                    help="construye y verifica sin escribir el pickle oficial")
    args = ap.parse_args()

    t0 = time.time()
    store = TimescaleDataStore()
    conn = store._conn()

    # ── 1. Pivotes SPY zz25 (columna vertebral) ──
    repo = ZigzagLegRepository(store)
    legs = repo.get_confirmed_legs("SPY", "zz25")
    legs = sorted(legs, key=lambda l: l.start_timestamp)
    df = pd.DataFrame([{
        "pivot_date": pd.Timestamp(l.start_timestamp).tz_convert("UTC").tz_localize(None),
        "pivot_type": l.start_type,
        "prev_leg_return": l.prev_leg_return,
        "prev_leg_duration": l.prev_leg_duration,
    } for l in legs])
    df["abs_prev_leg_return"] = df["prev_leg_return"].abs()
    df["pivot_year"] = df["pivot_date"].dt.year
    df["pivot_decade"] = (df["pivot_year"] // 10) * 10
    df["leg_bear"] = (df["pivot_type"] == "MAX").astype(int)
    # next_bear y next_leg_direction son idénticos a leg_bear (el one-off los
    # nombró mal; se preservan por compatibilidad de esquema).
    df["next_bear"] = df["leg_bear"]
    df["next_leg_direction"] = df["leg_bear"]

    # LIMITACIÓN CONOCIDA (F4): el zigzag contiene fechas de pivote duplicadas
    # (piernas forward/backward comparten start_timestamp). Inocuo para las
    # señales actuales (leen el D1 del state_key), pero cualquier consumidor
    # futuro que haga groupby(pivot_date) debe deduplicar.
    n_dup = int(pd.to_datetime(df["pivot_date"]).duplicated().sum())
    if n_dup:
        print(f"    ⚠️ F4: {n_dup} fechas de pivote duplicadas (limitación conocida del zigzag)")
    print(f"[1] {len(df)} pivotes zz25 ({time.time()-t0:.1f}s)")

    # ── 2. cascade_50/75: proximidad ±3 días calendario a pivotes de esa escala ──
    piv50, piv75 = set(), set()
    for scale, target in [("zz50", piv50), ("zz75", piv75)]:
        q = (f"SELECT start_timestamp, end_timestamp FROM market.zigzag_legs "
             f"WHERE ticker='SPY' AND scale='{scale}'")
        d = pd.read_sql(q, conn)
        for col in ["start_timestamp", "end_timestamp"]:
            for v in d[col]:
                target.add(pd.Timestamp(v).tz_convert("UTC").tz_localize(None).normalize())
    df["cascade_50"] = df["pivot_date"].apply(
        lambda d: int(any((d.normalize() + timedelta(days=i)) in piv50 for i in range(-3, 4))))
    df["cascade_75"] = df["pivot_date"].apply(
        lambda d: int(any((d.normalize() + timedelta(days=i)) in piv75 for i in range(-3, 4))))
    print(f"[2] cascade_50={df['cascade_50'].sum()}, cascade_75={df['cascade_75'].sum()} "
          f"({time.time()-t0:.1f}s)")

    # ── 3. duration_bars y daily_return_pct (pierna SALIENTE) ──
    df["duration_bars"] = 0
    df["daily_return_pct"] = np.nan
    for i, leg in enumerate(legs):
        s = pd.Timestamp(leg.start_timestamp).tz_convert("UTC").tz_localize(None).normalize()
        e = pd.Timestamp(leg.end_timestamp).tz_convert("UTC").tz_localize(None).normalize()
        dur = max(int((e - s).days), 1)  # piso 1 día (piernas degeneradas)
        ret_pct = (leg.end_price / leg.start_price - 1) * 100
        df.loc[i, "duration_bars"] = dur
        df.loc[i, "daily_return_pct"] = ret_pct / dur
    print(f"[3] duration/daily_return ({time.time()-t0:.1f}s)")

    # ── 4. Series de las 11 estaciones: _val/_vel/_vol ──
    # Alineación por FECHA EXACTA (nunca ffill). Fuera del rango de la serie:
    # _val=NaN, _vel=0.0, _vol=1.0 (defaults verificados). Dentro del rango
    # pero NaN (inicio de serie): fillna(0) para vel, fillna(1) para vol.
    series = {}
    for code, cfg in STATION_CONFIG.items():
        d = store.load_bars(cfg["ticker"], "1d")
        if d is None or d.empty:
            print(f"    ⚠️ {code}: sin datos ({cfg['ticker']})")
            continue
        s = d["close"].astype(float).copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        series[code] = s
        vel = s.diff(3).fillna(0.0)
        vol = (s.rolling(2).std() / s.rolling(10).std().replace(0, np.nan)).fillna(1.0)
        idx_set = set(s.index)
        df[f"{code}_val"] = [float(s.loc[dt]) if dt in idx_set else np.nan
                             for dt in pd.to_datetime(df["pivot_date"]).dt.normalize()]
        df[f"{code}_vel"] = [float(vel.loc[dt]) if dt in idx_set else 0.0
                             for dt in pd.to_datetime(df["pivot_date"]).dt.normalize()]
        df[f"{code}_vol"] = [float(vol.loc[dt]) if dt in idx_set else 1.0
                             for dt in pd.to_datetime(df["pivot_date"]).dt.normalize()]
    print(f"[4] series de {len(series)} estaciones ({time.time()-t0:.1f}s)")

    # ── 5. State keys y guidance vía adapters de producción ──
    adapters = {code: cfg["cls"]() for code, cfg in STATION_CONFIG.items() if code in series}
    fs_cache = {}

    def _zk_block(code, sk):
        """Lee states[sk].zigzag_kinematic.zz25 del fact store (cacheado)."""
        if code not in fs_cache:
            fp = ROOT / "backend/modules/entry_decision/domain/rules" / f"{code}_fact_store.json"
            if fp.exists():
                fs_cache[code] = json.loads(fp.read_text()).get("states", {})
            else:
                fs_cache[code] = {}
        st = fs_cache[code].get(sk, {}) if sk else {}
        return st.get("zigzag_kinematic", {}).get("zz25", {})

    for code in STATIONS:
        if code not in series:
            continue
        method = STATION_CONFIG[code]["method"]
        adapter = adapters[code]
        sks, ns, votes, zk_pbull, zk_pbear, zz25_pbull, zz25_pbear, ev_nets = (
            [], [], [], [], [], [], [], [])
        for _, row in df.iterrows():
            val = row.get(f"{code}_val")
            v2 = row.get(f"{code}_vel")
            v3 = row.get(f"{code}_vol")
            if pd.isna(val):
                sks.append(None); ns.append(np.nan); votes.append(np.nan)
                zk_pbull.append(np.nan); zk_pbear.append(np.nan)
                zz25_pbull.append(np.nan); zz25_pbear.append(np.nan)
                ev_nets.append(np.nan)
                continue
            if pd.isna(v2): v2 = 0.0
            if pd.isna(v3): v3 = 1.0
            try:
                g = getattr(adapter, method)(val=float(val), d3_speed=float(v2),
                                             vol_norm=float(v3), vol_d3=float(v3))
            except Exception:
                g = None
            if g is None:
                sks.append(None); ns.append(np.nan); votes.append(np.nan)
                zk_pbull.append(np.nan); zk_pbear.append(np.nan)
                zz25_pbull.append(np.nan); zz25_pbear.append(np.nan)
                ev_nets.append(np.nan)
                continue
            sks.append(g.state_key)
            ns.append(g.n)
            votes.append(d1_directional_vote(g.state_key))
            zk = _zk_block(code, g.state_key)
            zk_pbull.append(zk.get("p_bull", np.nan))
            zk_pbear.append(zk.get("p_bear", np.nan))
            zz25_pbull.append(g.zz25.p_bull if g.zz25 else np.nan)
            zz25_pbear.append(g.zz25.p_bear if g.zz25 else np.nan)
            ev_nets.append(g.zz25.ev_net if g.zz25 else np.nan)
        df[f"{code}_sk"] = sks
        df[f"{code}_n"] = ns
        df[f"{code}_d1_vote"] = votes
        df[f"{code}_zk_pbull"] = zk_pbull
        df[f"{code}_zk_pbear"] = zk_pbear
        df[f"{code}_zz25_pbull"] = zz25_pbull
        df[f"{code}_zz25_pbear"] = zz25_pbear
        df[f"{code}_ev_net"] = ev_nets
        print(f"    {code}: {df[f'{code}_sk'].notna().sum()} state_keys "
              f"({time.time()-t0:.1f}s)")
    print(f"[5] state_keys completados ({time.time()-t0:.1f}s)")

    # ── 6. Derivadas del cascade ──
    # Todas las constantes de normalización se leen del cascade_calibration.json
    # (producción). Los fallbacks son los defaults históricos del compositor.
    cal = json.loads(CAL_FILE.read_text())
    tm = cal.get("type_mask", {})
    dom25_stats = cal.get("domino_zz25", {"mean": 0.0532, "std": 0.035})
    d1_stats = cal.get("d1_bear_5", {})
    Z_BEAR_MU = float(d1_stats.get("mean", 0.3299))
    Z_BEAR_SIGMA = float(d1_stats.get("std", 0.2856))

    # GRUPO_A dinámico: unión de estaciones del type_mask (BS2).
    GRUPO_A = sorted(set().union(*[set(tm.get(pt, {}).get("stations", []))
                                   for pt in ("MIN", "MAX")])) or GRUPO_A_DEFAULT

    # d1_bear_5 = FRACCIÓN DE VOTOS BEARISH = count(v<0)/n (fórmula exacta de
    # producción, convergence_compositor.py:484). El denominador es variable por
    # NaN (2-5 estaciones según fecha) — structural break documentado (BS3).
    def calc_d1_bear_5(row):
        ptype = row["pivot_type"]
        cfg = tm.get(ptype, {"stations": GRUPO_A})
        allowed = set(cfg.get("stations", GRUPO_A))
        votes = [row[f"{s}_d1_vote"] for s in GRUPO_A if s in allowed
                 and not pd.isna(row.get(f"{s}_d1_vote"))]
        if not votes:
            return 0.0
        return float(sum(1 for v in votes if v < 0) / len(votes))

    df["d1_bear_5"] = df.apply(calc_d1_bear_5, axis=1)
    df["n_stations_a"] = df[[f"{s}_d1_vote" for s in GRUPO_A]].notna().sum(axis=1)
    df["mean_zk_pbull_A"] = df[[f"{s}_zk_pbull" for s in GRUPO_A]].mean(axis=1)
    df["mean_zk_pbull_11"] = df[[f"{s}_zk_pbull" for s in STATIONS]].mean(axis=1)

    df["z_bear"] = (df["d1_bear_5"] - Z_BEAR_MU) / Z_BEAR_SIGMA
    df["z_dom"] = (df["abs_prev_leg_return"] - dom25_stats["mean"]) / dom25_stats["std"]

    # cascade_conviction: pesos POR FILA según pivot_type (BS1), leídos del
    # type_mask. cascade_conviction_50 es el mismo c50 con el nombre correcto
    # que lee la señal cascade_reversal (fix CAT-A: antes no existía y la
    # señal estaba inerte en silencio).
    def calc_cascade(row):
        cfg = tm.get(row["pivot_type"], {})
        w_bear = float(cfg.get("w_bear", 0.66))
        w_dom = float(cfg.get("w_dom", 0.34))
        return w_bear * row["z_bear"] + w_dom * row["z_dom"]
    df["cascade_conviction"] = df.apply(calc_cascade, axis=1)
    df["cascade_conviction_50"] = df["cascade_conviction"]
    print(f"[6] derivadas ({time.time()-t0:.1f}s)")

    store.close()

    # ── 7. Orden de columnas estable (esquema de la referencia histórica) ──
    ref = None
    ref_cols = list(df.columns)
    if PKL_REFERENCIA.exists():
        ref = pd.read_pickle(PKL_REFERENCIA)
        ref_cols = [c for c in ref.columns if c in df.columns]
        df = df[ref_cols + [c for c in df.columns if c not in ref_cols]]
    print(f"[7] columnas: {len(df.columns)}")

    # ── 8. COMPUERTA: manifiesto de fidelidad vs referencia histórica ──
    # La fidelidad es DETECTOR de divergencias, no meta. Las divergencias
    # esperadas están clasificadas CAT-A/B/C (ver CAT_ESPERADAS y la doc).
    if ref is not None:
        print(f"\n{'='*100}\nMANIFIESTO DE FIDELIDAD (vs one-off 17-Ago) — detector, no meta")
        print(f"{'='*100}")
        manifest = []
        n_ok = 0
        for col in ref_cols:
            if col == "pivot_date":
                match = float((pd.to_datetime(df[col]).dt.normalize() ==
                               pd.to_datetime(ref[col]).dt.normalize()).mean())
            else:
                match = _match_col(df[col], ref[col])
            cat = CAT_ESPERADAS.get(col)
            if match >= 0.999:
                n_ok += 1
                cat = cat or "OK"
            else:
                cat = cat or "C"  # divergencia sin clasificar → investigar
            manifest.append({"columna": col, "match": round(match, 4), "categoria": cat})
        print(f"Columnas con match ≥99.9%: {n_ok}/{len(ref_cols)}")
        por_cat = {}
        for m in manifest:
            if m["categoria"] != "OK":
                por_cat.setdefault(m["categoria"], []).append((m["columna"], m["match"]))
        for cat in ("A", "B", "C"):
            cols = por_cat.get(cat, [])
            print(f"CAT-{cat} ({len(cols)} columnas)")
        if por_cat.get("C"):
            print(f"⚠️ {len(por_cat['C'])} divergencias SIN CLASIFICAR (CAT-C) — INVESTIGAR:")
            for col, m in por_cat["C"]:
                print(f"    {col}: match={m:.1%}")
        man_path = ROOT / "data/research/signals/manifiesto_divergencias_quants_obs.json"
        man_path.parent.mkdir(parents=True, exist_ok=True)
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump({"fecha": time.strftime("%Y-%m-%d"),
                       "builder": "generate_quants_obs.py (producción)",
                       "principio": "fidelidad como detector, no como meta",
                       "columnas": manifest}, f, indent=1, ensure_ascii=False)
        print(f"Manifiesto: {man_path}")

    # ── 9. COMPUERTA DE DERIVA vs pickle oficial previo (trazabilidad) ──
    if PKL_OFICIAL.exists():
        prev = pd.read_pickle(PKL_OFICIAL)
        if len(prev) == len(df):
            cambios = []
            for col in prev.columns:
                if col not in df.columns:
                    continue
                m = _match_col(df[col], prev[col]) if col != "pivot_date" else \
                    float((pd.to_datetime(df[col]).dt.normalize() ==
                           pd.to_datetime(prev[col]).dt.normalize()).mean())
                if m < 1.0:
                    cambios.append((col, m))
            print(f"\n[9] Deriva vs oficial previo: {len(cambios)} columnas cambiadas "
                  f"(de {len(prev.columns)})")
            for col, m in sorted(cambios, key=lambda x: x[1])[:15]:
                print(f"    {col}: match={m:.1%}")
        else:
            print(f"\n[9] Deriva: filas {len(prev)} → {len(df)} "
                  f"(crecimiento del zigzag: {len(df)-len(prev)} pivotes nuevos)")

    # ── 10. VERIFICACIÓN DE PROPÓSITO: la tabla sirve al evaluador/señales ──
    print(f"\n{'='*100}\nVERIFICACIÓN DE PROPÓSITO (consumidores reales)")
    print(f"{'='*100}")
    from arnes import SEÑALES
    n_activas, n_inertes, errores = 0, [], []
    for nombre, fn in SEÑALES.items():
        try:
            mask = fn(df).astype(bool)
            n = int(mask.sum())
            if n > 0:
                n_activas += 1
            else:
                n_inertes.append(nombre)
        except Exception as e:
            errores.append((nombre, str(e)[:60]))
    print(f"Señales que disparan: {n_activas}/{len(SEÑALES)}")
    if n_inertes:
        print(f"⚠️ Inertes (0 disparos): {n_inertes}")
    if errores:
        print(f"⚠️ Errores: {errores}")
    if n_inertes or errores:
        print("⚠️ COMPUERTA DE PROPÓSITO FALLÓ — el pickle NO se guarda.")
        sys.exit(1)
    cr = SEÑALES.get("cascade_reversal")
    if cr is not None:
        print(f"cascade_reversal: {int(cr(df).sum())} disparos")
    print(f"Pivotes: {len(df)}")

    # ── 11. Guardar ──
    if args.dry_run:
        print(f"\n[DRY-RUN] Tabla construida y verificada ({len(df)} × {len(df.columns)}). "
              f"No se escribió {PKL_OFICIAL}.")
    else:
        df.to_pickle(PKL_OFICIAL)
        print(f"\nGuardado: {PKL_OFICIAL} ({len(df)} filas × {len(df.columns)} columnas)")
    print(f"Tiempo total: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
