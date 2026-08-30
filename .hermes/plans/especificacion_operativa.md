# ESPECIFICACIÓN OPERATIVA — Clasificación de Señales METAR

> Estado: consolidado post-auditoría. Fecha: 2026-08-16.
> Cada señal: probabilidad + CI95 + N. Dato mata relato.

---

## 1. CLUSTERS ECONÓMICOS

Los 11 indicadores agrupados por lo que miden:

### MIEDO (4 estaciones) — comprar miedo extremo

| Estación | Rol | D1 extremo | Señal | Evidencia |
|---|---|---|---|---|
| **VVIX** | ENTRY 🥇 | EXTREME_VVIX | +2.69% 20d, Kelly 61% | Mejor individual del sistema |
| **FG** | ENTRY | EXTREME_FEAR | +4.4% 20d, WR 82% | Señal más alcista, N=22 |
| **VIX** | ENTRY | EXTREME_PANIC | +2.79% 20d, 2 wipeouts | Necesita filtro D2 flip |
| **SKEW** | CONTRARIANO | EXTREME_PARANOIA | +2.36% 60d, WR 74% | Ortogonal a VIX (ρ=-0.185) |

**Regla MIEDO:** comprar miedo en cualquiera, filtrar VIX con D2 flip.
VVIX solo basta. La conjunción no suma sobre VVIX.
SKEW mide miedo de COLA (institucional); VIX mide miedo de VOLATILIDAD.
NO coinciden (p=3e-31) — son complementarios, no confirmadores.

**🔥 CUADRANTE VIX×SKEW (la señal más fuerte del sistema, validada 16-Ago):**

| Cuadrante | N | 60d | Win | PF | Wipeouts |
|---|---|---|---|---|---|
| **PÁNICO TOTAL (VIX↑+SKEW↑)** | 55 | **+6.81%** | 82% | **8.09** | **0** |
| Crisis sin miedo (VIX↑+SKEW↓) | 1210 | +5.13% | 74% | 3.64 | 11 |
| Miedo silencioso (VIX↓+SKEW↑) | 1192 | +2.15% | 74% | 2.26 | 3 |
| Calma total (VIX↓+SKEW↓) | 5947 | +2.07% | 69% | 2.15 | 8 |

**PÁNICO TOTAL = PF 8.09, 0 wipeouts, N=55.** Cuando VIX y SKEW coinciden en extremo
(ambos miedos al máximo), es el ultimate contrarian buy. No es alarma — es oportunidad.
SKEW funciona como CONFIRMADOR: califica la NATURALEZA del miedo (volatilidad vs cola).

### POSICIONAMIENTO (1 estación)

| Estación | Rol | D1 extremo | Señal |
|---|---|---|---|
| **PCR** | ENTRY ⬆️ | EXTREME_PUT_PANIC | +2.26% 20d, WR 79%, Kelly 48% |

**PCR fue reclasificado de NEUTRAL a ENTRY.**
SKEW ya NO pertenece a este cluster (está en MIEDO).

**PCR detallado (16-Ago):**
- D2 dirección: ρ=-0.216 (p=3.7e-11) — contraria, como las demás.
- D1 nivel: ρ=-0.267 (p=1.9e-16) — PCR alto (más puts) = miedo = bullish.
- D3 cascade: ρ=-0.045 (p=0.18) — NO discrimina (a diferencia de FG/VVIX/BSI).
- PCR vs SKEW: ρ=-0.221 (p=2.4e-56) — CONTRADICEN, miden dimensiones opuestas.
- 🔴 D2=building es ESTRUCTURAL en 96% de señales PCR → el filtro D2 flip NO aplica.
  El gate correcto es CALIDAD N≥10: subconjunto N10-30 (WR 85%, Kelly 55%, 0 wipeouts).
  N<10 (76% de señales) = todas las colas letales (2008, COVID).

### AMPLITUD (2 estaciones)

| Estación | Rol | D1 extremo | Señal |
|---|---|---|---|
| **BSI** | ENTRY | BREADTH_WASHED_OUT | +2.6% 20d, WR 69%, N=58 |
| **SV5T** | ENTRY | EXTREME_TURBULENT | 0 wipeouts, más seguro |

