@Hermes Implementa el módulo del Gatekeeper Determinista en 'hermes_gates/pre_audit.py'.

Este script es el filtro de validación cuantitativa e industrial ($0 tokens de API) basado
en la metodología de Marcos López de Prado (Advances in Financial Machine Learning) y
Teoría de Valores Extremos (EVT). Audita los resultados crudos generados por el worker
en '{worktree}/artifacts/backtest_results.json' antes de que el auditor epistemológico
(Kimi-k3) sea invocado.

Dependencias permitidas: numpy, scipy, pandas (Python estándar). Cero APIs externas.

---

## 1. Argumentos CLI

```
--input  <ruta a backtest_results.json>
--output <ruta a pre_audit_summary.json>
```

---

## 2. Validación de Esquema y Anti-Lookahead Universal (Innegociable)

### 2a. Esquema JSON obligatorio por experiment_type

Validar presencia de 'experiment_type' y los campos requeridos según tipo:

| experiment_type        | Campos obligatorios en trade_log             | Campos obligatorios en raíz del JSON    |
|------------------------|----------------------------------------------|-----------------------------------------|
| `backtest`             | `signal_time, exec_time, return`             | `n_trials` (default 1 si ausente)       |
| `signal_event_study`   | `signal_time, exec_time, return, mae`        | —                                       |
| `benchmark_comparison` | `signal_time, exec_time, return`             | `benchmark_returns` (array paralelo)    |
| `forward_test`         | —                                            | `backtest_returns`, `forward_returns`   |
| `rare_tail_event`      | `signal_time, exec_time, return, mae`        | —                                       |

Si falta cualquier campo obligatorio:
  `stderr: "JSON_SCHEMA_ERROR: '<experiment_type>' requiere el campo '<campo>' [en cada trade | en la raíz]. Recibido: <claves presentes>."`
  Terminar con `exit(1)`.

### 2b. Anti-Lookahead (aplica a todo experiment_type que tenga trade_log)

- Parsear `signal_time` y `exec_time` con `pd.to_datetime()`.
- Verificar la aserción estricta: `signal_time < exec_time` en el 100% de los trades.
- Si se detecta cualquier coincidencia (`signal_time >= exec_time`) o inversión temporal:
  `stderr: "LOOKAHEAD_BIAS: Trade #<idx> tiene signal_time=<X> >= exec_time=<Y>. Data Leakage detectado."`
  Terminar inmediatamente con `exit(1)`.

---

## 3. Batería de Filtros Cuantitativos según experiment_type

### a) `backtest` (Estrategia Histórica General)

- **Muestra mínima:** N >= 100 trades cerrados.
- **Rentabilidad y Riesgo:**
  - Expectancy (EV) > 0.0
  - Profit Factor >= 1.30
  - Max Drawdown de la curva de capital <= 25.0%
- **Deflated Sharpe Ratio (DSR):** Calcular DSR formal ajustado por `n_trials`,
  skewness, kurtosis y track record. Exigir DSR >= 0.95.
  (Ver sección 5 para implementación matemática exacta).
- **PBO con CSCV y Embargo Adaptativo:** 8 particiones simétricas con buffer de
  embargo de `max(5, mediana_holding_period)` barras entre train/test
  (70 combinaciones 4-train / 4-test). Exigir PBO <= 0.30.
- **Anti-Concentración:** El Top 5% de trades no debe representar más del 40.0%
  del PnL acumulado total.

### b) `benchmark_comparison` (Evaluación Relativa vs SPY / Benchmark)

- **Muestra mínima:** N >= 50 periodos o trades comparables.
- **Alpha Anualizado:** Alpha contra Buy & Hold del benchmark > 0.0.
- **Downside Protection Score:** Retorno relativo medio >= 0.0 en los periodos
  donde el benchmark rinde negativo (protección de capital).
- **Information Ratio (IR):** IR >= 0.50.

### c) `forward_test` (Walk-Forward / Paper Trading Reciente)

- **Muestra mínima:** N >= 25 trades forward.
- **Consistencia de Distribución:** Test Kolmogorov-Smirnov
  (`scipy.stats.ks_2samp(backtest_returns, forward_returns)`).
  Exigir p-value > 0.05 (no rechazar procedencia de la misma distribución).
- **Rentabilidad Forward:** EV_forward > 0.0 y degradación de Win Rate <= 10 pp
  vs backtest.

### d) `signal_event_study` (Estudios de Señales / METAR / Tide / Secuencias)

- **Muestra mínima:** N >= 30 eventos.
- **Cumulative Abnormal Return (CAR):** T-test de 1 muestra
  (`scipy.stats.ttest_1samp(returns, 0.0)`) con p-value < 0.01 y t-stat > 2.50.
