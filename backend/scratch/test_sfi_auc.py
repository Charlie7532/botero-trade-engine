import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score
from unified_pretrainer_v2 import load_feature_lake, label_long_entry, apply_context, purged_walk_forward_cv
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.ticker_profile_store import TickerProfileStore

store = TimescaleDataStore()
ps = TickerProfileStore()
df, ohlcv_cache, profiles = load_feature_lake(store, ps)

# Test long_entry
head_name = 'long_entry'
labels = label_long_entry(df, ohlcv_cache, horizon=20)
ctx_mask = apply_context(df, head_name)
df_ctx = df[ctx_mask].copy()
labels_ctx = labels[ctx_mask.values]

valid_mask = (~np.isnan(labels_ctx))
df_clean = df_ctx[valid_mask].copy()
y = labels_ctx[valid_mask].astype(int)

features_to_test = ['tide_slope', 'sigma_tide', 'rsi_value', 'kalman_velocity']

print("\n--- AUC SFI EVALUATION ---")
for feat in features_to_test:
    X = df_clean[[feat]].values.astype(np.float32)
    sort_idx = df_clean['timestamp'].argsort().values
    X = X[sort_idx]
    y_sorted = y[sort_idx]
    
    splits = purged_walk_forward_cv(len(X), n_splits=3, purge_gap=20)
    aucs = []
    
    for fold, (train_idx, test_idx) in enumerate(splits):
        X_tr, y_tr = X[train_idx], y_sorted[train_idx]
        X_te, y_te = X[test_idx], y_sorted[test_idx]
        
        sw = max((len(y_tr) - y_tr.sum()) / max(y_tr.sum(), 1), 1.0)
        model = XGBClassifier(
            n_estimators=150, max_depth=4, learning_rate=0.05,
            min_child_weight=10, subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            scale_pos_weight=min(sw, 5.0),
            random_state=42, eval_metric='logloss', tree_method='hist',
            verbosity=0,
        )
        model.fit(X_tr, y_tr, verbose=False)
        y_prob = model.predict_proba(X_te)[:, 1]
        auc = roc_auc_score(y_te, y_prob)
        aucs.append(auc)
    
    print(f"Feature: {feat} | Mean AUC: {np.mean(aucs):.4f} | Folds AUCs: {[round(a, 4) for a in aucs]}")

store.close()
ps.close()
