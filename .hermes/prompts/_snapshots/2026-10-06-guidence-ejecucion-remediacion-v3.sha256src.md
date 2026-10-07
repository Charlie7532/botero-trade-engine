# GUÍAS DE EJECUCIÓN — Plan de remediación v3 (Ingesta + ZigZag + SV5 `*_TW`)

**Fuente:** `remediation_plan_auditoria_total.md` (Claude, 2026-10-06 16:51, sha `727df13927372eed…`)
**Prompt de origen:** `.hermes/prompts/2026-10-05-homogeneizacion-sv5-zigzag-v2.md` (sha `60af207c…`)
**Modo de partida:** read-only. Cada fase termina en **punto de aprobación** del usuario.

---

## 0 · Estado verificado — PUNTO DE PARTIDA (no re-litigar)

```
✅ La serie VIVA de SV5 ya es EMA5.  Recalculado desde los constituyentes:
      2026-09-25 VIVO 45,8 · recalc EMA5 47,0 (Δ −1,2) · recalc SMA5 41,6 (Δ +4,2)
      2026-09-30 VIVO 44,3 · recalc EMA5 45,6 (Δ −1,3) · recalc SMA5 37,0 (Δ +7,3)
      2026-10-01 VIVO 47,8 · recalc EMA5 48,9 (Δ −1,1) · recalc SMA5 39,5 (Δ +8,3)
   ⇒ El rebuild del 10-04 ya respetó la config. LA HOMOGENEIZACIÓN YA OCURRIÓ.
   ⇒ El trabajo pendiente NO es reconstruir: es RECONCILIAR (paridad, propagación, edges,
     literales, triad) y cerrar la ingesta.

✅ El zigzag NO cambió.  Misma ventana (2021-04-30..2026-06-22) AMD: 523 → 524 pivotes.
✅ La guarda por reloj de barra parcial YA EXISTE (ohlcv_provider.py L178-182, 18:00 ET, 10-04).
   OVERLAP_DAYS=7 se ancla en la última barra POR TICKER ⇒ un hueco de 11 días da RETRASO, no pérdida.
✅ Los 23 días de volumen falso ya se curaron: 0 días con mediana <0,6 en el pozo vivo (19 en el backup).
✅ Nada salió de circulación: S5* 72→72 · SV5* 40→40. Dimensiones intactas.
✅ El pozo: 6.481.574 barras · 1927→2026 · sin duplicados (idx_ohlcv_dedup).
```

## 0-bis · LO RETIRADO — NO RE-LITIGAR

```
✗ "hay que reconstruir las 14 series *_TW"      → ya hecho (la serie viva es EMA5)
✗ "EMA5 gana el mérito aguas abajo"             → el recall sube porque DISPARA más (18,7 %→24,7 %);
                                                  a igual tasa: prec 12,9→15,4 %, AUC 0,505→0,521 (azar)
✗ "D3 = cero recalibración"                     → FALSO: fact stores METAR y cascade usan las legs de SPY
                                                  como TARGET; SPY recalc coincide 96,5/93,8/92,1 %
✗ "SV5_QQQ_TW −68,2 pts"                        → el BACKUP estaba corrupto; el vivo = EMA5 exacto
✗ "el daemon no tiene guarda / OVERLAP en el borde" → la guarda existe; el hueco da retraso, no pérdida
✗ "23 días de volumen falso vivos"              → no reproducido (ya curados)
✗ "SIGMET 1 de cada 5 con prec. 13,8 %"         → es 1 de cada 4 (24,7 %) con prec. 14,8 %; 13,8 % es V41 HIGH
✗ "AMD 101,7 → 110,9 pivotes/año"               → comparaba ventanas distintas
✗ "el backfill usó el default del calculador"    → rodaba su propia fórmula (L74); el default es riesgo latente
✗ "36 sectoriales (12×3)"                        → son 33 (11×3) + 3 QQQ + 3 globales + 1 TURBULENCE
```

---

## 1 · CRONOGRAMA DURO

```
🔴 ANTES DEL 2026-10-08 (en 2 días):
   triad_retrainer_provider.py L28-40 ⇒ _is_retrain_due() = domingo O JSON con mtime > 7 días.
   Los JSON son del 10-01 ⇒ cualquier arranque del daemon desde el 10-08 REENTRENA SOLO,
   sin informe de delta, con rutas absolutas /root/botero-trade/… (L76/L88).
   ⇒ F0.5 es OBLIGATORIA y tiene reloj: o se le pone gate + informe de delta, o se congela.
```

