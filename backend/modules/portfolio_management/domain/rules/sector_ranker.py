import logging
import numpy as np
import pandas as pd
from backend.modules.portfolio_management.domain.entities.universe_candidate import MarketRegime

logger = logging.getLogger(__name__)

class SectorRanker:
    """
    Tier 1: Ranking de sectores por momentum relativo contra SPX.
    
    Usa los datos locales de la bóveda (.claude/DATA/) para calcular
    fuerza relativa sin depender de APIs externas.
    """

    # Sectores defensivos vs cíclicos
    CYCLICAL = ["XLK", "XLY", "XLI"]
    DEFENSIVE = ["XLRE"]

    def __init__(self, data_dir: str = "/root/botero-trade/.claude/DATA"):
        self.data_dir = data_dir

    def rank_sectors(
        self,
        regime: MarketRegime,
        timeframe: str = "1D",
        lookback: int = 60,
    ) -> list[dict]:
        """
        Calcula momentum relativo de cada sector vs SPX.
        Filtra por régimen macro.
        
        Returns:
            Lista ordenada de sectores con su momentum score.
        """
        import os
        from pathlib import Path

        data_path = Path(self.data_dir)
        spx_file = None
        sector_files = {}

        # Buscar archivos por timeframe
        for folder in data_path.iterdir():
            if not folder.is_dir():
                continue
            ticker = folder.name
            for f in folder.glob(f"*{timeframe}*"):
                if ticker == "SPX":
                    spx_file = f
                else:
                    sector_files[ticker] = f

        if spx_file is None:
            logger.warning("No se encontró SPX para ranking. Retornando todos.")
            return [{"ticker": t, "momentum": 0.0, "eligible": True} for t in sector_files]

        # Cargar SPX
        spx_df = pd.read_csv(spx_file)
        spx_df.columns = [c.strip() for c in spx_df.columns]
        spx_close = spx_df['close'].values

        rankings = []
        for ticker, path in sector_files.items():
            try:
                df = pd.read_csv(path)
                df.columns = [c.strip() for c in df.columns]
                close = df['close'].values

                # Ajustar longitudes
                min_len = min(len(close), len(spx_close))
                if min_len < lookback + 1:
                    continue

                # Momentum relativo: Log(Sector/SPX) últimos N períodos
                ratio = close[-min_len:] / spx_close[-min_len:]
                momentum = np.log(ratio[-1] / ratio[-lookback]) if ratio[-lookback] > 0 else 0

                # Filtrar por régimen
                is_cyclical = ticker in self.CYCLICAL
                eligible = True
                if regime == MarketRegime.RISK_OFF and is_cyclical:
                    eligible = False  # En Risk-Off, no operar cíclicos
                elif regime == MarketRegime.CRISIS:
                    eligible = False  # En crisis, solo reversiones extremas

                rankings.append({
                    "ticker": ticker,
                    "momentum": float(momentum),
                    "eligible": eligible,
                    "type": "cyclical" if is_cyclical else "defensive",
                })
            except Exception as e:
                logger.warning(f"Error procesando {ticker}: {e}")

        # Ordenar por momentum descendente
        rankings.sort(key=lambda x: x["momentum"], reverse=True)
        return rankings
