# AUDITORÍA — Cobertura de Métricas en Evaluadores (v1 + v2)

**Auditor:** deepseek/deepseek-v4-flash
**Objetivo:** Verificar que las 5 categorías de métricas están cubiertas por los evaluadores, identificar puntos ciegos, y proponer enriquecimiento.

---

## 1. PERFIL DE EPISODIOS

| Métrica | ¿En v1? | ¿En v2? | Estado |
|:--------|:-------:|:-------:|:-------|
| `n_episodios` (episodios únicos de-clustered) | ❌ v1 mide pivotes individuales | ✅ `poblacion.n_episodios` | ✅ |
| `n_barras_totales` (barras donde señal=True) | ❌ | ✅ `poblacion.total_barras_activas` | ✅ |
| `duracion_media/mediana/p90` (barras por episodio) | ❌ | ✅ `poblacion.duracion_episodio` | ✅ |
| `fire_rate_pct` (% de barras con señal activa) | ❌ | ✅ `poblacion.fire_rate_pct` | ✅ |
| `cadencia` (1 episodio cada N barras) | ❌ | ✅ `poblacion.cadencia_1_en_n_barras` | ✅ |

**Veredicto: ✅ CUBIERTO por v2. v1 no aplica (mide pivotes, no episodios).**

---

## 2. FIRST-PASSAGE POR ESCALA

| Métrica | ¿En v1? | ¿En v2? | Estado |
|:--------|:-------:|:-------:|:-------|
| `hit_rate` (% que cruzó primero el umbral favorable) | ✅ `perfil.hit_rate` | ✅ `escalas_zigzag.hit_rate` | ✅ |
| `EV` (retorno medio favorable) | ✅ `perfil.fav_media` | ✅ `escalas_zigzag.ev` | ✅ |
| `MAE_medio/p10` (dolor máximo intra-tramo) | ⚠️ `mae_medio` solo | ⚠️ `mae_medio`, `mae_p90` (no p10) | ❌ **Falta MAE_p10** |
| `MFE_medio/p90` (ganancia máxima) | ✅ `mfe_medio` | ✅ `mfe_medio`, `mfe_p90` | ✅ |
| `bars_medio` (velas hasta resolución) | ✅ `bars_medio` | ✅ `bars_medio` | ✅ |
| `profit_factor` (Σwins / \|Σlosses\|) | ✅ `profit_factor` | ✅ `profit_factor` | ✅ |
| `baseline` (mismas métricas sobre señal=False) | ✅ `baseline_hit`, `baseline_fav` | ✅ `baseline_hit`, `baseline_ev` | ✅ |

**Veredicto: ⚠️ 1 gap: MAE_p10 no existe en ningún evaluador (solo MAE_p90).**

---

## 3. TIMING VS PIVOTES ZZ

| Métrica | ¿En v1? | ¿En v2? | Estado |
|:--------|:-------:|:-------:|:-------|
| Distribución en 6 slots canónicos | ✅ `timing_slots.counts` | ✅ `timing_canonico.counts` | ✅ |
| `pct_en_rango` (% dentro de ±2 barras de pivote) | ✅ `timing_slots.pct_en_rango` | ✅ `timing_canonico.pct_en_rango` | ✅ |
| `delta_medio` (distancia media al pivote) | ❌ No existe | ❌ No existe | ❌ **Falta** |
| Desglose ANTICIPADORA/COINCIDENTE/CONFIRMADORA | ✅ `timing_slots.pct_anticipada/exacta/retrasada` | ✅ `timing_canonico.pct_anticipada/exacta/retrasada` | ✅ |
| Rendimiento por slot (hit/EV por slot) | ❌ No existe | ✅ `rendimiento_por_slot` | ✅ **solo en v2** |

**Veredicto: ⚠️ 1 gap: `delta_medio` (distancia media al pivote más cercano) no existe. Sería útil para cuantificar anticipación.**

---

## 4. RETORNO CONDICIONAL AL EPISODIO

| Métrica | ¿En v1? | ¿En v2? | Estado |
|:--------|:-------:|:-------:|:-------|
| EV del episodio: retorno acumulado `spy_ret_1d` desde first_bar hasta last_bar | ❌ No existe | ❌ No existe | 🔴 **FALTA CRÍTICA** |
| EV post-episodio: retorno desde last_bar hasta siguiente cambio de estado | ❌ No existe | ❌ No existe | 🔴 **FALTA CRÍTICA** |

**Veredicto: 🔴 2 gaps críticos. Ningún evaluador mide el retorno acumulado del episodio completo ni el retorno post-episodio. Esto es información valiosa para saber si el mercado se recupera o sigue cayendo después de la señal.**

---

## 5. FRECUENCIA COMO FEATURE

