"""
Caso de Uso: Evaluador Forense de Rotación por Piernas ZigZag y Posición Real
=============================================================================
Clean Architecture: Application Layer (Use Cases)
Módulo: entry_decision / rotation

Valora formalmente las Señales Disruptivas de Rotación y los Regímenes de Mercado
bajo la Taxonomía Profesional de 4 Niveles de Drawdown (Pullback, Corrección,
Bear Market Gradual, Crash Financiero Abrupto), midiendo la realidad integral de la cartera:
  1. Reloj Dual Natural: Mide tanto la vigencia del Régimen (entered_at -> exited_at)
     como el Ciclo Geométrico Oráculo (zz100 / zz125 de pivote a pivote).
  2. Taxonomía Profesional de 4 Niveles: Clasifica la magnitud y la velocidad cinética
     (delta % / delta t) del movimiento para discriminar entre un Pullback saludable,
     una Corrección técnica, un Bear Market gradual y un Crash sistémico.
  3. Protección Real Peak-to-Trough: Supera la métrica punto a punto calculando
     MAE_SPY - MAE_Portafolio desde el pico geométrico hasta el valle.
  4. Des-agrupación (Cooldown): Aplica filtro temporal de 10 barras para evitar
     multi-triggering de señales en consolidaciones laterales.
  5. Rendimiento Real del Portafolio: Evalúa los pesos sectoriales reales, cash y
     defensivos que la cuenta sostenía en cada momento.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import date, datetime
import pandas as pd
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


@dataclass
class RotationSignalEvent:
    signal_name: str
    fire_date: date
    target_type: str               # "TOP", "BOTTOM", "VETO"
    active_mode: str               # Régimen del portafolio en el disparo
    timing_slot: str               # "t=0", "t-1..2", "t-3..5", "t<-5", "t+1..2", "ENTRE"
    dist_days_to_pivot: int        # Negativo = Anticipado (barras de trading), Positivo = Retrasado
    
    # Magnitudes de la Pierna ZigZag (Subyacente SPY)
    spy_price_at_signal: float
    spy_pivot_price: float
    spy_leg_return: float          # Retorno total de la pierna ZigZag (%)
    spy_leg_direction: str         # "UP" o "DOWN"
    
    # Realidad del Portafolio en la Pierna Geométrica
    portfolio_equity_at_signal: float
    portfolio_cash_weight: float   # Peso en Cash (0.0 a 1.0)
    portfolio_top_sectors: str     # Ej: "XLF: 33%, XLY: 33%, XLK: 33%" o "XLP: 17%, Cash: 50%"
    portfolio_leg_return: float    # Retorno real que experimentó la cuenta en la pierna (%)
    portfolio_mae: float           # Drawdown real soportado por la cuenta en la pierna (%)
    portfolio_mfe: float           # Ganancia máxima alcanzada por la cuenta en la pierna (%)
    
    # Valor Económico Neto Generado
    alpha_leg: float               # Retorno Portafolio - Retorno SPY en la pierna (pp)
    economic_protection_val: float # % de caída que se evitó absorber (punto a punto)
    economic_utility_val: float    # % de subida capturada (en piernas alcistas)
    payoff_asymmetry: float        # Valor Generado / MAE Soportado
    
    # === MODERNIZACIÓN V41: TAXONOMÍA PROFESIONAL DE 4 NIVELES Y RELOJ DUAL ===
    drawdown_tier: str             # "PULLBACK", "CORRECCION", "BEAR_MARKET_GRADUAL", "CRASH_ABRUPTO", "RALLY"
    speed_pct_day: float           # Velocidad de caída o subida (% / día bursátil)
    peak_to_trough_protection: float # MAE_SPY_Peak_to_Trough - MAE_Port_Peak_to_Trough (pp salvados)
    regime_duration_bars: int      # Duración efectiva del régimen activado (Reloj de Régimen)
    regime_return: float           # Retorno del portafolio durante el régimen activado (%)
    regime_mae: float              # Drawdown soportado por el portafolio durante el régimen (%)


class RotationLegEvaluator:
    """
    Evaluador Forense de Rotación por Piernas ZigZag y Posición Real de Cartera.
    Adhiere estrictamente a Clean Architecture (Port & Repository vía TimescaleDataStore)
    y previene vulnerabilidades CWE-89 mediante consultas SQL parametrizadas.
    """
    SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]

    def __init__(self, store: Optional[TimescaleDataStore] = None):
        self.store = store or TimescaleDataStore()

    @staticmethod
    def compute_zigzag_from_bars(df_bars: pd.DataFrame, threshold_pct: float = 0.10) -> pd.DataFrame:
        """
        Calcula de forma exacta las piernas ZigZag sobre barras OHLCV diarias.
        Por defecto utiliza threshold_pct = 0.10 (zz100, Corrección Técnica).
        """
        prices = df_bars['close'].values
        dates = pd.to_datetime(df_bars.index).date
        n = len(prices)
        if n < 2:
            return pd.DataFrame()
            
        legs = []
        p0 = prices[0]
        high_p, low_p = p0, p0
        high_i, low_i = 0, 0
        trend = 0
        leg_id = 0
        
        for i in range(1, n):
            p = prices[i]
            if trend == 0:
                if p >= low_p * (1.0 + threshold_pct):
                    trend, high_p, high_i = 1, p, i
                    last_pivot_i, last_pivot_p, last_pivot_type = low_i, low_p, 'MIN'
                elif p <= high_p * (1.0 - threshold_pct):
                    trend, low_p, low_i = -1, p, i
                    last_pivot_i, last_pivot_p, last_pivot_type = high_i, high_p, 'MAX'
                else:
                    if p > high_p: high_p, high_i = p, i
                    if p < low_p: low_p, low_i = p, i
            elif trend == 1:
                if p > high_p:
                    high_p, high_i = p, i
                elif p <= high_p * (1.0 - threshold_pct):
                    leg_id += 1
                    legs.append({
                        'leg_id': leg_id,
                        'start_d': dates[last_pivot_i],
                        'end_d': dates[high_i],
                        'start_type': 'MIN',
                        'end_type': 'MAX',
                        'start_price': last_pivot_p,
                        'end_price': high_p,
                        'ret': (high_p - last_pivot_p) / last_pivot_p,
                        'leg_return': (high_p - last_pivot_p) / last_pivot_p,
                        'leg_direction': 'UP',
                        'duration_bars': high_i - last_pivot_i
                    })
                    trend, last_pivot_i, last_pivot_p, last_pivot_type = -1, high_i, high_p, 'MAX'
                    low_p, low_i = p, i
            elif trend == -1:
                if p < low_p:
                    low_p, low_i = p, i
                elif p >= low_p * (1.0 + threshold_pct):
                    leg_id += 1
                    legs.append({
                        'leg_id': leg_id,
                        'start_d': dates[last_pivot_i],
                        'end_d': dates[low_i],
                        'start_type': 'MAX',
                        'end_type': 'MIN',
                        'start_price': last_pivot_p,
                        'end_price': low_p,
                        'ret': (low_p - last_pivot_p) / last_pivot_p,
                        'leg_return': (low_p - last_pivot_p) / last_pivot_p,
                        'leg_direction': 'DOWN',
                        'duration_bars': low_i - last_pivot_i
                    })
                    trend, last_pivot_i, last_pivot_p, last_pivot_type = 1, low_i, low_p, 'MIN'
                    high_p, high_i = p, i
                    
        return pd.DataFrame(legs)

    def load_zigzag_legs(self, ticker: str = "SPY", scale: str = "zz100") -> pd.DataFrame:
        """
        Carga piernas ZigZag confirmadas.
        Si la escala solicitada (ej. zz100, zz125) no reside en la base de datos,
        la computa dinámicamente desde las barras OHLCV en Neon.
        """
        df = self.store.load_zigzag_legs(ticker=ticker, scale=scale)
        if not df.empty:
            return df
            
        # Computar dinámicamente a partir de las barras de SPY
        df_bars = self.store.load_bars(ticker, "1d").sort_index()
        threshold_map = {
            "zz25": 0.025, "zz50": 0.05, "zz75": 0.075,
            "zz100": 0.10, "zz125": 0.125, "zz150": 0.15, "zz200": 0.20
        }
        pct = threshold_map.get(scale, 0.10)
        return self.compute_zigzag_from_bars(df_bars, threshold_pct=pct)

    @staticmethod
    def calc_bar_distance(df_daily: pd.DataFrame, target_d: date, piv_date: date) -> int:
        """Calcula la distancia en barras de trading (no días de calendario) entre dos fechas."""
        idx_dates = [d.date() if hasattr(d, 'date') else d for d in df_daily.index]
        try:
            t_idx = idx_dates.index(target_d)
            p_idx = idx_dates.index(piv_date)
            return t_idx - p_idx
        except ValueError:
            return (target_d - piv_date).days

    @staticmethod
    def classify_timing_slot(dist_bars: int) -> str:
        """Clasifica el slot de sincronía con base en barras bursátiles efectivas."""
        if dist_bars == 0:
            return "t=0 (Exacta)"
        elif -2 <= dist_bars <= -1:
            return "t-1..2 (Anticipada Óptima)"
        elif -5 <= dist_bars <= -3:
            return "t-3..5 (Anticipada Temprana)"
        elif dist_bars < -5:
            return "t < -5 (Anticipación Estructural)"
        elif 1 <= dist_bars <= 2:
            return "t+1..2 (Confirmación Rápida)"
        elif 3 <= dist_bars <= 5:
            return "t+3..5 (Confirmación Normal)"
        else:
            return "ENTRE (En Cuerpo de Pierna)"

    @staticmethod
    def classify_drawdown_tier(drop_pct: float, bars_to_trough: int) -> Tuple[str, float]:
        """
        Clasifica formalmente el evento según la Taxonomía Profesional de 4 Niveles:
          1. Pullback (Hasta -10%)
          2. Corrección de Mercado (-10% a -19.9%)
          3. Bear Market Gradual (>= -20%, velocidad < 0.35%/d)
          4. Crash Financiero Abrupto (>= -20%, velocidad >= 0.35%/d o duracion <= 40b)
        """
        abs_drop = abs(drop_pct)
        dur = max(1, bars_to_trough)
        speed = abs_drop / dur
        
        if abs_drop < 10.0:
            tier = "1. PULLBACK (< 10%)"
        elif 10.0 <= abs_drop < 20.0:
            tier = "2. CORRECCION (10% a 20%)"
        else:
            if speed >= 0.35 or dur <= 40:
                tier = "4. CRASH_FINANCIERO_ABRUPTO (>= 20% veloz)"
            else:
                tier = "3. BEAR_MARKET_GRADUAL (>= 20% prolongado)"
                
        return tier, speed

    def evaluate_signals_on_portfolio(
        self,
        df_daily: pd.DataFrame,
        df_legs: pd.DataFrame,
        signals_dict: Dict[str, Tuple[pd.Series, str]], # {"Nombre": (Series_booleana, "TOP"|"BOTTOM")}
        cooldown_bars: int = 10
    ) -> List[RotationSignalEvent]:
        """
        Evalúa cada disparo de señal correlacionando la pierna ZigZag y la duración de régimen
        con la telemetría real del portafolio (equity, cash, retornos).
        Aplica cooldown de des-agrupación y métrica Peak-to-Trough.
        """
        events: List[RotationSignalEvent] = []
        df_daily = df_daily.sort_index()
        daily_dates = [d.date() if hasattr(d, 'date') else d for d in df_daily.index]
        
        for sig_name, (sig_series, target_type) in signals_dict.items():
            # Disparos de flanco ascendente (primer día de la señal)
            fires = sig_series & (~sig_series.shift(1, fill_value=False))
            raw_fire_dates = sig_series[fires].index
            
            # Des-agrupación por Cooldown
            fire_dates = []
            last_fire_idx = -9999
            for dt in raw_fire_dates:
                dt_d = dt.date() if hasattr(dt, 'date') else dt
                try:
                    curr_idx = daily_dates.index(dt_d)
                except ValueError:
                    curr_idx = -1
                if curr_idx - last_fire_idx >= cooldown_bars:
                    fire_dates.append(dt)
                    last_fire_idx = curr_idx
            
            for dt in fire_dates:
                target_d = dt.date() if hasattr(dt, 'date') else dt
                try:
                    target_idx = daily_dates.index(target_d)
                except ValueError:
                    continue
                
                # 1. Encontrar la pierna activa y siguiente
                active_legs = df_legs[(df_legs["start_d"] <= target_d) & (df_legs["end_d"] >= target_d)]
                if len(active_legs) == 0:
                    past_legs = df_legs[df_legs["end_d"] < target_d]
                    if len(past_legs) == 0:
                        continue
                    curr_leg = past_legs.iloc[-1]
                    next_legs = df_legs[df_legs["start_d"] >= target_d]
                    next_leg = next_legs.iloc[0] if len(next_legs) > 0 else None
                else:
                    curr_leg = active_legs.iloc[0]
                    curr_idx = df_legs.index[df_legs["leg_id"] == curr_leg["leg_id"]][0]
                    next_leg = df_legs.iloc[curr_idx + 1] if curr_idx + 1 < len(df_legs) else None
                    
                # 2. Timing y Pierna Relevante
                if target_type == "TOP":
                    if curr_leg["end_type"] == "MAX":
                        piv_date = curr_leg["end_d"]
                        piv_price = curr_leg["end_price"]
                        dist_bars = self.calc_bar_distance(df_daily, target_d, piv_date)
                        eval_leg = next_leg # Pierna bajista subsecuente
                    else:
                        piv_date = curr_leg["start_d"]
                        piv_price = curr_leg["start_price"]
                        dist_bars = self.calc_bar_distance(df_daily, target_d, piv_date)
                        eval_leg = curr_leg
                else: # BOTTOM
                    if curr_leg["end_type"] == "MIN":
                        piv_date = curr_leg["end_d"]
                        piv_price = curr_leg["end_price"]
                        dist_bars = self.calc_bar_distance(df_daily, target_d, piv_date)
                        eval_leg = next_leg # Pierna alcista subsecuente
                    else:
                        piv_date = curr_leg["start_d"]
                        piv_price = curr_leg["start_price"]
                        dist_bars = self.calc_bar_distance(df_daily, target_d, piv_date)
                        eval_leg = curr_leg
                        
                if eval_leg is None:
                    continue
                    
                slot = self.classify_timing_slot(dist_bars)
                spy_price_signal = float(df_daily.loc[dt, "spy"])
                
                # 3. Realidad de la Cartera en la Pierna Geométrica
                leg_end_d = eval_leg["end_d"].date() if hasattr(eval_leg["end_d"], 'date') else eval_leg["end_d"]
                leg_end_idx = int(np.searchsorted(daily_dates, leg_end_d, side='right') - 1)
                leg_end_idx = max(target_idx + 1, min(len(df_daily) - 1, leg_end_idx))
                
                leg_slice = df_daily.iloc[target_idx : leg_end_idx + 1]
                if len(leg_slice) < 2:
                    continue
                    
                eq_start = float(leg_slice["equity"].iloc[0])
                eq_end = float(leg_slice["equity"].iloc[-1])
                port_ret = ((eq_end / eq_start) - 1.0) * 100.0
                
                eq_series = leg_slice["equity"]
                eq_peak = eq_series.cummax()
                port_mae = float(((eq_series - eq_peak) / eq_peak).min() * 100.0)
                port_mfe = float(((eq_series - eq_start) / eq_start).max() * 100.0)
                
                spy_start = float(leg_slice["spy"].iloc[0])
                spy_end = float(leg_slice["spy"].iloc[-1])
                spy_ret = ((spy_end / spy_start) - 1.0) * 100.0
                alpha_leg = port_ret - spy_ret
                
                # 4. Clasificación Cinética y Métrica Peak-to-Trough
                # Slice desde el pivote extremo hasta el fin de la pierna
                piv_d = piv_date.date() if hasattr(piv_date, 'date') else piv_date
                piv_idx = int(np.searchsorted(daily_dates, piv_d, side='right') - 1)
                geom_start_idx = max(0, min(target_idx, piv_idx))
                geom_slice = df_daily.iloc[geom_start_idx : leg_end_idx + 1]
                
                if target_type == "TOP":
                    # Caída de SPY en la onda
                    spy_geom = geom_slice["spy"]
                    spy_pk = spy_geom.cummax()
                    spy_drop_pct = float(((spy_geom - spy_pk) / spy_pk).min() * 100.0)
                    
                    port_geom = geom_slice["equity"]
                    port_pk = port_geom.cummax()
                    port_drop_pct = float(((port_geom - port_pk) / port_pk).min() * 100.0)
                    
                    # Protección Real Peak-to-Trough
                    peak_to_trough_prot = abs(spy_drop_pct) - abs(port_drop_pct)
                    
                    # Clasificación formal
                    bars_to_trough = len(geom_slice)
                    tier, speed = self.classify_drawdown_tier(spy_drop_pct, bars_to_trough)
                    
                    econ_prot = max(0.0, -spy_ret - max(0.0, -port_ret))
                    econ_util = 0.0
                    payoff = econ_prot / max(0.1, abs(port_mae))
                else: # BOTTOM
                    spy_geom = geom_slice["spy"]
                    spy_trough = spy_geom.min()
                    spy_rally_pct = float(((spy_geom.iloc[-1] - spy_trough) / spy_trough) * 100.0)
                    
                    if spy_rally_pct < 10.0:
                        tier = "RALLY_PULLBACK (< 10%)"
                    elif 10.0 <= spy_rally_pct < 20.0:
                        tier = "RALLY_ESTRUCTURAL (10% a 20%)"
                    else:
                        tier = "RALLY_BULL_MARKET (>= 20%)"
                    speed = spy_rally_pct / max(1, len(geom_slice))
                    peak_to_trough_prot = 0.0
                    
                    econ_prot = 0.0
                    econ_util = max(0.0, port_ret)
                    payoff = econ_util / max(0.1, abs(port_mae))

                # 5. Reloj de Régimen (Stateful Lifetime)
                # Duración y retorno desde la señal hasta que el régimen transiciona a otro modo
                active_mode = str(leg_slice["mode"].iloc[0])
                mode_slice = df_daily.iloc[target_idx:]
                regime_end_idx = target_idx
                for m_idx in range(len(mode_slice)):
                    if mode_slice["mode"].iloc[m_idx] != active_mode:
                        regime_end_idx = target_idx + m_idx
                        break
                else:
                    regime_end_idx = len(df_daily) - 1
                    
                reg_df = df_daily.iloc[target_idx : regime_end_idx + 1]
                regime_dur_bars = len(reg_df)
                if regime_dur_bars > 1:
                    reg_eq_start = float(reg_df["equity"].iloc[0])
                    reg_eq_end = float(reg_df["equity"].iloc[-1])
                    regime_ret = ((reg_eq_end / reg_eq_start) - 1.0) * 100.0
                    
                    reg_eqs = reg_df["equity"]
                    reg_pk = reg_eqs.cummax()
                    regime_mae = float(((reg_eqs - reg_pk) / reg_pk).min() * 100.0)
                else:
                    regime_ret = 0.0
                    regime_mae = 0.0
                
                # Datos de Cartera
                if "cash_weight" in leg_slice.columns:
                    cash_w = float(leg_slice["cash_weight"].iloc[0])
                else:
                    cash_w = 1.0 if active_mode == "CRASH_SISTEMICO" else (0.5 if active_mode == "DISTRIBUCION_PRE_CRASH" else 0.0)
                
                top_sectors = active_mode
                if "top_sectors" in leg_slice.columns:
                    top_sectors = str(leg_slice["top_sectors"].iloc[0])

                events.append(RotationSignalEvent(
                    signal_name=sig_name,
                    fire_date=target_d,
                    target_type=target_type,
                    active_mode=active_mode,
                    timing_slot=slot,
                    dist_days_to_pivot=dist_bars,
                    spy_price_at_signal=spy_price_signal,
                    spy_pivot_price=float(piv_price),
                    spy_leg_return=float(eval_leg["leg_return"] * 100.0),
                    spy_leg_direction=str(eval_leg["leg_direction"]),
                    portfolio_equity_at_signal=eq_start,
                    portfolio_cash_weight=cash_w,
                    portfolio_top_sectors=top_sectors,
                    portfolio_leg_return=port_ret,
                    portfolio_mae=abs(port_mae),
                    portfolio_mfe=port_mfe,
                    alpha_leg=alpha_leg,
                    economic_protection_val=econ_prot,
                    economic_utility_val=econ_util,
                    payoff_asymmetry=payoff,
                    drawdown_tier=tier,
                    speed_pct_day=speed,
                    peak_to_trough_protection=peak_to_trough_prot,
                    regime_duration_bars=regime_dur_bars,
                    regime_return=regime_ret,
                    regime_mae=abs(regime_mae)
                ))
                
        return events
