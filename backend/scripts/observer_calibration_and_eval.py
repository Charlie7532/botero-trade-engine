#!/usr/bin/env python3
"""
Observer Calibration + Full Model Assembly + Win/Lose Evaluation
=================================================================
Three-in-one exercise:

  I.   CALIBRATION SWEEP: q_scale × r_scale × recovery_direction
  II.  FULL MODEL ASSEMBLY: v2 → v3 → v4 → v4+Observer
  III. WIN/LOSE EVALUATION: is each change a net gain?

Ground truth: 5% zigzag troughs + 3-scale confluences.
Metrics: %AFTER, AUC, profit_to_peak, capture_ratio, false_alarm_rate
"""
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from dataclasses import dataclass
from itertools import product
from sklearn.metrics import roc_auc_score

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_state_probability import (
    lookup_probability, _classify_sigma,
)


TEST_START = "2006-01-01"
CONFLUENCE_WINDOW = 5

# ═══════════════════════════════════════════════════════════
# Unified Observer (copy from backtest — self-contained)
# ═══════════════════════════════════════════════════════════
OBS_NAMES = ["sigma_current", "vwap_sigma_wave", "tension_wave", "rsi_value", "conj_wave_tide"]
N_OBS = len(OBS_NAMES)
N_STATE = 2 * N_OBS


class UnifiedKalmanObserver:
    def __init__(self, q_scale=0.03, r_scale=0.15, recovery_dir=None):
        self.q_scale = q_scale
        self.r_scale = r_scale
        self.recovery_dir = recovery_dir if recovery_dir is not None else np.array([1.0, 1.0, 1.0, 1.0, -1.0])
        self.x = None
        self.P = None
        self.F = None
        self.H = None
        self.Q = None
        self.R = None
        self._data_std = None

    def _build(self, data_std, dt=1.0):
        self._data_std = data_std
        self.F = np.eye(N_STATE)
        for i in range(N_OBS):
            self.F[i, N_OBS + i] = dt
        self.H = np.zeros((N_OBS, N_STATE))
        for i in range(N_OBS):
            self.H[i, i] = 1.0
        self.Q = np.zeros((N_STATE, N_STATE))
        for i in range(N_OBS):
            var = data_std[i] ** 2
            self.Q[i, i] = self.q_scale * var * dt**2
            self.Q[i, N_OBS + i] = self.q_scale * var * dt
            self.Q[N_OBS + i, i] = self.q_scale * var * dt
            self.Q[N_OBS + i, N_OBS + i] = self.q_scale * var
        self.R = np.diag(self.r_scale * data_std ** 2)

    def reset(self, obs0, data_std):
        self._build(data_std)
        self.x = np.zeros(N_STATE)
        self.x[:N_OBS] = obs0
        self.P = np.eye(N_STATE)
        for i in range(N_OBS):
            self.P[i, i] = data_std[i] ** 2
            self.P[N_OBS + i, N_OBS + i] = data_std[i] ** 2 * 4.0

    def update(self, z):
        if self.x is None:
            return 0.0, 0.0, "STABLE"
        x_pred = self.F @ self.x
        P_pred = self.F @ self.P @ self.F.T + self.Q
        y = z - self.H @ x_pred
        S = self.H @ P_pred @ self.H.T + self.R
        try:
            K = P_pred @ self.H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            K = P_pred @ self.H.T @ np.linalg.pinv(S)
        x_new = x_pred + K @ y
        self.x = x_new
        self.P = (np.eye(N_STATE) - K @ self.H) @ P_pred

        vel = x_new[N_OBS:]
        vel_n = vel / (self._data_std + 1e-10)
        vel_norm = float(np.linalg.norm(vel_n))
        rd = self.recovery_dir / np.linalg.norm(self.recovery_dir)
        if vel_norm > 1e-10:
            recovery = float(np.dot(vel_n / np.linalg.norm(vel_n), rd))
        else:
            recovery = 0.0
        if recovery > 0.3 and vel_norm > 0.5:
            state = "RECOVERING"
        elif recovery < -0.3 and vel_norm > 0.5:
            state = "DETERIORATING"
        elif vel_norm > 1.0:
            state = "TRANSITIONING"
        else:
            state = "STABLE"
        return recovery, vel_norm, state


