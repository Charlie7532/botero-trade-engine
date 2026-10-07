# GUIDANCE — Continuación: cierre del bug `fatigue_type` + ajuste de los prompts de Tide

> **Sesión limpia, contexto autocontenido.**
> **Revisión de referencia:** `7a64cb2` + los cambios sin commitear del A1. Verifícala al arrancar y cítala.
> **Dos partes, en este orden:** (1) cerrar el bug que ya está a medio arreglar; (2) **poner al día los prompts** — el pendiente que quedó atrás.

---

## 0. CONTEXTO DEL HILO (para que no lo re-descubras)

**1. El bug `fatigue_type`.** Un refactor (`9823194`) eliminó `fatigue_type` y `fatigue_delta_ev` de `RealEVSignal` sin homologar a los consumidores. Efectos verificados por ejecución:
- `swing_gate.py:280` → la alerta `REAL_EV` **nunca se emite** (el `try/except` se traga el `AttributeError`).
- `swing_gate.py:653` (TRIM) y **`swing_entry_rules.py:115`** (ACCUMULATE, vía `swing_gate.py:518`) → **`AttributeError` no capturado: `SwingGate.evaluate()` crashea**.
- **6 archivos, 10 puntos de consumo** en total (barrido completo ya hecho).

**2. La adjudicación del arquitecto fue la opción A1** — restaurar el contrato con defaults canónicos en el DTO. **Ya está aplicada** (cambios sin commitear):
```python
# rc_tide_ev_lookup.py
fatigue_type: str = "STABLE"        # "ACCUMULATING", "FATIGUE_RISK", "STABLE"
fatigue_delta_ev: float = 0.0       # EV(run_bucket) - EV(bucket_1)
# (y en el constructor, L235-236)
```

**3. Dos asuntos que el A1 NO cubre** (quedaron abiertos, hay que decidirlos):
- **`rc_tide_lookup.py:206`** → `except Exception: pass` **sigue tragándose los errores de este contrato** en silencio.
- **`swing_gate.py:653`** → el umbral es `ev <= -0.0020` (NEGATIVO); en `45a3a13` era `self.ev < 0.002` (POSITIVO). **Cambio de signo no declarado en ningún sitio.**

**4. Y el pendiente de fondo:** los **prompts de Tide quedaron desactualizados** por todo lo de estos días. Eso es la Parte 2.

---

## PARTE 1 — CERRAR EL BUG (verificar el A1 y decidir lo que falta)

### 1.1 Verificación end-to-end (ejecutando, no leyendo)
Cada punto con **comando + salida real**:

| # | Qué verificar | Cómo |
|---|---|---|
| ① | El DTO ya tiene los campos | `'fatigue_type' in RealEVSignal.__dataclass_fields__` → **True** |
| ② | `SwingGate.evaluate()` **no crashea** | Correr el script real contra el Vault (el mismo que evidenció el crash) |
| ③ | La rama ACCUMULATE (L518 → `swing_entry_rules.py:115`) pasa | reproducir el caso que crasheaba (`ev >= 0.0020`, `p_bull >= 0.42`) |
| ④ | La rama TRIM (L653) con `ev > -0.0020` pasa | reproducir el caso |
| ⑤ | **La alerta `REAL_EV` se emite** | correr y **contar alertas REAL_EV emitidas** (antes: 0) |
| ⑥ | Los **10 puntos** del barrido ya no lanzan excepción | recorrer la tabla del barrido, uno por uno |
| ⑦ | El test roto (`test_real_tide_ev_lookup.py:28`) | ¿pasa ahora o sigue roto? |

### 1.2 Las dos decisiones abiertas — **presentar, no decidir**
- **El silencio del `rc_tide_lookup.py:206`**: ¿se quita el `except: pass`, se loguea, o se deja? *(Con A1 su efecto es benigno, pero el patrón sigue tapando futuras roturas.)*
- **El umbral del `swing_gate.py:653`**: ¿`-0.0020` es intencional o es un error de signo heredado del refactor? *(Referencia: `45a3a13` usaba `+0.002`. Es una **decisión de diseño**, no una limpieza.)*

**Documenta las dos con su trade-off y márcalas "a adjudicar".**

