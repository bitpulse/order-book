"""
Input Validation Utilities
Provides functions for validating user input and parameters
"""

import re
from datetime import datetime
from typing import Dict, Any, Tuple, Optional


def validate_symbol(symbol: str) -> Tuple[bool, Optional[str]]:
    """
    Validate trading symbol format

    Args:
        symbol: Trading symbol (e.g., BTC_USDT)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not symbol:
        return False, "Symbol cannot be empty"

    # Check format: XXX_USDT or XXX_USD
    pattern = r'^[A-Z0-9]{2,10}_(USDT|USD|BUSD)$'
    if not re.match(pattern, symbol):
        return False, f"Invalid symbol format: {symbol}"

    return True, None


def validate_time_range(start: str, end: str) -> Tuple[bool, Optional[str]]:
    """
    Validate time range parameters

    Args:
        start: Start time (ISO 8601 format)
        end: End time (ISO 8601 format)

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

        if start_dt >= end_dt:
            return False, "Start time must be before end time"

        # Check if range is reasonable (not more than 30 days)
        delta = end_dt - start_dt
        if delta.days > 30:
            return False, "Time range cannot exceed 30 days"

        return True, None

    except (ValueError, AttributeError) as e:
        return False, f"Invalid timestamp format: {str(e)}"


def validate_analysis_params(params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate analysis parameters

    Args:
        params: Dictionary of analysis parameters

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ['symbol']
    for field in required_fields:
        if field not in params or not params[field]:
            return False, f"Missing required field: {field}"

    # Validate symbol
    is_valid, error = validate_symbol(params['symbol'])
    if not is_valid:
        return False, error

    # Validate lookback if present
    if 'lookback' in params:
        lookback = params['lookback']
        pattern = r'^\d+[smhd]$'
        if not re.match(pattern, lookback):
            return False, f"Invalid lookback format: {lookback}. Use format like '1h', '30m', '7d'"

    # Validate interval if present
    if 'interval' in params:
        interval = params['interval']
        pattern = r'^\d+[sm]$'
        if not re.match(pattern, interval):
            return False, f"Invalid interval format: {interval}. Use format like '1m', '30s'"

    # Validate numeric parameters
    if 'min_change' in params:
        try:
            min_change = float(params['min_change'])
            if min_change < 0 or min_change > 100:
                return False, "min_change must be between 0 and 100"
        except (ValueError, TypeError):
            return False, "min_change must be a number"

    if 'top' in params:
        try:
            top = int(params['top'])
            if top < 1 or top > 100:
                return False, "top must be between 1 and 100"
        except (ValueError, TypeError):
            return False, "top must be an integer"

    return True, None
