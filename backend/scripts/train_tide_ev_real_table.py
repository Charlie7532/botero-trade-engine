#!/usr/bin/env python3
"""
Train Real Point-in-Time Expected Value (EV) Probability Table — Tide Model
=============================================================================
Computes the forward pivot expected value model for quality_swing with:
  1. Real Point-in-Time Returns: (price(t_pivot) / close(t)) - 1 (Zero Ghost Return Bias).
  2. Volatility Normalization: slope_norm = slope / max(atr_pct, 0.005) against 100% census quantiles.
  3. Strict Stock & ETF Filter: Excludes 106 pseudo-OHLCV indicators.
  4. Maximum Swing Horizon Gate: days_to_pivot <= 120 days.
  5. Hierarchy of Rollups:
     - L3: Full 3D State (T_slope | C_slope | vwap_sigma_wave) - 180 states
     - L2: Mid-Macro (T_slope | C_slope) - 36 states
     - L1: Macro Marea (T_slope) - 6 states
     - L0: Global Baseline

Reads from Vault: engine.channel_snapshots + market.ohlcv_bars + engine.zigzag_points.
Output: backend/modules/quality_swing/domain/rules/rc_tide_ev_probability_table.json
"""
import os, sys, json, logging
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _classify_one

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("TrainTideEV")

ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
ZIGZAG_LABEL = {0.025: "zz25", 0.05: "zz50", 0.075: "zz75"}
MAX_HORIZON_DAYS = 120
DEFAULT_FRICTION_BPS = 0.0010

OUTPUT_PATH = root_dir / "backend/modules/quality_swing/domain/rules/rc_tide_ev_probability_table.json"


def classify_sigma(value: float) -> str:
    """Classify vwap_sigma_wave into <</</~/>/>>."""
    if value < -1.0:
        return "<<"
    elif value < -0.3:
        return "<"
    elif value <= 0.3:
        return "~"
    elif value <= 1.0:
        return ">"
    else:
        return ">>"


class TideAccumulator:
    """Accumulates raw un-shrunk counts and returns for Tide level states."""
    def __init__(self):
        self.n = 0
        self.returns = []

        # Per zigzag level
        self.n_pos = {0.025: 0, 0.05: 0, 0.075: 0}
        self.n_neg = {0.025: 0, 0.05: 0, 0.075: 0}
        self.sum_max = {0.025: 0.0, 0.05: 0.0, 0.075: 0.0}
        self.sum_min = {0.025: 0.0, 0.05: 0.0, 0.075: 0.0}
        self.days_list = {0.025: [], 0.05: [], 0.075: []}

    def add_pivot(self, level: float, tp_type: str, real_return_net: float, days_to_pivot: float):
        if tp_type == "MAX":
            self.n_pos[level] += 1
            self.sum_max[level] += real_return_net
        else:
            self.n_neg[level] += 1
            self.sum_min[level] += real_return_net
        self.days_list[level].append(days_to_pivot)
        self.returns.append(real_return_net)

    def increment_n(self):
        self.n += 1

    def format_raw(self) -> dict:
        if self.n == 0:
            return {}

        std_ret = float(np.std(self.returns)) if len(self.returns) > 1 else 0.04

        res = {
            "n": int(self.n),
            "std_return": round(std_ret, 6),
        }

        for lvl in ZIGZAG_LEVELS:
            lbl = ZIGZAG_LABEL[lvl]
            res[f"n_pos_{lbl}"] = int(self.n_pos[lvl])
            res[f"n_neg_{lbl}"] = int(self.n_neg[lvl])
            res[f"sum_max_{lbl}"] = round(float(self.sum_max[lvl]), 6)
            res[f"sum_min_{lbl}"] = round(float(self.sum_min[lvl]), 6)
            res[f"e_days_{lbl}"] = round(float(np.mean(self.days_list[lvl])), 2) if self.days_list[lvl] else 10.0

        return res


