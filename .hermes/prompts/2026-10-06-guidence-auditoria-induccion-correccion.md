# GUÍAS DE AUDITORÍA — inducción a corrección · ejecución F0-F6 en curso

**Objeto:** verificar lo implementado y **forzar corrección** donde no cumpla. Read-only hasta el hallazgo.
**Fuente:** `remediation_plan_auditoria_total.md` (v3, §5 fases · §7 decisiones aprobadas).

## 0 · REGLAS DEL AUDITOR

```
1. Ningún hallazgo sin query+salida pegados. Nada de "se ve bien".
2. Medir MAGNITUD, no conteo. Declarar AMBAS poblaciones antes de comparar.
3. Dos caminos independientes deben CONVERGER. Si no convergen, ese es el hallazgo.
4. Cotas BILATERALES en todo umbral (techo Y piso).
5. No aceptar autorreportes: verificar en la BASE y en el DIFF, no en la descripción.
6. Antes de reportar un defecto: comprobar que no es esperado (fecha del código vs fecha del dato).
7. Un hallazgo = causa + evidencia + corrección concreta. Sin anécdotas.
```

## 1 · ESTADO A AUDITAR (base de partida)

```
Modificados SIN commitear (16): ohlcv_provider · triad_retrainer_provider · breadth_provider ·
  volume_breadth_provider · zigzag_legs_daemon · convergence_compositor · market_sigmet_hazard_service ·
  notam_incident_service · cascade_calibration.json · generate_cascade_calibration · timescale_data_store ·
  zigzag_leg_repository · ports/__init__ · build_zigzag_benchmark · (
Nuevos: zigzag_core.py · ports/zigzag_leg_port.py · tests/test_convergence_compositor_causality.py
Base: market.ohlcv_bars con bar_status + ingested_at (0 filas con estado) · 6.678.766 filas
```

## 2 · VERIFICACIONES POR FASE

### F0.1 — `build_zigzag_benchmark.py` ya no toca producción
```
MEDIR:  grep -c "engine.zigzag_points" en el script (esperado 0 escrituras) · la función que hacía
        CREATE/DELETE ya no existe.
CRITERIO: 0 escrituras a engine.* en el archivo.
CORRECCIÓN SI FALLA: eliminar cualquier INSERT/DELETE/to_sql contra engine.zigzag_points;
        redirigir a parquet en scratch/.
```

### F0.3 — Backups acotados ANTES de cualquier escritura masiva
```
MEDIR:  information_schema.tables con nombre backup.*pre_homog*  (hoy: NO existen).
CRITERIO: existen y su conteo+checksum (md5(string_agg(… ORDER BY …))) coincide con el origen.
CORRECCIÓN SI FALLA: NO ejecutar ninguna fase que escriba. Crear el backup acotado primero
        (40 series SV5 = 453.847 filas · zigzag_legs solo SPY).
```

### F0.5 / Q4 — Retrainer congelado
```
MEDIR:  _is_retrain_due() con ENABLE_TRIAD_AUTORETRAIN sin definir ⇒ debe devolver False.
CRITERIO: sin la variable, no reentrena. Rutas relativas (no /root/botero-trade/…).
CORRECCIÓN SI FALLA: congelar antes del 2026-10-08 (los JSON son del 10-01; el umbral es 7 días).
```

### F1.1 / F1.2 — Estado de barra: esquema y cadena de escritura
```
MEDIR:  (a) columnas bar_status/ingested_at existen · (b) _tag_bar_status → df["bar_status"] →
        save_bars lee la COLUMNA (has_status_col) · (c) COALESCE(EXCLUDED.bar_status, tabla.bar_status).
CRITERIO: una barra nueva escrita por el provider queda con bar_status ∈ {PRELIMINARY, FINAL} e ingested_at.
CORRECCIÓN SI FALLA: si el estado no llega a la base, F1 es decorativa ⇒ conectar el camino de escritura.
⚠️ NOMBRES: el código usa 'PRELIMINARY'/'FINAL'; el plan dice 'PROVISIONAL'.
   Alinear la prosa del plan (o el literal) — no dejar dos vocabularios.
```

### F1.4 — Propagación de revisiones a los derivados
```
MEDIR:  revisar una barra en una fecha D y comprobar que S5*, SV5*, S5CAP*, VBI*, SV5_TURBULENCE y
        las legs/points de SPY se re-derivan desde D.
PRUEBA OBLIGATORIA: verificador estilo c1 §3 sobre TODAS las series de amplitud, últimas 60 sesiones:
        MAD guardado vs recalculado = 0,00.
CRITERIO: MAD 0,00 (hoy SV5TW del 2026-10-02 falla con 0,2).
CORRECCIÓN SI FALLA: extender la marca de sucio a las series que falten; re-derivar desde la mínima.
```

