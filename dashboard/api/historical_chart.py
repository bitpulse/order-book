"""
Historical Chart Blueprint
Handles historical data endpoints for timestamp-based chart visualization
"""

from flask import Blueprint, render_template, jsonify, request
from services import InfluxDBService
from datetime import datetime, timedelta
import os
import sys
import importlib.util

# Load dashboard config explicitly to avoid conflict with src/config.py
dashboard_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(dashboard_dir, 'config.py')

if os.path.exists(config_path):
    # Load config.py as a module
    spec = importlib.util.spec_from_file_location("dashboard_config", config_path)
    dashboard_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dashboard_config)
    MONITORED_SYMBOLS = dashboard_config.MONITORED_SYMBOLS
    DEFAULT_SYMBOL = dashboard_config.DEFAULT_SYMBOL
else:
    # Fallback to defaults
    MONITORED_SYMBOLS = ['SPX_USDT', 'BTC_USDT', 'ETH_USDT']
    DEFAULT_SYMBOL = 'SPX_USDT'

# Create blueprint
historical_chart_bp = Blueprint('historical_chart', __name__)

# Initialize services
influxdb_service = InfluxDBService()


@historical_chart_bp.route('/historical')
def historical_dashboard():
    """Serve the historical chart page"""
    return render_template('historical_chart.html')


@historical_chart_bp.route('/api/historical/price-history')
def get_historical_price_history():
    """
    Get price history for a specific timestamp with configurable interval

    Query params:
        symbol: Trading symbol (optional, defaults to DEFAULT_SYMBOL)
        timestamp: Center timestamp in ISO format (required)
        interval: Minutes before/after timestamp (optional, defaults to 5)
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    timestamp_str = request.args.get('timestamp')
    interval = int(request.args.get('interval', 5))  # Default ±5 minutes

    # Validate symbol
    from utils.validators import validate_symbol
    is_valid, error_msg = validate_symbol(symbol)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    # Validate timestamp
    if not timestamp_str:
        return jsonify({'error': 'timestamp parameter is required'}), 400

    try:
        # Parse timestamp
        center_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Calculate window based on interval
        start_time = center_time - timedelta(minutes=interval)
        end_time = center_time + timedelta(minutes=interval)

        # Convert to RFC3339 format for InfluxDB
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    except (ValueError, AttributeError) as e:
        return jsonify({'error': f'Invalid timestamp format: {str(e)}'}), 400

    # Fetch data from InfluxDB
    price_history, error = influxdb_service.get_price_data(symbol, start_str, end_str)

    if error:
        return jsonify({'error': error}), 500

    return jsonify({
        'symbol': symbol,
        'center_timestamp': timestamp_str,
        'start_time': start_str,
        'end_time': end_str,
        'window_minutes': 10,
        'data': price_history,
        'count': len(price_history)
    })


@historical_chart_bp.route('/api/historical/whale-events')
def get_historical_whale_events():
    """
    Get whale events for a specific timestamp with configurable interval

    Query params:
        symbol: Trading symbol (optional, defaults to DEFAULT_SYMBOL)
        timestamp: Center timestamp in ISO format (required)
        interval: Minutes before/after timestamp (optional, defaults to 5)
        min_usd: Minimum USD value filter (optional, defaults to 5000)
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    timestamp_str = request.args.get('timestamp')
    interval = int(request.args.get('interval', 5))  # Default ±5 minutes
    min_usd = request.args.get('min_usd', 5000, type=float)

    # Validate symbol
    from utils.validators import validate_symbol
    is_valid, error_msg = validate_symbol(symbol)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    # Validate timestamp
    if not timestamp_str:
        return jsonify({'error': 'timestamp parameter is required'}), 400

    try:
        # Parse timestamp
        center_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Calculate window based on interval
        start_time = center_time - timedelta(minutes=interval)
        end_time = center_time + timedelta(minutes=interval)

        # Convert to RFC3339 format for InfluxDB
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    except (ValueError, AttributeError) as e:
        return jsonify({'error': f'Invalid timestamp format: {str(e)}'}), 400

    # Fetch data from InfluxDB
    events, error = influxdb_service.get_whale_events(symbol, start_str, end_str)

    if error:
        return jsonify({'error': error}), 500

    # Filter by min_usd
    filtered_events = [e for e in events if e.get('usd_value', 0) >= min_usd]

    return jsonify({
        'symbol': symbol,
        'center_timestamp': timestamp_str,
        'start_time': start_str,
        'end_time': end_str,
        'window_minutes': 10,
        'min_usd': min_usd,
        'events': filtered_events,
        'count': len(filtered_events),
        'total_count': len(events)
    })


