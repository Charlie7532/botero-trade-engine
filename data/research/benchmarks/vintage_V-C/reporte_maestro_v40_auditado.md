# 📊 REPORTES DE BENCHMARK MAESTRO V40 — AUDITORÍA INTEGRAL (2000 - 2026)

> [!IMPORTANT]
> Este informe consolida la auditoría cuantitativa del **Quality Entry Gate V40** ejecutado sobre el histórico continuo de **6,730 días de mercado (2000-01-03 a 2026-10-06)**.
> Incorpora la arquitectura **Vault-First** con contingencia **SV5_SHOCK** para protección anti-fallos en episodios de degradación de data macro/VIX.
> **Vintage:** V-C (Series homogéneas EMA5 + barras curadas post-rebuild 2026-10-04).

## 📈 Summary de Performance Global

| Métrica | V40 Estándar (VIX + SV5_SHOCK) | V40 Contingencia (Sin VIX) | SPY Benchmark | Audit Diff |
| :--- | :---: | :---: | :---: | :---: |
| **Acciones SPY Finales** | **`460.87`** | **`442.92`** | `100.00` | `+17.95 acc` |
| **Equity Final** | **`$359,056.27`** | **`$345,074.36`** | - | - |
| **Max Drawdown** | **`-42.74%`** | **`-52.42%`** | `-55.19%` | `-9.68%` |
| **Recovery vs Sin Fallback** | **`100.0%`** | **`104.0%`** | `0.0%` | **96.9% Protegido** |

---

## 🏛️ 1. Desglose por Régimen de Mercado (Modo Estándar V40)

_Cálculo auditado mediante Episode-Aware Compounding (compuesto intra-episodio continuo)._

| Régimen de Mercado | Días Totales | Episodios | Ret. Acumulado (%) | Win Rate Diario (%) | Profit Factor | Ret. Promedio Diario (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`MERCADO_SANO`** | 4,322 | 102 | **+854.61%** | 55.3% | 1.21 | **+0.0568%** |
| **`DISTRIBUCION_PRE_CRASH`** | 806 | 269 | **+16.60%** | 52.5% | 1.09 | **+0.0350%** |
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
| **`MERCADO_SANO`** | 4,321 | 102 | **+830.31%** | 55.3% | 1.21 | **+0.0562%** |
| **`DISTRIBUCION_PRE_CRASH`** | 822 | 271 | **+15.76%** | 52.6% | 1.08 | **+0.0330%** |
| **`PISO_GENERACIONAL`** | 658 | 26 | **+239.82%** | 52.1% | 1.26 | **+0.2335%** |
| **`RE_ACUMULACION_ALCISTA`** | 524 | 269 | **+29.78%** | 53.9% | 1.28 | **+0.1097%** |
| **`NORMAL`** | 251 | 35 | **+3.26%** | 51.6% | 1.05 | **+0.0298%** |
| **`PULLBACK_ALCISTA`** | 97 | 38 | **+14.41%** | 64.4% | 2.08 | **+0.2316%** |
| **`RECUPERACION`** | 45 | 9 | **+18.75%** | 52.8% | 2.03 | **+0.4980%** |
| **`CRASH_SISTEMICO`** | 12 | 7 | **+0.00%** | 0.0% | 1.00 | **+0.0000%** |

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
| **2009** | **+32.75%** | +22.65% | **+10.09%** | **239.39** |
| **2010** | **+12.78%** | +13.14% | -0.36% | **238.18** |
| **2011** | **-0.75%** | +0.85% | -1.60% | **235.14** |
| **2012** | **+21.83%** | +14.17% | **+7.66%** | **251.64** |
| **2013** | **+31.02%** | +29.00% | **+2.02%** | **256.14** |
| **2014** | **+12.68%** | +14.56% | -1.89% | **252.30** |
| **2015** | **+15.82%** | +1.29% | **+14.53%** | **289.18** |
| **2016** | **+2.41%** | +13.59% | -11.17% | **259.38** |
| **2017** | **+18.97%** | +20.78% | -1.81% | **255.84** |
| **2018** | **-4.19%** | -5.25% | **+1.06%** | **257.16** |
| **2019** | **+28.52%** | +31.09% | -2.57% | **254.26** |
| **2020** | **+44.97%** | +17.24% | **+27.74%** | **315.02** |
| **2021** | **+26.02%** | +30.51% | -4.48% | **304.26** |
| **2022** | **+0.04%** | -18.65% | **+18.68%** | **374.89** |
| **2023** | **+30.11%** | +26.71% | **+3.40%** | **385.51** |
| **2024** | **+27.44%** | +25.59% | **+1.86%** | **391.74** |
| **2025** | **+43.14%** | +18.01% | **+25.13%** | **476.45** |
| **2026** | **+10.76%** | +14.93% | -4.17% | **460.87** |

---

## 🔬 Especificaciones de Fórmulas y Verificación Anti-Sesgo

| Métrica Auditada | Definición Matemática | Control Anti-Sesgo / Verificación |
| :--- | :--- | :--- |
| **Ret. Acumulado por Régimen** | `∏ (1 + R_episode) - 1` | Elimina la falsa multiplicación entre episodios separados por años |
| **Win Rate Diario** | `N_positive_days / N_intra_episode_days` | Descuenta días de transición (t_0 = 0%) para evitar dilución |
| **Rendimiento Anual V40** | `(Equity_end / Equity_start) - 1` | Retorno discreto de capital auditado contra el benchmark SPY |
| **Acciones SPY Compuestas** | `Equity_t / Price_SPY_t` | Medida de unidades absolutas de poder adquisitivo acumulado |
| **Contingencia SV5_SHOCK** | `std(Δ_SV5TW, 10d) ≤ 10.0` | Fallback empírico en la V36 redirect que preserva el 96.9% de protección |
