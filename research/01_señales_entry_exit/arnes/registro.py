"""Registro de señales: SEÑALES y _CERTEZA (metadatos de validación).

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""

SEÑALES = {}
_CERTEZA = {}  # nombre -> {validacion, n_min, dsr, fuente}

def _registrar(nombre, **certeza):
    """Registra una señal con su metadata de validación.
    certeza: {validacion, n_min, dsr, fuente, nota}
    - validacion: "VALIDATED (Grade A)" | "MODERATE" | "SPECULATIVE"
    - n_min: muestra mínima de la validación original
    - dsr: Deflated Sharpe Ratio p-value
    - fuente: documento de referencia
    """
    def deco(fn):
        SEÑALES[nombre] = fn
        _CERTEZA[nombre] = certeza
        return fn
    return deco
