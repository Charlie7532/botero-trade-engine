"""
Swing EV Decision Engine — Pure Domain Module
===============================================
El Módulo Correcto: TODA decisión pasa por la cadena completa de Esperanza Matemática.

Cadena de decisión:
  1. Carga la tabla fact PER-TICKER desde Neon PostgreSQL (engine.ticker_fact_states).
  2. Busca E[R|S_t] empírico para el estado actual con fallback cascade (L2→L1→L0).
  3. Modifica Ω por el sesgo cinemático del VWAP (dσ_vw/dt).
  4. Consulta la Matriz de Transición Markoviana para proyectar S_{t+1}.
  5. Calcula el Kelly Sizer continuo f* = E[R] / σ² con Half-Kelly.
  6. Emite SwingDecision con acción continua ponderada + sizing + razonamiento.

Data source: engine.ticker_fact_states + engine.ticker_fact_baselines (Neon PostgreSQL).
Loaded lazily on first access per ticker, cached in memory for the session.

Fixes applied over Gemini 3.6's implementation:
  - Falla 1: svw_drift now modifies Ω (kinematic bias multiplier)
  - Falla 4: p_cielo uses >= 0 in generator (already fixed in DB)
  - Falla 5: Half-Kelly + percentile-relative clamping (no longer always ±0.25)
"""
import logging
import math
from dataclasses import dataclass
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_TICKER_TABLES: Dict[str, dict] = {}
_CALIBRATION_CUTOFF: str = "9999-12-31"
_DB_CONN = None


# ─────────────────────────── Configuration ───────────────────────────

def configure(calibration_cutoff: str = "9999-12-31", conn=None):
    """Configure the engine before first use.

    Args:
        calibration_cutoff: "9999-12-31" for full history (production),
                            "2019-12-31" for in-sample (OOS testing).
        conn: Database connection. If None, creates one lazily.
    """
    global _CALIBRATION_CUTOFF, _DB_CONN
    _CALIBRATION_CUTOFF = calibration_cutoff
    _DB_CONN = conn
    _TICKER_TABLES.clear()
    _TICKER_KELLY_SCALES.clear()


def _get_conn():
    """Get or create a database connection."""
    global _DB_CONN
    if _DB_CONN is None:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        store = TimescaleDataStore()
        _DB_CONN = store._conn()
    return _DB_CONN


# ─────────────────────────── Data Classes ───────────────────────────

@dataclass(frozen=True)
class EVLookupResult:
    """Raw E[R|S_t] lookup from per-ticker fact table."""
    state_key: str
    fallback_level: str  # "L2", "L1", "L0"
    n_samples: int
    p_cielo: float
    p_infierno: float
    ev_net: float
    variance: float
    omega: float  # certitude index = 1/σ²
    sharpe: float
    rr_asymmetry: float
    kelly_f: float
    l0_ev: float = 0.0  # Ticker baseline E[R] for relative expectation calculation


@dataclass(frozen=True)
class TransitionProjection:
    """Markov transition projection S_{t+1}."""
    current_state: str
    most_likely_next: str
    next_probability: float
    next_implies_reversal: bool


@dataclass(frozen=True)
class SwingDecision:
    """Final output of the full E[R|S_t] chain."""
    ticker: str
    timestamp: str
    action: str  # "HARVEST", "ACCUMULATE", "HOLD", "OBSERVE", "EXIT_CRISIS"
    sizing_fraction: float  # Half-Kelly f*/2, clamped to operational range
    ev_net: float
    omega: float  # Ω after drift modification
    kelly_raw: float
    state_key: str
    fallback_level: str
    n_samples: int
    transition_next: str
    transition_prob: float
    reasoning: str


# ─────────────────────────── Fact Table Loader (from DB) ───────────────────────────

