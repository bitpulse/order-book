"""
Data Formatting Utilities
Provides functions for formatting data for display
"""

from datetime import datetime
from typing import Union, Optional


def format_timestamp(timestamp: Union[datetime, str, float, int]) -> str:
    """
    Format a timestamp to ISO 8601 string

    Args:
        timestamp: Datetime object, ISO string, or Unix timestamp

    Returns:
        str: ISO 8601 formatted string
    """
    if isinstance(timestamp, datetime):
        return timestamp.isoformat()
    elif isinstance(timestamp, str):
        return timestamp
    elif isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp).isoformat()
    else:
        return str(timestamp)


def format_number(number: Union[int, float], decimals: int = 2) -> str:
    """
    Format a number with appropriate suffix (K, M, B)

    Args:
        number: Number to format
        decimals: Number of decimal places

    Returns:
        str: Formatted number string
    """
    if number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.{decimals}f}B"
    elif number >= 1_000_000:
        return f"{number / 1_000_000:.{decimals}f}M"
    elif number >= 1_000:
        return f"{number / 1_000:.{decimals}f}K"
    else:
        return f"{number:.{decimals}f}"


def parse_iso_timestamp(iso_string: str) -> Optional[datetime]:
    """
    Parse an ISO 8601 timestamp string to datetime

    Args:
        iso_string: ISO 8601 formatted string

    Returns:
        datetime: Parsed datetime object or None if invalid
    """
    try:
        # Handle various ISO formats
        clean_string = iso_string.replace('Z', '+00:00')
        return datetime.fromisoformat(clean_string)
    except (ValueError, AttributeError):
        return None
