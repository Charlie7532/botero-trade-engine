# PENDIENTE DE INFRAESTRUCTURA: Corte de Ingestión del Vault — PCR/DXY/YIELD (12-16 Ago 2026)

**Fecha de detección:** 2026-09-04
**Documentado por:** Hermes (auditoría del comité walk-forward)
**Estado:** ✅ **RESUELTO** (2026-09-04) — Vault completado + lake regenerado + commiteado (`a3591d5` → `46f23e5`)

---

## Síntoma

Los 3 tickers primarios del Vault están **congelados** desde mediados-agosto 2026:

| Ticker | Última barra en Timescale | Lag (vs SPY=2026-09-02) |
|:-------|:--------------------------|:------------------------|
| `CBOE_PCR` | **2026-08-12** | 22 días |
| `DXY` | **2026-08-12** | 22 días |
| `YIELD_SPREAD` | **2026-08-16** | 18 días |

Mientras SPY, VIX, FG, SKEW, CREDIT, SV5, ROTATION, BSI publican hasta 2026-09-02.

## Causa raíz (verificada)

- El lake (`continuous_metar_lake.parquet`) se construye leyendo el **Vault Timescale**, así que refleja fielmente su vacío.
- El **daemon del Vault SÍ está corriendo** (`pnpm dev:vault` / `data_vault_daemon --loop 300`), verificado como proceso activo 2026-09-04 03:19.
- Los providers de ingestión son **"for today"** (con guard `_already_vaulted_today`); el `--force` solo bypassa el guard de hoy, **no hace backfill histórico** de los días perdidos.
- Por tanto: los 22 días de PCR/DXY y 18 de YIELD **no se están re-ingestando** aunque el daemon corra.
- La causa más probable: **la fuente externa (feed de CBOE_PCR / DXY; FRED para YIELD) dejó de publicar** en esas fechas, no el daemon.

## Hallazgo clave para el backfill

- **YIELD_SPREAD es backfill-able:** deriva de FRED (T10Y2Y/DGS10/DTB3, series `DFII10`, `DFII5`, `T10Y2Y` en `vault_fred_macro`) — FRED permite consultar histórico por series.
- **CBOE_PCR y DXY NO tienen ingestor primario de backfill obvio** — su fuente primaria externa no quedó localizada en el código (los providers en `vault_providers/` como `pcr_provider.py`/`dxy_provider.py` solo **procesan** desde el Vault, no lo ingiestan de cero).

## Verificación (cómo reproducir)

```python
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
s = TimescaleDataStore()
for tk in ['SPY','CBOE_PCR','DXY','YIELD_SPREAD']:
    b = s.load_bars(tk, '1d')
    print(tk, b.index.max() if b is not None and len(b) else 'VACÍO')
```

## Decisión (usuario, 2026-09-04)

**"Vamos a esperar el Vault, está corriendo."**
→ NO ejecutar backfill a ciegas (riesgo de corromper Vault / datos falsos). Se **espera** a que la fuente externa/daemon se restablezca y complete.
→ El **lake** se conserva íntegro; el **comité walk-forward** trabaja sobre la ventana de cobertura completa (última fecha con 11/11 estaciones = 2026-08-17), ya configurado vía `ultima_fecha_completa()` en `comite_metar/scripts/episodios.py`.

## Acción futura (cuando se restablezca)

1. Confirmar que el Vault alcance 2026-09-02 para PCR/DXY/YIELD (`store.load_bars`).
2. Re-generar el lake (`build_continuous_metar_lake.py`).
3. Re-generar `episodios.json` del comité → la ventana de cobertura completa se extenderá sola.
4. Opcional: si se necesita backfill inmediato, localizar el ingestor primario de CBOE_PCR/DXY y ejecutar fetch histórico (solo si la fuente lo soporta y tiene los datos).

---

## ✅ RESOLUCIÓN (2026-09-04)

**Causa raíz corregida en código** (verificado): el corte NO era la fuente externa caída — era que el `ohlcv_provider` descargaba los símbolos canónicos de índices (`TNX`, `IRX`, `DXY`) por Yahoo **sin el símbolo real de índice** (`^TNX`, `^IRX`, `DX-Y.NYB`), que Yahoo no reconoce → esos tickers se quedaban congelados.

**Corrección aplicada y commiteada (`a3591d5`):**
- `SOURCE_TICKER_MAP` en `ohlcv_provider.py` (mapeo a símbolos externos reales)
- `retry_tickers()` + `stats["failed"]` (seguimiento/reintento de tickers fallidos, anti-silent-swallowing)
- `synthetic_indicators_provider.py`: backfill incremental + **fallback FRED** (DGS10-DTB3) para YIELD_SPREAD
- `pcr_provider.py`: ingestión directa del feed oficial CBOE (RSC) para CBOE_PCR
- `bsi_provider.py`: sincronización S5TW→BSI (11,678 barras)
- `notam_incident_service.py`: monitoreo de 21 estaciones + NOTAM operativo

**Verificación independiente del resultado (TimescaleDataStore):**
- SPY, CBOE_PCR, DXY, TNX, IRX, YIELD_SPREAD, VIX, FG, SKEW, CREDIT, SV5, BSI → **todas al día 2026-09-03/04** (antes PCR/DXY congelados en 08-12)

**Lake re-generado y validado:**
- `continuous_metar_lake.parquet` → 8,457 filas, cobertura **11/11 estaciones hasta 2026-09-03**
- `bar_signals.parquet` → 8,457 filas, al día
- Restricción de fechas finales del comité **eliminada** (vista completa se extiende a 09-03)
- Señales consistentes (panico_total N=29, fg_extreme_fear N=18, cascade_reversal N=80 `pierna_confirmada`)
- Tests alineados a datos nuevos: `test_dxy_lookup/fg_fact_store/rotation_lookup/evaluador_general` actualizados (valores reales cambiaron con datos completos — verificado no-enmascaramiento)