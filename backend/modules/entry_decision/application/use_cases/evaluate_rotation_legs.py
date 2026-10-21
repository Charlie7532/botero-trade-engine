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
  4. Sin des-agrupación temporal: cada flanco ascendente de una señal es un evento.
     La agregación se hace por EPISODIO DE RÉGIMEN (cambio de estado), nunca por días.
  5. Rendimiento Real del Portafolio: Evalúa los pesos sectoriales reales, cash y
     defensivos que la cuenta sostenía en cada momento.
  6. Autopsia por Episodio de Régimen (evaluate_regime_episodes): cada episodio se
     clasifica en PERDIDA_EXCEDENTE / PERDIDA_MITIGADA / DEJO_DE_GANAR / GANANCIA_SUPERIOR
     con diagnóstico mecánico (exposición, pierna zz de entrada, pivotes atravesados,
     latencia tras pivote, barras retenidas por temporizador, señales vivas).
     Atribución T+0: el retorno de la barra t+1 pertenece al régimen decidido al cierre t.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import date, datetime
import pandas as pd
import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.zigzag_core import compute_zigzag_legs


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
    regime_duration_bars: int      # Barras desde la señal hasta que el régimen activo en la señal cambia
    regime_return: float           # Retorno del portafolio durante ese tramo del régimen (%)
    regime_mae: float              # Drawdown soportado por el portafolio durante ese tramo (%)

    # === CORRECCIÓN: comparabilidad y sucesión del régimen ===
    spy_return_from_signal: float = float("nan")  # Retorno SPY desde la señal al fin de la pierna (%), comparable con portfolio_leg_return
    leg_duration_bars: int = 0                    # Duración pivote-a-pivote de la pierna evaluada (barras)
    leg_confirmed: bool = True                    # False si la pierna evaluada es la última, aún no confirmada
    regime_next_mode: str = ""                    # Régimen que recibió la posta (vacío si no cambió hasta el final)
    regime_exit_date: Optional[date] = None       # Primera barra del régimen sucesor


@dataclass
class RegimeEpisode:
    """Episodio continuo de un régimen: qué se tenía, qué hizo el mercado, qué se perdió o dejó de ganar y por qué."""
    episode_id: int
    mode: str
    prev_mode: str                 # Quién entregó la posta
    next_mode: str                 # Quién la recibió
    start_d: date                  # Primera barra con el régimen (decisión al cierre)
    end_d: date                    # Última barra con el régimen
    bars: int
    # Atribución T+0: barras start+1 .. end+1
    port_ret: float                # %
    spy_ret: float                 # %
    alpha: float                   # pp
    port_logret: float             # 100*ln, aditivo entre episodios
    spy_logret: float              # 100*ln
    port_mae: float                # % (positivo)
    port_mfe: float                # %
    spy_mae: float                 # % (positivo)
    loss_pp: float                 # min(0, port_ret)
    missed_gain_pp: float          # max(0, spy_ret) - max(0, port_ret), acotado a >= 0
    protection_pp: float           # max(0, -spy_ret) - max(0, -port_ret); negativo = pérdida excedente
    outcome: str                   # PERDIDA_EXCEDENTE | PERDIDA_MITIGADA | DEJO_DE_GANAR | GANANCIA_SUPERIOR
    # Exposición
    cash_avg: float
    defensive_share: float         # Fracción defensiva (XLP/XLU/XLV) del capital invertido
    exposure_class: str            # CASH | DEFENSIVO | OFENSIVO
    holdings_at_entry: str
    # Contexto ZigZag (verdad ex-post de la escala evaluada)
    entry_leg_direction: str       # UP | DOWN | SIN_PIERNA
    entry_leg_progress: float      # 0 = pivote de inicio, 1 = pivote de fin
    pivots_inside: str             # Ej: "MAX@2007-10-09"
    bars_after_last_pivot: int     # Latencia: barras que el régimen siguió tras el último pivote atravesado (-1 si ninguno)
    # Máquina de estados
    timer_override_bars: int       # Barras en que el temporizador retuvo el estado contra el clasificador
    classifier_requested_mode: str # Estado que pedía el clasificador en esas barras
    signals_inside: str            # Flancos de señales dentro del episodio
    diagnosis: str


