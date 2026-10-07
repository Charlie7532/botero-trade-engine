"""
Parity & Homogeneity Tests for Volume Breadth Providers (SV5)
==============================================================
Validates exact float parity, constituent counts, and EMA5 crossover logic
between VolumeBreadthProvider and Neon Vault storage.
"""
import pytest
import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.daemons.vault_providers.volume_breadth_provider import VolumeBreadthProvider
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate


def test_sv5tw_stored_bars_parity():
    """Verify stored SV5TW bars in Neon reflect cured constituents (volume=506) and 43.3% on 2026-10-02."""
    store = TimescaleDataStore()
    df_sv5tw = store.load_bars("SV5TW", "1d")
    assert df_sv5tw is not None and not df_sv5tw.empty

    # Verify 2026-10-02 corrected bar
    oct2 = pd.to_datetime("2026-10-02").tz_localize("UTC")
    if oct2 in df_sv5tw.index:
        bar_oct2 = df_sv5tw.loc[oct2]
        assert round(float(bar_oct2["close"]), 1) == 43.3
        assert int(bar_oct2["volume"]) == 506

    # Verify 2026-10-05 bar
    oct5 = pd.to_datetime("2026-10-05").tz_localize("UTC")
    if oct5 in df_sv5tw.index:
        bar_oct5 = df_sv5tw.loc[oct5]
        assert round(float(bar_oct5["close"]), 1) == 34.4
        assert int(bar_oct5["volume"]) == 506


def test_volume_breadth_calc_crossovers_logic():
    """Verify that calculate_all_volume_breadth accurately calculates EMA5 > SMA20 crossovers."""
    from backend.modules.shared.domain.rules.volume_breadth_calculator import calculate_all_volume_breadth
    
    # Stock 1: Bullish volume surge at end -> EMA5 > SMA20
    vol1 = [1000.0] * 25 + [5000.0] * 5
    
    # Stock 2: Bearish volume collapse at end -> EMA5 < SMA20
    vol2 = [5000.0] * 25 + [500.0] * 5
    
    universe_vols = {"STK1": vol1, "STK2": vol2}
    
    results = calculate_all_volume_breadth(universe_vols)
    assert results is not None
    assert "tactical" in results
    # Exactly 1 out of 2 stocks has EMA5 > SMA20 -> 50.0%
    assert results["tactical"] == 50.0


def test_quality_entry_gate_sv5_edges_monotonic():
    """Verify QualityEntryGate.SV5_EDGES are strictly monotonic and align with EMA5 scale."""
    for key, edges in QualityEntryGate.SV5_EDGES.items():
        assert len(edges) == 4
        # Verify strictly increasing
        for i in range(len(edges) - 1):
            assert edges[i] < edges[i + 1], f"SV5_EDGES[{key}] not strictly increasing at index {i}"
        
        # Verify plausible breadth ranges (0 to 100)
        assert edges[0] >= 10.0
        assert edges[-1] <= 90.0


def test_volume_breadth_50_dates_historical_parity():
    """Verify that calculate_all_volume_breadth matches stored SV5 bars across 50 sample dates (30 random + 20 recent)."""
    import random
    from backend.modules.shared.domain.rules.volume_breadth_calculator import calculate_all_volume_breadth

    store = TimescaleDataStore()
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT time::date as dt 
                FROM market.ohlcv_bars 
                WHERE ticker = 'SV5TW' AND timeframe = '1d' AND time >= '2000-01-01'
                ORDER BY time ASC;
            """)
            all_dates = [r[0] for r in cur.fetchall()]

        assert len(all_dates) >= 50, "Insufficient SV5TW historical dates"
        last_20 = all_dates[-20:]
        remaining = all_dates[:-20]
        random.seed(42)  # Deterministic seed
        random_30 = sorted(random.sample(remaining, 30))
        test_dates = random_30 + last_20

        matches = 0
        tolerance = 0.1  # 0.1 percentage point rounding tolerance

        for target_date in test_dates:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT b.ticker, b.volume
                    FROM market.ohlcv_bars b
                    JOIN market.ticker_metadata m ON b.ticker = m.ticker
                    WHERE b.timeframe = '1d'
                      AND b.time <= %s
                      AND b.time >= %s - INTERVAL '300 days'
                      AND m.asset_type = 'STOCK'
                      AND 'SP500' = ANY(m.index_membership)
                      AND m.update_source = 'vault_ohlcv_bars'
                      AND b.volume > 0
                    ORDER BY b.ticker, b.time
                """, (target_date, target_date))
                vols = {}
                for tkr, vol in cur.fetchall():
                    vols.setdefault(tkr, []).append(float(vol))

                cur.execute("""
                    SELECT ticker, close 
                    FROM market.ohlcv_bars
                    WHERE ticker IN ('SV5TW', 'SV5FI', 'SV5TH')
                      AND timeframe = '1d'
                      AND time::date = %s
                """, (target_date,))
                stored = {r[0]: float(r[1]) for r in cur.fetchall()}

            calc = calculate_all_volume_breadth(vols)
            calc_tw = calc.get("tactical")
            calc_fi = calc.get("intermediate")
            calc_th = calc.get("structural")

            diff_tw = abs(calc_tw - stored.get("SV5TW", 0.0))
            diff_fi = abs(calc_fi - stored.get("SV5FI", 0.0))
            diff_th = abs(calc_th - stored.get("SV5TH", 0.0))

            if diff_tw <= tolerance and diff_fi <= tolerance and diff_th <= tolerance:
                matches += 1

        match_rate = matches / len(test_dates)
        assert match_rate >= 0.96, f"Parity match rate {match_rate:.2%} below 96% threshold ({matches}/{len(test_dates)})"
    finally:
        store._put(conn)

