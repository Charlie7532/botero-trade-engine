import pandas as pd
import numpy as np
from scipy.stats import rankdata
import logging

logger = logging.getLogger(__name__)


class QuantFeatureEngineer:
    """
    Motor Institucional de Features Estacionarios para LSTM.

    Produce exclusivamente features que satisfacen:
    1. Estacionariedad (ADF p < 0.05) — No explotan con el tiempo.
    2. Normalización local (Z-Scores rolling) — Media ~0, Std ~1.
    3. Memoria preservada (Diferenciación Fraccional) — Retiene soportes/resistencias.

    Familias de features:
    A. Diferenciación Fraccional (Memoria + Estacionariedad)
    B. Microestructura Normalizada (VWAP, Amihud, Volume Imbalance)
    C. Estructura Temporal (Multi-horizon returns, Volatility Ratios)
    D. Contexto Cross-Sectional (Relative Strength, Sector Rank)
    E. Corriente de Volumen (Relative Volume, Aceleración, Cumulative Delta)
    F. Contexto Macro (VIX, Bonds/Equity Ratio)
    """

    def __init__(self, data: pd.DataFrame, timeframe_minutes: int):
        self.df = data.copy()
        self.tf_mins = timeframe_minutes

        # Estandarizar nombre de columna de volumen
        if 'Volume' in self.df.columns and 'volume' not in self.df.columns:
            self.df.rename(columns={'Volume': 'volume'}, inplace=True)

    # ================================================================
    # FAMILY A: Fractional Differencing (López de Prado, Ch. 5)
    # ================================================================

    @staticmethod
    def _get_weights_ffd(d: float, threshold: float = 1e-5, max_width: int = 500) -> np.ndarray:
        """
        Computa los pesos para Fixed-Width Window Fractional Differentiation.
        Los pesos decaen geométricamente; truncamos cuando caen debajo del threshold
        o when max_width is reached (critical for daily data with limited bars).
        """
        weights = [1.0]
        k = 1
        while True:
            w = -weights[-1] * (d - k + 1) / k
            if abs(w) < threshold or k >= max_width:
                break
            weights.append(w)
            k += 1
        return np.array(weights[::-1]).reshape(-1, 1)

    def _fracdiff(self, series: pd.Series, d: float = 0.4) -> pd.Series:
        """
        Aplica diferenciación fraccional de orden d a una serie.
        d=0: Serie original (con memoria completa, no estacionaria).
        d=1: Primera diferencia (estacionaria, sin memoria).
        d=0.3-0.5: Punto óptimo — estacionaria Y con memoria.
        """
        weights = self._get_weights_ffd(d)
        width = len(weights)
        result = pd.Series(index=series.index, dtype=float)

        values = series.values
        for i in range(width - 1, len(values)):
            window = values[i - width + 1: i + 1]
            result.iloc[i] = np.dot(weights.T, window.reshape(-1, 1)).item()

        return result

    def extract_fractional_features(self, d_price: float = 0.4, d_volume: float = 0.6) -> None:
        """
        Familia A: Features con diferenciación fraccional.
        El parámetro d se calibra para cada serie buscando el mínimo d
        que produzca estacionariedad (ADF p < 0.05).

        d_price: Orden fraccional para precio (típicamente 0.3-0.5).
        d_volume: Orden fraccional para volumen (típicamente 0.5-0.7, más ruidoso).
        """
        logger.info(f"Calculando features fraccionales (d_price={d_price}, d_vol={d_volume})...")

        # Trabajamos con log(precio) para estabilizar la varianza
        log_close = np.log(self.df['close'].clip(lower=1e-8))
        log_volume = np.log(self.df['volume'].clip(lower=1.0))

        self.df['FD_LogClose'] = self._fracdiff(log_close, d=d_price)
        self.df['FD_LogVolume'] = self._fracdiff(log_volume, d=d_volume)

    # ================================================================
    # FAMILY B: Normalized Microstructure
    # ================================================================

    def extract_microstructure_features(self, vwap_window: int = 20) -> None:
        """
        Familia B: Features de microestructura normalizados por Z-Score rolling.
        Todos producen distribuciones con media ~0 y std ~1.
        """
        logger.info("Calculando features de microestructura normalizada...")

        df = self.df

        # --- B1: VWAP Z-Score (Distancia institucional al precio justo) ---
        typical_price = (df['high'] + df['low'] + df['close']) / 3.0
        cum_vp = (typical_price * df['volume']).rolling(vwap_window).sum()
        cum_vol = df['volume'].rolling(vwap_window).sum()
        vwap = cum_vp / cum_vol.clip(lower=1.0)

        vwap_diff = df['close'] - vwap
        vwap_std = vwap_diff.rolling(vwap_window).std().clip(lower=1e-8)
        df['MS_VWAP_ZScore'] = vwap_diff / vwap_std

        # --- B2: Volume Imbalance Z-Score (Presión compradora vs vendedora) ---
        range_t = (df['high'] - df['low']).clip(lower=1e-8)
        # Ratio de cierre dentro del rango: +1 = cerró en máximo, -1 = cerró en mínimo
        close_location = 2.0 * ((df['close'] - df['low']) / range_t) - 1.0
        # Ponderado por volumen = Order Flow Proxy
        order_flow = close_location * df['volume']
        of_mean = order_flow.rolling(vwap_window).mean()
        of_std = order_flow.rolling(vwap_window).std().clip(lower=1e-8)
        df['MS_OrderFlow_ZScore'] = (order_flow - of_mean) / of_std

        # --- B3: Amihud Illiquidity (Impacto de precio por unidad de volumen) ---
        log_returns = np.log(df['close'] / df['close'].shift(1).clip(lower=1e-8))
        amihud_raw = log_returns.abs() / df['volume'].clip(lower=1.0)
        # Normalizar por rolling Z-Score (Amihud nominal cambia con los años)
        amihud_mean = amihud_raw.rolling(50).mean()
        amihud_std = amihud_raw.rolling(50).std().clip(lower=1e-12)
        df['MS_Amihud_ZScore'] = (amihud_raw - amihud_mean) / amihud_std

        # --- B4: Spread Proxy (Estimación del bid-ask spread) ---
        spread_raw = range_t / df['close']
        spread_mean = spread_raw.rolling(vwap_window).mean()
        spread_std = spread_raw.rolling(vwap_window).std().clip(lower=1e-8)
        df['MS_Spread_ZScore'] = (spread_raw - spread_mean) / spread_std

    # ================================================================
    # FAMILY C: Temporal Structure
    # ================================================================

    def extract_temporal_features(self) -> None:
        """
        Familia C: Retornos multi-horizonte y ratios de volatilidad.
        La LSTM descubrirá sus propias "medias móviles" a partir de estos datos crudos.
        No le inyectamos MA/EMA/RSI humanos.
        """
        logger.info("Calculando features de estructura temporal...")

        df = self.df
        log_close = np.log(df['close'].clip(lower=1e-8))

        # --- C1: Multi-Horizon Log Returns ---
        for horizon in [1, 5, 15, 50]:
            df[f'TS_Return_{horizon}'] = log_close.diff(horizon)

        # --- C2: Realized Volatility (Dos escalas) ---
        returns_1 = log_close.diff(1)
        df['TS_RealVol_Fast'] = returns_1.rolling(14).std()
        df['TS_RealVol_Slow'] = returns_1.rolling(50).std()

        # --- C3: Volatility Ratio (Compresión vs Expansión) ---
        # Ratio < 1 = Vol comprimida (Squeeze inminente)
        # Ratio > 1 = Vol expandida (Movimiento en curso)
        df['TS_VolRatio'] = (
            df['TS_RealVol_Fast'] / df['TS_RealVol_Slow'].clip(lower=1e-8)
        )

        # --- C4: ATR Normalizado (Para la Triple Barrera downstream) ---
        high_low = df['high'] - df['low']
        high_prevclose = (df['high'] - df['close'].shift(1)).abs()
        low_prevclose = (df['low'] - df['close'].shift(1)).abs()
        true_range = pd.concat([high_low, high_prevclose, low_prevclose], axis=1).max(axis=1)
        df['TS_ATR_14'] = true_range.rolling(14).mean()
        # ATR como % del precio (normalizado, comparable entre activos)
        df['TS_ATR_Pct'] = df['TS_ATR_14'] / df['close']

    # ================================================================
    # FAMILY D: Cross-Sectional Context
    # ================================================================

    def extract_cross_sectional_features(
        self, benchmark_df: pd.DataFrame = None, z_length: int = 60
    ) -> None:
        """
        Familia D: Fuerza relativa contra el benchmark (SPX/SPY).
        Solo se ejecuta si se proporciona un DataFrame de benchmark.
        """
        if benchmark_df is None:
            logger.info("Sin benchmark proporcionado. Saltando features cross-sectional.")
            return

        logger.info("Calculando features cross-sectional vs benchmark...")

        # Alinear benchmark al índice del activo
        aligned_bench = benchmark_df['close'].reindex(self.df.index, method='ffill')

        # Ratio relativo
        ratio = self.df['close'] / aligned_bench.clip(lower=1e-8)
        ratio_mean = ratio.rolling(z_length).mean()
        ratio_std = ratio.rolling(z_length).std().clip(lower=1e-8)

        # Z-Score de fuerza relativa
        self.df['CS_RelStrength_ZScore'] = (ratio - ratio_mean) / ratio_std

        # Momentum relativo (retorno del ratio a 20 períodos)
        self.df['CS_RelMomentum'] = np.log(ratio / ratio.shift(20).clip(lower=1e-8))

        # Rolling Beta to benchmark (sensitivity to market moves)
        ticker_ret = self.df['close'].pct_change()
        bench_ret = aligned_bench.pct_change()
        cov = ticker_ret.rolling(z_length).cov(bench_ret)
        var = bench_ret.rolling(z_length).var().clip(lower=1e-12)
        self.df['CS_Beta'] = cov / var

    # ================================================================
    # FAMILY E: Volume Flow (Corriente del Volumen)
    # ================================================================

    def extract_volume_flow_features(self, lookback: int = 20) -> None:
        """
        Familia E: No solo cuánto volumen hay, sino su CORRIENTE.
        Un spike de volumen en caída ≠ spike de volumen en rebote.
        La corriente acumulada cuenta la historia que un punto no puede.
        """
        logger.info("Calculando features de corriente de volumen...")

        df = self.df

        # --- E1: Relative Volume (vol actual / promedio de 20 barras) ---
        # RelVol > 2 = Institucionales activos. RelVol < 0.5 = mercado muerto.
        avg_vol = df['volume'].rolling(lookback).mean().clip(lower=1.0)
        rel_vol = df['volume'] / avg_vol
        # Z-Score para estacionariedad
        rv_mean = rel_vol.rolling(50).mean()
        rv_std = rel_vol.rolling(50).std().clip(lower=1e-8)
        df['VF_RelVolume_ZScore'] = (rel_vol - rv_mean) / rv_std

        # --- E2: Volume Acceleration (cambio de ritmo) ---
        # Detecta cuando el volumen está ACELERANDO (entrada de institucionales)
        # vs DESACELERANDO (agotamiento del movimiento)
        vol_ma_fast = df['volume'].rolling(5).mean()
        vol_ma_slow = df['volume'].rolling(20).mean()
        vol_accel = (vol_ma_fast / vol_ma_slow.clip(lower=1.0)) - 1.0
        va_mean = vol_accel.rolling(50).mean()
        va_std = vol_accel.rolling(50).std().clip(lower=1e-8)
        df['VF_VolAccel_ZScore'] = (vol_accel - va_mean) / va_std

        # --- E3: Cumulative Delta (corriente acumulada de Order Flow) ---
        # El Order Flow puntual dice quién ganó HOY.
        # El Cumulative Delta dice quién está ganando la BATALLA.
        range_t = (df['high'] - df['low']).clip(lower=1e-8)
        close_location = 2.0 * ((df['close'] - df['low']) / range_t) - 1.0
        order_flow = close_location * df['volume']
        cum_delta = order_flow.rolling(lookback).sum()
        cd_mean = cum_delta.rolling(50).mean()
        cd_std = cum_delta.rolling(50).std().clip(lower=1e-8)
        df['VF_CumDelta_ZScore'] = (cum_delta - cd_mean) / cd_std

        # --- E4: Volume-Price Divergence ---
        # Precio sube con volumen decreciente = divergencia bajista
        # Precio baja con volumen decreciente = agotamiento de venta
        price_direction = np.sign(df['close'].diff(5))
        vol_direction = np.sign(df['volume'].diff(5))
        divergence = price_direction * vol_direction  # -1 = divergencia
        df['VF_VolPriceDivergence'] = divergence.rolling(10).mean()

    # ================================================================
    # FAMILY G: Organic Volume Decomposition & Sector Rotation
    # ================================================================

    def extract_organic_volume_features(
        self,
        spy_df: pd.DataFrame = None,
        sector_etf_df: pd.DataFrame = None,
        lookback: int = 60,
    ) -> None:
        """
        Familia G: Descompone el volumen observado en componente pasivo (índice)
        y orgánico (decisiones genuinas sobre la empresa).

        Uses MAD-trimmed OLS (vectorized) for speed:
        1. Compute rolling OLS beta via cov/var.
        2. Identify outlier days (volume residual > 3 MAD) — these are earnings/M&A.
        3. Trim outliers and recompute clean beta.
        4. Organic ratio = (actual - predicted_from_index) / actual.

        This runs in <1 sec per ticker vs 3+ min for per-bar RANSAC.

        Args:
            spy_df: SPY OHLCV DataFrame (for broad market beta).
            sector_etf_df: Sector ETF OHLCV DataFrame (for sector beta).
            lookback: Rolling window for beta estimation.
        """
        if spy_df is None:
            logger.info("Sin datos SPY. Saltando features de volumen orgánico.")
            return

        logger.info("Calculando features de volumen orgánico (MAD-trimmed OLS)...")
        df = self.df
        vol = df['volume'].astype(float)

        # Align SPY volume to ticker index
        spy_vol = spy_df['volume'].astype(float).reindex(df.index, method='ffill')

        # --- G1: Index Beta (MAD-trimmed rolling OLS) ---
        # Rolling covariance / variance = rolling beta (vectorized, instant)
        raw_beta = vol.rolling(lookback).cov(spy_vol) / spy_vol.rolling(lookback).var().clip(lower=1e-8)

        # Rolling intercept
        raw_alpha = vol.rolling(lookback).mean() - raw_beta * spy_vol.rolling(lookback).mean()

        # Predicted and residual
        predicted = raw_alpha + raw_beta * spy_vol
        residual = vol - predicted

        # MAD-based outlier detection (earnings/M&A days)
        rolling_mad = residual.rolling(lookback).apply(
            lambda x: np.median(np.abs(x - np.median(x))), raw=True
        )
        rolling_median = residual.rolling(lookback).median()
        is_outlier = (residual - rolling_median).abs() > 3.0 * rolling_mad.clip(lower=1.0)

        # Clean beta: recompute excluding outlier days
        vol_clean = vol.copy()
        spy_clean = spy_vol.copy()
        vol_clean[is_outlier] = np.nan
        spy_clean[is_outlier] = np.nan
        clean_beta = vol_clean.rolling(lookback, min_periods=lookback // 2).cov(
            spy_clean
        ) / spy_clean.rolling(lookback, min_periods=lookback // 2).var().clip(lower=1e-8)
        # Fill gaps with raw beta
        clean_beta = clean_beta.fillna(raw_beta)

        # Organic ratio
        clean_alpha = vol.rolling(lookback).mean() - clean_beta * spy_vol.rolling(lookback).mean()
        clean_predicted = clean_alpha + clean_beta * spy_vol
        organic = (vol - clean_predicted).clip(lower=0)
        organic_ratio = organic / vol.clip(lower=1.0)

        # Z-Score the beta for stationarity (Kalman proxy)
        beta_mean = clean_beta.rolling(lookback).mean()
        beta_std = clean_beta.rolling(lookback).std().clip(lower=1e-8)
        df['OV_IndexBeta_ZScore'] = (clean_beta - beta_mean) / beta_std
        df['OV_OrganicRatio'] = organic_ratio

        # --- G2: Sector Beta (rolling correlation as fast proxy) ---
        if sector_etf_df is not None:
            sector_vol = sector_etf_df['volume'].astype(float).reindex(df.index, method='ffill')
            sector_corr = vol.rolling(lookback).corr(sector_vol)
            sc_mean = sector_corr.rolling(lookback).mean()
            sc_std = sector_corr.rolling(lookback).std().clip(lower=1e-8)
            df['OV_SectorBeta_ZScore'] = (sector_corr - sc_mean) / sc_std

    # ================================================================
    # FAMILY H: Calendar Mechanical Forces
    # ================================================================

    def extract_calendar_features(self) -> None:
        """
        Familia H: Fuerzas determinísticas del calendario que inyectan
        volumen y distorsión de precio de forma predecible.

        - OPEX (tercer viernes de cada mes): market makers deshacen hedges.
        - Month-end: fondos mutuos rebalancean.
        - Quarter-end: window dressing por gestores.
        """
        logger.info("Calculando features de calendario mecánico...")
        df = self.df
        idx = df.index

        # --- H1: Days to OPEX (Options Expiration) ---
        # Third Friday of each month
        def days_to_opex(dt):
            """Days until next third Friday (OPEX)."""
            import calendar
            year, month = dt.year, dt.month
            # Find third Friday of current month
            c = calendar.monthcalendar(year, month)
            # Third Friday: find all Fridays, take the 3rd
            fridays = [week[calendar.FRIDAY] for week in c if week[calendar.FRIDAY] != 0]
            third_friday = fridays[2] if len(fridays) >= 3 else fridays[-1]
            from datetime import date
            opex = date(year, month, third_friday)
            if dt.date() > opex:
                # Move to next month
                if month == 12:
                    year, month = year + 1, 1
                else:
                    month += 1
                c = calendar.monthcalendar(year, month)
                fridays = [week[calendar.FRIDAY] for week in c if week[calendar.FRIDAY] != 0]
                third_friday = fridays[2] if len(fridays) >= 3 else fridays[-1]
                opex = date(year, month, third_friday)
            return (opex - dt.date()).days

        df['CAL_DaysToOPEX'] = pd.Series(
            [days_to_opex(dt) for dt in idx], index=idx, dtype=float
        )

        # --- H2: Month-End (last 3 business days) ---
        days_in_month = idx.to_series().dt.days_in_month
        day_of_month = idx.to_series().dt.day
        df['CAL_MonthEnd'] = ((days_in_month - day_of_month) <= 3).astype(float)

        # --- H3: Quarter-End (last 5 business days of Q) ---
        is_quarter_end_month = idx.month.isin([3, 6, 9, 12])
        df['CAL_QuarterEnd'] = (
            is_quarter_end_month & ((days_in_month - day_of_month) <= 5)
        ).astype(float)

    # ================================================================
    # FAMILY I: Intermarket Rotation
    # ================================================================

    def extract_intermarket_features(
        self,
        spy_df: pd.DataFrame = None,
        sector_etf_df: pd.DataFrame = None,
        bond_df: pd.DataFrame = None,
        hyg_df: pd.DataFrame = None,
        lookback: int = 20,
    ) -> None:
        """
        Familia I: Señales de rotación de capital entre clases de activos
        y entre sectores.

        Detección de rotación dual (precio + volumen):
        - Si sector_rs sube Y sector_vol_rs sube → Rotación REAL hacia el sector.
        - Si sector_rs sube PERO sector_vol_rs baja → Rally falso sin convicción.

        Args:
            spy_df: SPY OHLCV for broad market benchmark.
            sector_etf_df: Sector ETF OHLCV for sector-specific rotation.
            bond_df: Bond ETF (TLT/IEF) OHLCV for yield delta.
            hyg_df: HYG OHLCV for credit spread proxy.
        """
        if spy_df is None:
            logger.info("Sin datos SPY. Saltando features intermarket.")
            return

        logger.info("Calculando features de rotación inter-mercado...")
        df = self.df
        spy_close = spy_df['close'].reindex(df.index, method='ffill')

        # --- I1: Sector Price Relative Strength ---
        if sector_etf_df is not None:
            sector_close = sector_etf_df['close'].reindex(df.index, method='ffill')
            # Ratio sector/SPY → RS > 1 means sector outperforming
            rs_ratio = sector_close / spy_close.clip(lower=1e-8)
            rs_ret = np.log(rs_ratio / rs_ratio.shift(lookback).clip(lower=1e-8))
            rs_mean = rs_ret.rolling(50).mean()
            rs_std = rs_ret.rolling(50).std().clip(lower=1e-8)
            df['IM_SectorRS_ZScore'] = (rs_ret - rs_mean) / rs_std

            # --- I2: Sector Volume Relative Strength ---
            spy_vol = spy_df['volume'].astype(float).reindex(df.index, method='ffill')
            sector_vol = sector_etf_df['volume'].astype(float).reindex(df.index, method='ffill')
            vol_ratio = sector_vol / spy_vol.clip(lower=1.0)
            vr_ret = np.log(vol_ratio / vol_ratio.shift(lookback).clip(lower=1e-8))
            vr_mean = vr_ret.rolling(50).mean()
            vr_std = vr_ret.rolling(50).std().clip(lower=1e-8)
            df['IM_SectorVolRS_ZScore'] = (vr_ret - vr_mean) / vr_std

        # --- I3: Yield Delta (Bond sensitivity) ---
        if bond_df is not None:
            bond_close = bond_df['close'].reindex(df.index, method='ffill')
            bond_ret = np.log(bond_close / bond_close.shift(5).clip(lower=1e-8))
            br_mean = bond_ret.rolling(50).mean()
            br_std = bond_ret.rolling(50).std().clip(lower=1e-8)
            df['IM_YieldDelta_ZScore'] = (bond_ret - br_mean) / br_std

        # --- I4: Credit Spread Proxy (HYG vs IEF risk appetite) ---
        if hyg_df is not None and bond_df is not None:
            hyg_close = hyg_df['close'].reindex(df.index, method='ffill')
            bond_close = bond_df['close'].reindex(df.index, method='ffill')
            credit_ratio = hyg_close / bond_close.clip(lower=1e-8)
            cr_ret = np.log(credit_ratio / credit_ratio.shift(5).clip(lower=1e-8))
            cr_mean = cr_ret.rolling(50).mean()
            cr_std = cr_ret.rolling(50).std().clip(lower=1e-8)
            df['IM_CreditSpread_ZScore'] = (cr_ret - cr_mean) / cr_std

    # ================================================================
    # FAMILY F: Macro Context (VIX + Cross-Asset)
    # ================================================================

    def extract_macro_context_features(
        self, vix_df: pd.DataFrame = None, bond_df: pd.DataFrame = None,
    ) -> None:
        """
        Familia F: Contexto macro que la LSTM necesita para distinguir
        un crash por aranceles (reversión inminente) de un colapso
        fundamental (sin recovery).

        Sin estos features, la LSTM es una película muda.
        Con ellos, tiene subtitulos y narrador.
        """
        if vix_df is None and bond_df is None:
            logger.info("Sin datos macro. Saltando features de contexto.")
            return

        logger.info("Calculando features de contexto macro...")

        if vix_df is not None:
            # Alinear VIX al índice del activo
            vix_close = vix_df['close'].reindex(self.df.index, method='ffill')

            # --- F1: VIX Level Z-Score ---
            # VIX alto = miedo. Pero ¿qué tan alto vs su historia reciente?
            vix_mean = vix_close.rolling(60).mean()
            vix_std = vix_close.rolling(60).std().clip(lower=1e-4)
            self.df['MC_VIX_ZScore'] = (vix_close - vix_mean) / vix_std

            # --- F2: VIX Velocity (velocidad de cambio del miedo) ---
            # VIX subiendo rápido = pánico. VIX bajando rápido = alivio.
            vix_ret = np.log(vix_close / vix_close.shift(1).clip(lower=0.1))
            vr_mean = vix_ret.rolling(20).mean()
            vr_std = vix_ret.rolling(20).std().clip(lower=1e-8)
            self.df['MC_VIX_Velocity_ZScore'] = (vix_ret - vr_mean) / vr_std

            # --- F3: VIX Term Structure Proxy ---
            # VIX vs su SMA50: encima = backwardation (pánico)
            # debajo = contango (complacencia)
            vix_sma50 = vix_close.rolling(50).mean()
            self.df['MC_VIX_TermStructure'] = (
                (vix_close - vix_sma50) / vix_sma50.clip(lower=0.1)
            )

        if bond_df is not None:
            # Alinear bonos al índice del activo
            bond_close = bond_df['close'].reindex(self.df.index, method='ffill')

            # --- F4: Equity/Bond Ratio (Risk-On vs Risk-Off) ---
            # Ratio sube = risk-on. Ratio baja = flight-to-safety.
            ratio = self.df['close'] / bond_close.clip(lower=1e-8)
            ratio_ret = np.log(ratio / ratio.shift(5).clip(lower=1e-8))
            rr_mean = ratio_ret.rolling(50).mean()
            rr_std = ratio_ret.rolling(50).std().clip(lower=1e-8)
            self.df['MC_EquityBond_ZScore'] = (ratio_ret - rr_mean) / rr_std

    # ================================================================
    # FAMILY G: Regime Context (Market Cycle Conditioning)
    # ================================================================

    def extract_regime_features(self) -> None:
        """
        Familia G: Régimen de mercado como features estacionarios.

        Computados EXCLUSIVAMENTE de la data OHLCV del activo — no requiere
        datos externos, cumple Clean Architecture.

        Features:
            RG_WinsteinProxy:   Weinstein Stage encoding via price vs MA150 + slope.
            RG_TrendStrength:   Distance to SMA50 normalized by ATR (clipped [-5, 5]).
            RG_AccDistRatio_Z:  Up-volume / Down-volume ratio z-score (accumulation vs distribution).
            RG_MomentumRegime:  Binary — SMA20 > SMA50 = bullish (1.0), else bearish (0.0).
        """
        logger.info("Calculando features de régimen de mercado (Familia G)...")

        df = self.df

        # G1: Weinstein Stage Proxy (price vs MA150 + MA slope)
        ma_150 = df['close'].rolling(150, min_periods=50).mean()
        ma_slope = df['close'].rolling(20, min_periods=10).mean() - df['close'].rolling(40, min_periods=20).mean()
        # Encoding: Advancing=0.75, Basing=0.25, Topping=-0.25, Declining=-0.75
        stage = pd.Series(0.25, index=df.index)  # Default: Basing
        stage[(df['close'] > ma_150) & (ma_slope > 0)] = 0.75    # Advancing
        stage[(df['close'] > ma_150) & (ma_slope <= 0)] = -0.25   # Topping
        stage[(df['close'] < ma_150) & (ma_slope < 0)] = -0.75    # Declining
        df['RG_WinsteinProxy'] = stage

        # G2: Trend Strength (distance to SMA50 normalized by ATR)
        sma50 = df['close'].rolling(50, min_periods=20).mean()
        atr_col = df.get('TS_ATR_14')
        if atr_col is None:
            hl_range = df['high'] - df['low']
            atr_col = hl_range.rolling(14, min_periods=5).mean()
        df['RG_TrendStrength'] = ((df['close'] - sma50) / atr_col.clip(lower=1e-8)).clip(-5, 5)

        # G3: Accumulation vs Distribution (up-volume / down-volume z-score)
        price_up = (df['close'] > df['close'].shift(1)).astype(float)
        up_vol = (df['volume'] * price_up).rolling(20, min_periods=10).sum()
        down_vol = (df['volume'] * (1.0 - price_up)).rolling(20, min_periods=10).sum().clip(lower=1.0)
        acc_dist_ratio = up_vol / down_vol
        adr_mean = acc_dist_ratio.rolling(60, min_periods=20).mean()
        adr_std = acc_dist_ratio.rolling(60, min_periods=20).std().clip(lower=1e-8)
        df['RG_AccDistRatio_Z'] = (acc_dist_ratio - adr_mean) / adr_std

        # G4: Momentum Regime (SMA20 > SMA50 = BULL)
        sma20 = df['close'].rolling(20, min_periods=10).mean()
        df['RG_MomentumRegime'] = (sma20 > sma50).astype(float)

    # ================================================================
    # PIPELINE MASTER
    # ================================================================

    def get_feature_columns(self) -> list:
        """Retorna la lista de columnas que son features válidos para ML."""
        prefixes = ('FD_', 'MS_', 'TS_', 'CS_', 'VF_', 'MC_', 'OV_', 'CAL_', 'IM_', 'RG_')
        return [c for c in self.df.columns if c.startswith(prefixes)]

    def process_all_features(
        self,
        benchmark_df: pd.DataFrame = None,
        vix_df: pd.DataFrame = None,
        bond_df: pd.DataFrame = None,
        spy_df: pd.DataFrame = None,
        sector_etf_df: pd.DataFrame = None,
        hyg_df: pd.DataFrame = None,
        d_price: float = 0.4,
        d_volume: float = 0.6,
    ) -> pd.DataFrame:
        """
        Pipeline completo: De datos OHLCV crudos a matriz de ML estacionaria.

        Orden de ejecución:
        1. Fractional Differencing (preserva memoria, fuerza estacionariedad)
        2. Microstructure (VWAP, Order Flow, Amihud, Spread)
        3. Temporal (Returns, Volatility, ATR)
        4. Cross-Sectional (Relative Strength vs Benchmark)
        5. Volume Flow (Relative Vol, Aceleración, Cumulative Delta)
        6. Organic Volume Decomposition (Kalman+RANSAC vs SPY/Sector)
        7. Calendar Mechanical Forces (OPEX, Month-End, Quarter-End)
        8. Intermarket Rotation (Sector RS, Yield Delta, Credit Spread)
        9. Macro Context (VIX, Bonds/Equity Ratio)
        10. Limpieza de NaNs iniciales por rolling windows

        Returns:
            DataFrame con OHLCV original + features nombrados con prefijo de familia.
        """
        logger.info(
            f"Iniciando pipeline de features institucionales "
            f"({len(self.df)} filas, TF={self.tf_mins}m)"
        )

        self.extract_fractional_features(d_price=d_price, d_volume=d_volume)
        self.extract_microstructure_features()
        self.extract_temporal_features()
        self.extract_cross_sectional_features(benchmark_df=benchmark_df)
        self.extract_volume_flow_features()
        self.extract_organic_volume_features(spy_df=spy_df, sector_etf_df=sector_etf_df)
        self.extract_calendar_features()
        self.extract_intermarket_features(
            spy_df=spy_df, sector_etf_df=sector_etf_df,
            bond_df=bond_df, hyg_df=hyg_df,
        )
        self.extract_macro_context_features(vix_df=vix_df, bond_df=bond_df)
        self.extract_regime_features()

        # Reemplazar infinitos por NaN antes de dropear
        self.df.replace([np.inf, -np.inf], np.nan, inplace=True)
        self.df.dropna(inplace=True)

        feature_cols = self.get_feature_columns()
        logger.info(
            f"Pipeline completo. {len(feature_cols)} features generados, "
            f"{len(self.df)} filas válidas."
        )

        return self.df
