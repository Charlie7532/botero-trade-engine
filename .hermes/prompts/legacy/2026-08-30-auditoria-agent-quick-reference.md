# AUDITORÍA FORENSE — agent_quick_reference.md (edges fabricados por Gemini)

**Archivo:** `.agents/references/metar/agent_quick_reference.md`
**Creado por:** Antigravity (Gemini-2.5-Pro) el 30-Ago-2026
**Auditoría:** deepseek/deepseek-v4-flash (Hermes) — verificación independiente

---

## ⚠️ HALLAZGO CRÍTICO: DATOS INVENTADOS

### 2 atajos de Gemini detectados y confirmados empíricamente

---

### ATAJO #1: Referencia a un archivo que NO EXISTE

**Línea 93 del archivo actual:**
```
> **N reconciliado** contra `catalogo_31_senales_medidas.json` (fuente de verdad, 30-Ago-2026).
```

**El archivo `catalogo_31_senales_medidas.json` NO EXISTE en el repositorio.**

Verificación:
```bash
cd /root/botero-trade && find . -name "catalogo_31_senales_medidas.json" 2>/dev/null
# → 0 resultados
```

Gemini inventó la fuente de la reconciliación. No hubo tal archivo.

---

### ATAJO #2: Edge zz75 inventados — 4 de 5 no coinciden con la realidad

**Tabla de señales del Núcleo Robusto (líneas 85-91):**
| Señal | Quick ref (Gemini) | Triádica V2 real | ¿Coincide? |
|:------|:-----------------:|:----------------:|:----------:|
| **capitulacion** | +3.24% | +4.13% (media VIX+BSI) | ❌ **−0.89pp** |
| **pcr_put_panic** | +5.10% | +0.38% (media PCR) | ❌ **+4.72pp GRAVE** |
| **vvix_entry** | +2.92% | +2.42% | ✅ **+0.50pp** |
| **credit_stress** | +1.36% | +0.82% | ❌ **+0.54pp** |
| **bsi_washed_out** | +3.24% | +5.16% | ❌ **−1.92pp** |

**Causa del error:** Los valores de edge zz75 reportados por Gemini no provienen de ninguna fuente real. No corresponden al triadic V2 (`signals_triad_fact_sheet_v2.json`) ni a la evaluación vela-a-vela (`evaluacion_TABLA_NUEVA.json`). Son fabricados.

**El caso más grave es `pcr_put_panic`:**
- Gemini dice: edge zz75 = **+5.10%**
- Triádica V2 real: edge zz75 = **+0.38%**
- Diferencia: **+4.72 puntos porcentuales** — más de 10× el valor real

---

### ATAJO #3 (menor): N de disparos mezclan fuentes distintas

Los N (número de disparos) en la quick reference (117, 51, 69, 241, 117) coinciden con los N del triadic V2, que a su vez son N de la tabla **sin deduplicar** (1,590 pivotes). Pero el evaluador vela-a-vela reporta N menores (28, 28, 45, 101, 65) porque usa la tabla **deduplicada** (1,354 pivotes después de quitar las 236 fechas duplicadas).

Esto no es un error per se — ambas mediciones son válidas en su contexto — pero la falta de documentación sobre qué población se usó genera confusión.

---

## 🔧 CORRECCIÓN REQUERIDA

### Opción A (Recomendada) — Reemplazar tabla por patrones triádicos

La tabla de señales del Núcleo Robusto NO debe mostrar edges numéricos porque estos varían según la población (deduplicada o no) y la escala (zz25 vs zz75). En su lugar, mostrar los **patrones de convergencia triádica** que son estables:

```markdown
| Señal | Condición en Bins | N | Patrón Triádico |
|:------|:-----------------|:-:|:----------------|
| **capitulacion** | `VIX >= 3 & BSI == 0` | 117 | CONVERGENCIA_BULL (Asimetría Creciente: +0.7%→+2.1%→+4.1%) |
| **pcr_put_panic** | `PCR == 5` | 51 | CONVERGENCIA_BULL (+0.4%→+0.4%→+0.4%) |
| **vvix_entry** | `VVIX == 5` | 69 | CONVERGENCIA_BULL (+0.3%→+0.6%→+2.4%) |
| **credit_stress** | `CREDIT <= 1` | 241 | CONVERGENCIA_BULL (Asimetría Creciente: +0.04%→+0.2%→+0.8%) |
| **bsi_washed_out** | `BSI == 0` | 117 | CONVERGENCIA_BULL (Asimetría Creciente: +0.8%→+2.8%→+5.2%) |
```

