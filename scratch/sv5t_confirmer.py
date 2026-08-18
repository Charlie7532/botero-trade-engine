import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG, d1_directional_vote, CALIBRATION_FILE

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([{"start_timestamp": l.start_timestamp, "start_type": l.start_type, "prev_leg_return": l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3,4))))

# Load cascade_calibration for weights
with open(CALIBRATION_FILE) as f: cal = json.load(f)
w_bear = cal["type_mask"]["MIN"]["w_bear"]
w_dom  = cal["type_mask"]["MIN"]["w_dom"]
d1_mean = cal["d1_bear_5"]["mean"]; d1_std = cal["d1_bear_5"]["std"]
dom_mean = cal["domino_zz25"]["mean"]; dom_std = cal["domino_zz25"]["std"]

# Build observations with cascade_conviction + SV5T
indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    s = store.load_bars(cfg["ticker"], "1d")["close"].copy()
    s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
    indicator_series[code] = s

all_dates = set()
for s in indicator_series.values(): all_dates.update(s.index)
date_features = pd.DataFrame(index=sorted(all_dates))
for code, s in indicator_series.items():
    date_features[f"{code}_val"] = s

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}

# Load SV5T
sv5t = store.load_bars("SV5_TURBULENCE","1d")["close"].copy()
sv5t.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(sv5t.index)]
store.close()

GRUPO_A = ["vix","bsi","fg","credit","rotation"]

obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index: continue
    feats = date_features.loc[pd_]
    votes = {}
    for code in GRUPO_A:
        val = feats.get(f"{code}_val")
        if pd.isna(val): continue
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=0.0, vol_norm=1.0, vol_d3=0.0)
            if res and res.state_key:
                votes[code] = d1_directional_vote(res.state_key)
        except: continue
    p_type = row["start_type"]
    allowed = set(cal["type_mask"].get(p_type, {}).get("stations", GRUPO_A))
    m_votes = [v for c, v in votes.items() if c in allowed]
    if not m_votes: continue
    m_bear = sum(1 for v in m_votes if v < 0)
    d1b5 = m_bear / len(m_votes)
    
    # Cascade_conviction
    z_bear = (d1b5 - d1_mean) / d1_std
    z_dom = (row["abs_prev_leg_return"] - dom_mean) / dom_std
    cc = w_bear * z_bear + w_dom * z_dom
    
    # SV5T at pivot
    sv5_idx = sv5t.index[sv5t.index <= pd_]
    sv5_val = float(sv5t[sv5_idx[-1]]) if len(sv5_idx) > 0 else np.nan
    
    obs.append({"pivot_type": p_type, "cascade_50": row["cascade_50"], 
                "cc": cc, "sv5t": sv5_val, "d1b5": d1b5})

df = pd.DataFrame(obs)
y = df["cascade_50"].values

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

# SV5T terciles
sv5_lo = df["sv5t"] < df["sv5t"].quantile(0.33)
sv5_md = (df["sv5t"] >= df["sv5t"].quantile(0.33)) & (df["sv5t"] < df["sv5t"].quantile(0.67))
sv5_hi = df["sv5t"] >= df["sv5t"].quantile(0.67)

print("═══ SV5T como CONFIRMADOR de señal ═══\n")
print(f"IC global cascade_conviction: {ic(df['cc'], y):+.4f}\n")

for label, mask in [("SV5T BAJO (calma)", sv5_lo), ("SV5T MEDIO", sv5_md), ("SV5T ALTO (batalla)", sv5_hi)]:
    ic_val = ic(df.loc[mask, "cc"], y[mask])
    rate = y[mask].mean()
    print(f"  {label:<22}: IC={ic_val:+.4f}  cascade_rate={rate:.3f}  N={mask.sum()}")

# The KEY test: does cascade_conviction work better when confirmed by volume?
print(f"\n═══ ¿La señal es más CONFIABLE con batalla? ═══")
# Compare high vs low tertile: what cascade rate does t3_high cc predict?
cc_hi = df["cc"] > df["cc"].quantile(0.67)
for label, mask in [("SV5T BAJO (sin confirmar)", sv5_lo), ("SV5T ALTO (confirmado)", sv5_hi)]:
    cc_rate = y[mask & cc_hi].mean()
    base_rate = y[mask].mean()
    lift = (cc_rate - base_rate) / base_rate * 100 if base_rate > 0 else 0
    print(f"  {label}: cc↑↑→cascade={cc_rate:.1%} (base={base_rate:.1%}, lift=+{lift:.0f}%)")

# Bootstrap the IC difference
rng = np.random.default_rng(42)
diffs = []
for _ in range(2000):
    idx_lo = rng.choice(sv5_lo[sv5_lo].index, size=sv5_lo.sum(), replace=True)
    idx_hi = rng.choice(sv5_hi[sv5_hi].index, size=sv5_hi.sum(), replace=True)
    ic_lo = ic(df.loc[idx_lo,"cc"], y[idx_lo])
    ic_hi = ic(df.loc[idx_hi,"cc"], y[idx_hi])
    if not np.isnan(ic_lo) and not np.isnan(ic_hi):
        diffs.append(ic_hi - ic_lo)
diffs = np.array(diffs)
ci = np.percentile(diffs, [2.5, 97.5])
print(f"\n  Bootstrap ΔIC (alto-bajo): CI95 [{ci[0]:+.4f}, {ci[1]:+.4f}]")
print(f"  Prob(ΔIC > 0): {(diffs>0).mean():.0%}")