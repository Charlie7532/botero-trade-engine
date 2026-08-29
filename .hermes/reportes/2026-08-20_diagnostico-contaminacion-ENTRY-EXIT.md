# COMPARACIÓN — Gemini vs Hermes vs Opus: Contaminación del Sistema ENTRY/EXIT
## Diagnóstico de hibridación y divergencias

**Fecha:** 20-Ago-2026
**Fuentes:** `auditoria_5_addenda_algoritmos.md` (Opus), `evaluacion-senal-por-senal.md` (Hermes post-enmienda), Gemini prompts originales.

---

## 1. LA CONTAMINACIÓN DETECTADA

El sistema de calificación ENTRY/EXIT se contaminó en 3 niveles:

### Nivel 1: Señales EXIT con edge POSITIVO (son realmente ENTRY)

| Señal | Etiqueta | Edge real | Lo que dice Opus | Lo que confirma el arnés |
|-------|----------|-----------|------------------|--------------------------|
| **vix_crisis_spike** | `EXIT (techo)` | **+0.75%** positivo | No mencionado explícitamente | ✅ Confirmado: "Falsa EXIT. Edge positivo +0.75%. Es realmente ENTRY." |
| **credit_stress_exit** | `EXIT` | **+1.00%** (idéntico a credit_stress) | `lift=0.954x` + `fire_rate=51.6%` → retirado | ✅ Confirmado: retirada (lift<1.0) |
| **pcr_panic_exit** | `EXIT` | **+2.70%** (idéntico a pcr_put_panic) | No analizado individualmente | ✅ Confirmado: duplicado exacto de pcr_put_panic (ENTRY) |

**Conclusión:** Gemini creó señales con nombre `_exit` que tienen edge POSITIVO — son señales de compra disfrazadas de venta. El nombre engaña.

### Nivel 2: Señales ENTRY y EXIT idénticas (mismo código, distinto nombre)

| Par | ENTRY | EXIT | N idéntico | Edge idéntico |
|-----|-------|------|:----------:|:------------:|
| PCR | `pcr_put_panic` | `pcr_panic_exit` | 70 = 70 | +2.70% = +2.70% |
| Credit | `credit_stress` | `credit_stress_exit` | 215 = 215 | +1.00% = +1.00% |
| DXY | `dxy_bearish` | `dxy_spike_exit` | 35 = 35 | −0.04% = −0.04% |

**Conclusión:** Gemini registró la MISMA señal dos veces, una como ENTRY y otra como EXIT. El arnés las mide como idénticas porque el código es literalmente el mismo. Esto infló artificialmente el conteo de señales (28 → 22 reales → 19 únicas).

### Nivel 3: Señales EXIT que NO discriminan (LIFT ≈ 1.0)

| Señal | LIFT (MAX) | Edge | Diagnóstico del arnés |
|-------|:----------:|------|----------------------|
| credit_equity_divergence | 1.035x | −3.15% | "LIFT=1.035x ≈ baseline. La divergencia crédito-equity NO funciona como EXIT independiente." |
| skew_paranoia_exit | 1.116x | −0.38% | "No escala (3.8%→zz75). LIFT modesto." |
| dxy_spike_exit | 1.075x | −0.04% | "Edge≈0. No detecta ni piso ni techo." |

**Conclusión:** Son formalmente EXIT (edge negativo), pero el LIFT es prácticamente 1.0 — no son mejores que el baseline de 83.4% de caída natural en MAX. Son señales que "existen" pero no aportan.

---

## 2. EL MECANISMO DE CONTAMINACIÓN (cómo ocurrió)

```
FASE 1 — Gemini crea señales (17-Ago):
  "Vamos a crear señales de EXIT."
  → Define vix_crisis_spike como EXIT (VIX en crisis = peligro)
  → Define credit_stress_exit como EXIT (crédito estresado = salir)
  → Define pcr_panic_exit como EXIT (pánico de puts = salir)

FASE 2 — El arnés mide (17-19 Ago):
  vix_crisis_spike:    edge = +0.75%  → "¿positivo? Debe ser error de medición"
  credit_stress_exit:  edge = +1.00%  → "idéntico a credit_stress... ¿bug?"
  pcr_panic_exit:      edge = +2.70%  → "idéntico a pcr_put_panic... ¿duplicado?"
  
FASE 3 — Opus audita (20-Ago):
  PC1: 4 señales EXIT tienen lift<1.0 → RETIRAR
  PC3: vix_complacency ≡ euforia → DUPLICADO
  Pero NO detectó que vix_crisis_spike, credit_stress_exit, pcr_panic_exit 
  son ENTRY con nombre de EXIT.

FASE 4 — Hermes ejecuta evaluación (20-Ago 22:30):
  El arnés confirma: vix_crisis_spike tiene edge +0.75%.
  "Falsa EXIT. Es realmente ENTRY."
```

