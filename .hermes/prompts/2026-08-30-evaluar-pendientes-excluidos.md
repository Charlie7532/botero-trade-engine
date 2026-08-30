# PROMPT DE EVALUACIÓN — Pendientes Operativos y Excluidos

**Origen:** deepseek/deepseek-v4-flash (Hermes)
**Propósito:** Evaluar cada pendiente y excluido listado abajo — decidir si se acepta (ejecutar), se descarta (no hacer nunca), o se pospone (etapa futura).
**Criterios de evaluación:**
1. **Valor:** ¿Aporta edge medible, claridad o mantenibilidad?
2. **Esfuerzo:** ¿Cuánto tiempo/recursos requiere?
3. **Riesgo:** ¿Puede romper algo existente?
4. **Urgencia:** ¿Bloquea algo más?

---

## 🟡 PENDIENTES OPERATIVOS — Evaluar cada uno

### P1 — Migrar `build_continuous_metar_lake.py` a `backend/scripts/generators/`
**Estado:** ✅ Ya ejecutado por Opus (§13.2 del walkthrough)
**Veredicto:** Aceptado y completado.

### P2 — Clasificar 32 generadores en README_GENERATORS.md (3 capas)
| Criterio | Valoración |
|:---------|:-----------|
| **Valor** | Medio — un agente futuro no sabría cuáles ejecutar mensualmente |
| **Esfuerzo** | Bajo (~15 min crear el README) |
| **Riesgo** | Ninguno — es solo documentación |
| **Urgencia** | Baja — el conocimiento está en las personas, no en un archivo |

**Decisión sugerida:** ✅ Aceptar — crearlo ahora que el contexto está fresco.

### P3 — Establecer cron de regeneración mensual
| Criterio | Valoración |
|:---------|:-----------|
| **Valor** | Alto — sin cron, los fact stores/lake/quants_obs pueden quedar desactualizados |
| **Esfuerzo** | Medio (~20 min configurar cron + verificar) |
| **Riesgo** | Bajo — el cron ejecuta el mismo pipeline manual |
| **Urgencia** | Media — el Vault se actualiza a diario, los artefactos están desactualizados hoy |

**Decisión sugerida:** ✅ Aceptar — configurar cron mensual `0 0 1 * *`.

### P4 — Verificar que `agent_quick_reference.md` refleje los cambios del walkthrough §12
| Criterio | Valoración |
|:---------|:-----------|
| **Valor** | Alto — actualmente el archivo tiene edges correctos pero referenciaba un archivo que no existe (catalogo_31_senales) |
| **Esfuerzo** | Muy bajo (~5 min verificar) |
| **Riesgo** | Bajo — solo verificar que coincida |
| **Urgencia** | Media — agente futuro podría leer datos incorrectos |

**Decisión sugerida:** ✅ Aceptar — verificar y corregir si es necesario.

### P5 — Actualizar evaluador vela-a-vela (v2→v3)
| Criterio | Valoración |
|:---------|:-----------|
| **Valor** | Alto — el evaluador actual no evalúa las 3 señales V2 ni FG extremo |
| **Esfuerzo** | Bajo (~10 min: 4 cambios atómicos) |
| **Riesgo** | Medio — si se cambia el import de `medir_senal` a `arnes/`, hay que verificar que no se rompa |
| **Urgencia** | Media — el usuario ya pidió ejecutarlo |

**Decisión sugerida:** ✅ Aceptar — el prompt ya está listo.

---

## 🔴 EXCLUIDOS — Evaluar si realmente deben ser excluidos

### E1 — Benchmarks TIDE/wave/v37-v41
| Criterio | Valoración |
|:---------|:-----------|
| **¿Qué son?** | Scripts ML pesados en `backend/scripts/generators/` que producen tablas derivadas para investigación |
| **¿Pertenecen a METAR?** | ❌ No — son modelos independientes que consumen datos de METAR pero no son METAR |
| **Riesgo de excluirlos** | Bajo — no interfieren con el pipeline de señales |
| **Costo de mantenerlos** | Bajo — ya están en su lugar, no requieren mantenimiento activo |

**Decisión sugerida:** ❌ **Descartar** — no pertenecen a METAR.

