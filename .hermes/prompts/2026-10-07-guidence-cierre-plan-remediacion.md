# GUÍAS DE AUDITORÍA — CIERRE DEL PLAN DE REMEDIACIÓN (07-Oct-2026)

**Contexto:** el hilo reporta "~95 % completado" con los commits `5b50c6e` (12:31) y `ab837e1` (12:43).
La verificación independiente confirma la mayoría de las cifras, pero encuentra **anomalías no reportadas**
y **artefactos caducos que el hilo no lista**. Este guías cierra el plan con evidencia medida.

---

## 0. LO VERIFICADO — NO REHACER

| Punto | Evidencia medida | Veredicto |
|---|---|---|
| Legs de SPY purgadas | 1.584 (zz25) + 454 (zz50) + 184 (zz75) = **2.222** | ✅ Idéntico al recálculo canónico independiente |
| `confirmed_at` en `engine.zigzag_points` | **1.304 / 1.304** pivotes de SPY = 100 % | ✅ |
| `same_bar_pair` | **60** filas en `engine.zigzag_points` · **274** en `market.zigzag_legs` | ✅ Dos tablas distintas; ambas correctas |
| JSON de reglas (`rules/`) | **31/31 íntegros**: abren, llaves balanceadas, sin escritura parcial | ✅ |
| Esquemas vs git | **0 claves perdidas**, 0 cambios de esquema | ✅ ADDITIVE-ONLY respetado |
| Fact stores regenerados | 11 METAR (02:39–02:50) + `cascade_calibration` + `quants_obs.pkl` (1.584 × 165) | ✅ |
| F3.5 umbrales | `quality_entry_gate` lee los **tres** de `operational_thresholds` + `DECLARED_FALLBACK` | ✅ (era mi hallazgo previo: cerrado) |
| P9 | `forensic_v13` importa `calc_vwap_with_std` del kernel | ✅ |
| P10 | `signal_adapters` L1296 `Optional[bool]` + L1310 `is True` | ✅ |
| Higiene T2 | `scratch_*.py` movidos de `backend/scripts/` a `scratch/` | ✅ |
| F3.6/F3.7 (tríadas) | Re-entrenadas y **commiteadas** en `ab837e1` (12:43). Verificación independiente del claim "0 volteos de signo en celdas N≥30": comparando la versión actual vs `HEAD~1`, signo de (P_bot_5_0 − P_top_5_0) — **s5v: 400 celdas N≥30 → 0 volteos · s5: 292 → 0 volteos** | ✅ Claim cierto |

> **Nota de método (auditoría):** el campo `n` de las tríadas vive DENTRO de `cells[k]["global"]`, no
> al nivel de la celda. Un barrido al nivel equivocado devuelve "0 celdas con N≥30" — falso positivo
> silencioso. Verificar siempre la ruta del campo antes de concluir un conteo.

---

## 1. ANOMALÍAS CONFIRMADAS (no reportadas en el hilo)

### A1 — 11 `*_timing_fact_store.json` CADUCOS Y DESINCRONIZADOS  🔴
```
Evidencia 1: los 11 declaran "pivots_path": "data/research/pivots/quants_obs.pkl" y su mtime es 09-10
             (skew: 09-17) — 26 días anterior — mientras quants_obs.pkl se regeneró el 10-07 02:51 con
             1.584 pivotes ⇒ la fuente cambió y el consumidor NO.
Evidencia 2: poblaciones de estados distintas a sus fact stores:
             dxy 129 vs 112 (Δ−17) · skew 118 vs 105 (Δ−13) · sv5_turbulence 117 vs 110 (Δ−7) ·
             bsi 113 vs 112 (Δ−1) · pcr/rotation/vvix/yield_curve (Δ+1) · credit/fg/vix (=)
Evidencia 3: NINGÚN script de backend/ escribe "pivots_path" (grep vacío) ⇒ no existe productor
             que propague la fuente declarada ⇒ artefacto huérfano.
Impacto: el lector (timing_context.py L239-243 → Optional, spreads con .get()) es None-safe ⇒ NO
         crashea ⇒ DEGRADACIÓN SILENCIOSA: la señal temporal no aporta en los estados ausentes.
```

### A2 — `s5_s5v_stereotypes_results.json` CADUCO CON DEPENDENCIA REAL  🔴
```
mtime 09-04 04:32 (33 días) · 4,5 MB · su generador analyze_fusion_stereotypes.py contiene 19
referencias a datos que cambiaron (legs/points/quants/pivots/breadth) ⇒ debe regenerarse.
```

### A3 — Dos artefactos SIN GENERADOR EN EL REPO  🟠
```
· metar_station_personalities.json   (09-17, 19 días) — ningún script lo produce
· s5_sv5_quadrant_calibration.json   (08-15, 52 días) — ningún script lo produce
⇒ No se puede afirmar de qué dependen: PROCEDENCIA POR ESTABLECER (¿generador retirado? ¿script externo?).
  Si dependen de pivotes/amplitud ⇒ también caducos. Si no ⇒ declararlo como estático.
(decay_check_log.json es un log, no un artefacto de reglas: fuera del alcance.)
```

