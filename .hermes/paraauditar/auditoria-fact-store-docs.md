# AUDITORÍA — fact-store-mandatory-reference.md + fact_store_v3_architecture.md
## Botero Trade — 20-Ago-2026

---

## DOCUMENTO 1: fact-store-mandatory-reference.md

| Campo | Valor |
|-------|-------|
| **Ubicación** | `.agents/rules/fact-store-mandatory-reference.md` |
| **Líneas** | 41 |
| **Tamaño** | 1,884 bytes |
| **Rol** | Gatekeeper — regla que obliga a todo agente a leer `fact_store_v3_architecture.md` antes de trabajar con fact stores |

### ✅ ACIERTOS

1. **UNCONDITIONAL y applies to ALL agents** — lenguaje de contrato. Sin ambigüedad.
2. **Lista exhaustiva de triggers** (líneas 7-13): cubre todos los casos donde un agente podría tocar fact stores sin saber lo que contienen.
3. **"STOP. Before writing ANY code..."** — comando imperativo. No es una sugerencia, es una orden.
4. **"Why This Rule Exists"** (líneas 32-41): documenta el COSTO de violar la regla. El usuario perdió tiempo significativo. Los agentes cometieron 5 errores documentados.
5. **Lista de errores pasados** (líneas 34-39): reinterpretación de fórmulas, mala interpretación de `p_bull`, descarte de estados low-N que son diamantes, generación de datos sin saber su empleo.

### ⚠️ RIESGOS

| Riesgo | Descripción | Mitigación |
|--------|-------------|------------|
| **Auto-referencia circular** | La regla dice "lee fact_store_v3_architecture.md", pero si ese documento se vuelve obsoleto, la regla sigue apuntando a él sin saberlo | Agregar un hash/checksum del documento referenciado para detectar obsolescencia |
| **Sin mecanismo de enforcement** | Es un archivo .md que el agente debe leer voluntariamente. Si el agente no lo lee, no hay consecuencia | Podría integrarse como pre-commit hook o CI check |
| **No versionado** | Si `fact_store_v3_architecture.md` se actualiza a V4, esta regla queda desactualizada | Agregar `version: 3` y `last_updated: 2026-08-XX` |

### 📊 VEREDICTO: ✅ RESCATABLE — Gatekeeper correcto y necesario

---

## DOCUMENTO 2: fact_store_v3_architecture.md

| Campo | Valor |
|-------|-------|
| **Ubicación** | `.agents/references/fact_store_v3_architecture.md` |
| **Líneas** | 864 |
| **Tamaño** | 47,823 bytes |
| **Secciones** | 16 |
| **Rol** | Documentación canónica de los fact stores |

### ESTRUCTURA (16 secciones)

```
 1. QUÉ SON LOS FACT STORES            → definición, 4 capas de datos
 2. CADENA DE GENERACIÓN               → Vault → fact_table_engine → JSON
 3. TRÍADA ZIGZAG                      → vector multi-escala, patrones inter-escala
 4. LAS 3 DIMENSIONES (D1×D2×D3)       → fórmulas, unidades, clasificación
 5. ESTRUCTURA DE UN ESTADO            → JSON schema de cada estado
 6. CAPA ESTÁNDAR                      → zz25/zz50/zz75 a nivel diario
 7. CAPA CINEMÁTICA                    → zigzag_kinematic (retorno de pierna)
 8. REGÍMENES DE DIVERGENCIA TEMPORAL   → convergencia, divergencia, asimetría
 9. OPERATIONAL GUIDANCE               → taxonomía 4D
10. ESTACIONES METAR (11)              → lista de los 11 fact stores
11. REGLAS DE INTERPRETACIÓN           → cómo leer señales desde fact stores
12. SEÑALES INCONDICIONALES VS CONDICIONALES
13. CONFIDENCE TIERS Y MUESTRAS MÍNIMAS
14. DATOS DE ORIGEN                    → Neon Vault
15. GUÍA DE EMPLEO                     → qué dato responde qué pregunta
16. ANTI-PATRONES                      → 10 errores a nunca repetir
```

### ✅ ACIERTOS

1. **Fact Stores vs quants_obs — Son Instrumentos Diferentes** (Sección 1):
   - ✅ Diferencia claramente PROSPECCIÓN (fact store) de HISTORIA (quants_obs)
   - ✅ Explica el sesgo de selección por `pivot_type` en quants_obs
   - ✅ "Si divergen >20%, investigar el sesgo de selección por pivot_type"

2. **Cadena de Generación** (Sección 2):
   - ✅ Trazabilidad completa: Neon → TimescaleDataStore → v3_fact_table_engine → JSON
   - ✅ Documenta los 4 cómputos (standard, kinematic, structural_momentum, domino)
   - ✅ Nombra los 11 scripts generadores

3. **Vector de Estado Multi-Escala** (Sección 3):
   - ✅ "Cada estación emite un VECTOR, no un escalar"
   - ✅ 6 patrones inter-escala con significado e implicación operacional
   - ✅ Conecta con `convergence_compositor.py` (el código real)

