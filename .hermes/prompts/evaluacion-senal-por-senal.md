# PROMPT — Evaluación de Resultados: Señal por Señal, Efectividad y Mejora

**Para:** Worker (qwen-2.5-coder-32b) → Auditor (qwen3.8-max)
**De:** Juan Andrés (Arquitecto) vía Gemini → Hermes
**Fecha:** 20-Ago-2026
**Prioridad:** P1
**Estado:** NUEVO

---

## 0. OBJETIVO

Quiero ver **señal por señal** qué detecta el sistema, con qué efectividad, y si los cambios que hicimos (addenda, retiros, LIFT, correcciones) **mejoraron o empeoraron** la capacidad de detección. Quiero enfocarme exclusivamente en los **resultados de negocio**: ¿esta señal detecta pisos? ¿detecta techos? ¿con qué precisión? ¿cuánto mejoró con los cambios?

---

## 1. QUÉ TIENES QUE HACER

Ejecutar el arnés sobre **todas las señales activas** y producir un reporte de evaluación con 5 secciones.

### 1.1 Ficha técnica por señal (una tabla por señal)

Para CADA una de las 19 señales únicas (descontando duplicados), producir una mini-ficha con:

```
SEÑAL: credit_easing_k1
├─ Tipo: ENTRY (piso)
├─ ¿Qué detecta? Crédito en easing en un piso zigzag — el mercado de bonos confirma el suelo
├─ Edge: +5.19% (forward medio)
├─ Win Rate: 93.8% (de 112 activaciones, 105 fueron piernas alcistas)
├─ Peor caso (P5): −3.90% — en el 5% peor de los casos, pierde esto
├─ Mejor caso (P95): +11.19%
├─ LIFT vs baseline: 0.341x — P(cae|señal)=6.2% vs baseline=18.3% (ENTRY: mientras MÁS BAJO el LIFT, mejor — la señal REDUCE probabilidad de caída)
├─ Cascade: 53.6% escala a corrección (zz50), 32.1% a depresión (zz75)
├─ Duración media: 11.3 barras
├─ Estabilidad: 2000s WR=89%, 2010s WR=100%, 2020s WR=94%
├─ Régimen: FULL_CONVERGENT_BULL (las 3 escalas confirman)
├─ Structural momentum: 57.1% de pisos son HL (estructura alcista saludable)
├─ Grado: ⭐⭐⭐⭐⭐ (GRADE A — producción inmediata)
└─ Diagnóstico: La señal más fuerte del sistema. Casi nunca falla (93.8%). 
   Su valor defensivo es medio (LIFT=0.341x) pero su valor ofensivo es extraordinario.
```

**Para señales EXIT, el LIFT se interpreta al revés: mientras MÁS ALTO (>1.0), mejor — la señal AUMENTA probabilidad de caída vs baseline.**

### 1.2 Tabla comparativa consolidada

Una tabla ÚNICA con las 19 señales, columnas:
- Señal | Tipo | N | Edge | WR | LIFT | CI95 | Cascade 50/75 | Grado | Diagnóstico 1-línea

### 1.3 Análisis de cobertura: ¿qué detecta el sistema?

```
PISOS (ENTRY):
  - ¿Cuántos de los 795 pivotes MIN tienen al menos 1 señal ENTRY activa?
  - ¿Cuál es la cobertura? (ej: 384/795 = 48.3%)
  - ¿Cuál es el forward medio cuando hay ≥2 señales ENTRY simultáneas?
  - ¿Cuál es el forward medio cuando NO hay ninguna señal ENTRY?

TECHOS (EXIT):
  - ¿Cuántos de los 795 pivotes MAX tienen al menos 1 señal EXIT activa?
  - ¿Cuál es la cobertura?
  - ¿Cuál es el forward medio cuando hay ≥2 señales EXIT simultáneas?
  - ¿Cuál es el forward medio cuando NO hay ninguna señal EXIT?
```

### 1.4 Señales especiales (diamantes)

Listar TODAS las señales con N < 35 (umbral de diamante) y evaluar cada una con el protocolo §3.3:

| Señal | N | Edge | WR | LIFT | ¿Diamante? | Diagnóstico |
|-------|:--:|------|:----:|:----:|:----------:|-------------|
| panico_total | 34 | +1.49% | 58.8% | 1.526x | 💎 Sí | Combinación VIX+SKEW extremo — solo 34 veces en 33 años, PF>8 |
| ... | | | | | | |

### 1.5 ¿Qué mejoró y qué empeoró con los cambios?

Comparar los resultados ACTUALES (post-enmienda, post-addenda) contra los JSONs históricos PREVIOS (si existen en `data/research/signals/medicion_*.json`):

| Señal | Métrica | Antes | Ahora | Δ | ¿Mejora? |
|-------|---------|-------|-------|-----|----------|
| bsi_recovery | N | 324 | 481 | +157 | ✅ +48% más datos (label fantasma corregido) |
| bsi_recovery | Edge | −1.63% | −1.66% | −0.03pp | ≈ Igual (más robusto) |
| *todas* | LIFT | No existía | Medido | NUEVO | ✅ Nueva métrica |
| *todas* | structural_momentum | No existía | Medido | NUEVO | ✅ Nueva métrica |
| *todas* | divergence_regime | No existía | Medido | NUEVO | ✅ Nueva métrica |

