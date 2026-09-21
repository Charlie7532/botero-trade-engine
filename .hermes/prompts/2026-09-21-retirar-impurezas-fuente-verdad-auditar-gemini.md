# PROMPT: AUDITAR Y RETIRAR IMPUREZAS + CONSOLIDAR UNA SOLA FUENTE DE VERDAD
# + AUDITORÍA CUIDADOSA DE LOS CAMBIOS DE GEMINI

> **Fecha:** 2026-09-21 · **Repo:** /root/botero-trade · **Intérprete:** backend/.venv/bin/python3 · **Respuesta:** español
> **Principio rector:** cada indicador debe tener UNA sola fuente de la verdad. Retirar lo huérfano/backup/legacy SIN romper nada activo. **Dato mata relato.**

---

## PARTE A — AUDITAR y RETIRAR indicadores huérfanos/duplicados (con extremo cuidado)

### A0. Regla de ORO del retiro (LEER PRIMERO)
**NO retirar basándose solo en `update_source = 'none_historical_only'`.** Ese marcador puede no reflejar la realidad (un ticker marcado legacy puede seguir siendo CREADO por un provider activo). **ANTES de retirar cualquier ticker, CONFIRMAR EMPÍRICAMENTE que:**
1. NO es escrito por NINGÚN provider activo (`grep -rn "ticker=\"<T>\"" backend/daemons/`)
2. NO es leído por NINGÚN consumidor del pipeline (`grep -rn "<T>" backend/modules/`)
3. NO aparece en `${background}_provider` reconstruidos por Gemini

**Si un ticker es ESCRIBIDO o LEÍDO en el código activo → NO retirar (es fuente de verdad viva), aunque tenga marcador legacy.**

### A1. Retirar con evidencia (candidatos verificados)
**Candidatos primarios (el intento de sintetizar SKEW, huérfano):**
- `UW_SKEW_*` — 9 tickers: `UW_SKEW_A`, `UW_SKEW_AAPL`, `UW_SKEW_ABBV`, `UW_SKEW_ABNB`, `UW_SKEW_ABT`, `UW_SKEW_MSFT`, `UW_SKEW_NVDA`, `UW_SKEW_QQQ`, `UW_SKEW_SPY` (sec=Options Flow, src=none_historical_only). **Verificar que NINGÚN código los lee/usa.** Si huérfanos → retirar.

**Candidatos a AUDITAR (el F&G sintetizado — NO tocar sin verificación):**
- `FG_SP`, `FG_MOMENTUM`, `FG_STRENGTH`, `FG_BREADTH`, `FG_PUTCALL`, `FG_VIX`, `FG_JUNKBOND`, `FG_SAFEHAVEN`, `FGBI`
- ⚠️ **ADVERTENCIA:** el `cnn_fg_sp_provider.py` los RECONSTRUYE (FG_SP = media de los 7). **Si están activos → NO retirar**; si el provider está huérfano (nadie lo invoca) → decidir retirar. Confirmar por grep de invocación.

### A2. Proceso de retiro por ticker (solo tras A0)
1. `grep -rn "ticker=\"<T>\"" backend/daemons/ backend/modules/ --include="*.py"` → 0 hits = huérfano ✓
2. `grep -rn "<T>" backend/ --include="*.py" --include="*.json"` → revisar refs
3. Si huérfano → retirar de `market.ticker_metadata` (y de `market.ohlcv_bars` si hubiera data — **verificado hoy: 0 registros** para UW_SKEW_*)
4. Documentar cada retiro: {ticker, por qué huérfano, evidencia grep, qué se borró}

---

## PARTE B — CONSOLIDAR UNA SOLA FUENTE DE VERDAD (para no confundir)

### B1. El caso FG (crítico — requiere DECISIÓN, no automático)
- `get_fg_market_metar` (fg_metar_service.py) **lee SOLO el ticker `FG`** (base).
- `cnn_fg_sp_provider.py` **escribe `FG_SP`** (y el daemon data_vault_daemon escribe `FG`).
- **¿`FG` y `FG_SP` son la misma cosa con 2 nombres, o distintos?** Audit de dependencia:
  - Rastrear cómo el `FG` (base) se produce y cómo `FG_SP` se relaciona.
  - **Determinarr si es UA o DOBLE fuente de la verdad**. Si ambos representan el mismo FEAR & GREED → consolidar a UNO, eliminar el duplicado.

