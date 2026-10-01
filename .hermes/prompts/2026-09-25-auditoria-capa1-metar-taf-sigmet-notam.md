# PROMPT DE AUDITORÍA — Botero Trade · Capa 1 (METAR/TAF/SIGMET/NOTAM)

**Destino:** Claude Guiada (auditor)
**Fecha:** 2026-09-25
**Preparado por:** Hermes (guiar/auditar/construir prompts — NO programar)

---

## ROL
Eres un **AUDITOR independiente** de producción. Tu tarea es **DIAGNOSTICAR y REPORTAR**, no aplicar fixes. Separa SIEMPRE en tu entregable el bloque `DIAGNÓSTICO` del bloque `FIXES PROPUESTOS` (sin aplicarlos). El humano decide qué corregir después.

## REGLA ANTI-CORTOCIRCUITO (leer ANTES de tocar cualquier código)

Este proyecto tuvo un cortocircuito por confundir **código nuevo con código viejo**. Para evitarlo, MEMORIZA esta separación y respétala en TODO tu diagnóstico. Si un archivo/función NO aparece en la columna NUEVO, NO lo trates como producción canónica.

| Categoría | VIEJO / NO PRODUCCIÓN (no auditar como motor) | NUEVO / PRODUCCIÓN CANÓNICA (auditar ESTA) |
|---|---|---|
| **SIGMET** | `evaluate_market_sigmets()` — standalone duplicada, solo la usa el router `/sigmet` como **fallback** cuando no hay snapshot. Duplica lógica estación por estación. ⚠️ Fue la que dio los errores `action_code`/`turbulence_value` con datos en caché viejos — NO es el motor roto, es la duplicada. | `evaluate_sigmets_from_metar_dicts()` — **LA PRINCIPAL**. La usa el daemon `metar_compositor_provider.py` (L86-143) y el router `metar.py` (L284-302). Recibe `report.metar_snapshots` + `report.family_sequence`. **AUDITA ESTA.** |
| **TAF** | `_build_taf_entry` / `taf_station_codes` en `convergence_compositor.py` — **NO EXISTEN** (referenciados en un doc de research viejo, líneas 214-232 de una versión anterior). NO los busques ahí. | `taf_service.py` — `TafCone` + `compute_taf_cone()` + `compute_composite_taf_from_summaries()`. **ESTE ES EL TAF REAL.** |
| **Fuente de datos** | `data/research/pivots/quants_obs.pkl` — research pivots, **puede estar congelado** (ej. 2026-07-15 cuando el feed ya está en 09-24). NO lo uses para "estado de hoy". | **Capa 0 de datos: fact_store + timing_store COEXISTEN** (no se fusionan, son complementarios). Ambos en `backend/modules/entry_decision/domain/rules/`: `<station>_fact_store.json` (fact="qué retorno": p_bull/ev/divergence_regime/zigzag_kinematic) + `<station>_timing_fact_store.json` (timing="cuándo respecto al giro": slots zz25, pct_en_rango, first_passage MAE/MFE/RR, fire_rate_pct). Los consumen `<station>_lookup.py` (fact), `timing_context.py` (timing) y el compositor. Los generadores (`v3_fact_table_engine.py`) son build-time, NO runtime. |
| **Guidance** | `operational_guidance`/`pivot_overrides` con `STK_*` dentro del fact store — VIOLA Rule 21 (verificar, es señal de que se coló directiva vieja en el store de hechos). | Estación emite HECHOS (`p_bull`, `ev`, `n`) → compositor decide `MKT_*` → gates deciden `STK_*`. |

**Regla de hierro:** si una columna dice NUEVO, esa es la que auditas. Si una función duplicada del módulo existe (`evaluate_market_sigmets`), SOLO la documentas como duplicación — **NO la fusiones, NO la borres, NO la "arregles" para que coincida con la otra**, sin aprobación explícita del humano. Reporta la duplicación, no la resuelvas.

---

