"""
BaseStrategy - Abstract base class for all trading strategies

All strategies must inherit from this class and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime
import pandas as pd

from backtesting.core.portfolio import Portfolio
from backtesting.core.execution import ExecutionSimulator


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies

    Subclasses must implement:
    - on_whale_event(): React to whale events
    - on_tick(): React to every price update (optional)

    Example:
        class MyStrategy(BaseStrategy):
            def on_whale_event(self, event, market_data, portfolio):
                if event['event_type'] == 'market_buy':
                    return {'action': 'OPEN_LONG'}
                return None

            def on_tick(self, timestamp, market_data, portfolio):
                # Optional: check conditions on every tick
                pass
    """

    def __init__(self, name: Optional[str] = None):
        """
        Initialize base strategy

        Args:
            name: Strategy name (defaults to class name)
        """
        self.name = name or self.__class__.__name__
        self.portfolio: Optional[Portfolio] = None
        self.execution_simulator: Optional[ExecutionSimulator] = None

    def initialize(self, portfolio: Portfolio, execution_simulator: ExecutionSimulator):
        """
        Called once before backtest starts

        Args:
            portfolio: Portfolio instance
            execution_simulator: ExecutionSimulator instance
        """
        self.portfolio = portfolio
        self.execution_simulator = execution_simulator

    @abstractmethod
    def on_whale_event(self,
                      event: pd.Series,
                      market_data: pd.Series,
                      portfolio: Portfolio) -> Optional[Dict[str, Any]]:
        """
        Called when a whale event occurs

        Args:
            event: Whale event data with fields:
                - timestamp: Event timestamp
                - event_type: 'market_buy', 'market_sell', 'limit_wall', etc.
                - usd_value: USD value of the event
                - price: Price at which event occurred
                - size: Size in base currency
                - side: 'bid' or 'ask'
            market_data: Current market data with fields:
                - mid_price: Current mid price
                - bid_price: Best bid
                - ask_price: Best ask
                - spread_pct: Spread percentage
                - whale_usd_total: Total whale USD in current window
                - whale_count: Number of whale events in window
                - etc.
            portfolio: Current portfolio state

        Returns:
            Signal dictionary or None:
                {
                    'action': 'OPEN_LONG' | 'OPEN_SHORT' | 'CLOSE_LONG' | 'CLOSE_SHORT',
                    'stop_loss_pct': 0.015,  # Optional: stop loss %
                    'take_profit_pct': 0.03,  # Optional: take profit %
                    'timeout_seconds': 60,  # Optional: timeout
                    'size': 0.1,  # Optional: position size override
                    'metadata': {}  # Optional: custom data
                }
        """
        pass

    def on_tick(self,
               timestamp: datetime,
               market_data: pd.Series,
               portfolio: Portfolio):
        """
        Called on every price tick (optional)

        Override this if your strategy needs to check conditions
        on every price update, not just whale events.

        Args:
            timestamp: Current timestamp
            market_data: Current market data
            portfolio: Current portfolio state
        """
        pass

    def on_order_filled(self, order: Any):
        """
        Called when an order is filled (optional)

        Args:
            order: Filled order
        """
        pass

    def on_position_opened(self, position: Any):
        """
        Called when a position is opened (optional)

        Args:
            position: Opened position
        """
        pass

    def on_position_closed(self, trade: Any):
        """
        Called when a position is closed (optional)

        Args:
            trade: Completed trade
        """
        pass
