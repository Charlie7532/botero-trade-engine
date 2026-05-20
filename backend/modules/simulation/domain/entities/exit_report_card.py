from dataclasses import dataclass, field

@dataclass
class ExitReportCard:
    """Boletín de calificaciones para señales de SALIDA (-1)."""
    ticker: str
    signal_name: str
    n_signals: int

    # ── Distribución de clasificaciones ──
    classification_dist: dict[str, int] = field(default_factory=dict)    # {SAVED_US: 8, FALSE_ALARM: 3, ...}
    classification_pct: dict[str, float] = field(default_factory=dict)

    # ── Métricas de calidad de salida ──
    save_rate: float = 0.0             # % SAVED_US + GOOD_WARNING (las mejores)
    early_rate: float = 0.0            # % EARLY_BUT_RIGHT (correcta pero prematura)
    false_alarm_rate: float = 0.0      # % FALSE_ALARM (dijo sal, precio subió — lo peor)
    missed_upside_rate: float = 0.0    # % MISSED_UPSIDE (se perdió una subida grande)
    neutral_rate: float = 0.0          # % NEUTRAL_EXIT (irrelevante)
    
    # ── Análisis por horizonte ──
    avg_avoided_loss: dict[int, float] = field(default_factory=dict)       # {3: -0.8%, 10: -2.1%} pérdida evitada
    avg_missed_gain: dict[int, float] = field(default_factory=dict)        # {3: +0.5%, 10: +1.2%} ganancia perdida
    
    # ── Costo de las salidas malas ──
    cost_of_false_alarms: float = 0.0  # Retorno promedio perdido por FALSE_ALARM
    cost_of_missed_upside: float = 0.0 # Retorno promedio perdido por MISSED_UPSIDE
    net_exit_value: float = 0.0        # avg_avoided_loss - cost_of_misses (¿la salida neta ayudó?)
    
    # ── Diagnóstico de fallos ──
    foreseeable_pct: float = 0.0
    failure_breakdown: dict[str, int] = field(default_factory=dict)
    foreseeability_breakdown: dict[str, int] = field(default_factory=dict)
    top_lesson: str = "NONE"
    
    # ── Condicionamiento por régimen ──
    save_rate_by_fear: dict[str, float] = field(default_factory=dict)
    save_rate_by_vol_regime: dict[str, float] = field(default_factory=dict)
    false_alarm_rate_by_fear: dict[str, float] = field(default_factory=dict)
    
    grade: str = "D"
    verdict: str = "UNRATED"