Si algún edge **cambió significativamente** (>0.5pp o WR >5pp), marcarlo en 🔴 y diagnosticar si es mejora real o posible regresión.

---

## 2. MÉTODO DE EJECUCIÓN

```bash
cd /root/botero-trade

# 1. Ejecutar el arnés para TODAS las señales activas (22 señales, incluyendo duplicados)
PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import sys; sys.path.insert(0, 'research/01_señales_entry_exit')
from medir_senal import SEÑALES, _CERTEZA, cargar_datos, medir
import json
activas = sorted([n for n, c in _CERTEZA.items() if 'RETIRADA' not in str(c.get('validacion',''))])
df, spy = cargar_datos()
for sig in activas:
    rep = medir(sig, df, 'next_leg', spy=spy)
    with open(f'/tmp/eval_{sig}.json', 'w') as f:
        json.dump(rep, f, indent=2, ensure_ascii=False, default=str)
    print(f'{sig}: N={rep[\"activa\"][\"dist\"][\"n\"]} mean={rep[\"activa\"][\"dist\"][\"mean\"]:+.4f} WR={rep[\"activa\"][\"wl\"][\"win_rate\"]:.1%}')
print('OK')
"

# 2. Comparar contra JSONs históricos (si existen)
for f in data/research/signals/medicion_*.json; do
    sig=$(basename $f .json | sed 's/medicion_//')
    if [ -f "/tmp/eval_${sig}.json" ]; then
        echo "Comparando $sig..."
        PYTHONPATH=/root/botero-trade backend/.venv/bin/python -c "
import json
old = json.load(open('$f'))
new = json.load(open('/tmp/eval_${sig}.json'))
for k in ['activa','baseline','delta_media','triada']:
    if json.dumps(old.get(k), sort_keys=True, default=str) != json.dumps(new.get(k), sort_keys=True, default=str):
        print(f'  CAMBIO en {k}')
" 
    fi
done
```

---

## 3. ENTREGABLE

Un solo archivo markdown: `.hermes/reportes/2026-08-20_evaluacion-senal-por-senal.md`

Estructura:

```markdown
# EVALUACIÓN SEÑAL POR SEÑAL — Efectividad del Sistema de Detección

## 1. Fichas técnicas (19 señales)
[Una ficha por señal como en §1.1, ordenadas por Grado (A→B→Revisar)]

## 2. Tabla consolidada
[Tabla única con las 19 señales, columnas §1.2]

## 3. Cobertura del sistema
[§1.3 — ¿cuántos pisos/techos cubre? ¿qué pasa con ≥2 señales simultáneas?]

## 4. Diamantes
[§1.4 — todas las señales con N<35, evaluadas con protocolo §3.3]

## 5. Mejora/Empeoramiento
[§1.5 — delta antes/después, diagnóstico de qué cambió]

## 6. Diagnóstico final
- ¿El sistema es "inteligente"? (¿detecta más de lo que el azar explicaría?)
- ¿Las señales ENTRY capturan pisos reales o son ruido?
- ¿Las señales EXIT anticipan caídas o llegan tarde?
- ¿Cuántas señales son GRADO A (producción inmediata)?
- ¿Qué falta para considerar el sistema "completo"?
```

---

## 4. ARCHIVOS DE REFERENCIA

| # | Archivo | Para qué |
|---|---------|----------|
| 1 | `research/01_señales_entry_exit/medir_senal.py` | Ejecutar el arnés |
| 2 | `data/research/signals/medicion_*.json` | JSONs históricos para comparar antes/después |
| 3 | `.hermes/paraauditar/fact_store_v3_architecture.md` | §3.3 Diamantes, §13 Confidence Tiers |
| 4 | `.hermes/reportes/2026-08-20_evaluacion-resultados-algoritmo.md` | Evaluación resumida que hice hoy — punto de partida |

---

## 5. LÍMITES DEL SCOPE

- ✅ **Ejecutar** el arnés y reportar resultados — sin modificar código
- ✅ **Comparar** contra JSONs históricos donde existan
- ✅ **Evaluar** cada señal con métricas de negocio (Edge, WR, LIFT, Cascade, estabilidad)
- ✅ **Clasificar** por grado (A/B/Revisar) según efectividad demostrada
- ✅ **Identificar** diamantes y aplicar protocolo §3.3

---

## 6. CRITERIOS DE ACEPTACIÓN

- [ ] 19 fichas técnicas completas (una por señal única)
- [ ] Tabla consolidada con todas las métricas clave
- [ ] Análisis de cobertura de pisos y techos
- [ ] Todas las señales con N<35 evaluadas como diamantes
- [ ] Comparación antes/después para señales que tienen JSON histórico
- [ ] Diagnóstico final respondiendo: ¿es inteligente el sistema? ¿está listo?

---
**Firma:** deepseek/deepseek-v4-pro (Hermes) · 20-Ago-2026