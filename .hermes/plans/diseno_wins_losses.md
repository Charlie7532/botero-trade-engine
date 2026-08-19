# DISEÑO: Estudio WINS vs LOSSES — Eventos Extremos

> Filosofía: "El precio de no acertar es muy alto." No promediamos.
> Mostramos la distribución completa de lo que se gana y lo que se pierde.

---

## 1. QUÉ MEDIR (por estación, por estado extremo)

```
Para cada D1_bin extremo de las 7 estaciones ENTRY:

A. PROBABILIDAD DE ACIERTO
   - % de trades donde SPY forward > 0 (win rate)
   - % de trades donde SPY forward > 2% a 20d (win significativo)
   - % de trades donde SPY forward < -5% a 20d (loss catastrófico)
   - N total de trades, CI95 binomial

B. DISTRIBUCIÓN DE WINS
   - Magnitud: P25, P50, P75, P90, max del retorno cuando gana
   - Duración: cuántos días tarda en materializarse el win
   - % del capital ganado en wins sobre el total

C. DISTRIBUCIÓN DE LOSSES
   - Magnitud: P25, P50, P75, P90, min (max drawdown)
   - Duración: cuántos días dura el drawdown antes de recuperar
   - % del capital perdido en losses sobre el total
   - ¿Hay wipeouts? (loss > 20%)

D. RATIO COSTO/BENEFICIO
   - Win/Loss ratio: media(win) / |media(loss)|
   - Profit factor: suma(wins) / |suma(losses)|
   - Expected value: win_rate × avg_win − loss_rate × |avg_loss|
   - Kelly fraction: fracción óptima de capital a apostar

F. TIMING VS ZIGZAG (precisión de entrada)
   - Tipo: ANTICIPADA (antes del pivote) / EN_PIVOTE / RETRASADA (después)
   - Días al pivote más cercano: negativo = anticipada, positivo = retrasada
   - Costo de anticipación: % drawdown desde entrada hasta el pivote
   - Costo de retraso: % del movimiento ya perdido al entrar tarde
   - ⚠️ CUIDADO CON SIGNOS: MIN=piso (entrada long), MAX=techo

G. DURACIÓN Y ESTRUCTURA DEL MOVIMIENTO
   - Duración total del movimiento (días hasta agotarse)
   - ¿Fue CONSOLIDACIÓN? (movimiento lateral, <2% en 10d)
   - ¿Fue CONTINUACIÓN? (aceleró después de la entrada)
   - ¿Fue CUCHILLO CAYENDO? (entrada anticipada con pérdida >5% antes del pivote)
   - ¿Qué pudo advertirlo? (D2, D3, VIX en el momento de la entrada)

H. CALIDAD DE MUESTRA — SEPARAR POR N (¡NO MEZCLAR!)
   - Tier 1: N ≥ 30 → confiable, CI estrecho
   - Tier 2: 10 ≤ N < 30 → direccional, CI amplio, cautela
   - Tier 3: N < 10 → SEÑAL HUÉRFANA → requiere Orphan Interpreter
   - ⚠️ NUNCA promediar N=3 con N=47 en la misma métrica
   - Para huérfanas: reportar estado D1×D2×D3 completo, no solo p_bull
   - ¿El edge viene de estados poblados o de huérfanos ruidosos?
```

---

## 2. ESCALAS (lo aprendido)

```
✅ Usar state_key del METAR (D1_bin, no "VIX ≥ 30")
✅ D3 = std(2)/std(10) (corregido)
✅ BSI = S5TW (corregido)
✅ No usar zigzag para timing (solo para labeling)
✅ Cada métrica con CI95 bootstrap (2000 iter)
✅ Separar SIEMPRE wins de losses — nunca promediar sin separar
```

---

## 3. ESTACIONES A MEDIR

```
ENTRY (7): FG > VVIX > SKEW > SV5T > VIX > BSI > CREDIT
EXIT (1):  YIELD_CURVE
NEUTRAL (3): ROTATION, DXY, PCR (solo para confirmar neutralidad)
```

---

## 4. MÉTODO

```
1. Clasificar cada barra con el adapter → state_key (D1__D2__D3)
2. Filtrar D1_bin extremo de cada estación
3. Evitar clustering: min 10 días entre trades del mismo tipo
4. Medir SPY forward 5/10/20/40d desde la entrada
5. Separar en WINS (ret > 0) y LOSSES (ret ≤ 0)
6. Bootstrap CI95 para cada métrica
7. Reportar distribución completa, NO promedios solos
```

---

## 5. OUTPUT ESPERADO

```
Por estación:
  ┌────────────────────────────────────────────┐
  │ FG EXTREME_FEAR (N=47, 1993-2026)          │
  │ ├─ Win rate: 82% (CI95 [71-91%])           │
  │ ├─ WINS (N=38):                            │
  │ │   P50=+5.2%  P90=+15.8%  max=+32.1%     │
  │ │   duración mediana: 12 días              │
  │ ├─ LOSSES (N=9):                           │
  │ │   P50=-3.1%  P10=-12.4%  min=-18.2%     │
  │ │   duración mediana: 8 días               │
  │ ├─ Profit factor: 4.2                      │
  │ ├─ Kelly: 68%                              │
  │ └─ ⚠️ 2008: 3 losses consecutivas (-45%)    │
  └────────────────────────────────────────────┘
```

---

## 6. AGENTES

```
Agente 1: FG + VVIX + SKEW (top 3 ENTRY)
Agente 2: SV5T + VIX + BSI + CREDIT (4 ENTRY)
Agente 3: YIELD + ROTATION + DXY + PCR (EXIT + NEUTRAL)
```

---

## 7. REGLAS

```
- NO promediar sin separar wins/losses
- NO usar zigzag para timing
- NO umbrales crudos (solo bins del METAR)
- Toda métrica con CI95 + N
- Identificar CLÚSTERS DE PÉRDIDAS (rachas)
```