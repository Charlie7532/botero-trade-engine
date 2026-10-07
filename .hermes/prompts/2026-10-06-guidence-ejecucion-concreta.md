# GUÍAS DE EJECUCIÓN — Remediación v3 (Ingesta + ZigZag + SV5 `*_TW`)

**Principio:** Read-only hasta el OK de cada fase. Cada fase termina en punto de aprobación estricto (Regla 22).

---

## 1 · ESTADO DE PARTIDA (VERIFICADO EMPÍRICAMENTE)
```
Pozo: 6.481.574 barras 1d · 1927→2026 · sin duplicados (UNIQUE btree: ticker, timeframe, time via idx_ohlcv_dedup) · 752 tickers en metadata.
SV5: 40 series = 33 sectoriales (11×3) + 3 QQQ + 3 globales + 1 SV5_TURBULENCE.
     Las *_TW (13) + SV5_TURBULENCE = 14 series con EMA5 especificado (sectors.py:185). FI/TH son SMA: intactas.
     La serie viva YA es EMA5 en toda la historia (rebuild 2026-10-04: MAD 0,00 en 2026).
     Lo pendiente es RECONCILIAR revisiones no propagadas (ej. 2026-10-02: 43,1 vs 43,3) y calibraciones, NO reconstruir.
ZigZag: engine.zigzag_points (confirmación por CIERRE) · market.zigzag_legs (por TOQUE intrabarra).
     Misma máquina de estados: emparejando la regla coinciden al 100 % (SPY 868/300/136).
     zigzag_legs: 4.045.542 filas · 613 tickers · última confirmación 2026-08-03 (SPY zz25 07-31).
     Consumo productivo de zigzag_legs = SOLO SPY (Compositor L643/649, generators/cascade, fact stores).
Ingesta: guarda por reloj activa (_drop_unfinished_session, 18:00 ET). OVERLAP_DAYS=7 ancla por última barra del ticker.
     Devengo: 68 BATCH_DONE en 2026 · 18 huecos >3 días · máximo 11,8 días (retraso, no pérdida de barras).
```

---

## 2 · CRONOGRAMA DURO Y RIESGO DE SOBREESCRITURA
```
1. Retrainer automático: triad_retrainer_provider.py L28-40 verifica: domingo O mtime(JSON) > 7 días.
   mtime actual en disco: 2026-10-04 21:49:55 UTC (vence el 2026-10-11).
   RIESGO INMEDIATO: data_vault_daemon ejecutado con --force (como corre ad hoc en el hilo 3b3ccf19, 15× hoy)
   anula _already_vaulted_today (L73: if _FORCE_REFRESH: return False).
   ⇒ F0.5 (congelar retrainer automático) es prioritaria e inmediata para evitar sobreescrituras sin delta.
2. Destino del Daemon (F0.2): antes de cualquier backfill o escritura en Neon, verificar que no haya instancias
   concurrentes con --force corriendo en Portainer o en el host.
```

---

## 3 · FASES DETALLADAS

### F0 — Seguridad Inmediata y Censo Operativo (Sin escritura en datos)
```
F0.0  SEGURIDAD INMEDIATA (Código): build_zigzag_benchmark.py L110:
      Eliminar DELETE FROM engine.zigzag_points sin WHERE clause.
      Redirigir L165 a parquet local en scratch/ (prohibido escribir en tablas maestras sin schema benchmark.).
F0.1  Censo operativo en el momento: docker ps -a · pg_stat_activity · confirmar que no hay procesos daemon activos.
F0.2  Decidir y verificar dónde corre el daemon (este host vs Portainer). BLOQUEANTE para escrituras en Vault.
F0.3  Backup acotado con conteo y checksum md5(string_agg(...ORDER BY...)):
      - backup.ohlcv_bars_sv5_pre_homog_20261006 (40 series SV5 = 453.847 filas, 7,0 % del pozo).
      - backup.zigzag_points_pre_homog_20261006 (tabla engine completa).
      - backup.zigzag_legs_spy_pre_homog_20261006 (solo SPY para F2).
F0.4  Commit de control con el estado actual de los JSON de reglas en git.
F0.5  Congelar triad_retrainer_provider.py: insertar guard/flag explícito (ENABLE_TRIAD_AUTORETRAIN=False)
      para bloquear cualquier reentrenamiento ciego sin reporte de delta.
ACEPTACIÓN: L110 neutralizado · censo verificado (cero daemons activos) · backups con conteo idéntico · retrainer blindado.
```

