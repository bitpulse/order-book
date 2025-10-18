"""
MetricsCalculator - Performance metrics and statistics

Calculates comprehensive backtest performance metrics including:
- Returns (absolute, percentage, annualized)
- Risk metrics (Sharpe, Sortino, drawdown)
- Trade statistics (win rate, profit factor)
- Advanced metrics (Calmar ratio, recovery factor)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from loguru import logger

from backtesting.core.models import Trade, BacktestResult


class MetricsCalculator:
    """
    Calculates performance metrics for backtest results

    Example:
        calculator = MetricsCalculator()

        result = calculator.calculate(
            trades=trades_list,
            equity_curve=equity_data,
            initial_capital=10000,
            start_time=start_dt,
            end_time=end_dt,
            symbol='BTC_USDT'
        )

        result.print_summary()
    """

    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize metrics calculator

        Args:
            risk_free_rate: Annual risk-free rate for Sharpe calculation (default: 2%)
        """
        self.risk_free_rate = risk_free_rate

    def calculate(self,
                  trades: List[Trade],
                  equity_curve: List[Dict],
                  initial_capital: float,
                  start_time: datetime,
                  end_time: datetime,
                  symbol: str,
                  metadata: Optional[Dict] = None) -> BacktestResult:
        """
        Calculate comprehensive backtest metrics

        Args:
            trades: List of completed trades
            equity_curve: Time series of portfolio equity
            initial_capital: Starting capital
            start_time: Backtest start time
            end_time: Backtest end time
            symbol: Trading symbol
            metadata: Additional metadata

        Returns:
            BacktestResult with all metrics
        """
        logger.info(f"Calculating metrics for {len(trades)} trades")

        # Basic metrics
        final_capital = equity_curve[-1]['equity'] if equity_curve else initial_capital
        total_return_abs = final_capital - initial_capital
        total_return_pct = (total_return_abs / initial_capital) * 100

        # Trade statistics
        num_trades = len(trades)
        winning_trades = [t for t in trades if t.is_winner]
        losing_trades = [t for t in trades if not t.is_winner]
        num_wins = len(winning_trades)
        num_losses = len(losing_trades)
        win_rate = (num_wins / num_trades * 100) if num_trades > 0 else 0

        # P&L statistics
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0
        largest_win = max([t.pnl for t in winning_trades]) if winning_trades else 0
        largest_loss = min([t.pnl for t in losing_trades]) if losing_trades else 0

        # Profit factor
        gross_profit = sum([t.pnl for t in winning_trades]) if winning_trades else 0
        gross_loss = abs(sum([t.pnl for t in losing_trades])) if losing_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Risk metrics
        sharpe_ratio = self._calculate_sharpe_ratio(equity_curve, start_time, end_time)
        sortino_ratio = self._calculate_sortino_ratio(equity_curve, start_time, end_time)
        max_drawdown, max_dd_duration = self._calculate_max_drawdown(equity_curve)

        # Create result
        result = BacktestResult(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=total_return_pct,
            total_return_abs=total_return_abs,
            num_trades=num_trades,
            num_wins=num_wins,
            num_losses=num_losses,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            trades=trades,
            equity_curve=equity_curve,
            metadata=metadata or {}
        )

        logger.info(
            f"Metrics calculated: Return={total_return_pct:.2f}%, "
            f"Sharpe={sharpe_ratio:.2f}, Max DD={max_drawdown:.2f}%"
        )

        return result

    def _calculate_sharpe_ratio(self,
                                equity_curve: List[Dict],
                                start_time: datetime,
                                end_time: datetime) -> float:
        """
        Calculate Sharpe ratio (risk-adjusted return)

        Sharpe = (Return - RiskFreeRate) / StdDev(Returns)

        Args:
            equity_curve: Portfolio equity time series
            start_time: Start time
            end_time: End time

        Returns:
            Sharpe ratio (annualized)
        """
        if len(equity_curve) < 2:
            return 0.0

        # Extract equity values
        equity_values = [point['equity'] for point in equity_curve]

        # Calculate returns
        returns = np.diff(equity_values) / equity_values[:-1]

        if len(returns) == 0:
            return 0.0

        # Mean and std of returns
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        # Calculate period (for annualization)
        duration_days = (end_time - start_time).days
        if duration_days == 0:
            return 0.0

        # Annualize
        periods_per_year = 365 / duration_days
        annualized_return = mean_return * periods_per_year
        annualized_std = std_return * np.sqrt(periods_per_year)
        annualized_rf = self.risk_free_rate

        # Sharpe ratio
        sharpe = (annualized_return - annualized_rf) / annualized_std

        return sharpe

    def _calculate_sortino_ratio(self,
                                 equity_curve: List[Dict],
                                 start_time: datetime,
                                 end_time: datetime) -> float:
        """
        Calculate Sortino ratio (downside risk-adjusted return)

        Like Sharpe, but only considers downside volatility

        Args:
            equity_curve: Portfolio equity time series
            start_time: Start time
            end_time: End time

        Returns:
            Sortino ratio (annualized)
        """
        if len(equity_curve) < 2:
            return 0.0

        # Extract equity values
        equity_values = [point['equity'] for point in equity_curve]

        # Calculate returns
        returns = np.diff(equity_values) / equity_values[:-1]

        if len(returns) == 0:
            return 0.0

        # Mean return
        mean_return = np.mean(returns)

        # Downside deviation (only negative returns)
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return float('inf')  # No downside = infinite Sortino

        downside_std = np.std(downside_returns)

        if downside_std == 0:
            return 0.0

        # Calculate period (for annualization)
        duration_days = (end_time - start_time).days
        if duration_days == 0:
            return 0.0

        # Annualize
        periods_per_year = 365 / duration_days
        annualized_return = mean_return * periods_per_year
        annualized_downside_std = downside_std * np.sqrt(periods_per_year)
        annualized_rf = self.risk_free_rate

        # Sortino ratio
        sortino = (annualized_return - annualized_rf) / annualized_downside_std

        return sortino

    def _calculate_max_drawdown(self,
                                equity_curve: List[Dict]) -> tuple[float, float]:
        """
        Calculate maximum drawdown and duration

        Drawdown = (Peak - Trough) / Peak

        Args:
            equity_curve: Portfolio equity time series

        Returns:
            Tuple of (max_drawdown_pct, max_duration_days)
        """
        if len(equity_curve) < 2:
            return 0.0, 0.0

        # Extract equity and timestamps
        equity_values = np.array([point['equity'] for point in equity_curve])
        timestamps = [point['timestamp'] for point in equity_curve]

        # Calculate running maximum (peak)
        running_max = np.maximum.accumulate(equity_values)

        # Calculate drawdown at each point
        drawdowns = (running_max - equity_values) / running_max * 100

        # Maximum drawdown
        max_dd = np.max(drawdowns)

        # Calculate max drawdown duration
        max_dd_duration_days = 0.0
        in_drawdown = False
        dd_start_time = None

        for i, dd in enumerate(drawdowns):
            if dd > 0 and not in_drawdown:
                # Drawdown started
                in_drawdown = True
                dd_start_time = timestamps[i]
            elif dd == 0 and in_drawdown:
                # Drawdown ended (new peak)
                in_drawdown = False
                if dd_start_time:
                    duration = (timestamps[i] - dd_start_time).total_seconds() / 86400  # days
                    max_dd_duration_days = max(max_dd_duration_days, duration)

        # Check if still in drawdown at end
        if in_drawdown and dd_start_time:
            duration = (timestamps[-1] - dd_start_time).total_seconds() / 86400
            max_dd_duration_days = max(max_dd_duration_days, duration)

        return max_dd, max_dd_duration_days

    def calculate_trade_statistics(self, trades: List[Trade]) -> Dict:
        """
        Calculate detailed trade statistics

        Args:
            trades: List of trades

        Returns:
            Dictionary with trade statistics
        """
        if not trades:
            return {
                'total_trades': 0,
                'avg_duration_minutes': 0,
                'avg_pnl': 0,
                'median_pnl': 0,
                'best_trade': 0,
                'worst_trade': 0
            }

        pnls = [t.pnl for t in trades]
        durations = [t.duration_minutes for t in trades]

        return {
            'total_trades': len(trades),
            'avg_duration_minutes': np.mean(durations),
            'median_duration_minutes': np.median(durations),
            'min_duration_minutes': np.min(durations),
            'max_duration_minutes': np.max(durations),
            'avg_pnl': np.mean(pnls),
            'median_pnl': np.median(pnls),
            'std_pnl': np.std(pnls),
            'best_trade': max(pnls),
            'worst_trade': min(pnls),
            'total_pnl': sum(pnls)
        }

    def calculate_monthly_returns(self,
                                  equity_curve: List[Dict],
                                  initial_capital: float) -> pd.DataFrame:
        """
        Calculate monthly returns for heatmap visualization

        Args:
            equity_curve: Portfolio equity time series
            initial_capital: Starting capital

        Returns:
            DataFrame with monthly returns
        """
        if not equity_curve:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(equity_curve)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')

        # Resample to month-end
        monthly = df['equity'].resample('M').last()

        # Calculate monthly returns
        monthly_returns = monthly.pct_change() * 100

        # Format as calendar
        monthly_returns_df = pd.DataFrame({
            'Year': monthly_returns.index.year,
            'Month': monthly_returns.index.month,
            'Return': monthly_returns.values
        })

        return monthly_returns_df

    def calculate_win_loss_streaks(self, trades: List[Trade]) -> Dict:
        """
        Calculate winning and losing streaks

        Args:
            trades: List of trades

        Returns:
            Dictionary with streak statistics
        """
        if not trades:
            return {
                'max_win_streak': 0,
                'max_loss_streak': 0,
                'current_streak': 0,
                'current_streak_type': None
            }

        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0
        current_streak_type = None

        for trade in trades:
            if trade.is_winner:
                if current_streak_type == 'win':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = 'win'
                max_win_streak = max(max_win_streak, current_streak)
            else:
                if current_streak_type == 'loss':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = 'loss'
                max_loss_streak = max(max_loss_streak, current_streak)

        return {
            'max_win_streak': max_win_streak,
            'max_loss_streak': max_loss_streak,
            'current_streak': current_streak,
            'current_streak_type': current_streak_type
        }
