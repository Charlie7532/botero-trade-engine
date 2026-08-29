# AUDITORÍA — Evaluador Vela a Vela (calificador forense de señales)

**Auditor:** Claude Opus
**Solicitante:** Juan Andrés (Arquitecto) vía Hermes
**Fecha:** 21-Ago-2026
**Objetivo:** Auditar la corrección conceptual, los sesgos y los errores de un nuevo evaluador de señales antes de escalarlo a 24 señales. El evaluador califica disparos de señales de trading contra pivotes zigzag, sin sesgo de posición.

---

## 1. CONTEXTO — Por qué existe este evaluador

Hemos descubierto que el arnés de medición anterior (`medir_senal.py`) tiene dos sesgos graves:

1. **Sesgo de posición**: mide señales solo en filas de pivotes confirmados (1,590), asumiendo que el trader sabe dónde está el pivote. Ejemplo: `credit_easing_k1` tiene edge +5.19% CON filtro `pivot_type==MIN`, pero −0.48% SIN el filtro (+620% de inflación).
2. **Sesgo de estructura de escala**: medir "favorable" como el retorno hasta el próximo pivote del zigzag viene parcialmente garantizado por la construcción del zigzag (un MAX→MIN siempre es una caída de al menos el umbral).

Este evaluador corrige ambos: dispara en la vela del estado (observable en tiempo real), califica contra un baseline de la misma celda (escala×régimen), y no requiere saber el pivote.

---

## 2. CÓDIGO COMPLETO DEL EVALUADOR (269 líneas)

