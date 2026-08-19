# PLAN DE TRABAJO — Botero Trade METAR (ordenado)

> Estado: 4 agentes auditores corriendo. Este plan ordena TODO lo pendiente.

---

## FASE 0 — AUDITORÍA DE CÓDIGO (en curso)
- [x] Código completo convergence_compositor.py (975 líneas) — deleg_088842a6 ✅
- [ ] Cascade revalidación (D2/D3 agregan o degradan) — deleg_4a1b8e98 🔄
- [ ] Entry/Exit revalidación — deleg_9fe73515 🔄
- [ ] TAF auditoría (ftt_days, ev_per_day, multi-escala) — deleg_73fc2e73 🔄
- [ ] Regímenes revalidación — deleg_f7cc0932 🔄

## FASE 1 — CORRECCIÓN DE BUGS (prioridad alta)
1. D3 std(5)/std(20) → std(2)/std(10) ✅ corregido + guard test
2. BSI ticker S5FI → S5TW ✅ corregido
3. c75 clon de c50 ✅ corregido (0.50/0.50)
4. VOL_ACCELERATING_EXPANSION nunca asignado ✅ corregido (4 edges)
5. Regenerar 5 fact stores stale ✅ hecho
6. 🔴 **EDGES TRAILING 3 AÑOS** — cambiar `ind_df.quantile()` → `ind_df.tail(756).quantile()` en v3_fact_table_engine.py (líneas 473-475). Aplica a D1/D2/D3 de TODAS las series. Resuelve el drift secular de SKEW (+23 pts) y DXY (+8.5 pts).

## FASE 2 — REVALIDACIÓN CON ESCALAS CALIBRADAS
- Todo lo calculado con "VIX ≥ 30" o terciles crudos DEBE rehacerse con bins D1/D2/D3
- Matriz de oportunidad, timing, early warning, benchmark

## FASE 3 — EVENTOS RAROS (N<10) — PENDIENTE PROFUNDIZAR
**Error cometido:** promediar retornos SIN separar operaciones ganadas vs fallidas, sin medir el costo de fallar vs el beneficio de acertar.
- Solo VIX estudiado (y con errores de escala)
- Falta: estudio por estación, uplift, max drawdown, distribución de wins/losses
- Orphan State Vector Interpreter: diseñado, sin validar a fondo

## FASE 4 — D2 y D3 — QUÉ APORTAN
- D2: contraria dirección (comprar miedo ✅, vender euforia ❌ mito)
- D3: filtro cascade (FG/VVIX/BSI/PCR -15pp, SKEW +4pp invertido, macro neutro)
- Pendiente: grado de acierto, estadísticas, retornos en tiempo del zigzag

## FASE 5 — ENTRY/EXIT EN PRODUCCIÓN
- Entrada: CRISIS_SPIKE + D2 flip ↓ + D3 filtro
- Salida: D2 flip ↑ o D3 expansión (zigzag NO disponible en producción)
- Pendiente: validar que los filtros eliminan el left tail -25%

## FASE 6 — INTEGRACIÓN + PROMPTS A GEMINI
- TAF completo (ftt_days, ev_per_day, zz50/zz75 multi-escala)
- Orphan interpreter
- Entry/exit signals
- Regeneración de fact stores

---

## MÉTRICAS OBLIGATORIAS (dato mata relato)
- Cada señal: probabilidad + CI95 + N
- Costo de fallar (max drawdown, distribución de losses)
- Beneficio de acertar (distribución de wins)
- Uplift (vs baseline)
- No promediar sin separar wins/losses