@dataclass
class SignalCyclePosition:
    """
    Evento anunciador evaluado en el ciclo de UNA escala zz (no en días).
    TOP afirma 'viene un MAX'; BOTTOM afirma 'viene un MIN'.
    phase:
      PRE_PIVOTE           — dispara dentro de la pierna que termina en el pivote anunciado (anticipa)
      EN_PIVOTE            — dispara en la barra del pivote
      ANTES_DE_CONFIRMAR   — tras el extremo, antes de que el zz pueda confirmarlo (le gana al zz)
      POST_CONFIRMACION    — después de que el zz confirmó el giro (tardía)
    progress: fracción de la pierna transcurrida (PRE: 0=pivote opuesto previo, 1=pivote anunciado;
              post-pivote: fracción de la pierna contraria ya consumida).
    value_logpp: 100*ln del resultado de actuar en t hasta la CONFIRMACIÓN del pivote opuesto siguiente
              (re-entrada/salida mecánica del mismo zz). TOP: ln(P_t / P_conf_MIN). BOTTOM: ln(P_conf_MAX / P_t).
    adverse_logpp: costo de anticiparse (TOP: subida cedida hasta el MAX; BOTTOM: caída sufrida hasta el MIN).
    """
    signal_name: str
    fire_date: date
    target_type: str
    scale: str
    phase: str
    progress: float
    bars_vs_confirm: int           # t - barra de confirmación del pivote anunciado (negativo = antes que el zz)
    ref_pivot_date: Optional[date]
    ref_confirm_date: Optional[date]
    value_logpp: float
    adverse_logpp: float
    resolved: bool                 # False si el pivote opuesto aún no está confirmado


@dataclass
class RegimeScaleContext:
    """Posición de la entrada o salida de un episodio de régimen en el ciclo de una escala zz."""
    episode_id: int
    mode: str
    moment: str                    # ENTRADA | SALIDA
    bar_date: date
    scale: str
    leg_direction: str
    leg_progress: float
    last_confirmed_pivot: str      # MAX | MIN | ""
    last_pivot_date: Optional[date]
    last_confirm_date: Optional[date]
    bars_since_confirm: int        # barras desde que el zz confirmó su último giro (-1 si ninguno)


