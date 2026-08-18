# Análisis Profundo de Señales de EXIT
## Botero Trade — 18-Ago-2026

---

## 0. PROBLEMA IDENTIFICADO

```
SISTEMA ACTUAL:
  ✅ 11 señales de ENTRY (credit_easing, bsi_washed_out, capitulacion, etc.)
  ❌ Solo 2 señales de EXIT (euforia, fg_extreme_greed)
  
ESPECIFICACIÓN DICE:
  "No usar stops de PRECIO — stop de SEÑAL (el vector de estado dice 'peligro')"
  
GAP CRÍTICO:
  El sistema puede ENTRAR en 11 condiciones diferentes, pero solo puede SALIR en 2.
  Esto viola el principio de "salida por cambio del vector de estado METAR".
```

---

## 1. SEÑALES DE EXIT ACTUALES (solo 2)

### 1.1 euforia
- **Definición:** VIX en DEEP_COMPLACENCY/LOW_VOL + BSI en BULLISH_BREADTH
- **Edge:** -2.99% (WR 15%) — señal de TECHO
- **Interpretación:** Complacencia extrema = vender
- **Problema:** Solo detecta un tipo de techo (complacencia)

### 1.2 fg_extreme_greed
- **Definición:** FG en EXTREME_GREED (codicia extrema)
- **Edge:** -1.92% (WR 19%) — señal de TECHO
- **Interpretación:** Codicia extrema = techo
- **Problema:** Solo detecta un tipo de techo (codicia)

---

## 2. TIPOS DE SALIDA QUE FALTAN

Según la especificación, la salida debe ser por **cambio del vector de estado METAR**. Esto implica:

### 2.1 Salidas por DEGRADACIÓN del vector de estado
```
ENTRADA: vector de estado favorable (ej: VIX bajo, BSI alto, credit easing)
SALIDA: vector de estado se degrada (ej: VIX sube, BSI baja, credit stress)

Ejemplo:
  Si entré con bsi_washed_out (BSI en BREADTH_WASHED_OUT)
  Salgo cuando BSI sale de BREADTH_WASHED_OUT → BREADTH_RECOVERY
```

### 2.2 Salidas por ACTIVACIÓN de señales de peligro
```
ENTRADA: cualquier señal de ENTRY
SALIDA: señal de peligro activada (σ-overflow, D3<0.5 pre-extreme, cuchillo)

Ejemplo:
  Si entré con credit_easing_k1
  Salgo cuando VIX entra en CRISIS_SPIKE (señal de peligro)
```

### 2.3 Salidas por CASCADE_REVERSAL
```
ENTRADA: cascade_conviction_50 > 0 (señal alcista)
SALIDA: cascade_conviction_50 < 0 (señal bajista)

Ejemplo:
  Si entré con pcr_put_panic (cascade_50 = 0.69)
  Salgo cuando cascade_50 cae por debajo de 0.30 (reversal)
```

### 2.4 Salidas por TIME_DECAY
```
ENTRADA: señal de ENTRY con ftt_bull_days = 5 días
SALIDA: después de 5 días (tiempo esperado de la pierna)

Ejemplo:
  Si entré con vvix_entry (ftt_bull_days = 3.5)
  Salgo después de 3-4 días (tiempo esperado)
```

---

## 3. SEÑALES DE EXIT PROPUESTAS

### 3.1 EXIT por DEGRADACIÓN de BSI
```python
@_registrar("bsi_recovery")
def _bsi_recovery(df):
    """BSI sale de BREADTH_WASHED_OUT → BREADTH_RECOVERY"""
    bsi_d1 = df["bsi_sk"].str.split("__").str[0]
    return bsi_d1.isin(["BREADTH_RECOVERY", "NEUTRAL_HIGH_BREADTH"])
```

**Hipótesis:** Si entré con bsi_washed_out, salgo cuando BSI se recupera.
**Edge esperado:** Negativo (la recuperación marca el fin de la pierna alcista).

### 3.2 EXIT por ACTIVACIÓN de VIX CRISIS
```python
@_registrar("vix_crisis_spike")
def _vix_crisis_spike(df):
    """VIX entra en CRISIS_SPIKE → señal de peligro"""
    vix_d1 = df["vix_sk"].str.split("__").str[0]
    return vix_d1 == "CRISIS_SPIKE"
```

**Hipótesis:** CRISIS_SPIKE marca el inicio de una caída severa.
**Edge esperado:** Negativo (la crisis marca el fin de la pierna alcista).

### 3.3 EXIT por CASCADE_REVERSAL
```python
@_registrar("cascade_reversal")
def _cascade_reversal(df):
    """cascade_conviction_50 cae por debajo de 0.30 → reversal"""
    return df["cascade_conviction_50"] < 0.30
```

**Hipótesis:** Cascade bajo marca el fin de la tendencia.
**Edge esperado:** Negativo (cascade bajo = fin de la pierna).

