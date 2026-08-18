import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG

ALL = list(STATION_CONFIG.keys())
RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"

# Load fact store just for state_key lookup (not for zk_p_bull — we recompute OOS)
fact_stores = {}
for code in ALL:
    with open(f"{RULES}/{code}_fact_store.json") as f:
        fact_stores[code] = json.load(f)["states"]

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

legs25 = repo.get_confirmed_legs("SPY","zz25")
legs50 = repo.get_confirmed_legs("SPY","zz50")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
df25["next_type"] = df25["start_type"].shift(-1)
df25["next_bear"] = (df25["next_type"]=="MIN").astype(float)

# Load all station data with D2/D3
indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    s = store.load_bars(cfg["ticker"],"1d")["close"].copy()
    s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
    indicator_series[code] = s

all_dates_set = set()
for s in indicator_series.values(): all_dates_set.update(s.index)
date_features = pd.DataFrame(index=sorted(all_dates_set))
for code, s in indicator_series.items():
    vel = s.diff(3); std2=s.rolling(2).std(); std10=s.rolling(10).std()
    vol=(std2/std10).fillna(1.0)
    date_features[f"{code}_val"]=s; date_features[f"{code}_vel"]=vel; date_features[f"{code}_vol"]=vol

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}
store.close()

# Build chronological state-key traces for ALL 11 stations
records = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index: continue
    feats = date_features.loc[pd_]
    rec = {"pivot_date": pd_, "next_bear": row["next_bear"], "cascade_50": row["cascade_50"]}
    for code in ALL:
        val=feats.get(f"{code}_val"); vel=feats.get(f"{code}_vel",0.0); vol=feats.get(f"{code}_vol",1.0)
        if pd.isna(val): continue
        if pd.isna(vel): vel=0.0
        if pd.isna(vol): vol=1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                rec[f"{code}_sk"] = res.state_key
        except: continue
    records.append(rec)

df = pd.DataFrame(records).sort_values("pivot_date")

# WALK-FORWARD OOS: 26 folds expanding window (same as cascade decay check)
n_total = len(df)
n_folds = 26
fold_size = n_total // n_folds
folds = []
for i in range(n_folds):
    train_end_idx = (i + 1) * fold_size
    train = df.iloc[:train_end_idx]
    test = df.iloc[train_end_idx:train_end_idx + fold_size]
    if len(test) < 20 or len(train) < 50: continue
    folds.append((train, test))

print(f"Folds: {len(folds)} (expanding window, ~1yr tests)\n")

fold_ics = []
cold_ics = []  # States with N>=10 in training
all_n_skipped = 0

for fi, (train, test) in enumerate(folds):
    # For each test pivot, compute OOS global p_bull from training data
    oos_preds = []
    oos_true_vals = []
    for _, test_row in test.iterrows():
        station_pbulls = []
        for code in ALL:
            sk = test_row.get(f"{code}_sk")
            if pd.isna(sk): continue
            train_mask = train[f"{code}_sk"].notna() & (train[f"{code}_sk"] == sk)
            n = train_mask.sum()
            if n == 0: continue
            n_bull = (1 - train.loc[train_mask, "next_bear"].astype(float)).sum()
            n_bear = train.loc[train_mask, "next_bear"].astype(float).sum()
            if n_bull + n_bear < 2:
                all_n_skipped += 1
                continue
            m = 5
            p_bull = (n_bull + m * 0.5) / (n_bull + n_bear + m)
            station_pbulls.append(p_bull)
        if len(station_pbulls) >= 3:
            oos_preds.append(np.mean(station_pbulls))
            oos_true_vals.append(test_row["next_bear"])
    if len(oos_preds) < 20: continue
    ic_val = spearmanr(oos_preds, oos_true_vals)[0]
    fold_ics.append(ic_val)

print("═══ WALK-FORWARD OOS — State Vector (sin look-ahead) ═══\n")
fold_ics = np.array([f for f in fold_ics if not np.isnan(f)])
print(f"Folds: {len(fold_ics)} | OOS IC mean: {np.mean(fold_ics):+.4f} | median: {np.median(fold_ics):+.4f}")
print(f"OOS IC std: {np.std(fold_ics):.4f} | Folds >0: {np.sum(fold_ics>0)}/{len(fold_ics)} ({np.mean(fold_ics>0)*100:.0f}%)")
print(f"IC min/max: {np.min(fold_ics):+.4f} / {np.max(fold_ics):+.4f}")

# Bootstrap CI
rng = np.random.default_rng(42)
bs_means = [np.mean(rng.choice(fold_ics, size=len(fold_ics), replace=True)) for _ in range(2000)]
ci = np.percentile(bs_means, [2.5, 97.5])
print(f"Bootstrap CI95: [{ci[0]:+.4f}, {ci[1]:+.4f}]")

print(f"\n═══ COMPARACIÓN IS vs OOS ═══")
print(f"IS IC (con look-ahead): -0.489  (reportado)")
print(f"OOS IC (sin look-ahead): {np.mean(fold_ics):+.4f}  ({len(fold_ics)} folds walk-forward)")
deg = (abs(np.mean(fold_ics)) - 0.489) / 0.489 * 100
print(f"Degradación IS→OOS: {deg:+.0f}% (positivo = mejora, negativo = degrada)")

print(f"\n═══ CRÍTICO 3 — Cold Start ═══")
print(f"Estados N<10: afectan {all_n_skipped} pivotes (de {len(df)}) — signal ausente en esos pivotes")
print(f"→ El state vector OOS solo funciona en pivotes con ≥2 muestras de training")