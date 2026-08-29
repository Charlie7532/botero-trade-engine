# CIERRE DE ETAPA — Evaluador v6 + Auditoría + Refactor + Régimen de Crisis
**Fecha:** 22-Ago-2026 · **Firma:** qwen/qwen3.8-max (Hermes)
**Proyecto:** Botero Trade · rama de investigación `research/01_señales_entry_exit/`

---

## 1. Qué se logró en esta etapa

### A. Evaluador vela a vela v6 → v7 post-auditoría
- 28 señales evaluadas con first-passage bilateral en zz25/zz50/zz75, régimen observable, baseline por celda, p binomial, PF, EV/barra, INDEP.
- 7 señales con p<0.05; las mejores: pcr_put_panic zz75|BAJA (+4.04%, p=0.0015), credit_stress zz75|ALZA (+3.42%), capitulacion zz25|BAJA (+3.40%, p=0.002).
- **Structural break GFC (2009-03-09)** aplicado a todas: credit_ease_exit re-retirada como reliquia pre-QE (+6.99%→−2.84%, p=0.0000); bsi_recovery degradada post-QE (hit 59%→15%).

### B. Auditoría externa (Gemini, verificada dato por dato) + correcciones
- 10 recomendaciones (P0.1-P0.2, P1.3-P1.6, P2.7-P2.10). **Todas aplicadas y verificadas:**
  - P0.1 re-retiro credit_ease_exit ✅ · P0.2 contención tautológica vs genuina ✅
  - P1.3 sesgo de posición documentado ✅ · P1.4 bsi_recovery degradada ✅
  - P1.5 walk-forward del detector ✅ · P1.6 regresión ampliada ✅
  - P2.7 señales D3 ✅ · P2.8 semivida por régimen ✅ · P2.9 ventana INDEP ✅ · P2.10 conclusión ζ ✅

### C. Detector de régimen de crisis (máquina de estados)
- 952 overflows ±3σ → 79 episodios, mediana 13d, 16.9% del tiempo en crisis.
- 8/8 crisis históricas detectadas. Contención clasificada: 68.8% cross-familia (genuina), 6.7% tautológica, 21% punto ciego (198 overflows, 56% D3).
- Walk-forward: vix/vvix/dxy robustas (ρ 0.77-0.82), skew rota (deriva +0.73σ), credit intermedia (pierde GFC bajo ventana expansiva). Serie real credit hallada en el Vault (CREDIT_RATIO).

### D. Semivida de absorción VIX
- Mediana 8.2d; bimodal: **shock normal (peak_z<5σ) = 8d mediana (n=11) vs crisis sistémica (peak_z≥5σ) = 124.5d (n=2)**. El peak_z es observable en tiempo real → clasificador perfecto con esta historia (provisional: N=2 sistémicas).
- Hipótesis ζ: rechazada la oscilación (ζ<1); ζ>1 indistinguible de OU (precisión añadida por auditoría).

### E. Refactor del God file
- `medir_senal.py` (1,497 líneas) → paquete `arnes/` (8 módulos) + fachada de compatibilidad.
- **Regresión: 0 diferencias en 5 señales** (3 base + sorpresa_total + regime_change_exit), contra el original real.

### F. Señales D3 (punto ciego)
- 6 candidatas evaluadas: 0 significativas, 2 marginales (d3_bsi_max +3.31% p=0.069; d3_yield_min +3.92% p=0.088).
- Break test: d3_bsi y d3_yield robustas al quiebre (mejoran post); d3_extremo atrapada como reliquia. No promovidas al catálogo (N diamante).

### G. Singularidades de techos y pisos (bonus)
- P(tríada → pivote) medida en tiempo real: 137 tríadas con exceso de MIN, 88 con exceso de MAX.
- El discriminante pisos vs techos es **D2 (velocidad)**, no D1: ELEVATED_PANIC__FAST_SPIKE → pisos; ELEVATED_PANIC__FAST_CRUSH → techos.

---

## 2. Estado del catálogo

| Estado | Señales |
|--------|---------|
| **Activas robustas** (p<0.05 + sobreviven break) | pcr_put_panic, credit_stress, capitulacion, panico_total, vvix_entry, bsi_washed_out, breadth_contraction_exit |
| **Rescatada diamante** | skew_paranoia_exit (+2.84%, p=0.091, INDEP=71%) |
| **Degradada post-QE** | bsi_recovery |
| **Re-retirada (reliquia)** | credit_ease_exit |
| **Candidatas a retiro** | sub_reaccion (−0.51%), dxy_bearish (−1.69%) |
| **Candidatas D3 (investigación)** | d3_bsi, d3_yield (no en catálogo aún) |

## 3. Pendientes para la próxima etapa
1. **Validador OOS** — capa walk-forward sobre el catálogo v7 (responde "¿se repetirá mañana?").
2. Señales D3 sobre serie diaria completa (8,438 días vs 1,590 pivotes) para multiplicar N.
3. Recalibrar skew (deriva +0.73σ) y decidir tratamiento de credit en ventana expansiva.
4. Actualizar GUIA_EMPLEO.md con el catálogo v7 post-auditoría.
5. Filtro de falsos disparos y detector de trampas por anticipación fallida.
6. Conectar el clasificador shock/sistémico (peak_z) con el dimensionamiento de posición.

---
**Firma:** qwen/qwen3.8-max (Hermes) · 22-Ago-2026
