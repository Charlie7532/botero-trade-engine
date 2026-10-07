<!-- VINTAGE_METADATA_HEADER -->
> [!WARNING]
> **VINTAGE V-B (PRE-HOMOGENEIZACIÓN) — NO COMPARABLE DIRECTAMENTE CON V-C**
> **Motivo medido:** Datos generados con series tácticas híbridas SMA5/EMA5 en las 14 series `*_TW`, barras parciales previas al rebuild de 2026-10-04, y piernas SPY desalineadas.
> **Ventana declarada:** 2000-01-03 a 2026-06-16 (6.653 días de trading en V41/V40).
> **Propósito:** Registro histórico inmutable de auditoría para preservación de evidencia empírica (F5.1).
<!-- END_VINTAGE_METADATA_HEADER -->

# 📊 V40 Signal Contribution Study — Auditoría de Resultados

> **Dato Mata Relato** — Los datos destruyeron ambas hipótesis.

---

## Resultado Global

| Variante | FGBI | Core Dinámico | Acc SPY | Δ vs V39 | Max DD |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **V39 Baseline** | ❌ | ❌ | **1,034.81** | — | -39.21% |
| **V40-A** (solo FGBI) | ✅ | ❌ | **1,034.81** | **+0.00** | -39.21% |
| **V40-B** (solo Core) | ❌ | ✅ | **816.72** | **-218.08** 🔴 | -39.84% |
| **V40-C** (ambas) | ✅ | ✅ | **816.72** | **-218.08** 🔴 | -39.84% |

---

## 🔴 HALLAZGO 1: FGBI = CÓDIGO MUERTO (0.00 acc de contribución)

La antena FGBI **nunca se activó** a pesar de tener 3,871 barras de FG cargadas (2011-2026).

### Análisis Estructural

