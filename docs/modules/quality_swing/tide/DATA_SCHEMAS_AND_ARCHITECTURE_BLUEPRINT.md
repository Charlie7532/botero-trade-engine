# Plano de Arquitectura y Especificación de Esquemas de Datos (Tide, Current & Wave)

> **Subsistema:** Quality Swing (`backend/modules/quality_swing/`)  
> **Fecha:** 2026-09-29  
> **Propósito:** Especificación técnica integral del plano arquitectónico y diccionario exhaustivo de dimensiones, llaves y esquemas JSON para los módulos **Tide**, **Current** y **Wave**.

---

## 1. Plano de Arquitectura de 3 Niveles (Architecture Blueprint)

El subsistema **Quality Swing** actúa como la **Capa 3 (Entry Gate & Timing Táctico)** del bot. No decide qué activos comprar (responsabilidad de Quality Core), sino cuándo acumular o trimmar para maximizar la velocidad de capital y eliminar el *slippage*.

```
====================================================================================================
                        PLANO ARQUITECTÓNICO: QUALITY SWING ENGINE
====================================================================================================

               +-------------------------------------------------------+
               |         Neon PostgreSQL (Single Source of Truth)       |
               |         market.ohlcv_bars + engine.channel_snapshots  |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |        rc_slope_classifier.py / Feature Engine        |
               |  Cálculo de Regresión de 3 Escalas & Normalización ATR  |
               +-------------------------------------------------------+
                                           |
                   +-----------------------+-----------------------+
                   |                                               |
                   v                                               v
  +---------------------------------+             +---------------------------------+
  |    1. MODELO CLÁSICO (180/479)   |             |   2. MODELO REAL EV (245/25,797) |
  |  Frecuencia & Densidad Giratoria|             |  Valor Esperado Real P-en-Tiempo|
  +---------------------------------+             +---------------------------------+
  | - rc_tide_derived.json          |             | - rc_tide_ev_derived.json       |
  | - rc_wave_derived.json          |             | - rc_wave_ev_derived.json       |
  | - rc_tide_lookup.py             |             | - rc_tide_ev_lookup.py          |
  | - rc_wave_lookup.py             |             | - rc_ev_multiscale_tree.json    |
  +---------------------------------+             +---------------------------------+
                   |                                               |
                   |   (p_bull, odds, lift_vs_band)                |   (EV net, Sharpe, R:R, e_days,
                   |                                               |    Kelly f*, Cascadas L3->L0)
                   +-----------------------+-----------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |            swing_gate.py (Orquestador Dual)           |
               |   Evaluación de Confluencia Dual & Veto de Venta (TRIM)|
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |            RegimeStatePort (Vault-First)              |
               |        Persistencia en market.regime_states           |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |     Taxonomía Universal DTO (TideRouteGuidance)       |
               |   Emitiendo: STK_ACCUMULATE_STRUCTURAL / STK_BUY_DIP... |
               +-------------------------------------------------------+
```

---

## 2. Definición Físico-Matemática de las 3 Escalas

Las tres ventanas del canal de regresión procesan el movimiento del precio dividiéndolo en tres escalas ortogonales:

$$\begin{array}{lccll}
\hline
\textbf{Escala} & \textbf{Período (Barras)} & \textbf{Normalización} & \textbf{Categoría Físico-Matemática} & \textbf{Función en el Sistema} \\
\hline
\mathbf{TIDE} & N = 240 & \frac{\text{slope}_{240}}{\text{ATR}_{14} / \text{Price}} & \text{Tendencia Estructural (1 Año)} & \text{Sesgo secular de marea y Trend Protection Gate} \\
\mathbf{CURRENT} & N = 60 & \frac{\text{slope}_{60}}{\text{ATR}_{14} / \text{Price}} & \text{Momentum Trimestral (3 Meses)} & \text{Aceleración/Desaceleración y Pullback Detector} \\
\mathbf{WAVE} & N = 8\text{--}50\text{ (Adaptativo)} & \frac{\text{slope}_{\text{cycle}}}{\text{ATR}_{14} / \text{Price}} & \text{Microestructura Táctica (Días)} & \text{Ubicación VWAP } (\sigma Vw) \text{ y Timing de Disparo} \\
\hline
\end{array}$$

