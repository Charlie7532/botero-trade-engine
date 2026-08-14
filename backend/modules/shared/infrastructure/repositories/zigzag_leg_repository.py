import logging
import math
from datetime import datetime, UTC
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd

from backend.modules.shared.domain.entities.zigzag_leg import ZigzagLeg
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


class ZigzagLegRepository:
    """
    Repositorio de infraestructura para consultar y guardar tramos de ZigZag en Neon Vault.
    Clean Architecture: Infrastructure Adapter.
    """

    def __init__(self, store: Optional[TimescaleDataStore] = None):
        self.store = store or TimescaleDataStore()

    def get_confirmed_legs(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> List[ZigzagLeg]:
        """
        Obtiene los tramos confirmados de un ticker para una escala específica.
        Si se pasa `as_of_date`, aplica un filtro causal estricto:
        `confirmed_at_timestamp <= as_of_date`.
        """
        conn = self.store._conn()
        try:
            query = """
                SELECT 
                    ticker, scale, leg_id,
                    start_timestamp, start_type, start_price,
                    end_timestamp, end_type, end_price,
                    confirmed_at_timestamp, status,
                    prev_leg_return, prev_leg_duration
                FROM market.zigzag_legs
                WHERE ticker = %s AND scale = %s
            """
            params = [ticker, scale]

            if as_of_date:
                query += " AND confirmed_at_timestamp <= %s"
                params.append(as_of_date)

            query += " ORDER BY start_timestamp ASC;"

            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

            legs = []
            for r in rows:
                tkr, sc, lid, s_ts, s_type, s_px, e_ts, e_type, e_px, c_ts, st, plr, pld = r
                leg = ZigzagLeg(
                    ticker=tkr,
                    scale=sc,
                    leg_id=lid,
                    start_timestamp=s_ts,
                    start_type=s_type,
                    start_price=float(s_px),
                    end_timestamp=e_ts,
                    end_type=e_type,
                    end_price=float(e_px),
                    confirmed_at_timestamp=c_ts,
                    status=st,
                    prev_leg_return=float(plr) if plr is not None else None,
                    prev_leg_duration=int(pld) if pld is not None else None,
                )
                legs.append(leg)

            return legs
        except Exception as e:
            logger.error(f"❌ Error al consultar tramos de ZigZag para {ticker} ({scale}): {e}")
            return []
        finally:
            self.store._put(conn)

    def get_latest_confirmed_leg(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> Optional[ZigzagLeg]:
        """Obtiene el último tramo confirmado para un ticker y escala."""
        legs = self.get_confirmed_legs(ticker, scale, as_of_date)
        return legs[-1] if legs else None

    def save_legs(self, legs: List[ZigzagLeg]) -> int:
        """Guarda o actualiza tramos de ZigZag en Neon Vault (UPSERT)."""
        if not legs:
            return 0

        conn = self.store._conn()
        try:
            sql = """
                INSERT INTO market.zigzag_legs (
                    ticker, scale, leg_id,
                    start_timestamp, start_type, start_price,
                    end_timestamp, end_type, end_price,
                    confirmed_at_timestamp, status,
                    prev_leg_return, prev_leg_duration
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, scale, leg_id) DO UPDATE SET
                    start_price = EXCLUDED.start_price,
                    end_price = EXCLUDED.end_price,
                    confirmed_at_timestamp = EXCLUDED.confirmed_at_timestamp,
                    status = EXCLUDED.status,
                    prev_leg_return = EXCLUDED.prev_leg_return,
                    prev_leg_duration = EXCLUDED.prev_leg_duration;
            """

            tuples = [
                (
                    l.ticker,
                    l.scale,
                    l.leg_id,
                    l.start_timestamp,
                    l.start_type,
                    l.start_price,
                    l.end_timestamp,
                    l.end_type,
                    l.end_price,
                    l.confirmed_at_timestamp,
                    l.status,
                    l.prev_leg_return,
                    l.prev_leg_duration,
                )
                for l in legs
            ]

            with conn.cursor() as cur:
                cur.executemany(sql, tuples)
            conn.commit()
            return len(legs)
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error al guardar {len(legs)} tramos de ZigZag: {e}")
            raise
        finally:
            self.store._put(conn)

    def get_confirmed_legs_with_indicators(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Enriquece los tramos confirmados de un ticker con VIX, PCR y SKEW al inicio y fin del tramo.
        Realiza una consulta rápida de la tabla de tramos y hace el map en memoria con Pandas.
        """
        conn = self.store._conn()
        try:
            query = """
                SELECT 
                    ticker, scale, leg_id,
                    start_timestamp, start_type, start_price,
                    end_timestamp, end_type, end_price,
                    confirmed_at_timestamp, status,
                    prev_leg_return, prev_leg_duration
                FROM market.zigzag_legs
                WHERE ticker = %s AND scale = %s
            """
            params = [ticker, scale]
            if as_of_date:
                query += " AND confirmed_at_timestamp <= %s"
                params.append(as_of_date)
            
            query += " ORDER BY start_timestamp ASC;"
            
            df = pd.read_sql(query, conn, params=params)
            if df.empty:
                return df
        finally:
            self.store._put(conn)

        vix_bars = self.store.load_bars("VIX", "1d")
        pcr_bars = self.store.load_bars("CBOE_PCR", "1d")
        skew_bars = self.store.load_bars("SKEW", "1d")

        vix_dict = vix_bars["close"].to_dict() if vix_bars is not None and not vix_bars.empty else {}
        pcr_dict = pcr_bars["close"].to_dict() if pcr_bars is not None and not pcr_bars.empty else {}
        skew_dict = skew_bars["close"].to_dict() if skew_bars is not None and not skew_bars.empty else {}

        df["start_dt"] = pd.to_datetime(df["start_timestamp"]).dt.tz_localize(None)
        df["end_dt"] = pd.to_datetime(df["end_timestamp"]).dt.tz_localize(None)

        df["vix_at_start"] = df["start_dt"].map(vix_dict)
        df["vix_at_end"] = df["end_dt"].map(vix_dict)
        df["pcr_at_start"] = df["start_dt"].map(pcr_dict)
        df["pcr_at_end"] = df["end_dt"].map(pcr_dict)
        df["skew_at_start"] = df["start_dt"].map(skew_dict)
        df["skew_at_end"] = df["end_dt"].map(skew_dict)

        df["duration_bars"] = (pd.to_datetime(df["end_timestamp"]) - pd.to_datetime(df["start_timestamp"])).dt.days
        df["duration_bars"] = df["duration_bars"].clip(lower=1)
        df["confirmation_lag_bars"] = (pd.to_datetime(df["confirmed_at_timestamp"]) - pd.to_datetime(df["end_timestamp"])).dt.days
        df["confirmation_lag_bars"] = df["confirmation_lag_bars"].clip(lower=0)
        df["log_return"] = np.log(df["end_price"] / df["start_price"]) * 100.0

        # Cargar volatilidad diaria del ticker (std dev logarítmica de 20d) para normalización adimensional (Sigmas σ)
        ticker_bars = self.store.load_bars(ticker, "1d")
        if ticker_bars is not None and not ticker_bars.empty and len(ticker_bars) > 20:
            daily_std_pct = float(ticker_bars["close"].pct_change().dropna().std() * 100.0)
        else:
            daily_std_pct = 1.50 # Fallback SPY standard

        df["daily_std_pct"] = daily_std_pct
        df["sigma_return"] = df["log_return"] / (daily_std_pct * np.sqrt(df["duration_bars"]))

        return df

    def get_confirmed_legs_dataframe(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Obtiene un DataFrame con los tramos confirmados y todas sus métricas calculadas.
        """
        legs = self.get_confirmed_legs(ticker, scale, as_of_date)
        if not legs:
            return pd.DataFrame()

        records = []
        for l in legs:
            records.append({
                "ticker": l.ticker,
                "scale": l.scale,
                "leg_id": l.leg_id,
                "start_timestamp": l.start_timestamp,
                "start_type": l.start_type,
                "start_price": l.start_price,
                "end_timestamp": l.end_timestamp,
                "end_type": l.end_type,
                "end_price": l.end_price,
                "confirmed_at_timestamp": l.confirmed_at_timestamp,
                "status": l.status,
                "duration_bars": l.duration_bars,
                "confirmation_lag_bars": l.confirmation_lag_bars,
                "theoretical_return_pct": l.theoretical_return_pct,
                "log_return": l.log_return,
                "daily_return_pct": l.daily_return_pct,
            })

        return pd.DataFrame(records)
