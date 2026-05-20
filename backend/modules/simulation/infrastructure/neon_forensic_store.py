import json
import logging
import os
from dataclasses import asdict
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from backend.modules.simulation.domain.entities.signal_forensic_label import SignalForensicLabel
from backend.modules.simulation.domain.entities.entry_report_card import EntryReportCard
from backend.modules.simulation.domain.entities.exit_report_card import ExitReportCard
from backend.modules.simulation.domain.ports.forensic_store_port import ForensicStorePort

logger = logging.getLogger(__name__)

_DDL = """
CREATE SCHEMA IF NOT EXISTS engine;

CREATE TABLE IF NOT EXISTS engine.entry_forensic_labels (
    ticker             TEXT NOT NULL,
    signal_name        TEXT NOT NULL,
    signal_direction   INT NOT NULL,
    signal_confidence  FLOAT NOT NULL,
    signal_time        TIMESTAMPTZ NOT NULL,
    signal_price       FLOAT NOT NULL,
    classification     TEXT NOT NULL,
    failure_diagnosis  TEXT,
    foreseeability     TEXT,
    snapshot           JSONB,
    horizons           JSONB,
    PRIMARY KEY (ticker, signal_name, signal_time)
);

CREATE TABLE IF NOT EXISTS engine.exit_forensic_labels (
    ticker             TEXT NOT NULL,
    signal_name        TEXT NOT NULL,
    signal_direction   INT NOT NULL,
    signal_confidence  FLOAT NOT NULL,
    signal_time        TIMESTAMPTZ NOT NULL,
    signal_price       FLOAT NOT NULL,
    classification     TEXT NOT NULL,
    failure_diagnosis  TEXT,
    foreseeability     TEXT,
    snapshot           JSONB,
    horizons           JSONB,
    PRIMARY KEY (ticker, signal_name, signal_time)
);

CREATE TABLE IF NOT EXISTS engine.entry_report_cards (
    ticker                     TEXT NOT NULL,
    signal_name                TEXT NOT NULL,
    n_signals                  INT NOT NULL,
    classification_dist        JSONB,
    classification_pct         JSONB,
    golden_rate                FLOAT,
    trap_rate                  FLOAT,
    false_rate                 FLOAT,
    miss_rate                  FLOAT,
    avg_return_by_horizon      JSONB,
    wr_by_horizon              JSONB,
    edge_ratio_10              FLOAT,
    avg_mfe_10                 FLOAT,
    avg_mae_10                 FLOAT,
    foreseeable_pct            FLOAT,
    failure_breakdown          JSONB,
    foreseeability_breakdown   JSONB,
    top_lesson                 TEXT,
    golden_rate_by_fear        JSONB,
    golden_rate_by_vol_regime  JSONB,
    golden_rate_by_weinstein   JSONB,
    grade                      TEXT,
    verdict                    TEXT,
    created_at                 TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, signal_name)
);

CREATE TABLE IF NOT EXISTS engine.exit_report_cards (
    ticker                     TEXT NOT NULL,
    signal_name                TEXT NOT NULL,
    n_signals                  INT NOT NULL,
    classification_dist        JSONB,
    classification_pct         JSONB,
    save_rate                  FLOAT,
    early_rate                 FLOAT,
    false_alarm_rate           FLOAT,
    missed_upside_rate         FLOAT,
    neutral_rate               FLOAT,
    avg_avoided_loss           JSONB,
    avg_missed_gain            JSONB,
    cost_of_false_alarms       FLOAT,
    cost_of_missed_upside      FLOAT,
    net_exit_value             FLOAT,
    foreseeable_pct            FLOAT,
    failure_breakdown          JSONB,
    foreseeability_breakdown   JSONB,
    top_lesson                 TEXT,
    save_rate_by_fear          JSONB,
    save_rate_by_vol_regime    JSONB,
    false_alarm_rate_by_fear   JSONB,
    grade                      TEXT,
    verdict                    TEXT,
    created_at                 TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, signal_name)
);
"""

