"""Definiciones de las 28+ señales entry/exit (dominio). Cada una observable en tiempo real salvo las marcadas con filtro pivot_type (sesgo de posición documentado).

Extraído del God file medir_senal.py (refactor 22-Ago-2026, homologado canónico 30-Ago-2026).
Matemática pura, determinista, basada en vectores numéricos de estado D1__D2__D3.
"""
import numpy as np
import pandas as pd

from .registro import _registrar
from .estructura import _surprise_vector  # usada por sorpresa_total


def _get_dim(df: pd.DataFrame, station: str, dim: int = 0) -> pd.Series:
    """Extrae la dimensión numérica (0=D1, 1=D2, 2=D3) del state_key {station}_sk."""
    sk_col = f"{station}_sk"
    if sk_col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    parts = df[sk_col].dropna().astype(str).str.split("__", expand=True)
    if parts.empty or dim >= parts.shape[1]:
        return pd.Series(np.nan, index=df.index)
    s = pd.to_numeric(parts[dim], errors="coerce")
    return s.reindex(df.index)


# ─────────────────────────────────────────────────────────────────────────────
# 1. SEÑALES DE ENTRY (validadas)
# ─────────────────────────────────────────────────────────────────────────────

@_registrar("credit_easing_k1",
    validacion="VALIDATED (Grade A)", n_min=112, dsr=None,
    fuente="credit_easing_pisos.py (17-Ago)",
    tipo="entry", pivot_type="MIN",
    descripcion="Crédito mejorando en piso de drawdown. Señal contrarian de compra: el estrés crediticio cede mientras el precio toca fondo.")
def _credit_easing(df):
    """CREDIT easing en ventana K=1, EN UN PISO DE DRAWDOWN (pivot_type == MIN).
    (Hallazgo validado: EASING en piso → +5.19% 93.75%WR vs SIN → +2.99%.)"""
    es_min = (df["pivot_type"] == "MIN").values
    d = df["credit_val"]
    easing = (d > d.shift(1)).values
    return pd.Series(es_min & easing, index=df.index)


@_registrar("sorpresa_total",
    validacion="SPECULATIVE", n_min=525, dsr=None,
    fuente="distortion_surprise_adelantada.py (17-Ago), ρ≤0.15",
    tipo="entry", pivot_type="BOTH",
    descripcion="Sorpresa agregada de Shannon alta: el sistema METAR está en un estado estadísticamente improbable. Precursor de reversión.")
def _sorpresa_total(df):
    """Sorpresa agregada de Shannon (alta = sistema en estado improbable).
    Computada desde los fact stores vía state_key. Umbral = tercil alto."""
    surprise = _surprise_vector(df)
    total = surprise.mean(axis=1, skipna=True)
    return total >= total.quantile(0.67)


@_registrar("panico_total",
    validacion="VALIDATED (Grade A)", n_min=30, dsr=0.9680,
    fuente="operational-spec: VIX+SKEW extremos, +6.81% 60d, 82% WR",
    tipo="entry", pivot_type="BOTH",
    descripcion="VIX y SKEW ambos en extremo bearish simultáneamente. Pánico institucional completo = oportunidad contrarian de compra.")
def _panico_total(df):
    """PÁNICO TOTAL: VIX y SKEW ambos en D1 extremo (bearish).
    VIX en PANIC / EXTREME_PANIC (>= 4) Y SKEW en PARANOIA / EXTREME_PARANOIA (>= 4)."""
    vix_d1 = _get_dim(df, "vix", 0)
    skew_d1 = _get_dim(df, "skew", 0)
    return (vix_d1 >= 4) & (skew_d1 >= 4)


@_registrar("capitulacion",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: VIX↑ + S5 colapsa, +1.5% 20d, PF 2.19",
    tipo="entry", pivot_type="BOTH",
    descripcion="VIX en crisis + breadth colapsado (washed out). Capitulación del mercado = punto de máximo pesimismo.")
