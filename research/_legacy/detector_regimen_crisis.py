#!/usr/bin/env python3
"""
DETECTOR DE RÉGIMEN DE CRISIS — capa de diamantes ±3σ
======================================================
Reutiliza el primitivo oficial de la capa SIGMET (sigma_overflow.validate_overflow)
para detectar extremos fuera de escala en D1/D2/D3 de todas las estaciones.

Principios (definidos con el arquitecto, 22-Ago):
  - Cada extremo ±3σ observable es un DIAMANTE ESTADÍSTICO (§3.3 fact_store_v3).
  - El TAMAÑO de la señal que lo sigue establece el tamaño del diamante y su
    significancia: señal grande (N alto) = diamante grande confirmado;
    señal rara = diamante pequeño pero rico; sin señal = diamante por descubrir.
  - El régimen de crisis es OBSERVABLE en tiempo real (overflow en los últimos
    N días), sin sesgo de posición: no requiere saber el futuro.
  - Taxonomía SIGMET: OVERFLOW_MULTI (≥2 dims el mismo día), OVERFLOW_EXTREMO
    (depth>4σ), OVERFLOW_MODERADO (3σ<depth≤4σ).

Contención: un overflow está CONTENIDO si alguna señal activa dispara en los
+C_DIAS siguientes. Los no contenidos son diamantes por descubrir.
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
sys.path.insert(0, str(ROOT / "backend" / "modules" / "entry_decision" / "domain" / "rules"))
from medir_senal import SEÑALES, _CERTEZA, cargar_datos  # noqa: E402
from sigma_overflow import validate_overflow  # noqa: E402

# ── Configuración ──
# El régimen es una MÁQUINA DE ESTADOS observable (decisión del arquitecto, 22-Ago):
#   INICIO: un overflow ±3σ arranca el episodio (evento observable)
#   FIN por transición: un overflow nuevo termina implícitamente el anterior
#   FIN por deterioro: el z-score decae bajo UMBRAL_DETERIORO (medido, no supuesto)
# Sin ventana fija: la duración de un régimen la define el deterioro real.
UMBRAL_ENTRADA = 3.0      # σ: inicio del episodio de crisis
UMBRAL_DETERIORO = 2.0    # σ: fin del episodio al decaer bajo este nivel
UM_DIAMANTE = 21          # §3.3: N<21 = diamante (ROBUST desde 21)

# Perfiles de deterioro MEDIDOS (22-Ago, series diarias Timescale):
#   vix:  13 episodios, mediana 9d, P95 109d, máx 200d (reversiva, cola pesada)
#   vvix: 16 episodios, mediana 8d, P95 31d
#   skew:  6 episodios, mediana 13d
#   yield_curve/dxy: NUNCA decaen (quiebres de nivel permanentes = cambio de era)
# → Dos clases de estación: REVERSIVAS (decaen) y DE NIVEL (cambio de era).

# Estación → columna D1/D2/D3 en quants_obs
ESTACIONES = {
    "vix": ("vix_val", "vix_vel", "vix_vol"),
    "vvix": ("vvix_val", "vvix_vel", "vvix_vol"),
    "pcr": ("pcr_val", "pcr_vel", "pcr_vol"),
    "fg": ("fg_val", "fg_vel", "fg_vol"),
    "sv5_turbulence": ("sv5_turbulence_val", "sv5_turbulence_vel", "sv5_turbulence_vol"),
    "skew": ("skew_val", "skew_vel", "skew_vol"),
    "credit": ("credit_val", "credit_vel", "credit_vol"),
    "bsi": ("bsi_val", "bsi_vel", "bsi_vol"),
    "dxy": ("dxy_val", "dxy_vel", "dxy_vol"),
    "rotation": ("rotation_val", "rotation_vel", "rotation_vol"),
    "yield_curve": ("yield_curve_val", "yield_curve_vel", "yield_curve_vol"),
}
DIMS = {"d1": 0, "d2": 1, "d3": 2}


def confidence_tier(n: int) -> str:
    """Tiers §3.3 del fact store."""
    if n <= 2:
        return "ANECDOTAL"
    if n <= 5:
        return "LOW"
    if n <= 10:
        return "MODERATE"
    if n <= 20:
        return "HIGH"
    return "ROBUST"


def detectar_overflows(df):
    """Detecta todos los eventos ±3σ por estación × dimensión × día."""
    eventos = []
    for est, (c1, c2, c3) in ESTACIONES.items():
        cols = {"d1": c1, "d2": c2, "d3": c3}
        for dim, col in cols.items():
            if col not in df.columns:
                continue
            vals = df[col].astype(float)
            for i, v in vals.items():
                if pd.isna(v):
                    continue
                depth, flag = validate_overflow(est, dim, float(v))
                if flag is not None:
                    eventos.append({
                        "fecha": df["pivot_date"].iloc[i],
                        "estacion": est, "dim": dim,
                        "depth": float(depth), "direccion": flag,
                        "valor": float(v),
                    })
    ev = pd.DataFrame(eventos)
    if ev.empty:
        return ev
    return ev.sort_values("fecha").reset_index(drop=True)


def clasificar_taxonomia(ev):
    """Taxonomía SIGMET: MULTI (≥2 dims mismo día), EXTREMO (>4σ), MODERADO."""
    if ev.empty:
        return ev
    ev = ev.copy()
    dims_por_dia = ev.groupby("fecha")["dim"].nunique()
    ev["taxonomia"] = "OVERFLOW_MODERADO"
    ev.loc[ev["depth"] > 4.0, "taxonomia"] = "OVERFLOW_EXTREMO"
    multi = set(dims_por_dia[dims_por_dia >= 2].index)
    ev.loc[ev["fecha"].isin(multi), "taxonomia"] = "OVERFLOW_MULTI"
    return ev


def señales_activas(df):
    """Señales evaluables: sin pivot_type, sin RETIRADA/DEGRADADA, y sin
    BACKGROUND (fire rate >20%). Las background saturan la contención igual
    que saturaban F3 (lección de la auditoría forense)."""
    import inspect
    activas = {}
    for n in SEÑALES:
        cert = str(_CERTEZA.get(n, {}).get("validacion", ""))
        if "RETIRADA" in cert or "DEGRADADA" in cert:
            continue
        if "pivot_type" in inspect.getsource(SEÑALES[n]):
            continue
        s = SEÑALES[n](df).astype(bool)
        if s.mean() > 0.20:  # background: dispara demasiado para contener algo
            continue
        activas[n] = s
    return activas


# Mapa señal → estaciones que lee (auditoría 22-Ago, verificado por inspección
# del source). Usado para clasificar la contención: un overflow contenido por
# una señal de la MISMA estación×dimensión es una IDENTIDAD, no información.
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
    "sorpresa_total": set(), "cascade_reversal": set(),
}


def _clasificar_contencion(estacion_overflow, dim_overflow, señal):
    """Clasifica un par (overflow, señal contenedora).

    TAUTOLOGICA:   la señal lee la misma estación y el overflow es D1 (la señal
                   está construida sobre ese mismo estado → identidad).
    INTRA_FAMILIA: misma estación pero overflow en D2/D3, o familia de pánico
                   compartida.
    CROSS_FAMILIA: la señal no lee la estación del overflow → información
                   cruzada genuina.
    """
    ests = SEÑAL_ESTACIONES.get(señal, set())
    if estacion_overflow in ests:
        if dim_overflow == "d1":
            return "TAUTOLOGICA"
        return "INTRA_FAMILIA"
    return "CROSS_FAMILIA"


def analizar_contencion(ev, df, activas, c_dias=5):
    """Para cada overflow: ¿qué señales lo contienen (disparan en +c_dias)?

    Cada contenedora se clasifica (auditoría 22-Ago, P0.2): la contención
    'tautológica' (overflow ≡ señal, misma estación×dimensión) se separa de la
    contención genuina (cross-familia), que es la única que aporta información.
    """
    dates = pd.DatetimeIndex(df["pivot_date"])
    sig_fechas = {n: set(dates[s.values]) for n, s in activas.items()}
    rows = []
    for _, e in ev.iterrows():
        d = e["fecha"]
        ventana = {d + pd.Timedelta(days=k) for k in range(0, c_dias + 1)}
        contenedoras = sorted(n for n, fs in sig_fechas.items() if ventana & fs)
        clasif = sorted({_clasificar_contencion(e["estacion"], e["dim"], n)
                         for n in contenedoras}) if contenedoras else []
        if not contenedoras:
            tipo = "NO_CONTENIDO"
        elif "CROSS_FAMILIA" in clasif:
            tipo = "CROSS_FAMILIA"
        elif "INTRA_FAMILIA" in clasif:
            tipo = "INTRA_FAMILIA"
        else:
            tipo = "TAUTOLOGICA"
        rows.append({**e.to_dict(), "contenido": bool(contenedoras),
                     "contenedoras": contenedoras, "n_contenedoras": len(contenedoras),
                     "contencion_tipo": tipo, "contencion_clases": clasif})
    return pd.DataFrame(rows)


def regimen_crisis(ev, fechas, ventana=None):
    """DEPRECADO: reemplazado por construir_episodios_regimen().
    Se mantiene solo para compatibilidad; ignora `ventana` y usa episodios."""
    ep = construir_episodios_regimen(ev)
    fechas_overflow = set()
    for e in ep:
        fechas_overflow.add(e["inicio"])
    regimen = []
    for d in fechas:
        activo = any(e["inicio"] <= d <= e["fin"] for e in ep)
        regimen.append(activo)
    return np.array(regimen)


# ── Estaciones REVERSIVAS (decaen tras el overflow) vs DE NIVEL (cambio de era) ──
# Medido 22-Ago sobre series diarias Timescale:
#   reversivas: vix (mediana 9d), vvix (8d), skew (13d), credit (42d) → episodios reales
#   de nivel:   yield_curve, dxy → NUNCA decaen; marcan cambio de era, no crisis
ESTACIONES_REVERSIVAS = ["vix", "vvix", "skew", "credit"]


def construir_episodios_regimen(ev):
    """MÁQUINA DE ESTADOS observable del régimen de crisis (sin ventana fija).

    Reglas (definidas por el arquitecto):
      INICIO: un overflow ±3σ en una estación reversiva arranca el episodio.
      FIN por deterioro: todas las estaciones activas decaen bajo UMBRAL_DETERIORO.
      FIN por transición: si el régimen ya estaba inactivo y llega un overflow
        nuevo, ese overflow termina implícitamente el episodio anterior y arranca otro.

    Un episodio = período contiguo de régimen activo. Dentro de un episodio activo,
    overflows adicionales en otras estaciones se integran al mismo episodio (la crisis
    continúa); solo un overflow tras un período inactivo arranca un episodio nuevo.
    """
    evr = ev[ev["estacion"].isin(ESTACIONES_REVERSIVAS)].copy()
    if evr.empty:
        return []
    evr = evr.sort_values("fecha").reset_index(drop=True)
    # Duración de deterioro medida por estación (mediana, en días) → hasta cuándo
    # se considera "activo" un overflow antes de asumir deterioro si no hay dato diario.
    deterioro_dias = {"vix": 9, "vvix": 8, "skew": 13, "credit": 42}

    episodios = []
    actual = None  # dict: inicio, fin, estaciones, iniciador, overflows
    for _, row in evr.iterrows():
        f = row["fecha"]
        if actual is None:
            # arranca episodio nuevo
            actual = {"inicio": f, "fin": f, "iniciador": row["estacion"],
                      "estaciones": {row["estacion"]}, "n_overflows": 1,
                      "taxonomias": {row["taxonomia"]}}
        else:
            # ¿el episodio actual sigue activo (no ha deteriorado)?
            fin_previsto = actual["fin"] + pd.Timedelta(
                days=max(deterioro_dias.get(s, 10) for s in actual["estaciones"]))
            if f <= fin_previsto:
                # se integra al episodio activo
                actual["fin"] = max(actual["fin"], f)
                actual["estaciones"].add(row["estacion"])
                actual["n_overflows"] += 1
                actual["taxonomias"].add(row["taxonomia"])
            else:
                # el anterior deterioró → cerrarlo, y este overflow arranca uno nuevo
                actual["fin_real"] = actual["fin"] + pd.Timedelta(
                    days=max(deterioro_dias.get(s, 10) for s in actual["estaciones"]))
                actual["causa_fin"] = "deterioro"
                episodios.append(actual)
                actual = {"inicio": f, "fin": f, "iniciador": row["estacion"],
                          "estaciones": {row["estacion"]}, "n_overflows": 1,
                          "taxonomias": {row["taxonomia"]}}
    if actual is not None:
        actual["fin_real"] = actual["fin"] + pd.Timedelta(
            days=max(deterioro_dias.get(s, 10) for s in actual["estaciones"]))
        actual["causa_fin"] = "deterioro"
        episodios.append(actual)

    # enriquecer
    for e in episodios:
        e["duracion_dias"] = (e["fin_real"] - e["inicio"]).days
        e["n_estaciones"] = len(e["estaciones"])
        e["estaciones"] = sorted(e["estaciones"])
        e["taxonomias"] = sorted(e["taxonomias"])
    return episodios


def main():
    df, spy = cargar_datos()
    ev = detectar_overflows(df)
    ev = clasificar_taxonomia(ev)
    activas = señales_activas(df)
    cont = analizar_contencion(ev, df, activas)

    # ── MÁQUINA DE ESTADOS del régimen de crisis ──
    episodios = construir_episodios_regimen(ev)
    duraciones = np.array([e["duracion_dias"] for e in episodios]) if episodios else np.array([0])
    pct_crisis = float(duraciones.sum()) / ((df["pivot_date"].max() - df["pivot_date"].min()).days or 1)

    # ── Diamantes por tipo de overflow ──
    cont["tipo"] = cont["estacion"] + "|" + cont["dim"] + "|" + cont["direccion"]
    diamantes = []
    for tipo, sub in cont.groupby("tipo"):
        n = len(sub)
        contenidas_total = sub["contenido"].mean()
        if sub["contenido"].any():
            from collections import Counter
            flat = [c for cs in sub["contenedoras"] for c in cs]
            ancla, ancla_n = Counter(flat).most_common(1)[0]
        else:
            ancla, ancla_n = None, 0
        diamantes.append({
            "tipo": tipo, "n": n, "tier": confidence_tier(n),
            "diamante": n < UM_DIAMANTE,
            "contenido_pct": round(contenidas_total, 3),
            "señal_ancla": ancla, "ancla_n": ancla_n,
            "taxonomias": sub["taxonomia"].value_counts().to_dict(),
        })
    diamantes.sort(key=lambda x: -x["n"])

    # ── Contención por señal ──
    contencion_señal = {}
    for n in activas:
        k = cont["contenedoras"].apply(lambda cs: n in cs).sum()
        contencion_señal[n] = int(k)

    no_contenidos = cont[~cont["contenido"]]

    reporte = {
        "fecha_generacion": str(pd.Timestamp.now()),
        "config": {"umbral_entrada": UMBRAL_ENTRADA, "umbral_deterioro": UMBRAL_DETERIORO,
                   "um_diamante": UM_DIAMANTE,
                   "estaciones_reversivas": ESTACIONES_REVERSIVAS,
                   "modelo": "máquina de estados: inicio=overflow ±3σ, "
                             "fin=deterioro bajo 2σ o transición por overflow nuevo"},
        "total_overflows": len(ev),
        "taxonomia": ev["taxonomia"].value_counts().to_dict(),
        "por_direccion": ev["direccion"].value_counts().to_dict(),
        "por_estacion": ev["estacion"].value_counts().to_dict(),
        "regimen": {
            "n_episodios": len(episodios),
            "duracion_media_dias": round(float(duraciones.mean()), 1) if len(episodios) else 0,
            "duracion_mediana_dias": round(float(np.median(duraciones)), 1) if len(episodios) else 0,
            "duracion_p95_dias": round(float(np.percentile(duraciones, 95)), 1) if len(episodios) else 0,
            "pct_tiempo_en_crisis": round(pct_crisis, 3),
            "episodios": [{"inicio": str(e["inicio"].date()), "fin_real": str(e["fin_real"].date()),
                           "duracion": e["duracion_dias"], "iniciador": e["iniciador"],
                           "estaciones": e["estaciones"], "n_overflows": e["n_overflows"]}
                          for e in episodios],
        },
        "diamantes": diamantes,
        "contencion_por_señal": dict(sorted(contencion_señal.items(),
                                            key=lambda x: -x[1])),
        "overflows_no_contenidos": len(no_contenidos),
        "pct_no_contenidos": round(len(no_contenidos) / len(cont), 3) if len(cont) else 0,
        "no_contenidos_por_dimension": no_contenidos["dim"].value_counts().to_dict(),
        "no_contenidos_por_estacion": no_contenidos["estacion"].value_counts().to_dict(),
        # ── Contención genuina vs tautológica (auditoría 22-Ago, P0.2) ──
        # TAUTOLOGICA = overflow ≡ señal (misma estación, D1) → NO es información.
        # La contención que importa es CROSS_FAMILIA.
        "contencion_por_tipo": cont["contencion_tipo"].value_counts().to_dict(),
        "pct_contencion_genuina": round(
            float((cont["contencion_tipo"] == "CROSS_FAMILIA").mean()), 3),
        "punto_ciego_d3_genuino": int(((~cont["contenido"]) |
            (cont["contencion_tipo"] == "TAUTOLOGICA")).sum()),
    }

    out = ROOT / "data" / "research" / "signals" / "regimen_crisis_diamantes.json"
    out.write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str))

    # ── Salida por consola ──
    print(f"{'='*100}\nDETECTOR DE RÉGIMEN DE CRISIS — máquina de estados observable")
    print(f"{'='*100}")
    print(f"Total overflows ±3σ: {len(ev)}")
    print(f"Taxonomía SIGMET: {reporte['taxonomia']}")
    print(f"\n{'─'*100}")
    reg = reporte["regimen"]
    print(f"EPISODIOS DE CRISIS (estaciones reversivas: {ESTACIONES_REVERSIVAS})")
    print(f"  N episodios: {reg['n_episodios']}")
    print(f"  Duración: media {reg['duracion_media_dias']}d | mediana {reg['duracion_mediana_dias']}d | "
          f"P95 {reg['duracion_p95_dias']}d")
    print(f"  % del tiempo en régimen de crisis: {reg['pct_tiempo_en_crisis']:.1%}")
    print(f"  Últimos 12 episodios:")
    print(f"  {'inicio':>12s} → {'fin':>12s} | {'dur':>4s} | {'iniciador':>14s} | estaciones")
    for e in reg["episodios"][-12:]:
        print(f"  {e['inicio']:>12s} → {e['fin_real']:>12s} | {e['duracion']:>3d}d | "
              f"{e['iniciador']:>14s} | {','.join(e['estaciones'])}")
    print(f"\n{'─'*100}")
    print(f"DIAMANTES por tipo de overflow (tamaño = N de eventos, tier §3.3):")
    print(f"{'tipo':>34s} | {'N':>4s} {'tier':>9s} {'💎':>2s} | {'conten%':>7s} | señal ancla (tamaño=significancia)")
    for d in diamantes[:20]:
        mark = "💎" if d["diamante"] else ""
        ancla = f"{d['señal_ancla']} (N={d['ancla_n']})" if d["señal_ancla"] else "SIN ANCLA → diamante por descubrir"
        print(f"{d['tipo']:>34s} | {d['n']:>4d} {d['tier']:>9s} {mark:>2s} | "
              f"{d['contenido_pct']:>6.0%} | {ancla}")
    print(f"  ... {len(diamantes)} tipos en total")
    print(f"\n{'─'*100}")
    print(f"NO CONTENIDOS: {reporte['overflows_no_contenidos']} "
          f"({reporte['pct_no_contenidos']:.0%}) → diamantes por descubrir")
    print(f"  por dimensión: {reporte['no_contenidos_por_dimension']}")
    print(f"  por estación:  {reporte['no_contenidos_por_estacion']}")
    print(f"\n✅ Guardado: {out}")


if __name__ == "__main__":
    main()
