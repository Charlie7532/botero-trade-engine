# PROMPT PARA GEMINI — Reorganización de estructura y señales de EXIT

## CONTEXTO

Juan Andrés y Hermes están trabajando en señales de EXIT para Botero Trade. El sistema tiene 11 señales de ENTRY pero solo 2 de EXIT (euforia, fg_extreme_greed). La especificación dice: "No usar stops de PRECIO — stop de SEÑAL (el vector de estado dice 'peligro')".

## HALLAZGOS CLAVE

### Señales de EXIT evaluadas:
1. **bsi_recovery**: edge -1.63%, WR 29%, CI95 [-2.17%, -1.10%] ✅ **EFECTIVA**
   - Cuando BSI sale de BREADTH_WASHED_OUT → fin de la pierna alcista
   - Lookback crash: 100% de caídas tienen bsi_recovery activa

2. **vix_crisis_spike**: edge +0.75%, WR 57% ❌ Es ENTRY (comprar miedo)
3. **credit_stress_exit**: edge +1.00%, WR 55% ❌ Es ENTRY (comprar miedo)
4. **pcr_panic_exit**: edge +2.70%, WR 71% ❌ Es ENTRY (comprar pánico)
5. **dxy_spike_exit**: edge -0.04%, WR 46% ⚠️ Débil (no significativo)
6. **skew_paranoia_exit**: edge -0.38%, WR 46% ⚠️ Débil (no significativo)

### Conclusión:
Las señales de "pánico" son señales de ENTRY, no de EXIT. Solo **bsi_recovery** es efectiva como señal de EXIT.

## REORGANIZACIÓN DE ESTRUCTURA

### Problema:
- `scratch/` tiene archivos .md mezclados con código
- La información de inteligencia está dispersa
- No sigue Clean Architecture

### Solución:
Mover archivos .md de análisis a `backend/modules/entry_decision/references/`:

```bash
# Archivos a mover:
scratch/analisis_señales_exit.md → backend/modules/entry_decision/references/señales-exit.md
scratch/replanteamiento_señales_exit.md → backend/modules/entry_decision/references/señales-exit.md (append)
scratch/analisis_estadistico_profundo.md → backend/modules/entry_decision/references/cascade-conviction.md
```

### Estructura final:
```
botero-trade/
├── backend/
│   ├── modules/entry_decision/
│   │   └── references/              # Documentación técnica de METAR
│   │       ├── señales-exit.md      # Análisis de señales de EXIT
│   │       ├── cascade-conviction.md # Análisis estadístico profundo
│   │       └── metar-intelligence.md # Inteligencia general de METAR
│   └── references/                  # Documentación general
│       └── README.md                # Índice de documentación
└── scratch/                         # Solo scripts temporales (limpiar después)
```

## TAREAS PARA GEMINI

### Tarea 1: Reorganizar estructura
```bash
# Mover archivos de análisis
mv scratch/analisis_señales_exit.md backend/modules/entry_decision/references/señales-exit.md
mv scratch/replanteamiento_señales_exit.md backend/modules/entry_decision/references/señales-exit.md (append)
mv scratch/analisis_estadistico_profundo.md backend/modules/entry_decision/references/cascade-conviction.md

# Crear índice
touch backend/references/README.md
```

### Tarea 2: Implementar señales de EXIT efectivas
Implementar en `backend/modules/entry_decision/domain/rules/`:
- **bsi_recovery**: BSI sale de BREADTH_WASHED_OUT → BREADTH_RECOVERY o NEUTRAL_HIGH_BREADTH
- **vix_complacency_exit**: VIX en DEEP_COMPLACENCY o LOW_VOL (fin de euforia)
- **credit_ease_exit**: CREDIT sale de CREDIT_EASE o DEEP_CREDIT_EASE (fin de easing)
- **breadth_contraction_exit**: BSI sale de EXPANSIVE_BREADTH o HYPER_EXPANSIVE_BREADTH

### Tarea 3: Validar señales de EXIT
Para cada señal de EXIT:
- Medir edge ofensivo (forward return)
- Medir edge defensivo (pérdida evitada)
- Validar con bootstrap CI95
- Analizar estabilidad por década

## CRITERIOS DE ÉXITO

Una señal de EXIT es efectiva si:
- Edge ofensivo < -1% (el mercado pierde >1% cuando se activa)
- CI95 no cruza cero (significativo)
- WR < 40% (predice pérdida >60% de las veces)
- Estable por década (no cambia drásticamente)

## PROHIBIDO
- NO tocar señales de ENTRY existentes
- NO modificar cascade_conviction
- NO cambiar la estructura de fact stores
- NO usar stops de precio (solo stops de señal)

## VERIFICACIÓN
```bash
# Verificar que los archivos se movieron correctamente
ls -la backend/modules/entry_decision/references/

# Verificar que las señales de EXIT se implementaron
grep -r "bsi_recovery\|vix_complacency_exit\|credit_ease_exit\|breadth_contraction_exit" backend/modules/entry_decision/

# Ejecutar tests de señales de EXIT
PYTHONPATH=/root/botero-trade backend/.venv/bin/python scratch/medir_senal.py --señal bsi_recovery
```

---

**Firma:** qwen3.7-plus (Hermes)
**Fecha:** 18-Ago-2026
