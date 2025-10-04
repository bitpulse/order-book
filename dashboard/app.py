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


@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')


@app.route('/whale-actions')
def whale_actions():
    """Serve the whale actions analysis page"""
    return render_template('whale_actions.html')


@app.route('/whale-monitor')
def whale_monitor():
    """Serve the whale event monitor page"""
    return render_template('whale_monitor.html')


@app.route('/api/files')
def list_files():
    """List all available price change JSON files"""
    try:
        if not DATA_DIR.exists():
            return jsonify({'files': [], 'error': 'Data directory not found'})

        # Find all price_changes_*.json files
        files = []
        for file_path in DATA_DIR.glob('price_changes_*.json'):
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


@app.route('/api/data/<filename>')
def get_data(filename):
    """Serve a specific price change JSON file"""
    try:
        # Security: only allow price_changes_*.json files
        if not filename.startswith('price_changes_') or not filename.endswith('.json'):
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


@app.route('/api/whale-files')
def list_whale_files():
    """List all available whale activity JSON files"""
    try:
        if not DATA_DIR.exists():
            return jsonify({'files': [], 'error': 'Data directory not found'})

        # Find all whale_activity_*.json files
        files = []
        for file_path in DATA_DIR.glob('whale_activity_*.json'):
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


@app.route('/api/whale-data/<filename>')
def get_whale_data(filename):
    """Serve a specific whale activity JSON file"""
    try:
        # Security: only allow whale_activity_*.json files
        if not filename.startswith('whale_activity_') or not filename.endswith('.json'):
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

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8') if stderr else 'Unknown error'
            return jsonify({'error': f'Analysis failed: {error_msg}'}), 500

        # Find the newly created file
        files = sorted(DATA_DIR.glob(f'price_changes_{symbol}_*.json'), key=lambda x: x.stat().st_mtime, reverse=True)

        if files:
            newest_file = files[0]
            return jsonify({
                'success': True,
                'message': 'Analysis completed successfully',
                'filename': newest_file.name,
                'output': stdout.decode('utf-8') if stdout else ''
            })
        else:
            return jsonify({'error': 'Analysis completed but no output file found'}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Analysis timeout (exceeded 5 minutes)'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/run-whale-analysis', methods=['POST'])
def run_whale_analysis():
    """Run whale events analyzer with provided parameters"""
    import subprocess
    import sys
    from datetime import datetime

    try:
        data = json.loads(request.data)

        symbol = data.get('symbol', 'BANANA_USDT')
        lookback = data.get('lookback', '3h')
        interval = data.get('interval', '30s')
        top = data.get('top', 10)
        min_usd = data.get('min_usd', 10000)
        sort_by = data.get('sort_by', 'volume')

        # Build command
        script_path = LIVE_DIR / 'whale_events_analyzer.py'

        if not script_path.exists():
            return jsonify({'error': f'Analyzer script not found: {script_path}'}), 404

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

        # Find the newly created file
        files = sorted(DATA_DIR.glob(f'whale_activity_{symbol}_*.json'), key=lambda x: x.stat().st_mtime, reverse=True)

        if files:
            newest_file = files[0]
            return jsonify({
                'success': True,
                'message': 'Whale analysis completed successfully',
                'filename': newest_file.name,
                'output': stdout.decode('utf-8') if stdout else ''
            })
        else:
            return jsonify({'error': 'Analysis completed but no output file found'}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Analysis timeout (exceeded 5 minutes)'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/whale-monitor-files')
def list_whale_monitor_files():
    """List all available whale monitor JSON files"""
    try:
        if not DATA_DIR.exists():
            return jsonify({'files': [], 'error': 'Data directory not found'})

        # Find all whale_monitor_*.json files
        files = []
        for file_path in DATA_DIR.glob('whale_monitor_*.json'):
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


@app.route('/api/whale-monitor-data/<filename>')
def get_whale_monitor_data(filename):
    """Serve a specific whale monitor JSON file"""
    try:
        # Security: only allow whale_monitor_*.json files
        if not filename.startswith('whale_monitor_') or not filename.endswith('.json'):
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


@app.route('/api/run-whale-monitor', methods=['POST'])
def run_whale_monitor():
    """Run whale event monitor with provided parameters"""
    import subprocess

    try:
        data = json.loads(request.data)

        symbol = data.get('symbol', 'BANANA_USDT')
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

        # Find the newly created file
        files = sorted(DATA_DIR.glob(f'whale_monitor_{symbol}_*.json'), key=lambda x: x.stat().st_mtime, reverse=True)

        if files:
            newest_file = files[0]
            return jsonify({
                'success': True,
                'message': 'Whale monitor completed successfully',
                'filename': newest_file.name,
                'output': stdout.decode('utf-8') if stdout else ''
            })
        else:
            return jsonify({'error': 'Monitor completed but no output file found'}), 500

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
