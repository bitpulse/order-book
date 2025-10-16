#!/usr/bin/env python3
"""
Flask Dashboard Server for Price Change Analyzer
Serves web interface for visualizing price changes and whale events
"""

import os
import json
from flask import Flask, render_template, jsonify, send_from_directory, request
from flask_cors import CORS
from pathlib import Path

# Import config - handle both local and Docker paths
try:
    from dashboard.config import MONITORED_SYMBOLS, DEFAULT_SYMBOL
except ModuleNotFoundError:
    from config import MONITORED_SYMBOLS, DEFAULT_SYMBOL

app = Flask(__name__)
CORS(app)  # Enable CORS for development

# Get the data directory path
# In Docker, files are at /app/data and /app/live
# In local dev, files are at ../data and ../live
if os.getenv('DOCKER_ENV'):
    BASE_DIR = Path('/app')
else:
    BASE_DIR = Path(__file__).parent.parent

DATA_DIR = BASE_DIR / 'data'
LIVE_DIR = BASE_DIR / 'live'


def get_analyses_from_mongodb(collection_name, limit=100):
    """
    Get analyses from MongoDB only
    Returns list of analysis metadata
    """
    analyses = []

    try:
        import sys
        import os
        # Ensure the parent directory is in path (should contain 'src' folder)
        parent_dir = str(BASE_DIR)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Also add src directory itself for Docker environments
        src_dir = os.path.join(parent_dir, 'src')
        if os.path.exists(src_dir) and src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        from src.mongodb_storage import get_mongodb_storage
        from datetime import datetime

        mongo = get_mongodb_storage()
        if mongo:
            results = mongo.get_analyses(collection_name, limit=limit)
            for analysis in results:
                # Handle created_at - could be datetime or string
                created_at = analysis.get('created_at')
                if created_at:
                    if isinstance(created_at, datetime):
                        created_at_iso = created_at.isoformat()
                        created_at_ts = created_at.timestamp()
                    else:
                        created_at_iso = created_at
                        try:
                            created_at_ts = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                        except:
                            created_at_ts = 0
                else:
                    created_at_iso = None
                    created_at_ts = 0

                analyses.append({
                    'id': analysis['_id'],
                    'filename': analysis.get('metadata', {}).get('filename', 'N/A'),
                    'symbol': analysis.get('symbol'),
                    'created_at': created_at_iso,
                    'created_at_ts': created_at_ts,
                    'source': 'mongodb'
                })
            mongo.close()

            # Sort by creation time (newest first)
            analyses.sort(key=lambda x: x.get('created_at_ts', 0), reverse=True)
    except Exception as e:
        import traceback
        print(f"MongoDB query failed for {collection_name}: {e}")
        print(traceback.format_exc())

    return analyses


def get_analysis_from_mongodb(collection_name, analysis_id):
    """
    Get a specific analysis from MongoDB by ID
    Returns the analysis data or None
    """
    try:
        import sys
        import os
        # Ensure the parent directory is in path (should contain 'src' folder)
        parent_dir = str(BASE_DIR)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Also add src directory itself for Docker environments
        src_dir = os.path.join(parent_dir, 'src')
        if os.path.exists(src_dir) and src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        from src.mongodb_storage import get_mongodb_storage

        mongo = get_mongodb_storage()
        if mongo:
            analysis = mongo.get_analysis_by_id(collection_name, analysis_id)
            mongo.close()
            if analysis:
                return analysis['data']
    except Exception as e:
        import traceback
        print(f"MongoDB query failed: {e}")
        print(traceback.format_exc())

    return None


@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')


@app.route('/top-market-orders')
def top_market_orders():
    """Serve the top market orders analysis page"""
    return render_template('top_market_orders.html')


@app.route('/market-orders-intervals')
def market_orders_intervals():
    """Serve the market orders intervals analysis page"""
    return render_template('market_orders_intervals.html')


