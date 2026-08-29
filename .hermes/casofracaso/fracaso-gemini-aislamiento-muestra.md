# CASO DE FRACASO: Gemini y el Aislamiento de Muestra
## Cómo una muestra aislada produjo 5 fallos en cadena
## Botero Trade — Documentado 20-Ago-2026

---

## FICHA TÉCNICA DEL FRACASO

| Campo | Valor |
|-------|-------|
| **Ejercicio** | Aislamiento de "caídas no detectadas" (14 de 43 → 8.7% del total) |
| **Resultado reportado por Gemini** | 91.3% cobertura de techos, 92.9% cobertura de pisos |
| **Resultado real** | 73.3% cobertura de techos, 64.9% cobertura de pisos |
| **Inflación de cobertura** | Techos: +18pp · Pisos: +28pp |
| **Origen del error** | Gemini aisló 14 caídas no detectadas, buscó señales en ese subconjunto, encontró coincidencias sin validar contra la muestra completa |
| **Señales invalidadas** | Yield Curve como EXIT (p=0.9746), BSI Oversold como piso (69% activación base), SKEW Tail Risk como capa nueva (60-86% overlap) |
| **Fecha** | 19-Ago-2026 |
| **Detectado por** | Juan Andrés (auditoría manual contra datos) + Auditoría interna formal |

---

## 1. LA SECUENCIA DEL FRACASO (paso a paso)

```
PASO 1 — AISLAR LA MUESTRA PROBLEMA
─────────────────────────────────────
Gemini: "Hay 43 caídas que el sistema no detecta. Vamos a aislarlas."
→ Toma las 14 caídas NO detectadas como muestra de estudio

PASO 2 — BUSCAR PATRONES EN LA MUESTRA AISLADA
──────────────────────────────────────────────
Gemini: "En estas 14 caídas, veo que Yield Curve está invertida en el 91% de los casos."
→ Concluye: "Yield Curve como señal de EXIT sube cobertura al 91.3%"

PASO 3 — NO VALIDAR CONTRA LA MUESTRA COMPLETA
───────────────────────────────────────────────
Gemini NO calcula:
  ✗ Chi² de Yield Curve como discriminante (resultó p=0.9746)
  ✗ Tasa de activación base de BSI Oversold (resultó 68.9% de TODOS los pisos)
  ✗ Overlap de SKEW con señales existentes (resultó 60-86%)
  ✗ N_eff corregido por clustering (N inflado 2.86x-6.96x)

PASO 4 — REPORTAR COMO DESCUBRIMIENTO
───────────────────────────────────────
Gemini: "Floor Engine V2 alcanza 92.9% de cobertura. Sistema Protector Total V3."
→ Presenta coincidencias como si fueran señales validadas
```

---

## 2. LOS 5 FALLOS EN DETALLE

### 🔴 FALLO 1: Yield Curve como señal de EXIT

| Campo | Valor |
|-------|-------|
| **Lo que dijo Gemini** | "Al incorporar Yield Curve, la cobertura de techos salta del 73.3% al 91.3%" |
| **Lo que dijeron los datos** | Chi² = 0.0010, p-value = 0.9746 |
| **Interpretación del p-value** | La Yield Curve NO tiene NINGÚN poder discriminante. p=0.97 es peor que lanzar una moneda |
| **Por qué Gemini se equivocó** | No calculó su p-value contra el grupo de control (YC normal/steep). Reportó mejora de cobertura sin cuestionar si era por poder predictivo o por volumen bruto de activación |
| **Dato adicional** | Disparó en el 73.6% de los MAX en los 1990s y en el 81.4% en los 2020s. Es ruido de fondo presentado como señal |

**Lección:** Cobertura ≠ poder predictivo. Una variable que se activa en el 81% de los casos "cubre" el 81% de los eventos, pero no DISCRIMINA. Es una constante, no una señal.

---

### 🔴 FALLO 2: BSI Oversold como señal de piso

| Campo | Valor |
|-------|-------|
| **Lo que dijo Gemini** | "BSI Oversold atrapa el 82.5% de los pisos perdidos. Floor Engine V2 sube a 92.9%" |
| **Lo que dijeron los datos** | BSI Oversold dispara en 548 de 795 pivotes MIN (68.9% de TODOS los pisos) |
| **Por qué es una constante, no una señal** | Una variable que se activa en el 69% de la población NO es un detector — es ruido de fondo. "Si yo dijera 'mi detector de incendios tiene 92% de cobertura', pero el sensor se enciende el 69% de los días del año, me despedirían" |
| **Falsas alarmas** | 78 falling knives. Peor caso: -13.92% |
| **Error metodológico** | Confundió SENSIBILIDAD (recall) con ESPECIFICIDAD (precision). Reportó solo lo primero sin medir lo segundo |

