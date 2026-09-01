#!/usr/bin/env python3
"""
EVALUADOR GENERALIZADO DE SEÑALES (CONTINUO VELA A VELA)
==========================================================
Evalúa señales a lo largo de toda la serie continua diaria (Lake METAR: 8,453 barras, 1993→2026),
sin restringir el disparo a días de pivote previo.

Principios Metodológicos Fundamentales:
  1. Continuidad y De-clustering Dinámico:
     Las barras consecutivas activas se agrupan en EPISODIOS CONTINUOS.
     La medición de First-Passage se realiza desde la primera vela del episodio (donde se ejecuta la orden).
  2. First-Passage Real Vela a Vela (Triple Barrier):
     Desde el momento del disparo, camina vela a vela hacia adelante midiendo si alcanza antes
     la barrera favorable o adversa en 3 escalas ZigZag: zz25 (2.5%), zz50 (5.0%), zz75 (7.5%).
  3. Calificación Canónica de Timing (6 Slots en Barras de Trading):
     Mide la distancia exacta en velas de mercado al pivote ZigZag del tipo BLANCO (MIN/MAX) más cercano:
     [t-2: Anticipada 2v, t-1: Anticipada 1v, t=0: Exacta, t+1: Retrasada 1v, t+2: Retrasada 2v, ENTRE: Fuera de rango].
  4. Rendimiento Condicional al Timing:
     Calcula el Win Rate y EV desglosado por slot de anticipación/retraso.
  5. Frecuencia y Cadencia Real:
     Mide fire rate (%), número de episodios, duración de ráfaga y cadencia (1 disparo cada N velas).
  6. Comparativa Multi-Escala ZigZag:
     Identifica si la señal es de captura táctica (zz25), intermedia (zz50) o estructural (zz75).
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

import numpy as np
import pandas as pd
from scipy.stats import binomtest

# Resolver rutas del proyecto
ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = ROOT / "research" / "01_señales_entry_exit"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arnes.registro import SEÑALES, _CERTEZA
from arnes.timing import classify_timing_slots, calc_timing_distribution, SLOT_ORDER
from evaluador_vela_a_vela import BLANCOS

# Escalas estándar de barreras ZigZag
ESCALAS = {"zz25": 0.025, "zz50": 0.050, "zz75": 0.075}

# Cache global para evitar lecturas de disco repetidas
_CACHE_DATA: Dict[str, Any] = {
    "lake": None,
    "quants": None,
    "spy_close": None,
    "spy_high": None,
    "spy_low": None,
    "lake_idx": None,
    "piv_dates": None,
    "piv_types": None,
    "baseline_fp": None,
}


def cargar_entorno_evaluacion() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Carga y cachea el Lake Continuo y los Pivotes ZigZag de quants_obs."""
    if _CACHE_DATA["lake"] is None:
        lake_path = ROOT / "data" / "research" / "continuous_metar_lake.parquet"
        quants_path = ROOT / "data" / "research" / "pivots" / "quants_obs.pkl"

        if not lake_path.exists():
            raise FileNotFoundError(f"No se encontró el Lake en {lake_path}")
        if not quants_path.exists():
            raise FileNotFoundError(f"No se encontró quants_obs en {quants_path}")

        lake = pd.read_parquet(lake_path)
        quants = pd.read_pickle(quants_path)

        lake_idx = pd.DatetimeIndex(lake.index).normalize()
        piv_dates = pd.DatetimeIndex(quants["pivot_date"]).normalize()
        piv_types = quants["pivot_type"].values

        _CACHE_DATA["lake"] = lake
        _CACHE_DATA["quants"] = quants
        _CACHE_DATA["spy_close"] = lake["spy_close"].values.astype(float)
        _CACHE_DATA["spy_high"] = lake["spy_high"].values.astype(float)
        _CACHE_DATA["spy_low"] = lake["spy_low"].values.astype(float)
        _CACHE_DATA["lake_idx"] = lake_idx
        _CACHE_DATA["piv_dates"] = piv_dates
        _CACHE_DATA["piv_types"] = piv_types

    return _CACHE_DATA["lake"], _CACHE_DATA["quants"]


