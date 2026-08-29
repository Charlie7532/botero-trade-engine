# LOS FACTORES DE ÉXITO — Cómo llegamos a los descubrimientos fácticos
## Botero Trade — 19-Ago-2026
## La lógica, la información, las ventanas, los rectores

---

## 0. LA PREGUNTA QUE GUIÓ TODO

> **"Dato mata relato."**

No es un eslogan. Es un principio de diseño. Significa:

```
Toda hipótesis → se contrasta contra datos reales → el dato decide.
Si el dato refuta → la hipótesis se descarta, por más intuitiva que fuera.
Si el dato confirma → la hipótesis se documenta con CI95 + N + distribución.
```

Este principio fue el **rector supremo**. Todo lo demás se derivó de él.

---

## 1. LA LÓGICA QUE PERMITIÓ VER TODO ESTO

### 1.1 De "¿qué creo que pasa?" a "¿qué dicen los datos?"

```
ENFOQUE TRADICIONAL (que evitamos):
  1. Formular hipótesis basada en intuición
  2. Buscar datos que la confirmen
  3. Publicar la media del retorno forward
  → Resultado: sesgo de confirmación, overfitting, medias que esconden colas

NUESTRO ENFOQUE:
  1. Formular hipótesis basada en la estructura del mercado (METAR)
  2. Medir CONTRA los datos, no A FAVOR de los datos
  3. Reportar distribución completa (P5/P95), no solo media
  4. Si el dato refuta → la hipótesis se descarta INMEDIATAMENTE
  → Resultado: descubrimientos fácticos, no narrativas
```

**Ejemplo concreto:** La hipótesis de "vender euforia"
```
Intuición inicial:   "Cuando el mercado está eufórico, hay que vender"
Medición (17-Ago):   euforia → forward = -2.99%, WR = 14.6%
Dato:                 Efectivamente, la señal de techo funciona
Lo que NO asumimos:   Que "funciona" significa "siempre funciona"
Lo que SÍ medimos:    WR por década: 10% (1990s) → 29% (2000s) → 6% (2010s)
                      → La señal es consistentemente bajista, pero ruidosa
```

### 1.2 El vector de estado como lente universal

```
¿QUÉ OBSERVAMOS?
No observamos "el precio". No observamos "el retorno".
Observamos el VECTOR DE ESTADO de 11 estaciones meteorológicas.

Cada estación tiene 3 dimensiones:
  D1 (NIVEL):      ¿en qué estado está?    → CRISIS_SPIKE, DEEP_COMPLACENCY...
  D2 (VELOCIDAD):  ¿hacia dónde va?        → ACCELERATING_UP, FAST_CRUSH...
  D3 (VOLATILIDAD): ¿qué tan inestable es? → VOL_EXPANDING, VOL_COMPRESSING...

Esto produce 11 × ~150 estados = ~1,650 estados posibles del mercado.

La PREGUNTA no es "¿subió o bajó el SPY?"
La PREGUNTA es "¿en qué CONFIGURACIÓN de estados está el sistema?"
```

**Por qué esto es poderoso:**
```
En lugar de predecir "SPY va a subir 2%", predecimos:
"Cuando VIX está en CRISIS_SPIKE (D1) con velocidad DECELERATING (D2)
 y volatilidad COMPRESSING (D3), y además CREDIT está en STRESS (D1)
 con velocidad ACCELERATING (D2)..."

Esto es RICO en información. Cada estado adicional REDUCE la incertidumbre.
No es "el mercado sube" — es "el mercado sube PORQUE está en esta configuración".
```

---

## 2. CÓMO EMPLEAMOS LA INFORMACIÓN

### 2.1 El flujo de enriquecimiento

```
NIVEL 1 — DATOS CRUDOS:
  Vault PostgreSQL → OHLCV diario de SPY, VIX, VVIX, PCR, FG, SKEW, CREDIT, YIELD, DXY, BSI, SV5T, ROTATION

NIVEL 2 — CLASIFICACIÓN (fact stores):
  Datos crudos → D1×D2×D3 → state_key → {n, p_bull, ev_net, ev_per_day, ftt, e_days, ...}
  Cada estado tiene su propia distribución de retornos futuros (la tríada zigzag)

NIVEL 3 — AGREGACIÓN (quants_obs.pkl):
  1,590 pivotes zz25 del SPY × 141 columnas:
  - State keys de las 11 estaciones en cada pivote
  - Cascade_50/75 (¿la pierna se propagó?)
  - prev_leg_return (retorno de la pierna completa)
  - duration_bars (duración de la pierna)

NIVEL 4 — MEDICIÓN (medir_senal.py):
  Para cada señal registrada:
  - Distribución completa de retornos forward
  - Edge ofensivo + defensivo
  - Tríada zigzag (zz25/zz50/zz75)
  - Anticipación temporal + capture ratio + puntería

NIVEL 5 — FORENSE (forense_precursores.py):
  Para cada señal × cada estado del vector:
  - LIFT = P(estado | CRASH) / P(estado | NO CRASH)
  - Precursores universales (cross-señal)
  - Protectores (estados que NUNCA crashean)
```

