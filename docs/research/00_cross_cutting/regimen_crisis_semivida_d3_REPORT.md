# REPORT — Régimen de crisis, semivida de absorción y el punto ciego D3

**Fecha:** 22-Ago-2026
**Autor:** qwen/qwen3.8-max (Hermes)
**Estado:** Hallazgos validados; hipótesis D3 abierta (N insuficiente)
**Módulos:** `research/01_señales_entry_exit/detector_regimen_crisis.py`, `scratch/amortiguacion_vix.py`, `scratch/senal_d3_semivida.py`
**Datos:** `data/research/signals/regimen_crisis_diamantes.json`

---

## 1. Contexto

El análisis de los 198 overflows ±3σ NO contenidos por ninguna señal reveló un patrón
estructural: el 56% de los overflows no contenidos son de la dimensión **D3 (inestabilidad)**
— el sistema de señales lee niveles (D1) y velocidades (D2) pero casi no lee la
inestabilidad en sí misma. Simultáneamente, el arquitecto propuso la hipótesis del
factor de amortiguamiento (ζ) de sistemas de segundo orden como complemento al z-score:
¿cuánto tarda en absorberse un impulso del VIX? ¿Oscila el mercado al volver al
equilibrio?

## 2. La semivida de absorción del impulso VIX (medida, no supuesta)

13 episodios de crisis (z cruza +3σ → decae bajo +2σ), ajuste exponencial post-pico
(modelo OU / primer orden, el mismo que usa López de Prado en reversión a la media):

**Semivida de absorción: mediana 8.2 días** (P25=6.0, P75=11.4)

| Episodio | Peak z | Semivida |
|----------|:---:|:---:|
| LTCM oct-1998 | 3.9σ | 5.7d |
| 11-Sep 2001 | 3.1σ | 6.3d |
| Dot-com jul-2002 | 3.8σ | 3.4d |
| **GFC sep-2008** | **7.9σ** | **112.3d** |
| Volmageddon ago-2011 | 3.7σ | 5.9d |
| **Pandemia mar-2020** | **8.2σ** | **15.7d** |

**Bimodalidad:** shocks ordinarios se absorben en 3-16 días; las crisis estructurales
(GFC peak 7.9σ) tardan >100 días. No existe "la" semivida del VIX — hay dos regímenes
de absorción.

**Convergencia con la máquina de estados:** el deterioro medido empíricamente por el
detector de régimen (9 días para VIX) coincide con la semivida OU (8.2d). La máquina
de estados ya captura el fenómeno sin asumir forma funcional.

## 3. La hipótesis ζ (segundo orden amortiguado): RECHAZADA (precisada tras auditoría Opus, C.3)

> **Corrección de precisión (auditoría 22-Ago):** lo que la evidencia rechaza es
> ζ<1 (subamortiguado = oscilación). Un sistema sobreamortiguado (ζ>1) produce
> ACF positiva y 0 overshoot — es **indistinguible** de OU puro con estos datos.
> Conclusión precisa: *rechazamos la oscilación (ζ<1); no podemos distinguir
> entre reversión OU pura y segundo orden sobreamortiguado (ζ>1).*
> Para trading la distinción es irrelevante: ambos predicen decaimiento monótono.

| Test | Resultado |
|------|-----------|
| Oscilación (ACF1 de residuos < −0.2) | Solo 3/11 episodios con indicio débil |
| GFC: ACF1 de residuos | **+0.83** (persistencia, no oscilación) |
| Pandemia: ACF1 | **+0.60** |
| Cruces del nivel de reposo | 0 en todos los episodios |
| **Overshoot bajo reposo** | **0/11 episodios sobrepasan el 5%** |

El VIX **no oscila al volver al equilibrio**. Un sistema físico oscila porque tiene
inercia acoplada a la restauración; el mercado no tiene inercia mecánica — tiene
**regímenes**. El VIX no rebota alrededor del viejo equilibrio: cae hacia el nivel del
régimen vigente, y si el régimen cambió (2008), se queda alto hasta que el nuevo
régimen se establece.

**Implicación de diseño:** la teoría de segundo orden subamortiguado no aporta al
modelado del decaimiento. El modelo correcto es reversión a la media (OU, primer orden)
o sobreamortiguada (indistinguibles) con posible cambio de nivel de reposo — que es
exactamente lo que la capa SIGMET ya
maneja con su clipping ±2σ y el tratamiento de quiebres.

## 4. Auditoría de la semivida (anti-overshooting del modelo)

| Test | Resultado | Veredicto |
|------|-----------|:---------:|
| B0 validación | mediana 8.2d ≈ 8d esperado | ✅ |
| B1 overshoot real | 0/11 sobrepasan 5% bajo reposo | ✅ No hay overshoot |
| B2 sensibilidad | cambia 34% al mover +2 barras el inicio del ajuste | 🟡 Moderada |
| B3 multi-fase (BIC) | GFC y 2020 mejoran con 2 fases | 🟡 Bifásico |

La semivida es **real pero no constante**: depende del punto de inicio del ajuste, y
las crisis grandes son bifásicas (fase rápida de pánico agudo + fase lenta de
normalización estructural). Un solo κ subestima la fase lenta en GFC/2020.

**Regla de uso:** semivida = estimación de primer orden para shocks ordinarios; para
episodios con peak >5σ o duración >30 barras, usar el modelo bifásico o directamente
la duración medida de la máquina de estados.

## 5. ¿D3 predice la velocidad de absorción? — abierto, N insuficiente

Hipótesis: D3 alto (inestabilidad ya rota) al inicio del episodio → absorción lenta
(cambio de régimen); D3 bajo → absorción rápida (shock ordinario).

