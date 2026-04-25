"""
VOLUME PROFILE ANALYZER — Institutional Level Detection
=========================================================
Calcula el Volume Profile desde datos OHLCV diarios para identificar
niveles donde los institucionales concentraron operaciones.

Conceptos:
  POC (Point of Control) — Precio con mayor volumen acumulado. "Precio justo".
  VAH (Value Area High)  — Techo del 70% del volumen. Resistencia institucional.
  VAL (Value Area Low)   — Piso del 70% del volumen. Soporte institucional.

Dual Timeframe:
  Short (20d) — Actividad institucional reciente. Timing.
  Long  (50d) — Niveles estructurales. Soporte/resistencia real.

POC Migration:
  Short POC > Long POC — Institucionales acumulando a precios más altos (BULLISH)
  Short POC < Long POC — Institucionales distribuyendo a precios más bajos (BEARISH)

Profile Shape (Market Profile Theory):
  P-shape — Volumen concentrado ARRIBA. Compras institucionales agresivas.
            Indica ACUMULACIÓN alcista. Precio probable a subir.
  b-shape — Volumen concentrado ABAJO. Ventas institucionales agresivas.
            Indica DISTRIBUCIÓN bajista. Precio probable a bajar.
  D-shape — Distribución normal/balanceada. Equilibrio.
            Mercado lateral, esperar ruptura direccional.

Fundamentos:
  - Steidlmayer, J.P. (1986): "Market Profile" — CBOT
  - Dalton, J. (1993): "Mind Over Markets"
  - El volumen en un nivel de precio = "aceptación" institucional
  - Los precios se mueven de HVN a HVN, acelerando a través de LVN

Datos:
  Usa OHLCV diario de yfinance. Aproxima distribución intradía
  asumiendo distribución uniforme del volumen entre Low y High del día.
  Esto es estándar para swing trading (horizonte 3-10 días).

References:
  López de Prado (2018): Advances in Financial ML, Ch. 19 (Microstructure)
"""
import logging
import numpy as np
import pandas as pd
from typing import Optional, List, Tuple
from modules.volume_intelligence.models import VolumeNode, VolumeProfileResult, DualProfileResult
from modules.volume_intelligence import rules

logger = logging.getLogger(__name__)



