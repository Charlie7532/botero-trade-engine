# AUDITORÍA — INGESTA DE INDICADORES SINTÉTICOS: Fechado Incorrecto de Velas en el Vault
# + Fallback Silencioso del NOTAM en /weather

> **Fecha:** 2026-09-21 · **Estado:** PARA CORRECCIÓN (2 hallazgos)
> **Principio rector (citado del usuario):** *"Las velas tienen día y fecha y estas DEBEN QUEDAR en el día y fecha que les corresponde."*
> **Evidencia:** verificación empírica directa contra el Neon Vault (no simulación).

---

## HALLAZGO 1 (CRÍTICO) — Indicadores sintéticos con vela fechada en día SIN MERCADO

### El hecho verificado (query directo al Vault, día de la semana confirmado)

| Ticker | Velas en Vault (15-21 Sep) | Vela viernes-18? | Vela sábado-19? |
|:-------|:---------------------------|:-----------------|:----------------|
| **S5TW / S5TH / S5FI** (breadth) | 16, 17, **19** | ❌ NO | ✅ SÍ (mal) |
| **SV5TW / SV5TH** | 16, 17, **19** | ❌ NO | ✅ SÍ (mal) |
| **BSI** (sincronizado de S5TW) | 16, 17, **19** | ❌ NO | ✅ SÍ (mal) |
| **FG** | 16, **19** | ❌ NO (ni 17) | ✅ SÍ (mal) |
| **SPY / VIX** (cotizan) | 16, 17, **18** | ✅ SÍ | ❌ NO |

**Días de la semana (confirmados con Python):** `16=miércoles`, `17=jueves`, `18=VIERNES`, `19=SÁBADO`.

### El problema
- **Todos los indicadores SINTÉTICOS tienen una vela fechada en SÁBADO 19** — un día que el mercado NO cotiza.
- **Les FALTA la vela del VIERNES 18** (el último día hábil real).
- **Los que cotizan (SPY/VIX) SÍ tienen el 18 correcto.**

→ **La vela no quedó en su día/fecha correspondiente** (viola el principio rector). El sábado-19 se insertó usando la fecha del RELOJ del sistema, no la fecha de la data que el indicador representa.

### La causa raíz (cadena verificada en código)
1. **`bsi_provider.py` L91:** `time_val = pd.to_datetime(sigmet.as_of_date)` → BSI se fecha con lo que el METAR de BSI devuelva.
2. **`bsi_provider.py` L69 `_sync_s5tw_to_bsi`:** BSI sincroniza velas de S5TW → hereda la fecha mala.
3. **`get_bsi_market_metar` (bsi_metar_service.py) L123-128:** lee `MAX(time::date)` de S5TW → el "más reciente" es el sábado-19.
4. **`data_vault_daemon.py` L72 `_already_vaulted_today`:** usa `date.today().isoformat()` → define "hoy" con el RELOJ, no con la data.

**El origen:** el daemon de breadth/indicadores corrió el sábado y **fechó la vela con la fecha del reloj (sábado-19)** en vez de con la fecha de la data subyacente (viernes-18). Como el viernes-18 nunca se generó, queda el sábado-19 como "el más reciente".

### Impacto
- **NOTAM del viernes-18** reporta **stale** para FG/SV5/BSI/CREDIT/breadth (11 incidents) — correcto en señal, pero **la raíz es la vela mal fechada**, no la falta de data.
- El sábado-19 (sin mercado) contamina el `MAX(time::date)` y el análisis temporal.
- **Corrección:** el daemon debe fechar la vela con **la fecha de la data del indicador** (el último cierre de mercado = viernes-18), NO con `date.today()`. Y debe **backfill el 18 faltante**.

---

## HALLAZGO 2 (MEDIO) — Fallback silencioso del NOTAM en `/weather`

### El hecho verificado
**`backend/api/routers/metar.py` L310-314** (endpoint unificado `/weather`):

```python
# ── NOTAM (independent — reads Vault freshness directly) ────────
try:
    notams = evaluate_operational_notams(as_of_date=as_of_date)
    notam_data = [n.to_dict() for n in notams]
except Exception:
    notam_data = []          # ← SILENCIOSO: traga el error y devuelve "sin NOTAM"
```

### El problema
Si `evaluate_operational_notams` lanza una excepción en runtime (fallo de conexión, error de query), el `/weather` devuelve `"notam": []` **como si no hubiera incidentes** — un **falso "todo OK"**.

### La contradicción con la política
Contradice la **Regla/Strict Data Policy "cero fallbacks silenciosos"** (misma filosofía del `StrictDataPolicyError` ya implementada en los metar services). Un fallo del NOTAM no debe convertirse en "no hay NOTAM", sino en **alerta de que la telemetría no pudo evaluarse**.

### Corrección propuesta
Reemplazar `except Exception: notam_data = []` por:
- Devolver un objeto de ERROR/incidente con `severity="CRITICAL"`, `incident_type="NOTAM_EVALUATION_FAILURE"`, `details={error}` — para que el fallo del pipeline sea VISIBLE, no silencioso.

---

## Resumen de acciones (Rule 22 — esperar aprobación)

| # | Hallazgo | Severidad | Acción |
|:-:|:---------|:---------:|:-------|
| 1 | Vela sintética fechada en día sin mercado (sábado-19), falta viernes-18 | 🔴 CRÍTICA | Corregir fechado del daemon → usar fecha de la DATA; backfill 18 |
| 2 | Fallback silencioso del NOTAM en `/weather` (`except: []`) | 🟡 MEDIA | Convertir el error en incidente visible, no en "sin NOTAM" |

## Verificación acumulada
- [ ] 💾 Fix 1: `bsi_provider.py` L91 + `_already_vaulted_today` — fechar con la data, no el reloj; backfill del 18
- [ ] 💾 Fix 2: `metar.py` L310-314 — NOTAM fallo ⇒ incidente visible, no `[]`
- [ ] Re-correr: NOTAM del viernes-18 debe mostrar el 18 al día (no stale sintético)
- [ ] Confirmar que S5TW/SV5/BSI/FG obtienen vela correcta (viernes-18, no sábado-19)