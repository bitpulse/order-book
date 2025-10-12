#!/usr/bin/env python3
"""
Advanced Order Book Analysis Tool

Detects patterns, anomalies, and whale activity to build data-driven trading strategies.
Analyzes:
- Order Flow Imbalance (OFI)
- Iceberg orders
- Spoofing/manipulation patterns
- Liquidity clustering
- Market microstructure indicators
- Statistical correlations
- Trading signals

Research-based implementation using market microstructure theory.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from influxdb_client import InfluxDBClient
from typing import List, Dict, Tuple, Optional
import json
from loguru import logger
from collections import defaultdict
from dataclasses import dataclass, asdict
from scipy import stats
from scipy.cluster.hierarchy import linkage, fcluster
from sklearn.cluster import DBSCAN
import warnings
warnings.filterwarnings('ignore')

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import get_settings


@dataclass
class TradingSignal:
    """Trading signal with confidence and reasoning"""
    timestamp: datetime
    signal_type: str  # 'BUY', 'SELL', 'NEUTRAL'
    confidence: float  # 0.0 to 1.0
    price: float
    reasons: List[str]
    indicators: Dict[str, float]
    risk_reward_ratio: Optional[float] = None
    suggested_entry: Optional[float] = None
    suggested_stop: Optional[float] = None
    suggested_target: Optional[float] = None


@dataclass
class PatternDetection:
    """Detected pattern in order book"""
    pattern_type: str
    timestamp: datetime
    price_level: float
    confidence: float
    metrics: Dict[str, float]
    description: str


class AdvancedOrderBookAnalyzer:
    """Advanced analyzer for order book patterns and trading signals"""

    def __init__(self):
        self.settings = get_settings()
        self.client = InfluxDBClient(
            url=self.settings.influxdb_url,
            token=self.settings.influxdb_token,
            org=self.settings.influxdb_org
        )
        self.query_api = self.client.query_api()
        self.bucket = self.settings.influxdb_bucket

    # ==================== DATA EXTRACTION ====================

    def query_price_data(self, symbol: str, lookback_hours: int = 24) -> pd.DataFrame:
        """Query continuous price data"""
        logger.info(f"Querying price data for {symbol} (last {lookback_hours} hours)...")

        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{lookback_hours}h)
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        tables = self.query_api.query(query)
        records = []
        for table in tables:
            for record in table.records:
                records.append({
                    'time': record.get_time(),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'mid_price': record.values.get('mid_price', 0),
                    'spread': record.values.get('spread', 0),
                })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values('time').reset_index(drop=True)
        logger.info(f"Loaded {len(df)} price records")
        return df

    def query_whale_events(self, symbol: str, lookback_hours: int = 24,
                          event_types: Optional[List[str]] = None) -> pd.DataFrame:
        """Query whale/order book events"""
        logger.info(f"Querying whale events for {symbol}...")

        event_filter = ""
        if event_types:
            event_conditions = " or ".join([f'r.event_type == "{et}"' for et in event_types])
            event_filter = f'|> filter(fn: (r) => {event_conditions})'

        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{lookback_hours}h)
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          {event_filter}
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        tables = self.query_api.query(query)
        records = []
        for table in tables:
            for record in table.records:
                records.append({
                    'time': record.get_time(),
                    'event_type': record.values.get('event_type', ''),
                    'side': record.values.get('side', ''),
                    'price': record.values.get('price', 0),
                    'volume': record.values.get('volume', 0),
                    'usd_value': record.values.get('usd_value', 0),
                    'distance_from_mid_pct': record.values.get('distance_from_mid_pct', 0),
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'spread': record.values.get('spread', 0),
                    'level': record.values.get('level', 0),
                    'order_count': record.values.get('order_count', 0),
                    'info': record.values.get('info', ''),
                })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values('time').reset_index(drop=True)
        logger.info(f"Loaded {len(df)} whale events")
        return df

    def align_timeseries(self, price_df: pd.DataFrame, events_df: pd.DataFrame,
                        window: str = '1s') -> pd.DataFrame:
        """Align price data with events on common time grid"""
        if price_df.empty or events_df.empty:
            return pd.DataFrame()

        # Resample price data to regular intervals
        price_df = price_df.set_index('time')
        price_resampled = price_df.resample(window).last().ffill()

        # Merge events with nearest price
        events_df = events_df.set_index('time')
        combined = pd.merge_asof(
            events_df.sort_index(),
            price_resampled[['mid_price', 'spread']],
            left_index=True,
            right_index=True,
            direction='nearest',
            suffixes=('_event', '_current')
        )

        return combined.reset_index()

    # ==================== ORDER FLOW IMBALANCE (OFI) ====================

    def calculate_order_flow_imbalance(self, events_df: pd.DataFrame,
                                       window: str = '5s') -> pd.DataFrame:
        """
        Calculate Order Flow Imbalance (OFI) - key microstructure indicator
        OFI = (Bid Volume + Bid Increases) - (Ask Volume + Ask Increases)

        Research shows OFI has ~50% R² correlation with short-term returns
        """
        logger.info("Calculating Order Flow Imbalance (OFI)...")

        if events_df.empty:
            return pd.DataFrame()

        df = events_df.copy()
        df = df.set_index('time')

        # Aggregate by time window
        ofi_data = []

        for timestamp, window_data in df.resample(window):
            if window_data.empty:
                continue

            # Bid side pressure (positive)
            bid_events = window_data[window_data['side'].isin(['bid', 'buy'])]
            bid_new = bid_events[bid_events['event_type'] == 'new_bid']['volume'].sum()
            bid_increase = bid_events[bid_events['event_type'] == 'increase']['volume'].sum()
            bid_pressure = bid_new + bid_increase

            # Ask side pressure (negative)
            ask_events = window_data[window_data['side'].isin(['ask', 'sell'])]
            ask_new = ask_events[ask_events['event_type'] == 'new_ask']['volume'].sum()
            ask_increase = ask_events[ask_events['event_type'] == 'increase']['volume'].sum()
            ask_pressure = ask_new + ask_increase

            # Market orders (strong signal)
            market_buy_vol = window_data[window_data['event_type'] == 'market_buy']['volume'].sum()
            market_sell_vol = window_data[window_data['event_type'] == 'market_sell']['volume'].sum()

            # Calculate OFI
            ofi = bid_pressure - ask_pressure
            ofi_with_trades = ofi + (market_buy_vol - market_sell_vol)

            # Calculate depth imbalance
            total_bid_depth = bid_pressure
            total_ask_depth = ask_pressure
            depth_imbalance = 0
            if (total_bid_depth + total_ask_depth) > 0:
                depth_imbalance = (total_bid_depth - total_ask_depth) / (total_bid_depth + total_ask_depth)

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
            # Add rolling statistics
            ofi_df['ofi_ma_5'] = ofi_df['ofi'].rolling(5).mean()
            ofi_df['ofi_ma_20'] = ofi_df['ofi'].rolling(20).mean()
            ofi_df['ofi_std'] = ofi_df['ofi'].rolling(20).std()
            ofi_df['ofi_zscore'] = (ofi_df['ofi'] - ofi_df['ofi_ma_20']) / (ofi_df['ofi_std'] + 1e-9)

        logger.info(f"Calculated OFI for {len(ofi_df)} time windows")
        return ofi_df

    # ==================== ICEBERG DETECTION ====================

    def detect_iceberg_orders(self, events_df: pd.DataFrame,
                             min_refills: int = 3,
                             time_window: int = 30) -> List[PatternDetection]:
        """
        Detect iceberg orders (hidden large orders)

        Characteristics:
        - Rapid volume replenishment at same price after fills
        - Price stagnation despite heavy volume
        - Multiple decrease events followed by increases at same level
        """
        logger.info("Detecting iceberg orders...")

        if events_df.empty:
            return []

        icebergs = []
        df = events_df.copy()

        # Group by price level
        for price in df['price'].unique():
            price_events = df[df['price'] == price].sort_values('time')

            if len(price_events) < min_refills:
                continue

            # Look for decrease-increase patterns
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

            if refill_count >= min_refills:
                # Calculate time span
                time_span = (price_events.iloc[-1]['time'] - price_events.iloc[0]['time']).total_seconds()

                if time_span <= time_window:
                    confidence = min(refill_count / 10.0, 0.95)  # Cap at 0.95

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

    # ==================== SPOOFING DETECTION ====================

    def detect_spoofing(self, events_df: pd.DataFrame,
                       min_usd_value: float = 100000,
                       max_lifetime: int = 5) -> List[PatternDetection]:
        """
        Detect spoofing patterns (fake orders to manipulate)

        Characteristics:
        - Large orders appearing and disappearing quickly
        - Orders that don't get filled despite price movement
        - Layering at multiple price levels
        """
        logger.info("Detecting spoofing patterns...")

        if events_df.empty:
            return []

        spoofs = []
        df = events_df.copy()

        # Find new large orders
        new_orders = df[
            (df['event_type'].isin(['new_bid', 'new_ask'])) &
            (df['usd_value'] >= min_usd_value)
        ].copy()

        for idx, order in new_orders.iterrows():
            price = order['price']
            timestamp = order['time']
            side = order['side']

            # Look for removal within max_lifetime seconds
            future_events = df[
                (df['price'] == price) &
                (df['time'] > timestamp) &
                (df['time'] <= timestamp + timedelta(seconds=max_lifetime))
            ]

            # Check if it left without significant fills
            left_events = future_events[future_events['event_type'] == 'left_top']
            decrease_events = future_events[future_events['event_type'] == 'decrease']

            total_filled = decrease_events['volume'].sum()
            fill_pct = total_filled / order['volume'] if order['volume'] > 0 else 0

            if len(left_events) > 0 and fill_pct < 0.1:  # Less than 10% filled
                lifetime = (left_events.iloc[0]['time'] - timestamp).total_seconds()
                confidence = min(1.0 - fill_pct, 0.9) * (1.0 - lifetime / max_lifetime)

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

    # ==================== LIQUIDITY CLUSTERING ====================

    def analyze_liquidity_clustering(self, events_df: pd.DataFrame,
                                    eps_pct: float = 0.5,
                                    min_samples: int = 3) -> Dict:
        """
        Detect liquidity clustering at specific price levels using DBSCAN

        Identifies support/resistance levels where whales accumulate orders
        """
        logger.info("Analyzing liquidity clustering...")

        if events_df.empty:
            return {}

        # Focus on new orders and increases (actual liquidity additions)
        liquidity_events = events_df[
            events_df['event_type'].isin(['new_bid', 'new_ask', 'increase'])
        ].copy()

        if liquidity_events.empty:
            return {}

        # Separate bids and asks
        results = {}

        for side in ['bid', 'ask']:
            side_events = liquidity_events[liquidity_events['side'] == side]

            if len(side_events) < min_samples:
                continue

            # Prepare data for clustering
            prices = side_events['price'].values.reshape(-1, 1)
            volumes = side_events['usd_value'].values

            # DBSCAN clustering
            # eps is in price terms - convert from percentage
            mid_price = side_events['mid_price'].mean()
            eps = mid_price * (eps_pct / 100.0)

            clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(prices)
            labels = clustering.labels_

            # Analyze clusters
            clusters = []
            for label in set(labels):
                if label == -1:  # Noise
                    continue

                cluster_mask = labels == label
                cluster_events = side_events[cluster_mask]

                cluster_info = {
                    'price_level': cluster_events['price'].mean(),
                    'price_std': cluster_events['price'].std(),
                    'total_usd_value': cluster_events['usd_value'].sum(),
                    'event_count': len(cluster_events),
                    'avg_distance_from_mid_pct': cluster_events['distance_from_mid_pct'].mean(),
                    'time_span_seconds': (cluster_events['time'].max() - cluster_events['time'].min()).total_seconds(),
                    'first_seen': cluster_events['time'].min(),
                    'last_seen': cluster_events['time'].max()
                }
                clusters.append(cluster_info)

            # Sort by total USD value
            clusters = sorted(clusters, key=lambda x: x['total_usd_value'], reverse=True)
            results[side] = clusters[:10]  # Top 10 clusters

        logger.info(f"Found {len(results.get('bid', []))} bid clusters, {len(results.get('ask', []))} ask clusters")
        return results

    # ==================== MARKET MICROSTRUCTURE INDICATORS ====================

    def calculate_microstructure_indicators(self, price_df: pd.DataFrame,
                                           events_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate market microstructure indicators
        - Spread dynamics
        - Volume-weighted metrics
        - Volatility measures
        """
        logger.info("Calculating microstructure indicators...")

        if price_df.empty:
            return pd.DataFrame()

        df = price_df.copy().set_index('time')

        # Resample to regular intervals
        df_1s = df.resample('1s').last().ffill()

        # Calculate returns
        df_1s['returns'] = df_1s['mid_price'].pct_change()
        df_1s['log_returns'] = np.log(df_1s['mid_price'] / df_1s['mid_price'].shift(1))

        # Spread metrics
        df_1s['spread_bps'] = (df_1s['spread'] / df_1s['mid_price']) * 10000
        df_1s['spread_ma'] = df_1s['spread_bps'].rolling(60).mean()
        df_1s['spread_std'] = df_1s['spread_bps'].rolling(60).std()

        # Volatility (rolling standard deviation of returns)
        df_1s['volatility_1m'] = df_1s['returns'].rolling(60).std() * np.sqrt(60)  # Annualized
        df_1s['volatility_5m'] = df_1s['returns'].rolling(300).std() * np.sqrt(300)

        # Price velocity
        df_1s['price_velocity'] = df_1s['mid_price'].diff(5) / 5  # Price change per second

        # Realized volatility (using high-frequency approach)
        df_1s['realized_vol'] = np.sqrt((df_1s['returns'] ** 2).rolling(300).sum())

        logger.info(f"Calculated microstructure indicators for {len(df_1s)} time points")
        return df_1s.reset_index()

    # ==================== STATISTICAL ANALYSIS ====================

    def analyze_correlations(self, ofi_df: pd.DataFrame,
                            micro_df: pd.DataFrame) -> Dict:
        """
        Analyze correlations between OFI, spreads, and price movements
        Research shows strong relationships (R² > 0.5 for OFI, R² > 0.9 for spread-volatility)
        """
        logger.info("Analyzing statistical correlations...")

        if ofi_df.empty or micro_df.empty:
            return {}

        # Merge datasets
        ofi_df = ofi_df.set_index('time')
        micro_df = micro_df.set_index('time')

        combined = pd.merge_asof(
            ofi_df.sort_index(),
            micro_df[['mid_price', 'returns', 'spread_bps', 'volatility_1m']].sort_index(),
            left_index=True,
            right_index=True,
            direction='nearest'
        ).dropna()

        if combined.empty:
            return {}

        # Calculate future returns (prediction target)
        for seconds in [1, 5, 30, 60]:
            combined[f'future_return_{seconds}s'] = combined['mid_price'].shift(-seconds).pct_change()

        correlations = {}

        # OFI correlations with future returns
        for seconds in [1, 5, 30, 60]:
            col = f'future_return_{seconds}s'
            if col in combined.columns:
                valid = combined[['ofi', 'ofi_with_trades', 'depth_imbalance', col]].dropna()
                if len(valid) > 10:
                    correlations[f'ofi_vs_return_{seconds}s'] = {
                        'ofi': float(valid['ofi'].corr(valid[col])),
                        'ofi_with_trades': float(valid['ofi_with_trades'].corr(valid[col])),
                        'depth_imbalance': float(valid['depth_imbalance'].corr(valid[col])),
                        'sample_size': len(valid)
                    }

        # Spread-volatility correlation
        spread_vol = combined[['spread_bps', 'volatility_1m']].dropna()
        if len(spread_vol) > 10:
            correlations['spread_vs_volatility'] = {
                'correlation': float(spread_vol['spread_bps'].corr(spread_vol['volatility_1m'])),
                'r_squared': float(spread_vol['spread_bps'].corr(spread_vol['volatility_1m']) ** 2),
                'sample_size': len(spread_vol)
            }

        # OFI autocorrelation (persistence)
        if len(combined) > 20:
            ofi_values = combined['ofi'].values
            autocorr_1 = np.corrcoef(ofi_values[:-1], ofi_values[1:])[0, 1]
            autocorr_5 = np.corrcoef(ofi_values[:-5], ofi_values[5:])[0, 1] if len(ofi_values) > 5 else 0

            correlations['ofi_autocorrelation'] = {
                'lag_1': float(autocorr_1),
                'lag_5': float(autocorr_5)
            }

        logger.info(f"Calculated {len(correlations)} correlation sets")
        return correlations

    # ==================== ANOMALY DETECTION ====================

    def detect_anomalies(self, events_df: pd.DataFrame,
                        ofi_df: pd.DataFrame,
                        zscore_threshold: float = 3.0) -> List[PatternDetection]:
        """
        Detect statistical anomalies and unusual patterns
        - Volume outliers
        - OFI extremes
        - Spread spikes
        - Unusual event clusters
        """
        logger.info("Detecting anomalies...")

        anomalies = []

        # 1. Volume anomalies
        if not events_df.empty:
            events_df = events_df.copy()
            usd_mean = events_df['usd_value'].mean()
            usd_std = events_df['usd_value'].std()

            if usd_std > 0:
                events_df['usd_zscore'] = (events_df['usd_value'] - usd_mean) / usd_std
                volume_outliers = events_df[events_df['usd_zscore'] > zscore_threshold]

                for idx, event in volume_outliers.iterrows():
                    anomalies.append(PatternDetection(
                        pattern_type='volume_anomaly',
                        timestamp=event['time'],
                        price_level=event['price'],
                        confidence=min(event['usd_zscore'] / 10.0, 0.99),
                        metrics={
                            'usd_value': event['usd_value'],
                            'zscore': event['usd_zscore'],
                            'event_type': event['event_type'],
                            'side': event['side'],
                            'distance_from_mid_pct': event['distance_from_mid_pct']
                        },
                        description=f"Volume anomaly: {event['event_type']} ${event['usd_value']:,.0f} ({event['usd_zscore']:.1f}σ)"
                    ))

        # 2. OFI extremes
        if not ofi_df.empty and 'ofi_zscore' in ofi_df.columns:
            ofi_extremes = ofi_df[abs(ofi_df['ofi_zscore']) > zscore_threshold]

            for idx, row in ofi_extremes.iterrows():
                direction = "bullish" if row['ofi_zscore'] > 0 else "bearish"
                anomalies.append(PatternDetection(
                    pattern_type='ofi_extreme',
                    timestamp=row['time'],
                    price_level=row['mid_price'],
                    confidence=min(abs(row['ofi_zscore']) / 10.0, 0.99),
                    metrics={
                        'ofi': row['ofi'],
                        'ofi_zscore': row['ofi_zscore'],
                        'bid_pressure': row['bid_pressure'],
                        'ask_pressure': row['ask_pressure'],
                        'depth_imbalance': row['depth_imbalance']
                    },
                    description=f"OFI extreme ({direction}): {row['ofi']:.0f} ({row['ofi_zscore']:.1f}σ)"
                ))

        logger.info(f"Detected {len(anomalies)} anomalies")
        return anomalies

    # ==================== TRADING SIGNAL GENERATION ====================

    def generate_trading_signals(self, ofi_df: pd.DataFrame,
                                 micro_df: pd.DataFrame,
                                 patterns: List[PatternDetection],
                                 liquidity_clusters: Dict) -> List[TradingSignal]:
        """
        Generate trading signals based on multiple indicators

        Signal scoring system:
        - OFI direction and strength
        - Spread dynamics
        - Pattern confirmations
        - Liquidity support
        """
        logger.info("Generating trading signals...")

        if ofi_df.empty or micro_df.empty:
            return []

        signals = []

        # Merge OFI with microstructure
        ofi_df = ofi_df.set_index('time')
        micro_df = micro_df.set_index('time')

        combined = pd.merge_asof(
            ofi_df.sort_index(),
            micro_df.sort_index(),
            left_index=True,
            right_index=True,
            direction='nearest'
        ).dropna()

        if combined.empty:
            return []

        # Generate signals for each time point
        for idx, row in combined.iterrows():
            reasons = []
            score = 0  # -100 to +100, negative = sell, positive = buy
            indicators = {}

            # 1. OFI signal (strongest weight)
            if 'ofi_zscore' in row and pd.notna(row['ofi_zscore']):
                ofi_z = row['ofi_zscore']
                indicators['ofi_zscore'] = ofi_z

                if ofi_z > 2.0:
                    score += 40
                    reasons.append(f"Strong buy pressure (OFI: {ofi_z:.1f}σ)")
                elif ofi_z > 1.0:
                    score += 20
                    reasons.append(f"Moderate buy pressure (OFI: {ofi_z:.1f}σ)")
                elif ofi_z < -2.0:
                    score -= 40
                    reasons.append(f"Strong sell pressure (OFI: {ofi_z:.1f}σ)")
                elif ofi_z < -1.0:
                    score -= 20
                    reasons.append(f"Moderate sell pressure (OFI: {ofi_z:.1f}σ)")

            # 2. Depth imbalance
            if 'depth_imbalance' in row and pd.notna(row['depth_imbalance']):
                depth_imb = row['depth_imbalance']
                indicators['depth_imbalance'] = depth_imb

                if depth_imb > 0.3:
                    score += 15
                    reasons.append(f"Bid depth dominance ({depth_imb:.2f})")
                elif depth_imb < -0.3:
                    score -= 15
                    reasons.append(f"Ask depth dominance ({depth_imb:.2f})")

            # 3. Spread dynamics
            if 'spread_bps' in row and 'spread_ma' in row:
                if pd.notna(row['spread_bps']) and pd.notna(row['spread_ma']):
                    spread_ratio = row['spread_bps'] / row['spread_ma'] if row['spread_ma'] > 0 else 1
                    indicators['spread_ratio'] = spread_ratio

                    if spread_ratio < 0.7:
                        score += 10
                        reasons.append("Tight spread (high liquidity)")
                    elif spread_ratio > 1.5:
                        score -= 10
                        reasons.append("Wide spread (low liquidity)")

            # 4. Volatility check
            if 'volatility_1m' in row and pd.notna(row['volatility_1m']):
                vol = row['volatility_1m']
                indicators['volatility_1m'] = vol

                if vol > 0.05:  # High volatility
                    score = score * 0.7  # Reduce confidence in high volatility
                    reasons.append(f"High volatility ({vol:.3f})")

            # 5. Pattern confirmations
            pattern_window = timedelta(seconds=30)
            recent_patterns = [p for p in patterns if abs((p.timestamp - idx).total_seconds()) <= 30]

            for pattern in recent_patterns:
                if pattern.pattern_type == 'iceberg_order':
                    side = pattern.metrics.get('side', '')
                    if side == 'bid' and score > 0:
                        score += 10
                        reasons.append(f"Iceberg support at ${pattern.price_level:.2f}")
                    elif side == 'ask' and score < 0:
                        score += 10
                        reasons.append(f"Iceberg resistance at ${pattern.price_level:.2f}")

            # Generate signal if score is significant
            if abs(score) >= 20:  # Threshold for signal generation
                if score > 0:
                    signal_type = 'BUY'
                elif score < 0:
                    signal_type = 'SELL'
                else:
                    signal_type = 'NEUTRAL'

                confidence = min(abs(score) / 100.0, 0.95)
                price = row['mid_price']

                # Calculate suggested levels (basic example)
                spread = row.get('spread', price * 0.0001)
                if signal_type == 'BUY':
                    suggested_entry = price - spread
                    suggested_stop = price - (spread * 3)
                    suggested_target = price + (spread * 5)
                    risk_reward = 5.0 / 3.0
                elif signal_type == 'SELL':
                    suggested_entry = price + spread
                    suggested_stop = price + (spread * 3)
                    suggested_target = price - (spread * 5)
                    risk_reward = 5.0 / 3.0
                else:
                    suggested_entry = None
                    suggested_stop = None
                    suggested_target = None
                    risk_reward = None

                signals.append(TradingSignal(
                    timestamp=idx,
                    signal_type=signal_type,
                    confidence=confidence,
                    price=price,
                    reasons=reasons,
                    indicators=indicators,
                    risk_reward_ratio=risk_reward,
                    suggested_entry=suggested_entry,
                    suggested_stop=suggested_stop,
                    suggested_target=suggested_target
                ))

        # Filter to significant signals only (avoid noise)
        significant_signals = [s for s in signals if s.confidence >= 0.5]

        logger.info(f"Generated {len(significant_signals)} significant trading signals")
        return significant_signals

    # ==================== REPORTING ====================

    def save_results(self, symbol: str, results: Dict):
        """Save analysis results to files"""
        output_dir = Path("analysis_output")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"advanced_analysis_{symbol}_{timestamp}"

        # Save main analysis JSON
        json_path = output_dir / f"{base_name}.json"
        with open(json_path, 'w') as f:
            # Convert objects to dicts
            results_serializable = {}
            for key, value in results.items():
                if isinstance(value, list) and value and isinstance(value[0], (PatternDetection, TradingSignal)):
                    results_serializable[key] = [asdict(item) for item in value]
                elif isinstance(value, pd.DataFrame):
                    results_serializable[key] = f"<DataFrame: {len(value)} rows>"
                else:
                    results_serializable[key] = value

            json.dump(results_serializable, f, indent=2, default=str)

        logger.info(f"Saved analysis to {json_path}")

        # Save signals CSV
        if 'signals' in results and results['signals']:
            signals_df = pd.DataFrame([asdict(s) for s in results['signals']])
            csv_path = output_dir / f"{base_name}_signals.csv"
            signals_df.to_csv(csv_path, index=False)
            logger.info(f"Saved signals to {csv_path}")

        # Save patterns CSV
        if 'patterns' in results and results['patterns']:
            patterns_df = pd.DataFrame([asdict(p) for p in results['patterns']])
            csv_path = output_dir / f"{base_name}_patterns.csv"
            patterns_df.to_csv(csv_path, index=False)
            logger.info(f"Saved patterns to {csv_path}")

        return json_path

    def print_summary(self, results: Dict):
        """Print comprehensive analysis summary"""
        print("\n" + "=" * 100)
        print("ADVANCED ORDER BOOK ANALYSIS SUMMARY")
        print("=" * 100 + "\n")

        # Patterns
        if 'patterns' in results:
            patterns = results['patterns']
            print(f"DETECTED PATTERNS: {len(patterns)}")
            print("-" * 100)

            pattern_counts = defaultdict(int)
            for p in patterns:
                pattern_counts[p.pattern_type] += 1

            for ptype, count in pattern_counts.items():
                print(f"  {ptype}: {count}")

            # Top patterns
            top_patterns = sorted(patterns, key=lambda x: x.confidence, reverse=True)[:5]
            print("\nTop 5 Patterns:")
            for i, p in enumerate(top_patterns, 1):
                print(f"  {i}. {p.description} (confidence: {p.confidence:.2%})")

        # Signals
        if 'signals' in results:
            signals = results['signals']
            print(f"\n\nTRADING SIGNALS: {len(signals)}")
            print("-" * 100)

            buy_signals = [s for s in signals if s.signal_type == 'BUY']
            sell_signals = [s for s in signals if s.signal_type == 'SELL']

            print(f"  BUY signals: {len(buy_signals)}")
            print(f"  SELL signals: {len(sell_signals)}")

            if buy_signals:
                avg_confidence = np.mean([s.confidence for s in buy_signals])
                print(f"  Avg BUY confidence: {avg_confidence:.2%}")

            if sell_signals:
                avg_confidence = np.mean([s.confidence for s in sell_signals])
                print(f"  Avg SELL confidence: {avg_confidence:.2%}")

            # Top signals
            top_signals = sorted(signals, key=lambda x: x.confidence, reverse=True)[:10]
            print("\nTop 10 Signals:")
            for i, s in enumerate(top_signals, 1):
                print(f"\n  {i}. {s.signal_type} @ ${s.price:.2f} ({s.confidence:.1%} confidence)")
                print(f"     Time: {s.timestamp}")
                print(f"     Reasons: {', '.join(s.reasons[:3])}")
                if s.suggested_entry:
                    print(f"     Entry: ${s.suggested_entry:.2f} | Stop: ${s.suggested_stop:.2f} | Target: ${s.suggested_target:.2f}")

        # Correlations
        if 'correlations' in results:
            corrs = results['correlations']
            print("\n\nSTATISTICAL CORRELATIONS")
            print("-" * 100)

            for key, value in corrs.items():
                print(f"\n{key}:")
                if isinstance(value, dict):
                    for k, v in value.items():
                        if isinstance(v, (int, float)):
                            print(f"  {k}: {v:.4f}")
                        else:
                            print(f"  {k}: {v}")

        # Liquidity clusters
        if 'liquidity_clusters' in results:
            clusters = results['liquidity_clusters']
            print("\n\nLIQUIDITY CLUSTERS")
            print("-" * 100)

            for side in ['bid', 'ask']:
                if side in clusters and clusters[side]:
                    print(f"\n{side.upper()} Clusters (Top 5):")
                    for i, cluster in enumerate(clusters[side][:5], 1):
                        print(f"  {i}. ${cluster['price_level']:.2f} - ${cluster['total_usd_value']:,.0f}")
                        print(f"     Events: {cluster['event_count']}, Duration: {cluster['time_span_seconds']:.0f}s")

        print("\n" + "=" * 100 + "\n")

    # ==================== MAIN ANALYSIS ====================

    async def run(self, symbol: str = "BTC_USDT", lookback_hours: int = 24):
        """Run complete advanced analysis"""
        try:
            logger.info(f"Starting advanced analysis for {symbol}...")

            # 1. Extract data
            price_df = self.query_price_data(symbol, lookback_hours)
            events_df = self.query_whale_events(symbol, lookback_hours)

            if price_df.empty or events_df.empty:
                logger.warning("Insufficient data for analysis")
                return

            # 2. Calculate indicators
            ofi_df = self.calculate_order_flow_imbalance(events_df, window='5s')
            micro_df = self.calculate_microstructure_indicators(price_df, events_df)

            # 3. Detect patterns
            icebergs = self.detect_iceberg_orders(events_df)
            spoofs = self.detect_spoofing(events_df)
            anomalies = self.detect_anomalies(events_df, ofi_df)
            liquidity_clusters = self.analyze_liquidity_clustering(events_df)

            all_patterns = icebergs + spoofs + anomalies

            # 4. Statistical analysis
            correlations = self.analyze_correlations(ofi_df, micro_df)

            # 5. Generate trading signals
            signals = self.generate_trading_signals(ofi_df, micro_df, all_patterns, liquidity_clusters)

            # 6. Compile results
            results = {
                'symbol': symbol,
                'lookback_hours': lookback_hours,
                'analysis_timestamp': datetime.now(),
                'data_points': {
                    'price_records': len(price_df),
                    'whale_events': len(events_df),
                    'ofi_windows': len(ofi_df)
                },
                'patterns': all_patterns,
                'signals': signals,
                'correlations': correlations,
                'liquidity_clusters': liquidity_clusters,
                'ofi_summary': {
                    'mean': float(ofi_df['ofi'].mean()) if not ofi_df.empty else 0,
                    'std': float(ofi_df['ofi'].std()) if not ofi_df.empty else 0,
                    'max': float(ofi_df['ofi'].max()) if not ofi_df.empty else 0,
                    'min': float(ofi_df['ofi'].min()) if not ofi_df.empty else 0
                }
            }

            # 7. Save and display
            output_path = self.save_results(symbol, results)
            self.print_summary(results)

            logger.info("Advanced analysis complete!")
            logger.info(f"Results saved to: {output_path}")

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise
        finally:
            self.client.close()


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Advanced Order Book Analysis - Detect patterns and generate trading signals'
    )
    parser.add_argument('--symbol', default='BTC_USDT', help='Trading symbol')
    parser.add_argument('--lookback', type=int, default=24, help='Hours of data to analyze')

    args = parser.parse_args()

    # Setup logging
    logger.remove()
    logger.add(sys.stdout, level="INFO")

    analyzer = AdvancedOrderBookAnalyzer()
    await analyzer.run(symbol=args.symbol, lookback_hours=args.lookback)


if __name__ == "__main__":
    asyncio.run(main())
