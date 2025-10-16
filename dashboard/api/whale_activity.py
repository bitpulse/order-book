"""
Whale Activity Blueprint
Handles whale activity and whale events analysis endpoints
"""

from flask import Blueprint, render_template, jsonify, request
from services import MongoDBService, AnalysisService, FileService

# Create blueprint
whale_activity_bp = Blueprint('whale_activity', __name__)

# Initialize services
mongodb_service = MongoDBService()
analysis_service = AnalysisService()
file_service = FileService()


@whale_activity_bp.route('/whale-activity')
def whale_activity():
    """Serve the whale activity page"""
    return render_template('whale_activity.html')


@whale_activity_bp.route('/whale-actions')
def whale_actions():
    """Serve the whale actions page"""
    # Redirect to whale activity with specific view
    return render_template('whale_activity.html')


@whale_activity_bp.route('/api/whale-activity-files')
def list_whale_activity_files():
    """List all whale activity analyses from MongoDB"""
    analyses = mongodb_service.get_analyses('whale_activity', limit=100)
    return jsonify(analyses)


@whale_activity_bp.route('/api/whale-files')
def list_whale_files():
    """
    List all whale-related analyses from MongoDB
    Includes whale_activity, market_orders, etc.
    """
    # Combine analyses from multiple collections
    whale_activity = mongodb_service.get_analyses('whale_activity', limit=50)
    market_orders = mongodb_service.get_analyses('top_market_orders', limit=50)

    # Merge and sort by creation time
    all_analyses = whale_activity + market_orders
    all_analyses.sort(key=lambda x: x.get('created_at_ts', 0), reverse=True)

    return jsonify(all_analyses[:100])


@whale_activity_bp.route('/api/whale-activity-data/<analysis_id>')
def get_whale_activity_data(analysis_id):
    """Get specific whale activity analysis by ID"""
    data = mongodb_service.get_analysis_by_id('whale_activity', analysis_id)

    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'Analysis not found'}), 404


@whale_activity_bp.route('/api/whale-data/<filename>')
def get_whale_data(filename):
    """
    Serve a specific whale activity JSON file (LEGACY - kept for backward compatibility)
    Security: only allow whale_activity_*, market_orders_*, or top_market_orders_* files
    """
    # Validate filename
    allowed_prefixes = ('whale_activity_', 'market_orders_', 'top_market_orders_')
    if not (any(filename.startswith(prefix) for prefix in allowed_prefixes) and filename.endswith('.json')):
        return jsonify({'error': 'Invalid filename'}), 400

    # Try to read from file (legacy support)
    data = file_service.read_json_file(filename)

    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'File not found'}), 404


@whale_activity_bp.route('/api/run-whale-analysis', methods=['POST'])
def run_whale_analysis():
    """Run whale events analyzer OR market orders analyzer"""
    try:
        import json
        data = json.loads(request.data)

        # Validate parameters
        from utils.validators import validate_analysis_params
        is_valid, error_msg = validate_analysis_params(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        # Run analysis
        success, mongodb_id, error = analysis_service.run_whale_analysis(data)

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
