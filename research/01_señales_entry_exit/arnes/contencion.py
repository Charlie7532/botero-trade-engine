"""Contención de Crisis — clasificación de overflows y señales contenedoras.

Extraído de research/_legacy/detector_regimen_crisis.py.
Funciones puras para clasificar la relación entre un overflow ±3σ
y las señales que disparan en su vecindad temporal.

Taxonomía de contención (auditoría 22-Ago):
  TAUTOLÓGICA:   la señal lee la misma estación y el overflow es D1
                 (la señal está construida sobre ese mismo estado → identidad).
  INTRA_FAMILIA: misma estación pero overflow en D2/D3, o familia de pánico
                 compartida.
  CROSS_FAMILIA: la señal no lee la estación del overflow → información
                 cruzada genuina.
"""
import numpy as np
import pandas as pd
from typing import Optional


# Mapa señal → estaciones que lee (verificado por inspección de source, 22-Ago)
SEÑAL_ESTACIONES = {
    "credit_easing_k1": {"credit"}, "panico_total": {"vix", "skew"},
    "capitulacion": {"vix", "bsi"}, "sub_reaccion": {"vix", "bsi"},
    "euforia": {"vix", "bsi"}, "vvix_entry": {"vix", "vvix"},
    "bsi_washed_out": {"bsi"}, "credit_stress": {"credit"},
    "dxy_bearish": {"dxy"}, "pcr_put_panic": {"pcr"},
    "fg_extreme_fear": {"fg"}, "fg_extreme_greed": {"fg"},
    "bsi_recovery": {"bsi"}, "vix_crisis_spike": {"vix"},
    "credit_stress_exit": {"credit"}, "dxy_spike_exit": {"dxy"},
    "pcr_panic_exit": {"pcr"}, "skew_paranoia_exit": {"skew"},
    "vix_complacency_exit": {"vix"}, "credit_ease_exit": {"credit"},
    "breadth_contraction_exit": {"bsi"},
    "regime_change_exit": {"vix", "credit", "bsi"},
    "sv5t_silent_distribution": {"sv5_turbulence"},
    "credit_equity_divergence": {"credit"},
    "stealth_tail_hedging": {"vix", "skew"},
    "defensive_rotation_divergence": {"rotation"},
    "capitulacion_v2": {"vix", "bsi"},
    "euforia_v2": {"bsi"},  # V2 eliminated VIX filter (only BSI D1+D2)
    "vix_crisis_spike_v2": {"vix"},
    # E7 multi-station signals iterate over all 11 METAR stations
    "neutral_crush_entry": {"vix", "bsi", "credit", "yield_curve", "vvix",
                            "sv5_turbulence", "fg", "skew", "pcr", "rotation", "dxy"},
    "neutral_spike_exit": {"vix", "bsi", "credit", "yield_curve", "vvix",
                           "sv5_turbulence", "fg", "skew", "pcr", "rotation", "dxy"},
    "sorpresa_total": set(), "cascade_reversal": set(),
}

# Estaciones REVERSIVAS (decaen tras overflow) vs DE NIVEL (cambio de era, nunca decaen)
# Medido 22-Ago sobre series diarias Timescale:
#   reversivas: vix (mediana 9d), vvix (8d), skew (13d), credit (42d)
#   de nivel:   yield_curve, dxy → NUNCA decaen; marcan cambio de era, no crisis
ESTACIONES_REVERSIVAS = {"vix", "vvix", "skew", "credit"}

# Deterioro medido por estación (mediana en días)
DETERIORO_DIAS = {"vix": 9, "vvix": 8, "skew": 13, "credit": 42}


def clasificar_contencion(estacion_overflow: str, dim_overflow: str, señal: str) -> str:
    """Clasifica un par (overflow, señal contenedora).

    Returns:
        "TAUTOLOGICA" | "INTRA_FAMILIA" | "CROSS_FAMILIA"
    """
    ests = SEÑAL_ESTACIONES.get(señal, set())
    if estacion_overflow in ests:
        if dim_overflow == "d1":
            return "TAUTOLOGICA"
        return "INTRA_FAMILIA"
    return "CROSS_FAMILIA"


