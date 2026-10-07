# NOTA DE CORRECCIÓN AL PROMPT — previa a la ejecución

**Revisión base:** `593fd38b…` (snapshot: `.hermes/prompts/_snapshots/2026-10-02_pre-anotaciones_rediseno-ev-derived.md`)
**Regla:** correctivo puntual. **No reescribir secciones** — solo los puntos listados.
**Nada de esto es decisión nueva**: son alineaciones a lo ya decidido en el hilo.

## BLOQUE 1 — El bug de fatiga ya está cerrado (1 comando + 3 textos)
1. **§8.4** 🔴 — el comando `grep -c "fatigue_type" …/rc_tide_ev_lookup.py` **espera `0` y hoy da `2`**. Es **lo primero que corre el ejecutor**. Sustituir por: *"verificar que `RealEVSignal` expone `fatigue_type` y `fatigue_delta_ev`, y que los 8 tests de contrato pasan"*.
2. **§1.5** — de *"Bug Activo… CRASH POTENCIAL"* → **RESUELTO** (A1 + D-1, 02-Oct). Conservar el diagnóstico como historia.
3. **§7** — eliminar el criterio *"Se proponga una solución integral al bug de runtime `fatigue_type`"*.
4. **§9.2 #3** — quitar *"para subsanar de inmediato el bug de runtime"*. La pregunta sigue; el motivo ya no.

## BLOQUE 2 — El alcance de las escalas: §2.0-bis es el CANON
**No redefinir** (decisión del hilo, insertada 01-Oct): **filas 1–8 = gaussianas per-ticker · filas 9–10 = threshold fijo**.
**Alinear aguas abajo:**
- **§2.1** — reemplazar `k ∈ {T, C, W, VWAP}` por el conjunto de las 8 cuantiles, o referir explícitamente a §2.0-bis. *(Hoy L272 dice "T, C y VWAP" y L274 dice cuatro: se contradicen entre sí.)*
- **§2.3** — completar la tabla: faltan las filas **5–8** (σVc, σc, σVw, ΔσVw).

## BLOQUE 3 — Datos obsoletos
- **§2.0-ter** — actualizar al censo real: **4.581.546 obs / 566 tickers / 1962–2026**. **Eliminar "es imposible"** (L52): el backfill se completó y su propio punto 2 ya recomienda recalcular sobre el censo.
- **§2.3** — `n_tickers: 531` → **559/566** (el Anexo A ya lo declara *"propuesta, no dato"*).
- **§1.1** — cifras de `channel_snapshots` → **4.594.499 / 79 columnas**.

**Cierre:** aplicar todo antes de arrancar la FASE 2 del plan.
