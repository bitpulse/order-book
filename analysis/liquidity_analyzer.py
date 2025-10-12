"""
Liquidity Analysis Module

Analyzes liquidity distribution in the order book:
- Clustering analysis (DBSCAN) to find support/resistance
- Volume-weighted metrics
- Depth imbalance analysis
- Liquidity holes detection

Research Reference:
- Market depth analysis reveals institutional accumulation zones
- Support/resistance levels form where liquidity clusters
"""

import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN
from typing import Dict, List, Tuple
from loguru import logger


class LiquidityAnalyzer:
    """Analyze liquidity distribution and clustering"""

    def __init__(self):
        pass

    def analyze_clustering(self, events_df: pd.DataFrame,
                          eps_pct: float = 0.5,
                          min_samples: int = 3) -> Dict:
        """
        Detect liquidity clustering using DBSCAN algorithm

        Identifies price levels where large orders accumulate, which often
        become support (bids) or resistance (asks) levels.

        Args:
            events_df: DataFrame with whale events
            eps_pct: Clustering radius as % of mid-price
            min_samples: Minimum samples for cluster formation

        Returns:
            Dict with 'bid' and 'ask' cluster lists
        """
        logger.info("Analyzing liquidity clustering...")

        if events_df.empty:
            return {}

        # Focus on liquidity additions (not removals)
        liquidity_events = events_df[
            events_df['event_type'].isin(['new_bid', 'new_ask', 'increase'])
        ].copy()

        if liquidity_events.empty:
            return {}

        results = {}

        # Analyze bids and asks separately
        for side in ['bid', 'ask']:
            side_events = liquidity_events[liquidity_events['side'] == side]

            if len(side_events) < min_samples:
                continue

            # Prepare data for clustering
            prices = side_events['price'].values.reshape(-1, 1)
            volumes = side_events['usd_value'].values

            # DBSCAN clustering
            # Convert eps from percentage to absolute price
            mid_price = side_events['mid_price'].mean()
            eps = mid_price * (eps_pct / 100.0)

            clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(prices)
            labels = clustering.labels_

            # Analyze each cluster
            clusters = []
            for label in set(labels):
                if label == -1:  # Noise points
                    continue

                cluster_mask = labels == label
                cluster_events = side_events[cluster_mask]

                cluster_info = {
                    'price_level': float(cluster_events['price'].mean()),
                    'price_min': float(cluster_events['price'].min()),
                    'price_max': float(cluster_events['price'].max()),
                    'price_std': float(cluster_events['price'].std()),
                    'total_usd_value': float(cluster_events['usd_value'].sum()),
                    'avg_usd_value': float(cluster_events['usd_value'].mean()),
                    'event_count': int(len(cluster_events)),
                    'avg_distance_from_mid_pct': float(cluster_events['distance_from_mid_pct'].mean()),
                    'time_span_seconds': float((cluster_events['time'].max() - cluster_events['time'].min()).total_seconds()),
                    'first_seen': cluster_events['time'].min(),
                    'last_seen': cluster_events['time'].max()
                }
                clusters.append(cluster_info)

            # Sort by total USD value (most significant first)
            clusters = sorted(clusters, key=lambda x: x['total_usd_value'], reverse=True)
            results[side] = clusters[:10]  # Keep top 10

        logger.info(f"Found {len(results.get('bid', []))} bid clusters, {len(results.get('ask', []))} ask clusters")
        return results

    def calculate_depth_profile(self, events_df: pd.DataFrame,
                                price_bins: int = 20) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Calculate depth profile (liquidity distribution by price level)

        Args:
            events_df: DataFrame with whale events
            price_bins: Number of price bins

        Returns:
            Tuple of (bid_profile, ask_profile) DataFrames
        """
        logger.info("Calculating depth profile...")

        if events_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # Get latest state of liquidity
        latest_bids = events_df[
            (events_df['side'] == 'bid') &
            (events_df['event_type'].isin(['new_bid', 'increase']))
        ].copy()

        latest_asks = events_df[
            (events_df['side'] == 'ask') &
            (events_df['event_type'].isin(['new_ask', 'increase']))
        ].copy()

        def create_profile(df, side):
            if df.empty:
                return pd.DataFrame()

            # Bin by price
            df['price_bin'] = pd.cut(df['price'], bins=price_bins)
            profile = df.groupby('price_bin').agg({
                'volume': 'sum',
                'usd_value': 'sum',
                'order_count': 'sum',
                'distance_from_mid_pct': 'mean'
            }).reset_index()

            # Get bin midpoints
            profile['price_level'] = profile['price_bin'].apply(lambda x: x.mid)
            profile = profile.drop('price_bin', axis=1)
            profile = profile.sort_values('price_level')

            return profile

        bid_profile = create_profile(latest_bids, 'bid')
        ask_profile = create_profile(latest_asks, 'ask')

        logger.info(f"Created depth profiles: {len(bid_profile)} bid bins, {len(ask_profile)} ask bins")
        return bid_profile, ask_profile

    def detect_liquidity_holes(self, events_df: pd.DataFrame,
                               threshold_pct: float = 0.5) -> List[Dict]:
        """
        Detect liquidity holes (price levels with abnormally low liquidity)

        These areas can experience rapid price movement due to lack of support/resistance

        Args:
            events_df: DataFrame with whale events
            threshold_pct: % of mid-price to define hole size

        Returns:
            List of detected liquidity holes
        """
        logger.info("Detecting liquidity holes...")

        if events_df.empty:
            return []

        holes = []

        # Get current liquidity snapshot
        current_orders = events_df[
            events_df['event_type'].isin(['new_bid', 'new_ask', 'increase'])
        ].copy()

        if current_orders.empty:
            return []

        mid_price = current_orders['mid_price'].mean()

        for side in ['bid', 'ask']:
            side_orders = current_orders[current_orders['side'] == side].sort_values('price')

            if len(side_orders) < 2:
                continue

            # Find gaps between price levels
            prices = side_orders['price'].values
            gaps = np.diff(prices)

            # Find abnormally large gaps
            threshold = mid_price * (threshold_pct / 100.0)
            large_gaps = np.where(gaps > threshold)[0]

            for idx in large_gaps:
                gap_size = gaps[idx]
                gap_size_pct = (gap_size / mid_price) * 100

                holes.append({
                    'side': side,
                    'price_low': float(prices[idx]),
                    'price_high': float(prices[idx + 1]),
                    'gap_size': float(gap_size),
                    'gap_size_pct': float(gap_size_pct),
                    'distance_from_mid_pct': float(((prices[idx] + prices[idx+1])/2 - mid_price) / mid_price * 100)
                })

        logger.info(f"Detected {len(holes)} liquidity holes")
        return holes

    def calculate_liquidity_ratio(self, events_df: pd.DataFrame,
                                  distance_threshold_pct: float = 1.0) -> Dict:
        """
        Calculate bid/ask liquidity ratio near mid-price

        High ratio = more bid liquidity (bullish)
        Low ratio = more ask liquidity (bearish)

        Args:
            events_df: DataFrame with whale events
            distance_threshold_pct: Distance from mid-price to consider

        Returns:
            Dict with liquidity metrics
        """
        logger.info("Calculating liquidity ratio...")

        if events_df.empty:
            return {}

        # Focus on current liquidity state
        current_liquidity = events_df[
            events_df['event_type'].isin(['new_bid', 'new_ask', 'increase'])
        ].copy()

        # Filter by distance from mid-price
        near_mid = current_liquidity[
            abs(current_liquidity['distance_from_mid_pct']) <= distance_threshold_pct
        ]

        if near_mid.empty:
            return {}

        bid_liquidity = near_mid[near_mid['side'] == 'bid']['usd_value'].sum()
        ask_liquidity = near_mid[near_mid['side'] == 'ask']['usd_value'].sum()

        total_liquidity = bid_liquidity + ask_liquidity

        if total_liquidity == 0:
            return {}

        bid_ratio = bid_liquidity / total_liquidity
        ask_ratio = ask_liquidity / total_liquidity

        imbalance = (bid_liquidity - ask_liquidity) / total_liquidity

        return {
            'bid_liquidity_usd': float(bid_liquidity),
            'ask_liquidity_usd': float(ask_liquidity),
            'total_liquidity_usd': float(total_liquidity),
            'bid_ratio': float(bid_ratio),
            'ask_ratio': float(ask_ratio),
            'imbalance': float(imbalance),
            'interpretation': self._interpret_imbalance(imbalance)
        }

    def _interpret_imbalance(self, imbalance: float) -> str:
        """Interpret liquidity imbalance value"""
        if imbalance > 0.3:
            return "Strong bid dominance (bullish)"
        elif imbalance > 0.1:
            return "Moderate bid dominance"
        elif imbalance > -0.1:
            return "Balanced liquidity"
        elif imbalance > -0.3:
            return "Moderate ask dominance"
        else:
            return "Strong ask dominance (bearish)"

    def get_volume_weighted_price(self, events_df: pd.DataFrame, side: str) -> float:
        """
        Calculate volume-weighted average price (VWAP) for a side

        Args:
            events_df: DataFrame with whale events
            side: 'bid' or 'ask'

        Returns:
            VWAP value
        """
        side_events = events_df[
            (events_df['side'] == side) &
            (events_df['event_type'].isin(['new_bid', 'new_ask', 'increase']))
        ]

        if side_events.empty or side_events['volume'].sum() == 0:
            return 0.0

        vwap = (side_events['price'] * side_events['volume']).sum() / side_events['volume'].sum()
        return float(vwap)
