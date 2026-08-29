# PROMPT MAESTRO — Auditoría Holística y Diagnóstico de Estado: Ecosistema Aeronáutico METAR/TAF/SIGMET, Catálogo de Señales, Arquitectura Hexagonal y Gobernanza de Transición hacia Tide & Rotación

**Para:** Comité de Auditoría Cuantitativa Multimodelo (DeepSeek-R1/V3, Qwen 2.5/3-Max, GLM-4, Claude 3.7/Opus, Gemini 2.0 Pro/Flash, OpenAI o1/GPT-4o)  
**De:** Juan Andrés (Arquitecto de Sistemas & Lead Quantitative Strategist)  
**Fecha de Emisión:** 28-Ago-2026  
**Ambiente Operativo:** `/root/botero-trade` · Python venv en `backend/.venv` · Neon PostgreSQL (TimescaleDB)  
**Comando Base de Ejecución:** `cd /root/botero-trade && PYTHONPATH=/root/botero-trade:research/01_señales_entry_exit backend/.venv/bin/python <script>`

---

## 0. DIRECTIVA FUNDAMENTAL Y PROTOCOLO ANTI-SESGO MULTIMODELO

### 0.1 El Principio Rector: "Dato Mata Relato"
Este sistema no opera sobre heurísticas cualitativas, optimismo de retail ni academicismo abstracto. Opera sobre **mecánica cuantitativa e institucional pura**: microestructura de mercado, flujos de cobertura forzada de dealers (gamma/vanna/charm), cinemática multi-escala de precios (ZigZag) y estados dimensionales gaussianos calibrados sobre el historial completo en el Neon Vault.

### 0.2 Inoculación contra Sesgos Cognitivos y Sistémicos de Modelos Occidentales
Las inteligencias artificiales comerciales occidentales (e.g., Claude, Gemini, GPT) presentan sesgos sistemáticos documentados en finanzas cuantitativas que **DEBEN SER NEUTRALIZADOS Y AUDITADOS CRÍTICAMENTE POR MODELOS ORIENTALES / DEEPSEEK / QWEN**:

1. **Sesgo de Aversión Académica y Destrucción de Diamantes (Anti-Diamond Bias):**
   - *El error occidental:* Clasificar automáticamente cualquier evento con muestra baja ($N < 21$) como "ruido estadístico" o "insuficiente para operar", forzando degradaciones a Grado D o aplicando Bayesian Shrinkage ciego.
   - *La realidad institucional:* Los crashes sistémicos, pánicos de liquidez y capitulaciones extremas son **eventos intrínsecamente raros** (1 a 3 veces por década). Destruir su señal por "bajo N" es el **Anti-patrón #7 del Fact Store (§3.3)**: destruir la señal más asimétrica y rentable del sistema.
   - *La directiva:* Los eventos con $N < 21$ que exhiben asimetría extrema ($CI_{95}$ direccional que no cruza cero) son **DIAMANTES ESTADÍSTICOS**. Se auditan mediante tasa cruda ($P_{raw} = n_{fav}/n_{tot}$), intervalo binomial exacto de Clopper-Pearson y contexto cronológico narrativo, **NUNCA con shrinkage ni descarte ciego**.

2. **Sesgo de Complacencia y Sicofancia (Superficial Agreement):**
   - *El error occidental:* Validar resúmenes previos sin verificar el código fuente, las consultas SQL o los archivos pickle subyacentes, aceptando equivalencias matemáticas frágiles como verdades absolutas.
   - *La directiva:* Auditar desde los primeros principios (*First Principles*). Cada afirmación debe ser corroborada con ejecución de código y extracción de datos en tiempo real.

3. **Sesgo de Pedantería Teórica vs. Física Microestructural:**
   - *El error occidental:* Suponer normalidad i.i.d., estacionariedad estricta o eficiencia de mercado.
   - *La realidad institucional:* Los mercados operan en clusters de volatilidad (Mandelbrot), rotación sectorial no-lineal y regímenes asimétricos donde el tiempo de reacción ($\Delta 3d$ vs $\Delta 20d$) define el edge.

---

