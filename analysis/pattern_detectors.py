"""
Pattern Detection Modules

Detects specific order book patterns:
- Iceberg orders (hidden large orders)
- Spoofing (fake orders for manipulation)
- Order layering
- Volume clustering

Research References:
- Bookmap: "Advanced Order Flow Trading: Spotting Hidden Liquidity & Iceberg Orders"
- Justin Trading: "How to Spot Iceberg Orders and Spoofing Activity"
"""

import pandas as pd
from datetime import timedelta
from typing import List
from loguru import logger

try:
    from .data_models import PatternDetection
except ImportError:
    from data_models import PatternDetection


class IcebergDetector:
    """
    Detect iceberg orders (hidden large institutional orders)

    Characteristics:
    - Rapid volume replenishment at same price after fills
    - Price stagnation despite heavy trading volume
    - Multiple decrease events followed by increases
    """

    def __init__(self, min_refills: int = 3, time_window: int = 30):
        """
        Args:
            min_refills: Minimum refill cycles to qualify as iceberg
            time_window: Maximum time window in seconds
        """
        self.min_refills = min_refills
        self.time_window = time_window

    def detect(self, events_df: pd.DataFrame) -> List[PatternDetection]:
        """
        Detect iceberg orders

        Args:
            events_df: DataFrame with whale events

        Returns:
            List of detected iceberg patterns
        """
        logger.info("Detecting iceberg orders...")

        if events_df.empty:
            return []

        icebergs = []
        df = events_df.copy()

        # Group by price level
        for price in df['price'].unique():
            price_events = df[df['price'] == price].sort_values('time')

            if len(price_events) < self.min_refills:
                continue

            # Look for decrease-increase patterns (refills)
            refill_count = 0
            total_decreased = 0
            total_refilled = 0
            event_types = price_events['event_type'].tolist()

            for i in range(len(event_types) - 1):
                if event_types[i] == 'decrease' and event_types[i + 1] in ['increase', 'new_bid', 'new_ask']:
                    refill_count += 1
                    if i < len(price_events):
                        total_decreased += price_events.iloc[i]['volume']
                        total_refilled += price_events.iloc[i + 1]['volume']

            if refill_count >= self.min_refills:
                # Calculate time span
                time_span = (price_events.iloc[-1]['time'] - price_events.iloc[0]['time']).total_seconds()

                if time_span <= self.time_window:
                    # Higher confidence for more refills and larger volumes
                    confidence = min(refill_count / 10.0, 0.95)

                    side = price_events.iloc[0]['side']
                    avg_usd_value = price_events['usd_value'].mean()

                    icebergs.append(PatternDetection(
                        pattern_type='iceberg_order',
                        timestamp=price_events.iloc[0]['time'],
                        price_level=price,
                        confidence=confidence,
                        metrics={
                            'refill_count': refill_count,
                            'total_volume_cycled': total_decreased + total_refilled,
                            'avg_usd_value': avg_usd_value,
                            'time_span_seconds': time_span,
                            'side': side
                        },
                        description=f"Iceberg {side} order at ${price:.2f} - {refill_count} refills in {time_span:.0f}s"
                    ))

        logger.info(f"Detected {len(icebergs)} potential iceberg orders")
        return icebergs


