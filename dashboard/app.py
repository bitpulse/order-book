#!/usr/bin/env python3
"""
Flask Dashboard Server for Price Change Analyzer
Serves web interface for visualizing price changes and whale events
"""

import os
import json
from flask import Flask, render_template, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path

app = Flask(__name__)
CORS(app)  # Enable CORS for development

# Get the data directory path
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'


@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')


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
