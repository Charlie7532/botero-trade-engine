# 📊 INFORME DE DELTA BENCHMARK: VINTAGE V-B vs VINTAGE V-C (F5.2)

> **Fecha de Auditoría:** 2026-10-07 · **Git Base:** `dc39ba6`
> **Propósito:** Auditar el impacto de la homogeneización de datos post-rebuild (2026-10-04) separando el **Efecto Datos** del **Efecto Modelo**.

## 🔐 1. Firmas Criptográficas de Entradas (Inmutabilidad F5.2)

| Archivo de Entrada | Hash SHA-256 |
| :--- | :--- |
| `quants_obs_pkl` | `41b3323cda65d23435bbdcf91bb8f4416dc966511a8dbe211226347987ed9076` |
| `s5_triad_table_json` | `c52dd43a931d5e583fb3f6b77b753a86744b22a4594b8e3a34a5343d5ca74cd4` |
| `s5v_triad_table_json` | `e48eef9bf2f58d59047bf8b3a75c74f82d8f6489ad0fb82ae128b6e4e6cc3855` |
| `sv5_turbulence_fact_store_json` | `8f729a6045485379ff4e11d2dc58c442e76f55d92a1b4f82aa041315e7d96ca4` |
| `git_baseline_commit` | `dc39ba6` |
| `execution_timestamp` | `2026-10-07T15:44:47.067474+00:00` |

---

## 🔬 2. Brazo de Control A: Ventana Común (6,653 días, 2000-01-03 a 2026-06-16)

_Al evaluar exactamente la misma ventana temporal de V-B sobre los datos curados de V-C, se aísla con rigor científico el impacto exclusivo de la limpieza de datos._

| Versión | Acciones V-B (Datos Contaminados) | Acciones V-C (Datos Curados EMA5) | Delta Efecto Datos | Max Drawdown V-B | Max Drawdown V-C |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **V40 Baseline** | `459.36` | **`473.31`** | **`+13.95 acc (+3.04%)`** 🔥 | `-42.74%` | **`-42.74%`** |
| **V41 Auditada** | `426.89` | **`422.22`** | ` -4.67 acc (-1.09%)` | `-41.97%` | **`-41.97%`** |
| **Delta V41 vs V40** | `-32.46 acc` | `-51.09 acc` | - | `+0.77pp (Mejora)` | `+0.77pp (Mejora)` |

**Hallazgo Científico Clave:** La limpieza de las 14 series `*_TW` (sustitución de SMA5 por EMA5 y corrección de barras parciales) aporta **+13.95 acciones SPY adicionales (+3.04%)** al baseline V40 en el horizonte idéntico de 6,653 días.

---

## 📈 3. Extensión Completa Vintage V-C (6,730 días, 2000-01-03 a 2026-10-06)

| Métrica Global | Versión 40 (Baseline V-C) | Versión 41 (Auditada V-C) | SPY Benchmark | Delta V41 vs V40 |
| :--- | :---: | :---: | :---: | :---: |
| **Acciones SPY Finales** | **`460.87`** | **`411.12`** | `100.00` | **`-49.75 acc`** |
| **Equity Final ($100 Init)** | **`$359,056.27`** | **`$320,299.91`** | - | **`$-38,756.35`** |
| **Max Drawdown** | **`-42.74%`** | **`-41.97%`** | `-55.19%` | **`+0.77pp`** (Mejora Preservada) |
| **Protección Contingencia** | `96.9%` | **`96.9%`** | `0.0%` | Mantienen igual |

---

## 🏛️ 4. Desglose por Régimen de Mercado (Vintage V-C, 6,730 días)

| Régimen de Mercado | Días Totales | Ret. V40 (%) | Ret. V41 (%) | Delta Ret (%) | Win Rate (%) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`MERCADO_SANO`** | 4,322 | +854.61% | +854.61% | **+0.00%** | 55.3% | 1.21 |
| **`DISTRIBUCION_PRE_CRASH`** | 806 | +16.60% | +16.60% | **+0.00%** | 52.5% | 1.09 |
| **`PISO_GENERACIONAL`** | 623 | +188.88% | +188.88% | **+0.00%** | 53.0% | 1.24 |
| **`RE_ACUMULACION_ALCISTA`** | 524 | +29.78% | +25.04% | **-4.74%** | 53.9% | 1.25 |
| **`NORMAL`** | 211 | -0.47% | -0.47% | **+0.00%** | 52.0% | 1.02 |
| **`PULLBACK_ALCISTA`** | 97 | +14.41% | +14.41% | **+0.00%** | 64.4% | 2.08 |
| **`RECUPERACION`** | 95 | +14.87% | +9.98% | **-4.89%** | 50.6% | 1.22 |
| **`CRASH_SISTEMICO`** | 52 | +0.00% | +0.00% | **+0.00%** | 0.0% | 1.00 |
