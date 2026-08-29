# CRONOLOGÍA DEL HILO — Auditoría de Código Python
## Botero Trade — 17 al 19 de Agosto 2026
## Lo que fuimos trabajando y descubriendo, día por día

---

# DÍA 1 — MIÉRCOLES 17 DE AGOSTO 2026

---

## MAÑANA (08:00 — 12:00)

### 📋 08:00 — INICIO: Rescate del hilo de setup
**Contexto:** El usuario pide rescatar todos los hallazgos del hilo de setup de Slack. Hay un historial de agentes despachados con definiciones fragmentadas.

**Acción:** 
- Búsqueda en session_search → 0 resultados
- Rescate vía sqlite a `/root/.hermes/state.db` y lectura de `.hermes/plans/`

**Descubrimiento:** El error de diseño fue despachar agentes sin una especificación congelada. Cada agente recibió un fragmento distinto.

**Decisión:** Crear `especificacion_sistema_bitacora.md` como documento ÚNICO que todo agente reciba.

---

### 🔬 09:00 — Auditoría de artefactos de Antigravity
**Lectura de:** `audit_especificacion_bitacora.md` y `puntos_ciegos_spec.md` de Gemini.

**Descubrimiento B1:** `convergence_compositor.py:540` — N=0 vota con plena convicción.

**Verificación contra código:** 
- L172: `reliability_factor` existe
- L183: `rarity_amplifier` existe
- Pero solo se aplican a Canal 1 (EV) y Canal 2 (Rareza), NO al Canal 3 (D1 vote)

**Otros hallazgos de la auditoría:**
- A1: "activación" de categoría sin definición operativa 🔴
- A2: 22 bins D1 neutrales mudos = 70% del tiempo ciego 🟠
- A3: VIX/VVIX y CREDIT/YIELD comparten inputs → votos duplicados 🟠

---

### 🔧 09:30 — Ciclo B1 completo (4 fases)

**Fase 1 — Prompt #1 a Gemini:**
Fix de 1 línea: `vote = d1_directional_vote(state_key) * rf`

**Fase 2 — Auditoría #1:**
Fix corregido (cascade_50 +0.4147) PERO violación masiva de scope:
- ~400 líneas adicionales (TAFEntry, TAFComposite, DirectionalStateVector)
- VIX×SV5T, S5×SV5, intermarket_mechanics
- Reestructuración de loops
- **Rechazado. Scope creep.**

**Fase 3 — Respuesta a "¿el cambio está en un JSON?":**
NO. Gemini tocó 1 solo archivo (`convergence_compositor.py`). Los JSONs del git status eran del decay check propio y del retrain de SKEW.

**Fase 4 — Prompt #2 (revert + fix mínimo):**
Revertir TODO el scope creep, dejar SOLO B1 (2 cambios: `int→float` + `* rf`).

**Auditoría #2:** 
- Diff limpia de 18 líneas, solo B1
- Cascade sano: **+0.4087** (degradación +1.64%, umbral 10%)
- **SIGNAL HEALTHY**

---

### 🔍 09:45 — Defecto residual B1 (L366)
**Hallazgo:** `n_samp = metar.get("n_samples", 100) or 100` — el `or 100` anula el fix para N=0.

**Raíz del error:** Python: `0 or 100 == 100` (0 es falsy) → `reliability_factor(100)=1.0` → voto pleno.

**Micro-fix:** `or 100` → `or 0`. Entregado a Gemini. No verificado.

---

### 📊 10:00 — LEAVE-ONE-OUT del canal EV (subagente deleg_12f68712)

**Script:** `scratch/ev_station_leave_one_out.py`

**Resultados:**
```
BSI:            +0.0420  (44.3% del aporte positivo)  ← 🚂 locomotora
YIELD_CURVE:    +0.0203  (21.4%, p≤0=0.7%, CI95 sig)  ← APORTA a zz25
SV5_TURBULENCE: +0.0122  (12.9%)
VVIX:           +0.0082  (8.6%)
VIX:            +0.0050  (5.3%)
DXY:            +0.0039  corto / +0.0150 largo zz75    ← APORTA
PCR:            −0.0008  (peso muerto débil)
CREDIT:         −0.0031  (peso muerto débil)
FG:             −0.0089  (peso muerto)
```

