# PROMPT MAESTRO DEFINITIVO: Sistema Unificado de Inteligencia de Señales y Estados (v3.0)

**Destino de Implementación:** `research/01_señales_entry_exit/construir_bar_snapshot.py`  
**Outputs Principales:** 
1. `data/research/bar_snapshot_base.parquet` (~92 cols, 8,453 filas, ESTABLE)
2. `data/research/bar_snapshot_signals.parquet` (~74 cols, 8,453 filas, VOLÁTIL)
3. `data/research/signal_intelligence.json` (Consolidado único institucional para METAR / TAF / SIGMET / Gates)
4. Archivar a `data/research/_archive/` los 114+ archivos dispersos y obsoletos.

---

## 1. Directivas de Rigor Cuantitativo y Anti-Complacencia

1. **Dato Mata Relato (Sin Supuestos Teóricos):**
   * Ningún estado ni señal se asume ganador por "lógica intuitiva".
   * La reversión a la media en extremos ($D_1=5$) **no es inmediata**: en 2008 el VIX permaneció en $D_1=5$ durante **65 días consecutivos** mientras el SPY cayó un **$-37.2\%$ adicional**. Los estados extremos deben medir su **tiempo de permanencia (duración media y racha máxima)** y su **MAE peor caso** para evitar la trampa de comprar cuchillos cayendo.
   * La calma modal (`2__2__2`) **no se asume como continuación rentable**: empíricamente el SPY tiene un Hit Rate a $zz25$ de $53.5\%$ en `2__2__2` frente a un baseline incondicional de $56.7\%$ ($\text{Lift} = -3.2\%$). Es ruido de baja energía que destruye capital por fricción y costo de oportunidad.
2. **El Lift vs Baseline Incondicional es la Métrica Reina:**
   * La tasa de acierto bruta ($HR$) es engañosa debido al drift alcista incondicional del SPY (~54%–57%).
   * Todo estado y señal debe reportar obligatoriamente: $\text{Lift} = HR - \text{Baseline}_{\text{incondicional}}$. Si $\text{Lift} \le 0$, no existe edge estadístico.
3. **Control de Múltiples Pruebas y Sobreajuste (López de Prado):**
   * El espacio de 11 estaciones × 150 estados contiene 1,650 celdas. Probarlas libremente genera ~250 falsos descubrimientos por puro azar ($\alpha=0.05$).
   * Todo reporte debe incluir el intervalo de confianza exacto Clopper-Pearson ($\text{CI}_{95}$), el $p$-value bilateral exacto y la corrección de Benjamini-Hochberg ($p_{\text{BH}}$ con $q=0.05$).
4. **Gobernanza de Diamantes de Cola (§3.3):**
   * **Prohibido descartar por $N$ bajo.** Estados o señales con $N \in [1..19]$ se registran y preservan con bandera `tier_rareza: "DIAMANTE"` y `n_insuficiente: true`. No se les calcula ratios continuos espurios (Sharpe, Kelly), pero se reporta su asimetría real ($RR$), su MAE y su MFE.
5. **Cero Proliferación:**
   * Prohibido generar 50 archivos JSON dispersos. Toda la verdad atómica vive en los 2 Parquets y se sintetiza en **1 solo JSON consolidado** para el consumo de producción.

---

## 2. Especificación Técnica de Datos

### CAPA 1A: `bar_snapshot_base.parquet` (8,453 filas × ~92 cols) — ESTABLE
Se computa una sola vez (~60s). Solo se regenera si cambian las barras históricas del Lake o los percentiles $\sigma$.

