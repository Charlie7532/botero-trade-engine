#!/usr/bin/env python3
"""
BUILDER VERSIONADO DE quants_obs.pkl (22-Ago-2026)
===================================================
Reemplaza el generador one-off del 17-Ago que nunca fue versionado.

Construye: 1,590 pivotes SPY zz25 × 141 columnas:
  1. Pivotes: ZigzagLegRepository (SPY zz25) — verificado que reproduce el pickle
  2. Columnas zigzag: leg_bear, next_bear, cascade_50/75 (proximidad ±3 días a
     pivotes zz50/zz75), prev_leg_return, abs_prev_leg_return, duration_bars
  3. Por estación (11): _val, _vel (diff(3)), _vol (std2/std10), _sk (adapter
     de producción con fallback), _n, _d1_vote, _zk_pbull, _zk_pbear,
     _zz25_pbull/pbear, _ev_net
  4. Derivadas: d1_bear_5 (Grupo A con type_mask), mean_zk_pbull_A/11,
     z_bear, z_dom, cascade_conviction, daily_return_pct, next_leg_direction

REGLA DE FIDELIDAD: reproduce el pickle original. Los state_keys vienen de los
LookupAdapters de producción (edges estáticos del fact store), NO del binneo
expanding del v3_fact_table_engine. Compara contra el original antes de guardar.

Uso:
  cd /root/botero-trade && PYTHONPATH=/root/botero-trade \
    backend/.venv/bin/python research/10_gate_oos_validation/builder_quants_obs.py
"""
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
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

PKL_OUT = ROOT / "data/research/pivots/quants_obs_new.pkl"
PKL_ORIGINAL = ROOT / "data/research/pivots/quants_obs.pkl"
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


