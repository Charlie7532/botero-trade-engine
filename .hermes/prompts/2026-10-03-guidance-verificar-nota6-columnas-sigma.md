# GUIDANCE — Verificar la nota 6 y las columnas de las dimensiones σ · Tide v2

> **Sesión limpia · autocontenido.**
> **Revisión de referencia:** `6e1da582` (HEAD actual del prompt). Verifícala y cítala.
> **Instrucción:** ejecuta las 6 verificaciones. **Cada una con comando y salida real.** Al final, dictamina si el prompt debe corregirse y qué exactamente.

---

## 0. QUÉ SE PONE EN DUDA

El prompt afirma, en **§2.0-bis nota 6 [03-Oct]**:

> *"**Hecho verificado:** VWAP (fila 4, Tide) y σVw (fila 7, Multiscale) leen la **misma columna** `vwap_sigma_wave` (`train_tide_ev_real_table.py` L242 y `train_multiscale_kinematic_ev_tree.py` L310). Es una sola distribución por ticker: los edges de 6 bins y los de 5 bins salen de ella."*

**Un chequeo preliminar sugiere que esto es falso.** Si lo es, el diseño calibraría los edges de σVw contra la distribución de **otra variable**.

**Regla: no aceptes la nota ni la refutes sin medir.** Los 6 puntos siguientes son la medición.

---

## V1 — ¿La L310 del trainer de Multiscale lee `vwap_sigma_wave` o `sigma_wave`?

**Comando:** imprimir **las líneas 305–315** de `backend/scripts/trainers/train_multiscale_kinematic_ev_tree.py` y **las 238–246** de `backend/scripts/trainers/train_tide_ev_real_table.py`.

**Reportar:** el nombre **literal** de la columna que cada trainer pasa a su clasificador de σ. Nada más. Si difieren, la nota 6 es falsa.

---

## V2 — ¿Son la misma distribución? Medirlo, no inferirlo

**Comando:** sobre `engine.channel_snapshots`, para SPY y para el censo, extraer `vwap_sigma_wave` y `sigma_wave` y calcular **correlación** y **percentiles** de ambas.

**Criterio:** si la correlación es alta y positiva (≈ +0.9), podrían ser la misma serie. Si es **negativa** o cercana a cero, **son variables distintas**. Reportar el número, no la impresión.

---

## V3 — Nombres reales de columna por dimensión

**Comando:** listar las columnas de `engine.channel_snapshots` que contienen `sigma` / `delta` / `traj` / `vel`, y **contrastarlas con la tabla del §2.0-bis** (filas 4, 5, 6, 7, 8).

**Reportar:** tabla `DIMENSIÓN | NOMBRE EN EL PROMPT | COLUMNA REAL EN EL VAULT | ¿COINCIDE?` para **cada** una de las 8 dimensiones de cuantil. Se espera encontrar varias discrepancias.

---

## V4 — ΔσVw (dim 8): ¿de dónde sale realmente?

El prompt dice que su variable cruda es `delta_sigma_vwap_wave`.
**Comando:** verificar si esa columna **existe** en el Vault. Si no existe, buscar la fuente real del ΔσVw en el trainer de Multiscale (`classify_sigma_bin` sobre qué columna opera) y reportar la candidata.

**Pista:** existe una columna `vol_adj_delta`. **Confirmar si es eso — no asumirlo.**

---

## V5 — La sospecha de la columna mal nombrada

Una medición preliminar (4 barras de SPY) dio:
```
corr(vwap_sigma_wave, sigma_wave)   = −0.97
corr(vwap_sigma_wave, sigma_tide)   = +0.995
corr(vwap_sigma_wave, sigma_current)= +0.963
```
→ **Una columna llamada `..._wave` que se comporta como la de `tide`.**

**Comando:** medir esas tres correlaciones **sobre el censo completo** (o muestra amplia y declarada), por ticker y pooled. **Reportar los números.**
**Si se confirma**, no es un problema de nomenclatura: es **una columna que contiene la variable equivocada**, y afecta a todo lo que la consuma.

---

## V6 — Alcance del daño si la nota 6 cae

**Comando:** buscar todos los consumidores de `vwap_sigma_wave` en el repo (`--include=*.py`) y clasificar cada uno según **qué dimensión cree estar leyendo**.

**Reportar** en tabla: `CONSUMIDOR | CREE LEER | LEE REALMENTE | IMPACTO`.

**Puntos concretos a revisar además:**
- **§2.3** — la frase *"σVw comparte columna con VWAP, ver §2.0-bis nota 6"*, que justifica que σVw **no** tenga entrada propia en el perfil.
- **§2.1** — la nota que asigna a las dimensiones de 5 bins los 4 percentiles `[0.0228, 0.1587, 0.8413, 0.9772]`. ¿La distribución sobre la que se calculan es la correcta para **cada** σ?
- **§2.3, esquema JSON** — el perfil debe declarar una entrada por dimensión con **su** columna fuente.

---

## REGLAS

1. **Ejecutar ≠ leer.** Cada afirmación con comando y output. Sin output, no hay hallazgo.
2. **No ancles la conclusión.** Mide primero; el veredicto sale de los números.
3. **No corrijas nada en este paso.** Este guidance **verifica**, no edita.
4. **Reporta lo que no puedas verificar**, explícitamente.

---

## ENTREGABLE

1. **Tabla V1** — columna literal que lee cada trainer, con la línea exacta.
2. **Tabla V2/V5** — las correlaciones medidas, con el comando y el tamaño de muestra.
3. **Tabla V3** — `DIMENSIÓN | PROMPT | VAULT | ¿COINCIDE?` para las 8 dimensiones.
4. **V4** — la fuente real de ΔσVw, confirmada o refutada, con la línea del trainer.
5. **Tabla V6** — consumidores y su impacto.
6. **Las dos listas obligatorias:** *"afirmaciones que no debí hacer sin medir"* y *"no verificable aquí"*.
7. **Dictamen final — obligatorio, en una frase:**
   > *¿La nota 6 se sostiene, o el prompt debe corregirse?*
   Con la lista exacta de líneas a corregir, si procede.