**Nota técnica:** Columnas `{station}_n` del pkl rotas (todo 0).

---

### 📊 11:00 — LEAVE-ONE-OUT del cascade (subagente)

**Resultados:**
```
VIX:      +0.1147  [CI95 +0.088, +0.140]  p=0  ← locomotora
BSI:      +0.0059  ns
FG:       +0.0044  ns
CREDIT:   −0.0020  (peso muerto débil)
ROTATION: −0.0124  [CI95 −0.028, +0.004]  ← "resta" in-sample
```

**Por pivot_type:** 
- MIN (n=795): vix +0.116, rotation −0.016
- MAX (n=795): vix +0.116, bsi −0.004, fg Δ=0 (nunca se usa en MAX)

---

### 📊 11:30 — ADD-ONE-IN del cascade (subagente)
```
Base:                +0.4147
+YIELD_CURVE:         +0.3964  (Δ −0.0183 sig)  ← DEGRADA
+DXY:                 +0.4100  (Δ −0.0047 ns)
+ambas:               +0.3939  (Δ −0.0209 sig)  ← DEGRADA
```

**Resolución del enigma:** YIELD_CURVE/DXY tienen valor de MAGNITUD (EV), no de dirección. Son casi ortogonales al voto D1. Arquitectura actual correcta.

---

## TARDE (12:00 — 18:00)

### 🔬 13:00 — P0: Regenerar quants_obs.pkl (subagente)

**Problema:** Columnas `{station}_n` rotas (todo 0), 6 state_keys SKEW obsoletos.

**Solución:** Script de cirugía mínima. Respaldo `.bak`. Verificación por checksum.

**Resultado:** ✅ 1,590 filas intactas, SKEW arreglado, N poblado desde fact stores.

---

### 🔬 14:00 — P2: Test adelantado de distorsión (subagente)

**Hipótesis:** Sorpresa de Shannon = −log2(N_estado/N_total) predice SPY forward.

**Resultado:** Señal REAL pero MODESTA (ρ ≤ 0.15). CAT2 (miedo) es la locomotora.

**Inversión clave:** Mi hipótesis era "CAT2→momentum" pero el dato dice lo CONTRARIO: es REVERSIÓN alcista ("comprar miedo"), no momentum.

**Veredicto anti-adulación:** El efecto es pequeño. Bajo no-solapado, solo fwd_10d sobrevive marginalmente. "Condimento, no plato principal."

---

### 🧪 15:00 — Test retrospectivo de distorsión (subagente)

**Resultado:** SIN ALPHA. La "reversión" aparente es estructura del zigzag (pivot_type determinista: MIN rebota 87%, MAX cae 95%).

**Veredicto:** La versión retrospectiva queda descartada. La adelantada D(t) es la que importa.

---

### 📐 16:00 — Diseño del vector de sorpresa adelantado D(t)

**Fórmula:** `surprise_i = −log2(N_estado/N_total)` por estación.

**Interpretación por categoría:**
- CAT1 raro = cambio de régimen (re-calibrar)
- CAT2 raro = miedo (momentum → corregido a "reversión alcista")
- CAT3 raro = flujo forzado (reversión en agotamiento)

---

### 📊 16:30 — Walk-forward del cascade reducido (subagente) ⚡

**Pregunta:** ¿La reducción del Grupo A (VIX+BSI) sobrevive OOS?

**Resultado:** ❌ NO sobrevive.

| Config | IS | OOS | Δ OOS vs A |
|--------|------|------|------------|
| A (5 est) | +0.4147 | **+0.3189** | — |
| B (vix+bsi) | +0.4324 | +0.3071 | **−0.0118** |
| E (sin rotation) | +0.4142 | **+0.3046** | **−0.0143** |

