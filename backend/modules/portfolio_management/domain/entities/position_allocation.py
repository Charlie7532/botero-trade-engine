from dataclasses import dataclass

@dataclass
class PositionAllocation:
    ticker: str
    weight: float          # 0-1
    sector: str
    rs_score: float
    qualifier_grade: str
    conviction: float      # 0-100
