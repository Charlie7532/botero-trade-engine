# GUIDANCE — Corregir: umbral del TRIM, `except` mudo, y contratos sin tipo

> **Revisión de referencia:** verifícala al arrancar y cítala (`git rev-parse HEAD`).
> **Instrucción: evalúa este guidance y ejecuta las correcciones.** Si algo no cuadra con el repo, repórtalo en vez de forzarlo.

---

## CORRECCIÓN 1 — Alinear el umbral del TRIM con su spec

**Estado actual:**
```python
# backend/modules/quality_swing/application/use_cases/swing_gate.py:653
if _real_ev and (_real_ev.ev <= -0.0020 or _real_ev.fatigue_type == "FATIGUE_RISK"):
```

**Lo que dice el spec:**
```
docs/modules/quality_swing/tide/REAL_EV_LOOKUP_SPEC.md:191
  | STK_T_TRIM_TACTICAL | TRIM | `ev < -0.008 or (vwap_bin in (">>", ">") and T in ("T+++", "T+"))` |
docs/modules/quality_swing/tide/REAL_EV_LOOKUP_SPEC.md:99
  TAX_RULES -->|"ev < -0.8% o Trim Peak"| A4
```

**Tarea:**
1. **Verifica las 3 versiones** (spec `-0.008` · código `-0.0020` · `45a3a13` `+0.002`) reproduciendo cada una con comando + salida. Si el spec dice otra cosa en otra sección, **reporta la contradicción**.
2. **Determina cuál es la vigente** y **aloja la corrección en el lugar arquitectónicamente correcto** (si la decisión pertenece al motor EV y no al gate, muévela allí — **no dupliques la regla en dos capas**).
3. **El segundo disparador del TRIM**: el spec dice `vwap_bin in (">>", ">") and T in ("T+++", "T+")`. **Hoy el código usa `fatigue_type == "FATIGUE_RISK"` en su lugar** ✗. Reporta si falta ese disparador y si hay que restaurarlo.
4. **Declara el cambio**: comentario en el código + mensaje del commit, con el valor anterior, el nuevo y la referencia al spec.

---

## CORRECCIÓN 2 — El `except` mudo

**Estado actual:**
```python
# backend/modules/quality_swing/domain/rules/rc_tide_lookup.py:207
        except Exception:
            pass
```
*(Y es el mecanismo que ocultó el bug del `fatigue_type` durante días.)*

**Tarea — distinguir dos naturalezas de fallo, no una:**
| Fallo | Tratamiento |
|---|---|
| **El recurso no está** (JSON/tabla ausente, el Vault sin datos) | degradar **con log explícito** (nivel warning), declarando el valor por defecto que se usa |
| **Error de contrato** (el DTO no tiene un campo que el consumidor usa) | **NO capturar** — debe propagar y fallar fuerte |

**Requisito:** que ningún camino vuelva a terminar en `pass` mudo. **Barre la familia completa** (no solo esta línea): busca todos los `except` que terminan en `pass` en `backend/modules/quality_swing/` y reporta cuáles quedan y por qué.

---

## CORRECCIÓN 3 — Contratos sin tipo (la raíz común)

**Los dos fallos anteriores son la misma enfermedad:** un contrato declarado en un comentario, movido por refactors, sin nada que lo vigile. Ya ocurrió **tres veces**: `fatigue_type`, y los enums de `signal` / `action_code`.

**Tarea:**
1. **Tipar los contratos**: convertir a `Literal[...]` o `Enum` los campos hoy `str` libre:
   - `RealEVSignal.signal` y `.action_code` (y equivalentes en `RealWaveEVSignal`).
2. **Reconciliar las 3 listas divergentes** de `signal` (spec 6 valores · comentario 4 · código asigna 5) y los **dos namespaces** de `action_code` (`STK_*` en el módulo vs `ACTION_STK_T_*` en los scripts). Reporta cuál es el canónico y qué se hace con el otro.
3. **Test de contrato**: que falle si (a) el código emite un valor fuera de la lista canónica, o (b) un consumidor chequea un valor **que nunca se emite** (hoy hay varias ramas así).
4. **Marca los valores no consumidos** (p. ej. el `signal == "BLOCK"` no lo lee nadie): decide si se consumen, se eliminan o se declaran.

---

## REGLAS

1. **El spec es la autoridad.** Si el código y el spec divergen, se alinea — o se modifica el spec y **se declara**.
2. **Ejecutar ≠ leer**: cada afirmación con comando + salida.
3. **No decidas en silencio.** Todo cambio de umbral, de captura de errores o de valores de contrato: **declarado en el código y en el commit** (valor anterior → nuevo → motivo).
4. **Barre la familia**, no la línea que se ve.
5. **No amplíes el alcance**: no toques el carril `vwap`/`trade_count` (cerrado) ni el rediseño de Tide.
6. **Si el spec y el diseño te parecen equivocados**, no los cambies por tu cuenta: **repórtalo**.

---

## ENTREGABLE

1. **Tabla** `PUNTO | COMANDO | OUTPUT REAL | ¿CONFIRMA? | CORRECCIÓN APLICADA` para las 3 correcciones.
2. **Las 3 listas reconciliadas** (los valores canónicos de `signal` y de `action_code`, con su fuente).
3. **El barrido de la familia** del `except`: cuántos quedan y su tratamiento.
4. **La salida real de los tests** (los existentes + los nuevos) tras cada cambio.
5. **Dos listas**: *"afirmaciones que no debí hacer sin medir"* y *"no verificable aquí"*.
6. **Respuesta corta:** ¿el umbral del TRIM quedó alineado al spec? Sí/No, con el valor final y su comando de verificación.