### 1.3 La prueba que impide la regresión
`test_tide_guidance.py` **no existe** (solo el `.pyc`). Añadir la prueba de contrato que falle si un `*Signal` se usa con un campo inexistente. Sin ella, el mismo bug puede volver en el próximo refactor — **y ya volvió una vez**.

### 1.4 Declarar el placeholder (no dejar que parezca dato real)
Con A1, `fatigue_type = "STABLE"` **es un valor por defecto, no una medición**. Debe quedar **escrito** en el código o en el commit:
> *"A1: contrato restaurado con defaults. La fatiga NO se calcula todavía (requiere `fatigue_buckets` en el Fact Store). El valor por defecto es un placeholder declarado, no una medición."*
Sin esto, el sistema parecerá "verde" midiendo una fatiga que no existe.

---

## PARTE 2 — EL AJUSTE DE LOS PROMPTS (el pendiente que dejamos atrás)

**Regla: ADDITIVE-ONLY.** Se **añaden notas fechadas**; **no se recorta, resume ni reformula** nada del contenido existente.

### 2.1 `2026-09-28-tide-reanudar-contexto.md` (Prompt de Recuperación)
**Verificado hoy:** su núcleo sigue exacto (su autotest da 4/4) **pero tiene cifras y estado viejos**:
- **Cifras obsoletas** (§1): dice `engine.channel_snapshots` = **213.100 snapshots / 72 columnas**. **Hoy son 4.594.499 / 79.** *(Y §3 dice "3 de 72 columnas" → hoy 3 de 79.)*
- **Su hallazgo #1 (el bug `fatigue_type`) ya está en corrección** → hay que **actualizar su estado**: pasa de "BUG LATENTE VIVO" a "en cierre por A1 (fecha), con 2 decisiones pendientes (L206 y umbral)".
- **Su baseline** (`e2a2ada` / `9823194`): son hitos históricos; añadir que **la baseline de ejecución es el HEAD al arrancar**.
- **Re-ejecutar su autotest (§8)** y anotar el resultado actual.

### 2.2 `2026-09-29-rediseno-ev-derived-escalas-adaptativas.md` (Brief de diseño)
Tiene su **guidance propio** (`.hermes/prompts/2026-10-02-guidance-revision-prompt-tide.md`), que **ya fue evaluado** por el ejecutor y produjo 5 hallazgos + 3 ajustes sugeridos. **Ese trabajo sigue pendiente de ejecución** — es la Fase 1 del plan.

**Nota para no confundir**: los dos "vwap" del sistema.
- `channel_snapshots.vwap_tide/current/wave` → el VWAP **rodante del canal**, **INTACTO**, es la dimensión VWAP del EV.
- `market.ohlcv_bars.vwap` → el VWAP **del día** (Alpaca), **RETIRADO** el 02-Oct.
**Son objetos distintos con el mismo nombre.** No los mezcles al ajustar el prompt.

---

## REGLAS

1. **Ejecutar ≠ leer.** Cada afirmación con comando y salida. Sin output, no hay hallazgo.
2. **No decidas los trade-offs de diseño** (1.2): presenta opciones y marca "a adjudicar".
3. **ADDITIVE-ONLY** en los prompts (Parte 2). Se añade, no se reescribe.
4. **No amplíes el alcance**: no toques el carril `vwap`/`trade_count` (cerrado) ni el diseño de Tide.
5. **Cada corrección de prompt con su fecha** y marcando qué decía antes.
6. **No declares "cerrado" lo que no verificaste** — el bug ya se declaró arreglado una vez sin estarlo.

---

## ENTREGABLE

**1.** Tabla de los 7 checks de la Parte 1 — `PUNTO | COMANDO | OUTPUT REAL | ¿PASA? | OBSERVACIÓN`.
**2.** Tabla de las 2 decisiones de 1.2, marcadas **"a adjudicar"**.
**3.** La prueba de contrato añadida (con su salida al correrla).
**4.** Las **notas aditivas redactadas** para los dos prompts (Parte 2), listas para pegar, con su fecha y su ubicación exacta.
**5.** Las dos listas obligatorias: *"Afirmaciones que NO debí hacer sin medir"* y *"No verificable aquí"*.
**6.** Y la respuesta corta: **¿el bug está cerrado de verdad — verificable hoy — o solo dormido?**
