#!/usr/bin/env python3
"""
Price Change Analyzer with Whale Activity Correlation
Finds time intervals with largest price movements and displays whale activity during those periods
"""

import os
import sys
import json
import csv
import argparse
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from collections import defaultdict
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

# Load environment variables
load_dotenv()


class ProgressTimer:
    """Helper class to track elapsed time for operations"""
    def __init__(self):
        self.start_time = time.time()

    def elapsed(self) -> float:
        """Get elapsed time in seconds"""
        return time.time() - self.start_time

    def elapsed_str(self) -> str:
        """Get formatted elapsed time string"""
        elapsed = self.elapsed()
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        else:
            minutes = int(elapsed // 60)
            seconds = elapsed % 60
            return f"{minutes}m {seconds:.1f}s"


class PriceChangeAnalyzer:
    """Analyzes price changes and correlates with whale activity"""

    def __init__(self, symbol: str, lookback: str = None, interval: str = '1m',
                 min_change: float = 0.1, top_n: int = 10,
                 from_time: str = None, to_time: str = None):
        """
        Initialize the analyzer

        Args:
            symbol: Trading pair (e.g., BTC_USDT)
            lookback: Time period to analyze (e.g., 1h, 24h, 7d) - optional if from_time/to_time provided
            interval: Window size for price changes (e.g., 1s, 5s, 1m, 5m)
            min_change: Minimum price change % to consider
            top_n: Number of top intervals to return
            from_time: Start time for analysis (ISO 8601 format) - optional
            to_time: End time for analysis (ISO 8601 format) - optional
        """
        self.symbol = symbol
        self.lookback = lookback
        self.interval = interval
        self.min_change = min_change
        self.top_n = top_n
        self.from_time_str = from_time
        self.to_time_str = to_time

        # Initialize InfluxDB client
        self.influx_url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.influx_token = os.getenv("INFLUXDB_TOKEN")
        self.influx_org = os.getenv("INFLUXDB_ORG", "trading")
        self.influx_bucket = os.getenv("INFLUXDB_BUCKET", "trading_data")

        if not self.influx_token:
            raise ValueError("INFLUXDB_TOKEN environment variable is required")

        self.client = InfluxDBClient(
            url=self.influx_url,
            token=self.influx_token,
            org=self.influx_org
        )
        self.query_api = self.client.query_api()

    def _parse_interval_to_seconds(self, interval: str) -> int:
        """Convert interval string to seconds"""
        unit = interval[-1]
        value = int(interval[:-1])

        if unit == 's':
            return value
        elif unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        else:
            raise ValueError(f"Invalid interval unit: {unit}. Use s, m, or h")

    def _parse_lookback_to_timedelta(self, lookback: str) -> timedelta:
        """Parse lookback string (e.g., '1h', '24h', '7d') to timedelta"""
        value = int(lookback[:-1])
        unit = lookback[-1]

        if unit == 's':
            return timedelta(seconds=value)
        elif unit == 'm':
            return timedelta(minutes=value)
        elif unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
        else:
            raise ValueError(f"Invalid lookback unit: {unit}. Use s, m, h, or d")

    def _parse_time_string(self, time_str: str) -> datetime:
        """
        Parse time string to timezone-aware UTC datetime object

        Supports formats:
        - ISO 8601 with Z: "2025-10-15T14:00:00Z"
        - ISO 8601 with timezone: "2025-10-15T14:00:00+00:00"
        - Simple datetime: "2025-10-15 14:00:00"
        - Date only: "2025-10-15" (assumes 00:00:00 UTC)

        Args:
            time_str: Time string to parse

        Returns:
            Timezone-aware datetime in UTC

        Raises:
            ValueError: If time string format is invalid
        """
        if not time_str:
            raise ValueError("Time string cannot be empty")

        # Try ISO 8601 with Z suffix
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%SZ')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        # Try ISO 8601 with timezone (fromisoformat handles this)
        try:
            dt = datetime.fromisoformat(time_str)
            # Ensure it's UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            pass

        # Try simple datetime format: "YYYY-MM-DD HH:MM:SS"
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        # Try date only: "YYYY-MM-DD" (assume 00:00:00 UTC)
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%d')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        # All formats failed
        raise ValueError(
            f"Invalid time format: '{time_str}'. "
            f"Supported formats: 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SSZ'"
        )

    def _calculate_time_range(self) -> Tuple[datetime, datetime]:
        """
        Calculate start and end times based on parameters

        Priority logic:
        1. If both from_time and to_time specified: use them
        2. If only from_time: use from_time + lookback
        3. If only to_time: use to_time - lookback
        4. If neither: use NOW - lookback to NOW (current behavior)

        Returns:
            Tuple of (start_time, end_time) as UTC datetime objects

        Raises:
            ValueError: If time range is invalid
        """
        now = datetime.now(timezone.utc)
        start_time = None
        end_time = None

        # Parse from_time if provided
        if self.from_time_str:
            start_time = self._parse_time_string(self.from_time_str)

        # Parse to_time if provided
        if self.to_time_str:
            end_time = self._parse_time_string(self.to_time_str)

        # Case 1: Both from_time and to_time specified
        if start_time and end_time:
            # Warn if lookback is also specified (it will be ignored)
            if self.lookback:
                print(f"{YELLOW}Warning: --lookback is ignored when both --from-time and --to-time are specified{RESET}")

        # Case 2: Only from_time specified
        elif start_time and not end_time:
            if not self.lookback:
                raise ValueError("When using --from-time without --to-time, --lookback is required")
            lookback_delta = self._parse_lookback_to_timedelta(self.lookback)
            end_time = start_time + lookback_delta

        # Case 3: Only to_time specified
        elif not start_time and end_time:
            if not self.lookback:
                raise ValueError("When using --to-time without --from-time, --lookback is required")
            lookback_delta = self._parse_lookback_to_timedelta(self.lookback)
            start_time = end_time - lookback_delta

        # Case 4: Neither from_time nor to_time specified (default behavior)
        else:
            if not self.lookback:
                raise ValueError("Either --lookback or --from-time/--to-time must be specified")
            lookback_delta = self._parse_lookback_to_timedelta(self.lookback)
            end_time = now
            start_time = now - lookback_delta

        # Validation
        if start_time >= end_time:
            raise ValueError(f"Start time ({start_time}) must be before end time ({end_time})")

        # Warn if times are in the future
        if start_time > now:
            print(f"{YELLOW}Warning: Start time is in the future ({start_time}){RESET}")
        if end_time > now:
            print(f"{YELLOW}Warning: End time is in the future ({end_time}){RESET}")

        return start_time, end_time

    def _deduplicate_intervals(self, intervals: List[Dict]) -> List[Dict]:
        """
        Remove overlapping intervals to show unique price spikes.

        For each interval, check if it overlaps with any already-selected interval.
        If it overlaps, skip it (it's capturing the same spike).
        If it doesn't overlap, it's a unique spike - keep it.

        Args:
            intervals: List of interval dicts sorted by change_abs (largest first)

        Returns:
            List of non-overlapping intervals (unique spikes only)
        """
        if not intervals:
            return []

        unique_intervals = []

        for interval in intervals:
            # Check if this interval overlaps with any already-selected interval
            is_duplicate = False

            for existing in unique_intervals:
                # Two intervals overlap if:
                # interval.end >= existing.start AND interval.start <= existing.end
                if (interval['end_time'] >= existing['start_time'] and
                    interval['start_time'] <= existing['end_time']):
                    is_duplicate = True
                    break

            # Only keep non-overlapping (unique) intervals
            if not is_duplicate:
                unique_intervals.append(interval)

        return unique_intervals

    def _calculate_volatility(self, prices: List[float]) -> float:
        """
        Calculate price volatility (standard deviation normalized by mean)

        Args:
            prices: List of price values

        Returns:
            Normalized volatility (0.0 if insufficient data)
        """
        if len(prices) < 2:
            return 0.0

        mean = sum(prices) / len(prices)
        if mean == 0:
            return 0.0

        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std_dev = variance ** 0.5

        return std_dev / mean  # Normalized by mean

    def _compute_price_statistics(self, price_data: List[Dict], start_time: datetime, end_time: datetime) -> Dict:
        """
        Compute summary statistics for price data instead of storing raw data

        Args:
            price_data: List of price point dicts
            start_time: Interval start time
            end_time: Interval end time

        Returns:
            Dict with price statistics
        """
        if not price_data:
            return {
                'total_points': 0,
                'min_price': 0,
                'max_price': 0,
                'avg_price': 0,
                'volatility': 0,
                'spike_point': None,
                'first_price': 0,
                'last_price': 0
            }

        prices = [p['mid_price'] for p in price_data]

        # Find spike point (largest absolute price change between consecutive points)
        max_change = 0
        spike_point = None

        for i in range(1, len(price_data)):
            change = abs(price_data[i]['mid_price'] - price_data[i-1]['mid_price'])
            if change > max_change:
                max_change = change
                spike_point = price_data[i]

        return {
            'total_points': len(price_data),
            'min_price': min(prices),
            'max_price': max(prices),
            'avg_price': sum(prices) / len(prices),
            'volatility': self._calculate_volatility(prices),
            'spike_point': {
                'time': spike_point['time'].isoformat(),
                'price': spike_point['mid_price']
            } if spike_point else None,
            'first_price': price_data[0]['mid_price'],
            'last_price': price_data[-1]['mid_price']
        }

    def _compute_whale_statistics(self, whale_events: List[Dict]) -> Dict:
        """
        Compute summary statistics for whale events

        Args:
            whale_events: List of whale event dicts

        Returns:
            Dict with whale event statistics
        """
        if not whale_events:
            return {
                'count': 0,
                'total_usd': 0,
                'biggest_whale_usd': 0,
                'by_type': {},
                'by_side': {}
            }

        by_type = defaultdict(lambda: {'count': 0, 'total_usd': 0})
        by_side = defaultdict(lambda: {'count': 0, 'total_usd': 0})

        for event in whale_events:
            event_type = event.get('event_type', 'unknown')
            side = event.get('side', 'unknown')
            usd_value = event.get('usd_value', 0)

            by_type[event_type]['count'] += 1
            by_type[event_type]['total_usd'] += usd_value

            by_side[side]['count'] += 1
            by_side[side]['total_usd'] += usd_value

        return {
            'count': len(whale_events),
            'total_usd': sum(e.get('usd_value', 0) for e in whale_events),
            'biggest_whale_usd': max((e.get('usd_value', 0) for e in whale_events), default=0),
            'by_type': dict(by_type),
            'by_side': dict(by_side)
        }

    def find_price_changes(self) -> List[Dict]:
        """
        Find intervals with largest price changes

        Returns:
            List of dicts with: start_time, end_time, start_price, end_price, change_pct
        """
        timer = ProgressTimer()
        interval_seconds = self._parse_interval_to_seconds(self.interval)

        # Calculate time range based on parameters (lookback or from/to times)
        start_time, end_time = self._calculate_time_range()

        # Show time range in log
        start_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"{DIM}[1/3] Fetching price data from {start_str} to {end_str}...{RESET}")

        all_price_data = self.get_price_data(start_time, end_time)

        if not all_price_data:
            print(f"{RED}No price data found for {self.symbol}{RESET}")
            return []

        print(f"{GREEN}✓ Loaded {len(all_price_data):,} price points in {timer.elapsed_str()}{RESET}\n")

        # Calculate price changes using sliding window over actual data points
        print(f"{DIM}[2/3] Scanning for price changes with sliding window...{RESET}")
        scan_timer = ProgressTimer()
        price_changes = []
        interval_delta = timedelta(seconds=interval_seconds)

        # Use 1-second sliding window for high resolution
        slide_seconds = 1

        i = 0
        end_point_idx = 1  # Track end point position for O(n) performance
        total_points = len(all_price_data)
        last_progress_pct = 0

        while i < len(all_price_data) - 1:
            # Show progress every 25%
            current_progress_pct = int((i / total_points) * 100)
            if current_progress_pct >= last_progress_pct + 25 and current_progress_pct < 100:
                print(f"{DIM}  Processing... {current_progress_pct}% ({i:,}/{total_points:,}){RESET}")
                last_progress_pct = current_progress_pct
            start_point = all_price_data[i]
            start_time = start_point['time']
            target_end_time = start_time + interval_delta

            # Find the closest price point to the end time (resume from last position)
            end_point = None
            end_point_idx = max(end_point_idx, i + 1)  # Ensure we don't go backwards

            for j in range(end_point_idx, len(all_price_data)):
                if all_price_data[j]['time'] >= target_end_time:
                    end_point = all_price_data[j]
                    end_point_idx = j
                    break

            if not end_point:
                # No more valid end points, check if we can use the last point
                if len(all_price_data) > i + 1:
                    end_point = all_price_data[-1]
                    end_point_idx = len(all_price_data) - 1
                else:
                    break

            start_price = start_point['mid_price']
            end_price = end_point['mid_price']
            actual_end_time = end_point['time']

            if start_price > 0:
                change_pct = ((end_price - start_price) / start_price) * 100

                if abs(change_pct) >= self.min_change:
                    price_changes.append({
                        'start_time': start_time,
                        'end_time': actual_end_time,
                        'start_price': start_price,
                        'end_price': end_price,
                        'change_pct': change_pct,
                        'change_abs': abs(change_pct)
                    })

            # Slide window forward by slide_seconds (actually advance the index now)
            next_start_time = start_time + timedelta(seconds=slide_seconds)
            next_i = i + 1

            # Find the first data point at or after next_start_time
            for k in range(i + 1, len(all_price_data)):
                if all_price_data[k]['time'] >= next_start_time:
                    next_i = k
                    break

            i = next_i

        print(f"{GREEN}✓ Found {len(price_changes):,} intervals above {self.min_change}% threshold in {scan_timer.elapsed_str()}{RESET}")

        # Sort by absolute change
        if price_changes:
            print(f"{DIM}  Sorting by magnitude...{RESET}")
            price_changes.sort(key=lambda x: x['change_abs'], reverse=True)

        # De-duplicate overlapping intervals
        print(f"{DIM}  Deduplicating overlapping intervals...{RESET}")
        deduplicated = self._deduplicate_intervals(price_changes)
        print(f"{GREEN}✓ Deduplication: {len(price_changes):,} → {len(deduplicated):,} unique intervals{RESET}")

        # Return top N unique intervals
        result_count = min(self.top_n, len(deduplicated))
        print(f"{GREEN}✓ Returning top {result_count} intervals{RESET}\n")
        return deduplicated[:self.top_n]

    def get_price_data(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get all price points for a specific time interval

        Args:
            start_time: Start of interval
            end_time: End of interval

        Returns:
            List of price point dicts with time, mid_price, best_bid, best_ask, spread
        """
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{self.symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = self.query_api.query(query)

        price_points = []
        for table in result:
            for record in table.records:
                price_points.append({
                    'time': record.get_time(),
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'spread': record.values.get('spread', 0),
                })

        # Sort by time
        price_points.sort(key=lambda x: x['time'])
        return price_points

    def get_whale_events(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get whale events for a specific time interval

        Args:
            start_time: Start of interval
            end_time: End of interval

        Returns:
            List of whale event dicts
        """
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{self.symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = self.query_api.query(query)

        events = []
        for table in result:
            for record in table.records:
                events.append({
                    'time': record.get_time(),
                    'event_type': record.values.get('event_type', 'unknown'),
                    'side': record.values.get('side', 'unknown'),
                    'price': record.values.get('price', 0),
                    'volume': record.values.get('volume', 0),
                    'usd_value': record.values.get('usd_value', 0),
                    'distance_from_mid_pct': record.values.get('distance_from_mid_pct', 0),
                })

        # Sort by time
        events.sort(key=lambda x: x['time'])
        return events

    def analyze(self) -> List[Dict]:
        """
        Run full analysis: find price changes and correlate with whale events

        Returns:
            List of dicts with price change info, price data, and whale events
        """
        print(f"{CYAN}Analyzing price changes for {self.symbol}...{RESET}")

        # Show time configuration
        if self.from_time_str or self.to_time_str:
            time_config = []
            if self.from_time_str:
                time_config.append(f"from {self.from_time_str}")
            if self.to_time_str:
                time_config.append(f"to {self.to_time_str}")
            if self.lookback and not (self.from_time_str and self.to_time_str):
                time_config.append(f"({self.lookback})")
            print(f"{DIM}Time range: {' '.join(time_config)}{RESET}")
        else:
            print(f"{DIM}Lookback: {self.lookback}{RESET}")

        print(f"{DIM}Interval: {self.interval}, Min change: {self.min_change}%{RESET}\n")

        price_changes = self.find_price_changes()

        if not price_changes:
            print(f"{YELLOW}No significant price changes found.{RESET}")
            return []

        print(f"{GREEN}Found {len(price_changes)} intervals with significant price changes{RESET}\n")

        print(f"{DIM}[3/3] Analyzing intervals & fetching whale data...{RESET}")
        analysis_timer = ProgressTimer()
        results = []

        for i, change in enumerate(price_changes, 1):
            # Show progress for every interval (or every 5-10 for large batches)
            show_progress = (len(price_changes) <= 20) or (i % max(1, len(price_changes) // 20) == 0) or (i == len(price_changes))

            if show_progress:
                change_sign = '+' if change['change_pct'] > 0 else ''
                time_str = change['start_time'].strftime('%Y-%m-%d %H:%M:%S')
                print(f"{DIM}→ [{i}/{len(price_changes)}] Interval #{i}: {time_str} ({change_sign}{change['change_pct']:.2f}%){RESET}")

            # Calculate extended time window for context (before and after)
            interval_duration = change['end_time'] - change['start_time']

            # Get price data: before, during, and after the interval
            # Show 10x interval time before and after for better context analysis
            context_multiplier = 10
            extended_start = change['start_time'] - interval_duration * context_multiplier
            extended_end = change['end_time'] + interval_duration * context_multiplier

            # Fetch raw data (for statistics computation only, not for storage)
            fetch_timer = ProgressTimer()
            price_data = self.get_price_data(extended_start, extended_end)
            whale_events = self.get_whale_events(change['start_time'], change['end_time'])
            whale_events_before = self.get_whale_events(extended_start, change['start_time'])
            whale_events_after = self.get_whale_events(change['end_time'], extended_end)

            if show_progress:
                total_events = len(whale_events) + len(whale_events_before) + len(whale_events_after)
                print(f"{DIM}  ⤷ Fetched {len(price_data):,} price points, {total_events} whale events ({fetch_timer.elapsed_str()}){RESET}")

            # Compute statistics (lightweight, for storage)
            price_stats = self._compute_price_statistics(price_data, extended_start, extended_end)
            whale_stats = {
                'before': self._compute_whale_statistics(whale_events_before),
                'during': self._compute_whale_statistics(whale_events),
                'after': self._compute_whale_statistics(whale_events_after)
            }

            # Store results with references + statistics (not raw data)
            results.append({
                'rank': i,
                'start_time': change['start_time'],
                'end_time': change['end_time'],
                'start_price': change['start_price'],
                'end_price': change['end_price'],
                'change_pct': change['change_pct'],

                # Time references for querying raw data on-demand
                'time_windows': {
                    'extended_start': extended_start,
                    'extended_end': extended_end
                },

                # Pre-computed statistics (no raw data)
                'price_stats': price_stats,
                'whale_stats': whale_stats,

                # For backward compatibility and terminal display
                # (will be removed from MongoDB export but kept for display)
                '_price_data': price_data,
                '_whale_events': whale_events,
                '_whale_events_before': whale_events_before,
                '_whale_events_after': whale_events_after
            })

        print(f"{GREEN}✓ Analysis complete! Processed {len(results)} intervals in {analysis_timer.elapsed_str()}{RESET}\n")
        return results

    def _draw_mini_chart(self, price_data: List[Dict], interval_start: datetime, interval_end: datetime,
                         width: int = 70, height: int = 15) -> List[str]:
        """Draw ASCII line chart from price data with interval highlighting"""
        if len(price_data) < 2:
            return [f"{YELLOW}Insufficient data for chart{RESET}"]

        # Extract prices and times
        prices = [p['mid_price'] for p in price_data]
        times = [p['time'] for p in price_data]

        # Calculate price range with padding
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price

        # Avoid division by zero and add padding
        if price_range == 0:
            price_range = max_price * 0.001 if max_price > 0 else 1.0

        # Add 2% padding to top and bottom
        padding = price_range * 0.02
        min_price -= padding
        max_price += padding
        price_range = max_price - min_price

        # Resample data to fit chart width
        step = max(1, len(prices) // width)
        sampled_prices = []
        sampled_times = []
        for i in range(0, len(prices), step):
            chunk = prices[i:i+step]
            sampled_prices.append(sum(chunk) / len(chunk))  # Average
            sampled_times.append(times[i])

        # Ensure we don't exceed chart width
        sampled_prices = sampled_prices[:width]
        sampled_times = sampled_times[:width]

        # Find the exact point where the biggest price change happened
        max_change_col = -1
        max_change_amount = 0
        for col in range(1, len(sampled_prices)):
            change = abs(sampled_prices[col] - sampled_prices[col - 1])
            if change > max_change_amount:
                max_change_amount = change
                max_change_col = col

        # Determine which columns are in the interval (for reference only)
        interval_cols = set()
        for col, t in enumerate(sampled_times):
            if interval_start <= t <= interval_end:
                interval_cols.add(col)

        # Convert prices to row positions
        price_rows = []
        for price in sampled_prices:
            normalized = (price - min_price) / price_range
            row = int((1 - normalized) * (height - 1))
            price_rows.append(row)

        # Create chart grid
        chart = []

        # Draw chart rows (top to bottom = high to low price)
        for row in range(height):
            # Build line
            line_parts = []

            # Add price scale on the left
            if row == 0:
                label = f"{max_price:>9.4f} "
            elif row == height - 1:
                label = f"{min_price:>9.4f} "
            elif row == height // 2:
                label = f"{(max_price + min_price) / 2:>9.4f} "
            else:
                label = " " * 10

            line_parts.append(f"{DIM}{label}{RESET}")
            line_parts.append(f"{DIM}┃{RESET}")

            # Draw chart line
            for col in range(len(price_rows)):
                current_row = price_rows[col]

                # Highlight the exact spike point
                is_spike = (col == max_change_col or col == max_change_col - 1)

                # Determine color based on trend
                if col > 0:
                    prev_price = sampled_prices[col - 1]
                    curr_price = sampled_prices[col]
                    if curr_price > prev_price:
                        base_color = GREEN
                    elif curr_price < prev_price:
                        base_color = RED
                    else:
                        base_color = WHITE
                else:
                    base_color = CYAN

                # Make spike point extremely bright, rest dimmed
                if is_spike:
                    color = f"{BOLD}{base_color}"
                else:
                    color = f"{DIM}{base_color}"

                # Check if we should draw on this row
                if current_row == row:
                    # Draw the main line point
                    if col < len(price_rows) - 1:
                        next_row = price_rows[col + 1]
                        if next_row < current_row:  # Going up
                            # Use special marker for spike
                            if is_spike:
                                line_parts.append(f"{color}▲{RESET}")
                            else:
                                line_parts.append(f"{color}╱{RESET}")
                        elif next_row > current_row:  # Going down
                            # Use special marker for spike
                            if is_spike:
                                line_parts.append(f"{color}▼{RESET}")
                            else:
                                line_parts.append(f"{color}╲{RESET}")
                        else:  # Flat
                            line_parts.append(f"{color}━{RESET}")
                    else:
                        line_parts.append(f"{color}●{RESET}")

                # Draw connecting lines between points
                elif col > 0:
                    prev_row = price_rows[col - 1]
                    next_row = price_rows[col]

                    # Check if line passes through this row
                    if prev_row < next_row:  # Line going down
                        if row > prev_row and row <= next_row:
                            line_parts.append(f"{color}│{RESET}")
                        else:
                            line_parts.append(" ")
                    elif prev_row > next_row:  # Line going up
                        if row < prev_row and row >= next_row:
                            line_parts.append(f"{color}│{RESET}")
                        else:
                            line_parts.append(" ")
                    else:
                        line_parts.append(" ")
                else:
                    line_parts.append(" ")

            chart.append("".join(line_parts))

        # Add time axis with interval markers
        time_axis_parts = [" " * 10, f"{DIM}┗{RESET}"]

        # Calculate time labels
        if len(price_data) > 0:
            start_time = price_data[0]['time']
            end_time = price_data[-1]['time']

            # Build horizontal line with spike marker
            axis_line = []
            for col in range(len(sampled_prices)):
                if col == max_change_col:
                    # Mark the exact spike point
                    if sampled_prices[col] > sampled_prices[col - 1]:
                        axis_line.append(f"{BOLD}{GREEN}▲{RESET}")
                    else:
                        axis_line.append(f"{BOLD}{RED}▼{RESET}")
                else:
                    axis_line.append(f"{DIM}━{RESET}")

            time_axis_parts.append("".join(axis_line))
            chart.append("".join(time_axis_parts))

            # Add time labels with spike marker
            time_label_parts = [" " * 11, f"{DIM}{start_time.strftime('%H:%M:%S')}{RESET}"]

            # Add spike marker label
            if max_change_col >= 0 and max_change_col < len(sampled_times):
                spike_time = sampled_times[max_change_col]

                # Calculate spacing
                spaces_before_spike = max(0, max_change_col - 8)
                if spaces_before_spike > 0:
                    time_label_parts.append(" " * spaces_before_spike)

                # Determine if price went up or down
                if sampled_prices[max_change_col] > sampled_prices[max_change_col - 1]:
                    spike_marker = f"{BOLD}{GREEN}↑SPIKE{RESET}"
                else:
                    spike_marker = f"{BOLD}{RED}↓SPIKE{RESET}"

                time_label_parts.append(spike_marker)

                spaces_after = max(0, len(sampled_prices) - max_change_col - 14)
                if spaces_after > 0:
                    time_label_parts.append(" " * spaces_after)
            else:
                time_label_parts.append(" " * (len(sampled_prices) - 16))

            time_label_parts.append(f"{DIM}{end_time.strftime('%H:%M:%S')}{RESET}")
            chart.append("".join(time_label_parts))

        return chart

    def display_terminal(self, results: List[Dict]):
        """Display results in terminal with color coding"""
        for result in results:
            change_pct = result['change_pct']
            color = GREEN if change_pct > 0 else RED

            print(f"{BOLD}{'='*80}{RESET}")
            print(f"{BOLD}Rank #{result['rank']}: {color}{change_pct:+.3f}%{RESET} price change{RESET}")
            print(f"{DIM}Time: {result['start_time']} → {result['end_time']}{RESET}")
            print(f"{DIM}Price: ${result['start_price']:.2f} → ${result['end_price']:.2f}{RESET}")

            # Use temporary raw data fields for terminal display
            price_data = result.get('_price_data', [])
            whale_events_during = result.get('_whale_events', [])
            whale_stats = result.get('whale_stats', {})

            print(f"{DIM}Price data points: {len(price_data)}{RESET}")

            # Draw price chart (only if enough data points for meaningful visualization)
            if price_data and len(price_data) >= 10:
                print(f"\n{BOLD}Price Movement:{RESET} {DIM}(spike point highlighted with ▲/▼ marker){RESET}")
                chart_lines = self._draw_mini_chart(
                    price_data,
                    result['start_time'],
                    result['end_time']
                )
                for line in chart_lines:
                    print(line)
            elif price_data and len(price_data) >= 2:
                print(f"\n{DIM}Price Movement: {len(price_data)} data points (too few for chart, try larger interval){RESET}")

            # Event summary (from statistics)
            if whale_stats and whale_stats.get('during'):
                during_stats = whale_stats['during']
                print(f"\n{BOLD}Whale Activity Summary:{RESET}")
                for event_type, stats in during_stats.get('by_type', {}).items():
                    event_color = self._get_event_color(event_type)
                    print(f"  {event_color}{event_type:15s}{RESET}: {stats['count']:3d} events, "
                          f"${stats['total_usd']:,.0f} total")

            # Detailed timeline
            if whale_events_during:
                print(f"\n{BOLD}Event Timeline ({len(whale_events_during)} events):{RESET}")
                for event in whale_events_during[:20]:  # Show first 20
                    event_color = self._get_event_color(event['event_type'], event.get('side', ''))
                    time_str = event['time'].strftime('%H:%M:%S.%f')[:-3]
                    print(f"  {DIM}{time_str}{RESET} {event_color}{event['event_type']:15s}{RESET} "
                          f"${event['price']:.2f} × {event['volume']:.4f} "
                          f"= ${event['usd_value']:,.0f}")

                if len(whale_events_during) > 20:
                    print(f"  {DIM}... and {len(whale_events_during) - 20} more events{RESET}")
            else:
                print(f"\n{DIM}No whale events during this interval{RESET}")

            print()

    def _get_event_color(self, event_type: str, side: str = '') -> str:
        """
        Get color for event type based on market impact
        Bright colors = definitive events, Dim colors = volume changes (ambiguous)
        """
        # Definitive market events - bright colors
        if event_type == 'market_buy':
            return CYAN
        elif event_type == 'market_sell':
            return MAGENTA
        # Volume changes - muted colors (could be cancellations or modifications)
        elif event_type == 'increase':
            return f"{DIM}{GREEN}" if side == 'bid' else f"{DIM}{RED}"
        elif event_type == 'decrease':
            return f"{DIM}{RED}" if side == 'bid' else f"{DIM}{GREEN}"
        # New orders - bright colors
        elif 'bid' in event_type or 'buy' in event_type:
            return GREEN
        elif 'ask' in event_type or 'sell' in event_type:
            return RED
        else:
            return WHITE

    def export_json(self, results: List[Dict], filepath: str = None, save_to_db: bool = True, save_to_file: bool = False):
        """Export results to MongoDB (and optionally to JSON file for backup)"""
        # Convert datetime objects to strings and prepare lightweight data structure
        intervals = []
        for result in results:
            # Only include statistics and references (not raw data)
            export_result = {
                'rank': result['rank'],
                'symbol': self.symbol,
                'start_time': result['start_time'].isoformat(),
                'end_time': result['end_time'].isoformat(),
                'start_price': result['start_price'],
                'end_price': result['end_price'],
                'change_pct': result['change_pct'],

                # Time references for on-demand data fetching
                'time_windows': {
                    'extended_start': result['time_windows']['extended_start'].isoformat(),
                    'extended_end': result['time_windows']['extended_end'].isoformat()
                },

                # Pre-computed statistics (already serializable, no datetime objects)
                'price_stats': result['price_stats'],
                'whale_stats': result['whale_stats']
            }

            intervals.append(export_result)

        # Create export data with metadata
        export_data = {
            'analysis': {
                'symbol': self.symbol,
                'lookback': self.lookback,
                'interval': self.interval,
                'min_change': self.min_change,
                'timestamp': datetime.now().isoformat()
            },
            'intervals': intervals
        }

        # Save to MongoDB (primary storage)
        analysis_id = None
        if save_to_db:
            try:
                # Import here to avoid circular dependencies
                import sys
                import os
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from src.mongodb_storage import get_mongodb_storage

                mongo = get_mongodb_storage()
                if mongo:
                    metadata = {
                        'filename': os.path.basename(filepath) if filepath else f'price_changes_{self.symbol}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                        'top_n': self.top_n
                    }
                    analysis_id = mongo.save_analysis('price_changes', export_data, metadata)
                    print(f"{GREEN}✓ Saved to MongoDB with ID: {analysis_id}{RESET}")
                    mongo.close()
                else:
                    print(f"{YELLOW}Warning: MongoDB not available{RESET}")
                    if not save_to_file and filepath:
                        print(f"{YELLOW}Consider using file export as backup{RESET}")
            except Exception as e:
                print(f"{YELLOW}Warning: Could not save to MongoDB: {e}{RESET}")
                if not save_to_file and filepath:
                    print(f"{YELLOW}Consider using file export as backup{RESET}")

        # Optionally save to JSON file (backup or if MongoDB failed)
        if save_to_file and filepath:
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2)
            print(f"{GREEN}✓ Backup saved to {filepath}{RESET}")

        return analysis_id

    def export_csv(self, results: List[Dict], filepath: str):
        """Export results to CSV file"""
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'Rank', 'Start Time', 'End Time', 'Start Price', 'End Price',
                'Change %', 'Event Count', 'Event Types', 'Total USD Volume'
            ])

            # Data
            for result in results:
                event_types = ', '.join(result['event_summary'].keys())
                total_usd = sum(s['total_usd'] for s in result['event_summary'].values())

                writer.writerow([
                    result['rank'],
                    result['start_time'].isoformat(),
                    result['end_time'].isoformat(),
                    result['start_price'],
                    result['end_price'],
                    result['change_pct'],
                    len(result['whale_events']),
                    event_types,
                    total_usd
                ])

        print(f"{GREEN}Exported to {filepath}{RESET}")

    def close(self):
        """Close InfluxDB client"""
        self.client.close()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze price changes and correlate with whale activity'
    )

    parser.add_argument(
        '--symbol',
        type=str,
        default='BTC_USDT',
        help='Trading pair symbol (default: BTC_USDT)'
    )

    parser.add_argument(
        '--lookback',
        type=str,
        default='24h',
        help='Time period to analyze (e.g., 1h, 6h, 24h, 7d) (default: 24h)'
    )

    parser.add_argument(
        '--interval',
        type=str,
        default='1m',
        help='Window size for price changes (e.g., 1s, 5s, 10s, 30s, 1m, 5m, 15m, 30m, 1h) (default: 1m)'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of top intervals to show (default: 10)'
    )

    parser.add_argument(
        '--min-change',
        type=float,
        default=0.1,
        help='Minimum price change %% to consider (default: 0.1)'
    )

    parser.add_argument(
        '--output',
        type=str,
        choices=['terminal', 'json', 'csv'],
        default='terminal',
        help='Output format (default: terminal)'
    )

    parser.add_argument(
        '--export-path',
        type=str,
        help='Path for JSON/CSV export (auto-generated if not specified)'
    )

    parser.add_argument(
        '--from-time',
        type=str,
        help='Start time for analysis (ISO 8601: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ"). If not specified, uses --lookback from now.'
    )

    parser.add_argument(
        '--to-time',
        type=str,
        help='End time for analysis (ISO 8601: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ"). If not specified, uses now or from-time + lookback.'
    )

    parser.add_argument(
        '--save-db',
        action='store_true',
        help='Save results to MongoDB database (independent of output format)'
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    total_timer = ProgressTimer()

    try:
        print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
        print(f"{CYAN}Price Change Analyzer{RESET}")
        print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}\n")

        print(f"{DIM}Initializing analyzer for {args.symbol}...{RESET}")
        analyzer = PriceChangeAnalyzer(
            symbol=args.symbol,
            lookback=args.lookback,
            interval=args.interval,
            min_change=args.min_change,
            top_n=args.top,
            from_time=args.from_time,
            to_time=args.to_time
        )
        print(f"{GREEN}✓ Connected to InfluxDB{RESET}\n")

        results = analyzer.analyze()

        if not results:
            return

        # Handle output format
        if args.output == 'terminal':
            analyzer.display_terminal(results)
        elif args.output == 'json':
            # JSON output mode: save to file
            if args.export_path:
                export_path = args.export_path
            else:
                # Create data directory if it doesn't exist
                data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
                os.makedirs(data_dir, exist_ok=True)
                filename = f"price_changes_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                export_path = os.path.join(data_dir, filename)

            analyzer.export_json(results, filepath=export_path, save_to_db=False, save_to_file=True)
        elif args.output == 'csv':
            # Create data directory if it doesn't exist
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)

            if args.export_path:
                export_path = args.export_path
            else:
                filename = f"price_changes_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                export_path = os.path.join(data_dir, filename)

            analyzer.export_csv(results, export_path)

        # Handle --save-db flag (independent of output format)
        if args.save_db:
            print(f"\n{DIM}Saving to MongoDB...{RESET}")
            analysis_id = analyzer.export_json(results, save_to_db=True, save_to_file=False)
            if analysis_id:
                print(f"{GREEN}MongoDB ID: {analysis_id}{RESET}")

        analyzer.close()

        print(f"\n{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
        print(f"{GREEN}✓ Complete! Total time: {total_timer.elapsed_str()}{RESET}")
        print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}\n")

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
