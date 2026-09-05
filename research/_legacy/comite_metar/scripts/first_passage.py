"""
first_passage.py — metrología first-passage OHLC hacia adelante (Opción C).

Dado el disparo de una señal en t, computa el viaje forward del SPY hacia la
barrera ±scale / blanco (MIN|MAX), respetando el `blanco` de la señal y la
metrología Opción C (sin time-stop fijo salvo max_horizon explícito).

Semántica de barrera intrabar OHLC (Opción C):
    - touch_up : la vela s>t con high >= upper  (+scale)
    - touch_dn : la vela s>t con low  <= lower  (-scale)
    - first-passage = la primera vela que toca SU barrera objetiva. La barrera
      se evalúa sobre HIGH (↑) y LOW (↓) INTRIBAR, no sobre cierre.

Sin lookahead en la decisión: este módulo se invoca DESDE el disparo ya fijado
en t; solo mide el resultado forward. Nunca retroalimenta nada a `t`. El
disparo/estado del agente en t usa SOLO datos <= t (ver estado_en).

Escala:
    - scale_abs    : barrera absoluta (±).
    - scale_units  : barrera = ± scale_units * ATR(span) con datos estrictamente
                     <= t (sin lookahead en la calibración).
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from . import common


def atr_pre(df: pd.DataFrame, pos: int, span: int = 14) -> Optional[float]:
    """ATR simple, ventana con filas estrictamente <= pos. None si insuficiente."""
    if pos < 1:
        return None
    lo = max(pos - span + 1, 0)
    seg = df.iloc[lo:pos + 1]                       # Solo filas <= pos (no lookahead)
    if len(seg) < 2:
        return None
    high, low, close = seg["spy_high"], seg["spy_low"], seg["spy_close"]
    tr = pd.concat([high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    tr = tr.dropna()
    if tr.empty:
        return None
    return float(tr.tail(min(span, len(tr))).mean())


def first_passage(df: pd.DataFrame, t: int, *,
                  blanco: str = "MIN",
                  scale_abs: Optional[float] = None,
                  scale_units: Optional[float] = None,
                  max_horizon: Optional[int] = None,
                  atr_span: int = 14) -> Dict:
    """
    Computa el primer-passage del SPY desde la fila t hacia adelante.

    Parámetros
    ----------
    df          : lake continuo (columns spy_open/spy_high/spy_low/spy_close).
    t           : posición del disparo (0 <= t <= len-1).
    blanco      : 'MIN' (baja hacia -scale) o 'MAX' (sube hacia +scale).
    scale_abs   : barrera absoluta ±scale_abs.
    scale_units : si se pasa (y no scale_abs), barrera = ±scale_units * ATR(span)
                  calculado con datos <= t.
    max_horizon : barreras temporales (barras); None = sin time-stop (Opción C).
    atr_span    : ventana ATR previa (default 14).
    """
    n = len(df)
    if not (0 <= t <= n - 1):
        raise IndexError(f"first_passage t={t} fuera de [0,{n-1}]")

    if scale_abs is not None:
        scale = abs(float(scale_abs))
    elif scale_units is not None:
        atr = atr_pre(df, t, atr_span)
        if atr is None or atr <= 0:
            return {"ok": False, "motivo": f"ATR({atr_span}) no disponible en t"}
        scale = scale_units * atr
    else:
        raise ValueError("first_passage requiere scale_abs o scale_units")

    base_close = float(df.iloc[t]["spy_close"])
    upper = base_close + scale
    lower = base_close - scale
    horizon = max_horizon if max_horizon is not None else (n - 1 - t)
    if horizon < 1:
        return {"ok": False, "motivo": "sin barras forward (t en el final)"}

    end = min(t + horizon, n - 1)
    # Solo filas > t: forward real (nunca incluye t ni anteriores para el viaje)
    seg = df.iloc[t + 1: end + 1]
    if seg.empty:
        return {"ok": False, "motivo": "sin barras forward"}

    stop_position = len(df) + 1  # centinela: no alcanzada
    hit_type: Optional[str] = None
    mfe = None
    mae = None

    for local, (fecha, row) in enumerate(seg.iterrows()):
        pos_abs = t + 1 + local                     # posición absoluta por posición
        if pos_abs >= n:                            # defensa off-by-one
            break
        high = float(row["spy_high"])
        low = float(row["spy_low"])
        touch_up = high >= upper
        touch_dn = low <= lower

        # primera vela que cumple el objetivo del blanco; OHLC intrabar
        if blanco == "MAX" and touch_up:
            hit_type, stop_position = "touch_up", pos_abs
            break
        if blanco == "MIN" and touch_dn:
            hit_type, stop_position = "touch_dn", pos_abs
            break
        # (blanco no objetivo tocado antes se ignora: espera al objetivo,
        #  salvo que se quiera medir 'toucher cualquiera' — ver nota)
        mfe = max(mfe, high) if mfe is not None else high
        mae = min(mae, low) if mae is not None else low

    alcanzada = hit_type is not None
    return {
        "ok": True,
        "t": t,
        "fecha_disparo": str(df.index[t]),
        "base_close": base_close,
        "scale": scale,
        "upper": round(upper, 6),
        "lower": round(lower, 6),
        "blanco": blanco,
        "alcanzada": alcanzada,
        "primer_toque": hit_type,
        "primer_toque_pos": stop_position if alcanzada else None,
        "primer_toque_fecha": str(df.index[stop_position]) if alcanzada else None,
        "barras_hasta_toque": (stop_position - t) if alcanzada else None,
        "segmento_leido": f"{t+1}..{end}",
        "mfe_high": mfe,
        "mae_low": mae,
        "horizonte_barras": horizon,
        "sin_time_stop": max_horizon is None,
    }


def desempate_intrabar(current: Dict, blanco: str) -> str:
    """Resolución documentada si una misma vela toca ambos lados: manda el blanco."""
    return "touch_up" if blanco == "MAX" else "touch_dn"


if __name__ == "__main__":
    df = common.cargar_lake()
    print("lake:", df.shape)
    for t in (2000, 3000, 4000):
        r = first_passage(df, t, blanco="MIN", scale_units=1.5, atr_span=14, max_horizon=80)
        if r["ok"]:
            print(f"t={t} fecha={r['fecha_disparo']} alcanzada={r['alcanzada']} "
                  f"tipo={r['primer_toque']} barras={r['barras_hasta_toque']} "
                  f"scale={r['scale']:.3f}")
        else:
            print(f"t={t} NO_OK {r['motivo']}")