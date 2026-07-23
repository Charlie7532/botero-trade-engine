"""
Weinstein Stage Domain Entities
==================================
Defines WeinsteinStage enum and StructuralVeto dataclass.
"""
from dataclasses import dataclass
from enum import Enum, auto


class WeinsteinStage(Enum):
    UNCLASSIFIED = 0
    STAGE_1_BASING = 1
    STAGE_2_ADVANCING = 2
    STAGE_3_TOPPING = 3
    STAGE_4_DECLINING = 4

    @property
    def label(self) -> str:
        names = {
            0: "UNCLASSIFIED",
            1: "STAGE_1_BASING",
            2: "STAGE_2_ADVANCING",
            3: "STAGE_3_TOPPING",
            4: "STAGE_4_DECLINING",
        }
        return names.get(self.value, "UNCLASSIFIED")


@dataclass(frozen=True)
class StructuralVeto:
    """Represents Stan Weinstein's structural veto decision."""
    symbol: str
    stage: WeinsteinStage
    is_vetoed: bool
    current_price: float = 0.0
    ma_150: float = 0.0
    ma_slope: float = 0.0
    rs_score: float = 0.0
    rationale: str = ""