def _capitulacion(df):
    """CAPITULACIÓN: VIX en NEUTRAL_ALERT/PANIC/EXTREME_PANIC (>= 3) Y BSI en BREADTH_WASHED_OUT (== 0)."""
    vix_d1 = _get_dim(df, "vix", 0)
    bsi_d1 = _get_dim(df, "bsi", 0)
    return (vix_d1 >= 3) & (bsi_d1 == 0)


@_registrar("sub_reaccion",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: VIX↑ + S5 mantiene, esperar",
    tipo="entry", pivot_type="BOTH",
    descripcion="VIX en extremo pero breadth NO colapsa. El mercado absorbe el shock sin capitular = fortaleza subyacente.")
def _sub_reaccion(df):
    """SUB-REACCIÓN: VIX en extremo (>= 3) pero BSI NO en BREADTH_WASHED_OUT (!= 0)."""
    vix_d1 = _get_dim(df, "vix", 0)
    bsi_d1 = _get_dim(df, "bsi", 0)
    return (vix_d1 >= 3) & (bsi_d1.notna()) & (bsi_d1 != 0)


@_registrar("euforia",
    validacion="MODERATE", n_min=20, dsr=None,
    fuente="operational-spec: VIX↓ + S5 máximos, techo",
    tipo="exit", pivot_type="BOTH",
    descripcion="VIX en complacencia extrema + breadth no estresado. Euforia de mercado = señal de techo. WR bear 85.4%.")
def _euforia(df):
    """EUFORIA: VIX en complacencia (<= 1) y BSI no en lavado (!= 0)."""
    vix_d1 = _get_dim(df, "vix", 0)
    bsi_d1 = _get_dim(df, "bsi", 0)
    return (vix_d1 <= 1) & (bsi_d1.notna()) & (bsi_d1 != 0)


@_registrar("vvix_entry",
    validacion="VALIDATED (Grade A)", n_min=30, dsr=None,
    fuente="operational-spec: EXTREME_VVIX, +2.69% 20d, Kelly 61%",
    tipo="entry", pivot_type="BOTH",
    descripcion="VVIX en extremo: la volatilidad de la volatilidad dispara = inestabilidad máxima. Contrarian de compra.")
def _vvix_entry(df):
    """VVIX en EXTREME_INSTABILITY (== 5)."""
    return _get_dim(df, "vvix", 0) == 5


@_registrar("bsi_washed_out",
    validacion="VALIDATED (Grade A)", n_min=58, dsr=None,
    fuente="operational-spec: BREADTH_WASHED_OUT, +2.6% 20d, WR 69%",
    tipo="entry", pivot_type="BOTH",
    descripcion="Breadth del S&P500 colapsado (washed out). Máxima destrucción de amplitud = oportunidad contrarian de compra.")
def _bsi_washed_out(df):
    """BSI en BREADTH_WASHED_OUT (== 0)."""
    return _get_dim(df, "bsi", 0) == 0


@_registrar("credit_stress",
    validacion="VALIDATED (Grade A)", n_min=82, dsr=0.9509,
    fuente="operational-spec: CREDIT_STRESS, +3.00% 20d, Kelly 50%",
    tipo="entry", pivot_type="BOTH",
    descripcion="Spread de crédito HYG/LQD en zona de estrés. El mercado de bonos señala miedo = oportunidad contrarian en equity.")
def _credit_stress(df):
    """CREDIT en estrés (EXTREME_STRESS=0, STRESS=1, es decir <= 1)."""
    credit_d1 = _get_dim(df, "credit", 0)
    return (credit_d1.notna()) & (credit_d1 <= 1)


@_registrar("dxy_bearish",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: DOLLAR_SPIKE_CRISIS, −1.94% 20d, WR 28%",
    tipo="entry", pivot_type="BOTH",
    descripcion="Dólar en spike de crisis. Flight-to-safety extremo = correlación inversa con equity. Contexto macro adverso.")
def _dxy_bearish(df):
    """DXY en EXTREME_STRENGTH (== 5)."""
    return _get_dim(df, "dxy", 0) == 5


