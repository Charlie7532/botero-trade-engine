# GUÍAS DE EJECUCIÓN — Remediación v3 (Ingesta + ZigZag + SV5 `*_TW`)

Read-only hasta el OK de cada fase. Cada fase termina en punto de aprobación.

## 1 · ESTADO DE PARTIDA
```
Pozo: 6.481.574 barras · 1927→2026 · sin duplicados (idx_ohlcv_dedup) · 752 tickers
SV5: 40 series = 33 sectoriales (11×3) + 3 QQQ + 3 globales + 1 SV5_TURBULENCE
     Las *_TW (13) + SV5_TURBULENCE = 14 series con EMA5 especificado. FI/TH son SMA: intactas.
     La serie viva YA es EMA5 en toda la historia (verificado por recálculo: Δ −1,2 vs SMA5 Δ +4,2/+8,3).
     Lo pendiente es RECONCILIAR, no reconstruir.
ZigZag: engine.zigzag_points (confirmación por CIERRE) · market.zigzag_legs (por TOQUE intrabarra).
     Misma máquina de estados: emparejando la regla coinciden al 100 % (SPY 868/300/136).
     zigzag_legs: 4.045.542 filas · 613 tickers · última confirmación 2026-08-03 (SPY zz25 07-31).
     Consumo productivo de zigzag_legs = SOLO SPY.
Ingesta: guarda por reloj activa (_drop_unfinished_session, 18:00 ET). OVERLAP_DAYS=7 ancla por ticker.
     Devengo: 68 BATCH_DONE en 2026 · 18 huecos >3 días · máximo 11,8 días.
```

## 2 · CRONOGRAMA DURO
```
ANTES DEL 2026-10-08: triad_retrainer_provider.py L28-40 ⇒ _is_retrain_due() = domingo O JSON >7 días.
   JSON actuales: 10-01. Cualquier arranque del daemon desde el 10-08 reentrena solo, sin informe de delta.
   ⇒ F0.5 obligatoria.
```

## 3 · FASES

### F0 — Seguridad y censo (sin escritura)
```
F0.1  Censo operativo: docker ps -a · pg_stat_activity · autor de cada escritura. No hay supervisor;
      el daemon se lanza a mano (hilo 3b3ccf19, --force, 15×). --force anula las guardas de "ya hecho hoy".
F0.2  Decidir dónde corre el daemon (host local o Portainer). BLOQUEANTE.
F0.3  Backup acotado: 40 series SV5 = 453.847 filas (7,0 %). Con conteo y checksum.
      backup.zigzag_points_pre_homog_20261006 · backup.zigzag_legs_pre_homog_20261006
F0.4  Commit del estado actual de los JSON de reglas.
F0.5  Gate del retrainer: informe de delta + rutas relativas + aviso.
ACEPTACIÓN: censo pegado · destino del daemon escrito · backups con conteo verificado.
```

### F1 — Ingesta: estado, propagación, frescura
```
F1.1  Columnas ADITIVAS en market.ohlcv_bars: bar_status ('PROVISIONAL'|'FINAL') e ingested_at.
F1.2  Cura por ESTADO: sobrescribir TODAS las PROVISIONAL en cada corrida, sin límite de antigüedad.
      Fuera del conjunto provisional: mantener la clave de VOLUMEN.
F1.3  Propagar revisiones a los derivados. Hoy sólo se invalida channel_snapshots (L165, L203-214).
      Añadir: S5 · SV5 · S5CAP · VBI · SV5_TURBULENCE · zigzag.
F1.4  Señal de frescura (NOTAM) cuando el último bar FINAL supere N sesiones. N medido.
F1.5  Detección de acciones corporativas (CTVA 10-01 close ×0,162/vol ×21,9 · MRNA 08-19 ×2,77/vol ×46).
ACEPTACIÓN: bar_status en toda la historia · una revisión de prueba se propaga (delta bilateral) ·
frescura emite aviso.
```

### F2 — ZigZag: kernel, escritor único, rebuild
```
F2.1  as_of_date en convergence_compositor L643 y L649. Test: replay sin piernas futuras.
F2.2  Kernel único: compute_zigzag(high, low, close, pct, confirm_on="close"|"extreme") en zigzag_core.py.
      Sin cambiar ninguna regla. Test de paridad contra AMBAS tablas (SPY 868/300/136 · AMD/KO 99,8-100 %).
F2.3  Rebuild de market.zigzag_legs sobre las barras actuales — SOLO SPY. Cubrir ago-oct 2026.
F2.4  Columnas aditivas: same_bar_pair en ambas tablas · confirmed_at en engine.zigzag_points.
      No se modifica ningún pivote.
F2.5  build_zigzag_benchmark.py: quitar DELETE sin WHERE (L110); salida a benchmark. o parquet.
F2.6  Publicar delta en los 11 fact stores METAR y cascade_calibration (usan las legs de SPY como target).
ACEPTACIÓN: paridad del kernel · replay sin look-ahead · delta de fact stores publicado y aprobado.
```

