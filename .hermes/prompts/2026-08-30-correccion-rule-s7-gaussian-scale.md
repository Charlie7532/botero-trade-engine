# CORRECCIÓN DETALLADA — Rule S7 en gaussian_scale_policy.md

**Archivo:** `.agents/references/metar/gaussian_scale_policy.md`
**Problema:** La **Rule S7** (líneas 171-178) usa **labels textuales** para describir los extremos de D2 y D3, mientras que el nuevo §3.4 (correcto) usa **bins numéricos**. Esto crea dos definiciones contradictorias en el mismo archivo.

---

## 1. QUÉ HACER: Reemplazar las líneas 171-178

### Estado actual (INCORRECTO) — líneas 171-178:

```
### Rule S7: "Extreme" Means ±2σ (P2.28 / P97.72) — No Exceptions

When any code, documentation, or signal refers to a dimensional state as "extreme", it MUST correspond to the ±2σ bins:
- D1 extremes: Bin 0 (< −2σ) or Bin 5 (≥ +2σ) → 2.28% of population each
- D2 extremes: FAST_CRUSH_3D or FAST_SPIKE_3D → 2.28% each
- D3 extremes: VOL_EXTREME_SQUEEZE or VOL_PEAK_DECELERATION → 2.28% each

An indicator is NOT in an extreme state if it is in Bin 1 or Bin 4 (those are "elevated" = ±1σ to ±2σ).
```

### Estado deseado (CORRECTO):

```
### Rule S7: "Extreme" Means ±2σ (P2.28 / P97.72) — No Exceptions

When any code, documentation, or signal refers to a dimensional state as "extreme", it MUST correspond to the ±2σ bins:
- **D1 extremes (6 bins):** Bin 0 (< −2σ) or Bin 5 (≥ +2σ) → **2.28% of population each**
- **D2 extremes (5 bins):** Bin 0 (`FAST_CRUSH_3D`) or Bin 4 (`FAST_SPIKE_3D`) → **2.28% each**
- **D3 extremes (5 bins):** Bin 0 (`VOL_EXTREME_SQUEEZE`) or Bin 4 (`VOL_PEAK_DECELERATION`) → **2.28% each**

> **Regla:** Siempre comparar contra el bin numérico. El label semántico entre paréntesis es solo para referencia humana.

An indicator is NOT in an extreme state if it is in Bin 1 or Bin 4 (those are "elevated" = ±1σ to ±2σ).

For a generic function:
```python
def is_extreme(d1_bin: int, d2_bin: int, d3_bin: int) -> bool:
    d1_extreme = d1_bin in {0, 5}        # D1: 6 bins
    d2_extreme = d2_bin in {0, 4}        # D2: 5 bins (same ±2σ percentiles)
    d3_extreme = d3_bin in {0, 4}        # D3: 5 bins (same ±2σ percentiles)
    return d1_extreme or d2_extreme or d3_extreme
```
```

---

## 2. POR QUÉ ES NECESARIO

### 2.1 Riesgo actual
La Rule S7 actual obliga al agente a hacer:
```python
# ❌ INCORRECTO — el agente compara contra labels textuales
if d2_label == "FAST_SPIKE_3D":   # frágil: si renombran el label, se rompe
```

### 2.2 La corrección cambia a:
```python
# ✅ CORRECTO — el agente compara contra bin numérico
if d2_bin == 4:   # robusto: el bin numérico nunca cambia
```

### 2.3 Inconsistencia actual en el mismo archivo
| Sección | Formato de extremos | ¿Correcto? |
|:--------|:--------------------|:-----------|
| **§3.4** (línea 84-85) | `Bin 0 (FAST_CRUSH_3D)` | ✅ Bin numérico + label (correcto) |
| **Rule S7** (línea 175-176) | `FAST_CRUSH_3D or FAST_SPIKE_3D` | ❌ Solo label (atajo de Gemini) |

Esto crea confianza en el lector: dos secciones en el mismo archivo que dicen lo mismo pero con formatos distintos. La Rule S7 debe alinearse con §3.4.

---

## 3. VERIFICACIÓN POST-CORRECCIÓN

Después de aplicar el cambio, verificar que no queden referencias a labels de D2/D3 como identificadores únicos:

```bash
cd /root/botero-trade
# No debe haber "FAST_CRUSH_3D" como identificador sin su bin al lado
grep -n "FAST_CRUSH_3D" .agents/references/metar/gaussian_scale_policy.md
# Debe mostrar ej: Bin 0 (FAST_CRUSH_3D)
# NO debe mostrar extremos solo como: FAST_CRUSH_3D or FAST_SPIKE_3D
```

---

## 4. NOTA FINAL

Esta es la **última inconsistencia conocida** de la homologación canónica. Con esta corrección, los 5 archivos de referencia quedan consistentes: todas las comparaciones usan bins numéricos, los labels son solo para presentación humana.