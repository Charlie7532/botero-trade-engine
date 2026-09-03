# PROMPT: Reconstruir Data — SV5 como señal escasa (firma de techo, no 100% WR direccional)

**Fecha:** 03-Sep-2026
**Propósito:** Reconstruir/regenerar la data para que SV5 (`sv5t_silent_distribution`) quede como dictan los datos: **señal ESCASA cuya rareza ES el edge** (a mayor escasez, mayor probabilidad de techo/piso). **NO como "100% WR direccional" (que es una etiqueta retrospectiva engañosa).**

**Contexto de auditoría (ya verificado con datos):**
- La reconstrucción OHLC/Opción C del `bar_augment` ya está correcta (baselines 0.558/0.609/0.670, zz75 max 508 barras).
- El problema es la **semántica y métricas de SV5** en la cadena posicional/fallback.

---

## 1. El dato (rareza = riqueza, §3.3)

| Métrica | Valor |
|:--------|:------|
| Pivotes MAX totales | 795 |
| SV5 silencioso (D1 0-1, D3 3-4) en MAX | **22** |
| **Rareza** | **2.77% de los techos — solo 22 eventos en 33 años** |
| Coincidencia con techo | **22/22 = 100%** (`next_leg_direction=1` en todos) |
| WR direccional post-techo | **27.3%** (6/22), EV -2.46%, PF 0.27 |
| Distribución D3 de SV5 | D3=2: 480, D3=3: 95, D3=1: 82, D3=4: 14, D3=0: 16 |

**Interpretación correcta (lo que debes implementar):**
- SV5 es **escasa**: solo 2.77% de los techos la activan. Su valor reside en la **scareza** — cuando D3 está en el extremo (3-4) en un estado D1 bajo-inestable, es señal de techo.
- La coincidencia 22/22 es **firma de techo confirmado** (retrospectiva), NO WR direccional predictivo. El WR post-techo real de la dirección es 27.3% (la señal no predice la caída siguiente).
- **Error actual:** el `_CERTEZA` la etiqueta "100% WR en techos, PF=99.9" — mezcla la firma (22/22) con rendimiento direccional (que es 27%). Y el fallback del motor lee `cascade_50` (0.409) como hit rate en vez de `wl.win_rate` (0.273).

---

## 2. Correcciones a aplicar (reconstruir la data y la semántica de SV5)

### A. `arnes/señales.py` — corregir la etiqueta en `_registrar`
Remplazar:
```
validacion="RESCATADA — DIAMANTE SUPREMO (§3.3: N=20, 100% WR en techos MAX, Fwd=-4.63%, PF=99.9, CI95=[83.2%, 100.0%])"
```
por:
```
validacion="ESCASA — FIRMA DE TECHO (§3.3: N=22, 2.77% de techos, 22/22 coincidencia con techo confirmado; direccional débil: WR 27%, EV-2.5%, PF 0.27)"
```

**Regla de uso en `fuente`/`descripcion`:** SV5 es **firma de contexto** (precursora de techo por rareza), **NO** señal direccional de giro. Usar como filtro de convicción de techo, no como señal de entrada/salida direccional.

### B. `consultar_inteligencia.py` — fallback posicional: métrica correcta

En el fallback de señales posicionales (`sv5t_silent_distribution` + homólogas):
1. **Hit Rate = `wl.win_rate`** del `medicion_*.json` (0.273), **NO** `triada.cascade_50.rate_activa` (0.409).
2. **Eliminar el bypass RR hardcoded** (L445): quitar `or "DIAMANTE SUPREMO" in val or "VALIDATED" in val`. La regla `RR<1 -> NO OPERABLE` debe ser uniforme. (Si SV5 da RR<1, se marca NO OPERABLE como señal direccional — su rol es firma/filtro, no operativo direccional.)
3. **`bars_p90` y `mae_p95` con `np.percentile` REAL** sobre la distribución de `bars` y `|mae|`, **nunca** `media * 1.5` (que es fabricado).
4. Si SV5 se usa como firma/filtro (no señal direccional operativa), su `status`/`rol` puede indicar `FIRMA_TECHO` y el RR de operabilidad direccional se reporta como tal (no operable direccional, operable como contexto).

### C. Regenerar data reportando el rol de SV5
- Regenerar `bar_augment` ya está (no tocar método OHLC — correcto).
- Revisar que `medicion_sv5t_silent_distribution.json` y la ficha del motor reflejen: N=22, rareza 2.77%, 22/22 firma, WR 27.3% direccional.
- Reconstruir `data/research/signals/diamantes_cola.json` con SV5 categorizado correctamente: **firma de techo escasa**, no "diamante direccional 100%".

---

## 3. Verificación de aceptación

```bash
# 1. SV5 no se vende como "100% WR direccional"
python -c "
import json
c = __import__('arnes.registro', fromlist=['_CERTEZA'])._CERTEZA
v = c['sv5t_silent_distribution']['validacion']
assert '100% WR en techos MAX' not in v, 'Sigue la etiqueta engañosa'
assert 'SEÑAL ESCASA' in v or 'FIRMA DE TECHO' in v or 'scareza' in v
print('OK: SV5 etiquetada como señal escasa/firma de techo')
"

# 2. Hit Rate correcto en la ficha
python consultar_inteligencia.py senal sv5t_silent_distribution --scale zz50 | grep 'Hit Rate'
# Esperado: ~0.27 (no 0.41)

# 3. Sin bypass RR
grep -n 'DIAMANTE SUPREMO" in val\|VALIDATED" in val' consultar_inteligencia.py
# Esperado: 0 coincidencias

# 4. P90/P95 reales (no media*1.5)
grep -n '\* 1.5' consultar_inteligencia.py
# Esperado: 0 (bart_p90 usa np.percentile)
```

---

## 4. Alcance

**Hacer:** etiqueta SV5, HR correcto en fallback, quitar bypass RR, P90/P95 reales, regenerar `diamantes_cola` con SV5 como firma escasa.
**NO tocar:** `bar_augment.parquet` ya regenerado (OHLC/Opción C correcto); baselines; evaluación OHLC; el resto de la corrección ya validada.

**Regla rectora:** **rareza = riqueza** (§3.3). SV5 vale por ser escasa (2.77%) y coincidir con techo — no por un WR direccional que no tiene. La data debe decir eso, sin adornos.