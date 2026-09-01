# AUDITORÍA COMPLETA — Cobertura D1/D2/D3 + Triada Zigzag + Estocasticidad

**Auditor:** deepseek/deepseek-v4-flash
**Fecha:** 2026-09-01
**Framework:** López de Prado (Triple Barrier, DSR, CPCV)

---

## HALLAZGO CRÍTICO #1 — `perfil_3d_régimen` es un nombre engañoso

`perfil_3d_régimen` **NO mide las 3 dimensiones D1/D2/D3 del vector de estado.** Mide:
- 3 escalas zigzag: zz25, zz50, zz75
- × 2 regímenes: ALZA, BAJA
- = 6 celdas (no 1,650 combinaciones posibles)

**Dato concreto:** `perfil_3d_régimen` = `{zz25|ALZA, zz25|BAJA, zz50|ALZA, ...}`. El nombre sugiere D1/D2/D3 pero son escalas zigzag. Es un **sesgo de nomenclatura** que puede llevar a conclusiones erróneas.

---

## HALLAZGO CRÍTICO #2 — Los evaluadores NO condicionan por D2/D3

| Evaluador | Condiciona por | No condiciona por |
|:----------|:---------------|:------------------|
| `evaluador_general` | Señal ON/OFF, timing, era | **D1, D2, D3** |
| `evaluador_vav` | Escala ZZ, ALZA/BAJA | **D1, D2, D3** |
| `arnes/medicion` | Next_leg completo | **D1, D2, D3** |

**24 señales usan solo D1** (72%). **7 señales usan D2** — `credit_equity_divergence`, `defensive_rotation_divergence`, `capitulacion_v2`, `euforia_v2`, `vix_crisis_spike_v2`, `neutral_crush_entry`, `neutral_spike_exit`. **2 señales usan D3** — `sv5t_silent_distribution`, `stealth_tail_hedging`. Pero ninguna evaluación mide si esas señales performan DISTINTO cuando D2=CRUSH vs D2=SPIKE vs D2=NEUTRAL.

---

## HALLAZGO CRÍTICO #3 — Evaluación determinística, no estocástica

El first-passage actual:
1. **Camina el precio REAL** (camino histórico real)
2. **Responde**: "esto fue lo que pasó"
3. **No responde**: "cuál es la probabilidad de que pase"

Triple barrier de López de Prado requiere:
- Take-profit → ✅ Implementado (zz25/zz50/zz75)
- Stop-loss → ✅ Implementado (barrera opuesta)  
- **Time-stop** → ❌ **No implementado** (señales que tardan 200b se evalúan igual que las que tardan 5b)
- **Volatility adjusting** → ❌ No implementado

---

## HALLAZGO CRÍTICO #4 — Escalas zigzag fijas, no dinámicas

Cada estado del fact store tiene su PROPIO `e_ret_max` y `e_ret_min`. Por ejemplo, `vix_state=5__4__5` tiene `zz25.e_ret_max=3.2%`. Pero el evaluador usa escalas **fijas** (2.5%, 5.0%, 7.5%) ignorando la información específica del estado. Esto es como usar una misma vara para medir todos los terrenos.

---

## HALLAZGO CRÍTICO #5 — Datos de D2/D3 subutilizados

| Dimensión | Bins | % días | Señales que la usan | Evaluador la mide? |
|:---------:|:----:|:------:|:-------------------|:------------------:|
| D1 | 0-5 | 100% | 33/33 (100%) | ❌ Solo ON/OFF |
| ON/OFF
| D2 | 0-4 | 100% | 7/33 (21%) | ❌ Nunca |
| Nunca
| D3 | 0-4 | 100% | 2/33 (6%) | ❌ Nunca |

El lake TIENE los datos (33 columnas _d1_bin, _d2_bin, _d3_bin para 11 estaciones). Pero ningún evaluador los usa para segmentar resultados.

---

## MAPA DE ARQUITECTURA ACTUAL

```
┌─────────────────────────────────────────────────────────────┐
│                     ECOSISTEMA ACTUAL                          │
│                                                               │
│  ┌──────────────┐    ┌──────────────────────┐                │
│  │ Lake/Pivotes  │───▶│  evaluador_general    │                │
│  │ D1/D2/D3 bins │    │   (solo señal ON/OFF)│                │
│   
│  │ state_keys    │    │  NO condiciona D2/D3  │               
│  │ zz25/50/75  │    └──────────────────────┘                │
│└──────────────┘                             │                │
│          │                                                                                              
│          ▼                                                                                              
│  ┌──────────────────────┐                                                                              
│  │ evaluador_vav         │                                                                              
│  │ zz25/50/75 × ALZA/BAJ│                                                                              │
│  │ No D2/D3              │                                                                              │
│  └──────────────────────┘                                                                              
│                                                               │
│  ┌──────────────────────┐                                                                              
│  │ medicion.py (arnés)    │                                                                              
│  │ next_leg agregado      │                                                                              
│  └──────────────────────┘                                                                              
│                                                               │
│  OUTPUT ACTUAL: métricas AGREGADAS (pierde granularidad)     │
└─────────────────────────────────────────────────────────────┘
```

