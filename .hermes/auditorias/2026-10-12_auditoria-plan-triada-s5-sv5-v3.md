# Auditoría del Plan Tríada S5/SV5 v3.0 — con doble verificación

> **Fecha**: 2026-10-12
> **Auditor**: Hermes (independiente del agente que redactó el plan)
> **Objeto**: `implementation_plan.md` (08-Oct) + `plan_trabajo_depurado_triada_s5_sv5_v3.md` (12-Oct), artefactos del hilo `187feb11` / `14b6501a`
> **Método**: toda cifra medida contra `market.*` (Neon) y código vivo; cada hallazgo con **dos verificaciones independientes**
> **Estado**: ningún artefacto del proyecto fue modificado; esta auditoría es aditiva

---

## PARTE A — Segunda verificación de los hallazgos iniciales

| # | Hallazgo | 1ª verificación | 2ª verificación (método distinto) | Veredicto |
|---|---|---|---|---|
| 1 | Claim «XLK +14,2% vs XLU +5,1%» no reproduce | Media pierna MIN→MAX zz25/zz50/zz75 | Mediana + solo-últimos-5-años + búsqueda por celda más cercana | **CONFIRMADO — el delta real es 0,16–0,39 pp** |
| 2 | Brecha de frescura sectorial | XLK 07-31, XLU 07-24 (2 tickers) | Las **13** entidades + `prev_leg_return` NULL | **CONFIRMADO y ampliado** (11/11 sectores stale; 100% NULL) |
| 3 | Sync automático solo SPY | lectura del hook | grep del call-site en todo `backend/` | **CONFIRMADO** (`data_vault_daemon.py:1299` hardcodea `"SPY"`) |
| 4 | «Solo 6 entrenadores» subcontado | grep `engine.zigzag_points` | grep `zigzag_points` (sin prefijo) + por pyc compilados | **CONFIRMADO — son 10** |
| 5 | Se recuperaron artefactos, no la conversación | 678 steps vs 5 `.md` | inventario de ambos `brain/` | **CONFIRMADO** |
| 6 | Workaround, no reparación | 5 `.db` de 0 bytes | re-escaneo de `conversations/*.db` | **CONFIRMADO — siguen 5 en 0 bytes** |

### Detalle 1 — El claim científico del §1

Batería de 4 definiciones, todas medidas:

| Definición | zz25 XLK / XLU | zz50 XLK / XLU | zz75 XLK / XLU |
|---|---|---|---|
| Media MIN→MAX | 5,77 / 5,38 | 11,47 / 11,27 | 17,93 / 17,77 |
| Mediana MIN→MAX | 4,86 / 4,47 | 9,75 / 10,19 | 12,98 / **14,28** |
| Solo ≥2021-01-01 | 5,64 / 4,95 | 12,08 / 11,31 | 20,45 / 19,68 |

Ninguna celda combinación (ticker×escala) da XLK≈14,2 **y** XLU≈5,1. El valor **14,28 aparece en el dato — como la MEDIANA de XLU en zz75**, no de XLK. Los dos números existen en la tabla pero **asignados al sector y la escala equivocados**.

**Dispersión real intersectorial** (media MIN→MAX, 13 entidades):

| Escala | mín | máx | **Rango** | σ |
|---|---|---|---|---|
| zz25 | 5,25 (XLP) | 6,05 (QQQ) | **0,80 pp** | 0,22 |
| zz50 | 10,95 (XLV) | 12,49 (XLRE) | **1,54 pp** | 0,41 |
| zz75 | 16,90 (XLF) | 19,47 (SPY) | **2,57 pp** | 0,66 |

El plan declara Δ=9,1 pp. El máximo real es **2,57 pp** ⇒ sobreestima la dispersión entre **3,5× y 11×**.

### Detalle 2 — Frescura y dominó (las 13 entidades, zz25)

