"""
BacktestEngine - Main event-driven backtesting loop

This is the core engine that orchestrates the entire backtesting process:
- Loads historical data
- Iterates through time tick-by-tick
- Calls strategy methods to generate signals
- Simulates order execution
- Manages portfolio state
- Calculates performance metrics
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

from backtesting.core.models import (
    Order, Position, Trade, BacktestResult,
    OrderSide, OrderType, PositionSide
)
from backtesting.core.data_loader import DataLoader
from backtesting.core.portfolio import Portfolio
from backtesting.core.execution import ExecutionSimulator
from backtesting.core.metrics import MetricsCalculator


class BacktestEngine:
    """
    Event-driven backtesting engine

    Simulates trading by processing historical data chronologically,
    allowing strategies to react to market events in real-time.

    Example:
        from backtesting import BacktestEngine
        from backtesting.strategies import WhaleFollowingStrategy

        engine = BacktestEngine(
            strategy=WhaleFollowingStrategy(),
            initial_capital=10000
        )

        result = engine.run(
            symbol='BTC_USDT',
            start='2025-09-01',
            end='2025-10-01'
        )

        result.print_summary()
    """

    def __init__(self,
                 strategy: Any,  # BaseStrategy type (will be defined later)
                 initial_capital: float = 10000,
                 data_loader: Optional[DataLoader] = None,
                 execution_simulator: Optional[ExecutionSimulator] = None,
                 position_size_pct: float = 10.0,
                 max_risk_per_trade_pct: float = 2.0,
                 max_positions: int = 1):
        """
        Initialize backtesting engine

        Args:
            strategy: Trading strategy instance (must implement on_tick, on_whale_event)
            initial_capital: Starting capital in USD
            data_loader: DataLoader instance (creates new if None)
            execution_simulator: ExecutionSimulator instance (creates new if None)
            position_size_pct: % of capital per trade (default: 10%)
            max_risk_per_trade_pct: Max % risk per trade (default: 2%)
            max_positions: Max concurrent positions (default: 1)
        """
        self.strategy = strategy
        self.initial_capital = initial_capital

        # Initialize components
        self.data_loader = data_loader or DataLoader()
        self.execution_simulator = execution_simulator or ExecutionSimulator()

        # Portfolio will be reset on each run
        self.portfolio: Optional[Portfolio] = None

        # Portfolio configuration
        self.position_size_pct = position_size_pct
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_positions = max_positions

        # Backtest state
        self.current_time: Optional[datetime] = None
        self.current_price: Optional[float] = None
        self.data: Optional[pd.DataFrame] = None

        logger.info(f"BacktestEngine initialized with {strategy.__class__.__name__}")

    def run(self,
            symbol: str,
            start: str,
            end: str,
            min_whale_usd: float = 100000,
            window_size: str = '1s') -> BacktestResult:
        """
        Run backtest on historical data

        Args:
            symbol: Trading symbol (e.g., 'BTC_USDT')
            start: Start time (ISO format or datetime)
            end: End time (ISO format or datetime)
            min_whale_usd: Minimum whale event size in USD
            window_size: Time window for aggregation ('1s', '1min', etc.)

        Returns:
            BacktestResult with comprehensive performance metrics
        """
        logger.info(f"Starting backtest: {symbol} from {start} to {end}")

        # Reset portfolio
        self.portfolio = Portfolio(
            initial_capital=self.initial_capital,
            position_size_pct=self.position_size_pct,
            max_risk_per_trade_pct=self.max_risk_per_trade_pct,
            max_positions=self.max_positions
        )

        # Initialize strategy
        if hasattr(self.strategy, 'initialize'):
            self.strategy.initialize(self.portfolio, self.execution_simulator)

        # Load data
        logger.info("Loading historical data...")
        prices = self.data_loader.get_price_data(symbol, start, end)
        whales = self.data_loader.get_whale_events(symbol, start, end, min_usd=min_whale_usd)

        logger.info(f"Loaded {len(prices):,} price ticks and {len(whales):,} whale events")

        # Create unified timeline
        self.data = self.data_loader.create_unified_timeline(prices, whales, window_size=window_size)
        logger.info(f"Created unified timeline with {len(self.data):,} data points")

        # Main event loop
        start_time = datetime.now()
        self._run_event_loop(symbol, whales)
        duration = (datetime.now() - start_time).total_seconds()

        logger.info(f"Backtest completed in {duration:.2f}s")

        # Calculate metrics
        result = self._calculate_results(symbol, start, end)

        return result

    def _run_event_loop(self, symbol: str, whale_events: pd.DataFrame):
        """
        Main event loop - iterate through time chronologically

        Args:
            symbol: Trading symbol
            whale_events: DataFrame of whale events with timestamps
        """
        tick_count = 0
        whale_event_count = 0

        # Pre-sort whale events by timestamp for efficient matching
        whale_events = whale_events.sort_values('timestamp').reset_index(drop=True)
        whale_idx = 0
        whale_len = len(whale_events)

        for idx, row in self.data.iterrows():
            self.current_time = idx  # DataFrame index is timestamp
            self.current_price = row['mid_price']

            # Update portfolio with current price
            self.portfolio.update(self.current_price, self.current_time)

            # Process whale events that occurred at this timestamp (within 100ms window)
            time_window = timedelta(milliseconds=100)

            while whale_idx < whale_len:
                whale_ts = whale_events.iloc[whale_idx]['timestamp']

                # If whale event is too far in past, skip it
                if whale_ts < self.current_time - time_window:
                    whale_idx += 1
                    continue

                # If whale event is in current window, process it
                if whale_ts <= self.current_time + time_window:
                    whale_event = whale_events.iloc[whale_idx]
                    whale_event_count += 1
                    self._process_whale_event(symbol, whale_event, row)
                    whale_idx += 1
                else:
                    # Whale event is in future, break and wait for next tick
                    break

            # Call strategy's on_tick method
            if hasattr(self.strategy, 'on_tick'):
                self.strategy.on_tick(self.current_time, row, self.portfolio)

            # Check exit conditions for all open positions
            self._check_exits()

            tick_count += 1

            # Progress logging (every 100k ticks)
            if tick_count % 100000 == 0:
                logger.debug(f"Processed {tick_count:,} ticks, {whale_event_count} whale events, "
                           f"{len(self.portfolio.positions)} open positions, "
                           f"{len(self.portfolio.trades)} completed trades")

        # Close any remaining positions at final price
        self._close_all_positions("backtest_end")

        logger.info(f"Event loop complete: {tick_count:,} ticks, {whale_event_count} whale events processed")

    def _process_whale_event(self, symbol: str, whale_event: pd.Series, market_data: pd.Series):
        """
        Process a whale event and execute strategy logic

        Args:
            symbol: Trading symbol
            whale_event: Whale event data
            market_data: Current market data
        """
        # Call strategy's on_whale_event method
        if not hasattr(self.strategy, 'on_whale_event'):
            return

        signal = self.strategy.on_whale_event(whale_event, market_data, self.portfolio)

        if signal is None:
            return

        # Execute signal
        self._execute_signal(symbol, signal)

    def _execute_signal(self, symbol: str, signal: Dict[str, Any]):
        """
        Execute a trading signal from the strategy

        Args:
            symbol: Trading symbol
            signal: Signal dictionary with keys:
                - 'action': 'OPEN_LONG', 'OPEN_SHORT', 'CLOSE_LONG', 'CLOSE_SHORT'
                - 'stop_loss_pct': Optional stop loss percentage
                - 'take_profit_pct': Optional take profit percentage
                - 'timeout_seconds': Optional timeout in seconds
                - 'size': Optional position size override
                - 'metadata': Optional metadata dict
        """
        action = signal.get('action')

        if action in ['OPEN_LONG', 'OPEN_SHORT']:
            self._open_position(symbol, signal)
        elif action in ['CLOSE_LONG', 'CLOSE_SHORT']:
            self._close_positions_by_side(signal)

    def _open_position(self, symbol: str, signal: Dict[str, Any]):
        """
        Open a new position based on signal

        Args:
            symbol: Trading symbol
            signal: Signal parameters
        """
        action = signal['action']
        side = PositionSide.LONG if action == 'OPEN_LONG' else PositionSide.SHORT

        # Check position limits
        if len(self.portfolio.positions) >= self.max_positions:
            logger.debug(f"Position limit reached ({self.max_positions}), skipping signal")
            return

        # Calculate position size
        stop_loss_pct = signal.get('stop_loss_pct', 0.015)  # Default 1.5%

        if 'size' in signal:
            size = signal['size']
        else:
            # Calculate stop loss price
            if side == PositionSide.LONG:
                stop_loss_price = self.current_price * (1 - stop_loss_pct)
            else:
                stop_loss_price = self.current_price * (1 + stop_loss_pct)

            size = self.portfolio.calculate_position_size(
                entry_price=self.current_price,
                stop_loss_price=stop_loss_price
            )

        if size is None or size <= 0:
            logger.debug("Insufficient capital for position")
            return

        # Simulate execution
        if side == PositionSide.LONG:
            fill_price, commission, slippage = self.execution_simulator.simulate_market_buy(
                order_price=self.current_price,
                order_size=size,
                timestamp=self.current_time
            )
        else:
            fill_price, commission, slippage = self.execution_simulator.simulate_market_sell(
                order_price=self.current_price,
                order_size=size,
                timestamp=self.current_time
            )

        # Calculate stop loss and take profit prices
        stop_loss = None
        take_profit = None

        if 'stop_loss_pct' in signal:
            if side == PositionSide.LONG:
                stop_loss = fill_price * (1 - signal['stop_loss_pct'])
            else:
                stop_loss = fill_price * (1 + signal['stop_loss_pct'])

        if 'take_profit_pct' in signal:
            if side == PositionSide.LONG:
                take_profit = fill_price * (1 + signal['take_profit_pct'])
            else:
                take_profit = fill_price * (1 - signal['take_profit_pct'])

        # Calculate timeout
        timeout = None
        if 'timeout_seconds' in signal:
            timeout = self.current_time + timedelta(seconds=signal['timeout_seconds'])

        # Open position in portfolio
        position = self.portfolio.open_position(
            symbol=symbol,
            side=side,
            entry_price=fill_price,
            size=size,
            timestamp=self.current_time,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timeout=timeout,
            commission=commission,
            slippage=slippage,
            metadata=signal.get('metadata', {})
        )

        if position:
            logger.debug(f"Opened {side.value} position: size={size:.6f} @ ${fill_price:.2f}")

    def _close_positions_by_side(self, signal: Dict[str, Any]):
        """
        Close positions matching signal side

        Args:
            signal: Signal with 'action' key
        """
        action = signal['action']
        target_side = PositionSide.LONG if 'LONG' in action else PositionSide.SHORT

        positions_to_close = [p for p in self.portfolio.positions if p.side == target_side]

        for position in positions_to_close:
            self._close_position(position, reason="signal_close")

    def _check_exits(self):
        """
        Check all open positions for exit conditions
        (stop loss, take profit, timeout)
        """
        positions_to_close = []

        for position in self.portfolio.positions:
            # Check stop loss
            if position.should_stop_loss(self.current_price):
                positions_to_close.append((position, 'stop_loss'))
                continue

            # Check take profit
            if position.should_take_profit(self.current_price):
                positions_to_close.append((position, 'take_profit'))
                continue

            # Check timeout
            if position.should_timeout(self.current_time):
                positions_to_close.append((position, 'timeout'))
                continue

        # Close positions
        for position, reason in positions_to_close:
            self._close_position(position, reason)

    def _close_position(self, position: Position, reason: str):
        """
        Close a specific position

        Args:
            position: Position to close
            reason: Reason for closing
        """
        # Simulate execution
        if position.side == PositionSide.LONG:
            fill_price, commission, slippage = self.execution_simulator.simulate_market_sell(
                order_price=self.current_price,
                order_size=position.size,
                timestamp=self.current_time
            )
        else:
            fill_price, commission, slippage = self.execution_simulator.simulate_market_buy(
                order_price=self.current_price,
                order_size=position.size,
                timestamp=self.current_time
            )

        # Close in portfolio
        trade = self.portfolio.close_position(
            position=position,
            exit_price=fill_price,
            timestamp=self.current_time,
            reason=reason,
            commission=commission,
            slippage=slippage
        )

        if trade:
            logger.debug(f"Closed {position.side.value} position: "
                        f"P&L=${trade.pnl:.2f} ({trade.pnl_pct:.2f}%) - {reason}")

    def _close_all_positions(self, reason: str):
        """
        Close all open positions

        Args:
            reason: Reason for closing all positions
        """
        positions = list(self.portfolio.positions)  # Copy to avoid modification during iteration

        for position in positions:
            self._close_position(position, reason)

        if len(positions) > 0:
            logger.info(f"Closed {len(positions)} remaining positions: {reason}")

    def _calculate_results(self, symbol: str, start: str, end: str) -> BacktestResult:
        """
        Calculate final backtest results

        Args:
            symbol: Trading symbol
            start: Start time
            end: End time

        Returns:
            BacktestResult with comprehensive metrics
        """
        calculator = MetricsCalculator()

        result = calculator.calculate(
            trades=self.portfolio.trades,
            equity_curve=self.portfolio.equity_curve,
            initial_capital=self.initial_capital,
            start_time=self.data.index[0] if len(self.data) > 0 else datetime.now(),
            end_time=self.data.index[-1] if len(self.data) > 0 else datetime.now(),
            symbol=symbol
        )

        return result
