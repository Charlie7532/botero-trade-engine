import json
from datetime import timedelta
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG, d1_directional_vote

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]

fact_stores = {}
for code in GRUPO_A:
    with open(f"{RULES}/{code}_fact_store.json") as f:
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

obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index:
        continue
    feats = date_features.loc[pd_]
    rec = {"pivot_date": pd_, "cascade_50": row["cascade_50"], "start_type": row["start_type"]}
    votes = {}
    for code in GRUPO_A:
        val = feats.get(f"{code}_val")
        vel = feats.get(f"{code}_vel", 0.0)
        vol = feats.get(f"{code}_vol", 1.0)
        if pd.isna(val):
            continue
        if pd.isna(vel): vel = 0.0
        if pd.isna(vol): vol = 1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                votes[code] = d1_directional_vote(res.state_key)
                rec[f"{code}_sk"] = res.state_key
                rec[f"{code}_vel"] = float(vel)
                rec[f"{code}_vol"] = float(vol)
        except Exception:
            continue
    m_votes = [v for v in votes.values()]
    rec["d1_bear"] = sum(1 for v in m_votes if v < 0) / len(m_votes) if m_votes else np.nan
    obs.append(rec)

df_obs = pd.DataFrame(obs)
store.close()

y = df_obs["cascade_50"].values

def ic(a, b):
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 30: return np.nan, m.sum()
    return spearmanr(a[m], b[m])[0], m.sum()

print("═══ BASELINE: D1-only vote ═══")
r, n = ic(df_obs["d1_bear"], y)
print(f"  IC(d1_bear) = {r:+.4f} (N={n})")

print("\n═══ ¿SOLO D2 (velocidad)? ═══")
print(f"{'Station':<12} {'IC(D2 vel)':>10} {'N':>6}")
for code in GRUPO_A:
    r, n = ic(df_obs[f"{code}_vel"], y)
    if not np.isnan(r):
        print(f"{code:<12} {r:>+10.4f} {n:>6}")

print("\n═══ ¿SOLO D3 (volatilidad)? ═══")
print(f"{'Station':<12} {'IC(D3 vol)':>10} {'N':>6}")
for code in GRUPO_A:
    r, n = ic(df_obs[f"{code}_vol"], y)
    if not np.isnan(r):
        print(f"{code:<12} {r:>+10.4f} {n:>6}")

print("\n═══ FULL STATE: ev_net del fact store (D1×D2×D3) ═══")
print(f"{'Station':<12} {'IC(ev_net)':>10} {'IC(p_bull)':>10} {'N':>6}")
for code in GRUPO_A:
    evs = []
    pbs = []
    for sk in df_obs[f"{code}_sk"]:
        st = fact_stores[code].get(sk, {})
        zz25 = st.get("zz25", {})
        evs.append(zz25.get("ev_net"))
        pbs.append(zz25.get("p_bull"))
    r_ev, n = ic(evs, y)
    r_pb, _ = ic(pbs, y)
    if not np.isnan(r_ev):
        print(f"{code:<12} {r_ev:>+10.4f} {r_pb:>+10.4f} {n:>6}")

print("\n═══ ¿D2 direction (signo) como voto? ═══")
# D2 sign: positive = condition building (for VIX-like), negative = resolving
# Test: does D2 sign add signal on top of D1 vote?
for code in GRUPO_A:
    vel = df_obs[f"{code}_vel"]
    sign_vote = np.where(vel > 0, 1, np.where(vel < 0, -1, 0))
    r, n = ic(sign_vote, y)
    print(f"  {code:<12} IC(D2 signo) = {r:+.4f} (N={n})")
