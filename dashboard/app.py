#!/usr/bin/env python3
"""
Flask Dashboard Server for Order Book Analytics
Serves web interface for visualizing price changes, whale events, and live data

This is the main application file that initializes Flask and registers all blueprints.
Business logic is organized into services and API routes are in blueprints.
"""

import sys
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

# Add dashboard directory to Python path for imports
dashboard_dir = Path(__file__).parent
if str(dashboard_dir) not in sys.path:
    sys.path.insert(0, str(dashboard_dir))

# Import utilities and blueprints
from utils.paths import BASE_DIR, DATA_DIR, LIVE_DIR
from api import register_blueprints

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for development

# Register all API blueprints
register_blueprints(app)


# Global error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(Exception)
def handle_exception(error):
    """Handle all other exceptions"""
    import traceback
    print(f"Unhandled exception: {error}")
    print(traceback.format_exc())
    return jsonify({'error': str(error)}), 500


if __name__ == '__main__':
    print("=" * 80)
    print("Order Book Analytics Dashboard")
    print("=" * 80)
    print()
    print(f"Base directory: {BASE_DIR}")
    print(f"Data directory: {DATA_DIR}")
    print(f"Live scripts directory: {LIVE_DIR}")
    print()

    # Check if data directory exists
    if not DATA_DIR.exists():
        print(f"⚠️  WARNING: Data directory not found: {DATA_DIR}")
        print(f"   Please run the analysis scripts first to generate data.")
    else:
        json_files = list(DATA_DIR.glob('*.json'))
        print(f"✓ Data directory found: {len(json_files)} JSON file(s)")

    print()
    print("=" * 80)
    print("Dashboard will be available at: http://localhost:5000")
    print("=" * 80)
    print()
    print("Available endpoints:")
    print("  • /                         - Price change analyzer dashboard")
    print("  • /live                     - Live orderbook chart")
    print("  • /historical               - Historical chart (timestamp-based)")
    print("  • /top-market-orders        - Top market orders analysis")
    print("  • /market-orders-intervals  - Market orders intervals analysis")
    print("  • /whale-activity           - Whale activity analysis")
    print("  • /whale-monitor            - Whale monitor")
    print()
    print("API Documentation:")
    print("  • /api/files                - List price change analyses")
    print("  • /api/data/<id>            - Get specific analysis")
    print("  • /api/price-data           - Fetch raw price data (on-demand)")
    print("  • /api/whale-events         - Fetch raw whale events (on-demand)")
    print("  • /api/historical/*         - Historical chart data endpoints")
    print("  • /api/run-analysis         - Run new analysis")
    print()
    print("Starting server...")
    print()

    # Run the Flask development server
    app.run(debug=True, host='0.0.0.0', port=5000)
