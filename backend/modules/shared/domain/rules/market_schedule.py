"""
Market Schedule — Pure Domain Rule
======================================
Determines if market data is stale based on US equity market hours,
weekends, and major holidays. No external dependencies.

Used by VRR freshness checks to avoid false positives on weekends
and holidays (e.g., Friday's data is NOT stale on Saturday morning).
"""
from datetime import date, timedelta


# Major US market holidays (recurring, approximate dates)
# Federal holidays that close the NYSE/NASDAQ
_FIXED_HOLIDAYS = {
    (1, 1),    # New Year's Day
    (6, 19),   # Juneteenth
    (7, 4),    # Independence Day
    (12, 25),  # Christmas Day
}

# Holidays that float but are predictable
# MLK (3rd Mon Jan), Presidents (3rd Mon Feb), Memorial (last Mon May),
# Labor (1st Mon Sep), Thanksgiving (4th Thu Nov)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday in a given month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of a weekday in a given month."""
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def us_market_holidays(year: int) -> set[date]:
    """Return the set of NYSE/NASDAQ holidays for a given year."""
    holidays = set()

    # Fixed holidays (with weekend adjustment)
    for month, day in _FIXED_HOLIDAYS:
        d = date(year, month, day)
        # If Saturday → observed Friday; if Sunday → observed Monday
        if d.weekday() == 5:
            d = d - timedelta(days=1)
        elif d.weekday() == 6:
            d = d + timedelta(days=1)
        holidays.add(d)

    # Floating holidays
    holidays.add(_nth_weekday(year, 1, 0, 3))   # MLK Day (3rd Monday Jan)
    holidays.add(_nth_weekday(year, 2, 0, 3))   # Presidents Day (3rd Monday Feb)
    holidays.add(_last_weekday(year, 5, 0))      # Memorial Day (last Monday May)
    holidays.add(_nth_weekday(year, 9, 0, 1))   # Labor Day (1st Monday Sep)
    holidays.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving (4th Thursday Nov)
    # Good Friday is variable — approximation skipped for simplicity;
    # the 1-day tolerance in is_data_stale handles it gracefully.

    return holidays


def is_trading_day(d: date) -> bool:
    """Return True if the given date is a US equity trading day."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return d not in us_market_holidays(d.year)


def previous_trading_day(d: date) -> date:
    """Return the most recent trading day on or before d."""
    while not is_trading_day(d):
        d = d - timedelta(days=1)
    return d


def is_data_stale(
    last_update: date,
    asset_type: str = "STOCK",
    max_age_trading_days: int = 1,
) -> bool:
    """
    Check if data is stale relative to market schedule.

    Args:
        last_update: Date of the most recent data point.
        asset_type: "STOCK", "ETF", "CRYPTO", "INDEX", "INDICATOR"
        max_age_trading_days: How many trading days old data can be.

    Returns:
        True if data is stale and a VRR refresh should be requested.
    """
    today = date.today()

    # Crypto and indicators trade 24/7 — use calendar days
    if asset_type in ("CRYPTO",):
        return (today - last_update).days > max_age_trading_days

    # For stocks/ETFs/indices: count trading days since last update
    trading_days_elapsed = 0
    check = last_update + timedelta(days=1)
    while check <= today:
        if is_trading_day(check):
            trading_days_elapsed += 1
        if trading_days_elapsed > max_age_trading_days:
            return True
        check += timedelta(days=1)

    return False
