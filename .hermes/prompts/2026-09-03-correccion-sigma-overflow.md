# PROMPT: Corrección de `sigma_overflow.py` — Escala Empírica por Cuantiles (Vault Completo) + Alcance Acotado

**Fecha:** 03-Sep-2026
**Ejecutor:** Gemini
**Pre-auditado por:** Claude (meta-auditoría) — ver sección "decisiones de diseño".
**Propósito:** Corregir el cálculo de overflow en el sistema METAR, que usa μ/σ paramétricos fijos y produce (a) falsos positivos masivos en estaciones fat-tailed (VIX 13×), y (b) ceguera total en estaciones acotadas (FG/BSI/DXY/Yield). **Alcance ACOTADO**: solo se toca el overflow/z-scores/SIGMET. Los bins, state keys y fact stores del sistema son CORRECTOS y NO se tocan.

---

## DECISIONES DE DISEÑO (consensuadas, no abiertas a debate)

1. **Calibración sobre el Vault COMPLETO.** Los edges empíricos (cuantiles) se computan sobre la población completa de cada indicador en el Neon Vault, NO sobre una sub-ventana. Esto resuelve el "desajuste de ventana" que Claude identificó (DXY/Yield pre-1993 vs Lake). La población de calibración es el Vault histórico íntegro de cada ticker.

2. **D2 y D3 se computan INDEPENDIENTEMENTE POR ESTACIÓN.** Cada estación tiene sus propios edges de velocidad (D2 = diff(3)) y de estabilidad (D3 = std(2)/std(10)). NO hay edges compartidos entre estaciones. Los 7 cuantiles empíricos se calculan por estación × dimensión (D1, D2, D3) sobre la serie propia de esa estación.

3. **Método: Piecewise Quantile Scaling** (verificado monótono y continuo por Claude). Los 7 anclas gaussianas `[P0.135, P2.275, P15.866, P50, P84.134, P97.725, P99.865]` → z-scores `[-3, -2, -1, 0, +1, +2, +3]`, con interpolación lineal entre anclas y extrapolación lineal en las colas (>P99.865 y <P0.135).

4. **Definición de overflow:** un valor es overflow (`|z| > 3.0`) **solo si supera el cuantil empírico P99.865 o cae bajo P0.135** (0.135% nominal cada cola, ~1 en 740 días hábiles). Esto garantiza que el overflow sea un evento excepcional real.

5. **Interfaz 100% compatible:** `validate_overflow(station, dim, value)`, `classify_overflow_tier(z_score)`, `get_overflow_tier(station, dim, value)` mantienen sus firmas intactas. Ningún adaptador de runtime cambia de firma.

6. **Alcance acotado (CRÍTICO):** NO tocar los bins del lake (`*_d1_bin`), los state keys (`*_sk`), los edges de los 150 estados, ni los fact stores (que usan expanding rank — correctos). **Solo:** `sigma_overflow.py`, la columna `*_z_*` y overflows del lake, y los consumidores SIGMET.

---

## CAMBIOS

### Componente 1 — `backend/modules/entry_decision/domain/rules/sigma_overflow.py`
- Reemplazar `STATION_MU_SIGMA` por `STATION_EMPIRICAL_EDGES`: diccionario con los 7 cuantiles empíricos por estación × dimensión (D1, D2, D3), computados del Vault completo.
- Implementar `compute_empirical_z(val, edges) -> float` (Piecewise Quantile Scaling).
- `validate_overflow()` usa la nueva función z.
- Mantener `classify_overflow_tier()` (T1-T5) intacto.

### Componente 2 — `backend/scripts/generators/build_continuous_metar_lake.py`
- Actualizar la generación de `*_z_*` y `*_ovf*` para usar la función empírica sobre el Vault completo.
- **NO** alterar la generación de bins/state keys (expanding rank se mantiene).

### Componente 3 — `tests/test_sigma_overflow.py`
- Update fixtures y expectativas numéricas.
- Verificar: VIX median → z≈0, VIX 70 → z≥3 (UPPER), FG 95 → z>3 (UPPER), FG 1.5 → z<-3 (LOWER), Yield -1.8 → z<-3 (LOWER).

---

## VERIFICACIÓN (obligatoria antes de dar por bueno)

1. **Tests unitarios:** `pytest tests/test_sigma_overflow.py -v`
2. **Regresión:** `pytest tests/ -q`
3. **Eventos históricos** (validar que el nuevo z-score LOS DETECTA):
   - Lehman Brothers Oct-2008 (VIX spke, PCR capitulación)
   - Crash COVID Mar-2020 (VIX > 70, pánico)
   - Inversión de curva 2022-2023 (YIELD z<-3 — antes ciego)
   - FG en 3/95 (miedo/codicia extremos — antes ciego)
   - Spike VIX Ago-2024
4. **Tabla resumen** con overflows por estación (paramétrico viejo vs empírico nuevo) para confirmar 13× → ~1 en VIX.

---

## REGLAS

- **Dato mata relato:** cada número se verifica contra el Vault.
- **No tocar lo que funciona:** bins, state keys, fact stores (expanding rank) permanecen intactos.
- **Calibración sobre Vault completo** — no sub-ventana.
- **D2/D3 por estación independiente** — no edges compartidos.
- **No reinventar:** usar el Piecewise Quantile Scaling ya verificado por Claude.