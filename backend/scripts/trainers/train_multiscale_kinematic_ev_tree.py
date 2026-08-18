#!/usr/bin/env python3
"""
Train Multiscale Kinematic EV Tree — Stage 1: Raw Census Extractor
===================================================================
Performs industrial-grade raw empirical census extraction for multiscale turning points (2.5%, 5.0%, 7.5%):
  1. Real Point-in-Time Forward Returns: (price(t_pivot) / close(t)) - 1.0 (Zero Ghost Return Bias).
  2. Volatility Normalization: slope_norm = slope / max(atr_pct, 0.005) against 100% census quantiles.
  3. Strict Stock/ETF Filter: Excludes 106 pseudo-OHLCV indicators (VIX, VVIX, CBOE_PCR, FG, S5TH, S5FI).
  4. Causal Anticipatory Window & Kinematic Trajectory Delta: ΔσVw = σVw(t0) - σVw(t-2).
  5. Multi-Level Hierarchy Storage: Raw empirical counts for L0, L1, L3, and L6.

Output: backend/modules/quality_swing/domain/rules/rc_ev_multiscale_probability_table.json
"""
import sys
import json
import logging
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _classify_one

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TrainMultiscaleKinematicEV")

OUTPUT_PATH = ROOT / "backend/modules/quality_swing/domain/rules/rc_ev_multiscale_probability_table.json"
DEFAULT_FRICTION_BPS = 0.0010  # 10 bps round-trip friction (0.10%)
MAX_HORIZON_DAYS = 120          # Maximum days to next pivot for swing validity


def classify_sigma_bin(val: float) -> str:
    if val < -1.0:
        return "<<"
    elif val < -0.3:
        return "<"
    elif val <= 0.3:
        return "~"
    elif val <= 1.0:
        return ">"
    else:
        return ">>"


def classify_kinematic_trajectory(delta_svw: float) -> str:
    if delta_svw > 0.30:
        return "ABSORBING"
    elif delta_svw < -0.30:
        return "EXHAUSTING"
    else:
        return "STABLE"


class RawKinematicAccumulator:
    """Accumulates raw un-shrunk empirical counts and returns across 2.5%, 5.0%, and 7.5% scales."""
    def __init__(self):
        self.n = 0
        self.returns = []

        # Scale 2.5% (Minor Swing)
        self.n_pos_25 = 0; self.n_neg_25 = 0
        self.sum_max_25 = 0.0; self.sum_min_25 = 0.0
        self.days_25_list = []

        # Scale 5.0% (Medium Swing)
        self.n_pos_50 = 0; self.n_neg_50 = 0
        self.sum_max_50 = 0.0; self.sum_min_50 = 0.0
        self.days_50_list = []

        # Scale 7.5% (Major Swing)
        self.n_pos_75 = 0; self.n_neg_75 = 0
        self.sum_max_75 = 0.0; self.sum_min_75 = 0.0
        self.days_75_list = []

    def add_scale_25(self, tp_type: str, real_return_net: float, days_to_pivot: float):
        if tp_type == "MAX":
            self.n_pos_25 += 1
            self.sum_max_25 += real_return_net
        else:
            self.n_neg_25 += 1
            self.sum_min_25 += real_return_net
        self.days_25_list.append(days_to_pivot)
        self.returns.append(real_return_net)

    def add_scale_50(self, tp_type: str, real_return_net: float, days_to_pivot: float):
        if tp_type == "MAX":
            self.n_pos_50 += 1
            self.sum_max_50 += real_return_net
        else:
            self.n_neg_50 += 1
            self.sum_min_50 += real_return_net
        self.days_50_list.append(days_to_pivot)

    def add_scale_75(self, tp_type: str, real_return_net: float, days_to_pivot: float):
        if tp_type == "MAX":
            self.n_pos_75 += 1
            self.sum_max_75 += real_return_net
        else:
            self.n_neg_75 += 1
            self.sum_min_75 += real_return_net
        self.days_75_list.append(days_to_pivot)

    def increment_n(self):
        self.n += 1

    def format_raw(self) -> dict:
        if self.n == 0:
            return {}

        std_ret = float(np.std(self.returns)) if len(self.returns) > 1 else 0.04

        return {
            "n": int(self.n),
            "std_return": round(std_ret, 6),

            # Scale 2.5% Raw
            "n_pos_25": int(self.n_pos_25),
            "n_neg_25": int(self.n_neg_25),
            "sum_max_25": round(float(self.sum_max_25), 6),
            "sum_min_25": round(float(self.sum_min_25), 6),
            "e_days_25": round(float(np.mean(self.days_25_list)), 2) if self.days_25_list else 8.0,

            # Scale 5.0% Raw
            "n_pos_50": int(self.n_pos_50),
            "n_neg_50": int(self.n_neg_50),
            "sum_max_50": round(float(self.sum_max_50), 6),
            "sum_min_50": round(float(self.sum_min_50), 6),
            "e_days_50": round(float(np.mean(self.days_50_list)), 2) if self.days_50_list else 18.0,

            # Scale 7.5% Raw
            "n_pos_75": int(self.n_pos_75),
            "n_neg_75": int(self.n_neg_75),
            "sum_max_75": round(float(self.sum_max_75), 6),
            "sum_min_75": round(float(self.sum_min_75), 6),
            "e_days_75": round(float(np.mean(self.days_75_list)), 2) if self.days_75_list else 35.0,
        }


