# -*- coding: utf-8 -*-
"""
curador.py — Fase 3. Fusión probabilística de las 11 lecturas de los agentes.

Principios (arnés METAR, no negociable):
  - Confluencia PROBABILÍSTICA, no determinista: la dirección confluente no es
    un "empate que gana"; es la posterior P(dirección del pivote próximo)
    calculada agregando las lecturas CON señal, ponderadas por la convicción
    del agente (ALTA=3 / MEDIA=2 / BAJA=1).
  - Dato mata relato: un agente cuya convicción ya colapsó por falta de edge
    (ALTA->MEDIA->BAJA) contribuye poco al peso agregado.
  - De-clustering = credibilidad, no exclusión: cada lectura cuenta por su
    convicción, ninguna se descarta a priori; la contradicción se *reporta*
    (señal_contradictoria) en vez de silenciarse.
  - Rol precognitivo (precursor/canario/confirmador/ruido) se contabiliza como
    descriptor de SI el mundo espera anticipar el pivote, no como veto.

Entrada: las 11 lecturas de `Agente.leer(t, episodio)` (estructura canónica).
Salida : dict de fusión con conteos, confluencia probabilística, contradicción,
         co-ocurrencias con el catálogo de confluencias canarias, y alerta.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from comite_metar.scripts import common


# ---------------------------------------------------------------------------
# Pesos de convicción (hecho normativo del arnés: dato mata relato).
# ---------------------------------------------------------------------------
_CONV_PESO = {"ALTA": 3, "MEDIA": 2, "BAJA": 1}
_DIRS = ("ALZA", "BAJA", "NEUTRAL")
_ROL = ("precursor", "canario", "confirmador", "ruido")


def conviccion_peso(conviccion: Optional[str]) -> int:
    """Peso numérico de una convicción (ALTA=3/MEDIA=2/BAJA=1)."""
    return _CONV_PESO.get(str(conviccion).upper(), 1 if conviccion else 0)


def _norm_dir(d: Optional[str]) -> str:
    """Normaliza la dirección de un agente a (ALZA, BAJA, NEUTRAL).

    El agente (`_agente_base._TIPOS_DIR`) emite ALCISTA/BAJISTA/NEUTRAL;
    el curador y el modelador consumen ALZA/BAJA. Este helper unifica ambos
    vocabularios para que la confluencia no se vacíe por dicha discrepancia.
    """
    s = str(d or "").strip().upper()
    if s in ("ALZA", "ALCISTA", "BULLISH", "BULL"):
        return "ALZA"
    if s in ("BAJA", "BAJISTA", "BEARISH", "BEAR"):
        return "BAJA"
    return "NEUTRAL"


def _lectura_util(r: Dict) -> Optional[Dict]:
    """Extrae la lectura parseada de una respuesta de `Agente.leer`."""
    if not isinstance(r, dict):
        return None
    if r.get("pre_inception") or not r.get("maduro"):
        return None
    lec = r.get("lectura")
    if not isinstance(lec, dict):
        return None
    return lec


def co_ocurrencias_catalogo(estaciones_senal: set,
                            confluencias: Optional[List[Dict]] = None
                            ) -> Dict:
    """Confluencias canarias del catálogo activadas por estaciones con señal.

    Una confluencia del catálogo 'se activa' cuando las estaciones de AMBOS
    endpoints (signal_a / signal_b) están predecitendo dirección en este
    episodio. No asigna dirección (eso es del modelador): esta función es un
    refuerzo descriptivo (confluencia probabilística reforzada).
    """
    if confluencias is None:
        confluencias = common.cargar_confluencias().get("confluencias", [])
    activas = []
    for c in confluencias:
        sa, sb = c.get("signal_a"), c.get("signal_b")
        ea, eb = common.senal_estacion(sa), common.senal_estacion(sb)
        if ea in estaciones_senal and eb in estaciones_senal:
            activas.append({
                "tipo": c.get("tipo"),
                "signal_a": sa, "signal_b": sb,
                "station_a": ea, "station_b": eb,
                "independencia": c.get("independencia"),
                "p_independencia": c.get("p_independencia"),
                "edge_combinado": c.get("edge_combinado"),
            })
    return {"n_activas": len(activas), "lista": activas[:12]}


def fuse(lecturas: List[Dict],
         episodio: Optional[Dict] = None,
         confluencias: Optional[List[Dict]] = None) -> Dict:
    """Funde las lecturas de los agentes en la decisión probabilística del comité.

    Returns
    -------
    dict con:
        conteo_votos / conteo_roles           : frecuencia por dirección y rol
        pesos_conviccion                       : {estacion: peso}
        confluencia_probabilistica             : P(ALZA), P(BAJA), P_senal,
                                                 direccion_confluente,
                                                 conviccion_confluente [0,1]
        flujo_neto                             : score neto +/- (crudo ponderado)
        señal_contradictoria                   : bool + detalle
        co_ocurrencia_catalogo                 : canarios activados
        alerta                                 : texto
    """
    ep = episodio or {}
    resultado: Dict = {
        "episodio_id": ep.get("episodio_id"),
        "t0": ep.get("t0"),
        "fecha": ep.get("fecha_inicio"),
        "n_agentes_maduros": 0,
        "n_agentes_senal": 0,
        "conteo_votos": {d: 0 for d in _DIRS},
        "conteo_roles": {r: 0 for r in _ROL},
        "pesos_total": {},
        "lecturas_utilizadas": [],
    }

    pesos: Dict[str, int] = {}
    anti: Dict[str, int] = {d: 0 for d in ("ALZA", "BAJA")}
    senal_est = set()
    maduros = 0
    for r in lecturas:
        lec = _lectura_util(r)
        if not lec:
            continue
        est = lec.get("estacion") or r.get("estacion")
        maduros += 1
        dir_ = _norm_dir(lec.get("direccion_anticipada_spy", "NEUTRAL"))
        rol = lec.get("rol_precognitivo", "ruido")
        conv = lec.get("conviccion")
        w = conviccion_peso(conv)
        resultado["conteo_votos"][dir_] = resultado["conteo_votos"].get(dir_, 0) + 1
        resultado["conteo_roles"][rol] = resultado["conteo_roles"].get(rol, 0) + 1
        pesos[est] = w
        resultado["lecturas_utilizadas"].append({
            "estacion": est, "direccion": dir_, "rol": rol,
            "conviccion": conv, "peso": w,
            "D1xD2xD3": lec.get("D1xD2DXD3") or lec.get("D1xD2xD3") or lec.get("D1xD2DxD3"),
            "state_key": (lec.get("D1xD2xD3") or {}).get("state_key"),
            "accion": lec.get("accion"), "razon": lec.get("razon"),
        })
        if dir_ in ("ALZA", "BAJA"):
            resultado["n_agentes_senal"] += 1
            anti[dir_] += w
            senal_est.add(est)
    resultado["n_agentes_maduros"] = maduros
    resultado["pesos_total"] = pesos

    # --- Confluencia probabilística ------------------------------------
    w_total = anti["ALZA"] + anti["BAJA"]
    P_alza = anti["ALZA"] / w_total if w_total > 0 else 0.0
    P_baja = anti["BAJA"] / w_total if w_total > 0 else 0.0
    if w_total == 0:
        direccion = "NEUTRAL"
        conf_conv = 0.0
    else:
        winner = "ALZA" if P_alza >= P_baja else "BAJA"
        direccion = winner
        conf_conv = round(max(P_alza, P_baja), 4)
    resultado["confluencia"] = {
        "P_ALZA": round(P_alza, 4),
        "P_BAJA": round(P_baja, 4),
        "P_señal": round(resultado["n_agentes_senal"] / maduros, 4) if maduros else 0.0,
        "peso_total_senal": w_total,
        "direccion_confluente": direccion,
        "conviccion_confluente": conf_conv,
    }
    resultado["flujo_neto"] = round(anti["ALZA"] - anti["BAJA"] if w_total else 0.0, 4)

    # --- Contradicción (conflicto entre agentes) ---------------------------
    pp = min(P_alza, P_baja)
    contradictoria = bool(
        w_total > 0 and anti["ALZA"] > 0 and anti["BAJA"] > 0 and
        (pp >= 0.20 or min(anti["ALZA"], anti["BAJA"]) >= 2)
    )
    resultado["señal_contradictoria"] = contradictoria
    resultado["contradicción_detalle"] = (
        f"ALZA={anti['ALZA']} vs BAJA={anti['BAJA']} (peso) | P_alza={P_alza:.2f} "
        f"P_baja={P_baja:.2f}" if contradictoria else None
    )

    # --- Co-ocurrencia con catálogo de confluencias canarias --------------
    resultado["co_ocurrencia_catalogo"] = co_ocurrencias_catalogo(senal_est, confluencias)

    # --- Alerta ------------------------------------------------------------
    resultado["alerta"] = _alerta(resultado)
    return resultado


def _alerta(f: Dict) -> str:
    c = f["confluencia"]
    if f["n_agentes_maduros"] == 0:
        return "Sin agentes maduros en el episodio."
    if c["direccion_confluente"] == "NEUTRAL":
        return "Ninguna dirección con señales: régimen neutro, sin confluencia."
    pr = f["conteo_roles"]
    base = (
        f"Confluencia {c['direccion_confluente']} (P={c['conviccion_confluente']:.0%}, "
        f"señal {f['n_agentes_senal']}/{f['n_agentes_maduros']} agentes; "
        f"precur/d{pr.get('precursor',0)} canario{pr.get('canario',0)} "
        f"confirm{pr.get('confirmador',0)} ruido{pr.get('ruido',0)})."
    )
    if f["señal_contradictoria"]:
        base += " ⚠ Señal contradictoria detectada."
    if f["co_ocurrencia_catalogo"]["n_activas"]:
        base += f" Refuerzo catálogo: {f['co_ocurrencia_catalogo']['n_activas']} confluencia(s) activa(s)."
    return base