| Métrica | ¿En v1? | ¿En v2? | Estado |
|:--------|:-------:|:-------:|:-------|
| `una_entre_N` (1 disparo cada N barras) | ❌ | ✅ `cadencia_1_en_n_barras` | ✅ |
| Clasificación: N > 100 → diamante | ❌ | ⚠️ `es_diamante` (n_episodios < 21, no N > 100) | ⚠️ **Parámetro distinto** |
| Clasificación: N < 10 → señal de fondo | ❌ | ❌ No existe | ❌ **Falta** |

**Veredicto: ⚠️ La clasificación de rareza usa umbral distinto al que propones. `es_diamante` usa n_episodios < 21, no cadencia > 100. Además falta señal de "fondo" (N < 10).**

---

## 6. HALLAZGOS ADICIONALES — Puntos Ciegos Transversales

### PC-1: No hay EV condicional al episodio completo
**Impacto:** Alto. No sabemos si durante el episodio la señal acumula ganancia o pérdida, ni qué pasa después.

### PC-2: MAE_p10 no existe en ningún evaluador
**Impacto:** Bajo. MAE_medio y MAE_p90 existen, pero no el percentil 10 (dolor extremo).

### PC-3: `rendimiento_por_slot` solo en zz25
**Ubicación:** `evaluador_general.py` L360-383. El rendimiento desglosado por slot solo se calcula para zz25. zz50 y zz75 no tienen desglose por timing.

### PC-4: v1 y v2 producen JSON con esquemas distintos
**Impacto:** Alto para agentes. Un agente que lee `evaluacion_vela_a_vela_v7_final.json` (v1) encuentra keys como `perfil_3d_régimen`. El que lee `evaluador_general.py` (v2) encuentra `escalas_zigzag`. Son los mismos datos con nombres distintos. No hay un estándar unificado.

### PC-5: No hay métrica de certeza/confiabilidad agregada
**Impacto:** Medio. Hay `confidence_tier` por celda en v1, y `tier_rareza` por población en v2. Pero no hay un score compuesto que combine: N, p-value, OOS decay, INDEP, y rareza en una sola métrica de confianza.

---

## TABLA DE CORRECCIONES REQUERIDAS

| # | Prioridad | Gap | Dónde agregar | Esfuerzo |
|:-:|:---------:|:----|:--------------|:---------|
| **1** | 🔴 P0 | EV del episodio (retorno acumulado first_bar→last_bar) | `evaluador_general.py` | 10 min |
| **2** | 🔴 P0 | EV post-episodio (retorno last_bar→siguiente cambio) | `evaluador_general.py` | 10 min |
| **3** | 🟡 P1 | MAE_p10 en first-passage | `evaluador_general.py` + `evaluador_vela_a_vela.py` | 5 min |
| **4** | 🟡 P1 | `rendimiento_por_slot` para zz50 y zz75 (no solo zz25) | `evaluador_general.py` | 15 min |
| **5** | 🟡 P1 | `delta_medio` (distancia media al pivote más cercano) | `arnes/timing.py` o evaluadores | 5 min |
| **6** | 🟡 P1 | Clasificación frecuencia: señal de "fondo" (N < 10) | `evaluador_general.py` | 3 min |
| **7** | ⚪ P2 | Unificar esquema JSON entre v1 y v2 | Ambos evaluadores | 30 min |
| **8** | ⚪ P2 | Score compuesto de confiabilidad (N + p-val + OOS + INDEP + rareza) | Nuevo módulo `arnes/confianza.py` | 20 min |

---

## ARQUITECTURA PROPUESTA PARA ALMACENAMIENTO E INTERPRETACIÓN

### Recolección
```
evaluador_general.py (v2) → JSON por señal (individual)
                          → JSON consolidado (todas las señales)
evaluador_vela_a_vela.py (v1) → evaluacion_vela_a_vela_v7_final.json
```

### Almacenamiento
```
data/research/signals/
├── evaluacion_vela_a_vela_v7_final.json   ← v1 (pivotes, 33+ señales)
├── evaluacion_general_v2.json              ← v2 (continuo, episodios, timing)
├── medicion_*.json                         ← individual por señal (v1)
└── validacion_oos_catalogo_v7.json         ← OOS walk-forward
```

### Interpretación para agentes
Cada señal debe tener un resumen de una línea con:
- **N** (robustez estadística)
- **Edge** (neto OOS si existe, o IS)
- **Confianza** (NÚCLEO | CONTRIBUYENTE | PENDIENTE | DIAMANTE)
- **Gate de régimen** (ALZA/BAJA/BOTH)
- **Horizonte** (táctico ~8b | intermedio ~30b | estructural ~44b)
- **Timing** (anticipadora/exacta/confirmadora)

Esto permitiría a cualquier agente —humano o AI— interpretar la señal sin leer el JSON completo.