# ═══════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════

def load_data():
    store = TimescaleDataStore(); conn = store._conn()
    cs = pd.read_sql(f"""
        SELECT ticker, timestamp::date as date,
               sigma_current, sigma_wave, sigma_tide,
               vwap_sigma_wave, vwap_sigma_current,
               tide_slope, current_slope, wave_slope,
               tension_wave, tension_current,
               rsi_value, conj_wave_tide,
               current_accel, wave_accel,
               kf_price_filt_vel, kf_rsi_filt_vel,
               kf_tension_filt_vel, kf_conj_filt_vel
        FROM engine.channel_snapshots
        WHERE timeframe = '1d' AND timestamp >= '{TEST_START}'
        ORDER BY ticker, timestamp
    """, conn)

    zz25 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.025 ORDER BY ticker, timestamp", conn)
    zz50 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.05 ORDER BY ticker, timestamp", conn)
    zz75 = pd.read_sql("SELECT ticker, timestamp::date as date, tp_type, price FROM engine.zigzag_points WHERE min_swing_pct=0.075 ORDER BY ticker, timestamp", conn)
    bars = pd.read_sql("SELECT ticker, time::date as date, close FROM market.ohlcv_bars WHERE timeframe='1d' ORDER BY ticker, time", conn)

    store._put(conn); store.close()
    for d in [cs, zz25, zz50, zz75, bars]:
        d['date'] = pd.to_datetime(d['date'])
    return cs, zz25, zz50, zz75, bars


def build_base_df(cs, bars, zz25, zz50, zz75):
    """Build the master dataframe with all labels and features."""
    df = cs.merge(bars[['ticker', 'date', 'close']], on=['ticker', 'date'], how='inner')
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)

    # P(bull)
    p_bulls = []
    for _, r in df.iterrows():
        rc = lookup_probability(float(r['tide_slope']), float(r['sigma_current']),
                                float(r['sigma_wave']), float(r['vwap_sigma_wave']))
        p_bulls.append(rc.prob_bull if rc else None)
    df['p_bull'] = p_bulls
    df = df.dropna(subset=['p_bull'])

    # hookup
    df['hookup'] = df.groupby('ticker')['close'].transform(lambda x: x > x.shift(1))

    # Velocities
    df['sigma_c_vel'] = df.groupby('ticker')['sigma_current'].transform(lambda x: x - x.shift(1))
    df['svw_vel'] = df.groupby('ticker')['vwap_sigma_wave'].transform(lambda x: x - x.shift(1))

    # kf_consensus
    df['kf_consensus'] = (
        np.sign(df['kf_price_filt_vel'].fillna(0)) +
        np.sign(df['kf_rsi_filt_vel'].fillna(0)) +
        np.sign(df['kf_tension_filt_vel'].fillna(0)) +
        np.sign(df['kf_conj_filt_vel'].fillna(0))
    ).astype(int)

    # Trough labels
    trough_map = {}
    for ticker in zz25['ticker'].unique():
        t25 = zz25[(zz25['ticker'] == ticker) & (zz25['tp_type'] == 'MIN')].sort_values('date')
        d50 = pd.to_datetime(zz50[(zz50['ticker'] == ticker) & (zz50['tp_type'] == 'MIN')]['date']).values
        d75 = pd.to_datetime(zz75[(zz75['ticker'] == ticker) & (zz75['tp_type'] == 'MIN')]['date']).values

        entries = []
        for _, r in t25.iterrows():
            d = np.datetime64(r['date'])
            has50 = len(d50) > 0 and np.abs((d50 - d) / np.timedelta64(1, 'D')).min() <= CONFLUENCE_WINDOW
            has75 = len(d75) > 0 and np.abs((d75 - d) / np.timedelta64(1, 'D')).min() <= CONFLUENCE_WINDOW
            level = 3 if (has50 and has75) else 2 if has50 else 1
            entries.append((np.datetime64(r['date']), level, float(r['price'])))
        trough_map[ticker] = entries

    # Peak map for profit
    peak_map = {}
    for ticker in zz50['ticker'].unique():
        peaks = zz50[(zz50['ticker'] == ticker) & (zz50['tp_type'] == 'MAX')].sort_values('date')
        peak_map[ticker] = [(np.datetime64(r['date']), float(r['price'])) for _, r in peaks.iterrows()]

    t_level, t_side, t_dist, profit = [], [], [], []
    for _, row in df.iterrows():
        ticker, d, price = row['ticker'], np.datetime64(row['date']), float(row['close'])
        troughs = trough_map.get(ticker, [])
        peaks = peak_map.get(ticker, [])
        if not troughs:
            t_level.append(None); t_side.append(None); t_dist.append(None); profit.append(None)
            continue
        td = np.array([t[0] for t in troughs])
        tl = np.array([t[1] for t in troughs])
        diffs = np.abs((td - d) / np.timedelta64(1, 'D'))
        idx = diffs.argmin()
        t_level.append(tl[idx])
        t_side.append("AFTER" if d >= td[idx] else "BEFORE")
        t_dist.append(diffs[idx])
        # Profit to next peak
        pd_arr = np.array([p[0] for p in peaks]) if peaks else np.array([])
        pp_arr = np.array([p[1] for p in peaks]) if peaks else np.array([])
        pi = np.searchsorted(pd_arr, d, side='right') if len(pd_arr) > 0 else len(pd_arr)
        profit.append((pp_arr[pi] / price - 1) * 100 if pi < len(pp_arr) else None)

    df['trough_level'] = t_level
    df['trough_side'] = t_side
    df['trough_dist'] = t_dist
    df['profit_to_peak'] = profit

    return df