| Ticker | Piernas | Última pierna | `prev_leg_return` NULL |
|---|---:|---|---:|
| SPY | 1.584 | **2026-09-16** | 0,1% |
| XLK | 2.358 | 2026-07-31 | **100%** |
| XLE | 2.813 | 2026-07-31 | **100%** |
| XLC | 512 | 2026-07-30 | **100%** |
| XLI | 1.670 | 2026-07-30 | **100%** |
| QQQ | 2.416 | 2026-07-29 | 0,0% |
| XLV | 1.289 | 2026-07-28 | **100%** |
| XLRE | 563 | 2026-07-28 | **100%** |
| XLP | 1.051 | 2026-07-28 | **100%** |
| XLB | 2.111 | 2026-07-28 | **100%** |
| XLU | 1.561 | 2026-07-24 | **100%** |
| XLY | 1.936 | 2026-07-23 | **100%** |
| XLF | 2.178 | 2026-07-23 | **100%** |

Los 11 sectores caen en una ventana de **9 días** (23–31 julio) ⇒ corte de sync, no ausencia de giros. SPY y QQQ sí tienen `prev_leg_return` poblado; los 11 sectores, **0/25.502**.

### Detalle 4 — Entrenadores que leen `engine.zigzag_points`

10 archivos en `backend/scripts/trainers/`:
`train_dual_probability_tables`, `train_multiscale_kinematic_ev_tree`, **`train_rc_conviction`**, **`train_rc_state_table`**, **`train_sentinel_models`**, **`train_sentinel_v2`**, `train_tide_ev_real_table`, `train_tide_table`, `train_wave_table`, **`unified_pretrainer_v2`**.
(negrita = ausentes de la lista de 6). La lista de 6 además incluye `generate_wave_multiscale_tree.py`, que está en `generators/`, no en `trainers/`.

---

## PARTE B — Auditoría del plan

### Claims del plan verificados EXACTOS (4/4)

| Claim del plan | Verificado |
|---|---|
| `s5_triad_table.json` en **versión 2.0** | ✅ version = 2.0 |
| **83.154 observaciones globales** | ✅ suma de `global.n` sobre las 238 celdas R4 = **83.154 exacto** |
| `triad_lookup.py` pasa **6/6 tests** | ✅ `pytest tests/test_triad_lookup.py` → **6 passed** |
| `zz75`: ~70 a 382 piernas por entidad | ✅ real 67–382 |

### Claims del plan INEXACTOS

| Claim del plan | Realidad medida |
|---|---|
| «~1.000 a 2.800 piernas zz25 por entidad» | **512 – 2.813** (el mínimo es la mitad) |
| «~250 a 816 piernas zz50 por entidad» | **132 – 816** |
| «**250 celdas**» y criterio de Fase 1: «comprobar que el número de celdas se mantiene en 250» | R4 = **238**; total en el JSON = **391** (R4 238 + R3 123 + R2 25 + R1 5) |
| «Dispone de datos **completos** para las 13 entidades… en las tres escalas canónicas» | **FALSO para 11/13**: congeladas a julio y sin `prev_leg_return` |

### Hallazgos

**🔴 P1 — La decisión central del §1 se apoya en una cifra que no reproduce.**
El §1 concluye «Conveniencia: **ALTA**» → «**SÍ ES CONVENIENTE**» el desglose por sector, con el argumento de que el Tier «diluye esta ventaja de sizing». Medido, la ventaja es de **0,80–2,57 pp**, no 9,1 pp. Con umbral L1 de N≥20, **178 de 238** celdas exponen sector ⇒ se tomaría una decisión de exposición sectorial en el 75% de las celdas sobre una dispersión <2,6 pp. **El plan debe re-medir antes de comprometer la arquitectura.**

**🔴 P2 — Prerrequisito ausente: la Fase 1 se ejecutaría sobre datos defectuosos.**
El plan depurado §1.A afirma que `zigzag_legs` «dispone de datos completos para las 13 entidades». Verificado: los 11 sectores están congelados al 23–31 de julio (SPY al 16-sep) y su `prev_leg_return` es **25.502/25.502 = 100% NULL**; el hook automático hardcodea `"SPY"` (`data_vault_daemon.py:1299`). La Fase 1 ordena «extraer piernas confirmadas directamente de `market.zigzag_legs`» **sin ningún paso previo de rebuild ni de frescura**. Resultado si se ejecuta tal cual: el Bloque 4 se entrena sobre piernas de julio, sin dominó, y se certifica como v3.0.

**🔴 P3 — El criterio de aceptación de la Fase 1 es falso y no es verificable.**
«Comprobar que el número de celdas se mantiene en 250» → el real es **238 R4** (391 totales). Un ejecutor que valide «250» fallará, o forzará celdas vacías para cuadrar el número.