| Estado D3 al inicio | N | Absorción media |
|:---:|:---:|:---:|
| INESTABLE (d3z > 1) | 7 | 29 barras |
| CALMADO/MEDIO | 6 | 9 barras |

La dirección apunta como esperado (3.2× más lenta), pero:
- Fisher: p=0.79 (no significativo)
- Spearman(d3_onset, duración): rho=−0.02, p=0.94

**Veredicto:** diamante estadístico puro (protocolo §3.3, tier LOW-MODERATE). La
hipótesis es conceptualmente sólida y la dirección es la esperada, pero N=13 crisis
en 33 años no permite confirmar ni rechazar. No se construye señal operativa todavía.
Se re-evaluará cuando el evaluador corra sobre la serie diaria completa (8,448 barras
vs 1,590 pivotes) — los episodios intra-pivote multiplicarán la muestra.

Alternativas probadas (también sin potencia): peak_z ≥ 5 → lenta (p=0.20); velocidad
de subida z=2→z=3 vs duración (rho=−0.20, p=0.52).

## 6. El punto ciego D3 (inventario)

De los 952 overflows ±3σ históricos (taxonomía SIGMET: 512 MULTI, 359 MODERADO, 81
EXTREMO), 198 (21%) no son contenidos por ninguna señal activa. Distribución:

| Dimensión | No contenidos | Tasa de contención |
|-----------|:---:|:---:|
| D1 (nivel) | 9 | **97%** |
| D2 (velocidad) | 79 | 83% |
| **D3 (inestabilidad)** | **110** | **53%** |

Mayores huecos: sv5_turbulence|d3 (19), bsi|d3 (14), skew|d3 (14), yield_curve|d3 (12).
Además 27 OVERFLOW_EXTREMO (>4σ) sin contener, incluyendo bsi, rotation y yield_curve.

**Interpretación:** los overflows D3 no contenidos son los episodios donde el sistema
**no se estaba absorbiendo** — y no hay señal que los lea. La semivida justifica la
búsqueda: D3 es la candidata natural para distinguir shock (se absorbe solo) de cambio
de régimen (requiere lectura).

## 7. Máquina de estados del régimen de crisis (validada)

Reemplaza la ventana fija (suposición) por una máquina de estados observable
(decisión del arquitecto: "un régimen dura hasta que algo lo cambia"):

- **INICIO:** overflow ±3σ en estación reversiva (vix, vvix, skew, credit)
- **FIN por deterioro:** z-score decae bajo 2σ (duración medida, no supuesta)
- **FIN por transición:** overflow nuevo tras período inactivo cierra el episodio

Resultado: 79 episodios en 33 años. Duración media 26d, mediana 13d, P95 74d.
**16.9% del tiempo en régimen de crisis** (vs 49.7% de la ventana fija de 10d).
Iniciadores: vix 25, skew 25, vvix 17, credit 12.

**Validación de cordura — 8/8 crisis históricas detectadas:**

| Crisis | Episodios | Estaciones |
|--------|:---:|------------|
| LTCM 1998 | 3 | skew, vix |
| Dot-com 2000-02 | 4 | skew, vix |
| GFC 2007-09 | 8 | credit, skew, vix, vvix (todas) |
| Flash oct-2014 | 2 | skew |
| Volmageddon 2018 | 2 | todas |
| Pandemia 2020 | 1 (continuo) | todas |
| Yen carry ago-2024 | 1 | vix, vvix |
| Aranceles abr-2025 | 2 | todas |

Estaciones de nivel (yield_curve, dxy) NO revierten (7,000+ días "fuera de escala")
— son quiebres estructurales de era, no crisis. Se excluyen de la máquina y se tratan
como marcadores de cambio de era.

## 8. Conclusiones y pendientes

1. ✅ Semivida medida (8.2d mediana) y auditada (sin overshoot, bifásica en crisis grandes)
2. ✅ Hipótesis ζ: RECHAZADA la oscilación (ζ<1); ζ>1 indistinguible de OU — precisado tras auditoría Opus (C.3)
3. ✅ Máquina de estados validada (8/8 crisis, 16.9% del tiempo)
4. ✅ **P2.8 — Semivida por régimen (22-Ago):** separación limpia en dos regímenes, sin solapamiento:
   - **SHOCK NORMAL** (peak_z < 5σ, n=11): mediana **8d** (P25=6.5, P75=10.5, máx 23d)
   - **CRISIS SISTÉMICA** (peak_z ≥ 5σ, n=2: GFC 200d, pandemia 49d): mediana **124.5d**
   - El peak_z es observable en tiempo real → clasificador binario perfecto con esta historia (N=2 sistémicas = diamante; la regla es provisional hasta más episodios)
5. ✅ **P2.9 — Ventana INDEP calibrada (22-Ago):** Spearman del ranking INDEP 3d/5d/7d = 0.985/0.948/0.952 → ranking estable; la ventana de 5 días queda empíricamente justificada. `evaluar()` ahora acepta `ventana_f3` (default 5, sin cambio de comportamiento).
6. 🟡 Hipótesis D3→absorción: abierta, N insuficiente (diamante LOW-MODERATE)
7. ✅ **P2.7 — Señales D3 evaluadas (22-Ago):** 0 significativas, 2 marginales; break test atrapó `d3_extremo` como reliquia y confirmó `d3_bsi`/`d3_yield` robustas (ver `data/research/signals/senales_d3_break_test.json`)
8. 📌 Pendiente: re-evaluar D3 sobre serie diaria completa (más episodios)

---
**Firma:** qwen/qwen3.8-max (Hermes) · 22-Ago-2026