@_registrar("pcr_put_panic",
    validacion="VALIDATED (Grade A)", n_min=20, dsr=None,
    fuente="operational-spec: EXTREME_PUT_PANIC, +2.26% 20d, WR 79%",
    tipo="entry", pivot_type="BOTH",
    descripcion="Put/Call ratio en pánico extremo. Exceso de compra de puts = miedo institucional máximo. Contrarian de compra.")
def _pcr_put_panic(df):
    """PCR en EXTREME_PUT_PANIC (== 5)."""
    return _get_dim(df, "pcr", 0) == 5


@_registrar("fg_extreme_fear",
    validacion="VALIDATED", n_min=54, dsr=None,
    fuente="auditoria 17-Ago: EXTREME_FEAR=+1.58% WR=68.5% N=54",
    tipo="entry", pivot_type="BOTH",
    descripcion="Fear & Greed CNN en miedo extremo (<10). Sentimiento retail capitulado = oportunidad contrarian de compra.")
def _fg_extreme_fear(df):
    """FG en EXTREME_FEAR (== 0)."""
    return _get_dim(df, "fg", 0) == 0


@_registrar("fg_extreme_greed",
    validacion="VALIDATED", n_min=31, dsr=None,
    fuente="auditoria 17-Ago: EXTREME_GREED=-1.92% WR=19.4% N=31",
    tipo="exit", pivot_type="BOTH",
    descripcion="Fear & Greed CNN en codicia extrema (>90). Sentimiento retail eufórico = señal de techo. WR bear 80.6%.")
def _fg_extreme_greed(df):
    """FG en EXTREME_GREED (== 5)."""
    return _get_dim(df, "fg", 0) == 5


# ─────────────────────────────────────────────────────────────────────────────
# 2. SEÑALES DE EXIT
# ─────────────────────────────────────────────────────────────────────────────

@_registrar("bsi_recovery",
    validacion="DEGRADADA post-QE (structural break 22-Ago)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: BSI sale de BREADTH_WASHED_OUT",
    tipo="exit", pivot_type="BOTH",
    descripcion="Breadth sale de washed out hacia recuperación. Señal de salida del pánico. DEGRADADA: solo funcionaba pre-QE.")
def _bsi_recovery(df):
    """BSI sale de BREADTH_WASHED_OUT → NEUTRAL_HIGH_BREADTH (3) o EXPANSIVE_BREADTH (4)."""
    return _get_dim(df, "bsi", 0).isin([3, 4])


@_registrar("vix_crisis_spike",
    validacion="RECLASIFICADA ENTRY (20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: VIX entra en CRISIS_SPIKE. Edge +0.75% positivo → reclasificada como ENTRY (comprar miedo).",
    tipo="entry", pivot_type="BOTH",
    descripcion="VIX dispara a crisis spike. A pesar del nombre, el edge es POSITIVO: comprar el pánico de volatilidad es contrarian rentable.")
def _vix_crisis_spike(df):
    """[RECLASIFICADA ENTRY 20-Ago-2026] VIX entra en EXTREME_PANIC (== 5)."""
    return _get_dim(df, "vix", 0) == 5


@_registrar("cascade_reversal",
    validacion="PROPOSED — calibrada 23-Ago pero SIN edge significativo (mejor p=0.25)",
    n_min=None, dsr=None,
    tipo="exit", pivot_type="BOTH",
    descripcion="Convicción cascade cae por debajo del p15. Colapso de momentum = posible reversión. Sin significancia estadística aún.",
    fuente="analisis_señales_exit.md + calibración 23-Ago (calibracion_cascade_reversal.json)")
def _cascade_reversal(df):
    """cascade_conviction_50 cae por debajo de −0.957 — colapso de convicción (EXIT)."""
    if "cascade_conviction_50" not in df.columns:
        return pd.Series(False, index=df.index)
    UMBRAL_CALIBRADO = -0.957
    mask = df["cascade_conviction_50"] < UMBRAL_CALIBRADO
    return mask.fillna(False)


@_registrar("credit_stress_exit",
    validacion="RETIRADA (duplicado exacto de credit_stress — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: CREDIT entra en CREDIT_STRESS. RETIRADA: código idéntico a credit_stress (N=215, edge=+1.00%).",
    tipo="exit", pivot_type="BOTH",
    descripcion="RETIRADA: duplicado exacto de credit_stress. Usar credit_stress en su lugar.")