def match_forward_pivots(snap_df: pd.DataFrame, zz_df: pd.DataFrame) -> dict:
    """Vectorized forward-pivot matching per ticker."""
    if snap_df.empty or zz_df.empty:
        return {}

    zz_by_ticker = {tk: group for tk, group in zz_df.groupby('ticker')}
    results = {}

    for ticker, tdf in snap_df.groupby('ticker'):
        tzz = zz_by_ticker.get(ticker)
        if tzz is None or len(tzz) == 0:
            continue

        tdf = tdf.sort_values('timestamp')
        tzz = tzz.sort_values('timestamp')

        zz_ts = tzz['timestamp'].values
        zz_type = tzz['tp_type'].values
        zz_price = tzz['price'].values

        snap_ts = tdf['timestamp'].values
        snap_close = tdf['close'].values

        indices = np.searchsorted(zz_ts, snap_ts, side='right')
        valid_mask = indices < len(zz_ts)

        valid_snap_ts = snap_ts[valid_mask]
        valid_close = snap_close[valid_mask]
        target_idx = indices[valid_mask]

        target_ts = zz_ts[target_idx]
        target_type = zz_type[target_idx]
        target_price = zz_price[target_idx]

        days_delta = ((target_ts - valid_snap_ts) / np.timedelta64(1, 'D')).astype(float)
        horizon_mask = (days_delta > 0) & (days_delta <= MAX_HORIZON_DAYS)

        if not np.any(horizon_mask):
            continue

        h_snap_ts = valid_snap_ts[horizon_mask]
        h_close = valid_close[horizon_mask]
        h_price = target_price[horizon_mask]
        h_type = target_type[horizon_mask]
        h_days = days_delta[horizon_mask]

        net_returns = ((h_price / h_close) - 1.0) - DEFAULT_FRICTION_BPS

        for sts, tp, ret, dy in zip(h_snap_ts, h_type, net_returns, h_days):
            results[(ticker, pd.to_datetime(sts).date())] = (tp, float(ret), float(dy))

    return results