## 1. OBJETIVO Y ALCANCE DE ESTA AUDITORÍA PROFUNDA

El auditor debe emitir un **diagnóstico exhaustivo, implacable y cuantitativamente respaldado** estructurado en 7 dimensiones críticas:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             MAPA DE AUDITORÍA 7D                                 │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 1. Telemetría METAR (11 Estaciones): Estado, adaptadores y fact stores.          │
│ 2. Motor TAF (Pronóstico Triádico): zz25, zz50, zz75 y vectores estocásticos.    │
│ 3. Alertas SIGMET & NOTAM: Disrupción severa, circuit breakers y robustez.       │
│ 4. Catálogo de Señales (39 señales): Calidad, confiabilidad, tipos y regímenes.  │
│ 5. Puntos Ciegos & Quiebres Estructurales: Quants_obs, SKEW CAT-A, pre-2011 NaN. │
│ 6. Arquitectura Hexagonal: Topología de archivos, desacoplamiento y políticas.   │
│ 7. Plan de Culminación & Transición hacia Tide Engine y Rotación Sectorial.      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. INVENTARIO DE ARTEFACTOS Y FUENTES DE VERDAD

### 2.1 Ecosistema de Dominio y Servicios (`backend/modules/entry_decision/domain/`)
- **Reglas y Fact Stores (`domain/rules/`):**
  - `vix_fact_store.json` (108 estados) · `vix_lookup.py`
  - `vvix_fact_store.json` (104 estados) · `vvix_lookup.py`
  - `pcr_fact_store.json` (103 estados) · `pcr_lookup.py`
  - `fg_fact_store.json` (82 estados) · `fg_lookup.py`
  - `sv5_turbulence_fact_store.json` (104 estados) · `sv5_turbulence_lookup.py`
  - `skew_fact_store.json` (98 estados) · `skew_lookup.py`
  - `credit_fact_store.json` (112 estados) · `credit_lookup.py`
  - `yield_curve_fact_store.json` (133 estados) · `yield_curve_lookup.py`
  - `rotation_fact_store.json` (120 estados) · `rotation_lookup.py`
  - `bsi_fact_store.json` (104 estados) · `bsi_lookup.py`
  - `dxy_fact_store.json` (128 estados) · `dxy_lookup.py`
  - `cascade_calibration.json` (Parámetros calibrados de z_bear, domino_zz25/50 y type_mask)
  - `sigma_overflow.py` · `triad_lookup.py` · `systemic_gatekeeper.py`
- **Servicios Puros de Dominio (`domain/services/`):**
  - `convergence_compositor.py` (Compositor multi-estación dual-channel y convicción de cascada)
  - `market_sigmet_hazard_service.py` (Evaluador de clima severo y boletines SIGMET)
  - `notam_incident_service.py` (Boletines de disrupción técnica y Circuit Breakers)
  - 11 Servicios METAR (`vix_metar_service.py`, `credit_metar_service.py`, etc.)
- **Puntos de Entrada API (`backend/api/routers/`):**
  - `metar.py` (`/api/metar/raw/{station}`, `/api/metar/composite`, `/api/metar/all`)
  - `sigmet.py` (`/api/sigmet/active`)
  - `notam.py` (`/api/notam/incidents`)

### 2.2 Infraestructura de Datos y Almacén Canónico
- **Neon PostgreSQL (TimescaleDB):**
  - `market.ohlcv_bars`: ~5.80M barras normalizadas a medianoche UTC (`00:00:00+00`).
  - `market.zigzag_legs`: 4M+ piernas ZigZag históricas en 3 escalas (`zz25`, `zz50`, `zz75`).
  - `market.ticker_metadata`: Clasificación unificada de activos e indicadores (`STOCK`, `ETF`, `INDICATOR`).
- **Tablas de Observación y Generadores:**
  - `research/10_gate_oos_validation/builder_quants_obs.py` (Generador canónico v7 con fixes F1-F6).
  - `data/research/pivots/quants_obs_new.pkl` (1,590 filas de pivotes SPY zz25 × 142 columnas).
  - `data/research/signals/manifiesto_divergencias_quants_obs.json` (Auditoría de columnas CAT-A/B/C).
  - `backend/scripts/generators/generate_all_150_state_fact_stores.py` (Generador atómico de Fact Stores).

