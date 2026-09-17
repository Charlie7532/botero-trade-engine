═══ PROMPT: σ-Overflow — validación por software, D1×D2×D3 (definitivo) ═══

CONTEXTO: Las bandas σ calibradas cubren hasta ±2σ. Cuando el dato desborda
(VIX=82 = 10.7σ), todo se etiqueta igual y se pierde la distinción de
profundidad. El "over-correction" es proporcional a la profundidad.

DISEÑO (respeta uno-a-muchos vs uno-a-uno):
  - FACT STORE: NO se toca. Es uno-a-muchos (estado → estadística), no puede
    guardar valores por día.
  - SOFTWARE: un validador que corre sobre datos diarios (uno-a-uno), computa
    μ/σ de la historia del vault, y valida el overflow cuando el valor está
    en extremo. Para LAS TRES dimensiones D1, D2, D3.

═══════════════════════════════════════════════════════════════════
IMPLEMENTACIÓN
═══════════════════════════════════════════════════════════════════

PASO 1 — Crear módulo compartido sigma_overflow.py
  Ubicación: backend/modules/entry_decision/domain/rules/sigma_overflow.py

  Contenido:
    STATION_MU_SIGMA = {
      "vix":   {"d1": (19.44, 7.73), "d2": (0.0, 2.64), "d3": (0.54, 0.46)},
      "vvix":  {"d1": (93.47, 16.39), "d2": (0.0, ...), "d3": (...)},
      "pcr":   {...}, "fg": {...}, "skew": {...}, "bsi": {...},
      "sv5_turbulence": {...}, "credit": {...}, "yield_curve": {...},
      "dxy": {...}, "rotation": {...}
    }
    # μ/σ por estación × dimensión. Computarlos UNA VEZ desde la historia
    # del vault (market.ohlcv_bars), NO desde el fact store.
    # D1 = valor, D2 = diff(3d), D3 = std(2)/std(10).

    def validate_overflow(station, dim, value):
        mu, sigma = STATION_MU_SIGMA[station][dim]
        if sigma <= 0: return None, None
        if value > (mu + 3*sigma):
            return round((value-mu)/sigma, 2), "UPPER"
        elif value < (mu - 3*sigma):
            return round((value-mu)/sigma, 2), "LOWER"
        return None, None

  ⚠️ THRESHOLD ±3σ uniforme para D1, D2, D3.
     +2σ..+3σ = extremo normal (label basta). > +3σ = overflow real.

PASO 2 — Cada *StateGuidance: campos nuevos (sin tocar state_key)
  Agregar al dataclass:
    sigma_depth_d1: Optional[float] = None
    sigma_depth_d2: Optional[float] = None
    sigma_depth_d3: Optional[float] = None
    overflow_flag: Optional[str] = None  # "UPPER"|"LOWER"|"MULTI"|None

  En to_dict() agregar:
    "sigma_depth_d1": ..., "sigma_depth_d2": ..., "sigma_depth_d3": ...,
    "overflow_flag": ...

  El state_key (D1__D2__D3 labels) NO cambia.

PASO 3 — Cada *_metar_service.py (11): llamar validate_overflow
  Al clasificar el día (uno-a-uno), para LAS 3 dimensiones:
    d1_depth, f1 = validate_overflow(station, "d1", val)
    d2_depth, f2 = validate_overflow(station, "d2", vel)
    d3_depth, f3 = validate_overflow(station, "d3", vol_norm)

    flags = [f for f in (f1, f2, f3) if f]
    overflow_flag = "MULTI" if len(flags) >= 2 else (flags[0] if flags else None)

  Pasar los 4 campos al guidance.

PASO 4 — market_sigmet_hazard_service.py: evento de overflow
  "OVERFLOW_MULTI"    si overflow_flag == "MULTI" (2+ dimensiones > ±3σ) → cisne negro
  "OVERFLOW_EXTREMO"  si cualquier depth > 4σ
  "OVERFLOW_MODERADO" si 3σ < depth ≤ 4σ

PASO 5 — Test (test_sigma_overflow.py)
  - validate_overflow devuelve None para valor dentro de ±3σ (las 3 dims)
  - validate_overflow("vix","d1", 82.0) → depth≈8.1, flag="UPPER"
  - overflow_flag="MULTI" cuando 2+ dimensiones desbordan
  - state_key NO cambia; sigma_depth solo se llena en overflow

═══════════════════════════════════════════════════════════════════
PROHIBIDO
═══════════════════════════════════════════════════════════════════
- NO tocar fact stores NI v3_fact_table_engine.py (no regenerar nada)
- NO cambiar el state_key D1×D2×D3 (labels)
- NO usar ±2σ (es ±3σ)
- NO tocar cascade_conviction, cascade_calibration, convergence_compositor
- NO tocar Quality Swing (rc_tide_ev, scientific_fact_table)
- SOLO: sigma_overflow.py + 11 lookups/services guidance + sigmet + test

═══════════════════════════════════════════════════════════════════
VERIFICACIÓN
═══════════════════════════════════════════════════════════════════
1. pytest backend/tests/ (sin errores nuevos)
2. Fact stores INTACTOS (git status no muestra *_fact_store.json modificados)
3. VIX=82 → sigma_depth_d1≈8.1, overflow_flag="UPPER"
4. VIX=20 → depth=None (no overflow)
5. decay_check HEALTHY (cascade +0.41 sin cambios)