class VolumeProfileAnalyzer:
    """
    Analiza Volume Profile en dos timeframes para detectar
    niveles institucionales y sesgo de acumulación/distribución.
    """
    
    # Constants from centralized rules
    P_SHAPE_SKEW_THRESHOLD = rules.P_SHAPE_SKEW_THRESHOLD
    B_SHAPE_SKEW_THRESHOLD = rules.B_SHAPE_SKEW_THRESHOLD
    POC_MIGRATION_THRESHOLD = rules.POC_MIGRATION_THRESHOLD
    VALUE_AREA_PCT = rules.VALUE_AREA_PCT
    HVN_THRESHOLD = rules.HVN_THRESHOLD
    LVN_THRESHOLD = rules.LVN_THRESHOLD
    
    def compute(
        self,
        prices: pd.DataFrame,
        short_period: int = 20,
        long_period: int = 50,
        num_bins: int = 50,
    ) -> DualProfileResult:
        """
        Calcula Volume Profile dual (corto + largo plazo).
        
        Args:
            prices: DataFrame con Open, High, Low, Close, Volume
            short_period: Días para perfil corto (default: 20 = 1 mes)
            long_period: Días para perfil largo (default: 50 = trimestre)
            num_bins: Número de bins de precio para el histograma
            
        Returns:
            DualProfileResult con niveles, shape, y señal compuesta
        """
        result = DualProfileResult()
        
        if prices is None or prices.empty or len(prices) < short_period:
            return result
        
        # Normalize columns
        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(0)
        
        current_price = float(prices['Close'].iloc[-1])
        
        # Compute both profiles
        result.short = self._compute_single_profile(
            prices, short_period, num_bins, current_price
        )
        
        long_data_available = min(len(prices), long_period)
        if long_data_available >= 30:  # At least 30 days for long profile
            result.long = self._compute_single_profile(
                prices, long_data_available, num_bins, current_price
            )
        else:
            result.long = result.short  # Fall back to short
        
        # POC Migration Analysis
        result = self._analyze_poc_migration(result)
        
        # Compute actionable levels
        result = self._compute_actionable_levels(result, current_price)
        
        # Generate diagnosis
        result.diagnosis = self._generate_diagnosis(result, current_price)
        
        return result
    
    def _compute_single_profile(
        self,
        prices: pd.DataFrame,
        period: int,
        num_bins: int,
        current_price: float,
    ) -> VolumeProfileResult:
        """Compute a single Volume Profile for a given period."""
        result = VolumeProfileResult(period_days=period, current_price=current_price)
        
        # Get data for the period
        df = prices.tail(period).copy()
        
        if df.empty or len(df) < 5:
            return result
        
        high = df['High'].values.astype(float)
        low = df['Low'].values.astype(float)
        close = df['Close'].values.astype(float)
        volume = df['Volume'].values.astype(float)
        
        # Overall price range
        price_max = float(np.max(high))
        price_min = float(np.min(low))
        price_range = price_max - price_min
        
        if price_range <= 0 or np.sum(volume) <= 0:
            return result
        
        # Create bins
        bin_edges = np.linspace(price_min, price_max, num_bins + 1)
        bin_volumes = np.zeros(num_bins)
        bin_mids = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_width = bin_edges[1] - bin_edges[0]
        
        # Distribute each day's volume across the bins it spans
        for i in range(len(df)):
            day_low = low[i]
            day_high = high[i]
            day_volume = volume[i]
            day_close = close[i]
            day_open = df['Open'].values[i] if 'Open' in df.columns else day_close
            
            if day_volume <= 0 or day_high <= day_low:
                continue
            
            # Find which bins this day spans
            bin_start = max(0, int((day_low - price_min) / bin_width))
            bin_end = min(num_bins - 1, int((day_high - price_min) / bin_width))
            
            if bin_start > bin_end:
                bin_start, bin_end = bin_end, bin_start
            
            # Distribute volume with TPO-style weighting
            # More volume near the close (where price settled = more acceptance)
            num_covered_bins = bin_end - bin_start + 1
            if num_covered_bins > 0:
                for b in range(bin_start, bin_end + 1):
                    # Weight: bins closer to close get more volume
                    dist_to_close = abs(bin_mids[b] - day_close)
                    max_dist = max(abs(day_high - day_close), abs(day_close - day_low), bin_width)
                    weight = 1.0 - (dist_to_close / max_dist) * 0.5  # 0.5-1.0 range
                    bin_volumes[b] += day_volume * weight / num_covered_bins
        
        total_volume = np.sum(bin_volumes)
        if total_volume <= 0:
            return result
        
        # Normalize
        bin_pcts = bin_volumes / total_volume
        
        # POC: bin with maximum volume
        poc_idx = int(np.argmax(bin_volumes))
        result.poc = round(float(bin_mids[poc_idx]), 2)
        
        # Value Area: expand from POC until 70% of volume
        va_volume = bin_volumes[poc_idx]
        va_low_idx = poc_idx
        va_high_idx = poc_idx
        
        while va_volume / total_volume < self.VALUE_AREA_PCT:
            # Look one bin above and below, add the larger
            can_go_up = va_high_idx < num_bins - 1
            can_go_down = va_low_idx > 0
            
            if can_go_up and can_go_down:
                if bin_volumes[va_high_idx + 1] >= bin_volumes[va_low_idx - 1]:
                    va_high_idx += 1
                    va_volume += bin_volumes[va_high_idx]
                else:
                    va_low_idx -= 1
                    va_volume += bin_volumes[va_low_idx]
            elif can_go_up:
                va_high_idx += 1
                va_volume += bin_volumes[va_high_idx]
            elif can_go_down:
                va_low_idx -= 1
                va_volume += bin_volumes[va_low_idx]
            else:
                break
        
        result.vah = round(float(bin_edges[va_high_idx + 1]), 2)
        result.val = round(float(bin_edges[va_low_idx]), 2)
        
        # Position vs profile
        if current_price > result.vah:
            result.current_vs_va = "ABOVE_VA"
        elif current_price < result.val:
            result.current_vs_va = "BELOW_VA"
        else:
            result.current_vs_va = "IN_VA"
        
        poc_diff = current_price - result.poc
        if abs(poc_diff) / current_price < 0.005:  # Within 0.5%
            result.current_vs_poc = "AT_POC"
        elif poc_diff > 0:
            result.current_vs_poc = "ABOVE_POC"
        else:
            result.current_vs_poc = "BELOW_POC"
        
        result.poc_distance_pct = round((current_price - result.poc) / result.poc * 100, 2)
        
        # Identify HVN and LVN
        avg_bin_vol = total_volume / num_bins
        nodes = []
        for i in range(num_bins):
            node = VolumeNode(
                price_low=round(float(bin_edges[i]), 2),
                price_high=round(float(bin_edges[i + 1]), 2),
                price_mid=round(float(bin_mids[i]), 2),
                volume=float(bin_volumes[i]),
                pct_of_total=round(float(bin_pcts[i]) * 100, 2),
                is_hvn=bin_volumes[i] > avg_bin_vol * self.HVN_THRESHOLD,
                is_lvn=bin_volumes[i] < avg_bin_vol * self.LVN_THRESHOLD,
            )
            nodes.append(node)
        
        result.nodes = nodes
        
        # Nearest HVN above and below current price
        hvn_above = [n for n in nodes if n.is_hvn and n.price_mid > current_price]
        hvn_below = [n for n in nodes if n.is_hvn and n.price_mid < current_price]
        
        if hvn_above:
            result.nearest_hvn_above = hvn_above[0].price_mid
        if hvn_below:
            result.nearest_hvn_below = hvn_below[-1].price_mid
        
        # === PROFILE SHAPE DETECTION ===
        # P-shape: volume concentrated in upper half (bullish accumulation)
        # b-shape: volume concentrated in lower half (bearish distribution)
        # D-shape: balanced distribution
        
        mid_idx = num_bins // 2
        upper_vol = float(np.sum(bin_volumes[mid_idx:]))
        lower_vol = float(np.sum(bin_volumes[:mid_idx]))
        
        if total_volume > 0:
            # Skew: positive = P (upper heavy), negative = b (lower heavy)
            result.shape_skew = round((upper_vol - lower_vol) / total_volume, 3)
        
        if result.shape_skew > self.P_SHAPE_SKEW_THRESHOLD:
            result.shape = "P"   # Accumulation — volume at highs
        elif result.shape_skew < self.B_SHAPE_SKEW_THRESHOLD:
            result.shape = "b"   # Distribution — volume at lows
        else:
            result.shape = "D"   # Balanced
        
        return result
    
    def _analyze_poc_migration(self, result: DualProfileResult) -> DualProfileResult:
        """
        Analyze POC migration between short and long profiles.
        
        POC Migration is one of the most powerful institutional signals:
        - Short POC rising above Long POC = institutions accumulating at higher prices
        - Short POC falling below Long POC = institutions distributing at lower prices
        """
        if result.short.poc <= 0 or result.long.poc <= 0:
            return result
        
        migration_pct = ((result.short.poc - result.long.poc) / result.long.poc) * 100
        result.poc_migration_pct = round(migration_pct, 2)
        
        if migration_pct > self.POC_MIGRATION_THRESHOLD:
            result.poc_migration = "BULLISH"
        elif migration_pct < -self.POC_MIGRATION_THRESHOLD:
            result.poc_migration = "BEARISH"
        else:
            result.poc_migration = "NEUTRAL"
        
        # Composite institutional bias
        # Combine: POC migration + short shape + long shape
        bullish_signals = 0
        bearish_signals = 0
        
        # POC migration (strongest signal)
        if result.poc_migration == "BULLISH":
            bullish_signals += 2
        elif result.poc_migration == "BEARISH":
            bearish_signals += 2
        
        # Short profile shape
        if result.short.shape == "P":
            bullish_signals += 1
        elif result.short.shape == "b":
            bearish_signals += 1
        
        # Long profile shape
        if result.long.shape == "P":
            bullish_signals += 1
        elif result.long.shape == "b":
            bearish_signals += 1
        
        total_signals = bullish_signals + bearish_signals
        if total_signals == 0:
            result.institutional_bias = "NEUTRAL"
            result.bias_confidence = 50.0
        elif bullish_signals > bearish_signals:
            result.institutional_bias = "ACCUMULATION"
            result.bias_confidence = round(bullish_signals / max(total_signals, 1) * 100, 0)
        else:
            result.institutional_bias = "DISTRIBUTION"
            result.bias_confidence = round(bearish_signals / max(total_signals, 1) * 100, 0)
        
        return result
    
    def _compute_actionable_levels(
        self, result: DualProfileResult, current_price: float
    ) -> DualProfileResult:
        """Compute trading-actionable levels from both profiles."""
        
        # Primary support: lowest of the two VALs (strongest floor)
        result.primary_support = round(min(
            result.short.val if result.short.val > 0 else current_price,
            result.long.val if result.long.val > 0 else current_price,
        ), 2)
        
        # Primary resistance: highest of the two VAHs
        result.primary_resistance = round(max(
            result.short.vah if result.short.vah > 0 else current_price,
            result.long.vah if result.long.vah > 0 else current_price,
        ), 2)
        
        # Entry zone: between short VAL and short POC
        result.entry_zone_low = round(result.short.val, 2) if result.short.val > 0 else round(current_price * 0.97, 2)
        result.entry_zone_high = round(result.short.poc, 2) if result.short.poc > 0 else round(current_price * 0.99, 2)
        
        return result
    
    def _generate_diagnosis(
        self, result: DualProfileResult, current_price: float
    ) -> str:
        """Generate human-readable diagnosis."""
        
        shape_names = {
            "P": "P-shape (ACUMULACIÓN alcista)",
            "b": "b-shape (DISTRIBUCIÓN bajista)",
            "D": "D-shape (equilibrio)",
        }
        
        lines = []
        
        # Profile shapes
        lines.append(
            f"Short({result.short.period_days}d): {shape_names.get(result.short.shape, '?')} | "
            f"POC=${result.short.poc:.2f} VAH=${result.short.vah:.2f} VAL=${result.short.val:.2f}"
        )
        lines.append(
            f"Long({result.long.period_days}d): {shape_names.get(result.long.shape, '?')} | "
            f"POC=${result.long.poc:.2f} VAH=${result.long.vah:.2f} VAL=${result.long.val:.2f}"
        )
        
        # POC migration
        if result.poc_migration == "BULLISH":
            lines.append(
                f"📈 POC Migration: BULLISH ({result.poc_migration_pct:+.1f}%). "
                f"Institucionales acumulando a precios más altos."
            )
        elif result.poc_migration == "BEARISH":
            lines.append(
                f"📉 POC Migration: BEARISH ({result.poc_migration_pct:+.1f}%). "
                f"Institucionales distribuyendo a precios más bajos."
            )
        else:
            lines.append(f"➡️ POC Migration: NEUTRAL ({result.poc_migration_pct:+.1f}%)")
        
        # Institutional bias
        lines.append(
            f"Sesgo Institucional: {result.institutional_bias} "
            f"(conf={result.bias_confidence:.0f}%)"
        )
        
        # Price position
        lines.append(
            f"Precio ${current_price:.2f}: {result.short.current_vs_va} "
            f"(dist POC={result.short.poc_distance_pct:+.1f}%)"
        )
        
        return " | ".join(lines)
