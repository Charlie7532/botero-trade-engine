# Prompt de Cierre y Consolidación — Opus v3 + Hallazgos Complementarios (Corregido v2)

> **Propósito:** Prompt definitivo para Claude. Incorpora los hallazgos de sus auditorías, las pre-validaciones empíricas que ya ejecutó, las correcciones que los datos revelaron, y la auditoría forense de Gemini sobre consumo de campos del Fact Store. El objetivo es un plan único con 11 ejercicios, 6 de los cuales ya tienen resultado conocido.
>
> **v2 (31-Ago):** Integra correcciones aprobadas de `correcciones_prompt_cierre_v3.md`:
> - Campos Estándar ya extraídos que nadie lee (e_ret_max, rr_asymmetry, ev_per_day)
> - E11 completamente especificado (3 sub-tests: Sign-Consistency, EV Gradient, FTT Collapse)
> - Integración con arnés de investigación (`arnes/señales.py` + `evaluador_vela_a_vela.py`)
> - Eliminación de `CinematicaBullService` (no requiere servicio, requiere consumo directo)
>
> **Base:** respuesta de Claude (pre-validación empírica E7-E10)
> **Arquitecto:** Juan Andrés Botero
> **Filosofía:** El compositor usa 7 de 117 campos = 6%. No es error del Fact Store. Es error de consumo.

---

## ⚠️ Lo que ya sabemos antes de empezar

Claude pre-validó E7-E10 contra los Fact Stores reales. Esto ahorra iteraciones. Los resultados:

| Ejercicio | Propuesto | Resultado real | Acción |
|---|---|---|---|
| E1-E6 (v3 original) | Phase, Confluencia, Divergence, CV, Euphoria, RR | Sin pre-validar | Ejecutar |
| **E7** (Zona Neutral) | D2 discrimina dentro de D1 neutral | ✅ **VALIDADO pero INVERTIDO** — CRUSH > SPIKE en 8/11 estaciones (mean-reversion, no building) | **Ejecutar con hipótesis corregida** |
| **E8** (Structural Momentum) | Clasificar UPTREND/DOWNTREND | ⚠️ **95% RANGE con umbrales 0.55/0.45** — pero ese 5% son diamantes. **§3.3: no descartar por rareza, estudiar** | **Aplicar §3.3: bajar umbrales a 0.52/0.48 o usar p_raw. El 5% clasificado vale más que el 95% RANGO** |
| **E9** (Cascade Rate) | Discrimina severidad | ⚠️ **Solo 2/5 estaciones con datos; solo BSI funciona** — pero §3.3 dice rareza = riqueza | **Aplicar §3.3: N bajo = diamante. Bajar umbral HIGH>0.5 / LOW<0.4, usar ZZ25. Si solo BSI tiene edge, BSI es suficiente** |
| **E10** (Cinemática vs Estándar) | ¿Cuál es más discriminativa? | ✅ **Kinematic gana 8/11 estaciones** — BSI: -15pp spread vs -0.8pp estándar | **Integrar p_bull cinemático al compositor AHORA** |
| **E11** (Triada ZZ) | Convergencia/divergencia triadas | Sin pre-validar | **Ejecutar** |

---

## Correcciones a Ejercicios basadas en pre-validación

### E7 — ANATOMÍA ZONA NEUTRAL (hipótesis corregida)

**Hipótesis original:** D2=SPIKE tiene más edge que D2=CRUSH.

**Realidad:** **INVERTIDO.** D2=FAST_CRUSH tiene más EV que D2=FAST_SPIKE en 8/11 estaciones:

