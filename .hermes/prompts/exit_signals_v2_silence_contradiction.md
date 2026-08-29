# PROMPT PARA HERMES — Señales EXIT V2: Silencio, Contradicción y Contexto de Tendencia

**Origen:** Sesión Gemini (Opus) 19-Ago-2026 · Auditoría completa del ejercicio de señales EXIT
**Perfil recomendado:** `worker` (deepseek-v4-pro)

---

## 1. ESTADO ACTUAL DEL EJERCICIO

### Lo que ya se midió y validó (NO re-hacer):

| Señal EXIT | N | Edge | WR Bull | CI95 | Veredicto |
|---|---:|---:|---:|---|---|
| `bsi_recovery` | 324 | -1.63% | 29.0% | [-2.17%, -1.10%] | ✅ EXIT Gold Standard |
| `vix_complacency_exit` | 41 | -2.99% | 14.6% | [-3.98%, -1.81%] | ✅ EXIT Grado A |
| `credit_equity_divergence` | 120 | -3.15% | 14.2% | [-4.06%, -2.10%] | 🏆 EXIT Super Señal |
| `defensive_rotation_divergence` | 197 | -2.36% | 31.0% | [-3.20%, -1.50%] | 🏆 EXIT Grado A |
| `sv5t_silent_distribution` | 20 | -2.25% | 30.0% | [-4.05%, -0.39%] | 🏆 EXIT Grado A |
| `stealth_tail_hedging` | 31 | -0.65% | 35.5% | [-2.59%, +1.29%] | ⚠️ Marginal (cruza 0) |
| `credit_ease_exit` | 820 | +0.31% | 50.0% | cruza 0 | ❌ Ruido |
| `breadth_contraction_exit` | 1393 | +0.70% | 53.5% | — | ❌ Trend continuation |
| `regime_change_exit` | 382 | +1.31% | 61.5% | [+0.65%, +1.98%] | ❌ Es ENTRY (Falacia del Pánico) |

### Cobertura del Sistema Protector V2 (Techos detectados):

| Escala | Detectadas | % | No Detectadas |
|---|---:|---:|---:|
| zz25 (≥2.5%) | 486 | 73.4% | 176 |
| zz50 (≥5.0%) | 227 | 69.8% | 98 |
| zz75 (≥7.5%) | 118 | 73.3% | 43 |

---

## 2. HALLAZGO CRÍTICO: CONTEXTO DE TENDENCIA EN TECHOS (19-Ago-2026)

Se midieron las 4 estructuras del ZigZag 2.5% contra el precio real del SPY (33 años):

### Las 4 Estructuras ZigZag y su Comportamiento en Techos

| Estructura | Significado | N | % Caen | Fwd Mean | cascade≥5% | cascade≥7.5% | DD Medio Caídas |
|:---:|---|---:|---:|---:|---:|---:|---:|
| **HH+HL** | Tendencia Alcista | 285 | **90.5%** | -3.32% | **54.7%** | **32.6%** 🔴 | -4.48% |
| **HH+LL** | Divergencia Alcista | 144 | **89.6%** | -3.14% | 53.5% | 22.9% | -4.55% |
| **LH+HL** | Distribución | 141 | **88.7%** | -3.95% | 38.3% | 17.0% | -4.95% |
| **LH+LL** | Tendencia Bajista | 224 | **66.5%** | -2.25% | 54.5% | **30.8%** 🔴 | **-5.49%** |

**CONCLUSIÓN EMPÍRICA CONTRA-INTUITIVA:**
- **HIGHER_HIGH (con tendencia):** 90.2% probabilidad de caída, cascade_75=29.4%. La tendencia alcista NO protege en techos — al contrario, los HH son el **clímax de distribución**.
- **LOWER_HIGH (contra tendencia):** Solo 66.5% de caída, PERO cuando cae, el DD medio es -5.49% (el peor) con worst case -16.94%.
- **Los 132 "falsos techos" (MAX→UP):** El 68.2% son LOWER_HIGHs. Son rebotes en bear markets, no techos en tendencia alcista.

---

## 3. PUNTOS CIEGOS DETECTADOS POR GEMINI (AUDITORÍA)

### 🔴 PC1: `bsi_recovery` dispara en 95 pisos (MIN) — 29% de contaminación
- No filtra por `pivot_type == "MAX"`. El edge -1.63% está diluido por 95 activaciones en MIN donde el mercado sube.
- **ACCIÓN:** Crear `bsi_recovery_max_only` filtrado por MAX y re-medir.