```python
#!/usr/bin/env python3
"""
EVALUADOR VELA A VELA — Calificador forense de señales (v3)
============================================================
Califica cada disparo en la vela t, sin sesgo de posición:
  - Régimen observable: última pierna CONFIRMADA por escala (sello temporal)
  - Realidad: zig→señal (perdido) + señal→zag (capturado) + MAE intra-tramo
  - Perfil 3D (zz25/zz50/zz75) × régimen, con N_eff
  - Esperanza del fact store JSON por state_key + SORPRESA
  - Forensia F3: falla-de-lectura vs impredecible (techo de mejora)

Principio del tirador: el disparador no sabe el resultado al disparar;
el evaluador ve el blanco completo después. La información observable en t
es la del último pivote ya CONFIRMADO (confirmed_at ≤ t).
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
from medir_senal import SEÑALES, _CERTEZA, cargar_datos

FACT_STORE_DIR = ROOT / "backend/modules/entry_decision/domain/rules"
ESCALAS = {"zz25": 0.025, "zz50": 0.05, "zz75": 0.075}
BLANCOS = {  # aprobados por el arquitecto (20-Ago)
    "euforia": "MAX", "bsi_recovery": "MAX", "pcr_put_panic": "MIN",
    "fg_extreme_greed": "MAX", "credit_equity_divergence": "MAX",
    "credit_easing_k1": "MIN", "fg_extreme_fear": "MIN", "panico_total": "MIN",
    "vvix_entry": "MIN", "capitulacion": "MIN",
}

# ── Zigzag por escala sobre precios SPY (mismo algoritmo del generador) ──
def identificar_zigzag(prices: np.ndarray, thr: float):
    """Retorna array de índices de pivotes; +1 = MIN, -1 = MAX."""
    n = len(prices)
    piv_pos, piv_sign = [], []
    up = True
    last_i, last_v = 0, prices[0]
    for i in range(1, n):
        v = prices[i]
        if up:
            if v > last_v:
                last_i, last_v = i, v
            elif v <= last_v * (1.0 - thr):
                piv_pos.append(last_i); piv_sign.append(-1)
                up, last_i, last_v = False, i, v
        else:
            if v < last_v:
                last_i, last_v = i, v
            elif v >= last_v * (1.0 + thr):
                piv_pos.append(last_i); piv_sign.append(1)
                up, last_i, last_v = True, i, v
    return np.array(piv_pos, dtype=int), np.array(piv_sign, dtype=int)

def régimen_en(t_pos: int, piv_pos: np.ndarray, piv_sign: np.ndarray):
    """Última pierna CONFIRMADA en t_pos.
    Un pivote k queda confirmado cuando aparece el pivote k+1."""
    if len(piv_pos) < 2:
        return "NA", None
    conf_pos = piv_pos[1:]          # confirmación del pivote k = pos del k+1
    conf_idx = piv_pos[:-1]
    ok = conf_pos <= t_pos
    if not ok.any():
        return "NA", None
    last = np.where(ok)[0][-1]
    return ("ALZA" if piv_sign[last] == 1 else "BAJA"), conf_idx[last]

# ── Esperanza del fact store ──
_fs_cache = {}
def esperanza(state_key: str, estación: str, escala: str):
    """Devuelve (ev_net, p_bull) del JSON del fact store para state_key."""
    if estación not in _fs_cache:
        ruta = FACT_STORE_DIR / f"{estación}_fact_store.json"
        if not ruta.exists():
            return None, None
        _fs_cache[estación] = json.loads(ruta.read_text()).get("states", {})
    st = _fs_cache[estación].get(state_key)
    if not st:
        return None, None
    capa = st.get(escala, {})
    return capa.get("ev_net"), capa.get("p_bull")

# ── Evaluador principal ──
def evaluar(señal_nombre: str):
    df, spy = cargar_datos()
    spy_close = spy["close"].astype(float)
    prices = spy_close.values
    spy_idx = spy_close.index

    sig = SEÑALES[señal_nombre](df).astype(bool)
    blanco = BLANCOS.get(señal_nombre, "AMBOS")
    disparos = df[sig]

    zz = {esc: identificar_zigzag(prices, thr) for esc, thr in ESCALAS.items()}

    fichas = []
    for piv_i, row in disparos.iterrows():
        d_piv = row["pivot_date"]
        t0_pos = spy_idx.searchsorted(d_piv)  # momento del disparo: día del estado
        if t0_pos >= len(prices) - 1:
            continue

        for escala, (piv_pos, piv_sign) in zz.items():
            reg0, _ = régimen_en(t0_pos, piv_pos, piv_sign)
            fut = piv_pos[piv_pos > t0_pos]
            if len(fut) == 0:
                continue
            zag_pos = fut[0]
            p_conf, p_zag = prices[t0_pos], prices[zag_pos]
            if p_conf <= 0:
                continue

            capturado = (p_zag - p_conf) / p_conf
            tramo = prices[t0_pos:zag_pos + 1]
            if blanco == "MIN":
                mae = (tramo.min() - p_conf) / p_conf
                mfe = (tramo.max() - p_conf) / p_conf
                favorable = capturado
            else:
                mae = (tramo.max() - p_conf) / p_conf
                mfe = -(tramo.min() - p_conf) / p_conf
                favorable = -capturado

            fichas.append({
                "fecha_disparo": d_piv, "escala": escala, "régimen": reg0,
                "capturado_señal_zag": capturado, "favorable": favorable,
                "mae": mae, "mfe": mfe, "n_pierna_id": int(zag_pos),
            })

    F = pd.DataFrame(fichas)
    if F.empty:
        return {"señal": señal_nombre, "error": "sin disparos evaluables"}

    # ── Baseline por celda: TODOS los pivotes del mismo tipo en quants_obs ──
    tipo_pivote = "MAX" if blanco == "MAX" else ("MIN" if blanco == "MIN" else None)
    baseline_celda = {}
    if tipo_pivote:
        for escala, (piv_pos, piv_sign) in zz.items():
            for _, prow in df.iterrows():
                if prow["pivot_type"] != tipo_pivote:
                    continue
                t_pos = spy_idx.searchsorted(prow["pivot_date"])
                if t_pos >= len(prices) - 1:
                    continue
                reg, _ = régimen_en(t_pos, piv_pos, piv_sign)
                if reg == "NA":
                    continue
                fut = piv_pos[piv_pos > t_pos]
                if len(fut) == 0:
                    continue
                cap = (prices[fut[0]] - prices[t_pos]) / prices[t_pos]
                key = f"{escala}|{reg}"
                baseline_celda.setdefault(key, []).append(-cap if blanco == "MAX" else cap)
        for k in baseline_celda:
            baseline_celda[k] = float(np.mean(baseline_celda[k]))

    # ── Perfil 3D × régimen (con favorable NETO = señal − baseline) ──
    perfil = {}
    for escala in ESCALAS:
        for reg in ("ALZA", "BAJA"):
            sub = F[(F["escala"] == escala) & (F["régimen"] == reg)]
            if sub.empty:
                continue
            n_bruto = len(sub)
            n_eff = sub["n_pierna_id"].nunique()
            base_val = baseline_celda.get(f"{escala}|{reg}", 0.0)
            fav_neto = sub["favorable"] - base_val
            hits = (sub["favorable"] > 0)
            mae_med = float(sub["mae"].mean())
            mfe_med = float(sub["mfe"].mean())
            rr = mfe_med / abs(mae_med) if mae_med != 0 else np.inf
            perfil[f"{escala}|{reg}"] = {
                "n": n_bruto, "n_eff": int(n_eff),
                "fav_bruto": round(float(sub["favorable"].mean()), 4),
                "baseline": round(base_val, 4),
                "fav_neto": round(float(fav_neto.mean()), 4),
                "fav_neto_p5": round(float(fav_neto.quantile(0.05)), 4),
                "fav_neto_p95": round(float(fav_neto.quantile(0.95)), 4),
                "hit_rate": round(float(hits.mean()), 3),
                "rr": round(float(rr), 2) if np.isfinite(rr) else None,
                "mae_medio": round(mae_med, 4),
                "mfe_medio": round(mfe_med, 4),
            }

    # ── Forensia F3 ──
    otras = {n: SEÑALES[n](df).astype(bool) for n in
             ("euforia", "bsi_recovery", "pcr_put_panic") if n != señal_nombre}
    fallas, impredecibles = 0, 0
    for piv_i, row in disparos.iterrows():
        sub = F[(F["fecha_disparo"] == row["pivot_date"]) & (F["escala"] == "zz25")]
        if sub.empty or float(sub["favorable"].iloc[0]) >= 0:
            continue
        hermana = any(o.iloc[max(0, piv_i - 1):piv_i + 2].any() for o in otras.values())
        if hermana:
            fallas += 1
        else:
            impredecibles += 1
    total_fallidos = fallas + impredecibles

    return {
        "señal": señal_nombre, "blanco": blanco,
        "n_disparos": int(len(disparos)),
        "perfil_3d_régimen": perfil,
        "forensia_F3": {
            "disparos_fallidos": total_fallidos,
            "falla_de_lectura": fallas,
            "impredecible": impredecibles,
            "techo_mejora": round(fallas / total_fallidos, 2) if total_fallidos else None,
        },
    }
```