# ═══════════════════════════════════════════════════════════
# I. CALIBRATION SWEEP
# ═══════════════════════════════════════════════════════════

def run_calibration_sweep(cs, df_near):
    """Sweep q_scale, r_scale, recovery_direction weights."""
    q_vals = [0.01, 0.03, 0.05, 0.10]
    r_vals = [0.05, 0.10, 0.15, 0.25]

    # Recovery direction variants
    rec_dirs = {
        "default [1,1,1,1,-1]":    np.array([1.0, 1.0, 1.0, 1.0, -1.0]),
        "σC-heavy [2,1,1,1,-1]":   np.array([2.0, 1.0, 1.0, 1.0, -1.0]),
        "flow-heavy [1,2,1,1,-1]": np.array([1.0, 2.0, 1.0, 1.0, -1.0]),
        "RSI-heavy [1,1,1,2,-1]":  np.array([1.0, 1.0, 1.0, 2.0, -1.0]),
        "no-conj [1,1,1,1,0]":     np.array([1.0, 1.0, 1.0, 1.0, 0.0]),
        "equal [1,1,1,1,1]":       np.array([1.0, 1.0, 1.0, 1.0, 1.0]),
    }

    print(f"\n{'='*130}")
    print(f"  I. CALIBRATION SWEEP — q_scale × r_scale × recovery_direction")
    print(f"{'='*130}")

    # Phase 1: q × r sweep with default direction
    print(f"\n  Phase 1: q × r sweep (default recovery direction)")
    print(f"  {'q_scale':>8s} {'r_scale':>8s} {'AUC':>6s} {'%AFT_rec':>9s} {'%AFT_det':>9s} "
          f"{'spread':>8s} {'N_rec':>6s} {'pct_rec':>8s}")

    best_auc = 0
    best_params = None
    for q, r in product(q_vals, r_vals):
        recovery_scores = _run_observer_on_data(cs, q, r, rec_dirs["default [1,1,1,1,-1]"])
        near_rec = df_near.copy()
        near_rec['obs_recovery'] = recovery_scores.reindex(near_rec.index)
        valid = near_rec['obs_recovery'].notna()
        sub = near_rec[valid]
        if len(sub) < 1000:
            continue

        try:
            auc = roc_auc_score(sub['is_after'].astype(int), sub['obs_recovery'])
        except Exception:
            continue

        rec_mask = sub['obs_recovery'] > 0.3
        n_rec = rec_mask.sum()
        if n_rec < 50:
            continue

        after_rec = sub[rec_mask]['is_after'].mean()
        after_not = sub[~rec_mask]['is_after'].mean()
        spread = after_rec - after_not

        marker = " ★" if auc > best_auc else ""
        if auc > best_auc:
            best_auc = auc
            best_params = (q, r)

        print(f"  {q:>8.3f} {r:>8.3f} {auc:>5.3f} {after_rec:>8.1%} {after_not:>8.1%} "
              f"{spread:>+7.1%} {n_rec:>6,} {n_rec/len(sub):>7.1%}{marker}")

    print(f"\n  BEST q_scale={best_params[0]}, r_scale={best_params[1]}, AUC={best_auc:.3f}")

    # Phase 2: recovery direction sweep with best q, r
    q_best, r_best = best_params
    print(f"\n  Phase 2: Recovery direction sweep (q={q_best}, r={r_best})")
    print(f"  {'Direction':<30s} {'AUC':>6s} {'%AFT_rec':>9s} {'spread':>8s} {'N_rec':>6s}")

    best_dir_name = None
    best_dir_auc = 0
    for dir_name, dir_vec in rec_dirs.items():
        recovery_scores = _run_observer_on_data(cs, q_best, r_best, dir_vec)
        near_rec = df_near.copy()
        near_rec['obs_recovery'] = recovery_scores.reindex(near_rec.index)
        valid = near_rec['obs_recovery'].notna()
        sub = near_rec[valid]
        if len(sub) < 1000:
            continue

        try:
            auc = roc_auc_score(sub['is_after'].astype(int), sub['obs_recovery'])
        except Exception:
            continue

        rec_mask = sub['obs_recovery'] > 0.3
        n_rec = rec_mask.sum()
        if n_rec < 50:
            continue

        after_rec = sub[rec_mask]['is_after'].mean()
        after_not = sub[~rec_mask]['is_after'].mean()
        spread = after_rec - after_not

        marker = " ★" if auc > best_dir_auc else ""
        if auc > best_dir_auc:
            best_dir_auc = auc
            best_dir_name = dir_name

        print(f"  {dir_name:<30s} {auc:>5.3f} {after_rec:>8.1%} {spread:>+7.1%} {n_rec:>6,}{marker}")

    print(f"\n  BEST direction: {best_dir_name}, AUC={best_dir_auc:.3f}")
    print(f"  FINAL CALIBRATION: q={q_best}, r={r_best}, dir={best_dir_name}")

    return q_best, r_best, rec_dirs[best_dir_name]


