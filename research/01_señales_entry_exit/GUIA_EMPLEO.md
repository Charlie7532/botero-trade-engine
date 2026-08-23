# GUÍA DE EMPLEO — medir_senal.py
## Mapa Dato → Pregunta → Decisión

> Cada campo del JSON de medición responde una pregunta y informa una decisión concreta.
> Formato alineado con fact_store_v3_architecture.md §15.1.
> Versión: 20-Ago-2026 (incluye Addenda 1-3: structural_momentum, prev_leg_context, divergence_regime)

---

## 1. Distribución y Significancia

| Campo | Pregunta que responde | Decisión que informa | Ejemplo de uso |
|-------|----------------------|---------------------|----------------|
| `activa.dist.mean` | ¿Cuál es el retorno forward medio? | Edge esperado de la señal | credit_easing_k1: +5.19% → ofensiva fuerte |
| `activa.dist.p5` | ¿Cuál es el peor escenario (5%)? | Sizing máximo de posición | P5 < −10% → sizing reducido obligatoriamente |
| `activa.dist.p95` | ¿Cuál es el mejor escenario (5%)? | Target de profit ambicioso | P95 > +10% → se puede dejar correr la ganancia |
| `activa.wl.mean_win` | ¿Cuánto gano cuando acierto? | Target de profit realista | mean_win +6.91% → tomar ganancias cerca de +6% |
| `activa.wl.mean_loss` | ¿Cuánto pierdo cuando fallo? | Stop loss implícito | mean_loss −9.22% → stop defensivo en −8% |
| `activa.wl.profit_factor` | ¿Gano más de lo que pierdo (bruto)? | Calidad del edge | PF > 2 → edge sano; PF < 1 → señal perdedora |
| `activa.ci_mean` | ¿Es significativo el edge? | GO / NO-GO de la señal | CI95 cruza cero → NO-GO (edge no confirmado) |
| `delta_media` | ¿Cuánto supera al baseline homogéneo? | Edge incremental real | Δ vs baseline MIN-only: +1.49% (el verdadero) |

## 2. Tríada ZigZag y Propagación

| Campo | Pregunta que responde | Decisión que informa | Ejemplo de uso |
|-------|----------------------|---------------------|----------------|
| `triada.zz25.mean` | ¿Retorno de la pierna completa? | Retorno esperado del trade | +1.42% → trade de magnitud pequeña |
| `triada.zz25.win_rate` | ¿Qué % de piernas son alcistas? | Confianza direccional | WR 93.8% → altísima confianza |
| `triada.cascade_50.delta` | ¿La señal predice corrección (5%)? | ¿La señal antecede movimientos mayores? | Δ > +20pp → sí, mantiene a través de la corrección |
| `triada.cascade_75.delta` | ¿La señal predice depresión (7.5%)? | ¿La señal atrapa crashes? | Δ > +30pp → captura crashes (alto valor defensivo) |
| `triada.duracion_bars.mean` | ¿Cuánto dura la pierna? | Horizonte temporal del trade | 3-5 barras → trade táctico de días |

## 3. Timing y Costo de Entrada

| Campo | Pregunta que responde | Decisión que informa | Ejemplo de uso |
|-------|----------------------|---------------------|----------------|
| `timing_temprano.estadistica.mean` | ¿Drawdown de entrar temprano (MAE)? | Tolerancia al dolor intra-trade | MAE −1.69% (P5 −5.02%) → dolor tolerable |
| `costo_tarde.mean_opp_cost` | ¿Cuánto pierdo si espero 1 barra? | Urgencia de entrada | +0.86% → entrar pronto, esperar cuesta ~0.9% |
| `sensibilidad.{k}` | ¿El edge sobrevive con retraso k barras? | Flexibilidad de ejecución | edge cae poco con k=2 → hay margen |
| `anticipacion_zigzag.median_dias` | ¿Cuántos días antes se anticipa? | Ventana de preparación | mediana 2 días → preparar con 2d de anticipación |

## 4. Calidad de Captura

| Campo | Pregunta que responde | Decisión que informa | Ejemplo de uso |
|-------|----------------------|---------------------|----------------|
| `capture_ratio.ratio` | ¿Qué fracción de la pierna capturo? | Eficiencia de entrada | ratio > 0.3 → buena captura del movimiento |
| `punteria.{escala}.capture_ratio` | ¿Captura por escala zz25/50/75? | Eficiencia según escala | mayor en zz50 → señal de correcciones |
| `offset_entrada.{±1}` | ¿Cuánto cambia si entro ±1 barra? | Precisión de timing | ±1 barra poco impacto → timing flexible |

## 5. Robustez Temporal

| Campo | Pregunta que responde | Decisión que informa | Ejemplo de uso |
|-------|----------------------|---------------------|----------------|
| `estabilidad_decada.{década}.wr` | ¿La señal es estable en el tiempo? | Confianza para el futuro | WR 89%→100%→94% → muy estable |
| `estabilidad_decada.{década}.mean` | ¿El edge cambia por década? | Riesgo de régimen | caída del edge en 2020s → monitorear (pcr_put_panic) |
| `lookback_crash.{escala}.señales` | ¿La señal precedió crashes pasados? | Valor como precursora | 100% de caídas zz50 precedidas → precursora fuerte |