---

## 3. Matriz Exhaustiva de Archivos JSON y Esquemas de Datos

### 3.1. Familia TIDE (Macro & Trend)

#### A. `rc_tide_derived.json` (Modelo Clásico de Frecuencia — 464 KB)
* **Propósito:** Fact store pre-clasificado del modelo clásico de densidad de giros.
* **Dimensiones (3D):** $Tide\_Slope \text{ (6 niveles)} \times Current\_Slope \text{ (6 niveles)} \times \sigma VWAP\_Wave \text{ (5 bins)} = 180 \text{ estados}$.
* **Estructura del Formato de Clave:** `"T{level}|C{level}|{vwap_bin}"`  
  *Ejemplo:* `"T+++|C---|<<"`
* **Niveles de Pendiente:** `T+++`, `T++`, `T+`, `T-`, `T--`, `T---` | `C+++`, `C++`, `C+`, `C-`, `C--`, `C---`
* **Bins $\sigma VWAP$:** `<<` ($<-1.0\sigma$), `<` ($-1.0\sigma$ a $-0.3\sigma$), `~` ($\pm 0.3\sigma$), `>` ($+0.3\sigma$ a $+1.0\sigma$), `>>` ($>+1.0\sigma$).
* **Esquema de Atributos por Estado:**
  ```json
  "T+++|C---|<<": {
    "identity": {
      "signal": "BUY_DIP",
      "zone": "FLOOR",
      "regime": "DIV_DOWN",
      "conviction": "HIGH",
      "conviction_score": 85,
      "signal_confidence": 92
    },
    "direction": {
      "p_bull": 72.4,
      "odds": 2.62,
      "lift_vs_band": 1.45,
      "z_score": 3.12
    },
    "turn_risk": {
      "bottom_25": { "pct": 45.2, "n": 320 },
      "top_25": { "pct": 12.1, "n": 85 },
      "asymmetry_pp": 33.1
    },
    "composition": {
      "momentum_purity": 0.82,
      "capitulation_purity": 0.15
    },
    "frequency": {
      "N": 708,
      "rank": 14
    }
  }
  ```

---

#### B. `rc_tide_ev_derived.json` (Modelo Real EV Punto-en-Tiempo — 270 KB)
* **Propósito:** Tabla derivada con el Valor Esperado Neto real, Sharpe estocástico, asimetría $R:R$ y velocidad de capital para las 3 escalas ZigZag ($ZZ_{2.5\%}, ZZ_{5.0\%}, ZZ_{7.5\%}$).
* **Dimensiones (3D Expandido con Neutro):** $Tide\_Slope \text{ (7 niveles)} \times Current\_Slope \text{ (7 niveles)} \times \sigma VWAP\_Wave \text{ (5 bins)} = 245 \text{ estados L3}$.
* **Estructura del Formato de Clave:** `"T{level}|C{level}|{vwap_bin}"` (Incluye `T~` y `C~`).
* **Niveles de Pendiente:** `+++`, `++`, `+`, `~`, `-`, `--`, `---` (7 niveles cuantílicos).
* **Esquema de Atributos por Estado L3:**
  ```json
  "l3_full_state": {
    "T+++|C---|<<": {
      "n": 2393,
      "is_rare_state": false,
      "std_return": 0.1234,
      "ev_net_global": 0.0420,
      "sharpe": 0.3401,
      "zz25": {
        "p_bull": 0.5964,
        "p_bear": 0.4036,
        "e_ret_max": 0.0615,
        "e_ret_min": -0.0463,
        "ev_net": 0.0170,
        "e_days": 6.8,
        "ev_per_day": 0.002481,
        "rr_asymmetry": 1.3272
      },
      "zz50": {
        "p_bull": 0.6595,
        "p_bear": 0.3405,
        "e_ret_max": 0.1032,
        "e_ret_min": -0.0681,
        "ev_net": 0.0439,
        "e_days": 13.8,
        "ev_per_day": 0.003190,
        "rr_asymmetry": 1.5161
      },
      "zz75": {
        "p_bull": 0.7096,
        "p_bear": 0.2904,
        "e_ret_max": 0.1339,
        "e_ret_min": -0.0997,
        "ev_net": 0.0651,
        "e_days": 16.1,
        "ev_per_day": 0.004048,
        "rr_asymmetry": 1.3433
      }
    }
  }
  ```

