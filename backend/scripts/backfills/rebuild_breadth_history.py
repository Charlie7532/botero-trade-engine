#!/usr/bin/env python3
"""
Rebuild Breadth History — provider-parity recompute of breadth-derived indicators
=================================================================================
Recomputes the FULL history of the indicators the daily vault providers write one
bar at a time, using the SAME semantics as those providers, from the constituent
bars currently in the Vault. Intended to run after a constituent reload.

Parity with the providers (one bar per SPY session date d):
  - Constituents: asset_type='STOCK', update_source='vault_ohlcv_bars', and
      global (S5*, SV5*): 'SP500' in index_membership
      sector (S5_*, SV5_*, S5CAP_*, VBI_*): 'SP500' or 'QQQ' in index_membership, sector not null.
      QQQ (S5_QQQ_*, SV5_QQQ_*): 'QQQ' in index_membership, sector not null (QQQ's own list).
  - Window: bars with time in (d - N calendar days, d], N=300 (VBI: 50) — provider `days=` lookback.
  - S5 / S5_{ETF} / S5CAP:  close[-1] > mean(last k closes), ticker counted if it has >= k bars
      in the window (macro_trend_calculator.calculate_breadth; cap version weights by mcap_cache.json).
  - SV5 / SV5_{ETF}: positive-volume bars only; fast MA (EMA5 seeded by SMA / SMA20 / SMA50) >
      slow SMA (20/50/200), counted if >= slow bars in window (volume_breadth_calculator).
  - VBI_{ETF}: mean of clip(z(last vol vs last 20 positive vols, ddof=0), +-3), >= 20 bars in window.
  - volume column = n_constituents (tickers with >= 1 bar in the window); sectors need >= 10.
  - BSI = S5TW (breadth_provider writes it), SV5_TURBULENCE = sample std of the last 10 daily
      changes of SV5TW (sv5_turbulence_provider), volume 0.
  - CREDIT_RATIO / ROTATION_INDEX: backfill_synthetic_indicators (depend on reloaded ETF closes).
Inherited convention (the former backfill_breadth_history, now removed, which produced the original
history): global S5/SV5 bars are emitted only when >= 100 tickers are counted.

Write: per indicator ticker, one transaction: DELETE its 1d rows, INSERT the recomputed series.

Usage:
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfills/rebuild_breadth_history.py [--dry-run]
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values

root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS, BREADTH_MA_LENGTHS, VOLUME_BREADTH_MA_CONFIG, canonicalize,
    SECTOR_BREADTH_TICKERS, QQQ_VOLUME_BREADTH_TICKERS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rebuild_breadth_history")

WINDOW = "300D"
VBI_WINDOW = "50D"
GLOBAL_MIN_N = 100
SECTOR_MIN_N = 10
TURB_WINDOW = 10
MCAP_CACHE = root_dir / "backend" / "daemons" / "vault_providers" / "mcap_cache.json"
SUFFIX = {"structural": "TH", "intermediate": "FI", "tactical": "TW"}
_SECTOR_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}


def load_constituents(store):
    conn = store._conn()
    try:
        q = """
            SELECT b.ticker, m.sector, ('SP500' = ANY(m.index_membership)) AS sp500,
                   ('QQQ' = ANY(m.index_membership)) AS qqq,
                   b.time::date AS d, b.close, b.volume
            FROM market.ohlcv_bars b
            JOIN market.ticker_metadata m ON b.ticker = m.ticker
            WHERE b.timeframe = '1d' AND m.asset_type = 'STOCK'
              AND m.update_source = 'vault_ohlcv_bars'
              AND ('SP500' = ANY(m.index_membership) OR 'QQQ' = ANY(m.index_membership))
        """
        df = pd.read_sql(q, store.engine)
    finally:
        store._put(conn)
    df["d"] = pd.to_datetime(df["d"])
    return df


def calendar(store, raw: pd.DataFrame):
    """SPY session dates (the providers' effective dates); before SPY existed (1993), dates
    on which at least SECTOR_MIN_N constituents have a bar."""
    spy = store.load_bars("SPY", "1d")
    idx = pd.DatetimeIndex(spy.index)
    idx = (idx.tz_convert(None) if idx.tz is not None else idx).normalize()
    per_day = raw.groupby("d").size()
    pre = per_day[(per_day.index < idx.min()) & (per_day >= SECTOR_MIN_N)].index
    return pd.DatetimeIndex(pre).union(idx)


def _window_count(obs: pd.DataFrame, window: str) -> pd.DataFrame:
    """Count of observations per ticker in (d - window, d], on the union date index."""
    return obs.astype(float).rolling(window).sum()


def price_breadth_frames(close_w: pd.DataFrame):
    """For each k: above[k] (bool, ffilled) and valid[k] (>= k bars in window), plus has_any."""
    obs = close_w.notna()
    cnt = _window_count(obs, WINDOW)
    above, valid = {}, {}
    for key, k in BREADTH_MA_LENGTHS.items():
        sma = pd.DataFrame({t: close_w[t].dropna().rolling(k).mean() for t in close_w.columns})
        sma = sma.reindex(close_w.index)
        a = ((close_w > sma) & (sma > 0)).astype(float)
        a = a.where(obs).ffill()            # stale close semantics: last bar in window
        above[key] = a.fillna(0.0) > 0.5
        valid[key] = (cnt >= k) & sma.where(obs).ffill().notna()
    has_any = cnt >= 1
    return above, valid, has_any


def volume_breadth_frames(vol_w: pd.DataFrame):
    obs = vol_w.notna()
    cnt = _window_count(obs, WINDOW)
    flag, valid = {}, {}
    for key, cfg in VOLUME_BREADTH_MA_CONFIG.items():
        fast_l, slow_l = cfg["fast"], cfg["slow"]
        f_cols, s_cols = {}, {}
        for t in vol_w.columns:
            v = vol_w[t].dropna()
            if cfg["fast_type"] == "ema":
                # EMA seeded with the SMA of the first `fast_l` values, alpha = 2/(span+1)
                seed = v.iloc[:fast_l].mean() if len(v) >= fast_l else np.nan
                arr = v.to_numpy()
                out = np.full(len(arr), np.nan)
                if len(arr) >= fast_l:
                    a = 2.0 / (fast_l + 1)
                    e = seed
                    out[fast_l - 1] = e
                    for i in range(fast_l, len(arr)):
                        e = a * arr[i] + (1 - a) * e
                        out[i] = e
                f_cols[t] = pd.Series(out, index=v.index)
            else:
                f_cols[t] = v.rolling(fast_l).mean()
            s_cols[t] = v.rolling(slow_l).mean()
        fast = pd.DataFrame(f_cols).reindex(vol_w.index)
        slow = pd.DataFrame(s_cols).reindex(vol_w.index)
        f = ((fast > slow) & (slow > 0)).astype(float)
        flag[key] = f.where(obs).ffill().fillna(0.0) > 0.5
        valid[key] = (cnt >= slow_l) & slow.where(obs).ffill().gt(0)
    has_any = cnt >= 1
    return flag, valid, has_any


def vbi_frame(vol_w: pd.DataFrame):
    obs = vol_w.notna()
    cnt = _window_count(obs, VBI_WINDOW)
    z_cols = {}
    for t in vol_w.columns:
        v = vol_w[t].dropna()
        m = v.rolling(20).mean()
        s = v.rolling(20).std(ddof=0)
        z = ((v - m) / s).where(s > 0).clip(-3.0, 3.0)
        z_cols[t] = z
    z = pd.DataFrame(z_cols).reindex(vol_w.index).where(obs).ffill()
    z = z.where(cnt >= 20)
    return z, cnt >= 1


def series_rows(ticker, values: pd.Series, n: pd.Series):
    out = []
    for d, val in values.dropna().items():
        ts = pd.Timestamp(d).tz_localize("UTC")
        out.append((ts.to_pydatetime(), ticker, "1d", float(val), float(val), float(val), float(val), int(n.loc[d])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dump", type=str, help="Save recomputed series to this parquet file")
    args = ap.parse_args()

    store = TimescaleDataStore()
    raw = load_constituents(store)
    cal = calendar(store, raw)
    logger.info(f"Constituent rows: {len(raw):,}, tickers: {raw.ticker.nunique()}, calendar: {len(cal):,} SPY dates")

    meta = raw.drop_duplicates("ticker").set_index("ticker")
    close_w = raw.pivot_table(index="d", columns="ticker", values="close", aggfunc="last")
    vol_w = raw[raw.volume > 0].pivot_table(index="d", columns="ticker", values="volume", aggfunc="last")
    union = close_w.index.union(vol_w.index).union(cal)
    close_w = close_w.reindex(union)
    vol_w = vol_w.reindex(union)
    mcap = json.loads(MCAP_CACHE.read_text()) if MCAP_CACHE.exists() else {}

    logger.info("Computing price breadth frames...")
    above, pvalid, p_any = price_breadth_frames(close_w)
    logger.info("Computing volume breadth frames...")
    vflag, vvalid, v_any = volume_breadth_frames(vol_w)
    logger.info("Computing VBI frame...")
    vbi_z, vbi_any = vbi_frame(vol_w)

    series = {}   # ticker -> (values, n)
    sp500 = [t for t in close_w.columns if bool(meta.loc[t, "sp500"])]

    # Global S5 / SV5
    n_p = p_any[sp500].sum(axis=1)
    for key, sfx in SUFFIX.items():
        tot = pvalid[key][sp500].sum(axis=1)
        pct = ((above[key][sp500] & pvalid[key][sp500]).sum(axis=1) / tot * 100).round(1)
        series[f"S5{sfx}"] = (pct.where(tot >= GLOBAL_MIN_N).reindex(cal), n_p.reindex(cal))
    series["BSI"] = series["S5TW"]
    sp500_v = [t for t in vol_w.columns if t in sp500]
    n_v = v_any[sp500_v].sum(axis=1)
    for key, sfx in SUFFIX.items():
        tot = vvalid[key][sp500_v].sum(axis=1)
        pct = ((vflag[key][sp500_v] & vvalid[key][sp500_v]).sum(axis=1) / tot * 100).round(1)
        series[f"SV5{sfx}"] = (pct.where(tot >= GLOBAL_MIN_N).reindex(cal), n_v.reindex(cal))

    # Sectors
    sector_of = {t: _SECTOR_TO_ETF.get(canonicalize(s)) for t, s in meta["sector"].items() if s}
    for etf in SECTOR_ETFS:
        tick = [t for t, e in sector_of.items() if e == etf and t in close_w.columns]
        tick_v = [t for t in tick if t in vol_w.columns]
        if not tick:
            continue
        n_s = p_any[tick].sum(axis=1)
        w = pd.Series({t: mcap.get(t, 10_000_000_000) for t in tick})
        for key, sfx in SUFFIX.items():
            v = pvalid[key][tick]
            tot = v.sum(axis=1)
            pct = ((above[key][tick] & v).sum(axis=1) / tot * 100).round(1)
            series[f"S5_{etf}_{sfx}"] = (pct.where((n_s >= SECTOR_MIN_N) & (tot > 0)).reindex(cal), n_s.reindex(cal))
            wt = (v * w).sum(axis=1)
            cap = ((above[key][tick] & v) * w).sum(axis=1) / wt * 100
            series[f"S5CAP_{etf}_{sfx}"] = (cap.round(1).where((n_s >= SECTOR_MIN_N) & (wt > 0)).reindex(cal), n_s.reindex(cal))
        if tick_v:
            n_sv = v_any[tick_v].sum(axis=1)
            for key, sfx in SUFFIX.items():
                v = vvalid[key][tick_v]
                tot = v.sum(axis=1)
                pct = ((vflag[key][tick_v] & v).sum(axis=1) / tot * 100).round(1)
                series[f"SV5_{etf}_{sfx}"] = (pct.where((n_sv >= SECTOR_MIN_N) & (tot > 0)).reindex(cal), n_sv.reindex(cal))
            n_vbi = vbi_any[tick_v].sum(axis=1)
            vbi = vbi_z[tick_v].mean(axis=1).round(2)
            series[f"VBI_{etf}"] = (vbi.where(n_vbi >= SECTOR_MIN_N).reindex(cal), n_vbi.reindex(cal))

    # QQQ (own constituent list) — same frames as the sectors
    qqq = [t for t in close_w.columns if bool(meta.loc[t, "qqq"]) and meta.loc[t, "sector"]]
    qqq_v = [t for t in qqq if t in vol_w.columns]
    n_q = p_any[qqq].sum(axis=1)
    for key, sfx in SUFFIX.items():
        v = pvalid[key][qqq]
        tot = v.sum(axis=1)
        pct = ((above[key][qqq] & v).sum(axis=1) / tot * 100).round(1)
        series[SECTOR_BREADTH_TICKERS["QQQ"][key]] = (pct.where((n_q >= SECTOR_MIN_N) & (tot > 0)).reindex(cal), n_q.reindex(cal))
    n_qv = v_any[qqq_v].sum(axis=1)
    for key, sfx in SUFFIX.items():
        v = vvalid[key][qqq_v]
        tot = v.sum(axis=1)
        pct = ((vflag[key][qqq_v] & v).sum(axis=1) / tot * 100).round(1)
        series[QQQ_VOLUME_BREADTH_TICKERS[key]] = (pct.where((n_qv >= SECTOR_MIN_N) & (tot > 0)).reindex(cal), n_qv.reindex(cal))

    # SV5_TURBULENCE from the recomputed SV5TW bar series
    sv5tw = series["SV5TW"][0].dropna()
    turb = sv5tw.diff().rolling(TURB_WINDOW).std(ddof=1)
    series["SV5_TURBULENCE"] = (turb, pd.Series(0, index=turb.index))

    for t, (vals, _) in sorted(series.items()):
        v = vals.dropna()
        if len(v):
            logger.info(f"  {t:18s} {len(v):6,} bars {v.index.min().date()}..{v.index.max().date()} last={v.iloc[-1]}")

    if args.dump:
        pd.DataFrame({t: v for t, (v, _) in series.items()}).to_parquet(args.dump)
        logger.info(f"Series dumped to {args.dump}")

    if args.dry_run:
        logger.info("DRY RUN — no DB writes")
        return

    for t, (vals, n) in sorted(series.items()):
        rows = series_rows(t, vals, n.reindex(vals.index).fillna(0))
        conn = store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d'", (t,))
                deleted = cur.rowcount
                execute_values(cur, """INSERT INTO market.ohlcv_bars
                    (time, ticker, timeframe, open, high, low, close, volume) VALUES %s""", rows, page_size=2000)
            conn.commit()
            logger.info(f"  {t}: deleted {deleted:,}, inserted {len(rows):,}")
        except Exception:
            conn.rollback()
            raise
        finally:
            store._put(conn)

    # Synthetic stations depending on reloaded ETF closes
    from backend.scripts.backfills.backfill_synthetic_indicators import backfill_credit_ratio, backfill_rotation_index
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM market.ohlcv_bars WHERE ticker IN ('CREDIT_RATIO','ROTATION_INDEX') AND timeframe = '1d'")
        conn.commit()
    finally:
        store._put(conn)
    logger.info(f"  CREDIT_RATIO: {backfill_credit_ratio(store)} bars")
    logger.info(f"  ROTATION_INDEX: {backfill_rotation_index(store)} bars")

    from backend.modules.shared.infrastructure.redis_cache import get_redis_cache
    cache = get_redis_cache()
    if cache:
        for t in list(series) + ["CREDIT_RATIO", "ROTATION_INDEX"]:
            cache.invalidate(f"bars:{t}:1d")
    store.close()
    logger.info("REBUILD_BREADTH_DONE")


if __name__ == "__main__":
    main()
