#!/usr/bin/env python3
"""
Gate Sanity & Divergence Cleaner for Channel Snapshots & Observer
================================================================
Enforces the mandatory institutional gate before P1-A:
1. Sanea la FUENTE primero: vwap_sigma_wave (|v| > 10.0) y re-alinea tension_wave = sigma_wave
2. Sanea los DERIVADOS con umbrales per-columna:
   - obs_vel_svw (|v| > 10.0)
   - obs_vel_tension_w (|v| > 10.0)
   - obs_vel_sigma_c (|v| > 10.0)
   - obs_vel_conj_wt (|v| > 10.0)
   - obs_vel_rsi (|v| > 100.0)
   - obs_velocity_norm (|v| > 20.0)
3. Doble verificación estricta de cero violaciones en las 7 métricas en Neon.
"""
import logging
import sys
from dotenv import load_dotenv
load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_gate_cleanup() -> bool:
    store = TimescaleDataStore()
    conn = store._conn()

    try:
        # ── VERIFICACIÓN 1: Diagnóstico previo en Neon ──
        logger.info("=== PASO 1: DIAGNÓSTICO PRE-LIMPIEZA (7 Columnas: Fuente + Derivados) ===")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE ABS(vwap_sigma_wave) > 10)    AS fuente,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_svw) > 10)        AS svw,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_tension_w) > 10)  AS tension,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_sigma_c) > 10)    AS sigma_c,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_conj_wt) > 10)    AS conj_wt,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_rsi) > 100)       AS rsi,
                    COUNT(*) FILTER (WHERE ABS(obs_velocity_norm) > 20)  AS norm
                FROM engine.channel_snapshots;
            """)
            fuente, svw, tension, sigma_c, conj_wt, rsi, norm = cur.fetchone()
            logger.info(f"  [1.a] vwap_sigma_wave > 10.0:  {fuente:,}")
            logger.info(f"  [1.b] obs_vel_svw > 10.0:        {svw:,}")
            logger.info(f"  [1.c] obs_vel_tension_w > 10.0: {tension:,}")
            logger.info(f"  [1.d] obs_vel_sigma_c > 10.0:   {sigma_c:,}")
            logger.info(f"  [1.e] obs_vel_conj_wt > 10.0:   {conj_wt:,}")
            logger.info(f"  [1.f] obs_vel_rsi > 100.0:       {rsi:,}")
            logger.info(f"  [1.g] obs_velocity_norm > 20.0: {norm:,}")

        # ── PASO 2: LIMPIEZA ATÓMICA EN NEON ──
        logger.info("\n=== PASO 2: EJECUTANDO SANEO EN NEON ===")
        with conn.cursor() as cur:
            # 2.a: Saneo de la FUENTE primero
            if fuente > 0:
                logger.info(f"  Saneando FUENTE: vwap_sigma_wave > 10.0 ({fuente:,} filas)...")
                cur.execute("""
                    UPDATE engine.channel_snapshots
                    SET vwap_sigma_wave = 0.0,
                        tension_wave = sigma_wave
                    WHERE ABS(vwap_sigma_wave) > 10.0;
                """)
                src_updated = cur.rowcount
                logger.info(f"  -> Fuente saneada: {src_updated:,} filas actualizadas.")

            # 2.b: Saneo de los DERIVADOS con umbrales per-columna (CASE)
            total_deriv = svw + tension + sigma_c + conj_wt + rsi + norm
            if total_deriv > 0:
                logger.info(f"  Saneando DERIVADOS: umbrales per-columna ({total_deriv:,} banderas)...")
                cur.execute("""
                    UPDATE engine.channel_snapshots SET
                        obs_vel_svw = CASE WHEN ABS(obs_vel_svw) > 10.0 THEN 0.0 ELSE obs_vel_svw END,
                        obs_vel_tension_w = CASE WHEN ABS(obs_vel_tension_w) > 10.0 THEN 0.0 ELSE obs_vel_tension_w END,
                        obs_vel_sigma_c = CASE WHEN ABS(obs_vel_sigma_c) > 10.0 THEN 0.0 ELSE obs_vel_sigma_c END,
                        obs_vel_conj_wt = CASE WHEN ABS(obs_vel_conj_wt) > 10.0 THEN 0.0 ELSE obs_vel_conj_wt END,
                        obs_vel_rsi = CASE WHEN ABS(obs_vel_rsi) > 100.0 THEN 0.0 ELSE obs_vel_rsi END,
                        obs_velocity_norm = CASE WHEN ABS(obs_velocity_norm) > 20.0 THEN 0.0 ELSE obs_velocity_norm END
                    WHERE ABS(obs_vel_svw) > 10.0
                       OR ABS(obs_vel_tension_w) > 10.0
                       OR ABS(obs_vel_sigma_c) > 10.0
                       OR ABS(obs_vel_conj_wt) > 10.0
                       OR ABS(obs_vel_rsi) > 100.0
                       OR ABS(obs_velocity_norm) > 20.0;
                """)
                deriv_updated = cur.rowcount
                logger.info(f"  -> Derivados saneados: {deriv_updated:,} filas actualizadas.")

        conn.commit()
        logger.info("  Commit exitoso en Neon.")

        # ── PASO 3: DOBLE VERIFICACIÓN POST-LIMPIEZA (Tolerancia Cero en 7 Métricas) ──
        logger.info("\n=== PASO 3: DOBLE VERIFICACIÓN POST-LIMPIEZA (GATE) ===")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE ABS(vwap_sigma_wave) > 10)    AS fuente,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_svw) > 10)        AS svw,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_tension_w) > 10)  AS tension,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_sigma_c) > 10)    AS sigma_c,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_conj_wt) > 10)    AS conj_wt,
                    COUNT(*) FILTER (WHERE ABS(obs_vel_rsi) > 100)       AS rsi,
                    COUNT(*) FILTER (WHERE ABS(obs_velocity_norm) > 20)  AS norm
                FROM engine.channel_snapshots;
            """)
            r = cur.fetchone()
            logger.info(f"  [Verif Gate] fuente={r[0]}, svw={r[1]}, tension={r[2]}, sigma_c={r[3]}, conj_wt={r[4]}, rsi={r[5]}, norm={r[6]}")

        total_violations = sum(r)
        if total_violations == 0:
            logger.info("\n✅ GATE STATUS: PASS (Las 7 columnas están en 0). Saneamiento verificado al 100%. Desbloqueado para P1-A.")
            return True
        else:
            logger.error(f"\n❌ GATE STATUS: FAIL ({total_violations} violaciones residuales). P1-A BLOQUEADO.")
            return False

    finally:
        store._put(conn)
        store.close()


if __name__ == "__main__":
    success = run_gate_cleanup()
    sys.exit(0 if success else 1)


