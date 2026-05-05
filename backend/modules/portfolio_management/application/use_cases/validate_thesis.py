"""
Validate Thesis Checkpoints Use Case
======================================
Application-layer entry point for thesis checkpoint evaluation.
SurveillanceLoop (execution module) calls this instead of importing
portfolio_management domain rules directly.
"""
from backend.modules.portfolio_management.domain.rules.thesis_validator import ThesisValidator
from backend.modules.portfolio_management.domain.entities.thesis_checkpoint import InvestmentThesis


def validate_thesis(thesis: InvestmentThesis, current_metrics: dict) -> InvestmentThesis:
    """Evaluate all checkpoints in a thesis against current metrics.
    
    Returns the (potentially mutated) thesis with breached checkpoints marked.
    """
    return ThesisValidator.evaluate_checkpoints(thesis, current_metrics)
