import logging
import numpy as np
import pandas as pd
from datetime import datetime, UTC
from typing import Optional

from backend.modules.options_gamma.domain.entities.gamma_models import GammaRegime, OpExType, OptionsAnalysis
from backend.modules.options_gamma.domain.rules.black_scholes import bs_gamma, bs_delta
from backend.modules.options_gamma.domain.rules.opex_calendar import detect_opex

logger = logging.getLogger(__name__)

class OptionsAwareness:
    """
    Agente de Opciones Institucional V2.

    Calcula:
    - Max Pain (gravitación de Market Makers)
    - GEX real via Black-Scholes (no proxy)
    - Gamma Regime (PIN / DRIFT / SQUEEZE)
    - Flip Points (dónde cambia el régimen)
    - Gravity Score (-1.0 a +1.0 direccional)
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.OptionsAwareness")
        from backend.modules.options_gamma.infrastructure.yfinance_adapter import YFinanceOptionsAdapter
        self._adapter = YFinanceOptionsAdapter()

    # ─────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────

    def get_full_analysis(self, symbol: str) -> dict:
        """
        Análisis completo de opciones para un ticker.
        Backward-compatible con la interfaz anterior +
        nuevos campos de gamma regime.
        """
        analysis = self._analyze(symbol)
        return {
            # Legacy fields (backward compat with UniverseFilter)
            "symbol": analysis.symbol,
            "current_price": analysis.current_price,
            "max_pain": analysis.max_pain,
            "max_pain_distance_pct": round(analysis.max_pain_distance_pct, 2),
            "put_call_ratio": round(analysis.put_call_ratio, 3),
            "gex": {
                "gex_net_contracts": int(analysis.gamma_regime.net_gex),
                "gex_positive": analysis.gex_positive,
                "atm_calls_oi": 0,
                "atm_puts_oi": 0,
                "current_price": analysis.current_price,
            },
            "mm_bias": analysis.mm_bias,
            "expiration": analysis.expiration,
            "timestamp": analysis.timestamp,
            # NEW: Gamma Regime
            "gamma_regime": analysis.gamma_regime.regime,
            "net_gex_dollars": analysis.gamma_regime.net_gex,
            "gamma_shares_per_dollar": analysis.gamma_regime.gamma_shares_per_dollar,
            "hedge_dollars_per_dollar": analysis.gamma_regime.hedge_dollars_per_dollar,
            "flip_up": analysis.gamma_regime.flip_up,
            "flip_down": analysis.gamma_regime.flip_down,
            "call_wall": analysis.gamma_regime.call_wall,
            "call_wall_oi": analysis.gamma_regime.call_wall_oi,
            "put_wall": analysis.gamma_regime.put_wall,
            "put_wall_oi": analysis.gamma_regime.put_wall_oi,
            "pin_range": [analysis.gamma_regime.pin_range_low,
                          analysis.gamma_regime.pin_range_high],
            # NEW: Gravity
            "gravity_score": round(analysis.gravity_score, 4),
            "gravity_strength": round(analysis.gravity_strength, 1),
            # NEW: OpEx
            "opex_type": analysis.opex.opex_type,
            "is_opex_day": analysis.opex.is_opex_day,
            "opex_time_weight": analysis.opex.time_weight,
        }

    def get_gamma_regime(self, symbol: str) -> GammaRegime:
        """Direct access to gamma regime for internal use."""
        analysis = self._analyze(symbol)
        return analysis.gamma_regime

    def get_gravity_score(self, symbol: str) -> float:
        """
        Gravity score: -1.0 to +1.0.
        >0 = price expected to be pulled UP toward Max Pain
        <0 = price expected to be pulled DOWN toward Max Pain
        0  = no gravitational effect (non-OpEx or far from MP)
        """
        analysis = self._analyze(symbol)
        return analysis.gravity_score

    def get_nearest_expiration(self, symbol: str) -> Optional[str]:
        """Obtiene la fecha de expiración más cercana."""
        return self._adapter.fetch_nearest_expiration(symbol)

    def calculate_max_pain(self, symbol: str,
                           expiration_date: Optional[str] = None) -> Optional[float]:
        """Legacy: Calculate max pain for a symbol."""
        chain_data = self._adapter.fetch_chain(symbol)
        if not chain_data or 'calls' not in chain_data:
            return None
        try:
            return self._calc_max_pain(chain_data['calls'], chain_data['puts'])
        except Exception as e:
            self.logger.error(f"Error calculando Max Pain para {symbol}: {e}")
            return None

    def get_put_call_ratio(self, symbol: str,
                           expiration_date: Optional[str] = None) -> Optional[float]:
        """Legacy: PCR for a symbol."""
        chain_data = self._adapter.fetch_chain(symbol)
        if not chain_data or 'calls' not in chain_data:
            return None
        try:
            call_oi = chain_data['calls']['openInterest'].sum()
            put_oi = chain_data['puts']['openInterest'].sum()
            return put_oi / call_oi if call_oi > 0 else None
        except Exception as e:
            self.logger.error(f"Error calculando PCR para {symbol}: {e}")
            return None

    def get_gex_proxy(self, symbol: str, atm_range: float = 5.0) -> Optional[dict]:
        """Legacy: GEX proxy — now uses real Black-Scholes gamma."""
        analysis = self._analyze(symbol)
        return {
            "gex_net_contracts": int(analysis.gamma_regime.net_gex),
            "gex_positive": analysis.gamma_regime.net_gex > 0,
            "current_price": analysis.current_price,
        }

    # ─────────────────────────────────────────────────────────
    # CORE ANALYSIS ENGINE
    # ─────────────────────────────────────────────────────────

    def _analyze(self, symbol: str) -> OptionsAnalysis:
        """Full analysis pipeline — uses adapter for data, pure math for analysis."""
        result = OptionsAnalysis(symbol=symbol)

        try:
            chain_data = self._adapter.fetch_chain(symbol)
            if not chain_data or 'calls' not in chain_data:
                return result

            result.current_price = chain_data['current_price']
            result.expiration = chain_data['expiration']
            calls = chain_data['calls']
            puts = chain_data['puts']

            # Time to expiration
            exp_date = pd.Timestamp(result.expiration)
            T = max((exp_date - pd.Timestamp.now()).days / 365.0, 1/365.0)

            # Max Pain
            result.max_pain = self._calc_max_pain(calls, puts) or 0
            if result.max_pain and result.current_price:
                result.max_pain_distance_pct = (
                    (result.current_price - result.max_pain) / result.max_pain * 100
                )

            # PCR
            call_oi = calls['openInterest'].sum()
            put_oi = puts['openInterest'].sum()
            result.total_oi = int(call_oi + put_oi)
            result.put_call_ratio = put_oi / call_oi if call_oi > 0 else 0

            # Gamma Regime (Black-Scholes real)
            result.gamma_regime = self._calc_gamma_regime(
                result.current_price, calls, puts, T
            )

            # OpEx detection
            result.opex = detect_opex()

            # Gravity score
            result.gravity_score = self._calc_gravity(
                result.current_price, result.max_pain,
                result.opex, result.gamma_regime
            )
            result.gravity_strength = min(100, abs(result.gravity_score) * 100)

            # Legacy compat
            result.gex_positive = result.gamma_regime.net_gex > 0
            if result.max_pain_distance_pct < -2:
                result.mm_bias = "BULLISH_PULL"
            elif result.max_pain_distance_pct > 2:
                result.mm_bias = "BEARISH_PULL"
            else:
                result.mm_bias = "NEUTRAL"

            result.timestamp = chain_data.get('timestamp', datetime.now(UTC).isoformat())

        except Exception as e:
            self.logger.error(f"Error en análisis de {symbol}: {e}")

        return result

    # ─────────────────────────────────────────────────────────
    # GAMMA REGIME CALCULATION
    # ─────────────────────────────────────────────────────────

    def _calc_gamma_regime(self, S: float, calls: pd.DataFrame,
                           puts: pd.DataFrame, T: float) -> GammaRegime:
        """
        Calcula el régimen gamma usando Black-Scholes exacto.

        V_hedge = Σ [ N'(d1) / (S × σ × √T) × OI × 100 ] × ΔS
        """
        regime = GammaRegime()

        try:
            # GEX at current price
            call_gex, put_gex, total_gamma = self._calc_gex_at_price(
                S, calls, puts, T
            )
            regime.net_gex = call_gex + put_gex
            regime.call_gex = call_gex
            regime.put_gex = put_gex
            regime.gamma_shares_per_dollar = int(total_gamma)
            regime.hedge_dollars_per_dollar = total_gamma * S

            # Walls
            above_calls = calls[calls['strike'] > S].nlargest(
                1, 'openInterest'
            )
            below_puts = puts[puts['strike'] < S].nlargest(
                1, 'openInterest'
            )

            if not above_calls.empty:
                regime.call_wall = float(above_calls.iloc[0]['strike'])
                regime.call_wall_oi = int(above_calls.iloc[0]['openInterest'])
            else:
                regime.call_wall = S * 1.05

            if not below_puts.empty:
                regime.put_wall = float(below_puts.iloc[0]['strike'])
                regime.put_wall_oi = int(below_puts.iloc[0]['openInterest'])
            else:
                regime.put_wall = S * 0.95

            regime.pin_range_low = regime.put_wall
            regime.pin_range_high = regime.call_wall

            # Find GEX flip points (scan ±6% from current price)
            flip_up, flip_down = self._find_flip_points(
                S, calls, puts, T
            )
            regime.flip_up = flip_up
            regime.flip_down = flip_down

            # Determine regime
            if regime.net_gex > 0:
                regime.regime = "PIN"
            else:
                # GEX negative — check if squeeze conditions met
                if S > regime.call_wall:
                    regime.regime = "SQUEEZE_UP"
                elif S < regime.put_wall:
                    regime.regime = "SQUEEZE_DOWN"
                else:
                    regime.regime = "SQUEEZE_RISK"

            # Override to DRIFT if gamma is too low (far from MP)
            if total_gamma < 1000:  # Negligible gamma
                regime.regime = "DRIFT"

        except Exception as e:
            self.logger.error(f"Error calculando gamma regime: {e}")

        return regime

    def _calc_gex_at_price(self, S: float, calls: pd.DataFrame,
                           puts: pd.DataFrame, T: float,
                           r: float = 0.05):
        """
        Calcula GEX en un precio dado.

        Call GEX > 0: MMs compran en bajadas, venden en subidas (estabiliza)
        Put GEX < 0: MMs venden en caídas (desestabiliza)
        Net GEX = Call GEX + Put GEX
        """
        total_call_gex = 0.0
        total_put_gex = 0.0
        total_gamma = 0.0

        for _, row in calls.iterrows():
            K = row['strike']
            oi = row.get('openInterest', 0)
            iv = row.get('impliedVolatility', 0.30)
            if oi <= 0 or iv <= 0:
                continue
            g = bs_gamma(S, K, T, iv, r)
            total_call_gex += g * oi * 100 * S
            total_gamma += g * oi * 100

        for _, row in puts.iterrows():
            K = row['strike']
            oi = row.get('openInterest', 0)
            iv = row.get('impliedVolatility', 0.30)
            if oi <= 0 or iv <= 0:
                continue
            g = bs_gamma(S, K, T, iv, r)
            total_put_gex -= g * oi * 100 * S  # Negative: destabilizing
            total_gamma += g * oi * 100

        return total_call_gex, total_put_gex, total_gamma

    def _find_flip_points(self, S: float, calls: pd.DataFrame,
                          puts: pd.DataFrame, T: float,
                          scan_pct: float = 6.0,
                          steps: int = 30) -> tuple:
        """
        Encuentra los precios donde GEX cambia de positivo a negativo.

        flip_up: precio arriba del actual donde GEX → negativo (squeeze alcista)
        flip_down: precio abajo del actual donde GEX → negativo (squeeze bajista)
        """
        prices = np.linspace(S * (1 - scan_pct/100),
                             S * (1 + scan_pct/100), steps)

        gex_profile = []
        for p in prices:
            cg, pg, _ = self._calc_gex_at_price(p, calls, puts, T)
            gex_profile.append((p, cg + pg))

        midpoint = len(gex_profile) // 2
        flip_up = 0.0
        flip_down = 0.0

        # Scan upward from current price
        for i in range(midpoint, len(gex_profile) - 1):
            if gex_profile[i][1] > 0 and gex_profile[i+1][1] <= 0:
                flip_up = gex_profile[i+1][0]
                break

        # Scan downward from current price
        for i in range(midpoint, 0, -1):
            if gex_profile[i][1] > 0 and gex_profile[i-1][1] <= 0:
                flip_down = gex_profile[i-1][0]
                break

        return flip_up, flip_down

    # ─────────────────────────────────────────────────────────
    # GRAVITY SCORE
    # ─────────────────────────────────────────────────────────

    def _calc_gravity(self, price: float, max_pain: float,
                      opex: OpExType, regime: GammaRegime) -> float:
        """
        Gravity Score: -1.0 a +1.0

        +1.0 = Fuerte pull alcista (precio debajo de MP)
        -1.0 = Fuerte pull bajista (precio arriba de MP)
         0.0 = Sin efecto gravitacional

        Solo activo en OpEx day, ventana AM, régimen PIN.
        """
        if not max_pain or not price or max_pain == 0:
            return 0.0

        # No gravity outside OpEx windows
        if opex.time_weight == 0:
            return 0.0

        # No gravity in DRIFT or SQUEEZE (pin is broken)
        if regime.regime in ("DRIFT", "SQUEEZE_UP", "SQUEEZE_DOWN"):
            return 0.0

        dist_pct = (price - max_pain) / max_pain * 100

        # Too far from MP — gravity negligible
        if abs(dist_pct) > 3.0:
            return 0.0

        # Direction: price above MP = pull DOWN (negative), below = pull UP (positive)
        direction = -1.0 if dist_pct > 0 else 1.0

        # Magnitude: peaks at ~1.5% distance, weak very close (already pinned)
        # and weak far away (beyond gravitational field)
        abs_dist = abs(dist_pct)
        if abs_dist < 0.3:
            magnitude = abs_dist / 0.3 * 0.5  # Close to pin, weak pull
        elif abs_dist < 2.0:
            magnitude = 0.5 + (abs_dist - 0.3) / 1.7 * 0.5  # Growing
        else:
            magnitude = 1.0 - (abs_dist - 2.0) / 1.0 * 0.5  # Decaying

        magnitude = max(0, min(1.0, magnitude))

        return direction * magnitude * opex.time_weight

    # ─────────────────────────────────────────────────────────
    # MAX PAIN CALCULATION
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _calc_max_pain(calls: pd.DataFrame,
                       puts: pd.DataFrame) -> Optional[float]:
        """Calculate Max Pain from options chain DataFrames."""
        try:
            strikes = sorted(set(calls['strike']).union(set(puts['strike'])))
            min_loss = float('inf')
            max_pain = 0

            for strike in strikes:
                call_loss = calls[calls['strike'] < strike].apply(
                    lambda x: (strike - x['strike']) * x['openInterest'],
                    axis=1
                ).sum()
                put_loss = puts[puts['strike'] > strike].apply(
                    lambda x: (x['strike'] - strike) * x['openInterest'],
                    axis=1
                ).sum()

                total = call_loss + put_loss
                if total < min_loss:
                    min_loss = total
                    max_pain = strike

            return max_pain
        except Exception:
            return None