### 2.2 La regla de enriquecimiento: cada nivel agrega, nunca reemplaza

```
ERROR COMÚN:   "Reemplacemos los datos crudos por un modelo predictivo"
               → Se pierde la trazabilidad. No sabes POR QUÉ el modelo decidió.

NUESTRA REGLA: Cada nivel AGREGA información al nivel anterior.
               El state_key (N2) enriquece el dato crudo (N1).
               El quants_obs (N3) enriquece los fact stores (N2).
               La medición (N4) enriquece el quants_obs (N3).
               El forense (N5) enriquece la medición (N4).

               Nunca se reemplaza. Siempre se agrega.
               Siempre se puede trazar: ¿por qué este pivote dio este resultado?
               → Porque el state_key era X, que venía del dato crudo Y.
```

---

## 3. CÓMO DETERMINAMOS LAS VENTANAS DE DETECCIÓN

### 3.1 El problema de la ventana temporal

```
PREGUNTA: ¿Cuánto tiempo ANTES de un crash debemos buscar señales?

OPCIÓN A: Ventana fija (ej: 20 días antes)
  → Arbitrario. Un crash puede gestarse en 5 días o en 6 meses.

OPCIÓN B: Ventana por escala zigzag
  → zz25 (2.5%): buscar 3-5 días antes (retracción)
  → zz50 (5.0%): buscar 10-20 días antes (corrección)
  → zz75 (7.5%): buscar 30-60 días antes (depresión)

OPCIÓN C (LA QUE ELEGIMOS): Lookback [T0-3, T0+2] para TODAS las escalas
  → Misma ventana diaria alrededor del pivote
  → La diferencia entre escalas está en LOS PIVOTES analizados
  → Un crash zz25 es un pivote con caída de 2.5%
  → Un crash zz50 es un pivote con caída de 5.0% que además cascadeó
```

### 3.2 Cómo llegamos a [T0-3, T0+2]

```
RAZONAMIENTO:
  1. El pivote zigzag es el punto de inflexión CONFIRMADO
  2. Las señales del vector de estado se activan CERCA del pivote
     (la anticipación media de bsi_washed_out es 70 días, pero la mediana es 2)
  3. Una ventana de [-3, +2] días alrededor del pivote captura:
     - Señales que se activaron JUSTO ANTES del crash (T0-3)
     - Señales que se confirmaron JUSTO DESPUÉS del crash (T0+2)
  4. Ventanas más largas capturan ruido
  5. Ventanas más cortas pierden la señal

VALIDACIÓN EMPÍRICA:
  credit_easing_k1 en caídas zz50:
    - 60% de las caídas fueron precedidas por sorpresa_total
    - 60% de las caídas fueron precedidas por sub_reaccion
    - Esto NO se habría detectado con ventanas más cortas o más largas
```

### 3.3 La anticipación temporal (el Bug 1 que corregimos)

```
ERROR INICIAL (Bug 1):
  Medíamos "anticipación" como % de señales activas en el pivote ANTERIOR
  → Esto mide autocorrelación entre pivotes, NO anticipación temporal

CORRECCIÓN:
  Medimos "anticipación" como DÍAS entre la fecha del pivote y
  la fecha del pivote anterior donde la señal también estaba activa
  → Esto mide cuántos DÍAS antes se anticipó la señal

RESULTADO (bsi_washed_out):
  Antes (bug):   "66.5% se adelantan 1 pivote" (sin sentido temporal)
  Ahora (fix):   "media=70.4 días, mediana=2.0 días, 72% con anticipación > 0"
  → La mediana de 2 días confirma que la señal se activa MUY cerca del pivote
  → La media de 70 días revela que hay una cola larga de señales muy anticipadas
```

---

## 4. CÓMO EVALUAMOS LOS REPORTES

### 4.1 El framework de evaluación

```
TODO REPORTE (de Gemini, Claude, analista) se evalúa contra 5 criterios:

1. ¿CITA DATOS?         → Si no tiene N + CI95 + distribución → RECHAZADO
2. ¿VERIFICA?           → Si no se puede replicar con medir_senal.py → RECHAZADO
3. ¿RESPETA EL SCOPE?   → Si modificó archivos no autorizados → RECHAZADO
4. ¿ES PROBABILÍSTICO?  → Si usa lenguaje absoluto ("se queda/se va") → RECHAZADO
5. ¿DOCUMENTA FALLOS?   → Si solo muestra lo que funciona → SOSPECHOSO
```

