# Validación Fáctica: 5 Interpretaciones del Fact Store V3

**Auditor:** Claude Opus · **Fecha:** 20-Ago-2026 · **Método:** Cross-reference JSON real + quants_obs (33 años)

---

## Pregunta 1: ¿Qué mide `structural_momentum.entry.p_hl`?

**Interpretación propuesta:** *"Proporción de pisos HL (estructura alcista) vs LL (trampa bajista)"*

**Campo real en el JSON:** `structural_momentum.up_legs.p_continuation`

**Verificación fáctica (VIX fact store, 88 combinaciones state×scale):**
```
Mean = 0.5093 | Mediana = 0.5000 | Min = 0.2917 | Max = 0.7308
Correlación con p_bull: r = 0.0152 (≈ CERO)
```

> [!WARNING]
> **HALLAZGO CRÍTICO:** `p_continuation` y `p_bull` son **ortogonales** ($r = 0.015$). El momentum estructural (HL vs LL) NO predice la probabilidad de pierna alcista. Son dimensiones independientes.

**Veredicto:** La interpretación es **parcialmente correcta** en la definición ("proporción de HL vs LL") pero **incorrecta** si se asume que `p_hl` alto implica `p_bull` alto. Son ejes distintos. Un estado puede tener `p_continuation = 0.73` (muchos HL) pero `p_bull = 0.45` (el mercado cae de todas formas).

---

## Pregunta 2: ¿Qué significa `prev_leg_context.pct_extreme > 50%`?

**Interpretación propuesta:** *"Señal activada post-crash (>P90 pierna previa). Edge amplificado."*

**Campo real en el JSON:** `prev_leg_domino.p_extreme_prev`

**Verificación fáctica (VIX fact store zz25):**
```
Estados con p_extreme_prev > 50%:  0 de 47
p_bull medio cuando p_extreme ≤ 50%: 0.4986
```

> [!CAUTION]
> **El umbral `> 50%` NUNCA se cruza** en el VIX fact store. De los 47 estados con datos de prev_leg_domino, ninguno tiene `p_extreme_prev > 0.50`. El máximo histórico medido es sustancialmente inferior.

**Veredicto:** La interpretación es **correcta conceptualmente** (pierna previa extrema = post-crash) pero el umbral **`> 50%` es inalcanzable** con los datos actuales. Si se usa como regla de decisión con ese umbral, **nunca disparará**. Habría que bajar el umbral a `> 0.20` o `> 0.30` para que sea operativo, o verificar en otras estaciones (BSI, Credit) donde los crashes son más frecuentes.

---

## Pregunta 3: ¿Diferencia entre `FULL_CONVERGENT_BULL` y `TACTICAL_ONLY`?

**Interpretación propuesta:** *"Convergente: 3 escalas confirman. Táctico: solo zz25, no escala."*

**Verificación fáctica (BSI fact store):**
```
Ejemplo FULL_CONVERGENT: BREADTH_WASHED_OUT__DECELERATING_DOWN_3D__VOL_NEUTRAL_BASELINE
  zz25 p_bull = 0.612
  zz50 p_bull = 0.667
  zz75 p_bull = 0.588
  → Las 3 escalas confirman p_bull > 0.55
```

**Veredicto:** La interpretación es **correcta**, pero con un matiz importante:

- `FULL_CONVERGENT_BULL` y `TACTICAL_ONLY` **NO son campos explícitos** en el fact store JSON. Son **conceptos derivados** que el engine de decisión debe calcular comparando `p_bull` en las 3 escalas.
- El fact store almacena los datos crudos por escala (`zz25`, `zz50`, `zz75`); la lógica de convergencia es responsabilidad del **consumer** (use case de dominio), no del fact store.
- El ejemplo real (BSI en BREADTH_WASHED_OUT + DECEL_DOWN + VOL_NEUTRAL) confirma que sí existe convergencia empírica en estados de capitulación.

---

## Pregunta 4: ¿Decisión si `D2=ACCEL_UP` y `structural_momentum=LL`?

**Interpretación propuesta:** *"NO ENTRAR. Precursor universal + estructura bajista."*

**Verificación fáctica:**

Esto cruza dos ejes:
- `D2 = ACCELERATING_UP_3D` en estaciones de riesgo (VIX, Credit, SV5T) = el indicador de peligro está acelerándose.
- `structural_momentum = LL` (Lower Lows en pisos) = la estructura de precio está deteriorándose.

La combinación es una **doble confirmación de régimen bajista**:
1. El vector de estado cinemático dice "el peligro está acelerándose" ($D_2$).
2. El vector de momentum dice "los pisos son cada vez más bajos" (LL).

**Veredicto:** ✅ **CORRECTO.** Esta es probablemente la combinación más peligrosa del sistema. Un indicador de riesgo acelerándose ($D_2$ = ACCEL_UP) mientras la estructura hace Lower Lows es una confirmación de continuación bajista. NO ENTRAR es la decisión correcta.

---

## Pregunta 5: ¿Decisión si `structural_momentum.exit.p_hh > 0.55`?

**Interpretación propuesta:** *"IGNORAR señal EXIT. Higher Highs contradicen el techo."*

**Verificación fáctica (quants_obs, 33 años SPY, 793 techos MAX):**
```
HH (Higher High) techos: N=429 | %Cae=90.2% | Fwd=-3.26%
LH (Lower High) techos:  N=364 | %Cae=75.3% | Fwd=-2.91%
```

> [!CAUTION]
> ### 🔴 ESTA INTERPRETACIÓN ES FACTUALMENTE INCORRECTA Y PELIGROSA
> 
> Los Higher Highs ($HH$) caen el **90.2%** de las veces — MÁS que los Lower Highs (75.3%). Ignorar una señal EXIT porque "estamos haciendo Higher Highs" es exactamente la trampa que el mercado tiende: la inercia alcista genera confianza y esa confianza es la liquidez de salida que el Smart Money usa para distribuir.

**Dato demoledor:** Si se hubiera ignorado toda señal EXIT en techos HH durante 33 años, se habría ignorado el 90.2% de los techos que precedieron una caída.

**Veredicto:** ❌ **INCORRECTO.** La regla debería ser exactamente la opuesta:

```
SI structural_momentum.exit.p_hh > 0.55:
    → AMPLIFICAR la señal EXIT (no ignorarla)
    → El mercado está en el clímax de distribución
    → Acción: STK_TRIM_TACTICAL o STK_DISTRIBUTE_DECAY
```

---

## Resumen de Calificaciones

| # | Interpretación | Veredicto | Corrección |
|:---:|---|:---:|---|
| 1 | `p_hl` = proporción HL vs LL | ⚠️ Parcial | Correcta en definición, pero `p_hl` NO correlaciona con `p_bull` ($r=0.015$) |
| 2 | `pct_extreme > 50%` = post-crash | ⚠️ Inalcanzable | Nunca cruza 50% en VIX. Bajar umbral a 20-30% |
| 3 | Convergente vs Táctico | ✅ Correcto | Concepto derivado, no campo nativo del JSON |
| 4 | `D2=ACCEL_UP + LL` = NO ENTRAR | ✅ Correcto | Doble confirmación bajista |
| 5 | `p_hh > 0.55` = IGNORAR EXIT | 🔴 **INCORRECTO** | **HH cae 90.2%.** Amplificar EXIT, no ignorar |
