#!/usr/bin/env python3
"""
TickerDataHealer v2 — per-bar verification & repair of market.ohlcv_bars
=========================================================================
SCRATCH / PROPOSAL (Rule 22). Destination once approved: backend/scripts/backfills/
(Rule 10/13: only scripts/daemons may call external APIs).

Policy (from audit 2026-10-03):
  1. Operate PER BAR. No automatic temporal truncation. A cut is only executed if the
     Architect passes `truncate_before` explicitly; `propose_boundaries()` only reports evidence.
     Temporal proxy retired: "pre-2000" is NOT "pre-tape". The pre-tape boundary is strictly per-ticker
     and detected dynamically by measurement (% bars with volume > 0 and annual density), never by an arbitrary fixed year.
  2. Source order: Yahoo (auto_adjust=True, the Vault convention) -> Alpaca (adjustment=ALL, feed=SIP).
     Alpaca RAW is forbidden: its prices are not on the Vault scale (HUBB RAW/Vault = 1.09, ALL = 1.0000).
  3. A candidate bar is accepted only if:
       a) it is clean itself (volume>0, high>low, O/C inside [L,H]);
       b) IDENTITY + SCALE gate: on the >=MIN_ANCHORS clean bars nearest to the date where both
          Vault and source are clean, close_src/close_vault is stable (max/min <= MAX_RATIO_SPREAD).
          This rejects different entities under the same symbol (SW: Alpaca ALL/Vault p05=0.82, p95=2.44)
          and absorbs the Vault's mixed adjustment epochs (local ratio, not global);
       c) for close-only bars (C2) the rescaled candidate close matches the Vault close within 1%.
     Accepted prices are rescaled to the LOCAL Vault scale; volume rescaled by the local volume ratio.
  4. Bar classes (strict O==H==L==C used for fabrication, plus volume and physics):
       C1 placeholder : O=H=L=C and volume == 0 (uncomputable in VWAP -> NULL levels/sigmas)
       C2 close-only  : O=H=L=C and volume  > 0 (preserved intact, computed normally: volume>0 ->
                        strictly positive VWAP denominator; typical=(H+L+C)/3=close -> exact VWAP;
                        regression fits transacted close. zigzag_canonical uses H/L, so a pivot on
                        a C2 bar carries close, not the true extreme.
                        CARENCIA DECLARATION: C2 provides no intraday range; any future feature
                        based on High - Low must explicitly exclude C2 bars).
       C3 vol0+range  : volume == 0 and H > L     (range real, volume missing)
       C4 invalid     : O or C outside [L,H] by a relative excursion > C4_EPS (1e-6), or H < L.
                        Excursions <= 1e-6 are float comparison noise -> CLEAN, never overwritten.
                        (Measured 2026-10-04: 2,429 close-side noise bars at ~1e-16; 603 real
                        open-side bars, all 2026, = partial intraday bars persisted as closes.)
  5. Vault formats: Rule 18 midnight UTC, float64 OHLC, int64 volume, dedup keep=last, sorted.
     Commit reuses wipe_reload_cascade.atomic_swap_bars (DELETE bars+snapshots+zigzag, INSERT, COMMIT
     in one transaction), then rebuild_snapshots / rebuild_zigzag / rebuild_observer, then Redis
     invalidate_pattern("bars:{T}:*").
"""
import os
import sys
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

root_dir = Path("/root/botero-trade")
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger("TickerDataHealer")

COLS = ["open", "high", "low", "close", "volume"]
MIN_ANCHORS = 10          # clean overlapping bars required around each date
MAX_RATIO_SPREAD = 1.02   # max/min of local close ratio -> same entity, same scale
C2_CLOSE_TOL = 0.01       # close-only bar must match within 1%
SCALE_BREAK = 3.0         # day-over-day close ratio flagged as scale break
C4_EPS = 1e-6             # float-noise tolerance outside [L,H]. Measured 2026-10-04: noise max 2.05e-16, real min 9.58e-6 (empty gap between)


@dataclass
class HealReport:
    ticker: str
    bars: int = 0
    classes: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)       # per source: covered / clean / accepted / rejected_gate
    repaired: int = 0
    unrecovered: dict = field(default_factory=dict)
    scale_breaks: list = field(default_factory=list)
    boundary_evidence: dict = field(default_factory=dict)
    truncated: int = 0
    committed: bool = False