## CONTEXTO ARQUITECTÓNICO (definido — consultar `arquitectura-3-niveles-auditoria-polaridad-2026-09-17.md`)

Arquitectura de **3 niveles + Capa 0 de datos** (definida 17-Sep, sustituye al "giro 06-Sep"):

```
Capa 0 (datos) = fact_store + timing_store COEXISTEN (NO se fusionan, son complementarios):
  - <station>_fact_store.json   → "qué retorno espero si hoy estoy en este estado" (p_bull, ev_net, divergence_regime, zigzag_kinematic)
  - <station>_timing_fact_store.json → "cuándo/dónde estoy respecto al giro" (slots zz25, pct_en_rango, first_passage MAE/MFE/RR, fire_rate_pct)
Capa 1 (identidad) = station_profiles.py (polarity, cat, profession, d2_singularities) + structural_guidance.py + stations/*_intelligence.md
Capa 2 (confluencia) = convergence_compositor.py → guidance MKT_* (family_sequence_detector + taf_service)
Capa 3 (acción) = Entry Gates → directivas STK_*
```

- **Rutas runtime** (Capa 0, en `/root/botero-trade/backend/modules/entry_decision/domain/rules/`): `<station>_fact_store.json` (11) + `<station>_timing_fact_store.json` (11). **NO los trates como duplicados ni confundas uno con el otro** — fact responde "qué", timing responde "cuándo". Los consumen: `<station>_lookup.py` (fact), `timing_context.py` (timing), y el compositor (F2 timing context).
- **Los timing stores resuelven los ADDENDA 3/4/5** del `fact_store_v3_architecture.md` (Wins/Losses→MAE/MFE, Distribución P5/P95→p90, Base rate→fire_rate_pct). No son invento.
- **Generadores** (build-time, NO runtime): `backend/scripts/generators/generate_<station>_fact_table.py` + `backend/scripts/_lib/v3_fact_table_engine.py`
- **Interprete**: `cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python`
- Regla dura de directivas: **estaciones emiten HECHOS** (`p_bull`, `ev`, `n`), NUNCA directivas. El compositor emite `MKT_*`; los Entry Gates convierten a `STK_*`. `operational_guidance`/`pivot_overrides` con `STK_*` **dentro de un fact store violan Rule 21** — verifícalo.
- Tiers de confianza (4, runtime): EVENT(N<10)→ canal crisis_alerts separado (NO al composite EV) · TRANSITIONAL(10≤N<30)→ peso 0.5 · CONFIRMED(N≥30, D1∈{0,1,4,5})→ peso completo · BASELINE(N≥30, D1∈{2,3})→ peso completo.

---

## HALLAZGO CONFIRMADO PARA PARTIR (solo punto de partida — busca más)

**Bug tipo `argument of type 'NoneType' is not iterable` en DXY, reproducible:**

- Mecánica del crash (verificada, 25-Sep): `extract_structural_guidance()` en `structural_guidance.py` itera `zz25→zz50→zz75`. En un state activo (hoy DXY `3__3__2`), `zz25`/`zz50` tienen `structural_momentum` poblado (llenan `p_hl`/`p_hh`) pero **el `break` de línea 160 no dispara** (queda un valor None), así que entra a `zz75`, donde `sm.get("up_legs"/"down_legs", {})` devuelve **`null` explícito**, y `"p_continuation" in up/down` → `TypeError`. El crash está en **L142 (`up`) o L150 (`down`)**, según cuál sea null — no solo L150.
- **Causa raíz (correcta en el prompt):** `.get(key, default={})` protege contra clave AUSENTE pero NO contra valor `null` explícito dentro del dict. Fix sugerido: `sm.get("up_legs") or {}` y `sm.get("down_legs") or {}`.
- **⚠️ Distinción CRÍTICA de categorías de null (no confundirlas):**
  - `structural_momentum = null` (entero) → **SEGURO** — el guard `structural_guidance.py` L136 (`if not sm: continue`) lo atrapa. Es **la física normal** (~60-70% de estados, bins sin piernas). NO reportar como bug.
  - `structural_momentum` ES un dict pero sus hijos `up_legs` / `down_legs` = `null` explícito → **BUG real (crash)**. Ocurre cuando una escala (típicamente zz75) tiene piernas insuficientes para un lado.