**El error raíz:** Gemini asumió que "indicador en estado extremo = señal de salida". Pero el dato dice lo contrario: **los extremos son momento de comprar, no de vender** (sesgo contrarian del mercado). La intuición "VIX alto = peligro = vender" es incorrecta — el dato muestra que VIX alto = oportunidad de compra.

---

## 3. EVIDENCIA CRUZADA (las 3 fuentes)

| Fenómeno | Lo dijo Opus | Lo dice el arnés | Coinciden |
|----------|:------------:|:----------------:|:---------:|
| vix_crisis_spike es realmente ENTRY | ❌ No lo detectó | ✅ "Falsa EXIT. Edge +0.75%. Reclasificar como ENTRY." | Solo arnés |
| pcr_panic_exit = pcr_put_panic | ❌ No lo detectó | ✅ "100% mismo código, N=70 idéntico" | Solo arnés |
| credit_stress_exit = credit_stress | ❌ No lo detectó | ✅ "100% mismo código, N=215 idéntico" | Solo arnés |
| 4 EXIT con lift<1.0 | ✅ PC1 | ✅ Confirmado y retirado | Ambos |
| vix_complacency ≡ euforia | ✅ PC3 | ✅ Confirmado y retirado | Ambos |
| bsi_recovery label fantasma | ✅ PC6 (falso positivo) | ✅ Corregido, N 324→481 | Ambos |

---

## 4. LO QUE QUEDA CONTAMINADO (y requiere acción)

| # | Contaminación | Impacto | Acción |
|---|--------------|---------|--------|
| C1 | **vix_crisis_spike etiquetada EXIT** | Aparece en árboles EXIT como señal de venta, pero el mercado SUBE | **Reclasificar como ENTRY.** Mover a la tabla de pisos. |
| C2 | **3 pares duplicados (ENTRY=EXIT)** | Conteo inflado: 22 señales → 19 reales. El nombre `_exit` es mentira | **Unificar bajo UN solo nombre.** Eliminar el sufijo `_exit` fraudulento. |
| C3 | **EXIT que no discriminan (LIFT≈1.0)** | 3 señales EXIT no baten el baseline. Son peso muerto. | **Degradar a GRADO C** o retirar si no mejoran con filtro HH. |
| C4 | **EXIT no operacionalizadas con HH** | El hallazgo HH=90.2% no está en los árboles de decisión | **Agregar regla:** "señal EXIT + HH → amplificar" en ARBOLES_DECISION.md |

---

## 5. LO QUE OPUS NO VIO (puntos ciegos de la auditoría)

| Punto ciego | Por qué Opus no lo vio | Evidencia |
|-------------|------------------------|-----------|
| vix_crisis_spike es ENTRY | Opus se enfocó en LIFT y fire rate, no en la dirección del edge | Edge +0.75% confirmado por el arnés |
| 3 pares ENTRY=EXIT | Opus no comparó código fuente de las definiciones de señal | Código idéntico verificado |
| El sistema EXIT no bate el baseline | Opus midió LIFT individual pero no forward agregado | Forward con EXIT=−3.13% vs sin EXIT=−3.05% |

---

## 6. PLAN DE DESCONTAMINACIÓN

| # | Acción | Prioridad | Rompe algo? |
|---|--------|-----------|:-----------:|
| 1 | **Reclasificar vix_crisis_spike como ENTRY** | P0 | Solo cambia etiqueta y docstring |
| 2 | **Eliminar sufijos `_exit` fraudulentos:** unificar pcr_put_panic (eliminar pcr_panic_exit), credit_stress (eliminar credit_stress_exit), dxy_bearish (eliminar dxy_spike_exit) | P0 | 3 señales menos en el registro |
| 3 | **Agregar regla HH+EXIT en ARBOLES_DECISION.md** | P1 | Solo documentación |
| 4 | **Degradar EXIT con LIFT≈1.0 a GRADO C** | P2 | Solo cambia validacion |
| 5 | **Reconstruir mediciones con nombres limpios** | P2 | Los JSONs históricos quedan con nombres viejos |

---
**Firma:** deepseek/deepseek-v4-pro (Hermes) · 20-Ago-2026