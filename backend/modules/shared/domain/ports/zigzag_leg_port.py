"""
ZigzagLegPort — Domain Port for Zigzag Leg Queries & Persistence
=================================================================
ABC defining the contract for querying and storing ZigzagLeg data.
Consumed by ConvergenceCompositor, entry gates, and backtesting trainers.

Clean Architecture: Domain layer. No infrastructure dependencies.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from backend.modules.shared.domain.entities.zigzag_leg import ZigzagLeg


class ZigzagLegPort(ABC):
    """Port for querying and storing confirmed zigzag legs."""

    @abstractmethod
    def get_confirmed_legs(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> List[ZigzagLeg]:
        """
        Obtiene los tramos confirmados de un ticker para una escala específica.
        Si se pasa as_of_date, aplica filtro causal estricto:
        confirmed_at_timestamp <= as_of_date.
        """
        ...

    @abstractmethod
    def get_latest_confirmed_leg(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> Optional[ZigzagLeg]:
        """Obtiene el último tramo confirmado para un ticker y escala respetando as_of_date."""
        ...