### 🔴 PC2: Cobertura temporal parcial
- `credit_sk`: 100% NaN en 1990s, 57% NaN en 2000s (solo desde ~2007)
- `fg_sk`: 100% NaN en 1990s y 2000s (solo desde ~2011)
- `pcr_sk`, `vvix_sk`: 100% NaN en 1990s
- **ACCIÓN:** Segmentar cobertura: Era Pre-Crédito (1993-2006) vs Era Completa (2007-2026).

### 🔴 PC3: Yield Curve NO medida como señal EXIT
- `yield_curve_sk` tiene solo 0.1% NaN — cubre los 33 años completos.
- Es el predictor de recesiones más probado del mundo.
- **ACCIÓN:** Implementar y medir `yield_curve_inversion_exit`.

### 🟡 PC4: No hay PurgedKFold / DSR para señales EXIT
Los N=120 de `credit_equity_divergence` podrían ser ~15-20 eventos macro independientes.

### 🟡 PC5: No se mide cuánto cae el SPY antes de que la señal se active (detección ≠ acción ejecutable)

---

## 4. CORRECCIONES DE INGENIERÍA EN `medir_senal.py`

### C1: Unificar RNG (INCONSISTENCIA)
```python
# L824, L852 — Cambiar RandomState por default_rng:
# ANTES (legacy):
rng = np.random.RandomState(seed)
# DESPUÉS (moderno, consistente con L463):
rng = np.random.default_rng(seed)
```

### C2: Mover import inline a global
```python
# L923 — Mover a bloque de imports (L22-29):
# ELIMINAR:  import datetime as _dt  (dentro de medir())
# AGREGAR en L22-29:  import datetime as _dt
```

### C3: Eliminar ruta redundante (código muerto)
```python
# L33-35 — ELIMINAR el if (hace lo mismo):
OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"
# if not OBS_PKL.exists():
#     OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"  ← misma ruta
```

---

## 5. TAREAS PENDIENTES (PRIORIDAD)

### Tarea A: Señales EXIT faltantes (implementar + medir)

#### A1. `yield_curve_inversion_exit` — Inversión de curva en techo MAX
```python
@_registrar("yield_curve_inversion_exit",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: Yield curve invertida (D1 negativo) en techo MAX")
def _yield_curve_inversion_exit(df):
    """Yield curve invertida o aplanada en techo MAX — anticipa recesión."""
    is_max = df["pivot_type"] == "MAX"
    yc_sk = df["yield_curve_sk"].dropna()
    d1 = yc_sk.str.split("__").str[0]
    # Los bins de yield_curve con spread negativo o cercano a cero
    cond = d1.isin(["DEEP_INVERSION", "MODERATE_INVERSION", "FLAT_CURVE"])
    mask = is_max & cond.reindex(df.index, fill_value=False)
    return mask
```
**NOTA:** Verificar los nombres exactos de los D1 bins en `yield_curve_fact_store.json` antes de implementar.

#### A2. `bsi_recovery_max_only` — BSI Recovery filtrado SOLO en MAX
```python
@_registrar("bsi_recovery_max_only",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: BSI sale de WASHED_OUT en techo MAX (sin contaminación MIN)")
def _bsi_recovery_max_only(df):
    is_max = df["pivot_type"] == "MAX"
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    mask = bsi_d1.isin(["BREADTH_RECOVERY", "NEUTRAL_HIGH_BREADTH"])
    return is_max & mask.reindex(df.index, fill_value=False)
```

### Tarea B: Segmentar cobertura por era
Medir el Sistema Protector V2 separado en:
- **Era 1993-2006:** Solo VIX + BSI + SKEW + Yield Curve (estaciones con datos completos)
- **Era 2007-2026:** Todas las 11 estaciones

### Tarea C: Incorporar contexto de tendencia (HH/LH) como filtro
Agregar columna `max_trend` (HIGHER_HIGH / LOWER_HIGH) al dataset `quants_obs.pkl` para que las señales EXIT puedan ser filtradas por contexto de tendencia.

---

## 6. SEPARACIÓN CONCEPTUAL: ENTRY vs EXIT

Los ejercicios de ENTRY y EXIT tienen **física mecánica opuesta** y deben tratarse como ejercicios separados:

