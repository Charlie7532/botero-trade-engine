# PREGUNTA PENDIENTE — ¿El OOS es la herramienta para el pozo de catalogación?

**Fecha:** 05-Sep-2026
**Estado:** PENDIENTE — propuesta del usuario, no bloquea el plan de implementación actual. Mantener el foco.

## La pregunta
¿Sería el OOS la herramienta para el pozo de catalogación de señales por ventana (A2/A3/A4), o es definitivamente para otro propósito?

## Respuesta preliminar (a retomar después del plan de implementación)
- El OOS es **validación** (¿se repite la señal fuera de muestra?) — propósito distinto al de **catalogar roles por ventana** (descriptivo).
- El pozo (A2/A3/A4, secuencias, coincidencias) se construye con el **Evaluador General + timing_canonico** (ya en 36 señales), NO con el OOS.
- El OOS entra DESPUÉS para validar los roles más prometedores que salgan del pozo.

## Propuesta del usuario (definitiva al retomar)
+ Evaluar si el OOS (saneado, validador_oos.py) sirve como herramienta de validación del pozo de catalogación.

**No actuar sobre esto ahora — mantener el foco en responder al plan de implementación de Claude.**