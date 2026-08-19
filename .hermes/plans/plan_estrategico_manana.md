# PLAN DE TRABAJO ESTRATÉGICO — Sesión 2026-08-17

> Estado: sesión 16-Ago completada. Plan para terminar mañana.

---

## ✅ COMPLETADO HOY (16 de agosto)

| Frente | Detalle |
|---|---|
| Bugs corregidos | D3 std(2)/std(10), S5TW ticker, c75, VOL_ACCELERATING, SKEW 2011 |
| Tríada D1×D2×D3 | Lectura completa: D1=cascade, D2=contraria, D3=filtro |
| 11 estaciones clasificadas | ENTRY (8), EXIT (1), BEARISH (1), NEUTRAL (1) |
| Wins vs Losses | 8 dimensiones con bootstraps, wins/losses separados |
| Clusters validados | MIEDO (4), POSICIONAMIENTO (1), AMPLITUD (2), MACRO (4) |
| "Vender euforia" refutado | FG extremo = todo positivo, no hay venta |
| SKEW/VIX ortogonalidad | ρ=-0.185, p=3e-31 |
| Drift SKEW corregido | Cortado en 2011 (dato LIVE), cascade restaurado +0.41 |
| Especificación operativa | Consolidada en especificacion_operativa.md |
| S5×SV5, PCR, SKEW, BSI×SV5T | Agentes lanzados (PENDIENTE RESULTADOS) |

---

## 🔄 AGENTES — RESULTADOS COMPLETOS (16-Ago)

| Agente | Frente | Resultado |
|---|---|---|
| ✅ | SKEW profundo: cuadrante VIX×SKEW | **PÁNICO TOTAL = PF 8.09, 0 wipeouts, señal más fuerte** |
| ✅ | S5×SV5: validar matriz | **REFUTADA** — colapsa a S5 solo, SV5 es ruido |
| ✅ | PCR completo | ENTRY. D2 flip elimina las 3 wipeouts |
| ✅ | BSI×SV5T: conjunción | Complementarios puros (ρ≈0). Conjunción premium N=5 +4.39% |

### Hallazgos clave de cierre

```
1. PÁNICO TOTAL (VIX↑+SKEW↑): PF 8.09, 82% win 60d, 0 wipeouts, N=55
   → La señal MÁS FUERTE del sistema. SKEW es confirmador de miedo.

2. S5×SV5 REFUTADA: la matriz documentada está INVERTIDA.
   S5↑ → 68% bear (reversión, no continuación). SV5 no discrimina.

3. PCR: D2 flip elimina TODAS las wipeouts (3/3 con FAST_SPIKE/ACCELERATING).
   Confirma el hallazgo de VIX — el filtro D2 es universal.

4. BSI×SV5T: complementarios (ρ≈0). Conjunción rara (N=5) pero premium (+4.39%).
   Mismo patrón que MACRO — conjunción = máxima convicción, baja frecuencia.

5. BUG: decay_check cascade ANY-type (50.57%) vs v3 same-type (40.69%).
```

---

## 📋 PARA MAÑANA — PRIORIDADES

### FASE 1 — Consolidar resultados de agentes (30 min)
- Leer resultados de SKEW profundo
- Leer resultados de S5×SV5
- Leer resultados de PCR
- Actualizar especificación operativa

### FASE 2 — SIGMET (pendiente principal)
- Audit SigMet hazards actuales (edge, thresholds)
- Validar empíricamente cada alerta (VIX≥28, SKEW≥145, etc.)
- Clasificar SIGMETs con probabilidad + CI95 + N (como las estaciones)
- Integrar SKEW como confirmador de SIGMET

### FASE 3 — TAF (pendiente)
- ev_per_day y ftt_days YA están en TAFEntry (Gemini lo implementó)
- Validar que estén correctamente expuestos
- Extension multi-escala (zz25/zz50/zz75) si aplica
- Regla D2 contraria en TAF vs cascade

### FASE 4 — Orphan Interpreter (implementación)
- Diseño está listo (árbol D3 discrimina, D2 gatilla)
- Implementar para VIX (estación piloto)
- Extender a FG, VVIX, BSI (estaciones con D3 discriminante)

### FASE 5 — Cierre y entrega
- Actualizar cascade_calibration.json (dato fresco al cierre)
- pytest + decay check HEALTHY
- Commit final del día
- Plan para fase de producción

---

## 📐 ARQUITECTURA META — Las 4 capas

```
CAPA 2: CASCADE CONVICTION (continuación)
  D1 vote + domino → IC +0.41, PBO 0%
  NO se toca. D2/D3 no pertenecen aquí.

CAPA 1: TAF (dirección)
  D2 contraria → comprar miedo (VVIX/FG/VIX/CREDIT/PCR)
  ev_per_day, ftt_days, p_bull multi-escala

CAPA 3: CONFIRMADORES
  VIX×SV5T cuadrante → convicción
  VIX×SKEW cuadrante → naturaleza del miedo
  S5×SV5 matriz → amplitud+volumen
  D3 filtro → caos apaga cascade en sentimiento

CAPA 4: SIGMET (alertas)
  Alertas extremas con probabilidad + CI95
  Warnings, no entry/exit
```

---

## 🎯 MÉTRICAS OBLIGATORIAS (siempre)

```
- Toda señal: probabilidad + CI95 + N
- Toda distribución: wins y losses SEPARADOS
- Toda regla: validación OOS
- Toda afirmación: bootstrap (2000 iter)
- Nada binario. Nada sin dato.
```