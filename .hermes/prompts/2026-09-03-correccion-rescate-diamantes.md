# PROMPT: Corrección Integral del Motor — Rescate de Diamantes, BLANCOS, y Time-Stop por Celda

**Destino:** `consultar_inteligencia.py`, `construir_bar_snapshot.py`, `regenerar_fact_stores.py`
**Fecha:** 03-Sep-2026 (noche)
**Autor del hallazgo:** usuario — *"Opus destrozó las señales diamante, las clasificó como anecdotal, ignorando la rareza y sustento de caso de estudio, por alta probabilidad de retorno, de señal extrema, de exceso de lo que significa la señal."*

**Principio rector:** §3.3 — rareza = riqueza. N bajo NO degrada. La señal extrema con sustento de caso de estudio es el activo más valioso del sistema.

---

## PARTE 1 — AUDITORÍA: Los 4 daños confirmados (con verificación ejecutada 03-Sep noche)

### DAÑO 1 — 🔴 La DIAMANTE SUPREMO está rota en el motor: N=0, dirección "?"

`sv5t_silent_distribution` — rescatada el 28-Ago bajo §3.3 como diamante supremo (N=20, 100% WR en techos MAX, Fwd=-4.63%, PF=99.9, CI95=[83.2%, 100%]) — en el motor produce:

```
N episodios: 0 | Dirección: ? | Grade: ? | Diamante: False
```

**Causa raíz verificada (doble):**
1. **Bug BLANCOS:** el motor hace `blanco = _CERTEZA[señal].get("pivot_type", "MIN")` (L423). Para `sv5t`: `pivot_type=MAX` pero **`blanco=None` en `_CERTEZA`** → el motor evalúa la dirección equivocada o la descarta. El VAV tiene el dict `BLANCOS` propio (L112-130, 31/31 señales auditadas 20-Ago) — **el motor no lo usa.** 36 señales carecen de `blanco` en `_CERTEZA`.
2. **Fires=0 en bar_signals:** la señal es posicional (`pivot_type=MAX` en el cuerpo) y el mapeo ±2 barras del barrido la deja sin disparos en el lake. Su medición canónica existe (`medicion_sv5t_silent_distribution.json`: n=22 activos vs 772 baseline MAX, delta_media=+0.31pp, WR=27% vs baseline 21%) — **pero el motor no la lee.**

### DAÑO 2 — 🔴 Estados extremos con p_bull 1.00 marcados ANECDOTAL/LOW sin valor de caso

Verificado en `vix_fact_store.json` regenerado: estados con señal extrema y probabilidad de retorno alta, reducidos a etiqueta de "poca cosa":

| Estado | N | p_bull | ev_net | Etiqueta Opus | Lo que §3.3 exige |
|:-------|:-:|:------:|:------:|:--------------|:------------------|
| `1__1__0` | 1 | **1.00** | **+3.02%** | ANECDOTAL | Diamante con caso de estudio individual |
| `0__1__4` | 1 | **1.00** | **+2.61%** | ANECDOTAL | Ídem |
| `0__2__0` | 4 | **1.00** | **+2.55%** | ANECDOTAL | Ídem |
| `1__1__0` | 1 | 1.00 | +3.02% | ANECDOTAL | Ídem |
| `1__3__2` | 5 | 0.80 | +1.73% | LOW | Ídem |

**El error conceptual:** Opus usó `grade = tier_rareza = ANECDOTAL` como si "anecdotal" significara "sin valor". En §3.3, ANECDOTAL significa: *"solo existencia del evento"* — y justamente por eso **exige analizar cada evento individualmente** (fecha, contexto, resultado) con la tasa cruda. Un estado que ocurrió 1 vez con p_bull=1.00 y ev_net=+3.02% no es "poca cosa": es un **diamante de cola** que merece ficha de caso de estudio. La palabra "ANECDOTAL" en §3.3 es un nivel de INFERENCIA (no se puede inferir probabilidad), no un juicio de VALOR.

### DAÑO 3 — 🔴 Time-stop fijo 80/40/27 con timeout≠falla introduce sesgo de selección direccional

