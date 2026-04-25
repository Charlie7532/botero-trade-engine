from dataclasses import dataclass, field
from datetime import datetime, UTC

@dataclass
class WindowResult:
    """Resultado de una ventana individual de Walk-Forward."""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str

    # Métricas de la ventana de TEST
    n_trades: int = 0
    n_winners: int = 0
    n_losers: int = 0
    win_rate: float = 0.0

    total_pnl_pct: float = 0.0
    avg_pnl_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    calmar_ratio: float = 0.0       # Rendimiento anualizado / Max Drawdown

    # Distribución de errores (del TradeAutopsy)
    error_distribution: dict = field(default_factory=dict)
    avg_entry_efficiency: float = 0.0
    avg_edge_ratio: float = 0.0

    # Meta
    model_auc: float = 0.0         # AUC del modelo meta-labeler en esta ventana
    regime: str = ""                # Bull, Bear, Sideways (clasificación del período)

@dataclass
class BacktestReport:
    """Reporte consolidado del Walk-Forward completo."""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    total_windows: int = 0
    windows: list = field(default_factory=list)

    # Métricas agregadas (promedio de todas las ventanas)
    avg_sharpe: float = 0.0
    avg_win_rate: float = 0.0
    avg_profit_factor: float = 0.0
    worst_drawdown: float = 0.0
    total_return_pct: float = 0.0

@dataclass
class TradeAutopsyResult:
    """Resultado del análisis post-mortem de un trade."""
    trade_id: str
    ticker: str

    # ── MFE / MAE ────────────────────────────────────────────────
    mfe_pct: float = 0.0           # Max Favorable Excursion (%)
    mae_pct: float = 0.0           # Max Adverse Excursion (%)
    mfe_price: float = 0.0         # Precio en el punto MFE
    mae_price: float = 0.0         # Precio en el punto MAE
    bars_to_mfe: int = 0           # Barras desde entrada hasta MFE
    bars_to_mae: int = 0           # Barras desde entrada hasta MAE
    total_bars: int = 0            # Barras totales del trade

    # ── Métricas Derivadas ───────────────────────────────────────
    entry_efficiency: float = 0.0  # PnL / MFE (qué % del movimiento capturamos)
    stop_efficiency: float = 0.0   # MAE / initial_stop_distance
    edge_ratio: float = 0.0       # MFE / |MAE| (calidad del edge)
    normalized_edge_ratio: float = 0.0 # V7: Volatility-Normalized E-Ratio
    mc_p_value: float = 0.0       # V7: Monte Carlo Permutation p-value (Suerte vs Skill)
    mfe_timing: float = 0.0       # bars_to_mfe / total_bars (pico temprano vs tardío)

    # ── Diagnóstico ──────────────────────────────────────────────
    error_class: str = ""          # SIN_EDGE, ENTRADA_TARDIA, STOP_TIGHT, etc.
    diagnosis: str = ""            # Explicación en texto libre
    actionable_lesson: str = ""    # Qué ajustar para el próximo trade

    # ── Resultado ────────────────────────────────────────────────
    pnl_pct: float = 0.0
    was_winner: bool = False
    exit_reason: str = ""

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)

from backend.modules.execution.domain.entities.order_models import Trade

@dataclass
class BacktestResult:
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_cash: float
    final_value: float
    trades: list[Trade]
    metrics: dict = field(default_factory=dict)

    @property
    def total_return(self) -> float:
        return (self.final_value - self.initial_cash) / self.initial_cash
