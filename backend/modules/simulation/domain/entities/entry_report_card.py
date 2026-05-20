from dataclasses import dataclass, field

@dataclass
class EntryReportCard:
    """Boletín de calificaciones para señales de ENTRADA (+1)."""
    ticker: str
    signal_name: str
    n_signals: int

    # ── Distribución de clasificaciones ──
    classification_dist: dict[str, int] = field(default_factory=dict)    # {GOLDEN_RUN: 12, TRAP: 5, ...}
    classification_pct: dict[str, float] = field(default_factory=dict)

    # ── Métricas de calidad de entrada ──
    golden_rate: float = 0.0           # % GOLDEN_RUN + SOLID_MOVE (las mejores)
    trap_rate: float = 0.0             # % TRAP (entró y luego cayó — lo más peligroso)
    false_rate: float = 0.0            # % FALSE_SIGNAL (nunca funcionó)
    miss_rate: float = 0.0             # % MISS (nada pasó)
    
    # ── Análisis por horizonte ──
    avg_return_by_horizon: dict[int, float] = field(default_factory=dict)   # {3: 0.4%, 5: 0.7%, ...}
    wr_by_horizon: dict[int, float] = field(default_factory=dict)           # {3: 62%, 5: 65%, ...}
    
    # ── Asimetría del edge ──
    edge_ratio_10: float = 0.0         # avg_MFE / |avg_MAE| at H=10
    avg_mfe_10: float = 0.0            # Cuánto subió en promedio (máximo favorable)
    avg_mae_10: float = 0.0            # Cuánto bajó en promedio (máximo adverso)
    
    # ── Diagnóstico de fallos ──
    foreseeable_pct: float = 0.0                     # % de fallos que eran previsibles
    failure_breakdown: dict[str, int] = field(default_factory=dict)          # {BEAR_REGIME_IGNORED: 8, ...}
    foreseeability_breakdown: dict[str, int] = field(default_factory=dict)   # {FORESEEABLE: 19, UNFORESEE: 6, ...}
    top_lesson: str = "NONE"                            # Diagnóstico más frecuente
    
    # ── Condicionamiento por régimen ──
    golden_rate_by_fear: dict[str, float] = field(default_factory=dict)      # {PANIC: 85%, GREED: 55%, ...}
    golden_rate_by_vol_regime: dict[str, float] = field(default_factory=dict)
    golden_rate_by_weinstein: dict[str, float] = field(default_factory=dict)
    
    grade: str = "D"             # A/B/C/D/F
    verdict: str = "UNRATED"     # ELITE / VIABLE / MARGINAL / REJECT