Corregido el timeout (ya no es falla — bien), pero el corte fijo sigue censurando **asimétricamente**. Verificado con 300 timeouts zz75 extendidos a 200 barras: **66.8% habrían sido hit, 25.2% loss, 8.1% nunca**. El HR sobre resueltos (0.445 zz75) está sesgado a la baja porque el corte prefiere sobrevivir a los trades que caen rápido y excluye los que tardan (los que con drift terminan bien).

**El criterio del usuario (correcto):** *"una entrada o salida no puede permitir más de 5 velas contrarias a la señal o una pierna zz25/zz50 contraria; evaluar más allá es utopía — lo que suceda ya no es propio de la señal"* + *"la pierna de bajada no puede superar la de subida"* (RR≥1) + *"si la entrada es larga, no puede permitirse un break of structure"* (MAE peor que el peor histórico de la celda = ya no es la señal).

**El marco VAV ya lo mide por celda** (nada que inventar):
- `bars_medio` (duración real de la señal en esa celda; el 81.3% de los episodios duran ≤5 velas — el "5" del usuario coincide con el P90 del mercado)
- `mae_medio` / `mae_p95` (el dolor NORMAL y el dolor LÍMITE de la celda)
- `rr = MFE/|MAE|` (RR<1 = la celda es desastrosa: el dolor supera al premio — `cascade_reversal` RR=0.53, `regime_change_exit` RR=0.50; RR alto = diamante operativo — `panico_total` RR=9.7, `vvix_entry` RR=3.2)
- `e_days` del fact store (duración esperada por estado: zz25 mediana 6.9 días)

### DAÑO 4 — 🟡 B2 con criterios degradados invalida su veredicto

El "0/18 sobreviven" de B2 fue calculado con: embargo por barras (unidad equivocada), escala única zz25 (la peor para estas configs), y GRADE_A/B (los grados que el propio Opus ya eliminó en C4). Además los time-stops fijos distorsionan el HR de entrada. **B2 debe re-ejecutarse** con: embarga por episodio/entradas, mejor escala por config, tiers §3.3, y time-stop por celda.

---

## PARTE 2 — CORRECCIONES (en orden)

### C1 — Usar `BLANCOS` del VAV, no `pivot_type` de `_CERTEZA`

```python
# En consultar_inteligencia.py:
from evaluador_vela_a_vela import BLANCOS   # 31/31 señales auditadas
# blanco = BLANCOS.get(señal)   # "MAX" | "MIN"
# direction = "short" if blanco == "MAX" else "long"
# PROHIBIDO: blanco = _CERTEZA[señal].get("pivot_type")  ← son cosas distintas
```

Esto arregla inmediatamente la dirección de todas las señales exit (`sv5t`, `cascade_reversal`, `credit_equity_divergence`, etc.).

### C2 — Ficha de caso de estudio §3.3 para N<21 (el rescate de diamantes)

Cuando `n_resueltos < 21` en un estado o señal, el output DEBE incluir el bloque:

```json
"caso_de_estudio_§3.3": {
  "protocolo": "Rareza = riqueza. N bajo define nivel de INFERENCIA, no valor.",
  "eventos": [
    {"fecha": "2020-03-16", "estado": "5__4__3", "resultado": "+2.6%",
     "contexto": {"regimen": "BAJA", "overflow_d1": "T1", "vix_nivel": 82.3}}
  ],
  "tasa_cruda": 1.00,
  "nivel_inferencia": "ANECDOTAL",
  "sustento": "p_bull=1.00 con ev_net=+3.02% en estado extremo — candidato a señal de cola",
  "instruccion": "NO descartar. Analizar cada evento. Si el mecanismo es explicable, escalar a DIAMANTE_COLA con validación cruzada por confluencia."
}
```

**Cambiar el lenguaje del tier:** `ANECDOTAL` pasa a describirse como *"nivel de inferencia: solo existencia — REQUIERE caso de estudio individual"*, nunca "sin valor". Cada estado/señal con N<21 y |ev_net| o p_bull extremo es automáticamente **candidato diamante de cola** y aparece en una lista `diamantes_cola.json` generada por el motor.

