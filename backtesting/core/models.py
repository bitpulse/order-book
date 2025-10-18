"""
Core data models for backtesting

Defines the fundamental data structures used throughout the backtesting framework.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class OrderSide(Enum):
    """Order side enumeration"""
    BUY = 'BUY'
    SELL = 'SELL'


class OrderType(Enum):
    """Order type enumeration"""
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'


class OrderStatus(Enum):
    """Order status enumeration"""
    PENDING = 'PENDING'
    FILLED = 'FILLED'
    CANCELLED = 'CANCELLED'
    REJECTED = 'REJECTED'


class PositionSide(Enum):
    """Position side enumeration"""
    LONG = 'LONG'
    SHORT = 'SHORT'


@dataclass
class Order:
    """
    Represents a trading order

    Attributes:
        timestamp: When the order was created
        side: BUY or SELL
        order_type: MARKET or LIMIT
        size: Order size in base currency (e.g., BTC)
        price: Limit price (None for market orders)
        stop_loss: Stop loss price (optional)
        take_profit: Take profit price (optional)
        timeout: Auto-cancel time (optional)
        status: Current order status
        filled_price: Actual fill price
        filled_time: When order was filled
        commission: Trading commission paid
        slippage: Price slippage amount
        metadata: Additional order information
    """
    timestamp: datetime
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timeout: Optional[datetime] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_time: Optional[datetime] = None
    commission: float = 0.0
    slippage: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate order on creation"""
        if self.size <= 0:
            raise ValueError(f"Order size must be positive, got {self.size}")
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("Limit orders must have a price")


@dataclass
class Position:
    """
    Represents an open trading position

    Attributes:
        symbol: Trading symbol (e.g., BTC_USDT)
        side: LONG or SHORT
        entry_time: When position was opened
        entry_price: Average entry price
        size: Position size in base currency
        stop_loss: Stop loss price
        take_profit: Take profit price
        timeout: Auto-close time
        unrealized_pnl: Current unrealized P&L
        metadata: Additional position information
    """
    symbol: str
    side: PositionSide
    entry_time: datetime
    entry_price: float
    size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timeout: Optional[datetime] = None
    unrealized_pnl: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_pnl(self, current_price: float):
        """Update unrealized P&L based on current price"""
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:  # SHORT
            self.unrealized_pnl = (self.entry_price - current_price) * self.size

    def should_stop_loss(self, current_price: float) -> bool:
        """Check if stop loss should trigger"""
        if self.stop_loss is None:
            return False
        if self.side == PositionSide.LONG:
            return current_price <= self.stop_loss
        else:  # SHORT
            return current_price >= self.stop_loss

    def should_take_profit(self, current_price: float) -> bool:
        """Check if take profit should trigger"""
        if self.take_profit is None:
            return False
        if self.side == PositionSide.LONG:
            return current_price >= self.take_profit
        else:  # SHORT
            return current_price <= self.take_profit

    def should_timeout(self, current_time: datetime) -> bool:
        """Check if position should close due to timeout"""
        if self.timeout is None:
            return False
        return current_time >= self.timeout


@dataclass
class Trade:
    """
    Represents a completed trade (entry + exit)

    Attributes:
        symbol: Trading symbol
        side: LONG or SHORT
        entry_time: Entry timestamp
        exit_time: Exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        size: Trade size
        pnl: Realized profit/loss (absolute)
        pnl_pct: Realized profit/loss (percentage)
        commission: Total commission paid
        slippage: Total slippage cost
        duration_seconds: Trade duration
        exit_reason: Why the trade closed
        metadata: Additional trade information
    """
    symbol: str
    side: PositionSide
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    commission: float
    slippage: float
    duration_seconds: float
    exit_reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable"""
        return self.pnl > 0

    @property
    def duration_minutes(self) -> float:
        """Get trade duration in minutes"""
        return self.duration_seconds / 60


@dataclass
class BacktestResult:
    """
    Complete backtest results with performance metrics

    Attributes:
        symbol: Trading symbol
        start_time: Backtest start time
        end_time: Backtest end time
        initial_capital: Starting capital
        final_capital: Ending capital
        total_return: Total return percentage
        total_return_abs: Absolute return
        num_trades: Total number of trades
        num_wins: Number of winning trades
        num_losses: Number of losing trades
        win_rate: Percentage of winning trades
        avg_win: Average winning trade P&L
        avg_loss: Average losing trade P&L
        largest_win: Largest winning trade
        largest_loss: Largest losing trade
        profit_factor: Gross profit / Gross loss
        sharpe_ratio: Risk-adjusted return
        sortino_ratio: Downside risk-adjusted return
        max_drawdown: Maximum drawdown percentage
        max_drawdown_duration: Longest drawdown period
        trades: List of all trades
        equity_curve: Time series of portfolio value
        metadata: Additional backtest information
    """
    symbol: str
    start_time: datetime
    end_time: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_abs: float
    num_trades: int
    num_wins: int
    num_losses: int
    win_rate: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: float
    trades: List[Trade]
    equity_curve: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def print_summary(self):
        """Print a formatted summary of backtest results"""
        print("=" * 80)
        print(f"BACKTEST RESULTS: {self.symbol}")
        print("=" * 80)
        print(f"Period: {self.start_time} to {self.end_time}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${self.final_capital:,.2f}")
        print(f"Total Return: {self.total_return:+.2f}% (${self.total_return_abs:+,.2f})")
        print()
        print(f"Total Trades: {self.num_trades}")
        print(f"Wins: {self.num_wins} ({self.win_rate:.1f}%)")
        print(f"Losses: {self.num_losses}")
        print()
        print(f"Average Win: ${self.avg_win:.2f}")
        print(f"Average Loss: ${self.avg_loss:.2f}")
        print(f"Largest Win: ${self.largest_win:.2f}")
        print(f"Largest Loss: ${self.largest_loss:.2f}")
        print()
        print(f"Profit Factor: {self.profit_factor:.2f}")
        print(f"Sharpe Ratio: {self.sharpe_ratio:.2f}")
        print(f"Sortino Ratio: {self.sortino_ratio:.2f}")
        print(f"Max Drawdown: {self.max_drawdown:.2f}%")
        print("=" * 80)

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        return {
            'symbol': self.symbol,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'initial_capital': self.initial_capital,
            'final_capital': self.final_capital,
            'total_return': self.total_return,
            'total_return_abs': self.total_return_abs,
            'num_trades': self.num_trades,
            'num_wins': self.num_wins,
            'num_losses': self.num_losses,
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_duration': self.max_drawdown_duration,
            'num_trades_detail': len(self.trades),
            'metadata': self.metadata
        }
