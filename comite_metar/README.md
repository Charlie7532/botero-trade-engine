# Comité METAR — Walk-Forward Forense Integral

Comité de **11 agentes LLM** (una por estación METAR, cada uno con personalidad de experto en su "mundo") + **curador**, que simulan operar **en vivo vela a vela** sobre el SPY. Validan/invalidan reglas, hacen forensia, analizan confluencias y señales escasas, confrontan modelos. **"La verdad habla."**

## Estructura

```
comite_metar/
├── perfiles/           # perfil de cada estación (mundo, rol, ancla, idioma, inception)
│   └── perfil_estaciones.json   ← REGISTRO MAESTRO de los 11 mundos
├── scripts/            # cómputo determinista (estado/first-passage/episodios)
├── agentes/            # los 11 agentes LLM (cada uno invoca con su perfil)
├── curador/            # fusión + confluencia + confrontación
├── salidas/            # los 8 JSON de salida
└── README.md
```

## Los 11 mundos (personalidad + rol + ancla de validación)

| Estación | Mundo | Rol | Ancla D | Dirección física |
|:---------|:------|:----|:--------|:----------------|
| VIX | Volatilidad implícita / miedo | Precursor | Anticipa pivote | ↑ = peor |
| VVIX | Vol de la volatilidad | Precursor | Anticipa pivote | ↑ = peor |
| PCR | Posicionamiento put/call | Precursor | Anticipa pivote | ↑ = peor |
| FG | Sentimiento extremo | Exageración fat-tail | Giros + eventos | ↑ = mejor (contrarian en extremo) |
| SV5_Turb | Turbulencia de mercado | Régimen de fondo | Cambio de régimen | ↑ = peor |
| SKEW | Riesgo de cola | Precursor eventos extremos | Anticipa eventos de cola | ↑ = peor |
| CREDIT | Apetito de riesgo | Contexto | Régimen / flujo | ↑ = MEJOR (bin 0 = estrés) |
| YIELD_CURVE | Espera de ciclo | Régimen de fondo | Recesión/expansión | ↑ = expansión (bin 0 = inversión) |
| ROTATION | Rotación sectorial | Régimen/contexto | Defensivo vs cíclico | ↑ = risk-on |
| DXY | Dólar / liquidez | Contexto | Dirección del flujo | ↑ = peor para equities |
| BSI | Amplitud | Confirmador | Continuación del movimiento | ↑ = mejor |

## Estándar canónico (obligatorio)

Cada agente usa las **3 dimensiones D1×D2×D3** conforme a `d1_labels_canonical.md`:
- **D1** (magnitud): labels canónicos por estación (6 bines, EXTREME_x a EXTREME_antónimo), copiados LITERALMENTE.
- **D2** (velocidad, universal): FAST_CRUSH_3D → FAST_SPIKE_3D (5 bines).
- **D3** (estabilidad, universal): VOL_EXTREME_SQUEEZE → VOL_PEAK_DECELERATION (5 bines).
- **Dirección física** por estación (CREDIT/YIELD tienen bin 0 = estrés/inversión, INVERTIDO).
- **Overflow** ±2σ en `{est}_overflow_tier_*` marca extremos de cola.

**Mapa de datos** por estación: 22 columnas uniformes (`*_val`, `*_d?_bin`, `*_d1/z`, `*_sk`, `*_overflow_tier_*`) + mercado (`spy_*`). El agente decodifica el state_key con sus labels y aplica su dirección física antes de interpretar la combinación D1×D2×D3.

## Walk-Forward

- Por **episodios/pivotes** (no cada vela): agentes LLM interpretan en los puntos de decisión; el cómputo de estado/first-passage es determinista entre puntos.
- **Sin lookahead:** en `t` ningún agente usa datos post-`t`.
- **Inception respetado:** cada agente madura cuando su estación tiene datos (VIX 1993, VVIX/PCR 2006, CREDIT 2007, FG 2011, SV5_Turb 1999, etc.).
- **Ancla D:** cada estación se valida contra lo que su rol responde.

## Salidas (8 JSON)

`registro_forense.json`, `reglas_validadas.json`, `reglas_invalidadas.json`, `señales_descubiertas.json`, `confluencias_canarias.json`, `señales_escasas_significado.json`, `modelo_confluencia.json`, + alertas.

## Marco normativo
- **Metrología:** first-passage OHLC intrabar, sin time-stop (Opción C).
- **De-clustering = credibilidad, nunca exclusión** (§3.3, rareza=riqueza).
- **Rareza se prueba contra el nulo**, no se declara.
- **Confluencia probabilística**, no determinista.
- **Dato mata relato.** **La verdad habla.**

## Ejecutar
(Fase 1: generar episodios → Fase 2: agentes LLM → Fase 3: curador fusiona/registra → Fase 4: modelador aprende OOS → Fase 5: entrega.)