### C3 — First-passage puro por la triada (OPCIÓN C DEFINITIVA — resolución por cambio de régimen del zz)

**DECISIÓN TOMADA por el usuario (03-Sep): Opción C.** Eliminar el time-stop fijo 80/40/27. La justificación es la regla canónica ya implementada en el VAV + datos verificados en quants_obs:

> "Una señal le pega a un determinado zz. El movimiento termina cuando cambia de régimen (se confirma el siguiente pivote MIN↔MAX de esa escala). La naturaleza del movimiento es variable — no se mueven en plazos de tiempo ni en cantidad de velas fijas."

**Datos que la respaldan (verificados en quants_obs):**
- `duration_bars` (duración real de una pierna): P50=4, P75=8, P90=18, **máx=219 velas**. No hay plazo típico.
- `abs_prev_leg_return` (el zz que la pierna realmente recorrió): 100% ≥2.5%, 42.5% ≥5%, 15.4% ≥7.5%. **Muchas piernas no llegan a zz50/zz75** — `resuelto:False` en esas escalas es exclusión, no pérdida.

**Implementación (3 mediciones en paralelo, idéntico al VAV):**

```python
# POR CADA BARRA / POR CADA SEÑAL — replicar first_passage() del VAV (sin time-stop):
#   Las 3 escalas en paralelo (ESCALAS = zz25/zz50/zz75)
#   hit  → tocó primero +scale  (barrera favorable) → el movimiento cumplió su zz
#   loss → tocó primero -scale  (barrera adversa)
#   resuelto:False → no tocó ninguna barrera (la pierna quedó por debajo de ese zz)
#                    → se EXCLUYE del HR, NO es pérdida. Se reporta resolution_rate.
#   bars = event_i + 1  (duración REAL de la pierna, sin techo)
```

**Las 4 instrucciones adicionales (además de elegir C):**

1. **`resuelto:False` se excluye del HR en TODAS las métricas** del motor (fichas de estado, de señal, fact stores) — como el VAV hace en `first_passage()` (L161-162 `return {"resuelto": False}` → luego `if r and r["resuelto"]` L255). El motor actual aún cuenta timeouts de otra forma; alinear a exclusión pura.

2. **`resolution_rate` obligatorio por escala** en toda ficha: `resueltos/total`. Es el dato honesto de cobertura — un `resuelto:False` en zz75 no es señal mala, es una señal que nunca alcanzó ese zz.

3. **Reportar `bars` como el dato variable, no como techo:** en cada celda `escala|régimen`, `bars_medio` + `bars_p90` (duración real). El consumidor (risk manager) decide el kill operativo **si lo desea** — el motor no impone corte. Esto reconcilia tu "5 velas" (síntoma zz25) con la naturaleza variable de zz50/zz75.

4. **`rr_celda` con regla de operabilidad** (tu "la pierna de bajada no puede superar la de subida"): `rr = mfe_medio/|mae_medio|`. `rr < 1 → celda NO operable`. `cascade_reversal` (rr=0.53 en zz25|BAJA) y `regime_change_exit` (rr=0.50) salen del set operativo por dato, no por convención.

**REFERENCIA CANÓNICA (no reinventar):** la medición es literalmente `first_passage()` de `evaluador_vela_a_vela.py` L149-177. El motor debe **importar o copiar exactamente** ese comportamiento (sin `max_barras`, sin `timeout`). Verificación de aceptación: `|HR_motor − HR_VAV| ≤ 1pp` por celda en las 3 señales de prueba.

### C4 — Señales posicionales: leer su medición canónica, no dejarlas en N=0

Para las señales que filtran `pivot_type` en el cuerpo (`sv5t_silent_distribution`, `credit_easing_k1`, `credit_equity_divergence`, `defensive_rotation_divergence` y demás P1-excluidas del barrido):
- El motor NO puede medirlas sobre el lake (sin pivote, no hay señal).
- **Fuente correcta:** sus `medicion_*.json` (ya existen: `medicion_sv5t_silent_distribution.json` con n=22, baseline 772 MAX, delta_media=+0.31pp) y/o el VAV con `reevaluar=True`.
- La ficha del motor debe hacer **fallback transparente**: `"fuente": "medicion_pivotes_canonica"` y renderizar esas métricas en el mismo formato, en lugar de devolver N=0.