**Firma clásica de overfitting:** IS mejora, OOS degrada, gap se ensancha.

**Decisión:** ❌ NO tocar el cascade. Las 5 estaciones actuales son óptimas OOS.

**Lección:** ROTATION "no restaba" — estaba aportando OOS. LOO = diagnóstico, no receta.

---

### 😤 17:00 — El usuario nos corrige (crítica fundamental)

**"Tengo muchas preguntas y dudas, mediciones con supuestos de días, pero no evaluaron el riesgo o drawdown de comprar temprano o tarde... afirmaciones absolutas, cuando sé que no todo es 100%... simples observaciones."**

**Nuestra respuesta:** Construir un arnés de medición estándar (medir_senal.py) que codifica:
1. Distribución COMPLETA (P5/P95), no solo media
2. MAE intra-trade real (desde el Vault)
3. Costo de comprar tarde (por trade)
4. Sensibilidad al timing (±k barras)
5. Lenguaje PROBABILÍSTICO (no absolutos)

---

### 🤖 17:30 — Decisión: Código determinista, no agentes

**Usuario:** "¿Será que podemos crear un código que corra en la terminal local y no necesite agentes, que sea matemática pura y dura?"

**Implementación:** `medir_senal.py` (312 líneas iniciales).

---

### 🐛 18:00 — Gemini audita medir_senal.py

**4 bugs encontrados:**
- Bug 1: `_costo_tarde` — primer trade / suma 30 años (roto)
- Bug 2: `_drawdown_temprano` — cumsum 20 barras, no MAE real
- Bug 3: `_sensibilidad_timing` — shift sobre pivotes MIN/MAX alternantes
- Bug 4: `delta_media` — baseline no homogéneo

**Corrección:** Prompt a Gemini → corrige los 4 + mejoras.

**Verificación:** credit_easing_k1 edge intacto (+5.19%, WR 93.75%, N=112).

---

### 🔍 19:00 — El arnés usa d1_vote binario, no state_key

**Usuario:** "Las dimensiones D1, D2 y D3 fueron consideradas, el vector de estado fue analizado completo?"

**Error detectado:** Las señales en medir_senal.py usan `{station}_d1_vote == -1` (binario) en vez del state_key completo (D1×D2×D3).

**Corrección:** Prompt a Gemini → reemplazar `d1_vote` por `str.split("__").str[0]`.

---

### 📊 20:00 — 11 señales registradas con State Key completo

**Señal bsi_washed_out medida con medición triádica:**
```
Tríada zz25:  mean=+1.42%  WR=65.8%
Cascade zz50: 77.0%  (Δ +29.4pp)
Cascade zz75: 60.9%  (Δ +37.9pp)
Duración: 3.3 barras (mediana 1.0)
```

---

### 🔬 21:00 — Claude Opus audita y encuentra puntos ciegos

**4 puntos ciegos:**
1. Sign flips D2/D3 sin bootstrap CI → solo 1/4 pasa
2. Estabilidad por década → capitulacion colapsando (+1.32% → +0.12%)
3. Cross-signal overlap → solo `capitulacion + vvix_entry` es aditivo
4. `duration_bars` como filtro → credit_stress con pierna ≤2b = CERO edge

**Corrección:** Prompt a Claude → implementa los 4 fixes.

---

### 📐 22:00 — Lookback crash implementado

**Nueva sección 4.12 en medir_senal.py:** 
Ventana [T0-3, T0+2] alrededor de cada pivote de caída → qué señales estaban activas.

**Ejemplo credit_easing_k1:** En caídas zz50, 60% precedidas por sorpresa_total y sub_reaccion.

---

### 📊 23:00 — FORENSE completo ejecutado

**86 precursores encontrados.** 61.6% con N_lose 3-4 (rareza = riqueza).

**Precursor universal #1:** `credit.D2=ACCELERATING_UP_3D` en 5/6 señales.

**Esto cierra el Día 1.**

---

# DÍA 2 — JUEVES 18 DE AGOSTO 2026

---

