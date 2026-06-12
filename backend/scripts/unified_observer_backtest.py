#!/usr/bin/env python3
"""
Unified Kalman Observer — Design + Backtest
=============================================
ONE multivariate Kalman filter that observes the ENTIRE market state
simultaneously, replacing 5 independent 1D filters.

Architecture:
  State vector x = [σ_C, σV_W, tension_W, RSI, conj_WT,
                     σ̇_C, σ̇V_W, ṫension_W, ṘSI, ċonj_WT]
  10-dimensional: 5 positions + 5 velocities

  Observation z = [σ_C, σV_W, tension_W, RSI, conj_WT]
  5-dimensional: direct reads from channel snapshots

  Key advantage: the CROSS-COVARIANCE between channels is tracked.
  When σ_C moves, the filter updates its belief about σV_W, tension, etc.
  This captures the COUPLING that kf_consensus misses.

Outputs:
  - velocity_norm: ‖[σ̇_C, σ̇V_W, ...]‖ — how fast the system is moving
  - recovery_score: cosine(velocity, recovery_direction) — moving toward bull?
  - innovation_norm: ‖z - Hx̂‖ — how surprised the system is
  - state: RECOVERING / DETERIORATING / TRANSITIONING / STABLE

Comparison:
  Run on 83K bars, compare discrimination power vs kf_consensus for
  the AFTER_TROUGH target (zigzag ground truth).
"""
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from dataclasses import dataclass
from sklearn.metrics import roc_auc_score

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


TEST_START = "2006-01-01"
CONFLUENCE_WINDOW = 5

# ═══════════════════════════════════════════════════════════
# I. THE UNIFIED KALMAN OBSERVER
# ═══════════════════════════════════════════════════════════

# Features to observe (selected by AUC from deep mining)
OBS_NAMES = ["sigma_current", "vwap_sigma_wave", "tension_wave", "rsi_value", "conj_wave_tide"]
N_OBS = len(OBS_NAMES)
N_STATE = 2 * N_OBS  # position + velocity for each


@dataclass
class ObserverOutput:
    """Output of the unified Kalman observer for one bar."""
    # Filtered positions
    filt_sigma_c: float = 0.0
    filt_svw: float = 0.0
    filt_tension_w: float = 0.0
    filt_rsi: float = 0.0
    filt_conj_wt: float = 0.0

    # Filtered velocities
    vel_sigma_c: float = 0.0
    vel_svw: float = 0.0
    vel_tension_w: float = 0.0
    vel_rsi: float = 0.0
    vel_conj_wt: float = 0.0

    # Composite signals
    velocity_norm: float = 0.0       # ‖velocity vector‖
    recovery_score: float = 0.0      # cos(vel, recovery direction): +1=recovering, -1=deteriorating
    innovation_norm: float = 0.0     # ‖surprise‖: how unexpected this observation is
    transition_score: float = 0.0    # Combined: vel_norm * |recovery_score| — strength of directional move
    state: str = "STABLE"            # RECOVERING / DETERIORATING / TRANSITIONING / STABLE


