# GUIDANCE — Revisión del prompt de Tide (`ev_derived`, escalas adaptativas)

> **Sesión nueva, contexto autocontenido.** Este documento trae todo lo necesario para trabajar sin depender de conversaciones previas.
> **Artefacto a revisar:** `.hermes/prompts/2026-09-29-rediseno-ev-derived-escalas-adaptativas.md` (78.296 B, última edición 01-Oct 16:54).
> **Naturaleza del trabajo: REVISIÓN — no rediseño, no corrección de código.**

---

## 0. POR QUÉ ESTA SESIÓN ES NUEVA (estado del hilo anterior)

**Carril anterior: CERRADO. No lo reabras.**
Entre el 02-Oct (12:28 → 13:31) se ejecutó y cerró la retirada de dos columnas del vault. Commits, en orden:
```
31e4f03  exclude 4 VF_* features with best-effort temporal leakage
7c75c8d  retire market.ohlcv_bars.vwap column
f8d50e5  retire market.ohlcv_bars.trade_count + fix stale backfills
8e48b15  purge all vwap/trade_count dead code and obsolete scripts
7ca303c  remove vwap/trade_count from Alpaca live data adapter
7a64cb2  purge vwap/trade_count from research_lab (quaternion + discovery)
```
**Verificado:** árbol limpio · barrido de rastro en `research_lab` vacío · `ohlcv_bars` = OHLCV puro.
→ **Ese carril terminó bien. No queda nada pendiente ahí. No lo audites, no lo "mejores", no lo reabras.**

**Por qué una sesión nueva:** la sesión anterior alcanzó **`CHECKPOINT 15` y `CHECKPOINT 16`** — se truncó por longitud al menos dos veces, y su memoria del plan y de las decisiones está compactada. **Una revisión de un brief de diseño de 78 KB no se hace con un contexto que ya perdió el hilo.** De ahí este arranque limpio.

---

## 1. ESTADO DEL VAULT (lo que cambió desde que se escribió el prompt)

El prompt se escribió el 29-Sep / 01-Oct, con un supuesto de datos **más sucio** que el actual. Esto es lo que cambió. **Verifícalo tú; no lo asumas por este documento.**

| Cambio | Detalle | ¿Toca el prompt? |
|---|---|---|
| **B1-B4 cerrados** | cascada atómica probada · observer completo · zigzag completo · saltos feb-2006 resueltos | Contextual (baseline de datos) |
| **Rutas de scripts reparadas** | los scripts se movieron a `backfills/` / `generators/` / `trainers/`; 5 paths declarados estaban rotos y se corrigieron | ✅ verificar las rutas que el prompt cita |
| **`ohlcv_bars` = OHLCV puro** | se **retiraron** `vwap` y `trade_count` (11% de cobertura, enriquecimiento best-effort de Alpaca, con fuga temporal) | ⚠️ verificar que el prompt no dependa de ellas |
| **4 features `VF_*` fuera** | `VF_VWAPPremium_ZScore`, `VF_TradeCountRel_ZScore`, `VF_VolPerTrade_ZScore`, `VF_TradeCountAccel_ZScore` — excluidas y luego eliminadas del código | ⚠️ verificar si el prompt las nombra |
| **Lake intacto** | `channel_snapshots.vwap_tide/current/wave` + `vwap_sigma_*` + `vwap_spread_*` al 100% | ✅ **es la base del diseño del EV — no se tocó** |

---

## 2. LA DISTINCIÓN CRÍTICA (léela antes que nada)

> **Hay dos "vwap" en el sistema, y solo uno se retiró.**
>
> - **`channel_snapshots.vwap_tide / vwap_current / vwap_wave`** — el VWAP **rodante del canal** (ventanas 240 / 60 / auto), calculado de OHLCV, **cobertura 100%**, **es la dimensión VWAP del EV**. **INTACTO. Es la base de tu diseño.**
> - **`market.ohlcv_bars.vwap`** — el VWAP **del día** (dato primitivo del proveedor Alpaca), 11% de cobertura, **RETIRADO el 02-Oct**.
>
> **Son objetos distintos con el mismo nombre.** Confundirlos costó medio día de trabajo en este proyecto. **No los confundas al revisar.**

---

## 3. REGLA PRIMERO — ADDITIVE-ONLY (no negociable)

El prompt es un artefacto de diseño acumulativo. **Toda edición CRECE el archivo.**
- ✅ **Permitido:** añadir una nota, una advertencia, una aclaración, una revisión de baseline.
- ❌ **Prohibido:** recortar, resumir, reformular, "limpiar" o reordenar contenido existente.
- ❌ **Prohibido:** reescribir una sección "para que se entienda mejor".
- Si algo está mal, **no se borra: se corrige con una nota fechada** que dice qué era y qué es ahora.

**Razón:** el prompt es la memoria del diseño. Si se reescribe, se pierde el rastro de por qué se decidió lo que se decidió — y eso nos ha costado caro.

---

## 4. LA TAREA