def build_episodes(sig_mask: np.ndarray, index: pd.DatetimeIndex) -> List[Dict[str, Any]]:
    """Agrupa barras consecutivas activas en episodios continuos respetando la física de la señal."""
    if len(sig_mask) == 0 or not sig_mask.any():
        return []

    # Detectar transiciones 0->1 y 1->0
    diff = np.diff(np.concatenate(([0], sig_mask.astype(int), [0])))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0] - 1

    episodes = []
    for s, e in zip(starts, ends):
        episodes.append({
            "start_idx": int(s),
            "end_idx": int(e),
            "duration_bars": int(e - s + 1),
            "start_date": index[s],
            "end_date": index[e],
        })
    return episodes


def first_passage_bar(close: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                      t0: int, scale: float, blanco: str) -> Optional[Dict[str, Any]]:
    """Evalúa el primer paso vela a vela desde la barra t0 con precios OHLC."""
    p0 = close[t0]
    if p0 <= 0 or t0 >= len(close) - 1:
        return None

    path_h = highs[t0 + 1:]
    path_l = lows[t0 + 1:]
    path_c = close[t0 + 1:]

    up_target = p0 * (1.0 + scale)
    dn_target = p0 * (1.0 - scale)

    up_i = np.where(path_h >= up_target)[0]
    dn_i = np.where(path_l <= dn_target)[0]

    u_idx = up_i[0] if len(up_i) > 0 else np.inf
    d_idx = dn_i[0] if len(dn_i) > 0 else np.inf

    if np.isinf(u_idx) and np.isinf(d_idx):
        return {"resuelto": False}

    event_i = int(min(u_idx, d_idx))
    down_first = bool(d_idx < u_idx)

    seg_h = highs[t0: t0 + 1 + event_i + 1]
    seg_l = lows[t0: t0 + 1 + event_i + 1]
    p_end = path_c[event_i]

    if blanco == "MAX":  # EXIT / Short / Techo
        hit = down_first
        favorable = float((p0 - p_end) / p0)
        mae = float((seg_h.max() - p0) / p0)  # excursión adversa alcista (dolor >= 0)
        mfe = float((p0 - seg_l.min()) / p0)  # excursión favorable bajista (ganancia >= 0)
    else:  # MIN / Entry / Long / Piso
        hit = not down_first
        favorable = float((p_end - p0) / p0)
        mae = float((seg_l.min() - p0) / p0)  # excursión adversa bajista (dolor <= 0)
        mfe = float((seg_h.max() - p0) / p0)  # excursión favorable alcista (ganancia >= 0)

    return {
        "resuelto": True,
        "hit": bool(hit),
        "favorable": float(favorable),
        "mae": float(mae),
        "mfe": float(mfe),
        "bars": int(event_i + 1),
    }


def _calcular_baseline_first_passage(blanco: str, scale: float, min_date: Optional[str] = None) -> Dict[str, Any]:
    """Calcula el baseline incondicional de hit-rate y EV para una escala y dirección."""
    key = f"{blanco}_{scale}_{min_date}"
    if _CACHE_DATA["baseline_fp"] is None:
        _CACHE_DATA["baseline_fp"] = {}

    if key not in _CACHE_DATA["baseline_fp"]:
        close = _CACHE_DATA["spy_close"]
        highs = _CACHE_DATA["spy_high"]
        lows = _CACHE_DATA["spy_low"]
        lake_idx = _CACHE_DATA["lake_idx"]
        n_total = len(close)

        # Muestreo representativo uniforme cada 5 barras para velocidad
        sample_indices = np.arange(0, n_total - 20, 5)
        if min_date:
            ts_min = pd.Timestamp(min_date)
            sample_indices = [i for i in sample_indices if lake_idx[i] >= ts_min]

        results = [first_passage_bar(close, highs, lows, i, scale, blanco) for i in sample_indices]
        valid = [r for r in results if r and r["resuelto"]]

        if valid:
            hits = [r["hit"] for r in valid]
            favs = [r["favorable"] for r in valid]
            _CACHE_DATA["baseline_fp"][key] = {
                "hit_rate": float(np.mean(hits)),
                "ev": float(np.mean(favs)),
                "n_samples": len(valid),
            }
        else:
            _CACHE_DATA["baseline_fp"][key] = {"hit_rate": 0.50, "ev": 0.0, "n_samples": 0}

    return _CACHE_DATA["baseline_fp"][key]


