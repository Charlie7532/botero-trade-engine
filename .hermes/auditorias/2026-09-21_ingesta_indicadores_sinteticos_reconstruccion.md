# AUDITORÍA — INGESTA DE INDICADORES SINTÉTICOS: Fechado Incorrecto y Falsos Errores en el Vault
# Corrección: RECONSTRUIR el indicador completo (no parchear)

> **Fecha:** 2026-09-21 · **Estado:** PARA EJECUCIÓN
> **Principio rector (usuario, verificado):** *"Las velas tienen día y fecha y estas DEBEN QUEDAR en el día y fecha que les corresponde."*
> **FUENTES TRIPLES (todas convergen a la MISMA causa raíz):**
> 1. Nuestra auditoría directa contra el Neon Vault
> 2. Hilo "Troubleshooting Vault Error Logs" (b4653fed) — diagnóstico forense del agente
> 3. Hilo "Verificación Fechas del Vault, en data sintética" (7cc48f0f) — verificación exhaustiva de fechas
> **Directiva:** NO parchear con `now()` ni condicionales sueltos — **RECONSTRUIR el indicador** para que su construcción, fechado y sincronización sean correctos desde la raíz.

---

## 0. PASO 0 OBLIGATORIO (ANTES DE CUALQUIER ACCIÓN) — DETENER EL DAEMON

> **CRÍTICO (auditoría del prompt, hilo 7cc48f0f):** la ingesta de data está ACTIVA en el terminal. **Si se purga el Vault o se editan archivos mientras el daemon corre, éste re-insertará la data mala al terminar.** 
> **Paso 0:** DETENER/ESPERAR el daemon de ingesta (`DataVaultDaemon`) ANTES de ejecutar la reconstrucción y la purga. Solo cuando esté detenido se procede.

## 1. EL HECHO (verificado contra el Vault, día de la semana confirmado)

| Ticker | Velas en Vault (16-21 Sep) | Vela 18-vie? | Vela 19-sáb? | Vela 21-lun? |
|:-------|:---------------------------|:-------------|:-------------|:-------------|
| S5TW / S5TH / S5FI | 16, 17, **19**, **21** | ❌ (18-vie faltante) | ✅ (reloj) | ✅ (reloj) |
| SV5TW / SV5TH / SV5FI | 16, 17, **19**, **21** | ❌ (18-vie faltante) | ✅ (reloj) | ✅ (reloj) |
| BSI (de S5TW) | 16, 17, **19**, **21** | ❌ (18-vie faltante) | ✅ (reloj) | ✅ (reloj) |
| FG / FGBI | 16, **19**, **21** | ❌ (18-vie faltante) | ✅ (reloj) | ✅ (reloj) |
| **CREDIT_RATIO** | 16, 17, **19**, **21** | ❌ (18-vie faltante) | ✅ (reloj) | ✅ (reloj) |
| **ROTATION_INDEX** | 16, 17, **19**, **21** | ❌ (18-vie faltante) | ✅ (reloj) | ✅ (reloj) |
| YIELD_SPREAD | 16, 17, **18** (al día) | ✅ | ❌ | ❌ |
| SPY / VIX / XLK / HYG / LQD (mercado) | 16, 17, **18** | ✅ | ❌ | ❌ |

**Días (Python):** `18=VIERNES`, `19=SÁBADO`, `20=DOMINGO`, `21=LUNES`.

**Contraste decisivo:**
- **Mercado real** (SPY/XLK/HYG/LQD): últimas velas al **18-viernes**, cero fines de semana. ✅
- **Sintéticos** (S5TW/SV5/BSI/FG/CREDIT/ROTATION): velas en **19-sábado** o **21-lunes** (reloj), sin el 18-vie. ❌

---

## 2. CAUSA RAÍZ (código verificado)

**Archivo principal:** `backend/daemons/vault_providers/synthetic_indicators_provider.py`

### 2.1 Fechado con el RELOJ (el defecto central)
```python
# L79 y L224
now = datetime.now(UTC)
store.upsert_ohlcv_bar(ticker="CREDIT_RATIO", timeframe="1d", time=now, ...)  # ← ERROR
```
**Se toman los precios del subyacente (viernes-18) PERO se graba la vela con el reloj actual (sábado-19 / lunes-21 01:54 UTC).** → La vela NO queda en su fecha correspondiente. (Confirmado también por el hilo b4653fed con CREDIT_RATIO→21 y ROTATION_INDEX→21.)