- **Conteo crashable VERDADERO (verificado en fact stores, 25-Sep):** 
  `structural_momentum` es dict + `up_legs` O `down_legs` = null explícito:

  | Estación | Crashables/Total | % |
  |---|---:|---:|
  | BSI | **16/112** | 14.3% |
  | DXY | 9/128 | 7.0% |
  | VIX | 9/113 | 8.0% |
  | Rotation | 5/124 | 4.0% |
  | FG | 3/82 | 3.7% |
  | SV5_Turbulence | 3/110 | 2.7% |
  | VVIX | 2/98 | 2.0% |
  | Credit | 2/104 | 1.9% |
  | Yield_Curve | 2/131 | 1.5% |
  | PCR | 1/95 | 1.1% |
  | SKEW | **0/118** | 0.0% |
  | **TOTAL** | **52/1,215** | **4.3%** |

  → El bug es **ACTIVO hoy** (DXY state `3__3__2`) y **LATENTE** en 10 de 11 estaciones. **BSI es la más vulnerable** aunque hoy no crashea.
- **Desajuste de contrato**: `structural_guidance.py` línea 183 lee `is_fallback_l1`, pero `dxy_fact_store.json` tiene **0 ocurrencias** de ese campo → el generador (`generate_dxy_fact_table.py` + `v3_fact_table_engine.py`) no produce un campo que el consumidor espera.

**Reproducción:**
```
cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
from backend.modules.entry_decision.domain.services.dxy_metar_service import get_dxy_market_metar
print(get_dxy_market_metar())  # TypeError
"
```
Contraste: `get_credit_market_metar()`, `get_sv5_turbulence_market_metar()`, `get_vix_market_metar()` NO crashean hoy (pero su fact store contiene bins null latentes).

---

## TAREA 1 — Diagnóstico de la CLASE de bug (no solo la instancia)

1. Lee `structural_guidance.py` COMPLETO y los **11** `<station>_lookup.py`. Identifica TODOS los puntos con el patrón `.get(key, default)` cuyo default falla ante JSON `null` explícito (no ante clave ausente). No te detengas en la línea 150.
2. Corre un **barrido empírico de los 11 servicios** contra su fact store: para cada `state_key` activo actual, ¿el servicio lanza o no? Documenta divergence systemática.
3. **Grep de campos referenciados vs campos producidos**: para cada estación, lista los campos que el código consume (structural_guidance, family_sequence_detector, compositor, taf_service, timing_context) y cruza contra las keys reales. `is_fallback_l1` es un ejemplo — busca más contract breaks. **Audita AMBOS stores por estación** (`<station>_fact_store.json` Y `<station>_timing_fact_store.json`): verifica que el código que lee el timing store (`timing_context.py`, compositor F2) no asuma campos ausentes, y que no haya campos referenciados que ningún store produce.
4. **Dos categorías DISTINTAS de null** en campos estructurados que el código espera como dict. Clasifícalas por separado en tu tabla por fact store:
   - (a) `structural_momentum = null` (entero) → **SEGURO por diseño** — guard `structural_guidance.py` L136 (`if not sm: continue`). Es la física normal del espacio 3D (~60-70% de estados, bins sin piernas zigzag). NO lo reportes como bug.
   - (b) `structural_momentum` ES dict pero `up_legs` O `down_legs` = null explícito → **BUG latente**. Verificado (25-Sep): **52 estados en 10/11 estaciones** — BSI 16/112, DXY 9/128, VIX 9/113, Rotation 5, FG 3, SV5 3, VVIX 2, Credit 2, Yield 2, PCR 1, SKEW 0. Solo DXY crashea HOY por su estado activo; BSI es la más vulnerable.
   - El patrón exacto que crashea: `extract_structural_guidance` itera zz25→zz50→zz75; si zz25/zz50 llenan `p_hl`/`p_hh` pero el `break` L160 no dispara, cae a zz75 donde `legs=null` → `"p_continuation" in None` → TypeError. Verifica si hay OTROS campos (`terciles`, `prev_leg_domino`) con el mismo patrón de null-defectuoso.