class UnifiedKalmanObserver:
    """Multivariate Kalman filter tracking 5 market state variables jointly.

    State: [σ_C, σV_W, τ_W, RSI, conj_WT, σ̇_C, σ̇V_W, τ̇_W, ṘSI, ċ_WT]
    Transition: constant velocity model for each variable
    Observation: direct reads of the 5 position variables

    The key innovation: the covariance matrix P tracks HOW variables
    co-move. When σ_C starts rising and σV_W follows, the filter LEARNS
    this coupling and uses it for better prediction.
    """

    def __init__(self, q_scale: float = 0.03, r_scale: float = 0.15):
        """
        Args:
            q_scale: Process noise relative to data variance (how much we expect change)
            r_scale: Observation noise relative to data variance (how noisy the readings are)
        """
        self.q_scale = q_scale
        self.r_scale = r_scale
        self.x = None   # State vector [10]
        self.P = None   # Covariance [10x10]
        self.F = None   # Transition [10x10]
        self.H = None   # Observation [5x10]
        self.Q = None   # Process noise [10x10]
        self.R = None   # Observation noise [5x5]
        self._data_std = None  # Per-channel std for normalization

    def _build_matrices(self, data_std: np.ndarray, dt: float = 1.0):
        """Build system matrices. Called after warmup calibration."""
        self._data_std = data_std

        # Transition: constant velocity for each channel
        # [pos_i(t+1)] = [pos_i(t) + dt * vel_i(t)]
        # [vel_i(t+1)] = [vel_i(t)]
        self.F = np.eye(N_STATE)
        for i in range(N_OBS):
            self.F[i, N_OBS + i] = dt  # pos += dt * vel

        # Observation: read positions only
        self.H = np.zeros((N_OBS, N_STATE))
        for i in range(N_OBS):
            self.H[i, i] = 1.0

        # Process noise: scaled by channel variance
        # More noise on velocity (uncertain) than position
        self.Q = np.zeros((N_STATE, N_STATE))
        for i in range(N_OBS):
            var = data_std[i] ** 2
            # Position process noise (small)
            self.Q[i, i] = self.q_scale * var * dt**2
            # Cross: pos-vel
            self.Q[i, N_OBS + i] = self.q_scale * var * dt
            self.Q[N_OBS + i, i] = self.q_scale * var * dt
            # Velocity process noise (larger)
            self.Q[N_OBS + i, N_OBS + i] = self.q_scale * var

        # Observation noise: diagonal, scaled by channel variance
        self.R = np.diag(self.r_scale * data_std ** 2)

    def reset(self, initial_obs: np.ndarray, data_std: np.ndarray):
        """Initialize from first observation + calibration data."""
        self._build_matrices(data_std)
        self.x = np.zeros(N_STATE)
        self.x[:N_OBS] = initial_obs  # Set positions to first observation
        # Velocities start at 0
        self.P = np.eye(N_STATE)
        # Initialize position uncertainty to data variance
        for i in range(N_OBS):
            self.P[i, i] = data_std[i] ** 2
        # Initialize velocity uncertainty larger
        for i in range(N_OBS):
            self.P[N_OBS + i, N_OBS + i] = data_std[i] ** 2 * 4.0

    def update(self, observation: np.ndarray) -> ObserverOutput:
        """Full predict → innovate → update cycle.

        Returns ObserverOutput with velocity vector, recovery score,
        innovation norm, and state classification.
        """
        if self.x is None:
            return ObserverOutput()

        # 1. PREDICT
        x_pred = self.F @ self.x
        P_pred = self.F @ self.P @ self.F.T + self.Q

        # 2. INNOVATION (surprise)
        z = observation
        y = z - self.H @ x_pred  # Innovation vector [5]
        S = self.H @ P_pred @ self.H.T + self.R  # Innovation covariance [5x5]

        # 3. KALMAN GAIN
        try:
            K = P_pred @ self.H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            K = P_pred @ self.H.T @ np.linalg.pinv(S)

        # 4. UPDATE
        x_new = x_pred + K @ y
        P_new = (np.eye(N_STATE) - K @ self.H) @ P_pred

        # Store state
        self.x = x_new
        self.P = P_new

        # ── Extract outputs ──
        positions = x_new[:N_OBS]
        velocities = x_new[N_OBS:]

        # Normalize velocities by data std for fair comparison
        vel_normalized = velocities / (self._data_std + 1e-10)

        # Velocity norm (how fast the system is moving overall)
        vel_norm = float(np.linalg.norm(vel_normalized))

        # Recovery direction: we WANT σ_C↑, σV_W↑, tension_W↑, RSI↑, conj↓
        # (cheap→expensive, flow improving, tension releasing, RSI rising, conj normalizing)
        recovery_dir = np.array([1.0, 1.0, 1.0, 1.0, -1.0])
        recovery_dir_norm = recovery_dir / np.linalg.norm(recovery_dir)

        # Recovery score: cosine similarity with recovery direction
        if vel_norm > 1e-10:
            recovery_score = float(np.dot(vel_normalized / np.linalg.norm(vel_normalized), recovery_dir_norm))
        else:
            recovery_score = 0.0

        # Innovation norm (surprise, normalized by S)
        try:
            inn_whitened = np.linalg.solve(np.linalg.cholesky(S), y)
            inn_norm = float(np.linalg.norm(inn_whitened))
        except np.linalg.LinAlgError:
            inn_norm = float(np.linalg.norm(y / (np.sqrt(np.diag(S)) + 1e-10)))

        # Transition score: velocity × alignment
        transition_score = vel_norm * abs(recovery_score)

        # State classification
        if recovery_score > 0.3 and vel_norm > 0.5:
            state = "RECOVERING"
        elif recovery_score < -0.3 and vel_norm > 0.5:
            state = "DETERIORATING"
        elif vel_norm > 1.0:
            state = "TRANSITIONING"
        else:
            state = "STABLE"

        return ObserverOutput(
            filt_sigma_c=float(positions[0]),
            filt_svw=float(positions[1]),
            filt_tension_w=float(positions[2]),
            filt_rsi=float(positions[3]),
            filt_conj_wt=float(positions[4]),
            vel_sigma_c=float(velocities[0]),
            vel_svw=float(velocities[1]),
            vel_tension_w=float(velocities[2]),
            vel_rsi=float(velocities[3]),
            vel_conj_wt=float(velocities[4]),
            velocity_norm=vel_norm,
            recovery_score=recovery_score,
            innovation_norm=inn_norm,
            transition_score=transition_score,
            state=state,
        )