### F1.5 — Frescura medida sobre el dato
```
MEDIR:  el NOTAM_VAULT_STALE se emite con 2 sesiones de retraso simulado y NO con datos al día.
CRITERIO: umbral sobre max(time) vs última sesión NYSE cerrada y cobertura del universo ≥ 98 %.
CORRECCIÓN SI FALLA: no usar mcp_snapshots/BATCH_DONE como señal (hay barras sin ese registro).
```

### F2.1 — Causalidad
```
MEDIR:  get_confirmed_legs debe recibir as_of_date en TODAS las llamadas del compositor.
CRITERIO: un replay al 2021-09-17 NO ve la leg confirmada el 2021-09-20.
Estado hoy: tests/test_convergence_compositor_causality.py PASA (3 tests).
CORRECCIÓN SI FALLA: revisar que no quede ninguna llamada sin as_of_date en otros consumidores
        (generate_cascade_calibration, v3_fact_table_engine, generate_dxy_fact_table, generate_quants_obs).
```

### F2.2 — Kernel único
```
MEDIR:  compute_zigzag_* existe y AMBOS consumidores lo usan (backfill_zigzag_points y zigzag_legs_daemon).
CRITERIO: 'close' reproduce zigzag_points de SPY al 100 % (868/300/136) ·
        'extreme' reproduce bit a bit la salida actual de zigzag_legs.
CORRECCIÓN SI FALLA: si difiere en >0,1 %, el kernel no es equivalente ⇒ NO promover.
```

### F2.5 / F2.6 — Rebuild de legs de SPY + recalibración
```
MEDIR:  % de legs iguales por escala (antes 96,5/93,8/92,1 %) · tramos nuevos y perdidos con su causa ·
        delta bilateral estado por estado en los 11 fact stores y cascade_calibration.
CRITERIO: ningún estado degenerado; ninguna celda con n ≥ 30 cambia de signo sin explicación.
Estado hoy: cascade_calibration.json con 10 claves (0 nuevas, 0 huérfanas), 6 valores recalibrados,
        0 degenerados.
CORRECCIÓN SI FALLA: revertir el JSON (está en git) y rehacer con el informe de delta publicado.
```

### F2.7 — Columnas aditivas en las tablas zigzag
```
MEDIR:  engine.zigzag_points → confirmed_at · ambas tablas → same_bar_pair.
Hoy: NO existen.  CRITERIO: nullable y pobladas de forma determinista; conteo de same_bar_pair en SPY.
CORRECCIÓN SI FALLA: ADD COLUMN nullable (metadata, barato: 1.205 chunks, 0 comprimidos).
```

### F3b — SIGMET retirado
```
MEDIR:  el bloque SV5_TURBULENCE ≥ 10,0 eliminado y su import fuera.
Estado hoy: retirado.  CRITERIO: ningún literal 10.0 de SV5_TURBULENCE en el emisor.
CORRECCIÓN SI FALLA: corregir AGENTS.md ("> 10 = crisis proxy" queda falsado) y dejar la estación
        como telemetría METAR informativa.
```

### F4 — Escritor único
```
MEDIR:  tests/test_single_writer.py existe y PASA · las tres rutas de channel_snapshots producen
        filas idénticas en 5 tickers × 50 fechas · conteo de 0,0 fabricado por familia antes/después.
Hoy: test AUSENTE.  CORRECCIÓN SI FALLA: crear el test con lista blanca (AST/grep).
```

## 3 · VERIFICACIONES TRANSVERSALES (ninguna fase las cubre)

```
T1. COMPILA todo el árbol (compileall exit 0) tras cada cambio.
T2. HIGIENE: ningún trabajo desechable en el árbol del repo. Hoy hay 6 scratch_*.py en
    backend/scripts/ ⇒ mover a scratch/ (están untracked, no entran al commit).
T3. TRAZABILIDAD: 16 archivos modificados SIN COMMITEAR y 0 backups. Antes de escribir masivamente:
    backup + un solo escritor activo. Después: informe de delta.
T4. NINGÚN LITERAL de umbral con SV5 en el código (10,0 · 8,90 · 12,80) ⇒ todos del fact store
    con metadata (valor · percentil · ventana · % de disparo).
T5. La discrepancia de 0,2 del SV5TW 2026-10-02: resolverla, no arrastrarla.
T6. Prohibido --force en producción (hoy el daemon se lanza a mano desde el hilo paralelo; --force
    anula las guardas de "ya hecho hoy").
T7. V39/V40 marcados como pre-homogeneización. Cada benchmark nuevo registra data_vintage
    (fecha del rebuild + versión del kernel + hash de los fact stores).
```

## 4 · SALIDA ESPERADA

```
Por hallazgo: causa · evidencia (query+salida) · fase afectada · CORRECCIÓN concreta · quién la aplica.
Y un tablero por fase: CUMPLE / NO CUMPLE / N/A, con la evidencia al lado.
Si una fase está a medias, declararla a medias — no cerrarla por proximidad.
```