### 4.2 Ejemplo de evaluación real: Reporte de Gemini B1

```
CRITERIO 1 (CITA DATOS):    ✅ "cascade_50 +0.4147, degradación +0.20%"
CRITERIO 2 (VERIFICA):      ✅ decay_check_cascade_conviction.py confirma
CRITERIO 3 (SCOPE):         ❌ VIOLACIÓN MASIVA (~400 líneas adicionales)
CRITERIO 4 (PROBABILÍSTICO): ✅ "SIGNAL HEALTHY"
CRITERIO 5 (FALLOS):        ❌ No documentó el scope creep

VEREDICTO: RECHAZADO (criterio 3). Re-prompt con PROHIBIDO más estricto.
```

### 4.3 El principio de verificación cruzada

```
NUNCA aceptamos un hallazgo de UN solo agente sin verificarlo:

  1. Gemini/Claude reporta un hallazgo
  2. Hermes verifica contra el código fuente real
  3. Hermes ejecuta el script relevante para confirmar
  4. Solo si coincide → se acepta

CASO CONCRETO (Bug 2 de Capture Ratio):
  Claude reportó:  "Capture Ratio tiene semántica invertida"
  Hermes verificó:  El código ya usa np.abs() → NO EXISTE EL BUG
  Veredicto:        Falso positivo del auditor. No se corrige.
```

---

## 5. LOS RECTORES (principios que gobernaron todo)

### Rector 1: Dato mata relato

```
"Toda afirmación con CI95 + N + distribución. Sin eso, es narrativa."
```

**Cómo se aplicó:**
- Cada señal medida con distribución completa (P5/P95), no solo media
- Cada afirmación con bootstrap CI95 (3000 iteraciones, seed 42)
- Cada precursor con N_lose documentado
- "Vender euforia" → refutado por datos (FG euphoria no tiene celdas D2×D3 negativas)

### Rector 2: Rareza = Riqueza

```
"Los eventos con N bajo no son ruido. Son los más valiosos."
```

**Cómo se aplicó:**
- El analista inicial filtró N_lose < 5 como "artefacto"
- El usuario corrigió: "eso los hace más valiosos, como los diamantes"
- Reclasificación: 93% de precursores son eventos raros (N_lose 3-9)
- Solo 7% tienen estadística frecuentista confiable (N_lose ≥ 10)

### Rector 3: La tríada zigzag es la métrica

```
"No medir con horizontes fijos en días. Medir con la estructura natural del mercado."
```

**Cómo se aplicó:**
- Eliminación de `--horizontes 5,10,20,60` del arnés
- Toda medición contra zz25 (retracción), zz50 (corrección), zz75 (depresión)
- Cascade_50/75 como métrica de propagación
- Duración en barras como métrica de tiempo natural

### Rector 4: Separación de roles

```
"El implementador NO audita su propio código."
```

**Cómo se aplicó:**
- Hermes escribe código → Claude/Gemini auditan → Hermes verifica
- 5 bugs encontrados en código que Hermes escribió
- Ninguno fue encontrado por quien lo escribió
- La separación de roles ES el multiplicador de calidad

### Rector 5: Scope creep → rechazo inmediato

```
"Si el prompt decía '1 línea' y el diff tiene 400, se rechaza todo."
```

**Cómo se aplicó:**
- Gemini B1 fix: 1 línea solicitada → 400 líneas entregadas → RECHAZADO
- Gemini reorganización: "no eliminar archivos" → archivos eliminados → RECHAZADO (luego corregido por el usuario)
- El costo de aceptar scope creep es MAYOR que el de re-empezar

### Rector 6: PROHIBIDO explícito

```
"Cada prompt a un LLM debe listar exactamente qué NO tocar."
```

**Cómo se aplicó:**
- Sección PROHIBIDO en cada prompt a Gemini/Claude
- Lista de archivos, funciones, columnas que NO modificar
- Sin esta sección, los LLM exceden el scope consistentemente

---