def _credit_stress_exit(df):
    """[RETIRADA 20-Ago-2026] Duplicado exacto de credit_stress (<= 1)."""
    credit_d1 = _get_dim(df, "credit", 0)
    return (credit_d1.notna()) & (credit_d1 <= 1)


@_registrar("dxy_spike_exit",
    validacion="RETIRADA (duplicado exacto de dxy_bearish — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: DXY entra en DOLLAR_SPIKE_CRISIS. RETIRADA: código idéntico a dxy_bearish (N=35).",
    tipo="exit", pivot_type="BOTH",
    descripcion="RETIRADA: duplicado exacto de dxy_bearish. Usar dxy_bearish en su lugar.")
def _dxy_spike_exit(df):
    """[RETIRADA 20-Ago-2026] Duplicado exacto de dxy_bearish (== 5)."""
    return _get_dim(df, "dxy", 0) == 5


@_registrar("pcr_panic_exit",
    validacion="RETIRADA (duplicado exacto de pcr_put_panic — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: PCR entra en EXTREME_PUT_PANIC. RETIRADA: código idéntico a pcr_put_panic (N=70, edge=+2.70%).",
    tipo="exit", pivot_type="BOTH",
    descripcion="RETIRADA: duplicado exacto de pcr_put_panic. Usar pcr_put_panic en su lugar.")
def _pcr_panic_exit(df):
    """[RETIRADA 20-Ago-2026] Duplicado exacto de pcr_put_panic (== 5)."""
    return _get_dim(df, "pcr", 0) == 5


@_registrar("skew_paranoia_exit",
    validacion="RESCATADA (v6: +2.84% neto, p=0.091, N=16, INDEP=71% — método first-passage)", n_min=None, dsr=None,
    fuente="analisis_señales_exit.md: SKEW entra en BLACK_SWAN_PARANOIA. Rescatada por arquitecto 22-Ago tras re-evaluación v6.",
    tipo="entry", pivot_type="BOTH",
    descripcion="SKEW en paranoia de black swan. Institucionales comprando puts OTM masivamente = miedo extremo de cola. Diamante contrarian.")
def _skew_paranoia_exit(df):
    """[RESCATADA 22-Ago-2026] SKEW entra en EXTREME_PARANOIA (== 5)."""
    return _get_dim(df, "skew", 0) == 5


@_registrar("vix_complacency_exit",
    validacion="RETIRADA (duplicado 100% overlap con euforia — 20-Ago-2026 Opus PC3)", n_min=None, dsr=None,
    fuente="EXIT: VIX en DEEP_COMPLACENCY/LOW_VOL → fin de euforia",
    tipo="exit", pivot_type="BOTH",
    descripcion="RETIRADA: duplicado 100% de euforia. Usar euforia en su lugar.")
def _vix_complacency_exit(df):
    """[RETIRADA 20-Ago-2026] VIX en complacencia (<= 1)."""
    vix_d1 = _get_dim(df, "vix", 0)
    return (vix_d1.notna()) & (vix_d1 <= 1)


@_registrar("credit_ease_exit",
    validacion="RE-RETIRADA (structural break 22-Ago)", n_min=None, dsr=None,
    fuente="EXIT: CREDIT sale de CREDIT_EASE/DEEP_CREDIT_EASE → fin de easing",
    tipo="exit", pivot_type="BOTH",
    descripcion="RE-RETIRADA: crédito sale de easing. Reliquia pre-QE: el edge desapareció post-2009. No usar.")
def _credit_ease_exit(df):
    """[RE-RETIRADA 22-Ago-2026] CREDIT NO está en easing (< 4)."""
    credit_d1 = _get_dim(df, "credit", 0)
    return (credit_d1.notna()) & (credit_d1 < 4)