---

## 3. DIMENSIONES DE AUDITORÍA DETALLADAS

```markdown
### DIMENSIÓN 1: TELEMETRÍA METAR (Las 11 Estaciones de Mercado)
Evaluar la robustez, completitud y formulación matemática de las 11 estaciones:
1. **Definición de Dimensiones:**
   - D1 (Magnitud): 6 bines gaussianos [-2σ, -1σ, μ, +1σ, +2σ] sobre el histórico completo del Vault.
   - D2 (Velocidad Cinemática 72h): Δ3d = diff(3) clasificado en 5 bines gaussianos.
   - D3 (Estabilidad / Volatilidad Intra-Estación): Ratio std(2d)/std(10d) en 5 bines gaussianos (Estándar V1.1).
2. **Preguntas Clave para el Auditor:**
   - ¿Están todas las 11 estaciones implementadas con tolerancia CERO a fallbacks silenciosos (StrictDataPolicyError)?
   - ¿Existen discrepancias entre las fórmulas de los Fact Stores y los *_metar_service.py en producción?
   - ¿Cómo se maneja la ausencia de datos pre-2011 en estaciones recientes (e.g. FG disponible desde 2011, Credit desde 2007, PCR desde 2006)?

### DIMENSIÓN 2: MOTOR TAF (Terminal Aerodrome Forecast) Y MATRIZ TRIÁDICA
Auditar la proyección estocástica forward del mercado en 3 horizontes:
1. **La Tríada de Escalas ZigZag:**
   - zz25 (2.5%): Pullbacks tácticos / ruido de alta frecuencia (1–15 días).
   - zz50 (5.0%): Correcciones intermedias / horizonte swing trade (5–60 días).
   - zz75 (7.5%): Movimientos estructurales / cambios de régimen y capitulación (20–200+ días).
2. **Vectores de Estado y Cinética:**
   - Vector de Probabilidad: [P_bull_25, P_bull_50, P_bull_75]
   - Vector de Retorno Esperado: [EV_net_25, EV_net_50, EV_net_75]
   - Vector de Velocidad de Capital: [e_days_25, e_days_50, e_days_75] y e_speed = EV / e_days
3. **Preguntas Clave para el Auditor:**
   - ¿El cálculo de EV_net descuenta adecuadamente la fricción y el riesgo de cola?
   - ¿Cómo detecta el sistema los patrones de Divergencia de Agotamiento (P_bull_25 >> P_bull_75) y Divergencia de Reversión (P_bull_25 << P_bull_75)?
   - ¿Existe consistencia entre la probabilidad de desborde (Scale Overflow Program) y la realidad histórica?

### DIMENSIÓN 3: ALERTAS SIGMET Y DISRUPCIÓN NOTAM
Auditar la capa de seguridad crítica y circuit breakers del sistema:
1. **Taxonomía Aeronáutica de Severidad:**
   - METAR: Telemetría diaria continua (siempre activo).
   - TAF: Pronóstico estocástico condicionado al vector de estado.
   - SIGMET: Boletín de clima severo emitido ÚNICAMENTE ante violaciones de umbrales extremos (VIX >= 28, SKEW >= 145, SV5_Turbulence > 10, Inversión de Curva de Rendimientos, Capitulación por Pánico).
   - NOTAM: Disrupción operativa de infraestructura (stale data en Vault, caída de APIs, macro circuit breaker).
2. **Preguntas Clave para el Auditor:**
   - ¿Cumple market_sigmet_hazard_service.py con retornar lista vacía [] y status: CLEAR en condiciones normales?
   - ¿Los códigos de acción emitidos respetan la Taxonomía Universal (STK_BLOCK_CRISIS, STK_TRIM_TACTICAL, MKT_MACRO_CIRCUIT_BREAKER)?
   - ¿Existe algún acoplamiento indebido entre la emisión de un SIGMET y la ejecución de órdenes?

### DIMENSIÓN 4: CATÁLOGO DE SEÑALES, CALIDAD, TIPOS Y REGÍMENES
Auditar el catálogo de 39 señales en research/01_señales_entry_exit/arnes/señales.py y los resultados del evaluador OOS:
1. **Evaluación de Señales Nucleares (CATALOGO_V7 / V8):**
   - Señales de Entrada de Pánico / Valor: pcr_put_panic, credit_stress, capitulacion, vvix_entry, bsi_washed_out.
   - Señales de Salida / Distribución: euforia, bsi_recovery, fg_extreme_greed, stealth_tail_hedging, skew_paranoia_exit.
   - Señales Problemáticas / Degeneradas: credit_ease_exit (lift < 1.0, sufijo fraudulento), breadth_contraction_exit (fire rate 87.7% = ruido puro de régimen), cascade_reversal (p=0.25, sin significancia estadística).
2. **Aplicación Estricta del Protocolo Diamante (§3.3):**
   - Auditar panico_total (N=11) y skew_paranoia_exit (N=10).
   - ¿Fueron injustamente degradadas por modelos anteriores debido a sesgo occidental de bajo N?
   - Calcular P_raw, Intervalo Clopper-Pearson al 95%, y mapear las fechas históricas exactas de disparo.

### DIMENSIÓN 5: PUNTOS CIEGOS FORENSES Y RIESGOS ESTRUCTURALES
Analizar los 6 puntos ciegos descubiertos durante la investigación profunda:
1. **BS1 — Quiebre Estructural por Denominador Variable en d1_bear_5:**
   - El 64% de los pivotes históricos tienen < 5 estaciones disponibles. Antes de 2011, d1_bear_5 = count(v<0)/n divide entre 2, 3 o 4 en vez de 5.
   - Esto provoca que los saltos de presión bearish sean de 0.50 (en 1995) vs 0.20 (en 2020), distorsionando la escala de z_bear. ¿Cómo debe corregirse o acotarse?
2. **BS2 — Sesgo de Selección Condicional en quants_obs:**
   - quants_obs evalúa señales sobre días de pivote confirmado (P(favorable | señal ∧ pivote)), mientras que el Fact Store evalúa todos los días (P(favorable | señal)). Cuantificar la inflación de Win Rate resultante.
3. **BS3 — 236 Fechas de Pivote Duplicadas en Piernas SPY zz25:**
   - Piernas forward y backward que comparten start_timestamp. Confirmar si algún consumidor aguas abajo se ve afectado por duplicidad temporal.
4. **BS4 — Look-Ahead en Calibración de Umbrales:**
   - El umbral congelado -0.957 de cascade_reversal fue derivado del percentil 15 de la muestra completa (1993-2026). Cuantificar la inestabilidad por folds temporales.
5. **BS5 — Onda Expansiva Multidimensional de SKEW CAT-A:**
   - La reclasificación de SKEW alteró no solo D1, sino también D2 y D3, impactando a stealth_tail_hedging (8 filas cambiadas) y sorpresa_total.
6. **BS6 — Asimetría de Pesos en type_mask:**
   - El builder aplica pesos de type_mask.MIN a todas las filas. Auditar el riesgo ante futuras calibraciones diferenciadas.

### DIMENSIÓN 6: ARQUITECTURA HEXAGONAL, LOCALIZACIÓN Y GOBERNANZA DE RECALCULO
Auditar la higiene arquitectónica y las políticas de persistencia:
1. **Cumplimiento de Arquitectura Limpia:**
   - Regla de Dependencia Inward: El dominio no debe importar infraestructura ni librerías de scraping/APIs externas.
   - Acceso exclusivo al Neon Vault vía TimescaleDataStore (Regla 13).
2. **Topología de Archivos:**
   - Localización de Fact Stores (backend/modules/entry_decision/domain/rules/ vs backend/scripts/generators/).
   - Ubicación de generadores y pipelines de validación.
3. **Políticas de Actualización y Recálculo:**
   - ¿Cuándo se recalcula un Fact Store? (Regla 24: Solo cuando el historial del Vault crece >20% o tras quiebre estructural de régimen, mediante ejecución atómica de generate_all_150_state_fact_stores.py).
   - ¿Cómo y dónde se persiste el estado de régimen? (Regla 15/16: market.regime_states vía RegimeStatePort con esquema {classifier}:{department}:{scope}).

### DIMENSIÓN 7: PLAN DE CULMINACIÓN Y TRANSICIÓN HACIA TIDE Y ROTACIÓN
Establecer la hoja de ruta definitiva para sellar esta etapa y avanzar a los siguientes motores:
1. **Checklist de Culminación de Etapa Señales/METAR:**
   - Qué archivos deben congelarse como versión canónica inmutable.
   - Qué señales deben quedar catalogadas en Producción vs Cuarentena vs Retiradas.
2. **Puente hacia Tide Engine (Marea de Mercado & Contenedor Triádico):**
   - Integración con TriadContainer, elasticidad de VWAP multi-escala (<<, ~, >>) y divergencia de horizontes temporales.
3. **Puente hacia Rotación Sectorial y de Activos:**
   - Clasificación Weinstein (Etapas 1 a 4) en los 11 ETFs sectoriales SPDR.
   - Mapeo de ciclos inter-mercado Martin Pring (Bonos → Acciones → Commodities).
   - Gobernanza del Gate de Rotación Sectorial (s5_relative_modifier.json, sector_rotation_flow.py).
```

