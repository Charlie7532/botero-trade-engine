"""
Shared utility: derive MKT-level action code from guidance divergence_regime.

Used by all 11 METAR services to replace the removed operational_guidance field.
These are MKT-level signals (not STK) per user normativa.
"""


def derive_action_code(guidance) -> str:
    """Derive MKT-level action code from guidance divergence_regime.

    Returns a MKT_ prefixed action code based on the structural divergence
    between short-term (zz25) and long-term (zz75) probability vectors.
    """
    dr = getattr(guidance, 'divergence_regime', 'NEUTRAL')
    if dr == 'FULL_CONVERGENT_BULL':
        return 'MKT_ACCUMULATE_STRUCTURAL'
    elif dr == 'STRUCTURAL_BULL_PULLBACK':
        return 'MKT_BUY_DIP_TACTICAL'
    elif dr == 'FULL_CONVERGENT_BEAR':
        return 'MKT_TRIM_TACTICAL'
    elif dr == 'TACTICAL_REBOUND_IN_BEAR':
        return 'MKT_HOLD_STABLE'
    return 'MKT_HOLD_STABLE'
