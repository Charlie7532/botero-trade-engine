# AUDITORÍA EXTERNA — Validador OOS + Cadena de Medición Botero Trade

**Solicitante:** Juan Andrés (Arquitecto) vía Hermes (qwen/qwen3.8-max)
**Fecha:** 22-Ago-2026
**Ambiente:** `/root/botero-trade` · intérprete `backend/.venv/bin/python` · `PYTHONPATH=/root/botero-trade`

---

## 0. CONTEXTO

Se acaba de construir un **validador OOS** (walk-forward anclado) para el catálogo v7
de señales de trading. El validador reportó que las señales conservan edge positivo
out-of-sample. Pero antes de confiar, una autoauditoría honesta (incluida abajo)
encontró un **look-ahead crítico en el binneo de D2/D3** que contamina el input.

**Tu tarea:** auditar INDEPENDIENTEMENTE tanto el validador como la cadena completa
de medición. No confíes en nuestra autoauditoría — verifícala. Puede que hayamos
sobreestimado o subestimado el problema.

## 1. ARCHIVOS CLAVE

| Archivo | Qué es |
|---------|--------|
| `research/10_gate_oos_validation/validador_oos.py` | Validador OOS walk-forward |
| `research/10_gate_oos_validation/AUTOAUDITORIA_OOS_22AGO.md` | Nuestra autoauditoría |
| `research/01_señales_entry_exit/evaluador_vela_a_vela.py` | Calificador post-mortem (first-passage) |
| `research/01_señales_entry_exit/arnes/señales.py` | Definiciones de las 28 señales |
| `research/01_señales_entry_exit/arnes/medicion.py` | Motor `medir()` |
| `backend/scripts/_lib/v3_fact_table_engine.py` | Motor que genera los state_keys (D1__D2__D3) |
| `data/research/pivots/quants_obs.pkl` | 1,590 pivotes con state_keys |
| `data/research/signals/validacion_oos_catalogo_v7.json` | Resultados OOS |
| `research/01_señales_entry_exit/_deprecated/medir_senal_godfile_1497L_backup.py` | God file original (referencia) |

## 2. REGLAS DE LA CASA

1. **Dato mata relato.** Verifica cada afirmación corriendo el código. No aceptes fe.
2. **Lenguaje probabilístico.** N + CI95 + p-value en todo. Sin absolutos.
3. **Protocolo Diamante:** N<21 = diamante (tasa cruda + tier §3.3), nunca descartar.
4. **Taxonomía de sesgos a aplicar:** posición, estructura de escala, contaminación de
   baseline, look-ahead, multiplicidad, filtro pivot_type embebido.

## 3. AUTOAUDITORÍA HONESTA (verificar, no asumir)

Encontramos estos hallazgos. **Verifícalos con código, y busca lo que no vimos:**

### H1 — Look-ahead en binneo D2/D3 (CRÍTICO)
En `v3_fact_table_engine.py:469-483`: D1 usa `expanding().rank()` (limpio), pero
D2/D3 usan `calib_df.quantile()` sobre toda la historia y clasifican cada barra
histórica contra esos bordes. ¿Confirmas que esto es look-ahead? ¿Qué señales del
catálogo v7 están afectadas vs. limpias? ¿Cambia el resultado OOS si se excluyen
las señales contaminadas?

### H2 — Sign-test sin potencia
Con 2-4 folds el mínimo p posible es 0.0625-0.25. ¿Confirmas que ninguna señal
alcanza significancia OOS real? ¿Qué N de folds se necesitaría para potencia 0.8?

### H3 — Decay asimétrico
El decay compara IS (mejor celda sobre toda la historia) vs OOS (celda honesta).
¿Es un ratio válido de degradación o está inflado por selección optimista del IS?

## 4. PREGUNTAS NUEVAS (lo que NO verificamos)

1. **quants_obs.pkl mismo:** ¿fue generado con el motor actual o con una versión
   anterior? ¿Los state_keys del pickle coinciden con una regeneración? (El pickle
   puede ser más viejo que el código.)
2. **El validador usa `SEÑALES[s](df)` sobre el df completo** para la máscara — la
   señal se computa con toda la historia antes de cortar por folds. Para señales
   basadas solo en state_keys es inocuo, pero ¿hay alguna señal que use cuantiles
   o estadísticos del df completo dentro de su definición?
3. **Baseline del fold de test:** se excluyen las fechas de disparo de la señal —
   ¿pero la máscara de exclusión usa disparos de TODA la historia o solo del período?
   Verificar `fichas_baseline()` línea por línea.
4. **Régimen observable en folds tempranos:** con train de 5 años, ¿hay folds donde
   el régimen casi siempre es el mismo (pocos pivotes confirmados)? Eso degradaría
   la selección de celda.
5. **First-passage y datos intradía:** el first-passage usa solo closes. ¿Subestima
   el MAE (dolor) al ignorar excursiones adversas intradía?
6. **Independencia de folds:** folds consecutivos comparten el mismo train anclado
   creciente — los resultados OOS entre folds NO son independientes. ¿El sign-test
   asume independencia? ¿Cómo corregirlo?

## 5. SALIDA ESPERADA

```markdown
# AUDITORÍA EXTERNA — Validador OOS
## 1. Verificación de la autoauditoría (H1/H2/H3 confirmados o refutados con código)
## 2. Hallazgos nuevos (lo que no vimos)
## 3. Señales limpias vs contaminadas por look-ahead D2/D3
## 4. ¿El resultado OOS es confiable? (veredicto con evidencia)
## 5. Recomendaciones priorizadas (P0 bloqueantes / P1 importantes / P2 mejoras)
```

**Firma del solicitante:** qwen/qwen3.8-max (Hermes) · 22-Ago-2026
