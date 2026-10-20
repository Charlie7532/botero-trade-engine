# GUÍAS F5 — BENCHMARKS COMPARATIVOS POR VINTAGE DE DATOS
**Fecha:** 07-Oct-2026 · **Base:** verificado en disco antes de redactar (no tomado del enunciado del plan)

---

## 0. PRERREQUISITOS VERIFICADOS

```
HARNESS CANÓNICO (de facto, ya existe — no hay que inventarlo):
   backend/scripts/generators/generate_v40_full_master_benchmark.py
      expone: SECTORS_11 (11 ETFs sectoriales) · load_data(store) · run_benchmark(pivot, sec_pivot,
      macro_pivot, use_vix=True) · compute_regime_stats(df) · compute_yearly_stats(df) · main()
   generate_v41_comparative_benchmark.py LO IMPORTA y lo reutiliza (load_data, SECTORS_11,
      compute_regime_stats, compute_yearly_stats) ⇒ es la base compartida de los tres.
   ⇒ Los walk_forward_*.py sueltos (dsr, narrative_dsr, rc_rsi_dsr…) NO son este harness: no mezclar.

VENTANA declarada por los generadores: 2000-01-01 → 2026, que el docstring de V41 cifra en 6.653
días de trading.

   🔴 NO COINCIDE CON LOS DATOS ACTUALES: medido hoy, SPY tiene **6.730 días** desde 2000-01-01
      (diferencia de 77 días).
      Causa probable: la recarga de barras del rebuild (10-04) incorporó días que antes faltaban,
      y el docstring quedó describiendo la población VIEJA.
      ⇒ ⇒ CONSECUENCIA DIRECTA PARA F5.2: si V39/V40 se corrieron con 6.653 días y V-C corre sobre
        6.730, la comparación NO es homogénea — y F5.2 exige explícitamente "idéntica ventana y
        población declarada".
      ⇒ RESOLVER ANTES DE CORRER: fijar la ventana efectiva y decidir si se recorta V-C a la
        intersección con V-B, o se re-corren los tres sobre la ventana nueva (declarándola).


V41 = "SV5_SHOCK Volume Risk Modifiers" contra el baseline V40.

VINTAGES (del plan, no modificados):
   V-A  pre-mayo-2026: SMA5 pura offline + SV5_QQQ_TW corrupto en backup.
   V-B  may-2026 → 2026-10-03: datos vivos contaminados con barras parciales (incluye V39 y V40).
   V-C  desde 2026-10-04: serie homogénea EMA5 + barras curadas + SPY legs actualizadas.
```

---

## 1. 🔴 HALLAZGO QUE CONDICIONA F5.1 (verificado)

```
Los reportes de V39/V40/V41 EXISTEN — pero TODOS fuera del repositorio, en el brain del IDE:

   /root/.gemini/antigravity-ide/brain/747582b8-…/
       reporte_comparativo_v40_vs_v41.md        tablas_comparativas_v39.md
       benchmark_v40_exhaustivo.md              benchmark_exhaustivo_v40.md
       reporte_comparativo_regimenes_y_anios.md benchmark_v41_vs_v41_1_auditado.md
       auditoria_trade_by_trade_v41_vs_v41_1.md auditoria_forense_v41_gates.md
       v40_signal_contribution_study.md         directiva_anti_fallback_v40.md
   /root/.gemini/antigravity-ide/brain/2000c42e-…/benchmark_comparison.md

   Y el propio generador escribe ahí:
       generate_v41_comparative_benchmark.py L150 →
       art_path = "/root/.gemini/antigravity-ide/brain/747582b8-…/reporte_comparativo_v40_vs_v41.md"

⇒ Etiquetar "PRE-HOMOGENEIZACIÓN (NO COMPARABLE CON V-C)" sobre artefactos que NO están versionados
  no es auditable: el etiquetado se pierde y nadie puede re-verificarlo.
⇒ PRIMER PASO OBLIGATORIO: copiarlos al repo con ruta canónica, COMMITEARLOS, y sólo entonces etiquetar.
⇒ Y corregir el generador para que escriba SIEMPRE al repo — si no, el próximo reporte se vuelve a perder.
```