def _run_observer_on_data(cs, q_scale, r_scale, recovery_dir):
    """Run observer with given params, return recovery_score as Series aligned to cs index."""
    all_rec = pd.Series(dtype=float, index=cs.index)
    obs_cols = ['sigma_current', 'vwap_sigma_wave', 'tension_wave', 'rsi_value', 'conj_wave_tide']

    for ticker in cs['ticker'].unique():
        tk = cs[cs['ticker'] == ticker].sort_values('date')
        if len(tk) < 100:
            continue

        obs_data = tk[obs_cols].fillna(0).values
        warmup = min(50, len(obs_data))
        data_std = np.std(obs_data[:warmup], axis=0)
        data_std = np.maximum(data_std, 1e-6)

        observer = UnifiedKalmanObserver(q_scale=q_scale, r_scale=r_scale, recovery_dir=recovery_dir)
        observer.reset(obs_data[0], data_std)

        recs = []
        for i in range(len(obs_data)):
            rec, _, _ = observer.update(obs_data[i])
            recs.append(rec)

        all_rec.loc[tk.index] = recs

    return all_rec


# ═══════════════════════════════════════════════════════════
# II + III. FULL MODEL ASSEMBLY + WIN/LOSE EVALUATION
# ═══════════════════════════════════════════════════════════