---

#### C. `rc_tide_probability_table.json` & `rc_tide_ev_probability_table.json` (Raw Fact Stores — 156 KB & 150 KB)
* **Propósito:** Tablas primarias con los conteos absolutos sin procesar extraídos de los 4,554,321 snapshots de Neon DB. Contienen los numeradores y denominadores puros ($N_{pos}, N_{neg}, \sum \text{returns}$) utilizados por los scripts generadores.

---

### 3.2. Familia WAVE (Microestructura & Volatilidad)

#### A. `rc_wave_derived.json` (Modelo Clásico Wave — 1,424 KB)
* **Propósito:** Medición micro-estructural de la ola adaptativa.
* **Dimensiones (4D):** $Wave\_Slope \text{ (5 niveles)} \times \sigma Vc \text{ (5 bins)} \times \sigma c \text{ (5 bins)} \times \Delta\sigma Vw \text{ (3 tendencias: } \mathbf{\Delta}, \mathbf{\sim}, \mathbf{\nabla}\mathbf{)} = 375\text{--}479 \text{ estados}$.
* **Estructura del Formato de Clave:** `"W{slope}|σVc:{bin}|σc:{bin}|vel:{trend}"`  
  *Ejemplo:* `"W++|σVc:<|σc:~|vel:▲"`
* **Esquema de Atributos por Estado:**
  ```json
  "W++|σVc:<|σc:~|vel:▲": {
    "identity": {
      "signal": "ACCUMULATE",
      "microstructure_type": "SPRING_DIP",
      "conviction": "HIGH"
    },
    "p_any_bottom": 68.4,
    "lift_best_bottom": 1.85,
    "bot_pct_clean": 82.0,
    "n_samples": 412
  }
  ```

---

#### B. `rc_wave_ev_derived.json` & `rc_wave_ev_3scales_derived.json` (Real Wave EV — 2.6 MB & 560 KB)
* **Propósito:** Mapeo de Valor Esperado para la ola micro-estructural adaptativa. Evalúa la fuerza de restitución elástica del precio hacia la media del VWAP en escalas de 2.5%, 5.0% y 7.5%.
* **Estructura de Clave:** `"L1:W{slope}|σVc:{bin}|σc:{bin}|vel:{trend}"`
* **Atributos Clave:** `ev_net`, `sharpe`, `fatigue_type` (`STABLE`, `EXHAUSTING`, `FATIGUE_RISK`), `rr_asymmetry`.

---

### 3.3. Familia MULTISCALE (Tríada Completa & Cinemática)

#### A. `rc_ev_multiscale_tree.json` (Árbol Cinemático Multiescala — 20.9 MB)
* **Propósito:** El Fact Store más masivo del sistema. Agrupa la combinación simultánea de las 3 escalas ($Tide \times Current \times Wave$) junto a los estados de aceleración y fatiga.
* **Dimensiones (6D Cinemática):**  
  $$Tide\_Slope \times Current\_Slope \times Wave\_Slope \times \sigma Vc \times \sigma Vw \times \Delta\sigma Vw \# Fatigue\_State$$
