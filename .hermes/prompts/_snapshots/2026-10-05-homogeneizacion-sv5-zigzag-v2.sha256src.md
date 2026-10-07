# HOMOGENEIZACIÓN — SV5 `*_TW` + los dos zigzags · decisiones y alcance · 2026-10-05

Read-only hasta que cada acción tenga OK. Ningún query vale sin query+salida pegados.

---

## D1 · SV5 `*_TW` → **B (EMA5)**. Corrección de la recomendación anterior.

```
La config SIEMPRE dijo EMA5  (VOLUME_BREADTH_MA_CONFIG["tactical"]["fast_type"] = "ema")
El DEFAULT del calculador es SMA  (volume_breadth_calculator.calculate(..., fast_type: str = "sma"))
El backfill borrado (fast_backfill_sv5.py) usó el DEFAULT, no la config
⇒ A = cambiar la especificación para que coincida con un bug.   B = arreglar el bug.
```

**Tres pruebas independientes, todas a favor de EMA5:**

**① MATEMÁTICA — prueba de escalón (respuesta al impulso, un pico de 1 día):**
```
El día que el pico SALE de la ventana:
   día 15:  SMA(5) 100,0 (Δ −80,0)  ← discontinuidad de 80 puntos en un día
            EMA(5) 117,6 (Δ  −8,8)  ← decaimiento suave
⇒ El SMA(5) tiene un defecto ESTRUCTURAL: ventana de pesos uniformes + salto discreto.
⇒ Explica el Jul-13: RAW 1,2 % · SMA 19,9 % (16× de error, los días altos seguían en la ventana).
```

**② INDICADOR (ensayo 2026-07-15, hilo 747582b8, task-1611):**
```
                        Mean    Std   AvgΔ   MaxΔ   Saltos>10pp      r con RAW (lag0)
  RAW     40,0%  21,5%  15,0%  94,8%   234 (48%)         1,000
  SMA(5)  44,7%  22,8%   7,2%  54,7%   102 (21%)         0,533
  EMA(5)  44,0%  22,8%   8,2%  58,2%   132 (27%)         0,758
  ZLEMA(5)41,0%  22,6%  11,4%  91,3%   187 (38%)         0,863
Últimos 15 días: Jun-25 SPIKE RAW 73,5% · SMA5 9,3% · EMA5 22,0%   ← SMA lento
                 Jul-01       RAW 67,7% · SMA5 96,8% · EMA5 86,9%  ← SMA sobreestima
                 Jul-13 CRASH RAW  1,2% · SMA5 19,9% · EMA5  5,4%  ← SMA 16× arriba
                 Jul-14 BOUNCE RAW 35,4% · SMA5 14,1% · EMA5 11,5% ← EMA filtra
```

**③ AGUAS ABAJO — MISMOS umbrales sobre las dos series, SIN recalibrar. Benchmark: VIX ≥ 28.**
```
 Umbral              SMA5 (backup)                       EMA5 (vivo)
 SIGMET ≥ 10,0      19,2 % disparo · prec 12,8 % · recall 20,2 %
                    20,7 % disparo · prec 13,8 % · recall 26,2 %   → Δrecall +6,1 pts
 V41 HIGH > 8,90    24,4 % · prec 12,3 % · recall 24,8 %
                    27,6 % · prec 13,2 % · recall 33,4 %           → Δrecall +8,6 pts
 V41 EXTREME ≥ 12,8  9,8 % · prec 14,3 % · recall 11,5 %
                     9,9 % · prec 14,4 % · recall 13,1 %           → Δrecall +1,6 pts
⇒ EMA5 gana en precisión Y recall en las tres, con el mismo % de disparo.
```

**HOMOGENEIZAR — no duplicar.**
```
40 series SV5 = 36 sectoriales (12 sectores × TH/FI/TW) + 3 QQQ + 3 globales
Afectadas por el bug: ~14 series *_TW (global + 12 sectoriales + QQQ). Las TH/FI son SMA/SMA: no se tocan.
Verificado (jun-2021, backup→vivo):
   SV5TW    50,2→43,6 · 56,5→39,4      SV5_XLK_TW 33,0→29,5 · 45,5→31,8
   SV5_XLP_TW 68,6→57,1 · 71,4→51,4    SV5_XLU_TW 40,0→40,0 · 60,0→46,7
   SV5_QQQ_TW 85,4→30,1 · 85,4→17,2
⇒ Duplicar = 28 series. Prohibido: viola UNA FUENTE DE VERDAD POR INDICADOR.
⇒ La comparación SMA5-vs-EMA5 se hace UNA VEZ en script desechable (scratch/), sin escribir al Vault.
```