---

## 4. BATERÍA DE VERIFICACIÓN EJECUTABLE (TEST SCRIPTS)

El evaluador debe ejecutar y reportar los resultados de los siguientes scripts de diagnóstico directo:

### Script 1: Verificación de Fact Stores, Estados y Cero Huérfanos
```bash
cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import json
from pathlib import Path

rules_dir = Path('backend/modules/entry_decision/domain/rules')
fact_stores = sorted(rules_dir.glob('*_fact_store.json'))
print(f'=== FACT STORES EN DOMINIO ({len(fact_stores)} archivos) ===')
for fs in fact_stores:
    data = json.loads(fs.read_text())
    states = data.get('states', {})
    meta = data.get('_documentation', {})
    print(f'{fs.name:32s} | Estados: {len(states):3d} | Meta docs: {\"OK\" if meta else \"MISSING\"}')
"
```

### Script 2: Verificación de Integridad de Pivotes y Determinismo
```bash
cd /root/botero-trade && PYTHONPATH=/root/botero-trade:research/01_señales_entry_exit backend/.venv/bin/python -c "
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)
legs = repo.get_confirmed_legs('SPY', 'zz25')
store.close()

df_new = pd.read_pickle('data/research/pivots/quants_obs_new.pkl')
print(f'Repo legs: {len(legs)} | quants_obs_new rows: {len(df_new)}')
assert len(legs) == len(df_new), 'Mismatch en cantidad de pivotes'
print('>>> PIVOTES SPY zz25 VERIFICADOS AL 100% <<<')
"
```

