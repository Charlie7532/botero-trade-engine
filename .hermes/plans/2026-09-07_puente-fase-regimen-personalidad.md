# Puente Fase → Régimen — Constructo central del dossier de personalidad

> **Fecha:** 2026-09-07 · **Propósito:** documento de arquitectura que conecta los conceptos
> de **piso, techo, continuación, acumulación, distribución** con los **regímenes de mercado**,
> a través del rol funcional de cada estación en el árbol CAT1→2→3. Este documento es la base
> sobre la que se construirá el **dossier de personalidad de cada indicador**.
> **Estado:** borrador para validación del usuario (no implementado aún).

---

## 0. Advertencia terminológica: "ROTACIÓN" tiene DOS acepciones (no mezclar)

Este proyecto usa ROTATION con un significado **específico y distinto** del significado coloquial:

| Acepción | Definición | ¿Es nuestra estación ROTATION? |
|---|---|---|
| **Rotación de CAPITAL (risk in/out)** | Flujo de dinero entrando/saliendo del riesgo (asignación de capital, risk-on/risk-off agregado) | ❌ **NO** es lo que mide ROTATION |
| **Rotación de SECTORES** | Cambio de liderazgo entre sectores cíclicos (tech) y defensivos (utilities) | ✅ **SÍ** es nuestra estación ROTATION |

**Verificado en el fact store** (`rotation_fact_store.json`):
```
risk_on  = Cyclical / Tech Leadership (XLY/XLP + XLK/XLU > 0)
risk_off = Defensive / Utility Leadership (XLY/XLP + XLK/XLU < 0)
```
ROTATION mide **qué clase de activos lidera** (cyclical/tech vs defensive/utility), no **cuánto riesgo total hay**. Un mismo nivel de capital puede estar "en rotación ofensiva" o "defensiva".

**Regla de uso en todo lo que sigue:** cuando el documento hable de "rotación" referida a ROTATION, es rotación **de sectores**. Si alguna fase necesitara la noción de capital in/out, se declara explícitamente como concepto separado (NO se le llama "ROTATION" para no colisionar).

---

## 1. La idea central: son FASES de un CICLO; los regímenes son ESTADOS estables del ciclo

Piso, techo, continuación, acumulación y distribución **no son señales sueltas** — son **fases de un
ciclo de mercado**. Un **régimen** es el **estado estable** del ciclo cuando una fase domina con cierta
confluencia.

```
 PISO      →  ACUMULACIÓN   →  CONTINUACIÓN   →  TECHO   →  DISTRIBUCIÓN   →  CRASH
 (capitula)    (re-construye)    (tendencia)       (euforia)   (salida silent)  (sistémico)
      └──────────────── PISO GENERACIONAL (el ciclo reinicia abajo) ────────────────┘
```

**El régimen NO se establece promediando señales. Se establece sabiendo EN QUÉ FASE del ciclo
estás y CON QUÉ confluencia.** (Corrección de Ago-2026: el régimen es la CONCLUSIÓN del árbol,
no un nivel más.)

---

## 2. Tabla maestra: Concepto → Rol funcional (con estaciones reales)

| Concepto | Definición | Rol funcional | Estaciones (datos verificados) |
|---|---|---|---|
| **PISO** | Anticipa/confirma giro alcista desde un suelo | Detector de giro (TIMING) | VVIX (Rng 90%), BSI (93%), FG (86%), VIX (83%), PCR (83%), CREDIT (100%), ROTATION (72%) |
| **TECHO** | Anticipa/confirma giro bajista desde un máximo | Detector de giro (TIMING) | DXY (Rng máx 61%), YIELD (régimen, no timing) |
| **CONTINUACIÓN** | Confirma que la tendencia SIGUE | Confirmador | BSI D1=1 (oversold que ensancha), ROTATION D2=4 (aceleración ofensiva 66.9%) |
| **ACUMULACIÓN** | Post-piso: re-construcción lenta | Confirmador de largo plazo | SKEW D1=0 (única que crece con zz: 67→87→94%), BSI D1=1 |
| **DISTRIBUCIÓN** | Pre-crash: las instituciones salen sin ruido | Régimen de fondo (SIZING) | SV5 D1=0 (calma = distribución silenciosa), VIX D1=0 (complacencia) |

> **Nota sobre ROTATION:** aparece en PISO (D1=0 defensivo, Rng 72%) y en CONTINUACIÓN
> (D2=4 aceleración ofensiva). Es rotación **de sectores**: marcar cuándo el mercado rota hacia
> defensivos (piso/pre-crash) u ofensivos (continuación alcista). No mide capital total in/out.

---

## 3. Clasificación por naturaleza: el árbol CAT1 → CAT2 → CAT3

El lead-time de cada fasuf define en qué parte del árbol vive → cadena causal (no una sopa).

```
CAT1 (economía, lead LARGO) → RÉGIMEN de fondo
   CREDIT (HYG/LQD) · YIELD_CURVE (10Y-3M) · DXY · ROTATION (salida A)

CAT2 (protección, lead MEDIO) → PRECURSOR (anticipa el giro)
   VIX · VVIX · PCR · SKEW
   = institucionales compran protection ANTES de que el precio caiga

CAT3 (acción, lead CORTO) → CONFIRMADOR (la acción YA ocurrió)
   BSI · SV5T · FG · ROTATION (salida B)
   = S5 colapsa (capitulación) / SV5 agita (distribución)
```

