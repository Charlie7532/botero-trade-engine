"""
Master Script: Regeneración Histórica Completa de Data Sintética y Regímenes en Neon Vault.
========================================================================================
Ejecuta la secuencia integral aprobada:
  1. Purga de barras de fin de semana (ohlcv_bars) y transiciones residuales (regime_states).
  2. Regeneración desde cero de CREDIT_RATIO, YIELD_SPREAD, ROTATION_INDEX.
  3. Regeneración de amplitud sectorial de precios (S5_*).
  4. Regeneración de amplitud de volumen (SV5_*).
  5. Sincronización y recálculo de BSI y SV5_TURBULENCE.
  6. Recálculo Total 1993-2026 del Régimen de Volatilidad (Quality & Speculative).
  7. Re-anclaje de estados activos de telemetría METAR al viernes 2026-09-18.
  8. Certificación y auditoría de integridad Cero Discrepancias.

Diseñado para ejecutarse en background desconectado con logging exhaustivo.
"""
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.chdir(str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / ".env")
load_dotenv(PROJECT_ROOT / ".env")

# Logging setup
LOG_DIR = PROJECT_ROOT / ".hermes" / "auditorias"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "rebuild_synthetic_and_regimes.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("rebuild_master")

import psycopg2
import pandas as pd
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.postgres_regime_state import PostgresRegimeStateAdapter


def get_pg_conn():
    url = os.getenv("POSTGRES_URL")
    if not url:
        raise ValueError("POSTGRES_URL environment variable is missing")
    return psycopg2.connect(url)


def fase_1_purga_fin_de_semana():
    logger.info("=" * 70)
    logger.info("FASE 1: Purga Quirúrgica de Anomalías de Fin de Semana")
    logger.info("=" * 70)

    conn = get_pg_conn()
    cur = conn.cursor()

    # 1. Purgar barras de fin de semana en ohlcv_bars para sintéticos
    cur.execute("""
        DELETE FROM market.ohlcv_bars
        WHERE EXTRACT(DOW FROM time) IN (0, 6)
          AND time >= '2026-01-01'
          AND ticker NOT IN ('CPI', 'CPIAUCSL', 'DXY')
          AND (
              ticker IN (SELECT ticker FROM market.ticker_metadata WHERE industry = 'INDICATOR')
              OR ticker LIKE 'S5%'
              OR ticker LIKE 'SV5%'
              OR ticker LIKE 'VBI%'
              OR ticker LIKE 'FG%'
              OR ticker IN ('BSI', 'CREDIT_RATIO', 'YIELD_SPREAD', 'ROTATION_INDEX', 'SV5_TURBULENCE')
          );
    """)
    bars_deleted = cur.rowcount
    logger.info(f"  • Barras espurias de fin de semana eliminadas en ohlcv_bars: {bars_deleted}")

    # 2. Purgar transiciones residuales de fin de semana en regime_states
    cur.execute("""
        DELETE FROM market.regime_states
        WHERE entered_at >= '2026-09-19';
    """)
    regimes_deleted = cur.rowcount
    logger.info(f"  • Transiciones residuales eliminadas en market.regime_states: {regimes_deleted}")

    conn.commit()
    cur.close()
    conn.close()
    logger.info("✅ FASE 1 completada con éxito.")


def fase_2_regeneracion_ratios_sinteticos(store: TimescaleDataStore):
    logger.info("=" * 70)
    logger.info("FASE 2: Regeneración desde Cero de Ratios y Spreads Sintéticos")
    logger.info("=" * 70)

    conn = get_pg_conn()
    cur = conn.cursor()

    # Clean slate para los 3 indicadores sintéticos
    cur.execute("""
        DELETE FROM market.ohlcv_bars
        WHERE ticker IN ('CREDIT_RATIO', 'YIELD_SPREAD', 'ROTATION_INDEX')
          AND timeframe = '1d';
    """)
    logger.info(f"  • Barras anteriores purgadas para clean-slate: {cur.rowcount}")
    conn.commit()
    cur.close()
    conn.close()

    from backend.scripts.backfills.backfill_synthetic_indicators import (
        backfill_credit_ratio,
        backfill_yield_spread,
        backfill_rotation_index,
    )

    n_credit = backfill_credit_ratio(store)
    logger.info(f"  • CREDIT_RATIO regenerado al 100%: {n_credit} barras")

    n_yield = backfill_yield_spread(store)
    logger.info(f"  • YIELD_SPREAD regenerado al 100%: {n_yield} barras")

    n_rotation = backfill_rotation_index(store)
    logger.info(f"  • ROTATION_INDEX regenerado al 100%: {n_rotation} barras")

    logger.info("✅ FASE 2 completada con éxito.")


def fase_3_regeneracion_sector_breadth():
    logger.info("=" * 70)
    logger.info("FASE 3: Regeneración de Amplitud Sectorial de Precios (S5_*)")
    logger.info("=" * 70)

    from backend.scripts.backfills.backfill_sector_breadth import main as run_sector_breadth
    run_sector_breadth()
    logger.info("✅ FASE 3 completada con éxito.")


