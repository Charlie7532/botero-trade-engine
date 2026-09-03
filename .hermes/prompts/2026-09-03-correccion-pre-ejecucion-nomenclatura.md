# CORRECCIÓN PRE-EJECUCIÓN: Nomenclatura de Métricas por Celda (Opción C / OHLC)

**Destino:** Plan de implementación `implementation_plan.md` (Gemini, 09:59) — sección §2.3 `consultar_inteligencia.py` y §3 Verificación.
**Motivo:** residuos de la Opción B (cortes operativos) que contradicen la decisión Opción C (métricas descriptivas). Aplicar ANTES de ejecutar para que la implementación no reintroduzca cortes de tiempo/velas por confusión terminológica.

---

## 1. El problema (por qué esta corrección es previa a ejecutar)

La decisión tomada (prompt C2/C3): **P90(bars) y P95(|MAE|) se reportan como DATO DESCRIPTIVO** de la física del trade, **no como corte** del motor. La Opción C elimina todo corte arbitrario de tiempo/velas (C9 80/40/27).

El plan usa la nomenclatura `time_stop_celda` y `mae_limite_celda`, que **sugiere límites operativos** (residuo de la Opción B). Si el implementador honra los nombres, reintroduciría un corte — exactamente lo que la Opción C eliminó.

**Regla canónica que se protege:** "el movimiento termina cuando cambia la naturaleza del movimiento (cambio de régimen del zz), no en un número de velas." Un P90 de bars es estadística descriptiva, no un límite de resolución.

---

## 2. Cambios de nomenclatura obligatorios

### 2.1 En `consultar_inteligencia.py` (sección §2.3 del plan)

**REEMPLAZAR** (después de calcular las métricas):

```python
# ANTES (Opción B — cortes, AMBIGUO):
time_stop_celda   = np.percentile(bars, 90)
mae_limite_celda  = np.percentile(np.abs(maes), 95)
```

**POR** (Opción C — descriptivo):

```python
# DESPUÉS (Opción C — dato descriptivo, sin rol de corte):
bars_p90    = np.percentile(bars, 90)          # duración observada P90 (descriptivo)
mae_p95     = np.percentile(np.abs(maes), 95)  # dolor observado P95 (break-of-structure de referencia)
```

**Regla de uso obligatoria en el código:**
- `bars_p90` y `mae_p95` **NUNCA** se usan para terminar un trade ni para excluir una observación del HR.
- Son **estadísticas reportadas** para que el risk manager calibre su propio criterio de salida, si lo desea.
- El primer-passage resuelve **exclusivamente** por toque de barrera OHLC intrabar (favorable o adversa), sin reloj.

### 2.2 En la ficha formateada (`_format_ficha_senal`)

**REEMPLAZAR** el texto:
```
Time-stop celda (P90): {bars_p90} barra(s)   ← sugiere corte, eliminar
MAE límite celda (P95): {mae_p95}            ← sugiere corte, eliminar
```

**POR** (etiqueta descriptiva):
```
Bars P90 (duración observada): {bars_p90} barras   [descriptivo — no limita]
MAE P95 (break-of-structure de referencia): {mae_p95}   [referencia risk-manager — no corta]
RR por celda: {rr_celda:.2f} ({'OPERABLE' if rr>=1 else 'NO OPERABLE: dolor supera premio'})
```

El `rr_celda` con `RR<1 → NO OPERABLE` **SÍ se conserva** (es la regla de operabilidad por dato, no un corte de tiempo).

### 2.3 En la suite de verificación (sección §3 del plan)

**REEMPLAZAR** la aserción #4 (que decía "time_stop = P90(bars) de la celda — sin cortes globales 80/40/27"):

```bash
# 4. Métricas por celda reportadas como DESCRIPTIVAS (no cortes)
print('✅ 4. bars_p90 y mae_p95 reportados como dato descriptivo — la resolución ')
print('      es SOLO por barrera OHLC intrabar, sin cortes de velas (Opción C).')
```

---

## 3. Verificación de que la corrección se aplicó

```bash
backend/.venv/bin/python << 'EOF'
import pandas as pd
# 1. El parquet regenerado NO debe contener columnas que sugieran time-stop operativo
aug = pd.read_parquet('data/research/bar_augment.parquet')
stop_cols = [c for c in aug.columns if 'time_stop' in c or 'timeout' in c or 'max_bar' in c]
print('Columnas time-stop en bar_augment:', stop_cols if stop_cols else 'NINGUNA — solución solo por barrera ✅')

# 2. La resolución es natural (bordes NaN, no cortes)
for s in ['zz25','zz50','zz75']:
    nan = aug[f'{s}_long_hit'].isna().sum()
    print(f'{s}_long: NaN(borde)={nan}, resolución={1-nan/len(aug):.4f}')

# 3. Sin cortes de velas: los 'bars' pueden superar 27 (ex zz75 C9) sin ser timeout
print(f"zz75_long bars máx observado: {aug['zz75_long_bars'].max():.0f} (C9 era 27) — sin techo ✅")
EOF
```

**Resultado esperado:**
- `timeout`/`time_stop` ausentes (o solo `resolved:False` de borde).
- `zz75_long_bars.max() > 27` (la resolución no se corta a 27 velas).
- `bars_p90` y `mae_p95` presentes solo como reporte en las fichas, no como cortes.

---

## 4. Trazabilidad

| Elemento | Antes (Opción B) | Después (Opción C) | Origen |
|:---------|:-----------------|:-------------------|:-------|
| P90(bars) | `time_stop_celda` (corte) | `bars_p90` (descriptivo) | Prompt C2 crit.3: "bars/mae_p90 reportados por celda como dato, no como corte" |
| P95(\|MAE\|) | `mae_limite_celda` (corte) | `mae_p95` (referencia) | Prompt C2 crit.3: "mae_p95 como referencia de break structural para risk manager" |
| No operable | — | `RR < 1 → NO OPERABLE` (conservar) | Prompt C2 crit.3: "rr_celda con regla explícita" |
| Resolución | time-stop C9 80/40/27 | barrera OHLC intrabar, sin reloj | Prompt C2 crit.1: "sin time-stop, resuelto:False excluido, resolution_rate" |

---

## 5. Lo que NO se cambia

- La **reversión** de `credit_equity_divergence` y `defensive_rotation_divergence` (§2.1 plan).
- La **elección de ancla** por naturaleza de señal (§2.2 plan).
- El **fallback** a `medicion_*.json` para posicionales (§2.3 plan).
- El **rescate de diamantes** §3.3 y `diamantes_cola.json` (§2.4 plan).
- `RR<1 → NO OPERABLE` (se mantiene, es regla de operabilidad por dato).

**Este doc solo purga la nomenclatura que podía reintroducir cortes.** Aplicarlo, regenerar `bar_augment` con OHLC intrabar desde el script versionado, y recién entonces ejecutar la suite de verificación.