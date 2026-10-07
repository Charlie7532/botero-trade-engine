# GUIDANCE — Bug de contrato `fatigue_type` en el gate Tide

> **Sesión limpia, contexto autocontenido.**
> **Revisión de referencia:** `7a64cb2` (HEAD al 02-Oct-2026). Verifícala al arrancar y cítala.
> **Naturaleza:** diagnóstico + corrección de un bug de producción. **No es un rediseño.**
> **Severidad: ALTA.** Está vivo, en producción, detectado hace 4 días y sin resolver.

---

## 0. EL HALLAZGO (verificado hoy, no inferido)

El **prompt de Recuperación de Hilo Tide** (28-Sep) lo marcó como *"BUG LATENTE VIVO"*. **Se re-ejecutó su autotest el 02-Oct y sigue vivo:**

```
backend/modules/quality_swing/application/use_cases/swing_gate.py
  L280:  f"fatigue={_real_ev.fatigue_type} "                          ← alerta REAL_EV
  L653:  if _real_ev and (_real_ev.ev <= -0.0020 or _real_ev.fatigue_type == "FATIGUE_RISK"):
                                                                      ← gate de decisión, rama TRIM

backend/modules/quality_swing/domain/rules/rc_tide_ev_lookup.py
  class RealEVSignal  →  NO tiene el campo `fatigue_type`             ← verificado
```

**Efectos (según el análisis previo, a confirmar por ti):**
- **(a)** La alerta `REAL_EV` **nunca se emite** — el `try/except` de alrededor se traga el `AttributeError`.
- **(b)** En la rama TRIM, cuando `_real_ev.ev > -0.0020`, **L653 lanza `AttributeError`**.

**Nota de simetría:** `RealWaveEVSignal` (usado en L330) **sí** tiene `fatigue_type` → esa línea está sana. **El problema es solo `_real_ev`.** *(Es la misma familia de bug que rompía 4 tests en ago-2026: `hazard_alarm` ausente en `RealEVSignal`.)*

---

## 1. LA TAREA

### Paso 1 — CONFIRMAR O REFUTAR, EJECUTANDO
No alcanza con leer el código. **Reproduce el fallo:**
1. Importa `RealEVSignal` e imprime sus campos (`__dataclass_fields__`) → evidencia literal.
2. Verifica si `'fatigue_type' in RealEVSignal.__dataclass_fields__` → esperado **False**.
3. Verifica lo mismo para `RealWaveEVSignal` → esperado **True**.
4. **Dispara el camino L653** con un caso donde `_real_ev.ev > -0.0020` y reporta la excepción real (archivo:línea + traceback).
5. **Cuenta cuántas alertas `REAL_EV` se emiten** en una corrida de `swing_gate` (esperado: cero, por el `except`).

**Reporta `archivo:línea` + comando + output real en cada punto.** Si algo no coincide con lo esperado, **detente y reporta**: un valor distinto puede ser dato nuevo.

### Paso 2 — BARRER LA FAMILIA (no parchear el caso)
Antes de tocar nada: **enumera TODOS los consumidores** de `fatigue_type` en el módulo, y **todos** los `*Signal` que se usan con campos que podrían no existir.

```
grep -rn "fatigue_type" backend/modules/quality_swing/
grep -rn "_real_ev\.\|RealEVSignal" backend/modules/quality_swing/
```
**Salida:** tabla `archivo:línea | consumidor | campo | ¿existe en el DTO? | estado (sano / roto)`.
*(La lección del proyecto: un bug de contrato rara vez está solo en una línea.)*

### Paso 3 — PRESENTAR LAS OPCIONES (no decidir)
Hay al menos tres caminos, **con semántica distinta**. Documéntalos con su trade-off y **marca la decisión como "a adjudicar"**:

| Opción | Qué implica | Riesgo |
|---|---|---|
| **A. Añadir `fatigue_type` a `RealEVSignal`** | El motor de EV tendría que **calcular** ese campo (¿de dónde sale el fatigue en la escala Tide?) | Hay que definir su semántica; si se rellena con un valor falso, se contamina la decisión |
| **B. Retirar las referencias** (L280 y la condición de L653) | El gate TRIM pasaría a depender **solo** de `ev <= -0.0020` | Cambia el **comportamiento del gate** — es una decisión de diseño, no una limpieza |
| **C. Derivarlo en el consumidor** | `swing_gate` lo computa desde lo que el DTO sí trae | Duplica lógica; hay que declarar de dónde |

**No elijas. Presenta.** La opción correcta depende de si el REAL_EV **debe** tener noción de fatiga — y eso es del arquitecto.

### Paso 4 — EJECUTAR LA OPCIÓN APROBADA
Cuando haya decisión: implementarla **y añadir la prueba de contrato** que impide la regresión.
*(Contexto: `test_tide_guidance.py` **no existe** — solo el `.pyc`. La suite no protege esta clase de error. Verifícalo.)*

### Paso 5 — VERIFICACIÓN END-TO-END
- La alerta `REAL_EV` se emite cuando corresponde.
- La rama TRIM no lanza excepción con `_real_ev.ev > -0.0020`.
- La prueba nueva falla si alguien vuelve a usar un campo inexistente.
- **Una corrida real de `swing_gate`** sin errores, con evidencia.

---

## 2. REGLAS

1. **Ejecutar ≠ leer.** Cada afirmación con su comando y su salida. Sin output, no hay hallazgo.
2. **No decidas el trade-off de diseño** (Paso 3): presenta opciones, marca "a adjudicar".
3. **Barre la familia** antes de parchear: no arregles solo la línea que se ve.
4. **No amplíes el alcance.** No toques el diseño de Tide, ni los JSON de tablas, ni el brief de rediseño (eso es otro carril, con su propio guidance).
5. **No "arregles" cambiando el comportamiento en silencio.** Si la opción B altera el gate TRIM, eso se declara explícitamente.
6. **Evidencia bilateral**: verifica que el bug **está** donde se dice **y** que **no está** donde no se dice (L330, el `_wave_ev`).

---

## 3. ENTREGABLE

**3.1 Tabla de confirmación:**
```
PUNTO | COMANDO | OUTPUT REAL | ¿CONFIRMA? | OBSERVACIÓN
```

**3.2 Tabla del barrido de familia** (Paso 2).

**3.3 Tabla de opciones** (Paso 3) con su trade-off y la decisión **marcada como pendiente de adjudicación**.

**3.4 Dos listas obligatorias:**
- *"Afirmaciones que NO debí hacer sin medir."*
- *"No verificable aquí"* (con qué haría falta).

**3.5 Y la respuesta corta:**
> **¿El bug está activo hoy en producción?** Sí/No, con la evidencia de ejecución que lo sostiene.

---

*Contexto: este hallazgo no es nuevo — está en el prompt de Recuperación desde el 25-Sep. Lo que cambia hoy es que se re-verificó y **sigue vivo**. Es el único asunto de este plan que afecta a producción ahora mismo, y por eso va primero.*
