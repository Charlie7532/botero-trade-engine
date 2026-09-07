#!/usr/bin/env python3
"""
GENERADOR OFICIAL DE TIMING FACT STORES (CHRONOS ENGINE)
========================================================
Genera los 11 Timing Fact Stores para cada una de las estaciones METAR:
[vix, vvix, pcr, fg, sv5_turbulence, skew, credit, yield_curve, rotation, bsi, dxy].

Principios Fundamentales:
  1. Cero Juicio, Solo Datos: Datos empíricos puros. Sin etiquetas adjetivales.
  2. Evaluación Bidireccional: Evalúa cada vector de estado contra suelos (MIN) y techos (MAX).
  3. Geometría de Timing en 6 Slots Canónicos: Distancia exacta a pivotes [t-2, t-1, t=0, t+1, t+2, ENTRE].
  4. Rendimiento por Slot a Escala Táctica (zz25 = 2.5%).
  5. First-Passage Multiescala (zz25, zz50, zz75) con baselines incondicionales, asimetría y velocidad de capital.
  6. Fechas de Incepción Oficiales: Respeta estrictamente ESTACION_INCEPTION_DATES.
  7. Desbordamientos Empíricos (Overflow Tiers T1-T5): Registra métricas de colas > 3σ.
  8. Cumplimiento de la Regla 21 de AGENTS.md (_documentation completa).
"""

import sys
import json
import argparse
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

# Rutas del proyecto
ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = ROOT / "research" / "01_señales_entry_exit"
RULES_DIR = ROOT / "backend" / "modules" / "entry_decision" / "domain" / "rules"

if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluador_general import (
    cargar_entorno_evaluacion,
    evaluar_condicion_booleana,
    build_episodes,
    _calcular_baseline_first_passage,
    SLOT_ORDER,
    ESCALAS,
    _CACHE_DATA,
)
from arnes.registro import ESTACION_INCEPTION_DATES

STATIONS_LIST = [
    "vix",
    "vvix",
    "pcr",
    "fg",
    "sv5_turbulence",
    "skew",
    "credit",
    "yield_curve",
    "rotation",
    "bsi",
    "dxy",
]