@_registrar("breadth_contraction_exit",
    validacion="DEGRADADA — structural break interno OOS (auditoría Opus 22-Ago)", n_min=None, dsr=None,
    fuente="EXIT: BSI sale de EXPANSIVE → fin de expansión",
    tipo="exit", pivot_type="BOTH",
    descripcion="DEGRADADA: breadth contrae desde expansivo. Structural break OOS: anti-edge pre-2016, edge post-2016. No usar hasta aclarar.")
def _breadth_contraction_exit(df):
    """[DEGRADADA 22-Ago-2026] BSI NO está en expansivo (< 4)."""
    bsi_d1 = _get_dim(df, "bsi", 0)
    return (bsi_d1.notna()) & (bsi_d1 < 4)


@_registrar("regime_change_exit",
    validacion="RETIRADA (lift<1.0 — 20-Ago-2026 Opus PC1)", n_min=None, dsr=None,
    fuente="EXIT: Cambio de régimen VERANO→INVIERNO (credit_stress + vix_high + bsi_low)",
    tipo="exit", pivot_type="BOTH",
    descripcion="RETIRADA: cambio de régimen verano→invierno. LIFT<1.0 = peor que no hacer nada. Anti-señal.")
def _regime_change_exit(df):
    """[RETIRADA 20-Ago-2026] Cambio de régimen: Invierno (credit <= 2 & vix >= 3 & bsi <= 2)."""
    credit_d1 = _get_dim(df, "credit", 0)
    vix_d1 = _get_dim(df, "vix", 0)
    bsi_d1 = _get_dim(df, "bsi", 0)
    return (credit_d1 <= 2) & (vix_d1 >= 3) & (bsi_d1 <= 2)


@_registrar("sv5t_silent_distribution",
    validacion="RESCATADA — DIAMANTE SUPREMO (§3.3: N=20, 100% WR en techos MAX, Fwd=-4.63%, PF=99.9, CI95=[83.2%, 100.0%])", n_min=20, dsr=None,
    fuente="EXIT: SV5T en silencio institucional (LOW_TURBULENCE + VOL_EXPANSION) en techo. Rescatada 28-Ago bajo Protocolo Diamante §3.3.",
    tipo="exit", pivot_type="MAX",
    descripcion="DIAMANTE SUPREMO: en techo, volumen institucional desaparece mientras volatilidad expande. Distribución silenciosa. 20/20 WR en techos.")
def _sv5t_silent_distribution(df):
    """[DIAMANTE SUPREMO RESCATADO 28-Ago-2026 bajo Protocolo §3.3]
    En techo MAX, volumen institucional desaparece (sv5t <= 1) y volatilidad expande (sv5t_d3 >= 3)."""
    is_max = df["pivot_type"] == "MAX"
    sv5t_d1 = _get_dim(df, "sv5_turbulence", 0)
    sv5t_d3 = _get_dim(df, "sv5_turbulence", 2)
    cond = (sv5t_d1 <= 1) & (sv5t_d3 >= 3)
    return is_max & cond


@_registrar("credit_equity_divergence",
    validacion="DEGRADADA GRADO C (LIFT≈1.0 — 20-Ago-2026)", n_min=None, dsr=None,
    fuente="EXIT: Techo MAX con spread de crédito acelerando al alza. LIFT(MAX)=1.035x ≈ baseline (82.9%→85.8%) — NO discrimina.",
    tipo="exit", pivot_type="MAX",
    descripcion="DEGRADADA: divergencia crédito-equity en techos. LIFT≈1.0 = no discrimina vs baseline. Solo monitorear con filtro HH.")
def _credit_equity_divergence(df):
    """[GRADO C 20-Ago-2026] En techo MAX, crédito se deteriora con velocidad positiva (D2 >= 3)."""
    is_max = df["pivot_type"] == "MAX"
    credit_d2 = _get_dim(df, "credit", 1)
    cond = credit_d2 >= 3
    return is_max & cond


@_registrar("stealth_tail_hedging",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: VIX complaciente pero SKEW en expansión de volatilidad/cobertura",
    tipo="exit", pivot_type="BOTH",
    descripcion="VIX complaciente pero SKEW en expansión: institucionales comprando cobertura de cola en silencio. Señal de distribución oculta.")