---

## 2 · FASES

### F0 — Seguridad y censo operativo (SIN escritura en datos)
```
F0.1  Re-ejecutar el censo operativo: docker ps -a · pg_stat_activity · quién lanza el daemon.
      Verificado: hoy NO hay supervisor; el hilo 3b3ccf19 lo arrancó a mano con --force (15 veces).
      --force ANULA las guardas de "ya hecho hoy" (fundamental BATCH_DONE se escribió 6 veces desde 09-28).
F0.2  Decidir DÓNDE corre el daemon: este host o Portainer.  ← BLOQUEANTE. Las stacks remotas
      no son visibles desde aquí: las revisa el usuario.
F0.3  Backup ACOTADO (no de las 6,48 M de barras): las 40 series SV5 = 453.847 filas (7,0 %).
      Con verificación de conteo y checksum.
      backup.zigzag_points_pre_homog_20261006 · backup.zigzag_legs_pre_homog_20261006
F0.4  Backup de los JSON de reglas antes de cualquier retrain (están en git: verificar que el
      estado actual esté commiteado).
F0.5  🔴 GATE DEL RETRAINER (vence el 10-08): informe de delta + rutas relativas + aviso.
ACEPTACIÓN: censo pegado · destino del daemon decidido por escrito · backups con conteo verificado.
```

### F1 — Ingesta: estado, propagación, frescura (la pieza que evita la recaída)
```
F1.1  Columna ADITIVA de estado/procedencia en market.ohlcv_bars: bar_status ('PROVISIONAL'|'FINAL')
      e ingested_at.  (Nada de renombrar ni borrar columnas.)
F1.2  Cura por ESTADO, no por ventana: en cada corrida, re-descargar y sobrescribir TODAS las
      PROVISIONAL sin límite de antigüedad.  Fuera del conjunto provisional, mantener la clave
      de VOLUMEN (protege de los reajustes por dividendo).
F1.3  PROPAGAR las revisiones a los derivados: hoy sólo se invalida channel_snapshots (L165, L203-214).
      S5/SV5/S5CAP/VBI/SV5_TURBULENCE y zigzag NO se recalculan.
      Evidencia: SV5TW 2026-10-02 guardado 43,1 vs recálculo 43,3 (n=506).
F1.4  Señal de frescura: NOTAM cuando el último bar FINAL tenga más de N sesiones (N medido).
      68 BATCH_DONE en 2026 · 18 huecos > 3 días · máximo 11,8 días.  BATCH_DONE no sirve como
      señal (hay barras sin ese registro).
F1.5  Detección de acciones corporativas: CTVA 2026-10-01 close ×0,162 con volumen ×21,9 ·
      MRNA 2026-08-19 ×2,77 con volumen ×46.  Verificar a mano (va con P8).
ACEPTACIÓN: bar_status poblado en toda la historia · una revisión de prueba se propaga a los
derivados (delta bilateral) · frescura emite aviso · sin escritura concurrente durante la prueba.
```

### F2 — ZigZag: kernel, escritor único, rebuild (acotado a SPY)
```
F2.1  as_of_date en convergence_compositor.py L643 y L649 (un argumento, dos sitios).
      Test: tests/test_convergence_compositor_causality.py — un replay no debe tomar piernas futuras.
F2.2  Kernel único parametrizado en modules/shared/domain/rules/zigzag_core.py:
      compute_zigzag(high, low, close, pct, confirm_on="close"|"extreme").
      Adaptar backfill_zigzag_points.py ("close") y zigzag_legs_daemon.py ("extreme").
      NO se cambia ninguna regla de confirmación.  Test: tests/test_zigzag_kernel_parity.py
      (paridad contra AMBAS tablas: SPY 868/300/136 · AMD/KO 99,8-100 %).
F2.3  Rebuild de market.zigzag_legs sobre las barras actuales — SOLO SPY (es el único consumo
      productivo; los otros 569 tickers sólo alimentan investigación).
      Verificar que se cubran los tramos de agosto a octubre 2026 (última confirmación hoy: 08-03).
F2.4  Columnas ADITIVAS: same_bar_pair BOOLEAN en ambas tablas (8,2 % en zigzag_points ·
      22,0 % en zigzag_legs zz25) y confirmed_at TIMESTAMPTZ en engine.zigzag_points.
      NO se toca ningún pivote: la marca la consume quien decida filtrar.
F2.5  build_zigzag_benchmark.py: quitar el DELETE sin WHERE (L110) y redirigir su escritura a
      schema benchmark. o parquet local.
F2.6  🔴 DELTA EN LOS FACT STORES METAR Y CASCADE (esto es la recalibración que yo negaba):
      los 11 fact stores y cascade_calibration usan las legs de SPY como TARGET.  El SPY recalc
      coincide 96,5/93,8/92,1 % ⇒ publicar el delta ANTES de aceptar el rebuild.
ACEPTACIÓN: paridad del kernel contra ambas tablas · replay sin look-ahead · delta de fact stores
publicado y aprobado.
```

