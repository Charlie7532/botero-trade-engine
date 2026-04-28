"""
Integration Test Suite — Pre-Trade Engine
=============================================
End-to-end validation of every component in the modular pre-trade
engine. Uses synthetic data to test without external APIs.

Run: PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/tests/test_pretrade_integration.py
"""
import json
import sys
import shutil
import tempfile
import logging
from datetime import datetime, UTC, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(name)s] %(message)s")

PASS = 0
FAIL = 0
ERRORS = []


def test(name):
    """Decorator to track test results."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            global PASS, FAIL, ERRORS
            try:
                func(*args, **kwargs)
                PASS += 1
                print(f"  ✅ {name}")
            except Exception as e:
                FAIL += 1
                ERRORS.append((name, str(e)))
                print(f"  ❌ {name}: {e}")
        return wrapper
    return decorator


def generate_synthetic_ohlcv(days=200, ticker="TEST") -> pd.DataFrame:
    """Generate realistic synthetic OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=days, freq="B", tz="UTC")
    price = 100.0
    rows = []
    for d in dates:
        change = np.random.normal(0.0005, 0.015)
        open_p = price
        close_p = price * (1 + change)
        high_p = max(open_p, close_p) * (1 + abs(np.random.normal(0, 0.005)))
        low_p = min(open_p, close_p) * (1 - abs(np.random.normal(0, 0.005)))
        vol = int(np.random.lognormal(17, 0.5))
        rows.append({"open": open_p, "high": high_p, "low": low_p, "close": close_p, "volume": vol})
        price = close_p
    df = pd.DataFrame(rows, index=dates)
    df.index.name = "timestamp"
    return df


def generate_synthetic_flow(days=30) -> list[tuple[str, list[dict]]]:
    """Generate synthetic UW flow data."""
    entries = []
    base = datetime(2025, 6, 1, tzinfo=UTC)
    for i in range(days):
        dt = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        alerts = [
            {
                "type": "call" if np.random.random() > 0.4 else "put",
                "has_sweep": np.random.random() > 0.6,
                "total_premium": float(np.random.randint(50000, 500000)),
                "volume_oi_ratio": round(np.random.uniform(0.5, 5.0), 2),
                "total_ask_side_prem": float(np.random.randint(20000, 200000)),
                "total_bid_side_prem": float(np.random.randint(10000, 100000)),
            }
            for _ in range(np.random.randint(5, 20))
        ]
        entries.append((dt, alerts))
    return entries


# ═══════════════════════════════════════════════════════════
# Create temporary vault for all tests
# ═══════════════════════════════════════════════════════════
TEMP_DIR = Path(tempfile.mkdtemp(prefix="botero_test_"))


