import logging
import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class OptionsAwareness:
    """
    Agente de Análisis de Opciones (Gamma Squeeze & Max Pain).
    Busca determinar hacia dónde los Market Makers están incentivados 
    a mover el mercado (Max Pain) y evaluar desbalances (Put/Call Ratio).
    """

    def __init__(self):
        pass

    def get_nearest_expiration(self, symbol: str) -> Optional[str]:
        """Obtiene la fecha de expiración más cercana (usualmente el viernes)."""
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return None
        return expirations[0]

    def calculate_max_pain(self, symbol: str, expiration_date: Optional[str] = None) -> Optional[float]:
        """
        Calcula el 'Maximum Pain'. 
        El precio de ejercicio (Strike Price) donde la mayor cantidad de 
        opciones expirarán sin valor (worthless).
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
            
            # Obtener todos los strikes
            strikes = sorted(list(set(calls['strike']).union(set(puts['strike']))))
            
            max_pain = 0
            min_loss = float('inf')
            
            for strike in strikes:
                # Pérdida intrínseca total para los compradores de opciones si expira en este 'strike'
                call_loss = calls[calls['strike'] < strike].apply(lambda x: (strike - x['strike']) * x['openInterest'], axis=1).sum()
                put_loss = puts[puts['strike'] > strike].apply(lambda x: (x['strike'] - strike) * x['openInterest'], axis=1).sum()
                
                total_loss = call_loss + put_loss
                
                if total_loss < min_loss:
                    min_loss = total_loss
                    max_pain = strike

            logger.info(f"{symbol} | Exp: {expiration_date} | Max Pain: ${max_pain}")
            return max_pain
            
        except Exception as e:
            logger.error(f"Error calculando Max Pain para {symbol}: {e}")
            return None

    def get_put_call_ratio(self, symbol: str, expiration_date: Optional[str] = None) -> Optional[float]:
        """
        Ratio de volumen/interés abierto entre Puts y Calls. 
        Un ratio > 1 indica sentimiento bajista extremo (posible contrarian play).
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
                
            pcr = put_oi / call_oi
            logger.info(f"{symbol} | Exp: {expiration_date} | Put/Call Open Interest Ratio: {pcr:.2f}")
            return pcr
            
        except Exception as e:
            logger.error(f"Error calculando PCR para {symbol}: {e}")
            return None

    def get_gamma_bias(self, symbol: str) -> Dict[str, any]:
        """
        Genera un dictamen sobre la presión probable del mercado basándose en las opciones.
        """
        max_pain = self.calculate_max_pain(symbol)
        pcr = self.get_put_call_ratio(symbol)
        
        current_price = None
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period="1d")
            if not history.empty:
                current_price = history['Close'][-1]
        except Exception:
            pass

        bias = "NEUTRAL"
        if max_pain and current_price:
            # Si el precio actual está muy debajo del Max Pain, MMs tenderán a presionar arriba
            if current_price < (max_pain * 0.98):
                bias = "BULLISH_PULL"
            elif current_price > (max_pain * 1.02):
                bias = "BEARISH_PULL"
                
        return {
            "symbol": symbol,
            "current_price": current_price,
            "max_pain": max_pain,
            "put_call_ratio": pcr,
            "market_maker_bias": bias,
            "timestamp": datetime.utcnow().isoformat()
        }