### B2. Inventario de fuentes de verdad por estación
Para CADA estación METAR (VIX, VVIX, PCR, FG, SV5, SKEW, CREDIT, YIELD, ROTATION, BSI, DXY):
- ¿Cuál es el ticker CANÓNICO (base) que el servicio METAR lee?
- ¿Hay tickers DUPLICADOS/derivados que compiten (ej. FG vs FG_SP, CREDIT vs CREDIT_RATIO)?
- Reportar tabla: {estación, ticker canónico, tickers duplicados, ¿romperían si se retiran?}

---

## PARTE C — AUDITORÍA EXTREMA DE LOS CAMBIOS DE GEMINI (la prioridad)

Gemini reconstruyó 11 providers + data_vault_daemon para el fix de fechado. **Auditar con sumo cuidado:**

### C1. Patrón de fechado — verificar UNIFORMIDAD en TODOS
Cada provider debe usar `effective_date` (fecha de la DATA subyacente) y `already_up_to_date`, NUNCA `datetime.now()`. Auditar por provider:
- `synthetic_indicators_provider.py` (CREDIT_RATIO, ROTATION, YIELD)
- `breadth_provider.py` (S5TW/TH/FI), `bsi_provider.py`, `sv5_turbulence_provider.py`
- `volume_breadth`, `sector_breadth`, `sector_cap_breadth`, `sector_volume_breadth`, `sector_volume_intensity`
- `cnn_fg_sp_provider.py`, `cnn_fg_breadth_provider.py`
- `data_vault_daemon.py` (inline breadth)

**Chequeo:** `grep -rn "datetime.now(UTC)\|time=now\|time=effective_date"` por archivo → confirmar que NINGÚN upsert de fechado use `now`.

### C2. `already_up_to_date` — verificar que el guard es CORRECTO
- ¿El guard compara contra la fecha correcta del subyacente?
- ¿No bloquea una actualización legítima? (falso "ya al día")
- ¿El `start` (ventana de carga histórica) es suficiente? (auditar `timedelta(days=X)`)

### C3. No-regresión funcional
- Los 11 providers + daemon compilan (ast.parse) ✓ (ya verificado)
- **Importar cada daemon/provider** en el venv → confirmar que no rompe imports
- Correr la suite (`tests/` 248 + entry_decision 68) → 0 regresión
- **Smoke del backfill:** verificar que FG (o FG_SP) sigue generándose y que los indicadores ya no crean velas de sábado/domingo

### C4. La purga/backfill del Vault
- Verificar el estado real: ¿los indicadores sintéticos quedaron con vela 18-vie (correcto) o 19-sáb/21-lun (malo)?
- Si quedan velas en 19/21 → identificar y corregir
- `regime_states`: ¿las transiciones con fechas 19/21 se re-evaluaron?

---

## ENTREGABLES
1. **Tabla de retiro** (Parte A): por ticker, evidencia grep de huérfano, qué se borró
2. **Tabla de fuente de verdad** (Parte B): por estación, ticker canónico vs duplicados, decisión FG
3. **Informe de auditoría de Gemini** (Parte C): por provider, veredicto de fechado/guard/no-regresión
4. **Estado del Vault post-fix**: velas correctas (18-vie), sin 19/21 en sintéticos, regime_states OK

## REGLA GENERAL
- **No retirar nada sin confirmar que está HUÉRFANO** (ningún provider lo escribe, ningún módulo lo lee).
- **No corregir el fix de Gemini si está bien** — solo reportar; si hay bug, proponer fix y esperar aprobación (Rule 22).
- **Dato mata relato** — toda decisión con grep/evidence, no con intuición.
- No tocar rotación, no tocar gates, no modificar código a menos que se autorice.