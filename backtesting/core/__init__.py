"""
Core backtesting components

This module contains the fundamental building blocks for the backtesting framework:
- Engine: Main backtesting loop and event processing
- DataLoader: Historical data fetching and preprocessing
- Portfolio: Position and capital management
- Execution: Order execution simulation with realistic modeling
- Metrics: Performance calculation and analysis
"""

from backtesting.core.models import Order, Position, Trade, BacktestResult
from backtesting.core.engine import BacktestEngine
from backtesting.core.data_loader import DataLoader
from backtesting.core.portfolio import Portfolio
from backtesting.core.execution import ExecutionSimulator
from backtesting.core.metrics import MetricsCalculator

__all__ = [
    'Order',
    'Position',
    'Trade',
    'BacktestResult',
    'BacktestEngine',
    'DataLoader',
    'Portfolio',
    'ExecutionSimulator',
    'MetricsCalculator',
]
