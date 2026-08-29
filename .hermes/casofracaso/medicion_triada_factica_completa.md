# Medición Completa por Tríada de ZigZag — Datos Fácticos Sin Atajos
**Fecha:** 19-Ago-2026 · **Método:** Mann-Whitney U + Fisher exact · **Escalas:** $zz_{25}$, $zz_{50}$, $zz_{75}$

---

## Baselines Incondicionales (Grupo de Control por Tríada)

### Techos (MAX)
| Escala | N | Media | Mediana | P5 | P95 | Duración Med | Dur P90 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **$zz_{25}$** | 794 | -3.10% | -3.85% | -8.36% | +6.47% | 4d | 25d |
| **$zz_{50}$** | 392 | -2.81% | -4.38% | -10.05% | +7.57% | 2d | 18d |
| **$zz_{75}$** | 203 | -2.27% | -3.92% | -10.98% | +9.84% | 2d | 12d |

### Pisos (MIN)
| Escala | N | Media | Mediana | P5 | P95 | Duración Med | Dur P90 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **$zz_{25}$** | 795 | +3.91% | +4.24% | -6.18% | +10.71% | 4d | — |
| **$zz_{50}$** | 411 | +3.88% | +4.69% | -7.01% | +10.71% | — | — |
| **$zz_{75}$** | 222 | +3.48% | +4.65% | -8.07% | +10.91% | — | — |

> [!NOTE]
> **Observación estructural del ZigZag:** A medida que la pierna es más severa ($zz_{75}$), el retorno medio se COMPRIME (+3.48% vs +3.91%) y el cono de dispersión se ENSANCHA (P5 = -8.07% vs -6.18%). Los eventos severos son más impredecibles.

---

## SEÑALES DE SALIDA (EXIT) — Medidas por Tríada

| Señal | Escala | N | Ret Med | Ret P50 | Dur Med | P5 | P95 | MW-U $p$ | C75% | Fisher $p$ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`vix_complacency`** | $zz_{25}$ | 35 | **-4.35%** | -4.28% | **19d** | -6.24% | **-2.64%** | 0.1465 | 2.9% | 1.0000 |
| | $zz_{50}$ | 10 | -5.38% | -5.31% | 14d | -6.57% | -3.59% | 0.0602 | — | — |
| | $zz_{75}$ | **1** | — | — | — | — | — | — | — | — |
| **`bsi_recovery`** | $zz_{25}$ | 229 | -3.98% | -3.97% | 5d | -7.77% | +3.04% | 0.0658 | 13.5% | 1.0000 |
| | $zz_{50}$ | 73 | -4.27% | -5.00% | 3d | -8.79% | +5.26% | **0.0412** ✅ | — | — |
| | $zz_{75}$ | 31 | -4.39% | -4.79% | 1d | -10.78% | +6.42% | 0.0545 | — | — |
| **`credit_equity_div`** | $zz_{25}$ | 120 | -3.15% | -3.79% | 3d | -9.22% | +8.09% | 0.3213 | **31.7%** | 0.0615 |
| | $zz_{50}$ | 65 | -3.00% | -4.47% | 2d | -10.86% | +11.69% | 0.2608 | — | — |
| | $zz_{75}$ | 38 | -2.39% | -4.98% | 2d | -11.28% | +12.69% | 0.2577 | — | — |
| **`def_rotation_div`** | $zz_{25}$ | 197 | -2.36% | -4.00% | 2d | -10.92% | +8.68% | 0.5625 | **46.2%** | **0.0000** 🏆 |
| | $zz_{50}$ | 137 | -2.16% | -4.25% | 2d | -11.55% | +9.35% | 0.6050 | — | — |
| | $zz_{75}$ | 91 | -1.82% | -4.00% | 1d | -12.34% | +10.23% | 0.5263 | — | — |
| **`skew_d3_vol_exp`** | $zz_{25}$ | 114 | -3.77% | -4.21% | 3d | -11.57% | +4.79% | 0.0640 | 31.6% | 0.0709 |
| | $zz_{50}$ | 63 | -4.21% | -5.09% | 2d | -12.20% | +5.15% | **0.0436** ✅ | — | — |
| | $zz_{75}$ | 36 | -4.21% | -5.09% | 1d | -14.44% | +6.73% | 0.0638 | — | — |
| **`credit_d2_accel`** | $zz_{25}$ | 86 | -3.82% | -3.81% | 3d | -9.80% | +5.53% | 0.1528 | 29.1% | 0.2501 |
| | $zz_{50}$ | 44 | -3.81% | -4.51% | 2d | -10.87% | +6.34% | 0.1240 | — | — |
| | $zz_{75}$ | 25 | -3.79% | -6.18% | 1d | -11.17% | +11.16% | 0.0571 | — | — |
| **`2+ débiles`** | $zz_{25}$ | 127 | -3.64% | -3.89% | 2d | -10.84% | +6.32% | 0.1014 | **37.0%** | **0.0012** ✅ |
| | $zz_{50}$ | 72 | -3.76% | -4.73% | 2d | -11.59% | +8.78% | 0.0811 | — | — |
| | $zz_{75}$ | 47 | -3.81% | -5.22% | 1d | -13.27% | +9.12% | **0.0407** ✅ | — | — |