## MAPA DE ARQUITECTURA IDEAL

```
┌─────────────────────────────────────────────────────────────┐
│                   ECOSISTEMA IDEAL                           │
│                                                               │
│  ┌──────────────┐    ┌───────────────────────────────────┐─ │
│  │ Lake/Pivotes  │───▶│  evaluador_multidimensional      ││
│  │ D1/D2/D3 bins │    │  Condiciona por:                 ││
│  │ state_keys    │    │   ├─ D1: 0..5 (6 niveles)      │││
│  │ zz25/50/75    │    │   ├─ D2: 0..4 (5 niveles)      │││
│  │ fact_stores    │    │   ├─ D3: 0..4 (5 niveles)       ││
│  │ e_ret_max/min  │    │   ├─ Estación: 11               │││
│  └──────────────┘    │   ├─ Escala ZZ: 3 (fija/dinám)   ││
│                          │   └─ Métricas: EV, WR, CI95, N │││
│                          └──────────────────────────────────┘
│                                      │                      │
│                                      ▼                      │
│  ┌─────────────────┐     ┌──────────────────────┘         ││
│  │ Probabilístico    │     │ Trible Barrier completo │      ││
│  │ Monte Carlo por   │     │ Take-profit             │      ││
│  │ estado actual     │     │ Stop-loss              │      ││
│  │ P(cros_up/down)   │     │ ime-stop ✓             │      ││
│  │ P(imeout)         │     │ olatilicy adjust ✓     ││      ││
│  └────────────────────┘     └──────────────────────────┘   │
│                                                               │
│  OUTPUT: tabla de 6 dimensiones (estación×D1×D2×D3×escala)  │
└─────────────────────────────────────────────────────────────┘
```

---

## BLIND SPOTS — INVENTARIO FINAL (7)

| BS | Severidad | Descripción | Datos |
|:--:|:---------:|:------------|:------|
| **A** | 🔴 P0 | Evaluadores no condicionan por D2/D3 | 11 est × 6 D1 × 5 D2 × 5 D3 = **1,650 combinaciones** ignoradas |
| **B** | 🟡 P1 | `perfil_3d_régimen` mal nombrado (no es D1/D2/D3 sino zz25/50/75 × ALZA/BAJA) | Nombre sugiere 3D vector pero mide solo escalas |
| **C** | 🟡 P1 | Evaluación determinística, no probabilística | No hay Monte Carlo, no hay P(éxito \| estado) |
| **D** | 🟡 P1 | Time-stop no implementado en Triple Barrier | Señales lentas se evalúan igual que rápidas |
| E | ⚪P2 | Escalas ZZ fijas (2.5/5.0/7.5) ignoran e_ret_max del fact store | Cada estado tiene su propia volatilidad |
| **F** | 🟡 P1 | D2=CRUSH(0) y D2=SPIKE(4) no evaluados como features | D2=0 ~6% de los días, D2=4 ~3% — no sabemos si hay edge |
| **G** | 🟡 P1 | D3=3,4 (tai_expansion) no separado del resto | Protoocolo §3.3 exige tratar diamantes por separado |

---

## MEJORAS PROPUESTAS

| M# | Descripción | Esfuerzo | Depende de |
|:--:|:------------|:--------:|:-----------|
| **M1** | `evaluador_multidimensional.py` — segmenta por D1×D2×D3×estación×escala | 2-3 hrs | Lake + fact stores |
| **M2** | Time-stop: `mas_barras = ceil(1/scale)` en first-passage | 20 min | `evaluador_general.py` |
| **M3** | Renombrar `perfil_3d_régimen` → `perfil_escala_régimen` | 5 min | `evaluador_vav.py` |
| **M4** | Bootstrap probabilístico por estado: P(cross), P(timeout), t_esperado | 1-2 hrs | M1 |
| **M5** | Escalas dinámicas: leer `e_ret_max/min` del fact store en vez de fijas | 30 min | Fact stores |

---

## VEREDICTO

| Aspecto | Calificación | Explicación |
|:--------|:-----------:|:------------|
| Cobertura D1 | ✅ 100% | 33/33 señales usan D1 correctamente |
| Cobertura D2 | ⚠️ 21% en señales, **0% en evaluadores** | 7 señales usan D2 pero nadie evalúa su impacto |
| Cobertura D3 | ⚠️ 6% en señales, **0% en evaluadores** | 2 señales usan D3, nadie evalúa su impacto |
| Triada zz25/50/75 | ✅ En señales y evaluadores | Correcto como escalas, pero deberían ser dinámicas |
| Estocasticidad | ❌ **0%** | Todo es determinístico. No hay versión probabilística. |
| Time-stop | ❌ **No implementado** | Gap en Triple Barrier |
| Ranking ajustado | ❌ **No implementado** | Sin Bonferroni ni DSR |