### Script 3: Disparo de Señales y Clasificación Diamante (§3.3)
```bash
cd /root/botero-trade && PYTHONPATH=/root/botero-trade:research/01_señales_entry_exit backend/.venv/bin/python -c "
import pandas as pd, numpy as np, sys
sys.path.insert(0, 'research/01_señales_entry_exit')
from arnes import SEÑALES

df = pd.read_pickle('data/research/pivots/quants_obs_new.pkl')
print(f'=== DISPARO DE SEÑALES SOBRE TABLA NUEVA (N={len(df)}) ===')
print(f'{\"Señal\":32s} | {\"N\":>5s} | {\"Fire Rate\":>9s} | {\"Categoría\":>12s}')
print('-' * 65)

for name, fn in sorted(SEÑALES.items()):
    try:
        mask = fn(df).astype(bool)
        n = mask.sum()
        rate = f'{n/len(df):.1%}'
        cat = 'DIAMANTE' if n < 21 and n > 0 else ('ROBUST' if n >= 100 else 'STANDARD')
        print(f'{name:32s} | {n:5d} | {rate:>9s} | {cat:>12s}')
    except Exception as e:
        print(f'{name:32s} | ERROR: {e}')
"
```

### Script 4: Verificación en Vivo de Servicios de Dominio Puro (METAR, SIGMET, NOTAM)
```bash
cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
from backend.modules.entry_decision.domain.services.market_sigmet_hazard_service import evaluate_market_sigmets
from backend.modules.entry_decision.domain.services.notam_incident_service import evaluate_operational_notams
from backend.modules.entry_decision.domain.services.convergence_compositor import ConvergenceCompositor

print('=== VERIFICACIÓN EN VIVO DE SERVICIOS METAR, SIGMET, NOTAM ===\n')
comp = ConvergenceCompositor()
res = comp.compute()
print(f'✅ Compositor: Score={res.composite_ev_1d:+.4f} | Estaciones={res.active_stations}/11 | Guidance={res.unified_guidance}')

sigmets = evaluate_market_sigmets()
print(f'✅ SIGMET: {len(sigmets)} alertas activas')
for s in sigmets:
    print(f'   🚨 [{s.station}] {s.hazard_type} ({s.severity}) -> {s.operational_action}')

notams = evaluate_operational_notams()
print(f'✅ NOTAM: {len(notams)} incidentes técnicos activos')
"
```