def _rareza_tier(n: int) -> str:
    """Clasifica el tier de rareza según Protocolo Diamante §3.3."""
    if n <= 2:
        return "ANECDOTAL"
    if n <= 5:
        return "LOW"
    if n <= 10:
        return "MODERATE"
    if n <= 20:
        return "HIGH"
    return "ROBUST"


def evaluar_condicion_booleana(sig_mask: Union[np.ndarray, pd.Series],
                               nombre: str,
                               blanco: str = "MIN",
                               descripcion: str = "",
                               post_2011_only: bool = False,
                               fecha_inicio_valida: Optional[str] = None) -> Dict[str, Any]:
    """Evalúa de forma generalizada cualquier condición booleana o señal continua."""
    lake, quants = cargar_entorno_evaluacion()
    close = _CACHE_DATA["spy_close"]
    highs = _CACHE_DATA["spy_high"]
    lows = _CACHE_DATA["spy_low"]
    lake_idx = _CACHE_DATA["lake_idx"]
    piv_dates = _CACHE_DATA["piv_dates"]
    piv_types = _CACHE_DATA["piv_types"]

    if isinstance(sig_mask, pd.Series):
        mask_arr = sig_mask.reindex(lake.index, fill_value=False).values.astype(bool)
    else:
        mask_arr = np.array(sig_mask).astype(bool)

    if fecha_inicio_valida:
        mask_inicio = (lake_idx >= pd.Timestamp(fecha_inicio_valida))
        mask_arr = mask_arr & mask_inicio
        total_barras = int(mask_inicio.sum())
    elif post_2011_only:
        mask_post = (lake_idx >= pd.Timestamp("2011-02-01"))
        mask_arr = mask_arr & mask_post
        total_barras = int(mask_post.sum())
    else:
        total_barras = len(lake)

    effective_min_date = fecha_inicio_valida or ("2011-02-01" if post_2011_only else None)

    total_activas = int(mask_arr.sum())
    fire_rate = round(float(total_activas / total_barras * 100), 2) if total_barras > 0 else 0.0

    # Construir episodios continuos
    episodes = build_episodes(mask_arr, lake_idx)
    n_episodes = len(episodes)

    if n_episodes == 0:
        return {
            "senal": nombre,
            "blanco": blanco,
            "status": "SIN_DISPAROS",
            "descripcion": descripcion,
            "poblacion": {
                "total_barras_dataset": total_barras,
                "total_barras_activas": 0,
                "fire_rate_pct": 0.0,
                "n_episodios": 0,
            }
        }

    durations = [ep["duration_bars"] for ep in episodes]
    start_indices = np.array([ep["start_idx"] for ep in episodes])
    start_dates = lake_idx[start_indices]

    cadencia = round(float(total_barras / n_episodes), 1) if n_episodes > 0 else None
    dur_stats = {
        "mean": round(float(np.mean(durations)), 2),
        "median": round(float(np.median(durations)), 1),
        "p90": round(float(np.percentile(durations, 90)), 1),
        "min": int(np.min(durations)),
        "max": int(np.max(durations)),
    }

    # ── Timing Canónico en Barras de Trading (6 Slots) ──
    df_timing = classify_timing_slots(
        signal_dates=start_dates,
        pivot_dates=piv_dates,
        pivot_types=piv_types,
        target_pivot_type=blanco,
        trading_index=lake_idx,
    )
    timing_dist = calc_timing_distribution(
        signal_dates=start_dates,
        pivot_dates=piv_dates,
        pivot_types=piv_types,
        target_pivot_type=blanco,
        trading_index=lake_idx,
    )

    # ── First Passage por Escala ZigZag (zz25, zz50, zz75) ──
    escalas_results: Dict[str, Any] = {}
    best_scale = None
    best_ev_neto = -999.0

    # Guardar resultados de first passage por episodio para desglose por slot
    fp_by_episode: Dict[str, List[Optional[Dict[str, Any]]]] = {}

    for esc_name, esc_val in ESCALAS.items():
        fp_res = [first_passage_bar(close, highs, lows, s_idx, esc_val, blanco) for s_idx in start_indices]
        fp_by_episode[esc_name] = fp_res
        valid_fp = [r for r in fp_res if r and r.get("resuelto")]

        if not valid_fp:
            continue

        n_val = len(valid_fp)
        hits = np.array([r["hit"] for r in valid_fp])
        favs = np.array([r["favorable"] for r in valid_fp])
        maes = np.array([r["mae"] for r in valid_fp])
        mfes = np.array([r["mfe"] for r in valid_fp])
        bars = np.array([r["bars"] for r in valid_fp])

        hit_rate = float(hits.mean())
        ev_mean = float(favs.mean())
        mae_mean = float(maes.mean())
        mfe_mean = float(mfes.mean())
        bars_mean = float(bars.mean())

        # Baseline incondicional específico de la era observada
        bl = _calcular_baseline_first_passage(blanco, esc_val, min_date=effective_min_date)
        b_hit = bl["hit_rate"]
        b_ev = bl["ev"]

        hit_neto = round(float(hit_rate - b_hit), 4)
        ev_neto = round(float(ev_mean - b_ev), 4)

        # Binomial test
        p_val = float(binomtest(int(hits.sum()), n_val, b_hit, alternative="greater").pvalue)

        # Profit factor
        wins = favs[hits]
        losses = np.abs(favs[~hits])
        pf = float(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() > 0 else (99.0 if len(wins) > 0 else 0.0)

        # RR Asymmetry
        rr = round(float(mfe_mean / abs(mae_mean)), 2) if mae_mean != 0 else None
        ev_bar = round(float(ev_mean / bars_mean), 6) if bars_mean > 0 else None

        scale_entry = {
            "escala_pct": round(esc_val * 100, 1),
            "n": n_val,
            "hit_rate": round(hit_rate, 3),
            "baseline_hit": round(b_hit, 3),
            "hit_neto": hit_neto,
            "p_value_binom": round(p_val, 4),
            "ev": round(ev_mean, 4),
            "baseline_ev": round(b_ev, 4),
            "ev_neto": ev_neto,
            "profit_factor": round(pf, 2),
            "mae_medio": round(mae_mean, 4),
            "mae_p10": round(float(np.percentile(np.abs(maes), 10)) * (-1.0 if blanco == "MIN" else 1.0), 4),
            "mae_p90": round(float(np.percentile(np.abs(maes), 90)) * (-1.0 if blanco == "MIN" else 1.0), 4),
            "mfe_medio": round(mfe_mean, 4),
            "mfe_p90": round(float(np.percentile(mfes, 90)), 4),
            "rr_asymmetry": rr,
            "bars_medio": round(bars_mean, 1),
            "ev_por_barra": ev_bar,
        }
        escalas_results[esc_name] = scale_entry

        if ev_neto > best_ev_neto:
            best_ev_neto = ev_neto
            best_scale = esc_name

    # ── Rendimiento Desglosado por Slot de Timing (zz25) ──
    rendimiento_slots = {}
    slots_arr = df_timing["slot"].values
    fp_25 = fp_by_episode.get("zz25", [])

    for s_label in SLOT_ORDER:
        idxs_s = np.where(slots_arr == s_label)[0]
        n_s = len(idxs_s)
        if n_s == 0:
            rendimiento_slots[s_label] = {"n": 0, "hit_rate": None, "ev": None}
            continue

        s_fp = [fp_25[i] for i in idxs_s if i < len(fp_25) and fp_25[i] and fp_25[i].get("resuelto")]
        if s_fp:
            s_hits = [r["hit"] for r in s_fp]
            s_favs = [r["favorable"] for r in s_fp]
            rendimiento_slots[s_label] = {
                "n": int(len(s_fp)),
                "hit_rate": round(float(np.mean(s_hits)), 3),
                "ev": round(float(np.mean(s_favs)), 4),
                "bars_medio": round(float(np.mean([r["bars"] for r in s_fp])), 1),
            }
        else:
            rendimiento_slots[s_label] = {"n": n_s, "hit_rate": None, "ev": None}

    # Sub-población Post-2011 para estaciones de sentimiento
    # Omitir si la señal ya filtra Post-2011 (redundante: mismos datos, mismos resultados)
    post_stats = None
    if not post_2011_only:
        mask_post = (lake_idx >= pd.Timestamp("2011-02-01"))
        sig_post = mask_arr & mask_post
        ep_post = build_episodes(sig_post, lake_idx)
        if len(ep_post) > 0:
            p_starts = np.array([ep["start_idx"] for ep in ep_post])
            p_fp25 = [first_passage_bar(close, highs, lows, i, 0.025, blanco) for i in p_starts]
            v_p25 = [r for r in p_fp25 if r and r.get("resuelto")]
            if v_p25:
                post_stats = {
                    "total_barras_post2011": int(mask_post.sum()),
                    "n_episodios": len(ep_post),
                    "zz25_hit_rate": round(float(np.mean([r["hit"] for r in v_p25])), 3),
                    "zz25_ev": round(float(np.mean([r["favorable"] for r in v_p25])), 4),
                }

    return {
        "senal": nombre,
        "tipo": _CERTEZA.get(nombre, {}).get("tipo", "unknown"),
        "blanco": blanco,
        "status": "OK",
        "descripcion": descripcion or _CERTEZA.get(nombre, {}).get("descripcion", ""),
        "poblacion": {
            "total_barras_dataset": total_barras,
            "total_barras_activas": total_activas,
            "fire_rate_pct": fire_rate,
            "n_episodios": n_episodes,
            "cadencia_1_en_n_barras": cadencia,
            "es_fondo": cadencia is not None and cadencia < 10,
            "duracion_episodio": dur_stats,
            "es_diamante": n_episodes < 21,
            "tier_rareza": _rareza_tier(n_episodes),
        },
        "timing_canonico": timing_dist,
        "rendimiento_por_slot": rendimiento_slots,
        "escalas_zigzag": escalas_results,
        "escala_optima": best_scale,
        "post_2011": post_stats,
    }


def evaluar_senal(senal_nombre: str, forzar_full: bool = False) -> Dict[str, Any]:
    """Evalúa una señal registrada en el arnés con fallback inteligente Lake -> Quants.
    Aplica automáticamente la restricción de fecha de inicio válida (ej. Post-2011 para SKEW/FG)
    para evitar contaminar la estadística con datos sintéticos previos a la creación oficial del índice."""
    if senal_nombre not in SEÑALES:
        return {"senal": senal_nombre, "status": "NO_REGISTRADA", "razon": "No existe en el arnés de registro."}

    lake, quants = cargar_entorno_evaluacion()
    fn = SEÑALES[senal_nombre]
    blanco = BLANCOS.get(senal_nombre, "MIN")
    lake_idx = _CACHE_DATA["lake_idx"]
    meta = _CERTEZA.get(senal_nombre, {})
    fecha_inicio = meta.get("fecha_inicio_valida")

    # Intentar correr en Lake Continuo (8,453 barras)
    modo = "lake"
    try:
        sig_lake = fn(lake)
        if isinstance(sig_lake, pd.Series):
            mask_arr = sig_lake.values.astype(bool)
        else:
            mask_arr = np.array(sig_lake).astype(bool)

        # Si el lake no dispara nada pero es una señal que requiere quants_obs (ej. cascade_reversal)
        if mask_arr.sum() == 0:
            q_mask = fn(quants).values.astype(bool)
            if q_mask.sum() > 0:
                q_dates = pd.DatetimeIndex(quants.loc[q_mask, "pivot_date"]).normalize()
                mask_arr = lake_idx.isin(q_dates)
                modo = "quants_mapped"
    except Exception:
        # Fallback a quants
        q_mask = fn(quants).values.astype(bool)
        q_dates = pd.DatetimeIndex(quants.loc[q_mask, "pivot_date"]).normalize()
        mask_arr = lake_idx.isin(q_dates)
        modo = "quants_mapped"

    # Filtrar datos sintéticos previos a la fecha de inicio oficial (ej. SKEW < 2011-02-01)
    if fecha_inicio and not forzar_full:
        mask_valida = (lake_idx >= pd.Timestamp(fecha_inicio))
        mask_arr = mask_arr & mask_valida

    res = evaluar_condicion_booleana(
        sig_mask=mask_arr,
        nombre=senal_nombre,
        blanco=blanco,
        fecha_inicio_valida=fecha_inicio if not forzar_full else None,
    )
    res["modo_ejecucion"] = modo
    res["fecha_inicio_valida"] = fecha_inicio
    res["era_valida"] = meta.get("era_valida", "FULL")
    return res


def evaluar_todas(guardar_path: Optional[Path] = None) -> Dict[str, Any]:
    """Evalúa las 33 señales registradas del catálogo y opcionalmente guarda el JSON consolidado."""
    cargar_entorno_evaluacion()
    reporte = {}
    filas_resumen = []

    print(f"\n{'=' * 125}\nEVALUADOR GENERALIZADO CONTINUO (8,453 Barras Lake + First-Passage + Timing Canónico)\n{'=' * 125}")
    print(f"{'Señal':<30s} | {'Modo':<13s} | {'N (Ep)':>6s} {'Tier':>8s} | {'Fire%':>6s} {'1/N':>5s} | "
          f"{'EnRng%':>6s} {'Ant%':>5s} {'Exa%':>5s} {'Ret%':>5s} | {'Hit(zz25)':>9s} {'EV(zz25)':>9s} {'Best':>5s}")
    print("-" * 125)

    for s_name in sorted(SEÑALES.keys()):
        r = evaluar_senal(s_name)
        reporte[s_name] = r

        if r.get("status") != "OK":
            print(f"{s_name:<30s} | {r.get('status', 'ERROR'):<13s} | SIN DATOS")
            continue

        pob = r["poblacion"]
        tim = r["timing_canonico"]
        esc = r["escalas_zigzag"]
        z25 = esc.get("zz25", {})

        n_ep = pob["n_episodios"]
        tier = pob["tier_rareza"] + ("💎" if pob["es_diamante"] else "")
        fire = f"{pob['fire_rate_pct']:.1f}%"
        cad = f"{pob['cadencia_1_en_n_barras']:.0f}v" if pob["cadencia_1_en_n_barras"] else "-"

        en_rng = f"{tim['pct_en_rango']:.0f}%"
        ant = f"{tim['pct_anticipada']:.0f}%"
        exa = f"{tim['pct_exacta']:.0f}%"
        ret = f"{tim['pct_retrasada']:.0f}%"

        hit25 = f"{z25.get('hit_rate', 0.0):.1%} ({z25.get('hit_neto', 0.0):+.1%})" if z25 else "-"
        ev25 = f"{z25.get('ev', 0.0):+.2%}" if z25 else "-"
        best = r.get("escala_optima", "-")
        modo = r.get("modo_ejecucion", "lake")

        print(f"{s_name:<30s} | {modo:<13s} | {n_ep:>6d} {tier:>8s} | {fire:>6s} {cad:>5s} | "
              f"{en_rng:>6s} {ant:>5s} {exa:>5s} {ret:>5s} | {hit25:>9s} {ev25:>9s} {best:>5s}")

        filas_resumen.append({
            "senal": s_name,
            "n_episodios": n_ep,
            "tier": tier,
            "en_rango_pct": tim["pct_en_rango"],
            "anticipada_pct": tim["pct_anticipada"],
            "hit_rate_zz25": z25.get("hit_rate"),
            "ev_zz25": z25.get("ev"),
            "ev_neto_zz25": z25.get("ev_neto"),
            "escala_optima": best,
        })

    if guardar_path is None:
        guardar_path = ROOT / "data" / "research" / "signals" / "evaluacion_generalizada_lake.json"

    guardar_path.parent.mkdir(parents=True, exist_ok=True)
    guardar_path.write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str))
    print(f"\n✅ Reporte consolidado guardado en: {guardar_path}")
    print(f"{'=' * 125}\n")

    return reporte