**🟡 P4 — El plan presenta como novedad una jerarquía que ya existe en 2 de sus 3 niveles.**
Cada celda de v2.0 ya contiene `global`, `Defensive`, `Mixed`, `Cyclical`, `High-Beta`, `SPY`. **L2 (Tier) y L3 (Global) ya existen**; lo genuinamente nuevo es **L1 (sectores)** y los 4 bloques (temporal, timing, cinemática, `_documentation`). El «esquema de 4 bloques» es real; la «jerarquía tripartita» es añadir un nivel a una jerarquía de 2 preexistente.

**🟡 P5 — La Fase 1 regenera `bin_edges` sin resolver la fuente única de edges.**
Existe desfase entre los edges **hardcodeados** en `quality_entry_gate.py` (L46-56: `S5_EDGES`, `SV5_EDGES`) y el `bin_edges` de la tabla que lee `triad_lookup.py`. La Fase 1 reentrena y reescribe `bin_edges`; la Fase 3 solo verifica `TOP_DISTRIBUTION_STATES`. **El desfase se ensanchará**, no se cerrará. Debe fijarse una fuente única antes de generar.

**🟡 P6 — Calidad de dato no contemplada: 22.715 piernas con precio 0.**
Concentradas en las series sintéticas de amplitud (`S5_XLE_TW`, `S5_XLU_TW`, `S5_XLU_FI`, `S5_XLE_FI`). Producen `division by zero` al calcular retornos (reproducido en esta auditoría). El filtro a 13 entidades del plan las evita *para el Bloque 4*, pero el plan **no declara ese filtro como salvaguarda explícita** ni aborda la serie corrupta.

### Riesgos que el plan declara y NO cubre como dice

| Riesgo declarado | Salvaguarda declarada | Estado real |
|---|---|---|
| «Lookahead Bias en Piernas» | «piernas alineadas por `confirmed_at_timestamp`» | El plan no dice **quién** filtra; `prev_leg_return` (el dominó) está 100% NULL en sectores ⇒ el filtro no tiene con qué operar |
| «Inconsistencia de muestras» | «Uso exclusivo de `market.zigzag_legs` con filtro estricto sobre las 13 entidades» | El filtro existe en el texto pero **no hay chequeo de frescura** ni de integridad de `prev_leg_*` |
| «Explosión del Tamaño de Archivo» | «estructura compacta… carga lazy» | Sin umbral numérico; hoy el JSON ya tiene 391 celdas × 6 niveles |

---

## Recomendación de cierre (antes de aprobar la Fase 1)

1. **Re-medir la dispersión intersectorial** con la definición que el plan usará y decidir L1 con ese número (el medido: 0,80–2,57 pp).
2. **Rebuild de piernas de los 11 sectores** + poblar `prev_leg_return`; extender el hook de sync más allá de `"SPY"`.
3. **Corregir el criterio de aceptación**: R4 = 238 celdas (no 250) y total 391.
4. **Fijar la fuente única de `bin_edges`** antes de regenerar (gate vs tabla).
5. **Declarar el filtro anti-precio-cero** como salvaguarda explícita.

---

## Anexo — Evidencia reproducible

```
# Dispersión intersectorial
SELECT ticker, scale, AVG((end_price/start_price-1)*100)
FROM market.zigzag_legs
WHERE ticker IN ('XLK','XLV','XLF','XLY','XLP','XLI','XLE','XLU','XLRE','XLB','XLC','SPY','QQQ')
  AND start_type='MIN' GROUP BY ticker, scale;

# Frescura + dominó
SELECT ticker, MAX(end_timestamp)::date, SUM(CASE WHEN prev_leg_return IS NULL THEN 1 ELSE 0 END)
FROM market.zigzag_legs WHERE scale='zz25' GROUP BY ticker;

# Celdas del fact store
python -c "import json; d=json.load(open('backend/modules/entry_decision/domain/rules/s5_triad_table.json'));
print(sum(v['global']['n'] for k,v in d['cells'].items() if len(k.split('|'))==4))  # 83154"

# Sync automático
grep -n "sync_ticker_zigzag_legs" backend/daemons/data_vault_daemon.py   # L1299: (store, "SPY")
```
