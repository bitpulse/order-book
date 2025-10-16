"""
Live Data Blueprint
Handles live data streaming endpoints for real-time charts
"""

from flask import Blueprint, render_template, jsonify, request
from services import InfluxDBService
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
live_data_bp = Blueprint('live_data', __name__)

# Initialize services
influxdb_service = InfluxDBService()


@live_data_bp.route('/live')
def live_dashboard():
    """Serve the live chart page"""
    return render_template('live_chart.html')


@live_data_bp.route('/api/config/symbols')
def get_symbols():
    """Get list of monitored trading symbols"""
    return jsonify({
        'symbols': MONITORED_SYMBOLS,
        'default': DEFAULT_SYMBOL
    })


@live_data_bp.route('/api/live/price-history')
def get_live_price_history():
    """
    Get price history for live chart

    Query params:
        symbol: Trading symbol (optional, defaults to DEFAULT_SYMBOL)
        lookback: Time duration like "1h", "30m" (optional, defaults to "1h")
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    lookback = request.args.get('lookback', '1h')

    # Validate symbol
    from utils.validators import validate_symbol
    is_valid, error_msg = validate_symbol(symbol)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    price_history, error = influxdb_service.get_price_history(symbol, lookback)

    if error:
        return jsonify({'error': error}), 500

    return jsonify({
        'symbol': symbol,
        'lookback': lookback,
        'data': price_history,
        'count': len(price_history)
    })


@live_data_bp.route('/api/live/whale-events')
def get_live_whale_events():
    """
    Get recent whale events for live chart - supports incremental updates

    Query params:
        symbol: Trading symbol (optional, defaults to DEFAULT_SYMBOL)
        lookback: Time duration like "1h", "30m" (optional, defaults to "30m")
        min_usd: Minimum USD value filter (optional, defaults to 5000)
        last_timestamp: Last timestamp for incremental updates (optional, ISO format)
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    lookback = request.args.get('lookback', '30m')
    min_usd = request.args.get('min_usd', 5000, type=float)
    last_timestamp = request.args.get('last_timestamp')  # For incremental updates

    # Validate symbol
    from utils.validators import validate_symbol
    is_valid, error_msg = validate_symbol(symbol)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    events, is_incremental, error = influxdb_service.get_live_whale_events(
        symbol, lookback, min_usd, last_timestamp
    )

    if error:
        return jsonify({'error': error}), 500

    return jsonify({
        'symbol': symbol,
        'lookback': lookback,
        'events': events,
        'is_incremental': is_incremental,
        'count': len(events)
    })


@live_data_bp.route('/api/live/orderbook')
def get_live_orderbook():
    """
    Get latest orderbook snapshot

    Query params:
        symbol: Trading symbol (optional, defaults to DEFAULT_SYMBOL)
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)

    # Validate symbol
    from utils.validators import validate_symbol
    is_valid, error_msg = validate_symbol(symbol)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    orderbook, error = influxdb_service.get_orderbook_snapshot(symbol)

    if error:
        return jsonify({'error': error}), 500

    if orderbook:
        return jsonify(orderbook)
    else:
        return jsonify({'error': 'No orderbook data found'}), 404


@live_data_bp.route('/api/live/stats')
def get_live_stats():
    """
    Get live statistics for a symbol

    Query params:
        symbol: Trading symbol (optional, defaults to DEFAULT_SYMBOL)
    """
    symbol = request.args.get('symbol', DEFAULT_SYMBOL)

    # Validate symbol
    from utils.validators import validate_symbol
    is_valid, error_msg = validate_symbol(symbol)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    stats, error = influxdb_service.get_live_stats(symbol)

    if error:
        return jsonify({'error': error}), 500

    if stats:
        stats['symbol'] = symbol
        return jsonify(stats)
    else:
        return jsonify({'error': 'No stats available'}), 404