### F2.1 — Causalidad Estricta en Compositor (Adelantada — Aprobado Q7 — Solo Código)
```
F2.1  convergence_compositor.py:
      - L643/L649: Pasar as_of_date=as_of_dt a repo.get_confirmed_legs("SPY", "zz25"/"zz50"), convirtiendo
        el parámetro str a fin del día UTC (23:59:59.999999+00) antes de filtrar por confirmed_at_timestamp.
      - Clean Architecture: Inyectar ZigzagLegRepository por puerto/constructor; eliminar la instanciación directa
        de TimescaleDataStore() en L640-642 (dominio no debe importar infraestructura).
      - Manejo de excepciones: Eliminar except Exception: pass en L652-653 y el fallback ciego pivot_type="MIN"
        en L655-656; registrar logger.warning con fallback determinista justificado (Regla 10).
      - Test: tests/test_convergence_compositor_causality.py validando que un replay al 2021-09-17 no recibe
        la leg confirmada el 2021-09-20.
ACEPTACIÓN: Replay histórico no contiene look-ahead · tests de integración pasan sin regresión.
```

### F1 — Ingesta: Estado, Propagación y Señal de Frescura
```
F1.1  Columnas ADITIVAS en market.ohlcv_bars:
      ALTER TABLE market.ohlcv_bars ADD COLUMN bar_status VARCHAR(12) DEFAULT NULL;
      ALTER TABLE market.ohlcv_bars ADD COLUMN ingested_at TIMESTAMPTZ DEFAULT NULL;
      Valores: 'PROVISIONAL' (captura post-18:00 ET), 'FINAL' (consolidada en T+1).
      CRÍTICO: NULL histórico equivale semánticamente a FINAL. Prohibido ejecutar UPDATE masivo sobre los
      6,48M de filas (evita saturación de WAL y locks en los 1.205 chunks de TimescaleDB).
F1.2  Cura por ESTADO y Comparador Invariante a Escala:
      - Ventana de ingesta: start = min(fecha PROVISIONAL más antigua, last_bar - OVERLAP_DAYS).
      - Barras PROVISIONAL se re-consultan y promocionan a FINAL tras verificar consolidación post-cierre.
      - Comparador: detección de revisiones por volumen O por distorsión de forma (o/c, h/c, l/c > 1e-6).
      - Detección de split/ajuste: si el ratio de precio/volumen es constante != 1 en toda la ventana,
        marcar para recarga histórica completa del ticker, evitando empalmes híbridos de 7 días.
F1.3  Propagación a Derivados:
      Cualquier barra revisada/curada en la fecha D marca dirty_from = D en el Vault.
      Los providers de amplitud (volume_breadth, sector_volume_breadth) recalculan desde dirty_from:
      S5*, SV5*, S5CAP*, VBI*, SV5_TURBULENCE, y legs de SPY.
      Resuelve la discrepancia de 0,2 en SV5TW (2026-10-02: 43,1 stored vs 43,3 recalc).
F1.4  Señal de Frescura (NOTAM):
      Si a las 20:00 ET max(time) de SPY < última sesión NYSE, o cobertura < 98 %, emitir NOTAM_VAULT_STALE
      en /api/notam/incidents. Gates incorporan frescura en su contexto decisional (Regla 17).
F1.5  Detección de Acciones Corporativas:
      Disparar alerta y registrar en ticker_lifecycle_handoff.md ante variaciones > 45 % / < -31 %
      con volumen anómalo (casos CTVA 10-01 y MRNA 08-19).
ACEPTACIÓN: Columnas creadas (O(1)) · prueba de propagación dirty_from elimina discrepancia de 0,2 · NOTAM funcional.
```

