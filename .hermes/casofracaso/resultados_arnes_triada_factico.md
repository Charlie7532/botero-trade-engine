# Validación Cruzada: Historia vs Prospección
**Fecha:** 19-Ago-2026 · **Fuentes:** quants_obs (historia) + fact store zigzag_kinematic (prospección)

---

## El Principio Fundamental

| Instrumento | Dirección | Qué contiene | Para qué sirve |
|---|:---:|---|---|
| **quants_obs** | ← ATRÁS | Registro de cada pivote ZigZag: qué estado tenía, qué retorno tuvo la pierna siguiente | **Validación:** ¿la señal funcionó históricamente? |
| **Fact Store** (zigzag_kinematic) | → ADELANTE | $p_{bull}$, $E[ret_{max}]$, $E[ret_{min}]$, $EV_{net}$, $E[days]$ por estado D1\_\_D2\_\_D3 | **Decisión:** ¿qué espero que pase AHORA? |

> [!IMPORTANT]
> **Son complementarias, no sustitutas.** La historia valida que la prospección sea correcta. La prospección provee las probabilidades y esperanza matemática para operar en producción.

---

## Resultados de la Validación Cruzada

### ✅ Señales CONSISTENTES (Historia ↔ Prospección coinciden)

| Señal | Escala | HIST WR | PROSP $p_{bear/bull}$ | HIST Ret | PROSP EV | Δ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **`vix_complacency`** | zz25 | 100% bear | 87.5% bear | -4.35% | **-1.30%** | ⚠️ 12% |
| | zz50 | 100% bear | **100% bear** | -5.38% | **-2.45%** | ✅ 0% |
| **`fg_extreme_greed`** | zz25 | 92% bear | 85.7% bear | -3.32% | **-1.22%** | ✅ 6% |
| **`bsi_recovery`** | zz50 | 90.4% bear | 83.3% bear | -4.27% | **-3.62%** | ✅ 7% |
| | zz75 | 87.1% bear | 92.1% bear | -4.39% | **-4.37%** | ✅ 5% |
| **`bsi_washed_out`** | zz50 | 77.8% bull | 71.0% bull | +3.40% | **+2.72%** | ✅ 7% |
| | zz75 | 80.4% bull | 77.2% bull | +3.92% | **+5.59%** | ✅ 3% |
| **`vvix_extreme`** | zz50 | 71.4% bull | 63.9% bull | +3.16% | **+1.83%** | ✅ 7% |
| | zz75 | 76.9% bull | 72.4% bull | +4.02% | **+3.11%** | ✅ 5% |
| **`pcr_put_panic`** | zz25 | 78.7% bull | 70.8% bull | +3.72% | **+0.02%** | ✅ 8% |
| **`fg_extreme_fear`** | zz50 | 80.8% bull | 73.7% bull | +4.22% | **+1.45%** | ✅ 7% |
| **`vix_crisis`** (ENTRY) | zz75 | 73.3% bull | 63.6% bull | +3.32% | **+1.93%** | ✅ 10% |

### ❌ Señales con DIVERGENCIA (Historia ≠ Prospección, Δ > 20%)

| Señal | Escala | HIST WR | PROSP $p_{bear/bull}$ | Δ | Diagnóstico |
|---|:---:|:---:|:---:|:---:|---|
| **`def_rotation_div`** | zz25 | 70.5% bear | **44.9% bear** | **26%** | Sesgo pivot_type: HIST filtra MAX, PROSP no |
| | zz50 | 65.1% bear | 38.6% bear | 26% | |
| | zz75 | 59.8% bear | 35.3% bear | 24% | |
| **`rot_d2_crush`** | zz50 | 52.2% bear | 22.6% bear | 30% | Misma causa |
| | zz75 | 57.9% bear | 25.0% bear | 33% | |
| **`vix_crisis`** (EXIT) | zz50 | 61.8% bear | 40.9% bear | 21% | VIX crisis = pisos, no techos |
| | zz75 | 63.0% bear | 36.4% bear | 27% | |
| **`skew_d3_vol_exp`** | zz25 | 82.5% bear | 48.8% bear | 34% | PROSP incluye MIN+MAX |
| | zz50 | 77.8% bear | 48.6% bear | 29% | |
| **`bsi_recovery`** | zz25 | 94.3% bear | 69.5% bear | 25% | PROSP incluye MIN+MAX |

---

## Diagnóstico de las Divergencias

> [!CAUTION]
> **La divergencia tiene UNA causa raíz:** quants_obs filtra por `pivot_type` (solo MAX para EXIT, solo MIN para ENTRY), pero el fact store zigzag_kinematic cuenta TODAS las piernas ZigZag donde el estado estaba activo, **sin importar si el día era un pivote MAX o MIN.**
>
> Esto crea un sesgo sistemático:
> - **HIST dice 70.5% bear** porque solo mira pivotes MAX (que por definición del ZigZag son seguidos por caídas 83% del tiempo)
> - **PROSP dice 44.9% bear** porque incluye también los días NO-pivote y los MIN (que son seguidos por subidas)
>
> **Ninguno está "mal".** Miden cosas diferentes:
> - HIST responde: *"Si HOY es un techo ZigZag Y el estado es X, ¿qué pasa?"*
> - PROSP responde: *"Si HOY el estado es X (sin saber si es techo o piso), ¿qué pasa?"*

---

## Implicación para el Engine

```
CEILING ENGINE (EXIT):
  1. Lee el estado actual D1__D2__D3 → Fact Store (PROSP)
  2. Pregunta: ¿estamos en un pivote MAX? → ZigZag detector  
  3. Si es MAX + estado bearish → AMBAS fuentes coinciden → ALTA CONVICCIÓN
  4. Si NO es MAX + estado bearish → solo PROSP dice bear → BAJA CONVICCIÓN
  
  Las señales CONSISTENTES (vix_complacency, fg_greed, bsi_recovery)
  funcionan INDEPENDIENTEMENTE de si es pivote → son las más valiosas
  
  Las señales DIVERGENTES (def_rotation, skew_d3) solo funcionan
  CUANDO ya estás en un pivote MAX → son CONDICIONADAS al contexto
```

> [!IMPORTANT]
> **Conclusión operacional:** El Ceiling/Floor Engine debe tener DOS capas:
> 1. **Capa incondicional:** Señales que funcionan sin saber si es pivote (`vix_complacency`, `fg_greed`, `bsi_recovery`, `pcr_panic`, `vvix_extreme`)
> 2. **Capa condicional:** Señales que solo funcionan dado que el ZigZag detector ya confirmó un pivote (`def_rotation`, `skew_d3`, `rot_d2_crush`)