def main():
    parser = argparse.ArgumentParser(description="Evaluador Generalizado de Señales Continuas")
    parser.add_argument("--senal", type=str, default=None, help="Evaluar una señal específica")
    parser.add_argument("--todas", action="store_true", help="Evaluar todo el catálogo de 33 señales")
    parser.add_argument("--dry-run", action="store_true", help="Verificar entorno y dependencias")
    parser.add_argument("--salida", type=str, default=None, help="Ruta de guardado personalizada")
    args = parser.parse_args()

    if args.dry_run:
        lake, quants = cargar_entorno_evaluacion()
        print("✅ Dry-run completado exitosamente:")
        print(f"  Lake continuo: {len(lake)} barras ({lake.index[0]} a {lake.index[-1]})")
        print(f"  Quants pivotes: {len(quants)} pivotes ({quants['pivot_date'].min()} a {quants['pivot_date'].max()})")
        print(f"  Señales registradas: {len(SEÑALES)}")
        print(f"  Blancos definidos: {len(BLANCOS)}")
        return

    out_path = Path(args.salida) if args.salida else None

    if args.senal:
        cargar_entorno_evaluacion()
        res = evaluar_senal(args.senal)
        print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
            print(f"✅ Guardado en {out_path}")
    else:
        evaluar_todas(guardar_path=out_path)


if __name__ == "__main__":
    main()