* **Total de Estados Registrados:** **25,797 estados únicos en $S1_{full}$** (con 791,120 muestras multiescala).
* **Estructura del Formato de Clave:** `"T~|C+|W~|~|>|>>#STABLE"`
* **Esquema de Atributos por Estado:**
  ```json
  "S1_full": {
    "T-|C+|W~|~|>|>>#STABLE": {
      "n": 142,
      "ev_net_25": 0.0124,
      "ev_net_50": 0.0285,
      "ev_net_75": 0.0410,
      "p_bull_25": 0.612,
      "p_bull_50": 0.684,
      "p_bull_75": 0.741,
      "rr_asymmetry": 2.14,
      "e_days": 5.4,
      "kinematic_trajectory": "ACCELERATING_UP"
    }
  }
  ```

---

#### B. `rc_multiscale_regime_rules.json` (Reglas de Transición y Matriz Markoviana — 733 KB)
* **Propósito:** Define las probabilidades de transición condicionadas por la duración del estado ($1\text{--}3\text{d}$, $4\text{--}10\text{d}$, $>10\text{d}$).
* **Atributos Principales:** `feature_importances`, `duration_conditioned_transition_matrix`, `regime_rules`.

---

### 3.4. Familia NORMATIVA Y DE NORMALIZACIÓN

#### `rc_vol_normalized_thresholds.json` (Percentiles Gaussianos de Calibración — 4.3 KB)
* **Propósito:** Tabla de calibración con la distribución poblacional completa en Neon DB para garantizar clasificaciones z-score y cuantílicas inmunes a variaciones de volatilidad.
* **Esquema:**
  ```json
  {
    "tide_slope_norm": {
      "p2_5": -7.1072,
      "p10": -3.7897,
      "p25": -0.8920,
      "p50": 0.0,
      "p75": 5.8933,
      "p90": 9.0233,
      "p97_5": 13.1020
    },
    "current_slope_norm": {
      "p2_5": -15.6977,
      "p10": -9.3049,
      "p25": -3.7779,
      "p50": 0.0,
      "p75": 9.7130,
      "p90": 15.8825,
      "p97_5": 23.2615
    },
    "vwap_sigma_wave": {
      "p2_5": -1.95,
      "p10": -1.00,
      "p25": -0.30,
      "p50": 0.0,
      "p75": 0.30,
      "p90": 1.00,
      "p97_5": 1.95
    }
  }
  ```

---

## 4. Resumen del Diccionario de Campos de Producción

| Campo en JSON | Tipo de Dato | Definición Matemática / Significado Físico |
|---|:---:|---|
| `p_bull` | `float` | Probabilidad de que el siguiente pivote ZigZag sea un suelo MIN ($0.0 \text{--} 1.0$). |
| `ev_net` / `ev` | `float` | Retorno esperable neto ajustado por fricción ($E[R] = P_{bull} \cdot E[R_{max}] - P_{bear} \cdot |E[R_{min}]|$). |
| `sharpe` | `float` | Razón de Sharpe estocástica del estado ($EV / \sigma_{return}$). |
| `rr_asymmetry` | `float` | Asimetría Riesgo/Recompensa ($\frac{E[ret\_max]}{|E[ret\_min]|}$). Mínimo apetecible $\ge 1.5$. |
| `e_days` | `float` | Tiempo dinámico esperado en días bursátiles hasta el toque del pivote ZigZag. |
| `ev_per_day` | `float` | Velocidad de capital ($EV / e\_days$). Métrica clave para el sizing de Half-Kelly. |
| `fatigue_type` | `string` | Estado de desgaste del impulso (`STABLE`, `EXHAUSTING`, `FATIGUE_RISK`). |
| `is_rare_state` | `bool` | Flag que indica si la muestra del estado tiene $N < 15$ observaciones históricas. |

---

## 5. Ubicación del Documento en el Monorepo

Este plano de arquitectura y especificación de datos ha sido guardado permanentemente en el repositorio en:
`docs/modules/quality_swing/tide/DATA_SCHEMAS_AND_ARCHITECTURE_BLUEPRINT.md`
