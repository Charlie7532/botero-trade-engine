# Replanteamiento de Señales de EXIT
## Análisis de Datos Reales — 18-Ago-2026

---

## 0. PROBLEMA IDENTIFICADO

```
HIPÓTESIS INICIAL (INCORRECTA):
  "Señales de peligro = señales de EXIT"
  
RESULTADOS REALES:
  vix_crisis_spike:     edge +0.75% (WR 56.7%)  → ENTRY (comprar miedo)
  credit_stress_exit:   edge +1.00% (WR 54.9%)  → ENTRY (comprar miedo)
  pcr_panic_exit:       edge +2.70% (WR 71.4%)  → ENTRY (comprar miedo)
  
CONCLUSIÓN:
  Las señales de "pánico" son señales de ENTRY, no de EXIT.
  El sistema ya tiene estas señales: credit_stress, pcr_put_panic, etc.
```

---

## 1. SEÑAL DE EXIT EFECTIVA: bsi_recovery

```
RESULTADO:
  bsi_recovery: edge -1.63% (WR 29%)  → EXIT efectivo
  
INTERPRETACIÓN:
  Cuando BSI sale de BREADTH_WASHED_OUT → BREADTH_RECOVERY o NEUTRAL_HIGH_BREADTH
  El mercado PIERDE 1.63% en promedio.
  
POR QUÉ FUNCIONA:
  BREADTH_WASHED_OUT marca el fondo de una caída.
  Cuando BSI se recupera, la pierna alcista TERMINÓ.
  Es el fin de la tendencia, no el inicio.
```

---

## 2. REDEFINICIÓN DE SEÑALES DE EXIT

### 2.1 Señales de EXIT = Estados que marcan el FIN de una tendencia alcista

```
TIPOS DE EXIT:

1. EXIT por FIN DE EUFORIA (techo)
   - Estados de complacencia extrema
   - Ejemplo: euforia, fg_extreme_greed (ya implementadas)

2. EXIT por FIN DE RECUPERACIÓN (piso)
   - Estados de recuperación que marcan el fin de la pierna alcista
   - Ejemplo: bsi_recovery (implementada, efectiva)

3. EXIT por CAMBIO DE RÉGIMEN
   - Transición de VERANO a INVIERNO
   - Ejemplo: credit_stress + vix_high (no implementada)
```

### 2.2 Señales de ENTRY = Estados que marcan el INICIO de una tendencia

```
TIPOS DE ENTRY:

1. ENTRY por MIEDO EXTREMO (comprar miedo)
   - Estados de pánico
   - Ejemplo: credit_stress, pcr_put_panic, vix_crisis_spike

2. ENTRY por RECUPERACIÓN (comprar fondo)
   - Estados de fondo
   - Ejemplo: bsi_washed_out, capitulacion

3. ENTRY por EUFORIA (vender techo)
   - Estados de complacencia
   - Ejemplo: euforia, fg_extreme_greed (señales de EXIT en realidad)
```

---

## 3. NUEVAS SEÑALES DE EXIT PROPUESTAS

### 3.1 EXIT por FIN DE EUFORIA

```python
@_registrar("vix_complacency_exit")
def _vix_complacency_exit(df):
    """VIX en DEEP_COMPLACENCY o LOW_VOL — fin de la euforia."""
    vix_d1 = df["vix_sk"].dropna().str.split("__").str[0]
    mask = vix_d1.isin(["DEEP_COMPLACENCY", "LOW_VOL"])
    return mask.reindex(df.index, fill_value=False)
```

**Hipótesis:** Complacencia extrema marca el fin de la tendencia alcista.
**Edge esperado:** Negativo (el mercado pierde cuando la complacencia es extrema).

### 3.2 EXIT por FIN DE CREDIT_EASE

