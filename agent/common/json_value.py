"""
Helpers for converting database result values to JSON-friendly values.
"""

from datetime import date, datetime
from decimal import Decimal

try:
    import pandas as pd
except ImportError:  # pragma: no cover - pandas may not be installed in minimal envs
    pd = None


def is_missing_value(value) -> bool:
    """
    Return True for None and pandas/NumPy missing scalar values.

    pandas.NaT is also an instance of datetime, so this check must happen
    before datetime formatting.
    """
    if value is None:
        return True

    if pd is None:
        return False

    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False

    return isinstance(missing, bool) and missing


def convert_value_for_json(value):
    """
    Convert common database result value types to JSON-friendly scalar values.
    """
    if is_missing_value(value):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value