| Estación | CRUSH EV75 | SPIKE EV75 | Spread | N(crush) | N(spike) |
|---|---|---|---:|---:|---:|---:|
| SV5 Turbulence | +56.1bp | +12.2bp | **-43.8bp** | 170 | 20 |
| Credit | +3.8bp | -60.1bp | **-63.9bp** | 7 | 16 |
| Yield Curve | +54.4bp | +22.8bp | **-31.5bp** | 100 | 108 |
| VVIX | +35.5bp | +13.6bp | **-21.9bp** | 78 | 6 |
| PCR | +6.9bp | -6.1bp | **-12.9bp** | 34 | 5 |
| BSI | +22.0bp | +12.6bp | -9.4bp | 97 | 222 |
| VIX | +28.0bp | +20.9bp | -7.1bp | 115 | 60 |
| F&G | +33.7bp | +27.6bp | -6.1bp | 69 | 73 |
| SKEW | +26.9bp | +30.4bp | +3.6bp | 134 | 26 |
| DXY | +9.2bp | +50.0bp | **+40.8bp** | 67 | 54 |
| Rotation | +19.4bp | +62.7bp | **+43.2bp** | 84 | 108 |

**Mecánica:** Caída rápida de VIX en zona neutral = mean-reversion bullish. Spike rápido de VIX en zona neutral = ruido transitorio. DXY y Rotation son excepciones (dólar fuerte subiendo = compresión; rotación agresiva a cíclicos = bullish).

**Hipótesis corregida para el ejercicio:** D2=CRUSH dentro de D1 neutral es la señal con edge real. El criterio de corte (10bp en ≥3 estaciones) se cumple sobradamente (SV5T, Credit, Yield, VVIX, DXY, Rotation).

### E8 — STRUCTURAL MOMENTUM (corregido con umbrales más bajos)

**Realidad:** Con umbrales 0.55/0.45, ~95% de los estados clasifican como RANGO. El Bayesian shrinkage m=10 aplasta los valores hacia 0.50.

**⚠️ APLICAR PROTOCOLO §3.3 — RAREZA = RIQUEZA:**
Que el 95% sea RANGO no significa que el 5% restante no tenga valor. Ese 5% son los eventos raros donde la estructura de mercado es definida — y son los que más importan para decisiones de entrada/salida. No se descartan. Se estudian con la lente de diamantes.

**Método corregido:**
1. **Probar primera alternativa:** Usar `p_raw` en vez de `p_bayesian` para la clasificación — el dato crudo tiene más varianza y puede discriminar
2. **Probar segunda alternativa:** Bajar umbrales a P(HL) > 0.52 / < 0.48
3. **Probar tercera alternativa:** Usar escala ZZ25 (más N, menos afectado por shrinkage)
4. **Para los estados que SÍ clasifican (UPTREND, DOWNTREND, DIVERGENCIA):** medir EV75, N, CI95. Si N < 21, aplicar §3.3 — diamante, reportar evento por evento
5. **Conclusión:** ¿Los estados clasificados tienen edge exploitable aunque sean pocos? Si los pocos que clasifican tienen EV > 50bp, valen más que mil estados RANGO con EV ≈ 0
6. **NO descartar por "mayoría RANGO".** Documentar el edge de la minoría clasificada.

### E9 — CASCADE RATE (corregido con umbrales más amplios)

**Realidad:** Solo 2/5 estaciones tienen suficientes estados con cascade data y N≥10. De esas, solo BSI muestra spread significativo (-28bp).

**⚠️ APLICAR PROTOCOLO §3.3 — RAREZA = RIQUEZA:**
N bajo NO es "datos insuficientes". Es **exactamente donde están los diamantes.** Los eventos de cascade_rate > 0.6 son raros por definición — son los que más importan. No se archivan. Se estudian con:
- Tasa cruda (sin shrinkage)
- CI95 Clopper-Pearson (no bootstrap)
- Sin Bonferroni
- Análisis evento por evento (fecha, contexto, resultado)

**Método corregido:**
1. Bajar umbral: HIGH cascade > 0.5, LOW cascade < 0.4
2. Usar escala ZZ25 (más N en terciles domino) en vez de ZZ50
3. Para estados con N < 21: aplicar §3.3 — reportar tasa cruda + CI95 + listar cada evento individual
4. Para estados con N ≥ 21: aplicar estadística estándar
5. **NO descartar ninguna estación por N bajo.** Si N es bajo, se reporta como diamante con su contexto
6. Conclusión: ¿es útil como señal puntual (diamante) o como clasificador poblacional?