**Acciones**
```
D1-1. NO tocar la config: ya dice EMA5. El arreglo es que el pipeline la CUMPLA.
D1-2. Rebuild de las ~14 series *_TW (y con ellas SV5_TURBULENCE) honoring la config.
      Una serie por indicador. Homogéneo en TODA la historia (sin el híbrido SMA/EMA).
D1-3. Test de paridad OBLIGATORIO: daemon y backfill deben dar el MISMO valor en la misma fecha.
      Causa raíz del desastre: dos implementaciones de la misma fórmula, sin test.
D1-4. Re-derivar los percentiles sobre la serie nueva — es DETERMINISTA, no un re-ajuste:
      edges del fact store = cuantiles de la serie (backup: P25 4,24 · P50 5,98 · P75 8,81 · P90 12,75).
D1-5. Umbrales LITERALES a convertir en percentiles declarados con metadata (valor, percentil,
      ventana de calibración, % de disparo): `10.0` (3 sitios) · `8,90` · `12,80`.
      El gate los lee del fact store. Nunca literales en código.
D1-6. Monitor de deriva (PSI/KS) entre la ventana de calibración y la reciente → NOTAM
      "estación descalibrada" en vez de recalibrar en silencio.
```

**QQQ — revisión aparte (dos causas mezcladas):**
```
SV5_QQQ_TW cambió −68,2 pts (mucho más que el resto: −13 a −26).
Su serie se AÑADIÓ en fc1e7cc ("canonical QQQ history") ⇒ cambió también el UNIVERSO de constituyentes.
Acción: separar (a) SMA5→EMA5 de (b) cambio de universo, midiendo cada camino por separado.
        Si no convergen, ese es el hallazgo. Reconstruir DESPUÉS de separarlas.
```

---

## CENSO DE CONSUMIDORES — usar `graphify` (verificado: sirve)

```
graphify está en /root/.local/bin/graphify · grafo por defecto graphify-out/graph.json (23 MB, 04-oct 21:58)
Comandos:
   graphify explain "<nodo>"     → vecinos y direcciones del nodo
   graphify path "A" "B"         → camino más corto (añadir --undirected si no hay camino dirigido)
   graphify diagnose multigraph  → colisión de aristas
Node ids = ruta con "_" en vez de "/" y sin extensión.
```

**Censo ya verificado del SV5_TURBULENCE (grado 15, comunidad `convergence_compositor`):**
```
CONSUMIDORES (importan sv5_turbulence_metar_service):
   backend/modules/entry_decision/domain/services/convergence_compositor.py:L30   ← cascada / efecto dominó
   backend/modules/entry_decision/domain/services/market_sigmet_hazard_service.py:L29  ← EL SIGMET
   backend/api/routers/metar.py:L16
   backend/scripts/fetch_all_metar_reports.py:L19
   backend/scripts/forensics/forensic_march_27_vs_30_metar_audit.py:L16
   tests/test_sv5_turbulence_metar_service.py:L5
PRODUCTOR:   backend/daemons/vault_providers/sv5_turbulence_provider.py
LOOKUP:      backend/modules/entry_decision/domain/rules/sv5_turbulence_lookup.py
ESTACIÓN:    .agents/references/metar/stations/sv5_turbulence_personalidad.md
FACT STORES: sv5_turbulence_fact_store.json · sv5_turbulence_timing_fact_store.json
             metar_station_personalities.json
```

**Tarea del ejecutor:** extender este censo a TODAS las series afectadas — `SV5_{ETF}_TW` (12),
`SV5_QQQ_TW` y `SV5TW` — y a sus derivados (`SV5_TURBULENCE`, edges D1, pesos del compositor,
`SV5_EDGES["TW"]`, umbrales 60/40/50/−5 de rotación, `hybrid_scores`, `druckenmiller_causal_rules`,
`s5v_triad_table.json`). **Pegar la salida de graphify para cada uno.**

