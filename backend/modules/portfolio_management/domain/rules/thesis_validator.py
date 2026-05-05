from backend.modules.portfolio_management.domain.entities.thesis_checkpoint import InvestmentThesis, ThesisCheckpoint
from datetime import datetime, UTC

class ThesisValidator:
    """
    Helmer Protocol: Falsification Engine.
    Evaluates new fundamental data against established thesis checkpoints.
    """

    @staticmethod
    def evaluate_checkpoints(thesis: InvestmentThesis, current_metrics: dict) -> InvestmentThesis:
        """
        Compares current fundamental metrics against the checkpoints.
        If a checkpoint is breached, the thesis is invalidated.
        """
        is_any_breached = False
        now_str = datetime.now(UTC).isoformat()
        
        for cp in thesis.checkpoints:
            # We don't re-evaluate already breached ones unless we want to reset.
            if cp.is_breached:
                is_any_breached = True
                continue
                
            if cp.metric_name in current_metrics:
                current_value = current_metrics[cp.metric_name]
                cp.current_value = float(current_value)
                
                # Rule of thumb for falsification: If the metric drops BELOW threshold, it's a breach.
                # Example: FCF Growth drops below 10%, or Margin drops below 20%.
                # For things like concentration risk, the metric name might be 'customer_concentration'
                # where going ABOVE is a breach. We assume a threshold dictionary or logic here.
                # For simplicity, if metric has "risk" or "concentration", breach is > threshold.
                if "risk" in cp.metric_name.lower() or "concentration" in cp.metric_name.lower():
                    if cp.current_value > cp.threshold_value:
                        cp.is_breached = True
                        cp.breach_date = now_str
                        cp.evidence_notes = f"Breach: {cp.metric_name} rose to {cp.current_value} (Max allowed: {cp.threshold_value})"
                        is_any_breached = True
                else:
                    if cp.current_value < cp.threshold_value:
                        cp.is_breached = True
                        cp.breach_date = now_str
                        cp.evidence_notes = f"Breach: {cp.metric_name} dropped to {cp.current_value} (Min required: {cp.threshold_value})"
                        is_any_breached = True
                    
        if is_any_breached:
            thesis.thesis_status = "INVALIDATED"
            
        return thesis