@dataclass
class TransitionBridge:
    """Puente anuncio → acción: cuándo avisaron las señales y cuándo actuó el régimen, en la misma escala."""
    transition_date: date
    from_mode: str
    to_mode: str
    direction: str                 # DEFENSA (ofensivo→defensivo/cash) | OFENSIVA (defensivo/cash→ofensivo)
    scale: str
    action_phase: str
    action_progress: float
    action_bars_vs_confirm: int
    action_value_logpp: float
    n_events_in_cycle: int
    first_event: str
    first_event_phase: str
    first_event_progress: float
    bars_first_event_to_action: int
    first_event_value_logpp: float
    last_event: str
    last_event_phase: str
    bars_last_event_to_action: int
    last_event_value_logpp: float


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
    def compute_zigzag_from_bars(df_bars: pd.DataFrame, threshold_pct: float = 0.10,
                                 include_provisional: bool = False) -> pd.DataFrame:
        """
        Piernas ZigZag desde el kernel canónico de dominio (zigzag_core.compute_zigzag_legs): misma física que
        market.zigzag_legs (pivotes en high/low, confirmación cuando el extremo opuesto toca ±threshold_pct).
        Si df_bars sólo trae 'close', se usa close como high y low (física de cierre).
        Por defecto threshold_pct = 0.10 (zz100, Corrección Técnica).
        include_provisional=True agrega la última pierna en curso (confirmed=False) para no
        descartar el tramo final de la muestra. Por defecto se mantiene el conjunto histórico.
        """
        close = df_bars['close'].values.astype(float)
        high = df_bars['high'].values.astype(float) if 'high' in df_bars.columns else close
        low = df_bars['low'].values.astype(float) if 'low' in df_bars.columns else close
        dates = pd.to_datetime(df_bars.index).date
        raw = compute_zigzag_legs(dates=np.arange(len(close)), opens=close, highs=high, lows=low, closes=close,
                                  scale_name=f"zz{int(round(threshold_pct * 1000))}", min_pct=threshold_pct)

        def leg(k, si, ei, st, et, sp, ep, ci):
            return {'leg_id': k, 'start_d': dates[si], 'end_d': dates[ei], 'start_type': st, 'end_type': et,
                    'start_price': sp, 'end_price': ep, 'ret': (ep - sp) / sp, 'leg_return': (ep - sp) / sp,
                    'leg_direction': 'UP' if et == 'MAX' else 'DOWN', 'duration_bars': ei - si,
                    'confirm_d': dates[ci] if ci is not None else None, 'confirmed': ci is not None}

        legs = [leg(k, int(r['start_timestamp']), int(r['end_timestamp']), r['start_type'], r['end_type'],
                    r['start_price'], r['end_price'], int(r['confirmed_at_timestamp']))
                for k, r in enumerate(raw, 1)]
        if include_provisional and raw:
            # Estado del kernel tras la última confirmación: el extremo en curso arranca en la barra de confirmación.
            last = raw[-1]
            ci, ei = int(last['confirmed_at_timestamp']), int(last['end_timestamp'])
            if last['end_type'] == 'MAX':
                end_i, et = ci + int(np.argmin(low[ci:])), 'MIN'
                end_p = float(low[end_i])
            else:
                end_i, et = ci + int(np.argmax(high[ci:])), 'MAX'
                end_p = float(high[end_i])
            if end_i > ei:
                legs.append(leg(len(raw) + 1, ei, end_i, last['end_type'], et, last['end_price'], end_p, None))
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
        """Distancia en barras de trading entre dos fechas. Nunca usa días de calendario:
        si una fecha no es barra, se ubica en la última barra anterior o igual."""
        idx_dates = [d.date() if hasattr(d, 'date') else d for d in df_daily.index]
        t_idx = int(np.searchsorted(idx_dates, target_d, side='right') - 1)
        p_idx = int(np.searchsorted(idx_dates, piv_date, side='right') - 1)
        return t_idx - p_idx

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
    ) -> List[RotationSignalEvent]:
        """
        Evalúa cada disparo de señal correlacionando la pierna ZigZag y la duración de régimen
        con la telemetría real del portafolio (equity, cash, retornos).
        Cada flanco ascendente es un evento: no hay des-agrupación temporal.
        """
        events: List[RotationSignalEvent] = []
        df_daily = df_daily.sort_index()
        daily_dates = [d.date() if hasattr(d, 'date') else d for d in df_daily.index]
        
        for sig_name, (sig_series, target_type) in signals_dict.items():
            # Disparos de flanco ascendente (primer día de la señal)
            fires = sig_series & (~sig_series.shift(1, fill_value=False))
            fire_dates = sig_series[fires].index
            
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
                
                # La taxonomía es un hecho de la pierna (pivote a pivote), no del tramo desde la señal
                leg_ret_pct = float(eval_leg["leg_return"] * 100.0)
                leg_dur = eval_leg.get("duration_bars") if hasattr(eval_leg, "get") else None
                if leg_dur is None or pd.isna(leg_dur):
                    leg_dur = self.calc_bar_distance(df_daily, leg_end_d, eval_leg["start_d"].date() if hasattr(eval_leg["start_d"], 'date') else eval_leg["start_d"])
                leg_dur = int(leg_dur)

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
                    
                    # Clasificación formal sobre la pierna completa
                    tier, speed = self.classify_drawdown_tier(leg_ret_pct, leg_dur)
                    
                    econ_prot = max(0.0, -spy_ret - max(0.0, -port_ret))
                    econ_util = 0.0
                    payoff = econ_prot / max(0.1, abs(port_mae))
                else: # BOTTOM
                    if leg_ret_pct < 10.0:
                        tier = "RALLY_PULLBACK (< 10%)"
                    elif 10.0 <= leg_ret_pct < 20.0:
                        tier = "RALLY_ESTRUCTURAL (10% a 20%)"
                    else:
                        tier = "RALLY_BULL_MARKET (>= 20%)"
                    speed = abs(leg_ret_pct) / max(1, leg_dur)
                    peak_to_trough_prot = 0.0
                    
                    econ_prot = 0.0
                    econ_util = max(0.0, port_ret)
                    payoff = econ_util / max(0.1, abs(port_mae))

                # 5. Reloj de Régimen (Stateful Lifetime)
                # Duración y retorno desde la señal hasta que el régimen transiciona a otro modo
                active_mode = str(leg_slice["mode"].iloc[0])
                mode_slice = df_daily.iloc[target_idx:]
                regime_end_idx = target_idx
                next_mode, exit_date = "", None
                for m_idx in range(len(mode_slice)):
                    if mode_slice["mode"].iloc[m_idx] != active_mode:
                        regime_end_idx = target_idx + m_idx
                        next_mode = str(mode_slice["mode"].iloc[m_idx])
                        exit_date = daily_dates[regime_end_idx]
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
                # Sin dato de cash no se inventa: los pesos reales se renormalizan en el gate
                cash_w = float(leg_slice["cash_weight"].iloc[0]) if "cash_weight" in leg_slice.columns else float("nan")
                
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
                    regime_mae=abs(regime_mae),
                    spy_return_from_signal=spy_ret,
                    leg_duration_bars=leg_dur,
                    leg_confirmed=bool(eval_leg.get("confirmed", True)) if hasattr(eval_leg, "get") else True,
                    regime_next_mode=next_mode,
                    regime_exit_date=exit_date,
                ))
                
        return events

    # ───────────────────── Autopsia por episodio de régimen ─────────────────────
    DEFENSIVE = ("XLP", "XLU", "XLV")

    @classmethod
    def _defensive_share(cls, top_sectors: str) -> float:
        """Fracción defensiva del capital invertido a partir de 'XLV:59%, XLP:29%, Cash:12%'."""
        inv, dfn = 0.0, 0.0
        for tok in str(top_sectors).split(","):
            if ":" not in tok:
                continue
            name, val = tok.strip().split(":", 1)
            try:
                w = float(val.strip().rstrip("%"))
            except ValueError:
                continue
            if name.strip().lower() == "cash":
                continue
            inv += w
            if name.strip() in cls.DEFENSIVE:
                dfn += w
        return dfn / inv if inv > 0 else 0.0

    @staticmethod
    def classify_outcome(port_ret: float, spy_ret: float) -> str:
        if port_ret < 0 and port_ret < spy_ret:
            return "PERDIDA_EXCEDENTE"
        if port_ret < 0:
            return "PERDIDA_MITIGADA"
        if port_ret < spy_ret:
            return "DEJO_DE_GANAR"
        return "GANANCIA_SUPERIOR"

    def evaluate_regime_episodes(
        self,
        df_daily: pd.DataFrame,
        df_legs: pd.DataFrame,
        signals_dict: Optional[Dict[str, Tuple[pd.Series, str]]] = None,
    ) -> List[RegimeEpisode]:
        """
        Recorre cada episodio continuo de régimen y documenta qué se perdió o dejó de ganar y por qué.
        df_daily requiere: spy, equity, mode. Opcionales: cash_weight, top_sectors,
        locked + cf_mode (estado del clasificador sin temporizador).
        Atribución T+0: el régimen decidido al cierre t posee el retorno de la barra t+1, por lo que
        el episodio [s, e] posee las barras s+1..e+1 y la suma de port_logret - spy_logret de todos
        los episodios reconcilia exactamente con ln(equity_final/equity_inicial) - ln(spy_final/spy_inicial).
        """
        df = df_daily.sort_index()
        n = len(df)
        dates = [d.date() if hasattr(d, 'date') else d for d in df.index]
        eq = df["equity"].values.astype(float)
        spy = df["spy"].values.astype(float)
        mode = df["mode"].astype(str).values
        cash = df["cash_weight"].values.astype(float) if "cash_weight" in df.columns else np.full(n, np.nan)
        tops = df["top_sectors"].astype(str).values if "top_sectors" in df.columns else np.full(n, "")
        locked = df["locked"].values.astype(bool) if "locked" in df.columns else np.zeros(n, dtype=bool)
        cf_mode = df["cf_mode"].astype(str).values if "cf_mode" in df.columns else mode

        # Pierna vigente por barra (la barra pivote pertenece a la pierna que nace en ella)
        leg_dir = np.array(["SIN_PIERNA"] * n, dtype=object)
        leg_s = np.full(n, -1)
        leg_e = np.full(n, -1)
        pivots = []  # (idx, tipo)
        for _, L in df_legs.iterrows():
            s_d = L["start_d"].date() if hasattr(L["start_d"], 'date') else L["start_d"]
            e_d = L["end_d"].date() if hasattr(L["end_d"], 'date') else L["end_d"]
            si = int(np.searchsorted(dates, s_d, side='left'))
            ei = int(np.searchsorted(dates, e_d, side='left'))
            leg_dir[si:ei] = L["leg_direction"]
            leg_s[si:ei] = si
            leg_e[si:ei] = ei
            if bool(L.get("confirmed", True)):
                pivots.append((ei, str(L["end_type"])))

        # Flancos de señales
        fires = {}
        for name, (sr, _) in (signals_dict or {}).items():
            s = sr.reindex(df.index).fillna(False).astype(bool).values
            fires[name] = np.where(s & ~np.r_[False, s[:-1]])[0]

        seg_starts = [0] + [i for i in range(1, n) if mode[i] != mode[i - 1]]
        out: List[RegimeEpisode] = []
        for k, s in enumerate(seg_starts):
            e = (seg_starts[k + 1] - 1) if k + 1 < len(seg_starts) else n - 1
            last = min(e + 1, n - 1)
            port_ret = (eq[last] / eq[s] - 1.0) * 100.0
            spy_ret = (spy[last] / spy[s] - 1.0) * 100.0
            path_eq, path_spy = eq[s:last + 1], spy[s:last + 1]
            port_mae = float(-(path_eq / np.maximum.accumulate(path_eq) - 1).min() * 100.0)
            spy_mae = float(-(path_spy / np.maximum.accumulate(path_spy) - 1).min() * 100.0)
            port_mfe = float((path_eq / path_eq[0] - 1).max() * 100.0)

            cash_avg = float(np.nanmean(cash[s:e + 1])) if not np.all(np.isnan(cash[s:e + 1])) else float("nan")
            dshare = float(np.mean([self._defensive_share(t) for t in tops[s:e + 1]]))
            if not np.isnan(cash_avg) and cash_avg >= 0.5:
                expo = "CASH"
            elif dshare >= 0.5:
                expo = "DEFENSIVO"
            else:
                expo = "OFENSIVO"

            ldir = str(leg_dir[s])
            prog = float((s - leg_s[s]) / max(1, leg_e[s] - leg_s[s])) if leg_s[s] >= 0 else float("nan")
            inside = [(p, t) for p, t in pivots if s <= p <= e]
            piv_txt = ", ".join(f"{t}@{dates[p]}" for p, t in inside)
            latency = (last - inside[-1][0]) if inside else -1

            lk = locked[s:e + 1]
            timer_bars = int(lk.sum())
            req = ""
            if timer_bars:
                vals, cnt = np.unique(cf_mode[s:e + 1][lk], return_counts=True)
                req = str(vals[np.argmax(cnt)])

            sig_txt = ", ".join(f"{nm}x{int(((f >= s) & (f <= e)).sum())}" for nm, f in fires.items()
                                if ((f >= s) & (f <= e)).any())

            outcome = self.classify_outcome(port_ret, spy_ret)
            why = []
            if outcome.startswith("PERDIDA"):
                if expo == "OFENSIVO" and ldir == "DOWN":
                    why.append(f"OFENSIVA_DENTRO_DE_PIERNA_BAJISTA(progreso={prog:.2f})")
                if expo != "CASH" and any(t == "MAX" for _, t in inside):
                    why.append(f"PERMANENCIA_TRAS_TECHO_ZZ(latencia={latency}b)")
                if expo == "DEFENSIVO" and not np.isnan(cash_avg) and cash_avg < 0.05:
                    why.append("DEFENSA_SIN_LIQUIDEZ(defensivos_100%_invertidos)")
                if expo == "OFENSIVO" and ldir == "UP" and not inside:
                    why.append("RETROCESO_INTRA_PIERNA_ALCISTA(bajo_umbral_zz)")
            elif outcome == "DEJO_DE_GANAR":
                if expo == "CASH":
                    why.append("LIQUIDEZ_EN_ALZA")
                if expo == "DEFENSIVO":
                    why.append("DEFENSIVOS_EN_ALZA")
                if expo != "OFENSIVO" and any(t == "MIN" for _, t in inside):
                    why.append(f"PERMANENCIA_TRAS_SUELO_ZZ(latencia={latency}b)")
                if expo == "OFENSIVO":
                    why.append("SELECCION_SECTORIAL_REZAGADA")
            if timer_bars and req and req != mode[s]:
                why.append(f"ESTADO_RETENIDO_POR_TEMPORIZADOR({timer_bars}b, clasificador_pedia={req})")
            if outcome == "PERDIDA_EXCEDENTE" and expo == "OFENSIVO" and not why:
                why.append("SELECCION_SECTORIAL_PERDEDORA")

            out.append(RegimeEpisode(
                episode_id=k + 1, mode=str(mode[s]),
                prev_mode=str(mode[s - 1]) if s > 0 else "",
                next_mode=str(mode[e + 1]) if e + 1 < n else "",
                start_d=dates[s], end_d=dates[e], bars=e - s + 1,
                port_ret=port_ret, spy_ret=spy_ret, alpha=port_ret - spy_ret,
                port_logret=float(np.log(eq[last] / eq[s]) * 100.0),
                spy_logret=float(np.log(spy[last] / spy[s]) * 100.0),
                port_mae=port_mae, port_mfe=port_mfe, spy_mae=spy_mae,
                loss_pp=min(0.0, port_ret),
                missed_gain_pp=max(0.0, max(0.0, spy_ret) - max(0.0, port_ret)),
                protection_pp=max(0.0, -spy_ret) - max(0.0, -port_ret),
                outcome=outcome, cash_avg=cash_avg, defensive_share=dshare, exposure_class=expo,
                holdings_at_entry=str(tops[s]),
                entry_leg_direction=ldir, entry_leg_progress=prog,
                pivots_inside=piv_txt, bars_after_last_pivot=int(latency),
                timer_override_bars=timer_bars, classifier_requested_mode=req,
                signals_inside=sig_txt, diagnosis=" | ".join(why),
            ))
        return out

    # ─────────────── Ciclo multiescala: anuncio (evento) vs acción (régimen) ───────────────
    @staticmethod
    def _to_date(x):
        return x.date() if hasattr(x, 'date') else x

    @classmethod
    def _scale_structure(cls, dates: list, df_legs: pd.DataFrame):
        """Por pierna: (inicio, fin, confirmación del pivote final, dirección, confirmada) en índices de barra.
        leg_of[t] = pierna vigente en t (la barra pivote pertenece a la pierna que nace en ella)."""
        n = len(dates)
        L = []
        for _, r in df_legs.iterrows():
            si = int(np.searchsorted(dates, cls._to_date(r["start_d"]), side='left'))
            ei = int(np.searchsorted(dates, cls._to_date(r["end_d"]), side='left'))
            cd = r.get("confirm_d", None)
            ci = int(np.searchsorted(dates, cls._to_date(cd), side='left')) if cd is not None and not pd.isna(cd) else -1
            L.append((si, ei, ci, str(r["leg_direction"]), bool(r.get("confirmed", True))))
        leg_of = np.full(n, -1)
        for k, (si, ei, _, _, _) in enumerate(L):
            leg_of[si:ei] = k
        return L, leg_of

    @staticmethod
    def _cycle_position(t: int, target: str, L: list, leg_of: np.ndarray, price: np.ndarray) -> Optional[dict]:
        """Ubica la barra t en el ciclo de la escala respecto del pivote que afirma 'target' (TOP=MAX, BOTTOM=MIN)."""
        k = int(leg_of[t]) if 0 <= t < len(leg_of) else -1
        if k < 0:
            return None
        si, ei, ci, d, _ = L[k]
        if d == ("UP" if target == "TOP" else "DOWN"):
            phase, ref, ref_c, nxt = "PRE_PIVOTE", ei, ci, k + 1
        else:
            ref, ref_c, nxt = si, (L[k - 1][2] if k > 0 else -1), k
            if t == si:
                phase = "EN_PIVOTE"
            elif ref_c >= 0 and t < ref_c:
                phase = "ANTES_DE_CONFIRMAR"
            else:
                phase = "POST_CONFIRMACION"
        progress = (t - si) / max(1, ei - si)
        if nxt < len(L) and L[nxt][4] and L[nxt][2] >= 0:
            x = L[nxt][2]  # confirmación mecánica del pivote opuesto: salida/re-entrada del mismo zz
            value = 100.0 * (np.log(price[t] / price[x]) if target == "TOP" else np.log(price[x] / price[t]))
            resolved = True
        else:
            value, resolved = float("nan"), False
        adverse = 100.0 * np.log(price[ref] / price[t]) if phase == "PRE_PIVOTE" else 0.0
        return dict(phase=phase, progress=float(progress),
                    bars_vs_confirm=int(t - ref_c) if ref_c >= 0 else int(t - ref),
                    ref_idx=ref, ref_c=ref_c, value_logpp=float(value), adverse_logpp=float(adverse), resolved=resolved)

    def evaluate_signal_cycles(
        self,
        df_daily: pd.DataFrame,
        legs_by_scale: Dict[str, pd.DataFrame],
        signals_dict: Dict[str, Tuple[pd.Series, str]],
        both_directions: bool = False,
    ) -> List[SignalCyclePosition]:
        """Cada flanco de cada señal, ubicado en el ciclo de cada escala zz. both_directions evalúa la señal
        como TOP y como BOTTOM para revelar su naturaleza real independientemente de su etiqueta."""
        df = df_daily.sort_index()
        dates = [self._to_date(d) for d in df.index]
        price = df["spy"].values.astype(float)
        structs = {sc: self._scale_structure(dates, lg) for sc, lg in legs_by_scale.items()}
        out: List[SignalCyclePosition] = []
        for name, (sr, ttype) in signals_dict.items():
            s = sr.reindex(df.index).fillna(False).astype(bool).values
            idxs = np.where(s & ~np.r_[False, s[:-1]])[0]
            for tgt in (("TOP", "BOTTOM") if both_directions else (ttype,)):
                for sc, (L, leg_of) in structs.items():
                    for t in idxs:
                        p = self._cycle_position(int(t), tgt, L, leg_of, price)
                        if p is None:
                            continue
                        out.append(SignalCyclePosition(
                            signal_name=name, fire_date=dates[t], target_type=tgt, scale=sc,
                            phase=p["phase"], progress=p["progress"], bars_vs_confirm=p["bars_vs_confirm"],
                            ref_pivot_date=dates[p["ref_idx"]] if p["ref_idx"] < len(dates) else None,
                            ref_confirm_date=dates[p["ref_c"]] if 0 <= p["ref_c"] < len(dates) else None,
                            value_logpp=p["value_logpp"], adverse_logpp=p["adverse_logpp"], resolved=p["resolved"]))
        return out

    def cycle_base_rates(self, df_daily: pd.DataFrame, legs_by_scale: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Tasa base: la misma medida aplicada a TODAS las barras (un 'evento' en cada barra)."""
        df = df_daily.sort_index()
        dates = [self._to_date(d) for d in df.index]
        price = df["spy"].values.astype(float)
        rows = []
        for sc, lg in legs_by_scale.items():
            L, leg_of = self._scale_structure(dates, lg)
            for tgt in ("TOP", "BOTTOM"):
                P = [self._cycle_position(t, tgt, L, leg_of, price) for t in range(len(dates))]
                P = [p for p in P if p is not None and p["resolved"]]
                v = np.array([p["value_logpp"] for p in P])
                ph = pd.Series([p["phase"] for p in P]).value_counts(normalize=True)
                rows.append(dict(scale=sc, target_type=tgt, n_bars=len(P), base_hit=float((v > 0).mean()),
                                 base_value_mean=float(v.mean()), base_value_median=float(np.median(v)),
                                 base_pct_pre=float(ph.get("PRE_PIVOTE", 0.0)),
                                 base_pct_antes_conf=float(ph.get("ANTES_DE_CONFIRMAR", 0.0))))
        return pd.DataFrame(rows)

    def evaluate_regime_cycle_context(
        self,
        episodes: List[RegimeEpisode],
        df_daily: pd.DataFrame,
        legs_by_scale: Dict[str, pd.DataFrame],
    ) -> List[RegimeScaleContext]:
        """Entrada y salida de cada episodio ubicadas en el ciclo de cada escala, con el último giro confirmado."""
        df = df_daily.sort_index()
        dates = [self._to_date(d) for d in df.index]
        n = len(dates)
        out: List[RegimeScaleContext] = []
        for sc, lg in legs_by_scale.items():
            L, leg_of = self._scale_structure(dates, lg)
            conf = sorted((ci, ei, "MAX" if d == "UP" else "MIN") for (si, ei, ci, d, c) in L if c and ci >= 0)
            cis = np.array([c[0] for c in conf])
            for ep in episodes:
                s = int(np.searchsorted(dates, ep.start_d, side='left'))
                x = int(np.searchsorted(dates, ep.end_d, side='left')) + 1
                for moment, b in (("ENTRADA", s), ("SALIDA", x)):
                    if b >= n:
                        continue
                    k = int(leg_of[b])
                    ldir = L[k][3] if k >= 0 else "SIN_PIERNA"
                    prog = (b - L[k][0]) / max(1, L[k][1] - L[k][0]) if k >= 0 else float("nan")
                    j = int(np.searchsorted(cis, b, side='right')) - 1
                    out.append(RegimeScaleContext(
                        episode_id=ep.episode_id, mode=ep.mode, moment=moment, bar_date=dates[b], scale=sc,
                        leg_direction=ldir, leg_progress=float(prog),
                        last_confirmed_pivot=conf[j][2] if j >= 0 else "",
                        last_pivot_date=dates[conf[j][1]] if j >= 0 else None,
                        last_confirm_date=dates[conf[j][0]] if j >= 0 else None,
                        bars_since_confirm=int(b - conf[j][0]) if j >= 0 else -1))
        return out

    def evaluate_transition_bridge(
        self,
        episodes: List[RegimeEpisode],
        df_daily: pd.DataFrame,
        legs_by_scale: Dict[str, pd.DataFrame],
        signals_dict: Dict[str, Tuple[pd.Series, str]],
    ) -> List[TransitionBridge]:
        """
        Para cada cambio de exposición (ofensivo ↔ defensivo/cash, medido por la cartera real, no por nombres
        de régimen) ubica la acción en el ciclo y la compara con los anuncios del mismo ciclo: desde el pivote
        opuesto previo hasta la acción. Separa 'no lo vimos' de 'lo vimos y no actuamos'.
        """
        df = df_daily.sort_index()
        dates = [self._to_date(d) for d in df.index]
        price = df["spy"].values.astype(float)
        fires = {"TOP": [], "BOTTOM": []}
        for name, (sr, ttype) in signals_dict.items():
            s = sr.reindex(df.index).fillna(False).astype(bool).values
            for t in np.where(s & ~np.r_[False, s[:-1]])[0]:
                if ttype in fires:
                    fires[ttype].append((int(t), name))
        for v in fires.values():
            v.sort()
        structs = {sc: self._scale_structure(dates, lg) for sc, lg in legs_by_scale.items()}
        defensive = {"CASH", "DEFENSIVO"}
        out: List[TransitionBridge] = []
        for a, b in zip(episodes[:-1], episodes[1:]):
            if (a.exposure_class in defensive) == (b.exposure_class in defensive):
                continue
            direction = "DEFENSA" if b.exposure_class in defensive else "OFENSIVA"
            tgt = "TOP" if direction == "DEFENSA" else "BOTTOM"
            x = int(np.searchsorted(dates, b.start_d, side='left'))
            for sc, (L, leg_of) in structs.items():
                act = self._cycle_position(x, tgt, L, leg_of, price)
                if act is None:
                    continue
                k = int(leg_of[x])
                si, _, _, d, _ = L[k]
                ws = si if d == ("UP" if tgt == "TOP" else "DOWN") else (L[k - 1][0] if k > 0 else si)
                evs = [(t, nm) for t, nm in fires[tgt] if ws <= t <= x]
                fp = self._cycle_position(evs[0][0], tgt, L, leg_of, price) if evs else None
                lp = self._cycle_position(evs[-1][0], tgt, L, leg_of, price) if evs else None
                out.append(TransitionBridge(
                    transition_date=dates[x], from_mode=a.mode, to_mode=b.mode, direction=direction, scale=sc,
                    action_phase=act["phase"], action_progress=act["progress"],
                    action_bars_vs_confirm=act["bars_vs_confirm"], action_value_logpp=act["value_logpp"],
                    n_events_in_cycle=len(evs),
                    first_event=f"{evs[0][1]}@{dates[evs[0][0]]}" if evs else "",
                    first_event_phase=fp["phase"] if fp else "",
                    first_event_progress=fp["progress"] if fp else float("nan"),
                    bars_first_event_to_action=x - evs[0][0] if evs else -1,
                    first_event_value_logpp=fp["value_logpp"] if fp else float("nan"),
                    last_event=f"{evs[-1][1]}@{dates[evs[-1][0]]}" if evs else "",
                    last_event_phase=lp["phase"] if lp else "",
                    bars_last_event_to_action=x - evs[-1][0] if evs else -1,
                    last_event_value_logpp=lp["value_logpp"] if lp else float("nan")))
        return out