**Cadena causal (responde "cómo establecen régimen"):**
```
deterioro macro (CAT1: CREDIT stress, YIELD)
  → institucionales compran puts (CAT2: VIX/VVIX/PCR/SKEW)     = PRECURSOR = SUB-REACCIÓN → ESPERAR
  → mercado AÚN no vende (S5 mantiene)                           = no hay acción aún
  → recién S5 colapsa (CAT3: BSI capitulación)                   = PISO CONFIRMADO → COMPRAR
  → SV5 agita sin VIX (CAT3+CAT2: distribución silenciosa)       = DISTRIBUCIÓN → PRE-CRASH
```

> **Regla operativa (ya fijada):**
> COMPRAR (piso) = economía débil + protección extrema + acción YA descargada (S5 colapsó)
> ESPERAR = protección extrema pero acción aún no (S5 mantiene)
> VENDER (techo) = protección al alza + acción en máximos (euforia)

---

## 4. Fase dominante → RÉGIMEN (el cruce final)

| Fase dominante | Confluencia que la confirma | RÉGIMEN |
|---|---|---|
| Ninguna alarma; estaciones centrales; YIELD normal; DXY neutral | Clima benigno (~68% del tiempo) | **MERCADO_SANO** |
| **DISTRIBUCIÓN**: SV5 D1=0 + VIX complacencia + YIELD empinándose | Pre-crash sin pánico aún | **DISTRIBUCION_PRE_CRASH** |
| **PISO** extremo: CREDIT D1=0 + SV5 turbulencia + DXY fuerte | Congelamiento de liquidez | **CRASH_SISTEMICO** |
| **PISO** confirmado múltiple: capitulación VIX+BSI + FG miedo + PCR put-panic + YIELD inversión | El suelo está | **PISO_GENERACIONAL** |
| **ACUMULACIÓN**: SKEW D1=0 + BSI oversold (tras piso) | Re-construcción | **RE_ACUMULACION_ALCISTA** |
| **CONTINUACIÓN** con momentum: VIX D1=0 deriva + ROTATION D2=4 + DXY D1=1 | Recuperación eficiente | **RECUPERACION** |
| **CONTINUACIÓN** en corrección: divergencia táctica (zz25 bear / zz75 bull) | Retroceso contra tendencia | **PULLBACK_ALCISTA** |

> **El matiz fino (por qué "continuación" figura dos veces con resultado opuesto):**
> la bifurcación sale de la **firma multiescala** zz25/50/75 (divergencia táctica vs convergencia),
> no de una señal aislada. Ese es el eslabón que conecta la personalidad del indicador con el
> régimen: la tríada distingue "sigue la subida" de "corrección pasajera".

---

## 5. Implicación para el dossier de personalidad (qué debe declarar cada ficha)

Cada ficha de estación NO debe quedarse en "es detector de giro". Debe declarar:

1. **Identidad física:** qué mide, dirección D1, inception, universo (N_total, % N<10).
2. **Profesión/polaridad:** piso vs techo vs régimen, y si su D1 está invertido (BSI/CREDIT → D1 bajo = estrés).
3. **Rol en el árbol:** CAT1/2/3 (lead-time).
4. **Fase del ciclo que ayuda a marcar:** piso / techo / continuación / acumulación / distribución.
5. **Firma multiescala:** convergencia vs divergencia zz25/50/75 (conecta con el régimen).
6. **Perfil probabilístico σ×N:** WEATHER (N≥30) / CONFIRMED_ALERT / DIAMOND (N<10) / UNUSUAL_COMBO.

Así el régimen **emerge de componer las fichas** (confluencia de fases + CAT), no de promediarlas.

---

## 6. Fuentes

- `references/arbol-decision-regimenes.md` (árbol CAT1→2→3, hojas ya pobladas, regla operativa)
- `references/decantacion-estaciones-personalidad-sigmas-2026-09-06.md` (niveles σ×N, select_validation_tool)
- `.hermes/plans/clasificacion_naturaleza.md` (las 3 categorías CAT1/2/3)
- `.hermes/plans/sistema_metar_regimenes_v4.md` (secuencia/permutaciones)
- `rotation_fact_store.json` (verificación: ROTATION = sectores XLY/XLP + XLK/XLU, risk_on/risk_off)

---

## 7. Pendientes / decisiones abiertas

- [ ] **Validación del usuario** de este puente (este doc es borrador para eso).
- [ ] Ejercicio de **CONFIRMACIÓN techos/pisos** (cruce P_confirmado = slot × HR direccional),
      que aún no está hecho (Gemini mantiene Rng% desacoplado del HR).
- [ ] Decisión de **credibilidad**: regla usuario N<10 = alarma vs Gemini N bajo+CI Wilson.
- [ ] Redactar el **prompt del dossier de personalidad** sobre esta base.