## 6. LA ARQUITECTURA DE INFORMACIÓN QUE LO HIZO POSIBLE

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FLUJO DE INFORMACIÓN                             │
│                                                                     │
│  VAULT (PostgreSQL)                                                 │
│  ├── OHLCV diario (SPY, VIX, VVIX, PCR, FG, SKEW, CREDIT, ...)    │
│  └── Zigzag pivots (zz25, zz50, zz75)                              │
│           ↓                                                         │
│  FACT STORES (JSON)                                                 │
│  ├── 11 estaciones × ~150 estados cada una                          │
│  ├── D1×D2×D3 → state_key → {n, p_bull, ev_net, ev_per_day, ...} │
│  └── Tríada zigzag por estado (zz25/zz50/zz75)                     │
│           ↓                                                         │
│  quants_obs.pkl (DataFrame)                                         │
│  ├── 1,590 pivotes × 141 columnas                                  │
│  ├── {station}_sk (state_key) para cada estación                   │
│  ├── cascade_50, cascade_75, prev_leg_return, duration_bars        │
│  └── Punto de entrada ÚNICO para todo análisis                     │
│           ↓                                                         │
│  medir_senal.py (ARNÉS DE MEDICIÓN)                                 │
│  ├── 20 señales registradas con @_registrar                        │
│  ├── Distribución completa, ED, tríada, anticipación, puntería     │
│  └── 20 JSONs de medición en data/research/signals/                │
│           ↓                                                         │
│  forense_precursores.py (FORENSE)                                   │
│  ├── LIFT por estado del vector (D1, D2, D3, D1×D2)               │
│  ├── 86 precursores, protectores, universales                      │
│  └── Validación cruzada implícita (cross-señal)                    │
│           ↓                                                         │
│  analisis_estadistico_profundo.md (SÍNTESIS)                        │
│  ├── Edge Defensivo Graduado                                       │
│  ├── Graduated Response por señal                                   │
│  └── 8 puntos ciegos documentados                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. LO QUE APRENDIMOS SOBRE CÓMO APRENDER

### 7.1 La observación correcta

```
No observamos "el mercado". Observamos CONFIGURACIONES del mercado.

  ❌ "El SPY subió 2%"
  ✅ "El SPY subió 2% mientras VIX estaba en CRISIS_SPIKE (D1),
      con velocidad DECELERATING (D2), volatilidad COMPRESSING (D3),
      y CREDIT en STRESS (D1) con velocidad ACCELERATING (D2)"

La segunda observación es RICA. La primera es POBRE.
La riqueza de la observación DETERMINA la calidad del descubrimiento.
```

### 7.2 La pregunta correcta

```
No preguntamos "¿qué va a pasar?"
Preguntamos "¿qué PASÓ las otras veces que estuvimos en esta configuración?"

  ❌ "¿SPY va a subir mañana?"
  ✅ "De las 54 veces que FG estuvo en EXTREME_FEAR (D1) con velocidad
      DECELERATING (D2), ¿cuántas veces el SPY subió en los siguientes 20 días?
      ¿Cuál fue la distribución de retornos? ¿El P5? ¿El P95?"

La primera pregunta es adivinación.
La segunda pregunta es medición de un patrón histórico.
```

### 7.3 La verificación correcta

```
No aceptamos "parece que funciona".
Exigimos "funciona con CI95 que no cruza cero, N documentado,
           distribución completa, estable por década,
           y verificado por un auditor externo".

  ❌ "credit_easing_k1 tiene buen edge"
  ✅ "credit_easing_k1: N=112, mean=+5.19%, WR=93.8%,
      CI95=[+4.41%, +6.01%], estable en 3 décadas (89%→100%→94%),
      verificado por Claude Opus y Hermes contra código real"
```

---

## 8. LOS 7 FACTORES DE ÉXITO (síntesis final)

| # | Factor | Sin esto, ¿qué habría pasado? |
|---|---|---|
| **1** | **Dato mata relato** como rector supremo | Habríamos aceptado narrativas sin verificar |
| **2** | **Vector de estado** como lente de observación | Habríamos visto "sube/baja" en vez de configuraciones |
| **3** | **LIFT como métrica** para eventos raros | No habríamos encontrado nada con N=3 |
| **4** | **Separación de roles** (implementador ≠ auditor) | No habríamos encontrado 5 bugs en nuestro propio código |
| **5** | **Tríada zigzag** como métrica natural | Habríamos impuesto horizontes fijos arbitrarios |
| **6** | **Enriquecimiento por capas** (nunca reemplazar) | Habríamos perdido trazabilidad |
| **7** | **Verificación cruzada** de todo hallazgo | Habríamos aceptado falsos positivos del auditor |

---

## 9. LA LECCIÓN DEFINITIVA

> **"No necesitamos predecir el futuro. Necesitamos medir el pasado con tanta precisión que el futuro sea una repetición reconocible de un patrón ya documentado."**

No somos adivinos. Somos **cartógrafos de configuraciones del mercado.** Documentamos qué pasó cada vez que el sistema estuvo en un estado particular, con qué distribución de retornos, con qué probabilidad de cascade, con qué drawdown máximo. Cuando el sistema vuelve a ese estado, no "predecimos" — **reconocemos un patrón ya medido.**

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 19-Ago-2026