def _to_native(val):
    """Convert numpy and custom objects to Python native types for JSON serialization."""
    import numpy as np
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, dict):
        return {k: _to_native(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_to_native(v) for v in val]
    return val

class NeonForensicStore(ForensicStorePort):
    """Neon PostgreSQL implementation of ForensicStorePort."""

    def __init__(self, dsn: Optional[str] = None):
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=3,
            dsn=dsn or os.environ.get("POSTGRES_URL", ""),
        )
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Create the forensic tables if they do not exist."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(_DDL)
            conn.commit()
            logger.info("NeonForensicStore: schemas and tables ensured successfully")
        except Exception as e:
            conn.rollback()
            logger.error(f"NeonForensicStore DDL execution failed: {e}")
            raise
        finally:
            self._pool.putconn(conn)

    def save_entry_labels(self, labels: list[SignalForensicLabel]) -> None:
        """Upsert a list of entry forensic labels to engine.entry_forensic_labels."""
        if not labels:
            return
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                for lbl in labels:
                    snapshot_dict = _to_native(asdict(lbl.snapshot))
                    horizons_dict = _to_native({k: asdict(v) for k, v in lbl.horizons.items()})

                    cur.execute("""
                        INSERT INTO engine.entry_forensic_labels (
                            ticker, signal_name, signal_direction, signal_confidence,
                            signal_time, signal_price, classification, failure_diagnosis,
                            foreseeability, snapshot, horizons
                        ) VALUES (
                            %(ticker)s, %(signal_name)s, %(signal_direction)s, %(signal_confidence)s,
                            %(signal_time)s, %(signal_price)s, %(classification)s, %(failure_diagnosis)s,
                            %(foreseeability)s, %(snapshot)s, %(horizons)s
                        ) ON CONFLICT (ticker, signal_name, signal_time) DO UPDATE SET
                            signal_confidence = EXCLUDED.signal_confidence,
                            signal_price = EXCLUDED.signal_price,
                            classification = EXCLUDED.classification,
                            failure_diagnosis = EXCLUDED.failure_diagnosis,
                            foreseeability = EXCLUDED.foreseeability,
                            snapshot = EXCLUDED.snapshot,
                            horizons = EXCLUDED.horizons
                    """, {
                        "ticker": lbl.ticker,
                        "signal_name": lbl.signal_name,
                        "signal_direction": lbl.signal_direction,
                        "signal_confidence": lbl.signal_confidence,
                        "signal_time": lbl.signal_time,
                        "signal_price": lbl.signal_price,
                        "classification": lbl.classification,
                        "failure_diagnosis": lbl.failure_diagnosis,
                        "foreseeability": lbl.foreseeability,
                        "snapshot": json.dumps(snapshot_dict),
                        "horizons": json.dumps(horizons_dict)
                    })
            conn.commit()
            logger.info(f"NeonForensicStore: saved {len(labels)} entry labels")
        except Exception as e:
            conn.rollback()
            logger.error(f"NeonForensicStore: failed to save entry labels: {e}")
            raise
        finally:
            self._pool.putconn(conn)

    def save_exit_labels(self, labels: list[SignalForensicLabel]) -> None:
        """Upsert a list of exit forensic labels to engine.exit_forensic_labels."""
        if not labels:
            return
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                for lbl in labels:
                    snapshot_dict = _to_native(asdict(lbl.snapshot))
                    horizons_dict = _to_native({k: asdict(v) for k, v in lbl.horizons.items()})

                    cur.execute("""
                        INSERT INTO engine.exit_forensic_labels (
                            ticker, signal_name, signal_direction, signal_confidence,
                            signal_time, signal_price, classification, failure_diagnosis,
                            foreseeability, snapshot, horizons
                        ) VALUES (
                            %(ticker)s, %(signal_name)s, %(signal_direction)s, %(signal_confidence)s,
                            %(signal_time)s, %(signal_price)s, %(classification)s, %(failure_diagnosis)s,
                            %(foreseeability)s, %(snapshot)s, %(horizons)s
                        ) ON CONFLICT (ticker, signal_name, signal_time) DO UPDATE SET
                            signal_confidence = EXCLUDED.signal_confidence,
                            signal_price = EXCLUDED.signal_price,
                            classification = EXCLUDED.classification,
                            failure_diagnosis = EXCLUDED.failure_diagnosis,
                            foreseeability = EXCLUDED.foreseeability,
                            snapshot = EXCLUDED.snapshot,
                            horizons = EXCLUDED.horizons
                    """, {
                        "ticker": lbl.ticker,
                        "signal_name": lbl.signal_name,
                        "signal_direction": lbl.signal_direction,
                        "signal_confidence": lbl.signal_confidence,
                        "signal_time": lbl.signal_time,
                        "signal_price": lbl.signal_price,
                        "classification": lbl.classification,
                        "failure_diagnosis": lbl.failure_diagnosis,
                        "foreseeability": lbl.foreseeability,
                        "snapshot": json.dumps(snapshot_dict),
                        "horizons": json.dumps(horizons_dict)
                    })
            conn.commit()
            logger.info(f"NeonForensicStore: saved {len(labels)} exit labels")
        except Exception as e:
            conn.rollback()
            logger.error(f"NeonForensicStore: failed to save exit labels: {e}")
            raise
        finally:
            self._pool.putconn(conn)

    def save_entry_report_card(self, card: EntryReportCard) -> None:
        """Upsert an entry report card to engine.entry_report_cards."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO engine.entry_report_cards (
                        ticker, signal_name, n_signals, classification_dist, classification_pct,
                        golden_rate, trap_rate, false_rate, miss_rate, avg_return_by_horizon,
                        wr_by_horizon, edge_ratio_10, avg_mfe_10, avg_mae_10, foreseeable_pct,
                        failure_breakdown, foreseeability_breakdown, top_lesson, golden_rate_by_fear,
                        golden_rate_by_vol_regime, golden_rate_by_weinstein, grade, verdict, created_at
                    ) VALUES (
                        %(ticker)s, %(signal_name)s, %(n_signals)s, %(classification_dist)s, %(classification_pct)s,
                        %(golden_rate)s, %(trap_rate)s, %(false_rate)s, %(miss_rate)s, %(avg_return_by_horizon)s,
                        %(wr_by_horizon)s, %(edge_ratio_10)s, %(avg_mfe_10)s, %(avg_mae_10)s, %(foreseeable_pct)s,
                        %(failure_breakdown)s, %(foreseeability_breakdown)s, %(top_lesson)s, %(golden_rate_by_fear)s,
                        %(golden_rate_by_vol_regime)s, %(golden_rate_by_weinstein)s, %(grade)s, %(verdict)s, NOW()
                    ) ON CONFLICT (ticker, signal_name) DO UPDATE SET
                        n_signals = EXCLUDED.n_signals,
                        classification_dist = EXCLUDED.classification_dist,
                        classification_pct = EXCLUDED.classification_pct,
                        golden_rate = EXCLUDED.golden_rate,
                        trap_rate = EXCLUDED.trap_rate,
                        false_rate = EXCLUDED.false_rate,
                        miss_rate = EXCLUDED.miss_rate,
                        avg_return_by_horizon = EXCLUDED.avg_return_by_horizon,
                        wr_by_horizon = EXCLUDED.wr_by_horizon,
                        edge_ratio_10 = EXCLUDED.edge_ratio_10,
                        avg_mfe_10 = EXCLUDED.avg_mfe_10,
                        avg_mae_10 = EXCLUDED.avg_mae_10,
                        foreseeable_pct = EXCLUDED.foreseeable_pct,
                        failure_breakdown = EXCLUDED.failure_breakdown,
                        foreseeability_breakdown = EXCLUDED.foreseeability_breakdown,
                        top_lesson = EXCLUDED.top_lesson,
                        golden_rate_by_fear = EXCLUDED.golden_rate_by_fear,
                        golden_rate_by_vol_regime = EXCLUDED.golden_rate_by_vol_regime,
                        golden_rate_by_weinstein = EXCLUDED.golden_rate_by_weinstein,
                        grade = EXCLUDED.grade,
                        verdict = EXCLUDED.verdict,
                        created_at = NOW()
                """, {
                    "ticker": card.ticker,
                    "signal_name": card.signal_name,
                    "n_signals": card.n_signals,
                    "classification_dist": json.dumps(_to_native(card.classification_dist)),
                    "classification_pct": json.dumps(_to_native(card.classification_pct)),
                    "golden_rate": card.golden_rate,
                    "trap_rate": card.trap_rate,
                    "false_rate": card.false_rate,
                    "miss_rate": card.miss_rate,
                    "avg_return_by_horizon": json.dumps(_to_native(card.avg_return_by_horizon)),
                    "wr_by_horizon": json.dumps(_to_native(card.wr_by_horizon)),
                    "edge_ratio_10": card.edge_ratio_10,
                    "avg_mfe_10": card.avg_mfe_10,
                    "avg_mae_10": card.avg_mae_10,
                    "foreseeable_pct": card.foreseeable_pct,
                    "failure_breakdown": json.dumps(_to_native(card.failure_breakdown)),
                    "foreseeability_breakdown": json.dumps(_to_native(card.foreseeability_breakdown)),
                    "top_lesson": card.top_lesson,
                    "golden_rate_by_fear": json.dumps(_to_native(card.golden_rate_by_fear)),
                    "golden_rate_by_vol_regime": json.dumps(_to_native(card.golden_rate_by_vol_regime)),
                    "golden_rate_by_weinstein": json.dumps(_to_native(card.golden_rate_by_weinstein)),
                    "grade": card.grade,
                    "verdict": card.verdict
                })
            conn.commit()
            logger.info(f"NeonForensicStore: saved entry report card for {card.ticker} ({card.signal_name})")
        except Exception as e:
            conn.rollback()
            logger.error(f"NeonForensicStore: failed to save entry report card: {e}")
            raise
        finally:
            self._pool.putconn(conn)

    def save_exit_report_card(self, card: ExitReportCard) -> None:
        """Upsert an exit report card to engine.exit_report_cards."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO engine.exit_report_cards (
                        ticker, signal_name, n_signals, classification_dist, classification_pct,
                        save_rate, early_rate, false_alarm_rate, missed_upside_rate, neutral_rate,
                        avg_avoided_loss, avg_missed_gain, cost_of_false_alarms, cost_of_missed_upside,
                        net_exit_value, foreseeable_pct, failure_breakdown, foreseeability_breakdown,
                        top_lesson, save_rate_by_fear, save_rate_by_vol_regime, false_alarm_rate_by_fear,
                        grade, verdict, created_at
                    ) VALUES (
                        %(ticker)s, %(signal_name)s, %(n_signals)s, %(classification_dist)s, %(classification_pct)s,
                        %(save_rate)s, %(early_rate)s, %(false_alarm_rate)s, %(missed_upside_rate)s, %(neutral_rate)s,
                        %(avg_avoided_loss)s, %(avg_missed_gain)s, %(cost_of_false_alarms)s, %(cost_of_missed_upside)s,
                        %(net_exit_value)s, %(foreseeable_pct)s, %(failure_breakdown)s, %(foreseeability_breakdown)s,
                        %(top_lesson)s, %(save_rate_by_fear)s, %(save_rate_by_vol_regime)s, %(false_alarm_rate_by_fear)s,
                        %(grade)s, %(verdict)s, NOW()
                    ) ON CONFLICT (ticker, signal_name) DO UPDATE SET
                        n_signals = EXCLUDED.n_signals,
                        classification_dist = EXCLUDED.classification_dist,
                        classification_pct = EXCLUDED.classification_pct,
                        save_rate = EXCLUDED.save_rate,
                        early_rate = EXCLUDED.early_rate,
                        false_alarm_rate = EXCLUDED.false_alarm_rate,
                        missed_upside_rate = EXCLUDED.missed_upside_rate,
                        neutral_rate = EXCLUDED.neutral_rate,
                        avg_avoided_loss = EXCLUDED.avg_avoided_loss,
                        avg_missed_gain = EXCLUDED.avg_missed_gain,
                        cost_of_false_alarms = EXCLUDED.cost_of_false_alarms,
                        cost_of_missed_upside = EXCLUDED.cost_of_missed_upside,
                        net_exit_value = EXCLUDED.net_exit_value,
                        foreseeable_pct = EXCLUDED.foreseeable_pct,
                        failure_breakdown = EXCLUDED.failure_breakdown,
                        foreseeability_breakdown = EXCLUDED.foreseeability_breakdown,
                        top_lesson = EXCLUDED.top_lesson,
                        save_rate_by_fear = EXCLUDED.save_rate_by_fear,
                        save_rate_by_vol_regime = EXCLUDED.save_rate_by_vol_regime,
                        false_alarm_rate_by_fear = EXCLUDED.false_alarm_rate_by_fear,
                        grade = EXCLUDED.grade,
                        verdict = EXCLUDED.verdict,
                        created_at = NOW()
                """, {
                    "ticker": card.ticker,
                    "signal_name": card.signal_name,
                    "n_signals": card.n_signals,
                    "classification_dist": json.dumps(_to_native(card.classification_dist)),
                    "classification_pct": json.dumps(_to_native(card.classification_pct)),
                    "save_rate": card.save_rate,
                    "early_rate": card.early_rate,
                    "false_alarm_rate": card.false_alarm_rate,
                    "missed_upside_rate": card.missed_upside_rate,
                    "neutral_rate": card.neutral_rate,
                    "avg_avoided_loss": json.dumps(_to_native(card.avg_avoided_loss)),
                    "avg_missed_gain": json.dumps(_to_native(card.avg_missed_gain)),
                    "cost_of_false_alarms": card.cost_of_false_alarms,
                    "cost_of_missed_upside": card.cost_of_missed_upside,
                    "net_exit_value": card.net_exit_value,
                    "foreseeable_pct": card.foreseeable_pct,
                    "failure_breakdown": json.dumps(_to_native(card.failure_breakdown)),
                    "foreseeability_breakdown": json.dumps(_to_native(card.foreseeability_breakdown)),
                    "top_lesson": card.top_lesson,
                    "save_rate_by_fear": json.dumps(_to_native(card.save_rate_by_fear)),
                    "save_rate_by_vol_regime": json.dumps(_to_native(card.save_rate_by_vol_regime)),
                    "false_alarm_rate_by_fear": json.dumps(_to_native(card.false_alarm_rate_by_fear)),
                    "grade": card.grade,
                    "verdict": card.verdict
                })
            conn.commit()
            logger.info(f"NeonForensicStore: saved exit report card for {card.ticker} ({card.signal_name})")
        except Exception as e:
            conn.rollback()
            logger.error(f"NeonForensicStore: failed to save exit report card: {e}")
            raise
        finally:
            self._pool.putconn(conn)
