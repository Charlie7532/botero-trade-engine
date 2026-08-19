# LECTURA DE LA TRÍADA D1×D2×D3 — Resultado de 2 agentes expertos

> **Dato mata relato.** Resultados medidos con 1,589 pivotes SPY zz25 (33 años).

---

## La tríada — 3 dimensiones ORTOGONALES, 3 preguntas distintas

```
D1 (nivel):      ¿Dónde estoy?          → CASCADE (continuación)     [IC +0.41]
D2 (velocidad):  ¿Hacia dónde voy?      → DIRECCIÓN CONTRARIA (TAF)  [ρ 0.38-0.40]
D3 (volatilidad): ¿Cuánta energía gasté? → FILTRO DE CASCADE         [gap hasta -15pp]
```

**D1, D2, D3 son ortogonales entre sí (|ρ|<0.19)** — miden cosas independientes.

---

## D2 (velocidad) — CONFIRMA, NO ANTICIPA. ES CONTRARIANO.

```
Forward ρ (D2 → SPY futuro):  |ρ| ≤ 0.06  → NO predice
Backward ρ (SPY pasado → D2): |ρ| 0.40-0.83 → REFLEJA lo reciente
→ D2 es el ESPEJO del movimiento, no el profeta
```

| Tipo de estación | D2↑ significa | Próximo leg |
|---|---|---|
| Miedo (VIX, VVIX, PCR) | miedo subiendo | **BULL** (comprar el miedo) |
| Euforia (FG, BSI, Credit, Rotation) | greed acelerando | **BEAR** (vender la euforia) |

**Estaciones D2-informativas:** FG, BSI, VIX, Rotation, Credit, PCR, VVIX
**D2-inútiles:** SV5T (caos/volumen), DXY (asset externo)
**D2-marginales:** SKEW, Yield

**Rol:** señal CONTRARIA de dirección → TAF (NO cascade).

---

## D3 (volatilidad) — "GASTO DE ENERGÍA". CONTEMPORÁNEO, no predictivo.

```
D3 = std(2d)/std(10d) = ¿el indicador está estable o caótico?
Forward ρ < 0.03 (no predice) | Contemporáneo 0.29-0.50 (refleja el movimiento)
```

| Estación | D3 efecto cascade | Mecanismo |
|---|---|---|
| FG | **-15pp** (MIN: -25pp) | Oscilador bounded → whipsaw = resolución → sin cascade |
| VVIX | -9pp | Ídem |
| BSI | -7pp | Ídem |
| PCR | -6pp | Ídem (refuerzo) |
| SKEW | **+4pp** (INVERTIDO) | Cobertura activa = evento en desarrollo → MÁS cascade |
| CREDIT | **CONDICIONAL** (±13pp) | caos+estrés=-7pp, caos+ease=+7pp |
| Yield/Rot/SV5T/DXY | ~0 | Movimiento lento, D3 = ruido |
| VIX | ~0 | D1 ya captura (IC -0.40) |

**Regla de lectura D3:**
- Filtro NEGATIVO de cascade: FG, VVIX, BSI (PCR refuerzo)
- ALERTA POSITIVA: SKEW (cobertura activa)
- CONDICIONAL: Credit (split por régimen)
- IGNORAR: Yield, Rotation, SV5T, DXY, VIX

---

## 🔴 FIX pendiente — BSI ticker

```
decay_check_cascade_conviction.py línea 61:
  "bsi": {"ticker": "S5FI"}   ❌ → debe ser "S5TW"  ✅

BSI = S5TW = % S&P 500 sobre 20-DMA (táctica)
S5FI = % sobre 50-DMA (intermedia) — OTRO indicador
S5TH = % sobre 200-DMA (estructural)
```

---

## Implicación arquitectónica

```
Cascade_conviction (capa 2): D1 + domino  → NO cambiar (PBO=0%)
TAF (capa 1): D2 contraria → dirección del próximo leg
Confirmadores (capa 3): D3 filtro + VIX×SV5T + S5×SV5
Orphan Interpreter: D1×D2×D3 completo en estados N<10
```