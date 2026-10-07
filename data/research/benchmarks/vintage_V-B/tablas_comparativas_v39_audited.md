<!-- VINTAGE_METADATA_HEADER -->
> [!WARNING]
> **VINTAGE V-B (PRE-HOMOGENEIZACIÓN) — NO COMPARABLE DIRECTAMENTE CON V-C**
> **Motivo medido:** Datos generados con series tácticas híbridas SMA5/EMA5 en las 14 series `*_TW`, barras parciales previas al rebuild de 2026-10-04, y piernas SPY desalineadas.
> **Ventana declarada:** 2000-01-03 a 2026-06-16 (6.653 días de trading en V41/V40).
> **Propósito:** Registro histórico inmutable de auditoría para preservación de evidencia empírica (F5.1).
<!-- END_VINTAGE_METADATA_HEADER -->

# 📊 BENCHMARK MAESTRO V39 — Fórmulas Auditadas (2000 - 2026)

> [!IMPORTANT]
> Todas las fórmulas han sido auditadas para eliminar el bug de composición cruzada entre episodios no contiguos.

**Acciones SPY Compuestas Finales**: **`1044.21`**
**Max Drawdown**: `-39.21%`
**Días de Simulación**: `6,683`

## 🏛️ 1. Tabla por Régimen de Mercado (Episode-Aware Compounding)

| Régimen | Días | Episodios | Ret. Acumulado (%) | Win Rate Diario (%) | Profit Factor | Ret. Promedio Diario (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`MERCADO_SANO`** | 4,327 | 104 | **+747.28%** | 55.4% | 1.20 | **+0.0540%** |
| **`DISTRIBUCION_PRE_CRASH`** | 811 | 263 | **+19.43%** | 52.6% | 1.10 | **+0.0387%** |
| **`PISO_GENERACIONAL`** | 600 | 24 | **+202.23%** | 53.1% | 1.25 | **+0.2334%** |
| **`RE_ACUMULACION_ALCISTA`** | 498 | 259 | **+38.39%** | 52.7% | 1.37 | **+0.1432%** |
| **`NORMAL`** | 172 | 32 | **-1.23%** | 53.2% | 1.01 | **+0.0093%** |
| **`RECUPERACION`** | 126 | 10 | **+27.38%** | 50.0% | 1.45 | **+0.2226%** |
| **`PULLBACK_ALCISTA`** | 100 | 39 | **+17.41%** | 67.2% | 2.29 | **+0.2667%** |
| **`CRASH_SISTEMICO`** | 49 | 18 | **+0.00%** | 0.0% | 1.00 | **+0.0000%** |

---

## 📅 2. Tabla Año por Año

| Año | Rendimiento V39 (%) | Rendimiento SPY (%) | Alpha Neto (%) | Acciones SPY al Cierre |
| :---: | :---: | :---: | :---: | :---: |
| **2000** | **-1.77%** | -9.80% | **+8.03%** | **123.93** |
| **2001** | **+13.11%** | -11.27% | **+24.38%** | **155.58** |
| **2002** | **-10.02%** | -23.63% | **+13.61%** | **184.04** |
| **2003** | **+28.18%** | +22.19% | **+5.98%** | **194.05** |
| **2004** | **+8.71%** | +8.67% | **+0.04%** | **193.79** |
| **2005** | **+4.56%** | +3.50% | **+1.06%** | **195.07** |
| **2006** | **+13.89%** | +11.78% | **+2.11%** | **197.61** |
| **2007** | **+5.39%** | +3.42% | **+1.96%** | **202.24** |
| **2008** | **-1.22%** | -37.74% | **+36.52%** | **318.44** |
| **2009** | **+42.45%** | +19.88% | **+22.57%** | **385.04** |
| **2010** | **+12.30%** | +10.96% | **+1.34%** | **388.96** |
| **2011** | **+0.07%** | -1.22% | **+1.29%** | **395.28** |
| **2012** | **+21.93%** | +11.70% | **+10.23%** | **432.76** |
| **2013** | **+29.95%** | +26.45% | **+3.51%** | **445.76** |
| **2014** | **+12.56%** | +12.37% | **+0.20%** | **447.21** |
| **2015** | **+12.76%** | -0.76% | **+13.52%** | **509.35** |
| **2016** | **+1.73%** | +11.20% | -9.46% | **465.74** |
| **2017** | **+17.87%** | +18.48% | -0.61% | **463.99** |
| **2018** | **-4.23%** | -7.01% | **+2.78%** | **475.05** |
| **2019** | **+27.28%** | +28.65% | -1.38% | **473.97** |
| **2020** | **+43.86%** | +15.09% | **+28.78%** | **593.61** |
| **2021** | **+27.15%** | +28.79% | -1.64% | **586.17** |
| **2022** | **-2.32%** | -19.95% | **+17.62%** | **716.66** |
| **2023** | **+33.86%** | +24.81% | **+9.05%** | **769.72** |
| **2024** | **+29.27%** | +24.00% | **+5.27%** | **803.52** |
| **2025** | **+40.27%** | +16.64% | **+23.63%** | **968.91** |
| **2026** | **+14.63%** | +6.78% | **+7.86%** | **1044.21** |

---

## 🔬 Auditoría de Fórmulas

| Métrica | Fórmula Anterior (Bug) | Fórmula Corregida |
| :--- | :--- | :--- |
| **Ret. Acumulado por Régimen** | `np.prod(1 + daily_ret_all_days)` — mezcla días no contiguos | `prod(1 + episode_ret)` por episodio continuo |
| **Daily Ret por Régimen** | `equity.pct_change()` — primer día de episodio captura salto inter-régimen | `intra_ret` = solo cambios dentro del mismo episodio |
| **Ret. Anual V39** | `np.prod(1 + daily_ret)` — acumula errores de pct_change | `(equity_last / equity_first - 1)` = ratio directo |
| **Win Rate** | Denominador = días con ret ≠ 0 | Denominador = todos los días intra-episodio |
