"""
DeepFillReversalStrategy - Trade reversals after deep market sells

This strategy detects large market sell orders that execute far from the mid price,
indicating panic selling or order book clearing. It enters long positions expecting
a bounce back to fair value.

Strategy Logic:
1. Monitor for large market sell events
2. Check if execution price is far from mid price (e.g., 0.1%+ below)
3. This indicates deep order book clearing / panic selling
4. Enter LONG position immediately, expecting bounce
5. Exit on stop loss, take profit, or timeout

Example Scenario:
- Mid price: $460.50
- Market sell $100k executes at $458.50 (0.43% below mid)
- Order book was cleared deeply → likely oversold
- Strategy enters LONG expecting price to recover

Key Insight:
When market sells execute with large distance from mid price, it often represents
temporary imbalance that gets corrected quickly as liquidity providers step in.

Example:
    strategy = DeepFillReversalStrategy(
        min_distance_from_mid_pct=0.1,     # 0.1% distance minimum
        min_market_sell_usd=100000,        # $100k minimum sell
        stop_loss_pct=0.015,               # 1.5% stop
        take_profit_pct=0.030,             # 3.0% target
    )

    engine = BacktestEngine(strategy=strategy, initial_capital=10000)
    result = engine.run('BTC_USDT', '2025-09-01', '2025-10-01')
"""

from typing import Optional, Dict, Any
import pandas as pd
from loguru import logger
from datetime import datetime

from backtesting.strategies.base_strategy import BaseStrategy
from backtesting.core.portfolio import Portfolio


