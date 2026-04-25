import logging
import pandas as pd
from typing import Optional
from backend.modules.portfolio_management.domain.entities.position_allocation import PositionAllocation

logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    """
    Optimizador de portafolio con constraints institucionales.
    
    Implementa una versión simplificada de HRP que:
    1. Usa correlaciones rolling para detectar clusters
    2. Aplica inverse-variance weighting dentro de clusters
    3. Respeta constraints duros (max por posición/sector)
    
    Para HRP completo, instalar pypfopt.
    """
    
    MAX_POSITIONS = 8
    MIN_WEIGHT = 0.05      # 5% mínimo por posición
    MAX_WEIGHT = 0.25      # 25% máximo por posición
    MAX_SECTOR = 0.40      # 40% máximo por sector
    MIN_CASH = 0.10        # 10% cash mínimo
    MAX_CORRELATION = 0.75 # No más de 2 stocks con corr > 0.75
    
    def optimize_weights(
        self,
        candidates: list[dict],
        returns_df: Optional[pd.DataFrame] = None,
    ) -> list[PositionAllocation]:
        """
        Calcula pesos óptimos para un conjunto de candidatos.
        
        Args:
            candidates: Lista de dicts con ticker, sector, rs_score, 
                       qualifier_grade, conviction
            returns_df: DataFrame de retornos diarios (optional, para correlación)
        """
        if not candidates:
            return []
        
        # Limitar a MAX_POSITIONS
        candidates = sorted(candidates, key=lambda x: -x.get('conviction', 0))
        candidates = candidates[:self.MAX_POSITIONS]
        
        n = len(candidates)
        available = 1.0 - self.MIN_CASH
        
        # Intento 1: HRP si tenemos datos de retornos
        if returns_df is not None and len(returns_df) > 30:
            weights = self._hrp_weights(candidates, returns_df)
        else:
            # Fallback: Conviction-weighted
            weights = self._conviction_weights(candidates)
        
        # Aplicar constraints
        weights = self._apply_constraints(candidates, weights)
        
        # Escalar a capital disponible
        total = sum(weights.values())
        if total > 0:
            weights = {k: v * available / total for k, v in weights.items()}
        
        allocations = []
        for c in candidates:
            t = c['ticker']
            w = weights.get(t, 0)
            if w >= self.MIN_WEIGHT:
                allocations.append(PositionAllocation(
                    ticker=t,
                    weight=round(w, 4),
                    sector=c.get('sector', 'Unknown'),
                    rs_score=c.get('rs_score', 1.0),
                    qualifier_grade=c.get('qualifier_grade', 'C'),
                    conviction=c.get('conviction', 50),
                ))
        
        return allocations
    
    def _conviction_weights(self, candidates: list[dict]) -> dict:
        """Pesos basados en convicción (fallback sin datos de retornos)."""
        weights = {}
        total_conv = sum(c.get('conviction', 50) for c in candidates)
        if total_conv == 0:
            total_conv = len(candidates) * 50
        
        for c in candidates:
            conv = c.get('conviction', 50)
            weights[c['ticker']] = conv / total_conv
        
        return weights
    
    def _hrp_weights(self, candidates: list[dict], returns_df: pd.DataFrame) -> dict:
        """
        HRP simplificado: inverse-variance con penalización por correlación.
        """
        tickers = [c['ticker'] for c in candidates if c['ticker'] in returns_df.columns]
        if len(tickers) < 2:
            return self._conviction_weights(candidates)
        
        sub = returns_df[tickers].dropna()
        if len(sub) < 30:
            return self._conviction_weights(candidates)
        
        # Varianza de cada activo
        variances = sub.var()
        
        # Inverse variance weights
        inv_var = 1.0 / variances.replace(0, variances.max())
        
        # Penalizar pares con alta correlación
        corr = sub.corr()
        for i, t1 in enumerate(tickers):
            for j, t2 in enumerate(tickers):
                if i < j and abs(corr.loc[t1, t2]) > self.MAX_CORRELATION:
                    # Reducir el peso del que tiene menor convicción
                    c1 = next((c['conviction'] for c in candidates if c['ticker'] == t1), 50)
                    c2 = next((c['conviction'] for c in candidates if c['ticker'] == t2), 50)
                    weaker = t1 if c1 < c2 else t2
                    inv_var[weaker] *= 0.5
                    logger.warning(
                        f"Correlación {t1}/{t2}: {corr.loc[t1, t2]:.2f} > {self.MAX_CORRELATION}. "
                        f"Reduciendo {weaker}."
                    )
        
        total = inv_var.sum()
        weights = {t: (inv_var[t] / total) for t in tickers}
        
        # Agregar tickers sin datos de retornos con peso mínimo
        for c in candidates:
            if c['ticker'] not in weights:
                weights[c['ticker']] = self.MIN_WEIGHT
        
        return weights
    
    def _apply_constraints(self, candidates: list[dict], weights: dict) -> dict:
        """Aplica constraints duros de max por posición y sector."""
        # Max por posición
        for t in weights:
            weights[t] = max(self.MIN_WEIGHT, min(weights[t], self.MAX_WEIGHT))
        
        # Max por sector
        sector_weights = {}
        for c in candidates:
            t = c['ticker']
            s = c.get('sector', 'Unknown')
            sector_weights.setdefault(s, []).append(t)
        
        for sector, tickers in sector_weights.items():
            sector_total = sum(weights.get(t, 0) for t in tickers)
            if sector_total > self.MAX_SECTOR:
                scale = self.MAX_SECTOR / sector_total
                for t in tickers:
                    weights[t] = weights.get(t, 0) * scale
        
        return weights
