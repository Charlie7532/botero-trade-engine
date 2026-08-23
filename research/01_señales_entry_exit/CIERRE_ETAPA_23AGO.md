# CIERRE DE ETAPA — 23-Ago-2026
**Firma:** qwen/qwen3.8-max (Hermes)

## Objetivo de la etapa
Culminar la cadena de observación canónica `quants_obs`: auditar el generador
nuevo, sustituir el pickle oficial, calibrar `cascade_reversal`, validar los
diamantes §3.3, y dejar todo ordenado en producción con metodología clean.

## Entregables (todos versionados en main)

### 1. Generador oficial en producción
- `backend/scripts/generators/generate_quants_obs.py` — builder v8 promovido
  (paths relativos, 4 compuertas automáticas, --dry-run, compuerta de deriva).
- `backend/scripts/generators/QUANTS_OBS_GENERATOR.md` — documentación de
  referencia completa (esquema 143 columnas, fórmulas, divergencias CAT-A/B/C,
  limitaciones, checklist de auditoría, historial de 15 fixes).
- `backend/tests/test_quants_obs_builder.py` — 7 tests de regresión que
  congelan los invariantes auditados.

### 2. Tabla oficial sustituida
- `data/research/pivots/quants_obs.pkl` — tabla auditada ×3 (hash 59fe36d0,
  1,590 pivotes × 143 columnas, 28/28 señales disparan).
- `data/research/pivots/quants_obs_pre_sustitucion_20260823.pkl` — one-off
  original del 17-Ago versionado como referencia de fidelidad.

### 3. Validaciones completas sobre la tabla oficial
- Tests de regresión: 7 passed.
- Suite backend completa: 25 passed.
- Evaluador ×2 tablas: 5 señales núcleo idénticas byte a byte.
- Validador OOS catálogo v7: núcleo intacto
  (pcr_put_panic +2.56% decay 0.63, credit_stress +1.43%, capitulacion +2.64%
  decay 0.77, vvix_entry +2.08%, bsi_washed_out +0.99% 5/6 folds).
- Calibración + walk-forward cascade_reversal: PROPOSED (edge +0.28% fijo /
  +0.44% rolling p15, p>0.05 → requiere más evidencia).
- Análisis individual diamantes §3.3: panico_total 11/11 en crisis ±3σ
  (p_raw=7/7 en zz25|ALZA, CI95 CP [0.59,1.0]); skew_paranoia_exit 8/10 en
  crisis.
- Determinismo del generador ×3: hash idéntico.

### 4. Documentación consolidada
- `docs/research/10_gate_oos_validation/` — 8 documentos de las 3 rondas de
  auditoría externa + autoauditorías + README índice con decisiones vigentes.
- `research/01_señales_entry_exit/GUIA_EMPLEO.md` §8 — actualización a tabla
  143 columnas.
- `research/10_gate_oos_validation/forensia/` — 4 scripts de calibración,
  walk-forward, diamantes y comparación.

### 5. Commits en main
- `363d92d` feat: generador oficial + tests + doc
- `6f4fcc8` data: pickle oficial sustituido + evidencias
- `0e0bedf` feat: etapa señales 22-23 Ago (arnés refactor, evaluador, OOS)
- `24b5f0d` docs+data: auditoría consolidada + evidencias restantes
- `fa8e462` data: validación OOS re-corrida sobre tabla oficial

## Decisiones de arquitectura vigentes
1. Propósito > réplica: la tabla debe ser correcta según producción; la
   fidelidad al one-off es detector de divergencias, no meta.
2. Divergencias CAT-A/B/C: 12 CAT-A (artefactos del one-off), 37 CAT-B
   (deriva de versión), 0 CAT-C (sin clasificar).
3. Protocolo diamante §3.3: N<21 = diamante; p_raw + CI95 Clopper-Pearson;
   nunca degradar por muestra baja.
4. cascade_reversal: PROPOSED, umbral −0.957 congelado, sin promoción todavía.
5. Degradadas: breadth_contraction_exit (break interno OOS), credit_ease_exit
   (reliquia pre-QE), bsi_recovery (post-QE).

## Limitaciones conocidas (documentadas, no son bugs)
- F4: 236 fechas de pivote duplicadas (deduplicar en groupby).
- BS3: denominador variable de d1_bear_5 (64% de pivotes con <5 estaciones).
- BS5: cobertura de datos (FG 64% ausente, Credit/PCR/VVIX ~42%).
- Look-ahead de fact stores (edges estáticos calibrados con datos posteriores).

## Pendientes para etapas futuras (no bloquean el cierre)
1. Promoción de cascade_reversal (requiere más evidencia, p>0.05).
2. Edges históricos para backtesting estricto (solo si se hace backtesting de
   ejecución, no medición post-mortem).
3. Reclasificación de skew con clasificador estable (opcional; si se
   identifica el clasificador original se podrían recuperar N históricas de
   panico_total/skew_paranoia_exit).

## Estado final
✅ Etapa culminada. Todo lo prometido en el rescate del hilo de Slack está
ejecutado, verificado y versionado en main. La próxima IA que toque la cadena
encuentra: generador, manual, tests, historial de 15 fixes y 3 auditorías —
sin necesidad de reconstruir nada.
