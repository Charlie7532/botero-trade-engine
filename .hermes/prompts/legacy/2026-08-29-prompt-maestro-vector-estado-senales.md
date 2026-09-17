# Prompt Maestro: Integración del Vector de Estado Completo al Sistema de Señales

**Versión:** 1.0 — 29-Ago-2026  
**Sesión Origen:** Investigación 28-29 Ago 2026 (conversación 012139fd)  
**Propósito:** Mandato ejecutable de investigación que captura TODOS los descubrimientos y define el trabajo pendiente para integrar el vector de estado completo y la magnitud σ al arnés de 28 señales.

> [!IMPORTANT]
> **Este documento es un mandato de investigación, NO un plan de implementación de código.** Léelo completo antes de escribir cualquier código. Contiene hallazgos empíricos validados con N, WR y retornos reales de SPY. Las tablas son datos factuales del Vault (Neon PostgreSQL, ~8,400 barras diarias de SPY).

---

## A. INVENTARIO DE DESCUBRIMIENTOS EMPÍRICOS

### A.1 Overflows Cinemáticos — Censo Completo del Vault

**Fuente:** Recorrido vela a vela sobre `TimescaleDataStore` para 10 estaciones × 3 dimensiones (30 canales).  
**Script:** [`audit_overflow_candle_anatomy.py`](file:///root/botero-trade/research/01_señales_entry_exit/audit_overflow_candle_anatomy.py)  

| Métrica | Solo Pivotes (quants_obs) | Vault Completo | Factor |
|---|:-:|:-:|:-:|
| Overflows ≥2σ | 2,449 | **13,071** | **5.3×** |
| Overflows ≥3σ | ~650 | **3,354** | **5.2×** |
| **% fuera de pivotes** | — | **53.7%** | — |

**El 53.7% de los overflows cinemáticos ocurren FUERA de los pivotes de zigzag.** El arnés de 28 señales, que solo evalúa en pivotes, es ciego a la mayoría de los eventos.

### A.2 Confluencia Vectorial — El Discriminador Real

**Descubrimiento:** Un overflow individual en un solo canal ≈ ruido. La CONFLUENCIA (número de canales simultáneamente en overflow ≥2σ) es el discriminador real.

**Datos de confluencia en t=0 (pivotes):**

| Canales simultáneos | N días | WR 1d | WR 20d | Fwd 20d |
|:-:|:-:|:-:|:-:|:-:|
| 1 | 353 | 49.3% | 59.2% | +0.62% |
| 2 | 186 | 48.4% | 57.5% | +0.41% |
| 3 | 111 | 56.8% | 64.0% | +1.11% |
| **4** | **80** | **63.7%** | **72.5%** | **+3.85%** |
| 5 | 61 | 54.1% | 63.9% | +1.06% |
| **8** | **10** | **70.0%** | **80.0%** | **+2.85%** |
| **10** | **6** | 50.0% | **100%** | **+7.23%** |

**Datos de confluencia en ENTRE (>2d de pivote):**

| Canales simultáneos | N días | WR 1d | WR 20d | Fwd 20d |
|:-:|:-:|:-:|:-:|:-:|
| 1 | 1,341 | 57.0% | 67.6% | +0.95% |
| 3 | 250 | 57.6% | 73.2% | +1.42% |
| **5** | **40** | **65.0%** | **85.0%** | **+2.09%** |
| **6** | **21** | 61.9% | **81.0%** | **+2.33%** |

**Regla operativa provisional:**
- En pivote: confluencia ≥4 canales → WR 72.5% (operable)
- ENTRE pivotes: confluencia ≥5 canales → WR 85% (diamante)
- < 3 canales → marginal en pivote, ~67% ENTRE

### A.3 Polaridad: Panic Score vs Euphoria Score

**Descubrimiento:** La DIRECCIÓN del overflow importa tanto como la magnitud.

```
Panic Score = Σ [VIX(+), VVIX(+), PCR(+), SV5_Turb(+), FG(-), BSI(-), Credit(-), Rotation(-)]
Euphoria Score = Σ [FG(+), BSI(+), Rotation(+), VIX(-), PCR(-)]
```

Donde (+) = z-score ≥ 2σ, (-) = z-score ≤ -2σ.

**t=0 MIN (Pisos, N=485):**

| Panic Score | N | WR 1d | WR 5d | WR 20d | Fwd 20d |
|:-:|:-:|:-:|:-:|:-:|:-:|
| 0 | 71 | 78.9% | 77.5% | 74.6% | +2.35% |
| 1 | 168 | 79.2% | 72.6% | 69.0% | +1.93% |
| 3 | 51 | 70.6% | 70.6% | 74.5% | +3.32% |
| 4 | 38 | 65.8% | 78.9% | 73.7% | +4.16% |
| **7** | **12** | **91.7%** | 66.7% | **83.3%** | +1.50% |
| **8** | **6** | **83.3%** | 66.7% | **83.3%** | **+8.49%** |

**t=0 MAX (Techos, N=388):**

| Euphoria Score | N | Short WR 1d | Short WR 5d | Short WR 20d | Fwd 20d |
|:-:|:-:|:-:|:-:|:-:|:-:|
| 0 | 217 | **77.9%** | **69.1%** | 49.3% | -0.62% |
| 1 | 115 | **71.3%** | **67.8%** | 52.2% | -0.93% |
| 2 | 44 | **65.9%** | **70.5%** | **54.5%** | -1.40% |

**Pisos con Panic Score alto = rebote explosivo (+8.49%). Techos son tácticos (Short WR alto a 1-5d pero se diluye a 20d por drift alcista secular).**

**ENTRE pivotes — Euforia NO es señal de techo:**

| Euphoria Score ≥ K | N | Short WR 5d | Short WR 20d | Fwd 20d |
|:-:|:-:|:-:|:-:|:-:|
| ≥ 1 | 907 | 32.6% | 30.2% | +1.14% |
| ≥ 2 | 150 | 23.3% | 26.7% | +1.47% |
| **≥ 3** | **30** | **6.7%** | **26.7%** | +1.57% |

**REGLA: Shortear euforia en tendencia es suicida.** El mercado sigue subiendo 73-87% de las veces.

### A.4 Magnitud σ Aislada — Anatomía de Vela

| Sigma | Signo | N | Bar[-1] Verde | Bar[0] Verde | Bar[+1] Verde |
|:-:|---|:-:|:-:|:-:|:-:|
| 2σ-3σ | POS(+) | 4,936 | 52.2% | 49.9% | 52.6% |
| 2σ-3σ | NEG(-) | 1,960 | 43.3% | 42.7% | **53.8%** |
| 3σ-4σ | POS(+) | 1,290 | 50.2% | 46.0% | 52.2% |
| 3σ-4σ | NEG(-) | 292 | 43.8% | 46.9% | **58.6%** |
| **≥4σ** | POS(+) | 357 | 50.4% | 42.6% | **58.3%** |
| **≥4σ** | NEG(-) | 112 | 56.2% | 58.9% | 56.2% |

**2σ-3σ = ruido (52%). La discriminación empieza en 3σ. ≥4σ = operativo.**

### A.5 Diamantes de Vela

**Top alcistas (bar[+1] ≥70% verde, N≥10):**

| Canal | σ | Signo | Slot | N | Bar[+1]% | Body[+1] |
|---|:-:|---|---|:-:|:-:|:-:|
| **VVIX.d2** | ≥4σ | POS(+) | t=0 | **13** | **85%** | **+1.21%** |
| **SKEW.d1** | 3σ-4σ | POS(+) | ENTRE | 12 | **83%** | -0.03% |
| **Yield.d2** | 3σ-4σ | POS(+) | t=0 | 10 | **80%** | **+1.06%** |
| **BSI.d2** | 2σ-3σ | NEG(-) | t=0 | **55** | **76%** | +0.47% |
| **BSI.d2** | 3σ-4σ | POS(+) | ENTRE | 21 | **76%** | +0.20% |
| **SV5_Turb.d2** | 3σ-4σ | NEG(-) | ENTRE | 24 | **75%** | +0.21% |
| **VIX.d2** | ≥4σ | POS(+) | t=0 | **34** | **74%** | **+1.37%** |
| **BSI.d2** | 3σ-4σ | NEG(-) | t=0 | **19** | **74%** | **+0.79%** |
| **SV5_Turb.d2** | ≥4σ | NEG(-) | ENTRE | 28 | **71%** | +0.27% |

**Top bajistas (bar[+1] ≤30% verde, N≥10):**

| Canal | σ | Signo | Slot | N | Bar[+1]% | Body[+1] |
|---|:-:|---|---|:-:|:-:|:-:|
| **VIX.d2** | 3σ-4σ | POS(+) | t-1 | 10 | **30%** | -0.83% |
| **PCR.d1** | 2σ-3σ | POS(+) | t-1 | 18 | **28%** | **-1.03%** |
| **VIX.d3** | 3σ-4σ | POS(+) | t-1 | 11 | **27%** | -1.02% |
| **SV5_Turb.d3** | 3σ-4σ | POS(+) | t-1 | 13 | **23%** | **-1.07%** |
| **SV5_Turb.d3** | 2σ-3σ | POS(+) | t-2 | 18 | **22%** | -0.49% |
| **PCR.d1** | 2σ-3σ | POS(+) | ENTRE | 23 | **22%** | -0.34% |
| **Credit.d2** | 2σ-3σ | POS(+) | t=0 | 14 | **21%** | **-1.04%** |
| **VVIX.d2** | 2σ-3σ | NEG(-) | t=0 | 15 | **20%** | -0.63% |
| **Yield.d1** | 2σ-3σ | NEG(-) | t-1 | 11 | **9%** | -0.57% |

### A.6 Canales con Edge Individual (sin confluencia)

**En t=0 (sólos):**

| Canal solo | N | WR 20d |
|---|:-:|:-:|
| VIX.d3 | 20 | **85%** ✅ |
| VIX.d1 | 21 | **81%** ✅ |
| SKEW.d1 | 20 | **80%** ✅ |
| VIX.d2 | 15 | 67% |
| BSI.d3 | 20 | 40% ❌ |
| Yield.d3 | 21 | 38% ❌ |

**En ENTRE (sólos):**

| Canal solo | N | WR 20d |
|---|:-:|:-:|
| Credit.d1 | 49 | **84%** ✅ |
| SV5_Turb.d2 | 72 | **78%** ✅ |
| SKEW.d1 | 48 | **75%** ✅ |

---

## B. LAS 5 BRECHAS CRÍTICAS

1. **quants_obs no tiene z-scores crudos** → Agregar 30 columnas `{station}_z_d1/d2/d3`
2. **El evaluador mide horizonte fijo** → Agregar anatomía de vela + retorno estocástico zigzag
3. **Las señales no tienen contexto vectorial** → Score de Confluencia + Score de Magnitud como columnas auxiliares
4. **Las señales ENTRE no existen** → Crear señales de continuación cinemática vela a vela
5. **Ningún EXIT es puramente cinemático** → Crear precursores de caída desde diamantes bajistas

---

## C. PROTOCOLO DE INVESTIGACIÓN PENDIENTE

### C.1 Cruzar diamantes con la triada del fact store
Para cada diamante: consultar state_key D1×D2×D3, extraer p_bull/ev_net/e_days en zz25/zz50/zz75. ¿El fact store ya captura este edge o es información nueva?

### C.2 Medir retorno estocástico de los diamantes
Para cada diamante: medir la pierna zigzag que sigue (dirección, duración, magnitud, cascada a zz50/zz75).

### C.3 Validar overflows ENTRE con evaluación continua
WR 85% (confluencia ≥5) medido con fwd_20d fijo. Validar con retorno estocástico de la pierna siguiente.

### C.4 Test de significancia para señales nuevas
Bonferroni (p < 0.000238 = 0.05/210), DSR, Walk-forward OOS (5 folds), Structural break.

### C.5 Clasificación por slot temporal

| Slot | Tipo | Uso Operativo |
|---|---|---|
| **t-2** | Alerta temprana | Reducir exposición / preparar liquidez |
| **t-1** | Precursor | Sizing down / activar stops |
| **t=0** | Exacta | Entry/Exit con conviction por confluencia |
| **t+1** | Confirmación | Añadir posición si t=0 confirmada |
| **t+2** | Posmortem | Validación, no accionable |
| **ENTRE** | Continuación | Mantener posiciones / trend following |

---

## D. ARCHIVOS DE REFERENCIA

**Scripts de investigación:**
- [`audit_overflow_candle_anatomy.py`](file:///root/botero-trade/research/01_señales_entry_exit/audit_overflow_candle_anatomy.py)
- [`audit_vector_confluence.py`](file:///root/botero-trade/research/01_señales_entry_exit/audit_vector_confluence.py)
- [`extract_overflows_vela_a_vela.py`](file:///root/botero-trade/research/01_señales_entry_exit/extract_overflows_vela_a_vela.py)

**Artefactos:**
- [`distribucion_overflows_distancia_pivote.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/distribucion_overflows_distancia_pivote.md)
- [`auditoria_descubrimiento_vector_estado.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/auditoria_descubrimiento_vector_estado.md)
- [`anatomia_velas_overflows_corregido.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/anatomia_velas_overflows_corregido.md)
- [`inventario_overflows_cinematicos.md`](file:///root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/inventario_overflows_cinematicos.md)

**Código del arnés:**
- [`señales.py`](file:///root/botero-trade/research/01_señales_entry_exit/arnes/señales.py) — 28+3 señales
- [`generate_quants_obs.py`](file:///root/botero-trade/backend/scripts/generators/generate_quants_obs.py) — Generador
- [`sigma_overflow.py`](file:///root/botero-trade/backend/modules/entry_decision/domain/rules/sigma_overflow.py) — Constantes μ/σ
- [`fact_store_v3_architecture.md`](file:///root/botero-trade/.hermes/paraauditar/fact_store_v3_architecture.md) — Arquitectura fact stores

---

## E. RESTRICCIONES INAMOVIBLES

1. **Dato mata relato.** Toda conclusión debe tener N, WR, retorno medio, y CI95 cuando N≥20.
2. **No medir en rangos fijos arbitrarios.** El retorno estocástico (pierna zigzag) es la medición correcta. Horizontes fijos solo para comparabilidad.
3. **No agrupar magnitudes.** 2σ, 3σ, 4σ son fenómenos distintos. Separar siempre.
4. **No ignorar el signo.** VIX(+) ≠ VIX(-). Separar siempre.
5. **No evaluar sin el vector completo.** Confluencia y polaridad son obligatorias.
6. **No implementar antes de explorar.** El Protocolo C debe completarse antes de cualquier plan de código.
7. **Bonferroni es obligatorio.** 35 diamantes × 6 slots = 210 comparaciones → p < 0.000238.