### F3 — SV5: reconciliación (NO reconstrucción), edges, literales, Rotación, triad
```
F3.1  Confirmar formalmente que la serie viva es EMA5 en TODA la historia (evidencia propia ya existe;
      falta la del ejecutor, por mes, en las 14 series).
F3.2  Paridad daemon ↔ backfill: tests/test_volume_breadth_parity.py — el mismo valor float en
      cualquier fecha arbitraria.  (Causa raíz del desastre: dos implementaciones sin test.)
      Discrepancia conocida a resolver: 0,2 el 2026-10-02.
F3.3  Re-derivar los edges D1 y percentiles sobre la serie viva (DETERMINISTA, no re-ajuste):
      sv5_turbulence_fact_store.json · sv5_turbulence_timing_fact_store.json · personalidad de la estación.
F3.4  Eliminar literales: 10,0 (3 sitios) · 8,90 · 12,80 → percentiles declarados con metadata
      (valor, percentil, ventana de calibración, % de disparo) en el fact store.
      Nota: los comentarios dicen "8,90 = P75, 12,80 = P90" y sobre la serie EMA5 son ≈P68 y ≈P88.
F3.5  Rotación: SV5_EDGES["TW"] · v_tw ≥ 60 · vol_div ≥ −5 · sec_v_tw ≥ 40/50 · hybrid_scores ·
      druckenmiller_causal_rules.
F3.6  Re-entrenar triad SV5 (train_s5v_triad.py) — SÓLO después de F1, F2.6 y F3.3.
F3b   PROPÓSITO DEL SIGMET (no es recalibración).  Serie EMA5, 1999→2026-04, n=6.863:
      ≥10 dispara 24,7 % con precisión 14,8 % y lift 1,06 sobre drawdown ⇒ incumple la Regla 23
      en AMBOS ejes (no es raro, no discrimina).  Sólo P99 (20,56) muestra señal (lift 1,5-1,9,
      n=69 agrupados en pocos episodios, sin intervalo de confianza).
      ⇒ Revalidar el propósito o retirarlo como SIGMET.  Queda falsado "SV5_TURBULENCE > 10 = crisis proxy".
ACEPTACIÓN: paridad verificada · edges y literales derivados y declarados · triad reentrenada con
informe de delta · decisión escrita sobre el SIGMET.
```

### F4 — Contrato de escritor único
```
F4.1  tests/test_single_writer.py: inspección de AST — ninguna tabla del Vault con más de un
      escritor autorizado (lista blanca).  Patrón calc_vwap_with_std.
      Escritores hoy: channel_snapshots (4) · zigzag_legs (2) · zigzag_points (3).
      channel_snapshots: timescale_data_store.py:1170 (channel_snapshot_provider → compute_channel_snapshot) ·
      backfill_channel_snapshots_v2.py:396 · wipe_reload_cascade.py:390 (+DELETE L182) ·
      ohlcv_provider.py:209 (DELETE de invalidación).
F4.2  Kernel único de snapshots: compute_channel_snapshot; los demás lo invocan.
      Fallbacks 0.0 propios de los backfills: a None/NULL (P11).  Contar filas por familia.
F4.3  Enganchar zigzag_legs_daemon al ciclo POST-ingesta de OHLCV (hoy no está enganchado a nada).
ACEPTACIÓN: el test falla si aparece un segundo escritor · paridad daemon vs backfill en una fecha.
```