class TickerDataHealer:

    def __init__(self, store: Optional[TimescaleDataStore] = None):
        self.store = store or TimescaleDataStore()
        self._alpaca = None

    # ── Formats ───────────────────────────────────────────────────────
    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Rule 18: midnight UTC index, float64 OHLC, int64 volume, dedup keep=last, sorted."""
        if df.empty:
            return pd.DataFrame(columns=COLS)
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        idx = pd.to_datetime(df.index)
        idx = idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")
        df.index = idx.normalize()
        df.index.name = "time"
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df.dropna(subset=["open", "high", "low", "close"])
        out = df[["open", "high", "low", "close"]].astype("float64")
        out["volume"] = df["volume"].fillna(0).astype("int64")
        return out

    @staticmethod
    def classify(df: pd.DataFrame) -> pd.Series:
        o, h, l, c, v = (df[k] for k in COLS)
        hi, lo = h * (1 + C4_EPS), l * (1 - C4_EPS)
        invalid = (o > hi) | (o < lo) | (c > hi) | (c < lo) | (h < l)
        fab = (o == h) & (h == l) & (l == c)
        cls = pd.Series("CLEAN", index=df.index)
        cls[(v == 0) & (h > l) & ~invalid] = "C3"
        cls[fab & (v > 0)] = "C2"
        cls[fab & (v == 0)] = "C1"
        cls[invalid] = "C4"
        return cls

    # ── Sources ───────────────────────────────────────────────────────
    def load_vault(self, ticker: str) -> pd.DataFrame:
        conn = self.store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT time, open, high, low, close, volume FROM market.ohlcv_bars "
                    "WHERE ticker = %s AND timeframe = '1d' ORDER BY time", (ticker,))
                rows = cur.fetchall()
        finally:
            self.store._put(conn)
        return self.normalize(pd.DataFrame(rows, columns=["time"] + COLS).set_index("time"))

    def fetch_yahoo(self, ticker: str) -> pd.DataFrame:
        import yfinance as yf
        from backend.daemons.vault_providers.ohlcv_provider import SOURCE_TICKER_MAP
        sym = SOURCE_TICKER_MAP.get(ticker, ticker.replace(".", "-"))
        df = yf.download(sym, period="max", interval="1d", auto_adjust=True, progress=False)
        if df is None or df.empty:
            return pd.DataFrame(columns=COLS)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(sym, level=1, axis=1)
        return self.normalize(df)

    def fetch_alpaca(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import Adjustment, DataFeed
        if self._alpaca is None:
            self._alpaca = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
        req = StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Day, start=start, end=end,
                               adjustment=Adjustment.ALL, feed=DataFeed.SIP)
        data = self._alpaca.get_stock_bars(req).data.get(ticker, [])
        if not data:
            return pd.DataFrame(columns=COLS)
        df = pd.DataFrame([{"time": b.timestamp, "open": b.open, "high": b.high, "low": b.low,
                            "close": b.close, "volume": b.volume} for b in data]).set_index("time")
        return self.normalize(df)  # Alpaca stamps 04:00/05:00 UTC (= 00:00 ET) -> same date at midnight UTC

    # ── Gate ──────────────────────────────────────────────────────────
    @staticmethod
    def _local_ratios(vault, vcls, src):
        """For every date, local close/volume ratio src/vault over nearest MIN_ANCHORS clean anchors."""
        scls = TickerDataHealer.classify(src)
        anchors = vault.index[vcls == "CLEAN"].intersection(src.index[scls == "CLEAN"])
        if len(anchors) < MIN_ANCHORS:
            return None
        pr = (src.loc[anchors, "close"] / vault.loc[anchors, "close"]).values
        vr = (src.loc[anchors, "volume"] / vault.loc[anchors, "volume"].replace(0, np.nan)).values
        return anchors, pr, vr

    def _try_source(self, name, vault, vcls, src, targets, rep, healed):
        stats = {"covered": 0, "clean": 0, "accepted": 0, "rejected_gate": 0, "rejected_c2_close": 0}
        rep.sources[name] = stats
        if src.empty:
            return
        lr = self._local_ratios(vault, vcls, src)
        scls = self.classify(src)
        cand = targets.intersection(src.index)
        stats["covered"] = len(cand)
        cand = cand[scls.loc[cand] == "CLEAN"]
        stats["clean"] = len(cand)
        if lr is None or len(cand) == 0:
            stats["rejected_gate"] = len(cand)
            return
        anchors, pr, vr = lr
        apos = anchors.values
        for d in cand:
            i = np.searchsorted(apos, d.to_datetime64())
            lo, hi = max(0, i - MIN_ANCHORS // 2), min(len(apos), i + MIN_ANCHORS // 2)
            while hi - lo < MIN_ANCHORS and (lo > 0 or hi < len(apos)):
                lo, hi = max(0, lo - 1), min(len(apos), hi + 1)
            p = pr[lo:hi]
            if len(p) < MIN_ANCHORS or p.max() / p.min() > MAX_RATIO_SPREAD:
                stats["rejected_gate"] += 1
                continue
            k = float(np.median(p))
            kv = float(np.nanmedian(vr[lo:hi])) if np.isfinite(vr[lo:hi]).any() else 1.0
            row = src.loc[d]
            if vcls.loc[d] == "C2" and abs(row["close"] / k / vault.loc[d, "close"] - 1) > C2_CLOSE_TOL:
                stats["rejected_c2_close"] += 1
                continue
            healed.loc[d, ["open", "high", "low", "close"]] = row[["open", "high", "low", "close"]].values / k
            healed.loc[d, "volume"] = int(round(row["volume"] / kv))
            stats["accepted"] += 1
        targets.drop  # no-op; caller recomputes remaining targets

    # ── Evidence only (never auto-applied) ────────────────────────────
    def propose_boundaries(self, vault, vcls, rep, alpaca_first: Optional[pd.Timestamp]):
        r = vault["close"] / vault["close"].shift(1)
        for d in r[(r > SCALE_BREAK) | (r < 1 / SCALE_BREAK)].index:
            i = vault.index.get_loc(d)
            rep.scale_breaks.append({"date": str(d.date()), "prev": round(vault["close"].iloc[i - 1], 6),
                                     "now": round(vault["close"].iloc[i], 6), "x": round(r.loc[d], 3),
                                     "prev_class": vcls.iloc[i - 1], "class": vcls.iloc[i]})
        fab = vcls.isin(["C1", "C2"])
        if alpaca_first is not None and alpaca_first > vault.index.min():
            pre, post = fab[fab.index < alpaca_first], fab[fab.index >= alpaca_first]
            rep.boundary_evidence = {
                "alpaca_first_bar": str(alpaca_first.date()),
                "fab_pct_before": round(100 * pre.mean(), 1) if len(pre) else None,
                "fab_pct_after": round(100 * post.mean(), 1) if len(post) else None,
                "bars_before": int(len(pre)),
            }

    # ── Orchestration ─────────────────────────────────────────────────
    def heal(self, ticker: str, dry_run: bool = True,
             truncate_before: Optional[str] = None, force: bool = False) -> tuple[pd.DataFrame, HealReport]:
        ticker = ticker.upper()
        vault = self.load_vault(ticker)
        rep = HealReport(ticker=ticker, bars=len(vault))
        if vault.empty:
            return vault, rep
        vcls = self.classify(vault)
        rep.classes = vcls.value_counts().to_dict()
        healed = vault.copy()
        targets = vault.index[vcls != "CLEAN"]

        # 1) Yahoo first (Vault convention)
        try:
            y = self.fetch_yahoo(ticker)
        except Exception as e:
            logger.warning(f"[{ticker}] Yahoo failed: {e} -> falling back to Alpaca")
            y = pd.DataFrame(columns=COLS)
        self._try_source("yahoo", vault, vcls, y, targets, rep, healed)

        # 2) Alpaca second, only on what Yahoo did not repair
        remaining = targets[self.classify(healed).loc[targets] != "CLEAN"]
        a = pd.DataFrame(columns=COLS)
        try:
            # Free plan: SIP queries must end > 15 min ago
            a = self.fetch_alpaca(ticker, vault.index.min().to_pydatetime(),
                                  datetime.now(UTC) - timedelta(minutes=20))
        except Exception as e:
            logger.warning(f"[{ticker}] Alpaca failed: {e}")
        if len(remaining):
            logger.info(f"[{ticker}] Yahoo left {len(remaining)} bars -> trying Alpaca")
        self._try_source("alpaca", vault, vcls, a, remaining, rep, healed)

        hcls = self.classify(healed)
        rep.repaired = int(((vcls != "CLEAN") & (hcls == "CLEAN")).sum())
        rep.unrecovered = hcls[hcls != "CLEAN"].value_counts().to_dict()
        self.propose_boundaries(vault, vcls, rep, a.index.min() if not a.empty else None)

        # 3) Truncation only if explicitly ordered
        if truncate_before:
            cut = pd.Timestamp(truncate_before, tz="UTC").normalize()
            rep.truncated = int((healed.index < cut).sum())
            healed = healed[healed.index >= cut]

        if not dry_run and (rep.repaired or rep.truncated or force):
            self.commit(ticker, healed)
            rep.committed = True
        return healed, rep

    def commit(self, ticker: str, healed: pd.DataFrame) -> None:
        from backend.scripts.backfills.wipe_reload_cascade import (
            atomic_swap_bars, rebuild_snapshots, rebuild_zigzag, rebuild_observer)
        from backend.modules.shared.infrastructure.redis_cache import get_redis_cache
        atomic_swap_bars(self.store, ticker, healed)      # single transaction, rollback on error
        rebuild_snapshots(self.store, ticker, healed)      # separate commits from here on:
        rebuild_zigzag(self.store, ticker, healed)         # idempotent, re-run if interrupted
        rebuild_observer(self.store, ticker)
        cache = get_redis_cache()
        if cache:
            cache.invalidate_pattern(f"bars:{ticker}:*")


if __name__ == "__main__":
    import argparse, json, warnings
    warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--force", action="store_true", help="Force commit even if repaired=0 and truncated=0")
    ap.add_argument("--truncate-before", default=None, help="YYYY-MM-DD, only with Architect approval")
    args = ap.parse_args()
    h = TickerDataHealer()
    for t in args.tickers.split(","):
        _, r = h.heal(t, dry_run=not args.commit, truncate_before=args.truncate_before, force=args.force)
        print(json.dumps(r.__dict__, default=str))
    h.store.close()