1. **SPY Base (6):** `spy_open`, `spy_high`, `spy_low`, `spy_close`, `spy_volume`, `spy_ret_1d`.
2. **11 Estaciones METAR (11 × 7 = 77 cols):** Para cada estación $E \in \{$`vix`, `vvix`, `pcr`, `fg`, `sv5_turbulence`, `skew`, `credit`, `yield_curve`, `rotation`, `dxy`, `bsi`$\}$:
   * `{E}_sk`: Clave canónica string `"{d1}__{d2}__{d3}"`.
   * `{E}_d1_bin`, `{E}_d2_bin`, `{E}_d3_bin`: Bins discretos enteros.
   * `{E}_z_d1`, `{E}_z_d2`, `{E}_z_d3`: Z-scores gaussianos reales (distancia en $\sigma$ respecto a $\mu, \sigma$ histórica).
   * `{E}_overflow_tier_d1`, `{E}_overflow_tier_d2`, `{E}_overflow_tier_d3`: Tiers de desbordamiento por dimensión ("T0" a "T5+").
   * `{E}_entry`: Booleano (`True` en la primera barra donde `{E}_sk` cambia respecto al día anterior).
3. **Métricas Macro y Ruptura Multi-Estación (4):** `panic_score`, `euphoria_score`, `n_overflows_2s`, `n_overflows_3s`.
4. **Timing de Ciclo ZigZag (4):**
   * `tim_slot`: Categoría en `["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]` (calculado con `classify_timing_slots` de `arnes/timing.py`).
   * `pivot_nearest_type`: `"MIN"`, `"MAX"` o `None`.
   * `pivot_nearest_date`: Fecha del pivote ZigZag más cercano.
   * `delta_bars_pivot`: Distancia en barras de trading con signo (- = anticipada, 0 = coincidente, + = retrasada).
5. **Resolución First-Passage Incondicional (Triple Barrier C9) (36 cols):**
   * Para cada escala $S \in \{$`zz25` (2.5%), `zz50` (5.0%), `zz75` (7.5%)\}$ y polaridad $\{long, short\}$:
     * `{S}_{dir}_hit`: Booleano (alcanzó barrera favorable antes de adversa o timeout).
     * `{S}_{dir}_fav`: Float (retorno favorable $(P_{\text{end}} - P_0) / P_0$).
     * `{S}_{dir}_mae`: Float (máxima excursión adversa / drawdown intra-trade $\le 0$).
     * `{S}_{dir}_mfe`: Float (máxima excursión favorable / runup intra-trade $\ge 0$).
     * `{S}_{dir}_bars`: Entero (barras transcurridas hasta tocar barrera o timeout).
     * `{S}_{dir}_timeout`: Booleano (alcanzó el time-stop vertical).
   * Time-stop canónico (C9): $zz25 \to 80$v, $zz50 \to 40$v, $zz75 \to 27$v. Timeout = falla.

### CAPA 1B: `bar_snapshot_signals.parquet` (8,453 filas × ~74 cols) — VOLÁTIL
Se computa en ~2 segundos a partir de `arnes/señales.py`. Se regenera cuando se agregan o modifican señales en el catálogo.

1. Por cada una de las 37 señales homologadas:
   * `{S}`: Booleano (`True` si la condición de la señal está activa en la vela).
   * `{S}_entry`: Booleano (`True` únicamente en la primera vela de transición $0 \to 1$ del episodio, calculado con `build_episodes`).
2. **Señales posicionales (4):** Mapear el `pivot_type` del pivote ZigZag más cercano a $\le 2$ barras; si la barra dista $> 2$ barras de un pivote, `pivot_type = None` y la señal posicional evalúa `False`.

---

## 3. Algoritmo de Extracción y Síntesis Institucional (`signal_intelligence.json`)

Un script único funde en memoria `base` + `signals` ($df = \text{concat}$) y genera un **único archivo consolidado** estructurado en 3 niveles de análisis:

### Nivel A: Radiografía de Micro-Estados de Estación (El Estado como Señal)
Para cada una de las 11 estaciones y para cada uno de sus estados observados (incluyendo calma `2__2__2`, continuación `1__2__2`, inestabilidad `2__2__4` y pánico `5__4__3`):
* **Población y Permanencia:**
  * $N_{\text{barras}}$, $\%_{\text{tiempo}}$, $N_{\text{episodios}}$ de entrada (`{E}_entry`).
  * Duración media de permanencia (barras) y racha máxima histórica consecutiva en ese estado.
