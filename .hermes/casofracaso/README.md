# .hermes/casofracaso — ÍNDICE
## Documentos rescatados del incidente Gemini del 19-Ago-2026

---

## CRONOLOGÍA DEL INCIDENTE

```
19:04 — auditoria_ejercicio_exit_signals.md       ← PRE-INCIDENTE: code quality audit
20:12 — audit_complete_exercise.md                 ← DETECCIÓN: encontró los 5 fallos
20:18 — regano_formal_equipo.md                    ← INCIDENTE: regaño formal
20:48 — audit_propuesta_modularizacion.md          ← POST: meta-auditoría
20:52 — medicion_triada_factica_completa.md        ← POST: mediciones corregidas
21:04 — resultados_arnes_triada_factico.md         ← POST: validación cruzada
21:21 — implementation_plan.md                     ← POST: plan corregido
23:09 — diagnostico_prompting.md                  ← POST: Gemini diagnosticó su propio error
```

---

## ARCHIVOS RESCATADOS (5)

### 1. `fracaso-gemini-aislamiento-muestra.md` (17,183 bytes)
**Documento principal** — análisis del fracaso escrito por Hermes.
- 5 fallos documentados con datos exactos
- Diagnóstico de raíz: aislar muestra antes de validar
- Contraste con qwen3.8-max (por qué no falló)
- Plantilla anti-fracaso (9 checks)
- Lecciones extraídas

### 2. `auditoria_ejercicio_exit_signals.md` (11,229 bytes)
**Code quality audit de medir_senal.py** por Gemini.
- Score: 8.5/10
- 4 bugs de ingeniería (P1: RandomState vs default_rng, P2: import dentro de función, P3: ruta redundante, P4: nombre de paquete con ñ)
- 3 puntos ciegos metodológicos (MAX→UP 16.6%, contaminación MIN en bsi_recovery, cobertura temporal parcial)
- **Valor:** Estos bugs son REALES y no están relacionados con el fracaso de las señales. Son hallazgos de ingeniería que no caducan.

### 3. `diagnostico_prompting.md` (7,311 bytes)
**Autodiagnóstico de Gemini** sobre qué falló en su estilo de prompting.
- 4 aciertos del usuario (especificidad quirúrgica, sección PROHIBIDO, formato contrato, tabla de estado)
- 3 causas de complacencia (prompts conversacionales, frustración que reemplaza especificación, falta de criterio de aceptación)
- **Valor:** Es el documento donde Gemini APRENDIÓ. Contiene la receta para evitar que el incidente se repita.

### 4. `medicion_triada_factica_completa.md` (10,542 bytes)
**Mediciones corregidas** usando Mann-Whitney U + Fisher exact en las 3 escalas zigzag.
- Método corregido (no el método viciado del incidente)
- Puede contener datos válidos medidos con metodología correcta
- **Valor:** Si los datos son correctos, son reutilizables. Requiere validación.

### 5. `resultados_arnes_triada_factico.md` (4,832 bytes)
**Validación cruzada** entre historia (quants_obs) y prospección (fact store zigzag_kinematic).
- Compara mediciones en datos históricos vs. proyecciones del fact store
- Puede revelar sesgos entre lo que el fact store "cree" y lo que realmente pasó
- **Valor:** Metodología de validación cruzada reutilizable.

---

## ARCHIVOS NO RESCATADOS (se pierden al revertir el prompt)

### `audit_complete_exercise.md` (11,445 bytes)
La auditoría que detectó los 5 fallos. No se rescata porque:
- Su contenido ya está integrado en `fracaso-gemini-aislamiento-muestra.md`
- Las conclusiones que contiene (Yield Curve p=0.9746, BSI 68.9% activación, etc.) ya están documentadas

### `regano_formal_equipo.md` (7,198 bytes)
El regaño formal. No se rescata porque:
- Su contenido ya fue extraído y analizado en el caso de fracaso
- Es un documento de proceso, no de conocimiento técnico

### `audit_propuesta_modularizacion.md` (6,926 bytes)
Meta-auditoría post-incidente. No se rescata porque:
- Propone modularización basada en señales que luego fueron invalidadas
- Las propuestas arquitectónicas están contaminadas por el incidente

### `implementation_plan.md` (8,295 bytes)
Plan de implementación post-corrección. No se rescata porque:
- Basado en el "Sistema Protector Total V3" que contenía señales inválidas
- El plan está viciado por las señales que fallaron

---

## REGLAS EXTRAÍDAS DEL INCIDENTE

```
1. NUNCA aislar la muestra antes de validar en la muestra completa
2. NUNCA reportar cobertura sin p-value/Chi² de poder discriminante
3. NUNCA proponer "nueva capa" sin matriz de overlap con capas existentes
4. NUNCA reportar N sin N_eff corregido por clustering temporal
5. NUNCA usar prompts conversacionales para tareas de validación estadística
6. SIEMPRE incluir criterios de aceptación objetivos en cada prompt
7. SIEMPRE separar implementador de auditor (Gemini implementa, qwen3.8-max audita)
```

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 20-Ago-2026