---

## RECALIBRACIÓN — alcance (todo lo que consume la serie afectada)

```
① Fact stores:        sv5_turbulence_fact_store.json · sv5_turbulence_timing_fact_store.json
                      edges D1 = cuantiles → re-derivar (determinista)
② Estación METAR:     sv5_turbulence_personalidad.md + metar_station_personalities.json
                      (revisar si la personalidad declarada cambia con la serie nueva)
③ SIGMET:             market_sigmet_hazard_service.py L298/L639 (umbral ≥ 10,0)
④ V40/V41:            quality_entry_gate.py L69 (10,0) · L72 (> 8,90) · L73 (≥ 12,80)
⑤ Rotación:           SV5_EDGES["TW"] · v_tw ≥ 60 · vol_div = v_tw − tw ≥ −5 · sec_v_tw ≥ 40/50 ·
                      hybrid_scores = (rs+1)·v_tw · druckenmiller_causal_rules (sv5_tw ≥ 60)
⑥ Compositor:         pesos (sv5_turbulence 0,72 · zz25 0,79 …) en cascade_calibration.json
⑦ Triad SV5:          s5v_triad_table.json (regenerar tras la serie nueva)
⑧ Benchmarks:         V39 / V40 / V41 — re-correr sobre la MISMA serie
```
**Pendiente de medición, aparte:** el SIGMET dispara 1 de cada 5 días con precisión 13,8 % sobre base 12,3 %
⇒ **no cumple la Regla 23** (riesgo extremo y RARO). Es un problema de PROPÓSITO, no de serie. Revalidarlo.

---

## D2 · Los dos zigzags → una máquina, dos parametrizaciones. NO se unifica la regla.

```
backfill_zigzag_points.py L48: "Uses High for peaks, Low for valleys, CLOSE for confirmation."  (L90: if close[i] <)
zigzag_legs_daemon.py L127/L158: confirma por LOW/HIGH (toque intrabarra)
⇒ misma máquina; difiere SÓLO el disparador de confirmación.
Emparejando la regla: SPY zz25 868 vs 868 (100 %) · AMD 5.162 vs 5.174 · KO 2.397 vs 2.397 (99,9 %).
Consumidores: zigzag_points (cierre) → triad, rc, tide, wave, sentinel (sólo entrenamiento)
              zigzag_legs  (toque)  → 11 fact stores METAR + cascade calibration + producción (compositor Canal 4)
```

**Contradicción documental RESUELTA — la intención era el TOQUE:**
```
zigzag_legs_audit_report.md L38 escribe P_close ≤ P_MAX×(1−D), pero su propio ejemplo la refuta:
  sello el 2021-09-20 · SPY 03-Sep-2021 high 422,93 → umbral −5 % = 401,78
  2021-09-20: LOW 401,11 ✓ cruza  ·  CLOSE 405,96 ✗ NO cruza
  Ratios: reporte 0,9473 · por LOW 0,9481 · por CLOSE 0,9599 ⇒ coincide con el LOW
⇒ El CÓDIGO está bien; la prosa del reporte estaba mal.
```

**Acciones**
```
D2-1. NO cambiar ninguna regla. Cero recalibración.
D2-2. UN kernel: `zigzag(high, low, close, pct, confirm_on="close"|"extreme")` + test de paridad
      contra AMBAS tablas. Patrón `calc_vwap_with_std`.
D2-3. Nombrar sin ambigüedad: `zz25 (cierre)` vs `zz25 (toque)` en AGENTS.md y en los `_documentation`
      de los fact stores. Declarar la regla intrabarra como DISEÑADA.
D2-4. `build_zigzag_benchmark.py`: quitar `L110 DELETE` sin `WHERE`; escribir en schema `benchmark.`
      (o eliminarlo migrando su validación). Riesgo inmediato.
D2-5. `engine.zigzag_points`: 3 escritores → 1. Columna aditiva `confirmed_at` (zigzag_legs ya la tiene).
D2-6. Marca aditiva `same_bar_pair`: 8,2 % en zigzag_points · 22,0 % en zigzag_legs zz25.
      NO tocar pivotes; que cada consumidor decida si filtra.
```

---

## D3 · Reconstruir `zigzag_legs` + `as_of_date` en L643 → SÍ, las dos, primero.