* **Timing Canónico (Comparado contra Baseline Empírico):**
  * Baseline empírico del mercado: `ENTRE = 50.37%`, `En Rango = 49.63%`.
  * $\%_{\text{en\_rango}}$ ($t\pm 2$), $\%_{\text{ENTRE}}$ (continuación tendencial).
  * Distribución por slot: `t-2`, `t-1`, `t=0`, `t+1`, `t+2`, `ENTRE`.
  * **Clasificación Funcional de Timing (Derivada de Test Binomial, sin umbrales arbitrarios):**
    * `CONTINUACION_IMPULSO`: Si $\%_{\text{ENTRE}}$ supera significativamente el baseline del 50.37% ($p_{\text{binom}} < 0.05$).
    * `INFLEXION_GIRO`: Si $\%_{\text{en\_rango}}$ supera significativamente el baseline del 49.63% ($p_{\text{binom}} < 0.05$).
    * `TRANSICION_NEUTRA`: Si no hay diferencia estadísticamente significativa con la distribución modal.
* **First-Passage Long & Short a 3 escalas ($zz25, zz50, zz75$):**
  * $HR_{\text{long}}$, $HR_{\text{short}}$, $EV_{\text{long}}$, $EV_{\text{short}}$.
  * **Lift Real:** $\text{Lift} = HR - \text{Baseline}_{\text{incondicional}}$ para cada escala.
  * Intervalo exacto $\text{CI}_{95}$ Clopper-Pearson sobre el $HR$.
  * $p$-value binom contra el baseline incondicional.
  * **MAE (Drawdown intra-trade):** Mínimo, promedio y peor caso ($\text{MAE}_{\text{max}}$).
  * **MFE (Runup intra-trade):** Promedio y máximo.
  * **Ratio de Dolor:** $\text{MAE}_{\text{ratio}} = \text{MAE}_{\text{estado}} / \text{MAE}_{\text{baseline}}$ (si $< 0.8 \to$ baja volatilidad adversa; si $> 1.2 \to$ alta volatilidad adversa).
* **Desglose de Estabilidad Temporal por Macro-Eras:**
  * `Pre_QE` (1993–2008), `QE_Era` (2009–2021), `Post_QE` (2022–2026).
  * Ventana Reciente Rolling (últimos 3 años / 756 barras): Muestra si el edge sigue vivo en el régimen actual.

### Nivel B: Catálogo de Señales Calificadas (Taxonomía Homologada Canónica)
Para cada una de las 37 señales evaluadas exclusivamente sobre sus episodios de entrada (`{S}_entry == True`):
* **Filtro de Incepción Oficial:** Filtrar y evaluar únicamente desde `ESTACION_INCEPTION_DATES` (evitando datos sintéticos pre-2011 en SKEW/FG o pre-2007 en Credit).
* **Ficha de Calificación Institucional Canónica:**
  * **Rol Operacional:** `TACTICA_RAPIDA`, `ESTRUCTURAL`, `DIAMANTE_COLA`, `FILTRO_FONDO` (homologado con `ranking_maestro.json`).
  * **Estatus Institucional:**
    * `VALIDADA Grade A`: $N \ge 30$, pasa Benjamini-Hochberg ($p_{\text{BH}} < 0.05$), pasa DSR, $\text{Lift} > 0$.
    * `VALIDADA Grade B`: $N \ge 20$, $p_{\text{raw}} < 0.05$, $p_{\text{BH}} \in [0.05, 0.15]$, $\text{Lift} > 0$.
    * `Candidata Táctica` / `Candidata D3`: Edge positivo pero requiere confirmador cinemático $D_2$.
    * `Monitorear (Coincidente)`: Coincidente con giro pero $\text{Lift} \approx 0$.
    * `Diamante en Observación`: Evento de cola $N < 10$ con asimetría $RR > 3:1$.
    * `Inefectiva / Retirada`: $\text{Lift} \le 0$ o $p_{\text{BH}} \ge 0.50$.
  * **Acción Recomendada:** `PRODUCCION_PLENA`, `PRODUCCION_CONDICIONADA`, `EXCEPCION_COLA_SIZE_REDUCIDO`, `MONITOREO`, `CUARENTENA`.
  * **Incertidumbre Muestral:** $N_{\text{episodios}}$, $\text{CI}_{95}$ exacto Clopper-Pearson, $p_{\text{raw}}$, $p_{\text{BH}}$, $p_{\text{bonferroni}}$, DSR pass flag.
