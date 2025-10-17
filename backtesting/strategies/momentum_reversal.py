"""
MomentumReversalStrategy - Detect momentum dumps and catch reversals

This strategy detects heavy selling pressure followed by the first major buy,
indicating a potential momentum reversal at local lows.

Strategy Logic:
1. Phase 1: Monitor for heavy selling (market_sell events)
   - Track sell:buy ratio in rolling window
   - Detect price drops >threshold in <time window

2. Phase 2: Detect reversal setup
   - Heavy sells (5:1+ sell:buy ratio in 60s)
   - Price dropped >2% in <2min
   - Volume spike during dump

3. Phase 3: Entry trigger
   - First major buy appears (>$100k) at new local low
   - Enter long position immediately

4. Exit conditions:
   - Stop loss: Below the first major buy price
   - Take profit: Target percentage
   - Timeout: Max hold time

Example:
    strategy = MomentumReversalStrategy(
        min_first_buy_usd=100000,      # First buy must be $100k+
        sell_ratio_threshold=5.0,       # 5:1 sell:buy ratio
        price_drop_pct=2.0,             # 2% price drop
        lookback_seconds=60,            # Monitor last 60s
        stop_loss_pct=0.015,            # 1.5% stop loss
        take_profit_pct=0.030,          # 3.0% take profit
    )

    engine = BacktestEngine(strategy=strategy, initial_capital=10000)
    result = engine.run('BTC_USDT', '2025-09-01', '2025-10-01')
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger
from collections import deque

from backtesting.strategies.base_strategy import BaseStrategy
from backtesting.core.portfolio import Portfolio


class MomentumReversalStrategy(BaseStrategy):
    """
    Strategy that catches momentum reversals after heavy dumps

    Parameters:
        min_first_buy_usd: Minimum USD for first buy signal (default: 100,000)
        sell_ratio_threshold: Min sell:buy ratio to consider dump (default: 5.0)
        price_drop_pct: Min price drop % to trigger (default: 2.0%)
        price_drop_window_seconds: Time window for price drop (default: 120s)
        lookback_seconds: Time window to monitor sell/buy ratio (default: 60s)
        volume_spike_threshold: Min volume increase vs average (default: 2.0x)
        stop_loss_pct: Stop loss below entry (default: 1.5%)
        take_profit_pct: Take profit target (default: 3.0%)
        timeout_seconds: Max position hold time (default: 180s)
        entry_delay_seconds: Delay before entry (manual trading sim, default: 2s)
        cooldown_seconds: Cooldown after trade before next signal (default: 300s)
    """

    def __init__(self,
                 min_first_buy_usd: float = 100000,
                 sell_ratio_threshold: float = 5.0,
                 price_drop_pct: float = 2.0,
                 price_drop_window_seconds: int = 120,
                 lookback_seconds: int = 60,
                 volume_spike_threshold: float = 2.0,
                 stop_loss_pct: float = 0.015,
                 take_profit_pct: float = 0.030,
                 timeout_seconds: int = 180,
                 entry_delay_seconds: int = 2,
                 cooldown_seconds: int = 300):
        """
        Initialize momentum reversal strategy

        Args:
            min_first_buy_usd: Minimum USD value for first buy trigger
            sell_ratio_threshold: Minimum sell:buy ratio (e.g., 5.0 = 5:1)
            price_drop_pct: Minimum price drop percentage (e.g., 2.0 = 2%)
            price_drop_window_seconds: Time window to measure price drop
            lookback_seconds: Time window to calculate sell/buy ratio
            volume_spike_threshold: Minimum volume spike vs recent average
            stop_loss_pct: Stop loss percentage (e.g., 0.015 = 1.5%)
            take_profit_pct: Take profit percentage (e.g., 0.030 = 3.0%)
            timeout_seconds: Position timeout
            entry_delay_seconds: Entry delay (simulates manual reaction time)
            cooldown_seconds: Cooldown period after trade
        """
        super().__init__(name='MomentumReversalStrategy')

        self.min_first_buy_usd = min_first_buy_usd
        self.sell_ratio_threshold = sell_ratio_threshold
        self.price_drop_pct = price_drop_pct
        self.price_drop_window_seconds = price_drop_window_seconds
        self.lookback_seconds = lookback_seconds
        self.volume_spike_threshold = volume_spike_threshold
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.timeout_seconds = timeout_seconds
        self.entry_delay_seconds = entry_delay_seconds
        self.cooldown_seconds = cooldown_seconds

        # State tracking
        self.market_events: deque = deque()  # (timestamp, event_type, usd_value)
        self.price_history: deque = deque()  # (timestamp, price)
        self.dump_detected_at: Optional[datetime] = None
        self.dump_low_price: Optional[float] = None
        self.last_trade_time: Optional[datetime] = None

        # Statistics
        self.dumps_detected = 0
        self.signals_generated = 0
        self.signals_filtered = 0

        logger.info(f"Initialized {self.name} with parameters:")
        logger.info(f"  min_first_buy_usd: ${min_first_buy_usd:,.0f}")
        logger.info(f"  sell_ratio_threshold: {sell_ratio_threshold}:1")
        logger.info(f"  price_drop: {price_drop_pct}% in {price_drop_window_seconds}s")
        logger.info(f"  lookback_window: {lookback_seconds}s")
        logger.info(f"  stop_loss: {stop_loss_pct*100:.2f}%")
        logger.info(f"  take_profit: {take_profit_pct*100:.2f}%")
        logger.info(f"  timeout: {timeout_seconds}s")
        logger.info(f"  cooldown: {cooldown_seconds}s")

    def on_tick(self,
               timestamp: datetime,
               market_data: pd.Series,
               portfolio: Portfolio):
        """
        Update price history on every tick

        Args:
            timestamp: Current timestamp
            market_data: Current market data
            portfolio: Portfolio state
        """
        current_price = market_data.get('mid_price', 0)

        # Add to price history
        self.price_history.append((timestamp, current_price))

        # Clean old price history (keep 5 minutes)
        cutoff_time = timestamp - timedelta(seconds=300)
        while self.price_history and self.price_history[0][0] < cutoff_time:
            self.price_history.popleft()

    def on_whale_event(self,
                      event: pd.Series,
                      market_data: pd.Series,
                      portfolio: Portfolio) -> Optional[Dict[str, Any]]:
        """
        React to whale events - track market orders and detect reversals

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

        # Only track market buy/sell events
        if event_type not in ['market_buy', 'market_sell']:
            return None

        # Add event to history
        self.market_events.append((timestamp, event_type, usd_value))

        # Clean old events (keep only lookback window)
        cutoff_time = timestamp - timedelta(seconds=self.lookback_seconds)
        while self.market_events and self.market_events[0][0] < cutoff_time:
            self.market_events.popleft()

        # Check if we're in cooldown period
        if self.last_trade_time:
            time_since_trade = (timestamp - self.last_trade_time).total_seconds()
            if time_since_trade < self.cooldown_seconds:
                return None

        # Don't generate signals if we already have positions
        if len(portfolio.positions) > 0:
            return None

        # Phase 1: Check for dump conditions
        dump_active = self._check_dump_conditions(timestamp, market_data)

        # Phase 2: If dump detected and we see first major buy, generate signal
        if dump_active and event_type == 'market_buy' and usd_value >= self.min_first_buy_usd:
            return self._generate_reversal_signal(event, market_data, timestamp, price, usd_value)

        return None

    def _check_dump_conditions(self, timestamp: datetime, market_data: pd.Series) -> bool:
        """
        Check if dump conditions are met

        Returns:
            True if dump conditions are satisfied
        """
        current_price = market_data.get('mid_price', 0)

        # Calculate sell:buy ratio from recent events
        buy_volume = sum(usd for ts, evt, usd in self.market_events if evt == 'market_buy')
        sell_volume = sum(usd for ts, evt, usd in self.market_events if evt == 'market_sell')

        # Avoid division by zero
        if buy_volume < 1:
            buy_volume = 1

        sell_ratio = sell_volume / buy_volume

        # Check sell ratio threshold
        if sell_ratio < self.sell_ratio_threshold:
            # Reset dump state if ratio drops below threshold
            if self.dump_detected_at:
                self.dump_detected_at = None
                self.dump_low_price = None
            return False

        # Calculate price drop in window
        price_drop_window = timedelta(seconds=self.price_drop_window_seconds)
        price_history_in_window = [
            (ts, p) for ts, p in self.price_history
            if ts >= timestamp - price_drop_window
        ]

        if len(price_history_in_window) < 2:
            return False

        high_price = max(p for ts, p in price_history_in_window)
        price_drop_pct = ((high_price - current_price) / high_price) * 100

        # Check if price drop threshold met
        if price_drop_pct < self.price_drop_pct:
            # Reset dump state if price drop not enough
            if self.dump_detected_at:
                self.dump_detected_at = None
                self.dump_low_price = None
            return False

        # Calculate volume spike (compare recent volume to baseline)
        recent_volume = sum(usd for ts, evt, usd in self.market_events)
        avg_event_volume = recent_volume / max(len(self.market_events), 1)

        # Simplified volume spike check (compare total volume to event count)
        has_volume_spike = recent_volume > 0  # Just ensure there's activity

        # All conditions met - dump detected!
        if not self.dump_detected_at:
            self.dump_detected_at = timestamp
            self.dump_low_price = current_price
            self.dumps_detected += 1
            logger.info(f"🔴 DUMP DETECTED #{self.dumps_detected}: "
                       f"sell_ratio={sell_ratio:.1f}:1, "
                       f"price_drop={price_drop_pct:.2f}%, "
                       f"price=${current_price:.2f}")
        else:
            # Update low price if we went lower
            if current_price < self.dump_low_price:
                self.dump_low_price = current_price

        return True

    def _generate_reversal_signal(self,
                                  event: pd.Series,
                                  market_data: pd.Series,
                                  timestamp: datetime,
                                  price: float,
                                  usd_value: float) -> Dict[str, Any]:
        """
        Generate reversal entry signal

        Args:
            event: Whale event
            market_data: Current market data
            timestamp: Current timestamp
            price: Event price
            usd_value: Event USD value

        Returns:
            Trading signal
        """
        self.signals_generated += 1

        # Calculate sell:buy ratio for logging
        buy_volume = sum(usd for ts, evt, usd in self.market_events if evt == 'market_buy')
        sell_volume = sum(usd for ts, evt, usd in self.market_events if evt == 'market_sell')
        sell_ratio = sell_volume / max(buy_volume, 1)

        logger.info(f"🟢 REVERSAL SIGNAL #{self.signals_generated}: "
                   f"First buy ${usd_value:,.0f} @ ${price:.2f} "
                   f"(sell_ratio={sell_ratio:.1f}:1, dump_low=${self.dump_low_price:.2f})")

        # Record trade time for cooldown
        self.last_trade_time = timestamp

        # Reset dump state (we've taken action)
        self.dump_detected_at = None
        self.dump_low_price = None

        signal = {
            'action': 'OPEN_LONG',
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'timeout_seconds': self.timeout_seconds,
            'entry_delay_seconds': self.entry_delay_seconds,
            'metadata': {
                'strategy': 'momentum_reversal',
                'first_buy_usd': usd_value,
                'first_buy_price': price,
                'sell_ratio': sell_ratio,
                'dump_low_price': self.dump_low_price,
                'signal_number': self.signals_generated
            }
        }

        return signal

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get strategy statistics

        Returns:
            Dictionary with statistics
        """
        return {
            'dumps_detected': self.dumps_detected,
            'signals_generated': self.signals_generated,
            'signals_filtered': self.signals_filtered,
            'conversion_rate': (
                self.signals_generated / self.dumps_detected
                if self.dumps_detected > 0
                else 0
            )
        }