4. **Confidence Tiers** (Sección 13):
   - ✅ Define N mínimo por tier (N≥100 confiable, N=30-99 moderado, N=10-29 baja, N<10 DIAMANTE)
   - ✅ "Low-N states are statistical diamonds, not noise"
   - ✅ Alineado con nuestro marco Rareza=Riqueza

5. **Anti-Patrones** (Sección 16):
   - ✅ 10 errores documentados con ejemplos concretos
   - ✅ Cubre exactamente los errores que Gemini cometió en el incidente del 19-Ago

### 🔴 PROBLEMAS ENCONTRADOS

#### P1: Niveles de Confianza SIN bootstrap CI95
```
Sección 13 define tiers por N absoluto (N≥100, N=30-99, N=10-29, N<10).
Pero no menciona bootstrap CI95 como métrica complementaria.

N=100 con CI95 que cruza cero → NO es confiable, aunque N≥100.
N=8 con CI95 tight que no cruza cero → puede ser más confiable que N=100 con CI95 ancho.

El tier por N absoluto es ÚTIL como heurística, pero INCOMPLETO sin CI95.
```

#### P2: Ausencia de N_eff (tamaño de muestra efectivo)
```
El documento no menciona N_eff en ninguna sección.
Las señales que disparan en ráfagas (clustering temporal) inflan el N bruto.

Ejemplo del incidente: credit_equity_divergence N=120 → N_eff real ≈ 42.

Sin N_eff, los confidence tiers son demasiado optimistas para señales con clustering.
```

#### P3: Ausencia de validación OOS por década
```
El documento describe la generación de fact stores (prospección) y validación
contra quants_obs (historia), pero no menciona validación OOS por década.

Un estado con N=150 concentrado en 2010-2020 no es comparable a uno con
N=150 distribuido en 1993-2026. La estabilidad temporal importa.
```

#### P4: La Tabla de Fact Stores vs quants_obs es CORRECTA pero puede ser MALINTERPRETADA
```
"Fact Store → Sesgo: Ninguno (población completa)"
"quants_obs → Sesgo: Selección por pivote (infla WR)"

Esto es TÉCNICAMENTE correcto, pero:
- El fact store TIENE sesgo: solo cubre días donde el indicador tiene datos (FG no existe antes de 2011)
- quants_obs TIENE una ventaja: mide retornos REALES, no esperados
- La frase "infla WR" es imprecisa: infla el N, no necesariamente el WR
```

---

## VEREDICTO FINAL

| Documento | Veredicto | Acción |
|-----------|-----------|--------|
| `fact-store-mandatory-reference.md` | ✅ RESCATABLE | Gatekeeper necesario. Agregar versionado para detectar obsolescencia. |
| `fact_store_v3_architecture.md` | ✅ RESCATABLE (con reservas) | Documento fundacional sólido. Los 4 problemas (P1-P4) son omisiones, no errores. Se corrigen con addendum, no con reescritura. |

---

## ADDENDUM RECOMENDADO (4 correcciones)

### Addendum 1: Complementar Confidence Tiers con CI95

```markdown
## 13.1 Confidence Tiers with Bootstrap CI95

Los tiers por N absoluto son una heurística. La validación definitiva requiere:

| Tier | N | Bootstrap CI95 | Interpretación |
|------|---|----------------|----------------|
| CONFIABLE | ≥30 | CI95 no cruza cero | Señal validada |
| DIAMANTE | 3-29 | CI95 no cruza cero | Alta asimetría, interpretación requerida |
| DIRECCIONAL | ≥30 | CI95 cruza cero | Dirección correcta, magnitud incierta |
| RUIDO | cualquiera | CI95 ancho (>10pp) | No usar |
```

### Addendum 2: Agregar N_eff

```markdown
## 13.2 Effective Sample Size (N_eff)

Señales que disparan en clusters temporales (varios pivotes consecutivos
en la misma pierna) inflan el N bruto. Usar block bootstrap con ventana
de 30 días para calcular N_eff.

Si N_eff / N_bruto < 0.5 → inflación significativa → CI95 reportado con N_eff.
```

### Addendum 3: Agregar validación OOS por década

```markdown
## 13.3 Out-of-Sample Validation by Decade

Para estados con N ≥ 30, validar estabilidad temporal:
- Dividir en décadas: 1990s, 2000s, 2010s, 2020s
- Si WR cambia >20pp entre décadas → señal NO estacionaria
- Si WR es consistente (±10pp) → señal robusta
```

### Addendum 4: Clarificar sesgos de Fact Store vs quants_obs

```markdown
## 1.1 Sesgos de Cada Instrumento

| | Fact Store | quants_obs |
|---|---|---|
| Sesgo de cobertura | Solo días con datos del indicador (FG no existe <2011) | Solo pivotes ZigZag confirmados |
| Sesgo de selección | Ninguno (todos los días) | Selección por pivot_type (MAX/MIN) |
| Sesgo de medición | Retornos ESPERADOS (modelo) | Retornos REALES (historia) |
| Ventaja | Población completa, sin look-ahead | Ground truth, validación empírica |
```

---
**Firma:** deepseek/deepseek-v4-pro (Hermes)
**Fecha:** 20-Ago-2026