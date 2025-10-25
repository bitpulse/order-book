"""
Trading strategies for backtesting

This module contains various trading strategy implementations that can be
used with the backtesting engine.
"""

from backtesting.strategies.base_strategy import BaseStrategy
from backtesting.strategies.whale_following import WhaleFollowingStrategy
from backtesting.strategies.momentum_reversal import MomentumReversalStrategy
from backtesting.strategies.deep_fill_reversal import DeepFillReversalStrategy

__all__ = [
    'BaseStrategy',
    'WhaleFollowingStrategy',
    'MomentumReversalStrategy',
    'DeepFillReversalStrategy',
]