class DeepFillReversalStrategy(BaseStrategy):
    """
    Strategy that trades reversals after deep market sell fills

    The strategy looks for market sell orders that execute far from the mid price,
    indicating order book clearing and potential overreaction.

    Parameters:
        min_distance_from_mid_pct: Minimum distance from mid price % (default: 0.1%)
                                   Example: 0.1 means execution must be 0.1%+ below mid
        min_market_sell_usd: Minimum market sell size in USD (default: 100,000)
        max_distance_from_mid_pct: Maximum distance to trade (default: 5.0%)
                                   Filters extreme outliers / bad data
        stop_loss_pct: Stop loss percentage below entry (default: 1.5%)
        take_profit_pct: Take profit percentage above entry (default: 3.0%)
        timeout_seconds: Max position hold time (default: 60s)
        entry_delay_seconds: Delay before entry (manual trading sim, default: 2s)
        cooldown_seconds: Cooldown after trade before next signal (default: 120s)
        allow_market_buy_shorts: Also trade market buys above mid (short signal, default: False)
        max_spread_pct: Maximum spread to allow entry (default: 0.05% = 0.0005)
    """

    def __init__(self,
                 min_distance_from_mid_pct: float = 0.1,
                 min_market_sell_usd: float = 100000,
                 max_distance_from_mid_pct: float = 5.0,
                 stop_loss_pct: float = 0.015,
                 take_profit_pct: float = 0.030,
                 timeout_seconds: int = 60,
                 entry_delay_seconds: int = 2,
                 cooldown_seconds: int = 120,
                 allow_market_buy_shorts: bool = False,
                 max_spread_pct: float = 0.05):
        """
        Initialize deep fill reversal strategy

        Args:
            min_distance_from_mid_pct: Minimum distance from mid price (%)
            min_market_sell_usd: Minimum market sell size (USD)
            max_distance_from_mid_pct: Maximum distance to filter outliers (%)
            stop_loss_pct: Stop loss percentage (e.g., 0.015 = 1.5%)
            take_profit_pct: Take profit percentage (e.g., 0.030 = 3.0%)
            timeout_seconds: Position timeout
            entry_delay_seconds: Entry delay (simulates manual reaction time)
            cooldown_seconds: Cooldown period after trade
            allow_market_buy_shorts: Also trade market buys with distance (short signals)
            max_spread_pct: Maximum allowed spread percentage
        """
        super().__init__(name='DeepFillReversalStrategy')

        self.min_distance_from_mid_pct = min_distance_from_mid_pct
        self.min_market_sell_usd = min_market_sell_usd
        self.max_distance_from_mid_pct = max_distance_from_mid_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.timeout_seconds = timeout_seconds
        self.entry_delay_seconds = entry_delay_seconds
        self.cooldown_seconds = cooldown_seconds
        self.allow_market_buy_shorts = allow_market_buy_shorts
        self.max_spread_pct = max_spread_pct

        # State tracking
        self.last_trade_time: Optional[datetime] = None

        # Statistics
        self.signals_generated = 0
        self.signals_filtered = 0
        self.deep_sells_detected = 0
        self.deep_buys_detected = 0

        logger.info(f"Initialized {self.name} with parameters:")
        logger.info(f"  min_distance_from_mid_pct: {min_distance_from_mid_pct}%")
        logger.info(f"  min_market_sell_usd: ${min_market_sell_usd:,.0f}")
        logger.info(f"  max_distance_from_mid_pct: {max_distance_from_mid_pct}%")
        logger.info(f"  stop_loss: {stop_loss_pct*100:.2f}%")
        logger.info(f"  take_profit: {take_profit_pct*100:.2f}%")
        logger.info(f"  timeout: {timeout_seconds}s")
        logger.info(f"  cooldown: {cooldown_seconds}s")
        logger.info(f"  allow_market_buy_shorts: {allow_market_buy_shorts}")
        logger.info(f"  max_spread: {max_spread_pct*100:.3f}%")

    def on_whale_event(self,
                      event: pd.Series,
                      market_data: pd.Series,
                      portfolio: Portfolio) -> Optional[Dict[str, Any]]:
        """
        React to whale events - detect deep fills and generate reversal signals

        Args:
            event: Whale event data
            market_data: Current market data
            portfolio: Portfolio state

        Returns:
            Signal dict or None
        """
        timestamp = event.get('timestamp', datetime.now(tz=None))
        event_type = event.get('event_type', '')
        usd_value = event.get('usd_value', 0)
        price = event.get('price', 0)
        distance_from_mid_pct = event.get('distance_from_mid_pct', 0)  # Keep original sign
        mid_price = event.get('mid_price', 0)

        # Only care about market buy/sell events
        if event_type not in ['market_buy', 'market_sell']:
            return None

        # Check cooldown
        if self.last_trade_time:
            time_since_trade = (timestamp - self.last_trade_time).total_seconds()
            if time_since_trade < self.cooldown_seconds:
                return None

        # Check if we already have positions
        if len(portfolio.positions) > 0:
            self.signals_filtered += 1
            return None

        # Check spread (avoid wide spreads)
        spread_pct = market_data.get('spread_pct', 0)
        if spread_pct > self.max_spread_pct:
            self.signals_filtered += 1
            if self.signals_filtered <= 3:
                logger.debug(f"Filtered: spread too wide ({spread_pct*100:.3f}% > {self.max_spread_pct*100:.3f}%)")
            return None

        # Process market sell (LONG signals)
        if event_type == 'market_sell':
            return self._process_market_sell(event, market_data, timestamp, usd_value, price,
                                             distance_from_mid_pct, mid_price)

        # Process market buy (SHORT signals, if enabled)
        if event_type == 'market_buy' and self.allow_market_buy_shorts:
            return self._process_market_buy(event, market_data, timestamp, usd_value, price,
                                           distance_from_mid_pct, mid_price)

        return None

    def _process_market_sell(self,
                            event: pd.Series,
                            market_data: pd.Series,
                            timestamp: datetime,
                            usd_value: float,
                            price: float,
                            distance_from_mid_pct: float,
                            mid_price: float) -> Optional[Dict[str, Any]]:
        """
        Process market sell event for LONG signals

        Args:
            event: Whale event
            market_data: Current market data
            timestamp: Event timestamp
            usd_value: USD value of sell
            price: Execution price
            distance_from_mid_pct: Distance from mid price (%)
            mid_price: Mid price at event time

        Returns:
            Signal dict or None
        """
        # Check minimum USD size
        if usd_value < self.min_market_sell_usd:
            self.signals_filtered += 1
            return None

        # Check distance threshold (sell should be BELOW mid, so distance should be negative)
        # For market sells: negative distance = sold below mid price (deep fill)
        # We want: distance <= -min_distance_from_mid_pct (e.g., -0.1% or lower)
        if distance_from_mid_pct >= 0:
            # Sell executed at or above mid - not a deep fill
            self.signals_filtered += 1
            return None

        # Check minimum distance (use absolute value for comparison)
        abs_distance = abs(distance_from_mid_pct)
        if abs_distance < self.min_distance_from_mid_pct:
            self.signals_filtered += 1
            return None

        # Check maximum distance (filter outliers)
        if abs_distance > self.max_distance_from_mid_pct:
            self.signals_filtered += 1
            if self.signals_filtered <= 3:
                logger.warning(f"Filtered: distance too large ({abs_distance:.2f}% > {self.max_distance_from_mid_pct}%)")
            return None

        # Deep fill detected!
        self.deep_sells_detected += 1
        self.signals_generated += 1

        logger.info(f"🔴 DEEP FILL SELL #{self.deep_sells_detected}: "
                   f"${usd_value:,.0f} @ ${price:.2f} "
                   f"(mid: ${mid_price:.2f}, distance: {abs_distance:.2f}% below)")

        # Record trade time for cooldown
        self.last_trade_time = timestamp

        # Generate LONG signal
        signal = {
            'action': 'OPEN_LONG',
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'timeout_seconds': self.timeout_seconds,
            'entry_delay_seconds': self.entry_delay_seconds,
            'metadata': {
                'strategy': 'deep_fill_reversal',
                'trigger_type': 'market_sell',
                'trigger_usd': usd_value,
                'trigger_price': price,
                'mid_price': mid_price,
                'distance_from_mid_pct': abs_distance,  # Store absolute distance
                'signal_number': self.signals_generated,
                'deep_sell_number': self.deep_sells_detected
            }
        }

        logger.debug(f"Generated LONG signal #{self.signals_generated}: "
                    f"deep sell ${usd_value:,.0f} @ ${price:.2f} "
                    f"({abs_distance:.2f}% below mid)")

        return signal

    def _process_market_buy(self,
                           event: pd.Series,
                           market_data: pd.Series,
                           timestamp: datetime,
                           usd_value: float,
                           price: float,
                           distance_from_mid_pct: float,
                           mid_price: float) -> Optional[Dict[str, Any]]:
        """
        Process market buy event for SHORT signals (contrarian)

        Args:
            event: Whale event
            market_data: Current market data
            timestamp: Event timestamp
            usd_value: USD value of buy
            price: Execution price
            distance_from_mid_pct: Distance from mid price (%)
            mid_price: Mid price at event time

        Returns:
            Signal dict or None
        """
        # Check minimum USD size
        if usd_value < self.min_market_sell_usd:  # Use same threshold
            self.signals_filtered += 1
            return None

        # Check distance threshold (buy should be ABOVE mid, so distance should be positive)
        # For market buys: positive distance = bought above mid price (deep fill)
        # We want: distance >= min_distance_from_mid_pct (e.g., 0.1% or higher)
        if distance_from_mid_pct <= 0:
            # Buy executed at or below mid - not a deep fill
            self.signals_filtered += 1
            return None

        # Check minimum distance (already positive for buys above mid)
        abs_distance = abs(distance_from_mid_pct)
        if abs_distance < self.min_distance_from_mid_pct:
            self.signals_filtered += 1
            return None

        # Check maximum distance (filter outliers)
        if abs_distance > self.max_distance_from_mid_pct:
            self.signals_filtered += 1
            return None

        # Deep fill detected!
        self.deep_buys_detected += 1
        self.signals_generated += 1

        logger.info(f"🟢 DEEP FILL BUY #{self.deep_buys_detected}: "
                   f"${usd_value:,.0f} @ ${price:.2f} "
                   f"(mid: ${mid_price:.2f}, distance: {abs_distance:.2f}% above)")

        # Record trade time for cooldown
        self.last_trade_time = timestamp

        # Generate SHORT signal (contrarian)
        signal = {
            'action': 'OPEN_SHORT',
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'timeout_seconds': self.timeout_seconds,
            'entry_delay_seconds': self.entry_delay_seconds,
            'metadata': {
                'strategy': 'deep_fill_reversal',
                'trigger_type': 'market_buy',
                'trigger_usd': usd_value,
                'trigger_price': price,
                'mid_price': mid_price,
                'distance_from_mid_pct': abs_distance,  # Store absolute distance
                'signal_number': self.signals_generated,
                'deep_buy_number': self.deep_buys_detected
            }
        }

        logger.debug(f"Generated SHORT signal #{self.signals_generated}: "
                    f"deep buy ${usd_value:,.0f} @ ${price:.2f} "
                    f"({abs_distance:.2f}% above mid)")

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
            'deep_sells_detected': self.deep_sells_detected,
            'deep_buys_detected': self.deep_buys_detected,
            'signal_acceptance_rate': (
                self.signals_generated / (self.signals_generated + self.signals_filtered)
                if (self.signals_generated + self.signals_filtered) > 0
                else 0
            )
        }
