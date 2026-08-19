# CLASIFICACIÓN POR NATURALEZA — Las 3 categorías (lead-time)

> Marco conceptual central del sistema METAR. Juan Andrés, 17-Ago-2026.
> Modelo: PLA (matriz lógica programable) — múltiples entradas, múltiples salidas,
> interdependencias internas. Cada indicador alimenta UNA o VARIAS salidas.

---

## 1️⃣ SALUD DE LA ECONOMÍA (independientes del mercado, generan tendencias)

**Lead más largo.** La economía se deteriora ANTES de que el mercado lo refleje.

```
  CREDIT (HYG/LQD)  = salud del crédito corporativo → ¿las empresas se financian?
  YIELD_CURVE (10Y-3M) = salud del ciclo macro → ¿recesión o expansión?
  DXY               = salud del dólar → ¿flujos internacionales?
  ROTATION (salida A) = ¿el dinero SALE o ENTRA a USA? → relacionado a DXY y liquidez
```

## 2️⃣ PRIMEROS SENTIMIENTOS (cómo actúan futuros/opciones para proteger)

**Lead medio.** La protección se compra ANTES de que el mercado caiga — los
institucionales se cubren primero.

```
  VIX   = volatilidad implícita → precio del "seguro" de volatilidad
  VVIX  = vol del VIX → qué tan estable es el miedo
  PCR   = put/call → posicionamiento bajista (put panic = piso) Y
          alcista (call heavy = techo) — AMBOS lados
  SKEW  = prima de puts OTM → cuánto pagan por seguro de CRASH
```

## 3️⃣ LO QUE EL MERCADO ESTÁ HACIENDO (realidad, acción)

**Lead más corto.** La acción REAL — la confirmación final.

```
  BSI (S5TW) = breadth de precio → ¿cuántos stocks participan?
  SV5T       = breadth de volumen → ¿con qué fuerza participan?
  FG         = sentimiento sintetizado CNN (real 2011+, 3,880 barras)
               ⚠️ SOLO usa S&P 500 large caps → le faltan SMALL CAPS (IWM)
               ⚠️ Tiene gemelo sintético FG_SP (2009+, 4,358 barras) con 7
               sub-componentes: FGBI, FG_BREADTH, FG_STRENGTH, FG_VIX,
               FG_MOMENTUM, FG_SAFEHAVEN, FG_PUTCALL, FG_JUNKBOND
               → mismo patrón que SKEW (real + sintetizado)

VALIDADO (17-Ago): FG oficial CNN
  - Distribución SIMÉTRICA (EXTREME_FEAR 582d = EXTREME_GREED 583d)
  - Suavizado por ventana 504d (2 años de inercia)
  - EXTREME_FEAR → +1.85% 20d (WR 67.4%, PF 2.30) → +3.12% 40d (PF 3.06)
  - EXTREME_GREED → +0.81% 20d (positivo también)
  - "Vender euforia es mito" re-confirmado. ρ(FG, fwd20d) = -0.10 (contrarian)
  - CANARIO small-cap (IWM): TIPO-FEAR (CNN neutral + small en miedo) = -0.90% 20d
    (sub-reacción, no rebote); TIPO-GREED (small lideran) = +2.82% 40d
  - ⚠️ PENDIENTE: D2 (velocidad FG) y D3 (volatilidad FG) no discriminados aún
  ROTATION (salida B) = liderazgo sectorial → ¿el dinero rota defensivo↔cíclico?
               → protección de portafolios/ETF con mandato invertido
```

---

## 🔌 ROTATION es DUAL (una entrada, dos salidas)

```
SALIDA A (economía, cat. 1):  dinero sale/entra a USA — relacionado a DXY y liquidez
SALIDA B (acción, cat. 3):    dinero rota defensivo↔cíclico — protección con mandato

Mismo indicador, dos preguntas distintas. PLA.
```

---

## 🔗 La cadena causal (lead-time)

```
ECONOMÍA (1) → PROTECCIÓN (2) → ACCIÓN (3)

  CREDIT/YIELD se deterioran
       → institucionales compran puts/SKEW↑ (protección)
       → el mercado AÚN no vendió (S5 mantiene)
       → recién después S5 COLAPSA (venta real)

Esto explica el hallazgo del comité:
  MIEDO SIN VENTA (S5 mantiene) = etapa 2, venta aún no llega → ESPERAR
  MIEDO CON VENTA (S5 colapsa)  = etapa 3, corrección ya pasó → COMPRAR
```

---

## 📐 Otras dualidades detectadas

```
PCR:   DUAL — put panic (piso) + call heavy (techo)
SKEW:  CONFIRMADOR de naturaleza del miedo (cola vs volatilidad)
FG:    SINTETIZADO — le faltan small caps (rediseño en curso)
```

---

## 🎯 La regla operativa que emerge de la clasificación

```
COMPRAR (piso):  economía débil (CREDIT/YIELD) + protección extrema (PCR/SKEW)
                 + ACCIÓN ya descargada (S5 colapsó) → capitulación completa

ESPERAR:         protección extrema pero ACCIÓN aún no (S5 mantiene) → sub-reacción

VENDER (techo):  protección comprada al alza (call heavy) + acción en máximos
                 (S5 recuperó) → euforia completa
```