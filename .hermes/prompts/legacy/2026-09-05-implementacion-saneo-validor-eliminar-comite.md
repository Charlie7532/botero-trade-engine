# PROMPT: IMPLEMENTACIÓN — Sanear el Validador OOS + eliminar el comité votante + CONSERVAR el Evaluador General (la fuente de verdad sana)

**Fecha:** 05-Sep-2026
**Base:** Plan de Claude (`implementation_plan.md` del brain Antigravity) — adoptado con correcciones.
**Ejecutor:** Claude/ejecutor.

---

## 🎯 QUÉ SE CONSERVA vs QUÉ SE ELIMINA (decisión del usuario, NO negociable)

### ✅ SE CONSERVA: **EL EVALUADOR GENERAL** (`evaluador_general.py`) — la fuente de verdad de calificación
**Dato verificado (no relato): es el sistema SANO que DISCRIMINA.**
Sus 6 señales validadas con p_BH reales:
| Señal | score | p_BH | estado |
|:------|:-----:|:----:|:------:|
| fg_extreme_fear | 22.4 | 0.02 | 💎 DIAMANTE |
| dxy_bearish | 18.1 | 0.0 | VALIDADA |
| vvix_entry | 15.1 | 0.03 | VALIDADA |
| defensive_rotation_divergence | 14.2 | 0.0 | VALIDADA |
| vix_crisis_spike | 14.0 | 0.04 | VALIDADA |
| bsi_compression_entry | 10.3 | 0.0 | VALIDADA |

**Gap de separación: 9.19 puntos** entre validadas (score 15.69) y no validadas (6.50). **DISCRIMINA claramente lo bueno de lo malo.** Este es el instrumento que predecía y NO se toca.

**DESCARTADO el error de contexto:** NO se conserva "un agente del comité" como si fuera el instrumento sano. Los agentes del comité son parte del sistema defectuoso que se elimina. Lo que se conserva es el **Evaluador General** + el **timing_canonico** que produce (base del futuro pozo de catalogación A2/A3/A4). **No se inventa un "agente de referencia" — se defiende el Evaluador General, que es el que discrimina.**

### ❌ SE ELIMINA: el comité votante (`comite_metar/`)
- Los **11 agentes como comité votante** (conjeturan direcciones y se fusionan) — sistema roto (potencia N≥50 cero, OBSERVAR destructor).
- `curador/`, `modelador/` (el OOS paralelo), `run_comite.py`, `scripts/` del comité.
- **El conocimiento NO se pierde:** las métricas estadísticas puras de valor (`edge_direccional`, `clopper_pearson_ci`) se migran a `arnes/`. `_direccion_spy` (heurística manual redundante con fact stores) queda con decisión pendiente del arquitecto (archivar o descartar) — no se asume como activo.

---

## Fase 0: Eliminar el comité votante, migrar lo valioso

1. **Verificar dependencias:** `grep -rn "comite_metar" backend/ research/ tests/ --include="*.py"` → confirmar que solo `comite_metar/` se referencia a sí mismo. Documentar cualquier ref externa.
2. **Sobre `_direccion_spy` (heurística de interpretación por estación):** separarla de las métricas estadísticas. **No es parte del OOS legítimo** (el validador OOS NO la usa — verificado: solo la usa `_agente_base.py`). Es una **regla manual sin validar, redundante con los fact stores/perfiles**. DECISIÓN DEL ARQUITECTO PENDIENTE (no forzar): (a) archivar como referencia de semántica manual, o (b) descartar con el comité por redundancia. NO migrarla como activo de producción sin esa decisión.
3. **Migrar SÓLO las métricas estadísticas puras de valor:** `edge_direccional()` y `clopper_pearson_ci()` de `modelador.py` → a `arnes/estadisticas.py`. **Verificar imports** para no crear ciclos: se definían localmente en modelador; al moverse, confirmar que no dependan de `comite_metar`.
4. **Eliminar** el resto de `comite_metar/` (agentes, curador, modelador, run_comite, scripts). No se conserva el archivo `_agente_base.py` dependiente (sus imports a `comite_metar` lo harían inútil al borrar el directorio).

## Fase 1: Sanear el Validador OOS legítimo (`research/10_gate_oos_validation/validador_oos.py`)

Aplicar las 4 correcciones. **⚠️ ADVERTENCIA DE IMPACTO: cambiar de close-only a OHLC+time-stop PUEDE cambiar/desvalidar señales** que antes se validaban — es el resultado correcto de una metrología más rigurosa, pero el ejecutor debe reportar qué cambió y por qué, no ocultarlo.

**Corrección 1 — Inception Policy (BLOQUEANTE):**
- Cada señal usa su `fecha_inicio_valida` de `_CERTEZA`.
- Folds de train empiezan en `max(T0, inception_señal)`, no en 1993. Folds con test pre-inception se saltan.

**Corrección 2 y 3 — OHLC intrabar + Time-Stop C9:**
- Reemplazar `first_passage(prices, t, thr, blanco)` (close-only, sin stop) por `first_passage_bar(close, highs, lows, t, scale, blanco, max_barras)` del Evaluador General (importar a `arnes/medicion.py` o copiar).
- `max_barras = ceil(2/scale)` → zz25=80, zz50=40, zz75=27. Timeout = fracaso.

**Corrección 4 — Serie continua:** optar por serie continua si viable (evita sesgo de solo-pivote). Si complejo, documentar la limitación.

## Fase 2: Inyectar las mejoras reales (migradas a `arnes/`)
- **Edge direccional condicionado** + **`clopper_pearson_ci`** en `arnes/estadisticas.py`: por celda reportar `edge_alza`, `edge_baja`, `ci95`, `p_greater` por dirección.
- **CI95 Clopper-Pearson** en diamantes §3.3.
- **Smoke-test causal** `assert_sin_lookahead()`.

## Fase 3: Verificar / salidas
- Re-ejecutar `validador_oos.py`. **`cascade_reversal` debe mantener 9/9 folds + y `p_bonferroni = 0.004`** (dato verificado del JSON, NO 0.002).
- Señales post-2011 (skew, vvix) pierden folds tempranos — CORRECTO.
- Confirmar: repo sin `comite_metar`, sin refs rotas, `arnes/` aloja las funciones migradas y compila.

---

## CRITERIOS DE ACEPTACIÓN
1. **Evaluador General intacto** (sigue discriminando — sus 6 señales validadas permanecen; ninguna función del catálogo se rompe).
2. Comité votante eliminado; `edge_direccional`, `clopper_pearson_ci` migradas a `arnes/` y compilando. `_direccion_spy` decidida (archivada o descartada) según criterio del arquitecto — NO migrada como activo sin esa decisión.
3. `validador_oos.py` saneado con las 4 correcciones.
4. `validador_oos.py` corre: `cascade_reversal` 9/9 folds, p_bonferroni=0.004, señales post-2011 con folds correctos por inception.
5. Sin refs rotas (grep comite_metar solo devuelve doc); tests pasan.
6. El ejecutor reporta la tabla antes/después del cambio OHLC+time-stop (qué señales cambiaron de veredicto y por qué).

**Principios:** Dato mata relato. **El Evaluador General es el instrumento sano que discrimina — se defiende y conserva.** El comité votante es el instrumento defectuoso — se elimina, pero su conocimiento (funciones puras) se migra a `arnes/`, no se tira. No inventar 'agentes de referencia': lo que se conserva es el Evaluador General + timing_canonico.