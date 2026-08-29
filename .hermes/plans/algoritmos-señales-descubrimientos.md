# ALGORITMOS, SEÑALES Y DESCUBRIMIENTOS — Lo que construimos exitosamente
## Botero Trade — Auditoría de Código Python (17-19 Ago 2026)

---

## 1. ALGORITMOS CONSTRUIDOS

### 1.1 medir_senal.py — Arnés de Medición Estándar (1020 líneas)
**Qué hace:** Mide cualquier señal de trading con el MISMO estándar matemático.
**Arquitectura:** Decorador `@_registrar` + funciones puras que retornan `pd.Series(bool)`.
**Por qué es exitoso:** Eliminó "cada agente reinventa el método". 20 señales, 1 estándar.

```
@_registrar("bsi_washed_out",
    validacion="VALIDATED (Grade A)", n_min=58, dsr=None,
    fuente="operational-spec: BREADTH_WASHED_OUT, +2.6% 20d, WR 69%")
def _bsi_washed_out(df):
    """BSI en BREADTH_WASHED_OUT."""
    return df["bsi_sk"].str.split("__").str[0] == "BREADTH_WASHED_OUT"
```

**Métricas que calcula (estándar):**
- Distribución completa (P5/P25/P50/P75/P95)
- Edge ofensivo + Edge defensivo
- Tríada zigzag (zz25/zz50/zz75 + cascade rate)
- Anticipación temporal (días antes del pivote)
- Capture ratio por escala (zz25/zz50/zz75)
- Puntería + offset de entrada (±1 barra)
- Estabilidad por década
- D2×D3 desglose con bootstrap CI95
- Precursores de crash (lookback [T0-3, T0+2])

---

### 1.2 forense_precursores.py — Forense de Precursores de Crash (221 líneas)
**Qué hace:** Identifica qué estados del vector METAR (D1×D2×D3) anteceden a crashes.
**Métrica clave:** `lift = P(state | LOSER) / P(state | WINNER)`
**Resultado:** 86 precursores encontrados, 61.6% con N_lose 3-4 (rareza = riqueza).

```
🔴 PRECURSORES DE CRASH (lift ≥ 1.5, N_lose ≥ 3):
  lift=11.25  sv5_turbulence.D2 = FAST_SPIKE_3D
  lift= 6.43  pcr.D1×D2 = NEUTRAL_PCR×STABLE_CONTINUATION_3D
  lift= 5.00  credit.D3 = VOL_ACCELERATING_EXPANSION
```

---

### 1.3 query_graphify.py — Navegación del Grafo de Conocimiento
**Qué hace:** Consulta el grafo de dependencias del proyecto (14,030 nodos, 23,828 edges).
**Comandos:** `stats`, `hubs`, `search`, `depends`, `interdeps`, `path`.

---

### 1.4 Cascade Conviction (fórmula validada, no construida de cero)
```
cascade_conviction_50 = 0.66 × z(d1_bear_5) + 0.34 × z(|prev_leg_return|)
```
**Validación:** walk-forward OOS, 5 estaciones Grupo A óptimas, IC +0.4147.

---

### 1.5 B1 Fix — N=0 vote attenuation
```python
# convergence_compositor.py:540
vote = d1_directional_vote(state_key) * reliability_factor(n)
```
**Bug:** Estados sin evidencia (N=0) votaban con plena convicción.
**Fix:** 1 línea. Cascade sano post-fix: +0.4087.

---

## 2. SEÑALES DESCUBIERTAS Y VALIDADAS

### 2.1 Las 7 Señales Estrella (GRADE A)

| # | Señal | N | Forward | WR | CI95 | Perfil |
|---|---|---|---|---|---|---|
| 1 | **credit_easing_k1** | 112 | **+5.19%** | **93.8%** | [+4.41%, +6.01%] | ⚔️ Ofensiva pura |
| 2 | **pcr_put_panic** | 70 | +2.70% | 71.4% | [+1.13%, +4.24%] | ⚔️ Ofensiva |
| 3 | **vvix_entry** | 91 | +1.70% | 62.6% | [+0.19%, +3.24%] | ⚔️ Ofensiva |
| 4 | **fg_extreme_fear** | 54 | +1.58% | 68.5% | — | 🛡️ Defensiva |
| 5 | **bsi_washed_out** | 161 | +1.42% | 65.8% | [+0.25%, +2.55%] | 🛡️⚔️ Dual |
| 6 | **capitulacion** | 82 | +1.40% | 65.9% | — | 🛡️ Defensiva pura |
| 7 | **euforia** | 41 | **-2.99%** | **14.6%** | [-3.98%, -1.81%] | 🔻 Techo (EXIT) |

### 2.2 Señales de EXIT descubiertas