def _load_ticker_table(ticker: str) -> Optional[dict]:
    """Load per-ticker fact table lazily from engine.ticker_fact_states."""
    ticker_upper = ticker.upper()
    if ticker_upper in _TICKER_TABLES:
        return _TICKER_TABLES[ticker_upper]

    try:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute(
            """SELECT state_key, n, p_cielo, p_infierno, e_ret_cielo, e_ret_infierno,
                      ev_net, variance, std_dev, sharpe, omega, rr_asymmetry, kelly_f
               FROM engine.ticker_fact_states
               WHERE ticker = %s AND calibration_cutoff = %s AND lookforward_days = 20""",
            (ticker_upper, _CALIBRATION_CUTOFF),
        )
        rows = cur.fetchall()

        if not rows:
            logger.warning(f"No fact states for {ticker_upper} (cutoff={_CALIBRATION_CUTOFF})")
            return None

        fact_entries = {}
        for row in rows:
            fact_entries[row[0]] = {
                "n": row[1], "p_cielo": row[2], "p_infierno": row[3],
                "e_ret_cielo": row[4], "e_ret_infierno": row[5],
                "ev_net": row[6], "variance": row[7], "std_dev": row[8],
                "sharpe": row[9], "omega": row[10], "rr_asymmetry": row[11],
                "kelly_f": row[12],
            }

        cur.execute(
            """SELECT n, ev_net, variance, p_cielo
               FROM engine.ticker_fact_baselines
               WHERE ticker = %s AND calibration_cutoff = %s AND lookforward_days = 20""",
            (ticker_upper, _CALIBRATION_CUTOFF),
        )
        baseline_row = cur.fetchone()
        l0 = {
            "n": baseline_row[0], "ev_net": baseline_row[1],
            "variance": baseline_row[2], "p_cielo": baseline_row[3],
        } if baseline_row else {"n": 0, "ev_net": 0.0, "variance": 0.01, "p_cielo": 0.50}

        data = {"fact_entries": fact_entries, "l0_global": l0}
        _TICKER_TABLES[ticker_upper] = data
        return data

    except Exception as e:
        logger.error(f"Error loading fact table for {ticker_upper}: {e}")
        return None


# ─────────────────────────── VIX Regime (Gate only, NOT state dimension) ───────────────────────────

def _classify_vix(vix: float) -> str:
    """Classify VIX into discrete regime for Circuit Breaker gate.

    Empirically validated (A/B experiment 2026-07-27): VIX as a state dimension
    DEGRADES performance (+0.08% vs +0.50% 3D-only, t=0.18 vs 1.64).
    VIX crosses thresholds 238 times in OOS (14.5% of bars) — too noisy.
    VIX remains as Circuit Breaker gate only.
    """
    if vix < 18.0:
        return "V_LOW"
    elif vix < 25.0:
        return "V_NORM"
    elif vix < 35.0:
        return "V_ELEV"
    else:
        return "V_CRISIS"


# ─────────────────────────── State Classification (3D: T|C|VWAP) ───────────────────────────

def _classify_state(t_slope: float, c_slope: float, svw_filtered: float) -> tuple:
    """Classify continuous values into discrete 3D state bins."""
    t_bin = "T+" if t_slope >= 0.05 else ("T-" if t_slope <= -0.05 else "T0")
    c_bin = "C+" if c_slope >= 0.05 else ("C-" if c_slope <= -0.05 else "C0")

    if svw_filtered < -1.50:
        vw_bin = "<<"
    elif svw_filtered < -0.50:
        vw_bin = "<"
    elif svw_filtered <= 0.50:
        vw_bin = "~"
    elif svw_filtered <= 1.50:
        vw_bin = ">"
    else:
        vw_bin = ">>"

    state_key = f"{t_bin}|{c_bin}|{vw_bin}"
    return t_bin, c_bin, vw_bin, state_key


# ─────────────────────────── E[R|S_t] Lookup: L2(3D)→L1(2D)→L0 ───────────────────────────

def _ev_from_entry(e: dict, state_key: str, level: str, l0_ev: float = 0.0) -> EVLookupResult:
    """Build EVLookupResult from a fact entry dict."""
    return EVLookupResult(
        state_key=state_key, fallback_level=level, n_samples=e["n"],
        p_cielo=e["p_cielo"], p_infierno=e["p_infierno"],
        ev_net=e["ev_net"], variance=e["variance"], omega=e["omega"],
        sharpe=e["sharpe"], rr_asymmetry=e["rr_asymmetry"], kelly_f=e["kelly_f"],
        l0_ev=l0_ev
    )


