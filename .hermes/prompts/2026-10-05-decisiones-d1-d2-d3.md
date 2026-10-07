# DECISIONES — 3 preguntas cerradas · Botero Trade · 2026-10-05

Ámbito: `market.ohlcv_bars` · `engine.zigzag_points` · `market.zigzag_legs` · `SV5_*` · `entry_decision`.
Modo: read-only hasta que cada acción tenga OK. Ningún query vale sin query+salida pegados.

---

## D1 · SV5 `*_TW`: ¿A (SMA5) o B (EMA5)?

**RESPUESTA: A ahora. EMA5 en paralelo, adopción por mérito.**

**Motivo — el EMA5 NO es arbitrario: hay ensayo medido y aprobado (2026-07-15, hilo 747582b8, task-1611).**
```
FAST MA COMPARISON (vs SMA(20))          Mean    Std   AvgΔ   MaxΔ   Saltos>10pp
  RAW     40.0%  21.5%  15.0%  94.8%   234 (48%)
  SMA(5)  44.7%  22.8%   7.2%  54.7%   102 (21%)
  EMA(5)  44.0%  22.8%   8.2%  58.2%   132 (27%)
  ZLEMA(5)41.0%  22.6%  11.4%  91.3%   187 (38%)

Responsiveness (r con RAW, lag0):  SMA(5) 0,533  ·  EMA(5) 0,758  ·  ZLEMA(5) 0,863
Últimos 15 días:
  Jun-25 SPIKE  RAW 73,5% · SMA5  9,3% · EMA5 22,0%   ← SMA demasiado lento
  Jul-01        RAW 67,7% · SMA5 96,8% · EMA5 86,9%   ← SMA sobreestima
  Jul-13 CRASH  RAW  1,2% · SMA5 19,9% · EMA5  5,4%   ← SMA 16× arriba en estrés extremo
  Jul-14 BOUNCE RAW 35,4% · SMA5 14,1% · EMA5 11,5%   ← EMA filtra el rebote
Conclusión del ensayo: "EMA(5) es el sweet spot". Fórmula propuesta y aprobada: EMA(5,vol) > SMA(20,vol).
```

**Conflicto real (declararlo, no esconderlo):**
```
DISEÑADO Y PROBADO:  EMA(5)  · r 0,758 · aprobado 15-jul
ENTREGADO Y VALIDADO: SMA(5) · r 0,533 · entrenó triad, fact stores, edges D1
Causa del desvío: `volume_breadth_calculator.calculate(..., fast_type="sma")` como DEFAULT;
  la config lo sobrescribe a "ema" sólo en tactical; `fast_backfill_sv5.py` (borrado) implementó
  la fórmula por su cuenta y tomó el DEFAULT. El daemon sí leía la config.
```

**Evidencia de mérito predictivo (para no sobrevender ninguna):**
```
Ventana 1999-01-19→2026-04-30, n=6.863, días VIX≥28 = 12,3 %
                       SMA5     EMA5
  AUC VIX≥28 mismo día 0,505    0,521     ← ambas = azar
  AUC VIX≥28 a 10 d    0,489    0,505
  Precisión quintil sup 12,9%   15,4%
  ⇒ Δ = +0,016 AUC. No decide por mérito.
```

**Evidencia de que A no rompe el diseño anidado:**
```
Correlación inter-capa (hasta 2026-04-30):
  BACKUP (SMA5): TW·FI 0,035 · TW·TH −0,074 · FI·TH 0,071  → media 0,010
  VIVO  (EMA5):  TW·FI 0,033 · TW·TH −0,078 · FI·TH 0,078  → media 0,011
  ⇒ la decorrelación (~0,04 declarada) la producen los PARES DE LONGITUD (5/20 · 20/50 · 50/200),
    no el tipo de media. El EMA no era portante.
```

**Acciones exactas**
```
A1. `VOLUME_BREADTH_MA_CONFIG["tactical"]["fast_type"] = "sma"`  (constants/sectors.py L184)
A2. Ejecutar `rebuild_breadth_history.py` → recalcula 13 series `*_TW` + SV5_TURBULENCE
    (lee la config; no se toca su código; el daemon pasa a SMA5 solo)
A3. Actualizar docstrings y AGENTS.md: "TW = SMA5v > 20v" (hoy dice EMA5v>20v)
A4. Test de paridad OBLIGATORIO: daemon y backfill deben dar el MISMO valor en la misma fecha.
    Causa raíz de todo esto: dos implementaciones de la misma fórmula sin test.
A5. EMA5 como serie ADITIVA en paralelo (`SV5TW_EMA`), sin tocar la base ni los fact stores.
    Se adopta sólo si mejora de forma material en los gates reales (SIGMET · V40/V41 · rotación).
    Si se adopta: recalibrar UNA vez, declarado, con monitor de deriva (PSI/KS) — nunca en silencio.
A6. Umbrales: NO dejar literales (`10.0` en 3 sitios · `8,90/12,80` en otro).
    Percentil derivado de una ventana de calibración declarada, guardado con metadata
    (valor, percentil, ventana, % de disparo) en el fact store. El gate lo lee de ahí.
```