Revisar el prompt completo y **corregir los detalles desactualizados**, verificando que sus afirmaciones sigan siendo ciertas hoy.

### D1 — Ancla de revisión desactualizada
El prompt cita `e2a2ada` (9 veces) y `9823194`. Son **hitos históricos del P0**, no la revisión de partida.
→ **Corrección (nota fechada):** declarar que la **baseline de ejecución es el HEAD al arrancar** (hoy `7a64cb2`), y que los hashes citados son hitos del diseño, no el punto de partida.
*Motivo:* sin revisión fija, dos auditores leen estados distintos — ya nos pasó.

### D2 — Falta la nota de estado del vault
El prompt se escribió con un supuesto de datos más sucio que el actual.
→ **Corrección (párrafo aditivo):** una sección corta *"Estado del vault al 02-Oct-2026"* con los cambios de §1 **y la frase de que ninguno afecta al diseño del `ev_derived`** — porque la dimensión VWAP del EV vive en el lake, que está intacto.
*Motivo:* que el agente que reciba el prompt no se detenga a "arreglar" algo ya hecho, ni construya sobre un supuesto viejo.

### D3 — Barrido propio de desactualización (lo haces tú)
No te limites a D1 y D2. **Barre el prompt completo buscando todo lo que pueda haber quedado obsoleto.** Como mínimo:
- **Todas** las rutas de archivo/script que cita → verificar existencia real, **una por una**.
- Los **commits/hashes** citados → verificar que existan y qué son.
- Los **JSON/artefactos citados como fuente** (p. ej. `rc_vol_normalized_thresholds.json`, `ticker_gaussian_profiles.json`, los `_documentation.taxonomy`) → existencia **y contenido actual**.
- La sección **"Registro Canónico de Dimensiones (verificado contra JSONs, 01-Oct)"** → **re-verificar HOY contra los JSON reales**. Si algo cambió, es el hallazgo más importante de esta revisión.
- Las afirmaciones sobre **el esquema de datos** (columnas, cobertura, umbrales) → re-medir contra la base.
- Las referencias a **auditorías previas** → verificar que los informes citados existan.
- Cualquier **conteo** (features, dimensiones, tickers, filas) → re-medir; los números envejecen.

---

## 5. CRITERIOS DE REVISIÓN

Para cada detalle: ¿el prompt afirma algo hoy **falso**, **incompleto** o **confuso**?
- **Falso** → se corrige con una nota aditiva.
- **Incompleto** → se añade.
- **Confuso** (ambigüedad que puede llevar a un error) → se aclara.
- **Correcto** → **no se toca.** No "mejores" lo que ya está bien.

**Y con el mismo peso:** si revisas y el prompt **no requiere cambio en algún punto**, dilo explícitamente — *"verificado, sin cambios"*. Un "no hay problema" exige la misma evidencia que un "hay problema".

---

## 6. REGLAS DEL EJERCICIO

1. **Revisión, no rediseño.** No propongas cambios de arquitectura ni de escalas: eso es materia del diseño, no de esta revisión.
2. **No reabras el carril cerrado** (§0). No audites las retiradas, no toques código, no propongas revertirlas.
3. **Additive-only** (§3). Toda corrección **suma**; nada se elimina ni se reformula.
4. **Cada corrección con su razón y su fecha**: *"(corregido 02-Oct-2026: la revisión de referencia pasó a ser el HEAD al arrancar; `e2a2ada` es hito histórico)"*.
5. **Evidencia por hallazgo**: el comando y su salida. Sin salida, no hay hallazgo.
6. **No ancles**: verifica por dos caminos (lo que el prompt dice + lo que el sistema tiene). Si divergen, ese es el hallazgo.
7. **No amplíes el alcance**: no toques los otros prompts ni el código.
8. **Nada se decide aquí sobre el diseño de Tide.** Si detectas algo de diseño, se **anota como observación**, no se corrige.

---

## 7. ENTREGABLE

**7.1 Tabla de revisión** (por cada punto del prompt que revisaste):
```
SECCIÓN | QUÉ AFIRMA | VERIFICACIÓN (comando + salida) | ¿VIGENTE? | CORRECCIÓN PROPUESTA
```

**7.2 Las correcciones redactadas** — listas para pegar, **en texto aditivo**, con su ubicación exacta (sección/línea) y su nota de fecha.

**7.3 Las dos listas obligatorias:**
- *"Afirmaciones que NO debí hacer sin medir"*.
- *"No verificable aquí"* (con qué haría falta).

**7.4 Y la respuesta corta más importante:**
> **¿El prompt sigue siendo ejecutable tal como está, o hay algo que lo invalida?**
> Sí/No, y si no: **el punto exacto que lo bloquea.**

---

*Contexto de por qué se pide: el prompt de Tide es el brief de diseño del `ev_derived`. Se escribió cuando la data estaba más sucia y las rutas estaban rotas. Hoy la base está mejor, pero el artefacto no lo sabe. Esta revisión lo pone al día **sin perder nada de lo que ya decidió**.*