| Aspecto | PISOS (ENTRY) | TECHOS (EXIT) |
|---|---|---|
| Mecánica | Liquidación violenta, capitulación | Agotamiento silencioso, distribución |
| Tipo de señal | Ruidosa: picos extremos (+2σ, +3σ) | Silencio: ausencia de participación |
| Tendencia | Casi irrelevante (HL=83.9% vs LL=82.8%) | AMPLIFICA peligro (HH=90.5% caen) |
| Error costoso | Comprar tarde (costo de oportunidad) | Salir tarde (drawdown real) |
| Detección | Convergencia de miedo (señales ruidosas) | Contradicción inter-estación (señales silenciosas) |

---

## 7. WORKFLOW OBLIGATORIO: CODE REVIEW → RESULTS AUDIT (2 Etapas)

> **⚠️ REGLA INAMOVIBLE: Hermes NO ejecuta código nuevo sin aprobación previa de Gemini.**

### ETAPA 1: CODE REVIEW (antes de ejecutar)

```
Hermes (worker)                    Gemini (auditor)
──────────────                     ────────────────
1. Escribe el .py completo         
   (señales nuevas, correcciones)  
                                   
2. DETENTE. No ejecutes.           
   Entrega el código en un         
   bloque ```python``` o como      
   archivo .py en el repo.         
                                   3. Gemini revisa:
                                      • ¿Señales EXIT filtran por MAX?
                                      • ¿No hay look-ahead?
                                      • ¿NaN manejados correctamente?
                                      • ¿RNG consistente (default_rng)?
                                      • ¿Clean Architecture respetada?
                                      • ¿Tests existentes siguen pasando?
                                   
                                   4. Gemini responde:
                                      ✅ APROBADO → proceder a Etapa 2
                                      🔴 RECHAZADO → lista de correcciones
```

**Checklist de Code Review (Gemini verifica antes de aprobar):**
- [ ] Todas las señales EXIT incluyen `is_max = df["pivot_type"] == "MAX"` (excepto señales agnósticas documentadas)
- [ ] No hay `import` dentro de funciones
- [ ] `np.random.default_rng(seed)` usado consistentemente (no `RandomState`)
- [ ] Columnas `_sk` accedidas con `.dropna()` antes de `.str.split()`
- [ ] `.reindex(df.index, fill_value=False)` aplicado a masks con NaN
- [ ] Suite de tests: `pytest tests/ -x -q` → 252/252 passed

### ETAPA 2: RESULTS AUDIT (después de ejecutar)

```
Hermes (worker)                    Gemini (auditor)
──────────────                     ────────────────
5. Ejecuta el código aprobado.     
   Genera JSONs de medición.       
   Entrega reporte con tablas      
   de resultados.                  
                                   6. Gemini audita resultados:
                                      • ¿CI95 calculados correctamente?
                                      • ¿Cobertura temporal segmentada?
                                      • ¿Clustering temporal considerado?
                                      • ¿Interpretación consistente con datos?
                                      • ¿Conclusiones no contradicen la física?
                                   
                                   7. Gemini responde:
                                      ✅ VALIDADO → integrar a producción
                                      ⚠️ OBSERVACIONES → ajustar interpretación
                                      🔴 INVALIDADO → descartar o re-diseñar
```

### Comandos de Verificación (Etapa 1)

```bash
# Verificar correcciones de ingeniería
grep -n "RandomState" research/01_señales_entry_exit/medir_senal.py
# Debe dar 0 resultados

# Verificar filtro MAX en señales EXIT
grep -A2 "def _.*exit\|def _.*divergence\|def _.*distribution\|def _.*hedging" research/01_señales_entry_exit/medir_senal.py | grep "pivot_type"

# Tests completos
cd /root/botero-trade && PYTHONPATH=. backend/.venv/bin/python -m pytest tests/ -x -q
```

### Comandos de Medición (Etapa 2, solo después de aprobación)

```bash
PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/01_señales_entry_exit/medir_senal.py --señal yield_curve_inversion_exit
PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/01_señales_entry_exit/medir_senal.py --señal bsi_recovery_max_only
```

---

## PROHIBIDO
- ❌ NO ejecutar código nuevo sin aprobación de Gemini (Etapa 1 obligatoria)
- ❌ NO modificar señales de ENTRY existentes (credit_easing_k1, capitulacion, etc.)
- ❌ NO tocar cascade_conviction ni fact stores
- ❌ NO re-medir señales ya validadas (tabla de Sección 1)
- ❌ NO leer ni modificar archivos .env, .env.local, .mcp.json

---

**Firma:** Gemini (Opus) — Auditoría técnica y empírica
**Fecha:** 19-Ago-2026
**Referencia:** `auditoria_ejercicio_exit_signals.md` (artifact de auditoría completa)
