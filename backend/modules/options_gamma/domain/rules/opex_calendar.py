import pandas as pd
from datetime import datetime
from typing import Optional

from backend.modules.options_gamma.domain.entities.gamma_models import OpExType

def is_third_friday(d) -> bool:
    """Check if date is 3rd Friday of month."""
    if hasattr(d, 'date'):
        d = d.date()
    if isinstance(d, pd.Timestamp):
        d = d.date()
    if d.weekday() != 4:
        return False
    friday_count = sum(1 for day in range(1, d.day + 1)
                       if d.replace(day=day).weekday() == 4)
    return friday_count == 3


def is_quad_witching(d) -> bool:
    """
    Quad Witching: 3rd Friday of March, June, September, December.
    Stock options + index options + index futures + stock futures expire.
    """
    if hasattr(d, 'date'):
        d = d.date()
    return is_third_friday(d) and d.month in (3, 6, 9, 12)


def detect_opex(dt: Optional[datetime] = None) -> OpExType:
    """
    Detecta el tipo de OpEx para una fecha/hora dada.
    
    La fuerza del pin depende de:
    - Tipo de OpEx (Quad > Monthly > Weekly > Non)
    - Hora del día (9:30-12:00 ET = máxima fuerza)
    """
    if dt is None:
        dt = datetime.now()

    today = dt.date() if hasattr(dt, 'date') else dt
    hour_et = dt.hour + dt.minute / 60 if hasattr(dt, 'hour') else 12.0

    result = OpExType()

    # Determine OpEx type
    if is_quad_witching(today):
        result.opex_type = "QUAD_WITCHING"
        result.is_opex_day = True
    elif is_third_friday(today):
        result.opex_type = "MONTHLY_OPEX"
        result.is_opex_day = True
    elif hasattr(today, 'weekday') and today.weekday() == 4:
        result.opex_type = "WEEKLY_OPEX"
        result.is_opex_day = True
    else:
        result.opex_type = "NON_OPEX"
        result.is_opex_day = False

    # AM session (9:30-12:00 ET) = maximum gamma pin force
    result.is_am_session = 9.5 <= hour_et <= 12.0

    # Time weight: how strong is the pin effect right now
    if not result.is_opex_day:
        result.time_weight = 0.0
    elif 9.5 <= hour_et <= 12.0:
        result.time_weight = 1.0  # Maximum
    elif 12.0 < hour_et <= 14.0:
        result.time_weight = 0.5  # Decaying
    elif 14.0 < hour_et <= 16.0:
        result.time_weight = 0.2  # Weak
    else:
        result.time_weight = 0.0  # Pre/post market

    # OpEx type multiplier
    type_mult = {
        "QUAD_WITCHING": 1.3,
        "MONTHLY_OPEX": 1.0,
        "WEEKLY_OPEX": 0.6,
        "NON_OPEX": 0.0,
    }
    result.time_weight *= type_mult.get(result.opex_type, 0.0)

    return result