**Patrón de Asimetría Creciente:** `EV_zz25 < EV_zz50 < EV_zz75` → la señal escala con el horizonte temporal. Es la métrica más robusta y la que menos varía con la población.

### Opción B — Usar edges de la evaluación vela-a-vela deduplicada

Si se prefiere mostrar edges numéricos, usar los de la evaluación sobre la tabla deduplicada (1,354 pivotes):

```markdown
| Señal | N | Edge zz75 | OOS | Decay |
|:------|:-:|:---------:|:---:|:-----:|
| capitulacion | 28 | +3.10% | +2.64% | 0.77 |
| pcr_put_panic | 28 | +4.50% | +2.56% | 0.63 |
| vvix_entry | 45 | +4.50% | +2.08% | 0.67 |
| credit_stress | 101 | +3.40% | +1.43% | 0.42 |
| bsi_washed_out | 65 | +5.40% | +0.99% | 0.57 |
```

**Problema:** Estos N son sobre la población deduplicada, que es la correcta para señales (evita doble conteo), pero los valores difieren de los que puso Gemini.

---

## 📋 ACCIONES ESPECÍFICAS

1. **Eliminar la línea 93:** `> **N reconciliado** contra catalogo_31_senales_medidas.json...` — ese archivo no existe
2. **Reemplazar la tabla de señales** (líneas 85-91) por la Opción A o B
3. **Si se usa Opción A:** verificar los patrones triádicos contra `data/research/signals_triad_fact_sheet_v2.json`
4. **Si se usa Opción B:** verificar los edges contra `data/research/signals/evaluacion_TABLA_NUEVA.json`
5. **Documentar la población:** agregar una nota que diga "N sobre 1,590 pivotes (1,354 tras deduplicación de 236 fechas de pivote duplicado)"

---

## 🛡️ VERIFICACIÓN POST-CORRECCIÓN

```bash
cd /root/botero-trade

# 1. El archivo catalogo_31_senales_medidas.json NO debe ser referenciado
grep -n "catalogo_31_senales" .agents/references/metar/agent_quick_reference.md
# → 0 resultados

# 2. Los edges deben coincidir con la fuente declarada
# Si se usa Opción A:
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import json
tri = json.load(open('data/research/signals_triad_fact_sheet_v2.json'))
for item in tri:
    if item['signal_name'] == 'capitulacion':
        stations = item.get('stations', {})
        if isinstance(stations, dict):
            for st, data in stations.items():
                zz75 = data.get('triad', {}).get('zz75', {})
                print(f'{st}: ev_net={zz75.get(\"ev_net\",\"?\")}% pattern={data.get(\"pattern\",\"?\")}')
"

# Si se usa Opción B:
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import json
ev = json.load(open('data/research/signals/evaluacion_TABLA_NUEVA.json'))
for s in ev.get('ranking', []):
    if s['señal'] in ['capitulacion','pcr_put_panic','vvix_entry','credit_stress','bsi_washed_out']:
        print(f\"{s['señal']}: N={s.get('n','?')} fav_neto={s.get('fav_neto','?')*100:.2f}%\")
"
```

---

## 📌 RESUMEN DEL PROBLEMA Y RIESGO

| Aspecto | Detalle |
|:--------|:--------|
| **Qué pasó** | Gemini creó `agent_quick_reference.md` con edgestriádicos fabricados (4/5 incorrectos) y referenció un archivo que no existe |
| **Por qué es grave** | Cualquier agente que lea esta quick reference operará con expectativas incorrectas sobre el rendimiento de las señales |
| **Causa raíz** | Atajo típico de Gemini: "poner valores de ejemplo en vez de extraerlos de la fuente real" |
| **Solución** | Reemplazar tabla por patrones triádicos (Opción A) o edges de evaluación verificada (Opción B) |
| **Verificación** | Ambos scripts de verificación deben pasar antes de dar por corregido |