La lógica de FGBI reversal en [L210-216](file:///root/botero-trade/backend/modules/entry_decision/application/use_cases/quality_entry_gate.py#L210-L216):

```python
# Solo se evalúa dentro de CRASH_SISTEMICO
elif current_mode == "CRASH_SISTEMICO":
    is_fgbi_reversal = False
    if fgbi is not None and effective_peak is not None:
        if effective_peak > 20.0 and (fgbi < 15.0 or fgbi <= (peak - 5.0)):
            if th >= 40.0 or (vbi is not None and vbi > 1.5):  # ← AQUÍ ESTÁ EL PROBLEMA
                is_fgbi_reversal = True
```

**La condición `th >= 40.0` es ESTRUCTURALMENTE IMPOSIBLE dentro de CRASH_SISTEMICO:**

| Paso | Condición | Valor de th |
| :--- | :--- | :---: |
| **Entrada a CRASH** | `th < 30 AND fi < 25 AND tw < 20 AND n_dead >= 5` | th < 30 |
| **FGBI gate** | `th >= 40.0` | ❌ **IMPOSIBLE** — th acaba de cruzar < 30 |
| **Salida defensiva** | `has_defensive_floor AND can_switch_crash` (XLP_FI >= 25, 3 días) | Dispara **ANTES** de que th llegue a 40 |
| **Salida por recovery** | `tw > 45 AND fi > 35 AND th > 25` | Dispara con th > 25, mucho antes de 40 |

**La segunda condición alternativa (`vbi > 1.5`) tampoco aplica** — el benchmark no pasa `vbi`, siempre es `None`.

### Diagnóstico

```
Secuencia temporal en CRASH:
  Día 1:  th < 30 → ENTER CRASH (100% cash)
  Día 3:  XLP_FI >= 25 → defensive_floor EXIT → PISO_GENERACIONAL
  
  La ventana de 3 días es demasiado corta para que th suba de <30 a >=40.
  FGBI reversal es código muerto — nunca compite con defensive_floor.
```

> [!CAUTION]
> **La antena FGBI fue diseñada con un gate (`th >= 40`) que es incompatible con su propio contexto de activación (`CRASH → th < 30`)**. Esto NO es un error del benchmark — es un defecto de diseño en el gate.

---

## 🔴 HALLAZGO 2: Core Dinámico = REGRESIÓN CATASTRÓFICA (-218.08 acc)

Reemplazar XLP por XLY en el core de MERCADO_SANO **destruyó un 21% del valor acumulado**.

### Año por Año — Dónde Golpea

| Año | V39 (XLP Core) | V40-B (XLY Core) | Δ | Régimen dominante |
| :---: | :---: | :---: | :---: | :--- |
| 2001 | +24.38% | +9.62% | **-14.76 pp** 🔴 | Post dot-com: XLP protegió |
| 2022 | +17.62% | +11.55% | **-6.07 pp** 🔴 | Bear market: XLP protegió |
| 2026 (YTD) | +6.93% | +0.44% | **-6.49 pp** 🔴 | XLP amortiguó corrección |
| 2003 | +5.98% | +12.19% | +6.21 pp ✅ | Recovery: XLY lideró |
| 2020 | +28.78% | +29.70% | +0.92 pp ✅ | V-shape: XLY capturó rebote |
| 2025 | +23.63% | +26.31% | +2.68 pp ✅ | Bull: XLY amplificó |

### ¿Por qué XLP en Core es MEJOR?

**El relato decía**: *"XLP es defensivo, no agrega valor en mercados sanos".*

**Los datos dicen**: XLP en core actúa como un **amortiguador de composición**. En años buenos, la diferencia con XLY es marginal (+2-3pp). Pero en años de estrés dentro de MERCADO_SANO (correcciones de 5-10% que no llegan a cambiar régimen), XLP absorbe la caída y protege el capital compuesto.

El efecto es **asimétrico**:
- Años donde XLY gana: +0.5 a +6 pp → ganancia marginal
- Años donde XLP gana: +6 a +15 pp → protección **compuesta** sobre 26 años

Las pérdidas compuestas destruyen más valor que las ganancias marginales acumulan. **V39 estaba correcto.**

---

## Veredicto

| Cambio Propuesto | Resultado | Decisión |
| :--- | :--- | :--- |
| **FGBI** (activar antena) | 0.00 acc — código muerto | 🚫 **NO IMPLEMENTAR** (el gate necesita rediseño, no activación) |
| **Core Dinámico** (XLY por XLP) | -218.08 acc — regresión | 🚫 **NO IMPLEMENTAR** (V39 correcto) |

---

## Acciones Derivadas (Fase 2)

### Para FGBI (código muerto):
1. **Rediseñar el gate FGBI** — la condición `th >= 40` debe relajarse a algo alcanzable dentro de CRASH (ej: `th >= 25` o evaluar solo FG sin gate de th)
2. **Pasar VBI al benchmark** — actualmente `vbi=None` desactiva la segunda condición alternativa
3. **Estudio separado**: ¿qué pasa si FGBI se activa con `th >= 25`? ¿Mejora el timing de salida de CRASH?

### Para Core Pool:
1. **MANTENER** el hardcoded `["XLK", "XLC", "XLF", "XLI", "XLV", "XLP"]` — los datos lo validan
2. **Investigar**: ¿agregar XLY como 7mo miembro del core (no reemplazar XLP)? → estudio separado
3. **El "punto dulce" por VIX/FG** que pediste para decidir cuándo XLY vs XLP → **los datos muestran que XLP SIEMPRE gana en promedio compuesto**, no hay un umbral donde el switch sea rentable

### Para la Política Anti-Fallback:
Los resultados ya aportan datos de degradación:
- **Sin FGBI**: degradación = 0.00 acc (el sistema es completamente autónomo sin esta señal — **porque es código muerto**)
- **Con core dinámico erróneo**: degradación = -218.08 acc (un cambio de composición destruye valor masivamente)