**REFUTADO: matriz S5×SV5** (16-Ago):
- La matriz colapsa a S5 solo. SV5 (volumen breadth) es RUIDO.
- S5↑ → 68% bear (REVERSIÓN, no continuación). Las etiquetas "Rally con convicción" están INVERTIDAS.
- SV5 no discrimina (Δ1.6pp, CI cruza cero).
- BSI (S5TW) solo = predictor de dirección por reversión. SV5T no aporta.
- BUG detectado: decay_check usa cascade ANY-type (50.57%) vs v3_fact_table_engine same-type (40.69%).

### MACRO (4 estaciones)

| Estación | Rol | D1 extremo | Señal |
|---|---|---|---|
| **CREDIT** | ENTRY 🥇 | CREDIT_STRESS | +3.00% 20d, Kelly 50%, N=82 |
| **YIELD** | EXIT | EXTREME_STEEPNING | PF 0.73, Kelly -0.19 |
| **DXY** | BEARISH ⬇️ | EXTREME_STRENGTH | -1.94% 20d, WR 28% |
| **ROTATION** | NEUTRAL | — | Solo drift SPY |

---

## 2. REGLAS DE ENTRADA Y SALIDA

### ENTRADA (producción, sin zigzag)

```
AVISO:   ≥3 estaciones ENTRY en D1 extremo
FILTRO:  VIX debe tener D2 flip ↓ (FAST_CRUSH o DECELERATING_DOWN)
         D3 no caos (VOL_EXTREME_SQUEEZE o VOL_MODERATE_COMPRESSION)
ENTRAR:  en la barra de señal (sin esperar pivote)
HOLD:    20d o hasta señal de salida
```

### SALIDA

```
EXIT 1:  YIELD EXTREME_STEEPNING → reducir/exposición
EXIT 2:  D2 flip ↑ + D3 expansión combinados → corta drawdown a la mitad
```

### PROHIBIDO

```
- NO operar en euforia (FG EXTREME_GREED = todo positivo, no hay venta)
- NO usar zigzag para timing (solo para entrenamiento/labeling)
- NO promediar wins con losses (mostrar distribución completa)
- NO mezclar estados N<10 con N≥30 en la misma métrica
```

---

## 3. LECTURA DE LA TRÍADA D1×D2×D3

```
D1 (nivel):      TENSIÓN → CASCADE (continuación)      [IC +0.41, PBO=0%]
D2 (velocidad):  MOMENTUM → DIRECCIÓN CONTRARIA (TAF)   [ρ 0.38-0.40]
D3 (volatilidad): DESGASTE → FILTRO DE CASCADE           [gap -15pp FG]
```

- D2 es contraria: comprar miedo (VIX/FG/VVIX), pero con TIMING (D2 flip)
- D3 filtra cascade en FG/VVIX/BSI/PCR (caos = menos cascade)
- D3 es ortogonal a D1 y D2 (|ρ|<0.19)
- D3 en estaciones macro es NEUTRO (no usar)

---

## 4. SEÑALES HUÉRFANAS (N<10)

```
Un estado N<10 NO es "ignorar" — es "interpretar con vector completo D1×D2×D3".

Regla (Orphan Interpreter — pendiente de implementar):
  D3 CONTRACCIÓN (calma) + D2 ACELERANDO → 76% bull → ENTRAR
  D3 CONTRACCIÓN + D2 DESACELERANDO → 38% bull → SALIR
  D3 NO CONTRACCIÓN (~58%) → NO OPERAR (moneda al aire)
```

---

## 5. CORRECCIONES APLICADAS

| Corrección | Detalle |
|---|---|
| D3 bug | std(5)/std(20) → std(2)/std(10) en 8 servicios |
| S5TW | BSI ticker corregido (era S5FI) |
| c75 | ya no es clon de c50 (z_dom50, pesos 0.50/0.50) |
| VOL_ACCELERATING | 4 edges D3 (antes 3, nunca asignado) |
| SKEW 2011 | Edges solo con datos LIVE post-2011 (sin retroactivo CBOE) |
| PCR | Reclasificado de NEUTRAL a ENTRY |
| DXY | Reclasificado de NEUTRAL a BEARISH |
| "Vender euforia" | Refutado — FG extremo todo positivo |