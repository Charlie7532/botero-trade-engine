from dataclasses import dataclass, field

@dataclass
class ThesisCheckpoint:
    """
    Representa un evento de falsación. Si una métrica fundamental clave
    (ej: concentración de clientes, revenue growth) cruza su threshold,
    la tesis se invalida.
    """
    id: str
    ticker: str
    metric_name: str
    threshold_value: float
    current_value: float
    is_breached: bool
    breach_date: str = ""
    evidence_notes: str = ""

@dataclass
class InvestmentThesis:
    """
    La Tesis Fundamental (QUALITY). Reside en Neon PostgreSQL.
    Solo puede existir una activa por ticker.
    """
    ticker: str
    author: str # "CIO" o "Helmer"
    thesis_status: str # "ACTIVE", "INVALIDATED", "ARCHIVED"
    created_at: str
    checkpoints: list[ThesisCheckpoint] = field(default_factory=list)
