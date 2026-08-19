# INVENTARIO — Información desperdiciada (actualizado post-auditoría 14-Ago-2026)

> **Leyenda:** ✅ Resuelto | 🔧 En plan | ⏳ Pendiente | ❌ Refutado

---

## 1. ✅ D2 dirección de velocidad
**Antes:** D2 predice dirección (ρ=0.40) mejor que D1 (ρ=0.12), pero el cascade_conviction no lo usa.
**Ahora:** El state vector YA captura D2 (implícito en state_key D1×D2×D3). Ajuste de velocidad adicional no ayuda (w≈0, doble conteo). **La velocidad está donde debe estar: en el state_key.**
→ **Resuelto. No se necesita acción adicional.**

---

## 2. ✅ Contraste "formándose vs resolviéndose"
**Antes:** Mismo D1, D2 opuesto → implicación opuesta. El cascade los trata igual.
**Ahora:** El state_key YA distingue (CRISIS__FAST_CRUSH ≠ CRISIS__FAST_SPIKE). El state vector usa esta distinción (zk_p_bull por estado completo). El cascade (capa 2) sigue siendo D1-only para SU target (continuación).
→ **Resuelto para state vector. El cascade no lo necesita (ortogonal).**

---

## 3. 🔧 zigzag_kinematic (~50 campos)
**Antes:** Calculados y NUNCA leídos.
**Ahora:** El state vector YA usa `zk_p_bull`. El TAF expondrá `p_bull`, `e_days`, `ev_net`.
→ **En plan (DirectionalStateVector + TAFEntry). ~80 líneas.**

---

## 4. 🔧 SV5T — sensor de volumen de batalla
**Antes:** Mal clasificado como "modulador de confianza" en Grupo B.
**Ahora:** Comprendido: es sensor de VOLUMEN DE BATALLA (dirección neutral). Rol corregido: Grupo B como TIMING. Cuadrante VIX×SV5T validado (gap 48.9pp cascade).
→ **En plan (capa 3 — confirmadores).**

---

## 5. ⏳ Matriz de convicción S5×SV5
**Antes:** Documentada en el calculator, no expuesta en el ConvergenceReport.
**Ahora:** Sin cambios. Documentada pero no expuesta.
→ **Pendiente. Baja prioridad.**

---

## 6. 🔧 D3 volatilidad — estabilidad
**Antes:** Ignorada. Sin uso en cascade ni state vector.
**Ahora:** 🚨 **BUG encontrado y corregido** (std 5/20 → std 2/10, 69% de días con D3 incorrecto). D3 funciona como MODULADOR DE CONFIANZA: baja vol → IC -0.46, alta vol → IC -0.34 (99% confianza).
→ **En plan (confidence_modifier en DirectionalStateVector).**

---

## 7. ✅ 150 estados colapsados a 6
**Antes:** El cascade_conviction colapsa state_key D1×D2×D3 → solo D1.
**Ahora:** El state vector (capa 1) YA usa los 150 estados completos (zk_p_bull por estado). El cascade (capa 2) sigue D1-only para cascade (validado PBO=0%). Son capas separadas con targets distintos.
→ **Resuelto. Arquitectura de 2 capas ortogonales.**

---

## 8. ✅ Naturaleza única de cada estación
**Antes:** Todas tratadas como "¿vota dirección?" — ignorando su rol real.
**Ahora:** Comprendido: VIX anticipa, SV5T sincroniza, SKEW cubre (pared gamma), PCR es contrario. Familias refutadas (clustering k-means). Cada estación es más independiente de lo esperado.
→ **Resuelto. Las estaciones se usan planas (11), no por familias.**

---

## 9. ⏳ intermarket_mechanics
**Antes:** Documentada en cada fact store (vix_spike, credit_stress, dxy_flows...). No se usa.
**Ahora:** Sin cambios.
→ **Pendiente. Posible uso en capa 3 (confirmadores/SIGMET).**

---

## 10. 🔧 TAF (pronóstico)
**Antes:** No expuesto en ConvergenceReport.
**Ahora:** Diseñado: DirectionalStateVector (p_bull, direction, confidence, cold_start_pct). TAFEntry por estación (p_bull, e_days, ev_net, D2/D3 labels).
→ **En plan (~80 líneas, 80% del valor).**

---

## 📊 Resumen

| Estado | Conteo | Items |
|---|---|---|
| ✅ Resuelto | 4 | D2 dirección, contraste formando/resolviendo, 150 estados, naturaleza única |
| 🔧 En plan | 4 | zigzag_kinematic (TAF), SV5T (confirmador), D3 confianza, TAF exponer |
| ⏳ Pendiente | 2 | S5×SV5, intermarket_mechanics |
| ❌ Refutado | — | Familias, triple barrier, decantado, Kronos en METAR |