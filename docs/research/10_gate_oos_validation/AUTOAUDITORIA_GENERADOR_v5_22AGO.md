# AUTOAUDITORÍA DEL GENERADOR — `builder_quants_obs.py` v5 (22-Ago-2026)

**Firma:** qwen/qwen3.8-max (Hermes)
**Principio:** auditar que el generador nuevo sea CORRECTO EN SÍ MISMO (según la lógica de
producción), antes de auditar su fidelidad al one-off del 17-Ago.

---

## 1. RESULTADO FINAL DEL GENERADOR

| Métrica | Valor |
|---------|-------|
| Columnas ≥99.9% match con el original | **101/141** |
| CAT-A (artefacto del one-off, tabla usa producción) | **12 columnas** |
| CAT-B (deriva de versión, documentada) | **37 columnas** |
| CAT-C (sin clasificar) | **0** |
| Señales que disparan en la tabla nueva | **28/28** (cero inertes) |
| `cascade_reversal` (antes inerte en silencio) | **1,075 disparos — funciona** |
| Pivotes | **1,590** (columna vertebral 100% reproducible) |

## 2. FÓRMULAS AUDITADAS (cada una verificada con datos)

| Columna | Fórmula correcta | Evidencia | Match |
|---------|------------------|-----------|:---:|
| `pivot_date/type` | `ZigzagLegRepository.get_confirmed_legs("SPY","zz25")` | 1,590 pares idénticos | 100% |
| `duration_bars` | Duración CALENDARIO de la pierna que ARRANCA en el pivote, piso 1 día | reconstrucción exacta | 100% |
| `daily_return_pct` | Retorno de esa pierna (%) ÷ duración | reconstrucción exacta | 100% |
| `cascade_50/75` | Proximidad ±3 días a pivote zz50/zz75 (NO pertenencia) | fórmula hallada en early_warning.py | 99.9% |
| `next_bear`/`next_leg_direction` | Idénticos a `leg_bear` (el original los nombró mal) | match con `(pivot_type=="MAX")` | 100% |
| `{st}_val/_vel/_vol` | Vault, fecha EXACTA; fuera de rango val=NaN, vel=0, vol=1 | verificado con PCR | 100% |
| `{st}_sk` | LookupAdapter de producción (edges estáticos) | 10/11 estaciones al 100% | 100%* |
| `z_dom` | `(abs_prev_leg_return − 0.0532)/0.035` (cal-file) | reconstrucción | 100% |
| `d1_bear_5` | **PRESIÓN BEARISH = Σ(max(0,−voto))/n** (NO media) | reconstrucción | 100%** |
| `z_bear` | `(d1_bear_5 − 0.3299)/0.2856` — los defaults del compositor de producción | ingeniería inversa | 99.94% |
| `cascade_conviction` | `0.66·z_bear + 0.34·z_dom` | reconstrucción | 100%** |
| `cascade_conviction_50` | = c50 del compositor (`convergence_compositor.py:503`) — columna AÑADIDA | definición oficial | nueva |

\* skew al 13.3% — CAT-A documentado (sección 3).
\** con los votos del pickle; con votos de producción diverge solo en las 428 filas OVERSOLD (sección 3).

## 3. BUGS ENCONTRADOS EN EL GENERADOR PROPIO (autoauditoría honesta)

1. **`d1_bear_5` usaba la MEDIA de votos** — incorrecto. El pickle y el compositor de
   producción usan la FRACCIÓN de presión bearish. Corregido: fórmula de presión verificada
   al 100% contra el pickle.
2. **`cascade_conviction_50` no existía** — la señal `cascade_reversal` leía esa columna y
   el guard la hacía inerte en silencio. Corregido: columna añadida con la definición oficial
   del compositor; la señal ahora dispara 1,075 veces.

## 4. DECISIONES CAT-A (artefactos del one-off que NO se replican)

1. **Skew D1 con bins solapados:** el one-off clasificó SKEW con un método irreproducible
   (bins NORMAL_TAIL_RISK 109-120 y ELEVATED_TAIL_RISK 113-120 se cruzan — imposible con
   umbral estático). Hipótesis trailing probada y RECHAZADA (máx 41.9% en ventanas
   252/504/756/1000). **Decisión:** usar edges estáticos de producción y documentar.
2. **Escala de votos −0.5 de OVERSOLD_BREADTH:** el pickle votaba OVERSOLD_BREADTH = −0.5
   (medio voto bearish); la función de producción `d1_directional_vote` vota 0. Esto explica
   EXACTAMENTE las 428 filas divergentes de `d1_bear_5/z_bear/cascade_conviction`
   (428/1590 = 26.9% → match 73.1%). No es deriva misteriosa: es un único artefacto de
   escala. **Decisión:** usar la escala de producción. La fórmula resultante es idéntica a la
   del compositor actual (`n_bearish/n_votes`, convergence_compositor.py:484).

## 5. DECISIONES CAT-B (deriva de versión, documentada)

- Bloque plano `zz25` de los fact stores (`_zz25_pbull/pbear`, `_ev_net`): regenerado con
  "edges trailing 3 años" según `recalibrar_cascade_trailing.py`. El bloque `zigzag_kinematic`
  NO deriva (100% en 10/11 estaciones; rotation al 97% también regenerado).
- 1 fila de borde en sv5_turbulence/yield_curve/rotation con mismo `_val` pero distinto D1:
  caso de borde de edges derivados.

## 6. CONSISTENCIA CON PRODUCCIÓN (el test más importante)

- Los μ/σ usados por `z_bear` (0.3299/0.2856) **son exactamente los defaults del compositor
  de producción** (convergence_compositor.py:488-489) — evidencia de que el generador
  original consumía producción.
- `d1_bear_5` con votos de producción: media=0.3340 std=0.2869 — coherente con esos defaults.
- La fórmula de `cascade_conviction_50` coincide con el compositor (c50 = 0.66·z_bear + 0.34·z_dom).
- **Conclusión:** el generador nuevo es consistente con la lógica de producción actual.

## 7. PENDIENTE DE VERIFICACIÓN EXTERNA

- Si la tabla nueva cambia las mediciones del catálogo v7 de señales (evaluador vela-a-vela).
- Si alguna otra señal depende de columnas CAT-A/B de forma material.
- Si el esquema de 142 columnas preserva la compatibilidad de todos los consumidores.