### F2 — ZigZag: Kernel Canónico, Rebuild SPY y Recalibración Integral
```
F2.2  Kernel único en backend/modules/shared/domain/rules/zigzag_core.py:
      compute_zigzag(high, low, close, pct, confirm_on="close"|"extreme").
      Test de paridad algorítmica:
      - confirm_on="close" reproduce al 100 % engine.zigzag_points en SPY (868/300/136) y 99,8-100 % en AMD/KO.
      - confirm_on="extreme" reproduce bit a bit la salida de zigzag_legs_daemon.
F2.3  Rebuild de market.zigzag_legs — SOLO SPY:
      Ejecutar sync_ticker_zigzag_legs para SPY cubriendo ago-oct 2026 sobre barras curadas.
      Legs huérfanos de 48 tickers S5*/S5CAP* se conservan congelados al 08-03 sin borrar (Aprobado Q5).
      save_legs() en zigzag_leg_repository.py se retira de uso (Aprobado Q6).
F2.4  Columnas aditivas: same_bar_pair BOOLEAN DEFAULT FALSE en ambas tablas; confirmed_at en zigzag_points.
F2.6  RECALIBRACIÓN INTEGRAL DE CALIBRACIONES Y FACT STORES (Sin complacencia):
      Al actualizar las legs de SPY a octubre 2026 y disponer de SV5_TURBULENCE en EMA5:
      1. Recalibrar cascade_calibration.json ejecutando backend/scripts/generators/generate_cascade_calibration.py
         (re-deriva d1_bear_5, domino_zz25, domino_zz50, tercile_edges y type_mask sobre las legs de SPY).
      2. Recalibrar los 11 Fact Stores METAR ejecutando backend/scripts/generators/generate_all_150_state_fact_stores.py
         (especialmente sv5_turbulence_fact_store.json y timing con los nuevos percentiles EMA5).
      3. Ejecutar en scratch/ primero y publicar informe de delta bilateral estado por estado (Δp_bull, ΔEV, desplazamientos σ).
      4. Tras validación de no-degeneración, promover los JSONs a domain/rules/ y commitear.
ACEPTACIÓN: Paridad del kernel verificada · legs de SPY cubren hasta la última sesión · informe de delta bilateral publicado ·
calibraciones y fact stores sincronizados formalmente.
```

### F3 — SV5: Reconciliación, Edges, Literales, Rotación y Retiro SIGMET
```
F3.1  Confirmación por mes de homogeneidad EMA5 en las 14 series (MAD 0,00 en 2026).
F3.2  Test de paridad daemon ↔ backfill: tests/test_volume_breadth_parity.py validando coincidencia float exacta.
F3.3  sv5_turbulence_fact_store.json y timing_fact_store.json actualizados con edges Gaussianos σ de EMA5:
      P50 = 7,60 (antes 5,97); P75 = 10,89 (antes 10,18); P90 = 15,22 (antes 14,18).
F3.4  Sustituir literales 10.0 (3 sitios), 8.90 y 12.80 en quality_entry_gate.py por lecturas dinámicas
      de los percentiles del fact store con metadata completa (Regla 21).
F3.5  Sector Rotation Gate: mapear umbrales v_tw >= 60, sec_v_tw >= 40/50, vol_div >= -5 a sus cuantiles homólogos
      en la distribución EMA5 sin curve-fitting (walk-forward test).
F3.6  Re-entrenar Triad S5V (train_s5v_triad.py) y Triad S5 (train_s5_triad.py) con informe de delta por celda.
      Corrige el aprendizaje contaminado del SV5_QQQ_TW corrupto anterior.
F3b   RETIRO DE SIGMET SV5_TURBULENCE (Aprobado Q3 = Opción A):
      - Evidencia: >= 10 dispara 24,7 % de los días con lift 1,06 sobre drawdown (inútil como alarma extrema, viola Regla 23).
      - Retirar SV5_TURBULENCE del emisor de avisos severos en market_sigmet_hazard_service.py.
      - Mantener la estación en METAR (/api/metar/sv5_turbulence) como telemetría informativa ordinaria.
      - Corregir en AGENTS.md la afirmación falsada: "SV5_TURBULENCE > 10 = crisis proxy".
ACEPTACIÓN: Paridad verificada · literales eliminados · triads re-entrenados con delta publicado · SIGMET retirado.
```