---

## 3. RESULTADOS DEL PILOTO (3 señales)

| Señal | Blanco | Celda | N_eff | NETO | Hit | RR |
|-------|--------|-------|:---:|:---:|:---:|:---:|
| bsi_recovery | MAX | zz25\|ALZA | 173 | +0.30% | 100% | 71x |
| bsi_recovery | MAX | zz25\|BAJA | 107 | +0.54% | 0% | 0.14x |
| bsi_recovery | MAX | zz50\|ALZA | 82 | +1.13% | 100% | 36x |
| pcr_put_panic | MIN | zz25\|BAJA | 26 | +0.99% | 100% | 211x |
| pcr_put_panic | MIN | zz25\|ALZA | 17 | +0.66% | 0% | 0.06x |
| euforia | MAX | zz25\|ALZA | 23 | −0.05% | 100% | 75x |
| euforia | MAX | zz25\|BAJA | 8 | −1.08% | 0% | 0.15x |

---

## 4. DECISIONES DE DISEÑO QUE DEBEN AUDITARSE

### D1: Momento del disparo = día del pivote quants_obs
La señal dispara en `row["pivot_date"]`, que es la fecha del pivote en quants_obs. El trader no sabe en esa fecha que es un pivote — solo conoce el estado D1/D2/D3. **Pregunta: ¿esto reintroduce algún sesgo de posición residual?**

### D2: Régimen = último pivote confirmado
`régimen_en()` usa `conf_pos <= t_pos`, donde conf_pos = posición del pivote k+1. Un pivote k queda confirmado cuando aparece k+1. **Pregunta: ¿la definición de "confirmado" es correcta? ¿Hay look-ahead?**

### D3: Favorable neto = señal − baseline de la misma celda
El baseline se computa sobre TODOS los pivotes del mismo tipo (MIN/MAX) en quants_obs, agrupados por escala×régimen. **Pregunta: ¿el baseline está correctamente condicionado? ¿Debería excluir los pivotes de la señal misma?**

### D4: N_eff = pivotes zigzag únicos
`n_eff = sub["n_pierna_id"].nunique()` — los disparos que caen en la misma pierna zigzag no se cuentan como independientes. **Pregunta: ¿esta definición de N_eff es correcta?**

### D5: Hit/miss y RR
Hit = favorable > 0. RR = MFE / |MAE|. **Pregunta: ¿el RR con MAE casi cero (71x, 211x) es informativo o engañoso?**

### D6: Forensia F3
Un disparo fallido es "falla de lectura" si alguna señal hermana disparó en ±1 pivote; si no, "impredecible". **Pregunta: ¿esta definición captura correctamente el concepto de "información observable no usada"?**

---

## 5. PREGUNTAS ESPECÍFICAS DE SESGO

1. **Look-ahead en el régimen**: ¿`régimen_en()` usa información futura? El pivote k+1 (que confirma k) puede estar en el futuro respecto a t_pos.
2. **Contaminación del baseline**: el baseline incluye TODOS los pivotes del tipo correcto, incluyendo los de la señal misma. ¿Esto sesga el favorable neto hacia cero?
3. **Zigzag independiente vs quants_obs**: el evaluador computa su propio zigzag sobre precios SPY, pero quants_obs tiene su propio zigzag (con umbrales posiblemente distintos). ¿La discrepancia entre ambos zigzags introduce error de medición?
4. **Supervivencia del zigzag**: el último pivote del zigzag nunca queda confirmado (no hay k+1). ¿Esto sesga el régimen en las últimas barras?
5. **Estructura de escala**: ¿el favorable neto realmente elimina el sesgo de estructura, o queda residuo porque el baseline también está construido con el mismo zigzag?

---

## 6. FORMATO DE RESPUESTA ESPERADO

```markdown
# AUDITORÍA — Evaluador Vela a Vela

## 1. Veredicto general
[APROBADO / APROBADO CON RESERVAS / RECHAZADO]

## 2. Hallazgos por decisión de diseño
| Decisión | Veredicto | Severidad | Evidencia |

## 3. Respuestas a las 5 preguntas de sesgo
1. ...
2. ...

## 4. Errores encontrados (si alguno)
[con línea de código y corrección propuesta]

## 5. Recomendaciones antes de escalar
[lista priorizada]
```

---
**Firma del solicitante:** deepseek/deepseek-v4-pro (Hermes) · 21-Ago-2026
