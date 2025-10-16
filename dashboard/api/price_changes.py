"""
Price Changes Blueprint
Handles price change analysis endpoints
"""

from flask import Blueprint, render_template, jsonify, request
from services import MongoDBService, InfluxDBService, AnalysisService

# Create blueprint
price_changes_bp = Blueprint('price_changes', __name__)

# Initialize services
mongodb_service = MongoDBService()
influxdb_service = InfluxDBService()
analysis_service = AnalysisService()


@price_changes_bp.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')


@price_changes_bp.route('/api/files')
def list_files():
    """List all price change analyses from MongoDB"""
    analyses = mongodb_service.get_analyses('price_changes', limit=100)
    return jsonify({'files': analyses})


@price_changes_bp.route('/api/data/<analysis_id>')
def get_data(analysis_id):
    """Get specific price change analysis by ID"""
    data = mongodb_service.get_analysis_by_id('price_changes', analysis_id)

    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'Analysis not found'}), 404


@price_changes_bp.route('/api/stats')
def get_stats():
    """Get statistics about price change analyses"""
    analyses = mongodb_service.get_analyses('price_changes', limit=1000)

    stats = {
        'total_analyses': len(analyses),
        'symbols': list(set(a['symbol'] for a in analyses if a.get('symbol'))),
        'latest_analysis': analyses[0] if analyses else None
    }

    return jsonify(stats)


@price_changes_bp.route('/api/price-data')
def get_price_data():
    """
    Fetch raw price data from InfluxDB for a specific time range
    Used by frontend to load chart data on-demand

    Query params:
        symbol: Trading symbol (e.g., BTC_USDT)
        start: Start time (ISO 8601 format)
        end: End time (ISO 8601 format)
    """
    symbol = request.args.get('symbol')
    start = request.args.get('start')
    end = request.args.get('end')

    if not all([symbol, start, end]):
        return jsonify({'error': 'Missing required parameters: symbol, start, end'}), 400

    price_data, error = influxdb_service.get_price_data(symbol, start, end)

    if error:
        return jsonify({'error': error}), 500

    return jsonify({
        'price_data': price_data,
        'count': len(price_data)
    })


@price_changes_bp.route('/api/whale-events')
def get_whale_events():
    """
    Fetch raw whale events from InfluxDB for a specific time range
    Used by frontend to load event markers on-demand

    Query params:
        symbol: Trading symbol (e.g., BTC_USDT)
        start: Start time (ISO 8601 format)
        end: End time (ISO 8601 format)
    """
    symbol = request.args.get('symbol')
    start = request.args.get('start')
    end = request.args.get('end')

    if not all([symbol, start, end]):
        return jsonify({'error': 'Missing required parameters: symbol, start, end'}), 400

    whale_events, error = influxdb_service.get_whale_events(symbol, start, end)

    if error:
        return jsonify({'error': error}), 500

    return jsonify({
        'whale_events': whale_events,
        'count': len(whale_events)
    })


@price_changes_bp.route('/api/run-analysis', methods=['POST'])
def run_analysis():
    """Run price change analyzer with provided parameters"""
    try:
        import json
        data = json.loads(request.data)

        # Validate parameters
        from utils.validators import validate_analysis_params
        is_valid, error_msg = validate_analysis_params(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        # Run analysis
        success, mongodb_id, error = analysis_service.run_price_change_analysis(data)

        if success:
            return jsonify({
                'success': True,
                'message': 'Analysis completed successfully',
                'id': mongodb_id
            })
        else:
            return jsonify({'error': error}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@price_changes_bp.route('/api/delete/<analysis_id>', methods=['DELETE'])
def delete_analysis(analysis_id):
    """Delete a price change analysis by ID"""
    try:
        success = mongodb_service.delete_analysis('price_changes', analysis_id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Analysis deleted successfully'
            })
        else:
            return jsonify({'error': 'Analysis not found or could not be deleted'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500
