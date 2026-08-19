# ESTADO DEL SISTEMA — Checkpoint 17-Ago (mediodía)

> Estado consolidado del trabajo. Juan Andrés + Hermes.

---

## ✅ COMPLETADO HOY (17 de agosto)

### 1. Arquitectura METAR de 3 categorías (el avance conceptual)
```
El régimen = la SECUENCIA de activación (no una etiqueta bull/bear):
  CAT 1 (ECONOMÍA)     — CREDIT, YIELD, DXY, ROTATION-A — lead largo (fundamento)
  CAT 2 (SENTIMIENTO)  — VIX, VVIX, PCR, SKEW — lead medio (protección/bochorno)
  CAT 3 (ACCIÓN)       — BSI(S5TW), SV5T, FG, ROTATION-B — lead corto (realidad)

Las permutaciones = regímenes distintos:
  CAT1→CAT2→CAT3 = macro-driven (83%)      CAT2→CAT3→CAT1 = comprar miedo (+3.83% 40d)
  CAT1→CAT3→CAT2 = cuchillo (-5.64% 20d)   CAT3 lidera = explosivo (vol 2×)
```

### 2. Clasificador de secuencias (secuencias_classifier.py)
```
- Firma de permutación ESTABLE en 3 escalas (zz25/zz50/zz75)
- CAT1 lidera 90% de los pivotes; el orden CAT2 vs CAT3 es la señal
- Validado: cuchillo (bearish) y comprar-miedo (bullish) con CI95
```

### 3. σ-Overflow (desbordamiento de escala, ±3σ)
```
- Problema: las bandas σ saturan en ±2σ (VIX 41 = VIX 82 = "CRISIS_SPIKE")
- Solución: sigma_overflow.py — valida overflow ±3σ para D1×D2×D3
- depth = (val-μ)/σ — la profundidad continua (VIX 82 = +8.09σ)
- overflow_flag: UPPER/LOWER/MULTI (MULTI = cisne negro, 2+ dimensiones)
- Fact stores INTACTOS (uno-a-muchos respetado)
- Test 7/7 passed, cascade HEALTHY
```

### 4. 3 Category Agents (completados)
```
CAT 1: EXPANSIÓN 72.5%. CREDIT_STRESS=entry, YIELD=exit, DXY=bearish confirmados
CAT 2: NORMAL 53.1%. PÁNICO TOTAL PF 8.09 reproducido exacto
CAT 3: ALERTA (SV5T extremo). BSI lidera 53.2% anticipación
```

---

## 🔄 EN CURSO

- **COORDINATOR** (deleg_f44477c2): integra 3 categorías + cascade + σ-overflow
  → produce METAR/TAF/SIGMET + determina el régimen por secuencia

---

## ⏳ PENDIENTE

```
1. TIDE (tema aparte): 4 tests fallan por alias lookup_tide_guidance = lookup_real_ev
   (devuelve RealEVSignal sin hazard_alarm) — revertir o corregir el alias

2. Complacencia (extremo BAJO): subestudiada. VIX↓+SKEW↓+PCR↓ = ¿piso o calma?
   Es el espejo del "comprar miedo" que falta medir.

3. Puntos ciegos de eventos (traducir a causa estructural):
   - RALLY ESTRECHO (mega-cap concentration)
   - ACUMULACIÓN vs DISTRIBUCIÓN (dirección del flujo)
   - PÁNICO DE AMPLITUD (8+ sectores distribuyendo)
   - CAPITULACIÓN ESTRUCTURAL (120d)
   - TRAMPA TEMPORAL (gana 5d pierde 20d)

4. Lead-lag empírico entre categorías (la secuencia 1→2→3 NO asumida, medida)

5. Eventos raros del σ-overflow (la "mina de oro"): cada estación×dimensión×dirección
   es un evento especial distinto por estudiar

6. COMPLIANCE CHECK (reglas del proyecto + alineación al sistema):
   - Hypothesis governance (CANDIDATE→HYPOTHESIS→VALIDATED→DEGRADED→RETIRED)
   - Confidence Card obligatoria por señal
   - López de Prado (PBO, mutual info, triple barrier, structural breaks)
   - Esperanza matemática medida = sagrada (no supuestos)
   - METAR GLOBAL (ticker-independiente) vs per-ticker = TIDE
   - 'Nadie porta la verdad absoluta' (anti-adulación, revertir si dato contradice)
   - Regla: mejora local que degrada composite → revertir
   - Arquitectura: 3 categorías + SIGMET bus + secuencia = régimen
```

---

## 📂 ARCHIVOS CLAVE

```
Planes (.hermes/plans/):
  - sistema_metar_regimenes_v4.md     (arquitectura + concepto central)
  - clasificacion_naturaleza.md       (3 categorías por lead-time)
  - inventario_eventos_especiales.md  (4 capas de eventos)
  - plan_agentes_final.md             (arquitectura de agentes + árbol)
  - correccion_sigma_overflow.md      (especificación ±3σ)
  - prompt_sigma_overflow.md          (prompt final a Gemini)

Código:
  - scratch/secuencias_classifier.py  (clasificador de regímenes)
  - scratch/calibrador_sigmet.py      (SIGMET con bandas σ)
  - backend/.../sigma_overflow.py     (validador ±3σ)
  - tests/test_sigma_overflow.py      (7/7 passed)

Resultados de agentes:
  - scratch/cat1_economia.py, cat2_sentimiento.py, cat3_accion.py
```

---

## 🎯 MÉTRICAS DE REFERENCIA (GRADE A)

```
PÁNICO TOTAL (VIX↑+SKEW↑):      PF 8.09, 82% WR 60d, 0 wipeouts
CAPITULACIÓN (VIX↑+S5 colapsó): PF 2.19, +1.51% 20d
SUB-REACCIÓN (VIX↑+S5 mantiene): bearish, esperar
EUFORIA (VIX↓+S5 máximo):        71% bear, techo
CREDIT_STRESS:                   +3.00% 20d, Kelly 50%
EXTREME_FEAR + D3 comprimido:    PF 26.76, WR 87%
DXY DOLLAR_SPIKE_CRISIS:         -1.94%, bearish
YIELD EXTREME_STEEPNING:         exit (PF 0.73)
cascade_conviction:              IC +0.41, PBO 0%, HEALTHY
```