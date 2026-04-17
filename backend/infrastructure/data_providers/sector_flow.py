import logging
import numpy as np
import pandas as pd
from typing import Optional
from datetime import datetime

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

    def __init__(self):
        self._finviz_available = False
        try:
            from finvizfinance.screener.overview import Overview
            from finvizfinance.group.performance import Performance
            self._finviz_available = True
        except ImportError:
            logger.warning("finvizfinance no disponible.")

    # ================================================================
    # NIVEL 2: CORRIENTE SECTORIAL
    # ================================================================

    def get_sector_performance(self) -> pd.DataFrame:
        """
        Obtiene rendimiento de cada sector en múltiples horizontes.
        Fuente: Finviz Group Performance.
        """
        if not self._finviz_available:
            return pd.DataFrame()

        try:
            from finvizfinance.group.performance import Performance
            perf = Performance()
            df = perf.screener_view(group='Sector')
            if df is not None and not df.empty:
                logger.info(f"Sector performance: {len(df)} sectores cargados")
                return df
        except Exception as e:
            logger.error(f"Error sector performance: {e}")

        return pd.DataFrame()

    def get_sector_breadth(self) -> list[dict]:
        """
        Calcula breadth por sector: % de acciones sobre 50-DMA.
        Esto muestra la SALUD INTERNA de cada sector.
        
        Un sector puede subir en precio (por 2-3 mega caps) mientras
        la mayoría de sus acciones bajan. Eso es DIVERGENCIA.
        
        Returns:
            Lista de dicts con sector, pct_above_50dma, health, trend
        """
        if not self._finviz_available:
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

    def get_movers(self, min_change_pct: str = "Up 3%") -> list[dict]:
        """
        Obtiene las acciones con mayor movimiento hoy del S&P500.
        Estas son las "olas" — movimientos individuales sobre la marea.
        """
        if not self._finviz_available:
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
                    "ticker": row.get("Ticker", ""),
                    "company": row.get("Company", ""),
                    "sector": row.get("Sector", ""),
                    "industry": row.get("Industry", ""),
                    "price": row.get("Price", 0),
                    "change": row.get("Change", 0),
                    "volume": row.get("Volume", 0),
                }
                for _, row in df.iterrows()
            ]
        except Exception as e:
            logger.error(f"Error movers: {e}")
            return []

    def get_unusual_volume(self, min_rel_vol: str = "Over 2") -> list[dict]:
        """
        Detecta acciones con volumen inusual (> 2x promedio).
        Volumen inusual = institucionales actuando.
        
        Regla: Volumen inusual + precio subiendo = acumulación institucional
                Volumen inusual + precio bajando = distribución / panic selling
        """
        if not self._finviz_available:
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
                change = row.get("Change", 0)
                if isinstance(change, str):
                    change = float(change.replace('%', '')) / 100

                action = "accumulation" if change > 0 else "distribution"

                results.append({
                    "ticker": row.get("Ticker", ""),
                    "company": row.get("Company", ""),
                    "sector": row.get("Sector", ""),
                    "price": row.get("Price", 0),
                    "change": change,
                    "volume": row.get("Volume", 0),
                    "institutional_action": action,
                })

            return results
        except Exception as e:
            logger.error(f"Error unusual volume: {e}")
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
            "timestamp": datetime.utcnow().isoformat(),
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
            "timestamp": datetime.utcnow().isoformat(),
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