```
Producción lee SPY zz25 confirmado el 2026-07-31 (2 meses, barras pre-recarga).
   SPY zz25 último 07-29 (conf. 07-31) · zz50 06-26 (07-10) · zz75 03-30 (04-08)
   Tabla: 4.045.542 filas · 613 tickers · última confirmación 2026-08-03
Rebuild seguro: mismo algoritmo + barras de hoy → zz25 96,5 % · zz50 93,8 % · zz75 92,1 % idéntico.
Look-ahead: compute(as_of_date) llega a las 11 estaciones (L409 → _fetch_station L374-376)
   pero get_confirmed_legs L643 y L649 NO lo reciben.
   El repo SÍ lo soporta: zigzag_leg_repository.py:23-33 (`confirmed_at_timestamp <= as_of_date`)
   + idx_zigzag_legs_causal (ticker, scale, confirmed_at_timestamp).
   ⇒ en vivo inocuo; en replay/backtest toma el último tramo de TODA la tabla ⇒ LOOK-AHEAD.
   ⇒ el insumo central del efecto dominó ES legs25[-1].
Alcance: la antigüedad de zz75 es física (es la META de la cascada). La de zz25 es defecto (es INSUMO).
D3-1. Rebuild de market.zigzag_legs sobre las barras actuales, SIN cambiar el algoritmo.
D3-2. as_of_date en convergence_compositor L643 y L649.
D3-3. Test de regresión: en vivo no cambia; en replay SÍ (ese es el punto).
D3-4. zigzag_legs_daemon: enganche POST-ingesta de OHLCV (hoy es batch sin disparador).
```

---

## LO RETIRADO — NO HEREDAR
```
✗ "SV5 → A por paridad"                  RETIRADO. A legaliza el bug; el mérito (3 pruebas) dice EMA5.
✗ "serie aditiva SV5TW_EMA en paralelo"  RETIRADO. 14 series afectadas; duplicar viola una-fuente-de-verdad.
✗ "zigzag ×4,9 por high/low"             FALSO. Cobertura: tabla vieja = 5 años en 507/566 tickers.
                                         Densidad AMD 101,7/año → 110,9/año.
✗ "70-77 % de valores cambiados" (S5)    ENGAÑOSO. Conteo a 1e-9. MAGNITUD: MAD 0,24 · corr 1,000.
✗ "630 tickers"                          FALSO. 752 (520 STOCK · 180 INDICATOR · 47 ETF · 5 INDEX).
✗ "ningún daemon escribe channel_snapshots" FALSO. channel_snapshot_provider.py:36 + daemon:2221/2280.
✗ "normalizar zz25/50/75 por volatilidad" PROHIBIDO. Escalera de cascada (zz25→c50, zz50→c75, zz75 = meta).
```

## REGLAS
```
1. Dimensiones INVIOLABLES: sólo ESCALAS/edges. Nunca bins, etiquetas ni llave.
2. ADDITIVE-ONLY.  3. NO borrado total: conservar y migrar con evidencia escrita.
4. Todo umbral medido/derivado o DECLARADO como decisión.  5. Medir MAGNITUD, no conteo.
6. NO ANCLAR: dos caminos independientes deben CONVERGER; si no, ese es el hallazgo.
7. Regla 22: nada al Vault sin verificación. Snapshot de las 3 tablas antes de commitear.
8. Read-only hasta adjudicación.
```

## ESTADO
```
BLOQUEANTE OPERATIVO: el daemon `vault` NO está arriba (docker-compose `--loop 300` +
   `restart: unless-stopped`; `docker ps` sólo muestra redis + portainer; sin cron ni timer).
   ⇒ Sin él, D1 (paridad/homogeneidad) y D3 (frescura) se degradan solas.
PENDIENTE: estabilidad de la amplitud frente a N · el SIGMET (propósito) ·
   `SESSION_FINAL_ET=18:00` (¿Yahoo ya tiene el volumen consolidado?) · QQQ (separar causas).
BENCHMARKS: V39 (jul, serie híbrida) vs V40 (oct, post-rebuild) NO son comparables.
   Cerrar D1 y D3 → re-correr V39/V40/V41 sobre la MISMA serie → entonces comparar versiones.
```