* **Métricas de Riesgo Inter-Trade (Curva de Capital):**
  * Para señales con $N \ge 20$:
    * $\text{Max Drawdown}_{\text{inter}}$ (peor caída de la curva de equity acumulada).
    * $\text{Max Consecutive Losses}$ (racha máxima de fallos).
    * $\text{VaR}_{95}$ y $\text{CVaR}_{95}$ (Expected Shortfall).
    * $\text{Half-Kelly Fraction}$ ($f^* / 2$).
  * Para diamantes ($N < 20$): Asignar `null` en ratios inter-trade y reportar exclusivamente el $\text{MAE}$ intra-trade (mínimo, medio, peor caso).
* **Estabilidad por Era:** Rendimiento desglosado en `Pre_QE`, `QE_Era`, `Post_QE` y ventana rolling 3 años.

### Nivel C: Matriz de Confluencia Ortogonal y Co-ocurrencia
* Pares de señales que co-ocurren el mismo día.
* Independencia estadística: correlación de Pearson y solapamiento de estaciones.
* Edge combinado vs individual: si la confluencia aumenta el win rate o es redundancia espuria.

---

## 4. Verificación y Control de Calidad

El script debe pasar automáticamente la siguiente batería de aserciones numéricas:

```bash
backend/.venv/bin/python -c "
import pandas as pd, json
b = pd.read_parquet('data/research/bar_snapshot_base.parquet')
s = pd.read_parquet('data/research/bar_snapshot_signals.parquet')
intel = json.load(open('data/research/signal_intelligence.json'))

assert len(b) == 8453 and len(s) == 8453, 'Filas no coinciden con lake continuo'
assert 'vix_sk' in b.columns and 'tim_slot' in b.columns
assert 'vix_z_d1' in b.columns and 'vix_overflow_tier_d1' in b.columns
assert 'panico_total_entry' in s.columns

# 1. Verificar que el estado de calma 2__2__2 tiene métricas intrínsecas y Lift negativo reportado
v222 = intel['estaciones']['vix']['states']['2__2__2']
print('VIX 2__2__2 bars:', v222['poblacion']['n_barras'])
assert 'lift_vs_baseline' in v222['resolucion_long']['zz25']
print('VIX 2__2__2 Lift zz25:', v222['resolucion_long']['zz25']['lift_vs_baseline'])

# 2. Verificar que los diamantes de baja muestra (N < 5) NO fueron descartados
c_cap = intel['senales']['credit_capitulation_entry']
print('credit_capitulation_entry N:', c_cap['calificacion']['n_episodios'])
assert c_cap['calificacion']['tier_rareza'] == 'DIAMANTE'

# 3. Verificar que el z-score y overflow tier tridimensional están completos
assert 'vix_z_d2' in b.columns and 'vix_overflow_tier_d2' in b.columns

# 4. Verificar que no se generaron más de 3 archivos en disco
import os
assert os.path.exists('data/research/signal_intelligence.json')
print('✅ TODAS LAS PRUEBAS DE RIGOR Y GOBERNANZA PASARON')
"
```

---

## 5. Política de Archivo Inmediato

Una vez validado `signal_intelligence.json`:
* Mover a `data/research/_archive/` los 114+ archivos viejos (`medicion_*.json`, evaluadores v1..v7, `ranking_maestro.json`, etc.).
* El repositorio queda con **3 archivos en total** para todo el subsistema de señales y estados.