```python
@_registrar("credit_ease_exit")
def _credit_ease_exit(df):
    """CREDIT sale de CREDIT_EASE o DEEP_CREDIT_EASE — fin del easing."""
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    mask = ~credit_d1.isin(["CREDIT_EASE", "DEEP_CREDIT_EASE"])
    return mask.reindex(df.index, fill_value=False)
```

**Hipótesis:** Cuando el crédito deja de facilitar, la tendencia alcista termina.
**Edge esperado:** Negativo (el mercado pierde cuando el easing termina).

### 3.3 EXIT por FIN DE BREADTH_EXPANSION

```python
@_registrar("breadth_contraction_exit")
def _breadth_contraction_exit(df):
    """BSI sale de EXPANSIVE_BREADTH o HYPER_EXPANSIVE_BREADTH — fin de la expansión."""
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    mask = ~bsi_d1.isin(["EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"])
    return mask.reindex(df.index, fill_value=False)
```

**Hipótesis:** Cuando la amplitud se contrae, la tendencia alcista termina.
**Edge esperado:** Negativo (el mercado pierde cuando la amplitud se contrae).

### 3.4 EXIT por CAMBIO DE RÉGIMEN (VERANO → INVIERNO)

```python
@_registrar("regime_change_exit")
def _regime_change_exit(df):
    """Cambio de régimen: VERANO → INVIERNO."""
    # VERANO: credit_ease + vix_low + bsi_high
    # INVIERNO: credit_stress + vix_high + bsi_low
    
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    vix_d1 = df["vix_sk"].dropna().str.split("__").str[0]
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    
    # INVIERNO: credit_stress + vix_high + bsi_low
    invierno = (
        credit_d1.isin(["CREDIT_STRESS", "ELEVATED_CREDIT_STRESS", "CREDIT_CRISIS"]) &
        vix_d1.isin(["HIGH_VOL", "ELEVATED_PANIC", "CRISIS_SPIKE"]) &
        bsi_d1.isin(["BREADTH_WASHED_OUT", "OVERSOLD_BREADTH", "NEUTRAL_LOW_BREADTH"])
    )
    
    return invierno.reindex(df.index, fill_value=False)
```

**Hipótesis:** Cambio de régimen VERANO → INVIERNO marca el fin de la tendencia alcista.
**Edge esperado:** Negativo (el mercado pierde cuando cambia el régimen).

---

## 4. PLAN DE TRABAJO REVISADO

### Fase 1: Implementar nuevas señales de EXIT
- vix_complacency_exit
- credit_ease_exit
- breadth_contraction_exit
- regime_change_exit

### Fase 2: Medir edge ofensivo y defensivo
- Ejecutar medir_senal.py con cada señal
- Generar JSONs de medición

### Fase 3: Analizar resultados
- Comparar edge ofensivo vs edge defensivo
- Identificar señales de EXIT más efectivas
- Validar con bootstrap CI95

### Fase 4: Integrar en el sistema
- Seleccionar las 3-5 señales de EXIT más efectivas
- Documentar en la especificación
- Crear prompts para Gemini/Claude

---

## 5. CRITERIOS DE ÉXITO REVISADOS

Una señal de EXIT es efectiva si:
1. **Edge ofensivo < -1%** (el mercado pierde >1% cuando la señal se activa)
2. **Edge defensivo > 3%** (salir evita >3% de pérdida)
3. **WR < 40%** (la señal acierta >60% de las veces en predecir pérdida)
4. **FA_rate < 40%** (menos del 40% de las señales son falsas alarmas)
5. **Estable por década** (WR no sube por encima de 50% en ninguna década)

---

## 6. PRÓXIMOS PASOS

1. **Inmediato:** Implementar las 4 nuevas señales de EXIT
2. **Corto plazo:** Medir edge ofensivo y defensivo de cada señal
3. **Mediano plazo:** Seleccionar las 3-5 señales más efectivas
4. **Largo plazo:** Integrar en el sistema completo y validar con backtest OOS

---

**¿Procedo con la implementación de las 4 nuevas señales de EXIT?**