def analizar_contencion(
    ev: pd.DataFrame,
    pivot_dates: pd.DatetimeIndex,
    señales_activas: dict[str, pd.Series],
    c_dias: int = 5,
) -> pd.DataFrame:
    """Para cada overflow: ¿qué señales lo contienen (disparan en +c_dias)?

    Args:
        ev: DataFrame de overflows con columnas ['fecha', 'estacion', 'dim', 'depth', ...].
        pivot_dates: DatetimeIndex de las fechas de pivote del dataset.
        señales_activas: Dict {nombre_señal: Series[bool]} indexado igual que pivot_dates.
        c_dias: Ventana de contención en días calendario.

    Returns:
        DataFrame con columnas adicionales: contenido, contenedoras, n_contenedoras,
        contencion_tipo, contencion_clases.
    """
    sig_fechas = {
        n: set(pivot_dates[s.values]) for n, s in señales_activas.items()
    }
    rows = []
    for _, e in ev.iterrows():
        d = e["fecha"]
        ventana = {d + pd.Timedelta(days=k) for k in range(0, c_dias + 1)}
        contenedoras = sorted(n for n, fs in sig_fechas.items() if ventana & fs)
        clasif = sorted({
            clasificar_contencion(e["estacion"], e["dim"], n)
            for n in contenedoras
        }) if contenedoras else []

        if not contenedoras:
            tipo = "NO_CONTENIDO"
        elif "CROSS_FAMILIA" in clasif:
            tipo = "CROSS_FAMILIA"
        elif "INTRA_FAMILIA" in clasif:
            tipo = "INTRA_FAMILIA"
        else:
            tipo = "TAUTOLOGICA"

        rows.append({
            **e.to_dict(),
            "contenido": bool(contenedoras),
            "contenedoras": contenedoras,
            "n_contenedoras": len(contenedoras),
            "contencion_tipo": tipo,
            "contencion_clases": clasif,
        })
    return pd.DataFrame(rows)


def construir_episodios_regimen(ev: pd.DataFrame) -> list[dict]:
    """MÁQUINA DE ESTADOS observable del régimen de crisis (sin ventana fija).

    Reglas (definidas por el arquitecto, 22-Ago):
      INICIO: un overflow ±3σ en una estación reversiva arranca el episodio.
      FIN por deterioro: todas las estaciones activas decaen bajo UMBRAL_DETERIORO.
      FIN por transición: un overflow tras período inactivo arranca episodio nuevo.

    Args:
        ev: DataFrame de overflows con columnas ['fecha', 'estacion', 'taxonomia', ...].

    Returns:
        Lista de episodios: [{inicio, fin, iniciador, estaciones, n_overflows, taxonomias}]
    """
    evr = ev[ev["estacion"].isin(ESTACIONES_REVERSIVAS)].copy()
    if evr.empty:
        return []
    evr = evr.sort_values("fecha").reset_index(drop=True)

    episodios = []
    actual: Optional[dict] = None

    for _, row in evr.iterrows():
        f = row["fecha"]
        if actual is None:
            actual = {
                "inicio": f, "fin": f, "iniciador": row["estacion"],
                "estaciones": {row["estacion"]}, "n_overflows": 1,
                "taxonomias": {row.get("taxonomia", "UNKNOWN")},
            }
        else:
            max_deterioro = max(DETERIORO_DIAS.get(e, 9) for e in actual["estaciones"])
            gap = (f - actual["fin"]).days
            if gap <= max_deterioro:
                # Extiende el episodio
                actual["fin"] = f
                actual["estaciones"].add(row["estacion"])
                actual["n_overflows"] += 1
                actual["taxonomias"].add(row.get("taxonomia", "UNKNOWN"))
            else:
                # Cierra episodio anterior, abre nuevo
                actual["estaciones"] = sorted(actual["estaciones"])
                actual["taxonomias"] = sorted(actual["taxonomias"])
                episodios.append(actual)
                actual = {
                    "inicio": f, "fin": f, "iniciador": row["estacion"],
                    "estaciones": {row["estacion"]}, "n_overflows": 1,
                    "taxonomias": {row.get("taxonomia", "UNKNOWN")},
                }

    if actual is not None:
        actual["estaciones"] = sorted(actual["estaciones"])
        actual["taxonomias"] = sorted(actual["taxonomias"])
        episodios.append(actual)

    return episodios