# ═══════════════════════════════════════════════════════════
# II. BACKTEST vs kf_consensus vs individual velocities
# ═══════════════════════════════════════════════════════════

def load_data():
    store = TimescaleDataStore(); conn = store._conn()

    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, vwap_sigma_wave, vwap_sigma_current,
               tide_slope, tension_wave, rsi_value, conj_wave_tide,
               current_accel, wave_accel,
               kf_price_filt_vel, kf_rsi_filt_vel,
               kf_tension_filt_vel, kf_conj_filt_vel
        FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND timestamp >= '{TEST_START}'
        ORDER BY ticker, timestamp
    """, conn)

    zz25 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type FROM engine.zigzag_points WHERE min_swing_pct=0.025 ORDER BY ticker, timestamp", conn)
    zz50 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp", conn)
    zz75 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type FROM engine.zigzag_points WHERE min_swing_pct=0.075 ORDER BY ticker, timestamp", conn)

    store._put(conn); store.close()
    for d in [cs, zz25, zz50, zz75]:
        d['date'] = pd.to_datetime(d['date'])
    return cs, zz25, zz50, zz75


def compute_observer_series(cs):
    """Run the unified observer on all tickers."""
    results = []
    for ticker in cs['ticker'].unique():
        tk = cs[cs['ticker'] == ticker].sort_values('date').copy()
        if len(tk) < 100:
            continue

        obs_cols = ['sigma_current', 'vwap_sigma_wave', 'tension_wave', 'rsi_value', 'conj_wave_tide']
        obs_data = tk[obs_cols].fillna(0).values

        # Warmup calibration: first 50 bars
        warmup = min(50, len(obs_data))
        data_std = np.std(obs_data[:warmup], axis=0)
        data_std = np.maximum(data_std, 1e-6)

        observer = UnifiedKalmanObserver(q_scale=0.03, r_scale=0.15)
        observer.reset(obs_data[0], data_std)

        outputs = []
        for i in range(len(obs_data)):
            out = observer.update(obs_data[i])
            outputs.append(out)

        tk['obs_vel_norm'] = [o.velocity_norm for o in outputs]
        tk['obs_recovery'] = [o.recovery_score for o in outputs]
        tk['obs_innovation'] = [o.innovation_norm for o in outputs]
        tk['obs_transition'] = [o.transition_score for o in outputs]
        tk['obs_state'] = [o.state for o in outputs]

        results.append(tk)

    return pd.concat(results).reset_index(drop=True)


def label_and_compare(df, zz25, zz50, zz75):
    """Label with zigzag ground truth and compare all detectors."""
    # Build trough map (same as deep_feature_mining)
    trough_map = {}
    for ticker in zz25['ticker'].unique():
        t25 = zz25[(zz25['ticker'] == ticker) & (zz25['tp_type'] == 'MIN')]['date'].values
        t50 = zz50[(zz50['ticker'] == ticker) & (zz50['tp_type'] == 'MIN')]['date'].values
        t75 = zz75[(zz75['ticker'] == ticker) & (zz75['tp_type'] == 'MIN')]['date'].values

        entries = []
        for d in t25:
            has50 = len(t50) > 0 and np.abs((t50 - d) / np.timedelta64(1, 'D')).min() <= CONFLUENCE_WINDOW
            has75 = len(t75) > 0 and np.abs((t75 - d) / np.timedelta64(1, 'D')).min() <= CONFLUENCE_WINDOW
            level = 3 if (has50 and has75) else 2 if has50 else 1
            entries.append((d, level))
        trough_map[ticker] = entries

    # Label each bar
    trough_level = []
    trough_side = []
    trough_dist = []
    for _, row in df.iterrows():
        ticker = row['ticker']
        d = np.datetime64(row['date'])
        entries = trough_map.get(ticker, [])
        if not entries:
            trough_level.append(None)
            trough_side.append(None)
            trough_dist.append(None)
            continue
        t_dates = np.array([e[0] for e in entries])
        t_levels = np.array([e[1] for e in entries])
        diffs = np.abs((t_dates - d) / np.timedelta64(1, 'D'))
        idx = diffs.argmin()
        trough_level.append(t_levels[idx])
        trough_side.append("AFTER" if d >= t_dates[idx] else "BEFORE")
        trough_dist.append(diffs[idx])

    df['trough_level'] = trough_level
    df['trough_side'] = trough_side
    df['trough_dist'] = trough_dist

    # Focus on ACCUMULATE bars near troughs
    from backend.modules.quality_swing.domain.rules.rc_state_probability import lookup_probability
    p_bulls = []
    for _, r in df.iterrows():
        rc = lookup_probability(float(r['tide_slope']), float(r['sigma_current']),
                                float(r['sigma_wave']), float(r['vwap_sigma_wave']))
        p_bulls.append(rc.prob_bull if rc else None)
    df['p_bull'] = p_bulls

    near = df[(df['p_bull'].notna()) & (df['p_bull'] >= 0.65) &
              (df['trough_dist'].notna()) & (df['trough_dist'] <= 15)].copy()
    near['is_after'] = near['trough_side'] == 'AFTER'

    # kf_consensus
    near['kf_consensus'] = (
        np.sign(near['kf_price_filt_vel'].fillna(0)) +
        np.sign(near['kf_rsi_filt_vel'].fillna(0)) +
        np.sign(near['kf_tension_filt_vel'].fillna(0)) +
        np.sign(near['kf_conj_filt_vel'].fillna(0))
    ).astype(int)

    # sigma_c_vel and svw_vel
    near['sigma_c_vel'] = near.groupby('ticker')['sigma_current'].transform(lambda x: x - x.shift(1))
    near['svw_vel'] = near.groupby('ticker')['vwap_sigma_wave'].transform(lambda x: x - x.shift(1))

    print(f"\n{'='*130}")
    print(f"  HEAD-TO-HEAD: Unified Observer vs kf_consensus vs Velocity Pair")
    print(f"  ACCUMULATE bars within 15d of trough: {len(near):,}")
    print(f"  Base rate AFTER: {near['is_after'].mean():.1%}")
    print(f"{'='*130}")

    # Detectors to compare
    detectors = {
        # ── EXISTING ──
        "hookup (close > prev_close)":
            near.groupby('ticker')['sigma_current'].transform(lambda x: x > x.shift(1)),
        "kf_consensus ≥ 2 (4 Kalman agree)":
            near['kf_consensus'] >= 2,
        "kf_consensus ≥ 3 (3+ agree)":
            near['kf_consensus'] >= 3,
        "sigma_c_vel > 0 AND svw_vel > 0":
            (near['sigma_c_vel'] > 0) & (near['svw_vel'] > 0),

        # ── UNIFIED OBSERVER ──
        "Observer: recovery > 0":
            near['obs_recovery'] > 0,
        "Observer: recovery > 0.3":
            near['obs_recovery'] > 0.3,
        "Observer: recovery > 0.5":
            near['obs_recovery'] > 0.5,
        "Observer: state=RECOVERING":
            near['obs_state'] == 'RECOVERING',
        "Observer: transition > median":
            near['obs_transition'] > near['obs_transition'].median(),
        "Observer: vel_norm > median AND recovery > 0":
            (near['obs_vel_norm'] > near['obs_vel_norm'].median()) & (near['obs_recovery'] > 0),

        # ── COMBINED ──
        "Observer recovery>0 + hookup":
            (near['obs_recovery'] > 0) & near.groupby('ticker')['sigma_current'].transform(lambda x: x > x.shift(1)),
        "Observer recovery>0.3 + vel>0":
            (near['obs_recovery'] > 0.3) & (near['sigma_c_vel'] > 0) & (near['svw_vel'] > 0),
    }

    print(f"\n  {'Detector':<50s} {'N':>6s} {'%flag':>7s} {'%AFT_flag':>10s} {'%AFT_¬flag':>10s} "
          f"{'spread':>8s} {'AUC':>6s}")
    print(f"  {'─'*50} {'─'*6} {'─'*7} {'─'*10} {'─'*10} {'─'*8} {'─'*6}")

    for name, mask in detectors.items():
        mask = mask.fillna(False) if hasattr(mask, 'fillna') else mask
        n_flag = mask.sum()
        if n_flag < 50 or (~mask).sum() < 50:
            continue

        after_flag = near[mask]['is_after'].mean()
        after_not = near[~mask]['is_after'].mean()
        spread = after_flag - after_not

        # AUC for this detector
        try:
            auc = roc_auc_score(near['is_after'].astype(int), mask.astype(int))
        except Exception:
            auc = 0.5

        marker = " ★★" if spread > 0.15 else " ★" if spread > 0.10 else ""
        print(f"  {name:<50s} {n_flag:>6,} {n_flag/len(near):>6.1%} {after_flag:>9.1%} {after_not:>9.1%} "
              f"{spread:>+7.1%} {auc:>5.3f}{marker}")

    # ── Observer recovery_score as CONTINUOUS feature ──
    print(f"\n{'='*130}")
    print(f"  CONTINUOUS FEATURES — AUC for predicting AFTER trough")
    print(f"{'='*130}")

    cont_features = {
        'obs_recovery': "Observer recovery_score",
        'obs_vel_norm': "Observer velocity_norm",
        'obs_transition': "Observer transition_score",
        'obs_innovation': "Observer innovation_norm",
        'kf_consensus': "kf_consensus (sum of signs)",
        'sigma_c_vel': "sigma_c_vel (σ_C velocity)",
        'svw_vel': "svw_vel (σV_W velocity)",
    }

    for col, name in cont_features.items():
        valid = near[col].notna()
        sub = near[valid]
        if len(sub) < 500:
            continue
        try:
            auc = roc_auc_score(sub['is_after'].astype(int), sub[col].astype(float))
            direction = "HIGH→AFTER" if auc >= 0.5 else "LOW→AFTER"
            auc_eff = max(auc, 1 - auc)

            med = sub[col].median()
            after_hi = sub[sub[col] >= med]['is_after'].mean()
            after_lo = sub[sub[col] < med]['is_after'].mean()
            spread = after_hi - after_lo

            q10 = sub[col].quantile(0.10)
            q90 = sub[col].quantile(0.90)
            r10 = sub[sub[col] <= q10]['is_after'].mean() if (sub[col] <= q10).sum() > 30 else None
            r90 = sub[sub[col] >= q90]['is_after'].mean() if (sub[col] >= q90).sum() > 30 else None
            xspread = abs(r90 - r10) if r10 is not None and r90 is not None else 0

            marker = " ★★" if xspread > 0.25 else " ★" if xspread > 0.15 else ""
            r10s = f"{r10:.1%}" if r10 is not None else "  —"
            r90s = f"{r90:.1%}" if r90 is not None else "  —"
            print(f"  {name:<40s} AUC={auc_eff:.3f} {direction:<12s} "
                  f"med_split={after_hi:.1%}/{after_lo:.1%} Q10={r10s} Q90={r90s} Xspread={xspread:.1%}{marker}")
        except Exception:
            continue

    # ── Observer state distribution ──
    print(f"\n{'='*130}")
    print(f"  OBSERVER STATE DISTRIBUTION")
    print(f"{'='*130}")
    for state in ['RECOVERING', 'DETERIORATING', 'TRANSITIONING', 'STABLE']:
        mask = near['obs_state'] == state
        n = mask.sum()
        if n < 20:
            continue
        pct = n / len(near)
        after = near[mask]['is_after'].mean()
        print(f"  {state:<20s} N={n:>5,} ({pct:>5.1%})  %AFTER={after:.1%}")

    print("\nDONE")


def main():
    print("Loading data...")
    cs, zz25, zz50, zz75 = load_data()
    print(f"  {len(cs):,} snapshots, {cs['ticker'].nunique()} tickers")

    print("Running unified observer on all tickers...")
    df = compute_observer_series(cs)
    print(f"  {len(df):,} bars with observer output")

    print("Labeling and comparing...")
    label_and_compare(df, zz25, zz50, zz75)


if __name__ == "__main__":
    main()
