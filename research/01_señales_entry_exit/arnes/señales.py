"""Definiciones de las 28 señales entry/exit (dominio). Cada una observable en tiempo real salvo las marcadas con filtro pivot_type (sesgo de posición documentado).

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import pandas as pd  # noqa: F401

from .registro import _registrar  # noqa: F401
from .estructura import _surprise_vector  # usada por sorpresa_total

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
    validacion="DEGRADADA post-QE (structural break 22-Ago: hit 59% PRE-2009 → 15% POST en su mejor celda; p agregado 0.006 arrastrado por la era 2000s; semivida/D3 apunta a que solo funciona en shocks ordinarios, no en cambios de régimen)", n_min=None, dsr=None,
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
    validacion="PROPOSED — calibrada 23-Ago pero SIN edge significativo (mejor p=0.25)",
    n_min=None, dsr=None,
    fuente="analisis_señales_exit.md + calibración 23-Ago (calibracion_cascade_reversal.json)")
def _cascade_reversal(df):
    """cascade_conviction_50 cae por debajo de −0.957 — colapso de convicción (EXIT).

    CALIBRACIÓN 23-Ago-2026 (auditoría profunda):
    - El umbral original 0.30 quedó DESCALIBRADO con la normalización de producción
      (μ/σ 0.41/0.3206): fire rate 75.8% = background puro.
    - Barrido de umbrales: tercil_bajo (−0.387) y cero (0.0) también son background
      (fire rate >25%). p25 (−0.747) y p20 (−0.867) quedan en el límite del umbral
      de background (20%).
    - Elegido p15 (−0.957): fire rate 15% (bajo el umbral de background), mejor
      edge zz25|ALZA +0.28% (hit 72.6%, PF 3.06) — pero p=0.25, NO significativo.
    - El cuantil se CONGELA como constante (un cuantil recalculado por ejecución
      sería look-ahead; una señal real necesita un número fijo).
    - Estado: PROPUESTA con calibración honesta. Requiere validación OOS/walk-forward
      antes de promoción. El gradiente direccional es real (edge negativo en BAJA)
      pero sin potencia estadística todavía.
    """
    if "cascade_conviction_50" not in df.columns:
        return pd.Series(False, index=df.index)
    UMBRAL_CALIBRADO = -0.957  # cuantil p15 de c50 (calibración 23-Ago, congelado)
    mask = df["cascade_conviction_50"] < UMBRAL_CALIBRADO
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
    validacion="RE-RETIRADA (structural break 22-Ago: +6.99% PRE-2009 → −2.84% POST, p=0.0000 Fisher. Reliquia de era pre-QE. Rescate v6 invalidado)", n_min=None, dsr=None,
    fuente="EXIT: CREDIT sale de CREDIT_EASE/DEEP_CREDIT_EASE → fin de easing")
def _credit_ease_exit(df):
    """[RE-RETIRADA 22-Ago-2026: rescate v6 invalidado por structural break — el edge
    +1.54% (p=0.0013) era enteramente pre-2009 (+6.99%); post-quiebre −2.84% (p=0.0000
    Fisher). Es una reliquia de la era pre-QE: cuando el crédito salía del easing,
    las acciones subían; en la era QE esa relación desapareció.]
    CREDIT NO está en CREDIT_EASE ni DEEP_CREDIT_EASE — fin del easing."""
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    mask = ~credit_d1.isin(["CREDIT_EASE", "DEEP_CREDIT_EASE"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("breadth_contraction_exit",
    validacion="DEGRADADA — structural break interno OOS (auditoría Opus 22-Ago): primeros 5 folds (2001-2016) media −1.48% anti-edge; últimos 5 folds (2016-2026) media +1.81%. El +0.17% agregado enmascara el quiebre. Rescate v6 invalidado para producción hasta identificar la causa del cambio", n_min=None, dsr=None,
    fuente="EXIT: BSI sale de EXPANSIVE → fin de expansión")
def _breadth_contraction_exit(df):
    """[DEGRADADA 22-Ago-2026 por auditoría Opus: structural break interno en los folds
    OOS (anti-edge −1.48% pre-2016, edge +1.81% post-2016). El p agregado 0.0008 era
    real pero mezcla dos regímenes opuestos. No usar en producción hasta identificar
    la causa del cambio post-2016.]
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
