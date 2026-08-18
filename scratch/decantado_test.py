import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG, d1_directional_vote, CALIBRATION_FILE

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
GRUPO_A = ["vix","bsi","fg","credit","rotation"]

fact_stores = {}
for code in GRUPO_A:
    with open(f"{RULES}/{code}_fact_store.json") as f:
        fact_stores[code] = json.load(f)["states"]
with open(CALIBRATION_FILE) as f: cal = json.load(f)
w_bear = cal["type_mask"]["MIN"]["w_bear"]; w_dom = cal["type_mask"]["MIN"]["w_dom"]
d1_mean = cal["d1_bear_5"]["mean"]; d1_std = cal["d1_bear_5"]["std"]
dom_mean = cal["domino_zz25"]["mean"]; dom_std = cal["domino_zz25"]["std"]

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25")
legs50 = repo.get_confirmed_legs("SPY","zz50")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
df25["abs_prev_leg_return"] = np.abs(df25["prev_leg_return"])

indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    s = store.load_bars(cfg["ticker"],"1d")["close"].copy()
    s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
    indicator_series[code] = s
all_dates = set(); [all_dates.update(s.index) for s in indicator_series.values()]
date_features = pd.DataFrame(index=sorted(all_dates))
for code, s in indicator_series.items():
    vel = s.diff(3); std2=s.rolling(2).std(); std10=s.rolling(10).std()
    vol=(std2/std10).fillna(1.0)
    date_features[f"{code}_val"]=s; date_features[f"{code}_vel"]=vel; date_features[f"{code}_vol"]=vol

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}
store.close()

obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index: continue
    feats = date_features.loc[pd_]
    rec = {"cascade_50":row["cascade_50"], "start_type":row["start_type"], "abs_prev_leg_return":row["abs_prev_leg_return"]}
    votes={}
    for code in GRUPO_A:
        val=feats.get(f"{code}_val"); vel=feats.get(f"{code}_vel",0.0); vol=feats.get(f"{code}_vol",1.0)
        if pd.isna(val): continue
        if pd.isna(vel): vel=0.0
        if pd.isna(vol): vol=1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                votes[code] = d1_directional_vote(res.state_key)
                sk = res.state_key
                zk = fact_stores[code].get(sk, {}).get("zigzag_kinematic", {}).get("zz25", {})
                rec[f"{code}_vote"] = votes[code]
                rec[f"{code}_zk_pbull"] = zk.get("p_bull")
                rec[f"{code}_n"] = fact_stores[code].get(sk, {}).get("zz25", {}).get("n_raw")
        except: continue
    p_type = row["start_type"]
    allowed = set(cal["type_mask"].get(p_type, {}).get("stations", GRUPO_A))
    mv=[v for c,v in votes.items() if c in allowed]
    d1b5 = sum(1 for v in mv if v<0)/len(mv) if mv else 0
    z_bear = (d1b5 - d1_mean)/d1_std
    z_dom = (row["abs_prev_leg_return"] - dom_mean)/dom_std
    rec["cc_baseline"] = w_bear*z_bear + w_dom*z_dom
    obs.append(rec)

df = pd.DataFrame(obs)
y = df["cascade_50"].values

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

print("═══ DECANTADO — refinar voto D1 con hit-rate del estado ═══\n")
print(f"Baseline cascade_conviction: IC={ic(df['cc_baseline'], y):+.4f}\n")

# Decanting rules: within each station, mute the D1 vote if the state's zk_pbull DISAGREES
# vote=-1 (bearish) but zk_pbull > 0.5 (state actually bullish) -> mute
# vote=+1 (bullish) but zk_pbull < 0.5 (state actually bearish) -> mute

for threshold in [0.50, 0.55, 0.60, 0.65]:
    # Recompute d1_bear with decanted votes
    decanted_bear = []
    for _, row in df.iterrows():
        kept_votes = []
        for code in GRUPO_A:
            v = row.get(f"{code}_vote")
            pb = row.get(f"{code}_zk_pbull")
            n = row.get(f"{code}_n")
            if pd.isna(v) or pd.isna(pb): continue
            # Cold-start: if N < 10, keep raw vote (fallback)
            if n is not None and not pd.isna(n) and n < 10:
                kept_votes.append(v)
                continue
            # Decant: if vote and state direction disagree, mute
            disagreement = (v < 0 and pb > threshold) or (v > 0 and pb < (1-threshold))
            if not disagreement:
                kept_votes.append(v)
            # else: muted (not appended)
        if kept_votes:
            decanted_bear.append(sum(1 for v in kept_votes if v<0)/len(kept_votes))
        else:
            decanted_bear.append(np.nan)
    df["decanted_bear"] = decanted_bear
    
    z_bear_dec = (df["decanted_bear"] - d1_mean)/d1_std
    z_dom = (df["abs_prev_leg_return"] - dom_mean)/dom_std
    cc_dec = w_bear*z_bear_dec + w_dom*z_dom
    
    ic_dec = ic(cc_dec, y)
    n_muted = sum(1 for v in decanted_bear if pd.notna(v))
    print(f"  threshold={threshold:.2f}: IC={ic_dec:+.4f}  (Δ={ic_dec-ic(df['cc_baseline'], y):+.4f})  N_válidos={n_muted}")

# Also try: mute ONLY if extreme disagreement (pb > 0.65 or pb < 0.35)
print("\n═══ DECANTADO AGRESIVO — mutear solo desacuerdo EXTREMO ═══")
for lo, hi in [(0.35, 0.65), (0.30, 0.70)]:
    decanted_bear = []
    for _, row in df.iterrows():
        kept = []
        for code in GRUPO_A:
            v = row.get(f"{code}_vote"); pb = row.get(f"{code}_zk_pbull"); n = row.get(f"{code}_n")
            if pd.isna(v) or pd.isna(pb): continue
            if n is not None and not pd.isna(n) and n < 10:
                kept.append(v); continue
            disagree = (v < 0 and pb > hi) or (v > 0 and pb < lo)
            if not disagree: kept.append(v)
        decanted_bear.append(sum(1 for v in kept if v<0)/len(kept) if kept else np.nan)
    z_bear_dec = (pd.Series(decanted_bear) - d1_mean)/d1_std
    cc_dec = w_bear*z_bear_dec + w_dom*z_dom
    print(f"  banda [{lo},{hi}]: IC={ic(cc_dec, y):+.4f}  (Δ={ic(cc_dec,y)-ic(df['cc_baseline'],y):+.4f})")