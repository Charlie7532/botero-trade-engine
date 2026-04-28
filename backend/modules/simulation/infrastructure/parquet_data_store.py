"""
Parquet Data Store — Vault Implementation
============================================
Implements HistoricalDataPort with hybrid storage:
- Parquet for OHLCV bars, harmonized features, macro data
- JSON for raw MCP data (UW, GuruFocus), profiles, snapshots

All write operations are append-only with deduplication.
JSON files are immutable once written.

Directory structure: data/vault/ (see implementation_plan.md §5)
"""
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend.modules.simulation.domain.ports.historical_data_port import HistoricalDataPort

logger = logging.getLogger(__name__)

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "vault"


class ParquetDataStore(HistoricalDataPort):
    """Hybrid Parquet + JSON vault for all simulation data."""

    def __init__(self, vault_root: Path | None = None):
        self.root = vault_root or VAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────
    # OHLCV Bars (Parquet, append-only)
    # ──────────────────────────────────────────────────────────

    def _bars_path(self, ticker: str, tf: str) -> Path:
        return self.root / "market" / ticker.upper() / f"{tf}.parquet"

    def save_bars(self, ticker: str, tf: str, df: pd.DataFrame) -> None:
        """Append-only save. Deduplicates by timestamp index."""
        path = self._bars_path(ticker, tf)
        path.parent.mkdir(parents=True, exist_ok=True)

        if df.empty:
            return

        if path.exists():
            existing = pd.read_parquet(path)
            last_existing = existing.index.max()
            # Only add rows newer than what we have
            truly_new = df[df.index > last_existing]
            if truly_new.empty:
                logger.debug(f"Vault: {ticker}/{tf} — no new bars to append")
                return
            combined = pd.concat([existing, truly_new])
            logger.info(f"Vault: {ticker}/{tf} — appended {len(truly_new)} bars")
        else:
            combined = df.copy()
            logger.info(f"Vault: {ticker}/{tf} — created with {len(combined)} bars")

        combined.sort_index(inplace=True)
        combined.to_parquet(path, engine="pyarrow", compression="snappy")

    def load_bars(
        self, ticker: str, tf: str,
        start: Optional[date] = None, end: Optional[date] = None,
    ) -> pd.DataFrame:
        path = self._bars_path(ticker, tf)
        if not path.exists():
            return pd.DataFrame()

        df = pd.read_parquet(path)
        if start:
            df = df[df.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            df = df[df.index <= pd.Timestamp(end, tz="UTC")]
        return df

    def bars_last_date(self, ticker: str, tf: str) -> Optional[date]:
        path = self._bars_path(ticker, tf)
        if not path.exists():
            return None
        df = pd.read_parquet(path, columns=["close"])
        if df.empty:
            return None
        return df.index.max().date()

    # ──────────────────────────────────────────────────────────
    # Raw MCP JSON (immutable per date)
    # ──────────────────────────────────────────────────────────

    def _json_path(self, category: str, key: str, dt: str) -> Path:
        return self.root / category / key.upper() / f"{dt}.json"

    def vault_json(self, category: str, key: str, dt: str, data: Any) -> None:
        """Save raw JSON. Immutable: skips if file already exists."""
        path = self._json_path(category, key, dt)
        if path.exists():
            logger.debug(f"Vault: {category}/{key}/{dt} — already exists, skipping")
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, default=str, indent=2)
        logger.info(f"Vault: {category}/{key}/{dt} — saved ({len(json.dumps(data, default=str))} bytes)")

    def load_json(self, category: str, key: str, dt: str) -> Optional[Any]:
        path = self._json_path(category, key, dt)
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def load_json_range(
        self, category: str, key: str,
        start: str, end: str,
    ) -> list[tuple[str, Any]]:
        """Load all JSON files in date range [start, end] inclusive."""
        folder = self.root / category / key.upper()
        if not folder.exists():
            return []

        results = []
        for path in sorted(folder.glob("*.json")):
            dt = path.stem  # filename without .json
            if start <= dt <= end:
                with open(path) as f:
                    results.append((dt, json.load(f)))
        return results

    # ──────────────────────────────────────────────────────────
    # Harmonized Features (Parquet, regenerable)
    # ──────────────────────────────────────────────────────────

    def _features_path(self, ticker: str, feature_set: str) -> Path:
        return self.root / "features" / ticker.upper() / f"{feature_set}.parquet"

    def save_features(self, ticker: str, feature_set: str, df: pd.DataFrame) -> None:
        """Overwrite features (regenerable from raw JSON/Parquet)."""
        path = self._features_path(ticker, feature_set)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, engine="pyarrow", compression="snappy")
        logger.info(f"Vault: features/{ticker}/{feature_set} — saved ({len(df)} rows, {len(df.columns)} cols)")

    def load_features(self, ticker: str, feature_set: str) -> Optional[pd.DataFrame]:
        path = self._features_path(ticker, feature_set)
        if not path.exists():
            return None
        return pd.read_parquet(path)

    # ──────────────────────────────────────────────────────────
    # Strategy Profiles (replaceable, with archive)
    # ──────────────────────────────────────────────────────────

    def _profile_path(self, category: str, ticker: str) -> Path:
        return self.root / "profiles" / category / f"{ticker.upper()}.json"

    def save_profile(self, profile: Any) -> None:
        """Save profile. Archives previous version if exists."""
        from dataclasses import asdict
        data = asdict(profile) if hasattr(profile, "__dataclass_fields__") else profile

        category = data.get("category", "UNKNOWN")
        if hasattr(category, "value"):
            category = category.value
        ticker = data.get("ticker", "UNKNOWN")

        path = self._profile_path(category, ticker)

        # Archive previous version
        if path.exists():
            archive_dir = path.parent / f"{ticker.upper()}_archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            old_data = json.loads(path.read_text())
            old_cal = old_data.get("calibrated_at", "unknown")[:10]
            archive_path = archive_dir / f"{old_cal}.json"
            path.rename(archive_path)
            logger.info(f"Vault: archived previous profile → {archive_path.name}")

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, default=str, indent=2)
        logger.info(f"Vault: profile {category}/{ticker} saved")

    def load_profile(self, category: str, ticker: str) -> Optional[Any]:
        path = self._profile_path(category, ticker)
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    # ──────────────────────────────────────────────────────────
    # Trade Snapshots (immutable, append-only)
    # ──────────────────────────────────────────────────────────

    def save_snapshot(self, snapshot: Any) -> None:
        """Save immutable trade snapshot."""
        from dataclasses import asdict
        data = asdict(snapshot) if hasattr(snapshot, "__dataclass_fields__") else snapshot

        ts = data.get("timestamp", "")[:7]  # yyyy-mm
        snap_id = data.get("snapshot_id", "unknown")
        ticker = data.get("ticker", "UNK")

        folder = self.root / "snapshots" / ts
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"snap_{snap_id}_{ticker}.json"

        with open(path, "w") as f:
            json.dump(data, f, default=str, indent=2)
        logger.info(f"Vault: snapshot {ticker} → {path.name}")

    def load_snapshots(
        self, ticker: Optional[str] = None,
        category: Optional[str] = None,
        start: Optional[str] = None, end: Optional[str] = None,
    ) -> list[Any]:
        """Query snapshots by ticker, category, and/or date range."""
        snapshots_dir = self.root / "snapshots"
        if not snapshots_dir.exists():
            return []

        results = []
        for month_dir in sorted(snapshots_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            # Filter by date range (yyyy-mm)
            month_str = month_dir.name
            if start and month_str < start[:7]:
                continue
            if end and month_str > end[:7]:
                continue

            for snap_file in sorted(month_dir.glob("snap_*.json")):
                with open(snap_file) as f:
                    data = json.load(f)
                # Filter by ticker
                if ticker and data.get("ticker") != ticker:
                    continue
                # Filter by category
                if category and data.get("category") != category:
                    continue
                results.append(data)

        return results

    # ──────────────────────────────────────────────────────────
    # Macro Data (Parquet, append-only — same logic as bars)
    # ──────────────────────────────────────────────────────────

    def _macro_path(self, name: str) -> Path:
        return self.root / "macro" / f"{name}.parquet"

    def save_macro(self, name: str, df: pd.DataFrame) -> None:
        """Append macro data (VIX, yields). Same dedup logic as bars."""
        path = self._macro_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing = pd.read_parquet(path)
            last_existing = existing.index.max()
            truly_new = df[df.index > last_existing]
            if truly_new.empty:
                return
            combined = pd.concat([existing, truly_new])
        else:
            combined = df.copy()

        combined.sort_index(inplace=True)
        combined.to_parquet(path, engine="pyarrow", compression="snappy")

    def load_macro(self, name: str) -> Optional[pd.DataFrame]:
        path = self._macro_path(name)
        if not path.exists():
            return None
        return pd.read_parquet(path)
