#!/usr/bin/env python3
"""
medir_senal.py — ARNÉS DE MEDICIÓN ESTÁNDAR (matemática pura, sin agentes).

Propósito: codificar de una vez el estándar de medición de Botero Trade para que
ninguna señal se mida "a mano" otra vez. Cada señal se evalúa con el MISMO método:

  1. Distribución COMPLETA de outcomes (P5/P25/P50/P75/P95), no solo media.
  2. Drawdown de comprar TEMPRANO (MAE intra-trade real contra el Low del Vault).
  3. Drawdown de comprar TARDE (costo de oportunidad por trade de retrasar k barras).
  4. Sensibilidad al timing (retraso de 0..k barras continuas).
  5. CI95 bootstrap (seed fija) + N + wins/losses separados.
  6. Baseline condicionado homogéneo (mismo pivot_type).
  7. Salida PROBABILÍSTICA (no absolutos).

Uso:
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/01_señales_entry_exit/medir_senal.py \
      --señal credit_easing_k1 --horizontes 5,10,20,60 --seed 42 --bootstrap 3000

Determinista: mismo input → mismo output. Sin LLM, sin interpretación.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent if "__file__" in locals() else Path("/root/botero-trade")
SCRATCH = ROOT / "data/research"
OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"
if not OBS_PKL.exists():
    OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"

# ─────────────────────────────────────────────────────────────────────────────
# 1. CARGA DE DATOS
# ─────────────────────────────────────────────────────────────────────────────
def cargar_datos():
    """Carga los pivotes de quants_obs.pkl y las barras diarias de SPY desde el Vault."""
    df = pd.read_pickle(OBS_PKL).reset_index(drop=True)
    df["pivot_date"] = pd.to_datetime(df["pivot_date"])

    try:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        store = TimescaleDataStore()
        spy = store.load_bars("SPY", "1d")
        spy.index = pd.to_datetime(spy.index).tz_localize(None)
    except Exception as e:
        print(f"[WARN] No se pudo cargar SPY del Vault: {e}", file=sys.stderr)
        spy = None

    return df, spy


# ─────────────────────────────────────────────────────────────────────────────
# 2. DEFINICIONES DE SEÑAL (registro determinista)
#    Cada señal es una función df -> pd.Series (bool: señal activa)
#    o df -> pd.Series (score continuo). Aquí se registran todas.
# ─────────────────────────────────────────────────────────────────────────────
SEÑALES = {}
_CERTEZA = {}  # nombre -> {validacion, n_min, dsr, fuente}

def _registrar(nombre, **certeza):
    """Registra una señal con su metadata de validación.
    certeza: {validacion, n_min, dsr, fuente, nota}
    - validacion: "VALIDATED (Grade A)" | "MODERATE" | "SPECULATIVE"
    - n_min: muestra mínima de la validación original
    - dsr: Deflated Sharpe Ratio p-value
    - fuente: documento de referencia
    """
    def deco(fn):
        SEÑALES[nombre] = fn
        _CERTEZA[nombre] = certeza
        return fn
    return deco


@_registrar("credit_easing_k1",
    validacion="VALIDATED (Grade A)", n_min=112, dsr=None,
    fuente="credit_easing_pisos.py (17-Ago)")
def _credit_easing(df):
    """CREDIT easing en ventana K=1, EN UN PISO DE DRAWDOWN (pivot_type == MIN).
    (Hallazgo validado: EASING en piso → +5.19% 93.75%WR vs SIN → +2.99%.)"""
    es_min = (df["pivot_type"] == "MIN").values
    d = df["credit_val"]
    easing = (d > d.shift(1)).values
    return pd.Series(es_min & easing, index=df.index)


@_registrar("sorpresa_total",
    validacion="SPECULATIVE", n_min=525, dsr=None,
    fuente="distortion_surprise_adelantada.py (17-Ago), ρ≤0.15")
def _sorpresa_total(df):
    """Sorpresa agregada de Shannon (alta = sistema en estado improbable).
    Computada desde los fact stores vía state_key. Umbral = tercil alto."""
    surprise = _surprise_vector(df)
    total = surprise.mean(axis=1, skipna=True)
    return total >= total.quantile(0.67)


@_registrar("panico_total",
    validacion="VALIDATED (Grade A)", n_min=30, dsr=0.9680,
    fuente="operational-spec: VIX+SKEW extremos, +6.81% 60d, 82% WR")
def _panico_total(df):
    """PÁNICO TOTAL: VIX y SKEW ambos en D1 extremo (bearish).
    VIX en ELEVATED_PANIC/CRISIS_SPIKE Y SKEW en TAIL_PARANOIA/BLACK_SWAN_PARANOIA."""
    vix_d1 = df["vix_sk"].str.split("__").str[0]
    skew_d1 = df["skew_sk"].str.split("__").str[0]
    return vix_d1.isin({"ELEVATED_PANIC", "CRISIS_SPIKE"}) & skew_d1.isin({"TAIL_PARANOIA", "BLACK_SWAN_PARANOIA"})


@_registrar("capitulacion",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: VIX↑ + S5 colapsa, +1.5% 20d, PF 2.19")
def _capitulacion(df):
    """CAPITULACIÓN: VIX en HIGH_VOL/CRISIS_SPIKE Y BSI en BREADTH_WASHED_OUT."""
    vix_d1 = df["vix_sk"].str.split("__").str[0]
    bsi_d1 = df["bsi_sk"].str.split("__").str[0]
    return vix_d1.isin({"HIGH_VOL", "CRISIS_SPIKE"}) & (bsi_d1 == "BREADTH_WASHED_OUT")


@_registrar("sub_reaccion",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: VIX↑ + S5 mantiene, esperar")
def _sub_reaccion(df):
    """SUB-REACCIÓN: VIX en extremo (HIGH_VOL/CRISIS_SPIKE) pero BSI NO en BREADTH_WASHED_OUT."""
    vix_d1 = df["vix_sk"].str.split("__").str[0]
    bsi_d1 = df["bsi_sk"].str.split("__").str[0]
    return vix_d1.isin({"HIGH_VOL", "CRISIS_SPIKE"}) & (bsi_d1 != "BREADTH_WASHED_OUT")


@_registrar("euforia",
    validacion="MODERATE", n_min=20, dsr=None,
    fuente="operational-spec: VIX↓ + S5 máximos, techo")
def _euforia(df):
    """EUFORIA: VIX en DEEP_COMPLACENCY/LOW_VOL y BSI en BULLISH_BREADTH (o no extremo)."""
    vix_d1 = df["vix_sk"].str.split("__").str[0]
    bsi_d1 = df["bsi_sk"].str.split("__").str[0]
    return vix_d1.isin({"DEEP_COMPLACENCY", "LOW_VOL"}) & (bsi_d1 != "BREADTH_WASHED_OUT")


@_registrar("vvix_entry",
    validacion="VALIDATED (Grade A)", n_min=30, dsr=None,
    fuente="operational-spec: EXTREME_VVIX, +2.69% 20d, Kelly 61%")
def _vvix_entry(df):
    """VVIX en EXTREME_VVIX."""
    return df["vvix_sk"].str.split("__").str[0] == "EXTREME_VVIX"


@_registrar("bsi_washed_out",
    validacion="VALIDATED (Grade A)", n_min=58, dsr=None,
    fuente="operational-spec: BREADTH_WASHED_OUT, +2.6% 20d, WR 69%")
def _bsi_washed_out(df):
    """BSI en BREADTH_WASHED_OUT."""
    return df["bsi_sk"].str.split("__").str[0] == "BREADTH_WASHED_OUT"


@_registrar("credit_stress",
    validacion="VALIDATED (Grade A)", n_min=82, dsr=0.9509,
    fuente="operational-spec: CREDIT_STRESS, +3.00% 20d, Kelly 50%")
def _credit_stress(df):
    """CREDIT en CREDIT_STRESS."""
    return df["credit_sk"].str.split("__").str[0] == "CREDIT_STRESS"


@_registrar("dxy_bearish",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: DOLLAR_SPIKE_CRISIS, −1.94% 20d, WR 28%")
def _dxy_bearish(df):
    """DXY en DOLLAR_SPIKE_CRISIS."""
    return df["dxy_sk"].str.split("__").str[0] == "DOLLAR_SPIKE_CRISIS"


@_registrar("pcr_put_panic",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: EXTREME_PUT_PANIC, +2.26% 20d, WR 79%")
def _pcr_put_panic(df):
    """PCR en EXTREME_PUT_PANIC."""
    return df["pcr_sk"].str.split("__").str[0] == "EXTREME_PUT_PANIC"


@_registrar("fg_extreme_fear",
    validacion="VALIDATED", n_min=54, dsr=None,
    fuente="auditoria 17-Ago: EXTREME_FEAR=+1.58% WR=68.5% N=54")
def _fg_extreme_fear(df):
    """FG en EXTREME_FEAR — miedo extremo."""
    mask = df["fg_sk"].dropna().str.split("__").str[0] == "EXTREME_FEAR"
    return mask.reindex(df.index, fill_value=False)


@_registrar("fg_extreme_greed",
    validacion="VALIDATED", n_min=31, dsr=None,
    fuente="auditoria 17-Ago: EXTREME_GREED=-1.92% WR=19.4% N=31")
def _fg_extreme_greed(df):
    """FG en EXTREME_GREED — codicia extrema (techo)."""
    mask = df["fg_sk"].dropna().str.split("__").str[0] == "EXTREME_GREED"
    return mask.reindex(df.index, fill_value=False)


# ─────────────────────────────────────────────────────────────────────────────
# 2.5 SEÑALES DE EXIT (propuestas 18-Ago-2026)
# ─────────────────────────────────────────────────────────────────────────────

@_registrar("bsi_recovery",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: BSI sale de BREADTH_WASHED_OUT")
def _bsi_recovery(df):
    """BSI sale de BREADTH_WASHED_OUT → NEUTRAL_HIGH_BREADTH o EXPANSIVE_BREADTH.
    FIX 20-Ago-2026: 'BREADTH_RECOVERY' era un label fantasma (0 ocurrencias).
    El label correcto del generador para bin 4 es EXPANSIVE_BREADTH.
    """
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    mask = bsi_d1.isin(["NEUTRAL_HIGH_BREADTH", "EXPANSIVE_BREADTH"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("vix_crisis_spike",
    validacion="RECLASIFICADA ENTRY (20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: VIX entra en CRISIS_SPIKE. Edge +0.75% positivo → reclasificada como ENTRY (comprar miedo).")
def _vix_crisis_spike(df):
    """[RECLASIFICADA ENTRY 20-Ago-2026] VIX entra en CRISIS_SPIKE.
    Edge = +0.75%, WR = 56.7%, LIFT(MAX) = 0.728x (reduce caída en techos).
    A pesar de que el nombre sugiere peligro, el forward es POSITIVO:
    el pánico de volatilidad es contrarian — momento de comprar, no de vender.
    """
    vix_d1 = df["vix_sk"].dropna().str.split("__").str[0]
    mask = vix_d1 == "CRISIS_SPIKE"
    return mask.reindex(df.index, fill_value=False)


@_registrar("cascade_reversal",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: cascade_conviction_50 < 0.30")
def _cascade_reversal(df):
    """cascade_conviction_50 cae por debajo de 0.30 — reversal."""
    if "cascade_conviction_50" not in df.columns:
        return pd.Series(False, index=df.index)
    mask = df["cascade_conviction_50"] < 0.30
    return mask.fillna(False)


@_registrar("credit_stress_exit",
    validacion="RETIRADA (duplicado exacto de credit_stress — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: CREDIT entra en CREDIT_STRESS. RETIRADA: código idéntico a credit_stress (N=215, edge=+1.00%).")
def _credit_stress_exit(df):
    """[RETIRADA 20-Ago-2026] Duplicado exacto de credit_stress.
    Mismo código, mismo N=215, mismo edge=+1.00%.
    El sufijo '_exit' es fraudulento — edge positivo = ENTRY, no EXIT.
    Usar credit_stress en su lugar.
    """
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    mask = credit_d1 == "CREDIT_STRESS"
    return mask.reindex(df.index, fill_value=False)


@_registrar("dxy_spike_exit",
    validacion="RETIRADA (duplicado exacto de dxy_bearish — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: DXY entra en DOLLAR_SPIKE_CRISIS. RETIRADA: código idéntico a dxy_bearish (N=35).")
def _dxy_spike_exit(df):
    """[RETIRADA 20-Ago-2026] Duplicado exacto de dxy_bearish.
    Mismo código, mismo N=35, mismo edge≈0.
    Usar dxy_bearish en su lugar.
    """
    dxy_d1 = df["dxy_sk"].dropna().str.split("__").str[0]
    mask = dxy_d1 == "DOLLAR_SPIKE_CRISIS"
    return mask.reindex(df.index, fill_value=False)


@_registrar("pcr_panic_exit",
    validacion="RETIRADA (duplicado exacto de pcr_put_panic — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: PCR entra en EXTREME_PUT_PANIC. RETIRADA: código idéntico a pcr_put_panic (N=70, edge=+2.70%).")
def _pcr_panic_exit(df):
    """[RETIRADA 20-Ago-2026] Duplicado exacto de pcr_put_panic.
    Mismo código, mismo N=70, mismo edge=+2.70%.
    El sufijo '_exit' es fraudulento — edge positivo = ENTRY, no EXIT.
    Usar pcr_put_panic en su lugar.
    """
    pcr_d1 = df["pcr_sk"].dropna().str.split("__").str[0]
    mask = pcr_d1 == "EXTREME_PUT_PANIC"
    return mask.reindex(df.index, fill_value=False)


@_registrar("skew_paranoia_exit",
    validacion="RESCATADA (v6: +2.84% neto, p=0.091, N=16, INDEP=71% — método first-passage)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: SKEW entra en BLACK_SWAN_PARANOIA. Rescatada por arquitecto 22-Ago tras re-evaluación v6.")
def _skew_paranoia_exit(df):
    """[RESCATADA 22-Ago-2026] SKEW entra en BLACK_SWAN_PARANOIA.
    El método antiguo la degradó (GRADO C, LIFT≈1.0), pero el evaluador v6
    (first-passage, baseline por celda) muestra +2.84% favorable neto en zz75|ALZA,
    p=0.091 e INDEP=71% (alta independencia informacional). Incluida por el arquitecto.
    """
    skew_d1 = df["skew_sk"].dropna().str.split("__").str[0]
    mask = skew_d1 == "BLACK_SWAN_PARANOIA"
    return mask.reindex(df.index, fill_value=False)


@_registrar("vix_complacency_exit",
    validacion="RETIRADA (duplicado 100% overlap con euforia — 20-Ago-2026 Opus PC3)", n_min=None, dsr=None,
    fuente="EXIT: VIX en DEEP_COMPLACENCY/LOW_VOL → fin de euforia")
def _vix_complacency_exit(df):
    """[RETIRADA 20-Ago-2026: duplicado 100% idéntico a la señal validada 'euforia'. N=35, Lift=1.199x.]
    VIX en DEEP_COMPLACENCY o LOW_VOL — complacencia extrema, fin de euforia."""
    vix_d1 = df["vix_sk"].dropna().str.split("__").str[0]
    mask = vix_d1.isin(["DEEP_COMPLACENCY", "LOW_VOL"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("credit_ease_exit",
    validacion="RESCATADA (v6: +1.54% neto, p=0.0013, N=440 — método first-passage)", n_min=None, dsr=None,
    fuente="EXIT: CREDIT sale de CREDIT_EASE/DEEP_CREDIT_EASE → fin de easing")
def _credit_ease_exit(df):
    """[RESCATADA 22-Ago-2026: el método antiguo la descartó por lift<1.0, pero el evaluador
    v6 (first-passage, baseline por celda) muestra +1.54% favorable neto con p=0.0013.]
    CREDIT NO está en CREDIT_EASE ni DEEP_CREDIT_EASE — fin del easing."""
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    mask = ~credit_d1.isin(["CREDIT_EASE", "DEEP_CREDIT_EASE"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("breadth_contraction_exit",
    validacion="RESCATADA (v6: +0.84% neto, p=0.0008, N=709 — método first-passage)", n_min=None, dsr=None,
    fuente="EXIT: BSI sale de EXPANSIVE/HYPER_EXPANSIVE → fin de expansión")
def _breadth_contraction_exit(df):
    """[RESCATADA 22-Ago-2026: el método antiguo la descartó por fire rate alto, pero el evaluador
    v6 (first-passage, baseline por celda) muestra +0.84% favorable neto con p=0.0008.]
    BSI NO está en EXPANSIVE_BREADTH ni HYPER_EXPANSIVE_BREADTH — fin de expansión."""
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    mask = ~bsi_d1.isin(["EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("regime_change_exit",
    validacion="RETIRADA (lift<1.0 — 20-Ago-2026 Opus PC1)", n_min=None, dsr=None,
    fuente="EXIT: Cambio de régimen VERANO→INVIERNO (credit_stress + vix_high + bsi_low)")
def _regime_change_exit(df):
    """[RETIRADA 20-Ago-2026: lift=0.789x vs baseline MAX 83.4%. Peor que no hacer nada. Anti-señal.]
    Cambio de régimen: VERANO (credit_ease + vix_low + bsi_high) → INVIERNO (credit_stress + vix_high + bsi_low)."""
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    vix_d1 = df["vix_sk"].dropna().str.split("__").str[0]
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    invierno = (
        credit_d1.isin(["CREDIT_STRESS", "ELEVATED_CREDIT_STRESS", "CREDIT_CRISIS"]) &
        vix_d1.isin(["HIGH_VOL", "ELEVATED_PANIC", "CRISIS_SPIKE"]) &
        bsi_d1.isin(["BREADTH_WASHED_OUT", "OVERSOLD_BREADTH", "NEUTRAL_LOW_BREADTH"])
    )
    return invierno.reindex(df.index, fill_value=False)


@_registrar("sv5t_silent_distribution",
    validacion="RETIRADA (lift<1.0 — 20-Ago-2026 Opus PC1)", n_min=None, dsr=None,
    fuente="EXIT: SV5T en silencio institucional (LOW_TURBULENCE + VOL_EXPANSION) en techo")
def _sv5t_silent_distribution(df):
    """[RETIRADA 20-Ago-2026: lift=0.840x vs baseline MAX 83.4%. Peor que no hacer nada. Anti-señal.]
    En techo MAX, volumen institucional desaparece (LOW_TURBULENCE) y volatilidad expande."""
    is_max = df["pivot_type"] == "MAX"
    sv5t_sk = df["sv5_turbulence_sk"].dropna()
    d1 = sv5t_sk.str.split("__").str[0]
    d3 = sv5t_sk.str.split("__").str[2]
    cond = (d1 == "LOW_TURBULENCE") & d3.isin(["VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION"])
    mask = is_max & cond.reindex(df.index, fill_value=False)
    return mask


@_registrar("credit_equity_divergence",
    validacion="DEGRADADA GRADO C (LIFT≈1.0 — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="EXIT: Techo MAX con spread de crédito acelerando al alza. LIFT(MAX)=1.035x ≈ baseline (82.9%→85.8%) — NO discrimina.")
def _credit_equity_divergence(df):
    """[GRADO C 20-Ago-2026] En techo MAX, crédito se deteriora con velocidad positiva (D2=ACCELERATING_UP_3D).
    Edge=−3.15%, WR=14.2%, pero LIFT(MAX)=1.035x ≈ baseline.
    La divergencia crédito-equity NO funciona como señal EXIT independiente.
    Solo 3.5% mejor que no hacer nada. Monitorear con filtro HH.
    """
    is_max = df["pivot_type"] == "MAX"
    credit_sk = df["credit_sk"].dropna()
    d2 = credit_sk.str.split("__").str[1]
    cond = d2.isin(["ACCELERATING_UP_3D", "FAST_SPIKE_3D"])
    mask = is_max & cond.reindex(df.index, fill_value=False)
    return mask


@_registrar("stealth_tail_hedging",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: VIX complaciente pero SKEW en expansión de volatilidad/cobertura")
def _stealth_tail_hedging(df):
    """VIX en complacencia (LOW_VOL/DEEP_COMPLACENCY) mientras SKEW muestra compras OTM (VOL_EXPANSION)."""
    vix_sk = df["vix_sk"].dropna()
    skew_sk = df["skew_sk"].dropna()
    vix_d1 = vix_sk.str.split("__").str[0]
    skew_d3 = skew_sk.str.split("__").str[2]
    vix_low = vix_d1.isin(["DEEP_COMPLACENCY", "LOW_VOL", "MODERATE_VOL"])
    skew_exp = skew_d3.isin(["VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION"])
    mask = vix_low.reindex(df.index, fill_value=False) & skew_exp.reindex(df.index, fill_value=False)
    return mask


@_registrar("defensive_rotation_divergence",
    validacion="RETIRADA (lift<1.0 — 20-Ago-2026 Opus PC1)", n_min=None, dsr=None,
    fuente="EXIT: Techo MAX con rotación de capital colapsando hacia defensivos (FAST_CRUSH_3D)")
def _defensive_rotation_divergence(df):
    """[RETIRADA 20-Ago-2026: lift=0.828x vs baseline MAX 83.4%. Peor que no hacer nada. Anti-señal.]
    En techo MAX, rotación sectorial cae agresivamente (D2=FAST_CRUSH_3D o D1=DEFENSIVE)."""
    is_max = df["pivot_type"] == "MAX"
    rot_sk = df["rotation_sk"].dropna()
    d1 = rot_sk.str.split("__").str[0]
    d2 = rot_sk.str.split("__").str[1]
    cond = (d2 == "FAST_CRUSH_3D") | d1.isin(["DEFENSIVE", "DEFENSIVE_CAPITULATION"])
    mask = is_max & cond.reindex(df.index, fill_value=False)
    return mask


# ─────────────────────────────────────────────────────────────────────────────
# 3. VECTOR DE SORPRESA (Shannon) — compartido por las señales de distorsión
# ─────────────────────────────────────────────────────────────────────────────
_FS_DIR = ROOT / "backend/modules/entry_decision/domain/rules"
_ESTACIONES = ["vix", "bsi", "fg", "credit", "rotation",
               "sv5_turbulence", "skew", "pcr", "vvix", "yield_curve", "dxy"]
_CAT = {
    "credit": 1, "yield_curve": 1, "dxy": 1, "rotation": 1,
    "vix": 2, "vvix": 2, "pcr": 2, "skew": 2,
    "bsi": 3, "sv5_turbulence": 3, "fg": 3,
}


def _surprise_vector(df):
    """surprise_i = -log2(N_estado / N_total) por estación. Retorna DataFrame."""
    out = {}
    for code in _ESTACIONES:
        fp = _FS_DIR / f"{code}_fact_store.json"
        if not fp.exists():
            out[code] = np.nan
            continue
        with open(fp) as f:
            fs = json.load(f)
        states = fs.get("states", {})
        n_total = sum(s.get("n", 0) or 0 for s in states.values())
        sk_col = f"{code}_sk"
        if sk_col not in df.columns:
            out[code] = np.nan
            continue
        n_by_sk = {sk: (s.get("n", 0) or 0) for sk, s in states.items()}
        vals = []
        for sk in df[sk_col]:
            n = n_by_sk.get(sk, 0)
            if n <= 0 or n_total <= 0:
                vals.append(np.nan)
            else:
                vals.append(-np.log2(n / n_total))
        out[code] = vals
    return pd.DataFrame(out, index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
# 4. MÉTRICAS CENTRALES (matemática pura)
# ─────────────────────────────────────────────────────────────────────────────
def _pctiles(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return {"n": 0}
    return {
        "n": int(len(x)),
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "p5": float(np.percentile(x, 5)),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
        "p95": float(np.percentile(x, 95)),
        "std": float(np.std(x)),
    }


def _wins_losses(x):
    """wins/losses separados: win_rate, mean_win, mean_loss, profit_factor."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    wins = x[x > 0]
    losses = x[x < 0]
    if len(x) == 0:
        return {}
    gross_win = wins.sum() if len(wins) else 0.0
    gross_loss = abs(losses.sum()) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    return {
        "win_rate": float(len(wins) / len(x)),
        "n_wins": int(len(wins)),
        "n_losses": int(len(losses)),
        "mean_win": float(wins.mean()) if len(wins) else None,
        "mean_loss": float(losses.mean()) if len(losses) else None,
        "profit_factor": pf if pf != float("inf") else None,
    }


