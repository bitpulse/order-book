"""
ExecutionSimulator - Realistic order execution modeling

This module simulates realistic order execution including:
- Trading fees (maker/taker)
- Price slippage
- Order book depth impact
- Execution delays

Critical for accurate backtesting!
"""

from typing import Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger

from backtesting.core.models import Order, OrderSide, OrderType


class ExecutionSimulator:
    """
    Simulates realistic order execution for backtesting

    Models:
    - Trading fees (MEXC: 0.02% maker, 0.06% taker)
    - Slippage (market impact)
    - Execution delays
    - Partial fills (future)

    Example:
        sim = ExecutionSimulator(
            maker_fee=0.0002,
            taker_fee=0.0006,
            slippage_model='fixed',
            slippage_pct=0.02
        )

        filled_price, commission, slippage_cost = sim.simulate_market_buy(
            order_price=42000,
            order_size=0.1,
            timestamp=datetime.now()
        )
    """

    def __init__(self,
                 maker_fee_pct: float = 0.02,  # 0.02% maker fee
                 taker_fee_pct: float = 0.06,  # 0.06% taker fee
                 slippage_model: str = 'fixed',  # 'fixed', 'volume_based', or 'orderbook'
                 slippage_pct: float = 0.02,  # 0.02% base slippage
                 execution_delay_ms: int = 100):  # 100ms execution delay
        """
        Initialize execution simulator

        Args:
            maker_fee_pct: Maker fee percentage (default: 0.02% = MEXC maker)
            taker_fee_pct: Taker fee percentage (default: 0.06% = MEXC taker)
            slippage_model: Slippage calculation method
            slippage_pct: Base slippage percentage
            execution_delay_ms: Execution delay in milliseconds
        """
        self.maker_fee = maker_fee_pct / 100
        self.taker_fee = taker_fee_pct / 100
        self.slippage_model = slippage_model
        self.slippage_pct = slippage_pct / 100
        self.execution_delay = timedelta(milliseconds=execution_delay_ms)

        logger.info(
            f"ExecutionSimulator initialized: maker={maker_fee_pct}%, "
            f"taker={taker_fee_pct}%, slippage={slippage_pct}% ({slippage_model})"
        )

    def simulate_market_buy(self,
                           order_price: float,
                           order_size: float,
                           timestamp: datetime,
                           current_spread: float = 0.0) -> Tuple[float, float, float]:
        """
        Simulate market buy order execution

        Market orders:
        - Fill immediately at ask price
        - Pay taker fee
        - Experience slippage (eat through order book)

        Args:
            order_price: Current mid/mark price
            order_size: Order size in base currency
            timestamp: Order timestamp
            current_spread: Current bid-ask spread (optional)

        Returns:
            Tuple of (filled_price, commission, slippage_cost)
        """
        # Market buy fills at ask (mid + half spread)
        if current_spread > 0:
            base_fill_price = order_price + (current_spread / 2)
        else:
            base_fill_price = order_price

        # Calculate slippage
        slippage_amount = self._calculate_slippage(
            price=base_fill_price,
            size=order_size,
            side='buy'
        )

        # Final fill price (worse for buyer)
        filled_price = base_fill_price + slippage_amount

        # Calculate commission (on notional value)
        notional = filled_price * order_size
        commission = notional * self.taker_fee

        # Total slippage cost
        slippage_cost = slippage_amount * order_size

        logger.debug(
            f"Market BUY: {order_size:.4f} @ ${filled_price:.2f} "
            f"(comm: ${commission:.2f}, slip: ${slippage_cost:.2f})"
        )

        return filled_price, commission, slippage_cost

    def simulate_market_sell(self,
                            order_price: float,
                            order_size: float,
                            timestamp: datetime,
                            current_spread: float = 0.0) -> Tuple[float, float, float]:
        """
        Simulate market sell order execution

        Market orders:
        - Fill immediately at bid price
        - Pay taker fee
        - Experience slippage (eat through order book)

        Args:
            order_price: Current mid/mark price
            order_size: Order size in base currency
            timestamp: Order timestamp
            current_spread: Current bid-ask spread (optional)

        Returns:
            Tuple of (filled_price, commission, slippage_cost)
        """
        # Market sell fills at bid (mid - half spread)
        if current_spread > 0:
            base_fill_price = order_price - (current_spread / 2)
        else:
            base_fill_price = order_price

        # Calculate slippage
        slippage_amount = self._calculate_slippage(
            price=base_fill_price,
            size=order_size,
            side='sell'
        )

        # Final fill price (worse for seller)
        filled_price = base_fill_price - slippage_amount

        # Calculate commission (on notional value)
        notional = filled_price * order_size
        commission = notional * self.taker_fee

        # Total slippage cost
        slippage_cost = slippage_amount * order_size

        logger.debug(
            f"Market SELL: {order_size:.4f} @ ${filled_price:.2f} "
            f"(comm: ${commission:.2f}, slip: ${slippage_cost:.2f})"
        )

        return filled_price, commission, slippage_cost

    def _calculate_slippage(self,
                           price: float,
                           size: float,
                           side: str) -> float:
        """
        Calculate slippage amount based on model

        Args:
            price: Base price
            size: Order size
            side: 'buy' or 'sell'

        Returns:
            Slippage amount (absolute price units)
        """
        if self.slippage_model == 'fixed':
            # Simple fixed percentage slippage
            return price * self.slippage_pct

        elif self.slippage_model == 'volume_based':
            # Slippage increases with order size
            # Larger orders = more slippage
            # Formula: base_slippage * (1 + size_factor)
            size_factor = min(size * 0.1, 2.0)  # Cap at 2x multiplier
            return price * self.slippage_pct * (1 + size_factor)

        elif self.slippage_model == 'orderbook':
            # Simulate walking through order book levels
            # This would require actual order book depth data
            # For now, use volume-based as approximation
            logger.warning("Order book slippage model not implemented, using volume-based")
            size_factor = min(size * 0.1, 2.0)
            return price * self.slippage_pct * (1 + size_factor)

        else:
            logger.warning(f"Unknown slippage model: {self.slippage_model}, using fixed")
            return price * self.slippage_pct

    def simulate_limit_order(self,
                            order: Order,
                            current_price: float,
                            timestamp: datetime) -> Optional[Tuple[float, float, float]]:
        """
        Simulate limit order execution

        Limit orders:
        - Only fill if price reaches limit
        - Pay maker fee (better than taker)
        - Minimal slippage

        Args:
            order: Limit order
            current_price: Current market price
            timestamp: Current timestamp

        Returns:
            Tuple of (filled_price, commission, slippage) if filled, None otherwise
        """
        # Check if limit price reached
        if order.side == OrderSide.BUY:
            if current_price <= order.price:
                filled = True
                filled_price = order.price
            else:
                return None
        else:  # SELL
            if current_price >= order.price:
                filled = True
                filled_price = order.price
            else:
                return None

        # Maker fee (lower than taker)
        notional = filled_price * order.size
        commission = notional * self.maker_fee

        # Minimal slippage for limit orders (queue position)
        slippage_cost = filled_price * order.size * (self.slippage_pct * 0.1)  # 10% of base slippage

        logger.debug(
            f"Limit {order.side.value}: {order.size:.4f} @ ${filled_price:.2f} "
            f"(comm: ${commission:.2f})"
        )

        return filled_price, commission, slippage_cost

    def get_execution_time(self, order_time: datetime) -> datetime:
        """
        Calculate actual execution time with delay

        Args:
            order_time: When order was submitted

        Returns:
            Actual execution timestamp
        """
        return order_time + self.execution_delay

    def calculate_total_cost(self,
                            entry_price: float,
                            entry_size: float,
                            entry_commission: float,
                            entry_slippage: float,
                            exit_price: float,
                            exit_commission: float,
                            exit_slippage: float) -> float:
        """
        Calculate total trading cost for a round trip

        Args:
            entry_price: Entry fill price
            entry_size: Position size
            entry_commission: Entry commission
            entry_slippage: Entry slippage cost
            exit_price: Exit fill price
            exit_commission: Exit commission
            exit_slippage: Exit slippage cost

        Returns:
            Total cost in USD
        """
        return entry_commission + entry_slippage + exit_commission + exit_slippage

    def get_effective_entry_price(self,
                                  base_price: float,
                                  commission: float,
                                  slippage: float,
                                  size: float,
                                  side: str) -> float:
        """
        Calculate effective entry price including all costs

        Args:
            base_price: Base fill price
            commission: Commission paid
            slippage: Slippage cost
            size: Position size
            side: 'buy' or 'sell'

        Returns:
            Effective price (breakeven point)
        """
        total_cost = commission + slippage

        if side == 'buy':
            # For long: need price to rise to cover costs
            return base_price + (total_cost / size)
        else:  # sell/short
            # For short: need price to fall to cover costs
            return base_price - (total_cost / size)

    def estimate_roundtrip_cost(self,
                               price: float,
                               size: float) -> Dict:
        """
        Estimate total cost for a round-trip trade (entry + exit)

        Useful for:
        - Pre-trade cost analysis
        - Minimum profit target calculation
        - Strategy optimization

        Args:
            price: Current price
            size: Planned position size

        Returns:
            Dictionary with cost breakdown
        """
        # Simulate entry (market buy)
        entry_price, entry_comm, entry_slip = self.simulate_market_buy(
            order_price=price,
            order_size=size,
            timestamp=datetime.now()
        )

        # Simulate exit (market sell at same price - worst case)
        exit_price, exit_comm, exit_slip = self.simulate_market_sell(
            order_price=price,
            order_size=size,
            timestamp=datetime.now()
        )

        total_cost = entry_comm + entry_slip + exit_comm + exit_slip
        cost_pct = (total_cost / (price * size)) * 100

        return {
            'entry_commission': entry_comm,
            'entry_slippage': entry_slip,
            'exit_commission': exit_comm,
            'exit_slippage': exit_slip,
            'total_cost': total_cost,
            'cost_pct': cost_pct,
            'breakeven_move_pct': cost_pct  # Price needs to move this much to breakeven
        }


# Convenience functions for quick calculations

def calculate_mexc_fees(notional_usd: float, fee_type: str = 'taker') -> float:
    """
    Calculate MEXC trading fees

    Args:
        notional_usd: Trade value in USD
        fee_type: 'maker' or 'taker'

    Returns:
        Fee amount in USD
    """
    if fee_type == 'maker':
        return notional_usd * 0.0002  # 0.02%
    else:  # taker
        return notional_usd * 0.0006  # 0.06%


def estimate_min_profit_target(entry_price: float,
                               size: float,
                               total_costs: float) -> float:
    """
    Calculate minimum price movement needed for profit

    Args:
        entry_price: Entry price
        size: Position size
        total_costs: Total trading costs (commission + slippage)

    Returns:
        Minimum profit target in % to breakeven
    """
    cost_per_unit = total_costs / size
    breakeven_price = entry_price + cost_per_unit
    min_move_pct = ((breakeven_price - entry_price) / entry_price) * 100
    return min_move_pct
