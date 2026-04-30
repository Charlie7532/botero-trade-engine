"""
Candidate Dossier
=================
El "expediente" completo de una acción a través del Research Pipeline.
Se pasa al CIO (Dalio) en el IC Review.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, UTC

@dataclass
class CandidateDossier:
    # Identidad
    ticker: str
    sector: str
    status: str  # SOURCING, SCREENING, RESEARCH, IC_REVIEW, APPROVED, WATCHLIST, BUY_NOW, REJECTED
    
    # Munger's Inversion (Must be first in presentation!)
    short_seller_thesis: str = ""
    
    # Moat (Hohn)
    moat_classification: str = "UNKNOWN"
    barrier_stack: List[str] = field(default_factory=list)
    moat_stress_results: Dict = field(default_factory=dict)
    capex_dependency: float = 0.0
    
    # Valuation (Buffett)
    gf_value: float = 0.0
    current_price: float = 0.0
    discount_pct: float = 0.0
    
    buy_zone: float = 0.0
    add_zone: float = 0.0
    fair_value_low: float = 0.0
    fair_value_high: float = 0.0
    reduce_zone: float = 0.0
    
    # Technical/Gamma Structure (PTJ / Eifert)
    price_phase: str = "UNKNOWN"
    risk_reward: float = 0.0
    dma_200: float = 0.0
    put_wall: float = 0.0
    call_wall: float = 0.0
    vp_poc: float = 0.0
    vp_vah: float = 0.0
    vp_val: float = 0.0
    
    # Intelligence (Guru/Insider/SEC)
    guru_conviction: float = 0.0
    insider_conviction: float = 0.0
    sec_risk_factors: str = ""
    
    # Dalio's Idea Meritocracy Score
    # 1.0 (Baja confianza, datos faltantes) a 10.0 (Alta confianza, datos frescos y verificados)
    research_confidence_score: float = 5.0
    expert_opinions: Dict = field(default_factory=dict)
    disagreement_log: str = ""
    
    # Timestamps
    sourced_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    researched_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
