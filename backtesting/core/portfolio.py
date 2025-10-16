"""
Portfolio - Manages capital, positions, and equity tracking

This module handles all portfolio state during backtesting:
- Cash balance management
- Position tracking (open/closed)
- Equity calculation
- Trade history
- Risk management (position sizing, exposure limits)
"""

from typing import List, Optional, Dict
from datetime import datetime
from loguru import logger

from backtesting.core.models import (
    Position, Trade, Order, OrderSide, PositionSide
)


class Portfolio:
    """
    Manages portfolio state during backtesting

    Tracks:
    - Cash balance
    - Open positions
    - Closed trades
    - Equity curve
    - Performance metrics

    Example:
        portfolio = Portfolio(initial_capital=10000)

        # Open position
        portfolio.open_position(
            symbol='BTC_USDT',
            side=PositionSide.LONG,
            entry_price=42000,
            size=0.1,
            timestamp=datetime.now()
        )

        # Update with current price
        portfolio.update(current_price=42500, timestamp=datetime.now())

        # Close position
        portfolio.close_position(
            exit_price=42500,
            timestamp=datetime.now(),
            reason='take_profit'
        )
    """

    def __init__(self,
                 initial_capital: float,
                 position_size_pct: float = 10.0,
                 max_risk_per_trade_pct: float = 2.0,
                 max_positions: int = 1):
        """
        Initialize portfolio

        Args:
            initial_capital: Starting capital in USD
            position_size_pct: % of capital to use per trade (default: 10%)
            max_risk_per_trade_pct: Max % of capital to risk per trade (default: 2%)
            max_positions: Maximum concurrent positions (default: 1)
        """
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_positions = max_positions

        # Portfolio state
        self.cash = initial_capital
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []

        # Performance tracking
        self.peak_equity = initial_capital
        self.current_drawdown = 0.0
        self.max_drawdown = 0.0

        logger.info(f"Portfolio initialized with ${initial_capital:,.2f}")

    @property
    def equity(self) -> float:
        """Current total equity (cash + position values)"""
        return self.cash + sum(pos.unrealized_pnl for pos in self.positions)

    @property
    def has_open_position(self) -> bool:
        """Check if any positions are open"""
        return len(self.positions) > 0

    @property
    def total_return_pct(self) -> float:
        """Total return percentage"""
        return ((self.equity - self.initial_capital) / self.initial_capital) * 100

    def calculate_position_size(self,
                                entry_price: float,
                                stop_loss_price: Optional[float] = None) -> float:
        """
        Calculate position size based on portfolio rules

        Uses either:
        1. Fixed % of capital (if no stop loss)
        2. Risk-based sizing (if stop loss provided)

        Args:
            entry_price: Entry price for position
            stop_loss_price: Stop loss price (optional)

        Returns:
            Position size in base currency (e.g., BTC)
        """
        # Method 1: Fixed percentage of capital
        capital_to_use = self.equity * (self.position_size_pct / 100)
        size_from_capital = capital_to_use / entry_price

        # Method 2: Risk-based sizing (if stop loss provided)
        if stop_loss_price is not None:
            max_risk_usd = self.equity * (self.max_risk_per_trade_pct / 100)
            risk_per_unit = abs(entry_price - stop_loss_price)

            if risk_per_unit > 0:
                size_from_risk = max_risk_usd / risk_per_unit
                # Use the smaller of the two methods (more conservative)
                size = min(size_from_capital, size_from_risk)
            else:
                size = size_from_capital
        else:
            size = size_from_capital

        return size

    def can_open_position(self) -> bool:
        """
        Check if portfolio can open new position

        Returns:
            True if can open, False otherwise
        """
        if len(self.positions) >= self.max_positions:
            logger.debug(f"Cannot open position: max positions ({self.max_positions}) reached")
            return False

        if self.cash <= 0:
            logger.debug("Cannot open position: no cash available")
            return False

        return True

    def open_position(self,
                      symbol: str,
                      side: PositionSide,
                      entry_price: float,
                      size: float,
                      timestamp: datetime,
                      stop_loss: Optional[float] = None,
                      take_profit: Optional[float] = None,
                      timeout: Optional[datetime] = None,
                      commission: float = 0.0,
                      slippage: float = 0.0,
                      metadata: Optional[Dict] = None) -> Optional[Position]:
        """
        Open a new position

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            entry_price: Entry price
            size: Position size in base currency
            timestamp: Entry timestamp
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            timeout: Position timeout (optional)
            commission: Commission paid
            slippage: Slippage cost
            metadata: Additional position data

        Returns:
            Position object if successful, None otherwise
        """
        if not self.can_open_position():
            return None

        # Calculate position value
        position_value = size * entry_price
        total_cost = position_value + commission + slippage

        if total_cost > self.cash:
            logger.warning(f"Insufficient cash: need ${total_cost:.2f}, have ${self.cash:.2f}")
            return None

        # Deduct from cash
        self.cash -= total_cost

        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            entry_time=timestamp,
            entry_price=entry_price,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timeout=timeout,
            metadata=metadata or {}
        )

        # Store entry costs in metadata
        position.metadata.update({
            'entry_commission': commission,
            'entry_slippage': slippage,
            'entry_total_cost': total_cost
        })

        self.positions.append(position)

        logger.info(
            f"Opened {side.value} position: {size:.4f} {symbol} @ ${entry_price:.2f} "
            f"(cost: ${total_cost:.2f})"
        )

        return position

    def close_position(self,
                       position: Position,
                       exit_price: float,
                       timestamp: datetime,
                       reason: str,
                       commission: float = 0.0,
                       slippage: float = 0.0) -> Optional[Trade]:
        """
        Close an open position and record as trade

        Args:
            position: Position to close
            exit_price: Exit price
            timestamp: Exit timestamp
            reason: Exit reason (take_profit, stop_loss, timeout, manual)
            commission: Exit commission
            slippage: Exit slippage

        Returns:
            Trade object if successful, None otherwise
        """
        if position not in self.positions:
            logger.error("Cannot close position: not found in portfolio")
            return None

        # Calculate P&L
        if position.side == PositionSide.LONG:
            pnl = (exit_price - position.entry_price) * position.size
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * position.size

        # Subtract costs
        entry_commission = position.metadata.get('entry_commission', 0)
        entry_slippage = position.metadata.get('entry_slippage', 0)
        total_commission = entry_commission + commission
        total_slippage = entry_slippage + slippage
        total_costs = total_commission + total_slippage

        pnl_after_costs = pnl - total_costs

        # Calculate percentage
        pnl_pct = (pnl_after_costs / (position.entry_price * position.size)) * 100

        # Return cash (position value + pnl)
        position_value = position.size * exit_price
        self.cash += position_value - commission - slippage

        # Calculate duration
        duration = (timestamp - position.entry_time).total_seconds()

        # Create trade record
        trade = Trade(
            symbol=position.symbol,
            side=position.side,
            entry_time=position.entry_time,
            exit_time=timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,
            pnl=pnl_after_costs,
            pnl_pct=pnl_pct,
            commission=total_commission,
            slippage=total_slippage,
            duration_seconds=duration,
            exit_reason=reason,
            metadata=position.metadata.copy()
        )

        self.trades.append(trade)
        self.positions.remove(position)

        logger.info(
            f"Closed {position.side.value} position: {position.size:.4f} {position.symbol} @ ${exit_price:.2f} "
            f"(P&L: ${pnl_after_costs:+.2f} / {pnl_pct:+.2f}%, reason: {reason})"
        )

        return trade

    def close_all_positions(self,
                           exit_price: float,
                           timestamp: datetime,
                           reason: str = 'close_all',
                           commission: float = 0.0,
                           slippage: float = 0.0) -> List[Trade]:
        """
        Close all open positions

        Args:
            exit_price: Exit price for all positions
            timestamp: Exit timestamp
            reason: Exit reason
            commission: Commission per position
            slippage: Slippage per position

        Returns:
            List of Trade objects
        """
        trades = []
        positions_copy = self.positions.copy()  # Avoid modification during iteration

        for position in positions_copy:
            trade = self.close_position(
                position=position,
                exit_price=exit_price,
                timestamp=timestamp,
                reason=reason,
                commission=commission,
                slippage=slippage
            )
            if trade:
                trades.append(trade)

        return trades

    def update(self, current_price: float, timestamp: datetime):
        """
        Update portfolio state with current market price

        Updates:
        - Unrealized P&L for open positions
        - Equity curve
        - Drawdown metrics

        Args:
            current_price: Current market price
            timestamp: Current timestamp
        """
        # Update unrealized P&L for all positions
        for position in self.positions:
            position.update_pnl(current_price)

        # Update equity curve
        current_equity = self.equity
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': current_equity,
            'cash': self.cash,
            'unrealized_pnl': sum(pos.unrealized_pnl for pos in self.positions),
            'num_positions': len(self.positions)
        })

        # Update drawdown
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = ((self.peak_equity - current_equity) / self.peak_equity) * 100
            if self.current_drawdown > self.max_drawdown:
                self.max_drawdown = self.current_drawdown

    def get_position_for_symbol(self, symbol: str) -> Optional[Position]:
        """
        Get open position for a specific symbol

        Args:
            symbol: Trading symbol

        Returns:
            Position if found, None otherwise
        """
        for position in self.positions:
            if position.symbol == symbol:
                return position
        return None

    def get_summary(self) -> Dict:
        """
        Get portfolio summary statistics

        Returns:
            Dictionary with summary metrics
        """
        return {
            'initial_capital': self.initial_capital,
            'current_cash': self.cash,
            'current_equity': self.equity,
            'total_return_pct': self.total_return_pct,
            'num_open_positions': len(self.positions),
            'num_closed_trades': len(self.trades),
            'max_drawdown': self.max_drawdown,
            'peak_equity': self.peak_equity
        }
