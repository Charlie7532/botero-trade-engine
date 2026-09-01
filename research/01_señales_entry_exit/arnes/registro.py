"""Registro de señales: SEÑALES y _CERTEZA (metadatos de validación).

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.

§3.3 NOTA — Eventos de cola por construcción:
  SKEW D3=3,4 son estados inherentemente raros (~15% y ~2% frecuencia).
  D3=3 = expansión de cobertura de cola institucional.
  D3=4 = pánico de cola (31 eventos en 1,354 pivotes).
  La baja frecuencia NO es un defecto de muestra — es la naturaleza del indicador.
  No descartar por "N bajo" (Protocolo §3.3: rareza = riqueza).
  Analizar individualmente cada evento, no agregar con descarte estadístico.
"""

SEÑALES = {}
_CERTEZA = {}  # nombre -> {validacion, n_min, dsr, fuente, fecha_inicio_valida, era_valida}

# Fechas de inicio oficial de cada estación METAR.
# Cualquier dato previo a estas fechas es sintético / estimado y NO es válido para evaluación empírica.
ESTACION_INCEPTION_DATES = {
    "skew": "2011-02-01",          # CBOE SKEW Index oficial lanzado en Feb-2011 (pre-2011 sintética)
    "fg": "2011-02-01",            # CNN Fear & Greed Index
    "credit": "2007-04-11",        # HYG ETF (High Yield Corporate Bond) inception
    "pcr": "2006-11-01",           # CBOE Equity Options Put/Call Ratio serie moderna
    "vvix": "2006-03-06",          # CBOE VVIX Index (official launch)
    "sv5_turbulence": "1999-01-04",# SV5 Volume Breadth (datos de volumen institucional SP500)
    "rotation": "1999-01-04",      # Sector ETFs (XLY, XLP, XLK, XLU)
    "vix": "1990-01-02",           # CBOE VIX Index
    "yield_curve": "1993-01-29",   # TNX - IRX (10Y - 13W Yield Spread)
    "dxy": "1993-01-29",           # US Dollar Index
    "bsi": "1993-01-29",           # S&P 500 Breadth S5TH/FI/TW
}


def _registrar(nombre, **certeza):
    """Registra una señal con su metadata de validación.
    certeza: {validacion, n_min, dsr, fuente, fecha_inicio_valida, era_valida}
    - validacion: "VALIDATED (Grade A)" | "MODERATE" | "SPECULATIVE" | "RESCATADA"
    - n_min: muestra mínima de la validación original
    - dsr: Deflated Sharpe Ratio p-value
    - fuente: documento de referencia
    - fecha_inicio_valida: fecha mínima donde la data subyacente es real y no sintética (ej. 2011-02-01 para SKEW)
    - era_valida: "POST_2011" | "POST_2007" | "POST_1999" | "FULL"
    """
    def deco(fn):
        SEÑALES[nombre] = fn
        _CERTEZA[nombre] = certeza
        return fn
    return deco

