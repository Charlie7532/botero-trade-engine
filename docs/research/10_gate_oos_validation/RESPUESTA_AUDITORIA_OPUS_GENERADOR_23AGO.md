# RESPUESTA A AUDITORÍA EXTERNA — Generador `quants_obs` (Opus 4.6, 23-Ago)
**Fecha:** 23-Ago-2026 · **Firma:** qwen/qwen3.8-max (Hermes)
**Auditoría:** `auditoria_externa_generador_quants_obs.md` (Claude Opus 4.6 via Antigravity)
**Principio aplicado:** cada hallazgo se verifica con datos propios ANTES de aplicar el fix.

---

## VERIFICACIÓN INDEPENDIENTE DE LOS 4 HALLAZGOS

Todos los hallazgos fueron verificados con datos propios antes de aplicar nada:

| Hallazgo | Verificación propia | ¿Confirmado? |
|----------|--------------------|:---:|
| F1 (P0): z_bear hardcoded diverge de producción | cal-file actual μ=0.41 σ=0.3206; builder 0.3299/0.2856 → **284/1,590 inversiones de signo (17.9%)**, cascade 145 (9.1%) | ✅ confirmado |
| F2 (P1): panico_total 34→11, skew_paranoia_exit 26→10 | re-ejecutadas ambas señales sobre ambas tablas: 34→11 y 26→10 exactos | ✅ confirmado |
| F3 (P1): fórmula d1_bear_5 frágil | votos actuales ∈ {−1,0,1} en las 5 estaciones → fórmulas idénticas HOY, frágiles ante votos fraccionarios | ✅ confirmado |
| F4 (P2): 236 fechas duplicadas | contadas en la tabla nueva: 236 (propiedad del zigzag, presente también en el original) | ✅ confirmado |

## FIXES APLICADOS (builder v6)

### F1 — ✅ APLICADO (Opción C de la auditoría)
`Z_BEAR_MU/SIGMA` ahora se leen dinámicamente de `cascade_calibration.json` con fallback
a los defaults del compositor. **z_bear ahora es consistente con la producción actual:
0% de inversiones de signo** (antes 17.9%). El match vs el one-off original cae a ~0%
a propósito — el one-off fue generado con calibración obsoleta. Consistencia con
producción > fidelidad al artefacto, según el propósito declarado.
Nota: `cascade_reversal` pasa de 1,075 a 1,205 disparos (la calibración actual
reclasifica algunas filas bajo el umbral 0.30).

### F3 — ✅ APLICADO
`d1_bear_5` ahora usa el CONTEO `count(v<0)/n` — la fórmula exacta de producción
(convergence_compositor.py:484) — en vez de `Σ(max(0,−v))/n`. Robusta ante futuros
votos fraccionarios.

### F4 — ✅ APLICADO (documentación)
Limitación de las 236 fechas duplicadas documentada en el builder con warning activo
al ejecutar: cualquier futuro consumidor que haga `groupby(pivot_date)` debe deduplicar.

### F2 — DECISIÓN DIFERENTE a la recomendación, por principio establecido
La auditoría recomienda reclasificar `panico_total` (N=11) y `skew_paranoia_exit` (N=10)
como "Grade D" por inviabilidad OOS. **Se aplica en cambio el protocolo de diamantes
establecido** (fact_store_v3_architecture §3.3 + corrección explícita del arquitecto):
N<21 = diamante anecdótico, nunca degradar por muestra baja. Ambas señales quedan:
- Etiquetadas con sensibilidad CAT-A documentada (su N cambió por reclasificación SKEW,
  un artefacto del one-off, no por pérdida de información real).
- Con la observación de que el régimen de crisis ±3σ las agrupa (lifts 3.5-4.6x tras
  extremos, medido 22-Ago) — contexto que refuerza su valor como diamantes.
- Pendiente de recalificación solo si se encuentra una clasificación SKEW D1 más estable.

## ESTADO DEL GENERADOR v6

| Métrica | Valor |
|---------|-------|
| Columnas ≥99.9% match con el original | 101/141 (z_bear/cascade ahora 0% **a propósito**) |
| CAT-A / CAT-B / CAT-C | 12 / 37 / **0** |
| Señales que disparan | 28/28 (cero inertes) |
| Determinismo | bit-a-bit (verificado por el auditor, hash idéntico en 2 runs) |
| Consistencia z_bear con producción | **100%** (0 inversiones de signo) |

## VEREDICTOS DEL AUDITOR CONFIRMADOS
- P1 pivotes: APROBADO (1,590/1,590 idénticos a repo y original)
- P2 estado dimensional: APROBADO (0 huérfanos, fórmulas vs política AGENTS.md)
- P3 cascade: OBSERVACIÓN → **resuelta con fix F1**
- P4 decisiones CAT-A: APROBADAS ambas
- P5 impacto aguas abajo: 5/8 señales núcleo 100% idénticas; 2 con sensibilidad CAT-A; 1 bug corregido
- P6 reproductibilidad: APROBADO (determinista)