def lookup_ev(ticker: str, t_slope: float, c_slope: float,
             svw_filtered: float) -> EVLookupResult:
    """Look up E[R|S_t] with L2(3D)→L1(2D)→L0 fallback cascade.

    Cascade:
      L2: Exact 3D match  T+|C+|>>     (max precision)
      L1: T|C with VWAP~  T+|C+|~      (directional only)
      L0: Global baseline               (unconditional ticker mean)
    """
    table = _load_ticker_table(ticker)
    t_bin, c_bin, vw_bin, state_key = _classify_state(t_slope, c_slope, svw_filtered)

    if table is None:
        return EVLookupResult(
            state_key=state_key, fallback_level="NONE", n_samples=0,
            p_cielo=0.50, p_infierno=0.50, ev_net=0.0, variance=0.01,
            omega=100.0, sharpe=0.0, rr_asymmetry=1.0, kelly_f=0.0
        )

    entries = table.get("fact_entries", {})
    l0 = table.get("l0_global", {})
    l0_ev = float(l0.get("ev_net", 0.0))

    # L2: exact 3D match
    if state_key in entries:
        return _ev_from_entry(entries[state_key], state_key, "L2", l0_ev=l0_ev)

    # L1: Tide|Current with neutral VWAP
    l1_key = f"{t_bin}|{c_bin}|~"
    if l1_key in entries:
        return _ev_from_entry(entries[l1_key], l1_key, "L1", l0_ev=l0_ev)

    # L0: global ticker baseline
    return EVLookupResult(
        state_key="L0_GLOBAL", fallback_level="L0", n_samples=l0.get("n", 0),
        p_cielo=l0.get("p_cielo", 0.50), p_infierno=1.0 - l0.get("p_cielo", 0.50),
        ev_net=l0_ev, variance=l0.get("variance", 0.01),
        omega=1.0 / (l0.get("variance", 0.01) + 1e-8),
        sharpe=0.0, rr_asymmetry=1.0, kelly_f=0.0, l0_ev=l0_ev
    )


# ─────────────────────────── VWAP Drift Modifier (Smooth Continuous) ───────────────────────────

def _apply_drift_modifier(omega: float, ev_net: float, svw_drift: float) -> float:
    """Apply VWAP kinematic drift as a Bayesian modifier on Ω (certitude).

    Principle: If drift CONFIRMS the E[R] direction, Ω increases (higher certainty).
    If drift CONTRADICTS the E[R] direction, Ω decreases (lower certainty → OBSERVE).

    Uses tanh(ev_net * 200) instead of copysign to produce a SMOOTH continuous
    transition around E[R]=0. When |E[R]| > 0.005, tanh saturates to ±1 (same
    behavior as copysign). When E[R] ≈ 0, agreement smoothly approaches 0.

    Args:
        omega: Base certitude index (1/σ²)
        ev_net: Expected return from fact table
        svw_drift: dσ_vw/dt — rate of change of the VWAP sigma wave
    """
    if abs(svw_drift) < 0.01:
        return omega  # Drift is negligible, no modification

    # Smooth continuous agreement: tanh saturates at ±1 for |ev_net| > ~0.005
    # At ev_net=0: agreement=0 (no modification). No discontinuity.
    ev_direction = math.tanh(ev_net * 200.0)  # saturates at ±1 around |ev|>0.005
    drift_direction = math.copysign(1.0, svw_drift)
    agreement = ev_direction * drift_direction

    # Sigmoid modifier: maps agreement * |drift| to [0.5, 1.5]
    drift_magnitude = min(abs(svw_drift), 0.30)  # cap at 0.30
    raw_modifier = agreement * drift_magnitude * 3.0
    modifier = 1.0 / (1.0 + math.exp(-raw_modifier))  # sigmoid → [0, 1]
    modifier = 0.5 + modifier  # shift → [0.5, 1.5]

    return omega * modifier


# ─────────────────────────── Transition Matrix ───────────────────────────

def project_next_state(
    current_state: str,
    transition_matrix: Optional[Dict[str, Dict[str, float]]] = None
) -> TransitionProjection:
    """Project S_{t+1} from Markov transition matrix. If no matrix, return neutral."""
    if transition_matrix is None or current_state not in transition_matrix:
        return TransitionProjection(
            current_state=current_state,
            most_likely_next=current_state,
            next_probability=0.50,
            next_implies_reversal=False
        )

    row = transition_matrix[current_state]
    most_likely = max(row, key=row.get)
    prob = row[most_likely]

    # Detect reversal: does next state flip Tide or Current sign?
    curr_parts = current_state.split("|")
    next_parts = most_likely.split("|")
    reversal = False
    if len(curr_parts) >= 2 and len(next_parts) >= 2:
        tide_flip = (curr_parts[0] == "T+" and next_parts[0] == "T-") or \
                    (curr_parts[0] == "T-" and next_parts[0] == "T+")
        curr_flip = (curr_parts[1] == "C+" and next_parts[1] == "C-") or \
                    (curr_parts[1] == "C-" and next_parts[1] == "C+")
        reversal = tide_flip or curr_flip

    return TransitionProjection(
        current_state=current_state,
        most_likely_next=most_likely,
        next_probability=prob,
        next_implies_reversal=reversal
    )


# ─────────────────────────── Kelly Sizer (Per-Ticker L0-Relative Half-Kelly) ─────

