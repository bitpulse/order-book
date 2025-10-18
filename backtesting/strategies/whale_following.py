"""
WhaleFollowingStrategy - Follow large whale market orders

This strategy monitors for large whale market orders and follows them
with the assumption that whales have information or market impact that
will move prices in their direction.

Strategy Logic:
1. Detect large whale market buy/sell orders
2. Wait a short delay (simulate reaction time)
3. Enter position in same direction as whale
4. Set tight stop loss and reasonable take profit
5. Exit on timeout if neither is hit
"""

from typing import Optional, Dict, Any
import pandas as pd
from loguru import logger

from backtesting.strategies.base_strategy import BaseStrategy
from backtesting.core.portfolio import Portfolio


class WhaleFollowingStrategy(BaseStrategy):
    """
    Strategy that follows large whale market orders

    Parameters:
        min_whale_usd: Minimum whale order size in USD to trigger (default: 100,000)
        entry_delay_seconds: Simulated delay before entering trade (default: 2)
        stop_loss_pct: Stop loss percentage (default: 0.15% = 0.0015)
        take_profit_pct: Take profit percentage (default: 0.30% = 0.0030)
        timeout_seconds: Maximum time to hold position (default: 60s)
        follow_buys: Whether to follow market buys (default: True)
        follow_sells: Whether to follow market sells (default: True)
        max_spread_pct: Maximum spread to allow entry (default: 0.1%)

    Example:
        strategy = WhaleFollowingStrategy(
            min_whale_usd=100000,
            stop_loss_pct=0.0015,
            take_profit_pct=0.0030,
            timeout_seconds=60
        )

        engine = BacktestEngine(strategy=strategy, initial_capital=10000)
        result = engine.run('BTC_USDT', '2025-09-01', '2025-10-01')
    """

    def __init__(self,
                 min_whale_usd: float = 100000,
                 entry_delay_seconds: int = 2,
                 stop_loss_pct: float = 0.0015,
                 take_profit_pct: float = 0.0030,
                 timeout_seconds: int = 60,
                 follow_buys: bool = True,
                 follow_sells: bool = True,
                 max_spread_pct: float = 0.001,
                 event_types: Optional[list] = None):
        """
        Initialize whale following strategy

        Args:
            min_whale_usd: Minimum whale size in USD
            entry_delay_seconds: Delay before entry (simulates reaction time)
            stop_loss_pct: Stop loss percentage (0.0015 = 0.15%)
            take_profit_pct: Take profit percentage (0.0030 = 0.30%)
            timeout_seconds: Position timeout in seconds
            follow_buys: Follow whale market buys
            follow_sells: Follow whale market sells
            max_spread_pct: Maximum allowed spread percentage
            event_types: List of event types to follow (default: ['market_buy', 'market_sell'])
                        Options: 'market_buy', 'market_sell', 'increase', 'decrease', 'new'
        """
        super().__init__(name='WhaleFollowingStrategy')

        self.min_whale_usd = min_whale_usd
        self.entry_delay_seconds = entry_delay_seconds
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.timeout_seconds = timeout_seconds
        self.follow_buys = follow_buys
        self.follow_sells = follow_sells
        self.max_spread_pct = max_spread_pct
        self.event_types = event_types or ['market_buy', 'market_sell']

        # Statistics
        self.signals_generated = 0
        self.signals_filtered = 0

        logger.info(f"Initialized {self.name} with parameters:")
        logger.info(f"  min_whale_usd: ${min_whale_usd:,.0f}")
        logger.info(f"  stop_loss: {stop_loss_pct*100:.2f}%")
        logger.info(f"  take_profit: {take_profit_pct*100:.2f}%")
        logger.info(f"  timeout: {timeout_seconds}s")
        logger.info(f"  event_types: {self.event_types}")

    def on_whale_event(self,
                      event: pd.Series,
                      market_data: pd.Series,
                      portfolio: Portfolio) -> Optional[Dict[str, Any]]:
        """
        React to whale events

        Args:
            event: Whale event data
            market_data: Current market data
            portfolio: Portfolio state

        Returns:
            Signal dict or None
        """
        # Extract event data
        event_type = event.get('event_type', '')
        usd_value = event.get('usd_value', 0)
        price = event.get('price', 0)

        # Debug first few events
        if self.signals_generated + self.signals_filtered < 5:
            logger.info(f"Whale event: type={event_type}, usd={usd_value:.0f}, price={price:.2f}")

        # Filter by event type
        if event_type not in self.event_types:
            return None

        # Log first few market orders
        if self.signals_generated + self.signals_filtered < 3:
            logger.info(f"Market order detected: {event_type}, ${usd_value:.0f}, min_usd=${self.min_whale_usd:.0f}")

        # Filter by minimum size
        if usd_value < self.min_whale_usd:
            if self.signals_filtered < 3:
                logger.info(f"Filtered: USD {usd_value:.0f} < min {self.min_whale_usd:.0f}")
            self.signals_filtered += 1
            return None

        # Check if we should follow this direction
        if event_type == 'market_buy' and not self.follow_buys:
            self.signals_filtered += 1
            return None
        if event_type == 'market_sell' and not self.follow_sells:
            self.signals_filtered += 1
            return None

        # Check spread (avoid wide spreads that increase costs)
        spread_pct = market_data.get('spread_pct', 0)
        if self.signals_filtered < 5:
            logger.info(f"Market order {event_type}: spread={spread_pct*100:.3f}%, max={self.max_spread_pct*100:.1f}%")
        if spread_pct > self.max_spread_pct:
            self.signals_filtered += 1
            if self.signals_filtered <= 5:
                logger.info(f"Filtered: spread too wide ({spread_pct*100:.3f}% > {self.max_spread_pct*100:.1f}%)")
            return None

        # Check if we already have positions
        if len(portfolio.positions) > 0:
            self.signals_filtered += 1
            if self.signals_filtered <= 3:
                logger.info(f"Filtered: position already open ({event_type} ${usd_value:.0f})")
            return None

        # Generate signal
        self.signals_generated += 1
        logger.info(f"✓ Generated signal #{self.signals_generated}: {event_type} ${usd_value:.0f} @ ${price:.2f}")

        # Determine action based on event type
        side = event.get('side', '')

        if event_type == 'market_buy':
            action = 'OPEN_LONG'
        elif event_type == 'market_sell':
            action = 'OPEN_SHORT'
        elif event_type in ['increase', 'new']:
            # Order book wall increases - follow the side
            if side == 'bid':
                action = 'OPEN_LONG'  # Large buy wall = support
            elif side == 'ask':
                action = 'OPEN_SHORT'  # Large sell wall = resistance
            else:
                logger.warning(f"Unknown side '{side}' for {event_type} event")
                return None
        elif event_type == 'decrease':
            # Order book wall decreases - contrarian signal (wall being eaten)
            if side == 'bid':
                action = 'OPEN_SHORT'  # Buy wall being eaten = bearish
            elif side == 'ask':
                action = 'OPEN_LONG'  # Sell wall being eaten = bullish
            else:
                logger.warning(f"Unknown side '{side}' for {event_type} event")
                return None
        else:
            logger.warning(f"Unknown event_type '{event_type}'")
            return None

        signal = {
            'action': action,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'timeout_seconds': self.timeout_seconds,
            'entry_delay_seconds': self.entry_delay_seconds,  # Manual trading delay
            'metadata': {
                'whale_usd': usd_value,
                'whale_type': event_type,
                'whale_price': price,
                'spread_pct': spread_pct,
                'signal_number': self.signals_generated
            }
        }

        logger.debug(f"Generated signal #{self.signals_generated}: {action} "
                    f"(whale ${usd_value:,.0f} @ ${price:.2f})")

        return signal

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get strategy statistics

        Returns:
            Dictionary with statistics
        """
        return {
            'signals_generated': self.signals_generated,
            'signals_filtered': self.signals_filtered,
            'signal_acceptance_rate': (
                self.signals_generated / (self.signals_generated + self.signals_filtered)
                if (self.signals_generated + self.signals_filtered) > 0
                else 0
            )
        }