- **Calidad de Entrada (Path Dependency):** Ratio EV / |MAE_medio| >= 1.0
  (la ganancia esperada supera o iguala el drawdown intra-trade promedio).
- **Asimetría de Retorno:** Ratio (Ganancia Media / Pérdida Media) >= 1.20.

### e) `rare_tail_event` (Diamantes de Régimen, Cisnes y Desbordamientos ±3σ)

- **Población Exhaustiva:** N >= 5 eventos (censo histórico completo del fenómeno).
- **Rendimiento Asimétrico Extremo:**
  - Win Rate >= 75.0%
  - Profit Factor >= 3.0
  - Cero wipeouts catastróficos (ningún trade con pérdida > 2x la media de pérdidas).
- **Significancia No Paramétrica:** Test Exacto de Fisher (2x2: señal vs no-señal,
  win vs loss) o Monte Carlo de Colas (10,000 permutaciones) con p-value < 0.05.
- **Salida especial:** Adjuntar desglose histórico fecha a fecha
  (`event_census: [{date, return, mae}, ...]`) para auditoría microestructural
  en el perfil auditor (Kimi-k3).

---

## 4. Generación de Artefacto y Control de Salida

### Si cualquier filtro falla:
  `stderr: "PRE-AUDIT FAILED: <experiment_type> | <nombre_filtro>: obtenido=<valor> vs requerido=<umbral>"`
  Terminar con `exit(1)`.

### Si aprueba todas las validaciones:

Calcular métricas de forma (`scipy.stats.skew`, `scipy.stats.kurtosis` con `fisher=False`)
y generar el archivo JSON en `--output` con la siguiente estructura:

```json
{
  "timestamp": "<UTC ISO>",
  "experiment_type": "<tipo>",
  "status": "PASSED_DETERMINISTIC_GATES",
  "sample_size": "<N>",
  "n_trials": "<K>",
  "temporal_span": {
    "start": "<fecha_primer_trade>",
    "end": "<fecha_ultimo_trade>"
  },
  "lookahead_audit": "PASSED (0 violations)",
  "distribution_metrics": {
    "skewness": "<float>",
    "kurtosis": "<float>",
    "mae_mean": "<float o null>"
  },
  "verified_metrics": {
    "<metricas_calculadas_segun_tipo>"
  },
  "rare_event_census": "<lista de eventos fecha a fecha o null>"
}
```

Imprimir en stdout:
  `[PRE-AUDIT: PASSED] Type: <tipo> | N=<N> | Status: PASSED_DETERMINISTIC_GATES`

Terminar con `exit(0)`.

---

## 5. Implementación Matemática del DSR (López de Prado, AFML Ch.14)

El Deflated Sharpe Ratio ajusta el Sharpe observado por el número de ensayos realizados
(n_trials = K) para eliminar falsos descubrimientos por selección múltiple.

Implementar EXACTAMENTE esta función:

```python
import numpy as np
import scipy.stats

def compute_dsr(returns: np.ndarray, n_trials: int = 1, periods_per_year: int = 252) -> float:
    """
    Deflated Sharpe Ratio (López de Prado, 2018).

    returns: array de retornos por trade o por periodo.
    n_trials: número de estrategias/configuraciones probadas (K).
    periods_per_year: factor de anualización (252 para diario, N_trades/años para por-trade).

    Retorna: DSR en [0, 1]. Exigir DSR >= 0.95.
    """
    n = len(returns)
    if n < 2:
        return 0.0

    mean_r = np.mean(returns)
    std_r = np.std(returns, ddof=1)
    if std_r == 0:
        return 0.0

    # Sharpe Ratio anualizado
    sr = (mean_r / std_r) * np.sqrt(periods_per_year)

    # Momentos de la distribución de retornos
    skew = scipy.stats.skew(returns)
    kurt = scipy.stats.kurtosis(returns, fisher=False)  # Pearson (normal=3)

    # Varianza del estimador de Sharpe (Bailey & López de Prado, 2012)
    var_sr = (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * (sr ** 2)) / (n - 1)
    if var_sr <= 0:
        return 0.0

    # SR* benchmark: Sharpe esperado del mejor de K ensayos bajo H0
    if n_trials > 1:
        euler_mascheroni = 0.5772156649
        z1 = scipy.stats.norm.ppf(1.0 - 1.0 / n_trials)
        z2 = scipy.stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        sr_star = np.sqrt(var_sr) * ((1.0 - euler_mascheroni) * z1 + euler_mascheroni * z2)
    else:
        sr_star = 0.0

    # Probabilistic Sharpe Ratio deflactado
    dsr = scipy.stats.norm.cdf((sr - sr_star) / np.sqrt(var_sr))
    return float(dsr)
```

---

Crea el archivo 'hermes_gates/pre_audit.py' con este código completo, tipado,
modular, 100% determinista y sin dependencias externas.