### E2 — 158 scripts en research/02_ a research/11_
| Criterio | Valoración |
|:---------|:-----------|
| **¿Qué son?** | Artefactos de exploración histórica en sus propios directorios: cascade_conviction (24), estaciones_metar (26), conjuncion_multi (18), precursores_crash (1), metodologia_ldp (6), quality_swing_forensics (52), versioned_benchmarks (4), gate_oos_validation (3), experimental_engines (24) |
| **¿Deben ir a _legacy/?** | ❌ No — cada uno está en su propio directorio con nombre descriptivo. No están mezclados con el pipeline activo. |
| **Riesgo** | Ninguno — no importan desde el pipeline activo |
| **Valor de preservarlos** | Alto — contienen análisis que podrían retomarse (especialmente 06_metodologia_ldp con walkforward, y 07_quality_swing_forensics con más de 50 scripts de forensia) |

**Decisión sugerida:** ⏳ **Pospuesto** — no mover, no tocar. Preservar para referencia histórica.

### E3 — Señales V2 sin OOS (capitulacion_v2, euforia_v2, vix_crisis_spike_v2)
| Criterio | Valoración |
|:---------|:-----------|
| **¿Están listas?** | Sí — definidas en señales.py, evaluables por el evaluador vela-a-vela |
| **¿Tienen OOS?** | ❌ No — no pasaron por walk-forward |
| **¿Se pueden evaluar hoy?** | ✅ Sí — el evaluador v2→v3 incluirá sus blancos |
| **Valor** | Alto — muestran edges interesantes (+4.1%, −6.1%, +3.4%) |

**Decisión sugerida:** ⏳ **Pospuesto para etapa futura** — cuando se haga la ronda de validación OOS, incluirlas.

### E4 — `cascade_reversal` PROPOSED (p=0.25)
| Criterio | Valoración |
|:---------|:-----------|
| **Estado** | PROPOSED — calibrada con umbral −0.957 congelado |
| **¿Promovible?** | ❌ No — p=0.25 no es significativo. Fire rate 15% aceptable pero sin potencia |
| **¿Se puede mejorar?** | Posible — el walk-forward rolling p15 dio +0.44% (p=0.41), peor p-valor que el fijo |
| **Valor** | Bajo para operación, alto como alerta de cola |

**Decisión sugerida:** ⏳ **Pospuesto** — monitorear, no forzar. Si aparece un evento que lo valide, reevaluar.

### E5 — Reclasificación de skew (CAT-A)
| Criterio | Valoración |
|:---------|:-----------|
| **Estado** | Descartada por el usuario — disonancia estadística entre clasificadores |
| **¿Recuperaría algo?** | 23 disparos de panico_total (11→34) y 16 de skew_paranoia_exit (10→26) |
| **¿Vale la pena?** | ❌ No — recuperaría potencia estadística pero reintroduciría un clasificador bug (bins solapados) |
| **Riesgo** | Alto — reintroducir inconsistencias CAT-A |

**Decisión sugerida:** ❌ **Descartar definitivamente** — clasificador bug del one-off, no recuperar.

---

## 📋 TABLA DE DECISIONES — Para marcar

| ID | Pendiente | Decisión sugerida | ¿Acción? |
|:--:|:----------|:-----------------:|:--------:|
| P1 | Migrar lake builder | ✅ **Aceptado y ejecutado** | Ninguna |
| P2 | README generadores | ✅ **Aceptar — crear ahora** | Crear archivo |
| P3 | Cron mensual | ✅ **Aceptar — configurar** | Configurar cron |
| P4 | agent_quick_reference sync | ✅ **Aceptar — verificar** | Verificar + corregir |
| P5 | Evaluador v2→v3 | ✅ **Aceptar — ejecutar** | Prompt listo |
| E1 | Benchmarks TIDE/wave | ❌ **Descartar** | No tocar |
| E2 | 158 scripts research/02-11 | ⏳ **Pospuesto** | No mover |
| E3 | Señales V2 sin OOS | ⏳ **Pospuesto** | Evaluar en etapa futura |
| E4 | cascade_reversal PROPOSED | ⏳ **Pospuesto** | Monitorear |
| E5 | Reclasificación skew CAT-A | ❌ **Descartar definitivamente** | No recuperar |

---

## FORMATO DE ENTREGA ESPERADO

Para cada pendiente, marcar en la tabla:
- **ACEPTAR** — ejecutar ahora (sugerir orden)
- **DESCARTAR** — no hacer nunca (dar razón)
- **POSPONER** — hacer en etapa futura (dar condiciones para retomar)