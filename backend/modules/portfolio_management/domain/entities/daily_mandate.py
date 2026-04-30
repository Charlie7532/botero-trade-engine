from dataclasses import dataclass, field


@dataclass
class DailyMandate:
    """
    The absolute mandate given by the CIO for the day.

    Determines capital allocation between Quality and Speculative departments,
    sector vetoes, and focus areas based on macro regime synthesis.
    """
    date: str
    quality_budget_pct: float
    speculative_budget_pct: float
    regime: str
    vetoed_sectors: list[str] = field(default_factory=list)
    focus_sectors: list[str] = field(default_factory=list)
    reasoning: str = ""