def main():
    logger.info("Iniciando Censo Empírico Bruto Tide EV (Acciones + ETFs)...")
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        q_tickers = """
            SELECT ticker FROM market.ticker_metadata 
            WHERE (industry IS NULL OR UPPER(industry) != 'INDICATOR')
              AND (sector IS NULL OR UPPER(sector) NOT IN (
                  'INDICATOR', 'VOLUME BREADTH', 'CAP-WEIGHTED BREADTH', 'OPTIONS FLOW', 
                  'VOLATILITY', 'SENTIMENT', 'SHORT INTEREST', 'VOLUME INTENSITY', 
                  'QQQ BREADTH', 'INDEX', 'YIELDS', 'BROAD MARKET', 'CURRENCY', 
                  'COMMODITIES', 'FIXED INCOME', 'FEAR & GREED', 'BREADTH'
              ))
              AND ticker NOT IN ('VIX', 'VVIX', 'CBOE_PCR', 'FG', 'S5TH', 'S5FI', 'S5TW')
        """
        tickers_df = pd.read_sql(q_tickers, conn)
        all_tickers = tickers_df["ticker"].tolist()
        logger.info(f"Cargados {len(all_tickers)} activos (Solo Acciones y ETFs) desde market.ticker_metadata.")

        q_zz = """
            SELECT ticker, timestamp, tp_type, price, min_swing_pct
            FROM engine.zigzag_points
            WHERE min_swing_pct IN (0.025, 0.05, 0.075)
            ORDER BY ticker, timestamp
        """
        zz_all = pd.read_sql(q_zz, conn)
        zz_all['timestamp'] = pd.to_datetime(zz_all['timestamp'], utc=True)

        zigzags = {lvl: zz_all[zz_all['min_swing_pct'] == lvl] for lvl in ZIGZAG_LEVELS}

        s0_acc = TideAccumulator()
        l1_acc = defaultdict(TideAccumulator)
        l2_acc = defaultdict(TideAccumulator)
        l3_acc = defaultdict(TideAccumulator)

        chunk_size = 50
        total_chunks = (len(all_tickers) + chunk_size - 1) // chunk_size

        for idx, i in enumerate(range(0, len(all_tickers), chunk_size)):
            chunk_tickers = all_tickers[i:i + chunk_size]
            placeholders = ",".join(f"'{t}'" for t in chunk_tickers)

            q_snaps = f"""
                SELECT ticker, timestamp, tide_slope, current_slope, vwap_sigma_wave
                FROM engine.channel_snapshots
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
                ORDER BY ticker, timestamp
            """
            q_bars = f"""
                SELECT ticker, time AS timestamp, high, low, close
                FROM market.ohlcv_bars
                WHERE ticker IN ({placeholders}) AND timeframe = '1d'
                ORDER BY ticker, time
            """

            df_snaps = pd.read_sql(q_snaps, conn)
            df_bars = pd.read_sql(q_bars, conn)

            if df_snaps.empty or df_bars.empty:
                continue

            df_snaps['timestamp'] = pd.to_datetime(df_snaps['timestamp'], utc=True)
            df_bars['timestamp'] = pd.to_datetime(df_bars['timestamp'], utc=True)

            df_merged = pd.merge(df_snaps, df_bars, on=["ticker", "timestamp"]).dropna(subset=["close", "high", "low"])
            if df_merged.empty:
                continue

            close_prev = df_merged.groupby("ticker")["close"].shift(1)
            tr = pd.concat([
                df_merged["high"] - df_merged["low"],
                (df_merged["high"] - close_prev).abs(),
                (df_merged["low"] - close_prev).abs()
            ], axis=1).max(axis=1)
            df_merged["atr_raw"] = tr.groupby(df_merged["ticker"]).transform(lambda x: x.ewm(span=14, adjust=False).mean())
            df_merged["atr_pct"] = (df_merged["atr_raw"] / df_merged["close"]).fillna(0.01).clip(lower=0.005)

            matches = {}
            for lvl in ZIGZAG_LEVELS:
                sub_zz = zigzags[lvl][zigzags[lvl]['ticker'].isin(chunk_tickers)]
                matches[lvl] = match_forward_pivots(df_merged, sub_zz)

            for _, r in df_merged.iterrows():
                tk = r["ticker"]
                dt = r["timestamp"].date()
                key_tuple = (tk, dt)

                atr_pct = float(r['atr_pct'])

                t_lbl = _classify_one(float(r['tide_slope']), "T", atr_pct)
                c_lbl = _classify_one(float(r['current_slope']), "C", atr_pct)
                svw_lbl = classify_sigma(float(r['vwap_sigma_wave']))

                k1 = f"{t_lbl}"
                k2 = f"{t_lbl}|{c_lbl}"
                k3 = f"{t_lbl}|{c_lbl}|{svw_lbl}"

                s0_acc.increment_n()
                l1_acc[k1].increment_n()
                l2_acc[k2].increment_n()
                l3_acc[k3].increment_n()

                for lvl in ZIGZAG_LEVELS:
                    m = matches[lvl].get(key_tuple)
                    if m:
                        s0_acc.add_pivot(lvl, m[0], m[1], m[2])
                        l1_acc[k1].add_pivot(lvl, m[0], m[1], m[2])
                        l2_acc[k2].add_pivot(lvl, m[0], m[1], m[2])
                        l3_acc[k3].add_pivot(lvl, m[0], m[1], m[2])

            logger.info(f"  Lote Tide {idx + 1}/{total_chunks} procesado ({len(chunk_tickers)} activos). Acumulado: {s0_acc.n:,} muestras.")

        s0_fmt = s0_acc.format_raw()
        l1_dict = {k: acc.format_raw() for k, acc in l1_acc.items()}
        l2_dict = {k: acc.format_raw() for k, acc in l2_acc.items()}
        l3_dict = {k: acc.format_raw() for k, acc in l3_acc.items()}

        table = {
            "version": "v2_tide_ev_raw_2026",
            "friction_bps": DEFAULT_FRICTION_BPS,
            "n_samples_total": int(s0_acc.n),
            "l0_global": s0_fmt,
            "l1_macro": l1_dict,
            "l2_mid_macro": l2_dict,
            "l3_full_state": l3_dict,
        }

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(table, f, indent=2)

        logger.info(f"✅ ¡Censo empírico bruto Tide EV completado! Guardado en {OUTPUT_PATH}")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    main()