def full_model_comparison(df_near, obs_recovery):
    """Compare v2 → v3 → v4 → v4+Observer, all on same data."""

    near = df_near.copy()
    near['obs_recovery'] = obs_recovery.reindex(near.index)

    # ── Model definitions ──
    # Each model: (name, mask function) → returns which bars get ACCUMULATE signal
    # All start from P(bull) ≥ 65% (already filtered in df_near)

    models = {}

    # v2 BASELINE: P ≥ 65% only (no filters)
    models['v2_BASELINE'] = pd.Series(True, index=near.index)

    # v3 (old TIER 2): hookup OR (wave_accel>0 AND current_accel>0)
    accel_conf = (near['wave_accel'] > 0) & (near['current_accel'] > 0)
    models['v3_accel'] = near['hookup'] | accel_conf

    # v4 (new TIER 2): hookup OR (sigma_c_vel>0 AND svw_vel>0)
    vel_conf = (near['sigma_c_vel'] > 0) & (near['svw_vel'] > 0)
    models['v4_velocity'] = near['hookup'] | vel_conf

    # v4 + kf_consensus: hookup OR vel_confirmed, + kf_consensus bonus
    models['v4_vel+kfcon'] = (near['hookup'] | vel_conf) & (near['kf_consensus'] >= 1)

    # v4 + Observer (recovery > 0): THE SINGLE KALMAN
    obs_valid = near['obs_recovery'].notna()
    models['v4+Observer_r>0'] = obs_valid & (near['obs_recovery'] > 0)

    # v4 + Observer (recovery > 0.3)
    models['v4+Observer_r>0.3'] = obs_valid & (near['obs_recovery'] > 0.3)

    # v4 + Observer (recovery > 0) + hookup
    models['v4+Observer+hookup'] = obs_valid & (near['obs_recovery'] > 0) & near['hookup']

    # COMBINED BEST: Observer recovery>0 as main filter
    # High conviction: recovery > 0.3
    models['FINAL_full'] = obs_valid & (near['obs_recovery'] > 0)
    models['FINAL_high'] = obs_valid & (near['obs_recovery'] > 0.3)

    print(f"\n{'='*130}")
    print(f"  II + III. FULL MODEL COMPARISON — Is Each Change a Net Gain?")
    print(f"  ACCUMULATE bars within 15d of trough: {len(near):,}")
    print(f"{'='*130}")

    print(f"\n  {'Model':<25s} {'N_signal':>9s} {'%select':>8s} {'%AFTER':>8s} "
          f"{'profit_med':>10s} {'Q25_pft':>8s} {'Q75_pft':>8s} "
          f"{'AUC':>6s} {'vs_v2':>7s}")

    v2_after = None
    results = []
    for name, mask in models.items():
        sub = near[mask]
        n = len(sub)
        if n < 50:
            continue

        pct_select = n / len(near)
        after = sub['is_after'].mean()
        pft = sub['profit_to_peak'].dropna()
        pft_med = pft.median() if len(pft) > 0 else 0
        pft_q25 = pft.quantile(0.25) if len(pft) > 0 else 0
        pft_q75 = pft.quantile(0.75) if len(pft) > 0 else 0

        # AUC for mask vs is_after
        try:
            auc = roc_auc_score(near['is_after'].astype(int), mask.astype(int))
        except Exception:
            auc = 0.5

        if v2_after is None:
            v2_after = after
        delta = after - v2_after

        verdict = ""
        if delta > 0.05:
            verdict = " ★★ WIN"
        elif delta > 0.02:
            verdict = " ★ WIN"
        elif delta < -0.02:
            verdict = " ✗ LOSE"
        else:
            verdict = " ~ FLAT"

        print(f"  {name:<25s} {n:>9,} {pct_select:>7.1%} {after:>7.1%} "
              f"{pft_med:>+9.1f}% {pft_q25:>+7.1f}% {pft_q75:>+7.1f}% "
              f"{auc:>5.3f} {delta:>+6.1%}{verdict}")

        results.append({'name': name, 'n': n, 'pct': pct_select, 'after': after,
                        'profit': pft_med, 'auc': auc, 'delta': delta})

    # ── False alarm analysis ──
    print(f"\n  {'='*90}")
    print(f"  FALSE ALARM ANALYSIS — When signals fire BEFORE trough")
    print(f"  {'='*90}")
    print(f"  {'Model':<25s} {'N_before':>9s} {'%before':>9s} {'avg_dist':>9s} {'max_dd':>8s}")

    for name, mask in models.items():
        sub = near[mask]
        before = sub[sub['trough_side'] == 'BEFORE']
        n_before = len(before)
        if n_before < 10:
            continue
        pct_before = n_before / len(sub)
        avg_dist = before['trough_dist'].mean()
        # Max drawdown from false signals (profit to peak is from NEXT peak,
        # but negative profit means the stock fell further)
        dd = before['profit_to_peak'].dropna()
        max_dd = dd.quantile(0.10) if len(dd) > 10 else 0

        print(f"  {name:<25s} {n_before:>9,} {pct_before:>8.1%} {avg_dist:>8.1f}d {max_dd:>+7.1f}%")

    # ── Per P(bull) level breakdown ──
    print(f"\n  {'='*90}")
    print(f"  PER P(BULL) LEVEL — Does the filter improve equally at all conviction levels?")
    print(f"  {'='*90}")

    key_models = ['v2_BASELINE', 'v3_accel', 'v4_velocity', 'v4+Observer_r>0', 'FINAL_high']
    pbins = [(0.65, 0.75, "65-75%"), (0.75, 0.85, "75-85%"), (0.85, 1.01, "85-100%")]

    for lo, hi, label in pbins:
        pmask = (near['p_bull'] >= lo) & (near['p_bull'] < hi)
        print(f"\n  P(bull) = {label}:")
        print(f"  {'Model':<25s} {'N':>6s} {'%AFTER':>8s} {'profit':>8s}")
        for name in key_models:
            mask = models[name]
            sub = near[pmask & mask]
            if len(sub) < 30:
                continue
            after = sub['is_after'].mean()
            pft = sub['profit_to_peak'].dropna().median() if len(sub['profit_to_peak'].dropna()) > 0 else 0
            print(f"  {name:<25s} {len(sub):>6,} {after:>7.1%} {pft:>+7.1f}%")

    # ── Per ticker consistency ──
    print(f"\n  {'='*90}")
    print(f"  PER TICKER CONSISTENCY — How many tickers improve?")
    print(f"  {'='*90}")

    for model_name in ['v4+Observer_r>0', 'FINAL_high']:
        mask = models[model_name]
        n_better = 0
        n_worse = 0
        n_flat = 0
        for ticker in near['ticker'].unique():
            tk_base = near[(near['ticker'] == ticker)]
            tk_model = near[(near['ticker'] == ticker) & mask]
            if len(tk_model) < 20 or len(tk_base) < 20:
                continue
            after_base = tk_base['is_after'].mean()
            after_model = tk_model['is_after'].mean()
            if after_model > after_base + 0.02:
                n_better += 1
            elif after_model < after_base - 0.02:
                n_worse += 1
            else:
                n_flat += 1

        total = n_better + n_worse + n_flat
        print(f"  {model_name}: {n_better}/{total} better, {n_worse}/{total} worse, {n_flat}/{total} flat")

    print("\nDONE")


def main():
    print("Loading data...")
    cs, zz25, zz50, zz75, bars = load_data()
    print(f"  {len(cs):,} snapshots")

    print("Building base dataframe with labels...")
    df = build_base_df(cs, bars, zz25, zz50, zz75)
    print(f"  {len(df):,} labeled bars")

    # Focus on ACCUMULATE zone near troughs
    df_near = df[(df['p_bull'] >= 0.65) &
                 (df['trough_dist'].notna()) & (df['trough_dist'] <= 15)].copy()
    df_near['is_after'] = df_near['trough_side'] == 'AFTER'
    print(f"  ACCUMULATE near trough: {len(df_near):,}")

    print("\n" + "="*130)
    print("  PHASE I: CALIBRATION SWEEP")
    print("="*130)
    q_best, r_best, dir_best = run_calibration_sweep(cs, df_near)

    print("\nRunning final observer with calibrated params...")
    obs_recovery = _run_observer_on_data(cs, q_best, r_best, dir_best)

    print("\n" + "="*130)
    print("  PHASE II + III: FULL MODEL COMPARISON")
    print("="*130)
    full_model_comparison(df_near, obs_recovery)


if __name__ == "__main__":
    main()