**Output:** `data/research/metar_cascade_severity.json`

---

## Mapa de Ejercicios Consolidado (11)

| # | Ejercicio | Prioridad | Estado de validación | Output |
|---|---|---|---|---|
| 1 | Phase Quadrants D1×D2 (297 celdas) | 🔴 P0 | Sin pre-validar | `metar_phase_quadrants.json` |
| 2 | Gaussian Confluence Multi-Estación | 🔴 P0 | Sin pre-validar | `metar_gaussian_confluence.json` |
| 3 | **Divergence Regime (Fact Store)** | 🟡 P1 | ⚠️ **Pre-validar** | `metar_divergence_regime_check.json` |
| 4 | Capital Velocity × Horizon | 🟡 P1 | Sin pre-validar | `metar_capital_velocity_horizons.json` |
| 5 | Euphoria Confluence (lado bullish) | 🟡 P1 | Sin pre-validar | `metar_euphoria_confluence.json` |
| 6 | RR Asymmetry (fast-check, descartable) | 🟢 P2 | Sin pre-validar | `metar_rr_asymmetry_analysis.json` |
| **7** | **Anatomía Zona Neutral D1(2,3)×D2** | **🔴 P0** | **✅ Parcial — hipótesis INVERTIDA** | **`metar_neutral_zone_anatomy.json`** |
| **8** | **Structural Momentum** | **🟡 P1** | **⚠️ 95% RANGE con umbrales originales** | **`metar_structural_momentum_trend.json`** |
| **9** | **Cascade Rate Severity** | **🟢 P2** | **⚠️ Datos insuficientes, solo BSI** | **`metar_cascade_severity.json`** |
| **10** | **Cinemática vs Estándar** | **🔴 P0** | **✅ Kinematic gana 8/11** | **`metar_kinematic_vs_standard.json`** |
| **11** | **Triada ZZ Convergencia/Divergencia** | **🔴 P0** | Sin pre-validar | **`metar_triada_convergencia_divergencia.json`** |

### ⚠️ Nota sobre E3 — Divergence Regime (Fact Store nativo)

El divergence_regime del Fact Store (FULL_CONVERGENT_BEAR, TACTICAL_REBOUND_IN_BEAR, etc.) no tiene pre-validación de Claude. Sin embargo, experiencias previas sugieren que puede no discriminar tan claramente como se esperaba:

- El divergence_regime del Fact Store usa thresholds similares a los de Structural Momentum
- Si el Bayesian shrinkage afecta igual, la clasificación puede ser mayoritariamente MIXED_HORIZON_TRANSITION
- **Recomendación:** Pre-validar E3 con la misma metodología que Claude usó para E7-E10 antes de decidir si implementar como servicio

---

## Asignación de Capas a Consumidores (Pre-validada)

Basado en los previews de Claude, la asignación se puede resolver AHORA:

| Capa | Consumidor | Evidencia |
|---|---|---|
| **Estándar completa** (e_ret_max, rr_asymmetry, ev_per_day) | **Compositor METAR** | Ya extraída en dataclass `MarketMETAR`. Solo falta leerla. |
| **Cinemática p_bull** | **Compositor METAR** | Gana 8/11 estaciones en spread discriminativo. Integrar AHORA. |
| **Cinemática resto** (e_ret_max leg, ftt, rr) | **Ceiling/Floor Engine futuro** | Horizonte variable (duración de pierna), no fijo. No apto para METAR diario. |
| **Structural Momentum** | **Compositor (canal menor)** — solo el 5% que clasifica, pero ese 5% son diamantes con edge potencial. NO descartar. |
| **Cascade Rate** | **Compositor (señal puntual)** — aplicar §3.3: N bajo = diamante, no archivar. Si solo BSI funciona, BSI es suficiente. |
| **FTT (time to target)** | **Ceiling/Floor Engine + Time Stop** | Horizonte variable, no compositor. |