def main():
    t0 = time.time()
    store = TimescaleDataStore()
    conn = store._conn()

    # ── 1. Pivotes SPY zz25 ──
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
    # FIX (forensia 22-Ago): next_bear y next_leg_direction son IDÉNTICOS a leg_bear
    # en el pickle original (match 100% con (pivot_type=="MAX")). El generador
    # original los nombró mal; se preservan por fidelidad al esquema de 141 columnas.
    df["next_bear"] = df["leg_bear"]
    df["next_leg_direction"] = df["leg_bear"]

    # LIMITACIÓN CONOCIDA (auditoría Opus 23-Ago, F4): el zigzag SPY zz25 contiene
    # 236 fechas de pivote duplicadas (piernas forward/backward que comparten
    # start_timestamp, ej. 1997-01-10 MAX→MIN same-day). Es una propiedad del zigzag
    # almacenado en market.zigzag_legs, NO un bug del builder (el original tiene las
    # mismas 236). Inocuo para CATALOGO_V7 (las señales leen solo el D1 del state_key),
    # pero cualquier futuro consumidor que haga groupby(pivot_date) debe deduplicar.
    n_dup = int(pd.to_datetime(df["pivot_date"]).duplicated().sum())
    if n_dup:
        print(f"    ⚠️ F4: {n_dup} fechas de pivote duplicadas (limitación conocida del zigzag)")

    print(f"[1] {len(df)} pivotes zz25 ({time.time()-t0:.1f}s)")

    # ── 2. cascade_50/75: proximidad ±3 días a pivotes de esa escala ──
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

    # ── 3. SPY: daily_return_pct y duration_bars ──
    # FIX (forensia 22-Ago): duration_bars = duración CALENDARIO de la pierna que
    # ARRANCA en el pivote (leg saliente), con piso de 1 día (piernas degeneradas
    # de longitud cero → 1). daily_return_pct = retorno de esa pierna (%) / duración.
    # Verificado: match 100% en ambas columnas vs el pickle original.
    df["duration_bars"] = 0
    df["daily_return_pct"] = np.nan
    for i, leg in enumerate(legs):
        s = pd.Timestamp(leg.start_timestamp).tz_convert("UTC").tz_localize(None).normalize()
        e = pd.Timestamp(leg.end_timestamp).tz_convert("UTC").tz_localize(None).normalize()
        dur = max(int((e - s).days), 1)
        ret_pct = (leg.end_price / leg.start_price - 1) * 100
        df.loc[i, "duration_bars"] = dur
        df.loc[i, "daily_return_pct"] = ret_pct / dur
    print(f"[3] duration/daily_return ({time.time()-t0:.1f}s)")

    # ── 4. Series de las 11 estaciones: _val/_vel/_vol ──
    # FIX (forensia 22-Ago): alineación por FECHA EXACTA (no ffill). Fuera del
    # rango de la serie: _val=NaN, _vel=0.0, _vol=1.0 (defaults del original,
    # verificado con PCR: match 100%). Dentro del rango pero NaN (inicio de serie):
    # fillna(0) para vel, fillna(1) para vol.
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
    # FIX Familia 1 (forensia 22-Ago): {st}_zk_pbull/pbear provienen del bloque
    # zigzag_kinematic.zz25 del fact store (match 100% verificado para VIX),
    # mientras {st}_zz25_pbull/pbear y _ev_net provienen del bloque plano zz25
    # (93.9%/92.6% — deriva de versión de fact stores; irreproducible hoy).
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
            votes.append(d1_directional_vote(g.state_key, code))
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
    cal = json.loads(CAL_FILE.read_text())
    tm = cal.get("type_mask", {})
    # FIX (forensia 22-Ago): z_dom usa μ/σ del calibration file (match 100%).
    # z_bear NO usa los μ/σ del cal-file actual (0.41/0.3206) ni full-sample de la
    # columna guardada (0.3726/0.2964): la ingeniería inversa dio μ=0.3299 σ=0.2856
    # (match 99.94%), evidenciando que el generador original normalizó contra una
    # d1_bear_5 de versión previa (deriva). Se usan las constantes invertidas para
    # máxima fidelidad; documentado como artefacto de versión.
    dom25_stats = cal.get("domino_zz25", {"mean": 0.0532, "std": 0.035})
    # FIX F1 (auditoría Opus 23-Ago, P0): los μ/σ de z_bear se leen DINÁMICAMENTE del
    # cascade_calibration.json para mantener consistencia con la producción actual.
    # Antes: hardcoded 0.3299/0.2856 (defaults del compositor, coincidían con el cal-file
    # al momento de generarse el one-off). El cal-file fue actualizado a 0.41/0.3206,
    # creando 17.9% de filas con z_bear de signo invertido respecto a producción.
    # Opción C de la auditoría: leer del cal-file, fallback a defaults del compositor.
    d1_stats = cal.get("d1_bear_5", {})
    Z_BEAR_MU = float(d1_stats.get("mean", 0.3299))
    Z_BEAR_SIGMA = float(d1_stats.get("std", 0.2856))

    # FIX BS2 (auditoría profunda Opus 23-Ago): GRUPO_A se lee del type_mask del
    # cal-file (unión de estaciones de MIN y MAX), no hardcoded. Si se añade una
    # estación al cal-file, el builder la incorpora automáticamente.
    GRUPO_A = sorted(set().union(*[set(tm.get(pt, {}).get("stations", []))
                                   for pt in ("MIN", "MAX")])) or GRUPO_A_DEFAULT

    # FIX F3 (auditoría Opus 23-Ago, P1) + autoauditoría 22-Ago: d1_bear_5 es la
    # FRACCIÓN DE VOTOS BEARISH = count(v<0)/n, la fórmula exacta de producción
    # (convergence_compositor.py:484 → n_bearish/n_votes). Se usa el CONTEO en vez de
    # Σ(max(0,−v)) porque la equivalencia algebraica entre ambas solo se sostiene
    # mientras el dominio de votos sea {−1,0,1}; con votos fraccionarios (como el −0.5
    # histórico de OVERSOLD_BREADTH) divergirían en silencio. El conteo es robusto.
    # Verificado: idéntico a la columna del pickle original donde no hay filas OVERSOLD,
    # y coincide con la lectura de producción en el 100% de los casos con dominio actual.
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
    # FIX BS3 (auditoría profunda Opus 23-Ago, P1): el denominador de d1_bear_5 es
    # variable por NaN (2-5 estaciones según fecha: antes de 2011 solo 2-4 estaciones
    # disponibles). Esto crea un structural break en la escala de d1_bear_5/z_bear
    # (incrementos de 0.50 con 2 estaciones vs 0.20 con 5). Se emite n_stations_a
    # para que cualquier análisis pueda segmentar/normalizar por disponibilidad.
    # 64.2% de los pivotes tienen <5 estaciones; la primera fila con 5 es 2011-02-18.
    df["n_stations_a"] = df[[f"{s}_d1_vote" for s in GRUPO_A]].notna().sum(axis=1)
    df["mean_zk_pbull_A"] = df[[f"{s}_zk_pbull" for s in GRUPO_A]].mean(axis=1)
    df["mean_zk_pbull_11"] = df[[f"{s}_zk_pbull" for s in STATIONS]].mean(axis=1)

    df["z_bear"] = (df["d1_bear_5"] - Z_BEAR_MU) / Z_BEAR_SIGMA
    df["z_dom"] = (df["abs_prev_leg_return"] - dom25_stats["mean"]) / dom25_stats["std"]

    # FIX F5 (auditoría profunda 23-Ago): los pesos de cascade_conviction se leen
    # del type_mask del cal-file. MIN/MAX tienen pesos idénticos 0.66/0.34 hoy, pero
    # se leen dinámicamente para que un cambio futuro de calibración se propague.
    # FIX BS1 (auditoría profunda Opus 23-Ago): los pesos se aplican POR FILA según
    # pivot_type, no MIN para todos. Hoy inocuo (pesos MIN==MAX), pero si el cal-file
    # diferenciara pesos, cada pivote tendría los correctos.
    def calc_cascade(row):
        cfg = tm.get(row["pivot_type"], {})
        w_bear = float(cfg.get("w_bear", 0.66))
        w_dom = float(cfg.get("w_dom", 0.34))
        return w_bear * row["z_bear"] + w_dom * row["z_dom"]
    df["cascade_conviction"] = df.apply(calc_cascade, axis=1)

    # FIX CAT-A (autoauditoría propósito 22-Ago): cascade_conviction_50 ES c50 del
    # compositor de producción (convergence_compositor.py:503 → c50 = w_bear*z_bear +
    # w_dom*z_dom25 = 0.66*z_bear + 0.34*z_dom). El one-off del 17-Ago guardó c50 bajo
    # el nombre 'cascade_conviction' y la señal cascade_reversal lee el nombre correcto
    # 'cascade_conviction_50' — que nunca existió, haciendo la señal inerte en silencio.
    # Se emite con el nombre correcto para que el propósito (medir señales) se cumpla.
    df["cascade_conviction_50"] = df["cascade_conviction"]
    print(f"[6] derivadas ({time.time()-t0:.1f}s)")

    store.close()

    # ── 7. Ordenar columnas como el original y guardar ──
    orig = pd.read_pickle(PKL_ORIGINAL)
    orig_cols = [c for c in orig.columns if c in df.columns]
    missing = [c for c in orig.columns if c not in df.columns]
    extra = [c for c in df.columns if c not in orig_cols]
    df = df[orig_cols + [c for c in df.columns if c not in orig_cols]]
    print(f"[7] columnas: {len(df.columns)} (original: {len(orig.columns)}) | "
          f"faltantes: {missing} | extra: {extra}")

    # ── 8. COMPUERTA DE FIDELIDAD + MANIFIESTO DE DIVERGENCIAS ──
    # Principio rector: la fidelidad es DETECTOR de divergencias, no meta.
    # Cada divergencia se clasifica CAT-A/B/C según la autoauditoría de propósito.
    CAT = {
        # CAT-A: artefacto no reproducible del one-off → tabla usa lógica de producción
        # (1) skew: bins D1 solapados, clasificador irreproducible (trailing rechazada máx 41.9%)
        "skew_sk": "A", "skew_n": "A", "skew_d1_vote": "A",
        "skew_zk_pbull": "A", "skew_zk_pbear": "A", "skew_zz25_pbull": "A",
        "skew_zz25_pbear": "A", "skew_ev_net": "A",
        # (2) bsi_d1_vote: el pickle usa −0.5 para OVERSOLD_BREADTH; la función de
        # producción d1_directional_vote usa 0. El builder usa producción (CAT-A).
        "bsi_d1_vote": "A",
        # (2b) P3+ (auditoría profunda Opus 23-Ago): stealth_tail_hedging lee SKEW D3
        # (skew_sk.split("__")[2]); la reclasificación CAT-A de skew cambia el
        # state_key completo → 8 filas migran (N=31 estable, PROPOSED, marginal).
        "stealth_tail_hedging_note": "A",
        # CAT-A raíz (2): la escala de votos −0.5 de OVERSOLD_BREADTH propaga a
        # d1_bear_5 / z_bear / cascade_conviction en EXACTAMENTE las 428 filas
        # OVERSOLD (428/1590 = 26.9% → match 73.1%). No es deriva misteriosa: es un
        # único artefacto de escala de votos. La fórmula de presión bearish
        # Σ(max(0,−v))/n con votos de producción es idéntica a la del compositor
        # actual (convergence_compositor.py:484 → n_bearish/n_votes).
        "d1_bear_5": "A", "z_bear": "A", "cascade_conviction": "A",
        "cascade_conviction_50": "A",
        # FIX F1 (Opus 23-Ago): z_bear y cascade_conviction ahora usan μ/σ del
        # cal-file ACTUAL (0.41/0.3206) — consistencia con producción, no fidelidad
        # al one-off. El match vs original cae a ~0% a propósito: el one-off fue
        # generado con una calibración obsoleta (0.3299/0.2856). 17.9% de filas
        # tenían signo invertido respecto a producción; ahora 0%.
        # CAT-B: deriva de versión (fact stores regenerados / μσ históricos / edges)
        "mean_zk_pbull_A": "B", "mean_zk_pbull_11": "B",
        # (3) 1 fila en sv5/yield_curve/rotation con mismo _val pero distinto D1:
        # casos de borde donde los edges del fact store derivaron → CAT-B
        "sv5_turbulence_sk": "B", "yield_curve_sk": "B", "rotation_sk": "B",
    }
    # el resto de divergencias zz25/ev_net → CAT-B (bloque plano regenerado)
    for code in STATIONS:
        for suf in ("zz25_pbull", "zz25_pbear", "ev_net"):
            CAT.setdefault(f"{code}_{suf}", "B")
    # rotation_zk_pbull/pbear (97%): bloque kinematic de rotation también fue
    # regenerado con edges trailing → CAT-B (deriva de versión)
    CAT.setdefault("rotation_zk_pbull", "B")
    CAT.setdefault("rotation_zk_pbear", "B")

    print(f"\n{'='*100}\nCOMPUERTA DE FIDELIDAD (builder vs original) — detector, no meta")
    print(f"{'='*100}")
    manifest = []
    n_ok = 0
    for col in orig_cols:
        if col == "pivot_date":
            match = (pd.to_datetime(df[col]).dt.normalize() ==
                     pd.to_datetime(orig[col]).dt.normalize()).mean()
        elif df[col].dtype == object or df[col].dtype.name == "category":
            match = (df[col].fillna("__NA__").astype(str) ==
                     orig[col].fillna("__NA__").astype(str)).mean()
        else:
            a = pd.to_numeric(df[col], errors="coerce").astype(float)
            b = pd.to_numeric(orig[col], errors="coerce").astype(float)
            close = np.isclose(a, b, rtol=1e-9, atol=1e-9, equal_nan=True)
            match = close.mean()
        cat = CAT.get(col)
        if match >= 0.999:
            n_ok += 1
            cat = cat or "OK"
        else:
            cat = cat or "C"  # divergencia sin clasificar → CAT-C por defecto
        manifest.append({"columna": col, "match": round(float(match), 4), "categoria": cat})
    print(f"Columnas con match ≥99.9%: {n_ok}/{len(orig_cols)}")
    divergentes = [m for m in manifest if m["categoria"] != "OK"]
    por_cat = {}
    for m in divergentes:
        por_cat.setdefault(m["categoria"], []).append((m["columna"], m["match"]))
    for cat in ("A", "B", "C"):
        cols = por_cat.get(cat, [])
        print(f"\nCAT-{cat} ({len(cols)} columnas):")
        for col, m in sorted(cols, key=lambda x: x[1]):
            print(f"    {col}: match={m:.1%}")
    no_clasificadas = por_cat.get("C", [])
    if no_clasificadas:
        print(f"\n⚠️ {len(no_clasificadas)} divergencias SIN CLASIFICAR (CAT-C por defecto)")

    man_path = ROOT / "data/research/signals/manifiesto_divergencias_quants_obs.json"
    man_path.parent.mkdir(parents=True, exist_ok=True)
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump({"fecha": "2026-08-22", "builder": "v3",
                   "principio": "fidelidad como detector, no como meta",
                   "columnas": manifest}, f, indent=1, ensure_ascii=False)
    print(f"\nManifiesto: {man_path}")

    # ── 9. VERIFICACIÓN DE PROPÓSITO: la tabla debe servir al evaluador/señales ──
    print(f"\n{'='*100}\nVERIFICACIÓN DE PROPÓSITO (consumidores reales)")
    print(f"{'='*100}")
    sys.path.insert(0, str(ROOT / "research/01_señales_entry_exit"))
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
    print(f"Señales que disparan en la tabla nueva: {n_activas}/{len(SEÑALES)}")
    print(f"Inertes (0 disparos): {n_inertes}")
    if errores:
        print(f"Errores: {errores}")
    cr = SEÑALES.get("cascade_reversal")
    if cr is not None:
        n_cr = int(cr(df).sum())
        print(f"cascade_reversal: {n_cr} disparos "
              f"({'CAT-A RESUELTO — ahora funciona' if n_cr > 0 else 'SIGUE INERTE'})")
    # pivotes: columna vertebral
    print(f"Pivotes: {len(df)} (esperado 1,590 + crecimiento del zigzag)")

    df.to_pickle(PKL_OUT)
    print(f"\nGuardado: {PKL_OUT} ({len(df)} filas × {len(df.columns)} columnas)")
    print(f"Tiempo total: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
