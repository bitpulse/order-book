"""
Order Flow Imbalance (OFI) Calculator

Calculates Order Flow Imbalance - a key microstructure indicator that measures
the imbalance between buying and selling pressure in the order book.

Research Reference:
- Dean Markwick: "Order Flow Imbalance - A High Frequency Trading Signal"
- R² correlation with returns: ~50%
- Predictive power for short-term price movements (1s - 60s)
"""

import pandas as pd
import numpy as np
from loguru import logger
from typing import Optional


class OFICalculator:
    """Calculate Order Flow Imbalance metrics"""

    def __init__(self):
        pass

    def calculate(self, events_df: pd.DataFrame, window: str = '5s') -> pd.DataFrame:
        """
        Calculate Order Flow Imbalance (OFI)

        Formula:
            OFI = (Bid Volume + Bid Increases) - (Ask Volume + Ask Increases)
            OFI_with_trades = OFI + (Market Buy Volume - Market Sell Volume)

        Args:
            events_df: DataFrame with whale events
            window: Time window for aggregation (e.g., '1s', '5s', '10s')

        Returns:
            DataFrame with OFI metrics per time window
        """
        logger.info(f"Calculating Order Flow Imbalance with {window} window...")

        if events_df.empty:
            return pd.DataFrame()

        df = events_df.copy()
        df = df.set_index('time')

        ofi_data = []

        for timestamp, window_data in df.resample(window):
            if window_data.empty:
                continue

            # Bid side pressure (positive = bullish)
            bid_events = window_data[window_data['side'].isin(['bid', 'buy'])]
            bid_new = bid_events[bid_events['event_type'] == 'new_bid']['volume'].sum()
            bid_increase = bid_events[bid_events['event_type'] == 'increase']['volume'].sum()
            bid_pressure = bid_new + bid_increase

            # Ask side pressure (negative = bearish)
            ask_events = window_data[window_data['side'].isin(['ask', 'sell'])]
            ask_new = ask_events[ask_events['event_type'] == 'new_ask']['volume'].sum()
            ask_increase = ask_events[ask_events['event_type'] == 'increase']['volume'].sum()
            ask_pressure = ask_new + ask_increase

            # Market orders (strong directional signal)
            market_buy_vol = window_data[window_data['event_type'] == 'market_buy']['volume'].sum()
            market_sell_vol = window_data[window_data['event_type'] == 'market_sell']['volume'].sum()

            # Calculate OFI
            ofi = bid_pressure - ask_pressure
            ofi_with_trades = ofi + (market_buy_vol - market_sell_vol)

            # Calculate depth imbalance ratio
            total_bid_depth = bid_pressure
            total_ask_depth = ask_pressure
            depth_imbalance = 0
            if (total_bid_depth + total_ask_depth) > 0:
                depth_imbalance = (total_bid_depth - total_ask_depth) / (total_bid_depth + total_ask_depth)

            # Get current mid price
            mid_price = window_data['mid_price'].iloc[-1] if 'mid_price' in window_data.columns else 0

            ofi_data.append({
                'time': timestamp,
                'ofi': ofi,
                'ofi_with_trades': ofi_with_trades,
                'bid_pressure': bid_pressure,
                'ask_pressure': ask_pressure,
                'market_buy_volume': market_buy_vol,
                'market_sell_volume': market_sell_vol,
                'depth_imbalance': depth_imbalance,
                'mid_price': mid_price,
                'event_count': len(window_data)
            })

        ofi_df = pd.DataFrame(ofi_data)

        if not ofi_df.empty:
            # Add rolling statistics for trend analysis
            ofi_df['ofi_ma_5'] = ofi_df['ofi'].rolling(5, min_periods=1).mean()
            ofi_df['ofi_ma_20'] = ofi_df['ofi'].rolling(20, min_periods=1).mean()
            ofi_df['ofi_std'] = ofi_df['ofi'].rolling(20, min_periods=1).std()

            # Z-score (normalized OFI for extreme detection)
            ofi_df['ofi_zscore'] = (ofi_df['ofi'] - ofi_df['ofi_ma_20']) / (ofi_df['ofi_std'] + 1e-9)

            # OFI trend (derivative)
            ofi_df['ofi_trend'] = ofi_df['ofi'].diff()

            # Cumulative OFI (momentum)
            ofi_df['ofi_cumulative'] = ofi_df['ofi'].cumsum()

        logger.info(f"Calculated OFI for {len(ofi_df)} time windows")
        return ofi_df

    def get_ofi_interpretation(self, ofi_zscore: float) -> str:
        """
        Interpret OFI Z-score value

        Args:
            ofi_zscore: Normalized OFI value

        Returns:
            Human-readable interpretation
        """
        if ofi_zscore > 3:
            return "Extreme bullish pressure"
        elif ofi_zscore > 2:
            return "Strong bullish pressure"
        elif ofi_zscore > 1:
            return "Moderate bullish pressure"
        elif ofi_zscore > -1:
            return "Balanced / Neutral"
        elif ofi_zscore > -2:
            return "Moderate bearish pressure"
        elif ofi_zscore > -3:
            return "Strong bearish pressure"
        else:
            return "Extreme bearish pressure"

    def calculate_ofi_divergence(self, ofi_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect divergences between OFI and price movements

        Divergence signals:
        - OFI rising + price falling = bullish divergence (reversal signal)
        - OFI falling + price rising = bearish divergence (reversal signal)

        Args:
            ofi_df: OFI DataFrame
            price_df: Price DataFrame

        Returns:
            DataFrame with divergence signals
        """
        if ofi_df.empty or price_df.empty:
            return pd.DataFrame()

        logger.info("Calculating OFI divergences...")

        # Merge OFI with price
        ofi_df = ofi_df.set_index('time')
        price_df = price_df.set_index('time')

        combined = pd.merge_asof(
            ofi_df.sort_index(),
            price_df[['mid_price']].sort_index(),
            left_index=True,
            right_index=True,
            direction='nearest'
        )

        # Calculate price trend
        combined['price_change'] = combined['mid_price'].diff(5)
        combined['ofi_change'] = combined['ofi'].diff(5)

        # Detect divergences
        combined['bullish_divergence'] = (
            (combined['ofi_change'] > 0) & (combined['price_change'] < 0)
        ).astype(int)

        combined['bearish_divergence'] = (
            (combined['ofi_change'] < 0) & (combined['price_change'] > 0)
        ).astype(int)

        divergences = combined[
            (combined['bullish_divergence'] == 1) | (combined['bearish_divergence'] == 1)
        ].reset_index()

        logger.info(f"Found {len(divergences)} divergence signals")
        return divergences