### F4 — Contrato de Escritor Único por Tabla
```
F4.1  tests/test_single_writer.py: inspección AST y grep con lista blanca estricta.
      - market.ohlcv_bars: solo TimescaleDataStore.save_bars (vía providers autorizados).
      - engine.channel_snapshots: INSERT solo TimescaleDataStore.save_channel_snapshot; DELETE solo ohlcv_provider.
      - market.zigzag_legs: solo zigzag_legs_daemon.py.
      - engine.zigzag_points: solo cron diario y backfill_zigzag_points (vía kernel close).
F4.2  Kernel único compute_channel_snapshot:
      backfill_channel_snapshots_v2.py y wipe_reload_cascade.py invocan compute_channel_snapshot y
      persisten vía TimescaleDataStore. Fallbacks 0.0 sustituidos por None/NULL (P11).
F4.3  Enganchar sincronización diaria de zigzag_legs de SPY al ciclo POST-ingesta de data_vault_daemon.
ACEPTACIÓN: test_single_writer pasa y detecta cualquier segundo escritor no autorizado.
```

### F5 — Benchmarks Comparativos por Vintage de Datos
```
Declaración formal de Vintages:
- V-A (pre-mayo 2026): SMA5 pura offline + SV5_QQQ_TW corrupto en backup.
- V-B (mayo 2026 → 2026-10-03): datos vivos contaminados con barras parciales (incluye V39 de julio y V40).
- V-C (desde 2026-10-04): serie homogénea EMA5 + barras curadas + SPY legs actualizadas.
F5.1  Marcar formalmente V39 y V40 como "PRE-HOMOGENEIZACIÓN (NO COMPARABLES CON V-C)" en sus respectivos reportes.
F5.2  Re-ejecutar benchmarks V39/V40/V41 estrictamente sobre vintage V-C, con idéntica ventana y población declarada.
ACEPTACIÓN: V39/V40 etiquetados · comparativa limpia publicada sobre V-C.
```

### F6 — Higiene del Sistema y Documentación
```
P4   Sesgo de membresía: cuantificar y declarar ventana de comparabilidad (1980: 158; 2000: 353; 2008: 416; 2026: 506).
P7   Estabilidad de la amplitud frente a N en las mismas fechas (mínimo sectorial hoy: 20 en Basic Materials).
P9   forensic_v13_triple_regression.py: importar calc_vwap_with_std canónico y corregir docstring.
P10  signal_adapters.py:1375: below_vwap -> Optional[bool] con None propagado (eliminar fallback a False).
P11  Sustituir fallbacks 0.0 por NULL en snapshots (ejecutado en F4.2).
P12  Regenerar AGENTS.md y data_registry.md DESDE LA BASE:
     Total real: 6.481.574 barras 1d, 752 tickers en metadata, umbrales P50/P90 de SV5_TURBULENCE en EMA5,
     eliminación de "> 10 = crisis proxy", y definición "TW = EMA5v > 20v".
P13  engineer_features.py y quaternion_core.py: eliminar clip(lower=1.0) que fabrica VWAP=0 en ventanas sin volumen;
     utilizar kernel canónico.
ACEPTACIÓN: Scripts de investigación alineados al kernel canónico · AGENTS.md y data_registry.md 100 % sincronizados con Neon.
```

