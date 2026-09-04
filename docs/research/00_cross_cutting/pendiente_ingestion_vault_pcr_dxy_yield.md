# PENDIENTE DE INFRAESTRUCTURA: Corte de Ingestión del Vault — PCR/DXY/YIELD (12-16 Ago 2026)

**Fecha de detección:** 2026-09-04
**Documentado por:** Hermes (auditoría del comité walk-forward)
**Estado:** ESPERANDO AL VAULT (backfill upstream en curso)

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