## 6. Filtros de Contexto (D2/D3 y los nuevos Addenda)

| Campo | Pregunta que responde | Decisión que informa | Ejemplo de uso |
|-------|----------------------|---------------------|----------------|
| `desglose_d2d3.{est}.d2_velocity` | ¿Cuál es el mejor/peor sub-estado D2? | Filtro de entrada | entrar con D2=DECEL_DOWN (+5.17%), evitar FAST_CRUSH (−1.74%) |
| `desglose_d2d3.{est}.d3_station_vol` | ¿Cuál es el mejor/peor sub-estado D3? | Filtro de entrada | entrar con D3=VOL_COMPR (+5.42%), evitar VOL_EXP (−0.67%) |
| `structural_momentum.entry.p_hl` | ¿Los pisos hacen HL (comprables) o LL (trampas)? | Timing de entrada | p_hl > 0.55 → entrar; p_hl < 0.45 → esperar. Eje ORTOGONAL a p_bull (r=0.015) |
| `structural_momentum.exit.p_hh` | ¿Los techos hacen HH (distribución)? | Urgencia de salida | HH cae 90.2% → AMPLIFICAR EXIT, jamás ignorar |
| `prev_leg_context.pct_extreme` | ¿Venimos de un crash (pierna previa >P90)? | Amplificación del edge | umbral operativo >20-30% (el >50% es inalcanzable) |
| `prev_leg_context.forward_extreme_prev` | ¿El edge difiere post-crash vs drift? | Sizing condicional | forward extreme vs normal → ajustar tamaño |
| `divergence_regime.regime` | ¿Las escalas convergen o divergen? | Convicción del trade | FULL_CONVERGENT_BULL → convicción alta; TACTICAL_ONLY → trade táctico. Con N<3 → `DIAMANTE_ANECDOTAL` (protocolo diamantes §3.3: analizar cada evento individualmente, nunca descartar) |

## 7. Reglas de Lectura Rápida

1. **Antes de operar:** verificar `activa.ci_mean` (¿cruza cero?), luego `triada` (¿escala?).
2. **Dimensionar:** usar `activa.dist.p5` para el peor caso y `structural_momentum` para el timing.
3. **Filtrar:** aplicar `desglose_d2d3` (entrar solo en sub-estados "best") y `divergence_regime`.
4. **Contextuar:** revisar `prev_leg_context` (¿post-crash?) y `estabilidad_decada` (¿sigue vigente?).
5. **Los campos nuevos (structural_momentum, prev_leg_context, divergence_regime)** son derivados de quants_obs + SPY: el fact store NO los tiene nativos.

## 8. Tabla de Observación `quants_obs` (actualización 23-Ago-2026)

La tabla oficial `data/research/pivots/quants_obs.pkl` fue sustituida el
23-Ago-2026 por la versión auditada (3 auditorías externas Opus). **1,590
pivotes × 143 columnas.** Documentación completa:
`backend/scripts/generators/QUANTS_OBS_GENERATOR.md` (esquema, fórmulas,
divergencias CAT-A/B/C, limitaciones, checklist de auditoría).

**Columnas nuevas:**
- `cascade_conviction_50` — c50 del compositor de producción. La señal
  `cascade_reversal` leía este nombre y la columna no existía en el one-off
  original (señal inerte en silencio). Ahora dispara ~240 veces.
- `n_stations_a` — estaciones del Grupo A disponibles por pivote (2-5).
  El 64.2% de pivotes tiene <5 estaciones (primera fila completa: 2011-02-18).
  Usarla para segmentar análisis dependientes de `d1_bear_5`/`z_bear`.

**Estado de señales medidas sobre la tabla nueva:**
- Núcleo robusto (idéntico byte a byte en ambas tablas): `capitulacion`,
  `pcr_put_panic`, `vvix_entry`, `credit_stress`, `bsi_washed_out`.
- Diamantes §3.3 (N<21, nunca degradar): `panico_total` (N=11, 11/11 en
  crisis ±3σ), `skew_paranoia_exit` (N=10, 8/10 en crisis). Tratamiento:
  p_raw + CI95 Clopper-Pearson; análisis individual en
  `data/research/signals/diamantes_analisis_individual.json`.
- Degradadas: `breadth_contraction_exit` (break interno OOS),
  `credit_ease_exit` (reliquia pre-QE), `bsi_recovery` (post-QE).
- PROPOSED: `cascade_reversal` — umbral −0.957 congelado (calibración
  full-sample, fire rate 15%), edge +0.28% fijo / +0.44% walk-forward rolling
  p15, p>0.05 → requiere más evidencia antes de promoción.

**Limitaciones conocidas:** 236 fechas de pivote duplicadas (deduplicar en
cualquier groupby(pivot_date)); look-ahead de los fact stores (edges estáticos
calibrados con datos posteriores) — aceptado para medición post-mortem.

**Regenerar:** `backend/scripts/generators/generate_quants_obs.py` (determinista,
~40 s) + tests `backend/tests/test_quants_obs_builder.py` (7 tests).

---
**Firma:** qwen3.8-max (Hermes) · 20-Ago-2026 · Addenda 4 del prompt 5-addenda-algoritmos.md
**Actualización:** qwen3.8-max (Hermes) · 23-Ago-2026 · §8 tabla quants_obs auditada y sustituida
