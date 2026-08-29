# AUDITORÍA EXTERNA — Cadena completa `quants_obs` (auditoría profunda + calibración)

**Solicitante:** Juan Andrés (Arquitecto) vía Hermes (qwen/qwen3.8-max)
**Fecha:** 23-Ago-2026
**Ambiente:** `/root/botero-trade` — ejecutar con `cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python <script>`

---

## 1. CONTEXTO: QUÉ SE AUDITA

La **cadena completa de observación canónica** del sistema de señales de Botero Trade.
Esta auditoría es la culminación de un proceso de reconstrucción del generador
`quants_obs.pkl` (un one-off del 17-Ago que nunca fue versionado) y la calibración de
una señal resucitada (`cascade_reversal`).

**El propósito que guía todo:** una tabla de observación **correcta según la lógica de
producción y reproducible**, sobre la que se mide el edge real de cada señal de entry/exit.
La fidelidad al one-off original es un *detector de divergencias*, no la meta.

## 2. ARTEFACTOS A AUDITAR

1. `research/10_gate_oos_validation/builder_quants_obs.py` (v7 — con fix F5)
2. `data/research/pivots/quants_obs_new.pkl` (1,590 × 142 columnas)
3. `research/01_señales_entry_exit/arnes/señales.py` (`cascade_reversal` calibrada)
4. `data/research/signals/manifiesto_divergencias_quants_obs.json`
5. `data/research/signals/calibracion_cascade_reversal.json`
6. `data/research/signals/evaluacion_TABLA_NUEVA.json` y `evaluacion_TABLA_ORIGINAL.json`

**Documentación previa (leer primero):**
- `INFORME_AUDITORIA_PROFUNDA_CALIBRACION_23AGO.md` ← el informe principal de esta sesión
- `RESPUESTA_AUDITORIA_OPUS_GENERADOR_23AGO.md` ← respuesta a la auditoría Opus anterior
- `AUTOAUDITORIA_GENERADOR_v5_22AGO.md` y `AUTOAUDITORIA_PROPOSITO_QUANTS_OBS.md`

## 3. LO YA VERIFICADO (no repetir a ciegas, pero auditar el razonamiento)

### Auditoría Opus previa (23-Ago temprano) — 4 hallazgos confirmados y aplicados:
- **F1 (P0):** z_bear usaba μ/σ hardcoded → ahora dinámicos del cal-file. **Resuelto: 0% inversiones de signo** (antes 17.9%).
- **F2 (P1):** panico_total 34→11, skew_paranoia_exit 26→10 por reclasificación SKEW CAT-A.
- **F3 (P1):** fórmula d1_bear_5 frágil → cambiada al conteo de producción.
- **F4 (P2):** 236 fechas duplicadas → documentadas con warning activo.

### Auditoría profunda de esta sesión:
- **F5:** pesos cascade_conviction hardcoded → ahora dinámicos del type_mask. Resuelto.
- **Comparación completa** tabla nueva vs original: las 5 señales núcleo del catálogo v7
  son **idénticas byte a byte** (pcr_put_panic, credit_stress, capitulacion, vvix_entry,
  bsi_washed_out).
- **24 consumidores** de quants_obs mapeados; ninguna columna referida está ausente.
- Todos los D1 referidos por las señales existen en la tabla nueva.

### Calibración de cascade_reversal:
- Umbral original 0.30 → fire rate 75.8% (background puro) con normalización de producción.
- Barrido: tercil_bajo y cero también background; **elegido p15 (−0.957)**, fire rate 15%.
- Resultado honesto: edge +0.28% pero **p=0.25 — NO significativo**.
- Estado: PROPOSED, requiere OOS/walk-forward antes de promoción.

## 4. PREGUNTAS PARA EL AUDITOR (ordenadas por criticidad)

### P1 — Columna vertebral: pivotes (CRÍTICO)
Verificar independientemente que los 1,590 pivotes de `quants_obs_new.pkl` son exactamente
los de `ZigzagLegRepository.get_confirmed_legs("SPY","zz25")`. Confirmar consistencia del
zigzag en las tres escalas.

### P2 — Las 236 fechas de pivote duplicadas
¿Es correcto tratarlas como "limitación conocida" (el zigzag almacena una pierna forward y
una backward con el mismo start_timestamp), o debería el zigzag de producción resolverlas?
Evaluar el impacto real en cada uno de los 24 consumidores (¿alguno hace groupby(pivot_date)?).

### P3 — Consistencia de la reclasificación CAT-A de SKEW
El CAT-A de skew cambió el N de panico_total (34→11) y skew_paranoia_exit (26→10).
Verificar que ninguna OTRA señal depende del estado D1 de skew de forma material
(más allá de las dos ya cuantificadas). Confirmar que la divergencia queda acotada.

### P4 — `cascade_reversal` sin significancia (DECISIÓN REQUERIDA)
La señal calibrada dispara 240 veces con edge +0.28% pero p=0.25. Dictaminar:
- (a) ¿Promover como diamante anecdótico (N bajo, rareza valiosa) a pesar de p=0.25?
- (b) ¿Mantener en PROPOSED hasta validación OOS/walk-forward?
- (c) ¿El gradiente direccional real (edge negativo en BAJA −1.2% a −2.4%) justifica
      recalibrar con un enfoque diferente (p.ej. condicionar por régimen)?
Argumentar con el protocolo de diamantes del sistema (N<21 = diamante, no degradar por
muestra baja) y el estándar de walk-forward.

### P5 — Trade-off fidelidad vs consistencia con producción
El builder usa μ/σ del cal-file actual (producción), por lo que z_bear/cascade matchean
~0% contra el one-off original. ¿Es este el trade-off correcto? ¿Hay algún consumidor que
dependa de los valores históricos del one-off y se rompa?

### P6 — Reproductibilidad
Confirmar con un run independiente que el builder produce la misma tabla bit-a-bit.
Verificar que el umbral congelado de cascade_reversal (−0.957) no introduce look-ahead.

### P7 — Completitud de los fixes
La tabla del informe lista 11 fixes acumulados. Verificar que no quede ningún ajuste
pendiente, y buscar activamente (adversarialmente) si hay algún otro hardcoded, columna
faltante, o inconsistencia que se haya pasado en las auditorías previas.

## 5. LÍMITES DEL SCOPE

- ✅ **Preservar** `quants_obs.pkl` intacto (backup en `.bak`); el builder escribe en `_new.pkl`.
- ✅ **Respetar** los edges estáticos de los LookupAdapters como clasificación correcta.
- ✅ **Aislar** cualquier script de forensia en `scratch/`.
- ✅ **Conservar** la comparabilidad con los 24 consumidores; documentar todo cambio.
- ✅ **Usar lenguaje probabilístico** en el veredicto (P(x)=X%, no absolutos).

## 6. FORMATO DE ENTREGA ESPERADO

1. Veredicto por pregunta (P1-P7): APROBADO / RECHAZADO / OBSERVACIÓN, con evidencia reproducible.
2. Hallazgos nuevos (si los hay) con severidad y propuesta de corrección.
3. Dictamen sobre `cascade_reversal` (P4) con recomendación concreta.
4. Confirmación o refutación de los 11 fixes acumulados.
5. Firma del modelo auditor y fecha.
