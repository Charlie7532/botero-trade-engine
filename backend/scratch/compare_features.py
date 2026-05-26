import os, sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.head_scorer import HeadScorer
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker

store = TimescaleDataStore()
scorer = HeadScorer()

ticker = "SPY"
idx = 3907

ohlc = store.load_bars(ticker, "1d")
close = ohlc["close"].values.astype(float)
high = ohlc["high"].values.astype(float)
low = ohlc["low"].values.astype(float)
volume = ohlc["volume"].values.astype(float)
timestamps = ohlc.index.tolist()

ts = timestamps[idx]

# Load from tape
q = f"SELECT * FROM engine.signal_tape WHERE ticker = '{ticker}' AND timestamp = '{ts}'"
tape_row = pd.read_sql(q, store.engine).iloc[0]

# Pre-compute RSI and Kalman
intel = RSIIntelligence()
raw_rsi = intel._calc_rsi_series(close, 14)
import numpy as np
rsi_full = np.concatenate(([50.0], raw_rsi))

tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
vol_s = pd.Series(volume)
vol_m = vol_s.rolling(window=20, min_periods=1).mean()
returns = pd.Series(close).pct_change()
kalman_vel = np.zeros(len(close))
kalman_vad = np.zeros(len(close))
for i in range(len(close)):
    rv = float(volume[i])
    av = float(vol_m.iloc[i])
    orvol = rv / av if av > 0 else 1.0
    pc = float(close[max(0, i - 1)])
    cc = float(close[i])
    chg = ((cc - pc) / pc * 100) if pc > 0 else 0.0
    st = tracker.update(ticker, orvol, chg)
    kalman_vel[i] = st.get("velocity", 0.0)
    if i >= 20:
        v20 = returns.iloc[max(0, i - 19) : i + 1].std()
        kalman_vad[i] = kalman_vel[i] / max(v20 * 100, 0.01)

# Fresh computation
snap = compute_channel_snapshot(close, high, low, volume, idx)
snap.rsi_value = round(float(rsi_full[idx]), 2)
snap.kalman_velocity = round(float(kalman_vel[idx]), 6)
snap.vol_adj_delta = round(float(kalman_vad[idx]), 6)

prev_snap = compute_channel_snapshot(close, high, low, volume, idx - 1)
prev_snap.rsi_value = round(float(rsi_full[idx - 1]), 2)
prev_snap.kalman_velocity = round(float(kalman_vel[idx - 1]), 6)
prev_snap.vol_adj_delta = round(float(kalman_vad[idx - 1]), 6)

feat = scorer._snapshot_to_features(ticker, snap, prev_snap)

print("COMPARING FEATURES FOR SPY AT IDX 3907:")
print(f"{'Feature':30s} | {'Tape':15s} | {'Fresh':15s} | {'Diff':15s}")
print("-" * 80)
for k in sorted(feat.keys()):
    tape_val = tape_row.get(k)
    fresh_val = feat[k]
    if tape_val is not None:
        diff = float(tape_val) - float(fresh_val)
        if abs(diff) > 1e-5:
            print(f"{k:30s} | {tape_val:15.6f} | {fresh_val:15.6f} | {diff:15.6f} <--- DIFF!")
        else:
            print(f"{k:30s} | {tape_val:15.6f} | {fresh_val:15.6f} | {diff:15.6f}")

store.close()
