"""
_agente_base.py — lógica compartida de los 11 agentes de estación METAR.

Cada agente es un "mundo" definido por comite_metar/perfiles/perfil_estaciones.json.
En cada punto de decisión t el agente:

  1. Lee el state_key de SU estación en t — decodificado por `estado_en`
     (garantizado sin lookahead; solo columnas <= t).
  2. Decodifica D1xD2xD3 con sus labels canónicos (D1) y universales (D2/D3),
     aplica SU dirección física (ojo: CREDIT y YIELD tienen bin 0 = estrés/inversión).
  3. Interpreta el sentido de la combinación (perfil.sentido_combinaciones_D1D2D3).
  4. Emite SU lectura mediante `interpretar()`:
       - rol_precognitivo : precursor / canario / confirmador / ruido
       - direccion_anticipada (SPY) con su ancla de validación
       - convicción + riesgo (tier de overflow)
       - decisión propuesta (ENTRADA/EXIT/COBERTURA/OBSERVAR)
  5. Respalda con evidencia del catálogo homogenizado (posición en ranking, EV
     continuo, N limpio, timing) — no inventa números; los extrae de
     evaluacion_generalizada_lake.json + ranking_maestro.json.

«La verdad habla»: cada lectura se confronta contra el catálogo; si no hay edge
que la respalde, la convicción baja (dato mata relato).

Fase 2: este es el "esqueleto LLM". `interpretar` es el punto de anclaje donde
un LLM (con el CUESTIONARIO del agente) narra la lectura en el idioma del mundo.
Por defecto hay una regla determinista reproducible que YA decodifica y emite el
JSON canónico — así la fase es verificable sin gasto de LLM.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # /root/botero-trade

import pandas as pd

from comite_metar.scripts import common
from comite_metar.scripts import estado_en as ee
from comite_metar.scripts import first_passage as fp


# ---------------------------------------------------------------------------
# Dirección anticipada de SPY por estación (+1 alcista / -1 bajista / 0 neutra)
# a partir de D1/D2/D3 + overflow. Basada en perfil.direccion_fisica y en el
# sentido de combinaciones (contrarian en extremo).
# ---------------------------------------------------------------------------
def _direccion_spy(estacion: str, d1: int, d2: int, d3: int,
                   overflow_top: bool) -> int:
    high = (d1 in (4, 5)) or overflow_top
    low = d1 in (0, 1)
    if estacion in ("vix", "vvix", "pcr", "sv5_turbulence", "skew"):
        # valor alto = peor; extremo alto = riesgo bajista (salvo contrarian)
        if overflow_top:
            return -1
        if high:
            return -1
        if low:
            return +1 if d3 <= 2 else -1                 # complacencia+vol=distribución
        return 0
    if estacion == "fg":                                 # contrarian en extremo
        if d1 == 0:
            return +1                                    # miedo extremo -> suelo
        if d1 == 5 or overflow_top:
            return -1                                    # euforia -> techo
        return +1 if d1 in (1, 2) else -1
    if estacion == "credit":                             # bin 0 = estrés (INVERTIDO)
        if d1 in (0, 1):
            return -1
        if d1 in (4, 5) or overflow_top:
            return +1
        return 0
    if estacion == "yield_curve":                        # régimen fondo, sin timing
        return -1 if (d1 == 0 and d2 >= 4) else (+1 if d1 >= 2 else 0)
    if estacion == "rotation":
        return -1 if d1 in (0, 1) else (+1 if d1 in (4, 5) else 0)
    if estacion == "dxy":
        return +1 if d1 in (0, 1) else (-1 if high else 0)
    if estacion == "bsi":                                # confirmador de la salud
        if d1 in (4, 5):
            return +1
        if d1 == 0:
            return +1                                    # washed out -> posible suelo
        return +1 if d2 >= 3 else -1
    return 0


def _riesgo_tier(estado: Dict) -> Dict[str, int]:
    return {dim: (estado["overflow"][dim]["tier"] or 0) for dim in ("d1", "d2", "d3")}


def _nivel_extremo(estado: Dict) -> str:
    d1 = estado["bins"]["d1"]
    ovf = max((v["tier"] or 0) for v in estado["overflow"].values())
    if ovf >= 3:
        return f"BLOW-OFF (T{ovf})"
    if d1 in (0, 5):
        return "EXTREMO(±2σ)"
    if d1 in (1, 4):
        return "ELEVADO(±1σ-2σ)"
    return "NEUTRAL"


_TIPOS_DIR = {1: "ALZA", -1: "BAJA", 0: "NEUTRAL"}


class Agente:
    """Agente de una estación METAR. Lee SOLO su estación en t (sin lookahead)."""

    def __init__(self, estacion: str, perfil: Dict,
                 lake: Optional[pd.DataFrame] = None,
                 ranking: Optional[List[Dict]] = None,
                 senales: Optional[Dict] = None,
                 canarios: Optional[List[Dict]] = None):
        self.estacion = estacion
        self.perfil = perfil
        self.df = lake if lake is not None else common.cargar_lake()
        self.ranking = ranking if ranking is not None else common.cargar_ranking()["ranking"]
        self.senales = senales if senales is not None else common.cargar_catalogo()
        cc = common.cargar_confluencias()
        self.canarios = canarios if canarios is not None else cc.get("confluencias", [])

    # -- evidencia del catálogo para esta estación -------------------------
    def _evidencia(self) -> List[Dict]:
        evi = []
        for s in common.señales_de_estacion(self.estacion):
            rk = next((r for r in self.ranking if r["senal"] == s), None)
            if not rk:
                continue
            p = rk.get("poblacion") or {}
            rl = rk.get("rendimiento_lake") or {}
            evi.append({
                "senal": s,
                "tipo": rk.get("tipo"),
                "blanco": rk.get("blanco"),
                "inception": rk.get("inception"),
                "role": rk.get("rol_operacional"),
                "score_compuesto": rk.get("score_compuesto"),
                "p_BH": rk.get("p_BH"),
                "significativo_BH": rk.get("significativo_BH"),
                "p_bonferroni": rk.get("p_bonferroni"),
                "p_value_raw": rk.get("p_value_raw"),
                "ev_lake": rl.get("ev_optimo"),
                "hit_lake": rl.get("hit_rate_optimo"),
                "N_lake": p.get("n_episodios"),
                "n_indep": p.get("n_indep"),
                "tier_rareza": p.get("tier_rareza"),
                "fire_rate_pct": p.get("fire_rate_pct"),
                "es_diamante": p.get("es_diamante"),
                "timing": rk.get("timing"),
            })
        return evi

    # -- interpretación (regla determinista reproducible) -------------------
    def interpretar(self, estado: Dict) -> Dict:
        d1, d2, d3 = estado["bins"]["d1"], estado["bins"]["d2"], estado["bins"]["d3"]
        overflow = _riesgo_tier(estado)
        ovf_max = max(overflow.values()) if overflow else 0
        dir_spy = _direccion_spy(self.estacion, d1, d2, d3, ovf_max >= 1)
        rol_fijo = self.perfil.get("rol")
        extremo = (d1 in (0, 5)) or ovf_max >= 1
        elevado = d1 in (1, 4)

        evi = self._evidencia()

        if extremo:
            if rol_fijo in ("precursor", "precursor_eventos_extremos"):
                rol_pre = "precursor"
            elif rol_fijo == "exageracion_fat_tail":
                rol_pre = "canario"          # termómetro que revierte
            elif rol_fijo == "confirmador":
                rol_pre = "confirmador"
            else:
                rol_pre = "régimen"
        elif elevado:
            rol_pre = "canario"
        else:
            rol_pre = "ruido"

        evi_ord = sorted(evi, key=lambda e: -(e["score_compuesto"] or -9e9)) if evi else []
        strongest = evi_ord[0] if evi_ord else None

        # Convicción puramente física causal (D1xD2xD3 + overflow en t, sin lookahead de ranking futuro)
        if rol_pre == "ruido" or dir_spy == 0:
            conviccion, accion = "BAJA", "OBSERVAR"
        elif ovf_max >= 2 or (d1 in (0, 5) and ovf_max >= 1) or (d1 in (0, 5) and (d2 in (0, 4) or d3 in (0, 4))):
            conviccion = "ALTA"
            accion = "COBERTURA" if dir_spy < 0 else "ENTRADA"
        elif extremo:
            conviccion = "MEDIA"
            accion = "COBERTURA" if dir_spy < 0 else "ENTRADA"
        elif elevado:
            conviccion = "BAJA"
            accion = "OBSERVAR"
        else:
            conviccion = "BAJA"
            accion = "OBSERVAR"

        tier = max(overflow.get("d1", 0), 1 if extremo else 0)

        return {
            "estacion": self.estacion,
            "mundo": self.perfil["mundo"],
            "rol_ancla": rol_fijo,
            "ancla_validacion": self.perfil["ancla_validacion"],
            "direccion_fisica": self.perfil["direccion_fisica"],
            "D1xD2xD3": {
                "D1": estado["labels"]["D1"],
                "D2": estado["labels"]["D2"],
                "D3": estado["labels"]["D3"],
                "bins": estado["bins"],
                "state_key": estado["state_key"],
            },
            "rareza": _nivel_extremo(estado),
            "overflow_tiers": overflow,
            "direccion_anticipada_spy": _TIPOS_DIR[dir_spy],
            "rol_precognitivo": rol_pre,
            "conviccion": conviccion,
            "riesgo_tier": tier,
            "accion": accion,
            "razon": self._resumen(estado, rol_pre, strongest),
            "sentido_perfil": self.perfil.get("sentido_combinaciones_D1D2D3"),
            "canario_perfil": self.perfil.get("canario"),
            "evidencia": evi_ord,
        }

    def _resumen(self, estado, rol_pre, strongest=None) -> str:
        d1 = estado["labels"]["D1"]
        d2 = estado["labels"]["D2"]
        d3 = estado["labels"]["D3"]
        base = f"{d1} | {d2} | {d3} -> {rol_pre} (dir física: {self.perfil['direccion_fisica']})"
        if strongest:
            base += (f" | respaldo: {strongest['senal']} score={strongest['score_compuesto']} "
                     f"evlake={strongest['ev_lake']} N={strongest['N_lake']} "
                     f"sigBH={strongest['significativo_BH']}")
        return base

    def _blanco_dom(self) -> Optional[Dict]:
        evi = self._evidencia()
        if not evi:
            return None
        e = sorted(evi, key=lambda x: -(x["score_compuesto"] or 0))[0]
        return {"blanco": e["blanco"] or "MIN", "scale": 1.5, "max_horizon": 80}

    # -- API pública: lectura de un punto de decisión -----------------------
    def leer(self, t: int, episodio: Optional[Dict] = None) -> Dict:
        estado = ee.estado_en(self.df, t, perfiles=[self.perfil],
                              estaciones=[self.estacion])[self.estacion]
        if estado["pre_inception"]:
            return {
                "estacion": self.estacion, "t": t, "fecha": estado.get("tiempo"),
                "pre_inception": True, "maduro": False,
                "lectura": None, "primer_passage": None, "episodio": episodio,
            }
        interp = self.interpretar(estado)
        b = self._blanco_dom()
        fp_r = None
        if b:
            fp_r = fp.first_passage(self.df, t, blanco=b["blanco"],
                                    scale_units=b["scale"], atr_span=14,
                                    max_horizon=b["max_horizon"])
        return {
            "estacion": self.estacion, "t": t, "fecha": str(self.df.index[t]),
            "pre_inception": False, "maduro": True,
            "estado": estado,
            "lectura": interp,
            "primer_passage": fp_r,
            "episodio": episodio,
        }

    # -- cuestionario canónico (para el LLM real en la fase de ejecución) --
    @property
    def CUESTIONARIO(self) -> str:
        return (
            f"[Agente {self.estacion.upper()} - {self.perfil['mundo']}]\n"
            f"Rol: {self.perfil['rol']}. Ancla: {self.perfil['ancla_validacion']}.\n"
            f"1) ¿Qué D1xD2xD3 observas y qué significa en tu mundo?\n"
            f"2) ¿Pre-cursor / canario (~1-2 velas) / confirmador (en/tras pivote) / ruido?\n"
            f"3) ¿Probarías entrada/exit? Convición (alta/media/baja) y riesgo.\n"
            f"4) ¿Qué evidencia del catálogo respalda tu lectura (ranking, EV continuo, timing)?\n"
        )