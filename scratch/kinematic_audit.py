import json
from datetime import timedelta
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG, CALIBRATION_FILE

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"

# Group A stations (the ones that vote)
GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]

# Load fact stores
fact_stores = {}
for code in GRUPO_A:
    p = f"{RULES}/{code}_fact_store.json"
    with open(p) as f:
        fact_stores[code] = json.load(f)["states"]

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type, "prev_leg_return": l.prev_leg_return}
    for l in legs25
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)

# Load indicator series + adapters (same as decay check)
indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    df_ind = store.load_bars(cfg["ticker"], "1d")
    if df_ind is not None and not df_ind.empty:
        s = df_ind["close"].copy()
        s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
        indicator_series[code] = s

all_dates = set()
for s in indicator_series.values():
    all_dates.update(s.index)
date_features = pd.DataFrame(index=sorted(all_dates))
for code, s in indicator_series.items():
    vel = s.diff(3)
    std_2, std_10 = s.rolling(2).std(), s.rolling(10).std()
    vol = (std_2 / std_10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    date_features[f"{code}_val"] = s
    date_features[f"{code}_vel"] = vel
    date_features[f"{code}_vol"] = vol

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}

# Build observations with state_key per station
obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index:
        continue
    feats = date_features.loc[pd_]
    rec = {"pivot_date": pd_, "cascade_50": row["cascade_50"]}
    for code in GRUPO_A:
        adapter = adapters[code]
        val = feats.get(f"{code}_val")
        vel = feats.get(f"{code}_vel", 0.0)
        vol = feats.get(f"{code}_vol", 1.0)
        if pd.isna(val):
            rec[f"{code}_sk"] = None
            continue
        if pd.isna(vel): vel = 0.0
        if pd.isna(vol): vol = 1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapter, method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            rec[f"{code}_sk"] = res.state_key if res and res.state_key else None
        except Exception:
            rec[f"{code}_sk"] = None
    obs.append(rec)

df_obs = pd.DataFrame(obs)
store.close()

# Zigzag kinematic fields to audit
KINEMATIC_FIELDS = [
    "n_pos", "n_neg", "p_bull", "p_bear", "ev_net", "e_days",
    "ev_per_day", "rr_asymmetry",
    # structural_momentum
    "sm_up_p_continuation", "sm_up_ev_structural_pct", "sm_up_mean_accum_ret",
    "sm_down_p_continuation", "sm_down_ev_structural_pct",
    # prev_leg_domino
    "pld_mean_prev_return", "pld_mean_prev_duration", "pld_p_negative_prev",
    "pld_p_extreme_prev", "pld_cascade_rate_t3",
]

def extract_kinematic(states_dict, sk):
    """Extract kinematic fields from a state."""
    if sk is None or sk not in states_dict:
        return {}
    st = states_dict[sk]
    zz25 = st.get("zigzag_kinematic", {}).get("zz25", {})
    sm = zz25.get("structural_momentum", {})
    pld = zz25.get("prev_leg_domino", {})
    out = {}
    for f in ["n_pos", "n_neg", "p_bull", "p_bear", "ev_net", "e_days", "ev_per_day", "rr_asymmetry"]:
        out[f] = zz25.get(f)
    out["sm_up_p_continuation"] = sm.get("up_legs", {}).get("p_continuation")
    out["sm_up_ev_structural_pct"] = sm.get("up_legs", {}).get("ev_structural_pct")
    out["sm_up_mean_accum_ret"] = sm.get("up_legs", {}).get("mean_accum_ret")
    out["sm_down_p_continuation"] = sm.get("down_legs", {}).get("p_continuation")
    out["sm_down_ev_structural_pct"] = sm.get("down_legs", {}).get("ev_structural_pct")
    out["pld_mean_prev_return"] = pld.get("mean_prev_return")
    out["pld_mean_prev_duration"] = pld.get("mean_prev_duration")
    out["pld_p_negative_prev"] = pld.get("p_negative_prev")
    out["pld_p_extreme_prev"] = pld.get("p_extreme_prev")
    out["pld_cascade_rate_t3"] = pld.get("terciles_domino", {}).get("t3_large", {}).get("cascade_rate")
    return out

def ic(a, b):
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 30:
        return np.nan, m.sum()
    r, p = spearmanr(a[m], b[m])
    return r, m.sum()

y = df_obs["cascade_50"].values

print("═══ ZIGZAG_KINEMATIC — IC por campo vs cascade_50 ═══")
print(f"{'Campo':<30} {'IC':>8} {'p-val':>9} {'N':>6}")
print("-" * 58)

results = []
for field in KINEMATIC_FIELDS:
    for code in GRUPO_A:
        vals = []
        for sk in df_obs[f"{code}_sk"]:
            e = extract_kinematic(fact_stores[code], sk)
            vals.append(e.get(field))
        r, n = ic(vals, y)
        if not np.isnan(r):
            # p-value
            a = np.asarray(vals, dtype=float); b = np.asarray(y, dtype=float)
            m = ~np.isnan(a) & ~np.isnan(b)
            _, p = spearmanr(a[m], b[m])
            results.append((field, code, r, p, n))

# Sort by |IC|
results.sort(key=lambda x: abs(x[2]), reverse=True)
for field, code, r, p, n in results[:30]:
    print(f"{field[:14]:<14} [{code:<7}] {r:>+8.4f} {p:>9.4f} {n:>6}")

print("\n═══ TOP por campo (promedio |IC| entre 5 estaciones) ═══")
from collections import defaultdict
by_field = defaultdict(list)
for field, code, r, p, n in results:
    by_field[field].append(abs(r))
agg = {f: (np.mean(v), np.max(v)) for f, v in by_field.items()}
for f, (mean_r, max_r) in sorted(agg.items(), key=lambda x: -x[1][1]):
    print(f"{f:<30} mean|IC|={mean_r:.4f}  max|IC|={max_r:.4f}")
