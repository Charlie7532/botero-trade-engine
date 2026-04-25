import logging
import numpy as np
import pandas as pd
from typing import Optional
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


class SectorFlowEngine:
    """
    Motor de Flujo de Capital Sectorial.
    
    Responde la pregunta: ¿La acción está nadando con la marea 
    o contra la corriente?
    
    Niveles de análisis:
    1. MAREA (Mercado total): S5TH/S5TW, VIX → ¿El océano sube o baja?
    2. CORRIENTE (Sector): Breadth sectorial, momentum, RelVol → ¿El sector lidera?
    3. OLA (Acción): Volumen inusual, cambio de precio → ¿La acción tiene catalizador?
    
    Regla de oro del Value Investor:
    - Comprar acciones fuertes en sectores fuertes en mercados débiles (capitulación)
    - Comprar acciones castigadas en sectores fuertes (sobrerreacción)
    - NUNCA comprar acciones débiles en sectores débiles (knife catching)
    """

    SECTORS = [
        'Technology', 'Healthcare', 'Financial', 'Consumer Cyclical',
        'Consumer Defensive', 'Industrials', 'Energy', 'Utilities',
        'Real Estate', 'Basic Materials', 'Communication Services',
    ]

    # Mapping ETF → Sector para datos históricos
    SECTOR_ETFS = {
        'Technology': 'XLK',
        'Healthcare': 'XLV',
        'Financial': 'XLF',
        'Consumer Cyclical': 'XLY',
        'Consumer Defensive': 'XLP',
        'Industrials': 'XLI',
        'Energy': 'XLE',
        'Utilities': 'XLU',
        'Real Estate': 'XLRE',
        'Basic Materials': 'XLB',
        'Communication Services': 'XLC',
    }

    # Mercado general (Baseline)
    MARKET_ETFS = {
        'S&P 500 (Market)': 'SPY',
    }

    # ETFs geográficos internacionales — para detectar rotación global
    INTERNATIONAL_ETFS = {
        'World_Developed': 'EFA',    # iShares MSCI EAFE (Europa, Asia, Oceanía)
        'Emerging_Markets': 'EEM',   # iShares MSCI Emerging Markets
        'China':           'MCHI',   # iShares MSCI China
        'China_LargeCap':  'FXI',    # iShares China Large-Cap
        'Japan':           'EWJ',    # iShares MSCI Japan
        'Europe':          'VGK',    # Vanguard FTSE Europe
        'Brazil':          'EWZ',    # iShares MSCI Brazil
        'India':           'INDA',   # iShares MSCI India
        'South_Korea':     'EWY',    # iShares MSCI South Korea (Proxy Semiconductores)
        'Asia_Pacific':    'EPP',    # iShares MSCI Pacific ex Japan
    }

    # ETFs de Commodities — para rotación hacia materias primas / inflación
    COMMODITY_ETFS = {
        'Gold':        'GLD',   # SPDR Gold
        'Oil':         'USO',   # United States Oil Fund
        'Agriculture': 'DBA',   # Invesco DB Agriculture Fund
    }

    def __init__(self):
        # Primary: Finviz MCP (Elite subscription)
        self._finviz_mcp = None
        # Fallback: finvizfinance scraper
        self._finviz_scraper_available = False
        try:
            from finvizfinance.screener.overview import Overview
            from finvizfinance.group.performance import Performance
            self._finviz_scraper_available = True
        except ImportError:
            logger.info("finvizfinance scraper no disponible — usar Finviz MCP")

    def _get_finviz_mcp(self):
        """Lazy init del Finviz MCP adapter."""
        if self._finviz_mcp is None:
            from backend.infrastructure.data_providers.finviz_intelligence import FinvizIntelligence
            self._finviz_mcp = FinvizIntelligence()
        return self._finviz_mcp

    # ================================================================
    # NIVEL 2: CORRIENTE SECTORIAL
    # ================================================================

    def get_sector_performance(
        self, mcp_response: dict = None
    ) -> pd.DataFrame:
        """
        Obtiene rendimiento de cada sector en múltiples horizontes.
        
        Data Priority:
            1. Finviz MCP: get_sector_performance (Elite) ← PRIMARY
            2. finvizfinance scraper (fallback)
        """
        # Primary: Finviz MCP
        if mcp_response is not None:
            try:
                fv = self._get_finviz_mcp()
                sectors = fv.parse_sector_performance(mcp_response)
                if sectors:
                    rows = [{
                        'Name': s.sector, 'Perf 1D': s.perf_1d, 'Perf 1W': s.perf_1w,
                        'Perf 1M': s.perf_1m, 'Perf 3M': s.perf_3m,
                        'Perf YTD': s.perf_ytd, 'Perf 1Y': s.perf_1y,
                        'Rel Volume': s.relative_volume, 'Momentum': s.momentum_score,
                    } for s in sectors]
                    df = pd.DataFrame(rows)
                    logger.info(f"Sector performance via MCP: {len(df)} sectores")
                    return df
            except Exception as e:
                logger.warning(f"Error MCP sector performance: {e}")

        # Fallback: finvizfinance scraper
        if not self._finviz_scraper_available:
            return pd.DataFrame()

        try:
            from finvizfinance.group.performance import Performance
            perf = Performance()
            df = perf.screener_view(group='Sector')
            if df is not None and not df.empty:
                logger.info(f"Sector performance (scraper fallback): {len(df)} sectores")
                return df
        except Exception as e:
            logger.error(f"Error sector performance scraper: {e}")

        return pd.DataFrame()

    def get_sector_breadth(
        self, mcp_overview_response: dict = None
    ) -> list[dict]:
        """
        Calcula breadth por sector: % de acciones sobre 50-DMA.
        
        Data Priority:
            1. Finviz MCP: get_market_overview + custom_screener ← PRIMARY
            2. finvizfinance screener queries (fallback, SLOW: 11 queries)
        """
        # Primary: Finviz MCP (uses get_moving_average_position)
        if mcp_overview_response is not None:
            try:
                fv = self._get_finviz_mcp()
                overview = fv.parse_market_overview(mcp_overview_response)
                if overview:
                    # Build breadth from overview data if available
                    results = []
                    advances = overview.get('advances', 0)
                    declines = overview.get('declines', 0)
                    total = advances + declines
                    if total > 0:
                        pct = (advances / total) * 100
                        health = 'strong' if pct >= 70 else 'moderate' if pct >= 50 else 'weak' if pct >= 30 else 'capitulation'
                        results.append({
                            'sector': 'S&P 500 (Overall)',
                            'etf': 'SPY',
                            'total_stocks': total,
                            'above_50dma': advances,
                            'below_50dma': declines,
                            'pct_above_50dma': round(pct, 1),
                            'health': health,
                            'trend': '↑' if pct >= 60 else '→' if pct >= 40 else '↓',
                        })
                    if results:
                        logger.info(f"Sector breadth via MCP: {len(results)} entries")
                        return results
            except Exception as e:
                logger.warning(f"Error MCP breadth: {e}")

        # Fallback: finvizfinance scraper
        if not self._finviz_scraper_available:
            return []

        from finvizfinance.screener.overview import Overview
        results = []

        for sector in self.SECTORS:
            try:
                # Total stocks en el sector
                fov_total = Overview()
                fov_total.set_filter(filters_dict={
                    'Index': 'S&P 500', 'Sector': sector,
                })
                df_total = fov_total.screener_view()
                total = len(df_total) if df_total is not None else 0

                if total == 0:
                    continue

                # Stocks bajo 50-DMA
                fov_below = Overview()
                fov_below.set_filter(filters_dict={
                    'Index': 'S&P 500', 'Sector': sector,
                    '50-Day Simple Moving Average': 'Price below SMA50',
                })
                df_below = fov_below.screener_view()
                below = len(df_below) if df_below is not None else 0

                above = total - below
                pct = (above / total) * 100

                # Clasificar
                if pct >= 70:
                    health = "strong"
                    trend = "↑"
                elif pct >= 50:
                    health = "moderate"
                    trend = "→"
                elif pct >= 30:
                    health = "weak"
                    trend = "↓"
                else:
                    health = "capitulation"
                    trend = "⚠"

                results.append({
                    "sector": sector,
                    "etf": self.SECTOR_ETFS.get(sector, ""),
                    "total_stocks": total,
                    "above_50dma": above,
                    "below_50dma": below,
                    "pct_above_50dma": round(pct, 1),
                    "health": health,
                    "trend": trend,
                })

            except Exception as e:
                logger.warning(f"Error breadth {sector}: {e}")

        # Ordenar por salud descendente
        results.sort(key=lambda x: x["pct_above_50dma"], reverse=True)
        return results

    # ================================================================
    # NIVEL 3: OLAS INDIVIDUALES
    # ================================================================

    def get_movers(
        self, min_change_pct: str = "Up 3%",
        mcp_response: dict = None,
    ) -> list[dict]:
        """
        Obtiene las acciones con mayor movimiento hoy del S&P500.
        
        Data Priority:
            1. Finviz MCP: custom_screener / earnings_winners_screener ← PRIMARY
            2. finvizfinance screener (fallback)
        """
        # Primary: Finviz MCP
        if mcp_response is not None:
            try:
                fv = self._get_finviz_mcp()
                surges = fv.parse_volume_surge(mcp_response)
                return [
                    {
                        'ticker': s.ticker, 'price': s.price,
                        'change': s.change_pct, 'volume': s.volume,
                        'relative_volume': s.relative_volume,
                        'sector': '', 'company': '',
                    }
                    for s in surges
                ]
            except Exception as e:
                logger.warning(f"Error MCP movers: {e}")

        # Fallback: finvizfinance scraper
        if not self._finviz_scraper_available:
            return []

        try:
            from finvizfinance.screener.overview import Overview
            fov = Overview()
            fov.set_filter(filters_dict={
                'Index': 'S&P 500',
                'Change': min_change_pct,
            })
            df = fov.screener_view()
            if df is None or df.empty:
                return []

            return [
                {
                    'ticker': row.get('Ticker', ''),
                    'company': row.get('Company', ''),
                    'sector': row.get('Sector', ''),
                    'industry': row.get('Industry', ''),
                    'price': row.get('Price', 0),
                    'change': row.get('Change', 0),
                    'volume': row.get('Volume', 0),
                }
                for _, row in df.iterrows()
            ]
        except Exception as e:
            logger.error(f"Error movers scraper: {e}")
            return []

    def get_unusual_volume(
        self, min_rel_vol: str = "Over 2",
        mcp_response: dict = None,
    ) -> list[dict]:
        """
        Detecta acciones con volumen inusual (>2x promedio).
        
        Data Priority:
            1. Finviz MCP: volume_surge_screener / get_relative_volume_stocks ← PRIMARY
            2. finvizfinance screener (fallback)
        """
        # Primary: Finviz MCP
        if mcp_response is not None:
            try:
                fv = self._get_finviz_mcp()
                surges = fv.parse_volume_surge(mcp_response)
                results = []
                for s in surges:
                    action = 'accumulation' if s.change_pct > 0 else 'distribution'
                    results.append({
                        'ticker': s.ticker,
                        'price': s.price,
                        'change': s.change_pct,
                        'volume': s.volume,
                        'relative_volume': s.relative_volume,
                        'institutional_action': action,
                        'company': '', 'sector': '',
                    })
                if results:
                    logger.info(f"Unusual volume via MCP: {len(results)} stocks")
                    return results
            except Exception as e:
                logger.warning(f"Error MCP unusual volume: {e}")

        # Fallback: finvizfinance scraper
        if not self._finviz_scraper_available:
            return []

        try:
            from finvizfinance.screener.overview import Overview
            fov = Overview()
            fov.set_filter(filters_dict={
                'Index': 'S&P 500',
                'Relative Volume': min_rel_vol,
            })
            df = fov.screener_view()
            if df is None or df.empty:
                return []

            results = []
            for _, row in df.iterrows():
                change = row.get('Change', 0)
                if isinstance(change, str):
                    change = float(change.replace('%', '')) / 100
                action = 'accumulation' if change > 0 else 'distribution'
                results.append({
                    'ticker': row.get('Ticker', ''),
                    'company': row.get('Company', ''),
                    'sector': row.get('Sector', ''),
                    'price': row.get('Price', 0),
                    'change': change,
                    'volume': row.get('Volume', 0),
                    'institutional_action': action,
                })
            return results
        except Exception as e:
            logger.error(f"Error unusual volume scraper: {e}")
            return []

    # ================================================================
    # ANÁLISIS COMPUESTO: MAREA vs OLA
    # ================================================================

    def analyze_tide_vs_wave(
        self,
        ticker: str,
        ticker_sector: str,
        ticker_change: float,
        sector_breadth: list[dict],
    ) -> dict:
        """
        Determina si una acción está nadando con o contra la corriente.
        
        MAREA CON + OLA CON = Alta convicción LONG
        MAREA CON + OLA CONTRA = Sobrerreacción en sector fuerte (VALUE!)
        MAREA CONTRA + OLA CON = Stock aislado, no confiar (short squeeze?)
        MAREA CONTRA + OLA CONTRA = Knife catching, EVITAR
        
        Args:
            ticker: Símbolo de la acción
            ticker_sector: Sector al que pertenece
            ticker_change: Cambio % del día
            sector_breadth: Resultado de get_sector_breadth()
        """
        # Encontrar el sector
        sector_data = None
        for sb in sector_breadth:
            if sb["sector"] == ticker_sector:
                sector_data = sb
                break

        if sector_data is None:
            return {
                "ticker": ticker,
                "alignment": "unknown",
                "conviction": 0,
            }

        sector_pct = sector_data["pct_above_50dma"]
        sector_strong = sector_pct >= 50
        stock_up = ticker_change > 0

        if sector_strong and stock_up:
            alignment = "WITH_TIDE"
            conviction = min(100, sector_pct + abs(ticker_change) * 100)
            action = "STRONG_LONG"
            reason = f"Sector fuerte ({sector_pct:.0f}%) + stock subiendo"
        elif sector_strong and not stock_up:
            alignment = "AGAINST_WAVE"
            conviction = min(100, sector_pct)
            action = "VALUE_OPPORTUNITY"
            reason = (
                f"Sector fuerte ({sector_pct:.0f}%) pero stock bajando "
                f"({ticker_change*100:+.1f}%). Posible sobrerreacción."
            )
        elif not sector_strong and stock_up:
            alignment = "ISOLATED_WAVE"
            conviction = max(20, 50 - (50 - sector_pct))
            action = "CAUTION"
            reason = (
                f"Sector débil ({sector_pct:.0f}%) pero stock sube. "
                f"No confiar — puede ser short squeeze o dead cat bounce."
            )
        else:
            alignment = "AGAINST_TIDE"
            conviction = max(0, sector_pct - 10)
            action = "AVOID"
            reason = f"Sector débil ({sector_pct:.0f}%) + stock bajando. Knife catching."

        return {
            "ticker": ticker,
            "sector": ticker_sector,
            "sector_health_pct": sector_pct,
            "sector_health": sector_data["health"],
            "ticker_change": ticker_change,
            "alignment": alignment,
            "action": action,
            "conviction": round(conviction, 1),
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # ================================================================
    # PIPELINE: SECTOR ROTATION SNAPSHOT
    # ================================================================

    def get_full_rotation_snapshot(self) -> dict:
        """
        Captura completa del estado de rotación sectorial.
        Combina performance, breadth, movers, y volumen inusual.
        """
        logger.info("Generando snapshot de rotación sectorial...")

        snapshot = {
            "sector_breadth": self.get_sector_breadth(),
            "movers_up": self.get_movers("Up 3%"),
            "movers_down": self.get_movers("Down 3%"),
            "unusual_volume": self.get_unusual_volume("Over 2"),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Clasificar sectores
        strong = [s for s in snapshot["sector_breadth"] if s["health"] == "strong"]
        weak = [s for s in snapshot["sector_breadth"] if s["health"] in ("weak", "capitulation")]

        snapshot["strong_sectors"] = [s["sector"] for s in strong]
        snapshot["weak_sectors"] = [s["sector"] for s in weak]

        # Contar movers por sector
        sector_movers = {}
        for m in snapshot["movers_up"]:
            s = m["sector"]
            sector_movers[s] = sector_movers.get(s, {"up": 0, "down": 0})
            sector_movers[s]["up"] += 1
        for m in snapshot["movers_down"]:
            s = m["sector"]
            sector_movers[s] = sector_movers.get(s, {"up": 0, "down": 0})
            sector_movers[s]["down"] += 1
        snapshot["sector_movers_count"] = sector_movers

        logger.info(
            f"Rotación: {len(strong)} sectores fuertes, {len(weak)} débiles, "
            f"{len(snapshot['movers_up'])} movers ↑, {len(snapshot['movers_down'])} ↓"
        )

        return snapshot

    # ================================================================
    # HEATMAP GLOBAL: ETFs SECTORIALES + INTERNACIONALES
    # ================================================================

    def get_global_volume_heatmap(
        self,
        mcp_response: dict = None,
        include_dynamics: bool = True,
    ) -> pd.DataFrame:
        """
        Radar de Flujo Institucional Global.

        Consolida en un solo DataFrame los 19 ETFs (11 sectoriales + 8
        internacionales) con su Relative Volume, cambio de precio, y la
        señal de flujo inferida.

        De ser posible, enriquece con dinámica de volumen (velocidad y
        aceleración) usando el KalmanVolumeTracker — esto permite detectar
        la rotación ANTES de que el volumen explote, no después.

        Args:
            mcp_response: Respuesta de get_multiple_stocks_fundamentals para
                          los 19 ETFs. Si None, intenta construir un DataFrame
                          de fallback vía yfinance.
            include_dynamics: Si True, e intent el KalmanVolumeTracker está
                              disponible, añade columnas vel_rvol y accel_rvol.

        Returns:
            DataFrame con columnas:
              etf, label, universe, rel_vol, change_pct, flow_signal,
              wyckoff_state, vel_rvol, accel_rvol  (las dos últimas si disponibles)
        """
        # ── 1. Construir tabla base de todos los ETFs ────────────────
        all_etfs = {
            **{v: ('Market', k) for k, v in getattr(self, 'MARKET_ETFS', {}).items()},
            **{v: ('Domestic', k) for k, v in self.SECTOR_ETFS.items()},
            **{v: ('International', k) for k, v in getattr(self, 'INTERNATIONAL_ETFS', {}).items()},
            **{v: ('Commodity', k) for k, v in getattr(self, 'COMMODITY_ETFS', {}).items()},
        }

        rows = []

        if mcp_response is not None:
            # Parsear respuesta MCP de get_multiple_stocks_fundamentals
            items = mcp_response if isinstance(mcp_response, list) else \
                mcp_response.get('data', mcp_response.get('results', []))

            for item in items:
                ticker = str(item.get('ticker', item.get('Ticker', ''))).upper()
                if ticker not in all_etfs:
                    continue
                universe, label = all_etfs[ticker]
                rel_vol = self._safe_float(item.get('relative_volume', item.get('Relative Volume', 1.0)))
                change = self._safe_float(item.get('change', item.get('Change', 0.0)))
                rows.append({
                    'etf': ticker,
                    'label': label,
                    'universe': universe,
                    'rel_vol': rel_vol,
                    'change_pct': change,
                })
        else:
            # Fallback: yfinance para datos básicos (sin velocidad ni MCP)
            logger.info("Heatmap: usando yfinance como fallback (sin datos MCP)")
            try:
                import yfinance as yf
                tickers_list = list(all_etfs.keys())
                data = yf.download(
                    tickers_list, period='5d', interval='1d',
                    progress=False, auto_adjust=True,
                )
                if isinstance(data.columns, pd.MultiIndex):
                    close = data['Close']
                    volume = data['Volume']
                else:
                    close = data[['Close']]
                    volume = data[['Volume']]

                for ticker, (universe, label) in all_etfs.items():
                    try:
                        c = close[ticker].dropna()
                        v = volume[ticker].dropna()
                        if len(c) < 2:
                            continue
                        change = (c.iloc[-1] / c.iloc[-2] - 1) * 100
                        avg_vol = v.rolling(20, min_periods=5).mean().iloc[-1]
                        rel_vol = v.iloc[-1] / avg_vol if avg_vol > 0 else 1.0
                        rows.append({
                            'etf': ticker,
                            'label': label,
                            'universe': universe,
                            'rel_vol': round(float(rel_vol), 2),
                            'change_pct': round(float(change), 2),
                        })
                    except Exception:
                        continue
            except ImportError:
                logger.warning("yfinance no disponible para fallback del Heatmap")

        if not rows:
            logger.warning("Heatmap global: sin datos disponibles")
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # ── 2. Clasificar Flow Signal (posición estática) ─────────────
        df['flow_signal'] = df.apply(
            lambda r: self._classify_flow_signal(r['rel_vol'], r['change_pct']),
            axis=1,
        )

        # ── 3. Enriquecer con dinámica Kalman (velocidad + aceleración) ──
        if include_dynamics:
            try:
                from backend.infrastructure.data_providers.volume_dynamics import KalmanVolumeTracker
                tracker = KalmanVolumeTracker()
                velocities, accels, states = [], [], []
                for _, row in df.iterrows():
                    state = tracker.update(row['etf'], row['rel_vol'])
                    velocities.append(state['velocity'])
                    accels.append(state['acceleration'])
                    states.append(state['wyckoff_state'])
                df['vel_rvol'] = velocities
                df['accel_rvol'] = accels
                df['wyckoff_state'] = states
            except Exception as e:
                logger.debug(f"KalmanVolumeTracker no disponible: {e}")
                df['vel_rvol'] = 0.0
                df['accel_rvol'] = 0.0
                df['wyckoff_state'] = 'UNKNOWN'

        # ── 4. Ordenar: flujo más caliente primero ───────────────────
        # Priorizar acumulación temprana (vel alta + precio no explotado)
        sort_key = 'vel_rvol' if 'vel_rvol' in df.columns else 'rel_vol'
        df = df.sort_values(sort_key, ascending=False).reset_index(drop=True)

        logger.info(
            f"Heatmap global: {len(df)} ETFs | "
            f"Top flujo: {df.iloc[0]['etf']} ({df.iloc[0]['flow_signal']})"
            if not df.empty else "Heatmap global: vacío"
        )
        return df

    @staticmethod
    def _classify_flow_signal(rel_vol: float, change_pct: float) -> str:
        """
        Clasifica la señal de flujo institucional en base a
        la posición estática de Relative Volume y precio.

        Matriz Wyckoff simplificada:
          RVol alto + Change >0  → ACCUMULATION_ACTIVE  (dinero llegando)
          RVol alto + Change <0  → DISTRIBUTION          (dinero saliendo — evitar)
          RVol bajo  + Change >0  → WEAK_RALLY            (sin respaldo institucional)
          RVol bajo  + Change <0  → QUIET_DECLINE         (sin catalizador aún)
          RVol med   + Change ≈0   → CONSOLIDATION         (acumulación silenciosa posible)
        """
        if rel_vol >= 1.5 and change_pct > 0.3:
            return 'ACCUMULATION_ACTIVE'
        elif rel_vol >= 1.5 and change_pct < -0.3:
            return 'DISTRIBUTION'
        elif rel_vol >= 1.5 and abs(change_pct) <= 0.3:
            return 'HIGH_VOL_CONSOLIDATION'  # ← Potencial punto de ruptura inminente
        elif rel_vol < 0.8 and change_pct > 0.3:
            return 'WEAK_RALLY'
        elif rel_vol < 0.8 and change_pct < -0.3:
            return 'QUIET_DECLINE'
        else:
            return 'CONSOLIDATION'

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """Convierte un valor a float de forma segura."""
        if value is None:
            return default
        try:
            return float(str(value).replace('%', '').replace(',', '').strip())
        except (ValueError, TypeError):
            return default
