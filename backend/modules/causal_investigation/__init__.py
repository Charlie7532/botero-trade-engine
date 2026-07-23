"""
Causal Investigation Engine — Transversal Domain Service Module
===================================================================
Dupla: Stan Weinstein (Veto Estructural) & Stanley Druckenmiller (Contra-Veto Causal).

Evaluates structural trend health and multi-vector causal evidence to prevent
dead-cat bounce traps and unlock paradigm-shift inflection entries.

Clean Architecture: Pure Domain Service Module. Concentrated Vault-First ingestion.
"""
from backend.modules.causal_investigation.domain.entities.weinstein_stage import (
    WeinsteinStage,
    StructuralVeto,
)
from backend.modules.causal_investigation.domain.entities.druckenmiller_causal import (
    CausalSignal,
    CausalEvidenceMatrix,
    CounterVetoResult,
)
from backend.modules.causal_investigation.domain.entities.causal_verification import (
    CausalDecision,
    CausalVerificationSnapshot,
)
from backend.modules.causal_investigation.domain.dtos.causal_dtos import (
    CausalInputDTO,
    CausalVerificationRequest,
    CausalVerificationResponse,
)
from backend.modules.causal_investigation.application.use_cases.evaluate_causal_conviction import (
    evaluate_causal_conviction,
)

__all__ = [
    "WeinsteinStage",
    "StructuralVeto",
    "CausalSignal",
    "CausalEvidenceMatrix",
    "CounterVetoResult",
    "CausalDecision",
    "CausalVerificationSnapshot",
    "CausalInputDTO",
    "CausalVerificationRequest",
    "CausalVerificationResponse",
    "evaluate_causal_conviction",
]