| # | Señal | Edge | WR | CI95 | Por qué funciona |
|---|---|---|---|---|---|
| 1 | **bsi_recovery** | -1.63% | 29.0% | [-2.17%, -1.10%] | BSI sale de BREADTH_WASHED_OUT → fin de pierna alcista |
| 2 | **euforia** | -2.99% | 14.6% | [-3.98%, -1.81%] | Complacencia extrema → techo del mercado |
| 3 | **fg_extreme_greed** | -1.92% | 19.4% | — | Codicia extrema → techo |

### 2.3 Señales duplicadas detectadas (misma señal, diferente nombre)
- `pcr_panic_exit` ≡ `pcr_put_panic` (edge +2.70%, misma definición)
- `credit_stress_exit` ≡ `credit_stress` (edge +1.00%, misma definición)

---

## 3. DESCUBRIMIENTOS

### 3.1 Edge Defensivo > Edge Ofensivo

**Descubrimiento:** Cambiar la pregunta de "¿cuánto gana?" a "¿cuánto dejo de perder?" revela que las mejores señales estaban invisibilizadas.

| Señal | Edge Ofensivo | Edge Defensivo | × Baseline |
|-------|---------------|----------------|------------|
| **capitulacion** | +1.40% (no significativo) | **6.86%** | **3.6×** |
| **fg_extreme_fear** | +1.58% (no significativo) | **5.61%** | **2.9×** |
| **bsi_washed_out** | +1.42% (significativo) | **5.58%** | **3.1×** |

---

### 3.2 Precursores Universales de Crash

**Descubrimiento:** `credit.D2=ACCELERATING_UP_3D` es el precursor más universal — aparece en 5 de 6 tipos de señales, lift medio 4.1×.

| # | Precursor | Señales | Lift | Interpretación |
|---|---|---|---|---|
| 1 | `credit.D2=ACCEL_UP` | 5/6 | 4.1× | Crédito apretando = peligro |
| 2 | `sv5.LOW×DECEL_DOWN` | 4/6 | 5.2× | Calma rompiéndose |
| 3 | `skew.D3=VOL_EXPANSION` | 4/6 | 2.5× | Volatilidad expandiéndose |

---

### 3.3 Falsas Alarmas No Son El Enemigo

**Descubrimiento:** Para TODAS las señales con WR > 50%, el costo de NO actuar (comerse el crash) supera al costo de actuar y equivocarse (falsa alarma).

| Señal | Costo Actuar | Costo NO Actuar | Ratio |
|-------|-------------|-----------------|-------|
| credit_easing_k1 | 0.37% | 5.66% | **15.3×** |
| capitulacion | 2.36% | 9.22% | **3.9×** |
| fg_extreme_fear | 1.80% | 7.40% | **4.1×** |

---

### 3.4 FG Es Modulador, No Señal

**Descubrimiento:** FG no debe evaluarse como señal de entrada/salida. Es un termómetro del sentimiento del mercado — modula la probabilidad del régimen, no genera órdenes.

```
Error:      "FG: EV -8.9%, sin señal, retirar"
Corrección: "FG EXTREME_FEAR = régimen invierno → comprar tiene más peso"
```

---

### 3.5 Las Señales de Pánico Son ENTRY, No EXIT

**Descubrimiento:** vix_crisis_spike (+0.75%), credit_stress (+1.00%), pcr_panic_exit (+2.70%) tienen edge POSITIVO — son señales de "comprar miedo" (ENTRY), no de salir (EXIT).

---

### 3.6 Cascade Intacto — Walk-Forward Refuta Reducción

**Descubrimiento:** La reducción del Grupo A (VIX+BSI) mejora IS (+0.018) pero degrada OOS (-0.012). Firma de overfitting. Las 5 estaciones son óptimas.

---

### 3.7 Tríada Zigzag Como Métrica Universal

**Descubrimiento:** Medir con horizontes fijos en días (5/10/20/60) es arbitrario. La tríada zigzag (zz25/zz50/zz75 + cascade rate + duración) mide lo que realmente importa: la estructura natural del mercado.

---

## 4. RESUMEN: QUÉ NOS LLEVAMOS

### Algoritmos (4)
1. `medir_senal.py` — arnés de medición estándar
2. `forense_precursores.py` — forense de crash
3. `query_graphify.py` — navegación del grafo
4. Cascade conviction (fórmula validada)

### Señales (20)
- 12 ENTRY validadas (7 GRADE A)
- 3 EXIT validadas
- 3 propuestas EXIT (pendientes)
- 2 duplicadas/retiradas

### Descubrimientos (7)
1. Edge Defensivo > Edge Ofensivo
2. Precursores universales de crash
3. Falsas alarmas no son el enemigo
4. FG es modulador, no señal
5. Señales de pánico son ENTRY, no EXIT
6. Walk-forward refuta reducción del cascade
7. Tríada zigzag es la métrica correcta

### Métricas de desempeño del equipo
- 5 bugs encontrados en código propio
- 88/88 métricas verificadas post-corrección (cero regresiones)
- 2 scope creeps detectados y rechazados
- 3 correcciones de usuario incorporadas al sistema

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 19-Ago-2026