## TAREA 2 — Consistencia entre canales (METAR vs TAF vs SIGMET vs NOTAM)

Ejecuta las 4 salidas para el día actual por el **camino de producción REAL** (el mismo que usa el daemon `metar_compositor_provider.py` — una sola pasada del compositor, y SIGMET desde los snapshots ya computados, NO re-fetch):
```
cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
from backend.modules.entry_decision.domain.services.convergence_compositor import ConvergenceCompositor
from backend.modules.entry_decision.domain.services.taf_service import compute_composite_taf_from_summaries
from backend.modules.entry_decision.domain.services.market_sigmet_hazard_service import evaluate_sigmets_from_metar_dicts
from backend.modules.entry_decision.domain.services.notam_incident_service import evaluate_operational_notams
r = ConvergenceCompositor().compute()     # METAR
print('activas/blind:', r.active_stations, r.blind_stations)
print('guidance:', r.unified_guidance, '| cascade_50:', r.cascade_conviction_50)
taf = compute_composite_taf_from_summaries(r.station_summaries)   # TAF
print('TAF regime:', taf.get('composite_divergence_regime'))
sigmets = evaluate_sigmets_from_metar_dicts(r.metar_snapshots, r.family_sequence, r.as_of_date)   # SIGMET principal
print('SIGMET count:', len(sigmets), [s.hazard_type for s in sigmets])
print('NOTAM count:', len(evaluate_operational_notams()))   # SIN as_of_date
"
```
⚠️ **Usa `r.metar_snapshots` + `r.family_sequence`** (el camino canónico). NO uses `evaluate_market_sigmets()` para la Tarea 2 — esa es la standalone de fallback, duplica y puede dar errores por versión/caché vieja.
Responde:
- **¿`unified_guidance` puede ser `MKT_HOLD_STABLE` mientras hay SIGMET CRITICAL/EMERGENCY activo?** Verifica si el compositor consume el resultado del motor SIGMET. Si no, es un desacoplamiento.
- **¿El canal estadístico (`cascade_conviction`) y el canal señal (voto D1) discrepan sin advertencia?** Documenta cualquier conflicto direccional no reconciliado.
- Estando en `cascade_conviction_50 = −0.318` (bajista) vs TAF `CONVERGENT_MOMENTUM_EXPANSION` (alcista), ¿el sistema emite alguna advertencia de desacuerdo entre canales?

## TAREA 3 — Integridad de datos (una sola fuente de verdad)

1. Confirma que cada indicador lee **UNA** sola fuente en runtime (fact store JSON) — busca duplicación con campos que el runtime recalcula por su cuenta.
2. Identifica **código muerto o legado** que aún se ejecuta en el path de producción (p. ej. `_build_taf_entry` referenciado en docs `taf_ftt_evpd_audit_report.md` pero ¿existe en `convergence_compositor.py`?).
3. Verifica si `operational_guidance` con directivas `STK_*`/`MKT_*` **dentro de los fact stores** viola la regla "la estación emite HECHOS, nunca directivas".

---