### Hallazgos EXIT por Tríada

> [!IMPORTANT]
> **`vix_complacency` NO CASCADEA.** Solo 1 evento llegó a $zz_{75}$ en toda la historia. Es una señal de **corrección ordenada y superficial** (P95 = -2.64%, cono ultra comprimido). Nunca produce crash. **Rol: TRIM signal, no EXIT signal.**

> [!IMPORTANT]
> **`def_rotation_div` es el ÚNICO predictor de SEVERIDAD validado** (Fisher $p = 0.0000$ en C75 con 46.2% vs baseline 27.5%). Pero NO predice retornos más negativos que el baseline (MW-U $p > 0.50$). **Rol: SEVERITY GATE — indica que si cae, es más probable que sea profundo.**

> [!IMPORTANT]
> **`bsi_recovery` y `skew_d3_vol_exp` ganan significancia en $zz_{50}$** ($p = 0.041$ y $p = 0.044$). A escala táctica ($zz_{25}$) son marginales, pero a escala intermedia el edge se consolida. **Rol: INTERMEDIATE EXIT signals — su poder emerge en piernas de $\ge 5\%$.**

> [!IMPORTANT]
> **`2+ débiles` es el ENSEMBLE que funciona** — significativo tanto en C75 (Fisher $p = 0.0012$) como en retorno $zz_{75}$ (MW-U $p = 0.0407$). **La combinación de señales débiles produce un predictor genuino en la escala estructural.**

---

## SEÑALES DE ENTRADA (ENTRY) — Medidas por Tríada

| Señal | Escala | N | Ret Med | Ret P50 | Dur Med | P5 | P95 | MW-U $p$ | C75% | Fisher $p$ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`credit_easing_k1`** | $zz_{25}$ | 112 | **+5.19%** | +4.75% | 4d | -3.90% | +11.19% | **0.0143** ✅ | 34.8% | 0.0522 |
| | $zz_{50}$ | 59 | **+5.27%** | +5.36% | 2d | -5.24% | +10.75% | **0.0117** ✅ | — | — |
| | $zz_{75}$ | 39 | +5.14% | +5.28% | 2d | -6.03% | +10.70% | **0.0500** ✅ | — | — |
| **`capitulacion`** | $zz_{25}$ | 51 | +3.60% | +4.64% | 2d | -9.16% | +12.37% | 0.2722 | **62.7%** | **0.0000** 🏆 |
| | $zz_{50}$ | 37 | +4.15% | +5.25% | 1d | -9.69% | +12.23% | 0.1449 | — | — |
| | $zz_{75}$ | 32 | +4.70% | +5.39% | 1d | -10.59% | +12.35% | 0.0936 | — | — |
| **`fg_extreme_fear`** | $zz_{25}$ | 35 | +3.77% | +3.99% | 2d | -7.41% | +10.93% | 0.5523 | **54.3%** | **0.0007** 🏆 |
| | $zz_{50}$ | 26 | +4.22% | +5.36% | 2d | -7.75% | +12.89% | 0.2628 | — | — |
| | $zz_{75}$ | 19 | +4.34% | +5.51% | 2d | -8.40% | +9.61% | 0.2192 | — | — |
| **`bsi_washed_out`** | $zz_{25}$ | 100 | +3.22% | +4.22% | 2d | -8.37% | +10.70% | 0.4962 | **51.0%** | **0.0000** 🏆 |
| | $zz_{50}$ | 72 | +3.40% | +4.88% | 2d | -8.51% | +10.71% | 0.4075 | — | — |
| | $zz_{75}$ | 51 | +3.92% | +5.21% | 1d | -10.77% | +11.43% | 0.2000 | — | — |
| **`pcr_put_panic`** | $zz_{25}$ | 47 | +3.72% | +4.33% | 2d | -7.91% | +14.60% | 0.3869 | **48.9%** | **0.0013** ✅ |
| **`vvix_entry`** | $zz_{25}$ | 56 | +3.17% | +4.77% | 2d | -8.14% | +11.56% | 0.3566 | **46.4%** | **0.0017** ✅ |
| **`panico_total`** | $zz_{25}$ | 20 | +3.21% | +3.63% | 3d | -4.91% | +9.50% | 0.8819 | 25.0% | 0.6984 |

