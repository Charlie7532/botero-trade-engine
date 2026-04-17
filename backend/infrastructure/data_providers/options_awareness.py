import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class OptionsAwareness:
    """
    Agente de Opciones Institucional.
    Calcula Max Pain, Put/Call Ratio, GEX Proxy, y genera
    features normalizados para la LSTM.
    """

    def get_nearest_expiration(self, symbol: str) -> Optional[str]:
        """Obtiene la fecha de expiración más cercana."""
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return None
        return expirations[0]

    def calculate_max_pain(self, symbol: str, expiration_date: Optional[str] = None) -> Optional[float]:
        """
        Calcula el Maximum Pain: el strike donde la mayor cantidad de
        opciones expirarán sin valor (worthless).
        Los Market Makers tienen incentivo para mover el precio aquí.
        """
        ticker = yf.Ticker(symbol)

        if not expiration_date:
            expiration_date = self.get_nearest_expiration(symbol)
            if not expiration_date:
                logger.error(f"No hay opciones listadas para {symbol}")
                return None

        try:
            opt_chain = ticker.option_chain(expiration_date)
            calls = opt_chain.calls
            puts = opt_chain.puts

            strikes = sorted(list(set(calls['strike']).union(set(puts['strike']))))

            max_pain = 0
            min_loss = float('inf')

            for strike in strikes:
                call_loss = calls[calls['strike'] < strike].apply(
                    lambda x: (strike - x['strike']) * x['openInterest'], axis=1
                ).sum()
                put_loss = puts[puts['strike'] > strike].apply(
                    lambda x: (x['strike'] - strike) * x['openInterest'], axis=1
                ).sum()

                total_loss = call_loss + put_loss
                if total_loss < min_loss:
                    min_loss = total_loss
                    max_pain = strike

            return max_pain

        except Exception as e:
            logger.error(f"Error calculando Max Pain para {symbol}: {e}")
            return None

    def get_put_call_ratio(self, symbol: str, expiration_date: Optional[str] = None) -> Optional[float]:
        """
        Ratio de Open Interest entre Puts y Calls.
        > 1 = sesgo bajista (posible contrarian buy).
        < 0.7 = sesgo alcista excesivo (posible techo).
        """
        ticker = yf.Ticker(symbol)

        if not expiration_date:
            expiration_date = self.get_nearest_expiration(symbol)

        try:
            opt_chain = ticker.option_chain(expiration_date)
            put_oi = opt_chain.puts['openInterest'].sum()
            call_oi = opt_chain.calls['openInterest'].sum()

            if call_oi == 0:
                return None

            return put_oi / call_oi

        except Exception as e:
            logger.error(f"Error calculando PCR para {symbol}: {e}")
            return None

    def get_gex_proxy(self, symbol: str, atm_range: float = 5.0) -> Optional[dict]:
        """
        Estimación de Gamma Exposure (GEX).
        GEX > 0: Market Makers suprimen volatilidad (mercado estable).
        GEX < 0: Market Makers amplifican volatilidad (mercado explosivo).
        """
        ticker = yf.Ticker(symbol)
        exp = self.get_nearest_expiration(symbol)
        if not exp:
            return None

        try:
            # Obtener precio actual
            hist = ticker.history(period="1d")
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            if hist.empty:
                return None
            current_price = float(hist['Close'].iloc[-1])

            chain = ticker.option_chain(exp)

            # Filtrar strikes ATM (±range)
            near_strikes = [
                s for s in chain.calls['strike']
                if abs(s - current_price) <= atm_range
            ]

            atm_calls_oi = chain.calls[
                chain.calls['strike'].isin(near_strikes)
            ]['openInterest'].sum()

            atm_puts_oi = chain.puts[
                chain.puts['strike'].isin(near_strikes)
            ]['openInterest'].sum()

            gex_net = int(atm_calls_oi - atm_puts_oi)

            return {
                "gex_net_contracts": gex_net,
                "gex_positive": gex_net > 0,
                "atm_calls_oi": int(atm_calls_oi),
                "atm_puts_oi": int(atm_puts_oi),
                "current_price": current_price,
            }

        except Exception as e:
            logger.error(f"Error calculando GEX para {symbol}: {e}")
            return None

    def get_full_analysis(self, symbol: str) -> dict:
        """
        Análisis completo de opciones para un ticker.
        Retorna dict con todos los indicadores normalizados.
        """
        ticker = yf.Ticker(symbol)
        exp = self.get_nearest_expiration(symbol)

        # Precio actual
        hist = ticker.history(period="1d")
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        current_price = float(hist['Close'].iloc[-1]) if not hist.empty else 0

        max_pain = self.calculate_max_pain(symbol, exp)
        pcr = self.get_put_call_ratio(symbol, exp)
        gex = self.get_gex_proxy(symbol)

        # Distancia normalizada al Max Pain (% del precio)
        mp_distance_pct = 0.0
        if max_pain and current_price:
            mp_distance_pct = ((current_price - max_pain) / max_pain) * 100

        # Bias del Market Maker
        if mp_distance_pct < -2:
            mm_bias = "BULLISH_PULL"   # Precio muy debajo de MP → subirá
        elif mp_distance_pct > 2:
            mm_bias = "BEARISH_PULL"   # Precio muy arriba de MP → bajará
        else:
            mm_bias = "NEUTRAL"        # Cerca de MP → gravitación

        return {
            "symbol": symbol,
            "current_price": current_price,
            "max_pain": max_pain,
            "max_pain_distance_pct": round(mp_distance_pct, 2),
            "put_call_ratio": round(pcr, 3) if pcr else None,
            "gex": gex,
            "mm_bias": mm_bias,
            "expiration": exp,
            "timestamp": datetime.utcnow().isoformat(),
        }