## MAÑANA (00:00 — 08:00)

### 📊 00:00 — Análisis estadístico profundo (analista qwen3.8-max)

**Integración de 7 reportes Claude + 1 analista previo.**

**Resultado final (579 líneas, 12 secciones):**
- Edge Defensivo Graduado (ED por zz25/zz50/zz75)
- Graduated Response por señal
- 12 señales en tabla final integrada
- 8 puntos ciegos que NINGÚN reporte cubrió

---

### 🔄 02:00 — Corrección: Rareza=Riqueza

**El usuario corrige al analista:** "Eso lo hace extremadamente raro y como los diamantes, más escasos, más valiosos!!!"

**Re-análisis del analista:**
- 61.6% de precursores (N_lose 3-4) = MÁS VALIOSOS (antes "artefacto")
- Solo 7% N_lose ≥ 10 = estadística confiable
- Solo N_lose < 3 = anécdota

---

### 📐 03:00 — Marco corregido: Edge Defensivo

**El usuario redefine el marco:** "No es 'cuánto gano filtrando' sino 'cuánto dejo de perder retirándome a tiempo.'"

**Re-análisis del analista (qwen3.8-max) con el nuevo marco:**

| Señal | ED₂₅ | ×Base | Perfil |
|-------|------|-------|--------|
| 🥇 capitulacion | **6.86%** | **3.6×** | 🛡️ Defensiva pura |
| 🥈 fg_extreme_fear | **5.61%** | **2.9×** | 🛡️ Infravalorada |
| 🥉 bsi_washed_out | **5.58%** | **3.1×** | 🛡️⚔️ Híbrida |
| 4 credit_easing_k1 | 5.29% | 1.2× | ⚔️ Ofensiva pura |

**Hallazgo:** Las 2 mejores defensas del sistema estaban INVISIBILIZADAS por el marco ofensivo.

---

## TARDE (08:00 — 18:00)

### 🐛 10:00 — Auditoría de bugs en medir_senal.py

**Reviewer (qwen3.8-max) confirma:**
- Bug 1: Anticipación Temporal → CONFIRMADO (mide autocorrelación, no días)
- Bug 2: Capture Ratio → NO EXISTE (código ya usa `abs()`)

**QA (glm-5.2) diseña tests:**
- 5 casos de prueba para anticipación temporal
- `test_anticipacion_temporal.py` creado

**Implementación de corrección:**
- Reemplazo líneas 507-529 de medir_senal.py
- Tests 5/5 pasan

**Analista verifica:**
- 88/88 métricas idénticas antes/después
- Solo `anticipacion_zigzag` cambió
- **Fix aislado, sin side effects**

---

### 📁 11:00 — Reorganización de archivos (Gemini)

**Movidos de scratch/ a docs/research/ (taxonomía Clean):**
- `docs/research/01_señales_entry_exit/` — 4 .md + 20 JSONs
- `backend/references/README.md` — índice maestro
- `backend/modules/entry_decision/references/señales-exit.md`
- `backend/modules/entry_decision/references/cascade-conviction.md`

**Auditoría inicial de Hermes:** Gemini violó restricciones (eliminó archivos).

**Corrección del usuario:** "Cumpliendo la metodología Clean, fueron relocalizados en carpetas ordenadas"

**Veredicto corregido:** Gemini actuó correctamente. Los archivos de análisis ahora están donde deben estar según Clean Architecture.

---

### 🔍 12:00 — Análisis de señales de EXIT

**Problema identificado:** 11 ENTRY vs solo 2 EXIT (euforia, fg_extreme_greed).

**7 señales de EXIT evaluadas:**

| Señal | Edge | WR | Veredicto |
|-------|------|-----|-----------|
| bsi_recovery | **-1.63%** | 29.0% | ✅ EFECTIVA |
| euforia | **-2.99%** | 14.6% | ✅ EFECTIVA |
| vix_crisis_spike | +0.75% | 56.7% | ❌ Es ENTRY |
| credit_stress_exit | +1.00% | 54.9% | ❌ Es ENTRY |
| pcr_panic_exit | +2.70% | 71.4% | ❌ Es ENTRY |