@historical_chart_bp.route('/api/historical/stats')
def get_historical_stats():
    """
    Get statistics for a specific timestamp with configurable interval

    Query params:
        symbol: Trading symbol (optional, defaults to DEFAULT_SYMBOL)
        timestamp: Center timestamp in ISO format (required)
        interval: Minutes before/after timestamp (optional, defaults to 5)
        min_usd: Minimum USD value filter (optional, defaults to 5000)
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    timestamp_str = request.args.get('timestamp')
    interval = int(request.args.get('interval', 5))  # Default ±5 minutes
    min_usd = request.args.get('min_usd', 5000, type=float)

    # Validate symbol
    from utils.validators import validate_symbol
    is_valid, error_msg = validate_symbol(symbol)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    # Validate timestamp
    if not timestamp_str:
        return jsonify({'error': 'timestamp parameter is required'}), 400

    try:
        # Parse timestamp
        center_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Calculate window based on interval
        start_time = center_time - timedelta(minutes=interval)
        end_time = center_time + timedelta(minutes=interval)

        # Convert to RFC3339 format for InfluxDB
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    except (ValueError, AttributeError) as e:
        return jsonify({'error': f'Invalid timestamp format: {str(e)}'}), 400

    # Fetch price data for statistics
    price_history, price_error = influxdb_service.get_price_data(symbol, start_str, end_str)

    if price_error:
        return jsonify({'error': price_error}), 500

    # Fetch whale events for statistics
    events, events_error = influxdb_service.get_whale_events(symbol, start_str, end_str)

    if events_error:
        return jsonify({'error': events_error}), 500

    # Filter events by min_usd
    filtered_events = [e for e in events if e.get('usd_value', 0) >= min_usd]

    # Calculate statistics
    stats = {
        'symbol': symbol,
        'center_timestamp': timestamp_str,
        'window_minutes': 10,
        'total_events': len(filtered_events),
        'total_events_unfiltered': len(events)
    }

    # Price statistics
    if price_history:
        prices = [p.get('mid_price', 0) for p in price_history if p.get('mid_price')]
        if prices:
            stats['current_price'] = prices[-1]
            stats['start_price'] = prices[0]
            stats['min_price'] = min(prices)
            stats['max_price'] = max(prices)
            stats['avg_price'] = sum(prices) / len(prices)
            stats['price_change'] = prices[-1] - prices[0]
            stats['price_change_pct'] = ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] != 0 else 0

    # Event statistics by type
    event_counts = {}
    buy_events = []
    sell_events = []

    for event in filtered_events:
        event_type = event.get('event_type', 'unknown')
        side = event.get('side', 'unknown')
        usd_value = event.get('usd_value', 0)

        # Count by type
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

        # Separate by side for buy/sell analysis
        if side == 'bid' or event_type == 'market_buy':
            buy_events.append(usd_value)
        elif side == 'ask' or event_type == 'market_sell':
            sell_events.append(usd_value)

    stats['event_counts'] = event_counts

    # Buy/Sell statistics
    if buy_events:
        stats['total_buy_volume'] = sum(buy_events)
        stats['avg_buy_size'] = sum(buy_events) / len(buy_events)
        stats['max_buy_size'] = max(buy_events)
        stats['buy_count'] = len(buy_events)
    else:
        stats['total_buy_volume'] = 0
        stats['avg_buy_size'] = 0
        stats['max_buy_size'] = 0
        stats['buy_count'] = 0

    if sell_events:
        stats['total_sell_volume'] = sum(sell_events)
        stats['avg_sell_size'] = sum(sell_events) / len(sell_events)
        stats['max_sell_size'] = max(sell_events)
        stats['sell_count'] = len(sell_events)
    else:
        stats['total_sell_volume'] = 0
        stats['avg_sell_size'] = 0
        stats['max_sell_size'] = 0
        stats['sell_count'] = 0

    # Calculate net flow and ratio
    stats['net_flow'] = stats['total_buy_volume'] - stats['total_sell_volume']

    if stats['total_sell_volume'] > 0:
        stats['buy_sell_ratio'] = stats['total_buy_volume'] / stats['total_sell_volume']
    else:
        stats['buy_sell_ratio'] = float('inf') if stats['total_buy_volume'] > 0 else 0

    return jsonify(stats)
