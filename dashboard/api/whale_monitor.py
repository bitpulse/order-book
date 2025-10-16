"""
Whale Monitor Blueprint
Handles whale monitoring endpoints
"""

from flask import Blueprint, render_template, jsonify, request
from services import MongoDBService, AnalysisService

# Create blueprint
whale_monitor_bp = Blueprint('whale_monitor', __name__)

# Initialize services
mongodb_service = MongoDBService()
analysis_service = AnalysisService()


@whale_monitor_bp.route('/whale-monitor')
def whale_monitor():
    """Serve the whale monitor page"""
    return render_template('whale_monitor.html')


@whale_monitor_bp.route('/api/whale-monitor-files')
def list_whale_monitor_files():
    """List all whale monitor analyses from MongoDB"""
    analyses = mongodb_service.get_analyses('whale_monitor', limit=100)
    return jsonify(analyses)


@whale_monitor_bp.route('/api/whale-monitor-data/<analysis_id>')
def get_whale_monitor_data(analysis_id):
    """Get specific whale monitor analysis by ID"""
    data = mongodb_service.get_analysis_by_id('whale_monitor', analysis_id)

    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'Analysis not found'}), 404


@whale_monitor_bp.route('/api/run-whale-monitor', methods=['POST'])
def run_whale_monitor():
    """Run whale monitor with provided parameters"""
    try:
        import json
        data = json.loads(request.data)

        symbol = data.get('symbol', 'SPX_USDT')
        threshold = data.get('threshold', 50000)

        # Validate symbol
        from utils.validators import validate_symbol
        is_valid, error_msg = validate_symbol(symbol)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        # Validate threshold
        try:
            threshold = float(threshold)
            if threshold <= 0:
                return jsonify({'error': 'Threshold must be positive'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid threshold value'}), 400

        # Run monitor
        success, mongodb_id, error = analysis_service.run_whale_monitor({
            'symbol': symbol,
            'threshold': threshold
        })

        if success:
            return jsonify({
                'success': True,
                'message': 'Whale monitor completed successfully',
                'id': mongodb_id
            })
        else:
            return jsonify({'error': error}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