**Descubrimiento:** Las señales de "pánico" son ENTRY (comprar miedo), no EXIT.

---

### 📐 13:00 — Replanteamiento de EXIT

**Nuevas 4 señales de EXIT propuestas:**
1. vix_complacency_exit — VIX en DEEP_COMPLACENCY/LOW_VOL
2. credit_ease_exit — CREDIT sale de easing
3. breadth_contraction_exit — BSI sale de expansión
4. regime_change_exit — Cambio VERANO → INVIERNO

**Estado:** Prompts creados, pendientes de implementar.

---

### 🔄 14:00 — Cambio de modelo

**Usuario:** `/model deepseek/deepseek-v4-flash --global`

**Hermes corrige:** `hermes config set model.default deepseek/deepseek-v4-flash`

---

### 🔄 16:00 — Cambio a deepseek-v4-pro

**Usuario:** "Si, definitivamente! y forzalo para que quede global"

**Ejecutado:** `hermes config set model.default deepseek/deepseek-v4-pro`

---

### 📁 17:00 — Mapeo de Graphify

**Grafo:** 14,030 nodos, 23,828 edges, 924 comunidades, 1,625 archivos indexados.

**Nota:** Graphify no indexa archivos nuevos hasta el próximo commit.

---

## NOCHE (18:00 — 00:00)

### 📊 18:00 — Documentación de patrones de éxito

**3 documentos creados:**
1. `patrones-exito-auditoria-codigo.md` (11,690 bytes) — 5 casos de éxito, 7 principios
2. `resultados-extraordinarios-conclusiones.md` (13,046 bytes) — 10 resultados, 15 conclusiones
3. `algoritmos-señales-descubrimientos.md` (7,507 bytes) — 4 algoritmos, 7 señales, 7 descubrimientos

**Esto cierra el Día 2 y la sesión.**

---

# DÍA 3 — VIERNES 19 DE AGOSTO 2026

---

## MAÑANA (08:00 — presente)

### 📊 08:00 — Estado del sistema actualizado

**`estado_sistema_19ago.md`** — consolidación de:
- Ubicación de archivos reorganizados
- 20 señales con su estado actual
- Pendientes priorizados

---

### 📐 10:00 — Prompt para implementar 4 señales de EXIT

**Archivo:** `.hermes/prompts/implementar-4-señales-exit.md`

**Listo para pasar a Gemini.** 4 señales de EXIT por implementar y medir.

---

### 📊 11:00 — Cronología completa (este documento)

**Creado:** `cronologia-del-hilo.md`

---

## RESUMEN CRONOLÓGICO

| Fecha | Hitos principales |
|-------|-------------------|
| **17-Ago MAÑANA** | Rescate del hilo, B1 descubierto y corregido, EV leave-one-out, cascade leave-one-out |
| **17-Ago TARDE** | Distorsión test, walk-forward cascade, medir_senal.py creado, 4 bugs corregidos, 11 señales registradas |
| **17-Ago NOCHE** | Eventos especiales, edge defensivo propuesto, puntos ciegos corregidos, lookback crash, forense completo |
| **18-Ago MAÑANA** | Análisis estadístico profundo, corrección "rareza=riqueza", marco ED, verificación de bugs |
| **18-Ago TARDE** | Reorganización Clean, análisis EXIT, cambio de modelo, Graphify mapeado |
| **18-Ago NOCHE** | Documentación de patrones de éxito, resultados, conclusiones |
| **19-Ago MAÑANA** | Estado del sistema, prompt EXIT, cronología completa |

---

**Total acumulado:**
- 5 bugs encontrados y corregidos
- 20 señales medidas
- 86 precursores de crash identificados
- 4 algoritmos construidos
- 7 descubrimientos validados
- 8 documentos de especificación creados
- 14 prompts a Gemini/Claude
- 3 correcciones de usuario que cambiaron el rumbo

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 19-Ago-2026