## LÍMITES DEL SCOPE
- ✅ **Aislar** el diagnóstico en el dominio `entry_decision/domain/` — no tocar frontend, APIs ni TIDE/QualitySwing.
- ✅ **Proteger** todos los `*_lookup.py` y `structural_guidance.py` — solo lectura durante esta auditoría.
- ✅ **Respetar** los fact stores generados tal como están — diagnóstico sobre el artefacto, no regenerar durante auditoría.
- ✅ **Preservar** `v3_fact_table_engine.py` como fuente de build-time.
- ✅ **Ejecutar** comandos reales para cada hallazgo (verificar ≠ inferir).
- ✅ **Auditar** los 11 servicios, no solo DXY.
- ✅ **Consultar** el reporte previo `references/metar-taf-sigmet-notam-produccion-auditoria-2026-09-25.md` (skill botero-trade) para no re-litigar lo ya audítado.
- ✅ **Conservar** la separación viejo/nuevo (tabla anti-cortocircuito) en cada conclusión.
- ✅ **Documentar** la duplicación de las dos funciones SIGMET (`evaluate_market_sigmets` vs `evaluate_sigmets_from_metar_dicts`) — NO fusionarlas, NO borrarlas, NO "unificarlas". Reporta el riesgo, no lo resuelvas.
- ✅ **Auditar** el TAF en `taf_service.py` — el compositor NO contiene `_build_taf_entry` (los docs que lo referencian en líneas 214-232 de `convergence_compositor.py` son stale; verifica y reporta, NO los busques en el archivo nuevo).

---

## CRITERIO DE ACEPTACIÓN (el reporte está completo cuando:)
- [ ] Numeraste los hallazgos y cada uno trae: `archivo:línea`, comando de reproducción + output real, por qué es bug, severidad (alta/media/baja), y si es **latente** o **activo hoy**.
- [ ] Separaste en el entregable `DIAGNÓSTICO` (bloque 1) vs `FIXES PROPUESTOS` (bloque 2, sin aplicarlos).
- [ ] Distinguiste explícitamente lo **verificado por ejecución** de lo **inferido por lectura**.
- [ ] Entregaste la tabla de `null` por campo por fact store (Tarea 1.4).
- [ ] Respondiste las 3 preguntas de la Tarea 2 (guía unívoca + desacoplamiento + desacuerdo de canales).
- [ ] Reportaste la **longitud total de caracteres del reporte** al inicio y al final.

---

## AUTOTEST (obligatorio — ejecutar antes de responder)
1. Ejecutar: `get_dxy_market_metar()` → Esperado: `TypeError: argument of type 'NoneType' is not iterable`
2. Ejecutar: `get_vix_market_metar()` → Esperado: `OK` (NO crashea hoy)
3. Ejecutar: cargar `dxy_fact_store.json` y contar estados donde `structural_momentum` ES dict pero `up_legs` O `down_legs` = null explícito (en cualquier escala zz25/zz50/zz75) → Esperado: **9** de 128. (Los otros 87 tienen `structural_momentum=null` entero → SEGURO, guard L136.)
4. Ejecutar: cargar `vix_fact_store.json` y contar los mismos → Esperado: **9** de 113. (64 con `sm=null` entero → SEGURO.)
5. Verificar: ¿existe `is_fallback_l1` en `dxy_fact_store.json`? → Esperado: **NO (0 ocurrencias)**
6. Verificar el camino de producción: `r = ConvergenceCompositor().compute()` → registra `r.unified_guidance`, `r.active_stations`, `r.blind_stations` reales. NUNCA uses `evaluate_market_sigmets()` para esto — usa `evaluate_sigmets_from_metar_dicts(r.metar_snapshots, r.family_sequence, r.as_of_date)`.
7. **Distinguir viejo vs nuevo (anti-cortocircuito):** confirma que `_build_taf_entry` NO existe en `convergence_compositor.py` y que el TAF real vive en `taf_service.py`. Si un doc los referencia en el compositor (líneas 214-232), es un doc stale — repórtalo, NO lo busques en el archivo nuevo.

Si alguna respuesta NO coincide con lo esperado, DETERNSE y corrige la lectura antes de continuar (el resultado puede ser un dato nuevo — repórtalo, no lo ignores).

---

## ENTREGABLE
Reporte en formato markdown, numerado, con los bloques `DIAGNÓSTICO` y `FIXES PROPUESTOS` separados. NO apliques ningún cambio de código. Termina con una recomendación priorizada (cuál bug atacar primero y por qué).