@app.route('/whale-activity')
def whale_activity():
    """Serve the whale activity analysis page (all event types)"""
    return render_template('whale_activity.html')


@app.route('/whale-actions')
def whale_actions():
    """Redirect old whale-actions to top-market-orders"""
    from flask import redirect
    return redirect('/top-market-orders')


@app.route('/whale-monitor')
def whale_monitor():
    """Serve the whale event monitor page"""
    return render_template('whale_monitor.html')


@app.route('/live')
def live_dashboard():
    """Serve the live chart dashboard page"""
    return render_template('live_chart.html')


# ===== Live Dashboard API Endpoints =====

@app.route('/api/config/symbols')
def get_symbols():
    """Get list of monitored symbols"""
    return jsonify({
        'symbols': MONITORED_SYMBOLS,
        'default': DEFAULT_SYMBOL
    })


@app.route('/api/live/price-history')
def get_live_price_history():
    """Get live price history from InfluxDB"""
    from influxdb_client import InfluxDBClient
    from dotenv import load_dotenv

    load_dotenv()

    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    lookback = request.args.get('lookback', '1h')

    try:
        client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL"),
            token=os.getenv("INFLUXDB_TOKEN"),
            org=os.getenv("INFLUXDB_ORG")
        )
        query_api = client.query_api()
        bucket = os.getenv("INFLUXDB_BUCKET")

        # Query for mid price history
        query = f'''
        from(bucket: "{bucket}")
          |> range(start: -{lookback})
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> filter(fn: (r) => r._field == "mid_price")
          |> aggregateWindow(every: 1s, fn: last, createEmpty: false)
        '''

        tables = query_api.query(query)

        price_data = []
        for table in tables:
            for record in table.records:
                price_data.append({
                    'time': record.get_time().isoformat(),
                    'price': record.get_value()
                })

        client.close()

        return jsonify({
            'symbol': symbol,
            'lookback': lookback,
            'data': price_data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live/whale-events')
def get_live_whale_events():
    """Get live whale events from InfluxDB - optimized for incremental updates"""
    from influxdb_client import InfluxDBClient
    from dotenv import load_dotenv
    from datetime import datetime

    load_dotenv()

    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    lookback = request.args.get('lookback', '30m')
    min_usd = request.args.get('min_usd', 5000, type=float)
    last_timestamp = request.args.get('last_timestamp')  # ISO format timestamp

    try:
        client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL"),
            token=os.getenv("INFLUXDB_TOKEN"),
            org=os.getenv("INFLUXDB_ORG")
        )
        query_api = client.query_api()
        bucket = os.getenv("INFLUXDB_BUCKET")

        # If last_timestamp provided, only fetch newer events (incremental)
        # Otherwise fetch full history (initial load)
        if last_timestamp:
            # Convert ISO timestamp to RFC3339 format for Flux
            # Handle URL decoding: space back to +, then + to Z
            start_time = last_timestamp.replace(' 00:00', '+00:00').replace('+00:00', 'Z')

            # Use time() function in Flux to properly parse RFC3339 timestamp
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: time(v: "{start_time}"))
              |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
              |> filter(fn: (r) => r.symbol == "{symbol}")
              |> filter(fn: (r) => r._field == "usd_value" or r._field == "price" or r._field == "volume" or r._field == "distance_from_mid_pct")
              |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> filter(fn: (r) => r.usd_value >= {min_usd})
              |> sort(columns: ["_time"], desc: false)
            '''
        else:
            # Initial load - get historical events
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{lookback})
              |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
              |> filter(fn: (r) => r.symbol == "{symbol}")
              |> filter(fn: (r) => r._field == "usd_value" or r._field == "price" or r._field == "volume" or r._field == "distance_from_mid_pct")
              |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> filter(fn: (r) => r.usd_value >= {min_usd})
              |> sort(columns: ["_time"], desc: true)
              |> limit(n: 100)
            '''

        tables = query_api.query(query)

        # Parse events from pivoted data
        events = []

        for table in tables:
            for record in table.records:
                event = {
                    'time': record.get_time().isoformat(),
                    'event_type': record.values.get('event_type'),
                    'side': record.values.get('side'),
                    'price': record.values.get('price'),
                    'volume': record.values.get('volume'),
                    'usd_value': record.values.get('usd_value'),
                    'distance_from_mid_pct': record.values.get('distance_from_mid_pct')
                }
                events.append(event)

        if last_timestamp:
            # For incremental updates, sort ascending (oldest first)
            events.sort(key=lambda x: x['time'])
        else:
            # For initial load, sort descending (newest first) and limit
            events.sort(key=lambda x: x['time'], reverse=True)
            events = events[:100]

        client.close()

        return jsonify({
            'symbol': symbol,
            'lookback': lookback,
            'events': events,
            'is_incremental': last_timestamp is not None,
            'count': len(events)
        })

    except Exception as e:
        import traceback
        error_details = {
            'error': str(e),
            'type': type(e).__name__,
            'traceback': traceback.format_exc()
        }
        print(f"Error in whale events API: {error_details}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/live/orderbook')
def get_live_orderbook():
    """Get current order book snapshot from InfluxDB"""
    from influxdb_client import InfluxDBClient
    from dotenv import load_dotenv

    load_dotenv()

    symbol = request.args.get('symbol', DEFAULT_SYMBOL)

    try:
        client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL"),
            token=os.getenv("INFLUXDB_TOKEN"),
            org=os.getenv("INFLUXDB_ORG")
        )
        query_api = client.query_api()
        bucket = os.getenv("INFLUXDB_BUCKET")

        # Query for latest orderbook price data (best bid/ask)
        query = f'''
        from(bucket: "{bucket}")
          |> range(start: -1m)
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> last()
        '''

        tables = query_api.query(query)

        orderbook_data = {
            'symbol': symbol,
            'timestamp': None,
            'best_bid': None,
            'best_ask': None,
            'mid_price': None,
            'spread': None
        }

        for table in tables:
            for record in table.records:
                field = record.get_field()
                value = record.get_value()
                time = record.get_time()

                if not orderbook_data['timestamp']:
                    orderbook_data['timestamp'] = time.isoformat()

                if field == 'best_bid':
                    orderbook_data['best_bid'] = value
                elif field == 'best_ask':
                    orderbook_data['best_ask'] = value
                elif field == 'mid_price':
                    orderbook_data['mid_price'] = value
                elif field == 'spread':
                    orderbook_data['spread'] = value

        client.close()

        return jsonify(orderbook_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live/stats')
def get_live_stats():
    """Get live statistics from InfluxDB"""
    from influxdb_client import InfluxDBClient
    from dotenv import load_dotenv

    load_dotenv()

    symbol = request.args.get('symbol', DEFAULT_SYMBOL)
    lookback = request.args.get('lookback', '1h')

    try:
        client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL"),
            token=os.getenv("INFLUXDB_TOKEN"),
            org=os.getenv("INFLUXDB_ORG")
        )
        query_api = client.query_api()
        bucket = os.getenv("INFLUXDB_BUCKET")

        # Get event counts by type
        event_query = f'''
        from(bucket: "{bucket}")
          |> range(start: -{lookback})
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> filter(fn: (r) => r._field == "usd_value")
          |> group(columns: ["event_type"])
          |> count()
        '''

        tables = query_api.query(event_query)

        event_counts = {}
        total_events = 0

        for table in tables:
            for record in table.records:
                event_type = record.values.get('event_type')
                count = record.get_value()
                event_counts[event_type] = count
                total_events += count

        # Get total volume
        volume_query = f'''
        from(bucket: "{bucket}")
          |> range(start: -{lookback})
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> filter(fn: (r) => r._field == "usd_value")
          |> sum()
        '''

        volume_tables = query_api.query(volume_query)
        total_volume = 0

        for table in volume_tables:
            for record in table.records:
                total_volume = record.get_value()
                break

        client.close()

        return jsonify({
            'symbol': symbol,
            'lookback': lookback,
            'total_events': total_events,
            'total_volume': total_volume,
            'event_counts': event_counts
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/files')
def list_files():
    """List all available price change analyses from MongoDB"""
    try:
        files = get_analyses_from_mongodb('price_changes')
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/<analysis_id>')
def get_data(analysis_id):
    """Serve a specific price change analysis from MongoDB"""
    try:
        data = get_analysis_from_mongodb('price_changes', analysis_id)
        if data:
            return jsonify(data)
        return jsonify({'error': 'Analysis not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def get_stats():
    """Get statistics about available data"""
    try:
        if not DATA_DIR.exists():
            return jsonify({'error': 'Data directory not found'}), 404

        files = list(DATA_DIR.glob('price_changes_*.json'))
        total_size = sum(f.stat().st_size for f in files)

        return jsonify({
            'total_files': len(files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'data_dir': str(DATA_DIR)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/top-market-orders-files')
def list_top_market_orders_files():
    """List top_market_orders analyses from MongoDB"""
    try:
        files = get_analyses_from_mongodb('top_market_orders')
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/market-orders-intervals-files')
def list_market_orders_intervals_files():
    """List market_orders intervals analyses from MongoDB"""
    try:
        files = get_analyses_from_mongodb('market_orders_intervals')
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-activity-files')
def list_whale_activity_files():
    """List whale_activity analyses from MongoDB"""
    try:
        files = get_analyses_from_mongodb('whale_activity')
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-files')
def list_whale_files():
    """List all available whale activity AND market orders JSON files (LEGACY - kept for backward compatibility)"""
    try:
        if not DATA_DIR.exists():
            return jsonify({'files': [], 'error': 'Data directory not found'})

        # Find all whale_activity_*, market_orders_*, and top_market_orders_* files
        files = []
        patterns = ['whale_activity_*.json', 'market_orders_*.json', 'top_market_orders_*.json']
        for pattern in patterns:
            for file_path in DATA_DIR.glob(pattern):
                file_stat = file_path.stat()
                files.append({
                    'filename': file_path.name,
                    'size': file_stat.st_size,
                    'modified': file_stat.st_mtime
                })

        # Sort by modification time (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({'files': files})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/top-market-orders-data/<analysis_id>')
def get_top_market_orders_data(analysis_id):
    """Serve a specific top_market_orders analysis from MongoDB"""
    try:
        data = get_analysis_from_mongodb('top_market_orders', analysis_id)
        if data:
            return jsonify(data)
        return jsonify({'error': 'Analysis not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/market-orders-intervals-data/<analysis_id>')
def get_market_orders_intervals_data(analysis_id):
    """Serve a specific market_orders intervals analysis from MongoDB"""
    try:
        data = get_analysis_from_mongodb('market_orders_intervals', analysis_id)
        if data:
            return jsonify(data)
        return jsonify({'error': 'Analysis not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-activity-data/<analysis_id>')
def get_whale_activity_data(analysis_id):
    """Serve a specific whale_activity analysis from MongoDB"""
    try:
        data = get_analysis_from_mongodb('whale_activity', analysis_id)
        if data:
            return jsonify(data)
        return jsonify({'error': 'Analysis not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-data/<filename>')
def get_whale_data(filename):
    """Serve a specific whale activity OR market orders JSON file (LEGACY - kept for backward compatibility)"""
    try:
        # Security: only allow whale_activity_*, market_orders_*, or top_market_orders_* files
        allowed_prefixes = ('whale_activity_', 'market_orders_', 'top_market_orders_')
        if not (any(filename.startswith(prefix) for prefix in allowed_prefixes) and filename.endswith('.json')):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = DATA_DIR / filename

        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404

        with open(file_path, 'r') as f:
            data = json.load(f)

        return jsonify(data)

    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON file'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_influxdb_client():
    """
    Get configured InfluxDB client

    Returns:
        tuple: (client, query_api) or (None, None) if connection fails
    """
    try:
        from influxdb_client import InfluxDBClient

        influx_url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        influx_token = os.getenv("INFLUXDB_TOKEN")
        influx_org = os.getenv("INFLUXDB_ORG", "trading")

        if not influx_token:
            print("Warning: INFLUXDB_TOKEN not set")
            return None, None

        client = InfluxDBClient(
            url=influx_url,
            token=influx_token,
            org=influx_org
        )

        query_api = client.query_api()
        return client, query_api

    except Exception as e:
        print(f"Failed to connect to InfluxDB: {e}")
        return None, None


@app.route('/api/price-data')
def get_price_data_range():
    """
    Fetch raw price data from InfluxDB for a specific time range
    Used by frontend to load chart data on-demand

    Query params:
        symbol: Trading symbol (e.g., BTC_USDT)
        start: Start time (ISO 8601 format)
        end: End time (ISO 8601 format)
    """
    try:
        symbol = request.args.get('symbol')
        start = request.args.get('start')
        end = request.args.get('end')

        if not all([symbol, start, end]):
            return jsonify({'error': 'Missing required parameters: symbol, start, end'}), 400

        client, query_api = get_influxdb_client()
        if not client:
            return jsonify({'error': 'InfluxDB not configured'}), 500

        influx_bucket = os.getenv("INFLUXDB_BUCKET", "trading_data")

        query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: {start}, stop: {end})
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = query_api.query(query)

        price_points = []
        for table in result:
            for record in table.records:
                price_points.append({
                    'time': record.get_time().isoformat(),
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'spread': record.values.get('spread', 0)
                })

        client.close()

        return jsonify({
            'price_data': price_points,
            'count': len(price_points)
        })

    except Exception as e:
        import traceback
        print(f"Error fetching price data: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-events')
def get_whale_events_range():
    """
    Fetch raw whale events from InfluxDB for a specific time range
    Used by frontend to load event markers on-demand

    Query params:
        symbol: Trading symbol (e.g., BTC_USDT)
        start: Start time (ISO 8601 format)
        end: End time (ISO 8601 format)
    """
    try:
        symbol = request.args.get('symbol')
        start = request.args.get('start')
        end = request.args.get('end')

        if not all([symbol, start, end]):
            return jsonify({'error': 'Missing required parameters: symbol, start, end'}), 400

        client, query_api = get_influxdb_client()
        if not client:
            return jsonify({'error': 'InfluxDB not configured'}), 500

        influx_bucket = os.getenv("INFLUXDB_BUCKET", "trading_data")

        query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: {start}, stop: {end})
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = query_api.query(query)

        events = []
        for table in result:
            for record in table.records:
                events.append({
                    'time': record.get_time().isoformat(),
                    'event_type': record.values.get('event_type', 'unknown'),
                    'side': record.values.get('side', 'unknown'),
                    'price': record.values.get('price', 0),
                    'volume': record.values.get('volume', 0),
                    'usd_value': record.values.get('usd_value', 0),
                    'distance_from_mid_pct': record.values.get('distance_from_mid_pct', 0)
                })

        client.close()

        return jsonify({
            'whale_events': events,
            'count': len(events)
        })

    except Exception as e:
        import traceback
        print(f"Error fetching whale events: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/run-analysis', methods=['POST'])
def run_analysis():
    """Run price change analyzer with provided parameters"""
    import subprocess
    import sys
    from datetime import datetime

    try:
        data = json.loads(request.data)

        symbol = data.get('symbol', 'SPX_USDT')
        lookback = data.get('lookback', '3h')
        interval = data.get('interval', '10s')
        top = data.get('top', 5)
        min_change = data.get('min_change', 0.1)

        # Build command
        script_path = LIVE_DIR / 'price_change_analyzer.py'

        if not script_path.exists():
            return jsonify({'error': f'Analyzer script not found: {script_path}'}), 404

        cmd = [
            sys.executable,
            str(script_path),
            '--symbol', symbol,
            '--lookback', lookback,
            '--interval', interval,
            '--top', str(top),
            '--min-change', str(min_change),
            '--output', 'json'
        ]

        # Run analyzer
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(BASE_DIR),
            env=os.environ.copy()
        )

        # Wait for completion (with timeout)
        stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout

        # Decode output for logging
        output = stdout.decode('utf-8') if stdout else ''
        error_output = stderr.decode('utf-8') if stderr else ''

        # Log the full output for debugging
        print(f"=== Analysis Script Output ===")
        print(f"Return code: {process.returncode}")
        print(f"STDOUT:\n{output}")
        print(f"STDERR:\n{error_output}")
        print(f"==============================")

        if process.returncode != 0:
            return jsonify({
                'error': f'Analysis failed with return code {process.returncode}',
                'stderr': error_output,
                'stdout': output
            }), 500

        # Extract MongoDB ID from stdout
        analysis_id = None

        # Look for "MongoDB ID: <id>" in output
        import re
        match = re.search(r'MongoDB ID: ([a-f0-9]{24})', output)
        if match:
            analysis_id = match.group(1)

        if analysis_id:
            return jsonify({
                'success': True,
                'message': 'Analysis completed successfully',
                'id': analysis_id,
                'output': output
            })
        else:
            return jsonify({
                'error': 'Analysis completed but no MongoDB ID found in output',
                'stdout': output,
                'stderr': error_output,
                'hint': 'Check if MongoDB connection is working and script is outputting MongoDB ID'
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Analysis timeout (exceeded 5 minutes)'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/run-whale-analysis', methods=['POST'])
def run_whale_analysis():
    """Run whale events analyzer OR market orders analyzer"""
    import subprocess
    import sys
    from datetime import datetime

    try:
        data = json.loads(request.data)

        symbol = data.get('symbol', DEFAULT_SYMBOL)
        lookback = data.get('lookback', '3h')
        interval = data.get('interval', '30s')
        top = data.get('top', 10)
        min_usd = data.get('min_usd', 10000)
        sort_by = data.get('sort_by', 'volume')
        analyzer_type = data.get('analyzer_type', 'top_market_orders')  # 'top_market_orders', 'market_orders', or 'all_events'
        max_distance = data.get('max_distance')
        min_distance = data.get('min_distance')

        # Choose analyzer script
        if analyzer_type == 'top_market_orders':
            script_path = LIVE_DIR / 'top_market_orders_analyzer.py'
            file_prefix = 'top_market_orders'
        elif analyzer_type == 'market_orders':
            script_path = LIVE_DIR / 'market_orders_analyzer.py'
            file_prefix = 'market_orders'
        else:
            script_path = LIVE_DIR / 'whale_events_analyzer.py'
            file_prefix = 'whale_activity'

        if not script_path.exists():
            return jsonify({'error': f'Analyzer script not found: {script_path}'}), 404

        # Build command based on analyzer type
        if analyzer_type == 'top_market_orders':
            # No interval needed for individual orders
            cmd = [
                sys.executable,
                str(script_path),
                '--symbol', symbol,
                '--lookback', lookback,
                '--top', str(top),
                '--min-usd', str(min_usd),
                '--sort-by', sort_by,
                '--output', 'json'
            ]
            if max_distance is not None:
                cmd.extend(['--max-distance', str(max_distance)])
            if min_distance is not None:
                cmd.extend(['--min-distance', str(min_distance)])
        else:
            # Interval-based analyzers
            cmd = [
                sys.executable,
                str(script_path),
                '--symbol', symbol,
                '--lookback', lookback,
                '--interval', interval,
                '--top', str(top),
                '--min-usd', str(min_usd),
                '--sort-by', sort_by,
                '--output', 'json'
            ]

        # Run analyzer
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(BASE_DIR),
            env=os.environ.copy()
        )

        # Wait for completion (with timeout)
        stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8') if stderr else 'Unknown error'
            return jsonify({'error': f'Analysis failed: {error_msg}'}), 500

        # Extract MongoDB ID from stdout
        output = stdout.decode('utf-8') if stdout else ''
        import re
        match = re.search(r'MongoDB ID: ([a-f0-9]{24})', output)

        if match:
            analysis_id = match.group(1)
            return jsonify({
                'success': True,
                'message': f'{analyzer_type.replace("_", " ").title()} analysis completed successfully',
                'id': analysis_id,
                'output': output
            })
        else:
            return jsonify({'error': 'Analysis completed but no MongoDB ID found in output'}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Analysis timeout (exceeded 5 minutes)'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-monitor-files')
def list_whale_monitor_files():
    """List whale_monitor analyses from MongoDB"""
    try:
        files = get_analyses_from_mongodb('whale_monitor')
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-monitor-data/<analysis_id>')
def get_whale_monitor_data(analysis_id):
    """Serve a specific whale monitor analysis from MongoDB"""
    try:
        data = get_analysis_from_mongodb('whale_monitor', analysis_id)
        if data:
            return jsonify(data)
        return jsonify({'error': 'Analysis not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/run-whale-monitor', methods=['POST'])
def run_whale_monitor():
    """Run whale event monitor with provided parameters"""
    import subprocess

    try:
        data = json.loads(request.data)

        symbol = data.get('symbol', DEFAULT_SYMBOL)
        lookback = data.get('lookback', '3h')
        min_usd = data.get('min_usd', 5000)
        top = data.get('top', 50)
        max_distance = data.get('max_distance')  # Optional: max distance from mid price as percentage

        # Build command
        script_path = LIVE_DIR / 'whale_monitor.py'

        if not script_path.exists():
            return jsonify({'error': f'Monitor script not found: {script_path}'}), 404

        # Use the same Python executable that's running this Flask app
        import sys
        python_cmd = sys.executable

        cmd = [
            python_cmd,
            str(script_path),
            symbol,
            '--lookback', lookback,
            '--min-usd', str(min_usd),
            '--top', str(top),
            '--export-json'
        ]

        # Add optional max distance filter
        if max_distance is not None:
            cmd.extend(['--max-distance', str(max_distance)])

        # Run monitor
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(BASE_DIR),
            env=os.environ.copy()
        )

        # Wait for completion (with timeout)
        stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8') if stderr else 'Unknown error'
            return jsonify({'error': f'Monitor failed: {error_msg}'}), 500

        # Extract MongoDB ID from stdout
        output = stdout.decode('utf-8') if stdout else ''
        import re
        match = re.search(r'MongoDB ID: ([a-f0-9]{24})', output)

        if match:
            analysis_id = match.group(1)
            return jsonify({
                'success': True,
                'message': 'Whale monitor completed successfully',
                'id': analysis_id,
                'output': output
            })
        else:
            return jsonify({'error': 'Monitor completed but no MongoDB ID found in output'}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Monitor timeout (exceeded 5 minutes)'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    print(f"Starting Price Change Dashboard...")
    print(f"Data directory: {DATA_DIR}")
    print(f"Dashboard will be available at: http://localhost:5000")
    print()

    # Check if data directory exists
    if not DATA_DIR.exists():
        print(f"WARNING: Data directory not found: {DATA_DIR}")
        print(f"Please run the price change analyzer first to generate data.")
    else:
        files = list(DATA_DIR.glob('price_changes_*.json'))
        print(f"Found {len(files)} data file(s)")

    print()
    app.run(debug=True, host='0.0.0.0', port=5000)