### F5 — Benchmarks por vintage de datos
```
V-A: hasta abr-2026 — SMA5 puro (histórico)
V-B: may-2026 → 2026-10-03 — HÍBRIDO: SMA5 histórico + barras parciales del daemon (14-19 días
     contaminados)  ⇒ es donde corrió V39 (julio)
V-C: 2026-10-04 → — EMA5 homogéneo (post-rebuild)
F5.1  Declarar V39 y V40 NO comparables con cualquier resultado V-C.  Marcarlos "pre-homogeneización"
      en sus informes y en la memoria de evidencia.
F5.2  Re-correr V39/V40/V41 en V-C, DESPUÉS de F1-F4, misma ventana y misma población declarada.
F5.3  Tabla comparativa sólo dentro de V-C.
ACEPTACIÓN: V39/V40 marcados · benchmarks re-corridos con la misma población declarada.
```

### F6 — Higiene y docs
```
F6.1  P4 (sesgo de membresía): cuantificar 2000-2008 (353→416 constituyentes, 158 en 1980).
F6.2  P7 (GLOBAL_MIN_N=100 / SECTOR_MIN_N=10): medir estabilidad frente a N en las mismas fechas.
      Hoy el mínimo sectorial es 20 ⇒ el 10 sólo actúa en el pasado.
F6.3  P9 forensic_v13: importar calc_vwap_with_std + corregir el docstring que dice "Production VWAP".
F6.4  P10 below_vwap: Optional[bool] con None propagado; contar los casos por fecha antes.
F6.5  P11 fallbacks 0.0: None/NULL en backfill_channel_snapshots_v2 Y en la copia de wipe_reload_cascade.
F6.6  P12 docs: regenerar las tablas de AGENTS.md y data_registry.md DESDE LA BASE (no a mano).
      La fila TOTAL dice ~5,80M; el pozo tiene 6.481.574.  Y "752 tickers", no 630.
F6.7  P13 engineer_features (producción) y quaternion_core (research): usar el kernel canónico.
      clip(lower=1) sobre la suma de volumen fabrica VWAP=0 en ventanas sin volumen; min_periods=1.
F6.8  El compositor (dominio) instancia infraestructura (L640-642 TimescaleDataStore) + except: pass
      (L652-653) + pivot_type="MIN" por defecto (L655-656) ⇒ viola Clean Architecture y la Regla 10.
F6.9  48 tickers de amplitud con legs huérfanos hasta 2026-08-01/03 (sin consumidor productivo).
```

---

## 3 · REGLAS DE EJECUCIÓN

```
1. Cada fase termina en PUNTO DE APROBACIÓN del usuario.  No se encadena sin OK.
2. Antes de cualquier escritura masiva: (a) censo operativo re-ejecutado, (b) backup acotado con
   conteo y checksum verificados.
3. UN SOLO ESCRITOR ACTIVO a la vez.  Después de la escritura: informe de delta con cotas BILATERALES.
4. Dimensiones INVIOLABLES (sólo escalas/edges).  ADDITIVE-ONLY.
5. NO borrado total: conservar y migrar lo útil, con evidencia escrita.
6. Todo umbral: medido/derivado o DECLARADO como decisión.  Nada heredado sin medición.
7. Medir MAGNITUD, no conteo.  Declarar AMBAS poblaciones antes de comparar.
8. NO ANCLAR: dos caminos independientes deben CONVERGER; si no, ese es el hallazgo.
9. Regla 22: nada escrito en el Vault sin verificación.
10. Nada se ejecuta mientras no se decida dónde corre el daemon (F0.2).
```

## 4 · ESTADO DE LAS DECISIONES

```
D1  SV5 *_TW = EMA5 → YA ESTÁ EN EL VAULT (rebuild 10-04).  Justificación: ESPECIFICACIÓN
    (config desde 02fa9f3) + corrección del bug, NO mérito predictivo (marginal, cerca del azar).
    No se crea SV5TW_EMA: una sola fuente de verdad.  ⇒ El pendiente es RECONCILIAR, no reconstruir.
D2  Una máquina zigzag, dos disparadores (close → zigzag_points · extreme → zigzag_legs).
    Equivalencia medida al 100 % en SPY.  Se unifica el KERNEL, no la regla.
D3  Causalidad estricta: as_of_date OBLIGATORIO en toda lectura de legs.
```