**Secuela a probar (no incluida en A):** el SMA(5) marcaba 19,9 % cuando el RAW era 1,2 %.
Si el SMA sobreestima en crashes, la turbulencia derivada hereda el sesgo — posible causa de que
el SIGMET dispare 19–25 % de los días sin discriminar VIX≥28.

---

## D2 · Los dos zigzags: ¿cuál es el canónico para zz25/50/75?

**RESPUESTA: ninguno "gana". Una máquina de estados, dos parametrizaciones. No se unifica la regla.**

**Verificado en código (no en documentos):**
```
backfill_zigzag_points.py L48: "Uses High for peaks, Low for valleys, CLOSE for confirmation."
   L90: if close[i] < cand_high_val*(1-min_pct)          → `engine.zigzag_points`: CIERRE
zigzag_legs_daemon.py L127: if c_low  <= extreme*(1-thres)  → `market.zigzag_legs`: TOQUE intrabarra
                      L158: if c_high >= extreme*(1+thres)
⇒ misma máquina; difiere SÓLO el disparador de confirmación.
```

**Prueba de equivalencia emparejando la regla:** SPY zz25 868 vs 868 (100 %) · zz50/zz75 100 %/100 % ·
AMD zz25 5.162 vs 5.174 (~100 %) · KO zz25 2.397 vs 2.397 (99,9 %).

**Contradicción documental RESUELTA — la intención era el TOQUE:**
```
zigzag_legs_audit_report.md L38 (spec de agosto) escribe: P_close ≤ P_MAX × (1 − D)
Pero su propio ejemplo la refuta: el sello se firma el 2021-09-20.
  SPY 03-Sep-2021 high 422,93 → umbral −5 % = 401,78
  2021-09-20:  LOW 401,11 ✓ cruza   ·   CLOSE 405,96 ✗ NO cruza
  ⇒ con regla de cierre el sello NO podría ser el 20-Sep.
Ratios (factor de precio se cancela): reporte 164,50/173,64 = 0,9473 · por LOW 0,9481 · por CLOSE 0,9599
  ⇒ coincide con el LOW.
⇒ El CÓDIGO está bien; la PROSA del reporte estaba mal. NO hay bug tipo SV5 en zigzag_legs.
```

**Consumidores (no intercambiables — cada familia se calibró con su regla):**
```
`engine.zigzag_points` (cierre) → SÓLO entrenamiento: triad, rc, tide, wave, sentinel
`market.zigzag_legs`   (toque)  → entrenamiento: 11 fact stores METAR + cascade calibration
                                  producción: `convergence_compositor` Canal 4 (leído sin as_of_date)
```

**Acciones exactas**
```
D2-1. NO cambiar ninguna regla. No se recalibra nada.
D2-2. UN kernel parametrizado: `zigzag(high, low, close, pct, confirm_on="close"|"extreme")`
      + test de paridad contra AMBAS tablas. Una máquina, dos parámetros — patrón `calc_vwap_with_std`.
D2-3. Nombrar sin ambigüedad en AGENTS.md y en los `_documentation` de los fact stores:
      `zz25 (cierre)` vs `zz25 (toque)`. Declarar la regla intrabarra como DISEÑADA, no como accidente.
D2-4. `build_zigzag_benchmark.py`: quitar `L110 DELETE` sin `WHERE`; mover su escritura a schema
      `benchmark.` (o eliminarlo migrando su validación). Riesgo inmediato hoy.
D2-5. `engine.zigzag_points`: 3 escritores → 1. Añadir columna aditiva `confirmed_at`
      (zigzag_legs ya la tiene; zigzag_points no — sin ella no se audita causalidad).
D2-6. Marca aditiva `same_bar_pair` (orden intrabarra ambiguo): 8,2 % en zigzag_points,
      22,0 % en zigzag_legs zz25. NO tocar pivotes; que cada consumidor decida si filtra.
```

---

## D3 · ¿Reconstruir `zigzag_legs` + `as_of_date` en L643?

**RESPUESTA: SÍ a las dos. Es lo más urgente de las tres.**

**Evidencia**
```
Producción lee SPY zz25 confirmado el 2026-07-31 → 2 meses de antigüedad, sobre barras PRE-recarga.
SPY hoy: zz25 último 2026-07-29 (conf. 07-31) · zz50 06-26 (07-10) · zz75 03-30 (04-08)
Tabla completa: 4.045.542 filas · 613 tickers · última confirmación 2026-08-03

Seguridad del rebuild (mismo algoritmo, barras de hoy vs lo guardado):
  zz25 96,5 % coincidencia (faltan 2 tramos, posteriores al 07-31) · zz50 93,8 % · zz75 92,1 %
  ⇒ 96,5 % idéntico = NO mueve las estadísticas de entrenamiento ⇒ seguro.

Look-ahead (verificado):
  `compute(as_of_date)` SÍ propaga a las 11 estaciones (L409 → _fetch_station L374-376)
  `get_confirmed_legs("SPY","zz25")` L643 y `("SPY","zz50")` L649 → SIN as_of_date
  El repo SÍ lo soporta: `zigzag_leg_repository.py:23-33` aplica `confirmed_at_timestamp <= as_of_date`
  y existe `idx_zigzag_legs_causal (ticker, scale, confirmed_at_timestamp)`.
  ⇒ En vivo es inocuo. En replay/backtest toma el último tramo de TODA la tabla ⇒ LOOK-AHEAD.
  ⇒ El insumo central del "efecto dominó" ES `legs25[-1]`: sin filtro, entra un tramo FUTURO.
```