# Kelly scale is computed per-ticker from its L0 baseline variance.
# This eliminates the global _KELLY_SCALE = 0.0736 constant that caused:
#   1. Data leakage (derived from 1981-2026 full dataset)
#   2. Distortion across assets with different volatility regimes
# Instead, each ticker's raw Half-Kelly is normalized by its own L0 magnitude.
_TICKER_KELLY_SCALES: Dict[str, float] = {}  # cached per-ticker

_FALLBACK_KELLY_SCALE = 0.0736  # only used if L0 baseline unavailable


def _get_ticker_kelly_scale(ticker: str) -> float:
    """Compute per-ticker Kelly scale from L0 baseline variance.

    The scale maps so that the L0 baseline Half-Kelly maps to ~0.10 (operational midpoint).
    f*_L0 = E[R]_L0 / σ²_L0 / 2.  Scale = 0.10 / |f*_L0|.
    This ensures each ticker's own risk profile determines its sizing range.
    """
    ticker_upper = ticker.upper()
    if ticker_upper in _TICKER_KELLY_SCALES:
        return _TICKER_KELLY_SCALES[ticker_upper]

    table = _load_ticker_table(ticker_upper)
    if table is None:
        return _FALLBACK_KELLY_SCALE

    l0 = table.get("l0_global", {})
    l0_ev = l0.get("ev_net", 0.0)
    l0_var = l0.get("variance", 0.01)

    if l0_var < 1e-8 or abs(l0_ev) < 1e-8:
        _TICKER_KELLY_SCALES[ticker_upper] = _FALLBACK_KELLY_SCALE
        return _FALLBACK_KELLY_SCALE

    # L0 Half-Kelly magnitude
    l0_half_kelly = abs(l0_ev / l0_var / 2.0)
    # Scale so L0 maps to 0.10 (midpoint of [0, 0.25] operational range)
    scale = 0.10 / l0_half_kelly if l0_half_kelly > 0.01 else _FALLBACK_KELLY_SCALE
    # Clamp scale to reasonable range [0.01, 0.50] to avoid degenerate tickers
    scale = max(min(scale, 0.50), 0.01)

    _TICKER_KELLY_SCALES[ticker_upper] = scale
    return scale


def kelly_size(ev_net: float, variance: float, omega: float,
               min_omega: float = 20.0, ticker: str = "") -> float:
    """Per-Ticker L0-Relative Half-Kelly.

    f* = (E[R] / σ² / 2) × ticker_scale × certainty_scale

    ticker_scale is calibrated from the ticker's own L0 baseline so that
    the L0 Half-Kelly maps to 0.10 (operational midpoint).
    States with stronger signal than L0 get f* > 0.10; weaker get f* < 0.10.

    This replaces the global _KELLY_SCALE constant, eliminating:
      - Cross-ticker volatility distortion (AMZN vs PG/JNJ)
      - Data leakage from full-history P85 calibration
    """
    if variance < 1e-8:
        return 0.0

    # Half-Kelly
    raw_f = (ev_net / variance) / 2.0

    # Per-ticker scale
    scale = _get_ticker_kelly_scale(ticker) if ticker else _FALLBACK_KELLY_SCALE
    scaled_f = raw_f * scale

    # Certainty modulation
    certainty_scale = min(omega / min_omega, 1.0) if min_omega > 0 else 1.0
    scaled_f *= certainty_scale

    # Clamp to operational range
    return max(min(scaled_f, 0.25), -0.25)


# ─────────────────────────── Main Decision Engine ───────────────────────────