---

## 5. FORMATO DE ENTREGA DEL INFORME DE AUDITORÍA

El auditor (sea humano o LLM evaluador) debe estructurar su dictamen bajo la siguiente plantilla estándar:

```markdown
# INFORME DE AUDITORÍA INTEGRAL — Ecosistema METAR, TAF, SIGMET y Señales

## 1. RESUMEN EJECUTIVO Y SCORECARD GENERAL
- **Veredicto Global:** [APROBADO / APROBADO CON CONDICIONES / RECHAZADO]
- **Nivel de Madurez Operativa:** [Escala 1 a 10]
- **Riesgo Sistémico Residual:** [BAJO / MEDIO / CRÍTICO]

| Dimensión | Estado | Confianza | Severidad de Gaps |
|---|:---:|:---:|:---:|
| D1: Telemetría METAR (11 estaciones) | [OK / OBS] | [%] | [P0-P3] |
| D2: Motor TAF & Tríada Estocástica | [OK / OBS] | [%] | [P0-P3] |
| D3: Seguridad SIGMET & NOTAM | [OK / OBS] | [%] | [P0-P3] |
| D4: Catálogo de Señales & Diamantes | [OK / OBS] | [%] | [P0-P3] |
| D5: Puntos Ciegos & Quiebres | [OK / OBS] | [%] | [P0-P3] |
| D6: Arquitectura Hexagonal | [OK / OBS] | [%] | [P0-P3] |
| D7: Transición a Tide y Rotación | [OK / OBS] | [%] | [P0-P3] |

## 2. ANÁLISIS CRÍTICO DIMENSIÓN POR DIMENSIÓN
[Detallar hallazgos, evidencia matemática, fórmulas y veredictos específicos para cada una de las 7 dimensiones.]

## 3. DICTAMEN DE SESGOS IA OCCIDENTALES DETECTADOS
[Identificar y corregir explícitamente cualquier recomendación previa sesgada por anti-diamond bias, suavizamiento bayesiano ciego o sicofancia.]

## 4. MATRIZ DE RIESGOS FORENSES (P0 a P3)
| # | Riesgo / Punto Ciego | Severidad | Impacto Operativo | Solución Determinista |
|---|---|:---:|---|---|
| 1 | ... | P0/P1/P2/P3 | ... | ... |

## 5. HOJA DE RUTA DE CIERRE DE ETAPA Y TRANSICIÓN
- **Acciones Bloqueantes Previas al Cierre:** [Lista concisa de fixes]
- **Artefactos a Congelar:** [Lista de archivos versión canónica]
- **Directrices de Entrada a Tide Engine:** [Protocolo de integración]
- **Directrices de Entrada a Rotación Sectorial:** [Protocolo de integración]
```

---
*Fin del Prompt Maestro de Auditoría. Ejecutar con rigor institucional y sin concesiones teóricas.*
