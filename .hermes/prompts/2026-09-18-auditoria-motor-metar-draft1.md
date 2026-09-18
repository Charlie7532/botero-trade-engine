# PROMPT DE AUDITORÍA — Motor METAR: alineación de módulos, tratamiento de señales intermedias y coherencia

> **Fecha:** 2026-09-18 · **Versión prompt:** DRAFT 1 (se enriquece tema a tema)
> **Repo:** /root/botero-trade · **Intérprete:** backend/.venv/bin/python3 · **Respuesta:** español
> **Rol:** El agente VERIFICA empíricamente con scripts y reporta. NO modifica código — reporta y propone fixes (Rule 22).

---

## FUENTE DE VERDAD
**Documento de hallazgos:** `.hermes/auditorias/2026-09-18_hallazgos_consolidados_metar.md` (leer primero)
**Cita rectora:** Los indicadores emiten HECHOS, no directivas. No degradar a "NOISE" una señal con coherencia real.

---

## TAREA 1 — [A] Consistencia de CAT entre station_profiles y family_sequence
- **Hecho a verificar:** `fg` tiene `station_profiles.cat=2` (CAT2_SENTIMENT) pero `family_sequence.STATION_CATEGORIES['fg']=CAT3_ACTION`. Único mismatch de 11.
- **Verificar:**
  1. ¿family_sequence usa su propio STATION_CATEGORIES o prof.cat? (ya verificado: usa el suyo, L381)
  2. ¿El `station_cat` del output del discriminator (L846) es consumido por alguna lógica de decisión, o es solo rotulado?
  3. **Decidir:** ¿alinear `fg→cat=3` es seguro (no cambia decisión)? ¿Afecta a algún consumidor que espere cat=2?
- **Entregable:** confirmar/refutar que el cat=2 de fg es cosmético; recomendar el fix si procede.

## TAREA 2 — [B] Inconsistencia de escala: sgs (ratio) vs scale_gradient (diferencia)
- **Hecho a verificar:** coexisten `sgs=(hr75-hr25)/hr25` (timing_context L317) y `scale_gradient=hr75-hr25` (signal_discriminator L1298). 14.4% de estados cambian según cuál se use.
- **Verificar:**
  1. ¿Cuál es la definición CANÓNICA que el sistema adopta para clasificar STRUCTURAL/TACTICAL/FLAT?
  2. ¿El `_compute_floor_concordance` usa el `sgs` (ratio) pero la clasificación principal de escala usa `scale_gradient` (diferencia)? → ¿se contradicen?
  3. **Cuantificar el impacto real:** ¿cuántas señales clasificadas cambian de FLOOR/TRAP por esta inconsistencia en la práctica?
- **Entregable:** unificar a UNA definición (recomendado: ratio `sgs`, robusto). Proponer fix quirúrgico y validar que no cambia resultados legítimos.

## TAREA 3 — [C] `timing_mode=NOISE` artefacto de umbral per-slot (CRÍTICA)
- **Hecho a verificar:** el `timing_mode` queda NOISE por defecto (timing_context L344) y solo cambia si UN slot individual tiene n≥5 con edge>0.15 (L351-361). **96% de intermedias (5-9) con coherencia alta (pct_rango≥60%) quedan NOISE.**
- **DEFINICIÓN DE COHERENCIA (la que debe usar el agente):** *coherencia temporal posicional* = qué proporción de los episodios de la señal caen dentro de ±2 velas de un pivote zigzag (`pct_en_rango`). Alta (≥60%) = la señal dispara sistemáticamente cerca de giros → señal real con patrón, NO ruido. Baja (<40%) = disparos al azar sin relación con giros → ruido genuino.
- **Verificar:**
  1. Replicar la lógica: ¿el `pct_en_rango` se ignora para el `timing_mode`? (preverificado: sí — solo mira slots individuales, n≥5, no usa pct_en_rango)
  2. **Confirmar la contradicción:** estados con `signal_class=STRUCTURAL_FLOOR` Y `pct_en_rango=100%` pero `timing_mode=NOISE`. (Visto: bsi `0__0__3`, credit `1__0__2`.)
  3. **Proponer la regla correcta** (basada en la definición de coherencia):
     -⚠️ **"Fuera de rango" NO es sinónimo de ruido.** Una señal puede estar mayoRmente FUERA DE RANGO y ser legítima — señal de CONTINUACIÓN en la dirección (tendencia/persistencia) o de FUERZA de movimiento. La clasificación correcta es por la MAYORÍA relativa:

| Categoría | Criterio | Interpretación |
|:----------|:---------|:---------------|
| **EN RANGO (↓)** | mayoría dentro de ±2 velas de giros | Señal de GIRO (anticipa/exacta/confirma inversión) — canario, pivote, institucional |
| **FUERA DE RANGO (→)** | mayoría en ENTRE, lejos de giros | Señal de CONTINUACIÓN / FUERZA DE MOVIMIENTO (tendencia, régimen persistente) — señal real, NO ruido |
| **ERRÁTICA (ruido)** | NI dentro NI fuera — dispersa sin patrón dominante | **Ruido genuino** (si ni agrupa en giros ni agrupa en continuación) |
- **Entregable:** confirmar la cifra 96%, y proponer el nuevo umbral (coherencia posicional) que no degrade señales coherentes a ruido.

## TAREA 4 — [H] Investigar `floor_sgs=0.0` sospechoso (PENDIENTE)
- **Observación:** bsi `0__0__3` con hr75 y hr25 altos da `floor_sgs=0.0`. Sospecha de mal cómputo con N bajo (hr25=hr75 por pocos datos).
- **Verificar:**
  1. Para estados intermedias con N bajo, ¿el SGS se computa correctamente o el hr25/hr75 con pocos datos los fuerza a iguales → sgs=0?
  2. Cuantificar cuántos estados tienen `floor_sgs=0.0` injustificadamente (hay hr variadas pero el ratio da 0).
- **Entregable:** confirmar/subsanar el cómputo del SGS para N bajo.

## TAREA 5 — [E] Coherencia temporal de señales intermedias (5-9)
- **Hecho a verificar:** el 38% de intermedias tiene pct_en_rango≥60% (patrón), 36% disperso, 26% mixto.
- **Verificar, por señal intermedia con patrón (pct_rango≥60%):**
  1. ¿Sus episodios se agrupan temporalmente en eventos/regímenes de mercado relacionados (uniformidad → señal real)?
  2. ¿O se distribuyen sin patrón en el tiempo (azar → ruido)?
  3. Usar las fechas de `caso_de_estudio` / episodios para medir la agrupación (nearby events).
- **Entregable:** clasificar cada intermedia coherente como SEÑAL (con su evento) o confirmar que es ruido — con evidencia temporal.

## TAREA 6 — [D] Señales intermedias (5-9): el discriminator YA las clasifica bien
- **Hecho a verificar:** NOISE 8.4% (menor), FLOOR 68%. Contra la hipótesis de "N bajo→ruido".
- **Verificar:** confirmar la distribución por banda y que las intermedias con patrón producen FLOOR legítimo (no por azar de N).
- **Entregable:** tabla de confirmación.

## TAREA 7 — [G] Validación INDEPENDIENTE de umbrales de concordancia
- **Defecto previo:** la validación reusó `_compute_floor_concordance` (circular).
- **Verificar:** computar las 7 condiciones C1-C7 con implementación INDEPENDIENTE (leer métricas crudas del timing store, aplicar condiciones a mano) y re-medir la monotonicidad score→HR75 sin reusar la función del discriminator.
- **Entregable:** monotonicidad independiente — confirmar/corregir los umbrales.

---

## ENTREGABLES GENERALES
- Un reporte por tarea (en español, con tablas de datos reales).
- Los fixes propuestos deben ser QUIRÚRGICOS (archivo, línea, cambio) y esperar aprobación (Rule 22) — NO aplicarlos sin autorización.
- **Eje transversal:** respetar la cita (hechos vs directivas) y NO degradar señales coherentes a ruido.

## VERIFICACIÓN ACUMULADA (para cada tarea)
- [ ] ¿El número del hallazgo se confirma con datos reales?
- [ ] ¿Se cuantifica el impacto (no solo se describe)?
- [ ] ¿El fix propuesto es mínimo y no rompe otros consumidores?
- [ ] ¿Se respeta la cita rectora?