---

## Reorganización: Fases Revisadas

### Fase 0 — Correcciones Estructurales (INCLUYE bug D1_BEARISH_BINS + consumo de campos)

1. ✅ Añadir DXY al router + tests
2. ✅ Corregir `registered_count == 10` → 11 en tests
3. ✅ Completar NOTAM (staleness + FOMC blackout)
4. **🔴 NUEVO: Migrar D1_BEARISH_BINS y D1_BULLISH_BINS de labels string a bins numéricos** en `convergence_compositor.py` y en `d1_directional_vote()`. Bug funcional existente.
5. **🔴 NUEVO: Consumir campos Estándar ya extraídos por los lookups.** El `to_vector()` de cada lookup ya emite `e_ret_max`, `e_ret_min`, `rr_asymmetry`, `ev_per_day` por escala ZZ en el dataclass `ScaleGuidance` (ej. `vix_lookup.py` L154-158). El compositor los ignora. Extender `_compose()` para:
   a) Leer `rr_asymmetry.zz75` de cada estación → contar cuántas tienen RR>1.0 → emitir `n_convex_stations`
   b) Leer `e_ret_max.zz75` y `e_ret_min.zz75` → emitir en `station_summaries` para consumo por Risk Manager
   c) **NO crear canales nuevos** hasta que E6 (RR Asymmetry) valide que discriminan. Esfuerzo: ~20 líneas en compositor, 0 lookups nuevos.

### Fase 1 — Ejercicios Probatorios (11, con hipótesis corregidas)

> **⚠️ NOTA METODOLÓGICA (v2):** Los ejercicios E1-E11 DEBEN formularse como señales
> registradas en `research/01_señales_entry_exit/arnes/señales.py` con `@_registrar()`.
> Cada ejercicio produce:
> 1. **Señal registrada** → evaluable con `evaluador_vela_a_vela.py --señal <nombre>`
> 2. **JSON de resultado** → en `data/research/`
> 3. **Validación OOS** → con `validador_oos.py` (walk-forward anclado, seed=42)
>
> Framework existente (NO crear scripts ad-hoc):
> - `arnes/señales.py`: 28+ señales registradas con `@_registrar`
> - `evaluador_vela_a_vela.py`: first-passage por escala ZZ, hit/miss, MAE/MFE
> - `validador_oos.py`: walk-forward anclado, decay IS→OOS
> - `audit_overflow_candle_anatomy_v2.py`: anatomía de velas en overflows σ

- E1-E6: Ejecutar (Phase, Confluencia, Divergence Regime, CV, Euphoria, RR)
- E7: **Hipótesis corregida**: CRUSH > SPIKE en zona neutral (mean-reversion, no building)
- E8: **Con umbrales corregidos**: 0.52/0.48 en vez de 0.55/0.45, o usar p_raw, o ZZ25
- E9: **Con umbrales corregidos**: HIGH > 0.5 / LOW < 0.4, usar ZZ25. Si falla, archivar
- E10: ✅ Validado. Kinematic > Standard en 8/11. Proceder a consumo directo en compositor (no servicio)
- E11: **Triada ZZ — Método completo (v2):**
  - **E11a (Sign-Consistency):** ¿p_bull concuerda en las 3 escalas? Clasificar: `CONVERGENT_BULL` (3 escalas >0.52), `CONVERGENT_BEAR` (3 <0.48), `DIVERGENT_EXHAUSTION` (táctico bull/estructural bear), `DIVERGENT_REVERSAL` (táctico bear/estructural bull), `MIXED`. Criterio: EV_CONVERGENT > 2× EV_MIXED en ≥3 estaciones.
  - **E11b (EV Gradient):** ¿EV crece con la escala? `gradient = ev75 - ev25`. Si >0.002 → `AMPLIFYING`, si <-0.002 → `DECAYING`, else `FLAT`. Criterio: AMPLIFYING con WR75 > 60% en ≥3 estaciones.
  - **E11c (FTT Collapse):** ¿ftt75/ftt25 < 3.0? Solo capa cinemática. `COMPRESSED` = movimiento violento en todas las escalas. Criterio: ¿COMPRESSED coincide con crashes/rallies documentados?