def run_all_tests():
    global PASS, FAIL

    print(f"\n{'='*60}")
    print(f"  PRE-TRADE ENGINE INTEGRATION TESTS")
    print(f"  Temp vault: {TEMP_DIR}")
    print(f"{'='*60}\n")

    ohlcv = generate_synthetic_ohlcv()
    flow_data = generate_synthetic_flow()

    # ── 1. VAULT TESTS ────────────────────────────────────

    print("📦 1. VAULT (ParquetDataStore)")

    from backend.modules.simulation.infrastructure.parquet_data_store import ParquetDataStore
    store = ParquetDataStore(vault_root=TEMP_DIR)

    @test("Save and load OHLCV bars")
    def _():
        store.save_bars("TEST", "1d", ohlcv)
        loaded = store.load_bars("TEST", "1d")
        assert len(loaded) == len(ohlcv), f"Expected {len(ohlcv)}, got {len(loaded)}"
        assert list(loaded.columns) == list(ohlcv.columns)
    _()

    @test("Append-only deduplication")
    def _():
        initial_count = len(store.load_bars("TEST", "1d"))
        # Re-save same data — should not duplicate
        store.save_bars("TEST", "1d", ohlcv)
        after_count = len(store.load_bars("TEST", "1d"))
        assert after_count == initial_count, f"Duplicated: {initial_count} → {after_count}"
    _()

    @test("Append new bars only")
    def _():
        new_date = ohlcv.index.max() + pd.Timedelta(days=1)
        new_bar = pd.DataFrame(
            {"open": [100], "high": [101], "low": [99], "close": [100.5], "volume": [1000000]},
            index=pd.DatetimeIndex([new_date], name="timestamp"),
        )
        store.save_bars("TEST", "1d", new_bar)
        loaded = store.load_bars("TEST", "1d")
        assert len(loaded) == len(ohlcv) + 1
    _()

    @test("Load bars with date range filter")
    def _():
        from datetime import date
        filtered = store.load_bars("TEST", "1d", start=date(2025, 3, 1), end=date(2025, 4, 1))
        assert len(filtered) > 0
        assert filtered.index.min() >= pd.Timestamp("2025-03-01", tz="UTC")
    _()

    @test("bars_last_date returns correct date")
    def _():
        last = store.bars_last_date("TEST", "1d")
        assert last is not None
    _()

    @test("Vault JSON (immutable write)")
    def _():
        data = {"test": True, "count": 42}
        store.vault_json("flow/alerts", "TEST", "2025-06-15", data)
        loaded = store.load_json("flow/alerts", "TEST", "2025-06-15")
        assert loaded is not None
        assert loaded["count"] == 42
    _()

    @test("Vault JSON skips existing file")
    def _():
        store.vault_json("flow/alerts", "TEST", "2025-06-15", {"overwritten": True})
        loaded = store.load_json("flow/alerts", "TEST", "2025-06-15")
        assert "overwritten" not in loaded  # Original data preserved
    _()

    @test("Load JSON range")
    def _():
        for dt, alerts in flow_data:
            store.vault_json("flow/alerts", "TEST", dt, alerts)
        results = store.load_json_range("flow/alerts", "TEST", "2025-06-01", "2025-06-15")
        assert len(results) > 0
    _()

    @test("Save and load features")
    def _():
        features = pd.DataFrame({"feat1": [1.0, 2.0], "feat2": [3.0, 4.0]},
                                index=pd.DatetimeIndex(["2025-01-01", "2025-01-02"], tz="UTC", name="timestamp"))
        store.save_features("TEST", "flow_1d", features)
        loaded = store.load_features("TEST", "flow_1d")
        assert loaded is not None
        assert len(loaded) == 2
    _()

    @test("Save and load profile with archive")
    def _():
        from backend.modules.simulation.domain.entities.strategy_profile import (
            StrategyProfile, InvestmentCategory, SignalConfig,
        )
        profile = StrategyProfile(
            ticker="TEST", category=InvestmentCategory.TACTICAL_SPRING,
            calibrated_at=datetime.now(UTC).isoformat(),
            signals=[SignalConfig(name="test_signal", weight=1.0)],
        )
        store.save_profile(profile)
        loaded = store.load_profile("TACTICAL_SPRING", "TEST")
        assert loaded is not None
        assert loaded["ticker"] == "TEST"
    _()

    @test("Save and load trade snapshot")
    def _():
        from backend.modules.simulation.domain.entities.trade_snapshot import TradeSnapshot
        snap = TradeSnapshot(ticker="TEST", category="TACTICAL_SPRING")
        store.save_snapshot(snap)
        loaded = store.load_snapshots(ticker="TEST")
        assert len(loaded) >= 1
        assert loaded[0]["ticker"] == "TEST"
    _()

    @test("Save and load macro data")
    def _():
        macro = pd.DataFrame(
            {"close": [18.5, 19.2, 17.8]},
            index=pd.DatetimeIndex(["2025-01-01", "2025-01-02", "2025-01-03"], tz="UTC", name="timestamp"),
        )
        store.save_macro("vix", macro)
        loaded = store.load_macro("vix")
        assert loaded is not None
        assert len(loaded) == 3
    _()

    # ── 2. HARMONIZER TESTS ──────────────────────────────

    print("\n🔄 2. DATA HARMONIZER")

    from backend.modules.simulation.infrastructure.data_harmonizer import DataHarmonizer
    harmonizer = DataHarmonizer(store)

    @test("Harmonize UW flow → canonical features")
    def _():
        result = harmonizer.harmonize_uw_flow("TEST", "2025-06-01", "2025-06-30")
        assert not result.empty, "Empty flow features"
        expected_cols = ["uw_sweep_count", "uw_call_put_ratio", "uw_flow_score"]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"
        assert str(result.index.tz) == "UTC"
    _()

    @test("Build ML dataset (cross-source join)")
    def _():
        # Save flow features first
        flow_feats = harmonizer.harmonize_uw_flow("TEST", "2025-06-01", "2025-06-30")
        if not flow_feats.empty:
            store.save_features("TEST", "flow_1d", flow_feats)
        dataset = harmonizer.build_ml_dataset("TEST", "1d")
        assert not dataset.empty
        assert "open" in dataset.columns
        assert "close" in dataset.columns
    _()

    # ── 3. INTERCEPTOR TESTS ─────────────────────────────

    print("\n🔌 3. VAULT INTERCEPTOR")

    from backend.modules.simulation.infrastructure.vault_interceptor import VaultInterceptor
    interceptor = VaultInterceptor(store)

    @test("Intercept flow alerts transparently")
    def _():
        alerts = [{"type": "call", "has_sweep": True, "total_premium": 100000}]
        result = interceptor.intercept_flow_alerts("INTTEST", alerts)
        assert result == alerts  # Same data returned
        # Verify it was vaulted
        from datetime import date
        today = date.today().isoformat()
        vaulted = store.load_json("flow/alerts", "INTTEST", today)
        assert vaulted is not None
    _()

    @test("Intercept SPY flow")
    def _():
        ticks = [{"cum_delta": 50000, "signal": "BULLISH"}]
        result = interceptor.intercept_spy_flow(ticks)
        assert result == ticks
    _()

    @test("Intercept sentiment")
    def _():
        sent = {"sentiment_score": 75, "regime": "BULL"}
        result = interceptor.intercept_sentiment(sent)
        assert result == sent
    _()

    # ── 4. SIGNAL ADAPTERS TESTS ─────────────────────────

    print("\n📡 4. SIGNAL ADAPTERS")

    from backend.modules.simulation.infrastructure.signal_adapters import create_all_signals

    signals = create_all_signals()

    for signal in signals:
        @test(f"Signal '{signal.name}' generates valid output")
        def _(s=signal):
            result = s.generate(ohlcv)
            assert "signal" in result.columns, f"Missing 'signal' column"
            assert len(result) == len(ohlcv), f"Length mismatch: {len(result)} vs {len(ohlcv)}"
            assert set(result["signal"].unique()).issubset({-1, 0, 1}), f"Invalid signal values: {result['signal'].unique()}"
        _()

    # ── 5. TRIPLE BARRIER TESTS ──────────────────────────

    print("\n🎯 5. TRIPLE BARRIER LABELER")

    from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
    labeler = TripleBarrierAdapter()

    @test("Label entries with valid results")
    def _():
        # Create entries every 20 bars
        entries = pd.Series(False, index=ohlcv.index)
        entries.iloc[::20] = True
        labels = labeler.label_entries(ohlcv, entries, profit_mult=2.0, loss_mult=1.0, max_bars=15)
        assert len(labels) > 0
        for l in labels:
            assert l.label in (-1, 0, 1)
            assert l.hit_barrier in ("profit", "loss", "time")
            assert l.bars_held >= 0
    _()

    # ── 6. SMC ADAPTER TESTS ─────────────────────────────

    print("\n🏗️ 6. SMC ADAPTER")

    from backend.modules.simulation.infrastructure.smc_adapter import SMCAdapter
    smc = SMCAdapter()

    @test("SMC analyze returns valid MarketStructureResult")
    def _():
        result = smc.analyze(ohlcv)
        assert result.swing_trend in ("UPTREND", "DOWNTREND", "RANGING", "UNKNOWN")
        assert result.bos_direction in ("BULLISH", "BEARISH", "NONE")
        assert result.choch_direction in ("BULLISH", "BEARISH", "NONE")
    _()

    @test("SMC handles insufficient data gracefully")
    def _():
        small = ohlcv.head(10)
        result = smc.analyze(small)
        assert result.swing_trend == "UNKNOWN"  # Default for insufficient data
    _()

    # ── 7. ORACLE BACKTEST TESTS ─────────────────────────

    print("\n🔮 7. ORACLE BACKTEST")

    from backend.modules.simulation.domain.use_cases.oracle_backtest import OracleBacktester
    from backend.modules.simulation.domain.entities.strategy_profile import (
        InvestmentCategory, ORACLE_GEOMETRY,
    )

    oracle = OracleBacktester(store, labeler)

    @test("Oracle run_signal produces OracleResult")
    def _():
        from backend.modules.simulation.infrastructure.signal_adapters import MeanReversionSignalAdapter
        signal = MeanReversionSignalAdapter()
        geometry = ORACLE_GEOMETRY[InvestmentCategory.TACTICAL_SPRING]
        result = oracle.run_signal("TEST", "1d", signal, geometry)
        assert result.signal_name == "mean_reversion"
        assert result.ticker == "TEST"
    _()

    @test("Oracle rank_signals produces sorted rankings")
    def _():
        rankings = oracle.rank_signals("TEST", "1d", signals[:3])  # First 3 signals
        assert len(rankings) == 3
        # Should be sorted by ceiling_sharpe descending
        for i in range(len(rankings) - 1):
            assert rankings[i].ceiling_sharpe >= rankings[i + 1].ceiling_sharpe
        # Ranks assigned
        assert rankings[0].rank == 1
    _()

    # ── 8. COMPOSER TESTS ────────────────────────────────

    print("\n🎼 8. STRATEGY COMPOSER")

    from backend.modules.simulation.domain.use_cases.strategy_composer import StrategyComposer
    from backend.modules.simulation.domain.entities.strategy_profile import (
        StrategyProfile, SignalConfig,
    )

    composer = StrategyComposer()

    @test("Weighted vote: entry when score ≥ 0.5")
    def _():
        profile = StrategyProfile(
            ticker="TEST", category=InvestmentCategory.TACTICAL_SPRING,
            signals=[
                SignalConfig(name="a", weight=0.5, threshold=0.0),
                SignalConfig(name="b", weight=0.3, threshold=0.0),
                SignalConfig(name="c", weight=0.2, threshold=0.0),
            ],
            min_signals_required=2,
        )
        decision = composer.compose(profile, {"a": 1, "b": 1, "c": 0})
        assert decision.entry is True
        assert decision.score > 0.5
    _()

    @test("Weighted vote: reject when insufficient signals")
    def _():
        profile = StrategyProfile(
            ticker="TEST", category=InvestmentCategory.TACTICAL_SPRING,
            signals=[
                SignalConfig(name="a", weight=0.5, threshold=0.0),
                SignalConfig(name="b", weight=0.3, threshold=0.0),
                SignalConfig(name="c", weight=0.2, threshold=0.0),
            ],
            min_signals_required=3,
        )
        decision = composer.compose(profile, {"a": 1, "b": 0, "c": 0})
        assert decision.entry is False
    _()

    @test("Majority composition")
    def _():
        profile = StrategyProfile(
            ticker="TEST", category=InvestmentCategory.TACTICAL_SPRING,
            composite_method="majority",
            signals=[
                SignalConfig(name="a", weight=1, threshold=0.0),
                SignalConfig(name="b", weight=1, threshold=0.0),
                SignalConfig(name="c", weight=1, threshold=0.0),
            ],
            min_signals_required=2,
        )
        decision = composer.compose(profile, {"a": 1, "b": 1, "c": 0})
        assert decision.entry is True
    _()

    @test("Unanimous composition: all must agree")
    def _():
        profile = StrategyProfile(
            ticker="TEST", category=InvestmentCategory.TACTICAL_SPRING,
            composite_method="unanimous",
            signals=[
                SignalConfig(name="a", weight=1, threshold=0.0),
                SignalConfig(name="b", weight=1, threshold=0.0),
            ],
        )
        decision = composer.compose(profile, {"a": 1, "b": 0})
        assert decision.entry is False
        decision2 = composer.compose(profile, {"a": 1, "b": 1})
        assert decision2.entry is True
    _()

    # ── 9. ENTITIES TESTS ────────────────────────────────

    print("\n📐 9. DOMAIN ENTITIES")

    @test("InvestmentCategory taxonomy")
    def _():
        assert InvestmentCategory.CORE_VALUE.bucket == "CORE"
        assert InvestmentCategory.TACTICAL_SPRING.bucket == "TACTICAL"
        assert InvestmentCategory.CORE_VALUE.is_core is True
        assert InvestmentCategory.TACTICAL_GAMMA.is_core is False
        assert len(InvestmentCategory) == 7
    _()

    @test("ExecutionIntent is frozen (immutable)")
    def _():
        from backend.modules.simulation.domain.entities.execution_intent import ExecutionIntent
        intent = ExecutionIntent(ticker="AAPL", direction="LONG")
        try:
            intent.ticker = "NVDA"
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass  # Correct
    _()

    @test("TradeSnapshot auto-generates UUID and timestamp")
    def _():
        from backend.modules.simulation.domain.entities.trade_snapshot import TradeSnapshot
        s1 = TradeSnapshot(ticker="A")
        s2 = TradeSnapshot(ticker="B")
        assert s1.snapshot_id != s2.snapshot_id
        assert s1.timestamp != ""
    _()

    @test("ORACLE_GEOMETRY has all 7 categories")
    def _():
        assert len(ORACLE_GEOMETRY) == 7
        for cat in InvestmentCategory:
            assert cat in ORACLE_GEOMETRY
    _()

    # ── 10. PRE-TRADE GATE TESTS ─────────────────────────

    print("\n🚧 10. PRE-TRADE GATE")

    from backend.modules.simulation.domain.use_cases.pre_trade_gate import PreTradeGate

    @test("Gate rejects on insufficient data")
    def _():
        gate = PreTradeGate(
            store=store,
            structure_analyzer=smc,
            signals=signals[:3],
            composer=composer,
        )
        profile = StrategyProfile(
            ticker="NODATA", category=InvestmentCategory.CORE_VALUE,
            signals=[SignalConfig(name=s.name, weight=0.33, threshold=0.0) for s in signals[:3]],
        )
        intent, snapshot = gate.evaluate("NODATA", InvestmentCategory.CORE_VALUE, profile)
        assert intent is None
        assert snapshot.gate_reason == "INSUFFICIENT_DATA"
    _()

    @test("Gate produces snapshot for valid data")
    def _():
        gate = PreTradeGate(
            store=store,
            structure_analyzer=smc,
            signals=signals[:3],
            composer=composer,
        )
        profile = StrategyProfile(
            ticker="TEST", category=InvestmentCategory.TACTICAL_SPRING,
            signals=[SignalConfig(name=s.name, weight=0.33, threshold=0.0, enabled=True) for s in signals[:3]],
            min_signals_required=1,
        )
        intent, snapshot = gate.evaluate("TEST", InvestmentCategory.TACTICAL_SPRING, profile)
        assert snapshot is not None
        assert snapshot.ticker == "TEST"
        assert snapshot.structure is not None
        assert len(snapshot.signals) > 0
    _()

    # ── 11. FEEDBACK LOOP TESTS ──────────────────────────

    print("\n🔄 11. FEEDBACK LOOP")

    from backend.modules.simulation.domain.use_cases.analyze_indicators import IndicatorAnalyzer
    from backend.modules.simulation.domain.use_cases.retrain_trigger import RetrainTrigger

    @test("IndicatorAnalyzer quality report (empty)")
    def _():
        analyzer = IndicatorAnalyzer(store)
        report = analyzer.quality_report(ticker="NONEXISTENT")
        assert report.total_snapshots == 0
    _()

    @test("RetrainTrigger check (no data)")
    def _():
        analyzer = IndicatorAnalyzer(store)
        trigger = RetrainTrigger(store, analyzer)
        result = trigger.check("NONEXISTENT", "CORE_VALUE")
        assert isinstance(result, dict)
        assert "needs_retrain" in result
    _()

    # ── 12. PAYLOAD SYNC TESTS ───────────────────────────

    print("\n☁️ 12. PAYLOAD CMS SYNC")

    from backend.modules.simulation.infrastructure.payload_cms_sync_adapter import PayloadCMSSyncAdapter

    @test("PayloadCMS adapter initializes (offline OK)")
    def _():
        sync = PayloadCMSSyncAdapter(base_url="http://localhost:9999")
        assert sync.is_available() is False  # Expected: no server running
    _()

    # ── 13. CLEAN ARCHITECTURE COMPLIANCE ────────────────

    print("\n🏛️ 13. CLEAN ARCHITECTURE COMPLIANCE")

    @test("Domain ports have NO infrastructure imports")
    def _():
        ports_dir = Path("backend/modules/simulation/domain/ports")
        for f in ports_dir.glob("*.py"):
            if f.name == "__init__.py":
                continue
            content = f.read_text()
            forbidden = ["import yfinance", "import requests", "from backend.modules.simulation.infrastructure"]
            for term in forbidden:
                assert term not in content, f"{f.name} contains forbidden import: {term}"
    _()

    @test("Domain entities have NO infrastructure imports")
    def _():
        entities_dir = Path("backend/modules/simulation/domain/entities")
        for f in entities_dir.glob("*.py"):
            if f.name == "__init__.py":
                continue
            content = f.read_text()
            assert "import yfinance" not in content, f"{f.name} imports yfinance"
            assert "import requests" not in content, f"{f.name} imports requests"
    _()

    @test("Domain use cases import only ports (not adapters)")
    def _():
        use_cases = [
            "backend/modules/simulation/domain/use_cases/oracle_backtest.py",
            "backend/modules/simulation/domain/use_cases/strategy_composer.py",
        ]
        for uc_path in use_cases:
            content = Path(uc_path).read_text()
            assert "from backend.modules.simulation.infrastructure" not in content, \
                f"{uc_path} imports infrastructure directly"
    _()

    # ═══════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")

    if ERRORS:
        print("\n❌ FAILURES:")
        for name, err in ERRORS:
            print(f"  • {name}: {err}")

    # Cleanup
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

    return FAIL == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
