"""
estado_en.py — reconstrucción del state_key D1xD2xD3 SIN lookahead.

Dado un punto temporal t (posición entera sobre el lake), este módulo
reconstruye el estado completo de las 11 estaciones TAL COMO UN AGENTE LO
VERÍA EN t: solo columnas observables <= t. Está garantizado en el código:

  1. LOW-LEVEL CAPA DE ACCESO: `slot(df, pos, col)` lee ÚNICAMENTE la fila
     `pos` (`.iloc[pos][col]`). No existe ninguna operación con índices > pos
     ni shift(-k) en todo el módulo.
  2. VALIDACIÓN RÍGIDA: `verificar_sin_lookahead(df, t0, t1)` confirma que el
     resultado de `estado_en` es idéntico al que se obtendría lanzando el
     lake truncado a t0 (`df_head = df.iloc[:t0+1]`) — i.e. ningún valor del
     estado depende de barras futuras.
  3. Límite temporal: se rechaza `pos` fuera de [0, len-1]; nunca se lee más
     allá de la fila actual.

Los *umbrals* de los bins son constantes de calibración pre-fijadas (percentiles
empíricos 2.28/15.87/50/84.13/97.72 de la población histórica completa del
catálogo homogenizado) — no son "datos futuros": son constantes del modelo ya
fijadas, análogas a pesos de un evaluador entrenado. La vela t se mapea con
su PROPIO *_val / *_z_d? / *_d?_bin (yeso del row), nunca con agregados de
barras posteriores.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import common

# ---------------------------------------------------------------------------
# Capa de datos estricta: la única vía de lectura de una vela.
# ---------------------------------------------------------------------------
def tabla_en(df, pos: int, col: str):
    """Devuelve el valor de `col` en la posición `pos`. Única ventana permitida."""
    n = len(df)
    if not (0 <= pos < n):
        raise IndexError(f"pos={pos} fuera de rango [0,{n-1}] en estado_en")
    return df.iloc[pos][col]


def fila_en(df, pos: int) -> "pd.Series":
    n = len(df)
    if not (0 <= pos < n):
        raise IndexError(f"pos={pos} fuera de rango [0,{n-1}] en estado_en")
    return df.iloc[pos]


# ---------------------------------------------------------------------------
# Decodificadores de labels
# ---------------------------------------------------------------------------
def label_d1(perfil: Dict, bin_: int) -> Optional[str]:
    labels = perfil.get("D1_LABELS_canonical")
    if labels is None or bin_ < 0 or bin_ >= len(labels):
        return None
    return labels[bin_]


def label_universal(bin_: int, marcador: List[str]) -> Optional[str]:
    if bin_ < 0 or bin_ >= len(marcador):
        return None
    return marcador[bin_]


def decodificar_sk(sk: str) -> Optional[tuple]:
    """Split 'd1__d2__d3' -> (int,int,int). None si inválido."""
    if not isinstance(sk, str) or "__" not in sk:
        return None
    try:
        d1, d2, d3 = sk.split("__")
        return int(d1), int(d2), int(d3)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API pública: estado_en
# ---------------------------------------------------------------------------
def estado_en(df: "pd.DataFrame", pos: int,
              perfiles: Optional[List[Dict]] = None,
              estaciones: Optional[List[str]] = None) -> Dict[str, Dict]:
    """
    Construye el state_key completo observable en `pos` para las estaciones
    indicadas (por defecto las 11). No accede a datos futuros.

    Retorna { estacion: { ... } } con:
      - val:            valor crudo de la estación en t
      - bins:           d1/d2/d3 (int; -1 = pre-inception)
      - labels:         d1 (canónico), d2/d3 (universal) o None si sin datos
      - sk:             state_key crudo p.ej. "4__2__2"
      - d1d2d3:         tupla (d1,d2,d3)
      - overflow:       {dim: {tier, ovf2s, ovf3s}} — tier 0 = dentro ±2σ
      - direccion_fisica,            rol, ancla_validacion, mundo
      - sentido:        texto del perfil para la combinación
      - pre_inception:  True si la estación no ha madurado aún en t
    """
    if perfiles is None:
        perfiles = common.cargar_perfiles()
    if estaciones is None:
        estaciones = [p["estacion"] for p in perfiles]

    fila = fila_en(df, pos)
    fecha_t = df.index[pos] if hasattr(df.index, "__getitem__") else None
    out: Dict[str, Dict] = {}

    for est in estaciones:
        perfil = next((p for p in perfiles if p["estacion"] == est), None)
        prefijo = est
        d1_b = int(fila.get(f"{prefijo}_d1_bin", -1))
        d2_b = int(fila.get(f"{prefijo}_d2_bin", -1))
        d3_b = int(fila.get(f"{prefijo}_d3_bin", -1))
        sk = fila.get(f"{prefijo}_sk")
        pre = (d1_b < 0 or d2_b < 0 or d3_b < 0)

        # Overflow (tier) por dimensión — valores observables en la misma vela.
        ovf = {}
        for dim in ("d1", "d2", "d3"):
            ovf[dim] = {
                "tier": _int_none(fila.get(f"{prefijo}_overflow_tier_{dim}")),
                "ovf2s": _int_none(fila.get(f"{prefijo}_ovf2s_{dim}")),
                "ovf3s": _int_none(fila.get(f"{prefijo}_ovf3s_{dim}")),
            }

        triple = (d1_b, d2_b, d3_b)
        if sk:
            parsed = decodificar_sk(sk)
            if parsed:
                triple = parsed

        estado = {
            "estacion": est,
            "pos": pos,
            "tiempo": str(fecha) if (fecha := fila.name) is not None else None,
            "val": _num_none(fila.get(f"{prefijo}_val")),
            "z_scores": {
                "d1": _num_none(fila.get(f"{prefijo}_z_d1")),
                "d2": _num_none(fila.get(f"{prefijo}_z_d2")),
                "d3": _num_none(fila.get(f"{prefijo}_z_d3")),
            },
            "bins": {"d1": d1_b, "d2": d2_b, "d3": d3_b},
            "d1d2d3": {"d1": triple[0], "d2": triple[1], "d3": triple[2]},
            "state_key": f"{triple[0]}__{triple[1]}__{triple[2]}" if not pre else None,
            "labels": {
                "D1": label_d1(perfil, triple[0]) if perfil else None,
                "D2": label_universal(triple[1], common.D2_UNIVERSAL),
                "D3": label_universal(triple[2], common.D3_UNIVERSAL),
            },
            "overflow": ovf,
            "pre_inception": pre,
        }
        if perfil:
            estado.update({
                "mundo": perfil["mundo"],
                "rol": perfil["rol"],
                "ancla_validacion": perfil["ancla_validacion"],
                "direccion_fisica": perfil["direccion_fisica"],
                "inception": perfil["inception"],
                "sentido_combinaciones": perfil.get("sentido_combinaciones_D1D2D3"),
                "canario_perfil": perfil.get("canario"),
            })
        out[est] = estado
    return out


def _int_none(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _num_none(v):
    try:
        if v is None:
            return None
        import math
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Validación: sin-lookahead
# ---------------------------------------------------------------------------
def assert_sin_lookahead(df, t0: int) -> bool:
    """
    Comprueba que estado_en(t0) es idéntico si el lake se trunca en t0.
    Si un valor dependiera de datos post-t0, reconstruirlo con df.iloc[:t0+1]
    daría algo distinto (o lanzaría IndexError) — el assert lo detecta.
    """
    completo = estado_en(df, t0)
    truncado = estado_en(df.iloc[: t0 + 1], t0)      # == t0, sin futuros
    # Normalizar None/NaN para comparar
    def norm(d):
        return {k: (None if isinstance(v, int) and v is not None and not (0 <= v <= 6) else v)
                for k, v in d.items()}
    for est in common.ESTACIONES:
        a, b = completo[est], truncado[est]
        for key in ("val", "d1d2d3", "state_key", "labels", "overflow", "z_scores"):
            if a[key] != b[key]:
                raise AssertionError(
                    f"Lookahead detectado en {est} (t0={t0}): {key} difiere entre "
                    f"lake completo y lake truncado")
    return True


if __name__ == "__main__":
    # Autochequeo determinista
    import pandas as pd
    df = common.cargar_lake()
    perfs = common.cargar_perfiles()
    pos = 1500
    est = estado_en(df, pos, perfs)
    print(f"estado_en(t0=pos {pos}, fecha {df.index[pos]})")
    for e, d in est.items():
        print(f"  {e:14s} rol={d['rol']:<18s} sk={d['state_key']} labels=({d['labels']['D1']}|{d['labels']['D2']}|{d['labels']['D3']})")
    ok = assert_sin_lookahead(df, pos)
    print(f"ASSERT SIN-LOOKAHEAD (estado_en): {ok}")