### Fase 1b — Verificación de Consumidores

Ya resuelta por los previews de Claude. Ver tabla de asignación arriba.

### Fase 2 — Servicios de Dominio (solo hallazgos confirmados)

- `PhaseQuadrantClassifier` (con corrección E7: CRUSH > SPIKE en neutral)
- `ConfluencePhaseAggregator` (con zona neutral incluida)
- ~~`CinematicaBullService`~~ → **ELIMINADO (v2).** No requiere servicio nuevo. El p_bull cinemático se consume directamente en el compositor extendiendo `_compose()` para leer `zigzag_kinematic.zz75.p_bull` del estado JSON. Los lookups (10 de 11) deben extenderse para emitir `zigzag_kinematic` igual que `dxy_lookup.py` ya lo hace (L210).
- **NO crear**: `StructuralMomentumClassifier`, `CascadeRateService`, `DivergenceRegimeAggregator` a menos que los ejercicios corregidos demuestren lo contrario

### Fase 3-5 — Compositor, Router, Frontend

Sin cambios estructurales.

---

## Anti-Patrones (23)

Además de los 10 de Opus (que se mantienen):

11. ❌ Ignorar la zona neutral porque "no es extrema" → 68% de los días viven ahí, y D2 discrimina
12. ❌ Tratar las 4 capas del Fact Store como si fueran para el mismo consumidor
13. ❌ Implementar servicios de capas ignoradas sin validar que aportan edge incremental
14. ❌ **DEJAR D1_BEARISH_BINS CON LABELS STRING** → migrar a bins numéricos en Fase 0
15. ❌ Dejar convergence compositor sin tests (652 líneas, 0 tests)
16. 🆕 ❌ Asumir que D2=SPIKE en zona neutral tiene edge positivo (está INVERTIDO: CRUSH gana)
17. 🆕 ❌ Usar umbrales de Structural Momentum 0.55/0.45 sin verificar que el Bayesian shrinkage no los destruye
18. 🆕 ❌ Descarte por "N bajo" o "mayoría RANGO" — §3.3: rareza = riqueza. N bajo es diamante, no defecto. El 95% RANGO no invalida el 5% que sí clasifica.
19. 🆕 ❌ Aplicar Bonferroni o bootstrap a señales con N < 21 — §3.3 explícitamente lo prohíbe
20. 🆕 ❌ Tratar "solo una estación funciona" como insuficiente — si BSI tiene cascade edge, BSI se integra. No se necesita que 5/5 estaciones tengan edge.
21. 🆕 ❌ **Crear servicios nuevos para datos que ya están en el dataclass.** `e_ret_max`, `e_ret_min`, `rr_asymmetry` ya viajan en `ScaleGuidance` (8 campos × 3 escalas = 24 campos extraídos). No requieren servicio nuevo. Solo requieren que el compositor los LEA (~20 líneas).
22. 🆕 ❌ **Ejecutar ejercicios con scripts ad-hoc fuera del arnés.** Todo ejercicio que produzca una señal evaluable DEBE registrarse en `arnes/señales.py` y validarse con `evaluador_vela_a_vela.py` + `validador_oos.py`. Scripts sueltos no son reproducibles ni catalogables.
23. 🆕 ❌ **Definir un ejercicio P0 sin método.** Todo ejercicio debe tener: pregunta, método, criterio de corte, y output path. Sin método = sin criterio de descarte = sin rigor.

---

## Lo que NO cambia del v3 de Opus

- ✅ Los 6 ejercicios originales se mantienen intactos (E1-E6)
- ✅ La arquitectura de servicios (Phase Quadrant, Confluence Phase Aggregator)
- ✅ Los 3 channels del compositor se mantienen, solo se extienden
- ✅ La Opción C del frontend
- ✅ Los anti-patrones originales
- ✅ La verificación por fases