### C5 — Re-ejecutar B2 con criterios correctos

Repetición del veredicto de las 18 configs E7 usando: embargo por episodio (no por barra), mejor escala por config, tiers §3.3 (no GRADE_A/B), **first-passage puro por la triada (C3, Opción C — sin time-stop)**, y dirección correcta por blanco (C1). Reportar las dos lecturas: táctica (¿señal operable?) y descriptiva (¿firma de estado con sustento?).

### C6 — Verificación de aceptación

```bash
backend/.venv/bin/python << 'EOF'
import pandas as pd, subprocess, json

# 1. sv5t debe tener ficha completa (no N=0)
r = subprocess.run(['backend/.venv/bin/python3', 'research/01_señales_entry_exit/consultar_inteligencia.py',
                    'senal', 'sv5t_silent_distribution', '--scale', 'zz50'], capture_output=True, text=True)
assert 'N episodios: 0' not in r.stdout, 'Diamante supremo sigue rota'
assert 'short' in r.stdout or 'Dirección' in r.stdout
print('✅ 1. sv5t_silent_distribution (DIAMANTE SUPREMO) con ficha completa')

# 2. Estados extremos con bloque caso de estudio
fs = json.load(open('backend/modules/entry_decision/domain/rules/vix_fact_store.json'))
st = fs['states']['1__1__0']['zz25']
assert 'caso_de_estudio' in str(st) or st.get('n_raw',0) < 21
print('✅ 2. Diamantes de cola identificados con bloque §3.3')

# 3. RR por celda en la ficha de señal
r2 = subprocess.run(['backend/.venv/bin/python3', 'research/01_señales_entry_exit/consultar_inteligencia.py',
                     'senal', 'credit_stress', '--scale', 'zz25'], capture_output=True, text=True)
assert 'RR' in r2.stdout and 'celda' in r2.stdout.lower()
print('✅ 3. RR por celda con filtro operable (RR<1 = no operable)')

# 4. Time-stop por celda, no global
print('✅ 4. time_stop = P90(bars) de la celda — sin cortes globales 80/40/27')
EOF
```

---

## PARTE 3 — Trazabilidad: cada corrección ↔ su origen

| Corrección | Origen | Cita |
|:-----------|:-------|:-----|
| C1 BLANCOS | VAV L112-130 (auditado 20-Ago, 31/31) | El dict BLANCOS es la asignación auditada de blanco por señal |
| C2 caso de estudio §3.3 | fact_store_v3_architecture.md §3.3 + corrección del usuario | "N bajo define nivel de inferencia, no valor. Rareza = riqueza." |
| C3 time-stop por celda | Criterio del usuario 03-Sep + VAV (bars_medio, mae_p95, rr por celda) | "Máx 5 velas contrarias... pierna bajada no puede superar la de subida... no puede permitirse break of structure" |
| C4 señales posicionales | P1 del VAV + medicion_*.json canónicos | Las señales pivot-dependientes no se miden en el lake |
| C5 B2 v4 | Corrección metodológica 03-Sep | La unidad correcta es el episodio; los grados A/B ya están eliminados |
| RR<1 = no operable | `mfe_medio/|mae_medio|` del VAV, verificado: cascade 0.53, regime_change 0.50 vs panico_total 9.7, vvix_entry 3.2 | "El retorno es una entrada desastrosa" |

---

## PARTE 4 — Qué NO se toca

- `evaluador_vela_a_vela.py` / `evaluador_general.py`: canónicos, intactos.
- `_fire` suffix, filtro inception en 3 consultas, no-duplicación del lake: conservados.
- El concepto de `n_independent` para CI95 por barras: se conserva para el CI95, pero deja de ser criterio de calificación (vuelve §3.3 con `n_resueltos`).
- `defensive_rotation_divergence` y `credit_equity_divergence` rehabilitadas por el flujo ranking→_CERTEZA (PC5 de Opus): se mantienen, con verificación C6 pendiente.