### A4 — Un test en ROJO (preexistente, no regresión)  🟠
```
Suite COMPLETA (tests/ + backend/tests/): 306 passed, 1 FAILED
   FAILED backend/tests/test_redis_cache.py::TestRedisCacheSingleton::test_returns_none_without_redis_url
       (espera None sin REDIS_URL; el código devuelve una instancia RedisCache)
Causa aislada: introduced por 2fbf7fc (10-06 15:45, endurecimiento de Redis), ANTERIOR a la remediación.
⇒ No es regresión de lo auditado, pero (a) contradice el "268/268", y (b) revela contrato roto
  test↔implementación: adjudicar si el test es obsoleto o el endurecimiento cambió el contrato.
```

### A5 — P11 INCOMPLETO  🟠
```
wipe_reload_cascade.py: 0 ocurrencias de "else 0.0" ⇒ corregido ✅
backfill_channel_snapshots_v2.py: 5 ocurrencias (L86 slope_pct · L163 change_pct · L172 vol_adj)
⇒ Son "no computable" por división por cero ⇒ por la regla 0.0 = neutro medido / NULL = no computable,
  deben ser None.
```

### A6 — P12 con una cifra desviada  🟠
```
Documenta "752 tickers"; la base tiene 753.  (Barras: el conteo real es 6.679.478 — cotejar la cifra escrita.)
```

---

## 2. PENDIENTES DEL PLAN (según el hilo)

```
· F3.8  PSI: últimas 60 sesiones vs base histórica; PSI > 0,25 → NOTAM_DISTRIBUTION_DRIFT
        (umbral correcto: 0,25 es el corte estándar de la industria; falta declararlo como decisión
         y fijar la ventana base)
· Batch 608 tickers secundarios (743.141 tramos de longitud cero) → offline, lotes de 20
· F5    Walk-forward/backtest sobre el vintage homogéneo V-C (ΔSharpe, asimetría, hit rate)
· Kernel: sigue en 1 de 3 consumidores de producción — train_s5_triad.py L240 y train_s5v_triad.py L73
        conservan su propio compute_zigzag
· Higiene de commits: 5b50c6e mezcla 30 .py + 29 .md + 17 .json + 1 .pkl en un solo commit
```

---

## 3. ORDEN DE EJECUCIÓN PROPUESTO

```
1. A1 — Resolver los 11 *_timing.  Antes de decidir, establecer QUIÉN los escribió (no hay productor
        en el repo).  Opciones a adjudicar:
          (a) crearlos desde quants_obs.pkl con un generador versionado y encadenado, o
          (b) retirar "pivots_path" y sacarlos de la cadena si su señal no se usa.
        Criterio: la opción que NO deje artefactos sin productor.
2. A3 — Establecer la procedencia de metar_station_personalities y s5_sv5_quadrant_calibration
        (¿generador retirado? ¿script externo?) y decidir su destino.
3. A2 — Regenerar s5_s5v_stereotypes_results.json con analyze_fusion_stereotypes.py.
4. A4 — Adjudicar el contrato de redis_cache (test vs implementación) y dejar la suite verde.
5. A5 — P11 en backfill_channel_snapshots_v2.py: los 5 "else 0.0" → None.
6. A6 — P12: corregir a 753 tickers y cotejar las barras (6.679.478).
7. F3.8 PSI · 8. Kernel en los 2 trainers · 9. F5 walk-forward · 10. Batch de 608 tickers.
11. Commit separado para código y para prompts (no volver a mezclar 30 .py con 29 .md).
```

---

## 4. DECISIONES A ADJUDICAR (no son opinión: son datos faltantes)

```
D-1  Los 11 *_timing: ¿regenerar desde quants_obs.pkl, o retirar la dependencia declarada?
D-2  metar_station_personalities + s5_sv5_quadrant_calibration: ¿son estáticos o caducos?
D-3  test_redis_cache: ¿se actualiza el test o se revierte el endurecimiento de Redis?
D-4  Kernel zigzag: ¿se extiende a train_s5_triad / train_s5v_triad (3.º y 4.º consumidor)?
D-5  ¿Se acepta el batch de 608 tickers como deuda declarada hasta su ejecución?
```

---

## 5. CRITERIOS DE ACEPTACIÓN DEL CIERRE

```
· 0 artefactos en rules/ con mtime anterior al rebuild (10-04) y fuente declarada caduca.
· 0 artefactos de reglas SIN productor identificado en el repo.
· Suite completa verde: tests/ + backend/tests/ (hoy 306 passed + 1 failed).
· 0 ocurrencias de "else 0.0" en los backfills de channel_snapshots.
· Documentación con los conteos medidos desde la base, no transcritos.
· Los 11 *_timing con población de estados == su fact store, o retirados con registro.
```
