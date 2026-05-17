"""
Signal Passport — Departmental Reliability Profile
====================================================
Enriched signal calibration record produced by department-specific Oracles.

Extends the existing engine.signal_profiles with:
  - Per-regime breakdown (NORMAL / ELEVATED / CRISIS)
  - Per-fear-level breakdown (GREED → PANIC) — Swing only
  - Per-sigma-band breakdown (-2/-1.5/-1.0) — Swing only
  - OOS (Walk-Forward) Sharpe and WR
  - Composite reliability_score for pre-entry scaling

Pre-Entry Gate usage:
    passport = store.load_passport(ticker, "QUALITY_SWING", "regression_channel")
    expected_wr = passport.wr_by_fear_level.get(fear_label, 50.0)
    conviction *= passport.reliability_score * (expected_wr / 100.0)
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalPassport:
    """Departmental reliability profile for a single signal × ticker."""

    # ── Identity ──────────────────────────────────────────────────
    ticker: str
    department: str          # "QUALITY_CORE" | "QUALITY_SWING"
    signal_name: str

    # ── Core performance (mirrors engine.signal_profiles) ─────────
    ceiling_sharpe: float = 0.0
    floor_sharpe: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    n_entries: int = 0
    avg_return_pct: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_bars_held: float = 0.0
    avg_bars_to_loss: float = 0.0
    pct_loss_hit: float = 0.0
    pct_time_hit: float = 0.0

    # ── Reliability scores ────────────────────────────────────────
    reliability_score: float = 0.0    # 0-1 composite (Sharpe + consistency + OOS)
    consistency_score: float = 0.0    # 1 - (std_ret / abs(avg_ret)), capped 0-1
    oos_sharpe: float = 0.0           # Walk-Forward OOS Sharpe
    oos_win_rate: float = 0.0         # Walk-Forward OOS win rate

    # ── Regime breakdown (both departments) ───────────────────────
    sharpe_by_vol_regime: dict = field(default_factory=dict)   # {NORMAL: x, ELEVATED: x, CRISIS: x}
    wr_by_vol_regime: dict = field(default_factory=dict)       # {NORMAL: %, ELEVATED: %, CRISIS: %}
    n_by_vol_regime: dict = field(default_factory=dict)        # {NORMAL: n, ELEVATED: n, CRISIS: n}

    # ── Swing-specific breakdowns (populated only for QUALITY_SWING) ──
    wr_by_fear_level: dict = field(default_factory=dict)       # {PANIC: %, FEAR: %, ..., GREED: %}
    n_by_fear_level: dict = field(default_factory=dict)        # Sample count per fear level
    wr_by_sigma_band: dict = field(default_factory=dict)       # {"-2_-1.5": %, "-1.5_-1": %, etc.}
    n_by_sigma_band: dict = field(default_factory=dict)
    wave_flip_wr: float = 0.0         # WR when wave_flip=True
    wave_flip_no_wr: float = 0.0      # WR when wave_flip=False
    wave_flip_edge: float = 0.0       # wave_flip_wr - wave_flip_no_wr
    tide_regime_wr: dict = field(default_factory=dict)         # {BULL: %, FLAT: %, BEAR: %}
    n_by_tide_regime: dict = field(default_factory=dict)

    # ── Core-specific breakdowns (populated only for QUALITY_CORE) ──
    drawdown_recovery_avg_bars: float = 0.0   # Bars to recover from max adverse
    thesis_survival_rate: float = 0.0         # % of entries where price recovered within max_bars

    # ── Gate integration ──────────────────────────────────────────
    viable: bool = False
    grade: str = "D"           # A/B/C/D
    geometry_used: dict = field(default_factory=dict)
    calibrated_at: Optional[str] = None

    def expected_wr_for(self, fear_label: str) -> float:
        """Return expected WR for a given fear level, fallback to overall WR."""
        return self.wr_by_fear_level.get(fear_label, self.win_rate)

    def expected_sharpe_for_regime(self, regime: str) -> float:
        """Return expected Sharpe for a given vol regime, fallback to ceiling."""
        return self.sharpe_by_vol_regime.get(regime, self.ceiling_sharpe)
