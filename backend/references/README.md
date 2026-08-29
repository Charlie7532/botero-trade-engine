# Índice de Documentación Técnica — Botero Trade Engine Backend
## Sistema Cuantitativo Institucional y Arquitectura Limpia

Este directorio centraliza el índice de la documentación técnica, especificaciones estadísticas, modelos probabilísticos y referencias de dominio que gobiernan el motor de trading (`backend/`).

---

## 1. Módulos de Decisión y Señales (`backend/modules/`)

### 1.1 Módulo `entry_decision`
Ubicación: `backend/modules/entry_decision/references/`

| Documento | Descripción |
|---|---|
| [señales-exit.md](file:///root/botero-trade/backend/modules/entry_decision/references/señales-exit.md) | **Framework y Replanteamiento de Señales de EXIT**: Análisis de asimetría (11 ENTRY vs 2 EXIT), hallazgo empírico de que las señales de pánico operan como entradas contrarian, validación de `bsi_recovery` como salida efectiva (edge $-1.63\%$, WR $29\%$), taxonomía de 5 tipos de salida por degradación del vector de estado METAR y criterios de éxito cuantitativos. |
| [cascade-conviction.md](file:///root/botero-trade/backend/modules/entry_decision/references/cascade-conviction.md) | **Reevaluación Integrada de Convicción y Edge Defensivo**: Estudio profundo que integra 8 reportes forenses, formalización matemática del Edge Defensivo ($ED = |\overline{\text{Loss}}| - \overline{\text{Win}} \times \text{FA\_rate}$), 20 sign-flips en dimensiones D2×D3, análisis de precursores universales de crash (`credit.D2=ACCEL_UP`), degradación en 2020s y confluencia cross-señal aditiva vs redundante. |

---

## 2. Estaciones de Mercado e Inteligencia METAR (`.agents/references/`)

El sistema monitorea 9 estaciones de mercado ortogonales clasificadas bajo el estándar de calibración gaussiana ($\mu \pm k\sigma$):

| Estación | Documento de Referencia | Descripción Técnica |
|---|---|---|
| **VIX** | [vix_intelligence.md](file:///root/botero-trade/.agents/references/vix_intelligence.md) | CBOE Implied Volatility: régimen de complacencia, pánico y crisis de volatilidad en renta variable. |
| **VVIX** | [vvix_intelligence.md](file:///root/botero-trade/.agents/references/vvix_intelligence.md) | Volatilidad de la volatilidad: indicador líder de inestabilidad de régimen y transiciones estructurales. |
| **PCR** | [pcr_intelligence.md](file:///root/botero-trade/.agents/references/pcr_intelligence.md) | CBOE Put/Call Ratio: posicionamiento y asimetría de cobertura en opciones de renta variable. |
| **F&G** | [fg_intelligence.md](file:///root/botero-trade/.agents/references/fg_intelligence.md) | Fear & Greed Composite: indicador contrarian de sentimiento extremo de mercado. |
| **SV5 Turbulence** | [sv5_turbulence_intelligence.md](file:///root/botero-trade/.agents/references/sv5_turbulence_intelligence.md) | Turbulencia institucional de volumen ($\text{std}(\Delta \text{SV5TW}, 10\text{d})$): dispersión de flujo de capital institucional. |
| **SKEW** | [skew_intelligence.md](file:///root/botero-trade/.agents/references/skew_intelligence.md) | Demanda de puts OTM: riesgo de cola (*tail risk*) y paranoia institucional. |
| **Credit Stress** | [credit_intelligence.md](file:///root/botero-trade/.agents/references/credit_intelligence.md) | Ratio sintético HYG/LQD: liquidez crediticia, impulso monetario y estrés en renta fija. |
| **Yield Curve** | [yield_curve_intelligence.md](file:///root/botero-trade/.agents/references/yield_curve_intelligence.md) | Spread TNX−IRX (10Y−13W): inversión de curva soberana y fase del ciclo económico. |
| **Rotation Index** | [rotation_intelligence.md](file:///root/botero-trade/.agents/references/rotation_intelligence.md) | Rotación cíclica/defensiva ($z(\text{XLY}/\text{XLP}) + z(\text{XLK}/\text{XLU})$): apetito institucional por riesgo. |

---

## 3. Infraestructura de Datos y Políticas Cuantitativas (`.agents/references/`)

| Referencia | Enlace | Propósito |
|---|---|---|
| **Vault Data Registry** | [vault_data_registry.md](file:///root/botero-trade/.agents/references/vault_data_registry.md) | Registro exhaustivo de tickers, familias de amplitud (S5/SV5/S5CAP), series históricas (~5.80M barras) y convención de almacenamiento en Neon PostgreSQL (`market.ohlcv_bars`). |
| **Gaussian Scale Calibration** | [gaussian_scale_calibration_policy.md](file:///root/botero-trade/.agents/references/gaussian_scale_calibration_policy.md) | Política de partición dimensional basada en percentiles teóricos de la distribución normal ($D1$: magnitud en 6 bines, $D2$: velocidad 3d en 5 bines, $D3$: volatilidad de estación $\text{std}(2d)/\text{std}(10d)$ en 5 bines). |
| **METAR Interactions** | [metar_interactions.md](file:///root/botero-trade/.agents/references/metar_interactions.md) | Matriz de correlaciones, confluencias, desacoples e interacciones no lineales entre las 9 estaciones. |
| **Indicator Stochastic Registry** | [indicator_stochastic_registry.md](file:///root/botero-trade/.agents/references/indicator_stochastic_registry.md) | Mapeo probabilístico y matrices de transición de estados discretos. |

---

## 4. Mapa de Módulos del Backend (`backend/modules/`)

Todos los módulos siguen estrictamente **Clean & Hexagonal Architecture**, aislando `domain/` (entidades puras y reglas de negocio) de `infrastructure/` (adaptadores del Vault TimescaleDataStore, brokers y SDKs) y `application/` (casos de uso orquestadores).

```
backend/modules/
├── causal_investigation/     # Inferencia causal e identificación de drivers de mercado
├── entry_decision/           # Entry Hub, compuertas de régimen, filtros y referencias cuantitativas
├── execution/                # Paper trading, ejecución broker y journal de operaciones
├── flow_intelligence/        # Flujo institucional de opciones y transacciones de ballenas
├── market_health/            # Servicio transversal de convergencia y vector de estado METAR
├── options_gamma/            # Regímenes gamma (GEX, Vanna, Charm) y perfiles de exposición dealer
├── pattern_recognition/      # Reconocimiento algorítmico de patrones técnicos (pandas-ta)
├── portfolio_management/     # Filtros de universo de inversión, Alpha Scanner y selección de activos
├── price_analysis/           # Análisis técnico de precio, RSI multiescala y timing de fases
├── quality_swing/            # Módulo táctico swing para activos de alta calidad (MOAT)
├── rotation_intelligence/    # Análisis de rotación sectorial e intermercado (Weinstein / Pring)
├── shared/                   # Puertos globales, entidades de mercado, caché y DataStore
├── simulation/               # Motor de backtesting riguroso (Backtrader) y auditoría forense
├── volatility_regime/        # Clasificador de regímenes de volatilidad y máquina de estados
└── volume_intelligence/      # Perfiles de volumen, VWAP y filtro de Kalman de volumen
```

---

## 5. Reglas de Contribución y Mantenimiento

1. **Vault-First Data Access:** Todo módulo bajo `backend/modules/` lee datos exclusivamente desde `TimescaleDataStore` (Neon PostgreSQL). Llamadas directas a APIs externas están estrictamente prohibidas en el dominio.
2. **Stateful-First Classification:** Toda clasificación discreta de régimen debe persistirse en `market.regime_states` a través de `RegimeStatePort` emitiendo `StateSnapshot`.
3. **Universal Institutional Taxonomy:** Toda señal y acción emitida debe adherirse al estándar `[SCOPE]_[INTENT]_[EXECUTION]` (ej: `STK_ACCUMULATE_STRUCTURAL`, `STK_TRIM_TACTICAL`, `MKT_MACRO_CIRCUIT_BREAKER`).
4. **Alerta Aeronáutica en 4 Niveles:** Los servicios de monitoreo emiten en formato `METAR` (observación rutinaria), `TAF` (pronóstico de horizonte), `SIGMET` (alertas de peligro extremo) y `NOTAM` (disrupciones operativas).