---

## 2. F5.1 — ETIQUETADO

```
1. Mover los reportes de V39/V40 al repo (propuesta de ruta: data/research/benchmarks/vintage_V-B/).
2. Encabezar cada uno con: "VINTAGE V-B (pre-homogeneización) — NO COMPARABLE CON V-C" + el motivo
   medido (SMA5/EMA5 en las 14 series *_TW · barras parciales · SPY legs desalineadas).
3. Cambiar el art_path de los generadores a una ruta versionada.
ACEPTACIÓN: `git ls-files` muestra los reportes etiquetados (verificable, no declarativo).
```

---

## 3. F5.2 — RE-EJECUCIÓN SOBRE V-C

```
· Correr V39 · V40 · V41 sobre V-C, con ventana (2000-01-01 → fin) y población IDÉNTICAS y declaradas
  en el propio reporte.
· Cada reporte debe FIRMAR su vintage: fecha de corrida · conteo de barras · conteo de pivotes ·
  hash de las entradas (quants_obs.pkl y las tablas de triad vigentes).

⇒ APLICAR LA LECCIÓN DE ESTA SESIÓN (commit 58354ed): BASE FIJA + ARTEFACTO PERSISTIDO.
  Nada de comparar contra "HEAD" (la evidencia se autodestruye al commitear, ya nos pasó).
  Comparar V-C contra una revisión fija de V-B, y persistir el delta en JSON/CSV fechado.
```

---

## 4. ⚠️ ADVERTENCIA METODOLÓGICA (la más importante)

```
Entre V-B y V-C cambiaron DOS COSAS A LA VEZ: los DATOS (barras curadas, EMA5, legs) y el MODELO
(kernel ZigZag nuevo → triad re-entrenada → relative_modifiers re-calculados).

⇒ Un delta de Sharpe acierto/asimetría medido entre V-B y V-C mezcla ambos efectos y NO es atribuible
  a "la limpieza" por sí sola.
⇒ Para atribuir hacen falta brazos de control:
     brazo A: modelo VIEJO + datos NUEVOS (V-C)     → aísla el efecto DATO
     brazo B: modelo NUEVO + datos VIEJOS (V-B)     → aísla el efecto MODELO
     y la corrida completa V-C (modelo nuevo + datos nuevos)
⇒ Sin al menos un brazo, el titular "delta de Sharpe por las series limpias" sería un relato, no una
  medición.  Es una DECISIÓN a adjudicar, no una obviedad.
```

---

## 5. ORDEN DE EJECUCIÓN

```
1. Versionar los reportes V39/V40 (F5.1) + corregir el art_path de los generadores.
2. Fijar la base V-B como revisión inmutable (rev o tag) antes de correr nada.
3. Correr V39/V40/V41 sobre V-C con ventana y población declaradas y entradas hasheadas.
4. Persistir los reportes en el repo + el delta V-B→V-C (JSON/CSV) con timestamp.
5. (Opcional, si se aprueba) brazo de control para separar modelo de dato.
```

---

## 6. ACEPTACIÓN

```
· V39/V40 etiquetados Y versionados (git ls-files).
· Los tres reportes V-C en disco: ventana + población + vintage + hashes declarados en el propio archivo.
· Comparativa V-B → V-C publicada con delta por régimen y por año.
· Generadores escribiendo al repo (no al brain del IDE).
· (Si se aprueba) brazo de control corrido y reportado.
```

## 7. DECISIONES A ADJUDICAR

```
D-1  ¿Dónde se versionan los reportes de benchmark?  (propuesta: data/research/benchmarks/)
D-2  ¿Se corre el brazo de control para separar efecto MODELO de efecto DATO?
D-3  ¿La ventana se mantiene 2000-2026, o se declara una sub-ventana común a V-B y V-C?
```