### F3 — SV5: reconciliación, edges, literales, Rotación, triad
```
F3.1  Confirmar por mes, en las 14 series, que la serie viva es EMA5 en toda la historia.
F3.2  tests/test_volume_breadth_parity.py: daemon ↔ backfill, mismo float en cualquier fecha.
      Resolver la discrepancia de 0,2 del 2026-10-02.
F3.3  Re-derivar edges D1 y percentiles sobre la serie viva (determinista):
      sv5_turbulence_fact_store.json · sv5_turbulence_timing_fact_store.json · personalidad de la estación.
F3.4  Sustituir literales 10,0 (3 sitios) · 8,90 · 12,80 por percentiles declarados con metadata
      (valor · percentil · ventana de calibración · % de disparo). Sobre la serie EMA5 son ≈P68 y ≈P88.
F3.5  Rotación: SV5_EDGES["TW"] · v_tw ≥ 60 · vol_div ≥ −5 · sec_v_tw ≥ 40/50 · hybrid_scores ·
      druckenmiller_causal_rules.
F3.6  Re-entrenar triad SV5 (train_s5v_triad.py) tras F1, F2.6 y F3.3.
F3b   SIGMET: ≥10 dispara 24,7 % con precisión 14,8 % y lift 1,06 sobre drawdown. Sólo P99 (20,56)
      muestra señal (lift 1,5-1,9 · n=69). Revalidar el propósito o retirarlo. "SV5_TURBULENCE > 10
      = crisis proxy" queda falsado.
ACEPTACIÓN: paridad verificada · edges y literales derivados y declarados · triad con informe de delta ·
decisión escrita sobre el SIGMET.
```

### F4 — Contrato de escritor único
```
F4.1  tests/test_single_writer.py (AST + lista blanca). Hoy: channel_snapshots (4 escritores) ·
      zigzag_legs (2) · zigzag_points (3).
F4.2  Kernel único compute_channel_snapshot; los demás lo invocan. Fallbacks 0.0 → None/NULL.
F4.3  Enganchar zigzag_legs_daemon al ciclo POST-ingesta de OHLCV.
ACEPTACIÓN: el test falla ante un segundo escritor · paridad daemon vs backfill en una fecha.
```

### F5 — Benchmarks por vintage
```
V-A hasta abr-2026: SMA5 puro · V-B may-2026→10-03: híbrido (V39 de julio) · V-C 10-04→: EMA5 homogéneo
F5.1  Marcar V39 y V40 como pre-homogeneización, no comparables con V-C.
F5.2  Re-correr V39/V40/V41 en V-C tras F1-F4, misma ventana y misma población declarada.
ACEPTACIÓN: V39/V40 marcados · benchmarks re-corridos con población declarada.
```

### F6 — Higiene y docs
```
P4  Sesgo de membresía: cuantificar 2000-2008 (353→416 constituyentes · 158 en 1980).
P7  Estabilidad de la amplitud frente a N en las mismas fechas (mínimo sectorial hoy: 20).
P9  forensic_v13: importar calc_vwap_with_std + corregir el docstring.
P10 below_vwap → Optional[bool] con None propagado (contar casos por fecha antes).
P11 Fallbacks 0.0 → None/NULL en backfill_channel_snapshots_v2 Y en la copia de wipe_reload_cascade.
P12 Regenerar AGENTS.md y data_registry.md DESDE LA BASE (TOTAL ~5,80M vs 6.481.574 · 752 tickers, no 630).
P13 engineer_features y quaternion_core al kernel canónico (clip(lower=1) fabrica VWAP=0; min_periods=1).
    Compositor: no instanciar TimescaleDataStore en dominio (L640-642) · quitar except: pass (L652-653) ·
    quitar pivot_type="MIN" por defecto (L655-656).
    Legs huérfanos: 48 tickers de amplitud hasta 2026-08-01/03.
```

## 4 · REGLAS DE EJECUCIÓN
```
1. Punto de aprobación por fase.
2. Antes de escribir: censo + backup acotado con conteo y checksum.
3. UN escritor activo a la vez. Después: informe de delta con cotas BILATERALES.
4. Dimensiones inviolables (sólo escalas/edges). ADDITIVE-ONLY.
5. No borrado total: conservar y migrar lo útil, con evidencia escrita.
6. Todo umbral medido/derivado o declarado como decisión. Nada heredado sin medición.
7. Medir magnitud, no conteo. Declarar ambas poblaciones antes de comparar.
8. Dos caminos independientes deben converger; si no, ese es el hallazgo.
9. Regla 22: nada escrito en el Vault sin verificación.
10. Nada se ejecuta sin decidir dónde corre el daemon (F0.2).
```

## 5 · DECISIONES
```
D1  SV5 *_TW = EMA5 (en el Vault desde el rebuild del 10-04). Sin duplicar series. Pendiente: reconciliar.
D2  Una máquina zigzag, dos disparadores (close → zigzag_points · extreme → zigzag_legs). Se unifica el kernel.
D3  as_of_date obligatorio en toda lectura de legs.
```

## 6 · ORDEN DE ARRANQUE
```
F0.5 (vence 10-08) → F0.2 (ubicación del daemon) → F0.3 (backups) → F1 → F2 → F3 → F4 → F5 → F6
```