def decide(
    ticker: str,
    timestamp: str,
    t_slope: float,
    c_slope: float,
    svw_filtered: float,
    svw_drift: float = 0.0,
    vix: float = 20.0,
    transition_matrix: Optional[Dict[str, Dict[str, float]]] = None,
) -> SwingDecision:
    """
    The correct module: EVERY decision passes through the full E[R|S_t] chain.

    Chain:
      1. Lookup E[R|S_t] from per-ticker fact table (DB)
      2. Modify Ω by svw_drift (kinematic bias — Falla 1 fix)
      3. Project S_{t+1} from transition matrix
      4. Compute Half-Kelly sizing f*/2 (Falla 5 fix)
      5. Emit action based on E[R], modified Ω, S_{t+1}, and VIX
    """

    # ── Step 1: E[R|S_t] Lookup (3D state) ──
    ev = lookup_ev(ticker, t_slope, c_slope, svw_filtered)

    # ── Step 2: Drift Modifier on Ω ──
    omega_modified = _apply_drift_modifier(ev.omega, ev.ev_net, svw_drift)

    # ── Step 3: Transition Projection ──
    _, _, _, state_key = _classify_state(t_slope, c_slope, svw_filtered)
    proj = project_next_state(state_key, transition_matrix)

    # ── Step 4: Per-Ticker Half-Kelly Sizing ──
    f_star = kelly_size(ev.ev_net, ev.variance, omega_modified, ticker=ticker)

    # ── Step 5: Decision Logic (Relative E[R] + Markov Decay Refined) ──
    ev_rel = ev.ev_net - ev.l0_ev

    # 5a. Crisis Circuit Breaker (overrides everything)
    # Uses real VIX — caller MUST pass actual VIX from Vault (Falla 3 fix)
    if vix >= 28.0 and t_slope < -0.05:
        action = "EXIT_CRISIS"
        sizing = 0.25
        reasoning = (
            f"MACRO CIRCUIT BREAKER: VIX={vix:.1f} + T={t_slope:.3f} | "
            f"E[R|{ev.state_key}]={ev.ev_net*100:+.2f}%"
        )

    # 5b. E[R] significantly negative (absolute OR relative vs ticker baseline) → HARVEST
    # RULE: Do NOT harvest in strong bull marea (t_slope >= 0.05) unless VWAP is at extreme overbought (>= 1.50)
    elif (t_slope < 0.05 or svw_filtered >= 1.50) and (ev.ev_net < -0.005 or (ev_rel < -0.008 and c_slope < 0.0)) and omega_modified >= 25.0 and ev.n_samples >= 15:
        action = "HARVEST"
        sizing = min(abs(f_star), 0.25)
        reasoning = (
            f"HARVEST: E[R|{ev.state_key}]={ev.ev_net*100:+.2f}% (rel={ev_rel*100:+.2f}%) | "
            f"Ω={omega_modified:.0f} | n={ev.n_samples} | f*={f_star:+.4f}"
        )

    # 5c. S_{t+1} projects reversal OR expectation degradation → PREVENTIVE HARVEST
    # RULE: Conditioned on non-bull marea or overbought VWAP
    elif (t_slope < 0.05 or svw_filtered >= 1.20) and proj.next_probability >= 0.50 and (proj.next_implies_reversal or (ev_rel < -0.005 and c_slope < -0.02)) and ev.ev_net < 0.01:
        action = "HARVEST"
        sizing = min(abs(f_star), 0.15)
        reasoning = (
            f"PREVENTIVE HARVEST: S→{proj.most_likely_next} P={proj.next_probability:.2f} | "
            f"E[R]={ev.ev_net*100:+.2f}% (rel={ev_rel*100:+.2f}%) | Ω={omega_modified:.0f}"
        )

    # 5d. E[R] significantly positive (absolute OR relative) → ACCUMULATE
    elif (ev.ev_net > 0.005 or ev_rel > 0.005) and omega_modified >= 25.0 and ev.n_samples >= 15:
        action = "ACCUMULATE"
        sizing = min(max(f_star, 0.0), 0.25)
        reasoning = (
            f"ACCUMULATE: E[R|{ev.state_key}]={ev.ev_net*100:+.2f}% (rel={ev_rel*100:+.2f}%) | "
            f"Ω={omega_modified:.0f} | n={ev.n_samples} | f*={f_star:+.4f}"
        )

    # 5e. Low certainty → OBSERVE
    elif omega_modified < 20.0 or ev.n_samples < 15:
        action = "OBSERVE"
        sizing = 0.0
        reasoning = (
            f"INCERTIDUMBRE: Ω={omega_modified:.0f} (base={ev.omega:.0f}) | "
            f"n={ev.n_samples} | drift={svw_drift:+.3f}"
        )

    # 5f. Default: HOLD
    else:
        action = "HOLD"
        sizing = 0.0
        reasoning = (
            f"E[R|{ev.state_key}]={ev.ev_net*100:+.2f}% NEUTRAL | "
            f"Ω={omega_modified:.0f} | n={ev.n_samples}"
        )

    return SwingDecision(
        ticker=ticker,
        timestamp=timestamp,
        action=action,
        sizing_fraction=round(sizing, 4),
        ev_net=ev.ev_net,
        omega=round(omega_modified, 2),
        kelly_raw=round(f_star, 4),
        state_key=ev.state_key,
        fallback_level=ev.fallback_level,
        n_samples=ev.n_samples,
        transition_next=proj.most_likely_next,
        transition_prob=round(proj.next_probability, 3),
        reasoning=reasoning,
    )
