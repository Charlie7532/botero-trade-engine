# RESUMEN CONSOLIDADO — Lo confirmado hoy (dato mata relato)

> Sesión: calibración METAR/SIGMET. Todas las conclusiones con escalas del proyecto (bins D1/D2/D3).

---

## 1. CORRECCIONES DE BUGS

| Bug | Fix |
|---|---|
| D3 = std(5)/std(20) en 8 servicios | → std(2)/std(10) + guard test |
| BSI ticker S5FI en decay_check | → S5TW (línea 61) |
| c75 clon de c50 (z_dom25) | → z_dom50, pesos 0.50/0.50 |
| VOL_ACCELERATING_EXPANSION nunca asignado | → adapters D3 incompletos (solo BSI correcto) |

---

## 2. LA TRÍADA D1×D2×D3 (ortogonal, |ρ|<0.19)

```
D1 (nivel):      TENSIÓN → CASCADE (continuación)          [IC +0.41, PBO=0%]
D2 (velocidad):  MOMENTUM → DIRECCIÓN CONTRARIA (TAF)       [ρ 0.38-0.40]
D3 (volatilidad): DESGASTE → FILTRO DE CASCADE              [gap -15pp FG]
```

---

## 3. D2 — CONFIRMA, NO ANTICIPA. ES CONTRARIANO (parcialmente)

```
Forward ρ (D2→SPY futuro): |ρ|≤0.06  → NO predice
Backward ρ (SPY pasado→D2): |ρ|0.40-0.83 → REFLEJA

COMPRAR MIEDO:    VIX EXTREME_PANIC → +3.05% 20d  ✅ MASIVO
VENDER EUFORIA:   FG EXTREME_GREED → +0.77% 20d  ❌ ES UN MITO
                  (ninguna celda D2×D3 negativa en FG extremo)
```

**El edge está 100% en el MIEDO, no en la euforia.**

---

## 4. D3 — "GASTO DE ENERGÍA", CONTEMPORÁNEO

```
D3 discrimina CASCADE (no dirección):
  FG -15pp | VVIX -9pp | BSI -7pp | PCR -6pp  → caos = MENOS cascade
  SKEW +4pp INVERTIDO (cobertura activa = evento en desarrollo)
  CREDIT CONDICIONAL (±13pp, split por régimen)
  Macro (yield/rotation/dxy) NEUTRO

D3 es ortogonal a nivel y velocidad → dimensión independiente
```

---

## 5. EARLY WARNING — D2 es la señal temprana, D3 la calma pre-tormenta

```
Aproximación al extremo:
  D2 acelera monótonamente (41% en T-2→T-1)
  |D2|>2.5 = 2× riesgo, >4.0 = 3× riesgo, >3.0 = 98% irreversible
  D3<0.5 en T-5 = "calma pre-tormenta" (59% de episodios)

Respuesta post-extremo:
  D3 baja = oportunidad (reversión controlada)
  D3 alta + velocidad media = única zona negativa
```

---

## 6. TIMING — EXTREME_PANIC es AVISO, el PIVOTE es ENTRADA

```
EXTREME_PANIC → pivote zz25: 63% mismo día, 26% ya pasó, 11% 1-3d antes

Comprar en la barra:   +0.85% 20d
Comprar en el pivote:  +2.26% 20d  (+1.41% más)

BENCHMARK EXTREME_PANIC solo (31 trades):
  Hold 20d media +2.79%, mediana +4.76%
  PERO min -24.63% (2008-09-29), -21.69% (2009-02-06), -16.56% (2020-03-06)
  → LEFT TAIL FATAL sin filtros
```

---

## 7. ESTADÍSTICA CONDICIONAL (extremos)

```
P(B|A)    = cascade_50: 76.6% en extremo (vs 50.5% baseline)
P(C|A,B)  = cascade_75: 73.5% si cascadeó
P(C|A,B=0)= 0% si no cascadeó → salir

VIX ≥ 2σ = 34.9 (3.8% del tiempo) — el verdadero extremo
```

---

## 8. ORPHAN SIGNALS — interpretar, no temer

```
N<10 → señal IMPORTANTE que requiere mayor procesamiento

Árbol de decisión (VIX):
  D3 = CONTRACCIÓN (calma): D2 ACELERANDO→76% bull ENTRAR
                             D2 DESACELERANDO→38% bull SALIR
  D3 ≠ CONTRACCIÓN (caos): ~58% → NO OPERAR
```

---

## PREGUNTA ABIERTA PARA REPENSAR

**¿Cómo agrega esta información valor a CASCADE?**

Cascade = D1 + domino (IC +0.41, PBO=0%). NO se toca.

La nueva info NO agrega al cascade (continuación), sino a las CAPAS que lo rodean:
- TAF (dirección): D2 contraria → comprar miedo
- Confirmadores: D3 filtro, VIX×SV5T, pivot zz25
- Entry timing: EXTREME_PANIC alerta → pivot gatillo
- Orphan interpreter: estados N<10 con árbol D1×D2×D3