**Corrección de alcance:** la antigüedad de `zz75` (abril) es física del mercado — es la META de la cascada,
no un insumo. La de `zz25` (julio) es defecto: es INSUMO del compositor.

**Acciones exactas**
```
D3-1. Rebuild de `market.zigzag_legs` sobre las barras actuales — SIN cambiar el algoritmo.
D3-2. `as_of_date` en `convergence_compositor` L643 y L649 (un argumento, dos sitios).
D3-3. Test de regresión: el resultado en vivo no debe cambiar; en replay debe cambiar (ese es el punto).
D3-4. `zigzag_legs_daemon`: enganche diario (hoy es batch sin disparador).
      El disparador correcto es POST-ingesta de OHLCV, no un calendario.
```

---

## LO RETIRADO — NO HEREDAR

```
✗ "zigzag ×4,9 por usar high/low"        FALSO. La tabla vieja cubría 5 años en 507/566 tickers.
                                         Densidad: AMD 101,7/año (viejo) → 110,9/año (nuevo). Prueba: pivotes/AÑO.
✗ "70-77 % de valores cambiados" (S5)    ENGAÑOSO. Conteo de cualquier diferencia a 1e-9.
                                         MAGNITUD real: MAD 0,24 pts · corr 1,000. Sólo SV5TW cambió (MAD 4,91).
✗ "630 tickers"                          FALSO. 752 (520 STOCK · 180 INDICATOR · 47 ETF · 5 INDEX).
✗ "ningún daemon escribe channel_snapshots" FALSO. Existe `channel_snapshot_provider.py:36`
                                         (`vault_channel_snapshots`), registrado en data_vault_daemon.py:2221/2280.
✗ "el filtro update_source reduce el universo"  NULO. Los 506 ya lo tienen.
✗ "normalizar zz25/50/75 por volatilidad" PROHIBIDO. Son la escalera de un anidamiento de cascada
                                         (zz25→c50, zz50→c75, zz75 = meta). Normalizar mata la comparación.
```

## REGLAS

```
1. Dimensiones INVOLABLES: sólo cambian ESCALAS/edges. Nunca bins, etiquetas ni llave.
2. ADDITIVE-ONLY en esquemas.
3. NO borrado total: conservar y migrar lo útil, con evidencia escrita.
4. Todo umbral: medido/derivado del dato o DECLARADO como decisión. Nada heredado sin medición.
5. Medir MAGNITUD, no conteo. Declarar AMBAS poblaciones antes de comparar.
6. NO ANCLAR: dos caminos independientes deben CONVERGER; si no, ese es el hallazgo.
7. Regla 22: nada escrito en el Vault sin verificación. Snapshot de las 3 tablas antes de commitear.
8. Auditoría read-only hasta adjudicación.
```

## ESTADO

```
CERRADO: pozo (completo, fiel, sin duplicados) · causa SV5 (bug del backfill, probada por réplica)
         · contradicción zigzag (intención = toque; código correcto) · los 2 zigzags (1 máquina, 1 regla)
BLOQUEANTE OPERATIVO: el daemon `vault` NO está arriba (docker-compose `vault` con --loop 300 y
         restart: unless-stopped; `docker ps` sólo muestra redis + portainer). Sin cron ni timer.
         ⇒ Sin él, la paridad (D1) y la frescura (D3) se degradan solas.
PENDIENTE DE MEDICIÓN: estabilidad de la amplitud frente a N · el SIGMET (dispara 19-25 % sin discriminar)
         · `SESSION_FINAL_ET=18:00` (¿Yahoo ya tiene el volumen consolidado?) · el propósito del SIGMET.
```

## COMPARABILIDAD DE BENCHMARKS

```
V39 (2026-07-30) → serie HÍBRIDA (SMA5 historia + EMA5 reciente + volúmenes parciales)
V40 (2026-10-05) → serie POST-REBUILD (EMA5 + precios/volúmenes corregidos)
⇒ NO son comparables entre sí: mezclan el cambio de arquitectura con el cambio de serie.
Acción: cerrar D1 y D3 → re-correr V39, V40 y V41 sobre la MISMA serie limpia → entonces comparar versiones.
Declarar los resultados de julio y de octubre como "pre-rebuild, no comparables entre sí".
```
