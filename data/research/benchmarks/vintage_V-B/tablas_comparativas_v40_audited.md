<!-- VINTAGE_METADATA_HEADER -->
> [!WARNING]
> **VINTAGE V-B (PRE-HOMOGENEIZACIÓN) — NO COMPARABLE DIRECTAMENTE CON V-C**
> **Motivo medido:** Datos generados con series tácticas híbridas SMA5/EMA5 en las 14 series `*_TW`, barras parciales previas al rebuild de 2026-10-04, y piernas SPY desalineadas.
> **Ventana declarada:** 2000-01-03 a 2026-06-16 (6.653 días de trading en V41/V40).
> **Propósito:** Registro histórico inmutable de auditoría para preservación de evidencia empírica (F5.1).
<!-- END_VINTAGE_METADATA_HEADER -->

# 📊 REPORTES DE BENCHMARK MAESTRO V40 — AUDITORÍA INTEGRAL (2000 - 2026)

> [!IMPORTANT]
> Este informe consolida la auditoría cuantitativa del **Quality Entry Gate V40** ejecutado sobre el histórico continuo de 26.5 años (6,653 días de mercado, 2000–2026).
> Incorpora la arquitectura **Vault-First** con contingencia **SV5_SHOCK** para protección anti-fallos en episodios de degradación de data macro/VIX.

## 📈 Summary de Performance Global

| Métrica | V40 Estándar (VIX + SV5_SHOCK) | V40 Contingencia (Sin VIX) | SPY Benchmark | Audit Diff |
| :--- | :---: | :---: | :---: | :---: |
| **Acciones SPY Finales** | **`459.36`** | **`456.76`** | `100.00` | `+2.59 acc` |
| **Equity Final** | **`$353,539.47`** | **`$351,544.09`** | - | - |
| **Max Drawdown** | **`-42.74%`** | **`-52.42%`** | `-55.19%` | `-9.68%` |
| **Recovery vs Sin Fallback** | **`100.0%`** | **`100.6%`** | `0.0%` | **96.9% Protegido** |

---

## 🏛️ 1. Desglose por Régimen de Mercado (Modo Estándar V40)

_Cálculo auditado mediante Episode-Aware Compounding (compuesto intra-episodio continuo)._