def _stealth_tail_hedging(df):
    """VIX en complacencia (<= 2) mientras SKEW muestra compras OTM (D3 >= 3)."""
    vix_d1 = _get_dim(df, "vix", 0)
    skew_d3 = _get_dim(df, "skew", 2)
    return (vix_d1 <= 2) & (skew_d3 >= 3)


@_registrar("defensive_rotation_divergence",
    validacion="RETIRADA (lift<1.0 — 20-Ago-2026 Opus PC1)", n_min=None, dsr=None,
    fuente="EXIT: Techo MAX con rotación de capital colapsando hacia defensivos (FAST_CRUSH_3D)",
    tipo="exit", pivot_type="MAX",
    descripcion="RETIRADA: en techo, rotación colapsa hacia defensivos. LIFT<1.0 = anti-señal, peor que baseline.")
def _defensive_rotation_divergence(df):
    """[RETIRADA 20-Ago-2026] En techo MAX, rotación sectorial cae agresivamente (D2 == 0 o D1 <= 1)."""
    is_max = df["pivot_type"] == "MAX"
    rot_d1 = _get_dim(df, "rotation", 0)
    rot_d2 = _get_dim(df, "rotation", 1)
    cond = (rot_d2 == 0) | (rot_d1 <= 1)
    return is_max & cond


# ─────────────────────────────────────────────────────────────────────────────
# 3. SEÑALES V2 VECTORIALES (Fase 7 V7)
# ─────────────────────────────────────────────────────────────────────────────

@_registrar("capitulacion_v2",
    validacion="V2_VECTORIAL (Fase 7 V7)", n_min=30, dsr=None,
    fuente="Plan V7: capitulacion + BSI D2 confirmatoria (FAST_CRUSH / DECEL_DOWN)",
    tipo="entry", pivot_type="BOTH",
    descripcion="Capitulación vectorial: VIX crisis + BSI washed + BSI decelerando (D2). La cinemática confirma el agotamiento vendedor.")
def _capitulacion_v2(df):
    """CAPITULACIÓN V2: VIX >= 3 + BSI D1 == 0 + BSI D2 en {0, 1}."""
    vix_d1 = _get_dim(df, "vix", 0)
    bsi_d1 = _get_dim(df, "bsi", 0)
    bsi_d2 = _get_dim(df, "bsi", 1)
    return (vix_d1 >= 3) & (bsi_d1 == 0) & (bsi_d2.isin([0, 1]))


@_registrar("euforia_v2",
    validacion="V2_VECTORIAL (Fase 7 V7)", n_min=30, dsr=None,
    fuente="Plan V7: BSI EXPANSIVE/HYPER + D2 ACCEL (sin filtro VIX — N=48, WR bear=81.2%, 92% MAX)",
    tipo="exit", pivot_type="BOTH",
    descripcion="Euforia vectorial: BSI en expansión/hiper con D2 acelerando al alza = techo cinemático inminente. 92% ocurre en techos MAX.")
def _euforia_v2(df):
    """EUFORIA V2: BSI D1 >= 4 + BSI D2 >= 3."""
    bsi_d1 = _get_dim(df, "bsi", 0)
    bsi_d2 = _get_dim(df, "bsi", 1)
    return (bsi_d1 >= 4) & (bsi_d2 >= 3)


@_registrar("vix_crisis_spike_v2",
    validacion="V2_VECTORIAL (Fase 7 V7)", n_min=30, dsr=None,
    fuente="Plan V7: VIX CRISIS + VIX D2 FAST_SPIKE (impulso de volatilidad confirmado por cinemática)",
    tipo="entry", pivot_type="BOTH",
    descripcion="VIX crisis con cinemática de spike confirmada. El D2 velocidad confirma que el VIX NO está estancado en crisis sino acelerando.")
def _vix_crisis_spike_v2(df):
    """VIX CRISIS V2: VIX D1 == 5 + VIX D2 >= 3."""
    vix_d1 = _get_dim(df, "vix", 0)
    vix_d2 = _get_dim(df, "vix", 1)
    return (vix_d1 == 5) & (vix_d2 >= 3)