**Lección:** Antes de reportar una señal como "detector", medir su TASA DE ACTIVACIÓN BASE. Si dispara en >50% de los casos, no es una señal — es background.

---

### 🔴 FALLO 3: SKEW Tail Risk como "nueva capa V4"

| Campo | Valor |
|-------|-------|
| **Lo que dijo Gemini** | "12 de 14 techos no detectados tienen SKEW Tail Risk. La cobertura sube al 98.7%. Agreguemos una capa V4" |
| **Lo que dijeron los datos** | Matriz de overlap con señales existentes: |
| | vix_complacency: 86% · credit_divergence: 82% · bsi_recovery: 69% |
| | def_rotation: 65% · sv5t_silence: 60% |
| **Por qué no es una capa nueva** | SKEW Tail Risk ya está IMPLÍCITO en el 60-86% de las señales existentes. Es la misma información medida desde otro ángulo. Agregarlo como capa independiente infla la cobertura reportada sin agregar información nueva al vector de decisión |
| **Error metodológico** | No calculó la MATRIZ DE OVERLAP antes de proponer SKEW como capa adicional |

**Lección:** Antes de proponer una "nueva capa", medir el OVERLAP con las capas existentes. Si el overlap es >60%, no es una capa nueva — es información redundante.

---

### 🔴 FALLO 4: N inflado por clustering temporal

| Campo | Valor |
|-------|-------|
| **Lo que reportó Gemini** | credit_equity_divergence: N=120, CI95 = [-4.06%, -2.10%] |
| **Lo que dijeron los datos** | 120 disparos → solo 42 clusters independientes (ventana 30d) |
| | yield_inv: 383 disparos → 55 clusters (inflación 6.96x) |
| | skew_tail: 523 disparos → 98 clusters (inflación 5.34x) |
| **Factor de inflación** | Los N reportados están inflados entre 2.86x y 6.96x respecto a eventos macro independientes |
| **Consecuencia** | Los intervalos de confianza son MÁS ESTRECHOS de lo que deberían ser. La significancia estadística está inflada |
| **Error metodológico** | No se implementó block bootstrap. No se reportó N_eff (tamaño de muestra efectivo corregido por autocorrelación) |

**Lección:** Las señales que disparan en RÁFAGAS (varios pivotes consecutivos) tienen N inflado. Cada ráfaga cuenta como UN evento independiente, no como N eventos. El bootstrap simple sin clustering subestima la incertidumbre.

---

### 🔴 FALLO 5: Narrativa sin test de hipótesis

| Campo | Valor |
|-------|-------|
| **Lo que dijo Gemini** | "La tendencia es tu amiga hasta que se vuelve tu peor enemiga. Los Higher Highs con Extreme Greed tienen Cascade 7.5% de 36.4% (Lift 1.32x)" |
| **Lo que faltó** | No se sometió a test de hipótesis. No se comparó contra un baseline aleatorio. No se midió la significancia del lift 1.32x |
| **Error metodológico** | Construyó una NARRATIVA ("tendencia amiga/enemiga") y luego buscó datos que la confirmaran, en vez de formular una HIPÓTESIS y someterla a test estadístico |

**Lección:** "Lift 1.32x" sin CI95, sin test de hipótesis, sin baseline aleatorio, no es un descubrimiento — es una observación. La diferencia entre "observación" y "descubrimiento" es el test de hipótesis.

---

## 3. DIAGNÓSTICO DE RAÍZ: ¿POR QUÉ GEMINI FALLÓ?

### Causa raíz 1: Aislar la muestra ANTES de validar

```
FLUJO CORRECTO:
  1. Formular hipótesis sobre la MUESTRA COMPLETA (1,590 pivotes)
  2. Medir señal en la muestra completa
  3. CI95 + bootstrap + tasa de activación base + overlap matrix
  4. Solo DESPUÉS de validar, aislar subconjuntos para entender

FLUJO DE GEMINI (incorrecto):
  1. Aislar 14 caídas no detectadas ← EL ERROR
  2. Buscar patrones SOLO en esas 14
  3. Encontrar coincidencias (Yield Curve, BSI Oversold, SKEW)
  4. Reportar como descubrimientos sin validar contra la muestra completa
```