def _bootstrap_ci(metric_fn, data, n_iter=3000, seed=42):
    """CI95 bootstrap pareado de una métrica (media por defecto)."""
    rng = np.random.default_rng(seed)
    arr = np.asarray(data, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 20:
        return {"ci_lo": None, "ci_hi": None, "n": int(len(arr)), "nota": "N<20"}
    boots = []
    for _ in range(n_iter):
        idx = rng.integers(0, len(arr), len(arr))
        boots.append(metric_fn(arr[idx]))
    boots = np.array(boots)
    return {
        "ci_lo": float(np.percentile(boots, 2.5)),
        "ci_hi": float(np.percentile(boots, 97.5)),
        "n": int(len(arr)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. DRAWDOWN DE TIMING (MÉTRICAS INTRA-TRADE Y COSTO DE RETRASO)
# ─────────────────────────────────────────────────────────────────────────────
def _mae_intratrade(spy, señal, df):
    """MAE intra-trade real (máxima excursión adversa usando el Low del Vault).
    MAE_i = min_{t in [T0, T1]} (Low_t - Close_T0) / Close_T0, ≤ 0.
    T0 = fecha del pivote de señal, T1 = fecha del pivote siguiente en quants_obs.
    """
    if spy is None:
        return []
    maes = []
    for i in np.where(señal.values)[0]:
        t0 = df["pivot_date"].iloc[i]
        t1 = df["pivot_date"].iloc[i + 1] if i + 1 < len(df) else None
        loc0 = spy.index.searchsorted(t0)
        if loc0 >= len(spy):
            continue
        loc1 = spy.index.searchsorted(t1) if t1 is not None else len(spy) - 1
        if loc1 < loc0:
            loc1 = loc0
        slice_df = spy.iloc[loc0 : loc1 + 1]
        if len(slice_df) == 0:
            continue
        c0 = float(spy["close"].iloc[loc0])
        min_low = float(slice_df["low"].min())
        mae = (min_low - c0) / c0
        maes.append(mae)
    return maes


def _costo_tarde(spy, señal, df, k=1):
    """Costo medio de retrasar la entrada k barras, por trade.
    ΔOpportunity_i(k) = (Close[T0+k] - Close[T0]) / Close[T0]
    (el retorno que se pierde por esperar k barras tras la señal).
    """
    if spy is None:
        return {"n": 0, "costo_medio": None}
    costos = []
    for i in np.where(señal.values)[0]:
        t0 = df["pivot_date"].iloc[i]
        loc = spy.index.searchsorted(t0)
        if loc + k >= len(spy):
            continue
        c0 = float(spy["close"].iloc[loc])
        ck = float(spy["close"].iloc[loc + k])
        costos.append((ck - c0) / c0)
    if not costos:
        return {"n": 0, "costo_medio": None}
    return {
        "n": int(len(costos)),
        "costo_medio": float(np.mean(costos)),
        "p50": float(np.median(costos)),
        "p5": float(np.percentile(costos, 5)),
        "p95": float(np.percentile(costos, 95)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. SENSIBILIDAD AL TIMING (BARRAS DIARIAS CONTINUAS)
# ─────────────────────────────────────────────────────────────────────────────
def _sensibilidad_timing(spy, señal, df, ks=(0, 1, 2, 3, 5)):
    """Para cada k de retraso en BARRAS, medir el forward retorno medio
    si la entrada se ejecuta k barras después de la señal.
    forward_k_i = (Close[T1] - Close[T0+k]) / Close[T0+k].
    """
    if spy is None:
        return []
    res = []
    for k in ks:
        rets = []
        for i in np.where(señal.values)[0]:
            t0 = df["pivot_date"].iloc[i]
            t1 = df["pivot_date"].iloc[i + 1] if i + 1 < len(df) else None
            loc0 = spy.index.searchsorted(t0)
            loc_k = loc0 + k
            loc1 = spy.index.searchsorted(t1) if t1 is not None else len(spy) - 1
            if loc_k >= len(spy) or loc1 >= len(spy) or loc_k > loc1:
                continue
            c_k = float(spy["close"].iloc[loc_k])
            c_1 = float(spy["close"].iloc[loc1])
            ret_k = (c_1 - c_k) / c_k
            rets.append(ret_k)
        if len(rets) < 20:
            res.append({"k": int(k), "n": int(len(rets)), "mean": None})
        else:
            res.append({"k": int(k), "n": int(len(rets)), "mean": float(np.nanmean(rets))})
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 7. REPORTE COMPLETO DE UNA SEÑAL
# ─────────────────────────────────────────────────────────────────────────────
# ─── ADDENDUM 1: Structural Momentum Filter ───
def _structural_momentum_filter(señal, df, spy=None):
    """Clasifica momentum estructural (HL/LL para ENTRY, LH/HH para EXIT).
    HL = Higher Low → comprable. LL = Lower Low → TRAMPA bajista.
    LH = Lower High → deterioro. HH = Higher High → clímax de distribución.
    NOTA (validacion_5_interpretaciones_fact_store.md, P1): p_continuation y p_bull
    son ORTOGONALES (r=0.015). Reportar ambos por separado.
    Usa precios SPY en fechas de pivote para clasificar HL/LL y LH/HH correctamente.
    """
    rep_sm = {}
    if señal.sum() == 0:
        return rep_sm

    pivot_types_activos = df.loc[señal, "pivot_type"].unique()

    # Construir serie de precios SPY en fechas de pivote (si spy disponible)
    spy_close_at_pivot = None
    if spy is not None and "close" in spy.columns:
        try:
            closes = spy["close"]
            positions = closes.index.get_indexer(df["pivot_date"], method="nearest")
            spy_close_at_pivot = pd.Series(
                closes.iloc[positions].values, index=df.index
            )
            # Marcar NaN donde el indexer falló (-1)
            spy_close_at_pivot[positions == -1] = np.nan
        except Exception:
            spy_close_at_pivot = None

    # ENTRY (MIN pivots): HL vs LL
    if "MIN" in pivot_types_activos:
        min_mask = señal & (df["pivot_type"] == "MIN")
        min_idx = df.index[min_mask]

        if spy_close_at_pivot is not None and spy_close_at_pivot[min_mask].notna().sum() >= 5:
            # Clasificación por precio: MIN actual vs MIN anterior (en secuencia completa)
            all_min_idx = df.index[df["pivot_type"] == "MIN"]
            all_min_prices = spy_close_at_pivot[all_min_idx]
            # Para cada MIN activo en la señal, encontrar el MIN anterior en secuencia completa
            hl_count, ll_count = 0, 0
            for idx in min_idx:
                pos_in_all_min = all_min_idx.get_loc(idx)
                if pos_in_all_min == 0:
                    continue
                prev_min_idx = all_min_idx[pos_in_all_min - 1]
                p_curr = spy_close_at_pivot.get(idx)
                p_prev = spy_close_at_pivot.get(prev_min_idx)
                if p_curr is None or p_prev is None or pd.isna(p_curr) or pd.isna(p_prev):
                    continue
                if p_curr > p_prev:
                    hl_count += 1
                else:
                    ll_count += 1
            n_total = hl_count + ll_count
            if n_total > 0:
                rep_sm["entry"] = {
                    "n_hl": hl_count, "n_ll": ll_count, "n_total": n_total,
                    "p_hl": round(hl_count / n_total, 3),
                    "metodo": "precio SPY en pivotes MIN consecutivos",
                    "interpretacion": "HL = comprable. LL = TRAMPA (estructura bajista). "
                                      "p_hl y p_bull son ejes ORTOGONALES (r=0.015)."
                }
        else:
            # Fallback: heurística con prev_leg_return
            min_pivots = df[min_mask]
            prev_leg_shift = min_pivots["prev_leg_return"].shift(1)
            valid = prev_leg_shift.notna()
            hl_count = int((prev_leg_shift[valid] > 0).sum())
            ll_count = int((prev_leg_shift[valid] <= 0).sum())
            n_total = hl_count + ll_count
            if n_total > 0:
                rep_sm["entry"] = {
                    "n_hl": hl_count, "n_ll": ll_count, "n_total": n_total,
                    "p_hl": round(hl_count / n_total, 3),
                    "metodo": "heurística prev_leg_return (fallback)",
                    "interpretacion": "HL = comprable. LL = TRAMPA (estructura bajista). "
                                      "p_hl y p_bull son ejes ORTOGONALES (r=0.015)."
                }

    # EXIT (MAX pivots): LH vs HH
    if "MAX" in pivot_types_activos:
        max_mask = señal & (df["pivot_type"] == "MAX")
        max_idx = df.index[max_mask]

        if spy_close_at_pivot is not None and spy_close_at_pivot[max_mask].notna().sum() >= 5:
            all_max_idx = df.index[df["pivot_type"] == "MAX"]
            all_max_prices = spy_close_at_pivot[all_max_idx]
            lh_count, hh_count = 0, 0
            for idx in max_idx:
                pos_in_all_max = all_max_idx.get_loc(idx)
                if pos_in_all_max == 0:
                    continue
                prev_max_idx = all_max_idx[pos_in_all_max - 1]
                p_curr = spy_close_at_pivot.get(idx)
                p_prev = spy_close_at_pivot.get(prev_max_idx)
                if p_curr is None or p_prev is None or pd.isna(p_curr) or pd.isna(p_prev):
                    continue
                if p_curr < p_prev:
                    lh_count += 1
                else:
                    hh_count += 1
            n_total = lh_count + hh_count
            if n_total > 0:
                rep_sm["exit"] = {
                    "n_lh": lh_count, "n_hh": hh_count, "n_total": n_total,
                    "p_hh": round(hh_count / n_total, 3),
                    "metodo": "precio SPY en pivotes MAX consecutivos",
                    "interpretacion": "HH cae 90.2% de las veces (33años SPY N=429). "
                                      "AMPLIFICAR EXIT en HH. LH cae 75.3% (N=364)."
                }
        else:
            # Fallback: heurística con prev_leg_return
            max_pivots = df[max_mask]
            prev_leg_shift = max_pivots["prev_leg_return"].shift(1)
            valid = prev_leg_shift.notna()
            lh_count = int((prev_leg_shift[valid] < 0).sum())
            hh_count = int((prev_leg_shift[valid] >= 0).sum())
            n_total = lh_count + hh_count
            if n_total > 0:
                rep_sm["exit"] = {
                    "n_lh": lh_count, "n_hh": hh_count, "n_total": n_total,
                    "p_hh": round(hh_count / n_total, 3),
                    "metodo": "heurística prev_leg_return (fallback)",
                    "interpretacion": "HH cae 90.2% de las veces (33años SPY N=429). "
                                      "AMPLIFICAR EXIT en HH. LH cae 75.3% (N=364)."
                }
    return rep_sm


# ─── ADDENDUM 2: Prev Leg Domino (Lookback) ───
def _prev_leg_context(señal, fwd, df):
    """Contexto de la pierna previa: ¿venimos de un crash (>P90) o de un drift normal?
    NOTA (validacion_5_interpretaciones_fact_store.md, P2): umbral >50% es inalcanzable
    en VIX (0/47 estados). Usar >20% o >30% como umbral operativo.
    """
    abs_prev = df["prev_leg_return"].abs()
    p90_thr = float(np.percentile(abs_prev.dropna(), 90))

    prev_leg_act = abs_prev[señal].dropna()
    n_extreme = int((prev_leg_act > p90_thr).sum())
    n_normal = int((prev_leg_act <= p90_thr).sum())

    rep_plc = {
        "p90_threshold_abs_return": round(p90_thr, 4),
        "n_extreme_prev_leg": n_extreme,
        "n_normal_prev_leg": n_normal,
        "pct_extreme": round(n_extreme / len(prev_leg_act), 3) if len(prev_leg_act) > 0 else 0,
        "umbral_operativo": ">20% o >30% (el >50% es inalcanzable en VIX fact store)",
        "interpretacion": "pct_extreme alto = señal activada post-crash. Edge amplificado."
    }

    # Desglose forward por contexto (solo si ambos tienen n>=3)
    if n_extreme >= 3 and n_normal >= 3:
        fwd_extreme = fwd[señal & (abs_prev > p90_thr) & fwd.notna()]
        fwd_normal = fwd[señal & (abs_prev <= p90_thr) & fwd.notna()]
        if len(fwd_extreme) > 0:
            rep_plc["forward_extreme_prev"] = {
                "n": int(len(fwd_extreme)),
                "mean": round(float(np.nanmean(fwd_extreme)), 4),
                "win_rate": round(float((fwd_extreme > 0).mean()), 3)
            }
        if len(fwd_normal) > 0:
            rep_plc["forward_normal_prev"] = {
                "n": int(len(fwd_normal)),
                "mean": round(float(np.nanmean(fwd_normal)), 4),
                "win_rate": round(float((fwd_normal > 0).mean()), 3)
            }
    return rep_plc


# ─── ADDENDUM 3: Temporal Divergence Regime ───
def _divergence_regime(rep):
    """Clasifica convergencia/divergencia entre las 3 escalas zigzag.
    CONCEPTO DERIVADO: el fact store NO tiene este campo. Se deriva
    comparando p_bull en las 3 escalas (zz25/zz50/zz75).
    """
    tr = rep.get("triada", {})
    zz25_wr = tr.get("zz25", {}).get("win_rate", 0.0)
    c50 = tr.get("cascade_50", {}).get("rate_activa", 0.0)
    c75 = tr.get("cascade_75", {}).get("rate_activa", 0.0)
    n_activo = tr.get("zz25", {}).get("n", 0)

    # PROTOCOLO DIAMANTES (fact_store_v3_architecture.md §3.3):
    # N bajo ≠ descartable. Los eventos raros son diamantes estadísticos
    # que se analizan por separado, listando cada evento individualmente
    # con la tasa CRUDA (sin shrinkage agresivo).
    if n_activo < 3:
        return {
            "regime": "DIAMANTE_ANECDOTAL",
            "tier": "ANECDOTAL (N=1-2)" if n_activo >= 1 else "NONE (N=0)",
            "n_activo": n_activo,
            "interpretacion": "Diamante estadístico: el evento existe y tuvo un resultado "
                              "específico, pero no permite inferencia probabilística. "
                              "Analizar CADA evento individualmente (fecha, contexto, resultado). "
                              "NUNCA descartar por N bajo.",
            "zz25_wr": round(zz25_wr, 4),
            "cascade_50_rate": round(c50, 4),
            "cascade_75_rate": round(c75, 4),
            "fuente": "fact_store_v3_architecture.md §3.3 — Diamantes Estadísticos."
        }

    # Umbrales calibrados contra datos reales (20-Ago-2026):
    #   credit_easing_k1: WR=93.8%, c50=53.6%, c75=32.1% → FULL_CONVERGENT_BULL
    #   sub_reaccion:     WR=50.2%, c50=40.8%, c75=20.5% → MIXED_HORIZON_TRANSITION
    if zz25_wr > 0.55 and c50 > 0.50 and c75 > 0.28:
        regime = "FULL_CONVERGENT_BULL"
        interp = "Las 3 escalas confirman: señal ALCISTA en retracción, corrección y depresión."
    elif zz25_wr < 0.45 and c50 < 0.45 and c75 < 0.30:
        regime = "FULL_CONVERGENT_BEAR"
        interp = "Las 3 escalas confirman: señal BAJISTA en todas las dimensiones."
    elif zz25_wr > 0.55 and c50 < 0.45:
        regime = "TACTICAL_ONLY"
        interp = "Funciona en zz25 pero NO escala a zz50. Movimiento táctico contenido."
    elif zz25_wr < 0.50 and c50 > 0.55:
        regime = "STRUCTURAL_BUILDUP"
        interp = "Ambigua en zz25 pero SÍ escala a zz50. Mercado preparándose para movimiento mayor."
    elif c50 > 0.50 and c75 < 0.25:
        regime = "CORRECTION_CONTAINED"
        interp = "Corrección intermedia pero NO depresión. Contenido en zz50."
    else:
        regime = "MIXED_HORIZON_TRANSITION"
        interp = "Las escalas no convergen — transición entre regímenes."

    return {
        "regime": regime,
        "interpretacion": interp,
        "zz25_wr": round(zz25_wr, 4),
        "cascade_50_rate": round(c50, 4),
        "cascade_75_rate": round(c75, 4),
        "fuente": "CONCEPTO DERIVADO — el fact store NO tiene este campo nativo."
    }


# ─── LIFT vs baseline condicionado por pivot_type (ADDENDUM 9 — 20-Ago-2026) ───
def _lift_vs_baseline(señal, fwd, df):
    """Calcula lift = P(cae | señal) / P(cae | ¬señal) condicionado por pivot_type."""
    pivot_types = df.loc[señal, "pivot_type"].unique()
    lifts = {}
    for pt in pivot_types:
        mask_pt = df["pivot_type"] == pt
        mask_activa = señal & mask_pt & fwd.notna()
        mask_no_activa = (~señal) & mask_pt & fwd.notna()
        n_act = mask_activa.sum()
        n_noact = mask_no_activa.sum()
        if n_act < 3 or n_noact < 3:
            continue
        p_cae_act = float((fwd[mask_activa] <= 0).mean())
        p_cae_noact = float((fwd[mask_no_activa] <= 0).mean())
        lift = p_cae_act / p_cae_noact if p_cae_noact > 0 else 999.0
        lifts[pt] = {
            "n_activa": int(n_act), "n_no_activa": int(n_noact),
            "pct_cae_activa": round(p_cae_act * 100, 1),
            "pct_cae_no_activa": round(p_cae_noact * 100, 1),
            "lift": round(lift, 3),
            "interpretacion": ">1.0=señal real, <1.0=anti-señal, ≈1.0=ruido"
        }
    return lifts


def medir(señal_nombre, df, forward_col, spy=None, n_iter=3000, seed=42):
    if señal_nombre not in SEÑALES:
        raise ValueError(f"Señal desconocida: {señal_nombre}. Disponibles: {list(SEÑALES)}")
    señal = SEÑALES[señal_nombre](df)
    señal = señal.astype(bool)

    # forward: retorno de la pierna siguiente (default) o columna especificada
    if forward_col == "next_leg":
        fwd = df["prev_leg_return"].shift(-1)
    elif forward_col in df.columns:
        fwd = df[forward_col]
    else:
        raise ValueError(f"Columna forward desconocida: {forward_col}")

    rep = {"señal": señal_nombre, "forward": forward_col, "n_total": int(len(df))}

    # 4.1 distribución + wins/losses, señal activa vs baseline condicionado
    act = fwd[señal & fwd.notna()]

    # Baseline condicionado al mismo pivot_type (evita mezclar piernas bajistas en señales MIN)
    pivot_señal = df.loc[señal, "pivot_type"].unique()
    if len(pivot_señal) > 0 and len(pivot_señal) < len(df["pivot_type"].unique()):
        mask_base = (~señal) & df["pivot_type"].isin(pivot_señal) & fwd.notna()
        baseline_type = list(pivot_señal) if len(pivot_señal) > 1 else str(pivot_señal[0])
    else:
        mask_base = (~señal) & fwd.notna()
        baseline_type = "ALL"

    base = fwd[mask_base]
    rep["activa"] = {"dist": _pctiles(act), "wl": _wins_losses(act),
                     "ci_mean": _bootstrap_ci(np.mean, act, n_iter, seed)}
    rep["baseline"] = {"dist": _pctiles(base), "wl": _wins_losses(base)}
    rep["baseline_pivot_type"] = baseline_type
    if len(act) and len(base):
        rep["delta_media"] = float(np.nanmean(act) - np.nanmean(base))

    # 4.2 drawdown de timing (MAE intra-trade real, solo señal activa)
    maes = _mae_intratrade(spy, señal, df)
    rep["timing_temprano"] = {"estadistica": _pctiles(maes)}

    # 4.3 costo de oportunidad de entrar tarde (por trade)
    rep["costo_tarde"] = _costo_tarde(spy, señal, df, k=1)

    # 4.4 sensibilidad al timing (retraso en barras diarias continuas)
    rep["sensibilidad"] = _sensibilidad_timing(spy, señal, df, ks=(0, 1, 2, 3, 5))

    # 4.5 Medición por escala triádica: zz25, cascade_50, cascade_75, duration_bars
    c50_act = df.loc[señal, "cascade_50"].dropna()
    c50_base = df.loc[mask_base, "cascade_50"].dropna()
    c75_act = df.loc[señal, "cascade_75"].dropna()
    c75_base = df.loc[mask_base, "cascade_75"].dropna()
    dur_act = df.loc[señal, "duration_bars"].dropna()
    dur_base = df.loc[mask_base, "duration_bars"].dropna()

    c50_rate_act = float(c50_act.mean()) if len(c50_act) else 0.0
    c50_rate_base = float(c50_base.mean()) if len(c50_base) else 0.0
    c75_rate_act = float(c75_act.mean()) if len(c75_act) else 0.0
    c75_rate_base = float(c75_base.mean()) if len(c75_base) else 0.0

    rep["triada"] = {
        "zz25": {
            "mean": float(np.nanmean(act)) if len(act) else 0.0,
            "median": float(np.nanmedian(act)) if len(act) else 0.0,
            "win_rate": float((act > 0).mean()) if len(act) else 0.0,
            "n": int(len(act)),
        },
        "cascade_50": {
            "rate_activa": c50_rate_act,
            "rate_baseline": c50_rate_base,
            "delta": float(c50_rate_act - c50_rate_base),
            "n": int(len(c50_act)),
        },
        "cascade_75": {
            "rate_activa": c75_rate_act,
            "rate_baseline": c75_rate_base,
            "delta": float(c75_rate_act - c75_rate_base),
            "n": int(len(c75_act)),
        },
        "duracion_bars": {
            "mean": float(dur_act.mean()) if len(dur_act) else 0.0,
            "median": float(dur_act.median()) if len(dur_act) else 0.0,
            "baseline_mean": float(dur_base.mean()) if len(dur_base) else 0.0,
            "n": int(len(dur_act)),
        },
    }

    # 4.5b Desglose short/long por duration_bars
    if señal.sum() > 0 and "duration_bars" in df.columns:
        dur_sig = df.loc[señal, "duration_bars"].dropna()
        if len(dur_sig) >= 10:
            median_dur = float(dur_sig.median())
            cortas = señal & (df["duration_bars"] <= median_dur)
            largas = señal & (df["duration_bars"] > median_dur)
            fwd_cortas = fwd[cortas & fwd.notna()]
            fwd_largas = fwd[largas & fwd.notna()]
            rep["duracion_desglose"] = {
                "mediana_bars": round(median_dur, 1),
                "cortas": {
                    "n": int(len(fwd_cortas)),
                    "fwd_mean": round(float(np.nanmean(fwd_cortas)), 6) if len(fwd_cortas) else None,
                    "wr": round(float((fwd_cortas > 0).mean()), 4) if len(fwd_cortas) else None,
                },
                "largas": {
                    "n": int(len(fwd_largas)),
                    "fwd_mean": round(float(np.nanmean(fwd_largas)), 6) if len(fwd_largas) else None,
                    "wr": round(float((fwd_largas > 0).mean()), 4) if len(fwd_largas) else None,
                },
                "delta": round(float(np.nanmean(fwd_cortas) - np.nanmean(fwd_largas)), 6) if len(fwd_cortas) and len(fwd_largas) else None,
            }
        else:
            rep["duracion_desglose"] = None
    else:
        rep["duracion_desglose"] = None

    # 4.6 Anticipación temporal: días antes del pivot en que la señal ya estaba activa
    señal_shift1 = señal.shift(1, fill_value=False)
    señal_shift_1 = señal.shift(-1, fill_value=False)

    if señal.sum() > 0:
        anticipaciones_dias = []
        for i in np.where(señal.values)[0]:
            pivot_date_actual = df["pivot_date"].iloc[i]
            # Buscar pivote anterior con señal activa
            pivote_anterior_idx = None
            for j in range(i - 1, -1, -1):
                if señal.iloc[j]:
                    pivote_anterior_idx = j
                    break
            if pivote_anterior_idx is not None:
                fecha_anterior = df["pivot_date"].iloc[pivote_anterior_idx]
                dias_antes = (pivot_date_actual - fecha_anterior).days
            else:
                dias_antes = 0
            anticipaciones_dias.append(dias_antes)

        anticipaciones_arr = np.array(anticipaciones_dias)
        n_total = int(len(anticipaciones_dias))
        n_anticipados = int((anticipaciones_arr > 0).sum())
        rep["anticipacion_zigzag"] = {
            "mean_dias": round(float(np.mean(anticipaciones_arr)), 2),
            "median_dias": round(float(np.median(anticipaciones_arr)), 2),
            "p5_dias": round(float(np.percentile(anticipaciones_arr, 5)), 2),
            "p25_dias": round(float(np.percentile(anticipaciones_arr, 25)), 2),
            "p75_dias": round(float(np.percentile(anticipaciones_arr, 75)), 2),
            "p95_dias": round(float(np.percentile(anticipaciones_arr, 95)), 2),
            "n_total": n_total,
            "n_anticipados": n_anticipados,
            "pct_anticipados": round(float((anticipaciones_arr > 0).mean() * 100), 1),
        }
    else:
        rep["anticipacion_zigzag"] = None

    # 4.7 Capture ratio: forward_return / abs(prev_leg_return), separado por pivot_type
    zz25_act = act
    zz25_leg = df.loc[señal, "prev_leg_return"].dropna()
    if len(zz25_act) > 0 and len(zz25_leg) > 0:
        abs_leg_mean = float(np.nanmean(np.abs(zz25_leg)))
        fwd_mean = float(np.nanmean(zz25_act))
        cr_global = fwd_mean / abs_leg_mean if abs_leg_mean > 1e-8 else 0.0
        # Per pivot_type breakdown
        cr_by_type = {}
        for pt_val in df.loc[señal, "pivot_type"].unique():
            pt_mask = señal & (df["pivot_type"] == pt_val)
            pt_fwd = fwd[pt_mask & fwd.notna()]
            pt_leg = df.loc[pt_mask, "prev_leg_return"].dropna()
            if len(pt_fwd) >= 5 and len(pt_leg) >= 5:
                abs_leg = float(np.nanmean(np.abs(pt_leg)))
                pt_fwd_mean = float(np.nanmean(pt_fwd))
                cr_by_type[pt_val] = {
                    "ratio": round(pt_fwd_mean / abs_leg if abs_leg > 1e-8 else 0.0, 4),
                    "fwd_mean": round(pt_fwd_mean, 6),
                    "abs_leg_mean": round(abs_leg, 6),
                    "n": int(len(pt_fwd)),
                }
        rep["capture_ratio"] = {
            "ratio": round(cr_global, 4),
            "fwd_mean": round(fwd_mean, 6),
            "abs_leg_mean": round(abs_leg_mean, 6),
            "n": int(len(zz25_act)),
            "por_pivot_type": cr_by_type,
        }
    else:
        rep["capture_ratio"] = None

    # 4.8 Drawdown por anticipación (entrada temprana) y salida tardía
    if señal.sum() > 0:
        early_mask = señal_shift1 & señal
        early_fwd = fwd[early_mask & fwd.notna()]
        early_mae = _mae_intratrade(spy, early_mask, df) if spy is not None else []
        late_mask = señal & señal_shift_1
        late_fwd = fwd[late_mask & fwd.notna()]
        late_mae = _mae_intratrade(spy, late_mask, df) if spy is not None else []
        rep["drawdown_anticipacion"] = {
            "entrada_temprana": {
                "n": int(len(early_fwd)),
                "forward_mean": float(np.nanmean(early_fwd)) if len(early_fwd) else None,
                "mae_medio": float(np.nanmean(early_mae)) if len(early_mae) else None,
            },
            "salida_tardia": {
                "n": int(len(late_fwd)),
                "forward_mean": float(np.nanmean(late_fwd)) if len(late_fwd) else None,
                "mae_medio": float(np.nanmean(late_mae)) if len(late_mae) else None,
            },
        }
    else:
        rep["drawdown_anticipacion"] = None

    # 4.8 Desglose D2×D3: breakdown del forward por dimensión DENTRO del D1 filtrado
    # Detecta las estaciones primarias usadas por la señal (las _sk que tienen D1 uniforme)
    desglose = {}
    sk_cols = [c for c in df.columns if c.endswith("_sk")]
    for sk_col in sk_cols:
        station = sk_col.replace("_sk", "")
        sk_series = df.loc[señal, sk_col].dropna()
        if len(sk_series) < 10:
            continue
        d1_vals = sk_series.str.split("__").str[0]
        # Only decompose if ≥80% of signal events share the same D1
        top_d1 = d1_vals.value_counts()
        if len(top_d1) == 0:
            continue
        dominant_d1 = top_d1.index[0]
        dominant_pct = top_d1.iloc[0] / len(d1_vals)
        if dominant_pct < 0.50:
            continue

        # D2 breakdown within dominant D1
        d1_mask = señal & (df[sk_col].str.split("__").str[0] == dominant_d1)
        d2_series = df.loc[d1_mask, sk_col].str.split("__").str[1]
        d3_series = df.loc[d1_mask, sk_col].str.split("__").str[2]

        d2_breakdown = {}
        d2_fwd_pools = {}  # store fwd arrays for CI calculation
        for d2v in sorted(d2_series.dropna().unique()):
            sub_mask = d1_mask & (df[sk_col].str.split("__").str[1] == d2v)
            sub_fwd = fwd[sub_mask & fwd.notna()]
            if len(sub_fwd) >= 5:
                wr = float((sub_fwd > 0).mean())
                d2_breakdown[d2v] = {
                    "n": int(len(sub_fwd)),
                    "mean": round(float(sub_fwd.mean()), 6),
                    "wr": round(wr, 4),
                    "tag": "FAVORABLE" if wr > 0.55 else "UNFAVORABLE" if wr < 0.45 else "NEUTRAL",
                }
                d2_fwd_pools[d2v] = sub_fwd.values

        # Bootstrap CI for best-vs-worst D2 spread
        d2_ci = None
        if len(d2_fwd_pools) >= 2:
            best_k = max(d2_fwd_pools, key=lambda k: np.nanmean(d2_fwd_pools[k]))
            worst_k = min(d2_fwd_pools, key=lambda k: np.nanmean(d2_fwd_pools[k]))
            b_arr, w_arr = d2_fwd_pools[best_k], d2_fwd_pools[worst_k]
            rng = np.random.default_rng(seed)
            diffs = [np.mean(rng.choice(b_arr, len(b_arr))) - np.mean(rng.choice(w_arr, len(w_arr))) for _ in range(n_iter)]
            ci_lo, ci_hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
            d2_ci = {"best": best_k, "worst": worst_k, "ci_lo": round(ci_lo, 6), "ci_hi": round(ci_hi, 6),
                     "significativo": ci_lo > 0}

        d3_breakdown = {}
        d3_fwd_pools = {}
        for d3v in sorted(d3_series.dropna().unique()):
            sub_mask = d1_mask & (df[sk_col].str.split("__").str[2] == d3v)
            sub_fwd = fwd[sub_mask & fwd.notna()]
            if len(sub_fwd) >= 5:
                wr = float((sub_fwd > 0).mean())
                d3_breakdown[d3v] = {
                    "n": int(len(sub_fwd)),
                    "mean": round(float(sub_fwd.mean()), 6),
                    "wr": round(wr, 4),
                    "tag": "FAVORABLE" if wr > 0.55 else "UNFAVORABLE" if wr < 0.45 else "NEUTRAL",
                }
                d3_fwd_pools[d3v] = sub_fwd.values

        # Bootstrap CI for best-vs-worst D3 spread
        d3_ci = None
        if len(d3_fwd_pools) >= 2:
            best_k = max(d3_fwd_pools, key=lambda k: np.nanmean(d3_fwd_pools[k]))
            worst_k = min(d3_fwd_pools, key=lambda k: np.nanmean(d3_fwd_pools[k]))
            b_arr, w_arr = d3_fwd_pools[best_k], d3_fwd_pools[worst_k]
            rng = np.random.default_rng(seed)
            diffs = [np.mean(rng.choice(b_arr, len(b_arr))) - np.mean(rng.choice(w_arr, len(w_arr))) for _ in range(n_iter)]
            ci_lo, ci_hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
            d3_ci = {"best": best_k, "worst": worst_k, "ci_lo": round(ci_lo, 6), "ci_hi": round(ci_hi, 6),
                     "significativo": ci_lo > 0}

        if d2_breakdown or d3_breakdown:
            desglose[station] = {
                "d1_dominante": dominant_d1,
                "d1_pct": round(float(dominant_pct * 100), 1),
                "n_d1": int(d1_mask.sum()),
                "d2_velocity": d2_breakdown,
                "d2_ci95": d2_ci,
                "d3_station_vol": d3_breakdown,
                "d3_ci95": d3_ci,
            }
    rep["desglose_d2d3"] = desglose if desglose else None

    # 4.9 Estabilidad por década
    rep["estabilidad_decada"] = {}
    for decada in ["1990", "2000", "2010", "2020"]:
        yr_start, yr_end = int(decada), int(decada) + 9
        mask_dec = señal & df["pivot_year"].between(yr_start, yr_end)
        dec_fwd = fwd[mask_dec & fwd.notna()]
        if len(dec_fwd) >= 3:
            rep["estabilidad_decada"][decada] = {
                "n": int(len(dec_fwd)),
                "mean": round(float(np.nanmean(dec_fwd)), 6),
                "wr": round(float((dec_fwd > 0).mean()), 4),
            }
        else:
            rep["estabilidad_decada"][decada] = {"n": int(len(dec_fwd)), "mean": None, "wr": None}

    # 4.10 Puntería por escala zigzag: capture ratio por zz25/zz50/zz75
    rep["punteria"] = {}
    for escala, col_cascade, objetivo in [("zz25", None, 0.025), ("zz50", "cascade_50", 0.05), ("zz75", "cascade_75", 0.075)]:
        if escala == "zz25":
            mask = señal & fwd.notna()
            lag = fwd[mask]
        else:
            mask = señal & (df[col_cascade] == 1) & fwd.notna()
            lag = fwd[mask]
        if len(lag) >= 5:
            rep["punteria"][escala] = {
                "n": int(len(lag)),
                "forward_mean": float(np.nanmean(lag)),
                "win_rate": float((lag > 0).mean()),
                "capture_ratio": float(np.nanmean(lag) / objetivo),
                "mae_medio": float(np.nanmean(_mae_intratrade(spy, mask, df))) if spy is not None else None,
            }

    # 4.11 Offset de entrada: capture ratio si entro ±1 barra del pivote
    if spy is not None:
        rep["offset_entrada"] = {}
        for offset in [-1, 0, 1]:
            off_mask = señal.values.copy()
            if offset != 0:
                off_mask = np.roll(off_mask, -offset)
            off_mask = pd.Series(off_mask, index=señal.index).astype(bool)
            off_fwd = fwd[off_mask & fwd.notna()]
            if len(off_fwd) >= 5:
                leg_mean = float(np.nanmean(np.abs(df.loc[señal, "prev_leg_return"])))
                rep["offset_entrada"][f"{offset:+d}"] = {
                    "n": int(len(off_fwd)),
                    "forward_mean": float(np.nanmean(off_fwd)),
                    "win_rate": float((off_fwd > 0).mean()),
                    "capture_ratio": float(np.nanmean(off_fwd) / leg_mean) if leg_mean > 0 else 0,
                }

    # 4.12 Lookback crash — señales activas en ventana [T0-3, T0+2]
    # Para cada pivote de caída (prev_leg_return < 0), buscar qué señales
    # estaban activas en la ventana diaria alrededor del pivote.
    import datetime as _dt
    crash_threshold = 0  # negativo = caída
    ventana_dias = 3  # [T0-3, T0+2]

    rep["lookback_crash"] = {}
    crash_pivots = señal & (df["prev_leg_return"] < crash_threshold)
    crash_idx = np.where(crash_pivots.values)[0]

    # Pre-compute all signal masks once (expensive to recompute per crash pivot)
    _all_sig_masks = {}
    for sig_name, sig_fn in SEÑALES.items():
        try:
            _all_sig_masks[sig_name] = sig_fn(df).astype(bool)
        except Exception:
            pass

    for escala, col_cascade, max_dur in [("zz25", None, 10), ("zz50", "cascade_50", 30), ("zz75", "cascade_75", 60)]:
        if len(crash_idx) == 0:
            continue

        # Filter crash pivots by zigzag scale
        if col_cascade is not None and col_cascade in df.columns:
            # For zz50/zz75: only crashes that reached the cascade threshold
            escala_mask = crash_pivots & df[col_cascade].notna() & (df[col_cascade] == True)
            escala_idx = np.where(escala_mask.values)[0]
        else:
            escala_idx = crash_idx

        if len(escala_idx) == 0:
            continue

        # Señales activas en la ventana [T0-ventana_dias, T0+2]
        activas_en_ventana = {sig: 0 for sig in _all_sig_masks}
        total_crashes_escala = 0

        for i in escala_idx:
            t0 = df["pivot_date"].iloc[i]
            t_min = t0 - _dt.timedelta(days=ventana_dias)
            t_max = t0 + _dt.timedelta(days=2)

            # Pivotes dentro de la ventana
            ventana = (df["pivot_date"] >= t_min) & (df["pivot_date"] <= t_max)
            if ventana.sum() == 0:
                continue

            total_crashes_escala += 1

            # Para cada señal, ¿estaba activa en algún pivote de la ventana?
            for sig_name, sig_serie in _all_sig_masks.items():
                if sig_serie[ventana].any():
                    activas_en_ventana[sig_name] += 1

        if total_crashes_escala > 0:
            rep["lookback_crash"][escala] = {
                "n_crashes": total_crashes_escala,
                "ventana_dias": ventana_dias,
                "señales": {},
            }
            for sig_name, n_activas in sorted(activas_en_ventana.items(), key=lambda x: -x[1]):
                if n_activas >= 3:  # mínimo 3 para reportar
                    pct = n_activas / total_crashes_escala * 100
                    rep["lookback_crash"][escala]["señales"][sig_name] = {
                        "n_crashes_con_senal": n_activas,
                        "pct_crashes": round(pct, 1),
                    }

    # 4.13 correlación Spearman señal-vs-forward
    rep["spearman"] = None

    # 4.14 ADDENDUM 1 — Structural Momentum (HH/HL/LH/LL)
    rep["structural_momentum"] = _structural_momentum_filter(señal, df, spy=spy)

    # 4.15 ADDENDUM 2 — Prev Leg Domino (post-crash context)
    rep["prev_leg_context"] = _prev_leg_context(señal, fwd, df)

    # 4.16 ADDENDUM 3 — Temporal Divergence Regime
    rep["divergence_regime"] = _divergence_regime(rep)

    # 4.17 ADDENDUM 9 — LIFT vs baseline condicionado por pivot_type (Enmienda 20-Ago-2026)
    rep["lift_vs_baseline"] = _lift_vs_baseline(señal, fwd, df)

    return rep


def medir_cross_overlap(df, forward_col="next_leg", n_iter=3000, seed=42):
    """Mide edge de la intersección de cada par de señales registradas."""
    if forward_col == "next_leg":
        fwd = df["prev_leg_return"].shift(-1)
    else:
        fwd = df[forward_col]

    sig_masks = {name: fn(df).astype(bool) for name, fn in SEÑALES.items()}
    sig_names = sorted(sig_masks.keys())
    overlaps = []

    for i in range(len(sig_names)):
        for j in range(i + 1, len(sig_names)):
            s1, s2 = sig_names[i], sig_names[j]
            m1, m2 = sig_masks[s1], sig_masks[s2]
            both = m1 & m2
            n_both = int(both.sum())
            if n_both < 5:
                continue

            fwd_only1 = fwd[m1 & ~m2 & fwd.notna()]
            fwd_only2 = fwd[~m1 & m2 & fwd.notna()]
            fwd_both = fwd[both & fwd.notna()]

            if len(fwd_both) < 3:
                continue

            mean_1 = float(np.nanmean(fwd_only1)) if len(fwd_only1) else None
            mean_2 = float(np.nanmean(fwd_only2)) if len(fwd_only2) else None
            mean_both = float(np.nanmean(fwd_both))
            max_solo = max(mean_1 or 0, mean_2 or 0)

            if mean_both > max_solo + 0.002:
                tag = "ADITIVA"
            elif mean_both < min(mean_1 or 0, mean_2 or 0) - 0.002:
                tag = "CANCELATORIA"
            else:
                tag = "REDUNDANTE"

            overlaps.append({
                "par": f"{s1} × {s2}",
                "n_overlap": n_both,
                "pct_overlap": round(100 * n_both / min(m1.sum(), m2.sum()), 1),
                "solo_a": {"n": int(len(fwd_only1)), "mean": round(mean_1, 6) if mean_1 is not None else None, "wr": round(float((fwd_only1 > 0).mean()), 4) if len(fwd_only1) else None},
                "solo_b": {"n": int(len(fwd_only2)), "mean": round(mean_2, 6) if mean_2 is not None else None, "wr": round(float((fwd_only2 > 0).mean()), 4) if len(fwd_only2) else None},
                "ambas": {"n": int(len(fwd_both)), "mean": round(mean_both, 6), "wr": round(float((fwd_both > 0).mean()), 4)},
                "tag": tag,
            })

    return overlaps


# ─────────────────────────────────────────────────────────────────────────────
# 8. CLI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Arnés de medición estándar Botero Trade")
    ap.add_argument("--señal", required=True, help="Nombre de la señal registrada")
    ap.add_argument("--forward", default="next_leg", help="Columna de retorno forward")
    ap.add_argument("--bootstrap", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None, help="Ruta del JSON de salida")
    ap.add_argument("--cross-overlap", action="store_true", help="Incluir análisis de cross-signal overlap")
    args = ap.parse_args()

    df, spy = cargar_datos()
    rep = medir(args.señal, df, args.forward, spy=spy, n_iter=args.bootstrap, seed=args.seed)
    rep["meta"] = {"seed": args.seed, "bootstrap": args.bootstrap,
                   "determinista": True, "sin_agentes": True}

    if args.cross_overlap:
        rep["cross_overlap"] = medir_cross_overlap(df, args.forward, args.bootstrap, args.seed)

    out_path = args.out or str(SCRATCH / f"medicion_{args.señal}.json")
    with open(out_path, "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False, default=str)

    # resumen humano a stdout
    a = rep["activa"]["dist"]
    b_type = rep.get("baseline_pivot_type", "ALL")
    print(f"SEÑAL: {args.señal}  (forward={args.forward})")
    if a.get("n", 0) == 0:
        # PROTOCOLO DIAMANTES: N=0 no crashea el reporte; se documenta como diamante.
        print("  Activa: N=0 → DIAMANTE ANECDOTAL (sin activaciones en la muestra)")
        print("  ⚠️  Sin activaciones: analizar el contexto del evento individualmente.")
        return
    print(f"  Activa: N={a['n']}  mean={a['mean']:+.4f}  med={a['median']:+.4f}")
    print(f"  P5/P95: {a['p5']:+.4f} / {a['p95']:+.4f}")
    print(f"  Win rate: {rep['activa']['wl'].get('win_rate', 0):.1%}")
    print(f"  CI95 media: {rep['activa']['ci_mean']['ci_lo']:+.4f} .. {rep['activa']['ci_mean']['ci_hi']:+.4f}")
    print(f"  Δ vs baseline ({b_type}): {rep.get('delta_media', 0):+.4f}")

    if "lift_vs_baseline" in rep and rep["lift_vs_baseline"]:
        for pt, l_info in rep["lift_vs_baseline"].items():
            print(f"  LIFT ({pt}): {l_info['lift']:.3f}x  (P(cae|señal)={l_info['pct_cae_activa']:.1f}% vs baseline={l_info['pct_cae_no_activa']:.1f}%, N={l_info['n_activa']})")

    if "triada" in rep and rep["triada"]:
        tr = rep["triada"]
        c50 = tr["cascade_50"]
        c75 = tr["cascade_75"]
        dur = tr["duracion_bars"]
        print(f"  Tríada ZigZag: zz25 mean={tr['zz25']['mean']:+.4f} (WR={tr['zz25']['win_rate']:.1%})")
        print(f"  Cascade reach: zz50={c50['rate_activa']:.1%} (Δ={c50['delta']:+.1%}) | zz75={c75['rate_activa']:.1%} (Δ={c75['delta']:+.1%})")
        print(f"  Duración pierna: {dur['mean']:.1f} bars (med={dur['median']:.1f}, base={dur['baseline_mean']:.1f})")

    if "anticipacion_zigzag" in rep and rep["anticipacion_zigzag"]:
        az = rep["anticipacion_zigzag"]
        print(f"  Anticipación temporal: media={az['mean_dias']:.1f} días  mediana={az['median_dias']:.1f} días  ({az['pct_anticipados']}% con anticipación > 0)")
        print(f"  Percentiles: P5={az['p5_dias']:.0f}  P25={az['p25_dias']:.0f}  P75={az['p75_dias']:.0f}  P95={az['p95_dias']:.0f}  (N={az['n_total']})")
    if "drawdown_anticipacion" in rep and rep["drawdown_anticipacion"]:
        et = rep["drawdown_anticipacion"].get("entrada_temprana", {})
        st = rep["drawdown_anticipacion"].get("salida_tardia", {})
        if et.get("forward_mean") is not None:
            print(f"  Entrada temprana: forward={et['forward_mean']:+.4f}  MAE={et.get('mae_medio',0):+.4f}  (N={et['n']})")
        if st.get("forward_mean") is not None:
            print(f"  Salida tardía:    forward={st['forward_mean']:+.4f}  MAE={st.get('mae_medio',0):+.4f}  (N={st['n']})")
    if "capture_ratio" in rep and rep["capture_ratio"]:
        cr = rep["capture_ratio"]
        print(f"  Capture ratio: {cr['ratio']:.2f} (fwd {cr['fwd_mean']:+.4f} / |leg| {cr['abs_leg_mean']:.4f})")
        for pt_name, pt_data in cr.get("por_pivot_type", {}).items():
            print(f"    {pt_name}: ratio={pt_data['ratio']:.2f} (fwd={pt_data['fwd_mean']:+.4f}, |leg|={pt_data['abs_leg_mean']:.4f}, N={pt_data['n']})")
    if "punteria" in rep and rep["punteria"]:
        for esc, p in sorted(rep["punteria"].items()):
            print(f"  Puntería {esc}: capture={p['capture_ratio']:.2f}  WR={p['win_rate']:.1%}  MAE={p.get('mae_medio',0):+.4f}  (N={p['n']})")
    if "offset_entrada" in rep and rep["offset_entrada"]:
        for off, v in sorted(rep["offset_entrada"].items()):
            print(f"  Offset {off}: capture={v['capture_ratio']:.2f}  forward={v['forward_mean']:+.4f}  WR={v['win_rate']:.1%}  (N={v['n']})")

    # Lookback crash
    if "lookback_crash" in rep and rep["lookback_crash"]:
        print(f"  Lookback crash [T0-3, T0+2] — señales que anteceden a caídas:")
        for esc, lc in sorted(rep["lookback_crash"].items()):
            print(f"    {esc} (N={lc['n_crashes']}):")
            top = sorted(lc["señales"].items(), key=lambda x: -x[1]["pct_crashes"])[:5]
            for sig_name, info in top:
                print(f"      {sig_name:25s}  {info['pct_crashes']:5.1f}% de caídas")

    # Duración desglose
    if "duracion_desglose" in rep and rep["duracion_desglose"]:
        dd = rep["duracion_desglose"]
        c = dd["cortas"]
        l = dd["largas"]
        if c.get("fwd_mean") is not None and l.get("fwd_mean") is not None:
            print(f"  Duración desglose (med={dd['mediana_bars']:.0f}b): cortas={c['fwd_mean']:+.4f} WR={c['wr']:.0%} N={c['n']} | largas={l['fwd_mean']:+.4f} WR={l['wr']:.0%} N={l['n']} | Δ={dd['delta']:+.4f}")

    # D2×D3 desglose compacto con CI95
    if "desglose_d2d3" in rep and rep["desglose_d2d3"]:
        for station, info in rep["desglose_d2d3"].items():
            d2 = info["d2_velocity"]
            d3 = info["d3_station_vol"]
            d2_ci = info.get("d2_ci95")
            d3_ci = info.get("d3_ci95")
            if d2:
                best_d2 = max(d2.items(), key=lambda x: x[1]["mean"])
                worst_d2 = min(d2.items(), key=lambda x: x[1]["mean"])
                ci_tag = ""
                if d2_ci:
                    ci_tag = f" CI95=[{d2_ci['ci_lo']:+.4f},{d2_ci['ci_hi']:+.4f}] {'✅' if d2_ci['significativo'] else '❌'}"
                print(f"  D2 {station} [{info['d1_dominante']}]: best={best_d2[0]} ({best_d2[1]['mean']:+.4f} WR={best_d2[1]['wr']:.0%} N={best_d2[1]['n']}) | worst={worst_d2[0]} ({worst_d2[1]['mean']:+.4f} WR={worst_d2[1]['wr']:.0%} N={worst_d2[1]['n']}){ci_tag}")
            if d3:
                best_d3 = max(d3.items(), key=lambda x: x[1]["mean"])
                worst_d3 = min(d3.items(), key=lambda x: x[1]["mean"])
                ci_tag = ""
                if d3_ci:
                    ci_tag = f" CI95=[{d3_ci['ci_lo']:+.4f},{d3_ci['ci_hi']:+.4f}] {'✅' if d3_ci['significativo'] else '❌'}"
                print(f"  D3 {station} [{info['d1_dominante']}]: best={best_d3[0]} ({best_d3[1]['mean']:+.4f} WR={best_d3[1]['wr']:.0%} N={best_d3[1]['n']}) | worst={worst_d3[0]} ({worst_d3[1]['mean']:+.4f} WR={worst_d3[1]['wr']:.0%} N={worst_d3[1]['n']}){ci_tag}")

    # Estabilidad por década
    if "estabilidad_decada" in rep and rep["estabilidad_decada"]:
        parts = []
        for dec, vals in sorted(rep["estabilidad_decada"].items()):
            if vals.get("mean") is not None:
                parts.append(f"{dec}s={vals['mean']:+.4f} WR={vals['wr']:.0%} N={vals['n']}")
        if parts:
            print(f"  Estabilidad: {' | '.join(parts)}")

    if "costo_tarde" in rep and rep["costo_tarde"].get("costo_medio") is not None:
        print(f"  Costo retraso k=1d: {rep['costo_tarde']['costo_medio']:+.4f} (N={rep['costo_tarde']['n']})")
    if "timing_temprano" in rep and "estadistica" in rep["timing_temprano"]:
        tt = rep["timing_temprano"]["estadistica"]
        print(f"  MAE intra-trade medio: {tt.get('mean', 0):+.4f} (med: {tt.get('median', 0):+.4f}, P5: {tt.get('p5', 0):+.4f})")

    # Cross-signal overlap
    if "cross_overlap" in rep and rep["cross_overlap"]:
        print(f"\n  CROSS-SIGNAL OVERLAP ({len(rep['cross_overlap'])} pares con N≥5):")
        for ov in sorted(rep["cross_overlap"], key=lambda x: x["ambas"]["mean"], reverse=True):
            a_info = ov["solo_a"]
            b_info = ov["solo_b"]
            both = ov["ambas"]
            tag_icon = "+" if ov["tag"] == "ADITIVA" else "−" if ov["tag"] == "CANCELATORIA" else "="
            print(f"    [{tag_icon}] {ov['par']:45s} N={both['n']:3d} ({ov['pct_overlap']:.0f}%) | ambas={both['mean']:+.4f} WR={both['wr']:.0%} | solo_a={(a_info['mean'] or 0):+.4f} solo_b={(b_info['mean'] or 0):+.4f} | {ov['tag']}")

    print(f"  Reporte: {out_path}")


if __name__ == "__main__":
    main()

