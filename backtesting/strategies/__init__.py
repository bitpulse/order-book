"""
Trading strategies for backtesting

This module contains various trading strategy implementations that can be
used with the backtesting engine.
"""

from backtesting.strategies.base_strategy import BaseStrategy
from backtesting.strategies.whale_following import WhaleFollowingStrategy

__all__ = [
    'BaseStrategy',
    'WhaleFollowingStrategy',
]