**El problema:** Cuando aislás una muestra PEQUEÑA (14 eventos) y buscás patrones en ella, SIEMPRE vas a encontrar coincidencias. El sesgo de selección garantiza que encuentres "algo". Pero ese "algo" no necesariamente generaliza a la muestra completa.

### Causa raíz 2: No aplicar el estándar de validación

```
ESTÁNDAR QUE GEMINI DEBERÍA HABER APLICADO (y no aplicó):

  ✓ Bootstrap CI95 (seed fija)
  ✗ Chi² / p-value de poder discriminante    ← FALLO 1
  ✗ Tasa de activación base                  ← FALLO 2
  ✗ Matriz de overlap con señales existentes ← FALLO 3
  ✗ N_eff corregido por clustering           ← FALLO 4
  ✗ Test de hipótesis formal                 ← FALLO 5
```

### Causa raíz 3: Complacencia — reportar sin verificar

```
El patrón de complacencia de Gemini:

  1. Encuentra un patrón en datos aislados
  2. ASUME que es una señal (sin verificarlo)
  3. Construye una narrativa alrededor ("Floor Engine V2", "Sistema Protector V3")
  4. Reporta como descubrimiento
  5. No incluye los tests de validación que refutarían su propio hallazgo

Esto es LO OPUESTO al principio "dato mata relato".
Gemini construyó un RELATO y buscó DATOS que lo confirmaran.
```

---

## 4. CÓMO SE DETECTÓ EL FRACASO

```
1. JUAN ANDRÉS detectó inconsistencia:
   "91.3% de cobertura no puede ser cierto"

2. Auditoría manual contra datos:
   - Yield Curve: Chi² = 0.0010, p = 0.9746 → sin poder discriminante
   - BSI Oversold: activación en 68.9% de todos los pisos → constante, no señal
   - SKEW: 60-86% overlap → información redundante
   - N inflado 2.86x-6.96x por clustering

3. REGAÑO FORMAL AL EQUIPO:
   Documento regano_formal_equipo.md emitido el 19-Ago-2026
   5 fallos documentados con datos exactos

4. DIAGNÓSTICO DE PROMPTING:
   Documento diagnostico_prompting.md:
   "Los prompts conversacionales son vulnerables. La estructura se pierde."
   "La frustración reemplaza la especificación → complacencia defensiva."
```

---

## 5. CONTRASTE: POR QUÉ forense_precursores.py y medir_senal.py NO FALLARON

| Aspecto | Gemini (falló) | qwen3.8-max (no falló) |
|---------|----------------|------------------------|
| **Muestra** | Aisló 14 eventos → sesgo de selección | Usó los 1,590 pivotes completos |
| **Validación** | Reportó cobertura sin p-value | Bootstrap CI95 en cada métrica |
| **N reportado** | N inflado (sin N_eff) | N exacto de la muestra de pivotes |
| **Overlap** | No midió overlap con señales existentes | forense_precursores.py mide cross-señal universalidad |
| **Tasa base** | No midió tasa de activación base | medir_senal.py reporta baseline homogéneo (mismo pivot_type) |
| **Métrica** | Cobertura (recall sin precision) | Distribución completa (P5/P95) + CI95 + wins/losses separados |
| **Código** | Prompt conversacional → ambigüedad | Código determinista → mismo input, mismo output |

---

## 6. LAS 5 LECCIONES DEL FRACASO

### Lección 1: Nunca aislar la muestra antes de validar

```
REGLA:   Validar en la muestra COMPLETA primero.
         Solo DESPUÉS de que el CI95 no cruza cero, aislar subconjuntos para entender.

VIOLACIÓN: Gemini aisló 14 caídas → encontró coincidencias en ese subconjunto →
           reportó como descubrimientos sin validar contra los 1,590 pivotes.

CONSECUENCIA: 5 fallos en cadena. 91.3% reportado → 73.3% real.
```

### Lección 2: Cobertura ≠ poder predictivo

```
REGLA:   Una variable que se activa en el 69% de los casos "cubre" muchos eventos,
         pero no DISCRIMINA. Medir SIEMPRE especificidad junto con sensibilidad.

VIOLACIÓN: Gemini reportó "92.9% cobertura" de BSI Oversold sin mencionar
           que dispara en el 68.9% de TODOS los pisos. Es una constante, no una señal.

CONSECUENCIA: 78 falling knives. Peor caso: -13.92%.
```