---

## 4 · REGLAS DE EJECUCIÓN (INVIOLABLES)
```
1. Punto de aprobación obligatorio por fase antes de avanzar a la siguiente.
2. Censo y backup acotado con conteo y checksum antes de cualquier mutación de datos.
3. Un solo escritor activo a la vez. Cero ejecuciones concurrentes del daemon.
4. Prohibido ejecutar --force en producción.
5. Inviolabilidad dimensional: solo cambian escalas/edges, jamás bins, etiquetas ni llaves vectoriales (Regla 24).
6. Enfoque aditivo (ADDITIVE-ONLY): preservar historia, columnas nullable, cero UPDATEs masivos que saturen hypertables.
7. Sin complacencia: toda calibración que dependa de datos actualizados (legs SPY, EMA5) se recalcula y audita.
8. Todo reporte comparativo exige cotas bilaterales y declaración explícita de poblaciones (Regla 23/24).
9. Regla 22: cero mutaciones en base de datos o git sin validación y aprobación del usuario.
```

---

## 5 · DECISIONES CONSOLIDADAS
```
D1   SV5 *_TW = EMA5 canónico (confirmado en Vault desde 10-04). Prohibido duplicar series (no SV5TW_EMA).
D2   Una máquina ZigZag, dos parametrizaciones:
     - engine.zigzag_points: confirm_on="close" (Triad, RC, Tide, Wave, Sentinel).
     - market.zigzag_legs: confirm_on="extreme" (METAR, Cascade, Compositor).
D3   Causalidad estricta: as_of_date obligatorio en toda consulta de legs.
Q1   bar_status VARCHAR(12) DEFAULT NULL + ingested_at TIMESTAMPTZ en market.ohlcv_bars. NULL = final histórico.
Q2   Daemon: ubicación única con supervisor y sin --force (este host vs Portainer verificado).
Q3   SIGMET SV5_TURBULENCE: Retirado del emisor de alertas severas. Telemetría confinada a METAR ordinario.
Q4   Retrainer automático: congelado con flag explícito hasta completar F3.
Q5   Legs huérfanos de 48 tickers S5*: conservados congelados al 08-03 sin borrar.
Q6   save_legs() en repositorio: retirado de lista blanca y eliminado.
Q7   F2.1 (as_of_date en compositor + Clean Architecture port) adelantada inmediatamente tras F0.
```

---

## 6 · SECUENCIA EXACTA DE ARRANQUE
```
1. F0.0 (Neutralizar DELETE en build_zigzag_benchmark) + F0.5 (Congelar auto-retrainer)  [Seguridad Código]
2. F0.1 (Censo operativo) + F0.2 (Verificación ubicación daemon) + F0.3 (Backups acotados) [Seguridad Datos]
3. F2.1 (as_of_date en Compositor + Clean Architecture port)                             [Look-ahead Código]
4. F1 (Ingesta: columnas O(1), comparador invariante a escala, dirty_from, NOTAM)        [Pozo y Fuente]
5. F2 (Kernel único, Rebuild SPY legs, Recalibración Integral Calibraciones/Fact Stores) [Targets y Metar]
6. F3 (Paridad SV5, Retiro SIGMET F3b, Umbrales Dinámicos, Triads sincronizados)        [Domain Rules]
7. F4 (Contratos de escritor único + test_single_writer AST)                             [Gobernanza]
8. F5 (Re-ejecución de Benchmarks V-C con poblaciones declaradas)                       [Validación]
9. F6 (Higiene P4/P7/P9-P13 + Regeneración AGENTS.md y data_registry desde la base)      [Cierre y Docs]
```
