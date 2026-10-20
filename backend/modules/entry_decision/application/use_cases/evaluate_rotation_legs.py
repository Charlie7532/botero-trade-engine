"""
Caso de Uso: Evaluador Forense de Rotación por Piernas ZigZag y Posición Real
=============================================================================
Clean Architecture: Application Layer (Use Cases)
Módulo: entry_decision / rotation

Valora formalmente las Señales Disruptivas de Rotación y los Regímenes de Mercado
midiendo la realidad integral de la cartera:
  1. No solo la pierna teórica de SPY, sino el RENDIMIENTO REAL DEL PORTAFOLIO según la
     composición que sostenía en ese instante (Pesos sectoriales, Cash, Defensivos).
  2. Valor Fáctico de Protección: Capital salvado en dólares y % frente al colapso de la pierna bajista.
  3. Valor Fáctico de Utilidad: Alpha real capturado en la pierna alcista gracias a la rotación de beta.
  4. Dolor Real Incurrido (Portfolio MAE): Drawdown máximo que la cuenta soportó dentro de la pierna.
  5. Calificación Canónica de Timing y Detección de Puntos Ciegos (Cash Drag, Ruptura de Correlación).
  6. Arquitectura Dual: Evaluación Canónica T+0 (medición de señal en su punto exacto) y
     Diagnóstico Secundario de Estrés Friccional (T+1 y deslizamiento en bps).
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import date, datetime
import pandas as pd
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate


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
    spy_leg_return: float          # Retorno total de la pierna ZigZag
    spy_leg_direction: str         # "UP" o "DOWN"
    
    # Realidad del Portafolio (Lo que la posición contenía en el momento)
    portfolio_equity_at_signal: float
    portfolio_cash_weight: float   # Peso en Cash (0.0 a 1.0)
    portfolio_top_sectors: str     # Ej: "XLF: 33%, XLY: 33%, XLK: 33%" o "XLP: 17%, Cash: 50%"
    portfolio_leg_return: float    # Retorno real que experimentó la cuenta en la pierna
    portfolio_mae: float           # Drawdown real soportado por la cuenta en la pierna (%)
    portfolio_mfe: float           # Ganancia máxima alcanzada por la cuenta en la pierna (%)
    
    # Valor Económico Neto Generado
    alpha_leg: float               # Retorno Portafolio - Retorno SPY en la pierna
    economic_protection_val: float # % de caída que se evitó absorber (en piernas bajistas)
    economic_utility_val: float    # % de subida capturada (en piernas alcistas)
    payoff_asymmetry: float        # Valor Generado / MAE Soportado


class RotationLegEvaluator:
    """
    Evaluador Forense de Rotación por Piernas ZigZag y Posición Real de Cartera.
    Adhiere estrictamente a Clean Architecture (Port & Repository vía TimescaleDataStore)
    y previene vulnerabilidades CWE-89 mediante consultas SQL parametrizadas.
    """
    SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]

    def __init__(self, store: Optional[TimescaleDataStore] = None):
        self.store = store or TimescaleDataStore()

    def load_zigzag_legs(self, ticker: str = "SPY", scale: str = "zz50") -> pd.DataFrame:
        """Carga piernas ZigZag confirmadas delegando en el DataStore parametrizado (CWE-89 safe)."""
        return self.store.load_zigzag_legs(ticker=ticker, scale=scale)

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

    def evaluate_signals_on_portfolio(
        self,
        df_daily: pd.DataFrame,
        df_legs: pd.DataFrame,
        signals_dict: Dict[str, Tuple[pd.Series, str]] # {"Nombre": (Series_booleana, "TOP"|"BOTTOM")}
    ) -> List[RotationSignalEvent]:
        """
        Evalúa cada disparo de señal correlacionando la pierna ZigZag con
        la telemetría real del portafolio (equity, cash, retornos).
        Mide la señal en su punto exacto canónico (T+0).
        """
        events: List[RotationSignalEvent] = []
        
        for sig_name, (sig_series, target_type) in signals_dict.items():
            # Disparos de flanco ascendente (primer día de la señal)
            fires = sig_series & (~sig_series.shift(1, fill_value=False))
            fire_dates = df_daily[fires].index
            
            for dt in fire_dates:
                target_d = dt.date() if hasattr(dt, 'date') else dt
                
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
                
                # 3. Realidad de la Cartera en el Intervalo de la Pierna
                leg_end_val = pd.to_datetime(eval_leg["end_d"])
                dt_ts = pd.to_datetime(dt)
                if df_daily.index.tz is not None:
                    if leg_end_val.tz is None:
                        leg_end_val = leg_end_val.tz_localize(df_daily.index.tz)
                    if dt_ts.tz is None:
                        dt_ts = dt_ts.tz_localize(df_daily.index.tz)
                else:
                    if leg_end_val.tz is not None:
                        leg_end_val = leg_end_val.tz_localize(None)
                    if dt_ts.tz is not None:
                        dt_ts = dt_ts.tz_localize(None)

                mask = (df_daily.index >= dt_ts) & (df_daily.index <= leg_end_val)
                leg_slice = df_daily[mask]
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
                
                # Valor de Protección vs Utilidad
                if target_type == "TOP":
                    # Si SPY cayó -20% y el portafolio cayó -3%, protegimos 17%
                    econ_prot = max(0.0, -spy_ret - max(0.0, -port_ret))
                    econ_util = 0.0
                    payoff = econ_prot / max(0.1, abs(port_mae))
                else:
                    econ_prot = 0.0
                    # Si el portafolio subió +30% y SPY +20%, utilidad total de cartera
                    econ_util = max(0.0, port_ret)
                    payoff = econ_util / max(0.1, abs(port_mae))
                    
                active_mode = str(leg_slice["mode"].iloc[0])
                
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
                    payoff_asymmetry=payoff
                ))
                
        return events
