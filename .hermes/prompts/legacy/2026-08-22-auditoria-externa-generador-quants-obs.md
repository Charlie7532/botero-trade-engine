# AUDITORÍA EXTERNA — Generador `quants_obs` (validar que el NUEVO generador es correcto)

**Solicitante:** Juan Andrés (Arquitecto) vía Hermes (qwen/qwen3.8-max)
**Fecha:** 22-Ago-2026
**Ambiente:** `/root/botero-trade` — ejecutar con `cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python <script>`

---

## 1. OBJETIVO

**Validar que el nuevo generador es correcto en sí mismo** (según la lógica de producción),
NO que replique byte-a-byte un artefacto one-off del 17-Ago que contiene bugs conocidos.
La fidelidad al original es un *detector de divergencias*, no la meta de aceptación.

El propósito del artefacto que genera: `quants_obs` es la **tabla de observación canónica**
del sistema de señales — para cada pivote confirmado del zigzag SPY captura el estado
dimensional instantáneo de las 11 estaciones + la convicción del cascade. Es la matriz de
features sobre la que se mide el edge de cada señal de entry/exit. **Si los pivotes o las
fórmulas están mal, todo el sistema de señales mide mal.**

## 2. ARTEFACTOS A AUDITAR

1. **Generador:** `research/10_gate_oos_validation/builder_quants_obs.py` (v5)
2. **Salida:** `data/research/signals/../pivots/quants_obs_new.pkl` (1,590 × 142 columnas)
3. **Manifiesto de divergencias:** `data/research/signals/manifiesto_divergencias_quants_obs.json`
4. **Autoauditoría previa:** `research/10_gate_oos_validation/AUTOAUDITORIA_GENERADOR_v5_22AGO.md`
5. **Original (referencia, NO meta):** `data/research/pivots/quants_obs.pkl` (backup en `.bak`)

## 3. LO YA VERIFICADO (autoauditoría interna — revisar pero no repetir a ciegas)

El generador fue autoauditado y estos resultados están documentados con evidencia:
- **101/141 columnas** matchean ≥99.9% con el original.
- **12 columnas CAT-A** (artefactos del one-off; el builder usa la lógica de producción correcta).
- **37 columnas CAT-B** (deriva de versión de fact stores; documentada).
- **0 columnas CAT-C** (sin clasificar).
- **28/28 señales disparan** en la tabla nueva (cero inertes).
- **`cascade_reversal`** pasó de inerte-en-silencio a 1,075 disparos (bug de columna faltante corregido).
- Fórmulas clave verificadas al 100%: pivotes, `duration_bars`, `daily_return_pct`,
  `cascade_50/75`, `z_dom`, `d1_bear_5` (presión bearish), `cascade_conviction`.

## 4. PREGUNTAS CLAVE PARA EL AUDITOR (ordenadas por criticidad)

### P1 — Columna vertebral: los pivotes (CRÍTICO)
Verificar de forma independiente que los 1,590 pivotes de `quants_obs_new.pkl` son
EXACTAMENTE los del zigzag oficial de producción:
- `ZigzagLegRepository.get_confirmed_legs("SPY","zz25")` → pares (fecha,tipo) idénticos.
- Consistencia del zigzag en las tres escalas (zz25/zz50/zz75): alternancia, continuidad,
  umbral de movimiento mínimo.
- **Cualquier desalineación aquí hace fallar todo el sistema — es la prioridad máxima.**

### P2 — Fórmulas del estado dimensional
Para cada una de las 11 estaciones, verificar que `_val/_vel/_vol/_sk` se generan según la
lógica de producción:
- `_val`: serie del Vault alineada por fecha exacta.
- `_vel`: `diff(3)`; `_vol`: `std(2)/std(10)`; defaults fuera de rango vel=0, vol=1.
- `_sk`: LookupAdapter de producción con edges estáticos del fact store.
- Confirmar que los state_keys son 100% consistentes con los fact stores de producción
  (cero huérfanos).

### P3 — Fórmulas del cascade y derivados
- `d1_bear_5` = presión bearish Σ(max(0,−voto))/n (verificar contra
  `convergence_compositor.py:439,484` que usa fracción bearish).
- `z_bear` = (d1_bear_5 − 0.3299)/0.2856 (defaults del compositor, L488-489).
- `z_dom` = (abs_prev_leg_return − 0.0532)/0.035 (calibration file).
- `cascade_conviction` y `cascade_conviction_50` = 0.66·z_bear + 0.34·z_dom
  (verificar contra compositor L503).

### P4 — Idoneidad de las decisiones CAT-A
Dictaminar si las dos decisiones CAT-A son correctas o si se debe hacer otra cosa:
1. **Skew D1 solapado:** el builder usa edges estáticos de producción y documenta la
   divergencia (no clona el clasificador irreproducible del one-off). ¿Correcto?
2. **Escala de votos −0.5 de OVERSOLD_BREADTH:** el builder usa la escala de producción
   {−1,0,+1}. Esto explica exactamente las 428 filas divergentes de d1_bear_5/z_bear/
   cascade_conviction. ¿Correcto, o debería preservarse la escala −0.5?

### P5 — Impacto aguas abajo
- Re-correr el evaluador (`evaluador_vela_a_vela.py`) sobre `quants_obs_new.pkl` y
  comparar el catálogo v7 de señales contra las mediciones sobre el original. ¿Cambian
  los edges de las 8 señales robustas?
- Verificar que ninguna señal del catálogo depende de columnas CAT-A/B de forma material.
- Verificar compatibilidad del esquema de 142 columnas con todos los consumidores
  (`evaluador_vela_a_vela.py`, `arnes/`, `audit_regimes.py`, scripts de forensia).

### P6 — Reproductibilidad
- Ejecutar el builder dos veces y verificar que produce la misma tabla (determinismo).
- Verificar que al crecer el zigzag (pivote nuevo de 2026-07-29) el builder lo incorpora
  correctamente sin romper las filas existentes.

## 5. LÍMITES DEL SCOPE

- ✅ **Preservar** `quants_obs.pkl` intacto (no sustituir); el builder escribe en `_new.pkl`.
- ✅ **Respetar** los edges estáticos de los LookupAdapters de producción como clasificación
  correcta por defecto.
- ✅ **Mantener** el universo de 1,590 pivotes SPY zz25 para la comparación.
- ✅ **Aislar** cualquier script de forensia en `scratch/`.
- ✅ **Conservar** la comparabilidad con los consumidores actuales; documentar todo cambio.

## 6. FORMATO DE ENTREGA ESPERADO

1. Veredicto por pregunta (P1-P6): APROBADO / RECHAZADO / OBSERVACIÓN, con evidencia reproducible.
2. Lista de hallazgos críticos (si los hay) con severidad y propuesta de corrección.
3. Confirmación o refutación de las decisiones CAT-A (P4).
4. Comparación del catálogo v7 sobre tabla nueva vs original (P5).
5. Firma del modelo auditor y fecha.