class SpoofingDetector:
    """
    Detect spoofing patterns (fake orders to manipulate price)

    Characteristics:
    - Large orders appearing and quickly disappearing
    - Orders that don't get filled despite price movement
    - Coordinated layering at multiple levels
    """

    def __init__(self, min_usd_value: float = 100000, max_lifetime: int = 5):
        """
        Args:
            min_usd_value: Minimum USD value to consider
            max_lifetime: Maximum lifetime in seconds for potential spoof
        """
        self.min_usd_value = min_usd_value
        self.max_lifetime = max_lifetime

    def detect(self, events_df: pd.DataFrame) -> List[PatternDetection]:
        """
        Detect spoofing patterns

        Args:
            events_df: DataFrame with whale events

        Returns:
            List of detected spoofing patterns
        """
        logger.info("Detecting spoofing patterns...")

        if events_df.empty:
            return []

        spoofs = []
        df = events_df.copy()

        # Find new large orders
        new_orders = df[
            (df['event_type'].isin(['new_bid', 'new_ask'])) &
            (df['usd_value'] >= self.min_usd_value)
        ].copy()

        for idx, order in new_orders.iterrows():
            price = order['price']
            timestamp = order['time']
            side = order['side']

            # Look for removal within max_lifetime seconds
            future_events = df[
                (df['price'] == price) &
                (df['time'] > timestamp) &
                (df['time'] <= timestamp + timedelta(seconds=self.max_lifetime))
            ]

            # Check if it left without significant fills
            left_events = future_events[future_events['event_type'] == 'left_top']
            decrease_events = future_events[future_events['event_type'] == 'decrease']

            total_filled = decrease_events['volume'].sum()
            fill_pct = total_filled / order['volume'] if order['volume'] > 0 else 0

            # Spoof criteria: left quickly with minimal fills
            if len(left_events) > 0 and fill_pct < 0.1:  # Less than 10% filled
                lifetime = (left_events.iloc[0]['time'] - timestamp).total_seconds()

                # Higher confidence for shorter lifetime and less fills
                confidence = min(1.0 - fill_pct, 0.9) * (1.0 - lifetime / self.max_lifetime)

                spoofs.append(PatternDetection(
                    pattern_type='potential_spoof',
                    timestamp=timestamp,
                    price_level=price,
                    confidence=confidence,
                    metrics={
                        'usd_value': order['usd_value'],
                        'lifetime_seconds': lifetime,
                        'fill_percentage': fill_pct * 100,
                        'distance_from_mid_pct': order['distance_from_mid_pct'],
                        'side': side
                    },
                    description=f"Potential spoof {side} - ${order['usd_value']:,.0f} lasted {lifetime:.1f}s, {fill_pct*100:.1f}% filled"
                ))

        logger.info(f"Detected {len(spoofs)} potential spoofing patterns")
        return spoofs


class LayeringDetector:
    """
    Detect layering patterns (multiple orders at different levels)

    Characteristics:
    - Multiple large orders placed simultaneously
    - Orders at regular price intervals
    - Often used with spoofing strategy
    """

    def __init__(self, time_window: int = 2, min_layers: int = 3):
        """
        Args:
            time_window: Time window in seconds to group orders
            min_layers: Minimum number of layers to qualify
        """
        self.time_window = time_window
        self.min_layers = min_layers

    def detect(self, events_df: pd.DataFrame) -> List[PatternDetection]:
        """
        Detect layering patterns

        Args:
            events_df: DataFrame with whale events

        Returns:
            List of detected layering patterns
        """
        logger.info("Detecting layering patterns...")

        if events_df.empty:
            return []

        layers = []
        df = events_df.copy()

        # Focus on new orders
        new_orders = df[df['event_type'].isin(['new_bid', 'new_ask'])].copy()

        if new_orders.empty:
            return []

        # Sort by time
        new_orders = new_orders.sort_values('time')

        # Use rolling window to find simultaneous orders
        for i in range(len(new_orders)):
            order = new_orders.iloc[i]
            timestamp = order['time']
            side = order['side']

            # Find orders in same time window and side
            window_orders = new_orders[
                (new_orders['time'] >= timestamp) &
                (new_orders['time'] <= timestamp + timedelta(seconds=self.time_window)) &
                (new_orders['side'] == side) &
                (new_orders['price'] != order['price'])  # Different prices
            ]

            if len(window_orders) >= self.min_layers - 1:  # -1 because we already have current order
                # Check if prices are at regular intervals (hint of coordinated action)
                prices = sorted([order['price']] + window_orders['price'].tolist())
                intervals = [prices[i+1] - prices[i] for i in range(len(prices)-1)]

                # Calculate coefficient of variation for intervals
                if len(intervals) > 0:
                    mean_interval = sum(intervals) / len(intervals)
                    std_interval = (sum((x - mean_interval)**2 for x in intervals) / len(intervals)) ** 0.5
                    cv = std_interval / mean_interval if mean_interval > 0 else 999

                    # Regular intervals (low CV) suggest coordination
                    if cv < 0.3:
                        total_value = order['usd_value'] + window_orders['usd_value'].sum()
                        confidence = min(len(window_orders) / 10.0, 0.85) * (1 - cv)

                        layers.append(PatternDetection(
                            pattern_type='layering',
                            timestamp=timestamp,
                            price_level=order['price'],
                            confidence=confidence,
                            metrics={
                                'layer_count': len(window_orders) + 1,
                                'total_usd_value': total_value,
                                'side': side,
                                'price_interval_cv': cv,
                                'time_window_seconds': self.time_window
                            },
                            description=f"Layering detected: {len(window_orders)+1} {side} orders, ${total_value:,.0f}"
                        ))

                        # Break to avoid duplicate detections
                        break

        logger.info(f"Detected {len(layers)} layering patterns")
        return layers