### Lección 3: Overlap matrix antes de nueva capa

```
REGLA:   Antes de proponer una "nueva capa", medir overlap con capas existentes.
         Si overlap > 60%, no agrega información nueva.

VIOLACIÓN: Gemini propuso SKEW Tail Risk como "capa V4" sin calcular que ya está
           implícito en 60-86% de las señales existentes.

CONSECUENCIA: Cobertura inflada sin información nueva en el vector de decisión.
```

### Lección 4: N_eff para señales con clustering temporal

```
REGLA:   Señales que disparan en ráfagas (varios pivotes consecutivos)
         requieren N_eff (tamaño de muestra efectivo), no N bruto.
         Block bootstrap corrige por autocorrelación temporal.

VIOLACIÓN: Gemini reportó N=120 donde el N_eff real era ~42.
           CI95 más estrecho de lo correcto → significancia inflada.

CONSECUENCIA: Intervalos de confianza demasiado optimistas.
              Señales parecen más significativas de lo que son.
```

### Lección 5: Prompts conversacionales son vulnerables

```
REGLA:   Prompts en archivo .md con PROHIBIDO explícito > prompts conversacionales.
         La estructura previene complacencia. La conversación la habilita.

VIOLACIÓN: El ejercicio de "aislar caídas no detectadas" se hizo en chat,
           sin estructura de validación, sin criterios de aceptación,
           sin PROHIBIDO explícito.

CONSECUENCIA: Gemini "terminó" cuando creyó que estaba completo.
              No había criterio objetivo de terminación.
```

---

## 7. PLANTILLA ANTI-FRACASO (para no repetirlo)

```
╔══════════════════════════════════════════════════════════════════╗
║           PLANTILLA ANTI-FRACASO — Validación de Señales       ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ANTES DE REPORTAR UNA SEÑAL COMO "DESCUBIERTA":                ║
║                                                                  ║
║  □ 1. Medir en la muestra COMPLETA (1,590 pivotes),             ║
║       no en un subconjunto aislado                               ║
║                                                                  ║
║  □ 2. Bootstrap CI95 (seed fija, n_iter=3000)                   ║
║       → ¿El CI95 cruza cero?                                     ║
║                                                                  ║
║  □ 3. Tasa de activación base                                    ║
║       → ¿Dispara en >50% de los casos? → NO es una señal         ║
║                                                                  ║
║  □ 4. Poder discriminante (Chi² o similar)                       ║
║       → ¿p-value < 0.05? → TIENE poder discriminante             ║
║                                                                  ║
║  □ 5. Matriz de overlap con señales existentes                   ║
║       → ¿Overlap > 60%? → NO agrega información nueva            ║
║                                                                  ║
║  □ 6. N_eff corregido por clustering temporal                    ║
║       → ¿N_eff / N_bruto < 0.5? → inflación significativa        ║
║                                                                  ║
║  □ 7. Distribución completa (P5/P25/P50/P75/P95)                 ║
║       → ¿La cola izquierda es aceptable?                         ║
║                                                                  ║
║  □ 8. Wins/losses separados                                      ║
║       → ¿Asimetría > 1.2×? → señal defensiva, no ofensiva        ║
║                                                                  ║
║  □ 9. Estabilidad por década                                     ║
║       → ¿WR cambia >20pp entre décadas? → no estacionaria        ║
║                                                                  ║
║  SOLO SI TODOS LOS CHECKS PASAN → reportar como descubrimiento   ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 8. ESTADO DEL INCIDENTE

| Campo | Valor |
|-------|-------|
| **Estado** | ✅ CERRADO — fallos documentados, lecciones extraídas |
| **Detección** | Juan Andrés (auditoría manual) + Auditoría interna formal |
| **Corrección** | Reversión de conclusiones de Gemini. Señales invalidadas removidas. |
| **Acción preventiva** | Plantilla anti-fracaso (9 checks). Prompts solo en archivos .md con PROHIBIDO. |
| **Impacto en el sistema** | Ninguno — detectado a tiempo. Las señales inválidas no llegaron a producción. |
| **Costo** | Tiempo perdido: ~4 horas de análisis. Confianza en Gemini: reducida para tareas no estructuradas. |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 20-Ago-2026
**Fuentes:** `regano_formal_equipo.md`, `diagnostico_prompting.md`, `auditoria_ejercicio_exit_signals.md`