"""
Backtesting Framework for Order Book Whale Trading Strategies

A comprehensive backtesting system designed specifically for testing trading strategies
based on order book whale activity, price movements, and market microstructure signals.

Main Components:
- BacktestEngine: Core event-driven backtesting engine
- DataLoader: Fetches historical data from InfluxDB and MongoDB
- Portfolio: Manages positions, cash, and equity tracking
- ExecutionSimulator: Models realistic order execution with fees and slippage
- Strategies: Pre-built and custom trading strategies
- Analysis: Performance metrics, visualization, and reporting

Example Usage:
    from backtesting import BacktestEngine, DataLoader
    from backtesting.strategies import WhaleFollowingStrategy

    # Initialize
    loader = DataLoader()
    strategy = WhaleFollowingStrategy(min_whale_usd=100000)
    engine = BacktestEngine(
        strategy=strategy,
        data_loader=loader,
        initial_capital=10000
    )

    # Run backtest
    results = engine.run(
        symbol='BTC_USDT',
        start_time='2025-09-01',
        end_time='2025-10-17'
    )

    # Analyze results
    print(f"Total Return: {results.total_return:.2f}%")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {results.max_drawdown:.2f}%")

    # Generate report
    results.generate_report('backtest_report.html')
"""

__version__ = '1.0.0'
__author__ = 'BitPulse Team'

from backtesting.core.engine import BacktestEngine
from backtesting.core.data_loader import DataLoader
from backtesting.core.portfolio import Portfolio
from backtesting.core.execution import ExecutionSimulator
from backtesting.core.metrics import MetricsCalculator
from backtesting.strategies import BaseStrategy, WhaleFollowingStrategy, MomentumReversalStrategy

__all__ = [
    'BacktestEngine',
    'DataLoader',
    'Portfolio',
    'ExecutionSimulator',
    'MetricsCalculator',
    'BaseStrategy',
    'WhaleFollowingStrategy',
    'MomentumReversalStrategy',
]
