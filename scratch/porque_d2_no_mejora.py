import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG, d1_directional_vote, CALIBRATION_FILE

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
GRUPO_A = ["vix","bsi","fg","credit","rotation"]

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
    vels = {}
    for code in GRUPO_A:
        val=feats.get(f"{code}_val"); vel=feats.get(f"{code}_vel",0.0); vol=feats.get(f"{code}_vol",1.0)
        if pd.isna(val): continue
        if pd.isna(vel): vel=0.0
        if pd.isna(vol): vol=1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                votes[code]=d1_directional_vote(res.state_key)
                vels[code]=float(vel)
        except: continue
    p_type = row["start_type"]
    allowed = set(cal["type_mask"].get(p_type, {}).get("stations", GRUPO_A))
    mv=[v for c,v in votes.items() if c in allowed]
    d1b5 = sum(1 for v in mv if v<0)/len(mv) if mv else 0
    z_bear = (d1b5 - d1_mean)/d1_std
    z_dom = (row["abs_prev_leg_return"] - dom_mean)/dom_std
    rec["cc_base"] = w_bear*z_bear + w_dom*z_dom
    rec["z_bear"] = z_bear; rec["z_dom"] = z_dom
    rec["d1b5"] = d1b5
    # velocity aggregates
    rec["vel_mean"] = np.mean(list(vels.values())) if vels else np.nan
    rec["vel_abs_mean"] = np.mean([abs(v) for v in vels.values()]) if vels else np.nan
    obs.append(rec)

df = pd.DataFrame(obs)
y = df["cascade_50"].values

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

print("═══ ¿Por qué D2 no mejora cascade? ═══\n")
print(f"Baseline cascade_conviction: IC={ic(df['cc_base'], y):+.4f}\n")

# 1. Is domino (price velocity) already capturing what D2 would add?
print("── Relación entre domino (velocidad precio) y D2 (velocidad indicador) ──")
print(f"corr(z_dom, vel_abs_mean) = {spearmanr(df['z_dom'].dropna(), df['vel_abs_mean'].dropna()[df['z_dom'].notna()])[0]:+.4f}")
print(f"IC(vel_abs_mean → cascade) = {ic(df['vel_abs_mean'], y):+.4f}")
print(f"IC(z_dom → cascade)        = {ic(df['z_dom'], y):+.4f}")

# 2. Does |D2| (signed vs absolute) matter?
print(f"\n── ¿Signo vs magnitud de D2? ──")
print(f"IC(vel_mean CON SIGNO → cascade) = {ic(df['vel_mean'], y):+.4f}")
print(f"IC(|vel_mean| → cascade)         = {ic(df['vel_abs_mean'], y):+.4f}")

# 3. Add |D2| as 3rd term
vel_mean = df["vel_abs_mean"].dropna()
v_mean = vel_mean.mean(); v_std = vel_mean.std()
z_vel = (df["vel_abs_mean"] - v_mean)/v_std
cc_3term = w_bear*df["z_bear"] + w_dom*df["z_dom"] + 0.15*z_vel
print(f"\n── |D2| como 3er término (peso 0.15) ──")
print(f"IC baseline: {ic(df['cc_base'], y):+.4f}")
print(f"IC + |D2|:   {ic(cc_3term, y):+.4f}")

# 4. Does |D2| interact with domino? (both velocity)
# Split by domino tercile, check if |D2| adds within low-domino
dom_lo = df["z_dom"] < df["z_dom"].quantile(0.33)
print(f"\n── ¿|D2| ayuda cuando domino es BAJO? (no redundante) ──")
print(f"IC(z_dom→cascade) en domino BAJO:  {ic(df.loc[dom_lo,'z_dom'], y[dom_lo]):+.4f}")
print(f"IC(|D2|→cascade) en domino BAJO:   {ic(df.loc[dom_lo,'vel_abs_mean'], y[dom_lo]):+.4f}")
print(f"IC(baseline) en domino BAJO:       {ic(df.loc[dom_lo,'cc_base'], y[dom_lo]):+.4f}")