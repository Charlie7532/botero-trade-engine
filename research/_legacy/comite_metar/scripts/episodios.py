"""
episodios.py — generación determinista de episodios y puntos de decisión.

El comité NO interpreta cada vela: interpreta en puntos de decisión (pivotes)
donde el estado es "activable". Un episodio es una corrida contigua de
activaciones de estación. Principios:

  - Activación: una estación está "activa" en la vela t si NO es pre-inception
    y presenta un régimen notable: D1 extremo (bins {0,5}) o overflow tier>0
    (cualquier dimensión). Es puramente causal (estado_en lee solo <= t).
  - De-clustering dinámico: corridas consecutivas de activación se agrupan en
    UN episodio (credibilidad, no exclusión: no se corta el episodio ni se
    descartan velas; se marcan límites). Huecos <= `gap` barras se fusionan.
  - Punto de decisión primario t0 = primera vela del episodio (el agente lee
    el estado en t0 con los datos <= t0). `nucleo_pos` = vela con más
    estaciones activas dentro del episodio (el centro del evento).

Salida: comite_metar/salidas/episodios.json  +  comite_metar/salidas/mapa_activacion.json
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import common

# Parámetros de policy (deterministas y documentados)
GAP_BRIDGE = 2                 # max hueco (barras) fusionado al mismo episodio
MAX_RUN_BARS = 20              # longitud máxima de episodio (evita mega-episodios macro)
MIN_LEN = 1                    # longitud mínima de episodio
BINS_D1_EXTREMO = (0, 5)       # extremos ±2σ de D1 (magnitud)
BINS_D2D3_EXTREMO = (0, 4)     # extremos ±2σ de D2/D3 (velocidad/vol)
OVERFLOW_ACTIVO = 1            # tier >= 1 => estrictamente más allá de ±2σ

ESTACIONES_TACTICAS = ("vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew", "bsi", "rotation")
ESTACIONES_MACRO = ("yield_curve", "credit", "dxy")


def _obtener_inceptions() -> Dict[str, pd.Timestamp]:
    try:
        perfiles = common.cargar_perfiles()
        return {p["estacion"]: pd.Timestamp(p.get("inception", "1993-01-29")) for p in perfiles}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
def _tier(df: pd.DataFrame, pos: int, est: str, dim: str) -> int:
    try:
        v = df.iloc[pos][f"{est}_overflow_tier_{dim}"]
        return int(v) if v is not None else 0
    except (KeyError, TypeError, ValueError):
        return 0


def estacion_activa(df: pd.DataFrame, pos: int, est: str,
                    inceptions: Optional[Dict[str, pd.Timestamp]] = None) -> bool:
    """True si `est` está 'activa' en la vela pos (causal, sin lookahead y post-inception)."""
    if inceptions:
        inc = inceptions.get(est)
        if inc is not None and df.index[pos] < inc:
            return False
    try:
        d1 = int(df.iloc[pos][f"{est}_d1_bin"])
    except (KeyError, TypeError, ValueError):
        return False
    if d1 < 0:                                    # pre-inception / sin datos
        return False
    if d1 in BINS_D1_EXTREMO:
        return True
    return any(_tier(df, pos, est, dim) >= OVERFLOW_ACTIVO for dim in ("d1", "d2", "d3"))


def activas_en(df: pd.DataFrame, pos: int,
               estaciones: Optional[List[str]] = None) -> List[str]:
    estaciones = estaciones or common.ESTACIONES
    incs = _obtener_inceptions()
    return [e for e in estaciones if estacion_activa(df, pos, e, inceptions=incs)]


def marcas(df: pd.DataFrame, estaciones: Optional[List[str]] = None) -> Dict[int, List[str]]:
    """Vectorizado: pos -> [estaciones activas] respetando inceptions."""
    estaciones = estaciones or common.ESTACIONES
    incs = _obtener_inceptions()
    detalle: Dict[int, List[str]] = {}
    for e in estaciones:
        col = f"{e}_d1_bin"
        if col not in df.columns:
            continue
        a = df[col].fillna(-1).astype(int).values
        inc = incs.get(e, pd.Timestamp("1993-01-29"))
        valid_date = np.asarray(df.index >= inc)
        presente = (a >= 0) & valid_date
        if not presente.any():
            continue
        ext = presente & np.isin(a, list(BINS_D1_EXTREMO))
        ovf = np.zeros(len(df), dtype=bool)
        for dim in ("d1", "d2", "d3"):
            col_ovf = f"{e}_overflow_tier_{dim}"
            if col_ovf in df.columns:
                tiers = df[col_ovf].fillna(0).astype(int).values
                ovf = np.logical_or(ovf, tiers >= OVERFLOW_ACTIVO)
        act = np.logical_and(np.logical_or(ext, ovf), presente)
        for pos in np.where(act)[0]:
            detalle.setdefault(int(pos), []).append(e)
    return detalle


# ---------------------------------------------------------------------------
def _nucleo(df: pd.DataFrame, run: List[int], detalle: Dict[int, List[str]]) -> int:
    """Vela del episodio con más estaciones activas (desempate: más D1 extremo)."""
    best, best_n, best_x = run[0], -1, -1
    for pos in run:
        activos = detalle.get(pos, [])
        exts = sum(1 for e in activos
                   if int(df.iloc[pos][f"{e}_d1_bin"]) in BINS_D1_EXTREMO)
        key = (len(activos), exts)
        if key > (best_n, best_x):
            best, best_n, best_x = pos, len(activos), exts
    return best


def _empaquetar(df: pd.DataFrame, run: List[int], estaciones: List[str],
                detalle: Dict[int, List[str]]) -> Optional[Dict]:
    if not run:
        return None
    t0, t1 = run[0], run[-1]
    nucleo = _nucleo(df, run, detalle)
    activas_t0 = detalle.get(t0, [])
    return {
        "t0": t0,
        "fecha_inicio": str(df.index[t0]),
        "t1": t1,
        "fecha_t1": str(df.index[t1]),
        "longitud_barras": len(run),
        "n_activas_t0": len(activas_t0),
        "estaciones_activas_t0": activas_t0,
        "nucleo_pos": nucleo,
        "nucleo_fecha": str(df.index[nucleo]),
        "n_activas_nucleo": len(detalle.get(nucleo, [])),
    }


def ultima_fecha_completa(df: pd.DataFrame,
                          estaciones: Optional[List[str]] = None) -> "pd.Timestamp":
    """Última fila donde TODAS las estaciones tienen cobertura (no pre-inception)."""
    estaciones = estaciones or common.ESTACIONES
    mask_todo = None
    for e in estaciones:
        col = f"{e}_d1_bin"
        if col not in df.columns:
            continue
        presente = df[col].fillna(-1).astype(int).values >= 0
        mask_todo = presente if mask_todo is None else (mask_todo & presente)
    if mask_todo is None or not mask_todo.any():
        return df.index[0]
    idx = np.where(mask_todo)[0][-1]
    return df.index[idx]


def episodios(df: pd.DataFrame, estaciones: Optional[List[str]] = None,
              gap: int = GAP_BRIDGE,
              max_run: int = MAX_RUN_BARS,
              solo_vista_completa: bool = False) -> List[Dict]:
    """Agrupa velas activas en episodios con de-clustering desacoplado.

    Desacoplo:
      - Estaciones estructurales (yield_curve, credit, dxy) son de contexto;
        NO abren episodios por sí solas.
      - Disparan episodios: >=1 estación táctica O confluencia de >=2 estaciones.
      - Cierre de episodio: hueco > gap O longitud >= max_run (evita mega-episodios).
    """
    estaciones = estaciones or common.ESTACIONES
    detalle = marcas(df, estaciones)
    epis: List[Dict] = []
    run: List[int] = []
    prev: Optional[int] = None

    if solo_vista_completa:
        ultima_ok = ultima_fecha_completa(df, estaciones)
        idx_ok = df.index <= ultima_ok
        detalle = {pos: acts for pos, acts in detalle.items() if idx_ok[pos]}

    # Filtrar velas activables que disparan episodios (tácticas o confluencia >= 2)
    trigger_pos = sorted(
        pos for pos, acts in detalle.items()
        if any(st in ESTACIONES_TACTICAS for st in acts) or len(acts) >= 2
    )

    for pos in trigger_pos:
        if prev is None or (pos - prev <= gap and len(run) < max_run):
            run.append(pos)
        else:
            if (ep := _empaquetar(df, run, estaciones, detalle)) is not None:
                epis.append(ep)
            run = [pos]
        prev = pos

    if run:
        if (ep := _empaquetar(df, run, estaciones, detalle)) is not None:
            epis.append(ep)

    for i, ep in enumerate(epis, 1):
        ep["episodio_id"] = i
    return epis


def generar(df: Optional[pd.DataFrame] = None,
            estaciones: Optional[List[str]] = None,
            escribir: bool = True,
            solo_vista_completa: bool = True) -> List[Dict]:
    if df is None:
        df = common.cargar_lake()
    eps = episodios(df, estaciones=estaciones,
                    solo_vista_completa=solo_vista_completa)
    if escribir:
        common.SALIDAS.mkdir(parents=True, exist_ok=True)
        (common.SALIDAS / "episodios.json").write_text(
            json.dumps(eps, indent=2, ensure_ascii=False), encoding="utf-8")
        marc = marcas(df, estaciones)
        (common.SALIDAS / "mapa_activacion.json").write_text(
            json.dumps({str(k): v for k, v in marc.items()}, indent=2,
                       ensure_ascii=False), encoding="utf-8")
    return eps


if __name__ == "__main__":
    df = common.cargar_lake()
    eps = episodios(df, estaciones=common.ESTACIONES)
    print(f"Lake: {df.shape}")
    print(f"EPISODIOS generados: {len(eps)}")
    for e in eps[:5]:
        print(f"  #{e['episodio_id']:>4} {e['fecha_inicio']} -> {e['fecha_t1']} "
              f"barras={e['longitud_barras']:>3} "
              f"activas_t0={','.join(e['estaciones_activas_t0']) or '-'}")
    guardado = generar(df, estaciones=common.ESTACIONES)
    print("guardado en", common.SALIDAS / "episodios.json", "| total:", len(guardado))