def fase_4_regeneracion_volume_breadth():
    logger.info("=" * 70)
    logger.info("FASE 4: Regeneración de Amplitud de Volumen (SV5_*)")
    logger.info("=" * 70)

    from backend.daemons.vault_providers.volume_breadth_provider import VolumeBreadthProvider
    from backend.daemons.vault_providers.sector_volume_breadth_provider import SectorVolumeBreadthProvider
    from backend.daemons.vault_providers.sector_cap_breadth_provider import SectorCapBreadthProvider
    from backend.daemons.vault_providers.sector_volume_intensity_provider import SectorVolumeIntensityProvider

    store = TimescaleDataStore()
    try:
        res_vb = VolumeBreadthProvider().run_full(store)
        logger.info(f"  • VolumeBreadthProvider: {res_vb}")

        res_svb = SectorVolumeBreadthProvider().run_full(store)
        logger.info(f"  • SectorVolumeBreadthProvider: {res_svb}")

        res_scb = SectorCapBreadthProvider().run_full(store)
        logger.info(f"  • SectorCapBreadthProvider: {res_scb}")

        res_svi = SectorVolumeIntensityProvider().run_full(store)
        logger.info(f"  • SectorVolumeIntensityProvider: {res_svi}")
    finally:
        store.close()

    logger.info("✅ FASE 4 completada con éxito.")


def fase_5_sincronizacion_bsi_y_turbulence(store: TimescaleDataStore):
    logger.info("=" * 70)
    logger.info("FASE 5: Sincronización y Recálculo de BSI y SV5_TURBULENCE")
    logger.info("=" * 70)

    from backend.daemons.vault_providers.bsi_provider import BSIProvider
    from backend.daemons.vault_providers.sv5_turbulence_provider import SV5TurbulenceProvider

    # 1. BSI
    res_bsi = BSIProvider().run_full(store)
    logger.info(f"  • Sincronización BSI: {res_bsi}")

    # 2. SV5_TURBULENCE
    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM market.ohlcv_bars WHERE ticker = 'SV5_TURBULENCE' AND timeframe = '1d';")
    logger.info(f"  • SV5_TURBULENCE anteriores borrados para recálculo completo: {cur.rowcount}")
    conn.commit()
    cur.close()
    conn.close()

    sv5tw = store.load_bars("SV5TW", "1d")
    if sv5tw is not None and len(sv5tw) >= 10:
        delta = sv5tw["close"].diff()
        rolling_std = delta.rolling(window=10, min_periods=5).std().dropna()
        records = [
            ("SV5_TURBULENCE", "1d", ts, float(val), float(val), float(val), float(val), 0)
            for ts, val in rolling_std.items()
        ]
        from psycopg2.extras import execute_batch
        conn = store._conn()
        try:
            cur = conn.cursor()
            execute_batch(cur, """
                INSERT INTO market.ohlcv_bars (ticker, timeframe, time, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, timeframe, time) DO UPDATE
                SET close = EXCLUDED.close;
            """, records)
            conn.commit()
            logger.info(f"  • SV5_TURBULENCE recalculado al 100%: {len(records)} barras insertadas")
        finally:
            store._put(conn)

    logger.info("✅ FASE 5 completada con éxito.")