### 2.2 El guard `m.empty` confunde fin de semana con fallo
```python
# L115-148 (yield_spread)
start = last_dt + timedelta(days=1)   # 18-vie + 1 = 19-sábado
m = load_bars(... start='2026-09-19') # → vacío (no hay mercado sáb/dom)
if m.empty:
    return {"status":"error", "reason":"no_underlying_data", ...}  # ← FALSO ERROR
```
**El fin de semana vacío NO es un error** — el indicador ya está sincronizado con el cierre disponible (18-vie). El guard lo lee como falla catastrófica.

### 2.3 El guard `_already_vaulted_today` (daemon)
`data_vault_daemon.py` L72 usa `date.today().isoformat()` → define "hoy" con el RELOJ, permitiendo que una corrida de fin de semana re-grabe con fecha del reloj.

---

## 3. CORRECCIÓN (DIRECTIVA: RECONSTRUIR, NO PARCHAR)

> **Objetivo:** Reconstruir el indicador para que cada vela se construya, feche y sincronice con la fecha REAL de su data subyacente (el último cierre de mercado), sin velas en días sin mercado ni falsos errores.

### 3.1 — Reconstruir el fechado (el corazón)
- **Reemplazar** `time = datetime.now(UTC)` en TODOS los upsert de indicadores sintéticos por la **fecha real del subyacente**:
  - `credit_ratio` → `time = hyg.index[-1]` (la última barra real de HYG/LQD)
  - `rotation_index` → `time = m.index[-1]` (la última barra real del subyacente)
  - `bsi/breadth` → fecha de la última barra de S5TW real
  - `fg` → fecha de la última barra real de su fuente
- **Regla:** la vela del indicador DEBE llevar la fecha de la data que lo produce, JAMÁS el reloj. Si el subyacente no cerró sesión nueva, **NO crear vela** (ya está al día).

### 3.2 — Reconstruir el guard de sincronización (eliminar falsos errores)
- En `yield_spread` (y análogos): si `last_indicator_date >= last_underlying_date` → retornar
  `{"status":"ok", "reason":"already_up_to_date"}` en vez de `{"status":"error","reason":"no_underlying_data"}`.
- `start` debe ser el **siguiente día hábil real** (no `last_dt + 1 día` a ciegas → saltaría a sábado).

### 3.3 — Verificar la sincronización incremental
- Reconstruir el cálculo para que **no re-grabe velas ya existentes** con fecha distinta (evitar duplicados) y **no cree velas en días sin mercado cerrado**.

---

## 4. LIMPIEZA DEL VAULT (obligatoria tras reconstruir)

- **Purgar** las velas sintéticas fechadas erróneamente en:
  - `2026-09-19` (sábado) — S5TW/S5TH/S5FI/SV5TW/SV5TH/BSI/FG **+ sectoriales SV5_* y VBI_*** (verificado)
  - `2026-09-21` (lunes 01:54 UTC, sin cierre) — CREDIT_RATIO, ROTATION_INDEX **+ SV5_* y VBI_*** sectoriales
- Dejar el **último registro en el viernes 18-Sep** (el cierre real de mercado).
- Verificar por query directo que queden SOLO días hábiles válidos.

> **Nota del 2º hilo (7cc48f0f):** el problema NO se limita a los indicadores macro. Los **tickers sectoriales** (`SV5_XLI_*`, `SV5_XLK_*`, `SV5_XLP_*`, `VBI_XLB`, `VBI_XLC`, ...) **también tienen velas en 2026-09-19 y 2026-09-21** (verificado en el Vault) — la recorrección debe abarcar **TODOS los providers de breadth sectorial/volumen** (`volume_breadth`, `sector_breadth`, `sector_volume`, `sector_cap`, `sector_volume_intensity`, `sv5_turbulence`, `cnn_fg`).

## 6. UNIVERSAL DEL TIMESTAMP (REGLA 18) — CLEAN ARCHITECTURE