def _build_documentation_header(
    station: str,
    v1_doc: Dict[str, Any],
    inception_date: str,
    total_bars: int,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Construye el encabezado _documentation conforme a la Regla 21 de AGENTS.md."""
    st_upper = station.upper()
    taxonomy = v1_doc.get("taxonomy", {})
    thresholds = v1_doc.get("dimension_thresholds_definition", {})

    return {
        "model_purpose": (
            f"METAR Station {st_upper} Empirical Fact Store 2: Triad Timing & Multi-Scale Dual-Passage Engine. "
            f"Evaluates every observed state triad (D1__D2__D3) across its official continuous market history "
            f"({start_date} to {end_date}, {total_bars} daily trading bars) without directional bias. "
            f"Measures exact temporal turning-point timing (6-slot canonical geometry [t-2..t+2, ENTRE]) and "
            f"forward Triple-Barrier first-passage returns independently for both market bottoms (MIN) and "
            f"market tops (MAX). Pure empirical measurement data with zero narrative or qualitative judgment."
        ),
        "data_sources": {
            "lake_path": "data/research/continuous_metar_lake.parquet",
            "pivots_path": "data/research/pivots/quants_obs.pkl",
            "benchmark_asset": "SPY (OHLCV)",
            "official_inception_date": inception_date,
            "coverage_start": start_date,
            "coverage_end": end_date,
            "sample_size_days": total_bars,
        },
        "return_formula": (
            "First-Passage Triple Barrier: from episode start bar t0, walk forward bar-by-bar. "
            "UP_barrier = P0 * (1 + scale), DN_barrier = P0 * (1 - scale). "
            "hit_MIN = {UP barrier hit before DN barrier}; favorable_MIN = (P_end - P0) / P0. "
            "hit_MAX = {DN barrier hit before UP barrier}; favorable_MAX = (P0 - P_end) / P0. "
            "Time-stop vertical barrier calibrated to P95 empirical resolution: zz25->35, zz50->110, zz75->190 bars. "
            "Unresolved episodes at timeout are counted as failures (hit=False) to eliminate survivorship bias."
        ),
        "state_hierarchy": {
            "L0": f"Station Root ({st_upper})",
            "L1_D1": "Point-in-Time Magnitude (Level mapped to 6 Gaussian sigma bins [0..5])",
            "L2_D2": "72h Kinematic Velocity (3-day difference mapped to 5 Gaussian bins [0..4])",
            "L3_D3": "Intra-Station Volatility Instability Ratio (std(2d)/std(10d) mapped to 5 Gaussian bins [0..4])",
            "state_key_format": "D1__D2__D3 (numeric coordinate string, e.g. '4__3__2')",
        },
        "taxonomy": taxonomy,
        "dimension_thresholds_definition": thresholds,
        "zigzag_scale_classification": {
            "zz25": {
                "scale_pct": 2.5,
                "target_return": "+/- 2.5% SPY movement",
                "holding_barrier_max_bars": 35,
                "operational_horizon": "Tactical Swing / Short-term turning point capture.",
            },
            "zz50": {
                "scale_pct": 5.0,
                "target_return": "+/- 5.0% SPY movement",
                "holding_barrier_max_bars": 110,
                "operational_horizon": "Intermediate Cyclical Swing / Core leg accumulation.",
            },
            "zz75": {
                "scale_pct": 7.5,
                "target_return": "+/- 7.5% SPY movement",
                "holding_barrier_max_bars": 190,
                "operational_horizon": "Structural Macro Leg / Long-term regime trend.",
            },
        },
        "field_glossary": {
            "poblacion": {
                "barras": "Total active daily bars where triad condition held true within valid era.",
                "fire_rate_pct": "Saturation rate: active_bars / total_valid_era_bars * 100.",
                "n_episodios": "Count of discrete de-clustered continuous episodes.",
                "duracion_media": "Mean episode duration in consecutive trading days.",
                "duracion_max": "Maximum observed consecutive episode duration in days.",
            },
            "overflows": {
                "n_episodios_tier_gte_1": "Episodes where indicator breached +/-3 sigma on any dimension during episode.",
                "pct_episodios_overflow": "Percentage of triad episodes reaching Tier 1 or higher.",
                "max_tier_d1": "Highest observed overflow tier on D1 Level (0=Normal, 1=T1, 2=T2, 3=T3, 4=T4, 5=T5).",
                "max_tier_d2": "Highest observed overflow tier on D2 3d Velocity.",
                "max_tier_d3": "Highest observed overflow tier on D3 Volatility Instability.",
            },
            "resumen_rango": {
                "n_en_rango": "Episodes occurring within [-2, +2] trading bars of target ZigZag turning point.",
                "pct_en_rango": "Percentage of episodes falling within the turning point proximity window.",
                "delta_medio": "Mean absolute distance in trading bars to nearest target pivot.",
                "delta_mediana": "Median absolute distance in trading bars to nearest target pivot.",
            },
            "slots_zz25": {
                "n": "Episode sample count in this specific timing slot.",
                "pct": "Percentage of triad episodes falling into this timing slot.",
                "hit_rate": "Empirical win rate at zz25 (2.5%) scale for episodes in this slot.",
                "ev": "Expected arithmetic return of the first-passage resolution at zz25 from this slot.",
                "bars": "Mean trading bars required to resolve the position at zz25 from this slot.",
            },
            "first_passage": {
                "hit_rate": "Empirical barrier touch win rate across all episodes for this scale.",
                "baseline_hit": "Unconditional market win rate for (blanco, scale) during this station's valid era.",
                "hit_neto": "hit_rate - baseline_hit (empirical edge over unconditional baseline).",
                "ev": "Expected arithmetic mean return per trade (positive = capital expansion).",
                "baseline_ev": "Unconditional market expected return during this station's valid era.",
                "ev_neto": "ev - baseline_ev (net return edge).",
                "profit_factor": "Gross profit sum divided by absolute gross loss sum.",
                "rr_asymmetry": "mfe_medio / |mae_medio| (reward-to-risk ratio).",
                "ev_por_barra": "ev / bars_medio (capital velocity: return edge per unit of holding time).",
                "mae_medio": "Mean Maximum Adverse Excursion (average drawdown pain).",
                "mae_p90": "90th percentile Maximum Adverse Excursion (severe tail risk pain).",
                "mfe_medio": "Mean Maximum Favorable Excursion (average peak unrealized profit).",
                "mfe_p90": "90th percentile Maximum Favorable Excursion (tail profit potential).",
                "bars_medio": "Mean holding bars from signal trigger to barrier event or timeout.",
                "p_value": "Binomial exact test p-value testing significance against unconditional baseline.",
            },
        },
        "signal_interpretation_policy": (
            "Clean Architecture Standard: This JSON file acts exclusively as an empirical Fact Store. "
            "It does not contain pre-computed trading directives, adjectival rankings, or heuristic biases. "
            "Downstream pure-domain adapters (e.g., entry gates, Bayesian compositors, and allocation rules) "
            "consume these objective distributions dynamically to derive execution signals."
        ),
    }


def generar_estacion(station: str, lake: pd.DataFrame, verbose: bool = True) -> Dict[str, Any]:
    """Genera el Timing Fact Store completo para una estación METAR."""
    st_lower = station.lower()
    sk_col = f"{st_lower}_sk"
    if sk_col not in lake.columns:
        raise ValueError(f"Columna {sk_col} no encontrada en el Lake continuo.")

    # Cargar fact store V1 correspondiente para obtener estados y metadatos
    v1_path = RULES_DIR / f"{st_lower}_fact_store.json"
    if not v1_path.exists():
        raise FileNotFoundError(f"Fact store V1 no encontrado en {v1_path}")

    with open(v1_path, "r", encoding="utf-8") as f:
        v1_data = json.load(f)

    v1_doc = v1_data.get("_documentation", {})
    registered_states = sorted(list(v1_data.get("states", {}).keys()))

    lake_idx = pd.DatetimeIndex(lake.index).normalize()
    inception_date = ESTACION_INCEPTION_DATES.get(st_lower, "1993-01-29")
    ts_inception = pd.Timestamp(inception_date)

    valid_mask = lake_idx >= ts_inception
    total_valid_bars = int(valid_mask.sum())
    start_date_str = str(lake_idx[valid_mask][0].date())
    end_date_str = str(lake_idx[valid_mask][-1].date())

    if verbose:
        print(f"\n{'=' * 90}")
        print(f"PROCESANDO ESTACIÓN: {st_lower.upper()} (Incepción: {inception_date})")
        print(f"Ventana Válida: {start_date_str} a {end_date_str} ({total_valid_bars} barras diarias)")
        print(f"Estados Registrados en V1: {len(registered_states)}")
        print(f"{'=' * 90}")

    # Columnas de overflow precalculadas en el lake
    ovf_col_d1 = f"{st_lower}_overflow_tier_d1"
    ovf_col_d2 = f"{st_lower}_overflow_tier_d2"
    ovf_col_d3 = f"{st_lower}_overflow_tier_d3"

    has_ovf = (
        ovf_col_d1 in lake.columns
        and ovf_col_d2 in lake.columns
        and ovf_col_d3 in lake.columns
    )
    t1_arr = lake[ovf_col_d1].fillna(0).values.astype(int) if has_ovf else None
    t2_arr = lake[ovf_col_d2].fillna(0).values.astype(int) if has_ovf else None
    t3_arr = lake[ovf_col_d3].fillna(0).values.astype(int) if has_ovf else None

    # 1. Calcular baselines incondicionales de la era para MIN y MAX
    baselines_output = {}
    for esc_name, esc_val in ESCALAS.items():
        bl_min = _calcular_baseline_first_passage("MIN", esc_val, min_date=inception_date)
        bl_max = _calcular_baseline_first_passage("MAX", esc_val, min_date=inception_date)
        baselines_output[esc_name] = {
            "min_hit": round(float(bl_min["hit_rate"]), 4),
            "min_ev": round(float(bl_min["ev"]), 4),
            "max_hit": round(float(bl_max["hit_rate"]), 4),
            "max_ev": round(float(bl_max["ev"]), 4),
        }

    # 2. Iterar sobre los estados registrados
    states_dict: Dict[str, Any] = {}
    n_populated = 0
    t0_st = time.time()

    for idx, sk in enumerate(registered_states):
        raw_mask = (lake[sk_col] == sk).values.astype(bool)
        state_valid_mask = raw_mask & valid_mask
        n_barras = int(state_valid_mask.sum())

        if n_barras == 0:
            states_dict[sk] = {
                "poblacion": {
                    "barras": 0,
                    "fire_rate_pct": 0.0,
                    "n_episodios": 0,
                    "duracion_media": 0.0,
                    "duracion_max": 0,
                },
                "overflows": {
                    "n_episodios_tier_gte_1": 0,
                    "pct_episodios_overflow": 0.0,
                    "max_tier_d1": 0,
                    "max_tier_d2": 0,
                    "max_tier_d3": 0,
                },
                "medicion_min": None,
                "medicion_max": None,
            }
            continue

        # Población y episodios continuos
        episodes = build_episodes(state_valid_mask, lake_idx)
        n_episodes = len(episodes)

        if n_episodes == 0:
            continue

        n_populated += 1
        durations = [ep["duration_bars"] for ep in episodes]
        fire_rate = round(float(n_barras / total_valid_bars * 100), 2)

        poblacion = {
            "barras": n_barras,
            "fire_rate_pct": fire_rate,
            "n_episodios": n_episodes,
            "duracion_media": round(float(np.mean(durations)), 2) if durations else 0.0,
            "duracion_max": int(np.max(durations)) if durations else 0,
        }

        # Desbordamientos empíricos por episodio
        if has_ovf:
            d1_maxs = [int(np.max(t1_arr[ep["start_idx"] : ep["end_idx"] + 1])) for ep in episodes]
            d2_maxs = [int(np.max(t2_arr[ep["start_idx"] : ep["end_idx"] + 1])) for ep in episodes]
            d3_maxs = [int(np.max(t3_arr[ep["start_idx"] : ep["end_idx"] + 1])) for ep in episodes]
            ovf_eps = sum(1 for i in range(n_episodes) if d1_maxs[i] >= 1 or d2_maxs[i] >= 1 or d3_maxs[i] >= 1)
            overflow_data = {
                "n_episodios_tier_gte_1": int(ovf_eps),
                "pct_episodios_overflow": round(float(ovf_eps / n_episodes * 100), 2),
                "max_tier_d1": int(max(d1_maxs)),
                "max_tier_d2": int(max(d2_maxs)),
                "max_tier_d3": int(max(d3_maxs)),
            }
        else:
            overflow_data = {
                "n_episodios_tier_gte_1": 0,
                "pct_episodios_overflow": 0.0,
                "max_tier_d1": 0,
                "max_tier_d2": 0,
                "max_tier_d3": 0,
            }

        # ── Medición MIN (Suelos) ──
        res_min = evaluar_condicion_booleana(
            state_valid_mask,
            nombre=f"{st_lower}_{sk}",
            blanco="MIN",
            fecha_inicio_valida=inception_date,
        )
        tc_min = res_min.get("timing_canonico", {})
        rs_min = res_min.get("rendimiento_por_slot", {})
        fp_min = res_min.get("escalas_zigzag", {})

        slots_min = {}
        for s in SLOT_ORDER:
            cnt = tc_min.get("counts", {}).get(s, 0)
            pct = tc_min.get("pcts", {}).get(s, 0.0)
            perf = rs_min.get(s, {})
            slots_min[s] = {
                "n": cnt,
                "pct": pct,
                "hit_rate": perf.get("hit_rate"),
                "ev": perf.get("ev"),
                "bars": perf.get("bars_medio"),
            }

        first_passage_min = {}
        for esc in ["zz25", "zz50", "zz75"]:
            e_data = fp_min.get(esc, {})
            if e_data:
                first_passage_min[esc] = {
                    "hit_rate": e_data.get("hit_rate"),
                    "baseline_hit": e_data.get("baseline_hit"),
                    "hit_neto": e_data.get("hit_neto"),
                    "ev": e_data.get("ev"),
                    "baseline_ev": e_data.get("baseline_ev"),
                    "ev_neto": e_data.get("ev_neto"),
                    "profit_factor": e_data.get("profit_factor"),
                    "rr_asymmetry": e_data.get("rr_asymmetry"),
                    "ev_por_barra": e_data.get("ev_por_barra"),
                    "mae_medio": e_data.get("mae_medio"),
                    "mae_p90": e_data.get("mae_p90"),
                    "mfe_medio": e_data.get("mfe_medio"),
                    "mfe_p90": e_data.get("mfe_p90"),
                    "bars_medio": e_data.get("bars_medio"),
                    "p_value": e_data.get("p_value_binom"),
                    "n_timeout": e_data.get("n_timeout", 0),
                    "timeout_rate": e_data.get("timeout_rate", 0.0),
                    "max_barras": e_data.get("max_barras"),
                }

        medicion_min = {
            "resumen_rango": {
                "n_en_rango": tc_min.get("n_en_rango", 0),
                "pct_en_rango": tc_min.get("pct_en_rango", 0.0),
                "delta_medio": tc_min.get("delta_medio"),
                "delta_mediana": tc_min.get("delta_mediana"),
            },
            "slots_zz25": slots_min,
            "first_passage": first_passage_min,
        }

        # ── Medición MAX (Techos) ──
        res_max = evaluar_condicion_booleana(
            state_valid_mask,
            nombre=f"{st_lower}_{sk}",
            blanco="MAX",
            fecha_inicio_valida=inception_date,
        )
        tc_max = res_max.get("timing_canonico", {})
        rs_max = res_max.get("rendimiento_por_slot", {})
        fp_max = res_max.get("escalas_zigzag", {})

        slots_max = {}
        for s in SLOT_ORDER:
            cnt = tc_max.get("counts", {}).get(s, 0)
            pct = tc_max.get("pcts", {}).get(s, 0.0)
            perf = rs_max.get(s, {})
            slots_max[s] = {
                "n": cnt,
                "pct": pct,
                "hit_rate": perf.get("hit_rate"),
                "ev": perf.get("ev"),
                "bars": perf.get("bars_medio"),
            }

        first_passage_max = {}
        for esc in ["zz25", "zz50", "zz75"]:
            e_data = fp_max.get(esc, {})
            if e_data:
                first_passage_max[esc] = {
                    "hit_rate": e_data.get("hit_rate"),
                    "baseline_hit": e_data.get("baseline_hit"),
                    "hit_neto": e_data.get("hit_neto"),
                    "ev": e_data.get("ev"),
                    "baseline_ev": e_data.get("baseline_ev"),
                    "ev_neto": e_data.get("ev_neto"),
                    "profit_factor": e_data.get("profit_factor"),
                    "rr_asymmetry": e_data.get("rr_asymmetry"),
                    "ev_por_barra": e_data.get("ev_por_barra"),
                    "mae_medio": e_data.get("mae_medio"),
                    "mae_p90": e_data.get("mae_p90"),
                    "mfe_medio": e_data.get("mfe_medio"),
                    "mfe_p90": e_data.get("mfe_p90"),
                    "bars_medio": e_data.get("bars_medio"),
                    "p_value": e_data.get("p_value_binom"),
                    "n_timeout": e_data.get("n_timeout", 0),
                    "timeout_rate": e_data.get("timeout_rate", 0.0),
                    "max_barras": e_data.get("max_barras"),
                }

        medicion_max = {
            "resumen_rango": {
                "n_en_rango": tc_max.get("n_en_rango", 0),
                "pct_en_rango": tc_max.get("pct_en_rango", 0.0),
                "delta_medio": tc_max.get("delta_medio"),
                "delta_mediana": tc_max.get("delta_mediana"),
            },
            "slots_zz25": slots_max,
            "first_passage": first_passage_max,
        }

        states_dict[sk] = {
            "poblacion": poblacion,
            "overflows": overflow_data,
            "medicion_min": medicion_min,
            "medicion_max": medicion_max,
        }

        if verbose and (idx + 1) % 25 == 0:
            print(f"  [{idx + 1}/{len(registered_states)}] estados procesados...")

    elapsed_st = time.time() - t0_st
    if verbose:
        print(f"  Completados {len(registered_states)} estados ({n_populated} poblados) en {elapsed_st:.2f}s")

    # 3. Ensamblar JSON completo
    doc_header = _build_documentation_header(
        station=st_lower,
        v1_doc=v1_doc,
        inception_date=inception_date,
        total_bars=total_valid_bars,
        start_date=start_date_str,
        end_date=end_date_str,
    )

    full_output = {
        "_documentation": doc_header,
        "station": st_lower.upper(),
        "inception_date": inception_date,
        "coverage_start": start_date_str,
        "coverage_end": end_date_str,
        "sample_size_bars": total_valid_bars,
        "states_registered": len(registered_states),
        "states_populated": n_populated,
        "baselines": baselines_output,
        "states": states_dict,
    }

    out_file = RULES_DIR / f"{st_lower}_timing_fact_store.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(full_output, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"✅ Guardado exitosamente: {out_file}")

    return full_output


def main():
    parser = argparse.ArgumentParser(description="Generador Oficial de Timing Fact Stores")
    parser.add_argument("--estacion", type=str, default=None, help="Generar una sola estación (ej. vix)")
    parser.add_argument("--todas", action="store_true", help="Generar las 11 estaciones METAR")
    parser.add_argument("--dry-run", action="store_true", help="Verificar entorno y dependencias")
    args = parser.parse_args()

    lake, quants = cargar_entorno_evaluacion()

    if args.dry_run:
        print("✅ Dry-run exitoso. Lake:", len(lake), "barras. Quants:", len(quants), "pivotes.")
        return

    t0_global = time.time()

    if args.estacion:
        st = args.estacion.lower()
        if st not in STATIONS_LIST:
            print(f"❌ Estación '{st}' no reconocida. Opciones: {STATIONS_LIST}")
            sys.exit(1)
        generar_estacion(st, lake, verbose=True)
    elif args.todas:
        print(f"\nIniciando generación masiva de las {len(STATIONS_LIST)} estaciones METAR...")
        for st in STATIONS_LIST:
            generar_estacion(st, lake, verbose=True)
        print(f"\n🎉 Generación de las 11 estaciones completada en {time.time() - t0_global:.1f}s.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
