# PROMPT PARA GEMINI — Implementar y medir 4 señales de EXIT

## CONTEXTO
El sistema Botero Trade tiene 20 señales medidas, pero solo 3 son de EXIT (euforia, fg_extreme_greed, bsi_recovery). Necesitamos desarrollar 4 señales de EXIT adicionales basadas en el vector de estado METAR.

## ARCHIVOS DE REFERENCIA
- `research/01_señales_entry_exit/medir_senal.py` — Arnés de medición (registrar señales aquí)
- `research/01_señales_entry_exit/` — 20 JSONs de medición existentes
- `docs/research/01_señales_entry_exit/analisis_señales_exit.md` — Análisis de señales de EXIT
- `docs/research/01_señales_entry_exit/replanteamiento_señales_exit.md` — Replanteamiento

## TAREAS

### Tarea 1: Implementar 4 señales de EXIT en medir_senal.py
Agregar después de `bsi_recovery` (línea ~209):

```python
@_registrar("vix_complacency_exit",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: VIX en DEEP_COMPLACENCY/LOW_VOL → fin de euforia")
def _vix_complacency_exit(df):
    """VIX en DEEP_COMPLACENCY o LOW_VOL — complacencia extrema, fin de euforia."""
    vix_d1 = df["vix_sk"].dropna().str.split("__").str[0]
    mask = vix_d1.isin(["DEEP_COMPLACENCY", "LOW_VOL"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("credit_ease_exit",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: CREDIT sale de CREDIT_EASE/DEEP_CREDIT_EASE → fin de easing")
def _credit_ease_exit(df):
    """CREDIT NO está en CREDIT_EASE ni DEEP_CREDIT_EASE — fin del easing."""
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    mask = ~credit_d1.isin(["CREDIT_EASE", "DEEP_CREDIT_EASE"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("breadth_contraction_exit",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: BSI sale de EXPANSIVE/HYPER_EXPANSIVE → fin de expansión")
def _breadth_contraction_exit(df):
    """BSI NO está en EXPANSIVE_BREADTH ni HYPER_EXPANSIVE_BREADTH — fin de expansión."""
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    mask = ~bsi_d1.isin(["EXPANSIVE_BREADTH", "HYPER_EXPANSIVE_BREADTH"])
    return mask.reindex(df.index, fill_value=False)


@_registrar("regime_change_exit",
    validacion="PROPOSED", n_min=None, dsr=None,
    fuente="EXIT: Cambio de régimen VERANO→INVIERNO (credit_stress + vix_high + bsi_low)")
def _regime_change_exit(df):
    """Cambio de régimen: VERANO (credit_ease + vix_low + bsi_high) → INVIERNO (credit_stress + vix_high + bsi_low)."""
    credit_d1 = df["credit_sk"].dropna().str.split("__").str[0]
    vix_d1 = df["vix_sk"].dropna().str.split("__").str[0]
    bsi_d1 = df["bsi_sk"].dropna().str.split("__").str[0]
    invierno = (
        credit_d1.isin(["CREDIT_STRESS", "ELEVATED_CREDIT_STRESS", "CREDIT_CRISIS"]) &
        vix_d1.isin(["HIGH_VOL", "ELEVATED_PANIC", "CRISIS_SPIKE"]) &
        bsi_d1.isin(["BREADTH_WASHED_OUT", "OVERSOLD_BREADTH", "NEUTRAL_LOW_BREADTH"])
    )
    return invierno.reindex(df.index, fill_value=False)
```

### Tarea 2: Medir cada señal de EXIT
Ejecutar para cada una de las 4 señales:
```bash
cd /root/botero-trade
PYTHONPATH=/root/botero-trade .venv/bin/python research/01_señales_entry_exit/medir_senal.py --señal vix_complacency_exit
PYTHONPATH=/root/botero-trade .venv/bin/python research/01_señales_entry_exit/medir_senal.py --señal credit_ease_exit
PYTHONPATH=/root/botero-trade .venv/bin/python research/01_señales_entry_exit/medir_senal.py --señal breadth_contraction_exit
PYTHONPATH=/root/botero-trade .venv/bin/python research/01_señales_entry_exit/medir_senal.py --señal regime_change_exit
```

### Tarea 3: Guardar JSONs de medición
Los JSONs se guardan automáticamente en `research/01_señales_entry_exit/medicion_{señal}.json`.

## CRITERIOS DE ÉXITO
Una señal de EXIT es efectiva si:
1. **Edge ofensivo < -1%** (el mercado pierde >1% cuando se activa)
2. **WR < 40%** (predice pérdida >60% de las veces)
3. **CI95 no cruza cero** (significativo)
4. **Estable por década** (no cambia drásticamente)

## VERIFICACIÓN
```bash
# Verificar que las 4 señales se registraron
grep -c "@_registrar" research/01_señales_entry_exit/medir_senal.py
# Debe ser 20 (13 existentes + 3 EXIT existentes + 4 nuevas EXIT)

# Verificar que los JSONs se crearon
ls -la research/01_señales_entry_exit/medicion_vix_complacency_exit.json
ls -la research/01_señales_entry_exit/medicion_credit_ease_exit.json
ls -la research/01_señales_entry_exit/medicion_breadth_contraction_exit.json
ls -la research/01_señales_entry_exit/medicion_regime_change_exit.json
```

## PROHIBIDO
- ❌ NO modificar señales de ENTRY existentes
- ❌ NO tocar cascade_conviction
- ❌ NO modificar fact stores
- ❌ NO eliminar archivos existentes
- ❌ NO cambiar la estructura de directorios

## ENTREGABLES
1. `research/01_señales_entry_exit/medir_senal.py` (modificado, +4 señales)
2. `research/01_señales_entry_exit/medicion_vix_complacency_exit.json`
3. `research/01_señales_entry_exit/medicion_credit_ease_exit.json`
4. `research/01_señales_entry_exit/medicion_breadth_contraction_exit.json`
5. `research/01_señales_entry_exit/medicion_regime_change_exit.json`

---
**Firma:** Hermes (deepseek/deepseek-v4-flash)
**Fecha:** 19-Ago-2026