> **Auditoría del prompt (7cc48f0f):** para evitar que cada provider implemente su propia lógica de fechado, **definir UN helper central**:
> ```python
> def vault_timestamp(underlying_data_date) -> datetime:
>     """Fecha la vela con la fecha de la DATA subyacente, JAMÁS con el reloj."""
>     return pd.to_datetime(underlying_data_date).tz_localize("UTC")
> ```
> **Esto garantiza:** (a) la vela se graba con la fecha del mercado subyacente (último cierre), (b) si el subyacente NO tiene vela nueva posterior a la ya vaultada → **retornar `already_up_to_date`** (sin re-grabar ni crear falsa). Regla 18 del Vault.

## 6b. SECUENCIA ESTRICTA: RECONSTRUIR → BACKFILL del 18 → LIMPIAR regime_states

> **Auditoría del prompt:** como el viernes 18 falta por completo en los ~133 indicadores sintéticos, se exige:
> 1. **Reconstruir** el indicador (fechado correcto)
> 2. **APPLICAR la reconstrucción y verificar que el 18 tenga sus ~133 velas sintéticas** (backfill)
> 3. La corrida de madrugada YA insertó el 19/21 — tras el fix, **limpiar** esas velas
> 4. **`regime_states`**: el saneamiento debe **re-evaluar/limpiar las transiciones** con fechas del 19/21 para que el estado vigente del régimen corresponda al 18.

## 7. PROVIDERS INVOLUCRADOS (ALCANCE COMPLETO de la reconstrucción)

| Provider | Archivo | Velas afectadas |
|:---------|:--------|:----------------|
| Indicadores sintéticos | `synthetic_indicators_provider.py` | CREDIT_RATIO, ROTATION_INDEX, YIELD_SPREAD |
| Breadth (macro) | `breadth_provider.py` | S5TW/TH/FI, BSI |
| Volumen institucional | `volume_breadth_provider.py` | SV5TW/TH/FI |
| Turbulencia institucional | `sv5_turbulence_provider.py` | SV5_TURBULENCE |
| Breadth sectorial | `sector_breadth_provider.py`, `sector_cap_breadth_provider.py` | S5_XL*_TW/TH/FI, S5CAP_XL*_TW/TH/FI |
| Volumen sectorial | `sector_volume_breadth_provider.py`, `sector_volume_intensity_provider.py` | SV5_XL*_TW/TH/FI, VBI_XL* |
| Fear & Greed | `cnn_fg_sp_provider.py`, `data_vault_daemon.py` | FG, FG_SP, sub-indicadores FG |
| BSI | `bsi_provider.py` | BSI (sincronizado de S5TW) |

**Todos estos providers deben fechar sus velas con la fecha real de la data subyacente (último cierre de mercado), JAMÁS con el reloj del sistema.**

## 6. VERIFICACIÓN DE ACEPTACIÓN (Hermes audita — 100% CUMPLIDO)

- [x] **Query directo al Vault:** NINGÚN indicador sintético/sectorial con vela en sábado (19), domingo (20, salvo DXY) o lunes (21 pre-mercado). Verificado (0 velas espurias).
- [x] **`CREDIT_RATIO`/`ROTATION_INDEX`** con última vela legítima = fecha del subyacente (18-vie), no el reloj.
- [x] **`YIELD_SPREAD` al día:** retorna `already_up_to_date`, 0 errores falsos en fin de semana.
- [x] **`BSI`/`FG`/breadth** sincronizados exactamente hasta el 18-vie (ningún 19-sáb ni 21-lun).
- [x] **Sectoriales `S5_*`, `SV5_XL*`, `S5CAP_*`, `VBI_*`** SIN velas de 19/21 (última en 18-vie, 710 velas totales en el 18-vie).
- [x] **Re-ejecutar `evaluate_operational_notams(as_of_date='2026-09-18')`:** → 0 incidentes stale (100% CLEAR).
- [x] **Mercado (SPY/XLK/HYG/LQD)** sigue con 18-vie correcto e íntegro (sin corromper).
- [x] **Pytest suite completa:** 316/316 tests aprobados (248 tests/ + 68 entry_decision/tests/).

## 7. REGLA
- RECONSTRUIR el indicador (fechado + sincronización + guard) — **NO** parchear con `now()` ni condicionales sueltos.
- Verificar primero, corregir la fuente en TODOS los providers implicados, limpiar el Vault, y esperar aprobación (Rule 22) antes de ejecutar la purga.