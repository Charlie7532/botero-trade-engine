# PLAN MAESTRO — v2.0 (post-auditoría López de Prado)

> **Filosofía:** Dato mata relato. Probabilístico. Nada binario.

---

## 1. HECHOS VALIDADOS (irrefutables)

| # | Hecho | Métrica | Evidencia |
|---|---|---|---|
| 1 | State vector (D1×D2×D3, 11 est) es 3.2× superior a D1 para DIRECCIÓN | IC -0.489 vs -0.155 | 1,589 pivotes, 33 años |
| 2 | D2/D3 capturan NO-LINEALIDAD que Spearman pierde | MI gap +0.44~0.52 | yield_vel, dxy_val, vix_vol, skew_val |
| 3 | VIX×SV5T cuadrante: gap 48.9pp de cascade | 76.6% vs 27.6% | N>300 por cuadrante |
| 4 | Cascade Conviction NO está overfit | PBO=0.0%, OOS 92.9% folds | Bootstrap CI [+0.37,+0.45] |
| 5 | Cascade y dirección son ORTOGONALES | IC cruzado -0.086 | Dos señales independientes |

---

## 2. INTUICIONES REFUTADAS (no volver a ellas)

| Intuición | Dato | Veredicto |
|---|---|---|
| "Familias" por similitud conceptual | Clustering k-means da 4 clusters distintos | ❌ REFUTADO |
| Triple barrier mejora cascade | IC cae de +0.41 a +0.11 | ❌ REFUTADO |
| Agregar D2 al cascade_conviction | Degrada OOS -0.15 | ❌ REFUTADO |
| SV5T vota dirección | Degrada IC -0.01 | ❌ REFUTADO |
| Per-ticker edges | Degrada composite | ❌ REFUTADO |

---

## 3. CLUSTERING REAL (no intuición)

```
Cluster 1: pcr, fg, bsi        → sentimiento + amplitud
Cluster 2: vvix, dxy           → vol-of-vol + dólar
Cluster 3: vix, credit, yield  → estrés + macro
Cluster 4: sv5_turbulence      → ÚNICO (independiente)
```

PCA: 63% varianza en 3 componentes, dimensionalidad efectiva ≈ 6.

---

## 4. ARQUITECTURA FINAL — 3 capas ortogonales

```
┌─────────────────────────────────────────────────────────────┐
│                    CONVERGENCE REPORT                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CAPA 1 — STATE VECTOR (base)                               │
│    11 estaciones × state_key(D1×D2×D3) → zk_p_bull          │
│    Agregado → p_bull global → DIRECCIÓN (IC -0.489)         │
│                                                             │
│  CAPA 2 — CASCADE CONVICTION (validado, PBO=0%)             │
│    D1 vote + domino, pesos 0.66/0.34, type mask             │
│    → CASCADE (IC +0.41)                                     │
│                                                             │
│  CAPA 3 — CONFIRMADORES                                     │
│    VIX×SV5T cuadrante (48.9pp)                              │
│    D2/D3 no-lineales (MI gap)                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Capa 1 y Capa 2 son ORTOGONALES → no fusionar.**
Capa 3 modula la CONVICCIÓN de ambas.

---

## 5. DECISIONES DEL DATO (respondidas)

| Pregunta | Respuesta |
|---|---|
| ¿Un score o dos? | **DOS** (cascade + dirección, ortogonales) |
| ¿Complementa o reemplaza? | **Complementa** (coincidencia = +42pp) |
| ¿Familias o flat? | **Flat 11** (clustering refutó familias) |
| ¿D2 explícito? | **NO** (ya implícito en state_key) |
| ¿Incertidumbre? | **VIX×SV5T + MI no-lineal**, no dispersión |

---

## 6. SECUENCIA DE IMPLEMENTACIÓN

| Fase | Qué | Validación |
|---|---|---|
| 1. State Vector Engine | Exponer p_bull global (11 est) en ConvergenceReport | IC -0.489 OOS |
| 2. Capa 3 Confirmadores | VIX×SV5T + D2/D3 no-lineales | Gap 48.9pp |
| 3. Structural break awareness | Decay check por década (2020s más fuerte) | CUSUM p<0.05 |
| 4. Integración | Report final: dirección + cascade + convicción | Bootstrap CI |

---

## 7. NO SE TOCA

- ❌ Pesos 0.66/0.34, type mask, fact stores, 150 estados
- ❌ Cascade_conviction (PBO=0%, ya es óptimo)
- ✅ Solo se AGREGA (capa 1 y 3 son nuevas, no modifican la 2)

---

## 8. PRÓXIMO PASO

Auditar este plan (riesgos, supuestos, blind spots) → luego prompt de implementación.