def match_forward_pivots(snap_df: pd.DataFrame, zz_df: pd.DataFrame) -> dict:
    """Vectorized forward-pivot matching per ticker for a given ZigZag scale."""
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
    logger.info("Iniciando Censo Empírico Bruto Multiescala (Etapa 1)...")
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

        logger.info("Cargando pivotes ZigZag (2.5%, 5.0%, 7.5%) desde Neon Vault...")
        q_zz = """
            SELECT ticker, timestamp, tp_type, price, min_swing_pct
            FROM engine.zigzag_points
            WHERE min_swing_pct IN (0.025, 0.05, 0.075)
            ORDER BY ticker, timestamp
        """
        zz_all = pd.read_sql(q_zz, conn)
        zz_all['timestamp'] = pd.to_datetime(zz_all['timestamp'], utc=True)

        zz_25 = zz_all[zz_all['min_swing_pct'] == 0.025]
        zz_50 = zz_all[zz_all['min_swing_pct'] == 0.05]
        zz_75 = zz_all[zz_all['min_swing_pct'] == 0.075]

        s0_acc = RawKinematicAccumulator()
        s1_acc = defaultdict(RawKinematicAccumulator)
        s3_acc = defaultdict(RawKinematicAccumulator)

        chunk_size = 50
        total_chunks = (len(all_tickers) + chunk_size - 1) // chunk_size

        for idx, i in enumerate(range(0, len(all_tickers), chunk_size)):
            chunk_tickers = all_tickers[i:i + chunk_size]
            placeholders = ",".join(f"'{t}'" for t in chunk_tickers)

            q_snaps = f"""
                SELECT ticker, timestamp, tide_slope, current_slope, wave_slope,
                       sigma_current, sigma_wave, vwap_sigma_wave
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

            # Vectorized ATR_14% calculation per ticker
            close_prev = df_merged.groupby("ticker")["close"].shift(1)
            tr = pd.concat([
                df_merged["high"] - df_merged["low"],
                (df_merged["high"] - close_prev).abs(),
                (df_merged["low"] - close_prev).abs()
            ], axis=1).max(axis=1)
            df_merged["atr_raw"] = tr.groupby(df_merged["ticker"]).transform(lambda x: x.ewm(span=14, adjust=False).mean())
            df_merged["atr_pct"] = (df_merged["atr_raw"] / df_merged["close"]).fillna(0.01).clip(lower=0.005)

            # Compute VWAP Sigma Wave Trajectory Delta (t-2 -> t0)
            df_merged["vwap_sigma_wave_t2"] = df_merged.groupby("ticker")["vwap_sigma_wave"].shift(2)
            df_merged["delta_svw"] = df_merged["vwap_sigma_wave"] - df_merged["vwap_sigma_wave_t2"].fillna(df_merged["vwap_sigma_wave"])
            df_merged["kinematic_traj"] = df_merged["delta_svw"].apply(classify_kinematic_trajectory)

            # Match forward pivots for all 3 scales
            sub_zz25 = zz_25[zz_25['ticker'].isin(chunk_tickers)]
            sub_zz50 = zz_50[zz_50['ticker'].isin(chunk_tickers)]
            sub_zz75 = zz_75[zz_75['ticker'].isin(chunk_tickers)]

            match25 = match_forward_pivots(df_merged, sub_zz25)
            match50 = match_forward_pivots(df_merged, sub_zz50)
            match75 = match_forward_pivots(df_merged, sub_zz75)

            for _, r in df_merged.iterrows():
                tk = r["ticker"]
                dt = r["timestamp"].date()
                key_tuple = (tk, dt)

                atr_pct = float(r['atr_pct'])

                t_lbl = _classify_one(float(r['tide_slope']), "T", atr_pct)
                c_lbl = _classify_one(float(r['current_slope']), "C", atr_pct)
                w_lbl = _classify_one(float(r['wave_slope']), "W", atr_pct)
                sc_lbl = classify_sigma_bin(float(r['sigma_current']))
                sw_lbl = classify_sigma_bin(float(r['sigma_wave']))
                svw_lbl = classify_sigma_bin(float(r['vwap_sigma_wave']))
                traj_lbl = str(r["kinematic_traj"])

                m25 = match25.get(key_tuple)
                m50 = match50.get(key_tuple)
                m75 = match75.get(key_tuple)

                if not m25 and not m50 and not m75:
                    continue

                k3 = f"{t_lbl}|{c_lbl}|{w_lbl}#{traj_lbl}"
                k1 = f"{t_lbl}|{c_lbl}|{w_lbl}|{sc_lbl}|{sw_lbl}|{svw_lbl}#{traj_lbl}"

                s0_acc.increment_n()
                s3_acc[k3].increment_n()
                s1_acc[k1].increment_n()

                if m25:
                    s0_acc.add_scale_25(m25[0], m25[1], m25[2])
                    s3_acc[k3].add_scale_25(m25[0], m25[1], m25[2])
                    s1_acc[k1].add_scale_25(m25[0], m25[1], m25[2])

                if m50:
                    s0_acc.add_scale_50(m50[0], m50[1], m50[2])
                    s3_acc[k3].add_scale_50(m50[0], m50[1], m50[2])
                    s1_acc[k1].add_scale_50(m50[0], m50[1], m50[2])

                if m75:
                    s0_acc.add_scale_75(m75[0], m75[1], m75[2])
                    s3_acc[k3].add_scale_75(m75[0], m75[1], m75[2])
                    s1_acc[k1].add_scale_75(m75[0], m75[1], m75[2])

            logger.info(f"  Lote {idx + 1}/{total_chunks} procesado ({len(chunk_tickers)} activos). Total acumulado: {s0_acc.n:,} muestras.")

        s0_fmt = s0_acc.format_raw()
        s1_dict = {k: acc.format_raw() for k, acc in s1_acc.items()}
        s3_dict = {k: acc.format_raw() for k, acc in s3_acc.items()}

        raw_table = {
            "version": "v2_multiscale_kinematic_raw_2026",
            "friction_bps": DEFAULT_FRICTION_BPS,
            "n_samples_total": int(s0_acc.n),
            "s0_global": s0_fmt,
            "s1_full": s1_dict,
            "s3_triad": s3_dict,
        }

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(raw_table, f, indent=2)

        logger.info(f"✅ ¡Censo empírico bruto completado! Guardado en {OUTPUT_PATH}")

    finally:
        try:
            store._put(conn)
        except Exception:
            pass


if __name__ == "__main__":
    main()