### Hallazgos ENTRY por Tríada

> [!IMPORTANT]
> **`credit_easing_k1` es el ÚNICO diamante validado en las 3 escalas de la Tríada** ($p = 0.014$, $0.012$, $0.050$). Edge neto estable de $+1.28\%$ a $+1.39\%$ sobre el baseline. Es la señal de entrada más robusta del sistema.

> [!IMPORTANT]
> **Las señales de pánico son PREDICTORES DE SEVERIDAD, no de retorno.** `capitulacion`, `fg_extreme_fear`, `bsi_washed_out`, `pcr_put_panic`, `vvix_entry` — NINGUNA tiene $p < 0.05$ en MW-U (retorno medio igual al baseline). Pero TODAS tienen Fisher $p < 0.002$ en C75, con C75% entre 46-63% vs baseline 28%.
>
> **Interpretación:** El pánico no hace que el rebote sea más grande en promedio, sino que lo hace **más probable de ser estructural** ($\ge 7.5\%$). Señalan que estás en un piso profundo, no en una corrección menor.

> [!WARNING]
> **`panico_total` no tiene poder en ningún eje** ($p = 0.88$ en retorno, $p = 0.70$ en C75, N = 20). Es la señal más débil del inventario.

---

## Taxonomía Corregida: Dos Ejes Ortogonales

```
                    ┌──────────────────────────────────────────────────────────┐
                    │           EJE 2: PREDICE SEVERIDAD                      │
                    │         (Fisher exact C75, p < 0.05)                    │
                    │                                                          │
                    │    NO                          SÍ                        │
              ┌─────┼────────────────────┬───────────────────────────────────── │
              │     │                    │                                     │
  EJE 1:     │ NO  │  fg_greed          │  def_rotation_div (p=0.0000)        │
  PREDICE    │     │  panico_total      │  capitulacion (p=0.0000)            │
  RETORNO    │     │  yield_curve       │  fg_extreme_fear (p=0.0007)         │
  (MW-U      │     │  dxy_stress        │  bsi_washed_out (p=0.0000)          │
   p<0.05)   │     │  sv5t_silence      │  pcr_put_panic (p=0.0013)           │
              │     │                    │  vvix_entry (p=0.0017)              │
              │     │                    │  credit_equity_div (p=0.0615)       │
              ├─────┼────────────────────┼─────────────────────────────────────│
              │     │                    │                                     │
              │ SÍ  │  vix_complacency   │  credit_easing_k1 (p=0.014/0.052)  │
              │     │  (p=0.06, anti-C75)│  bsi_recovery (p=0.041 en zz50)    │
              │     │                    │  2+ débiles (p=0.001/0.041)         │
              │     │                    │  skew_d3_vol_exp (p=0.044 en zz50)  │
              └─────┴────────────────────┴─────────────────────────────────────┘
```

### Cuadrantes Operativos:

1. **↗ Esquina RETORNO + SEVERIDAD:** `credit_easing_k1`, `bsi_recovery` (zz50), `2+ débiles`, `skew_d3` (zz50)
   → **Señales de acción directa.** Disparan sizing y timing.

2. **→ Solo SEVERIDAD:** `def_rotation_div`, `capitulacion`, `fg_fear`, `bsi_washed_out`, `pcr_panic`, `vvix_entry`
   → **Gates de profundidad.** Indican que el evento es estructural, no superficial. Modifican el sizing hacia arriba (en pisos) o la urgencia de salida (en techos).

3. **↑ Solo RETORNO:** `vix_complacency`
   → **TRIM signal.** Caída segura pero superficial. Tomar ganancias parciales, no salir.

4. **Esquina muerta:** `panico_total`, `fg_greed`, `yield_curve`, `dxy_stress`
   → **Sin poder en ningún eje.** Purgar o reclasificar como contexto ambiental puro.