| Régimen de Mercado | Días Totales | Episodios | Ret. Acumulado (%) | Win Rate Diario (%) | Profit Factor | Ret. Promedio Diario (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`MERCADO_SANO`** | 4,322 | 103 | **+837.22%** | 55.3% | 1.21 | **+0.0564%** |
| **`DISTRIBUCION_PRE_CRASH`** | 804 | 269 | **+15.22%** | 52.3% | 1.08 | **+0.0329%** |
| **`PISO_GENERACIONAL`** | 623 | 25 | **+188.88%** | 53.0% | 1.24 | **+0.2179%** |
| **`RE_ACUMULACION_ALCISTA`** | 524 | 269 | **+29.78%** | 53.9% | 1.28 | **+0.1097%** |
| **`NORMAL`** | 211 | 33 | **-0.47%** | 52.0% | 1.02 | **+0.0129%** |
| **`PULLBACK_ALCISTA`** | 97 | 38 | **+14.41%** | 64.4% | 2.08 | **+0.2316%** |
| **`RECUPERACION`** | 95 | 10 | **+14.87%** | 50.6% | 1.29 | **+0.1810%** |
| **`CRASH_SISTEMICO`** | 52 | 19 | **+0.00%** | 0.0% | 1.00 | **+0.0000%** |

---

## 🛡️ 2. Desglose por Régimen de Mercado (Modo Contingencia Sin VIX)

_Evaluación con VIX deshabilitado (usando SV5_SHOCK ≤ 10.0 desde Vault)._

| Régimen de Mercado | Días Totales | Episodios | Ret. Acumulado (%) | Win Rate Diario (%) | Profit Factor | Ret. Promedio Diario (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`MERCADO_SANO`** | 4,321 | 103 | **+813.37%** | 55.3% | 1.21 | **+0.0558%** |
| **`DISTRIBUCION_PRE_CRASH`** | 820 | 271 | **+14.39%** | 52.5% | 1.08 | **+0.0309%** |
| **`PISO_GENERACIONAL`** | 658 | 26 | **+264.33%** | 52.4% | 1.27 | **+0.2445%** |
| **`RE_ACUMULACION_ALCISTA`** | 524 | 269 | **+29.78%** | 53.9% | 1.28 | **+0.1097%** |
| **`NORMAL`** | 248 | 35 | **+2.73%** | 51.4% | 1.05 | **+0.0277%** |
| **`PULLBACK_ALCISTA`** | 97 | 38 | **+14.41%** | 64.4% | 2.08 | **+0.2316%** |
| **`RECUPERACION`** | 45 | 9 | **+18.75%** | 52.8% | 2.03 | **+0.4980%** |
| **`CRASH_SISTEMICO`** | 15 | 8 | **+0.00%** | 0.0% | 1.00 | **+0.0000%** |

---

## 📅 3. Desglose Año por Año (2000 - 2026)

| Año | Rendimiento V40 (%) | Rendimiento SPY (%) | Alpha Neto (%) | Acciones SPY al Cierre |
| :---: | :---: | :---: | :---: | :---: |
| **2000** | **-0.29%** | -8.85% | **+8.56%** | **124.09** |
| **2001** | **+12.36%** | -10.13% | **+22.50%** | **152.80** |
| **2002** | **-17.64%** | -22.42% | **+4.78%** | **162.87** |
| **2003** | **+27.04%** | +24.18% | **+2.85%** | **166.46** |
| **2004** | **+8.27%** | +10.75% | -2.48% | **162.46** |
| **2005** | **+4.60%** | +5.32% | -0.73% | **160.74** |
| **2006** | **+10.27%** | +13.84% | -3.58% | **154.80** |
| **2007** | **+3.25%** | +5.33% | -2.08% | **152.41** |
| **2008** | **-8.33%** | -36.24% | **+27.90%** | **217.36** |
| **2009** | **+32.27%** | +22.65% | **+9.61%** | **238.51** |
| **2010** | **+12.78%** | +13.14% | -0.36% | **237.31** |
| **2011** | **-0.75%** | +0.85% | -1.60% | **234.28** |
| **2012** | **+21.83%** | +14.17% | **+7.66%** | **250.72** |
| **2013** | **+31.02%** | +29.00% | **+2.02%** | **255.21** |
| **2014** | **+12.68%** | +14.56% | -1.89% | **251.39** |
| **2015** | **+15.82%** | +1.29% | **+14.53%** | **288.13** |
| **2016** | **+2.41%** | +13.59% | -11.17% | **258.43** |
| **2017** | **+18.97%** | +20.78% | -1.81% | **254.91** |
| **2018** | **-4.19%** | -5.25% | **+1.06%** | **256.23** |
| **2019** | **+28.52%** | +31.09% | -2.57% | **253.33** |
| **2020** | **+44.97%** | +17.24% | **+27.74%** | **313.87** |
| **2021** | **+26.02%** | +30.51% | -4.48% | **303.16** |
| **2022** | **+0.04%** | -18.65% | **+18.68%** | **373.53** |
| **2023** | **+30.11%** | +26.71% | **+3.40%** | **384.11** |
| **2024** | **+27.44%** | +25.59% | **+1.86%** | **390.31** |
| **2025** | **+43.14%** | +18.01% | **+25.13%** | **474.71** |
| **2026** | **+9.46%** | +13.54% | -4.08% | **459.36** |

---

## 🔬 Especificaciones de Fórmulas y Verificación Anti-Sesgo

| Métrica Auditada | Definición Matemática | Control Anti-Sesgo / Verificación |
| :--- | :--- | :--- |
| **Ret. Acumulado por Régimen** | `∏ (1 + R_episode) - 1` | Elimina la falsa multiplicación entre episodios separados por años |
| **Win Rate Diario** | `N_positive_days / N_intra_episode_days` | Descuenta días de transición (t_0 = 0%) para evitar dilución |
| **Rendimiento Anual V40** | `(Equity_end / Equity_start) - 1` | Retorno discreto de capital auditado contra el benchmark SPY |
| **Acciones SPY Compuestas** | `Equity_t / Price_SPY_t` | Medida de unidades absolutas de poder adquisitivo acumulado |
| **Contingencia SV5_SHOCK** | `std(Δ_SV5TW, 10d) ≤ 10.0` | Fallback empírico en la V36 redirect que preserva el 96.9% de protección |