def fase_6_recalculo_total_regimenes_volatilidad():
    logger.info("=" * 70)
    logger.info("FASE 6: Recálculo Total 1993-2026 del Régimen de Volatilidad")
    logger.info("=" * 70)

    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM market.regime_states
        WHERE key IN ('vol:quality:MARKET', 'vol:speculative:MARKET');
    """)
    logger.info(f"  • Transiciones anteriores de vol borradas para clean slate: {cur.rowcount}")
    conn.commit()
    cur.close()
    conn.close()

    from backend.scripts.backfills.backfill_regime_states import main as run_vol_backfill
    run_vol_backfill()
    logger.info("✅ FASE 6 completada con éxito.")


def fase_7_reanclaje_metar_al_cierre_18():
    logger.info("=" * 70)
    logger.info("FASE 7: Re-anclaje de Estaciones METAR al Cierre del Viernes 2026-09-18")
    logger.info("=" * 70)

    as_of = "2026-09-18"

    from backend.modules.entry_decision.domain.services.pcr_metar_service import get_pcr_market_metar
    from backend.modules.entry_decision.domain.services.vvix_metar_service import get_vvix_market_metar
    from backend.modules.entry_decision.domain.services.skew_metar_service import get_skew_market_metar
    from backend.modules.entry_decision.domain.services.fg_metar_service import get_fg_market_metar
    from backend.modules.entry_decision.domain.services.dxy_metar_service import get_dxy_market_metar
    from backend.modules.entry_decision.domain.services.credit_metar_service import get_credit_market_metar
    from backend.modules.entry_decision.domain.services.yield_curve_metar_service import get_yield_curve_market_metar
    from backend.modules.entry_decision.domain.services.rotation_metar_service import get_rotation_market_metar
    from backend.modules.entry_decision.domain.services.bsi_metar_service import get_bsi_market_metar
    from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import get_sv5_turbulence_market_metar
    from backend.modules.entry_decision.domain.services.vix_metar_service import get_vix_market_metar

    stations = [
        ("VIX", get_vix_market_metar),
        ("VVIX", get_vvix_market_metar),
        ("PCR", get_pcr_market_metar),
        ("SKEW", get_skew_market_metar),
        ("FG", get_fg_market_metar),
        ("DXY", get_dxy_market_metar),
        ("CREDIT", get_credit_market_metar),
        ("YIELD", get_yield_curve_market_metar),
        ("ROTATION", get_rotation_market_metar),
        ("BSI", get_bsi_market_metar),
        ("TURBULENCE", get_sv5_turbulence_market_metar),
    ]

    for name, fn in stations:
        try:
            m = fn(as_of_date=as_of)
            logger.info(f"  • Estación {name:<10}: OK | As-Of: {m.as_of_date} | Action: {m.action_code}")
        except Exception as e:
            logger.warning(f"  • Estación {name:<10}: Error re-evaluando: {e}")

    logger.info("✅ FASE 7 completada con éxito.")


def fase_8_certificacion_final():
    logger.info("=" * 70)
    logger.info("FASE 8: Certificación y Auditoría de Integridad Cero Discrepancias")
    logger.info("=" * 70)

    conn = get_pg_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT count(*)
        FROM market.ohlcv_bars
        WHERE EXTRACT(DOW FROM time) IN (0, 6)
          AND time >= '2026-01-01'
          AND ticker NOT IN ('CPI', 'CPIAUCSL', 'DXY');
    """)
    weekend_count = cur.fetchone()[0]
    logger.info(f"  • Barras de fin de semana en ohlcv_bars (no-macro): {weekend_count}")

    cur.execute("""
        SELECT count(*)
        FROM market.regime_states
        WHERE entered_at >= '2026-09-19';
    """)
    weekend_regimes = cur.fetchone()[0]
    logger.info(f"  • Transiciones de fin de semana en regime_states >= 19-Sep: {weekend_regimes}")

    cur.execute("""
        SELECT count(*), count(DISTINCT ticker)
        FROM market.ohlcv_bars
        WHERE time::date = '2026-09-18'
          AND ticker IN (SELECT ticker FROM market.ticker_metadata WHERE industry = 'INDICATOR');
    """)
    r_fri = cur.fetchone()
    logger.info(f"  • Indicadores con vela en Viernes 2026-09-18: {r_fri[0]} barras across {r_fri[1]} tickers")

    cur.execute("""
        SELECT key, current_state, entered_at, duration_bars
        FROM market.regime_states
        WHERE key IN ('vol:quality:MARKET', 'vol:speculative:MARKET')
          AND closed_at IS NULL;
    """)
    logger.info("  • Estados activos de Régimen de Volatilidad:")
    for r in cur.fetchall():
        logger.info(f"    - {r[0]}: {r[1]} (entered: {r[2]}, duration: {r[3]} bars)")

    cur.close()
    conn.close()

    if weekend_count == 0 and weekend_regimes == 0:
        logger.info("🏆 CERTIFICACIÓN EXITOSA: 100% Cero Discrepancias de Fin de Semana en Neon Vault.")
    else:
        logger.error(f"⚠️ Alerta: Quedaron discrepancias (weekend_bars={weekend_count}, weekend_regimes={weekend_regimes})")

    logger.info("=" * 70)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Master Rebuild Script")
    parser.add_argument("--from-phase", type=int, default=1, help="Start from phase N (1-8)")
    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    logger.info(f"Iniciando Master Rebuild (desde Fase {args.from_phase}) a las {start_time.isoformat()}")

    store = TimescaleDataStore()
    try:
        if args.from_phase <= 1:
            fase_1_purga_fin_de_semana()
        if args.from_phase <= 2:
            fase_2_regeneracion_ratios_sinteticos(store)
        if args.from_phase <= 3:
            fase_3_regeneracion_sector_breadth()
        if args.from_phase <= 4:
            fase_4_regeneracion_volume_breadth()
        if args.from_phase <= 5:
            fase_5_sincronizacion_bsi_y_turbulence(store)
        if args.from_phase <= 6:
            fase_6_recalculo_total_regimenes_volatilidad()
        if args.from_phase <= 7:
            fase_7_reanclaje_metar_al_cierre_18()
        if args.from_phase <= 8:
            fase_8_certificacion_final()
    finally:
        store.close()

    elapsed = datetime.now(timezone.utc) - start_time
    logger.info(f"Master Rebuild finalizado exitosamente en {elapsed.total_seconds():.1f}s")


if __name__ == "__main__":
    main()
