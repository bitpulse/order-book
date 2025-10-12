"""
Anomaly Detection Module

Detects statistical anomalies and unusual patterns:
- Volume outliers (Z-score method)
- OFI extremes
- Spread spikes
- Unusual event clusters
- Time-series anomalies

Uses statistical methods for robust detection.
"""

import pandas as pd
import numpy as np
from scipy import stats
from typing import List
from loguru import logger

try:
    from .data_models import PatternDetection
except ImportError:
    from data_models import PatternDetection


class AnomalyDetector:
    """Detect anomalies in order book data"""

    def __init__(self, zscore_threshold: float = 3.0):
        """
        Initialize anomaly detector

        Args:
            zscore_threshold: Z-score threshold for anomaly (typically 2-3)
        """
        self.zscore_threshold = zscore_threshold

    def detect_all(self, events_df: pd.DataFrame,
                   ofi_df: pd.DataFrame,
                   micro_df: pd.DataFrame) -> List[PatternDetection]:
        """
        Detect all types of anomalies

        Args:
            events_df: DataFrame with whale events
            ofi_df: DataFrame with OFI metrics
            micro_df: DataFrame with microstructure indicators

        Returns:
            List of detected anomalies
        """
        logger.info("Detecting anomalies...")

        anomalies = []

        # 1. Volume anomalies
        anomalies.extend(self.detect_volume_anomalies(events_df))

        # 2. OFI extremes
        anomalies.extend(self.detect_ofi_extremes(ofi_df))

        # 3. Spread anomalies
        anomalies.extend(self.detect_spread_anomalies(micro_df))

        # 4. Event clustering anomalies
        anomalies.extend(self.detect_event_clusters(events_df))

        logger.info(f"Total anomalies detected: {len(anomalies)}")
        return anomalies

    def detect_volume_anomalies(self, events_df: pd.DataFrame) -> List[PatternDetection]:
        """
        Detect volume outliers using Z-score method

        Args:
            events_df: DataFrame with whale events

        Returns:
            List of volume anomalies
        """
        if events_df.empty or 'usd_value' not in events_df.columns:
            return []

        logger.info("Detecting volume anomalies...")

        anomalies = []
        df = events_df.copy()

        # Calculate Z-scores
        usd_mean = df['usd_value'].mean()
        usd_std = df['usd_value'].std()

        if usd_std == 0:
            return []

        df['usd_zscore'] = (df['usd_value'] - usd_mean) / usd_std

        # Find outliers
        outliers = df[df['usd_zscore'] > self.zscore_threshold]

        for idx, event in outliers.iterrows():
            confidence = min(event['usd_zscore'] / 10.0, 0.99)

            anomalies.append(PatternDetection(
                pattern_type='volume_anomaly',
                timestamp=event['time'],
                price_level=event['price'],
                confidence=confidence,
                metrics={
                    'usd_value': event['usd_value'],
                    'zscore': event['usd_zscore'],
                    'event_type': event['event_type'],
                    'side': event['side'],
                    'distance_from_mid_pct': event['distance_from_mid_pct'],
                    'volume': event['volume']
                },
                description=f"Volume anomaly: {event['event_type']} ${event['usd_value']:,.0f} ({event['usd_zscore']:.1f}σ)"
            ))

        logger.info(f"Detected {len(anomalies)} volume anomalies")
        return anomalies

    def detect_ofi_extremes(self, ofi_df: pd.DataFrame) -> List[PatternDetection]:
        """
        Detect OFI extreme values

        Args:
            ofi_df: DataFrame with OFI metrics

        Returns:
            List of OFI extremes
        """
        if ofi_df.empty or 'ofi_zscore' not in ofi_df.columns:
            return []

        logger.info("Detecting OFI extremes...")

        anomalies = []
        extremes = ofi_df[abs(ofi_df['ofi_zscore']) > self.zscore_threshold]

        for idx, row in extremes.iterrows():
            direction = "bullish" if row['ofi_zscore'] > 0 else "bearish"
            confidence = min(abs(row['ofi_zscore']) / 10.0, 0.99)

            anomalies.append(PatternDetection(
                pattern_type='ofi_extreme',
                timestamp=row['time'],
                price_level=row['mid_price'],
                confidence=confidence,
                metrics={
                    'ofi': row['ofi'],
                    'ofi_zscore': row['ofi_zscore'],
                    'bid_pressure': row['bid_pressure'],
                    'ask_pressure': row['ask_pressure'],
                    'depth_imbalance': row['depth_imbalance'],
                    'market_buy_volume': row.get('market_buy_volume', 0),
                    'market_sell_volume': row.get('market_sell_volume', 0)
                },
                description=f"OFI extreme ({direction}): {row['ofi']:.0f} ({row['ofi_zscore']:.1f}σ)"
            ))

        logger.info(f"Detected {len(anomalies)} OFI extremes")
        return anomalies

    def detect_spread_anomalies(self, micro_df: pd.DataFrame) -> List[PatternDetection]:
        """
        Detect unusual spread widening/tightening

        Args:
            micro_df: DataFrame with microstructure indicators

        Returns:
            List of spread anomalies
        """
        if micro_df.empty or 'spread_zscore' not in micro_df.columns:
            return []

        logger.info("Detecting spread anomalies...")

        anomalies = []
        extremes = micro_df[abs(micro_df['spread_zscore']) > self.zscore_threshold]

        for idx, row in extremes.iterrows():
            if row['spread_zscore'] > 0:
                anomaly_type = "spread_widening"
                description = f"Spread widening: {row['spread_bps']:.1f} bps ({row['spread_zscore']:.1f}σ)"
            else:
                anomaly_type = "spread_tightening"
                description = f"Spread tightening: {row['spread_bps']:.1f} bps ({row['spread_zscore']:.1f}σ)"

            confidence = min(abs(row['spread_zscore']) / 10.0, 0.99)

            anomalies.append(PatternDetection(
                pattern_type=anomaly_type,
                timestamp=row['time'],
                price_level=row['mid_price'],
                confidence=confidence,
                metrics={
                    'spread_bps': row['spread_bps'],
                    'spread_zscore': row['spread_zscore'],
                    'spread_ma': row.get('spread_ma', 0),
                    'volatility_1m': row.get('volatility_1m', 0)
                },
                description=description
            ))

        logger.info(f"Detected {len(anomalies)} spread anomalies")
        return anomalies

    def detect_event_clusters(self, events_df: pd.DataFrame,
                             time_window: int = 5,
                             min_events: int = 10) -> List[PatternDetection]:
        """
        Detect unusual clustering of events in time

        Args:
            events_df: DataFrame with whale events
            time_window: Time window in seconds
            min_events: Minimum events to qualify as cluster

        Returns:
            List of event cluster anomalies
        """
        if events_df.empty:
            return []

        logger.info("Detecting event clusters...")

        anomalies = []
        df = events_df.copy().set_index('time')

        # Calculate event rate
        event_counts = df.resample('1s').size()
        mean_rate = event_counts.mean()
        std_rate = event_counts.std()

        if std_rate == 0:
            return []

        # Find clusters (high event rate periods)
        event_counts_zscore = (event_counts - mean_rate) / std_rate
        clusters = event_counts_zscore[event_counts_zscore > self.zscore_threshold]

        for timestamp, zscore in clusters.items():
            # Get events in this window
            window_events = df[
                (df.index >= timestamp) &
                (df.index < timestamp + pd.Timedelta(seconds=time_window))
            ]

            if len(window_events) >= min_events:
                total_usd = window_events['usd_value'].sum()
                event_types = window_events['event_type'].value_counts().to_dict()

                confidence = min(zscore / 10.0, 0.95)

                anomalies.append(PatternDetection(
                    pattern_type='event_cluster',
                    timestamp=timestamp,
                    price_level=window_events['mid_price'].mean(),
                    confidence=confidence,
                    metrics={
                        'event_count': len(window_events),
                        'zscore': zscore,
                        'total_usd_value': total_usd,
                        'time_window_seconds': time_window,
                        'event_types': str(event_types)
                    },
                    description=f"Event cluster: {len(window_events)} events in {time_window}s ({zscore:.1f}σ)"
                ))

        logger.info(f"Detected {len(anomalies)} event clusters")
        return anomalies

    def detect_price_jumps(self, price_df: pd.DataFrame,
                          threshold_pct: float = 0.5) -> List[PatternDetection]:
        """
        Detect sudden price jumps

        Args:
            price_df: DataFrame with price data
            threshold_pct: Percentage threshold for jump

        Returns:
            List of price jump anomalies
        """
        if price_df.empty:
            return []

        logger.info("Detecting price jumps...")

        anomalies = []
        df = price_df.copy()

        # Calculate returns
        df['return_1s'] = df['mid_price'].pct_change() * 100  # Percentage

        # Find jumps
        jumps = df[abs(df['return_1s']) > threshold_pct]

        for idx, row in jumps.iterrows():
            direction = "upward" if row['return_1s'] > 0 else "downward"
            confidence = min(abs(row['return_1s']) / 2.0, 0.95)

            anomalies.append(PatternDetection(
                pattern_type='price_jump',
                timestamp=row['time'],
                price_level=row['mid_price'],
                confidence=confidence,
                metrics={
                    'return_pct': row['return_1s'],
                    'price_before': row['mid_price'] / (1 + row['return_1s']/100),
                    'price_after': row['mid_price'],
                    'spread': row.get('spread', 0)
                },
                description=f"Price jump ({direction}): {abs(row['return_1s']):.2f}%"
            ))

        logger.info(f"Detected {len(anomalies)} price jumps")
        return anomalies

    def calculate_anomaly_score(self, anomalies: List[PatternDetection]) -> dict:
        """
        Calculate overall anomaly score for the period

        Args:
            anomalies: List of detected anomalies

        Returns:
            Dict with anomaly metrics
        """
        if not anomalies:
            return {
                'total_anomalies': 0,
                'anomaly_score': 0,
                'average_confidence': 0,
                'by_type': {}
            }

        # Count by type
        by_type = {}
        for anomaly in anomalies:
            ptype = anomaly.pattern_type
            if ptype not in by_type:
                by_type[ptype] = 0
            by_type[ptype] += 1

        # Calculate aggregate score
        total_confidence = sum(a.confidence for a in anomalies)
        avg_confidence = total_confidence / len(anomalies)

        # Anomaly score (0-100)
        anomaly_score = min(len(anomalies) * 5 + avg_confidence * 50, 100)

        return {
            'total_anomalies': len(anomalies),
            'anomaly_score': float(anomaly_score),
            'average_confidence': float(avg_confidence),
            'by_type': by_type,
            'interpretation': self._interpret_anomaly_score(anomaly_score)
        }

    def _interpret_anomaly_score(self, score: float) -> str:
        """Interpret anomaly score"""
        if score < 20:
            return "Normal market conditions"
        elif score < 40:
            return "Mild unusual activity"
        elif score < 60:
            return "Moderate unusual activity"
        elif score < 80:
            return "High unusual activity"
        else:
            return "Extreme unusual activity"