### 3.4 EXIT por CREDIT_STRESS
```python
@_registrar("credit_stress_exit")
def _credit_stress_exit(df):
    """CREDIT entra en CREDIT_STRESS → señal de peligro"""
    credit_d1 = df["credit_sk"].str.split("__").str[0]
    return credit_d1 == "CREDIT_STRESS"
```

**Hipótesis:** Credit stress marca el inicio de una recesión.
**Edge esperado:** Negativo (credit stress = fin de la pierna alcista).

### 3.5 EXIT por DXY_SPIKE
```python
@_registrar("dxy_spike_exit")
def _dxy_spike_exit(df):
    """DXY entra en DOLLAR_SPIKE_CRISIS → señal de peligro"""
    dxy_d1 = df["dxy_sk"].str.split("__").str[0]
    return dxy_d1 == "DOLLAR_SPIKE_CRISIS"
```

**Hipótesis:** Dollar spike marca el inicio de una crisis global.
**Edge esperado:** Negativo (dollar spike = fin de la pierna alcista).

### 3.6 EXIT por SKEW_PARANOIA
```python
@_registrar("skew_paranoia_exit")
def _skew_paranoia_exit(df):
    """SKEW entra en BLACK_SWAN_PARANOIA → señal de peligro"""
    skew_d1 = df["skew_sk"].str.split("__").str[0]
    return skew_d1 == "BLACK_SWAN_PARANOIA"
```

**Hipótesis:** Black swan paranoia marca el inicio de una crisis.
**Edge esperado:** Negativo (paranoia = fin de la pierna alcista).

### 3.7 EXIT por PCR_PANIC
```python
@_registrar("pcr_panic_exit")
def _pcr_panic_exit(df):
    """PCR entra en EXTREME_PUT_PANIC → señal de peligro"""
    pcr_d1 = df["pcr_sk"].str.split("__").str[0]
    return pcr_d1 == "EXTREME_PUT_PANIC"
```

**Hipótesis:** Put panic marca el inicio de una caída severa.
**Edge esperado:** Negativo (panic = fin de la pierna alcista).

---

## 4. METODOLOGÍA DE MEDICIÓN

Para cada señal de EXIT propuesta, mediré:

### 4.1 Edge ofensivo (forward return)
```
¿Cuánto pierde el mercado cuando la señal de EXIT se activa?
Edge = mean(forward_return | señal de EXIT activa)
```

### 4.2 Edge defensivo (pérdida evitada)
```
¿Cuánta pérdida evita salir cuando la señal de EXIT se activa?
ED = |mean_loss| - (mean_win × FA_rate)
```

### 4.3 Timing
```
¿Cuántos días antes del crash se activa la señal de EXIT?
anticipación = días antes del pivot_date que la señal se activó
```

### 4.4 Falsas alarmas
```
¿Cuántas veces la señal de EXIT se activa pero el mercado NO cae?
FA_rate = % de señales de EXIT que NO resultan en caída
```

### 4.5 Estabilidad por década
```
¿La señal de EXIT es estable en el tiempo?
WR por década: 1990s, 2000s, 2010s, 2020s
```

---

## 5. PLAN DE TRABAJO

### Fase 1: Implementar señales de EXIT en medir_senal.py
- Agregar 7 señales de EXIT propuestas
- Ejecutar medir_senal.py con cada señal
- Generar JSONs de medición

### Fase 2: Analizar resultados
- Comparar edge ofensivo vs edge defensivo
- Identificar señales de EXIT más efectivas
- Validar con bootstrap CI95

### Fase 3: Integrar en el sistema
- Seleccionar las 3-5 señales de EXIT más efectivas
- Documentar en la especificación
- Crear prompts para Gemini/Claude

### Fase 4: Validar con backtest OOS
- Backtest walk-forward del sistema completo (ENTRY + EXIT)
- Medir capture ratio, drawdown, Sharpe ratio
- Validar que el sistema completo es rentable

---

## 6. CRITERIOS DE ÉXITO

Una señal de EXIT es efectiva si:
1. **Edge ofensivo < -1%** (el mercado pierde >1% cuando la señal se activa)
2. **Edge defensivo > 3%** (salir evita >3% de pérdida)
3. **WR > 60%** (la señal acierta >60% de las veces)
4. **FA_rate < 40%** (menos del 40% de las señales son falsas alarmas)
5. **Estable por década** (WR no cae por debajo de 50% en ninguna década)

---

## 7. PRÓXIMOS PASOS

1. **Inmediato:** Implementar las 7 señales de EXIT en medir_senal.py
2. **Corto plazo:** Medir edge ofensivo y defensivo de cada señal
3. **Mediano plazo:** Seleccionar las 3-5 señales más efectivas
4. **Largo plazo:** Integrar en el sistema completo y validar con backtest OOS

---

**¿Procedo con la implementación de las 7 señales de EXIT?**
