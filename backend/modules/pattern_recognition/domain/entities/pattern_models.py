from dataclasses import dataclass

@dataclass
class PatternVerdict:
    """Resultado del análisis de patrones de velas y estructuras."""
    ticker: str = ""

    # Patrón primario detectado (última vela o secuencia)
    primary_pattern: str = "NONE"
    # Patrón secundario de confirmación (si existe)
    secondary_pattern: str = "NONE"

    # Sentimiento consolidado
    sentiment: str = "NEUTRAL"         # BULLISH | BEARISH | NEUTRAL
    confirmation_score: float = 0.0    # -1.0 (muy bajista) → +1.0 (muy alcista)

    # Estructuras de consolidación
    is_inside_bar_series: bool = False  # 2+ inside bars consecutivas = coil/spring
    is_vcp_tight: bool = False          # VCP de alta calidad (contracciones sucesivas)

    # Contexto de ubicación
    detected_on_support: bool = False   # ¿El patrón ocurre en zona de soporte clave?
    detected_on_resistance: bool = False

    # Meta
    candles_analyzed: int = 0
    diagnosis: str = ""
